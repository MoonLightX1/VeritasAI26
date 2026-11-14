// stock page: header, chart, drawing toolbar, buy and sell

const params = new URLSearchParams(location.search);
const TICKER = (params.get('t') || '').toUpperCase();
const RANGES = [['1D', '1D'], ['1W', '1W'], ['1M', '1M'], ['3M', '3M'],
  ['6M', '6M'], ['1Y', '1Y'], ['5Y', '5Y'], ['MAX', 'Max']];
const TOOLS = [['none', 'Cursor'], ['pen', 'Pencil'], ['line', 'Line'], ['hline', 'Price line'],
  ['vline', 'Date line'], ['arrow', 'Arrow'], ['rect', 'Rectangle'], ['circle', 'Circle'],
  ['text', 'Text'], ['eraser', 'Eraser']];

let chart = null;
let stock = null;
let range = '1Y';
let unsaved = false;
let loadToken = 0;
let view = 'actual';      // 'actual' or 'pred', which graph they are looking at
let predToken = 0;
let sumToken = 0;
const predCache = {};     // range -> { at, data }, so flipping back and forth is instant
const PRED_FRESH = 5 * 60 * 1000;

function buildRanges() {
  const box = document.getElementById('ranges');
  box.innerHTML = RANGES.map(function (r) {
    return '<button class="chip' + (r[0] === range ? ' on' : '') + '" data-r="' + r[0] + '">' + r[1] + '</button>';
  }).join('');
  box.onclick = function (e) {
    const r = e.target.dataset.r;
    if (!r || r === range) return;
    range = r;
    predToken++;
    buildRanges();
    loadHistory();
  };
}

function buildPredict() {
  const box = document.getElementById('predictBar');
  box.innerHTML =
    '<span class="seg">' +
    '<button class="chip' + (view === 'actual' ? ' on' : '') + '" data-v="actual">Actual</button>' +
    '<button class="chip' + (view === 'pred' ? ' on' : '') + '" data-v="pred">Predicted (news)</button>' +
    '</span><span class="muted small" id="predState"></span>';
  box.onclick = function (e) {
    const v = e.target.dataset.v;
    if (!v || v === view) return;
    setView(v);
  };
}

function setView(v) {
  view = v;
  predToken++;
  buildPredict();
  if (v === 'actual') {
    chart.clearPrediction();
    document.getElementById('predictInfo').classList.add('hidden');
    showSide(false);
  } else {
    loadPrediction();
  }
}

function showSide(on) {
  document.getElementById('aiSide').classList.toggle('hidden', !on);
  document.getElementById('chartLayout').classList.toggle('has-side', on);
  chart.resize();
}

// the side panel: why it looks this way, the AI's call, and the AI's summary
function renderSide(p) {
  const s = p.sentiment;
  const side = document.getElementById('aiSide');
  function driverList(title, list, cls) {
    if (!list.length) return '';
    return '<div class="small ' + cls + '" style="margin-top:6px"><b>' + title + '</b></div><ul class="drivers">' +
      list.map(function (n) {
        return '<li><a href="' + esc(n.link) + '" target="_blank" rel="noopener noreferrer">' + esc(n.title) + '</a></li>';
      }).join('') + '</ul>';
  }
  const ai = p.ai || {};
  const call = ai.used
    ? '<p><b>AI prediction:</b> ' + ({ up: 'up', down: 'down', flat: 'stable' }[ai.outlook] || 'see line') +
      ' (<span class="' + cls(ai.change_pct) + '">' + pct(ai.change_pct) + '</span>)' +
      (ai.confidence ? ', ' + esc(ai.confidence) + ' confidence' : '') +
      '<br><span class="muted small">The trend + news method alone said ' + pct(ai.stat_change_pct) + '.</span></p>'
    : '<p class="muted small">The AI did not make this prediction' + (ai.note ? ': ' + esc(ai.note) : '') +
      '. It uses the trend + news method.</p>';
  const sum = p.summary || { text: '', ai: false, note: '' };
  side.innerHTML =
    '<h3>Why it looks ' + esc(s.label === 'neutral' ? 'stable' : s.label) + '</h3>' +
    '<div style="margin-bottom:6px">' + toneBadge(s.score) + ' <span class="muted small">' + esc(p.counts) + '</span></div>' +
    '<p>' + esc(p.why) + '</p>' +
    driverList('Pushing it up', p.drivers.positive, 'up') +
    driverList('Pushing it down', p.drivers.negative, 'down') +
    '<h3 style="margin-top:14px">AI summary</h3>' + call +
    '<p>' + esc(sum.text) + '</p>' +
    '<span class="ai-tag">' + (sum.ai ? 'Written by ' + esc(sum.by) : 'Auto summary, AI model not used') + '</span>' +
    (!sum.ai && sum.note ? '<div class="muted small" style="margin-top:4px">' + esc(sum.note) + '</div>' : '');
  showSide(true);
}

function toneBadge(score) {
  const c = score >= 0.15 ? 'pos' : score <= -0.15 ? 'neg' : '';
  const t = (score > 0 ? '+' : '') + score.toFixed(2);
  return '<span class="tone ' + c + '">' + t + '</span>';
}

function renderPredictInfo(p) {
  const s = p.sentiment;
  const box = document.getElementById('predictInfo');
  const dir = p.change_pct >= 0 ? 'up' : 'down';
  box.innerHTML =
    '<div class="pi-head"><b>News mood:</b> ' + toneBadge(s.score) + ' <b>' + esc(s.label) + '</b>' +
    '<span class="muted small">from ' + s.articles + ' recent headline' + (s.articles === 1 ? '' : 's') +
    ' &middot; scored by ' + esc(s.engine) + '</span></div>' + (s.engine_note ? '<div class="muted small">Model: ' + esc(s.engine_note) + '</div>' : '') + +
    '<div>' + esc(p.why) + ' The dashed line ends around <b>' + money(p.to_price) + '</b> <span class="' + (dir === 'up' ? 'up' : 'down') + '">(' +
    pct(p.change_pct) + ')</span>, and the shaded area is the likely range.</div>' +
    (p.news.length
      ? '<ul>' + p.news.map(function (n) {
          return '<li>' + toneBadge(n.score) + (n.severe ? '<span class="tone neg" title="Serious: legal, leadership or regulatory">!</span>' : '') + '<a href="' + esc(n.link) + '" target="_blank" rel="noopener noreferrer">' + esc(n.title) +
            '</a><span class="src">' + esc(n.publisher) + '</span></li>';
        }).join('') + '</ul>'
      : '<div class="muted small" style="margin-top:6px">No recent news came back, so this follows the price trend only.</div>') +
    '<p class="muted small" style="margin:8px 0 0">' + esc(p.disclaimer) + '</p>';
  box.classList.remove('hidden');
}

function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

// the popup that shows what the prediction is doing, step by step
function openProgress(onCancel) {
  const host = document.getElementById('modalHost');
  const icons = { pending: '&#9675;', done: '&#10003;', warn: '!', skipped: '&ndash;', error: '&times;' };
  host.innerHTML =
    '<div class="modal-bg"><div class="modal" style="max-width:560px">' +
      '<h2>Predicting ' + esc(stock.name) + '</h2>' +
      '<p class="muted small" id="pgSub">Starting...</p>' +
      '<ul class="steps" id="pgSteps"></ul>' +
      '<div id="pgErr" class="banner err hidden"></div>' +
      '<p class="muted small" id="pgHint">The first prediction can take a few minutes while the AI model loads. After that it is much faster.</p>' +
      '<button class="btn light" id="pgCancel">Cancel</button>' +
    '</div></div>';
  document.getElementById('pgCancel').onclick = onCancel;
  return {
    update: function (st) {
      document.getElementById('pgSub').textContent = 'Working for ' + st.elapsed + 's';
      document.getElementById('pgSteps').innerHTML = st.steps.map(function (x) {
        const ic = x.status === 'running' ? '<span class="spin"></span>' : (icons[x.status] || icons.pending);
        return '<li class="' + x.status + '"><span class="ic">' + ic + '</span><div><b>' + esc(x.title) + '</b>' +
          (x.detail ? '<div class="muted small">' + esc(x.detail) + '</div>' : '') + '</div></li>';
      }).join('');
    },
    fail: function (msg) {
      const e = document.getElementById('pgErr');
      e.textContent = msg;
      e.classList.remove('hidden');
      document.getElementById('pgCancel').textContent = 'Close';
    },
    close: function () { host.innerHTML = ''; }
  };
}

function applyPrediction(p) {
  chart.setPrediction(p.points);
  renderPredictInfo(p);
  renderSide(p);
}

async function loadPrediction() {
  if (view !== 'pred') return;
  const mine = ++predToken;
  const hit = predCache[range];
  if (hit && Date.now() - hit.at < PRED_FRESH) { applyPrediction(hit.data); return; }

  const pop = openProgress(function () { pop.close(); setView('actual'); });
  let jid;
  try {
    jid = (await api('/api/stocks/' + TICKER + '/predict/start?range=' + range, { method: 'POST' })).job;
  } catch (e) {
    pop.close();
    toast(e.message, true);
    setView('actual');
    return;
  }
  let fails = 0;
  while (true) {
    await sleep(700);
    if (mine !== predToken || view !== 'pred') { pop.close(); return; } // cancelled or changed range
    let st;
    try {
      st = await api('/api/stocks/job/' + jid);
      fails = 0;
    } catch (e) {
      if (++fails < 4) continue;
      pop.fail(e.message);
      return;
    }
    pop.update(st);
    if (!st.done) continue;
    if (st.error) { pop.fail(st.error); return; }
    await sleep(900); // let them see the last steps tick over
    if (mine !== predToken || view !== 'pred') { pop.close(); return; }
    pop.close();
    predCache[range] = { at: Date.now(), data: st.result };
    applyPrediction(st.result);
    return;
  }
}

function buildTools() {
  const box = document.getElementById('tools');
  box.innerHTML =
    TOOLS.map(function (t) {
      return '<button class="chip' + (t[0] === 'none' ? ' on' : '') + '" data-tool="' + t[0] + '">' + t[1] + '</button>';
    }).join('') +
    '<span class="sep"></span>' +
    '<input type="color" id="colorPick" value="#5b6cd6" title="Drawing color">' +
    '<span class="brk"></span>' +
    '<button class="chip" id="undoBtn">Undo</button>' +
    '<button class="chip" id="redoBtn">Redo</button>' +
    '<button class="chip" id="clearBtn">Clear all</button>' +
    '<span class="sep"></span>' +
    '<button class="chip" id="saveBtn">Save drawings</button>' +
    '<button class="chip" id="loadBtn">Load saved</button>' +
    '<span class="sep"></span>' +
    '<button class="chip" id="zoomIn">Zoom in</button>' +
    '<button class="chip" id="zoomOut">Zoom out</button>' +
    '<button class="chip" id="zoomReset">Reset zoom</button>' +
    '<span class="sep"></span>' +
    '<button class="chip" id="imgBtn">Download image</button>';

  box.addEventListener('click', function (e) {
    const t = e.target.dataset.tool;
    if (t === undefined) return;
    chart.setTool(t);
    box.querySelectorAll('[data-tool]').forEach(function (b) {
      b.classList.toggle('on', b.dataset.tool === t);
    });
  });
  document.getElementById('colorPick').oninput = function () { chart.color = this.value; };
  document.getElementById('undoBtn').onclick = function () { chart.undo(); };
  document.getElementById('redoBtn').onclick = function () { chart.redo(); };
  document.getElementById('clearBtn').onclick = function () {
    if (!chart.shapes.length) return;
    if (confirm('Remove all drawings on this chart? You can still undo it.')) chart.clearShapes();
  };
  document.getElementById('saveBtn').onclick = saveShapes;
  document.getElementById('loadBtn').onclick = function () {
    if (unsaved && !confirm('You have unsaved drawings. Load the saved ones anyway?')) return;
    loadShapes(true);
  };
  document.getElementById('zoomIn').onclick = function () { chart.zoom(1 / 1.4); };
  document.getElementById('zoomOut').onclick = function () { chart.zoom(1.4); };
  document.getElementById('zoomReset').onclick = function () { chart.resetZoom(); };
  document.getElementById('imgBtn').onclick = function () {
    if (!chart.data.length) { toast('Chart is still loading.', true); return; }
    const day = new Date().toISOString().slice(0, 10);
    chart.toPNG(stock.name + ' (' + stock.ticker + ')', 'Range: ' + range + '  |  Latest close ' + money(stock.quote.price),
      'moneysprout-' + stock.ticker + '-' + range + '-' + day + '.png');
    toast('Image downloaded');
  };
}

function setUnsaved(v) {
  unsaved = v;
  document.getElementById('saveState').textContent = v ? ' You have unsaved drawings.' : '';
}

async function loadHistory() {
  const msg = document.getElementById('chartMsg');
  msg.innerHTML = '<div class="skel" style="width:100%;height:100%"></div>';
  msg.classList.remove('hidden');
  const mine = ++loadToken;
  try {
    const h = await api('/api/stocks/' + TICKER + '/history?range=' + range);
    if (mine !== loadToken) return; // they clicked another range already
    chart.setData(h.points, h.intraday, h.timezone);
    msg.classList.add('hidden');
    if (view === 'pred') loadPrediction();
  } catch (e) {
    // show the error and a button so they can try again
    msg.innerHTML = '<div style="text-align:center;padding:0 16px"><div>' + esc(e.message) +
      '</div><button class="btn light sm" id="retryChart" style="margin-top:10px">Try again</button></div>';
    document.getElementById('retryChart').onclick = loadHistory;
  }
}

// keeps the price and chart live while the page is open
async function liveRefresh() {
  if (document.hidden || !chart || !stock) return;
  try {
    const s = await api('/api/stocks/' + TICKER);
    stock.quote = s.quote;
    renderHead();
    const mine = loadToken;
    const h = await api('/api/stocks/' + TICKER + '/history?range=' + range);
    if (mine !== loadToken || h.range !== range) return;
    chart.refreshData(h.points);
  } catch (e) {
    // quiet, it will try again in a bit
  }
}

async function saveShapes() {
  const done = busy(document.getElementById('saveBtn'), 'Saving...');
  try {
    await api('/api/annotations/' + TICKER, { method: 'PUT', body: { shapes: chart.shapes } });
    setUnsaved(false);
    toast('Drawings saved');
  } catch (e) {
    toast(e.message, true);
  }
  done();
}

async function loadShapes(showToast) {
  try {
    const d = await api('/api/annotations/' + TICKER);
    chart.setShapes(d.shapes);
    setUnsaved(false);
    if (showToast) toast(d.shapes.length ? 'Saved drawings loaded' : 'No saved drawings yet');
  } catch (e) {
    toast(e.message, true);
  }
}

function renderHead() {
  const q = stock.quote;
  document.title = stock.name + ' (' + stock.ticker + ') - MoneySprout';
  document.getElementById('head').innerHTML = '<div><h1 style="margin:0">' + esc(stock.name) + ' <span class="muted mono" style="font-size:16px">' + stock.ticker + '</span></h1>' +
    '<div class="muted small">' + esc(stock.exchange) + ' &middot; ' + esc(stock.sector) + '</div>' +
    '<div><span class="price">' + money(q.price) + '</span> <span class="' + cls(q.change) + '"><b>' +
    signedMoney(q.change) + ' (' + pct(q.change_pct) + ')</b></span></div>' +
    '<div class="muted small">' + liveLabel(q) + '</div></div>';

  document.getElementById('aboutTitle').textContent = 'About ' + stock.name;
  document.getElementById('desc').textContent = stock.description;
  const facts = [
    ['Industry', stock.industry],
    ['Sector', stock.sector],
    ['Headquarters', stock.headquarters],
    ['Founded', stock.founded],
    ['Exchange', stock.exchange],
    ['Shares you own', stock.shares_owned || 0]
  ];
  document.getElementById('facts').innerHTML = facts.map(function (f) {
    return '<tr><td class="muted">' + f[0] + '</td><td class="right">' + esc(f[1]) + '</td></tr>';
  }).join('');

  const wb = document.getElementById('watchBtn');
  wb.textContent = stock.watching ? 'Remove from watchlist' : 'Add to watchlist';
  document.getElementById('noteLink').href = 'notes.html?t=' + stock.ticker;
}

document.getElementById('watchBtn').onclick = async function () {
  try {
    if (stock.watching) {
      await api('/api/watchlist/' + TICKER, { method: 'DELETE' });
      stock.watching = false;
      toast('Removed from your watchlist');
    } else {
      await api('/api/watchlist', { method: 'POST', body: { ticker: TICKER } });
      stock.watching = true;
      toast('Added to your watchlist');
    }
    renderHead();
  } catch (e) {
    toast(e.message, true);
  }
};

// buy and sell popup

function openTrade(mode) {
  const q = stock.quote;
  const host = document.getElementById('modalHost');
  let inputMode = 'shares';

  host.innerHTML =
    '<div class="modal-bg" id="mbg"><div class="modal">' +
      '<h2>Trade ' + esc(stock.name) + '</h2>' +
      '<div class="tabs"><button class="chip" data-m="buy">Buy</button><button class="chip" data-m="sell">Sell</button></div>' +
      '<div id="modalBody"></div>' +
    '</div></div>';

  const bg = document.getElementById('mbg');
  bg.addEventListener('mousedown', function (e) { if (e.target === bg) close(); });

  function close() { host.innerHTML = ''; }

  function renderBody() {
    host.querySelectorAll('[data-m]').forEach(function (b) { b.classList.toggle('on', b.dataset.m === mode); });
    const body = document.getElementById('modalBody');
    const cash = window.ME.wallet.cash;
    const owned = stock.shares_owned || 0;

    if (mode === 'buy') {
      body.innerHTML =
        '<div class="summary-box"><div><span>Latest price</span><b>' + money(q.price) + '</b></div>' +
        '<div><span>Cash</span><b>' + money(cash) + '</b></div></div>' +
        '<div class="tabs"><button class="chip" data-i="shares">By shares</button><button class="chip" data-i="amount">By dollars</button></div>' +
        '<div class="field"><label id="inLabel"></label><input type="number" id="amt" min="0" step="any"></div>' +
        '<div class="summary-box" id="calc"></div>' +
        '<div id="tradeErr" class="banner err hidden"></div>' +
        '<button class="btn block" id="go">Buy</button>';
    } else {
      body.innerHTML =
        '<div class="summary-box"><div><span>Latest price</span><b>' + money(q.price) + '</b></div>' +
        '<div><span>Shares you own</span><b>' + owned + '</b></div></div>' +
        (owned > 0
          ? '<div class="field"><label>Shares to sell</label><input type="number" id="amt" min="0" step="any">' +
            '<button class="btn light sm" id="allBtn" style="margin-top:6px">Sell all</button></div>' +
            '<div class="summary-box" id="calc"></div>' +
            '<div id="tradeErr" class="banner err hidden"></div>' +
            '<button class="btn block" id="go">Sell</button>'
          : '<div class="empty">You do not own any shares of this company yet.</div>');
    }
    wireBody();
  }

  function wireBody() {
    const amt = document.getElementById('amt');
    if (!amt) return;
    const calc = document.getElementById('calc');
    const err = document.getElementById('tradeErr');

    function figure() {
      const v = parseFloat(amt.value);
      if (!v || v <= 0) return null;
      if (mode === 'buy') {
        const shares = inputMode === 'shares' ? v : Math.floor((v / q.price) * 10000) / 10000;
        return { shares: shares, total: shares * q.price };
      }
      return { shares: v, total: v * q.price };
    }

    function update() {
      const f = figure();
      if (mode === 'buy') {
        const label = document.getElementById('inLabel');
        label.textContent = inputMode === 'shares' ? 'Number of shares' : 'Amount in dollars';
        host.querySelectorAll('[data-i]').forEach(function (b) { b.classList.toggle('on', b.dataset.i === inputMode); });
      }
      if (!f) { calc.innerHTML = '<div class="muted">Enter an amount to see a summary.</div>'; return; }
      if (mode === 'buy') {
        const left = window.ME.wallet.cash - f.total;
        calc.innerHTML = '<div><span>Shares</span><b>' + f.shares + '</b></div>' +
          '<div><span>Estimated total cost</span><b>' + money(f.total) + '</b></div>' +
          '<div><span>Cash left after</span><b class="' + (left < 0 ? 'down' : '') + '">' + money(left) + '</b></div>';
      } else {
        const gain = (q.price - stock.avg_price) * f.shares;
        calc.innerHTML = '<div><span>Shares</span><b>' + f.shares + '</b></div>' +
          '<div><span>Estimated proceeds</span><b>' + money(f.total) + '</b></div>' +
          '<div><span>Estimated profit / loss</span><b class="' + cls(gain) + '">' + signedMoney(gain) + '</b></div>';
      }
    }
    amt.addEventListener('input', update);
    host.querySelectorAll('[data-i]').forEach(function (b) {
      b.onclick = function () { inputMode = b.dataset.i; amt.value = ''; update(); };
    });
    const all = document.getElementById('allBtn');
    if (all) all.onclick = function () { amt.value = stock.shares_owned; update(); };
    update();

    document.getElementById('go').onclick = async function () {
      const v = parseFloat(amt.value);
      err.classList.add('hidden');
      if (!v || v <= 0) {
        err.textContent = 'Enter an amount first.';
        err.classList.remove('hidden');
        return;
      }
      const btn = this;
      const done = busy(btn, mode === 'buy' ? 'Buying...' : 'Selling...');
      try {
        let r;
        if (mode === 'buy') {
          const body = { ticker: TICKER };
          if (inputMode === 'shares') body.quantity = v; else body.amount = v;
          r = await api('/api/portfolio/buy', { method: 'POST', body: body });
          toast('Bought ' + r.quantity + ' shares for ' + money(r.total));
        } else {
          const body = { ticker: TICKER, quantity: v };
          if (stock.shares_owned && Math.abs(v - stock.shares_owned) < 0.00005) body.sell_all = true;
          r = await api('/api/portfolio/sell', { method: 'POST', body: body });
          toast('Sold ' + r.quantity + ' shares for ' + money(r.total));
        }
        close();
        await refreshAfterTrade();
      } catch (e) {
        let text = e.message;
        if (e.status === 403) text += ' You can ask in Settings.';
        err.textContent = text;
        err.classList.remove('hidden');
        done();
      }
    };
  }

  host.querySelectorAll('[data-m]').forEach(function (b) {
    b.onclick = function () { mode = b.dataset.m; renderBody(); };
  });
  renderBody();
}

async function refreshAfterTrade() {
  // pull fresh wallet and holdings so the page matches
  const me = await api('/api/auth/me');
  window.ME = me;
  setWallet(me.wallet.cash);
  const s = await api('/api/stocks/' + TICKER);
  stock = Object.assign(stock, s);
  const hold = await api('/api/portfolio/holdings');
  const mine = hold.holdings.find(function (h) { return h.ticker === TICKER; });
  stock.avg_price = mine ? mine.avg_price : 0;
  renderHead();
}

document.getElementById('buyBtn').onclick = function () { openTrade('buy'); };
document.getElementById('sellBtn').onclick = function () { openTrade('sell'); };

window.addEventListener('beforeunload', function (e) {
  if (unsaved) { e.preventDefault(); e.returnValue = ''; }
});

async function start() {
  await initShell('explore.html');
  document.getElementById('banner').innerHTML = demoBanner();

  if (!TICKER) { location.href = 'explore.html'; return; }
  try {
    stock = await api('/api/stocks/' + TICKER);
  } catch (e) {
    document.getElementById('page').innerHTML = '<div class="banner err">' + esc(e.message) +
      '</div><a class="btn" href="explore.html">Back to Explore</a>';
    return;
  }
  const hold = await api('/api/portfolio/holdings');
  const mine = hold.holdings.find(function (h) { return h.ticker === TICKER; });
  stock.avg_price = mine ? mine.avg_price : 0;

  renderHead();
  buildRanges();
  buildPredict();
  chart = new StockChart(document.getElementById('chart'));
  chart.onChange = function () { setUnsaved(true); };
  buildTools();
  chart.setTool('none');
  await loadShapes(false);
  loadHistory();
  setInterval(liveRefresh, 15000);
}

start();
