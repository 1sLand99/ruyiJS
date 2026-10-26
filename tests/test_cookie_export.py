"""Whole-jar host snapshots and HTTP Cookie selection through Python and C ABI."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context, JSError
from iframe_client import CClient

BASE = 'https://cookie.example.test'
EPOCH = 1700000000


class CookieCases:
    def setUp(self):
        self.c = self.client()
        self.addCleanup(self.c.close)
        self.c.configure_clock('logical', epoch_ms=EPOCH * 1000)
        self.c.load_page(BASE + '/', '')

    def export(self):
        if isinstance(self.c, Context):
            return self.c.export_cookies()
        return self.c.call('cookies', action='export')

    def header(self, url, **options):
        if isinstance(self.c, Context):
            return self.c.cookie_header(url, **options)
        fields = dict(source_url='', navigation=False, method='GET') | options
        return self.c.call('cookies', action='header', url=url, **fields)

    def seed(self, *cookies):
        self.c.put_resource(BASE + '/seed', '', headers=[['Set-Cookie', c] for c in cookies])
        self.c.eval("(()=>{const x=new XMLHttpRequest();x.open('GET','/seed',false);x.send()})()")

    def test_full_snapshot_includes_http_only_and_preserves_attributes(self):
        self.seed('sid=root; HttpOnly; Secure; Path=/; SameSite=Lax; Max-Age=600',
                  'sid=deep; HttpOnly; Secure; Path=/account; SameSite=Strict',
                  'shared=yes; Domain=example.test; Path=/; Secure; SameSite=None')
        self.c.eval("document.cookie='visible=ok; Path=/'")
        rows = self.export()
        self.assertEqual(len(rows), 4)
        root = next(c for c in rows if c['value'] == 'root')
        self.assertEqual(root, dict(name='sid', value='root', domain='cookie.example.test',
            path='/', sameSite='Lax', hostOnly=True, secure=True, httpOnly=True,
            session=False, expires=EPOCH + 600, created=EPOCH, order=1))
        shared = next(c for c in rows if c['name'] == 'shared')
        self.assertEqual((shared['domain'], shared['hostOnly'], shared['expires'],
                          shared['session'], shared['sameSite']), ('example.test', False, None, True, 'None'))
        self.assertEqual(self.c.eval('document.cookie'), 'shared=yes; visible=ok')
        rows[0]['value'] = 'changed in Python'
        self.assertEqual(self.export()[0]['value'], 'root')
        with Context(shell=ROOT / 'dist/js.exe') as other:
            self.assertEqual(other.export_cookies(), [])

    def test_header_uses_scope_and_preserves_duplicate_names(self):
        self.seed('sid=root; HttpOnly; Secure; Path=/', 'sid=deep; HttpOnly; Secure; Path=/account',
                  'shared=yes; Domain=example.test; Path=/', 'plain=ok; Path=/')
        self.assertEqual(self.header(BASE + '/account/info'), 'sid=deep; sid=root; shared=yes; plain=ok')
        self.assertEqual(self.header(BASE + '/accounting'), 'sid=root; shared=yes; plain=ok')
        self.assertEqual(self.header(BASE.replace('https:', 'http:') + '/'), 'shared=yes; plain=ok')
        self.assertEqual(self.header('https://sibling.example.test/'), 'shared=yes')
        self.assertEqual(self.header('https://unrelated.test/'), '')

    def test_expiry_deletion_and_empty_jar(self):
        self.assertEqual(self.export(), [])
        self.assertEqual(self.header(BASE), '')
        self.seed('short=1; Max-Age=1', 'dead=1; Max-Age=0', 'session=1')
        self.assertEqual([r['name'] for r in self.export()], ['short', 'session'])
        self.c.advance(1000)
        self.assertEqual([r['name'] for r in self.export()], ['session'])
        self.seed('session=; Max-Age=0')
        self.assertEqual(self.export(), [])

    def test_cross_origin_frame_and_top_level_navigation_share_jar(self):
        self.seed('first=1; HttpOnly; Secure')
        self.c.put_resource('https://frame.other.test/', '<p>frame</p>',
                            headers=[['Set-Cookie', 'frame=2; HttpOnly; Secure; SameSite=None']])
        self.c.eval("document.body.innerHTML='<iframe src=\"https://frame.other.test/\"></iframe>'")
        for _ in range(10):
            if len(self.export()) == 2:
                break
            self.c.advance(0)
        self.assertEqual({r['domain'] for r in self.export()}, {'cookie.example.test', 'frame.other.test'})
        self.c.load_page('https://next.other.test/', '')
        self.c.eval("document.cookie='next=3; Path=/'")
        self.assertEqual(len(self.export()), 3)
        self.assertEqual(self.header(BASE + '/'), 'first=1')
        self.assertEqual(self.header('https://frame.other.test/'), 'frame=2')

    def test_same_site_request_context(self):
        self.seed('strict=1; SameSite=Strict; Secure', 'lax=2; SameSite=Lax; Secure',
                  'none=3; SameSite=None; Secure', 'default=4; Secure')
        cross = dict(source_url='https://other.test/')
        self.assertEqual(self.header(BASE, **cross), 'none=3')
        self.assertEqual(self.header(BASE, navigation=True, **cross), 'lax=2; none=3; default=4')
        self.assertEqual(self.header(BASE, navigation=True, method='post', **cross), 'none=3; default=4')
        self.c.advance(121000)
        self.assertEqual(self.header(BASE, navigation=True, method='POST', **cross), 'none=3')
        self.assertEqual(self.header(BASE, source_url=BASE), 'strict=1; lax=2; none=3; default=4')

    def test_host_interface_has_no_page_surface_and_ignores_page_getters(self):
        self.seed('secret=1; HttpOnly; Secure')
        probe = '''(() => [window,Document.prototype,CookieStore.prototype].map(o=>[
          Object.keys(o),Object.getOwnPropertyNames(o),Reflect.ownKeys(o).map(String),
          (()=>{const a=[];for(const k in o)a.push(k);return a})()]))()'''
        self.c.eval('''globalThis.savedCookieDescriptors = [
          Object.getOwnPropertyDescriptor(Document.prototype,'cookie'),
          Object.getOwnPropertyDescriptor(window,'cookieStore'),
          Object.getOwnPropertyDescriptors(CookieStore.prototype)]; void 0''')
        before = self.c.eval(probe)
        self.assertEqual(self.export()[0]['name'], 'secret')
        self.assertEqual(self.header(BASE), 'secret=1')
        self.assertEqual(self.c.eval(probe), before)
        self.assertTrue(self.c.eval('''(() => {
          const current=[Object.getOwnPropertyDescriptor(Document.prototype,'cookie'),
            Object.getOwnPropertyDescriptor(window,'cookieStore'),
            Object.getOwnPropertyDescriptors(CookieStore.prototype)];
          function equal(a,b) {return Reflect.ownKeys(a).every(k =>
            typeof a[k]==='object' && a[k]!==null ? equal(a[k],b[k]) : a[k]===b[k])}
          return current.every((d,i)=>equal(d,savedCookieDescriptors[i]));
        })()'''))
        self.c.eval("void Object.defineProperty(document,'cookie',{get(){throw Error('page getter')}})")
        self.assertEqual(self.export()[0]['value'], '1')
        self.assertEqual(self.header(BASE), 'secret=1')
        self.assertEqual(self.c.eval('[typeof export_cookies,typeof cookie_header]'), ['undefined', 'undefined'])

    def test_bytes_survive_export_and_header(self):
        self.seed('raw=\xff; HttpOnly')
        self.c.eval("document.cookie='text=中文; Path=/'")
        rows = self.export()
        self.assertEqual(rows[0]['value'].encode('latin-1'), b'\xff')
        self.assertEqual(rows[1]['value'].encode('latin-1'), '中文'.encode())
        self.assertEqual(self.header(BASE).encode('latin-1'), b'raw=\xff; text=' + '中文'.encode())
        self.assertEqual(json.loads(json.dumps(rows)), rows)

    def test_validation_and_closed_context(self):
        self.seed('keep=1')
        for url, options in [('/relative', {}), ('file:///x', {}), (BASE, {'source_url': '/bad'}),
                             (BASE, {'method': ''}), (BASE, {'method': 'GET\r\n'}),
                             (BASE, {'navigation': 'yes'})]:
            with self.subTest(url=url, options=options), self.assertRaises((TypeError, JSError)):
                self.header(url, **options)
        call = self.c._request if isinstance(self.c, Context) else self.c.call
        with self.assertRaises(JSError):
            call('cookies', action='export', url=BASE)
        self.assertEqual(self.header(BASE), 'keep=1')
        if isinstance(self.c, Context):
            self.c.close()
            with self.assertRaises(RuntimeError):
                self.c.export_cookies()


class PythonCookies(CookieCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class CCookies(CookieCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__':
    unittest.main()
