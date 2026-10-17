"""Static artifact checks; these are not a Protheus compiler or equivalence proof."""
from pathlib import Path
import hashlib
import json
import re
import sys
import advpl_emitter


def require(condition, message):
    if not condition: raise ValueError(message)


def lexical(source):
    stack,quote,controls = [],None,[]
    for line in source.splitlines():
        if line.lstrip().startswith('//'): continue
        for char in line:
            if quote:
                if char==quote: quote=None
            elif char in "\"'": quote=char
            elif char in '([{': stack.append(char)
            elif char in ')]}':
                require(bool(stack),'Unbalanced closing delimiter')
                require(stack.pop()=={')':'(',']':'[','}':'{'}[char],'Mismatched delimiter')
        require(quote is None,'Unterminated string')
        text = line.strip().lower()
        if re.match(r'^if\b',text): controls.append('if')
        elif text.startswith('do case'): controls.append('case')
        elif re.match(r'^for\b',text): controls.append('for')
        elif re.match(r'^while\b',text): controls.append('while')
        elif text=='begin sequence': controls.append('sequence')
        elif text in ('endif','endcase','next','enddo','end sequence'):
            require(bool(controls),'Unbalanced closing control')
            require(controls.pop()=={'endif':'if','endcase':'case','next':'for','enddo':'while',
                                    'end sequence':'sequence'}[text],'Mismatched control')
    require(not stack and not controls,'Unclosed delimiter/control')


def verify(directory):
    sys.setrecursionlimit(5000)
    directory = Path(directory)
    def read(name): return json.loads((directory/name).read_text(encoding='utf-8-sig'))
    record,parsed,emitted = read('decoded-record.json'),read('object-parse.json'),read('decompilation.json')
    selected = read('selected-entry.json')
    name = record['source']
    require(Path(name).name==name and re.fullmatch(r'[A-Za-z0-9_]+\.(PRW|PRX)',name,re.I),'Unsafe source name')
    require(emitted['source']==Path(name).stem+'.reconstruido.prw','Unexpected output name')
    entry = selected['entries']
    require(len(entry)==1 and entry[0]['name']==name,'Selected identity mismatch')
    require(selected['rpo_sha256']==record['rpo_sha256'],'RPO identity mismatch')
    binary = (directory/(Path(name).stem+'.serialized.bin')).read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    require(digest==record['serialized_sha256']==parsed['serialized_sha256']==emitted['serialized_sha256'],
            'Serialized hash mismatch')
    require(len(binary)==entry[0]['plain_bytes']==record['serialized_bytes']==parsed['consumed_bytes'],
            'Serialized size/consumption mismatch')
    require(parsed['status']=='complete-object-parse' and not parsed['blocker'],'Incomplete typed parse')
    root = parsed['root']
    require(root['end_offset']==len(binary) and root['program_source']==name,'Program identity/boundary mismatch')
    nodes = list(advpl_emitter.executable_nodes(root))
    for n in nodes:
        if n['tag'] in (67,69,109):
            require(n['body_bytes']==n['body_consumed_bytes'],'Body size mismatch')
            require(n['field_168']==n['body']['offset'],'Body offset mismatch')
            require(n['field_170']==n['extra_offset'],'Pool offset mismatch')
    emitter = advpl_emitter.Emitter()
    emitter.program(root)
    require(all(id(n) in emitter.rendered for n in nodes),'Executable node omitted')
    require(len(nodes)==emitted['executable_object_count'] and emitted['unrendered_objects']==0,'Coverage mismatch')
    source_bytes = (directory/emitted['source']).read_bytes()
    require(hashlib.sha256(source_bytes).hexdigest()==emitted['source_sha256'],'Source hash mismatch')
    source = (directory/emitted['source']).read_text(encoding='utf-8-sig')
    require(source=='\n'.join(emitter.lines)+'\n','Emission differs from tree')
    require(len(emitter.functions)==len(root['functions'])==len(emitted['functions']),'Function count mismatch')
    lexical(source)
    result = {'status':'passed-static-verification','source':emitted['source'],
              'source_sha256':emitted['source_sha256'],'executable_objects':len(nodes),
              'unrendered_objects':0,'functions':len(root['functions']),'generated_lines':len(emitter.lines),
              'checks':['artifact identity and hashes','complete parse','function and pool boundaries',
                        'emission coverage','constant references','deterministic emission','lexical balance'],
              'limitation':'Not compiled or executed; semantic equivalence is unverified.'}
    (directory/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
