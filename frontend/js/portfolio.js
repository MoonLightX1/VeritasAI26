// portfolio page

function card(label, value, sub, subClass) {
  return '<div class="card stat"><div class="label">' + label + '</div><div class="value">' + value +
    '</div><div class="sub ' + (subClass || 'muted') + '">' + (sub || '&nbsp;') + '</div></div>';
}

async function start() {
  await initShell('portfolio.html');
  document.getElementById('banner').innerHTML = demoBanner();

  try {
    const p = await api('/api/portfolio');
    setWallet(p.cash);
    document.getElementById('summary').innerHTML =
      card('Total value', money(p.total_value), 'Cash plus shares') +
      card('Available cash', money(p.cash), 'Virtual money') +
      card('Amount invested', money(p.invested), 'Cost of shares you own') +
      card('Profit / loss', signedMoney(p.profit), pct(p.profit_pct), cls(p.profit));

    const hb = document.getElementById('holdings');
    if (!p.holdings.length) {
      hb.innerHTML = '<div class="empty">You do not own any shares yet. <a href="explore.html">Explore companies</a> to get started.</div>';
    } else {
      hb.innerHTML = '<table><thead><tr><th>Company</th><th class="right">Shares</th><th class="right">Avg price</th>' +
        '<th class="right">Latest price</th><th class="right">Value</th><th class="right">Profit / loss</th></tr></thead><tbody>' +
        p.holdings.map(function (h) {
          return '<tr><td><a href="stock.html?t=' + h.ticker + '"><b>' + esc(h.name) + '</b></a> <span class="muted">' + h.ticker + '</span></td>' +
            '<td class="right">' + h.quantity + '</td><td class="right">' + money(h.avg_price) + '</td>' +
            '<td class="right">' + money(h.price) + '</td><td class="right">' + money(h.value) + '</td>' +
            '<td class="right ' + cls(h.profit) + '">' + signedMoney(h.profit) + ' (' + pct(h.profit_pct) + ')</td></tr>';
        }).join('') + '</tbody></table>';
    }
  } catch (e) {
    toast(e.message, true);
  }

  try {
    const t = await api('/api/portfolio/transactions');
    const box = document.getElementById('tx');
    if (!t.transactions.length) {
      box.innerHTML = '<div class="empty">No transactions yet.</div>';
    } else {
      box.innerHTML = '<table><thead><tr><th>Date</th><th>Type</th><th>Company</th><th class="right">Shares</th>' +
        '<th class="right">Price</th><th class="right">Total</th></tr></thead><tbody>' +
        t.transactions.map(function (x) {
          return '<tr><td class="nowrap">' + shortDate(x.created_at) + '</td>' +
            '<td><span class="pill ' + (x.type === 'BUY' ? '' : 'warn') + '">' + x.type + '</span></td>' +
            '<td><a href="stock.html?t=' + x.ticker + '">' + x.ticker + '</a></td>' +
            '<td class="right">' + x.quantity + '</td><td class="right">' + money(x.price) + '</td>' +
            '<td class="right">' + money(x.total) + '</td></tr>';
        }).join('') + '</tbody></table>';
    }
  } catch (e) {
    toast(e.message, true);
  }
}

start();
