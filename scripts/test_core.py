"""Synthetic regression checks; no proprietary fixtures or external services."""
import unittest
import warnings
import struct
from pathlib import Path
import re
from advpl_emitter import Emitter, EmissionError, quote
from object_reader import Reader, Unsupported
from checks import lexical
from tlpp_reader import Reader as TLPPReader
from tlpp_emitter import Emitter as TLPPEmitter


def node(tag, **fields): return dict(tag=tag,offset=0,source_line=1,**fields)


class CoreChecks(unittest.TestCase):
    def test_tlpp_bodyless_method_wire_layout(self):
        prefix = bytes([68])+b'U\0F'+struct.pack('<iII',0,0,0)
        payload = prefix+struct.pack('<IIi',len(prefix)+8,4,0)+b'FEXTERNAL\0'+struct.pack('<I',0)+b'F\0'
        reader = TLPPReader(payload)
        method = reader.node()
        self.assertEqual(reader.at,len(payload))
        self.assertEqual(method['tag'],68)
        self.assertFalse(method['has_body'])
        self.assertIsNone(method['body'])
        self.assertEqual(method['body_bytes'],0)
        self.assertEqual(method['symbol'],'EXTERNAL')

    def test_tlpp_field_and_unknown_annotations(self):
        payload = bytes([8])+b'FIELD\0OFObject\0F'
        field = TLPPReader(payload).class_data()
        self.assertEqual((field['flags'],field['type'],field['declared_type']),(8,'O','Object'))
        with self.assertRaises(Unsupported): TLPPReader(payload[:-1]+b'A').class_data()
        with self.assertRaises(Unsupported): TLPPReader(b'\xff').small_count()

    def test_tlpp_super_dispatch(self):
        call = node(64,method_flag=True,call_flag=False,receiver=node(31,name='SELF'),
                    function_name=node(27,name='NEW'),arguments=node(93,children=[]))
        self.assertEqual(TLPPEmitter().expr(call),'Super:NEW()')
        call['receiver']=node(31,name='OTHER')
        with self.assertRaises(EmissionError): TLPPEmitter().expr(call)

    def test_tlpp_bodyless_reference_is_metadata(self):
        method = node(68,has_body=False,method_flags=0,inherited_call=None,symbol='EXTERNAL',
                      body_bytes=0,declared_line=0)
        root = node(117,children=[],functions=[],optional_80=None,source_name='TEST',
                    program_source='SAMPLE.TLPP',static_definitions=node(2,children=[]),
                    classes=[{'name':'TEST.SAMPLE','base_class':'BASE','implements':[],
                              'data':[],'methods':[method]}])
        emitter = TLPPEmitter();emitter.program(root)
        self.assertEqual(len(emitter.references),1)
        self.assertEqual(emitter.references[0]['name'],'EXTERNAL')
        self.assertFalse(any('Method EXTERNAL(' in line for line in emitter.lines))

    def test_portuguese_document_encoding(self):
        root=Path(__file__).resolve().parent.parent
        for path in root.rglob('*'):
            if '.git' not in path.parts and '__pycache__' not in path.parts and path.suffix in ('.md','.py','.yaml','.json'):
                path.read_bytes().decode('utf-8')
        for filename in ('README.md','SKILL.md'):
            text=(root/filename).read_bytes().decode('utf-8')
            self.assertNotIn('\ufffd',text)
            self.assertIsNone(re.search(r'\w\?\w|\?{2,}',text),filename)
            self.assertIn('usu\u00e1rio',text)

    def test_invalid_fields_stop(self):
        for value in (b'\x79\x01',b'\x01',b'\x48X'):
            with self.assertRaises(Unsupported): Reader(value).node()

    def test_unknown_semantics_and_invalid_pool_stop(self):
        for value in (node(999),node(121,constant_index=99)):
            with self.assertRaises(EmissionError): Emitter().expr(value)

    def test_byte_literals_roundtrip(self):
        value = bytes(range(1,256)).decode('latin1')
        expression = quote(value)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',SyntaxWarning)
            self.assertEqual(eval(expression,{'__builtins__':{},'Chr':chr}),value)
        self.assertTrue(expression.isascii())

    def test_comparison_and_chain(self):
        x,y,seven = node(31,name='X'),node(31,name='Y'),node(25,kind='N',value=7)
        emitter = Emitter()
        self.assertEqual(emitter.expr(node(34,left=x,right=seven,comparison='\x05')),'(X >= 7)')
        chain = node(37,children=[node(36,left=x,right=None),node(36,left=y,right=None)],value=seven)
        self.assertEqual(emitter.expr(chain),'(X := (Y := 7))')

    def test_macro_call(self):
        call = node(48,function_name=node(54,value=node(31,name='CFUNC')),arguments=node(93,children=[]))
        self.assertEqual(Emitter().expr(call),'&CFUNC.()')

    def test_error_handler(self):
        block = node(69,parameters=[{'name':'OERROR'}],constants=[],
                     body=node(73,value=node(61,operand=node(31,name='OERROR'))))
        self.assertEqual(Emitter().expr(block),'{|OERROR| Break(@OERROR)}')

    def test_lexical_scope(self):
        emitter = Emitter()
        emitter.pool = [node(25,kind='C',value='outer')]
        block = node(69,parameters=[],constants=[],body=node(121,constant_index=0))
        self.assertEqual(emitter.expr(block),'{|| "outer"}')

    def test_lexical_failures(self):
        lexical('If .T.\n A("[()]")\nEndIf\n')
        for value in ('A(]', 'If .T.\nEndDo', 'A("text)', 'For I := 1 To 2'):
            with self.assertRaises(ValueError): lexical(value)


if __name__ == '__main__': unittest.main(verbosity=2)
