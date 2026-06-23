"""
Voice Live BYOM (Bring Your Own Model) Config
=============================================

Validates the per-agent BYOM config that drives the VoiceLive connect() query
param (``profile``). BYOM is opt-in: when no mode is set the agent connects with
managed VoiceLive (no profile param).

Covers:
  * VoiceLiveBYOMConfig.from_dict normalization (disabled vs enabled, alt keys).
  * to_query() shaping for connect(..., query=...).
  * UnifiedAgent.get_byom_query() delegation.
  * The agent_builder ByomConfigSchema mode validator.
"""

from __future__ import annotations

import pytest

from apps.artagent.backend.registries.agentstore.base import (
    VOICELIVE_BYOM_MODES,
    HandoffConfig,
    ModelConfig,
    UnifiedAgent,
    VoiceLiveBYOMConfig,
)


# =============================================================================
# VoiceLiveBYOMConfig.from_dict — disabled cases
# =============================================================================


@pytest.mark.parametrize("data", [None, {}, {"mode": ""}, {"mode": "   "}])
def test_from_dict_disabled_returns_none(data):
    """Empty/whitespace/missing mode (and no override) → disabled (None)."""
    assert VoiceLiveBYOMConfig.from_dict(data) is None


# =============================================================================
# VoiceLiveBYOMConfig.from_dict — enabled cases
# =============================================================================


def test_from_dict_mode_only():
    cfg = VoiceLiveBYOMConfig.from_dict({"mode": "byom-foundry-anthropic-messages"})
    assert cfg is not None
    assert cfg.mode == "byom-foundry-anthropic-messages"
    assert cfg.to_query() == {"profile": "byom-foundry-anthropic-messages"}


def test_from_dict_accepts_byom_alias():
    """`byom` is accepted as an alias for `mode`."""
    cfg = VoiceLiveBYOMConfig.from_dict({"byom": "byom-azure-openai-chat-completion"})
    assert cfg is not None
    assert cfg.mode == "byom-azure-openai-chat-completion"
    assert cfg.to_query() == {"profile": "byom-azure-openai-chat-completion"}


def test_to_dict_round_trip():
    cfg = VoiceLiveBYOMConfig.from_dict({"mode": "byom-azure-openai-realtime"})
    assert cfg.to_dict() == {"mode": "byom-azure-openai-realtime"}
    # Re-parsing the serialized form yields an equivalent query.
    assert VoiceLiveBYOMConfig.from_dict(cfg.to_dict()).to_query() == cfg.to_query()


def test_to_query_disabled_when_mode_missing():
    """No mode → BYOM disabled → query is None."""
    cfg = VoiceLiveBYOMConfig(mode=None)
    assert cfg.to_query() is None


# =============================================================================
# UnifiedAgent.get_byom_query — delegation
# =============================================================================


def _make_agent(byom: VoiceLiveBYOMConfig | None) -> UnifiedAgent:
    return UnifiedAgent(
        name="ByomAgent",
        description="byom test agent",
        handoff=HandoffConfig(trigger="handoff_byomagent"),
        model=ModelConfig(deployment_id="gpt-realtime"),
        byom=byom,
        prompt_template="You are a test agent.",
    )


def test_agent_get_byom_query_none_when_unset():
    assert _make_agent(None).get_byom_query() is None


def test_agent_get_byom_query_returns_profile():
    cfg = VoiceLiveBYOMConfig.from_dict({"mode": "byom-azure-openai-realtime"})
    assert _make_agent(cfg).get_byom_query() == {"profile": "byom-azure-openai-realtime"}


# =============================================================================
# agent_builder ByomConfigSchema — mode validation at the API boundary
# =============================================================================


def test_schema_rejects_invalid_mode():
    from apps.artagent.backend.api.v1.endpoints.agent_builder import ByomConfigSchema

    with pytest.raises(ValueError):
        ByomConfigSchema(mode="not-a-real-mode")


@pytest.mark.parametrize("mode", VOICELIVE_BYOM_MODES)
def test_schema_accepts_known_modes(mode):
    from apps.artagent.backend.api.v1.endpoints.agent_builder import ByomConfigSchema

    assert ByomConfigSchema(mode=mode).mode == mode


def test_schema_blank_mode_normalizes_to_none():
    from apps.artagent.backend.api.v1.endpoints.agent_builder import ByomConfigSchema

    assert ByomConfigSchema(mode="   ").mode is None
