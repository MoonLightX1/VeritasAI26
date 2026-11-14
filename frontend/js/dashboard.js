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

// popup about the ai stuff, shows once each time you open the site (not on the main page)
function aiNotice() {
  try { if (sessionStorage.getItem('aiNoticeSeen')) return; } catch (e) {}
  const host = document.createElement('div');
  host.className = 'modal-bg';
  host.innerHTML = '<div class="modal" role="dialog" aria-modal="true">' +
    '<h2>Before you start</h2>' +
    '<p>MoneySprout has AI predictions and summaries. They are made by a computer reading news headlines.</p>' +
    '<ul class="plain-bullets"><li>They can be wrong, and they are often wrong.</li>' +
    '<li>They are not financial advice.</li>' +
    '<li>All the money here is pretend. Nothing here is a real trade.</li></ul>' +
    '<button class="btn block" id="aiOk">I understand</button></div>';
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
  // grey placeholders until the numbers show up
  document.getElementById('wallet').innerHTML = '<div class="skel skel-big"></div>';
  ['watch', 'trending', 'activity', 'viewed'].forEach(function (id) {
    document.getElementById(id).innerHTML = skeletonRows(3);
  });
  await load(true);
  // refresh the prices every 30 seconds while the page is open
  setInterval(function () { if (!document.hidden) load(false); }, 30000);
}

async function load(first) {
  let d;
  try {
    d = await api('/api/dashboard');
  } catch (e) {
    // only nag on the first load, later ones just try again next time
    if (first) toast(e.message, true);
    return;
  }

  const w = d.wallet;
  document.getElementById('wallet').innerHTML =
    statCard('Portfolio value', money(w.total_value), '', '', true, 'Cash plus what your shares are worth right now.') +
    statCard('Cash', money(w.cash), '', '', false, 'Pretend money you have left to spend.') +
    statCard('All time', signedMoney(w.profit), pct(w.profit_pct), cls(w.profit), false, 'Gain or loss compared to the money you put in.') +
    statCard('Today', signedMoney(w.day_change), pct(w.day_change_pct), cls(w.day_change), false, 'How your shares moved since yesterday\'s close.');
  setWallet(w.cash);

  const watch = document.getElementById('watch');
  if (!d.watchlist.length) {
    watch.innerHTML = '<div class="empty">Nothing here yet. <a href="explore">Find a company</a> and add it to your watchlist.</div>';
  } else {
    watch.innerHTML = d.watchlist.map(stockRow).join('') + '<p style="margin:10px 0 0"><a href="watchlist">See full watchlist</a></p>';
  }

  document.getElementById('trending').innerHTML = d.trending.map(stockRow).join('');

  const act = document.getElementById('activity');
  if (!d.activity.length) {
    act.innerHTML = '<div class="empty">No trades yet. Open a company and buy a few shares.</div>';
  } else {
    act.innerHTML = d.activity.map(function (a) {
      return '<div class="row"><div><span class="pill ' + (a.kind === 'buy' ? '' : 'warn') + '">' + a.kind.toUpperCase() + '</span> ' +
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

  // sparklines need the canvases to be on the page first
  const sparks = {};
  d.watchlist.concat(d.trending).forEach(function (i) { sparks[i.ticker] = i.spark; });
  document.querySelectorAll('canvas.spark').forEach(function (c) {
    if (sparks[c.dataset.t]) drawSpark(c, sparks[c.dataset.t]);
  });
}

start();
