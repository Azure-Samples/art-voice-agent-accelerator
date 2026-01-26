/**
 * ScenarioBuilderFlowy Component
 * ==============================
 * 
 * An alternative scenario builder using the Flowy library for visual flow editing.
 * This component provides a drag-and-drop interface for building agent workflows.
 * 
 * Based on: https://github.com/alyssaxuu/flowy
 * 
 * Features:
 * - Drag agents from sidebar to canvas
 * - Automatic snapping and connection lines
 * - Visual representation of handoff flows
 * - Compatible with existing scenario configuration format
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
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
import AutoFixHighIcon from '@mui/icons-material/AutoFixHigh';
import PersonAddIcon from '@mui/icons-material/PersonAdd';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';

import { API_BASE_URL } from '../config/constants.js';
import logger from '../utils/logger.js';

// Import Flowy styles
import '../styles/flowy.css';

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS & STYLES
// ═══════════════════════════════════════════════════════════════════════════════

const colors = {
  start: { bg: '#ecfdf5', border: '#10b981', avatar: '#059669' },
  active: { bg: '#f5f3ff', border: '#8b5cf6', avatar: '#7c3aed' },
  inactive: { bg: '#f9fafb', border: '#d1d5db', avatar: '#9ca3af' },
  selected: { bg: '#ede9fe', border: '#6366f1', avatar: '#4f46e5' },
  session: { bg: '#fef3c7', border: '#f59e0b', avatar: '#d97706' },
};

// ═══════════════════════════════════════════════════════════════════════════════
// FLOWY CANVAS COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function FlowyCanvasSection({
  agents,
  config,
  onConfigChange,
  // onEditAgent, // Reserved for future use
  // onViewAgent, // Reserved for future use  
  onCreateAgent,
  // sessionId, // Reserved for future use
}) {
  const canvasRef = useRef(null);
  const blocksContainerRef = useRef(null);
  const flowyInitialized = useRef(false);
  const [isFlowyReady, setIsFlowyReady] = useState(false);
  const [draggedAgent, setDraggedAgent] = useState(null);

  // isFlowyReady is used to track initialization state

  // Build block ID from agent name
  const getBlockId = useCallback((agentName) => {
    return `agent-${agentName.toLowerCase().replace(/\s+/g, '-')}`;
  }, []);

  // Get agent color scheme
  const getAgentColorScheme = useCallback((agent, isStart = false) => {
    if (isStart) return colors.start;
    return colors.active;
  }, []);

  // Initialize Flowy
  const initializeFlowy = useCallback(() => {
    if (!canvasRef.current || flowyInitialized.current) return;
    if (typeof window.flowy === 'undefined') {
      console.warn('Flowy library not loaded yet');
      return;
    }

    const onGrab = (block) => {
      const agentName = block?.querySelector('[data-agent-name]')?.dataset?.agentName;
      if (agentName) {
        setDraggedAgent(agentName);
      }
    };

    const onRelease = () => {
      setDraggedAgent(null);
    };

    const onSnap = (block, first, parent) => {
      // Extract agent name from the block's data attribute
      const childAgentName = block?.querySelector('[data-agent-name]')?.dataset?.agentName;
      const parentAgentName = parent?.querySelector('[data-agent-name]')?.dataset?.agentName;

      if (!childAgentName) {
        logger.warn('onSnap: Could not find agent name in block');
        return true; // Allow snap but don't update config
      }

      // First block is the start agent
      if (first) {
        logger.info('Setting start agent:', childAgentName);
        onConfigChange(prev => ({
          ...prev,
          start_agent: childAgentName,
        }));
        return true;
      }

      // Create handoff from parent to child
      if (parentAgentName && childAgentName !== parentAgentName) {
        logger.info('Creating handoff:', parentAgentName, '->', childAgentName);
        onConfigChange(prev => {
          const exists = prev.handoffs?.some(
            h => h.from_agent === parentAgentName && h.to_agent === childAgentName
          );
          
          if (exists) return prev;

          const newHandoff = {
            from_agent: parentAgentName,
            to_agent: childAgentName,
            tool: 'handoff_to_agent',
            type: prev.handoff_type || 'announced',
            share_context: true,
            handoff_condition: '',
            context_vars: {},
          };

          return {
            ...prev,
            handoffs: [...(prev.handoffs || []), newHandoff],
          };
        });
        return true;
      }

      return true;
    };

    const onRearrange = (/* block, parent */) => {
      // When blocks are rearranged, we need to rebuild the handoffs from Flowy's output
      // Return true to keep blocks in their new positions
      logger.info('Blocks rearranged');
      return true;
    };

    try {
      // Get the actual DOM element
      const canvasElement = canvasRef.current;
      window.flowy(canvasElement, onGrab, onRelease, onSnap, onRearrange, 40, 80);
      flowyInitialized.current = true;
      setIsFlowyReady(true);
      logger.info('Flowy initialized successfully on canvas:', canvasElement);
    } catch (err) {
      logger.error('Failed to initialize Flowy:', err);
    }
  }, [onConfigChange]);

  // Delete all blocks
  const handleDeleteAll = useCallback(() => {
    if (typeof window.flowy !== 'undefined') {
      try {
        window.flowy.deleteBlocks();
        onConfigChange(prev => ({
          ...prev,
          start_agent: null,
          handoffs: [],
        }));
      } catch (err) {
        logger.error('Error deleting blocks:', err);
      }
    }
  }, [onConfigChange]);

  // Check for Flowy library
  useEffect(() => {
    const checkFlowy = () => {
      if (typeof window.flowy !== 'undefined') {
        initializeFlowy();
      } else {
        setTimeout(checkFlowy, 100);
      }
    };
    checkFlowy();
  }, [initializeFlowy]);

  return (
    <Box sx={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Draggable blocks sidebar */}
      <Box
        ref={blocksContainerRef}
        sx={{
          width: 240,
          minWidth: 240,
          borderRight: '1px solid #e5e7eb',
          backgroundColor: '#fafbfc',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Create agent button */}
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

        <Box sx={{ 
          p: 1.5, 
          borderBottom: '1px solid #e5e7eb',
          backgroundColor: '#fff',
        }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <DragIndicatorIcon fontSize="small" sx={{ color: '#6366f1' }} />
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Drag to Canvas
            </Typography>
          </Stack>
          <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mt: 0.5 }}>
            First agent becomes the start
          </Typography>
        </Box>

        {/* Agent blocks container - unified, no session vs built-in distinction */}
        <Box id="flowy-blocks" sx={{ flex: 1, overflowY: 'auto', p: 1 }}>
          {agents.length > 0 && (
            <Box>
              <Typography 
                variant="caption" 
                sx={{ 
                  fontWeight: 700, 
                  color: colors.active.avatar,
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                  fontSize: 10,
                  px: 0.5,
                  display: 'block',
                  mb: 1,
                }}
              >
                Available Agents
              </Typography>
              
              {agents.map(agent => {
                const colorScheme = getAgentColorScheme(agent);
                const blockId = getBlockId(agent.name);
                
                return (
                  <Box
                    key={agent.name}
                    className="create-flowy"
                    data-agent-name={agent.name}
                    data-block-id={blockId}
                    sx={{ mb: 1 }}
                  >
                    <input type="hidden" name="blockelemtype" className="blockelemtype" value={blockId} />
                    <input type="hidden" name="blockid" className="blockid" value={blockId} />
                    <input type="hidden" name="agentname" className="agentname" data-agent-name={agent.name} value={agent.name} />
                    <div className="grabme" data-agent-name={agent.name}>
                      <Paper
                        elevation={0}
                        className="agent-block"
                        sx={{
                          background: colorScheme.bg,
                          border: `2px solid ${colorScheme.border}`,
                          borderRadius: '12px',
                          p: 1.25,
                          cursor: 'grab',
                          transition: 'all 0.2s ease',
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
                            {agent.description && (
                              <Typography
                                variant="caption"
                                sx={{
                                  color: '#64748b',
                                  fontSize: 9,
                                  display: 'block',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {agent.description}
                              </Typography>
                            )}
                          </Box>
                        </Stack>
                      </Paper>
                    </div>
                  </Box>
                );
              })}
            </Box>
          )}
        </Box>
      </Box>

      {/* Flowy Canvas */}
      <Box
        sx={{
          flex: 1,
          position: 'relative',
          backgroundColor: '#f8fafc',
          backgroundImage: 'radial-gradient(circle, #d1d5db 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          overflow: 'auto',
        }}
      >
        <Box
          ref={canvasRef}
          id="canvas"
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            minHeight: '100%',
            minWidth: '100%',
            zIndex: 1,
          }}
        />

        {/* Empty state */}
        {!config.start_agent && (
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
              {isFlowyReady ? 'Drag an agent here to start' : 'Loading Flowy...'}
            </Typography>
            <Typography variant="body2" sx={{ color: '#94a3b8', mt: 1 }}>
              {isFlowyReady ? 'The first agent dropped becomes the starting point' : 'Please wait'}
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
          <Tooltip title="Clear all blocks">
            <IconButton
              onClick={handleDeleteAll}
              size="small"
              sx={{
                backgroundColor: 'white',
                border: '1px solid #e5e7eb',
                '&:hover': { backgroundColor: '#fef2f2', borderColor: '#fca5a5' },
              }}
            >
              <DeleteIcon fontSize="small" sx={{ color: '#ef4444' }} />
            </IconButton>
          </Tooltip>
        </Box>

        {/* Drag indicator */}
        {draggedAgent && (
          <Box
            sx={{
              position: 'absolute',
              bottom: 16,
              left: '50%',
              transform: 'translateX(-50%)',
              backgroundColor: 'rgba(99, 102, 241, 0.9)',
              color: 'white',
              px: 2,
              py: 1,
              borderRadius: '20px',
              fontSize: 12,
              fontWeight: 600,
              boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)',
            }}
          >
            Dragging: {draggedAgent}
          </Box>
        )}
      </Box>

      {/* Right sidebar - Stats */}
      <Box
        sx={{
          width: 200,
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
              Handoff Routes
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {config.handoffs?.length || 0}
            </Typography>
          </Paper>

          {config.handoffs?.length > 0 && (
            <>
              <Divider />
              <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                Handoffs
              </Typography>
              <Stack spacing={0.5}>
                {config.handoffs.map((h, i) => (
                  <Chip
                    key={i}
                    label={`${h.from_agent} → ${h.to_agent}`}
                    size="small"
                    variant="outlined"
                    icon={h.type === 'announced' ? <VolumeUpIcon /> : <VolumeOffIcon />}
                    sx={{
                      justifyContent: 'flex-start',
                      height: 26,
                      fontSize: 10,
                    }}
                  />
                ))}
              </Stack>
            </>
          )}
        </Stack>
      </Box>
    </Box>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ScenarioBuilderFlowy({
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

  // Icon picker state
  const [showIconPicker, setShowIconPicker] = useState(false);
  const iconPickerAnchor = useRef(null);
  const iconOptions = [
    '🎭', '🎯', '🎪', '🏛️', '🏦', '🏥', '🏢', '📞', '💬', '🤖',
    '🎧', '📱', '💼', '🛒', '🍔', '✈️', '🏨', '🚗', '📚', '⚖️',
  ];

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
      void err; // Expected when no scenario exists
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
      void err; // Suppress unused variable warning
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    if (!config.start_agent) {
      setError('Please select a start agent by dragging one to the canvas');
      setSaving(false);
      return;
    }

    try {
      const endpoint = editMode
        ? `${API_BASE_URL}/api/v1/scenario-builder/session/${sessionId}`
        : `${API_BASE_URL}/api/v1/scenario-builder/create?session_id=${sessionId}`;

      const method = editMode ? 'PUT' : 'POST';

      // Get all agents in the graph
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
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="caption" color="text.secondary">
            Templates:
          </Typography>
          {availableTemplates.map((template) => (
            <Chip
              key={template.id}
              label={template.name}
              size="small"
              icon={selectedTemplate === template.id ? <CheckIcon /> : <HubIcon fontSize="small" />}
              color={selectedTemplate === template.id ? 'primary' : 'default'}
              variant={selectedTemplate === template.id ? 'filled' : 'outlined'}
              onClick={() => handleApplyTemplate(template.id)}
              sx={{ cursor: 'pointer' }}
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

      {/* Main content - Flowy Canvas */}
      <Box sx={{ flex: 1, overflow: 'hidden' }}>
        <FlowyCanvasSection
          agents={availableAgents}
          config={config}
          onConfigChange={setConfig}
          onEditAgent={onEditAgent}
          onViewAgent={() => {}}
          onCreateAgent={onCreateAgent}
          sessionId={sessionId}
        />
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
          {saving ? 'Saving...' : editMode ? 'Update Scenario' : 'Create Scenario'}
        </Button>
      </Box>
    </Box>
  );
}
