// @vitest-environment node
// Integration test against a REAL running backend. Skipped unless enabled:
//   PowerShell:  $env:API_INTEGRATION=1; npm test
// Uses save=false for detections and does not reset history.
import { readFile } from 'node:fs/promises'
import { describe, expect, it } from 'vitest'

import { ApiError, detectBase64, detectFile, exportCsvUrl, getHealth, getHistory, getStats } from './api'

const enabled = process.env.API_INTEGRATION === '1'
const sample = new URL('../public/samples/03_living_room_gaming.jpg', import.meta.url)

describe.skipIf(!enabled)('API integration (live backend)', () => {
  it('reports health', async () => {
    const health = await getHealth()
    expect(health.status).toBe('ok')
    expect(health.model_loaded).toBe(true)
  })

  it('detects people in an uploaded sample without saving', async () => {
    const bytes = await readFile(sample)
    const file = new File([bytes], '03_living_room_gaming.jpg', { type: 'image/jpeg' })
    const res = await detectFile(file, { save: false, returnImage: false })
    expect(res.count).toBe(3)
    expect(res.saved).toBe(false)
    expect(res.detections[0].bbox).toHaveLength(4)
  })

  it('detects from a base64 data URL at 640 px', async () => {
    const b64 = (await readFile(sample)).toString('base64')
    const res = await detectBase64(`data:image/jpeg;base64,${b64}`, { save: false, imgSize: 640, returnImage: false })
    expect(res.img_size).toBe(640)
    expect(res.count).toBeGreaterThan(0)
  })

  it('surfaces backend errors as ApiError', async () => {
    const fake = new File(['not an image'], 'fake.png', { type: 'image/png' })
    const err = await detectFile(fake, { save: false }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(415)
    expect(err.type).toBe('UnsupportedFormatError')
  })

  it('reads history and stats, and serves the CSV export', async () => {
    const page = await getHistory({ limit: 5 })
    expect(page).toHaveProperty('total')
    const stats = await getStats()
    expect(stats.runtime.model).toBeTruthy()
    const csv = await fetch(exportCsvUrl({ minCount: 1 }))
    expect(csv.headers.get('content-type')).toContain('text/csv')
  })
})
