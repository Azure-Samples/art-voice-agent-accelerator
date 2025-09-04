# Real-Time Voice Agent

A production-ready Azure-powered voice agent with advanced text-to-speech and speech recognition capabilities.

## 🚀 Features

- **Real-time speech synthesis** with Azure Cognitive Services
- **Streaming speech recognition** with advanced language detection
- **Multi-language support** with automatic optimization
- **Neural voice synthesis** with customizable styles and prosody
- **OpenTelemetry observability** with distributed tracing
- **Production-ready** with comprehensive error handling and monitoring

## 🏗️ Architecture

The voice agent is built with a modular architecture optimized for low-latency real-time applications:

- **FastAPI backend** for high-performance async operations
- **Azure Communication Services** for call automation and media streaming
- **Azure Speech Services** for TTS/STT with neural voice models
- **Azure OpenAI** for intelligent conversation handling
- **OpenTelemetry** for comprehensive observability and monitoring

## 🎯 Key Components

### SpeechSynthesizer

The core text-to-speech engine providing:

- Multiple synthesis modes (speaker playback, memory synthesis, frame-based streaming)
- Flexible authentication (API key, managed identity, credential chains)
- Intelligent environment detection for headless deployments
- Advanced SSML support with style and prosody control
- Real-time frame generation for streaming applications

### StreamingSpeechRecognizer

Advanced speech-to-text engine featuring:

- Real-time streaming recognition with minimal latency
- Language detection and speaker diarization
- Neural audio processing for improved accuracy
- Comprehensive callback system for real-time processing
- Session management with proper resource cleanup

## 📊 Observability

Built-in observability features include:

- **Distributed tracing** with OpenTelemetry and Azure Monitor
- **Structured logging** with correlation IDs for request tracking
- **Performance metrics** for latency and error rate monitoring
- **Service dependency mapping** for application insights
- **Real-time monitoring** dashboards and alerting

## 🔧 Configuration

The system supports flexible configuration through:

- Environment variables for credentials and settings
- Runtime configuration for voice parameters and behavior
- Deployment-specific settings for different environments
- Automatic fallback mechanisms for robust operation

## 🌟 Getting Started

Ready to build your voice application? Check out our [Quick Start Guide](getting-started/quickstart.md) to get up and running in minutes.

For detailed API documentation, explore our [API Reference](api/overview.md) section.
