"""
Agent Builder Voice Catalog
===========================

Guards the ``GET /api/v1/agent-builder/voices`` contract that populates the
Agent Builder voice picker and the Quick Tune "Voice (TTS)" dropdown.

The bug this covers: the endpoint used to build its response from a small
hand-written ``AVAILABLE_VOICES`` catalog (14 en-US voices, 4 of them HD) and
used the live region voice list only as an *intersection filter*. No matter how
many voices the Speech region actually supported, the picker could never show
more than the catalog — so HD voices and every non-en-US locale were invisible.

These tests call the endpoint coroutine directly (no network) with the region
enumeration stubbed, so they exercise the real server-side merge/tag/sort logic.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from apps.artagent.backend.api.v1.endpoints import agent_builder
from apps.artagent.backend.api.v1.endpoints.agent_builder import (
    _HD_CATALOG,
    _MAI_CATALOG,
    AVAILABLE_VOICES,
    _classify_voice_name,
    _locale_from_short_name,
    list_available_voices,
)
from apps.artagent.backend.api.v1.schemas.voices import VoiceInfo
from apps.artagent.backend.src.services import voice_catalog

# =============================================================================
# HELPERS
# =============================================================================


def call(**kwargs):
    """Invoke the endpoint coroutine synchronously."""
    return asyncio.run(list_available_voices(**kwargs)).model_dump()


def sdk_voice(short_name: str, locale: str, local_name: str, gender: str = "Female"):
    """Mimic the Speech SDK's VoiceInfo shape for get_voices_async() results."""
    return SimpleNamespace(
        short_name=short_name,
        locale=locale,
        local_name=local_name,
        gender=SimpleNamespace(name=gender),
    )


REGION_SAMPLE = [
    sdk_voice("en-US-AvaMultilingualNeural", "en-US", "Ava"),
    sdk_voice("en-US-AndrewMultilingualNeural", "en-US", "Andrew", "Male"),
    sdk_voice("en-US-Ava:DragonHDLatestNeural", "en-US", "Ava"),
    sdk_voice("en-US-Steffan:DragonHDLatestNeural", "en-US", "Steffan", "Male"),
    sdk_voice("de-DE-Seraphina:DragonHDLatestNeural", "de-DE", "Seraphina"),
    sdk_voice("ja-JP-Nanami:DragonHDLatestNeural", "ja-JP", "Nanami"),
    sdk_voice("zh-CN-Yunfan:DragonHDLatestNeural", "zh-CN", "Yunfan", "Male"),
    sdk_voice("de-DE-Conrad:DragonHDOmniLatestNeural", "de-DE", "Conrad", "Male"),
    sdk_voice("en-US-Jimmie:DragonHDFlashLatestNeural", "en-US", "Jimmie", "Male"),
    sdk_voice("en-US-AlloyTurboMultilingualNeural", "en-US", "Alloy", "Male"),
    sdk_voice("fr-FR-DeniseNeural", "fr-FR", "Denise"),
    sdk_voice("pt-BR-FranciscaNeural", "pt-BR", "Francisca"),
    sdk_voice("sr-Latn-RS-NicholasNeural", "sr-Latn-RS", "Nicholas", "Male"),
]


@pytest.fixture(autouse=True)
def _clear_voice_cache():
    """The async regional service owns the single resource-scoped cache."""
    voice_catalog._cache.clear()
    voice_catalog._failures.clear()
    voice_catalog._pending.clear()
    yield
    voice_catalog._cache.clear()
    voice_catalog._failures.clear()
    voice_catalog._pending.clear()


@pytest.fixture
def region(monkeypatch):
    """Stub the live region enumeration with an arbitrary SDK-shaped voice list."""

    def _install(sdk_voices):
        converted = [
            VoiceInfo(
                name=voice.short_name,
                display_name=voice.local_name,
                local_name=voice.local_name,
                language=voice.locale,
                gender=voice.gender.name,
                category=voice_catalog.voice_category(voice.short_name),
            )
            for voice in sdk_voices
        ]
        monkeypatch.setattr(
            agent_builder,
            "discover_voice_catalog",
            AsyncMock(
                return_value=voice_catalog.VoiceDiscovery(
                    voice_catalog.speech_voice_scope(),
                    voice_catalog.VoiceSnapshot(tuple(converted), time.time()),
                )
            ),
        )
        return converted

    return _install


@pytest.fixture
def offline(monkeypatch):
    """Stub the region enumeration as unreachable (returns None)."""
    monkeypatch.setattr(
        agent_builder,
        "discover_voice_catalog",
        AsyncMock(
            return_value=voice_catalog.VoiceDiscovery(voice_catalog.speech_voice_scope(), None)
        ),
    )


# =============================================================================
# CLASSIFICATION
# =============================================================================


@pytest.mark.parametrize(
    "short_name,category,voice_type,is_hd",
    [
        ("en-US-Ava:DragonHDLatestNeural", "hd", "neural-hd", True),
        # Microsoft's docs use lowercase locales for HD names; case-sensitive
        # matching here is what used to drop HD voices entirely.
        ("en-us-ava:dragonhdlatestneural", "hd", "neural-hd", True),
        ("de-DE-Conrad:DragonHDOmniLatestNeural", "hd", "neural-hd-omni", True),
        ("zh-CN-Xiaoxiao:DragonHDFlashLatestNeural", "hd", "neural-hd-flash", True),
        ("en-US-AlloyTurboMultilingualNeural", "turbo", "neural-turbo", False),
        ("en-US-Ethan:MAI-Voice-2", "mai", "mai", False),
        ("en-US-Harper:MAI-Voice-2.1", "mai", "mai", False),
        ("en-US-Harper:MAI-Voice-2.1-Flash", "mai", "mai", False),
        ("fr-FR-DeniseNeural", "standard", "neural", False),
    ],
)
def test_classify_voice_name(short_name, category, voice_type, is_hd):
    assert _classify_voice_name(short_name) == (category, voice_type, is_hd)


@pytest.mark.parametrize(
    "short_name,locale",
    [
        ("en-US-AvaMultilingualNeural", "en-US"),
        ("en-US-Ava:DragonHDLatestNeural", "en-US"),
        ("ja-JP-Nanami:DragonHDLatestNeural", "ja-JP"),
        ("sr-Latn-RS-NicholasNeural", "sr-Latn-RS"),
    ],
)
def test_locale_from_short_name(short_name, locale):
    assert _locale_from_short_name(short_name) == locale


# =============================================================================
# STATIC CATALOG
# =============================================================================


def test_catalog_covers_documented_hd_voices():
    """The curated HD catalog must cover the documented DragonHD personas, not
    just the four en-US voices it originally shipped with."""
    names = {v.name for v in _HD_CATALOG}
    for expected in (
        "en-US-Ava:DragonHDLatestNeural",
        "en-US-Andrew:DragonHDLatestNeural",
        "en-US-Steffan:DragonHDLatestNeural",
        "en-US-Aria:DragonHDLatestNeural",
        "de-DE-Seraphina:DragonHDLatestNeural",
        "es-ES-Ximena:DragonHDLatestNeural",
        "fr-FR-Remy:DragonHDLatestNeural",
        "ja-JP-Nanami:DragonHDLatestNeural",
        "zh-CN-Yunfan:DragonHDLatestNeural",
    ):
        assert expected in names, f"missing documented HD voice {expected}"

    # Regional representation: HD is not an en-US-only family.
    assert {v.language for v in _HD_CATALOG} >= {
        "en-US",
        "de-DE",
        "es-ES",
        "fr-FR",
        "ja-JP",
        "zh-CN",
    }
    assert all(v.is_hd and v.category == "hd" for v in _HD_CATALOG)


def test_mai_catalog_offers_both_2_1_models_for_every_documented_persona():
    """MAI-Voice-2.1 presets replace the 2.0 presets; Flash is listed first."""
    names = {v.name for v in _MAI_CATALOG}
    for persona in ("en-US-Harper", "en-US-Sage", "es-MX-Valeria", "zh-CN-Wei", "vi-VN-Harper"):
        assert f"{persona}:MAI-Voice-2.1-Flash" in names
        assert f"{persona}:MAI-Voice-2.1" in names
    assert len(names) == len(_MAI_CATALOG) and len(_MAI_CATALOG) % 2 == 0
    assert _MAI_CATALOG[0].name.endswith(":MAI-Voice-2.1-Flash")
    assert not any(v.name.endswith((":MAI-Voice-2", ":MAI-Voice-2-Flash")) for v in _MAI_CATALOG)
    assert all(v.category == "mai" and v.voice_type == "mai" for v in _MAI_CATALOG)
    assert names <= {v.name for v in AVAILABLE_VOICES}
    harry = next(v for v in _MAI_CATALOG if v.name == "en-GB-Harry:MAI-Voice-2.1")
    assert (harry.language, harry.gender, harry.display_name) == (
        "en-GB",
        "Male",
        "Harry · en-GB (MAI-Voice-2.1)",
    )


def test_catalog_entries_are_self_consistent():
    """Category / voice_type / is_hd are derived from the short name so a typo
    can't mislabel or hide a voice."""
    for v in AVAILABLE_VOICES:
        assert (v.category, v.voice_type, v.is_hd) == _classify_voice_name(v.name)


# =============================================================================
# ENDPOINT — REGION IS THE SOURCE
# =============================================================================


def test_region_voices_are_the_source_not_a_filter(region):
    """Voices the region supports must be returned even when they aren't in the
    curated catalog. This is the core regression."""
    region(REGION_SAMPLE)
    payload = call()

    names = {v["name"] for v in payload["voices"]}
    assert payload["verified_against_region"] is True
    assert payload["source"] == "region-validated"
    # Not in the curated catalog, but supported by the region → must be offered.
    assert "fr-FR-DeniseNeural" in names
    assert "pt-BR-FranciscaNeural" in names
    assert "sr-Latn-RS-NicholasNeural" in names
    assert payload["total"] == len(REGION_SAMPLE)


def test_hd_voices_are_included_and_tagged(region):
    region(REGION_SAMPLE)
    payload = call()

    hd = [v for v in payload["voices"] if v["is_hd"]]
    assert payload["hd_total"] == len(hd) == 7
    assert {v["name"] for v in hd} == {
        "en-US-Ava:DragonHDLatestNeural",
        "en-US-Steffan:DragonHDLatestNeural",
        "de-DE-Seraphina:DragonHDLatestNeural",
        "ja-JP-Nanami:DragonHDLatestNeural",
        "zh-CN-Yunfan:DragonHDLatestNeural",
        "de-DE-Conrad:DragonHDOmniLatestNeural",
        "en-US-Jimmie:DragonHDFlashLatestNeural",
    }
    assert all(v["category"] == "hd" for v in hd)

    by_type = {v["name"]: v["voice_type"] for v in hd}
    assert by_type["en-US-Ava:DragonHDLatestNeural"] == "neural-hd"
    assert by_type["de-DE-Conrad:DragonHDOmniLatestNeural"] == "neural-hd-omni"
    assert by_type["en-US-Jimmie:DragonHDFlashLatestNeural"] == "neural-hd-flash"


def test_regional_coverage_is_preserved(region):
    """Non-en-US locales must survive; nothing filters down to a single locale."""
    region(REGION_SAMPLE)
    payload = call()

    assert set(payload["locales"]) >= {"de-DE", "en-US", "fr-FR", "ja-JP", "pt-BR", "zh-CN"}
    assert payload["locale_count"] == len(payload["locales"])
    hd_locales = {v["language"] for v in payload["voices"] if v["is_hd"]}
    assert hd_locales >= {"en-US", "de-DE", "ja-JP", "zh-CN"}


def test_voices_are_grouped_hd_first_and_sorted_by_category(region):
    """MUI's Autocomplete groupBy requires options pre-sorted by group."""
    region(REGION_SAMPLE)
    payload = call()

    categories = [v["category"] for v in payload["voices"]]
    assert categories[0] == "hd"
    # Each category appears as one contiguous run.
    runs = [c for i, c in enumerate(categories) if i == 0 or categories[i - 1] != c]
    assert len(runs) == len(set(runs))
    assert payload["category_counts"]["hd"] == 7


def test_metadata_is_populated_for_labelling(region):
    region(REGION_SAMPLE)
    payload = call()

    ava_hd = next(v for v in payload["voices"] if v["name"] == "en-US-Ava:DragonHDLatestNeural")
    assert ava_hd["is_hd"] is True
    assert ava_hd["language"] == "en-US"
    assert ava_hd["region_verified"] is True
    assert ava_hd["gender"] == "Female"

    nanami = next(v for v in payload["voices"] if v["name"] == "ja-JP-Nanami:DragonHDLatestNeural")
    # Non-default locales carry the locale in the label so the picker is scannable.
    assert "ja-JP" in nanami["display_name"]
    assert "HD" in nanami["display_name"]


# =============================================================================
# ENDPOINT — FILTERS
# =============================================================================


def test_category_filter(region):
    region(REGION_SAMPLE)
    payload = call(category="hd")
    assert payload["total"] == 7
    assert all(v["category"] == "hd" for v in payload["voices"])


def test_hd_only_filter(region):
    region(REGION_SAMPLE)
    payload = call(hd_only=True)
    assert payload["total"] == 7
    assert all(v["is_hd"] for v in payload["voices"])


def test_locale_filter_is_case_insensitive(region):
    region(REGION_SAMPLE)
    payload = call(locale="ja-jp")
    assert payload["total"] == 1
    assert payload["voices"][0]["name"] == "ja-JP-Nanami:DragonHDLatestNeural"


# =============================================================================
# REGION ENUMERATION (SDK SEAM)
# =============================================================================


def test_fetch_region_voices_reads_sdk_and_caches(monkeypatch):
    """Exercise the real async discovery path with a stubbed synthesizer so
    the SDK → VoiceInfo conversion and the 10-minute cache are covered."""
    speechsdk = pytest.importorskip("azure.cognitiveservices.speech")

    calls = {"n": 0}

    class _Synth:
        def __init__(self, speech_config=None, audio_config=None):
            pass

        def get_voices_async(self):
            calls["n"] += 1
            return SimpleNamespace(
                get=lambda: SimpleNamespace(
                    reason=speechsdk.ResultReason.VoicesListRetrieved,
                    voices=list(REGION_SAMPLE),
                )
            )

    monkeypatch.setattr(speechsdk, "SpeechSynthesizer", _Synth)
    monkeypatch.setattr(speechsdk, "SpeechConfig", lambda **kwargs: object())
    monkeypatch.setattr(
        voice_catalog,
        "speech_voice_scope",
        lambda: voice_catalog.SpeechVoiceScope("westus2", "", "", "test-key"),
    )

    snapshot = asyncio.run(voice_catalog.discover_voice_catalog()).snapshot
    voices = snapshot.voices
    assert voices is not None
    assert len(voices) == len(REGION_SAMPLE)
    assert sum(1 for v in voices if v.is_hd) == 7
    assert all(v.region_verified for v in voices)

    # Second call is served from the cache — no extra Azure round-trip.
    asyncio.run(voice_catalog.discover_voice_catalog())
    assert calls["n"] == 1

    # The endpoint's refresh=True maps to use_cache=False on the shared service.
    asyncio.run(voice_catalog.discover_voice_catalog(use_cache=False))
    assert calls["n"] == 2


def test_fetch_region_voices_returns_none_when_speech_unconfigured(monkeypatch):
    monkeypatch.setattr(
        voice_catalog, "speech_voice_scope", lambda: voice_catalog.SpeechVoiceScope("", "", "", "")
    )
    result = asyncio.run(voice_catalog.discover_voice_catalog())
    assert result.snapshot is None
    assert "no configured Speech" in result.warning


# =============================================================================
# ENDPOINT — DEGRADED PATHS
# =============================================================================


def test_hd_catalog_backfills_when_region_reports_no_hd(region):
    """If the region enumerates zero HD voices we surface the documented HD
    catalog as unverified with an explicit note, rather than silently showing
    no HD option at all."""
    region([v for v in REGION_SAMPLE if "dragonhd" not in v.short_name.lower()])
    payload = call()

    assert payload["hd_from_catalog"] is True
    assert payload["hd_total"] == len(_HD_CATALOG)
    assert payload["notes"], "an explanatory note must be surfaced to the UI"
    assert any("HD" in n for n in payload["notes"])
    hd = [v for v in payload["voices"] if v["is_hd"]]
    assert all(v["region_verified"] is False for v in hd)


def test_no_hd_backfill_when_region_reports_hd(region):
    region(REGION_SAMPLE)
    payload = call()
    assert payload["hd_from_catalog"] is False
    assert payload["notes"] == []


def test_offline_falls_back_to_catalog_with_hd(offline):
    """When Azure is unreachable the picker still offers the full HD catalog and
    says so, instead of pretending the list is authoritative."""
    payload = call()

    assert payload["verified_against_region"] is False
    assert payload["source"] == "static-catalog"
    assert payload["notes"]
    assert payload["hd_total"] == len(_HD_CATALOG)
    # Preview MAI voices stay opt-in on the unverified path.
    assert payload["category_counts"].get("mai", 0) == 0
    assert all(v["region_verified"] is False for v in payload["voices"])


def test_offline_include_unverified_adds_preview_voices(offline):
    payload = call(include_unverified=True)
    assert payload["category_counts"]["mai"] > 0
    assert payload["total"] == len(AVAILABLE_VOICES)


def test_include_unverified_supplements_region_list(region):
    """Opting in must add catalog voices the region didn't enumerate without
    dropping any region voice."""
    region(REGION_SAMPLE)
    verified_names = {v["name"] for v in call()["voices"]}
    supplemented = call(include_unverified=True)
    names = {v["name"] for v in supplemented["voices"]}

    assert verified_names <= names
    assert supplemented["total"] > len(verified_names)
    assert supplemented["category_counts"]["mai"] > 0


def test_discovered_mai_voices_are_badged_with_their_own_model(region):
    """Uncurated MAI voices keep their actual model in the label, including legacy 2.0."""
    region(
        [
            sdk_voice("en-US-Nova:MAI-Voice-2.1-Flash", "en-US", "Nova"),
            sdk_voice("en-US-Nova:MAI-Voice-2", "en-US", "Nova"),
        ]
    )
    labels = {v["name"]: v["display_name"] for v in call()["voices"]}
    assert labels["en-US-Nova:MAI-Voice-2.1-Flash"] == "Nova (MAI-Voice-2.1-Flash)"
    assert labels["en-US-Nova:MAI-Voice-2"] == "Nova (MAI-Voice-2)"


def test_mai_voice_catalog_and_regions_are_advertised_separately(region):
    """The picker can always offer MAI voices and judge region support without
    MAI leaking into the region-verified ``voices`` list."""
    discovered = "en-US-Harper:MAI-Voice-2.1-Flash"
    region([sdk_voice(discovered, "en-US", "Harper"), *REGION_SAMPLE])
    payload = call()

    assert payload["mai_voice_regions"] == list(agent_builder.MAI_VOICE_REGIONS)
    assert len(payload["mai_voice_regions"]) == 14
    assert {"swedencentral", "eastus2"} <= set(payload["mai_voice_regions"])
    assert "northcentralus" not in payload["mai_voice_regions"]

    catalog = {v["name"] for v in payload["mai_voice_catalog"]}
    assert catalog == {v.name for v in _MAI_CATALOG} - {discovered}
    assert all(v["region_verified"] is False for v in payload["mai_voice_catalog"])
    assert [v["name"] for v in payload["voices"] if v["category"] == "mai"] == [discovered]


def test_response_shape_is_backward_compatible(region):
    region(REGION_SAMPLE)
    payload = call()
    for key in (
        "status",
        "total",
        "voices",
        "by_category",
        "default_voice",
        "verified_against_region",
        "source",
        "response_time_ms",
    ):
        assert key in payload
    assert payload["status"] == "success"
    assert sum(len(v) for v in payload["by_category"].values()) == payload["total"]
    for voice in payload["voices"]:
        assert {"name", "display_name", "category", "language"} <= set(voice)


# =============================================================================
# RESOURCE / REGION ATTRIBUTION
# =============================================================================
# The Speech resource that synthesizes these voices is a specific account in a
# specific region, and it is frequently not the region the backend runs in. The
# picker has to be able to say which one, so the user can weigh the round trip
# every Cascade TTS/STT hop pays.


def test_voices_payload_names_the_speech_resource_and_region(region, monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_ENDPOINT", "https://contoso-aif.cognitiveservices.azure.com/")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "northcentralus")
    monkeypatch.setenv("CONTAINER_APP_ENV_DNS_SUFFIX", "calmstone.westus2.azurecontainerapps.io")
    region(REGION_SAMPLE)

    payload = call()

    assert payload["resource_name"] == "contoso-aif"
    assert payload["endpoint_host"] == "contoso-aif.cognitiveservices.azure.com"
    assert payload["region"] == "northcentralus"
    assert payload["region_key"] == "northcentralus"
    assert payload["region_source"] == "config"
    assert payload["app_region_key"] == "westus2"


def test_voices_payload_leaves_region_unknown_when_unconfigured(region, monkeypatch):
    """Never guess a region — the UI hides the attribution instead."""
    monkeypatch.delenv("AZURE_SPEECH_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    region(REGION_SAMPLE)

    payload = call()

    assert payload["region"] is None
    assert payload["region_source"] == ""
    assert payload["resource_name"] == ""
