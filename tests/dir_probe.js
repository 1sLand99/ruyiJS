(window => {
  const doc = window.document;
  const descriptor = window.Object.getOwnPropertyDescriptor(window.HTMLElement.prototype, 'dir');
  const element = doc.createElement('div');
  const values = ['ltr', 'RTL', 'AuTo', '', 'invalid', ' ltr', 'rtl ', '\u212a', null, undefined, 42];
  const assignments = values.map(value => {
    element.dir = value;
    return [element.dir, element.getAttribute('dir')];
  });
  element.setAttribute('dir', 'RtL');
  const direct = [element.dir, element.getAttribute('dir')];
  element.removeAttribute('dir');
  const absent = [element.dir, element.hasAttribute('dir')];
  const parent = doc.createElement('section');
  parent.dir = 'rtl';
  parent.appendChild(element);
  const inherited = element.dir;
  element.dir = 'auto';
  const clone = element.cloneNode(false);
  const cloned = [clone.dir, clone.getAttribute('dir'), clone instanceof window.HTMLElement];
  let converted = 0;
  element.dir = {toString() { converted++; return 'LtR'; }};
  const conversion = [element.dir, element.getAttribute('dir'), converted];
  let symbolError;
  try { element.dir = window.Symbol('bad'); } catch (error) { symbolError = error.name; }
  const atomic = [symbolError, element.dir, element.getAttribute('dir')];
  const brands = [];
  for (const receiver of [{}, doc, doc.createElementNS('http://www.w3.org/2000/svg', 'svg')]) {
    try { descriptor.get.call(receiver); brands.push('accepted'); }
    catch (error) { brands.push([error.name, error instanceof window.TypeError]); }
  }
  let writeConversions = 0;
  try { descriptor.set.call({}, {toString() { writeConversions++; return 'rtl'; }}); }
  catch (error) { brands.push([error.name, error instanceof window.TypeError]); }
  return {assignments, direct, absent, inherited, cloned, conversion, atomic, brands,
    writeConversions, descriptor: {enumerable:descriptor.enumerable,
      configurable:descriptor.configurable, getLength:descriptor.get.length,
      setLength:descriptor.set.length, own:window.Object.hasOwn(element, 'dir'),
      shared:window.Object.getOwnPropertyDescriptor(window.HTMLDivElement.prototype,'dir') === undefined}};
})
