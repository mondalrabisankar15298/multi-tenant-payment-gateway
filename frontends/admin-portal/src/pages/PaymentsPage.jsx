import { useState, useEffect } from 'react'
import { useMerchant } from '../contexts/MerchantContext'
import { api } from '../api/client'
import DataTable from '../components/DataTable'

export default function PaymentsPage() {
  const { selectedMerchant } = useMerchant()
  const [payments, setPayments] = useState([])
  const [totalItems, setTotalItems] = useState(0)
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState(25)
  const [customers, setCustomers] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ customer_id: '', amount: '', method: 'card', description: '' })
  const [refundModal, setRefundModal] = useState({ show: false, paymentId: null, amount: '', reason: '' })
  
  const [editingPayment, setEditingPayment] = useState(null)
  const [viewingPayment, setViewingPayment] = useState(null)
  const [description, setDescription] = useState('')
  const [metadataString, setMetadataString] = useState('{}')
  const [toast, setToast] = useState(null)

  const mid = selectedMerchant?.merchant_id

  const showToast = (message, type = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3500)
  }

  useEffect(() => {
    if (mid) { fetchPayments(); fetchCustomers() }
  }, [mid, page, limit])

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setShowForm(false)
        setRefundModal(prev => ({ ...prev, show: false }))
        setEditingPayment(null)
        setViewingPayment(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const fetchPayments = async () => {
    try {
      const data = await api.getPayments(mid, { page, limit })
      setPayments(data.data)
      setTotalItems(data.total)
    } catch (err) {
      showToast(`Failed to load payments: ${err.message}`, 'error')
    }
  }
  const fetchCustomers = async () => {
    try {
      const data = await api.getCustomers(mid, { limit: 1000 })
      setCustomers(data.data || data)
    } catch (err) {
      showToast(`Failed to load customers: ${err.message}`, 'error')
    }
  }

  const handlePageChange = (newPage, newLimit) => {
    setPage(newPage)
    setLimit(newLimit)
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    try {
      await api.createPayment(mid, { ...form, amount: Number(form.amount) })
      await fetchPayments()
      setShowForm(false)
      setForm({ customer_id: '', amount: '', method: 'card', description: '' })
      showToast('Payment created successfully!')
    } catch (err) {
      showToast(`Failed to create payment: ${err.message}`, 'error')
    }
  }

  const openEdit = (pay) => {
    setEditingPayment(pay)
    setDescription(pay.description || '')
    setMetadataString(JSON.stringify(pay.metadata || {}, null, 2))
  }

  const handleUpdate = async (e) => {
    e.preventDefault()
    let parsedMeta = {}
    try { parsedMeta = JSON.parse(metadataString || '{}') } 
    catch { return alert("Invalid Metadata JSON") }

    try {
      await api.updatePayment(mid, editingPayment.payment_id, {
        description: description || null,
        metadata: parsedMeta
      })
      await fetchPayments()
      setEditingPayment(null)
      showToast('Payment updated!')
    } catch (err) {
      showToast(`Failed to update payment: ${err.message}`, 'error')
    }
  }

  const handleAction = async (action, paymentId) => {
    try {
      if (action === 'authorize') await api.authorizePayment(mid, paymentId)
      if (action === 'capture') await api.capturePayment(mid, paymentId)
      if (action === 'fail') await api.failPayment(mid, paymentId)
      if (action === 'refund') {
        setRefundModal({ show: true, paymentId, amount: '', reason: 'Requested by Admin' })
        return
      }
      await fetchPayments()
      showToast(`Payment ${action}d!`)
    } catch (err) {
      showToast(`Action failed: ${err.message}`, 'error')
    }
  }

  const handleRefundSubmit = async (e) => {
    e.preventDefault()
    try {
      const amount = Number(refundModal.amount)
      if (isNaN(amount) || amount <= 0) return showToast('Invalid refund amount', 'error')
      await api.createRefund(mid, refundModal.paymentId, { amount, reason: refundModal.reason })
      await fetchPayments()
      setRefundModal({ show: false, paymentId: null, amount: '', reason: '' })
      showToast('Refund initiated successfully!')
    } catch (err) {
      showToast(`Refund failed: ${err.message}`, 'error')
    }
  }

  if (!mid) return <div className="empty-state"><h3>Select a merchant to manage payments</h3></div>

  const columns = [
    { 
      key: 'payment_id', 
      label: 'ID', 
      render: (v) => <span style={{ color: 'var(--accent-primary)' }}>{v?.substring(0, 8)}...</span> 
    },
    { 
      key: 'customer_id', 
      label: 'Customer',
      render: (cid) => customers.find(c => c.customer_id === cid)?.name || cid
    },
    { 
      key: 'amount', 
      label: 'Amount (Refunded)', 
      render: (v, row) => Number(row.amount_refunded) > 0 
        ? <span>₹{Number(v).toLocaleString()} <small style={{color: '#ef4444', fontWeight: '500', marginLeft: '4px'}}>(−₹{Number(row.amount_refunded).toLocaleString()})</small></span>
        : `₹${Number(v).toLocaleString()}` 
    },
    { key: 'currency', label: 'Currency' },
    { key: 'method', label: 'Method', render: (v) => <span className="badge badge-created">{v}</span> },
    { key: 'status', label: 'Status', render: (v) => <span className={`badge badge-${v}`}>{v}</span> },
    { key: 'created_at', label: 'Created', render: (v) => new Date(v).toLocaleString() },
  ]

  const getActions = (row) => {
    const btns = []
    if (row.status === 'created') {
      btns.push(<button key="auth" className="btn btn-success btn-sm" onClick={(e) => { e.stopPropagation(); handleAction('authorize', row.payment_id); }}>Authorize</button>)
      btns.push(<button key="fail" className="btn btn-danger btn-sm" onClick={(e) => { e.stopPropagation(); handleAction('fail', row.payment_id); }}>Fail</button>)
    }
    if (row.status === 'authorized') {
      btns.push(<button key="cap" className="btn btn-success btn-sm" onClick={(e) => { e.stopPropagation(); handleAction('capture', row.payment_id); }}>Capture</button>)
    }
    if (row.status === 'captured') {
      btns.push(<button key="ref" className="btn btn-outline btn-sm" onClick={(e) => { e.stopPropagation(); handleAction('refund', row.payment_id); }}>Refund</button>)
    }
    btns.push(<button key="edit" className="btn btn-outline btn-sm" onClick={(e) => { e.stopPropagation(); openEdit(row); }}>Edit</button>)
    return btns
  }

  return (
    <div>
      <div className="action-bar">
        <h1 className="page-title" style={{ margin: 0 }}>Payments</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ New Payment</button>
      </div>

      <div className="card">
        <DataTable 
          columns={columns} 
          data={payments} 
          actions={getActions} 
          onRowClick={setViewingPayment}
          onPageChange={handlePageChange}
          totalItems={totalItems}
          currentPage={page}
          itemsPerPage={limit}
        />
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2 className="modal-title">Create Payment</h2>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Customer</label>
                <select className="form-input" value={form.customer_id} onChange={e => setForm({...form, customer_id: e.target.value})} required>
                  <option value="">Select customer...</option>
                  {customers.map(c => <option key={c.customer_id} value={c.customer_id}>{c.name}</option>)}
                </select>
              </div>
              <div className="grid-2">
                <div className="form-group">
                  <label>Amount (₹)</label>
                  <input className="form-input" type="number" step="0.01" value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label>Method</label>
                  <select className="form-input" value={form.method} onChange={e => setForm({...form, method: e.target.value})}>
                    <option value="card">Card</option>
                    <option value="upi">UPI</option>
                    <option value="netbanking">Net Banking</option>
                    <option value="wallet">Wallet</option>
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label>Description</label>
                <input className="form-input" value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="Order #12345" />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create Payment</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {refundModal.show && (
        <div className="modal-overlay" onClick={() => setRefundModal({...refundModal, show: false})}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2 className="modal-title">Refund Payment</h2>
            <form onSubmit={handleRefundSubmit}>
              <div className="form-group">
                <label>
                  Refund Amount (₹)
                  {refundModal.paymentId && payments.find(p => p.payment_id === refundModal.paymentId) && (
                    <span style={{color: '#64748b', fontSize: '13px', marginLeft: '8px', fontWeight: 'normal'}}>
                      Available: ₹{Number(payments.find(p => p.payment_id === refundModal.paymentId).amount - (payments.find(p => p.payment_id === refundModal.paymentId).amount_refunded || 0)).toLocaleString()}
                    </span>
                  )}
                </label>
                <input className="form-input" type="number" step="0.01" value={refundModal.amount} onChange={e => setRefundModal({...refundModal, amount: e.target.value})} required placeholder="e.g. 500" />
              </div>
              <div className="form-group">
                <label>Reason</label>
                <input className="form-input" value={refundModal.reason} onChange={e => setRefundModal({...refundModal, reason: e.target.value})} required />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-outline" onClick={() => setRefundModal({...refundModal, show: false})}>Cancel</button>
                <button type="submit" className="btn btn-danger">Process Refund</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingPayment && (
        <div className="modal-overlay" onClick={() => setEditingPayment(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2 className="modal-title">Edit Payment Data</h2>
            <form onSubmit={handleUpdate}>
              <div className="form-group">
                <label>Description</label>
                <input className="form-input" value={description} onChange={e => setDescription(e.target.value)} placeholder="Payment description..." />
              </div>
              <div className="form-group">
                <label>Metadata (JSON)</label>
                <textarea 
                  className="form-input" 
                  rows="5"
                  value={metadataString} 
                  onChange={e => setMetadataString(e.target.value)} 
                  style={{ fontFamily: 'monospace' }}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-outline" onClick={() => setEditingPayment(null)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Save Changes</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {viewingPayment && (
        <div className="modal-overlay" onClick={() => setViewingPayment(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 800 }}>
            <h2 className="modal-title">Payment Details</h2>
            <pre style={{ 
              background: '#f8fafc', 
              color: '#0f172a', 
              padding: 16, 
              borderRadius: 8, 
              overflowX: 'auto', 
              fontSize: 13,
              border: '1px solid #e2e8f0',
              lineHeight: '1.5'
            }}>
              {JSON.stringify((() => {
                let display = { ...viewingPayment }
                if (typeof display.metadata === 'string') {
                  try { display.metadata = JSON.parse(display.metadata) } catch {}
                }
                return display
              })(), null, 2)}
            </pre>
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={() => setViewingPayment(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div style={{
          position: 'fixed', bottom: '24px', right: '24px', zIndex: 9999,
          padding: '12px 20px', borderRadius: '8px', fontWeight: 500, fontSize: '14px',
          background: toast.type === 'error' ? '#ef4444' : '#22c55e',
          color: '#fff', boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
        }}>
          {toast.type === 'error' ? '❌ ' : '✅ '}{toast.message}
        </div>
      )}
    </div>
  )
}
