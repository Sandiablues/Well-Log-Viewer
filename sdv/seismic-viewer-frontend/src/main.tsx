import { StrictMode } from 'react'
import { installMultiViewerThemeRuntime } from './themeRuntime'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import SystemMonitorPage from './components/SystemMonitorPage'
import "./styles/seismic-viewer-actions.css";
installMultiViewerThemeRuntime()
const searchParams = new URLSearchParams(window.location.search)
const isSystemMonitorPage = searchParams.get('system-monitor') === '1'
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isSystemMonitorPage ? <SystemMonitorPage /> : <App />}
  </StrictMode>,
)
