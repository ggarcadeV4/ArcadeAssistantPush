import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary'
import './index.css'
import { ProfileProvider } from './context/ProfileContext.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ErrorBoundary>
        <ProfileProvider>
          <App />
        </ProfileProvider>
      </ErrorBoundary>
    </BrowserRouter>
  </React.StrictMode>,
)
