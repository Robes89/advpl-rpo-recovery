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
        return super().expr(n,missing)

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
            self.put('Class '+name+' From '+cls['base_class'])
            for field in cls['data']:
                access={0:'Public',4:'Protected',8:'Private'}.get(field['flags'])
                if access is None or field['type']!='O' or field['declared_type']!='OBJECT':
                    raise base.EmissionError('Unconfirmed class-data scope/type')
                text=access+' Data '+field['name']+' As Object'
                if field['initializer'] is not None: text+=' Init '+self.expr(field['initializer'])
                self.put(text,1)
            implemented = [fn for fn in cls['methods'] if fn['has_body']]
            for fn in cls['methods']:
                if fn['method_flags']!=0 or fn['inherited_call'] is not None:
                    self.error(fn,'Unconfirmed method declaration flags')
                if not fn['has_body']:
                    self.rendered.add(id(fn))
                    self.references.append({'name':fn['symbol'],'offset':fn['offset'],
                                            'body_bytes':fn['body_bytes'],'declared_line':fn['declared_line'],
                                            'status':'bodyless-reference; implementation not present in this record'})
            for fn in sorted(implemented,key=lambda n:n['declared_line']):
                self.put('Public Method '+fn['symbol']+'('+self.parameters(fn)+')',1,fn)
            self.put('EndClass')
            for fn in sorted(implemented,key=lambda n:n['declared_line']):
                self.pool=fn.get('constants',[])
                self.rendered.add(id(fn))
                self.put('')
                self.put('// Linha original: '+str(fn['declared_line'])+'; objeto: '+str(fn['offset']))
                self.put('Method '+fn['symbol']+'('+self.parameters(fn)+') Class '+name,n=fn)
                start=len(self.lines)
                self.statement(fn['body'],1)
                self.functions.append({'name':fn['symbol'],'kind':'Method','class':cls['name'],
                                       'original_line':fn['declared_line'],'serialized_offset':fn['offset'],
                                       'generated_start_line':start,'generated_end_line':len(self.lines)})
