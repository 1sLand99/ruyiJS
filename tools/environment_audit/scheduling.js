(async window => {
  const out={},order=[];
  await new Promise(resolve=>{
    setTimeout(()=>{order.push('timer');resolve()},0);
    Promise.resolve().then(()=>order.push('promise'));
    queueMicrotask(()=>order.push('microtask'));order.push('sync');
  });out.order=order;
  let cancelled=false;const timer=setTimeout(()=>cancelled=true,0);clearTimeout(timer);await new Promise(resolve=>setTimeout(resolve,25));out.cancelled=cancelled;
  out.interval=await new Promise(resolve=>{let count=0;const id=setInterval(()=>{if(++count===3){clearInterval(id);resolve(count)}},5)});
  const start=performance.now();await new Promise(resolve=>setTimeout(resolve,25));
  out.clock={monotonic:performance.now()>=start,timeOriginFinite:Number.isFinite(performance.timeOrigin),aligned:Math.abs(Date.now()-performance.timeOrigin-performance.now())<100};
  performance.clearMarks();performance.clearMeasures();performance.mark('a');
  const observed=[];const observer=new PerformanceObserver(list=>observed.push(...list.getEntries().map(e=>[e.name,e.entryType])));
  observer.observe({entryTypes:['measure']});performance.measure('audit',{start:1,end:3});
  await new Promise(resolve=>setTimeout(resolve,30));observer.disconnect();
  const measure=performance.getEntriesByName('audit','measure')[0];out.performance={observed,duration:measure?.duration,entryIdentity:measure instanceof PerformanceMeasure,
    toJSON:measure&&Object.keys(measure.toJSON()).sort(),types:PerformanceObserver.supportedEntryTypes.slice().sort()};
  try{out.animationFrame=await new Promise(resolve=>requestAnimationFrame(timestamp=>resolve({finite:Number.isFinite(timestamp),number:typeof timestamp})));}
  catch(e){out.animationFrame={error:e.name}}
  return out;
})
