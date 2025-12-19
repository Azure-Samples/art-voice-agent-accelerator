// src/hooks/useLogs.js
import { useState, useCallback } from "react";

export default function useLogs() {
  const [log, setLog] = useState("");
  const [callActive, setCallActive] = useState(false);

  const appendLog = useCallback((msg) => {
    setLog((prev) =>
      prev + "\n" + new Date().toLocaleTimeString() + " - " + msg
    );
    if (msg.includes("Call connected")) setCallActive(true);
    if (msg.includes("Call ended") || msg.includes("❌ Call disconnected"))
      setCallActive(false);
  }, []);

  return { log, appendLog, callActive, setCallActive };
}
