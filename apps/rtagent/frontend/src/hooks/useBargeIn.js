import { useCallback } from 'react';

const toMs = (value) => (typeof value === "number" ? Math.round(value) : undefined);

const useBargeIn = ({
  appendLog,
  setActiveSpeaker,
  assistantStreamGenerationRef,
  pcmSinkRef,
  playbackActiveRef,
  metricsRef,
  publishMetricsSummary,
}) => {
  const interruptAssistantOutput = useCallback(
    (meta, { logMessage } = {}) => {
      if (!meta) {
        return;
      }

      assistantStreamGenerationRef.current += 1;
      const logText =
        logMessage ||
        `🔇 Audio interrupted by user speech (${meta.trigger || "unknown"} → ${meta.at || "unknown"})`;
      appendLog(logText);

      if (pcmSinkRef.current) {
        pcmSinkRef.current.port.postMessage({ type: "clear" });
      }
      playbackActiveRef.current = false;
      setActiveSpeaker(null);
    },
    [
      appendLog,
      assistantStreamGenerationRef,
      pcmSinkRef,
      playbackActiveRef,
      setActiveSpeaker,
    ],
  );

  const recordBargeInEvent = useCallback(
    (action, meta = {}) => {
      const metrics = metricsRef.current;
      const now = performance.now();
      let event = metrics.pendingBargeIn;

      if (!event || action === "tts_cancelled") {
        event = {
          id: metrics.bargeInEvents.length + 1,
          trigger: meta.trigger,
          stage: meta.at,
          receivedTs: now,
          actions: [],
          sinceLastAudioFrameMs:
            metrics.lastAudioFrameTs != null ? now - metrics.lastAudioFrameTs : undefined,
        };
        metrics.pendingBargeIn = event;
        metrics.bargeInEvents.push(event);
      }

      event.actions.push({ action, ts: now });

      if (action === "tts_cancelled") {
        publishMetricsSummary("Barge-in tts_cancelled", {
          trigger: meta.trigger,
          stage: meta.at,
          sinceLastAudioFrameMs: toMs(event.sinceLastAudioFrameMs),
        });
      } else if (action === "audio_stop") {
        event.audioStopTs = now;
        event.timeFromCancelMs = event.receivedTs != null ? now - event.receivedTs : undefined;
        publishMetricsSummary("Barge-in audio_stop", {
          trigger: meta.trigger,
          stage: meta.at,
          deltaMs: toMs(event.timeFromCancelMs),
        });
      } else {
        publishMetricsSummary("Barge-in event", { action });
      }

      return event;
    },
    [metricsRef, publishMetricsSummary],
  );

  const finalizeBargeInClear = useCallback(
    (event, { keepPending = false } = {}) => {
      if (!event) {
        return;
      }
      const now = performance.now();
      if (event.clearIssuedTs == null) {
        event.clearIssuedTs = now;
        event.totalClearMs = event.receivedTs != null ? now - event.receivedTs : undefined;
        event.clearAfterAudioStopMs = event.audioStopTs != null ? now - event.audioStopTs : undefined;
        publishMetricsSummary("Barge-in playback cleared", {
          totalMs: toMs(event.totalClearMs),
          afterAudioStopMs: toMs(event.clearAfterAudioStopMs),
        });
      }
      metricsRef.current.pendingBargeIn = keepPending ? event : null;
    },
    [metricsRef, publishMetricsSummary],
  );

  return {
    interruptAssistantOutput,
    recordBargeInEvent,
    finalizeBargeInClear,
  };
};

export default useBargeIn;
