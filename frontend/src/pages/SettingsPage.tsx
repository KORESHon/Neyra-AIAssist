import { useState } from 'react'
import { apiPost, getToken, setToken } from '../api'
import type { ApiEnvelope } from '../types'

export function SettingsPage() {
  const [token, setTokenInput] = useState(getToken())
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState('0.8')
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function applyRuntime() {
    setError(null)
    setStatus('Применение...')
    try {
      await apiPost<ApiEnvelope<unknown>>('/v1/config/update', {
        updates: {
          'openrouter.model': model,
          'openrouter.temperature': Number(temperature),
        },
      })
      setStatus('Настройки применены')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <section className="grid">
      <article className="card">
        <h2>Bearer</h2>
        <label className="token-field">
          <span>Токен API (локальное хранение в браузере)</span>
          <input
            autoComplete="off"
            onChange={(e) => setTokenInput(e.target.value)}
            placeholder="опционально"
            type="password"
            value={token}
          />
        </label>
        <div className="actions">
          <button
            className="btn"
            onClick={() => {
              setToken(token)
              setStatus('Токен сохранён')
            }}
            type="button"
          >
            Сохранить токен
          </button>
        </div>
      </article>
      <article className="card">
        <h2>Runtime config (allowlist)</h2>
        <label className="token-field">
          <span>openrouter.model</span>
          <input onChange={(e) => setModel(e.target.value)} placeholder="например qwen/qwen3-235b-a22b-2507" value={model} />
        </label>
        <label className="token-field">
          <span>openrouter.temperature</span>
          <input onChange={(e) => setTemperature(e.target.value)} value={temperature} />
        </label>
        <div className="actions">
          <button className="btn" onClick={() => void applyRuntime()} type="button">
            Применить
          </button>
        </div>
        {error ? <div className="banner error">{error}</div> : null}
        <p className="muted small">{status || '—'}</p>
      </article>
    </section>
  )
}
