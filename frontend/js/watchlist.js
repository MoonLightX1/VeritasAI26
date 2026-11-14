// watchlist page

const listBox = document.getElementById('list');
const addInput = document.getElementById('addInput');
let companies = [];

async function load() {
  try {
    const data = await api('/api/watchlist');
    if (!data.items.length) {
      listBox.innerHTML = '<div class="empty">Your watchlist is empty. Add a company above.</div>';
      return;
    }
    listBox.innerHTML = data.items.map(function (c) {
      const q = c.quote;
      return '<div class="row"><div class="l">' + logoHtml(c.ticker) +
        '<div><a href="stock.html?t=' + c.ticker + '"><b>' + esc(c.name) + '</b></a><div class="muted small">' + c.ticker + ' &middot; ' + esc(c.sector) + '</div></div></div>' +
        (c.spark && c.spark.length ? '<canvas class="spark" data-t="' + c.ticker + '" style="width:90px;height:34px"></canvas>' : '<span></span>') +
        '<div class="right"><b>' + money(q.price) + '</b><div class="small ' + cls(q.change_pct) + '">' + pct(q.change_pct) + '</div></div>' +
        '<div class="nowrap"><a class="btn sm" href="stock.html?t=' + c.ticker + '">Open</a> ' +
        '<button class="btn light sm" data-remove="' + c.ticker + '">Remove</button></div></div>';
    }).join('');
    const sp = {};
    data.items.forEach(function (c) { sp[c.ticker] = c.spark; });
    listBox.querySelectorAll('canvas.spark').forEach(function (cv) { drawSpark(cv, sp[cv.dataset.t]); });
  } catch (e) {
    listBox.innerHTML = '<div class="banner err">' + esc(e.message) + '</div>';
  }
}

listBox.addEventListener('click', async function (e) {
  const t = e.target.dataset.remove;
  if (!t) return;
  try {
    await api('/api/watchlist/' + t, { method: 'DELETE' });
    toast(t + ' removed from your watchlist');
    load();
  } catch (err) {
    toast(err.message, true);
  }
});

// figure out which company they typed, accepts "AAPL" or "Apple (AAPL)" or just a name
function findTicker(text) {
  const v = text.trim().toLowerCase();
  if (!v) return null;
  const hit = companies.find(function (c) {
    return c.ticker.toLowerCase() === v || c.name.toLowerCase() === v ||
      (c.name + ' (' + c.ticker + ')').toLowerCase() === v;
  });
  return hit ? hit.ticker : null;
}

document.getElementById('addBtn').onclick = async function () {
  const t = findTicker(addInput.value);
  if (!t) { toast('Pick a company from the list.', true); return; }
  try {
    await api('/api/watchlist', { method: 'POST', body: { ticker: t } });
    addInput.value = '';
    toast(t + ' added to your watchlist');
    load();
  } catch (e) {
    toast(e.message, true);
  }
};

async function start() {
  await initShell('watchlist.html');
  document.getElementById('banner').innerHTML = demoBanner();
  const data = await api('/api/stocks/search?q=');
  companies = data.results;
  document.getElementById('companies').innerHTML = companies.map(function (c) {
    return '<option value="' + esc(c.name) + ' (' + c.ticker + ')"></option>';
  }).join('');
  load();
}

start();
