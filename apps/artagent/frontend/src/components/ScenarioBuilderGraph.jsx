/**
 * ScenarioBuilderGraph Component
 * ===============================
 * 
 * A React-native scenario builder using SVG for visual flow editing.
 * This component provides a clean interface for building agent workflows
 * with proper edge definition and visual representation of handoffs.
 * 
 * Features:
 * - Drag agents from sidebar to canvas
 * - Click to select nodes, click again to create edges
 * - Visual representation of handoff flows with arrows
 * - Compatible with existing scenario configuration format
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Popover,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import DeleteIcon from '@mui/icons-material/Delete';
import DownloadIcon from '@mui/icons-material/Download';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import HubIcon from '@mui/icons-material/Hub';
import LinkIcon from '@mui/icons-material/Link';
import MicIcon from '@mui/icons-material/Mic';
import MemoryIcon from '@mui/icons-material/Memory';
import RefreshIcon from '@mui/icons-material/Refresh';
import SaveIcon from '@mui/icons-material/Save';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import SettingsIcon from '@mui/icons-material/Settings';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import VolumeOffIcon from '@mui/icons-material/VolumeOff';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import BuildIcon from '@mui/icons-material/Build';
import DescriptionIcon from '@mui/icons-material/Description';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import HomeIcon from '@mui/icons-material/Home';
import GpsFixedIcon from '@mui/icons-material/GpsFixed';
import CreditCardIcon from '@mui/icons-material/CreditCard';
import WarningIcon from '@mui/icons-material/Warning';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import AttachMoneyIcon from '@mui/icons-material/AttachMoney';
import EditIcon from '@mui/icons-material/Edit';

import { API_BASE_URL } from '../config/constants.js';
import logger from '../utils/logger.js';
import { AgentDetailsDialog } from './AgentBuilderContent.jsx';

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS & STYLES
// ═══════════════════════════════════════════════════════════════════════════════

const colors = {
  start: { bg: '#ecfdf5', border: '#10b981', avatar: '#059669', text: '#065f46' },
  active: { bg: '#f5f3ff', border: '#8b5cf6', avatar: '#7c3aed', text: '#5b21b6' },
  session: { bg: '#fef3c7', border: '#f59e0b', avatar: '#d97706', text: '#92400e' },
  selected: { bg: '#dbeafe', border: '#3b82f6', avatar: '#2563eb', text: '#1e40af' },
  invalid: { bg: '#fef2f2', border: '#ef4444', avatar: '#dc2626', text: '#991b1b' },
};

// ═══════════════════════════════════════════════════════════════════════════════
// HANDOFF CONDITION PATTERNS
// ═══════════════════════════════════════════════════════════════════════════════

const HANDOFF_CONDITION_PATTERNS = [
  {
    id: 'authentication',
    name: 'Authentication Required',
    IconComponent: PersonAddIcon,
    description: 'When identity verification or login is needed',
    condition: `Transfer when the customer needs to:
- Verify their identity or authenticate
- Log into their account
- Provide security credentials or PIN
- Complete multi-factor authentication`,
  },
  {
    id: 'specialized_topic',
    name: 'Specialized Topic',
    IconComponent: GpsFixedIcon,
    description: 'When conversation requires specific expertise',
    condition: `Transfer when the customer asks about topics that require specialized knowledge or expertise that this agent cannot provide.`,
  },
  {
    id: 'account_issue',
    name: 'Account/Billing Issue',
    IconComponent: CreditCardIcon,
    description: 'Account management or billing concerns',
    condition: `Transfer when the customer mentions:
- Account access problems or lockouts
- Billing discrepancies or payment issues
- Subscription changes or cancellations
- Refund requests or credit adjustments`,
  },
  {
    id: 'fraud_security',
    name: 'Fraud/Security Concern',
    IconComponent: WarningIcon,
    description: 'Suspicious activity or security issues',
    condition: `Transfer IMMEDIATELY when the customer reports:
- Unauthorized transactions or suspicious activity
- Lost or stolen cards/credentials
- Potential identity theft or account compromise
- Security alerts or concerns`,
  },
  {
    id: 'technical_support',
    name: 'Technical Support',
    IconComponent: BuildIcon,
    description: 'Technical issues requiring troubleshooting',
    condition: `Transfer when the customer needs help with:
- Technical problems or error messages
- Product or service not working correctly
- Setup, configuration, or installation issues
- Connectivity or performance problems`,
  },
  {
    id: 'escalation',
    name: 'Escalation Request',
    IconComponent: TrendingUpIcon,
    description: 'Customer requests supervisor or escalation',
    condition: `Transfer when the customer:
- Explicitly requests to speak with a supervisor or manager
- Expresses significant dissatisfaction that you cannot resolve
- Has a complex issue requiring higher authorization
- Needs decisions beyond your authority level`,
  },
  {
    id: 'sales_upsell',
    name: 'Sales/Upsell Opportunity',
    IconComponent: AttachMoneyIcon,
    description: 'Interest in purchasing or upgrading',
    condition: `Transfer when the customer expresses interest in:
- Purchasing new products or services
- Upgrading their current plan or subscription
- Special offers, promotions, or deals
- Comparing options or getting pricing information`,
  },
  {
    id: 'custom',
    name: 'Custom Condition',
    IconComponent: EditIcon,
    description: 'Write your own handoff condition',
    condition: '',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

const buildHandoffInstructions = (handoffs, agentName) => {
  if (!agentName) return '';
  const outgoing = (handoffs || []).filter((handoff) => handoff?.from_agent === agentName);
  if (outgoing.length === 0) return '';
  const lines = [
    '## Agent Handoff Instructions',
    '',
    'You can transfer the conversation to other specialized agents when appropriate.',
    'Use the `handoff_to_agent` tool with the target agent name and reason.',
    'Call the tool immediately without announcing the transfer - the target agent will greet the customer.',
    '',
    '**Available Handoff Targets:**',
    '',
  ];
  outgoing.forEach((handoff) => {
    const targetAgent = handoff?.to_agent || 'the target agent';
    let condition = (handoff?.handoff_condition || '').trim();
    if (!condition) {
      condition = `When the customer's needs are better served by ${targetAgent}.`;
    }
    lines.push(
      `- **${targetAgent}** - call \`handoff_to_agent(target_agent="${targetAgent}", reason="...")\``
    );
    condition.split('\n').forEach((line) => {
      if (line.trim()) {
        lines.push(`  ${line.trim()}`);
      }
    });
    lines.push('');
  });
  return lines.join('\n');
};

const buildRuntimePrompt = (prompt, handoffs, agentName) => {
  const instructions = buildHandoffInstructions(handoffs, agentName);
  if (!instructions) return prompt || '';
  if (!prompt) return instructions;
  return `${prompt}\n\n${instructions}`;
};

const getRuntimePromptPreview = (prompt) => {
  if (!prompt) return { text: '', hasHandoffInstructions: false };
  const hasHandoffInstructions = prompt.includes('## Agent Handoff Instructions');
  return { text: prompt, hasHandoffInstructions };
};

// Component to render highlighted runtime prompt preview
function HighlightedPromptPreview({ previewData, targetAgent }) {
  const handoffRef = useRef(null);

  useEffect(() => {
    if (handoffRef.current && previewData?.hasHandoffInstructions) {
      handoffRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [previewData?.text, previewData?.hasHandoffInstructions]);

  if (!previewData || !previewData.text) {
    return <span>No prompt available.</span>;
  }

  const { text, hasHandoffInstructions } = previewData;

  if (!hasHandoffInstructions) {
    return <span>{text}</span>;
  }

  const parts = text.split('## Agent Handoff Instructions');
  if (parts.length === 1) {
    return <span>{text}</span>;
  }

  const beforeHandoff = parts[0];
  const handoffSection = parts[1];

  if (targetAgent) {
    const targetMarker = `- **${targetAgent}**`;
    const handoffLines = handoffSection.split('\n');
    let targetStartIdx = -1;
    let targetEndIdx = -1;

    for (let i = 0; i < handoffLines.length; i++) {
      if (handoffLines[i].includes(targetMarker)) {
        targetStartIdx = i;
        break;
      }
    }

    if (targetStartIdx !== -1) {
      for (let i = targetStartIdx + 1; i < handoffLines.length; i++) {
        if (handoffLines[i].trim().startsWith('- **') && handoffLines[i].includes('**')) {
          targetEndIdx = i;
          break;
        }
      }
      if (targetEndIdx === -1) targetEndIdx = handoffLines.length;
    }

    if (targetStartIdx !== -1) {
      const beforeTarget = handoffLines.slice(0, targetStartIdx).join('\n');
      const targetSection = handoffLines.slice(targetStartIdx, targetEndIdx).join('\n');
      const afterTarget = handoffLines.slice(targetEndIdx).join('\n');

      return (
        <>
          <span>{beforeHandoff}</span>
          <span style={{ backgroundColor: '#fef3c7', color: '#92400e', padding: '2px 4px', borderRadius: '3px', fontWeight: 600 }}>
            ## Agent Handoff Instructions
          </span>
          <span>{beforeTarget}</span>
          <span ref={handoffRef} style={{ backgroundColor: '#fef9e7', display: 'inline-block', paddingLeft: '4px', borderLeft: '3px solid #fbbf24' }}>
            {targetSection}
          </span>
          <span>{afterTarget}</span>
        </>
      );
    }
  }

  return (
    <>
      <span>{beforeHandoff}</span>
      <span style={{ backgroundColor: '#fef3c7', color: '#92400e', padding: '2px 4px', borderRadius: '3px', fontWeight: 600 }}>
        ## Agent Handoff Instructions
      </span>
      <span ref={handoffRef} style={{ backgroundColor: '#fef9e7' }}>
        {handoffSection}
      </span>
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HANDOFF EDITOR DIALOG (Full implementation with patterns and preview)
// ═══════════════════════════════════════════════════════════════════════════════

const HandoffEditorDialog = React.memo(function HandoffEditorDialog({ open, onClose, handoff, agents, scenarioAgents = [], handoffs, onSave, onDelete }) {
  const [type, setType] = useState(handoff?.type || 'announced');
  const [shareContext, setShareContext] = useState(handoff?.share_context !== false);
  const [handoffCondition, setHandoffCondition] = useState(handoff?.handoff_condition || '');
  const [selectedPattern, setSelectedPattern] = useState(null);
  const [showPatternPicker, setShowPatternPicker] = useState(false);

  // Editable source and target agents
  const [fromAgent, setFromAgent] = useState(handoff?.from_agent || '');
  const [toAgent, setToAgent] = useState(handoff?.to_agent || '');
  const [sourceAnchorEl, setSourceAnchorEl] = useState(null);
  const [targetAnchorEl, setTargetAnchorEl] = useState(null);

  const sourceAgent = agents?.find(a => a.name === fromAgent);
  const targetAgent = agents?.find(a => a.name === toAgent);

  // Build runtime handoffs for preview
  const runtimeHandoffs = useMemo(() => {
    if (!fromAgent || !toAgent) return handoffs || [];
    const baseHandoffs = Array.isArray(handoffs) ? handoffs : [];
    let matched = false;
    const updated = baseHandoffs.map((edge) => {
      if (edge.from_agent === handoff?.from_agent && edge.to_agent === handoff?.to_agent) {
        matched = true;
        return { ...edge, from_agent: fromAgent, to_agent: toAgent, handoff_condition: handoffCondition };
      }
      return edge;
    });
    if (!matched) {
      updated.push({ from_agent: fromAgent, to_agent: toAgent, handoff_condition: handoffCondition });
    }
    return updated;
  }, [handoffs, handoff, fromAgent, toAgent, handoffCondition]);

  // Build runtime prompt preview
  const runtimePrompt = useMemo(() => {
    if (!fromAgent) return '';
    const basePrompt = sourceAgent?.prompt_full || sourceAgent?.prompt_preview || '';
    return buildRuntimePrompt(basePrompt, runtimeHandoffs, fromAgent);
  }, [fromAgent, runtimeHandoffs, sourceAgent]);

  const runtimePromptPreview = useMemo(
    () => getRuntimePromptPreview(runtimePrompt),
    [runtimePrompt],
  );

  // Track handoff identity to reset state when editing different handoff
  const handoffKey = handoff ? `${handoff.from_agent}::${handoff.to_agent}` : null;
  const prevHandoffKeyRef = useRef(null);

  useEffect(() => {
    const handoffChanged = prevHandoffKeyRef.current !== handoffKey;
    if (handoff && handoffChanged) {
      prevHandoffKeyRef.current = handoffKey;
      setType(handoff.type || 'announced');
      setShareContext(handoff.share_context !== false);
      setHandoffCondition(handoff.handoff_condition || '');
      setFromAgent(handoff.from_agent || '');
      setToAgent(handoff.to_agent || '');
      // Detect if current condition matches a pattern
      const matchingPattern = HANDOFF_CONDITION_PATTERNS.find(
        p => p.condition && p.condition.trim() === (handoff.handoff_condition || '').trim()
      );
      setSelectedPattern(matchingPattern?.id || (handoff.handoff_condition ? 'custom' : null));
    }
  }, [handoffKey, handoff]);

  const handlePatternSelect = (patternId) => {
    const pattern = HANDOFF_CONDITION_PATTERNS.find(p => p.id === patternId);
    if (pattern) {
      setSelectedPattern(patternId);
      if (patternId !== 'custom') {
        const condition = pattern.condition.replace(/\{target_agent\}/g, toAgent || 'the target agent');
        setHandoffCondition(condition);
      }
      setShowPatternPicker(false);
    }
  };

  const handleSave = () => {
    onSave({
      ...handoff,
      from_agent: fromAgent,
      to_agent: toAgent,
      type,
      tool: 'handoff_to_agent',
      share_context: shareContext,
      handoff_condition: handoffCondition,
      context_vars: handoff?.context_vars || {},
      // Include original agents for replacement detection
      _original_from: handoff.from_agent,
      _original_to: handoff.to_agent,
    });
    onClose();
  };

  // Check if the current handoff configuration is valid
  const isValidHandoff = fromAgent && toAgent && fromAgent !== toAgent;
  const isDuplicateHandoff = handoffs?.some(
    h => h.from_agent === fromAgent && h.to_agent === toAgent &&
         !(h.from_agent === handoff?.from_agent && h.to_agent === handoff?.to_agent)
  );

  if (!handoff) return null;

  // Get available agents for source (exclude current target)
  const availableSourceAgents = agents?.filter(a => a.name !== toAgent) || [];
  // Get available agents for target (exclude current source)
  const availableTargetAgents = agents?.filter(a => a.name !== fromAgent) || [];

  // Categorize agents into in-canvas and available-to-add
  const categorizeAgents = (agentList) => {
    const inCanvas = agentList.filter(a => scenarioAgents.includes(a.name));
    const availableToAdd = agentList.filter(a => !scenarioAgents.includes(a.name));
    return { inCanvas, availableToAdd };
  };

  const sourceAgentCategories = categorizeAgents(availableSourceAgents);
  const targetAgentCategories = categorizeAgents(availableTargetAgents);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <LinkIcon color="primary" />
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Edit Handoff
          </Typography>
        </Box>
        <IconButton onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      
      <DialogContent dividers>
        <Stack spacing={3} sx={{ mt: 1 }}>
          {/* Flow visualization with clickable agent selection */}
          <Paper variant="outlined" sx={{ p: 2, backgroundColor: '#f8fafc', borderRadius: 2 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'center', mb: 1.5 }}>
              Click on an agent to change it
            </Typography>
            <Stack direction="row" alignItems="center" justifyContent="center" spacing={2}>
              {/* Source Agent - Clickable */}
              <Tooltip title="Click to change source agent" arrow>
                <Chip
                  avatar={<Avatar sx={{ bgcolor: colors.active.avatar }}>{sourceAgent?.name?.[0] || '?'}</Avatar>}
                  label={fromAgent}
                  onClick={(e) => setSourceAnchorEl(e.currentTarget)}
                  sx={{
                    fontWeight: 600,
                    cursor: 'pointer',
                    border: '2px solid transparent',
                    '&:hover': {
                      borderColor: '#6366f1',
                      backgroundColor: 'rgba(99, 102, 241, 0.08)',
                    },
                  }}
                  deleteIcon={<ArrowForwardIcon sx={{ fontSize: 16 }} />}
                />
              </Tooltip>

              <ArrowForwardIcon sx={{ color: '#6366f1' }} />

              {/* Target Agent - Clickable */}
              <Tooltip title="Click to change target agent" arrow>
                <Chip
                  avatar={<Avatar sx={{ bgcolor: colors.start.avatar }}>{targetAgent?.name?.[0] || '?'}</Avatar>}
                  label={toAgent}
                  onClick={(e) => setTargetAnchorEl(e.currentTarget)}
                  sx={{
                    fontWeight: 600,
                    cursor: 'pointer',
                    border: '2px solid transparent',
                    '&:hover': {
                      borderColor: '#10b981',
                      backgroundColor: 'rgba(16, 185, 129, 0.08)',
                    },
                  }}
                />
              </Tooltip>
            </Stack>

            {/* Validation messages */}
            {fromAgent === toAgent && fromAgent && (
              <Typography variant="caption" color="error" sx={{ display: 'block', textAlign: 'center', mt: 1 }}>
                ⚠️ Source and target agent cannot be the same
              </Typography>
            )}
            {isDuplicateHandoff && (
              <Typography variant="caption" color="error" sx={{ display: 'block', textAlign: 'center', mt: 1 }}>
                ⚠️ This handoff already exists
              </Typography>
            )}
          </Paper>

          {/* Source Agent Popover */}
          <Popover
            open={Boolean(sourceAnchorEl)}
            anchorEl={sourceAnchorEl}
            onClose={() => setSourceAnchorEl(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
            transformOrigin={{ vertical: 'top', horizontal: 'center' }}
          >
            <Box sx={{ p: 1, minWidth: 250, maxHeight: 400, overflowY: 'auto' }}>
              <Typography variant="caption" color="text.secondary" sx={{ px: 1, py: 0.5, display: 'block' }}>
                Select Source Agent
              </Typography>

              {/* In Canvas Section */}
              {sourceAgentCategories.inCanvas.length > 0 && (
                <>
                  <Typography
                    variant="caption"
                    sx={{
                      px: 1,
                      py: 0.5,
                      mt: 0.5,
                      display: 'block',
                      fontWeight: 600,
                      color: '#10b981',
                      textTransform: 'uppercase',
                      fontSize: 9,
                      letterSpacing: 0.5,
                    }}
                  >
                    In Canvas
                  </Typography>
                  {sourceAgentCategories.inCanvas.map((agent) => (
                    <MenuItem
                      key={agent.name}
                      selected={agent.name === fromAgent}
                      onClick={() => {
                        setFromAgent(agent.name);
                        setSourceAnchorEl(null);
                      }}
                      sx={{ borderRadius: 1, my: 0.25, backgroundColor: 'rgba(16, 185, 129, 0.04)' }}
                    >
                      <Avatar sx={{ width: 24, height: 24, mr: 1, bgcolor: colors.active.avatar, fontSize: 12 }}>
                        {agent.name[0]}
                      </Avatar>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: agent.name === fromAgent ? 600 : 400 }}>
                          {agent.name}
                        </Typography>
                        {agent.description && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontSize: 10 }}>
                            {agent.description.slice(0, 40)}{agent.description.length > 40 ? '...' : ''}
                          </Typography>
                        )}
                      </Box>
                      {agent.name === fromAgent && <CheckIcon sx={{ ml: 1, color: '#6366f1', fontSize: 18 }} />}
                    </MenuItem>
                  ))}
                </>
              )}

              {/* Available to Add Section */}
              {sourceAgentCategories.availableToAdd.length > 0 && (
                <>
                  <Typography
                    variant="caption"
                    sx={{
                      px: 1,
                      py: 0.5,
                      mt: sourceAgentCategories.inCanvas.length > 0 ? 1 : 0.5,
                      display: 'block',
                      fontWeight: 600,
                      color: '#94a3b8',
                      textTransform: 'uppercase',
                      fontSize: 9,
                      letterSpacing: 0.5,
                    }}
                  >
                    Available to Add
                  </Typography>
                  {sourceAgentCategories.availableToAdd.map((agent) => (
                    <MenuItem
                      key={agent.name}
                      selected={agent.name === fromAgent}
                      onClick={() => {
                        setFromAgent(agent.name);
                        setSourceAnchorEl(null);
                      }}
                      sx={{ borderRadius: 1, my: 0.25, opacity: 0.7 }}
                    >
                      <Avatar sx={{ width: 24, height: 24, mr: 1, bgcolor: colors.active.avatar, fontSize: 12 }}>
                        {agent.name[0]}
                      </Avatar>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: agent.name === fromAgent ? 600 : 400 }}>
                          {agent.name}
                        </Typography>
                        {agent.description && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontSize: 10 }}>
                            {agent.description.slice(0, 40)}{agent.description.length > 40 ? '...' : ''}
                          </Typography>
                        )}
                      </Box>
                      {agent.name === fromAgent && <CheckIcon sx={{ ml: 1, color: '#6366f1', fontSize: 18 }} />}
                    </MenuItem>
                  ))}
                </>
              )}
            </Box>
          </Popover>

          {/* Target Agent Popover */}
          <Popover
            open={Boolean(targetAnchorEl)}
            anchorEl={targetAnchorEl}
            onClose={() => setTargetAnchorEl(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
            transformOrigin={{ vertical: 'top', horizontal: 'center' }}
          >
            <Box sx={{ p: 1, minWidth: 250, maxHeight: 400, overflowY: 'auto' }}>
              <Typography variant="caption" color="text.secondary" sx={{ px: 1, py: 0.5, display: 'block' }}>
                Select Target Agent
              </Typography>

              {/* In Canvas Section */}
              {targetAgentCategories.inCanvas.length > 0 && (
                <>
                  <Typography
                    variant="caption"
                    sx={{
                      px: 1,
                      py: 0.5,
                      mt: 0.5,
                      display: 'block',
                      fontWeight: 600,
                      color: '#10b981',
                      textTransform: 'uppercase',
                      fontSize: 9,
                      letterSpacing: 0.5,
                    }}
                  >
                    In Canvas
                  </Typography>
                  {targetAgentCategories.inCanvas.map((agent) => (
                    <MenuItem
                      key={agent.name}
                      selected={agent.name === toAgent}
                      onClick={() => {
                        setToAgent(agent.name);
                        setTargetAnchorEl(null);
                        // Update handoff condition if using a pattern
                        if (selectedPattern && selectedPattern !== 'custom') {
                          const pattern = HANDOFF_CONDITION_PATTERNS.find(p => p.id === selectedPattern);
                          if (pattern) {
                            setHandoffCondition(pattern.condition.replace(/\{target_agent\}/g, agent.name));
                          }
                        }
                      }}
                      sx={{ borderRadius: 1, my: 0.25, backgroundColor: 'rgba(16, 185, 129, 0.04)' }}
                    >
                      <Avatar sx={{ width: 24, height: 24, mr: 1, bgcolor: colors.start.avatar, fontSize: 12 }}>
                        {agent.name[0]}
                      </Avatar>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: agent.name === toAgent ? 600 : 400 }}>
                          {agent.name}
                        </Typography>
                        {agent.description && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontSize: 10 }}>
                            {agent.description.slice(0, 40)}{agent.description.length > 40 ? '...' : ''}
                          </Typography>
                        )}
                      </Box>
                      {agent.name === toAgent && <CheckIcon sx={{ ml: 1, color: '#10b981', fontSize: 18 }} />}
                    </MenuItem>
                  ))}
                </>
              )}

              {/* Available to Add Section */}
              {targetAgentCategories.availableToAdd.length > 0 && (
                <>
                  <Typography
                    variant="caption"
                    sx={{
                      px: 1,
                      py: 0.5,
                      mt: targetAgentCategories.inCanvas.length > 0 ? 1 : 0.5,
                      display: 'block',
                      fontWeight: 600,
                      color: '#94a3b8',
                      textTransform: 'uppercase',
                      fontSize: 9,
                      letterSpacing: 0.5,
                    }}
                  >
                    Available to Add
                  </Typography>
                  {targetAgentCategories.availableToAdd.map((agent) => (
                    <MenuItem
                      key={agent.name}
                      selected={agent.name === toAgent}
                      onClick={() => {
                        setToAgent(agent.name);
                        setTargetAnchorEl(null);
                        // Update handoff condition if using a pattern
                        if (selectedPattern && selectedPattern !== 'custom') {
                          const pattern = HANDOFF_CONDITION_PATTERNS.find(p => p.id === selectedPattern);
                          if (pattern) {
                            setHandoffCondition(pattern.condition.replace(/\{target_agent\}/g, agent.name));
                          }
                        }
                      }}
                      sx={{ borderRadius: 1, my: 0.25, opacity: 0.7 }}
                    >
                      <Avatar sx={{ width: 24, height: 24, mr: 1, bgcolor: colors.start.avatar, fontSize: 12 }}>
                        {agent.name[0]}
                      </Avatar>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: agent.name === toAgent ? 600 : 400 }}>
                          {agent.name}
                        </Typography>
                        {agent.description && (
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontSize: 10 }}>
                            {agent.description.slice(0, 40)}{agent.description.length > 40 ? '...' : ''}
                          </Typography>
                        )}
                      </Box>
                      {agent.name === toAgent && <CheckIcon sx={{ ml: 1, color: '#10b981', fontSize: 18 }} />}
                    </MenuItem>
                  ))}
                </>
              )}
            </Box>
          </Popover>

          {/* Pattern Selection Section */}
          <Box>
            <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
              <AutoFixHighIcon sx={{ fontSize: 16, color: '#6366f1' }} />
              When should this handoff happen?
            </Typography>

            {/* Quick pattern chips */}
            <Box sx={{ mb: 2 }}>
              <Stack direction="row" flexWrap="wrap" gap={1}>
                {HANDOFF_CONDITION_PATTERNS.slice(0, 6).map((pattern) => {
                  const Icon = pattern.IconComponent;
                  return (
                    <Chip
                      key={pattern.id}
                      icon={<Icon sx={{ fontSize: 18 }} />}
                      label={pattern.name}
                      onClick={() => handlePatternSelect(pattern.id)}
                      variant={selectedPattern === pattern.id ? 'filled' : 'outlined'}
                      color={selectedPattern === pattern.id ? 'primary' : 'default'}
                      sx={{
                        cursor: 'pointer',
                        fontWeight: selectedPattern === pattern.id ? 600 : 400,
                        '&:hover': { backgroundColor: selectedPattern === pattern.id ? undefined : 'rgba(99, 102, 241, 0.08)' },
                      }}
                    />
                  );
                })}
                <Chip
                  icon={<AddIcon sx={{ fontSize: 18 }} />}
                  label="More..."
                  onClick={() => setShowPatternPicker(!showPatternPicker)}
                  variant="outlined"
                  sx={{ cursor: 'pointer', borderStyle: 'dashed', '&:hover': { backgroundColor: 'rgba(99, 102, 241, 0.08)' } }}
                />
              </Stack>
            </Box>

            {/* Expanded pattern picker */}
            <Collapse in={showPatternPicker}>
              <Paper variant="outlined" sx={{ p: 2, mb: 2, borderRadius: '12px', backgroundColor: '#fafafa' }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5, fontWeight: 600 }}>
                  All Handoff Patterns:
                </Typography>
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 1 }}>
                  {HANDOFF_CONDITION_PATTERNS.map((pattern) => {
                    const Icon = pattern.IconComponent;
                    return (
                      <Paper
                        key={pattern.id}
                        variant="outlined"
                        onClick={() => handlePatternSelect(pattern.id)}
                        sx={{
                          p: 1.5,
                          cursor: 'pointer',
                          borderRadius: '8px',
                          borderColor: selectedPattern === pattern.id ? '#6366f1' : '#e5e7eb',
                          backgroundColor: selectedPattern === pattern.id ? 'rgba(99, 102, 241, 0.08)' : '#fff',
                          transition: 'all 0.2s',
                          '&:hover': { borderColor: '#6366f1', boxShadow: '0 2px 8px rgba(99, 102, 241, 0.15)' },
                        }}
                      >
                        <Stack direction="row" spacing={1} alignItems="flex-start">
                          <Icon sx={{ fontSize: 22, color: selectedPattern === pattern.id ? '#6366f1' : '#64748b' }} />
                          <Box sx={{ flex: 1 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 12 }}>
                              {pattern.name}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10 }}>
                              {pattern.description}
                            </Typography>
                          </Box>
                          {selectedPattern === pattern.id && (
                            <CheckIcon sx={{ color: '#6366f1', fontSize: 18 }} />
                          )}
                        </Stack>
                      </Paper>
                    );
                  })}
                </Box>
              </Paper>
            </Collapse>

            {/* Condition text area */}
            <TextField
              value={handoffCondition}
              onChange={(e) => {
                setHandoffCondition(e.target.value);
                setSelectedPattern('custom');
              }}
              size="small"
              fullWidth
              multiline
              rows={4}
              placeholder={`Transfer to ${toAgent} when the customer:\n- Asks about [specific topic or service]\n- Expresses [intent or need]\n- Mentions [keywords or phrases]`}
              helperText={
                <span>
                  This condition will be injected into <strong>{fromAgent}</strong>'s system prompt to guide when to transfer to{' '}
                  <strong>{toAgent}</strong>
                  {targetAgent?.description && (
                    <span style={{ color: '#64748b' }}>
                      {' '}({targetAgent.description})
                    </span>
                  )}
                </span>
              }
              sx={{ '& .MuiOutlinedInput-root': { fontFamily: 'monospace', fontSize: 13 } }}
            />

            {/* Runtime prompt preview */}
            <Paper variant="outlined" sx={{ mt: 1.5, p: 1.5, borderRadius: '12px', bgcolor: '#f8fafc' }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Stack direction="row" alignItems="center" spacing={0.75}>
                  <Typography variant="caption" color="text.secondary">
                    <strong style={{ color: '#1976d2' }}>{fromAgent}</strong>'s Runtime System Prompt
                  </Typography>
                  <Chip
                    label="Source Agent"
                    size="small"
                    color="primary"
                    sx={{ height: 18, fontSize: 9, fontWeight: 600 }}
                  />
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                  (auto-focused on handoff instructions)
                </Typography>
              </Stack>
              <Box
                sx={{
                  maxHeight: '200px',
                  overflowY: 'auto',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  p: 1.5,
                  backgroundColor: '#fafafa',
                }}
              >
                <Typography
                  component="div"
                  variant="caption"
                  sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap', fontSize: 11, lineHeight: 1.6 }}
                >
                  <HighlightedPromptPreview previewData={runtimePromptPreview} targetAgent={toAgent} />
                </Typography>
              </Box>
            </Paper>
          </Box>

          <Divider />

          {/* Type and context options */}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            {/* Handoff Type */}
            <FormControl size="small" sx={{ minWidth: 200 }}>
              <InputLabel>Handoff Type</InputLabel>
              <Select value={type} onChange={(e) => setType(e.target.value)} label="Handoff Type">
                <MenuItem value="announced">
                  <Stack direction="row" alignItems="center" gap={1}>
                    <VolumeUpIcon fontSize="small" sx={{ color: '#8b5cf6' }} />
                    Announced
                  </Stack>
                </MenuItem>
                <MenuItem value="discrete">
                  <Stack direction="row" alignItems="center" gap={1}>
                    <VolumeOffIcon fontSize="small" sx={{ color: '#f59e0b' }} />
                    Discrete (silent)
                  </Stack>
                </MenuItem>
              </Select>
            </FormControl>

            {/* Share Context Toggle */}
            <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, flex: 1 }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>Share Context</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Pass conversation history
                  </Typography>
                </Box>
                <Chip
                  label={shareContext ? 'Yes' : 'No'}
                  color={shareContext ? 'success' : 'default'}
                  onClick={() => setShareContext(!shareContext)}
                  sx={{ cursor: 'pointer' }}
                />
              </Stack>
            </Paper>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ justifyContent: 'space-between', px: 2, py: 1.5 }}>
        <Button
          color="error"
          startIcon={<DeleteIcon />}
          onClick={() => {
            onDelete(handoff.from_agent, handoff.to_agent);
            onClose();
          }}
        >
          Delete
        </Button>
        <Box>
          <Button onClick={onClose} sx={{ mr: 1 }}>Cancel</Button>
          <Tooltip 
            title={!isValidHandoff ? "Source and target must be different agents" : isDuplicateHandoff ? "This handoff already exists" : ""}
            arrow
          >
            <span>
              <Button 
                variant="contained" 
                onClick={handleSave}
                disabled={!isValidHandoff || isDuplicateHandoff}
              >
                Save Changes
              </Button>
            </span>
          </Tooltip>
        </Box>
      </DialogActions>
    </Dialog>
  );
});

// ═══════════════════════════════════════════════════════════════════════════════
// GRAPH CANVAS COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

const ScenarioGraphCanvas = React.memo(function ScenarioGraphCanvas({
  agents,
  config,
  onConfigChange,
  onCreateAgent,
  onViewAgentDetails,
}) {
  const containerRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [connectingFrom, setConnectingFrom] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const [nodePositions, setNodePositions] = useState({});
  const [dragging, setDragging] = useState(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [draggingAgent, setDraggingAgent] = useState(null);
  const [showHandoffEditor, setShowHandoffEditor] = useState(false);

  // Canvas panning state
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  // Handle Escape key to cancel connection mode
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && connectingFrom) {
        setConnectingFrom(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [connectingFrom]);

  // Track container dimensions
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setDimensions({ width: rect.width || 800, height: rect.height || 500 });
      }
    };
    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  // Get agents that are part of the scenario
  const scenarioAgents = useMemo(() => {
    const agentSet = new Set();
    if (config.start_agent) agentSet.add(config.start_agent);
    (config.handoffs || []).forEach(h => {
      agentSet.add(h.from_agent);
      agentSet.add(h.to_agent);
    });
    return Array.from(agentSet);
  }, [config]);

  // Calculate base node layout (without user-dragged positions)
  // This only recalculates when the graph structure changes, NOT during drag
  const baseNodeLayout = useMemo(() => {
    if (scenarioAgents.length === 0) return [];
    
    // Build adjacency for layout
    const children = {};
    scenarioAgents.forEach(a => { children[a] = []; });
    (config.handoffs || []).forEach(h => {
      if (children[h.from_agent]) {
        children[h.from_agent].push(h.to_agent);
      }
    });

    // BFS to assign levels
    const levels = {};
    const visited = new Set();
    const queue = config.start_agent ? [config.start_agent] : [];
    let level = 0;
    
    while (queue.length > 0) {
      const levelSize = queue.length;
      for (let i = 0; i < levelSize; i++) {
        const node = queue.shift();
        if (visited.has(node)) continue;
        visited.add(node);
        levels[node] = level;
        (children[node] || []).forEach(child => {
          if (!visited.has(child)) queue.push(child);
        });
      }
      level++;
    }

    // Add unvisited nodes
    scenarioAgents.forEach(a => {
      if (!visited.has(a)) {
        levels[a] = level;
        level++;
      }
    });

    // Group by level
    const levelGroups = {};
    Object.entries(levels).forEach(([agent, lvl]) => {
      if (!levelGroups[lvl]) levelGroups[lvl] = [];
      levelGroups[lvl].push(agent);
    });

    // Calculate positions - larger nodes for better readability
    const nodeWidth = 180;
    const nodeHeight = 90;
    const horizontalGap = 80;
    const verticalGap = 120;
    const result = [];

    Object.entries(levelGroups).forEach(([lvl, agentsInLevel]) => {
      const y = 80 + parseInt(lvl) * (nodeHeight + verticalGap);
      const totalWidth = agentsInLevel.length * nodeWidth + (agentsInLevel.length - 1) * horizontalGap;
      const startX = (dimensions.width - totalWidth) / 2;

      agentsInLevel.forEach((agentName, idx) => {
        const agent = agents.find(a => a.name === agentName);
        const x = startX + idx * (nodeWidth + horizontalGap);
        
        // Check if node has any connections (is it floating?)
        const hasIncoming = (config.handoffs || []).some(h => h.to_agent === agentName);
        const hasOutgoing = (config.handoffs || []).some(h => h.from_agent === agentName);
        const isStartAgent = agentName === config.start_agent;
        const isFloating = !isStartAgent && !hasIncoming;
        
        result.push({
          id: agentName,
          name: agentName,
          baseX: x,
          baseY: y,
          width: nodeWidth,
          height: nodeHeight,
          isStart: isStartAgent,
          isFloating,
          hasOutgoing,
          agent,
        });
      });
    });

    return result;
  }, [scenarioAgents, config, agents, dimensions.width]);

  // Merge base layout with user-dragged positions (fast - only recalculates on position change)
  const nodes = useMemo(() => {
    return baseNodeLayout.map(node => ({
      ...node,
      x: nodePositions[node.id]?.x ?? node.baseX,
      y: nodePositions[node.id]?.y ?? node.baseY,
    }));
  }, [baseNodeLayout, nodePositions]);

  // Create edges from handoffs
  const edges = useMemo(() => {
    const handoffList = config.handoffs || [];
    return handoffList.map((h) => {
      const fromNode = nodes.find(n => n.id === h.from_agent);
      const toNode = nodes.find(n => n.id === h.to_agent);
      if (!fromNode || !toNode) return null;
      
      // Check for bidirectional (both A->B and B->A exist)
      const hasReverseEdge = handoffList.some(
        other => other.from_agent === h.to_agent && other.to_agent === h.from_agent
      );
      
      // Determine if this goes "upward" in the tree (from lower node to higher node)
      const isUpward = fromNode.y > toNode.y;
      
      // For bidirectional edges, offset them horizontally to avoid overlap
      const xOffset = hasReverseEdge ? (isUpward ? -30 : 30) : 0;
      
      // Arrow offset so arrows don't get hidden behind nodes
      const arrowOffset = 15;
      
      // Calculate start and end points based on direction
      let fromX, fromY, toX, toY;
      
      if (isUpward) {
        // Edge goes upward: start from TOP of source, end at BOTTOM of target
        fromX = fromNode.x + fromNode.width / 2 + xOffset;
        fromY = fromNode.y; // Top of source node
        toX = toNode.x + toNode.width / 2 + xOffset;
        toY = toNode.y + toNode.height + arrowOffset; // Below target node
      } else {
        // Edge goes downward: start from BOTTOM of source, end at TOP of target
        fromX = fromNode.x + fromNode.width / 2 + xOffset;
        fromY = fromNode.y + fromNode.height; // Bottom of source node
        toX = toNode.x + toNode.width / 2 + xOffset;
        toY = toNode.y - arrowOffset; // Above target node
      }
      
      return {
        id: `${h.from_agent}->${h.to_agent}`,
        from: h.from_agent,
        to: h.to_agent,
        type: h.type || 'announced',
        isBidirectional: hasReverseEdge,
        isUpward,
        fromX,
        fromY,
        toX,
        toY,
        handoff: h,
      };
    }).filter(Boolean);
  }, [config.handoffs, nodes]);

  // Handle node click
  const handleNodeClick = useCallback((nodeId, e) => {
    e.stopPropagation();
    // Complete connection if we're connecting
    if (connectingFrom && connectingFrom !== nodeId) {
      onConfigChange(prev => {
        const exists = prev.handoffs?.some(
          h => h.from_agent === connectingFrom && h.to_agent === nodeId
        );
        if (exists) return prev;
        
        return {
          ...prev,
          handoffs: [...(prev.handoffs || []), {
            from_agent: connectingFrom,
            to_agent: nodeId,
            tool: 'handoff_to_agent',
            type: prev.handoff_type || 'announced',
            share_context: true,
            handoff_condition: '',
            context_vars: {},
          }],
        };
      });
      setConnectingFrom(null);
      return;
    }
    // Just select/deselect when clicking node body
    setSelectedNode(nodeId === selectedNode ? null : nodeId);
    setSelectedEdge(null);
  }, [selectedNode, connectingFrom, onConfigChange]);

  // Handle edge click - open handoff editor
  const handleEdgeClick = useCallback((edge, e) => {
    e.stopPropagation();
    setSelectedEdge(edge);
    setSelectedNode(null);
    setShowHandoffEditor(true);
  }, []);

  // Handle canvas click (deselect)
  const handleCanvasClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
    setConnectingFrom(null);
  }, []);

  // Handle canvas mouse down for panning
  const handleCanvasMouseDown = useCallback((e) => {
    // Only start panning if clicking on canvas background (not a node)
    if (e.target === e.currentTarget || e.target.tagName === 'svg') {
      setIsPanning(true);
      setPanStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
    }
  }, [panOffset]);

  // Reset pan to center
  const handleResetPan = useCallback(() => {
    setPanOffset({ x: 0, y: 0 });
  }, []);

  // Start connecting from a node's output port (bottom) - now uses click for easier interaction
  const handleOutputPortClick = useCallback((nodeId, e) => {
    e.stopPropagation();
    e.preventDefault();
    // Toggle connection mode
    if (connectingFrom === nodeId) {
      setConnectingFrom(null);
    } else {
      setConnectingFrom(nodeId);
      const rect = containerRef.current?.getBoundingClientRect();
      if (rect) {
        setMousePos({
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
        });
      }
    }
  }, [connectingFrom]);

  // Delete handoff
  const handleDeleteHandoff = useCallback((fromAgent, toAgent) => {
    onConfigChange(prev => ({
      ...prev,
      handoffs: (prev.handoffs || []).filter(
        h => !(h.from_agent === fromAgent && h.to_agent === toAgent)
      ),
    }));
    setSelectedEdge(null);
  }, [onConfigChange]);

  // Update handoff (from editor)
  const handleUpdateHandoff = useCallback((updatedHandoff) => {
    // Check if agents were changed (using _original_from/_original_to markers)
    const originalFrom = updatedHandoff._original_from || updatedHandoff.from_agent;
    const originalTo = updatedHandoff._original_to || updatedHandoff.to_agent;
    const agentsChanged = originalFrom !== updatedHandoff.from_agent || originalTo !== updatedHandoff.to_agent;
    
    // Clean up the internal markers before saving
    const cleanHandoff = { ...updatedHandoff };
    delete cleanHandoff._original_from;
    delete cleanHandoff._original_to;
    
    onConfigChange(prev => {
      let newHandoffs;
      
      if (agentsChanged) {
        // Remove the old handoff and add the new one
        newHandoffs = (prev.handoffs || []).filter(
          h => !(h.from_agent === originalFrom && h.to_agent === originalTo)
        );
        newHandoffs.push(cleanHandoff);
      } else {
        // Just update in place
        newHandoffs = (prev.handoffs || []).map(h => 
          h.from_agent === cleanHandoff.from_agent && h.to_agent === cleanHandoff.to_agent
            ? cleanHandoff
            : h
        );
      }
      
      return {
        ...prev,
        handoffs: newHandoffs,
      };
    });
  }, [onConfigChange]);

  // Remove node from scenario
  const handleRemoveNode = useCallback((nodeId) => {
    onConfigChange(prev => {
      const newHandoffs = (prev.handoffs || []).filter(
        h => h.from_agent !== nodeId && h.to_agent !== nodeId
      );
      return {
        ...prev,
        start_agent: prev.start_agent === nodeId ? null : prev.start_agent,
        handoffs: newHandoffs,
      };
    });
    setSelectedNode(null);
  }, [onConfigChange]);

  // Set as start agent
  const handleSetStart = useCallback((nodeId) => {
    onConfigChange(prev => ({
      ...prev,
      start_agent: nodeId,
    }));
  }, [onConfigChange]);

  // Add agent to scenario (from sidebar click)
  const handleAddAgent = useCallback((agentName) => {
    const isFirst = scenarioAgents.length === 0;
    if (isFirst) {
      onConfigChange(prev => ({
        ...prev,
        start_agent: agentName,
      }));
    }
    // For non-first agents, they need to be connected - add to canvas as floating (invalid)
    // and let user connect them
    if (!isFirst && !scenarioAgents.includes(agentName)) {
      // Add a placeholder handoff that will show the node as floating/invalid
      // Actually, just clicking starts a connection from selected node
      if (selectedNode) {
        onConfigChange(prev => ({
          ...prev,
          handoffs: [...(prev.handoffs || []), {
            from_agent: selectedNode,
            to_agent: agentName,
            tool: 'handoff_to_agent',
            type: prev.handoff_type || 'announced',
            share_context: true,
            handoff_condition: '',
            context_vars: {},
          }],
        }));
      }
    }
    setSelectedNode(agentName);
  }, [scenarioAgents, selectedNode, onConfigChange]);

  // Handle agent drag from sidebar
  const handleAgentDragStart = useCallback((agentName, e) => {
    setDraggingAgent(agentName);
    e.dataTransfer.setData('text/plain', agentName);
    e.dataTransfer.effectAllowed = 'copy';
  }, []);

  const handleCanvasDrop = useCallback((e) => {
    e.preventDefault();
    const agentName = e.dataTransfer.getData('text/plain');
    if (!agentName || !containerRef.current) return;
    
    const rect = containerRef.current.getBoundingClientRect();
    const dropX = e.clientX - rect.left - 70 - panOffset.x; // Center the node, account for pan
    const dropY = e.clientY - rect.top - 30 - panOffset.y;
    
    // Save the drop position
    setNodePositions(prev => ({
      ...prev,
      [agentName]: { x: dropX, y: dropY },
    }));
    
    // Add agent to scenario
    const isFirst = scenarioAgents.length === 0;
    if (isFirst) {
      onConfigChange(prev => ({
        ...prev,
        start_agent: agentName,
      }));
    }
    // If not first and has a selected node, create connection
    else if (selectedNode && !scenarioAgents.includes(agentName)) {
      onConfigChange(prev => ({
        ...prev,
        handoffs: [...(prev.handoffs || []), {
          from_agent: selectedNode,
          to_agent: agentName,
          tool: 'handoff_to_agent',
          type: prev.handoff_type || 'announced',
          share_context: true,
          handoff_condition: '',
          context_vars: {},
        }],
      }));
    }
    // If dropping without connection, just add to scenario (will be floating/invalid)
    else if (!scenarioAgents.includes(agentName)) {
      // Force add by creating a self-reference that we'll clean up
      // Actually, we need to add to scenario agents - simplest is to make it start agent temporarily
      // But that would break flow. Instead, we mark it as needing connection
      onConfigChange(prev => {
        // Add as handoff target from start agent if exists
        if (prev.start_agent && prev.start_agent !== agentName) {
          return {
            ...prev,
            handoffs: [...(prev.handoffs || []), {
              from_agent: prev.start_agent,
              to_agent: agentName,
              tool: 'handoff_to_agent',
              type: prev.handoff_type || 'announced',
              share_context: true,
              handoff_condition: '',
              context_vars: {},
            }],
          };
        }
        // No start agent, make this the start
        return { ...prev, start_agent: agentName };
      });
    }
    
    setDraggingAgent(null);
    setSelectedNode(agentName);
  }, [scenarioAgents, selectedNode, onConfigChange, panOffset]);

  const handleCanvasDragOver = useCallback((e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  // Node drag handlers
  const handleNodeMouseDown = useCallback((nodeId, e) => {
    e.stopPropagation();
    // Don't start drag if connecting
    if (connectingFrom) return;
    const node = nodes.find(n => n.id === nodeId);
    if (node && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setDragging(nodeId);
      setDragOffset({
        x: e.clientX - rect.left - panOffset.x - node.x,
        y: e.clientY - rect.top - panOffset.y - node.y,
      });
    }
  }, [nodes, connectingFrom, panOffset]);

  const handleMouseMove = useCallback((e) => {
    // Handle canvas panning
    if (isPanning && !dragging && !connectingFrom) {
      const newX = e.clientX - panStart.x;
      const newY = e.clientY - panStart.y;
      setPanOffset({ x: newX, y: newY });
      return;
    }
    // Update mouse position for connection line preview
    if (connectingFrom && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setMousePos({
        x: e.clientX - rect.left - panOffset.x,
        y: e.clientY - rect.top - panOffset.y,
      });
    }
    // Handle node dragging
    if (dragging && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const newX = e.clientX - rect.left - dragOffset.x - panOffset.x;
      const newY = e.clientY - rect.top - dragOffset.y - panOffset.y;
      setNodePositions(prev => ({
        ...prev,
        [dragging]: { x: newX, y: newY },
      }));
    }
  }, [connectingFrom, dragging, dragOffset, isPanning, panStart, panOffset]);

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    setIsPanning(false);
    // Don't clear connectingFrom here - let node click or canvas click handle it
  }, []);

  // Get color scheme for node
  const getNodeColors = (node) => {
    if (selectedNode === node.id || connectingFrom === node.id) return colors.selected;
    if (node.isFloating) return colors.invalid; // Floating nodes are invalid
    if (node.isStart) return colors.start;
    if (node.isSession) return colors.session;
    return colors.active;
  };

  // Build initials
  const buildInitials = (name) => {
    const parts = name.split(/[\s_-]+/).filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  };

  // Available agents not in scenario
  const availableAgents = agents.filter(a => !scenarioAgents.includes(a.name));

  return (
    <Box sx={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Sidebar - Available Agents */}
      <Box
        sx={{
          width: 200,
          minWidth: 200,
          borderRight: '1px solid #e5e7eb',
          backgroundColor: '#fafbfc',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {onCreateAgent && (
          <Box sx={{ p: 1.5, borderBottom: '1px solid #e5e7eb' }}>
            <Button
              variant="outlined"
              size="small"
              fullWidth
              startIcon={<PersonAddIcon />}
              onClick={onCreateAgent}
              sx={{
                py: 1,
                borderStyle: 'dashed',
                borderColor: colors.session.border,
                color: colors.session.avatar,
                fontWeight: 600,
                fontSize: 12,
              }}
            >
              Create New Agent
            </Button>
          </Box>
        )}

        <Box sx={{ p: 1.5, borderBottom: '1px solid #e5e7eb', backgroundColor: '#fff' }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <AddIcon fontSize="small" sx={{ color: '#6366f1' }} />
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Add to Flow
            </Typography>
          </Stack>
          <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mt: 0.5 }}>
            Drag to canvas or click to add
          </Typography>
        </Box>

        <Box sx={{ flex: 1, overflowY: 'auto', p: 1 }}>
          {availableAgents.map(agent => {
            const colorScheme = colors.active;
            return (
              <Paper
                key={agent.name}
                elevation={0}
                draggable
                onDragStart={(e) => handleAgentDragStart(agent.name, e)}
                onDragEnd={() => setDraggingAgent(null)}
                onClick={() => handleAddAgent(agent.name)}
                sx={{
                  mb: 1,
                  p: 1.25,
                  cursor: 'grab',
                  background: draggingAgent === agent.name ? colors.selected.bg : colorScheme.bg,
                  border: `2px solid ${draggingAgent === agent.name ? colors.selected.border : colorScheme.border}`,
                  borderRadius: '12px',
                  transition: 'all 0.2s ease',
                  opacity: draggingAgent === agent.name ? 0.5 : 1,
                  '&:hover': {
                    transform: 'translateY(-2px)',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
                  },
                  '&:active': {
                    cursor: 'grabbing',
                  },
                }}
              >
                <Stack direction="row" alignItems="center" spacing={1}>
                  <DragIndicatorIcon sx={{ fontSize: 16, color: '#94a3b8', mr: -0.5 }} />
                  <Avatar
                    sx={{
                      width: 28,
                      height: 28,
                      bgcolor: colorScheme.avatar,
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    {agent.name?.[0] || 'A'}
                  </Avatar>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 600,
                        fontSize: 12,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {agent.name}
                    </Typography>
                  </Box>
                  <Tooltip title="View details">
                    <IconButton
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewAgentDetails?.(agent);
                      }}
                      sx={{ p: 0.5 }}
                    >
                      <SettingsIcon sx={{ fontSize: 14, color: '#94a3b8' }} />
                    </IconButton>
                  </Tooltip>
                </Stack>
              </Paper>
            );
          })}

          {availableAgents.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4, color: '#94a3b8' }}>
              <Typography variant="caption">All agents added</Typography>
            </Box>
          )}
        </Box>
      </Box>

      {/* Graph Canvas */}
      <Box
        ref={containerRef}
        onClick={handleCanvasClick}
        onMouseDown={handleCanvasMouseDown}
        onDrop={handleCanvasDrop}
        onDragOver={handleCanvasDragOver}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        sx={{
          flex: 1,
          position: 'relative',
          backgroundColor: '#f8fafc',
          backgroundImage: 'radial-gradient(circle, #d1d5db 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          backgroundPosition: `${panOffset.x}px ${panOffset.y}px`,
          overflow: 'hidden',
          cursor: isPanning ? 'grabbing' : (dragging ? 'grabbing' : 'grab'),
        }}
      >
        {/* Pannable content container - oversized to prevent edge clipping */}
        <Box
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            transform: `translate(${panOffset.x}px, ${panOffset.y}px)`,
            pointerEvents: 'none',
          }}
        >
        <svg
          style={{ 
            position: 'absolute', 
            // Large negative margins create space for edges that extend beyond nodes
            top: '-1000px', 
            left: '-1000px', 
            width: 'calc(100% + 2000px)', 
            height: 'calc(100% + 2000px)', 
            pointerEvents: 'none', 
          }}
        >
          {/* Translate SVG content to match the offset */}
          <g transform="translate(1000, 1000)">
          <defs>
            {/* Forward edge arrows */}
            <marker id="arrowhead-announced" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#8b5cf6" />
            </marker>
            <marker id="arrowhead-discrete" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#f59e0b" />
            </marker>
            {/* Reverse edge arrows - teal color */}
            <marker id="arrowhead-reverse-announced" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#14b8a6" />
            </marker>
            <marker id="arrowhead-reverse-discrete" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#0d9488" />
            </marker>
          </defs>

          {/* Edges */}
          {edges.map(edge => {
            const midY = (edge.fromY + edge.toY) / 2;
            const isAnnounced = edge.type === 'announced';
            const isSelected = selectedEdge?.id === edge.id;
            const isBidirectional = edge.isBidirectional;
            
            // Color scheme: forward=purple, bidirectional=teal, discrete=dashed
            const getEdgeColor = () => {
              if (isSelected) return '#3b82f6';
              if (isBidirectional) return isAnnounced ? '#14b8a6' : '#0d9488';
              return isAnnounced ? '#8b5cf6' : '#f59e0b';
            };
            const edgeColor = getEdgeColor();
            const markerType = isBidirectional ? `reverse-${edge.type}` : edge.type;
            
            // Label text
            const labelText = isBidirectional ? '↔ handoff' : 'handoff';
            const labelWidth = isBidirectional ? 90 : 80;
            
            return (
              <g key={edge.id} style={{ cursor: 'pointer', pointerEvents: 'auto' }} onClick={(e) => handleEdgeClick(edge, e)}>
                {/* Invisible wider path for easier clicking */}
                <path
                  d={`M ${edge.fromX} ${edge.fromY} C ${edge.fromX} ${midY}, ${edge.toX} ${midY}, ${edge.toX} ${edge.toY}`}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={14}
                />
                {/* Visible path */}
                <path
                  d={`M ${edge.fromX} ${edge.fromY} C ${edge.fromX} ${midY}, ${edge.toX} ${midY}, ${edge.toX} ${edge.toY}`}
                  fill="none"
                  stroke={edgeColor}
                  strokeWidth={isSelected ? 3 : 2}
                  markerEnd={`url(#arrowhead-${markerType})`}
                  strokeDasharray={isAnnounced ? '0' : '6,4'}
                />
                {/* Edge label - click to edit */}
                <g transform={`translate(${(edge.fromX + edge.toX) / 2}, ${midY})`}>
                  <rect
                    x={-labelWidth/2}
                    y="-14"
                    width={labelWidth}
                    height="28"
                    rx="14"
                    fill={isSelected ? '#dbeafe' : (isBidirectional ? '#f0fdfa' : 'white')}
                    stroke={edgeColor}
                    strokeWidth={isSelected ? 2 : 1}
                  />
                  <text textAnchor="middle" dy="5" fontSize="11" fill={edgeColor} fontWeight="600">
                    {isAnnounced ? '🔊' : '🔇'} {labelText}
                  </text>
                </g>
              </g>
            );
          })}

          {/* Connecting line preview - follows mouse */}
          {connectingFrom && (() => {
            const fromNode = nodes.find(n => n.id === connectingFrom);
            if (!fromNode) return null;
            const fromX = fromNode.x + fromNode.width / 2;
            const fromY = fromNode.y + fromNode.height;
            const midY = (fromY + mousePos.y) / 2;
            return (
              <path
                d={`M ${fromX} ${fromY} C ${fromX} ${midY}, ${mousePos.x} ${midY}, ${mousePos.x} ${mousePos.y}`}
                fill="none"
                stroke="#3b82f6"
                strokeWidth={2}
                strokeDasharray="5,5"
                opacity={0.7}
                style={{ pointerEvents: 'none' }}
              />
            );
          })()}
          </g>
        </svg>

        {/* Nodes */}
        {nodes.map(node => {
          const nodeColors = getNodeColors(node);
          const isConnectTarget = connectingFrom && connectingFrom !== node.id;
          return (
            <Box
              key={node.id}
              sx={{
                position: 'absolute',
                left: node.x,
                top: node.y,
                width: node.width,
                zIndex: dragging === node.id ? 100 : 1,
                pointerEvents: 'auto',
              }}
            >
              {/* Floating/Invalid warning */}
              {node.isFloating && (
                <Tooltip title="This agent needs an incoming connection. Drag from another agent's output port to connect.">
                  <Box
                    sx={{
                      position: 'absolute',
                      top: -24,
                      left: '50%',
                      transform: 'translateX(-50%)',
                      backgroundColor: '#fef2f2',
                      border: '1px solid #fca5a5',
                      borderRadius: '8px',
                      px: 1,
                      py: 0.25,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.5,
                      whiteSpace: 'nowrap',
                      zIndex: 20,
                    }}
                  >
                    <Typography variant="caption" sx={{ color: '#dc2626', fontWeight: 600, fontSize: 9 }}>
                      ⚠️ Needs connection
                    </Typography>
                  </Box>
                </Tooltip>
              )}

              {/* Node Body */}
              <Paper
                elevation={selectedNode === node.id ? 4 : (isConnectTarget ? 3 : 1)}
                onClick={(e) => handleNodeClick(node.id, e)}
                onMouseDown={(e) => handleNodeMouseDown(node.id, e)}
                sx={{
                  height: node.height,
                  background: isConnectTarget ? '#dbeafe' : nodeColors.bg,
                  border: `2px solid ${isConnectTarget ? '#3b82f6' : nodeColors.border}`,
                  borderRadius: '12px',
                  cursor: dragging === node.id ? 'grabbing' : (isConnectTarget ? 'pointer' : 'grab'),
                  transition: 'all 0.2s ease',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  userSelect: 'none',
                  position: 'relative',
                  animation: isConnectTarget ? 'targetPulse 1.5s infinite' : 'none',
                  '@keyframes targetPulse': {
                    '0%, 100%': { boxShadow: '0 0 0 0 rgba(59, 130, 246, 0.4)' },
                    '50%': { boxShadow: '0 0 0 8px rgba(59, 130, 246, 0)' },
                  },
                  '&:hover': isConnectTarget ? {
                    transform: 'scale(1.05)',
                    boxShadow: '0 4px 20px rgba(59, 130, 246, 0.4)',
                  } : {},
                }}
              >
                {/* Details button */}
                <Tooltip title="View agent details">
                  <IconButton
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      onViewAgentDetails?.(node.agent);
                    }}
                    sx={{
                      position: 'absolute',
                      top: 4,
                      right: 4,
                      p: 0.5,
                      opacity: 0.5,
                      '&:hover': { opacity: 1, backgroundColor: 'rgba(0,0,0,0.08)' },
                    }}
                  >
                    <SettingsIcon sx={{ fontSize: 16 }} />
                  </IconButton>
                </Tooltip>

                {node.isStart && (
                  <Chip
                    icon={<PlayArrowIcon sx={{ fontSize: 14 }} />}
                    label="START"
                    size="small"
                    sx={{
                      position: 'absolute',
                      top: -14,
                      left: '50%',
                      transform: 'translateX(-50%)',
                      height: 24,
                      fontSize: 11,
                      fontWeight: 700,
                      backgroundColor: '#10b981',
                      color: 'white',
                      '& .MuiChip-icon': { color: 'white' },
                    }}
                  />
                )}
                <Avatar
                  sx={{
                    width: 40,
                    height: 40,
                    bgcolor: nodeColors.avatar,
                    fontSize: 14,
                    fontWeight: 700,
                    mb: 0.5,
                  }}
                >
                  {buildInitials(node.name)}
                </Avatar>
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: 600,
                    color: nodeColors.text,
                    textAlign: 'center',
                    px: 1,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: '100%',
                    fontSize: 13,
                    lineHeight: 1.2,
                  }}
                >
                  {node.name}
                </Typography>
                {node.agent?.description && (
                  <Typography
                    variant="caption"
                    sx={{
                      color: 'text.secondary',
                      textAlign: 'center',
                      px: 1,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: '100%',
                      fontSize: 10,
                      opacity: 0.8,
                    }}
                  >
                    {node.agent.description.length > 25 
                      ? node.agent.description.slice(0, 25) + '...' 
                      : node.agent.description}
                  </Typography>
                )}
              </Paper>

              {/* Output Port (bottom) - click to start connection */}
              {/* Hide when another node is in connecting mode (unless this is the source) */}
              {(!connectingFrom || connectingFrom === node.id) && (
                <Tooltip 
                  title={connectingFrom === node.id ? 'Click to cancel' : 'Click to connect to another agent'}
                  arrow
                  placement="bottom"
                >
                  <Box
                    onClick={(e) => handleOutputPortClick(node.id, e)}
                    sx={{
                      position: 'absolute',
                      bottom: -10,
                      left: '50%',
                      transform: 'translateX(-50%)',
                      width: connectingFrom === node.id ? 24 : 20,
                      height: connectingFrom === node.id ? 24 : 20,
                      borderRadius: '50%',
                      backgroundColor: connectingFrom === node.id ? '#3b82f6' : '#6366f1',
                      border: `2px solid ${connectingFrom === node.id ? '#1d4ed8' : '#4f46e5'}`,
                      cursor: 'pointer',
                      zIndex: 10,
                      transition: 'all 0.15s ease',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: connectingFrom === node.id ? '0 0 12px rgba(59, 130, 246, 0.6)' : 'none',
                      animation: connectingFrom === node.id ? 'activePulse 1s infinite' : 'none',
                      '@keyframes activePulse': {
                        '0%, 100%': { boxShadow: '0 0 0 0 rgba(59, 130, 246, 0.6)' },
                        '50%': { boxShadow: '0 0 0 6px rgba(59, 130, 246, 0)' },
                      },
                      '&:hover': {
                        transform: 'translateX(-50%) scale(1.2)',
                        boxShadow: '0 0 12px rgba(99, 102, 241, 0.6)',
                      },
                    }}
                  >
                    {connectingFrom === node.id ? (
                      <CloseIcon sx={{ fontSize: 12, color: 'white' }} />
                    ) : (
                      <AddIcon sx={{ fontSize: 12, color: 'white' }} />
                    )}
                  </Box>
                </Tooltip>
              )}
            </Box>
          );
        })}
        </Box>{/* End of pannable content container */}

        {/* Connection Mode Banner */}
        {connectingFrom && (
          <Box
            sx={{
              position: 'absolute',
              top: 12,
              left: '50%',
              transform: 'translateX(-50%)',
              backgroundColor: '#3b82f6',
              color: 'white',
              px: 2.5,
              py: 1,
              borderRadius: '20px',
              display: 'flex',
              alignItems: 'center',
              gap: 1.5,
              boxShadow: '0 4px 12px rgba(59, 130, 246, 0.4)',
              zIndex: 100,
              animation: 'fadeIn 0.2s ease',
              '@keyframes fadeIn': {
                from: { opacity: 0, transform: 'translateX(-50%) translateY(-10px)' },
                to: { opacity: 1, transform: 'translateX(-50%) translateY(0)' },
              },
            }}
          >
            <LinkIcon sx={{ fontSize: 18 }} />
            <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
              Click any agent to connect from "{connectingFrom}"
            </Typography>
            <Chip
              label="Cancel (Esc)"
              size="small"
              onClick={(e) => { e.stopPropagation(); setConnectingFrom(null); }}
              sx={{
                height: 24,
                fontSize: 11,
                backgroundColor: 'rgba(255,255,255,0.2)',
                color: 'white',
                cursor: 'pointer',
                '&:hover': { backgroundColor: 'rgba(255,255,255,0.3)' },
              }}
            />
          </Box>
        )}

        {/* Empty state */}
        {nodes.length === 0 && (
          <Box
            sx={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              textAlign: 'center',
              color: '#94a3b8',
              pointerEvents: 'none',
            }}
          >
            <SmartToyIcon sx={{ fontSize: 64, opacity: 0.3, mb: 2 }} />
            <Typography variant="h6" sx={{ fontWeight: 600, color: '#64748b' }}>
              Click an agent to start
            </Typography>
            <Typography variant="body2" sx={{ color: '#94a3b8', mt: 1 }}>
              The first agent becomes the starting point
            </Typography>
          </Box>
        )}

        {/* Toolbar */}
        <Box
          sx={{
            position: 'absolute',
            top: 16,
            right: 16,
            display: 'flex',
            gap: 1,
          }}
        >
          {/* Reset pan button - always visible when panned */}
          {(panOffset.x !== 0 || panOffset.y !== 0) && (
            <Tooltip title="Reset pan (center view)">
              <IconButton
                onClick={handleResetPan}
                size="small"
                sx={{
                  backgroundColor: 'white',
                  border: '1px solid #e5e7eb',
                  '&:hover': { backgroundColor: '#f0f9ff' },
                }}
              >
                <GpsFixedIcon fontSize="small" sx={{ color: '#3b82f6' }} />
              </IconButton>
            </Tooltip>
          )}
          {selectedNode && !connectingFrom && (
            <>
              {!nodes.find(n => n.id === selectedNode)?.isStart && (
                <Tooltip title="Set as start agent">
                  <IconButton
                    onClick={() => handleSetStart(selectedNode)}
                    size="small"
                    sx={{
                      backgroundColor: 'white',
                      border: '1px solid #e5e7eb',
                      '&:hover': { backgroundColor: '#ecfdf5' },
                    }}
                  >
                    <PlayArrowIcon fontSize="small" sx={{ color: '#10b981' }} />
                  </IconButton>
                </Tooltip>
              )}
              <Tooltip title="Remove from flow">
                <IconButton
                  onClick={() => handleRemoveNode(selectedNode)}
                  size="small"
                  sx={{
                    backgroundColor: 'white',
                    border: '1px solid #e5e7eb',
                    '&:hover': { backgroundColor: '#fef2f2' },
                  }}
                >
                  <DeleteIcon fontSize="small" sx={{ color: '#ef4444' }} />
                </IconButton>
              </Tooltip>
            </>
          )}
          {connectingFrom && (
            <Tooltip title="Cancel connection">
              <Button
                variant="contained"
                size="small"
                startIcon={<CloseIcon />}
                onClick={() => setConnectingFrom(null)}
                sx={{
                  backgroundColor: '#ef4444',
                  '&:hover': { backgroundColor: '#dc2626' },
                }}
              >
                Cancel
              </Button>
            </Tooltip>
          )}
        </Box>

        {/* Instructions */}
        {connectingFrom && (
          <Box
            sx={{
              position: 'absolute',
              bottom: 16,
              left: '50%',
              transform: 'translateX(-50%)',
              backgroundColor: 'rgba(59, 130, 246, 0.9)',
              color: 'white',
              px: 3,
              py: 1.5,
              borderRadius: '20px',
              fontSize: 13,
              fontWeight: 600,
              boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
            }}
          >
            🎯 Click any agent to connect
          </Box>
        )}

        {/* Help hint when canvas has nodes but no connection in progress */}
        {nodes.length > 0 && !connectingFrom && (
          <Box
            sx={{
              position: 'absolute',
              bottom: 16,
              left: '50%',
              transform: 'translateX(-50%)',
              backgroundColor: 'rgba(100, 116, 139, 0.9)',
              color: 'white',
              px: 2,
              py: 0.75,
              borderRadius: '20px',
              fontSize: 12,
              fontWeight: 500,
              whiteSpace: 'nowrap',
            }}
          >
            <span style={{ marginRight: 6 }}>⊕</span>
            Click "+" to connect
            <span style={{ margin: '0 8px', opacity: 0.5 }}>•</span>
            Drag to pan
          </Box>
        )}
      </Box>

      {/* Right sidebar - Stats & Handoffs */}
      <Box
        sx={{
          width: 180,
          minWidth: 180,
          borderLeft: '1px solid #e5e7eb',
          backgroundColor: '#fff',
          p: 1.5,
          overflowY: 'auto',
        }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
          Scenario Flow
        </Typography>
        
        <Stack spacing={2}>
          <Paper variant="outlined" sx={{ p: 1.5, borderRadius: '10px' }}>
            <Typography variant="caption" color="text.secondary">
              Start Agent
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {config.start_agent || '—'}
            </Typography>
          </Paper>

          <Paper variant="outlined" sx={{ p: 1.5, borderRadius: '10px' }}>
            <Typography variant="caption" color="text.secondary">
              Total Agents
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {scenarioAgents.length}
            </Typography>
          </Paper>

          <Paper variant="outlined" sx={{ p: 1.5, borderRadius: '10px' }}>
            <Typography variant="caption" color="text.secondary">
              Handoff Routes
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {config.handoffs?.length || 0}
            </Typography>
          </Paper>

          {(config.handoffs?.length || 0) > 0 && (
            <>
              <Divider />
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                Connections (click to edit)
              </Typography>
              <Stack spacing={0.5}>
                {config.handoffs.map((h, i) => (
                  <Chip
                    key={i}
                    label={`${h.from_agent} → ${h.to_agent}`}
                    size="small"
                    variant="outlined"
                    icon={h.type === 'announced' ? <VolumeUpIcon /> : <VolumeOffIcon />}
                    onClick={() => {
                      setSelectedEdge({ id: `${h.from_agent}->${h.to_agent}`, handoff: h });
                      setShowHandoffEditor(true);
                    }}
                    onDelete={() => handleDeleteHandoff(h.from_agent, h.to_agent)}
                    sx={{
                      justifyContent: 'flex-start',
                      height: 28,
                      fontSize: 10,
                      cursor: 'pointer',
                      '& .MuiChip-label': { flex: 1 },
                      '&:hover': { backgroundColor: '#f1f5f9' },
                    }}
                  />
                ))}
              </Stack>
            </>
          )}

          {/* Floating agents warning */}
          {nodes.some(n => n.isFloating) && (
            <Paper 
              variant="outlined" 
              sx={{ 
                p: 1.5, 
                borderRadius: '10px', 
                backgroundColor: '#fef2f2',
                borderColor: '#fca5a5',
              }}
            >
              <Typography variant="caption" sx={{ color: '#dc2626', fontWeight: 600 }}>
                ⚠️ Floating Agents
              </Typography>
              <Typography variant="caption" sx={{ display: 'block', color: '#991b1b', mt: 0.5 }}>
                Some agents need incoming connections. Drag from an output port to connect them.
              </Typography>
            </Paper>
          )}
        </Stack>
      </Box>

      {/* Handoff Editor Dialog */}
      <HandoffEditorDialog
        open={showHandoffEditor}
        onClose={() => {
          setShowHandoffEditor(false);
          setSelectedEdge(null);
        }}
        handoff={selectedEdge?.handoff}
        agents={agents}
        scenarioAgents={scenarioAgents}
        handoffs={config.handoffs || []}
        onSave={handleUpdateHandoff}
        onDelete={handleDeleteHandoff}
      />
    </Box>
  );
});

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ScenarioBuilderGraph({
  sessionId,
  onScenarioCreated,
  onScenarioUpdated,
  onEditAgent,
  onCreateAgent,
  existingConfig = null,
  editMode = false,
}) {
  // State
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Data
  const [availableAgents, setAvailableAgents] = useState([]);
  const [availableTemplates, setAvailableTemplates] = useState([]);
  const [sessionScenarios, setSessionScenarios] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);

  // Scenario config
  const [config, setConfig] = useState({
    name: 'Custom Scenario',
    description: '',
    icon: '🎭',
    start_agent: null,
    handoff_type: 'announced',
    handoffs: [],
    global_template_vars: {
      company_name: 'ART Voice Agent',
      industry: 'general',
    },
  });

  // UI state
  const [showSettings, setShowSettings] = useState(false);
  const [viewingAgent, setViewingAgent] = useState(null);
  const [showExportInstructions, setShowExportInstructions] = useState(false);
  const [exportedYaml, setExportedYaml] = useState('');

  // Icon picker state
  const [showIconPicker, setShowIconPicker] = useState(false);
  const iconPickerAnchor = useRef(null);
  const iconOptions = [
    '🎭', '🎯', '🎪', '🏛️', '🏦', '🏥', '🏢', '📞', '💬', '🤖',
    '🎧', '📱', '💼', '🛒', '🍔', '✈️', '🏨', '🚗', '📚', '⚖️',
  ];
  const defaultTemplate = useMemo(() => {
    if (!availableTemplates.length) return null;
    return (
      availableTemplates.find((template) => template.id === 'banking') ||
      availableTemplates.find((template) => template.id === 'default') ||
      availableTemplates[0]
    );
  }, [availableTemplates]);
  const sessionScenarioItems = useMemo(() => {
    if (!defaultTemplate) return sessionScenarios;
    const exists = sessionScenarios.some(
      (scenario) =>
        (scenario.name || '').toLowerCase() === (defaultTemplate.name || '').toLowerCase()
    );
    if (exists) return sessionScenarios;
    return [
      {
        name: defaultTemplate.name,
        description: defaultTemplate.description,
        icon: defaultTemplate.icon,
        start_agent: defaultTemplate.start_agent,
        handoff_type: defaultTemplate.handoff_type,
        handoffs: defaultTemplate.handoffs || [],
        global_template_vars: defaultTemplate.global_template_vars || {},
        is_default_template: true,
      },
      ...sessionScenarios,
    ];
  }, [defaultTemplate, sessionScenarios]);

  // ─────────────────────────────────────────────────────────────────────────
  // DATA FETCHING
  // ─────────────────────────────────────────────────────────────────────────

  const fetchAvailableAgents = useCallback(async () => {
    try {
      const url = sessionId 
        ? `${API_BASE_URL}/api/v1/scenario-builder/agents?session_id=${encodeURIComponent(sessionId)}`
        : `${API_BASE_URL}/api/v1/scenario-builder/agents`;
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        setAvailableAgents(data.agents || []);
      }
    } catch (err) {
      logger.error('Failed to fetch agents:', err);
    }
  }, [sessionId]);

  const fetchAvailableTemplates = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/scenario-builder/templates`);
      if (response.ok) {
        const data = await response.json();
        setAvailableTemplates(data.templates || []);
      }
    } catch (err) {
      logger.error('Failed to fetch templates:', err);
    }
  }, []);

  const fetchSessionScenarios = useCallback(async () => {
    if (!sessionId) {
      setSessionScenarios([]);
      return;
    }
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/scenario-builder/session/${encodeURIComponent(sessionId)}/scenarios`
      );
      if (response.ok) {
        const data = await response.json();
        setSessionScenarios(data.scenarios || []);
      }
    } catch (err) {
      logger.error('Failed to fetch session scenarios:', err);
    }
  }, [sessionId]);

  const fetchExistingScenario = useCallback(async () => {
    if (!sessionId) return;
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/scenario-builder/session/${sessionId}`
      );
      if (response.ok) {
        const data = await response.json();
        if (data.config) {
          setConfig({
            name: data.config.name || 'Custom Scenario',
            description: data.config.description || '',
            icon: data.config.icon || '🎭',
            start_agent: data.config.start_agent,
            handoff_type: data.config.handoff_type || 'announced',
            handoffs: data.config.handoffs || [],
            global_template_vars: data.config.global_template_vars || {},
          });
        }
      }
    } catch (err) {
      void err;
      logger.debug('No existing scenario');
    }
  }, [sessionId]);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchAvailableAgents(),
      fetchAvailableTemplates(),
      fetchSessionScenarios(),
      editMode ? fetchExistingScenario() : Promise.resolve(),
    ]).finally(() => setLoading(false));
  }, [
    fetchAvailableAgents,
    fetchAvailableTemplates,
    fetchSessionScenarios,
    fetchExistingScenario,
    editMode,
  ]);

  useEffect(() => {
    if (existingConfig) {
      setConfig({
        name: existingConfig.name || 'Custom Scenario',
        description: existingConfig.description || '',
        icon: existingConfig.icon || '🎭',
        start_agent: existingConfig.start_agent,
        handoff_type: existingConfig.handoff_type || 'announced',
        handoffs: existingConfig.handoffs || [],
        global_template_vars: existingConfig.global_template_vars || {},
      });
    }
  }, [existingConfig]);

  // ─────────────────────────────────────────────────────────────────────────
  // HANDLERS
  // ─────────────────────────────────────────────────────────────────────────

  const handleApplyTemplate = useCallback(async (templateId) => {
    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/scenario-builder/templates/${templateId}`
      );
      if (response.ok) {
        const data = await response.json();
        const template = data.template;
        setConfig({
          name: template.name || 'Custom Scenario',
          description: template.description || '',
          icon: template.icon || '🎭',
          start_agent: template.start_agent,
          handoff_type: template.handoff_type || 'announced',
          handoffs: template.handoffs || [],
          global_template_vars: template.global_template_vars || {},
        });
        setSelectedTemplate(templateId);
        setSuccess(`Applied template: ${template.name}`);
        setTimeout(() => setSuccess(null), 3000);
      }
    } catch (err) {
      setError('Failed to apply template');
      void err;
    } finally {
      setLoading(false);
    }
  }, []);

  const handleApplySessionScenario = useCallback((scenario, scenarioKey) => {
    if (!scenario) return;
    setConfig({
      name: scenario.name || 'Custom Scenario',
      description: scenario.description || '',
      icon: scenario.icon || '🎭',
      start_agent: scenario.start_agent,
      handoff_type: scenario.handoff_type || 'announced',
      handoffs: scenario.handoffs || [],
      global_template_vars: scenario.global_template_vars || {},
    });
    setSelectedTemplate(scenarioKey || `session:${scenario.name || 'custom'}`);
    setSuccess(`Loaded session scenario: ${scenario.name || 'Custom Scenario'}`);
    setTimeout(() => setSuccess(null), 3000);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    if (!config.start_agent) {
      setError('Please add at least one agent to the flow');
      setSaving(false);
      return;
    }

    try {
      const endpoint = editMode
        ? `${API_BASE_URL}/api/v1/scenario-builder/session/${sessionId}`
        : `${API_BASE_URL}/api/v1/scenario-builder/create?session_id=${sessionId}`;

      const method = editMode ? 'PUT' : 'POST';

      const agentsInGraph = new Set([config.start_agent]);
      config.handoffs.forEach(h => {
        agentsInGraph.add(h.from_agent);
        agentsInGraph.add(h.to_agent);
      });

      const payload = {
        name: config.name,
        description: config.description,
        icon: config.icon,
        agents: Array.from(agentsInGraph),
        start_agent: config.start_agent,
        handoff_type: config.handoff_type,
        handoffs: config.handoffs,
        global_template_vars: config.global_template_vars,
        tools: [],
      };

      const response = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save scenario');
      }

      const data = await response.json();

      if (editMode && onScenarioUpdated) {
        onScenarioUpdated(data.config || config);
      } else if (onScenarioCreated) {
        onScenarioCreated(data.config || config);
      }

      // Refresh data to show saved changes immediately
      fetchSessionScenarios();
      fetchAvailableAgents();
      setSuccess(editMode ? 'Scenario updated!' : 'Scenario created!');
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      logger.error('Failed to save scenario:', err);
      setError(err.message || 'Failed to save scenario');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (sessionId) {
      try {
        await fetch(
          `${API_BASE_URL}/api/v1/scenario-builder/session/${sessionId}`,
          { method: 'DELETE' }
        );
      } catch {
        logger.warn('Failed to clear session scenario');
      }
    }

    setConfig({
      name: 'Custom Scenario',
      description: '',
      icon: '🎭',
      start_agent: null,
      handoff_type: 'announced',
      handoffs: [],
      global_template_vars: {
        company_name: 'ART Voice Agent',
        industry: 'general',
      },
    });
    setSelectedTemplate(null);
    setError(null);
    setSuccess('Scenario reset');
    setTimeout(() => setSuccess(null), 2000);
    fetchSessionScenarios();
  };

  const handleExportScenario = () => {
    // Convert config to YAML format compatible with backend scenariostore
    const scenarioName = config.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_');

    // Get list of agents in the scenario from the canvas
    const agentsInScenario = new Set();
    if (config.start_agent) {
      agentsInScenario.add(config.start_agent);
    }
    config.handoffs.forEach((handoff) => {
      agentsInScenario.add(handoff.from_agent);
      agentsInScenario.add(handoff.to_agent);
    });

    // Build YAML content following orchestration.yaml structure
    const yamlLines = [
      `# ${config.name}`,
      config.description ? `# ${config.description}` : null,
      '',
      `name: ${scenarioName}`,
      `description: ${config.description || config.name}`,
      `icon: "${config.icon}"`,
      '',
      '# Starting agent',
      `start_agent: ${config.start_agent || 'Concierge'}`,
      '',
      '# Agents to include in this scenario',
      'agents:',
    ];

    // Add agents list
    if (agentsInScenario.size > 0) {
      Array.from(agentsInScenario).forEach(agentName => {
        yamlLines.push(`  - ${agentName}`);
      });
    } else {
      yamlLines.push('  []');
    }

    yamlLines.push('');
    yamlLines.push('# Handoff behavior - default for unlisted routes');
    yamlLines.push(`handoff_type: ${config.handoff_type}`);
    yamlLines.push('');
    yamlLines.push('# Handoff Graph - Directed edges between agents');
    yamlLines.push('handoffs:');

    // Build handoffs array (not dictionary)
    if (config.handoffs && config.handoffs.length > 0) {
      config.handoffs.forEach((handoff, index) => {
        if (index > 0) yamlLines.push('');
        yamlLines.push(`  - from: ${handoff.from_agent}`);
        yamlLines.push(`    to: ${handoff.to_agent}`);
        yamlLines.push(`    tool: ${handoff.tool || `handoff_${handoff.to_agent.toLowerCase().replace(/\s+/g, '_')}`}`);
        yamlLines.push(`    type: ${handoff.type || config.handoff_type}`);
        yamlLines.push(`    share_context: ${handoff.share_context !== false}`);

        if (handoff.handoff_condition && handoff.handoff_condition.trim()) {
          yamlLines.push(`    handoff_condition: |`);
          handoff.handoff_condition.split('\n').forEach(line => {
            yamlLines.push(`      ${line}`);
          });
        }

        if (handoff.context_vars && Object.keys(handoff.context_vars).length > 0) {
          yamlLines.push(`    context_vars:`);
          Object.entries(handoff.context_vars).forEach(([key, value]) => {
            yamlLines.push(`      ${key}: ${JSON.stringify(value)}`);
          });
        }
      });
    } else {
      yamlLines.push('  []');
    }

    yamlLines.push('');
    yamlLines.push('# Generic Handoff Configuration');
    yamlLines.push('# Enables the handoff_to_agent tool for dynamic agent transfers');
    yamlLines.push('generic_handoff:');
    yamlLines.push('  enabled: true');
    yamlLines.push(`  default_type: ${config.handoff_type}`);
    yamlLines.push('  share_context: true');
    yamlLines.push('  require_client_id: false');
    yamlLines.push('');
    yamlLines.push('# Agent defaults applied to all agents');
    yamlLines.push('agent_defaults:');
    Object.entries(config.global_template_vars).forEach(([key, value]) => {
      yamlLines.push(`  ${key}: "${value}"`);
    });
    yamlLines.push('');

    const yamlContent = yamlLines.filter(line => line !== null).join('\n');
    setExportedYaml(yamlContent);
    setShowExportInstructions(true);
  };

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
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

      {/* Header */}
      <Box sx={{ p: 2, borderBottom: '1px solid #e5e7eb' }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
          {/* Icon Picker */}
          <Box>
            <Tooltip title="Click to change icon">
              <Button
                ref={iconPickerAnchor}
                variant="outlined"
                onClick={() => setShowIconPicker(true)}
                sx={{
                  minWidth: 56,
                  height: 40,
                  fontSize: '1.5rem',
                  borderColor: '#d1d5db',
                }}
              >
                {config.icon}
              </Button>
            </Tooltip>
            <Popover
              open={showIconPicker}
              anchorEl={iconPickerAnchor.current}
              onClose={() => setShowIconPicker(false)}
              anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
            >
              <Box sx={{ p: 1.5, maxWidth: 280 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                  Choose scenario icon:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {iconOptions.map((emoji) => (
                    <IconButton
                      key={emoji}
                      onClick={() => {
                        setConfig((prev) => ({ ...prev, icon: emoji }));
                        setShowIconPicker(false);
                      }}
                      sx={{
                        fontSize: '1.25rem',
                        width: 36,
                        height: 36,
                        bgcolor: config.icon === emoji ? 'primary.light' : 'transparent',
                      }}
                    >
                      {emoji}
                    </IconButton>
                  ))}
                </Box>
              </Box>
            </Popover>
          </Box>

          <TextField
            label="Scenario Name"
            value={config.name}
            onChange={(e) => setConfig((prev) => ({ ...prev, name: e.target.value }))}
            size="small"
            sx={{ flex: 1, maxWidth: 300 }}
          />
          <TextField
            label="Description"
            value={config.description}
            onChange={(e) => setConfig((prev) => ({ ...prev, description: e.target.value }))}
            size="small"
            sx={{ flex: 2 }}
          />
          <Button
            variant="outlined"
            startIcon={<SettingsIcon />}
            onClick={() => setShowSettings(!showSettings)}
            size="small"
          >
            Settings
          </Button>
        </Stack>

        {/* Templates */}
        <Stack spacing={1.2}>
          <Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
                Session Scenarios
              </Typography>
              <Chip size="small" label={sessionScenarioItems.length} />
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
              Stored in session state. Click to load and edit.
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              {sessionScenarioItems.length > 0 ? (
                sessionScenarioItems.map((scenario, index) => {
                  const scenarioKey = `session:${scenario.name || index}`;
                  return (
                    <Chip
                      key={scenarioKey}
                      label={
                        scenario.is_default_template
                          ? `${scenario.icon || '🎭'} ${scenario.name || 'Default'} (default)`
                          : `${scenario.icon || '🎭'} ${scenario.name || 'Custom Scenario'}`
                      }
                      size="small"
                      icon={
                        selectedTemplate === scenarioKey
                          ? <CheckIcon />
                          : scenario.is_active
                            ? <AutoFixHighIcon fontSize="small" />
                            : <EditIcon fontSize="small" />
                      }
                      color={selectedTemplate === scenarioKey ? 'primary' : 'default'}
                      variant={selectedTemplate === scenarioKey ? 'filled' : 'outlined'}
                      onClick={() => handleApplySessionScenario(scenario, scenarioKey)}
                      sx={{ cursor: 'pointer' }}
                    />
                  );
                })
              ) : (
                <Typography variant="caption" color="text.secondary">
                  {sessionId ? 'No session scenarios yet.' : 'Connect a session to load scenarios.'}
                </Typography>
              )}
            </Stack>
          </Box>
        </Stack>

        {/* Settings panel */}
        <Collapse in={showSettings}>
          <Paper variant="outlined" sx={{ mt: 2, p: 2, borderRadius: '12px' }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <FormControl size="small" sx={{ minWidth: 180 }}>
                <InputLabel>Default Handoff Type</InputLabel>
                <Select
                  value={config.handoff_type}
                  label="Default Handoff Type"
                  onChange={(e) => setConfig((prev) => ({ ...prev, handoff_type: e.target.value }))}
                >
                  <MenuItem value="announced">🔊 Announced</MenuItem>
                  <MenuItem value="discrete">🔇 Discrete</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label="Company Name"
                value={config.global_template_vars.company_name || ''}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    global_template_vars: {
                      ...prev.global_template_vars,
                      company_name: e.target.value,
                    },
                  }))
                }
                size="small"
                sx={{ flex: 1 }}
              />
              <TextField
                label="Industry"
                value={config.global_template_vars.industry || ''}
                onChange={(e) =>
                  setConfig((prev) => ({
                    ...prev,
                    global_template_vars: {
                      ...prev.global_template_vars,
                      industry: e.target.value,
                    },
                  }))
                }
                size="small"
                sx={{ flex: 1 }}
              />
            </Stack>
          </Paper>
        </Collapse>
      </Box>

      {/* Main content - Graph Canvas */}
      <Box sx={{ flex: 1, overflow: 'hidden' }}>
        <ScenarioGraphCanvas
          agents={availableAgents}
          config={config}
          onConfigChange={setConfig}
          onEditAgent={onEditAgent}
          onCreateAgent={onCreateAgent}
          onViewAgentDetails={setViewingAgent}
        />
      </Box>

      {/* Agent Details Dialog */}
      <AgentDetailsDialog
        open={!!viewingAgent}
        onClose={() => setViewingAgent(null)}
        agent={viewingAgent}
      />

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
              Export Scenario Configuration
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Follow these steps to persist your scenario in the backend code
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
                Copy the YAML configuration
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
                Create the scenario directory
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                In your terminal, navigate to the backend registries directory and create a new folder:
              </Typography>
              <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#1e1e1e', borderRadius: 1 }}>
                <Typography
                  component="code"
                  variant="body2"
                  sx={{ fontFamily: 'monospace', color: '#a5d6ff', fontSize: 13 }}
                >
                  mkdir -p apps/artagent/backend/registries/scenariostore/{config.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}
                </Typography>
              </Paper>
            </Box>

            {/* Step 3 */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip label="3" size="small" color="primary" />
                Save the YAML file
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Create a file named <code style={{ backgroundColor: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>orchestration.yaml</code> (or <code style={{ backgroundColor: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>scenario.yaml</code>) in the new directory and paste the YAML content:
              </Typography>
              <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#1e1e1e', borderRadius: 1 }}>
                <Typography
                  component="code"
                  variant="body2"
                  sx={{ fontFamily: 'monospace', color: '#a5d6ff', fontSize: 13 }}
                >
                  # Save the copied YAML to this file:<br/>
                  apps/artagent/backend/registries/scenariostore/{config.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}/orchestration.yaml
                </Typography>
              </Paper>
            </Box>

            {/* Step 4 */}
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Chip label="4" size="small" color="primary" />
                Restart the backend
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                The backend will automatically discover the new scenario on restart:
              </Typography>
              <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#1e1e1e', borderRadius: 1 }}>
                <Typography
                  component="code"
                  variant="body2"
                  sx={{ fontFamily: 'monospace', color: '#a5d6ff', fontSize: 13 }}
                >
                  # Restart your backend service<br/>
                  # The scenario will appear in the templates list
                </Typography>
              </Paper>
            </Box>

            {/* Info Box */}
            <Paper sx={{ p: 2, backgroundColor: '#eff6ff', border: '1px solid #bfdbfe' }}>
              <Typography variant="body2" sx={{ fontWeight: 600, color: '#1e40af', mb: 1 }}>
                📝 Note about Agent Exports
              </Typography>
              <Typography variant="body2" color="text.secondary">
                To export agent configurations, use the Agent Builder interface. Each agent's YAML should be saved to:<br/>
                <code style={{ backgroundColor: '#dbeafe', padding: '2px 6px', borderRadius: 4, fontSize: 12 }}>
                  apps/artagent/backend/registries/agentstore/&lt;agent_name&gt;/agent.yaml
                </code>
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
              a.download = `${config.name.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}_orchestration.yaml`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download YAML File
          </Button>
        </DialogActions>
      </Dialog>

      {/* Footer */}
      <Box
        sx={{
          p: 2,
          borderTop: '1px solid #e5e7eb',
          backgroundColor: '#fafbfc',
          display: 'flex',
          gap: 2,
          justifyContent: 'flex-end',
        }}
      >
        <Button onClick={handleReset} startIcon={<RefreshIcon />} disabled={saving}>
          Reset
        </Button>
        <Button
          onClick={handleExportScenario}
          startIcon={<DownloadIcon />}
          disabled={!config.name.trim() || !config.start_agent}
          variant="outlined"
        >
          Export YAML
        </Button>
        <Button
          variant="contained"
          onClick={handleSave}
          startIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
          disabled={saving || !config.name.trim() || !config.start_agent}
          sx={{
            background: editMode
              ? 'linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)'
              : 'linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)',
          }}
        >
          {saving ? 'Saving Scenario...' : 'Save Scenario'}
        </Button>
      </Box>
    </Box>
  );
}
