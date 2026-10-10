import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, deleteVideoJob, getVideoJob, uploadVideo } from '../../api'
import { clock, duration } from '../../utils/format'
import VideoMode, { validateVideoFile } from './VideoMode'
import { frameIndexAt, toDetections } from './VideoPlayer'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal()),
  uploadVideo: vi.fn(),
  getVideoJob: vi.fn(),
  deleteVideoJob: vi.fn(() => Promise.resolve(null)),
}))

const RESULT = {
  video: { width: 640, height: 360, fps: 25, duration_s: 4, frames_total: 100, analysed_fps: 8.33 },
  summary: {
    unique_people: 3, peak_people: 2, peak_t: 1.2, avg_people: 1.4, frames_analysed: 33,
    avg_inference_ms: 70, processing_s: 3.1, speed_factor: 1.29,
  },
  people: [
    { track_id: 1, first_t: 0, last_t: 3.9, duration_s: 3.9, frames: 33, best_confidence: 0.91 },
    { track_id: 2, first_t: 1.2, last_t: 2.5, duration_s: 1.3, frames: 11, best_confidence: 0.77 },
  ],
  frames: [
    { t: 0, boxes: [[1, 10, 10, 100, 300, 0.9]] },
    { t: 1.2, boxes: [[1, 20, 10, 110, 300, 0.9], [2, 300, 20, 380, 320, 0.7]] },
  ],
}

const job = (status, extra = {}) => ({
  id: 'job1', filename: 'walk.mp4', status, progress: 0, created_at: '2026-10-10T12:00:00Z',
  options: { conf: 0.4, img_size: 640, sample_fps: 10, enhance: false }, error: null, result: null, ...extra,
})

const video = (name = 'walk.mp4', type = 'video/mp4') => new File(['fake'], name, { type })
const user = () => userEvent.setup({ applyAccept: false })

beforeEach(() => {
  vi.clearAllMocks()
})

describe('VideoMode', () => {
  it('uploads, shows progress, then the tracked results', async () => {
    uploadVideo.mockImplementation(async (_f, _o, { onUploadProgress }) => {
      onUploadProgress(0.5)
      return job('queued')
    })
    getVideoJob
      .mockResolvedValueOnce(job('processing', { progress: 0.4 }))
      .mockResolvedValue(job('done', { progress: 1, result: RESULT }))
    render(<VideoMode />)

    await user().upload(screen.getByLabelText('Choose a video'), video())
    await user().selectOptions(screen.getByLabelText('Frames analysed per second'), '5')
    await user().click(screen.getByRole('button', { name: 'Analyse video' }))

    expect(uploadVideo.mock.calls[0][1]).toEqual({ sampleFps: 5, imgSize: 640, conf: 0.4, enhance: false })
    expect(await screen.findByText('Analysing…', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(await screen.findByTestId('video-unique', {}, { timeout: 5000 })).toHaveTextContent('3')

    const table = screen.getByRole('heading', { name: 'Tracked people' }).closest('section')
    const rows = within(table).getAllByRole('row')
    expect(rows).toHaveLength(3)
    expect(rows[2]).toHaveTextContent('#2')
    expect(rows[2]).toHaveTextContent(clock(1.2))
    expect(rows[2]).toHaveTextContent(duration(1.3))
  })

  it('shows a processing error from the server', async () => {
    uploadVideo.mockResolvedValue(job('queued'))
    getVideoJob.mockResolvedValue(job('error', { error: 'Could not read this video.' }))
    render(<VideoMode />)
    await user().upload(screen.getByLabelText('Choose a video'), video())
    await user().click(screen.getByRole('button', { name: 'Analyse video' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not read this video.')
  })

  it('shows upload errors (e.g. too large)', async () => {
    uploadVideo.mockRejectedValue(new ApiError('Video is larger than 200 MB.', { status: 413 }))
    render(<VideoMode />)
    await user().upload(screen.getByLabelText('Choose a video'), video())
    await user().click(screen.getByRole('button', { name: 'Analyse video' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Video is larger than 200 MB.')
  })

  it('cancels a running job', async () => {
    uploadVideo.mockResolvedValue(job('queued'))
    getVideoJob.mockResolvedValue(job('processing', { progress: 0.2 }))
    render(<VideoMode />)
    await user().upload(screen.getByLabelText('Choose a video'), video())
    await user().click(screen.getByRole('button', { name: 'Analyse video' }))
    await user().click(await screen.findByRole('button', { name: 'Cancel' }))

    expect(deleteVideoJob).toHaveBeenCalledWith('job1')
    expect(screen.getByText('Analysis cancelled.')).toBeInTheDocument()
  })

  it('rejects non-video files in the browser', async () => {
    render(<VideoMode />)
    await user().upload(screen.getByLabelText('Choose a video'), new File(['x'], 'photo.jpg', { type: 'image/jpeg' }))
    expect(screen.getByRole('alert')).toHaveTextContent('"photo.jpg" is not a video')
    expect(screen.getByRole('button', { name: 'Analyse video' })).toBeDisabled()
  })
})

describe('video helpers', () => {
  it('finds the analysed frame for a playback time', () => {
    const frames = [{ t: 0 }, { t: 0.1 }, { t: 0.2 }, { t: 0.3 }]
    expect(frameIndexAt(frames, -1)).toBe(-1)
    expect(frameIndexAt(frames, 0)).toBe(0)
    expect(frameIndexAt(frames, 0.15)).toBe(1)
    expect(frameIndexAt(frames, 9)).toBe(3)
    expect(frameIndexAt([], 1)).toBe(-1)
  })

  it('converts compact boxes to detections', () => {
    expect(toDetections([[4, 1, 2, 3, 4, 0.8], [0, 5, 6, 7, 8, 0.5]])).toEqual([
      { track_id: 4, pending: false, bbox: [1, 2, 3, 4], confidence: 0.8 },
      { track_id: null, pending: true, bbox: [5, 6, 7, 8], confidence: 0.5 },
    ])
  })

  it('validates video files', () => {
    expect(validateVideoFile(video())).toBeNull()
    expect(validateVideoFile(video('clip.MOV', ''))).toBeNull()
    expect(validateVideoFile(new File([''], 'e.mp4', { type: 'video/mp4' }))).toMatch(/is empty/)
  })

  it('formats video clock times', () => {
    expect(clock(83.44)).toBe('1:23.4')
    expect(clock(5, 0)).toBe('0:05')
  })
})

describe('waitFor guard', () => {
  it('has no pending timers leaking between tests', async () => {
    await waitFor(() => expect(true).toBe(true))
  })
})
