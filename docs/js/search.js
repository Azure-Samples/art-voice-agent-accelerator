// ============================================================
// ART Agent Docs v2 — Client-side search
// Loads docs-v2/search-index.json on demand, ranks sections by
// token overlap + title boost, renders highlighted snippets.
//
// Wire up:  <button class="search-trigger">…</button> in the header
//           <script src="js/search.js"></script>  at end of <body>
//
// Keyboard: ⌘K / Ctrl+K opens, Esc closes,
//           ↑↓ navigates, Enter follows, / opens (when not typing)
// ============================================================

(() => {
  const INDEX_URL = 'search-index.json';
  const MAX_RESULTS = 10;
  const SNIPPET_PAD = 80;
  const STOP_WORDS = new Set([
    'a','an','the','and','or','of','to','in','on','for','is','are','be',
    'as','at','by','with','from','it','this','that','these','those'
  ]);

  let indexPromise = null;
  let modalEl = null;
  let inputEl = null;
  let resultsEl = null;
  let statusEl = null;
  let activeIndex = -1;
  let currentResults = [];

  // ---- Index loading ------------------------------------------------------

  function loadIndex() {
    if (!indexPromise) {
      indexPromise = fetch(INDEX_URL, { cache: 'force-cache' })
        .then(r => {
          if (!r.ok) throw new Error(`Failed to load ${INDEX_URL}: ${r.status}`);
          return r.json();
        })
        .then(data => {
          // Pre-lowercase searchable fields once
          for (const s of data.sections) {
            s._titleLc = (s.title || '').toLowerCase();
            s._pageLc  = (s.page  || '').toLowerCase();
            s._textLc  = (s.text  || '').toLowerCase();
          }
          return data;
        })
        .catch(err => {
          indexPromise = null;
          throw err;
        });
    }
    return indexPromise;
  }

  // ---- Tokenize + score ---------------------------------------------------

  function tokenize(q) {
    return (q || '')
      .toLowerCase()
      .split(/[^a-z0-9_]+/)
      .filter(t => t.length >= 2 && !STOP_WORDS.has(t));
  }

  function scoreSection(s, tokens, rawPhrase) {
    let score = 0;
    let matchedTokens = 0;

    for (const t of tokens) {
      let hit = false;

      // Title — strongest signal
      if (s._titleLc.includes(t)) {
        score += 20;
        if (s._titleLc.startsWith(t)) score += 10;
        hit = true;
      }
      // Page name
      if (s._pageLc.includes(t)) {
        score += 5;
        hit = true;
      }
      // Body — count occurrences, capped to avoid runaway from common words
      if (s._textLc) {
        let from = 0, count = 0;
        while (count < 20) {
          const idx = s._textLc.indexOf(t, from);
          if (idx < 0) break;
          count++;
          from = idx + t.length;
        }
        if (count) {
          score += count;
          hit = true;
        }
      }
      if (hit) matchedTokens++;
    }

    // Require every multi-token query to land on at least one signal
    if (tokens.length > 1 && matchedTokens < Math.min(2, tokens.length)) {
      return 0;
    }
    if (matchedTokens === 0) return 0;

    // Phrase boost (only for multi-word queries)
    if (rawPhrase && rawPhrase.length >= 4 && rawPhrase.includes(' ')) {
      if (s._titleLc.includes(rawPhrase)) score += 100;
      if (s._textLc.includes(rawPhrase))  score += 30;
    }

    // Heading-level boost: h1 > h2 > h3
    score += (4 - (s.level || 2)) * 2;

    return score;
  }

  function search(query, sections) {
    const tokens = tokenize(query);
    if (!tokens.length) return [];
    const phrase = query.trim().toLowerCase();

    const scored = [];
    for (const s of sections) {
      const score = scoreSection(s, tokens, phrase);
      if (score > 0) scored.push({ s, score });
    }
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, MAX_RESULTS).map(x => x.s);
  }

  // ---- Snippet + highlight ------------------------------------------------

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function highlight(text, tokens) {
    if (!text) return '';
    const safe = escapeHtml(text);
    if (!tokens.length) return safe;
    const pattern = new RegExp(
      '(' + tokens.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')',
      'gi'
    );
    return safe.replace(pattern, '<mark>$1</mark>');
  }

  function buildSnippet(text, tokens) {
    if (!text) return '';
    const lc = text.toLowerCase();
    let firstHit = -1;
    for (const t of tokens) {
      const i = lc.indexOf(t);
      if (i >= 0 && (firstHit < 0 || i < firstHit)) firstHit = i;
    }
    if (firstHit < 0) {
      return highlight(text.slice(0, SNIPPET_PAD * 2), tokens);
    }
    const start = Math.max(0, firstHit - SNIPPET_PAD);
    const end   = Math.min(text.length, firstHit + SNIPPET_PAD * 2);
    let snippet = text.slice(start, end);
    if (start > 0) snippet = '…' + snippet;
    if (end < text.length) snippet = snippet + '…';
    return highlight(snippet, tokens);
  }

  // ---- Rendering ----------------------------------------------------------

  function renderResults(query, sections) {
    activeIndex = -1;
    if (!query || !query.trim()) {
      currentResults = [];
      resultsEl.innerHTML = '';
      statusEl.textContent = 'Type to search — try "deploy", "tools", "VoiceLive", "create agent".';
      return;
    }

    const tokens = tokenize(query);
    const results = search(query, sections);
    currentResults = results;

    if (!results.length) {
      resultsEl.innerHTML = '';
      statusEl.textContent = `No matches for "${query}".`;
      return;
    }

    statusEl.textContent = `${results.length} match${results.length === 1 ? '' : 'es'}`;
    resultsEl.innerHTML = results.map((s, i) => {
      const crumbs = s.level > 1 ? `${escapeHtml(s.page)} <span class="search-arrow">›</span> ` : '';
      const titleHtml = highlight(s.title, tokens);
      const snippet = buildSnippet(s.text, tokens);
      return `
        <a class="search-result" href="${escapeHtml(s.url)}" data-idx="${i}">
          <div class="search-result-crumbs">${crumbs}<span class="search-result-title">${titleHtml}</span></div>
          <div class="search-result-snippet">${snippet}</div>
        </a>
      `;
    }).join('');
  }

  function setActive(idx) {
    const items = resultsEl.querySelectorAll('.search-result');
    if (!items.length) return;
    if (idx < 0) idx = items.length - 1;
    if (idx >= items.length) idx = 0;
    activeIndex = idx;
    items.forEach((el, i) => el.classList.toggle('active', i === idx));
    const el = items[idx];
    if (el) el.scrollIntoView({ block: 'nearest' });
  }

  // ---- Modal lifecycle ----------------------------------------------------

  function ensureModal() {
    if (modalEl) return modalEl;
    modalEl = document.createElement('div');
    modalEl.className = 'search-modal';
    modalEl.innerHTML = `
      <div class="search-modal-backdrop"></div>
      <div class="search-modal-panel" role="dialog" aria-modal="true" aria-label="Search docs">
        <div class="search-modal-input-row">
          <span class="search-modal-icon" aria-hidden="true">⌕</span>
          <input class="search-modal-input" type="search" autocomplete="off" spellcheck="false"
                 placeholder="Search the docs…" aria-label="Search docs">
          <kbd class="search-modal-esc">Esc</kbd>
        </div>
        <div class="search-modal-status"></div>
        <div class="search-modal-results" role="listbox"></div>
        <div class="search-modal-footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>Esc</kbd> close</span>
          <span class="search-modal-credit">Indexed from local docs-v2 pages</span>
        </div>
      </div>
    `;
    document.body.appendChild(modalEl);

    inputEl   = modalEl.querySelector('.search-modal-input');
    resultsEl = modalEl.querySelector('.search-modal-results');
    statusEl  = modalEl.querySelector('.search-modal-status');

    modalEl.querySelector('.search-modal-backdrop')
      .addEventListener('click', closeModal);

    inputEl.addEventListener('input', () => {
      loadIndex()
        .then(data => renderResults(inputEl.value, data.sections))
        .catch(err => { statusEl.textContent = `Search index failed: ${err.message}`; });
    });

    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); setActive(activeIndex + 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(activeIndex - 1); }
      else if (e.key === 'Enter') {
        const items = resultsEl.querySelectorAll('.search-result');
        const target = items[activeIndex >= 0 ? activeIndex : 0];
        if (target) {
          e.preventDefault();
          window.location.href = target.getAttribute('href');
          closeModal();
        }
      }
    });

    resultsEl.addEventListener('mousemove', (e) => {
      const el = e.target.closest('.search-result');
      if (!el) return;
      const idx = parseInt(el.dataset.idx, 10);
      if (!Number.isNaN(idx) && idx !== activeIndex) setActive(idx);
    });

    return modalEl;
  }

  function openModal() {
    ensureModal();
    modalEl.classList.add('open');
    document.documentElement.classList.add('search-open');
    inputEl.value = '';
    renderResults('', []);
    // Prime the index in the background so first keystroke is instant
    loadIndex().catch(err => {
      statusEl.textContent = `Search index failed: ${err.message}`;
    });
    setTimeout(() => inputEl.focus(), 10);
  }

  function closeModal() {
    if (!modalEl) return;
    modalEl.classList.remove('open');
    document.documentElement.classList.remove('search-open');
  }

  // ---- Global key bindings ------------------------------------------------

  document.addEventListener('keydown', (e) => {
    const isTyping = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)
      || document.activeElement?.isContentEditable;

    // ⌘K / Ctrl+K — open
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (modalEl?.classList.contains('open')) closeModal();
      else openModal();
      return;
    }
    // "/" — open when not typing in a field
    if (e.key === '/' && !isTyping && !modalEl?.classList.contains('open')) {
      e.preventDefault();
      openModal();
      return;
    }
    // Esc — close
    if (e.key === 'Escape' && modalEl?.classList.contains('open')) {
      closeModal();
    }
  });

  // ---- Wire up search trigger button(s) ----------------------------------

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.search-trigger').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        openModal();
      });
    });
    // Inject ⌘K / Ctrl+K hint dynamically based on platform
    const isMac = /Mac|iPhone|iPad/i.test(navigator.platform);
    document.querySelectorAll('.search-trigger .search-trigger-kbd').forEach(el => {
      el.textContent = isMac ? '⌘K' : 'Ctrl K';
    });
  });

  // Expose for debugging
  window.__artDocsSearch = { openModal, closeModal, loadIndex };
})();
