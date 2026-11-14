// settings page

const AGE_TEXT = { under_13: 'Under 13', '13_17': '13 to 17', '18_plus': '18 or older' };
const GRADE_TEXT = { elementary: 'Elementary school', middle_school: 'Middle school', high_school: 'High school',
  college: 'College', graduated: 'Finished school', other: 'Other' };
const REL_TEXT = { mother: 'Mother', father: 'Father', guardian: 'Legal guardian', grandparent: 'Grandparent', other: 'Other' };
const STATUS_PILL = {
  none: ['gray', 'Not asked yet'],
  pending: ['warn', 'Waiting for a parent'],
  approved: ['', 'Approved'],
  denied: ['bad', 'Denied']
};

function row(a, b) { return '<tr><td class="muted">' + a + '</td><td class="right">' + b + '</td></tr>'; }

function renderAccount() {
  const m = window.ME;
  document.getElementById('account').innerHTML =
    row('Username', esc(m.username)) +
    row('Email', esc(m.email)) +
    row('Age range', AGE_TEXT[m.age_band] || '') +
    (m.details ? row('Name', esc(m.details.full_name)) +
      row('Location', esc(m.details.region + ', ' + m.details.country)) +
      row('School level', GRADE_TEXT[m.details.grade] || '') : '') +
    row('Joined', shortDate(m.created_at)) +
    row('Practice trades', m.transactions) +
    row('Watchlist companies', m.watchlist_count) +
    row('Predictions', m.predictions + ' (coming later)');
  document.getElementById('dname').value = m.display_name;
  document.getElementById('demoState').textContent = m.demo_mode
    ? 'Demo mode is ON. Demo accounts can be made and the demo parent override is available.' +
      (m.is_demo ? ' This is a demo account.' : '')
    : 'Demo mode is OFF. Demo accounts and the demo parent override are disabled.';
  renderParent();
}

// shows the parent they gave us at signup
function renderParent() {
  const p = window.ME.parent;
  const box = document.getElementById('parentInfo');
  if (!p) {
    box.innerHTML = '<div class="muted small">No parent or guardian on file. Adult accounts do not need one.</div>';
    return;
  }
  box.innerHTML = '<table><tbody>' +
    row('Name', esc(p.full_name)) +
    row('Relationship', REL_TEXT[p.relationship] || '') +
    row('Email', esc(p.email)) +
    row('Phone', esc(p.phone)) +
    '</tbody></table>';
}

async function loadPerm() {
  const d = await api('/api/parental-controls/status');
  const p = STATUS_PILL[d.status] || STATUS_PILL.none;
  document.getElementById('permStatus').innerHTML = '<span class="pill ' + p[0] + '">' + p[1] + '</span>' +
    (d.age_band === '18_plus' ? ' <span class="muted small">Adult account, no permission needed.</span>' : '');

  const actions = document.getElementById('permActions');
  if (d.status === 'none' || d.status === 'denied') {
    actions.innerHTML = '<button class="btn" id="reqBtn">Ask a parent for permission</button>';
    document.getElementById('reqBtn').onclick = async function () {
      try {
        await api('/api/parental-controls/request', { method: 'POST' });
        toast('Request sent');
        loadPerm();
      } catch (e) { toast(e.message, true); }
    };
  } else if (d.status === 'pending') {
    actions.innerHTML = '<span class="muted">A parent needs to approve your request.</span>';
  } else {
    actions.innerHTML = '';
  }

  // override buttons only show when there is something pending and demo mode is on
  document.getElementById('permDemo').classList.toggle('hidden', !(d.demo_mode && d.status === 'pending'));

  const hist = document.getElementById('permHistory');
  if (!d.history.length) {
    hist.innerHTML = '<div class="muted small">Nothing yet.</div>';
  } else {
    hist.innerHTML = d.history.map(function (h) {
      return '<div class="row"><div><span class="pill ' + (STATUS_PILL[h.status] || ['', ''])[0] + '">' + h.status + '</span> ' +
        (h.demo_override ? '<span class="pill warn">DEMO OVERRIDE</span> ' : '') +
        '<span class="muted small">' + esc(h.note || '') + '</span></div>' +
        '<div class="muted small">' + shortDate(h.requested_at) + '</div></div>';
    }).join('');
  }
}

async function demoDecide(which) {
  try {
    await api('/api/parental-controls/' + which, { method: 'POST' });
    toast('Demo override: ' + (which === 'approve' ? 'approved' : 'denied'));
    loadPerm();
  } catch (e) { toast(e.message, true); }
}

document.getElementById('demoApprove').onclick = function () { demoDecide('approve'); };
document.getElementById('demoDeny').onclick = function () { demoDecide('deny'); };

document.getElementById('saveName').onclick = async function () {
  const v = document.getElementById('dname').value.trim();
  if (!v) { toast('Name cannot be empty.', true); return; }
  try {
    await api('/api/auth/display-name', { method: 'PUT', body: { display_name: v } });
    toast('Name saved');
    window.ME.display_name = v;
    document.querySelector('.who-name').textContent = v;
  } catch (e) { toast(e.message, true); }
};

document.getElementById('savePw').onclick = async function () {
  try {
    await api('/api/auth/password', {
      method: 'PUT',
      body: {
        current_password: document.getElementById('curpw').value,
        new_password: document.getElementById('newpw').value
      }
    });
    document.getElementById('curpw').value = '';
    document.getElementById('newpw').value = '';
    toast('Password changed');
  } catch (e) { toast(e.message, true); }
};

document.getElementById('resetBtn').onclick = async function () {
  if (!confirm('Reset your virtual portfolio back to $10,000? Your holdings and transactions will be removed.')) return;
  try {
    await api('/api/portfolio/reset', { method: 'POST', body: { confirm: true } });
    toast('Portfolio reset');
    setWallet(10000);
  } catch (e) { toast(e.message, true); }
};

document.getElementById('delBtn').onclick = async function () {
  const pw = document.getElementById('delpw').value;
  if (!pw) { toast('Type your password first.', true); return; }
  if (!confirm('Delete your account forever? This cannot be undone.')) return;
  try {
    await api('/api/auth/delete-account', { method: 'POST', body: { password: pw } });
    location.href = 'index.html';
  } catch (e) { toast(e.message, true); }
};

async function start() {
  await initShell('settings.html');
  renderAccount();
  loadPerm();
}

start();
