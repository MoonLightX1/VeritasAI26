// login page

const form = document.getElementById('form');
const errBox = document.getElementById('err');
const submit = document.getElementById('submit');

function showErr(msg) {
  errBox.textContent = msg;
  errBox.classList.remove('hidden');
}

// if already logged in just skip ahead
api('/api/auth/me', { noRedirect: true }).then(function () {
  location.href = 'dashboard.html';
}).catch(function () {});

form.addEventListener('submit', async function (e) {
  e.preventDefault();
  errBox.classList.add('hidden');
  submit.disabled = true;
  submit.textContent = 'Logging in...';
  try {
    await api('/api/auth/login', {
      method: 'POST',
      noRedirect: true,
      body: {
        identifier: document.getElementById('ident').value,
        password: document.getElementById('pw').value,
        remember: document.getElementById('remember').checked
      }
    });
    location.href = 'dashboard.html';
  } catch (err) {
    showErr(err.message);
    submit.disabled = false;
    submit.textContent = 'Log in';
  }
});

document.getElementById('themeSlot').innerHTML = themeButton();
