// Client for the Detecto FastAPI backend.
//
// Every function returns parsed JSON or throws an ApiError whose `message` is
// ready to show to users. Options use camelCase here and are mapped to the
// backend's snake_case query parameters.
import { API_URL } from './config'

/** Error raised for any failed API call (HTTP error, network failure, bad response). */
export class ApiError extends Error {
  /**
   * @param {string} message  human-readable message for the UI
   * @param {object} info
   * @param {number} info.status  HTTP status (0 = network failure)
   * @param {string} info.type    backend error class (e.g. "UnsupportedFormatError") or a generic type
   * @param {*}      [info.details] raw error body, for debugging
   */
  constructor(message, { status, type, details } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.type = type
    this.details = details
  }
}

const FALLBACK_MESSAGES = {
  400: 'The request was invalid.',
  404: 'Not found.',
  413: 'The file is too large.',
  415: 'Unsupported file type. Please use a JPEG or PNG image.',
  422: 'Some of the values sent were invalid.',
  500: 'The server hit an unexpected error.',
}

// --- helpers ----------------------------------------------------------------

/** Build a full URL, skipping null/undefined/'' params and serialising dates and booleans. */
export function buildUrl(path, params = {}) {
  const url = new URL(path, API_URL + '/')
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    url.searchParams.set(key, value instanceof Date ? value.toISOString() : String(value))
  }
  return url.toString()
}

/** Turn FastAPI's 422 `detail` list into "field: message" lines. */
function formatValidationErrors(detail) {
  return detail
    .map((e) => {
      const field = (e.loc || []).filter((p) => p !== 'query' && p !== 'body').join('.')
      return field ? `${field}: ${e.msg}` : e.msg
    })
    .join('; ')
}

async function toApiError(res) {
  let body = null
  try {
    body = await res.json()
  } catch {
    // non-JSON error body (e.g. proxy or crash page)
  }

  let message = FALLBACK_MESSAGES[res.status] || `Request failed (HTTP ${res.status}).`
  if (typeof body?.detail === 'string') message = body.detail
  else if (Array.isArray(body?.detail)) message = formatValidationErrors(body.detail)

  const type = body?.error || (res.status === 422 ? 'ValidationError' : `HTTP${res.status}`)
  return new ApiError(message, { status: res.status, type, details: body })
}

/** Core fetch wrapper used by every endpoint function. */
async function request(path, { method = 'GET', params, body, signal } = {}) {
  const init = { method, signal }
  if (body instanceof FormData) {
    init.body = body // browser sets the multipart boundary
  } else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { 'Content-Type': 'application/json' }
  }

  let res
  try {
    res = await fetch(buildUrl(path, params), init)
  } catch (err) {
    if (err.name === 'AbortError') throw err // caller cancelled: not an error to show
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is the backend running?`, {
      status: 0,
      type: 'NetworkError',
      details: err,
    })
  }

  if (!res.ok) throw await toApiError(res)

  try {
    return await res.json()
  } catch {
    throw new ApiError('The server sent an invalid response.', { status: res.status, type: 'InvalidResponse' })
  }
}

// Shared /detect query options
function detectParams({ conf, enhance, returnImage, imgSize, save } = {}) {
  return { conf, enhance, return_image: returnImage, img_size: imgSize, save }
}

// Shared /history and export filters
function historyParams({ start, end, minConfidence, minCount, newestFirst } = {}) {
  return { start, end, min_confidence: minConfidence, min_count: minCount, newest_first: newestFirst }
}

// --- endpoints --------------------------------------------------------------

/** GET /health: { status, version, model, device, model_loaded } */
export function getHealth({ signal } = {}) {
  return request('health', { signal })
}

/**
 * POST /detect with an uploaded File/Blob.
 * @param {File|Blob} file
 * @param {{conf?: number, enhance?: boolean, returnImage?: boolean, imgSize?: number, save?: boolean}} [options]
 */
export function detectFile(file, options = {}, { signal } = {}) {
  const form = new FormData()
  form.append('file', file, file.name || 'upload.jpg')
  return request('detect', { method: 'POST', params: detectParams(options), body: form, signal })
}

/**
 * POST /detect/base64 with a base64 string or data URL (e.g. a webcam frame).
 * @param {string} image
 * @param {{source?: string} & Parameters<typeof detectParams>[0]} [options]
 */
export function detectBase64(image, { source, ...options } = {}, { signal } = {}) {
  return request('detect/base64', {
    method: 'POST',
    params: detectParams(options),
    body: { image, source },
    signal,
  })
}

/** GET /history: { total, items }. Dates may be Date objects or ISO strings. */
export function getHistory({ limit, offset, ...filters } = {}, { signal } = {}) {
  return request('history', { params: { ...historyParams(filters), limit, offset }, signal })
}

/** GET /history/{id} */
export function getHistoryItem(id, { signal } = {}) {
  return request(`history/${encodeURIComponent(id)}`, { signal })
}

/** GET /stats: { summary, runtime } */
export function getStats({ start, end } = {}, { signal } = {}) {
  return request('stats', { params: { start, end }, signal })
}

/**
 * GET /stats/hourly. Buckets default to the browser's local time zone.
 * @param {{mode?: 'timeline'|'hour_of_day', tzOffsetMinutes?: number, start?, end?}} [options]
 */
export function getHourly(
  { mode = 'timeline', tzOffsetMinutes = -new Date().getTimezoneOffset(), start, end } = {},
  { signal } = {},
) {
  return request('stats/hourly', {
    params: { mode, tz_offset_minutes: tzOffsetMinutes, start, end },
    signal,
  })
}

/** DELETE /reset: { deleted } */
export function resetHistory({ signal } = {}) {
  return request('reset', { method: 'DELETE', signal })
}

/** URL for downloading history as CSV with the given filters (use as an <a href>). */
export function exportCsvUrl(filters = {}, { includeDetections } = {}) {
  return buildUrl('history/export.csv', {
    ...historyParams(filters),
    include_detections: includeDetections,
  })
}
