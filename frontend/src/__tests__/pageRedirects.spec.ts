import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../api', () => ({ default: { get: vi.fn(() => new Promise(() => {})), post: vi.fn(), patch: vi.fn() } }))

import router from '../router'
import { useAuthStore } from '../stores/auth'

// Removed duplicate pages keep their old URLs working.
function signIn(role: 'trainer' | 'student') {
    const auth = useAuthStore()
    auth.$patch({ accessToken: 'token', user: { id: 1, username: 'u', email: '', role, cohort: '' } })
}

async function land(path: string) {
    await router.push(path)
    return router.currentRoute.value.fullPath
}

beforeEach(async () => {
    setActivePinia(createPinia())
})

describe('old trainer URLs', () => {
    it.each([
        ['/dashboard/support/student/7', '/dashboard/students/7'],
        ['/dashboard/support/exam/9', '/dashboard/history/9'],
        ['/exams/9', '/dashboard/history/9'],
        ['/dashboard/plagiarism/queue', '/dashboard/plagiarism/cohorts'],
    ])('%s goes to %s', async (from, to) => {
        signIn('trainer')
        expect(await land(from)).toBe(to)
    })
})

describe('students', () => {
    it('keep /exams/:id as their exam start page', async () => {
        signIn('student')
        expect(await land('/exams/9')).toBe('/exams/9')
    })
})
