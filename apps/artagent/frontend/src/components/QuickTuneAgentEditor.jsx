import { memo, useId, useMemo, useRef, useState } from 'react';
import {
  Accordion, AccordionDetails, AccordionSummary, Alert, Box, Checkbox,
  Button, Chip, FormControlLabel, MenuItem, Slider, Stack, TextField, ToggleButton,
  ToggleButtonGroup, Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import {
  BYOM_OPTIONS, CASCADE_MODEL_PRESETS, mergeAgentAssignments, parsePercent, toPercent, TRANSCRIPTION_MODELS,
} from '../utils/quickTune.js';
import { MANAGED_VOICELIVE_OPTIONS, voiceLiveModelError } from '../utils/foundryModels.js';
import { crossRegionHint, describeModelSource } from '../utils/foundryRegions.js';
import {
  authoringSelectProps, authoringSurfaceSx,
} from '../styles/authoringStyles.js';
import ToolCatalogPicker from './ToolCatalogPicker.jsx';
import PromptEditorDialog from './PromptEditorDialog.jsx';
import VoiceSelector from './VoiceSelector.jsx';
import {
  DEFAULT_TRANSCRIPTION_MODEL, MAI_TRANSCRIPTION_MODEL, effectiveTranscriptionModel,
  isMaiTranscriptionModel, isMaiVoice, maiConfigurationError, normalizeTranscriptionModel,
  transcriptionHelp, transcriptionModelLabel, useManagedMaiPipeline, voiceLivePipeline,
} from '../utils/maiSpeech.js';

const sectionStyle = {
  border: '1px solid', borderColor: 'divider', borderRadius: '10px !important',
  minWidth: 0,
  '&:before': { display: 'none' },
  '&.Mui-expanded': { m: 0, borderColor: 'primary.light' },
  '& .MuiAccordionDetails-root': { p: 2 },
};

function TuneSlider({ label, value, onChange, min, max, step = 1, unit = '' }) {
  const id = useId();
  return (
    <Box sx={{ px: 0.5, minWidth: 0 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="baseline" gap={1.5}>
        <Typography id={id} variant="body2" sx={{ minWidth: 0 }}>{label}</Typography>
        <Typography variant="body2" color="text.secondary"
          sx={{ flexShrink: 0, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>{value}{unit}</Typography>
      </Stack>
      <Slider aria-labelledby={id} value={value} onChange={(_, next) => onChange(next)}
        min={min} max={max} step={step} size="small" valueLabelDisplay="auto" />
    </Box>
  );
}

const QuickTuneAgentEditor = memo(function QuickTuneAgentEditor({
  config, onChange, tools = [], voices = [], models = null,
  mode = 'voicelive', onModeChange, isNew = false, initialSection = 'voice',
  disabled = false, assignmentAgents = [], toolsAvailable = true, assignmentsAvailable = true,
  sessionId, scenario, contextNotice, onPromptOpen, saveAction, saveError, saveNotice,
  voiceMetadata, voicesLoading = false, onRefreshVoices, modelMetadata,
}) {
  const [section, setSection] = useState(initialSection);
  const [promptEditorOpen, setPromptEditorOpen] = useState(false);
  const sectionId = useId();
  const toolsHeadingRef = useRef(null);
  const set = (key, value) => onChange({ ...config, [key]: value });
  const nested = (key, field, value) => set(key, { ...config[key], [field]: value });
  const voiceLive = mode === 'voicelive';
  const modelKey = voiceLive ? 'voicelive_model' : 'cascade_model';
  const modelId = config[modelKey]?.deployment_id || '';
  const managed = voiceLive && !config.byom?.mode;
  const discovered = models?.[mode];
  const source = modelMetadata?.[mode];
  const otherMode = voiceLive ? 'cascade' : 'voicelive';
  const regionHint = crossRegionHint({
    active: { ...source, label: voiceLive ? 'VoiceLive' : 'Custom Speech' },
    other: { ...modelMetadata?.[otherMode], label: voiceLive ? 'Custom Speech' : 'VoiceLive' },
    app: source?.appRegion,
  });
  const modelError = voiceLive ? voiceLiveModelError(config, discovered) : '';
  const modelOptions = managed ? MANAGED_VOICELIVE_OPTIONS
    : discovered?.length ? discovered : CASCADE_MODEL_PRESETS;
  const allModels = modelId && !modelOptions.some((model) => model.id === modelId)
    ? [{ id: modelId, label: modelId }, ...modelOptions] : modelOptions;
  const voiceName = config.voice?.name || '';
  const routingTools = tools.filter((tool) => tool.is_handoff).map((tool) => tool.name);
  const availableTools = tools.filter((tool) => !tool.is_handoff);
  const selectedTools = (config.tools || []).filter((name) => !routingTools.includes(name));
  const usageAgents = useMemo(() => mergeAgentAssignments(
    assignmentAgents, [{ name: config.name, tools: config.tools }],
  ), [assignmentAgents, config.name, config.tools]);
  const transcription = normalizeTranscriptionModel(voiceLive
    ? config.session?.input_audio_transcription_settings?.model
    : config.speech?.transcription_model) || (voiceLive ? '' : DEFAULT_TRANSCRIPTION_MODEL);
  const transcriptionOptions = [...new Set([
    ...(voiceLive ? TRANSCRIPTION_MODELS : [DEFAULT_TRANSCRIPTION_MODEL, MAI_TRANSCRIPTION_MODEL, 'azure-speech']), transcription,
  ])].filter(Boolean);
  const effectiveModel = effectiveTranscriptionModel(config, mode);
  const maiInput = isMaiTranscriptionModel(effectiveModel);
  const supportedModels = voiceMetadata?.runtime_transcription_models?.[mode] || [];
  const maiSupported = supportedModels.includes(effectiveModel);
  const maiError = maiConfigurationError(config, mode, voiceMetadata ?? null);
  const pipeline = voiceLivePipeline(config);
  const azureOnlyOptions = config.session?.input_audio_transcription_settings || {};
  const hasAzureOnlyOptions = azureOnlyOptions.custom_speech != null || azureOnlyOptions.phrase_list != null;

  const summary = (key, title, detail) => (
    <AccordionSummary ref={key === 'tools' ? toolsHeadingRef : undefined}
      expandIcon={<ExpandMoreIcon />} aria-controls={`${sectionId}-${key}`}
      sx={{
        px: 2, minHeight: 68, textAlign: 'left',
        '& .MuiAccordionSummary-content': { minWidth: 0, my: 1.5, mr: 1.5 },
      }}>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography fontWeight={650} variant="body2">{title}</Typography>
        <Typography variant="caption" color="text.secondary" component="div" noWrap
          title={detail} sx={{ mt: 0.25 }}>
          {detail}
        </Typography>
      </Box>
    </AccordionSummary>
  );

  return (
    <Stack spacing={1.25} useFlexGap component="fieldset" disabled={disabled}
      sx={{
        ...authoringSurfaceSx, border: 0, p: 0, m: 0,
        '& .MuiTextField-root': { bgcolor: 'background.paper' },
      }}>
      <Accordion disableGutters elevation={0} sx={sectionStyle}
        expanded={section === 'behavior'} onChange={(_, expanded) => setSection(expanded ? 'behavior' : '')}>
        {summary('behavior', 'Behavior', config.description || 'Instructions, identity, and greetings')}
        <AccordionDetails id={`${sectionId}-behavior`}>
          <Stack spacing={2}>
            <TextField label="Agent name" value={config.name || ''} size="small"
              onChange={(event) => set('name', event.target.value)}
              slotProps={{ input: { readOnly: !isNew }, htmlInput: { maxLength: 64 } }}
              helperText={isNew ? 'A new agent; existing agents stay unchanged.' : 'Duplicate this agent to create a new one.'} />
            <TextField label="Role" value={config.description || ''} size="small" multiline maxRows={4}
              onChange={(event) => set('description', event.target.value)} />
            <TextField label="Instructions" value={config.prompt || ''} multiline minRows={7} maxRows={18}
              size="small" onChange={(event) => set('prompt', event.target.value)}
              helperText="What should this agent do, and what should it avoid?" />
            <Button variant="outlined" startIcon={<OpenInNewIcon />} onClick={() => {
              onPromptOpen?.();
              setPromptEditorOpen(true);
            }} sx={{ alignSelf: 'flex-start' }}>Open prompt editor</Button>
            <TextField label="First greeting" value={config.greeting || ''} multiline size="small"
              onChange={(event) => set('greeting', event.target.value)} />
            <TextField label="Greeting after a handoff back" value={config.return_greeting || ''}
              multiline size="small" onChange={(event) => set('return_greeting', event.target.value)} />
          </Stack>
        </AccordionDetails>
      </Accordion>

      <Accordion disableGutters elevation={0} sx={sectionStyle}
        slotProps={{ transition: {
          onEntered: () => toolsHeadingRef.current?.scrollIntoView({ block: 'start', inline: 'nearest' }),
        } }}
        expanded={section === 'tools'} onChange={(_, expanded) => setSection(expanded ? 'tools' : '')}>
        {summary('tools', 'Tools', `${selectedTools.length} capabilities selected`)}
        <AccordionDetails id={`${sectionId}-tools`}>
          <Stack spacing={1.5}>
            <Typography variant="body2" color="text.secondary">
              Search by purpose. Open details for inputs and agent assignments.
            </Typography>
            <ToolCatalogPicker tools={availableTools} value={selectedTools} agents={usageAgents}
              disabled={disabled} toolsAvailable={toolsAvailable} assignmentsAvailable={assignmentsAvailable}
              onChange={(names) => set('tools', [
                ...names,
                ...(config.tools || []).filter((name) => routingTools.includes(name)),
              ])} />
            <Typography variant="caption" color="text.secondary">
              Choose only what this agent needs. Handoff tools are managed by scenario routes.
              Connection settings are in Advanced Builder.
            </Typography>
          </Stack>
        </AccordionDetails>
      </Accordion>

      <Accordion disableGutters elevation={0} sx={sectionStyle}
        expanded={section === 'voice'} onChange={(_, expanded) => setSection(expanded ? 'voice' : '')}>
        {summary('voice', 'Voice & model', [modelId, voiceName].filter(Boolean).join(' / ') || 'How the agent sounds and responds')}
        <AccordionDetails id={`${sectionId}-voice`}>
          <Stack spacing={2}>
            <ToggleButtonGroup exclusive fullWidth size="small" value={mode}
              onChange={(_, next) => next && onModeChange?.(next)} aria-label="Settings mode"
              sx={{ '& .MuiToggleButton-root': { px: 1, py: 1, lineHeight: 1.4 } }}>
              <ToggleButton value="cascade" sx={{ textTransform: 'none' }}>Custom Speech</ToggleButton>
              <ToggleButton value="voicelive" sx={{ textTransform: 'none' }}>VoiceLive</ToggleButton>
            </ToggleButtonGroup>
            {voiceLive && (
              <TextField select size="small" label="Model source" value={config.byom?.mode || ''}
                slotProps={{ select: authoringSelectProps }}
                onChange={(event) => set('byom', event.target.value
                  ? { ...config.byom, mode: event.target.value } : null)}
                helperText={pipeline === 'native' ? 'Native realtime audio. MAI transcription requires a text-based pipeline.'
                  : pipeline === 'byom-chat' ? 'BYOM chat pipeline: speech input, your deployed text model, then speech output.'
                    : pipeline === 'managed-chat' ? 'Managed cascade: speech input, a text model, then speech output.'
                      : 'For a custom deployment, select its matching BYOM profile.'}>
                {BYOM_OPTIONS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                ))}
              </TextField>
            )}
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 210px), 1fr))', gap: 2 }}>
              <TextField select size="small" label="Model" value={modelId}
                slotProps={{ select: authoringSelectProps }}
                onChange={(event) => set(modelKey, {
                  ...config[modelKey], deployment_id: event.target.value,
                  name: event.target.value, model_family: null,
                })}
                helperText={(managed ? 'Managed VoiceLive models' : discovered?.length
                  ? 'Deployments from your connected resource' : 'Presets shown. Deployment availability could not be confirmed.')
                  + describeModelSource(source, { managed })}>
                {!modelId && <MenuItem value="">Use configured default</MenuItem>}
                {allModels.map((model) => <MenuItem key={model.id} value={model.id}>{model.label}</MenuItem>)}
              </TextField>
              <VoiceSelector voices={voices} value={voiceName} metadata={voiceMetadata}
                mode={mode} voiceLiveRegion={modelMetadata?.voicelive?.region || ''}
                loading={voicesLoading} onRefresh={onRefreshVoices} disabled={disabled}
                onChange={(name) => isMaiVoice(name)
                  ? set('voice', { ...config.voice, name, type: 'azure-standard', endpoint_id: null })
                  : nested('voice', 'name', name)} />
              <TextField select size="small" label="Input transcription" value={transcription}
                slotProps={{ select: { ...authoringSelectProps, displayEmpty: true }, inputLabel: { shrink: true } }}
                sx={{ gridColumn: '1 / -1' }}
                onChange={(event) => voiceLive
                  ? nested('session', 'input_audio_transcription_settings',
                    { ...azureOnlyOptions, model: event.target.value })
                  : nested('speech', 'transcription_model', event.target.value)}
                helperText={transcriptionHelp(config, mode)}>
                {transcriptionOptions.map((model) => (
                  <MenuItem key={model} value={model} disabled={isMaiTranscriptionModel(model) && !supportedModels.includes(model)}>
                    {transcriptionModelLabel(model)}
                    {isMaiTranscriptionModel(model) && !supportedModels.includes(model) ? ' - backend update required' : ''}
                  </MenuItem>
                ))}
                {voiceLive && <MenuItem value="">Use configured default</MenuItem>}
              </TextField>
              {maiInput && !voiceLive && (config.speech?.candidate_languages?.length || 0) > 1 && (
                <Typography variant="caption" color="text.secondary" sx={{ gridColumn: '1 / -1' }}>
                  MAI detects language automatically; the Azure Speech candidate-language allowlist is not enforced.
                </Typography>
              )}
              <TuneSlider label="Speaking rate" value={parsePercent(config.voice?.rate)}
                min={-50} max={50} unit="%" onChange={(value) => nested('voice', 'rate', toPercent(value))} />
              <TuneSlider label="Pause before reply"
                value={voiceLive ? config.session?.silence_duration_ms ?? 700 : config.speech?.vad_silence_timeout_ms ?? 800}
                min={100} max={3000} step={50} unit=" ms"
                onChange={(value) => voiceLive ? nested('session', 'silence_duration_ms', value)
                  : nested('speech', 'vad_silence_timeout_ms', value)} />
            </Box>
            {modelError && <Alert severity="warning">{modelError}</Alert>}
            {regionHint && (
              <Alert severity="info">
                {regionHint.lines.map((line) => <Typography key={line} variant="body2">{line}</Typography>)}
              </Alert>
            )}
            {maiError && (
              <Alert severity="warning">
                {maiError}
                {voiceLive && maiSupported && !['managed-chat', 'byom-chat'].includes(pipeline) && (
                  <Button size="small" onClick={() => onChange(useManagedMaiPipeline(config))} sx={{ mt: 1 }}>
                    Use managed gpt-4.1
                  </Button>
                )}
                {voiceLive && maiSupported && hasAzureOnlyOptions && (
                  <Button size="small" onClick={() => {
                    const compatible = { ...azureOnlyOptions };
                    delete compatible.custom_speech;
                    delete compatible.phrase_list;
                    nested('session', 'input_audio_transcription_settings', compatible);
                  }} sx={{ mt: 1 }}>Remove Azure-only options</Button>
                )}
                {!voiceLive && maiSupported && (
                  <Button size="small" onClick={() => set('speech', {
                    ...config.speech, enable_diarization: false,
                  })} sx={{ mt: 1 }}>Use MAI live input settings</Button>
                )}
              </Alert>
            )}
            <Accordion disableGutters elevation={0}
              sx={{ '&:before': { display: 'none' }, bgcolor: 'action.hover', borderRadius: 1.5 }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ textAlign: 'left' }}>
                <Typography variant="body2">Fine controls</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={2}>
                  <TextField label="Voice style" size="small" value={config.voice?.style || ''}
                    onChange={(event) => nested('voice', 'style', event.target.value)}
                    helperText="Supported styles depend on the selected voice." />
                  <TuneSlider label="Pitch" value={parsePercent(config.voice?.pitch)} min={-50} max={50} unit="%"
                    onChange={(value) => nested('voice', 'pitch', toPercent(value))} />
                  {voiceLive ? (
                    <>
                      <TuneSlider label="Speech sensitivity" value={config.session?.turn_detection_threshold ?? 0.5}
                        min={0} max={1} step={0.05} onChange={(value) => nested('session', 'turn_detection_threshold', value)} />
                      <TuneSlider label="Audio prefix padding" value={config.session?.prefix_padding_ms ?? 240}
                        min={0} max={1000} step={20} unit=" ms"
                        onChange={(value) => nested('session', 'prefix_padding_ms', value)} />
                      <Chip size="small" variant="outlined" sx={{ alignSelf: 'flex-start' }}
                        label={`Turn detection: ${config.session?.turn_detection_type || 'default'}`} />
                    </>
                  ) : (
                    <FormControlLabel label={maiInput ? 'Semantic turn detection' : 'Semantic speech segmentation'}
                      control={<Checkbox checked={Boolean(config.speech?.use_semantic_segmentation)}
                        onChange={(event) => nested('speech', 'use_semantic_segmentation', event.target.checked)} />} />
                  )}
                </Stack>
              </AccordionDetails>
            </Accordion>
            <PromptEditorDialog open={promptEditorOpen} onClose={() => setPromptEditorOpen(false)}
              value={config.prompt || ''} onChange={(prompt) => set('prompt', prompt)}
              agentName={config.name} templateVars={config.template_vars || {}} tools={config.tools || []}
              sessionId={sessionId} scenario={scenario} mode={mode} disabled={disabled}
              contextNotice={contextNotice} saveAction={saveAction} saveError={saveError} saveNotice={saveNotice} />
          </Stack>
        </AccordionDetails>
      </Accordion>
    </Stack>
  );
});

export default QuickTuneAgentEditor;
