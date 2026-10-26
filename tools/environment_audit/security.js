(async window => {
  const out={secure:isSecureContext,isolated:crossOriginIsolated};
  const frame=document.createElement('iframe');frame.src='http://127.0.0.1:'+location.port+'/frame';
  const loaded=new Promise(resolve=>{frame.onload=resolve;setTimeout(resolve,3000)});document.body.appendChild(frame);await loaded;
  const child=frame.contentWindow;out.cross={};
  for(const key of ['document','location','Array','name','postMessage','closed','length']){
    try{out.cross[key]={type:typeof child[key]};if(key==='location')out.cross[key].href=child.location.href;}
    catch(e){out.cross[key]={error:e.name};}
  }
  out.cross.identity=child===frame.contentWindow;
  frame.remove();
  try {
    const name='environment-audit-'+Math.random();const policy=trustedTypes.createPolicy(name,{createHTML:v=>v,createScript:v=>v,createScriptURL:v=>v});
    const html=policy.createHTML('<b>x</b>');out.trustedTypes={html:String(html),isHTML:trustedTypes.isHTML(html),isScript:trustedTypes.isScript(html),name:policy.name.startsWith('environment-audit-')};
  }catch(e){out.trustedTypes={error:e.name,message:e.message}}
  try {
    const f=document.createElement('iframe');f.srcdoc='<meta http-equiv="Content-Security-Policy" content="script-src \'none\'"><script>window.auditRan=true<\/script><p>x</p>';
    const ready=new Promise(resolve=>{f.onload=resolve;setTimeout(resolve,1000)});document.body.appendChild(f);await ready;
    out.csp={scriptBlocked:f.contentWindow.auditRan!==true,domain:f.contentDocument.domain===document.domain};f.remove();
  }catch(e){out.csp={error:e.name,message:e.message}}
  return out;
})
