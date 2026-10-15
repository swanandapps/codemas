import { describe, it, expect } from 'vitest'

import { parseStatement } from '../utils/statement'

describe('parseStatement', () => {
  it('splits a generated one-paragraph description into headed sections', () => {
    const s = parseStatement(
      'Given an array of integers and a target integer, return the indices of the two numbers such that they add up to the target. '
      + 'Input format: First line contains an integer n (number of elements in the array). Second line contains n space-separated integers (the array). Third line contains the target integer. '
      + 'Output format: Print the indices of the two numbers (0-based) in a single line, separated by a space.',
    )
    expect(s.statement).toEqual([
      'Given an array of integers and a target integer, return the indices of the two numbers such that they add up to the target.',
    ])
    expect(s.sections).toEqual([
      {
        heading: 'Input format',
        items: [
          'First line contains an integer n (number of elements in the array).',
          'Second line contains n space-separated integers (the array).',
          'Third line contains the target integer.',
        ],
      },
      { heading: 'Output format', items: ['Print the indices of the two numbers (0-based) in a single line, separated by a space.'] },
    ])
  })

  it('reads labelled lines and merges seeded "Input (line N)" lines into one section', () => {
    const s = parseStatement(
      'Return indices of the two numbers.\nYou may assume one solution.\n\n'
      + 'Input (line 1): array length n\nInput (line 2): space-separated integers\nInput (line 3): target\n'
      + 'Output: two indices separated by space\nConstraints:\n2 <= n <= 1000\n-10^9 <= nums[i] <= 10^9',
    )
    expect(s.statement).toEqual(['Return indices of the two numbers.\nYou may assume one solution.'])
    expect(s.sections).toEqual([
      { heading: 'Input format', items: ['Line 1: array length n', 'Line 2: space-separated integers', 'Line 3: target'] },
      { heading: 'Output format', items: ['two indices separated by space'] },
      { heading: 'Constraints', items: ['2 <= n <= 1000', '-10^9 <= nums[i] <= 10^9'] },
    ])
  })

  it('keeps an unlabelled description as the problem statement', () => {
    const s = parseStatement('Implement debounce.\n\nIt delays calls.')
    expect(s.statement).toEqual(['Implement debounce.', 'It delays calls.'])
    expect(s.sections).toEqual([])
  })
})
