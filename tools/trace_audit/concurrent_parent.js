(() => {
  const frames = Array.from(document.querySelectorAll('iframe'));
  const state = window.concurrentProof = {ready: [], sent: [0, 0], received: [0, 0],
    order: [], errors: [], done: false, started: false, count: 8};
  function record(label) {
    state.order.push(label);
    document.documentElement.setAttribute('data-concurrent-proof', label);
  }
  addEventListener('error', e => state.errors.push(e.message));
  addEventListener('unhandledrejection', e => state.errors.push(String(e.reason)));
  addEventListener('message', function parentReceive(event) {
    const index = frames.findIndex(frame => frame.contentWindow === event.source);
    if (index < 0 || event.origin !== new URL(frames[index].src).origin) return;
    if (event.data === 'ready') {
      if (state.ready.includes(index)) throw new Error('duplicate ready');
      state.ready.push(index); record('parent:ready:' + index);
    } else if (event.data === 'pong') {
      if (++state.received[index] > state.count) throw new Error('extra response');
      record('parent:receive:' + index + ':' + state.received[index]);
      if (state.received.every(value => value === state.count)) {
        record('parent:done'); state.done = true;
      }
    }
  });
  window.startConcurrentProof = function startConcurrentProof() {
    if (state.started || state.ready.length !== 2) throw new Error('fixture not ready');
    state.started = true; record('parent:start');
    for (let n = 0; n < state.count; n++) {
      for (let index = 0; index < frames.length; index++) {
        record('parent:send:' + index + ':' + (++state.sent[index]));
        frames[index].contentWindow.postMessage('ping', new URL(frames[index].src).origin);
      }
    }
    return null;
  };
})();
