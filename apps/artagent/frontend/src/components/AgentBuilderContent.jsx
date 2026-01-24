/**
 * AgentBuilderContent Component
 * ==============================
 * 
 * The content portion of the AgentBuilder that can be embedded in 
 * the unified AgentScenarioBuilder dialog. This is a re-export that
 * wraps the original AgentBuilder to work in embedded mode.
 * 
 * For now, this imports and re-exports the original AgentBuilder
 * with a special prop to indicate embedded mode. The AgentBuilder
 * handles this by conditionally rendering without its Dialog wrapper.
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  AlertTitle,
  Autocomplete,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  LinearProgress,
  List,
  ListItem,
  ListItemAvatar,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Paper,
  Radio,
  Select,
  Slider,
  Stack,
  Tab,
  Tabs,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import RefreshIcon from '@mui/icons-material/Refresh';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import BuildIcon from '@mui/icons-material/Build';
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver';
import TuneIcon from '@mui/icons-material/Tune';
import CodeIcon from '@mui/icons-material/Code';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import CheckIcon from '@mui/icons-material/Check';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import MemoryIcon from '@mui/icons-material/Memory';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import EditIcon from '@mui/icons-material/Edit';
import HearingIcon from '@mui/icons-material/Hearing';
import CloseIcon from '@mui/icons-material/Close';
import DownloadIcon from '@mui/icons-material/Download';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import PersonIcon from '@mui/icons-material/Person';
import BusinessIcon from '@mui/icons-material/Business';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import BadgeIcon from '@mui/icons-material/Badge';
import InsightsIcon from '@mui/icons-material/Insights';

import { API_BASE_URL } from '../config/constants.js';
import logger from '../utils/logger.js';

// ═══════════════════════════════════════════════════════════════════════════════
// STYLES
// ═══════════════════════════════════════════════════════════════════════════════

const styles = {
  tabs: {
    borderBottom: 1,
    borderColor: 'divider',
    backgroundColor: '#fafbfc',
    '& .MuiTab-root': {
      textTransform: 'none',
      fontWeight: 600,
      minHeight: 48,
    },
    '& .Mui-selected': {
      color: '#1e3a5f',
    },
  },
  tabPanel: {
    padding: '24px',
    minHeight: '400px',
    height: 'calc(100% - 48px)',
    overflowY: 'auto',
    backgroundColor: '#fff',
  },
  sectionCard: {
    borderRadius: '12px',
    border: '1px solid #e5e7eb',
    boxShadow: 'none',
    '&:hover': {
      borderColor: '#c7d2fe',
      boxShadow: '0 2px 8px rgba(99, 102, 241, 0.08)',
    },
  },
  promptEditor: {
    fontFamily: '"Fira Code", "Consolas", monospace',
    fontSize: '13px',
    lineHeight: 1.6,
    '& .MuiInputBase-root': {
      backgroundColor: '#1e1e2e',
      color: '#cdd6f4',
      borderRadius: '8px',
    },
    '& .MuiInputBase-input': {
      color: '#cdd6f4',
    },
    '& .MuiInputBase-input::placeholder': {
      color: '#6c7086',
      opacity: 1,
    },
    '& .MuiInputLabel-root': {
      color: '#a6adc8',
      lineHeight: 1.2,
      transform: 'translate(14px, 14px) scale(1)',
    },
    '& .MuiInputLabel-root.MuiInputLabel-shrink': {
      transform: 'translate(14px, -18px) scale(0.75)',
    },
    '& .MuiInputLabel-root.Mui-focused': {
      color: '#89b4fa',
    },
    '& .MuiOutlinedInput-notchedOutline': {
      borderColor: '#45475a',
    },
    '& .MuiOutlinedInput-root:hover .MuiOutlinedInput-notchedOutline': {
      borderColor: '#585b70',
    },
    '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': {
      borderColor: '#89b4fa',
    },
  },
  templateVarChip: {
    fontFamily: 'monospace',
    fontSize: '12px',
    height: '28px',
    cursor: 'pointer',
    transition: 'all 0.2s',
    '&:hover': {
      transform: 'translateY(-1px)',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
    },
  },
};

const CASCADE_MODEL_PRESETS = [
  { id: 'gpt-4o', label: 'gpt-4o' },
  { id: 'gpt-4o-mini', label: 'gpt-4o-mini' },
  { id: 'gpt-4.1', label: 'gpt-4.1' },
  { id: 'gpt-4.1-mini', label: 'gpt-4.1-mini' },
  { id: 'gpt-4', label: 'gpt-4' },
  { id: 'gpt-5', label: 'gpt-5' },
  { id: 'gpt-5-mini', label: 'gpt-5-mini' },
  { id: 'gpt-5-nano', label: 'gpt-5-nano' },
  { id: 'o3-mini', label: 'o3-mini' },
  { id: 'o3', label: 'o3' },
  { id: 'o1', label: 'o1' },
];

const VOICELIVE_MODEL_PRESETS = [
  { id: 'gpt-realtime', label: 'gpt-realtime' },
  { id: 'gpt-realtime-mini', label: 'gpt-realtime-mini' },
  { id: 'gpt-4o', label: 'gpt-4o' },
  { id: 'gpt-4o-mini', label: 'gpt-4o-mini' },
  { id: 'gpt-4.1', label: 'gpt-4.1' },
  { id: 'gpt-4.1-mini', label: 'gpt-4.1-mini' },
  { id: 'gpt-5', label: 'gpt-5' },
  { id: 'gpt-5-mini', label: 'gpt-5-mini' },
  { id: 'gpt-5-nano', label: 'gpt-5-nano' },
  { id: 'gpt-5-chat', label: 'gpt-5-chat' },
  { id: 'phi4-mm-realtime', label: 'phi4-mm-realtime' },
  { id: 'phi4-mini', label: 'phi4-mini' },
];

const detectEndpointPreference = (deploymentId) => {
  const name = (deploymentId || '').toLowerCase();
  if (!name) {
    return 'chat';
  }
  if (name.includes('gpt-4')) {
    return 'chat';
  }
  if (name.includes('gpt-5') || name.includes('o1') || name.includes('o3') || name.includes('o4')) {
    return 'responses';
  }
  return 'responses';
};

const resolveEndpointPreference = (modelConfig) => {
  if (!modelConfig) {
    return 'chat';
  }
  const preference = modelConfig.endpoint_preference;
  if (preference && preference !== 'auto') {
    return preference;
  }
  return detectEndpointPreference(
    modelConfig.deployment_id || modelConfig.model_name || modelConfig.name
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// TAB PANEL
// ═══════════════════════════════════════════════════════════════════════════════

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`agent-builder-content-tabpanel-${index}`}
      {...other}
    >
      {value === index && <Box sx={styles.tabPanel}>{children}</Box>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEMPLATE VARIABLE REFERENCE
// ═══════════════════════════════════════════════════════════════════════════════

const TEMPLATE_VARIABLES = [
  {
    name: 'caller_name',
    description: 'Full name of the caller from session profile',
    example: '{{ caller_name | default("valued customer") }}',
    icon: <PersonIcon fontSize="small" />,
    source: 'Session Profile',
  },
  {
    name: 'institution_name',
    description: 'Name of your organization/institution',
    example: '{{ institution_name | default("Contoso Bank") }}',
    icon: <BusinessIcon fontSize="small" />,
    source: 'Template Vars',
  },
  {
    name: 'agent_name',
    description: 'Display name of the AI agent',
    example: '{{ agent_name | default("Assistant") }}',
    icon: <SmartToyIcon fontSize="small" />,
    source: 'Template Vars',
  },
  {
    name: 'client_id',
    description: 'Unique identifier for the customer',
    example: '{% if client_id %}Account: {{ client_id }}{% endif %}',
    icon: <BadgeIcon fontSize="small" />,
    source: 'Session Profile',
  },
  {
    name: 'customer_intelligence',
    description: 'Customer insights and preferences object',
    example: '{{ customer_intelligence.preferred_channel }}',
    icon: <InsightsIcon fontSize="small" />,
    source: 'Session Profile',
  },
  {
    name: 'session_profile',
    description: 'Full session profile object with all customer data',
    example: '{{ session_profile.email }}',
    icon: <AccountBalanceIcon fontSize="small" />,
    source: 'Core Memory',
  },
  {
    name: 'tools',
    description: 'List of available tool names for this agent',
    example: '{% for tool in tools %}{{ tool }}{% endfor %}',
    icon: <BuildIcon fontSize="small" />,
    source: 'Agent Config',
  },
];

const TRANSCRIPTION_MODELS = [
  { value: 'azure-speech', label: 'Azure Speech' },
  { value: 'gpt-4o-transcribe', label: 'GPT-4o Transcribe' },
  { value: 'whisper-1', label: 'Whisper-1' },
];

const TRANSCRIPTION_LANGUAGES = [
  { value: 'en-US', label: 'English (US)' },
  { value: 'en-GB', label: 'English (UK)' },
  { value: 'es-ES', label: 'Spanish (ES)' },
  { value: 'fr-FR', label: 'French (FR)' },
  { value: 'de-DE', label: 'German (DE)' },
  { value: 'it-IT', label: 'Italian (IT)' },
  { value: 'pt-BR', label: 'Portuguese (BR)' },
  { value: 'ja-JP', label: 'Japanese (JP)' },
  { value: 'ko-KR', label: 'Korean (KR)' },
  { value: 'zh-CN', label: 'Chinese (CN)' },
];

const TEMPLATE_VARIABLE_DOCS = [
  {
    key: 'caller_name',
    label: 'caller_name',
    type: 'string',
    source: 'Session Profile',
    paths: ['profile.caller_name', 'profile.name', 'profile.contact_info.full_name', 'profile.contact_info.first_name'],
    example: 'Ava Harper',
    description: 'Full name of the caller as captured or inferred from the session profile.',
  },
  {
    key: 'institution_name',
    label: 'institution_name',
    type: 'string',
    source: 'Template Vars (defaults) or Session Profile',
    paths: ['template_vars.institution_name', 'profile.institution_name'],
    example: 'Contoso Financial',
    description: 'Brand or institution name used for introductions and persona anchoring.',
  },
  {
    key: 'agent_name',
    label: 'agent_name',
    type: 'string',
    source: 'Template Vars (defaults)',
    paths: ['template_vars.agent_name'],
    example: 'Concierge',
    description: 'Display name of the current AI agent.',
  },
  {
    key: 'client_id',
    label: 'client_id',
    type: 'string',
    source: 'Session Profile / memo',
    paths: ['profile.client_id', 'profile.customer_id', 'profile.contact_info.client_id', 'memo_manager.client_id'],
    example: 'C123-9982',
    description: 'Internal customer identifier or account code if present in the session context.',
  },
  {
    key: 'customer_intelligence',
    label: 'customer_intelligence',
    type: 'object',
    source: 'Session Profile',
    paths: ['profile.customer_intelligence', 'profile.customer_intel'],
    example: '{ "preferred_channel": "voice", "risk_score": 0.12 }',
    description: 'Structured insight object about the customer (preferences, segments, scores).',
  },
  {
    key: 'customer_intelligence.relationship_context.relationship_tier',
    label: 'customer_intelligence.relationship_context.relationship_tier',
    type: 'string',
    source: 'Session Profile',
    paths: [
      'profile.customer_intelligence.relationship_context.relationship_tier',
      'profile.customer_intel.relationship_context.relationship_tier',
    ],
    example: 'Platinum',
    description: 'Relationship tier from customer_intelligence.relationship_context.',
  },
  {
    key: 'customer_intelligence.relationship_context.relationship_duration_years',
    label: 'customer_intelligence.relationship_context.relationship_duration_years',
    type: 'number',
    source: 'Session Profile',
    paths: [
      'profile.customer_intelligence.relationship_context.relationship_duration_years',
      'profile.customer_intel.relationship_context.relationship_duration_years',
    ],
    example: '8',
    description: 'Relationship duration (years) from customer_intelligence.relationship_context.',
  },
  {
    key: 'customer_intelligence.preferences.preferredContactMethod',
    label: 'customer_intelligence.preferences.preferredContactMethod',
    type: 'string',
    source: 'Session Profile',
    paths: [
      'profile.customer_intelligence.preferences.preferredContactMethod',
      'profile.customer_intel.preferences.preferredContactMethod',
    ],
    example: 'mobile',
    description: 'Preferred contact method from customer_intelligence.preferences.',
  },
  {
    key: 'customer_intelligence.bank_profile.current_balance',
    label: 'customer_intelligence.bank_profile.current_balance',
    type: 'number',
    source: 'Session Profile',
    paths: [
      'profile.customer_intelligence.bank_profile.current_balance',
      'profile.customer_intel.bank_profile.current_balance',
    ],
    example: '45230.50',
    description: 'Current balance from customer_intelligence.bank_profile.',
  },
  {
    key: 'customer_intelligence.spending_patterns.avg_monthly_spend',
    label: 'customer_intelligence.spending_patterns.avg_monthly_spend',
    type: 'number',
    source: 'Session Profile',
    paths: [
      'profile.customer_intelligence.spending_patterns.avg_monthly_spend',
      'profile.customer_intel.spending_patterns.avg_monthly_spend',
    ],
    example: '4500',
    description: 'Average monthly spend from customer_intelligence.spending_patterns.',
  },
  {
    key: 'session_profile',
    label: 'session_profile',
    type: 'object',
    source: 'Session Profile',
    paths: ['profile'],
    example: '{ "email": "user@example.com", "contact_info": { ... } }',
    description: 'Full session profile object containing contact_info, verification codes, and custom fields.',
  },
  {
    key: 'session_profile.email',
    label: 'session_profile.email',
    type: 'string',
    source: 'Session Profile',
    paths: ['profile.email'],
    example: 'user@example.com',
    description: 'Email from the session profile.',
  },
  {
    key: 'session_profile.contact_info.phone_last_4',
    label: 'session_profile.contact_info.phone_last_4',
    type: 'string',
    source: 'Session Profile',
    paths: ['profile.contact_info.phone_last_4'],
    example: '5678',
    description: 'Phone last 4 from session profile contact_info.',
  },
  {
    key: 'tools',
    label: 'tools',
    type: 'array<string>',
    source: 'Agent Config',
    paths: ['tools'],
    example: '["get_account_summary", "handoff_to_auth"]',
    description: 'List of enabled tool names for the agent (honors your current selection).',
  },
];

// Extract Jinja-style variables from text (e.g., "{{ caller_name }}", "{{ user.name | default('') }}")
const extractJinjaVariables = (text = '') => {
  const vars = new Set();
  const regex = /\{\{\s*([a-zA-Z0-9_.]+)(?:\s*\|[^}]*)?\s*\}\}/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    const candidate = match[1];
    if (candidate) {
        const trimmed = candidate.trim();
        if (trimmed) {
          vars.add(trimmed);
          const root = trimmed.split('.')[0];
          if (root) vars.add(root);
        }
    }
  }
  return Array.from(vars);
};

// ═══════════════════════════════════════════════════════════════════════════════
// TEMPLATE VARIABLE HELPER COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

const TemplateVariableHelper = React.memo(function TemplateVariableHelper({ onInsert, usedVars = [] }) {
  const [copiedVar, setCopiedVar] = useState(null);
  const [expanded, setExpanded] = useState(true);
  const usedSet = useMemo(() => new Set(usedVars || []), [usedVars]);

  const varsBySource = useMemo(() => {
    const groups = {
      'Session Profile': [],
      'Customer Intelligence': [],
      Other: [],
    };
    TEMPLATE_VARIABLE_DOCS.forEach((doc) => {
      const key = doc.key || '';
      if (key.startsWith('customer_intelligence')) {
        groups['Customer Intelligence'].push(doc);
      } else if (key.startsWith('session_profile')) {
        groups['Session Profile'].push(doc);
      } else {
        groups.Other.push(doc);
      }
    });
    Object.keys(groups).forEach((key) => {
      groups[key].sort((a, b) => a.label.localeCompare(b.label));
    });
    return groups;
  }, []);

  const handleCopy = useCallback(
    (varName) => {
      const textToCopy = `{{ ${varName} }}`;
      navigator.clipboard.writeText(textToCopy);
      setCopiedVar(varName);
      setTimeout(() => setCopiedVar(null), 2000);
      if (onInsert) onInsert(textToCopy);
    },
    [onInsert],
  );

  return (
    <Card variant="outlined" sx={{ ...styles.sectionCard, mb: 2 }}>
      <CardContent sx={{ pb: '12px !important' }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2, justifyContent: 'space-between' }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <InfoOutlinedIcon color="primary" fontSize="small" />
            <Typography variant="subtitle2" color="primary">
              Available Template Variables
            </Typography>
          </Stack>
          <Button size="small" onClick={() => setExpanded((prev) => !prev)}>
            {expanded ? 'Hide' : 'Show'}
          </Button>
        </Stack>
        <Collapse in={expanded} timeout="auto">
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
            Click a variable to copy. These are populated from the session profile at runtime.
          </Typography>
          <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
            <Chip label="Used in template" size="small" color="success" variant="filled" />
            <Chip label="Not used" size="small" variant="outlined" />
          </Stack>
          <Stack spacing={1.5}>
            {Object.entries(varsBySource).map(([source, docs]) => (
              <Box key={source}>
                <Typography variant="caption" sx={{ fontWeight: 700, color: '#475569', mb: 0.5, display: 'block' }}>
                  {source}
                </Typography>
                <Stack direction="row" flexWrap="wrap" gap={1}>
                  {docs.map((doc) => {
                    const active = usedSet.has(doc.key) || copiedVar === doc.key;
                    return (
                      <Tooltip
                        key={doc.key}
                        title={
                          <Box sx={{ p: 0.5 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>{doc.description}</Typography>
                            <Typography variant="caption" sx={{ fontFamily: 'monospace', color: '#93c5fd' }}>
                              {doc.example}
                            </Typography>
                            <Typography variant="caption" display="block" sx={{ mt: 0.5, color: '#a5b4fc' }}>
                              Type: {doc.type}
                            </Typography>
                          </Box>
                        }
                        arrow
                      >
                        <Chip
                          icon={copiedVar === doc.key ? <CheckIcon fontSize="small" /> : undefined}
                          label={`{{ ${doc.key} }}`}
                          size="small"
                          variant={active ? 'filled' : 'outlined'}
                          color={active ? 'success' : 'default'}
                          onClick={() => handleCopy(doc.key)}
                          sx={styles.templateVarChip}
                        />
                      </Tooltip>
                    );
                  })}
                </Stack>
              </Box>
            ))}
          </Stack>
        </Collapse>
      </CardContent>
    </Card>
  );
});

// ═══════════════════════════════════════════════════════════════════════════════
// INLINE VARIABLE PICKER (Collapsed by default, shows under each field)
// ═══════════════════════════════════════════════════════════════════════════════

const InlineVariablePicker = React.memo(function InlineVariablePicker({ onInsert, usedVars = [] }) {
  const [expanded, setExpanded] = useState(false);
  const [copiedVar, setCopiedVar] = useState(null);
  const usedSet = useMemo(() => new Set(usedVars || []), [usedVars]);

  // Common variables for greetings
  const commonVars = useMemo(() => [
    { key: 'caller_name', example: '{{ caller_name | default("valued customer") }}' },
    { key: 'agent_name', example: '{{ agent_name | default("Assistant") }}' },
    { key: 'institution_name', example: '{{ institution_name | default("our organization") }}' },
    { key: 'client_id', example: '{{ client_id }}' },
  ], []);

  const handleInsert = useCallback((varName) => {
    const textToCopy = `{{ ${varName} }}`;
    navigator.clipboard.writeText(textToCopy);
    setCopiedVar(varName);
    setTimeout(() => setCopiedVar(null), 1500);
    if (onInsert) onInsert(textToCopy);
  }, [onInsert]);

  return (
    <Box sx={{ mt: 0.5 }}>
      <Button
        size="small"
        onClick={() => setExpanded(!expanded)}
        startIcon={<CodeIcon fontSize="small" />}
        sx={{ 
          textTransform: 'none', 
          fontSize: '12px', 
          color: '#6366f1',
          p: 0,
          minWidth: 'auto',
          '&:hover': { backgroundColor: 'transparent', textDecoration: 'underline' }
        }}
      >
        {expanded ? 'Hide variables' : 'Insert template variable'}
      </Button>
      <Collapse in={expanded} timeout="auto">
        <Box sx={{ mt: 1, p: 1.5, backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
            Click to copy. Use <code>{'{{ var | default("fallback") }}'}</code> for defaults.
          </Typography>
          <Stack direction="row" flexWrap="wrap" gap={0.5}>
            {commonVars.map((v) => {
              const isUsed = usedSet.has(v.key);
              const isCopied = copiedVar === v.key;
              return (
                <Tooltip key={v.key} title={v.example} arrow>
                  <Chip
                    icon={isCopied ? <CheckIcon fontSize="small" /> : undefined}
                    label={`{{ ${v.key} }}`}
                    size="small"
                    variant={isUsed || isCopied ? 'filled' : 'outlined'}
                    color={isCopied ? 'success' : isUsed ? 'primary' : 'default'}
                    onClick={() => handleInsert(v.key)}
                    sx={{ 
                      fontSize: '11px', 
                      height: '24px',
                      cursor: 'pointer',
                      fontFamily: 'monospace',
                    }}
                  />
                </Tooltip>
              );
            })}
          </Stack>
          <Typography variant="caption" sx={{ display: 'block', mt: 1, color: '#64748b' }}>
            Conditionals: <code>{'{% if caller_name %}Hi {{ caller_name }}{% endif %}'}</code>
          </Typography>
        </Box>
      </Collapse>
    </Box>
  );
});

const getVoiceLabel = (agent) => {
  const voice = agent?.voice || {};
  return (
    voice.display_name ||
    voice.name ||
    voice.voice_name ||
    voice.voiceName ||
    'Default'
  );
};

const getModelName = (model) => {
  const resolved = model || {};
  return (
    resolved.deployment_id ||
    resolved.model_name ||
    resolved.name ||
    resolved.deployment ||
    'Default'
  );
};

const getModelLabel = (agent) => getModelName(agent?.model || agent?.cascade_model || agent?.voicelive_model);

const getCascadeLabel = (agent) => getModelName(agent?.cascade_model);

const getVoiceLiveLabel = (agent) => getModelName(agent?.voicelive_model);

const formatToolName = (tool) => {
  if (!tool) return '';
  if (typeof tool === 'string') return tool;
  return tool.name || tool.tool_name || String(tool);
};

function AgentDetailsDialog({ open, onClose, agent, loading }) {
  const promptText =
    agent?.prompt_full || agent?.prompt || agent?.prompt_preview || '';
  const tools = (agent?.tools || []).map(formatToolName).filter(Boolean);
  const voiceLabel = getVoiceLabel(agent);
  const modelLabel = getModelLabel(agent);
  const cascadeLabel = getCascadeLabel(agent);
  const voiceLiveLabel = getVoiceLiveLabel(agent);
  const promptIsPreview = !agent?.prompt_full && !agent?.prompt && !!agent?.prompt_preview;

  if (!open) return null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" alignItems="center" spacing={2}>
          <Avatar sx={{ bgcolor: '#0ea5e9' }}>
            {agent?.name?.[0] || 'A'}
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {agent?.name || 'Agent Details'}
              </Typography>
              {agent?.is_entry_point && (
                <Chip size="small" color="primary" label="Entry" />
              )}
            </Stack>
            <Typography variant="body2" color="text.secondary" noWrap>
              {agent?.description || 'No description provided'}
            </Typography>
          </Box>
          <IconButton onClick={onClose} size="small">
            <CloseIcon />
          </IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent dividers sx={{ p: 0 }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
            <CircularProgress />
          </Box>
        ) : (
          <Stack spacing={0}>
            <Box sx={{ p: 2, borderBottom: '1px solid #e5e7eb' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                Snapshot
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ gap: 1 }}>
                <Chip
                  size="small"
                  icon={<BuildIcon sx={{ fontSize: 14 }} />}
                  label={`${tools.length} tools`}
                />
                <Chip
                  size="small"
                  icon={<RecordVoiceOverIcon sx={{ fontSize: 14 }} />}
                  label={voiceLabel}
                />
                <Chip
                  size="small"
                  icon={<MemoryIcon sx={{ fontSize: 14 }} />}
                  label={modelLabel}
                />
                <Chip
                  size="small"
                  icon={<MemoryIcon sx={{ fontSize: 14 }} />}
                  label={`Cascade ${cascadeLabel}`}
                />
                <Chip
                  size="small"
                  icon={<HearingIcon sx={{ fontSize: 14 }} />}
                  label={`VoiceLive ${voiceLiveLabel}`}
                />
              </Stack>
            </Box>

            {(agent?.greeting || agent?.return_greeting) && (
              <Box sx={{ p: 2, borderBottom: '1px solid #e5e7eb' }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                  Greetings
                </Typography>
                <Stack spacing={1}>
                  {agent?.greeting && (
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                        Initial Greeting
                      </Typography>
                      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, mt: 0.5 }}>
                        <Typography
                          variant="body2"
                          sx={{ fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap' }}
                        >
                          {agent.greeting}
                        </Typography>
                      </Paper>
                    </Box>
                  )}
                  {agent?.return_greeting && (
                    <Box>
                      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                        Return Greeting
                      </Typography>
                      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, mt: 0.5 }}>
                        <Typography
                          variant="body2"
                          sx={{ fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap' }}
                        >
                          {agent.return_greeting}
                        </Typography>
                      </Paper>
                    </Box>
                  )}
                </Stack>
              </Box>
            )}

            <Box sx={{ p: 2, borderBottom: '1px solid #e5e7eb' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                Prompt {promptIsPreview ? '(Preview)' : ''}
              </Typography>
              {promptText ? (
                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, maxHeight: 260, overflow: 'auto' }}>
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap' }}
                  >
                    {promptText}
                  </Typography>
                </Paper>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No prompt available
                </Typography>
              )}
            </Box>

            <Box sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                Tools
              </Typography>
              {tools.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No tools configured for this agent
                </Typography>
              ) : (
                <Stack direction="row" flexWrap="wrap" gap={1}>
                  {tools.map((tool) => (
                    <Chip
                      key={tool}
                      label={tool}
                      size="small"
                      sx={{ fontFamily: 'monospace', fontSize: 11 }}
                    />
                  ))}
                </Stack>
              )}
            </Box>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// Export for use in other components
export { AgentDetailsDialog };

function ToolDetailsDialog({ open, onClose, tool }) {
  if (!tool) return null;

  const parameters = tool.parameters ? JSON.stringify(tool.parameters, null, 2) : null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box
            sx={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              backgroundColor: '#eef2ff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <BuildIcon sx={{ fontSize: 16, color: '#4338ca' }} />
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              {tool.name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Tool details
            </Typography>
          </Box>
          <IconButton onClick={onClose} size="small">
            <CloseIcon />
          </IconButton>
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
              Description
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {tool.description || 'No description provided.'}
            </Typography>
          </Box>

          {tool.tags?.length > 0 && (
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                Tags
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={1}>
                {tool.tags.map((tag) => (
                  <Chip key={tag} size="small" label={tag} />
                ))}
              </Stack>
            </Box>
          )}

          {parameters && (
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                Parameters
              </Typography>
              <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, backgroundColor: '#0f172a' }}>
                <Typography
                  component="pre"
                  sx={{
                    fontFamily: 'monospace',
                    fontSize: 12,
                    color: '#e2e8f0',
                    whiteSpace: 'pre-wrap',
                    m: 0,
                  }}
                >
                  {parameters}
                </Typography>
              </Paper>
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// DEFAULT PROMPT
// ═══════════════════════════════════════════════════════════════════════════════

const DEFAULT_PROMPT = `You are {{ agent_name | default('Assistant') }}, a helpful AI assistant for {{ institution_name | default('our organization') }}.

## Your Role
Assist users with their inquiries in a friendly, professional manner.
{% if caller_name %}
The caller's name is {{ caller_name }}.
{% endif %}

## Guidelines
- Be concise and helpful in your responses
- Ask clarifying questions when the request is ambiguous
- Use the available tools when appropriate to help the user
- If you cannot help with something, acknowledge it honestly

## Available Tools
You have access to the following tools:
{% for tool in tools %}
- {{ tool }}
{% endfor %}
`;

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function AgentBuilderContent({
  sessionId,
  sessionProfile = null,
  onAgentCreated,
  onAgentUpdated,
  existingConfig = null,
  editMode = false,
}) {
  // Tab state
  const [activeTab, setActiveTab] = useState(0);
  const [isEditMode, setIsEditMode] = useState(editMode);
  
  // Loading states
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  
  // Available options from backend
  const [availableTools, setAvailableTools] = useState([]);
  const [availableVoices, setAvailableVoices] = useState([]);
  const [availableTemplates, setAvailableTemplates] = useState([]);
  const [detailAgent, setDetailAgent] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedTool, setSelectedTool] = useState(null);
  const [showExportInstructions, setShowExportInstructions] = useState(false);
  const [exportedYaml, setExportedYaml] = useState('');

  // Agent configuration state
  const [config, setConfig] = useState({
    name: 'Custom Agent',
    description: '',
    greeting: '',
    return_greeting: '',
    handoff_trigger: '',
    prompt: DEFAULT_PROMPT,
    tools: [],
    cascade_model: {
      deployment_id: 'gpt-4o',
      endpoint_preference: 'auto',
      api_version: 'v1',
      temperature: 0.7,
      top_p: 0.9,
      max_tokens: 4096,
      verbosity: 0,
      min_p: null,
      typical_p: null,
      reasoning_effort: null,
      include_reasoning: false,
    },
    voicelive_model: {
      deployment_id: 'gpt-realtime',
      endpoint_preference: 'auto',
      temperature: 0.7,
      top_p: 0.9,
      max_tokens: 4096,
      verbosity: 0,
      min_p: null,
      typical_p: null,
      reasoning_effort: null,
      include_reasoning: false,
    },
    voice: {
      name: 'en-US-AvaMultilingualNeural',
      type: 'azure-standard',
      style: 'chat',
      rate: '+0%',
      pitch: '+0%',
      endpoint_id: '',
    },
    speech: {
      vad_silence_timeout_ms: 800,
      use_semantic_segmentation: false,
      candidate_languages: ['en-US'],
    },
    session: {
      modalities: ['TEXT', 'AUDIO'],
      input_audio_format: 'PCM16',
      output_audio_format: 'PCM16',
      turn_detection_type: 'azure_semantic_vad',
      turn_detection_threshold: 0.5,
      silence_duration_ms: 700,
      prefix_padding_ms: 240,
      tool_choice: 'auto',
      input_audio_transcription_settings: {
        model: 'azure-speech',
        language: 'en-US',
      },
    },
    template_vars: {
      institution_name: 'Contoso Financial',
      agent_name: 'Assistant',
    },
  });
  const [draftGreeting, setDraftGreeting] = useState('');
  const [draftReturnGreeting, setDraftReturnGreeting] = useState('');
  const [draftPrompt, setDraftPrompt] = useState(DEFAULT_PROMPT);

  // Explicit custom mode tracking - prevents input reset when typing hyphens
  // that might temporarily match a preset name (e.g., typing "my-gpt-4o-test" matches "gpt-4o")
  const [isCascadeCustomMode, setIsCascadeCustomMode] = useState(false);
  const [isVoiceliveCustomMode, setIsVoiceliveCustomMode] = useState(false);
  const customModeInitialized = useRef(false);

  const cascadeEndpointPreference = useMemo(
    () => resolveEndpointPreference(config.cascade_model),
    [config.cascade_model],
  );
  const voiceliveEndpointPreference = useMemo(
    () => resolveEndpointPreference(config.voicelive_model),
    [config.voicelive_model],
  );
  // Compute preset values for dropdown display
  const cascadeModelPreset = useMemo(() => {
    if (isCascadeCustomMode) return 'custom';
    const deploymentId = (config.cascade_model?.deployment_id || '').trim();
    return CASCADE_MODEL_PRESETS.some((preset) => preset.id === deploymentId)
      ? deploymentId
      : 'custom';
  }, [config.cascade_model?.deployment_id, isCascadeCustomMode]);
  const voiceliveModelPreset = useMemo(() => {
    if (isVoiceliveCustomMode) return 'custom';
    const deploymentId = (config.voicelive_model?.deployment_id || '').trim();
    return VOICELIVE_MODEL_PRESETS.some((preset) => preset.id === deploymentId)
      ? deploymentId
      : 'custom';
  }, [config.voicelive_model?.deployment_id, isVoiceliveCustomMode]);
  const isCascadeCustom = isCascadeCustomMode || cascadeModelPreset === 'custom';
  const isVoiceliveCustom = isVoiceliveCustomMode || voiceliveModelPreset === 'custom';

  // Initialize custom mode flags based on loaded config (only once)
  useEffect(() => {
    if (customModeInitialized.current) return;
    const cascadeId = (config.cascade_model?.deployment_id || '').trim();
    const voiceliveId = (config.voicelive_model?.deployment_id || '').trim();
    const cascadeIsCustom = cascadeId && !CASCADE_MODEL_PRESETS.some(p => p.id === cascadeId);
    const voiceliveIsCustom = voiceliveId && !VOICELIVE_MODEL_PRESETS.some(p => p.id === voiceliveId);
    if (cascadeIsCustom) setIsCascadeCustomMode(true);
    if (voiceliveIsCustom) setIsVoiceliveCustomMode(true);
    customModeInitialized.current = true;
  }, [config.cascade_model?.deployment_id, config.voicelive_model?.deployment_id]);
  const cascadeOverrideValue = (config.cascade_model?.deployment_id || '').trim();
  const voiceliveOverrideValue = (config.voicelive_model?.deployment_id || '').trim();
  const isCascadeOverrideMissing = isCascadeCustom && !cascadeOverrideValue;
  const isVoiceliveOverrideMissing = isVoiceliveCustom && !voiceliveOverrideValue;
  const cascadeApiVersionValue = useMemo(
    () => (config.cascade_model?.api_version || 'v1').trim(),
    [config.cascade_model?.api_version],
  );

  // Tool categories
  const [expandedCategories, setExpandedCategories] = useState({});
  const [toolFilter, setToolFilter] = useState('all');
  // All templates displayed uniformly - no session vs built-in distinction
  const allTemplates = useMemo(
    () => availableTemplates || [],
    [availableTemplates],
  );

  // ─────────────────────────────────────────────────────────────────────────
  // DATA FETCHING
  // ─────────────────────────────────────────────────────────────────────────

  const fetchAvailableTools = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/agent-builder/tools`);
      if (response.ok) {
        const data = await response.json();
        setAvailableTools(data.tools || []);
      }
    } catch (err) {
      logger.error('Failed to fetch tools:', err);
    }
  }, []);

  const fetchAvailableVoices = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/agent-builder/voices`);
      if (response.ok) {
        const data = await response.json();
        setAvailableVoices(data.voices || []);
      }
    } catch (err) {
      logger.error('Failed to fetch voices:', err);
    }
  }, []);

  const fetchAvailableTemplates = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/agent-builder/templates`);
      if (response.ok) {
        const data = await response.json();
        setAvailableTemplates(data.templates || []);
      }
    } catch (err) {
      logger.error('Failed to fetch templates:', err);
    }
  }, []);

  const fetchExistingConfig = useCallback(async () => {
    if (!sessionId || !editMode) return;
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/agent-builder/session/${sessionId}`
      );
      if (response.ok) {
        const data = await response.json();
        if (data.config) {
          setConfig((prev) => ({
            ...prev,
            name: data.config.name || prev.name,
            description: data.config.description || '',
            greeting: data.config.greeting || '',
            return_greeting: data.config.return_greeting || '',
            handoff_trigger: data.config.handoff_trigger || '',
            prompt: data.config.prompt_full || data.config.prompt || prev.prompt,
            tools: data.config.tools || [],
            cascade_model: data.config.cascade_model || prev.cascade_model,
            voicelive_model: data.config.voicelive_model || prev.voicelive_model,
            voice: data.config.voice || prev.voice,
            speech: data.config.speech || prev.speech,
            session: {
              ...prev.session,
              ...(data.config.session || {}),
              input_audio_transcription_settings: {
                ...(prev.session?.input_audio_transcription_settings || {}),
                ...(data.config.session?.input_audio_transcription_settings || {}),
              },
            },
          }));
          setIsEditMode(true);
        }
      }
    } catch (err) {
      logger.debug('No existing config for session');
    }
  }, [sessionId, editMode]);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchAvailableTools(),
      fetchAvailableVoices(),
      fetchAvailableTemplates(),
      fetchExistingConfig(),
    ]).finally(() => setLoading(false));
  }, [fetchAvailableTools, fetchAvailableVoices, fetchAvailableTemplates, fetchExistingConfig]);

  // Apply existing config
  useEffect(() => {
    if (existingConfig) {
      setConfig((prev) => ({
        ...prev,
        ...existingConfig,
      }));
    }
  }, [existingConfig]);

  // ─────────────────────────────────────────────────────────────────────────
  // COMPUTED
  // ─────────────────────────────────────────────────────────────────────────

  const toolsByCategory = useMemo(() => {
    const grouped = {};
    availableTools.forEach((tool) => {
      const category = tool.is_handoff ? 'Handoffs' : (tool.tags?.[0] || 'General');
      if (!grouped[category]) grouped[category] = [];
      grouped[category].push(tool);
    });
    return grouped;
  }, [availableTools]);

  const filteredTools = useMemo(() => {
    if (toolFilter === 'all') return availableTools;
    if (toolFilter === 'handoff') return availableTools.filter((t) => t.is_handoff);
    return availableTools.filter((t) => !t.is_handoff);
  }, [availableTools, toolFilter]);

  const greetingVars = useMemo(
    () => extractJinjaVariables(config.greeting),
    [config.greeting],
  );
  const returnGreetingVars = useMemo(
    () => extractJinjaVariables(config.return_greeting),
    [config.return_greeting],
  );
  const promptVars = useMemo(
    () => extractJinjaVariables(config.prompt),
    [config.prompt],
  );
  const usedVars = useMemo(
    () => [...new Set([...greetingVars, ...returnGreetingVars, ...promptVars])],
    [greetingVars, returnGreetingVars, promptVars],
  );

  // Ref for prompt textarea to support variable insertion
  const promptTextareaRef = useRef(null);

  // ─────────────────────────────────────────────────────────────────────────
  // HANDLERS
  // ─────────────────────────────────────────────────────────────────────────

  const handleConfigChange = useCallback((field, value) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleNestedConfigChange = useCallback((parent, field, value) => {
    setConfig((prev) => ({
      ...prev,
      [parent]: { ...prev[parent], [field]: value },
    }));
  }, []);

  const handleSessionTranscriptionChange = useCallback((field, value) => {
    setConfig((prev) => ({
      ...prev,
      session: {
        ...(prev.session || {}),
        input_audio_transcription_settings: {
          ...(prev.session?.input_audio_transcription_settings || {}),
          [field]: value,
        },
      },
    }));
  }, []);

  // Insert variable at cursor position in prompt textarea
  const handleInsertVariable = useCallback((varText) => {
    const textarea = promptTextareaRef.current;
    if (textarea) {
      const start = textarea.selectionStart || 0;
      const end = textarea.selectionEnd || 0;
      const text = draftPrompt;
      const before = text.substring(0, start);
      const after = text.substring(end);
      const newText = before + varText + after;
      setDraftPrompt(newText);
      // Set cursor position after inserted text
      setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(start + varText.length, start + varText.length);
      }, 0);
    } else {
      // Fallback: append to end
      setDraftPrompt((prev) => prev + varText);
    }
  }, [draftPrompt]);

  useEffect(() => {
    setDraftGreeting(config.greeting || '');
  }, [config.greeting]);

  useEffect(() => {
    setDraftReturnGreeting(config.return_greeting || '');
  }, [config.return_greeting]);

  useEffect(() => {
    setDraftPrompt(config.prompt || DEFAULT_PROMPT);
  }, [config.prompt]);

  const isCustomVoice = (config.voice?.type || 'azure-standard') === 'azure-custom';

  const handleToolToggle = useCallback((toolName) => {
    setConfig((prev) => ({
      ...prev,
      tools: prev.tools.includes(toolName)
        ? prev.tools.filter((t) => t !== toolName)
        : [...prev.tools, toolName],
    }));
  }, []);

  const applyTemplateFromCache = useCallback((template) => {
    if (!template) return;
    setConfig((prev) => ({
      ...prev,
      name: template.name || prev.name,
      description: template.description || '',
      greeting: template.greeting || '',
      return_greeting: template.return_greeting || '',
      prompt:
        template.prompt_full ||
        template.prompt ||
        template.prompt_preview ||
        prev.prompt,
      tools: template.tools || [],
      cascade_model: template.cascade_model || prev.cascade_model,
      voicelive_model: template.voicelive_model || prev.voicelive_model,
      voice: template.voice || prev.voice,
    }));
    setSuccess(`Applied agent: ${template.name}`);
    setTimeout(() => setSuccess(null), 3000);
  }, []);

  const handleApplyTemplate = useCallback(async (templateId) => {
    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/agent-builder/templates/${templateId}`
      );
      if (response.ok) {
        const data = await response.json();
        const template = data.template;
        setConfig((prev) => ({
          ...prev,
          name: template.name || prev.name,
          description: template.description || '',
          greeting: template.greeting || '',
          return_greeting: template.return_greeting || '',
          prompt: template.prompt_full || template.prompt || DEFAULT_PROMPT,
          tools: template.tools || [],
          cascade_model: template.cascade_model || prev.cascade_model,
          voicelive_model: template.voicelive_model || prev.voicelive_model,
          voice: template.voice || prev.voice,
        }));
        setSuccess(`Applied template: ${template.name}`);
        setTimeout(() => setSuccess(null), 3000);
      }
    } catch (err) {
      setError('Failed to apply template');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleApplyTemplateCard = useCallback(
    (template) => {
      if (!template) return;
      if (template.is_session_agent || String(template.id || '').startsWith('session:')) {
        applyTemplateFromCache(template);
      } else {
        handleApplyTemplate(template.id);
      }
    },
    [applyTemplateFromCache, handleApplyTemplate],
  );

  const handleViewDetails = useCallback(async (template) => {
    if (!template) return;
    if (template.is_session_agent || String(template.id || '').startsWith('session:')) {
      setDetailAgent(template);
      return;
    }
    if (!template.id) {
      setDetailAgent(template);
      return;
    }
    setDetailAgent(template);
    setDetailLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/agent-builder/templates/${template.id}`
      );
      if (response.ok) {
        const data = await response.json();
        const fullTemplate = data.template || {};
        setDetailAgent({
          ...template,
          ...fullTemplate,
          prompt_full: fullTemplate.prompt || template.prompt_full || template.prompt_preview,
        });
      } else {
        setDetailAgent(template);
      }
    } catch (err) {
      setDetailAgent(template);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleCloseDetails = useCallback(() => {
    setDetailAgent(null);
    setDetailLoading(false);
  }, []);

  const handleOpenToolDetails = useCallback((tool) => {
    setSelectedTool(tool);
  }, []);

  const handleCloseToolDetails = useCallback(() => {
    setSelectedTool(null);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    try {
      const cascadeApiVersion = config.cascade_model?.api_version || 'v1';
      const payload = {
        name: config.name,
        description: config.description,
        greeting: draftGreeting,
        return_greeting: draftReturnGreeting,
        handoff_trigger: config.handoff_trigger,
        prompt: draftPrompt,
        tools: config.tools,
        cascade_model: {
          ...config.cascade_model,
          endpoint_preference: cascadeEndpointPreference,
          api_version: cascadeApiVersion,
        },
        voicelive_model: {
          ...config.voicelive_model,
          endpoint_preference: voiceliveEndpointPreference,
        },
        voice: config.voice,
        speech: config.speech,
        session: config.session,
        template_vars: config.template_vars,
      };

      if (draftGreeting !== config.greeting) {
        handleConfigChange('greeting', draftGreeting);
      }
      if (draftReturnGreeting !== config.return_greeting) {
        handleConfigChange('return_greeting', draftReturnGreeting);
      }
      if (draftPrompt !== config.prompt) {
        handleConfigChange('prompt', draftPrompt);
      }

      const url = isEditMode
        ? `${API_BASE_URL}/api/v1/agent-builder/session/${encodeURIComponent(sessionId)}`
        : `${API_BASE_URL}/api/v1/agent-builder/create?session_id=${encodeURIComponent(sessionId)}`;
      const method = isEditMode ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to save agent');
      }

      const data = await res.json();
      setSuccess(`Agent "${config.name}" ${isEditMode ? 'updated' : 'created'} successfully!`);

      if (!isEditMode) {
        setIsEditMode(true);
      }

      const agentConfig = { ...config, session_id: sessionId, agent_id: data.agent_id };

      if (isEditMode && onAgentUpdated) {
        onAgentUpdated(agentConfig);
      } else if (onAgentCreated) {
        onAgentCreated(agentConfig);
      }
    } catch (err) {
      setError(err.message);
      logger.error('Error saving agent:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/defaults`);
      const { defaults } = await res.json();
      setConfig({
        name: 'Custom Agent',
        description: '',
        greeting: '',
        return_greeting: '',
        handoff_trigger: '',
        prompt: DEFAULT_PROMPT,
        tools: [],
        cascade_model: defaults?.model || config.cascade_model,
        voicelive_model: config.voicelive_model,
        voice: defaults?.voice || config.voice,
        speech: {
          vad_silence_timeout_ms: 800,
          use_semantic_segmentation: false,
          candidate_languages: ['en-US'],
        },
        session: {
          modalities: ['TEXT', 'AUDIO'],
          input_audio_format: 'PCM16',
          output_audio_format: 'PCM16',
          turn_detection_type: 'azure_semantic_vad',
          turn_detection_threshold: 0.5,
          silence_duration_ms: 700,
          prefix_padding_ms: 240,
          tool_choice: 'auto',
          input_audio_transcription_settings:
            defaults?.session?.input_audio_transcription_settings || {
              model: 'azure-speech',
              language: 'en-US',
            },
        },
        template_vars: defaults?.template_vars || config.template_vars,
      });
      setSuccess('Reset to defaults');
    } catch {
      setError('Failed to reset');
    }
  };

  const handleExportAgent = () => {
    const agentName = config.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_');
    const yamlLines = [
      `# ${config.name}`,
      config.description ? `# ${config.description}` : null,
      '',
      `name: ${config.name}`,
      `description: ${config.description || config.name}`,
      '',
      '# Handoff configuration',
      config.handoff_trigger ? `handoff:` : null,
      config.handoff_trigger ? `  trigger: ${config.handoff_trigger}` : null,
      '',
      '# Greetings',
      config.greeting ? `greeting: |` : null,
    ];

    if (config.greeting) {
      config.greeting.split('\n').forEach(line => {
        yamlLines.push(`  ${line}`);
      });
    }

    if (config.return_greeting) {
      yamlLines.push('');
      yamlLines.push('return_greeting: |');
      config.return_greeting.split('\n').forEach(line => {
        yamlLines.push(`  ${line}`);
      });
    }

    yamlLines.push('');
    yamlLines.push('# Voice configuration');
    yamlLines.push('voice:');
    yamlLines.push(`  name: ${config.voice.name}`);
    yamlLines.push(`  type: ${config.voice.type}`);
    if (config.voice.rate) yamlLines.push(`  rate: "${config.voice.rate}"`);
    if (config.voice.pitch) yamlLines.push(`  pitch: "${config.voice.pitch}"`);
    if (config.voice.style) yamlLines.push(`  style: ${config.voice.style}`);

    yamlLines.push('');
    yamlLines.push('# VoiceLive model configuration');
    yamlLines.push('voicelive_model:');
    yamlLines.push(`  deployment_id: ${config.voicelive_model.deployment_id}`);
    yamlLines.push(`  temperature: ${config.voicelive_model.temperature}`);
    yamlLines.push(`  max_tokens: ${config.voicelive_model.max_tokens}`);

    yamlLines.push('');
    yamlLines.push('# Cascade model configuration');
    yamlLines.push('cascade_model:');
    yamlLines.push(`  deployment_id: ${config.cascade_model.deployment_id}`);
    yamlLines.push(`  temperature: ${config.cascade_model.temperature}`);
    yamlLines.push(`  max_tokens: ${config.cascade_model.max_tokens}`);

    yamlLines.push('');
    yamlLines.push('# Session configuration (VoiceLive mode)');
    yamlLines.push('session:');
    yamlLines.push(`  modalities: [${config.session.modalities.join(', ')}]`);
    yamlLines.push(`  input_audio_format: ${config.session.input_audio_format}`);
    yamlLines.push(`  output_audio_format: ${config.session.output_audio_format}`);
    yamlLines.push(`  turn_detection:`);
    yamlLines.push(`    type: ${config.session.turn_detection_type}`);
    yamlLines.push(`    threshold: ${config.session.turn_detection_threshold}`);
    yamlLines.push(`    prefix_padding_ms: ${config.session.prefix_padding_ms}`);
    yamlLines.push(`    silence_duration_ms: ${config.session.silence_duration_ms}`);
    yamlLines.push(`  tool_choice: ${config.session.tool_choice}`);

    yamlLines.push('');
    yamlLines.push('# Tools (referenced by name from shared registry)');
    yamlLines.push('tools:');
    if (config.tools && config.tools.length > 0) {
      config.tools.forEach(tool => {
        yamlLines.push(`  - ${tool}`);
      });
    } else {
      yamlLines.push('  []');
    }

    yamlLines.push('');
    yamlLines.push('# Prompt (file reference or inline)');
    yamlLines.push('prompts:');
    yamlLines.push(`  path: prompt.jinja`);
    yamlLines.push('');
    yamlLines.push('# Note: Create a separate prompt.jinja file with the following content:');
    yamlLines.push('# ---prompt.jinja---');
    yamlLines.push(config.prompt);
    yamlLines.push('# ---end prompt.jinja---');

    const yamlContent = yamlLines.filter(line => line !== null).join('\n');
    setExportedYaml(yamlContent);
    setShowExportInstructions(true);
  };

  const renderAgentCard = (agent) => {
    const toolCount = Array.isArray(agent?.tools) ? agent.tools.length : 0;
    const voiceLabel = getVoiceLabel(agent);
    const cascadeLabel = getCascadeLabel(agent);
    const voiceLiveLabel = getVoiceLiveLabel(agent);

    return (
      <Card
        key={agent?.id || agent?.name}
        variant="outlined"
        sx={{
          minWidth: 260,
          maxWidth: 320,
          flex: '1 1 260px',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: '12px',
          borderColor: '#e5e7eb',
          boxShadow: 'none',
          '&:hover': {
            borderColor: '#6366f1',
            boxShadow: '0 4px 12px rgba(99,102,241,0.1)',
          },
        }}
      >
        <CardContent sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Avatar sx={{ width: 32, height: 32, bgcolor: '#0ea5e9' }}>
              {agent?.name?.[0] || 'A'}
            </Avatar>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600 }} noWrap>
                {agent?.name || 'Agent'}
              </Typography>
            </Box>
            {agent?.is_entry_point && (
              <Chip size="small" color="primary" label="Entry" />
            )}
          </Stack>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              mb: 1.25,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {agent?.description || 'No description provided'}
          </Typography>

          <Box
            sx={{
              mb: 1.5,
              px: 1,
              py: 0.75,
              borderRadius: '10px',
              backgroundColor: '#f8fafc',
              border: '1px solid #e5e7eb',
            }}
          >
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'auto 1fr',
                columnGap: 1,
                rowGap: 0.75,
                alignItems: 'center',
              }}
            >
              <Box
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  px: 0.75,
                  py: 0.25,
                  borderRadius: '999px',
                  backgroundColor: '#eef2ff',
                  color: '#4338ca',
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 0.2,
                }}
              >
                <BuildIcon sx={{ fontSize: 12 }} />
                Tools
              </Box>
              <Typography variant="body2" sx={{ fontWeight: 600, color: '#0f172a' }}>
                {toolCount}
              </Typography>

              <Box
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  px: 0.75,
                  py: 0.25,
                  borderRadius: '999px',
                  backgroundColor: '#eef2ff',
                  color: '#4338ca',
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 0.2,
                }}
              >
                <MemoryIcon sx={{ fontSize: 12 }} />
                Cascade
              </Box>
              <Typography
                variant="body2"
                sx={{ fontWeight: 600, color: '#0f172a', wordBreak: 'break-word' }}
                title={cascadeLabel}
              >
                {cascadeLabel}
              </Typography>

              <Box
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  px: 0.75,
                  py: 0.25,
                  borderRadius: '999px',
                  backgroundColor: '#ecfeff',
                  color: '#0e7490',
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 0.2,
                }}
              >
                <HearingIcon sx={{ fontSize: 12 }} />
                VoiceLive
              </Box>
              <Typography
                variant="body2"
                sx={{ fontWeight: 600, color: '#0f172a', wordBreak: 'break-word' }}
                title={voiceLiveLabel}
              >
                {voiceLiveLabel}
              </Typography>

              <Box
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  px: 0.75,
                  py: 0.25,
                  borderRadius: '999px',
                  backgroundColor: '#f0fdf4',
                  color: '#15803d',
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 0.2,
                }}
              >
                <RecordVoiceOverIcon sx={{ fontSize: 12 }} />
                Voice
              </Box>
              <Typography
                variant="body2"
                sx={{ fontWeight: 600, color: '#0f172a', wordBreak: 'break-word' }}
                title={voiceLabel}
              >
                {voiceLabel}
              </Typography>
            </Box>
          </Box>

          <Stack direction="row" spacing={1} sx={{ mt: 'auto' }}>
            <Button
              size="small"
              variant="text"
              startIcon={<InfoOutlinedIcon />}
              onClick={() => handleViewDetails(agent)}
              sx={{ textTransform: 'none' }}
            >
              Details
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={() => handleApplyTemplateCard(agent)}
              sx={{ textTransform: 'none' }}
            >
              Edit Agent
            </Button>
          </Stack>
        </CardContent>
      </Card>
    );
  };

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Loading */}
      {loading && <LinearProgress />}

      {/* Alerts */}
      <Collapse in={!!error || !!success}>
        <Box sx={{ px: 2, pt: 2 }}>
          {error && (
            <Alert severity="error" onClose={() => setError(null)} sx={{ borderRadius: '12px' }}>
              {error}
            </Alert>
          )}
          {success && (
            <Alert severity="success" onClose={() => setSuccess(null)} sx={{ borderRadius: '12px' }}>
              {success}
            </Alert>
          )}
        </Box>
      </Collapse>

      {/* Edit mode banner */}
      {isEditMode && (
        <Alert
          severity="info"
          icon={<EditIcon />}
          sx={{
            mx: 3,
            mt: 2,
            borderRadius: '12px',
            backgroundColor: '#fef3c7',
            color: '#92400e',
          }}
        >
          <Typography variant="body2">
            <strong>Edit Mode:</strong> Updating existing agent for this session.
          </Typography>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs
        value={activeTab}
        onChange={(e, v) => setActiveTab(v)}
        sx={styles.tabs}
        variant="fullWidth"
      >
        <Tab icon={<SmartToyIcon />} label="Identity" iconPosition="start" />
        <Tab icon={<CodeIcon />} label="Prompt" iconPosition="start" />
        <Tab icon={<BuildIcon />} label="Tools" iconPosition="start" />
        <Tab icon={<RecordVoiceOverIcon />} label="Voice" iconPosition="start" />
        <Tab icon={<TuneIcon />} label="Model" iconPosition="start" />
        <Tab icon={<HearingIcon />} label="VAD/Session" iconPosition="start" />
      </Tabs>

      {/* Content */}
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {/* TAB 0: IDENTITY */}
            <TabPanel value={activeTab} index={0}>
              <Stack spacing={3}>
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                      🤖 Agent Identity
                    </Typography>
                    <Stack spacing={2}>
                      <TextField
                        label="Agent Name"
                        value={config.name}
                        onChange={(e) => handleConfigChange('name', e.target.value)}
                        fullWidth
                        required
                      />
                      <TextField
                        label="Description"
                        value={config.description}
                        onChange={(e) => handleConfigChange('description', e.target.value)}
                        fullWidth
                        multiline
                        rows={2}
                      />
                    </Stack>
                  </CardContent>
                </Card>

                {/* Available Agents */}
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 1, fontWeight: 600 }}>
                      <FolderOpenIcon fontSize="small" sx={{ mr: 1, verticalAlign: 'middle' }} />
                      Available Agents
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                      Select an agent to edit. Changes with the same name will update the existing agent.
                    </Typography>
                    {allTemplates.length > 0 ? (
                      <Stack direction="row" flexWrap="wrap" gap={1.5}>
                        {allTemplates.map(renderAgentCard)}
                      </Stack>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        No agents available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Stack>
            </TabPanel>

            {/* TAB 1: PROMPT */}
            <TabPanel value={activeTab} index={1}>
              {/* Greetings */}
              <Card variant="outlined" sx={{ ...styles.sectionCard, mb: 2 }}>
                <CardContent>
                  <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                    👋 Greetings (Jinja2 templates supported)
                  </Typography>
                  <Stack spacing={2}>
                    <Box>
                      <TextField
                        label="Initial Greeting"
                        value={draftGreeting}
                        onChange={(e) => setDraftGreeting(e.target.value)}
                        onBlur={() => {
                          if (draftGreeting !== config.greeting) {
                            handleConfigChange('greeting', draftGreeting);
                          }
                        }}
                        fullWidth
                        multiline
                        rows={3}
                        placeholder="Hi {{ caller_name | default('there') }}, I'm {{ agent_name }}. How can I help?"
                        sx={styles.promptEditor}
                      />
                      <InlineVariablePicker 
                        onInsert={(text) => setDraftGreeting((prev) => prev + text)} 
                        usedVars={greetingVars}
                      />
                    </Box>
                    <Box>
                      <TextField
                        label="Return Greeting"
                        value={draftReturnGreeting}
                        onChange={(e) => setDraftReturnGreeting(e.target.value)}
                        onBlur={() => {
                          if (draftReturnGreeting !== config.return_greeting) {
                            handleConfigChange('return_greeting', draftReturnGreeting);
                          }
                        }}
                        fullWidth
                        multiline
                        rows={3}
                        placeholder="Welcome back{{ caller_name | default('') | prepend(', ') }}. Is there anything else I can help with?"
                        sx={styles.promptEditor}
                      />
                      <InlineVariablePicker 
                        onInsert={(text) => setDraftReturnGreeting((prev) => prev + text)} 
                        usedVars={returnGreetingVars}
                      />
                    </Box>
                  </Stack>
                </CardContent>
              </Card>

              {/* System Prompt */}
              <Card variant="outlined" sx={styles.sectionCard}>
                <CardContent>
                  <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                    📝 System Prompt
                  </Typography>
                  <TextField
                    inputRef={promptTextareaRef}
                    value={draftPrompt}
                    onChange={(e) => setDraftPrompt(e.target.value)}
                    onBlur={() => {
                      if (draftPrompt !== config.prompt) {
                        handleConfigChange('prompt', draftPrompt);
                      }
                    }}
                    fullWidth
                    multiline
                    rows={18}
                    placeholder="Enter your system prompt with Jinja2 template syntax..."
                    sx={styles.promptEditor}
                  />
                  <InlineVariablePicker 
                    onInsert={handleInsertVariable} 
                    usedVars={promptVars}
                  />
                </CardContent>
              </Card>
            </TabPanel>

            {/* TAB 2: TOOLS */}
            <TabPanel value={activeTab} index={2}>
              <Stack spacing={2}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="subtitle2" color="primary" sx={{ fontWeight: 600 }}>
                    🛠️ Available Tools ({config.tools.length} selected)
                  </Typography>
                  <ToggleButtonGroup
                    value={toolFilter}
                    exclusive
                    onChange={(e, v) => v && setToolFilter(v)}
                    size="small"
                  >
                    <ToggleButton value="all">All</ToggleButton>
                    <ToggleButton value="normal">Tools</ToggleButton>
                    <ToggleButton value="handoff">Handoffs</ToggleButton>
                  </ToggleButtonGroup>
                </Stack>

                {Object.entries(toolsByCategory).map(([category, tools]) => (
                  <Accordion key={category} defaultExpanded>
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Typography variant="subtitle2">{category}</Typography>
                      <Chip
                        size="small"
                        label={`${tools.filter((t) => config.tools.includes(t.name)).length}/${tools.length}`}
                        sx={{ ml: 2 }}
                      />
                    </AccordionSummary>
                    <AccordionDetails>
                      <Stack spacing={1}>
                        {tools.map((tool) => (
                          <FormControlLabel
                            key={tool.name}
                            control={
                              <Checkbox
                                checked={config.tools.includes(tool.name)}
                                onChange={() => handleToolToggle(tool.name)}
                              />
                            }
                            label={
                              <Box
                                sx={{
                                  display: 'flex',
                                  alignItems: 'flex-start',
                                  gap: 1,
                                  width: '100%',
                                  minWidth: 0,
                                }}
                              >
                                <Box sx={{ flex: 1, minWidth: 0 }}>
                                  <Stack
                                    direction="row"
                                    alignItems="center"
                                    spacing={1}
                                    sx={{ flexWrap: 'wrap', minWidth: 0 }}
                                  >
                                    <Typography
                                      variant="body2"
                                      sx={{
                                        fontWeight: 600,
                                        minWidth: 0,
                                        maxWidth: '100%',
                                        overflowWrap: 'anywhere',
                                      }}
                                    >
                                      {tool.name}
                                    </Typography>
                                    {tool.is_handoff && (
                                      <Chip
                                        label="handoff"
                                        size="small"
                                        color="secondary"
                                        sx={{ height: 18, fontSize: 10 }}
                                      />
                                    )}
                                    {(tool.tags || []).slice(0, 2).map((tag) => (
                                      <Chip key={tag} label={tag} size="small" sx={{ height: 18, fontSize: 10 }} />
                                    ))}
                                  </Stack>
                                  <Typography
                                    variant="caption"
                                    color="text.secondary"
                                    sx={{
                                      display: 'block',
                                      mt: 0.25,
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                      whiteSpace: 'nowrap',
                                    }}
                                  >
                                    {tool.description || 'No description available.'}
                                  </Typography>
                                </Box>
                                <Tooltip title="Tool details">
                                  <IconButton
                                    size="small"
                                    sx={{ flexShrink: 0, alignSelf: 'flex-start' }}
                                    onClick={(e) => {
                                      e.preventDefault();
                                      e.stopPropagation();
                                      handleOpenToolDetails(tool);
                                    }}
                                  >
                                    <InfoOutlinedIcon fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                              </Box>
                            }
                            sx={{
                              alignItems: 'flex-start',
                              width: '100%',
                              m: 0,
                              '& .MuiFormControlLabel-label': {
                                flex: 1,
                                minWidth: 0,
                              },
                            }}
                          />
                        ))}
                      </Stack>
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Stack>
            </TabPanel>

            {/* TAB 3: VOICE */}
            <TabPanel value={activeTab} index={3}>
              <Card variant="outlined" sx={styles.sectionCard}>
                <CardContent>
                  <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                    🎙️ Voice Settings
                  </Typography>
                  <Stack spacing={2}>
                    {!isCustomVoice ? (
                      <Autocomplete
                        options={availableVoices}
                        getOptionLabel={(opt) => opt.display_name || opt.name}
                        value={availableVoices.find((v) => v.name === config.voice?.name) || null}
                        onChange={(e, v) => v && handleNestedConfigChange('voice', 'name', v.name)}
                        renderInput={(params) => <TextField {...params} label="Voice" />}
                      />
                    ) : (
                      <TextField
                        label="Custom Voice Name"
                        value={config.voice?.name || ''}
                        onChange={(e) => handleNestedConfigChange('voice', 'name', e.target.value)}
                        fullWidth
                        helperText="Custom voice name from your Azure Speech resource"
                      />
                    )}
                    <Stack direction="row" spacing={2}>
                      <TextField
                        select
                        label="Voice Type"
                        value={config.voice?.type || 'azure-standard'}
                        onChange={(e) => handleNestedConfigChange('voice', 'type', e.target.value)}
                        fullWidth
                        SelectProps={{ native: true }}
                        helperText="Voice output type (TTS)"
                      >
                        <option value="azure-standard">Azure Standard</option>
                        <option value="azure-custom">Azure Custom</option>
                      </TextField>
                      {isCustomVoice && (
                        <TextField
                          label="Custom Endpoint ID"
                          value={config.voice?.endpoint_id || ''}
                          onChange={(e) => handleNestedConfigChange('voice', 'endpoint_id', e.target.value)}
                          fullWidth
                          helperText="Endpoint ID for your custom voice deployment"
                        />
                      )}
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      Voice settings control TTS output. Input transcription for VoiceLive is configured in VAD/Session.
                      {' '}
                      <Box
                        component="a"
                        href="https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-how-to-customize"
                        target="_blank"
                        rel="noreferrer"
                        sx={{ color: 'inherit', textDecoration: 'underline' }}
                      >
                        VoiceLive customization guide
                      </Box>
                    </Typography>
                  <Stack direction="row" spacing={2}>
                    <TextField
                      label="Speaking Rate"
                        value={config.voice?.rate || '+0%'}
                        onChange={(e) => handleNestedConfigChange('voice', 'rate', e.target.value)}
                        fullWidth
                        helperText="e.g., +10%, -5%, +0%"
                      />
                      <TextField
                        label="Pitch"
                        value={config.voice?.pitch || '+0%'}
                        onChange={(e) => handleNestedConfigChange('voice', 'pitch', e.target.value)}
                        fullWidth
                        helperText="e.g., +5%, -10%, +0%"
                      />
                    </Stack>
                    <TextField
                      select
                      label="Voice Style"
                      value={config.voice?.style || 'chat'}
                      onChange={(e) => handleNestedConfigChange('voice', 'style', e.target.value)}
                      fullWidth
                      SelectProps={{ native: true }}
                      helperText="Emotional style of the voice"
                    >
                      <option value="chat">Chat (conversational)</option>
                      <option value="cheerful">Cheerful</option>
                      <option value="empathetic">Empathetic</option>
                      <option value="calm">Calm</option>
                      <option value="professional">Professional</option>
                      <option value="friendly">Friendly</option>
                    </TextField>
                  </Stack>
                </CardContent>
              </Card>
            </TabPanel>

            {/* TAB 4: MODEL */}
            <TabPanel value={activeTab} index={4}>
              <Stack spacing={2}>
                <Alert severity="info" icon={<WarningAmberIcon />} sx={{ borderRadius: '12px' }}>
                  <AlertTitle sx={{ fontWeight: 600 }}>Foundry Deployment Required</AlertTitle>
                  <Typography variant="body2">
                    Model names must match deployments in your connected Foundry/Azure OpenAI resource.
                  </Typography>
                </Alert>

                {/* Cascade Model Configuration */}
                <Accordion defaultExpanded>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Chip label="Cascade Mode" color="primary" size="small" />
                      <Typography variant="subtitle2" fontWeight={600}>
                        STT → LLM → TTS Pipeline
                      </Typography>
                    </Stack>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Stack spacing={3}>
                      <TextField
                        select
                        label="Model (Preset)"
                        value={cascadeModelPreset}
                        onChange={(e) => {
                          const selected = e.target.value;
                          if (selected === 'custom') {
                            setIsCascadeCustomMode(true);
                            // Keep existing value if any, otherwise empty
                            if (!config.cascade_model?.deployment_id || CASCADE_MODEL_PRESETS.some(p => p.id === config.cascade_model?.deployment_id)) {
                              handleNestedConfigChange('cascade_model', 'deployment_id', '');
                            }
                          } else {
                            setIsCascadeCustomMode(false);
                            handleNestedConfigChange('cascade_model', 'deployment_id', selected);
                          }
                        }}
                        fullWidth
                        size="small"
                        helperText="Select a base model (override below if needed)"
                        SelectProps={{ native: true }}
                      >
                        {CASCADE_MODEL_PRESETS.map((preset) => (
                          <option key={preset.id} value={preset.id}>
                            {preset.label}
                          </option>
                        ))}
                        <option value="custom">Custom</option>
                      </TextField>

                      {isCascadeCustom && (
                        <TextField
                          label="Deployment Name (Override)"
                          value={config.cascade_model?.deployment_id || ''}
                          onChange={(e) => handleNestedConfigChange('cascade_model', 'deployment_id', e.target.value)}
                          fullWidth
                          required={isCascadeCustom}
                          error={isCascadeOverrideMissing}
                          helperText={
                            isCascadeOverrideMissing
                              ? 'Required when Custom is selected. Must be deployed to your Foundry/Azure OpenAI resource.'
                              : 'Overrides the preset. Must be deployed to your Foundry/Azure OpenAI resource.'
                          }
                          size="small"
                          sx={{
                            '& .MuiOutlinedInput-root': {
                              backgroundColor: '#fff7ed',
                              '& fieldset': { borderColor: '#fdba74' },
                              '&:hover fieldset': { borderColor: '#fb923c' },
                              '&.Mui-focused fieldset': { borderColor: '#f97316' },
                            },
                          }}
                        />
                      )}

                      <TextField
                        select
                        label="Endpoint"
                        value={config.cascade_model?.endpoint_preference || 'auto'}
                        onChange={(e) => handleNestedConfigChange('cascade_model', 'endpoint_preference', e.target.value)}
                        fullWidth
                        size="small"
                        helperText={
                          config.cascade_model?.endpoint_preference === 'auto'
                            ? `Auto: ${cascadeEndpointPreference === 'responses' ? 'Responses API' : 'Chat Completions'}`
                            : 'API endpoint to use for this model'
                        }
                        SelectProps={{ native: true }}
                      >
                        <option value="auto">Auto (detect from model/parameters)</option>
                        <option value="chat">Chat Completions (/chat/completions)</option>
                        <option value="responses">Responses API (/responses)</option>
                      </TextField>

                      {cascadeEndpointPreference === 'responses' && (
                        <TextField
                          label="Responses API Version"
                          value={cascadeApiVersionValue}
                          fullWidth
                          size="small"
                          disabled
                          helperText="Responses API version is managed by the backend (UI configuration coming soon)."
                        />
                      )}

                      <Divider />

                      {/* Show chat completions parameters (including temperature) */}
                      {cascadeEndpointPreference === 'chat' && (
                        <>
                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Temperature</Typography>
                                <Tooltip title="Controls randomness. Lower = focused, Higher = creative.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.cascade_model?.temperature ?? 0.7} size="small" color="primary" />
                            </Stack>
                            <Slider
                              value={config.cascade_model?.temperature ?? 0.7}
                              onChange={(_e, v) => handleNestedConfigChange('cascade_model', 'temperature', v)}
                              min={0}
                              max={2}
                              step={0.1}
                              marks={[
                                { value: 0, label: 'Focused' },
                                { value: 0.7, label: '0.7' },
                                { value: 1, label: 'Balanced' },
                                { value: 2, label: 'Creative' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Top P (Nucleus Sampling)</Typography>
                                <Tooltip title="Controls diversity via nucleus sampling.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.cascade_model?.top_p ?? 0.9} size="small" color="primary" />
                            </Stack>
                            <Slider
                              value={config.cascade_model?.top_p ?? 0.9}
                              onChange={(_e, v) => handleNestedConfigChange('cascade_model', 'top_p', v)}
                              min={0}
                              max={1}
                              step={0.05}
                              marks={[
                                { value: 0.1, label: '0.1' },
                                { value: 0.5, label: '0.5' },
                                { value: 0.9, label: '0.9' },
                                { value: 1, label: '1.0' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Max Tokens</Typography>
                                <Tooltip title="Maximum tokens in response. Higher = longer responses but more latency.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={`${(config.cascade_model?.max_tokens ?? 4096).toLocaleString()} tokens`} size="small" color="primary" />
                            </Stack>
                            <Slider
                              value={config.cascade_model?.max_tokens ?? 4096}
                              onChange={(_e, v) => handleNestedConfigChange('cascade_model', 'max_tokens', v)}
                              min={256}
                              max={16384}
                              step={256}
                              marks={[
                                { value: 1024, label: '1K' },
                                { value: 4096, label: '4K' },
                                { value: 8192, label: '8K' },
                                { value: 16384, label: '16K' },
                              ]}
                            />
                          </Box>
                        </>
                      )}

                      {/* Show responses API parameters */}
                      {cascadeEndpointPreference === 'responses' && (
                        <>
                          <Alert severity="info" sx={{ borderRadius: '8px' }}>
                            <Typography variant="caption">
                              Responses API parameters (for o-reasoning/GPT-5 models)
                            </Typography>
                          </Alert>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Verbosity Level</Typography>
                                <Tooltip title="0=Minimal (fastest, realtime), 1=Standard, 2=Detailed">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.cascade_model?.verbosity ?? 0} size="small" color="secondary" />
                            </Stack>
                            <Slider
                              value={config.cascade_model?.verbosity ?? 0}
                              onChange={(_e, v) => handleNestedConfigChange('cascade_model', 'verbosity', v)}
                              min={0}
                              max={2}
                              step={1}
                              marks={[
                                { value: 0, label: 'Minimal' },
                                { value: 1, label: 'Standard' },
                                { value: 2, label: 'Detailed' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Min P</Typography>
                                <Tooltip title="Minimum probability threshold for token selection.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.cascade_model?.min_p ?? 'Auto'} size="small" color="secondary" />
                            </Stack>
                            <Slider
                              value={config.cascade_model?.min_p ?? 0}
                              onChange={(_e, v) => {
                                const val = v === 0 ? null : v;
                                handleNestedConfigChange('cascade_model', 'min_p', val);
                              }}
                              min={0}
                              max={0.5}
                              step={0.01}
                              marks={[
                                { value: 0, label: 'Auto' },
                                { value: 0.1, label: '0.1' },
                                { value: 0.2, label: '0.2' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Typical P</Typography>
                                <Tooltip title="Typical sampling parameter for quality control.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.cascade_model?.typical_p ?? 'Auto'} size="small" color="secondary" />
                            </Stack>
                            <Slider
                              value={config.cascade_model?.typical_p ?? 0}
                              onChange={(_e, v) => {
                                const val = v === 0 ? null : v;
                                handleNestedConfigChange('cascade_model', 'typical_p', val);
                              }}
                              min={0}
                              max={1}
                              step={0.05}
                              marks={[
                                { value: 0, label: 'Auto' },
                                { value: 0.5, label: '0.5' },
                                { value: 1, label: '1.0' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Reasoning Effort</Typography>
                                <Tooltip title="Compute effort for o1/o3 reasoning models.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.cascade_model?.reasoning_effort || 'Auto'} size="small" color="secondary" />
                            </Stack>
                            <Select
                              value={config.cascade_model?.reasoning_effort || ''}
                              onChange={(e) => handleNestedConfigChange('cascade_model', 'reasoning_effort', e.target.value || null)}
                              size="small"
                              fullWidth
                              displayEmpty
                            >
                              <MenuItem value="">Auto</MenuItem>
                              <MenuItem value="low">Low</MenuItem>
                              <MenuItem value="medium">Medium</MenuItem>
                              <MenuItem value="high">High</MenuItem>
                            </Select>
                          </Box>

                          <FormControlLabel
                            control={
                              <Checkbox
                                checked={config.cascade_model?.include_reasoning ?? false}
                                onChange={(e) => handleNestedConfigChange('cascade_model', 'include_reasoning', e.target.checked)}
                              />
                            }
                            label={
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2">Include Reasoning Tokens</Typography>
                                <Tooltip title="Include reasoning process in response (o1/o3 models)">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                            }
                          />
                        </>
                      )}
                    </Stack>
                  </AccordionDetails>
                </Accordion>

                {/* VoiceLive Model Configuration */}
                <Accordion defaultExpanded>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Chip label="VoiceLive Mode" color="secondary" size="small" />
                      <Typography variant="subtitle2" fontWeight={600}>
                        Realtime Audio API
                      </Typography>
                    </Stack>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Stack spacing={3}>
                      <TextField
                        select
                        label="Model (Preset)"
                        value={voiceliveModelPreset}
                        onChange={(e) => {
                          const selected = e.target.value;
                          if (selected === 'custom') {
                            setIsVoiceliveCustomMode(true);
                            // Keep existing value if any, otherwise empty
                            if (!config.voicelive_model?.deployment_id || VOICELIVE_MODEL_PRESETS.some(p => p.id === config.voicelive_model?.deployment_id)) {
                              handleNestedConfigChange('voicelive_model', 'deployment_id', '');
                            }
                          } else {
                            setIsVoiceliveCustomMode(false);
                            handleNestedConfigChange('voicelive_model', 'deployment_id', selected);
                          }
                        }}
                        fullWidth
                        size="small"
                        helperText="Select a base model (override below if needed)"
                        SelectProps={{ native: true }}
                      >
                        {VOICELIVE_MODEL_PRESETS.map((preset) => (
                          <option key={preset.id} value={preset.id}>
                            {preset.label}
                          </option>
                        ))}
                        <option value="custom">Custom</option>
                      </TextField>

                      {isVoiceliveCustom && (
                        <TextField
                          label="Deployment Name (Override)"
                          value={config.voicelive_model?.deployment_id || ''}
                          onChange={(e) => handleNestedConfigChange('voicelive_model', 'deployment_id', e.target.value)}
                          fullWidth
                          required={isVoiceliveCustom}
                          error={isVoiceliveOverrideMissing}
                          helperText={
                            isVoiceliveOverrideMissing
                              ? 'Required when Custom is selected. Must be deployed to your Foundry/Azure OpenAI resource.'
                              : 'Overrides the preset. Must be deployed to your Foundry/Azure OpenAI resource.'
                          }
                          size="small"
                          sx={{
                            '& .MuiOutlinedInput-root': {
                              backgroundColor: '#fff7ed',
                              '& fieldset': { borderColor: '#fdba74' },
                              '&:hover fieldset': { borderColor: '#fb923c' },
                              '&.Mui-focused fieldset': { borderColor: '#f97316' },
                            },
                          }}
                        />
                      )}

                      <TextField
                        select
                        label="Endpoint"
                        value={config.voicelive_model?.endpoint_preference || 'auto'}
                        onChange={(e) => handleNestedConfigChange('voicelive_model', 'endpoint_preference', e.target.value)}
                        fullWidth
                        size="small"
                        helperText={
                          config.voicelive_model?.endpoint_preference === 'auto'
                            ? `Auto: ${voiceliveEndpointPreference === 'responses' ? 'Responses API' : 'Chat Completions'}`
                          : 'API endpoint to use for this model'
                        }
                        SelectProps={{ native: true }}
                      >
                        <option value="auto">Auto (detect from model/parameters)</option>
                        <option value="chat">Chat Completions (/chat/completions)</option>
                        <option value="responses">Responses API (/responses)</option>
                      </TextField>

                      <Typography variant="caption" color="text.secondary">
                        VoiceLive models must be deployed to your connected Foundry resource. Foundry agents/BYOM chat
                        completions are not yet wired in this demo.
                      </Typography>

                      <Divider />

                      {/* Chat completions parameters (including temperature) */}
                      {voiceliveEndpointPreference === 'chat' && (
                        <>
                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Temperature</Typography>
                                <Tooltip title="Controls randomness. Lower = focused, Higher = creative.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.voicelive_model?.temperature ?? 0.7} size="small" color="primary" />
                            </Stack>
                            <Slider
                              value={config.voicelive_model?.temperature ?? 0.7}
                              onChange={(_e, v) => handleNestedConfigChange('voicelive_model', 'temperature', v)}
                              min={0}
                              max={2}
                              step={0.1}
                              marks={[
                                { value: 0, label: 'Focused' },
                                { value: 0.7, label: '0.7' },
                                { value: 1, label: 'Balanced' },
                                { value: 2, label: 'Creative' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Top P (Nucleus Sampling)</Typography>
                                <Tooltip title="Controls diversity via nucleus sampling.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.voicelive_model?.top_p ?? 0.9} size="small" color="primary" />
                            </Stack>
                            <Slider
                              value={config.voicelive_model?.top_p ?? 0.9}
                              onChange={(_e, v) => handleNestedConfigChange('voicelive_model', 'top_p', v)}
                              min={0}
                              max={1}
                              step={0.05}
                              marks={[
                                { value: 0.1, label: '0.1' },
                                { value: 0.5, label: '0.5' },
                                { value: 0.9, label: '0.9' },
                                { value: 1, label: '1.0' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Max Tokens</Typography>
                                <Tooltip title="Maximum tokens in response.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={`${(config.voicelive_model?.max_tokens ?? 4096).toLocaleString()} tokens`} size="small" color="primary" />
                            </Stack>
                            <Slider
                              value={config.voicelive_model?.max_tokens ?? 4096}
                              onChange={(_e, v) => handleNestedConfigChange('voicelive_model', 'max_tokens', v)}
                              min={256}
                              max={16384}
                              step={256}
                              marks={[
                                { value: 1024, label: '1K' },
                                { value: 4096, label: '4K' },
                                { value: 8192, label: '8K' },
                                { value: 16384, label: '16K' },
                              ]}
                            />
                          </Box>
                        </>
                      )}

                      {/* Responses API parameters */}
                      {voiceliveEndpointPreference === 'responses' && (
                        <>
                          <Alert severity="info" sx={{ borderRadius: '8px' }}>
                            <Typography variant="caption">
                              Responses API parameters (for o-reasoning/GPT-5 models)
                            </Typography>
                          </Alert>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Verbosity Level</Typography>
                                <Tooltip title="0=Minimal (fastest, realtime), 1=Standard, 2=Detailed">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.voicelive_model?.verbosity ?? 0} size="small" color="secondary" />
                            </Stack>
                            <Slider
                              value={config.voicelive_model?.verbosity ?? 0}
                              onChange={(_e, v) => handleNestedConfigChange('voicelive_model', 'verbosity', v)}
                              min={0}
                              max={2}
                              step={1}
                              marks={[
                                { value: 0, label: 'Minimal' },
                                { value: 1, label: 'Standard' },
                                { value: 2, label: 'Detailed' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Min P</Typography>
                                <Tooltip title="Minimum probability threshold for token selection.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.voicelive_model?.min_p ?? 'Auto'} size="small" color="secondary" />
                            </Stack>
                            <Slider
                              value={config.voicelive_model?.min_p ?? 0}
                              onChange={(_e, v) => {
                                const val = v === 0 ? null : v;
                                handleNestedConfigChange('voicelive_model', 'min_p', val);
                              }}
                              min={0}
                              max={0.5}
                              step={0.01}
                              marks={[
                                { value: 0, label: 'Auto' },
                                { value: 0.1, label: '0.1' },
                                { value: 0.2, label: '0.2' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Typical P</Typography>
                                <Tooltip title="Typical sampling parameter.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.voicelive_model?.typical_p ?? 'Auto'} size="small" color="secondary" />
                            </Stack>
                            <Slider
                              value={config.voicelive_model?.typical_p ?? 0}
                              onChange={(_e, v) => {
                                const val = v === 0 ? null : v;
                                handleNestedConfigChange('voicelive_model', 'typical_p', val);
                              }}
                              min={0}
                              max={1}
                              step={0.05}
                              marks={[
                                { value: 0, label: 'Auto' },
                                { value: 0.5, label: '0.5' },
                                { value: 1, label: '1.0' },
                              ]}
                            />
                          </Box>

                          <Box>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2" fontWeight={500}>Reasoning Effort</Typography>
                                <Tooltip title="Compute effort for o1/o3 models.">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                              <Chip label={config.voicelive_model?.reasoning_effort || 'Auto'} size="small" color="secondary" />
                            </Stack>
                            <Select
                              value={config.voicelive_model?.reasoning_effort || ''}
                              onChange={(e) => handleNestedConfigChange('voicelive_model', 'reasoning_effort', e.target.value || null)}
                              size="small"
                              fullWidth
                              displayEmpty
                            >
                              <MenuItem value="">Auto</MenuItem>
                              <MenuItem value="low">Low</MenuItem>
                              <MenuItem value="medium">Medium</MenuItem>
                              <MenuItem value="high">High</MenuItem>
                            </Select>
                          </Box>

                          <FormControlLabel
                            control={
                              <Checkbox
                                checked={config.voicelive_model?.include_reasoning ?? false}
                                onChange={(e) => handleNestedConfigChange('voicelive_model', 'include_reasoning', e.target.checked)}
                              />
                            }
                            label={
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2">Include Reasoning Tokens</Typography>
                                <Tooltip title="Include reasoning process in response (o1/o3 models)">
                                  <InfoOutlinedIcon fontSize="small" color="action" />
                                </Tooltip>
                              </Stack>
                            }
                          />
                        </>
                      )}
                    </Stack>
                  </AccordionDetails>
                </Accordion>
              </Stack>
            </TabPanel>

            {/* TAB 5: VAD/SESSION SETTINGS */}
            <TabPanel value={activeTab} index={5}>
              <Stack spacing={3}>
                {/* VoiceLive Session Settings */}
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                      🎧 VoiceLive Session Settings
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                      These settings apply when using VoiceLive mode (Realtime API).
                    </Typography>
                    <Stack spacing={2}>
                      <TextField
                        select
                        label="Turn Detection Type"
                        value={config.session?.turn_detection_type || 'azure_semantic_vad'}
                        onChange={(e) => handleNestedConfigChange('session', 'turn_detection_type', e.target.value)}
                        fullWidth
                        SelectProps={{ native: true }}
                        helperText="Voice Activity Detection method"
                      >
                        <option value="azure_semantic_vad">Azure Semantic VAD</option>
                        <option value="server_vad">Server VAD</option>
                        <option value="none">None (manual)</option>
                      </TextField>
                      <Box>
                        <Typography variant="body2" gutterBottom>
                          VAD Threshold: {config.session?.turn_detection_threshold ?? 0.5}
                        </Typography>
                        <Slider
                          value={config.session?.turn_detection_threshold ?? 0.5}
                          onChange={(e, v) => handleNestedConfigChange('session', 'turn_detection_threshold', v)}
                          min={0}
                          max={1}
                          step={0.05}
                          marks={[
                            { value: 0 },
                            { value: 0.5 },
                            { value: 1 },
                          ]}
                          sx={{
                            px: 0,
                          }}
                        />
                        <Box
                          sx={{
                            px: 0,
                            mt: 0.5,
                            display: 'grid',
                            gridTemplateColumns: '1fr auto 1fr',
                            alignItems: 'center',
                            color: 'text.secondary',
                          }}
                        >
                          <Typography variant="caption" sx={{ justifySelf: 'start' }}>
                            Less Sensitive
                          </Typography>
                          <Typography variant="caption" sx={{ justifySelf: 'center' }}>
                            0.5
                          </Typography>
                          <Typography variant="caption" sx={{ justifySelf: 'end' }}>
                            More Sensitive
                          </Typography>
                        </Box>
                      </Box>
                      <Stack direction="row" spacing={2}>
                        <TextField
                          label="Silence Duration (ms)"
                          type="number"
                          value={config.session?.silence_duration_ms ?? 700}
                          onChange={(e) => handleNestedConfigChange('session', 'silence_duration_ms', parseInt(e.target.value))}
                          fullWidth
                          inputProps={{ min: 100, max: 3000, step: 50 }}
                          helperText="Wait time after speech before responding"
                        />
                        <TextField
                          label="Prefix Padding (ms)"
                          type="number"
                          value={config.session?.prefix_padding_ms ?? 240}
                          onChange={(e) => handleNestedConfigChange('session', 'prefix_padding_ms', parseInt(e.target.value))}
                          fullWidth
                          inputProps={{ min: 0, max: 1000, step: 20 }}
                          helperText="Audio buffer before detected speech"
                        />
                      </Stack>
                      <TextField
                        select
                        label="Tool Choice"
                        value={config.session?.tool_choice || 'auto'}
                        onChange={(e) => handleNestedConfigChange('session', 'tool_choice', e.target.value)}
                        fullWidth
                        SelectProps={{ native: true }}
                        helperText="How the model selects tools"
                      >
                        <option value="auto">Auto (model decides)</option>
                        <option value="none">None (no tools)</option>
                        <option value="required">Required (must use tool)</option>
                      </TextField>
                      <Divider />
                      <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                          📝 VoiceLive Input Transcription
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                          Applies to VoiceLive (Realtime). Configure STT model and language for input transcription.
                        </Typography>
                        <Stack direction="row" spacing={2}>
                          <TextField
                            select
                            label="Transcription Model"
                            value={config.session?.input_audio_transcription_settings?.model || 'azure-speech'}
                            onChange={(e) => handleSessionTranscriptionChange('model', e.target.value)}
                            fullWidth
                            SelectProps={{ native: true }}
                          >
                            {TRANSCRIPTION_MODELS.map((model) => (
                              <option key={model.value} value={model.value}>
                                {model.label}
                              </option>
                            ))}
                          </TextField>
                          <TextField
                            select
                            label="Language"
                            value={config.session?.input_audio_transcription_settings?.language || 'en-US'}
                            onChange={(e) => handleSessionTranscriptionChange('language', e.target.value)}
                            fullWidth
                            SelectProps={{ native: true }}
                          >
                            {TRANSCRIPTION_LANGUAGES.map((language) => (
                              <option key={language.value} value={language.value}>
                                {language.label}
                              </option>
                            ))}
                          </TextField>
                        </Stack>
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>

                {/* Cascade Speech Settings */}
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                      🎙️ Cascade Speech Settings
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                      These settings apply when using Cascade mode (STT → LLM → TTS).
                    </Typography>
                    <Stack spacing={2}>
                      <TextField
                        label="VAD Silence Timeout (ms)"
                        type="number"
                        value={config.speech?.vad_silence_timeout_ms ?? 800}
                        onChange={(e) => handleNestedConfigChange('speech', 'vad_silence_timeout_ms', parseInt(e.target.value))}
                        fullWidth
                        inputProps={{ min: 100, max: 5000, step: 50 }}
                        helperText="Silence duration before finalizing recognition"
                      />
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={config.speech?.use_semantic_segmentation ?? false}
                            onChange={(e) => handleNestedConfigChange('speech', 'use_semantic_segmentation', e.target.checked)}
                          />
                        }
                        label="Use Semantic Segmentation"
                      />
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={config.speech?.enable_diarization ?? false}
                            onChange={(e) => handleNestedConfigChange('speech', 'enable_diarization', e.target.checked)}
                          />
                        }
                        label="Enable Speaker Diarization"
                      />
                    </Stack>
                  </CardContent>
                </Card>
              </Stack>
            </TabPanel>
          </>
        )}
      </Box>

      <AgentDetailsDialog
        open={Boolean(detailAgent) || detailLoading}
        onClose={handleCloseDetails}
        agent={detailAgent}
        loading={detailLoading}
      />
      <ToolDetailsDialog
        open={Boolean(selectedTool)}
        onClose={handleCloseToolDetails}
        tool={selectedTool}
      />

      {/* Footer */}
      <Divider />
      <Box sx={{ p: 2, backgroundColor: '#fafbfc', display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
        <Button onClick={handleReset} startIcon={<RefreshIcon />} disabled={saving}>
          Reset
        </Button>
        <Button
          onClick={handleExportAgent}
          startIcon={<DownloadIcon />}
          disabled={!config.name.trim() || config.prompt.length < 10}
          variant="outlined"
        >
          Export YAML
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
          disabled={saving || !config.name.trim() || config.prompt.length < 10}
          sx={{
            background: isEditMode
              ? 'linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)'
              : 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
          }}
        >
          {saving ? 'Saving Agent...' : 'Save Agent'}
        </Button>
      </Box>

      {/* Export Instructions Dialog */}
      <Dialog
        open={showExportInstructions}
        onClose={() => setShowExportInstructions(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <FolderOpenIcon color="primary" />
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Export Agent Configuration
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Follow these steps to persist your agent in the backend code
            </Typography>
          </Box>
          <IconButton onClick={() => setShowExportInstructions(false)}>
            <CloseIcon />
          </IconButton>
        </DialogTitle>

        <DialogContent dividers>
          <Stack spacing={3}>
            {/* Step 1 */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip label="1" size="small" color="primary" />
                Copy the agent YAML configuration
              </Typography>
              <Paper variant="outlined" sx={{ p: 2, backgroundColor: '#f8fafc', position: 'relative' }}>
                <Typography
                  component="pre"
                  variant="body2"
                  sx={{
                    fontFamily: 'monospace',
                    fontSize: 12,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    maxHeight: 300,
                    overflowY: 'auto',
                    m: 0,
                  }}
                >
                  {exportedYaml}
                </Typography>
                <Tooltip title="Copy to clipboard">
                  <IconButton
                    size="small"
                    onClick={() => {
                      navigator.clipboard.writeText(exportedYaml);
                      setSuccess('YAML copied to clipboard!');
                      setTimeout(() => setSuccess(null), 2000);
                    }}
                    sx={{ position: 'absolute', top: 8, right: 8, backgroundColor: 'white' }}
                  >
                    <ContentCopyIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Paper>
            </Box>

            {/* Step 2 */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip label="2" size="small" color="primary" />
                Create the agent directory
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                In your terminal, create the agent directory:
              </Typography>
              <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#1e1e1e', borderRadius: 1 }}>
                <Typography
                  component="code"
                  variant="body2"
                  sx={{ fontFamily: 'monospace', color: '#a5d6ff', fontSize: 13 }}
                >
                  mkdir -p apps/artagent/backend/registries/agentstore/{config.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}
                </Typography>
              </Paper>
            </Box>

            {/* Step 3 */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip label="3" size="small" color="primary" />
                Create agent.yaml and prompt.jinja files
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Create two files in the agent directory:
              </Typography>
              <Stack spacing={1}>
                <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#1e1e1e', borderRadius: 1 }}>
                  <Typography
                    component="code"
                    variant="body2"
                    sx={{ fontFamily: 'monospace', color: '#a5d6ff', fontSize: 13 }}
                  >
                    # 1. agent.yaml (copy YAML above, but exclude the prompt section at the end)<br/>
                    apps/artagent/backend/registries/agentstore/{config.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}/agent.yaml
                  </Typography>
                </Paper>
                <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#1e1e1e', borderRadius: 1 }}>
                  <Typography
                    component="code"
                    variant="body2"
                    sx={{ fontFamily: 'monospace', color: '#a5d6ff', fontSize: 13 }}
                  >
                    # 2. prompt.jinja (copy prompt content from YAML comments)<br/>
                    apps/artagent/backend/registries/agentstore/{config.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}/prompt.jinja
                  </Typography>
                </Paper>
              </Stack>
            </Box>

            {/* Step 4 */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip label="4" size="small" color="primary" />
                Restart the backend
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                The backend will automatically discover the new agent on restart:
              </Typography>
              <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#1e1e1e', borderRadius: 1 }}>
                <Typography
                  component="code"
                  variant="body2"
                  sx={{ fontFamily: 'monospace', color: '#a5d6ff', fontSize: 13 }}
                >
                  # Restart your backend service<br/>
                  # The agent will be available in the agent builder and scenarios
                </Typography>
              </Paper>
            </Box>

            {/* Info Box */}
            <Paper sx={{ p: 2, backgroundColor: '#fef3c7', border: '1px solid #fbbf24' }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: '#92400e', mb: 1 }}>
                ⚠️ Important Notes
              </Typography>
              <Typography variant="body2" color="text.secondary" component="div">
                <ul style={{ margin: '4px 0', paddingLeft: 20 }}>
                  <li>The YAML export includes the prompt as comments. Extract it into a separate <code style={{ backgroundColor: '#fde68a', padding: '2px 4px', borderRadius: 2 }}>prompt.jinja</code> file</li>
                  <li>Agent names should be unique across your agentstore</li>
                  <li>Tools referenced in the YAML must exist in the toolstore registry</li>
                </ul>
              </Typography>
            </Paper>
          </Stack>
        </DialogContent>

        <DialogActions sx={{ p: 2 }}>
          <Button onClick={() => setShowExportInstructions(false)}>
            Close
          </Button>
          <Button
            variant="contained"
            startIcon={<DownloadIcon />}
            onClick={() => {
              const blob = new Blob([exportedYaml], { type: 'text/yaml' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `${config.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}_agent.yaml`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download YAML File
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
