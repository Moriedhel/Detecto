import { NavLink, Outlet } from 'react-router-dom'

import BackendStatus from './BackendStatus'

// App shell: header with brand, page navigation and backend status.
export default function Layout() {
  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <img src="/favicon.svg" alt="" width="24" height="24" />
          <span>Detecto</span>
        </div>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end>Detection</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
        <BackendStatus />
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
