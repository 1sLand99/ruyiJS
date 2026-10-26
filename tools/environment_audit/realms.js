(async window => {
  const out={},doc=window.document,frame=doc.createElement('iframe');doc.body.appendChild(frame);
  const child=frame.contentWindow;
  out.identity={window:child.window===child,self:child.self===child,parent:child.parent===window,top:child.top===window.top,
    document:child.document===frame.contentDocument,view:child.document.defaultView===child,frame:child.frameElement===frame,
    array:child.Array!==Array,element:child.document.createElement('div') instanceof child.HTMLElement,
    wrongRealm:child.document.createElement('div') instanceof HTMLElement,domain:child.document.domain===doc.domain};
  const proto=Object.getOwnPropertyDescriptor(Document.prototype,'title');proto.set.call(child.document,'child title');
  out.borrowed={title:proto.get.call(child.document),mainTitle:document.title,childIdentity:child.document instanceof child.Document};
  const names=['Document','Element','HTMLElement','Node','HTMLCanvasElement','Navigator','Screen','Crypto','XMLHttpRequest','Event','EventTarget','Storage'];
  out.constructorRealms=Object.fromEntries(names.map(n=>[n,typeof child[n]===typeof window[n]&&child[n]!==window[n]]));
  const order=[];let sequence=0;
  const received=new Promise(resolve=>{
    const handler=event=>{if(event.data?.audit==='message'){order.push(['message',sequence,event.source===window,event.origin===location.origin,event.isTrusted]);removeEventListener('message',handler);resolve();}};
    addEventListener('message',handler);window.postMessage({audit:'message',nested:[1]},'*');sequence=1;order.push(['sync']);Promise.resolve().then(()=>order.push(['microtask']));
  });
  await received;out.messageOrder=order;
  out.clone=(()=>{const a={map:new Map([['x',1]]),bytes:new Uint8Array([1,2])};a.self=a;const b=structuredClone(a);return[b!==a,b.self===b,b.map instanceof Map,Array.from(b.bytes)]})();
  out.events=await new Promise(resolve=>{
    const channel=new MessageChannel();channel.port2.onmessage=e=>{resolve([e.data.value,e.ports.length,e.isTrusted]);channel.port1.close();channel.port2.close();};
    const data={value:1};channel.port1.postMessage(data);data.value=2;
  });
  const srcdoc=doc.createElement('iframe');srcdoc.srcdoc='<p id="srcdoc">x</p>';doc.body.appendChild(srcdoc);
  await new Promise(resolve=>setTimeout(resolve,100));
  out.srcdoc={domain:srcdoc.contentDocument.domain===doc.domain,base:srcdoc.contentDocument.baseURI===doc.baseURI,
    element:srcdoc.contentDocument.querySelector('#srcdoc')?.textContent||null};
  srcdoc.remove();frame.remove();return out;
})
