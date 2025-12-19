"""
Backward-compatible shim for CallEventHandlers.

The event system historically exposed apps.artagent.backend.api.v1.events.handlers,
while the consolidated implementation now lives in acs_events.py.  Importing the
class here preserves existing imports across the codebase and tests.
"""

from . import acs_events as _acs_module

CallEventHandlers = _acs_module.CallEventHandlers
DTMF_VALIDATION_ENABLED = _acs_module.DTMF_VALIDATION_ENABLED
DTMFValidationLifecycle = _acs_module.DTMFValidationLifecycle
broadcast_session_envelope = _acs_module.broadcast_session_envelope
logger = _acs_module.logger

__all__ = [
    "CallEventHandlers",
    "DTMF_VALIDATION_ENABLED",
    "DTMFValidationLifecycle",
    "broadcast_session_envelope",
    "logger",
]
