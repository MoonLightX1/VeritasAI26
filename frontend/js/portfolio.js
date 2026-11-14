// portfolio page

function card(label, value, sub, subClass, main) {
  return '<div class="stat' + (main ? ' main' : '') + '"><div class="label">' + label + '</div><div class="value">' + value +
    '</div>' + (sub ? '<div class="sub ' + (subClass || 'muted') + '">' + sub + '</div>' : '') + '</div>';
}

// adds the fake money, then reloads the numbers
async function deposit(amount, btn) {
  const done = busy(btn, 'Adding');
  try {
    const r = await api('/api/portfolio/deposit', { method: 'POST', body: { amount: amount } });
    toast('Added ' + money(r.added));
    document.getElementById('depAmt').value = '';
    setWallet(r.cash);
    await load();
  } catch (e) {
    toast(e.message, true);
  }
  done();
}

function setupDeposit() {
  const box = document.getElementById('depositCard');
  box.classList.remove('hidden');
  box.querySelectorAll('button[data-amt]').forEach(function (b) {
    b.onclick = function () { deposit(Number(b.dataset.amt), b); };
  });
  document.getElementById('depBtn').onclick = function () {
    const v = Number(document.getElementById('depAmt').value);
    if (!v || v < 1) { toast('Type an amount first.', true); return; }
    deposit(v, this);
  };
}

async function start() {
  await initShell('portfolio');
  if (window.ME.demo_mode) setupDeposit();
  await load();
}

async function load() {
  document.getElementById('banner').innerHTML = demoBanner();
  if (!document.getElementById('summary').innerHTML) {
    document.getElementById('summary').innerHTML = '<div class="skel skel-big"></div>';
    document.getElementById('holdings').innerHTML = skeletonRows(3);
    document.getElementById('tx').innerHTML = skeletonRows(3);
  }

  try {
    const p = await api('/api/portfolio');
    setWallet(p.cash);
    document.getElementById('summary').innerHTML =
      card('Portfolio value', money(p.total_value), '', '', true) +
      card('Cash', money(p.cash)) +
      card('Invested', money(p.invested)) +
      card('Profit / loss', signedMoney(p.profit), pct(p.profit_pct), cls(p.profit));

    const hb = document.getElementById('holdings');
    if (!p.holdings.length) {
      hb.innerHTML = '<div class="empty">No shares yet. <a href="explore">Find a company</a> to buy your first.</div>';
    } else {
      hb.innerHTML = '<table><thead><tr><th>Company</th><th class="right">Shares</th><th class="right">Avg price</th>' +
        '<th class="right">Latest price</th><th class="right">Value</th><th class="right">Profit / loss</th></tr></thead><tbody>' +
        p.holdings.map(function (h) {
          return '<tr><td><a href="stock?t=' + h.ticker + '"><b>' + esc(h.name) + '</b></a> <span class="muted">' + h.ticker + '</span></td>' +
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
            '<td><a href="stock?t=' + x.ticker + '">' + x.ticker + '</a></td>' +
            '<td class="right">' + x.quantity + '</td><td class="right">' + money(x.price) + '</td>' +
            '<td class="right">' + money(x.total) + '</td></tr>';
        }).join('') + '</tbody></table>';
    }
  } catch (e) {
    toast(e.message, true);
  }
}

start();