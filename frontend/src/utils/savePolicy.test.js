import { describe, expect, it } from 'vitest'

import { createSavePolicy } from './savePolicy'

/** Simulate frames: returns which frame indexes were saved. */
function run(policy, counts, { stepMs = 100 } = {}) {
  const saved = []
  counts.forEach((count, i) => {
    const now = i * stepMs
    if (policy.shouldSave(now)) {
      saved.push(i)
      policy.markSaved(now, count)
    }
    policy.observe(count)
  })
  return saved
}

describe('createSavePolicy', () => {
  it('saves the first frame, then only stable count changes', () => {
    const p = createSavePolicy({ onChange: true, stableFrames: 3 })
    //            0  1  2  3  4  5  6  7  8  9
    const counts = [2, 2, 3, 3, 3, 3, 3, 3, 3, 3]
    // count becomes 3 at frame 2; stable for 3 frames after frame 4 -> saved at frame 5
    expect(run(p, counts)).toEqual([0, 5])
  })

  it('ignores one-frame flicker', () => {
    const p = createSavePolicy({ onChange: true, stableFrames: 3 })
    expect(run(p, [2, 3, 2, 3, 2, 2, 3, 2, 2])).toEqual([0])
  })

  it('adds periodic snapshots when an interval is set', () => {
    const p = createSavePolicy({ onChange: true, intervalMs: 1000 })
    const counts = Array(25).fill(1) // 2.5 s of a constant count at 10 fps
    expect(run(p, counts)).toEqual([0, 10, 20])
  })

  it('can save on a timer only', () => {
    const p = createSavePolicy({ onChange: false, intervalMs: 500 })
    expect(run(p, [1, 1, 5, 5, 5, 5, 5, 1, 1, 1, 1])).toEqual([0, 5, 10])
  })

  it('never saves when disabled', () => {
    const p = createSavePolicy({ onChange: false, intervalMs: null })
    expect(run(p, [1, 2, 3, 4, 5, 5, 5, 5])).toEqual([])
  })
})
