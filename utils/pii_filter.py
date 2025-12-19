# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License in the project root for
# license information.
# --------------------------------------------------------------------------
"""
PII (Personally Identifiable Information) filtering utilities for telemetry.

This module provides configurable scrubbing of sensitive data from:
- Log messages
- Span attributes
- Trace data exported to Azure Monitor

Configuration via environment variables:
- TELEMETRY_PII_SCRUBBING_ENABLED: Enable/disable PII scrubbing (default: true)
- TELEMETRY_PII_SCRUB_PHONE_NUMBERS: Scrub phone numbers (default: true)
- TELEMETRY_PII_SCRUB_EMAILS: Scrub email addresses (default: true)
- TELEMETRY_PII_SCRUB_SSN: Scrub Social Security Numbers (default: true)
- TELEMETRY_PII_SCRUB_CREDIT_CARDS: Scrub credit card numbers (default: true)
- TELEMETRY_PII_SCRUB_IP_ADDRESSES: Scrub IP addresses (default: false)
- TELEMETRY_PII_CUSTOM_PATTERNS: JSON array of custom regex patterns to scrub
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from re import Pattern
from typing import Any

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# PII PATTERN DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

# Pre-compiled patterns for common PII types
# Each tuple: (pattern, replacement, description)
_PII_PATTERNS: list[tuple[Pattern[str], str, str]] = [
    # Phone numbers (US formats: +1-xxx-xxx-xxxx, (xxx) xxx-xxxx, xxx-xxx-xxxx, etc.)
    (
        re.compile(r"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        "[PHONE_REDACTED]",
        "phone_number",
    ),
    # Email addresses
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "[EMAIL_REDACTED]",
        "email",
    ),
    # US Social Security Numbers (xxx-xx-xxxx)
    (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[SSN_REDACTED]",
        "ssn",
    ),
    # Credit card numbers (13-19 digits, with optional separators)
    (
        re.compile(r"\b(?:\d{4}[-\s]?){3,4}\d{1,4}\b"),
        "[CARD_REDACTED]",
        "credit_card",
    ),
    # IPv4 addresses
    (
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "[IP_REDACTED]",
        "ip_address",
    ),
    # IPv6 addresses (simplified pattern)
    (
        re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"),
        "[IP_REDACTED]",
        "ip_address",
    ),
]

# Attribute names that commonly contain PII and should be scrubbed
PII_ATTRIBUTE_NAMES = frozenset(
    [
        # User identifiers
        "user.email",
        "user.phone",
        "user.name",
        "user.full_name",
        "customer.email",
        "customer.phone",
        "customer.name",
        "caller.phone",
        "caller.number",
        "caller.id",
        # Auth/session
        "auth.token",
        "access_token",
        "refresh_token",
        "api_key",
        "authorization",
        "x-api-key",
        # Network
        "http.client_ip",
        "client.address",
        "net.peer.ip",
        # ACS specific
        "acs.caller_id",
        "acs.phone_number",
        "phone.number",
    ]
)

# Attribute names to completely redact (value replaced entirely)
REDACT_ATTRIBUTE_NAMES = frozenset(
    [
        "password",
        "secret",
        "credential",
        "token",
        "api_key",
        "apikey",
        "api-key",
        "authorization",
        "auth",
    ]
)


@dataclass
class PIIScrubberConfig:
    """Configuration for PII scrubbing behavior."""

    enabled: bool = True
    scrub_phone_numbers: bool = True
    scrub_emails: bool = True
    scrub_ssn: bool = True
    scrub_credit_cards: bool = True
    scrub_ip_addresses: bool = False  # Disabled by default (may be needed for debugging)
    custom_patterns: list[tuple[Pattern[str], str]] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> PIIScrubberConfig:
        """Create configuration from environment variables."""

        def _bool_env(key: str, default: bool) -> bool:
            return os.getenv(key, str(default)).lower() in ("true", "1", "yes")

        config = cls(
            enabled=_bool_env("TELEMETRY_PII_SCRUBBING_ENABLED", True),
            scrub_phone_numbers=_bool_env("TELEMETRY_PII_SCRUB_PHONE_NUMBERS", True),
            scrub_emails=_bool_env("TELEMETRY_PII_SCRUB_EMAILS", True),
            scrub_ssn=_bool_env("TELEMETRY_PII_SCRUB_SSN", True),
            scrub_credit_cards=_bool_env("TELEMETRY_PII_SCRUB_CREDIT_CARDS", True),
            scrub_ip_addresses=_bool_env("TELEMETRY_PII_SCRUB_IP_ADDRESSES", False),
        )

        # Load custom patterns from JSON environment variable
        custom_patterns_json = os.getenv("TELEMETRY_PII_CUSTOM_PATTERNS")
        if custom_patterns_json:
            try:
                patterns = json.loads(custom_patterns_json)
                for item in patterns:
                    if isinstance(item, dict) and "pattern" in item:
                        config.custom_patterns.append(
                            (re.compile(item["pattern"]), item.get("replacement", "[REDACTED]"))
                        )
            except (json.JSONDecodeError, re.error) as e:
                logger.warning(f"Failed to parse TELEMETRY_PII_CUSTOM_PATTERNS: {e}")

        return config


class PIIScrubber:
    """
    Scrubs PII from strings, dictionaries, and telemetry attributes.

    Thread-safe and designed for high-throughput telemetry pipelines.
    """

    def __init__(self, config: PIIScrubberConfig | None = None):
        self.config = config or PIIScrubberConfig.from_env()
        self._active_patterns = self._build_active_patterns()

    def _build_active_patterns(self) -> list[tuple[Pattern[str], str]]:
        """Build list of active patterns based on configuration."""
        if not self.config.enabled:
            return []

        patterns = []
        pattern_flags = {
            "phone_number": self.config.scrub_phone_numbers,
            "email": self.config.scrub_emails,
            "ssn": self.config.scrub_ssn,
            "credit_card": self.config.scrub_credit_cards,
            "ip_address": self.config.scrub_ip_addresses,
        }

        for pattern, replacement, pii_type in _PII_PATTERNS:
            if pattern_flags.get(pii_type, True):
                patterns.append((pattern, replacement))

        # Add custom patterns
        patterns.extend(self.config.custom_patterns)

        return patterns

    def scrub_string(self, value: str) -> str:
        """
        Scrub PII from a string value.

        Args:
            value: String potentially containing PII

        Returns:
            String with PII patterns replaced
        """
        if not self.config.enabled or not value:
            return value

        result = value
        for pattern, replacement in self._active_patterns:
            result = pattern.sub(replacement, result)

        return result

    def scrub_attribute_value(self, name: str, value: Any) -> Any:
        """
        Scrub PII from an attribute value based on the attribute name.

        Args:
            name: Attribute name (used to determine scrubbing behavior)
            value: Attribute value

        Returns:
            Scrubbed value
        """
        if not self.config.enabled:
            return value

        name_lower = name.lower()

        # Completely redact sensitive attribute names
        for redact_name in REDACT_ATTRIBUTE_NAMES:
            if redact_name in name_lower:
                return "[REDACTED]"

        # Scrub known PII attribute names
        for pii_name in PII_ATTRIBUTE_NAMES:
            if pii_name in name_lower or name_lower in pii_name:
                if isinstance(value, str):
                    return self.scrub_string(value)
                return "[REDACTED]"

        # For other string values, apply pattern-based scrubbing
        if isinstance(value, str):
            return self.scrub_string(value)

        return value

    def scrub_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Scrub PII from all values in a dictionary.

        Args:
            data: Dictionary with potentially sensitive values

        Returns:
            New dictionary with scrubbed values
        """
        if not self.config.enabled:
            return data

        return {key: self.scrub_attribute_value(key, value) for key, value in data.items()}


# Module-level singleton for convenience
_default_scrubber: PIIScrubber | None = None


def get_pii_scrubber() -> PIIScrubber:
    """Get the default PII scrubber instance (lazily initialized)."""
    global _default_scrubber
    if _default_scrubber is None:
        _default_scrubber = PIIScrubber()
    return _default_scrubber


def scrub_pii(value: str) -> str:
    """Convenience function to scrub PII from a string."""
    return get_pii_scrubber().scrub_string(value)


def scrub_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to scrub PII from a dictionary of attributes."""
    return get_pii_scrubber().scrub_dict(attributes)
