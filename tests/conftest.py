import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

# Disable telemetry for tests
os.environ["DISABLE_CLOUD_TELEMETRY"] = "true"

# Set required environment variables for CI
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_KEY", "test-key")  # Alternate env var
os.environ.setdefault("AZURE_OPENAI_CHAT_DEPLOYMENT_ID", "test-deployment")
os.environ.setdefault("AZURE_SPEECH_KEY", "test-speech-key")
os.environ.setdefault("AZURE_SPEECH_REGION", "test-region")

# Mock the config module before any app imports
# This provides stubs for all config values used by the application
if "config" not in sys.modules:
    from src.enums.stream_modes import StreamMode

    config_mock = ModuleType("config")
    # Core settings
    config_mock.ACS_STREAMING_MODE = StreamMode.MEDIA
    config_mock.GREETING = "Hello! How can I help you today?"
    config_mock.STOP_WORDS = ["stop", "cancel", "nevermind"]
    config_mock.DEFAULT_TTS_VOICE = "en-US-JennyNeural"
    config_mock.STT_PROCESSING_TIMEOUT = 5.0
    config_mock.DEFAULT_VOICE_RATE = "+0%"
    config_mock.DEFAULT_VOICE_STYLE = "chat"
    config_mock.GREETING_VOICE_TTS = "en-US-JennyNeural"
    config_mock.TTS_SAMPLE_RATE_ACS = 24000
    config_mock.TTS_SAMPLE_RATE_UI = 24000
    config_mock.TTS_END = ["."]
    config_mock.DTMF_VALIDATION_ENABLED = False
    config_mock.ENABLE_ACS_CALL_RECORDING = False
    # ACS settings
    config_mock.ACS_CALL_CALLBACK_PATH = "/api/v1/calls/callback"
    config_mock.ACS_CONNECTION_STRING = "test-connection-string"
    config_mock.ACS_ENDPOINT = "https://test.communication.azure.com"
    config_mock.ACS_SOURCE_PHONE_NUMBER = "+15551234567"
    config_mock.ACS_WEBSOCKET_PATH = "/api/v1/media/stream"
    config_mock.AZURE_SPEECH_ENDPOINT = "https://test.cognitiveservices.azure.com"
    config_mock.AZURE_STORAGE_CONTAINER_URL = "https://test.blob.core.windows.net/container"
    config_mock.BASE_URL = "https://test.example.com"
    # Azure settings
    config_mock.AZURE_CLIENT_ID = "test-client-id"
    config_mock.AZURE_CLIENT_SECRET = "test-secret"
    config_mock.AZURE_TENANT_ID = "test-tenant"
    config_mock.AZURE_OPENAI_ENDPOINT = "https://test.openai.azure.com"
    config_mock.AZURE_OPENAI_CHAT_DEPLOYMENT_ID = "test-deployment"
    config_mock.AZURE_OPENAI_API_VERSION = "2024-05-01"
    config_mock.AZURE_OPENAI_API_KEY = "test-key"
    # Mock functions
    config_mock.get_provider_status = lambda: {"status": "ok"}
    config_mock.refresh_appconfig_cache = lambda: None
    sys.modules["config"] = config_mock

# Mock Azure OpenAI client to avoid Azure authentication during tests
aoai_client_mock = MagicMock()
aoai_client_mock.chat = MagicMock()
aoai_client_mock.chat.completions = MagicMock()
aoai_client_mock.chat.completions.create = MagicMock()

if "src.aoai.client" not in sys.modules:
    aoai_module = ModuleType("src.aoai.client")
    aoai_module.get_client = MagicMock(return_value=aoai_client_mock)
    aoai_module.create_azure_openai_client = MagicMock(return_value=aoai_client_mock)
    sys.modules["src.aoai.client"] = aoai_module

# Mock the openai_services module that imports from src.aoai.client
if "apps.artagent.backend.src.services.openai_services" not in sys.modules:
    openai_services_mock = ModuleType("apps.artagent.backend.src.services.openai_services")
    openai_services_mock.AzureOpenAIClient = MagicMock(return_value=aoai_client_mock)
    openai_services_mock.get_client = MagicMock(return_value=aoai_client_mock)
    sys.modules["apps.artagent.backend.src.services.openai_services"] = openai_services_mock

# Mock PortAudio-dependent modules before any imports
sounddevice_mock = MagicMock()
sounddevice_mock.default.device = [0, 1]
sounddevice_mock.default.samplerate = 44100
sounddevice_mock.default.channels = [1, 2]
sounddevice_mock.query_devices.return_value = []
sounddevice_mock.InputStream = MagicMock
sounddevice_mock.OutputStream = MagicMock
sys.modules["sounddevice"] = sounddevice_mock

# Mock pyaudio for CI environments
pyaudio_mock = MagicMock()
pyaudio_mock.PyAudio.return_value = MagicMock()
pyaudio_mock.paInt16 = 8
pyaudio_mock.paContinue = 0
sys.modules["pyaudio"] = pyaudio_mock

# Mock Azure Speech SDK specifically to avoid authentication requirements in CI
# Only mock if the real package is not available
try:
    import azure.cognitiveservices.speech
except ImportError:
    azure_speech_mock = MagicMock()
    azure_speech_mock.SpeechConfig.from_subscription.return_value = MagicMock()
    azure_speech_mock.AudioConfig.use_default_microphone.return_value = MagicMock()
    azure_speech_mock.SpeechRecognizer.return_value = MagicMock()
    sys.modules["azure.cognitiveservices.speech"] = azure_speech_mock

# Mock the problematic Lvagent audio_io module to prevent PortAudio imports
audio_io_mock = MagicMock()
audio_io_mock.MicSource = MagicMock
audio_io_mock.SpeakerSink = MagicMock
audio_io_mock.pcm_to_base64 = MagicMock(return_value="mock_base64_data")
sys.modules["apps.artagent.backend.src.agents.Lvagent.audio_io"] = audio_io_mock

# Mock the entire Lvagent module to prevent any problematic imports
lvagent_mock = MagicMock()
lvagent_mock.build_lva_from_yaml = MagicMock(return_value=MagicMock())
sys.modules["apps.artagent.backend.src.agents.Lvagent"] = lvagent_mock
sys.modules["apps.artagent.backend.src.agents.Lvagent.factory"] = lvagent_mock
sys.modules["apps.artagent.backend.src.agents.Lvagent.base"] = lvagent_mock

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
