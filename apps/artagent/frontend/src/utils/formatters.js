import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import ErrorOutlineRoundedIcon from '@mui/icons-material/ErrorOutlineRounded';
import InfoRoundedIcon from '@mui/icons-material/InfoRounded';
import PhoneInTalkRoundedIcon from '@mui/icons-material/PhoneInTalkRounded';
import WarningAmberRoundedIcon from '@mui/icons-material/WarningAmberRounded';

export const formatAgentInventory = (payload = {}) => {
  if (!payload || payload.type !== 'agent_inventory') return null;
  const agentsRaw = payload.agents || payload.agent_summaries || payload.summaries || [];
  const agents = Array.isArray(agentsRaw) ? agentsRaw : [];
  const countFromPayload =
    typeof payload.agent_count === 'number'
      ? payload.agent_count
      : typeof payload.count === 'number'
      ? payload.count
      : null;
  const count = Math.max(countFromPayload ?? 0, agents.length);
  return {
    source: payload.source || 'unified',
    scenario: payload.scenario || null,
    startAgent: payload.start_agent || null,
    count,
    agents: agents.map((a) => ({
      name: a.name,
      description: a.description,
      greeting: !!a.greeting,
      returnGreeting: !!a.return_greeting,
      toolCount: a.tool_count || (a.tools || []).length,
      toolsPreview: a.tools_preview || a.tools || a.tool_names || a.toolNames || [],
      tools: a.tools || a.tools_preview || a.tool_names || a.toolNames || [],
      handoffTrigger: a.handoff_trigger || null,
      model: a.model || null,
      voice: a.voice || null,
    })),
    handoffMap: payload.handoff_map || {},
    connections: Object.entries(payload.handoff_map || {}).map(([tool, target]) => ({ tool, target })),
  };
};

export const formatStatusTimestamp = (isoValue) => {
  if (!isoValue) {
    return null;
  }
  const date = isoValue instanceof Date ? isoValue : new Date(isoValue);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

export const inferStatusTone = (textValue = '') => {
  const normalized = textValue.toLowerCase();
  const matchesAny = (needles) => needles.some((needle) => normalized.includes(needle));
  if (textValue.includes('❌') || textValue.includes('🚫') || matchesAny(['error', 'fail', 'critical'])) {
    return 'error';
  }
  if (textValue.includes('✅') || textValue.includes('🎉') || matchesAny(['success', 'ready', 'connected', 'restarted', 'completed'])) {
    return 'success';
  }
  if (textValue.includes('⚠️') || textValue.includes('🛑') || textValue.includes('📵') || matchesAny(['stopp', 'ended', 'disconnect', 'hang up', 'warning'])) {
    return 'warning';
  }
  return 'info';
};

export const formatEventTypeLabel = (value = '') => {
  if (!value) return 'System Event';
  return value
    .split(/[_\s]+/u)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ');
};

export const shortenIdentifier = (value) => {
  if (typeof value !== 'string') return value;
  return value.length > 14 ? `${value.slice(0, 6)}…${value.slice(-4)}` : value;
};

export const describeEventData = (data = {}) => {
  if (!data || typeof data !== 'object') {
    return null;
  }

  const summaryParts = [];
  const seen = new Set();
  const prioritizedKeys = [
    'message',
    'reason_label',
    'disconnect_reason',
    'caller_id',
    'call_connection_id',
    'browser_session_id',
    'connected_at',
    'ended_at',
  ];

  const formatKey = (key) =>
    key
      .split(/[_\s]+/u)
      .filter(Boolean)
      .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
      .join(' ');

  const formatValue = (key, value) => {
    if (value == null) return value;
    if (typeof value === 'number') return value;
    if (typeof value !== 'string') return value;
    if (key.includes('id')) return shortenIdentifier(value);
    if (key.includes('reason')) {
      return value
        .split(/[_\s]+/u)
        .filter(Boolean)
        .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
        .join(' ');
    }
    if (key.endsWith('_at')) {
      return formatStatusTimestamp(value) ?? value;
    }
    return value;
  };

  const appendSummary = (key, rawValue) => {
    if (rawValue == null || seen.has(key)) {
      return;
    }
    const formattedValue = formatValue(key, rawValue);
    if (formattedValue === undefined || formattedValue === null || formattedValue === '') {
      return;
    }
    summaryParts.push(`${formatKey(key)}: ${formattedValue}`);
    seen.add(key);
  };

  prioritizedKeys.forEach((key) => appendSummary(key, data[key]));

  if (!summaryParts.length) {
    Object.entries(data).forEach(([key, value]) => {
      if (seen.has(key)) return;
      if (typeof value === 'string' || typeof value === 'number') {
        appendSummary(key, value);
      }
    });
  }

  return summaryParts.length ? summaryParts.slice(0, 2).join(' • ') : null;
};

export const buildSystemMessage = (text, options = {}) => {
  const timestamp = options.timestamp ?? new Date().toISOString();
  const statusTone = options.statusTone ?? options.tone ?? inferStatusTone(text);
  return {
    speaker: 'System',
    text,
    statusTone,
    timestamp,
    statusCaption: options.statusCaption ?? null,
    statusLabel: options.statusLabel ?? null,
  };
};

export const STATUS_TONE_META = {
  info: {
    label: 'System Message',
    accent: '#2563eb',
    background: 'linear-gradient(135deg, rgba(37,99,235,0.08), rgba(14,116,144,0.06))',
    border: '1px solid rgba(37,99,235,0.18)',
    borderColor: 'rgba(37,99,235,0.18)',
    surface: 'rgba(37,99,235,0.12)',
    iconBackground: 'rgba(37,99,235,0.14)',
    icon: InfoRoundedIcon,
    textColor: '#0f172a',
    captionColor: 'rgba(15,23,42,0.65)',
  },
  success: {
    label: 'Event',
    accent: '#059669',
    background: 'linear-gradient(135deg, rgba(16,185,129,0.12), rgba(56,189,248,0.05))',
    border: '1px solid rgba(34,197,94,0.24)',
    borderColor: 'rgba(34,197,94,0.24)',
    surface: 'rgba(16,185,129,0.14)',
    iconBackground: 'rgba(16,185,129,0.18)',
    icon: CheckCircleRoundedIcon,
    textColor: '#064e3b',
    captionColor: 'rgba(6,78,59,0.7)',
  },
  warning: {
    label: 'Warning',
    accent: '#f59e0b',
    background: 'linear-gradient(135deg, rgba(245,158,11,0.14), rgba(249,115,22,0.08))',
    border: '1px solid rgba(245,158,11,0.28)',
    borderColor: 'rgba(245,158,11,0.28)',
    surface: 'rgba(245,158,11,0.16)',
    iconBackground: 'rgba(245,158,11,0.22)',
    icon: WarningAmberRoundedIcon,
    textColor: '#7c2d12',
    captionColor: 'rgba(124,45,18,0.7)',
  },
  call: {
    label: 'Call Live',
    accent: '#0ea5e9',
    background: 'linear-gradient(135deg, rgba(14,165,233,0.14), rgba(45,212,191,0.08))',
    border: '1px solid rgba(14,165,233,0.24)',
    borderColor: 'rgba(14,165,233,0.24)',
    surface: 'rgba(14,165,233,0.16)',
    iconBackground: 'rgba(14,165,233,0.22)',
    icon: PhoneInTalkRoundedIcon,
    textColor: '#0f172a',
    captionColor: 'rgba(15,23,42,0.55)',
  },
  error: {
    label: 'Action Needed',
    accent: '#ef4444',
    background: 'linear-gradient(135deg, rgba(239,68,68,0.12), rgba(249,115,22,0.05))',
    border: '1px solid rgba(239,68,68,0.26)',
    borderColor: 'rgba(239,68,68,0.26)',
    surface: 'rgba(239,68,68,0.14)',
    iconBackground: 'rgba(239,68,68,0.2)',
    icon: ErrorOutlineRoundedIcon,
    textColor: '#7f1d1d',
    captionColor: 'rgba(127,29,29,0.7)',
  },
};
