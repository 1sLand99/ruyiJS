(() => {
  const results = window.asyncProof = {events: [], done: false, errors: [], intervalCount: 0};
  function record(label) {
    results.events.push(label);
    document.documentElement.setAttribute('data-causal-proof', label);
  }
  window.addEventListener('error', e => results.errors.push(e.message));
  window.addEventListener('unhandledrejection', e => results.errors.push(String(e.reason)));
  const frame = document.querySelector('iframe');
  const worker = new Worker('/async-worker.js');
  const channel = new MessageChannel();
  const target = new EventTarget();
  let ticks = 0;
  target.addEventListener('local-proof', function localListener() { record('listener'); });
  channel.port1.onmessage = function portReceive(event) {
    if (event.data !== 'port-value') return;
    record('port-receive');
    frame.contentWindow.postMessage('frame-request', location.origin);
  };
  worker.onmessage = function workerReceive(event) {
    if (event.data !== 'worker-response') return;
    record('worker-receive');
    const interval = setInterval(function recurringCallback() {
      ++ticks; results.intervalCount = ticks;
      record('interval-' + ticks);
      if (ticks === 3) {
        clearInterval(interval);
        queueMicrotask(function finalMicrotask() {
          record('complete'); results.done = true;
          worker.terminate(); channel.port1.close(); channel.port2.close();
        });
      }
    }, 10);
  };
  window.addEventListener('message', function windowReceive(event) {
    if (event.source === window && event.data === 'self-value') {
      record('self-receive'); channel.port2.postMessage('port-value');
    } else if (event.source === frame.contentWindow && event.data === 'frame-response') {
      record('frame-receive'); worker.postMessage('worker-request');
    }
  });
  window.startAsyncProof = function startAsyncProof() {
    if (results.events.length) throw new Error('fixture started twice');
    record('start');
    const cancelled = setTimeout(() => record('cancelled-ran'), 1000);
    clearTimeout(cancelled);
    queueMicrotask(function firstMicrotask() {
      record('microtask');
      Promise.resolve().then(function promiseCallback() {
        record('promise');
        setTimeout(function timeoutCallback() {
          record('timeout'); record('before-dispatch');
          target.dispatchEvent(new Event('local-proof'));
          record('after-dispatch'); window.postMessage('self-value', location.origin);
        }, 0);
      });
    });
    return null;
  };
})();
