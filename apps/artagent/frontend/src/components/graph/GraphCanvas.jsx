import React, { useCallback, useMemo, useState, useEffect } from 'react';
import SettingsEthernetRoundedIcon from '@mui/icons-material/SettingsEthernetRounded';
import { styles } from '../../styles/voiceAppStyles.js';
import { formatStatusTimestamp } from '../../utils/formatters.js';

const GraphCanvas = ({ events, currentAgent, isFull = false }) => {
  const [selectedNode, setSelectedNode] = useState(null);
  const recent = useMemo(() => {
    return events
      .filter((evt) => {
        const from = evt.from || evt.agent;
        const to = evt.to || evt.agent;
        if (!from || !to) return false;
        const bothSystem = from === "System" && to === "System";
        return !bothSystem;
      })
      .slice(-30);
  }, [events]);
  const agentNames = useMemo(() => {
    const names = new Set();
    recent.forEach((evt) => {
      if (evt.from) names.add(evt.from);
      if (evt.to) names.add(evt.to);
      if (evt.agent) names.add(evt.agent);
    });
    return Array.from(names);
  }, [recent]);

  const height = isFull ? 320 : 240;
  const viewWidth = isFull ? 640 : 340;
  const centerX = viewWidth / 2;
  const centerY = height / 2;
  const radius = Math.min(viewWidth, height) * 0.32;
  const nodes = useMemo(() => {
    return agentNames.map((name, idx) => {
      const angle = (2 * Math.PI * idx) / Math.max(agentNames.length, 1) - Math.PI / 2;
      return {
        id: name,
        label: name,
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      };
    });
  }, [agentNames, centerX, centerY, radius]);

  const buildInitials = useCallback((label, id) => {
    const base = (label || id || "").trim();
    if (!base) return "";
    const parts = base.split(/[\s_-]+/u).filter(Boolean);
    let candidate = "";
    if (parts.length) {
      candidate = parts.map((p) => p[0]).join("").toUpperCase().slice(0, 3);
    } else {
      candidate = base.slice(0, 3).toUpperCase();
    }
    if (candidate === "ASS") {
      return "AST";
    }
    return candidate;
  }, []);

  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const rawEdges = recent
    .map((edge) => {
      const from = edge.from || edge.agent;
      const to = edge.kind === "tool" ? (edge.from || edge.agent) : edge.to || edge.agent || "User";
      if (!from || !to || !nodeById[from] || !nodeById[to]) return null;
      const toolLabel = edge.kind === "tool" ? (edge.tool || edge.summary || "Tool") : null;
      const ts = edge.ts || edge.timestamp || edge.time || "";
      return { from, to, kind: edge.kind, toolLabel, ts, key: `${from}→${to}` };
    })
    .filter(Boolean);

  // Keep only the latest tool edge per agent to avoid overlapping tool labels
  const latestToolByAgent = new Map();
  rawEdges.forEach((edge, idx) => {
    if (edge.kind === "tool") {
      latestToolByAgent.set(edge.from, idx);
    }
  });
  const filteredEdges = rawEdges.filter((edge, idx) => edge.kind !== "tool" || latestToolByAgent.get(edge.from) === idx);

  const edgeCounts = {};
  const edges = filteredEdges.map((edge) => {
    const fromNode = nodeById[edge.from];
    const toNode = nodeById[edge.to];
    const count = edgeCounts[edge.key] = (edgeCounts[edge.key] || 0) + 1;
    const offsetIndex = count - 1;
    const offsetStep = 2;
    const offset = Math.min(offsetIndex, 2) * offsetStep * (offsetIndex % 2 === 0 ? 1 : -1);
    const dx = toNode.y - fromNode.y;
    const dy = fromNode.x - toNode.x;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const ox = (dx / len) * offset;
    const oy = (dy / len) * offset;
    return {
      ...edge,
      id: `${edge.from}-${edge.to}-${count}-${edge.kind}-${edge.ts}`,
      ox,
      oy,
      count,
    };
  });

  const activeEdgeId = edges.length ? edges[edges.length - 1].id : null;
  const visibleEdges = edges;

  // Auto-select last active participant (or current agent) for default events view
  useEffect(() => {
    if (selectedNode && agentNames.includes(selectedNode)) {
      return;
    }
    const lastEvt = [...recent].reverse().find((evt) => {
      const names = [evt.to, evt.from, evt.agent].filter(Boolean);
      return names.some((n) => n && n !== "System");
    });
    const fallback = currentAgent && agentNames.includes(currentAgent) ? currentAgent : null;
    const candidate =
      (lastEvt &&
        [lastEvt.to, lastEvt.from, lastEvt.agent].filter(
          (n) => n && n !== "System",
        )[0]) ||
      fallback ||
      null;
    if (candidate) {
      setSelectedNode(candidate);
    }
  }, [recent, selectedNode, agentNames, currentAgent]);

  if (!recent.length) {
    return (
      <div style={{ ...styles.graphCanvasWrapper, overflow: 'hidden' }}>
        <div style={{ 
          width: '100%', 
          height: height, 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          flexDirection: 'column',
          gap: '12px',
          color: '#64748b',
        }}>
          <SettingsEthernetRoundedIcon sx={{ fontSize: 48, opacity: 0.3 }} />
          <div style={{ fontSize: '14px', fontWeight: 500 }}>No agent activity yet</div>
          <div style={{ fontSize: '12px', opacity: 0.7 }}>Start a conversation to see the agent graph</div>
        </div>
      </div>
    );
  }

  const containerStyle = {
    ...styles.graphCanvasWrapper,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    gap: 10,
    height: isFull ? "100%" : "auto",
    minHeight: isFull ? 380 : undefined,
  };

  return (
    <div style={containerStyle}>
      <svg width="100%" height={height} viewBox={`0 0 ${viewWidth} ${height}`} preserveAspectRatio="xMidYMid meet">
        <defs>
          <marker id="arrow-primary" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L6,3 L0,6 z" fill="rgba(59,130,246,0.8)" />
          </marker>
          <marker id="arrow-strong" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L6,3 L0,6 z" fill="#f97316" />
          </marker>
          <marker id="arrow-muted" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L6,3 L0,6 z" fill="rgba(148,163,184,0.55)" />
          </marker>
        </defs>
        {visibleEdges.map((edge) => {
          const from = nodeById[edge.from];
          const to = nodeById[edge.to];
          const count = edgeCounts[edge.key] || 1;
        const isRepeated = count > 1;
          const isActiveEdge = edge.id === activeEdgeId;
          const base = edge.kind === "tool"
            ? "16,185,129"
            : edge.kind === "switch"
            ? "245,158,11"
            : edge.from === "System" || edge.to === "System"
            ? "148,163,184"
            : "59,130,246";
          const stroke = isActiveEdge
            ? `rgba(${base},0.9)`
            : `rgba(${base},0.25)`;
          const markerEnd = isActiveEdge
            ? (isRepeated ? "url(#arrow-strong)" : "url(#arrow-primary)")
            : "url(#arrow-muted)";
          const fromRadius = edge.from.includes("-tool-") ? 10 : 18;
          const toRadius = edge.to.includes("-tool-") ? 10 : 18;

          const sx = from.x + (edge.ox || 0);
          const sy = from.y + (edge.oy || 0);
          const tx = to.x + (edge.ox || 0);
          const ty = to.y + (edge.oy || 0);

          const dx = tx - sx;
          const dy = ty - sy;
          const len = Math.sqrt(dx * dx + dy * dy) || 1;
          const ux = dx / len;
          const uy = dy / len;

          const startX = sx + ux * (fromRadius + 4);
          const startY = sy + uy * (fromRadius + 4);
          const endX = tx - ux * (toRadius + 6);
          const endY = ty - uy * (toRadius + 6);

          if (edge.kind === "tool") {
            // clockwise self-loop farther from the node
            const loopR = fromRadius + 36;
            const startAngle = -Math.PI / 2; // top
            const endAngle = -Math.PI; // left
            const midAngle = -3 * Math.PI / 4; // midpoint of quarter arc
            const cxLoop = from.x + (edge.ox || 0);
            const cyLoop = from.y + (edge.oy || 0);
            const startLoopX = cxLoop + loopR * Math.cos(startAngle);
            const startLoopY = cyLoop + loopR * Math.sin(startAngle);
            const endLoopX = cxLoop + loopR * Math.cos(endAngle);
            const endLoopY = cyLoop + loopR * Math.sin(endAngle);
            const midLoopX = cxLoop + (loopR + 6) * Math.cos(midAngle);
            const midLoopY = cyLoop + (loopR + 6) * Math.sin(midAngle);
            const d = `M ${startLoopX} ${startLoopY} Q ${midLoopX} ${midLoopY} ${endLoopX} ${endLoopY}`;
            return (
              <g key={edge.id}>
                <path
                  d={d}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={isRepeated ? 2 : 1.4}
                  markerEnd="url(#arrow-muted)"
                  strokeDasharray="4 3"
                  opacity="0.9"
                  strokeLinecap="round"
                />
                {edge.toolLabel && (
                  <text
                    x={midLoopX}
                    y={midLoopY - 8}
                    textAnchor="middle"
                    fontSize="10"
                    fill="#b45309"
                    fontWeight="600"
                  >
                    Tool: {edge.toolLabel}
                  </text>
                )}
              </g>
            );
          }

          const perpX = -uy;
          const perpY = ux;
          const bendBase = edge.kind === "tool" ? 4 : 8;
          const bend = bendBase + (Math.min(count, 2) - 1) * 2;
          const cx = (startX + endX) / 2 + perpX * bend;
          const cy = (startY + endY) / 2 + perpY * bend;
          const midX = (startX + endX) / 2;
          const midY = (startY + endY) / 2;
          return (
            <g key={edge.id}>
              <path
                d={`M ${startX} ${startY} Q ${cx} ${cy} ${endX} ${endY}`}
                fill="none"
                stroke={stroke}
                strokeWidth={isRepeated ? 3 : 2}
                markerEnd={markerEnd}
                strokeDasharray={edge.kind === "tool" ? "4 3" : edge.kind === "switch" ? "2 2" : (edge.from === "System" || edge.to === "System") ? "5 3" : "0"}
                opacity="0.9"
                strokeLinecap="round"
              />
              {edge.toolLabel && (
                <text
                  x={midX + perpX * 6}
                  y={midY + perpY * 6}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#b45309"
                  fontWeight="700"
                >
                  {edge.toolLabel}
                </text>
              )}
            </g>
          );
        })}
        {nodes.map((node) => {
          const isActive = currentAgent && node.id === currentAgent;
          const isSelected = selectedNode === node.id;
          const palette = node.id === "System"
            ? { fill: "linear-gradient(135deg, #fdfdfd, #f1f5f9)", stroke: "#d6d9dd", fg: "#475569" }
            : node.id === "User"
            ? { fill: "linear-gradient(135deg, #f4f8ff, #e7f0ff)", stroke: "#bcd7ff", fg: "#2563eb" }
            : node.id.includes("-tool-")
            ? { fill: "linear-gradient(135deg, #fffaf0, #fef6e4)", stroke: "#f5d58a", fg: "#b45309" }
            : { fill: "linear-gradient(135deg, #f1fdfa, #e3f7ff)", stroke: "#9ae6ff", fg: "#0f4c5c" };
          const initials = node.id === "System"
            ? "SYS"
            : node.id === "User"
            ? "USR"
            : buildInitials(node.label, node.id);
          const innerRadius = node.id.includes("-tool-") ? 10 : 12;
          return (
            <g key={node.id} onClick={() => setSelectedNode(node.id)} style={{ cursor: "pointer" }}>
              <circle
                cx={node.x}
                cy={node.y}
                r={isActive || isSelected ? 22 : 18}
                fill={palette.fill}
                stroke={palette.stroke}
                strokeWidth={isActive || isSelected ? 2.5 : 1.6}
                filter="drop-shadow(0 4px 10px rgba(15,23,42,0.03))"
              />
              <circle
                cx={node.x}
                cy={node.y}
                r={isActive || isSelected ? innerRadius + 6 : innerRadius + 4}
                fill="rgba(255,255,255,0.96)"
                stroke="rgba(0,0,0,0.04)"
                strokeWidth={1}
              />
              <text
                x={node.x}
                y={node.y + 3}
                textAnchor="middle"
                fontSize={node.id.includes("-tool-") ? 9 : 10}
                fontWeight="700"
                fill={palette.fg}
              >
                {initials}
              </text>
              <text
                x={node.x}
                y={node.y + (isActive || isSelected ? 26 : 24)}
                textAnchor="middle"
                fontSize="11"
                fontWeight="700"
                fill="#0f172a"
              >
                {node.label}
              </text>
            </g>
          );
        })}
      </svg>
      {selectedNode && (
        <div
          style={{
            marginTop: "4px",
            padding: "10px 12px",
            border: "1px solid #e2e8f0",
            borderRadius: "12px",
            background: "rgba(248,250,252,0.9)",
            flex: isFull ? "1 1 auto" : "0 0 auto",
            minHeight: isFull ? 200 : 120,
            maxHeight: isFull ? "none" : 260,
            overflowY: "auto",
          }}
        >
          <div style={{ fontSize: "11px", fontWeight: 700, color: "#0f172a", marginBottom: "6px" }}>
            Events for {selectedNode}
          </div>
          {recent
            .filter((evt) => (evt.from || evt.agent) === selectedNode || (evt.to || evt.agent) === selectedNode)
            .slice(-10)
            .map((evt, idx) => (
              <div key={`${selectedNode}-evt-${idx}`} style={{ fontSize: "11px", color: "#334155", marginBottom: "4px", display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
                {(() => {
                  const kind = evt.kind || "event";
                  const eventTypeLabel = evt.eventType || evt.event_type;
                  const speakerLabel = evt.speaker || evt.from || evt.agent || "";
                  const label =
                    kind === "tool"
                      ? `Tool: ${evt.tool || evt.toolLabel || "Call"}`
                      : kind === "switch"
                      ? "Handoff"
                      : eventTypeLabel
                      ? formatEventTypeLabel(eventTypeLabel)
                      : speakerLabel
                      ? `${speakerLabel}`
                      : "Message";
                  return (
                    <>
                      <span style={{ fontWeight: 700, color: "#2563eb" }}>{label}</span>
                      <span style={{ color: "#94a3b8" }}>{formatStatusTimestamp(evt.ts) || ""}</span>
                    </>
                  );
                })()}
                <span style={{ color: "#0f172a", whiteSpace: "normal", wordBreak: "break-word" }}>{evt.text || evt.summary || evt.detail || evt.tool || ""}</span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
};

export default GraphCanvas;
