"""Inherited domain reads use the original receiver document in Python and C."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context
from iframe_client import CClient


class DomainCases:
    def setUp(self):
        self.context = self.client()
        self.addCleanup(self.context.close)
        self.context.load_page('https://parent.example.test/page', '<!doctype html><body></body>')

    def test_nested_blank_and_borrowed_accessor(self):
        self.assertEqual(self.context.eval('''(() => {
          const f=document.createElement('iframe');document.body.appendChild(f);
          const w=f.contentWindow, g=w.document.createElement('iframe');w.document.body.appendChild(g);
          const a=Object.getOwnPropertyDescriptor(Document.prototype,'domain').get;
          const b=Object.getOwnPropertyDescriptor(w.Document.prototype,'domain').get;
          return [document.domain,w.document.domain,g.contentDocument.domain,a.call(w.document),b.call(document),
            a!==b,w.document instanceof w.Document,!(w.document instanceof Document)];
        })()'''), ['parent.example.test'] * 5 + [True, True, True])

    def test_srcdoc_and_detached_documents(self):
        self.context.eval("const f=document.createElement('iframe');f.srcdoc='<p>x';document.body.appendChild(f);undefined")
        self.context.advance(20)
        self.assertEqual(self.context.eval('''[f.contentDocument.domain,
          document.implementation.createHTMLDocument('x').domain,new Document().domain,
          new DOMParser().parseFromString('<p>x','text/html').domain]'''), ['parent.example.test'] * 4)

    def test_navigation_updates_receiver_origin(self):
        self.context.put_resource('https://parent.example.test/child', '<p>child')
        self.context.eval("const f=document.createElement('iframe');document.body.appendChild(f);f.src='/child';undefined")
        self.context.advance(20)
        self.assertEqual(self.context.eval('[f.contentDocument.domain,document.domain]'), ['parent.example.test'] * 2)
        self.context.load_page('https://other.example.test/', '<iframe></iframe>')
        self.assertEqual(self.context.eval("[document.domain,document.querySelector('iframe').contentDocument.domain]"),
                         ['other.example.test'] * 2)

    def test_metadata_override_descriptor_and_invalid_receiver(self):
        self.assertEqual(self.context.eval('''(() => {
          const f=document.createElement('iframe');document.body.appendChild(f);
          const d=f.contentDocument, a=Object.getOwnPropertyDescriptor(Document.prototype,'domain');
          d.domain='example.test';let error;
          try{a.get.call({})}catch(e){error=e.name}
          return [d.domain,document.domain,error,a.get.length,a.set.length,a.enumerable,a.configurable,
            Object.hasOwn(d,'domain'),String(a.get).includes('[native code]')];
        })()'''), ['example.test','parent.example.test','TypeError',0,1,True,True,False,True])

    def test_document_survives_collection(self):
        self.context.eval("const f=document.createElement('iframe');document.body.appendChild(f);globalThis.d=f.contentDocument;undefined")
        if isinstance(self.context, Context):
            self.context.collect_garbage()
        else:
            self.context.call('collect')
        self.assertEqual(self.context.eval('d.domain'), 'parent.example.test')


class PythonDomain(DomainCases, unittest.TestCase):
    client = staticmethod(lambda: Context(shell=ROOT / 'dist/js.exe'))


class CDomain(DomainCases, unittest.TestCase):
    client = staticmethod(CClient)


if __name__ == '__main__':
    unittest.main()
