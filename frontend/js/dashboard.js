// dashboard page

function statCard(label, value, sub, subClass, main, desc) {
  return '<div class="stat' + (main ? ' main' : '') + '"><div class="label">' + label + '</div><div class="value">' + value +
    '</div>' + (sub ? '<div class="sub ' + (subClass || 'muted') + '">' + sub + '</div>' : '') +
    (desc ? '<div class="desc">' + desc + '</div>' : '') + '</div>';
}

function stockRow(item) {
  const q = item.quote;
  return '<div class="row"><div class="l">' + logoHtml(item.ticker) +
    '<a href="stock?t=' + item.ticker + '"><b>' + esc(item.name) + '</b></a></div>' +
    (item.spark && item.spark.length ? '<canvas class="spark" data-t="' + item.ticker + '" style="width:80px;height:34px"></canvas>' : '') +
    '<div class="right"><div><b>' + money(q.price) + '</b></div><div class="small ' + cls(q.change_pct) + '">' + pct(q.change_pct) + '</div></div></div>';
}

// ai popup, once per visit
function aiNotice() {
  try { if (sessionStorage.getItem('aiNoticeSeen')) return; } catch (e) {}
  const host = document.createElement('div');
  host.className = 'modal-bg';
  host.innerHTML = '<div class="modal" role="dialog" aria-modal="true">' +
    '<h2>Quick heads up</h2>' +
    '<p>MoneySprout has AI guesses and summaries. A computer reads the news headlines and writes them.</p>' +
    '<ul class="plain-bullets"><li>There is a chance of it being wrong.</li>' +
    '<li>They are not financial advice.</li>' +
    '<li>Nothing here is a real trade.</li></ul>' +
    '<button class="btn block" id="aiOk">Got it</button></div>';
  document.body.appendChild(host);
  document.getElementById('aiOk').onclick = function () {
    try { sessionStorage.setItem('aiNoticeSeen', '1'); } catch (e) {}
    host.remove();
  };
}

async function start() {
  const me = await initShell('dashboard');
  document.getElementById('banner').innerHTML = demoBanner();
  aiNotice();
  // placeholders
  document.getElementById('wallet').innerHTML = '<div class="skel skel-big"></div>';
  ['watch', 'trending', 'activity', 'viewed'].forEach(function (id) {
    document.getElementById(id).innerHTML = skeletonRows(3);
  });
  await load(true);
  // refresh every 30s
  setInterval(function () { if (!document.hidden) load(false); }, 30000);
}

async function load(first) {
  let d;
  try {
    d = await api('/api/dashboard');
  } catch (e) {
    // only complain on first load
    if (first) toast(e.message, true);
    return;
  }

  const w = d.wallet;
  document.getElementById('wallet').innerHTML =
    statCard('Portfolio value', money(w.total_value), '', '', true, 'Your cash plus what your shares are worth right now.') +
    statCard('Cash', money(w.cash), '', '', false, 'Cash you still have to spend.') +
    statCard('Overall', signedMoney(w.profit), pct(w.profit_pct), cls(w.profit), false, 'How much you are up or down compared to what you started with.') +
    statCard('Today', signedMoney(w.day_change), pct(w.day_change_pct), cls(w.day_change), false, 'How your shares did since yesterday\'s close.');
  setWallet(w.cash);

  const watch = document.getElementById('watch');
  if (!d.watchlist.length) {
    watch.innerHTML = '<div class="empty">Nothing here yet. <a href="explore">Find a company</a> you like and add it to your watchlist.</div>';
  } else {
    watch.innerHTML = d.watchlist.map(stockRow).join('') + '<p style="margin:10px 0 0"><a href="watchlist">See full watchlist</a></p>';
  }

  document.getElementById('trending').innerHTML = d.trending.map(stockRow).join('');

  const act = document.getElementById('activity');
  if (!d.activity.length) {
    act.innerHTML = '<div class="empty">No trades yet. Open a company and buy a few shares to get going.</div>';
  } else {
    act.innerHTML = d.activity.map(function (a) {
      return '<div class="row"><div><b class="' + (a.kind === 'buy' ? 'up' : 'down') + '">' + a.kind.toUpperCase() + '</b> ' +
        a.quantity + ' x <a href="stock?t=' + a.ticker + '">' + a.ticker + '</a> at ' + money(a.price) +
        '</div><div class="muted small">' + shortDate(a.at) + '</div></div>';
    }).join('');
  }

  const vw = document.getElementById('viewed');
  if (!d.viewed.length) {
    vw.innerHTML = '<div class="empty">Companies you look at will show up here.</div>';
  } else {
    vw.innerHTML = d.viewed.map(function (v) {
      return '<div class="row"><div class="l">' + logoHtml(v.ticker) + '<a href="stock?t=' + v.ticker + '">' +
        esc(v.name) + '</a></div><div class="muted small">' + shortDate(v.at) + '</div></div>';
    }).join('');
  }

  // canvases have to exist first
  const sparks = {};
  d.watchlist.concat(d.trending).forEach(function (i) { sparks[i.ticker] = i.spark; });
  document.querySelectorAll('canvas.spark').forEach(function (c) {
    if (sparks[c.dataset.t]) drawSpark(c, sparks[c.dataset.t]);
  });
}

start();
