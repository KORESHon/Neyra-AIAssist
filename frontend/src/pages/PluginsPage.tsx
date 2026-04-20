import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiPatch, apiPost, apiPut } from '../api'
import type { ApiEnvelope, PluginRow } from '../types'

type PluginDetails = {
  plugin: PluginRow
  config: Record<string, unknown>
}

export function PluginsPage() {
  const [plugins, setPlugins] = useState<PluginRow[]>([])
  const [selected, setSelected] = useState<string>('')
  const [details, setDetails] = useState<PluginDetails | null>(null)
  const [configText, setConfigText] = useState('{}')
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  const loadPlugins = useCallback(async () => {
    const r = await apiGet<ApiEnvelope<{ plugins: PluginRow[] }>>('/v1/plugins')
    setPlugins(r.data.plugins ?? [])
    if (!selected && r.data.plugins?.length) {
      setSelected(r.data.plugins[0].id)
    }
  }, [selected])

  const loadDetails = useCallback(async (pluginId: string) => {
    const r = await apiGet<ApiEnvelope<PluginDetails>>(`/v1/plugins/${pluginId}`)
    setDetails(r.data)
    setConfigText(JSON.stringify(r.data.config ?? {}, null, 2))
  }, [])

  useEffect(() => {
    void loadPlugins()
  }, [loadPlugins])

  useEffect(() => {
    if (selected) void loadDetails(selected)
  }, [selected, loadDetails])

  async function togglePlugin(enabled: boolean) {
    if (!selected) return
    setError(null)
    setStatus('Применение...')
    try {
      const r = await apiPatch<ApiEnvelope<{ operation_id: string }>>(`/v1/plugins/${selected}`, { enabled })
      setStatus(`Готово: ${r.data.operation_id}`)
      await loadPlugins()
      await loadDetails(selected)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function saveConfig() {
    if (!selected) return
    setError(null)
    setStatus('Сохраняю config...')
    try {
      const parsed = JSON.parse(configText) as Record<string, unknown>
      await apiPut<ApiEnvelope<{ operation_id: string }>>(`/v1/plugins/${selected}/config`, {
        config: parsed,
      })
      setStatus('Config сохранён')
      await loadDetails(selected)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function invokePlugin() {
    if (!selected) return
    setError(null)
    setStatus('Выполняю invoke...')
    try {
      await apiPost<ApiEnvelope<unknown>>(`/v1/plugins/${selected}/invoke`, { payload: {} })
      setStatus('Invoke выполнен')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <section className="grid">
      <article className="card">
        <h2>Плагины</h2>
        <select className="select" onChange={(e) => setSelected(e.target.value)} value={selected}>
          {plugins.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id} ({p.enabled ? 'enabled' : 'disabled'})
            </option>
          ))}
        </select>
        <div className="stack">
          <button className="btn" onClick={() => void togglePlugin(true)} type="button">
            Включить
          </button>
          <button className="btn secondary" onClick={() => void togglePlugin(false)} type="button">
            Выключить
          </button>
          <button className="btn secondary" onClick={() => void invokePlugin()} type="button">
            Invoke (on_demand)
          </button>
        </div>
        <p className="muted small">{status || '—'}</p>
      </article>

      <article className="card">
        <h2>Состояние</h2>
        <pre className="json">{details ? JSON.stringify(details.plugin, null, 2) : '—'}</pre>
      </article>

      <article className="card wide">
        <h2>Конфиг плагина</h2>
        {error ? <div className="banner error">{error}</div> : null}
        <textarea className="json-input" onChange={(e) => setConfigText(e.target.value)} value={configText} />
        <div className="actions">
          <button className="btn" onClick={() => void saveConfig()} type="button">
            Сохранить config
          </button>
          <button
            className="btn secondary"
            onClick={() => selected && void loadDetails(selected)}
            type="button"
          >
            Перезагрузить из файла
          </button>
        </div>
      </article>
    </section>
  )
}
