"""Native RNG restoration, JIT continuity, realm isolation and Python/C parity."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context, JSError
from iframe_client import CClient

FIRST, SECOND = '123456789abcdef0', 'fedcba9876543210'


def expected(count):
    a, b, out = int(FIRST, 16), int(SECOND, 16), []
    for _ in range(count):
        v = (a ^ (a << 23)) & ((1 << 64) - 1)
        a, b = b, (v ^ b ^ (v >> 17) ^ (b >> 26)) & ((1 << 64) - 1)
        out.append(((a + b) & ((1 << 53) - 1)) / (1 << 53))
    return out


class RandomCases:
    def setUp(self):
        self.c = self.client()
        self.addCleanup(self.c.close)

    def configure(self, first=FIRST, second=SECOND):
        if isinstance(self.c, Context):
            return self.c.configure_random(first, second)
        return self.c.call('configure_random', state0=first, state1=second)

    def test_engine_sequence_survives_jit_warmup(self):
        self.assertTrue(self.configure())
        result = self.c.eval('''(() => {
          const values=[]; for(let i=0;i<12000;i++) values.push(Math.random()); return values;
        })()''')
        self.assertEqual(result, expected(12000))

    def test_validation_is_atomic_and_execution_freezes_configuration(self):
        self.configure()
        for a, b in [('0'*16, '0'*16), ('g'*16, SECOND), (FIRST, 12), ('1', SECOND), ('é'*16, SECOND),
                     ('f'*15+'\0', SECOND)]:
            with self.subTest(a=a, b=b), self.assertRaises(JSError):
                self.configure(a, b)
        self.assertEqual(self.c.eval('Math.random()'), expected(1)[0])
        with self.assertRaises(JSError):
            self.configure()
        self.assertEqual(self.c.eval('Math.random()'), expected(2)[1])

    def test_native_surface_and_page_load(self):
        self.configure()
        self.c.load_page('https://random.test/', '<script>window.first=Math.random()</script>')
        result = self.c.eval('''(() => {
          const d=Object.getOwnPropertyDescriptor(Math,'random');
          return [first,Math.random(),typeof configure_random,typeof setRNGState,
            d.writable,d.enumerable,d.configurable,d.value.length,
            Function.prototype.toString.call(Math.random).includes('[native code]')];
        })()''')
        self.assertEqual(result, expected(2) + ['undefined','undefined',True,False,True,0,True])

    def test_child_and_context_randomness_stay_independent(self):
        self.configure()
        self.c.load_page('https://random.test/', '<iframe></iframe>')
        result = self.c.eval('''(() => {
          const child=document.querySelector('iframe').contentWindow;
          child.eval('for(let i=0;i<5000;i++) Math.random()');
          return [Math.random(),Math.random(),child.Math.random !== Math.random];
        })()''')
        self.assertEqual(result, expected(2) + [True])
        with Context(shell=ROOT / 'dist/js.exe') as other:
            other.configure_random(FIRST, SECOND)
            self.assertEqual(other.eval('Math.random()'), expected(1)[0])


class PythonRandom(RandomCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class CRandom(RandomCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__':
    unittest.main()
