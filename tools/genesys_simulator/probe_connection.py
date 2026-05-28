"""Genesys AudioConnector connection-probe diagnostic.

Reproduces the *exact* handshake Genesys Cloud performs when you activate (or
toggle Inactive -> Active) an Audio Connector integration, and reports whether
the target server handles it correctly. Use it to verify any ART deployment's
``/api/v1/genesys/stream`` endpoint without a Genesys account.

The Genesys activation probe is a regular AudioHook ``open`` whose
``conversationId`` and ``participant.id`` are the null UUID
(``00000000-0000-0000-0000-000000000000``). A conformant server must:

  1. Complete the WebSocket handshake. Genesys offers **no**
     ``Sec-WebSocket-Protocol`` header, so the server must NOT select a
     subprotocol the client did not offer (doing so makes a strict client
     abort the handshake -- the classic "problem communicating with the
     AudioConnector Bot" failure with empty server logs).
  2. Answer ``open`` with ``opened`` within ~5s.
  3. Send NO audio for the probe (it is not a real call).
  4. Close cleanly when the client sends ``close``.

Exit code is 0 when all checks pass, 1 otherwise -- so it can be wired into CI
or a smoke test.

Examples::

    python probe_connection.py ws://localhost:8081/api/v1/genesys/stream
    python probe_connection.py wss://<your-app>.azurecontainerapps.io/api/v1/genesys/stream
    python probe_connection.py --offer-subprotocol audiohook wss://<your-app>/api/v1/genesys/stream
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

import websocket  # websocket-client

NULL_UUID = "00000000-0000-0000-0000-000000000000"
DEFAULT_URL = os.environ.get(
    "GENESYS_PROBE_URL", "ws://localhost:8081/api/v1/genesys/stream"
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="probe_connection.py",
        description="Replay the Genesys AudioConnector activation probe against an ART endpoint.",
    )
    p.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_URL,
        help=f"WebSocket URL of the Genesys stream endpoint (default: {DEFAULT_URL})",
    )
    p.add_argument(
        "--offer-subprotocol",
        metavar="NAME",
        default=None,
        help=(
            "Offer this WebSocket subprotocol on the handshake. Genesys offers "
            "NONE, so leave this unset to mirror Genesys exactly; set it only to "
            "test negotiation behavior."
        ),
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-message receive timeout in seconds (default: 10).",
    )
    return p.parse_args(argv)


def run_probe(url: str, offer_subprotocol: str | None, timeout: float) -> bool:
    session_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    print(f"Target: {url}")
    print(
        f"Mode:   connection probe (null-UUID) | "
        f"offer_subprotocol={offer_subprotocol or 'none (Genesys-exact)'}"
    )
    print(f"Session: {session_id}\n")

    kwargs: dict = dict(
        header={
            "audiohook-session-id": session_id,
            "audiohook-organization-id": org_id,
            "audiohook-correlation-id": str(uuid.uuid4()),
        },
        timeout=timeout,
    )
    if offer_subprotocol:
        kwargs["subprotocols"] = [offer_subprotocol]

    try:
        ws = websocket.create_connection(url, **kwargs)
    except Exception as exc:  # noqa: BLE001 - surface any handshake failure
        print(f"  HANDSHAKE FAILED: {type(exc).__name__}: {exc}")
        return False

    negotiated = ws.subprotocol
    print(f"  [ 0.00s] handshake OK | negotiated subprotocol={negotiated!r}")

    # A server must not select a subprotocol the client did not offer.
    subprotocol_ok = True
    if not offer_subprotocol and negotiated:
        subprotocol_ok = False
        print(
            f"        WARNING: server selected subprotocol {negotiated!r} "
            f"but the client offered none (RFC 6455 violation)."
        )

    open_msg = {
        "version": "2",
        "id": session_id,
        "type": "open",
        "seq": 1,
        "position": "PT0S",
        "parameters": {
            "organizationId": org_id,
            "conversationId": NULL_UUID,
            "participant": {"id": NULL_UUID, "ani": "", "aniName": "", "dnis": ""},
            "media": [
                {"type": "audio", "format": "PCMU", "channels": ["external", "internal"], "rate": 8000},
                {"type": "audio", "format": "PCMU", "channels": ["external"], "rate": 8000},
                {"type": "audio", "format": "PCMU", "channels": ["internal"], "rate": 8000},
            ],
            "language": None,
            "customConfig": {},
        },
        "serverseq": 0,
    }

    t0 = time.monotonic()
    ws.send(json.dumps(open_msg))
    print("  [ 0.00s] -> open (probe)")

    opened_at: float | None = None
    binary_frames = 0
    closed_cleanly = False
    ws.settimeout(timeout)

    for _ in range(20):
        try:
            msg = ws.recv()
        except websocket.WebSocketTimeoutException:
            print("        (timeout waiting for next message)")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  <- ERROR: {type(exc).__name__}: {exc}")
            break

        dt = time.monotonic() - t0
        if isinstance(msg, (bytes, bytearray)):
            binary_frames += 1
            print(f"  [{dt:5.2f}s] <- BINARY frame, {len(msg)} bytes (probe should receive NO audio)")
            continue

        parsed = json.loads(msg)
        mtype = parsed.get("type")
        params = parsed.get("parameters", {})
        print(f"  [{dt:5.2f}s] <- {mtype}")

        if mtype == "opened":
            opened_at = dt
            print(f"        startPaused present: {'startPaused' in params}")
            close_msg = {
                "version": "2", "id": session_id, "type": "close", "seq": 2,
                "position": "PT0S", "parameters": {"reason": "end"}, "serverseq": 1,
            }
            ws.send(json.dumps(close_msg))
            print(f"  [{dt:5.2f}s] -> close (reason=end)")
        elif mtype in ("closed", "disconnect"):
            closed_cleanly = True
            break
        elif mtype == "error":
            print(f"        server error: {json.dumps(params)[:300]}")
            break

    try:
        ws.close()
    except Exception:  # noqa: BLE001
        pass

    opened_ok = opened_at is not None and opened_at <= 5.0
    no_audio_ok = binary_frames == 0

    print("\n=== PROBE RESULT ===")
    print(f"  [{'PASS' if subprotocol_ok else 'FAIL'}] subprotocol negotiation")
    print(
        f"  [{'PASS' if opened_ok else 'FAIL'}] opened within 5s "
        f"({'%.2fs' % opened_at if opened_at is not None else 'not received'})"
    )
    print(f"  [{'PASS' if no_audio_ok else 'FAIL'}] no audio during probe ({binary_frames} binary frames)")
    print(f"  [{'PASS' if closed_cleanly else 'WARN'}] clean close (closed/disconnect received)")

    passed = subprotocol_ok and opened_ok and no_audio_ok
    print(f"\n{'PROBE PASSED' if passed else 'PROBE FAILED'} - "
          f"server-side protocol path is {'healthy' if passed else 'NOT healthy'} as deployed.")
    return passed


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    ok = run_probe(args.url, args.offer_subprotocol, args.timeout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
