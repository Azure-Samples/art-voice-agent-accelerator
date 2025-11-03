from .cosmosdb_services import CosmosDBMongoCoreManager
from .redis_services import AzureRedisManager

# Import OpenAI client with error handling for CI environments
try:
    from .openai_services import AzureOpenAIClient
except ImportError as e:
    print(f"Warning: Could not import AzureOpenAIClient: {e}")
    AzureOpenAIClient = None

from .speech_services import (
    SpeechSynthesizer,
    StreamingSpeechRecognizerFromBytes,
)

__all__ = [
    "AzureOpenAIClient",
    "CosmosDBMongoCoreManager",
    "AzureRedisManager", 
    "SpeechSynthesizer",
    "StreamingSpeechRecognizerFromBytes",
]
