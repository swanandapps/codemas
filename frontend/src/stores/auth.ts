import { defineStore } from 'pinia'  // pinia store factory
import api from '../api'  // our axios instance with JWT interceptor
import { getAuth, saveLogin, clearLogin } from '../session'  // per-tab login

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
        user: getAuth()?.user ?? null,  // this tab's account survives a refresh
        accessToken: getAuth()?.access ?? null,
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

            saveLogin({ access: res.data.access, refresh: res.data.refresh, user: res.data.user })
        },

        logout(): void {
            this.accessToken = null
            this.user = null
            clearLogin()  // this tab only: other tabs keep their accounts
        },
    },
})
