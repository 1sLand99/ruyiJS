(async window => {
  const result = {}, document = window.document;
  const run = (name, action) => { try { result[name] = action(); } catch(e) { result[name] = {error:e.name,message:e.message}; } };
  const checksum = bytes => { let sum=0, hash=2166136261;for (const b of bytes) {sum+=b;hash=Math.imul(hash^b,16777619)>>>0;}return {length:bytes.length,sum,hash}; };
  run('canvasPixels', () => {
    const canvas = document.createElement('canvas');canvas.width=32;canvas.height=32;const c=canvas.getContext('2d');
    c.fillStyle='#f60';c.fillRect(1,2,12,9);c.globalCompositeOperation='multiply';c.fillStyle='#29f';c.beginPath();c.arc(14,14,9,0,Math.PI*2);c.fill();
    const first=checksum(c.getImageData(0,0,32,32).data);c.save();c.translate(2,3);c.restore();
    return {first,transform:[c.getTransform().a,c.getTransform().e],canvasIdentity:c.canvas===canvas};
  });
  run('textMetrics', () => {
    const old=document.documentElement.lang, rows=[];
    for (const language of ['en-US','zh-CN']) {
      document.documentElement.lang=language;
      for(const kind of ['canvas','offscreen']) {
        const canvas=kind==='canvas'?document.createElement('canvas'):new OffscreenCanvas(120,30);
        const c=canvas.getContext('2d');c.font='16px sans-serif';
        for(const text of ['Hello','😀','☀️']) {
          const m=c.measureText(text);rows.push({language,kind,text,width:m.width,ascent:m.fontBoundingBoxAscent,
            descent:m.fontBoundingBoxDescent,hanging:m.hangingBaseline,ideographic:m.ideographicBaseline});
        }
      }
    }
    document.documentElement.lang=old;return rows;
  });
  run('cssLayout', () => {
    const root=document.createElement('div');root.style.cssText='position:absolute;left:3px;top:5px;width:100px;height:20px;padding:2px;border:1px solid red;box-sizing:content-box';document.body.appendChild(root);
    const a=root.getBoundingClientRect(),s=getComputedStyle(root);const normal=[a.x,a.y,a.width,a.height,s.boxSizing,s.width,root.clientWidth];
    root.style.width='1e38px';const huge=root.getBoundingClientRect().width;root.remove();return {normal,huge};
  });
  run('svg', () => {
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg'),rect=document.createElementNS(ns,'rect');
    svg.setAttribute('viewBox','1 2 100 50');rect.setAttribute('width','10');rect.setAttribute('height','20');svg.appendChild(rect);document.body.appendChild(svg);
    const box=rect.getBBox();const values=[svg.viewBox.baseVal.x,svg.viewBox.baseVal.width,box.width,box.height];svg.remove();return values;
  });
  for(const kind of ['webgl','webgl2'])run(kind,() => {
    const c=document.createElement('canvas');c.width=8;c.height=8;const g=c.getContext(kind);
    if(!g)return null;
    g.clearColor(.25,.5,.75,1);g.clear(g.COLOR_BUFFER_BIT);const bytes=new Uint8Array(4);g.readPixels(0,0,1,1,g.RGBA,g.UNSIGNED_BYTE,bytes);
    const state={pixels:Array.from(bytes),version:g.getParameter(g.VERSION),viewport:Array.from(g.getParameter(g.VIEWPORT)),
      extensions:g.getSupportedExtensions().slice().sort(),attributes:g.getContextAttributes(),error:g.getError()};
    g.enable(0xdead);state.invalid=g.getError();g.getExtension('WEBGL_lose_context')?.loseContext();return state;
  });
  run('fontFaceSet',() => [document.fonts.status,typeof document.fonts.check('16px Arial'),document.fonts instanceof FontFaceSet]);
  try {
    const audio=new OfflineAudioContext(1,256,44100);const source=audio.createOscillator();source.type='sine';source.frequency.value=440;source.connect(audio.destination);source.start();
    const rendered=await audio.startRendering();const values=rendered.getChannelData(0);
    result.audio={length:values.length,channels:rendered.numberOfChannels,rate:rendered.sampleRate,head:Array.from(values.slice(0,8)),sum:Array.from(values).reduce((a,b)=>a+Math.abs(b),0)};
  } catch(e) {result.audio={error:e.name,message:e.message};}
  return result;
})
