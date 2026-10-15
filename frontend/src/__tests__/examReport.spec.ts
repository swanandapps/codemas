import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

const get = vi.fn()
const patch = vi.fn()
const post = vi.fn()
vi.mock('../api', () => ({ default: {
    get: (...a: unknown[]) => get(...a), patch: (...a: unknown[]) => patch(...a), post: (...a: unknown[]) => post(...a),
} }))

import ExamHistoryDetailView from '../views/ExamHistoryDetailView.vue'

// The exam report is the one exam page for trainers: a draft can be made live from it,
// and while live it shows each student's attempts and latest submission.
const base = {
    exam_id: 9, title: 'Week 3', description: '', duration_minutes: 60, start_time: null, end_time: null,
    took: 0, enrolled: 0, took_rate: null, accepted_rate: null, passed_students: 0,
    flagged_students: 0, flagged_students_rate: null, flags_to_review: 0, integrity_health: 'green',
    similarity_pairs: 0, confirmed_plagiarism: 0, avg_solve_s: null, avg_exec_ms: null, top_language: null,
    question_count: 1, hardest_question: null, hardest_accepted_rate: null, total_submissions: 0,
    questions: [{ question_id: 1, title: 'Two sum', difficulty: 'easy', total_attempts: 0, solved_students: 0,
        attempted_students: 0, accepted_rate: null, avg_solve_s: null, flag_count: 0 }],
    students: [],
}
const draft = { ...base, status: 'draft' }
const live = {
    ...base, status: 'live', took: 1, enrolled: 2, took_rate: 50, accepted_rate: 100, passed_students: 1, total_submissions: 2,
    students: [
        { student_id: 4, username: 'aarav_sharma0', full_name: 'Aarav Sharma', submitted: true, questions_solved: 1,
            total_questions: 1, passed: true, points: 10, rank: 1, avg_solve_s: 120, attempts: 2, last_status: 'passed',
            last_submitted_at: '2026-10-07T13:38:00Z', behavioural_flags: 0, similarity_flags: 0 },
        { student_id: 5, username: 'tara_shah96', full_name: 'Tara Shah', submitted: false, questions_solved: 0,
            total_questions: 1, passed: null, points: 0, rank: 2, avg_solve_s: null, attempts: 0, last_status: null,
            last_submitted_at: null, behavioural_flags: 0, similarity_flags: 0 },
    ],
}

function mockApi(report: object) {
    get.mockImplementation((url: string) => {
        if (url === '/dashboard/exams/9/') return Promise.resolve({ data: report })
        if (url === '/exams/9/') return Promise.resolve({ data: { id: 9, is_active: false, start_time: null, end_time: null, sections: [], status: 'draft' } })
        if (url === '/exams/sections/') return Promise.resolve({ data: [{ name: 'A', students: 3 }, { name: 'B', students: 2 }] })
        return Promise.resolve({ data: [] })
    })
}

let router: ReturnType<typeof createRouter>

async function render(state?: Record<string, string>) {
    router = createRouter({ history: createMemoryHistory(), routes: [
        { path: '/dashboard/history/:id', component: ExamHistoryDetailView },
        { path: '/:rest(.*)', component: { template: '<div />' } },
    ] })
    router.push({ path: '/dashboard/history/9', state })
    await router.isReady()
    const wrapper = mount(ExamHistoryDetailView, { global: { plugins: [router] } })
    await flushPromises()
    return wrapper
}

beforeEach(() => {
    get.mockReset()
    patch.mockReset()
    post.mockReset()
})

describe('exam report, draft', () => {
    it('shows the publish card and renders cleanly with no submissions', async () => {
        mockApi(draft)
        const w = await render()
        expect(w.text()).toContain('This exam is a draft')
        expect(w.find('button.publish-btn').text()).toBe('Activate now')
        expect(w.text()).toContain('Whole cohort · 5')
        expect(w.text()).not.toContain('NaN')
        expect(w.text()).not.toContain('Run plagiarism check')
        expect(w.text()).not.toContain('End exam')
        expect(w.text()).toContain('No students enrolled yet')
    })

    it('shows why Create exam could not publish it', async () => {
        mockApi(draft)
        const w = await render({ notice: "The exam was saved as a draft, but it couldn't go live. Activate it below." })
        expect(w.find('.publish-card').text()).toContain("couldn't go live")
    })

    it('Activate now sends the same request as before and reloads the report', async () => {
        mockApi(draft)
        patch.mockResolvedValue({ data: { is_active: true } })
        const w = await render()
        await w.findAll('button.chip').find(b => b.text().startsWith('B'))!.trigger('click')
        mockApi(live)
        await w.find('button.publish-btn').trigger('click')
        await flushPromises()
        expect(patch).toHaveBeenCalledWith('/exams/9/', { is_active: true, sections: ['B'] })
        expect(w.find('.publish-card').exists()).toBe(false)
        expect(w.text()).toContain('End exam')
    })
})

describe('exam report, live', () => {
    it('has one student table with attempts and latest submission, and no top performers panel', async () => {
        mockApi(live)
        const w = await render()
        expect(w.find('.publish-card').exists()).toBe(false)
        expect(w.text()).not.toContain('Top performers')
        expect(w.findAll('.st-row')).toHaveLength(2)
        const header = w.find('.st-header').text()
        expect(header).toContain('Attempts')
        expect(header).toContain('Last submission')
        expect(w.findAll('.st-row')[0]!.text()).toContain('Passed, 7 Oct 2026')
        expect(w.findAll('button').filter(b => b.text() === 'End exam')).toHaveLength(1)
    })
})

describe('plagiarism check button', () => {
    const ended = { ...base, status: 'ended', took: 2, enrolled: 2 }

    it('offers to run the check on an exam that was never checked', async () => {
        mockApi(ended)
        const w = await render()
        expect(w.text()).toContain('Run plagiarism check')
        expect(w.text()).not.toContain('View plagiarism cases')
    })

    it('links to the case file once the exam has been checked', async () => {
        mockApi({ ...ended, similarity_pairs: 6, flagged_students: 4 })
        const w = await render()
        expect(w.text()).not.toContain('Run plagiarism check')
        const link = w.find('a.check-btn')
        expect(link.text()).toBe('View plagiarism cases')
        expect(link.attributes('href')).toBe('/dashboard/plagiarism/cohorts/9')
    })

    it('counts a completed check with no flags as checked', async () => {
        mockApi(ended)
        const inner = get.getMockImplementation()!
        get.mockImplementation((url: string, ...rest: unknown[]) =>
            url === '/plagiarism/runs/' ? Promise.resolve({ data: [{ id: 3, status: 'completed' }] }) : inner(url, ...rest))
        const w = await render()
        expect(w.find('a.check-btn').text()).toBe('View plagiarism cases')
    })
})

// Confirmed plagiarism costs the student their points; a pending flag only marks them for review.
describe('integrity status badge in the student cell', () => {
    const row = live.students[0]!
    const withStatus = (integrity_status: string | null, points_withheld: number, extra: object = {}) => ({
        ...live, students: [{ ...row, integrity_status, points_withheld, ...extra }],
    })

    it('shows the withheld points next to the name when plagiarism is confirmed', async () => {
        mockApi(withStatus('withheld', 20, { points: 10 }))
        const w = await render()
        const badge = w.find('.st-name .integrity-badge')
        expect(badge.exists()).toBe(true)
        expect(badge.text()).toContain('Points withheld · plagiarism confirmed')
        expect(badge.text()).toContain('−20')
        expect(badge.classes()).toContain('withheld')
    })

    it('leaves the amount out when the voided question earned nothing', async () => {
        mockApi(withStatus('withheld', 0))
        const w = await render()
        expect(w.find('.integrity-badge').text()).toBe('Points withheld · plagiarism confirmed')
    })

    it('marks a student with a pending flag as under review', async () => {
        mockApi(withStatus('under_review', 0))
        const w = await render()
        const badge = w.find('.st-name .integrity-badge')
        expect(badge.text()).toBe('Under review')
        expect(badge.classes()).toContain('review')
    })

    it('shows no badge for a student with neither', async () => {
        mockApi(withStatus(null, 0))
        const w = await render()
        expect(w.find('.integrity-badge').exists()).toBe(false)
    })

    it('does not add a column for it', async () => {
        mockApi(withStatus('withheld', 20))
        const w = await render()
        expect(w.find('.st-header').findAll('span')).toHaveLength(9)
    })
})


// The badge opens the student's case straight from the report; the name opens their page.
describe('integrity badge links to the case', () => {
    const row = live.students[0]!
    const report = (integrity_status: string | null, points_withheld: number, case_key: string | null) => ({
        ...live, students: [{ ...row, integrity_status, points_withheld, case_key }],
    })
    const href = (a: { attributes: (k: string) => string | undefined }) => decodeURIComponent(a.attributes('href') ?? '')

    it('opens a case still under review, saying it came from this report', async () => {
        mockApi(report('under_review', 0, '4'))
        const w = await render()
        const badge = w.find('a.integrity-badge')
        expect(badge.text()).toBe('Under review · Open case →')
        expect(badge.classes()).toContain('review')
        expect(href(badge)).toBe('/dashboard/plagiarism/cohorts/9?case=4&from=report:9')
        await badge.trigger('click')   // the case, not the row's student page
        await flushPromises()
        expect(router.currentRoute.value.fullPath).toContain('/dashboard/plagiarism/cohorts/9?case=4')
    })

    it('lets the trainer view a confirmed case', async () => {
        mockApi(report('withheld', 20, '4'))
        const w = await render()
        const badge = w.find('a.integrity-badge')
        expect(badge.text()).toBe('Points withheld · plagiarism confirmed · −20 · View case →')
        expect(href(badge)).toBe('/dashboard/plagiarism/cohorts/9?case=4&from=report:9')
    })

    it('still opens the student page from the name and the row', async () => {
        mockApi(report('under_review', 0, '4'))
        const w = await render()
        expect(w.find('a.st-link').attributes('href')).toBe('/dashboard/students/4')
        await w.find('.st-row').trigger('click')
        await flushPromises()
        expect(router.currentRoute.value.path).toBe('/dashboard/students/4')
    })

    it('shows what was just decided, coming back from a case', async () => {
        mockApi(report('withheld', 20, '4'))
        const w = await render({ caseNotice: 'Case confirmed for 2 students. Your note is on their results.' })
        expect(w.find('[role="status"]').text()).toBe('Case confirmed for 2 students. Your note is on their results.')
    })
})

describe('live exam before any check', () => {
    it('offers no Run button, says the check runs at the end, and ranks only students who submitted', async () => {
        mockApi(live)
        const w = await render()
        expect(w.text()).not.toContain('Run plagiarism check')
        expect(w.text()).toContain('Plagiarism check runs when the exam ends')
        expect(w.text()).toContain('#1')          // aarav submitted
        expect(w.text()).not.toContain('#2')      // tara has not: shown as a dash, not a rank
        expect(w.text()).not.toContain('None')
    })
})

describe('exam report ranks', () => {
    it('a student who submitted but has no points is "Not ranked"; one who never submitted shows —', async () => {
        const zero = { ...live.students[0], student_id: 6, username: 'zero_pts', full_name: 'Zero Points', points: 0, rank: null,
            passed: false, questions_solved: 0 }
        mockApi({ ...live, students: [live.students[0], zero, { ...live.students[1], rank: null }] })
        const w = await render()
        const cells = w.findAll('.st-row').map(r => r.find('span').text())
        expect(cells).toEqual(['#1', 'Not ranked', '—'])
    })
})

// A question voided for confirmed plagiarism is not solved: the Result column says why.
describe('exam report result when a question was not counted', () => {
    const row = live.students[0]!
    const report = (extra: object) => ({
        ...live, students: [{ ...row, total_questions: 2, integrity_status: 'withheld', points_withheld: 20, ...extra }],
    })
    const cells = (w: Awaited<ReturnType<typeof render>>) => w.find('.st-row').findAll(':scope > span')

    it('shows the counted solves and "Not passed · plagiarism" when it failed the exam', async () => {
        mockApi(report({ questions_solved: 0, questions_voided: 1, passed: false, points: 0 }))
        const w = await render()
        expect(cells(w)[4]!.text()).toBe('0/2')
        expect(cells(w)[5]!.text()).toBe('Not passed · plagiarism')
        expect(w.find('.st-name .integrity-badge').text()).toContain('Points withheld · plagiarism confirmed')
    })

    it('keeps "Passed" with a small note when the student still solved half', async () => {
        mockApi(report({ questions_solved: 1, questions_voided: 1, passed: true }))
        const w = await render()
        expect(cells(w)[5]!.find('.badge-yes').text()).toBe('Passed')
        expect(cells(w)[5]!.find('.result-note').text()).toBe('1 not counted: plagiarism confirmed')
    })

    it('adds nothing for a student with no voided question', async () => {
        mockApi(live)
        const w = await render()
        expect(cells(w)[5]!.text()).toBe('Passed')
    })
})
