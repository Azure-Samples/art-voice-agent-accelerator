import sys
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Disable telemetry for tests
os.environ["DISABLE_CLOUD_TELEMETRY"] = "true"

# Set required environment variables for CI
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_CHAT_DEPLOYMENT_ID", "test-deployment")
os.environ.setdefault("AZURE_SPEECH_KEY", "test-speech-key")
os.environ.setdefault("AZURE_SPEECH_REGION", "test-region")

# Mock PortAudio-dependent modules before any imports
sounddevice_mock = MagicMock()
sounddevice_mock.default.device = [0, 1]
sounddevice_mock.default.samplerate = 44100
sounddevice_mock.default.channels = [1, 2]
sounddevice_mock.query_devices.return_value = []
sounddevice_mock.InputStream = MagicMock
sounddevice_mock.OutputStream = MagicMock
sys.modules['sounddevice'] = sounddevice_mock

# Mock pyaudio for CI environments
pyaudio_mock = MagicMock()
pyaudio_mock.PyAudio.return_value = MagicMock()
pyaudio_mock.paInt16 = 8
pyaudio_mock.paContinue = 0
sys.modules['pyaudio'] = pyaudio_mock

# Mock Azure Speech SDK specifically to avoid authentication requirements in CI
# Only mock if the real package is not available
try:
    import azure.cognitiveservices.speech
except ImportError:
    azure_speech_mock = MagicMock()
    azure_speech_mock.SpeechConfig.from_subscription.return_value = MagicMock()
    azure_speech_mock.AudioConfig.use_default_microphone.return_value = MagicMock()
    azure_speech_mock.SpeechRecognizer.return_value = MagicMock()
    sys.modules['azure.cognitiveservices.speech'] = azure_speech_mock

# Mock the problematic Lvagent audio_io module to prevent PortAudio imports
audio_io_mock = MagicMock()
audio_io_mock.MicSource = MagicMock
audio_io_mock.SpeakerSink = MagicMock
audio_io_mock.pcm_to_base64 = MagicMock(return_value="mock_base64_data")
sys.modules['apps.rtagent.backend.src.agents.Lvagent.audio_io'] = audio_io_mock

# Mock the entire Lvagent module to prevent any problematic imports
lvagent_mock = MagicMock()
lvagent_mock.build_lva_from_yaml = MagicMock(return_value=MagicMock())
sys.modules['apps.rtagent.backend.src.agents.Lvagent'] = lvagent_mock
sys.modules['apps.rtagent.backend.src.agents.Lvagent.factory'] = lvagent_mock
sys.modules['apps.rtagent.backend.src.agents.Lvagent.base'] = lvagent_mock

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
