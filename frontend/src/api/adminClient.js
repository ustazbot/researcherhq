import api from './client'

export const adminApi = {
  listUsers: (params) => api.get('/admin/users', { params }),
  updateUser: (id, data) => api.patch(`/admin/users/${id}`, data),
  deleteUser: (id) => api.delete(`/admin/users/${id}`),
  grantPro: (id) => api.post(`/admin/users/${id}/grant-pro`),

  listSupportReports: (params) => api.get('/admin/support-reports', { params }),
  updateSupportReport: (id, data) => api.patch(`/admin/support-reports/${id}`, data),

  listBillingEvents: (params) => api.get('/admin/billing-events', { params }),
  manualAdjustment: (data) => api.post('/admin/billing-events/manual-adjustment', data),

  listProjects: (params) => api.get('/admin/projects', { params }),
  deleteProject: (id) => api.delete(`/admin/projects/${id}`),

  getActionLog: (params) => api.get('/admin/action-log', { params }),
}
