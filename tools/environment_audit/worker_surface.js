(scope => {
  const tag=Object.prototype.toString,key=k=>typeof k==='symbol'?'@@'+k.description:k;
  const fn=f=>({name:f.name,length:f.length,native:Function.prototype.toString.call(f).includes('[native code]')});
  const describe=obj=>{
    const order=Reflect.ownKeys(obj),properties={};
    for(const k of order){const d=Object.getOwnPropertyDescriptor(obj,k),r={enumerable:d.enumerable,configurable:d.configurable};
      if('value'in d){r.kind='data';r.writable=d.writable;r.type=d.value===null?'null':typeof d.value;if(typeof d.value==='function')r.function=fn(d.value);}
      else {r.kind='accessor';r.get=d.get?fn(d.get):null;r.set=d.set?fn(d.set):null;}
      properties[key(k)]=r;
    }return {order:order.map(key),properties};
  };
  const result={globals:describe(scope),interfaces:{},instances:{},chains:{},errors:[]};
  for(const name of Reflect.ownKeys(scope)){
    if(typeof name!=='string')continue;const d=Object.getOwnPropertyDescriptor(scope,name);
    if(!d||typeof d.value!=='function')continue;
    result.interfaces[name]=describe(d.value);
    if(d.value.prototype)result.interfaces[name+'.prototype']=describe(d.value.prototype);
  }
  for(const name of ['navigator','performance','location','crypto']){
    try{result.instances[name]=describe(scope[name]);let p=Object.getPrototypeOf(scope[name]),depth=0;
      while(p&&depth++<8){const label=p.constructor?.name||tag.call(p);result.chains[label+'.prototype']=describe(p);p=Object.getPrototypeOf(p);}}
    catch(e){result.errors.push({name,error:e.name})}
  }
  return result;
})
