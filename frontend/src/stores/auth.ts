import { defineStore } from 'pinia'  // pinia store factory
import api from '../api'  // our axios instance with JWT interceptor

interface User {
    id: number
    username: string
    email: string
    role: 'student' | 'trainer' | 'admin'
    cohort: string
}

interface AuthState {
    user: User | null
    accessToken: string | null
}

export const useAuthStore = defineStore('auth', {
    state: (): AuthState => ({
        user: JSON.parse(localStorage.getItem('user') || 'null'),  // persist user across page refresh
        accessToken: localStorage.getItem('access_token') || null,
    }),

    getters: {
        isLoggedIn: (state): boolean => !!state.accessToken,  // true if token exists
        isTrainer: (state): boolean => state.user?.role === 'trainer',  // true if trainer
        isStudent: (state): boolean => state.user?.role === 'student',  // true if student
    },

    actions: {
        async login(username: string, password: string): Promise<void> {
            const res = await api.post('/auth/login/', { username, password })
            this.accessToken = res.data.access
            this.user = res.data.user

            // persist to localStorage so user stays logged in after refresh
            localStorage.setItem('access_token', res.data.access)
            localStorage.setItem('refresh_token', res.data.refresh)
            localStorage.setItem('user', JSON.stringify(res.data.user))
        },

        logout(): void {
            this.accessToken = null
            this.user = null
            localStorage.clear()  // wipe all tokens and user data
        },
    },
})
