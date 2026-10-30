"""Class/method wire layouts validated in the supplied TLPP build."""
import object_reader as base


class Reader(base.Reader):
    def small_count(self):
        count = self.i8()
        if count < 0: raise base.Unsupported(f'Negative class item count at {self.at-1}')
        return count

    def class_data(self):
        n = {'offset':self.at,'flags':self.byte(),'name':self.string(),'type':chr(self.byte())}
        n['initializer'] = self.node() if self.boolean() else None
        n['declared_type'] = self.string()
        marker = chr(self.byte())
        if marker != 'F':
            raise base.Unsupported(f'Unimplemented class-data annotations at {self.at-1}')
        n['end_offset'] = self.at
        return n

    def class_interface(self):
        n = {'offset':self.at,'name':self.string(),'base_class':self.string()}
        n['data'] = [self.class_data() for _ in range(self.u16())]
        n['methods'] = [self.node() for _ in range(self.u16())]
        n['implements'] = [self.string() for _ in range(self.small_count())]
        n['annotations'] = []
        for _ in range(self.small_count()):
            # Mesmo layout da anotacao de funcao: nome + pares (chave, constante).
            # Validado em BACKOFFICE.SV.FIN.BANKSTATEMENT.TLPP (30/10/2026).
            item = {'name':self.string()}
            item['items'] = [(self.string(),self.node()) for _ in range(self.small_count())]
            n['annotations'].append(item)
        n['end_offset'] = self.at
        return n

    def json_literal(self, n):
        # Literal JSON (tipo 4009, com escape 106). Primeiro par: objeto 115, valor, lista dos demais, chave.
        # Demais pares: sem objeto, valor, sem lista, chave. Layout deduzido do registro, nao dos leitores
        # nativos; fronteiras de corpo exatas em BACKOFFICE.SV.FIN.BANKSTATEMENT.TLPP (30/10/2026).
        n['json_object'] = self.node() if self.boolean() else None
        n['value'] = self.node()
        n['pairs'] = self.node() if self.boolean() else None
        n['key'] = self.string()
        head = n['json_object'] is not None
        if head != (n['pairs'] is not None) or (head and n['json_object']['tag'] != 115):
            raise base.Unsupported(f'Unexpected JSON literal layout at {n["offset"]}')
        if head and (n['pairs']['tag'] != 2 or 'stack_symbols' in n['pairs'] or
                     any(c['tag'] != 4009 or c['json_object'] is not None for c in n['pairs']['children'])):
            raise base.Unsupported(f'Unexpected JSON literal pairs at {n["offset"]}')

    def payload(self, n):
        if n['tag'] == 4009:
            self.json_literal(n)
        elif n['tag'] == 68:
            n['tag'] = 67
            try:
                super().payload(n)
            finally:
                n['tag'] = 68
            inherited = self.boolean()
            n['inherited_call'] = [self.node(),self.node()] if inherited else None
            n['method_flags'] = self.byte()
        elif n['tag'] in (104,117):
            self.list_payload(n)
            n['optional_80'] = self.node() if self.boolean() else None
            n['attribute_99'] = self.boolean()
            n['source_name'] = self.string()
            n['extra_names'] = [self.string() for _ in range(self.count(100000))]
            n['static_definitions'] = self.node()
            n['classes'] = [self.class_interface() for _ in range(self.u16())]
            n['functions'] = [self.node() for _ in range(self.u16())]
            length = self.i32()
            if length < 0: raise base.Unsupported('Negative source map length')
            n['source_line_map'] = self.take(max(0,length-1)).hex()
            n['program_source'] = self.string()
            n['call_names'] = [self.string() for _ in range(self.count(100000))]
        else:
            super().payload(n)
