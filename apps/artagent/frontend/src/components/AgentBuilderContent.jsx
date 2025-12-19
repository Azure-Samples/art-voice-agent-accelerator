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
  FormControlLabel,
  IconButton,
  InputAdornment,
  LinearProgress,
  List,
  ListItem,
  ListItemAvatar,
  ListItemIcon,
  ListItemText,
  Radio,
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
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import StarIcon from '@mui/icons-material/Star';
import EditIcon from '@mui/icons-material/Edit';
import HearingIcon from '@mui/icons-material/Hearing';
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
      temperature: 0.7,
      top_p: 0.9,
      max_tokens: 4096,
    },
    voicelive_model: {
      deployment_id: 'gpt-realtime',
      temperature: 0.7,
      top_p: 0.9,
      max_tokens: 4096,
    },
    voice: {
      name: 'en-US-AvaMultilingualNeural',
      type: 'azure-standard',
      style: 'chat',
      rate: '+0%',
      pitch: '+0%',
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
    },
    template_vars: {
      institution_name: 'Contoso Financial',
      agent_name: 'Assistant',
    },
  });

  // Tool categories
  const [expandedCategories, setExpandedCategories] = useState({});
  const [toolFilter, setToolFilter] = useState('all');

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
            session: data.config.session || prev.session,
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

  // Compute used Jinja variables from prompt, greeting, return_greeting
  const usedVars = useMemo(() => {
    const fromGreeting = extractJinjaVariables(config.greeting);
    const fromReturnGreeting = extractJinjaVariables(config.return_greeting);
    const fromPrompt = extractJinjaVariables(config.prompt);
    return [...new Set([...fromGreeting, ...fromReturnGreeting, ...fromPrompt])];
  }, [config.greeting, config.return_greeting, config.prompt]);

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

  // Insert variable at cursor position in prompt textarea
  const handleInsertVariable = useCallback((varText) => {
    const textarea = promptTextareaRef.current;
    if (textarea) {
      const start = textarea.selectionStart || 0;
      const end = textarea.selectionEnd || 0;
      const text = config.prompt;
      const before = text.substring(0, start);
      const after = text.substring(end);
      const newText = before + varText + after;
      handleConfigChange('prompt', newText);
      // Set cursor position after inserted text
      setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(start + varText.length, start + varText.length);
      }, 0);
    } else {
      // Fallback: append to end
      handleConfigChange('prompt', config.prompt + varText);
    }
  }, [config.prompt, handleConfigChange]);

  const handleToolToggle = useCallback((toolName) => {
    setConfig((prev) => ({
      ...prev,
      tools: prev.tools.includes(toolName)
        ? prev.tools.filter((t) => t !== toolName)
        : [...prev.tools, toolName],
    }));
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

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    try {
      const payload = {
        name: config.name,
        description: config.description,
        greeting: config.greeting,
        return_greeting: config.return_greeting,
        handoff_trigger: config.handoff_trigger,
        prompt: config.prompt,
        tools: config.tools,
        cascade_model: config.cascade_model,
        voicelive_model: config.voicelive_model,
        voice: config.voice,
        speech: config.speech,
        session: config.session,
        template_vars: config.template_vars,
      };

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
        },
        template_vars: defaults?.template_vars || config.template_vars,
      });
      setSuccess('Reset to defaults');
    } catch {
      setError('Failed to reset');
    }
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
                      <TextField
                        label="Handoff Trigger"
                        value={config.handoff_trigger}
                        onChange={(e) => handleConfigChange('handoff_trigger', e.target.value)}
                        fullWidth
                        placeholder={`handoff_${config.name.toLowerCase().replace(/\s+/g, '_')}`}
                        helperText="Tool name for routing to this agent (auto-generated if empty)"
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <SwapHorizIcon fontSize="small" color="action" />
                            </InputAdornment>
                          ),
                        }}
                      />
                    </Stack>
                  </CardContent>
                </Card>

                {/* Templates & Existing Agents */}
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 1, fontWeight: 600 }}>
                      <FolderOpenIcon fontSize="small" sx={{ mr: 1, verticalAlign: 'middle' }} />
                      Edit Existing or Create from Template
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                      Select an agent to edit or use as a starting template for a new agent.
                    </Typography>
                    <Stack direction="row" flexWrap="wrap" gap={1}>
                      {availableTemplates.map((t) => (
                        <Chip
                          key={t.id}
                          label={t.name}
                          icon={t.is_session_agent ? <SmartToyIcon fontSize="small" /> : <StarIcon fontSize="small" />}
                          color={t.is_session_agent ? 'secondary' : 'default'}
                          onClick={() => handleApplyTemplate(t.id)}
                          sx={{ cursor: 'pointer' }}
                        />
                      ))}
                      {availableTemplates.length === 0 && (
                        <Typography variant="body2" color="text.secondary">
                          No templates available
                        </Typography>
                      )}
                    </Stack>
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
                        value={config.greeting}
                        onChange={(e) => handleConfigChange('greeting', e.target.value)}
                        fullWidth
                        multiline
                        rows={3}
                        placeholder="Hi {{ caller_name | default('there') }}, I'm {{ agent_name }}. How can I help?"
                        sx={styles.promptEditor}
                      />
                      <InlineVariablePicker 
                        onInsert={(text) => handleConfigChange('greeting', config.greeting + text)} 
                        usedVars={extractJinjaVariables(config.greeting)}
                      />
                    </Box>
                    <Box>
                      <TextField
                        label="Return Greeting"
                        value={config.return_greeting}
                        onChange={(e) => handleConfigChange('return_greeting', e.target.value)}
                        fullWidth
                        multiline
                        rows={3}
                        placeholder="Welcome back{{ caller_name | default('') | prepend(', ') }}. Is there anything else I can help with?"
                        sx={styles.promptEditor}
                      />
                      <InlineVariablePicker 
                        onInsert={(text) => handleConfigChange('return_greeting', config.return_greeting + text)} 
                        usedVars={extractJinjaVariables(config.return_greeting)}
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
                    value={config.prompt}
                    onChange={(e) => handleConfigChange('prompt', e.target.value)}
                    fullWidth
                    multiline
                    rows={18}
                    placeholder="Enter your system prompt with Jinja2 template syntax..."
                    sx={styles.promptEditor}
                  />
                  <InlineVariablePicker 
                    onInsert={handleInsertVariable} 
                    usedVars={extractJinjaVariables(config.prompt)}
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
                              <Stack direction="row" alignItems="center" spacing={1}>
                                <Typography variant="body2">{tool.name}</Typography>
                                {tool.is_handoff && (
                                  <Chip label="handoff" size="small" color="secondary" sx={{ height: 18, fontSize: 10 }} />
                                )}
                              </Stack>
                            }
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
                    <Autocomplete
                      options={availableVoices}
                      getOptionLabel={(opt) => opt.display_name || opt.name}
                      value={availableVoices.find((v) => v.name === config.voice?.name) || null}
                      onChange={(e, v) => v && handleNestedConfigChange('voice', 'name', v.name)}
                      renderInput={(params) => <TextField {...params} label="Voice" />}
                    />
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
              <Stack spacing={3}>
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                      ⚡ Cascade Mode Model (STT → LLM → TTS)
                    </Typography>
                    <TextField
                      label="Deployment ID"
                      value={config.cascade_model?.deployment_id || 'gpt-4o'}
                      onChange={(e) => handleNestedConfigChange('cascade_model', 'deployment_id', e.target.value)}
                      fullWidth
                      helperText="Azure OpenAI deployment name"
                    />
                    <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
                      <TextField
                        label="Temperature"
                        type="number"
                        value={config.cascade_model?.temperature ?? 0.7}
                        onChange={(e) => handleNestedConfigChange('cascade_model', 'temperature', parseFloat(e.target.value))}
                        inputProps={{ min: 0, max: 2, step: 0.1 }}
                        size="small"
                      />
                      <TextField
                        label="Max Tokens"
                        type="number"
                        value={config.cascade_model?.max_tokens ?? 4096}
                        onChange={(e) => handleNestedConfigChange('cascade_model', 'max_tokens', parseInt(e.target.value))}
                        size="small"
                      />
                    </Stack>
                  </CardContent>
                </Card>

                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                      🎤 VoiceLive Mode Model (Realtime API)
                    </Typography>
                    <TextField
                      label="Deployment ID"
                      value={config.voicelive_model?.deployment_id || 'gpt-realtime'}
                      onChange={(e) => handleNestedConfigChange('voicelive_model', 'deployment_id', e.target.value)}
                      fullWidth
                      helperText="Azure OpenAI realtime deployment name"
                    />
                    <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
                      <TextField
                        label="Temperature"
                        type="number"
                        value={config.voicelive_model?.temperature ?? 0.7}
                        onChange={(e) => handleNestedConfigChange('voicelive_model', 'temperature', parseFloat(e.target.value))}
                        inputProps={{ min: 0, max: 2, step: 0.1 }}
                        size="small"
                      />
                      <TextField
                        label="Max Tokens"
                        type="number"
                        value={config.voicelive_model?.max_tokens ?? 4096}
                        onChange={(e) => handleNestedConfigChange('voicelive_model', 'max_tokens', parseInt(e.target.value))}
                        size="small"
                      />
                    </Stack>
                  </CardContent>
                </Card>
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
                            { value: 0, label: '0 (Less Sensitive)' },
                            { value: 0.5, label: '0.5' },
                            { value: 1, label: '1 (More Sensitive)' },
                          ]}
                        />
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

      {/* Footer */}
      <Divider />
      <Box sx={{ p: 2, backgroundColor: '#fafbfc', display: 'flex', gap: 2, justifyContent: 'flex-end' }}>
        <Button onClick={handleReset} startIcon={<RefreshIcon />} disabled={saving}>
          Reset
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
          {saving
            ? isEditMode ? 'Updating...' : 'Creating...'
            : isEditMode ? 'Update Agent' : 'Create Agent'}
        </Button>
      </Box>
    </Box>
  );
}
