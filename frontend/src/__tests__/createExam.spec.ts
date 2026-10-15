import { describe, it, expect } from 'vitest'

import { shortTitle } from '../utils/questionFields'
import { scheduleProblems, toLocalInput } from '../utils/exams'

describe('shortTitle', () => {
  it('uses the first sentence when it is short', () => {
    expect(shortTitle('Reverse a string. Keep the spaces.')).toBe('Reverse a string')
  })

  it('cuts a long sentence to about six words without ending on a small word', () => {
    expect(shortTitle('Given an array of integers and a target, return two indices.')).toBe('Given an array of integers')
  })

  it('capitalises the first letter and keeps the rest as typed', () => {
    expect(shortTitle('count the vowels in a JSON string')).toBe('Count the vowels in a JSON')
  })

  it('reads only the first line', () => {
    expect(shortTitle('Sum two numbers\nInput format: two ints')).toBe('Sum two numbers')
  })

  it('is empty for empty text, so the caller can fall back to "Question N"', () => {
    expect(shortTitle('')).toBe('')
    expect(shortTitle('   \n ')).toBe('')
    expect(shortTitle(undefined)).toBe('')
  })

  it('works on a topic typed for generation', () => {
    expect(shortTitle('beginner JavaScript arrays: loops and filtering')).toBe('Beginner JavaScript arrays')
  })
})

describe('scheduleProblems', () => {
  const now = new Date(2026, 9, 7, 12, 0)

  it('needs an opening time', () => {
    expect(scheduleProblems('', '', now)).toEqual({ start: 'Pick when the exam opens' })
  })

  it('needs the opening time to be in the future', () => {
    expect(scheduleProblems('2026-10-07T11:00', '', now)).toEqual({ start: 'Pick an opening time in the future' })
  })

  it('accepts a future opening time with no closing time', () => {
    expect(scheduleProblems('2026-10-08T09:00', '', now)).toEqual({})
  })

  it('needs the closing time after the opening time', () => {
    expect(scheduleProblems('2026-10-08T09:00', '2026-10-08T09:00', now))
      .toEqual({ end: 'The closing time must be after the opening time' })
    expect(scheduleProblems('2026-10-08T09:00', '2026-10-08T10:30', now)).toEqual({})
  })

  it('round-trips with toLocalInput', () => {
    const d = new Date(2026, 9, 8, 9, 5)
    expect(toLocalInput(d)).toBe('2026-10-08T09:05')
    expect(new Date(toLocalInput(d)).getTime()).toBe(d.getTime())
  })
})
