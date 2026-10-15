import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../stores/auth'

const post = vi.fn()
const get = vi.fn(() => Promise.resolve({ data: [] }))
vi.mock('../api', () => ({ default: {
    get: (...a: unknown[]) => (get as any)(...a), post: (...a: unknown[]) => post(...a),
    patch: vi.fn(), put: vi.fn(), delete: vi.fn(),
} }))

import CreateExamView from '../views/CreateExamView.vue'

async function mountPage() {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:p(.*)', component: CreateExamView }] })
    router.push('/dashboard/create'); await router.isReady()
    const w = mount(CreateExamView, { global: { plugins: [router] } })
    await flushPromises()
    return w
}

async function generateDraft(w: any) {
    await w.find('textarea').setValue('Binary search')
    await w.find('form.gen-card').trigger('submit')   // the Generate button submits this form
    await flushPromises()
}

beforeEach(() => {
    localStorage.clear()
    post.mockClear()
    setActivePinia(createPinia())
    useAuthStore().user = { id: 1, username: 'venugopal', email: '', role: 'trainer', cohort: '' }
    post.mockResolvedValue({ data: {
            title: 'Binary Search', description: 'd', questions: [{
                title: 'Find the index', description: 'Find it.', difficulty: 'medium', language: 'javascript',
                test_cases: [
                    { input_data: '1 3 5 7 9\n5', expected_output: '2', is_hidden: false },
                    { input_data: '1 3 5 7 9\n9', expected_output: '4', is_hidden: true },
                    { input_data: '1 3 5 7 9\n11', expected_output: '-1', is_hidden: true },
                ],
                starter_code: { javascript: '', python: '' },
            }],
        } })
})

// The trainer reviewing a draft sees every test case, hidden ones included, to catch a bad one
// (e.g. a "not found" test a broken solution passes by luck) before saving.
describe('Create exam review: all test cases', () => {
    it('lists hidden test cases with their expected output', async () => {
        const w = await mountPage()
        await generateDraft(w)

        const list = w.find('.all-cases')
        expect(list.exists()).toBe(true)
        expect(list.text()).toContain('only you see this')
        const rows = list.findAll('tbody tr').map(r => r.text())
        expect(rows).toHaveLength(3)
        expect(rows[2]).toContain('-1')
        expect(rows[2]).toContain('Hidden')
        expect(rows[0]).toContain('Shown')
    })
})

describe('Create exam: a reload keeps the draft', () => {
    it('restores the generated draft after a reload, and Start over clears it', async () => {
        const first = await mountPage()
        await generateDraft(first)
        first.unmount()                                   // the reload

        const again = await mountPage()
        expect(post).toHaveBeenCalledTimes(1)             // no second generation
        expect(again.text()).toContain('Restored your unsaved draft')
        expect(again.find('.all-cases').exists()).toBe(true)   // back on the review step with the questions

        await again.findAll('button').find(b => b.text() === 'Start over')!.trigger('click')
        await flushPromises()
        again.unmount()
        const fresh = await mountPage()
        expect(fresh.text()).not.toContain('Restored your unsaved draft')
        expect(fresh.find('.all-cases').exists()).toBe(false)
    })
})
