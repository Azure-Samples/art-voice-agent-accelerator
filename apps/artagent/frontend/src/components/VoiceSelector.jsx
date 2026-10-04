import { memo, useMemo, useState } from 'react';
import {
  Autocomplete, Box, FormControlLabel, IconButton, Link, Stack, Switch, TextField, ToggleButton,
  ToggleButtonGroup, Tooltip, Typography,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { authoringAutocompleteSlots } from '../styles/authoringStyles.js';
import { MAI_VOICE_DOCS_URL, MAI_VOICE_PRESETS, isMaiVoice, voiceDisplayLabel } from '../utils/maiSpeech.js';
import {
  ALL_FAMILIES, MULTILINGUAL, VOICE_FAMILIES, buildLanguageOptions, defaultLanguage, familyCounts,
  filterVoices, localeLabel, maiRegionStatus, mergeVoiceOptions, voiceFamily, voiceLocale,
} from '../utils/voiceCatalog.js';

const FAMILY_LABELS = { mai: 'MAI', hd: 'HD', standard: 'Standard' };
const browserLocale = typeof navigator === 'undefined' ? '' : navigator.language;

const DocsLink = () => (
  <Link href={MAI_VOICE_DOCS_URL} target="_blank" rel="noopener noreferrer" underline="hover">
    See supported regions
  </Link>
);

function describeTargets(targets) {
  return targets.map(({ label, region }) => `${region || 'unknown region'} (${label})`).join(' and ');
}

const UNSUPPORTED_ADVICE = {
  cascade: 'Switch to VoiceLive or use a Speech resource in a supported region.',
  voicelive: 'Use a Voice Live resource in a supported region.',
};

function MaiStatus({ status, mode, showAnyway, onShowAnyway }) {
  const supported = status.targets.filter((target) => target.supported);
  const unsupported = status.targets.filter((target) => target.supported === false);
  if (status.state === 'supported') {
    return (
      <Typography variant="caption" color="success.dark" data-testid="mai-region-status">
        MAI voices synthesize on {describeTargets(supported)}.
        {unsupported.length > 0 && ` They will not on ${describeTargets(unsupported)}.`}
      </Typography>
    );
  }
  if (status.state === 'unknown') {
    return (
      <Typography variant="caption" color="text.secondary" data-testid="mai-region-status">
        Can't confirm MAI support for this resource's region. <DocsLink />
      </Typography>
    );
  }
  return (
    <Stack spacing={0.25} data-testid="mai-region-status">
      <Typography variant="caption" color="warning.dark">
        MAI voices aren't available on {describeTargets(unsupported)}.{' '}
        {UNSUPPORTED_ADVICE[mode] || 'Use a resource in a supported region.'} <DocsLink />
      </Typography>
      <FormControlLabel
        control={<Switch size="small" checked={showAnyway} onChange={(event) => onShowAnyway(event.target.checked)} />}
        label={<Typography variant="caption">Select MAI voices anyway</Typography>} />
    </Stack>
  );
}

function provenanceText(metadata, count, loading) {
  const origin = metadata?.region || metadata?.resource_host || 'the configured Speech resource';
  if (loading) return 'Loading the regional Speech voice catalog...';
  if (metadata?.source === 'repository-configurations') {
    return 'Repository voices only. This registration-only backend is not connected to the full regional catalog.';
  }
  if (metadata?.catalog_complete) {
    return `${count} voices from ${origin}${metadata.stale ? ' (stale cache)' : metadata.cached ? ' (cached)' : ''}.`;
  }
  if (metadata?.source === 'static-catalog') return 'Limited starter presets. Regional availability is not verified.';
  if (metadata?.hd_from_catalog) return `${count} catalog voices for ${origin}; documented HD entries are unverified.`;
  if (metadata?.source === 'region-validated') return 'Region-checked presets only. This backend does not expose the full catalog.';
  return '';
}

/**
 * Voice picker shared by Quick Tune and both builders: choose a language
 * (Multilingual and All pinned), narrow by family, then pick a voice. Typing in
 * the voice box searches every language. `mode` selects which resource's region
 * decides MAI support; omit it for agent definitions used by either mode.
 */
const VoiceSelector = memo(function VoiceSelector({
  voices, value, onChange, metadata, loading = false, onRefresh, disabled = false,
  mode, voiceLiveRegion = '',
}) {
  const options = useMemo(
    () => mergeVoiceOptions(voices, metadata?.mai_voice_catalog || MAI_VOICE_PRESETS, value),
    [voices, metadata?.mai_voice_catalog, value],
  );
  const languageOptions = useMemo(() => buildLanguageOptions(options), [options]);
  const selected = options.find((voice) => voice.name === value) || null;
  const [language, setLanguage] = useState(() => defaultLanguage(value, voices, browserLocale));
  const [family, setFamily] = useState(ALL_FAMILIES);
  const [showAnyway, setShowAnyway] = useState(false);
  const [shownValue, setShownValue] = useState(value);
  if (value !== shownValue) {
    // An externally changed voice (another agent, a cross-language search pick)
    // brings the filters to it rather than leaving it hidden.
    setShownValue(value);
    if (selected && !selected.unlisted && !filterVoices([selected], { language, family }).length) {
      setLanguage(voiceLocale(selected) || language);
      setFamily(ALL_FAMILIES);
    }
  }

  const status = useMemo(() => maiRegionStatus({
    mode,
    speechRegion: metadata?.region || '',
    voiceLiveRegion,
    supportedRegions: metadata?.mai_voice_regions || [],
    speechCatalogHasMai: voices.some((voice) => isMaiVoice(voice.name) && voice.region_verified),
  }), [mode, metadata?.region, metadata?.mai_voice_regions, voiceLiveRegion, voices]);
  const maiBlocked = status.state === 'unsupported' && !showAnyway;
  const counts = useMemo(() => familyCounts(options, language), [options, language]);
  const languageValue = languageOptions.find((option) => option.id === language)
    || { id: language, label: localeLabel(language), count: 0 };
  const selectedIsMai = isMaiVoice(selected?.name);
  const total = metadata?.total_available ?? voices.length;
  const provenance = provenanceText(metadata, total, loading);

  return (
    <Stack spacing={0.75} sx={{ minWidth: 0 }} data-testid="voice-selector">
      <Stack direction="row" alignItems="flex-start" gap={0.5}>
        <Autocomplete size="small" fullWidth disabled={disabled} loading={loading}
          options={languageOptions} value={languageValue} disableClearable
          slotProps={authoringAutocompleteSlots}
          getOptionLabel={(option) => option.label}
          getOptionKey={(option) => option.id}
          isOptionEqualToValue={(option, current) => option.id === current.id}
          filterOptions={(items, { inputValue }) => {
            const query = inputValue.toLowerCase().trim();
            return items.filter((item) => !query || `${item.label} ${item.id}`.toLowerCase().includes(query));
          }}
          onChange={(_, option) => option && setLanguage(option.id)}
          renderOption={(props, option) => {
            const { key, ...optionProps } = props;
            return (
              <li key={key} {...optionProps} aria-label={`${option.label}, ${option.count} voices`}>
                <Stack direction="row" justifyContent="space-between" gap={1} sx={{ width: '100%' }}>
                  <Typography variant="body2" fontWeight={option.pinned ? 700 : 400}>{option.label}</Typography>
                  <Typography variant="caption" color="text.secondary">{option.count}</Typography>
                </Stack>
              </li>
            );
          }}
          renderInput={(params) => (
            <TextField {...params} label="Voice language" placeholder="Search languages"
              helperText={language === MULTILINGUAL ? 'Voices that speak many languages' : undefined} />
          )} />
        {onRefresh && (
          <Tooltip title="Refresh regional voice catalog">
            <span><IconButton size="small" aria-label="Refresh regional voice catalog"
              disabled={loading || disabled} onClick={onRefresh} sx={{ mt: 0.5 }}>
              <RefreshIcon fontSize="small" />
            </IconButton></span>
          </Tooltip>
        )}
      </Stack>
      <ToggleButtonGroup size="small" exclusive value={family} disabled={disabled}
        aria-label="Voice family" onChange={(_, next) => next && setFamily(next)}
        sx={{ flexWrap: 'wrap', maxWidth: '100%' }}>
        {VOICE_FAMILIES.map(({ id, label }) => (
          <ToggleButton key={id} value={id} aria-label={`${label} voices`}
            disabled={id !== 'mai' && id !== ALL_FAMILIES && counts[id] === 0}
            sx={{ textTransform: 'none', px: 1.25, py: 0.25 }}>
            {label} <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
              {counts[id]}
            </Typography>
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      <Autocomplete size="small" fullWidth loading={loading} disabled={disabled}
        options={options} value={selected} disableClearable
        slotProps={authoringAutocompleteSlots}
        getOptionLabel={voiceDisplayLabel}
        getOptionKey={(voice) => voice.name}
        getOptionDisabled={(voice) => maiBlocked && isMaiVoice(voice.name)}
        isOptionEqualToValue={(option, current) => option.name === current.name}
        filterOptions={(items, { inputValue }) => filterVoices(items, { language, family, query: inputValue })}
        noOptionsText={family === 'mai'
          ? `No MAI voices for ${languageValue.label}. Try Multilingual or All languages.`
          : 'No voices match. Typing searches every language.'}
        onChange={(_, voice) => voice && onChange(voice.name)}
        renderOption={(props, voice) => {
          const { key, ...optionProps } = props;
          const label = voiceDisplayLabel(voice);
          const locale = localeLabel(voiceLocale(voice));
          const mai = isMaiVoice(voice.name);
          return (
            <li key={key} {...optionProps}
              aria-label={locale ? `${label}, ${locale}, ${voice.name}` : label}>
              <Box sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                <Typography variant="body2" fontWeight={600}>{label}</Typography>
                <Typography variant="caption" color="text.secondary" component="div">
                  {[locale, voice.gender, voice.unlisted ? null : FAMILY_LABELS[voiceFamily(voice)], voice.status]
                    .filter(Boolean).join(' · ')}
                </Typography>
                <Typography variant="caption" color="text.secondary" component="div">{voice.name}</Typography>
                {mai && status.state === 'unsupported' && (
                  <Typography variant="caption" color="warning.dark" component="div">Unsupported region</Typography>
                )}
                {mai && status.state !== 'unsupported' && voice.region_verified === false && (
                  <Typography variant="caption" color="text.secondary" component="div">
                    Documented voice, not listed by this resource's catalog
                  </Typography>
                )}
              </Box>
            </li>
          );
        }}
        renderInput={(params) => <TextField {...params} label="Voice" placeholder="Search name, language, or style" />} />
      {!loading && (family === 'mai' || selectedIsMai) && (
        <MaiStatus status={status} mode={mode} showAnyway={showAnyway} onShowAnyway={setShowAnyway} />
      )}
      {provenance && <Typography variant="caption" color="text.secondary">{provenance}</Typography>}
      {!loading && metadata?.warnings?.map((warning, index) => (
        <Typography key={index} variant="caption" color="warning.dark">{warning}</Typography>
      ))}
      {!loading && selected?.unlisted && metadata?.catalog_complete && (
        <Typography variant="caption" color="warning.dark">
          The current voice was not returned by this resource. It is preserved until you choose another.
        </Typography>
      )}
    </Stack>
  );
});

export default VoiceSelector;
