// landing page: theme button, and the preview logo falls back to letters if it can not load
document.getElementById('themeSlot').innerHTML = themeButton();
document.addEventListener('error', function (e) {
  const im = e.target;
  if (!im || im.tagName !== 'IMG' || !im.dataset.t) return;
  im.parentNode.classList.remove('img');
  im.parentNode.textContent = im.dataset.t.slice(0, 4);
}, true);
