const API_BASE = '/api/v1';

class ApiClient {
  constructor() {
    this.adminKey = localStorage.getItem('admin_api_key') || '';
  }

  setAdminKey(key) {
    this.adminKey = key;
    localStorage.setItem('admin_api_key', key);
  }

  async request(path, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      'X-Admin-Key': this.adminKey,
      ...options.headers,
    };

    const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: response.statusText }));
      throw new Error(error.detail || error.message || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Consumer Management
  async listConsumers() { return this.request('/admin/consumers'); }
  async getConsumer(id) { return this.request(`/admin/consumers/${id}`); }
  async createConsumer(data) { return this.request('/admin/consumers', { method: 'POST', body: JSON.stringify(data) }); }
  async updateConsumer(id, data) { return this.request(`/admin/consumers/${id}`, { method: 'PUT', body: JSON.stringify(data) }); }
  async deleteConsumer(id) { return this.request(`/admin/consumers/${id}`, { method: 'DELETE' }); }
  async suspendConsumer(id) { return this.request(`/admin/consumers/${id}/suspend`, { method: 'POST' }); }
  async activateConsumer(id) { return this.request(`/admin/consumers/${id}/activate`, { method: 'POST' }); }
  async rotateSecret(id) { return this.request(`/admin/consumers/${id}/rotate-secret`, { method: 'POST' }); }
  async assignMerchants(id, merchantIds) { return this.request(`/admin/consumers/${id}/merchants`, { method: 'POST', body: JSON.stringify({ merchant_ids: merchantIds }) }); }
  async removeMerchant(consumerId, merchantId) { return this.request(`/admin/consumers/${consumerId}/merchants/${merchantId}`, { method: 'DELETE' }); }
  async listConsumerMerchants(id) { return this.request(`/admin/consumers/${id}/merchants`); }

  // Analytics
  async getOverview() { return this.request('/admin/analytics/overview'); }
  async getConsumerStats(id) { return this.request(`/admin/analytics/consumers/${id}`); }
  async getConsumerApiCalls(id, params = '') { return this.request(`/admin/analytics/consumers/${id}/api-calls${params}`); }
  async getConsumerWebhooks(id, params = '') { return this.request(`/admin/analytics/consumers/${id}/webhooks${params}`); }
}

export const api = new ApiClient();
