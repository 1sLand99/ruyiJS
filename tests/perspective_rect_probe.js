(w=>{
  const document=w.document,result={};
  const root=document.createElement('div');root.style.cssText='position:fixed;left:0;top:0;width:400px;height:400px';document.body.append(root);
  const cases={
    none:'none',translateZ:'translateZ(80px)',
    perspective:'perspective(800px) translateZ(80px)',
    negative:'perspective(800px) translateZ(-80px)',
    reverse:'translateZ(80px) perspective(800px)',
    translate3d:'perspective(800px) translate3d(10px,20px,80px)',
    scale3d:'scale3d(2,3,4)',rotateX:'rotateX(45deg)',rotateY:'rotateY(45deg)',
    matrix3d:'matrix3d(1,0,0,0,0,1,0,0,0,0,1,-0.00125,0,0,80,0.9)',
    rotatePerspective:'perspective(800px) rotateY(30deg)',
    rotate2d:'rotate(30deg)',matrix2d:'matrix(1.11,2.0001,-1.0001,1.009,150,94.4)',
  };
  for(const [name,transform] of Object.entries(cases)){
    const e=document.createElement('div');e.style.cssText='position:absolute;left:20px;top:30px;width:100px;height:50px;transform:'+transform;root.append(e);
    for(const origin of ['50% 50%','0px 0px']){
      e.style.transformOrigin=origin;const r=e.getBoundingClientRect();result[name+'|'+origin]=[r.x,r.y,r.width,r.height];
    }
    e.remove();
  }
  root.remove();return result;
})
