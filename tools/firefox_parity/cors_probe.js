(async function(scope, target, sameOrigin) {
  const cases = [
    ['same-origin', sameOrigin, 'explicit', 'omit'],
    ['cookie-prime', target, 'explicit', 'include'],
    ['same-origin-no-cors', sameOrigin, 'explicit', 'omit', 'no-cors'],
    ['explicit-list', target, 'explicit', 'omit'],
    ['cross-origin-no-cors', target, 'explicit', 'omit', 'no-cors'],
    ['multiline-case', target, 'multiline', 'omit'],
    ['no-expose', target, 'none', 'omit'],
    ['wildcard-omit', target, 'wildcard', 'omit'],
    ['wildcard-include', target, 'wildcard', 'include'],
    ['cookie-explicit-include', target, 'cookie-expose', 'include']
  ];
  const result = [];
  for (const [name, origin, variant, credentials, requestMode = 'cors'] of cases) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await scope.fetch(origin + '/resource?case=' + variant, {
        mode: requestMode, credentials, cache: 'no-store', signal:controller.signal
      });
      const clone = response.clone();
      const names = [...response.headers.keys()];
      const row = {
        name, type: response.type, status: response.status,
        url: response.url, redirected: response.redirected,
        names, cloneType: clone.type, cloneNames: [...clone.headers.keys()],
        responseBrand: Object.prototype.toString.call(response),
        responsePrototype: Object.getPrototypeOf(response) === scope.Response.prototype,
        cloneBrand: Object.prototype.toString.call(clone),
        clonePrototype: Object.getPrototypeOf(clone) === scope.Response.prototype,
        headersBrand: Object.prototype.toString.call(response.headers),
        headersPrototype: Object.getPrototypeOf(response.headers) === scope.Headers.prototype,
        cloneHeadersPrototype: Object.getPrototypeOf(clone.headers) === scope.Headers.prototype,
        hiddenValue: response.headers.get('x-hidden'),
        starValue: response.headers.get('*'),
        cookieValue: response.headers.get('set-cookie'),
        cookie2Value: response.headers.get('set-cookie2'),
        cookieSeen: response.headers.get('x-cookie-seen'),
        cookies: typeof response.headers.getSetCookie === 'function' ? response.headers.getSetCookie() : null,
        body: await response.text(), cloneBody: await clone.text()
      };
      try { response.headers.set('x-mutated', 'value'); row.headersMutation = 'allowed'; }
      catch (error) { row.headersMutation = error.name; }
      result.push(row);
    } catch (error) {
      result.push({name, error: error.name, message: error.message});
    } finally {
      clearTimeout(timeout);
    }
  }
  return result;
})
