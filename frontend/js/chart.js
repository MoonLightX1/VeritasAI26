// stock chart on a canvas, no libraries
// shapes are saved as (time, price) so they stay put when you zoom

class StockChart {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.data = [];
    this.realN = 0; // real points, the rest are predicted
    this.pred = [];
    this.intraday = false;
    this.tz = 'UTC'; // exchange timezone
    this.v0 = 0; // first visible index
    this.v1 = 1; // last visible index
    this.tool = 'none';
    this.color = '#5b6cd6';
    this.shapes = [];
    this.undoStack = [];
    this.redoStack = [];
    this.draft = null;
    this.hover = null;
    this.pan = null;
    this.erasing = false;
    this.onChange = function () {};
    this.pad = { l: 10, r: 64, t: 12, b: 26 };
    this.volFrac = 0.18;

    this.resize = this.resize.bind(this);
    window.addEventListener('resize', this.resize);
    // redraw on theme change
    window.addEventListener('themechange', () => this.draw());
    this.bind();
    this.resize();
  }

  // data

  setData(points, intraday, tz) {
    this.pred = [];
    this.realN = points.length;
    this.data = points;
    this.intraday = intraday;
    this.tz = intraday ? (tz || 'America/New_York') : 'UTC';
    this.v0 = 0;
    this.v1 = Math.max(1, points.length - 1);
    this.hover = null;
    this.draw();
  }

  // new data, keep the zoom
  refreshData(points) {
    const old = this.data.length;
    const atEnd = this.v1 >= old - 1.5;
    const width = this.v1 - this.v0;
    // keep predicted part minus what real prices caught up to
    const lastT = points.length ? points[points.length - 1].t : 0;
    this.pred = this.pred.filter(function (p) { return p.t > lastT; });
    this.realN = points.length;
    this.data = points.concat(this.pred);
    if (!old || points.length < 2) { this.v0 = 0; this.v1 = Math.max(1, this.data.length - 1); }
    else if (atEnd) {
      // stick to the newest point
      this.v1 = this.data.length - 1;
      this.v0 = Math.max(0, this.v1 - width);
    }
    this.draw();
  }

  // predicted points [{t, c, lo, hi}], dashed line and shaded range
  setPrediction(future) {
    this.pred = future.map(function (f) { return { t: f.t, c: f.c, lo: f.lo, hi: f.hi, v: 0, p: true }; });
    this.data = this.data.slice(0, this.realN).concat(this.pred);
    this.v0 = 0;
    this.v1 = Math.max(1, this.data.length - 1);
    this.hover = null;
    this.draw();
  }

  // back to the actual graph
  clearPrediction() {
    if (!this.pred.length) return;
    this.pred = [];
    this.data = this.data.slice(0, this.realN);
    this.v0 = 0;
    this.v1 = Math.max(1, this.data.length - 1);
    this.hover = null;
    this.draw();
  }

  setShapes(shapes) {
    this.shapes = shapes || [];
    this.undoStack = [];
    this.redoStack = [];
    this.draw();
  }

  setTool(t) {
    this.tool = t;
    this.draft = null;
    this.canvas.style.cursor = t === 'none' ? 'crosshair' : (t === 'eraser' ? 'cell' : 'crosshair');
  }

  // layout

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = w;
    this.h = h;
    this.draw();
  }

  get pw() { return this.w - this.pad.l - this.pad.r; }
  get plotBottom() { return this.h - this.pad.b; }
  get priceBottom() { return this.plotBottom - (this.plotBottom - this.pad.t) * this.volFrac - 6; }

  // index <-> time
  timeToIdx(t) {
    const d = this.data;
    const n = d.length;
    if (n < 2) return 0;
    if (t <= d[0].t) return (t - d[0].t) / (d[1].t - d[0].t);
    if (t >= d[n - 1].t) return n - 1 + (t - d[n - 1].t) / (d[n - 1].t - d[n - 2].t);
    let lo = 0, hi = n - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (d[mid].t <= t) lo = mid; else hi = mid;
    }
    return lo + (t - d[lo].t) / (d[hi].t - d[lo].t);
  }

  idxToTime(i) {
    const d = this.data;
    const n = d.length;
    if (n < 2) return 0;
    if (i <= 0) return d[0].t + i * (d[1].t - d[0].t);
    if (i >= n - 1) return d[n - 1].t + (i - (n - 1)) * (d[n - 1].t - d[n - 2].t);
    const lo = Math.floor(i);
    return d[lo].t + (i - lo) * (d[lo + 1].t - d[lo].t);
  }

  xOfIdx(i) { return this.pad.l + ((i - this.v0) / (this.v1 - this.v0)) * this.pw; }
  idxOfX(x) { return this.v0 + ((x - this.pad.l) / this.pw) * (this.v1 - this.v0); }
  xOfTime(t) { return this.xOfIdx(this.timeToIdx(t)); }
  yOfPrice(p) { return this.pad.t + ((this.pmax - p) / (this.pmax - this.pmin)) * (this.priceBottom - this.pad.t); }
  priceOfY(y) { return this.pmax - ((y - this.pad.t) / (this.priceBottom - this.pad.t)) * (this.pmax - this.pmin); }

  toPx(pt) { return [this.xOfTime(pt[0]), this.yOfPrice(pt[1])]; }
  fromPx(x, y) { return [this.idxToTime(this.idxOfX(x)), this.priceOfY(y)]; }

  visibleRange() {
    const n = this.data.length;
    const a = Math.max(0, Math.floor(this.v0));
    const b = Math.min(n - 1, Math.ceil(this.v1));
    return [a, b];
  }

  computeScale() {
    const r = this.visibleRange();
    let min = Infinity, max = -Infinity, vmax = 0;
    for (let i = r[0]; i <= r[1]; i++) {
      const p = this.data[i];
      const lo = p.p ? p.lo : p.c, hi = p.p ? p.hi : p.c;
      if (lo < min) min = lo;
      if (hi > max) max = hi;
      if (p.v > vmax) vmax = p.v;
    }
    if (!isFinite(min)) { min = 0; max = 1; }
    if (min === max) { min -= 1; max += 1; }
    const padding = (max - min) * 0.08;
    this.pmin = min - padding;
    this.pmax = max + padding;
    this.vmax = vmax || 1;
  }

  // drawing

  fmtTime(t, full) {
    const d = new Date(t);
    const opts = { timeZone: this.tz };
    if (this.intraday) {
      if (full) return d.toLocaleString('en-US', Object.assign({ month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }, opts));
      return d.toLocaleString('en-US', Object.assign({ month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }, opts));
    }
    return d.toLocaleDateString('en-US', Object.assign({ month: 'short', day: 'numeric', year: 'numeric' }, opts));
  }

  // theme colors from css
  colors() {
    const css = getComputedStyle(document.documentElement);
    const get = (n, d) => css.getPropertyValue(n).trim() || d;
    return {
      text: get('--text', '#1d1d1b'),
      muted: get('--muted', '#77746a'),
      line: get('--line', '#d8d3c4'),
      card: get('--card', '#ffffff'),
      up: get('--up', '#2e7d4f'),
      down: get('--down', '#b8392e')
    };
  }

  draw() {
    const ctx = this.ctx;
    if (!this.w) return;
    this.c = this.colors();
    ctx.clearRect(0, 0, this.w, this.h);
    if (this.data.length < 2) return;
    this.computeScale();

    this.drawGrid();
    this.drawVolume();
    this.drawLine();
    this.drawPrediction();
    this.drawShapes();
    this.drawHover();
  }

  drawGrid() {
    const ctx = this.ctx;
    ctx.font = '11px "Inter Variable", system-ui, sans-serif';
    ctx.fillStyle = this.c.muted;
    ctx.strokeStyle = this.c.line;
    ctx.lineWidth = 1;
    ctx.textAlign = 'left';
    // price lines
    for (let i = 0; i <= 5; i++) {
      const p = this.pmin + ((this.pmax - this.pmin) * i) / 5;
      const y = this.yOfPrice(p);
      ctx.beginPath();
      ctx.moveTo(this.pad.l, y);
      ctx.lineTo(this.w - this.pad.r, y);
      ctx.stroke();
      ctx.fillText(p.toFixed(2), this.w - this.pad.r + 6, y + 4);
    }
    // time labels
    ctx.textAlign = 'center';
    const n = Math.max(2, Math.floor(this.pw / 110));
    for (let i = 0; i <= n; i++) {
      const idx = this.v0 + ((this.v1 - this.v0) * i) / n;
      const x = this.xOfIdx(idx);
      const t = this.idxToTime(idx);
      const d = new Date(t);
      let label;
      if (this.intraday) {
        label = d.toLocaleString('en-US', { timeZone: this.tz, month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
      } else if (this.v1 - this.v0 > 600) {
        label = d.toLocaleDateString('en-US', { timeZone: 'UTC', month: 'short', year: 'numeric' });
      } else {
        label = d.toLocaleDateString('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' });
      }
      let tx = x;
      if (i === 0) { ctx.textAlign = 'left'; tx = this.pad.l; }
      else if (i === n) { ctx.textAlign = 'right'; tx = this.w - this.pad.r; }
      else ctx.textAlign = 'center';
      ctx.fillText(label, tx, this.h - 8);
    }
    ctx.textAlign = 'left';
  }

  drawVolume() {
    const ctx = this.ctx;
    const r = this.visibleRange();
    const base = this.plotBottom;
    const maxH = (this.plotBottom - this.pad.t) * this.volFrac;
    const barW = Math.max(1, (this.pw / (this.v1 - this.v0)) * 0.7);
    ctx.fillStyle = this.c.muted;
    ctx.globalAlpha = 0.25;
    for (let i = r[0]; i <= r[1]; i++) {
      const x = this.xOfIdx(i);
      if (x < this.pad.l - 2 || x > this.w - this.pad.r + 2) continue;
      const h = (this.data[i].v / this.vmax) * maxH;
      ctx.fillRect(x - barW / 2, base - h, barW, h);
    }
    ctx.globalAlpha = 1;
  }

  drawLine() {
    const ctx = this.ctx;
    const r = this.visibleRange();
    // color and solid line use real prices only
    const realEnd = Math.min(r[1], this.realN - 1);
    if (realEnd < r[0]) return;
    const first = this.data[r[0]].c;
    const last = this.data[realEnd].c;
    const up = last >= first;
    const col = up ? this.c.up : this.c.down;

    ctx.save();
    ctx.beginPath();
    ctx.rect(this.pad.l, 0, this.pw, this.h);
    ctx.clip();

    const start = Math.max(0, r[0] - 1);
    const end = Math.min(this.realN - 1, r[1] + 1);

    ctx.beginPath();
    for (let i = start; i <= end; i++) {
      const x = this.xOfIdx(i), y = this.yOfPrice(this.data[i].c);
      if (i === start) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = col;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    ctx.stroke();
    ctx.restore();
  }

  drawPrediction() {
    if (!this.pred.length) return;
    const ctx = this.ctx;
    const a = this.realN - 1; // last real point
    const b = this.data.length - 1;
    const startC = this.data[a].c;
    const endC = this.data[b].c;
    const col = endC >= startC ? this.c.up : this.c.down;

    ctx.save();
    ctx.beginPath();
    ctx.rect(this.pad.l, 0, this.pw, this.h);
    ctx.clip();

    // shaded range, fans out
    ctx.beginPath();
    ctx.moveTo(this.xOfIdx(a), this.yOfPrice(startC));
    for (let i = a + 1; i <= b; i++) ctx.lineTo(this.xOfIdx(i), this.yOfPrice(this.data[i].hi));
    for (let i = b; i > a; i--) ctx.lineTo(this.xOfIdx(i), this.yOfPrice(this.data[i].lo));
    ctx.closePath();
    ctx.fillStyle = this.rgba(col, 0.14);
    ctx.fill();

    // divider between real and predicted
    const nx = this.xOfIdx(a);
    ctx.strokeStyle = this.c.muted;
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 4]);
    ctx.beginPath();
    ctx.moveTo(nx, this.pad.t);
    ctx.lineTo(nx, this.plotBottom);
    ctx.stroke();

    // dashed predicted line
    ctx.setLineDash([7, 5]);
    ctx.beginPath();
    for (let i = a; i <= b; i++) {
      const x = this.xOfIdx(i), y = this.yOfPrice(this.data[i].c);
      if (i === a) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = col;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = this.c.muted;
    ctx.font = '11px "Inter Variable", system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('Predicted', Math.min(nx + 6, this.w - this.pad.r - 60), this.pad.t + 12);
    ctx.restore();
  }

  drawHover() {
    if (!this.hover || this.tool !== 'none' || this.pan) return;
    const ctx = this.ctx;
    const idx = Math.round(this.idxOfX(this.hover.x));
    if (idx < 0 || idx >= this.data.length) return;
    const p = this.data[idx];
    const x = this.xOfIdx(idx);
    const y = this.yOfPrice(p.c);
    if (x < this.pad.l || x > this.w - this.pad.r) return;

    ctx.save();
    ctx.strokeStyle = this.c.muted;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(x, this.pad.t);
    ctx.lineTo(x, this.plotBottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = this.c.card;
    ctx.strokeStyle = this.c.text;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    const lines = p.p
      ? [this.fmtTime(p.t, true), 'Predicted: $' + p.c.toFixed(2), 'Likely: $' + p.lo.toFixed(2) + ' - $' + p.hi.toFixed(2)]
      : [this.fmtTime(p.t, true), 'Price: $' + p.c.toFixed(2), 'Volume: ' + p.v.toLocaleString('en-US')];
    ctx.font = '12px "Inter Variable", system-ui, sans-serif';
    let bw = 0;
    lines.forEach(function (l) { bw = Math.max(bw, ctx.measureText(l).width); });
    bw += 16;
    const bh = lines.length * 16 + 10;
    let bx = x + 12;
    if (bx + bw > this.w - this.pad.r) bx = x - bw - 12;
    let by = Math.max(this.pad.t, Math.min(y - bh / 2, this.plotBottom - bh));
    ctx.fillStyle = this.c.text;
    ctx.fillRect(bx, by, bw, bh);
    ctx.fillStyle = this.c.card;
    ctx.textAlign = 'left';
    lines.forEach(function (l, i) { ctx.fillText(l, bx + 8, by + 18 + i * 16); });
    ctx.restore();
  }

  // #rrggbb to rgba
  rgba(hex, a) {
    const h = hex.replace('#', '');
    const n = parseInt(h.length === 3 ? h.split('').map(function (x) { return x + x; }).join('') : h, 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }

  // save as png
  toPNG(title, subtitle, filename) {
    this.hover = null;
    this.draw();
    const src = this.canvas;
    const dpr = src.width / this.w;
    const head = 54 * dpr;
    const foot = 28 * dpr;
    const out = document.createElement('canvas');
    out.width = src.width;
    out.height = src.height + head + foot;
    const o = out.getContext('2d');
    o.fillStyle = this.c.card;
    o.fillRect(0, 0, out.width, out.height);
    o.textBaseline = 'alphabetic';
    o.fillStyle = this.c.text;
    o.font = 'bold ' + 20 * dpr + 'px "Inter Variable", system-ui, sans-serif';
    o.fillText(title, 14 * dpr, 28 * dpr);
    o.fillStyle = this.c.muted;
    o.font = 13 * dpr + 'px "Inter Variable", system-ui, sans-serif';
    o.fillText(subtitle, 14 * dpr, 46 * dpr);
    o.drawImage(src, 0, head);
    o.fillStyle = this.c.muted;
    o.font = 11 * dpr + 'px "Inter Variable", system-ui, sans-serif';
    o.fillText('MoneySprout, data from Yahoo Finance, may be delayed. Demo only.', 14 * dpr, out.height - 10 * dpr);
    out.toBlob(function (blob) {
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    }, 'image/png');
  }

  // shapes

  drawShapes() {
    const ctx = this.ctx;
    ctx.save();
    ctx.beginPath();
    ctx.rect(this.pad.l, 0, this.pw, this.plotBottom);
    ctx.clip();
    const all = this.shapes.slice();
    if (this.draft) all.push(this.draft);
    for (let i = 0; i < all.length; i++) this.drawShape(all[i]);
    ctx.restore();
  }

  drawShape(s) {
    const ctx = this.ctx;
    ctx.strokeStyle = s.color;
    ctx.fillStyle = s.color;
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.setLineDash([]);
    if (s.type === 'pen') {
      ctx.beginPath();
      s.pts.forEach((pt, i) => {
        const p = this.toPx(pt);
        if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
      });
      ctx.stroke();
    } else if (s.type === 'line' || s.type === 'arrow') {
      const a = this.toPx(s.a), b = this.toPx(s.b);
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.stroke();
      if (s.type === 'arrow') {
        const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
        const len = 12;
        ctx.beginPath();
        ctx.moveTo(b[0], b[1]);
        ctx.lineTo(b[0] - len * Math.cos(ang - 0.45), b[1] - len * Math.sin(ang - 0.45));
        ctx.lineTo(b[0] - len * Math.cos(ang + 0.45), b[1] - len * Math.sin(ang + 0.45));
        ctx.closePath();
        ctx.fill();
      }
    } else if (s.type === 'hline') {
      const y = this.yOfPrice(s.p);
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(this.pad.l, y);
      ctx.lineTo(this.w - this.pad.r, y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = '11px "Inter Variable", system-ui, sans-serif';
      ctx.fillText('$' + s.p.toFixed(2), this.pad.l + 4, y - 4);
    } else if (s.type === 'vline') {
      const x = this.xOfTime(s.t);
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(x, this.pad.t);
      ctx.lineTo(x, this.plotBottom);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = '11px "Inter Variable", system-ui, sans-serif';
      ctx.save();
      ctx.translate(x + 4, this.pad.t + 6);
      ctx.fillText(this.fmtTime(s.t), 0, 10);
      ctx.restore();
    } else if (s.type === 'rect') {
      const a = this.toPx(s.a), b = this.toPx(s.b);
      ctx.strokeRect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
    } else if (s.type === 'circle') {
      const a = this.toPx(s.a), b = this.toPx(s.b);
      const r = Math.hypot(b[0] - a[0], b[1] - a[1]);
      ctx.beginPath();
      ctx.arc(a[0], a[1], r, 0, Math.PI * 2);
      ctx.stroke();
    } else if (s.type === 'text') {
      const a = this.toPx(s.a);
      ctx.font = 'bold 14px "Inter Variable", system-ui, sans-serif';
      ctx.fillText(s.text, a[0], a[1]);
    }
  }

  // distance to a shape, for the eraser
  hitDistance(s, x, y) {
    const segDist = function (ax, ay, bx, by) {
      const dx = bx - ax, dy = by - ay;
      const len2 = dx * dx + dy * dy;
      let t = len2 ? ((x - ax) * dx + (y - ay) * dy) / len2 : 0;
      t = Math.max(0, Math.min(1, t));
      return Math.hypot(x - (ax + t * dx), y - (ay + t * dy));
    };
    if (s.type === 'pen') {
      let best = Infinity;
      for (let i = 1; i < s.pts.length; i++) {
        const a = this.toPx(s.pts[i - 1]), b = this.toPx(s.pts[i]);
        best = Math.min(best, segDist(a[0], a[1], b[0], b[1]));
      }
      return best;
    }
    if (s.type === 'line' || s.type === 'arrow') {
      const a = this.toPx(s.a), b = this.toPx(s.b);
      return segDist(a[0], a[1], b[0], b[1]);
    }
    if (s.type === 'hline') return Math.abs(y - this.yOfPrice(s.p));
    if (s.type === 'vline') return Math.abs(x - this.xOfTime(s.t));
    if (s.type === 'rect') {
      const a = this.toPx(s.a), b = this.toPx(s.b);
      const x0 = Math.min(a[0], b[0]), x1 = Math.max(a[0], b[0]);
      const y0 = Math.min(a[1], b[1]), y1 = Math.max(a[1], b[1]);
      return Math.min(segDist(x0, y0, x1, y0), segDist(x1, y0, x1, y1), segDist(x1, y1, x0, y1), segDist(x0, y1, x0, y0));
    }
    if (s.type === 'circle') {
      const a = this.toPx(s.a), b = this.toPx(s.b);
      const r = Math.hypot(b[0] - a[0], b[1] - a[1]);
      return Math.abs(Math.hypot(x - a[0], y - a[1]) - r);
    }
    if (s.type === 'text') {
      const a = this.toPx(s.a);
      const w = this.ctx.measureText(s.text).width;
      if (x >= a[0] && x <= a[0] + w && y >= a[1] - 14 && y <= a[1] + 4) return 0;
      return Infinity;
    }
    return Infinity;
  }

  eraseAt(x, y) {
    for (let i = this.shapes.length - 1; i >= 0; i--) {
      if (this.hitDistance(this.shapes[i], x, y) < 8) {
        this.shapes.splice(i, 1);
        this.onChange();
        this.draw();
        return true;
      }
    }
    return false;
  }

  // undo / redo

  snapshot() {
    this.undoStack.push(JSON.stringify(this.shapes));
    if (this.undoStack.length > 100) this.undoStack.shift();
    this.redoStack = [];
  }

  undo() {
    if (!this.undoStack.length) return;
    this.redoStack.push(JSON.stringify(this.shapes));
    this.shapes = JSON.parse(this.undoStack.pop());
    this.onChange();
    this.draw();
  }

  redo() {
    if (!this.redoStack.length) return;
    this.undoStack.push(JSON.stringify(this.shapes));
    this.shapes = JSON.parse(this.redoStack.pop());
    this.onChange();
    this.draw();
  }

  clearShapes() {
    if (!this.shapes.length) return;
    this.snapshot();
    this.shapes = [];
    this.onChange();
    this.draw();
  }

  // zoom and pan

  zoom(factor, anchorX) {
    const n = this.data.length;
    if (n < 3) return;
    const anchorIdx = anchorX === undefined ? (this.v0 + this.v1) / 2 : this.idxOfX(anchorX);
    let span = (this.v1 - this.v0) * factor;
    span = Math.max(6, Math.min(n - 1, span));
    const ratio = (anchorIdx - this.v0) / (this.v1 - this.v0);
    this.v0 = anchorIdx - span * ratio;
    this.v1 = this.v0 + span;
    this.clampView();
    this.draw();
  }

  resetZoom() {
    this.v0 = 0;
    this.v1 = Math.max(1, this.data.length - 1);
    this.draw();
  }

  clampView() {
    const n = this.data.length;
    const span = this.v1 - this.v0;
    if (this.v0 < 0) { this.v0 = 0; this.v1 = span; }
    if (this.v1 > n - 1) { this.v1 = n - 1; this.v0 = this.v1 - span; }
    if (this.v0 < 0) this.v0 = 0;
  }

  // mouse and touch

  pos(e) {
    const r = this.canvas.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  inPlot(x, y) {
    return x >= this.pad.l && x <= this.w - this.pad.r && y >= this.pad.t && y <= this.plotBottom;
  }

  bind() {
    const c = this.canvas;

    c.addEventListener('pointerdown', (e) => {
      const p = this.pos(e);
      if (!this.data.length || !this.inPlot(p[0], p[1])) return;
      c.setPointerCapture(e.pointerId);

      if (this.tool === 'none') {
        this.pan = { x: p[0], v0: this.v0, v1: this.v1 };
        c.style.cursor = 'grabbing';
        return;
      }
      if (this.tool === 'eraser') {
        this.snapshot();
        this.erasing = true;
        this.eraseAt(p[0], p[1]);
        return;
      }
      const pt = this.fromPx(p[0], p[1]);
      if (this.tool === 'text') {
        const txt = prompt('Type your note for the chart:');
        if (txt && txt.trim()) {
          this.snapshot();
          this.shapes.push({ type: 'text', a: pt, text: txt.trim().slice(0, 80), color: this.color });
          this.onChange();
          this.draw();
        }
        return;
      }
      if (this.tool === 'hline') {
        this.snapshot();
        this.shapes.push({ type: 'hline', p: pt[1], color: this.color });
        this.onChange();
        this.draw();
        return;
      }
      if (this.tool === 'vline') {
        this.snapshot();
        this.shapes.push({ type: 'vline', t: pt[0], color: this.color });
        this.onChange();
        this.draw();
        return;
      }
      if (this.tool === 'pen') {
        this.draft = { type: 'pen', pts: [pt], color: this.color };
      } else {
        this.draft = { type: this.tool, a: pt, b: pt, color: this.color };
      }
      this.draw();
    });

    c.addEventListener('pointermove', (e) => {
      const p = this.pos(e);
      this.hover = { x: p[0], y: p[1] };
      if (this.pan) {
        const dIdx = -((p[0] - this.pan.x) / this.pw) * (this.pan.v1 - this.pan.v0);
        this.v0 = this.pan.v0 + dIdx;
        this.v1 = this.pan.v1 + dIdx;
        this.clampView();
      } else if (this.erasing) {
        this.eraseAt(p[0], p[1]);
      } else if (this.draft) {
        const pt = this.fromPx(p[0], p[1]);
        if (this.draft.type === 'pen') this.draft.pts.push(pt);
        else this.draft.b = pt;
      }
      this.draw();
    });

    const finish = (e) => {
      if (this.pan) {
        this.pan = null;
        c.style.cursor = 'crosshair';
      }
      this.erasing = false;
      if (this.draft) {
        const d = this.draft;
        this.draft = null;
        let keep = true;
        if (d.type === 'pen') keep = d.pts.length > 2;
        else {
          const a = this.toPx(d.a), b = this.toPx(d.b);
          keep = Math.hypot(a[0] - b[0], a[1] - b[1]) > 4;
        }
        if (keep) {
          this.snapshot();
          this.shapes.push(d);
          this.onChange();
        }
      }
      this.draw();
    };
    c.addEventListener('pointerup', finish);
    c.addEventListener('pointercancel', finish);
    c.addEventListener('pointerleave', () => {
      this.hover = null;
      this.draw();
    });

    c.addEventListener('wheel', (e) => {
      if (!this.data.length) return;
      e.preventDefault();
      const p = this.pos(e);
      this.zoom(e.deltaY > 0 ? 1.18 : 1 / 1.18, p[0]);
    }, { passive: false });
  }
}
