import { useState } from 'react'
import { Link } from 'react-router-dom'

import { exportCsvUrl } from '../api'
import ErrorBanner from '../components/ErrorBanner'
import HistoryFilters from '../components/history/HistoryFilters'
import HistoryTable from '../components/history/HistoryTable'
import HourlyChart from '../components/history/HourlyChart'
import KpiRow from '../components/history/KpiRow'
import PeopleOverTimeChart from '../components/history/PeopleOverTimeChart'
import ResetHistory from '../components/history/ResetHistory'
import useHistoryData from '../hooks/useHistoryData'

const PAGE_SIZE = 25
const INITIAL_FILTERS = { preset: 'all', start: null, end: null, minConfidence: null, minCount: null }

const isFiltered = (f) => f.start || f.end || f.minConfidence != null || f.minCount != null

// History View: everything below the filter row is scoped by the same filters.
export default function HistoryPage() {
  const [filters, setFilters] = useState(INITIAL_FILTERS)
  const [page, setPage] = useState(0)
  const [reloadKey, setReloadKey] = useState(0)
  const [notice, setNotice] = useState(null)
  const [actionError, setActionError] = useState(null)

  const data = useHistoryData(filters, page, PAGE_SIZE, reloadKey)
  const summary = data.stats?.summary
  const totalStored = summary?.total_detections ?? 0
  const loadingOverview = data.loading.overview && data.stats != null // refetch: keep previous render, faded

  const changeFilters = (next) => {
    setFilters(next)
    setPage(0)
    setNotice(null)
  }

  const reload = () => setReloadKey((k) => k + 1)

  const neverUsed = data.stats != null && totalStored === 0 && !isFiltered(filters)

  return (
    <section className="history-page">
      <header className="page-header page-header-row">
        <div>
          <h1>History</h1>
          <p className="muted">People counted over time. Filters apply to every number, chart and row below.</p>
        </div>
        <div className="toolbar">
          <button type="button" className="button" onClick={reload}>Refresh</button>
          <a
            className={`button${totalStored ? '' : ' disabled'}`}
            href={exportCsvUrl(filters)}
            download
            aria-disabled={!totalStored}
            onClick={(e) => !totalStored && e.preventDefault()}
          >
            Export CSV
          </a>
          <ResetHistory
            // The exact count of ALL records is only known when no filter is active
            total={isFiltered(filters) ? null : totalStored}
            disabled={data.stats == null || (!isFiltered(filters) && totalStored === 0)}
            onDone={(deleted) => {
              setNotice(`Deleted ${deleted.toLocaleString()} detections.`)
              setPage(0)
              reload()
            }}
            onError={setActionError}
          />
        </div>
      </header>

      <HistoryFilters filters={filters} onChange={changeFilters} />

      <ErrorBanner message={actionError || data.error} onDismiss={() => setActionError(null)} />
      {notice && <p className="notice" role="status">{notice}</p>}

      {neverUsed ? (
        <div className="panel placeholder">
          <p>
            No detections stored yet. Run some on the <Link to="/">Detection page</Link> and they will appear here.
          </p>
        </div>
      ) : (
        <div className={`history-body${loadingOverview ? ' refetching' : ''}`} aria-busy={data.loading.overview}>
          <KpiRow summary={summary} />

          <div className="history-charts">
            <section className="panel">
              <h2>People over time</h2>
              <PeopleOverTimeChart records={data.series} total={data.seriesTotal} timeline={data.timeline?.buckets} />
            </section>
            <section className="panel">
              <h2>Average crowd size by hour of day</h2>
              <HourlyChart buckets={data.hourly?.buckets} />
            </section>
          </div>

          <section className={`panel${data.loading.table && data.table ? ' refetching' : ''}`}>
            <h2>Detections</h2>
            <HistoryTable page={data.table} pageIndex={page} pageSize={PAGE_SIZE} onPage={setPage} />
          </section>
        </div>
      )}
    </section>
  )
}
