import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const get = vi.fn()
vi.mock('../api', () => ({ default: { get: (...a: unknown[]) => get(...a), patch: vi.fn() } }))

import DashboardView from '../views/DashboardView.vue'
import DisputeDetailView from '../views/DisputeDetailView.vue'

function makeRouter(path: string, component: object) {
    return createRouter({ history: createMemoryHistory(), routes: [
        { path, component },
        { path: '/dashboard/students', name: 'students', component: { template: '<div />' } },
        { path: '/:rest(.*)', component: { template: '<div />' } },
    ] })
}

beforeEach(() => get.mockReset())

describe('Overview', () => {
    const health = {
        summary: { students: 3, cohorts: 1, unassigned_students: 0, latest_exam: null },
        cohorts: [{ cohort: 'A', state: 'on_track', students: 3, latest: { exam_id: 9, accepted_rate: 80, took: 3, enrolled: 3,
            flagged_students_rate: 0 }, delta: null, series: [{ accepted_rate: 80 }], bands: { thriving: 3, steady: 0, struggling: 0,
            no_submissions: 0 }, flags_to_review: 2, reasons: [] }],
        exams: [{ exam_id: 9, title: 'Week 3', health: 'on_track', start_time: null, took: 3, enrolled: 3, took_rate: 100,
            accepted_rate: 80, hardest_question: null, hardest_accepted_rate: null, flagged_students_rate: 0 }],
        students_needing_help: [],
        rules: { at_risk: {}, watch: {} },
    }

    it('has no exams table: the Exams page is the one place for exams', async () => {
        get.mockResolvedValue({ data: health })
        const router = makeRouter('/dashboard', DashboardView)
        router.push('/dashboard')
        await router.isReady()
        const w = mount(DashboardView, { global: { plugins: [router] } })
        await flushPromises()
        expect(w.find('#exams-heading').exists()).toBe(false)
        expect(w.text()).not.toContain('Week 3')
    })

    it('sends "Flags to review" to Investigation', async () => {
        get.mockResolvedValue({ data: health })
        const router = makeRouter('/dashboard', DashboardView)
        router.push('/dashboard')
        await router.isReady()
        const w = mount(DashboardView, { global: { plugins: [router] } })
        await flushPromises()
        await w.find('button.cc-foot-link').trigger('click')
        await flushPromises()
        expect(router.currentRoute.value.path).toBe('/dashboard/plagiarism/cohorts')
    })
})

describe('Dispute', () => {
    it('links the matched student by their user id, not the submission id', async () => {
        get.mockResolvedValue({ data: {
            id: 7, student: 4, student_username: 'aarav_sharma0', flag_type: 'similarity', flag_id: 30, student_note: 'mine',
            status: 'open', resolution_note: '', created_at: '2026-10-07T13:38:00Z',
            flag_detail: { similarity_score: 0.95, detection_method: 'ast', review_status: 'pending', review_note: '', reviewed_by: null },
            submission: { id: 101, exam: 'Week 3', exam_id: 9, question: 'Two sum', language: 'python', attempt: 1,
                submitted_at: '2026-10-07T13:38:00Z', code: 'x' },
            matched_submission: { id: 102, student: 'tara_shah96', student_id: 5, code: 'y' },
        } })
        const router = makeRouter('/dashboard/support/disputes/:id', DisputeDetailView)
        router.push('/dashboard/support/disputes/7')
        await router.isReady()
        const w = mount(DisputeDetailView, { global: { plugins: [router] } })
        await flushPromises()
        const links = w.findAll('a').map(a => [a.text(), a.attributes('href')])
        expect(links).toContainEqual(['tara_shah96', '/dashboard/students/5'])
        expect(links).toContainEqual(['aarav_sharma0', '/dashboard/students/4'])
    })
})
