
| Feature | What it delivers | Meter that ticks |
|---------|------------------|------------------|
| **Real-time transcription** (`transcriptionOptions.startTranscription = true`) | ACS streams your chosen party's audio to Azure AI Speech on Microsoft's backbone and pushes TranscriptionReceived events with partial and final text. | Speech-to-Text minutes ($/min) |
| **Bidirectional media streaming** (`mediaStreamingOptions.enableBidirectional = true`) | A WebSocket that sends you raw PCM and lets you push PCM back into the live call in sub-100 ms. | Media-stream minutes ($/min) |

They’re independent flags in the same payload, and the preview REST schema even shows them side-by-side:
```
"mediaStreamingOptions": { "enableBidirectional": true, ... },
"transcriptionOptions": { "startTranscription": true, ... }
```  
---

### Do you ever turn **both** on?

| Use-case | Why both make sense | Gotchas |
|----------|--------------------|---------|
| **You want instant, Microsoft-hosted STT *and* need to inject custom audio** (e.g., a proprietary TTS voice, watermarking tones, or a second AI model) | Built-in STT gives you transcripts with zero extra code while the bidirectional socket lets you stream your own PCM back. | • You pay *two* meters (STT + stream).<br>• The Speech recognizer ignores audio you inject, so there’s no echo loop, but it still sees the caller’s channel only. |
| **Hybrid AI routing / A/B testing** | Keep Azure’s STT running for baseline quality metrics while you stream the same audio to a third-party engine over the socket for comparison. | Double STT cost; make sure you don’t violate data-residency rules when forwarding PCM. |
| **Fail-safe design** | Use built-in transcription as the fallback; if your custom pipeline fails, you still get text from ACS and can fall back to DTMF or canned prompts. | Build a health probe and switch logic; you’ll still pay for the idle stream. |

---

### When you’d normally pick **one** or the other

| If you need… | Enable only |
|--------------|------------|
| Quick transcripts, no custom audio processing | **Transcription** – simpler & cheaper |
| Fine-grained barge-in, custom STT/TTS, multi-service fan-out | **Bidirectional streaming** – you’ll do your own STT |

---

### Cost & performance trade-offs

* **Running both ≈ 1.5-2 × the per-minute cost** (Speech minutes + streaming minutes).  
* Latency is dictated by the slower path: built-in STT returns words in ~250 ms; your outbound PCM path adds whatever network hop you introduce, but it **doesn’t slow** the built-in recognizer.  
* Memory/CPU on your bot side goes up because you now maintain **two** WebSocket consumers (ACS events + bidirectional media).

---

### TL;DR

*They’re orthogonal toggles.*  
Most solutions choose **one**: built-in STT *or* bidirectional PCM.  
Turn **both** on only when you have a concrete need—custom outbound audio or dual-engine transcription—and are willing to pay the extra meters.  [oai_citation:4‡learn.microsoft.com](https://learn.microsoft.com/en-us/azure/communication-services/concepts/call-automation/audio-streaming-concept?utm_source=chatgpt.com) [oai_citation:5‡learn.microsoft.com](https://learn.microsoft.com/en-us/azure/communication-services/concepts/call-automation/real-time-transcription?utm_source=chatgpt.com) [oai_citation:6‡learn.microsoft.com](https://learn.microsoft.com/es-es/rest/api/communication/callautomation/answer-call/answer-call?view=rest-communication-callautomation-2024-11-15-preview&utm_source=chatgpt.com)