/* Virasat Atlas front end. Plain JS, no build step. All user text is inserted with
   textContent / text nodes, never innerHTML, so stored entries cannot inject markup. */
(() => {
  'use strict';

  const API = '/api/v1';
  const $ = (sel, root = document) => root.querySelector(sel);

  const TYPE_COLORS = {
    stepwell: '#1F5FA8', fort: '#8A3B2A', temple: '#D58A12', mosque: '#17806E',
    mausoleum: '#6D4C93', palace: '#C23B6A', 'harappan-site': '#7C6A2C', craft: '#4F8A2E', memorial: '#4B4F5C',
  };
  const TYPE_LABELS = {
    stepwell: 'Stepwell', fort: 'Fort', temple: 'Temple', mosque: 'Mosque', mausoleum: 'Mausoleum',
    palace: 'Palace', 'harappan-site': 'Harappan site', craft: 'Living craft', memorial: 'Memorial',
  };
  const LANG_LABELS = { en: 'English', hi: 'हिन्दी', gu: 'ગુજરાતી' };
  const GOLD = '#C9A227';
  const C_MIN = -30, C_MAX = 20;

  const state = {
    sites: [],
    looseEntries: [],
    meta: null,
    region: 'gujarat',   // state slug, or 'all' for All India
    markers: new Map(),
    selectedId: null,
    filters: { types: new Set(), eras: new Set(), themes: new Set(), unesco: false, from: C_MIN, to: C_MAX },
    query: '',
    trail: null,
    pick: null,       // { lat, lng } of the entry pin
    pinMarker: null,
    picking: false,
    dialogReturn: null,
  };

  /* ---------- helpers ---------- */
  function h(tag, props, ...kids) {
    const n = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v == null || v === false) continue;
        if (k === 'class') n.className = v;
        else if (k === 'text') n.textContent = v;
        else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
        else n.setAttribute(k, v === true ? '' : v);
      }
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return n;
  }

  const isMobile = () => window.matchMedia('(max-width: 760px)').matches;
  const ordinal = (n) => {
    const s = ['th', 'st', 'nd', 'rd'], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  };
  const centuryLabel = (c) => (c == null ? '' : c < 0 ? `${ordinal(-c)} century BCE` : `${ordinal(c)} century`);
  const humanize = (s) => String(s).replace(/-/g, ' ');
  const typeColor = (t) => TYPE_COLORS[t] || '#6B5E50';
  const typeLabel = (t) => TYPE_LABELS[t] || humanize(t || 'site');
  const dotFor = (t) => h('i', { class: 'dot', style: `background:${typeColor(t)}` });
  const siteById = (id) => state.sites.find((s) => s.id === id);

  async function api(path, opts = {}) {
    let res;
    try {
      res = await fetch(API + path, opts);
    } catch {
      throw new Error('Cannot reach the server. Check that it is running, then try again.');
    }
    if (!res.ok) {
      let msg = res.statusText || `Request failed (${res.status})`;
      try {
        const j = await res.json();
        const err = j.error || {};
        msg = err.message || (typeof j.detail === 'string' ? j.detail : msg);
        if (err.code === 'VALIDATION_ERROR' && Array.isArray(err.detail) && err.detail[0]) {
          const d = err.detail[0];
          const field = (d.loc || []).filter((p) => p !== 'body' && p !== 'query').join('.');
          msg = `${field || 'Input'}: ${d.msg}`;
        }
      } catch { /* non-JSON error body */ }
      const e = new Error(msg);
      e.status = res.status;
      throw e;
    }
    return res.status === 204 ? null : res.json();
  }

  function debounce(fn, ms) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  let toastTimer;
  function toast(msg, bad = false) {
    const t = $('#toast');
    t.textContent = msg;
    t.className = bad ? 'bad' : '';
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 4200);
  }

  /* ---------- map ---------- */
  const map = L.map('map', { zoomControl: false, minZoom: 4, maxZoom: 17 }).setView([22.4, 71.6], 7);
  L.control.zoom({ position: 'topright' }).addTo(map);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  const markerLayer = L.layerGroup().addTo(map);
  const trailLayer = L.layerGroup().addTo(map);
  const entryLayer = L.layerGroup().addTo(map);   // located entries that belong to no site

  /** Centre a point in the visible part of the map, not behind the panel or sheet. */
  function focusOn(lat, lng, zoom = 12) {
    const z = Math.max(map.getZoom(), zoom);
    const p = map.project([lat, lng], z);
    const shift = isMobile() ? L.point(0, window.innerHeight * 0.18) : L.point(-190, 0);
    map.flyTo(map.unproject(p.add(shift), z), z, { duration: 0.8 });
  }
  function fitTo(bounds, fly = false) {
    const mobile = isMobile();
    (fly ? map.flyToBounds : map.fitBounds).call(map, bounds, {
      paddingTopLeft: mobile ? [30, 130] : [Number.parseInt(getComputedStyle(document.documentElement).getPropertyValue('--panel-w'), 10) + 40, 40],
      paddingBottomRight: mobile ? [30, window.innerHeight * 0.5] : [40, 170],
      maxZoom: 12,
    });
  }

  function markerStyle(s, selected) {
    const u = s.unesco;
    return {
      radius: selected ? 13 : u ? 11 : 9,
      fillColor: typeColor(s.site_type),
      fillOpacity: 0.93,
      color: selected ? '#28306B' : u ? GOLD : '#FFF8E8',
      weight: selected ? 4 : u ? 4 : 2,
    };
  }

  function filteredSites() {
    const f = state.filters;
    return state.sites.filter((s) =>
      (!f.types.size || f.types.has(s.site_type)) &&
      (!f.eras.size || f.eras.has(s.era)) &&
      (!f.themes.size || (s.themes || []).some((t) => f.themes.has(t))) &&
      (!f.unesco || s.unesco) &&
      (s.century == null || (s.century >= f.from && s.century <= f.to)));
  }

  function renderMarkers() {
    const visible = filteredSites();
    const ids = new Set(visible.map((s) => s.id));
    for (const [id, m] of state.markers) {
      if (!ids.has(id)) { markerLayer.removeLayer(m); state.markers.delete(id); }
    }
    for (const s of visible) {
      if (state.markers.has(s.id)) continue;
      const m = L.circleMarker([s.lat, s.lng], markerStyle(s, s.id === state.selectedId));
      m.bindTooltip(h('span', { text: s.name }), { direction: 'top', offset: [0, -8] });
      m.on('click', () => openSite(s.id));
      m.addTo(markerLayer);
      state.markers.set(s.id, m);
    }
    renderTimelineBars();
    if (!state.query) renderBrowse();
    updateClearButton();
  }

  function restyleSelected(prevId) {
    for (const id of [prevId, state.selectedId]) {
      const s = id && siteById(id), m = id && state.markers.get(id);
      if (s && m) { m.setStyle(markerStyle(s, id === state.selectedId)); if (id === state.selectedId) m.bringToFront(); }
    }
  }

  /* ---------- tag chips ---------- */
  function tagChips(tag) {
    const frag = document.createDocumentFragment();
    if (tag) {
      if (tag.site_type) frag.append(h('span', { class: 'tag type' }, dotFor(tag.site_type), typeLabel(tag.site_type)));
      if (tag.era) frag.append(h('span', { class: 'tag era', text: tag.era }));
      if (tag.century != null) frag.append(h('span', { class: 'tag', text: centuryLabel(tag.century) }));
      for (const t of tag.themes || []) frag.append(h('span', { class: 'tag theme', text: humanize(t) }));
      if (tag.language) frag.append(h('span', { class: 'tag', text: LANG_LABELS[tag.language] || tag.language }));
    }
    return frag;
  }

  /** Live tag preview: debounced POST /tag as the user types. */
  function attachTagPreview(inputs, box, emptyMsg) {
    let seq = 0;
    const note = (msg) => { box.replaceChildren(h('span', { class: 'muted', text: msg })); };
    note(emptyMsg);
    const run = debounce(async () => {
      const text = inputs.map((i) => i.value).join('\n').trim();
      const mine = ++seq;
      if (text.length < 6) { note(emptyMsg); return; }
      try {
        const tag = await api('/tag', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
        if (mine !== seq) return;
        const chips = tagChips(tag);
        box.replaceChildren(chips.childNodes.length ? chips : h('span', { class: 'muted', text: 'No tags found yet. Mention a site type, era or place.' }));
      } catch {
        if (mine === seq) note('Tag preview is unavailable right now. You can still save.');
      }
    }, 450);
    inputs.forEach((i) => i.addEventListener('input', run));
    return { run, reset: () => { seq++; note(emptyMsg); } };
  }

  /* ---------- sheet (mobile) ---------- */
  const panel = $('#panel');
  function setSheet(s) {
    panel.dataset.sheet = s;
    $('#sheetHandle').setAttribute('aria-expanded', String(s !== 'peek'));
  }
  $('#sheetHandle').addEventListener('click', () => {
    const order = ['half', 'full', 'peek'];
    setSheet(order[(order.indexOf(panel.dataset.sheet) + 1) % order.length]);
  });

  /* ---------- search + browse list ---------- */
  const resultsEl = $('#results');
  const statusEl = $('#status');
  const listTitle = $('#listTitle');

  function highlightInto(node, text, query) {
    const terms = [...new Set(query.split(/[\s,.;:!?()"'\-]+/u).filter((t) => t.length >= 2))]
      .sort((a, b) => b.length - a.length)
      .map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    if (!terms.length) { node.textContent = text; return; }
    const re = new RegExp(terms.join('|'), 'giu');
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (!m[0]) { re.lastIndex++; continue; }
      if (m.index > last) node.append(text.slice(last, m.index));
      node.append(h('mark', { text: m[0] }));
      last = m.index + m[0].length;
    }
    node.append(text.slice(last));
  }

  function renderBrowse() {
    const list = filteredSites();
    listTitle.textContent = list.length === state.sites.length ? 'Sites on the map' : `Sites matching your filters`;
    statusEl.textContent = state.sites.length ? `${list.length} of ${state.sites.length} sites shown` : '';
    if (!list.length) {
      resultsEl.replaceChildren(h('li', { class: 'empty', text: state.sites.length ? 'No sites match these filters. Widen the century range or clear a filter.' : state.looseEntries.length ? `No heritage sites recorded here yet. ${state.looseEntries.length === 1 ? 'The field entry is shown as a hollow dot' : 'Field entries are shown as hollow dots'} on the map.` : 'No sites loaded yet.' }));
      return;
    }
    resultsEl.replaceChildren(...list
      .slice().sort((a, b) => a.name.localeCompare(b.name))
      .map((s) => h('li', null, h('button', {
        class: 'item', type: 'button',
        onclick: () => { goToSite(s); },
      },
      h('span', { class: 'item-head' }, dotFor(s.site_type), h('span', { class: 'item-title', text: s.name })),
      h('span', { class: 'item-meta', text: [typeLabel(s.site_type), s.era, s.district].filter(Boolean).join(', ') })))));
  }

  function goToSite(s) {
    if (isMobile()) setSheet('peek');
    focusOn(s.lat, s.lng, 12);
    openSite(s.id, { fly: false });
  }

  function renderResults(results, text) {
    listTitle.textContent = `Results for “${text}”`;
    statusEl.textContent = results.length ? `${results.length} result${results.length === 1 ? '' : 's'}` : '';
    if (!results.length) {
      resultsEl.replaceChildren(h('li', { class: 'empty', text: `Nothing matched “${text}”. Try another spelling, or a word from the site's name.` }));
      return;
    }
    resultsEl.replaceChildren(...results.map((r) => {
      const snippet = h('p', { class: 'snippet' });
      highlightInto(snippet, r.snippet || '', text);
      return h('li', null, h('button', { class: 'item', type: 'button', onclick: () => onResult(r) },
        h('span', { class: 'item-head' },
          dotFor((siteById(r.site_id || r.id) || {}).site_type),
          h('span', { class: 'item-title', text: r.title }),
          h('span', { class: 'kind', text: r.kind === 'site' ? 'Site' : 'Entry' }),
          h('span', { class: 'lang', text: LANG_LABELS[r.language] || r.language })),
        snippet));
    }));
  }

  function onResult(r) {
    if (isMobile()) setSheet('peek');
    if (r.lat != null && r.lng != null) focusOn(r.lat, r.lng, 13);
    const sid = r.kind === 'site' ? r.id : r.site_id;
    if (sid) openSite(sid, { fly: false });
    else {
      closeDrawer();
      L.popup({ closeButton: true }).setLatLng([r.lat, r.lng]).setContent(h('div', null, h('strong', { text: r.title }))).openOn(map);
    }
  }

  let searchSeq = 0;
  const runSearch = debounce(async () => {
    const text = $('#q').value.trim();
    state.query = text;
    if (!text) { renderBrowse(); return; }
    const mine = ++searchSeq;
    statusEl.textContent = 'Searching…';
    try {
      const r = await api(`/search?q=${encodeURIComponent(text)}&k=12${regionQuery('&')}`);
      if (mine === searchSeq) renderResults(r.results || [], text);
    } catch (e) {
      if (mine === searchSeq) {
        statusEl.textContent = '';
        resultsEl.replaceChildren(h('li', { class: 'empty', text: `Search failed: ${e.message}` }));
      }
    }
  }, 280);
  $('#q').addEventListener('input', () => { state.query = $('#q').value.trim(); runSearch(); });

  /* ---------- filters ---------- */
  function makeChip(group, value, label, count, colorType) {
    const b = h('button', { class: 'chip', type: 'button', 'aria-pressed': 'false' },
      colorType ? dotFor(colorType) : null, label, count != null ? h('span', { class: 'n', text: count }) : null);
    b.addEventListener('click', () => {
      const set = state.filters[group];
      set.has(value) ? set.delete(value) : set.add(value);
      b.setAttribute('aria-pressed', String(set.has(value)));
      renderMarkers();
    });
    return b;
  }

  function buildFilters() {
    const meta = state.meta || { types: [], eras: [], themes: [] };
    const types = meta.types.length ? meta.types : [...new Set(state.sites.map((s) => s.site_type))].map((v) => ({ value: v, count: null }));
    const eras = meta.eras.length ? meta.eras : [...new Set(state.sites.map((s) => s.era).filter(Boolean))].map((v) => ({ value: v, count: null }));
    const themes = meta.themes.length ? meta.themes : [...new Set(state.sites.flatMap((s) => s.themes || []))].map((v) => ({ value: v, count: null }));
    $('#chipTypes').replaceChildren(...types.map((t) => makeChip('types', t.value, typeLabel(t.value), t.count, t.value)));
    $('#chipEras').replaceChildren(...eras.map((t) => makeChip('eras', t.value, t.value, t.count)));
    $('#chipThemes').replaceChildren(...themes.map((t) => makeChip('themes', t.value, humanize(t.value), t.count)));

    const sel = $('#trailTheme');
    sel.replaceChildren(h('option', { value: '', text: 'Any theme' }), ...themes.map((t) => h('option', { value: t.value, text: humanize(t.value) })));

    $('#legendList').replaceChildren(
      ...Object.keys(TYPE_LABELS).map((t) => h('li', null, dotFor(t), TYPE_LABELS[t])),
      h('li', null, h('i', { class: 'dot entry-dot' }), 'Field entry, no site yet'));
  }

  $('#chipUnesco').addEventListener('click', (e) => {
    state.filters.unesco = !state.filters.unesco;
    e.currentTarget.setAttribute('aria-pressed', String(state.filters.unesco));
    renderMarkers();
  });
  $('#clearFilters').addEventListener('click', () => {
    const f = state.filters;
    f.types.clear(); f.eras.clear(); f.themes.clear(); f.unesco = false; f.from = C_MIN; f.to = C_MAX;
    $('#tlFrom').value = C_MIN; $('#tlTo').value = C_MAX;
    document.querySelectorAll('.chips .chip, #chipUnesco').forEach((c) => c.setAttribute('aria-pressed', 'false'));
    updateTimelineLabel();
    renderMarkers();
  });
  function updateClearButton() {
    const f = state.filters;
    $('#clearFilters').hidden = !(f.types.size || f.eras.size || f.themes.size || f.unesco || f.from !== C_MIN || f.to !== C_MAX);
  }

  /* ---------- timeline ---------- */
  function renderTimelineBars() {
    const counts = new Array(C_MAX - C_MIN + 1).fill(0);
    for (const s of state.sites) if (s.century != null && s.century >= C_MIN && s.century <= C_MAX) counts[s.century - C_MIN]++;
    const max = Math.max(1, ...counts);
    $('#tlBars').replaceChildren(...counts.map((n, i) => {
      const c = i + C_MIN;
      const bar = h('i', { class: c === 0 ? 'zero' : '' });
      bar.style.height = n ? `${Math.round(12 + (n / max) * 88)}%` : '3px';
      if (!n) bar.style.background = 'var(--sandstone-deep)';
      if (c < state.filters.from || c > state.filters.to) bar.classList.add('off');
      return bar;
    }));
  }
  function updateTimelineLabel() {
    const { from, to } = state.filters;
    const lab = (c) => (c < 0 ? `${ordinal(-c)} c. BCE` : `${ordinal(c || 1)} c.`);
    $('#tlLabel').textContent = from === C_MIN && to === C_MAX ? 'All centuries' : `${lab(from)} to ${lab(to)}`;
    $('#tlReset').hidden = from === C_MIN && to === C_MAX;
  }
  function onSlider(which) {
    const f = state.filters, a = $('#tlFrom'), b = $('#tlTo');
    if (which === 'from' && +a.value > +b.value) b.value = a.value;
    if (which === 'to' && +b.value < +a.value) a.value = b.value;
    f.from = +a.value; f.to = +b.value;
    updateTimelineLabel();
    renderMarkers();
  }
  $('#tlFrom').addEventListener('input', () => onSlider('from'));
  $('#tlTo').addEventListener('input', () => onSlider('to'));
  $('#tlReset').addEventListener('click', () => {
    $('#tlFrom').value = C_MIN; $('#tlTo').value = C_MAX; onSlider('from');
  });

  /* ---------- detail drawer ---------- */
  const drawer = $('#drawer');
  function closeDrawer() {
    const prev = state.selectedId;
    state.selectedId = null;
    drawer.hidden = true;
    document.body.classList.remove('drawer-open');
    restyleSelected(prev);
  }

  function entryCard(e) {
    const hasTags = e.tags && (e.tags.site_type || e.tags.era || e.tags.century != null || (e.tags.themes || []).length);
    return h('article', { class: 'entry' },
      h('h4', { text: e.title }),
      h('p', { class: 'by' },
        e.author ? `By ${e.author}` : 'Anonymous',
        h('span', { class: 'kind', text: e.kind }),
        h('span', { class: 'lang', text: LANG_LABELS[e.language] || e.language })),
      e.body ? h('p', { class: 'text', text: e.body }) : null,
      e.image_url ? h('img', { src: e.image_url, alt: `Photo for ${e.title}`, loading: 'lazy' }) : null,
      hasTags ? h('div', { class: 'tags' }, tagChips(e.tags)) : null);
  }

  function renderDrawer(d) {
    const entries = d.entries || [];
    drawer.replaceChildren(
      h('div', { class: 'dr-head' },
        h('h2', { text: d.name }),
        h('div', { class: 'badges' },
          h('span', { class: 'badge' }, dotFor(d.site_type), ' ', typeLabel(d.site_type)),
          d.era ? h('span', { class: 'badge era', text: d.era }) : null,
          d.century != null ? h('span', { class: 'badge', text: centuryLabel(d.century) }) : null,
          d.unesco ? h('span', { class: 'badge unesco', text: 'UNESCO World Heritage' }) : null),
        h('button', { class: 'dr-close', type: 'button', 'aria-label': 'Close details', onclick: closeDrawer }, '×')),
      h('div', { class: 'dr-body' },
        d.district ? h('p', { class: 'district', text: `${d.district} district` }) : null,
        h('p', { class: 'desc', text: d.description }),
        d.folklore ? h('blockquote', { class: 'folk' }, d.folklore, h('cite', { text: 'Local tradition' })) : null,
        (d.themes || []).length ? h('div', { class: 'tags', style: 'margin-top:12px' }, (d.themes).map((t) => h('span', { class: 'tag theme', text: humanize(t) }))) : null,
        h('h3', { text: entries.length ? `Field entries (${entries.length})` : 'Field entries' }),
        entries.length ? entries.map(entryCard) : h('p', { class: 'muted', text: 'No field entries here yet. Add the first one from your visit.' }),
        h('button', { class: 'btn terracotta', type: 'button', onclick: () => openEntryDialog({ siteId: d.id }) }, 'Add a field entry here')));
  }

  /* Photo of the site, looked up by the backend (Wikipedia / Wikimedia Commons). Optional. */
  async function loadHero(id, name) {
    try {
      const im = await api(`/sites/${id}/image`);
      if (state.selectedId !== id || !im.image_url) return;
      const body = drawer.querySelector('.dr-body');
      if (!body) return;
      const fig = h('figure', { class: 'dr-hero' });
      const img = h('img', { src: im.image_url, alt: `Photo of ${name}`, loading: 'lazy' });
      img.addEventListener('error', () => fig.remove());
      fig.append(img);
      if (im.page_url && im.page_url.startsWith('https://')) {
        fig.append(h('figcaption', {}, 'Photo: ',
          h('a', { href: im.page_url, target: '_blank', rel: 'noopener noreferrer' }, im.source || 'Wikimedia'),
          ' (licence on source page)'));
      }
      body.prepend(fig);
    } catch (_) { /* no photo is fine */ }
  }

  async function openSite(id, { fly = true } = {}) {
    const prev = state.selectedId;
    state.selectedId = id;
    restyleSelected(prev);
    if (isMobile()) setSheet('peek');
    drawer.hidden = false;
    document.body.classList.add('drawer-open');
    drawer.replaceChildren(h('p', { class: 'dr-body muted', text: 'Loading…' }));
    const s = siteById(id);
    if (fly && s) focusOn(s.lat, s.lng, 12);
    try {
      const d = await api(`/sites/${id}`);
      if (state.selectedId !== id) return;
      renderDrawer(d);
      loadHero(id, d.name);
      drawer.scrollTop = 0;
      drawer.focus({ preventScroll: true });
    } catch (e) {
      if (state.selectedId === id) {
        drawer.replaceChildren(h('div', { class: 'dr-body' },
          h('p', { class: 'err', text: `Could not load this site: ${e.message}` }),
          h('button', { class: 'btn outline', type: 'button', onclick: closeDrawer }, 'Close')));
      }
    }
  }

  /* ---------- trail ---------- */
  function clearTrail() {
    trailLayer.clearLayers();
    state.trail = null;
    $('#trailOut').replaceChildren();
  }

  function geolocate() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) { reject(new Error('unsupported')); return; }
      navigator.geolocation.getCurrentPosition((p) => resolve(p.coords), reject, { timeout: 8000, maximumAge: 300000 });
    });
  }

  $('#trailForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const out = $('#trailOut'), btn = $('#trailGo');
    const stops = Math.min(15, Math.max(2, parseInt($('#trailStops').value, 10) || 6));
    $('#trailStops').value = stops;
    const body = { max_stops: stops };
    if ($('#trailTheme').value) body.theme = $('#trailTheme').value;
    btn.disabled = true;
    out.replaceChildren(h('p', { class: 'muted', text: 'Planning your route…' }));
    let usedStart = false, note = '';
    if ($('#trailLoc').checked) {
      try {
        const c = await geolocate();
        body.start_lat = c.latitude; body.start_lng = c.longitude; usedStart = true;
      } catch {
        note = 'Your location is unavailable, so the trail starts from the densest cluster of sites instead.';
      }
    }
    try {
      const r = await api('/trails', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      drawTrail(r, usedStart ? { lat: body.start_lat, lng: body.start_lng } : null, note);
    } catch (e) {
      out.replaceChildren(h('p', { class: 'err', text: e.status === 422 ? `${e.message}. Try a different theme or more stops.` : e.message }));
    } finally {
      btn.disabled = false;
    }
  });

  function drawTrail(r, start, note) {
    trailLayer.clearLayers();
    state.trail = r;
    if (r.polyline && r.polyline.length > 1) {
      L.polyline(r.polyline, { color: '#FFF8E8', weight: 8, opacity: 0.9, lineCap: 'round' }).addTo(trailLayer);
      L.polyline(r.polyline, { color: '#28306B', weight: 4, opacity: 0.95, dashArray: '2 8', lineCap: 'round' }).addTo(trailLayer);
    }
    if (start) {
      L.marker([start.lat, start.lng], {
        icon: L.divIcon({ className: '', html: '<div class="stop-pin start">S</div>', iconSize: [28, 28], iconAnchor: [14, 14] }),
        keyboard: false,
      }).bindTooltip(h('span', { text: 'Your start' })).addTo(trailLayer);
    }
    for (const s of r.stops) {
      L.marker([s.lat, s.lng], {
        icon: L.divIcon({ className: '', html: `<div class="stop-pin">${Number(s.order)}</div>`, iconSize: [28, 28], iconAnchor: [14, 14] }),
        keyboard: false,
      }).bindTooltip(h('span', { text: `${s.order}. ${s.name}` }), { direction: 'top', offset: [0, -12] })
        .on('click', () => openSite(s.id)).addTo(trailLayer);
    }
    const pts = r.polyline && r.polyline.length ? r.polyline : r.stops.map((s) => [s.lat, s.lng]);
    if (isMobile()) setSheet('half');
    fitTo(L.latLngBounds(pts));

    const withStart = (r.leg_km || []).length === r.stops.length;
    const legFor = (i) => {
      const k = withStart ? i : i - 1;
      return k >= 0 && r.leg_km[k] != null ? `${r.leg_km[k].toFixed(1)} km${i === 0 && withStart ? ' from start' : ''}` : '';
    };
    const hours = Number(r.est_hours);
    // replaceChildren turns a null argument into the text "null", so only pass real nodes.
    $('#trailOut').replaceChildren(...[
      h('p', { class: 'trail-sum', text: `${r.stops.length} stops, ${Number(r.total_km).toFixed(0)} km, about ${hours.toFixed(1)} hours` }),
      h('p', { class: 'trail-note', text: 'Distances are in a straight line. Allow extra time for roads.' }),
      note ? h('p', { class: 'trail-note', text: note }) : null,
      h('ol', { class: 'trail-list' }, r.stops.map((s, i) => h('li', null, h('button', { type: 'button', onclick: () => { focusOn(s.lat, s.lng, 12); openSite(s.id, { fly: false }); } },
        h('span', { class: 'num', text: s.order }), h('span', { text: s.name }), h('span', { class: 'leg', text: legFor(i) }))))),
      h('button', { class: 'link', type: 'button', onclick: clearTrail }, 'Clear trail'),
    ].filter(Boolean));
  }

  /* ---------- site pickers ---------- */
  function fillSiteSelect(sel, firstLabel) {
    const keep = sel.value;
    sel.replaceChildren(h('option', { value: '', text: firstLabel }),
      ...state.sites.slice().sort((a, b) => a.name.localeCompare(b.name)).map((s) => h('option', { value: s.id, text: s.name })));
    sel.value = keep;
  }

  /* ---------- add field entry ---------- */
  const entryDlg = $('#entryDlg');
  const entryForm = $('#entryForm');
  const entryTags = attachTagPreview([$('#eTitle'), $('#eBody')], $('#eTags'), 'Tags appear here as you write.');

  function setPin(latlng) {
    state.pick = latlng ? { lat: latlng.lat, lng: latlng.lng } : null;
    if (state.pinMarker) { map.removeLayer(state.pinMarker); state.pinMarker = null; }
    if (latlng) {
      state.pinMarker = L.marker(latlng, {
        draggable: true, keyboard: false,
        icon: L.divIcon({ className: '', html: '<div class="pin-drop"></div>', iconSize: [18, 18], iconAnchor: [9, 18] }),
      }).addTo(map);
      state.pinMarker.on('dragend', () => { const p = state.pinMarker.getLatLng(); state.pick = { lat: p.lat, lng: p.lng }; showLoc(); });
    }
    showLoc();
  }
  function showLoc() {
    const p = state.pick;
    $('#eLoc').textContent = p ? `${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}` : 'No location set';
    $('#eLocClear').hidden = !p;
  }

  function openEntryDialog({ siteId } = {}) {
    fillSiteSelect($('#eSite'), 'Match to the nearest site automatically');
    if (siteId) $('#eSite').value = siteId;
    $('#eErr').hidden = true;
    if (!entryDlg.open) entryDlg.showModal();
    $('#eTitle').focus();
  }
  $('#btnAddEntry').addEventListener('click', () => openEntryDialog());

  function resetEntryForm() {
    entryForm.reset();
    setPin(null);
    entryTags.reset();
    $('#eErr').hidden = true;
  }
  $('#eCancel').addEventListener('click', () => { resetEntryForm(); entryDlg.close(); });
  $('#eLocClear').addEventListener('click', () => setPin(null));

  function endPick() {
    state.picking = false;
    document.body.classList.remove('picking');
    $('#pickBanner').hidden = true;
    map.off('click', onPickClick);
  }
  function onPickClick(e) {
    endPick();
    setPin(e.latlng);
    if (isMobile()) setSheet('half');
    entryDlg.showModal();
  }
  $('#ePick').addEventListener('click', () => {
    entryDlg.close();
    state.picking = true;
    document.body.classList.add('picking');
    $('#pickBanner').hidden = false;
    if (isMobile()) setSheet('peek');
    map.once('click', onPickClick);
  });
  $('#pickCancel').addEventListener('click', () => { endPick(); entryDlg.showModal(); });

  function checkImage(file) {
    if (!file) return null;
    if (file.size > 8 * 1024 * 1024) return 'That image is larger than 8 MB. Choose a smaller photo.';
    return null;
  }

  entryForm.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const err = $('#eErr');
    const title = $('#eTitle').value.trim(), bodyText = $('#eBody').value.trim();
    const file = $('#eImage').files[0];
    const problem = !title ? 'Add a title for this entry.' : !bodyText ? 'Write a few notes so others can find this entry.' : checkImage(file);
    if (problem) { err.textContent = problem; err.hidden = false; return; }

    const fd = new FormData();
    fd.append('title', title);
    fd.append('body', bodyText);
    fd.append('kind', $('#eKind').value);
    if ($('#eAuthor').value.trim()) fd.append('author', $('#eAuthor').value.trim());
    if ($('#eSite').value) fd.append('site_id', $('#eSite').value);
    if ($('#eState').value.trim()) fd.append('state', $('#eState').value.trim());
    if (state.pick) { fd.append('lat', String(state.pick.lat)); fd.append('lng', String(state.pick.lng)); }
    if (file) fd.append('image', file);

    const save = $('#eSave');
    save.disabled = true; err.hidden = true;
    try {
      const saved = await api('/entries', { method: 'POST', body: fd });
      const pick = state.pick;
      resetEntryForm();
      entryDlg.close();
      // An entry saved to another state would be invisible here, so follow it there.
      if (state.region !== 'all' && saved.state && slugOf(saved.state) !== state.region) {
        await applyRegion(slugOf(saved.state), { fly: false });
      } else {
        await refreshData();
      }
      const site = saved.site_id && siteById(saved.site_id);
      toast(site ? (saved.auto_attached ? `Entry saved and matched to ${site.name}.` : `Entry saved to ${site.name}.`) : 'Entry saved.');
      if (site) { if (isMobile()) setSheet('peek'); focusOn(site.lat, site.lng, 12); openSite(site.id, { fly: false }); }
      else if (pick) focusOn(pick.lat, pick.lng, 12);
      else if (saved.lat != null) focusOn(saved.lat, saved.lng, 12);
    } catch (e) {
      err.textContent = `Could not save: ${e.message}`; err.hidden = false;
    } finally {
      save.disabled = false;
    }
  });

  /* ---------- digitise document ---------- */
  const ocrDlg = $('#ocrDlg');
  const ocrTags = attachTagPreview([$('#oText')], $('#oTags'), 'Tags appear after the text is read.');

  $('#btnOcr').addEventListener('click', () => {
    fillSiteSelect($('#oSite'), 'Leave unattached');
    ocrDlg.showModal();
  });

  $('#oRead').addEventListener('click', async () => {
    const err = $('#oErr'), file = $('#oFile').files[0];
    err.hidden = true;
    const problem = !file ? 'Choose a scan or photo first.' : checkImage(file);
    if (problem) { err.textContent = problem; err.hidden = false; return; }
    const fd = new FormData();
    fd.append('file', file);
    fd.append('image', file);
    fd.append('lang', $('#oLang').value);
    const btn = $('#oRead');
    btn.disabled = true; btn.textContent = 'Reading…';
    try {
      const r = await api('/ocr', { method: 'POST', body: fd });
      $('#oText').value = r.text || '';
      const chips = tagChips(r.tags || { language: r.language });
      $('#oTags').replaceChildren(chips.childNodes.length ? chips : h('span', { class: 'muted', text: 'No tags found.' }));
      $('#oResult').hidden = false;
      if (!r.text || !r.text.trim()) { err.textContent = 'No text was found on that page. Try a sharper, well-lit photo, or pick the other language.'; err.hidden = false; }
      $('#oText').focus();
    } catch (e) {
      err.textContent = e.status === 501
        ? 'Text recognition is not set up on this server. Install Tesseract with Hindi and Gujarati language data, then restart the server.'
        : `Could not read that page: ${e.message}`;
      err.hidden = false;
    } finally {
      btn.disabled = false; btn.textContent = 'Read text';
    }
  });

  $('#ocrForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const err = $('#oErr'), text = $('#oText').value.trim(), file = $('#oFile').files[0];
    if (!text) { err.textContent = 'There is no text to save yet.'; err.hidden = false; return; }
    const fd = new FormData();
    fd.append('title', $('#oTitle').value.trim() || 'Digitised document');
    fd.append('body', text);
    fd.append('kind', 'ocr');
    if ($('#oAuthor').value.trim()) fd.append('author', $('#oAuthor').value.trim());
    if ($('#oSite').value) fd.append('site_id', $('#oSite').value);
    if (file) fd.append('image', file);
    const save = $('#oSave');
    save.disabled = true; err.hidden = true;
    try {
      const saved = await api('/entries', { method: 'POST', body: fd });
      $('#ocrForm').reset();
      $('#oResult').hidden = true;
      ocrTags.reset();
      ocrDlg.close();
      await refreshData();
      const site = saved.site_id && siteById(saved.site_id);
      toast(site ? `Document saved to ${site.name}.` : 'Document saved. It is now searchable.');
      if (site) { focusOn(site.lat, site.lng, 12); openSite(site.id, { fly: false }); }
    } catch (e) {
      err.textContent = `Could not save: ${e.message}`; err.hidden = false;
    } finally {
      save.disabled = false;
    }
  });

  /* ---------- dialogs: close buttons, click on backdrop ---------- */
  document.querySelectorAll('dialog').forEach((dlg) => {
    dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
    dlg.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => dlg.close()));
  });

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (state.picking) { endPick(); entryDlg.showModal(); return; }
    if (!document.querySelector('dialog[open]') && !drawer.hidden) closeDrawer();
  });

  /* ---------- data ---------- */
  function renderStats() {
    const m = state.meta;
    $('#statSites').textContent = m ? m.sites : state.sites.length;
    $('#statEntries').textContent = m ? m.entries : 0;
    $('#statLangs').textContent = m ? m.languages.filter((l) => l.count > 0).length : 0;
  }

  /* ---------- entries that are not at a known site ---------- */
  function entryPopup(e) {
    return h('div', { class: 'entry-pop' },
      h('strong', { text: e.title }),
      h('span', { class: 'muted', text: [e.author ? `By ${e.author}` : null, e.state].filter(Boolean).join(' · ') }),
      e.body ? h('p', { text: e.body.length > 220 ? `${e.body.slice(0, 220)}…` : e.body }) : null,
      e.image_url ? h('img', { src: e.image_url, alt: `Photo for ${e.title}`, loading: 'lazy' }) : null);
  }
  function renderEntryMarkers() {
    entryLayer.clearLayers();
    for (const e of state.looseEntries) {
      const m = L.circleMarker([e.lat, e.lng], { radius: 7, color: '#B5451B', weight: 3, fillColor: '#FFF8E8', fillOpacity: 0.95 });
      m.bindTooltip(h('span', { text: e.title }), { direction: 'top', offset: [0, -6] });
      m.bindPopup(() => entryPopup(e));
      m.addTo(entryLayer);
    }
  }

  /* ---------- region ---------- */
  const slugOf = (name) => String(name).trim().toLowerCase().split(/\s+/).join('-');
  const INDIA_BOUNDS = [[6.5, 68.0], [35.7, 97.5]];
  const regionQuery = (lead) => (state.region === 'all' ? '' : `${lead}state=${encodeURIComponent(state.region)}`);
  const hashRegion = () => new URLSearchParams(location.hash.slice(1)).get('state');

  /** Pick a valid region: the wanted one if it exists, else Gujarat, else All India. */
  function resolveRegion(states, wanted) {
    const slugs = new Set(states.map((s) => s.slug));
    const w = (wanted || '').toLowerCase();
    if (w === 'all') return 'all';
    if (slugs.has(w)) return w;
    return slugs.has('gujarat') ? 'gujarat' : 'all';
  }
  function setHash() {
    try { history.replaceState(null, '', `#state=${encodeURIComponent(state.region)}`); } catch (_) { /* file:// or sandbox */ }
  }
  function regionName() {
    if (state.region === 'all') return 'India';
    const s = ((state.meta && state.meta.states) || []).find((x) => x.slug === state.region);
    return s ? s.value : humanize(state.region);
  }
  function buildRegionSelect() {
    const states = (state.meta && state.meta.states) || [];
    const total = states.reduce((n, s) => n + s.count, 0);
    const sel = $('#region');
    sel.replaceChildren(
      h('option', { value: 'all', text: `All India (${total})` }),
      ...states.map((s) => h('option', { value: s.slug, text: `${s.value} (${s.count})` })));
    sel.value = state.region;
    $('#stateList').replaceChildren(...states.map((s) => h('option', { value: s.value })));
    const name = regionName();
    $('#tagline').textContent = `Field notes from ${state.region === 'all' ? "India's" : `${name}'s`} heritage, placed on the map.`;
  }
  function flyToRegion(fly = true) {
    if (state.region === 'all') fitTo(L.latLngBounds(INDIA_BOUNDS), fly);
    else {
      const points = [...state.sites, ...state.looseEntries].map((p) => [p.lat, p.lng]);
      if (points.length) fitTo(L.latLngBounds(points), fly);
    }
  }
  async function applyRegion(slug, { fly = true } = {}) {
    state.region = slug;
    setHash();
    closeDrawer();
    map.closePopup();
    clearTrail();
    $('#clearFilters').click();   // old chip choices may not exist in the new region
    await refreshData();
    flyToRegion(fly);
  }
  $('#region').addEventListener('change', (e) => applyRegion(e.target.value).catch(() => {}));
  window.addEventListener('hashchange', () => {
    const next = resolveRegion((state.meta && state.meta.states) || [], hashRegion());
    if (next !== state.region) applyRegion(next).catch(() => {});
  });

  async function refreshData() {
    const [meta, sites, loose] = await Promise.all([
      api(`/meta?${regionQuery('').replace(/^&/, '')}`).catch(() => null),
      api(`/sites?limit=500${regionQuery('&')}`),
      api(`/entries?unattached=true${regionQuery('&')}`).catch(() => ({ items: [] })),
    ]);
    state.meta = meta;
    state.sites = sites.items || [];
    state.looseEntries = loose.items || [];
    renderStats();
    buildRegionSelect();
    buildFilters();
    // Re-apply pressed state after chips are rebuilt.
    for (const [group, id] of [['types', '#chipTypes'], ['eras', '#chipEras'], ['themes', '#chipThemes']]) {
      document.querySelectorAll(`${id} .chip`).forEach((c) => {
        const label = c.textContent;
        for (const v of state.filters[group]) {
          const text = group === 'types' ? typeLabel(v) : group === 'themes' ? humanize(v) : v;
          if (label.startsWith(text)) c.setAttribute('aria-pressed', 'true');
        }
      });
    }
    renderMarkers();
    renderEntryMarkers();
    if (state.query) runSearch();
  }

  async function init() {
    if (isMobile()) { $('#legend').removeAttribute('open'); setSheet('half'); }
    updateTimelineLabel();
    renderTimelineBars();
    try {
      const all = await api('/meta');   // unscoped, to learn which states exist
      state.meta = all;
      state.region = resolveRegion(all.states || [], hashRegion());
      setHash();
      await refreshData();
      flyToRegion(false);
    } catch (e) {
      statusEl.textContent = '';
      listTitle.textContent = 'Sites on the map';
      resultsEl.replaceChildren(h('li', { class: 'empty' },
        h('p', { text: `Could not load the archive: ${e.message}` }),
        h('button', { class: 'btn outline', type: 'button', style: 'margin-top:10px', onclick: init }, 'Try again')));
    }
  }
  init();
})();
