# **ARTVoice Frontend**

**React voice interface** with WebSocket real-time communication for Azure Communication Services.

## **Quick Start**

```bash
npm install
npm run dev  # http://localhost:5173
```

## **Architecture**

```
frontend/
├── src/
│   ├── main.jsx              # React entry point
│   ├── App.jsx               # App wrapper
│   └── components/
│       └── RealTimeVoiceApp.jsx  # Complete voice app
├── package.json
└── .env                      # Backend URL configuration
```

## **Features**

- **Real-time Voice Processing** - WebAudio API integration
- **WebSocket Communication** - Live backend connectivity  
- **Azure Communication Services** - Phone call integration
- **Health Monitoring** - Backend status indicators

## **Configuration**

```bash
# .env
VITE_BACKEND_BASE_URL=http://localhost:8000
```

## **Key Dependencies**

- **React 19** - Core framework
- **Vite** - Build tool and dev server
- **Azure Communication Services** - Voice calling SDK
- **Microsoft Cognitive Services** - Speech SDK

## UI Components

**Main Interface**:
- 768px fixed width
- Voice controls (start/stop, phone)
- Real-time waveform animation
- Message bubbles with timestamps
- Backend health status
- Help system modal
