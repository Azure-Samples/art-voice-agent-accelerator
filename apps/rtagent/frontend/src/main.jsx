import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './components/App.jsx'
import abstractBg from './assets/abstract.jpg'
import logger, { configureLogLevel } from './utils/logger.js'

// Set background image dynamically for proper Vite asset handling
document.body.style.backgroundImage = `url(${abstractBg})`

configureLogLevel(import.meta.env?.VITE_APP_LOG_LEVEL ?? import.meta.env?.VITE_LOG_LEVEL)
logger.info('[ARTAgent] Frontend bootstrapping')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)