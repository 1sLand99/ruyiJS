(() => {
  const result = window.mappingProof = {events: [], done: false, errors: []};
  function mark(label) {
    result.events.push(label);
    document.documentElement.setAttribute('data-causal-proof', label);
  }
  addEventListener('error', e => result.errors.push(e.message));
  addEventListener('unhandledrejection', e => result.errors.push(String(e.reason)));
  function registerSiblings() {
    mark('start');
    let resolve;
    const deferred = new Promise(r => { resolve = r; });
    deferred.then(function deferredReaction() { mark('reaction'); });
    const cancelled = setTimeout(function cancelledTimer() { mark('cancelled'); }, 100);
    clearTimeout(cancelled);
    setTimeout(function timerA() { mark('timer-a'); }, 0);
    setTimeout(function timerB() { mark('timer-b'); }, 0);
    setTimeout(function resolverTimer() {
      mark('resolve-before');
      resolve();
      mark('resolve-after');
    }, 20);
    setTimeout(function finishTimer() { mark('finish'); result.done = true; }, 40);
    mark('registered');
  }
  registerSiblings();
})();
