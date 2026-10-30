"""Experimental, build-bound RPO index reader. Reads original inputs without executing them."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib
import csv
from datetime import datetime, timedelta

APP_SERVER_SHA256 = '850abee5b279ce7487eab3836a1adcbacfb5643120f962a8a399fdc979317d83'
# Perfis de descritor aceitos e o menor offset de registro de cada um.
# 0419/24.3.0.11: custom.rpo; o primeiro registro inicia em 38, conferido por decifragem e zlib.
# 0419/24.3.1.5: patch .ptm, mesmo conteiner e mesmo cabecalho de 38 bytes.
PROFILES = {('APNSRM0421','24.3.0.0_ts03'):39, ('APNSRM0419','24.3.0.11'):38,
            ('APNSRM0419','24.3.1.5'):38}
from pe_reader import read_pe
from crypto import decrypt


class FormatError(ValueError):
    pass


class Cursor:
    def __init__(self, data):
        self.data, self.at = data, 0

    def take(self, size):
        if size < 0 or self.at+size > len(self.data):
            raise FormatError(f'Truncated field at {self.at}, need {size} bytes')
        result = self.data[self.at:self.at+size]
        self.at += size
        return result

    def u32(self):
        return struct.unpack('<I', self.take(4))[0]

    def i32(self):
        return struct.unpack('<i', self.take(4))[0]

    def string(self):
        end = self.data.find(b'\0', self.at)
        if end < self.at:
            raise FormatError('Missing string terminator')
        return self.take(end-self.at+1)[:-1].decode('latin-1')

    def marker(self, value):
        if self.take(1) != value:
            raise FormatError(f'Expected descriptor marker {value!r}')

    def binary(self, limit=1048576):
        size = self.u32()
        if size > limit:
            raise FormatError('Binary field exceeds budget')
        return self.take(size)


def parse_descriptor(data):
    c = Cursor(data)
    result = {'format_build': c.string(), 'appserver_build': c.string(),
              'field_164': c.i32(), 'field_174': c.i32(), 'field_170': c.i32()}
    c.marker(b'C')
    result['tagged_string_1'] = c.string()
    c.marker(b'N')
    result['tagged_number'] = c.i32()
    c.marker(b'C')
    result['tagged_string_2'] = c.string()
    result['field_160'] = c.i32()
    result['datetime_raw_double'] = struct.unpack('<d', c.take(8))[0]
    position = c.i32()
    result['index_file_offset'] = struct.unpack('<q', c.take(8))[0] if position == -1 else position
    result['index_plain_bytes'] = c.i32()
    result['index_compressed_bytes'] = c.i32()
    result['index_cipher_bytes'] = c.i32()
    result['field_b0'] = c.i32()
    result['field_b4'] = c.i32()
    if c.at != len(data):
        raise FormatError('Unparsed descriptor bytes')
    return result


def der_item(data, at=0, expected=None):
    if at+2 > len(data):
        raise FormatError('Truncated DER header')
    tag, size = data[at], data[at+1]
    start = at+2
    if size & 0x80:
        count = size & 0x7f
        if not 1 <= count <= 4 or start+count > len(data):
            raise FormatError('Invalid DER length')
        size = int.from_bytes(data[start:start+count], 'big')
        start += count
    end = start+size
    if end > len(data) or (expected is not None and tag != expected):
        raise FormatError('DER tag/range mismatch')
    return data[start:end], end


def public_numbers(pem):
    lines = pem.strip().splitlines()
    if lines[0] != b'-----BEGIN PUBLIC KEY-----' or lines[-1] != b'-----END PUBLIC KEY-----':
        raise FormatError('Unexpected public key carrier')
    der = base64.b64decode(b''.join(lines[1:-1]), validate=True)
    spki, end = der_item(der, expected=0x30)
    if end != len(der):
        raise FormatError('Trailing SPKI bytes')
    algorithm, at = der_item(spki, expected=0x30)
    if algorithm != bytes.fromhex('06092a864886f70d0101010500'):
        raise FormatError('Not rsaEncryption')
    bits, end = der_item(spki, at, 0x03)
    if end != len(spki) or not bits or bits[0] != 0:
        raise FormatError('Invalid RSA bit string')
    rsa, end = der_item(bits[1:], expected=0x30)
    if end != len(bits)-1:
        raise FormatError('Trailing RSA bytes')
    modulus, at = der_item(rsa, expected=0x02)
    exponent, end = der_item(rsa, at, 0x02)
    if end != len(rsa):
        raise FormatError('Trailing RSA integer bytes')
    return int.from_bytes(modulus, 'big'), int.from_bytes(exponent, 'big')


def public_material(image_path):
    data, image_base, sections = read_pe(image_path)
    bound_hash = APP_SERVER_SHA256
    digest = hashlib.sha256(data).hexdigest()
    if digest != bound_hash:
        raise FormatError('AppServer image does not match examined build')
    # getRsaCert references the DWORD carrier at this RVA in the examined binary.
    rva = 0x311b990
    section = next(s for s in sections if s[1] <= rva < s[1]+s[3])
    offset = section[2]+rva-section[1]
    private_size, public_size, phrase_size = struct.unpack_from('<III', data, offset)
    if not 1 <= public_size <= 16384 or private_size > 16384 or phrase_size > 1024:
        raise FormatError('Invalid public-material carrier bounds')
    start = offset+4*(3+private_size)
    if start+4*public_size > section[2]+section[3]:
        raise FormatError('Public carrier outside file-backed section')
    mask = bytes.fromhex('033067eaaf1f5b')
    public = bytes(data[start+4*i] ^ mask[i % len(mask)] for i in range(public_size))
    return public_numbers(public), digest


def recover_descriptor(block, numbers):
    n, e = numbers
    size = (n.bit_length()+7)//8
    if len(block) != size or int.from_bytes(block, 'big') >= n:
        raise FormatError('RSA descriptor size/value mismatch')
    padded = pow(int.from_bytes(block, 'big'), e, n).to_bytes(size, 'big')
    separator = padded.find(b'\0', 2)
    if padded[:2] != b'\0\1' or separator < 10 or padded[2:separator] != b'\xff'*(separator-2):
        raise FormatError('Descriptor RSA type-1 padding validation failed')
    return padded[separator+1:]


def decode_index(rpo, window, fields, openssl=None):
    c = Cursor(window)
    c.binary()
    bank_key = c.binary()
    declared_iv = c.u32()
    if not 17 < declared_iv <= 1048576:
        raise FormatError('Invalid IV bank length')
    # Native TMemoryStream::Read clips reads at the window boundary. Do not invent missing bytes.
    bank_iv = c.take(min(declared_iv, len(window)-c.at))
    # In this examined build GetKey/GetIv validate a computed offset, but return
    # the start of their buffers (RVAs 0xabdc60 / 0xabde20), not that offset.
    if len(bank_key) < 16 or len(bank_iv) < 16:
        raise FormatError('Required key/IV slice is not present in supplied trailer window')
    key, iv = bank_key[:16], bank_iv[:16]
    cipher_id = fields['field_b4'] % 8
    names = ['AES-128-CBC', 'AES-128-ECB', 'ARIA-128-CBC', 'ARIA-128-ECB',
             'SM4-CBC', 'SM4-ECB', 'CAMELLIA-128-CBC', 'CAMELLIA-128-ECB']
    for field in ['index_cipher_bytes', 'index_plain_bytes', 'index_compressed_bytes']:
        if not 0 < fields[field] <= 128*1024*1024:
            raise FormatError('Index length outside reader budget')
    at, length = fields['index_file_offset'], fields['index_cipher_bytes']
    if at < 39 or at+length > rpo.stat().st_size-0x5000 or length % 16:
        raise FormatError('Index cipher range is outside the RPO body or block alignment')
    with rpo.open('rb') as f:
        f.seek(at)
        encrypted = f.read(length)
    if len(encrypted) != length:
        raise FormatError('Truncated index ciphertext')
    compressed = decrypt(encrypted, names[cipher_id].lower(), key, iv, openssl)
    if len(compressed) != fields['index_compressed_bytes']:
        raise FormatError('Decoded compressed index length differs from descriptor')
    decoder = zlib.decompressobj()
    plain = decoder.decompress(compressed, fields['index_plain_bytes']+1)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(plain) != fields['index_plain_bytes']:
        raise FormatError('Index zlib stream, checksum or decoded length validation failed')
    metadata = {'cipher': names[cipher_id], 'cipher_bytes': length,
                'compressed_bytes': len(compressed), 'plain_bytes': len(plain),
                'plain_sha256': hashlib.sha256(plain).hexdigest(),
                'key_bank_bytes': len(bank_key), 'iv_bank_declared_bytes': declared_iv,
                'iv_bank_available_bytes': len(bank_iv),
                'required_key_slice_present': True, 'required_iv_slice_present': True}
    return plain, metadata


def parse_entries(plain, body_end, min_offset=39):
    c = Cursor(plain)
    count = c.i32()
    if not 0 <= count <= min(2000000, len(plain)//46):
        raise FormatError('Invalid index entry count')
    entries = []
    for ordinal in range(count):
        start = c.at
        name = c.string()
        if not name or len(name) > 4096 or any(ord(ch) < 32 for ch in name):
            raise FormatError(f'Invalid entry name at {start}')
        stamp = struct.unpack('<d', c.take(8))[0]
        offset = c.i32()
        if offset == -1:
            offset = struct.unpack('<q', c.take(8))[0]
        values = [c.i32() for _ in range(8)]
        status = c.take(1)[0]
        plain_bytes, compressed_bytes, field_34, field_38, field_20, field_24, field_30, cipher_bytes = values
        if min(plain_bytes, compressed_bytes, cipher_bytes) < 0:
            raise FormatError(f'Negative entry size at {start}')
        if cipher_bytes and (offset < min_offset or offset+cipher_bytes > body_end):
            raise FormatError(f'Entry ciphertext outside body: {name!r}')
        try:
            compiled = (datetime(1899, 12, 30)+timedelta(seconds=round(stamp*86400))).isoformat(timespec='seconds')
        except (OverflowError, ValueError):
            raise FormatError(f'Invalid entry date at {start}')
        entries.append({'ordinal': ordinal, 'index_offset': start, 'name': name,
                        'compiled_datetime': compiled, 'datetime_raw_double': stamp,
                        'file_offset': offset, 'plain_bytes': plain_bytes,
                        'compressed_bytes': compressed_bytes, 'cipher_bytes': cipher_bytes,
                        'field_34': field_34, 'field_38': field_38, 'field_20': field_20,
                        'field_24': field_24, 'field_30': field_30, 'status': status})
    if c.at != len(plain):
        raise FormatError(f'Index has {len(plain)-c.at} unparsed bytes')
    return entries

