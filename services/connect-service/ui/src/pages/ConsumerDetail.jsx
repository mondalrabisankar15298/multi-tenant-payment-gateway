import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'

export default function ConsumerDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [consumer, setConsumer] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showMerchantModal, setShowMerchantModal] = useState(false)
  const [merchantIds, setMerchantIds] = useState('')
  const [apiCallsChart, setApiCallsChart] = useState([])
  const [webhooksChart, setWebhooksChart] = useState([])

  useEffect(() => { loadAll() }, [id])

  async function loadAll() {
    setLoading(true)
    try {
      const [consumerRes, statsRes] = await Promise.allSettled([
        api.getConsumer(id),
        api.getConsumerStats(id),
      ])

      if (consumerRes.status === 'fulfilled') setConsumer(consumerRes.value.data)
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data)

      // Load charts
      try {
        const apiRes = await api.getConsumerApiCalls(id, '?granularity=hour')
        setApiCallsChart(apiRes.data || [])
      } catch {}

      try {
        const whRes = await api.getConsumerWebhooks(id, '?granularity=hour')
        setWebhooksChart(whRes.data || [])
      } catch {}
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  async function handleRotateSecret() {
    if (!confirm('This will invalidate the current secret. Continue?')) return
    try {
      const res = await api.rotateSecret(id)
      alert(`New secret: ${res.data.client_secret}\n\n⚠ Save this — it won't be shown again!`)
      await loadAll()
    } catch (err) { alert(err.message) }
  }

  async function handleAssignMerchants(e) {
    e.preventDefault()
    try {
      const ids = merchantIds.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n))
      await api.assignMerchants(id, ids)
      setShowMerchantModal(false)
      setMerchantIds('')
      await loadAll()
    } catch (err) { alert(err.message) }
  }

  async function handleRemoveMerchant(merchantId) {
    if (!confirm(`Remove merchant ${merchantId} access?`)) return
    await api.removeMerchant(id, merchantId)
    await loadAll()
  }

  async function handleSuspend() {
    if (!confirm('Suspend this consumer?')) return
    await api.suspendConsumer(id)
    await loadAll()
  }

  async function handleActivate() {
    await api.activateConsumer(id)
    await loadAll()
  }

  async function handleRevoke() {
    if (!confirm('PERMANENTLY revoke this consumer? This cannot be undone.')) return
    await api.deleteConsumer(id)
    navigate('/consumers')
  }

  if (loading) return <div className="loading"><div className="spinner" /> Loading...</div>
  if (!consumer) return <div className="empty-state"><h3>Consumer not found</h3></div>

  const statusBadge = {
    active: 'badge-active',
    suspended: 'badge-suspended',
    revoked: 'badge-revoked',
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <button className="btn btn-secondary btn-sm" onClick={() => navigate('/consumers')} style={{ marginBottom: 12 }}>
            ← Back
          </button>
          <h2>{consumer.name}</h2>
          <p>{consumer.description || 'No description'}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary btn-sm" onClick={handleRotateSecret}>🔄 Rotate Secret</button>
          {consumer.status === 'active' && (
            <button className="btn btn-secondary btn-sm" onClick={handleSuspend}>⏸ Suspend</button>
          )}
          {consumer.status === 'suspended' && (
            <button className="btn btn-primary btn-sm" onClick={handleActivate}>▶ Activate</button>
          )}
          <button className="btn btn-danger btn-sm" onClick={handleRevoke}>🗑 Revoke</button>
        </div>
      </div>

      {/* Info Cards */}
      <div className="stat-cards">
        <div className="stat-card">
          <div className="label">Status</div>
          <div><span className={`badge ${statusBadge[consumer.status]}`}>{consumer.status}</span></div>
        </div>
        <div className="stat-card">
          <div className="label">Client ID</div>
          <div className="mono" style={{ fontSize: 12, color: 'var(--text-primary)', wordBreak: 'break-all' }}>{consumer.client_id}</div>
        </div>
        <div className="stat-card">
          <div className="label">Rate Limit</div>
          <div className="value">{consumer.rate_limit_requests}<span style={{ fontSize: 14, color: 'var(--text-muted)' }}> / {consumer.rate_limit_window_seconds}s</span></div>
        </div>
        <div className="stat-card">
          <div className="label">Scopes</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
            {(consumer.scopes || []).map(s => (
              <span key={s} className="badge badge-active" style={{ fontSize: 10 }}>{s}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="stat-cards">
          <div className="stat-card">
            <div className="label">API Calls (24h)</div>
            <div className="value">{stats.api_calls?.last_24h?.toLocaleString() || 0}</div>
          </div>
          <div className="stat-card">
            <div className="label">Avg Response Time</div>
            <div className="value">{stats.response_time_ms?.avg || 0}<span style={{ fontSize: 14, color: 'var(--text-muted)' }}>ms</span></div>
          </div>
          <div className="stat-card">
            <div className="label">Webhook Success (7d)</div>
            <div className="value">{stats.webhooks?.success_rate || 100}%</div>
          </div>
          <div className="stat-card">
            <div className="label">DLQ Count</div>
            <div className="value" style={{ color: stats.dlq_count > 0 ? 'var(--danger)' : 'var(--success)' }}>
              {stats.dlq_count || 0}
            </div>
          </div>
        </div>
      )}

      {/* Charts */}
      <div className="charts-grid">
        <div className="chart-card">
          <h3>API Calls (24h)</h3>
          {apiCallsChart.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={apiCallsChart}>
                <XAxis dataKey="timestamp" tickFormatter={t => new Date(t).getHours() + 'h'} tick={{ fill: '#8892b0', fontSize: 11 }} />
                <YAxis tick={{ fill: '#8892b0', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#1a1f35', border: '1px solid #2d3555', borderRadius: 8 }} />
                <Line type="monotone" dataKey="call_count" stroke="#6366f1" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : <div className="empty-state"><p>No data yet</p></div>}
        </div>
        <div className="chart-card">
          <h3>Webhook Deliveries (24h)</h3>
          {webhooksChart.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={webhooksChart}>
                <XAxis dataKey="timestamp" tickFormatter={t => new Date(t).getHours() + 'h'} tick={{ fill: '#8892b0', fontSize: 11 }} />
                <YAxis tick={{ fill: '#8892b0', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#1a1f35', border: '1px solid #2d3555', borderRadius: 8 }} />
                <Legend />
                <Line type="monotone" dataKey="delivered" stroke="#10b981" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="failed" stroke="#ef4444" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : <div className="empty-state"><p>No data yet</p></div>}
        </div>
      </div>

      {/* Merchants */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>Assigned Merchants</h3>
          <button className="btn btn-sm btn-primary" onClick={() => setShowMerchantModal(true)}>+ Assign</button>
        </div>
        {(consumer.merchants || []).length > 0 ? (
          <table className="data-table">
            <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {consumer.merchants.map(m => (
                <tr key={m.merchant_id}>
                  <td>{m.merchant_id}</td>
                  <td style={{ color: 'var(--text-primary)' }}>{m.merchant_name}</td>
                  <td>{m.merchant_email}</td>
                  <td><span className={`badge badge-${m.merchant_status === 'active' ? 'active' : 'suspended'}`}>{m.merchant_status}</span></td>
                  <td><button className="btn btn-sm btn-danger" onClick={() => handleRemoveMerchant(m.merchant_id)}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty-state"><p>No merchants assigned</p></div>}
      </div>

      {/* Assign Merchant Modal */}
      {showMerchantModal && (
        <div className="modal-overlay" onClick={() => setShowMerchantModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <form onSubmit={handleAssignMerchants}>
              <h3>Assign Merchants</h3>
              <div className="form-group">
                <label>Merchant IDs (comma-separated)</label>
                <input value={merchantIds} onChange={e => setMerchantIds(e.target.value)} placeholder="1, 2, 3" required />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowMerchantModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Assign</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
