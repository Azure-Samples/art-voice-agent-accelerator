import React, { useCallback, useEffect, useRef, useState } from 'react';
import "reactflow/dist/style.css";
import useBargeIn from '../hooks/useBargeIn.js';
import logger from '../utils/logger.js';

// Environment configuration
const backendPlaceholder = '__BACKEND_URL__';
const API_BASE_URL = backendPlaceholder.startsWith('__') 
  ? import.meta.env.VITE_BACKEND_BASE_URL || 'http://localhost:8000'
  : backendPlaceholder;

const WS_URL = API_BASE_URL.replace(/^https?/, "wss");

// Session management utilities
const getOrCreateSessionId = () => {
  const sessionKey = 'voice_agent_session_id';
  let sessionId = sessionStorage.getItem(sessionKey);
  
  if (!sessionId) {
    const tabId = Math.random().toString(36).substr(2, 6);
    sessionId = `session_${Date.now()}_${tabId}`;
    sessionStorage.setItem(sessionKey, sessionId);
  }
  
  
  return sessionId;
};

const createNewSessionId = () => {
  const sessionKey = 'voice_agent_session_id';
  const tabId = Math.random().toString(36).substr(2, 6);
  const sessionId = `session_${Date.now()}_${tabId}`;
  sessionStorage.setItem(sessionKey, sessionId);
  logger.info('Created NEW session ID for reset:', sessionId);
  return sessionId;
};

const createMetricsState = () => ({
  sessionStart: null,
  sessionStartIso: null,
  sessionId: null,
  firstTokenTs: null,
  ttftMs: null,
  turnCounter: 0,
  turns: [],
  bargeInEvents: [],
  pendingBargeIn: null,
  lastAudioFrameTs: null,
  currentTurnId: null,
  awaitingAudioTurnId: null,
});

const toMs = (value) => (typeof value === "number" ? Math.round(value) : undefined);

// Component styles
const styles = {
  root: {
    width: "768px",
    maxWidth: "768px",
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
    width: "100%",
    maxWidth: "100%",
    height: "90vh",
    maxHeight: "900px",
    background: "white",
    borderRadius: "20px",
    boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
    border: "0px solid #ce1010ff",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },

  appHeader: {
    backgroundColor: "#f8fafc",
    background: "linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)",
    padding: "16px 24px 12px 24px",
    borderBottom: "1px solid #e2e8f0",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
  },

  appTitleContainer: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "4px",
  },

  appTitleWrapper: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },

  appTitleIcon: {
    fontSize: "20px",
    opacity: 0.7,
  },

  appTitle: {
    fontSize: "18px",
    fontWeight: "600",
    color: "#334155",
    textAlign: "center",
    margin: 0,
    letterSpacing: "0.1px",
  },

  appSubtitle: {
    fontSize: "12px",
    fontWeight: "400",
    color: "#64748b",
    textAlign: "center",
    margin: 0,
    letterSpacing: "0.1px",
    maxWidth: "350px",
    lineHeight: "1.3",
    opacity: 0.8,
  },
  waveformSection: {
    backgroundColor: "#f1f5f9",
    background: "linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%)",
    padding: "12px 4px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    borderBottom: "1px solid #e2e8f0",
    height: "22%",
    minHeight: "90px",
    position: "relative",
  },
  
  waveformSectionTitle: {
    fontSize: "12px",
    fontWeight: "500",
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
    marginBottom: "8px",
    opacity: 0.8,
  },
  
  // Section divider line - more subtle
  sectionDivider: {
    position: "absolute",
    bottom: "-1px",
    left: "20%",
    right: "20%",
    height: "1px",
    backgroundColor: "#cbd5e1",
    borderRadius: "0.5px",
    opacity: 0.6,
  },
  
  waveformContainer: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
    height: "60%",
    padding: "0 10px",
    background: "radial-gradient(ellipse at center, rgba(100, 116, 139, 0.05) 0%, transparent 70%)",
    borderRadius: "6px",
  },
  
  waveformSvg: {
    width: "100%",
    height: "60px",
    filter: "drop-shadow(0 1px 2px rgba(100, 116, 139, 0.1))",
    transition: "filter 0.3s ease",
  },
  
  chatSection: {
    flex: 1,
    padding: "15px 20px 15px 5px",
    width: "100%",
    overflowY: "auto",
    backgroundColor: "#ffffff",
    borderBottom: "1px solid #e2e8f0",
    display: "flex",
    flexDirection: "column",
    position: "relative",
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
    gap: "16px",
    flex: 1,
    overflowY: "auto",
    padding: "0",
  },
  
  userMessage: {
    alignSelf: "flex-end",
    maxWidth: "75%",
    marginRight: "15px",
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
    maxWidth: "80%", // Increased width for maximum space usage
    marginLeft: "0px", // No left margin - flush to edge
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
    padding: "12px",
    backgroundColor: "#f1f5f9",
    background: "linear-gradient(180deg, #f1f5f9 0%, #e2e8f0 100%)",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    height: "15%",
    minHeight: "100px",
    borderTop: "1px solid #e2e8f0",
    position: "relative",
  },
  
  controlContainer: {
    display: "flex",
    gap: "8px",
    background: "white",
    padding: "12px 16px",
    borderRadius: "24px",
    boxShadow: "0 4px 16px rgba(100, 116, 139, 0.08), 0 1px 4px rgba(100, 116, 139, 0.04)",
    border: "1px solid #e2e8f0",
    width: "fit-content",
  },
  
  controlButton: (isActive, variant = 'default') => {
    // Base styles for all buttons
    return {
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
      background: "linear-gradient(135deg, #f1f5f9, #e2e8f0)",
      color: isActive ? "#10b981" : "#64748b",
      transform: isActive ? "scale(1.05)" : "scale(1)",
      boxShadow: isActive ? 
        "0 6px 20px rgba(16,185,129,0.3), 0 0 0 3px rgba(16,185,129,0.1)" : 
        "0 2px 8px rgba(0,0,0,0.08)",
    };
  },

  // Enhanced button styles with hover effects
  resetButton: (isActive, isHovered) => ({
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
    background: "linear-gradient(135deg, #f1f5f9, #e2e8f0)",
    color: isActive ? "#10b981" : "#64748b",
    transform: isHovered ? "scale(1.08)" : (isActive ? "scale(1.05)" : "scale(1)"),
    boxShadow: isHovered ? 
      "0 8px 24px rgba(100,116,139,0.3), 0 0 0 3px rgba(100,116,139,0.15)" :
      (isActive ? 
        "0 6px 20px rgba(16,185,129,0.3), 0 0 0 3px rgba(16,185,129,0.1)" : 
        "0 2px 8px rgba(0,0,0,0.08)"),
  }),

  micButton: (isActive, isHovered) => ({
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
      (isActive ? "linear-gradient(135deg, #10b981, #059669)" : "linear-gradient(135deg, #dcfce7, #bbf7d0)") :
      "linear-gradient(135deg, #f1f5f9, #e2e8f0)",
    color: isHovered ? 
      (isActive ? "white" : "#16a34a") :
      (isActive ? "#10b981" : "#64748b"),
    transform: isHovered ? "scale(1.08)" : (isActive ? "scale(1.05)" : "scale(1)"),
    boxShadow: isHovered ? 
      "0 8px 25px rgba(16,185,129,0.4), 0 0 0 4px rgba(16,185,129,0.15), inset 0 1px 2px rgba(255,255,255,0.2)" :
      (isActive ? 
        "0 6px 20px rgba(16,185,129,0.3), 0 0 0 3px rgba(16,185,129,0.1)" : 
        "0 2px 8px rgba(0,0,0,0.08)"),
  }),

  phoneButton: (isActive, isHovered, isDisabled = false) => {
    const base = {
      width: "56px",
      height: "56px",
      borderRadius: "50%",
      border: "none",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: "20px",
      transition: "all 0.3s ease",
      position: "relative",
    };

    if (isDisabled) {
      return {
        ...base,
        cursor: "not-allowed",
        background: "linear-gradient(135deg, #e2e8f0, #cbd5e1)",
        color: "#94a3b8",
        transform: "scale(1)",
        boxShadow: "inset 0 0 0 1px rgba(148, 163, 184, 0.3)",
        opacity: 0.7,
      };
    }

    return {
      ...base,
      cursor: "pointer",
      background: isHovered ? 
        (isActive ? "linear-gradient(135deg, #3f75a8ff, #2b5d8f)" : "linear-gradient(135deg, #dcfce7, #bbf7d0)") :
        "linear-gradient(135deg, #f1f5f9, #e2e8f0)",
      color: isHovered ? 
        (isActive ? "white" : "#3f75a8ff") :
        (isActive ? "#3f75a8ff" : "#64748b"),
      transform: isHovered ? "scale(1.08)" : (isActive ? "scale(1.05)" : "scale(1)"),
      boxShadow: isHovered ? 
        "0 8px 25px rgba(16,185,129,0.4), 0 0 0 4px rgba(16,185,129,0.15), inset 0 1px 2px rgba(255,255,255,0.2)" :
        (isActive ? 
          "0 6px 20px rgba(16,185,129,0.3), 0 0 0 3px rgba(16,185,129,0.1)" : 
          "0 2px 8px rgba(0,0,0,0.08)"),
    };
  },

  // Tooltip styles
  buttonTooltip: {
    position: 'absolute',
    bottom: '-45px',
    left: '50%',
    transform: 'translateX(-50%)',
    background: 'rgba(51, 65, 85, 0.95)',
    color: '#f1f5f9',
    padding: '8px 12px',
    borderRadius: '8px',
    fontSize: '11px',
    fontWeight: '500',
    whiteSpace: 'nowrap',
    backdropFilter: 'blur(10px)',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
    border: '1px solid rgba(255,255,255,0.1)',
    pointerEvents: 'none',
    opacity: 0,
    transition: 'opacity 0.2s ease, transform 0.2s ease',
    zIndex: 1000,
  },

  buttonTooltipVisible: {
    opacity: 1,
    transform: 'translateX(-50%) translateY(-2px)',
  },
  
  // Input section for phone calls
  phoneInputSection: {
    position: "absolute",
    bottom: "60px", // Moved lower from 140px to 60px to avoid blocking chat bubbles
    left: "500px", // Moved further to the right from 400px to 500px
    background: "white",
    padding: "20px",
    borderRadius: "20px", // More rounded - changed from 16px to 20px
    boxShadow: "0 8px 32px rgba(0,0,0,0.12)",
    border: "1px solid #e2e8f0",
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    minWidth: "240px",
    zIndex: 90,
  },
  
  phoneInput: {
    padding: "12px 16px",
    border: "1px solid #d1d5db",
    borderRadius: "12px", // More rounded - changed from 8px to 12px
    fontSize: "14px",
    outline: "none",
    transition: "border-color 0.2s ease, box-shadow 0.2s ease",
    "&:focus": {
      borderColor: "#10b981",
      boxShadow: "0 0 0 3px rgba(16,185,129,0.1)"
    }
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
    boxShadow: "0 8px 32px rgba(0,0,0,0.12)",
    zIndex: 1000,
    minWidth: "280px",
    maxWidth: "320px",
    backdropFilter: "blur(8px)",
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
    background: isDisabled ? "linear-gradient(135deg, #e2e8f0, #cbd5e1)" : (isActive ? "#ef4444" : "#67d8ef"),
    color: isDisabled ? "#94a3b8" : "white",
    border: "none",
    borderRadius: "8px", // More box-like - less rounded
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
    position: "absolute",
    top: "16px",
    right: "16px",
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
    zIndex: 1000,
    boxShadow: "0 2px 8px rgba(0,0,0,0.05)",
  },

  helpButtonHover: {
    background: "#f1f5f9",
    color: "#334155",
    boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
    transform: "scale(1.05)",
  },

  helpTooltip: {
    position: "absolute",
    top: "40px",
    right: "0px",
    background: "white",
    border: "1px solid #e2e8f0",
    borderRadius: "12px",
    padding: "16px",
    width: "280px",
    boxShadow: "0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08)",
    fontSize: "12px",
    lineHeight: "1.5",
    color: "#334155",
    zIndex: 1001,
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
};
// Add keyframe animation for pulse effect
const styleSheet = document.createElement("style");
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
`;
document.head.appendChild(styleSheet);

/* ------------------------------------------------------------------ *
 *  BACKEND HELP BUTTON COMPONENT
 * ------------------------------------------------------------------ */
const BackendHelpButton = () => {
  const [isHovered, setIsHovered] = useState(false);
  const [isClicked, setIsClicked] = useState(false);

  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsClicked(!isClicked);
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
  };

  return (
    <div 
      style={{
        width: '14px',
        height: '14px',
        borderRadius: '50%',
        backgroundColor: isHovered ? '#3b82f6' : '#64748b',
        color: 'white',
        fontSize: '9px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        fontWeight: '600',
        position: 'relative',
        flexShrink: 0
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      ?
      <div style={{
        visibility: (isHovered || isClicked) ? 'visible' : 'hidden',
        opacity: (isHovered || isClicked) ? 1 : 0,
        position: 'absolute',
        bottom: '20px',
        left: '0',
        backgroundColor: 'rgba(0, 0, 0, 0.95)',
        color: 'white',
        padding: '12px',
        borderRadius: '8px',
        fontSize: '11px',
        lineHeight: '1.4',
        minWidth: '280px',
        maxWidth: '320px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
        zIndex: 10000,
        transition: 'all 0.2s ease',
        backdropFilter: 'blur(8px)'
      }}>
        <div style={{
          fontSize: '12px',
          fontWeight: '600',
          color: '#67d8ef',
          marginBottom: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}>
          🔧 Backend Status Monitor
        </div>
        <div style={{ marginBottom: '8px' }}>
          Real-time health monitoring for all ARTAgent backend services including Redis cache, Azure OpenAI, Speech Services, and Communication Services.
        </div>
        <div style={{ marginBottom: '8px' }}>
          <strong>Status Colors:</strong><br/>
          🟢 Healthy - All systems operational<br/>
          🟡 Degraded - Some performance issues<br/>
          🔴 Unhealthy - Service disruption
        </div>
        <div style={{ fontSize: '10px', color: '#94a3b8', fontStyle: 'italic' }}>
          Auto-refreshes every 30 seconds • Click to expand for details
        </div>
        {isClicked && (
          <div style={{
            textAlign: 'center',
            marginTop: '8px',
            fontSize: '9px',
            color: '#94a3b8',
            fontStyle: 'italic'
          }}>
            Click ? again to close
          </div>
        )}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ *
 *  BACKEND STATISTICS BUTTON COMPONENT
 * ------------------------------------------------------------------ */
const BackendStatisticsButton = ({ onToggle, isActive }) => {
  const [isHovered, setIsHovered] = useState(false);

  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    onToggle();
  };

  return (
    <div 
      style={{
        width: '14px',
        height: '14px',
        borderRadius: '50%',
        backgroundColor: isActive ? '#3b82f6' : (isHovered ? '#3b82f6' : '#64748b'),
        color: 'white',
        fontSize: '8px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        fontWeight: '600',
        position: 'relative',
        flexShrink: 0
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={handleClick}
      title="Toggle session statistics"
    >
      📊
    </div>
  );
};

/* ------------------------------------------------------------------ *
 *  HELP BUTTON COMPONENT
 * ------------------------------------------------------------------ */
const HelpButton = () => {
  const [isHovered, setIsHovered] = useState(false);
  const [isClicked, setIsClicked] = useState(false);

  const handleClick = (e) => {
    // Don't prevent default for links
    if (e.target.tagName !== 'A') {
      e.preventDefault();
      e.stopPropagation();
      setIsClicked(!isClicked);
    }
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
    // Only hide if not clicked
    if (!isClicked) {
      // Tooltip will hide via CSS
    }
  };

  return (
    <div 
      style={{
        ...styles.helpButton,
        ...(isHovered ? styles.helpButtonHover : {})
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
    >
      ?
      <div style={{
        ...styles.helpTooltip,
        ...((isHovered || isClicked) ? styles.helpTooltipVisible : {})
      }}>
        <div style={styles.helpTooltipTitle}>
        </div>
        <div style={{
          ...styles.helpTooltipText,
          color: '#dc2626',
          fontWeight: '600',
          fontSize: '12px',
          marginBottom: '12px',
          padding: '8px',
          backgroundColor: '#fef2f2',
          borderRadius: '4px',
          border: '1px solid #fecaca'
        }}>
          This is a demo available for Microsoft employees only.
        </div>
        <div style={styles.helpTooltipTitle}>
          🤖 ARTAgent Demo
        </div>
        <div style={styles.helpTooltipText}>
          ARTAgent is an accelerator that delivers a friction-free, AI-driven voice experience—whether callers dial a phone number, speak to an IVR, or click "Call Me" in a web app. Built entirely on Azure services, it provides a low-latency stack that scales on demand while keeping the AI layer fully under your control.
        </div>
        <div style={styles.helpTooltipText}>
          Design a single agent or orchestrate multiple specialist agents. The framework allows you to build your voice agent from scratch, incorporate memory, configure actions, and fine-tune your TTS and STT layers.
        </div>
        <div style={styles.helpTooltipText}>
          🤔 <strong>Try asking about:</strong> Insurance claims, policy questions, authentication, or general inquiries.
        </div>
        <div style={styles.helpTooltipText}>
         📑 <a 
            href="https://microsoft.sharepoint.com/teams/rtaudioagent" 
            target="_blank" 
            rel="noopener noreferrer"
            style={{
              color: '#3b82f6',
              textDecoration: 'underline'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            Visit the Project Hub
          </a> for instructions, deep dives and more.
        </div>
        <div style={styles.helpTooltipText}>
          📧 Questions or feedback? <a 
            href="mailto:rtvoiceagent@microsoft.com?subject=ARTAgent Feedback"
            style={{
              color: '#3b82f6',
              textDecoration: 'underline'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            Contact the team
          </a>
        </div>
        {isClicked && (
          <div style={{
            textAlign: 'center',
            marginTop: '8px',
            fontSize: '10px',
            color: '#64748b',
            fontStyle: 'italic'
          }}>
            Click ? again to close
          </div>
        )}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ *
 *  ENHANCED BACKEND INDICATOR WITH HEALTH MONITORING & AGENT CONFIG
 * ------------------------------------------------------------------ */
const BackendIndicator = ({ url, onConfigureClick, onStatusChange }) => {
  const [isConnected, setIsConnected] = useState(null);
  const [displayUrl, setDisplayUrl] = useState(url);
  const [readinessData, setReadinessData] = useState(null);
  const [agentsData, setAgentsData] = useState(null);
  const [error, setError] = useState(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isClickedOpen, setIsClickedOpen] = useState(false);
  const [showComponentDetails, setShowComponentDetails] = useState(false);
  const [screenWidth, setScreenWidth] = useState(window.innerWidth);
  const [showAgentConfig, setShowAgentConfig] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [configChanges, setConfigChanges] = useState({});
  const [updateStatus, setUpdateStatus] = useState({});
  const [showStatistics, setShowStatistics] = useState(false);
  const [showAcsHover, setShowAcsHover] = useState(false);
  const [acsTooltipPos, setAcsTooltipPos] = useState(null);
  const summaryRef = useRef(null);

  // Track screen width for responsive positioning
  useEffect(() => {
    const handleResize = () => setScreenWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Check readiness endpoint
  const checkReadiness = async () => {
    try {
      const response = await fetch(`${url}/api/v1/readiness`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      
      // Validate expected structure
      if (data.status && data.checks && Array.isArray(data.checks)) {
        setReadinessData(data);
        setIsConnected(data.status !== "unhealthy");
        setError(null);
      } else {
        throw new Error("Invalid response structure");
      }
    } catch (err) {
      logger.error("Readiness check failed:", err);
      setIsConnected(false);
      setError(err.message);
      setReadinessData(null);
    }
  };

  // Check agents endpoint
  const checkAgents = async () => {
    try {
      const response = await fetch(`${url}/api/v1/agents`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      
      if (data.status === "success" && data.agents && Array.isArray(data.agents)) {
        setAgentsData(data);
      } else {
        throw new Error("Invalid agents response structure");
      }
    } catch (err) {
      logger.error("Agents check failed:", err);
      setAgentsData(null);
    }
  };

  // Check health endpoint for session statistics
  const [healthData, setHealthData] = useState(null);
  const checkHealth = async () => {
    try {
      const response = await fetch(`${url}/api/v1/health`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      
      if (data.status) {
        setHealthData(data);
      } else {
        throw new Error("Invalid health response structure");
      }
    } catch (err) {
      logger.error("Health check failed:", err);
      setHealthData(null);
    }
  };

  // Update agent configuration
  const updateAgentConfig = async (agentName, config) => {
    try {
      setUpdateStatus({...updateStatus, [agentName]: 'updating'});
      
      const response = await fetch(`${url}/api/v1/agents/${agentName}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(config),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      
      setUpdateStatus({...updateStatus, [agentName]: 'success'});
      
      // Refresh agents data
      checkAgents();
      
      // Clear success status after 3 seconds
      setTimeout(() => {
        setUpdateStatus(prev => {
          const newStatus = {...prev};
          delete newStatus[agentName];
          return newStatus;
        });
      }, 3000);
      
      return data;
    } catch (err) {
      logger.error("Agent config update failed:", err);
      setUpdateStatus({...updateStatus, [agentName]: 'error'});
      
      // Clear error status after 5 seconds
      setTimeout(() => {
        setUpdateStatus(prev => {
          const newStatus = {...prev};
          delete newStatus[agentName];
          return newStatus;
        });
      }, 5000);
      
      throw err;
    }
  };

  useEffect(() => {
    // Parse and format the URL for display
    try {
      const urlObj = new URL(url);
      const host = urlObj.hostname;
      const protocol = urlObj.protocol.replace(':', '');
      
      // Shorten Azure URLs
      if (host.includes('.azurewebsites.net')) {
        const appName = host.split('.')[0];
        setDisplayUrl(`${protocol}://${appName}.azure...`);
      } else if (host === 'localhost') {
        setDisplayUrl(`${protocol}://localhost:${urlObj.port || '8000'}`);
      } else {
        setDisplayUrl(`${protocol}://${host}`);
      }
    } catch (e) {
      setDisplayUrl(url);
    }

    // Initial check
    checkReadiness();
    checkAgents();
    checkHealth();

    // Set up periodic checks every 30 seconds
    const interval = setInterval(() => {
      checkReadiness();
      checkAgents();
      checkHealth();
    }, 30000);

    return () => clearInterval(interval);
  }, [url]);

  // Get overall health status
  const readinessChecks = readinessData?.checks ?? [];
  const unhealthyChecks = readinessChecks.filter((c) => c.status === "unhealthy");
  const degradedChecks = readinessChecks.filter((c) => c.status === "degraded");
  const acsOnlyIssue =
    unhealthyChecks.length > 0 &&
    degradedChecks.length === 0 &&
    unhealthyChecks.every((c) => c.component === "acs_caller") &&
    readinessChecks
      .filter((c) => c.component !== "acs_caller")
      .every((c) => c.status === "healthy");

  const getOverallStatus = () => {
    if (!readinessData?.checks) {
      if (isConnected === null) return "checking";
      if (!isConnected) return "unhealthy";
      return "checking";
    }

    if (acsOnlyIssue) return "degraded";
    if (unhealthyChecks.length > 0) return "unhealthy";
    if (degradedChecks.length > 0) return "degraded";
    return "healthy";
  };

  const overallStatus = getOverallStatus();
  const statusColor = overallStatus === "healthy" ? "#10b981" : 
                     overallStatus === "degraded" ? "#f59e0b" :
                     overallStatus === "unhealthy" ? "#ef4444" : "#6b7280";

  useEffect(() => {
    if (typeof onStatusChange === "function") {
      onStatusChange({ status: overallStatus, acsOnlyIssue });
    }
  }, [overallStatus, acsOnlyIssue, onStatusChange]);

  useEffect(() => {
    if (!acsOnlyIssue && showAcsHover) {
      setShowAcsHover(false);
      setAcsTooltipPos(null);
    }
  }, [acsOnlyIssue, showAcsHover]);

  // Dynamic sizing based on screen width - keep in bottom left but adjust size to maintain separation
  const getResponsiveStyle = () => {
    const baseStyle = {
      ...styles.backendIndicator,
      transition: "all 0.3s ease",
    };

    // Calculate available space for the status box to avoid ARTAgent overlap
    const containerWidth = 768;
    const containerLeftEdge = (screenWidth / 2) - (containerWidth / 2);
    const availableWidth = containerLeftEdge - 40 - 20; // 40px margin from container, 20px from screen edge
    
    // Adjust size based on available space
    if (availableWidth < 200) {
      // Very narrow - compact size
      return {
        ...baseStyle,
        minWidth: "150px",
        maxWidth: "180px",
        padding: !shouldBeExpanded && overallStatus === "healthy" ? "8px 12px" : "10px 14px",
        fontSize: "10px",
      };
    } else if (availableWidth < 280) {
      // Medium space - reduced size
      return {
        ...baseStyle,
        minWidth: "180px",
        maxWidth: "250px",
        padding: !shouldBeExpanded && overallStatus === "healthy" ? "10px 14px" : "12px 16px",
      };
    } else {
      // Plenty of space - full size
      return {
        ...baseStyle,
        minWidth: !shouldBeExpanded && overallStatus === "healthy" ? "200px" : "280px",
        maxWidth: "320px",
        padding: !shouldBeExpanded && overallStatus === "healthy" ? "10px 14px" : "12px 16px",
      };
    }
  };

  // Component icon mapping with descriptions
  const componentIcons = {
    redis: "💾",
    azure_openai: "🧠",
    speech_services: "🎙️",
    acs_caller: "📞",
    rt_agents: "🤖"
  };

  // Component descriptions
  const componentDescriptions = {
    redis: "Redis Cache - Session & state management",
    azure_openai: "Azure OpenAI - GPT models & embeddings",
    speech_services: "Speech Services - STT/TTS processing",
    acs_caller: "Communication Services - Voice calling",
    rt_agents: "RT Agents - Real-time Voice Agents"
  };

  const handleBackendClick = (e) => {
    // Don't trigger if clicking on buttons
    if (e.target.closest('div')?.style?.cursor === 'pointer' && e.target !== e.currentTarget) {
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    setIsClickedOpen(!isClickedOpen);
    if (!isClickedOpen) {
      setIsExpanded(true);
    }
  };

  const handleMouseEnter = () => {
    if (!isClickedOpen) {
      setIsExpanded(true);
    }
  };

  const handleMouseLeave = () => {
    if (!isClickedOpen) {
      setIsExpanded(false);
    }
  };

  // Determine if should be expanded (either clicked open or hovered)
  const shouldBeExpanded = isClickedOpen || isExpanded;

  return (
    <div 
      style={getResponsiveStyle()} 
      title={isClickedOpen ? `Click to close backend status` : `Click to pin open backend status`}
      onClick={handleBackendClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div style={styles.backendHeader}>
        <div style={{
          ...styles.backendStatus,
          backgroundColor: statusColor,
        }}></div>
        <span style={styles.backendLabel}>Backend Status</span>
        <BackendHelpButton />
        <span style={{
          ...styles.expandIcon,
          transform: shouldBeExpanded ? "rotate(180deg)" : "rotate(0deg)",
          color: isClickedOpen ? "#3b82f6" : styles.expandIcon.color,
          fontWeight: isClickedOpen ? "600" : "normal",
        }}>▼</span>
      </div>
      
      {/* Compact URL display when collapsed */}
      {!shouldBeExpanded && (
        <div style={{
          ...styles.backendUrl,
          fontSize: "9px",
          opacity: 0.7,
          marginTop: "2px",
        }}>
          {displayUrl}
        </div>
      )}

      {/* Only show component health when expanded or when there's an issue */}
      {(shouldBeExpanded || overallStatus !== "healthy") && (
        <>
          {/* Expanded information display */}
          {shouldBeExpanded && (
            <>
              
              {/* API Entry Point Info */}
              <div style={{
                padding: "8px 10px",
                backgroundColor: "#f8fafc",
                borderRadius: "8px",
                marginBottom: "10px",
                fontSize: "10px",
                border: "1px solid #e2e8f0",
              }}>
                <div style={{
                  fontWeight: "600",
                  color: "#475569",
                  marginBottom: "4px",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}>
                  🌐 Backend API Entry Point
                </div>
                <div style={{
                  color: "#64748b",
                  fontSize: "9px",
                  fontFamily: "monospace",
                  marginBottom: "6px",
                  padding: "3px 6px",
                  backgroundColor: "white",
                  borderRadius: "4px",
                  border: "1px solid #f1f5f9",
                }}>
                  {url}
                </div>
                <div style={{
                  color: "#64748b",
                  fontSize: "9px",
                  lineHeight: "1.3",
                }}>
                  Main FastAPI server handling WebSocket connections, voice processing, and AI agent orchestration
                </div>
              </div>

              {/* System status summary */}
              {readinessData && (
                <div 
                  style={{
                    padding: "6px 8px",
                    backgroundColor: overallStatus === "healthy" ? "#f0fdf4" : 
                                   overallStatus === "degraded" ? "#fffbeb" : "#fef2f2",
                    borderRadius: "6px",
                    marginBottom: "8px",
                    fontSize: "10px",
                    border: `1px solid ${overallStatus === "healthy" ? "#bbf7d0" : 
                                        overallStatus === "degraded" ? "#fed7aa" : "#fecaca"}`,
                    cursor: "pointer",
                    transition: "all 0.2s ease",
                  }}
                  ref={summaryRef}
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowComponentDetails(!showComponentDetails);
                  }}
                  onMouseEnter={() => {
                    if (summaryRef.current) {
                      const rect = summaryRef.current.getBoundingClientRect();
                      setAcsTooltipPos({
                        top: rect.bottom + 8,
                        left: rect.left + rect.width / 2,
                      });
                    }
                    setShowAcsHover(true);
                  }}
                  onMouseLeave={() => {
                    setShowAcsHover(false);
                    setAcsTooltipPos(null);
                  }}
                  title="Click to show/hide component details"
                >
                  <div style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}>
                    <div>
                      <div style={{
                        fontWeight: "600",
                        color: overallStatus === "healthy" ? "#166534" : 
                              overallStatus === "degraded" ? "#92400e" : "#dc2626",
                        marginBottom: "2px",
                      }}>
                        System Status: {overallStatus.charAt(0).toUpperCase() + overallStatus.slice(1)}
                      </div>
                      <div style={{
                        color: "#64748b",
                        fontSize: "9px",
                      }}>
                        {readinessData.checks.length} components monitored • 
                        Last check: {new Date().toLocaleTimeString()}
                      </div>
                    </div>
                    <div style={{
                      fontSize: "12px",
                      color: "#64748b",
                      transform: showComponentDetails ? "rotate(180deg)" : "rotate(0deg)",
                      transition: "transform 0.2s ease",
                    }}>
                      ▼
                    </div>
                  </div>
                </div>
              )}

              {acsOnlyIssue && showAcsHover && acsTooltipPos && (
                <div
                  style={{
                    ...styles.acsHoverDialog,
                    top: acsTooltipPos.top,
                    left: acsTooltipPos.left,
                  }}
                >
                  ACS outbound calling is currently unavailable, but the Conversation API continues to stream microphone audio from this device to the backend.
                </div>
              )}
            </>
          )}

          {error ? (
            <div style={styles.errorMessage}>
              ⚠️ Connection failed: {error}
            </div>
          ) : readinessData?.checks && showComponentDetails ? (
            <>
              <div style={styles.componentGrid}>
                {readinessData.checks.map((check, idx) => (
                  <div 
                    key={idx} 
                    style={{
                      ...styles.componentItem,
                      flexDirection: "column",
                      alignItems: "flex-start",
                      padding: "6px 8px", // Reduced from 12px 16px to half
                    }}
                    title={check.details || `${check.component} status: ${check.status}`}
                  >
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "5px", // Reduced from 10px to half
                      width: "100%",
                    }}>
                      <span>{componentIcons[check.component] || "•"}</span>
                      <div style={styles.componentDot(check.status)}></div>
                      <span style={styles.componentName}>
                        {check.component.replace(/_/g, ' ')}
                      </span>
                      {check.check_time_ms !== undefined && (
                        <span style={styles.responseTime}>
                          {check.check_time_ms.toFixed(0)}ms
                        </span>
                      )}
                    </div>
                    
                    {/* Component description when expanded */}
                    {shouldBeExpanded && (
                      <div style={{
                        fontSize: "8px", // Reduced from 10px
                        color: "#64748b",
                        marginTop: "3px", // Reduced from 6px to half
                        lineHeight: "1.3", // Reduced line height
                        fontStyle: "italic",
                        paddingLeft: "9px", // Reduced from 18px to half
                      }}>
                        {componentDescriptions[check.component] || "Backend service component"}
                      </div>
                    )}
                    
                    {/* Status details removed per user request */}
                  </div>
                ))}
              </div>
              
              {/* Component details section removed per user request */}
            </>
          ) : null}
          
          {readinessData?.response_time_ms && shouldBeExpanded && (
            <div style={{
              fontSize: "9px",
              color: "#94a3b8",
              marginTop: "8px",
              paddingTop: "8px",
              borderTop: "1px solid #f1f5f9",
              textAlign: "center",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}>
              <span>Health check latency: {readinessData.response_time_ms.toFixed(0)}ms</span>
              <span title="Auto-refreshes every 30 seconds">🔄</span>
            </div>
          )}

          {/* Session Statistics Section */}
          {shouldBeExpanded && healthData && (
            <div style={{
              marginTop: "8px",
              paddingTop: "8px",
              borderTop: "1px solid #f1f5f9",
            }}>
              <div style={{
                fontSize: "10px",
                fontWeight: "600",
                color: "#374151",
                marginBottom: "6px",
                display: "flex",
                alignItems: "center",
                gap: "4px",
              }}>
                📊 Session Statistics
              </div>
              
              <div style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "8px",
                fontSize: "9px",
              }}>
                {/* Active Sessions */}
                <div style={{
                  background: "#f8fafc",
                  border: "1px solid #e2e8f0",
                  borderRadius: "6px",
                  padding: "6px 8px",
                  textAlign: "center",
                }}>
                  <div style={{
                    fontWeight: "600",
                    color: "#10b981",
                    fontSize: "12px",
                  }}>
                    {healthData.active_sessions || 0}
                  </div>
                  <div style={{
                    color: "#64748b",
                    fontSize: "8px",
                  }}>
                    Active Sessions
                  </div>
                </div>

                {/* Session Metrics */}
                {healthData.session_metrics && (
                  <div style={{
                    background: "#f8fafc",
                    border: "1px solid #e2e8f0",
                    borderRadius: "6px",
                    padding: "6px 8px",
                    textAlign: "center",
                  }}>
                    <div style={{
                      fontWeight: "600",
                      color: "#3b82f6",
                      fontSize: "12px",
                    }}>
                      {healthData.session_metrics.connected || 0}
                    </div>
                    <div style={{
                      color: "#64748b",
                      fontSize: "8px",
                    }}>
                      Total Connected
                    </div>
                  </div>
                )}
                
                {/* Disconnected Sessions */}
                {healthData.session_metrics?.disconnected !== undefined && (
                  <div style={{
                    background: "#f8fafc",
                    border: "1px solid #e2e8f0",
                    borderRadius: "6px",
                    padding: "6px 8px",
                    textAlign: "center",
                    gridColumn: healthData.session_metrics ? "1 / -1" : "auto",
                  }}>
                    <div style={{
                      fontWeight: "600",
                      color: "#6b7280",
                      fontSize: "12px",
                    }}>
                      {healthData.session_metrics.disconnected}
                    </div>
                    <div style={{
                      color: "#64748b",
                      fontSize: "8px",
                    }}>
                      Disconnected
                    </div>
                  </div>
                )}
              </div>
              
              {/* Last updated */}
              <div style={{
                fontSize: "8px",
                color: "#94a3b8",
                marginTop: "6px",
                textAlign: "center",
                fontStyle: "italic",
              }}>
                Updated: {new Date(healthData.timestamp * 1000).toLocaleTimeString()}
              </div>
            </div>
          )}

          {/* Agents Configuration Section */}
          {shouldBeExpanded && agentsData?.agents && (
            <div style={{
              marginTop: "10px",
              paddingTop: "10px",
              borderTop: "2px solid #e2e8f0",
            }}>
              {/* Agents Header */}
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: "8px",
                padding: "6px 8px",
                backgroundColor: "#f1f5f9",
                borderRadius: "6px",
              }}>
                <div style={{
                  fontWeight: "600",
                  color: "#475569",
                  fontSize: "11px",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}>
                  🤖 RT Agents ({agentsData.agents.length})
                </div>
              </div>

              {/* Agents List */}
              <div style={{
                display: "grid",
                gridTemplateColumns: "1fr",
                gap: "6px",
                fontSize: "10px",
              }}>
                {agentsData.agents.map((agent, idx) => (
                  <div 
                    key={idx} 
                    style={{
                      padding: "8px 10px",
                      border: "1px solid #e2e8f0",
                      borderRadius: "6px",
                      backgroundColor: "white",
                      cursor: showAgentConfig ? "pointer" : "default",
                      transition: "all 0.2s ease",
                      ...(showAgentConfig && selectedAgent === agent.name ? {
                        borderColor: "#3b82f6",
                        backgroundColor: "#f0f9ff",
                      } : {}),
                    }}
                    onClick={() => showAgentConfig && setSelectedAgent(selectedAgent === agent.name ? null : agent.name)}
                    title={agent.description || `${agent.name} - Real-time voice agent`}
                  >
                    <div style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: "4px",
                    }}>
                      <div style={{
                        fontWeight: "600",
                        color: "#374151",
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                      }}>
                        <span style={{
                          width: "8px",
                          height: "8px",
                          borderRadius: "50%",
                          backgroundColor: agent.status === "loaded" ? "#10b981" : "#ef4444",
                          display: "inline-block",
                        }}></span>
                        {agent.name}
                      </div>
                      <div style={{
                        fontSize: "9px",
                        color: "#64748b",
                        display: "flex",
                        alignItems: "center",
                        gap: "6px",
                      }}>
                        {agent.model?.deployment_id && (
                          <span title={`Model: ${agent.model.deployment_id}`}>
                            💭 {agent.model.deployment_id.replace('gpt-', '')}
                          </span>
                        )}
                        {agent.voice?.current_voice && (
                          <span title={`Voice: ${agent.voice.current_voice}`}>
                            🔊 {agent.voice.current_voice.split('-').pop()?.replace('Neural', '')}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Agents Info Footer */}
              <div style={{
                fontSize: "8px",
                color: "#94a3b8",
                marginTop: "8px",
                textAlign: "center",
                fontStyle: "italic",
              }}>
                Runtime configuration • Changes require restart for persistence • Contact rtvoiceagent@microsoft.com
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ *
 *  WAVEFORM COMPONENT - SIMPLE & SMOOTH
 * ------------------------------------------------------------------ */
const WaveformVisualization = ({ speaker, audioLevel = 0, outputAudioLevel = 0 }) => {
  const [waveOffset, setWaveOffset] = useState(0);
  const [amplitude, setAmplitude] = useState(5);
  const animationRef = useRef();
  
  useEffect(() => {
    const animate = () => {
      setWaveOffset(prev => (prev + (speaker ? 2 : 1)) % 1000);
      
      setAmplitude(() => {
        // React to actual audio levels first, then fall back to speaker state
        if (audioLevel > 0.01) {
          // User is speaking - use real audio level
          const scaledLevel = audioLevel * 25;
          const smoothVariation = Math.sin(Date.now() * 0.002) * (scaledLevel * 0.2);
          return Math.max(8, scaledLevel + smoothVariation);
        } else if (outputAudioLevel > 0.01) {
          // Assistant is speaking - use output audio level
          const scaledLevel = outputAudioLevel * 20;
          const smoothVariation = Math.sin(Date.now() * 0.0018) * (scaledLevel * 0.25);
          return Math.max(6, scaledLevel + smoothVariation);
        } else if (speaker) {
          // Active speaking fallback - gentle rhythmic movement
          const time = Date.now() * 0.002;
          const baseAmplitude = 10;
          const rhythmicVariation = Math.sin(time) * 5;
          return baseAmplitude + rhythmicVariation;
        } else {
          // Idle state - gentle breathing pattern
          const time = Date.now() * 0.0008;
          const breathingAmplitude = 3 + Math.sin(time) * 1.5;
          return breathingAmplitude;
        }
      });
      
      animationRef.current = requestAnimationFrame(animate);
    };
    
    animationRef.current = requestAnimationFrame(animate);
    
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [speaker, audioLevel, outputAudioLevel]);
  
  const generateWavePath = () => {
    const width = 750;
    const height = 100;
    const centerY = height / 2;
    const frequency = 0.02;
    const points = 100;
    
    let path = `M 0 ${centerY}`;
    
    for (let i = 0; i <= points; i++) {
      const x = (i / points) * width;
      const y = centerY + Math.sin((x * frequency + waveOffset * 0.1)) * amplitude;
      path += ` L ${x} ${y}`;
    }
    
    return path;
  };

  // Secondary wave
  const generateSecondaryWave = () => {
    const width = 750;
    const height = 100;
    const centerY = height / 2;
    const frequency = 0.025;
    const points = 100;
    
    let path = `M 0 ${centerY}`;
    
    for (let i = 0; i <= points; i++) {
      const x = (i / points) * width;
      const y = centerY + Math.sin((x * frequency + waveOffset * 0.12)) * (amplitude * 0.6);
      path += ` L ${x} ${y}`;
    }
    
    return path;
  };

  // Wave rendering
  const generateMultipleWaves = () => {
    const waves = [];
    
    let baseColor, opacity;
    if (speaker === "User") {
      baseColor = "#ef4444";
      opacity = 0.8;
    } else if (speaker === "Assistant") {
      baseColor = "#67d8ef";
      opacity = 0.8;
    } else {
      baseColor = "#3b82f6";
      opacity = 0.4;
    }
    
    // Main wave
    waves.push(
      <path
        key="wave1"
        d={generateWavePath()}
        stroke={baseColor}
        strokeWidth={speaker ? "3" : "2"}
        fill="none"
        opacity={opacity}
        strokeLinecap="round"
      />
    );
    
    // Secondary wave
    waves.push(
      <path
        key="wave2"
        d={generateSecondaryWave()}
        stroke={baseColor}
        strokeWidth={speaker ? "2" : "1.5"}
        fill="none"
        opacity={opacity * 0.5}
        strokeLinecap="round"
      />
    );
    
    return waves;
  };
  
  return (
    <div style={styles.waveformContainer}>
      <svg style={styles.waveformSvg} viewBox="0 0 750 80" preserveAspectRatio="xMidYMid meet">
        {generateMultipleWaves()}
      </svg>
      
      {/* Audio level indicators for debugging */}
      {window.location.hostname === 'localhost' && (
        <div style={{
          position: 'absolute',
          bottom: '-25px',
          left: '50%',
          transform: 'translateX(-50%)',
          fontSize: '10px',
          color: '#666',
          whiteSpace: 'nowrap'
        }}>
          Input: {(audioLevel * 100).toFixed(1)}% | Amp: {amplitude.toFixed(1)}
        </div>
      )}
    </div>
  );
};

/* ------------------------------------------------------------------ *
 *  CHAT BUBBLE
 * ------------------------------------------------------------------ */
const ChatBubble = ({ message }) => {
  const { speaker, text, isTool, streaming } = message;
  const isUser = speaker === "User";
  const isSpecialist = speaker?.includes("Specialist");
  const isAuthAgent = speaker === "Auth Agent";
  
  if (isTool) {
    return (
      <div style={{ ...styles.assistantMessage, alignSelf: "center" }}>
        <div style={{
          ...styles.assistantBubble,
          background: "#8b5cf6",
          textAlign: "center",
          fontSize: "14px",
        }}>
          {text}
        </div>
      </div>
    );
  }
  
  const bubbleStyle = isUser ? styles.userBubble : styles.assistantBubble;

  return (
    <div style={isUser ? styles.userMessage : styles.assistantMessage}>
      {/* Show agent name for specialist agents and auth agent */}
      {!isUser && (isSpecialist || isAuthAgent) && (
        <div style={styles.agentNameLabel}>
          {speaker}
        </div>
      )}
      <div style={bubbleStyle}>
        {text.split("\n").map((line, i) => (
          <div key={i}>{line}</div>
        ))}
        {streaming && <span style={{ opacity: 0.7 }}>▌</span>}
      </div>
    </div>
  );
};

// Main voice application component
function RealTimeVoiceApp() {
  
  // CSS animation for pulsing effect
  React.useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
        100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
      }
    `;
    document.head.appendChild(style);
    
    return () => {
      document.head.removeChild(style);
    };
  }, []);

  // Component state
  const [messages, setMessages] = useState([]);
  const [log, setLog] = useState("");
  const [recording, setRecording] = useState(false);
  const [targetPhoneNumber, setTargetPhoneNumber] = useState("");
  const [callActive, setCallActive] = useState(false);
  const [activeSpeaker, setActiveSpeaker] = useState(null);
  const [showPhoneInput, setShowPhoneInput] = useState(false);
  const [systemStatus, setSystemStatus] = useState({
    status: "checking",
    acsOnlyIssue: false,
  });
  const handleSystemStatus = useCallback((nextStatus) => {
    setSystemStatus((prev) =>
      prev.status === nextStatus.status && prev.acsOnlyIssue === nextStatus.acsOnlyIssue
        ? prev
        : nextStatus
    );
  }, []);

  // Tooltip states
  const [showResetTooltip, setShowResetTooltip] = useState(false);
  const [showMicTooltip, setShowMicTooltip] = useState(false);
  const [showPhoneTooltip, setShowPhoneTooltip] = useState(false);

  // Hover states
  const [resetHovered, setResetHovered] = useState(false);
  const [micHovered, setMicHovered] = useState(false);
  const [phoneHovered, setPhoneHovered] = useState(false);
  const [phoneDisabledPos, setPhoneDisabledPos] = useState(null);
  const isCallDisabled =
    systemStatus.status === "degraded" && systemStatus.acsOnlyIssue;

  useEffect(() => {
    if (isCallDisabled) {
      setShowPhoneInput(false);
    } else if (phoneDisabledPos) {
      setPhoneDisabledPos(null);
    }
  }, [isCallDisabled, phoneDisabledPos]);

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
  const phoneButtonRef = useRef(null);

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
  const terminationReasonRef = useRef(null);
  const resampleWarningRef = useRef(false);
  const shouldReconnectRef = useRef(false);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  
  const [audioLevel, setAudioLevel] = useState(0);
  const audioLevelRef = useRef(0);
  const metricsRef = useRef(createMetricsState());

  const workletSource = `
    class PcmSink extends AudioWorkletProcessor {
      constructor() {
        super();
        this.queue = [];
        this.readIndex = 0;
        this.samplesProcessed = 0;
        this.port.onmessage = (e) => {
          if (e.data?.type === 'push') {
            // payload is Float32Array
            this.queue.push(e.data.payload);
          } else if (e.data?.type === 'clear') {
            // Clear all queued audio data for immediate interruption
            this.queue = [];
            this.readIndex = 0;
          }
        };
      }
      process(inputs, outputs) {
        const out = outputs[0][0]; // mono
        let i = 0;
        while (i < out.length) {
          if (this.queue.length === 0) {
            // no data: output silence
            for (; i < out.length; i++) out[i] = 0;
            break;
          }
          const chunk = this.queue[0];
          const remain = chunk.length - this.readIndex;
          const toCopy = Math.min(remain, out.length - i);
          out.set(chunk.subarray(this.readIndex, this.readIndex + toCopy), i);
          i += toCopy;
          this.readIndex += toCopy;
          if (this.readIndex >= chunk.length) {
            this.queue.shift();
            this.readIndex = 0;
          }
        }
        this.samplesProcessed += out.length;
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

  // Initialize playback audio context and worklet (call on user gesture)
  const initializeAudioPlayback = async () => {
    if (playbackAudioContextRef.current) return; // Already initialized
    
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
      
      // Resume on user gesture
      await audioCtx.resume();
      
      playbackAudioContextRef.current = audioCtx;
      pcmSinkRef.current = sink;
      
      appendLog("🔊 Audio playback initialized");
      logger.info("AudioWorklet playback system initialized, context sample rate:", audioCtx.sampleRate);
    } catch (error) {
      logger.error("Failed to initialize audio playback:", error);
      appendLog("❌ Audio playback init failed");
    }
  };


  const appendLog = useCallback((message) => {
    setLog(prev => `${prev}\n${new Date().toLocaleTimeString()} - ${message}`);
  }, []);

  const publishMetricsSummary = useCallback(
    (label, detail) => {
      if (!label) {
        return;
      }

      let formatted = null;
      if (typeof detail === "string") {
        formatted = detail;
        logger.info(`[Metrics] ${label}: ${detail}`);
      } else if (detail && typeof detail === "object") {
        const entries = Object.entries(detail).filter(([, value]) => value !== undefined && value !== null && value !== "");
        formatted = entries
          .map(([key, value]) => `${key}=${value}`)
          .join(" • ");
        logger.info(`[Metrics] ${label}`, detail);
      } else {
        logger.info(`[Metrics] ${label}`, metricsRef.current);
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

  useEffect(()=>{
    if(messageContainerRef.current) {
      messageContainerRef.current.scrollTo({
        top: messageContainerRef.current.scrollHeight,
        behavior: 'smooth'
      });
    } else if(chatRef.current) {
      chatRef.current.scrollTo({
        top: chatRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  },[messages]);

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
    };
  }, []);

  useEffect(()=>{
    if (log.includes("Call connected"))  setCallActive(true);
    if (log.includes("Call ended"))      setCallActive(false);
  },[log]);

  const startRecognition = async () => {
      setMessages([]);
      appendLog("🎤 PCM streaming started");

      await initializeAudioPlayback();

      const sessionId = getOrCreateSessionId();
      resetMetrics(sessionId);
      assistantStreamGenerationRef.current = 0;
      terminationReasonRef.current = null;
      resampleWarningRef.current = false;
      shouldReconnectRef.current = true;
      reconnectAttemptsRef.current = 0;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      logger.info('🔗 [FRONTEND] Starting conversation WebSocket with session_id:', sessionId);

      const connectSocket = (isReconnect = false) => {
        const ws = new WebSocket(`${WS_URL}/api/v1/realtime/conversation?session_id=${sessionId}`);
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
          appendLog(isReconnect ? "🔌 WS reconnected - Connected to backend!" : "🔌 WS open - Connected to backend!");
          logger.info(
            "WebSocket connection %s to backend at:",
            isReconnect ? "RECONNECTED" : "OPENED",
            `${WS_URL}/api/v1/realtime/conversation`,
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

        ws.onmessage = handleSocketMessage;
        socketRef.current = ws;
        return ws;
      };

      connectSocket(false);

      // 2) setup Web Audio for raw PCM @16 kHz
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
        
        // Calculate real-time audio level
        let sum = 0;
        for (let i = 0; i < float32.length; i++) {
          sum += float32[i] * float32[i];
        }
        const rms = Math.sqrt(sum / float32.length);
        const level = Math.min(1, rms * 10); // Scale and clamp to 0-1
        
        audioLevelRef.current = level;
        setAudioLevel(level);

        // Debug: Log a sample of mic data

        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          int16[i] = Math.max(-1, Math.min(1, float32[i])) * 0x7fff;
        }

        // Debug: Show size before send
        // logger.debug("Sending int16 PCM buffer, length:", int16.length);

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
      
      // Add session stopped message instead of clearing everything
      setMessages(m => [...m, { 
        speaker: "System", 
        text: "🛑 Session stopped" 
      }]);
      setActiveSpeaker("System");
      setRecording(false);
      appendLog("🛑 PCM streaming stopped");
    };

    const pushIfChanged = (arr, msg) => {
      if (arr.length === 0) return [...arr, msg];
      const last = arr[arr.length - 1];
      if (last.speaker === msg.speaker && last.text === msg.text) return arr;
      return [...arr, msg];
    };

    const handleSocketMessage = async (event) => {
      // Log all incoming messages for debugging
      if (typeof event.data === "string") {
        try {
          const msg = JSON.parse(event.data);
          logger.debug("📨 WebSocket message received:", msg.type || "unknown", msg);
        } catch (e) {
          logger.debug("📨 Non-JSON WebSocket message:", event.data);
          logger.debug(e)
        }
      } else {
        logger.debug("📨 Binary WebSocket message received, length:", event.data.byteLength);
      }

      if (typeof event.data !== "string") {
        const ctx = new AudioContext();
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
        logger.debug("📨 Received envelope message:", {
          type: payload.type,
          sender: payload.sender,
          topic: payload.topic,
          session_id: payload.session_id
        });
        
        // Extract the actual message from the envelope
        const envelopeType = payload.type;
        const envelopeSender = payload.sender;
        const actualPayload = payload.payload;
        
        // Transform envelope back to legacy format for compatibility
        if (envelopeType === "event" && actualPayload.message) {
          // Status/chat message in envelope
          payload = {
            type: "assistant",
            sender: envelopeSender,
            speaker: envelopeSender,
            message: actualPayload.message,
            content: actualPayload.message
          };
        } else if (envelopeType === "assistant_streaming" && actualPayload.content) {
          // Streaming response in envelope
          payload = {
            type: "assistant_streaming",
            sender: envelopeSender,
            speaker: envelopeSender,
            content: actualPayload.content
          };
        } else if (envelopeType === "status" && actualPayload.message) {
          // Status message in envelope
          payload = {
            type: "status",
            sender: envelopeSender,
            speaker: envelopeSender,
            message: actualPayload.message,
            content: actualPayload.message
          };
        } else {
          // For other envelope types, use the payload directly
          payload = {
            ...actualPayload,
            sender: envelopeSender,
            speaker: envelopeSender
          };
        }
        
        logger.debug("📨 Transformed envelope to legacy format:", payload);
      }

      if (payload.type === "session_end") {
        const reason = payload.reason || "UNKNOWN";
        terminationReasonRef.current = reason;
        if (reason === "HUMAN_HANDOFF") {
          shouldReconnectRef.current = false;
        }
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
        appendLog(`⚠️ Session ended (${reason})`);
        playbackActiveRef.current = false;
        if (pcmSinkRef.current) {
          pcmSinkRef.current.port.postMessage({ type: "clear" });
        }
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

        if (partialText) {
          let registeredTurn = false;
          setMessages((prev) => {
            const last = prev.at(-1);
            if (last?.speaker === "User" && last?.streaming) {
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
              },
            ];
          });

          if (registeredTurn) {
            registerUserTurn(partialText);
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
        setMessages((prev) =>
          pushIfChanged(prev, { speaker: "System", text: transferText })
        );
        setActiveSpeaker("System");
        appendLog("🤝 Escalated to live agent");
        return;
      }
      
      // Handle audio_data messages from backend TTS
      if (payload.type === "audio_data" && payload.data) {
        try {
          logger.debug("🔊 Received audio_data message:", {
            frame_index: payload.frame_index,
            total_frames: payload.total_frames,
            sample_rate: payload.sample_rate,
            data_length: payload.data.length,
            is_final: payload.is_final
          });

          registerAudioFrame(payload.frame_index, payload.is_final === true);

          const isFinalChunk =
            payload.is_final === true ||
            (Number.isFinite(payload.total_frames) &&
              Number.isFinite(payload.frame_index) &&
              payload.frame_index + 1 >= payload.total_frames);

          // Decode base64 -> Int16 -> Float32 [-1, 1]
          const bstr = atob(payload.data);
          const buf = new ArrayBuffer(bstr.length);
          const view = new Uint8Array(buf);
          for (let i = 0; i < bstr.length; i++) view[i] = bstr.charCodeAt(i);
          const int16 = new Int16Array(buf);
          const float32 = new Float32Array(int16.length);
          for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x8000;

          logger.debug(`🔊 Processing TTS audio chunk: ${float32.length} samples, sample_rate: ${payload.sample_rate || 16000}`);
          logger.debug("🔊 Audio data preview:", float32.slice(0, 10));

          // Push to the worklet queue
          if (pcmSinkRef.current) {
            let samples = float32;
            const playbackCtx = playbackAudioContextRef.current;
            const sourceRate = payload.sample_rate;
            if (playbackCtx && Number.isFinite(sourceRate) && sourceRate && playbackCtx.sampleRate !== sourceRate) {
              samples = resampleFloat32(float32, sourceRate, playbackCtx.sampleRate);
              if (!resampleWarningRef.current) {
                appendLog(`🎚️ Resampling audio ${sourceRate}Hz → ${playbackCtx.sampleRate}Hz`);
                resampleWarningRef.current = true;
              }
            }
            pcmSinkRef.current.port.postMessage({ type: 'push', payload: samples });
            appendLog(`🔊 TTS audio frame ${payload.frame_index + 1}/${payload.total_frames}`);
          } else {
            logger.warn("Audio playback not initialized, attempting init...");
            appendLog("⚠️ Audio playback not ready, initializing...");
            // Try to initialize if not done yet
            await initializeAudioPlayback();
            if (pcmSinkRef.current) {
              let samples = float32;
              const playbackCtx = playbackAudioContextRef.current;
              const sourceRate = payload.sample_rate;
              if (playbackCtx && Number.isFinite(sourceRate) && sourceRate && playbackCtx.sampleRate !== sourceRate) {
                samples = resampleFloat32(float32, sourceRate, playbackCtx.sampleRate);
                if (!resampleWarningRef.current) {
                  appendLog(`🎚️ Resampling audio ${sourceRate}Hz → ${playbackCtx.sampleRate}Hz`);
                  resampleWarningRef.current = true;
                }
              }
              pcmSinkRef.current.port.postMessage({ type: 'push', payload: samples });
              appendLog("🔊 TTS audio playing (after init)");
            } else {
              logger.error("Failed to initialize audio playback");
              appendLog("❌ Audio init failed");
            }
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
      const { type, content = "", message = "", speaker } = payload;
      const txt = content || message;
      const msgType = (type || "").toLowerCase();

      if (msgType === "user" || speaker === "User") {
        setActiveSpeaker("User");
        setMessages((prev) => {
          const last = prev.at(-1);
          if (last?.speaker === "User" && last?.streaming) {
            return prev.map((m, i) =>
              i === prev.length - 1 ? { ...m, text: txt, streaming: false } : m,
            );
          }
          return [...prev, { speaker: "User", text: txt }];
        });
        appendLog(`User: ${txt}`);
        return;
      }

      if (type === "assistant_streaming") {
        const streamingSpeaker = speaker || "Assistant";
        const streamGeneration = assistantStreamGenerationRef.current;
        registerAssistantStreaming(streamingSpeaker);
        setActiveSpeaker(streamingSpeaker);
        setMessages(prev => {
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
            },
          ];
        });
        const pending = metricsRef.current?.pendingBargeIn;
        if (pending) {
          finalizeBargeInClear(pending);
        }
        return;
      }

      if (msgType === "assistant" || msgType === "status" || speaker === "Assistant") {
        const assistantSpeaker = speaker || "Assistant";
        registerAssistantFinal(assistantSpeaker);
        setActiveSpeaker("Assistant");
        setMessages(prev => {
          const latest = prev.at(-1);
          if (
            latest?.streaming &&
            latest?.speaker === assistantSpeaker
          ) {
            return prev.map((m, i) =>
              i === prev.length - 1
                ? {
                    ...m,
                    text: txt,
                    streaming: false,
                  }
                : m,
            );
          }
          return pushIfChanged(prev, {
            speaker: assistantSpeaker,
            text: txt,
          });
        });

        appendLog("🤖 Assistant responded");
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
      
        appendLog(`⚙️ ${payload.tool} started`);
        return;
      }
      
    
      if (type === "tool_progress") {
        setMessages((prev) =>
          prev.map((m, i, arr) =>
            i === arr.length - 1 && m.text.startsWith(`🛠️ tool ${payload.tool}`)
              ? { ...m, text: `🛠️ tool ${payload.tool} ${payload.pct}% 🔄` }
              : m,
          ),
        );
        appendLog(`⚙️ ${payload.tool} ${payload.pct}%`);
        return;
      }
    
      if (type === "tool_end") {

      
        const finalText =
          payload.status === "success"
            ? `🛠️ tool ${payload.tool} completed ✔️\n${JSON.stringify(
                payload.result,
                null,
                2,
              )}`
            : `🛠️ tool ${payload.tool} failed ❌\n${payload.error}`;
      
        setMessages((prev) =>
          prev.map((m, i, arr) =>
            i === arr.length - 1 && m.text.startsWith(`🛠️ tool ${payload.tool}`)
              ? { ...m, text: finalText }
              : m,
          ),
        );
      
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
  
  /* ------------------------------------------------------------------ *
   *  OUTBOUND ACS CALL
   * ------------------------------------------------------------------ */
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
      logger.info('📞 [FRONTEND] Initiating phone call with session_id:', currentSessionId);
      logger.debug('📞 [FRONTEND] This session_id will be sent to backend for call mapping');
      
      const res = await fetch(`${API_BASE_URL}/api/v1/calls/initiate`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ 
          target_number: targetPhoneNumber,
          context: {
            browser_session_id: currentSessionId  // 🎯 CRITICAL: Pass browser session ID for ACS coordination
          }
        }),
      });
      const json = await res.json();
      if (!res.ok) {
        appendLog(`Call error: ${json.detail||res.statusText}`);
        return;
      }
      // show in chat
      setMessages(m => [
        ...m,
        { speaker:"Assistant", text:`📞 Call started → ${targetPhoneNumber}` }
      ]);
      appendLog("📞 Call initiated");

      // relay WS WITH session_id to monitor THIS session (including phone calls)
      logger.info('🔗 [FRONTEND] Starting dashboard relay WebSocket to monitor session:', currentSessionId);
      const relay = new WebSocket(`${WS_URL}/api/v1/realtime/dashboard/relay?session_id=${currentSessionId}`);
      relay.onopen = () => appendLog("Relay WS connected");
      relay.onmessage = ({data}) => {
        try {
          const obj = JSON.parse(data);
          
          // Handle envelope format for relay messages
          let processedObj = obj;
          if (obj.type && obj.sender && obj.payload && obj.ts) {
            logger.debug("📨 Relay received envelope message:", {
              type: obj.type,
              sender: obj.sender,
              topic: obj.topic
            });
            
            // Extract actual message from envelope
            if (obj.payload.message) {
              processedObj = {
                type: obj.type,
                sender: obj.sender,
                message: obj.payload.message
              };
            } else if (obj.payload.text) {
              processedObj = {
                type: obj.type,
                sender: obj.sender,
                message: obj.payload.text
              };
            } else {
              // Fallback to using the whole payload as message
              processedObj = {
                type: obj.type,
                sender: obj.sender,
                message: JSON.stringify(obj.payload)
              };
            }
            logger.debug("📨 Transformed relay envelope:", processedObj);
          }
          
          if (processedObj.type?.startsWith("tool_")) {
            handleSocketMessage({ data: JSON.stringify(processedObj) });
            return;
          }
          const { sender, message } = processedObj;
          if (sender && message) {
            setMessages(m => [...m, { speaker: sender, text: message }]);
            setActiveSpeaker(sender);
            appendLog(`[Relay] ${sender}: ${message}`);
          }
        } catch (error) {
          logger.error("Relay parse error:", error);
          appendLog("Relay parse error");
        }
      };
      relay.onclose = () => {
        appendLog("Relay WS disconnected");
        setCallActive(false);
        setActiveSpeaker(null);
      };
    } catch(e) {
      appendLog(`Network error starting call: ${e.message}`);
    }
  };

  /* ------------------------------------------------------------------ *
   *  RENDER
   * ------------------------------------------------------------------ */
  return (
    <div style={styles.root}>
      <div style={styles.mainContainer}>
        {/* Backend Status Indicator */}
        <BackendIndicator url={API_BASE_URL} onStatusChange={handleSystemStatus} />

        {/* App Header */}
        <div style={styles.appHeader}>
          <div style={styles.appTitleContainer}>
            <div style={styles.appTitleWrapper}>
              <span style={styles.appTitleIcon}>🎙️</span>
              <h1 style={styles.appTitle}>ARTAgent</h1>
            </div>
            <p style={styles.appSubtitle}>Transforming customer interactions with real-time, intelligent voice interactions</p>
            <div style={{
              fontSize: '10px',
              color: '#94a3b8',
              marginTop: '4px',
              fontFamily: 'monospace',
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}>
              <span>💬</span>
              <span>Session: {getOrCreateSessionId()}</span>
            </div>
          </div>
          {/* Top Right Help Button */}
          <HelpButton />
        </div>

        {/* Waveform Section */}
        <div style={styles.waveformSection}>
          <div style={styles.waveformSectionTitle}>Voice Activity</div>
          <WaveformVisualization 
            isActive={recording} 
            speaker={activeSpeaker} 
            audioLevel={audioLevel}
            outputAudioLevel={0}
          />
          <div style={styles.sectionDivider}></div>
        </div>

        {/* Chat Messages */}
        <div style={styles.chatSection} ref={chatRef}>
          <div style={styles.chatSectionIndicator}></div>
          <div style={styles.messageContainer} ref={messageContainerRef}>
            {messages.map((message, index) => (
              <ChatBubble key={index} message={message} />
            ))}
          </div>
        </div>

        {/* Control Buttons - Clean 3-button layout */}
        <div style={styles.controlSection}>
          <div style={styles.controlContainer}>
            
            {/* LEFT: Reset/Restart Session Button */}
            <div style={{ position: 'relative' }}>
              <button
                style={styles.resetButton(false, resetHovered)}
                onMouseEnter={() => {
                  setShowResetTooltip(true);
                  setResetHovered(true);
                }}
                onMouseLeave={() => {
                  setShowResetTooltip(false);
                  setResetHovered(false);
                }}
                onClick={() => {
                  // Reset entire session - clear chat and restart with new session ID
                  const newSessionId = createNewSessionId();
                  
                  // Close existing WebSocket if connected
                  if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
                    logger.info('🔌 Closing WebSocket for session reset...');
                    socketRef.current.close();
                  }
                  
                  // Reset UI state
                  setMessages([]);
                  setActiveSpeaker(null);
                  stopRecognition();
                  setCallActive(false);
                  setShowPhoneInput(false);
                  appendLog(`🔄️ Session reset - new session ID: ${newSessionId.split('_')[1]}`);
                  
                  // Add welcome message
                  setTimeout(() => {
                    setMessages([{ 
                      speaker: "System", 
                      text: "✅ Session restarted with new ID. Ready for a fresh conversation!" 
                    }]);
                  }, 500);
                }}
              >
                ⟲
              </button>
              
              {/* Tooltip */}
              <div 
                style={{
                  ...styles.buttonTooltip,
                  ...(showResetTooltip ? styles.buttonTooltipVisible : {})
                }}
              >
                Reset conversation & start fresh
              </div>
            </div>

            {/* MIDDLE: Microphone Button */}
            <div style={{ position: 'relative' }}>
              <button
                style={styles.micButton(recording, micHovered)}
                onMouseEnter={() => {
                  setShowMicTooltip(true);
                  setMicHovered(true);
                }}
                onMouseLeave={() => {
                  setShowMicTooltip(false);
                  setMicHovered(false);
                }}
                onClick={recording ? stopRecognition : startRecognition}
              >
                {recording ? "🛑" : "🎤"}
              </button>
              
              {/* Tooltip */}
              <div 
                style={{
                  ...styles.buttonTooltip,
                  ...(showMicTooltip ? styles.buttonTooltipVisible : {})
                }}
              >
                {recording ? "Stop recording your voice" : "Start voice conversation"}
              </div>
            </div>

            {/* RIGHT: Phone Call Button */}
            <div 
              style={{ position: 'relative' }}
              onMouseEnter={() => {
                setShowPhoneTooltip(true);
                if (isCallDisabled && phoneButtonRef.current) {
                  const rect = phoneButtonRef.current.getBoundingClientRect();
                  setPhoneDisabledPos({
                    top: rect.bottom + 12,
                    left: rect.left + rect.width / 2,
                  });
                }
                if (!isCallDisabled) {
                  setPhoneHovered(true);
                }
              }}
              onMouseLeave={() => {
                setShowPhoneTooltip(false);
                setPhoneHovered(false);
                setPhoneDisabledPos(null);
              }}
            >
              <button
                ref={phoneButtonRef}
                style={styles.phoneButton(callActive, phoneHovered, isCallDisabled)}
                disabled={isCallDisabled}
                title={
                  isCallDisabled
                    ? undefined
                    : callActive
                      ? "Hang up the phone call"
                      : "Make a phone call"
                }
                onClick={() => {
                  if (isCallDisabled) {
                    return;
                  }
                  if (callActive) {
                    // Hang up call
                    stopRecognition();
                    setCallActive(false);
                    setMessages(prev => [...prev, { 
                      speaker: "System",
                      text: "📞 Call ended" 
                    }]);
                  } else {
                    // Show phone input
                    setShowPhoneInput(!showPhoneInput);
                  }
                }}
              >
                {callActive ? "📵" : "📞"}
              </button>
              
              {/* Tooltip */}
              {!isCallDisabled && (
                <div 
                  style={{
                    ...styles.buttonTooltip,
                    ...(showPhoneTooltip ? styles.buttonTooltipVisible : {})
                  }}
                >
                  {callActive ? "Hang up the phone call" : "Make a phone call"}
                </div>
              )}
              {isCallDisabled && showPhoneTooltip && phoneDisabledPos && (
                <div
                  style={{
                    ...styles.phoneDisabledDialog,
                    top: phoneDisabledPos.top,
                    left: phoneDisabledPos.left,
                  }}
                >
                  ⚠️ Outbound calling is disabled. Update backend .env with Azure Communication Services settings (ACS_CONNECTION_STRING, ACS_SOURCE_PHONE_NUMBER, ACS_ENDPOINT) to enable this feature.
                </div>
              )}
            </div>

          </div>
        </div>

        {/* Phone Input Panel */}
      {showPhoneInput && (
        <div style={styles.phoneInputSection}>
          <div style={{ marginBottom: '8px', fontSize: '12px', color: '#64748b' }}>
            {callActive ? '📞 Call in progress' : '📞 Enter your phone number to get a call'}
          </div>
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
      )}
      </div>
    </div>
  );
}

// Main App component wrapper
function App() {
  return <RealTimeVoiceApp />;
}

export default App;
