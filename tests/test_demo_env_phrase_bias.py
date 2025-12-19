import types
from datetime import UTC, datetime

import pytest
from apps.artagent.backend.api.v1.endpoints import demo_env
from apps.artagent.backend.api.v1.endpoints.demo_env import DemoUserProfile


class DummyManager:
    def __init__(self):
        self.calls = []

    async def add_phrases(self, phrases):
        self.calls.append(list(phrases))
        return len([p for p in phrases if p])


@pytest.mark.asyncio
async def test_phrase_bias_helper_adds_full_and_institution_names():
    manager = DummyManager()
    request = types.SimpleNamespace(
        app=types.SimpleNamespace(state=types.SimpleNamespace(speech_phrase_manager=manager))
    )

    profile = DemoUserProfile(
        client_id="id",
        full_name="Ada Lovelace",
        email="ada@example.com",
        phone_number=None,
        relationship_tier="Gold",
        created_at=datetime.now(UTC),
        institution_name="Fabrikam Capital",
        company_code="FAB-1234",
        company_code_last4="1234",
        client_type="institutional",
        authorization_level="advisor",
        max_transaction_limit=1000,
        mfa_required_threshold=100,
        contact_info={},
        verification_codes={},
        mfa_settings={},
        compliance={},
        customer_intelligence={},
    )

    await demo_env._append_phrase_bias_entries(profile, request)

    assert manager.calls == [["Ada Lovelace", "Fabrikam Capital"]]
