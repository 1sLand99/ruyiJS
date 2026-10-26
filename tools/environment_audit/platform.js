(async window => {
  const out={},run=(name,fn)=>{try{out[name]=fn()}catch(e){out[name]={error:e.name,message:e.message}}};
  run('navigator',()=>Object.fromEntries(['userAgent','platform','language','languages','hardwareConcurrency','maxTouchPoints','webdriver','oscpu','deviceMemory','cookieEnabled'].map(k=>[k,navigator[k]??null])));
  run('screen',()=>Object.fromEntries(['width','height','availWidth','availHeight','colorDepth','pixelDepth'].map(k=>[k,screen[k]])));
  run('viewport',()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,visual:visualViewport&&[visualViewport.width,visualViewport.height,visualViewport.scale]}));
  run('intl',()=>({options:new Intl.DateTimeFormat().resolvedOptions(),date:new Date(1700000000000).toString(),
    number:new Intl.NumberFormat('en-US').format(1234.5),locale:Intl.getCanonicalLocales('en-us')}));
  run('plugins',()=>({tag:Object.prototype.toString.call(navigator.plugins),items:Array.from(navigator.plugins,p=>[p.name,p.filename,p.length]),mimes:Array.from(navigator.mimeTypes,m=>m.type)}));
  run('url',()=>{const u=new URL('../x?q=1#h','https://example.test/a/b');u.searchParams.append('a','hello world');return[u.href,u.origin,u.pathname,u.search,u.hash]});
  run('encoding',()=>{const input='中文😀';const bytes=new TextEncoder().encode(input);return[Array.from(bytes),new TextDecoder().decode(bytes),btoa('test'),atob('dGVzdA==')]});
  run('storage',()=>{localStorage.setItem('audit','hello');sessionStorage.setItem('audit','world');const v=[localStorage.getItem('audit'),sessionStorage.getItem('audit')];localStorage.removeItem('audit');sessionStorage.removeItem('audit');return v});
  run('cookies',()=>{document.cookie='audit=one; Path=/';const exists=document.cookie.split('; ').includes('audit=one');document.cookie='audit=; Max-Age=0; Path=/';return[exists,!document.cookie.includes('audit=one')]});
  run('cryptoViews',()=>{const bytes=new Uint8Array(6);bytes.fill(100);crypto.getRandomValues(bytes.subarray(1,5));let name;try{crypto.getRandomValues(new Float32Array(1))}catch(e){name=e.name}return[bytes[0],bytes[5],name]});
  if(isSecureContext){
    const bytes=new TextEncoder().encode('abc');const digest=await crypto.subtle.digest('SHA-256',bytes);
    out.digest=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
  } else out.digest='not exposed in insecure context';
  out.media={};for(const type of ['','video/mp4','video/webm; codecs="vp9"','audio/mpeg','bad/type']) {
    out.media[type]={canPlay:document.createElement('video').canPlayType(type),source:typeof MediaSource==='function'?MediaSource.isTypeSupported(type):null};
  }
  out.permissions={};for(const name of ['geolocation','notifications','camera','microphone']){
    try{const p=await navigator.permissions.query({name});out.permissions[name]={state:p.state,tag:Object.prototype.toString.call(p)};}
    catch(e){out.permissions[name]={error:e.name};}
  }
  run('speech',()=>({available:typeof speechSynthesis==='object',voices:typeof speechSynthesis==='object'?speechSynthesis.getVoices().map(v=>[v.name,v.lang,v.default]):[]}));
  return out;
})
