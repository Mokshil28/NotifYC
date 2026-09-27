import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { LiveShell } from './live-shell'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <LiveShell>
      <App />
    </LiveShell>
  </React.StrictMode>,
)
