// Global test setup: jest-dom matchers (toBeInTheDocument, …) and per-test cleanup.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom has no object URLs; previews only need a placeholder string
if (!URL.createObjectURL) URL.createObjectURL = () => 'blob:mock-preview'
if (!URL.revokeObjectURL) URL.revokeObjectURL = () => {}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
