import { useEffect, useState } from 'react'

// Chart colours come from the CSS design tokens (styles/index.css), so charts
// follow light/dark mode. SVG attributes can't use var() reliably, hence this hook.
const TOKENS = { mark: '--chart', grid: '--chart-grid', text: '--text-muted', surface: '--surface' }
const FALLBACK = { mark: '#16a34a', grid: '#e8ebef', text: '#5f6873', surface: '#ffffff' }

function read() {
  if (typeof window === 'undefined' || !window.getComputedStyle) return FALLBACK
  const style = getComputedStyle(document.documentElement)
  return Object.fromEntries(
    Object.entries(TOKENS).map(([key, prop]) => [key, style.getPropertyValue(prop).trim() || FALLBACK[key]]),
  )
}

export default function useChartColors() {
  const [colors, setColors] = useState(read)

  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!mq) return undefined
    const update = () => setColors(read())
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [])

  return colors
}
