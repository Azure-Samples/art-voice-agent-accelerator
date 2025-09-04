import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './components/App.jsx'
import abstractBg from './assets/abstract.jpg'

// Set background image dynamically for proper Vite asset handling
document.body.style.backgroundImage = `url(${abstractBg})`

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)