"""File-backed PE32+ AMD64 reader; never loads or executes the image."""
import struct

def read_pe(path):
    data = path.read_bytes()
    if data[:2] != b'MZ':
        raise ValueError('Not an MZ image')
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[pe:pe+4] != b'PE\0\0':
        raise ValueError('Not a PE image')
    machine, count = struct.unpack_from('<HH', data, pe+4)
    optional_size = struct.unpack_from('<H', data, pe+20)[0]
    optional = pe + 24
    if machine != 0x8664 or struct.unpack_from('<H', data, optional)[0] != 0x20b:
        raise ValueError('This script only inspects PE32+ AMD64')
    image_base = struct.unpack_from('<Q', data, optional+24)[0]
    sections = []
    for i in range(count):
        offset = optional + optional_size + 40*i
        name = data[offset:offset+8].rstrip(b'\0').decode('ascii', errors='replace')
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from('<IIII', data, offset+8)
        flags = struct.unpack_from('<I', data, offset+36)[0]
        if raw_offset + raw_size > len(data):
            raise ValueError('Section outside file')
        sections.append((name, rva, raw_offset, raw_size, flags))
    return data, image_base, sections

