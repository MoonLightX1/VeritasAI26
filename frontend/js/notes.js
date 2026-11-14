// notes page

const listBox = document.getElementById('list');
const titleIn = document.getElementById('title');
const contentIn = document.getElementById('content');
const companySel = document.getElementById('company');
const filterSel = document.getElementById('filter');
const searchIn = document.getElementById('search');
const stamp = document.getElementById('stamp');
const delBtn = document.getElementById('delBtn');

let notes = [];
let currentId = null; // null means a brand new note
let timer = null;

function fillEditor(n) {
  currentId = n ? n.id : null;
  titleIn.value = n ? n.title : '';
  contentIn.value = n ? n.content : '';
  companySel.value = n && n.ticker ? n.ticker : '';
  stamp.textContent = n ? 'Last saved ' + shortDate(n.updated_at) : 'New note';
  delBtn.classList.toggle('hidden', !n);
  renderList();
}

function renderList() {
  if (!notes.length) {
    listBox.innerHTML = '<div class="empty small">No notes found.</div>';
    return;
  }
  listBox.innerHTML = notes.map(function (n) {
    return '<div class="note-item' + (n.id === currentId ? ' on' : '') + '" data-id="' + n.id + '">' +
      '<b>' + esc(n.title) + '</b>' + (n.ticker ? ' <span class="pill">' + n.ticker + '</span>' : '') +
      '<div class="muted small">' + shortDate(n.updated_at) + '</div>' +
      '<div class="muted small">' + esc(n.content.slice(0, 70)) + '</div></div>';
  }).join('');
}

async function loadNotes() {
  const q = searchIn.value.trim();
  const t = filterSel.value;
  try {
    const d = await api('/api/notes?q=' + encodeURIComponent(q) + '&ticker=' + encodeURIComponent(t));
    notes = d.notes;
    renderList();
  } catch (e) {
    toast(e.message, true);
  }
}

listBox.addEventListener('click', function (e) {
  const item = e.target.closest('.note-item');
  if (!item) return;
  const n = notes.find(function (x) { return x.id === Number(item.dataset.id); });
  if (n) fillEditor(n);
});

document.getElementById('newBtn').onclick = function () {
  fillEditor(null);
  const pre = new URLSearchParams(location.search).get('t');
  if (pre) companySel.value = pre.toUpperCase();
  titleIn.focus();
};

document.getElementById('saveBtn').onclick = async function () {
  const title = titleIn.value.trim();
  if (!title) { toast('Give your note a title first.', true); return; }
  const body = { title: title, content: contentIn.value, ticker: companySel.value || null };
  try {
    let saved;
    if (currentId) saved = await api('/api/notes/' + currentId, { method: 'PUT', body: body });
    else saved = await api('/api/notes', { method: 'POST', body: body });
    toast('Note saved');
    currentId = saved.id;
    await loadNotes();
    const n = notes.find(function (x) { return x.id === saved.id; });
    if (n) fillEditor(n);
  } catch (e) {
    toast(e.message, true);
  }
};

delBtn.onclick = async function () {
  if (!currentId || !confirm('Delete this note? This cannot be undone.')) return;
  try {
    await api('/api/notes/' + currentId, { method: 'DELETE' });
    toast('Note deleted');
    fillEditor(null);
    loadNotes();
  } catch (e) {
    toast(e.message, true);
  }
};

searchIn.addEventListener('input', function () {
  clearTimeout(timer);
  timer = setTimeout(loadNotes, 250);
});
filterSel.addEventListener('change', loadNotes);

async function start() {
  await initShell('notes.html');
  const data = await api('/api/stocks/search?q=');
  const opts = data.results.map(function (c) {
    return '<option value="' + c.ticker + '">' + esc(c.name) + ' (' + c.ticker + ')</option>';
  }).join('');
  companySel.innerHTML = '<option value="">No company</option>' + opts;
  filterSel.innerHTML = '<option value="">All companies</option>' + opts;

  await loadNotes();
  const pre = new URLSearchParams(location.search).get('t');
  if (pre) {
    // coming from a stock page, start a new note for that company
    fillEditor(null);
    companySel.value = pre.toUpperCase();
    const first = pre.toUpperCase();
    titleIn.value = first + ' notes';
  } else if (notes.length) {
    fillEditor(notes[0]);
  } else {
    fillEditor(null);
  }
}

start();
