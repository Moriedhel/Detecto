import { ALLOWED_TYPES, MAX_UPLOAD_MB } from '../config'

const EXTENSION_TYPES = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png' }

/** Best-guess MIME type: the browser's `file.type`, else from the extension. */
export function guessType(file) {
  if (file.type) return file.type
  const ext = file.name?.split('.').pop()?.toLowerCase()
  return EXTENSION_TYPES[ext] || ''
}

/**
 * Check a file before uploading. Returns an error message, or null if OK.
 * The backend validates again (including the file's actual bytes); this just
 * gives instant feedback without a round trip.
 */
export function validateImageFile(file) {
  if (!file) return 'No file selected.'
  if (file.size === 0) return `"${file.name}" is empty.`

  const type = guessType(file)
  if (!ALLOWED_TYPES.includes(type)) {
    const shown = type || file.name.split('.').pop() || 'unknown'
    return `"${file.name}" is not supported (${shown}). Please choose a JPEG or PNG image.`
  }

  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    const mb = (file.size / 1024 / 1024).toFixed(1)
    return `"${file.name}" is ${mb} MB; the limit is ${MAX_UPLOAD_MB} MB.`
  }
  return null
}
