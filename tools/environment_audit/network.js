(async window => {
  const out={};
  const response=await fetch('/echo',{method:'POST',headers:{'content-type':'text/plain'},body:'hello'});
  out.fetch={status:response.status,ok:response.ok,type:response.type,body:await response.json(),used:response.bodyUsed};
  const headers=new Headers([['X-B','2'],['x-a','1']]);headers.append('X-A','3');
  out.headers={entries:Array.from(headers),has:headers.has('X-A'),get:headers.get('x-a')};
  const data=new Response('αβ');const copy=data.clone();out.clone=[await data.text(),await copy.text(),data.bodyUsed,copy.bodyUsed];
  const stream=new ReadableStream({start(c){c.enqueue(new Uint8Array([65,66]));c.close()}});
  out.stream=await new Response(stream).text();
  const body=new Blob(['a','中'],{type:'text/plain'});out.blob=[body.size,body.type,await body.text()];
  out.xhr=await new Promise(resolve=>{
    const x=new XMLHttpRequest(),events=[];x.onreadystatechange=()=>events.push('r'+x.readyState);
    x.onload=()=>events.push('load');x.onloadend=()=>resolve({status:x.status,text:x.responseText,events,header:x.getResponseHeader('X-Audit-Visible')});
    x.open('POST','/echo');x.setRequestHeader('Content-Type','text/plain');x.send('xhr');
  });
  const target='http://127.0.0.1:'+location.port+'/cors';
  for(const mode of ['cors','no-cors']){
    try{const r=await fetch(target,{mode,credentials:'omit'});out[mode]={status:r.status,type:r.type,ok:r.ok,
      visible:r.headers.get('x-audit-visible'),hidden:r.headers.get('x-audit-hidden'),body:await r.text()};}
    catch(e){out[mode]={error:e.name,message:e.message}}
  }
  const controller=new AbortController();controller.abort('audit-abort');
  try{await fetch('/echo',{signal:controller.signal});out.abort='resolved';}catch(e){out.abort=e==='audit-abort'?'same reason':String(e)}
  await new Promise(resolve=>setTimeout(resolve,50));
  const entries=performance.getEntriesByType('resource').filter(e=>e.name.includes('/echo'));
  out.timing=entries.map(e=>({type:e.initiatorType,start: e.startTime>=0,request:e.requestStart>0,response:e.responseStart>=e.requestStart,
    end:e.responseEnd>=e.responseStart,bytes:e.decodedBodySize>0,prototype:e instanceof PerformanceResourceTiming}));
  return out;
})
