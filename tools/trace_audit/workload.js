(() => {
  function leaf(value) { return ((value * 33) ^ (value >>> 3)) | 0; }
  function bytes(value) { return value.byteLength; }
  const functions = [leaf, x => leaf(x + 1), x => leaf(x + 2)];
  const buffer = new Uint8Array(1024);
  const node = document.createElement('div');
  node.id = 'trace-bench';
  document.body.appendChild(node);

  function surface() {
    let traps = 0, getters = 0;
    const proxy = new Proxy({}, {get() { traps++; return 1; },
      ownKeys() { traps++; return []; }, getPrototypeOf() { traps++; return null; }});
    const object = {get probe() { getters++; return 1; }};
    function accept(value) { return value === proxy || value === object; }
    const accepted = [accept(proxy), accept(object)];
    const method = Object.getOwnPropertyDescriptor(Document.prototype, 'createElement');
    return {traps, getters, accepted,
      method: {writable: method.writable, enumerable: method.enumerable,
        configurable: method.configurable, name: method.value.name,
        length: method.value.length, source: Function.prototype.toString.call(method.value)},
      keys: Reflect.ownKeys(Document.prototype).map(String),
      randomSource: Function.prototype.toString.call(Math.random)};
  }

  function benchmark(iterations) {
    let sum = 0;
    let start = performance.now();
    for (let i = 0; i < iterations; i++) sum ^= functions[i % 3](i);
    const js = performance.now() - start;
    start = performance.now();
    let dom = 0;
    for (let i = 0; i < 2000; i++) {
      const child = document.createElement('span');
      child.setAttribute('data-index', String(i));
      node.appendChild(child);
      dom += child.getAttribute('data-index').length;
      node.removeChild(child);
    }
    const domMs = performance.now() - start;
    start = performance.now();
    let data = 0;
    for (let i = 0; i < 20000; i++) data += bytes(buffer);
    return {js_ms: js, dom_ms: domMs, values_ms: performance.now() - start,
      checksum: [sum, dom, data]};
  }

  async function chain() {
    const order = ['script'];
    const event = new EventTarget();
    event.addEventListener('probe', () => order.push('listener'));
    queueMicrotask(() => order.push('microtask'));
    await Promise.resolve();
    order.push('promise');
    await new Promise(resolve => setTimeout(resolve, 0));
    order.push('timer');
    event.dispatchEvent(new Event('probe'));
    return order;
  }

  window.traceBench = {benchmark, surface, chain};
})();
