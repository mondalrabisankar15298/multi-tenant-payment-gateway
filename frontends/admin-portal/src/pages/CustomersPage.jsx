import { useState, useEffect } from 'react'
import { useMerchant } from '../contexts/MerchantContext'
import { api } from '../api/client'
import DataTable from '../components/DataTable'

export default function CustomersPage() {
  const { selectedMerchant } = useMerchant()
  const [customers, setCustomers] = useState([])
  const [totalItems, setTotalItems] = useState(0)
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState(25)
  const [showForm, setShowForm] = useState(false)
  const [editingCustomer, setEditingCustomer] = useState(null)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [viewingCustomer, setViewingCustomer] = useState(null)
  const [toast, setToast] = useState(null)

  const mid = selectedMerchant?.merchant_id

  const showToast = (message, type = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3500)
  }

  useEffect(() => {
    if (mid) fetchCustomers()
  }, [mid, page, limit])

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setShowForm(false)
        setEditingCustomer(null)
        setViewingCustomer(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const fetchCustomers = async () => {
    try {
      const data = await api.getCustomers(mid, { page, limit })
      setCustomers(data.data)
      setTotalItems(data.total)
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
      await api.createCustomer(mid, { name, email, phone })
      await fetchCustomers()
      setShowForm(false)
      setName(''); setEmail(''); setPhone('')
      showToast('Customer created successfully!')
    } catch (err) {
      showToast(`Failed to create customer: ${err.message}`, 'error')
    }
  }

  const openEdit = (cust) => {
    setEditingCustomer(cust)
    setName(cust.name || '')
    setEmail(cust.email || '')
    setPhone(cust.phone || '')
  }

  const handleUpdate = async (e) => {
    e.preventDefault()
    try {
      await api.updateCustomer(mid, editingCustomer.customer_id, { name, email, phone })
      await fetchCustomers()
      setEditingCustomer(null)
      showToast('Customer updated successfully!')
    } catch (err) {
      showToast(`Failed to update customer: ${err.message}`, 'error')
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this customer?')) return
    try {
      await api.deleteCustomer(mid, id)
      await fetchCustomers()
      showToast('Customer deleted.')
    } catch (err) {
      showToast(`Failed to delete customer: ${err.message}`, 'error')
    }
  }

  if (!mid) return <div className="empty-state"><h3>Select a merchant to manage customers</h3></div>

  const columns = [
    { 
      key: 'customer_id', 
      label: 'ID',
      render: (v) => <span style={{ color: 'var(--accent-primary)' }}>{v}</span>
    },
    { key: 'name', label: 'Name' },
    { key: 'email', label: 'Email' },
    { key: 'phone', label: 'Phone' },
    { key: 'created_at', label: 'Created', render: (v) => new Date(v).toLocaleDateString() },
  ]

  return (
    <div>
      <div className="action-bar">
        <h1 className="page-title" style={{ margin: 0 }}>Customers</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ New Customer</button>
      </div>

      <div className="card">
        <DataTable
          columns={columns}
          data={customers}
          onRowClick={setViewingCustomer}
          onPageChange={handlePageChange}
          totalItems={totalItems}
          currentPage={page}
          itemsPerPage={limit}
          actions={(row) => (
            <>
              <button className="btn btn-outline btn-sm" onClick={(e) => { e.stopPropagation(); openEdit(row); }}>Edit</button>
              <button className="btn btn-danger btn-sm" onClick={(e) => { e.stopPropagation(); handleDelete(row.customer_id); }}>Delete</button>
            </>
          )}
        />
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2 className="modal-title">Create Customer</h2>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Full Name</label>
                <input className="form-input" value={name} onChange={e => setName(e.target.value)} required />
              </div>
              <div className="form-group">
                <label>Email</label>
                <input className="form-input" type="email" value={email} onChange={e => setEmail(e.target.value)} />
              </div>
              <div className="form-group">
                <label>Phone</label>
                <input className="form-input" value={phone} onChange={e => setPhone(e.target.value)} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-outline" onClick={() => setShowForm(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingCustomer && (
        <div className="modal-overlay" onClick={() => setEditingCustomer(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2 className="modal-title">Edit Customer</h2>
            <form onSubmit={handleUpdate}>
              <div className="form-group">
                <label>Full Name</label>
                <input className="form-input" value={name} onChange={e => setName(e.target.value)} required />
              </div>
              <div className="form-group">
                <label>Email</label>
                <input className="form-input" type="email" value={email} onChange={e => setEmail(e.target.value)} />
              </div>
              <div className="form-group">
                <label>Phone</label>
                <input className="form-input" value={phone} onChange={e => setPhone(e.target.value)} />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-outline" onClick={() => setEditingCustomer(null)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Save Changes</button>
              </div>
            </form>
          </div>
        </div>
      )}
      {viewingCustomer && (
        <div className="modal-overlay" onClick={() => setViewingCustomer(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 800 }}>
            <h2 className="modal-title">Customer Details</h2>
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
              {JSON.stringify(viewingCustomer, null, 2)}
            </pre>
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={() => setViewingCustomer(null)}>Close</button>
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
