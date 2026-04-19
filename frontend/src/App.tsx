import { useCallback, useEffect, useState } from 'react'
import { apiGet, getToken, setToken } from './api'

type HealthData = Record<string, unknown>
type MemoryStats = {
  short_memory_size: number
  long_memory_records: number
  people_records: number
}
type PluginRow = {
  id: string
  name: string
  version: string
  enabled: boolean
  lifecycle: string
  cli_modes: string[]
  main_script: string
  plugin_dir: string
}

type BalanceData = {
  provider: string
  hint?: string
  openrouter?: null
  limit?: number | null
  limit_remaining?: number | null
  limit_reset?: string | null
  usage?: number
  usage_daily?: number
  usage_weekly?: number
  usage_monthly?: number
  is_free_tier?: boolean
  label?: string
}

export default function App() {
  const [tokenInput, setTokenInput] = useState(getToken)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [health, setHealth] = useState<HealthData | null>(null)
  const [memory, setMemory] = useState<MemoryStats | null>(null)
  const [plugins, setPlugins] = useState<PluginRow[]>([])
  const [balance, setBalance] = useState<BalanceData | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [h, m, p, b] = await Promise.all([
        apiGet<{ data: HealthData }>('/v1/health'),
        apiGet<{ data: MemoryStats }>('/v1/memory/stats'),
        apiGet<{ data: { plugins: PluginRow[] } }>('/v1/plugins'),
        apiGet<{ data: BalanceData }>('/v1/llm/balance'),
      ])
      setHealth(h.data)
      setMemory(m.data)
      setPlugins(p.data.plugins ?? [])
      setBalance(b.data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    queueMicrotask(() => {
      void load()
    })
  }, [load])

  return (
    <div className="layout">
      <header className="top">
        <div>
          <h1 className="title">Нейра</h1>
          <p className="subtitle">дашборд ядра — здоровье, память, баланс LLM, плагины</p>
        </div>
        <div className="actions">
          <label className="token-field">
            <span>Bearer (если задан в config)</span>
            <input
              type="password"
              autoComplete="off"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="опционально"
            />
          </label>
          <button type="button" className="btn secondary" onClick={() => setToken(tokenInput)}>
            Сохранить токен
          </button>
          <button type="button" className="btn" onClick={() => void load()} disabled={loading}>
            {loading ? 'Обновление…' : 'Обновить'}
          </button>
        </div>
      </header>

      {error ? (
        <div className="banner error" role="alert">
          {error}
        </div>
      ) : null}

      <section className="grid">
        <article className="card">
          <h2>Health</h2>
          <pre className="json">{health ? JSON.stringify(health, null, 2) : '—'}</pre>
        </article>
        <article className="card">
          <h2>Память</h2>
          {memory ? (
            <ul className="stats">
              <li>
                Краткая память: <strong>{memory.short_memory_size}</strong> сообщ.
              </li>
              <li>
                RAG: <strong>{memory.long_memory_records}</strong> записей
              </li>
              <li>
                PeopleDB: <strong>{memory.people_records}</strong>
              </li>
            </ul>
          ) : (
            <p className="muted">—</p>
          )}
        </article>
        <article className="card">
          <h2>OpenRouter</h2>
          {balance?.hint ? <p className="muted">{balance.hint}</p> : null}
          {balance && balance.provider === 'openrouter' ? (
            <ul className="stats">
              {balance.label != null && balance.label !== '' ? (
                <li>
                  Ключ: <strong className="mono">{String(balance.label)}</strong>
                </li>
              ) : null}
              <li>
                Остаток лимита:{' '}
                <strong>
                  {balance.limit_remaining != null && balance.limit_remaining !== undefined
                    ? String(balance.limit_remaining)
                    : '—'}
                </strong>
                {balance.limit != null ? (
                  <span className="muted"> / {String(balance.limit)}</span>
                ) : null}
              </li>
              <li>
                Usage (всего): <strong>{balance.usage != null ? String(balance.usage) : '—'}</strong>
              </li>
              <li className="muted small">
                Сутки: {balance.usage_daily ?? '—'} · неделя: {balance.usage_weekly ?? '—'} · месяц:{' '}
                {balance.usage_monthly ?? '—'}
              </li>
            </ul>
          ) : balance ? (
            <p className="muted">Провайдер: {balance.provider} — баланс OpenRouter не запрашивается.</p>
          ) : (
            <p className="muted">—</p>
          )}
        </article>
        <article className="card wide">
          <h2>Плагины</h2>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>id</th>
                  <th>версия</th>
                  <th>режимы</th>
                  <th>вкл</th>
                  <th>скрипт</th>
                </tr>
              </thead>
              <tbody>
                {plugins.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="muted">
                      нет данных
                    </td>
                  </tr>
                ) : (
                  plugins.map((row) => (
                    <tr key={row.id}>
                      <td className="mono">{row.id}</td>
                      <td>{row.version}</td>
                      <td className="mono small">{row.cli_modes.join(', ') || '—'}</td>
                      <td>{row.enabled ? 'да' : 'нет'}</td>
                      <td className="mono small">{row.main_script || '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <footer className="foot">
        <a href="/docs" target="_blank" rel="noreferrer">
          Swagger /docs
        </a>
        <span className="sep">·</span>
        <a href="/openapi.json" target="_blank" rel="noreferrer">
          openapi.json
        </a>
        <span className="sep">·</span>
        <a href="/redoc" target="_blank" rel="noreferrer">
          ReDoc
        </a>
      </footer>
    </div>
  )
}
