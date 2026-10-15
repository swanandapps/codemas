import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'

import { saveDraft, loadDraft, clearDraft, DRAFT_MAX_AGE_MS } from '../utils/createExamDraft'

// The Create exam page keeps its unsaved work in this browser so a reload doesn't lose a generated
// draft (and cost another generation): per trainer, until saved or discarded, at most a week old.
describe('create exam draft storage', () => {
    beforeEach(() => localStorage.clear())
    afterEach(() => vi.useRealTimers())

    it('round-trips a draft for the same trainer only', () => {
        saveDraft('venugopal', { step: 'review', draft: { title: 'Binary Search' } })
        expect(loadDraft('venugopal')).toMatchObject({ step: 'review', draft: { title: 'Binary Search' } })
        expect(loadDraft('another_trainer')).toBeNull()
    })

    it('clears a draft', () => {
        saveDraft('venugopal', { step: 'review' })
        clearDraft('venugopal')
        expect(loadDraft('venugopal')).toBeNull()
    })

    it('drops a draft older than a week', () => {
        vi.useFakeTimers()
        vi.setSystemTime(new Date('2026-10-01T10:00:00Z'))
        saveDraft('venugopal', { step: 'review' })
        vi.setSystemTime(new Date(Date.parse('2026-10-01T10:00:00Z') + DRAFT_MAX_AGE_MS + 1000))
        expect(loadDraft('venugopal')).toBeNull()
    })

    it('ignores broken storage and never throws', () => {
        localStorage.setItem('codemas:create-exam-draft:venugopal', '{not json')
        expect(loadDraft('venugopal')).toBeNull()
        const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('full') })
        expect(() => saveDraft('venugopal', { step: 'review' })).not.toThrow()
        setItem.mockRestore()
    })

    it('needs a trainer to key the draft by', () => {
        saveDraft(undefined, { step: 'review' })
        expect(loadDraft(undefined)).toBeNull()
    })
})
