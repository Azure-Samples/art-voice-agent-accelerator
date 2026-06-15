// ============================================================
// ART Agent Docs v2 — Main JS (no build step required)
// ============================================================

// --- Legacy-docs URL override ---
// The "Legacy" header pill and sidebar link default to `legacy-site/index.html`,
// which is the mkdocs build output (sources live at `docs/legacy/`, built into
// `docs/legacy-site/`). Run `make docs-legacy-build` once to populate it.
//
// In production, set LEGACY_DOCS_URL to an absolute URL (e.g. the GH Pages
// site at https://azure-samples.github.io/art-voice-agent-accelerator/, or a
// dedicated `/legacy/` subpath) to repoint all legacy links from one place.
// Leave as null to keep the relative `legacy-site/index.html` default.
const LEGACY_DOCS_URL = null;

document.addEventListener('DOMContentLoaded', () => {

  // --- Apply legacy-docs URL override (if configured) ---
  if (LEGACY_DOCS_URL) {
    document.querySelectorAll('#legacy-docs-link, #legacy-docs-sidebar-link')
      .forEach(el => { el.href = LEGACY_DOCS_URL; });
  }

  // --- Theme toggle ---
  const toggle = document.querySelector('.theme-toggle');
  const saved = localStorage.getItem('art-docs-theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
  else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
  if (toggle) {
    const update = () => {
      const dark = document.documentElement.getAttribute('data-theme') === 'dark';
      toggle.textContent = dark ? '☀️' : '🌙';
    };
    update();
    toggle.addEventListener('click', () => {
      const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('art-docs-theme', next);
      update();
      document.dispatchEvent(new CustomEvent('art-theme-changed', { detail: { theme: next } }));
    });
  }

  // --- Active sidebar link tracking ---
  const sidebarLinks = document.querySelectorAll('.sidebar-section a[href^="#"]');
  if (sidebarLinks.length) {
    const sections = [];
    sidebarLinks.forEach(link => {
      const id = link.getAttribute('href').slice(1);
      const el = document.getElementById(id);
      if (el) sections.push({ link, el });
    });

    const setActive = () => {
      let current = sections[0];
      for (const s of sections) {
        if (s.el.getBoundingClientRect().top <= 100) current = s;
      }
      sidebarLinks.forEach(l => l.classList.remove('active'));
      if (current) current.link.classList.add('active');
    };
    window.addEventListener('scroll', setActive, { passive: true });
    setActive();
  }

  // --- Tab groups ---
  document.querySelectorAll('.tab-group').forEach(group => {
    const btns = group.querySelectorAll('.tab-btn');
    const panels = group.querySelectorAll('.tab-panel');
    btns.forEach(btn => {
      btn.addEventListener('click', () => {
        btns.forEach(b => b.classList.remove('active'));
        panels.forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        const target = group.querySelector(`#${btn.dataset.tab}`);
        if (target) target.classList.add('active');
      });
    });
  });

  // --- Mobile sidebar ---
  const sidebarToggle = document.querySelector('.sidebar-toggle');
  const sidebar = document.querySelector('.sidebar');
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
    document.addEventListener('click', (e) => {
      if (!sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });
  }

  // --- Copy code buttons ---
  document.querySelectorAll('pre').forEach(pre => {
    if (pre.closest('.code-block')) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'code-block';

    const toolbar = document.createElement('div');
    toolbar.className = 'code-block-toolbar';

    const label = document.createElement('span');
    label.className = 'code-block-label';
    label.textContent = 'Code';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'code-block-copy';

    const resetLabel = () => {
      btn.textContent = 'Copy';
      btn.setAttribute('aria-label', 'Copy code to clipboard');
    };

    resetLabel();
    btn.addEventListener('click', async () => {
      const text = pre.textContent.trimEnd();
      await navigator.clipboard.writeText(text);
      btn.textContent = 'Copied';
      btn.setAttribute('aria-label', 'Copied to clipboard');
      window.setTimeout(resetLabel, 1500);
    });

    toolbar.append(label, btn);
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.append(toolbar, pre);

    pre.addEventListener('mouseenter', () => btn.classList.add('is-visible'));
    pre.addEventListener('mouseleave', () => btn.classList.remove('is-visible'));
  });

  // --- Header active page ---
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.header-nav a').forEach(a => {
    const href = a.getAttribute('href');
    if (href === path || (path === 'index.html' && href === 'index.html')) {
      a.classList.add('active');
    }
  });

  // --- Expandable architecture diagrams (modal with drag & zoom) ---
  const modal = document.createElement('div');
  modal.className = 'diagram-modal';
  modal.innerHTML = `
    <div class="diagram-modal-backdrop"></div>
    <div class="diagram-modal-container">
      <div class="diagram-modal-header">
        <span class="diagram-modal-title"></span>
        <div class="diagram-modal-controls">
          <button class="diagram-zoom-btn" data-action="reset" title="Reset zoom (R)">Reset</button>
          <button class="diagram-zoom-btn" data-action="zoomout" title="Zoom out (−)">−</button>
          <span class="diagram-zoom-level">100%</span>
          <button class="diagram-zoom-btn" data-action="zoomin" title="Zoom in (+)">+</button>
        </div>
        <button class="diagram-modal-close" aria-label="Close" title="Close (Esc)">✕</button>
      </div>
      <div class="diagram-modal-canvas">
        <div class="diagram-modal-content"></div>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  let isDragging = false;
  let dragStart = { x: 0, y: 0 };
  let offset = { x: 0, y: 0 };
  let zoom = 1;
  const minZoom = 0.5;
  const maxZoom = 4;
  const zoomStep = 0.2;

  const canvas = modal.querySelector('.diagram-modal-canvas');
  const content = modal.querySelector('.diagram-modal-content');
  const title = modal.querySelector('.diagram-modal-title');
  const zoomLevel = modal.querySelector('.diagram-zoom-level');
  const backdrop = modal.querySelector('.diagram-modal-backdrop');
  const closeBtn = modal.querySelector('.diagram-modal-close');

  const updateTransform = () => {
    content.style.transform = `translate(${offset.x}px, ${offset.y}px) scale(${zoom})`;
    content.style.cursor = zoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default';
    zoomLevel.textContent = Math.round(zoom * 100) + '%';
  };

  const resetZoom = () => {
    zoom = 1;
    offset = { x: 0, y: 0 };
    updateTransform();
  };

  const closeModal = () => {
    modal.classList.remove('open');
    content.innerHTML = '';
    resetZoom();
  };

  const openDiagram = (fig) => {
    const svg = fig.querySelector('svg');
    const pic = fig.querySelector('img');
    const caption = fig.querySelector('figcaption, .az-diagram-caption');
    content.innerHTML = '';
    if (svg) {
      // Wrap in an .az-diagram host so the scoped tile/text fills resolve
      const host = document.createElement('div');
      host.className = 'az-diagram modal-diagram-host';
      const clone = svg.cloneNode(true);
      clone.removeAttribute('width');
      clone.removeAttribute('height');
      clone.style.width = '100%';
      clone.style.height = '100%';
      host.appendChild(clone);
      content.appendChild(host);
    } else if (pic) {
      const im = document.createElement('img');
      im.src = pic.src;
      im.alt = pic.alt;
      content.appendChild(im);
    } else {
      return;
    }
    title.textContent = caption ? caption.textContent.trim().split('.')[0] : '';
    resetZoom();
    modal.classList.add('open');
  };

  // Zoom controls
  modal.querySelectorAll('.diagram-zoom-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const action = btn.dataset.action;
      if (action === 'reset') {
        resetZoom();
      } else if (action === 'zoomin') {
        zoom = Math.min(zoom + zoomStep, maxZoom);
        updateTransform();
      } else if (action === 'zoomout') {
        zoom = Math.max(zoom - zoomStep, minZoom);
        updateTransform();
      }
    });
  });

  // Mouse wheel zoom
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -zoomStep : zoomStep;
    zoom = Math.max(minZoom, Math.min(zoom + delta, maxZoom));
    updateTransform();
  }, { passive: false });

  // Drag to pan
  content.addEventListener('mousedown', (e) => {
    isDragging = true;
    dragStart = { x: e.clientX - offset.x, y: e.clientY - offset.y };
    updateTransform();
    e.preventDefault();
  });

  document.addEventListener('mousemove', (e) => {
    if (isDragging && modal.classList.contains('open')) {
      offset.x = e.clientX - dragStart.x;
      offset.y = e.clientY - dragStart.y;
      updateTransform();
    }
  });

  document.addEventListener('mouseup', () => {
    if (isDragging) {
      isDragging = false;
      updateTransform();
    }
  });

  // Touch zoom (pinch)
  let touchDistance = 0;
  canvas.addEventListener('touchstart', (e) => {
    if (e.touches.length === 2) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      touchDistance = Math.sqrt(dx * dx + dy * dy);
    }
  });

  canvas.addEventListener('touchmove', (e) => {
    if (e.touches.length === 2) {
      e.preventDefault();
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const newDistance = Math.sqrt(dx * dx + dy * dy);
      const delta = (newDistance - touchDistance) * 0.01;
      zoom = Math.max(minZoom, Math.min(zoom + delta, maxZoom));
      touchDistance = newDistance;
      updateTransform();
    }
  }, { passive: false });

  // Close handlers
  closeBtn.addEventListener('click', closeModal);
  backdrop.addEventListener('click', closeModal);
  document.addEventListener('keydown', (e) => {
    if (!modal.classList.contains('open')) return;
    if (e.key === 'Escape') closeModal();
    else if (e.key === 'r' || e.key === 'R') resetZoom();
    else if (e.key === '+' || e.key === '=') { zoom = Math.min(zoom + zoomStep, maxZoom); updateTransform(); }
    else if (e.key === '-') { zoom = Math.max(zoom - zoomStep, minZoom); updateTransform(); }
  });

  // Open diagram on click — event delegation so it survives diagram re-renders
  document.addEventListener('click', (e) => {
    if (modal.contains(e.target)) return;
    const fig = e.target.closest('.arch-diagram[data-expandable], .az-diagram[data-diagram]');
    if (fig) openDiagram(fig);
  });

  // --- Render mermaid diagrams ---
  if (typeof mermaid !== 'undefined') {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    mermaid.initialize({
      startOnLoad: true,
      theme: dark ? 'dark' : 'default',
      securityLevel: 'loose',
      flowchart: { useMaxWidth: true, htmlLabels: true },
    });
  }

});
