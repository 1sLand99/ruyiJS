(window => {
  const d=window.document, output={};
  for(const kind of ['webgl','webgl2']) {
    const canvas=d.createElement('canvas');canvas.width=4;canvas.height=3;
    const gl=canvas.getContext(kind);if(!gl){output[kind]={missing:true};continue;}
    const result={};output[kind]=result;
    const pixels=()=>{const p=new window.Uint8Array(canvas.width*canvas.height*4);
      gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,p);return Array.from(p);};
    result.initial=pixels();gl.clearColor(.25,.5,.75,1);gl.clear(gl.COLOR_BUFFER_BIT);
    result.full=pixels();
    gl.enable(gl.SCISSOR_TEST);gl.scissor(1,1,2,1);gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);
    result.scissor=pixels();
    gl.colorMask(false,true,false,false);gl.clearColor(0,1,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    result.mask=pixels();
    gl.disable(gl.SCISSOR_TEST);gl.colorMask(true,true,true,true);gl.viewport(0,0,0,0);
    gl.enable(gl.BLEND);gl.clearColor(0,0,1,.5);gl.clear(gl.COLOR_BUFFER_BIT);
    result.viewportBlend=pixels();
    gl.clearColor(1,1,1,1);gl.clear(gl.DEPTH_BUFFER_BIT|gl.STENCIL_BUFFER_BIT);result.depthOnly=pixels();
    gl.clear(0);result.zeroMask=pixels();gl.clear(1);result.invalid=[gl.getError(),pixels()];
    gl.enable(gl.SCISSOR_TEST);gl.scissor(-1,-1,2,2);gl.clear(gl.COLOR_BUFFER_BIT);result.clipped=pixels();
    gl.scissor(0,0,0,0);gl.clearColor(1,0,1,1);gl.clear(gl.COLOR_BUFFER_BIT);result.empty=pixels();
    gl.disable(gl.SCISSOR_TEST);
    result.values=[];
    for(const v of [.1,.2,.3,.4,.49,.5,.51,.9,0,1,-1,2]){
      gl.clearColor(v,v,v,v);gl.clear(gl.COLOR_BUFFER_BIT);
      result.values.push([v,pixels().slice(0,4),Array.from(gl.getParameter(gl.COLOR_CLEAR_VALUE))]);
    }
    const fb=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,fb);
    result.bound=[gl.getParameter(gl.FRAMEBUFFER_BINDING)===fb,gl.checkFramebufferStatus(gl.FRAMEBUFFER)];
    gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);result.framebufferError=gl.getError();
    gl.deleteFramebuffer(fb);result.deleted=[gl.getParameter(gl.FRAMEBUFFER_BINDING),gl.isFramebuffer(fb),pixels()];
    canvas.width=2;gl.clearColor(0,1,0,1);gl.clear(gl.COLOR_BUFFER_BIT);result.resized=pixels();
    const method=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(gl),'clear');
    let receiver,arity;try{method.value.call({},0);}catch(e){receiver=e.name;}try{gl.clear();}catch(e){arity=e.name;}
    result.descriptor=[method.enumerable,method.configurable,method.writable,method.value.length,receiver,arity,
      String(method.value).includes('[native code]'),Object.hasOwn(gl,'clear')];
    result.error=gl.getError();
  }
  return output;
})
