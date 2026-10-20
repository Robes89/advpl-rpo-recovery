"""Experimental typed-object parser. Unsupported layouts stop parsing explicitly."""
from pathlib import Path
import json
import hashlib
import struct
import sys
from collections import Counter

HERE = Path(__file__).resolve().parent


class Unsupported(ValueError):
    pass


class Reader:
    def __init__(self, data):
        self.data, self.at, self.line = data, 0, 0
        self.completed, self.counts = [], Counter()
        self.path = []

    def take(self, size):
        if size < 0 or self.at+size > len(self.data):
            raise Unsupported(f'Truncated field at {self.at}, need {size}')
        result = self.data[self.at:self.at+size]
        self.at += size
        return result

    def byte(self): return self.take(1)[0]
    def u16(self): return struct.unpack('<H', self.take(2))[0]
    def i32(self): return struct.unpack('<i', self.take(4))[0]
    def u32(self): return struct.unpack('<I', self.take(4))[0]
    def i8(self): return struct.unpack('<b', self.take(1))[0]
    def real(self): return struct.unpack('<d', self.take(8))[0]

    def string(self):
        end = self.data.find(b'\0', self.at)
        if end < self.at or end-self.at > 1048576:
            raise Unsupported(f'Invalid string at {self.at}')
        # A lossless byte-to-codepoint carrier; source emission handles high bytes.
        return self.take(end-self.at+1)[:-1].decode('latin1')

    def boolean(self):
        value = self.byte()
        if value not in (ord('T'), ord('F')):
            raise Unsupported(f'Unexpected boolean 0x{value:x} at {self.at-1}')
        return value == ord('T')

    def list_payload(self, n):
        count = self.u16()
        n['children'] = []
        for _ in range(count):
            n['children'].append(self.node())
        if self.boolean():
            n['stack_symbols'] = []
            count = self.count(100000)
            for _ in range(count):
                name = self.string()
                links = [self.i32() for _ in range(self.count(100000))]
                n['stack_symbols'].append({'name': name, 'links': links})

    def count(self, maximum):
        count = self.i32()
        if not 0 <= count <= maximum:
            raise Unsupported(f'Invalid count {count} at {self.at-4}')
        return count

    def node(self):
        if len(self.path) >= 200:
            raise Unsupported('AST nesting budget exceeded')
        start = self.at
        raw = self.byte()
        tag = raw & 0x7f
        if tag == 106:
            tag = self.i32()
        if raw & 0x80:
            self.line = self.u16()
        n = {'tag': tag, 'offset': start, 'source_line': self.line}
        self.counts[tag] += 1
        self.path.append((tag, start))
        try:
            self.payload(n)
            n['end_offset'] = self.at
            self.completed.append(n)
            return n
        finally:
            self.path.pop()

    def payload(self, n):
        t = n['tag']
        if t in (0, 52, 115):
            return
        if t in (2, 3, 4, 5, 6, 7, 8, 9, 92, 93):
            self.list_payload(n)
        elif t in (35, 36, 38, 39, 40, 41):
            n['left'] = self.node()
            n['right'] = self.node() if self.boolean() else None
        elif t in (16, 17, 18, 19, 20, 21, 22, 23, 24, 34, 62, 63, 113, 114, 118, 119, 120):
            a, b = self.boolean(), self.boolean()
            n['left'] = self.node() if a else None
            n['right'] = self.node() if b else None
            if t == 34:
                n['comparison'] = chr(self.byte())
        elif t in (25, 26):
            kind = chr(self.byte())
            n['kind'] = kind
            if kind == 'C':
                n['value'] = self.string()
            elif kind == 'D':
                n['value'] = self.real()
            elif kind == 'L':
                n['value'] = self.boolean()
            elif kind == 'N':
                n['value'] = self.real()
            elif kind == 'U':
                n['value'] = None
            else:
                raise Unsupported(f'Constant kind {kind!r} at {self.at-1}')
        elif t in (29, 31, 94, 95, 96):
            n['scope'] = chr(self.byte())
            n['name'] = self.string()
            if t == 94:
                n['value'] = self.node()
        elif t == 32:
            n['identifier'] = self.node() if self.boolean() else None
        elif t == 27:
            n['name'] = self.string()
        elif t in (28, 30):
            n['identifier'] = self.node()
        elif t in (46, 49, 50, 64, 76):
            n['registered_name'] = self.string()
            n['arguments'] = self.node()
            if t in (49, 50, 64, 76):
                n['function_name'] = self.node()
                n['call_flag'] = self.boolean()
            if t in (64, 76):
                n['method_flag'] = self.boolean()
                n['receiver'] = self.node() if self.boolean() else None
            if t == 76:
                n['dynamic_class'] = self.node()
        elif t in (12, 13, 14, 15):
            present = [self.boolean() for _ in range(3)]
            n['condition'], n['then'], n['else'] = [self.node() if flag else None for flag in present]
        elif t == 11:
            self.list_payload(n)
            n['condition'] = self.node()
        elif t == 10:
            present = [self.boolean() for _ in range(4)]
            n['initialization'], n['limit'], n['step'], n['body'] = [self.node() if flag else None for flag in present]
        elif t in (72, 73, 74, 75, 103, 122):
            n['value'] = self.node() if self.boolean() else None
        elif t == 121:
            n['constant_index'] = self.i32()
        elif t == 59:
            n['elements'] = self.node() if self.boolean() else None
        elif t == 60:
            n['array'], n['index'] = self.node(), self.node()
        elif t == 33:
            n['operator'] = chr(self.byte())
            n['operand'] = self.node()
        elif t == 37:
            self.list_payload(n)
            n['value'] = self.node()
        elif t == 48:
            n['function_name'], n['arguments'] = self.node(), self.node()
        elif t == 61:
            n['operand'] = self.node()
        elif t == 77:
            n['left'], n['right'] = self.node(), self.node()
        elif t in (44, 45):
            n['operator'] = chr(self.byte())
            n['operand'] = self.node()
        elif t == 53:
            n['name'] = self.string()
        elif t == 54:
            n['value'] = self.node()
        elif t in (82, 83, 84, 85, 86, 87, 89, 91):
            n['arguments'] = [self.node() if self.boolean() else None]
        elif t in (80, 88):
            n['arguments'] = [self.node() if self.boolean() else None for _ in range(2)]
        elif t in (81, 90):
            n['arguments'] = [self.node() if self.boolean() else None for _ in range(3)]
        elif t == 99:
            n['symbols'] = [self.string() for _ in range(3)]
        elif t in (55, 56, 57, 58):
            n['left'], n['right'] = self.node(), self.node()
            if t in (57, 58):
                n['operator'] = chr(self.byte())
        elif t == 70:
            n['block'] = self.node()
        elif t == 500:
            # Declaracao tipada (Local x As Tipo): letra do tipo, nome e inteiro de 4 bytes.
            # Validado em CNTA121.PRW (38 ocorrencias, inteiro sempre 0, parse completo).
            n['var_type'] = chr(self.byte())
            n['name'] = self.string()
            n['field_typed'] = self.i32()
        elif t == 78:
            self.list_payload(n)
            n['recover'] = self.node() if self.boolean() else None
        elif t == 79:
            n['symbol'] = self.string() if self.boolean() else None
            n['body'] = self.node()
        elif t in (67, 69, 109):
            n['function_flag'] = chr(self.byte())
            n['name'] = self.string()
            has_body = self.boolean()
            n['has_body'] = has_body
            count = self.i32()
            if not 0 <= count <= 10000:
                raise Unsupported(f'Invalid parameter count at {self.at-4}')
            n['parameters'] = []
            for _ in range(count):
                p = {'name': self.string(), 'type': chr(self.byte())}
                if p['type'] == 'a':
                    p['annotation'] = self.string()
                    p['annotation_items'] = [(self.string(), self.node()) for _ in range(self.i8())]
                    p['type'] = chr(self.byte())
                n['parameters'].append(p)
            n['field_168'], n['body_bytes'] = self.u32(), self.u32()
            body_start = self.at
            if (has_body and n['field_168'] != body_start) or (not has_body and n['field_168'] not in (0, body_start)):
                raise Unsupported(f'Function body offset mismatch at {body_start}')
            n['body'] = self.node() if has_body else None
            n['body_consumed_bytes'] = self.at-body_start
            if n['body_consumed_bytes'] != n['body_bytes']:
                raise Unsupported(f'Function body boundary mismatch at {body_start}: {n["body_bytes"]} vs {n["body_consumed_bytes"]}')
            n['field_170'], extra_size = self.u32(), self.u32()
            extra_start = self.at
            if n['field_170'] != extra_start:
                raise Unsupported(f'Constant pool offset mismatch at {extra_start}')
            n['extra_offset'] = extra_start
            n['extra_bytes'] = self.take(extra_size).hex()
            if extra_size:
                pool = Reader(bytes.fromhex(n['extra_bytes']))
                pool.line = self.line
                count = pool.i32()
                if not 0 <= count <= 100000:
                    raise Unsupported(f'Invalid constant count at {extra_start}')
                n['constants'] = [pool.node() for _ in range(count)]
                if pool.at != extra_size:
                    raise Unsupported(f'Constant pool boundary mismatch at {extra_start}')
            if t == 69:
                n['symbol'] = self.string()
                return
            kind = chr(self.byte())
            if kind == 'A':
                n['annotations'] = []
                for _ in range(self.i8()):
                    annotation = {'name': self.string()}
                    annotation['items'] = [(self.string(), self.node()) for _ in range(self.i8())]
                    n['annotations'].append(annotation)
                kind = chr(self.byte())
            n['function_type'] = kind
            n['symbol'] = self.string()
            n['declared_line'] = self.u32()
        elif t in (104, 117):
            self.list_payload(n)
            n['optional_80'] = self.node() if self.boolean() else None
            n['attribute_99'] = self.boolean()
            n['source_name'] = self.string()
            n['extra_names'] = [self.string() for _ in range(self.count(100000))]
            n['static_definitions'] = self.node()
            classes = self.u16()
            if classes:
                raise Unsupported(f'Class interfaces count {classes} at {self.at-2}')
            count = self.u16()
            n['functions'] = [self.node() for _ in range(count)]
            byte_count = self.i32()
            if byte_count < 0:
                raise Unsupported(f'Negative line map size at {self.at-4}')
            n['source_line_map'] = self.take(max(0, byte_count-1)).hex()
            n['program_source'] = self.string()
            count = self.count(100000)
            n['call_names'] = [self.string() for _ in range(count)]
        else:
            raise Unsupported(f'Unsupported tag {t} at offset {n["offset"]}, source line {n["source_line"]}')


def main(output_dir=HERE, reader_class=Reader):
    sys.setrecursionlimit(5000)
    output_dir = Path(output_dir)
    record = json.loads((output_dir/'decoded-record.json').read_text(encoding='utf-8'))
    data = (output_dir/(Path(record['source']).stem+'.serialized.bin')).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != record['serialized_sha256']:
        raise Unsupported('Serialized record hash differs from verified decryption')
    reader = reader_class(data)
    root, failure = None, None
    try:
        root = reader.node()
        if root.get('program_source') != record['source']:
            raise Unsupported('Unexpected program identity')
        if reader.at != len(data):
            failure = f'Trailing {len(data)-reader.at} serialized bytes'
    except Unsupported as e:
        failure = str(e)
    maximal, covered = [], -1
    for n in sorted(reader.completed, key=lambda n: (n['offset'], -n['end_offset'])):
        if n['offset'] >= covered:
            maximal.append(n)
            covered = n['end_offset']
    result = {'status': 'complete-object-parse' if failure is None else 'partial-object-parse',
              'serialized_sha256': digest,
              'serialized_bytes': len(data), 'consumed_bytes': reader.at,
              'completed_objects': len(reader.completed), 'tag_counts': dict(reader.counts),
              'blocker': failure, 'root': root,
              'completed': maximal if failure is not None else [],
              'limitations': ['Typed object parsing is experimental; unsupported layouts are never skipped or guessed.']}
    (output_dir/'object-parse.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('root', 'completed')}, indent=2))
    return 1 if failure else 0
