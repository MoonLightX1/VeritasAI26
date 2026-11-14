// dashboard page

function statCard(label, value, sub, subClass) {
  return '<div class="card stat"><div class="label">' + label + '</div><div class="value">' + value +
    '</div><div class="sub ' + (subClass || 'muted') + '">' + (sub || '&nbsp;') + '</div></div>';
}

function stockRow(item) {
  const q = item.quote;
  return '<div class="row"><div class="l">' + logoHtml(item.ticker) +
    '<div><a href="stock.html?t=' + item.ticker + '"><b>' + esc(item.name) + '</b></a><div class="muted small">' + item.ticker + '</div></div></div>' +
    (item.spark ? '<canvas class="spark" data-t="' + item.ticker + '" style="width:80px;height:34px"></canvas>' : '') +
    '<div class="right"><div><b>' + money(q.price) + '</b></div><div class="small ' + cls(q.change_pct) + '">' + pct(q.change_pct) + '</div></div></div>';
}

async function start() {
  const me = await initShell('dashboard.html');
  document.getElementById('welcome').textContent = 'Welcome, ' + me.display_name;
  document.getElementById('banner').innerHTML = demoBanner();

  let d;
  try {
    d = await api('/api/dashboard');
  } catch (e) {
    toast(e.message, true);
    return;
  }

  const w = d.wallet;
  document.getElementById('wallet').innerHTML =
    statCard('Available cash', money(w.cash), 'Ready to practice with') +
    statCard('Total portfolio value', money(w.total_value), 'Cash plus shares') +
    statCard('Total profit / loss', signedMoney(w.profit), pct(w.profit_pct) + ' since you started', cls(w.profit)) +
    statCard('Today', signedMoney(w.day_change), pct(w.day_change_pct) + ' daily change', cls(w.day_change));
  setWallet(w.cash);

  document.getElementById('indices').innerHTML = d.indices.map(function (i) {
    const arrow = i.change_pct >= 0 ? 'Up' : 'Down';
    return '<div class="card stat"><div class="label">' + esc(i.name) + '</div><div class="value">' +
      Number(i.price).toLocaleString('en-US', { maximumFractionDigits: 2 }) + '</div>' +
      '<div class="sub ' + cls(i.change_pct) + '">' + arrow + ' ' + pct(i.change_pct) + '</div>' +
      '<div class="muted small">Demo data as of ' + i.as_of + '</div></div>';
  }).join('');

  const watch = document.getElementById('watch');
  if (!d.watchlist.length) {
    watch.innerHTML = '<div class="empty">Nothing here yet. <a href="explore.html">Find a company</a> and add it to your watchlist.</div>';
  } else {
    watch.innerHTML = d.watchlist.map(stockRow).join('') + '<p style="margin:10px 0 0"><a href="watchlist.html">See full watchlist</a></p>';
  }

  document.getElementById('trending').innerHTML = d.trending.map(stockRow).join('');

  const act = document.getElementById('activity');
  if (!d.activity.length) {
    act.innerHTML = '<div class="empty">No practice trades yet. Open a company and try buying a few shares.</div>';
  } else {
    act.innerHTML = d.activity.map(function (a) {
      return '<div class="row"><div><span class="pill ' + (a.kind === 'buy' ? '' : 'warn') + '">' + a.kind.toUpperCase() + '</span> ' +
        a.quantity + ' x <a href="stock.html?t=' + a.ticker + '">' + a.ticker + '</a> at ' + money(a.price) +
        '</div><div class="muted small">' + shortDate(a.at) + '</div></div>';
    }).join('');
  }

  const vw = document.getElementById('viewed');
  if (!d.viewed.length) {
    vw.innerHTML = '<div class="empty">Companies you look at will show up here.</div>';
  } else {
    vw.innerHTML = d.viewed.map(function (v) {
      return '<div class="row"><div class="l">' + logoHtml(v.ticker) + '<a href="stock.html?t=' + v.ticker + '">' +
        esc(v.name) + '</a></div><div class="muted small">' + shortDate(v.at) + '</div></div>';
    }).join('');
  }

  // sparklines need the canvases to be on the page first
  const sparks = {};
  d.watchlist.forEach(function (i) { sparks[i.ticker] = i.spark; });
  document.querySelectorAll('canvas.spark').forEach(function (c) {
    if (sparks[c.dataset.t]) drawSpark(c, sparks[c.dataset.t]);
  });
}

start();
