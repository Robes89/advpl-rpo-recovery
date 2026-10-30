"""Offline, build-bound RPO index and ADVPL reconstruction. Python 3.11+, OpenSSL."""
from pathlib import Path
import argparse
import csv
import contextlib
import io
import hashlib
import json
import re
import struct
import sys
import zlib

import index_reader as idx
import object_reader
import advpl_emitter
from crypto import decrypt


def write_json(path, value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def identity_and_window(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream,'sha256').hexdigest()
        size = stream.seek(0,2)
        if size < 0x5000: raise idx.FormatError('RPO too small for supported trailer')
        stream.seek(-0x5000,2)
        window = stream.read(0x5000)
    return digest,size,window


def build_index(args):
    numbers,image_hash = idx.public_material(args.appserver)
    digest,size,window = identity_and_window(args.rpo)
    length = struct.unpack_from('<I',window)[0]
    if not 1 <= length <= len(window)-4: raise idx.FormatError('Invalid descriptor size')
    descriptor = idx.recover_descriptor(window[4:4+length],numbers)
    fields = idx.parse_descriptor(descriptor)
    if (fields['format_build'],fields['appserver_build']) not in idx.PROFILES:
        raise idx.FormatError('Descriptor build is outside the validated profile')
    plain,decoded = idx.decode_index(args.rpo,window,fields,args.openssl)
    entries = idx.parse_entries(plain,fields['index_file_offset'],idx.PROFILES[(fields['format_build'],fields['appserver_build'])])
    if len({r['name'].upper() for r in entries}) != len(entries):
        raise idx.FormatError('Ambiguous index names')
    report = {'status':'index-decoded-and-entry-ranges-validated','rpo_sha256':digest,
              'rpo_bytes':size,'appserver_sha256':image_hash,'descriptor':fields,
              'decoded_index':decoded,'entry_count':len(entries)}
    out = args.output_dir
    out.mkdir(parents=True,exist_ok=True)
    (out/'index-decoded.bin').write_bytes(plain)
    write_json(out/'descriptor.json',report)
    with (out/'index.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(entries[0]) if entries else ['name'],delimiter=';')
        writer.writeheader()
        writer.writerows(entries)
    print(json.dumps({'status':report['status'],'entries':len(entries),'index_dir':str(out)}))


def reconstruct(args):
    name = args.source.upper()
    if not re.fullmatch(r'[A-Z0-9_]+(?:[.\- ][A-Z0-9_]+)*\.(PRW|PRX|TLPP)',name):
        raise idx.FormatError('Expected one indexed PRW, PRX or TLPP basename')
    is_tlpp = name.endswith('.TLPP')
    cached = read_json(args.index_dir/'descriptor.json')
    if cached['appserver_sha256'] != idx.APP_SERVER_SHA256:
        raise idx.FormatError('Cached index uses an unsupported AppServer profile')
    fields = cached['descriptor']
    if (fields['format_build'],fields['appserver_build']) not in idx.PROFILES:
        raise idx.FormatError('Unsupported cached descriptor build')
    plain = (args.index_dir/'index-decoded.bin').read_bytes()
    index_hash = hashlib.sha256(plain).hexdigest()
    if index_hash != cached['decoded_index']['plain_sha256']:
        raise idx.FormatError('Cached index checksum mismatch')
    entries = idx.parse_entries(plain,fields['index_file_offset'],idx.PROFILES[(fields['format_build'],fields['appserver_build'])])
    selected = [r for r in entries if r['name'].upper()==name]
    if len(selected) != 1: raise idx.FormatError('Expected exactly one indexed entry for '+name)
    entry = selected[0]
    stem = Path(entry['name']).stem
    digest,size,window = identity_and_window(args.rpo)
    if digest != cached['rpo_sha256'] or size != cached['rpo_bytes']:
        raise idx.FormatError('RPO identity differs from cached index')
    if entry['cipher_bytes'] <= 0 or entry['cipher_bytes'] > 128*1024*1024 or entry['plain_bytes'] > 128*1024*1024:
        raise idx.FormatError('Source record size outside budget')
    with args.rpo.open('rb') as stream:
        stream.seek(entry['file_offset'])
        encrypted = stream.read(entry['cipher_bytes'])
    if len(encrypted) != entry['cipher_bytes']: raise idx.FormatError('Truncated record')
    cursor = idx.Cursor(window)
    cursor.binary()
    key_bank = cursor.binary()
    iv_size = cursor.u32()
    iv_bank = cursor.take(min(iv_size,len(window)-cursor.at))
    if len(key_bank)<16 or len(iv_bank)<16: raise idx.FormatError('Missing key/IV slices')
    names = ['aes-128-cbc','aes-128-ecb','aria-128-cbc','aria-128-ecb',
             'sm4-cbc','sm4-ecb','camellia-128-cbc','camellia-128-ecb']
    cipher = names[entry['field_38'] % 8]
    compressed = decrypt(encrypted,cipher,key_bank[:16],iv_bank[:16],args.openssl)
    if len(compressed) != (entry['compressed_bytes'] or entry['plain_bytes']):
        raise idx.FormatError('Decrypted record length mismatch')
    if entry['compressed_bytes']:
        decoder = zlib.decompressobj()
        serialized = decoder.decompress(compressed,entry['plain_bytes']+1)
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(serialized)!=entry['plain_bytes']:
            raise idx.FormatError('Record zlib size/checksum mismatch')
    else:
        serialized = compressed
    out = args.output_dir
    suffix = '.tlpp' if is_tlpp else '.prw'
    if (out/'decompilation.json').exists() or (out/(stem+'.reconstruido'+suffix)).exists():
        raise idx.FormatError('Use a fresh output directory to keep earlier results reviewable')
    out.mkdir(parents=True,exist_ok=True)
    (out/(stem+'.serialized.bin')).write_bytes(serialized)
    write_json(out/'selected-entry.json',{'rpo_sha256':digest,'index_sha256':index_hash,'entries':selected})
    record = {'status':'serialized-record-recovered','source':entry['name'],
              'rpo_sha256':digest,'file_offset':entry['file_offset'],'cipher':cipher,
              'cipher_bytes':len(encrypted),'compressed_bytes':len(compressed),
              'serialized_bytes':len(serialized),'serialized_sha256':hashlib.sha256(serialized).hexdigest()}
    write_json(out/'decoded-record.json',record)
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
    print(json.dumps({'status':'reconstructed-and-statically-verified',
                      'source':str(out/report['source']),'functions':report['functions'],
                      'generated_lines':report['generated_lines'],
                      'aligned_source':str(out/aligned['source']),'aligned_lines':aligned['lines'],
                      'aligned_exact_ratio':aligned['exact_ratio'],
                      'limitation':'Experimental reconstruction; not compiled or executed.'}))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest='command',required=True)
    index = commands.add_parser('index',help='Decode index using the supported supplied DLL')
    index.add_argument('--rpo',required=True,type=Path)
    index.add_argument('--appserver',required=True,type=Path,help='Supplied apwinnt.dll (never executed)')
    index.add_argument('--output-dir',required=True,type=Path)
    index.add_argument('--openssl',type=Path)
    index.set_defaults(run=build_index)
    source = commands.add_parser('decompile',help='Reconstruct one PRW/PRX entry or supported TLPP class')
    source.add_argument('--rpo',required=True,type=Path)
    source.add_argument('--index-dir',required=True,type=Path)
    source.add_argument('--source',required=True)
    source.add_argument('--output-dir',required=True,type=Path)
    source.add_argument('--openssl',type=Path)
    source.set_defaults(run=reconstruct)
    check = commands.add_parser('verify',help='Verify existing generated artifacts without execution')
    check.add_argument('--artifact-dir',required=True,type=Path)
    def verification(args):
        from checks import verify
        print(json.dumps(verify(args.artifact_dir),indent=2))
    check.set_defaults(run=verification)
    aligned = commands.add_parser('align',help='Write NAME.alinhado with statements on their original lines (debug)')
    aligned.add_argument('--artifact-dir',required=True,type=Path)
    def alignment(args):
        from align_lines import align
        result = align(args.artifact_dir)
        print(json.dumps({k:v for k,v in result.items() if k!='displaced_sample'},indent=2,ensure_ascii=False))
    aligned.set_defaults(run=alignment)
    args = cli.parse_args()
    try:
        args.run(args)
    except (ValueError,OSError,KeyError,StopIteration,struct.error,RecursionError) as error:
        print('Error: '+str(error),file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__': sys.exit(main())
