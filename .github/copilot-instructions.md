# 🧠 Copilot Instructions for Real-Time Voice App (Python 3.11, FastAPI, Azure)

---

## 🚀 Overview

You are generating Python 3.11 code for a **low-latency, real-time voice app** using:

- **FastAPI**
- **Azure Communication Services** (Call Automation + Media Streaming)
- **Azure Speech** (STT/TTS)
- **Azure OpenAI**

---

## 📐 General Principles

- **Readability & Simplicity:** Favor clear, direct code.
- **Modular Design:** Separate infrastructure, backend logic, and frontend UX.
- **Async Endpoints:** Use `async` for HTTP and WebSocket handlers.
- **Schemas:** All request/response models use `pydantic.BaseModel`.
- **Dependency Injection:** Use FastAPI `Depends` for session/auth/Redis clients.
- **Configuration:** Use environment variables or `.env` for secrets/config.
- **Structured Logging:** Emit JSON logs with `correlation ID`, `callConnectionId`, etc.
- **No Blocking I/O:** Avoid global state; use scoped containers.

---

## 🔎 Tracing & App Map

- **OpenTelemetry:** Always instrument with OTEL.
    - Set `service.name` and `service.instance.id` on `TracerProvider Resource`.
- **SpanKind:**
    - `SERVER` for inbound HTTP/WS
    - `CLIENT` for outbound calls
    - `INTERNAL` for internal steps
- **Context Propagation:** Use W3C `traceparent` over HTTP/WS. Use span links for cross-process work.
- **Root Trace:** One per `callConnectionId`. Add `rt.call.connection_id` and `rt.session.id` attributes.
- **Span Volume:** Reasonable; one session span for STT (+ events), optional VAD segment spans. **Never per-frame.**
- **Semantic Attributes:** Use keys like `peer.service`, `net.peer.name`, `http.request.method`, `server.address`, `network.protocol.name="websocket"`.
- **Error Handling:** On errors, set span status to `ERROR` and add event with `error.type` and `error.message`.

---

## 🏗️ Structure & Dependency Injection

- **No Client Stashing:** Do not stash clients on `Request`/`WebSocket`.
- **Typed AppContainer:** Create protocols for Redis, Speech, AOAI. Attach to `app.state`, expose via FastAPI dependencies.
- **WebSocket Handlers:** Accept dependencies via `container_from_ws(ws)`; avoid direct `ws.app.state.*` access.

---

## 📞 Azure Communication Services (ACS) Specifics

- **callConnectionId:** Treat as correlation token, not secret. Prefer headers/message body.
- **Media Spans:** 
    - `SERVER` span for WS accept
    - `CLIENT` spans for ACS control ops (answer, play, stop, hangup)

---

## ✨ Style Guide

- **Small, Focused Functions:** Explicit timeouts on awaits; no blocking calls in event loop.
- **Background Work:** Use `asyncio.create_task` and track task lifecycles.
- **Docstrings:** Include inputs/outputs and latency considerations.
- **Unit-Testable:** Allow fakes for Redis/Speech/AOAI via Protocols.

---

## 🚫 Do NOT

- Add per-audio-chunk spans
- Use global singletons
- Add span attributes for `service.name`/`span.kind`

---

> **Tip:** Use code blocks, lists, and semantic section headers to clarify intent and structure for inferencing engines.

---
