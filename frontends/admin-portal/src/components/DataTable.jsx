import { useState } from 'react'

export default function DataTable({ columns, data, actions, onRowClick, onPageChange, totalItems, currentPage: currentPageProp, itemsPerPage }) {
  const currentPage = currentPageProp || 1
  const [localItemsPerPage, setLocalItemsPerPage] = useState(itemsPerPage || 25)

  if (!data || data.length === 0) {
    return (
      <div className="empty-state">
        <h3>No data yet</h3>
        <p>Create your first record to see it here</p>
      </div>
    )
  }

  const isServerSide = typeof totalItems === 'number'

  const totalPages = isServerSide
    ? Math.ceil(totalItems / localItemsPerPage)
    : Math.ceil(data.length / localItemsPerPage)

  const displayData = isServerSide ? data : data.slice((currentPage - 1) * localItemsPerPage, currentPage * localItemsPerPage)

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= totalPages) {
      if (isServerSide) {
        onPageChange && onPageChange(newPage, localItemsPerPage)
      } else {
        setCurrentPage(newPage)
      }
    }
  }

  const handleItemsPerPageChange = (newSize) => {
    setLocalItemsPerPage(newSize)
    if (isServerSide) {
      onPageChange && onPageChange(1, newSize)
    }
  }

  const startIdx = isServerSide
    ? (currentPage - 1) * localItemsPerPage + 1
    : (currentPage - 1) * localItemsPerPage + 1
  const endIdx = isServerSide
    ? Math.min(currentPage * localItemsPerPage, totalItems)
    : Math.min(currentPage * localItemsPerPage, data.length)

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              {columns.map(col => (
                <th key={col.key}>{col.label}</th>
              ))}
              {actions && <th>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {displayData.map((row, i) => (
              <tr
                key={i}
                onClick={() => onRowClick && onRowClick(row)}
                style={{ cursor: onRowClick ? 'pointer' : 'default' }}
              >
                {columns.map(col => (
                  <td key={col.key}>
                    {col.render ? col.render(row[col.key], row) : row[col.key]?.toString() || '—'}
                  </td>
                ))}
                {actions && (
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="btn-actions">
                      {actions(row)}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 24px', borderTop: '1px solid #e2e8f0', background: '#f8fafc', borderBottomLeftRadius: '8px', borderBottomRightRadius: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: '#64748b' }}>
          <span>Rows per page:</span>
          <select
            value={localItemsPerPage}
            onChange={(e) => handleItemsPerPageChange(Number(e.target.value))}
            style={{ padding: '4px', borderRadius: '4px', border: '1px solid #cbd5e1', cursor: 'pointer', outline: 'none' }}
          >
            {[15, 25, 50, 75, 100].map(size => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
          <span style={{ marginLeft: '12px' }}>
            Showing {startIdx} to {endIdx} of {totalItems || data.length}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <button
            onClick={() => handlePageChange(currentPage - 1)}
            disabled={currentPage === 1}
            style={{ padding: '6px 12px', borderRadius: '4px', border: '1px solid #cbd5e1', background: currentPage === 1 ? '#f1f5f9' : '#ffffff', cursor: currentPage === 1 ? 'not-allowed' : 'pointer', color: currentPage === 1 ? '#94a3b8' : '#0f172a', fontSize: '13px' }}
          >
            Prev
          </button>
          <span style={{ fontSize: '13px', color: '#0f172a', fontWeight: '500', padding: '0 8px' }}>
            {currentPage} / {totalPages || 1}
          </span>
          <button
            onClick={() => handlePageChange(currentPage + 1)}
            disabled={currentPage === totalPages || totalPages === 0}
            style={{ padding: '6px 12px', borderRadius: '4px', border: '1px solid #cbd5e1', background: currentPage === totalPages || totalPages === 0 ? '#f1f5f9' : '#ffffff', cursor: currentPage === totalPages || totalPages === 0 ? 'not-allowed' : 'pointer', color: currentPage === totalPages || totalPages === 0 ? '#94a3b8' : '#0f172a', fontSize: '13px' }}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
