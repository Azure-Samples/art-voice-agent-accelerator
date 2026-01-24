/**
 * ScenarioBuilder Component
 * =========================
 * 
 * A visual flow-based scenario builder with connected agent nodes:
 * 
 *   [Start Agent] ──→ [Target A] ──→ [Target C]
 *                          │
 *                          └──→ [Target B]
 * 
 * Features:
 * - Visual graph layout showing agent flow
 * - Click "+" on any node to add handoff targets
 * - Arrows show handoff connections with type indicators
 * - Select start agent to begin the flow
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Avatar,
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  LinearProgress,
  List,
  ListItem,
  ListItemAvatar,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Popover,
  Select,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import CheckIcon from '@mui/icons-material/Check';
import CloseIcon from '@mui/icons-material/Close';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import HubIcon from '@mui/icons-material/Hub';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import RefreshIcon from '@mui/icons-material/Refresh';
import SaveIcon from '@mui/icons-material/Save';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import SettingsIcon from '@mui/icons-material/Settings';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import VolumeOffIcon from '@mui/icons-material/VolumeOff';
import TuneIcon from '@mui/icons-material/Tune';
import CallSplitIcon from '@mui/icons-material/CallSplit';
import ArrowRightAltIcon from '@mui/icons-material/ArrowRightAlt';
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import BuildIcon from '@mui/icons-material/Build';
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver';
import MemoryIcon from '@mui/icons-material/Memory';
import TextFieldsIcon from '@mui/icons-material/TextFields';

import { API_BASE_URL } from '../config/constants.js';
import logger from '../utils/logger.js';

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS & STYLES
// ═══════════════════════════════════════════════════════════════════════════════

const NODE_WIDTH = 180;
const NODE_HEIGHT = 80;
const HORIZONTAL_GAP = 120;
const VERTICAL_GAP = 100;
const ARROW_SIZE = 24;

const colors = {
  start: { bg: '#ecfdf5', border: '#10b981', avatar: '#059669' },
  active: { bg: '#f5f3ff', border: '#8b5cf6', avatar: '#7c3aed' },
  inactive: { bg: '#f9fafb', border: '#d1d5db', avatar: '#9ca3af' },
  selected: { bg: '#ede9fe', border: '#6366f1', avatar: '#4f46e5' },
  session: { bg: '#fef3c7', border: '#f59e0b', avatar: '#d97706' }, // Amber for session agents
  announced: '#8b5cf6',
  discrete: '#f59e0b',
};

// Distinct color palette for connection arrows (to differentiate overlapping paths)
const connectionColors = [
  '#8b5cf6', // violet
  '#3b82f6', // blue
  '#06b6d4', // cyan
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ef4444', // red
  '#ec4899', // pink
  '#6366f1', // indigo
  '#14b8a6', // teal
  '#f97316', // orange
  '#84cc16', // lime
  '#a855f7', // purple
];

const parseSimpleJinjaVar = (value) => {
  if (typeof value !== 'string') return null;
  const match = value.match(/^\s*\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}\s*$/);
  return match ? match[1] : null;
};

const stringifyContextValue = (value) => {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch (err) {
    return String(value);
  }
};

const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const truncateText = (value, maxLength = 32) => {
  if (value === null || value === undefined) return '';
  const text = String(value).replace(/\s+/g, ' ').trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1)}…`;
};

const buildVarAliases = (varName) => {
  if (!varName) return [];
  if (!varName.includes('.')) return [varName];
  const parts = varName.split('.');
  const key = parts.pop();
  const root = parts.join('.');
  return [
    varName,
    `${root}.get('${key}')`,
    `${root}.get("${key}")`,
    `${root}['${key}']`,
    `${root}["${key}"]`,
  ];
};

const getPromptContextSnippet = (prompt, varName, maxLines = 4) => {
  if (!prompt) return '';
  const lines = prompt.split('\n');
  if (!varName) {
    const fallback = lines.slice(0, maxLines).join('\n');
    return lines.length > maxLines ? `${fallback}\n…` : fallback;
  }
  const aliases = buildVarAliases(varName);
  const firstIndex = lines.findIndex((line) =>
    aliases.some((alias) => alias && line.includes(alias))
  );
  if (firstIndex === -1) {
    const fallback = lines.slice(0, maxLines).join('\n');
    return lines.length > maxLines ? `${fallback}\n…` : fallback;
  }
  const start = Math.max(0, firstIndex - 1);
  const end = Math.min(lines.length, start + maxLines);
  const snippet = lines.slice(start, end).join('\n');
  return end < lines.length ? `${snippet}\n…` : snippet;
};

const renderPromptHighlights = (text, vars) => {
  if (!text) return 'No prompt preview available.';
  const uniqueVars = Array.from(new Set(vars || [])).filter(Boolean);
  if (uniqueVars.length === 0) return text;
  const aliases = uniqueVars.flatMap(buildVarAliases).filter(Boolean);
  if (aliases.length === 0) return text;
  const pattern = aliases.map(escapeRegExp).join('|');
  if (!pattern) return text;
  const regex = new RegExp(`\\{\\{[^}]*(${pattern})[^}]*\\}\\}`, 'g');
  const parts = [];
  let lastIndex = 0;
  let matchIndex = 0;
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    parts.push(
      <Box
        component="span"
        key={`hl-${match.index}-${matchIndex}`}
        sx={{ bgcolor: 'rgba(99, 102, 241, 0.15)', borderRadius: '4px', px: 0.5 }}
      >
        {match[0]}
      </Box>
    );
    lastIndex = regex.lastIndex;
    matchIndex += 1;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
};

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

  return {
    text: prompt,
    hasHandoffInstructions
  };
};

// Component to render highlighted runtime prompt preview
const HighlightedPromptPreview = ({ previewData, targetAgent }) => {
  const handoffRef = useRef(null);

  useEffect(() => {
    // Auto-scroll to the handoff section when it exists or updates
    if (handoffRef.current && previewData?.hasHandoffInstructions) {
      handoffRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [previewData?.text, previewData?.hasHandoffInstructions]);

  if (!previewData || !previewData.text) {
    return <span>No prompt available.</span>;
  }

  const { text, hasHandoffInstructions } = previewData;

  if (!hasHandoffInstructions) {
    return <span>{text}</span>;
  }

  // Split by the handoff instructions marker
  const parts = text.split('## Agent Handoff Instructions');

  if (parts.length === 1) {
    return <span>{text}</span>;
  }

  const beforeHandoff = parts[0];
  const handoffSection = parts[1];

  // If we have a specific target agent to highlight, parse the handoff section
  if (targetAgent) {
    // Find the specific target agent section
    const targetMarker = `- **${targetAgent}**`;
    const handoffLines = handoffSection.split('\n');

    let targetStartIdx = -1;
    let targetEndIdx = -1;

    // Find where our target agent section starts
    for (let i = 0; i < handoffLines.length; i++) {
      if (handoffLines[i].includes(targetMarker)) {
        targetStartIdx = i;
        break;
      }
    }

    // Find where our target agent section ends (next agent or end)
    if (targetStartIdx !== -1) {
      for (let i = targetStartIdx + 1; i < handoffLines.length; i++) {
        if (handoffLines[i].trim().startsWith('- **') && handoffLines[i].includes('**')) {
          targetEndIdx = i;
          break;
        }
      }
      if (targetEndIdx === -1) {
        targetEndIdx = handoffLines.length;
      }
    }

    // Reconstruct with highlighting only the target section
    if (targetStartIdx !== -1) {
      const beforeTarget = handoffLines.slice(0, targetStartIdx).join('\n');
      const targetSection = handoffLines.slice(targetStartIdx, targetEndIdx).join('\n');
      const afterTarget = handoffLines.slice(targetEndIdx).join('\n');

      return (
        <>
          <span>{beforeHandoff}</span>
          <span
            style={{
              backgroundColor: '#fef3c7',
              color: '#92400e',
              padding: '2px 4px',
              borderRadius: '3px',
              fontWeight: 600,
            }}
          >
            ## Agent Handoff Instructions
          </span>
          <span>{beforeTarget}</span>
          <span
            ref={handoffRef}
            style={{
              backgroundColor: '#fef9e7',
              display: 'inline-block',
              paddingLeft: '4px',
              borderLeft: '3px solid #fbbf24',
            }}
          >
            {targetSection}
          </span>
          <span>{afterTarget}</span>
        </>
      );
    }
  }

  // Fallback: highlight entire handoff section
  return (
    <>
      <span>{beforeHandoff}</span>
      <span
        ref={handoffRef}
        style={{
          backgroundColor: '#fef3c7',
          color: '#92400e',
          padding: '2px 4px',
          borderRadius: '3px',
          fontWeight: 600,
        }}
      >
        ## Agent Handoff Instructions
      </span>
      <span
        style={{
          backgroundColor: '#fef9e7',
          display: 'inline-block',
          paddingLeft: '4px',
          borderLeft: '3px solid #fbbf24',
        }}
      >
        {handoffSection}
      </span>
    </>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// FLOW NODE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function FlowNode({
  agent,
  isStart,
  isSelected,
  position,
  onSelect,
  onAddHandoff,
  onEditAgent,
  onViewDetails,
  outgoingCount,
}) {
  // Color scheme: start > active (no session distinction)
  const colorScheme = isStart ? colors.start : colors.active;
  
  return (
    <Paper
      elevation={isSelected ? 4 : 1}
      onClick={() => onSelect(agent)}
      sx={{
        position: 'absolute',
        left: position.x,
        top: position.y,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        borderRadius: '12px',
        border: `2px solid ${isSelected ? colors.selected.border : colorScheme.border}`,
        backgroundColor: isSelected ? colors.selected.bg : colorScheme.bg,
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        overflow: 'visible',
        zIndex: isSelected ? 10 : 1,
        '&:hover': {
          boxShadow: '0 4px 20px rgba(0,0,0,0.12)',
          transform: 'translateY(-2px)',
        },
      }}
    >
      {/* Start badge */}
      {isStart && (
        <Chip
          icon={<PlayArrowIcon sx={{ fontSize: 12 }} />}
          label="START"
          size="small"
          color="success"
          sx={{
            position: 'absolute',
            top: -12,
            left: '50%',
            transform: 'translateX(-50%)',
            height: 22,
            fontSize: 10,
            fontWeight: 700,
          }}
        />
      )}
      
      {/* Node content */}
      <Stack
        direction="row"
        alignItems="center"
        spacing={1.5}
        sx={{ p: 1.5, height: '100%' }}
      >
        <Avatar
          sx={{
            width: 40,
            height: 40,
            bgcolor: isSelected ? colors.selected.avatar : colorScheme.avatar,
            fontSize: 16,
            fontWeight: 600,
          }}
        >
          {agent.name?.[0] || 'A'}
        </Avatar>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="subtitle2"
            sx={{
              fontWeight: 600,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              lineHeight: 1.2,
            }}
          >
            {agent.name}
          </Typography>
          {agent.description && (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                display: 'block',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: 10,
              }}
            >
              {agent.description}
            </Typography>
          )}
        </Box>
      </Stack>

      {/* Add handoff button (right side) */}
      <Tooltip title="Add handoff target">
        <IconButton
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            onAddHandoff(agent);
          }}
          sx={{
            position: 'absolute',
            right: -16,
            top: '50%',
            transform: 'translateY(-50%)',
            width: 32,
            height: 32,
            backgroundColor: '#fff',
            border: '2px solid #e5e7eb',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            '&:hover': {
              backgroundColor: '#f5f3ff',
              borderColor: '#8b5cf6',
            },
          }}
        >
          <AddIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      {/* Edit button (left side) - available for all agents */}
      {onEditAgent && (
        <Tooltip title="Edit agent in Agent Builder">
          <IconButton
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              onEditAgent(agent);
            }}
            sx={{
              position: 'absolute',
              left: -16,
              top: '50%',
              transform: 'translateY(-50%)',
              width: 28,
              height: 28,
              backgroundColor: '#fff',
              border: `2px solid ${colors.active.border}`,
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              '&:hover': {
                backgroundColor: colors.active.bg,
                borderColor: colors.active.avatar,
              },
            }}
          >
            <EditIcon sx={{ fontSize: 14 }} />
          </IconButton>
        </Tooltip>
      )}

      {/* Info button (bottom left) */}
      <Tooltip title="View agent details">
        <IconButton
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            onViewDetails(agent);
          }}
          sx={{
            position: 'absolute',
            left: 6,
            bottom: -14,
            width: 26,
            height: 26,
            backgroundColor: '#fff',
            border: '2px solid #e5e7eb',
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            '&:hover': {
              backgroundColor: '#f0f9ff',
              borderColor: '#0ea5e9',
              color: '#0ea5e9',
            },
          }}
        >
          <InfoOutlinedIcon sx={{ fontSize: 14 }} />
        </IconButton>
      </Tooltip>

      {/* Outgoing count badge */}
      {outgoingCount > 0 && (
        <Chip
          label={outgoingCount}
          size="small"
          sx={{
            position: 'absolute',
            bottom: -10,
            right: 10,
            height: 20,
            minWidth: 20,
            fontSize: 11,
            fontWeight: 600,
            backgroundColor: '#8b5cf6',
            color: '#fff',
          }}
        />
      )}
    </Paper>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONNECTION ARROW COMPONENT (SVG)
// ═══════════════════════════════════════════════════════════════════════════════

function ConnectionArrow({
  from,
  to,
  type,
  isSelected,
  isHighlighted,
  onClick,
  onMouseEnter,
  onMouseLeave,
  onDelete,
  colorIndex = 0,
  isBidirectional = false,
  offsetSign = 0,
}) {
  // Get connection color from palette
  const connectionColor = connectionColors[colorIndex % connectionColors.length];
  
  // Determine if this is a forward or backward connection
  const isBackward = to.x < from.x;
  
  let startX, startY, endX, endY;
  
  const edgeInset = 10;
  const anchorInset = 12;
  const verticalSign = isBidirectional
    ? offsetSign
    : (to.y < from.y ? -1 : 1);
  const anchorY = isBidirectional || isBackward
    ? (verticalSign < 0 ? anchorInset : NODE_HEIGHT - anchorInset)
    : NODE_HEIGHT / 2;

  if (isBackward) {
    // Backward: connect LEFT side of source → RIGHT side of target
    // This creates a short, direct path instead of looping around
    startX = from.x - edgeInset;
    startY = from.y + anchorY;
    endX = to.x + NODE_WIDTH + edgeInset;
    endY = to.y + anchorY;
  } else {
    // Forward: connect RIGHT side of source → LEFT side of target
    startX = from.x + NODE_WIDTH + edgeInset;
    startY = from.y + anchorY;
    endX = to.x - edgeInset;
    endY = to.y + anchorY;
  }
  
  const dx = endX - startX;
  const dy = endY - startY;
  const distance = Math.sqrt(dx * dx + dy * dy);
  const arrowOffset = 10; // Space for arrowhead
  
  // Simple S-curve for all connections
  const curvature = Math.min(60, Math.max(30, distance * 0.35));
  const returnLift = isBackward ? (verticalSign < 0 ? -28 : 28) : 0;
  
  let path;
  if (isBackward) {
    // Backward: curve to the left
    path = `M ${startX} ${startY} 
            C ${startX - curvature} ${startY + returnLift}, 
              ${endX + curvature + arrowOffset} ${endY + returnLift}, 
              ${endX + arrowOffset} ${endY}`;
  } else {
    // Forward: curve to the right
    path = `M ${startX} ${startY} 
            C ${startX + curvature} ${startY}, 
              ${endX - curvature - arrowOffset} ${endY}, 
              ${endX - arrowOffset} ${endY}`;
  }
  
  // Calculate label position (midpoint)
  const labelX = (startX + endX) / 2;
  const labelY = (startY + endY) / 2;
  const labelOffsetY = isBidirectional || isBackward
    ? (verticalSign < 0 ? -16 : 18)
    : (isSelected ? 25 : 18);
  
  // Use connection color from palette (unique per arrow)
  const arrowColor = connectionColor;

  const directionGlyph = isBackward ? '←' : '→';
  const typeGlyph = type === 'announced' ? '🔊' : '🔇';
  const labelText = `${directionGlyph}${typeGlyph}`;
  const labelWidth = 32;
  
  // Determine marker based on direction
  const markerId = `arrowhead-${colorIndex}${isSelected ? '-selected' : ''}`;
  
  const isEmphasized = Boolean(isSelected || isHighlighted);

  return (
    <g
      style={{ cursor: 'pointer' }}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {/* Invisible wider path for easier clicking */}
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
      />
      {/* Visible arrow path */}
      <path
        d={path}
        fill="none"
        stroke="#0f172a"
        strokeWidth={isEmphasized ? 4.5 : 4}
        strokeLinecap="round"
        strokeOpacity={isEmphasized ? 0.25 : 0.15}
      />
      <path
        d={path}
        fill="none"
        stroke={isSelected ? colors.selected.border : arrowColor}
        strokeWidth={isEmphasized ? 3.4 : 2.6}
        strokeDasharray={type === 'discrete' ? '8,4' : 'none'}
        strokeLinecap="round"
        strokeOpacity={isEmphasized ? 1 : 0.9}
        markerEnd={`url(#${markerId})`}
        style={{ transition: 'stroke 0.2s, stroke-width 0.2s' }}
      />
      {/* Delete button (shown when selected) */}
      {isSelected && (
        <g
          transform={`translate(${labelX - 10}, ${labelY + labelOffsetY - 30})`}
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          style={{ cursor: 'pointer' }}
        >
          <circle cx="10" cy="10" r="12" fill="#fff" stroke="#ef4444" strokeWidth="2" />
          <text x="10" y="14" textAnchor="middle" fill="#ef4444" fontSize="14" fontWeight="bold">×</text>
        </g>
      )}
      {/* Type label with background for visibility */}
      <g>
        <rect
          x={labelX - labelWidth / 2}
          y={labelY + labelOffsetY - 10}
          width={labelWidth}
          height={16}
          rx={4}
          fill="white"
          fillOpacity={0.9}
          stroke={arrowColor}
          strokeWidth={1}
        />
        <text
          x={labelX}
          y={labelY + labelOffsetY + 3}
          textAnchor="middle"
          fill={arrowColor}
          fontSize="10"
          fontWeight="600"
        >
          {labelText}
        </text>
      </g>
    </g>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HANDOFF CONDITION PATTERNS (predefined templates)
// ═══════════════════════════════════════════════════════════════════════════════

const HANDOFF_CONDITION_PATTERNS = [
  {
    id: 'authentication',
    name: '🔐 Authentication Required',
    icon: '🔐',
    description: 'When identity verification or login is needed',
    condition: `Transfer when the customer needs to:
- Verify their identity or authenticate
- Log into their account
- Provide security credentials or PIN
- Complete multi-factor authentication`,
  },
  {
    id: 'specialized_topic',
    name: '🎯 Specialized Topic',
    icon: '🎯',
    description: 'When conversation requires specific expertise',
    condition: `Transfer when the customer asks about topics that require specialized knowledge or expertise that this agent cannot provide.`,
  },
  {
    id: 'account_issue',
    name: '💳 Account/Billing Issue',
    icon: '💳',
    description: 'Account management or billing concerns',
    condition: `Transfer when the customer mentions:
- Account access problems or lockouts
- Billing discrepancies or payment issues
- Subscription changes or cancellations
- Refund requests or credit adjustments`,
  },
  {
    id: 'fraud_security',
    name: '🚨 Fraud/Security Concern',
    icon: '🚨',
    description: 'Suspicious activity or security issues',
    condition: `Transfer IMMEDIATELY when the customer reports:
- Unauthorized transactions or suspicious activity
- Lost or stolen cards/credentials
- Potential identity theft or account compromise
- Security alerts or concerns`,
  },
  {
    id: 'technical_support',
    name: '🔧 Technical Support',
    icon: '🔧',
    description: 'Technical issues requiring troubleshooting',
    condition: `Transfer when the customer needs help with:
- Technical problems or error messages
- Product or service not working correctly
- Setup, configuration, or installation issues
- Connectivity or performance problems`,
  },
  {
    id: 'escalation',
    name: '⬆️ Escalation Request',
    icon: '⬆️',
    description: 'Customer requests supervisor or escalation',
    condition: `Transfer when the customer:
- Explicitly requests to speak with a supervisor or manager
- Expresses significant dissatisfaction that you cannot resolve
- Has a complex issue requiring higher authorization
- Needs decisions beyond your authority level`,
  },
  {
    id: 'sales_upsell',
    name: '💰 Sales/Upsell Opportunity',
    icon: '💰',
    description: 'Interest in purchasing or upgrading',
    condition: `Transfer when the customer expresses interest in:
- Purchasing new products or services
- Upgrading their current plan or subscription
- Special offers, promotions, or deals
- Comparing options or getting pricing information`,
  },
  {
    id: 'appointment',
    name: '📅 Scheduling/Appointment',
    icon: '📅',
    description: 'Booking, rescheduling, or canceling',
    condition: `Transfer when the customer wants to:
- Schedule a new appointment or meeting
- Reschedule or cancel an existing appointment
- Check availability or confirm booking details
- Modify reservation or booking information`,
  },
  {
    id: 'returns',
    name: '📦 Returns/Exchanges',
    icon: '📦',
    description: 'Product returns or exchange requests',
    condition: `Transfer when the customer needs help with:
- Returning a product or requesting a refund
- Exchanging an item for a different one
- Reporting damaged or defective products
- Tracking return status or shipping labels`,
  },
  {
    id: 'general_inquiry',
    name: '❓ General Inquiry',
    icon: '❓',
    description: 'Questions best handled by another agent',
    condition: `Transfer when the customer's questions or needs are better suited for this specialized agent's expertise.`,
  },
  {
    id: 'custom',
    name: '✏️ Custom Condition',
    icon: '✏️',
    description: 'Write your own handoff condition',
    condition: '',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// HANDOFF EDITOR DIALOG
// ═══════════════════════════════════════════════════════════════════════════════

function HandoffEditorDialog({ open, onClose, handoff, agents, scenarioAgents = [], handoffs, onSave, onDelete }) {
  const [type, setType] = useState(handoff?.type || 'announced');
  const [shareContext, setShareContext] = useState(handoff?.share_context !== false);
  const [handoffCondition, setHandoffCondition] = useState(handoff?.handoff_condition || '');
  const [selectedPattern, setSelectedPattern] = useState(null);
  const [showPatternPicker, setShowPatternPicker] = useState(false);
  const [contextVarEntries, setContextVarEntries] = useState([]);
  const [expandedMappingId, setExpandedMappingId] = useState(null);
  const [promptDialog, setPromptDialog] = useState({
    open: false,
    title: '',
    content: '',
  });

  const sourceAgent = agents?.find(a => a.name === handoff?.from_agent);
  const targetAgent = agents?.find(a => a.name === handoff?.to_agent);
  const sourcePromptVars = useMemo(
    () => Array.from(new Set((sourceAgent?.prompt_vars || []).filter(Boolean))),
    [sourceAgent],
  );
  const targetPromptVars = useMemo(
    () => Array.from(new Set((targetAgent?.prompt_vars || []).filter(Boolean))),
    [targetAgent],
  );
  const runtimeHandoffs = useMemo(() => {
    if (!handoff) return handoffs || [];
    const baseHandoffs = Array.isArray(handoffs) ? handoffs : [];
    let matched = false;
    const updated = baseHandoffs.map((edge) => {
      if (
        edge.from_agent === handoff.from_agent &&
        edge.to_agent === handoff.to_agent
      ) {
        matched = true;
        return { ...edge, handoff_condition: handoffCondition };
      }
      return edge;
    });
    if (!matched) {
      updated.push({ ...handoff, handoff_condition: handoffCondition });
    }
    return updated;
  }, [handoffs, handoff, handoffCondition]);
  const runtimePrompt = useMemo(() => {
    if (!handoff?.from_agent) return '';
    const basePrompt = sourceAgent?.prompt_full || sourceAgent?.prompt_preview || '';
    return buildRuntimePrompt(basePrompt, runtimeHandoffs, handoff.from_agent);
  }, [handoff, runtimeHandoffs, sourceAgent]);
  const runtimePromptPreview = useMemo(
    () => getRuntimePromptPreview(runtimePrompt),
    [runtimePrompt],
  );

  // Track the handoff identity to only reset state when editing a different handoff
  const handoffKey = handoff ? `${handoff.from_agent}::${handoff.to_agent}` : null;
  const prevHandoffKeyRef = useRef(null);

  useEffect(() => {
    // Only reset state when editing a different handoff (or when dialog first opens)
    const handoffChanged = prevHandoffKeyRef.current !== handoffKey;

    if (handoff && handoffChanged) {
      prevHandoffKeyRef.current = handoffKey;

      setType(handoff.type || 'announced');
      setShareContext(handoff.share_context !== false);
      setHandoffCondition(handoff.handoff_condition || '');
      const existingContextVars = handoff.context_vars || {};
      const entries = [];
      const seen = new Set();
      targetPromptVars.forEach((key) => {
        const existingValue = existingContextVars[key];
        const mappedVar = parseSimpleJinjaVar(existingValue);
        entries.push({
          id: `auto-${key}`,
          key,
          mode: existingValue !== undefined ? (mappedVar ? 'map' : 'custom') : 'inherit',
          sourceVar: mappedVar || '',
          value: mappedVar ? '' : stringifyContextValue(existingValue),
          locked: true,
        });
        seen.add(key);
      });
      Object.entries(existingContextVars).forEach(([key, value]) => {
        if (!seen.has(key)) {
          const mappedVar = parseSimpleJinjaVar(value);
          entries.push({
            id: `custom-${key}`,
            key,
            mode: mappedVar ? 'map' : 'custom',
            sourceVar: mappedVar || '',
            value: mappedVar ? '' : stringifyContextValue(value),
            locked: false,
          });
        }
      });
      setContextVarEntries(entries);
      // Detect if current condition matches a pattern
      const matchingPattern = HANDOFF_CONDITION_PATTERNS.find(
        p => p.condition && p.condition.trim() === (handoff.handoff_condition || '').trim()
      );
      setSelectedPattern(matchingPattern?.id || (handoff.handoff_condition ? 'custom' : null));
    }
  }, [handoffKey, targetPromptVars, handoff]);

  const handlePatternSelect = (patternId) => {
    const pattern = HANDOFF_CONDITION_PATTERNS.find(p => p.id === patternId);
    if (pattern) {
      setSelectedPattern(patternId);
      if (patternId !== 'custom') {
        // Replace {target_agent} placeholder if present
        const condition = pattern.condition.replace(/\{target_agent\}/g, handoff?.to_agent || 'the target agent');
        setHandoffCondition(condition);
      }
      setShowPatternPicker(false);
    }
  };

  const handleSave = () => {
    const contextVars = contextVarEntries.reduce((acc, entry) => {
      const key = entry.key?.trim();
      if (!key) return acc;
      if (entry.mode === 'inherit') return acc;
      if (entry.mode === 'map') {
        const sourceVar = entry.sourceVar?.trim();
        if (!sourceVar) return acc;
        acc[key] = `{{ ${sourceVar} }}`;
        return acc;
      }
      const value = entry.value;
      if (value === undefined || value === null) return acc;
      if (typeof value === 'string' && value.trim() === '') return acc;
      acc[key] = value;
      return acc;
    }, {});
    // Always use the centralized handoff_to_agent tool
    onSave({
      ...handoff,
      type,
      tool: 'handoff_to_agent',  // Standardized - always use generic handoff
      share_context: shareContext,
      handoff_condition: handoffCondition,
      context_vars: contextVars,
    });
    onClose();
  };

  if (!handoff) return null;

  const handleAddContextVar = () => {
    const newId = `custom-${Date.now()}`;
    setContextVarEntries((prev) => [
      { id: newId, key: '', mode: 'custom', sourceVar: '', value: '', locked: false },
      ...prev,
    ]);
    setExpandedMappingId(newId);
  };

  const handleUpdateContextVar = (id, field, value) => {
    setContextVarEntries((prev) =>
      prev.map((entry) => (entry.id === id ? { ...entry, [field]: value } : entry))
    );
  };

  const handleRemoveContextVar = (id) => {
    setContextVarEntries((prev) => prev.filter((entry) => entry.id !== id));
  };

  const handleOpenPromptDialog = (title, content) => {
    setPromptDialog({
      open: true,
      title,
      content: content || 'No prompt available.',
    });
  };

  const handleClosePromptDialog = () => {
    setPromptDialog({ open: false, title: '', content: '' });
  };

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <CallSplitIcon color="primary" />
        Edit Handoff: {handoff.from_agent} → {handoff.to_agent}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ mt: 1 }}>
          {/* Pattern Selection Section */}
          <Box>
            <Typography variant="subtitle2" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
              <AutoFixHighIcon sx={{ fontSize: 16, color: '#6366f1' }} />
              When should this handoff happen?
            </Typography>
            
            {/* Quick pattern chips */}
            <Box sx={{ mb: 2 }}>
              <Stack direction="row" flexWrap="wrap" gap={1}>
                {HANDOFF_CONDITION_PATTERNS.slice(0, 6).map((pattern) => (
                  <Chip
                    key={pattern.id}
                    icon={<span style={{ fontSize: 14 }}>{pattern.icon}</span>}
                    label={pattern.name.replace(pattern.icon + ' ', '')}
                    onClick={() => handlePatternSelect(pattern.id)}
                    variant={selectedPattern === pattern.id ? 'filled' : 'outlined'}
                    color={selectedPattern === pattern.id ? 'primary' : 'default'}
                    sx={{
                      cursor: 'pointer',
                      fontWeight: selectedPattern === pattern.id ? 600 : 400,
                      '&:hover': { backgroundColor: selectedPattern === pattern.id ? undefined : 'rgba(99, 102, 241, 0.08)' },
                    }}
                  />
                ))}
                <Chip
                  icon={<span style={{ fontSize: 14 }}>➕</span>}
                  label="More..."
                  onClick={() => setShowPatternPicker(!showPatternPicker)}
                  variant="outlined"
                  sx={{
                    cursor: 'pointer',
                    borderStyle: 'dashed',
                    '&:hover': { backgroundColor: 'rgba(99, 102, 241, 0.08)' },
                  }}
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
                  {HANDOFF_CONDITION_PATTERNS.map((pattern) => (
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
                        '&:hover': {
                          borderColor: '#6366f1',
                          boxShadow: '0 2px 8px rgba(99, 102, 241, 0.15)',
                        },
                      }}
                    >
                      <Stack direction="row" spacing={1} alignItems="flex-start">
                        <Typography sx={{ fontSize: 20 }}>{pattern.icon}</Typography>
                        <Box sx={{ flex: 1 }}>
                          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 12 }}>
                            {pattern.name.replace(pattern.icon + ' ', '')}
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
                  ))}
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
              placeholder={`Transfer to ${handoff.to_agent} when the customer:\n- Asks about [specific topic or service]\n- Expresses [intent or need]\n- Mentions [keywords or phrases]`}
              helperText={
                <span>
                  This condition will be injected into <strong>{handoff.from_agent}</strong>'s system prompt to guide when to transfer.
                  {targetAgent?.description && (
                    <span style={{ display: 'block', marginTop: 4, color: '#6366f1' }}>
                      💡 {handoff.to_agent}: {targetAgent.description}
                    </span>
                  )}
                </span>
              }
              sx={{
                '& .MuiOutlinedInput-root': {
                  fontFamily: 'monospace',
                  fontSize: 13,
                },
              }}
            />
            <Paper
              variant="outlined"
              sx={{ mt: 1.5, p: 1.5, borderRadius: '12px', bgcolor: '#f8fafc' }}
            >
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  Full runtime system prompt (auto-focused on handoff instructions)
                </Typography>
                <Button
                  size="small"
                  variant="text"
                  onClick={() =>
                    handleOpenPromptDialog(
                      `${handoff.from_agent} runtime prompt`,
                      runtimePrompt || 'No prompt available.',
                    )
                  }
                >
                  View in dialog
                </Button>
              </Stack>
              <Box
                sx={{
                  maxHeight: '300px',
                  overflowY: 'auto',
                  overflowX: 'hidden',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  p: 1.5,
                  backgroundColor: '#fafafa',
                  '&::-webkit-scrollbar': {
                    width: '8px',
                  },
                  '&::-webkit-scrollbar-track': {
                    backgroundColor: '#f1f5f9',
                    borderRadius: '4px',
                  },
                  '&::-webkit-scrollbar-thumb': {
                    backgroundColor: '#cbd5e1',
                    borderRadius: '4px',
                    '&:hover': {
                      backgroundColor: '#94a3b8',
                    },
                  },
                }}
              >
                <Typography
                  component="div"
                  variant="caption"
                  sx={{
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap',
                    fontSize: 11,
                    lineHeight: 1.6,
                  }}
                >
                  <HighlightedPromptPreview
                    previewData={runtimePromptPreview}
                    targetAgent={handoff?.to_agent}
                  />
                </Typography>
              </Box>
            </Paper>
          </Box>

          <Divider />

          {/* Type selector */}
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              Handoff Type
            </Typography>
            <ToggleButtonGroup
              value={type}
              exclusive
              onChange={(e, v) => v && setType(v)}
              size="small"
              fullWidth
            >
              <ToggleButton value="announced" sx={{ textTransform: 'none' }}>
                <VolumeUpIcon sx={{ mr: 1, color: colors.announced }} />
                Announced
              </ToggleButton>
              <ToggleButton value="discrete" sx={{ textTransform: 'none' }}>
                <VolumeOffIcon sx={{ mr: 1, color: colors.discrete }} />
                Discrete (Silent)
              </ToggleButton>
            </ToggleButtonGroup>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              {type === 'announced'
                ? 'Target agent will greet/announce the transfer'
                : 'Silent handoff - agent continues conversation naturally'}
            </Typography>
            {/* Detailed behavior explanation */}
            <Paper 
              variant="outlined" 
              sx={{ 
                mt: 1.5, 
                p: 1.5, 
                borderRadius: '8px', 
                bgcolor: type === 'announced' ? 'rgba(139, 92, 246, 0.05)' : 'rgba(245, 158, 11, 0.05)',
                borderColor: type === 'announced' ? 'rgba(139, 92, 246, 0.2)' : 'rgba(245, 158, 11, 0.2)'
              }}
            >
              <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 0.5 }}>
                {type === 'announced' ? '🔊 Announced Behavior:' : '🔇 Discrete Behavior:'}
              </Typography>
              {type === 'announced' ? (
                <Typography variant="caption" color="text.secondary" component="div">
                  • Target agent speaks their <strong>greeting</strong> message on arrival<br/>
                  • User hears a clear transition (e.g., "Hi, I'm the Fraud Specialist...")<br/>
                  • Best for: First-time routing, specialist introductions, formal transfers<br/>
                  • Creates explicit "I'm transferring you" experience
                </Typography>
              ) : (
                <Typography variant="caption" color="text.secondary" component="div">
                  • Target agent uses <strong>return_greeting</strong> (or continues silently)<br/>
                  • Seamless transition - user may not notice the switch<br/>
                  • Best for: Returning to previous agent, internal escalations<br/>
                  • Creates natural conversational flow without interruption
                </Typography>
              )}
            </Paper>
          </Box>

          {/* Share context */}
          <FormControlLabel
            control={
              <Switch
                checked={shareContext}
                onChange={(e) => setShareContext(e.target.checked)}
              />
            }
            label={
              <Box>
                <Typography variant="body2">Share conversation context</Typography>
                <Typography variant="caption" color="text.secondary">
                  Pass chat history and memory to target agent
                </Typography>
              </Box>
            }
          />

          <Divider />

          {/* Advanced Config - Collapsed by default */}
          <Accordion
            sx={{
              borderRadius: '12px',
              border: '1px solid #e5e7eb',
              boxShadow: 'none',
              '&:before': { display: 'none' },
            }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Stack direction="row" spacing={1.5} alignItems="center">
                <TextFieldsIcon sx={{ fontSize: 18, color: '#6366f1' }} />
                <Box>
                  <Typography variant="subtitle2">Advanced Handoff Config</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Prompt context and variable mapping
                  </Typography>
                </Box>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: '12px' }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Box>
                      <Typography variant="subtitle2">Variable mapping</Typography>
                      <Typography variant="caption" color="text.secondary">
                        Map source variables or override values passed to the target agent.
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                        Source vars: {sourcePromptVars.length} • Target vars: {targetPromptVars.length}
                      </Typography>
                    </Box>
                    <Button
                      onClick={handleAddContextVar}
                      size="small"
                      variant="outlined"
                      startIcon={<AddIcon />}
                    >
                      Add mapping
                    </Button>
                  </Stack>
                  <Stack spacing={1.5} sx={{ mt: 2 }}>
                    {contextVarEntries.length === 0 ? (
                      <Alert severity="info" sx={{ borderRadius: '8px' }}>
                        Add a mapping to pass or override context for this handoff.
                      </Alert>
                    ) : (
                      contextVarEntries.map((entry) => (
                        <Accordion
                          key={entry.id}
                          expanded={expandedMappingId === entry.id}
                          onChange={(_event, isExpanded) =>
                            setExpandedMappingId(isExpanded ? entry.id : null)
                          }
                          sx={{
                            border: '1px solid #e5e7eb',
                            borderRadius: '10px',
                            bgcolor: '#fff',
                            boxShadow: 'none',
                            '&:before': { display: 'none' },
                          }}
                          TransitionProps={{ unmountOnExit: true }}
                        >
                          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                            <Stack
                              direction="row"
                              spacing={1}
                              alignItems="center"
                              sx={{ flex: 1, minWidth: 0 }}
                            >
                              <Chip
                                label={entry.key || 'unnamed'}
                                size="small"
                                sx={{ fontFamily: 'monospace' }}
                              />
                              <Chip
                                label={
                                  entry.mode === 'map'
                                    ? 'Mapped'
                                    : entry.mode === 'custom'
                                      ? 'Override'
                                      : 'Inherit'
                                }
                                size="small"
                                variant="outlined"
                              />
                              {entry.mode === 'custom' ? (
                                <Chip
                                  label={`Value: ${truncateText(entry.value || '') || 'set value'}`}
                                  size="small"
                                  color="warning"
                                  variant="outlined"
                                />
                              ) : (
                                <Typography
                                  variant="caption"
                                  color="text.secondary"
                                  sx={{
                                    minWidth: 0,
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                >
                                  {entry.mode === 'map' && entry.sourceVar
                                    ? `← ${entry.sourceVar}`
                                    : 'uses runtime value'}
                                </Typography>
                              )}
                            </Stack>
                            {!entry.locked && (
                              <IconButton
                                size="small"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleRemoveContextVar(entry.id);
                                }}
                                aria-label="Remove mapping"
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            )}
                          </AccordionSummary>
                          <AccordionDetails>
                            <Stack spacing={2}>
                              <Box
                                sx={{
                                  display: 'grid',
                                  gridTemplateColumns: {
                                    xs: '1fr',
                                    md: '220px 180px 1fr',
                                  },
                                  gap: 1,
                                }}
                              >
                                <Box>
                                  <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                                    Target variable
                                  </Typography>
                                  {entry.locked ? (
                                    <Chip
                                      label={entry.key}
                                      size="small"
                                      sx={{
                                        fontFamily: 'monospace',
                                        maxWidth: 200,
                                        whiteSpace: 'normal',
                                      }}
                                    />
                                  ) : (
                                    <TextField
                                      label="Target variable"
                                      size="small"
                                      value={entry.key}
                                      onChange={(e) => handleUpdateContextVar(entry.id, 'key', e.target.value)}
                                      fullWidth
                                    />
                                  )}
                                </Box>
                                <Box>
                                  <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                                    Mode
                                  </Typography>
                                  <FormControl size="small" fullWidth>
                                    <InputLabel>Mode</InputLabel>
                                    <Select
                                      label="Mode"
                                      value={entry.mode || 'inherit'}
                                      onChange={(e) => {
                                        const nextMode = e.target.value;
                                        handleUpdateContextVar(entry.id, 'mode', nextMode);
                                        if (nextMode === 'map' && !entry.sourceVar && sourcePromptVars[0]) {
                                          handleUpdateContextVar(entry.id, 'sourceVar', sourcePromptVars[0]);
                                        }
                                      }}
                                    >
                                      <MenuItem value="inherit">Use existing</MenuItem>
                                      <MenuItem value="map">Map from source</MenuItem>
                                      <MenuItem value="custom">Custom override</MenuItem>
                                    </Select>
                                  </FormControl>
                                </Box>
                                <Box>
                                  <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
                                    Source / Value
                                  </Typography>
                                  {entry.mode === 'map' && (
                                    <FormControl size="small" fullWidth>
                                      <InputLabel>Source variable</InputLabel>
                                      <Select
                                        label="Source variable"
                                        value={entry.sourceVar || ''}
                                        onChange={(e) => handleUpdateContextVar(entry.id, 'sourceVar', e.target.value)}
                                        disabled={sourcePromptVars.length === 0}
                                      >
                                        {sourcePromptVars.length === 0 ? (
                                          <MenuItem value="">No source vars</MenuItem>
                                        ) : (
                                          sourcePromptVars.map((varName) => (
                                            <MenuItem key={varName} value={varName}>
                                              {varName}
                                            </MenuItem>
                                          ))
                                        )}
                                      </Select>
                                    </FormControl>
                                  )}
                                  {entry.mode === 'custom' && (
                                    <TextField
                                      label="Value"
                                      size="small"
                                      fullWidth
                                      value={entry.value}
                                      onChange={(e) => handleUpdateContextVar(entry.id, 'value', e.target.value)}
                                      placeholder="e.g. {{ client_id }} or 'billing inquiry'"
                                    />
                                  )}
                                  {entry.mode === 'inherit' && (
                                    <Typography variant="caption" color="text.secondary">
                                      Uses the runtime value from the handoff context.
                                    </Typography>
                                  )}
                                </Box>
                              </Box>

                              <Divider />

                              <Box>
                                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                                  <Typography variant="caption" color="text.secondary">
                                    Target prompt context
                                  </Typography>
                                  <Stack direction="row" spacing={1}>
                                    <Button
                                      size="small"
                                      variant="text"
                                      onClick={() =>
                                        handleOpenPromptDialog(
                                          `${handoff.to_agent} prompt`,
                                          targetAgent?.prompt_full || targetAgent?.prompt_preview,
                                        )
                                      }
                                    >
                                      View target prompt
                                    </Button>
                                    {entry.mode === 'map' && (
                                      <Button
                                        size="small"
                                        variant="text"
                                        onClick={() =>
                                          handleOpenPromptDialog(
                                            `${handoff.from_agent} prompt`,
                                            sourceAgent?.prompt_full || sourceAgent?.prompt_preview,
                                          )
                                        }
                                      >
                                        View source prompt
                                      </Button>
                                    )}
                                  </Stack>
                                </Stack>
                                <Paper
                                  variant="outlined"
                                  sx={{ p: 1.5, borderRadius: '10px', bgcolor: '#f8fafc' }}
                                >
                                  <Typography
                                    component="div"
                                    variant="caption"
                                    sx={{
                                      fontFamily: 'monospace',
                                      whiteSpace: 'pre-wrap',
                                      fontSize: 11,
                                      lineHeight: 1.6,
                                    }}
                                  >
                                    {renderPromptHighlights(
                                      getPromptContextSnippet(
                                        targetAgent?.prompt_full || targetAgent?.prompt_preview,
                                        entry.key,
                                      ),
                                      [entry.key],
                                    )}
                                  </Typography>
                                </Paper>
                              </Box>
                            </Stack>
                          </AccordionDetails>
                        </Accordion>
                      ))
                    )}
                  </Stack>
                </Paper>
              </Stack>
            </AccordionDetails>
          </Accordion>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => { onDelete(); onClose(); }} color="error">
          Delete
        </Button>
        <Box sx={{ flex: 1 }} />
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleSave} variant="contained">
          Save
        </Button>
      </DialogActions>
      </Dialog>
      <Dialog open={promptDialog.open} onClose={handleClosePromptDialog} maxWidth="md" fullWidth>
        <DialogTitle>{promptDialog.title}</DialogTitle>
        <DialogContent dividers>
          <Typography
            component="pre"
            sx={{
              fontFamily: 'monospace',
              fontSize: 12,
              whiteSpace: 'pre-wrap',
              margin: 0,
            }}
          >
            {promptDialog.content}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClosePromptDialog}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// AGENT DETAIL DIALOG
// ═══════════════════════════════════════════════════════════════════════════════

function AgentDetailDialog({ open, onClose, agent, allAgents, handoffs }) {
  if (!agent) return null;

  // Get handoffs from this agent
  const outgoingHandoffs = handoffs.filter((h) => h.from_agent === agent.name);
  const incomingHandoffs = handoffs.filter((h) => h.to_agent === agent.name);

  // Use tool_details for full tool info (from backend), fallback to tools as string array
  const toolDetails = agent.tool_details || [];
  
  // Categorize tools - handoff vs regular
  const handoffTools = toolDetails.filter((t) => 
    t.name?.startsWith('handoff_')
  );
  const regularTools = toolDetails.filter((t) => 
    !t.name?.startsWith('handoff_')
  );
  
  // Also handle legacy tools array (strings only)
  const legacyTools = (agent.tools || []).filter(t => typeof t === 'string');
  const legacyHandoffTools = legacyTools.filter(t => t.startsWith('handoff_'));
  const legacyRegularTools = legacyTools.filter(t => !t.startsWith('handoff_'));

  // Agent color - unified styling
  const agentColor = colors.active;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{ sx: { borderRadius: '16px', maxHeight: '85vh' } }}
    >
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" alignItems="center" spacing={2}>
          <Avatar
            sx={{
              width: 48,
              height: 48,
              bgcolor: agentColor.avatar,
              fontSize: 20,
              fontWeight: 600,
            }}
          >
            {agent.name?.[0] || 'A'}
          </Avatar>
          <Box sx={{ flex: 1 }}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {agent.name}
              </Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              {agent.description || 'No description provided'}
            </Typography>
          </Box>
          <IconButton onClick={onClose} size="small">
            <CloseIcon />
          </IconButton>
        </Stack>
      </DialogTitle>

      <DialogContent dividers sx={{ p: 0 }}>
        <Stack spacing={0}>
          {/* Greetings Section */}
          {(agent.greeting || agent.return_greeting) && (
            <Box sx={{ p: 2, backgroundColor: '#f0fdf4', borderBottom: '1px solid #e5e7eb' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#059669', mb: 1 }}>
                <RecordVoiceOverIcon sx={{ fontSize: 16, mr: 1, verticalAlign: 'middle' }} />
                Greetings
              </Typography>
              <Stack spacing={1}>
                {agent.greeting && (
                  <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                      Initial Greeting
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#fff', borderRadius: '8px', mt: 0.5 }}>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap' }}>
                        {agent.greeting}
                      </Typography>
                    </Paper>
                  </Box>
                )}
                {agent.return_greeting && (
                  <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                      Return Greeting
                    </Typography>
                    <Paper variant="outlined" sx={{ p: 1.5, backgroundColor: '#fff', borderRadius: '8px', mt: 0.5 }}>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: 12, whiteSpace: 'pre-wrap' }}>
                        {agent.return_greeting}
                      </Typography>
                    </Paper>
                  </Box>
                )}
              </Stack>
            </Box>
          )}

          {/* Tools Section */}
          <Box sx={{ p: 2, borderBottom: '1px solid #e5e7eb' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#6366f1', mb: 1.5 }}>
              <BuildIcon sx={{ fontSize: 16, mr: 1, verticalAlign: 'middle' }} />
              Available Tools ({regularTools.length + legacyRegularTools.length})
            </Typography>
            
            {regularTools.length === 0 && legacyRegularTools.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No tools configured for this agent
              </Typography>
            ) : (
              <Stack spacing={1}>
                {/* Tool details with descriptions */}
                {regularTools.map((tool, idx) => (
                  <Paper key={`detail-${idx}`} variant="outlined" sx={{ p: 1.5, borderRadius: '8px' }}>
                    <Stack direction="row" alignItems="flex-start" spacing={1}>
                      <Chip
                        label={tool.name}
                        size="small"
                        color="primary"
                        sx={{ fontSize: 11, fontFamily: 'monospace', fontWeight: 600 }}
                      />
                      <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                        {tool.description || 'No description available'}
                      </Typography>
                    </Stack>
                  </Paper>
                ))}
                {/* Legacy tools without descriptions (if tool_details not available) */}
                {regularTools.length === 0 && legacyRegularTools.length > 0 && (
                  <Stack direction="row" flexWrap="wrap" gap={1}>
                    {legacyRegularTools.map((toolName, idx) => (
                      <Chip
                        key={idx}
                        label={toolName}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: 11, fontFamily: 'monospace' }}
                      />
                    ))}
                  </Stack>
                )}
              </Stack>
            )}
          </Box>

          {/* Handoffs Section */}
          <Box sx={{ p: 2, borderBottom: '1px solid #e5e7eb' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#8b5cf6', mb: 1.5 }}>
              <CallSplitIcon sx={{ fontSize: 16, mr: 1, verticalAlign: 'middle' }} />
              Handoff Connections
            </Typography>
            
            <Stack spacing={2}>
              {/* Outgoing Handoffs */}
              <Box>
                <Typography variant="caption" sx={{ fontWeight: 600, color: '#059669' }}>
                  ↗️ Can hand off to ({outgoingHandoffs.length})
                </Typography>
                {outgoingHandoffs.length === 0 ? (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                    No outgoing handoffs configured
                  </Typography>
                ) : (
                  <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
                    {outgoingHandoffs.map((h, idx) => (
                      <Chip
                        key={idx}
                        label={h.to_agent}
                        size="small"
                        color="success"
                        variant="outlined"
                        icon={h.type === 'announced' ? <VolumeUpIcon /> : <VolumeOffIcon />}
                        sx={{ fontSize: 11 }}
                      />
                    ))}
                  </Stack>
                )}
              </Box>
              
              {/* Incoming Handoffs */}
              <Box>
                <Typography variant="caption" sx={{ fontWeight: 600, color: '#3b82f6' }}>
                  ↙️ Receives handoffs from ({incomingHandoffs.length})
                </Typography>
                {incomingHandoffs.length === 0 ? (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                    No incoming handoffs
                  </Typography>
                ) : (
                  <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
                    {incomingHandoffs.map((h, idx) => (
                      <Chip
                        key={idx}
                        label={h.from_agent}
                        size="small"
                        color="primary"
                        variant="outlined"
                        icon={h.type === 'announced' ? <VolumeUpIcon /> : <VolumeOffIcon />}
                        sx={{ fontSize: 11 }}
                      />
                    ))}
                  </Stack>
                )}
              </Box>

              {/* Handoff Tools Available */}
              {(handoffTools.length > 0 || legacyHandoffTools.length > 0) && (
                <Box>
                  <Typography variant="caption" sx={{ fontWeight: 600, color: '#f59e0b' }}>
                    🔧 Handoff Tools Available
                  </Typography>
                  <Stack direction="row" flexWrap="wrap" gap={1} sx={{ mt: 1 }}>
                    {handoffTools.map((tool, idx) => (
                      <Tooltip key={`tool-${idx}`} title={tool.description || 'Handoff tool'}>
                        <Chip
                          label={tool.name}
                          size="small"
                          variant="outlined"
                          color="warning"
                          sx={{ fontSize: 10, fontFamily: 'monospace' }}
                        />
                      </Tooltip>
                    ))}
                    {handoffTools.length === 0 && legacyHandoffTools.map((toolName, idx) => (
                      <Chip
                        key={`legacy-${idx}`}
                        label={toolName}
                        size="small"
                        variant="outlined"
                        color="warning"
                        sx={{ fontSize: 10, fontFamily: 'monospace' }}
                      />
                    ))}
                  </Stack>
                </Box>
              )}
            </Stack>
          </Box>

          {/* Context / Template Variables Section */}
          {agent.template_vars && Object.keys(agent.template_vars).length > 0 && (
            <Box sx={{ p: 2, borderBottom: '1px solid #e5e7eb' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#0891b2', mb: 1.5 }}>
                <TextFieldsIcon sx={{ fontSize: 16, mr: 1, verticalAlign: 'middle' }} />
                Template Variables
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={1}>
                {Object.entries(agent.template_vars).map(([key, value]) => (
                  <Tooltip key={key} title={`${value}`}>
                    <Chip
                      label={`${key}: ${typeof value === 'string' ? value.slice(0, 20) : value}${typeof value === 'string' && value.length > 20 ? '...' : ''}`}
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: 11, fontFamily: 'monospace' }}
                    />
                  </Tooltip>
                ))}
              </Stack>
            </Box>
          )}

          {/* Voice Configuration */}
          {agent.voice && (
            <Box sx={{ p: 2, borderBottom: '1px solid #e5e7eb' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#ec4899', mb: 1.5 }}>
                <RecordVoiceOverIcon sx={{ fontSize: 16, mr: 1, verticalAlign: 'middle' }} />
                Voice Configuration
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={1}>
                <Chip label={`Voice: ${agent.voice.name || 'Default'}`} size="small" variant="outlined" />
                {agent.voice.rate && <Chip label={`Rate: ${agent.voice.rate}`} size="small" variant="outlined" />}
                {agent.voice.style && <Chip label={`Style: ${agent.voice.style}`} size="small" variant="outlined" />}
              </Stack>
            </Box>
          )}

          {/* Model Configuration */}
          {(agent.model || agent.cascade_model || agent.voicelive_model) && (
            <Box sx={{ p: 2 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, color: '#7c3aed', mb: 1.5 }}>
                <MemoryIcon sx={{ fontSize: 16, mr: 1, verticalAlign: 'middle' }} />
                Model Configuration
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={1}>
                {agent.cascade_model && (
                  <Chip 
                    label={`Cascade: ${agent.cascade_model.deployment_id || 'gpt-4o'}`} 
                    size="small" 
                    variant="outlined"
                    color="secondary"
                  />
                )}
                {agent.voicelive_model && (
                  <Chip 
                    label={`VoiceLive: ${agent.voicelive_model.deployment_id || 'gpt-4o-realtime'}`} 
                    size="small" 
                    variant="outlined"
                    color="secondary"
                  />
                )}
                {agent.model && !agent.cascade_model && !agent.voicelive_model && (
                  <Chip 
                    label={`Model: ${agent.model.deployment_id || agent.model.name || 'Default'}`} 
                    size="small" 
                    variant="outlined"
                  />
                )}
              </Stack>
            </Box>
          )}
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} variant="contained">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ADD HANDOFF POPOVER
// ═══════════════════════════════════════════════════════════════════════════════

function AddHandoffPopover({ anchorEl, open, onClose, fromAgent, agents, existingTargets, onAdd }) {
  const availableAgents = useMemo(() => {
    if (!fromAgent) return [];
    return agents.filter(
      (a) => a.name !== fromAgent.name && !existingTargets.includes(a.name)
    );
  }, [agents, fromAgent, existingTargets]);

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: 'center', horizontal: 'right' }}
      transformOrigin={{ vertical: 'center', horizontal: 'left' }}
      PaperProps={{
        sx: { width: 280, maxHeight: 400, borderRadius: '12px' },
      }}
    >
      <Box sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Add handoff from {fromAgent?.name}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ mb: 2, display: 'block' }}>
          Select target agent
        </Typography>
        
        {availableAgents.length === 0 ? (
          <Alert severity="info" sx={{ borderRadius: '8px' }}>
            No more agents available to add
          </Alert>
        ) : (
          <List dense sx={{ mx: -2 }}>
            {availableAgents.map((agent) => (
              <ListItemButton
                key={agent.name}
                onClick={() => { onAdd(agent); onClose(); }}
                sx={{ borderRadius: '8px', mx: 1 }}
              >
                <ListItemAvatar>
                  <Avatar sx={{ width: 32, height: 32, bgcolor: colors.active.avatar }}>
                    {agent.name?.[0]}
                  </Avatar>
                </ListItemAvatar>
                <ListItemText
                  primary={agent.name}
                  secondary={agent.description}
                  primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                  secondaryTypographyProps={{ variant: 'caption', noWrap: true }}
                />
              </ListItemButton>
            ))}
          </List>
        )}
      </Box>
    </Popover>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// START AGENT SELECTOR
// ═══════════════════════════════════════════════════════════════════════════════

function StartAgentSelector({ agents, selectedStart, onSelect }) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        borderRadius: '12px',
        borderStyle: 'dashed',
        borderColor: '#10b981',
        backgroundColor: '#f0fdf4',
      }}
    >
      <Typography variant="subtitle2" sx={{ mb: 1, color: '#059669' }}>
        <PlayArrowIcon sx={{ fontSize: 16, mr: 0.5, verticalAlign: 'middle' }} />
        Select Starting Agent
      </Typography>
      <FormControl size="small" fullWidth>
        <Select
          value={selectedStart || ''}
          onChange={(e) => onSelect(e.target.value)}
          displayEmpty
        >
          <MenuItem value="" disabled>
            <em>Choose the entry point agent...</em>
          </MenuItem>
          {agents.map((agent) => (
            <MenuItem key={agent.name} value={agent.name}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Avatar 
                  sx={{ 
                    width: 24, 
                    height: 24, 
                    bgcolor: colors.active.avatar, 
                    fontSize: 12 
                  }}
                >
                  {agent.name?.[0]}
                </Avatar>
                <span>{agent.name}</span>
              </Stack>
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </Paper>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// AGENT LIST SIDEBAR
// ═══════════════════════════════════════════════════════════════════════════════

function AgentListSidebar({ agents, graphAgents, onAddToGraph, onEditAgent, onCreateAgent }) {
  const ungraphedAgents = agents.filter((a) => !graphAgents.includes(a.name));

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Create new agent button */}
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
              borderColor: colors.active.border,
              color: colors.active.avatar,
              fontWeight: 600,
              fontSize: 12,
              '&:hover': {
                borderStyle: 'solid',
                backgroundColor: colors.active.bg,
              },
            }}
          >
            Create New Agent
          </Button>
        </Box>
      )}

      {ungraphedAgents.length === 0 ? (
        <Box sx={{ 
          p: 3, 
          textAlign: 'center', 
          color: '#9ca3af', 
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 1,
        }}>
          <SmartToyIcon sx={{ fontSize: 40, opacity: 0.4 }} />
          <Typography variant="body2" sx={{ fontWeight: 500, color: '#6b7280' }}>
            All agents added
          </Typography>
          <Typography variant="caption" sx={{ color: '#9ca3af' }}>
            Drag from graph or reset
          </Typography>
        </Box>
      ) : (
        <Box sx={{ flex: 1, overflowY: 'auto', py: 1 }}>
          {/* Available Agents Section - unified, no session vs built-in distinction */}
          <Box>
            <Box sx={{ 
              px: 1.5, 
              py: 0.75, 
              display: 'flex', 
              alignItems: 'center', 
              gap: 0.5,
              backgroundColor: 'rgba(139, 92, 246, 0.06)',
              borderLeft: '3px solid',
              borderColor: colors.active.avatar,
            }}>
              <SmartToyIcon sx={{ fontSize: 14, color: colors.active.avatar }} />
              <Typography 
                variant="caption" 
                sx={{ 
                  fontWeight: 700, 
                  color: colors.active.avatar,
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  fontSize: 10,
                }}
              >
                Available Agents
              </Typography>
              <Chip 
                label={ungraphedAgents.length} 
                size="small" 
                sx={{ 
                  ml: 'auto', 
                  height: 18, 
                  fontSize: 10,
                  bgcolor: 'rgba(139, 92, 246, 0.1)',
                  color: colors.active.avatar,
                  fontWeight: 600,
                }} 
              />
            </Box>
            <List sx={{ py: 0.5 }}>
              {ungraphedAgents.map((agent) => (
                <ListItem
                  key={agent.name}
                  disablePadding
                  sx={{ 
                    px: 1,
                    '&:hover': {
                      backgroundColor: 'rgba(139, 92, 246, 0.04)',
                    },
                  }}
                >
                  <ListItemButton
                    onClick={() => onAddToGraph(agent)}
                    sx={{ 
                      py: 1, 
                      px: 1,
                      borderRadius: '8px',
                      minHeight: 48,
                    }}
                  >
                    <ListItemAvatar sx={{ minWidth: 40 }}>
                      <Avatar 
                        sx={{ 
                          width: 32, 
                          height: 32, 
                          bgcolor: colors.active.avatar, 
                          fontSize: 13,
                          fontWeight: 600,
                        }}
                      >
                        {agent.name?.[0]}
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText
                      primary={agent.name}
                      secondary={agent.description || 'Click to add to graph'}
                      primaryTypographyProps={{ 
                        variant: 'body2', 
                        fontSize: 13,
                        fontWeight: 500,
                        sx: { lineHeight: 1.3 },
                      }}
                      secondaryTypographyProps={{ 
                        variant: 'caption', 
                        fontSize: 10,
                        sx: { 
                          lineHeight: 1.2,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        },
                      }}
                    />
                    <Stack direction="row" spacing={0.5} sx={{ ml: 0.5 }}>
                      {onEditAgent && (
                        <Tooltip title="Edit">
                          <IconButton 
                            size="small" 
                            onClick={(e) => {
                              e.stopPropagation();
                              onEditAgent(agent, null);
                            }}
                            sx={{ 
                              width: 28, 
                              height: 28,
                              '&:hover': { backgroundColor: 'rgba(139, 92, 246, 0.1)' },
                            }}
                          >
                            <EditIcon sx={{ fontSize: 14, color: colors.active.avatar }} />
                          </IconButton>
                        </Tooltip>
                      )}
                      <Tooltip title="Add to graph">
                        <IconButton 
                          size="small" 
                          onClick={(e) => {
                            e.stopPropagation();
                            onAddToGraph(agent);
                          }}
                          sx={{ 
                            width: 28, 
                            height: 28,
                            backgroundColor: 'rgba(139, 92, 246, 0.08)',
                            '&:hover': { backgroundColor: 'rgba(139, 92, 246, 0.15)' },
                          }}
                        >
                          <AddIcon sx={{ fontSize: 16, color: colors.active.avatar }} />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          </Box>
        </Box>
      )}
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ScenarioBuilder({
  sessionId,
  onScenarioCreated,
  onScenarioUpdated,
  onEditAgent,  // Callback to switch to agent builder for editing: (agent, sessionId) => void
  onCreateAgent, // Callback to switch to agent builder for creating new agent: () => void
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

  // Icon picker state
  const [showIconPicker, setShowIconPicker] = useState(false);
  const iconPickerAnchor = useRef(null);

  // Preset icons for scenarios
  const iconOptions = [
    '🎭', '🎯', '🎪', '🏛️', '🏦', '🏥', '🏢', '📞', '💬', '🤖',
    '🎧', '📱', '💼', '🛒', '🍔', '✈️', '🏨', '🚗', '📚', '⚖️',
    '🎓', '🏋️', '🎮', '🎬', '🎵', '🔧', '💡', '🌟', '❤️', '🌍',
  ];

  // UI state
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [hoveredEdge, setHoveredEdge] = useState(null);
  const [addHandoffAnchor, setAddHandoffAnchor] = useState(null);
  const [addHandoffFrom, setAddHandoffFrom] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [editingHandoff, setEditingHandoff] = useState(null);
  const [viewingAgent, setViewingAgent] = useState(null);

  const canvasRef = useRef(null);

  const isSameHandoff = useCallback((left, right) => {
    if (!left || !right) return false;
    return left.from_agent === right.from_agent && left.to_agent === right.to_agent;
  }, []);

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
      let templates = [];
      
      // Fetch all scenarios for this session (includes both custom and built-in)
      if (sessionId) {
        try {
          const sessionResponse = await fetch(
            `${API_BASE_URL}/api/v1/scenario-builder/session/${sessionId}/scenarios`
          );
          if (sessionResponse.ok) {
            const sessionData = await sessionResponse.json();
            
            // Add session-custom scenarios first (marked as custom)
            if (sessionData.scenarios && sessionData.scenarios.length > 0) {
              const customTemplates = sessionData.scenarios.map((scenario) => ({
                id: `_custom_${scenario.name.replace(/\s+/g, '_').toLowerCase()}`,
                name: `${scenario.icon || '🎭'} ${scenario.name || 'Custom Scenario'}`,
                description: scenario.description || 'Your custom session scenario',
                icon: scenario.icon || '🎭',
                agents: scenario.agents || [],
                start_agent: scenario.start_agent,
                handoffs: scenario.handoffs || [],
                handoff_type: scenario.handoff_type || 'announced',
                global_template_vars: scenario.global_template_vars || {},
                isCustom: true,
                isActive: scenario.is_active,
                originalName: scenario.name,
              }));
              templates = [...templates, ...customTemplates];
            }
            
            // Add built-in scenarios (from scenario store)
            if (sessionData.builtin_scenarios && sessionData.builtin_scenarios.length > 0) {
              const builtinTemplates = sessionData.builtin_scenarios.map((scenario) => ({
                id: scenario.name.toLowerCase().replace(/\s+/g, '_'),
                name: `${scenario.icon || '📋'} ${scenario.name}`,
                description: scenario.description || '',
                icon: scenario.icon || '📋',
                agents: scenario.agents || [],
                start_agent: scenario.start_agent,
                handoffs: scenario.handoffs || [],
                handoff_type: scenario.handoff_type || 'announced',
                global_template_vars: scenario.global_template_vars || {},
                isCustom: false,
                isActive: scenario.is_active,
                originalName: scenario.name,
              }));
              templates = [...templates, ...builtinTemplates];
            }
          }
        } catch (err) {
          logger.debug('Failed to fetch session scenarios, falling back to templates endpoint');
        }
      }
      
      // Fallback: if no session or no scenarios found, fetch from templates endpoint
      if (templates.length === 0) {
        const response = await fetch(`${API_BASE_URL}/api/v1/scenario-builder/templates`);
        if (response.ok) {
          const data = await response.json();
          templates = (data.templates || []).map((t) => ({
            ...t,
            isCustom: false,
            isActive: false,
          }));
        }
      }
      
      // Auto-select the active scenario if one exists
      const activeTemplate = templates.find(t => t.isActive);
      if (activeTemplate) {
        setSelectedTemplate(activeTemplate.id);
      }
      
      setAvailableTemplates(templates);
    } catch (err) {
      logger.error('Failed to fetch templates:', err);
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
      logger.debug('No existing scenario');
    }
  }, [sessionId]);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchAvailableAgents(),
      fetchAvailableTemplates(),
      editMode ? fetchExistingScenario() : Promise.resolve(),
    ]).finally(() => setLoading(false));
  }, [fetchAvailableAgents, fetchAvailableTemplates, fetchExistingScenario, editMode]);

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

  // Validate and clean up config when availableAgents changes
  // Remove invalid agents that no longer exist
  useEffect(() => {
    if (availableAgents.length === 0) return;
    
    const validAgentNames = new Set(availableAgents.map(a => a.name));
    const invalidAgentsFound = [];
    
    setConfig((prev) => {
      let hasChanges = false;
      let newConfig = { ...prev };
      
      // Check if start_agent is valid
      if (prev.start_agent && !validAgentNames.has(prev.start_agent)) {
        invalidAgentsFound.push(prev.start_agent);
        logger.warn(`Invalid start_agent "${prev.start_agent}" removed`);
        newConfig.start_agent = null;
        hasChanges = true;
      }
      
      // Filter out handoffs with invalid agents
      const validHandoffs = prev.handoffs.filter((h) => {
        const fromValid = validAgentNames.has(h.from_agent);
        const toValid = validAgentNames.has(h.to_agent);
        if (!fromValid) invalidAgentsFound.push(h.from_agent);
        if (!toValid) invalidAgentsFound.push(h.to_agent);
        if (!fromValid || !toValid) {
          logger.warn(`Invalid handoff removed: ${h.from_agent} → ${h.to_agent}`);
          hasChanges = true;
          return false;
        }
        return true;
      });
      
      if (validHandoffs.length !== prev.handoffs.length) {
        newConfig.handoffs = validHandoffs;
      }
      
      // Show warning if invalid agents were found
      if (invalidAgentsFound.length > 0) {
        const uniqueInvalid = [...new Set(invalidAgentsFound)];
        setError(`Removed invalid agents from previous session: ${uniqueInvalid.join(', ')}. Click RESET to clear completely.`);
      }
      
      return hasChanges ? newConfig : prev;
    });
  }, [availableAgents]);

  // ─────────────────────────────────────────────────────────────────────────
  // GRAPH LAYOUT CALCULATION
  // ─────────────────────────────────────────────────────────────────────────

  const graphLayout = useMemo(() => {
    const positions = {};
    const agentsInGraph = new Set();

    if (!config.start_agent) {
      return { positions, agentsInGraph: [] };
    }

    // BFS to calculate positions
    const queue = [{ agent: config.start_agent, level: 0, index: 0 }];
    const levelCounts = {};
    const visited = new Set();

    // First pass: count agents per level for vertical centering
    const tempQueue = [{ agent: config.start_agent, level: 0 }];
    const tempVisited = new Set();
    while (tempQueue.length > 0) {
      const { agent, level } = tempQueue.shift();
      if (tempVisited.has(agent)) continue;
      tempVisited.add(agent);
      levelCounts[level] = (levelCounts[level] || 0) + 1;
      
      const outgoing = config.handoffs.filter((h) => h.from_agent === agent);
      outgoing.forEach((h) => {
        if (!tempVisited.has(h.to_agent)) {
          tempQueue.push({ agent: h.to_agent, level: level + 1 });
        }
      });
    }

    // Second pass: assign positions
    const levelIndices = {};
    while (queue.length > 0) {
      const { agent, level } = queue.shift();
      if (visited.has(agent)) continue;
      visited.add(agent);
      agentsInGraph.add(agent);

      // Calculate position
      const currentIndex = levelIndices[level] || 0;
      levelIndices[level] = currentIndex + 1;
      const totalInLevel = levelCounts[level] || 1;
      
      // Center vertically based on number of agents in this level
      const totalHeight = totalInLevel * (NODE_HEIGHT + VERTICAL_GAP) - VERTICAL_GAP;
      const startY = Math.max(60, 200 - totalHeight / 2);
      
      positions[agent] = {
        x: 40 + level * (NODE_WIDTH + HORIZONTAL_GAP),
        y: startY + currentIndex * (NODE_HEIGHT + VERTICAL_GAP),
      };

      // Queue outgoing connections
      const outgoing = config.handoffs.filter((h) => h.from_agent === agent);
      outgoing.forEach((h) => {
        if (!visited.has(h.to_agent)) {
          queue.push({ agent: h.to_agent, level: level + 1 });
        }
      });
    }

    return { positions, agentsInGraph: Array.from(agentsInGraph) };
  }, [config.start_agent, config.handoffs]);

  const handoffPairs = useMemo(() => {
    const pairs = new Set();
    config.handoffs.forEach((handoff) => {
      if (handoff?.from_agent && handoff?.to_agent) {
        pairs.add(`${handoff.from_agent}::${handoff.to_agent}`);
      }
    });
    return pairs;
  }, [config.handoffs]);

  // ─────────────────────────────────────────────────────────────────────────
  // HANDLERS
  // ─────────────────────────────────────────────────────────────────────────

  const handleSetStartAgent = useCallback((agentName) => {
    setConfig((prev) => {
      if (prev.start_agent === agentName) {
        return prev;
      }
      if (!prev.start_agent) {
        return { ...prev, start_agent: agentName };
      }

      const preserved = prev.handoffs.filter((h) => h.from_agent !== prev.start_agent);
      const seen = new Set(preserved.map((h) => `${h.from_agent}::${h.to_agent}`));
      const remapped = [];
      prev.handoffs.forEach((handoff) => {
        if (handoff.from_agent !== prev.start_agent) {
          return;
        }
        const next = { ...handoff, from_agent: agentName };
        const key = `${next.from_agent}::${next.to_agent}`;
        if (seen.has(key)) {
          return;
        }
        seen.add(key);
        remapped.push(next);
      });

      return {
        ...prev,
        start_agent: agentName,
        handoffs: [...preserved, ...remapped],
      };
    });
  }, []);

  const handleOpenAddHandoff = useCallback((agent, event) => {
    setAddHandoffFrom(agent);
    setAddHandoffAnchor(event?.currentTarget || canvasRef.current);
  }, []);

  const handleAddHandoff = useCallback((targetAgent) => {
    if (!addHandoffFrom) return;
    
    const newHandoff = {
      from_agent: addHandoffFrom.name,
      to_agent: targetAgent.name,
      tool: `handoff_${targetAgent.name.toLowerCase().replace(/\s+/g, '_')}`,
      type: config.handoff_type,
      share_context: true,
      handoff_condition: '', // User can define when to trigger this handoff
      context_vars: {},
    };

    setConfig((prev) => ({
      ...prev,
      handoffs: [...prev.handoffs, newHandoff],
    }));

    setAddHandoffFrom(null);
    setAddHandoffAnchor(null);
  }, [addHandoffFrom, config.handoff_type]);

  const handleSelectEdge = useCallback((handoff) => {
    setSelectedEdge(handoff);
    setSelectedNode(null);
  }, []);

  const handleUpdateHandoff = useCallback((updatedHandoff) => {
    setConfig((prev) => ({
      ...prev,
      handoffs: prev.handoffs.map((h) =>
        h.from_agent === updatedHandoff.from_agent && h.to_agent === updatedHandoff.to_agent
          ? updatedHandoff
          : h
      ),
    }));
    setSelectedEdge(null);
  }, []);

  const handleDeleteHandoff = useCallback((handoff) => {
    setConfig((prev) => ({
      ...prev,
      handoffs: prev.handoffs.filter(
        (h) => !(h.from_agent === handoff.from_agent && h.to_agent === handoff.to_agent)
      ),
    }));
    setSelectedEdge(null);
    setEditingHandoff(null);
  }, []);

  const handleApplyTemplate = useCallback(async (templateId) => {
    setLoading(true);
    try {
      // Handle custom session scenarios (IDs starting with _custom_)
      if (templateId.startsWith('_custom_')) {
        const customTemplate = availableTemplates.find(t => t.id === templateId);
        if (customTemplate) {
          setConfig({
            name: customTemplate.originalName || customTemplate.name?.replace('🎭 ', '') || 'Custom Scenario',
            description: customTemplate.description || '',
            icon: customTemplate.icon || '🎭',
            start_agent: customTemplate.start_agent,
            handoff_type: customTemplate.handoff_type || 'announced',
            handoffs: customTemplate.handoffs || [],
            global_template_vars: customTemplate.global_template_vars || {},
          });
          setSelectedTemplate(templateId);
          setSuccess(`Loaded custom scenario: ${customTemplate.originalName || customTemplate.name?.replace('🎭 ', '')}`);
          setTimeout(() => setSuccess(null), 3000);
        }
        setLoading(false);
        return;
      }
      
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
    } finally {
      setLoading(false);
    }
  }, [availableTemplates]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    // Validate agents before saving
    const validAgentNames = new Set(availableAgents.map(a => a.name));
    const invalidAgents = graphLayout.agentsInGraph.filter(name => !validAgentNames.has(name));
    
    if (invalidAgents.length > 0) {
      setError(`Invalid agents: ${invalidAgents.join(', ')}. Please reset and reconfigure the scenario.`);
      setSaving(false);
      return;
    }
    
    if (!config.start_agent) {
      setError('Please select a start agent');
      setSaving(false);
      return;
    }

    try {
      const endpoint = editMode
        ? `${API_BASE_URL}/api/v1/scenario-builder/session/${sessionId}`
        : `${API_BASE_URL}/api/v1/scenario-builder/create?session_id=${sessionId}`;

      const method = editMode ? 'PUT' : 'POST';

      const payload = {
        name: config.name,
        description: config.description,
        icon: config.icon,
        agents: graphLayout.agentsInGraph,
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

      // Refresh templates list to include updated custom scenario
      await fetchAvailableTemplates();
      // Set selected template to the newly saved scenario
      const scenarioTemplateId = `_custom_${config.name.replace(/\s+/g, '_').toLowerCase()}`;
      setSelectedTemplate(scenarioTemplateId);

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
    // Clear session scenario state on the backend
    if (sessionId) {
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/scenario-builder/session/${sessionId}`,
          { method: 'DELETE' }
        );
        if (!response.ok) {
          logger.warn('Failed to clear session scenario on backend');
        }
      } catch (err) {
        logger.warn('Failed to clear session scenario:', err);
      }
    }
    
    // Reset local state
    setConfig({
      name: 'Custom Scenario',
      description: '',
      start_agent: null,
      handoff_type: 'announced',
      handoffs: [],
      global_template_vars: {
        company_name: 'ART Voice Agent',
        industry: 'general',
      },
    });
    setSelectedTemplate(null);
    setSelectedNode(null);
    setSelectedEdge(null);
    setError(null);
    setSuccess('Scenario reset successfully');
    setTimeout(() => setSuccess(null), 2000);
  };

  // Get outgoing handoff counts per agent
  const outgoingCounts = useMemo(() => {
    const counts = {};
    config.handoffs.forEach((h) => {
      counts[h.from_agent] = (counts[h.from_agent] || 0) + 1;
    });
    return counts;
  }, [config.handoffs]);

  // Get existing targets for an agent
  const getExistingTargets = useCallback((agentName) => {
    return config.handoffs
      .filter((h) => h.from_agent === agentName)
      .map((h) => h.to_agent);
  }, [config.handoffs]);

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  const canvasWidth = Math.max(
    800,
    Math.max(...Object.values(graphLayout.positions).map((p) => p.x + NODE_WIDTH + 100), 0)
  );
  const canvasHeight = Math.max(
    400,
    Math.max(...Object.values(graphLayout.positions).map((p) => p.y + NODE_HEIGHT + 60), 0)
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Loading bar */}
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
                  '&:hover': { borderColor: '#9ca3af' },
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
                        borderRadius: 1,
                        bgcolor: config.icon === emoji ? 'primary.light' : 'transparent',
                        '&:hover': { bgcolor: 'action.hover' },
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
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="caption" color="text.secondary">
            Scenarios:
          </Typography>
          {availableTemplates.map((template) => (
            <Chip
              key={template.id}
              label={template.isActive ? `✓ ${template.name}` : template.name}
              size="small"
              icon={selectedTemplate === template.id ? <CheckIcon /> : <HubIcon fontSize="small" />}
              color={template.isActive
                ? 'success'
                : template.isCustom 
                  ? (selectedTemplate === template.id ? 'warning' : 'default')
                  : (selectedTemplate === template.id ? 'primary' : 'default')
              }
              variant={selectedTemplate === template.id || template.isActive ? 'filled' : 'outlined'}
              onClick={() => handleApplyTemplate(template.id)}
              sx={{ 
                cursor: 'pointer',
                ...(template.isActive && {
                  fontWeight: 'bold',
                }),
                ...(template.isCustom && !template.isActive && {
                  borderColor: 'warning.main',
                  '&:hover': { borderColor: 'warning.dark' },
                }),
              }}
            />
          ))}
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

      {/* Main content */}
      <Box sx={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left sidebar - Agent list */}
        <Box
          sx={{
            width: 240,
            minWidth: 240,
            borderRight: '1px solid #e5e7eb',
            backgroundColor: '#fafbfc',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            // Custom scrollbar styling
            '&::-webkit-scrollbar': {
              width: 6,
            },
            '&::-webkit-scrollbar-track': {
              background: 'transparent',
            },
            '&::-webkit-scrollbar-thumb': {
              background: '#d1d1d1',
              borderRadius: 3,
              '&:hover': {
                background: '#b1b1b1',
              },
            },
          }}
        >
          <Box sx={{ 
            p: 1.5, 
            borderBottom: '1px solid #e5e7eb',
            backgroundColor: '#fff',
          }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <SmartToyIcon fontSize="small" sx={{ color: '#6366f1' }} />
              Available Agents
            </Typography>
            <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mt: 0.25 }}>
              Click to set as start agent
            </Typography>
          </Box>
          <AgentListSidebar
            agents={availableAgents}
            graphAgents={graphLayout.agentsInGraph}
            onAddToGraph={(agent) => {
              // Always set the clicked agent as the start agent
              handleSetStartAgent(agent.name);
            }}
            onEditAgent={onEditAgent}
            onCreateAgent={onCreateAgent}
          />
        </Box>

        {/* Canvas area */}
        <Box
          ref={canvasRef}
          sx={{
            flex: 1,
            backgroundColor: '#f8fafc',
            overflow: 'auto',
            position: 'relative',
            // Custom scrollbar styling
            '&::-webkit-scrollbar': {
              width: 10,
              height: 10,
            },
            '&::-webkit-scrollbar-track': {
              background: '#f1f1f1',
              borderRadius: 5,
            },
            '&::-webkit-scrollbar-thumb': {
              background: '#c1c1c1',
              borderRadius: 5,
              '&:hover': {
                background: '#a1a1a1',
              },
            },
            '&::-webkit-scrollbar-corner': {
              background: '#f1f1f1',
            },
          }}
        >
          {/* Empty state - no start agent */}
          {!config.start_agent ? (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                p: 4,
              }}
            >
              <StartAgentSelector
                agents={availableAgents}
                selectedStart={config.start_agent}
                onSelect={handleSetStartAgent}
              />
            </Box>
          ) : (
            /* Visual flow graph */
            <Box
              sx={{
                position: 'relative',
                minWidth: canvasWidth,
                minHeight: canvasHeight,
                p: 2,
              }}
            >
              {/* SVG layer for arrows */}
              <svg
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                  overflow: 'visible',
                }}
              >
                <defs>
                  {/* Forward arrow markers (pointing right) - one for each color */}
                  {connectionColors.map((color, idx) => (
                    <marker
                      key={`arrowhead-${idx}`}
                      id={`arrowhead-${idx}`}
                      markerWidth="12"
                      markerHeight="9"
                      refX="10"
                      refY="4.5"
                      orient="auto"
                    >
                      <polygon points="0 0, 12 4.5, 0 9" fill={color} />
                    </marker>
                  ))}
                  {/* Selected state markers (forward) */}
                  {connectionColors.map((color, idx) => (
                    <marker
                      key={`arrowhead-${idx}-selected`}
                      id={`arrowhead-${idx}-selected`}
                      markerWidth="12"
                      markerHeight="9"
                      refX="10"
                      refY="4.5"
                      orient="auto"
                    >
                      <polygon points="0 0, 12 4.5, 0 9" fill={colors.selected.border} />
                    </marker>
                  ))}
                </defs>

                {/* Render connection arrows */}
                <g style={{ pointerEvents: 'auto' }}>
                  {config.handoffs.map((handoff, idx) => {
                    const fromPos = graphLayout.positions[handoff.from_agent];
                    const toPos = graphLayout.positions[handoff.to_agent];
                    if (!fromPos || !toPos) return null;
                    const reverseKey = `${handoff.to_agent}::${handoff.from_agent}`;
                    const isBidirectional = handoffPairs.has(reverseKey);
                    const offsetSign = handoff.from_agent < handoff.to_agent ? 1 : -1;

                    return (
                      <ConnectionArrow
                        key={`${handoff.from_agent}-${handoff.to_agent}-${idx}`}
                        from={fromPos}
                        to={toPos}
                        type={handoff.type}
                        colorIndex={idx}
                        isBidirectional={isBidirectional}
                        offsetSign={offsetSign}
                        isSelected={isSameHandoff(handoff, selectedEdge)}
                        isHighlighted={isSameHandoff(handoff, hoveredEdge)}
                        onClick={() => {
                          setSelectedEdge(handoff);
                          setEditingHandoff(handoff);
                        }}
                        onMouseEnter={() => setHoveredEdge(handoff)}
                        onMouseLeave={() => setHoveredEdge(null)}
                        onDelete={() => handleDeleteHandoff(handoff)}
                      />
                    );
                  })}
                </g>
              </svg>

              {/* Render nodes */}
              {Object.entries(graphLayout.positions).map(([agentName, position]) => {
                const agent = availableAgents.find((a) => a.name === agentName);
                if (!agent) return null;

                return (
                  <FlowNode
                    key={agentName}
                    agent={agent}
                    isStart={config.start_agent === agentName}
                    isSelected={selectedNode?.name === agentName}
                    position={position}
                    onSelect={setSelectedNode}
                    onAddHandoff={(a) => handleOpenAddHandoff(a, null)}
                    onEditAgent={onEditAgent ? (a) => onEditAgent(a, null) : null}
                    onViewDetails={setViewingAgent}
                    outgoingCount={outgoingCounts[agentName] || 0}
                  />
                );
              })}
            </Box>
          )}
        </Box>

        {/* Right sidebar - Stats */}
        <Box
          sx={{
            width: 220,
            borderLeft: '1px solid #e5e7eb',
            backgroundColor: '#fff',
            p: 2,
          }}
        >
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }}>
            Scenario Stats
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
                Agents in Graph
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {graphLayout.agentsInGraph.length}
              </Typography>
            </Paper>

            <Paper variant="outlined" sx={{ p: 1.5, borderRadius: '10px' }}>
              <Typography variant="caption" color="text.secondary">
                Handoff Routes
              </Typography>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {config.handoffs.length}
              </Typography>
            </Paper>

            <Divider />

            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
              Handoffs
            </Typography>
            {config.handoffs.length === 0 ? (
              <Typography variant="caption" color="text.secondary">
                No handoffs yet. Click + on a node to add.
              </Typography>
            ) : (
              <Stack spacing={0.5}>
                {config.handoffs.map((h, i) => {
                  const handoffColor = connectionColors[i % connectionColors.length];
                  const hasCondition = h.handoff_condition && h.handoff_condition.trim().length > 0;
                  const isActive = isSameHandoff(h, selectedEdge) || isSameHandoff(h, hoveredEdge);
                  return (
                    <Tooltip
                      key={i}
                      title={hasCondition ? `Condition: ${h.handoff_condition}` : 'No handoff condition defined'}
                      placement="left"
                      arrow
                    >
                      <Chip
                        label={`${h.from_agent} → ${h.to_agent}${hasCondition ? ' 📋' : ''}`}
                        size="small"
                        variant="outlined"
                        icon={h.type === 'announced' ? <VolumeUpIcon sx={{ color: `${handoffColor} !important` }} /> : <VolumeOffIcon sx={{ color: `${handoffColor} !important` }} />}
                        onClick={() => {
                          setSelectedEdge(h);
                          setEditingHandoff(h);
                        }}
                        onMouseEnter={() => setHoveredEdge(h)}
                        onMouseLeave={() => setHoveredEdge(null)}
                        onDelete={() => handleDeleteHandoff(h)}
                        sx={{
                          justifyContent: 'flex-start',
                          height: 28,
                          fontSize: 11,
                          borderColor: handoffColor,
                          borderWidth: isActive ? 3 : hasCondition ? 3 : 2,
                          backgroundColor: isActive ? `${handoffColor}1a` : 'transparent',
                          boxShadow: isActive ? `0 0 0 2px ${handoffColor}33` : 'none',
                          '&:hover': {
                            borderColor: handoffColor,
                            backgroundColor: `${handoffColor}15`,
                          },
                        }}
                      />
                    </Tooltip>
                  );
                })}
              </Stack>
            )}
          </Stack>
        </Box>
      </Box>

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

      {/* Add Handoff Popover */}
      <AddHandoffPopover
        anchorEl={addHandoffAnchor}
        open={Boolean(addHandoffAnchor)}
        onClose={() => { setAddHandoffAnchor(null); setAddHandoffFrom(null); }}
        fromAgent={addHandoffFrom}
        agents={availableAgents}
        existingTargets={addHandoffFrom ? getExistingTargets(addHandoffFrom.name) : []}
        onAdd={handleAddHandoff}
      />

      {/* Handoff Editor Dialog */}
      <HandoffEditorDialog
        open={Boolean(editingHandoff)}
        onClose={() => setEditingHandoff(null)}
        handoff={editingHandoff}
        agents={availableAgents}
        scenarioAgents={graphLayout.agentsInGraph}
        handoffs={config.handoffs}
        onSave={handleUpdateHandoff}
        onDelete={() => editingHandoff && handleDeleteHandoff(editingHandoff)}
      />

      {/* Agent Detail Dialog */}
      <AgentDetailDialog
        open={Boolean(viewingAgent)}
        onClose={() => setViewingAgent(null)}
        agent={viewingAgent}
        allAgents={availableAgents}
        handoffs={config.handoffs}
      />
    </Box>
  );
}
