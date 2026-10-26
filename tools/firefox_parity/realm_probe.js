(window => {
  const document = window.document;
  const element = document.createElement("div");
  const descriptor = Object.getOwnPropertyDescriptor(window.Element.prototype, "replaceChildren");
  return {
    lexicalWindow: globalThis === window,
    documentIdentity: document.defaultView === window,
    elementRealm: Object.getPrototypeOf(element) === window.HTMLDivElement.prototype,
    constructorRealm: Object.getPrototypeOf(window.Element) === window.Node,
    property: descriptor ? {enumerable: descriptor.enumerable,
      configurable: descriptor.configurable, writable: descriptor.writable,
      name: descriptor.value.name, length: descriptor.value.length} : null
  };
})
