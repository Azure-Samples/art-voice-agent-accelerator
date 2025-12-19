# Ensure telemetry is disabled for unit tests to avoid the ProxyLogger/resource issue
import os

# Disable cloud telemetry so utils/ml_logging avoids attaching OpenTelemetry LoggingHandler.
# This must be set before importing modules that call get_logger() at import time.
os.environ.setdefault("DISABLE_CLOUD_TELEMETRY", "true")
# Also ensure Application Insights connection string is not set (prevents other code paths)
os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)

# Set required Azure OpenAI environment variables for CI
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_CHAT_DEPLOYMENT_ID", "test-deployment")

import asyncio


class DummyMemo:
    def __init__(self):
        self._d = {}

    def get_context(self, k, default=None):
        return self._d.get(k, default)

    def update_context(self, k, v):
        self._d[k] = v

    def set_context(self, k, v):
        self._d[k] = v

    async def persist_to_redis_async(self, redis_mgr):
        pass


class FakeAuthService:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    async def validate_pin(self, call_id, phone, pin):
        self.calls.append((call_id, phone, pin))
        # small delay to emulate I/O
        await asyncio.sleep(0.01)
        return {"ok": self.ok, "user_id": "u1"} if self.ok else {"ok": False}
