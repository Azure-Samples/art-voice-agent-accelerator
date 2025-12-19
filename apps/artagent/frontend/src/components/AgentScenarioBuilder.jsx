/**
 * AgentScenarioBuilder Component
 * ===============================
 * 
 * A unified builder dialog that combines:
 * - Agent Builder: Create and configure individual agents
 * - Scenario Builder: Create orchestration flows between agents
 * 
 * Users can toggle between modes using a toolbar switch.
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Avatar,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  LinearProgress,
  Stack,
  Chip,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import HubIcon from '@mui/icons-material/Hub';
import EditIcon from '@mui/icons-material/Edit';

import AgentBuilderContent from './AgentBuilderContent.jsx';
import ScenarioBuilder from './ScenarioBuilder.jsx';

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
  modeToggle: {
    backgroundColor: 'rgba(255,255,255,0.1)',
    borderRadius: '12px',
    '& .MuiToggleButton-root': {
      color: 'rgba(255,255,255,0.7)',
      border: 'none',
      padding: '8px 16px',
      textTransform: 'none',
      fontWeight: 600,
      '&.Mui-selected': {
        color: 'white',
        backgroundColor: 'rgba(255,255,255,0.2)',
      },
      '&:hover': {
        backgroundColor: 'rgba(255,255,255,0.15)',
      },
    },
  },
  content: {
    height: 'calc(100% - 72px)', // Subtract header height
    overflow: 'hidden',
  },
  betaChip: {
    color: 'white',
    backgroundColor: 'rgba(255,255,255,0.18)',
    borderColor: 'rgba(255,255,255,0.3)',
    fontWeight: 700,
    letterSpacing: '0.5px',
    height: 22,
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function AgentScenarioBuilder({
  open,
  onClose,
  sessionId,
  sessionProfile = null,
  // Agent callbacks
  onAgentCreated,
  onAgentUpdated,
  existingAgentConfig = null,
  agentEditMode = false,
  // Scenario callbacks
  onScenarioCreated,
  onScenarioUpdated,
  existingScenarioConfig = null,
  scenarioEditMode = false,
  // Initial mode
  initialMode = 'agents',
}) {
  // Mode state: 'agents' or 'scenarios'
  const [mode, setMode] = useState(initialMode);
  
  // Refresh key - increments each time dialog opens to force child components to remount
  const [refreshKey, setRefreshKey] = useState(0);
  
  // Increment refresh key when dialog opens
  useEffect(() => {
    if (open) {
      setRefreshKey((prev) => prev + 1);
    }
  }, [open]);
  
  // Track agent being edited from scenario builder
  const [editingAgentFromScenario, setEditingAgentFromScenario] = useState(null);
  const [editingAgentSessionId, setEditingAgentSessionId] = useState(null);

  const handleModeChange = useCallback((event, newMode) => {
    if (newMode !== null) {
      // Clear editing state when switching modes manually
      if (newMode === 'scenarios') {
        setEditingAgentFromScenario(null);
        setEditingAgentSessionId(null);
      }
      setMode(newMode);
    }
  }, []);

  const handleClose = useCallback(() => {
    // Clear editing state on close
    setEditingAgentFromScenario(null);
    setEditingAgentSessionId(null);
    onClose();
  }, [onClose]);

  // Handler for editing an agent from the scenario builder
  const handleEditAgentFromScenario = useCallback((agent, agentSessionId) => {
    setEditingAgentFromScenario(agent);
    setEditingAgentSessionId(agentSessionId || sessionId);
    setMode('agents');
  }, [sessionId]);

  // Handler for creating a new agent from scenario builder
  const handleCreateAgentFromScenario = useCallback(() => {
    setEditingAgentFromScenario(null);
    setEditingAgentSessionId(null);
    setMode('agents');
  }, []);

  // Wrap agent callbacks to also refresh scenario builder
  const handleAgentCreatedInternal = useCallback((config) => {
    if (onAgentCreated) onAgentCreated(config);
    // Clear editing state after creation
    setEditingAgentFromScenario(null);
    setEditingAgentSessionId(null);
  }, [onAgentCreated]);

  const handleAgentUpdatedInternal = useCallback((config) => {
    if (onAgentUpdated) onAgentUpdated(config);
    // Clear editing state after update
    setEditingAgentFromScenario(null);
    setEditingAgentSessionId(null);
  }, [onAgentUpdated]);

  // Determine if we're in agent edit mode (either from prop or from scenario navigation)
  const isAgentEditMode = agentEditMode || editingAgentFromScenario !== null;
  const effectiveAgentSessionId = editingAgentSessionId || sessionId;

  const getModeTitle = () => {
    if (mode === 'agents') {
      return agentEditMode ? 'Editing Session Agent' : 'Create Custom Agent';
    }
    return scenarioEditMode ? 'Editing Session Scenario' : 'Create Custom Scenario';
  };

  const getModeDescription = () => {
    if (mode === 'agents') {
      return 'Configure AI agents with custom prompts, tools, and voice settings';
    }
    return 'Design agent orchestration flows with handoffs and routing';
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="lg"
      fullWidth
      sx={styles.dialog}
    >
      {/* Header with mode toggle */}
      <DialogTitle sx={styles.header}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Stack direction="row" alignItems="center" spacing={2}>
            <Avatar
              sx={{
                bgcolor: 'rgba(255,255,255,0.15)',
                width: 40,
                height: 40,
              }}
            >
              {mode === 'agents' ? (
                agentEditMode ? <EditIcon /> : <SmartToyIcon />
              ) : (
                scenarioEditMode ? <EditIcon /> : <HubIcon />
              )}
            </Avatar>
            <Box>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {mode === 'agents' ? 'Agent Builder' : 'Scenario Builder'}
                </Typography>
                <Chip
                  label="BETA"
                  size="small"
                  variant="outlined"
                  sx={styles.betaChip}
                />
              </Stack>
              <Typography variant="caption" sx={{ opacity: 0.8 }}>
                {getModeDescription()}
              </Typography>
            </Box>
          </Stack>

          <Stack direction="row" alignItems="center" spacing={3}>
            {/* Mode toggle */}
            <ToggleButtonGroup
              value={mode}
              exclusive
              onChange={handleModeChange}
              size="small"
              sx={styles.modeToggle}
            >
              <ToggleButton value="agents">
                <Tooltip title="Configure individual agents">
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <SmartToyIcon fontSize="small" />
                    <span>Agents</span>
                  </Stack>
                </Tooltip>
              </ToggleButton>
              <ToggleButton value="scenarios">
                <Tooltip title="Design agent orchestration flows">
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <HubIcon fontSize="small" />
                    <span>Scenarios</span>
                  </Stack>
                </Tooltip>
              </ToggleButton>
            </ToggleButtonGroup>

            {/* Session info */}
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
              }}
            >
              <Typography variant="caption" sx={{ color: 'white', opacity: 0.8 }}>
                Session
              </Typography>
              <Typography variant="body2" sx={{ color: 'white', fontFamily: 'monospace' }}>
                {sessionId || 'none'}
              </Typography>
            </Box>

            <IconButton onClick={handleClose} sx={{ color: 'white' }}>
              <CloseIcon />
            </IconButton>
          </Stack>
        </Stack>
      </DialogTitle>

      {/* Content - switches between Agent and Scenario builder */}
      <Box sx={styles.content}>
        {mode === 'agents' ? (
          <AgentBuilderContent
            key={`agent-builder-${effectiveAgentSessionId}-${refreshKey}`}
            sessionId={effectiveAgentSessionId}
            sessionProfile={sessionProfile}
            onAgentCreated={handleAgentCreatedInternal}
            onAgentUpdated={handleAgentUpdatedInternal}
            existingConfig={editingAgentFromScenario || existingAgentConfig}
            editMode={isAgentEditMode}
          />
        ) : (
          <ScenarioBuilder
            key={`scenario-builder-${sessionId}-${refreshKey}`}
            sessionId={sessionId}
            onScenarioCreated={onScenarioCreated}
            onScenarioUpdated={onScenarioUpdated}
            existingConfig={existingScenarioConfig}
            editMode={scenarioEditMode}
            onEditAgent={handleEditAgentFromScenario}
            onCreateAgent={handleCreateAgentFromScenario}
          />
        )}
      </Box>
    </Dialog>
  );
}
