// src/hooks/useSpeechRecognizer.js
import { useState, useRef } from "react";
import {
  SpeechConfig,
  AudioConfig,
  SpeechRecognizer,
  PropertyId,
} from "microsoft-cognitiveservices-speech-sdk";

export default function useSpeechRecognizer(
  onRecognizing,
  onRecognized
) {
  const [recording, setRecording] = useState(false);
  const recognizerRef = useRef(null);
  const startRecognition = () => {
    let cfg;
    const endpoint = import.meta.env.VITE_AZURE_SPEECH_ENDPOINT;
    const key = import.meta.env.VITE_AZURE_SPEECH_KEY;
    const region = import.meta.env.VITE_AZURE_REGION;

    if (endpoint) {
      cfg = SpeechConfig.fromEndpoint(new URL(endpoint), key);
    } else {
      cfg = SpeechConfig.fromSubscription(key, region);
    }
    cfg.speechRecognitionLanguage = "en-US";

    const rec = new SpeechRecognizer(
      cfg,
      AudioConfig.fromDefaultMicrophoneInput()
    );
    rec.properties.setProperty(
      PropertyId.Speech_SegmentationSilenceTimeoutMs,
      "800"
    );
    rec.properties.setProperty(
      PropertyId.Speech_SegmentationStrategy,
      "Semantic"
    );

    if (onRecognizing) rec.recognizing = onRecognizing;
    if (onRecognized) rec.recognized = onRecognized;

    rec.startContinuousRecognitionAsync();
    recognizerRef.current = rec;
    setRecording(true);
  };

  const stopRecognition = () => {
    recognizerRef.current?.stopContinuousRecognitionAsync();
    setRecording(false);
  };

  return { recording, startRecognition, stopRecognition, recognizerRef };
}
