// notes page, list on the left, reader/editor on the right

const listBox = document.getElementById('list');
const searchIn = document.getElementById('search');
const filterSel = document.getElementById('filter');
const sortSel = document.getElementById('sort');
const countBox = document.getElementById('count');
const reader = document.getElementById('reader');
const editor = document.getElementById('editor');
const blank = document.getElementById('blank');
const titleIn = document.getElementById('title');
const contentIn = document.getElementById('content');
const companySel = document.getElementById('company');
const counter = document.getElementById('counter');
const dirtyBox = document.getElementById('dirty');

let notes = [];
let currentId = null;   // null for a new note
let editing = false;
let dirty = false;
let timer = null;

// which panel is showing
function show(which) {
  reader.classList.toggle('hidden', which !== 'reader');
  editor.classList.toggle('hidden', which !== 'editor');
  blank.classList.toggle('hidden', which !== 'blank');
  editing = which === 'editor';
}

function words(text) {
  const t = text.trim();
  return t ? t.split(/\s+/).length : 0;
}

// plain text to simple html (bullets, headings, paragraphs)
function renderBody(text) {
  if (!text.trim()) return '<p class="muted">This note is empty. Hit Edit to write something.</p>';
  let out = '';
  let inList = false;
  let para = [];
  function flushPara() {
    if (para.length) out += '<p>' + para.join('<br>') + '</p>';
    para = [];
  }
  function closeList() {
    if (inList) out += '</ul>';
    inList = false;
  }
  text.split('\n').forEach(function (line) {
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    const head = line.match(/^#{1,3}\s+(.*)$/);
    if (bullet) {
      flushPara();
      if (!inList) { out += '<ul>'; inList = true; }
      out += '<li>' + esc(bullet[1]) + '</li>';
    } else if (head) {
      flushPara(); closeList();
      out += '<h3>' + esc(head[1]) + '</h3>';
    } else if (!line.trim()) {
      flushPara(); closeList();
    } else {
      closeList();
      para.push(esc(line));
    }
  });
  flushPara(); closeList();
  return out;
}

function dayLabel(iso) {
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return 'Today';
  const y = new Date(); y.setDate(y.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return 'Yesterday';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function sorted() {
  const list = notes.slice();
  const how = sortSel.value;
  if (how === 'az') list.sort(function (a, b) { return a.title.localeCompare(b.title); });
  else if (how === 'old') list.sort(function (a, b) { return a.updated_at < b.updated_at ? -1 : 1; });
  else list.sort(function (a, b) { return a.updated_at < b.updated_at ? 1 : -1; });
  return list;
}

function renderList() {
  countBox.textContent = notes.length + (notes.length === 1 ? ' note' : ' notes');
  if (!notes.length) {
    listBox.innerHTML = '<div class="empty small">No notes found.</div>';
    return;
  }
  listBox.innerHTML = sorted().map(function (n) {
    const snippet = n.content.replace(/\s+/g, ' ').trim().slice(0, 90);
    return '<div class="note-item' + (n.id === currentId ? ' on' : '') + '" data-id="' + n.id + '" tabindex="0">' +
      '<div class="note-item-top"><b>' + esc(n.title) + '</b>' +
      (n.ticker ? '<span class="muted small">' + esc(n.ticker) + '</span>' : '') + '</div>' +
      '<div class="muted small">' + dayLabel(n.updated_at) + '</div>' +
      '<div class="muted small note-snip">' + (esc(snippet) || 'Empty note') + '</div></div>';
  }).join('');
}

function showNote(n) {
  currentId = n.id;
  document.getElementById('rTitle').textContent = n.title;
  document.getElementById('rMeta').innerHTML =
    (n.ticker ? '<a class="pill" href="stock?t=' + esc(n.ticker) + '">' + esc(n.ticker) + '</a>' : '') +
    '<span>Edited ' + shortDate(n.updated_at) + '</span>' +
    '<span>' + words(n.content) + ' words</span>';
  document.getElementById('rBody').innerHTML = renderBody(n.content);
  show('reader');
  renderList();
}

function startEdit(n, preTicker) {
  currentId = n ? n.id : null;
  titleIn.value = n ? n.title : '';
  contentIn.value = n ? n.content : '';
  companySel.value = n && n.ticker ? n.ticker : (preTicker || '');
  setDirty(false);
  updateCounter();
  show('editor');
  renderList();
  (n ? contentIn : titleIn).focus();
}

function setDirty(v) {
  dirty = v;
  dirtyBox.textContent = v ? 'Unsaved changes' : '';
}

function updateCounter() {
  counter.textContent = words(contentIn.value) + ' words, ' + contentIn.value.length + ' of 10000 characters';
}

// ask before throwing away edits
function okToLeave() {
  return !(editing && dirty) || confirm('You have unsaved changes. Leave without saving?');
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

function openFirst() {
  if (notes.length) showNote(sorted()[0]);
  else { currentId = null; show('blank'); }
}

listBox.addEventListener('click', function (e) {
  const item = e.target.closest('.note-item');
  if (!item || !okToLeave()) return;
  const n = notes.find(function (x) { return x.id === Number(item.dataset.id); });
  if (n) showNote(n);
});

listBox.addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && e.target.classList.contains('note-item')) e.target.click();
});

document.getElementById('newBtn').onclick = function () {
  if (okToLeave()) startEdit(null);
};

document.getElementById('editBtn').onclick = function () {
  const n = notes.find(function (x) { return x.id === currentId; });
  if (n) startEdit(n);
};

document.getElementById('cancelBtn').onclick = function () {
  if (!okToLeave()) return;
  setDirty(false);
  const n = notes.find(function (x) { return x.id === currentId; });
  if (n) showNote(n); else openFirst();
};

async function save() {
  const title = titleIn.value.trim();
  if (!title) { toast('Give your note a title first.', true); return; }
  const body = { title: title, content: contentIn.value, ticker: companySel.value || null };
  const done = busy(document.getElementById('saveBtn'), 'Saving');
  try {
    let saved;
    if (currentId) saved = await api('/api/notes/' + currentId, { method: 'PUT', body: body });
    else saved = await api('/api/notes', { method: 'POST', body: body });
    toast('Note saved');
    setDirty(false);
    await loadNotes();
    const n = notes.find(function (x) { return x.id === saved.id; });
    if (n) showNote(n);
  } catch (e) {
    toast(e.message, true);
  }
  done();
}

document.getElementById('saveBtn').onclick = save;

document.addEventListener('keydown', function (e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && editing) {
    e.preventDefault();
    save();
  }
});

document.getElementById('delBtn').onclick = async function () {
  if (!currentId || !confirm('Delete this note? This cannot be undone.')) return;
  try {
    await api('/api/notes/' + currentId, { method: 'DELETE' });
    toast('Note deleted');
    currentId = null;
    await loadNotes();
    openFirst();
  } catch (e) {
    toast(e.message, true);
  }
};

[titleIn, contentIn, companySel].forEach(function (el) {
  el.addEventListener('input', function () { setDirty(true); updateCounter(); });
  el.addEventListener('change', function () { setDirty(true); });
});

searchIn.addEventListener('input', function () {
  clearTimeout(timer);
  timer = setTimeout(loadNotes, 250);
});
filterSel.addEventListener('change', loadNotes);
sortSel.addEventListener('change', renderList);

// warn on tab close if unsaved
window.addEventListener('beforeunload', function (e) {
  if (editing && dirty) { e.preventDefault(); e.returnValue = ''; }
});

async function start() {
  await initShell('notes');
  const data = await api('/api/stocks/search?q=');
  const opts = data.results.map(function (c) {
    return '<option value="' + c.ticker + '">' + esc(c.name) + ' (' + c.ticker + ')</option>';
  }).join('');
  companySel.innerHTML = '<option value="">No company</option>' + opts;
  filterSel.innerHTML = '<option value="">All companies</option>' + opts;

  await loadNotes();
  const pre = new URLSearchParams(location.search).get('t');
  if (pre) {
    // came from a stock page, start a note for it
    startEdit(null, pre.toUpperCase());
    titleIn.value = pre.toUpperCase() + ' notes';
    setDirty(false);
  } else {
    openFirst();
  }
}

start();
