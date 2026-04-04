import React, { useState, useEffect } from 'react'
import { api } from '../api/client'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'

export default function Dashboard() {
  const [overview, setOverview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadOverview()
  }, [])

  async function loadOverview() {
    try {
      setLoading(true)
      const res = await api.getOverview()
      setOverview(res.data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="loading"><div className="spinner" /> Loading dashboard...</div>
  if (error) return <div className="empty-state"><h3>Error</h3><p>{error}</p></div>
  if (!overview) return null

  return (
    <div>
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>System-wide overview of the third-party consumer platform</p>
      </div>

      <div className="stat-cards">
        <div className="stat-card">
          <div className="label">Active Consumers</div>
          <div className="value">{overview.active_consumers}</div>
        </div>
        <div className="stat-card">
          <div className="label">API Calls (24h)</div>
          <div className="value">{overview.api_calls?.last_24h?.toLocaleString() || 0}</div>
        </div>
        <div className="stat-card">
          <div className="label">Webhooks Delivered (24h)</div>
          <div className="value">{overview.webhooks?.delivered_24h?.toLocaleString() || 0}</div>
        </div>
        <div className="stat-card">
          <div className="label">Webhook Success Rate</div>
          <div className="value">{overview.webhooks?.success_rate || 100}%</div>
        </div>
        <div className="stat-card">
          <div className="label">DLQ Backlog</div>
          <div className="value" style={{ color: overview.dlq_backlog > 0 ? 'var(--danger)' : 'var(--success)' }}>
            {overview.dlq_backlog}
          </div>
        </div>
      </div>

      {overview.top_consumers?.length > 0 && (
        <div className="card" style={{ marginBottom: 32 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 20 }}>
            Top Consumers by API Calls (24h)
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={overview.top_consumers}>
              <XAxis dataKey="name" tick={{ fill: '#8892b0', fontSize: 12 }} />
              <YAxis tick={{ fill: '#8892b0', fontSize: 12 }} />
              <Tooltip
                contentStyle={{ background: '#1a1f35', border: '1px solid #2d3555', borderRadius: 8 }}
                labelStyle={{ color: '#f0f2f7' }}
              />
              <Bar dataKey="call_count" fill="#6366f1" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
