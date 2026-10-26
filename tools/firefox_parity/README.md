# Firefox surface evidence

Run `python -B tools/firefox_parity/collect.py` to capture the current
`dist/js.exe` and a fresh, owned Firefox process. The default Firefox is
`D:/firefox/src/firefox/obj-jscall-check/dist/bin/firefox.exe`; override with
`--firefox PATH`. Each file is under 200 lines; these tools do not install APIs.

An independent profile and all evidence stay in a new project `artifacts/`
directory. The runner never attaches to an existing browser or user profile.
The profile maps `parity.test` to loopback with Firefox's DNS preference;
`http://parity.test:PORT` is the ordinary HTTP context and
`http://localhost:PORT` is the trustworthy secure context. Both have a same-origin
iframe. ruyijs receives the same HTML and URL via `load_page`, with the frame
response registered in its existing resource owner. No external requests are
needed by the fixture. Firefox startup can run its normal background services.

`surface.js` records all Window own property keys and descriptors, visible
constructor static/prototype descriptors and prototype chains, selected
platform instances, every listed HTML element factory, and selected SVG
factories. Reflection reads descriptors without invoking global getters;
only explicit instance factories and metadata accessors are evaluated.
Captured property lists include symbols. `metadata.json` includes Firefox
version/build ID/capabilities, executable SHA256, probe SHA256 and fixture HTML.
Each capture includes the visible UA, security flags and document URL.

The report distinguishes missing objects/properties, extra exposure,
descriptors, key order and prototype chains. Repeated instance/chain views are
not unique API counts. Presence does not validate API behavior, invalid
receivers, realm identity, permissions or event ordering. Secure-context-only
APIs need exposure checks as well as method implementation. Workers and
cross-origin documents are not covered by this collector.

For a focused behavior comparison, place a function expression in a JS file:

```javascript
(window => {
  const document = window.document;
  const element = document.createElement('div');
  element.replaceChildren('one', document.createElement('b'));
  return {text: element.textContent, html: element.innerHTML};
})
```

Run `python -B tools/firefox_parity/collect.py --probe PATH.js`.
The function is called with the target main/iframe window in both HTTP contexts.
Use that window's constructors and document for realm-sensitive checks.
The function must return a JSON-serializable value. Focused capture files wrap
the return value in `value`, with UA/URL/security flags alongside it.
The function executes through the target window's native `eval`, so its
ECMAScript intrinsics and lexical global belong to that realm.
Focused runs emit the eight captures and metadata, without a surface diff report.
