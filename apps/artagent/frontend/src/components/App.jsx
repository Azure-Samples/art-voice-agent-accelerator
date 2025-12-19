import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Box,
  Button,
  Divider,
  IconButton,
  LinearProgress,
  Typography,
} from '@mui/material';
import SendRoundedIcon from '@mui/icons-material/SendRounded';
import BoltRoundedIcon from '@mui/icons-material/BoltRounded';
import SmartToyRoundedIcon from '@mui/icons-material/SmartToyRounded';
import BuildRoundedIcon from '@mui/icons-material/BuildRounded';
import TemporaryUserForm from './TemporaryUserForm';
import { AcsStreamingModeSelector, RealtimeStreamingModeSelector } from './StreamingModeSelector.jsx';
import ProfileButton from './ProfileButton.jsx';
import ProfileDetailsPanel from './ProfileDetailsPanel.jsx';
import BackendIndicator from './BackendIndicator.jsx';
import HelpButton from './HelpButton.jsx';
import IndustryTag from './IndustryTag.jsx';
import WaveformVisualization from './WaveformVisualization.jsx';
import ConversationControls from './ConversationControls.jsx';
import ChatBubble from './ChatBubble.jsx';
import GraphCanvas from './graph/GraphCanvas.jsx';
import GraphListView from './graph/GraphListView.jsx';
import AgentTopologyPanel from './AgentTopologyPanel.jsx';
import AgentDetailsPanel from './AgentDetailsPanel.jsx';
import AgentBuilder from './AgentBuilder.jsx';
import AgentScenarioBuilder from './AgentScenarioBuilder.jsx';
import useBargeIn from '../hooks/useBargeIn.js';
import { API_BASE_URL, WS_URL } from '../config/constants.js';
import { ensureVoiceAppKeyframes, styles } from '../styles/voiceAppStyles.js';
import {
  buildSystemMessage,
  describeEventData,
  formatEventTypeLabel,
  formatStatusTimestamp,
  inferStatusTone,
  formatAgentInventory,
} from '../utils/formatters.js';
import {
  buildSessionProfile,
  createMetricsState,
  createNewSessionId,
  getOrCreateSessionId,
  setSessionId as persistSessionId,
  toMs,
} from '../utils/session.js';
import logger from '../utils/logger.js';

const STREAM_MODE_STORAGE_KEY = 'artagent.streamingMode';
const STREAM_MODE_FALLBACK = 'voice_live';
const REALTIME_STREAM_MODE_STORAGE_KEY = 'artagent.realtimeStreamingMode';
const REALTIME_STREAM_MODE_FALLBACK = 'realtime';
const PANEL_MARGIN = 16;
// Avoid noisy logging in hot-path streaming handlers unless explicitly enabled
const ENABLE_VERBOSE_STREAM_LOGS = false;

// Infer template id from config path (e.g., /agents/concierge/agent.yaml -> concierge)
const deriveTemplateId = (configPath) => {
  if (!configPath || typeof configPath !== 'string') return null;
  const parts = configPath.split(/[/\\]/).filter(Boolean);
  const agentIdx = parts.lastIndexOf('agents');
  if (agentIdx >= 0 && parts[agentIdx + 1]) return parts[agentIdx + 1];
  return parts.length >= 2 ? parts[parts.length - 2] : null;
};

// Component styles













// Main voice application component
function RealTimeVoiceApp() {
  
  useEffect(() => {
    ensureVoiceAppKeyframes();
  }, []);

  // Component state
  const [messages, setMessages] = useState([]);
  // Keep logs off React state to avoid re-renders on every envelope/audio frame.
  const logBufferRef = useRef("");
  const [recording, setRecording] = useState(false);
  const [micMuted, setMicMuted] = useState(false);
  const [targetPhoneNumber, setTargetPhoneNumber] = useState("");
  const [callActive, setCallActive] = useState(false);
  const [activeSpeaker, setActiveSpeaker] = useState(null);
  const [showPhoneInput, setShowPhoneInput] = useState(false);
  const [showRealtimeModePanel, setShowRealtimeModePanel] = useState(false);
  const [pendingRealtimeStart, setPendingRealtimeStart] = useState(false);
  const [agentInventory, setAgentInventory] = useState(null);
  const [agentDetail, setAgentDetail] = useState(null);
  const [sessionAgentConfig, setSessionAgentConfig] = useState(null);
  const [sessionScenarioConfig, setSessionScenarioConfig] = useState(null);
  const [showAgentsPanel, setShowAgentsPanel] = useState(false);
  const [selectedAgentName, setSelectedAgentName] = useState(null);
  const [realtimePanelCoords, setRealtimePanelCoords] = useState({ top: 0, left: 0 });
  const [chatWidth, setChatWidth] = useState(1040);
  const [isResizingChat, setIsResizingChat] = useState(false);
  const chatWidthRef = useRef(chatWidth);
  const resizeStartXRef = useRef(0);
  const mainShellRef = useRef(null);
  const [systemStatus, setSystemStatus] = useState({
    status: "checking",
    acsOnlyIssue: false,
  });
  const streamingModeOptions = AcsStreamingModeSelector.options ?? [];
  const realtimeStreamingModeOptions = RealtimeStreamingModeSelector.options ?? [];
  const allowedStreamModes = streamingModeOptions.map((option) => option.value);
  const fallbackStreamMode = allowedStreamModes.includes(STREAM_MODE_FALLBACK)
    ? STREAM_MODE_FALLBACK
    : allowedStreamModes[0] || STREAM_MODE_FALLBACK;
  const allowedRealtimeStreamModes = realtimeStreamingModeOptions.map((option) => option.value);
  const fallbackRealtimeStreamMode = allowedRealtimeStreamModes.includes(
    REALTIME_STREAM_MODE_FALLBACK,
  )
    ? REALTIME_STREAM_MODE_FALLBACK
    : allowedRealtimeStreamModes[0] || REALTIME_STREAM_MODE_FALLBACK;
  const [selectedStreamingMode, setSelectedStreamingMode] = useState(() => {
    const allowed = new Set(allowedStreamModes);
    if (typeof window !== 'undefined') {
      try {
        const stored = window.localStorage.getItem(STREAM_MODE_STORAGE_KEY);
        if (stored && allowed.has(stored)) {
          return stored;
        }
      } catch (err) {
        logger.warn('Failed to read stored streaming mode preference', err);
      }
    }
    const envMode = (import.meta.env.VITE_ACS_STREAMING_MODE || '').toLowerCase();
    if (envMode && allowed.has(envMode)) {
      return envMode;
    }
    return fallbackStreamMode;
  });
  const [selectedRealtimeStreamingMode, setSelectedRealtimeStreamingMode] = useState(() => {
    const allowed = new Set(allowedRealtimeStreamModes);
    if (typeof window !== 'undefined') {
      try {
        const stored = window.localStorage.getItem(REALTIME_STREAM_MODE_STORAGE_KEY);
        if (stored && allowed.has(stored)) {
          return stored;
        }
      } catch (err) {
        logger.warn('Failed to read stored realtime streaming mode preference', err);
      }
    }
    const envMode = (import.meta.env.VITE_REALTIME_STREAMING_MODE || '').toLowerCase();
    if (envMode && allowed.has(envMode)) {
      return envMode;
    }
    return fallbackRealtimeStreamMode;
  });
  const [sessionProfiles, setSessionProfiles] = useState({});
  // Session ID must be declared before scenario helpers that use it
  const [sessionId, setSessionId] = useState(() => getOrCreateSessionId());
  
  // Scenario selection state - now per session
  const [showScenarioMenu, setShowScenarioMenu] = useState(false);
  const scenarioButtonRef = useRef(null);
  
  // Helper to get scenario for current session (default: banking)
  const getSessionScenario = useCallback((sessId = sessionId) => {
    return sessionProfiles[sessId]?.scenario || 'banking';
  }, [sessionProfiles, sessionId]);
  
  // Helper to set scenario for current session
  const setSessionScenario = useCallback((scenario, sessId = sessionId) => {
    setSessionProfiles(prev => ({
      ...prev,
      [sessId]: { ...prev[sessId], scenario }
    }));
  }, [sessionId]);
  
  // Helper to get scenario icon from session config (falls back to scenario type icons)
  const getSessionScenarioIcon = useCallback(() => {
    const scenario = getSessionScenario();
    // First check if we have a custom scenario with an icon in sessionScenarioConfig
    if (sessionScenarioConfig?.scenarios) {
      const activeScenario = sessionScenarioConfig.scenarios.find(s => 
        s.name && `custom_${s.name.replace(/\s+/g, '_').toLowerCase()}` === scenario
      );
      if (activeScenario?.icon) {
        return activeScenario.icon;
      }
    }
    // Fall back to type-based icons
    if (scenario?.startsWith('custom_')) return '🎭';
    if (scenario === 'banking') return '🏦';
    return '🛡️'; // insurance default
  }, [getSessionScenario, sessionScenarioConfig]);
  // Profile menu state moved to ProfileButton component
  const [editingSessionId, setEditingSessionId] = useState(false);
  const [pendingSessionId, setPendingSessionId] = useState(() => getOrCreateSessionId());
  const [sessionUpdating, setSessionUpdating] = useState(false);
  const [sessionUpdateError, setSessionUpdateError] = useState(null);
  const [currentCallId, setCurrentCallId] = useState(null);
  const [showAgentPanel, setShowAgentPanel] = useState(false);
  const [showTextInput, setShowTextInput] = useState(false);
  const [textInput, setTextInput] = useState("");
  const [graphEvents, setGraphEvents] = useState([]);
  const graphEventCounterRef = useRef(0);
  const currentAgentRef = useRef("Concierge");
  const [mainView, setMainView] = useState("chat"); // chat | graph | timeline
  const [lastUserMessage, setLastUserMessage] = useState(null);
  const [lastAssistantMessage, setLastAssistantMessage] = useState(null);

  const appendLog = useCallback((message) => {
    const line = `${new Date().toLocaleTimeString()} - ${message}`;
    logBufferRef.current = logBufferRef.current
      ? `${logBufferRef.current}\n${line}`
      : line;
    logger.debug(line);
  }, []);

  const appendGraphEvent = useCallback((event) => {
    graphEventCounterRef.current += 1;
    const ts = event.ts || event.timestamp || new Date().toISOString();
    setGraphEvents((prev) => {
      const trimmed = prev.length > 120 ? prev.slice(prev.length - 120) : prev;
      return [...trimmed, { ...event, ts, id: `${ts}-${graphEventCounterRef.current}` }];
    });
  }, []);

  const fetchSessionAgentConfig = useCallback(async (targetSessionId = sessionId) => {
    if (!targetSessionId) return;
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/agent-builder/session/${encodeURIComponent(targetSessionId)}`
      );
      if (res.status === 404) {
        setSessionAgentConfig(null);
        return;
      }
      if (!res.ok) return;
      const data = await res.json();
      setSessionAgentConfig(data);
    } catch (err) {
      appendLog(`Session agent fetch failed: ${err.message}`);
    }
  }, [sessionId, appendLog]);

  useEffect(() => {
    fetchSessionAgentConfig();
  }, [fetchSessionAgentConfig]);

  // Fetch all session scenarios (for custom scenarios list)
  const fetchSessionScenarioConfig = useCallback(async (targetSessionId = sessionId) => {
    if (!targetSessionId) return;
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/scenario-builder/session/${encodeURIComponent(targetSessionId)}/scenarios`
      );
      if (res.status === 404) {
        setSessionScenarioConfig(null);
        return;
      }
      if (!res.ok) return;
      const data = await res.json();
      // Store the scenarios array
      setSessionScenarioConfig(data.scenarios && data.scenarios.length > 0 ? data : null);
    } catch (err) {
      appendLog(`Session scenarios fetch failed: ${err.message}`);
    }
  }, [sessionId, appendLog]);

  useEffect(() => {
    fetchSessionScenarioConfig();
  }, [fetchSessionScenarioConfig]);

  // Chat width resize listeners (placed after state initialization)
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizingChat) return;
      const delta = e.clientX - resizeStartXRef.current;
      const next = Math.min(1320, Math.max(900, chatWidthRef.current + delta));
      setChatWidth(next);
    };
    const handleMouseUp = () => {
      if (isResizingChat) {
        chatWidthRef.current = chatWidth;
        setIsResizingChat(false);
      }
    };
    if (isResizingChat) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizingChat, chatWidth]);

  // Preload agent inventory from the health/agents endpoint so the topology can render before the first event.
  const activeAgentNameRaw =
    selectedAgentName ||
    currentAgentRef.current ||
    agentInventory?.startAgent ||
    (agentInventory?.agents && agentInventory.agents[0]?.name) ||
    "Concierge";
  const activeAgentName = (activeAgentNameRaw || "").trim();

  const activeAgentInfo = useMemo(() => {
    if (agentDetail && (agentDetail.name || "").toLowerCase().trim() === activeAgentName.toLowerCase()) {
      return agentDetail;
    }
    if (!agentInventory?.agents) return null;
    const target = activeAgentName.toLowerCase();
    return (
      agentInventory.agents.find((a) => (a.name || "").toLowerCase().trim() === target) ||
      null
    );
  }, [agentInventory, agentDetail, activeAgentName]);

  const resolvedAgentName = activeAgentInfo?.name || activeAgentName;

  const resolvedAgentTools = useMemo(() => {
    if (!activeAgentInfo) return [];
    return Array.isArray(activeAgentInfo.tools) ? activeAgentInfo.tools : [];
  }, [activeAgentInfo]);

  const resolvedHandoffTools = useMemo(
    () => (Array.isArray(activeAgentInfo?.handoff_tools) ? activeAgentInfo.handoff_tools : []),
    [activeAgentInfo]
  );

  const fetchAgentInventory = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/agents`);
      if (!res.ok) return;
      const data = await res.json();
      const agents = Array.isArray(data.agents) && data.agents.length > 0
        ? data.agents
        : (Array.isArray(data.summaries) ? data.summaries : []);
      if (!Array.isArray(agents) || agents.length === 0) return;
      const normalized = {
        agents: agents.map((a) => ({
          name: a.name,
          description: a.description,
          model: a.model?.deployment_id || a.model || null,
          voice: a.voice?.current_voice || a.voice || null,
          tools: a.tools || a.tool_names || a.toolNames || a.tools_preview || [],
          handoffTools: a.handoff_tools || a.handoffTools || [],
          toolCount:
            a.tool_count ??
            a.toolCount ??
            (a.tools?.length ?? a.tool_names?.length ?? a.tools_preview?.length ?? 0),
          templateId: deriveTemplateId(a.config_path || a.configPath || a.configPathname),
          configPath: a.config_path || a.configPath || null,
        })),
        startAgent: data.start_agent || data.startAgent || null,
          scenario: data.scenario || null,
          handoffMap: data.handoff_map || data.handoffMap || {},
        };
        setAgentInventory(normalized);
        if (
          normalized.startAgent &&
          (currentAgentRef.current === "Concierge" || !currentAgentRef.current)
        ) {
          currentAgentRef.current = normalized.startAgent;
        setSelectedAgentName(normalized.startAgent);
      }
    } catch (err) {
      appendLog(`Agent preload failed: ${err.message}`);
    }
  }, [appendLog]);

  useEffect(() => {
    fetchAgentInventory();
  }, [fetchAgentInventory]);

  useEffect(() => {
    setPendingSessionId(sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (sessionAgentConfig?.config?.name) {
      const name = sessionAgentConfig.config.name;
      setSelectedAgentName((prev) => prev || name);
      currentAgentRef.current = name;
    }
  }, [sessionAgentConfig]);

  useEffect(() => {
    let cancelled = false;
    const fetchAgentDetail = async () => {
      if (!resolvedAgentName) return;
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/v1/agents/${encodeURIComponent(resolvedAgentName)}?session_id=${encodeURIComponent(sessionId)}`
        );
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        setAgentDetail(data);
      } catch (err) {
        appendLog(`Agent detail fetch failed: ${err.message}`);
      }
    };
    fetchAgentDetail();
    return () => {
      cancelled = true;
    };
  }, [resolvedAgentName, sessionId, appendLog]);

  useEffect(() => {
    if (!showAgentPanel) return;
    fetchSessionAgentConfig();
  }, [showAgentPanel, fetchSessionAgentConfig, resolvedAgentName]);

  const resolveAgentLabel = useCallback((payload, fallback = null) => {
    if (!payload || typeof payload !== "object") {
      return fallback;
    }
    return (
      payload.active_agent_label ||
      payload.agent_label ||
      payload.agentLabel ||
      payload.agent_name ||
      payload.agentName ||
      payload.speaker ||
      payload.sender ||
      fallback
    );
  }, []);

  const effectiveAgent = useCallback(() => {
    const label = currentAgentRef.current;
    if (label && label !== "System" && label !== "User") return label;
    return null;
  }, []);

  const handleSendText = useCallback(() => {
    if (!textInput.trim()) return;
    
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      // BARGE-IN: Stop TTS audio playback before sending text
      // NOTE: We do NOT suspend the recording context (microphone) because
      // the user should still be able to speak after sending text
      
      // 1. Stop TTS playback audio context (speaker output) to interrupt agent speech
      if (playbackAudioContextRef.current && playbackAudioContextRef.current.state === "running") {
        playbackAudioContextRef.current.suspend();
        appendLog("🛑 TTS playback interrupted by user text input");
      }
      
      // 2. Clear the audio playback queue to stop any buffered agent audio
      if (pcmSinkRef.current) {
        pcmSinkRef.current.port.postMessage({ type: 'clear' });
      }
      
      // Send as raw text message
      const userText = textInput.trim();
      socketRef.current.send(userText);

      // Let backend echo the user message to avoid duplicate bubbles
      appendLog(`User (text): ${userText}`);
      setActiveSpeaker("User");
      setTextInput("");
    } else {
      appendLog("⚠️ Cannot send text: WebSocket not connected");
    }
  }, [textInput, appendLog]);

  const appendSystemMessage = useCallback((text, options = {}) => {
    const timestamp = options.timestamp ?? new Date().toISOString();

    if (options.variant === "session_stop") {
      const dividerLabel =
        options.dividerLabel ?? `Session paused · ${formatStatusTimestamp(timestamp)}`;
      setMessages((prev) => [
        ...prev,
        {
          type: "divider",
          label: dividerLabel,
          timestamp,
        },
      ]);
      return;
    }

    const baseMessage = buildSystemMessage(text, { ...options, timestamp });
    const shouldInsertDivider = options.withDivider === true;
    const dividerLabel = shouldInsertDivider
      ? options.dividerLabel ?? `Call disconnected · ${formatStatusTimestamp(timestamp)}`
      : null;
    setMessages((prev) => [
      ...prev,
      baseMessage,
      ...(shouldInsertDivider
        ? [
            {
              type: "divider",
              label: dividerLabel,
              timestamp,
            },
          ]
        : []),
    ]);
  }, [setMessages]);

  const validateSessionId = useCallback(
    async (id) => {
      if (!id) return false;
      const pattern = /^session_[0-9]{6,}_[A-Za-z0-9]+$/;
      if (!pattern.test(id)) {
        setSessionUpdateError("Session ID must match pattern: session_<timestamp>_<suffix>");
        return false;
      }
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/v1/metrics/session/${encodeURIComponent(id)}`
        );
        return res.ok;
      } catch (err) {
        appendLog(`Session validation failed: ${err.message}`);
        return false;
      }
    },
    [appendLog]
  );

  const handleSessionIdSave = useCallback(async () => {
    const target = (pendingSessionId || "").trim();
    if (!target) {
      setSessionUpdateError("Session ID is required");
      return;
    }
    if (target === sessionId) {
      setEditingSessionId(false);
      setSessionUpdateError(null);
      return;
    }
    setSessionUpdating(true);
    const isValid = await validateSessionId(target);
    if (isValid) {
      persistSessionId(target);
      setSessionId(target);
      setPendingSessionId(target);
      setSessionUpdateError(null);
      setEditingSessionId(false);
      await fetchSessionAgentConfig(target);
    } else {
      setSessionUpdateError("Session not found or inactive. Reverting.");
      setPendingSessionId(sessionId);
    }
    setSessionUpdating(false);
  }, [pendingSessionId, sessionId, validateSessionId, fetchSessionAgentConfig]);

  const handleSessionIdCancel = useCallback(() => {
    setPendingSessionId(sessionId);
    setSessionUpdateError(null);
    setEditingSessionId(false);
  }, [sessionId]);

  const handleSystemStatus = useCallback((nextStatus = { status: "checking", acsOnlyIssue: false }) => {
    setSystemStatus((prev) => {
      const hasChanged =
        !prev ||
        prev.status !== nextStatus.status ||
        prev.acsOnlyIssue !== nextStatus.acsOnlyIssue;

      if (hasChanged && nextStatus?.status) {
        appendLog(
          `Backend status: ${nextStatus.status}${
            nextStatus.acsOnlyIssue ? " (ACS configuration issue)" : ""
          }`,
        );
      }

      return hasChanged ? nextStatus : prev;
    });
  }, [appendLog]);

  const [showDemoForm, setShowDemoForm] = useState(false);
  const openDemoForm = useCallback(() => setShowDemoForm(true), [setShowDemoForm]);
  const closeDemoForm = useCallback(() => setShowDemoForm(false), [setShowDemoForm]);
  const [showAgentBuilder, setShowAgentBuilder] = useState(false);
  const [showAgentScenarioBuilder, setShowAgentScenarioBuilder] = useState(false);
  const [builderInitialMode, setBuilderInitialMode] = useState('agents');
  const [createProfileHovered, setCreateProfileHovered] = useState(false);
  const demoFormCloseTimeoutRef = useRef(null);
  const profileHighlightTimeoutRef = useRef(null);
  const [profileHighlight, setProfileHighlight] = useState(false);
  const [showProfilePanel, setShowProfilePanel] = useState(false);
  const lastProfileIdRef = useRef(null);
  const realtimePanelRef = useRef(null);
  const realtimePanelAnchorRef = useRef(null);
  const triggerProfileHighlight = useCallback(() => {
    setProfileHighlight(true);
    if (profileHighlightTimeoutRef.current) {
      clearTimeout(profileHighlightTimeoutRef.current);
    }
    profileHighlightTimeoutRef.current = window.setTimeout(() => {
      setProfileHighlight(false);
      profileHighlightTimeoutRef.current = null;
    }, 3500);
  }, []);
  const isCallDisabled =
    systemStatus.status === "degraded" && systemStatus.acsOnlyIssue;

  useEffect(() => {
    if (isCallDisabled) {
      setShowPhoneInput(false);
    }
  }, [isCallDisabled]);

  useEffect(() => {
    return () => {
      if (demoFormCloseTimeoutRef.current) {
        clearTimeout(demoFormCloseTimeoutRef.current);
        demoFormCloseTimeoutRef.current = null;
      }
      if (profileHighlightTimeoutRef.current) {
        clearTimeout(profileHighlightTimeoutRef.current);
        profileHighlightTimeoutRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    try {
      window.localStorage.setItem(
        STREAM_MODE_STORAGE_KEY,
        selectedStreamingMode,
      );
    } catch (err) {
      logger.warn('Failed to persist streaming mode preference', err);
    }
  }, [selectedStreamingMode]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    try {
      window.localStorage.setItem(
        REALTIME_STREAM_MODE_STORAGE_KEY,
        selectedRealtimeStreamingMode,
      );
    } catch (err) {
      logger.warn('Failed to persist realtime streaming mode preference', err);
    }
  }, [selectedRealtimeStreamingMode]);

  useEffect(() => {
    if (!showPhoneInput) {
      return undefined;
    }

    const handleOutsideClick = (event) => {
      const panelNode = phonePanelRef.current;
      const buttonNode = phoneButtonRef.current;
      if (panelNode && panelNode.contains(event.target)) {
        return;
      }
      if (buttonNode && buttonNode.contains(event.target)) {
        return;
      }
      setShowPhoneInput(false);
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [showPhoneInput]);

  useEffect(() => {
    if (!showRealtimeModePanel) {
      setPendingRealtimeStart(false);
      return undefined;
    }

    const handleRealtimeOutsideClick = (event) => {
      const panelNode = realtimePanelRef.current;
      if (panelNode && panelNode.contains(event.target)) {
        return;
      }
      setShowRealtimeModePanel(false);
    };

    document.addEventListener('mousedown', handleRealtimeOutsideClick);
    return () => document.removeEventListener('mousedown', handleRealtimeOutsideClick);
  }, [showRealtimeModePanel]);

  useEffect(() => {
    if (!showScenarioMenu) {
      return undefined;
    }

    const handleScenarioOutsideClick = (event) => {
      const buttonNode = scenarioButtonRef.current;
      if (buttonNode && buttonNode.contains(event.target)) {
        return;
      }
      // Check if click is inside the menu
      const menuNode = document.querySelector('[data-scenario-menu]');
      if (menuNode && menuNode.contains(event.target)) {
        return;
      }
      setShowScenarioMenu(false);
    };

    document.addEventListener('mousedown', handleScenarioOutsideClick);
    return () => document.removeEventListener('mousedown', handleScenarioOutsideClick);
  }, [showScenarioMenu]);

  // Close backend panel on outside click
  useEffect(() => {
    const handleOutsideClick = (event) => {
      // Check if the BackendIndicator has a panel open
      const panelNode = document.querySelector('[data-backend-panel]');
      if (!panelNode) return;
      
      // Don't close if clicking inside the panel
      if (panelNode.contains(event.target)) {
        return;
      }
      
      // Find the backend button and check if we clicked it
      const buttons = document.querySelectorAll('button[title="Backend Status"]');
      for (const button of buttons) {
        if (button.contains(event.target)) {
          return;
        }
      }
      
      // Click was outside - trigger a click on the button to close
      if (buttons.length > 0) {
        buttons[0].click();
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  useEffect(() => {
    if (recording) {
      setShowRealtimeModePanel(false);
    }
  }, [recording]);

  useLayoutEffect(() => {
    if (!showRealtimeModePanel) {
      return undefined;
    }
    if (typeof window === 'undefined') {
      return undefined;
    }

    const updatePosition = () => {
      const anchorEl = micButtonRef.current || realtimePanelAnchorRef.current;
      const panelEl = realtimePanelRef.current;
      if (!anchorEl || !panelEl) {
        return;
      }
      const anchorRect = anchorEl.getBoundingClientRect();
      const panelRect = panelEl.getBoundingClientRect();
      let top = anchorRect.top - panelRect.height - PANEL_MARGIN;
      if (top < PANEL_MARGIN) {
        top = anchorRect.bottom + PANEL_MARGIN;
      }
      let left = anchorRect.left + anchorRect.width / 2 - panelRect.width / 2;
      const maxLeft = window.innerWidth - panelRect.width - PANEL_MARGIN;
      left = Math.min(
        Math.max(left, PANEL_MARGIN),
        Math.max(PANEL_MARGIN, maxLeft),
      );
      setRealtimePanelCoords({ top, left });
    };

    updatePosition();
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [showRealtimeModePanel]);

  useEffect(() => {
    if (typeof document === 'undefined') {
      return;
    }
    if (!showDemoForm) {
      document.body.style.removeProperty('overflow');
      return;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow || '';
    };
  }, [showDemoForm]);

  const handleStreamingModeChange = useCallback(
    (mode) => {
      if (!mode || mode === selectedStreamingMode) {
        return;
      }
      setSelectedStreamingMode(mode);
      logger.info(`🎚️ [FRONTEND] Streaming mode updated to ${mode}`);
    },
    [selectedStreamingMode],
  );

  const handleRealtimeStreamingModeChange = useCallback(
    (mode) => {
      if (!mode) {
        return;
      }
      if (mode !== selectedRealtimeStreamingMode) {
        setSelectedRealtimeStreamingMode(mode);
        logger.info(`🎚️ [FRONTEND] Realtime streaming mode updated to ${mode}`);
      }
      const shouldStart = pendingRealtimeStart && !recording;
      setPendingRealtimeStart(false);
      setShowRealtimeModePanel(false);
      if (shouldStart) {
        startRecognitionRef.current?.(mode);
      }
    },
    [pendingRealtimeStart, recording, selectedRealtimeStreamingMode],
  );

  const selectedStreamingModeLabel = AcsStreamingModeSelector.getLabel(
    selectedStreamingMode,
  );
  const selectedRealtimeStreamingModeLabel = RealtimeStreamingModeSelector.getLabel(
    selectedRealtimeStreamingMode,
  );
  const selectedRealtimeModeConfig = useMemo(() => {
    const match = realtimeStreamingModeOptions.find(
      (option) => option.value === selectedRealtimeStreamingMode,
    );
    return match?.config ?? null;
  }, [realtimeStreamingModeOptions, selectedRealtimeStreamingMode]);

  const updateToolMessage = useCallback(
    (toolName, transformer, fallbackMessage) => {
      setMessages((prev) => {
        const next = [...prev];
        let targetIndex = -1;

        for (let idx = next.length - 1; idx >= 0; idx -= 1) {
          const candidate = next[idx];
          if (candidate?.isTool && candidate.text?.includes(`tool ${toolName}`)) {
            targetIndex = idx;
            break;
          }
        }

        if (targetIndex === -1) {
          if (!fallbackMessage) {
            return prev;
          }
          const fallback =
            typeof fallbackMessage === "function"
              ? fallbackMessage()
              : fallbackMessage;
          return [...prev, fallback];
        }

        const current = next[targetIndex];
        const updated = transformer(current);
        if (!updated || updated === current) {
          return prev;
        }

        next[targetIndex] = updated;
        return next;
      });
    },
    [setMessages],
  );

  // Health monitoring (disabled)
  /*
  const { 
    healthStatus = { isHealthy: null, lastChecked: null, responseTime: null, error: null },
    readinessStatus = { status: null, timestamp: null, responseTime: null, checks: [], lastChecked: null, error: null },
    overallStatus = { isHealthy: false, hasWarnings: false, criticalErrors: [] },
    refresh = () => {} 
  } = useHealthMonitor({
    baseUrl: API_BASE_URL,
    healthInterval: 30000,
    readinessInterval: 15000,
    enableAutoRefresh: true,
  });
  */

  // Function call state (disabled)
  /*
  const [functionCalls, setFunctionCalls] = useState([]);
  const [callResetKey, setCallResetKey] = useState(0);
  */

  // Component refs
  const chatRef = useRef(null);
  const messageContainerRef = useRef(null);
  const socketRef = useRef(null);
  const relaySocketRef = useRef(null);
  const phoneButtonRef = useRef(null);
  const phonePanelRef = useRef(null);
  const micButtonRef = useRef(null);
  const micMutedRef = useRef(false);
  const relayHealthIntervalRef = useRef(null);
  const relayReconnectTimeoutRef = useRef(null);
  const handleSocketMessageRef = useRef(null);
  const openRelaySocketRef = useRef(null);
  const callLifecycleRef = useRef({
    pending: false,
    active: false,
    callId: null,
    lastEnvelopeAt: 0,
    reconnectAttempts: 0,
    reconnectScheduled: false,
    stalledLoggedAt: null,
    lastRelayOpenedAt: 0,
  });

  // Audio processing refs
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);
  const analyserRef = useRef(null);
  const micStreamRef = useRef(null);
  
  // Audio playback refs for AudioWorklet
  const playbackAudioContextRef = useRef(null);
  const pcmSinkRef = useRef(null);
  const playbackActiveRef = useRef(false);
  const assistantStreamGenerationRef = useRef(0);
  const currentAudioGenerationRef = useRef(0); // Generation when current audio stream started
  const terminationReasonRef = useRef(null);
  const resampleWarningRef = useRef(false);
  const audioInitFailedRef = useRef(false);
  const audioInitAttemptedRef = useRef(false);
  const shouldReconnectRef = useRef(false);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  
  const audioLevelRef = useRef(0);
  const outputAudioLevelRef = useRef(0);
  const outputLevelDecayTimeoutRef = useRef(null);
  const startRecognitionRef = useRef(null);
  const stopRecognitionRef = useRef(null);

  const cancelOutputLevelDecay = useCallback(() => {
    if (outputLevelDecayTimeoutRef.current && typeof window !== 'undefined') {
      window.clearTimeout(outputLevelDecayTimeoutRef.current);
      outputLevelDecayTimeoutRef.current = null;
    }
  }, []);

  const scheduleOutputLevelDecay = useCallback(() => {
    if (typeof window === 'undefined') {
      outputAudioLevelRef.current = 0;
      return;
    }
    cancelOutputLevelDecay();
    const decayStep = () => {
      let next = outputAudioLevelRef.current * 0.78;
      if (next < 0.002) {
        next = 0;
      }
      outputAudioLevelRef.current = next;
      if (next > 0) {
        outputLevelDecayTimeoutRef.current = window.setTimeout(decayStep, 160);
      } else {
        outputLevelDecayTimeoutRef.current = null;
      }
    };
    outputLevelDecayTimeoutRef.current = window.setTimeout(decayStep, 200);
  }, [cancelOutputLevelDecay]);

  const clearTtsPlaybackQueue = useCallback(
    (reason) => {
      if (pcmSinkRef.current) {
        pcmSinkRef.current.port.postMessage({ type: "clear" });
      }
      playbackActiveRef.current = false;
      cancelOutputLevelDecay();
      outputAudioLevelRef.current = 0;
      if (playbackAudioContextRef.current && playbackAudioContextRef.current.state === "running") {
        playbackAudioContextRef.current.suspend().catch(() => {});
      }
      if (reason) {
        appendLog(`🔇 Cleared TTS audio queue (${reason})`);
      }
    },
    [appendLog, cancelOutputLevelDecay],
  );
  const metricsRef = useRef(createMetricsState());
  // Throttle hot-path UI updates for streaming text
  const lastSttPartialUpdateRef = useRef(0);
  const lastAssistantStreamUpdateRef = useRef(0);

  const workletSource = `
    class PcmSink extends AudioWorkletProcessor {
      constructor() {
        super();
        this.queue = [];
        this.readIndex = 0;
        this.samplesProcessed = 0;
        this.meter = 0;
        this.meterSamples = 0;
        this.meterInterval = sampleRate / 20; // ~50ms cadence
        this.port.onmessage = (e) => {
          if (e.data?.type === 'push') {
            this.queue.push(e.data.payload);
          } else if (e.data?.type === 'clear') {
            this.queue = [];
            this.readIndex = 0;
            this.meter = 0;
            this.meterSamples = 0;
            this.port.postMessage({ type: 'meter', value: 0 });
          }
        };
      }
      process(inputs, outputs) {
        const out = outputs[0][0];
        let writeIndex = 0;
        let sumSquares = 0;

        while (writeIndex < out.length) {
          if (this.queue.length === 0) {
            break;
          }

          const chunk = this.queue[0];
          const remain = chunk.length - this.readIndex;
          const toCopy = Math.min(remain, out.length - writeIndex);

          for (let n = 0; n < toCopy; n += 1) {
            const sample = chunk[this.readIndex + n] || 0;
            out[writeIndex + n] = sample;
            sumSquares += sample * sample;
          }

          writeIndex += toCopy;
          this.readIndex += toCopy;

          if (this.readIndex >= chunk.length) {
            this.queue.shift();
            this.readIndex = 0;
          }
        }

        if (writeIndex < out.length) {
          out.fill(0, writeIndex);
        }

        const frameSamples = out.length;
        const rmsInstant = frameSamples > 0 ? Math.sqrt(sumSquares / frameSamples) : 0;
        const smoothing = rmsInstant > this.meter ? 0.35 : 0.15;
        this.meter = this.meter + (rmsInstant - this.meter) * smoothing;
        this.meterSamples += frameSamples;

        if (this.meterSamples >= this.meterInterval) {
          this.meterSamples = 0;
          this.port.postMessage({ type: 'meter', value: this.meter });
        }

        this.samplesProcessed += frameSamples;
        return true;
      }
    }
    registerProcessor('pcm-sink', PcmSink);
  `;

  const resampleFloat32 = useCallback((input, fromRate, toRate) => {
    if (!input || fromRate === toRate || !Number.isFinite(fromRate) || !Number.isFinite(toRate) || fromRate <= 0 || toRate <= 0) {
      return input;
    }

    const resampleRatio = toRate / fromRate;
    if (!Number.isFinite(resampleRatio) || resampleRatio <= 0) {
      return input;
    }

    const newLength = Math.max(1, Math.round(input.length * resampleRatio));
    const output = new Float32Array(newLength);
    for (let i = 0; i < newLength; i += 1) {
      const sourceIndex = i / resampleRatio;
      const index0 = Math.floor(sourceIndex);
      const index1 = Math.min(input.length - 1, index0 + 1);
      const frac = sourceIndex - index0;
      const sample0 = input[index0] ?? 0;
      const sample1 = input[index1] ?? sample0;
      output[i] = sample0 + (sample1 - sample0) * frac;
    }
    return output;
  }, []);

  const updateOutputLevelMeter = useCallback((samples, meterValue) => {
    const previous = outputAudioLevelRef.current;
    let target = previous;

    if (typeof meterValue === "number" && Number.isFinite(meterValue)) {
      target = Math.min(1, Math.max(0, meterValue * 1.35));
    } else if (samples && samples.length) {
      let sumSquares = 0;
      for (let i = 0; i < samples.length; i += 1) {
        const sample = samples[i] || 0;
        sumSquares += sample * sample;
      }
      const rms = Math.sqrt(sumSquares / samples.length);
      target = Math.min(1, rms * 10);
    } else {
      target = previous * 0.75;
    }

    const blend = target > previous ? 0.35 : 0.2;
    let nextLevel = previous + (target - previous) * blend;

    if (nextLevel < 0.002) {
      nextLevel = 0;
    }

    outputAudioLevelRef.current = nextLevel;
    scheduleOutputLevelDecay();
  }, [scheduleOutputLevelDecay]);

  // Initialize playback audio context and worklet (call on user gesture)
  const initializeAudioPlayback = async () => {
    if (playbackAudioContextRef.current) return; // Already initialized
    if (audioInitFailedRef.current) return; // Already failed, don't retry
    if (audioInitAttemptedRef.current) return; // Already attempting
    
    audioInitAttemptedRef.current = true;
    
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
        // Let browser use its native rate (usually 48kHz), worklet will handle resampling
      });
      
      // Add the worklet module
      await audioCtx.audioWorklet.addModule(URL.createObjectURL(new Blob(
        [workletSource], { type: 'text/javascript' }
      )));
      
      // Create the worklet node
      const sink = new AudioWorkletNode(audioCtx, 'pcm-sink', {
        numberOfInputs: 0, 
        numberOfOutputs: 1, 
        outputChannelCount: [1]
      });
      sink.connect(audioCtx.destination);
      sink.port.onmessage = (event) => {
        if (event?.data?.type === 'meter') {
          updateOutputLevelMeter(undefined, event.data.value ?? 0);
        }
      };
      
      // Resume on user gesture
      await audioCtx.resume();
      
      playbackAudioContextRef.current = audioCtx;
      pcmSinkRef.current = sink;
      
      appendLog("🔊 Audio playback initialized");
      logger.info("AudioWorklet playback system initialized, context sample rate:", audioCtx.sampleRate);
    } catch (error) {
      audioInitFailedRef.current = true;
      audioInitAttemptedRef.current = false;
      logger.error("Failed to initialize audio playback:", error);
      appendLog("❌ Audio playback init failed");
    }
  };


  const resetCallLifecycle = useCallback(() => {
    const state = callLifecycleRef.current;
    state.pending = false;
    state.active = false;
    state.callId = null;
    state.lastEnvelopeAt = 0;
    state.reconnectAttempts = 0;
    state.reconnectScheduled = false;
    state.stalledLoggedAt = null;
    state.lastRelayOpenedAt = 0;
    if (relayReconnectTimeoutRef.current && typeof window !== "undefined") {
      window.clearTimeout(relayReconnectTimeoutRef.current);
      relayReconnectTimeoutRef.current = null;
    }
  }, []);

  const closeRelaySocket = useCallback((reason = "client stop", options = {}) => {
    const { preserveLifecycle = false } = options;
    const relaySocket = relaySocketRef.current;
    if (relayReconnectTimeoutRef.current && typeof window !== "undefined") {
      window.clearTimeout(relayReconnectTimeoutRef.current);
      relayReconnectTimeoutRef.current = null;
    }
    if (!relaySocket) {
      if (!preserveLifecycle) {
        resetCallLifecycle();
      }
      return;
    }
    try {
      relaySocket.close(1000, reason);
    } catch (error) {
      logger.warn("Error closing relay socket:", error);
    } finally {
      if (relaySocketRef.current === relaySocket) {
        relaySocketRef.current = null;
      }
      if (!preserveLifecycle) {
        resetCallLifecycle();
      }
    }
  }, [resetCallLifecycle]);
  // Formatting functions moved to ProfileButton component
  const activeSessionProfile = sessionProfiles[sessionId];
  const hasActiveProfile = Boolean(activeSessionProfile?.profile);
  useEffect(() => {
    const profilePayload = activeSessionProfile?.profile;
    const nextId = profilePayload?.id || activeSessionProfile?.sessionId || null;
    if (!nextId) {
      lastProfileIdRef.current = null;
      setShowProfilePanel(false);
      return;
    }
    if (lastProfileIdRef.current !== nextId) {
      lastProfileIdRef.current = nextId;
      setShowProfilePanel(true);
    }
  }, [activeSessionProfile]);
  
  const handleDemoCreated = useCallback((demoPayload) => {
    if (!demoPayload) {
      return;
    }
    const ssn = demoPayload?.profile?.verification_codes?.ssn4;
    const notice = demoPayload?.safety_notice ?? 'Demo data only.';
    const sessionKey = demoPayload.session_id ?? sessionId;
    let previouslyHadProfile = false;
    const messageLines = [
      'DEMO PROFILE GENERATED',
      ssn ? `Temporary SSN Last 4: ${ssn}` : null,
      notice,
      'NEVER enter real customer or personal data in this environment.',
    ].filter(Boolean);
    setSessionProfiles((prev) => {
      previouslyHadProfile = Boolean(prev[sessionKey]?.profile);
      return {
        ...prev,
        [sessionKey]: buildSessionProfile(
          demoPayload,
          sessionKey,
          prev[sessionKey],
        ),
      };
    });
    appendSystemMessage(messageLines.join('\n'), { tone: "warning" });
    appendLog('Synthetic demo profile issued with sandbox identifiers');
    if (!previouslyHadProfile) {
      triggerProfileHighlight();
    }
    if (demoFormCloseTimeoutRef.current) {
      clearTimeout(demoFormCloseTimeoutRef.current);
    }
    demoFormCloseTimeoutRef.current = window.setTimeout(() => {
      closeDemoForm();
      demoFormCloseTimeoutRef.current = null;
    }, 1000);
  }, [appendLog, appendSystemMessage, sessionId, triggerProfileHighlight, closeDemoForm]);

  useEffect(() => {
    return () => {
      closeRelaySocket("component unmount");
    };
  }, [closeRelaySocket]);

  useEffect(() => {
    if (!recording) {
      micMutedRef.current = false;
      setMicMuted(false);
    }
  }, [recording]);

  const handleResetSession = useCallback(() => {
    const newSessionId = createNewSessionId();
    setSessionId(newSessionId);
    setSessionProfiles({});
    setSessionAgentConfig(null); // Clear session-specific agent config
    setSessionScenarioConfig(null); // Clear session-specific scenario config
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      logger.info('🔌 Closing WebSocket for session reset...');
      try {
        socketRef.current.close();
      } catch (error) {
        logger.warn('Error closing socket during reset', error);
      }
    }
    setMessages([]);
    setActiveSpeaker(null);
    stopRecognitionRef.current?.();
    setCallActive(false);
    setCurrentCallId(null);
    setShowPhoneInput(false);
    setGraphEvents([]);
    graphEventCounterRef.current = 0;
    currentAgentRef.current = "Concierge";
    micMutedRef.current = false;
    setMicMuted(false);
    closeRelaySocket("session reset");
    appendLog(`🔄️ Session reset - new session ID: ${newSessionId}`);
    setTimeout(() => {
      appendSystemMessage(
        "Session restarted with new ID. Ready for a fresh conversation!",
        { tone: "success" },
      );
    }, 500);
  }, [appendLog, appendSystemMessage, closeRelaySocket, setSessionId, setSessionProfiles, setMessages, setActiveSpeaker, setCallActive, setShowPhoneInput]);

  const handleMuteToggle = useCallback(() => {
    if (!recording) {
      return;
    }
    const next = !micMutedRef.current;
    micMutedRef.current = next;
    setMicMuted(next);
    appendLog(next ? "🔇 Microphone muted" : "🔈 Microphone unmuted");
  }, [appendLog, recording]);

  const handleMicToggle = useCallback(() => {
    if (recording) {
      stopRecognitionRef.current?.();
    } else {
      micMutedRef.current = false;
      setMicMuted(false);
      setPendingRealtimeStart(true);
      setShowRealtimeModePanel(true);
    }
  }, [recording]);

  const terminateACSCall = useCallback(async () => {
    if (!callActive && !currentCallId) {
      stopRecognitionRef.current?.();
      return;
    }

    const payload =
      currentCallId != null
        ? {
            call_id: currentCallId,
            session_id: getOrCreateSessionId(),
            reason: "normal",
          }
        : null;
    try {
      if (payload) {
        const res = await fetch(`${API_BASE_URL}/api/v1/calls/terminate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const errorBody = await res.json().catch(() => ({}));
          appendLog(
            `Hangup failed: ${errorBody.detail || res.statusText || res.status}`
          );
        } else {
          appendLog("📴 Hangup requested");
        }
      }
    } catch (err) {
      appendLog(`Hangup error: ${err?.message || err}`);
    } finally {
      stopRecognitionRef.current?.();
      setCallActive(false);
      setActiveSpeaker(null);
      setShowPhoneInput(false);
      setCurrentCallId(null);
      resetCallLifecycle();
      closeRelaySocket("call terminated");
    }
  }, [
    appendLog,
    closeRelaySocket,
    resetCallLifecycle,
    callActive,
    currentCallId,
    setCallActive,
    setShowPhoneInput,
  ]);

  const handlePhoneButtonClick = useCallback(() => {
    if (isCallDisabled && !callActive) {
      return;
    }
    if (callActive) {
      terminateACSCall();
      return;
    }
    setShowPhoneInput((prev) => !prev);
  }, [isCallDisabled, callActive, setShowPhoneInput, terminateACSCall]);

  const publishMetricsSummary = useCallback(
    (label, detail) => {
      if (!label) {
        return;
      }

      let formatted = null;
      if (typeof detail === "string") {
        formatted = detail;
        logger.debug(`[Metrics] ${label}: ${detail}`);
      } else if (detail && typeof detail === "object") {
        const entries = Object.entries(detail).filter(([, value]) => value !== undefined && value !== null && value !== "");
        formatted = entries
          .map(([key, value]) => `${key}=${value}`)
          .join(" • ");
        logger.debug(`[Metrics] ${label}`, detail);
      } else {
        logger.debug(`[Metrics] ${label}`, metricsRef.current);
      }

      appendLog(formatted ? `📈 ${label} — ${formatted}` : `📈 ${label}`);
    },
    [appendLog],
  );

  const {
    interruptAssistantOutput,
    recordBargeInEvent,
    finalizeBargeInClear,
  } = useBargeIn({
    appendLog,
    setActiveSpeaker,
    assistantStreamGenerationRef,
    pcmSinkRef,
    playbackActiveRef,
    metricsRef,
    publishMetricsSummary,
  });

  const resetMetrics = useCallback(
    (sessionId) => {
      metricsRef.current = createMetricsState();
      const metrics = metricsRef.current;
      metrics.sessionStart = performance.now();
      metrics.sessionStartIso = new Date().toISOString();
      metrics.sessionId = sessionId;
      publishMetricsSummary("Session metrics reset", {
        sessionId,
        at: metrics.sessionStartIso,
      });
    },
    [publishMetricsSummary],
  );

  const registerUserTurn = useCallback(
    (text) => {
      const metrics = metricsRef.current;
      const now = performance.now();
      const turnId = metrics.turnCounter + 1;
      metrics.turnCounter = turnId;
      const turn = {
        id: turnId,
        userTs: now,
        userTextPreview: text.slice(0, 80),
      };
      metrics.turns.push(turn);
      metrics.currentTurnId = turnId;
      metrics.awaitingAudioTurnId = turnId;
      const elapsed = metrics.sessionStart != null ? toMs(now - metrics.sessionStart) : undefined;
      publishMetricsSummary(`Turn ${turnId} user`, {
        elapsedSinceStartMs: elapsed,
      });
    },
    [publishMetricsSummary],
  );

  const registerAssistantStreaming = useCallback(
    (speaker) => {
      const metrics = metricsRef.current;
      const now = performance.now();
      let turn = metrics.turns.slice().reverse().find((t) => !t.firstTokenTs || !t.audioEndTs);
      if (!turn) {
        const turnId = metrics.turnCounter + 1;
        metrics.turnCounter = turnId;
        turn = {
          id: turnId,
          userTs: metrics.sessionStart ?? now,
          synthetic: true,
          userTextPreview: "[synthetic]",
        };
        metrics.turns.push(turn);
        metrics.currentTurnId = turnId;
      }

      if (!turn.firstTokenTs) {
        turn.firstTokenTs = now;
        turn.firstTokenLatencyMs = turn.userTs != null ? now - turn.userTs : undefined;
        if (metrics.firstTokenTs == null) {
          metrics.firstTokenTs = now;
        }
        if (metrics.sessionStart != null && metrics.ttftMs == null) {
          metrics.ttftMs = now - metrics.sessionStart;
          publishMetricsSummary("TTFT captured", {
            ttftMs: toMs(metrics.ttftMs),
          });
        }
        publishMetricsSummary(`Turn ${turn.id} first token`, {
          latencyMs: toMs(turn.firstTokenLatencyMs),
          speaker,
        });
      }
      metrics.currentTurnId = turn.id;
    },
    [publishMetricsSummary],
  );

  const registerAssistantFinal = useCallback(
    (speaker) => {
      const metrics = metricsRef.current;
      const now = performance.now();
      const turn = metrics.turns.slice().reverse().find((t) => !t.finalTextTs);
      if (!turn) {
        return;
      }

      if (!turn.finalTextTs) {
        turn.finalTextTs = now;
        turn.finalLatencyMs = turn.userTs != null ? now - turn.userTs : undefined;
        metrics.awaitingAudioTurnId = turn.id;
        publishMetricsSummary(`Turn ${turn.id} final text`, {
          latencyMs: toMs(turn.finalLatencyMs),
          speaker,
        });
        if (turn.audioStartTs != null) {
          turn.finalToAudioMs = turn.audioStartTs - turn.finalTextTs;
          publishMetricsSummary(`Turn ${turn.id} final→audio`, {
            deltaMs: toMs(turn.finalToAudioMs),
          });
        }
      }
    },
    [publishMetricsSummary],
  );

  const registerAudioFrame = useCallback(
    (frameIndex, isFinal) => {
      const metrics = metricsRef.current;
      const now = performance.now();
      metrics.lastAudioFrameTs = now;

      const preferredId = metrics.awaitingAudioTurnId ?? metrics.currentTurnId;
      let turn = preferredId != null ? metrics.turns.find((t) => t.id === preferredId) : undefined;
      if (!turn) {
        turn = metrics.turns.slice().reverse().find((t) => !t.audioEndTs);
      }
      if (!turn) {
        return;
      }

      if ((frameIndex ?? 0) === 0 && turn.audioStartTs == null) {
        turn.audioStartTs = now;
        const deltaFromFinal = turn.finalTextTs != null ? now - turn.finalTextTs : undefined;
        turn.finalToAudioMs = deltaFromFinal;
        publishMetricsSummary(`Turn ${turn.id} audio start`, {
          afterFinalMs: toMs(deltaFromFinal),
          elapsedMs: turn.userTs != null ? toMs(now - turn.userTs) : undefined,
        });
      }

      if (isFinal) {
        turn.audioEndTs = now;
        turn.audioPlaybackDurationMs = turn.audioStartTs != null ? now - turn.audioStartTs : undefined;
        turn.totalLatencyMs = turn.userTs != null ? now - turn.userTs : undefined;
        metrics.awaitingAudioTurnId = null;
        publishMetricsSummary(`Turn ${turn.id} audio complete`, {
          playbackDurationMs: toMs(turn.audioPlaybackDurationMs),
          totalMs: toMs(turn.totalLatencyMs),
        });
      }
    },
    [publishMetricsSummary],
  );

  useEffect(() => {
    const target = messageContainerRef.current || chatRef.current;
    if (!target) return;
    // Use instant scrolling while streaming to reduce layout thrash
    const behavior = recording ? "auto" : "smooth";
    target.scrollTo({ top: target.scrollHeight, behavior });
  }, [messages, recording]);

  useEffect(() => {
    return () => {
      if (processorRef.current) {
        try { 
          processorRef.current.disconnect(); 
        } catch (e) {
          logger.warn("Cleanup error:", e);
        }
      }
      if (audioContextRef.current) {
        try { 
          audioContextRef.current.close(); 
        } catch (e) {
          logger.warn("Cleanup error:", e);
        }
      }
      if (pcmSinkRef.current) {
        try {
          pcmSinkRef.current.port.onmessage = null;
          pcmSinkRef.current = null;
        } catch (e) {
          logger.warn("Cleanup error:", e);
        }
      }
      if (playbackAudioContextRef.current) {
        try { 
          playbackAudioContextRef.current.close(); 
        } catch (e) {
          logger.warn("Cleanup error:", e);
        }
      }
      playbackActiveRef.current = false;
      shouldReconnectRef.current = false;
      reconnectAttemptsRef.current = 0;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (socketRef.current) {
        try { 
          socketRef.current.close(); 
        } catch (e) {
          logger.warn("Cleanup error:", e);
        }
        socketRef.current = null;
      }
      cancelOutputLevelDecay();
      outputAudioLevelRef.current = 0;
      audioLevelRef.current = 0;
    };
  }, [cancelOutputLevelDecay]);

  const startRecognition = async (modeOverride) => {
      clearTtsPlaybackQueue("mic start");
      appendLog("🎤 PCM streaming started");
      await initializeAudioPlayback();

      const sessionId = getOrCreateSessionId();
      const realtimeMode = modeOverride || selectedRealtimeStreamingMode;
      const realtimeReadableMode =
        selectedRealtimeStreamingModeLabel || realtimeMode;
      const activeRealtimeConfig = modeOverride
        ? (realtimeStreamingModeOptions.find((option) => option.value === realtimeMode)?.config ?? null)
        : selectedRealtimeModeConfig;
      
      // Get user email from active session profile for pre-loading
      const userEmail = activeSessionProfile?.profile?.email || 
                       activeSessionProfile?.profile?.contact_info?.email || null;
      const emailParam = userEmail ? `&user_email=${encodeURIComponent(userEmail)}` : '';
      
      const currentScenario = getSessionScenario();
      const baseConversationUrl = `${WS_URL}/api/v1/browser/conversation?session_id=${sessionId}&streaming_mode=${encodeURIComponent(
        realtimeMode,
      )}${emailParam}&scenario=${encodeURIComponent(currentScenario)}`;
      resetMetrics(sessionId);
      assistantStreamGenerationRef.current = 0;
      terminationReasonRef.current = null;
      resampleWarningRef.current = false;
      audioInitFailedRef.current = false;
      audioInitAttemptedRef.current = false;
      currentAudioGenerationRef.current = 0;
      shouldReconnectRef.current = true;
      reconnectAttemptsRef.current = 0;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      logger.info(
        '🔗 [FRONTEND] Starting conversation WebSocket with session_id: %s (realtime_mode=%s)',
        sessionId,
        realtimeReadableMode,
      );
      if (activeRealtimeConfig) {
        logger.debug(
          '[FRONTEND] Realtime streaming mode config:',
          activeRealtimeConfig,
        );
      }

      const connectSocket = (isReconnect = false) => {
        const ws = new WebSocket(baseConversationUrl);
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
          appendLog(isReconnect ? "🔌 WS reconnected - Connected to backend!" : "🔌 WS open - Connected to backend!");
          logger.info(
            "WebSocket connection %s to backend at:",
            isReconnect ? "RECONNECTED" : "OPENED",
            baseConversationUrl,
          );
          reconnectAttemptsRef.current = 0;
        };

        ws.onclose = (event) => {
          appendLog(`🔌 WS closed - Code: ${event.code}, Reason: ${event.reason}`);
          logger.info("WebSocket connection CLOSED. Code:", event.code, "Reason:", event.reason);

          if (socketRef.current === ws) {
            socketRef.current = null;
          }

          if (!shouldReconnectRef.current) {
            if (terminationReasonRef.current === "HUMAN_HANDOFF") {
              appendLog("🔌 WS closed after live agent transfer");
            }
            return;
          }

          const attempt = reconnectAttemptsRef.current + 1;
          reconnectAttemptsRef.current = attempt;
          const delay = Math.min(5000, 250 * Math.pow(2, attempt - 1));
          appendLog(`🔄 WS reconnect scheduled in ${Math.round(delay)} ms (attempt ${attempt})`);

          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }

          reconnectTimeoutRef.current = window.setTimeout(() => {
            reconnectTimeoutRef.current = null;
            if (!shouldReconnectRef.current) {
              return;
            }
            appendLog("🔄 Attempting WS reconnect…");
            connectSocket(true);
          }, delay);
        };

        ws.onerror = (err) => {
          appendLog("❌ WS error - Check if backend is running");
          logger.error("WebSocket error - backend might not be running:", err);
        };

        ws.onmessage = (event) => {
          const handler = handleSocketMessageRef.current;
          if (handler) {
            handler(event);
          }
        };
        socketRef.current = ws;
        return ws;
      };

      connectSocket(false);

      // 2) setup Web Audio for raw PCM @16 kHz
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micMutedRef.current = false;
      setMicMuted(false);
      micStreamRef.current = stream;
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000
      });
      audioContextRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);

      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.3;
      analyserRef.current = analyser;
      
      source.connect(analyser);

      const bufferSize = 512; 
      const processor  = audioCtx.createScriptProcessor(bufferSize, 1, 1);
      processorRef.current = processor;

      analyser.connect(processor);

      processor.onaudioprocess = (evt) => {
        const float32 = evt.inputBuffer.getChannelData(0);
        const isMuted = micMutedRef.current;
        let target = 0;

        const int16 = new Int16Array(float32.length);

        if (isMuted) {
          for (let i = 0; i < float32.length; i++) {
            int16[i] = 0;
          }
        } else {
          let sum = 0;
          for (let i = 0; i < float32.length; i++) {
            const sample = Math.max(-1, Math.min(1, float32[i]));
            sum += sample * sample;
            int16[i] = sample * 0x7fff;
          }
          const rms = Math.sqrt(sum / float32.length);
          target = Math.min(1, rms * 10);
        }

        const previous = audioLevelRef.current;
        const smoothing = target > previous ? 0.32 : 0.18;
        const level = previous + (target - previous) * smoothing;
        audioLevelRef.current = level;

        const activeSocket = socketRef.current;
        if (activeSocket && activeSocket.readyState === WebSocket.OPEN) {
          activeSocket.send(int16.buffer);
          // Debug: Confirm data sent
          // logger.debug("PCM audio chunk sent to backend!");
        } else {
          logger.debug("WebSocket not open, did not send audio.");
        }
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);
      setRecording(true);
    };

    const stopRecognition = () => {
      clearTtsPlaybackQueue("mic stop");
      if (processorRef.current) {
        try { 
          processorRef.current.disconnect(); 
        } catch (e) {
          logger.warn("Error disconnecting processor:", e);
        }
        processorRef.current = null;
      }
      if (audioContextRef.current) {
        try { 
          audioContextRef.current.close(); 
        } catch (e) {
          logger.warn("Error closing audio context:", e);
        }
        audioContextRef.current = null;
      }
      if (micStreamRef.current) {
        try {
          micStreamRef.current.getTracks().forEach((track) => {
            try {
              track.stop();
            } catch (trackError) {
              logger.warn("Error stopping mic track:", trackError);
            }
          });
        } catch (streamError) {
          logger.warn("Error releasing microphone stream:", streamError);
        }
        micStreamRef.current = null;
      }
      playbackActiveRef.current = false;
      
      shouldReconnectRef.current = false;
      reconnectAttemptsRef.current = 0;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      if (socketRef.current) {
        try { 
          socketRef.current.close(1000, "client stop"); 
        } catch (e) {
          logger.warn("Error closing socket:", e);
        }
        socketRef.current = null;
      }
      
      // Add session stopped divider instead of card
      appendSystemMessage("🛑 Session stopped", { variant: "session_stop" });
      setActiveSpeaker("System");
      setRecording(false);
      micMutedRef.current = false;
      setMicMuted(false);
      audioLevelRef.current = 0;
      outputAudioLevelRef.current = 0;
      cancelOutputLevelDecay();
      appendLog("🛑 PCM streaming stopped");
    };

    startRecognitionRef.current = startRecognition;
    stopRecognitionRef.current = stopRecognition;

    const pushIfChanged = (arr, msg) => {
      const normalizedMsg =
        msg?.speaker === "System"
          ? buildSystemMessage(msg.text ?? "", msg)
          : msg;
      if (arr.length === 0) return [...arr, normalizedMsg];
      const last = arr[arr.length - 1];
      if (last.speaker === normalizedMsg.speaker && last.text === normalizedMsg.text) return arr;
      return [...arr, normalizedMsg];
    };

    const updateTurnMessage = (turnId, updater, options = {}) => {
      const { createIfMissing = true, initial } = options;

      setMessages((prev) => {
        if (!turnId) {
          if (!createIfMissing) {
            return prev;
          }
          const base = typeof initial === "function" ? initial() : initial;
          if (!base) {
            return prev;
          }
          return [...prev, base];
        }

        const index = prev.findIndex((m) => m.turnId === turnId);
        if (index === -1) {
          if (!createIfMissing) {
            return prev;
          }
          const base = typeof initial === "function" ? initial() : initial;
          if (!base) {
            return prev;
          }
          return [...prev, { ...base, turnId }];
        }

        const current = prev[index];
        const patch = typeof updater === "function" ? updater(current) : null;
        if (patch == null) {
          return prev;
        }

        const next = [...prev];
        next[index] = { ...current, ...patch, turnId };
        return next;
      });
    };

    const handleSocketMessage = async (event) => {
      // Optional verbose tracing; disabled by default for perf
      if (ENABLE_VERBOSE_STREAM_LOGS) {
        if (typeof event.data === "string") {
          try {
            const msg = JSON.parse(event.data);
            logger.debug("📨 WebSocket message received:", msg.type || "unknown", msg);
          } catch (e) {
            logger.debug("📨 Non-JSON WebSocket message:", event.data);
            logger.debug(e);
          }
        } else {
          logger.debug("📨 Binary WebSocket message received, length:", event.data.byteLength);
        }
      }

      if (typeof event.data !== "string") {
        // Binary audio data (legacy path)
        
        // Resume audio context if suspended (after text barge-in)
        if (audioContextRef.current && audioContextRef.current.state === "suspended") {
          await audioContextRef.current.resume();
          appendLog("▶️ Audio context resumed");
        }
        
        const ctx = audioContextRef.current || new AudioContext();
        if (!audioContextRef.current) {
          audioContextRef.current = ctx;
        }
        
        const buf = await event.data.arrayBuffer();
        const audioBuf = await ctx.decodeAudioData(buf);
        const src = ctx.createBufferSource();
        src.buffer = audioBuf;
        src.connect(ctx.destination);
        src.start();
        appendLog("🔊 Audio played");
        return;
      }
    
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        appendLog("Ignored non‑JSON frame");
        return;
      }

      // --- NEW: Handle envelope format from backend ---
      // If message is in envelope format, extract the actual payload
      if (payload.type && payload.sender && payload.payload && payload.ts) {
        const envelope = payload;
        logger.debug("📨 Received envelope message:", {
          type: envelope.type,
          sender: envelope.sender,
          topic: envelope.topic,
          session_id: envelope.session_id,
        });

        const envelopeType = envelope.type;
        const envelopeSender = envelope.sender;
        const envelopeTimestamp = envelope.ts;
        const envelopeSessionId = envelope.session_id;
        const envelopeTopic = envelope.topic;
        const actualPayload = envelope.payload ?? {};

        let flattenedPayload;

        // Transform envelope back to legacy format for compatibility
        if (envelopeType === "event" && (actualPayload.event_type || actualPayload.eventType)) {
          const evtType = actualPayload.event_type || actualPayload.eventType;
          const eventData = {
            ...(typeof actualPayload.data === "object" && actualPayload.data ? actualPayload.data : {}),
            ...actualPayload,
          };
          delete eventData.event_type;
          delete eventData.eventType;
          flattenedPayload = {
            ...eventData,
            type: "event",
            event_type: evtType,
            event_data: eventData,
            data: eventData,
            message: actualPayload.message || eventData.message,
            content: actualPayload.content || eventData.content || actualPayload.message,
            sender: envelopeSender,
            speaker: envelopeSender,
          };
        } else if (
          envelopeType === "event" &&
          actualPayload.message &&
          !actualPayload.event_type &&
          !actualPayload.eventType
        ) {
          const merged = { ...actualPayload };
          merged.message = merged.message ?? actualPayload.message;
          merged.content = merged.content ?? actualPayload.message;
          merged.streaming = merged.streaming ?? false;
          flattenedPayload = {
            ...merged,
            type: merged.type || "assistant",
            sender: envelopeSender,
            speaker: envelopeSender,
          };
        } else if (envelopeType === "assistant_streaming") {
          const merged = { ...actualPayload };
          merged.content = merged.content ?? merged.message ?? "";
          merged.streaming = true;
          flattenedPayload = {
            ...merged,
            type: "assistant_streaming",
            sender: envelopeSender,
            speaker: envelopeSender,
          };
        } else if (envelopeType === "status" && actualPayload.message) {
          const merged = { ...actualPayload };
          merged.message = merged.message ?? actualPayload.message;
          merged.content = merged.content ?? actualPayload.message;
          merged.statusLabel =
            merged.statusLabel ?? merged.label ?? merged.status_label;
          flattenedPayload = {
            ...merged,
            type: "status",
            sender: envelopeSender,
            speaker: envelopeSender,
          };
        } else {
          // For other envelope types, use the payload directly and retain the type
          flattenedPayload = {
            ...actualPayload,
            type: actualPayload.type || envelopeType,
            sender: envelopeSender,
            speaker: envelopeSender,
          };
        }

        if (envelopeTimestamp && !flattenedPayload.ts) {
          flattenedPayload.ts = envelopeTimestamp;
        }
        if (envelopeSessionId && !flattenedPayload.session_id) {
          flattenedPayload.session_id = envelopeSessionId;
        }
        if (envelopeTopic && !flattenedPayload.topic) {
          flattenedPayload.topic = envelopeTopic;
        }

        payload = flattenedPayload;
        logger.debug("📨 Transformed envelope to legacy format:", payload);
      }

      // Normalize source/target for graph/timeline views
      const inferredSpeaker = payload.speaker || payload.sender || payload.from;
      if (!payload.from && inferredSpeaker) {
        payload.from = inferredSpeaker;
      }
      if (!payload.to) {
        // If speaker is user, target is current agent; otherwise target user by default.
        if (inferredSpeaker === "User") {
          payload.to = currentAgentRef.current || payload.agent_name || "Concierge";
        } else if (inferredSpeaker) {
          payload.to = "User";
        }
      }

      if (callLifecycleRef.current.pending) {
        callLifecycleRef.current.lastEnvelopeAt = Date.now();
      }

      const normalizedEventType =
        payload.event_type ||
        payload.eventType ||
        (typeof payload.type === "string" && payload.type.startsWith("event_")
          ? payload.type
          : undefined);

      if (normalizedEventType) {
        payload.event_type = normalizedEventType;
      }

      if (normalizedEventType === "session_updated" || normalizedEventType === "agent_change") {
        const combinedData = {
          ...(typeof payload.event_data === "object" && payload.event_data ? payload.event_data : {}),
          ...(typeof payload.data === "object" && payload.data ? payload.data : {}),
        };

        if (typeof payload.session === "object" && payload.session) {
          combinedData.session = combinedData.session ?? payload.session;
        }

        let candidateAgent =
          payload.active_agent_label ||
          payload.agent_label ||
          payload.agentLabel ||
          payload.agent_name ||
          combinedData.active_agent_label ||
          combinedData.agent_label ||
          combinedData.agentLabel ||
          combinedData.agent_name;

        if (!candidateAgent) {
          const sessionInfo = combinedData.session;
          if (sessionInfo && typeof sessionInfo === "object") {
            candidateAgent =
              sessionInfo.active_agent_label ||
              sessionInfo.activeAgentLabel ||
              sessionInfo.active_agent ||
              sessionInfo.agent_label ||
              sessionInfo.agentLabel ||
              sessionInfo.agent_name ||
              sessionInfo.agentName ||
              sessionInfo.current_agent ||
              sessionInfo.currentAgent ||
              sessionInfo.handoff_target ||
              sessionInfo.handoffTarget;
          }
        }

        const agentLabel =
          typeof candidateAgent === "string" ? candidateAgent.trim() : null;

        if (agentLabel) {
          const label = agentLabel;
          combinedData.active_agent_label = combinedData.active_agent_label ?? label;
          combinedData.agent_label = combinedData.agent_label ?? label;
          combinedData.agent_name = combinedData.agent_name ?? label;
          payload.active_agent_label = payload.active_agent_label ?? label;
          payload.agent_label = payload.agent_label ?? label;
          payload.agent_name = payload.agent_name ?? label;
          const previousAgent =
            payload.previous_agent ||
            payload.previousAgent ||
            combinedData.previous_agent ||
            combinedData.previousAgent ||
            combinedData.handoff_source ||
            combinedData.handoffSource;
          const fromAgent = previousAgent || currentAgentRef.current;
          const reasonText =
            payload.summary ||
            combinedData.handoff_reason ||
            combinedData.handoffReason ||
            combinedData.message ||
            "Agent switched";
          if (fromAgent && label && label !== fromAgent) {
            appendGraphEvent({
              kind: "switch",
              from: fromAgent,
              to: label,
              text: reasonText,
              ts: payload.ts || payload.timestamp,
            });
          }
          if (label !== "System" && label !== "User") {
            currentAgentRef.current = label;
          }
        }

        const displayLabel = combinedData.active_agent_label || combinedData.agent_label;
        const resolvedMessage =
          payload.message ||
          payload.summary ||
          combinedData.message ||
          (displayLabel ? `Active agent: ${displayLabel}` : null);

        if (resolvedMessage) {
          combinedData.message = resolvedMessage;
          payload.summary = payload.summary ?? resolvedMessage;
          payload.message = payload.message ?? resolvedMessage;
        }

        if (!combinedData.timestamp && payload.ts) {
          combinedData.timestamp = payload.ts;
        }

        payload.data = combinedData;
        payload.event_data = combinedData;
        if (payload.type !== "event") {
          payload.type = "event";
        }
      }

      if (payload.event_type === "call_connected") {
        setCallActive(true);
        appendLog("📞 Call connected");
        const lifecycle = callLifecycleRef.current;
        lifecycle.pending = true;
        lifecycle.active = true;
        lifecycle.callId = payload.call_connection_id || lifecycle.callId;
        lifecycle.lastEnvelopeAt = Date.now();
        lifecycle.reconnectAttempts = 0;
        lifecycle.reconnectScheduled = false;
        lifecycle.stalledLoggedAt = null;
        payload.summary = payload.summary ?? "Call connected";
        payload.type = payload.type ?? "event";
        appendGraphEvent({
          kind: "event",
          from: payload.speaker || "System",
          to: currentAgentRef.current || "Concierge",
          text: "Call connected",
          ts: payload.ts || payload.timestamp,
        });
      }

      if (payload.event_type === "call_disconnected") {
        setCallActive(false);
        setActiveSpeaker(null);
        resetCallLifecycle();
        closeRelaySocket("call disconnected");
        appendLog("📞 Call ended");
        payload.summary = payload.summary ?? "Call disconnected";
        payload.type = payload.type ?? "event";
        appendGraphEvent({
          kind: "event",
          from: payload.speaker || "System",
          to: currentAgentRef.current || "Concierge",
          text: "Call disconnected",
          ts: payload.ts || payload.timestamp,
        });
      }

      if (payload.type === "session_end") {
        const reason = payload.reason || "UNKNOWN";
        terminationReasonRef.current = reason;
        if (reason === "HUMAN_HANDOFF") {
          shouldReconnectRef.current = false;
        }
        resetCallLifecycle();
        setCallActive(false);
        setShowPhoneInput(false);
        const normalizedReason =
          typeof reason === "string" ? reason.split("_").join(" ") : String(reason);
        const reasonText =
          reason === "HUMAN_HANDOFF"
            ? "Transferring you to a live agent. Please stay on the line."
            : `Session ended (${normalizedReason})`;
        setMessages((prev) =>
          pushIfChanged(prev, { speaker: "System", text: reasonText })
        );
        setActiveSpeaker("System");
        appendGraphEvent({
          kind: "event",
          from: "System",
          to: currentAgentRef.current || "Concierge",
          text: reasonText,
          ts: payload.ts || payload.timestamp,
        });
        appendLog(`⚠️ Session ended (${reason})`);
        playbackActiveRef.current = false;
        if (pcmSinkRef.current) {
          pcmSinkRef.current.port.postMessage({ type: "clear" });
        }
        return;
      }

      // Handle turn_metrics from backend - display TTFT/TTFB per turn
      if (payload.type === "turn_metrics") {
        const turnNum = payload.turn_number ?? payload.turnNumber ?? "?";
        const ttftMs = payload.llm_ttft_ms ?? payload.llmTtftMs;
        const ttfbMs = payload.tts_ttfb_ms ?? payload.ttsTtfbMs;
        const sttMs = payload.stt_latency_ms ?? payload.sttLatencyMs;
        const durationMs = payload.duration_ms ?? payload.durationMs;
        const agentName = payload.agent_name ?? payload.agentName ?? "Concierge";
        
        // Log to metrics panel
        publishMetricsSummary(`Turn ${turnNum} server metrics`, {
          ttfbMs: ttfbMs != null ? Math.round(ttfbMs) : undefined,
          ttftMs: ttftMs != null ? Math.round(ttftMs) : undefined,
          sttMs: sttMs != null ? Math.round(sttMs) : undefined,
          durationMs: durationMs != null ? Math.round(durationMs) : undefined,
          agent: agentName,
        });
        
        logger.debug(`📊 Turn ${turnNum} metrics from server:`, {
          ttfbMs,
          ttftMs,
          sttMs,
          durationMs,
          agentName,
        });
        
        return;
      }

      if (payload.event_type === "stt_partial" && payload.data) {
        const partialData = payload.data;
        const partialText = (partialData.content || "").trim();
        const partialMeta = {
          reason: partialData.reason || "stt_partial",
          trigger: partialData.streaming_type || "stt_partial",
          at: partialData.stage || "partial",
          action: "stt_partial",
          sequence: partialData.sequence,
        };

        logger.debug("📝 STT partial detected:", {
          text: partialText,
          sequence: partialData.sequence,
          trigger: partialMeta.trigger,
        });

        const bargeInEvent = recordBargeInEvent("stt_partial", partialMeta);
        const shouldClearPlayback =
          playbackActiveRef.current === true || !bargeInEvent?.clearIssuedTs;

        if (shouldClearPlayback) {
          interruptAssistantOutput(partialMeta, {
            logMessage: "🔇 Audio cleared due to live speech (partial transcription)",
          });

          if (bargeInEvent) {
            finalizeBargeInClear(bargeInEvent, { keepPending: true });
          }
        }

        const now = (typeof performance !== "undefined" && performance.now)
          ? performance.now()
          : Date.now();
        const throttleMs = 90;

        if (partialText) {
          const shouldUpdateUi = now - lastSttPartialUpdateRef.current >= throttleMs;
          if (shouldUpdateUi) {
            lastSttPartialUpdateRef.current = now;
            const turnId =
              partialData.turn_id ||
              partialData.turnId ||
              partialData.response_id ||
              partialData.responseId ||
              null;
            let registeredTurn = false;

            setMessages((prev) => {
              const last = prev.at(-1);
              if (
                last?.speaker === "User" &&
                last?.streaming &&
                (!turnId || last.turnId === turnId)
              ) {
                if (last.text === partialText) {
                  return prev;
                }
                const updated = prev.slice();
                updated[updated.length - 1] = {
                  ...last,
                  text: partialText,
                  streamingType: "stt_partial",
                  sequence: partialData.sequence,
                  language: partialData.language || last.language,
                  turnId: turnId ?? last.turnId,
                };
                return updated;
              }

              registeredTurn = true;
              return [
                ...prev,
                {
                  speaker: "User",
                  text: partialText,
                  streaming: true,
                  streamingType: "stt_partial",
                  sequence: partialData.sequence,
                  language: partialData.language,
                  turnId: turnId ?? undefined,
                },
              ];
            });

            if (registeredTurn) {
              registerUserTurn(partialText);
            }
          }
        }

        setActiveSpeaker("User");
        return;
      }

      if (payload.event_type === "live_agent_transfer") {
        terminationReasonRef.current = "HUMAN_HANDOFF";
        shouldReconnectRef.current = false;
        playbackActiveRef.current = false;
        if (pcmSinkRef.current) {
          pcmSinkRef.current.port.postMessage({ type: "clear" });
        }
        const reasonDetail =
          payload.data?.reason ||
          payload.data?.escalation_reason ||
          payload.data?.message;
        const transferText = reasonDetail
          ? `Escalating to a live agent: ${reasonDetail}`
          : "Escalating you to a live agent. Please hold while we connect.";
        appendGraphEvent({
          kind: "switch",
          from: currentAgentRef.current || "Concierge",
          to: payload.data?.target_agent || "Live Agent",
          text: transferText,
          ts: payload.ts || payload.timestamp,
        });
        currentAgentRef.current = payload.data?.target_agent || "Live Agent";
        setMessages((prev) =>
          pushIfChanged(prev, { speaker: "System", text: transferText })
        );
        setActiveSpeaker("System");
        appendLog("🤝 Escalated to live agent");
        return;
      }

      if (payload.type === "event") {
        const eventType =
          payload.event_type ||
          payload.eventType ||
          payload.name ||
          payload.data?.event_type ||
          "event";
        // Agent inventory/debug info
        if (eventType === "agent_inventory" || payload.payload?.type === "agent_inventory") {
          const summary = formatAgentInventory(payload.payload || payload);
          if (summary) {
            setAgentInventory(summary);
          }
          const agentCount = summary ? (summary.count ?? summary.agents?.length ?? 0) : 0;
          const names = summary?.agents?.slice(0, 5).map((a) => a.name).join(", ");
          setMessages((prev) => [
            ...prev,
            {
              speaker: "System",
              text: `Agents loaded (${agentCount})${summary?.scenario ? ` · scenario: ${summary.scenario}` : ""}${
                names ? ` · ${names}` : ""
              }`,
              statusTone: "info",
              meta: summary,
            },
          ]);
          appendGraphEvent({
            kind: "system",
            from: "System",
            to: "Dashboard",
            text: `Agent inventory (${summary?.source || "unified"})`,
            ts: payload.ts || payload.timestamp,
          });
          appendLog(
            `📦 Agent inventory received (${summary?.count ?? 0} agents${
              summary?.scenario ? ` | scenario=${summary.scenario}` : ""
            })`,
          );
          return;
        }
        const rawEventData =
          payload.data ??
          payload.event_data ??
          (typeof payload.payload === "object" ? payload.payload : null);
        const eventData =
          rawEventData && typeof rawEventData === "object" ? rawEventData : {};
        const eventTimestamp = payload.ts || new Date().toISOString();
        const eventTopic = payload.topic || "session";
        const cascadeType =
          (eventType || "").toLowerCase().includes("speech_cascade") ||
          (eventData.streaming_type || eventData.streamingType) === "speech_cascade";
        const cascadeStage = (eventData.stage || eventData.phase || "").toLowerCase();
        // Skip noisy cascade envelope parts; assistant/user bubbles already handle content
        if (cascadeType && cascadeStage && cascadeStage !== "final") {
          return;
        }

        const eventSpeaker =
          eventData.speaker ||
          eventData.agent ||
          eventData.active_agent_label ||
          payload.speaker ||
          payload.sender ||
          "System";
        const eventSummary =
          payload.summary ||
          payload.message ||
          describeEventData(eventData) ||
          formatEventTypeLabel(eventType);
        const eventAgent = resolveAgentLabel(
          { ...payload, speaker: eventSpeaker, data: eventData },
          currentAgentRef.current,
        );
        if (eventAgent && eventAgent !== "System" && eventAgent !== "User") {
          currentAgentRef.current = eventAgent;
        }

        setMessages((prev) => [
          ...prev,
          {
            type: "event",
            speaker: eventSpeaker,
            eventType,
            data: eventData,
            timestamp: eventTimestamp,
            topic: eventTopic,
            sessionId: payload.session_id || sessionId,
          },
        ]);
        appendGraphEvent({
          kind: "event",
          from: eventSpeaker,
          to: eventData?.target_agent || eventSpeaker,
          text: eventSummary,
          ts: eventTimestamp,
        });
        appendLog(`📡 Event received: ${eventType}`);
        return;
      }
      
      // Handle audio_data messages from backend TTS
      if (payload.type === "audio_data") {
        try {
          if (ENABLE_VERBOSE_STREAM_LOGS) {
            logger.debug("🔊 Received audio_data message:", {
              frame_index: payload.frame_index,
              total_frames: payload.total_frames,
              sample_rate: payload.sample_rate,
              data_length: payload.data ? payload.data.length : 0,
              is_final: payload.is_final,
            });
          }

          const hasData = typeof payload.data === "string" && payload.data.length > 0;

          const isFinalChunk =
            payload.is_final === true ||
            (Number.isFinite(payload.total_frames) &&
              Number.isFinite(payload.frame_index) &&
              payload.frame_index + 1 >= payload.total_frames);

          const frameIndex = Number.isFinite(payload.frame_index) ? payload.frame_index : 0;
          
          // Track generation for this audio stream - first frame starts a new stream
          if (frameIndex === 0) {
            currentAudioGenerationRef.current = assistantStreamGenerationRef.current;
          }
          
          // Check if barge-in happened - skip audio from cancelled turns
          if (currentAudioGenerationRef.current !== assistantStreamGenerationRef.current) {
            logger.debug(`🔇 Skipping stale audio frame (gen ${currentAudioGenerationRef.current} vs ${assistantStreamGenerationRef.current})`);
            // Still mark as not active since we're skipping
            playbackActiveRef.current = false;
            return;
          }
          
          registerAudioFrame(frameIndex, isFinalChunk);

          // Resume playback context if suspended (after text barge-in)
          if (playbackAudioContextRef.current) {
            const ctx = playbackAudioContextRef.current;
            logger.debug(`[Audio] Playback context state: ${ctx.state}`);
            if (ctx.state === "suspended") {
              logger.info("[Audio] Resuming suspended playback context...");
              await ctx.resume();
              appendLog("▶️ TTS playback resumed");
              logger.debug(`[Audio] Playback context state after resume: ${ctx.state}`);
            }
          } else {
            logger.warn("[Audio] No playback context found, initializing...");
            await initializeAudioPlayback();
          }

          if (!hasData) {
            playbackActiveRef.current = !isFinalChunk;
            updateOutputLevelMeter();
            return;
          }

          // Decode base64 -> Int16 -> Float32 [-1, 1]
          const bstr = atob(payload.data);
          const buf = new ArrayBuffer(bstr.length);
          const view = new Uint8Array(buf);
          for (let i = 0; i < bstr.length; i++) view[i] = bstr.charCodeAt(i);
          const int16 = new Int16Array(buf);
          const float32 = new Float32Array(int16.length);
          for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x8000;

          if (ENABLE_VERBOSE_STREAM_LOGS) {
            logger.debug(
              `🔊 Processing TTS audio chunk: ${float32.length} samples, sample_rate: ${payload.sample_rate || 16000}`,
            );
            logger.debug("🔊 Audio data preview:", float32.slice(0, 10));
          }

          // Push to the worklet queue
          if (pcmSinkRef.current) {
            let samples = float32;
            const playbackCtx = playbackAudioContextRef.current;
            const sourceRate = payload.sample_rate;
            if (playbackCtx && Number.isFinite(sourceRate) && sourceRate && playbackCtx.sampleRate !== sourceRate) {
              samples = resampleFloat32(float32, sourceRate, playbackCtx.sampleRate);
              if (!resampleWarningRef.current && ENABLE_VERBOSE_STREAM_LOGS) {
                appendLog(`🎚️ Resampling audio ${sourceRate}Hz → ${playbackCtx.sampleRate}Hz`);
                resampleWarningRef.current = true;
              }
            }
            pcmSinkRef.current.port.postMessage({ type: 'push', payload: samples });
            updateOutputLevelMeter(samples);
            if (ENABLE_VERBOSE_STREAM_LOGS) {
              appendLog(`🔊 TTS audio frame ${payload.frame_index + 1}/${payload.total_frames}`);
            }
          } else {
            if (!audioInitFailedRef.current) {
              logger.warn("Audio playback not initialized, attempting init...");
              if (ENABLE_VERBOSE_STREAM_LOGS) {
                appendLog("⚠️ Audio playback not ready, initializing...");
              }
              // Try to initialize if not done yet
              await initializeAudioPlayback();
              if (pcmSinkRef.current) {
                let samples = float32;
                const playbackCtx = playbackAudioContextRef.current;
                const sourceRate = payload.sample_rate;
                if (playbackCtx && Number.isFinite(sourceRate) && sourceRate && playbackCtx.sampleRate !== sourceRate) {
                  samples = resampleFloat32(float32, sourceRate, playbackCtx.sampleRate);
                  if (!resampleWarningRef.current && ENABLE_VERBOSE_STREAM_LOGS) {
                    appendLog(`🎚️ Resampling audio ${sourceRate}Hz → ${playbackCtx.sampleRate}Hz`);
                    resampleWarningRef.current = true;
                  }
                }
                pcmSinkRef.current.port.postMessage({ type: 'push', payload: samples });
                updateOutputLevelMeter(samples);
                if (ENABLE_VERBOSE_STREAM_LOGS) {
                  appendLog("🔊 TTS audio playing (after init)");
                }
              } else {
                logger.error("Failed to initialize audio playback");
                if (ENABLE_VERBOSE_STREAM_LOGS) {
                  appendLog("❌ Audio init failed");
                }
              }
            }
            // If init already failed, silently skip audio frames
          }
          playbackActiveRef.current = !isFinalChunk;
          return; // handled
        } catch (error) {
          logger.error("Error processing audio_data:", error);
          appendLog("❌ Audio processing failed: " + error.message);
        }
      }
      
      // --- Handle relay/broadcast messages with {sender, message} ---
      if (payload.sender && payload.message) {
        // Route all relay messages through the same logic
        payload.speaker = payload.sender;
        payload.content = payload.message;
        // fall through to unified logic below
      }
      if (!payload || typeof payload !== "object") {
        appendLog("Ignored malformed payload");
        return;
      }

      const { type, content = "", message = "", speaker } = payload;
      const txt = content || message;
      const msgType = (type || "").toLowerCase();

      if (msgType === "session_profile" || msgType === "demo_profile") {
        const sessionKey = payload.session_id ?? sessionId;
        if (sessionKey) {
          setSessionProfiles((prev) => {
            const normalized = buildSessionProfile(payload, sessionKey, prev[sessionKey]);
            if (!normalized) {
              return prev;
            }
            return {
              ...prev,
              [sessionKey]: normalized,
            };
          });
          appendLog(`Session profile acknowledged for ${sessionKey}`);
        }
        return;
      }

      if (msgType === "user" || speaker === "User") {
        setActiveSpeaker("User");
        const turnId =
          payload.turn_id ||
          payload.turnId ||
          payload.response_id ||
          payload.responseId ||
          null;
        const isStreamingUser = payload.streaming === true;

        if (turnId) {
          updateTurnMessage(
            turnId,
            (current = {}) => ({
              speaker: "User",
              text: txt ?? current.text ?? "",
              streaming: isStreamingUser,
              streamingType: isStreamingUser ? "stt_final" : undefined,
              cancelled: false,
            }),
            {
              initial: () => ({
                speaker: "User",
                text: txt,
                streaming: isStreamingUser,
                streamingType: isStreamingUser ? "stt_final" : undefined,
                turnId,
              }),
            },
          );
        } else {
          setMessages((prev) => {
            const last = prev.at(-1);
            if (last?.speaker === "User" && last?.streaming) {
              return prev.map((m, i) =>
                i === prev.length - 1
                  ? { ...m, text: txt, streaming: isStreamingUser }
                  : m,
              );
            }
            return [...prev, { speaker: "User", text: txt, streaming: isStreamingUser }];
          });
        }
        appendLog(`User: ${txt}`);
        setLastUserMessage(txt);
        const shouldGraph =
          !isStreamingUser || payload.is_final === true || payload.final === true;
        if (shouldGraph) {
          const targetAgent =
            resolveAgentLabel(payload, effectiveAgent()) ||
            effectiveAgent() ||
            "Assistant";
          appendGraphEvent({
            kind: "message",
            from: "User",
            to: targetAgent,
            text: txt,
            ts: payload.ts || payload.timestamp,
          });
        }
        return;
      }

      if (type === "assistant_cancelled") {
        const turnId =
          payload.turn_id ||
          payload.turnId ||
          payload.response_id ||
          payload.responseId ||
          null;
        if (turnId) {
          updateTurnMessage(
            turnId,
            (current) =>
              current
                ? {
                    streaming: false,
                    cancelled: true,
                    cancelReason:
                      payload.cancel_reason ||
                      payload.cancelReason ||
                      payload.reason ||
                      current.cancelReason,
                  }
                : null,
            { createIfMissing: false },
          );
        }
        setActiveSpeaker(null);
        appendLog("🤖 Assistant response interrupted");
        return;
      }

      if (type === "assistant_streaming") {
        const streamingSpeaker = speaker || "Concierge";
        const streamGeneration = assistantStreamGenerationRef.current;
        registerAssistantStreaming(streamingSpeaker);
        setActiveSpeaker(streamingSpeaker);
        const now = (typeof performance !== "undefined" && performance.now)
          ? performance.now()
          : Date.now();
        const throttleMs = 90;
        const shouldUpdateUi = now - lastAssistantStreamUpdateRef.current >= throttleMs;
        const turnId =
          payload.turn_id ||
          payload.turnId ||
          payload.response_id ||
          payload.responseId ||
          null;

        if (shouldUpdateUi) {
          lastAssistantStreamUpdateRef.current = now;
          if (turnId) {
            updateTurnMessage(
              turnId,
              (current) => {
                const previousText =
                  current?.streamGeneration === streamGeneration
                    ? current?.text ?? ""
                    : "";
                return {
                  speaker: streamingSpeaker,
                  text: `${previousText}${txt}`,
                  streaming: true,
                  streamGeneration,
                  cancelled: false,
                  cancelReason: undefined,
                };
              },
              {
                initial: () => ({
                  speaker: streamingSpeaker,
                  text: txt,
                  streaming: true,
                  streamGeneration,
                  turnId,
                  cancelled: false,
                }),
              },
            );
          } else {
            setMessages((prev) => {
              const latest = prev.at(-1);
              if (
                latest?.streaming &&
                latest?.speaker === streamingSpeaker &&
                latest?.streamGeneration === streamGeneration
              ) {
                return prev.map((m, i) =>
                  i === prev.length - 1
                    ? {
                        ...m,
                        text: m.text + txt,
                        cancelled: false,
                        cancelReason: undefined,
                      }
                    : m,
                );
              }
              return [
                ...prev,
                {
                  speaker: streamingSpeaker,
                  text: txt,
                  streaming: true,
                  streamGeneration,
                  cancelled: false,
                },
              ];
            });
          }
        }
        const pending = metricsRef.current?.pendingBargeIn;
        if (pending) {
          finalizeBargeInClear(pending);
        }
        return;
      }

      if (msgType === "assistant" || msgType === "status" || speaker === "Concierge") {
        if (msgType === "status") {
          const normalizedStatus = (txt || "").toLowerCase();
          if (
            normalizedStatus.includes("call connected") ||
            normalizedStatus.includes("call disconnected")
          ) {
            return;
          }
        }
        const assistantSpeaker = resolveAgentLabel(payload, speaker || "Concierge");
        registerAssistantFinal(assistantSpeaker);
        setActiveSpeaker(assistantSpeaker);
        const messageOptions = {
          speaker: assistantSpeaker,
          text: txt,
        };
        if (payload.statusLabel) {
          messageOptions.statusLabel = payload.statusLabel;
        }
        if (payload.statusTone) {
          messageOptions.statusTone = payload.statusTone;
        }
        if (payload.statusCaption) {
          messageOptions.statusCaption = payload.statusCaption;
        }
        if (payload.ts || payload.timestamp) {
          messageOptions.timestamp = payload.ts || payload.timestamp;
        }
        const turnId =
          payload.turn_id ||
          payload.turnId ||
          payload.response_id ||
          payload.responseId ||
          null;

        if (turnId) {
          updateTurnMessage(
            turnId,
            (current) => ({
              ...messageOptions,
              text: txt ?? current?.text ?? "",
              streaming: false,
              cancelled: false,
              cancelReason: undefined,
            }),
            {
              initial: () => ({
                ...messageOptions,
                streaming: false,
                cancelled: false,
                turnId,
              }),
            },
          );
        } else {
          setMessages((prev) => {
            for (let idx = prev.length - 1; idx >= 0; idx -= 1) {
              const candidate = prev[idx];
              if (candidate?.streaming) {
                return prev.map((m, i) =>
                  i === idx
                    ? {
                        ...m,
                        ...messageOptions,
                        streaming: false,
                        cancelled: false,
                        cancelReason: undefined,
                      }
                    : m,
                );
              }
            }
            return pushIfChanged(prev, {
              ...messageOptions,
              cancelled: false,
              cancelReason: undefined,
            });
          });
        }

        const agentLabel = resolveAgentLabel(payload, assistantSpeaker);
        if (agentLabel && agentLabel !== "System" && agentLabel !== "User") {
          currentAgentRef.current = agentLabel;
        }
        appendGraphEvent({
          kind: "message",
          from: agentLabel || assistantSpeaker || "Assistant",
          to: "User",
          text: txt,
          ts: payload.ts || payload.timestamp,
        });
        appendLog("🤖 Assistant responded");
        setLastAssistantMessage(txt);
        return;
      }
    
      if (
        type === "function_call" ||
        payload.function_call ||
        payload.function_call_id ||
        payload.tool_call_id
      ) {
        const fnName =
          payload.function_call?.name ||
          payload.name ||
          payload.tool ||
          payload.function_name ||
          payload.tool_name ||
          "Function";
        const argText =
          typeof payload.function_call?.arguments === "string"
            ? payload.function_call.arguments.slice(0, 120)
            : "";
        appendGraphEvent({
          kind: "function",
          from: resolveAgentLabel(payload, currentAgentRef.current || "Assistant"),
          to: fnName,
          text: argText || payload.summary || "Function call",
          ts: payload.ts || payload.timestamp,
        });
        return;
      }

      if (type === "tool_start") {
        setMessages((prev) => [
          ...prev,
          {
            speaker: "Assistant",
            isTool: true,
            text: `🛠️ tool ${payload.tool} started 🔄`,
          },
        ]);
        appendGraphEvent({
          kind: "tool",
          from: resolveAgentLabel(payload, currentAgentRef.current || "Assistant"),
          to: resolveAgentLabel(payload, currentAgentRef.current || "Assistant"),
          tool: payload.tool,
          text: "started",
          ts: payload.ts || payload.timestamp,
        });
        appendLog(`⚙️ ${payload.tool} started`);
        return;
      }
      
    
      if (type === "tool_progress") {
        const pctNumeric = Number(payload.pct);
        const pctText = Number.isFinite(pctNumeric)
          ? `${pctNumeric}%`
          : payload.pct
          ? `${payload.pct}`
          : "progress";
        updateToolMessage(
          payload.tool,
          (message) => ({
            ...message,
            text: `🛠️ tool ${payload.tool} ${pctText} 🔄`,
          }),
          () => ({
            speaker: "Assistant",
            isTool: true,
            text: `🛠️ tool ${payload.tool} ${pctText} 🔄`,
          }),
        );
        appendGraphEvent({
          kind: "tool",
          from: resolveAgentLabel(payload, currentAgentRef.current || "Assistant"),
          to: resolveAgentLabel(payload, currentAgentRef.current || "Assistant"),
          tool: payload.tool,
          text: pctText,
          ts: payload.ts || payload.timestamp,
        });
        appendLog(`⚙️ ${payload.tool} ${pctText}`);
        return;
      }
    
      if (type === "tool_end") {

        const resultPayload =
          payload.result ?? payload.output ?? payload.data ?? payload.response;
        const serializedResult =
          resultPayload !== undefined
            ? JSON.stringify(resultPayload, null, 2)
            : null;
        const finalText =
          payload.status === "success"
            ? `🛠️ tool ${payload.tool} completed ✔️${
                serializedResult ? `\n${serializedResult}` : ""
              }`
            : `🛠️ tool ${payload.tool} failed ❌\n${payload.error}`;
        updateToolMessage(
          payload.tool,
          (message) => ({
            ...message,
            text: finalText,
          }),
          {
            speaker: "Assistant",
            isTool: true,
            text: finalText,
          },
        );

        const handoffTarget =
          (resultPayload &&
            typeof resultPayload === "object" &&
            (resultPayload.target_agent ||
              resultPayload.handoff_target ||
              resultPayload.handoffTarget ||
              resultPayload.targetAgent)) ||
          payload.target_agent ||
          payload.handoff_target ||
          payload.handoffTarget;
        if (handoffTarget) {
          const sourceAgent = resolveAgentLabel(payload, currentAgentRef.current || "Assistant");
          const handoffReason =
            (resultPayload &&
              typeof resultPayload === "object" &&
              (resultPayload.handoff_summary ||
                resultPayload.handoffSummary ||
                resultPayload.message ||
                resultPayload.reason)) ||
            payload.summary ||
            payload.message;
          appendGraphEvent({
            kind: "switch",
            from: sourceAgent,
            to: handoffTarget,
            text: handoffReason || `Handoff via ${payload.tool}`,
            ts: payload.ts || payload.timestamp,
          });
        }

        appendGraphEvent({
          kind: "tool",
          from: resolveAgentLabel(payload, currentAgentRef.current || "Assistant"),
          to: resolveAgentLabel(payload, currentAgentRef.current || "Assistant"),
          tool: payload.tool,
          text: payload.status || "completed",
          detail: serializedResult || payload.error,
          ts: payload.ts || payload.timestamp,
        });
        appendLog(`⚙️ ${payload.tool} ${payload.status} (${payload.elapsedMs} ms)`);
        return;
      }

      if (type === "control") {
        const { action } = payload;
        logger.debug("🎮 Control message received:", action);
        
        if (action === "tts_cancelled" || action === "audio_stop") {
          logger.debug(`🔇 Control audio stop received (${action}) - clearing audio queue`);
          const meta = {
            reason: payload.reason,
            trigger: payload.trigger,
            at: payload.at,
            action,
          };
          const event = recordBargeInEvent(action, meta);
          interruptAssistantOutput(meta);
          if (action === "audio_stop" && event) {
            finalizeBargeInClear(event);
          }
          return;
        }

        logger.debug("🎮 Unknown control action:", action);
        return;
      }
    };

    handleSocketMessageRef.current = handleSocketMessage;
  
  /* ------------------------------------------------------------------ *
   *  OUTBOUND ACS CALL
   * ------------------------------------------------------------------ */
  const openRelaySocket = useCallback((targetSessionId, options = {}) => {
    const { reason = "manual", suppressLog = false } = options;
    if (!targetSessionId) {
      return null;
    }

    const lifecycle = callLifecycleRef.current;
    if (relayReconnectTimeoutRef.current && typeof window !== "undefined") {
      window.clearTimeout(relayReconnectTimeoutRef.current);
      relayReconnectTimeoutRef.current = null;
    }
    lifecycle.reconnectScheduled = false;

    try {
      const encodedSession = encodeURIComponent(targetSessionId);
      const relayUrl = `${WS_URL}/api/v1/browser/dashboard/relay?session_id=${encodedSession}`;
      closeRelaySocket(`${reason || "manual"} reopen`, { preserveLifecycle: true });
      if (!suppressLog) {
        appendLog(`Connecting relay WS (${reason})`);
      }

      const relay = new WebSocket(relayUrl);
      relaySocketRef.current = relay;
      lifecycle.lastRelayOpenedAt = Date.now();

      relay.onopen = () => {
        appendLog("Relay WS connected");
        lifecycle.reconnectAttempts = 0;
        lifecycle.reconnectScheduled = false;
        lifecycle.stalledLoggedAt = null;
        lifecycle.lastEnvelopeAt = Date.now();
      };

      relay.onerror = (error) => {
        logger.error("Relay WS error:", error);
        appendLog("Relay WS error");
      };

      relay.onmessage = ({ data }) => {
        lifecycle.lastEnvelopeAt = Date.now();
        try {
          const obj = JSON.parse(data);
          let processedObj = obj;

          if (obj && obj.type && obj.sender && obj.payload && obj.ts) {
            logger.debug("📨 Relay received envelope message:", {
              type: obj.type,
              sender: obj.sender,
              topic: obj.topic,
            });

            processedObj = {
              type: obj.type,
              sender: obj.sender,
              ...obj.payload,
            };
            logger.debug("📨 Transformed relay envelope:", processedObj);
          }

          const handler = handleSocketMessageRef.current;
          if (handler) {
            handler({ data: JSON.stringify(processedObj) });
          }
        } catch (error) {
          logger.error("Relay parse error:", error);
          appendLog("Relay parse error");
        }
      };

      relay.onclose = (event) => {
        if (relaySocketRef.current === relay) {
          relaySocketRef.current = null;
        }

        const state = callLifecycleRef.current;
        const pending = state.pending;
        const code = event?.code;
        const reasonText = event?.reason;

        if (!pending) {
          appendLog("Relay WS disconnected");
          setCallActive(false);
          setActiveSpeaker(null);
          return;
        }

        const details = [code ?? "no code"];
        if (reasonText) {
          details.push(reasonText);
        }
        appendLog(`Relay WS closed (${details.join(": ")}) – scheduling retry`);

        state.reconnectAttempts = Math.min(state.reconnectAttempts + 1, 6);
        state.reconnectScheduled = true;

        if (typeof window !== "undefined") {
          const baseDelay = 800;
          const delay = Math.min(10000, baseDelay * Math.pow(2, state.reconnectAttempts - 1));
          if (relayReconnectTimeoutRef.current) {
            window.clearTimeout(relayReconnectTimeoutRef.current);
          }
          relayReconnectTimeoutRef.current = window.setTimeout(() => {
            relayReconnectTimeoutRef.current = null;
            state.reconnectScheduled = false;
            if (!callLifecycleRef.current.pending) {
              return;
            }
            const opener = openRelaySocketRef.current;
            if (opener) {
              opener(targetSessionId, { reason: "auto-reconnect", suppressLog: true });
            }
          }, delay);
        }
      };

      return relay;
    } catch (error) {
      logger.error("Failed to open relay websocket:", error);
      appendLog("Relay WS open failed");
      return null;
    }
  }, [appendLog, closeRelaySocket, setActiveSpeaker, setCallActive]);

  openRelaySocketRef.current = openRelaySocket;

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const interval = window.setInterval(() => {
      const lifecycle = callLifecycleRef.current;
      if (!lifecycle.pending) {
        return;
      }

      const relay = relaySocketRef.current;
      const sessionKey = sessionId || getOrCreateSessionId();
      const now = Date.now();

      if (!relay || relay.readyState !== WebSocket.OPEN) {
        if (!lifecycle.reconnectScheduled) {
          lifecycle.reconnectScheduled = true;
          lifecycle.reconnectAttempts = Math.min(lifecycle.reconnectAttempts + 1, 6);
          const baseDelay = 800;
          const delay = Math.min(10000, baseDelay * Math.pow(2, lifecycle.reconnectAttempts - 1));
          if (relayReconnectTimeoutRef.current) {
            window.clearTimeout(relayReconnectTimeoutRef.current);
          }
          relayReconnectTimeoutRef.current = window.setTimeout(() => {
            relayReconnectTimeoutRef.current = null;
            lifecycle.reconnectScheduled = false;
            if (!callLifecycleRef.current.pending) {
              return;
            }
            const opener = openRelaySocketRef.current;
            if (opener) {
              opener(sessionKey, { reason: "monitor-reconnect", suppressLog: true });
            }
          }, delay);
        }
        return;
      }

      lifecycle.reconnectAttempts = 0;

      if (lifecycle.lastEnvelopeAt && now - lifecycle.lastEnvelopeAt > 15000) {
        if (!lifecycle.stalledLoggedAt || now - lifecycle.stalledLoggedAt > 15000) {
          appendLog("⚠️ No ACS updates in 15s — refreshing relay subscription.");
          lifecycle.stalledLoggedAt = now;
        }
        const opener = openRelaySocketRef.current;
        if (opener) {
          opener(sessionKey, { reason: "envelope-timeout", suppressLog: true });
        }
        lifecycle.lastEnvelopeAt = Date.now();
      }
    }, 6000);

    relayHealthIntervalRef.current = interval;

    return () => {
      if (relayHealthIntervalRef.current && typeof window !== "undefined") {
        window.clearInterval(relayHealthIntervalRef.current);
        relayHealthIntervalRef.current = null;
      }
    };
  }, [appendLog, sessionId]);

  const startACSCall = async () => {
    if (systemStatus.status === "degraded" && systemStatus.acsOnlyIssue) {
      appendLog("🚫 Outbound calling disabled until ACS configuration is provided.");
      return;
    }
    if (!/^\+\d+$/.test(targetPhoneNumber)) {
      alert("Enter phone in E.164 format e.g. +15551234567");
      return;
    }
    try {
      // Get the current session ID for this browser session
      const currentSessionId = getOrCreateSessionId();
      logger.info(
        `📞 [FRONTEND] Initiating phone call with session_id: ${currentSessionId} (streaming_mode=${selectedStreamingMode})`,
      );
      logger.debug(
        '📞 [FRONTEND] This session_id will be sent to backend for call mapping',
      );
      
      const res = await fetch(`${API_BASE_URL}/api/v1/calls/initiate`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ 
          target_number: targetPhoneNumber,
          streaming_mode: selectedStreamingMode,
          context: {
            browser_session_id: currentSessionId,  // 🎯 Pass browser session ID for ACS coordination
            streaming_mode: selectedStreamingMode,
          }
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        appendLog(`Call error: ${json.detail||res.statusText}`);
        resetCallLifecycle();
        return;
      }
      const newCallId = json.call_id ?? json.callId ?? null;
      setCurrentCallId(newCallId);
      if (!newCallId) {
        appendLog("⚠️ Call initiated but call_id missing from response");
      }
      // show in chat with dedicated system card
      const readableMode = selectedStreamingModeLabel || selectedStreamingMode;
      appendSystemMessage("📞 Call started", {
        tone: "call",
        statusCaption: `→ ${targetPhoneNumber} · Mode: ${readableMode}`,
        statusLabel: "Call Initiated",
      });
      appendLog(`📞 Call initiated (mode: ${readableMode})`);
      setShowPhoneInput(false);
      const lifecycle = callLifecycleRef.current;
      lifecycle.pending = true;
      lifecycle.active = false;
      lifecycle.callId = newCallId ?? null;
      lifecycle.lastEnvelopeAt = Date.now();
      lifecycle.reconnectAttempts = 0;
      lifecycle.reconnectScheduled = false;
      lifecycle.stalledLoggedAt = null;
      lifecycle.lastRelayOpenedAt = 0;

      logger.info('🔗 [FRONTEND] Starting dashboard relay WebSocket to monitor session:', currentSessionId);
      openRelaySocket(currentSessionId, { reason: "call-start" });
    } catch(e) {
      appendLog(`Network error starting call: ${e.message}`);
      resetCallLifecycle();
    }
  };

  /* ------------------------------------------------------------------ *
   *  RENDER
   * ------------------------------------------------------------------ */
  const recentTools = useMemo(
    () => graphEvents.filter((evt) => evt.kind === "tool").slice(-5).reverse(),
    [graphEvents],
  );

  return (
    <div style={{ ...styles.root, maxWidth: `${chatWidth}px` }}>
      <div style={{ ...styles.mainContainer, maxWidth: `${chatWidth}px` }}>
        {/* Left Vertical Sidebar - Sleek Professional Design */}
        <div style={{
          position: 'fixed',
          top: '50%',
          left: '20px',
          transform: 'translateY(-50%)',
          zIndex: 1300,
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          alignItems: 'center',
          background: 'linear-gradient(145deg, rgba(255,255,255,0.98), rgba(248,250,252,0.95))',
          padding: '12px 10px',
          borderRadius: '20px',
          boxShadow: '0 4px 24px rgba(15,23,42,0.08), 0 0 0 1px rgba(226,232,240,0.4), inset 0 1px 0 rgba(255,255,255,0.8)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
        }}>
          {/* Scenario Selector Button */}
          <div style={{
            paddingBottom: '8px',
            borderBottom: '1px solid rgba(226,232,240,0.6)',
            position: 'relative',
            width: '100%',
            display: 'flex',
            justifyContent: 'center',
          }}>
            <button
              ref={scenarioButtonRef}
              onClick={() => setShowScenarioMenu((prev) => !prev)}
              title="Select Industry Scenario"
              style={{
                width: '44px',
                height: '44px',
                borderRadius: '12px',
                border: '1px solid rgba(226,232,240,0.6)',
                background: getSessionScenario()?.startsWith('custom_') 
                  ? 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)'
                  : getSessionScenario() === 'banking' 
                    ? 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)'
                    : 'linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%)',
                color: '#ffffff',
                fontSize: '18px',
                fontWeight: '500',
                cursor: 'pointer',
                transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                boxShadow: '0 2px 8px rgba(15,23,42,0.1), inset 0 1px 0 rgba(255,255,255,0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = '0 4px 16px rgba(15,23,42,0.15), inset 0 1px 0 rgba(255,255,255,0.15)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)';
                e.currentTarget.style.boxShadow = '0 2px 8px rgba(15,23,42,0.1), inset 0 1px 0 rgba(255,255,255,0.15)';
              }}
            >
              {getSessionScenarioIcon()}
            </button>

            {/* Scenario Selection Menu */}
            {showScenarioMenu && (
              <div 
                data-scenario-menu
                style={{
                position: 'absolute',
                left: '64px',
                top: '0',
                background: 'linear-gradient(145deg, rgba(255,255,255,0.98), rgba(248,250,252,0.95))',
                borderRadius: '14px',
                padding: '6px',
                boxShadow: '0 8px 32px rgba(15,23,42,0.12), 0 0 0 1px rgba(226,232,240,0.4), inset 0 1px 0 rgba(255,255,255,0.8)',
                backdropFilter: 'blur(24px)',
                WebkitBackdropFilter: 'blur(24px)',
                minWidth: '200px',
                zIndex: 1400,
              }}>
                {/* Built-in Scenarios */}
                <div style={{
                  padding: '4px 8px 6px',
                  fontSize: '10px',
                  fontWeight: '600',
                  color: '#94a3b8',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}>
                  Industry Templates
                </div>
                {[
                  { id: 'banking', icon: '🏦', label: 'Banking' },
                  { id: 'insurance', icon: '🛡️', label: 'Insurance' },
                ].map(({ id, icon, label }) => (
                  <button
                    key={id}
                    onClick={async () => {
                      // Apply industry template to session on backend
                      try {
                        await fetch(
                          `${API_BASE_URL}/api/v1/scenario-builder/session/${sessionId}/apply-template?template_id=${encodeURIComponent(id)}`,
                          { method: 'POST' }
                        );
                        appendLog(`${icon} Applied ${label} template to session ${sessionId}`);
                      } catch (err) {
                        appendLog(`Failed to apply template: ${err.message}`);
                      }
                      
                      setSessionScenario(id);
                      setShowScenarioMenu(false);
                      appendLog(`${icon} Switched to ${label} for session ${sessionId}`);
                      
                      if (callActive) {
                        // ACS mode: restart the call with new scenario
                        appendLog(`🔄 Restarting call with ${label} scenario...`);
                        terminateACSCall();
                        setTimeout(() => {
                          handlePhoneButtonClick();
                        }, 500);
                      } else if (recording) {
                        // Browser recording mode: reconnect WebSocket with new scenario
                        appendLog(`🔄 Reconnecting with ${label} scenario...`);
                        handleMicToggle(); // Stop current recording
                        setTimeout(() => {
                          handleMicToggle(); // Start new recording with new scenario
                        }, 500);
                      }
                    }}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      borderRadius: '10px',
                      border: 'none',
                      background: getSessionScenario() === id 
                        ? 'linear-gradient(135deg, rgba(99,102,241,0.1), rgba(79,70,229,0.08))' 
                        : 'transparent',
                      color: getSessionScenario() === id ? '#4f46e5' : '#64748b',
                      fontSize: '13px',
                      fontWeight: getSessionScenario() === id ? '600' : '500',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                      textAlign: 'left',
                    }}
                    onMouseEnter={(e) => {
                      if (getSessionScenario() !== id) {
                        e.currentTarget.style.background = 'rgba(148,163,184,0.06)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (getSessionScenario() !== id) {
                        e.currentTarget.style.background = 'transparent';
                      }
                    }}
                  >
                    <span style={{ fontSize: '16px' }}>{icon}</span>
                    <span>{label}</span>
                    {getSessionScenario() === id && (
                      <span style={{ marginLeft: 'auto', fontSize: '14px', color: '#4f46e5' }}>✓</span>
                    )}
                  </button>
                ))}

                {/* Custom Scenarios (show all custom scenarios for the session) */}
                {sessionScenarioConfig?.scenarios?.length > 0 && (
                  <>
                    <div style={{
                      margin: '8px 0 4px',
                      borderTop: '1px solid rgba(226,232,240,0.6)',
                      paddingTop: '8px',
                    }}>
                      <div style={{
                        padding: '4px 8px 6px',
                        fontSize: '10px',
                        fontWeight: '600',
                        color: '#f59e0b',
                        textTransform: 'uppercase',
                        letterSpacing: '0.5px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}>
                        <span style={{ fontSize: '12px' }}>🎭</span>
                        Custom Scenarios ({sessionScenarioConfig.scenarios.length})
                      </div>
                    </div>
                    {sessionScenarioConfig.scenarios.map((scenario, index) => {
                      const scenarioKey = `custom_${scenario.name.replace(/\s+/g, '_').toLowerCase()}`;
                      const isActive = getSessionScenario() === scenarioKey;
                      const scenarioIcon = scenario.icon || '🎭';
                      return (
                        <button
                          key={scenarioKey}
                          onClick={async () => {
                            // Set active scenario on backend
                            try {
                              await fetch(
                                `${API_BASE_URL}/api/v1/scenario-builder/session/${sessionId}/active?scenario_name=${encodeURIComponent(scenario.name)}`,
                                { method: 'POST' }
                              );
                            } catch (err) {
                              appendLog(`Failed to set active scenario: ${err.message}`);
                            }
                            
                            setSessionScenario(scenarioKey);
                            setShowScenarioMenu(false);
                            appendLog(`${scenarioIcon} Switched to Custom Scenario: ${scenario.name}`);
                            
                            if (callActive) {
                              appendLog(`🔄 Restarting call with custom scenario...`);
                              terminateACSCall();
                              setTimeout(() => {
                                handlePhoneButtonClick();
                              }, 500);
                            } else if (recording) {
                              appendLog(`🔄 Reconnecting with custom scenario...`);
                              handleMicToggle();
                              setTimeout(() => {
                                handleMicToggle();
                              }, 500);
                            }
                          }}
                          style={{
                            width: '100%',
                            padding: '10px 14px',
                            borderRadius: '10px',
                            border: 'none',
                            background: isActive 
                              ? 'linear-gradient(135deg, rgba(245,158,11,0.15), rgba(217,119,6,0.1))' 
                              : 'transparent',
                            color: isActive ? '#d97706' : '#64748b',
                            fontSize: '13px',
                            fontWeight: isActive ? '600' : '500',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                            textAlign: 'left',
                            marginBottom: index < sessionScenarioConfig.scenarios.length - 1 ? '4px' : 0,
                          }}
                          onMouseEnter={(e) => {
                            if (!isActive) {
                              e.currentTarget.style.background = 'rgba(245,158,11,0.06)';
                            }
                          }}
                          onMouseLeave={(e) => {
                            if (!isActive) {
                              e.currentTarget.style.background = 'transparent';
                            }
                          }}
                        >
                          <span style={{ fontSize: '16px' }}>{scenarioIcon}</span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ 
                              overflow: 'hidden', 
                              textOverflow: 'ellipsis', 
                              whiteSpace: 'nowrap',
                            }}>
                              {scenario.name}
                            </div>
                            <div style={{ 
                              fontSize: '10px', 
                              color: '#94a3b8',
                              fontWeight: '400',
                            }}>
                              {scenario.agents?.length || 0} agents · {scenario.handoffs?.length || 0} handoffs
                            </div>
                          </div>
                          {isActive && (
                            <span style={{ fontSize: '14px', color: '#d97706' }}>✓</span>
                          )}
                        </button>
                      );
                    })}
                  </>
                )}

                <div style={{
                  marginTop: '8px',
                  padding: '8px 10px 6px',
                  borderRadius: '10px',
                  background: 'rgba(148,163,184,0.08)',
                  color: '#475569',
                  fontSize: '11px',
                  lineHeight: 1.4,
                  border: '1px dashed rgba(148,163,184,0.35)',
                }}>
                  {sessionScenarioConfig?.scenarios?.length > 0 
                    ? 'Switch between scenarios for this session'
                    : 'Create a custom scenario in the Scenario Builder'}
                </div>
              </div>
            )}
          </div>

          {/* Agent Builder Button */}
          <button
            onClick={() => {
              setBuilderInitialMode('agents');
              setShowAgentScenarioBuilder(true);
            }}
            title="Agent Builder"
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '12px',
              border: '1px solid rgba(226,232,240,0.6)',
              background: 'linear-gradient(145deg, #ffffff, #fafbfc)',
              color: '#f59e0b',
              fontSize: '18px',
              cursor: 'pointer',
              transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
              boxShadow: '0 2px 8px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(245,158,11,0.2), inset 0 1px 0 rgba(255,255,255,0.8)';
              e.currentTarget.style.background = 'linear-gradient(135deg, #fef3c7, #fde68a)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 2px 8px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)';
              e.currentTarget.style.background = 'linear-gradient(145deg, #ffffff, #fafbfc)';
            }}
          >
            <BuildRoundedIcon fontSize="small" />
          </button>

          {/* Agent Context Button */}
          <button
            onClick={() => setShowAgentPanel((prev) => !prev)}
            title="Agent Context"
            style={{
              width: '44px',
              height: '44px',
              borderRadius: '12px',
              border: '1px solid rgba(226,232,240,0.6)',
              background: 'linear-gradient(145deg, #ffffff, #fafbfc)',
              color: '#0ea5e9',
              fontSize: '18px',
              cursor: 'pointer',
              transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
              boxShadow: '0 2px 8px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(14,165,233,0.2), inset 0 1px 0 rgba(255,255,255,0.8)';
              e.currentTarget.style.background = 'linear-gradient(135deg, #e0f2fe, #bae6fd)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 2px 8px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)';
              e.currentTarget.style.background = 'linear-gradient(145deg, #ffffff, #fafbfc)';
            }}
          >
            <SmartToyRoundedIcon fontSize="small" />
          </button>

          {/* Divider */}
          <div style={{
            width: '32px',
            height: '1px',
            background: 'linear-gradient(90deg, transparent, rgba(226,232,240,0.6), transparent)',
            margin: '4px 0',
          }} />

          {/* Backend Status Button */}
          <BackendIndicator 
            url={API_BASE_URL} 
            onStatusChange={handleSystemStatus}
            compact={true}
          />
          
          {/* Help Button */}
          <HelpButton />
        </div>

        <div
          ref={mainShellRef}
          style={{
            ...styles.mainShell,
            width: `${chatWidth}px`,
            maxWidth: `${chatWidth}px`,
            minWidth: "900px",
          }}
        >
          {/* App Header */}
          <div style={styles.appHeader}>
            <div style={styles.appHeaderIdentity}>
              <div style={styles.appTitleBlock}>
                <h1 style={styles.appTitle}>🎙️ ARTAgent</h1>
                <p style={styles.appSubtitle}>Transforming customer interactions with real-time, intelligent voice experiences.</p>
              </div>
            </div>

            <div style={{ ...styles.appHeaderFooter, alignItems: "center", gap: "16px" }}>
              <div
                style={{
                  ...styles.sessionTag,
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  cursor: "pointer",
                  position: "relative",
                }}
                onClick={() => {
                  if (!editingSessionId) {
                    setPendingSessionId(sessionId);
                    setEditingSessionId(true);
                    setSessionUpdateError(null);
                  }
                }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    if (!editingSessionId) {
                      setPendingSessionId(sessionId);
                      setEditingSessionId(true);
                      setSessionUpdateError(null);
                    }
                  }
                }}
              >
                <span style={styles.sessionTagIcon}>💬</span>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <div style={styles.sessionTagLabel}>Active Session</div>
                    <span style={{
                      padding: "2px 8px",
                      borderRadius: "4px",
                      background: getSessionScenario()?.startsWith('custom_')
                        ? "rgba(245,158,11,0.1)"
                        : getSessionScenario() === 'banking' 
                          ? "rgba(99,102,241,0.1)" 
                          : "rgba(14,165,233,0.1)",
                      color: getSessionScenario()?.startsWith('custom_')
                        ? "#f59e0b"
                        : getSessionScenario() === 'banking' 
                          ? "#6366f1" 
                          : "#0ea5e9",
                      fontSize: "10px",
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                    }}>
                      {getSessionScenario()?.startsWith('custom_') ? getSessionScenario().replace('custom_', '') : getSessionScenario()}
                    </span>
                  </div>
                  <code style={styles.sessionTagValue}>{sessionId}</code>
                  {sessionUpdateError && !editingSessionId && (
                    <div style={{ color: "#dc2626", fontSize: "12px" }}>
                      {sessionUpdateError}
                    </div>
                  )}
                </div>
                {editingSessionId && (
                  <div
                    style={{
                      position: "absolute",
                      top: "calc(100% + 6px)",
                      left: 0,
                      background: "#fff",
                      padding: "10px",
                      borderRadius: "12px",
                      boxShadow: "0 10px 30px rgba(0,0,0,0.12)",
                      minWidth: "260px",
                      zIndex: 10,
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      <input
                        value={pendingSessionId}
                        onChange={(e) => setPendingSessionId(e.target.value)}
                        style={{
                          padding: "6px 10px",
                          borderRadius: "8px",
                          border: "1px solid #e2e8f0",
                          fontFamily: "monospace",
                          fontSize: "13px",
                          minWidth: "220px",
                        }}
                        placeholder="session_123..."
                        autoFocus
                      />
                      <Button
                        size="small"
                        variant="contained"
                        onClick={handleSessionIdSave}
                        disabled={sessionUpdating}
                        sx={{ textTransform: "none" }}
                      >
                        {sessionUpdating ? "Saving..." : "Save"}
                      </Button>
                      <Button
                        size="small"
                        variant="text"
                        onClick={handleSessionIdCancel}
                        disabled={sessionUpdating}
                        sx={{ textTransform: "none" }}
                      >
                        Cancel
                      </Button>
                    </div>
                    {sessionUpdateError && (
                      <div style={{ color: "#dc2626", fontSize: "12px", marginTop: "6px" }}>
                        {sessionUpdateError}
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div style={styles.appHeaderActions}>
                {hasActiveProfile ? (
                  <ProfileButton
                    profile={activeSessionProfile}
                    highlight={profileHighlight}
                    onCreateProfile={openDemoForm}
                    onTogglePanel={() => setShowProfilePanel((prev) => !prev)}
                  />
                ) : (
                  <Button
                    variant="contained"
                    disableElevation
                    startIcon={<BoltRoundedIcon fontSize="small" />}
                    onMouseEnter={() => setCreateProfileHovered(true)}
                    onMouseLeave={() => setCreateProfileHovered(false)}
                    onClick={openDemoForm}
                    sx={{
                      ...styles.createProfileButton,
                      ...(createProfileHovered ? styles.createProfileButtonHover : {}),
                    }}
                  >
                    Create Demo Profile
                  </Button>
                )}
              </div>
            </div>
          </div>

            {/* Waveform Section */}
            <div style={styles.waveformSection}>
              <WaveformVisualization 
                activeSpeaker={activeSpeaker} 
                audioLevelRef={audioLevelRef}
                outputAudioLevelRef={outputAudioLevelRef}
              />
              <div style={styles.sectionDivider}></div>
            </div>

            <div style={styles.mainViewRow}>
              <div style={styles.viewContent}>
                {mainView === "chat" && (
                  <div style={styles.chatSection} ref={chatRef}>
                    <div style={styles.chatSectionIndicator}></div>
                    <div style={styles.messageContainer} ref={messageContainerRef}>
                      {messages.map((message, index) => (
                        <ChatBubble
                          key={index}
                          message={message}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {mainView === "graph" && (
                  <div style={styles.graphFullWrapper}>
                    <GraphCanvas events={graphEvents} currentAgent={currentAgentRef.current} isFull />
                  </div>
                )}

                {mainView === "timeline" && (
                  <div style={{ ...styles.graphFullWrapper, minHeight: "420px" }}>
                    <GraphListView events={graphEvents} compact={false} fillHeight />
                  </div>
                )}
              </div>
            </div>

            {/* Text Input - Shows above controls when recording */}
            {recording && (
              <div style={styles.textInputContainer}>
                <input
                  type="text"
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && textInput.trim()) handleSendText();
                  }}
                  placeholder="Type your message here..."
                  style={styles.textInput}
                />
                <IconButton 
                  onClick={handleSendText} 
                  disabled={!textInput.trim()}
                  disableRipple
                  sx={{
                    width: "48px",
                    height: "48px",
                    minWidth: "48px",
                    borderRadius: "50%",
                    padding: 0,
                    background: textInput.trim() 
                      ? "linear-gradient(135deg, #10b981, #059669)" 
                      : "linear-gradient(135deg, #f1f5f9, #e2e8f0)",
                    color: textInput.trim() ? "white" : "#cbd5e1",
                    border: textInput.trim() ? "none" : "1px solid #e2e8f0",
                    boxShadow: textInput.trim() 
                      ? "0 4px 14px rgba(16,185,129,0.3), inset 0 1px 2px rgba(255,255,255,0.2)" 
                      : "0 2px 6px rgba(0,0,0,0.06)",
                    transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
                    cursor: textInput.trim() ? "pointer" : "not-allowed",
                    '&:hover': textInput.trim() ? {
                      background: "linear-gradient(135deg, #059669, #047857)",
                      transform: "scale(1.08) translateY(-1px)",
                      boxShadow: "0 8px 20px rgba(16,185,129,0.4), 0 0 0 3px rgba(16,185,129,0.15), inset 0 1px 2px rgba(255,255,255,0.2)",
                    } : {},
                    '&:active': textInput.trim() ? {
                      transform: "scale(1.02) translateY(0px)",
                      boxShadow: "0 2px 8px rgba(16,185,129,0.3)",
                    } : {},
                    '& svg': {
                      fontSize: '20px',
                      transform: 'translateX(1px)',
                    },
                  }}
                >
                  <SendRoundedIcon />
                </IconButton>
              </div>
            )}

            {/* Control Buttons - Clean 3-button layout */}
            <ConversationControls
              recording={recording}
              callActive={callActive}
              isCallDisabled={isCallDisabled}
              onResetSession={handleResetSession}
              onMicToggle={handleMicToggle}
              micMuted={micMuted}
              onMuteToggle={handleMuteToggle}
              onPhoneButtonClick={handlePhoneButtonClick}
              phoneButtonRef={phoneButtonRef}
              micButtonRef={micButtonRef}
              mainView={mainView}
              onMainViewChange={setMainView}
            />
            {/* Resize handle for chat width */}
            <div
              style={{
                position: "absolute",
                top: "0",
                right: "-6px",
                width: "12px",
                height: "100%",
                cursor: "ew-resize",
                zIndex: 5,
              }}
              onMouseDown={(e) => {
                resizeStartXRef.current = e.clientX;
                chatWidthRef.current = chatWidth;
                setIsResizingChat(true);
              }}
            />

            <div style={styles.realtimeModeDock} ref={realtimePanelAnchorRef} />

        {/* Phone Input Panel */}
      {showPhoneInput && (
        <div ref={phonePanelRef} style={styles.phoneInputSection}>
          <div style={{ marginBottom: '8px', fontSize: '12px', color: '#64748b' }}>
            {callActive ? '📞 Call in progress' : '📞 Enter your phone number to get a call'}
          </div>
          <AcsStreamingModeSelector
            value={selectedStreamingMode}
            onChange={handleStreamingModeChange}
            disabled={callActive || isCallDisabled}
          />
          <div style={styles.phoneInputRow}>
            <input
              type="tel"
              value={targetPhoneNumber}
              onChange={(e) => setTargetPhoneNumber(e.target.value)}
              placeholder="+15551234567"
              style={styles.phoneInput}
              disabled={callActive || isCallDisabled}
            />
            <button
              onClick={callActive ? stopRecognition : startACSCall}
              style={styles.callMeButton(callActive, isCallDisabled)}
              title={
                callActive
                  ? "🔴 Hang up call"
                  : isCallDisabled
                    ? "Configure Azure Communication Services to enable calling"
                    : "📞 Start phone call"
              }
              disabled={callActive || isCallDisabled}
            >
              {callActive ? "🔴 Hang Up" : "📞 Call Me"}
            </button>
          </div>
        </div>
      )}
        {showRealtimeModePanel && typeof document !== 'undefined' &&
          createPortal(
            <div
              ref={realtimePanelRef}
              style={{
                ...styles.realtimeModePanel,
                top: realtimePanelCoords.top,
                left: realtimePanelCoords.left,
              }}
            >
              <RealtimeStreamingModeSelector
                value={selectedRealtimeStreamingMode}
                onChange={handleRealtimeStreamingModeChange}
                disabled={recording}
              />
            </div>,
            document.body,
          )}
        {showDemoForm && typeof document !== 'undefined' &&
          createPortal(
            <>
              <div style={styles.demoFormBackdrop} onClick={closeDemoForm} />
              <div className="demo-form-overlay" style={styles.demoFormOverlay}>
                <TemporaryUserForm
                  apiBaseUrl={API_BASE_URL}
                  onClose={closeDemoForm}
                  sessionId={sessionId}
                  onSuccess={handleDemoCreated}
                />
              </div>
            </>,
            document.body
          )
        }
      </div>
      {showAgentsPanel && (
        <AgentTopologyPanel
          inventory={agentInventory}
          activeAgent={selectedAgentName}
          onClose={() => setShowAgentsPanel(false)}
        />
      )}
    </div>
    <ProfileDetailsPanel
      profile={activeSessionProfile}
      sessionId={sessionId}
      open={showProfilePanel}
      onClose={() => setShowProfilePanel(false)}
    />
    <AgentDetailsPanel
      open={showAgentPanel}
      onClose={() => setShowAgentPanel(false)}
      agentName={resolvedAgentName}
      agentDescription={activeAgentInfo?.description}
      sessionId={sessionId}
      sessionAgentConfig={sessionAgentConfig}
      lastUserMessage={lastUserMessage}
      lastAssistantMessage={lastAssistantMessage}
      recentTools={recentTools}
      messages={messages}
      agentTools={resolvedAgentTools}
      handoffTools={resolvedHandoffTools}
    />
    <AgentBuilder
      open={showAgentBuilder}
      onClose={() => setShowAgentBuilder(false)}
      sessionId={sessionId}
      sessionProfile={activeSessionProfile}
      onAgentCreated={(agentConfig) => {
        appendLog(`✨ Dynamic agent created: ${agentConfig.name}`);
        appendSystemMessage(`🤖 Agent "${agentConfig.name}" is now active`, {
          tone: "success",
          statusCaption: `Tools: ${agentConfig.tools?.length || 0} · Voice: ${agentConfig.voice?.name || 'default'}`,
          statusLabel: "Agent Active",
        });
        // Set the created agent as the active agent
        setSelectedAgentName(agentConfig.name);
        fetchSessionAgentConfig();
        // Refresh agent inventory to include the new session agent
        setAgentInventory((prev) => {
          if (!prev) return prev;
          const existing = prev.agents?.find((a) => a.name === agentConfig.name);
          if (existing) {
            // Update existing agent
            return {
              ...prev,
              agents: prev.agents.map((a) => 
                a.name === agentConfig.name
                  ? {
                      ...a,
                      description: agentConfig.description,
                      tools: agentConfig.tools || [],
                      toolCount: agentConfig.tools?.length || 0,
                      model: agentConfig.model?.deployment_id || null,
                      voice: agentConfig.voice?.name || null,
                    }
                  : a
              ),
            };
          }
          return {
            ...prev,
            agents: [
              ...(prev.agents || []),
              {
                name: agentConfig.name,
                description: agentConfig.description,
                tools: agentConfig.tools || [],
                toolCount: agentConfig.tools?.length || 0,
                model: agentConfig.model?.deployment_id || null,
                voice: agentConfig.voice?.name || null,
                templateId: agentConfig.name ? agentConfig.name.toLowerCase().replace(/\s+/g, "_") : null,
              },
            ],
          };
        });
        setShowAgentBuilder(false);
      }}
      onAgentUpdated={(agentConfig) => {
        appendLog(`✏️ Dynamic agent updated: ${agentConfig.name}`);
        appendSystemMessage(`🤖 Agent "${agentConfig.name}" updated`, {
          tone: "success",
          statusCaption: `Tools: ${agentConfig.tools?.length || 0} · Voice: ${agentConfig.voice?.name || 'default'}`,
          statusLabel: "Agent Updated",
        });
        // Update the agent in inventory
        setAgentInventory((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            agents: prev.agents.map((a) => 
              a.name === agentConfig.name
                ? {
                    ...a,
                    description: agentConfig.description,
                    tools: agentConfig.tools || [],
                    toolCount: agentConfig.tools?.length || 0,
                    model: agentConfig.model?.deployment_id || null,
                    voice: agentConfig.voice?.name || null,
                    templateId: agentConfig.name
                      ? agentConfig.name.toLowerCase().replace(/\s+/g, "_")
                      : a.templateId,
                  }
                : a
            ),
          };
        });
        // Don't close the dialog on update - user may want to continue editing
      }}
    />
    <AgentScenarioBuilder
      open={showAgentScenarioBuilder}
      onClose={() => setShowAgentScenarioBuilder(false)}
      initialMode={builderInitialMode}
      sessionId={sessionId}
      sessionProfile={activeSessionProfile}
      scenarioEditMode={sessionScenarioConfig?.scenarios?.length > 0}
      existingScenarioConfig={
        sessionScenarioConfig?.scenarios?.find(s => s.is_active) || 
        sessionScenarioConfig?.scenarios?.[0] || 
        null
      }
      onAgentCreated={(agentConfig) => {
        appendLog(`✨ Dynamic agent created: ${agentConfig.name}`);
        appendSystemMessage(`🤖 Agent "${agentConfig.name}" is now active`, {
          tone: "success",
          statusCaption: `Tools: ${agentConfig.tools?.length || 0} · Voice: ${agentConfig.voice?.name || 'default'}`,
          statusLabel: "Agent Active",
        });
        setSelectedAgentName(agentConfig.name);
        fetchSessionAgentConfig();
        setAgentInventory((prev) => {
          if (!prev) return prev;
          const existing = prev.agents?.find((a) => a.name === agentConfig.name);
          if (existing) {
            return {
              ...prev,
              agents: prev.agents.map((a) => 
                a.name === agentConfig.name
                  ? {
                      ...a,
                      description: agentConfig.description,
                      tools: agentConfig.tools || [],
                      toolCount: agentConfig.tools?.length || 0,
                      model: agentConfig.model?.deployment_id || null,
                      voice: agentConfig.voice?.name || null,
                    }
                  : a
              ),
            };
          }
          return {
            ...prev,
            agents: [
              ...(prev.agents || []),
              {
                name: agentConfig.name,
                description: agentConfig.description,
                tools: agentConfig.tools || [],
                toolCount: agentConfig.tools?.length || 0,
                model: agentConfig.model?.deployment_id || null,
                voice: agentConfig.voice?.name || null,
                templateId: agentConfig.name ? agentConfig.name.toLowerCase().replace(/\s+/g, "_") : null,
              },
            ],
          };
        });
      }}
      onAgentUpdated={(agentConfig) => {
        appendLog(`✏️ Dynamic agent updated: ${agentConfig.name}`);
        appendSystemMessage(`🤖 Agent "${agentConfig.name}" updated`, {
          tone: "success",
          statusCaption: `Tools: ${agentConfig.tools?.length || 0} · Voice: ${agentConfig.voice?.name || 'default'}`,
          statusLabel: "Agent Updated",
        });
        setAgentInventory((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            agents: prev.agents.map((a) => 
              a.name === agentConfig.name
                ? {
                    ...a,
                    description: agentConfig.description,
                    tools: agentConfig.tools || [],
                    toolCount: agentConfig.tools?.length || 0,
                    model: agentConfig.model?.deployment_id || null,
                    voice: agentConfig.voice?.name || null,
                    templateId: agentConfig.name
                      ? agentConfig.name.toLowerCase().replace(/\s+/g, "_")
                      : a.templateId,
                  }
                : a
            ),
          };
        });
      }}
      onScenarioCreated={(scenarioConfig) => {
        appendLog(`🎭 Scenario created: ${scenarioConfig.name || 'Custom Scenario'}`);
        appendSystemMessage(`🎭 Scenario "${scenarioConfig.name || 'Custom'}" is now active`, {
          tone: "success",
          statusCaption: `Agents: ${scenarioConfig.agents?.length || 0} · Handoffs: ${scenarioConfig.handoffs?.length || 0}`,
          statusLabel: "Scenario Active",
        });
        // Refresh scenario configuration and set to custom scenario
        fetchSessionScenarioConfig();
        setSessionScenario('custom');
      }}
      onScenarioUpdated={(scenarioConfig) => {
        appendLog(`✏️ Scenario updated: ${scenarioConfig.name || 'Custom Scenario'}`);
        appendSystemMessage(`🎭 Scenario "${scenarioConfig.name || 'Custom'}" updated`, {
          tone: "success",
          statusCaption: `Agents: ${scenarioConfig.agents?.length || 0} · Handoffs: ${scenarioConfig.handoffs?.length || 0}`,
          statusLabel: "Scenario Updated",
        });
        fetchSessionScenarioConfig();
        // Keep the scenario set to custom if updating
        if (!getSessionScenario()?.startsWith('custom_')) {
          setSessionScenario('custom');
        }
      }}
    />
  </div>
);
}

// Main App component wrapper
function App() {
  return <RealTimeVoiceApp />;
}

export default App;
