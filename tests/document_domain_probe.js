(window => {
  const document = window.document;
  const frame = document.createElement('iframe');
  document.body.appendChild(frame);
  const child = frame.contentWindow;
  const nested = child.document.createElement('iframe');
  child.document.body.appendChild(nested);
  const getter = Object.getOwnPropertyDescriptor(window.Document.prototype, 'domain').get;
  const read = doc => ({url:doc.URL, domain:doc.domain});
  let receiverError;
  try { getter.call({}); } catch (error) { receiverError = error.name; }
  const result = {
    main:read(document), blank:read(child.document), nested:read(nested.contentDocument),
    parsed:read(new window.DOMParser().parseFromString('<!doctype html><p>x', 'text/html')),
    created:read(document.implementation.createHTMLDocument('x')),
    constructed:read(new window.Document()), borrowed:getter.call(child.document),
    identity:child.document instanceof child.Document && !(child.document instanceof window.Document),
    receiverError, native:Function.prototype.toString.call(getter).includes('[native code]')
  };
  frame.remove();
  return result;
})
