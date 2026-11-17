import {frameAt, applyImageDensity, watchDisplayDensity} from './density.js';
const $ = (id) => document.getElementById(id);
const reactions = [[-2, '😖', 'Horrible'], [-1, '👎', 'Dislike'], [0, '🤔', 'Good start'], [1, '👍', 'Good'], [2, '🤩', 'Awesome']];
let state, token, filter = 'new', styleFilter = 'all', selecting = false;
let selected = new Set(), currentId, region = null, fitMode = false, viewZoom = 1, sequenceTimer;
let currentStep = 0, toastTimer, refreshing = false, lastBoard = '', dialogOrder = [];
let lastFeedback = '', lastActivity = '', sending = false;
const styleName = (name) => name.replace(/[-_]/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const drafts = JSON.parse(sessionStorage.getItem('design-director-drafts') || '{}');
const escape = (text) => String(text ?? '').replace(/[&<>"']/g, (char) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
const artifact = () => state.artifacts.find((item) => item.id === currentId);
const time = (epoch) => new Date(epoch * 1000).toLocaleTimeString('en-GB', {timeZone: state?.settings.timezone || 'UTC', hour: '2-digit', minute: '2-digit', timeZoneName: 'short'});

function imageAttributes(item, step = 0) {
  const frame = frameAt(item, step);
  const dimensions = frame.dimensions || [];
  return `data-image-standard="${escape(frame.standard)}" data-image-retina="${escape(frame.retina || '')}" data-logical-width="${dimensions[0] || ''}" data-logical-height="${dimensions[1] || ''}" ${dimensions.length ? `width="${dimensions[0]}" height="${dimensions[1]}"` : ''}`;
}

function prepareImage(image, item, step = 0) {
  const frame = frameAt(item, step);
  image.dataset.imageStandard = frame.standard;
  image.dataset.imageRetina = frame.retina || '';
  image.dataset.logicalWidth = frame.dimensions?.[0] || '';
  image.dataset.logicalHeight = frame.dimensions?.[1] || '';
  applyImageDensity(image, window.devicePixelRatio || 1);
}

function updateImagesForDisplay(ratio = window.devicePixelRatio || 1) {
  document.querySelectorAll('img[data-image-standard]').forEach((image) => applyImageDensity(image, ratio));
  if ($('viewer').open && artifact()) updateDownloads();
}

function updateDownloads() {
  const item = artifact();
  if (!item) return;
  const frame = frameAt(item, currentStep);
  const dimensions = frame.dimensions || [];
  for (const scale of [1, 2]) {
    const link = $('download-' + scale);
    const available = scale === 1 || !!frame.retina;
    link.hidden = !available;
    link.href = `/download/${item.id}/${currentStep}/${scale}`;
    link.textContent = `${scale === 1 ? 'Standard 1×' : 'Retina 2×'}${dimensions.length ? ' · ' + dimensions.map((size) => size * scale).join(' × ') : ''}`;
  }
  const retinaPreview = (window.devicePixelRatio || 1) > 1 && frame.retina;
  $('image-density').textContent = retinaPreview ? 'Retina preview · 2× detail, actual size' : 'Standard preview · 1×';
  $('retina-pending').hidden = !!frame.retina;
}

function toast(message) {
  (document.querySelector('dialog[open]') || document.body).append($('toast'));
  $('toast').textContent = message;
  $('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('toast').hidden = true, 3200);
}

async function api(path, data) {
  const response = await fetch('/api/' + path, data ? {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Review-Token': token}, body: JSON.stringify(data)} : {});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Could not save');
  return result;
}

async function action(callback) {
  try { await callback(); } catch (error) { toast(error.message); }
}

function visibleArtifacts() {
  return state.artifacts.filter((item) => (styleFilter === 'all' || item.style === styleFilter) &&
    (filter === 'all' || filter === 'new' && !item.viewed || filter === 'seen' && item.viewed && !item.reviewed || filter === 'reviewed' && item.reviewed));
}

function reactionButtons(item) {
  return reactions.map(([value, emoji, label]) => `<button class="reaction ${item.reaction === value ? 'chosen' : ''}" data-reaction="${value}" title="${label}" aria-label="${label}" aria-pressed="${item.reaction === value}">${emoji}<span class="reaction-label">${label}</span></button>`).join('');
}

function renderBoard(force = false) {
  const signature = JSON.stringify([state.artifacts, filter, styleFilter, selecting, [...selected]]);
  if (!force && signature === lastBoard) return;
  lastBoard = signature;
  const items = visibleArtifacts();
  $('gallery').innerHTML = items.map((item) => `<article class="card ${selected.has(item.id) ? 'selected' : ''}" data-id="${item.id}" style="width:calc(${item.dimensions[0]}px * var(--zoom) + 2px)">
    <div class="card-top">${selecting ? `<input type="checkbox" class="select-box" aria-label="Select ${escape(item.title)}" ${selected.has(item.id) ? 'checked' : ''}>` : ''}<span class="card-title">${escape(item.title)}</span><span class="badge ${item.decision || (!item.viewed ? 'new' : '')}">${escape(item.decision || (!item.viewed ? 'NEW' : item.reviewed ? 'REVIEWED' : 'SEEN'))}</span><span class="card-time">${item.steps.length ? '▶ ' + item.steps.length + ' steps' : escape(item.dimensions.join(' × '))}</span></div>
    <div class="thumb-scroll"><button class="thumb" style="width:calc(${item.dimensions[0]}px * var(--zoom))" aria-label="Review ${escape(item.title)}"><img ${imageAttributes(item)} alt="${escape(item.title)}" loading="lazy" draggable="false"></button></div>
    <div class="card-bottom"><div><p class="card-caption">${escape(item.caption)}</p><p class="card-style">${escape(styleName(item.style))} · ${escape(styleName(item.component))}</p></div><div class="reaction-row">${reactionButtons(item)}</div></div></article>`).join('');
  updateImagesForDisplay();
  $('empty').hidden = !!items.length;
  const newCount = state.artifacts.filter((item) => !item.viewed).length;
  $('new-count').textContent = newCount;
  $('count-new').textContent = newCount;
  $('count-seen').textContent = state.artifacts.filter((item) => item.viewed && !item.reviewed).length;
  $('count-reviewed').textContent = state.artifacts.filter((item) => item.reviewed).length;
  $('count-all').textContent = state.artifacts.length;
  $('review-next').disabled = !state.artifacts.length;
  $('board-subtitle').textContent = state.artifacts.length ? 'A quick reaction. A precise note. The director takes it from there.' : 'Your director is preparing the first designs.';
  $('selection-bar').hidden = !selected.size;
  $('selected-count').textContent = `${selected.size} selected`;
  const styles = [...new Set(state.artifacts.map((item) => item.style))];
  $('style-filter').innerHTML = '<option value="all">All styles</option>' + styles.map((style) => `<option ${style === styleFilter ? 'selected' : ''} value="${escape(style)}">${escape(styleName(style))}</option>`).join('');
}

function renderStatus() {
  const running = state.jobs.find((job) => job.status === 'running');
  const queued = state.jobs.filter((job) => job.status === 'queued');
  const blocked = state.jobs.filter((job) => job.status === 'blocked');
  const seconds = Math.max(0, (state.deadline || 0) - Date.now() / 1000);
  $('status').textContent = running ? running.title : state.settings.paused ? 'Paused' : seconds && queued.length ? 'Starting next design' : seconds ? 'Queue complete' : state.settings.schedule.enabled ? 'Outside work hours' : 'Session complete';
  $('remaining').textContent = seconds ? `${Math.ceil(seconds / 60)} min left` : '';
  $('status-dot').classList.toggle('running', !!running);
  $('schedule-indicator').textContent = state.settings.schedule.enabled ? '· On' : '';
  $('engine').value = state.settings.engine || 'claude';
  $('project-name').textContent = state.settings.projectName || 'Your project';
  $('schedule-timezone').textContent = state.settings.timezone || 'UTC';
  $('board-status').textContent = `${state.jobs.filter((job) => job.status === 'done').length} jobs done · ${queued.length} queued${blocked.length ? ' · ' + blocked.length + ' need attention' : ''}`;
  $('display-note').textContent = 'Actual-size previews · Design target: ' + (state.settings.targetSize || [1920, 1080]).join(' × ');
  $('pause').disabled = state.settings.paused;
  $('start').textContent = seconds ? 'Reset work window' : 'Start session';
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    state = await api('state');
    renderBoard();
    renderStatus();
    if ($('viewer').open) { prepareImage($('full-image'), artifact(), currentStep); updateDownloads(); renderFeedback(); }
    if ($('group-dialog').open) {
      $('compare-grid').querySelectorAll('img[data-artifact]').forEach((image) => {
        const item = state.artifacts.find((entry) => entry.id === image.dataset.artifact);
        if (item) prepareImage(image, item);
      });
    }
    if ($('activity-dialog').open) renderActivity();
  } finally { refreshing = false; }
}

function toggleSelection(id) {
  selected.has(id) ? selected.delete(id) : selected.add(id);
  renderBoard(true);
}

async function feedback(data) {
  await api('feedback', data);
  toast(data.text ? 'Saved. Your director will take it from here.' : 'Saved');
  await refresh();
}

function fitImage() {
  const item = artifact();
  if (!item) return;
  const image = $('full-image');
  const area = $('image-scroll');
  const density = Number(image.dataset.renderDensity || 1);
  const width = Number(image.dataset.logicalWidth) || image.naturalWidth / density || item.dimensions[0];
  const height = Number(image.dataset.logicalHeight) || image.naturalHeight / density || item.dimensions[1];
  const padding = getComputedStyle(area);
  const availableWidth = area.clientWidth - parseFloat(padding.paddingLeft) - parseFloat(padding.paddingRight);
  const availableHeight = area.clientHeight - parseFloat(padding.paddingTop) - parseFloat(padding.paddingBottom);
  const scale = fitMode ? Math.min(1, availableWidth / width, availableHeight / height) : viewZoom;
  $('image-stage').style.width = `${Math.max(1, width * scale)}px`;
  $('image-stage').style.maxWidth = fitMode ? '100%' : 'none';
  $('image-stage').style.margin = fitMode ? 'auto' : '0';
  area.style.justifyContent = width * scale > availableWidth ? 'flex-start' : 'center';
  $('actual').classList.toggle('active', !fitMode && viewZoom === 1);
  $('fit').classList.toggle('active', fitMode);
  $('viewer-zoom').textContent = Math.round(scale * 100) + '%';
  drawRegions();
}

async function openViewer(id) {
  if (currentId) saveDraft();
  currentId = id;
  lastFeedback = '';
  region = null; currentStep = 0; fitMode = false; viewZoom = 1;
  stopSequence();
  const item = artifact();
  if (!item) return;
  if (!$('viewer').open) {
    dialogOrder = visibleArtifacts().map((entry) => entry.id);
    $('viewer').showModal();
  }
  $('viewer-title').textContent = item.title;
  $('viewer-meta').textContent = styleName(item.style) + ' / ' + styleName(item.component);
  $('viewer-position').textContent = `${dialogOrder.indexOf(id) + 1} of ${dialogOrder.length}`;
  $('previous').disabled = dialogOrder.length < 2; $('next').disabled = dialogOrder.length < 2;
  $('viewer-caption').textContent = item.caption;
  $('recommendation').textContent = item.recommendation || '';
  $('recommendation').hidden = !item.recommendation;
  $('comment').value = drafts[id]?.text || '';
  $('scope').value = drafts[id]?.scope || 'interpret';
  updateComposer();
  $('image-stage').classList.add('drawing');
  $('sequence').hidden = !item.steps.length;
  $('step').max = item.steps.length;
  $('step').value = 0;
  setStep(drafts[id]?.step || 0);
  region = drafts[id]?.region || null;
  updateDrawingTools();
  $('full-image').onload = fitImage;
  renderFeedback();
  requestAnimationFrame(fitImage);
  if (!item.viewed) { await api('viewed', {ids: [id]}); await refresh(); }
}

function renderFeedback() {
  const item = artifact();
  if (!item) return;
  const signature = JSON.stringify([currentId, item.reaction, item.decision, state.feedback]);
  $('region-note').hidden = !region;
  if (signature === lastFeedback) { drawRegions(); return; }
  lastFeedback = signature;
  $('viewer-reactions').innerHTML = reactionButtons(item);
  $('region-note').hidden = !region;
  const comments = state.feedback.filter((entry) => entry.ids.includes(currentId) || (entry.resolution?.scope || entry.scope) === 'style' && entry.styles.includes(item.style) || (entry.resolution?.scope || entry.scope) === 'component' && entry.components.includes(item.component));
  $('feedback-count').textContent = comments.length || '';
  $('comment-list').innerHTML = comments.length ? comments.map((entry) => `<div class="comment-item">${escape(entry.text || (entry.decision || reactions.find(([value]) => value === entry.reaction)?.[2]))}<small>${entry.region ? '◯ Area · ' : ''}${escape(entry.resolution?.scope || entry.scope)} · ${entry.processed ? 'Applied' : 'For director'} · ${time(entry.created)}</small>${entry.resolution?.reason ? `<details><summary>Director’s response</summary><small>${escape(entry.resolution.reason)}</small></details>` : ''}</div>`).join('') : '<p class="comment-empty">Your notes and the director’s responses will appear here.</p>';
  drawRegions();
}

function drawRegions() {
  const svg = $('annotations');
  const bounds = $('image-stage').getBoundingClientRect();
  svg.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`);
  const saved = state.feedback.filter((entry) => entry.ids.includes(currentId) && entry.region && (entry.region.step || 0) === currentStep).map((entry) => entry.region);
  svg.innerHTML = [...saved, ...(region ? [region] : [])].map((area, index) => {
    const x = area.x * bounds.width, y = area.y * bounds.height, w = area.w * bounds.width, h = area.h * bounds.height;
    const attrs = `fill="#eb9d3215" stroke="${index >= saved.length ? '#ed7b31' : '#519b79'}" stroke-width="2" vector-effect="non-scaling-stroke"`;
    if (area.shape === 'freehand') {
      const path = area.points.map(([px, py], pointIndex) => `${pointIndex ? 'L' : 'M'}${px * bounds.width},${py * bounds.height}`).join(' ');
      return `<path d="${path}" fill="none" stroke="${index >= saved.length ? '#ed7b31' : '#519b79'}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" ${index >= saved.length ? 'data-draft="true" pointer-events="stroke"' : ''}/>`;
    }
    return area.shape === 'ellipse' ? `<ellipse cx="${x + w / 2}" cy="${y + h / 2}" rx="${w / 2}" ry="${h / 2}" ${attrs}/>` : `<rect x="${x}" y="${y}" width="${w}" height="${h}" ${attrs}/>`;
  }).join('');
}

function setStep(step) {
  currentStep = Number(step);
  $('step').value = currentStep;
  prepareImage($('full-image'), artifact(), currentStep);
  updateDownloads();
  $('step-caption').textContent = currentStep ? artifact().stepCaptions?.[currentStep - 1] || `Step ${currentStep}` : 'Overview';
  region = null;
  updateDrawingTools();
  $('region-note').hidden = true;
  drawRegions();
}

function stopSequence() { clearInterval(sequenceTimer); sequenceTimer = null; $('play').textContent = '▶ Play'; }

function openGroup() {
  if (!selected.size) return;
  const items = state.artifacts.filter((item) => selected.has(item.id));
  $('group-title').textContent = `${items.length} designs · one conversation`;
  $('compare-grid').innerHTML = items.map((item) => `<figure style="width:calc(${item.dimensions[0]}px * var(--compare-scale, 1))"><figcaption>${escape(item.title)} · ${escape(item.style)}</figcaption><img ${imageAttributes(item)} data-artifact="${item.id}" alt="${escape(item.title)}"></figure>`).join('');
  $('compare-grid').style.setProperty('--compare-scale', 1);
  $('compare-zoom').value = 100; $('compare-percent').textContent = '100%';
  updateImagesForDisplay();
  $('group-dialog').showModal();
}

function renderActivity() {
  const signature = JSON.stringify([state.jobs, state.events, state.settings.engine]);
  if (signature === lastActivity) return;
  lastActivity = signature;
  const expanded = new Set([...$('activity-content').querySelectorAll('details[open]')].map((item) => item.dataset.key));
  const jobCard = (job) => `<div class="activity-item ${job.status === 'running' ? 'running' : job.status === 'blocked' ? 'error' : ''}"><strong>${escape(job.title)}</strong><small>${job.status === 'running' ? 'Working now' : job.status === 'blocked' ? 'Needs attention' : job.status === 'done' ? 'Completed' : 'Up next'}${job.attempts > 1 ? ' · attempt ' + job.attempts : ''}</small>${job.error ? `<p>${escape(job.error)}</p>` : ''}${job.summary ? `<p>${escape(job.summary)}</p>` : ''}${job.status === 'blocked' ? `<button data-retry="${job.id}">Retry</button>` : ''}${job.processMarker ? `<details data-key="${job.id}" ${expanded.has(job.id) ? 'open' : ''}><summary>Session details</summary><div class="session-detail">${escape(job.engine === 'claude' ? 'Claude Code · background session' : 'Codex + Pen Dev')}<br>${escape(job.processMarker)}<br>${escape(job.logPath || '')}</div></details>` : ''}</div>`;
  const running = state.jobs.filter((job) => job.status === 'running');
  const blocked = state.jobs.filter((job) => job.status === 'blocked');
  const queued = state.jobs.filter((job) => job.status === 'queued').sort((a, b) => b.priority - a.priority || a.created - b.created);
  const done = state.jobs.filter((job) => job.status === 'done').sort((a, b) => b.finished - a.finished);
  $('activity-content').innerHTML = `<p class="desk-intro">${state.settings.engine === 'claude' ? 'Claude Code runs separate background sessions on this computer. These do not appear in an existing Claude desktop chat.' : 'Codex directs the Pen Dev canvas on this computer.'} Work pauses when this computer sleeps.</p>` + (running.length ? running.map(jobCard).join('') : '<div class="activity-item running"><strong>No design in progress</strong><small>' + (state.settings.paused ? 'Paused · your work is saved' : 'Waiting for the next work window or job') + '</small></div>') + (blocked.length ? '<section class="desk-section"><h3>Needs attention</h3>' + blocked.map(jobCard).join('') + '</section>' : '') + '<section class="desk-section"><h3>Next in line · ' + queued.length + '</h3>' + queued.slice(0, 5).map(jobCard).join('') + '</section>' + `<details class="desk-completed" data-key="completed" ${expanded.has('completed') ? 'open' : ''}><summary>Completed work · ${done.length}</summary>${done.map(jobCard).join('')}</details>` + '<section class="desk-section"><h3>Recent activity</h3>' + state.events.slice(0, 8).map((event) => `<div class="activity-item"><small>${time(event.created)}</small><p>${escape(event.text)}</p></div>`).join('') + '</section>';
}

function updateComposer() {
  $('send-comment').disabled = sending || !$('comment').value.trim();
  $('draft-status').textContent = $('comment').value ? 'Draft saved' : '';
}

function saveDraft() {
  if (!currentId) return;
  if ($('comment').value || region) drafts[currentId] = {text: $('comment').value, scope: $('scope').value, region, step: currentStep};
  else delete drafts[currentId];
  sessionStorage.setItem('design-director-drafts', JSON.stringify(drafts));
  updateComposer();
}

function updateDrawingTools() {
  $('image-stage').classList.add('drawing');
  $('clear-mark').hidden = !region;
  $('drawing-hint').textContent = region ? 'Click your mark, then Delete to clear. Draw again to replace it.' : 'Circle anything, then add a note.';
}

function clearMark() {
  region = null; saveDraft(); updateDrawingTools(); renderFeedback();
}

// Board and review controls.
$('filters').onclick = (event) => { const button = event.target.closest('[data-filter]'); if (!button) return; filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach((item) => (item.classList.toggle('active', item === button), item.setAttribute('aria-pressed', item === button))); renderBoard(); };
$('show-all').onclick = () => document.querySelector('[data-filter="all"]').click();
$('style-filter').onchange = (event) => { styleFilter = event.target.value; renderBoard(); };
function setBoardZoom(value) {
  document.documentElement.style.setProperty('--zoom', value / 100);
  $('card-size').value = value; $('board-zoom').textContent = value + '%';
}
$('card-size').oninput = (event) => setBoardZoom(Number(event.target.value));
$('board-actual').onclick = () => setBoardZoom(100);
$('board-fit').onclick = () => setBoardZoom(25);
$('select-mode').onclick = () => { selecting = !selecting; $('select-mode').classList.toggle('active', selecting); $('select-mode').setAttribute('aria-pressed', selecting); renderBoard(); };
$('clear-selection').onclick = () => { selected.clear(); renderBoard(); };
$('gallery').onclick = (event) => action(async () => {
  if (suppressClick) return;
  const card = event.target.closest('.card');
  if (!card) return;
  const reaction = event.target.closest('[data-reaction]');
  if (reaction) return feedback({ids: [card.dataset.id], reaction: Number(reaction.dataset.reaction), scope: 'screen'});
  if (selecting || event.shiftKey) return toggleSelection(card.dataset.id);
  if (event.target.closest('.thumb')) await openViewer(card.dataset.id);
});
$('review-next').onclick = () => action(() => openViewer((state.artifacts.find((item) => !item.viewed) || state.artifacts[0])?.id));
$('viewer-close').onclick = () => $('viewer').close();
$('viewer').onclose = () => { saveDraft(); stopSequence(); };
$('comment').oninput = saveDraft;
$('scope').onchange = saveDraft;
$('group-text').oninput = () => $('group-send').disabled = !$('group-text').value.trim();
$('session-open').onclick = () => { $('session-controls').hidden = !$('session-controls').hidden; $('session-open').setAttribute('aria-expanded', !$('session-controls').hidden); };
function navigate(offset) {
  if (!dialogOrder.length) return;
  const index = dialogOrder.indexOf(currentId);
  action(() => openViewer(dialogOrder[(index + offset + dialogOrder.length) % dialogOrder.length]));
}
$('previous').onclick = () => navigate(-1); $('next').onclick = () => navigate(1);
$('fit').onclick = () => { fitMode = true; fitImage(); }; $('actual').onclick = () => { fitMode = false; viewZoom = 1; fitImage(); };
$('zoom-in').onclick = () => { fitMode = false; viewZoom = Math.min(2, viewZoom + .25); fitImage(); };
$('zoom-out').onclick = () => { fitMode = false; viewZoom = Math.max(.25, viewZoom - .25); fitImage(); };
$('clear-region').onclick = clearMark;
$('clear-mark').onclick = clearMark;
$('viewer-reactions').onclick = (event) => { const button = event.target.closest('[data-reaction]'); if (button) action(() => feedback({ids: [currentId], reaction: Number(button.dataset.reaction), scope: 'screen'})); };
$('send-comment').onclick = () => action(async () => {
  if (sending || !$('comment').value.trim()) return;
  sending = true; updateComposer();
  try {
    await feedback({ids: [currentId], text: $('comment').value, region, scope: $('scope').value});
    $('comment').value = ''; region = null; saveDraft(); updateDrawingTools(); renderFeedback();
  } finally { sending = false; updateComposer(); }
});
$('mark-reviewed').onclick = () => action(async () => { await api('reviewed', {ids: [currentId]}); await refresh(); toast('Reviewed'); navigate(1); });
$('play').onclick = () => {
  if (sequenceTimer) return stopSequence();
  $('play').textContent = 'Ⅱ Pause';
  sequenceTimer = setInterval(() => setStep((currentStep + 1) % (artifact().steps.length + 1)), 1800);
};
$('step').oninput = (event) => { stopSequence(); setStep(event.target.value); };
$('compare').onclick = openGroup; $('group-comment').onclick = () => { openGroup(); $('group-text').focus(); };
$('compare-zoom').oninput = () => { $('compare-grid').style.setProperty('--compare-scale', Number($('compare-zoom').value) / 100); $('compare-percent').textContent = $('compare-zoom').value + '%'; };
$('compare-actual').onclick = () => { $('compare-zoom').value = 100; $('compare-zoom').oninput(); };
$('group-close').onclick = () => $('group-dialog').close();
$('group-send').onclick = () => action(async () => { await feedback({ids: [...selected], text: $('group-text').value, scope: $('group-scope').value}); $('group-text').value = ''; $('group-send').disabled = true; $('group-dialog').close(); selected.clear(); renderBoard(); });

// Draw directly on the image. Coordinates remain stable at every zoom level.
let areaStart, strokePoints = [];
function imagePoint(event) { const box = $('image-stage').getBoundingClientRect(); return [Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)), Math.max(0, Math.min(1, (event.clientY - box.top) / box.height))]; }
$('image-stage').onpointerdown = (event) => {
  if (event.button !== 0) return;
  stopSequence();
  event.preventDefault();
  if (event.target.closest('[data-draft]')) {
    $('image-scroll').focus();
    $('drawing-hint').textContent = 'Mark selected · press Delete or Backspace to clear.';
    return;
  }
  areaStart = imagePoint(event); strokePoints = [areaStart];
  $('image-stage').setPointerCapture(event.pointerId);
};
$('image-stage').onpointermove = (event) => {
  if (!areaStart) return;
  const point = imagePoint(event);
  const last = strokePoints[strokePoints.length - 1];
  if (Math.hypot(point[0] - last[0], point[1] - last[1]) < .002 || strokePoints.length >= 600) return;
  strokePoints.push(point);
  const xs = strokePoints.map(([x]) => x), ys = strokePoints.map(([, y]) => y);
  const x = Math.min(...xs), y = Math.min(...ys);
  region = {shape: 'freehand', step: currentStep, points: [...strokePoints], x, y, w: Math.max(...xs) - x, h: Math.max(...ys) - y};
  drawRegions();
};
$('image-stage').onpointerup = () => {
  if (!areaStart) return;
  areaStart = null;
  saveDraft(); updateDrawingTools(); renderFeedback();
  if (region) $('comment').focus();
};
$('image-stage').onpointercancel = () => { areaStart = null; clearMark(); };

// Rectangle selection across screenshot cards.
let marqueeStart, suppressClick = false;
$('gallery').onpointerdown = (event) => {
  if (!selecting || event.button !== 0 || event.target.closest('[data-reaction],input')) return;
  marqueeStart = {x: event.clientX, y: event.clientY, ids: event.shiftKey ? new Set(selected) : new Set()};
  $('gallery').setPointerCapture(event.pointerId);
  event.preventDefault();
};
$('gallery').onpointermove = (event) => {
  if (!marqueeStart) return;
  const left = Math.min(event.clientX, marqueeStart.x), top = Math.min(event.clientY, marqueeStart.y);
  const width = Math.abs(event.clientX - marqueeStart.x), height = Math.abs(event.clientY - marqueeStart.y);
  if (width + height < 8) return;
  suppressClick = true;
  Object.assign($('marquee').style, {left: left + 'px', top: top + 'px', width: width + 'px', height: height + 'px'});
  $('marquee').hidden = false;
  selected = new Set(marqueeStart.ids);
  document.querySelectorAll('.card').forEach((card) => {
    const box = card.getBoundingClientRect();
    if (box.left < left + width && box.right > left && box.top < top + height && box.bottom > top) selected.add(card.dataset.id);
    card.classList.toggle('selected', selected.has(card.dataset.id));
  });
};
$('gallery').onpointerup = () => { marqueeStart = null; $('marquee').hidden = true; renderBoard(); setTimeout(() => suppressClick = false, 50); };
$('gallery').onpointercancel = () => { marqueeStart = null; $('marquee').hidden = true; suppressClick = false; renderBoard(); };

// Bounded work sessions and optional daily schedule.
$('hours').oninput = () => $('hours-value').textContent = $('hours').value + ' hours';
$('engine').onchange = () => action(async () => { await api('control', {action: 'engine', engine: $('engine').value}); await refresh(); toast('Design tool changed. Work and feedback are preserved.'); });
$('start').onclick = () => action(async () => { await api('control', {action: 'run', hours: Number($('hours').value)}); await refresh(); toast('Director started. Come back whenever you like.'); });
$('pause').onclick = () => action(async () => { await api('control', {action: 'pause'}); await refresh(); toast('Stopping the worker. Your work is saved.'); });
let days = new Set([0, 1, 2, 3, 4]);
function renderDays() { $('weekdays').innerHTML = ['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((label, day) => `<button data-day="${day}" class="${days.has(day) ? 'active' : ''}" aria-label="${['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][day]}" aria-pressed="${days.has(day)}">${label}</button>`).join(''); }
$('schedule-open').onclick = () => {
  const schedule = state.settings.schedule;
  $('schedule-enabled').checked = schedule.enabled;
  $('schedule-start').value = schedule.start || '09:00'; $('schedule-end').value = schedule.end || '13:00';
  const date = new Date(Date.now() + 6 * 86400000).toLocaleDateString('en-CA', {timeZone: state?.settings.timezone || 'UTC'});
  $('schedule-through').value = schedule.through || date;
  days = new Set(schedule.days || [0, 1, 2, 3, 4]); renderDays(); $('schedule-dialog').showModal();
};
$('weekdays').onclick = (event) => { const button = event.target.closest('[data-day]'); if (!button) return; const day = Number(button.dataset.day); days.has(day) ? days.delete(day) : days.add(day); renderDays(); };
$('schedule-close').onclick = () => $('schedule-dialog').close();
$('schedule-save').onclick = () => action(async () => {
  await api('control', {action: 'schedule', schedule: {enabled: $('schedule-enabled').checked, start: $('schedule-start').value, end: $('schedule-end').value, through: $('schedule-through').value, days: [...days]}});
  $('schedule-dialog').close(); await refresh(); toast('Hours saved');
});
$('activity-open').onclick = () => { renderActivity(); $('activity-dialog').showModal(); };
$('activity-close').onclick = () => $('activity-dialog').close();
$('activity-content').onclick = (event) => { const button = event.target.closest('[data-retry]'); if (button) action(async () => { await api('control', {action: 'retry', id: button.dataset.retry}); await refresh(); }); };
window.addEventListener('resize', () => { if ($('viewer').open) fitImage(); });
document.addEventListener('keydown', (event) => { if (!$('viewer').open || ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) return; if ((event.key === 'Delete' || event.key === 'Backspace') && region) { event.preventDefault(); clearMark(); return; } if (event.key === 'ArrowRight') navigate(1); if (event.key === 'ArrowLeft') navigate(-1); });
watchDisplayDensity(updateImagesForDisplay);
await action(async () => { token = (await api('session')).token; await refresh(); });
setInterval(() => action(refresh), 4000);
