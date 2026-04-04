import React, { useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Consumers from './pages/Consumers'
import ConsumerDetail from './pages/ConsumerDetail'
import { api } from './api/client'

export default function App() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('admin_api_key') || '')
  const [keySubmitted, setKeySubmitted] = useState(!!apiKey)

  function handleKeySubmit(e) {
    e.preventDefault()
    if (apiKey.trim()) {
      api.setAdminKey(apiKey.trim())
      setKeySubmitted(true)
    }
  }

  if (!keySubmitted) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0a0e1a',
        fontFamily: 'Inter, sans-serif',
      }}>
        <div style={{
          background: '#1a1f35',
          border: '1px solid #2d3555',
          borderRadius: 12,
          padding: 40,
          width: 400,
        }}>
          <h2 style={{ color: '#f0f2f7', marginBottom: 8, fontSize: 22 }}>Connect Gateway Admin</h2>
          <p style={{ color: '#8892b0', fontSize: 14, marginBottom: 24 }}>Enter your admin API key to access the console.</p>
          <form onSubmit={handleKeySubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#8892b0', marginBottom: 6 }}>
                Admin API Key
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder="dev-admin-key-change-in-production"
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  background: '#1e2540',
                  border: '1px solid #2d3555',
                  borderRadius: 8,
                  color: '#f0f2f7',
                  fontSize: 14,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
                autoFocus
              />
            </div>
            <button
              type="submit"
              style={{
                width: '100%',
                padding: '10px 18px',
                background: '#6366f1',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Sign In
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <BrowserRouter basename="/admin">
      <div className="app-layout">
        <aside className="sidebar">
          <div className="sidebar-logo">
            <h1>Connect Gateway</h1>
            <span>Admin Console</span>
          </div>
          <nav className="sidebar-nav">
            <NavLink to="/" end>📊 Dashboard</NavLink>
            <NavLink to="/consumers">👥 Consumers</NavLink>
          </nav>
          <div style={{ padding: '0 12px', marginTop: 'auto' }}>
            <button
              onClick={() => {
                localStorage.removeItem('admin_api_key')
                setKeySubmitted(false)
              }}
              style={{
                width: '100%',
                padding: '8px 12px',
                background: 'transparent',
                border: '1px solid #2d3555',
                borderRadius: 8,
                color: '#8892b0',
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              🔑 Change API Key
            </button>
          </div>
        </aside>
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/consumers" element={<Consumers />} />
            <Route path="/consumers/:id" element={<ConsumerDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
