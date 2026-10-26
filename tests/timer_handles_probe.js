(window => {
  const document = window.document;
  const a = document.createElement('iframe'), b = document.createElement('iframe');
  document.body.append(a,b);
  const wa=a.contentWindow, wb=b.contentWindow;
  const noop=()=>{};
  const t1=wa.setTimeout(noop,60000), i1=wa.setInterval(noop,60000);
  const t2=wb.setTimeout(noop,60000);
  const raf1=wa.requestAnimationFrame(noop), raf2=wb.requestAnimationFrame(noop);
  const t3=wa.setTimeout(noop,60000);
  const borrowed=wa.setTimeout.call(wb,noop,60000);
  const t4=wa.setTimeout(noop,60000), t5=wb.setTimeout(noop,60000);
  wa.clearTimeout(t1);wa.clearInterval(i1);wa.clearTimeout(t3);wa.clearTimeout(t4);
  wb.clearTimeout(t2);wa.clearTimeout(borrowed);wb.clearTimeout(borrowed);wb.clearTimeout(t5);
  wa.cancelAnimationFrame(raf1);wb.cancelAnimationFrame(raf2);
  const t6=wa.setTimeout(noop,60000);wa.clearTimeout(t6);
  const shape=Object.getOwnPropertyDescriptor(wa,'setTimeout');
  const result={ids:[t1,i1,t2,raf1,raf2,t3,borrowed,t4,t5,t6],
    shape:[shape.value.name,shape.value.length,shape.writable,shape.enumerable,shape.configurable,
           shape.value.toString().includes('[native code]')],
    separateFunctions:wa.setTimeout!==wb.setTimeout};
  a.remove();b.remove();
  return result;
})
