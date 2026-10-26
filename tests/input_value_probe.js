(window => {
  const d=window.document, result={};
  const input=(type='text')=>{const e=d.createElement('input');e.type=type;return e;};
  const snapshot=e=>[e.value,e.defaultValue,e.getAttribute('value')];
  const run=(name,fn)=>{try{result[name]=fn();}catch(e){result[name]={error:e.name,message:e.message};}};
  run('dirty',()=>{
    const e=input(), rows=[snapshot(e)];e.defaultValue='seed';rows.push(snapshot(e));
    e.value='live';rows.push(snapshot(e));e.defaultValue='next';rows.push(snapshot(e));
    e.removeAttribute('value');rows.push(snapshot(e));e.value='';rows.push(snapshot(e));
    e.setAttributeNS(null,'value','last');rows.push(snapshot(e));return rows;
  });
  run('modes',()=>['text','search','password','tel','url','email','number','hidden','submit','button','reset','image','checkbox','radio'].map(type=>{
    const e=input(type);e.defaultValue='12';e.value='34';e.defaultValue='56';return [type,...snapshot(e)];
  }));
  run('transitions',()=>{
    const rows=[];
    for(const first of ['text','hidden','checkbox','file'])for(const next of ['text','hidden','checkbox','file']){
      const e=input(first);e.defaultValue='seed';if(first!=='file')e.value='live';
      e.setAttribute('type',next);rows.push([first,next,...snapshot(e)]);
      e.setAttributeNS(null,'type','text');rows.push(['back',...snapshot(e)]);
    }return rows;
  });
  run('clone',()=>{
    const e=input();e.defaultValue='seed';e.value='live';
    const c=e.cloneNode(), other=d.implementation.createHTMLDocument('copy'), i=other.importNode(e,true);
    c.defaultValue='clone';i.defaultValue='import';other.adoptNode(e);e.defaultValue='adopt';
    return [snapshot(e),snapshot(c),snapshot(i),e.ownerDocument===other];
  });
  run('form',()=>{
    const f=d.createElement('form');f.innerHTML='<input name="x" value="seed" required><input type="hidden" name="h" value="v">';d.body.append(f);
    const e=f.elements.x;e.value='live';e.defaultValue='new';
    const before=Array.from(new window.FormData(f));e.value='';const missing=e.validity.valueMissing;
    f.reset();const after=[snapshot(e),Array.from(new window.FormData(f)),e.validity.valueMissing];
    e.defaultValue='clean';after.push(snapshot(e));f.remove();return {before,missing,after};
  });
  run('resetEvents',()=>{
    const f=d.createElement('form'), e=input();e.defaultValue='seed';e.value='live';f.append(e);d.body.append(f);
    const events=[];const cancel=ev=>{events.push([ev.bubbles,ev.cancelable,ev.isTrusted,e.value]);ev.preventDefault();};
    f.addEventListener('reset',cancel);f.reset();const kept=snapshot(e);f.removeEventListener('reset',cancel);
    f.addEventListener('reset',()=>{events.push(['again',e.value]);f.reset();e.defaultValue='handler';},{once:true});
    f.reset();const restored=snapshot(e);f.remove();return {events,kept,restored};
  });
  run('mutations',()=>{
    const e=input(), o=new window.MutationObserver(()=>{});o.observe(e,{attributes:true,attributeOldValue:true});
    e.value='live';const current=o.takeRecords().map(r=>[r.attributeName,r.oldValue]);
    e.defaultValue='seed';const defaults=o.takeRecords().map(r=>[r.attributeName,r.oldValue]);
    e.type='hidden';const transition=o.takeRecords().map(r=>[r.attributeName,r.oldValue]);
    o.disconnect();return {current,defaults,transition};
  });
  run('conversion',()=>{
    const e=input(), values=[];
    for(const value of [null,undefined,1.25,Infinity,NaN]){e.value=value;values.push(snapshot(e));}
    let error;try{e.value=Symbol('x');}catch(e){error=e.name;}
    const f=input('file');let fileError;try{f.value='path';}catch(e){fileError=e.name;}f.value='';
    return {values,error,fileError,file:snapshot(f)};
  });
  run('numericRange',()=>{
    const e=input('number');e.defaultValue='1';e.valueAsNumber=2;e.stepUp();
    const t=input();t.defaultValue='abc';t.setRangeText('Z',1,2,'preserve');
    return [snapshot(e),e.valueAsNumber,snapshot(t)];
  });
  run('realm',()=>{
    const frame=d.createElement('iframe');d.body.append(frame);const w=frame.contentWindow;
    const e=w.document.createElement('input'), a=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value');
    const b=Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value');
    a.set.call(e,'live');e.defaultValue='seed';let error;try{a.set.call({},'x');}catch(e){error=e.name;}
    const values=[a.get.call(e),b.get.call(e),e.defaultValue,a.get!==b.get,e instanceof w.HTMLInputElement,
      e instanceof window.HTMLInputElement,a.enumerable,a.configurable,a.get.length,a.set.length,error,
      Object.hasOwn(e,'value'),String(a.set).includes('[native code]')];frame.remove();return values;
  });
  return result;
})
