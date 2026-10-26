"""Recorded random-byte ownership, exact consumption and Python/C production paths."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from ruyijs import Context, JSError
from iframe_client import CClient

URL = 'https://crypto.test/'


class CryptoCases:
    def setUp(self):
        self.c = self.client()
        self.addCleanup(self.c.close)

    def configure(self, documents):
        if isinstance(self.c, Context): return self.c.configure_crypto_replay(documents)
        return self.c.call('configure_crypto_replay', documents=documents)

    def status(self):
        if isinstance(self.c, Context): return self.c.crypto_replay_status()
        return self.c.call('crypto_replay_status')

    def test_subarray_identity_and_hidden_state(self):
        self.configure([{'url':URL,'values':['01020304','']}])
        self.c.load_page(URL,'<!doctype html>')
        self.assertEqual(self.c.eval('''(() => {
          const all=new Uint8Array(8).fill(9), part=all.subarray(2,6);
          const same=crypto.getRandomValues(part)===part;
          const empty=new Uint8Array(0);crypto.getRandomValues(empty);
          const d=Object.getOwnPropertyDescriptor(Crypto.prototype,'getRandomValues');
          return [Array.from(all),same,Reflect.ownKeys(crypto).map(String),
            d.writable,d.enumerable,d.configurable,d.value.length,
            d.value.toString().includes('[native code]'),typeof configure_crypto_replay];
        })()'''), [[9,9,1,2,3,4,9,9],True,[],True,True,True,1,True,'undefined'])
        self.assertEqual(self.status(),[{'url':URL,'expected':2,'used':2,'mismatches':0,'bound':True}])
        self.assertIs(self.status()[0]['bound'],True)

    def test_mismatch_is_atomic_and_validation_precedes_consumption(self):
        self.configure([{'url':URL,'values':['0102']}])
        self.c.load_page(URL,'')
        result=self.c.eval('''(() => {
          const failures=[];
          for(const f of [()=>crypto.getRandomValues(new Uint8Array(3)),
            ()=>crypto.randomUUID(),()=>crypto.getRandomValues(new Float32Array(1)),
            ()=>crypto.getRandomValues(new Uint8Array(65537)),
            ()=>Crypto.prototype.getRandomValues.call({},new Uint8Array(2))]) {
            try{f();failures.push('accepted')}catch(e){failures.push(e.name)}
          }
          const a=new Uint8Array(2);crypto.getRandomValues(a);
          const untouched=new Uint8Array(2).fill(7);
          try{crypto.getRandomValues(untouched)}catch(e){failures.push(e.name)}
          return [failures,Array.from(a),Array.from(untouched)];
        })()''')
        self.assertEqual(result,[['OperationError','OperationError','TypeMismatchError',
            'QuotaExceededError','TypeError','OperationError'],[1,2],[7,7]])
        self.assertEqual(self.status()[0]['used'],1)
        self.assertEqual(self.status()[0]['mismatches'],3)

    def test_invalid_configuration_is_atomic_and_freezes(self):
        self.configure([{'url':URL,'values':['0102']}])
        for documents in [None,[{'url':URL,'values':['x0']}],[{'url':URL,'values':['123']}],
                          [{'url':URL,'values':[12]}],[{'url':'relative','values':[]}]]:
            with self.subTest(documents=documents), self.assertRaises(JSError): self.configure(documents)
        self.c.load_page(URL,'<script>window.bytes=Array.from(crypto.getRandomValues(new Uint8Array(2)))</script>')
        self.assertEqual(self.c.eval('bytes'),[1,2])
        with self.assertRaises(JSError): self.configure([])

    def test_frame_owner_and_borrowed_method_survive_gc(self):
        self.configure([{'url':URL,'values':['01']},{'url':URL+'frame','values':['02']},
                        {'url':'https://other.test/frame','values':['03']}])
        self.c.put_resource(URL+'frame','<!doctype html>')
        self.c.put_resource('https://other.test/frame','<script>window.saved=Array.from(crypto.getRandomValues(new Uint8Array(1)))</script>')
        self.c.load_page(URL,'<iframe src="frame"></iframe><iframe src="https://other.test/frame"></iframe>')
        if isinstance(self.c,Context): self.c.collect_garbage()
        else:self.c.call('collect')
        result=self.c.eval('''(() => {
          const w=document.querySelector('iframe').contentWindow;
          const p=crypto.getRandomValues(new Uint8Array(1));
          const c=new w.Uint8Array(1);Crypto.prototype.getRandomValues.call(w.crypto,c);
          return [p[0],c[0],w.crypto!==crypto,w.crypto.getRandomValues!==crypto.getRandomValues];
        })()''')
        self.assertEqual(result,[1,2,True,True])
        self.assertEqual([r['used'] for r in self.status()],[1,1,1])

    def test_occurrences_are_finite_and_unknown_documents_keep_os_source(self):
        self.configure([{'url':URL,'values':['01']},{'url':URL,'values':['02']}])
        for byte in [1,2]:
            self.c.load_page(URL,'')
            self.assertEqual(self.c.eval('crypto.getRandomValues(new Uint8Array(1))[0]'),byte)
        with self.assertRaises(JSError):self.c.load_page(URL,'')
        self.c.load_page('https://unplanned.test/','')
        self.assertEqual(self.c.eval('crypto.getRandomValues(new Uint8Array(5)).length'),5)
        self.assertEqual([r['used'] for r in self.status()],[1,1])

    def test_integer_views_are_matched_by_bytes(self):
        names=['Int8Array','Uint8Array','Uint8ClampedArray','Int16Array','Uint16Array',
               'Int32Array','Uint32Array','BigInt64Array','BigUint64Array']
        self.configure([{'url':URL,'values':['0102030405060708']*len(names)}])
        self.c.load_page(URL,'')
        for name in names:
            self.assertEqual(self.c.eval("(()=>{const v=new "+name+"(new ArrayBuffer(8));crypto.getRandomValues(v);return Array.from(new Uint8Array(v.buffer))})()"),list(range(1,9)))

    def test_uuid_and_byte_calls_preserve_order(self):
        uuid='00112233-4455-4677-8899-aabbccddeeff'
        self.configure([{'url':URL,'values':['01',{'method':'randomUUID','value':uuid},'02']}])
        self.c.load_page(URL,'')
        with self.assertRaises(JSError):self.c.eval('crypto.randomUUID()')
        self.assertEqual(self.c.eval('crypto.getRandomValues(new Uint8Array(1))[0]'),1)
        with self.assertRaises(JSError):self.c.eval('crypto.getRandomValues(new Uint8Array(16))')
        self.assertEqual(self.c.eval('crypto.randomUUID()'),uuid)
        self.assertEqual(self.c.eval('crypto.getRandomValues(new Uint8Array(1))[0]'),2)
        self.assertEqual(self.status()[0]['used'],3)
        self.assertEqual(self.status()[0]['mismatches'],2)

    def test_invalid_uuid_configuration_does_not_replace_previous_plan(self):
        self.configure([{'url':URL,'values':['01']}])
        for value in ['00112233-4455-1677-8899-aabbccddeeff','00112233-4455-4677-0099-aabbccddeeff','x'*36]:
            with self.assertRaises(JSError):
                self.configure([{'url':URL,'values':[{'method':'randomUUID','value':value}]}])
        self.c.load_page(URL,'')
        self.assertEqual(self.c.eval('crypto.getRandomValues(new Uint8Array(1))[0]'),1)

    def test_receiver_identity_survives_shadowed_global_and_borrowed_error(self):
        self.configure([{'url':URL,'values':['0102']},{'url':URL+'child','values':['03']}])
        self.c.put_resource(URL+'child','')
        self.c.load_page(URL,'<iframe src="child"></iframe>')
        result=self.c.eval('''(() => {
          const original=crypto, w=document.querySelector('iframe').contentWindow;
          Object.defineProperty(window,'crypto',{value:{},configurable:true});
          let error;
          try {w.crypto.getRandomValues.call(original,new Uint8Array(1))}
          catch(e){error=[e.name,e instanceof w.DOMException,e instanceof DOMException]}
          const v=new Uint8Array(2);original.getRandomValues(v);
          return [error,Array.from(v)];
        })()''')
        self.assertEqual(result,[['OperationError',True,False],[1,2]])

    def test_query_and_navigated_document_match_exactly(self):
        target=URL+'?recorded=1'
        self.configure([{'url':target,'values':['03']}])
        self.c.put_resource(target,'<script>window.result=crypto.getRandomValues(new Uint8Array(1))[0]</script>')
        self.c.load_page(URL,'')
        self.assertIs(self.status()[0]['bound'],False)
        self.c.eval('location.href='+repr(target)+';undefined')
        self.c.advance(50)
        self.assertEqual(self.c.eval('result'),3)
        self.assertIs(self.status()[0]['bound'],True)

    def test_contexts_do_not_share_consumption(self):
        self.configure([{'url':URL,'values':['01']}])
        self.c.load_page(URL,'')
        self.assertEqual(self.c.eval('crypto.getRandomValues(new Uint8Array(1))[0]'),1)
        with Context(shell=ROOT/'dist/js.exe') as other:
            other.configure_crypto_replay([{'url':URL,'values':['02']}])
            other.load_page(URL,'')
            self.assertEqual(other.eval('crypto.getRandomValues(new Uint8Array(1))[0]'),2)
            self.assertEqual(other.crypto_replay_status()[0]['used'],1)
        self.assertEqual(self.status()[0]['used'],1)

    def test_detached_zero_view_and_unknown_fields(self):
        self.configure([{'url':URL,'values':['','0102']}])
        with self.assertRaises(JSError):self.configure([{'url':URL,'values':['01'],'unknown':True}])
        self.c.load_page(URL,'')
        self.assertEqual(self.c.eval('''(() => {
          const buffer=new ArrayBuffer(2),view=new Uint8Array(buffer);
          structuredClone(buffer,{transfer:[buffer]});
          const same=crypto.getRandomValues(view)===view;
          return [same,view.byteLength,Array.from(crypto.getRandomValues(new Uint8Array(2)))];
        })()'''),[True,0,[1,2]])


class PythonCrypto(CryptoCases,unittest.TestCase):
    client=staticmethod(lambda:Context(shell=ROOT/'dist/js.exe'))


class CCrypto(CryptoCases,unittest.TestCase):
    client=staticmethod(CClient)


if __name__=='__main__':unittest.main()
