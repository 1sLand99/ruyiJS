(() => {
  let gets=0, traps=0, jsonCalls=0;
  const plain={answer:42, text:'quote"\\\n\ud800', missing:undefined, zero:-0};
  Object.defineProperty(plain,'hidden',{value:'kept',enumerable:false});
  const accessor={safe:'data',get danger(){gets++;throw new Error('getter executed')}};
  const proxy=new Proxy({}, {get(){traps++;throw new Error('get trap')},
    ownKeys(){traps++;throw new Error('keys trap')},getPrototypeOf(){traps++;throw new Error('prototype trap')}});
  const cycle={name:'cycle'};cycle.self=cycle;
  const array=[1,,{nested:'array-value'}];array.extra='own';
  const nested={child:{leaf:{value:73}}};
  const wide={};for(let i=0;i<50;i++)wide['key'+i]=i;
  const deep={a:{b:{c:{d:{e:1}}}}};
  const stringify={toJSON(){jsonCalls++;return 'changed'},text:'x'.repeat(300)};
  const longString={text:JSON.parse('"'+'y'.repeat(300)+'"')};
  const dictionary={};for(let i=0;i<40;i++)dictionary['d'+i]=i;delete dictionary.d3;
  const indexed=[1,2];Object.defineProperty(indexed,'1',{get(){gets++;return 99}});
  const symbolKey={};symbolKey[Symbol('hidden')]=42;
  function snapshotReturn(value){'use strict';return value;}
  function snapshotTarget(value){'use strict';return 17;}
  function ignoredTarget(value){'use strict';return 19;}
  const before=Object.getOwnPropertyDescriptor(plain,'hidden');
  const checks=[];
  checks.push(snapshotTarget(plain));
  checks.push(snapshotTarget(accessor));
  checks.push(snapshotTarget(proxy));
  checks.push(snapshotTarget(cycle));
  checks.push(snapshotTarget(array));
  checks.push(snapshotTarget(nested));
  checks.push(snapshotTarget(wide));
  checks.push(snapshotTarget(deep));
  checks.push(snapshotTarget(stringify));
  checks.push(snapshotTarget(longString));
  checks.push(snapshotTarget(dictionary));
  checks.push(snapshotTarget(indexed));
  checks.push(snapshotTarget(symbolKey));
  checks.push(snapshotReturn({returned:true})!==null);
  checks.push(snapshotTarget(new Uint8Array([1,2,254])));
  checks.push(snapshotTarget({0:'numeric-slot',2:81}));
  checks.push(ignoredTarget({excluded:99}));
  const after=Object.getOwnPropertyDescriptor(plain,'hidden');
  window.snapshotResult={gets,traps,jsonCalls,checks,
    descriptorsEqual:before.value===after.value&&before.enumerable===after.enumerable&&before.writable===after.writable,
    functionSource:snapshotTarget.toString(),ownKeys:Reflect.ownKeys(plain).map(String)};
})();
