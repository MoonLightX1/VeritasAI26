// light/dark mode, loads in the head so there is no flash

(function () {
  function saved() {
    try { return localStorage.getItem('ms_theme'); } catch (e) { return null; }
  }

  function systemDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  window.currentTheme = function () {
    return document.documentElement.getAttribute('data-theme') || 'light';
  };

  window.setTheme = function (t) {
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('ms_theme', t); } catch (e) {}
    // tell the chart
    window.dispatchEvent(new Event('themechange'));
    document.querySelectorAll('.theme-btn').forEach(function (b) { b.textContent = t === 'dark' ? 'Light' : 'Dark'; });
  };

  window.toggleTheme = function () {
    window.setTheme(window.currentTheme() === 'dark' ? 'light' : 'dark');
  };

  // button html
  window.themeButton = function () {
    return '<button class="btn light sm theme-btn" type="button">' +
      (window.currentTheme() === 'dark' ? 'Light' : 'Dark') + '</button>';
  };

  // one click listener, no inline onclick because of the csp
  document.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('.theme-btn')) window.toggleTheme();
  });

  document.documentElement.setAttribute('data-theme', saved() || (systemDark() ? 'dark' : 'light'));
})();
