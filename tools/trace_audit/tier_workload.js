(() => {
  function measuredLeaf(value) {
    for (let step = 0; step < 32; step++) value = ((value * 33) ^ (value >>> 3) ^ step) | 0;
    return value;
  }
  function shiftedOne(value) { return measuredLeaf(value + 1); }
  function shiftedTwo(value) { return measuredLeaf(value + 2); }
  function measuredBytes(value) { return value.byteLength; }
  function acceptOnly(value) { return typeof value; }
  const calls = [measuredLeaf, shiftedOne, shiftedTwo];
  const buffer = new Uint8Array(1024);
  function run(iterations, byteCalls) {
    const started = performance.now();
    let checksum = 0;
    for (let i = 0; i < iterations; i++) checksum ^= calls[i % 3](i);
    let size = 0;
    for (let i = 0; i < byteCalls; i++) size += measuredBytes(buffer);
    return {page_ms: performance.now() - started, checksum: [checksum, size]};
  }
  function surface() {
    let gets = 0, traps = 0;
    const object = {get data() { gets++; return 1; }};
    const proxy = new Proxy({}, {get() { traps++; return 1; },
      ownKeys() { traps++; return []; }, getPrototypeOf() { traps++; return null; }});
    const types = [acceptOnly(object), acceptOnly(proxy)];
    const descriptor = Object.getOwnPropertyDescriptor(Math, 'imul');
    return {gets, traps, types, descriptor: [descriptor.writable, descriptor.enumerable,
      descriptor.configurable, descriptor.value.length, descriptor.value.toString()],
      leafSource: measuredLeaf.toString()};
  }
  window.tierBench = {run, surface};
})();
