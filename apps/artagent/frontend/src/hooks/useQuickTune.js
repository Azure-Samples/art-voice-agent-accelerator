import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { deriveModelOptions, fetchFoundryModels } from '../utils/foundryModels.js';
import { pickAttribution } from '../utils/foundryRegions.js';
import { pickVoiceMetadata } from '../utils/voiceCatalog.js';
import {
  agentKey, copyAgentConfig, loadEditableAgent, mergeAgentAssignments, quickTuneRequest, sameConfig,
} from '../utils/quickTune.js';
import logger from '../utils/logger.js';

export default function useQuickTune({ open, sessionId, activeAgentName }) {
  const [catalog, setCatalog] = useState({
    agents: [], tools: [], voices: [], voiceMetadata: null, models: null, modelMetadata: {},
  });
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [coreCatalogErrors, setCoreCatalogErrors] = useState([]);
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [voiceError, setVoiceError] = useState('');
  const [selectedName, setSelectedName] = useState(activeAgentName || '');
  const [entries, setEntries] = useState({});
  const [loadingAgent, setLoadingAgent] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const userSelected = useRef(false);
  const catalogVersion = useRef(0);
  const voiceVersion = useRef(0);
  const requestVersion = useRef(0);
  const lifetime = useRef(null);

  useEffect(() => {
    lifetime.current = new AbortController();
    return () => lifetime.current.abort();
  }, []);

  const loadVoices = useCallback(async (force = false) => {
    const version = ++voiceVersion.current;
    const catalogRequest = catalogVersion.current;
    const signal = lifetime.current.signal;
    const current = () => !signal.aborted && version === voiceVersion.current
      && catalogRequest === catalogVersion.current;
    setVoicesLoading(true);
    setVoiceError('');
    try {
      const data = await quickTuneRequest(`agent-builder/voices${force ? '?use_cache=false' : ''}`, { signal });
      if (!Array.isArray(data.voices)) throw new Error('The voice catalog returned an invalid response.');
      if (!current()) return;
      const metadata = pickVoiceMetadata(data);
      setCatalog((previous) => ({ ...previous, voices: data.voices, voiceMetadata: metadata }));
    } catch (cause) {
      if (!current()) return;
      logger.error('Quick Tune voice catalog loading failed:', cause);
      setVoiceError(cause.message);
      setCatalog((previous) => ({
        ...previous,
        voiceMetadata: {
          ...previous.voiceMetadata,
          stale: previous.voices.length > 0,
          warnings: ['Could not refresh the regional voice catalog. Previous selections are preserved.'],
        },
      }));
    } finally {
      if (current()) setVoicesLoading(false);
    }
  }, []);
  const refreshVoices = useCallback(() => loadVoices(true), [loadVoices]);
  const catalogErrors = useMemo(() => [
    ...coreCatalogErrors, ...(voiceError ? [`Voice catalog: ${voiceError}`] : []),
  ], [coreCatalogErrors, voiceError]);

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    const signal = lifetime.current.signal;
    const version = ++catalogVersion.current;
    loadVoices();
    // Deployment discovery is optional and must not hold up basic agent editing.
    ['cascade', 'voicelive'].forEach((mode) => {
      fetchFoundryModels(mode, { signal }).then((result) => {
        if (signal.aborted || version !== catalogVersion.current) return;
        setCatalog((previous) => ({
          ...previous,
          models: { ...previous.models, [mode]: result ? deriveModelOptions(result.models)[mode] : null },
          modelMetadata: { ...previous.modelMetadata, [mode]: result ? pickAttribution(result) : null },
        }));
      });
    });
    const results = await Promise.allSettled([
      quickTuneRequest(`agent-builder/templates?session_id=${encodeURIComponent(sessionId)}`, { signal }),
      quickTuneRequest('agent-builder/tools', { signal }),
    ]);
    if (signal.aborted || version !== catalogVersion.current) return;
    const errors = [];
    const keys = ['agents', 'tools'];
    const labels = ['Agent catalog', 'Tool catalog'];
    const updates = {};
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        errors.push(`${labels[index]}: ${result.reason.message}`);
        return;
      }
      const items = result.value[index === 0 ? 'templates' : keys[index]];
      if (!Array.isArray(items)) {
        errors.push(`${labels[index]} returned an invalid response.`);
      } else {
        updates[keys[index]] = items;
      }
    });
    setCatalog((previous) => ({ ...previous, ...updates }));
    setCoreCatalogErrors(errors);
    setCatalogLoading(false);
  }, [sessionId, loadVoices]);

  useEffect(() => {
    if (!open) return;
    setEntries((previous) => Object.fromEntries(
      Object.entries(previous).filter(([, item]) => item.isNew || !sameConfig(item.base, item.config)),
    ));
    loadCatalog();
  }, [open, loadCatalog]);

  useEffect(() => {
    if (!userSelected.current && activeAgentName) setSelectedName(activeAgentName);
  }, [activeAgentName]);

  const entry = entries[agentKey(selectedName)];
  useEffect(() => {
    if (!open || !selectedName || entry || catalogLoading) {
      setLoadingAgent(false);
      return undefined;
    }
    const controller = new AbortController();
    const version = ++requestVersion.current;
    setLoadingAgent(true);
    setError('');
    const load = async () => {
      try {
        const config = await loadEditableAgent(selectedName, sessionId, catalog.agents, controller.signal);
        if (version !== requestVersion.current || controller.signal.aborted) return;
        setEntries((previous) => ({
          ...previous,
          [agentKey(selectedName)]: { base: config, config, isNew: false },
        }));
      } catch (cause) {
        if (controller.signal.aborted) return;
        logger.error('Quick Tune could not load agent:', cause);
        setError(cause.message);
      } finally {
        if (!controller.signal.aborted && version === requestVersion.current) setLoadingAgent(false);
      }
    };
    load();
    return () => controller.abort();
  }, [open, selectedName, sessionId, catalog.agents, catalogLoading, entry, reload]);

  const updateAgent = useCallback((config) => {
    userSelected.current = true;
    setEntries((previous) => ({
      ...previous,
      [agentKey(selectedName)]: { ...previous[agentKey(selectedName)], config },
    }));
    setError('');
  }, [selectedName]);

  const markSaved = useCallback((name, config) => {
    setEntries((previous) => {
      const next = { ...previous };
      delete next[agentKey(name)];
      next[agentKey(config.name)] = { base: config, config, isNew: false };
      return next;
    });
    setSelectedName(config.name);
    loadCatalog();
  }, [loadCatalog]);

  const duplicateAgent = useCallback(() => {
    if (!entry) return;
    userSelected.current = true;
    const config = copyAgentConfig(entry.config, [
      ...catalog.agents.map((agent) => agent.name),
      ...Object.values(entries).map((item) => item.config.name),
    ], catalog.tools);
    const name = config.name;
    setEntries((previous) => ({
      ...previous,
      [agentKey(name)]: { base: null, config, isNew: true },
    }));
    setSelectedName(name);
    setError('');
  }, [entry, entries, catalog.agents, catalog.tools]);

  const discardAgent = useCallback(() => {
    if (entry?.isNew) {
      setEntries((previous) => {
        const next = { ...previous };
        delete next[agentKey(selectedName)];
        return next;
      });
      setSelectedName(activeAgentName || catalog.agents[0]?.name || '');
    } else if (entry) {
      updateAgent(structuredClone(entry.base));
    }
    setError('');
  }, [entry, selectedName, activeAgentName, catalog.agents, updateAgent]);

  const assignmentAgents = useMemo(() => mergeAgentAssignments(
    catalog.agents,
    Object.values(entries).map((item) => ({
      ...item.config, has_local_draft: item.isNew || !sameConfig(item.base, item.config),
    })),
  ), [catalog.agents, entries]);

  return {
    catalog, catalogErrors, catalogLoading, loadCatalog,
    voicesLoading, refreshVoices,
    entries, assignmentAgents, selectedName, setSelectedName: (name) => {
      userSelected.current = true;
      setSelectedName(name);
      setError('');
    }, entry,
    dirty: Boolean(entry && (entry.isNew || !sameConfig(entry.base, entry.config))),
    loadingAgent, error, setError, updateAgent, markSaved, duplicateAgent, discardAgent,
    retryAgent: () => setReload((value) => value + 1),
    signal: () => lifetime.current.signal,
  };
}
