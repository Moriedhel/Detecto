import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, deletePerson, enrollPerson, getPeople } from '../api'
import BoxLayer from './BoxLayer'
import FacePanel from './FacePanel'

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal()),
  getPeople: vi.fn(),
  enrollPerson: vi.fn(),
  deletePerson: vi.fn(),
}))

const MARIA = { id: 1, name: 'Maria', photos: 3, created_at: '2026-10-10T10:00:00Z' }
const photo = (name = 'me.jpg') => new File(['jpeg'], name, { type: 'image/jpeg' })
const user = () => userEvent.setup({ applyAccept: false })

beforeEach(() => {
  vi.clearAllMocks()
  getPeople.mockResolvedValue({ available: true, threshold: 0.363, people: [MARIA] })
})

describe('FacePanel', () => {
  it('lists enrolled people and toggles recognition', async () => {
    const onToggle = vi.fn()
    render(<FacePanel enabled={false} onToggle={onToggle} />)

    expect(await screen.findByText('Maria')).toBeInTheDocument()
    expect(screen.getByText('3 photos')).toBeInTheDocument()

    await user().click(screen.getByRole('checkbox', { name: 'Recognise enrolled faces' }))
    expect(onToggle).toHaveBeenCalledWith(true)
  })

  it('enrols only with a name, photos and consent', async () => {
    enrollPerson.mockResolvedValue({
      person: { ...MARIA, id: 2, name: 'Nikos', photos: 1 },
      results: [{ file: 'a.jpg', ok: true, reason: null }, { file: 'b.jpg', ok: false, reason: '2 faces found.' }],
    })
    render(<FacePanel enabled={false} onToggle={vi.fn()} />)
    await screen.findByText('Maria')

    const submit = screen.getByRole('button', { name: 'Enrol' })
    expect(submit).toBeDisabled()

    await user().type(screen.getByLabelText('Name'), 'Nikos')
    await user().upload(screen.getByLabelText(/Photos/), [photo('a.jpg'), photo('b.jpg')])
    expect(submit).toBeDisabled() // consent still missing
    await user().click(screen.getByRole('checkbox', { name: /agreed to have their face enrolled/ }))
    await user().click(submit)

    const [name, files, opts] = enrollPerson.mock.calls[0]
    expect(name).toBe('Nikos')
    expect(files.map((f) => f.name)).toEqual(['a.jpg', 'b.jpg'])
    expect(opts).toEqual({ consent: true })
    expect(await screen.findByText(/Enrolled Nikos: 1 of 2 photos used/)).toBeInTheDocument()
    expect(screen.getByText('b.jpg: 2 faces found.')).toBeInTheDocument()
    expect(getPeople).toHaveBeenCalledTimes(2) // list refreshed
  })

  it('rejects non-image files before uploading', async () => {
    render(<FacePanel enabled={false} onToggle={vi.fn()} />)
    await screen.findByText('Maria')
    await user().type(screen.getByLabelText('Name'), 'X')
    await user().upload(screen.getByLabelText(/Photos/), [new File(['x'], 'notes.txt', { type: 'text/plain' })])
    await user().click(screen.getByRole('checkbox', { name: /agreed/ }))
    await user().click(screen.getByRole('button', { name: 'Enrol' }))

    expect(screen.getByRole('alert')).toHaveTextContent('"notes.txt" is not supported')
    expect(enrollPerson).not.toHaveBeenCalled()
  })

  it('shows enrolment errors from the server', async () => {
    enrollPerson.mockRejectedValue(new ApiError('No usable photos. a.jpg: No face found.', { status: 422 }))
    render(<FacePanel enabled={false} onToggle={vi.fn()} />)
    await screen.findByText('Maria')
    await user().type(screen.getByLabelText('Name'), 'Ana')
    await user().upload(screen.getByLabelText(/Photos/), photo('a.jpg'))
    await user().click(screen.getByRole('checkbox', { name: /agreed/ }))
    await user().click(screen.getByRole('button', { name: 'Enrol' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No usable photos. a.jpg: No face found.')
  })

  it('deletes a person', async () => {
    deletePerson.mockResolvedValue(null)
    render(<FacePanel enabled={false} onToggle={vi.fn()} />)
    await screen.findByText('Maria')
    getPeople.mockResolvedValue({ available: true, threshold: 0.363, people: [] })

    await user().click(screen.getByRole('button', { name: 'Delete Maria' }))

    expect(deletePerson).toHaveBeenCalledWith(1)
    expect(await screen.findByText(/Deleted Maria and their face data/)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Delete Maria' })).not.toBeInTheDocument())
  })

  it('explains when the face models are missing', async () => {
    getPeople.mockResolvedValue({ available: false, threshold: 0.363, people: [] })
    render(<FacePanel enabled={false} onToggle={vi.fn()} />)
    expect(await screen.findByText(/Face models are missing/)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Recognise enrolled faces' })).not.toBeInTheDocument()
  })
})

describe('BoxLayer with tracking', () => {
  it('shows "#?" while a new person is pending re-identification', () => {
    const { container } = render(
      <BoxLayer
        width={640}
        height={480}
        detections={[
          { bbox: [10, 10, 200, 400], confidence: 0.9, track_id: 3, pending: true },
          { bbox: [300, 10, 500, 400], confidence: 0.8, track_id: 1, reidentified: true },
        ]}
      />,
    )
    expect(within(container).getByText('#? 90%')).toBeInTheDocument()
    expect(within(container).getByText('#1 80%')).toBeInTheDocument()
  })
})

describe('BoxLayer with faces', () => {
  it('names recognised people and labels unknown faces', () => {
    const { container } = render(
      <BoxLayer
        width={640}
        height={480}
        detections={[
          { bbox: [10, 10, 200, 400], confidence: 0.9, identity: { person_id: 1, name: 'Maria', similarity: 0.71 } },
          { bbox: [300, 10, 500, 400], confidence: 0.8, identity: { person_id: null, name: null, similarity: 0.1 } },
        ]}
        faces={[
          { bbox: [60, 30, 120, 100], score: 0.9, person_id: 1, name: 'Maria', similarity: 0.71 },
          { bbox: [360, 30, 420, 100], score: 0.9, person_id: null, name: null, similarity: 0.1 },
        ]}
      />,
    )
    const svg = within(container)
    expect(svg.getByText('#1 Maria')).toBeInTheDocument()
    expect(svg.getByText('#2 80%')).toBeInTheDocument()
    expect(svg.getByText('Maria 71%')).toBeInTheDocument()
    expect(svg.getByText('Unknown')).toBeInTheDocument()
    expect(svg.getAllByTestId('face-box')).toHaveLength(2)
  })
})
