import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, detectFile } from '../api'
import DetectionPage from './DetectionPage'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal()),
  detectFile: vi.fn(),
}))

const RESULT = {
  record_id: 7,
  saved: true,
  timestamp: '2026-10-07T12:00:00Z',
  img_size: 1280,
  count: 2,
  avg_confidence: 0.75,
  detections: [
    { bbox: [10, 20, 110, 220], confidence: 0.9, center: [60, 120], width: 100, height: 200 },
    { bbox: [200, 30, 260, 150], confidence: 0.6, center: [230, 90], width: 60, height: 120 },
  ],
  image_width: 640,
  image_height: 480,
  conf_threshold: 0.4,
  contrast_enhanced: false,
  timings: { decode_ms: 3, preprocess_ms: 1, inference_ms: 120.4, detect_ms: 130, overlay_ms: 0, total_ms: 140.2 },
  annotated_image: null,
}

const jpeg = (name = 'photo.jpg') => new File(['fake-bytes'], name, { type: 'image/jpeg' })
const user = () => userEvent.setup({ applyAccept: false })
const fileInput = () => screen.getByLabelText('Choose an image')

beforeEach(() => {
  detectFile.mockReset()
})

describe('DetectionPage (upload)', () => {
  it('uploads an image and shows count, boxes and per-person rows', async () => {
    detectFile.mockResolvedValue(RESULT)
    render(<DetectionPage />)

    await user().upload(fileInput(), jpeg())

    expect(await screen.findByTestId('people-count')).toHaveTextContent('2')
    expect(screen.getByText('75%')).toBeInTheDocument() // average confidence
    expect(screen.getByText('120 ms')).toBeInTheDocument() // inference time
    expect(screen.getAllByTestId('detection-box')).toHaveLength(2)
    expect(screen.getByRole('img', { name: '2 people detected' })).toHaveAttribute('viewBox', '0 0 640 480')
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(3) // header + 2
    expect(screen.getByText(/saved as #7/)).toBeInTheDocument()

    const [sentFile, options] = detectFile.mock.calls[0]
    expect(sentFile.name).toBe('photo.jpg')
    expect(options).toEqual({ conf: 0.4, enhance: false, returnImage: false })
  })

  it('rejects unsupported files in the browser without calling the API', async () => {
    render(<DetectionPage />)
    await user().upload(fileInput(), new File(['GIF89a'], 'anim.gif', { type: 'image/gif' }))

    expect(screen.getByRole('alert')).toHaveTextContent('"anim.gif" is not supported (image/gif)')
    expect(detectFile).not.toHaveBeenCalled()
  })

  it('shows backend errors and lets the user dismiss them', async () => {
    detectFile.mockRejectedValue(
      new ApiError('File content is not a supported image.', { status: 415, type: 'UnsupportedFormatError' }),
    )
    render(<DetectionPage />)
    await user().upload(fileInput(), jpeg('renamed.jpg'))

    expect(await screen.findByRole('alert')).toHaveTextContent('File content is not a supported image.')
    await user().click(screen.getByRole('button', { name: 'Dismiss error' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('highlights the matching box when hovering a table row', async () => {
    detectFile.mockResolvedValue(RESULT)
    render(<DetectionPage />)
    await user().upload(fileInput(), jpeg())
    await screen.findByTestId('people-count')

    const secondRow = within(screen.getByRole('table')).getAllByRole('row')[2]
    await user().hover(secondRow)

    const boxes = screen.getAllByTestId('detection-box')
    expect(boxes[1]).toHaveClass('active')
    expect(boxes[0]).toHaveClass('dimmed')
    expect(secondRow).toHaveClass('active')
  })

  it('re-runs detection only when asked after settings change', async () => {
    detectFile.mockResolvedValue(RESULT)
    render(<DetectionPage />)
    await user().upload(fileInput(), jpeg())
    await screen.findByTestId('people-count')

    expect(screen.queryByRole('button', { name: 'Re-run detection' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('slider'), { target: { value: '0.6' } })
    await user().click(screen.getByRole('checkbox', { name: /contrast boost/i }))
    expect(detectFile).toHaveBeenCalledTimes(1) // no automatic re-run

    await user().click(screen.getByRole('button', { name: 'Re-run detection' }))
    await waitFor(() => expect(detectFile).toHaveBeenCalledTimes(2))
    expect(detectFile.mock.calls[1][1]).toEqual({ conf: 0.6, enhance: true, returnImage: false })
  })

  it('keeps labels inside the image and draws them above all boxes', async () => {
    detectFile.mockResolvedValue({
      ...RESULT,
      count: 1,
      detections: [{ bbox: [630, 0, 640, 30], confidence: 0.8, center: [635, 15], width: 10, height: 30 }],
    })
    const { container } = render(<DetectionPage />)
    await user().upload(fileInput(), jpeg())
    await screen.findByTestId('people-count')

    const svg = container.querySelector('svg.overlay-svg')
    const labelBg = svg.querySelector('.box-label-bg')
    const x = Number(labelBg.getAttribute('x'))
    const w = Number(labelBg.getAttribute('width'))
    expect(x + w).toBeLessThanOrEqual(640) // pushed left to stay inside
    expect(Number(labelBg.getAttribute('y'))).toBe(0) // inside the box at the top edge
    // label group comes after the box group in the DOM, so it paints on top
    const groups = [...svg.querySelectorAll(':scope > g')]
    expect(groups.indexOf(labelBg.parentNode)).toBeGreaterThan(groups.indexOf(screen.getByTestId('detection-box')))
  })

  it('shows a message instead of a broken preview', async () => {
    detectFile.mockRejectedValue(new ApiError('File content is not a supported image.', { status: 415 }))
    render(<DetectionPage />)
    await user().upload(fileInput(), jpeg('fake.jpg'))
    fireEvent.error(screen.getByRole('img', { name: 'fake.jpg' }))
    expect(await screen.findByText('Preview not available for this file.')).toBeInTheDocument()
  })

  it('loads a sample image from the gallery', async () => {
    detectFile.mockResolvedValue(RESULT)
    // Minimal Response stand-in: jsdom's Blob can't be wrapped in Node's Response
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(['jpeg-bytes'], { type: 'image/jpeg' }),
    })
    render(<DetectionPage />)

    await user().click(screen.getByRole('button', { name: /Street crossing/ }))

    await waitFor(() => expect(detectFile).toHaveBeenCalledTimes(1))
    expect(fetch).toHaveBeenCalledWith('/samples/07_street_crossing.jpg')
    expect(detectFile.mock.calls[0][0].name).toBe('07_street_crossing.jpg')
  })

  it('cancels the previous request when a new image is chosen', async () => {
    detectFile.mockImplementationOnce(() => new Promise(() => {})) // never resolves
    detectFile.mockResolvedValueOnce(RESULT)
    render(<DetectionPage />)

    await user().upload(fileInput(), jpeg('first.jpg'))
    const firstSignal = detectFile.mock.calls[0][2].signal
    await user().upload(fileInput(), jpeg('second.jpg'))

    expect(firstSignal.aborted).toBe(true)
    expect(await screen.findByTestId('people-count')).toHaveTextContent('2')
  })
})
