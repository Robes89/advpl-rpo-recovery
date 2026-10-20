"""Emit reviewable ADVPL from the recovered typed tree; fail on unknown semantics."""
from pathlib import Path
import json
import hashlib
import math
import sys
from collections import Counter

HERE = Path(__file__).resolve().parent


class EmissionError(ValueError):
    pass


def quote(value):
    # Keep literal bytes, including control characters, independent of delimiters.
    pieces, run = [], ''
    def flush():
        nonlocal run
        if run:
            if '"' not in run:
                pieces.append('"'+run+'"')
            elif "'" not in run:
                pieces.append("'"+run+"'")
            else:
                pieces.append('"'+run.replace('"', '" + Chr(34) + "')+'"')
            run = ''
    for char in value:
        if ord(char) < 32 or ord(char) >= 127:
            flush()
            pieces.append(f'Chr({ord(char)})')
        else:
            run += char
    flush()
    return '('+' + '.join(pieces)+')' if len(pieces)>1 else (pieces[0] if pieces else '""')


class Emitter:
    INTRINSICS = {80:'SubStr',81:'SubStr',82:'Trim',83:'RTrim',84:'LTrim',
                  85:'Lower',86:'Upper',87:'Len',88:'Round',89:'Val',90:'StrZero',91:'DbSelectArea'}
    BINARY = {16:'+',17:'-',18:'*',19:'/',20:'.And.',21:'.Or.',22:'%',23:'^',24:'$',
              113:'<<',114:'>>',118:'+',119:'+',120:'+'}
    ASSIGN = {35:':=',36:':=',38:'+=',39:'-=',40:'*=',41:'/='}
    # Letras validadas: CNTA121.PRW (C/N/L/D/A/O) e MATA103.PRW (B = "Local bATFVlCT as Block").
    TYPED = {'C':'Character','N':'Numeric','L':'Logical','D':'Date','A':'Array','O':'Object','B':'Block'}

    def __init__(self):
        self.pool = []
        self.lines, self.mapping = [], []
        self.visited = Counter()
        self.functions = []
        self.rendered = set()

    def error(self, n, message):
        raise EmissionError(f'{message}; tag {n["tag"]}, offset {n["offset"]}, original line {n["source_line"]}')

    def put(self, text, indent=0, n=None):
        self.lines.append('    '*indent+text)
        if n:
            self.mapping.append({'generated_line':len(self.lines), 'serialized_offset':n['offset'],
                                 'original_line':n['source_line'], 'tag':n['tag']})

    def arguments(self, n):
        if n is None:
            return ''
        self.rendered.add(id(n))
        if n['tag'] not in (2,8,9,92,93):
            self.error(n, 'Unexpected argument container')
        self.visited[n['tag']] += 1
        return ', '.join(self.expr(child, missing=True) for child in n['children'])

    def expr(self, n, missing=False):
        if n is None:
            return '' if missing else 'Nil'
        t = n['tag']
        self.rendered.add(id(n))
        self.visited[t] += 1
        if t == 0:
            return '' if missing else 'Nil'
        if t == 115: return 'JsonObject():New()'
        if t == 500:
            # 'U' = tipo nao reconhecido pelo compilador (ex.: As Caracter): sem tipo efetivo.
            if n['field_typed'] != 0:
                self.error(n, 'Typed declaration with non-zero field not validated')
            if n['var_type'] == 'U':
                return n['name']
            if n['var_type'] not in self.TYPED:
                self.error(n, f'Typed declaration kind {n["var_type"]!r} not validated')
            return n['name']+' As '+self.TYPED[n['var_type']]
        if t == 73:
            return 'Break('+('' if n['value'] is None else self.expr(n['value']))+')'
        if t == 121:
            index = n['constant_index']
            if not 0 <= index < len(self.pool):
                self.error(n, f'Constant reference out of bounds: {index}/{len(self.pool)}')
            return self.expr(self.pool[index])
        if t in (25,26):
            k, v = n['kind'], n['value']
            if k == 'U': return 'Nil'
            if k == 'C': return quote(v)
            if k == 'L': return '.T.' if v else '.F.'
            if k == 'N':
                if not math.isfinite(v): self.error(n, 'Non-finite numeric literal')
                return str(int(v)) if v == int(v) else repr(v)
            self.error(n, f'Unimplemented literal type {k}')
        if t in (27,29,31,95,96):
            return n['name']
        if t in (28,30): return '&('+self.expr(n['identifier'])+')'
        if t == 32: return 'M->'+self.expr(n['identifier'])
        if t in self.BINARY:
            return '('+self.expr(n['left'])+' '+self.BINARY[t]+' '+self.expr(n['right'])+')'
        if t in self.ASSIGN:
            left = self.expr(n['left'])
            return left if n['right'] is None else '('+left+' '+self.ASSIGN[t]+' '+self.expr(n['right'])+')'
        if t == 94: return '('+n['name']+' := '+self.expr(n['value'])+')'
        if t == 34:
            operators = {0:'=',1:'==',2:'<',3:'<=',4:'>',5:'>=',6:'<>'}
            op = operators.get(ord(n['comparison']))
            if op is None: self.error(n, 'Unconfirmed comparison operator')
            return '('+self.expr(n['left'])+' '+op+' '+self.expr(n['right'])+')'
        if t == 33:
            op = {0:'+',1:'-',2:'.Not.'}.get(ord(n['operator']))
            if op is None: self.error(n, 'Unconfirmed unary operator')
            return '('+op+' '+self.expr(n['operand'])+')'
        if t in (44,45):
            op = '++' if t == 44 else '--'
            value = self.expr(n['operand'])
            if ord(n['operator']) == 0: return '('+op+value+')'
            if ord(n['operator']) == 1: return '('+value+op+')'
            self.error(n, 'Unknown increment position')
        if t in (46,49,50,64,76,48):
            if t == 48:
                target = n['function_name']
                if target['tag'] != 54 or target['value']['tag'] not in (27,31,96):
                    self.error(n, 'Unsupported macro call target')
                self.visited[54] += 1
                self.rendered.add(id(target))
                return '&'+self.expr(target['value'])+'.('+self.arguments(n['arguments'])+')'
            name = n.get('registered_name') or self.expr(n['function_name'])
            args = self.arguments(n['arguments'])
            if t == 76:
                return self.expr(n['dynamic_class'])+'():'+name+'('+args+')'
            if t == 64:
                if n['receiver'] is None: self.error(n, 'Method without explicit receiver')
                return self.expr(n['receiver'])+':'+name+'('+args+')'
            return name+'('+args+')'
        if t in self.INTRINSICS:
            return self.INTRINSICS[t]+'('+', '.join(self.expr(a, missing=True) for a in n['arguments'])+')'
        if t == 14:
            return 'IIf('+', '.join(self.expr(n[k]) for k in ('condition','then','else'))+')'
        if t == 59: return '{'+self.arguments(n['elements'])+'}'
        if t == 60: return self.expr(n['array'])+'['+self.arguments(n['index'])+']'
        if t == 61: return '@'+self.expr(n['operand'])
        if t in (62,63):
            right = self.expr(n['right'])
            if n['left'] is None:
                # Campo sem alias (area corrente): forma de REPLACE x WITH y => _FIELD->x := y.
                # Validado em MATA103.PRW (Replace B3_FILIAL With ..., Replace &(cMes) With ...).
                return '_FIELD->'+('('+right+')' if t == 63 else right)
            left = self.expr(n['left'])
            alias = left if n['left']['tag'] == 27 else '('+left+')'
            return alias+'->'+('('+right+')' if t == 63 else right)
        if t == 99:
            if not n['symbols'][1]: self.error(n, 'Alias lacks field expression')
            return n['symbols'][2]
        if t == 77: return self.expr(n['right'])+':'+self.expr(n['left'])
        if t == 53: return '&'+n['name']
        if t == 54: return '&('+self.expr(n['value'])+')'
        if t == 70: return self.expr(n['block'])
        if t == 69:
            old = self.pool
            try:
                body = n['body']
                if body['tag'] in (2,92):
                    self.rendered.add(id(body))
                    value = ', '.join(self.expr(child) for child in body['children'])
                else:
                    value = self.expr(body)
                return '{|'+', '.join(p['name'] for p in n['parameters'])+'| '+value+'}'
            finally:
                self.pool = old
        if t == 37:
            value = self.expr(n['value'])
            for child in reversed(n['children']):
                if child['tag'] not in self.ASSIGN or child['right'] is not None:
                    self.error(child, 'Unsupported chained assignment shape')
                self.visited[child['tag']] += 1
                self.rendered.add(id(child))
                value = '('+self.expr(child['left'])+' := '+value+')'
            return value
        if t in (2,92,93): return '('+self.arguments(n)+')'
        self.error(n, 'Expression emission not implemented')

    def statement(self, n, indent=0, declaration=None):
        if n is None: return
        t = n['tag']
        self.rendered.add(id(n))
        if t in (2,92):
            self.visited[t] += 1
            for child in n['children']: self.statement(child, indent, declaration)
        elif t in (3,4,5,6,7):
            self.visited[t] += 1
            prefix = {3:declaration or 'Static',4:'Private',5:'Public',6:'Local',7:'Static'}[t]
            for child in n['children']:
                value = self.expr(child)
                if child['tag'] in self.ASSIGN and child.get('right') is not None:
                    value = value[1:-1]
                self.put(prefix+' '+value, indent, child)
        elif t in (12,13):
            self.visited[t] += 1
            self.put(('If ' if t == 12 else 'ElseIf ')+self.expr(n['condition']), indent, n)
            self.statement(n['then'], indent+1)
            tail = n['else']
            if tail and tail['tag'] == 13:
                self.statement(tail, indent)
            elif tail:
                self.put('Else', indent)
                self.statement(tail, indent+1)
            if t == 12: self.put('EndIf', indent)
        elif t == 15:
            self.put('Do Case', indent, n)
            current = n
            while current and current['tag'] == 15:
                self.rendered.add(id(current))
                self.visited[15] += 1
                self.put('Case '+self.expr(current['condition']), indent+1, current)
                self.statement(current['then'], indent+2)
                current = current['else']
            if current:
                self.put('Otherwise', indent+1)
                self.statement(current, indent+2)
            self.put('EndCase', indent)
        elif t == 10:
            self.visited[t] += 1
            init = self.expr(n['initialization'])
            if n['initialization']['tag'] in self.ASSIGN: init=init[1:-1]
            value = 'For '+init+' To '+self.expr(n['limit'])
            if n['step'] is not None: value += ' Step '+self.expr(n['step'])
            self.put(value, indent, n)
            self.statement(n['body'], indent+1)
            self.put('Next', indent)
        elif t == 11:
            self.visited[t] += 1
            self.put('While '+self.expr(n['condition']), indent, n)
            for child in n['children']: self.statement(child, indent+1)
            self.put('EndDo', indent)
        elif t == 73:
            self.put(self.expr(n), indent, n)
        elif t in (72,74,75,103):
            self.visited[t] += 1
            word = {72:'Return',73:'Break',74:'Exit',75:'Loop',103:'Throw'}[t]
            self.put(word+(' '+self.expr(n['value']) if n['value'] is not None else ''), indent, n)
        elif t == 78:
            self.visited[t] += 1
            self.put('Begin Sequence', indent, n)
            for child in n['children']: self.statement(child, indent+1)
            if n['recover']: self.statement(n['recover'], indent)
            self.put('End Sequence', indent)
        elif t == 79:
            self.visited[t] += 1
            self.put('Recover'+(' Using '+n['symbol'] if n['symbol'] else ''), indent, n)
            self.statement(n['body'], indent+1)
        elif t == 0:
            self.visited[t] += 1
        else:
            self.put(self.expr(n), indent, n)

    def program(self, root):
        self.rendered.add(id(root))
        self.put('// Reconstrucao experimental de '+root['program_source']+' a partir do RPO fornecido.')
        self.put('// Nao recompilado. Comentarios, macros e formatacao originais nao recuperados.')
        self.put('')
        for child in root['children']: self.statement(child, declaration='Static')
        self.statement(root['static_definitions'], declaration='Static')
        for fn in root['functions']:
            self.rendered.add(id(fn))
            self.pool = fn.get('constants', [])
            prefix = {'F':'Function','f':'Function','T':'Static Function','t':'Static Function',
                      'I':'Init Function','E':'Exit Function','M':'Main Function','L':'Function'}.get(fn['function_type'])
            if not prefix: self.error(fn, 'Unknown declaration kind')
            name = fn['symbol'] or fn['name']
            self.put('')
            self.put('// Linha original: '+str(fn['declared_line'])+'; objeto: '+str(fn['offset']))
            self.put(prefix+' '+name+'('+', '.join(p['name'] for p in fn['parameters'])+')', n=fn)
            first = len(self.lines)
            self.statement(fn['body'], 1)
            self.functions.append({'name':name,'kind':prefix,'original_line':fn['declared_line'],
                                   'generated_start_line':first,'generated_end_line':len(self.lines),
                                   'serialized_offset':fn['offset'],'constant_count':len(self.pool)})


def executable_nodes(value):
    if isinstance(value, list):
        for child in value: yield from executable_nodes(child)
    elif isinstance(value, dict):
        if 'tag' in value: yield value
        for key, child in value.items():
            if key != 'constants': yield from executable_nodes(child)


def main(output_dir=HERE, emitter_class=Emitter):
    sys.setrecursionlimit(5000)
    output_dir = Path(output_dir)
    parsed = json.loads((output_dir/'object-parse.json').read_text(encoding='utf-8'))
    if parsed['status'] != 'complete-object-parse':
        raise EmissionError('Full tree required: '+str(parsed['blocker']))
    emitter = emitter_class()
    emitter.program(parsed['root'])
    nodes = list(executable_nodes(parsed['root']))
    missing = [n for n in nodes if id(n) not in emitter.rendered]
    if missing:
        emitter.error(missing[0], f'{len(missing)} executable objects were not rendered')
    source = '\n'.join(emitter.lines)+'\n'
    is_tlpp = parsed['root']['program_source'].upper().endswith('.TLPP')
    suffix = '.tlpp' if is_tlpp else '.prw'
    destination = output_dir/(Path(parsed['root']['program_source']).stem+'.reconstruido'+suffix)
    destination.write_text(source, encoding='utf-8-sig', newline='\r\n')
    report = {'status':'experimental-advpl-reconstruction','source':destination.name,
              'serialized_sha256':parsed['serialized_sha256'],
              'source_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
              'executable_object_count':len(nodes),'unrendered_objects':len(missing),
              'functions':emitter.functions, 'generated_lines':len(emitter.lines),
              'tag_visits':dict(emitter.visited), 'source_map':emitter.mapping,
              'limitations':['Not compiled or executed; semantic equivalence is unverified.',
                             'Original comments, preprocessor macros, includes and formatting are unavailable.']}
    if is_tlpp:
        report.update(status='experimental-tlpp-class-reconstruction',
                      classes=len(parsed['root']['classes']),implemented_methods=len(emitter.functions),
                      bodyless_references=emitter.references)
        report['limitations'].append('Bodyless method references are retained as metadata; signatures and implementations are not invented.')
    (output_dir/'decompilation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_map','functions')},indent=2))
    print('Functions:',len(emitter.functions))
    return report
