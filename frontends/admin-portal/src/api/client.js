const BASE_URL = '/api'
let globalApiKey = null;

export const setApiKey = (key) => { globalApiKey = key; }

async function request(path, options = {}) {
  const { signal, ...rest } = options;
  const headers = { 'Content-Type': 'application/json', ...rest.headers };
  if (globalApiKey) {
    headers['X-API-Key'] = globalApiKey;
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    headers,
    signal,
    ...rest,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // Merchants
  getMerchants: (opts) => request('/merchants', opts),
  createMerchant: (data, opts) => request('/merchants', { method: 'POST', body: JSON.stringify(data), ...opts }),
  getMerchant: (id, opts) => request(`/merchants/${id}`, opts),
  updateMerchant: (id, data, opts) => request(`/merchants/${id}`, { method: 'PUT', body: JSON.stringify(data), ...opts }),

  // Customers
  getCustomers: (mid, opts) => request(`/${mid}/customers`, opts),
  createCustomer: (mid, data, opts) => request(`/${mid}/customers`, { method: 'POST', body: JSON.stringify(data), ...opts }),
  updateCustomer: (mid, id, data, opts) => request(`/${mid}/customers/${id}`, { method: 'PUT', body: JSON.stringify(data), ...opts }),
  deleteCustomer: (mid, id, opts) => request(`/${mid}/customers/${id}`, { method: 'DELETE', ...opts }),

  // Payments
  getPayments: (mid, opts) => request(`/${mid}/payments`, opts),
  createPayment: (mid, data, opts) => request(`/${mid}/payments`, { method: 'POST', body: JSON.stringify(data), ...opts }),
  updatePayment: (mid, id, data, opts) => request(`/${mid}/payments/${id}`, { method: 'PUT', body: JSON.stringify(data), ...opts }),
  authorizePayment: (mid, id, opts) => request(`/${mid}/payments/${id}/authorize`, { method: 'POST', ...opts }),
  capturePayment: (mid, id, opts) => request(`/${mid}/payments/${id}/capture`, { method: 'POST', ...opts }),
  failPayment: (mid, id, opts) => request(`/${mid}/payments/${id}/fail`, { method: 'POST', ...opts }),

  // Refunds
  createRefund: (mid, payId, data, opts) => request(`/${mid}/payments/${payId}/refund`, { method: 'POST', body: JSON.stringify(data), ...opts }),
  processRefund: (mid, refId, opts) => request(`/${mid}/refunds/${refId}/process`, { method: 'POST', ...opts }),
  getRefunds: (mid, opts) => request(`/${mid}/refunds`, opts),

  // Events
  getEvents: (params = {}, opts) => {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== '' && v != null)
      .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
      .join('&')
    return request(`/events${qs ? `?${qs}` : ''}`, opts)
  },
}
