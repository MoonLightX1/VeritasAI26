// light / dark mode
// this loads in the head so the page never flashes the wrong color

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
    // let the chart know so it can redraw
    window.dispatchEvent(new Event('themechange'));
    document.querySelectorAll('.theme-btn').forEach(function (b) { b.textContent = t === 'dark' ? 'Light' : 'Dark'; });
  };

  window.toggleTheme = function () {
    window.setTheme(window.currentTheme() === 'dark' ? 'light' : 'dark');
  };

  // button html, pages drop this in wherever they want the toggle
  window.themeButton = function () {
    return '<button class="btn light sm theme-btn" type="button" onclick="toggleTheme()">' +
      (window.currentTheme() === 'dark' ? 'Light' : 'Dark') + '</button>';
  };

  document.documentElement.setAttribute('data-theme', saved() || (systemDark() ? 'dark' : 'light'));
})();
