import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { BookOpenText, Gauge, House, Menu, PlugZap, Settings, Webhook, X } from 'lucide-react'
import { cn } from './lib/utils'
import { DashboardPage } from './pages/DashboardPage'
import { DocsPage } from './pages/DocsPage'
import { HomePage } from './pages/HomePage'
import { PluginsPage } from './pages/PluginsPage'
import { SettingsPage } from './pages/SettingsPage'
import { WebhooksPage } from './pages/WebhooksPage'

const NAV_ITEMS = [
  { to: '/home', label: 'Микро-сайт', icon: House },
  { to: '/dashboard', label: 'Дашборд', icon: Gauge },
  { to: '/plugins', label: 'Плагины', icon: PlugZap },
  { to: '/settings', label: 'Настройки', icon: Settings },
  { to: '/webhooks', label: 'Вебхуки', icon: Webhook },
  { to: '/api-docs', label: 'API Docs', icon: BookOpenText },
]

export default function App() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [isMobileNav, setIsMobileNav] = useState(() => (typeof window !== 'undefined' ? window.innerWidth < 768 : false))

  useEffect(() => {
    const onResize = () => setIsMobileNav(window.innerWidth < 768)
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    if (!isMobileNav) setMobileNavOpen(false)
  }, [isMobileNav])

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto w-full max-w-7xl px-4 py-6">
        <header className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 shadow-[0_0_40px_rgba(6,182,212,0.08)] backdrop-blur-sm">
          <h1 className="bg-gradient-to-r from-cyan-300 via-cyan-100 to-zinc-100 bg-clip-text text-3xl font-semibold tracking-tight text-transparent md:text-4xl">
            Neyra Control Center
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            Микро-сайт, управление плагинами, вебхуки и встроенная документация API
          </p>
        </header>
        {isMobileNav ? (
          <div className="mb-6 flex items-center justify-between gap-3 rounded-2xl border border-zinc-800 bg-zinc-900/40 p-2 backdrop-blur-sm">
            <p className="pl-2 text-sm font-medium tracking-tight text-zinc-300">Навигация</p>
            <button
              aria-label="Открыть меню"
              className="inline-flex items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-900/70 px-3 py-2 text-sm text-zinc-200 transition hover:border-cyan-500/50 hover:text-cyan-100"
              onClick={() => setMobileNavOpen(true)}
              type="button"
            >
              <Menu className="h-4 w-4" />
              Меню
            </button>
          </div>
        ) : (
          <nav className="mb-6 flex items-center gap-2 overflow-x-auto rounded-2xl border border-zinc-800 bg-zinc-900/40 p-2 backdrop-blur-sm">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                className={({ isActive }) =>
                  cn(
                    'group inline-flex shrink-0 items-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500',
                    isActive
                      ? 'border-cyan-300/70 bg-cyan-500/25 font-semibold text-cyan-50 shadow-[0_0_20px_rgba(6,182,212,0.25)] ring-1 ring-cyan-300/40'
                      : 'border-zinc-700 bg-zinc-900/50 text-zinc-400 hover:border-cyan-500/40 hover:text-zinc-100'
                  )
                }
                to={item.to}
              >
                <item.icon className="h-4 w-4 transition-colors group-hover:text-cyan-300" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        )}

        {mobileNavOpen && isMobileNav ? (
          <div className="fixed inset-0 z-50">
            <button
              aria-label="Закрыть меню"
              className="absolute inset-0 bg-black/65 backdrop-blur-[1px]"
              onClick={() => setMobileNavOpen(false)}
              type="button"
            />
            <aside className="absolute right-0 top-0 h-full w-[88%] max-w-sm border-l border-zinc-800 bg-zinc-950/95 p-4 shadow-2xl">
              <div className="mb-4 flex items-center justify-between">
                <p className="text-sm font-semibold tracking-tight text-zinc-200">Разделы Neyra</p>
                <button
                  aria-label="Закрыть меню"
                  className="rounded-lg border border-zinc-700 bg-zinc-900/70 p-2 text-zinc-300 hover:border-cyan-500/50 hover:text-cyan-100"
                  onClick={() => setMobileNavOpen(false)}
                  type="button"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="grid gap-2">
                {NAV_ITEMS.map((item) => (
                  <NavLink
                    key={item.to}
                    className={({ isActive }) =>
                      cn(
                        'inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500',
                        isActive
                          ? 'border-cyan-300/70 bg-cyan-500/25 font-semibold text-cyan-50 ring-1 ring-cyan-300/40'
                          : 'border-zinc-700 bg-zinc-900/70 text-zinc-300'
                      )
                    }
                    onClick={() => setMobileNavOpen(false)}
                    to={item.to}
                  >
                    <item.icon className="h-4 w-4" />
                    {item.label}
                  </NavLink>
                ))}
              </div>
            </aside>
          </div>
        ) : null}

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
    </div>
  )
}
