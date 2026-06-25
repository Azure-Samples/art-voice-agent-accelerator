import React, { useMemo, useState } from 'react';

const containerStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: '8px',
  width: '100%',
  maxWidth: '320px',
  padding: '10px 12px',
  borderRadius: '14px',
  background: 'rgba(255,255,255,0.9)',
  border: '1px solid rgba(226,232,240,0.8)',
  boxShadow: '0 8px 20px rgba(15,23,42,0.12)',
  boxSizing: 'border-box',
};

const headerStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  fontSize: '11px',
  color: '#475569',
  fontWeight: 600,
  letterSpacing: '0.03em',
};

const badgeBaseStyle = {
  fontSize: '9px',
  padding: '2px 8px',
  borderRadius: '999px',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const badgeToneStyles = {
  default: {
    backgroundColor: 'rgba(59, 130, 246, 0.12)',
    color: '#2563eb',
  },
  realtime: {
    backgroundColor: 'rgba(14,165,233,0.15)',
    color: '#0e7490',
  },
  neutral: {
    backgroundColor: 'rgba(148,163,184,0.18)',
    color: '#475569',
  },
};

const optionsRowStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: '8px',
  width: '100%',
};

const baseCardStyle = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-start',
  gap: '6px',
  padding: '10px 12px',
  width: '100%',
  borderRadius: '12px',
  border: '1px solid rgba(226,232,240,0.9)',
  background: '#f8fafc',
  cursor: 'pointer',
  transition: 'all 0.2s ease',
  boxShadow: '0 4px 8px rgba(15, 23, 42, 0.08)',
  textAlign: 'left',
};

const selectedCardStyle = {
  borderColor: 'rgba(99,102,241,0.85)',
  boxShadow: '0 8px 16px rgba(99,102,241,0.22)',
  background: 'linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(224,231,255,0.9) 100%)',
};

const optionHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: '10px',
  width: '100%',
};

const textBlockStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: '1px',
};

const disabledCardStyle = {
  cursor: 'not-allowed',
  opacity: 0.6,
  boxShadow: 'none',
};

const iconStyle = {
  fontSize: '18px',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '26px',
};

const titleStyle = {
  fontSize: '12px',
  fontWeight: 700,
  color: '#0f172a',
  margin: 0,
};

const descriptionStyle = {
  fontSize: '10px',
  color: '#475569',
  margin: 0,
  lineHeight: 1.5,
};

const hintStyle = {
  fontSize: '9px',
  color: '#1d4ed8',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const footerNoteStyle = {
  fontSize: '9px',
  color: '#94a3b8',
  lineHeight: 1.4,
};

const infoIconStyle = {
  marginLeft: 'auto',
  flexShrink: 0,
  width: '16px',
  height: '16px',
  borderRadius: '999px',
  border: '1px solid rgba(99,102,241,0.45)',
  color: '#6366f1',
  fontSize: '10px',
  fontWeight: 700,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: 'help',
  lineHeight: 1,
};

const tooltipStyle = {
  position: 'absolute',
  bottom: 'calc(100% + 8px)',
  right: '0',
  zIndex: 50,
  width: '288px',
  padding: '12px 14px',
  borderRadius: '12px',
  background: '#0f172a',
  color: '#e2e8f0',
  boxShadow: '0 12px 28px rgba(15,23,42,0.35)',
  fontSize: '11px',
  lineHeight: 1.55,
  textAlign: 'left',
  pointerEvents: 'none',
};

const tooltipTitleStyle = {
  fontSize: '11px',
  fontWeight: 700,
  color: '#ffffff',
  margin: '0 0 4px',
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
};

const tooltipBodyStyle = {
  margin: 0,
  color: '#cbd5e1',
};

const tooltipDividerStyle = {
  height: '1px',
  background: 'rgba(148,163,184,0.25)',
  margin: '8px 0',
};

const tooltipFootStyle = {
  margin: '8px 0 0',
  fontSize: '10px',
  color: '#94a3b8',
  fontStyle: 'italic',
};

const VOICE_LIVE_BASE_CONFIG = Object.freeze({
  orchestrator: 'voice_live_orchestration',
  contextKey: 'streaming_mode',
  endpoints: {
    acs: '/api/v1/calls/initiate',
    browser: '/api/v1/browser/conversation',
  },
});

const ACS_STREAMING_MODE_OPTIONS = [
  {
    value: 'voice_live',
    label: 'Voice Live',
    icon: '⚡️',
    description:
      'Ultra-low latency playback via Azure AI Voice Live. Ideal for PSTN calls with barge-in.',
    hint: 'Recommended',
    tooltip: {
      title: 'Managed speech channel',
      body:
        'Azure AI Voice Live hosts the entire STT → LLM → TTS loop as one managed realtime service. Speech-in and speech-out are handled for you — lowest latency (~200-400ms), native barge-in, and minimal orchestration code.',
      foot: 'Both modes work — Voice Live trades fine-grained control for simplicity and speed.',
    },
    config: {
      ...VOICE_LIVE_BASE_CONFIG,
      entryPoint: 'acs',
    },
  },
  {
    value: 'media',
    label: 'Custom Speech Cascade',
    icon: '🌐',
    description:
      'Composable STT → LLM → TTS cascade with full control over models, agent policies, voice personas, and adaptive routing.',
    tooltip: {
      title: 'Direct Azure Speech Services',
      body:
        'You orchestrate Azure Speech STT, the LLM, and Azure Speech TTS as separate components yourself. More moving parts, but you get fine-grained control over each model, voice persona, prompt routing, and adaptive policies.',
      foot: 'Both modes work — Custom Speech gives you a bit more control over every stage.',
    },
    config: {
      orchestrator: 'acs_media_pipeline',
      contextKey: 'streaming_mode',
      endpoints: {
        acs: '/api/v1/calls/initiate',
      },
    },
  },
];

const REALTIME_STREAMING_MODE_OPTIONS = [
  {
    value: 'voice_live',
    label: 'Voice Live Orchestration',
    icon: '⚡️',
    description:
      'Route /realtime sessions through the Voice Live orchestrator for dual-stream control.',
    hint: 'Voice Live stack',
    tooltip: {
      title: 'Managed speech channel',
      body:
        'Azure AI Voice Live hosts the entire STT → LLM → TTS loop as one managed realtime service. Speech-in and speech-out are handled for you — lowest latency (~200-400ms), native barge-in, and minimal orchestration code.',
      foot: 'Both modes work — Voice Live trades fine-grained control for simplicity and speed.',
    },
    config: {
      ...VOICE_LIVE_BASE_CONFIG,
      entryPoint: 'realtime',
    },
  },
  {
    value: 'realtime',
    label: 'Custom Speech Cascade',
    icon: '🌐',
    description:
      'Composable STT → LLM → TTS cascade with full control over models, agent policies, voice personas, and adaptive routing.',
    tooltip: {
      title: 'Direct Azure Speech Services',
      body:
        'You orchestrate Azure Speech STT, the LLM, and Azure Speech TTS as separate components yourself. More moving parts, but you get fine-grained control over each model, voice persona, prompt routing, and adaptive policies.',
      foot: 'Both modes work — Custom Speech gives you a bit more control over every stage.',
    },
    config: {
      orchestrator: 'browser_sdk_relay',
      endpoints: {
        browser: '/api/v1/browser/conversation',
      },
    },
  },
];

const buildGetLabel = (options) => (streamMode) => {
  const match = options.find((option) => option.value === streamMode);
  return match ? match.label : streamMode;
};

const getBadgeStyle = (tone = 'default') => ({
  ...badgeBaseStyle,
  ...(badgeToneStyles[tone] || badgeToneStyles.default),
});

function StreamingModeSelector({
  title = 'Streaming mode',
  badgeText,
  badgeTone = 'default',
  options = ACS_STREAMING_MODE_OPTIONS,
  value,
  onChange,
  onOptionSelect,
  disabled = false,
  footnote,
}) {
  const resolvedOptions = Array.isArray(options) ? options : [];
  const badgeStyles = useMemo(() => getBadgeStyle(badgeTone), [badgeTone]);
  const [hoveredValue, setHoveredValue] = useState(null);

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <span>{title}</span>
        {badgeText ? <span style={badgeStyles}>{badgeText}</span> : null}
      </div>
      <div style={optionsRowStyle}>
        {resolvedOptions.map((option) => {
          const isSelected = option.value === value;
          const showTooltip = option.tooltip && hoveredValue === option.value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                if (!disabled) {
                  onOptionSelect?.(option);
                  onChange?.(option.value, option);
                }
              }}
              onMouseEnter={() => option.tooltip && setHoveredValue(option.value)}
              onMouseLeave={() =>
                setHoveredValue((current) => (current === option.value ? null : current))
              }
              style={{
                ...baseCardStyle,
                ...(isSelected ? selectedCardStyle : {}),
                ...(disabled ? disabledCardStyle : {}),
                position: 'relative',
              }}
              disabled={disabled}
            >
              <div style={optionHeaderStyle}>
                <span style={iconStyle}>{option.icon}</span>
                <div style={textBlockStyle}>
                  <p style={titleStyle}>{option.label}</p>
                  <p style={descriptionStyle}>{option.description}</p>
                </div>
                {option.tooltip ? (
                  <span
                    style={infoIconStyle}
                    aria-hidden="true"
                    onMouseEnter={() => setHoveredValue(option.value)}
                  >
                    i
                  </span>
                ) : null}
              </div>
              {option.hint && isSelected && <span style={hintStyle}>{option.hint}</span>}
              {showTooltip ? (
                <div style={tooltipStyle} role="tooltip">
                  <p style={tooltipTitleStyle}>
                    <span>{option.icon}</span>
                    {option.tooltip.title}
                  </p>
                  <p style={tooltipBodyStyle}>{option.tooltip.body}</p>
                  {option.tooltip.foot ? (
                    <>
                      <div style={tooltipDividerStyle} />
                      <p style={tooltipFootStyle}>{option.tooltip.foot}</p>
                    </>
                  ) : null}
                </div>
              ) : null}
            </button>
          );
        })}
      </div>
      {footnote ? <div style={footerNoteStyle}>{footnote}</div> : null}
    </div>
  );
}

function AcsStreamingModeSelector({ onConfigChange, ...props }) {
  return (
    <StreamingModeSelector
      title="ACS Streaming Mode"
      badgeText="Telephony"
      badgeTone="default"
      options={ACS_STREAMING_MODE_OPTIONS}
      footnote="Active mode applies to ACS PSTN calls only. Browser/WebRTC streaming remains unchanged."
      onOptionSelect={(option) => onConfigChange?.(option?.config ?? null)}
      {...props}
    />
  );
}

function RealtimeStreamingModeSelector({ onConfigChange, ...props }) {
  return (
    <StreamingModeSelector
      title="Realtime streaming mode"
      badgeText="wss server"
      badgeTone="realtime"
      options={REALTIME_STREAMING_MODE_OPTIONS}
      footnote="Applies to the /realtime WebSocket endpoint and Voice Live orchestration pipeline."
      onOptionSelect={(option) => onConfigChange?.(option?.config ?? null)}
      {...props}
    />
  );
}

StreamingModeSelector.options = ACS_STREAMING_MODE_OPTIONS;
StreamingModeSelector.getLabel = buildGetLabel(ACS_STREAMING_MODE_OPTIONS);

AcsStreamingModeSelector.options = ACS_STREAMING_MODE_OPTIONS;
AcsStreamingModeSelector.getLabel = buildGetLabel(ACS_STREAMING_MODE_OPTIONS);

RealtimeStreamingModeSelector.options = REALTIME_STREAMING_MODE_OPTIONS;
RealtimeStreamingModeSelector.getLabel = buildGetLabel(REALTIME_STREAMING_MODE_OPTIONS);

export default StreamingModeSelector;
export { AcsStreamingModeSelector, RealtimeStreamingModeSelector };
