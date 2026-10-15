import { describe, it, expect } from 'vitest'

import { findMatchedLines } from '../utils/codeCompare'

const A = `const input = require('fs').readFileSync(0, 'utf8');
const str = input.trim();

function isPalindrome(str) {
  let left = 0;
  let right = str.length - 1;
  while (left < right) {
    if (str[left] !== str[right]) {
      return false;
    }
    left++;
  }
  return true;
}`

// same program, variables renamed and a comment added: a copy
const B = A.replace(/\bleft\b/g, 'leftpointer').replace(/\bright\b/g, 'rightpointer')
    .replace('return true;', 'return true; // done')

describe('findMatchedLines', () => {
  it('matches lines that differ only in variable names or comments', () => {
    const { matched1, matched2 } = findMatchedLines(A.split('\n'), B.split('\n'))
    const lines = A.split('\n')
    for (const i of [4, 5, 6, 7, 10, 12]) expect(matched1.has(i), lines[i]).toBe(true)
    expect(matched2.has(4)).toBe(true)
  })

  it('does not match a line whose structure differs', () => {
    const { matched1 } = findMatchedLines(['let a = b + 1;'], ['let a = b - 1;'])
    expect(matched1.size).toBe(0)
  })

  it('keeps property and method names, so different calls do not match', () => {
    const { matched1 } = findMatchedLines(['x.push(y);'], ['x.pop(y);'])
    expect(matched1.size).toBe(0)
  })

  it('ignores trivial lines like a lone brace', () => {
    const { matched1 } = findMatchedLines(['}', '  });'], ['}', '  });'])
    expect(matched1.size).toBe(0)
  })
})
