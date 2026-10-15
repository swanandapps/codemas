import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory, RouterView } from 'vue-router'

const get = vi.fn()
const patch = vi.fn()
vi.mock('../api', () => ({ default: { get: (...a: unknown[]) => get(...a), patch: (...a: unknown[]) => patch(...a) } }))

import CohortDetailView from '../views/CohortDetailView.vue'

const members = [
    { student_id: 1, username: 'aarav_sharma0', first_name: 'Aarav' },
    { student_id: 2, username: 'tara_shah96', first_name: 'Tara' },
]
const bFlag = {
    id: 20, submission_id: 101, student: 'aarav_sharma0', student_id: 1, question_title: 'Palindrome',
    question_difficulty: 'medium', exam_title: 'Palindrome Checker', exam_id: 9, attempt_number: 1,
    submission_status: 'passed', language: 'javascript', submitted_at: '2026-10-07T13:38:00Z',
    risk_score: 0.7, confidence: 'medium', paste_score: 1, time_score: 1, snapshot_score: 0, submission_score: 0,
    signals_triggered: ['Pasted 100% of final code (485 chars)', 'Submitted 39s after starting, on a medium problem (typical: 4m 0s)'],
    review_status: 'pending', review_note: '',
}
const detail = {
    exam: { id: 9, title: 'Palindrome Checker', status: 'live', question_count: 1, duration_minutes: 30,
        start_time: '2026-10-07T13:00:00Z', end_time: null, last_checked_at: null },
    stats: { took: 2, enrolled: 103, took_rate: 1.9, flagged_students: 1, flagged_students_rate: 50,
        total_submissions: 3, similarity_count: 1, cases_to_decide: 1, health: 'red' },
    students: [],
    rings: [{ size: 2, members, avg_similarity: 1, max_similarity: 1, confirmed: 0, case: '1' }],
    cases: [{
        key: '1', number: 1, members, status: 'pending', pending: 2, max_similarity: 1, max_risk: 70,
        pairs: [{ id: 10, submission_1: 101, submission_2: 102, student_1_id: 1, student_2_id: 2, attempt_1: 1,
            attempt_2: 3, question_title: 'Palindrome', similarity_score: 1, review_status: 'pending', review_note: '' }],
        behavioural: [bFlag],
    }],
}

async function render(path: string) {
    const router = createRouter({ history: createMemoryHistory(), routes: [
        { path: '/dashboard/plagiarism/cohorts/:id', name: 'cohort-detail', component: CohortDetailView },
        { path: '/:rest(.*)', component: { template: '<div />' } },
    ] })
    router.push(path)
    await router.isReady()
    // through the router view, as in the app: leaving the case unmounts it
    const wrapper = mount(RouterView, { global: { plugins: [router] } })
    await flushPromises()
    return { wrapper, router }
}

beforeEach(() => {
    get.mockReset()
    patch.mockReset()
    window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
    get.mockImplementation((url: string) => url.startsWith('/plagiarism/cohorts/')
        ? Promise.resolve({ data: detail })
        : Promise.resolve({ data: { code: 'let a = 1;' } }))
})

describe('exam case file', () => {
    it('lists the cases with the KPIs, and no exam controls', async () => {
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9')
        const text = wrapper.text()
        expect(text).toContain('Cases to decide')
        expect(text).toContain('Case 1')
        expect(text).toContain('Open case →')
        expect(text).toContain('Waiting: 1 similarity pair, 1 behaviour flag on Aarav')
        expect(text).toContain('1 question · 30 min · started')
        expect(text).not.toContain('Run plagiarism check')
        expect(text).not.toContain('End exam')
    })

    it('opens a case from the query and confirms every pending flag with one note', async () => {
        patch.mockResolvedValue({ data: {} })
        const { wrapper, router } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        expect(wrapper.text()).toContain(
            'Their code is identical once variable names are set aside, and Aarav pasted all of the final code 39 seconds after starting.')
        // tara only matched Aarav's code: she isn't sent the note unless the trainer chooses to
        expect(wrapper.find('.decision-bar').text()).toContain("tara_shah96 only matched and won't get the note.")
        await wrapper.find('#case-note').setValue('Same code')
        await wrapper.findAll('button').find(b => b.text() === 'Confirm case')!.trigger('click')
        await flushPromises()
        expect(patch).toHaveBeenCalledWith('/plagiarism/10/review/', { review_status: 'confirmed', review_note: '' })
        expect(patch).toHaveBeenCalledWith('/plagiarism/behavioural/20/review/', { review_status: 'confirmed', review_note: 'Same code' })
        // opened from the investigation itself: it stays on the case
        expect(router.currentRoute.value.fullPath).toBe('/dashboard/plagiarism/cohorts/9?case=1')
        expect(wrapper.find('.from-back').exists()).toBe(false)
    })

    it('says which flags did not save and retries only those', async () => {
        patch.mockImplementation((url: string) => url.includes('behavioural') ? Promise.reject(new Error('down')) : Promise.resolve({ data: {} }))
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        await wrapper.findAll('button').find(b => b.text() === 'Dismiss case')!.trigger('click')
        await flushPromises()
        expect(wrapper.find('[role="alert"]').text()).toContain("1 flag didn't save: Behaviour flag on aarav_sharma0")
        patch.mockReset()
        patch.mockResolvedValue({ data: {} })
        await wrapper.findAll('button').find(b => b.text() === 'Retry')!.trigger('click')
        await flushPromises()
        expect(patch).toHaveBeenCalledTimes(1)
        expect(patch).toHaveBeenCalledWith('/plagiarism/behavioural/20/review/', { review_status: 'dismissed', review_note: '' })
    })
})

function groupDetail(n: number, score: (i: number, j: number) => number) {
    const people = Array.from({ length: n }, (_, i) => ({ student_id: i + 1, username: `student_${i + 1}`, first_name: '' }))
    const pairs = []
    let id = 100
    for (let i = 1; i <= n; i++) for (let j = i + 1; j <= n; j++) {
        pairs.push({ id: id++, submission_1: i * 10, submission_2: j * 10, student_1_id: i, student_2_id: j, attempt_1: 1,
            attempt_2: 1, question_title: 'Palindrome', similarity_score: score(i, j), review_status: 'pending', review_note: '' })
    }
    return { ...detail, cases: [{ key: '1', number: 1, members: people, status: 'pending', pending: pairs.length,
        max_similarity: 1, max_risk: null, pairs, behavioural: [] }] }
}

describe('matching code in an opened case', () => {
    it('shows a grid of who matches whom and one comparison, swapped in place', async () => {
        const four = groupDetail(4, (i, j) => (i === 1 && j === 2 ? 1 : 0.9))
        get.mockImplementation((url: string) => url.startsWith('/plagiarism/cohorts/')
            ? Promise.resolve({ data: four })
            : Promise.resolve({ data: { code: 'let a = 1;' } }))
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        const text = wrapper.text()
        expect(text).toContain('6 similarity pairs among 4 students, strongest 100%.')
        expect(text.match(/Red = same line once names are set aside/g)).toHaveLength(1)
        const cells = wrapper.findAll('button.grid-cell')
        expect(cells).toHaveLength(12)
        // strongest pair first and selected, in both of its cells
        const pressed = cells.filter(c => c.attributes('aria-pressed') === 'true')
        expect(pressed.map(c => c.attributes('aria-label'))).toEqual([
            'Compare student_1 and student_2, 100% match', 'Compare student_2 and student_1, 100% match'])
        expect(wrapper.find('.viewer-title').text()).toBe('student_1 and student_2 · 100% match')
        await cells.find(c => c.attributes('aria-label') === 'Compare student_3 and student_4, 90.0% match')!.trigger('click')
        expect(wrapper.find('.viewer-title').text()).toBe('student_3 and student_4 · 90.0% match')
        expect(wrapper.find('[role="status"]').text()).toBe('Showing student_3 and student_4, 90.0% match')
        expect(wrapper.findAll('.similarity-evidence')).toHaveLength(1)
        // deciding each flag separately still lists every pair
        await wrapper.findAll('button').find(b => b.text() === 'Decide each flag separately')!.trigger('click')
        expect(wrapper.findAll('.per-flag-row')).toHaveLength(6)
    })

    it('says so when everyone handed in the same code', async () => {
        const same = groupDetail(4, () => 1)
        get.mockImplementation((url: string) => url.startsWith('/plagiarism/cohorts/')
            ? Promise.resolve({ data: same })
            : Promise.resolve({ data: { code: 'let a = 1;' } }))
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        expect(wrapper.text()).toContain('All 4 students submitted the same code once variable names are set aside.')
    })

    it('lists the pairs strongest first instead of a grid in a big case', async () => {
        const big = groupDetail(11, (i, j) => (i === 10 && j === 11 ? 0.99 : 0.85))
        get.mockImplementation((url: string) => url.startsWith('/plagiarism/cohorts/')
            ? Promise.resolve({ data: big })
            : Promise.resolve({ data: { code: 'let a = 1;' } }))
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        expect(wrapper.find('.sim-grid').exists()).toBe(false)
        let lines = wrapper.findAll('button.pair-line')
        expect(lines).toHaveLength(10)
        expect(lines[0]!.text()).toContain('student_10 and student_11')
        expect(lines[0]!.attributes('aria-pressed')).toBe('true')
        await wrapper.findAll('button').find(b => b.text() === 'Show all 55 pairs')!.trigger('click')
        lines = wrapper.findAll('button.pair-line')
        expect(lines).toHaveLength(55)
        await lines[5]!.trigger('click')
        expect(lines[5]!.attributes('aria-pressed')).toBe('true')
        expect(wrapper.find('.viewer-title').text()).toContain('· 85.0% match')
    })
})


// A case with three students: aarav and tara both have behaviour flags, carol only matched aarav's code.
const carol = { student_id: 3, username: 'carol_d', first_name: 'Carol' }
const three = {
    ...detail,
    cases: [{
        key: '1', number: 1, members: [...members, carol], status: 'pending', pending: 4, max_similarity: 1, max_risk: 70,
        pairs: [
            { id: 10, submission_1: 101, submission_2: 102, student_1_id: 1, student_2_id: 2, attempt_1: 1,
                attempt_2: 3, question_title: 'Palindrome', similarity_score: 1, review_status: 'pending', review_note: '' },
            { id: 11, submission_1: 101, submission_2: 103, student_1_id: 1, student_2_id: 3, attempt_1: 1,
                attempt_2: 1, question_title: 'Palindrome', similarity_score: 0.9, review_status: 'pending', review_note: '' },
        ],
        behavioural: [bFlag, { ...bFlag, id: 21, submission_id: 102, student: 'tara_shah96', student_id: 2, risk_score: 0.5 }],
    }],
}

function serve(data: object) {
    get.mockImplementation((url: string) => url.startsWith('/plagiarism/cohorts/')
        ? Promise.resolve({ data })
        : Promise.resolve({ data: { code: 'let a = 1;' } }))
}
const button = (w: ReturnType<typeof mount>, label: string) => w.findAll('button').find(b => b.text() === label)!
const notesSent = () => Object.fromEntries(patch.mock.calls.map(([url, body]) => [url, (body as { review_note: string }).review_note]))

describe('a case opened from a student page', () => {
    it('leads back to the student, and highlights them in the grid and their behaviour card', async () => {
        serve(groupDetail(4, () => 0.9))
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1&from=student:2')
        const back = wrapper.find('a.from-back')
        expect(back.text()).toBe('← Back to student_2')
        expect(back.attributes('href')).toBe('/dashboard/students/2?tab=integrity')
        const marked = wrapper.findAll('.sim-grid th.focus')
        expect(marked.map(th => th.text())).toEqual(['student_2', 'student_2'])   // their column and their row
        expect(wrapper.findAll('.sim-grid td.focus')).toHaveLength(7)
        expect(wrapper.text()).toContain("student_2's row and column are highlighted.")
        const card = wrapper.find('[aria-label="student_2\'s behaviour"]')
        expect(card.classes()).toContain('focus')
        expect(wrapper.findAll('.behaviour-card.focus')).toHaveLength(1)
    })

    it('goes back to the student with what was decided once the case is confirmed', async () => {
        patch.mockResolvedValue({ data: {} })
        const { wrapper, router } = await render('/dashboard/plagiarism/cohorts/9?case=1&from=student:1')
        await wrapper.find('#case-note').setValue('Same code')
        await button(wrapper, 'Confirm case').trigger('click')
        await flushPromises()
        expect(router.currentRoute.value.fullPath).toBe('/dashboard/students/1?tab=integrity')
        expect(router.options.history.state.caseNotice).toBe(
            'Case confirmed for 2 students. Your note is on the results of 1 of them.')
    })

    it('stays on the case when a flag did not save', async () => {
        patch.mockImplementation((url: string) => url.includes('behavioural') ? Promise.reject(new Error('down')) : Promise.resolve({ data: {} }))
        const { wrapper, router } = await render('/dashboard/plagiarism/cohorts/9?case=1&from=student:1')
        await button(wrapper, 'Confirm case').trigger('click')
        await flushPromises()
        expect(router.currentRoute.value.path).toBe('/dashboard/plagiarism/cohorts/9')
        expect(wrapper.find('[role="alert"]').text()).toContain("didn't save")
    })
})

describe('a case opened from the exam report', () => {
    it('leads back to the report, and returns there after the decision', async () => {
        patch.mockResolvedValue({ data: {} })
        const { wrapper, router } = await render('/dashboard/plagiarism/cohorts/9?case=1&from=report:9')
        const back = wrapper.find('a.from-back')
        expect(back.text()).toBe('← Back to Palindrome Checker report')
        expect(back.attributes('href')).toBe('/dashboard/history/9')
        expect(wrapper.findAll('.focus')).toHaveLength(0)
        await button(wrapper, 'Dismiss case').trigger('click')
        await flushPromises()
        expect(router.currentRoute.value.fullPath).toBe('/dashboard/history/9')
        expect(router.options.history.state.caseNotice).toBe('Case dismissed for 2 students.')
    })
})

describe('notes per student', () => {
    it('opens one note box per student, filled with the group note; a matched-only student is left out', async () => {
        serve(three)
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        await wrapper.find('#case-note').setValue('Same code')
        const toggle = button(wrapper, 'Write separate notes')
        expect(toggle.attributes('aria-expanded')).toBe('false')
        await toggle.trigger('click')
        expect(button(wrapper, 'Use one note for everyone').attributes('aria-expanded')).toBe('true')
        expect((wrapper.find('#note-1').element as HTMLInputElement).value).toBe('Same code')
        expect((wrapper.find('#note-2').element as HTMLInputElement).value).toBe('Same code')
        expect(wrapper.find('label[for="note-1"]').text()).toBe('Note to aarav_sharma0')
        expect(wrapper.find('#note-3').exists()).toBe(false)
        expect(wrapper.text()).toContain('No behaviour signals — matched only')
        const send = wrapper.find('#send-3')
        expect((send.element as HTMLInputElement).checked).toBe(false)
        expect(wrapper.find('label[for="send-3"]').text()).toBe('Send note to carol_d')
    })

    it('sends the group note to everyone with a behaviour flag, and none to the matched-only student', async () => {
        serve(three)
        patch.mockResolvedValue({ data: {} })
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        await wrapper.find('#case-note').setValue('Same code')
        await button(wrapper, 'Confirm case').trigger('click')
        await flushPromises()
        expect(notesSent()).toEqual({
            '/plagiarism/10/review/': 'Same code',
            '/plagiarism/11/review/': '',
            '/plagiarism/behavioural/20/review/': 'Same code',
            '/plagiarism/behavioural/21/review/': 'Same code',
        })
    })

    it('puts separate notes on each student\'s own flags, and none on a pair whose students differ', async () => {
        serve(three)
        patch.mockResolvedValue({ data: {} })
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        await wrapper.find('#case-note').setValue('Same code')
        await button(wrapper, 'Write separate notes').trigger('click')
        await wrapper.find('#note-1').setValue('You shared your code')
        await wrapper.find('#note-2').setValue('You copied the code')
        await button(wrapper, 'Confirm case').trigger('click')
        await flushPromises()
        expect(notesSent()).toEqual({
            '/plagiarism/10/review/': '',
            '/plagiarism/11/review/': '',
            '/plagiarism/behavioural/20/review/': 'You shared your code',
            '/plagiarism/behavioural/21/review/': 'You copied the code',
        })
    })

    it('sends the matched-only student a note when ticked, through the pair it shares', async () => {
        serve(three)
        patch.mockResolvedValue({ data: {} })
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        await wrapper.find('#case-note').setValue('Same code')
        await button(wrapper, 'Write separate notes').trigger('click')
        await wrapper.find('#send-3').setValue(true)
        expect((wrapper.find('#note-3').element as HTMLInputElement).value).toBe('Same code')
        await button(wrapper, 'Confirm case').trigger('click')
        await flushPromises()
        expect(notesSent()['/plagiarism/11/review/']).toBe('Same code')
    })

    it('warns when a matched-only student\'s own words have no flag to reach them', async () => {
        serve(three)
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        await button(wrapper, 'Write separate notes').trigger('click')
        await wrapper.find('#send-3').setValue(true)
        await wrapper.find('#note-3').setValue('Please talk to me')
        expect(wrapper.find('#note-3-warn').text()).toContain("carol_d won't see this note")
        expect(wrapper.find('#note-3').attributes('aria-describedby')).toBe('note-3-warn')
    })
})

describe('appeals on the case file', () => {
    const withAppeal = { ...detail, appeals: [{ id: 7, student_id: 1, student_note: 'I wrote it at home first.', created_at: '2026-10-08T10:00:00Z' }] }

    it('marks a case with an open appeal, on the list and in the case, with the response and a link', async () => {
        get.mockImplementation((url: string) => url.startsWith('/plagiarism/cohorts/')
            ? Promise.resolve({ data: withAppeal }) : Promise.resolve({ data: { code: '' } }))
        const list = await render('/dashboard/plagiarism/cohorts/9')
        expect(list.wrapper.text()).toContain('Appeal pending')
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        const note = wrapper.find('.appeal-note')
        expect(note.text()).toContain('Appeal pending')
        expect(note.text()).toContain('aarav_sharma0')
        expect(note.text()).toContain('I wrote it at home first.')
        expect(note.findAll('a').some(a => a.attributes('href') === '/dashboard/support/disputes/7')).toBe(true)
    })

    it('shows nothing when there is no open appeal', async () => {
        const { wrapper } = await render('/dashboard/plagiarism/cohorts/9?case=1')
        expect(wrapper.text()).not.toContain('Appeal pending')
    })
})
