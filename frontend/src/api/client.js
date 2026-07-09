import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
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
      window.location.href = import.meta.env.BASE_URL + 'auth'  // BASE_URL = '/app/'
    }
    // FastAPI 422s return `detail` as a list of Pydantic error objects, not a string.
    // Components do `err.response?.data?.detail || fallback` and render it directly,
    // which crashes React ("Objects are not valid as a React child") — normalize here once.
    const detail = err.response?.data?.detail
    if (Array.isArray(detail)) {
      err.response.data.detail = detail.map(d => d.msg || JSON.stringify(d)).join(' ')
    }
    return Promise.reject(err)
  }
)

export default api
