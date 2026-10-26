(() => {
  function snapshotTarget(value){'use strict';return value.answer;}
  const value={answer:17,nested:{label:'fixed',score:23},array:[1,2,3]};
  const functions=[snapshotTarget,v=>snapshotTarget(v)^13,v=>snapshotTarget(v)+7];
  const samples=[];let checksum=0;
  for(let batch=0;batch<12;batch++) {
    const started=performance.now();
    for(let i=0;i<1000000;i++){value.answer=i;checksum^=functions[i%3](value);}
    samples.push(performance.now()-started);
  }
  window.snapshotResult={gets:0,traps:0,jsonCalls:0,checksum,samples,
    descriptor:Object.getOwnPropertyDescriptor(value,'answer')};
})();
