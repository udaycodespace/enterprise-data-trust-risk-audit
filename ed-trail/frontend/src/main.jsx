import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

// Uses ED-BASE AuthProvider from parent frontend
// Import: import { AuthProvider } from '../../frontend/src/providers/AuthProvider.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>,
)
