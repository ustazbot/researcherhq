import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 60000,
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('rhq_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('rhq_token')
      localStorage.removeItem('rhq_user')
      window.location.href = '/auth'
    }
    return Promise.reject(err)
  }
)

export default api
