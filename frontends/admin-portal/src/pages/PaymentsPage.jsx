import { useState, useEffect } from 'react'
import { useMerchant } from '../contexts/MerchantContext'
import { api } from '../api/client'
import DataTable from '../components/DataTable'

export default function PaymentsPage() {
  const { selectedMerchant } = useMerchant()
  const [payments, setPayments] = useState([])
  const [customers, setCustomers] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ customer_id: '', amount: '', method: 'card', description: '' })
  const [refundModal, setRefundModal] = useState({ show: false, paymentId: null, amount: '', reason: '' })

  const mid = selectedMerchant?.merchant_id

  useEffect(() => {
    if (mid) { fetchPayments(); fetchCustomers() }
  }, [mid])

  const fetchPayments = async () => setPayments(await api.getPayments(mid))
  const fetchCustomers = async () => setCustomers(await api.getCustomers(mid))

  const handleCreate = async (e) => {
    e.preventDefault()
    await api.createPayment(mid, { ...form, amount: Number(form.amount) })
    await fetchPayments()
    setShowForm(false)
    setForm({ customer_id: '', amount: '', method: 'card', description: '' })
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
    } catch (err) { alert(err.message) }
  }

  const handleRefundSubmit = async (e) => {
    e.preventDefault()
    try {
      const amount = Number(refundModal.amount)
      if (isNaN(amount) || amount <= 0) return alert("Invalid refund amount")
      await api.createRefund(mid, refundModal.paymentId, { amount, reason: refundModal.reason })
      await fetchPayments()
      setRefundModal({ show: false, paymentId: null, amount: '', reason: '' })
    } catch (err) { alert(err.message) }
  }

  if (!mid) return <div className="empty-state"><h3>Select a merchant to manage payments</h3></div>

  const columns = [
    { key: 'payment_id', label: 'ID', render: (v) => v?.substring(0, 8) + '...' },
    { key: 'customer_id', label: 'Customer' },
    { key: 'amount', label: 'Amount', render: (v) => `₹${Number(v).toLocaleString()}` },
    { key: 'currency', label: 'Currency' },
    { key: 'method', label: 'Method', render: (v) => <span className="badge badge-created">{v}</span> },
    { key: 'status', label: 'Status', render: (v) => <span className={`badge badge-${v}`}>{v}</span> },
    { key: 'created_at', label: 'Created', render: (v) => new Date(v).toLocaleString() },
  ]

  const getActions = (row) => {
    const btns = []
    if (row.status === 'created') {
      btns.push(<button key="auth" className="btn btn-success btn-sm" onClick={() => handleAction('authorize', row.payment_id)}>Authorize</button>)
      btns.push(<button key="fail" className="btn btn-danger btn-sm" onClick={() => handleAction('fail', row.payment_id)}>Fail</button>)
    }
    if (row.status === 'authorized') {
      btns.push(<button key="cap" className="btn btn-success btn-sm" onClick={() => handleAction('capture', row.payment_id)}>Capture</button>)
    }
    if (row.status === 'captured') {
      btns.push(<button key="ref" className="btn btn-outline btn-sm" onClick={() => handleAction('refund', row.payment_id)}>Refund</button>)
    }
    return btns
  }

  return (
    <div>
      <div className="action-bar">
        <h1 className="page-title" style={{ margin: 0 }}>Payments</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ New Payment</button>
      </div>

      <div className="card">
        <DataTable columns={columns} data={payments} actions={getActions} />
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
                <label>Refund Amount (₹)</label>
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
    </div>
  )
}
