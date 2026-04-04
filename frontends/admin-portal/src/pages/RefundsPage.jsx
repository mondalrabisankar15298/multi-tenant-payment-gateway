import { useState, useEffect } from 'react'
import { useMerchant } from '../contexts/MerchantContext'
import { api } from '../api/client'
import DataTable from '../components/DataTable'

export default function RefundsPage() {
  const { selectedMerchant } = useMerchant()
  const [refunds, setRefunds] = useState([])
  const [totalItems, setTotalItems] = useState(0)
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState(25)
  const [viewingRefund, setViewingRefund] = useState(null)
  const [toast, setToast] = useState(null)
  const mid = selectedMerchant?.merchant_id

  const showToast = (message, type = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3500)
  }

  useEffect(() => {
    if (mid) fetchRefunds()
  }, [mid, page, limit])

  useEffect(() => {
    const handleKeyDown = (e) => { if (e.key === 'Escape') setViewingRefund(null) }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const fetchRefunds = async () => {
    try {
      const data = await api.getRefunds(mid, { page, limit })
      setRefunds(data.data)
      setTotalItems(data.total)
    } catch (err) {
      showToast(`Failed to load refunds: ${err.message}`, 'error')
    }
  }

  const handlePageChange = (newPage, newLimit) => {
    setPage(newPage)
    setLimit(newLimit)
  }

  const handleProcess = async (refundId) => {
    try {
      await api.processRefund(mid, refundId)
      await fetchRefunds()
      showToast('Refund processed!')
    } catch (err) {
      showToast(`Failed to process refund: ${err.message}`, 'error')
    }
  }

  if (!mid) return <div className="empty-state"><h3>Select a merchant to view refunds</h3></div>

  const columns = [
    { 
      key: 'refund_id', 
      label: 'Refund ID', 
      render: (v) => <span style={{ color: 'var(--accent-primary)' }}>{v?.substring(0, 8)}...</span> 
    },
    { key: 'payment_id', label: 'Payment ID', render: (v) => v?.substring(0, 8) + '...' },
    { key: 'amount', label: 'Amount', render: (v) => `₹${Number(v).toLocaleString()}` },
    { key: 'reason', label: 'Reason' },
    { key: 'status', label: 'Status', render: (v) => <span className={`badge badge-${v}`}>{v}</span> },
    { key: 'created_at', label: 'Created', render: (v) => new Date(v).toLocaleString() },
  ]

  return (
    <div>
      <h1 className="page-title">Refunds</h1>
      <div className="card">
        <DataTable
          columns={columns}
          data={refunds}
          onRowClick={setViewingRefund}
          onPageChange={handlePageChange}
          totalItems={totalItems}
          currentPage={page}
          itemsPerPage={limit}
          actions={(row) =>
            row.status === 'initiated' ? (
              <button 
                className="btn btn-success btn-sm" 
                onClick={(e) => { e.stopPropagation(); handleProcess(row.refund_id); }}
              >
                Process
              </button>
            ) : null
          }
        />
      </div>

      {viewingRefund && (
        <div className="modal-overlay" onClick={() => setViewingRefund(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 800 }}>
            <h2 className="modal-title">Refund Details</h2>
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
              {JSON.stringify(viewingRefund, null, 2)}
            </pre>
            <div className="modal-actions">
              <button className="btn btn-primary" onClick={() => setViewingRefund(null)}>Close</button>
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
