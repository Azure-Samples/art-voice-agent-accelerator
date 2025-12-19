import pytest
from src.speech.phrase_list_manager import (
    PhraseListManager,
    get_global_phrase_manager,
    get_global_phrase_snapshot,
    parse_phrase_entries,
    set_global_phrase_manager,
)


def test_parse_phrase_entries_normalizes_whitespace():
    assert parse_phrase_entries("  alpha , , beta ") == {"alpha", "beta"}


@pytest.mark.asyncio
async def test_phrase_manager_adds_and_deduplicates():
    manager = PhraseListManager(initial_phrases=["Contoso"])

    first_add = await manager.add_phrase("Fabrikam")
    second_add = await manager.add_phrase("Fabrikam")

    snapshot = await manager.snapshot()

    assert first_add is True
    assert second_add is False
    assert snapshot == ["Contoso", "Fabrikam"]


@pytest.mark.asyncio
async def test_global_manager_registration_restores(monkeypatch):
    original_manager = get_global_phrase_manager()
    try:
        custom_manager = PhraseListManager(initial_phrases=["Ada", "Contoso"])
        set_global_phrase_manager(custom_manager)

        snapshot = await get_global_phrase_snapshot()
        assert snapshot == ["Ada", "Contoso"]
    finally:
        set_global_phrase_manager(original_manager)
