# 🧪 Advanced Labs

This section contains experimental notebooks and deep technical explorations for developers working with the Real-Time Audio Agent framework.

## 📁 Lab Organization

### **Development Labs (`dev/`)**
Production-ready experiments for extending and optimizing the voice agent framework.

### **Voice Testing (`podcast_voice_tests/`)**
Audio quality benchmarks and TTS model comparisons with sample outputs.

### **Recordings (`recordings/`)**
Test audio files and conversation samples for development and debugging.

## 🚀 **Getting Started with Labs**

### **Prerequisites**
1. Complete `hello_world/` tutorials first
2. Understand basic ARTAgent framework concepts
3. Have Azure services configured and tested

### **Recommended Lab Sequence**

#### **For System Understanding**
1. `01-build-your-audio-agent.ipynb` (full pipeline)
2. `03-latency-arena.ipynb` (performance baseline)
3. `voice-live.ipynb` (real-time validation)

#### **For Audio Optimization**
1. `06-text-to-speech.ipynb` (TTS basics)
2. `05-speech-to-text-multilingual.ipynb` (STT tuning)
3. `07-vad.ipynb` (voice detection)

#### **For Advanced Features**
1. `04-memory-agents.ipynb` (conversation memory)
2. `08-speech-to-text-diarization.ipynb` (speaker recognition)
3. `02-how-to-use-aoai-for-realtime-transcriptions.ipynb` (advanced STT)

## ⚡ **Quick Tips**

### **Notebook Execution**
- Always run from **project root directory**
- Notebooks handle directory navigation automatically
- Each notebook includes cleanup and error handling

### **Experimentation Guidelines**
- **Safe to modify**: All code is production-tested
- **Branch before major changes**: Keep working versions
- **Document findings**: Add markdown cells with your observations

### **Performance Testing**
- Use `03-latency-arena.ipynb` for baseline measurements
- Test with realistic audio samples from `recordings/`
- Compare results against `podcast_voice_tests/` benchmarks

## 🔬 **Research & Development**

These labs are designed for:
- **Feature Development**: Extending framework capabilities
- **Performance Research**: Optimizing latency and quality
- **Integration Testing**: Validating new Azure services
- **Use Case Exploration**: Testing domain-specific applications

Feel free to fork, modify, and extend these notebooks for your specific research needs!

