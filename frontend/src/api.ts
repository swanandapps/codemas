import axios, { type AxiosRequestConfig } from 'axios'  // axios HTTP client with TypeScript types

// Django backend — VITE_API_URL is baked in at build time (set on the Railway frontend service)
export const API_BASE_URL: string = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

const api = axios.create({
    baseURL: API_BASE_URL,
})

// attach JWT token to every request automatically
api.interceptors.request.use((config) => {
    const token: string | null = localStorage.getItem('access_token')
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
            const refresh: string | null = localStorage.getItem('refresh_token')
            if (refresh) {
                try {
                    const res = await axios.post(`${API_BASE_URL}/auth/refresh/`, { refresh })
                    localStorage.setItem('access_token', res.data.access)  // save new token
                    error.config.headers.Authorization = `Bearer ${res.data.access}`
                    return axios(error.config as AxiosRequestConfig)  // retry original request with new token
                } catch {
                    localStorage.clear()  // refresh failed — log out
                    window.location.href = '/login'
                }
            }
        }
        return Promise.reject(error)
    }
)

export default api
