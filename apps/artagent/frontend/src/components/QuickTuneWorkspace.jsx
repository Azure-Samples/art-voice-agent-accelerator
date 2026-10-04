import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert, Autocomplete, Box, Button, Chip, Divider, Drawer, IconButton,
  LinearProgress, Paper, Stack, Tab, Tabs, TextField, Tooltip, Typography, useMediaQuery,
} from '@mui/material';
import { createTheme, ThemeProvider, useTheme } from '@mui/material/styles';
import CloseIcon from '@mui/icons-material/Close';
import OpenInFullIcon from '@mui/icons-material/OpenInFull';
import CloseFullscreenIcon from '@mui/icons-material/CloseFullscreen';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import RefreshIcon from '@mui/icons-material/Refresh';
import TuneIcon from '@mui/icons-material/Tune';
import useQuickTune from '../hooks/useQuickTune.js';
import useScenarioEditor from '../hooks/useScenarioEditor.js';
import {
  affectsActiveMode, agentKey, liveSettingsPatch, quickTuneRequest, sameConfig, scenarioFlowError,
} from '../utils/quickTune.js';
import QuickTuneAgentEditor from './QuickTuneAgentEditor.jsx';
import ScenarioDraftComposer from './ScenarioDraftComposer.jsx';
import ScenarioFlowEditor from './ScenarioFlowEditor.jsx';
import ScenarioDetailsEditor from './ScenarioDetailsEditor.jsx';
import ScenarioGraphDialog from './ScenarioGraphDialog.jsx';
import ScenarioGraphPreview from './ScenarioGraphPreview.jsx';
import { OrchestrationDiagramModal } from './OrchestrationDiagram.jsx';
import logger from '../utils/logger.js';
import { authoringAutocompleteSlots, authoringSurfaceSx } from '../styles/authoringStyles.js';
import { maiConfigurationError } from '../utils/maiSpeech.js';
import { voiceLiveModelError } from '../utils/foundryModels.js';

const QuickTuneWorkspace = memo(function QuickTuneWorkspace({
  open, onClose, expanded, onExpandedChange, view, onViewChange,
  sessionId, activeAgentName, startAgentName, scenario, scenarios = [], activeMode, recording, callActive,
  onAgentSaved, onScenarioApplied, onAdvanced,
}) {
  const parentTheme = useTheme();
  const workspaceTheme = useMemo(() => createTheme(parentTheme, {
    zIndex: { modal: 13000, tooltip: 13020 },
  }), [parentTheme]);
  const tune = useQuickTune({ open, sessionId, activeAgentName });
  const scenarioEditor = useScenarioEditor({
    open, enabled: view !== 'create', sessionId, activeScenario: scenario, scenarios,
  });
  const { loadCatalog } = tune;
  const [mode, setMode] = useState(activeMode);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [hasScenarioDraft, setHasScenarioDraft] = useState(false);
  const flow = scenarioEditor.entry?.config;
  const flowLoading = scenarioEditor.loading;
  const flowError = scenarioEditor.error;
  const setFlow = scenarioEditor.updateConfig;
  const [showDiagram, setShowDiagram] = useState(false);
  const [showFlowGraph, setShowFlowGraph] = useState(false);
  const [inspectedFlowAgent, setInspectedFlowAgent] = useState(null);
  const [promptScenarioName, setPromptScenarioName] = useState(null);
  const desktop = useMediaQuery('(min-width:1200px)');
  const headingRef = useRef(null);
  const openerRef = useRef(null);
  const connected = recording || callActive;
  const entry = tune.entry;
  const targetIsActive = agentKey(entry?.config.name) === agentKey(activeAgentName) && !entry?.isNew;
  const patch = targetIsActive && connected && activeMode === 'voicelive' && mode === 'voicelive'
    ? liveSettingsPatch(entry?.base, entry?.config) : null;
  // Saving an agent also makes it the session's starting agent.
  const activates = Boolean(entry?.config.name?.trim())
    && agentKey(entry?.config.name) !== agentKey(startAgentName || activeAgentName);
  const reconnect = recording && !patch && (targetIsActive
    ? affectsActiveMode(entry?.base, entry?.config, activeMode) : activates);
  const flowDirty = scenarioEditor.dirty;
  const scenarioAgentNames = tune.catalog.agents.map((agent) => agent.name);
  const flowGraphConfig = flow && !flow.agents?.length ? { ...flow, agents: scenarioAgentNames } : flow;
  const flowValidation = scenarioEditor.jsonError || scenarioFlowError(flowGraphConfig, tune.catalog.tools);
  const toolsReady = !tune.catalogLoading
    && !tune.catalogErrors.some((message) => message.startsWith('Tool catalog'));
  const flowIsCurrent = flow && agentKey(flow.name) === agentKey(scenario?.name);
  const canSaveFlow = flowDirty && !busy && !flowLoading && !connected && toolsReady && !flowValidation
    && !tune.catalogErrors.some((message) => message.startsWith('Agent catalog'));
  const flowSaveLabel = flowIsCurrent ? 'Save scenario' : 'Save & activate';
  const duplicateName = entry?.isNew && tune.catalog.agents.some((agent) => (
    agentKey(agent.name) === agentKey(entry.config.name)
  ));
  const pendingCount = Object.values(tune.entries).filter((item) => (
    item.isNew || !sameConfig(item.base, item.config)
  )).length;
  const promptScopeName = promptScenarioName || scenario?.name;
  const promptScopeEntry = scenarioEditor.entries[agentKey(promptScopeName)];
  const promptScenario = promptScopeEntry?.config
    || scenarios.find((item) => agentKey(item.name) === agentKey(promptScopeName)) || scenario;
  const promptContextNotice = Object.values(promptScopeEntry?.jsonErrors || {}).some(Boolean)
    ? 'Scenario context has invalid JSON. This preview uses the last valid values; fix and save the scenario before connecting.'
    : promptScopeEntry && !sameConfig(promptScopeEntry.base, promptScopeEntry.config)
      ? 'Preview includes an unsaved scenario draft. Save the scenario to use these values at runtime.' : '';

  useEffect(() => {
    if (!open || !desktop) return undefined;
    openerRef.current = document.activeElement;
    const timer = window.setTimeout(() => headingRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(timer);
      openerRef.current?.focus?.();
    };
  }, [open, desktop]);

  useEffect(() => {
    if (!open) setMode(activeMode);
  }, [activeMode, open]);

  const saveAgent = async () => {
    setBusy(true);
    tune.setError('');
    setNotice('');
    const signal = tune.signal();
    const submitted = structuredClone(entry.config);
    let saved = false;
    try {
      const path = `agent-builder/session/${encodeURIComponent(sessionId)}`;
      const data = await quickTuneRequest(
        patch ? `${path}/live-settings?agent_name=${encodeURIComponent(submitted.name)}`
          : `${path}?activate=false${entry.isNew ? '&create_only=true' : ''}`,
        { method: patch ? 'POST' : 'PUT', signal, body: JSON.stringify(patch || submitted) },
      );
      if (patch && !data.applied) throw new Error('The server could not apply these settings. Refresh before retrying.');
      if (signal.aborted) return;
      saved = true;
      tune.markSaved(tune.selectedName, submitted);
      let scenarioName = null;
      if (activates) {
        const query = new URLSearchParams({ agent_name: submitted.name });
        if (scenario?.name) query.set('scenario_name', scenario.name);
        const activated = await quickTuneRequest(`${path.replace('agent-builder', 'scenario-builder')}/start-agent?${query}`, {
          method: 'POST', signal,
        });
        if (signal.aborted) return;
        scenarioName = activated.config?.name || scenario?.name || null;
      }
      await onAgentSaved(submitted, {
        isNew: entry.isNew, reconnect, live: Boolean(patch && data.live), mode, scenarioName,
      });
      if (signal.aborted) return;
      setNotice(patch && data.live ? 'Applied to the running agent.'
        : reconnect ? `Saved. The conversation is reconnecting${activates ? ` with ${submitted.name} as the active agent` : ' with your changes'}.`
          : activates ? `Saved. ${submitted.name} is now the active agent for this session.`
            : 'Saved for the next connection. Other agents and modes keep their settings.');
    } catch (cause) {
      if (signal.aborted) return;
      logger.error('Quick Tune save failed:', cause);
      tune.setError(saved ? `Settings were saved, but the view or connection could not refresh: ${cause.message}` : cause.message);
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  };

  const saveFlow = async () => {
    setBusy(true);
    scenarioEditor.setError('');
    const signal = tune.signal();
    const submitted = structuredClone(flow);
    let saved = false;
    try {
      const data = await quickTuneRequest(`scenario-builder/session/${encodeURIComponent(sessionId)}`, {
        method: 'PUT', signal, body: JSON.stringify(submitted),
      });
      if (!data.config?.name) throw new Error('The server did not confirm a saved scenario.');
      if (signal.aborted) return;
      saved = true;
      scenarioEditor.markSaved(data.config);
      await onScenarioApplied(data.config, []);
      if (!signal.aborted) setNotice('Scenario saved and selected. Start a conversation to try it.');
    } catch (cause) {
      if (!signal.aborted) {
        logger.error('Quick Tune scenario save failed:', cause);
        scenarioEditor.setError(saved
          ? `The scenario was saved, but the view could not refresh: ${cause.message}` : cause.message);
      }
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  };

  const handleScenarioApplied = useCallback(async (config, agents) => {
    await onScenarioApplied(config, agents);
    await loadCatalog();
  }, [onScenarioApplied, loadCatalog]);
  const openFlowGraph = useCallback(() => {
    setInspectedFlowAgent(null);
    setShowFlowGraph(true);
    onViewChange('flow');
    setNotice('');
  }, [onViewChange]);
  const updateFlowGraph = (updater) => setFlow((previous) => {
    const expanded = previous.agents?.length ? previous : { ...previous, agents: scenarioAgentNames };
    const updated = typeof updater === 'function' ? updater(expanded) : updater;
    return !previous.agents?.length
      && sameConfig([...(updated.agents || [])].sort(), [...scenarioAgentNames].sort())
      ? { ...updated, agents: [] } : updated;
  });

  const agentOptions = [
    ...tune.catalog.agents.map((agent) => ({ name: agent.name, label: agent.name })),
    ...Object.entries(tune.entries)
      .filter(([key]) => !tune.catalog.agents.some((agent) => agentKey(agent.name) === key))
      .map(([key, item]) => ({ name: key, label: `${item.config.name} (draft)` })),
  ];
  if (tune.selectedName && !agentOptions.some((agent) => agentKey(agent.name) === agentKey(tune.selectedName))) {
    agentOptions.unshift({ name: tune.selectedName, label: tune.selectedName });
  }
  const applyLabel = entry?.isNew ? 'Save new agent' : patch ? 'Apply live'
    : reconnect ? 'Apply & reconnect' : activates ? 'Save & activate' : 'Save changes';
  const agentSaveDisabled = !tune.dirty || busy || tune.loadingAgent || duplicateName || !entry?.config.name?.trim()
    || (entry?.config.prompt?.trim().length || 0) < 10
    || (mode === 'voicelive' && Boolean(voiceLiveModelError(entry?.config, tune.catalog.models?.voicelive)))
    || Boolean(maiConfigurationError(entry?.config, mode, tune.catalog.voiceMetadata));

  return (
    <ThemeProvider theme={workspaceTheme}>
      <Drawer anchor="right" open={open} variant={desktop ? 'persistent' : 'temporary'} onClose={onClose}
        ModalProps={{ keepMounted: true }}
        sx={{ zIndex: desktop ? 1300 : 12000 }}
        slotProps={{ paper: {
          component: 'aside', role: 'complementary', 'aria-label': 'Quick Tune workspace',
          sx: {
            ...authoringSurfaceSx,
            width: expanded ? 600 : 440, boxSizing: 'border-box',
            maxWidth: { xs: 'calc(100vw - 16px)', sm: 'calc(100vw - 32px)' },
            height: { xs: 'calc(100dvh - 16px)', sm: 'calc(100dvh - 32px)' },
            top: { xs: 8, sm: 16 }, right: { xs: 8, sm: 16 },
            border: '1px solid', borderColor: 'divider', borderRadius: 3,
            boxShadow: '0 12px 40px rgba(15,23,42,0.16)', overflow: 'hidden',
            color: 'text.primary', bgcolor: 'background.paper',
          },
        } }}>
        <Stack sx={{ height: '100%', minHeight: 0 }} onKeyDown={(event) => {
          if (event.key === 'Escape' && !busy) { event.stopPropagation(); onClose(); }
        }}>
          <Box sx={{ px: { xs: 2, sm: 2.5 }, pt: 2, pb: 2, flexShrink: 0 }}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <TuneIcon sx={{ color: 'primary.main', fontSize: 22 }} />
              <Typography component="h2" variant="h6" fontWeight={700} tabIndex={-1} ref={headingRef}
                sx={{ flex: 1, minWidth: 0, outline: 'none' }}>Quick Tune</Typography>
              <Tooltip title={expanded ? 'Compact workspace' : 'Expand workspace'}>
                <IconButton size="small" aria-label={expanded ? 'Compact workspace' : 'Expand workspace'}
                  onClick={() => onExpandedChange(!expanded)}>
                  {expanded ? <CloseFullscreenIcon fontSize="small" /> : <OpenInFullIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
              <IconButton size="small" aria-label="Close Quick Tune" onClick={onClose}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
            <Stack direction="row" alignItems="center" gap={1} sx={{ mt: 0.75 }} flexWrap="wrap">
              <Typography variant="body2" color="text.secondary"
                sx={{ minWidth: 0, maxWidth: '100%' }}>{scenario?.name || 'Current session'}</Typography>
              <Chip label={connected ? 'Conversation running' : 'Ready to try'} size="small" variant="outlined" />
              {(pendingCount > 0 || hasScenarioDraft || scenarioEditor.hasDrafts) && (
                <Chip label="Unsaved draft" size="small" color="warning" variant="outlined" />
              )}
            </Stack>
          </Box>
          <Tabs value={view} variant="scrollable" scrollButtons="auto"
            onChange={(_, next) => { onViewChange(next); setNotice(''); }}
            aria-label="Quick Tune views" sx={{
              px: 1, flexShrink: 0, borderBottom: 1, borderColor: 'divider', bgcolor: 'action.hover',
              '& .MuiTab-root': { textTransform: 'none', minWidth: 0, px: 1.25, flex: '1 0 auto', fontWeight: 600, whiteSpace: 'nowrap' },
            }}>
            <Tab value="tune" label="Tune agent" />
            <Tab value="flow" label="Edit scenario" />
            <Tab value="create" label="Create scenario" />
          </Tabs>
          {(tune.catalogLoading || tune.loadingAgent || busy || flowLoading) && <LinearProgress />}
          <Box sx={{
            overflowY: 'auto', overscrollBehavior: 'contain', flex: 1, minHeight: 0,
            p: { xs: 2, sm: 2.5 },
          }}>
            {tune.catalogErrors.length > 0 && (
              <Alert severity="warning" sx={{ mb: 2 }}
                action={<Button size="small" onClick={tune.loadCatalog}>Retry</Button>}>
                {tune.catalogErrors.map((message) => <Typography variant="body2" key={message}>{message}</Typography>)}
              </Alert>
            )}
            {view !== 'create' && (
              <ScenarioGraphPreview config={flowGraphConfig} agents={tune.catalog.agents}
                name={scenarioEditor.selectedName} loading={flowLoading}
                error={flowError} dirty={flowDirty} disabled={busy}
                onOpen={openFlowGraph} onRetry={scenarioEditor.retry} />
            )}
            <Box hidden={view !== 'tune'} data-testid="quick-tune-agent">
              <Stack spacing={2}>
                <Stack direction="row" spacing={1} alignItems="flex-start">
                  <Autocomplete size="small" fullWidth disableClearable options={agentOptions}
                    sx={{ flex: 1 }} slotProps={authoringAutocompleteSlots}
                    value={agentOptions.find((agent) => agentKey(agent.name) === agentKey(tune.selectedName)) || null}
                    getOptionLabel={(agent) => agent.label}
                    isOptionEqualToValue={(option, value) => agentKey(option.name) === agentKey(value.name)}
                    onChange={(_, agent) => {
                      if (agent) { tune.setSelectedName(agent.name); setPromptScenarioName(null); setNotice(''); }
                    }}
                    disabled={busy}
                    renderInput={(params) => <TextField {...params} label="Agent to tune" />} />
                  <Tooltip title="Duplicate as a new agent">
                    <span><IconButton aria-label="Duplicate agent" disabled={!entry || busy || !toolsReady}
                      onClick={tune.duplicateAgent}><ContentCopyIcon fontSize="small" /></IconButton></span>
                  </Tooltip>
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  {targetIsActive ? 'Editing the selected agent, not the whole scenario.'
                    : 'Editing this agent will not switch the running conversation.'}
                  {' '}Changes stay in this workspace until you apply them.
                </Typography>
                {tune.error && (
                  <Alert severity="error" action={!entry
                    ? <Button size="small" onClick={tune.retryAgent}>Reload</Button>
                    : tune.dirty ? <Button size="small" onClick={saveAgent} disabled={busy}>Retry save</Button> : undefined}>
                    {tune.error}
                  </Alert>
                )}
                {entry && (
                  <QuickTuneAgentEditor key={tune.selectedName} config={entry.config} onChange={tune.updateAgent}
                    sessionId={sessionId} scenario={promptScenario} contextNotice={promptContextNotice}
                    onPromptOpen={() => tune.setSelectedName(tune.selectedName)}
                    saveAction={{ onClick: saveAgent, disabled: agentSaveDisabled, label: busy ? 'Saving...' : applyLabel }}
                    saveError={tune.error} saveNotice={tune.dirty ? '' : notice}
                    tools={tune.catalog.tools} voices={tune.catalog.voices} models={tune.catalog.models}
                    modelMetadata={tune.catalog.modelMetadata}
                    voiceMetadata={tune.catalog.voiceMetadata} voicesLoading={tune.voicesLoading}
                    onRefreshVoices={tune.refreshVoices}
                    assignmentAgents={tune.assignmentAgents} toolsAvailable={toolsReady}
                    assignmentsAvailable={!tune.catalogLoading && !tune.catalogErrors.some((message) => message.startsWith('Agent catalog'))}
                    mode={mode} onModeChange={setMode} isNew={entry.isNew}
                    initialSection={entry.isNew ? 'behavior' : 'voice'} disabled={busy || tune.loadingAgent} />
                )}
                {!entry && !tune.loadingAgent && !tune.catalogLoading && !tune.error && (
                  <Alert severity="info">Select an agent to start, or describe a new scenario.</Alert>
                )}
                {mode !== activeMode && <Alert severity="info">Editing the other orchestration mode. This does not switch the conversation mode.</Alert>}
                {duplicateName && <Alert severity="warning">That agent name already exists. Choose a unique name for this copy.</Alert>}
                {tune.dirty && (
                  <Alert severity="info">
                    {patch ? 'Voice and turn-taking changes can apply instantly.'
                      : reconnect ? 'Applying will reconnect the browser conversation. Your session context is kept.'
                        : callActive && targetIsActive ? 'Saved settings need a new connection. This will not hang up your phone call.'
                          : 'Save these settings for the next connection.'}
                  </Alert>
                )}
                {notice && view === 'tune' && !tune.dirty && <Alert severity="success" role="status">{notice}</Alert>}
              </Stack>
            </Box>
            <Box hidden={view !== 'flow'} data-testid="quick-tune-flow">
              <Stack spacing={2}>
                <Autocomplete size="small" options={scenarios} disableClearable disabled={busy}
                  slotProps={authoringAutocompleteSlots}
                  value={scenarios.find((item) => agentKey(item.name) === agentKey(scenarioEditor.selectedName)) || null}
                  getOptionLabel={(item) => item.name}
                  isOptionEqualToValue={(option, value) => agentKey(option.name) === agentKey(value.name)}
                  onChange={(_, item) => {
                    if (item) { scenarioEditor.select(item.name); setNotice(''); setInspectedFlowAgent(null); }
                  }}
                  renderInput={(params) => <TextField {...params} label="Scenario to edit" />} />
                <Typography variant="body2" color="text.secondary">
                  Edit details, context, agents, and handoffs. Each scenario keeps its own draft until you save.
                </Typography>
                {flowError && <Alert severity="error" action={!flow
                  ? <Button onClick={scenarioEditor.retry}>Retry</Button> : undefined}>{flowError}</Alert>}
                {flow && !flowIsCurrent && (
                  <Alert severity="info">Editing "{flow.name}" does not change the running scenario.
                    Save &amp; activate will select it for your next conversation.</Alert>
                )}
                {flow && (
                  <>
                    <ScenarioDetailsEditor config={flow} onChange={setFlow}
                      jsonDrafts={scenarioEditor.entry.jsonDrafts} jsonErrors={scenarioEditor.entry.jsonErrors}
                      onJsonChange={scenarioEditor.updateJson} disabled={busy || flowLoading} />
                    <Divider />
                    <Typography variant="subtitle2">Agents &amp; handoffs</Typography>
                    <ScenarioFlowEditor scenario={flow} onChange={setFlow} tools={tune.catalog.tools}
                      availableAgents={scenarioAgentNames} allowAllAgents disabled={busy || flowLoading} />
                  </>
                )}
                {flowDirty && flowValidation && <Alert severity="warning">{flowValidation}</Alert>}
                {!flow && !flowLoading && !flowError && <Alert severity="info">Choose a scenario to edit its configuration.</Alert>}
                {connected && <Alert severity="info">You can keep editing. End the current conversation before saving scenario changes.</Alert>}
                {notice && view === 'flow' && !flowDirty && <Alert severity="success">{notice}</Alert>}
              </Stack>
            </Box>
            <Box hidden={view !== 'create'} data-testid="quick-tune-create">
              <ScenarioDraftComposer sessionId={sessionId} catalog={tune.catalog}
                voicesLoading={tune.voicesLoading} onRefreshVoices={tune.refreshVoices}
                assignmentAgents={tune.assignmentAgents}
                catalogLoading={tune.catalogLoading} catalogErrors={tune.catalogErrors}
                connected={connected} onApplied={handleScenarioApplied} onDraftChange={setHasScenarioDraft} />
            </Box>
          </Box>
          <Divider />
          {view === 'tune' && (
            <Stack direction="row" gap={1} flexWrap="wrap"
              sx={{ px: { xs: 2, sm: 2.5 }, py: 1.5, flexShrink: 0, bgcolor: 'background.paper' }}>
              <Button variant="contained" onClick={saveAgent}
                disabled={agentSaveDisabled}
                sx={{ textTransform: 'none', boxShadow: 'none' }}>
                {busy ? 'Saving...' : applyLabel}
              </Button>
              <Button onClick={tune.discardAgent} disabled={!tune.dirty || busy}
                sx={{ textTransform: 'none' }}>Discard changes</Button>
            </Stack>
          )}
          {view === 'flow' && flow && (
            <Stack direction="row" gap={1} flexWrap="wrap" sx={{ px: 2.5, py: 1.5, flexShrink: 0 }}>
              <Button variant="contained" onClick={saveFlow} disabled={!canSaveFlow}>{flowSaveLabel}</Button>
              <Button onClick={scenarioEditor.discard} disabled={!flowDirty || busy}>Discard changes</Button>
            </Stack>
          )}
          <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={0.5}
            sx={{ px: 1.5, py: 1, flexShrink: 0, bgcolor: 'action.hover' }}>
            <Button size="small" onClick={() => onAdvanced(view === 'tune' ? 'agents' : 'scenarios',
              entry?.isNew ? activeAgentName : tune.selectedName)}
              title="Edits saved configuration. Quick Tune drafts stay here." sx={{ textTransform: 'none' }}>
              Advanced Builder
            </Button>
            <Stack direction="row">
              <Button size="small" onClick={() => setShowDiagram(true)} sx={{ textTransform: 'none' }}>How voice works</Button>
              <Tooltip title="Refresh catalogs">
                <span><IconButton size="small" aria-label="Refresh catalogs" onClick={tune.loadCatalog}
                  disabled={tune.catalogLoading || busy}><RefreshIcon fontSize="small" /></IconButton></span>
              </Tooltip>
            </Stack>
          </Stack>
        </Stack>
      </Drawer>
      <OrchestrationDiagramModal open={showDiagram} onClose={() => setShowDiagram(false)}
        initialMode={mode} zIndex={desktop ? 2000 : 13000} />
      {flow && (
        <ScenarioGraphDialog
          open={showFlowGraph}
          onClose={() => setShowFlowGraph(false)}
          title={`Graphical editor - ${flow.name}`}
          subtitle="Drag, connect, and edit routes. Nothing is saved until you save the scenario."
          agents={tune.catalog.agents}
          config={flowGraphConfig}
          onConfigChange={updateFlowGraph}
          layout={scenarioEditor.entry.layout}
          onLayoutChange={scenarioEditor.updateLayout}
          onSelectAgent={setInspectedFlowAgent}
          disabled={busy || flowLoading}
          banner={flowError ? <Alert severity="error">{flowError}</Alert> : null}
          inspector={inspectedFlowAgent ? (() => {
            const agent = tune.catalog.agents.find((item) => agentKey(item.name) === agentKey(inspectedFlowAgent));
            return (
              <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, minWidth: 0 }}>
                <Stack spacing={1.5}>
                  <Typography fontWeight={600}>{inspectedFlowAgent}</Typography>
                  <Typography variant="body2">{agent?.description || 'Existing agent'}</Typography>
                  <Stack direction="row" gap={0.75} flexWrap="wrap">
                    {(agent?.tools || []).map((tool) => <Chip key={tool} label={tool} size="small" variant="outlined" />)}
                  </Stack>
                  <Button size="small" onClick={() => {
                    tune.setSelectedName(inspectedFlowAgent);
                    setPromptScenarioName(flow.name);
                    onViewChange('tune');
                    setShowFlowGraph(false);
                  }} sx={{ alignSelf: 'flex-start' }}>Tune this agent</Button>
                </Stack>
              </Paper>
            );
          })() : null}
          actions={(
            <>
              {flowDirty && flowValidation && <Alert severity="warning" sx={{ flex: 1, py: 0 }}>{flowValidation}</Alert>}
              <Button onClick={() => setShowFlowGraph(false)}>Close</Button>
              <Button variant="contained" onClick={saveFlow}
                disabled={!canSaveFlow}>{flowSaveLabel}</Button>
            </>
          )}
        />
      )}
    </ThemeProvider>
  );
});

export default QuickTuneWorkspace;
