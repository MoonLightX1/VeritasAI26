// shared stuff every page uses

async function api(path, options) {
  options = options || {};
  // the server only accepts changes that carry this header, so other sites cannot fake them
  const init = { method: options.method || 'GET', credentials: 'same-origin', headers: { 'X-Requested-With': 'moneysprout' } };
  if (options.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(options.body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch (e) {
    throw new Error('Cannot reach the server right now. Is it running?');
  }
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (!res.ok) {
    // not logged in, send them to login (but not if we are already on a public page)
    if (res.status === 401 && !options.noRedirect) {
      location.href = 'login';
    }
    let msg = 'Oops, something went wrong.';
    if (data && typeof data.detail === 'string') msg = data.detail;
    else if (data && Array.isArray(data.detail) && data.detail[0]) msg = data.detail[0].msg;
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return data;
}

function money(n) {
  if (n === null || n === undefined || isNaN(n)) return '-';
  return Number(n).toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

function signedMoney(n) {
  const s = money(Math.abs(n));
  return (n < 0 ? '-' : '+') + s;
}

function pct(n) {
  if (n === null || n === undefined || isNaN(n)) return '-';
  return (n > 0 ? '+' : '') + Number(n).toFixed(2) + '%';
}

function cls(n) { return n > 0 ? 'up' : (n < 0 ? 'down' : ''); }

// makes text safe to drop into html, including inside "quotes" of an attribute
function esc(s) {
  return (s === null || s === undefined ? '' : String(s))
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// only lets real https links through, anything else becomes a dead link
function safeUrl(u) {
  return /^https:\/\//i.test(String(u || '')) ? String(u) : '#';
}

function shortDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) + ' ' +
    d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

function toast(msg, isErr) {
  let box = document.getElementById('toasts');
  if (!box) {
    box = document.createElement('div');
    box.id = 'toasts';
    document.body.appendChild(box);
  }
  const t = document.createElement('div');
  t.className = 'toast' + (isErr ? ' err' : '');
  t.textContent = msg;
  box.appendChild(t);
  setTimeout(function () { t.remove(); }, 3500);
}

// tiny sparkline on a canvas, just a line
function drawSpark(canvas, values) {
  canvas._vals = values; // keep them so we can redraw on theme change
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 100;
  const h = canvas.clientHeight || 36;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  if (!values || values.length < 2) return;
  const min = Math.min.apply(null, values);
  const max = Math.max.apply(null, values);
  const up = values[values.length - 1] >= values[0];
  const css = getComputedStyle(document.documentElement);
  ctx.strokeStyle = css.getPropertyValue(up ? '--up' : '--down').trim() || (up ? '#1f9d55' : '#d93f3f');
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  values.forEach(function (v, i) {
    const x = (i / (values.length - 1)) * (w - 2) + 1;
    const y = h - 3 - ((v - min) / ((max - min) || 1)) * (h - 6);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

window.addEventListener('themechange', function () {
  document.querySelectorAll('canvas.spark').forEach(function (c) {
    if (c._vals) drawSpark(c, c._vals);
  });
});

function logoHtml(ticker, big) {
  return '<div class="logo img' + (big ? ' big' : '') + '"><img src="/api/stocks/logo/' + encodeURIComponent(ticker) + '" alt="" data-t="' + esc(ticker) + '"></div>';
}

// if a logo does not load, go back to the ticker letters
document.addEventListener('error', function (e) {
  const im = e.target;
  if (!im || im.tagName !== 'IMG' || !im.dataset.t) return;
  const box = im.parentNode;
  box.classList.remove('img');
  box.textContent = im.dataset.t.slice(0, 4);
}, true);

const NAV = [
  ['dashboard', 'Dashboard'],
  ['explore', 'Find Stocks'],
  ['portfolio', 'My Portfolio'],
  ['watchlist', 'Watchlist'],
  ['notes', 'My Notes'],
  ['code-analysis', 'Under the Hood'],
  ['settings', 'Settings']
];

// builds the top bar around the page content
// every logged in page calls this first
async function initShell(active) {
  const me = await api('/api/auth/me');
  window.ME = me;

  const content = document.getElementById('page');
  const shell = document.createElement('div');
  shell.className = 'shell';

  const links = NAV.map(function (n) {
    return '<a href="' + n[0] + '" class="' + (n[0] === active ? 'active' : '') + '">' + n[1] + '</a>';
  }).join('');

  shell.innerHTML =
    '<header class="topbar">' +
      '<a class="brand" href="dashboard">Money<span>Sprout</span></a>' +
      '<nav class="nav">' + links + '</nav>' +
      '<div class="search"><input type="text" id="globalSearch" placeholder="Search a company" autocomplete="off">' +
      '<div class="suggest hidden" id="globalSuggest"></div></div>' +
      '<div class="who">' +
        '<span class="who-name muted">' + esc(me.display_name) + '</span>' +
        '<span class="mkt" id="mktPill" data-s="unknown" title="US stock market"><span class="dot"></span><span id="mktTxt">Market</span></span>' +
        '<a class="cash" href="portfolio">Cash <b id="walletAmt">' + money(me.wallet.cash) + '</b></a>' +
        themeButton() +
        '<button class="btn light sm" id="logoutBtn">Log out</button>' +
      '</div>' +
    '</header>' +
    '<div class="content" id="contentSlot"></div>';

  document.body.insertBefore(shell, content);
  document.getElementById('contentSlot').appendChild(content);
  content.classList.remove('hidden');

  document.getElementById('logoutBtn').onclick = async function () {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch (e) {}
    location.href = '/';
  };

  setupSearch();
  loadMarketPill();
  setInterval(function () { if (!document.hidden) loadMarketPill(); }, 60000);
  return me;
}

// says if the market is open or closed, shows in the top bar on every page
async function loadMarketPill() {
  const el = document.getElementById('mktPill');
  if (!el) return;
  try {
    const m = await api('/api/stocks/market/status', { noRedirect: true });
    el.dataset.s = !m.known ? 'unknown' : (m.open ? 'open' : 'closed');
    document.getElementById('mktTxt').textContent = !m.known ? 'Market status unknown' : (m.open ? 'Market open' : 'Market closed');
  } catch (e) {
    // quiet, it will try again in a minute
  }
}

function setWallet(cash) {
  const el = document.getElementById('walletAmt');
  if (el) el.textContent = money(cash);
}

// search box in the top bar, shows suggestions as you type
function setupSearch() {
  const input = document.getElementById('globalSearch');
  const box = document.getElementById('globalSuggest');
  let timer = null;

  input.addEventListener('input', function () {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { box.classList.add('hidden'); return; }
    timer = setTimeout(async function () {
      try {
        const data = await api('/api/stocks/search?q=' + encodeURIComponent(q));
        const items = data.results.slice(0, 6);
        if (!items.length) {
          box.innerHTML = '<div class="empty small">No companies found</div>';
        } else {
          box.innerHTML = items.map(function (r) {
            return '<a href="stock?t=' + r.ticker + '"><span>' + esc(r.name) + ' <span class="muted">' +
              r.ticker + '</span></span><span>' + money(r.quote.price) + '</span></a>';
          }).join('');
        }
        box.classList.remove('hidden');
      } catch (e) {}
    }, 200);
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && input.value.trim()) {
      location.href = 'explore?q=' + encodeURIComponent(input.value.trim());
    }
  });

  document.addEventListener('click', function (e) {
    if (!box.contains(e.target) && e.target !== input) box.classList.add('hidden');
  });
}

// small line that says how fresh a price is
function liveLabel(q) {
  const t = new Date(q.as_of).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  let txt = 'Updated ' + t;
  if (q.stale) txt += ' (the price source is not answering, so this is older data)';
  return txt;
}

function demoBanner() {
  return '<div class="banner">This is pretend money, and none of it is financial advice. Prices come from Yahoo Finance and can be about 15 minutes late.</div>';
}

// warning that goes above anything the ai wrote
function aiWarning() {
  return '<div class="banner warn-ai"><b>Heads up:</b> an AI wrote this after reading news headlines. ' +
    'It can be wrong or out of date, so treat it as a guess and not advice. Please do not use it for real money choices.</div>';
}

// loading placeholders, grey bars that pulse a little
function skeletonRows(n) {
  let out = '';
  for (let i = 0; i < n; i++) out += '<div class="skel skel-row"></div>';
  return out;
}

function skeletonCards(n) {
  let out = '';
  for (let i = 0; i < n; i++) out += '<div class="skel skel-card"></div>';
  return out;
}

// puts a button in a loading state, call the returned function to undo it
function busy(btn, text) {
  const old = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span>' + esc(text);
  return function () { btn.disabled = false; btn.innerHTML = old; };
}
