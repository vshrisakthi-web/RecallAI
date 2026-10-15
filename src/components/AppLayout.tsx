import { NavLink, Outlet } from 'react-router-dom';

const navItems = [
  { to: '/overview', label: 'Overview', icon: '▦' },
  { to: '/timeline', label: 'Memory Timeline', icon: '〰' },
  { to: '/ask', label: 'Ask RecallAI', icon: '✦' },
  { to: '/workflow', label: 'Workflow Review', icon: '✅' },
  { to: '/privacy', label: 'Privacy Settings', icon: '🔒' },
];

/**
 * Dashboard app shell: persistent sidebar navigation, a top privacy/status bar,
 * and a privacy footer. Wraps all routed dashboard screens via <Outlet />.
 */
export default function AppLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-canvas md:flex-row">
      {/* Sidebar */}
      <aside className="w-full shrink-0 border-b border-slate-100 bg-surface md:sticky md:top-0 md:h-screen md:w-64 md:border-b-0 md:border-r">
        <div className="flex items-center gap-2 px-5 py-4">
          <span
            aria-hidden="true"
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white"
          >
            ↻
          </span>
          <div className="leading-tight">
            <div className="text-sm font-bold text-ink">RecallAI</div>
            <div className="text-xs text-ink-muted">Local</div>
          </div>
        </div>

        <nav aria-label="Primary" className="px-3 pb-4">
          <ul className="space-y-1">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    [
                      'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition',
                      isActive
                        ? 'bg-brand-700 text-white'
                        : 'text-ink-muted hover:bg-slate-50 hover:text-ink',
                    ].join(' ')
                  }
                >
                  <span aria-hidden="true">{item.icon}</span>
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {/* Device storage panel */}
        <div className="mx-3 mb-3 rounded-xl bg-slate-50 p-4">
          <div className="mb-2 flex items-center justify-between text-xs font-medium text-ink">
            <span>💾 Device Storage</span>
            <span className="rounded bg-safe-100 px-2 py-0.5 text-safe-700">Encrypted</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
            <div className="h-full w-[18%] rounded-full bg-brand-500" />
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-ink-muted">
            <span>1.4 GB used</span>
            <span>Local SSD</span>
          </div>
        </div>

        <div className="px-5 pb-4 text-xs text-ink-muted">
          <span aria-hidden="true">📍</span> Data stored locally
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top status bar */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 bg-surface px-5 py-2 text-xs text-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true">🛡️</span> Zero Cloud Telemetry • Isolated Air-Gapped
            Sandbox
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-safe-500" aria-hidden="true" />
            Local Daemon Running
          </span>
        </div>

        <main className="flex-1 px-5 py-6 md:px-8">
          <Outlet />
        </main>

        {/* Privacy footer */}
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 bg-surface px-5 py-3 text-xs text-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true">🔒</span> Your memories never leave this device.
            Encrypted on local drive.
          </span>
          <span className="inline-flex items-center gap-3">
            <span>AES-256 GCM</span>
            <span>Hardware Enclave Active</span>
          </span>
        </footer>
      </div>
    </div>
  );
}
