import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const HEALTH = { status: 'ok', version: '0.1.0', model: 'yolov8n.pt', device: 'cpu', model_loaded: true }

function renderAt(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App shell', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(HEALTH), { status: 200 }),
    )
  })

  it('shows the Detection page by default', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { name: 'Detection' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Detection' })).toHaveClass('active')
  })

  it('navigates to History', async () => {
    renderAt('/')
    await userEvent.click(screen.getByRole('link', { name: 'History' }))
    // History is lazy-loaded, so its heading appears asynchronously
    // (first load compiles the chart library, which can exceed the default 1 s wait)
    expect(await screen.findByRole('heading', { name: 'History' }, { timeout: 15000 })).toBeInTheDocument()
  })

  it('redirects unknown paths to Detection', () => {
    renderAt('/does-not-exist')
    expect(screen.getByRole('heading', { name: 'Detection' })).toBeInTheDocument()
  })
})

describe('BackendStatus', () => {
  it('shows model and device when the API is online', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(HEALTH), { status: 200 }),
    )
    renderAt('/')
    expect(await screen.findByText('API online · yolov8n.pt · cpu')).toBeInTheDocument()
  })

  it('shows offline when the API cannot be reached', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    renderAt('/')
    expect(await screen.findByText('API offline')).toBeInTheDocument()
  })
})
