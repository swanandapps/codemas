import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory, RouterView } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

const get = vi.fn()
const post = vi.fn()
const patch = vi.fn()
vi.mock('../api', () => ({ default: {
    get: (...a: unknown[]) => get(...a), post: (...a: unknown[]) => post(...a), patch: (...a: unknown[]) => patch(...a),
} }))

import MyResultsView from '../views/MyResultsView.vue'
import StudentDisputesView from '../views/StudentDisputesView.vue'
import NavBar from '../components/NavBar.vue'
import StudentDashboardView from '../views/StudentDashboardView.vue'
import DashboardView from '../views/DashboardView.vue'
import DisputeQueueView from '../views/DisputeQueueView.vue'
import DisputeDetailView from '../views/DisputeDetailView.vue'
import { useAuthStore } from '../stores/auth'
import { resetAttention } from '../utils/attention'
import { parseCaseFrom } from '../utils/caseFile'

// One-round appeals per exam, what students see of a decision, and the badges that say
// something is waiting.

async function mountAt(path: string, component: object, routePath = path.split('?')[0]!) {
    const router = createRouter({ history: createMemoryHistory(), routes: [
        { path: routePath, component },
        { path: '/:rest(.*)', component: { template: '<div />' } },
    ] })
    router.push(path)
    await router.isReady()
    const w = mount(RouterView, { global: { plugins: [router] }, attachTo: document.body })
    await flushPromises()
    return { w, router }
}

function respond(routes: Record<string, unknown>) {
    get.mockImplementation((url: string) => (url in routes
        ? Promise.resolve({ data: routes[url] })
        : Promise.reject(new Error(`no mock for ${url}`))))
}

beforeEach(() => {
    get.mockReset()
    post.mockReset()
    patch.mockReset()
    post.mockResolvedValue({ data: {} })
    resetAttention()
    setActivePinia(createPinia())
    Element.prototype.scrollIntoView = vi.fn()
})

// ── My results: the trainer review box ───────────────────────────────────────

const q = (id: number, title: string, withheld = 0) => ({
    question_id: id, title, difficulty: 'medium', points: 20, points_withheld: withheld, attempts: 3, passed_on: 3, status: 'passed',
})
function examRow(over: Record<string, unknown> = {}) {
    return {
        exam_id: 9, exam_title: 'Week 5', exam_date: '2026-10-01T10:00:00Z', questions_total: 2, questions_solved: 2,
        points: 10, points_withheld: 20, attempts: 4, passed: true, rank: 2, cohort_size: 3, summary_ready: false,
        questions: [q(1, 'QE'), q(2, 'QM', 20)],
        integrity: { outcome: 'withheld', points_withheld: 20, appeal: null, can_appeal: true },
        ...over,
    }
}
const reviews = [
    { kind: 'behaviour', exam_id: 9, question_id: 2, question_title: 'QM', submission_id: 13, attempt_number: 3,
        review_status: 'confirmed', review_note: 'Your code was pasted in.' },
    { kind: 'similarity', exam_id: 9, question_id: 2, question_title: 'QM', submission_id: 13, attempt_number: 3,
        review_status: 'confirmed', review_note: '' },
    { kind: 'behaviour', exam_id: 9, question_id: 2, question_title: 'QM', submission_id: 12, attempt_number: 2,
        review_status: 'confirmed', review_note: '' },
]
const appeal = (over: Record<string, unknown> = {}) => ({
    id: 5, exam_id: 9, exam_title: 'Week 5', status: 'open', student_note: 'I wrote it at home first.',
    decision_note: 'Your code was pasted in.', resolution_note: '', created_at: '2026-10-02T10:00:00Z',
    resolved_at: null, is_new: false, ...over,
})

async function myResults(opts: { exams?: unknown[]; reviews?: unknown[]; appeals?: unknown[]; path?: string } = {}) {
    respond({
        '/submissions/': { results: [], next: null },
        '/leaderboard/me/': { score: 10, score_available: 30, rank: 2, cohort_size: 3, ahead_of: 1, difficulty_progress: {} },
        '/leaderboard/me/exams/': opts.exams ?? [examRow()],
        '/plagiarism/mine/': opts.reviews ?? reviews,
        '/support/disputes/mine/': opts.appeals ?? [],
    })
    return mountAt(opts.path ?? '/results', MyResultsView, '/results')
}
const box = (w: ReturnType<typeof mount>) => w.find('.review-box')

describe('My results: trainer review box', () => {
    it('heads a withheld decision with its outcome, says the note once and tucks the attempts away', async () => {
        const { w } = await myResults()
        const text = box(w).text()
        expect(text).toContain('Points withheld: plagiarism confirmed (−20)')
        expect(text.split('Your code was pasted in.').length - 1).toBe(1)
        const details = box(w).find('details.review-details')
        expect(details.exists()).toBe(true)
        expect(details.attributes('open')).toBeUndefined()
        expect(details.text()).toContain('attempt 3')
        expect(details.text()).toContain('attempt 2')
    })

    it('lets the student respond once, with a required response', async () => {
        post.mockImplementation((url: string, body: { student_note: string }) => url === '/support/disputes/'
            ? Promise.resolve({ data: appeal({ student_note: body.student_note }) })
            : Promise.resolve({ data: {} }))
        const { w } = await myResults()
        await box(w).findAll('button').find(b => b.text() === 'Respond to this decision')!.trigger('click')
        const textarea = box(w).find('textarea')
        expect(box(w).find(`label[for="${textarea.attributes('id')}"]`).exists()).toBe(true)
        await box(w).find('button.appeal-submit').trigger('click')
        expect(box(w).text()).toContain('Write your response')
        expect(post).not.toHaveBeenCalledWith('/support/disputes/', expect.anything())
        await textarea.setValue('I wrote it at home first.')
        await box(w).find('button.appeal-submit').trigger('click')
        await flushPromises()
        expect(post).toHaveBeenCalledWith('/support/disputes/', { exam_id: 9, student_note: 'I wrote it at home first.' })
        expect(box(w).text()).toContain('Waiting for your trainer')
        expect(box(w).text()).toContain('I wrote it at home first.')
        expect(box(w).text()).not.toContain('Respond to this decision')
    })

    it('says "Reviewed — no action taken" for a dismissal with a note, with nothing to appeal', async () => {
        const { w } = await myResults({
            exams: [examRow({ points: 30, points_withheld: 0, questions: [q(1, 'QE'), q(2, 'QM')],
                integrity: { outcome: 'dismissed', points_withheld: 0, appeal: null, can_appeal: false } })],
            reviews: [{ ...reviews[0], review_status: 'dismissed', review_note: 'Checked: your own work.' }],
        })
        expect(box(w).text()).toContain('Reviewed — no action taken')
        expect(box(w).text()).toContain('Checked: your own work.')
        expect(box(w).text()).not.toContain('Respond to this decision')
    })

    it('shows an open appeal as waiting, with the response', async () => {
        const { w } = await myResults({
            exams: [examRow({ integrity: { outcome: 'withheld', points_withheld: 20, appeal: 'open', can_appeal: false } })],
            appeals: [appeal()],
        })
        expect(box(w).text()).toContain('Waiting for your trainer')
        expect(box(w).text()).toContain('I wrote it at home first.')
    })

    it('shows an upheld decision with the trainer reply', async () => {
        const { w } = await myResults({
            exams: [examRow({ integrity: { outcome: 'withheld', points_withheld: 20, appeal: 'upheld', can_appeal: false } })],
            appeals: [appeal({ status: 'upheld', resolution_note: 'The evidence stands.' })],
        })
        expect(box(w).text()).toContain('Decision upheld')
        expect(box(w).text()).toContain('The evidence stands.')
    })

    it('shows an overturned decision: points restored, the original note once and the reply once', async () => {
        const { w } = await myResults({
            exams: [examRow({ points: 30, points_withheld: 0, questions: [q(1, 'QE'), q(2, 'QM')],
                integrity: { outcome: 'overturned', points_withheld: 0, appeal: 'overturned', can_appeal: false } })],
            // the overturn rewrote the behaviour flag's note with the ruling; the pair kept the original
            reviews: [{ ...reviews[0], review_status: 'dismissed', review_note: 'You showed your drafts.' },
                { ...reviews[1], review_note: 'Your code was pasted in.' }],
            appeals: [appeal({ status: 'overturned', resolution_note: 'You showed your drafts.' })],
        })
        const text = box(w).text()
        expect(text).toContain('Decision overturned: points restored')
        expect(text).toContain('Decision overturned — points restored')
        expect(text.split('You showed your drafts.').length - 1).toBe(1)
        expect(text.split('Your code was pasted in.').length - 1).toBe(1)
    })

    it('ranks among those who took the exam, or says "Not ranked"', async () => {
        const { w } = await myResults({ exams: [
            examRow(),
            examRow({ exam_id: 8, exam_title: 'Week 4', exam_date: '2026-09-01T10:00:00Z', rank: null, integrity: null }),
        ] })
        const heads = w.findAll('.exam-head').map(h => h.text())
        expect(heads[0]).toContain('Section rank #2 of 3')
        expect(heads[1]).toContain('Not ranked')
    })

    it('marks decisions seen when opened', async () => {
        await myResults()
        expect(post).toHaveBeenCalledWith('/support/attention/seen/')
    })

    it('opens the exam named in the link at its review', async () => {
        const { w } = await myResults({
            path: '/results?exam=9',
            exams: [examRow({ exam_id: 10, exam_title: 'Week 6', exam_date: '2026-10-05T10:00:00Z', integrity: null,
                points_withheld: 0, questions: [q(3, 'Q6')] }), examRow()],
        })
        const week5 = w.findAll('article.exam').find(a => a.text().includes('Week 5'))!
        expect(week5.find('.review-box').exists()).toBe(true)
        expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
    })
})

// ── Student Disputes page ────────────────────────────────────────────────────

describe('Disputes (student)', () => {
    async function disputes(rows: unknown[], path = '/disputes') {
        respond({ '/support/disputes/mine/': rows })
        return mountAt(path, StudentDisputesView, '/disputes')
    }

    it('has an empty state', async () => {
        const { w } = await disputes([])
        expect(w.text()).toContain("You haven't disputed any decisions.")
    })

    it('lists appeals newest first with their status and the trainer reply once ruled', async () => {
        const { w } = await disputes([
            appeal({ id: 6, exam_id: 10, exam_title: 'Week 6' }),
            appeal({ status: 'overturned', resolution_note: 'You showed your drafts.', resolved_at: '2026-10-03T10:00:00Z', is_new: true }),
        ])
        const rows = w.findAll('.appeal-row')
        expect(rows.map(r => r.find('.appeal-exam').text())).toEqual(['Week 6', 'Week 5'])
        expect(rows[0]!.text()).toContain('Waiting for your trainer')
        expect(rows[1]!.text()).toContain('Decision overturned')
        expect(rows[1]!.text()).toContain('You showed your drafts.')
        expect(rows[1]!.text()).toContain('New')
    })

    it('expands to the decision, the response and a way to the review in My results', async () => {
        const { w } = await disputes([appeal()])
        const toggle = w.find('.appeal-row button.appeal-toggle')
        expect(toggle.attributes('aria-expanded')).toBe('false')
        await toggle.trigger('click')
        expect(toggle.attributes('aria-expanded')).toBe('true')
        const body = w.find('.appeal-body')
        expect(body.text()).toContain('Your code was pasted in.')
        expect(body.text()).toContain('I wrote it at home first.')
        const link = body.findAll('a').find(a => a.text().includes('View in My results'))!
        expect(link.attributes('href')).toBe('/results?exam=9')
    })

    it('marks rulings seen when opened', async () => {
        await disputes([])
        expect(post).toHaveBeenCalledWith('/support/attention/seen/')
    })
})

// ── Badges and banners ───────────────────────────────────────────────────────

describe('sidebar badges', () => {
    async function nav(role: 'student' | 'trainer', attention: object) {
        useAuthStore().user = { id: 1, username: 'u', email: '', role, cohort: 'A' }
        respond({ '/support/attention/': attention })
        return mountAt('/home', NavBar)
    }
    const badgeOn = (w: ReturnType<typeof mount>, label: string) =>
        w.findAll('a.nav-item').find(a => a.text().startsWith(label))!.find('.nav-badge')

    it('student: new decisions on My results, new rulings on Disputes (after My results)', async () => {
        const { w } = await nav('student', { new_decisions: 2, new_rulings: 1, latest: null })
        const labels = w.findAll('a.nav-item').map(a => a.text().replace(/\d+.*$/, '').trim())
        expect(labels.indexOf('Disputes')).toBe(labels.indexOf('My results') + 1)
        expect(badgeOn(w, 'My results').text()).toBe('2')
        expect(badgeOn(w, 'Disputes').text()).toBe('1')
        expect(w.findAll('a.nav-item').find(a => a.text().startsWith('Disputes'))!.attributes('href')).toBe('/disputes')
    })

    it('trainer: cases to decide on Investigation, open appeals on Disputes', async () => {
        const { w } = await nav('trainer', { open_appeals: 3, cases_to_decide: 4 })
        expect(badgeOn(w, 'Investigation').text()).toBe('4')
        expect(badgeOn(w, 'Disputes').text()).toBe('3')
    })

    it('no badge when nothing is waiting', async () => {
        const { w } = await nav('trainer', { open_appeals: 0, cases_to_decide: 0 })
        expect(w.find('.nav-badge').exists()).toBe(false)
    })
})

describe('Home banner', () => {
    async function home(latest: object | null) {
        useAuthStore().user = { id: 1, username: 'u', email: '', role: 'student', cohort: 'A' }
        respond({ '/exams/': [], '/submissions/': [], '/leaderboard/me/': {}, '/leaderboard/': { leaderboard: [] },
            '/support/attention/': { new_decisions: 1, new_rulings: 0, latest } })
        return mountAt('/home', StudentDashboardView)
    }

    it('points to a new decision', async () => {
        const { w } = await home({ kind: 'decision', exam_id: 9, exam_title: 'Week 5', at: '2026-10-02T10:00:00Z' })
        const link = w.find('a.attention-banner')
        expect(link.text()).toBe('Your trainer reviewed Week 5. See the decision →')
        expect(link.attributes('href')).toBe('/results?exam=9')
    })

    it('points to a ruling', async () => {
        const { w } = await home({ kind: 'ruling', exam_id: 9, exam_title: 'Week 5', appeal_id: 5, status: 'upheld', at: '2026-10-02T10:00:00Z' })
        const link = w.find('a.attention-banner')
        expect(link.text()).toBe('Your appeal for Week 5 was upheld →')
        expect(link.attributes('href')).toBe('/disputes?appeal=5')
    })

    it('stays away when nothing is new', async () => {
        const { w } = await home(null)
        expect(w.find('.attention-banner').exists()).toBe(false)
    })
})

describe('Overview: what is waiting', () => {
    const health = { summary: { students: 3, cohorts: 1, unassigned_students: 0, latest_exam: null },
        cohorts: [], exams: [], students_needing_help: [], rules: { at_risk: {}, watch: {} } }

    async function overview(attention: object) {
        respond({ '/dashboard/health/': health, '/support/attention/': attention })
        return mountAt('/dashboard', DashboardView)
    }

    it('names appeals and cases with links', async () => {
        const { w } = await overview({ open_appeals: 2, cases_to_decide: 3 })
        const line = w.find('.waiting-line')
        expect(line.text()).toBe('2 appeals and 3 cases waiting for you')
        const hrefs = line.findAll('a').map(a => a.attributes('href'))
        expect(hrefs).toEqual(['/dashboard/support/disputes', '/dashboard/plagiarism/cohorts'])
    })

    it('leaves out a zero', async () => {
        const { w } = await overview({ open_appeals: 1, cases_to_decide: 0 })
        expect(w.find('.waiting-line').text()).toBe('1 appeal waiting for you')
    })

    it('is hidden when nothing waits', async () => {
        const { w } = await overview({ open_appeals: 0, cases_to_decide: 0 })
        expect(w.find('.waiting-line').exists()).toBe(false)
    })
})

// ── Trainer Disputes ─────────────────────────────────────────────────────────

const trainerRow = (over: Record<string, unknown> = {}) => ({
    id: 7, student: 4, student_username: 'aarav_sharma0', exam_id: 9, exam_title: 'Week 5', flag_type: null, flag_id: null,
    status: 'open', student_note: 'I wrote it at home first.', decision_note: 'Your code was pasted in.',
    resolution_note: '', created_at: '2026-10-02T10:00:00Z', resolved_at: null, resolved_by_username: null, case_key: '4',
    ...over,
})

describe('Disputes (trainer)', () => {
    it('filters by Open, Upheld, Overturned and All', async () => {
        get.mockResolvedValue({ data: [trainerRow()] })
        const { w } = await mountAt('/dashboard/support/disputes', DisputeQueueView)
        const chips = w.findAll('button.filter-btn')
        expect(chips.map(c => c.text())).toEqual(['Open', 'Upheld', 'Overturned', 'All'])
        expect(chips[0]!.attributes('aria-pressed')).toBe('true')
        await chips[1]!.trigger('click')
        await flushPromises()
        expect(get).toHaveBeenLastCalledWith('/support/disputes/?status=upheld')
    })

    it('lists the student, exam, date, status, response and a link to the case', async () => {
        get.mockResolvedValue({ data: [trainerRow()] })
        const { w } = await mountAt('/dashboard/support/disputes', DisputeQueueView)
        const row = w.find('.dispute-card')
        for (const t of ['aarav_sharma0', 'Week 5', 'Open', 'I wrote it at home first.']) expect(row.text()).toContain(t)
        const caseLink = row.findAll('a').find(a => a.text().includes('View case'))!
        expect(caseLink.attributes('href')).toBe('/dashboard/plagiarism/cohorts/9?case=4&from=dispute:7')
    })

    it('shows a legacy per-flag dispute by its flag\'s exam', async () => {
        get.mockResolvedValue({ data: [trainerRow({ exam_id: null, exam_title: null, case_key: null, flag_type: 'behavioural',
            flag_id: 20, status: 'upheld', flag_context: { exam: 'Week 1', question: 'FizzBuzz' } })] })
        const { w } = await mountAt('/dashboard/support/disputes', DisputeQueueView)
        expect(w.find('.dispute-card').text()).toContain('Week 1')
        expect(w.find('.dispute-card').text()).toContain('Upheld')
    })

    it('the case file links back to the appeal it was opened from', () => {
        expect(parseCaseFrom('dispute:7')).toEqual({ kind: 'dispute', id: 7 })
    })
})

describe('Appeal detail (trainer)', () => {
    async function detail(row: object) {
        get.mockResolvedValue({ data: row })
        return mountAt('/dashboard/support/disputes/7', DisputeDetailView, '/dashboard/support/disputes/:id')
    }
    const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find(b => b.text() === text)!

    it('shows the original decision, the response and the case', async () => {
        const { w } = await detail(trainerRow())
        expect(w.text()).toContain('Your code was pasted in.')
        expect(w.text()).toContain('I wrote it at home first.')
        expect(w.findAll('a').some(a => a.attributes('href') === '/dashboard/plagiarism/cohorts/9?case=4&from=dispute:7')).toBe(true)
    })

    it('overturn explains what changes and needs a reply', async () => {
        patch.mockResolvedValue({ data: trainerRow({ status: 'overturned', resolution_note: 'You showed your drafts.',
            resolved_by_username: 'trainer1', resolved_at: '2026-10-03T10:00:00Z' }) })
        const { w } = await detail(trainerRow())
        await button(w, 'Overturn').trigger('click')
        expect(w.text()).toContain('Their behaviour flags on this exam become dismissed; their points are restored. Classmates are not affected.')
        await button(w, 'Overturn decision').trigger('click')
        expect(patch).not.toHaveBeenCalled()
        expect(w.text()).toContain('Write a reply')
        const reply = w.find('textarea')
        expect(w.find(`label[for="${reply.attributes('id')}"]`).exists()).toBe(true)
        await reply.setValue('You showed your drafts.')
        await button(w, 'Overturn decision').trigger('click')
        await flushPromises()
        expect(patch).toHaveBeenCalledWith('/support/disputes/7/', { decision: 'overturn', resolution_note: 'You showed your drafts.' })
        expect(w.text()).toContain('Overturned')
        expect(w.text()).toContain('You showed your drafts.')
        expect(w.findAll('button').some(b => b.text() === 'Uphold')).toBe(false)
    })

    it('uphold sends the reply', async () => {
        patch.mockResolvedValue({ data: trainerRow({ status: 'upheld', resolution_note: 'It stands.' }) })
        const { w } = await detail(trainerRow())
        await button(w, 'Uphold').trigger('click')
        await w.find('textarea').setValue('It stands.')
        await button(w, 'Uphold decision').trigger('click')
        await flushPromises()
        expect(patch).toHaveBeenCalledWith('/support/disputes/7/', { decision: 'uphold', resolution_note: 'It stands.' })
    })

    it('a ruled appeal is final: no actions', async () => {
        const { w } = await detail(trainerRow({ status: 'upheld', resolution_note: 'It stands.' }))
        expect(w.text()).toContain('It stands.')
        expect(w.findAll('button').some(b => ['Uphold', 'Overturn'].includes(b.text()))).toBe(false)
    })
})

// ── My results: a question voided for confirmed plagiarism is not solved ─────────

describe('My results: a voided question does not count as solved', () => {
    const voidedQ = { ...q(2, 'QM', 20), passed_on: 2, voided: true }
    const stat = (w: ReturnType<typeof mount>, label: string) =>
        w.findAll('.stats > div').find(d => d.find('small').text().startsWith(label))!

    it('fails the exam and says why when the voided question was the only solve', async () => {
        const { w } = await myResults({ exams: [examRow({
            questions_total: 1, questions_solved: 0, questions_voided: 1, passed: false, points: 0,
            questions: [voidedQ],
        })] })
        expect(stat(w, 'Questions solved').find('b').text()).toBe('0 / 1')
        expect(stat(w, 'Questions solved').text()).toContain('1 not counted: plagiarism confirmed')
        expect(stat(w, 'Result').find('b').text()).toBe('Not passed')
        expect(stat(w, 'Result').text()).toContain('Plagiarism confirmed by your trainer')
        expect(w.find('.q-row').text()).toContain('Tests passed on attempt 2 · Not counted: plagiarism')
        expect(w.find('.q-row').text()).not.toContain('Passed on attempt')
        expect(w.find('.q-row').text()).toContain('Points withheld · −20')
    })

    it('keeps the pass, with a note, when enough other questions were solved', async () => {
        const { w } = await myResults({ exams: [examRow({
            questions_total: 2, questions_solved: 1, questions_voided: 1, passed: true,
            questions: [q(1, 'QE'), voidedQ],
        })] })
        expect(stat(w, 'Questions solved').find('b').text()).toBe('1 / 2')
        expect(stat(w, 'Result').find('b').text()).toBe('Passed')
        expect(stat(w, 'Result').text()).toContain('1 question not counted: plagiarism confirmed')
        const rows = w.findAll('.q-row')
        expect(rows[0]!.text()).toContain('Passed on attempt 3')
        expect(rows[1]!.text()).toContain('Tests passed on attempt 2 · Not counted: plagiarism')
    })

    it('says why in the collapsed exam line too', async () => {
        const failed = examRow({ exam_id: 8, exam_title: 'Week 4', exam_date: '2026-09-24T10:00:00Z',
            questions_total: 1, questions_solved: 0, questions_voided: 1, passed: false, questions: [voidedQ], integrity: null })
        const { w } = await myResults({ exams: [examRow({ questions_voided: 0 }), failed] })
        const head = w.findAll('.exam-head')[1]!.text()
        expect(head).toContain('0 / 1 solved · Not passed · plagiarism confirmed')
    })

    it('adds nothing when no question was voided', async () => {
        const { w } = await myResults({ exams: [examRow({ questions_voided: 0, points_withheld: 0, questions: [q(1, 'QE'), q(2, 'QM')] })] })
        expect(w.find('.stats').text()).not.toContain('not counted')
        expect(w.find('.stats').text()).not.toContain('Plagiarism confirmed')
    })
})
