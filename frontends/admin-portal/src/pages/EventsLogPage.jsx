import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import DataTable from '../components/DataTable'
import { useMerchant } from '../contexts/MerchantContext'

const ENTITY_TYPES = ['merchant', 'customer', 'payment', 'refund']
// ... (rest of constants stay the same)
const EVENT_TYPES = [
  'merchant.created.v1',
  'customer.created.v1', 'customer.updated.v1', 'customer.deleted.v1',
  'payment.created.v1', 'payment.authorized.v1', 'payment.captured.v1',
  'payment.failed.v1', 'payment.settled.v1',
  'refund.initiated.v1', 'refund.processed.v1', 'refund.failed.v1',
]
const STATUSES = ['pending', 'published']

const BADGE_COLORS = {
  'merchant.created.v1': '#8b5cf6',
  'customer.created.v1': '#06b6d4', 'customer.updated.v1': '#0ea5e9', 'customer.deleted.v1': '#ef4444',
  'payment.created.v1': '#f59e0b', 'payment.authorized.v1': '#10b981',
  'payment.captured.v1': '#22c55e', 'payment.failed.v1': '#ef4444',
  'payment.settled.v1': '#6366f1', 'refund.initiated.v1': '#f97316',
  'refund.processed.v1': '#84cc16', 'refund.failed.v1': '#dc2626',
}

export default function EventsLogPage() {
  const { merchants } = useMerchant()
  const [events, setEvents] = useState([])
  const [viewingEvent, setViewingEvent] = useState(null)
  const [loading, setLoading] = useState(false)

  const [filters, setFilters] = useState({
    status: '',
    merchant_id: '',
    entity_type: '',
    event_type: '',
    from_date: '',
    to_date: '',
  })

  const fetchEvents = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getEvents(filters)
      setEvents(data)
    } catch (err) {
      console.error('Failed to fetch events:', err)
    } finally {
      setLoading(false)
    }
  }, [filters])

  useEffect(() => { fetchEvents() }, [fetchEvents])

  useEffect(() => {
    const handleKeyDown = (e) => { if (e.key === 'Escape') setViewingEvent(null) }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const setFilter = (key, value) => setFilters(prev => ({ ...prev, [key]: value }))

  const clearFilters = () => setFilters({
    status: '', merchant_id: '', entity_type: '', event_type: '', from_date: '', to_date: '',
  })

  const hasFilters = Object.values(filters).some(v => v !== '')

  const columns = [
    {
      key: 'event_id',
      label: 'Event ID',
      render: (v) => <span style={{ color: 'var(--accent-primary)', fontFamily: 'monospace', fontSize: 12 }}>{v?.substring(0, 12)}…</span>
    },
    {
      key: 'event_type',
      label: 'Event Type',
      render: (v) => (
        <span style={{
          display: 'inline-block', padding: '2px 8px', borderRadius: 4, fontSize: 11,
          fontWeight: 600, fontFamily: 'monospace',
          background: (BADGE_COLORS[v] || '#64748b') + '22',
          color: BADGE_COLORS[v] || '#64748b',
          border: `1px solid ${(BADGE_COLORS[v] || '#64748b')}44`,
        }}>
          {v}
        </span>
      )
    },
    { key: 'entity_type', label: 'Entity', render: (v) => <span style={{ textTransform: 'capitalize' }}>{v}</span> },
    {
      key: 'merchant_id',
      label: 'Merchant',
      render: (mid) => merchants.find(m => m.merchant_id === mid)?.name || `#${mid}`
    },
    {
      key: 'status',
      label: 'Status',
      render: (v) => <span className={`badge badge-${v}`}>{v}</span>
    },
    {
      key: 'created_at',
      label: 'Created At',
      render: (v) => (
        <span style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
          {new Date(v).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'medium' })}
        </span>
      )
    },
  ]

  return (
    <div>
      {/* Header */}
      <div className="action-bar" style={{ marginBottom: 0 }}>
        <div>
          <h1 className="page-title" style={{ margin: 0 }}>Events Log</h1>
          <p style={{ margin: '2px 0 0', color: 'var(--text-muted)', fontSize: 13 }}>
            {loading ? 'Loading…' : `${events.length} event${events.length !== 1 ? 's' : ''} found`}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {hasFilters && (
            <button className="btn btn-outline btn-sm" onClick={clearFilters}>✕ Clear Filters</button>
          )}
          <button className="btn btn-outline" onClick={fetchEvents}>↻ Refresh</button>
        </div>
      </div>

      {/* Filter Panel */}
      <div className="card" style={{ marginBottom: 16, padding: '16px 20px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
          {/* Merchant */}
          <div className="form-group" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
              Merchant
            </label>
            <select className="form-input" style={{ padding: '6px 10px', fontSize: 13 }}
              value={filters.merchant_id} onChange={e => setFilter('merchant_id', e.target.value)}>
              <option value="">All Merchants</option>
              {merchants.map(m => <option key={m.merchant_id} value={m.merchant_id}>{m.name}</option>)}
            </select>
          </div>

          {/* Entity Type */}
          <div className="form-group" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
              Entity Type
            </label>
            <select className="form-input" style={{ padding: '6px 10px', fontSize: 13 }}
              value={filters.entity_type} onChange={e => setFilter('entity_type', e.target.value)}>
              <option value="">All Entities</option>
              {ENTITY_TYPES.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
            </select>
          </div>

          {/* Event Type */}
          <div className="form-group" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
              Event Type
            </label>
            <select className="form-input" style={{ padding: '6px 10px', fontSize: 13 }}
              value={filters.event_type} onChange={e => setFilter('event_type', e.target.value)}>
              <option value="">All Events</option>
              {EVENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          {/* Status */}
          <div className="form-group" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
              Status
            </label>
            <select className="form-input" style={{ padding: '6px 10px', fontSize: 13 }}
              value={filters.status} onChange={e => setFilter('status', e.target.value)}>
              <option value="">All Statuses</option>
              {STATUSES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
            </select>
          </div>

          {/* From Date */}
          <div className="form-group" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
              From Date
            </label>
            <input className="form-input" type="date" style={{ padding: '6px 10px', fontSize: 13 }}
              value={filters.from_date} onChange={e => setFilter('from_date', e.target.value)} />
          </div>

          {/* To Date */}
          <div className="form-group" style={{ margin: 0 }}>
            <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
              To Date
            </label>
            <input className="form-input" type="date" style={{ padding: '6px 10px', fontSize: 13 }}
              value={filters.to_date} onChange={e => setFilter('to_date', e.target.value)} />
          </div>
        </div>

        {/* Active filter chips */}
        {hasFilters && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
            {Object.entries(filters).map(([k, v]) => v ? (
              <span key={k} style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 10px', borderRadius: 999, fontSize: 12, fontWeight: 500,
                background: 'var(--accent-primary)22', color: 'var(--accent-primary)',
                border: '1px solid var(--accent-primary)44'
              }}>
                {k.replace('_', ' ')}: {v}
                <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', padding: 0, lineHeight: 1 }}
                  onClick={() => setFilter(k, '')}>×</button>
              </span>
            ) : null)}
          </div>
        )}
      </div>

      {/* Table */}
      <div className="card">
        <DataTable
          columns={columns}
          data={events}
          onRowClick={setViewingEvent}
        />
      </div>

      {/* Detail Modal */}
      {viewingEvent && (
        <div className="modal-overlay" onClick={() => setViewingEvent(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 860 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
              <div>
                <h2 className="modal-title" style={{ margin: 0 }}>Event Details</h2>
                <span style={{
                  display: 'inline-block', marginTop: 6, padding: '2px 10px', borderRadius: 4,
                  fontSize: 11, fontWeight: 600, fontFamily: 'monospace',
                  background: (BADGE_COLORS[viewingEvent.event_type] || '#64748b') + '22',
                  color: BADGE_COLORS[viewingEvent.event_type] || '#64748b',
                  border: `1px solid ${(BADGE_COLORS[viewingEvent.event_type] || '#64748b')}44`,
                }}>
                  {viewingEvent.event_type}
                </span>
              </div>
              <span className={`badge badge-${viewingEvent.status}`} style={{ marginTop: 4 }}>
                {viewingEvent.status}
              </span>
            </div>

            {/* Metadata row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 16 }}>
              {[
                ['Merchant', merchants.find(m => m.merchant_id === viewingEvent.merchant_id)?.name || `#${viewingEvent.merchant_id}`],
                ['Entity', `${viewingEvent.entity_type} / ${viewingEvent.entity_id?.substring(0, 12)}…`],
                ['Created', new Date(viewingEvent.created_at).toLocaleString()],
              ].map(([label, val]) => (
                <div key={label} style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '10px 14px' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{val}</div>
                </div>
              ))}
            </div>

            <pre style={{
              background: '#0f172a', color: '#e2e8f0',
              padding: 16, borderRadius: 8, overflowX: 'auto',
              fontSize: 12, lineHeight: '1.6', margin: 0
            }}>
              {JSON.stringify((() => {
                let display = { ...viewingEvent }
                if (typeof display.payload === 'string') {
                  try { display.payload = JSON.parse(display.payload) } catch {}
                }
                return display
              })(), null, 2)}
            </pre>
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={() => setViewingEvent(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
