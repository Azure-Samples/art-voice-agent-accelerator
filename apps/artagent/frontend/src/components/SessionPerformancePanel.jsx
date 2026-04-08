import React, { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Box,
  Chip,
  Button,
  Divider,
  IconButton,
  Typography,
  LinearProgress,
  Alert,
} from '@mui/material';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import SpeedRoundedIcon from '@mui/icons-material/SpeedRounded';
import TimelineRoundedIcon from '@mui/icons-material/TimelineRounded';
import MemoryRoundedIcon from '@mui/icons-material/MemoryRounded';
import TrendingUpRoundedIcon from '@mui/icons-material/TrendingUpRounded';
import WarningAmberRoundedIcon from '@mui/icons-material/WarningAmberRounded';
import RecordVoiceOverRoundedIcon from '@mui/icons-material/RecordVoiceOverRounded';
import SwapCallsRoundedIcon from '@mui/icons-material/SwapCallsRounded';

const PanelCard = ({ title, icon, children, collapsible, defaultOpen = true, alert = null }) => {
  const [expanded, setExpanded] = useState(defaultOpen);

  return (
    <Box
      sx={{
        borderRadius: '16px',
        border: '1px solid rgba(226,232,240,0.6)',
        background: 'linear-gradient(145deg, #ffffff, #fafbfc)',
        boxShadow: '0 2px 8px rgba(15,23,42,0.06), inset 0 1px 0 rgba(255,255,255,0.8)',
        p: 2,
        mb: 2,
        transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        '&:hover': {
          boxShadow: '0 4px 12px rgba(15,23,42,0.08), inset 0 1px 0 rgba(255,255,255,0.8)',
        },
      }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: (collapsible && !expanded) ? 0 : 1,
          cursor: collapsible ? 'pointer' : 'default',
        }}
        onClick={() => collapsible && setExpanded(!expanded)}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {icon}
          <Typography sx={{ fontWeight: 700, color: '#0f172a', fontSize: '12px', letterSpacing: '0.5px' }}>
            {title}
          </Typography>
          {alert && (
            <Chip
              icon={<WarningAmberRoundedIcon sx={{ fontSize: 14 }} />}
              label={alert}
              size="small"
              color="warning"
              sx={{ height: 20, fontSize: '10px', fontWeight: 600 }}
            />
          )}
        </Box>
        {collapsible && (
          <Typography sx={{ fontSize: '10px', color: '#94a3b8', fontWeight: 600 }}>
            {expanded ? 'Hide' : 'Show'}
          </Typography>
        )}
      </Box>
      {(!collapsible || expanded) && children}
    </Box>
  );
};

const MetricRow = ({ label, value, unit, trend, severity = 'info' }) => {
  const severityColors = {
    success: '#22c55e',
    warning: '#f59e0b',
    error: '#ef4444',
    info: '#0ea5e9',
  };

  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.5, gap: 1 }}>
      <Typography sx={{ color: '#475569', fontWeight: 600, fontSize: '11px' }}>{label}</Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <Typography
          sx={{
            color: severityColors[severity],
            fontWeight: 700,
            fontSize: '12px',
            fontFamily: 'Monaco, Menlo, monospace'
          }}
        >
          {value}
        </Typography>
        {unit && (
          <Typography sx={{ color: '#94a3b8', fontSize: '10px', fontWeight: 600 }}>
            {unit}
          </Typography>
        )}
        {trend && (
          <TrendingUpRoundedIcon
            sx={{
              fontSize: 12,
              color: trend > 0 ? '#ef4444' : '#22c55e',
              transform: trend < 0 ? 'rotate(180deg)' : 'none'
            }}
          />
        )}
      </Box>
    </Box>
  );
};

const LatencyBar = ({ entry }) => {
  const severityColors = {
    success: '#22c55e',
    warning: '#f59e0b',
    error: '#ef4444',
    info: '#0ea5e9',
  };
  const avgMs = Number.isFinite(entry?.avg_ms) ? entry.avg_ms : 0;
  const relativePct = Number.isFinite(entry?.relative_pct) ? entry.relative_pct : 0;
  const severityColor = severityColors[entry?.severity] || severityColors.info;

  return (
    <Box sx={{ mb: 1 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
        <Typography sx={{ fontSize: '11px', fontWeight: 600, color: '#475569' }}>
          {entry?.stage || 'unknown'}
        </Typography>
        <Typography
          sx={{
            fontSize: '11px',
            fontWeight: 700,
            color: severityColor,
            fontFamily: 'Monaco, Menlo, monospace'
          }}
        >
          {avgMs.toFixed(1)}ms
        </Typography>
      </Box>
      <Box sx={{ position: 'relative', height: 6, bgcolor: '#f1f5f9', borderRadius: 3 }}>
        <Box
          sx={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: '100%',
            width: `${Math.max(relativePct, 2)}%`,
            bgcolor: severityColor,
            borderRadius: 3,
            transition: 'all 0.3s ease',
          }}
        />
      </Box>
    </Box>
  );
};

const formatEpochTimestamp = (value) => {
  if (!Number.isFinite(value)) {
    return '—';
  }
  const ms = value > 1e12 ? value : value * 1000;
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) {
    return '—';
  }
  return date.toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const formatConnectionStatus = (value) => {
  if (!value) return '—';
  const normalized = String(value);
  return normalized.charAt(0).toUpperCase() + normalized.slice(1);
};

const SessionPerformancePanel = ({
  open,
  onClose,
  sessionId,
  coreMemory = null,
  sessionMeta = null,
  sessionMetrics = null,
  scenarioConfig = null,
}) => {
  // Parse core memory data
  const performanceData = useMemo(() => {
    if (!coreMemory) return null;

    const data = {
      scenario: coreMemory.scenario_name || 'Unknown',
      activeAgent: coreMemory.active_agent || 'Unknown',
      greetingSent: coreMemory.greeting_sent || false,
      turnCount: coreMemory.cascade_turn_count || 0,
      visitedAgents: coreMemory.visited_agents || [],
      tokens: coreMemory.cascade_tokens || { input: 0, output: 0 },
      currentRunId: coreMemory.current_run_id || null,
    };
    return data;
  }, [coreMemory]);

  // Get handoffs from the active scenario
  const activeScenarioHandoffs = useMemo(() => {
    if (!scenarioConfig?.scenarios) return [];
    const activeScenario = sessionMeta?.scenarios?.find(scenario => scenario.is_active)?.name;
    const activeScenarioName = performanceData?.scenario || activeScenario;
    if (!activeScenarioName) return [];
    
    // Find matching scenario (could be custom or standard, case-insensitive)
    const scenario = scenarioConfig.scenarios.find(s => {
      const normalizedName = s.name?.toLowerCase();
      const customName = `custom_${s.name?.replace(/\s+/g, '_').toLowerCase()}`;
      const targetLower = activeScenarioName.toLowerCase();
      return normalizedName === targetLower || customName === activeScenarioName || s.name === activeScenarioName;
    });
    
    return scenario?.handoffs || [];
  }, [scenarioConfig, performanceData?.scenario, sessionMeta]);

  const latencyBreakdown = sessionMetrics?.latency_breakdown || [];
  const insights = sessionMetrics?.insights || [];
  const insightsSummary = sessionMetrics?.insights_summary || null;
  const totalLatencyEntry = latencyBreakdown.find((entry) => entry.stage === 'total') || null;

  const sessionActiveAgent = sessionMeta?.agents?.find(agent => agent.is_active)?.name || null;
  const sessionActiveScenario = sessionMeta?.scenarios?.find(scenario => scenario.is_active)?.name || null;
  const sessionTurnCount = sessionMeta?.turn_count ?? null;
  const sessionDisplayId = sessionMeta?.session_id || sessionId || '—';
  const lastActivityDisplay = sessionMeta?.last_activity
    ? formatEpochTimestamp(sessionMeta.last_activity)
    : (sessionMeta?.last_activity_readable || '—');
  const createdAtDisplay = sessionMeta?.created_at
    ? formatEpochTimestamp(sessionMeta.created_at)
    : '—';

  if (!open) return null;

  return createPortal(
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        bottom: 0,
        width: '400px',
        maxWidth: '90vw',
        background: 'linear-gradient(145deg, rgba(255,255,255,0.98), rgba(248,250,252,0.95))',
        borderRight: '1px solid rgba(226,232,240,0.4)',
        boxShadow: '8px 0 32px rgba(15,23,42,0.12), 0 0 0 1px rgba(226,232,240,0.4), inset 0 1px 0 rgba(255,255,255,0.8)',
        backdropFilter: 'blur(24px)',
        WebkitBackdropFilter: 'blur(24px)',
        zIndex: 1400,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', p: 2, pb: 1.5, cursor: 'grab' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <SpeedRoundedIcon sx={{ color: '#0ea5e9' }} fontSize="small" />
          <Box>
            <Typography sx={{ fontWeight: 800, fontSize: '15px', color: '#0f172a' }}>Session Performance (Beta)</Typography>
            <Typography sx={{ fontSize: '11px', color: '#64748b' }}>Real-time latency and bottleneck analysis</Typography>
          </Box>
        </Box>
        <IconButton size="small" onClick={onClose}>
          <CloseRoundedIcon fontSize="small" />
        </IconButton>
      </Box>
      <Divider />

      <Box
        sx={{
          p: 2,
          overflowY: 'auto',
          scrollbarWidth: 'none',
          '&::-webkit-scrollbar': { display: 'none' },
          maxHeight: '100%',
        }}
      >
        {/* Performance Alerts */}
        {insights.length > 0 && (
          <Alert
            severity={insightsSummary?.severity || 'warning'}
            sx={{ mb: 2, borderRadius: '12px' }}
            icon={<WarningAmberRoundedIcon />}
          >
            <Typography sx={{ fontWeight: 600, fontSize: '12px', mb: 0.5 }}>
              {insights.length} Performance Issue{insights.length !== 1 ? 's' : ''} Detected
            </Typography>
            {insights.slice(0, 3).map((issue, idx) => (
              <Typography key={idx} sx={{ fontSize: '11px' }}>
                • {issue.message}
              </Typography>
            ))}
          </Alert>
        )}

        {/* Session Overview */}
        <PanelCard
          title="Session Overview"
          icon={<RecordVoiceOverRoundedIcon sx={{ fontSize: 16, color: '#0ea5e9' }} />}
        >
          <MetricRow label="Scenario" value={performanceData?.scenario || sessionActiveScenario || '—'} />
          <MetricRow label="Active Agent" value={performanceData?.activeAgent || sessionActiveAgent || '—'} />
          <MetricRow label="Session ID" value={sessionDisplayId} />
          <MetricRow label="Last Activity" value={lastActivityDisplay} />
          <MetricRow label="Created" value={createdAtDisplay} />
          <MetricRow label="Connection" value={formatConnectionStatus(sessionMeta?.connection_status)} />
          <MetricRow
            label="Turn Count"
            value={(performanceData?.turnCount ?? sessionTurnCount ?? 0).toString()}
            severity={(performanceData?.turnCount ?? sessionTurnCount ?? 0) > 10 ? 'warning' : 'info'}
          />
          <MetricRow
            label="Greeting Status"
            value={performanceData?.greetingSent ? 'Sent' : 'Pending'}
            severity={performanceData?.greetingSent ? 'success' : 'warning'}
          />
          {sessionMeta && (
            <>
              <MetricRow label="User" value={sessionMeta.user_email || '—'} />
              <MetricRow label="Streaming Mode" value={sessionMeta.streaming_mode || '—'} />
              <MetricRow label="Agents" value={(sessionMeta.agents_count ?? 0).toString()} />
              <MetricRow label="Scenarios" value={(sessionMeta.scenarios_count ?? 0).toString()} />
              <MetricRow label="Custom Agents" value={(sessionMeta.custom_agents_count ?? 0).toString()} />
              <MetricRow label="Custom Scenarios" value={(sessionMeta.custom_scenarios_count ?? 0).toString()} />
              <MetricRow
                label="Profile"
                value={
                  sessionMeta.profile_name
                    ? `${sessionMeta.profile_name}${sessionMeta.profile_type ? ` (${sessionMeta.profile_type})` : ''}`
                    : '—'
                }
              />
            </>
          )}
          {performanceData?.visitedAgents?.length > 0 && (
            <Box sx={{ mt: 1 }}>
              <Typography sx={{ fontSize: '11px', fontWeight: 700, color: '#475569', mb: 0.5 }}>
                Agent Journey ({performanceData.visitedAgents.length})
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {performanceData.visitedAgents.map((agent, idx) => (
                  <Chip
                    key={idx}
                    label={agent}
                    size="small"
                    sx={{ fontSize: '10px', height: 20 }}
                  />
                ))}
              </Box>
            </Box>
          )}
        </PanelCard>

        {/* Handoff Conditions */}
        {activeScenarioHandoffs.length > 0 && (
          <PanelCard
            title="Handoff Conditions"
            icon={<SwapCallsRoundedIcon sx={{ fontSize: 16, color: '#8b5cf6' }} />}
            collapsible
            defaultOpen={true}
          >
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              {activeScenarioHandoffs.map((handoff, idx) => {
                const fromAgent = handoff.from_agent || handoff.from || '?';
                const toAgent = handoff.to_agent || handoff.to || '?';
                const condition = handoff.handoff_condition || handoff.condition;
                const toolName = handoff.tool;
                const handoffType = handoff.type;
                const shareContext = handoff.share_context;

                return (
                  <Box
                    key={idx}
                    sx={{
                      p: 1.5,
                      bgcolor: '#f8fafc',
                      borderRadius: '8px',
                      border: '1px solid rgba(226,232,240,0.6)',
                    }}
                  >
                    {/* Agent chips row */}
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                      <Chip
                        label={fromAgent}
                        size="small"
                        sx={{
                          fontSize: '10px',
                          height: 18,
                          bgcolor: '#e0f2fe',
                          color: '#0369a1',
                          fontWeight: 600,
                        }}
                      />
                      <Typography sx={{ fontSize: '10px', color: '#94a3b8' }}>→</Typography>
                      <Chip
                        label={toAgent}
                        size="small"
                        sx={{
                          fontSize: '10px',
                          height: 18,
                          bgcolor: '#dcfce7',
                          color: '#166534',
                          fontWeight: 600,
                        }}
                      />
                    </Box>

                    {/* Tool and type info */}
                    {(toolName || handoffType) && (
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1 }}>
                        {toolName && (
                          <Chip
                            label={`🔧 ${toolName}`}
                            size="small"
                            sx={{
                              fontSize: '9px',
                              height: 16,
                              bgcolor: '#fef3c7',
                              color: '#92400e',
                              fontWeight: 500,
                            }}
                          />
                        )}
                        {handoffType && (
                          <Chip
                            label={handoffType}
                            size="small"
                            sx={{
                              fontSize: '9px',
                              height: 16,
                              bgcolor: handoffType === 'discrete' ? '#dbeafe' : '#fae8ff',
                              color: handoffType === 'discrete' ? '#1e40af' : '#86198f',
                              fontWeight: 500,
                            }}
                          />
                        )}
                        {shareContext && (
                          <Chip
                            label="shares context"
                            size="small"
                            sx={{
                              fontSize: '9px',
                              height: 16,
                              bgcolor: '#d1fae5',
                              color: '#065f46',
                              fontWeight: 500,
                            }}
                          />
                        )}
                      </Box>
                    )}

                    {/* Condition text */}
                    {condition ? (
                      <Typography
                        sx={{
                          fontSize: '10px',
                          color: '#475569',
                          lineHeight: 1.5,
                          whiteSpace: 'pre-wrap',
                          bgcolor: '#fff',
                          p: 1,
                          borderRadius: '6px',
                          border: '1px solid #e2e8f0',
                        }}
                      >
                        {condition.length > 300 ? `${condition.slice(0, 300)}...` : condition}
                      </Typography>
                    ) : (
                      <Typography sx={{ fontSize: '10px', color: '#94a3b8', fontStyle: 'italic' }}>
                        No condition specified
                      </Typography>
                    )}
                  </Box>
                );
              })}
            </Box>
          </PanelCard>
        )}

        {/* Token Usage */}
        <PanelCard
          title="Token Usage"
          icon={<MemoryRoundedIcon sx={{ fontSize: 16, color: '#6366f1' }} />}
        >
          <MetricRow
            label="Input Tokens"
            value={performanceData?.tokens?.input?.toLocaleString() || '0'}
            severity={performanceData?.tokens?.input > 1000 ? 'warning' : 'info'}
          />
          <MetricRow
            label="Output Tokens"
            value={performanceData?.tokens?.output?.toLocaleString() || '0'}
            severity={performanceData?.tokens?.output > 1000 ? 'warning' : 'info'}
          />
          <MetricRow
            label="Total Tokens"
            value={((performanceData?.tokens?.input || 0) + (performanceData?.tokens?.output || 0)).toLocaleString()}
            severity="info"
          />
          {performanceData?.turnCount > 0 && (
            <MetricRow
              label="Avg Tokens/Turn"
              value={Math.round(((performanceData?.tokens?.input || 0) + (performanceData?.tokens?.output || 0)) / performanceData.turnCount).toLocaleString()}
              severity="info"
            />
          )}
        </PanelCard>

        {/* Latency Breakdown */}
        {latencyBreakdown.length > 0 && (
          <PanelCard
            title="Latency Breakdown"
            icon={<TimelineRoundedIcon sx={{ fontSize: 16, color: '#22c55e' }} />}
            alert={insights.length > 0 ? `${insights.length} issue${insights.length !== 1 ? 's' : ''}` : null}
          >
            <MetricRow
              label="Total Latency"
              value={totalLatencyEntry ? totalLatencyEntry.avg_ms.toFixed(1) : '—'}
              unit="ms"
              severity={totalLatencyEntry?.severity || 'info'}
            />
            <MetricRow
              label="Turns"
              value={sessionMetrics?.turn_count?.toString() || '0'}
            />

            <Box sx={{ mt: 1.5 }}>
              <Typography sx={{ fontSize: '11px', fontWeight: 700, color: '#475569', mb: 1 }}>
                Stage Performance
              </Typography>
              {latencyBreakdown.map((entry) => (
                <LatencyBar key={entry.stage} entry={entry} />
              ))}
            </Box>

            <Box sx={{ mt: 1.5 }}>
              <Typography sx={{ fontSize: '11px', fontWeight: 700, color: '#475569', mb: 0.5 }}>
                Stage Details
              </Typography>
              {latencyBreakdown.map((entry) => (
                <Box key={entry.stage} sx={{ mb: 1, p: 1, bgcolor: '#f8fafc', borderRadius: '8px' }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                    <Typography sx={{ fontSize: '11px', fontWeight: 600, color: '#0f172a' }}>
                      {entry.stage}
                    </Typography>
                    <Chip
                      label={`${entry.count}x`}
                      size="small"
                      sx={{ height: 16, fontSize: '10px' }}
                    />
                  </Box>
                  <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.5, fontSize: '10px' }}>
                    <MetricRow label="Avg" value={entry.avg_ms.toFixed(1)} unit="ms" />
                    <MetricRow label="Max" value={entry.max_ms.toFixed(1)} unit="ms" />
                    <MetricRow label="Min" value={entry.min_ms.toFixed(1)} unit="ms" />
                    <MetricRow
                      label="P95"
                      value={Number.isFinite(entry.p95_ms) ? entry.p95_ms.toFixed(1) : '—'}
                      unit="ms"
                    />
                  </Box>
                </Box>
              ))}
            </Box>
          </PanelCard>
        )}

        {/* Performance Insights */}
        <PanelCard
          title="Performance Insights"
          icon={<TrendingUpRoundedIcon sx={{ fontSize: 16, color: '#f59e0b' }} />}
          collapsible
          defaultOpen={insights.length > 0}
        >
          {insights.length === 0 ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1, bgcolor: '#f0fdf4', borderRadius: '8px' }}>
              <Typography sx={{ fontSize: '12px', color: '#22c55e', fontWeight: 600 }}>
                ✅ No performance issues detected
              </Typography>
            </Box>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              {insights.map((issue, idx) => (
                <Box
                  key={idx}
                  sx={{
                    p: 1,
                    bgcolor: issue.severity === 'error' ? '#fef2f2' : '#fffbeb',
                    borderRadius: '8px',
                    border: `1px solid ${issue.severity === 'error' ? '#fecaca' : '#fde68a'}`,
                  }}
                >
                  <Typography
                    sx={{
                      fontSize: '11px',
                      color: issue.severity === 'error' ? '#dc2626' : '#d97706',
                      fontWeight: 600
                    }}
                  >
                    {issue.message}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}

          <Box sx={{ mt: 1.5, p: 1, bgcolor: '#f1f5f9', borderRadius: '8px' }}>
            <Typography sx={{ fontSize: '11px', fontWeight: 600, color: '#475569', mb: 0.5 }}>
              💡 Optimization Tips
            </Typography>
            <Typography sx={{ fontSize: '10px', color: '#64748b', lineHeight: 1.4 }}>
              • Monitor STT recognition latency for audio quality issues
              <br />
              • Consider model deployment optimization for high token usage
              <br />
              • Watch for excessive agent handoffs that may confuse users
            </Typography>
          </Box>
        </PanelCard>

        {!performanceData && !sessionMetrics && (
          <Alert severity="info" sx={{ borderRadius: '12px' }}>
            <Typography sx={{ fontSize: '12px', fontWeight: 600 }}>
              No performance data available
            </Typography>
            <Typography sx={{ fontSize: '11px' }}>
              Core memory data is not available for this session. Performance metrics will appear once the session is active.
            </Typography>
          </Alert>
        )}
      </Box>
    </div>,
    document.body,
  );
};

export default SessionPerformancePanel;
