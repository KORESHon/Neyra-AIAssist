import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { cn } from './lib/utils'
import { DashboardPage } from './pages/DashboardPage'
import { DocsPage } from './pages/DocsPage'
import { HomePage } from './pages/HomePage'
import { PluginsPage } from './pages/PluginsPage'
import { SettingsPage } from './pages/SettingsPage'
import { WebhooksPage } from './pages/WebhooksPage'

const NAV_ITEMS = [
  { to: '/home', label: 'Микро-сайт' },
  { to: '/dashboard', label: 'Дашборд' },
  { to: '/plugins', label: 'Плагины' },
  { to: '/settings', label: 'Настройки' },
  { to: '/webhooks', label: 'Вебхуки' },
  { to: '/api-docs', label: 'API Docs' },
]

export default function App() {
  return (
    <div className="mx-auto min-h-screen w-full max-w-7xl px-4 py-6 text-foreground">
      <header className="mb-4">
        <h1 className="text-3xl font-semibold tracking-tight">Neyra Control Center</h1>
        <p className="mt-2 text-sm text-muted">Микро-сайт, управление плагинами, вебхуки и встроенная документация API</p>
      </header>
      <nav className="mb-4 flex flex-wrap gap-2 rounded-lg border border-border bg-card p-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            className={({ isActive }) =>
              cn(
                'rounded-md border px-3 py-2 text-sm transition-colors',
                isActive
                  ? 'border-accent bg-accent/20 text-foreground'
                  : 'border-border bg-background/50 text-muted hover:bg-border/30'
              )
            }
            to={item.to}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/home" replace />} />
          <Route path="/home" element={<HomePage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/plugins" element={<PluginsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/webhooks" element={<WebhooksPage />} />
          <Route path="/api-docs" element={<DocsPage />} />
          <Route path="*" element={<Navigate to="/home" replace />} />
        </Routes>
      </main>
    </div>
  )
}
