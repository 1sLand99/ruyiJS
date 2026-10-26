(w => {
  const names = ['width', 'actualBoundingBoxLeft', 'actualBoundingBoxRight',
    'actualBoundingBoxAscent', 'actualBoundingBoxDescent', 'fontBoundingBoxAscent',
    'fontBoundingBoxDescent', 'emHeightAscent', 'emHeightDescent',
    'hangingBaseline', 'alphabeticBaseline', 'ideographicBaseline'];
  const result = {};
  for (const kind of ['canvas', 'offscreen']) {
    const canvas = kind === 'canvas' ? w.document.createElement('canvas') : new w.OffscreenCanvas(100, 80);
    const context = canvas.getContext('2d');
    for (const font of ['16px Arial', '13.5px "Times New Roman"']) {
      context.font = font;
      for (const baseline of ['alphabetic', 'top', 'hanging', 'middle', 'ideographic', 'bottom']) {
        context.textBaseline = baseline;
        for (const text of ['Hello', '']) {
          const m = context.measureText(text);
          result[[kind, font, baseline, text].join('|')] = names.map(n => m[n]);
        }
      }
      context.textBaseline = 'alphabetic';
      for (const direction of ['ltr', 'rtl']) {
        context.direction = direction;
        for (const align of ['left', 'right', 'center', 'start', 'end']) {
          context.textAlign = align;
          const m = context.measureText('Hello');
          result[[kind, font, direction, align].join('|')] = names.map(n => m[n]);
        }
      }
      context.textAlign = 'start'; context.direction = 'ltr';
    }
    const metric = context.measureText('x');
    const descriptor = w.Object.getOwnPropertyDescriptor(w.TextMetrics.prototype, 'hangingBaseline');
    let invalid;
    try { descriptor.get.call({}); } catch (error) { invalid = error.name; }
    result[kind + '|identity'] = [w.Object.getPrototypeOf(metric) === w.TextMetrics.prototype,
      metric instanceof w.TextMetrics, descriptor.enumerable, descriptor.configurable,
      typeof descriptor.set, invalid];
  }
  return result;
})
