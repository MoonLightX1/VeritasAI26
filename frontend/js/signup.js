// signup page, all accounts are demo accounts

const IS_DEMO = true;

const form = document.getElementById('form');
const errBox = document.getElementById('err');
const submit = document.getElementById('submit');
const userInput = document.getElementById('username');
const userHint = document.getElementById('userHint');
const emailInput = document.getElementById('email');
const emailHint = document.getElementById('emailHint');
const pw = document.getElementById('pw');
const pw2 = document.getElementById('pw2');
const pwHint = document.getElementById('pwHint');
const birth = document.getElementById('birth');
const parentBox = document.getElementById('parentBox');
const pemail = document.getElementById('pemail');
const pemailHint = document.getElementById('pemailHint');

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

let timer = null;

document.getElementById('themeSlot').innerHTML = themeButton();

function val(id) { return document.getElementById(id).value.trim(); }

function setHint(el, text, good) {
  el.textContent = text;
  el.className = 'hint ' + (text ? (good ? 'ok' : 'bad') : '');
}

// page text
document.title = 'Make a demo account - MoneySprout';
document.getElementById('title').textContent = 'Make a demo account';
submit.textContent = 'Make my account';

// birthday -> age
function ageFromBirth() {
  if (!birth.value) return null;
  const b = new Date(birth.value + 'T00:00:00');
  if (isNaN(b)) return null;
  const t = new Date();
  let age = t.getFullYear() - b.getFullYear();
  const m = t.getMonth() - b.getMonth();
  if (m < 0 || (m === 0 && t.getDate() < b.getDate())) age--;
  return age;
}

// parent info is always shown, but it is optional in the demo
function needsParent() {
  return true;
}

function updateParent() {
  const age = ageFromBirth();
  const show = needsParent();
  parentBox.classList.toggle('hidden', !show);
  const hint = document.getElementById('birthHint');
  if (age === null) { hint.textContent = 'This just tells us which age group you are in.'; hint.className = 'hint muted'; }
  else if (age < 6 || age > 110) setHint(hint, 'Hmm, that birthday does not look right.', false);
  else setHint(hint, 'You are ' + age + '.', true);

}
birth.max = new Date().toISOString().slice(0, 10);
birth.addEventListener('input', updateParent);
birth.addEventListener('change', updateParent);
updateParent();

// username check after they stop typing
userInput.addEventListener('input', function () {
  clearTimeout(timer);
  const v = userInput.value.trim();
  if (!v) { setHint(userHint, '', true); return; }
  if (!/^[A-Za-z0-9_]{3,20}$/.test(v)) {
    setHint(userHint, 'Use 3 to 20 letters, numbers or underscores.', false);
    return;
  }
  timer = setTimeout(async function () {
    try {
      const r = await api('/api/auth/username-check?username=' + encodeURIComponent(v), { noRedirect: true });
      setHint(userHint, r.available ? 'Username is available.' : r.reason, r.available);
    } catch (e) {}
  }, 300);
});

emailInput.addEventListener('blur', function () {
  const v = emailInput.value.trim();
  if (v && !EMAIL_RE.test(v)) setHint(emailHint, 'That email does not look right.', false);
  else setHint(emailHint, '', true);
});

function checkParentEmail() {
  const v = pemail.value.trim().toLowerCase();
  if (!v) { setHint(pemailHint, '', true); return; }
  if (!EMAIL_RE.test(v)) setHint(pemailHint, 'That email does not look right.', false);
  else if (v === emailInput.value.trim().toLowerCase()) setHint(pemailHint, 'Use your parent or guardian\'s email, not yours.', false);
  else setHint(pemailHint, '', true);
}
pemail.addEventListener('blur', checkParentEmail);

function checkMatch() {
  if (!pw2.value) { setHint(pwHint, '', true); return; }
  if (pw.value !== pw2.value) setHint(pwHint, 'Passwords do not match.', false);
  else setHint(pwHint, 'Passwords match.', true);
}
pw.addEventListener('input', checkMatch);
pw2.addEventListener('input', checkMatch);

function showErr(msg) {
  errBox.textContent = msg;
  errBox.classList.remove('hidden');
  window.scrollTo(0, 0);
}

function interests() {
  return Array.prototype.map.call(document.querySelectorAll('#interests input:checked'), function (i) { return i.value; });
}

// error message or null. only the password and a username or email are required
function quickCheck() {
  const u = userInput.value.trim();
  const em = emailInput.value.trim();
  if (!u && !em) return 'Enter a username or an email.';
  if (u && !/^[A-Za-z0-9_]{3,20}$/.test(u)) return 'Use 3 to 20 letters, numbers or underscores for the username.';
  if (em && !EMAIL_RE.test(em)) return 'That email does not look right.';
  if (!pw.value) return 'You need a password.';
  if (pw.value !== pw2.value) return 'Passwords do not match.';
  if (birth.value) {
    const age = ageFromBirth();
    if (age === null || age < 6 || age > 110) return 'That birthday does not look right. You must be at least 6 to sign up.';
  }
  const pe = pemail.value.trim().toLowerCase();
  if (pe && !EMAIL_RE.test(pe)) return 'Your parent or guardian\'s email does not look right.';
  if (pe && pe === em.toLowerCase()) return 'Use your parent or guardian\'s email, not yours.';
  if (!document.getElementById('terms').checked) return 'Check the box at the bottom to keep going.';
  return null;
}

form.addEventListener('submit', async function (e) {
  e.preventDefault();
  errBox.classList.add('hidden');

  // quick checks, server checks again
  const bad = quickCheck();
  if (bad) return showErr(bad);

  const body = {
    first_name: val('first'),
    last_name: val('last'),
    username: userInput.value,
    email: emailInput.value,
    password: pw.value,
    confirm_password: pw2.value,
    birth_date: birth.value,
    country: val('country'),
    region: val('region'),
    grade: val('grade'),
    school: val('school'),
    experience: val('exp'),
    goal: val('goal'),
    interests: interests(),
    heard_from: val('heard'),
    accept_terms: document.getElementById('terms').checked,
    demo: IS_DEMO
  };
  if (needsParent()) {
    body.parent = {
      full_name: val('pname'),
      relationship: val('prel'),
      email: pemail.value,
      phone: val('pphone'),
      consent: document.getElementById('pconsent').checked
    };
  }

  submit.disabled = true;
  const label = submit.textContent;
  submit.textContent = 'Setting things up...';
  try {
    await api('/api/auth/signup', { method: 'POST', noRedirect: true, body: body });
    location.href = 'dashboard';
  } catch (err) {
    showErr(err.message);
    submit.disabled = false;
    submit.textContent = label;
  }
});
