// src/hooks/useWebSocket.js
import { useState, useEffect, useRef, useCallback } from "react";

export default function useWebSocket({
  appendLog,
  addMindMapNode,
  setActiveSpeaker,
  lastUserId,
  lastAssistantId,
  appendMessage,     // optional: if you want to mirror into another queue
}) {
  const [messages, setMessages] = useState([]);
  const conversationSocketRef = useRef(null);
  const dashboardSocketRef = useRef(null);
  const backendPlaceholder = '__BACKEND_URL__';
  const backendUrl = backendPlaceholder.startsWith('__') 
    ? import.meta.env.VITE_BACKEND_BASE_URL || 'http://localhost:8000'
    : backendPlaceholder;
  const WS_URL = backendUrl.replace(/^https?/, "wss");

  const append = useCallback(
    (msg) => {
      setMessages((prev) => [...prev, msg]);
      appendMessage?.(msg);
    },
    [appendMessage]
  );

  const sendText = useCallback(
    (text) => {
      if (conversationSocketRef.current?.readyState === WebSocket.OPEN) {
        conversationSocketRef.current.send(JSON.stringify({ text }));
        append({ speaker: "User", text });
        addMindMapNode?.({ speaker: "User", text });
        setActiveSpeaker?.("User");
        appendLog?.(`User: ${text}`);
      }
    },
    [append, addMindMapNode, setActiveSpeaker, appendLog]
  );

  useEffect(() => {
    const socket = new WebSocket(`${WS_URL}/realtime`);
    socket.binaryType = "arraybuffer";

    socket.onopen = () => append({ speaker: "System", text: "🔌 WS open" });
    socket.onclose = () => append({ speaker: "System", text: "🔌 WS closed" });

    socket.onmessage = async (event) => {
      // binary = TTS audio
      if (typeof event.data !== "string") {
        const ctx = new AudioContext();
        const buf = await event.data.arrayBuffer();
        const audioBuf = await ctx.decodeAudioData(buf);
        const src = ctx.createBufferSource();
        src.buffer = audioBuf;
        src.connect(ctx.destination);
        src.start();
        appendLog?.("🔊 Audio played");
        return;
      }

      // JSON payload
      let p;
      try {
        p = JSON.parse(event.data);
      } catch {
        appendLog?.("Ignored non-JSON frame");
        return;
      }
      const {
        type,
        content = "",
        message = "",
        tool,
        pct,
        status,
        elapsedMs,
        result,
        error,
      } = p;
      const txt = content || message;

      switch (type) {
        case "assistant_streaming":
          setActiveSpeaker?.("Assistant");
          setMessages((prev) => {
            if (prev.at(-1)?.streaming) {
              return prev.map((m, i) =>
                i === prev.length - 1 ? { ...m, text: txt } : m
              );
            }
            return [...prev, { speaker: "Assistant", text: txt, streaming: true }];
          });
          break;

        case "assistant":
        case "status":
          append({ speaker: "Assistant", text: txt });
          addMindMapNode?.({
            speaker: "Assistant",
            text: txt,
            parentId: lastUserId.current,
          });
          setActiveSpeaker?.("Assistant");
          appendLog?.("🤖 Assistant responded");
          break;

        case "tool_start":
          addMindMapNode?.({
            speaker: "Assistant",
            functionCall: tool,
            parentId: lastAssistantId.current,
            toolStatus: "running",
          });
          append({
            speaker: "Assistant",
            isTool: true,
            text: `🛠️ tool ${tool} started 🔄`,
          });
          appendLog?.(`⚙️ ${tool} started`);
          break;

        case "tool_progress":
          setMessages((prev) =>
            prev.map((m, i, arr) =>
              i === arr.length - 1 && m.text.startsWith(`🛠️ tool ${tool}`)
                ? { ...m, text: `🛠️ tool ${tool} ${pct}% 🔄` }
                : m
            )
          );
          appendLog?.(`⚙️ ${tool} ${pct}%`);
          break;

        case "tool_end": {
          addMindMapNode?.({
            speaker: "Assistant",
            functionCall: tool,
            parentId: lastAssistantId.current,
            toolStatus: status === "success" ? "completed" : "error",
          });
          const finalText =
            status === "success"
              ? `🛠️ tool ${tool} completed ✔️\n${JSON.stringify(
                  result,
                  null,
                  2
                )}`
              : `🛠️ tool ${tool} failed ❌\n${error}`;
          setMessages((prev) =>
            prev.map((m, i, arr) =>
              i === arr.length - 1 && m.text.startsWith(`🛠️ tool ${tool}`)
                ? { ...m, text: finalText }
                : m
            )
          );
          appendLog?.(`⚙️ ${tool} ${status} (${elapsedMs} ms)`);
          break;
        }
      }
    };

    socketRef.current = socket;
    return () => {
      if (socket.readyState === WebSocket.OPEN) socket.close();
    };
  }, [
    WS_URL,
    append,
    appendLog,
    addMindMapNode,
    setActiveSpeaker,
    lastUserId,
    lastAssistantId,
    appendMessage,
  ]);

  return { messages, sendText, socketRef };
}
