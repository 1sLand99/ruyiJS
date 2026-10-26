(async window => {
  const result = {}, document = window.document;
  const run = (name, action) => { try { result[name] = action(); } catch (e) { result[name] = {error:e.name, message:e.message}; } };
  run('attributes', () => {
    const element = document.createElement('input');
    element.setAttribute('data-X', '1'); element.setAttribute('disabled', ''); element.value = 'a';
    const values = [element.disabled, element.getAttribute('data-x'), element.dataset.x, element.value, element.defaultValue];
    element.removeAttribute('disabled'); element.defaultValue = 'b';
    return {values, after:[element.disabled, element.value, element.defaultValue], keys:Array.from(element.attributes, a => a.name)};
  });
  run('collections', () => {
    const root = document.createElement('div'); root.innerHTML = '<span></span>text<span></span>';
    const live = root.children, fixed = root.querySelectorAll('span'); root.appendChild(document.createElement('b'));
    return [live.length, fixed.length, root.childNodes.length, Object.prototype.toString.call(live),
      Array.from(root.childNodes, n => n.nodeType), live === root.children];
  });
  run('treewalker', () => {
    const root = document.createElement('div'); root.innerHTML = '<p id="skip"><b id="keep"></b></p><p id="reject"><i></i></p><p id="last"></p>';
    const walker = document.createTreeWalker(root, 1, n => n.id === 'skip' ? 3 : n.id === 'reject' ? 2 : 1);
    const next = []; for (let n; (n = walker.nextNode()) && next.length < 10;) next.push(n.id);
    return {next, previous:walker.previousNode()?.id, root:walker.root === root, tag:Object.prototype.toString.call(walker)};
  });
  run('shadow', () => {
    const host = document.createElement('div');document.body.appendChild(host);
    const shadow = host.attachShadow({mode:'open'});shadow.innerHTML = '<span id="a:b">x</span>';
    const node = shadow.getElementById('a:b');
    const value = [node.textContent, node.getRootNode() === shadow, node.getRootNode({composed:true}) === document,
      shadow.activeElement, shadow.host === host, shadow.mode, shadow instanceof DocumentFragment];
    host.remove(); return value;
  });
  run('fragment', () => {
    const root = document.createElement('div'), fragment = document.createDocumentFragment();
    root.innerHTML = '<p>old</p>';fragment.append(document.createElement('b'), 'text');
    const old = root.firstChild;root.replaceChild(fragment, old);
    return [root.innerHTML, fragment.childNodes.length, old.parentNode,fragment.nodeType];
  });
  run('range', () => {
    const root = document.createElement('div');root.innerHTML = '<span>abcd</span><i>ef</i>';
    const range = document.createRange();range.setStart(root.firstChild.firstChild, 1);range.setEnd(root.lastChild.firstChild, 1);
    const selected = range.toString();const part = range.cloneContents();
    return [selected, part.textContent, range.collapsed,range.commonAncestorContainer === root];
  });
  run('reflection', () => {
    const element = document.createElement('div');element.dir = 'RTL';element.lang = 'en-US';element.tabIndex = 4;
    return [element.dir,element.getAttribute('dir'),element.lang,element.tabIndex,element.cloneNode().dir];
  });
  run('form', () => {
    const form = document.createElement('form');form.innerHTML = '<input name="a" value="1"><input name="c" type="checkbox" checked><input name="x" disabled value="skip"><select name="s"><option value="v" selected>V</option></select>';
    return Array.from(new FormData(form).entries());
  });
  run('parsing', () => {
    const parsed = new DOMParser().parseFromString('<!doctype html><table><tr><td>x</td></tr></table>', 'text/html');
    return [parsed.contentType,parsed.documentElement.tagName,parsed.querySelector('tbody')?.tagName,parsed.domain,
      document.implementation.createHTMLDocument('x').domain];
  });
  run('eventPropagation', () => {
    const root = document.createElement('div'), child = document.createElement('span');root.appendChild(child);
    const calls = [];root.addEventListener('audit', e => calls.push(['capture',e.eventPhase]),true);
    child.addEventListener('audit', e => { calls.push(['target',e.eventPhase]);e.preventDefault(); }, {once:true});
    root.addEventListener('audit', e => calls.push(['bubble',e.eventPhase]));
    const event = new Event('audit',{bubbles:true,cancelable:true});const first = child.dispatchEvent(event);child.dispatchEvent(new Event('audit'));
    return {calls, first, prevented:event.defaultPrevented,trusted:event.isTrusted,target:event.target === child};
  });
  const observed = [], root = document.createElement('div');
  const observer = new MutationObserver(records => observed.push(...records.map(r => [r.type,r.attributeName,r.addedNodes.length])));
  observer.observe(root,{childList:true,attributes:true});root.setAttribute('id','x');root.appendChild(document.createElement('b'));
  await Promise.resolve();observer.disconnect();result.mutations = observed;
  return result;
})
