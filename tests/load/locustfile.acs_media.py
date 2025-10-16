# locustfile.py
import base64, json, os, time, uuid
from pathlib import Path
from gevent import sleep
import random

from locust import User, task, events, between
import websocket
from websocket import WebSocketConnectionClosedException
import ssl, urllib.parse, certifi, websocket

# Treat benign WebSocket closes as non-errors (1000/1001/1006 often benign in load)
WS_IGNORE_CLOSE_EXCEPTIONS = os.getenv("WS_IGNORE_CLOSE_EXCEPTIONS", "true").lower() in {"1", "true", "yes"}

## For debugging websocket connections
# websocket.enableTrace(True)
# print("LOCUST_HOST =", os.environ.get("LOCUST_HOST"))

#
# --- Config ---
DEFAULT_WS_URL = os.getenv("WS_URL")
PCM_DIR = os.getenv("PCM_DIR", "tests/load/audio_cache")  # If set, iterate .pcm files in this directory per turn
# PCM_PATH = os.getenv("PCM_PATH", "sample_16k_s16le_mono.pcm")  # Used if no directory provided
SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", "16000"))  # Hz
BYTES_PER_SAMPLE = int(os.getenv("BYTES_PER_SAMPLE", "2"))  # 1 => PCM8 unsigned, 2 => PCM16LE
CHANNELS = int(os.getenv("CHANNELS", "1"))
CHUNK_MS = int(os.getenv("CHUNK_MS", "20"))  # 20 ms
CHUNK_BYTES = int(SAMPLE_RATE * BYTES_PER_SAMPLE * CHANNELS * CHUNK_MS / 1000)  # default 640
TURNS_PER_USER = int(os.getenv("TURNS_PER_USER", "3"))
CHUNKS_PER_TURN = int(os.getenv("CHUNKS_PER_TURN", "100"))  # ~2s @20ms
TURN_TIMEOUT_SEC = float(os.getenv("TURN_TIMEOUT_SEC", "15.0"))
PAUSE_BETWEEN_TURNS_SEC = float(os.getenv("PAUSE_BETWEEN_TURNS_SEC", "1.5"))

# If your endpoint requires explicit empty AudioData frames, use this (preferred for semantic VAD)
FIRST_BYTE_TIMEOUT_SEC = float(os.getenv("FIRST_BYTE_TIMEOUT_SEC", "5.0"))  # max wait for first server byte
BARGE_QUIET_MS = int(os.getenv("BARGE_QUIET_MS", "400"))  # consider response ended after this quiet gap
# Any server message containing these tokens completes a turn:
RESPONSE_TOKENS = tuple((os.getenv("RESPONSE_TOKENS", "recognizer,greeting,response,transcript,result")
                         .lower().split(",")))

# End-of-response detection tokens for barge-in
END_TOKENS = tuple((os.getenv("END_TOKENS", "final,end,completed,stopped,barge").lower().split(",")))


# Module-level zeroed chunk buffer for explicit silence
if BYTES_PER_SAMPLE == 1:
    # PCM8 unsigned silence is 0x80
    ZERO_CHUNK = b"\x80" * CHUNK_BYTES
else:
    # PCM16LE (and other signed PCM) silence is 0x00
    ZERO_CHUNK = b"\x00" * CHUNK_BYTES

def b64(buf: bytes) -> str:
    return base64.b64encode(buf).decode("ascii")

def generate_silence_chunk(duration_ms: float = 100.0, sample_rate: int = 16000) -> bytes:
    """Generate a silent audio chunk with very low-level noise for VAD continuity."""
    samples = int((duration_ms / 1000.0) * sample_rate)
    # Generate very quiet background noise instead of pure silence
    # This is more realistic and helps trigger final speech recognition
    import struct
    audio_data = bytearray()
    for _ in range(samples):
        # Add very quiet random noise (-10 to +10 amplitude in 16-bit range)
        noise = random.randint(-10, 10)
        audio_data.extend(struct.pack('<h', noise))
    return bytes(audio_data)
  # PCM16LE and other signed

class ACSUser(User):
    def _resolve_ws_url(self) -> str:
        candidate = (self.environment.host or DEFAULT_WS_URL or "").strip()
        if not candidate:
            raise RuntimeError(
                "No websocket host configured. Provide --host/LOCUST_HOST or legacy WS_URL."
            )

        if candidate.startswith("https://"):
            candidate = "wss://" + candidate[len("https://") :]
        elif candidate.startswith("http://"):
            candidate = "wss://" + candidate[len("http://") :]
        elif candidate.startswith("ws://"):
            candidate = "ws://" + candidate[len("ws://") :]
        elif not candidate.startswith("wss://"):
            candidate = f"wss://{candidate.lstrip('/')}"

        parsed = urllib.parse.urlparse(candidate)
        path = parsed.path or ""
        if path in {"", "/"}:
            parsed = parsed._replace(path="/api/v1/media/stream")
            candidate = urllib.parse.urlunparse(parsed)

        return candidate

    def _recv_with_timeout(self, per_attempt_timeout: float):
        try:
            self.ws.settimeout(per_attempt_timeout)
            return self.ws.recv()
        except WebSocketConnectionClosedException:
            self._connect_ws()
            return None
        except Exception:
            return None

    def _measure_ttfb(self, max_wait_sec: float) -> tuple[bool, float]:
        """Time-To-First-Byte after EOS: start timer now and wait for first incoming WS frame."""
        start = time.time()
        deadline = start + max_wait_sec
        while time.time() < deadline:
            msg = self._recv_with_timeout(0.05)
            if msg:
                return True, (time.time() - start) * 1000.0
        return False, (time.time() - start) * 1000.0

    def _wait_for_end_of_response(self, quiet_ms: int, max_wait_sec: float) -> tuple[bool, float]:
        """
        After barge-in is initiated, wait until the previous server response 'ends'.
        Heuristics:
         - See an END_TOKENS token in any incoming message, OR
         - Observe no inbound frames for 'quiet_ms'.
        """
        start = time.time()
        last_msg_at = None
        deadline = start + max_wait_sec
        per_attempt = 0.05
        quiet_sec = max(quiet_ms / 1000.0, per_attempt)
        while time.time() < deadline:
            msg = self._recv_with_timeout(per_attempt)
            if msg:
                last_msg_at = time.time()
                text = str(msg).lower()
                # any explicit end tokens
                if any(tok in text for tok in END_TOKENS):
                    return True, (time.time() - start) * 1000.0
            else:
                if last_msg_at and (time.time() - last_msg_at) >= quiet_sec:
                    return True, (time.time() - start) * 1000.0
        return False, (time.time() - start) * 1000.0
    wait_time = between(0.3, 1.1)

    def _record(self, name: str, response_time_ms: float, exc: Exception | None = None):
        # Unified request event (Locust 2.39+)
        self.environment.events.request.fire(
            request_type="websocket",
            name=name,
            response_time=response_time_ms,
            response_length=0,
            exception=exc,
            context={"call_connection_id": getattr(self, "call_connection_id", None)}
        )

    def _connect_ws(self):
        # Emulate ACS headers that many servers expect for correlation
        self.call_connection_id = f"{uuid.uuid4()}"
        url = self._resolve_ws_url()
        self.correlation_id = str(uuid.uuid4())

        # Parse host for SNI and Origin
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        headers = [
            f"x-ms-call-connection-id: {self.call_connection_id}",
            f"x-ms-call-correlation-id: {self.correlation_id}",
            f"x-call-connection-id: {self.call_connection_id}",
            f"x-session-id: {self.call_connection_id}",
        ]
        print(url)
        sslopt = {}
        if url.startswith("wss://"):
            sslopt = {
                "cert_reqs": ssl.CERT_REQUIRED,
                "ca_certs": certifi.where(),
                "check_hostname": True,
                "server_hostname": host,   # ensure SNI
            }
        origin_scheme = "https" if url.startswith("wss://") else "http"
        # Explicitly disable proxies even if env vars are set
        self.ws = websocket.create_connection(
            url,
            header=headers,
            origin=f"{origin_scheme}://{host}",
            enable_multithread=True,
            sslopt=sslopt,
            http_proxy_host=None,
            http_proxy_port=None,
            proxy_type=None,
            # subprotocols=["your-protocol"]  # uncomment if your server requires one
        )

        # Send initial AudioMetadata once per connection
        meta = {
            "kind": "AudioMetadata",
            "audioMetadata": {
                "subscriptionId": str(uuid.uuid4()),
                "encoding": "PCM",
                "sampleRate": SAMPLE_RATE,
                "channels": CHANNELS,
                "length": CHUNK_BYTES
            }
        }
        self.ws.send(json.dumps(meta))

    def on_start(self):
        # Discover PCM inputs
        self.pcm_files = []
        if PCM_DIR:
            d = Path(PCM_DIR)
            if d.exists() and d.is_dir():
                self.pcm_files = sorted(str(p) for p in d.glob("*.pcm"))
        # if not self.pcm_files:
        #     # Fallback to single file path
        #     self.pcm_files = [str(Path(PCM_PATH))]
        # Validate and prime state
        validated = []
        for p in self.pcm_files:
            b = Path(p).read_bytes()
            if len(b) > 0:
                validated.append(p)
        if not validated:
            raise RuntimeError(f"No valid PCM inputs found. Checked PCM_DIR={PCM_DIR}")
        self.pcm_files = validated
        self.turn_index = 0
        # placeholders initialized per turn
        self.audio = b""
        self.offset = 0

        self._connect_ws()

    def on_stop(self):
        try:
            self.ws.close()
        except Exception:
            pass
        finally:
            self.ws = None

    def _next_chunk(self) -> bytes:
        end = self.offset + CHUNK_BYTES
        if end <= len(self.audio):
            chunk = self.audio[self.offset:end]
        else:
            # wrap
            chunk = self.audio[self.offset:] + self.audio[:end % len(self.audio)]
        self.offset = end % len(self.audio)
        return chunk

    def _begin_turn_audio(self):
        """Select next PCM file and reset buffer for this turn."""
        file_path = self.pcm_files[self.turn_index % len(self.pcm_files)]
        self.turn_index += 1
        self.audio = Path(file_path).read_bytes()
        self.offset = 0
        return file_path
    

    
    def _send_audio_chunk(self):
        payload = {
            "kind": "AudioData",
            "audioData": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.", time.gmtime())
                             + f"{int(time.time_ns()%1_000_000_000/1_000_000):03d}Z",
                "participantRawID": self.call_connection_id,
                "data": b64(self._next_chunk()),
                "length": CHUNK_BYTES,
                "silent": False
            }
        }
        try:
            self.ws.send(json.dumps(payload))
        except WebSocketConnectionClosedException:
            # Reconnect and resend metadata, then retry once
            self._connect_ws()
            self.ws.send(json.dumps(payload))

    def _await_server_response(self, timeout_sec: float) -> tuple[bool, float]:
        start = time.time()
        deadline = start + timeout_sec
        while time.time() < deadline:
            try:
                self.ws.settimeout(min(0.2, max(0.01, deadline - time.time())))
                msg = self.ws.recv()
            except WebSocketConnectionClosedException:
                # connection dropped; reconnect and continue waiting
                self._connect_ws()
                continue
            except Exception:
                msg = None
            if not msg:
                continue
            text = str(msg).lower()
            if any(tok in text for tok in RESPONSE_TOKENS):
                return True, (time.time() - start) * 1000.0
        return False, (time.time() - start) * 1000.0

    @task
    def speech_turns(self):
        for _ in range(TURNS_PER_USER):
            t0 = time.time()
            try:
                # pick file for this turn
                file_used = self._begin_turn_audio()
                # stream N chunks at ~CHUNK_MS cadence
                for _ in range(CHUNKS_PER_TURN):
                    self._send_audio_chunk()
                    sleep(CHUNK_MS / 1000.0)

                # Send several small non-silent "silence" chunks to encourage finalization
                try:
                    for _ in range(15):  # ~1.5s total at 100ms
                        silence_msg = {
                            "kind": "AudioData",
                            "audioData": {
                                "data": base64.b64encode(generate_silence_chunk(100)).decode('utf-8'),
                                "silent": False,  # keep VAD engaged for graceful end
                                "timestamp": time.time()
                            }
                        }
                        self.ws.send(json.dumps(silence_msg))
                        time.sleep(0.1)
                except WebSocketConnectionClosedException as e:
                    # Benign: server may close after completing turn; avoid counting as error
                    if WS_IGNORE_CLOSE_EXCEPTIONS:
                        # Reconnect for next operations/turns and continue
                        try:
                            self._connect_ws()
                        except Exception:
                            pass
                    else:
                        raise

                # TTFB: measure time from now (after EOS) to first server frame
                ttfb_ok, ttfb_ms = self._measure_ttfb(FIRST_BYTE_TIMEOUT_SEC)
                self._record(name=f"ttfb[{Path(file_used).name}]", response_time_ms=ttfb_ms, exc=None if ttfb_ok else Exception("tffb_timeout"))

                # Barge-in: start next turn immediately with a single audio frame
                next_file_used = self._begin_turn_audio()
                barge_start_sent = time.time()
                try:
                    self._send_audio_chunk()  # one chunk to trigger barge-in
                except Exception as e:
                    self._record(name=f"barge_in[{Path(file_used).name}->{Path(next_file_used).name}]", response_time_ms=(time.time() - barge_start_sent) * 1000.0, exc=e)
                    # if barge failed to send, continue to next loop iteration
                    continue
                # Measure time until 'end of previous response' using heuristic
                barge_ok, barge_ms = self._wait_for_end_of_response(BARGE_QUIET_MS, TURN_TIMEOUT_SEC)
                self._record(
                    name=f"barge_in[{Path(file_used).name}->{Path(next_file_used).name}]",
                    response_time_ms=barge_ms, 
                    exc=None if barge_ok else Exception("barge_end_timeout")
                )

            except WebSocketConnectionClosedException as e:
                # Treat normal/idle WS closes as non-errors to reduce false positives in load reports
                if WS_IGNORE_CLOSE_EXCEPTIONS:
                    # Optionally record a benign close event as success for observability
                    self._record(name="websocket_closed", response_time_ms=(time.time() - t0) * 1000.0, exc=None)
                else:
                    self._record(name=f"turn_error[{Path(file_used).name if 'file_used' in locals() else 'unknown'}]",
                                 response_time_ms=(time.time() - t0) * 1000.0, exc=e)
            except Exception as e:
                turn_name = f"{Path(file_used).name}" if 'file_used' in locals() else "unknown"
                self._record(name=f"turn_error[{turn_name}]", response_time_ms=(time.time() - t0) * 1000.0, exc=e)
            sleep(PAUSE_BETWEEN_TURNS_SEC)