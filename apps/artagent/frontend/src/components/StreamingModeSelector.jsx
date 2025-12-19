import React, { useMemo } from 'react';

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

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <span>{title}</span>
        {badgeText ? <span style={badgeStyles}>{badgeText}</span> : null}
      </div>
      <div style={optionsRowStyle}>
        {resolvedOptions.map((option) => {
          const isSelected = option.value === value;
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
              style={{
                ...baseCardStyle,
                ...(isSelected ? selectedCardStyle : {}),
                ...(disabled ? disabledCardStyle : {}),
              }}
              disabled={disabled}
            >
              <div style={optionHeaderStyle}>
                <span style={iconStyle}>{option.icon}</span>
                <div style={textBlockStyle}>
                  <p style={titleStyle}>{option.label}</p>
                  <p style={descriptionStyle}>{option.description}</p>
                </div>
              </div>
              {option.hint && isSelected && <span style={hintStyle}>{option.hint}</span>}
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
