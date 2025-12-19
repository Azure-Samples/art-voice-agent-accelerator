/**
 * AgentBuilder Component
 * ======================
 * 
 * A dynamic agent configuration builder that allows users to create
 * custom AI agents at runtime with:
 * - Custom name and description
 * - System prompt configuration with Jinja2 template support
 * - Tool selection from available registry
 * - Voice and model settings
 * 
 * The configured agent is stored per-session and used instead of
 * the default agent when active.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
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
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import CloseIcon from '@mui/icons-material/Close';
import SaveIcon from '@mui/icons-material/Save';
import RefreshIcon from '@mui/icons-material/Refresh';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import BuildIcon from '@mui/icons-material/Build';
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver';
import TuneIcon from '@mui/icons-material/Tune';
import CodeIcon from '@mui/icons-material/Code';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import PersonIcon from '@mui/icons-material/Person';
import BusinessIcon from '@mui/icons-material/Business';
import AccountBalanceIcon from '@mui/icons-material/AccountBalance';
import BadgeIcon from '@mui/icons-material/Badge';
import InsightsIcon from '@mui/icons-material/Insights';
import CheckIcon from '@mui/icons-material/Check';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import MemoryIcon from '@mui/icons-material/Memory';
import SwapHorizIcon from '@mui/icons-material/SwapHoriz';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import StarIcon from '@mui/icons-material/Star';
import EditIcon from '@mui/icons-material/Edit';
import AddIcon from '@mui/icons-material/Add';
import HearingIcon from '@mui/icons-material/Hearing';
import { API_BASE_URL } from '../config/constants.js';
import logger from '../utils/logger.js';

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
// MODEL DEFINITIONS
// ═══════════════════════════════════════════════════════════════════════════════

// Models for Cascade mode (standard chat completion API)
const CASCADE_MODEL_OPTIONS = [
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    description: 'Most capable model for complex tasks',
    tier: 'recommended',
    speed: 'fast',
    capabilities: ['Vision', 'Function Calling', 'JSON Mode'],
    contextWindow: '128K tokens',
  },
  {
    id: 'gpt-4o-mini',
    name: 'GPT-4o Mini',
    description: 'Balanced speed and capability',
    tier: 'standard',
    speed: 'fastest',
    capabilities: ['Function Calling', 'JSON Mode'],
    contextWindow: '128K tokens',
  },
  {
    id: 'gpt-4-turbo',
    name: 'GPT-4 Turbo',
    description: 'Previous generation, still powerful',
    tier: 'standard',
    speed: 'medium',
    capabilities: ['Vision', 'Function Calling', 'JSON Mode'],
    contextWindow: '128K tokens',
  },
  {
    id: 'gpt-4',
    name: 'GPT-4',
    description: 'Original GPT-4 model',
    tier: 'legacy',
    speed: 'slow',
    capabilities: ['Function Calling'],
    contextWindow: '8K tokens',
  },
  {
    id: 'gpt-35-turbo',
    name: 'GPT-3.5 Turbo',
    description: 'Fast and cost-effective for simple tasks',
    tier: 'legacy',
    speed: 'fastest',
    capabilities: ['Function Calling', 'JSON Mode'],
    contextWindow: '16K tokens',
  },
];

// Models for VoiceLive mode (realtime API)
const VOICELIVE_MODEL_OPTIONS = [
  {
    id: 'gpt-realtime',
    name: 'GPT-4o Realtime Preview',
    description: 'Low-latency realtime voice model',
    tier: 'recommended',
    speed: 'fastest',
    capabilities: ['Realtime Audio', 'Function Calling'],
    contextWindow: '128K tokens',
  },
  {
    id: 'gpt-4o-mini-realtime-preview',
    name: 'GPT-4o Mini Realtime Preview',
    description: 'Faster, cost-effective realtime model',
    tier: 'standard',
    speed: 'fastest',
    capabilities: ['Realtime Audio', 'Function Calling'],
    contextWindow: '128K tokens',
  },
];

// Legacy: combined options for backward compatibility
const MODEL_OPTIONS = CASCADE_MODEL_OPTIONS;

// ═══════════════════════════════════════════════════════════════════════════════
// STYLES
// ═══════════════════════════════════════════════════════════════════════════════

const styles = {
  dialog: {
    '& .MuiDialog-paper': {
      maxWidth: '1200px',
      width: '95vw',
      height: '90vh',
      maxHeight: '90vh',
      borderRadius: '16px',
      resize: 'both',
      overflow: 'auto',
    },
  },
  header: {
    background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #3d7ab5 100%)',
    color: 'white',
    padding: '16px 24px',
    borderRadius: '16px 16px 0 0',
  },
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
  modelCard: {
    cursor: 'pointer',
    transition: 'all 0.2s',
    border: '2px solid transparent',
    '&:hover': {
      borderColor: '#6366f1',
      transform: 'translateY(-2px)',
      boxShadow: '0 4px 12px rgba(99, 102, 241, 0.15)',
    },
  },
  modelCardSelected: {
    borderColor: '#6366f1',
    backgroundColor: '#f5f3ff',
  },
  promptEditor: {
    fontFamily: '"Fira Code", "Consolas", monospace',
    fontSize: '13px',
    lineHeight: 1.6,
    '& .MuiInputBase-root': {
      backgroundColor: '#1e1e2e',
      color: '#cdd6f4',
      borderRadius: '8px',
      '& .MuiInputBase-input': {
        color: '#cdd6f4',
      },
    },
    '& .MuiInputBase-input::placeholder': {
      color: 'rgba(255,255,255,0.6)',
    },
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// TAB PANEL COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`agent-builder-tabpanel-${index}`}
      aria-labelledby={`agent-builder-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={styles.tabPanel}>{children}</Box>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEMPLATE VARIABLE HELPER
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
// MODEL SELECTOR COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function ModelSelector({ value, onChange, modelOptions = MODEL_OPTIONS, title = 'Select Model Deployment', showAlert = true }) {
  const getTierColor = (tier) => {
    switch (tier) {
      case 'recommended': return 'success';
      case 'standard': return 'primary';
      case 'legacy': return 'default';
      default: return 'default';
    }
  };

  const getSpeedIcon = (speed) => {
    switch (speed) {
      case 'fastest': return '⚡⚡⚡';
      case 'fast': return '⚡⚡';
      case 'medium': return '⚡';
      case 'slow': return '🐢';
      default: return '⚡';
    }
  };

  return (
    <Stack spacing={2}>
      {showAlert && (
        <Alert severity="info" icon={<WarningAmberIcon />} sx={{ borderRadius: '12px' }}>
          <AlertTitle sx={{ fontWeight: 600 }}>Azure OpenAI Deployment Required</AlertTitle>
          <Typography variant="body2">
            The model deployment name must match a deployment in your Azure OpenAI resource. 
            Ensure the selected model is deployed in your subscription before use.
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            Check your Azure Portal → Azure OpenAI → Deployments to verify available models.
          </Typography>
        </Alert>
      )}

      <Typography variant="subtitle2" sx={{ mt: 1 }}>
        {title}
      </Typography>

      <Stack spacing={1.5}>
        {modelOptions.map((model) => (
          <Card
            key={model.id}
            variant="outlined"
            onClick={() => onChange(model.id)}
            sx={{
              ...styles.modelCard,
              ...(value === model.id ? styles.modelCardSelected : {}),
            }}
          >
            <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Stack direction="row" alignItems="center" spacing={2}>
                  <Radio
                    checked={value === model.id}
                    size="small"
                    sx={{ p: 0 }}
                  />
                  <Box>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Typography variant="subtitle2">{model.name}</Typography>
                      <Chip
                        label={model.tier === 'recommended' ? '✨ Recommended' : model.tier}
                        size="small"
                        color={getTierColor(model.tier)}
                        sx={{ height: 20, fontSize: '11px' }}
                      />
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      {model.description}
                    </Typography>
                  </Box>
                </Stack>
                <Stack direction="row" alignItems="center" spacing={2}>
                  <Tooltip title="Speed">
                    <Typography variant="caption">{getSpeedIcon(model.speed)}</Typography>
                  </Tooltip>
                  <Chip
                    label={model.contextWindow}
                    size="small"
                    variant="outlined"
                    sx={{ height: 20, fontSize: '10px' }}
                  />
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Stack>

      {/* Custom deployment input */}
      <TextField
        label="Custom Deployment Name"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        size="small"
        fullWidth
        helperText="Enter your exact Azure OpenAI deployment name if not listed above"
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <MemoryIcon fontSize="small" color="action" />
            </InputAdornment>
          ),
        }}
      />
    </Stack>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// DEFAULT PROMPT TEMPLATE
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

export default function AgentBuilder({
  open,
  onClose,
  sessionId,
  onAgentCreated,
  onAgentUpdated,
  existingConfig = null,
  editMode = false,
  sessionProfile = null,
}) {
  // Tab state
  const [activeTab, setActiveTab] = useState(0);
  const [effectiveSessionId, setEffectiveSessionId] = useState(sessionId);
  const [editingSessionId, setEditingSessionId] = useState(false);
  const [pendingSessionId, setPendingSessionId] = useState(sessionId || '');
  const [sessionUpdating, setSessionUpdating] = useState(false);
  const [sessionUpdateError, setSessionUpdateError] = useState(null);
  
  // Track if we're editing an existing session agent
  const [isEditMode, setIsEditMode] = useState(editMode);
  
  // Loading states
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [templateVarsExpanded, setTemplateVarsExpanded] = useState(true);
  
  // Available options from backend
  const [availableTools, setAvailableTools] = useState([]);
  const [availableVoices, setAvailableVoices] = useState([]);
  const [availableTemplates, setAvailableTemplates] = useState([]);
  const [sessionAgents, setSessionAgents] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [_defaults, setDefaults] = useState(null);
  const [expandedTemplates, setExpandedTemplates] = useState({});
  
  // Agent configuration state
  const [config, setConfig] = useState({
    name: 'Custom Agent',
    description: '',
    greeting: '',
    return_greeting: '',
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
    model: {
      deployment_id: 'gpt-4o',
      temperature: 0.7,
      top_p: 0.9,
      max_tokens: 4096,
    },
    voice: {
      name: 'en-US-AvaMultilingualNeural',
      type: 'azure-standard',
      style: 'chat',
      rate: '+0%',
    },
    speech: {
      vad_silence_timeout_ms: 800,
      use_semantic_segmentation: false,
      candidate_languages: ['en-US'],
      enable_diarization: false,
      speaker_count_hint: 2,
    },
    template_vars: {
      institution_name: 'Contoso Financial',
      agent_name: 'Assistant',
    },
  });
  
  // Tool categories expanded state
  const [expandedCategories, setExpandedCategories] = useState({});
  
  // Tool filter state: 'all', 'normal', 'handoff'
  const [toolFilter, setToolFilter] = useState('all');

  // Detect template variables from greeting and prompt for convenience defaults
  const greetingVariables = useMemo(
    () => extractJinjaVariables(config.greeting),
    [config.greeting],
  );
  const detectedTemplateVars = useMemo(() => {
    const fromGreeting = extractJinjaVariables(config.greeting);
    const fromReturnGreeting = extractJinjaVariables(config.return_greeting);
    const fromPrompt = extractJinjaVariables(config.prompt);
    const merged = new Set([...fromGreeting, ...fromReturnGreeting, ...fromPrompt]);
    return Array.from(merged);
  }, [config.greeting, config.return_greeting, config.prompt]);

  // Ensure config.template_vars includes any detected variables so users can set defaults
  useEffect(() => {
    setConfig((prev) => {
      const nextTemplateVars = { ...(prev.template_vars || {}) };
      let changed = false;
      detectedTemplateVars.forEach((key) => {
        if (!(key in nextTemplateVars)) {
          nextTemplateVars[key] = '';
          changed = true;
        }
      });
      return changed ? { ...prev, template_vars: nextTemplateVars } : prev;
    });
  }, [detectedTemplateVars]);

  // ─────────────────────────────────────────────────────────────────────────
  // DATA FETCHING
  // ─────────────────────────────────────────────────────────────────────────

  const fetchAvailableTools = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/tools`);
      if (!res.ok) throw new Error('Failed to fetch tools');
      const data = await res.json();
      setAvailableTools(data.tools || []);
      logger.info('Loaded tools:', data.total);
    } catch (err) {
      logger.error('Error fetching tools:', err);
      setError('Failed to load available tools');
    }
  }, []);

  const fetchAvailableVoices = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/voices`);
      if (!res.ok) throw new Error('Failed to fetch voices');
      const data = await res.json();
      setAvailableVoices(data.voices || []);
      logger.info('Loaded voices:', data.total);
    } catch (err) {
      logger.error('Error fetching voices:', err);
      setError('Failed to load available voices');
    }
  }, []);

  const fetchDefaults = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/defaults`);
      if (!res.ok) throw new Error('Failed to fetch defaults');
      const data = await res.json();
      setDefaults(data.defaults);
      if (data.prompt_template && !existingConfig) {
        setConfig(prev => ({ ...prev, prompt: data.prompt_template }));
      }
    } catch (err) {
      logger.error('Error fetching defaults:', err);
    }
  }, [existingConfig]);

  const fetchAvailableTemplates = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/templates`);
      if (!res.ok) throw new Error('Failed to fetch templates');
      const data = await res.json();
      setAvailableTemplates(data.templates || []);
      logger.info('Loaded templates:', data.total);
    } catch (err) {
      logger.error('Error fetching templates:', err);
    }
  }, []);

  const fetchSessionAgents = useCallback(async () => {
    const collected = [];
    try {
      if (effectiveSessionId) {
        // Fetch the live session-scoped agent so it shows up immediately in the template grid
        const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/session/${encodeURIComponent(effectiveSessionId)}`);
        if (res.ok) {
          const data = await res.json();
          if (data?.config) {
            collected.push({
              id: `session-${effectiveSessionId}`,
              name: data.config.name || data.agent_name || 'Session Agent',
              description: data.config.description || '',
              tools: data.config.tools || [],
              greeting: data.config.greeting,
              return_greeting: data.config.return_greeting,
              prompt: data.config.prompt_full || data.config.prompt_preview,
              model: data.config.model,
              voice: data.config.voice,
              template_vars: data.config.template_vars,
              speech: data.config.speech,
              source: 'session',
            });
          }
        }
      }
      setSessionAgents(collected);
    } catch (err) {
      logger.error('Error fetching session agents:', err);
      setSessionAgents(collected);
    }
  }, [effectiveSessionId]);

  // Reload agents from disk and refresh templates
  const [reloadingTemplates, setReloadingTemplates] = useState(false);
  
  const reloadAgentTemplates = useCallback(async () => {
    setReloadingTemplates(true);
    try {
      // First, tell the backend to reload agents from disk
      const reloadRes = await fetch(`${API_BASE_URL}/api/v1/agent-builder/reload-agents`, {
        method: 'POST',
      });
      if (!reloadRes.ok) {
        const errData = await reloadRes.json();
        throw new Error(errData.detail || 'Failed to reload agents');
      }
      
      // Then refresh the templates list
      await fetchAvailableTemplates();
      await fetchSessionAgents();
      setSuccess('Agent templates refreshed successfully');
      logger.info('Agent templates reloaded from disk');
    } catch (err) {
      logger.error('Error reloading agent templates:', err);
      setError(err.message || 'Failed to reload agent templates');
    } finally {
      setReloadingTemplates(false);
    }
  }, [fetchAvailableTemplates, fetchSessionAgents]);

  const fetchExistingConfig = useCallback(async () => {
    if (!effectiveSessionId) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/session/${effectiveSessionId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.config) {
          // Use functional update to avoid dependency on config
          setConfig(prev => ({
            name: data.config.name || 'Custom Agent',
            description: data.config.description || '',
            greeting: data.config.greeting || '',
            return_greeting: data.config.return_greeting || prev.return_greeting || '',
            prompt: data.config.prompt_full || data.config.prompt_preview || DEFAULT_PROMPT,
            tools: data.config.tools || [],
            model: data.config.model || prev.model,
            voice: data.config.voice || prev.voice,
            speech: data.config.speech || prev.speech,
            template_vars: data.config.template_vars || prev.template_vars,
          }));
          // Set edit mode since we have an existing config
          setIsEditMode(true);
          return true; // Signal that config was found
        }
      }
      return false;
    } catch {
      logger.debug('No existing config for session:', effectiveSessionId);
      return false;
    }
  }, [effectiveSessionId]);  // Only depend on sessionId

  useEffect(() => {
    if (open) {
      setLoading(true);
      setError(null);
      setSuccess(null);
      setSelectedTemplate(null);
      // Reset edit mode initially, fetchExistingConfig will set it if config exists
      setIsEditMode(editMode);
      Promise.all([
        fetchAvailableTools(),
        fetchAvailableVoices(),
        fetchAvailableTemplates(),
        fetchSessionAgents(),
        fetchDefaults(),
        fetchExistingConfig(),
      ]).finally(() => setLoading(false));
    }
  }, [open, editMode, fetchAvailableTools, fetchAvailableVoices, fetchAvailableTemplates, fetchSessionAgents, fetchDefaults, fetchExistingConfig]);

  // Apply existing config if provided
  useEffect(() => {
    if (existingConfig) {
      setConfig(prev => ({ ...prev, ...existingConfig }));
    }
  }, [existingConfig]);

  useEffect(() => {
    setEffectiveSessionId(sessionId);
    setPendingSessionId(sessionId || '');
  }, [sessionId]);

  // ─────────────────────────────────────────────────────────────────────────
  // TOOL GROUPING
  // ─────────────────────────────────────────────────────────────────────────

  const toolsByCategory = useMemo(() => {
    const categories = {};
    for (const tool of availableTools) {
      const tags = tool.tags || ['general'];
      for (const tag of tags) {
        if (!categories[tag]) categories[tag] = [];
        if (!categories[tag].find(t => t.name === tool.name)) {
          categories[tag].push(tool);
        }
      }
    }
    return categories;
  }, [availableTools]);

  const handoffTools = useMemo(() => 
    availableTools.filter(t => t.is_handoff),
    [availableTools]
  );

  // ─────────────────────────────────────────────────────────────────────────
  // HANDLERS
  // ─────────────────────────────────────────────────────────────────────────

  const handleTabChange = (_event, newValue) => {
    setActiveTab(newValue);
  };

  const handleConfigChange = useCallback((field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
  }, []);

  const handleNestedConfigChange = (parent, field, value) => {
    setConfig(prev => ({
      ...prev,
      [parent]: { ...prev[parent], [field]: value },
    }));
  };

  const handleToolToggle = useCallback((toolName) => {
    setConfig(prev => {
      const tools = prev.tools.includes(toolName)
        ? prev.tools.filter(t => t !== toolName)
        : [...prev.tools, toolName];
      return { ...prev, tools };
    });
  }, []);

  const toggleCategory = useCallback((category) => {
    setExpandedCategories(prev => ({
      ...prev,
      [category]: !prev[category],
    }));
  }, []);

  const handleSelectAllCategory = (category, categoryTools) => {
    setConfig(prev => {
      const categoryToolNames = categoryTools.map(t => t.name);
      const allSelected = categoryToolNames.every(name => prev.tools.includes(name));
      
      if (allSelected) {
        return { ...prev, tools: prev.tools.filter(t => !categoryToolNames.includes(t)) };
      } else {
        const newTools = [...prev.tools];
        categoryToolNames.forEach(name => {
          if (!newTools.includes(name)) newTools.push(name);
        });
        return { ...prev, tools: newTools };
      }
    });
  };

  const toggleTemplateExpansion = useCallback((templateId) => {
    setExpandedTemplates(prev => ({ ...prev, [templateId]: !prev[templateId] }));
  }, []);

  const handleApplySessionAgent = useCallback((agentCard) => {
    if (!agentCard) return;
    setConfig(prev => ({
      ...prev,
      name: agentCard.name || prev.name,
      description: agentCard.description || prev.description,
      greeting: agentCard.greeting ?? prev.greeting,
      return_greeting: agentCard.return_greeting ?? prev.return_greeting,
      prompt: agentCard.prompt || prev.prompt,
      tools: agentCard.tools || prev.tools,
      voice: agentCard.voice ? { ...prev.voice, ...agentCard.voice } : prev.voice,
      model: agentCard.model ? { ...prev.model, ...agentCard.model } : prev.model,
      speech: agentCard.speech ? { ...prev.speech, ...agentCard.speech } : prev.speech,
      template_vars: agentCard.template_vars ? { ...prev.template_vars, ...agentCard.template_vars } : prev.template_vars,
    }));
    setSelectedTemplate(agentCard.id);
    setSuccess(`Applied session agent: ${agentCard.name || 'Session Agent'}`);
    setTimeout(() => setSuccess(null), 3000);
  }, []);

  const handleApplyTemplate = async (templateId) => {
    if (!templateId) {
      setSelectedTemplate(null);
      return;
    }
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/templates/${templateId}`);
      if (!res.ok) throw new Error('Failed to fetch template details');
      const data = await res.json();
      const template = data.template;
      
      // Apply template to config
      // Build cascade_model and voicelive_model from template's model or use defaults
      const templateModel = template.model || {};
      const cascadeDefaults = { deployment_id: 'gpt-4o', temperature: 0.7, top_p: 0.9, max_tokens: 4096 };
      const voiceliveDefaults = { deployment_id: 'gpt-realtime', temperature: 0.7, top_p: 0.9, max_tokens: 4096 };
      
      setConfig(prev => ({
        ...prev,
        name: template.name || prev.name,
        description: template.description || prev.description,
        greeting: template.greeting || prev.greeting,
        return_greeting: template.return_greeting || prev.return_greeting,
        prompt: template.prompt || prev.prompt,
        tools: template.tools || prev.tools,
        voice: template.voice ? { ...prev.voice, ...template.voice } : prev.voice,
        model: template.model ? { ...prev.model, ...template.model } : prev.model,
        cascade_model: template.cascade_model 
          ? { ...cascadeDefaults, ...template.cascade_model }
          : { ...cascadeDefaults, ...templateModel },
        voicelive_model: template.voicelive_model
          ? { ...voiceliveDefaults, ...template.voicelive_model }
          : voiceliveDefaults,
        speech: template.speech ? { ...prev.speech, ...template.speech } : prev.speech,
        template_vars: template.template_vars ? { ...prev.template_vars, ...template.template_vars } : prev.template_vars,
      }));
      
      setSelectedTemplate(templateId);
      setSuccess(`Applied template: ${template.name}`);
      setTimeout(() => setSuccess(null), 3000);
      
      logger.info('Applied template:', templateId);
    } catch (err) {
      logger.error('Error applying template:', err);
      setError(`Failed to apply template: ${err.message}`);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      // Build payload matching backend DynamicAgentConfig schema
      const payload = {
        name: config.name,
        description: config.description,
        greeting: config.greeting,
        return_greeting: config.return_greeting,
        prompt: config.prompt,  // Backend expects 'prompt', not 'prompt_template'
        tools: config.tools,
        cascade_model: {
          deployment_id: config.cascade_model?.deployment_id || 'gpt-4o',
          temperature: config.cascade_model?.temperature ?? 0.7,
          top_p: config.cascade_model?.top_p ?? 0.9,
          max_tokens: config.cascade_model?.max_tokens ?? 4096,
        },
        voicelive_model: {
          deployment_id: config.voicelive_model?.deployment_id || 'gpt-realtime',
          temperature: config.voicelive_model?.temperature ?? 0.7,
          top_p: config.voicelive_model?.top_p ?? 0.9,
          max_tokens: config.voicelive_model?.max_tokens ?? 4096,
        },
        voice: {
          name: config.voice.name,
          type: config.voice.type,
          style: config.voice.style,
          rate: config.voice.rate,
        },
        speech: {
          vad_silence_timeout_ms: config.speech?.vad_silence_timeout_ms,
          use_semantic_segmentation: config.speech?.use_semantic_segmentation,
          candidate_languages: config.speech?.candidate_languages,
          enable_diarization: config.speech?.enable_diarization,
          speaker_count_hint: config.speech?.speaker_count_hint,
        },
        template_vars: config.template_vars,
      };

      // Use PUT for update, POST for create
      const isUpdate = isEditMode;
      const url = isUpdate
        ? `${API_BASE_URL}/api/v1/agent-builder/session/${encodeURIComponent(effectiveSessionId)}`
        : `${API_BASE_URL}/api/v1/agent-builder/create?session_id=${encodeURIComponent(effectiveSessionId)}`;
      const method = isUpdate ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        let errorMessage = isUpdate ? 'Failed to update agent' : 'Failed to create agent';
        if (errData.detail) {
          if (typeof errData.detail === 'string') {
            errorMessage = errData.detail;
          } else if (Array.isArray(errData.detail)) {
            errorMessage = errData.detail.map(e => `${e.loc?.join('.')}: ${e.msg}`).join(', ');
          } else {
            errorMessage = JSON.stringify(errData.detail);
          }
        }
        throw new Error(errorMessage);
      }

      const data = await res.json();
      const actionVerb = isUpdate ? 'updated' : 'created';
      setSuccess(`Agent "${config.name}" ${actionVerb} successfully! It is now active for this session.`);
      
      // After successful create/update, mark as edit mode for subsequent saves
      if (!isUpdate) {
        setIsEditMode(true);
      }
      
      // Refresh templates to include the newly created/updated agent
      // This triggers a backend reload and fetches the updated template list
      reloadAgentTemplates();
      
      const agentConfig = {
        ...config,
        session_id: effectiveSessionId,
        agent_id: data.agent_id,
      };
      
      if (isUpdate && onAgentUpdated) {
        onAgentUpdated(agentConfig);
      } else if (onAgentCreated) {
        onAgentCreated(agentConfig);
      }
      fetchSessionAgents();
    } catch (err) {
      setError(err.message || 'An unexpected error occurred');
      logger.error('Error saving agent:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/agent-builder/defaults`);
      const { defaults: fetchedDefaults } = await res.json();
      setConfig({
        name: 'Custom Agent',
        description: '',
        greeting: '',
        return_greeting: fetchedDefaults?.return_greeting || '',
        prompt: fetchedDefaults?.prompt_template || DEFAULT_PROMPT,
        tools: [],
        model: fetchedDefaults?.model || config.model,
        voice: fetchedDefaults?.voice || config.voice,
        speech: fetchedDefaults?.speech || config.speech,
        template_vars: fetchedDefaults?.template_vars || config.template_vars,
      });
      setSuccess('Agent configuration reset to defaults');
    } catch {
      setError('Failed to reset configuration');
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  const _voicesByCategory = useMemo(() => {
    const categories = {};
    for (const voice of availableVoices) {
      if (!categories[voice.category]) categories[voice.category] = [];
      categories[voice.category].push(voice);
    }
    return categories;
  }, [availableVoices]);

  const templateVarKeys = useMemo(() => {
    const keys = new Set(Object.keys(config.template_vars || {}));
    detectedTemplateVars.forEach((v) => keys.add(v));
    return Array.from(keys).sort();
  }, [config.template_vars, detectedTemplateVars]);

  const validateSessionId = useCallback(async (id) => {
    if (!id) return false;
    const pattern = /^session_[0-9]{6,}_[A-Za-z0-9]+$/;
    if (!pattern.test(id)) {
      setSessionUpdateError('Session ID must match pattern: session_<timestamp>_<suffix>');
      return false;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/metrics/session/${encodeURIComponent(id)}`);
      if (!res.ok) {
        setSessionUpdateError('Session not found or inactive.');
        return false;
      }
      return true;
    } catch (err) {
      setSessionUpdateError('Session validation failed.');
      return false;
    }
  }, []);

  const handleSessionIdSave = useCallback(async () => {
    const target = (pendingSessionId || '').trim();
    if (!target) {
      setSessionUpdateError('Session ID is required');
      return;
    }
    if (target === effectiveSessionId) {
      setEditingSessionId(false);
      setSessionUpdateError(null);
      return;
    }
    setSessionUpdating(true);
    const isValid = await validateSessionId(target);
    if (isValid) {
      setEffectiveSessionId(target);
      setEditingSessionId(false);
      setSessionUpdateError(null);
      await Promise.all([fetchSessionAgents(), fetchExistingConfig()]);
    } else {
      setPendingSessionId(effectiveSessionId || '');
    }
    setSessionUpdating(false);
  }, [pendingSessionId, effectiveSessionId, fetchExistingConfig, fetchSessionAgents, validateSessionId]);

  const handleSessionIdCancel = useCallback(() => {
    setPendingSessionId(effectiveSessionId || '');
    setSessionUpdateError(null);
    setEditingSessionId(false);
  }, [effectiveSessionId]);

  const templateCards = useMemo(() => {
    const merged = [];
    const seen = new Set();
    (availableTemplates || []).forEach((tmpl) => {
      const key = tmpl.id || tmpl.name;
      if (!key || seen.has(key)) return;
      seen.add(key);
      merged.push({
        ...tmpl,
        source: 'template',
        // Ensure consistent field names
        voiceName: tmpl.voice?.name || tmpl.voice?.voice_name || null,
        modelName: tmpl.model?.model_name || tmpl.model?.name || tmpl.model?.deployment || null,
      });
    });
    (sessionAgents || []).forEach((agent) => {
      const key = agent.id || agent.name || agent.agent_name;
      if (!key || seen.has(key)) return;
      seen.add(key);
      merged.push({
        id: key,
        name: agent.name || agent.agent_name || 'Agent',
        description: agent.description || agent.summary || '',
        greeting: agent.greeting || '',
        tools: agent.tools || agent.tool_names || agent.toolNames || [],
        is_entry_point: agent.is_entry_point || agent.entry_point || false,
        source: 'session',
        voiceName: agent.voice?.name || agent.voice?.voice_name || null,
        modelName: agent.model?.model_name || agent.model?.name || agent.model?.deployment || null,
        is_session_agent: true,
        session_id: agent.session_id || null,
      });
    });
    return merged;
  }, [availableTemplates, sessionAgents]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      sx={styles.dialog}
    >
      {/* Header */}
      <DialogTitle sx={styles.header}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack direction="row" alignItems="center" spacing={2}>
            <Avatar sx={{ bgcolor: 'rgba(255,255,255,0.15)', width: 40, height: 40 }}>
              {isEditMode ? <EditIcon /> : <SmartToyIcon />}
            </Avatar>
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                Agent Builder
              </Typography>
              <Typography variant="caption" sx={{ opacity: 0.8 }}>
                {isEditMode ? 'Editing existing session agent' : 'Create a new custom agent'}
              </Typography>
            </Box>
          </Stack>
          <Stack direction="row" alignItems="center" spacing={2}>
            <Box
              sx={{
                px: 1.5,
                py: 0.75,
                borderRadius: '999px',
                backgroundColor: 'rgba(255,255,255,0.12)',
                border: '1px solid rgba(255,255,255,0.2)',
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                position: 'relative',
                cursor: 'pointer',
              }}
              onClick={() => {
                if (!editingSessionId) {
                  setPendingSessionId(effectiveSessionId || '');
                  setEditingSessionId(true);
                  setSessionUpdateError(null);
                }
              }}
            >
              <Typography variant="caption" sx={{ color: 'white', opacity: 0.8 }}>
                Session
              </Typography>
              <Typography variant="body2" sx={{ color: 'white', fontFamily: 'monospace' }}>
                {effectiveSessionId || 'none'}
              </Typography>
              {editingSessionId && (
                <Box
                  sx={{
                    position: 'absolute',
                    top: 'calc(100% + 8px)',
                    right: 0,
                    backgroundColor: '#0f172a',
                    borderRadius: 1.5,
                    boxShadow: '0 12px 30px rgba(0,0,0,0.25)',
                    p: 1.5,
                    minWidth: 280,
                    zIndex: 10,
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.8)' }}>
                    {'Update session id (session_<timestamp>_<suffix>)'}
                  </Typography>
                  <TextField
                    value={pendingSessionId}
                    onChange={(e) => setPendingSessionId(e.target.value)}
                    size="small"
                    fullWidth
                    sx={{ mt: 1 }}
                    InputProps={{
                      sx: {
                        backgroundColor: '#1e293b',
                        color: 'white',
                        fontFamily: 'monospace',
                      },
                    }}
                    autoFocus
                  />
                  {sessionUpdateError && (
                    <Typography variant="caption" color="error" sx={{ mt: 0.5, display: 'block' }}>
                      {sessionUpdateError}
                    </Typography>
                  )}
                  <Stack direction="row" spacing={1} sx={{ mt: 1, justifyContent: 'flex-end' }}>
                    <Button
                      size="small"
                      onClick={handleSessionIdCancel}
                      disabled={sessionUpdating}
                      sx={{ textTransform: 'none' }}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="small"
                      variant="contained"
                      onClick={handleSessionIdSave}
                      disabled={sessionUpdating}
                      sx={{ textTransform: 'none' }}
                    >
                      {sessionUpdating ? 'Saving...' : 'Save'}
                    </Button>
                  </Stack>
                </Box>
              )}
            </Box>
            <IconButton onClick={onClose} sx={{ color: 'white' }}>
              <CloseIcon />
            </IconButton>
          </Stack>
        </Stack>
      </DialogTitle>

      {/* Loading bar */}
      {loading && <LinearProgress />}

      {/* Alerts */}
      <Collapse in={!!error || !!success}>
        <Box sx={{ px: 2, pt: 2 }}>
          {error && (
            <Alert severity="error" onClose={() => setError(null)} sx={{ borderRadius: '12px' }}>
              <AlertTitle>Error</AlertTitle>
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

      {/* Mode-specific info banner */}
      {!loading && isEditMode && (
        <Alert 
          severity="info" 
          icon={<EditIcon />}
          sx={{ 
            mx: 3, 
            mt: 2, 
            borderRadius: '12px',
            backgroundColor: '#fef3c7',
            color: '#92400e',
            '& .MuiAlert-icon': { color: '#f59e0b' },
          }}
        >
          <Typography variant="body2">
            <strong>Edit Mode:</strong> You're updating the existing agent for this session. Changes will take effect immediately.
          </Typography>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onChange={handleTabChange} sx={styles.tabs} variant="fullWidth">
        <Tab icon={<SmartToyIcon />} label="Identity" iconPosition="start" />
        <Tab icon={<CodeIcon />} label="Prompt" iconPosition="start" />
        <Tab icon={<BuildIcon />} label="Tools" iconPosition="start" />
        <Tab icon={<RecordVoiceOverIcon />} label="Voice" iconPosition="start" />
        <Tab icon={<HearingIcon />} label="Speech" iconPosition="start" />
        <Tab icon={<TuneIcon />} label="Model" iconPosition="start" />
      </Tabs>

      <DialogContent sx={{ padding: 0 }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
            <Stack alignItems="center" spacing={2}>
              <CircularProgress />
              <Typography color="text.secondary">Loading configuration...</Typography>
            </Stack>
          </Box>
        ) : (
          <>
            {/* ═══════════════════════════════════════════════════════════════════ */}
            {/* TAB 0: IDENTITY */}
            {/* ═══════════════════════════════════════════════════════════════════ */}
            <TabPanel value={activeTab} index={0}>
              <Stack spacing={3}>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
                  <Card variant="outlined" sx={{ ...styles.sectionCard, flex: 1 }}>
                    <CardContent>
                      <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                        🟢 Active Session Agent
                      </Typography>
                      <Stack direction="row" alignItems="center" spacing={2}>
                        <Avatar sx={{ bgcolor: '#e0f2fe', color: '#0284c7', width: 40, height: 40 }}>
                          <SmartToyIcon fontSize="small" />
                        </Avatar>
                        <Box sx={{ flex: 1 }}>
                          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                            {config.name || 'Untitled Agent'}
                          </Typography>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                            {config.description || 'No description provided.'}
                          </Typography>
                          <Stack direction="row" spacing={1} flexWrap="wrap">
                            <Chip size="small" label={`${config.tools?.length || 0} tools`} />
                            {config.model?.deployment_id && (
                              <Chip size="small" label={`Model: ${config.model.deployment_id}`} />
                            )}
                          </Stack>
                        </Box>
                      </Stack>
                    </CardContent>
                  </Card>

                  <Card variant="outlined" sx={{ ...styles.sectionCard, flex: 1 }}>
                    <CardContent>
                      <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                        🤖 Agent Identity
                      </Typography>
                      <Stack spacing={2.5}>
                        <TextField
                          label="Agent Name"
                          value={config.name}
                          onChange={(e) => handleConfigChange('name', e.target.value)}
                          fullWidth
                          required
                          helperText="A friendly name for your agent (e.g., 'Banking Concierge', 'Tech Support Bot')"
                          InputProps={{
                            startAdornment: (
                              <InputAdornment position="start">
                                <SmartToyIcon color="action" />
                              </InputAdornment>
                            ),
                          }}
                        />
                        <TextField
                          label="Description"
                          value={config.description}
                          onChange={(e) => handleConfigChange('description', e.target.value)}
                          fullWidth
                          multiline
                          rows={2}
                          helperText="Brief description of what this agent does and its purpose"
                        />
                      </Stack>
                    </CardContent>
                  </Card>
                </Stack>

                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" color="primary" sx={{ fontWeight: 600 }}>
                        📂 Start from Template
                      </Typography>
                      <Stack direction="row" alignItems="center" spacing={1}>
                        {selectedTemplate && (
                          <Chip
                            icon={<CheckIcon />}
                            label="Template applied"
                            color="success"
                            size="small"
                            onDelete={() => setSelectedTemplate(null)}
                          />
                        )}
                        <Tooltip title="Refresh agent templates from disk">
                          <IconButton
                            size="small"
                            onClick={reloadAgentTemplates}
                            disabled={reloadingTemplates}
                            sx={{
                              color: 'primary.main',
                              '&:hover': { backgroundColor: 'rgba(99, 102, 241, 0.1)' },
                            }}
                          >
                            {reloadingTemplates ? (
                              <CircularProgress size={18} />
                            ) : (
                              <RefreshIcon fontSize="small" />
                            )}
                          </IconButton>
                        </Tooltip>
                      </Stack>
                    </Stack>
                    <Stack direction="row" flexWrap="wrap" gap={1.5}>
                      {templateCards.map((tmpl) => (
                        <Card
                          key={tmpl.id}
                          variant="outlined"
                          sx={{
                            minWidth: 280,
                            maxWidth: 320,
                            flex: '1 1 280px',
                            display: 'flex',
                            flexDirection: 'column',
                            height: expandedTemplates[tmpl.id] ? 'auto' : 380,
                            borderColor: tmpl.id === selectedTemplate ? '#6366f1' : '#e5e7eb',
                            boxShadow: tmpl.id === selectedTemplate ? '0 6px 18px rgba(99,102,241,0.15)' : 'none',
                            transition: 'all 0.2s ease',
                            '&:hover': {
                              borderColor: '#6366f1',
                              boxShadow: '0 4px 12px rgba(99,102,241,0.1)',
                            },
                          }}
                        >
                          <CardContent sx={{ pb: '12px !important', display: 'flex', flexDirection: 'column', height: '100%' }}>
                            {/* Header with avatar and name */}
                            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                              <Avatar sx={{ width: 32, height: 32, bgcolor: tmpl.is_entry_point ? '#4338ca' : '#eef2ff', color: tmpl.is_entry_point ? 'white' : '#4338ca' }}>
                                {tmpl.is_entry_point ? <StarIcon fontSize="small" /> : (tmpl.name?.[0] || 'A')}
                              </Avatar>
                              <Box sx={{ flex: 1, minWidth: 0 }}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.2 }} noWrap>
                                  {tmpl.name}
                                </Typography>
                                {tmpl.source === 'session' && (
                                  <Typography variant="caption" sx={{ color: '#6366f1', fontWeight: 500 }}>
                                    Session Agent
                                  </Typography>
                                )}
                              </Box>
                              {tmpl.is_entry_point && (
                                <Chip size="small" color="primary" label="Entry" sx={{ height: 20, fontSize: '0.7rem' }} />
                              )}
                            </Stack>

                            {/* Description */}
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              sx={{
                                mb: 1.5,
                                minHeight: 40,
                                fontSize: '0.8rem',
                                lineHeight: 1.4,
                                ...(expandedTemplates[tmpl.id]
                                  ? {}
                                  : {
                                      display: '-webkit-box',
                                      WebkitLineClamp: 2,
                                      WebkitBoxOrient: 'vertical',
                                      overflow: 'hidden',
                                    }),
                              }}
                            >
                              {tmpl.description || 'No description provided.'}
                            </Typography>
                            {(tmpl.description || '').length > 100 && (
                              <Button
                                size="small"
                                variant="text"
                                onClick={() => toggleTemplateExpansion(tmpl.id)}
                                sx={{ alignSelf: 'flex-start', textTransform: 'none', py: 0, mb: 1, fontSize: '0.75rem' }}
                              >
                                {expandedTemplates[tmpl.id] ? 'Show less' : 'Show more'}
                              </Button>
                            )}

                            <Divider sx={{ my: 1 }} />

                            {/* Tools Section */}
                            <Box sx={{ mb: 1.5 }}>
                              <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
                                <BuildIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
                                <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                                  Tools ({tmpl.tools?.length || 0})
                                </Typography>
                              </Stack>
                              <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ gap: 0.5 }}>
                                {(tmpl.tools || []).slice(0, 4).map((tool, idx) => (
                                  <Chip
                                    key={idx}
                                    size="small"
                                    label={typeof tool === 'string' ? tool.replace(/_/g, ' ') : tool.name || tool}
                                    sx={{
                                      height: 22,
                                      fontSize: '0.65rem',
                                      backgroundColor: '#f1f5f9',
                                      '& .MuiChip-label': { px: 1 },
                                    }}
                                  />
                                ))}
                                {(tmpl.tools?.length || 0) > 4 && (
                                  <Chip
                                    size="small"
                                    label={`+${tmpl.tools.length - 4} more`}
                                    sx={{
                                      height: 22,
                                      fontSize: '0.65rem',
                                      backgroundColor: '#e0e7ff',
                                      color: '#4338ca',
                                      '& .MuiChip-label': { px: 1 },
                                    }}
                                  />
                                )}
                                {(!tmpl.tools || tmpl.tools.length === 0) && (
                                  <Typography variant="caption" color="text.disabled" sx={{ fontStyle: 'italic' }}>
                                    No tools configured
                                  </Typography>
                                )}
                              </Stack>
                            </Box>

                            {/* Voice & Model Info */}
                            <Stack direction="row" spacing={2} sx={{ mb: 1.5 }}>
                              <Box sx={{ flex: 1 }}>
                                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.25 }}>
                                  <RecordVoiceOverIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
                                  <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                                    Voice
                                  </Typography>
                                </Stack>
                                <Typography variant="caption" sx={{ color: tmpl.voiceName ? 'text.primary' : 'text.disabled' }}>
                                  {tmpl.voiceName || 'Default'}
                                </Typography>
                              </Box>
                              <Box sx={{ flex: 1 }}>
                                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.25 }}>
                                  <MemoryIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
                                  <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                                    Model
                                  </Typography>
                                </Stack>
                                <Typography variant="caption" sx={{ color: tmpl.modelName ? 'text.primary' : 'text.disabled' }} noWrap>
                                  {tmpl.modelName || 'Default'}
                                </Typography>
                              </Box>
                            </Stack>

                            {/* Greeting preview if available */}
                            {tmpl.greeting && (
                              <Box sx={{ mb: 1.5, p: 1, backgroundColor: '#f8fafc', borderRadius: 1, border: '1px solid #e2e8f0' }}>
                                <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary', display: 'block', mb: 0.25 }}>
                                  Greeting
                                </Typography>
                                <Typography
                                  variant="caption"
                                  sx={{
                                    color: 'text.secondary',
                                    fontStyle: 'italic',
                                    display: '-webkit-box',
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: 'vertical',
                                    overflow: 'hidden',
                                  }}
                                >
                                  "{tmpl.greeting}"
                                </Typography>
                              </Box>
                            )}

                            {/* Action button */}
                            <Button
                              size="small"
                              fullWidth
                              variant={selectedTemplate === tmpl.id ? 'contained' : 'outlined'}
                              onClick={() => {
                                if (tmpl.source === 'session') {
                                  handleApplySessionAgent(tmpl);
                                } else {
                                  handleApplyTemplate(tmpl.id);
                                }
                              }}
                              sx={{ mt: 'auto' }}
                            >
                              {tmpl.source === 'session' ? 'Edit Agent' : 'Use Template'}
                            </Button>
                          </CardContent>
                        </Card>
                      ))}
                    </Stack>
                  </CardContent>
                </Card>

              </Stack>
            </TabPanel>

            {/* ═══════════════════════════════════════════════════════════════════ */}
            {/* TAB 1: PROMPT */}
            {/* ═══════════════════════════════════════════════════════════════════ */}
            <TabPanel value={activeTab} index={1}>
              <Stack spacing={2}>
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Stack spacing={2.5}>
                      <Box>
                        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
                          <Typography variant="subtitle2" color="primary" sx={{ fontWeight: 600 }}>
                            👋 Greeting Message (Optional)
                          </Typography>
                        </Stack>
                        <TextField
                          value={config.greeting}
                          onChange={(e) => handleConfigChange('greeting', e.target.value)}
                          fullWidth
                          multiline
                          rows={4}
                          placeholder="Hi {{ caller_name | default('there') }}, I'm {{ agent_name }}. How can I help you today?"
                          helperText="Optional: initial message when conversation starts. Use template variables for personalization."
                          sx={styles.promptEditor}
                          InputLabelProps={{
                            shrink: true,
                            sx: {
                              color: '#cdd6f4',
                              backgroundColor: '#1e1e2e',
                              px: 0.5,
                              borderRadius: 0.75,
                              '&.Mui-focused': { color: '#cdd6f4' },
                            },
                          }}
                        />
                        <TemplateVariableHelper
                          usedVars={detectedTemplateVars}
                          onInsert={(val) =>
                            setConfig(prev => ({ ...prev, greeting: (prev.greeting || '') + val }))
                          }
                        />
                      </Box>

                      <Box>
                        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
                          <Typography variant="subtitle2" color="primary" sx={{ fontWeight: 600 }}>
                            🔁 Return Greeting (Optional)
                          </Typography>
                        </Stack>
                        <TextField
                          value={config.return_greeting || ''}
                          onChange={(e) => handleConfigChange('return_greeting', e.target.value)}
                          fullWidth
                          multiline
                          rows={3}
                          placeholder="Welcome back {{ caller_name | default('friend') }}. Picking up where we left off."
                          helperText="Optional: message when the caller returns. Leave blank to use default behavior."
                          sx={styles.promptEditor}
                          InputLabelProps={{
                            shrink: true,
                            sx: {
                              color: '#cdd6f4',
                              backgroundColor: '#1e1e2e',
                              px: 0.5,
                              borderRadius: 0.75,
                              '&.Mui-focused': { color: '#cdd6f4' },
                            },
                          }}
                        />
                        <TemplateVariableHelper
                          usedVars={detectedTemplateVars}
                          onInsert={(val) =>
                            setConfig(prev => ({ ...prev, return_greeting: (prev.return_greeting || '') + val }))
                          }
                        />
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>

                <Card variant="outlined" sx={{ ...styles.sectionCard, flex: 1 }}>
                  <CardContent>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" color="primary" sx={{ fontWeight: 600 }}>
                        📝 System Prompt
                      </Typography>
                      <Chip 
                        label={`${config.prompt.length} chars`} 
                        size="small" 
                        variant="outlined"
                      />
                    </Stack>
                    <TextField
                      value={config.prompt}
                      onChange={(e) => handleConfigChange('prompt', e.target.value)}
                      fullWidth
                      multiline
                      rows={12}
                      placeholder="Enter your system prompt with Jinja2 template syntax..."
                      sx={styles.promptEditor}
                      InputLabelProps={{
                        shrink: true,
                        sx: {
                          color: '#cdd6f4',
                          backgroundColor: '#1e1e2e',
                          px: 0.5,
                          borderRadius: 0.75,
                          '&.Mui-focused': { color: '#cdd6f4' },
                        },
                      }}
                    />
                    <Box sx={{ mt: 1.5 }}>
                      <TemplateVariableHelper
                        usedVars={detectedTemplateVars}
                        onInsert={(val) =>
                          setConfig(prev => ({ ...prev, prompt: (prev.prompt || '') + val }))
                        }
                      />
                    </Box>

                    <Card variant="outlined" sx={{ mt: 2, borderColor: '#e2e8f0' }}>
                      <CardContent>
                        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
                          <Typography variant="subtitle2" color="primary" sx={{ fontWeight: 600 }}>
                            🏢 Template Variables (Prompt Defaults)
                          </Typography>
                          <Button size="small" onClick={() => setTemplateVarsExpanded((prev) => !prev)}>
                            {templateVarsExpanded ? 'Hide' : 'Show'}
                          </Button>
                        </Stack>
                        <Collapse in={templateVarsExpanded} timeout="auto">
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                            Default values for template variables used in your prompt. Session profile data can override these at runtime.
                          </Typography>
                          <Stack spacing={1.2}>
                            {templateVarKeys.length === 0 && (
                              <Typography variant="body2" color="text.secondary">
                                Add variables in your greeting or prompt to customize defaults.
                              </Typography>
                            )}
                            {templateVarKeys.map((key) => {
                              const friendly =
                                key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                              const icon =
                                key === 'institution_name'
                                  ? <BusinessIcon fontSize="small" color="action" />
                                  : key === 'agent_name'
                                  ? <SmartToyIcon fontSize="small" color="action" />
                                  : <InfoOutlinedIcon fontSize="small" color="action" />;
                              return (
                                <TextField
                                  key={key}
                                  label={`${friendly} ({{ ${key} }})`}
                                  value={config.template_vars[key] ?? ''}
                                  onChange={(e) => handleNestedConfigChange('template_vars', key, e.target.value)}
                                  size="small"
                                  fullWidth
                                  InputProps={{
                                    startAdornment: (
                                      <InputAdornment position="start">
                                        {icon}
                                      </InputAdornment>
                                    ),
                                  }}
                                  helperText="Default value; session data can override at runtime"
                                />
                              );
                            })}
                          </Stack>
                        </Collapse>
                      </CardContent>
                    </Card>
                  </CardContent>
                </Card>

                <Alert severity="info" sx={{ borderRadius: '12px' }}>
                  <Typography variant="body2">
                    <strong>Tip:</strong> Use Jinja2 syntax like <code>{'{{ variable }}'}</code> for dynamic content 
                    and <code>{'{% if condition %}'}</code> for conditional blocks. 
                    The <code>tools</code> variable contains the list of enabled tool names.
                  </Typography>
                </Alert>
              </Stack>
            </TabPanel>

            {/* ═══════════════════════════════════════════════════════════════════ */}
            {/* TAB 2: TOOLS */}
            {/* ═══════════════════════════════════════════════════════════════════ */}
            <TabPanel value={activeTab} index={2}>
              <Stack spacing={2}>
                {/* Filter and Summary Card */}
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent sx={{ py: 1.5 }}>
                    <Stack spacing={2}>
                      {/* Filter Toggle */}
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <ToggleButtonGroup
                          value={toolFilter}
                          exclusive
                          onChange={(_, newFilter) => newFilter && setToolFilter(newFilter)}
                          size="small"
                          sx={{
                            '& .MuiToggleButton-root': {
                              textTransform: 'none',
                              px: 2,
                              py: 0.5,
                            },
                          }}
                        >
                          <ToggleButton value="all">
                            <Stack direction="row" alignItems="center" spacing={1}>
                              <BuildIcon fontSize="small" />
                              <span>All Tools</span>
                              <Chip 
                                label={availableTools.length} 
                                size="small" 
                                sx={{ height: 20, fontSize: '11px', ml: 0.5 }} 
                              />
                            </Stack>
                          </ToggleButton>
                          <ToggleButton value="normal">
                            <Stack direction="row" alignItems="center" spacing={1}>
                              <BuildIcon fontSize="small" />
                              <span>Normal</span>
                              <Chip 
                                label={availableTools.filter(t => !t.is_handoff).length} 
                                size="small" 
                                color="primary"
                                variant="outlined"
                                sx={{ height: 20, fontSize: '11px', ml: 0.5 }} 
                              />
                            </Stack>
                          </ToggleButton>
                          <ToggleButton value="handoff">
                            <Stack direction="row" alignItems="center" spacing={1}>
                              <SwapHorizIcon fontSize="small" />
                              <span>Handoffs</span>
                              <Chip 
                                label={handoffTools.length} 
                                size="small" 
                                color="secondary"
                                variant="outlined"
                                sx={{ height: 20, fontSize: '11px', ml: 0.5 }} 
                              />
                            </Stack>
                          </ToggleButton>
                        </ToggleButtonGroup>
                        
                        <Button
                          size="small"
                          onClick={() => setConfig(prev => ({ ...prev, tools: [] }))}
                          disabled={config.tools.length === 0}
                          color="error"
                        >
                          Clear All
                        </Button>
                      </Stack>
                      
                      {/* Selection Summary */}
                      <Divider />
                      <Stack direction="row" alignItems="center" spacing={2}>
                        <Typography variant="body2" color="text.secondary">
                          Selected:
                        </Typography>
                        <Chip 
                          icon={<BuildIcon />}
                          label={`${config.tools.filter(t => !handoffTools.find(h => h.name === t)).length} normal tools`}
                          size="small"
                          color="primary"
                          variant={config.tools.filter(t => !handoffTools.find(h => h.name === t)).length > 0 ? 'filled' : 'outlined'}
                        />
                        <Chip 
                          icon={<SwapHorizIcon />}
                          label={`${config.tools.filter(t => handoffTools.find(h => h.name === t)).length} handoffs`}
                          size="small"
                          color="secondary"
                          variant={config.tools.filter(t => handoffTools.find(h => h.name === t)).length > 0 ? 'filled' : 'outlined'}
                        />
                      </Stack>
                    </Stack>
                  </CardContent>
                </Card>

                {/* Normal Tools by Category */}
                {(toolFilter === 'all' || toolFilter === 'normal') && Object.entries(toolsByCategory)
                  .filter(([cat]) => cat !== 'handoff')
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([category, tools]) => {
                    const categoryTools = tools.filter(t => !t.is_handoff);
                    if (categoryTools.length === 0) return null;
                    const allSelected = categoryTools.every(t => config.tools.includes(t.name));
                    const someSelected = categoryTools.some(t => config.tools.includes(t.name));

                    return (
                      <Accordion
                        key={category}
                        expanded={expandedCategories[category] || false}
                        onChange={() => toggleCategory(category)}
                        sx={{ 
                          borderRadius: '12px !important',
                          '&:before': { display: 'none' },
                          boxShadow: 'none',
                          border: '1px solid #e5e7eb',
                        }}
                      >
                        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                          <Stack direction="row" alignItems="center" spacing={2} sx={{ width: '100%', pr: 2 }}>
                            <Checkbox
                              checked={allSelected}
                              indeterminate={someSelected && !allSelected}
                              onChange={(e) => {
                                e.stopPropagation();
                                handleSelectAllCategory(category, categoryTools);
                              }}
                              onClick={(e) => e.stopPropagation()}
                              size="small"
                            />
                            <Typography variant="subtitle2" sx={{ textTransform: 'capitalize', flex: 1 }}>
                              {category}
                            </Typography>
                            <Chip
                              label={`${categoryTools.filter(t => config.tools.includes(t.name)).length}/${categoryTools.length}`}
                              size="small"
                              color={someSelected ? 'primary' : 'default'}
                              variant={someSelected ? 'filled' : 'outlined'}
                            />
                          </Stack>
                        </AccordionSummary>
                        <AccordionDetails>
                          <List dense disablePadding>
                            {categoryTools.map(tool => (
                              <ListItem
                                key={tool.name}
                                onClick={() => handleToolToggle(tool.name)}
                                sx={{ 
                                  cursor: 'pointer',
                                  borderRadius: '8px',
                                  '&:hover': { backgroundColor: '#f5f5f5' },
                                }}
                              >
                                <ListItemIcon sx={{ minWidth: 36 }}>
                                  <Checkbox
                                    checked={config.tools.includes(tool.name)}
                                    size="small"
                                    edge="start"
                                  />
                                </ListItemIcon>
                                <ListItemText
                                  primary={tool.name}
                                  secondary={tool.description}
                                  primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                                  secondaryTypographyProps={{ variant: 'caption' }}
                                />
                              </ListItem>
                            ))}
                          </List>
                        </AccordionDetails>
                      </Accordion>
                    );
                  })}

                {/* Handoff Tools */}
                {(toolFilter === 'all' || toolFilter === 'handoff') && handoffTools.length > 0 && (
                  <Accordion
                    expanded={expandedCategories['handoff'] || false}
                    onChange={() => toggleCategory('handoff')}
                    sx={{ 
                      borderRadius: '12px !important',
                      '&:before': { display: 'none' },
                      boxShadow: 'none',
                      border: '2px solid #c7d2fe',
                      backgroundColor: '#f5f3ff',
                    }}
                  >
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                      <Stack direction="row" alignItems="center" spacing={2} sx={{ width: '100%', pr: 2 }}>
                        <SwapHorizIcon color="secondary" />
                        <Typography variant="subtitle2" color="secondary" sx={{ flex: 1 }}>
                          Handoff Tools
                        </Typography>
                        <Chip
                          label={`${handoffTools.filter(t => config.tools.includes(t.name)).length}/${handoffTools.length}`}
                          size="small"
                          color="secondary"
                        />
                      </Stack>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                        Handoff tools transfer the conversation to another agent or system
                      </Typography>
                      <List dense disablePadding>
                        {handoffTools.map(tool => (
                          <ListItem
                            key={tool.name}
                            onClick={() => handleToolToggle(tool.name)}
                            sx={{ 
                              cursor: 'pointer',
                              borderRadius: '8px',
                              '&:hover': { backgroundColor: 'rgba(99, 102, 241, 0.1)' },
                            }}
                          >
                            <ListItemIcon sx={{ minWidth: 36 }}>
                              <Checkbox
                                checked={config.tools.includes(tool.name)}
                                size="small"
                                edge="start"
                                color="secondary"
                              />
                            </ListItemIcon>
                            <ListItemText
                              primary={tool.name}
                              secondary={tool.description}
                              primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                              secondaryTypographyProps={{ variant: 'caption' }}
                            />
                          </ListItem>
                        ))}
                      </List>
                    </AccordionDetails>
                  </Accordion>
      )}

              </Stack>
            </TabPanel>

            {/* ═══════════════════════════════════════════════════════════════════ */}
            {/* TAB 3: VOICE */}
            {/* ═══════════════════════════════════════════════════════════════════ */}
            <TabPanel value={activeTab} index={3}>
              <Stack spacing={3}>
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                      🎙️ Voice Selection
                    </Typography>
                    <Autocomplete
                      value={availableVoices.find(v => v.name === config.voice.name) || null}
                      onChange={(_e, newValue) => {
                        if (newValue) {
                          handleNestedConfigChange('voice', 'name', newValue.name);
                        }
                      }}
                      options={availableVoices}
                      groupBy={(option) => option.category}
                      getOptionLabel={(option) => option.display_name || option.name}
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          label="Voice"
                          placeholder="Search voices..."
                        />
                      )}
                      renderOption={(props, option) => {
                        const { key, ...restProps } = props;
                        return (
                          <ListItem {...restProps} key={key}>
                            <ListItemAvatar>
                              <Avatar sx={{ width: 32, height: 32, bgcolor: '#e0e7ff' }}>
                                <RecordVoiceOverIcon fontSize="small" color="primary" />
                              </Avatar>
                            </ListItemAvatar>
                            <ListItemText
                              primary={option.display_name}
                              secondary={option.name}
                              primaryTypographyProps={{ variant: 'body2' }}
                              secondaryTypographyProps={{ variant: 'caption' }}
                            />
                          </ListItem>
                        );
                      }}
                    />
                  </CardContent>
                </Card>

                <Stack direction="row" spacing={2}>
                  <Card variant="outlined" sx={{ ...styles.sectionCard, flex: 1 }}>
                    <CardContent>
                      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5 }}>
                        Speaking Style
                      </Typography>
                      <ToggleButtonGroup
                        value={config.voice.style}
                        exclusive
                        onChange={(_e, v) => v && handleNestedConfigChange('voice', 'style', v)}
                        size="small"
                        fullWidth
                      >
                        <ToggleButton value="chat">💬 Chat</ToggleButton>
                        <ToggleButton value="narration-professional">👔 Professional</ToggleButton>
                        <ToggleButton value="friendly">😊 Friendly</ToggleButton>
                        <ToggleButton value="empathetic">🤗 Empathetic</ToggleButton>
                      </ToggleButtonGroup>
                    </CardContent>
                  </Card>

                  <Card variant="outlined" sx={{ ...styles.sectionCard, flex: 1 }}>
                    <CardContent>
                      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5 }}>
                        Speech Rate
                      </Typography>
                      <ToggleButtonGroup
                        value={config.voice.rate}
                        exclusive
                        onChange={(_e, v) => v && handleNestedConfigChange('voice', 'rate', v)}
                        size="small"
                        fullWidth
                      >
                        <ToggleButton value="-20%">🐢 Slow</ToggleButton>
                        <ToggleButton value="+0%">⚡ Normal</ToggleButton>
                        <ToggleButton value="+20%">🚀 Fast</ToggleButton>
                      </ToggleButtonGroup>
                    </CardContent>
                  </Card>
                </Stack>

                <Card variant="outlined" sx={{ ...styles.sectionCard, bgcolor: '#f0f9ff' }}>
                  <CardContent>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      Voice Preview
                    </Typography>
                    <Stack direction="row" spacing={3}>
                      <Box>
                        <Typography variant="caption" color="text.secondary">Voice</Typography>
                        <Typography variant="body2" fontWeight={600}>{config.voice.name}</Typography>
                      </Box>
                      <Divider orientation="vertical" flexItem />
                      <Box>
                        <Typography variant="caption" color="text.secondary">Style</Typography>
                        <Typography variant="body2" fontWeight={600}>{config.voice.style}</Typography>
                      </Box>
                      <Divider orientation="vertical" flexItem />
                      <Box>
                        <Typography variant="caption" color="text.secondary">Rate</Typography>
                        <Typography variant="body2" fontWeight={600}>{config.voice.rate}</Typography>
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>
              </Stack>
            </TabPanel>

            {/* ═══════════════════════════════════════════════════════════════════ */}
            {/* TAB 4: SPEECH RECOGNITION (STT / VAD) */}
            {/* ═══════════════════════════════════════════════════════════════════ */}
            <TabPanel value={activeTab} index={4}>
              <Stack spacing={3}>
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                      🎤 Voice Activity Detection (VAD)
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                      Control how the speech recognizer detects when you've finished speaking.
                    </Typography>
                    
                    <Stack spacing={4}>
                      <Box>
                        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                          <Stack direction="row" alignItems="center" spacing={1}>
                            <Typography variant="body2" fontWeight={500}>Silence Timeout</Typography>
                            <Tooltip title="Duration of silence (in milliseconds) before finalizing recognition. Lower = faster response, Higher = more complete sentences.">
                              <InfoOutlinedIcon fontSize="small" color="action" />
                            </Tooltip>
                          </Stack>
                          <Chip label={`${config.speech?.vad_silence_timeout_ms || 800}ms`} size="small" color="primary" />
                        </Stack>
                        <Slider
                          value={config.speech?.vad_silence_timeout_ms || 800}
                          onChange={(_e, v) => handleNestedConfigChange('speech', 'vad_silence_timeout_ms', v)}
                          min={200}
                          max={2000}
                          step={100}
                          marks={[
                            { value: 200, label: 'Fast' },
                            { value: 800, label: '800ms' },
                            { value: 1300, label: '1.3s' },
                            { value: 2000, label: 'Slow' },
                          ]}
                        />
                      </Box>

                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={config.speech?.use_semantic_segmentation || false}
                            onChange={(e) => handleNestedConfigChange('speech', 'use_semantic_segmentation', e.target.checked)}
                          />
                        }
                        label={
                          <Stack direction="row" alignItems="center" spacing={1}>
                            <Typography variant="body2">Enable Semantic Segmentation</Typography>
                            <Tooltip title="Uses AI to detect natural sentence boundaries instead of just silence. Can improve transcription quality for longer utterances.">
                              <InfoOutlinedIcon fontSize="small" color="action" />
                            </Tooltip>
                          </Stack>
                        }
                      />
                    </Stack>
                  </CardContent>
                </Card>

                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                      🌍 Language Detection
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                      Languages available for automatic detection. More languages may slightly increase latency.
                    </Typography>
                    
                    <Autocomplete
                      multiple
                      options={['en-US', 'es-ES', 'fr-FR', 'de-DE', 'it-IT', 'pt-BR', 'ja-JP', 'ko-KR', 'zh-CN']}
                      value={config.speech?.candidate_languages || ['en-US']}
                      onChange={(_, newValue) => handleNestedConfigChange('speech', 'candidate_languages', newValue)}
                      renderInput={(params) => (
                        <TextField {...params} label="Candidate Languages" placeholder="Add language..." />
                      )}
                      renderTags={(value, getTagProps) =>
                        value.map((option, index) => (
                          <Chip
                            {...getTagProps({ index })}
                            key={option}
                            label={option}
                            size="small"
                          />
                        ))
                      }
                    />
                  </CardContent>
                </Card>

                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 2, fontWeight: 600 }}>
                      👥 Speaker Diarization (Advanced)
                    </Typography>
                    
                    <Stack spacing={2}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={config.speech?.enable_diarization || false}
                            onChange={(e) => handleNestedConfigChange('speech', 'enable_diarization', e.target.checked)}
                          />
                        }
                        label={
                          <Stack direction="row" alignItems="center" spacing={1}>
                            <Typography variant="body2">Enable Speaker Diarization</Typography>
                            <Tooltip title="Identifies different speakers in the audio. Useful for multi-speaker scenarios but adds latency.">
                              <InfoOutlinedIcon fontSize="small" color="action" />
                            </Tooltip>
                          </Stack>
                        }
                      />
                      
                      {config.speech?.enable_diarization && (
                        <Box sx={{ pl: 3 }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                            <Typography variant="body2" fontWeight={500}>Expected Speakers</Typography>
                            <Chip label={config.speech?.speaker_count_hint || 2} size="small" color="primary" />
                          </Stack>
                          <Slider
                            value={config.speech?.speaker_count_hint || 2}
                            onChange={(_e, v) => handleNestedConfigChange('speech', 'speaker_count_hint', v)}
                            min={1}
                            max={10}
                            step={1}
                            marks={[
                              { value: 1, label: '1' },
                              { value: 2, label: '2' },
                              { value: 5, label: '5' },
                              { value: 10, label: '10' },
                            ]}
                          />
                        </Box>
                      )}
                    </Stack>
                  </CardContent>
                </Card>

                {/* Speech Settings Summary */}
                <Card variant="outlined" sx={{ ...styles.sectionCard, bgcolor: 'action.hover' }}>
                  <CardContent>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                      📋 Current Speech Settings
                    </Typography>
                    <Stack direction="row" spacing={3} divider={<Divider orientation="vertical" flexItem />}>
                      <Box>
                        <Typography variant="caption" color="text.secondary">Silence Timeout</Typography>
                        <Typography variant="body2" fontWeight={600}>{config.speech?.vad_silence_timeout_ms || 800}ms</Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary">Semantic</Typography>
                        <Typography variant="body2" fontWeight={600}>{config.speech?.use_semantic_segmentation ? 'Enabled' : 'Disabled'}</Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary">Languages</Typography>
                        <Typography variant="body2" fontWeight={600}>{(config.speech?.candidate_languages || ['en-US']).length}</Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary">Diarization</Typography>
                        <Typography variant="body2" fontWeight={600}>{config.speech?.enable_diarization ? 'On' : 'Off'}</Typography>
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>
              </Stack>
            </TabPanel>

            {/* ═══════════════════════════════════════════════════════════════════ */}
            {/* TAB 5: MODEL */}
            {/* ═══════════════════════════════════════════════════════════════════ */}
            <TabPanel value={activeTab} index={5}>
              <Stack spacing={3}>
                <Alert severity="info" icon={<WarningAmberIcon />} sx={{ borderRadius: '12px' }}>
                  <AlertTitle sx={{ fontWeight: 600 }}>Azure OpenAI Deployment Required</AlertTitle>
                  <Typography variant="body2">
                    Model deployment names must match deployments in your Azure OpenAI resource.
                    Different models are used depending on the orchestration mode.
                  </Typography>
                </Alert>

                {/* Cascade Mode Model */}
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
                      <Chip label="Cascade Mode" color="primary" size="small" />
                      <Typography variant="subtitle2" color="primary" sx={{ fontWeight: 600 }}>
                        🔄 STT → LLM → TTS Pipeline
                      </Typography>
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Uses standard Chat Completion API. Best for complex conversations with tool calling.
                    </Typography>
                    <ModelSelector
                      value={config.cascade_model?.deployment_id || 'gpt-4o'}
                      onChange={(v) => handleNestedConfigChange('cascade_model', 'deployment_id', v)}
                      modelOptions={CASCADE_MODEL_OPTIONS}
                      title="Cascade Model Deployment"
                      showAlert={false}
                    />
                  </CardContent>
                </Card>

                {/* VoiceLive Mode Model */}
                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
                      <Chip label="VoiceLive Mode" color="secondary" size="small" />
                      <Typography variant="subtitle2" color="secondary" sx={{ fontWeight: 600 }}>
                        ⚡ Realtime Audio API
                      </Typography>
                    </Stack>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Uses Realtime API for ultra-low latency. Audio streams directly to/from the model.
                    </Typography>
                    <ModelSelector
                      value={config.voicelive_model?.deployment_id || 'gpt-realtime'}
                      onChange={(v) => handleNestedConfigChange('voicelive_model', 'deployment_id', v)}
                      modelOptions={VOICELIVE_MODEL_OPTIONS}
                      title="VoiceLive Model Deployment"
                      showAlert={false}
                    />
                  </CardContent>
                </Card>

                <Divider />

                <Card variant="outlined" sx={styles.sectionCard}>
                  <CardContent>
                    <Typography variant="subtitle2" color="primary" sx={{ mb: 3, fontWeight: 600 }}>
                      ⚙️ Generation Parameters (Shared)
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 3 }}>
                      These parameters apply to both Cascade and VoiceLive modes.
                    </Typography>

                    <Stack spacing={4}>
                      <Box>
                        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                          <Stack direction="row" alignItems="center" spacing={1}>
                            <Typography variant="body2" fontWeight={500}>Temperature</Typography>
                            <Tooltip title="Controls randomness. Lower values = more focused and deterministic. Higher values = more creative and varied.">
                              <InfoOutlinedIcon fontSize="small" color="action" />
                            </Tooltip>
                          </Stack>
                          <Chip label={config.cascade_model?.temperature ?? 0.7} size="small" color="primary" />
                        </Stack>
                        <Slider
                          value={config.cascade_model?.temperature ?? 0.7}
                          onChange={(_e, v) => {
                            handleNestedConfigChange('cascade_model', 'temperature', v);
                            handleNestedConfigChange('voicelive_model', 'temperature', v);
                          }}
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
                            <Tooltip title="Controls diversity via nucleus sampling. Lower values make output more focused.">
                              <InfoOutlinedIcon fontSize="small" color="action" />
                            </Tooltip>
                          </Stack>
                          <Chip label={config.cascade_model?.top_p ?? 0.9} size="small" color="primary" />
                        </Stack>
                        <Slider
                          value={config.cascade_model?.top_p ?? 0.9}
                          onChange={(_e, v) => {
                            handleNestedConfigChange('cascade_model', 'top_p', v);
                            handleNestedConfigChange('voicelive_model', 'top_p', v);
                          }}
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
                            <Tooltip title="Maximum number of tokens in the response. Higher values allow longer responses but may increase latency.">
                              <InfoOutlinedIcon fontSize="small" color="action" />
                            </Tooltip>
                          </Stack>
                          <Chip label={`${(config.cascade_model?.max_tokens ?? 4096).toLocaleString()} tokens`} size="small" color="primary" />
                        </Stack>
                        <Slider
                          value={config.cascade_model?.max_tokens ?? 4096}
                          onChange={(_e, v) => {
                            handleNestedConfigChange('cascade_model', 'max_tokens', v);
                            handleNestedConfigChange('voicelive_model', 'max_tokens', v);
                          }}
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
                    </Stack>
                  </CardContent>
                </Card>
              </Stack>
            </TabPanel>
          </>
        )}
      </DialogContent>

      {/* Actions */}
      <Divider />
      <DialogActions sx={{ padding: '16px 24px', backgroundColor: '#fafbfc' }}>
        <Button
          onClick={handleReset}
          startIcon={<RefreshIcon />}
          disabled={saving}
        >
          Reset to Defaults
        </Button>
        <Box sx={{ flex: 1 }} />
        <Button onClick={onClose} disabled={saving}>
          Cancel
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
            boxShadow: isEditMode
              ? '0 4px 14px rgba(245, 158, 11, 0.35)'
              : '0 4px 14px rgba(99, 102, 241, 0.35)',
            '&:hover': {
              background: isEditMode
                ? 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)'
                : 'linear-gradient(135deg, #4338ca 0%, #4f46e5 100%)',
            },
          }}
        >
          {saving 
            ? (isEditMode ? 'Updating...' : 'Creating...') 
            : (isEditMode ? 'Update Agent' : 'Create Agent')
          }
        </Button>
      </DialogActions>
    </Dialog>
  );
}
