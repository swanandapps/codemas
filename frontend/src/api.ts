import axios, { type AxiosRequestConfig } from 'axios'  // axios HTTP client with TypeScript types
import { getAuth, updateAccess, clearLogin } from './session'  // per-tab login

// Django backend — VITE_API_URL is baked in at build time (set on the Railway frontend service)
export const API_BASE_URL: string = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

const api = axios.create({
    baseURL: API_BASE_URL,
})

// attach JWT token to every request automatically
api.interceptors.request.use((config) => {
    const token = getAuth()?.access
    if (token) {
        config.headers.Authorization = `Bearer ${token}`
    }
    return config
})

// if token expired, try refresh automatically
api.interceptors.response.use(
    (response) => response,  // success — pass through
    async (error) => {
        if (error.response?.status === 401) {  // token expired
            const refresh = getAuth()?.refresh
            if (refresh) {
                try {
                    const res = await axios.post(`${API_BASE_URL}/auth/refresh/`, { refresh })
                    updateAccess(res.data.access)  // save new token for this tab
                    error.config.headers.Authorization = `Bearer ${res.data.access}`
                    return axios(error.config as AxiosRequestConfig)  // retry original request with new token
                } catch {
                    clearLogin()  // refresh failed — log this tab out
                    window.location.href = '/login'
                }
            }
        }
        return Promise.reject(error)
    }
)

export default api
