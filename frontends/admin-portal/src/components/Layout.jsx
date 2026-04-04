import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import MerchantSelector from './MerchantSelector'

export default function Layout() {
  const [seeding, setSeeding] = useState(false)
  const [seedResult, setSeedResult] = useState(null)

  async function handleSeed() {
    if (!confirm('Generate seed data? This will create 5 merchants, 200 customers, 500 payments, and ~80 refunds.')) return
    setSeeding(true)
    setSeedResult(null)
    try {
      const resp = await fetch('/api/admin/seed?merchants=5&customers=200&payments=500', { method: 'POST' })
      const data = await resp.json()
      setSeedResult(data)
      if (data.status === 'success') {
        alert(`Seed complete!\n${data.message}`)
        window.location.reload()
      } else {
        alert('Seed failed: ' + (data.detail || 'Unknown error'))
      }
    } catch (err) {
      alert('Seed failed: ' + err.message)
    } finally {
      setSeeding(false)
    }
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          Pay<span>Gateway</span>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/merchants" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            🏢 Merchants
          </NavLink>
          <NavLink to="/customers" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            👤 Customers
          </NavLink>
          <NavLink to="/payments" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            💳 Payments
          </NavLink>
          <NavLink to="/refunds" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            ↩️ Refunds
          </NavLink>
          <NavLink to="/events" className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}>
            📋 Events Log
          </NavLink>
        </nav>
        <div style={{ padding: '16px', marginTop: 'auto' }}>
          <button
            onClick={handleSeed}
            disabled={seeding}
            style={{
              width: '100%',
              padding: '10px 12px',
              background: seeding ? '#555' : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: seeding ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
            }}
          >
            {seeding ? (
              <>
                <span style={{
                  width: '14px', height: '14px',
                  border: '2px solid rgba(255,255,255,0.3)',
                  borderTopColor: 'white',
                  borderRadius: '50%',
                  animation: 'spin 0.6s linear infinite',
                  display: 'inline-block',
                }} />
                Generating...
              </>
            ) : (
              <>🌱 Generate Seed Data</>
            )}
          </button>
        </div>
      </aside>
      <div className="main-content">
        <div className="top-bar">
          <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Admin Portal</div>
          <MerchantSelector />
        </div>
        <div className="page-content fade-in">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
