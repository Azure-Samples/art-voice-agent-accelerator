import React, { useEffect, useRef, useState } from 'react';
import BackendHelpButton from './BackendHelpButton.jsx';
import { styles } from '../styles/voiceAppStyles.js';
import { useBackendHealth } from '../hooks/useBackendHealth.js';

const BackendIndicator = ({ url, onConfigureClick, onStatusChange, onAgentSelect, compact = false }) => {
  const [displayUrl, setDisplayUrl] = useState(url);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isClickedOpen, setIsClickedOpen] = useState(false);
  const [showComponentDetails, setShowComponentDetails] = useState(false);
  const [screenWidth, setScreenWidth] = useState(window.innerWidth);
  const [showAgentConfig, setShowAgentConfig] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState(null);
  // const [configChanges, setConfigChanges] = useState({});
  // const [updateStatus, setUpdateStatus] = useState({});
  // const [showStatistics, setShowStatistics] = useState(false);
  const [showAcsHover, setShowAcsHover] = useState(false);
  const [acsTooltipPos, setAcsTooltipPos] = useState(null);
  const [revealApiUrl, setRevealApiUrl] = useState(false);
  const [showPanel, setShowPanel] = useState(false);
  const summaryRef = useRef(null);
  const buttonRef = useRef(null);

  const { readinessData, agentsData, healthData, error, overallStatus, acsOnlyIssue } =
    useBackendHealth(url);

  // Track screen width for responsive positioning
  useEffect(() => {
    const handleResize = () => setScreenWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // // Update agent configuration
  // const updateAgentConfig = async (agentName, config) => {
  //   try {
  //     setUpdateStatus({...updateStatus, [agentName]: 'updating'});
      
  //     const response = await fetch(`${url}/api/v1/agents/${agentName}`, {
  //       method: 'PUT',
  //       headers: {
  //         'Content-Type': 'application/json',
  //       },
  //       body: JSON.stringify(config),
  //     });

  //     if (!response.ok) {
  //       throw new Error(`HTTP ${response.status}`);
  //     }

  //     const data = await response.json();
      
  //     setUpdateStatus({...updateStatus, [agentName]: 'success'});
      
  //     // Refresh agents data
  //     checkAgents();
      
  //     // Clear success status after 3 seconds
  //     setTimeout(() => {
  //       setUpdateStatus(prev => {
  //         const newStatus = {...prev};
  //         delete newStatus[agentName];
  //         return newStatus;
  //       });
  //     }, 3000);
      
  //     return data;
  //   } catch (err) {
  //     logger.error("Agent config update failed:", err);
  //     setUpdateStatus({...updateStatus, [agentName]: 'error'});
      
  //     // Clear error status after 5 seconds
  //     setTimeout(() => {
  //       setUpdateStatus(prev => {
  //         const newStatus = {...prev};
  //         delete newStatus[agentName];
  //         return newStatus;
  //       });
  //     }, 5000);
      
  //     throw err;
  //   }
  // };

  useEffect(() => {
    try {
      const urlObj = new URL(url);
      const host = urlObj.hostname;
      const protocol = urlObj.protocol.replace(':', '');
      
      if (host.includes('.azurecontainerapps.io')) {
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
  }, [url]);

  const readinessChecks = readinessData?.checks ?? [];
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
    rt_agents: "🤖",
    auth_configuration: "🔐",
    app_configuration: "⚙️",
  };

  // Component descriptions
  const componentDescriptions = {
    redis: "Redis Cache - Session & state management",
    azure_openai: "Azure OpenAI - GPT models & embeddings",
    speech_services: "Speech Services - STT/TTS processing",
    acs_caller: "Communication Services - Voice calling",
    rt_agents: "RT Agents - Real-time Voice Agents",
    auth_configuration: "Authentication config (client IDs, tenant IDs, allowed callers)",
    app_configuration: "Azure App Configuration (feature flags, secrets, and settings)",
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

  const maskApiUrl = (value) => {
    if (!value) {
      return "";
    }
    try {
      const parsed = new URL(value);
      const protocol = parsed.protocol.replace(":", "");
      const hostParts = parsed.hostname.split(".");
      const primary = hostParts.shift() || "";
      const maskSegment = (segment) => {
        if (segment.length <= 3) {
          return "•".repeat(segment.length || 3);
        }
        const prefix = segment.slice(0, 2);
        const suffix = segment.slice(-2);
        const middle = "•".repeat(Math.max(segment.length - 4, 2));
        return `${prefix}${middle}${suffix}`;
      };
      const maskedPrimary = maskSegment(primary);
      const maskedHost = hostParts.length > 0 ? `${maskedPrimary}.${hostParts.join(".")}` : maskedPrimary;
      const path = parsed.pathname && parsed.pathname !== "/" ? "/…" : "/";
      return `${protocol}://${maskedHost}${path}`;
    } catch {
      const safe = String(value);
      if (safe.length <= 4) {
        return "•".repeat(safe.length);
      }
      return `${safe.slice(0, 2)}${"•".repeat(Math.max(safe.length - 4, 2))}${safe.slice(-2)}`;
    }
  };

  const displayedApiUrl = revealApiUrl ? url : maskApiUrl(url);
  const maskToggleStyle = revealApiUrl
    ? { ...styles.maskToggleButton, ...styles.maskToggleButtonActive }
    : styles.maskToggleButton;

  // Compact sidebar button mode
  if (compact) {
    const statusColor = overallStatus === "healthy" ? '#10b981' : 
                       overallStatus === "degraded" ? '#f59e0b' : '#ef4444';
    const statusBgColor = overallStatus === "healthy" ? 'rgba(16,185,129,0.08)' : 
                         overallStatus === "degraded" ? 'rgba(245,158,11,0.08)' : 'rgba(239,68,68,0.08)';
    const statusIcon = overallStatus === "healthy" ? '✓' : 
                      overallStatus === "degraded" ? '⚠' : '✕';
    
    return (
      <>
        <button
          ref={buttonRef}
          onClick={() => setShowPanel((prev) => !prev)}
          title="Backend Status"
          style={{
            width: '44px',
            height: '44px',
            borderRadius: '12px',
            border: '1px solid rgba(226,232,240,0.6)',
            background: 'linear-gradient(145deg, #ffffff, #fafbfc)',
            color: statusColor,
            fontSize: '16px',
            fontWeight: '600',
            cursor: 'pointer',
            transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
            boxShadow: '0 2px 8px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'translateY(-2px)';
            e.currentTarget.style.boxShadow = `0 4px 16px ${statusColor}20, inset 0 1px 0 rgba(255,255,255,0.8)`;
            e.currentTarget.style.background = `linear-gradient(135deg, ${statusBgColor}, ${statusBgColor})`;
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = '0 2px 8px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)';
            e.currentTarget.style.background = 'linear-gradient(145deg, #ffffff, #fafbfc)';
          }}
        >
          {statusIcon}
        </button>

        {/* Status Panel */}
        {showPanel && (
          <div
            data-backend-panel
            style={{
              position: 'fixed',
              left: '84px',
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'linear-gradient(145deg, rgba(255,255,255,0.98), rgba(248,250,252,0.95))',
              borderRadius: '14px',
              padding: '16px',
              boxShadow: '0 8px 32px rgba(15,23,42,0.12), 0 0 0 1px rgba(226,232,240,0.4), inset 0 1px 0 rgba(255,255,255,0.8)',
              backdropFilter: 'blur(24px)',
              WebkitBackdropFilter: 'blur(24px)',
              width: '340px',
              maxHeight: '80vh',
              overflowY: 'auto',
              zIndex: 1400,
            }}
          >
            {/* Header */}
            <div style={{
              fontSize: '14px',
              fontWeight: '600',
              color: '#1e293b',
              marginBottom: '12px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}>
              <span style={{ fontSize: '18px' }}>⚙️</span>
              Backend Status
            </div>

            {/* API Endpoint */}
            <div style={{
              padding: '10px',
              background: '#f8fafc',
              borderRadius: '8px',
              marginBottom: '12px',
              border: '1px solid #e2e8f0',
            }}>
              <div style={{
                fontSize: '11px',
                fontWeight: '600',
                color: '#475569',
                marginBottom: '6px',
              }}>
                🌐 API Endpoint
              </div>
              <div style={{
                fontSize: '10px',
                fontFamily: 'monospace',
                color: '#64748b',
                wordBreak: 'break-all',
              }}>
                {displayUrl}
              </div>
            </div>

            {/* Overall Status */}
            <div style={{
              padding: '10px',
              background: overallStatus === "healthy" ? '#f0fdf4' : 
                         overallStatus === "degraded" ? '#fffbeb' : '#fef2f2',
              borderRadius: '8px',
              marginBottom: '12px',
              border: `1px solid ${overallStatus === "healthy" ? '#bbf7d0' : 
                                  overallStatus === "degraded" ? '#fed7aa' : '#fecaca'}`,
            }}>
              <div style={{
                fontSize: '12px',
                fontWeight: '600',
                color: overallStatus === "healthy" ? '#166534' : 
                      overallStatus === "degraded" ? '#92400e' : '#dc2626',
                marginBottom: '4px',
              }}>
                {statusIcon} {overallStatus.charAt(0).toUpperCase() + overallStatus.slice(1)}
              </div>
              <div style={{
                fontSize: '10px',
                color: '#64748b',
              }}>
                {overallStatus === "healthy" && "All systems operational"}
                {overallStatus === "degraded" && "Some services degraded"}
                {overallStatus === "unhealthy" && "System experiencing issues"}
              </div>
            </div>

            {/* Components with Details */}
            {readinessData?.checks && (
              <div>
                <div style={{
                  fontSize: '11px',
                  fontWeight: '600',
                  color: '#475569',
                  marginBottom: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}>
                  <span>🔧</span>
                  Components
                </div>
                {readinessData.checks.map((check, idx) => {
                  const componentKey = (check.component || check.componentId || 'unknown').toLowerCase();
                  const status = (check.status || 'unknown').toLowerCase();
                  const isHealthy = status === "healthy";
                  const isDegraded = status === "degraded";
                  const componentName = componentKey !== 'unknown'
                    ? componentKey.replace(/_/g, ' ')
                    : 'Unknown component';
                  const description = componentDescriptions[componentKey] || '';
                  const statusIcon = isHealthy ? '✓' : isDegraded ? '⚠' : '✕';
                  const background = isHealthy ? '#f0fdf4' : isDegraded ? '#fffbeb' : '#fef2f2';
                  const border = isHealthy ? '#bbf7d0' : isDegraded ? '#fed7aa' : '#fecaca';
                  const statusColor = isHealthy ? '#166534' : isDegraded ? '#92400e' : '#dc2626';
                  const detailText = check.error || check.details;

                  return (
                    <div 
                      key={idx} 
                      style={{
                        padding: '10px',
                        background,
                        borderRadius: '8px',
                        marginBottom: '8px',
                        border: `1px solid ${border}`,
                      }}
                    >
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        marginBottom: '6px',
                      }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          fontSize: '11px',
                          fontWeight: '600',
                          color: statusColor,
                        }}>
                          <span style={{ fontSize: '14px' }}>
                            {componentIcons[componentKey] || '🔧'}
                          </span>
                          <span>{componentName}</span>
                        </div>
                        <div style={{
                          fontSize: '16px',
                          color: statusColor,
                        }}>
                          {statusIcon}
                        </div>
                      </div>
                      
                      {/* Component Description */}
                      {description && (
                        <div style={{
                          fontSize: '9px',
                          color: '#64748b',
                          marginBottom: '6px',
                          lineHeight: '1.4',
                        }}>
                          {description}
                        </div>
                      )}

                      {/* Output/Error Details */}
                      {detailText && (
                        <div style={{
                          fontSize: '9px',
                          color: statusColor,
                          marginTop: '4px',
                          fontFamily: 'monospace',
                          background: 'rgba(255,255,255,0.5)',
                          padding: '4px 6px',
                          borderRadius: '4px',
                          wordBreak: 'break-word',
                        }}>
                          {String(detailText)}
                        </div>
                      )}

                      {/* Time/Performance Info */}
                      {typeof check.check_time_ms === 'number' && (
                        <div style={{
                          fontSize: '9px',
                          color: '#64748b',
                          marginTop: '4px',
                        }}>
                          ⏱️ {Math.round(check.check_time_ms)}ms
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Health Data Summary */}
            {healthData && (
              <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #e2e8f0' }}>
                <div style={{
                  fontSize: '11px',
                  fontWeight: '600',
                  color: '#475569',
                  marginBottom: '8px',
                }}>
                  📊 Health Metrics
                </div>
                <div style={{
                  fontSize: '10px',
                  color: '#64748b',
                  background: '#f8fafc',
                  padding: '8px',
                  borderRadius: '6px',
                  border: '1px solid #e2e8f0',
                }}>
                  {healthData.status && (
                    <div style={{ marginBottom: '4px' }}>
                      Status: <strong>{healthData.status}</strong>
                    </div>
                  )}
                  {healthData.version && (
                    <div style={{ marginBottom: '4px' }}>
                      Version: <strong>{healthData.version}</strong>
                    </div>
                  )}
                  {healthData.timestamp && (
                    <div>
                      Last Check: {new Date(healthData.timestamp).toLocaleTimeString()}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Agents Summary */}
            {agentsData?.agents && agentsData.agents.length > 0 && (
              <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid #e2e8f0' }}>
                <div style={{
                  fontSize: '11px',
                  fontWeight: '600',
                  color: '#475569',
                  marginBottom: '8px',
                }}>
                  🤖 Active Agents ({agentsData.agents.length})
                </div>
                <div style={{
                  fontSize: '10px',
                  color: '#64748b',
                  background: '#f8fafc',
                  padding: '8px',
                  borderRadius: '6px',
                  border: '1px solid #e2e8f0',
                }}>
                  {agentsData.agents.map((a) => a.name).join(', ')}
                </div>
              </div>
            )}
          </div>
        )}
      </>
    );
  }

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
          {displayedApiUrl}
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
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "8px",
                  marginBottom: "6px",
                }}>
                  <div style={{
                    color: "#64748b",
                    fontSize: "9px",
                    fontFamily: "monospace",
                    padding: "3px 6px",
                    backgroundColor: "white",
                    borderRadius: "4px",
                    border: "1px solid #f1f5f9",
                    flex: "1 1 auto",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}>
                    {displayedApiUrl}
                  </div>
                  <button
                    type="button"
                    style={maskToggleStyle}
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      setRevealApiUrl((prev) => !prev);
                    }}
                  >
                    {revealApiUrl ? "Mask" : "Reveal"}
                  </button>
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
                  🤖 Agents ({agentsData.agents.length})
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

export default BackendIndicator;
