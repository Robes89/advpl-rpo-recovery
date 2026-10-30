"""Synthetic regression checks; no proprietary fixtures or external services."""
import unittest
import warnings
import struct
import zlib
from pathlib import Path
from types import SimpleNamespace
import re
import json
import tempfile
from advpl_emitter import Emitter, EmissionError, quote
from object_reader import Reader, Unsupported
from checks import lexical
from tlpp_reader import Reader as TLPPReader
from tlpp_emitter import Emitter as TLPPEmitter
from align_lines import align
from index_reader import FormatError, PROFILES
import ptm
import rpo


def node(tag, **fields): return dict(tag=tag,offset=0,source_line=1,**fields)


def run_align(source, smap):
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        reconstructed = folder/'TESTE.reconstruido.prw'
        reconstructed.write_text('\n'.join(source)+'\n',encoding='utf-8-sig')
        report = {'source':reconstructed.name,
                  'source_map':[{'generated_line':g,'original_line':o} for g,o in smap.items()]}
        (folder/'decompilation.json').write_text(json.dumps(report),encoding='utf-8')
        result = align(folder)
        assert (folder/'alignment.json').exists()
        assert reconstructed.read_text(encoding='utf-8-sig').splitlines() == source
        return result, (folder/'TESTE.alinhado.prw').read_text(encoding='utf-8-sig').splitlines()


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

    def test_tlpp_json_literal(self):
        tag = b'\x6a'+struct.pack('<i',4009)
        pair = lambda value,key: tag+b'F'+value+b'F'+key+b'\0'
        rest = bytes([2])+struct.pack('<H',1)+pair(b'\x1fUY\0',b'B')+b'F'
        head = tag+b'T\x73'+b'\x1fUX\0'+b'T'+rest+b'A\0'
        reader = TLPPReader(head)
        literal = reader.node()
        self.assertEqual(reader.at,len(head))
        self.assertEqual(TLPPEmitter().expr(literal),'{"A": X, "B": Y}')
        with self.assertRaises(Unsupported): TLPPReader(head.replace(b'T\x73',b'T\x00',1)).node()
        with self.assertRaises(EmissionError): TLPPEmitter().expr(TLPPReader(pair(b'\x1fUY\0',b'B')).node())

    def test_tlpp_class_annotation_and_scopes(self):
        payload = b'T.S\0BASE\0'+struct.pack('<HH',0,0)+bytes([0,1])+b'NOTE\0\x02on\0\x19LTname\0\x19Cx\xe1\0'
        reader = TLPPReader(payload)
        cls = reader.class_interface()
        self.assertEqual(reader.at,len(payload))
        method = node(68,has_body=True,method_flags=4,inherited_call=None,symbol='M',parameters=[],
                      body=node(2,children=[]),body_bytes=0,declared_line=5,function_flag='N')
        cls.update(data=[{'flags':4,'name':'NX','type':'N','declared_type':'NUMERIC','initializer':None}],methods=[method])
        root = node(117,children=[],functions=[],optional_80=None,source_name='T',program_source='S.TLPP',
                    static_definitions=node(2,children=[]),classes=[cls])
        emitter = TLPPEmitter();emitter.program(root)
        for line in ('@NOTE(on=.T., name="x\xe1")','    Protected Data NX As Numeric',
                     '    Protected Method M() As Numeric','Method M() As Numeric Class S'):
            self.assertIn(line,emitter.lines)
        method['method_flags'] = 2
        with self.assertRaises(EmissionError): TLPPEmitter().program(root)
        method['method_flags'] = 4
        cls['annotations'][0]['items'][1][1]['value'] = 'a\nb'
        with self.assertRaises(EmissionError): TLPPEmitter().program(root)

    def test_source_name_filter(self):
        args = SimpleNamespace(source='A.B-C D.TLPP',index_dir=Path('indice-inexistente'))
        with self.assertRaises(FileNotFoundError): rpo.reconstruct(args)
        for name in ('..\\A.PRW','A/B.PRW','A..B.PRW','.A.PRW','A.TXT'):
            args.source = name
            with self.assertRaises(FormatError): rpo.reconstruct(args)

    def test_descriptor_profiles(self):
        self.assertEqual(PROFILES[('APNSRM0421','24.3.0.0_ts03')],39)
        self.assertEqual(PROFILES[('APNSRM0419','24.3.0.11')],38)
        self.assertEqual(PROFILES[('APNSRM0419','24.3.1.5')],38)
        self.assertNotIn(('APNSRM0419','20.3.2.11'),PROFILES)

    def test_ptm_patchinfo_layout(self):
        raw,stamp = b'PAYLOAD',struct.pack('<d',45000.0)
        stored = zlib.compress(raw)
        def patchinfo(gap):
            record = struct.pack('<I',0)+b'A.PRW\0'+gap+b'A.PRW\0'+stamp+\
                     struct.pack('<7I',0,0,0,1,len(raw),len(stored),len(stored))+stored
            return b'R.RPO\0'+stamp+b'HOST\0'+struct.pack('<II',1,2)+b'APNSRM0419\0'+stamp+b'\0'+\
                   struct.pack('<I',1)+b'A.PRW\0'+struct.pack('<I',1)+record+b'\0\0'
        header,records,left = ptm.parse_patchinfo(patchinfo(bytes(9)))
        self.assertEqual((header['format_build'],left),('APNSRM0419',2))
        self.assertEqual((records[0]['name'],records[0]['serialized']),('A.PRW',raw))
        with self.assertRaises(FormatError): ptm.parse_patchinfo(patchinfo(b'\x01'+bytes(8)))

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

    def test_typed_declaration(self):
        payload = bytes([106])+struct.pack('<i',500)+b'CCNOME\0'+struct.pack('<i',0)
        reader = Reader(payload)
        typed = reader.node()
        self.assertEqual(reader.at,len(payload))
        self.assertEqual((typed['tag'],typed['var_type'],typed['name'],typed['field_typed']),(500,'C','CNOME',0))
        self.assertEqual(Emitter().expr(typed),'CNOME As Character')
        self.assertEqual(Emitter().expr(node(500,var_type='B',name='BBLOCO',field_typed=0)),'BBLOCO As Block')
        self.assertEqual(Emitter().expr(node(500,var_type='U',name='CJSON',field_typed=0)),'CJSON')
        for value in (node(500,var_type='X',name='C',field_typed=0),node(500,var_type='C',name='C',field_typed=1)):
            with self.assertRaises(EmissionError): Emitter().expr(value)

    def test_field_without_alias(self):
        field = node(27,name='B3_FILIAL')
        self.assertEqual(Emitter().expr(node(62,left=None,right=field)),'_FIELD->B3_FILIAL')
        self.assertEqual(Emitter().expr(node(63,left=None,right=node(31,name='CMES'))),'_FIELD->(CMES)')
        self.assertEqual(Emitter().expr(node(62,left=node(27,name='SB3'),right=field)),'SB3->B3_FILIAL')

    def test_align_original_lines(self):
        source = ['','// Linha original: 10; objeto: 100','Static Function B()','    Local A','    Local B',
                  '    If X','        Y()','    EndIf','    Return','','// Linha original: 2; objeto: 50',
                  'User Function A()','    Return .T.']
        result, aligned = run_align(source,{4:11,5:11,6:12,7:12,9:13,13:3})
        self.assertEqual(aligned,['','User Function A()','    Return .T.']+['']*6+
                         ['Static Function B()','    Local A, B','    IIf(X, Y(), Nil)','    Return'])
        self.assertEqual((result['exact_ratio'],result['displaced']),(1.0,0))
        self.assertEqual(result['folds'],{'declaracoes na mesma linha':1,'IIf':1})

    def test_align_jump_on_one_line(self):
        source = ['','// Linha original: 1; objeto: 10','User Function A()','    While .T.','        If X',
                  '            Exit','        EndIf','    EndDo','    Return']
        result, aligned = run_align(source,{4:2,5:3,6:3,8:4,9:5})
        self.assertEqual(aligned,['User Function A()','    While .T.','        If X; Exit; EndIf','    EndDo','    Return'])
        self.assertEqual((result['exact_ratio'],result['folds']),(1.0,{'If numa linha':1}))

    def test_tlpp_typed_declaration_trailer(self):
        def typed(kind, name, code, trailer, flag=b'T'):
            return bytes([106])+struct.pack('<i',500)+kind+name+b'\0'+struct.pack('<i',code)+trailer+flag
        payload = typed(b'L',b'LOK',6,b'\x05'+bytes(7))
        reader = Reader(payload)
        declaration = reader.node()
        self.assertEqual(reader.at,len(payload))
        self.assertEqual((declaration['field_typed'],declaration['typed_trailer']),(6,'05'+'00'*7))
        self.assertEqual(Emitter().expr(declaration),'LOK As Logical')
        self.assertEqual(Emitter().expr(Reader(typed(b'I',b'NQTD',25,bytes(8))).node()),'NQTD As Integer')
        for value in (typed(b'L',b'LOK',6,bytes(8)),typed(b'C',b'CNOME',99,bytes(8)),typed(b'C',b'CNOME',1,bytes(8),b'F')):
            with self.assertRaises(Unsupported): Reader(value).node()

    def test_try_catch_finally(self):
        def name(text): return bytes([27])+text+b'\0'
        catch = bytes([102])+b'T'+name(b'OERR')+name(b'B')
        payload = bytes([101])+struct.pack('<H',1)+name(b'A')+b'F'+b'T'+catch+b'T'+name(b'C')
        reader = Reader(payload)
        block = reader.node()
        self.assertEqual(reader.at,len(payload))
        emitter = Emitter();emitter.statement(block,1)
        self.assertEqual(emitter.lines,['    Try','        A','    Catch OERR','        B','    Finally','        C','    EndTry'])
        lexical('\n'.join(emitter.lines))
        with self.assertRaises(Unsupported): Reader(payload.replace(bytes([102]),bytes([27])+b'X\0',1)).node()

    def test_tlpp_function_only_program(self):
        fn = node(67,function_type='F',symbol='TESTE',name='TESTE',declared_line=1,constants=[],
                  parameters=[{'name':'CNOME','type':'C'},{'name':'XVALOR','type':'U'}],body=node(0))
        root = node(117,children=[],functions=[fn],classes=[],optional_80=None,source_name='',
                    program_source='SAMPLE.TLPP',static_definitions=node(2,children=[]))
        emitter = TLPPEmitter();emitter.program(root)
        self.assertIn('Function TESTE(CNOME As Character, XVALOR)',emitter.lines)
        root['source_name'] = 'TEST'
        with self.assertRaises(EmissionError): TLPPEmitter().program(root)

    def test_lexical_failures(self):
        lexical('If .T.\n A("[()]")\nEndIf\n')
        lexical('Try\n If X; Exit; EndIf\nEndTry\n')
        for value in ('A(]', 'If .T.\nEndDo', 'A("text)', 'For I := 1 To 2', 'Try\nEndIf'):
            with self.assertRaises(ValueError): lexical(value)


if __name__ == '__main__': unittest.main(verbosity=2)
