// Runtime configuration, read from Vite env variables (frontend/.env)
const stripTrailingSlashes = (s) => {
  while (s.endsWith('/')) s = s.slice(0, -1)
  return s
}

export const API_URL = stripTrailingSlashes(import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000')

// Client-side upload checks; keep in line with the backend's DETECTO_MAX_UPLOAD_MB / allowed types
export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB || 10)
export const ALLOWED_TYPES = ['image/jpeg', 'image/png']

// Default confidence threshold shown in the UI (backend default: DETECTO_CONF_THRESHOLD)
export const DEFAULT_CONF = Number(import.meta.env.VITE_DEFAULT_CONF || 0.4)
