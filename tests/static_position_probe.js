(w=>{
  const document=w.document,result={};
  const root=document.createElement('div');root.style.cssText='position:fixed;left:10px;top:20px;width:300px;font:16px Arial;line-height:20px';document.body.append(root);
  const fixtures={
    after:'<div style="height:40px"></div><div data-target style="position:absolute;width:30px;height:10px"></div>',
    before:'<div data-target style="position:absolute;width:30px;height:10px"></div><div style="height:40px"></div>',
    between:'<div style="height:20px"></div><div data-target style="position:absolute;width:30px;height:10px"></div><div style="height:50px"></div>',
    margins:'<div style="height:40px;margin-bottom:12px"></div><div data-target style="position:absolute;width:30px;height:10px;margin-top:-5px;margin-left:7px"></div>',
    explicitTop:'<div style="height:40px"></div><div data-target style="position:absolute;top:3px;width:30px;height:10px"></div>',
    explicitLeft:'<div style="height:40px"></div><div data-target style="position:absolute;left:3px;width:30px;height:10px"></div>',
    repeated:'<div style="height:40px"></div><div data-target style="position:absolute;width:30px;height:10px"></div><div data-target style="position:absolute;width:50px;height:20px"></div>',
    nested:'<div style="height:40px"></div><div style="padding:3px"><div style="height:20px"></div><div data-target style="position:absolute;width:30px;height:10px"></div></div>',
    hidden:'<div style="display:none;height:40px"></div><div style="height:20px"></div><div data-target style="position:absolute;width:30px;height:10px"></div>',
    inlineBefore:'<span style="display:inline-block;width:50px;height:20px"></span><div data-target style="position:absolute;width:30px;height:10px"></div>',
    fixed:'<div style="height:40px"></div><div data-target style="position:fixed;width:30px;height:10px"></div>',
    descendant:'<div style="height:40px"></div><div style="position:absolute;width:30px;height:10px"><div data-target style="position:absolute;left:2px;top:3px;width:4px;height:5px"></div></div>'
  };
  for(const [name,html] of Object.entries(fixtures)){
    root.innerHTML=html;result[name]=Array.from(root.querySelectorAll('[data-target]'),e=>{
      const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height];
    });result[name+'|height']=root.getBoundingClientRect().height;
  }
  root.remove();return result;
})
