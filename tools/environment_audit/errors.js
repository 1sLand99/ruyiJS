(async window => {
  const rows={};
  function check(name,fn){try{const v=fn();if(v&&typeof v.then==='function')return v.then(()=>{rows[name]={returned:true}},e=>capture(name,e));rows[name]={returned:true,type:typeof v};}catch(e){capture(name,e)}}
  function capture(name,e){rows[name]={name:e.name,message:e.message,typeError:e instanceof TypeError,domException:e instanceof DOMException,code:e.code??null};}
  for(const [name,fn] of [
    ['Document.querySelector',()=>Document.prototype.querySelector.call({})],
    ['Element.getAttribute',()=>Element.prototype.getAttribute.call({},'id')],
    ['Node.appendChild',()=>Node.prototype.appendChild.call({},document.body)],
    ['Navigator.userAgent',()=>Object.getOwnPropertyDescriptor(Navigator.prototype,'userAgent').get.call({})],
    ['Screen.width',()=>Object.getOwnPropertyDescriptor(Screen.prototype,'width').get.call({})],
    ['EventTarget.addEventListener',()=>EventTarget.prototype.addEventListener.call({},'x',()=>{})],
    ['Canvas.getContext',()=>HTMLCanvasElement.prototype.getContext.call({},'2d')],
    ['Crypto.getRandomValues',()=>Crypto.prototype.getRandomValues.call({},new Uint8Array(1))],
    ['XHR.send',()=>new XMLHttpRequest().send()],
    ['postMessage.missing',()=>window.postMessage()],
    ['querySelector.invalid',()=>document.querySelector('[')],
    ['URL.invalid',()=>new URL('bad')],
    ['Headers.invalid',()=>new Headers({'bad name':'x'})],
    ['Request.invalid',()=>new Request(location.href,{method:'bad method'})],
    ['DOMException.construct',()=>{const e=new DOMException('test','InvalidStateError');return[e.name,e.message,e.code]}]
  ])check(name,fn);
  await check('Response.clone.used',async()=>{const r=new Response('x');await r.text();r.clone()});
  const f=document.createElement('iframe');document.body.appendChild(f);
  try{f.contentWindow.Document.prototype.querySelector.call({});}catch(e){rows.borrowedErrorRealm={parent:e instanceof TypeError,child:e instanceof f.contentWindow.TypeError,name:e.name}}
  f.remove();return rows;
})
