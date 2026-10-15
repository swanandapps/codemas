import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const get = vi.fn()
vi.mock('../api', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))

import StudentDetailView from '../views/StudentDetailView.vue'

// The one student page: it carries what the old student case page showed (review notes,
// who reviewed, the matched student, disputes) on an Integrity tab and a Disputes tab.
const detail = {
    student: { id: 4, username: 'aarav_sharma0', email: 'a@x.in', cohort: 'A', accepted_rate: 50, exams_passed: 1,
        exams_taken: 2, total_submissions: 3, cohort_rank: 2, cohort_size: 9, open_disputes: 1 },
    performance_trend: [],
    questions: [{ question_id: 1, question_title: 'Two sum', exam: 'Week 3', max_attempts: 3, attempts_used: 1, attempts: [] }],
    behavioural_flags: [{ id: 20, submission_id: 99, question: 'FizzBuzz', exam: 'Week 1', exam_id: 7, risk_score: 0.8, risk: 80,
        confidence: 'high', paste_score: 1, time_score: 1, signals: ['Pasted 100% of final code'],
        review_status: 'confirmed', review_note: 'Pasted from outside', reviewed_by: 'trainer1' }],
    plagiarism_flags: [{ id: 30, question: 'Two sum', exam: 'Week 3', exam_id: 9, submission_id: 101, matched_student: 'tara_shah96',
        matched_student_id: 5, similarity_score: 0.95, review_status: 'pending', review_note: '', reviewed_by: null }],
    // one group per exam with a flag, newest first (dashboard StudentDetailView)
    integrity_cases: [
        { exam_id: 9, exam_title: 'Week 3', exam_date: '2026-10-07T13:00:00Z', questions: ['Two sum'], status: 'pending',
            points_withheld: 0, case_key: '4', behaviour_flags: 0, top_signals: [],
            code_matches: [{ student_id: 5, username: 'tara_shah96', score: 0.95 }], review: null },
        { exam_id: 7, exam_title: 'Week 1', exam_date: '2026-09-23T13:00:00Z', questions: ['FizzBuzz'], status: 'confirmed',
            points_withheld: 20, case_key: '4', behaviour_flags: 1, top_signals: ['Pasted 100% of final code'],
            code_matches: [], review: { note: 'Pasted from outside', reviewed_by: 'trainer1', reviewed_at: '2026-09-24T09:30:00Z' } },
    ],
    disputes: [{ id: 7, flag_type: 'behavioural', flag_id: 20, student_note: 'I typed it myself', status: 'open',
        resolution_note: '', created_at: '2026-10-07T13:38:00Z' }],
}

async function render(to: string | { path: string; query?: Record<string, string>; state?: Record<string, string> } = '/dashboard/students/4') {
    const router = createRouter({ history: createMemoryHistory(), routes: [
        { path: '/dashboard/students/:id', component: StudentDetailView },
        { path: '/:rest(.*)', component: { template: '<div />' } },
    ] })
    router.push(to)
    await router.isReady()
    const wrapper = mount(StudentDetailView, { global: { plugins: [router], stubs: { apexchart: true } } })
    await flushPromises()
    return wrapper
}

function tab(w: Awaited<ReturnType<typeof render>>, label: string) {
    return w.findAll('button.tab-btn').find(b => b.text().startsWith(label))!
}

beforeEach(() => {
    get.mockReset()
    get.mockResolvedValue({ data: detail })
})

describe('student page', () => {
    it('has Overview, Integrity and Disputes tabs, and no Plagiarism tab', async () => {
        const w = await render()
        expect(w.findAll('button.tab-btn').map(b => b.text().split(/\s/)[0])).toEqual(['Overview', 'Integrity', 'Disputes'])
    })

    it('names each question\'s exam', async () => {
        const w = await render()
        expect(w.find('.question-header').text()).toContain('Week 3')
    })

    it('keeps each flag, its review note and the matched student under the exam\'s flag details', async () => {
        const w = await render()
        await tab(w, 'Integrity').trigger('click')
        const [week3, week1] = w.findAll('.exam-case')
        expect(week1!.find('details.flag-details summary').text()).toBe('Flag details · 1 behaviour flag')
        expect(week1!.find('details.flag-details').text()).toContain('Reviewed by trainer1')
        expect(week3!.find('details.flag-details summary').text()).toBe('Flag details · 1 similarity flag')
        const matched = week3!.findAll('a').find(a => a.text() === 'tara_shah96')!
        expect(matched.attributes('href')).toBe('/dashboard/students/5')
        expect(week3!.findAll('a').some(a => a.attributes('href') === '/dashboard/submissions/101')).toBe(true)
    })

    it('lists the student\'s disputes', async () => {
        const w = await render()
        await tab(w, 'Disputes').trigger('click')
        expect(w.text()).toContain('I typed it myself')
        expect(w.findAll('a').some(a => a.attributes('href') === '/dashboard/support/disputes/7')).toBe(true)
    })
})

describe('integrity tab: one group per exam', () => {
    const href = (a: { attributes: (k: string) => string | undefined }) => decodeURIComponent(a.attributes('href') ?? '')

    it('says how many cases are waiting on the tab', async () => {
        const w = await render()
        expect(tab(w, 'Integrity').text()).toBe('Integrity 1 case pending')
        get.mockResolvedValue({ data: { ...detail, integrity_cases: detail.integrity_cases.slice(1) } })
        const done = await render()
        expect(tab(done, 'Integrity').text()).toBe('Integrity')
    })

    it('heads each exam with its status, withheld points and a way into the case', async () => {
        const w = await render()
        await tab(w, 'Integrity').trigger('click')
        const [week3, week1] = w.findAll('.exam-case')
        expect(week3!.find('h2').text()).toBe('Week 3')
        expect(week3!.find('.case-status').text()).toBe('Under review')
        expect(week3!.find('.case-meta').text()).toBe('7 Oct 2026 · Two sum')
        const open = week3!.find('a.open-case')
        expect(open.text()).toBe('Open case →')
        expect(href(open)).toBe('/dashboard/plagiarism/cohorts/9?case=4&from=student:4')
        expect(week1!.find('.case-status').text()).toBe('Plagiarism confirmed')
        expect(week1!.find('.withheld-chip').text()).toBe('Points withheld · −20')
        expect(week1!.find('a.open-case').exists()).toBe(false)
        const view = week1!.find('a.view-case')
        expect(view.text()).toBe('View case →')
        expect(href(view)).toBe('/dashboard/plagiarism/cohorts/7?case=4&from=student:4')
    })

    it('sums up behaviour and code matches, and shows the note the student was sent', async () => {
        const w = await render()
        await tab(w, 'Integrity').trigger('click')
        const [week3, week1] = w.findAll('.exam-case')
        expect(week3!.find('.case-behaviour').text()).toBe('Behaviour No behaviour flags')
        expect(week3!.findAll('.match-chip').map(c => c.text())).toEqual(['tara_shah96 · 95.0%'])
        expect(week3!.find('.case-review').exists()).toBe(false)
        expect(week1!.find('.case-behaviour').text()).toBe('Behaviour 1 flag · Pasted 100% of final code')
        expect(week1!.find('.case-review').text()).toContain('Your note to the student: “Pasted from outside”')
        expect(week1!.find('.case-review').text()).toContain('Confirmed by trainer1 · 24 Sept 2026')
    })

    it('shows an open appeal on its exam, with the response and a link to it', async () => {
        const groups = [{ ...detail.integrity_cases[1]!, appeal: { id: 7, status: 'open', student_note: 'I wrote it at home first.' } }]
        get.mockResolvedValue({ data: { ...detail, integrity_cases: groups } })
        const w = await render()
        await tab(w, 'Integrity').trigger('click')
        const group = w.find('.exam-case')
        expect(group.find('.appeal-chip').text()).toBe('Appeal pending')
        expect(group.text()).toContain('I wrote it at home first.')
        expect(group.findAll('a').some(a => a.attributes('href') === '/dashboard/support/disputes/7')).toBe(true)
    })

    it('labels every outcome', async () => {
        const groups = ['pending', 'confirmed', 'dismissed', 'mixed'].map((status, i) => ({
            ...detail.integrity_cases[1]!, exam_id: i + 1, exam_title: `E${i}`, status, points_withheld: 0 }))
        get.mockResolvedValue({ data: { ...detail, integrity_cases: groups } })
        const w = await render()
        await tab(w, 'Integrity').trigger('click')
        expect(w.findAll('.case-status').map(c => c.text())).toEqual(['Under review', 'Plagiarism confirmed', 'Dismissed', 'Partly decided'])
    })

    it('opens on the Integrity tab with what was just decided, coming back from a case', async () => {
        const w = await render({ path: '/dashboard/students/4', query: { tab: 'integrity' },
            state: { caseNotice: 'Case confirmed for 4 students. Your note is on their results.' } })
        expect(w.find('[role="status"]').text()).toBe('Case confirmed for 4 students. Your note is on their results.')
        expect(tab(w, 'Integrity').classes()).toContain('active')
        expect(w.findAll('.exam-case')).toHaveLength(2)
    })
})

// A question voided for confirmed plagiarism is not solved, so it can turn an exam's dot red.
describe('performance trend when a question was not counted', () => {
    const point = (extra: object) => ({ date: '2026-10-01', exam: 'Week 3', status: 'failed', pct_time_used: 40,
        questions_solved: 0, questions_total: 2, questions_voided: 1, points: 0, points_withheld: 20, ...extra })

    async function chart(trend: object[]) {
        get.mockResolvedValue({ data: { ...detail, performance_trend: trend } })
        const w = await render()
        return (w.vm as any).trendOptions   // the chart itself is stubbed: read what it is given
    }

    it('paints the dot red and says why in the tooltip', async () => {
        const options = await chart([point({})])
        expect(options.markers.discrete[0].fillColor).toBe('#ED0331')
        const html = options.tooltip.custom({ series: [[40]], seriesIndex: 0, dataPointIndex: 0 })
        expect(html).toContain('Not passed')
        expect(html).toContain('solved 0 of 2 questions')
        expect(html).toContain('plagiarism confirmed: 1 question not counted')
    })

    it('says nothing about plagiarism when every solve counted', async () => {
        const options = await chart([point({ status: 'passed', questions_solved: 1, questions_voided: 0, points_withheld: 0 })])
        const html = options.tooltip.custom({ series: [[40]], seriesIndex: 0, dataPointIndex: 0 })
        expect(html).not.toContain('not counted')
    })
})
