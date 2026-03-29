const BASE_URL = '/api'
let _apiKey = null

async function request(path, options = {}) {
  const { signal, ...rest } = options;
  const headers = { 'Content-Type': 'application/json', ...rest.headers }
  
  if (_apiKey) {
    headers['X-API-Key'] = _apiKey
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    headers,
    signal,
    ...rest,
  })
  if (!res.ok) throw new Error('Request failed')
  return res.json()
}

export const api = {
  setApiKey: (key) => { _apiKey = key },
  getMerchants: (opts) => request('/merchants', opts),
  getPayments: (mid, params = '', opts) => request(`/${mid}/payments${params}`, opts),
  getPayment: (mid, id, opts) => request(`/${mid}/payments/${id}`, opts),
  getRefunds: (mid, opts) => request(`/${mid}/refunds`, opts),
  getCustomers: (mid, opts) => request(`/${mid}/customers`, opts),
  getCustomer: (mid, id, opts) => request(`/${mid}/customers/${id}`, opts),
  updateCustomer: (mid, id, data, opts) => request(`/${mid}/customers/${id}`, { method: 'PUT', body: JSON.stringify(data), ...opts }),
  updatePayment: (mid, id, data, opts) => request(`/${mid}/payments/${id}`, { method: 'PUT', body: JSON.stringify(data), ...opts }),
  getSummary: (mid, opts) => request(`/${mid}/analytics/summary`, opts),
  getDaily: (mid, days = 30, opts) => request(`/${mid}/analytics/daily?days=${days}`, opts),
  getMethods: (mid, opts) => request(`/${mid}/analytics/methods`, opts),
}
