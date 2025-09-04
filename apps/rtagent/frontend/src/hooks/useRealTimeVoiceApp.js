/**
 * Real-Time Voice Application Hooks
 * 
 * Complete business logic extracted from the original monolithic component
 */
import { useState, useRef, useEffect, useCallback } from 'react';

// AudioWorklet source code for PCM streaming playback
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
          console.log('AudioWorklet: Received audio chunk, queue length:', this.queue.length);
        } else if (e.data?.type === 'clear') {
          // Clear all queued audio data for immediate interruption
          this.queue = [];
          this.readIndex = 0;
          console.log('AudioWorklet: Audio queue cleared for barge-in');
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

export const useRealTimeVoiceApp = (API_BASE_URL, WS_URL) => {
  // State management
  const [messages, setMessages] = useState([]);
  const [log, setLog] = useState("");
  const [recording, setRecording] = useState(false);
  const [targetPhoneNumber, setTargetPhoneNumber] = useState("");
  const [callActive, setCallActive] = useState(false);
  const [activeSpeaker, setActiveSpeaker] = useState(null);
  const [showPhoneInput, setShowPhoneInput] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [outputAudioLevel, setOutputAudioLevel] = useState(0);

  // Tooltip states
  const [showResetTooltip, setShowResetTooltip] = useState(false);
  const [showMicTooltip, setShowMicTooltip] = useState(false);
  const [showPhoneTooltip, setShowPhoneTooltip] = useState(false);

  // Hover states for enhanced button effects
  const [resetHovered, setResetHovered] = useState(false);
  const [micHovered, setMicHovered] = useState(false);
  const [phoneHovered, setPhoneHovered] = useState(false);

  // Refs
  const chatRef = useRef(null);
  const messageContainerRef = useRef(null);
  const socketRef = useRef(null);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);
  const analyserRef = useRef(null);
  const micStreamRef = useRef(null);
  const playbackAudioContextRef = useRef(null);
  const pcmSinkRef = useRef(null);
  const audioLevelRef = useRef(0);
  const outputAudioLevelRef = useRef(0);

  // Utility functions
  const appendLog = useCallback((text) => {
    setLog((prev) => prev + `${new Date().toLocaleTimeString()}: ${text}\n`);
  }, []);

  // Auto-scroll chat to bottom
  useEffect(() => {
    if (messageContainerRef.current) {
      messageContainerRef.current.scrollTop = messageContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // Initialize playback audio context and worklet
  const initializeAudioPlayback = async () => {
    if (playbackAudioContextRef.current) return;
    
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({});
      
      await audioCtx.audioWorklet.addModule(URL.createObjectURL(new Blob(
        [workletSource], { type: 'text/javascript' }
      )));
      
      const pcmSink = new AudioWorkletNode(audioCtx, 'pcm-sink');
      pcmSink.connect(audioCtx.destination);
      
      playbackAudioContextRef.current = audioCtx;
      pcmSinkRef.current = pcmSink;
      
      appendLog("🔊 Audio playback initialized");
    } catch (e) {
      appendLog(`❌ Audio playback init failed: ${e.message}`);
    }
  };

  // Start audio recognition - EXACT COPY from original
  const startRecognition = async () => {
    // mind-map reset not needed
    setMessages([]);
    appendLog("🎤 PCM streaming started");

    // Initialize audio playback system on user gesture
    await initializeAudioPlayback();

    // 1) open WS
    const socket = new WebSocket(`${WS_URL}/api/v1/realtime/conversation`);
    socket.binaryType = "arraybuffer";

    socket.onopen = () => {
      appendLog("🔌 WS open - Connected to backend!");
      console.log("WebSocket connection OPENED to backend at:", `${WS_URL}/api/v1/realtime/conversation`);
    };
    socket.onclose = (event) => {
      appendLog(`🔌 WS closed - Code: ${event.code}, Reason: ${event.reason}`);
      console.log("WebSocket connection CLOSED. Code:", event.code, "Reason:", event.reason);
    };
    socket.onerror = (err) => {
      appendLog("❌ WS error - Check if backend is running");
      console.error("WebSocket error - backend might not be running:", err);
    };
    socket.onmessage = handleSocketMessage;
    socketRef.current = socket;

    // 2) setup Web Audio for raw PCM @16 kHz
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    micStreamRef.current = stream;
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 16000
    });
    audioContextRef.current = audioCtx;

    const source = audioCtx.createMediaStreamSource(stream);

    // Add analyser for real-time audio level monitoring
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.3;
    analyserRef.current = analyser;
    
    // Connect source to analyser
    source.connect(analyser);

    // 3) ScriptProcessor with small buffer for low latency (256 or 512 samples)
    const bufferSize = 512; 
    const processor  = audioCtx.createScriptProcessor(bufferSize, 1, 1);
    processorRef.current = processor;

    // Connect analyser to processor for audio data flow
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
      console.log("Mic data sample:", float32.slice(0, 10)); // Should show non-zero values if your mic is hot

      const int16 = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {
        int16[i] = Math.max(-1, Math.min(1, float32[i])) * 0x7fff;
      }

      // Debug: Show size before send
      console.log("Sending int16 PCM buffer, length:", int16.length);

      if (socket.readyState === WebSocket.OPEN) {
        socket.send(int16.buffer);
        // Debug: Confirm data sent
        console.log("PCM audio chunk sent to backend!");
      } else {
        console.log("WebSocket not open, did not send audio.");
      }
    };

    source.connect(processor);
    processor.connect(audioCtx.destination);
    setRecording(true);
  };

  // Stop audio recognition - EXACT COPY from original
  const stopRecognition = () => {
    if (processorRef.current) {
      try { 
        processorRef.current.disconnect(); 
      } catch (e) {
        console.warn("Error disconnecting processor:", e);
      }
      processorRef.current = null;
    }
    if (audioContextRef.current) {
      try { 
        audioContextRef.current.close(); 
      } catch (e) {
        console.warn("Error closing audio context:", e);
      }
      audioContextRef.current = null;
    }
    // Note: Keep playback context alive for TTS even when stopping recording
    // if (playbackAudioContextRef.current) {
    //   try { 
    //     playbackAudioContextRef.current.close(); 
    //   } catch (e) {
    //     console.warn("Error closing playback audio context:", e);
    //   }
    //   playbackAudioContextRef.current = null;
    //   pcmSinkRef.current = null;
    // }
    if (socketRef.current) {
      try { 
        socketRef.current.close(); 
      } catch (e) {
        console.warn("Error closing socket:", e);
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
    
    // Don't clear all state - preserve chat history and UI
    // Just stop the recording session
  };

  // Helper to dedupe consecutive identical messages
  const pushIfChanged = (arr, msg) => {
    // Only dedupe if the last message is from the same speaker and has the same text
    if (arr.length === 0) return [...arr, msg];
    const last = arr[arr.length - 1];
    if (last.speaker === msg.speaker && last.text === msg.text) return arr;
    return [...arr, msg];
  };

  // Handle WebSocket messages - EXACT COPY from original
  const handleSocketMessage = async (event) => {
    // Log all incoming messages for debugging
    if (typeof event.data === "string") {
      try {
        const msg = JSON.parse(event.data);
        console.log("📨 WebSocket message received:", msg.type || "unknown", msg);
      } catch (e) {
        console.log("📨 Non-JSON WebSocket message:", event.data);
      }
    } else {
      console.log("📨 Binary WebSocket message received, length:", event.data.byteLength);
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
    
    // Handle audio_data messages from backend TTS
    if (payload.type === "audio_data" && payload.data) {
      try {
        console.log("🔊 Received audio_data message:", {
          frame_index: payload.frame_index,
          total_frames: payload.total_frames,
          sample_rate: payload.sample_rate,
          data_length: payload.data.length,
          is_final: payload.is_final
        });

        // Decode base64 -> Int16 -> Float32 [-1, 1]
        const bstr = atob(payload.data);
        const buf = new ArrayBuffer(bstr.length);
        const view = new Uint8Array(buf);
        for (let i = 0; i < bstr.length; i++) view[i] = bstr.charCodeAt(i);
        const int16 = new Int16Array(buf);
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x8000;

        console.log(`🔊 Processing TTS audio chunk: ${float32.length} samples, sample_rate: ${payload.sample_rate || 16000}`);
        console.log("🔊 Audio data preview:", float32.slice(0, 10));

        // Push to the worklet queue
        if (pcmSinkRef.current) {
          pcmSinkRef.current.port.postMessage({ type: 'push', payload: float32 });
          appendLog(`🔊 TTS audio frame ${payload.frame_index + 1}/${payload.total_frames}`);
        } else {
          console.warn("Audio playback not initialized, attempting init...");
          appendLog("⚠️ Audio playback not ready, initializing...");
          // Try to initialize if not done yet
          await initializeAudioPlayback();
          if (pcmSinkRef.current) {
            pcmSinkRef.current.port.postMessage({ type: 'push', payload: float32 });
            appendLog("🔊 TTS audio playing (after init)");
          } else {
            console.error("Failed to initialize audio playback");
            appendLog("❌ Audio init failed");
          }
        }
        return; // handled
      } catch (error) {
        console.error("Error processing audio_data:", error);
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

    /* ---------- USER BRANCH ---------- */
    if (msgType === "user" || speaker === "User") {
      setActiveSpeaker("User");
      // Always append user message immediately, do not dedupe
      setMessages(prev => [...prev, { speaker: "User", text: txt }]);

      appendLog(`User: ${txt}`);
      return;
    }

    /* ---------- ASSISTANT STREAM ---------- */
    if (type === "assistant_streaming") {
      const streamingSpeaker = speaker || "Assistant";
      setActiveSpeaker(streamingSpeaker);
      setMessages(prev => {
        if (prev.at(-1)?.streaming) {
          return prev.map((m,i)=> i===prev.length-1 ? {...m, text:txt} : m);
        }
        return [...prev, { speaker:streamingSpeaker, text:txt, streaming:true }];
      });
      return;
    }

    /* ---------- ASSISTANT FINAL ---------- */
    if (msgType === "assistant" || msgType === "status" || speaker === "Assistant") {
      setActiveSpeaker("Assistant");
      setMessages(prev => {
        if (prev.at(-1)?.streaming) {
          return prev.map((m,i)=> i===prev.length-1 ? {...m, text:txt, streaming:false} : m);
        }
        return pushIfChanged(prev, { speaker:"Assistant", text:txt });
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

    /* ---------- CONTROL MESSAGES BRANCH ---------- */
    if (type === "control") {
      const { action } = payload;
      console.log("🎮 Control message received:", action);
      
      if (action === "tts_cancelled") {
        console.log("🔇 TTS cancelled - clearing audio queue");
        appendLog("🔇 Audio interrupted by user speech");
        
        // Clear the audio worklet queue
        if (pcmSinkRef.current) {
          pcmSinkRef.current.port.postMessage({ type: 'clear' });
        }
        
        // Reset active speaker since TTS was interrupted
        setActiveSpeaker(null);
        return;
      }
      
      console.log("🎮 Unknown control action:", action);
      return;
    }
  };

  // Start ACS phone call
  const startACSCall = async () => {
    if (!/^\+\d+$/.test(targetPhoneNumber)) {
      alert("Enter phone in E.164 format e.g. +15551234567");
      return;
    }
    
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/calls/initiate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_number: targetPhoneNumber }),
      });
      
      const json = await res.json();
      if (!res.ok) {
        appendLog(`Call error: ${json.detail || res.statusText}`);
        return;
      }
      
      setMessages(m => [...m, { speaker: "Assistant", text: `📞 Call started → ${targetPhoneNumber}` }]);
      appendLog("📞 Call initiated");

      // Relay WebSocket
      const relay = new WebSocket(`${WS_URL}/api/v1/realtime/dashboard/relay`);
      relay.onopen = () => appendLog("Relay WS connected");
      relay.onmessage = ({ data }) => {
        try {
          const obj = JSON.parse(data);
          if (obj.type?.startsWith("tool_")) {
            handleSocketMessage({ data: JSON.stringify(obj) });
            return;
          }
          const { sender, message } = obj;
          setMessages(m => [...m, { speaker: sender, text: message }]);
          setActiveSpeaker(sender);
          appendLog(`[Relay] ${sender}: ${message}`);
        } catch {
          appendLog("Relay parse error");
        }
      };
      relay.onclose = () => {
        appendLog("Relay WS disconnected");
        setCallActive(false);
        setActiveSpeaker(null);
      };
    } catch (e) {
      appendLog(`Network error starting call: ${e.message}`);
    }
  };

  // Reset session
  const resetSession = () => {
    setMessages([]);
    setActiveSpeaker(null);
    stopRecognition();
    setCallActive(false);
    setShowPhoneInput(false);
    appendLog("🔄️ Session reset - starting fresh");
    
    setTimeout(() => {
      setMessages([{ 
        speaker: "System", 
        text: "✅ Session restarted. Ready for a new conversation!" 
      }]);
    }, 500);
  };

  // Toggle phone input
  const togglePhoneInput = () => {
    if (callActive) {
      stopRecognition();
      setCallActive(false);
      setMessages(prev => [...prev, { 
        speaker: "System",
        text: "📞 Call ended" 
      }]);
    } else {
      setShowPhoneInput(!showPhoneInput);
    }
  };

  return {
    // State
    messages,
    log,
    recording,
    targetPhoneNumber,
    callActive,
    activeSpeaker,
    showPhoneInput,
    audioLevel,
    outputAudioLevel,
    
    // Tooltip states
    showResetTooltip,
    showMicTooltip,
    showPhoneTooltip,
    
    // Hover states
    resetHovered,
    micHovered,
    phoneHovered,
    
    // Refs
    chatRef,
    messageContainerRef,
    
    // Actions
    setTargetPhoneNumber,
    setShowResetTooltip,
    setShowMicTooltip,
    setShowPhoneTooltip,
    setResetHovered,
    setMicHovered,
    setPhoneHovered,
    
    // Functions
    startRecognition,
    stopRecognition,
    startACSCall,
    resetSession,
    togglePhoneInput,
    appendLog
  };
};
