// settings page

const AGE_TEXT = { under_13: 'Under 13', '13_17': '13 to 17', '18_plus': '18 or older', unknown: 'N/A' };
const GRADE_TEXT = { elementary: 'Elementary school', middle_school: 'Middle school', high_school: 'High school',
  college: 'College', graduated: 'Finished school', other: 'Other' };
const REL_TEXT = { mother: 'Mother', father: 'Father', guardian: 'Legal guardian', grandparent: 'Grandparent', other: 'Other' };
const STATUS_PILL = {
  none: ['gray', 'Not asked yet'],
  pending: ['warn', 'Waiting on a parent'],
  approved: ['', 'Approved'],
  denied: ['bad', 'Denied']
};

function row(a, b) { return '<tr><td class="muted">' + a + '</td><td class="right">' + b + '</td></tr>'; }

const EXP_TEXT = { none: 'Nothing yet', a_little: 'A little', some: 'Some', lots: 'A lot' };
const GOAL_TEXT = { learn_basics: 'Learn the basics', school_project: 'School project', save_for_future: 'Get ready to invest someday',
  for_fun: 'Just for fun', teach_others: 'Teach someone else' };
const INT_TEXT = { tech: 'Tech', gaming: 'Gaming', sports: 'Sports', food: 'Food', fashion: 'Fashion', cars: 'Cars',
  entertainment: 'Movies and music', energy: 'Energy', health: 'Health', other: 'Something else' };

// anything empty shows as N/A
function na(v) { return v ? esc(v) : 'N/A'; }

function renderAccount() {
  const m = window.ME;
  const d = m.details || {};
  const place = function (a, b) { return a || b ? [a, b].filter(Boolean).join(', ') : ''; };
  document.getElementById('account').innerHTML =
    row('Username', na(m.username)) +
    row('Email', na(m.email)) +
    row('Name', na(d.full_name)) +
    row('Age range', AGE_TEXT[m.age_band] || 'N/A') +
    row('Country', na(d.country)) +
    row('State or region', na(d.region)) +
    row('School level', GRADE_TEXT[d.grade] || 'N/A') +
    row('School name', na(d.school)) +
    row('Stock experience', EXP_TEXT[d.experience] || 'N/A') +
    row('Main goal', GOAL_TEXT[d.goal] || 'N/A') +
    row('Interests', d.interests && d.interests.length ? esc(d.interests.map(function (i) { return INT_TEXT[i] || i; }).join(', ')) : 'N/A') +
    row('Joined', shortDate(m.created_at)) +
    row('Trades', m.transactions) +
    row('Watchlist companies', m.watchlist_count);
  document.getElementById('dname').value = m.display_name;
  document.getElementById('demoState').textContent = m.demo_mode
    ? 'Demo mode is on, so you can use the parent override and add funds.'
    : 'Demo mode is off.';
  renderParent();
}

// parent from signup
function renderParent() {
  const p = window.ME.parent || {};
  document.getElementById('parentInfo').innerHTML = '<table><tbody>' +
    row('Name', na(p.full_name)) +
    row('Relationship', REL_TEXT[p.relationship] || 'N/A') +
    row('Email', na(p.email)) +
    row('Phone', na(p.phone)) +
    '</tbody></table>';
}

async function loadPerm() {
  const d = await api('/api/parental-controls/status');
  const p = STATUS_PILL[d.status] || STATUS_PILL.none;
  document.getElementById('permStatus').innerHTML = '<span class="pill ' + p[0] + '">' + p[1] + '</span>' +
    (d.age_band === '18_plus' ? ' <span class="muted small">Adult account, no permission needed.</span>' : '');

  const actions = document.getElementById('permActions');
  if (d.status === 'none' || d.status === 'denied') {
    actions.innerHTML = '<button class="btn" id="reqBtn">Ask a parent to say okay</button>';
    document.getElementById('reqBtn').onclick = async function () {
      try {
        await api('/api/parental-controls/request', { method: 'POST' });
        toast('Request sent!');
        loadPerm();
      } catch (e) { toast(e.message, true); }
    };
  } else if (d.status === 'pending') {
    actions.innerHTML = '<span class="muted">Now a parent just needs to say okay.</span>';
  } else {
    actions.innerHTML = '';
  }

  // override buttons need a pending request and demo mode
  document.getElementById('permDemo').classList.toggle('hidden', !(d.demo_mode && d.status === 'pending'));

  const hist = document.getElementById('permHistory');
  if (!d.history.length) {
    hist.innerHTML = '<div class="muted small">Nothing yet.</div>';
  } else {
    hist.innerHTML = d.history.map(function (h) {
      return '<div class="row"><div><span class="pill ' + (STATUS_PILL[h.status] || ['', ''])[0] + '">' + h.status + '</span> ' +
        (h.demo_override ? '<span class="pill warn">Demo override</span> ' : '') +
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
  if (!v) { toast('Your name cannot be blank.', true); return; }
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
  if (!confirm('Start over with $10,000? Your shares and trades will be cleared.')) return;
  try {
    await api('/api/portfolio/reset', { method: 'POST', body: { confirm: true } });
    toast('Fresh start, you have $10,000 again');
    setWallet(10000);
  } catch (e) { toast(e.message, true); }
};

document.getElementById('delBtn').onclick = async function () {
  const pw = document.getElementById('delpw').value;
  if (!pw) { toast('Type your password first.', true); return; }
  if (!confirm('Really delete your account? You cannot undo this.')) return;
  try {
    await api('/api/auth/delete-account', { method: 'POST', body: { password: pw } });
    location.href = '/';
  } catch (e) { toast(e.message, true); }
};

async function start() {
  await initShell('settings');
  renderAccount();
  loadPerm();
}

start();
