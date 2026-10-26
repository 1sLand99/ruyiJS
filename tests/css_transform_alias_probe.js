(w => {
  const document=w.document, results={};
  const declarations=[
    'transform:translateX(5px);-webkit-transform:translateX(15px);-moz-transform:translateX(25px)',
    '-moz-transform:translateX(25px);transform:translateX(5px)',
    'transform:translateX(5px)!important;-webkit-transform:translateX(15px)',
    '-moz-transform:translateX(25px)!important;transform:translateX(5px)!important',
    'transform:translateX(5px);-ms-transform:translateX(30px);-o-transform:translateX(40px)',
  ];
  const element=document.createElement('div');element.id='alias-test';
  const host=document.createElement('div');host.style.cssText='position:fixed;left:0;top:0';host.append(element);document.body.append(host);
  const snapshot=style=>({text:style.cssText,keys:Array.from({length:style.length},(_,i)=>style.item(i)),
    values:['transform','-webkit-transform','-moz-transform'].map(n=>style.getPropertyValue(n)),
    priorities:['transform','-webkit-transform','-moz-transform'].map(n=>style.getPropertyPriority(n))});
  for(let i=0;i<declarations.length;i++){
    element.style.cssText=declarations[i];results['inline'+i]=snapshot(element.style);
    results['position'+i]=element.getBoundingClientRect().x;
  }
  element.style.cssText='';element.style.setProperty('-moz-transform','translateX(9px)');
  results.set=snapshot(element.style);results.removed=element.style.removeProperty('-webkit-transform');
  results.afterRemove=snapshot(element.style);
  element.style.cssText='';element.style.MozTransform='translateX(11px)';
  results.named=snapshot(element.style);
  const sheet=document.createElement('style');sheet.textContent='#alias-test{'+declarations[0]+'}';document.head.append(sheet);
  element.style.cssText='';results.rule=snapshot(sheet.sheet.cssRules[0].style);results.rulePosition=element.getBoundingClientRect().x;
  sheet.sheet.cssRules[0].style.setProperty('-webkit-transform','translateX(17px)');
  results.ruleSet=snapshot(sheet.sheet.cssRules[0].style);results.ruleSetPosition=element.getBoundingClientRect().x;
  const style=element.style, getter=w.Object.getOwnPropertyDescriptor(w.CSSStyleProperties.prototype,'transform').get;
  let invalid;try{getter.call({})}catch(e){invalid=e.name}
  results.identity=[element.style===style,w.Object.getPrototypeOf(style)===w.CSSStyleProperties.prototype,invalid];
  sheet.remove();host.remove();return results;
})
