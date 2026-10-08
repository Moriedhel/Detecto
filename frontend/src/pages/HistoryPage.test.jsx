import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getHistory, getHourly, getStats, resetHistory } from '../api'
import { fromLocalInput, presetRange, toLocalInput } from '../utils/timeRange'
import HistoryPage from './HistoryPage'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal()),
  getHistory: vi.fn(),
  getStats: vi.fn(),
  getHourly: vi.fn(),
  resetHistory: vi.fn(),
}))

const record = (id, count, extra = {}) => ({
  id,
  timestamp: `2026-10-07T1${id % 10}:00:00Z`,
  count,
  avg_confidence: count ? 0.75 : null,
  inference_ms: 210,
  total_ms: 240,
  source: `frame${id}.jpg`,
  image_width: 640,
  image_height: 480,
  conf_threshold: 0.4,
  contrast_enhanced: false,
  detections: [],
  ...extra,
})

const SUMMARY = {
  total_detections: 3, frames_with_people: 2, total_people: 7, avg_people: 2.33, max_people: 4,
  avg_confidence: 0.7612, avg_inference_ms: 210, p50_inference_ms: 205, p95_inference_ms: 260,
  max_inference_ms: 260, avg_total_ms: 240, first_timestamp: null, last_timestamp: null,
}

function mockApi({ total = 3, items = [record(3, 4), record(2, 3), record(1, 0)], summary = SUMMARY } = {}) {
  getHistory.mockResolvedValue({ total, items })
  getStats.mockResolvedValue({ summary: { ...summary, total_detections: total }, runtime: {} })
  getHourly.mockResolvedValue({ mode: 'hour_of_day', tz_offset_minutes: 0, buckets: [
    { hour: '09', detections: 2, avg_people: 1.5, max_people: 3, avg_confidence: 0.7 },
    { hour: '14', detections: 1, avg_people: 4, max_people: 4, avg_confidence: 0.8 },
  ] })
}

const renderPage = () =>
  render(
    <MemoryRouter>
      <HistoryPage />
    </MemoryRouter>,
  )

beforeEach(() => {
  vi.clearAllMocks()
})

describe('HistoryPage', () => {
  it('shows KPIs, the hourly table view and the detections table', async () => {
    mockApi()
    renderPage()

    expect(await screen.findByText('People counted')).toBeInTheDocument()
    expect(screen.getByText('76%')).toBeInTheDocument() // avg confidence
    expect(screen.getByText('p95 260 ms')).toBeInTheDocument()

    const detections = screen.getByRole('heading', { name: 'Detections' }).closest('section')
    await waitFor(() => expect(within(detections).getAllByRole('row')).toHaveLength(4)) // header + 3
    expect(within(detections).getByText('frame3.jpg')).toBeInTheDocument()

    // hourly table view: only hours with data, every value reachable without hovering
    const hourly = screen.getByRole('heading', { name: /by hour of day/ }).closest('section')
    const rows = within(hourly).getAllByRole('row')
    expect(rows).toHaveLength(3)
    expect(rows[1]).toHaveTextContent('09:00')
    expect(rows[2]).toHaveTextContent('14:00')
  })

  it('applies the same filters to stats, charts and table', async () => {
    mockApi()
    renderPage()
    await screen.findByText('People counted')

    await userEvent.selectOptions(screen.getByLabelText('Min. confidence'), '0.7')
    fireEvent.change(screen.getByLabelText('Min. people'), { target: { value: '2' } })

    await waitFor(() => {
      const last = (fn) => fn.mock.calls.at(-1)[0]
      expect(last(getStats)).toMatchObject({ minConfidence: 0.7, minCount: 2 })
      const hourlyCalls = getHourly.mock.calls.slice(-2).map(([opts]) => opts)
      expect(hourlyCalls).toEqual(expect.arrayContaining([
        expect.objectContaining({ minConfidence: 0.7, minCount: 2, mode: 'hour_of_day' }),
        expect.objectContaining({ minConfidence: 0.7, minCount: 2, mode: 'timeline' }),
      ]))
      expect(last(getHistory)).toMatchObject({ minConfidence: 0.7, minCount: 2 })
    })
  })

  it('date presets set a start time; custom shows date inputs', async () => {
    mockApi()
    renderPage()
    await screen.findByText('People counted')

    await userEvent.click(screen.getByRole('radio', { name: 'Last hour' }))
    await waitFor(() => expect(getStats.mock.calls.at(-1)[0].start).toBeTruthy())
    const start = new Date(getStats.mock.calls.at(-1)[0].start).getTime()
    expect(Date.now() - start).toBeGreaterThan(3590_000)
    expect(Date.now() - start).toBeLessThan(3700_000)

    await userEvent.click(screen.getByRole('radio', { name: 'Custom' }))
    expect(screen.getByLabelText('From')).toBeInTheDocument()
    expect(screen.getByLabelText('To')).toBeInTheDocument()
  })

  it('pages through the table', async () => {
    mockApi({ total: 60, items: Array.from({ length: 25 }, (_, i) => record(i + 1, 1)) })
    renderPage()
    expect(await screen.findByText('1–25 of 60')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() =>
      expect(getHistory).toHaveBeenCalledWith(expect.objectContaining({ limit: 25, offset: 25 }), expect.anything()),
    )
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled()
  })

  it('exports CSV with the current filters', async () => {
    mockApi()
    renderPage()
    await screen.findByText('People counted')
    await userEvent.selectOptions(screen.getByLabelText('Min. confidence'), '0.8')

    const link = screen.getByRole('link', { name: 'Export CSV' })
    const url = new URL(link.getAttribute('href'))
    expect(url.pathname).toBe('/history/export.csv')
    expect(url.searchParams.get('min_confidence')).toBe('0.8')
  })

  it('clears history only after confirmation', async () => {
    mockApi()
    resetHistory.mockResolvedValue({ deleted: 3 })
    renderPage()
    await screen.findByText('People counted')

    await userEvent.click(screen.getByRole('button', { name: 'Clear history' }))
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveTextContent('Delete all 3 stored detections?')

    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(resetHistory).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Clear history' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete all' }))
    expect(resetHistory).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('Deleted 3 detections.')).toBeInTheDocument()
  })

  it('shows an empty state when nothing has been stored yet', async () => {
    mockApi({ total: 0, items: [] })
    renderPage()
    expect(await screen.findByText(/No detections stored yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Detection page' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('button', { name: 'Clear history' })).toBeDisabled()
  })

  it('shows API errors', async () => {
    getHistory.mockRejectedValue(new Error('Cannot reach the API'))
    getStats.mockRejectedValue(new Error('Cannot reach the API'))
    getHourly.mockRejectedValue(new Error('Cannot reach the API'))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the API')
  })
})

describe('timeRange helpers', () => {
  it('round-trips datetime-local values', () => {
    const iso = fromLocalInput('2026-10-07T14:30')
    expect(toLocalInput(iso)).toBe('2026-10-07T14:30')
    expect(fromLocalInput('')).toBeNull()
  })

  it('resolves "today" to local midnight', () => {
    const now = new Date(2026, 9, 7, 15, 45)
    const start = new Date(presetRange('today', now).start)
    expect([start.getHours(), start.getMinutes(), start.getDate()]).toEqual([0, 0, 7])
    expect(presetRange('all')).toEqual({ start: null, end: null })
  })
})
