const api = '/api/v1';
const $ = (selector) => document.querySelector(selector);
let currentRun = null;
let currentRevision = null;
let shownVideo = '';
let shownStatus = null;
function notice(message) { $('#notice').textContent = message; }
async function request(path, options = {}) {
  const response = await fetch(api + path, options);
  if (!response.ok) {
    let body = await response.json().catch(() => ({}));
    throw new Error(body.detail?.message || JSON.stringify(body.detail) || `HTTP ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}
function payload() {
  const form = $('#settings');
  return {
    theme: form.theme.value, custom_theme: form.custom_theme.value || null,
    target_duration: Number(form.target_duration.value), narration_speed: Number(form.narration_speed.value),
    tone: form.tone.value || null, perspective: form.perspective.value, audience: form.audience.value,
    language: form.language.value, premise: form.premise.value, avoid: form.avoid.value
  };
}
function loadSettings(data) {
  const form = $('#settings');
  for (const [key, value] of Object.entries(data)) {
    if (form[key]) form[key].value = value ?? '';
  }
}
async function clips() {
  const items = await request('/clips');
  $('#clips').replaceChildren(...items.map(item => {
    const li = document.createElement('li');
    li.textContent = `${item.width}×${item.height}, ${item.duration.toFixed(1)}s `;
    const remove = document.createElement('button'); remove.textContent = 'Remove';
    remove.onclick = () => act(async () => { await request(`/clips/${item.id}`, {method:'DELETE'}); await clips(); });
    li.append(remove); return li;
  }));
}
async function runs() {
  const items = await request('/runs');
  const select = $('#runs');
  const selected = currentRun || select.value;
  select.replaceChildren(new Option('Select a run', ''), ...items.map(item => new Option(`${item.title || item.theme} · ${item.status} · ${item.id.slice(0,8)}`, item.id)));
  select.value = selected;
}
function copyEditor(value) {
  const section = document.createElement('div'); section.className = 'copy-card';
  for (const key of ['title','caption','hashtags']) {
    const label = document.createElement('label'); label.textContent = key;
    const input = document.createElement(key === 'caption' ? 'textarea' : 'input'); input.dataset.field = key;
    input.value = key === 'hashtags' ? value[key].join(' ') : value[key]; label.append(input); section.append(label);
  }
  return section;
}
async function refresh() {
  if (!currentRun) return;
  const run = await request(`/runs/${currentRun}`);
  $('#status').textContent = `Status: ${run.status}${run.error ? ' · ' + run.error : ''}`;
  const revision = run.revisions.at(-1);
  if (revision && (currentRevision !== revision.number || run.status !== shownStatus || run.status === 'awaiting_review' && !shownVideo)) {
    currentRevision = revision.number;
    const detail = await request(`/runs/${currentRun}/revisions/${currentRevision}`);
    $('#story-title').textContent = detail.model_info?.story_title || '';
    $('#story-meta').textContent = detail.model_info?.word_count ? `${detail.model_info.word_count} words · ${Math.round(detail.model_info.estimated_duration_seconds)} seconds estimated` : '';
    $('#story').textContent = detail.story || '';
    $('#continuity-note').textContent = detail.summary || '';
    $('#evaluation').textContent = (detail.evaluation?.reasons || []).join(' • ');
    shownStatus = run.status;
    $('#copy').replaceChildren(...(detail.posting_copy ? [copyEditor(detail.posting_copy)] : []));
    if (run.status === 'awaiting_review' || run.status === 'approved') {
      shownVideo = `${currentRun}-${currentRevision}`;
      $('#video').src = `${api}/runs/${currentRun}/video?preview=${Date.now()}`;
    }
  }
  $('#approve').disabled = run.status !== 'awaiting_review';
  $('#retry').disabled = run.status !== 'failed';
  $('#delete-run').disabled = !['failed', 'awaiting_review', 'approved'].includes(run.status);
  $('#download').href = run.approved_revision_id ? `${api}/runs/${currentRun}/video?download=true` : '#';
  await runs();
}
async function act(action) { try { await action(); notice('Saved.'); } catch (error) { notice(error.message); } }
$('#save').onclick = () => act(async () => { await request('/settings', {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())}); });
$('#generate').onclick = () => act(async () => { const run = await request('/runs', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({overrides:payload()})}); currentRun = run.id; currentRevision = null; shownVideo = ''; shownStatus = null; await refresh(); });
$('#clip').onchange = () => act(async () => { const file = $('#clip').files[0]; if (!file) return; const form = new FormData(); form.append('file',file); await request('/clips',{method:'POST',body:form}); await clips(); });
$('#runs').onchange = () => { currentRun = $('#runs').value; currentRevision = null; shownVideo = ''; shownStatus = null; act(refresh); };
async function revise(kind, note) { await request(`/runs/${currentRun}/revisions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,note})}); currentRevision = null; shownVideo = ''; shownStatus = null; await refresh(); }
$('#revise-story').onclick = () => act(() => revise('story',$('#story-note').value));
$('#revise-position').onclick = () => act(() => revise('subtitle_position',$('#position-note').value));
$('#approve').onclick = () => act(async () => { await request(`/runs/${currentRun}/approve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision_no:currentRevision})}); await refresh(); });
$('#retry').onclick = () => act(async () => { await request(`/runs/${currentRun}/retry`,{method:'POST'}); await refresh(); });
$('#delete-run').onclick = () => {
  if (!currentRun || !confirm('Permanently delete this story, all revisions, and generated files? Uploaded clips will be kept.')) return;
  return act(async () => {
    await request(`/runs/${currentRun}`, {method:'DELETE'});
    currentRun = null; currentRevision = null; shownVideo = ''; shownStatus = null;
    $('#runs').value = '';
    $('#status').textContent = 'No run selected.';
    $('#video').removeAttribute('src'); $('#video').load();
    for (const id of ['story-title', 'story-meta', 'story', 'continuity-note', 'evaluation']) $(`#${id}`).textContent = '';
    $('#copy').replaceChildren();
    $('#approve').disabled = true; $('#retry').disabled = true; $('#delete-run').disabled = true;
    $('#download').href = '#';
    await runs();
  });
};
$('#save-copy').onclick = () => act(async () => { const section = $('.copy-card'); const field = key => section.querySelector(`[data-field="${key}"]`).value; const copy = {title:field('title'),caption:field('caption'),hashtags:field('hashtags').split(/\s+/).filter(Boolean)}; await request(`/runs/${currentRun}/revisions/${currentRevision}/posting-copy`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(copy)}); });
Promise.all([request('/settings'),clips(),runs()]).then(([settings]) => loadSettings(settings)).catch(error => notice(error.message));
setInterval(() => refresh().catch(error => notice(error.message)),3000);
