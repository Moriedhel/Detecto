// Grab the current video frame as a JPEG data URL, downscaled for fast upload.
let canvas = null // reused between frames

/**
 * @param {HTMLVideoElement} video
 * @param {number} maxWidth  frames wider than this are scaled down (keeps aspect ratio)
 * @param {number} quality   JPEG quality 0..1
 * @returns {{dataUrl: string, width: number, height: number} | null}  null until the video has a frame
 */
export function captureFrame(video, maxWidth = 640, quality = 0.8) {
  const vw = video?.videoWidth
  const vh = video?.videoHeight
  if (!vw || !vh) return null

  const scale = Math.min(1, maxWidth / vw)
  const width = Math.round(vw * scale)
  const height = Math.round(vh * scale)

  canvas ??= document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  canvas.getContext('2d').drawImage(video, 0, 0, width, height)
  return { dataUrl: canvas.toDataURL('image/jpeg', quality), width, height }
}
