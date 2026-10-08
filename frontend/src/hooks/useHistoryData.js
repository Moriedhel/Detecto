import { useEffect, useState } from 'react'

import { getHistory, getHourly, getStats } from '../api'

export const SERIES_LIMIT = 1000 // max records plotted in the time chart

/**
 * Loads everything the History View shows, for one set of filters.
 * Previous data stays visible while new data loads (no flashing).
 *
 * @param {object} filters   { start, end, minConfidence, minCount } (ISO strings / numbers / null)
 * @param {number} page      0-based table page
 * @param {number} pageSize  table rows per page
 * @param {number} reloadKey change to force a refetch (e.g. after reset)
 */
export default function useHistoryData(filters, page, pageSize, reloadKey) {
  const [overview, setOverview] = useState({ stats: null, hourly: null, timeline: null, series: null, seriesTotal: 0 })
  const [table, setTable] = useState(null)
  const [loading, setLoading] = useState({ overview: true, table: true })
  const [error, setError] = useState(null)

  // KPIs + charts depend only on the filters
  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    setLoading((l) => ({ ...l, overview: true }))

    Promise.all([
      getStats(filters, { signal }),
      getHourly({ ...filters, mode: 'hour_of_day' }, { signal }),
      getHourly({ ...filters, mode: 'timeline' }, { signal }),
      getHistory({ ...filters, limit: SERIES_LIMIT, newestFirst: true }, { signal }),
    ])
      .then(([stats, hourly, timeline, latest]) => {
        setOverview({
          stats,
          hourly,
          timeline,
          series: [...latest.items].reverse(), // oldest -> newest for the time axis
          seriesTotal: latest.total,
        })
        setError(null)
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
      .finally(() => {
        if (!signal.aborted) setLoading((l) => ({ ...l, overview: false }))
      })

    return () => controller.abort()
  }, [filters, reloadKey])

  // Table page depends on filters + page
  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    setLoading((l) => ({ ...l, table: true }))

    getHistory({ ...filters, limit: pageSize, offset: page * pageSize }, { signal })
      .then((res) => {
        setTable(res)
        setError(null)
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
      .finally(() => {
        if (!signal.aborted) setLoading((l) => ({ ...l, table: false }))
      })

    return () => controller.abort()
  }, [filters, page, pageSize, reloadKey])

  return { ...overview, table, loading, error }
}
