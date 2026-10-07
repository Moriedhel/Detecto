import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { detectBase64 } from '../api'
import DetectionPage from '../pages/DetectionPage'
import { captureFrame } from '../utils/capture'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal()),
  detectBase64: vi.fn(),
}))
// jsdom has no canvas/video pixels: return a fixed fake frame
vi.mock('../utils/capture', () => ({
  captureFrame: vi.fn(() => ({ dataUrl: 'data:image/jpeg;base64,AAAA', width: 640, height: 360 })),
}))

const frameResult = (count, extra = {}) => ({
  record_id: null,
  saved: false,
  timestamp: '2026-10-07T12:00:00Z',
  img_size: 640,
  count,
  avg_confidence: count ? 0.8 : null,
  detections: Array.from({ length: count }, (_, i) => ({
    bbox: [10 + i * 50, 10, 50 + i * 50, 200], confidence: 0.8, center: [30 + i * 50, 105], width: 40, height: 190,
  })),
  image_width: 640,
  image_height: 360,
  conf_threshold: 0.4,
  contrast_enhanced: false,
  timings: { decode_ms: 1, preprocess_ms: 0, inference_ms: 60, detect_ms: 65, overlay_ms: 0, total_ms: 70 },
  annotated_image: null,
  ...extra,
})

let track
function mockCamera({ fail } = {}) {
  track = { stop: vi.fn(), getSettings: () => ({ deviceId: 'cam-1' }), onended: null }
  const stream = { getTracks: () => [track], getVideoTracks: () => [track] }
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: fail ? vi.fn().mockRejectedValue(fail) : vi.fn().mockResolvedValue(stream),
      enumerateDevices: vi.fn().mockResolvedValue([{ kind: 'videoinput', deviceId: 'cam-1', label: 'Front camera' }]),
    },
  })
}

const openWebcam = async (user) => {
  render(<DetectionPage />)
  await user.click(screen.getByRole('tab', { name: 'Webcam' }))
}

beforeEach(() => {
  detectBase64.mockReset()
  captureFrame.mockClear()
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
})

afterEach(() => {
  delete navigator.mediaDevices
})

describe('WebcamMode', () => {
  it('starts the camera and runs live detection at 640 px', async () => {
    mockCamera()
    detectBase64.mockImplementation(async (_img, opts) => frameResult(2, { saved: opts.save, record_id: opts.save ? 1 : null }))
    const user = userEvent.setup()
    await openWebcam(user)

    await user.click(screen.getByRole('button', { name: 'Start camera' }))

    expect(await screen.findByTestId('live-count')).toHaveTextContent('2')
    expect(screen.getAllByTestId('detection-box')).toHaveLength(2)
    expect(screen.getByRole('img', { name: '2 people detected' })).toHaveAttribute('viewBox', '0 0 640 360')

    const [image, options] = detectBase64.mock.calls[0]
    expect(image).toBe('data:image/jpeg;base64,AAAA')
    expect(options).toMatchObject({ source: 'webcam', imgSize: 640, returnImage: false, save: true, conf: 0.4 })
    // later frames with the same count are not saved
    await waitFor(() => expect(detectBase64.mock.calls.length).toBeGreaterThan(2))
    expect(detectBase64.mock.calls.slice(1).every(([, o]) => o.save === false)).toBe(true)
    expect(screen.getByTestId('live-saved')).toHaveTextContent('1')
  })

  it('stops the camera and the loop', async () => {
    mockCamera()
    detectBase64.mockResolvedValue(frameResult(1))
    const user = userEvent.setup()
    await openWebcam(user)
    await user.click(screen.getByRole('button', { name: 'Start camera' }))
    await screen.findByTestId('live-count')

    await user.click(screen.getByRole('button', { name: 'Stop camera' }))

    expect(track.stop).toHaveBeenCalled()
    expect(screen.getByText('Camera is off.')).toBeInTheDocument()
    const calls = detectBase64.mock.calls.length
    await new Promise((r) => setTimeout(r, 250))
    expect(detectBase64.mock.calls.length).toBe(calls) // no more frames sent
  })

  it('releases the camera when switching back to Upload', async () => {
    mockCamera()
    detectBase64.mockResolvedValue(frameResult(1))
    const user = userEvent.setup()
    await openWebcam(user)
    await user.click(screen.getByRole('button', { name: 'Start camera' }))
    await screen.findByTestId('live-count')

    await user.click(screen.getByRole('tab', { name: 'Upload' }))
    expect(track.stop).toHaveBeenCalled()
  })

  it('explains a denied camera permission', async () => {
    mockCamera({ fail: new DOMException('denied', 'NotAllowedError') })
    const user = userEvent.setup()
    await openWebcam(user)
    await user.click(screen.getByRole('button', { name: 'Start camera' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Camera access was denied')
    expect(detectBase64).not.toHaveBeenCalled()
  })

  it('explains a missing camera', async () => {
    mockCamera({ fail: new DOMException('none', 'NotFoundError') })
    const user = userEvent.setup()
    await openWebcam(user)
    await user.click(screen.getByRole('button', { name: 'Start camera' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No camera was found')
  })

  it('stops live detection with a message when the API fails', async () => {
    mockCamera()
    detectBase64.mockResolvedValueOnce(frameResult(1)).mockRejectedValue(new Error('Cannot reach the API'))
    const user = userEvent.setup()
    await openWebcam(user)
    await user.click(screen.getByRole('button', { name: 'Start camera' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Live detection stopped: Cannot reach the API')
    expect(track.stop).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Start camera' })).toBeInTheDocument()
  })
})
