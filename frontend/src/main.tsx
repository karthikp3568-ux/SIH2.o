import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import { App } from './App'
import { AppProvider } from './state/AppContext'
import './styles/global.css'
import './styles/screens.css'
import './styles/skills.css'
import './styles/profile.css'
import './styles/pathways.css'
import './styles/journey.css'
import './styles/admin.css'

const container = document.getElementById('root')
if (!container) throw new Error('Root element is missing from index.html')

ReactDOM.createRoot(container).render(
  <React.StrictMode>
    <BrowserRouter>
      <AppProvider>
        <App />
      </AppProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
