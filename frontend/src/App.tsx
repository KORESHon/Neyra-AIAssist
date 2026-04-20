import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
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
    <div className="layout">
      <header className="top">
        <div>
          <h1 className="title">Neyra Control Center</h1>
          <p className="subtitle">Микро-сайт, управление плагинами, вебхуки и встроенная документация API</p>
        </div>
      </header>
      <nav className="tabs">
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.to} className={({ isActive }) => (isActive ? 'tab active' : 'tab')} to={item.to}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="page">
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
