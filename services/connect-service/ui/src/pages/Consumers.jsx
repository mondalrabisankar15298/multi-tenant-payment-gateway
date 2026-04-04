import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

const SCOPE_OPTIONS = [
  'payments:read', 'customers:read', 'refunds:read',
  'events:read', 'merchants:read', 'webhooks:manage',
]

export default function Consumers() {
  const [consumers, setConsumers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newSecret, setNewSecret] = useState(null)
  const [form, setForm] = useState({ name: '', description: '', scopes: ['payments:read', 'customers:read'] })
  const navigate = useNavigate()

  useEffect(() => { loadConsumers() }, [])

  async function loadConsumers() {
    try {
      const res = await api.listConsumers()
      setConsumers(res.data || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate(e) {
    e.preventDefault()
    try {
      const res = await api.createConsumer(form)
      setNewSecret(res.data)
      await loadConsumers()
    } catch (err) {
      alert(err.message)
    }
  }

  async function handleSuspend(id) {
    if (!confirm('Suspend this consumer?')) return
    await api.suspendConsumer(id)
    await loadConsumers()
  }

  async function handleActivate(id) {
    await api.activateConsumer(id)
    await loadConsumers()
  }

  function getBadgeClass(status) {
    const map = { active: 'badge-active', suspended: 'badge-suspended', revoked: 'badge-revoked' }
    return `badge ${map[status] || 'badge-pending'}`
  }

  if (loading) return <div className="loading"><div className="spinner" /> Loading...</div>

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2>Consumers</h2>
          <p>Manage third-party consumer integrations</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ Add Consumer</button>
      </div>

      {consumers.length === 0 ? (
        <div className="empty-state">
          <h3>No consumers yet</h3>
          <p>Create your first third-party consumer to get started.</p>
        </div>
      ) : (
        <div className="card">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Client ID</th>
                <th>Status</th>
                <th>Scopes</th>
                <th>Rate Limit</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {consumers.map(c => (
                <tr key={c.consumer_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/consumers/${c.consumer_id}`)}>
                  <td style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{c.name}</td>
                  <td className="mono">{c.client_id?.slice(0, 16)}...</td>
                  <td><span className={getBadgeClass(c.status)}>{c.status}</span></td>
                  <td>{(c.scopes || []).length} scopes</td>
                  <td>{c.rate_limit_requests}/{c.rate_limit_window_seconds}s</td>
                  <td onClick={e => e.stopPropagation()}>
                    {c.status === 'active' ? (
                      <button className="btn btn-sm btn-secondary" onClick={() => handleSuspend(c.consumer_id)}>Suspend</button>
                    ) : c.status === 'suspended' ? (
                      <button className="btn btn-sm btn-primary" onClick={() => handleActivate(c.consumer_id)}>Activate</button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Consumer Modal */}
      {showCreate && (
        <div className="modal-overlay" onClick={() => { setShowCreate(false); setNewSecret(null) }}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            {newSecret ? (
              <>
                <h3>Consumer Created ✓</h3>
                <div className="secret-box">
                  <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>Client ID</label>
                  <code>{newSecret.client_id}</code>
                </div>
                <div className="secret-box">
                  <label style={{ fontSize: 12, color: 'var(--text-muted)' }}>Client Secret</label>
                  <code>{newSecret.client_secret}</code>
                  <p>⚠ This secret will NOT be shown again. Save it now!</p>
                </div>
                <div className="modal-actions">
                  <button className="btn btn-primary" onClick={() => { setShowCreate(false); setNewSecret(null) }}>Done</button>
                </div>
              </>
            ) : (
              <form onSubmit={handleCreate}>
                <h3>Add Consumer</h3>
                <div className="form-group">
                  <label>Name</label>
                  <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
                </div>
                <div className="form-group">
                  <label>Description</label>
                  <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} rows={3} />
                </div>
                <div className="form-group">
                  <label>Scopes</label>
                  {SCOPE_OPTIONS.map(scope => (
                    <label key={scope} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: 13 }}>
                      <input
                        type="checkbox"
                        checked={form.scopes.includes(scope)}
                        onChange={e => {
                          setForm(prev => ({
                            ...prev,
                            scopes: e.target.checked
                              ? [...prev.scopes, scope]
                              : prev.scopes.filter(s => s !== scope),
                          }))
                        }}
                      />
                      <code style={{ fontSize: 12, color: 'var(--accent)' }}>{scope}</code>
                    </label>
                  ))}
                </div>
                <div className="modal-actions">
                  <button type="button" className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
                  <button type="submit" className="btn btn-primary">Create Consumer</button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
