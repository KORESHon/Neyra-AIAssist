import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../api'
import type { ApiEnvelope, BalanceData, HealthData, MemoryStats, PluginRow } from '../types'

export function DashboardPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthData | null>(null)
  const [memory, setMemory] = useState<MemoryStats | null>(null)
  const [plugins, setPlugins] = useState<PluginRow[]>([])
  const [balance, setBalance] = useState<BalanceData | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [h, m, p, b] = await Promise.all([
        apiGet<ApiEnvelope<HealthData>>('/v1/health'),
        apiGet<ApiEnvelope<MemoryStats>>('/v1/memory/stats'),
        apiGet<ApiEnvelope<{ plugins: PluginRow[] }>>('/v1/plugins'),
        apiGet<ApiEnvelope<BalanceData>>('/v1/llm/balance'),
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
    void load()
  }, [load])

  return (
    <section className="stack">
      <div className="actions">
        <button className="btn" disabled={loading} onClick={() => void load()} type="button">
          {loading ? 'Обновление…' : 'Обновить данные'}
        </button>
      </div>
      {error ? <div className="banner error">{error}</div> : null}
      <div className="grid">
        <article className="card">
          <h2>Health</h2>
          <pre className="json">{health ? JSON.stringify(health, null, 2) : '—'}</pre>
        </article>
        <article className="card">
          <h2>Память</h2>
          {memory ? (
            <ul className="stats">
              <li>Краткая память: {memory.short_memory_size}</li>
              <li>RAG: {memory.long_memory_records}</li>
              <li>PeopleDB: {memory.people_records}</li>
            </ul>
          ) : (
            <p className="muted">—</p>
          )}
        </article>
        <article className="card">
          <h2>Баланс LLM</h2>
          {!balance ? <p className="muted">—</p> : null}
          {balance?.hint ? <p className="muted">{balance.hint}</p> : null}
          {balance && balance.provider === 'openrouter' ? (
            <ul className="stats">
              <li>Остаток: {balance.limit_remaining ?? '—'}</li>
              <li>Лимит: {balance.limit ?? '—'}</li>
              <li>Usage total: {balance.usage ?? '—'}</li>
              <li>Сутки/неделя/месяц: {balance.usage_daily ?? '—'} / {balance.usage_weekly ?? '—'} / {balance.usage_monthly ?? '—'}</li>
            </ul>
          ) : null}
        </article>
        <article className="card wide">
          <h2>Плагины (read-only обзор)</h2>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>id</th>
                  <th>версия</th>
                  <th>lifecycle</th>
                  <th>enabled</th>
                  <th>script</th>
                </tr>
              </thead>
              <tbody>
                {plugins.length === 0 ? (
                  <tr>
                    <td className="muted" colSpan={5}>
                      нет данных
                    </td>
                  </tr>
                ) : (
                  plugins.map((row) => (
                    <tr key={row.id}>
                      <td className="mono">{row.id}</td>
                      <td>{row.version}</td>
                      <td>{row.lifecycle}</td>
                      <td>{row.enabled ? 'yes' : 'no'}</td>
                      <td className="mono">{row.main_script || '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </section>
  )
}
