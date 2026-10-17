"""Synthetic regression checks; no proprietary fixtures or external services."""
import unittest
import warnings
from advpl_emitter import Emitter, EmissionError, quote
from object_reader import Reader, Unsupported
from checks import lexical


def node(tag, **fields): return dict(tag=tag,offset=0,source_line=1,**fields)


class CoreChecks(unittest.TestCase):
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
