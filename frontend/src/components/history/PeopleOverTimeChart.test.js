import { describe, expect, it } from 'vitest'

import { dayTicks, hourlyPoints, rawPoints } from './PeopleOverTimeChart'

describe('dayTicks', () => {
  it('puts one tick per local midnight for multi-day ranges', () => {
    const from = new Date(2026, 9, 1, 9).getTime()
    const to = new Date(2026, 9, 4, 18).getTime()
    const ticks = dayTicks([from, to]).map((t) => new Date(t))
    expect(ticks.map((d) => d.getDate())).toEqual([2, 3, 4])
    expect(ticks.every((d) => d.getHours() === 0 && d.getMinutes() === 0)).toBe(true)
  })

  it('thins ticks for long ranges and leaves short ranges to the chart', () => {
    const from = new Date(2026, 8, 1).getTime()
    expect(dayTicks([from, from + 60 * 86400_000]).length).toBeLessThanOrEqual(8)
    expect(dayTicks([from, from + 6 * 3600_000])).toBeUndefined()
  })
})

const rec = (iso, count) => ({ timestamp: iso, count, avg_confidence: 0.8, source: 'x', id: 1 })

describe('rawPoints', () => {
  it('breaks the line at long gaps instead of holding the last value', () => {
    const pts = rawPoints([
      rec('2026-10-07T09:00:00Z', 2),
      rec('2026-10-07T09:20:00Z', 3),
      rec('2026-10-07T09:40:00Z', 4),
      rec('2026-10-07T21:00:00Z', 1), // overnight-sized gap
    ])
    expect(pts.map((p) => p.value)).toEqual([2, 3, 4, null, 1])
  })

  it('keeps regular sequences intact', () => {
    const pts = rawPoints([rec('2026-10-07T09:00:00Z', 1), rec('2026-10-07T09:30:00Z', 2)])
    expect(pts.every((p) => p.value != null)).toBe(true)
  })
})

describe('hourlyPoints', () => {
  it('fills hours without data with null', () => {
    const pts = hourlyPoints([
      { hour: '2026-10-07T09:00', detections: 2, avg_people: 1.5, max_people: 2, avg_confidence: 0.7 },
      { hour: '2026-10-07T12:00', detections: 1, avg_people: 4, max_people: 4, avg_confidence: 0.8 },
    ])
    expect(pts.map((p) => p.value)).toEqual([1.5, null, null, 4])
    expect(pts[1].t - pts[0].t).toBe(3600_000)
  })
})
