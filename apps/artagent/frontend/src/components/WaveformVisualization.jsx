import React, { useEffect, useMemo, useRef, useState } from 'react';
import { styles } from '../styles/voiceAppStyles.js';
import { smoothValue } from '../utils/audio.js';

const WaveformVisualization = React.memo(({ activeSpeaker, audioLevelRef, outputAudioLevelRef, bargeInActive = false }) => {
  const [waveRenderState, setWaveRenderState] = useState({ amplitude: 0, offset: 0 });
  const [speakerState, setSpeakerState] = useState({ user: false, assistant: false });
  const animationRef = useRef();
  const containerRef = useRef(null);
  const [canvasWidth, setCanvasWidth] = useState(750);
  const combinedLevelRef = useRef(0);
  const latestLevelsRef = useRef({ input: 0, output: 0 });
  const levelTimestampRef = useRef(performance.now());
  const lastVisualUpdateRef = useRef(performance.now());
  const waveRenderRef = useRef({ amplitude: 0, offset: 0 });
  const USER_THRESHOLD = 0.015;
  const ASSISTANT_THRESHOLD = 0.006;
  const userDisplayActive = speakerState.user || activeSpeaker === "User";
  const assistantDisplayActive = speakerState.assistant || activeSpeaker === "Assistant";
  const bothDisplayActive = userDisplayActive && assistantDisplayActive;

  useEffect(() => {
    const updateWidth = () => {
      const next = containerRef.current?.getBoundingClientRect()?.width;
      if (next && Math.abs(next - canvasWidth) > 2) {
        setCanvasWidth(next);
      }
    };
    updateWidth();
    const ro = new ResizeObserver(updateWidth);
    if (containerRef.current) {
      ro.observe(containerRef.current);
    }
    window.addEventListener("resize", updateWidth);
    return () => {
      window.removeEventListener("resize", updateWidth);
      ro.disconnect();
    };
  }, [canvasWidth]);

  useEffect(() => {
    let rafId;
    const updateLevels = () => {
      const now = performance.now();
      const deltaMs = now - (levelTimestampRef.current || now);
      levelTimestampRef.current = now;
      const inputLevel = audioLevelRef?.current ?? 0;
      const outputLevel = outputAudioLevelRef?.current ?? 0;
      latestLevelsRef.current = { input: inputLevel, output: outputLevel };

      const target = Math.max(inputLevel, outputLevel);
      const previous = combinedLevelRef.current;
      const next = smoothValue(previous, target, deltaMs, 85, 260);
      combinedLevelRef.current = next < 0.004 ? 0 : next;

      setSpeakerState((prev) => {
        const nextUser = inputLevel > USER_THRESHOLD
          ? true
          : inputLevel < USER_THRESHOLD * 0.6
            ? false
            : prev.user;
        const nextAssistant = outputLevel > ASSISTANT_THRESHOLD
          ? true
          : outputLevel < ASSISTANT_THRESHOLD * 0.6
            ? false
            : prev.assistant;
        if (prev.user === nextUser && prev.assistant === nextAssistant) {
          return prev;
        }
        return { user: nextUser, assistant: nextAssistant };
      });

      rafId = requestAnimationFrame(updateLevels);
    };
    rafId = requestAnimationFrame(updateLevels);
    return () => {
      if (rafId) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [audioLevelRef, outputAudioLevelRef]);

  useEffect(() => {
    let lastTs = performance.now();

    const animate = () => {
      const now = performance.now();
      const delta = now - lastTs;
      lastTs = now;

      const activity = combinedLevelRef.current;
      const normalized = Math.min(1, Math.pow(activity * 1.1, 0.88));
      const targetAmplitude = normalized < 0.015
        ? 0
        : (36 * normalized) + (18 * normalized * normalized) + (bargeInActive ? 6 : 0);
      const prevAmplitude = waveRenderRef.current.amplitude;
      const easedAmplitude = smoothValue(prevAmplitude, targetAmplitude, delta, 110, 260);
      const finalAmplitude = easedAmplitude < 0.35 ? 0 : easedAmplitude;

      const prevOffset = waveRenderRef.current.offset;
      const waveSpeed = 0.38 + normalized * 2.1;
      const nextOffset = (prevOffset + waveSpeed * (delta / 16)) % 1000;

      const nowTs = now;
      const needsUpdate =
        Math.abs(finalAmplitude - prevAmplitude) > 0.35 ||
        Math.abs(nextOffset - prevOffset) > 0.9 ||
        nowTs - lastVisualUpdateRef.current > 48;

      if (needsUpdate) {
        const nextState = { amplitude: finalAmplitude, offset: nextOffset };
        waveRenderRef.current = nextState;
        lastVisualUpdateRef.current = nowTs;
        setWaveRenderState(nextState);
      }

      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [bargeInActive]);
  
  const generateWavePath = () => {
    const width = Math.max(canvasWidth, 200);
    const height = 110;
    const centerY = height / 2;
    const frequency = 0.02;
    const points = 160;

    let path = `M 0 ${centerY}`;

    for (let i = 0; i <= points; i++) {
      const x = (i / points) * width;
      const y = centerY + Math.sin((x * frequency + waveRenderState.offset * 0.1)) * waveRenderState.amplitude;
      path += ` L ${x} ${y}`;
    }
    
    return path;
  };

  // Secondary wave
  const generateSecondaryWave = () => {
    const width = Math.max(canvasWidth, 200);
    const height = 110;
    const centerY = height / 2;
    const frequency = 0.0245;
    const points = 140;

    let path = `M 0 ${centerY}`;

    for (let i = 0; i <= points; i++) {
      const x = (i / points) * width;
      const y = centerY + Math.sin((x * frequency + waveRenderState.offset * 0.12)) * (waveRenderState.amplitude * 0.6);
      path += ` L ${x} ${y}`;
    }
    
    return path;
  };

  // Wave rendering
  const generateMultipleWaves = () => {
    const waves = [];
    
    let baseColor;
    let opacity = 0.85;
    if (bothDisplayActive) {
      baseColor = "url(#waveGradientBarge)";
    } else if (userDisplayActive) {
      baseColor = "#ef4444";
    } else if (assistantDisplayActive) {
      baseColor = "#67d8ef";
    } else {
      baseColor = "#3b82f6";
      opacity = 0.45;
    }

    if (waveRenderState.amplitude <= 0.8) {
      baseColor = "#cbd5e1";
      waves.push(
        <line
          key="wave-idle"
          x1="0"
          y1="40"
          x2={Math.max(canvasWidth, 200)}
          y2="40"
          stroke={baseColor}
          strokeWidth="2"
          strokeLinecap="round"
          opacity={0.75}
        />
      );
      return waves;
    }

    waves.push(
      <path
        key="wave1"
        d={generateWavePath()}
        stroke={baseColor}
        strokeWidth={userDisplayActive || assistantDisplayActive ? "3" : "2"}
        fill="none"
        opacity={opacity}
        strokeLinecap="round"
      />
    );

    waves.push(
      <path
        key="wave2"
        d={generateSecondaryWave()}
        stroke={baseColor}
        strokeWidth={userDisplayActive || assistantDisplayActive ? "2" : "1.5"}
        fill="none"
        opacity={opacity * 0.5}
        strokeLinecap="round"
      />
    );
    
    return waves;
  };
  
  const audioLevel = latestLevelsRef.current.input;
  const outputAudioLevel = latestLevelsRef.current.output;

  return (
    <div style={styles.waveformContainer} ref={containerRef}>
      <svg style={styles.waveformSvg} viewBox={`0 0 ${Math.max(canvasWidth, 200)} 110`} preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="waveGradientBarge" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#ef4444" />
            <stop offset="50%" stopColor="#8b5cf6" />
            <stop offset="100%" stopColor="#67d8ef" />
          </linearGradient>
        </defs>
        {generateMultipleWaves()}
      </svg>
      
      <div style={{
        position: 'absolute',
        bottom: '-14px',
        left: '50%',
        transform: 'translateX(-50%)',
        fontSize: '11px',
        color: '#475569',
        whiteSpace: 'nowrap',
        background: 'rgba(255,255,255,0.9)',
        padding: '4px 10px',
        borderRadius: '10px',
        border: '1px solid rgba(226,232,240,0.9)',
        boxShadow: '0 6px 12px rgba(15,23,42,0.08)',
        zIndex: '10',
      }}>
        Input: {(audioLevel * 100).toFixed(1)}% | Output: {(outputAudioLevel * 100).toFixed(1)}% | Amp: {waveRenderState.amplitude.toFixed(1)} | Speaker: {bothDisplayActive ? 'Barge-In' : (userDisplayActive ? 'User' : assistantDisplayActive ? 'Assistant' : (activeSpeaker || 'Idle'))}
      </div>

    </div>
  );
});

export default WaveformVisualization;
