import { describe, it, expect } from 'vitest'

import { submissionStatusLabel } from '../utils/format'
import { countsAsFlagged, maxConfidence } from '../utils/metrics'
import { canRunPlagiarismCheck, canStartExam, examStatusLabel } from '../utils/exams'

describe('submissionStatusLabel', () => {
  it('gives a submission that could not be graded one label on every page', () => {
    expect(submissionStatusLabel('error')).toBe("Couldn't run")
    expect(submissionStatusLabel('passed')).toBe('Passed')
    expect(submissionStatusLabel('failed')).toBe('Failed')
    expect(submissionStatusLabel('pending')).toBe('Pending')
  })
})

describe('countsAsFlagged', () => {
  it('leaves out dismissed flags, so confidence comes from the rest', () => {
    const flags = [
      { confidence: 'high', review_status: 'dismissed' },
      { confidence: 'low', review_status: 'pending' },
      { confidence: 'medium', review_status: 'confirmed' },
    ]
    expect(flags.filter(countsAsFlagged).map(f => f.confidence)).toEqual(['low', 'medium'])
    expect(maxConfidence(flags.filter(countsAsFlagged).map(f => f.confidence))).toBe('medium')
  })
})

describe('exam status', () => {
  it('labels the three server statuses', () => {
    expect(examStatusLabel('draft')).toBe('Draft')
    expect(examStatusLabel('live')).toBe('Live')
    expect(examStatusLabel('ended')).toBe('Ended')
  })

  it('lets a student start only a live exam they have not submitted, as the Exams page does', () => {
    expect(canStartExam({ is_active: true, finished_at: null })).toBe(true)
    expect(canStartExam({ is_active: true })).toBe(true)
    expect(canStartExam({ is_active: true, finished_at: '2026-10-07T10:00:00Z' })).toBe(false)
    expect(canStartExam({ is_active: false, finished_at: null })).toBe(false)
  })

  it('offers the plagiarism re-run on ended exams and on live ones with submissions', () => {
    expect(canRunPlagiarismCheck({ status: 'ended', total_submissions: 0 })).toBe(true)
    expect(canRunPlagiarismCheck({ status: 'live', total_submissions: 4 })).toBe(false)   // ending the exam runs the check
    expect(canRunPlagiarismCheck({ status: 'live', total_submissions: 0 })).toBe(false)
    expect(canRunPlagiarismCheck({ status: 'draft', total_submissions: 0 })).toBe(false)
  })
})
