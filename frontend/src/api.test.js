import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  buildUrl,
  detectBase64,
  detectFile,
  exportCsvUrl,
  getHistory,
  getHourly,
  getStats,
  resetHistory,
} from './api'
import { API_URL } from './config'

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

let fetchMock
beforeEach(() => {
  fetchMock = vi.spyOn(globalThis, 'fetch')
})

/** URL and init of the n-th fetch call. */
const call = (n = 0) => {
  const [url, init] = fetchMock.mock.calls[n]
  return { url: new URL(url), init }
}

// --- URL building -------------------------------------------------------------

describe('buildUrl with a relative API_URL (Docker: nginx proxies /api)', () => {
  it('resolves against the page origin', async () => {
    vi.resetModules()
    vi.doMock('./config', () => ({ API_URL: '/api' }))
    const { buildUrl: build } = await import('./api')
    const url = new URL(build('history', { limit: 5 }))
    expect(url.origin).toBe(window.location.origin)
    expect(url.pathname).toBe('/api/history')
    expect(url.searchParams.get('limit')).toBe('5')
    vi.doUnmock('./config')
    vi.resetModules()
  })
})

describe('buildUrl', () => {
  it('skips empty values and serialises dates and booleans', () => {
    const url = new URL(
      buildUrl('history', {
        start: new Date('2026-10-01T10:00:00Z'),
        end: undefined,
        min_count: null,
        min_confidence: '',
        newest_first: false,
        limit: 0,
      }),
    )
    expect(url.origin + url.pathname).toBe(`${API_URL}/history`)
    expect(Object.fromEntries(url.searchParams)).toEqual({
      start: '2026-10-01T10:00:00.000Z',
      newest_first: 'false',
      limit: '0',
    })
  })
})

// --- endpoints ----------------------------------------------------------------

describe('detect', () => {
  it('uploads a file as multipart with mapped options', async () => {
    fetchMock.mockResolvedValue(json({ count: 2 }))
    const file = new File(['x'], 'photo.jpg', { type: 'image/jpeg' })

    const result = await detectFile(file, { conf: 0.5, enhance: true, returnImage: false, imgSize: 640 })

    expect(result).toEqual({ count: 2 })
    const { url, init } = call()
    expect(url.pathname).toBe('/detect')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      conf: '0.5', enhance: 'true', return_image: 'false', img_size: '640',
    })
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file').name).toBe('photo.jpg')
  })

  it('sends base64 frames as JSON with source and save=false', async () => {
    fetchMock.mockResolvedValue(json({ count: 1, saved: false }))

    await detectBase64('data:image/jpeg;base64,AAA', { source: 'webcam', save: false, imgSize: 640 })

    const { url, init } = call()
    expect(url.pathname).toBe('/detect/base64')
    expect(url.searchParams.get('save')).toBe('false')
    expect(url.searchParams.get('img_size')).toBe('640')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(init.body)).toEqual({ image: 'data:image/jpeg;base64,AAA', source: 'webcam' })
  })
})

describe('history and stats', () => {
  it('maps history filters and paging', async () => {
    fetchMock.mockResolvedValue(json({ total: 0, items: [] }))
    await getHistory({ minConfidence: 0.7, minCount: 1, newestFirst: false, limit: 25, offset: 50 })
    expect(Object.fromEntries(call().url.searchParams)).toEqual({
      min_confidence: '0.7', min_count: '1', newest_first: 'false', limit: '25', offset: '50',
    })
  })

  it('passes the time range to /stats', async () => {
    fetchMock.mockResolvedValue(json({ summary: {}, runtime: {} }))
    await getStats({ start: '2026-10-01T00:00:00Z' })
    expect(call().url.searchParams.get('start')).toBe('2026-10-01T00:00:00Z')
  })

  it('defaults hourly buckets to the local time zone', async () => {
    fetchMock.mockResolvedValue(json({ buckets: [] }))
    await getHourly({ mode: 'hour_of_day' })
    const params = call().url.searchParams
    expect(params.get('mode')).toBe('hour_of_day')
    expect(params.get('tz_offset_minutes')).toBe(String(-new Date().getTimezoneOffset()))
  })

  it('resets with DELETE', async () => {
    fetchMock.mockResolvedValue(json({ deleted: 3 }))
    expect(await resetHistory()).toEqual({ deleted: 3 })
    expect(call().init.method).toBe('DELETE')
  })

  it('builds a CSV export URL with the current filters', () => {
    const url = new URL(exportCsvUrl({ minCount: 2, start: '2026-10-01T00:00:00Z' }, { includeDetections: true }))
    expect(url.pathname).toBe('/history/export.csv')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      start: '2026-10-01T00:00:00Z', min_count: '2', include_detections: 'true',
    })
  })
})

// --- errors -------------------------------------------------------------------

describe('errors', () => {
  const file = new File(['x'], 'a.png', { type: 'image/png' })

  it('uses the backend message and error type', async () => {
    fetchMock.mockResolvedValue(
      json({ detail: 'File is 12.0 MB; limit is 10 MB.', error: 'FileTooLargeError' }, 413),
    )
    const err = await detectFile(file).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(413)
    expect(err.type).toBe('FileTooLargeError')
    expect(err.message).toBe('File is 12.0 MB; limit is 10 MB.')
  })

  it('formats FastAPI validation errors (422)', async () => {
    fetchMock.mockResolvedValue(
      json({
        detail: [{ loc: ['query', 'conf'], msg: 'Input should be less than or equal to 1', type: 'less_than_equal' }],
      }, 422),
    )
    const err = await detectFile(file, { conf: 2 }).catch((e) => e)
    expect(err.type).toBe('ValidationError')
    expect(err.message).toBe('conf: Input should be less than or equal to 1')
  })

  it('falls back to a friendly message for non-JSON errors', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 415 }))
    const err = await detectFile(file).catch((e) => e)
    expect(err.message).toBe('Unsupported file type. Please use a JPEG or PNG image.')
    expect(err.type).toBe('HTTP415')
  })

  it('reports network failures as status 0', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const err = await getHistory().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(0)
    expect(err.type).toBe('NetworkError')
    expect(err.message).toContain('Is the backend running?')
  })

  it('lets aborts through untouched', async () => {
    fetchMock.mockRejectedValue(new DOMException('aborted', 'AbortError'))
    const err = await getHistory().catch((e) => e)
    expect(err).not.toBeInstanceOf(ApiError)
    expect(err.name).toBe('AbortError')
  })

  it('rejects an invalid success body', async () => {
    fetchMock.mockResolvedValue(new Response('not json', { status: 200 }))
    const err = await getStats().catch((e) => e)
    expect(err.type).toBe('InvalidResponse')
  })
})
