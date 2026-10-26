(function captureSurface(w) {
  "use strict";
  const own = Reflect.ownKeys, descriptor = Object.getOwnPropertyDescriptor;
  const prototype = Object.getPrototypeOf, tag = Object.prototype.toString;
  const keyName = k => typeof k === "symbol" ? "@@" + (k.description || "") : k;
  const result = {metadata: {}, globals: {}, interfaces: {}, instances: {}, chains: {}, errors: []};
  function failure(where, e) {
    result.errors.push({where, name: String(e.name), message: String(e.message).slice(0, 300)});
  }
  function functionInfo(fn) {
    return {name: fn.name, length: fn.length,
            native: Function.prototype.toString.call(fn).includes("[native code]")};
  }
  function describe(object) {
    const keys = own(object), properties = {};
    for (const key of keys) {
      const d = descriptor(object, key);
      const row = {configurable: d.configurable, enumerable: d.enumerable};
      if ("value" in d) {
        row.kind = "data"; row.writable = d.writable;
        row.type = d.value === null ? "null" : typeof d.value;
        if (typeof d.value === "function") row.function = functionInfo(d.value);
        if (/^[A-Z][A-Z_0-9]+$/.test(String(key)) &&
            ["number", "string", "boolean"].includes(typeof d.value)) row.constant = d.value;
      } else {
        row.kind = "accessor";
        row.get = d.get ? functionInfo(d.get) : null;
        row.set = d.set ? functionInfo(d.set) : null;
      }
      properties[keyName(key)] = row;
    }
    return {order: keys.map(keyName), properties};
  }
  function className(object) {
    if (typeof object === "function" && object.name) return object.name;
    const d = descriptor(object, "constructor");
    if (d && typeof d.value === "function") return d.value.name + ".prototype";
    const symbol = descriptor(object, Symbol.toStringTag);
    if (symbol && typeof symbol.value === "string") return symbol.value + ".prototype";
    return tag.call(object);
  }
  function chain(object) {
    const names = [], seen = new Set();
    for (let p = prototype(object); p !== null; p = prototype(p)) {
      if (seen.has(p)) throw new Error("Prototype cycle");
      seen.add(p);
      const name = className(p);
      names.push(name);
      if (!Object.hasOwn(result.chains, name)) result.chains[name] = describe(p);
    }
    return names;
  }
  function inspect(name, object, destination) {
    try { destination[name] = {...describe(object), chain: chain(object)}; }
    catch (e) { failure(name, e); }
  }
  result.metadata = {url: w.location.href, secureContext: w.isSecureContext,
    crossOriginIsolated: w.crossOriginIsolated, userAgent: w.navigator.userAgent,
    language: w.navigator.language};
  result.globals = describe(w);
  for (const name of own(w).filter(k => typeof k === "string").sort()) {
    try {
      const d = descriptor(w, name);
      if (!d || !("value" in d) || d.value === null) continue;
      const value = d.value;
      if (typeof value === "function") {
        inspect(name, value, result.interfaces);
        const p = descriptor(value, "prototype");
        if (p && p.value && typeof p.value === "object")
          inspect(name + ".prototype", p.value, result.interfaces);
      } else if (/^[A-Z]/.test(name) && typeof value === "object") {
        inspect(name, value, result.interfaces);
      }
    } catch (e) { failure("global:" + name, e); }
  }
  for (const name of ["navigator", "document", "location", "history", "screen", "performance",
       "crypto", "console", "localStorage", "sessionStorage", "customElements", "visualViewport"])
    try { if (w[name] != null) inspect(name, w[name], result.instances); }
    catch (e) { failure("instance:" + name, e); }
  inspect("window", w, result.instances);
  for (const name of ["documentElement", "head", "body"])
    if (w.document[name]) inspect("document." + name, w.document[name], result.instances);
  const tags = ("a abbr address area article aside audio b base bdi bdo blockquote body br button " +
    "canvas caption cite code col colgroup data datalist dd del details dfn dialog div dl dt em embed " +
    "fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 head header hgroup hr html i iframe img " +
    "input ins kbd label legend li link main map mark menu meta meter nav noscript object ol optgroup " +
    "option output p picture pre progress q rp rt ruby s samp script search section select slot small " +
    "source span strong style sub summary sup table tbody td template textarea tfoot th thead time " +
    "title tr track u ul var video wbr unknown").split(" ");
  for (const name of tags) {
    try { inspect("element:" + name, w.document.createElement(name), result.instances); }
    catch (e) { failure("element:" + name, e); }
  }
  for (const name of ["svg", "g", "path", "rect", "circle", "text", "use", "a", "foreignObject"])
    try { inspect("svg:" + name, w.document.createElementNS("http://www.w3.org/2000/svg", name),
                  result.instances); }
    catch (e) { failure("svg:" + name, e); }
  return result;
})
