import { describe, expect, it } from 'vitest'

import { confidenceLevel, ms, pct } from './format'
import { guessType, validateImageFile } from './validation'

const file = (name, type, size = 1000) => {
  const f = new File(['x'], name, { type })
  Object.defineProperty(f, 'size', { value: size })
  return f
}

describe('validateImageFile', () => {
  it('accepts JPEG and PNG', () => {
    expect(validateImageFile(file('a.jpg', 'image/jpeg'))).toBeNull()
    expect(validateImageFile(file('a.png', 'image/png'))).toBeNull()
  })

  it('falls back to the extension when the browser gives no type', () => {
    expect(guessType(file('photo.JPEG', ''))).toBe('image/jpeg')
    expect(validateImageFile(file('photo.png', ''))).toBeNull()
  })

  it('rejects other formats with a clear message', () => {
    expect(validateImageFile(file('anim.gif', 'image/gif'))).toMatch(/not supported \(image\/gif\).*JPEG or PNG/)
    expect(validateImageFile(file('notes.txt', ''))).toMatch(/not supported \(txt\)/)
  })

  it('rejects empty and oversized files', () => {
    expect(validateImageFile(file('a.jpg', 'image/jpeg', 0))).toMatch(/is empty/)
    expect(validateImageFile(file('big.jpg', 'image/jpeg', 12 * 1024 * 1024))).toMatch(/12\.0 MB; the limit is 10 MB/)
  })

  it('handles a missing file', () => {
    expect(validateImageFile(null)).toBe('No file selected.')
  })
})

describe('format', () => {
  it('formats percentages and durations', () => {
    expect(pct(0.873)).toBe('87%')
    expect(pct(null)).toBe('–')
    expect(ms(12.4)).toBe('12 ms')
    expect(ms(1234)).toBe('1.23 s')
  })

  it('bands confidence', () => {
    expect(confidenceLevel(0.9)).toBe('high')
    expect(confidenceLevel(0.6)).toBe('medium')
    expect(confidenceLevel(0.3)).toBe('low')
  })
})
