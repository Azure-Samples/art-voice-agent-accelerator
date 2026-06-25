/* ============================================================
   Interactive Orchestration Diagram (vanilla port of the
   frontend React component apps/artagent/frontend/src/components/
   OrchestrationDiagram.jsx). Renders the same rich, animated
   "how voice orchestration works" widget into a docs page.

   Mount point:  <div id="orchestration-interactive"></div>
   ============================================================ */
(function () {
  'use strict';

  const PALETTE = {
    cascade: { main: '#0ea5e9', soft: '#e0f2fe', deep: '#0369a1' },
    voicelive: { main: '#7c3aed', soft: '#ede9fe', deep: '#5b21b6' },
  };

  const CASCADE_STAGES = [
    {
      id: 'stt', icon: '🎧', verb: 'Listen', title: 'Speech → Text',
      detail: 'You choose the recognizer (standard Azure Speech, a Custom Speech model, phrase lists) and own the live audio stream, voice-activity detection, and barge-in.',
      owns: 'You run &amp; tune this',
    },
    {
      id: 'llm', icon: '🧠', verb: 'Think', title: 'Language Model',
      detail: 'Any Azure OpenAI chat model (gpt-4o, gpt-4.1, …). Because it is a text model you can swap it, tune prompts/tools, and even fine-tune it.',
      owns: 'You pick &amp; can fine-tune',
    },
    {
      id: 'tts', icon: '🔊', verb: 'Speak', title: 'Text → Speech',
      detail: '400+ neural voices, speaking styles, and Custom Neural Voice. You control the voice/persona per agent and how the reply is streamed back.',
      owns: 'You run &amp; tune this',
    },
  ];

  const VOICELIVE_STAGE = {
    id: 'managed', icon: '⚡️', verb: 'Listen · Think · Speak', title: 'Azure AI Voice Live',
    detail: 'One managed service listens, reasons, and talks back for you. Azure runs and scales the whole loop — you just pick the model and the voice.',
    owns: 'Azure runs it for you',
  };

  const VOICELIVE_ARCHS = [
    { id: 'native', label: 'Native speech-to-speech', blurb: 'Audio flows straight into a realtime model and back out — no separate text steps.' },
    { id: 'cascaded', label: 'Cascaded inside VoiceLive', blurb: 'Azure still runs the 3 steps for you, just behind one managed connection.' },
  ];

  const SUMMARY = {
    voicelive: {
      accent: 'voicelive', icon: '⚡️', name: 'VoiceLive', tagline: 'Easiest to run',
      points: ['Azure runs the whole pipeline', 'You just pick a model + voice', 'Least to build &amp; maintain'],
      bestFor: 'Best when you want to ship fast with minimal moving parts.',
    },
    cascade: {
      accent: 'cascade', icon: '🌐', name: 'Custom Speech', tagline: 'Most control',
      points: ['You wire up Listen → Think → Speak', 'Swap or fine-tune any single step', 'More to build, but fully yours'],
      bestFor: 'Best when you need to tune, swap, or fine-tune individual pieces.',
    },
  };

  const KEYFRAMES = `
@keyframes odx-flow { 0% { background-position: 0% 0; } 100% { background-position: -200% 0; } }
@keyframes odx-dot { 0% { left: 6%; opacity: 0; } 20% { opacity: 1; } 80% { opacity: 1; } 100% { left: 94%; opacity: 0; } }
@keyframes odx-fade { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
#orchestration-interactive { all: initial; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; display: block; }
#orchestration-interactive * { box-sizing: border-box; }
.odx-stage { transition: transform .2s cubic-bezier(.4,0,.2,1), box-shadow .2s ease, border-color .2s ease, background .2s ease; }
.odx-stage:hover { transform: translateY(-3px); box-shadow: 0 12px 24px rgba(15,23,42,.13) !important; }
.odx-card { transition: transform .2s cubic-bezier(.4,0,.2,1), box-shadow .2s ease, border-color .2s ease; }
.odx-card:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(15,23,42,.10); }
.odx-fade { animation: odx-fade .4s cubic-bezier(.4,0,.2,1); }
.odx-btn { cursor: pointer; font-family: inherit; }
`;

  const ENDPOINT = 'display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;flex:0 0 auto;min-width:58px;padding:11px 8px;border-radius:14px;background:linear-gradient(135deg,#334155 0%,#0f172a 100%);color:#e2e8f0;font-size:10px;font-weight:600;text-align:center;box-shadow:0 4px 10px rgba(15,23,42,0.18)';

  function connector(color) {
    return `<div aria-hidden="true" style="position:relative;flex:0 0 24px;min-width:24px;height:3px;align-self:center;border-radius:999px;background:linear-gradient(90deg,${color.main}22 0%,${color.main} 50%,${color.main}22 100%);background-size:200% 100%;animation:odx-flow 1.6s linear infinite">`
      + `<span style="position:absolute;top:50%;width:6px;height:6px;border-radius:50%;background:${color.main};box-shadow:0 0 8px ${color.main};transform:translateY(-50%);animation:odx-dot 1.6s linear infinite"></span></div>`;
  }

  function stageCard(stage, color, active) {
    return `<button type="button" class="odx-stage odx-btn" data-stage="${stage.id}" style="flex:1 1 0;min-width:94px;display:flex;flex-direction:column;gap:3px;padding:13px 11px;border-radius:14px;border:2px solid ${active ? color.main : '#e8edf3'};background:${active ? 'linear-gradient(160deg,#ffffff 0%,' + color.soft + ' 100%)' : '#ffffff'};box-shadow:${active ? '0 8px 18px ' + color.main + '26' : '0 1px 3px rgba(15,23,42,0.06)'};text-align:left">`
      + `<span style="display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:10px;font-size:19px;line-height:1;background:${active ? '#ffffff' : color.soft};margin-bottom:3px">${stage.icon}</span>`
      + `<span style="font-size:13px;font-weight:800;color:${color.deep}">${stage.verb}</span>`
      + `<span style="font-size:10.5px;color:#64748b">${stage.title}</span>`
      + `<span style="margin-top:5px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.4px;color:${color.main}">${stage.owns}</span>`
      + `</button>`;
  }

  let state = { mode: 'voicelive', vlArch: 'native', activeStage: null };
  let mount = null;

  function modeToggle() {
    return `<div style="display:flex;gap:6px;padding:5px;background:#f1f5f9;border-radius:14px;margin-bottom:16px;box-shadow:inset 0 1px 2px rgba(15,23,42,0.06)">`
      + [['cascade', '🌐 Custom Speech Cascade'], ['voicelive', '⚡️ VoiceLive']].map(function (o) {
        const key = o[0]; const label = o[1]; const sel = state.mode === key; const c = PALETTE[key];
        return `<button type="button" class="odx-btn" data-mode="${key}" style="flex:1;padding:9px 10px;border-radius:9px;border:${sel ? '1px solid ' + c.main : '1px solid transparent'};background:${sel ? '#fff' : 'transparent'};color:${sel ? c.deep : '#64748b'};font-size:12.5px;font-weight:${sel ? 800 : 600};box-shadow:${sel ? '0 1px 4px rgba(15,23,42,0.12)' : 'none'}">${label}</button>`;
      }).join('') + `</div>`;
  }

  function pipeline(color) {
    const stages = state.mode === 'cascade' ? CASCADE_STAGES : [VOICELIVE_STAGE];
    let inner = `<div style="${ENDPOINT}"><span style="font-size:17px">📞</span>Caller audio</div>` + connector(color);
    stages.forEach(function (stage, idx) {
      inner += stageCard(stage, color, state.activeStage === stage.id);
      if (idx < stages.length - 1 || state.mode === 'voicelive') inner += connector(color);
    });
    if (state.mode === 'cascade') inner += connector(color);
    inner += `<div style="${ENDPOINT}"><span style="font-size:17px">🔈</span>Caller audio</div>`;
    return `<div class="odx-fade" style="display:flex;align-items:stretch;gap:2px;flex-wrap:nowrap;overflow-x:auto;overflow-y:hidden;padding:12px 4px;margin:-4px -4px 0">${inner}</div>`;
  }

  function nativeDiagram(color) {
    return `<div style="margin-top:10px;padding:12px;border-radius:12px;border:1px solid #e8edf3;background:#fff">`
      + `<div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin-bottom:10px">Where the transcript comes from</div>`
      + `<div style="display:flex;align-items:center;gap:2px;flex-wrap:nowrap;overflow-x:auto;overflow-y:hidden;padding:4px 0">`
      + `<div style="${ENDPOINT}"><span style="font-size:15px">🎤</span>Audio in</div>` + connector(color)
      + `<div style="flex:1 1 0;min-width:150px;padding:12px;border-radius:14px;border:2px solid ${color.main};background:linear-gradient(160deg,#ffffff 0%,${color.soft} 100%);text-align:center;box-shadow:0 6px 16px ${color.main}22">`
      + `<div style="font-size:19px;line-height:1">🎙️</div><div style="font-size:12px;font-weight:800;color:${color.deep};margin-top:3px">Realtime model</div><div style="font-size:10px;color:#64748b">reasons directly on <strong>audio</strong></div></div>`
      + connector(color) + `<div style="${ENDPOINT}"><span style="font-size:15px">🔈</span>Audio out</div></div>`
      + `<div style="display:flex;gap:10px;margin-top:6px;align-items:stretch">`
      + `<div style="width:66px;display:flex;justify-content:center;position:relative"><div style="width:2px;background:linear-gradient(180deg,${color.main},${color.main}22);border-radius:999px"></div><span style="position:absolute;bottom:-2px;color:${color.main};font-size:13px;line-height:1">▼</span></div>`
      + `<div style="flex:1;padding:10px 12px;border-radius:12px;border:1px dashed #cbd5e1;background:linear-gradient(160deg,#ffffff 0%,#f8fafc 100%)">`
      + `<div style="font-size:11.5px;font-weight:700;color:#475569">📝 Transcript — a “best guess”</div>`
      + `<div style="font-size:10.5px;color:#64748b;margin-top:3px;line-height:1.5">Generated <em>on the side</em> for your UI &amp; logs. The model never reads this text — it already reasoned on the raw audio, so the transcript can differ from what actually drove the reply.</div></div></div></div>`;
  }

  function cascadedDiagram(color) {
    const steps = [['🎧', 'STT'], ['🧠', 'LLM'], ['🔊', 'TTS']];
    let chain = '';
    steps.forEach(function (s, i) {
      chain += `<div style="flex:1 1 0;min-width:54px;text-align:center;padding:8px 4px;border-radius:10px;background:#fff;border:1px solid ${color.main}33;box-shadow:0 1px 3px rgba(15,23,42,0.06)"><div style="font-size:16px;line-height:1">${s[0]}</div><div style="font-size:10px;font-weight:800;color:${color.deep};margin-top:2px">${s[1]}</div></div>`;
      if (i < steps.length - 1) chain += connector(color);
    });
    return `<div style="margin-top:10px;padding:12px;border-radius:12px;border:1px solid #e8edf3;background:linear-gradient(180deg,#ffffff 0%,#f7f9fc 100%)">`
      + `<div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin-bottom:10px">The cascade — but Azure runs it</div>`
      + `<div style="display:flex;align-items:center;gap:2px;flex-wrap:nowrap;overflow-x:auto;overflow-y:visible;padding:14px 0 2px">`
      + `<div style="${ENDPOINT}"><span style="font-size:15px">🎤</span>Audio in</div>` + connector(color)
      + `<div style="flex:1 1 0;min-width:230px;position:relative;padding:18px 12px 12px;border-radius:14px;border:2px dashed ${color.main};background:${color.soft}">`
      + `<span style="position:absolute;top:-9px;left:12px;padding:2px 9px;border-radius:999px;background:linear-gradient(135deg,${color.main},${color.deep});color:#fff;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;box-shadow:0 3px 8px ${color.main}44;white-space:nowrap">⚡️ Azure Voice Live · managed</span>`
      + `<div style="display:flex;align-items:center;gap:2px">${chain}</div></div>`
      + connector(color) + `<div style="${ENDPOINT}"><span style="font-size:15px">🔈</span>Audio out</div></div>`
      + `<div style="font-size:10.5px;color:#475569;margin-top:10px;line-height:1.5">Same <strong>Listen → Think → Speak</strong> as Custom Speech — Azure just hosts and runs the three steps for you behind one connection. Because there&apos;s a real STT step, the transcript is the <strong>actual recognized text</strong>, not a best guess.</div></div>`;
  }

  function vlArchSection(color) {
    const cards = VOICELIVE_ARCHS.map(function (a) {
      const sel = state.vlArch === a.id;
      return `<button type="button" class="odx-card odx-btn" data-arch="${a.id}" style="flex:1 1 180px;text-align:left;padding:11px 13px;border-radius:12px;border:1.5px solid ${sel ? color.main : '#e8edf3'};background:${sel ? 'linear-gradient(160deg,#ffffff 0%,' + color.soft + ' 100%)' : '#fff'};box-shadow:${sel ? '0 6px 14px ' + color.main + '1f' : '0 1px 2px rgba(15,23,42,0.05)'}">`
        + `<div style="font-size:12px;font-weight:800;color:#0f172a">${a.id === 'native' ? '🎙️ ' : '🔤 '}${a.label}</div>`
        + `<div style="font-size:10.5px;color:#64748b;margin-top:3px;line-height:1.45">${a.blurb}</div></button>`;
    }).join('');
    let extra = '';
    if (state.vlArch === 'native') {
      extra = nativeDiagram(color)
        + `<div style="margin-top:10px;padding:10px 12px;border-radius:10px;background:linear-gradient(135deg,#fffbeb,#fef3c7);border:1px solid #fcd34d;font-size:11px;line-height:1.5;color:#78350f"><strong>⚠️ Realtime models:</strong> can&apos;t be fine-tuned and bill premium audio tokens. Going to prod? Benchmark them against higher-throughput text LLMs (Cascade) with a robust eval suite in <a href="https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-approach-gen-ai" target="_blank" rel="noopener noreferrer" style="color:#b45309;font-weight:700">Azure AI Foundry</a> first.</div>`;
    } else {
      extra = cascadedDiagram(color);
    }
    return `<div style="margin-top:14px"><div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#94a3b8;margin-bottom:6px">Inside VoiceLive</div>`
      + `<div style="display:flex;gap:8px;flex-wrap:wrap">${cards}</div>${extra}</div>`;
  }

  function stageDetail(color) {
    let d = null;
    if (state.mode === 'cascade') d = CASCADE_STAGES.find(function (s) { return s.id === state.activeStage; });
    else if (state.activeStage === 'managed') d = VOICELIVE_STAGE;
    if (!d) return '';
    return `<div style="margin-top:14px;padding:12px 14px;border-radius:12px;font-size:12px;line-height:1.55;background:${color.soft};border:1px solid ${color.main}44;color:${color.deep}"><strong>${d.icon} ${d.title}</strong> — ${d.detail}</div>`;
  }

  function spectrum() {
    const v = PALETTE.voicelive, c = PALETTE.cascade;
    const marker = function (left, glyph, title) {
      return `<span title="${title}" style="position:absolute;left:${left};top:50%;transform:translate(-50%,-50%);width:26px;height:26px;border-radius:50%;background:#fff;box-shadow:0 2px 6px rgba(15,23,42,0.2);display:inline-flex;align-items:center;justify-content:center;font-size:14px">${glyph}</span>`;
    };
    return `<div style="border:1px solid #e8edf3;border-radius:16px;padding:16px 18px;margin-bottom:14px;background:linear-gradient(180deg,#ffffff 0%,#f7f9fc 100%);box-shadow:0 1px 2px rgba(15,23,42,0.04)">`
      + `<div style="display:flex;justify-content:space-between;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px"><span style="color:${v.deep}">← Simpler to run</span><span style="color:${c.deep}">More control →</span></div>`
      + `<div style="position:relative;height:10px;border-radius:999px;background:linear-gradient(90deg,${v.main},#a78bfa 45%,#6ea8e0 55%,${c.main});box-shadow:0 2px 8px rgba(99,102,241,0.25)">${marker('8%', '⚡️', 'VoiceLive')}${marker('92%', '🌐', 'Custom Speech')}</div>`
      + `<div style="display:flex;justify-content:space-between;margin-top:8px"><span style="font-size:11px;font-weight:700;color:${v.deep}">VoiceLive</span><span style="font-size:11px;font-weight:700;color:${c.deep}">Custom Speech</span></div></div>`;
  }

  function summaryCards() {
    const cards = [SUMMARY.voicelive, SUMMARY.cascade].map(function (card) {
      const c = PALETTE[card.accent]; const isActive = state.mode === card.accent;
      const points = card.points.map(function (p) {
        return `<li style="display:flex;gap:6px;font-size:11.5px;color:#334155;line-height:1.5;margin-bottom:3px"><span style="color:${c.main};font-weight:800">•</span>${p}</li>`;
      }).join('');
      return `<div class="odx-card" style="flex:1 1 220px;border-radius:16px;padding:15px;border:2px solid ${isActive ? c.main : '#e8edf3'};background:${isActive ? 'linear-gradient(160deg,#ffffff 0%,' + c.soft + ' 100%)' : '#fff'};box-shadow:${isActive ? '0 8px 18px ' + c.main + '1f' : '0 1px 3px rgba(15,23,42,0.05)'}">`
        + `<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px"><span style="display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:11px;background:${c.soft};font-size:19px">${card.icon}</span><div><div style="font-size:13px;font-weight:800;color:#0f172a">${card.name}</div><div style="font-size:10px;font-weight:700;color:${c.deep};text-transform:uppercase;letter-spacing:0.4px">${card.tagline}</div></div></div>`
        + `<ul style="margin:0 0 8px;padding-left:0;list-style:none">${points}</ul>`
        + `<div style="font-size:10.5px;color:#64748b;font-style:italic;line-height:1.45">${card.bestFor}</div></div>`;
    }).join('');
    return `<div style="display:flex;gap:12px;flex-wrap:wrap">${cards}</div>`;
  }

  function template() {
    const color = PALETTE[state.mode];
    return `<div style="border:1px solid #e8edf3;border-radius:18px;padding:20px;background:#fff;color:#0f172a;box-shadow:0 4px 16px rgba(15,23,42,0.06)">`
      + `<div style="margin-bottom:16px"><p style="font-size:18px;font-weight:800;margin:0;color:#0f172a;letter-spacing:-0.01em">How voice orchestration works</p>`
      + `<p style="font-size:12px;color:#64748b;margin:5px 0 0;line-height:1.55">Every call needs to <strong>listen</strong>, <strong>think</strong>, then <strong>speak</strong>. The only question is how much of that you run yourself — it&apos;s a trade between <strong>simplicity</strong> and <strong>control</strong>.</p></div>`
      + modeToggle()
      + `<div style="border:1px solid #e8edf3;border-radius:18px;padding:18px;background:linear-gradient(180deg,#ffffff 0%,#f7f9fc 100%);margin-bottom:16px;box-shadow:0 1px 2px rgba(15,23,42,0.04)">`
      + `<span style="display:inline-flex;align-items:center;gap:6px;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.6px;padding:4px 11px;border-radius:999px;margin-bottom:14px;background:${color.soft};color:${color.deep};border:1px solid ${color.main}55">${state.mode === 'cascade' ? '🛠️ You orchestrate each component' : '☁️ Azure manages the pipeline'}</span>`
      + pipeline(color)
      + (state.mode === 'voicelive' ? vlArchSection(color) : '')
      + stageDetail(color)
      + `</div>`
      + spectrum()
      + summaryCards()
      + `<p style="font-size:10.5px;color:#94a3b8;margin:12px 2px 0;line-height:1.5">Either way you run the <strong>same</strong> agents and tools — you can switch modes any time without rebuilding your agent.</p>`
      + `</div>`;
  }

  function render() { if (mount) mount.innerHTML = template(); }

  function onClick(e) {
    const modeBtn = e.target.closest('[data-mode]');
    if (modeBtn) { state.mode = modeBtn.getAttribute('data-mode'); state.activeStage = null; render(); return; }
    const archBtn = e.target.closest('[data-arch]');
    if (archBtn) { state.vlArch = archBtn.getAttribute('data-arch'); render(); return; }
    const stageBtn = e.target.closest('[data-stage]');
    if (stageBtn) { state.activeStage = stageBtn.getAttribute('data-stage'); render(); return; }
  }

  function onHover(e) {
    const stageBtn = e.target.closest('[data-stage]');
    if (stageBtn) {
      const id = stageBtn.getAttribute('data-stage');
      if (state.activeStage !== id) { state.activeStage = id; render(); }
    }
  }

  function init() {
    mount = document.getElementById('orchestration-interactive');
    if (!mount) return;
    const style = document.createElement('style');
    style.textContent = KEYFRAMES;
    document.head.appendChild(style);
    // Event delegation survives re-renders (listeners on the persistent mount).
    mount.addEventListener('click', onClick);
    mount.addEventListener('mouseover', onHover);
    render();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
