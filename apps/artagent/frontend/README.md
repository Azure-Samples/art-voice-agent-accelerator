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
├── entrypoint.sh             # Container startup (App Config integration)
└── .env                      # Local development configuration
```

## **Features**

- **Real-time Voice Processing** - WebAudio API integration
- **WebSocket Communication** - Live backend connectivity  
- **Azure Communication Services** - Phone call integration
- **Health Monitoring** - Backend status indicators

## **Configuration**

### Local Development

```bash
# .env
VITE_BACKEND_BASE_URL=http://localhost:8010
```

### Azure Deployment (App Configuration)

When deployed to Azure Container Apps, the frontend reads configuration from **Azure App Configuration** at container startup:

| App Config Key | Description |
|----------------|-------------|
| `app/frontend/backend-url` | Backend API URL (e.g., `https://backend.azurecontainerapps.io`) |
| `app/frontend/ws-url` | WebSocket URL (e.g., `wss://backend.azurecontainerapps.io`) |

The container uses managed identity to authenticate with App Configuration. Environment variables set in Container Apps:

```
AZURE_APPCONFIG_ENDPOINT=https://appconfig-xxx.azconfig.io
AZURE_APPCONFIG_LABEL=<environment>
AZURE_CLIENT_ID=<managed-identity-client-id>
```

The `entrypoint.sh` script:
1. Acquires an access token via managed identity (IMDS)
2. Fetches `backend-url` and `ws-url` from App Configuration
3. Replaces `__BACKEND_URL__` and `__WS_URL__` placeholders in built JS files
4. Starts the web server

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
