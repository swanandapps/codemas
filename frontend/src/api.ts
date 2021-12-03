import axios, { type AxiosRequestConfig } from 'axios'  // axios HTTP client with TypeScript types

const api = axios.create({
    baseURL: 'http://localhost:8000/api',  // Django backend
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
                    const res = await axios.post('http://localhost:8000/api/auth/refresh/', { refresh })
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
