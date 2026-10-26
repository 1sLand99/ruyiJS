(async window => {
  const source = __WORKER_SURFACE__;
  const code=`const capture=${source};onmessage=async function(event){
    const result={surface:capture(self),behavior:{}};
    result.behavior.navigator={platform:navigator.platform,language:navigator.language,languages:Array.from(navigator.languages),hardwareConcurrency:navigator.hardwareConcurrency};
    result.behavior.scope=[self===globalThis,typeof document,typeof window,typeof importScripts];
    const bytes=new TextEncoder().encode('abc');
    if(crypto.subtle)result.behavior.digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    result.behavior.clone=[event.data.value,event.data.bytes instanceof Uint8Array,Array.from(event.data.bytes)];
    try{const c=new OffscreenCanvas(4,4),x=c.getContext('2d');x.fillStyle='red';x.fillRect(0,0,4,4);result.behavior.canvas=Array.from(x.getImageData(0,0,1,1).data)}catch(e){result.behavior.canvas={error:e.name}}
    try{const r=await fetch(event.data.url);result.behavior.fetch={status:r.status,type:r.type,visible:r.headers.get('x-audit-visible'),hidden:r.headers.get('x-audit-hidden')}}catch(e){result.behavior.fetch={error:e.name}}
    try{const root=await navigator.storage.getDirectory();const f=await root.getFileHandle('audit.bin',{create:true});const h=await f.createSyncAccessHandle();h.write(new Uint8Array([1,2,3]));const out=new Uint8Array(3);h.read(out,{at:0});result.behavior.opfs=Array.from(out);h.close();await root.removeEntry('audit.bin')}catch(e){result.behavior.opfs={error:e.name}}
    postMessage(result);
  };`;
  const url=URL.createObjectURL(new Blob([code],{type:'text/javascript'}));
  const worker=new Worker(url);
  try{return await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(new Error('Worker deadline exceeded')),8000);
    worker.onmessage=e=>{clearTimeout(timeout);resolve(e.data)};worker.onerror=e=>{clearTimeout(timeout);reject(new Error(e.message))};
    const value={value:1,bytes:new Uint8Array([4,5]),url:'http://127.0.0.1:'+location.port+'/cors'};worker.postMessage(value);value.value=2;
  });}finally{worker.terminate();URL.revokeObjectURL(url);}
})
