"""Emit validated TLPP class bodies without inventing bodyless implementations."""
import advpl_emitter as base


class Emitter(base.Emitter):
    def expr(self,n,missing=False):
        if n is not None and n['tag']==64 and n['method_flag']:
            receiver = self.expr(n['receiver'])
            if receiver.upper()!='SELF' or n['call_flag']:
                self.error(n,'Unconfirmed super dispatch shape')
            self.rendered.add(id(n))
            self.visited[64] += 1
            return 'Super:'+self.expr(n['function_name'])+'('+self.arguments(n['arguments'])+')'
        if n is not None and n['tag']==4009:
            # Literal JSON: o primeiro par traz o JsonObject e a lista dos demais pares.
            if n['json_object'] is None: self.error(n,'JSON pair outside literal')
            parts=[]
            for pair in [n]+n['pairs']['children']:
                self.rendered.add(id(pair))
                self.visited[4009] += 1
                parts.append(base.quote(pair['key'])+': '+self.expr(pair['value']))
            self.expr(n['json_object'])
            self.rendered.add(id(n['pairs']))
            self.visited[n['pairs']['tag']] += 1
            return '{'+', '.join(parts)+'}'
        return super().expr(n,missing)

    def method_head(self,fn):
        kind = self.TYPED.get(fn['function_flag'])
        return fn['symbol']+'('+self.parameters(fn)+')'+(' As '+kind if kind else '')

    def annotations(self,fn):
        # Formato lido do registro: nome + pares (chave, constante). So string/logico confirmados sao emitidos.
        for item in fn.get('annotations',[]):
            values=[]
            for key,node in item['items']:
                if node['tag']==25 and node['kind']=='L':
                    text='.T.' if node['value'] else '.F.'
                elif node['tag']==25 and node['kind']=='C' and '"' not in node['value'] and \
                        not any(ord(c)<32 or 127<=ord(c)<160 for c in node['value']):
                    text='"'+node['value']+'"'
                else:
                    self.error(node,'Unconfirmed annotation value')
                self.rendered.add(id(node))
                self.visited[25] += 1
                values.append(key+'='+text)
            self.put('@'+item['name']+'('+', '.join(values)+')',n=item['items'][0][1] if item['items'] else None)

    def parameters(self,fn):
        names = {'U':None,'C':'Character','L':'Logical','N':'Numeric','D':'Date','O':'Object','A':'Array'}
        result=[]
        for param in fn['parameters']:
            if param['type'] not in names: self.error(fn,'Unknown parameter type')
            value = param['name']
            if names[param['type']]: value += ' As '+names[param['type']]
            result.append(value)
        return ', '.join(result)

    def program(self,root):
        self.references=[]
        if not root['classes']:
            # TLPP so com funcoes, sem Class e sem Namespace (validado em TAFA613.TLPP, 22/10/2026):
            # mesmo layout de programa do PRW, com parametros tipados.
            if root['children'] or root['optional_80'] is not None or root['source_name']:
                self.error(root,'Unsupported additional program contents')
            return base.Emitter.program(self,root)
        self.rendered.add(id(root))
        if root['children'] or root['functions'] or root['optional_80'] is not None:
            self.error(root,'Unsupported additional program contents')
        self.put('// Reconstrucao experimental de '+root['program_source']+'.')
        self.put('// Sem recompilacao ou validacao funcional no Protheus.')
        names = [fn['symbol'] for cls in root['classes'] for fn in cls['methods'] if not fn['has_body']]
        self.put('// Referencias sem corpo no registro: '+(', '.join(names) if names else 'nenhuma')+'.')
        self.put('// Essas referencias permanecem no mapa; nenhum corpo foi inventado.')
        self.put('')
        self.put('Namespace '+root['source_name'])
        self.put('')
        self.statement(root['static_definitions'])
        for cls in root['classes']:
            if not cls['name'].startswith(root['source_name']+'.') or cls['implements']:
                raise base.EmissionError('Unconfirmed class namespace/interfaces')
            name = cls['name'].rsplit('.',1)[1]
            self.annotations(cls)
            self.put('Class '+name+' From '+cls['base_class'])
            scopes={0:'Public',4:'Protected',8:'Private'}
            for field in cls['data']:
                access=scopes.get(field['flags'])
                kind=self.TYPED.get(field['type'])
                if access is None or kind is None or field['declared_type']!=kind.upper():
                    raise base.EmissionError('Unconfirmed class-data scope/type')
                text=access+' Data '+field['name']+' As '+kind
                if field['initializer'] is not None: text+=' Init '+self.expr(field['initializer'])
                self.put(text,1)
            implemented = [fn for fn in cls['methods'] if fn['has_body']]
            for fn in cls['methods']:
                if fn['method_flags'] not in scopes or fn['inherited_call'] is not None:
                    self.error(fn,'Unconfirmed method declaration flags')
                if not fn['has_body']:
                    self.rendered.add(id(fn))
                    self.references.append({'name':fn['symbol'],'offset':fn['offset'],
                                            'body_bytes':fn['body_bytes'],'declared_line':fn['declared_line'],
                                            'status':'bodyless-reference; implementation not present in this record'})
            for fn in sorted(implemented,key=lambda n:n['declared_line']):
                self.put(scopes[fn['method_flags']]+' Method '+self.method_head(fn),1,fn)
            self.put('EndClass')
            for fn in sorted(implemented,key=lambda n:n['declared_line']):
                self.pool=fn.get('constants',[])
                self.rendered.add(id(fn))
                self.put('')
                self.put('// Linha original: '+str(fn['declared_line'])+'; objeto: '+str(fn['offset']))
                self.put('Method '+self.method_head(fn)+' Class '+name,n=fn)
                start=len(self.lines)
                self.statement(fn['body'],1)
                self.functions.append({'name':fn['symbol'],'kind':'Method','class':cls['name'],
                                       'original_line':fn['declared_line'],'serialized_offset':fn['offset'],
                                       'generated_start_line':start,'generated_end_line':len(self.lines)})
