// explore page, search and browse companies

const qInput = document.getElementById('q');
const resultsBox = document.getElementById('results');
const countBox = document.getElementById('count');
let timer = null;

async function search() {
  const q = qInput.value.trim();
  resultsBox.innerHTML = '<div class="muted">Loading...</div>';
  try {
    const data = await api('/api/stocks/search?q=' + encodeURIComponent(q));
    const list = data.results;
    countBox.textContent = list.length + (list.length === 1 ? ' company' : ' companies');
    if (!list.length) {
      resultsBox.innerHTML = '<div class="empty" style="grid-column:1/-1">Nothing matched that search. Try a different name or ticker.</div>';
      return;
    }
    resultsBox.innerHTML = list.map(function (c) {
      const qt = c.quote;
      return '<a class="card stock-card" href="stock.html?t=' + c.ticker + '">' +
        '<div class="row" style="border:none;padding:0 0 8px"><div class="l">' + logoHtml(c.ticker) +
        '<div><b>' + esc(c.name) + '</b><div class="muted small">' + c.ticker + ' &middot; ' + esc(c.exchange) + '</div></div></div>' +
        '<div class="right"><b>' + money(qt.price) + '</b><div class="small ' + cls(qt.change_pct) + '">' + pct(qt.change_pct) + '</div></div></div>' +
        '<p class="muted small" style="margin:0">' + esc(c.description) + '</p></a>';
    }).join('');
  } catch (e) {
    resultsBox.innerHTML = '<div class="banner err" style="grid-column:1/-1">' + esc(e.message) + '</div>';
  }
}

qInput.addEventListener('input', function () {
  clearTimeout(timer);
  timer = setTimeout(search, 250);
});

async function start() {
  await initShell('explore.html');
  document.getElementById('banner').innerHTML = demoBanner();
  const params = new URLSearchParams(location.search);
  if (params.get('q')) qInput.value = params.get('q');
  search();
}

start();
