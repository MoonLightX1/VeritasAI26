// signup page, every account here is a demo account

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
document.getElementById('demoNote').classList.remove('hidden');
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

function needsParent() {
  const age = ageFromBirth();
  if (IS_DEMO) return true;
  return age !== null && age < 18;
}

function updateParent() {
  const age = ageFromBirth();
  const show = needsParent();
  parentBox.classList.toggle('hidden', !show);
  const hint = document.getElementById('birthHint');
  if (age === null) { hint.textContent = 'This just tells us which age group you are in.'; hint.className = 'hint muted'; }
  else if (age < 6 || age > 110) setHint(hint, 'Hmm, that birthday does not look right.', false);
  else setHint(hint, 'You are ' + age + '.', true);

  const why = document.getElementById('parentWhy');
  if (age !== null && age >= 18) {
    why.textContent = 'Demo accounts always need parent or guardian info, even if you are an adult.';
  } else {
    why.textContent = 'You are under 18, so we need a parent or guardian on your account. They should be okay with you using MoneySprout.';
  }
}
birth.max = new Date().toISOString().slice(0, 10);
birth.addEventListener('input', updateParent);
birth.addEventListener('change', updateParent);
updateParent();

// check if username is free after they stop typing
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

// returns an error message or null
function quickCheck() {
  if (!val('first')) return 'What is your first name?';
  if (!val('last')) return 'What is your last name?';
  const age = ageFromBirth();
  if (age === null) return 'When is your birthday?';
  if (age < 6 || age > 110) return 'That birthday does not look right. You must be at least 6 to sign up.';
  if (!val('country')) return 'Which country are you in?';
  if (!val('region')) return 'Which state or region are you in?';
  if (!val('grade')) return 'Pick your school level.';
  if (!userInput.value.trim()) return 'Pick a username.';
  if (!EMAIL_RE.test(emailInput.value.trim())) return 'That email does not look right.';
  if (!pw.value) return 'You need a password.';
  if (pw.value !== pw2.value) return 'Passwords do not match.';
  if (!val('exp')) return 'Tell us how much you know about stocks so far.';
  if (!val('goal')) return 'Pick a main goal.';
  if (!interests().length) return 'Pick at least one thing you are into.';

  if (needsParent()) {
    if (val('pname').length < 2) return 'Enter your parent or guardian\'s full name.';
    if (!val('prel')) return 'Pick how your parent or guardian is related to you.';
    if (val('pphone').replace(/\D/g, '').length < 7) return 'Enter a phone number for your parent or guardian.';
    if (!EMAIL_RE.test(pemail.value.trim())) return 'Enter your parent or guardian\'s email.';
    if (pemail.value.trim().toLowerCase() === emailInput.value.trim().toLowerCase()) return 'Use your parent or guardian\'s email, not yours.';
    if (!document.getElementById('pconsent').checked) return 'Check the box to confirm your parent or guardian knows about this account.';
  }
  if (!document.getElementById('terms').checked) return 'Check the box at the bottom to keep going.';
  return null;
}

form.addEventListener('submit', async function (e) {
  e.preventDefault();
  errBox.classList.add('hidden');

  // quick checks here, the server checks everything again
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
