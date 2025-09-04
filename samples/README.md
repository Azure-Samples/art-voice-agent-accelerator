# **ARTVoice Samples**

**Hands-on examples and tutorials** for building voice agents with the ARTVoice Accelerator framework.

## **Structure**

```
samples/
├── hello_world/          # Quick start tutorials
├── labs/                 # Advanced experiments and deep dives  
└── README.md             # This guide
```

## **🎯 Getting Started: Hello World**

**Best for**: Newcomers, proof-of-concept development, learning the basics.

| Notebook | Description |
|----------|-------------|
| `01-create-your-first-rt-agent.ipynb` | Build a complete customer support voice agent |
| `03-create-your-first-foundry-agents.ipynb` | Create Azure AI Foundry agents |
| `04-exploring-live-api.ipynb` | Explore Azure Live Voice API integration |
| `05-create-your-first-livevoice.ipynb` | Build with Live Voice capabilities |

### **Quick Start**
1. Start with notebook 01 if you're new to the project
2. Follow notebooks in sequence
3. Each notebook is self-contained with working examples

## **🧪 Advanced Labs**

**Best for**: Framework extension, research experiments, specific use cases.

Advanced notebooks for understanding and extending framework components.
|----------|------------|----------|
| `01-build-your-audio-agent.ipynb` | **Full Pipeline** | Complete voice-to-voice system with Azure AI |
| `02-how-to-use-aoai-for-realtime-transcriptions.ipynb` | **Speech Recognition** | Azure OpenAI STT optimization |
| `03-latency-arena.ipynb` | **Performance** | Latency measurement and optimization |
| `04-memory-agents.ipynb` | **State Management** | Conversational memory and context |
| `05-speech-to-text-multilingual.ipynb` | **Internationalization** | Multi-language speech recognition |
| `06-text-to-speech.ipynb` | **Voice Synthesis** | TTS configuration and voice selection |
| `07-vad.ipynb` | **Voice Activity** | Voice activity detection tuning |
| `08-speech-to-text-diarization.ipynb` | **Speaker Recognition** | Multi-speaker conversation handling |
| `voice-live.ipynb` | **Real-time Testing** | Live voice interaction testing |

#### **Voice Testing (`labs/podcast_voice_tests/`)**

Audio quality experiments and voice model comparisons:

- **Ground truth recordings** for quality benchmarking
- **Multiple TTS model outputs** for voice comparison
- **Production voice samples** for different use cases

#### **Recording Storage (`labs/recordings/`)**

Test recordings and audio samples for development and debugging.

---

## 🎓 **Learning Path Recommendations**

### **For Framework Newcomers**
1. **Start**: `hello_world/01-create-your-first-rt-agent.ipynb`
2. **Next**: `hello_world/02-run-test-rt-agent.ipynb`
3. **Then**: `labs/dev/01-build-your-audio-agent.ipynb`

### **For Voice Optimization**
1. `labs/dev/06-text-to-speech.ipynb` (TTS basics)
2. `labs/dev/05-speech-to-text-multilingual.ipynb` (STT tuning)
3. `labs/podcast_voice_tests/` (quality comparison)

### **For Performance Tuning**
1. `labs/dev/03-latency-arena.ipynb` (latency measurement)
2. `labs/dev/07-vad.ipynb` (voice activity detection)
3. `labs/dev/voice-live.ipynb` (real-time testing)

### **For Advanced Features**
1. `labs/dev/04-memory-agents.ipynb` (conversational memory)
2. `labs/dev/08-speech-to-text-diarization.ipynb` (speaker identification)
3. `labs/dev/02-how-to-use-aoai-for-realtime-transcriptions.ipynb` (advanced STT)

---

## ⚙️ **Prerequisites**

### **Environment Setup**
- **Python 3.11+** 
- **Dependencies**: Install with `pip install -r requirements.txt`
- **Jupyter environment** for running notebooks

### **Azure Services Required**
- **Azure Speech Services** (STT/TTS)
- **Azure OpenAI** (GPT models and function calling)
- **Azure Communication Services** (for phone integration)
- **Azure Redis** (for state management)

### **Configuration**
Ensure your `.env` file contains the required Azure service credentials before running any notebooks.

---

## 🔧 **Usage Guidelines**

### **Running Notebooks**
1. **Navigate to project root** before starting Jupyter
2. **Activate conda environment**: `conda activate audioagent`
3. **Start Jupyter**: `jupyter lab` or use VS Code
4. **Follow notebook order** for structured learning

### **Code Safety**
- ✅ **All code in notebooks is production-tested and working**
- ✅ **Feel free to experiment and modify for your use cases**
- ✅ **Each notebook includes error handling and cleanup**

### **Troubleshooting**
- **Environment issues**: Check conda environment activation
- **Import errors**: Ensure you're running from project root directory
- **Azure service errors**: Verify credentials in `.env` file

---

## 🤝 **Contributing**

### **Adding New Samples**
- **Hello World**: Add beginner-friendly, well-documented tutorials
- **Labs**: Add experimental or advanced feature demonstrations
- **Include**: Clear documentation, error handling, and cleanup code

### **Sample Guidelines**
- Keep notebooks **self-contained** with setup and cleanup
- Include **clear explanations** of what each section does
- Add **error handling** for common failure scenarios
- Test thoroughly before contributing

---

## 📞 **Need Help?**

- **Framework Documentation**: See main project README
- **API Reference**: Check `/docs/api/` folder
- **Issues**: Create GitHub issues for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions

---

*Happy building! 🎉 The samples are designed to get you productive quickly while providing deep technical insights for advanced use cases.*
