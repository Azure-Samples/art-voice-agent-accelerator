import React, { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';

/**
 * OrchestrationDiagram — an interactive visual that explains the two voice
 * orchestration modes the accelerator ships with:
 *
 *   • Custom Speech Cascade — you wire up Azure Speech STT → Azure OpenAI LLM
 *     → Azure Speech TTS as three separate components you own and tune.
 *   • VoiceLive — Azure AI Voice Live hosts the whole speech-in → reason →
 *     speech-out loop as one managed realtime service (native speech-to-speech
 *     or cascaded-inside-VoiceLive).
 *
 * Mirrors the architecture docs under
 * docs/legacy/architecture/orchestration/ but rendered as an interactive,
 * framework-light component (plain React + inline styles) so it can be embedded
 * inside both the inline-styled Quick Tune popover and the MUI Agent Builder.
 *
 * Exports:
 *   • OrchestrationDiagram       — the bare visual (embed anywhere).
 *   • OrchestrationDiagramModal  — portal overlay with backdrop + close button.
 */

// Normalize the various mode tokens used across the app to 'cascade'|'voicelive'.
const normalizeMode = (m) => {
  const v = (m || '').toLowerCase();
  if (v === 'voice_live' || v === 'voicelive' || v === 'realtime') return 'voicelive';
  return 'cascade';
};

const PALETTE = {
  cascade: { main: '#0ea5e9', soft: '#e0f2fe', deep: '#0369a1' },
  voicelive: { main: '#7c3aed', soft: '#ede9fe', deep: '#5b21b6' },
};

// Pipeline stages for Custom Speech Cascade — three components YOU own.
const CASCADE_STAGES = [
  {
    id: 'stt',
    icon: '🎧',
    verb: 'Listen',
    title: 'Speech → Text',
    detail:
      'You choose the recognizer (standard Azure Speech, a Custom Speech model, phrase lists) and own the live audio stream, voice-activity detection, and barge-in.',
    owns: 'You run & tune this',
  },
  {
    id: 'llm',
    icon: '🧠',
    verb: 'Think',
    title: 'Language Model',
    detail:
      'Any Azure OpenAI chat model (gpt-4o, gpt-4.1, …). Because it is a text model you can swap it, tune prompts/tools, and even fine-tune it.',
    owns: 'You pick & can fine-tune',
  },
  {
    id: 'tts',
    icon: '🔊',
    verb: 'Speak',
    title: 'Text → Speech',
    detail:
      '400+ neural voices, speaking styles, and Custom Neural Voice. You control the voice/persona per agent and how the reply is streamed back.',
    owns: 'You run & tune this',
  },
];

// VoiceLive — one managed service that does all three.
const VOICELIVE_STAGE = {
  id: 'managed',
  icon: '⚡️',
  verb: 'Listen · Think · Speak',
  title: 'Azure AI Voice Live',
  detail:
    'One managed service listens, reasons, and talks back for you. Azure runs and scales the whole loop — you just pick the model and the voice.',
  owns: 'Azure runs it for you',
};

const VOICELIVE_ARCHS = [
  {
    id: 'native',
    label: 'Native speech-to-speech',
    blurb: 'Audio flows straight into a realtime model and back out — no separate text steps.',
    warn: true,
  },
  {
    id: 'cascaded',
    label: 'Cascaded inside VoiceLive',
    blurb: 'Azure still runs the 3 steps for you, just behind one managed connection.',
    warn: false,
  },
];

// Plain-language summary cards — the heart of the "complexity vs control" story.
const SUMMARY = {
  voicelive: {
    accent: 'voicelive',
    icon: '⚡️',
    name: 'VoiceLive',
    tagline: 'Easiest to run',
    points: [
      'Azure runs the whole pipeline',
      'You just pick a model + voice',
      'Least to build & maintain',
    ],
    bestFor: 'Best when you want to ship fast with minimal moving parts.',
  },
  cascade: {
    accent: 'cascade',
    icon: '🌐',
    name: 'Custom Speech',
    tagline: 'Most control',
    points: [
      'You wire up Listen → Think → Speak',
      'Swap or fine-tune any single step',
      'More to build, but fully yours',
    ],
    bestFor: 'Best when you need to tune, swap, or fine-tune individual pieces.',
  },
};

const styles = {
  root: {
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    color: '#0f172a',
    boxSizing: 'border-box',
  },
  header: { marginBottom: '16px', paddingRight: '40px' },
  title: { fontSize: '18px', fontWeight: 800, margin: 0, color: '#0f172a', letterSpacing: '-0.01em' },
  subtitle: { fontSize: '12px', color: '#64748b', margin: '5px 0 0', lineHeight: 1.55 },
  toggleRow: {
    display: 'flex',
    gap: '6px',
    padding: '5px',
    background: '#f1f5f9',
    borderRadius: '14px',
    marginBottom: '16px',
    boxShadow: 'inset 0 1px 2px rgba(15,23,42,0.06)',
  },
  flowWrap: {
    border: '1px solid #e8edf3',
    borderRadius: '18px',
    padding: '18px',
    background: 'linear-gradient(180deg, #ffffff 0%, #f7f9fc 100%)',
    marginBottom: '16px',
    boxShadow: '0 1px 2px rgba(15,23,42,0.04)',
  },
  ownerBand: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '10px',
    fontWeight: 800,
    textTransform: 'uppercase',
    letterSpacing: '0.6px',
    padding: '4px 11px',
    borderRadius: '999px',
    marginBottom: '14px',
  },
  pipeline: {
    display: 'flex',
    alignItems: 'stretch',
    gap: '2px',
    flexWrap: 'nowrap',
    overflowX: 'auto',
    overflowY: 'hidden',
    padding: '12px 4px',
    margin: '-4px -4px 0',
  },
  endpoint: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '3px',
    flex: '0 0 auto',
    minWidth: '58px',
    padding: '11px 8px',
    borderRadius: '14px',
    background: 'linear-gradient(135deg, #334155 0%, #0f172a 100%)',
    color: '#e2e8f0',
    fontSize: '10px',
    fontWeight: 600,
    textAlign: 'center',
    boxShadow: '0 4px 10px rgba(15,23,42,0.18)',
  },
  detailPanel: {
    marginTop: '14px',
    padding: '12px 14px',
    borderRadius: '12px',
    fontSize: '12px',
    lineHeight: 1.55,
  },
};

// Injected once — keyframes + hover effects that inline styles can't express.
const KEYFRAMES = `
@keyframes od-flow { 0% { background-position: 0% 0; } 100% { background-position: -200% 0; } }
@keyframes od-dot { 0% { left: 6%; opacity: 0; } 20% { opacity: 1; } 80% { opacity: 1; } 100% { left: 94%; opacity: 0; } }
@keyframes od-fade { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.od-stage { transition: transform .2s cubic-bezier(.4,0,.2,1), box-shadow .2s ease, border-color .2s ease, background .2s ease; }
.od-stage:hover { transform: translateY(-3px); box-shadow: 0 12px 24px rgba(15,23,42,.13) !important; }
.od-card { transition: transform .2s cubic-bezier(.4,0,.2,1), box-shadow .2s ease, border-color .2s ease; }
.od-card:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(15,23,42,.10); }
.od-close { transition: background .15s ease, color .15s ease, border-color .15s ease; }
.od-close:hover { background: #f1f5f9 !important; color: #0f172a !important; border-color: #cbd5e1 !important; }
.od-fade { animation: od-fade .4s cubic-bezier(.4,0,.2,1); }
`;

// Animated flowing connector between pipeline nodes.
function FlowConnector({ color }) {
  return (
    <div
      aria-hidden="true"
      style={{
        position: 'relative',
        flex: '0 0 24px',
        minWidth: '24px',
        height: '3px',
        alignSelf: 'center',
        borderRadius: '999px',
        background: `linear-gradient(90deg, ${color.main}22 0%, ${color.main} 50%, ${color.main}22 100%)`,
        backgroundSize: '200% 100%',
        animation: 'od-flow 1.6s linear infinite',
        overflow: 'visible',
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: '50%',
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: color.main,
          boxShadow: `0 0 8px ${color.main}`,
          transform: 'translateY(-50%)',
          animation: 'od-dot 1.6s linear infinite',
        }}
      />
    </div>
  );
}

function StageCard({ stage, color, active, onActivate }) {
  return (
    <button
      type="button"
      className="od-stage"
      onMouseEnter={onActivate}
      onFocus={onActivate}
      onClick={onActivate}
      style={{
        flex: '1 1 0',
        minWidth: '94px',
        display: 'flex',
        flexDirection: 'column',
        gap: '3px',
        padding: '13px 11px',
        borderRadius: '14px',
        border: `2px solid ${active ? color.main : '#e8edf3'}`,
        background: active
          ? `linear-gradient(160deg, #ffffff 0%, ${color.soft} 100%)`
          : '#ffffff',
        boxShadow: active ? `0 8px 18px ${color.main}26` : '0 1px 3px rgba(15,23,42,0.06)',
        cursor: 'pointer',
        textAlign: 'left',
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '34px',
          height: '34px',
          borderRadius: '10px',
          fontSize: '19px',
          lineHeight: 1,
          background: active ? '#ffffff' : color.soft,
          boxShadow: active ? `0 2px 6px ${color.main}22` : 'none',
          marginBottom: '3px',
        }}
      >
        {stage.icon}
      </span>
      <span
        style={{
          fontSize: '13px',
          fontWeight: 800,
          color: color.deep,
        }}
      >
        {stage.verb}
      </span>
      <span style={{ fontSize: '10.5px', color: '#64748b' }}>{stage.title}</span>
      <span
        style={{
          marginTop: '5px',
          fontSize: '9px',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.4px',
          color: color.main,
        }}
      >
        {stage.owns}
      </span>
    </button>
  );
}

export function OrchestrationDiagram({ initialMode = 'voicelive' }) {
  const [mode, setMode] = useState(normalizeMode(initialMode));
  const [activeStage, setActiveStage] = useState(null);
  const [vlArch, setVlArch] = useState('native');
  const color = PALETTE[mode];

  const stages = mode === 'cascade' ? CASCADE_STAGES : [VOICELIVE_STAGE];
  const detail = useMemo(() => {
    if (mode === 'cascade') {
      return CASCADE_STAGES.find((s) => s.id === activeStage) || null;
    }
    return activeStage === 'managed' ? VOICELIVE_STAGE : null;
  }, [mode, activeStage]);

  const switchMode = (next) => {
    setMode(next);
    setActiveStage(null);
  };

  return (
    <div style={styles.root}>
      <style>{KEYFRAMES}</style>
      <div style={styles.header}>
        <p style={styles.title}>How voice orchestration works</p>
        <p style={styles.subtitle}>
          Every call needs to <strong>listen</strong>, <strong>think</strong>, then{' '}
          <strong>speak</strong>. The only question is how much of that you run yourself —
          it&apos;s a trade between <strong>simplicity</strong> and <strong>control</strong>.
        </p>
      </div>

      {/* Mode toggle */}
      <div style={styles.toggleRow}>
        {[
          { key: 'cascade', label: '🌐 Custom Speech Cascade' },
          { key: 'voicelive', label: '⚡️ VoiceLive' },
        ].map((opt) => {
          const selected = mode === opt.key;
          const c = PALETTE[opt.key];
          return (
            <button
              key={opt.key}
              type="button"
              onClick={() => switchMode(opt.key)}
              style={{
                flex: 1,
                padding: '9px 10px',
                borderRadius: '9px',
                border: selected ? `1px solid ${c.main}` : '1px solid transparent',
                background: selected ? '#fff' : 'transparent',
                color: selected ? c.deep : '#64748b',
                fontSize: '12.5px',
                fontWeight: selected ? 800 : 600,
                cursor: 'pointer',
                boxShadow: selected ? '0 1px 4px rgba(15,23,42,0.12)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      {/* Flow diagram */}
      <div style={styles.flowWrap}>
        <span
          style={{
            ...styles.ownerBand,
            background: color.soft,
            color: color.deep,
            border: `1px solid ${color.main}55`,
          }}
        >
          {mode === 'cascade' ? '🛠️ You orchestrate each component' : '☁️ Azure manages the pipeline'}
        </span>

        <div style={styles.pipeline} className="od-fade" key={mode}>
          <div style={styles.endpoint}>
            <span style={{ fontSize: '17px' }}>📞</span>
            Caller audio
          </div>
          <FlowConnector color={color} />

          {stages.map((stage, idx) => (
            <React.Fragment key={stage.id}>
              <StageCard
                stage={stage}
                color={color}
                active={activeStage === stage.id}
                onActivate={() => setActiveStage(stage.id)}
              />
              {(idx < stages.length - 1 || mode === 'voicelive') && (
                <FlowConnector color={color} />
              )}
            </React.Fragment>
          ))}

          {mode === 'cascade' && <FlowConnector color={color} />}
          <div style={styles.endpoint}>
            <span style={{ fontSize: '17px' }}>🔈</span>
            Caller audio
          </div>
        </div>

        {/* VoiceLive architecture sub-toggle */}
        {mode === 'voicelive' && (
          <div style={{ marginTop: '14px' }}>
            <div
              style={{
                fontSize: '10px',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
                color: '#94a3b8',
                marginBottom: '6px',
              }}
            >
              Inside VoiceLive
            </div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {VOICELIVE_ARCHS.map((a) => {
                const selected = vlArch === a.id;
                return (
                  <button
                    key={a.id}
                    type="button"
                    className="od-card"
                    onClick={() => setVlArch(a.id)}
                    style={{
                      flex: '1 1 180px',
                      textAlign: 'left',
                      padding: '11px 13px',
                      borderRadius: '12px',
                      border: `1.5px solid ${selected ? color.main : '#e8edf3'}`,
                      background: selected
                        ? `linear-gradient(160deg, #ffffff 0%, ${color.soft} 100%)`
                        : '#fff',
                      boxShadow: selected ? `0 6px 14px ${color.main}1f` : '0 1px 2px rgba(15,23,42,0.05)',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontSize: '12px', fontWeight: 800, color: '#0f172a' }}>
                      {a.id === 'native' ? '🎙️ ' : '🔤 '}
                      {a.label}
                    </div>
                    <div style={{ fontSize: '10.5px', color: '#64748b', marginTop: '3px', lineHeight: 1.45 }}>
                      {a.blurb}
                    </div>
                  </button>
                );
              })}
            </div>

            {vlArch === 'native' && (
              <>
                {/* How transcription works for native speech-to-speech */}
                <div
                  style={{
                    marginTop: '10px',
                    padding: '12px',
                    borderRadius: '10px',
                    border: '1px solid #e2e8f0',
                    background: '#fff',
                  }}
                >
                  <div
                    style={{
                      fontSize: '10px',
                      fontWeight: 800,
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      color: '#94a3b8',
                      marginBottom: '10px',
                    }}
                  >
                    Where the transcript comes from
                  </div>

                  {/* Main path: audio reasons in audio */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '2px', flexWrap: 'wrap' }}>
                    <div style={styles.endpoint}>
                      <span style={{ fontSize: '15px' }}>🎤</span>
                      Audio in
                    </div>
                    <FlowConnector color={color} />
                    <div
                      style={{
                        flex: '1 1 0',
                        minWidth: '150px',
                        padding: '12px',
                        borderRadius: '14px',
                        border: `2px solid ${color.main}`,
                        background: `linear-gradient(160deg, #ffffff 0%, ${color.soft} 100%)`,
                        textAlign: 'center',
                        boxShadow: `0 6px 16px ${color.main}22`,
                      }}
                    >
                      <div style={{ fontSize: '19px', lineHeight: 1 }}>🎙️</div>
                      <div style={{ fontSize: '12px', fontWeight: 800, color: color.deep, marginTop: '3px' }}>
                        Realtime model
                      </div>
                      <div style={{ fontSize: '10px', color: '#64748b' }}>
                        reasons directly on <strong>audio</strong>
                      </div>
                    </div>
                    <FlowConnector color={color} />
                    <div style={styles.endpoint}>
                      <span style={{ fontSize: '15px' }}>🔈</span>
                      Audio out
                    </div>
                  </div>

                  {/* Side branch: the "best guess" transcript */}
                  <div style={{ display: 'flex', gap: '10px', marginTop: '6px', alignItems: 'stretch' }}>
                    <div
                      style={{
                        width: '66px',
                        display: 'flex',
                        justifyContent: 'center',
                        position: 'relative',
                      }}
                    >
                      <div
                        style={{
                          width: '2px',
                          background: `linear-gradient(180deg, ${color.main}, ${color.main}22)`,
                          borderRadius: '999px',
                        }}
                      />
                      <span
                        style={{
                          position: 'absolute',
                          bottom: '-2px',
                          color: color.main,
                          fontSize: '13px',
                          lineHeight: 1,
                        }}
                      >
                        ▼
                      </span>
                    </div>
                    <div
                      style={{
                        flex: 1,
                        padding: '10px 12px',
                        borderRadius: '12px',
                        border: '1px dashed #cbd5e1',
                        background: 'linear-gradient(160deg, #ffffff 0%, #f8fafc 100%)',
                      }}
                    >
                      <div style={{ fontSize: '11.5px', fontWeight: 700, color: '#475569' }}>
                        📝 Transcript — a “best guess”
                      </div>
                      <div style={{ fontSize: '10.5px', color: '#64748b', marginTop: '3px', lineHeight: 1.5 }}>
                        Generated <em>on the side</em> for your UI &amp; logs. The model never
                        reads this text — it already reasoned on the raw audio, so the transcript
                        can differ from what actually drove the reply.
                      </div>
                    </div>
                  </div>
                </div>

                {/* Realtime model caveats */}
                <div
                  style={{
                    marginTop: '10px',
                    padding: '10px 12px',
                    borderRadius: '10px',
                    background: 'linear-gradient(135deg, #fffbeb, #fef3c7)',
                    border: '1px solid #fcd34d',
                    fontSize: '11px',
                    lineHeight: 1.5,
                    color: '#78350f',
                  }}
                >
                  <strong>⚠️ Realtime models:</strong> can&apos;t be fine-tuned and bill premium
                  audio tokens. Going to prod? Benchmark them against higher-throughput text LLMs
                  (Cascade) with a robust eval suite in{' '}
                  <a
                    href="https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-approach-gen-ai"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#b45309', fontWeight: 700 }}
                  >
                    Azure AI Foundry
                  </a>{' '}
                  first.
                </div>
              </>
            )}

            {vlArch === 'cascaded' && (
              <div
                style={{
                  marginTop: '10px',
                  padding: '12px',
                  borderRadius: '12px',
                  border: '1px solid #e8edf3',
                  background: 'linear-gradient(180deg, #ffffff 0%, #f7f9fc 100%)',
                }}
              >
                <div
                  style={{
                    fontSize: '10px',
                    fontWeight: 800,
                    textTransform: 'uppercase',
                    letterSpacing: '0.5px',
                    color: '#94a3b8',
                    marginBottom: '10px',
                  }}
                >
                  The cascade — but Azure runs it
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '2px', flexWrap: 'nowrap', overflowX: 'auto', overflowY: 'visible', padding: '14px 0 2px' }}>
                  <div style={styles.endpoint}>
                    <span style={{ fontSize: '15px' }}>🎤</span>
                    Audio in
                  </div>
                  <FlowConnector color={color} />

                  {/* Managed wrapper containing the 3 cascade steps */}
                  <div
                    style={{
                      flex: '1 1 0',
                      minWidth: '230px',
                      position: 'relative',
                      padding: '18px 12px 12px',
                      borderRadius: '14px',
                      border: `2px dashed ${color.main}`,
                      background: color.soft,
                    }}
                  >
                    <span
                      style={{
                        position: 'absolute',
                        top: '-9px',
                        left: '12px',
                        padding: '2px 9px',
                        borderRadius: '999px',
                        background: `linear-gradient(135deg, ${color.main}, ${color.deep})`,
                        color: '#fff',
                        fontSize: '9px',
                        fontWeight: 800,
                        textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                        boxShadow: `0 3px 8px ${color.main}44`,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      ⚡️ Azure Voice Live · managed
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                      {[
                        { icon: '🎧', label: 'STT' },
                        { icon: '🧠', label: 'LLM' },
                        { icon: '🔊', label: 'TTS' },
                      ].map((step, i, arr) => (
                        <React.Fragment key={step.label}>
                          <div
                            style={{
                              flex: '1 1 0',
                              minWidth: '54px',
                              textAlign: 'center',
                              padding: '8px 4px',
                              borderRadius: '10px',
                              background: '#fff',
                              border: `1px solid ${color.main}33`,
                              boxShadow: '0 1px 3px rgba(15,23,42,0.06)',
                            }}
                          >
                            <div style={{ fontSize: '16px', lineHeight: 1 }}>{step.icon}</div>
                            <div style={{ fontSize: '10px', fontWeight: 800, color: color.deep, marginTop: '2px' }}>
                              {step.label}
                            </div>
                          </div>
                          {i < arr.length - 1 && <FlowConnector color={color} />}
                        </React.Fragment>
                      ))}
                    </div>
                  </div>

                  <FlowConnector color={color} />
                  <div style={styles.endpoint}>
                    <span style={{ fontSize: '15px' }}>🔈</span>
                    Audio out
                  </div>
                </div>

                <div style={{ fontSize: '10.5px', color: '#475569', marginTop: '10px', lineHeight: 1.5 }}>
                  Same <strong>Listen → Think → Speak</strong> as Custom Speech — Azure just hosts
                  and runs the three steps for you behind one connection. Because there&apos;s a
                  real STT step, the transcript is the <strong>actual recognized text</strong>,
                  not a best guess.
                </div>
              </div>
            )}
          </div>
        )}

        {/* Stage detail */}
        {detail && (
          <div
            style={{
              ...styles.detailPanel,
              background: color.soft,
              border: `1px solid ${color.main}44`,
              color: color.deep,
            }}
          >
            <strong>
              {detail.icon} {detail.title}
            </strong>{' '}
            — {detail.detail}
          </div>
        )}
      </div>

      {/* Simplicity ↔ Control spectrum */}
      <div
        style={{
          border: '1px solid #e8edf3',
          borderRadius: '16px',
          padding: '16px 18px',
          marginBottom: '14px',
          background: 'linear-gradient(180deg, #ffffff 0%, #f7f9fc 100%)',
          boxShadow: '0 1px 2px rgba(15,23,42,0.04)',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: '10px',
            fontWeight: 800,
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            marginBottom: '10px',
          }}
        >
          <span style={{ color: PALETTE.voicelive.deep }}>← Simpler to run</span>
          <span style={{ color: PALETTE.cascade.deep }}>More control →</span>
        </div>
        <div
          style={{
            position: 'relative',
            height: '10px',
            borderRadius: '999px',
            background: `linear-gradient(90deg, ${PALETTE.voicelive.main}, #a78bfa 45%, #6ea8e0 55%, ${PALETTE.cascade.main})`,
            boxShadow: '0 2px 8px rgba(99,102,241,0.25)',
          }}
        >
          {/* VoiceLive marker (left) */}
          <span
            style={{
              position: 'absolute',
              left: '8%',
              top: '50%',
              transform: 'translate(-50%, -50%)',
              width: '26px',
              height: '26px',
              borderRadius: '50%',
              background: '#fff',
              boxShadow: '0 2px 6px rgba(15,23,42,0.2)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '14px',
            }}
            title="VoiceLive"
          >
            ⚡️
          </span>
          {/* Custom Speech marker (right) */}
          <span
            style={{
              position: 'absolute',
              left: '92%',
              top: '50%',
              transform: 'translate(-50%, -50%)',
              width: '26px',
              height: '26px',
              borderRadius: '50%',
              background: '#fff',
              boxShadow: '0 2px 6px rgba(15,23,42,0.2)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '14px',
            }}
            title="Custom Speech"
          >
            🌐
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px' }}>
          <span style={{ fontSize: '11px', fontWeight: 700, color: PALETTE.voicelive.deep }}>
            VoiceLive
          </span>
          <span style={{ fontSize: '11px', fontWeight: 700, color: PALETTE.cascade.deep }}>
            Custom Speech
          </span>
        </div>
      </div>

      {/* Two plain-language summary cards */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
        {[SUMMARY.voicelive, SUMMARY.cascade].map((card) => {
          const c = PALETTE[card.accent];
          const isActive = mode === card.accent;
          return (
            <div
              key={card.name}
              className="od-card"
              style={{
                flex: '1 1 220px',
                borderRadius: '16px',
                padding: '15px',
                border: `2px solid ${isActive ? c.main : '#e8edf3'}`,
                background: isActive
                  ? `linear-gradient(160deg, #ffffff 0%, ${c.soft} 100%)`
                  : '#fff',
                boxShadow: isActive ? `0 8px 18px ${c.main}1f` : '0 1px 3px rgba(15,23,42,0.05)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '36px',
                    height: '36px',
                    borderRadius: '11px',
                    background: c.soft,
                    fontSize: '19px',
                  }}
                >
                  {card.icon}
                </span>
                <div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: '#0f172a' }}>{card.name}</div>
                  <div style={{ fontSize: '10px', fontWeight: 700, color: c.deep, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                    {card.tagline}
                  </div>
                </div>
              </div>
              <ul style={{ margin: '0 0 8px', paddingLeft: '0', listStyle: 'none' }}>
                {card.points.map((p) => (
                  <li
                    key={p}
                    style={{
                      display: 'flex',
                      gap: '6px',
                      fontSize: '11.5px',
                      color: '#334155',
                      lineHeight: 1.5,
                      marginBottom: '3px',
                    }}
                  >
                    <span style={{ color: c.main, fontWeight: 800 }}>•</span>
                    {p}
                  </li>
                ))}
              </ul>
              <div style={{ fontSize: '10.5px', color: '#64748b', fontStyle: 'italic', lineHeight: 1.45 }}>
                {card.bestFor}
              </div>
            </div>
          );
        })}
      </div>

      <p style={{ fontSize: '10.5px', color: '#94a3b8', margin: '12px 2px 0', lineHeight: 1.5 }}>
        Either way you run the <strong>same</strong> agents and tools — you can switch modes any
        time without rebuilding your agent.
      </p>
    </div>
  );
}

export function OrchestrationDiagramModal({ open, onClose, initialMode = 'voicelive' }) {
  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 2000,
        background: 'rgba(15,23,42,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        backdropFilter: 'blur(2px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: '640px',
          maxHeight: '88vh',
          overflowY: 'auto',
          background: '#fff',
          borderRadius: '18px',
          boxShadow: '0 24px 64px rgba(15,23,42,0.4)',
          padding: '22px',
        }}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="od-close"
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            width: '32px',
            height: '32px',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 0,
            borderRadius: '50%',
            border: '1px solid #e2e8f0',
            background: '#fff',
            color: '#64748b',
            fontSize: '15px',
            lineHeight: 1,
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(15,23,42,0.08)',
          }}
        >
          ✕
        </button>
        <OrchestrationDiagram initialMode={initialMode} />
      </div>
    </div>,
    document.body,
  );
}

export default OrchestrationDiagram;
