import { useEffect, useState } from 'react'

/**
 * Rendered width (CSS px) of the element in `ref`, kept up to date with a
 * ResizeObserver. Returns 0 until measured or where ResizeObserver is missing
 * (e.g. some test environments). Pass `dep` to re-attach when the element changes.
 */
export default function useElementWidth(ref, dep) {
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref, dep])

  return width
}
