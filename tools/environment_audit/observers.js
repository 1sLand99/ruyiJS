(async window => {
  const out={},element=document.createElement('div');element.style.cssText='position:absolute;left:0;top:0;width:50px;height:25px';document.body.appendChild(element);
  try{
    out.resize=await new Promise(resolve=>{
      const id=setTimeout(()=>{observer.disconnect();resolve({timeout:true})},1500);
      const observer=new ResizeObserver(entries=>{clearTimeout(id);observer.disconnect();const e=entries[0];resolve({target:e.target===element,width:e.contentRect.width,height:e.contentRect.height,box:Array.isArray(e.contentBoxSize)})});
      observer.observe(element);
    });
  }catch(e){out.resize={error:e.name,message:e.message}}
  try{
    out.intersection=await new Promise(resolve=>{
      const id=setTimeout(()=>{observer.disconnect();resolve({timeout:true})},1500);
      const observer=new IntersectionObserver(entries=>{clearTimeout(id);observer.disconnect();const e=entries[0];resolve({target:e.target===element,intersecting:e.isIntersecting,ratio:e.intersectionRatio,rect:[e.boundingClientRect.width,e.boundingClientRect.height]})});
      observer.observe(element);
    });
  }catch(e){out.intersection={error:e.name,message:e.message}}
  try{
    const animation=element.animate([{opacity:0},{opacity:1}],{duration:20,fill:'forwards'});
    const completed=await Promise.race([animation.finished.then(()=>true),new Promise(resolve=>setTimeout(()=>resolve(false),1500))]);
    out.animation={completed,state:animation.playState,finished:animation.finished instanceof Promise,effect:animation.effect instanceof KeyframeEffect,timing:animation.effect.getTiming().duration};animation.cancel();
  }catch(e){out.animation={error:e.name,message:e.message}}
  element.remove();return out;
})
