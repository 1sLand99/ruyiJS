(w => {
  const result = {}, document = w.document;
  const host = document.createElement('div');
  host.style.cssText='position:absolute;left:0;top:0;width:500px;height:300px';
  document.body.append(host);
  const cases = {
    normal:'width:100.25px;height:20.5px;left:3.1px;top:-4.2px',
    large:'width:1e38px;height:1e38px',
    boundary:'width:17895697px;height:17895698px',
    negativePosition:'width:10px;height:20px;left:-1e38px;top:-1e38px',
    positivePosition:'width:10px;height:20px;left:1e38px;top:1e38px',
    padded:'width:1e38px;height:20px;padding:2px;border:1px solid red',
    borderBox:'width:1e38px;height:20px;padding:2px;border:1px solid red;box-sizing:border-box',
    centered:'width:8e37px;height:100px;left:50%;transform:translateX(-50%)',
    maxWidth:'width:1e38px;height:20px;max-width:120px',
    minWidth:'width:20px;height:20px;min-width:1e38px',
    percentage:'width:1e30%;height:20px',
    viewport:'width:1e30vw;height:20px',
    transformed:'width:100px;height:20px;transform:scaleX(1e30)',
  };
  for(const [name,css] of Object.entries(cases)) {
    const e=document.createElement('div');e.style.cssText='position:absolute;left:0;top:0;'+css;host.append(e);
    const r=e.getBoundingClientRect(), list=e.getClientRects();
    result[name]={rect:[r.x,r.y,r.width,r.height],offset:[e.offsetWidth,e.offsetHeight],
      client:[e.clientWidth,e.clientHeight],list:[list.length,list[0].width,list[0].height]};
    e.remove();
  }
  host.remove();
  result.standalone=new w.DOMRect(1e38,-1e38,1e38,1e38).width;
  return result;
})
