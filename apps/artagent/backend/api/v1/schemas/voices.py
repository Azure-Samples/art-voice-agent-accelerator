"""Speech voice catalog metadata shared by authoring clients."""

from __future__ import annotations

from typing import ClassVar, Literal

from apps.artagent.backend.api.v1.models.base import BaseModel
from pydantic import Field


class VoiceInfo(BaseModel):
    """A Speech voice's service identifier and discoverable capabilities."""

    id: ClassVar[None] = None
    name: str
    display_name: str
    category: str
    language: str = "en-US"
    local_name: str = ""
    gender: str | None = None
    voice_type: str = ""
    service_voice_type: str = ""
    is_hd: bool = False
    region_verified: bool = False
    styles: list[str] = Field(default_factory=list)
    status: str = ""


class VoiceCatalogResponse(BaseModel):
    """A full regional snapshot or an explicitly limited fallback catalog."""

    id: ClassVar[None] = None
    status: Literal["success", "degraded"]
    total: int
    total_available: int
    voices: list[VoiceInfo]
    by_category: dict[str, list[VoiceInfo]]
    category_counts: dict[str, int] = Field(default_factory=dict)
    hd_total: int = 0
    locales: list[str] = Field(default_factory=list)
    locale_count: int = 0
    runtime_transcription_models: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Backend transcription routing support by orchestration mode, "
            "not regional model or voice availability."
        ),
    )
    default_voice: str
    verified_against_region: bool
    catalog_complete: bool
    hd_from_catalog: bool = False
    mai_voice_regions: list[str] = Field(
        default_factory=list,
        description="Documented Azure regions (slug form) that serve MAI-Voice models.",
    )
    mai_voice_catalog: list[VoiceInfo] = Field(
        default_factory=list,
        description=(
            "Documented MAI voices the regional catalog did not return, marked "
            "region_verified=false. Kept out of `voices` so MAI stays opt-in there."
        ),
    )
    source: str
    region: str | None = None
    resource_host: str | None = None
    resource_name: str = ""
    endpoint_host: str = ""
    region_key: str = ""
    region_source: str = ""
    app_region: str = ""
    app_region_key: str = ""
    cached: bool = False
    stale: bool = False
    retrieved_at: float | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    response_time_ms: float
