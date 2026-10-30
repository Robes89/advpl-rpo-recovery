"""Leitura de patch .ptm. O conteiner e o do RPO; os fontes ficam no registro PATCHINFO.
Layout conferido em um patch do build 24.3.1.5 com 145 registros. Nao abre os .MAP."""
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import contextlib
import hashlib
import io
import json
import struct
import sys
import zlib

import index_reader as idx
import object_reader
import advpl_emitter
from crypto import decrypt

CIPHERS = ['aes-128-cbc','aes-128-ecb','aria-128-cbc','aria-128-ecb',
           'sm4-cbc','sm4-ecb','camellia-128-cbc','camellia-128-ecb']


def write_json(path, value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')


def date(raw):
    return (datetime(1899,12,30)+timedelta(seconds=round(raw*86400))).isoformat(timespec='seconds')


def read_patchinfo(path, appserver, openssl):
    numbers,_ = idx.public_material(appserver)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) < 0x5000: raise idx.FormatError('Patch too small for supported trailer')
    window = raw[-0x5000:]
    length = struct.unpack_from('<I',window)[0]
    if not 1 <= length <= len(window)-4: raise idx.FormatError('Invalid descriptor size')
    fields = idx.parse_descriptor(idx.recover_descriptor(window[4:4+length],numbers))
    profile = (fields['format_build'],fields['appserver_build'])
    if profile not in idx.PROFILES: raise idx.FormatError('Descriptor build is outside the validated profile')
    plain,_ = idx.decode_index(path,window,fields,openssl)
    entries = idx.parse_entries(plain,fields['index_file_offset'],idx.PROFILES[profile])
    selected = [e for e in entries if e['name']=='PATCHINFO']
    if len(selected) != 1: raise idx.FormatError('Expected exactly one PATCHINFO entry')
    entry = selected[0]
    cursor = idx.Cursor(window)
    cursor.binary()
    key_bank = cursor.binary()
    iv_size = cursor.u32()
    iv_bank = cursor.take(min(iv_size,len(window)-cursor.at))
    if len(key_bank)<16 or len(iv_bank)<16: raise idx.FormatError('Missing key/IV slices')
    encrypted = raw[entry['file_offset']:entry['file_offset']+entry['cipher_bytes']]
    compressed = decrypt(encrypted,CIPHERS[entry['field_38']%8],key_bank[:16],iv_bank[:16],openssl)
    if len(compressed) != entry['compressed_bytes']: raise idx.FormatError('Decrypted PATCHINFO length mismatch')
    decoder = zlib.decompressobj()
    data = decoder.decompress(compressed,entry['plain_bytes']+1)
    if not decoder.eof or decoder.unused_data or len(data) != entry['plain_bytes']:
        raise idx.FormatError('PATCHINFO zlib size/checksum mismatch')
    return digest,data


def parse_patchinfo(data):
    c = idx.Cursor(data)
    header = {'rpo_name':c.string(),'date':date(struct.unpack('<d',c.take(8))[0]),'machine':c.string()}
    header['field_a'],header['field_b'] = c.u32(),c.u32()
    header['format_build'] = c.string()
    header['base_date'] = date(struct.unpack('<d',c.take(8))[0])
    c.take(1)
    names = [c.string() for _ in range(c.u32())]
    if c.u32() != len(names): raise idx.FormatError('Record count differs from name list')
    records = []
    for name in names:
        if c.u32() != 0: raise idx.FormatError(f'Unexpected record preamble before {name}')
        first = c.string()
        if c.take(9) != bytes(9): raise idx.FormatError(f'Unexpected record header in {name}')
        second = c.string()
        if not first == second == name: raise idx.FormatError(f'Record out of order: {first} != {name}')
        stamp = struct.unpack('<d',c.take(8))[0]
        flags = (c.u32(),c.u32(),c.u32())
        sequence,plain_bytes,compressed_bytes,stored_bytes = c.u32(),c.u32(),c.u32(),c.u32()
        if compressed_bytes != stored_bytes: raise idx.FormatError(f'Stored size differs in {name}')
        at = c.at
        stored = c.take(stored_bytes)
        decoder = zlib.decompressobj()
        serialized = decoder.decompress(stored,plain_bytes+1)
        if not decoder.eof or decoder.unused_data or len(serialized) != plain_bytes:
            raise idx.FormatError(f'Record zlib size/checksum mismatch in {name}')
        records.append({'name':name,'compiled_datetime':date(stamp),'sequence':sequence,'flags':flags,
                        'patchinfo_offset':at,'plain_bytes':plain_bytes,'compressed_bytes':compressed_bytes,
                        'serialized':serialized})
    return header,records,len(data)-c.at


def public(record):
    return {k:v for k,v in record.items() if k!='serialized'}


def listing(args):
    _,data = read_patchinfo(args.ptm,args.appserver,args.openssl)
    header,records,left = parse_patchinfo(data)
    print(json.dumps({'header':header,'records':[public(r) for r in records],'bytes_after_records':left},indent=1,ensure_ascii=False))


def reconstruct(args):
    name = args.source.upper()
    digest,data = read_patchinfo(args.ptm,args.appserver,args.openssl)
    header,records,left = parse_patchinfo(data)
    selected = [r for r in records if r['name'].upper()==name]
    if len(selected) != 1: raise idx.FormatError('Expected exactly one patch record for '+name)
    entry = selected[0]
    is_tlpp = name.endswith('.TLPP')
    stem = Path(entry['name']).stem
    out = args.output_dir
    suffix = '.tlpp' if is_tlpp else '.prw'
    if (out/'decompilation.json').exists() or (out/(stem+'.reconstruido'+suffix)).exists():
        raise idx.FormatError('Use a fresh output directory to keep earlier results reviewable')
    out.mkdir(parents=True,exist_ok=True)
    serialized = entry['serialized']
    (out/(stem+'.serialized.bin')).write_bytes(serialized)
    write_json(out/'selected-entry.json',{'rpo_sha256':digest,'patch_header':header,'patch_records':len(records),
                                          'bytes_after_records':left,'entries':[public(entry)]})
    write_json(out/'decoded-record.json',{'status':'serialized-record-recovered','source':entry['name'],
                                          'rpo_sha256':digest,'container':'PATCHINFO',
                                          'file_offset':entry['patchinfo_offset'],
                                          'compressed_bytes':entry['compressed_bytes'],
                                          'serialized_bytes':len(serialized),
                                          'serialized_sha256':hashlib.sha256(serialized).hexdigest()})
    reader_class,emitter_class = object_reader.Reader,advpl_emitter.Emitter
    if is_tlpp:
        from tlpp_reader import Reader as reader_class
        from tlpp_emitter import Emitter as emitter_class
    with contextlib.redirect_stdout(io.StringIO()):
        parse_failed = object_reader.main(out,reader_class=reader_class)
    if parse_failed:
        raise idx.FormatError('Incomplete typed parse: inspect object-parse.json; no source emitted')
    with contextlib.redirect_stdout(io.StringIO()):
        advpl_emitter.main(out,emitter_class=emitter_class)
    from checks import verify
    report = verify(out)
    from align_lines import align
    aligned = align(out)
    print(json.dumps({'status':'reconstructed-and-statically-verified','source':str(out/report['source']),
                      'compiled':entry['compiled_datetime'],'functions':report['functions'],
                      'generated_lines':report['generated_lines'],'aligned_source':str(out/aligned['source']),
                      'aligned_lines':aligned['lines'],'aligned_exact_ratio':aligned['exact_ratio'],
                      'patch_records':len(records),'bytes_after_records':left},ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command',required=True)
    for name in ('list','decompile'):
        command = commands.add_parser(name)
        command.add_argument('--ptm',type=Path,required=True)
        command.add_argument('--appserver',type=Path,required=True)
        command.add_argument('--openssl')
        if name == 'decompile':
            command.add_argument('--source',required=True)
            command.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    try:
        listing(args) if args.command=='list' else reconstruct(args)
    except (ValueError,OSError) as error:
        print('Error: '+str(error),file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
