import React, { useMemo, useState } from 'react';

const cardStyle = {
  border: "1px solid #e5e7eb",
  borderRadius: 10,
  padding: 12,
  background: "linear-gradient(135deg, #f8fafc 0%, #ffffff 100%)",
  boxShadow: "0 4px 10px rgba(0,0,0,0.04)",
};

const connectionStyle = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "6px 10px",
  backgroundColor: "#eef2ff",
  border: "1px dashed #c7d2fe",
  borderRadius: 8,
  fontSize: 12,
  color: "#4338ca",
};

const AgentTopologyPanel = ({ inventory, activeAgent, onClose }) => {
  const [expandedAgent, setExpandedAgent] = useState(null);

  const {
    agents = [],
    startAgent = null,
    scenario = null,
    handoffMap = {},
  } = inventory || {};

  const connections = useMemo(
    () => Object.entries(handoffMap || {}).map(([tool, target]) => ({ tool, target })),
    [handoffMap],
  );

  const previewNames = useMemo(
    () => agents.slice(0, 3).map((a) => a.name).join(", "),
    [agents],
  );

  const selected = useMemo(() => {
    if (!agents.length) return null;
    const found = agents.find((a) => a.name === expandedAgent);
    return found || agents[0];
  }, [agents, expandedAgent]);

  if (!agents.length) {
    return null;
  }

  const toolList = useMemo(() => {
    if (!selected) return [];
    return Array.from(
      new Set(
        (selected.tools_preview ||
          selected.tools ||
          selected.tool_names ||
          selected.toolNames ||
          []).filter(Boolean),
      ),
    );
  }, [selected]);

  return (
    <div
      className="agents-panel"
      style={{
        position: "fixed",
        left: 12,
        bottom: 120,
        width: 520,
        maxHeight: "70vh",
        overflow: "auto",
        zIndex: 30,
        background: "rgba(255,255,255,0.98)",
        borderRadius: 14,
        boxShadow: "0 18px 50px rgba(15,23,42,0.22)",
        border: "1px solid #e2e8f0",
        padding: 12,
        scrollbarWidth: "none",
        msOverflowStyle: "none",
      }}
    >
      <div
        style={{
          position: "sticky",
          top: 0,
          background: "rgba(255,255,255,0.98)",
          paddingBottom: 8,
          marginBottom: 8,
          zIndex: 1,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ fontWeight: 700, color: "#111827", letterSpacing: 0.2 }}>Agents</div>
            <div style={{ fontSize: 11, color: "#6b7280", display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ padding: "2px 6px", borderRadius: 999, background: "#eef2ff", color: "#4338ca", border: "1px solid #e0e7ff" }}>
                {agents.length} agents
              </span>
              {scenario && (
                <span style={{ padding: "2px 6px", borderRadius: 999, background: "#ecfeff", color: "#0e7490", border: "1px solid #bae6fd" }}>
                  scenario: {scenario}
                </span>
              )}
              {activeAgent && (
                <span style={{ padding: "2px 6px", borderRadius: 999, background: "#d1fae5", color: "#065f46", border: "1px solid #bbf7d0" }}>
                  active: {activeAgent}
                </span>
              )}
            </div>
          </div>
          {typeof onClose === "function" && (
            <button
              type="button"
              onClick={onClose}
              style={{
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                background: "#ffffff",
                padding: "4px 8px",
                fontSize: 12,
                color: "#475569",
                cursor: "pointer",
              }}
            >
              Close
            </button>
          )}
        </div>
      </div>

      <div
        style={{
          fontSize: 12,
          color: "#4b5563",
          padding: "10px 12px",
          border: "1px dashed #e5e7eb",
          borderRadius: 10,
          background: "#f8fafc",
          marginBottom: 12,
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 4 }}>Preview</div>
        <div>{previewNames || "Agents loaded"}</div>
      </div>

      <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        {agents.map((agent, idx) => {
          const isSelected = selected?.name === agent.name;
          return (
            <div
              key={idx}
              style={{
                ...cardStyle,
                borderColor: isSelected ? "#3b82f6" : cardStyle.border,
                boxShadow: isSelected ? "0 8px 24px rgba(59,130,246,0.18)" : cardStyle.boxShadow,
                cursor: "pointer",
              }}
              onClick={() => setSelectedAgent(agent.name)}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontWeight: 700, color: "#111827" }}>{agent.name}</div>
                {startAgent === agent.name && (
                  <span style={{ fontSize: 11, padding: "2px 6px", borderRadius: 999, background: "#d1fae5", color: "#065f46", border: "1px solid #34d399" }}>
                    start
                  </span>
                )}
              </div>
              {agent.description && (
                <div style={{ marginTop: 6, color: "#4b5563", fontSize: 12, lineHeight: 1.4 }}>
                  {agent.description}
                </div>
              )}
              <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap", fontSize: 11, color: "#374151" }}>
                {agent.model && (
                  <span style={{ padding: "2px 6px", background: "#f3f4f6", borderRadius: 8 }}>
                    Model: {typeof agent.model === "string" ? agent.model.replace(/^gpt-/, "") : agent.model}
                  </span>
                )}
                {agent.voice && (
                  <span style={{ padding: "2px 6px", background: "#fef3c7", borderRadius: 8 }}>
                    Voice: {typeof agent.voice === "string" ? (agent.voice.split("-").pop() || agent.voice) : agent.voice}
                  </span>
                )}
                {typeof agent.toolCount === "number" && (
                  <span style={{ padding: "2px 6px", background: "#ecfeff", borderRadius: 8 }}>Tools: {agent.toolCount}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {selected && (
        <div
          style={{
            marginTop: 14,
            padding: "12px",
            borderRadius: 10,
            border: "1px solid #e5e7eb",
            background: "#ffffff",
            boxShadow: "0 6px 14px rgba(15,23,42,0.08)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div style={{ fontWeight: 700, color: "#0f172a" }}>{selected.name}</div>
            <div style={{ display: "flex", gap: 6, fontSize: 11, color: "#475569" }}>
              {selected.model && <span style={{ padding: "2px 6px", borderRadius: 8, background: "#f1f5f9" }}>Model: {selected.model}</span>}
              {selected.voice && <span style={{ padding: "2px 6px", borderRadius: 8, background: "#fef3c7" }}>Voice: {selected.voice}</span>}
              {selected.handoff_trigger && <span style={{ padding: "2px 6px", borderRadius: 8, background: "#ecfeff" }}>Handoff: {selected.handoff_trigger}</span>}
            </div>
          </div>
          {selected.description && (
            <div style={{ fontSize: 12, color: "#4b5563", marginBottom: 8 }}>
              {selected.description}
            </div>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {toolList.length > 0 ? (
              toolList.map((tool, idx) => (
                <span key={idx} style={{ padding: "4px 8px", borderRadius: 8, background: "#eef2ff", color: "#4338ca", fontSize: 12, border: "1px solid #e0e7ff" }}>
                  {tool}
                </span>
              ))
            ) : selected.toolCount > 0 ? (
              <span style={{ fontSize: 12, color: "#94a3b8" }}>
                {selected.toolCount} tools declared (names unavailable)
              </span>
            ) : (
              <span style={{ fontSize: 12, color: "#94a3b8" }}>No tools declared</span>
            )}
          </div>
        </div>
      )}

      {connections.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontWeight: 600, color: "#1f2937", marginBottom: 6 }}>Handoff routes</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {connections.map(({ tool, target }) => (
              <div key={`${tool}-${target}`} style={connectionStyle}>
                <span style={{ fontWeight: 700 }}>{tool}</span>
                <span style={{ color: "#4b5563" }}>-&gt;</span>
                <span style={{ fontWeight: 600 }}>{target}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default AgentTopologyPanel;
