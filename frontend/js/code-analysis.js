// code analysis page
// all numbers are saved from test runs, nothing runs live

const FAN = {"calm":{"hist":[109.33,110.1,112.84,112.21,113.14,114.01,114.49,114.85,115.17,114.14,112.41,111.75,112.74,115.33,117.03,118.89,120.29,121.56,121.89,123.31,126.63,126.01,124.71,128.43,128.9,130.79,132.52,130.28,135.12,138.77,139.14,140.72,140.99,139.13,138.9,139.68,142.04,143.55,143.68,146.63,144.97,146.7,149.17,148.52,144.58,142.63,143.14,144.28,147.67,145.46,145.46,146.89,146.54,141.42,143.14,148.19,150.44,148.39,147.47,147.96],"mid":[149.47,152.12,153.95,152.32,153.75,155.78,154.57,155.86,155.21,154.59,154.65,154.93,153.54,153.27,153.23,153.89,154.68,151.89,149.77,149.08,149.25,148.51,149.51,149.4,151.11,153.31,152.36,151.81,152.94,153.2],"lo":[146.74,148.21,149.12,146.81,147.55,148.91,147.21,147.95,146.87,145.85,145.49,145.35,143.67,143.06,142.68,142.96,143.37,140.48,138.22,137.29,137.17,136.22,136.87,136.51,137.82,139.56,138.46,137.72,138.49,138.5],"hi":[152.24,156.14,158.94,158.03,160.21,162.97,162.28,164.2,164.03,163.86,164.39,165.13,164.08,164.2,164.56,165.65,166.88,164.24,162.29,161.88,162.39,161.91,163.31,163.51,165.69,168.4,167.66,167.35,168.88,169.46],"actual":[153.59,155.02,155.29,158.96,158.76,163.26,161.59,160.44,162.19,165.69,167.32,168.08,163.55,161.81,160.34,159.06,160.46,159.66,161.56,161.75,160.95,161.23,162.28,164.38,163.2,162.64,159.34,163.22,166.82,166.37],"inside":23,"steps":30},"shock":{"hist":[109.33,110.1,112.84,112.21,113.14,114.01,114.49,114.85,115.17,114.14,112.41,111.75,112.74,115.33,117.03,118.89,120.29,121.56,121.89,123.31,126.63,126.01,124.71,128.43,128.9,130.79,132.52,130.28,135.12,138.77,139.14,140.72,140.99,139.13,138.9,139.68,142.04,143.55,143.68,146.63,144.97,146.7,149.17,148.52,144.58,142.63,143.14,144.28,147.67,145.46,145.46,146.89,146.54,141.42,143.14,148.19,150.44,148.39,147.47,147.96],"mid":[149.47,152.12,153.95,152.32,153.75,155.78,154.57,155.86,155.21,154.59,154.65,154.93,153.54,153.27,153.23,153.89,154.68,151.89,149.77,149.08,149.25,148.51,149.51,149.4,151.11,153.31,152.36,151.81,152.94,153.2],"lo":[146.74,148.21,149.12,146.81,147.55,148.91,147.21,147.95,146.87,145.85,145.49,145.35,143.67,143.06,142.68,142.96,143.37,140.48,138.22,137.29,137.17,136.22,136.87,136.51,137.82,139.56,138.46,137.72,138.49,138.5],"hi":[152.24,156.14,158.94,158.03,160.21,162.97,162.28,164.2,164.03,163.86,164.39,165.13,164.08,164.2,164.56,165.65,166.88,164.24,162.29,161.88,162.39,161.91,163.31,163.51,165.69,168.4,167.66,167.35,168.88,169.46],"actual":[165.5,170.16,171.04,183.45,182.78,198.75,192.72,188.64,194.86,207.76,213.97,216.89,199.82,193.51,188.27,183.8,188.71,185.89,192.6,193.31,190.44,191.45,195.18,202.87,198.55,196.49,184.79,198.62,212.03,210.33],"inside":0,"steps":30}};

// make an svg thing
function el(tag, attrs, parent) {
  const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}

function text(parent, x, y, str, opts) {
  opts = opts || {};
  const t = el('text', {
    x: x, y: y,
    'text-anchor': opts.anchor || 'middle',
    style: 'fill:' + (opts.fill || 'var(--muted)') + ';font-size:' + (opts.size || 11) + 'px;' + (opts.bold ? 'font-weight:600;' : '')
  }, parent);
  t.textContent = str;
  return t;
}

// title, svg and legend go in a box
function startChart(box, title, legend) {
  box.innerHTML = '';
  const h = document.createElement('h3');
  h.textContent = title;
  box.appendChild(h);
  const svg = el('svg', { viewBox: '0 0 640 270', width: '100%', role: 'img', 'aria-label': title });
  svg.style.maxWidth = '100%';
  svg.style.height = 'auto';
  box.appendChild(svg);
  if (legend && legend.length) {
    const lg = document.createElement('div');
    lg.className = 'legend small muted';
    legend.forEach(function (l) {
      const s = document.createElement('span');
      s.innerHTML = '<i style="background:' + l[1] + '"></i>' + l[0];
      lg.appendChild(s);
    });
    box.appendChild(lg);
  }
  return svg;
}

// bar chart
// cfg has title, labels, series, max, unit, ref
function barChart(box, cfg) {
  const svg = startChart(box, cfg.title, cfg.series.length > 1 ? cfg.series.map(function (s) { return [s.name, s.color]; }) : null);
  const L = 44, R = 12, T = 14, B = 54, W = 640, H = 270;
  const iw = W - L - R, ih = H - T - B;
  const max = cfg.max;
  const y = function (v) { return T + ih - (v / max) * ih; };

  // lines in the back
  const steps = cfg.steps || 4;
  for (let i = 0; i <= steps; i++) {
    const v = (max / steps) * i;
    el('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), style: 'stroke:var(--line);stroke-width:1' }, svg);
    text(svg, L - 6, y(v) + 4, Math.round(v) + (cfg.unit || ''), { anchor: 'end' });
  }

  const n = cfg.labels.length, ns = cfg.series.length;
  const gw = iw / n;
  const bw = Math.min(46, (gw * 0.7) / ns);
  cfg.labels.forEach(function (lab, i) {
    const gx = L + gw * i + gw / 2;
    cfg.series.forEach(function (s, j) {
      const v = s.values[i];
      const x = gx - (bw * ns) / 2 + bw * j;
      const top = y(v);
      el('rect', { x: x + 1, y: top, width: bw - 2, height: Math.max(0, T + ih - top), rx: 2, style: 'fill:' + s.color }, svg);
      text(svg, x + bw / 2, top - 4, (cfg.decimals ? v.toFixed(cfg.decimals) : Math.round(v * 10) / 10) + (cfg.unit || ''), { size: 10, fill: 'var(--text)' });
    });
    // label can have line breaks
    lab.split('\n').forEach(function (part, k) {
      text(svg, gx, H - B + 16 + k * 13, part);
    });
  });

  // dashed line like promised 80%
  if (cfg.ref) {
    el('line', { x1: L, x2: W - R, y1: y(cfg.ref.value), y2: y(cfg.ref.value), style: 'stroke:var(--down);stroke-width:1.5;stroke-dasharray:5 4' }, svg);
    text(svg, W - R, y(cfg.ref.value) - 5, cfg.ref.label, { anchor: 'end', fill: 'var(--down)', size: 11 });
  }
  el('line', { x1: L, x2: W - R, y1: T + ih, y2: T + ih, style: 'stroke:var(--muted);stroke-width:1' }, svg);
}

// price line, forecast, shaded range, real stuff
function fanChart(box, d, title) {
  const svg = startChart(box, title, [
    ['past price', 'var(--text)'], ['forecast', 'var(--accent)'], ['range it promised', 'var(--good-line)'], ['what really happened', 'var(--down)']
  ]);
  const L = 44, R = 12, T = 14, B = 28, W = 640, H = 270;
  const iw = W - L - R, ih = H - T - B;
  const nh = d.hist.length, nf = d.mid.length;
  const total = nh + nf - 1;
  const all = d.hist.concat(d.lo, d.hi, d.actual);
  let mn = Math.min.apply(null, all), mx = Math.max.apply(null, all);
  const pad = (mx - mn) * 0.06;
  mn -= pad; mx += pad;
  const x = function (i) { return L + (i / total) * iw; };
  const y = function (v) { return T + ih - ((v - mn) / (mx - mn)) * ih; };

  for (let i = 0; i <= 4; i++) {
    const v = mn + ((mx - mn) / 4) * i;
    el('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), style: 'stroke:var(--line);stroke-width:1' }, svg);
    text(svg, L - 6, y(v) + 4, Math.round(v), { anchor: 'end' });
  }

  // shaded part, top edge then bottom edge
  const last = nh - 1;
  let pts = x(last) + ',' + y(d.hist[last]);
  d.hi.forEach(function (v, i) { pts += ' ' + x(last + 1 + i) + ',' + y(v); });
  for (let i = nf - 1; i >= 0; i--) pts += ' ' + x(last + 1 + i) + ',' + y(d.lo[i]);
  el('polygon', { points: pts, style: 'fill:var(--accent);opacity:0.2' }, svg);

  const line = function (arr, startIdx, startVal, style) {
    let p = '';
    if (startVal !== null) p += x(startIdx - 1) + ',' + y(startVal) + ' ';
    arr.forEach(function (v, i) { p += x(startIdx + i) + ',' + y(v) + ' '; });
    el('polyline', { points: p.trim(), style: 'fill:none;' + style }, svg);
  };
  line(d.hist, 0, null, 'stroke:var(--text);stroke-width:1.6');
  line(d.mid, nh, d.hist[last], 'stroke:var(--accent);stroke-width:2;stroke-dasharray:6 4');
  line(d.actual, nh, d.hist[last], 'stroke:var(--down);stroke-width:1.8');

  // line between past and future
  el('line', { x1: x(last), x2: x(last), y1: T, y2: T + ih, style: 'stroke:var(--muted);stroke-width:1;stroke-dasharray:2 3' }, svg);
  text(svg, x(last) - 6, T + 12, 'past', { anchor: 'end' });
  text(svg, x(last) + 6, T + 12, 'future', { anchor: 'start' });
  text(svg, W - R, H - 8, d.inside + ' of ' + d.steps + ' real days inside the range', { anchor: 'end', fill: 'var(--text)', size: 12, bold: true });
}

function drawAll() {
  // headline accuracy
  barChart(document.getElementById('chartAcc'), {
    title: 'Headline test: overall accuracy (63 headlines)',
    labels: ['Always guess\nbiggest group', 'Keyword scorer,\nno context rules', 'Keyword scorer,\nwith context rules'],
    series: [{ name: 'accuracy', color: 'var(--accent)', values: [31.7, 79.4, 87.3] }],
    max: 100, unit: '%', steps: 4
  });

  // precision and recall
  barChart(document.getElementById('chartPR'), {
    title: 'Headline test: precision and recall by kind of headline',
    labels: ['Good', 'Bad', 'Routine', 'Not about\nthe business'],
    series: [
      { name: 'precision (when it said this, how often it was right)', color: 'var(--accent)', values: [90.5, 94.7, 72.2, 100] },
      { name: 'recall (how many of the real ones it found)', color: 'var(--muted)', values: [95, 90, 86.7, 62.5] }
    ],
    max: 100, unit: '%', steps: 4
  });

  // mood number vs how many headlines
  barChart(document.getElementById('chartCombine'), {
    title: 'Mood score for piles of identical very positive headlines',
    labels: ['1 headline', '3 headlines', '10 headlines', '20 headlines', '10 good +\n1 scandal'],
    series: [{ name: 'mood score', color: 'var(--accent)', values: [0.469, 0.726, 0.898, 0.946, 0.489] }],
    max: 1, unit: '', steps: 5, decimals: 2
  });

  // does the range hit 80
  barChart(document.getElementById('chartBand'), {
    title: 'Simulated stocks: how often the real price landed in the 80% range (last day)',
    labels: ['Normal\nmoves', 'Fat-tailed\nmoves', 'Volatility\nshock', 'Good news\n(noise)', 'Bad news\n(noise)'],
    series: [{ name: 'hit rate', color: 'var(--accent)', values: [80.4, 79.1, 41.7, 71.7, 69.2] }],
    max: 100, unit: '%', steps: 4, ref: { value: 80, label: 'promised 80%' }
  });

  // direction, should be about 50
  barChart(document.getElementById('chartDir'), {
    title: 'Simulated stocks: how often the forecast got the direction right',
    labels: ['Normal\nmoves', 'Fat-tailed\nmoves', 'Volatility\nshock', 'Good news\n(noise)', 'Bad news\n(noise)'],
    series: [{ name: 'direction right', color: 'var(--muted)', values: [49.3, 51.6, 49.3, 50.6, 49.4] }],
    max: 100, unit: '%', steps: 4, ref: { value: 50, label: 'coin flip 50%' }
  });

  fanChart(document.getElementById('fanCalm'), FAN.calm, 'Future as calm as the past');
  fanChart(document.getElementById('fanShock'), FAN.shock, 'Future 3x as jumpy as the past');
}

// colors use css vars so nothing to redraw
window.addEventListener('themechange', function () {});

initShell('code-analysis').then(drawAll);
