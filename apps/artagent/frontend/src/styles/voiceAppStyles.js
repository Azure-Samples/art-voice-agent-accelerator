export const styles = {
  root: {
    width: "100%",
    maxWidth: "1040px",
    fontFamily: "Segoe UI, Roboto, sans-serif",
    background: "transparent",
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    color: "#1e293b",
    position: "relative",
    alignItems: "center",
    justifyContent: "center",
    padding: "8px",
    border: "0px solid #0e4bf3ff",
  },
  
  mainContainer: {
    position: "relative",
    width: "100%",
    maxWidth: "1040px",
    height: "calc(100vh - 32px)",
    minHeight: "calc(100vh - 32px)",
    maxHeight: "calc(100vh - 32px)",
    display: "flex",
    flexDirection: "column",
    alignItems: "stretch",
    justifyContent: "flex-start",
    paddingTop: "18px",
  },

  mainShell: {
    position: "relative",
    flex: 1,
    background: "white",
    borderRadius: "20px",
    boxShadow: "0 12px 32px rgba(15,23,42,0.12)",
    border: "0px solid transparent",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },

  helpButtonDock: {
    position: "fixed",
    top: "20px",
    left: "24px",
    display: "flex",
    alignItems: "center",
    gap: "12px",
    zIndex: 120,
  },
  backendIndicatorDock: {
    position: "fixed",
    bottom: "20px",
    left: "20px",
    transform: "scale(0.94)",
    transformOrigin: "bottom left",
    boxShadow: "0 6px 18px rgba(15,23,42,0.18)",
    zIndex: 7,
    display: "flex",
    alignItems: "center",
    gap: "10px",
  },

  appHeader: {
    position: "relative",
    backgroundColor: "#f8fafc",
    background: "linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)",
    padding: "20px 24px 18px 24px",
    borderBottom: "1px solid #e2e8f0",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "18px",
    minHeight: "96px",
  },

  appHeaderIdentity: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "8px",
    padding: "16px 24px",
    borderRadius: "22px",
    background: "linear-gradient(140deg, rgba(255,255,255,0.97), rgba(248,250,252,0.92))",
    border: "1px solid rgba(148,163,184,0.18)",
    boxShadow: "0 8px 20px rgba(15,23,42,0.08)",
    width: "100%",
    maxWidth: "420px",
  },

  appTitleBlock: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    minWidth: 0,
    alignItems: "center",
    textAlign: "center",
  },

  appTitle: {
    fontSize: "16px",
    fontWeight: "800",
    color: "#0f172a",
    margin: 0,
    letterSpacing: "-0.02em",
    // textTransform: "uppercase",
  },

  appSubtitle: {
    fontSize: "11px",
    color: "#475569",
    margin: 0,
    maxWidth: "320px",
    lineHeight: "1.35",
  },

  appHeaderFooter: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "16px",
    flexWrap: "wrap",
    width: "100%",
    maxWidth: "520px",
    margin: "0 auto",
  },

  sessionTag: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    padding: "7px 14px",
    borderRadius: "999px",
    background: "rgba(248,250,252,0.9)",
    border: "1px solid rgba(148,163,184,0.28)",
    fontSize: "10px",
    color: "#1f2937",
    whiteSpace: "nowrap",
    boxShadow: "none",
    flexShrink: 0,
  },
  appHeaderActions: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    flexWrap: "wrap",
  },
  waveformSection: {
    position: "relative",
    background: "linear-gradient(180deg, rgba(248,250,252,0.95) 0%, rgba(241,245,249,1) 100%)",
    borderBottom: "1px solid rgba(148,163,184,0.18)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "6px",
    overflow: "visible",
    boxShadow: "inset 0 -10px 20px rgba(15,23,42,0.04)",
  },
  waveformSectionCollapsed: {
    padding: "10px 22px 12px 22px",
    minHeight: "0",
    alignItems: "flex-start",
    justifyContent: "flex-start",
    gap: "6px",
  },
  waveformHeader: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  waveformHint: {
    fontSize: "11px",
    color: "#94a3b8",
    fontWeight: 500,
    letterSpacing: "0.1px",
  },
  waveformCollapsedLine: {
    width: "100%",
    height: "2px",
    borderRadius: "999px",
    background: "linear-gradient(90deg, rgba(148,163,184,0.05), rgba(148,163,184,0.35), rgba(148,163,184,0.05))",
  },
  
  // Section divider line - more subtle
  sectionDivider: {
    position: "absolute",
    bottom: 0,
    left: "24px",
    right: "24px",
    height: "1px",
    backgroundColor: "rgba(148,163,184,0.35)",
    borderRadius: "999px",
    opacity: 0.7,
    pointerEvents: "none",
    zIndex: 0,
  },
  
  waveformContainer: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
    height: "96px",
    padding: "2px 16px 0",
    background: "radial-gradient(ellipse at center, rgba(100, 116, 139, 0.08) 0%, transparent 70%)",
    borderRadius: "0px",
    overflow: "visible",
  },
  
  waveformSvg: {
    width: "100%",
    height: "86px",
    filter: "drop-shadow(0 2px 6px rgba(100, 116, 139, 0.15))",
    transition: "filter 0.3s ease",
  },
  
  chatSection: {
    flex: 1,
    width: "100%",
    overflowY: "auto",
    overflowX: "hidden",
    backgroundColor: "#ffffff",
    borderTop: "1px solid rgba(148,163,184,0.14)",
    borderBottom: "1px solid rgba(148,163,184,0.12)",
    display: "flex",
    flexDirection: "column",
    position: "relative",
    alignItems: "stretch",
  },
  
  chatSectionHeader: {
    textAlign: "center",
    marginBottom: "30px",
    paddingBottom: "20px",
    borderBottom: "1px solid #f1f5f9",
  },
  
  chatSectionTitle: {
    fontSize: "14px",
    fontWeight: "600",
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
    marginBottom: "5px",
  },
  
  chatSectionSubtitle: {
    fontSize: "12px",
    color: "#94a3b8",
    fontStyle: "italic",
  },

  graphContainer: {
    width: "100%",
    maxWidth: "100%",
    margin: "0 auto",
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: "16px",
    boxShadow: "0 6px 18px rgba(15,23,42,0.06)",
    padding: "12px 16px",
    overflowX: "hidden",
  },
  graphHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "12px",
    marginBottom: "8px",
  },
  graphTitle: {
    fontSize: "13px",
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "#0f172a",
  },
  graphSubtitle: {
    fontSize: "11px",
    color: "#64748b",
  },
  graphAgentsRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: "8px",
    marginBottom: "10px",
  },
  graphAgentChip: {
    padding: "6px 10px",
    borderRadius: "999px",
    background: "rgba(226,232,240,0.8)",
    border: "1px solid rgba(148,163,184,0.4)",
    fontSize: "11px",
    fontWeight: 700,
    color: "#0f172a",
    letterSpacing: "0.04em",
  },
  graphEventsList: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    width: "100%",
  },
  graphEventRow: {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-start",
    gap: "10px",
    padding: "8px 10px",
    background: "white",
    borderRadius: "12px",
    border: "1px solid rgba(226,232,240,0.8)",
    boxShadow: "0 4px 12px rgba(15,23,42,0.04)",
    width: "100%",
    boxSizing: "border-box",
  },
  graphEventMeta: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    minWidth: "82px",
  },
  graphBadge: (variant = "message") => {
    const palettes = {
      message: { bg: "rgba(59,130,246,0.12)", color: "#1e3a8a", border: "rgba(59,130,246,0.25)" },
      tool: { bg: "rgba(16,185,129,0.12)", color: "#065f46", border: "rgba(16,185,129,0.28)" },
      switch: { bg: "rgba(234,179,8,0.14)", color: "#854d0e", border: "rgba(234,179,8,0.32)" },
      event: { bg: "rgba(100,116,139,0.14)", color: "#111827", border: "rgba(148,163,184,0.4)" },
      function: { bg: "rgba(94,234,212,0.14)", color: "#0f766e", border: "rgba(94,234,212,0.4)" },
    };
    const palette = palettes[variant] || palettes.message;
    return {
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "4px 10px",
      borderRadius: "999px",
      background: palette.bg,
      color: palette.color,
      border: `1px solid ${palette.border}`,
      fontSize: "11px",
      fontWeight: 700,
      letterSpacing: "0.04em",
      textTransform: "uppercase",
      whiteSpace: "nowrap",
    };
  },
  graphTimestamp: {
    fontSize: "11px",
    color: "#94a3b8",
    fontFamily: 'Roboto Mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
  },
  graphFlow: {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: "6px",
    color: "#0f172a",
    fontWeight: 700,
    letterSpacing: "0.02em",
  },
  graphNode: (variant = "default") => {
    const palette = {
      default: { bg: "rgba(226,232,240,0.8)", color: "#0f172a", border: "rgba(148,163,184,0.4)" },
      target: { bg: "rgba(103,216,239,0.18)", color: "#0b4f6c", border: "rgba(103,216,239,0.35)" },
    }[variant] || { bg: "rgba(226,232,240,0.8)", color: "#0f172a", border: "rgba(148,163,184,0.4)" };
    return {
      padding: "4px 8px",
      borderRadius: "10px",
      background: palette.bg,
      color: palette.color,
      border: `1px solid ${palette.border}`,
      fontSize: "11px",
      fontWeight: 700,
      letterSpacing: "0.02em",
    };
  },
  graphText: {
    fontSize: "12px",
    color: "#475569",
    lineHeight: 1.45,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  graphFullWrapper: {
    width: "100%",
    maxWidth: "100%",
    padding: "0 0 4px",
    flex: 1,
    overflow: "auto",
  },
  viewSwitch: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  viewSwitchButton: (active) => ({
    padding: "10px 12px",
    borderRadius: "12px",
    border: active ? "1px solid rgba(59,130,246,0.6)" : "1px solid rgba(148,163,184,0.45)",
    background: active ? "linear-gradient(135deg, #dbeafe, #bfdbfe)" : "white",
    color: active ? "#1d4ed8" : "#475569",
    fontSize: "12px",
    fontWeight: 700,
    letterSpacing: "0.03em",
    cursor: active ? "default" : "pointer",
    boxShadow: active ? "0 8px 16px rgba(59,130,246,0.18)" : "none",
    transition: "all 0.15s ease",
    textAlign: "left",
  }),
  mainViewRow: {
    display: "flex",
    flexDirection: "column",
    gap: "0px",
    padding: "6px 0 0",
    width: "100%",
    flex: 1,
    minHeight: 0,
    boxSizing: "border-box",
  },
  viewContent: {
    flex: 1,
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
  },
  viewFloatingDock: {
    position: "absolute",
    right: "32px",
    bottom: "130px",
    transform: "none",
    background: "rgba(255,255,255,0.82)",
    border: "1px solid rgba(226,232,240,0.9)",
    borderRadius: "12px",
    padding: "6px",
    boxShadow: "0 10px 26px rgba(15,23,42,0.15)",
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    zIndex: 48,
    backdropFilter: "blur(10px)",
  },
  viewInlineSwitch: {
    position: "absolute",
    right: "18px",
    top: "50%",
    transform: "translateY(-50%)",
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    padding: "4px 6px",
    background: "rgba(255,255,255,0.85)",
    border: "1px solid rgba(226,232,240,0.8)",
    borderRadius: "14px",
    boxShadow: "0 4px 12px rgba(15,23,42,0.08)",
  },
  viewInlineButton: (active) => ({
    padding: "6px 10px",
    borderRadius: "10px",
    border: active ? "1px solid rgba(59,130,246,0.55)" : "1px solid rgba(148,163,184,0.45)",
    background: active ? "linear-gradient(135deg, #dbeafe, #bfdbfe)" : "rgba(255,255,255,0.95)",
    color: active ? "#1d4ed8" : "#475569",
    fontSize: "12px",
    fontWeight: 700,
    letterSpacing: "0.02em",
    cursor: active ? "default" : "pointer",
    boxShadow: active ? "0 6px 12px rgba(59,130,246,0.18)" : "none",
    transition: "all 0.12s ease",
  }),
  graphDock: {
    position: "fixed",
    left: "max(8px, calc(50% - 480px))",
    top: "140px",
    zIndex: 40,
    width: "280px",
    pointerEvents: "auto",
  },
  graphCollapsedCard: {
    padding: "10px 12px",
    borderRadius: "12px",
    border: "1px solid rgba(148,163,184,0.4)",
    background: "rgba(255,255,255,0.96)",
    boxShadow: "0 12px 24px rgba(15,23,42,0.12)",
    cursor: "pointer",
    display: "flex",
    alignItems: "flex-start",
    gap: "10px",
    position: "relative",
  },
  graphCollapsedBadge: {
    padding: "4px 8px",
    borderRadius: "999px",
    background: "rgba(59,130,246,0.12)",
    color: "#1d4ed8",
    fontSize: "11px",
    fontWeight: 700,
    border: "1px solid rgba(59,130,246,0.25)",
    letterSpacing: "0.04em",
  },
  graphCollapsedText: {
    fontSize: "12px",
    color: "#0f172a",
    lineHeight: 1.4,
  },
  graphPanel: {
    background: "rgba(255,255,255,0.98)",
    borderRadius: "16px",
    border: "1px solid rgba(148,163,184,0.35)",
    boxShadow: "0 20px 40px rgba(15,23,42,0.16)",
    overflow: "hidden",
  },
  graphPanelHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 14px",
    borderBottom: "1px solid rgba(226,232,240,0.9)",
    background: "linear-gradient(135deg, #f8fafc, #edf2f7)",
  },
  graphPanelTitle: {
    fontSize: "12px",
    fontWeight: 800,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "#0f172a",
  },
  graphPanelTabs: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  graphTab: (active) => ({
    padding: "6px 10px",
    borderRadius: "10px",
    border: `1px solid ${active ? "rgba(59,130,246,0.6)" : "rgba(148,163,184,0.4)"}`,
    background: active ? "rgba(59,130,246,0.12)" : "rgba(255,255,255,0.85)",
    color: active ? "#1d4ed8" : "#475569",
    fontSize: "11px",
    fontWeight: 700,
    letterSpacing: "0.04em",
    cursor: active ? "default" : "pointer",
  }),
  graphPanelBody: {
    maxHeight: "70vh",
    overflowY: "auto",
    padding: "10px 12px 12px",
  },
  graphCanvasWrapper: {
    border: "1px solid rgba(226,232,240,0.9)",
    borderRadius: "12px",
    background: "linear-gradient(180deg, rgba(248,250,252,0.8), rgba(255,255,255,0.95))",
    padding: "10px",
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.8)",
  },
  
  // Chat section visual indicator
  chatSectionIndicator: {
    position: "absolute",
    left: "0",
    top: "0",
    bottom: "0",
    width: "0px",
    backgroundColor: "#3b82f6",
  },
  
  messageContainer: {
    display: "flex",
    flexDirection: "column",
    gap: "18px",
    flex: 1,
    overflowY: "auto",
    overflowX: "hidden",
    padding: "6px 12px 18px",
    alignItems: "stretch",
    width: "100%",
  },
  
  userMessage: {
    alignSelf: "flex-end",
    maxWidth: "78%",
    marginRight: "20px",
    marginBottom: "4px",
  },
  
  userBubble: {
    background: "#e0f2fe",
    color: "#0f172a",
    padding: "12px 16px",
    borderRadius: "20px",
    fontSize: "14px",
    lineHeight: "1.5",
    border: "1px solid #bae6fd",
    boxShadow: "0 2px 8px rgba(14,165,233,0.15)",
    wordWrap: "break-word",
    overflowWrap: "break-word",
    hyphens: "auto",
    whiteSpace: "pre-wrap",
  },
  
  // Assistant message (left aligned - teal bubble)
  assistantMessage: {
    alignSelf: "flex-start",
    maxWidth: "82%", // Increased width for maximum space usage
    marginLeft: "4px", // No left margin - flush to edge
    marginBottom: "4px",
  },
  
  assistantBubble: {
    background: "#67d8ef",
    color: "white",
    padding: "12px 16px",
    borderRadius: "20px",
    fontSize: "14px",
    lineHeight: "1.5",
    boxShadow: "0 2px 8px rgba(103,216,239,0.3)",
    wordWrap: "break-word",
    overflowWrap: "break-word",
    hyphens: "auto",
    whiteSpace: "pre-wrap",
  },

  // Agent name label (appears above specialist bubbles)
  agentNameLabel: {
    fontSize: "10px",
    fontWeight: "400",
    color: "#64748b",
    opacity: 0.7,
    marginBottom: "2px",
    marginLeft: "8px",
    letterSpacing: "0.5px",
    textTransform: "none",
    fontStyle: "italic",
  },
  
  // Control section - blended footer design
  controlSection: {
    padding: "10px 16px 14px",
    background: "#f5f7fb",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    borderTop: "1px solid #e2e8f0",
    position: "relative",
  },
  
  controlContainer: {
    display: "flex",
    gap: "10px",
    background: "rgba(255,255,255,0.9)",
    padding: "10px 14px",
    borderRadius: "18px",
    boxShadow: "0 4px 14px rgba(15,23,42,0.12)",
    border: "1px solid rgba(226,232,240,0.9)",
    width: "fit-content",
  },
  
  // Enhanced button styles with hover effects
  resetButton: (isHovered) => ({
    width: "56px",
    height: "56px",
    borderRadius: "50%",
    border: '1px solid rgba(226,232,240,0.6)',
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    fontSize: "20px",
    transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
    position: "relative",
    background: 'linear-gradient(145deg, #ffffff, #fafbfc)',
    color: '#64748b',
    transform: isHovered ? 'translateY(-2px)' : 'translateY(0)',
    boxShadow: isHovered ? 
      '0 4px 16px rgba(100,116,139,0.15), inset 0 1px 0 rgba(255,255,255,0.8)' :
      '0 2px 8px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)',
    padding: 0,
    '& svg': {
      color: isHovered ? '#475569' : '#64748b',
    },
  }),

  micButton: (isActive, isHovered) => ({
    width: "56px",
    height: "56px",
    borderRadius: "50%",
    border: '1px solid rgba(226,232,240,0.6)',
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    fontSize: "20px",
    transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
    position: "relative",
    // RECORDING (active): Cyan accent gradient
    // IDLE: White base gradient
    background: isActive ? 
      (isHovered ? 'linear-gradient(135deg, rgba(14,165,233,0.15), rgba(14,165,233,0.1))' : 'linear-gradient(145deg, rgba(14,165,233,0.1), rgba(14,165,233,0.08))') :
      'linear-gradient(145deg, #ffffff, #fafbfc)',
    color: isActive ? '#0ea5e9' : '#64748b',
    transform: isHovered ? 'translateY(-2px)' : 'translateY(0)',
    // RECORDING: Subtle cyan glow
    // IDLE: Standard shadow
    boxShadow: isActive ? 
      (isHovered ? 
        '0 4px 16px rgba(14,165,233,0.2), inset 0 1px 0 rgba(255,255,255,0.8)' :
        '0 2px 8px rgba(14,165,233,0.15), inset 0 1px 0 rgba(255,255,255,0.8)') :
      (isHovered ? 
        '0 4px 16px rgba(15,23,42,0.12), inset 0 1px 0 rgba(255,255,255,0.8)' :
        '0 2px 8px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)'),
    padding: 0,
    animation: "none",
    '& svg': {
      color: isActive ? '#0ea5e9' : (isHovered ? '#475569' : '#64748b'),
    },
  }),

  muteButton: (isMuted, isHovered, isDisabled = false) => {
    const base = {
      width: "56px",
      height: "56px",
      borderRadius: "50%",
      border: '1px solid rgba(226,232,240,0.6)',
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
      position: "relative",
      padding: 0,
      '& svg': {
        color: '#64748b',
      },
    };

    if (isDisabled) {
      return {
        ...base,
        cursor: "not-allowed",
        background: 'linear-gradient(145deg, #f1f5f9, #e2e8f0)',
        opacity: 0.5,
        boxShadow: '0 2px 4px rgba(15,23,42,0.04)',
        '& svg': {
          color: "#94a3b8",
        },
      };
    }

    // MUTED: Subtle red accent on white base
    // UNMUTED: Subtle green accent on white base
    const palette = isMuted
      ? {
          base: 'linear-gradient(145deg, rgba(254,202,202,0.3), rgba(252,165,165,0.2))',
          hover: 'linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.1))',
          fg: '#ef4444',
          hoverFg: '#dc2626',
          shadow: '0 2px 8px rgba(239,68,68,0.15), inset 0 1px 0 rgba(255,255,255,0.8)',
          hoverShadow: '0 4px 16px rgba(239,68,68,0.2), inset 0 1px 0 rgba(255,255,255,0.8)',
        }
      : {
          base: 'linear-gradient(145deg, rgba(209,250,229,0.3), rgba(167,243,208,0.2))',
          hover: 'linear-gradient(135deg, rgba(16,185,129,0.15), rgba(16,185,129,0.1))',
          fg: '#10b981',
          hoverFg: '#059669',
          shadow: '0 2px 8px rgba(16,185,129,0.15), inset 0 1px 0 rgba(255,255,255,0.8)',
          hoverShadow: '0 4px 16px rgba(16,185,129,0.2), inset 0 1px 0 rgba(255,255,255,0.8)',
        };

    return {
      ...base,
      cursor: "pointer",
      background: isHovered ? palette.hover : palette.base,
      transform: isHovered ? 'translateY(-2px)' : 'translateY(0)',
      boxShadow: isHovered ? palette.hoverShadow : palette.shadow,
      '& svg': {
        color: isHovered ? palette.hoverFg : palette.fg,
      },
    };
  },

  phoneButton: (isActive, isHovered, isDisabled = false) => {
    const base = {
      width: "56px",
      height: "56px",
      borderRadius: "50%",
      border: '1px solid rgba(226,232,240,0.6)',
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "20px",
      transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
      position: "relative",
      padding: 0,
      '& svg': {
        color: '#64748b',
      },
    };

    if (isDisabled) {
      return {
        ...base,
        cursor: "not-allowed",
        background: 'linear-gradient(145deg, #f1f5f9, #e2e8f0)',
        color: "#94a3b8",
        transform: 'translateY(0)',
        boxShadow: '0 2px 4px rgba(15,23,42,0.04)',
        opacity: 0.5,
        '& svg': {
          color: "#94a3b8",
        },
      };
    }

    // ACTIVE (in call): Subtle red accent for "hang up"
    // INACTIVE: Subtle green accent for "start call"
    return {
      ...base,
      cursor: "pointer",
      background: isActive ? 
        (isHovered ? 'linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.1))' : 'linear-gradient(145deg, rgba(239,68,68,0.1), rgba(239,68,68,0.08))') :
        (isHovered ? 'linear-gradient(135deg, rgba(16,185,129,0.15), rgba(16,185,129,0.1))' : 'linear-gradient(145deg, rgba(16,185,129,0.1), rgba(16,185,129,0.08))'),
      color: isActive ? '#ef4444' : '#10b981',
      transform: isHovered ? 'translateY(-2px)' : 'translateY(0)',
      // ACTIVE: Subtle red glow for "danger/end call"
      // INACTIVE: Subtle green glow for "start call"
      boxShadow: isActive ? 
        (isHovered ? 
          '0 4px 16px rgba(239,68,68,0.2), inset 0 1px 0 rgba(255,255,255,0.8)' :
          '0 2px 8px rgba(239,68,68,0.15), inset 0 1px 0 rgba(255,255,255,0.8)') :
        (isHovered ? 
          '0 4px 16px rgba(16,185,129,0.2), inset 0 1px 0 rgba(255,255,255,0.8)' :
          '0 2px 8px rgba(16,185,129,0.15), inset 0 1px 0 rgba(255,255,255,0.8)'),
      '& svg': {
        color: isActive ? '#ef4444' : '#10b981',
      },
    };
  },

  keyboardButton: (isActive, isHovered) => ({
    width: "56px",
    height: "56px",
    borderRadius: "50%",
    border: "none",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    fontSize: "20px",
    transition: "all 0.3s ease",
    position: "relative",
    background: isHovered ? 
      (isActive ? "linear-gradient(135deg, #3b82f6, #2563eb)" : "linear-gradient(135deg, #dbeafe, #bfdbfe)") :
      "linear-gradient(135deg, #f1f5f9, #e2e8f0)",
    color: isHovered ? 
      (isActive ? "white" : "#0f172a") :
      (isActive ? "#2563eb" : "#1f2937"),
    transform: isHovered ? "scale(1.08)" : (isActive ? "scale(1.05)" : "scale(1)"),
    boxShadow: isHovered ? 
      "0 8px 25px rgba(59,130,246,0.4), 0 0 0 4px rgba(59,130,246,0.15), inset 0 1px 2px rgba(255,255,255,0.2)" :
      (isActive ? 
        "0 6px 20px rgba(37,99,235,0.3), 0 0 0 3px rgba(37,99,235,0.15)" : 
        "0 2px 8px rgba(0,0,0,0.08)"),
    padding: 0,
    '& svg': {
      color: isHovered ? (isActive ? "#f8fafc" : "#0f172a") : (isActive ? "#2563eb" : "#1f2937"),
    },
  }),

  // Tooltip styles
  buttonTooltip: {
    position: 'fixed',
    left: 0,
    top: 0,
    transform: 'translate(-50%, 0)',
    background: 'rgba(30, 41, 59, 0.92)',
    color: '#f1f5f9',
    padding: '8px 12px',
    borderRadius: '8px',
    fontSize: '11px',
    fontWeight: '500',
    whiteSpace: 'nowrap',
    boxShadow: '0 4px 10px rgba(15,23,42,0.18)',
    border: '1px solid rgba(255,255,255,0.08)',
    pointerEvents: 'none',
    opacity: 0,
    transition: 'opacity 0.18s ease, transform 0.18s ease',
    zIndex: 80,
  },

  buttonTooltipVisible: {
    opacity: 1,
    transform: 'translate(-50%, 0)',
  },

  realtimeModeDock: {
    width: '100%',
    padding: '0 24px',
    marginTop: '12px',
    position: 'relative',
    minHeight: '1px',
  },

  realtimeModePanel: {
    position: 'fixed',
    width: '100%',
    maxWidth: '360px',
    zIndex: 120,
  },

  textInputContainer: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "14px 24px 16px",
    backgroundColor: "rgba(255,255,255,0.98)",
    borderTop: "1px solid rgba(226,232,240,0.5)",
    width: "100%",
    boxSizing: "border-box",
    boxShadow: "0 -4px 12px rgba(15,23,42,0.04)",
    transition: "all 0.3s ease",
  },

  textInput: {
    flex: 1,
    padding: "12px 16px",
    borderRadius: "22px",
    border: "1px solid #e2e8f0",
    fontSize: "14px",
    outline: "none",
    transition: "all 0.2s ease",
    backgroundColor: "#f8fafc",
    color: "#1e293b",
    fontFamily: "inherit",
  },
  
  // Input section for phone calls
  phoneInputSection: {
    position: "absolute",
    bottom: "120px",
    right: "32px",
    padding: "16px",
    borderRadius: "18px",
    background: "rgba(255,255,255,0.96)",
    border: "1px solid rgba(226,232,240,0.9)",
    boxShadow: "0 20px 30px rgba(15,23,42,0.18)",
    fontSize: "12px",
    flexDirection: "column",
    gap: "12px",
    minWidth: "280px",
    maxWidth: "320px",
    zIndex: 90,
  },
  
  phoneInputRow: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    width: "100%",
  },
  
  phoneInput: {
    flex: 1,
    padding: "10px 12px",
    border: "1px solid #d1d5db",
    borderRadius: "12px",
    fontSize: "14px",
    outline: "none",
    transition: "border-color 0.2s ease, box-shadow 0.2s ease",
  },
  

  // Backend status indicator - enhanced for component health - relocated to bottom left
  backendIndicator: {
    position: "fixed",
    bottom: "20px",
    left: "20px",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    padding: "12px 16px",
    backgroundColor: "rgba(255, 255, 255, 0.98)",
    border: "1px solid #e2e8f0",
    borderRadius: "12px",
    fontSize: "11px",
    color: "#64748b",
    boxShadow: "0 6px 18px rgba(15,23,42,0.16)",
    zIndex: 60,
    minWidth: "280px",
    maxWidth: "320px",
  },

  maskToggleButton: {
    fontSize: "9px",
    padding: "4px 8px",
    borderRadius: "6px",
    border: "1px solid rgba(59,130,246,0.4)",
    background: "rgba(59,130,246,0.08)",
    color: "#2563eb",
    fontWeight: 600,
    cursor: "pointer",
    transition: "all 0.2s ease",
  },

  maskToggleButtonActive: {
    background: "rgba(59,130,246,0.16)",
    color: "#1d4ed8",
    borderColor: "rgba(37,99,235,0.5)",
  },

  backendHeader: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginBottom: "4px",
    cursor: "pointer",
  },

  backendStatus: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    backgroundColor: "#10b981",
    animation: "pulse 2s ease-in-out infinite",
    flexShrink: 0,
  },

  backendUrl: {
    fontFamily: "monospace",
    fontSize: "10px",
    color: "#475569",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },

  backendLabel: {
    fontWeight: "600",
    color: "#334155",
    fontSize: "12px",
    letterSpacing: "0.3px",
  },

  expandIcon: {
    marginLeft: "auto",
    fontSize: "12px",
    color: "#94a3b8",
    transition: "transform 0.2s ease",
  },

  componentGrid: {
    display: "grid",
    gridTemplateColumns: "1fr",
    gap: "6px", // Reduced from 12px to half
    marginTop: "6px", // Reduced from 12px to half
    paddingTop: "6px", // Reduced from 12px to half
    borderTop: "1px solid #f1f5f9",
  },

  componentItem: {
    display: "flex",
    alignItems: "center",
    gap: "4px", // Reduced from 8px to half
    padding: "5px 7px", // Reduced from 10px 14px to half
    backgroundColor: "#f8fafc",
    borderRadius: "5px", // Reduced from 10px to half
    fontSize: "9px", // Reduced from 11px
    border: "1px solid #e2e8f0",
    transition: "all 0.2s ease",
    minHeight: "22px", // Reduced from 45px to half
  },

  componentDot: (status) => ({
    width: "4px", // Reduced from 8px to half
    height: "4px", // Reduced from 8px to half
    borderRadius: "50%",
    backgroundColor: status === "healthy" ? "#10b981" : 
                     status === "degraded" ? "#f59e0b" : 
                     status === "unhealthy" ? "#ef4444" : "#6b7280",
    flexShrink: 0,
  }),

  componentName: {
    fontWeight: "500",
    color: "#475569",
    textTransform: "capitalize",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    fontSize: "9px", // Reduced from 11px
    letterSpacing: "0.01em", // Reduced letter spacing
  },

  responseTime: {
    fontSize: "8px", // Reduced from 10px
    color: "#94a3b8",
    marginLeft: "auto",
  },

  errorMessage: {
    fontSize: "10px",
    color: "#ef4444",
    marginTop: "4px",
    fontStyle: "italic",
  },

  // Call Me button style (rectangular box)
  callMeButton: (isActive, isDisabled = false) => ({
    padding: "12px 24px",
    marginTop: "4px",
    background: isDisabled ? "linear-gradient(135deg, #e2e8f0, #cbd5e1)" : (isActive ? "#ef4444" : "#67d8ef"),
    color: isDisabled ? "#94a3b8" : "white",
    border: "none",
    borderRadius: "16px", // More box-like - less rounded
    cursor: isDisabled ? "not-allowed" : "pointer",
    fontSize: "14px",
    fontWeight: "600",
    transition: "all 0.2s ease",
    boxShadow: isDisabled ? "inset 0 0 0 1px rgba(148, 163, 184, 0.3)" : "0 2px 8px rgba(0,0,0,0.1)",
    minWidth: "120px", // Ensure consistent width
    opacity: isDisabled ? 0.7 : 1,
  }),

  acsHoverDialog: {
    position: "fixed",
    transform: "translateX(-50%)",
    marginTop: "0",
    backgroundColor: "rgba(255, 255, 255, 0.98)",
    border: "1px solid #fed7aa",
    borderRadius: "6px",
    padding: "8px 10px",
    fontSize: "9px",
    color: "#b45309",
    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
    width: "260px",
    zIndex: 2000,
    lineHeight: "1.4",
    pointerEvents: "none",
  },

  phoneDisabledDialog: {
    position: "fixed",
    transform: "translateX(-50%)",
    backgroundColor: "rgba(255, 255, 255, 0.98)",
    border: "1px solid #fecaca",
    borderRadius: "8px",
    padding: "10px 14px",
    fontSize: "11px",
    color: "#b45309",
    boxShadow: "0 6px 16px rgba(0,0,0,0.15)",
    width: "280px",
    zIndex: 2000,
    lineHeight: "1.5",
    pointerEvents: "none",
  },

  // Help button in top right corner
  helpButton: {
    position: "relative",
    width: "32px",
    height: "32px",
    borderRadius: "50%",
    border: "1px solid #e2e8f0",
    background: "#f8fafc",
    color: "#64748b",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "14px",
    transition: "all 0.2s ease",
    boxShadow: "0 2px 8px rgba(0,0,0,0.05)",
    flexShrink: 0,
    zIndex: 20,
  },

  helpButtonHover: {
    background: "#f1f5f9",
    color: "#334155",
    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
    transform: "scale(1.05)",
  },

  industryTag: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
  },
  topTabsContainer: {
    position: "absolute",
    top: "-8px",
    left: "36px",
    display: "flex",
    alignItems: "center",
    gap: "6px",
    zIndex: 0,
  },
  topTab: (active, palette = {}) => {
    const {
      background = "linear-gradient(135deg, #334155, #1f2937)",
      color = "#f8fafc",
      borderColor = "rgba(51,65,85,0.45)",
      shadow = "0 10px 22px rgba(30,64,175,0.22)",
      textShadow = "0 1px 2px rgba(15,23,42,0.45)",
    } = palette;
    return {
      padding: "7px 18px",
      borderRadius: "12px 12px 0 0",
      border: active ? `1px solid ${borderColor}` : "1px solid rgba(148,163,184,0.45)",
      borderBottom: active ? "1px solid transparent" : "1px solid rgba(148,163,184,0.5)",
      background: active ? background : "rgba(148,163,184,0.08)",
      color: active ? color : "#475569",
      gap: "12px",
      flexWrap: "wrap",
      fontSize: "9px",
      fontWeight: 700,
      textTransform: "uppercase",
      letterSpacing: "0.14em",
      boxShadow: active ? shadow : "inset 0 -1px 0 rgba(148,163,184,0.4)",
      cursor: active ? "default" : "pointer",
      transition: "all 0.24s ease",
      textShadow: active ? textShadow : "none",
    };
  },
  createProfileButton: {
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    fontWeight: 600,
    fontSize: "11px",
    padding: "10px 20px",
    borderRadius: "18px",
    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
    boxShadow: "0 10px 22px rgba(99,102,241,0.28)",
    color: "#f8fafc",
    border: "1px solid rgba(255,255,255,0.25)",
  },
  createProfileButtonHover: {
    boxShadow: "0 14px 26px rgba(99,102,241,0.33)",
  },

  helpTooltip: {
    position: "absolute",
    top: "calc(100% + 10px)",
    left: "auto",
    right: 0,
    background: "white",
    border: "1px solid #e2e8f0",
    borderRadius: "12px",
    padding: "16px",
    width: "280px",
    boxShadow: "0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08)",
    fontSize: "12px",
    lineHeight: "1.5",
    color: "#334155",
    zIndex: 25,
    opacity: 0,
    transform: "translateY(-8px)",
    pointerEvents: "none",
    transition: "all 0.2s ease",
  },

  helpTooltipVisible: {
    opacity: 1,
    transform: "translateY(0px)",
    pointerEvents: "auto",
  },

  helpTooltipTitle: {
    fontSize: "13px",
    fontWeight: "600",
    color: "#1e293b",
    marginBottom: "8px",
    display: "flex",
    alignItems: "center",
    flexShrink: 0,
    gap: "6px",
  },

  helpTooltipText: {
    marginBottom: "12px",
    color: "#64748b",
  },

  helpTooltipContact: {
    fontSize: "11px",
    color: "#67d8ef",
    fontFamily: "monospace",
    background: "#f8fafc",
    padding: "4px 8px",
    borderRadius: "6px",
    border: "1px solid #e2e8f0",
  },
  demoFormBackdrop: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(15, 23, 42, 0.25)",
    zIndex: 12000,
  },
  demoFormOverlay: {
    position: "fixed",
    top: "50%",
    left: "50%",
    transform: "translate(-50%, -50%)",
    zIndex: 12010,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "8px",
    maxWidth: "100vw",
    maxHeight: "calc(100vh - 80px)",
    overflowY: "auto",
    scrollbarWidth: "none",
    msOverflowStyle: "none",
  },
  profileButtonWrapper: {
    margin: "0 24px",
    paddingBottom: "12px",
  },
  profileMenuPaper: {
    maxWidth: '380px',
    minWidth: '320px',
    boxShadow: '0 8px 32px rgba(0,0,0,0.12), 0 2px 16px rgba(0,0,0,0.08)',
    borderRadius: '16px',
    border: '1px solid rgba(226, 232, 240, 0.8)',
    backdropFilter: 'blur(20px)',
  },
  profileDetailsGrid: {
    padding: '16px',
    display: 'grid',
    gap: '8px',
    fontSize: '12px',
    color: '#1f2937',
  },
  profileDetailItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '4px 0',
  },
  profileDetailLabel: {
    fontWeight: '600',
    color: '#64748b',
    fontSize: '11px',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  profileDetailValue: {
    fontWeight: '500',
    color: '#1f2937',
    textAlign: 'right',
    maxWidth: '200px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  profileMenuHeader: {
    padding: '16px 16px 8px 16px',
    background: 'linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%)',
    borderTopLeftRadius: '16px',
    borderTopRightRadius: '16px',
  },
  ssnChipWrapper: {
    display: 'flex',
    justifyContent: 'center',
    padding: '8px 16px',
    background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.05) 0%, rgba(249, 115, 22, 0.05) 100%)',
  },
  profileBadge: {
    padding: "10px 12px",
    borderRadius: "10px",
    background: "linear-gradient(135deg, #f97316, #ef4444)",
    color: "#ffffff",
    fontWeight: 700,
    letterSpacing: "0.6px",
    textAlign: "center",
  },
  profileNotice: {
    marginTop: "4px",
    padding: "8px 10px",
    borderRadius: "8px",
    background: "#fef2f2",
    border: "1px solid #fecaca",
    color: "#b91c1c",
    fontSize: "11px",
    fontWeight: 600,
    textAlign: "center",
  },
};

export const ensureVoiceAppKeyframes = () => {
  if (typeof document === 'undefined') return;
  if (document.getElementById('voice-app-keyframes')) return;
  const styleSheet = document.createElement('style');
  styleSheet.id = 'voice-app-keyframes';
  styleSheet.textContent = `
  @keyframes pulse {
    0% {
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4);
    }
    70% {
      box-shadow: 0 0 0 6px rgba(16, 185, 129, 0);
    }
    100% {
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
    }
  }
  .demo-form-overlay {
    scrollbar-width: none;
    -ms-overflow-style: none;
  }
  .demo-form-overlay::-webkit-scrollbar {
    display: none;
  }
  `;
  document.head.appendChild(styleSheet);
};
