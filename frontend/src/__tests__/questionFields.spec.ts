import { describe, it, expect } from 'vitest'

import { parseStatement } from '../utils/statement'
import { composeDescription, decomposeDescription } from '../utils/questionFields'

// The AI's run-together paragraph and the seeded "Input (line N)" layout
const AI_DESCRIPTION =
  'Given an array of integers and a target integer, return the indices of the two numbers such that they add up to the target. '
  + 'Input format: First line contains an integer n (number of elements in the array). Second line contains n space-separated integers (the array). Third line contains the target integer. '
  + 'Output format: Print the indices of the two numbers (0-based) in a single line, separated by a space.'

const SEEDED_DESCRIPTION =
  'Return indices of the two numbers.\nYou may assume one solution.\n\n'
  + 'Input (line 1): array length n\nInput (line 2): space-separated integers\nInput (line 3): target\n'
  + 'Output: two indices separated by space\nConstraints:\n2 <= n <= 1000\n-10^9 <= nums[i] <= 10^9'

describe('decomposeDescription', () => {
  it('splits the AI run-together format into fields', () => {
    expect(decomposeDescription(AI_DESCRIPTION)).toEqual({
      problem: 'Given an array of integers and a target integer, return the indices of the two numbers such that they add up to the target.',
      inputFormat: 'First line contains an integer n (number of elements in the array).\n'
        + 'Second line contains n space-separated integers (the array).\nThird line contains the target integer.',
      outputFormat: 'Print the indices of the two numbers (0-based) in a single line, separated by a space.',
      constraints: '',
      note: '',
    })
  })

  it('splits the seeded "Input (line N)" format into fields', () => {
    expect(decomposeDescription(SEEDED_DESCRIPTION)).toEqual({
      problem: 'Return indices of the two numbers.\nYou may assume one solution.',
      inputFormat: 'Line 1: array length n\nLine 2: space-separated integers\nLine 3: target',
      outputFormat: 'two indices separated by space',
      constraints: '2 <= n <= 1000\n-10^9 <= nums[i] <= 10^9',
      note: '',
    })
  })
})

describe('composeDescription', () => {
  it('writes problem, then a labelled block per non-empty section', () => {
    expect(composeDescription({
      problem: 'Reverse the string.\n\nKeep spaces.',
      inputFormat: 'One line: the string',
      outputFormat: 'The reversed string',
      constraints: '',
      note: '',
    })).toBe('Reverse the string.\n\nKeep spaces.\n\nInput format:\nOne line: the string\n\nOutput format:\nThe reversed string')
  })

  it('writes nothing for empty fields', () => {
    expect(composeDescription({ problem: ' ', inputFormat: '', outputFormat: '', constraints: '', note: '' })).toBe('')
  })

  it('round-trips: compose(decompose(x)) parses to the same statement and sections', () => {
    for (const x of [AI_DESCRIPTION, SEEDED_DESCRIPTION, 'Implement debounce.\n\nIt delays calls.', 'Sum it.\nNote: use 64-bit ints.']) {
      const composed = composeDescription(decomposeDescription(x))
      expect(parseStatement(composed)).toEqual(parseStatement(x))
      // and composing again changes nothing
      expect(composeDescription(decomposeDescription(composed))).toBe(composed)
    }
  })

  it('handles a description with sections but no problem text', () => {
    const composed = composeDescription({ problem: '', inputFormat: 'n', outputFormat: '', constraints: '1 <= n', note: '' })
    expect(parseStatement(composed)).toEqual({
      statement: [],
      sections: [{ heading: 'Input format', items: ['n'] }, { heading: 'Constraints', items: ['1 <= n'] }],
    })
  })
})
