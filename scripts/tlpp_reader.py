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
        annotations = self.small_count()
        if annotations:
            raise base.Unsupported(f'Unimplemented class annotations at {self.at-1}')
        n['end_offset'] = self.at
        return n

    def payload(self, n):
        if n['tag'] == 68:
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
