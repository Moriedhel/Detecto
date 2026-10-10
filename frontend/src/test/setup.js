// Global test setup: jest-dom matchers (toBeInTheDocument, …) and per-test cleanup.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom doesn't implement media playback; stub it so components can call play/pause
// (guarded: the API integration tests run in plain Node without a DOM)
if (typeof HTMLMediaElement !== 'undefined') {
  HTMLMediaElement.prototype.play = () => Promise.resolve()
  HTMLMediaElement.prototype.pause = () => {}
}

// jsdom has no object URLs; previews only need a placeholder string
if (!URL.createObjectURL) URL.createObjectURL = () => 'blob:mock-preview'
if (!URL.revokeObjectURL) URL.revokeObjectURL = () => {}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
