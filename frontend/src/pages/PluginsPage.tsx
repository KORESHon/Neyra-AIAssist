import { useCallback, useEffect, useState } from 'react'
import { FileCode2, Play, RefreshCw, Settings2, ToggleLeft, ToggleRight } from 'lucide-react'
import { apiGet, apiPatch, apiPost, apiPut } from '../api'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { EmptyState } from '../components/ui/empty-state'
import { InlineFeedback } from '../components/ui/inline-feedback'
import { Skeleton } from '../components/ui/skeleton'
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
  const [loadingPlugins, setLoadingPlugins] = useState(false)
  const [loadingDetails, setLoadingDetails] = useState(false)

  const loadPlugins = useCallback(async () => {
    setLoadingPlugins(true)
    const r = await apiGet<ApiEnvelope<{ plugins: PluginRow[] }>>('/v1/plugins')
    setPlugins(r.data.plugins ?? [])
    if (!selected && r.data.plugins?.length) {
      setSelected(r.data.plugins[0].id)
    }
    setLoadingPlugins(false)
  }, [selected])

  const loadDetails = useCallback(async (pluginId: string) => {
    setLoadingDetails(true)
    const r = await apiGet<ApiEnvelope<PluginDetails>>(`/v1/plugins/${pluginId}`)
    setDetails(r.data)
    setConfigText(JSON.stringify(r.data.config ?? {}, null, 2))
    setLoadingDetails(false)
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
    <section className="grid gap-6 lg:grid-cols-[minmax(280px,300px)_1fr]">
      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
            <Settings2 className="h-4 w-4 text-cyan-300" />
            Плагины
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {loadingPlugins ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full rounded-xl" />
              <Skeleton className="h-10 w-full rounded-xl" />
              <Skeleton className="h-10 w-full rounded-xl" />
            </div>
          ) : null}
          {!loadingPlugins ? plugins.map((p) => (
            <button
              key={p.id}
              className={`flex w-full items-center justify-between rounded-xl border px-3 py-2 text-left transition ${
                selected === p.id
                  ? 'border-cyan-400/50 bg-cyan-500/10 text-cyan-100'
                  : 'border-zinc-800 bg-zinc-900/70 text-zinc-300 hover:border-zinc-700'
              }`}
              onClick={() => setSelected(p.id)}
              type="button"
            >
              <span className="font-mono text-sm">{p.id}</span>
              <span className="inline-flex items-center gap-2 text-xs text-zinc-400">
                <span className={`h-2 w-2 rounded-full ${p.enabled ? 'bg-emerald-400' : 'bg-zinc-500'}`} />
                {p.enabled ? 'enabled' : 'disabled'}
              </span>
            </button>
          )) : null}
          {!loadingPlugins && plugins.length === 0 ? (
            <EmptyState
              description="Проверь доступность `/v1/plugins` или активные плагины в конфиге."
              icon={Settings2}
              title="Нет доступных плагинов"
            />
          ) : null}
        </CardContent>
      </Card>

      <div className="grid min-w-0 gap-6">
        <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-base font-semibold tracking-tight text-zinc-100">Управление плагином</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-4">
              <button
                aria-label="toggle plugin"
                className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 ${
                  details?.plugin.enabled
                    ? 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200'
                    : 'border-zinc-700 bg-zinc-800/60 text-zinc-400'
                }`}
                onClick={() => void togglePlugin(!Boolean(details?.plugin.enabled))}
                type="button"
              >
                {details?.plugin.enabled ? <ToggleRight className="h-5 w-5" /> : <ToggleLeft className="h-5 w-5" />}
                {details?.plugin.enabled ? 'Enabled' : 'Disabled'}
              </button>
              <Button className="gap-2" onClick={() => void invokePlugin()} type="button" variant="secondary">
                <Play className="h-4 w-4" />
                Invoke (on_demand)
              </Button>
              <Button className="gap-2" onClick={() => selected && void loadDetails(selected)} type="button" variant="secondary">
                <RefreshCw className="h-4 w-4" />
                Обновить состояние
              </Button>
            </div>
            {status ? <InlineFeedback tone="success">{status}</InlineFeedback> : <p className="text-sm text-zinc-400">Выбери плагин в левом меню.</p>}
          </CardContent>
        </Card>

        <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
              <FileCode2 className="h-4 w-4 text-cyan-300" />
              Состояние
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingDetails ? <Skeleton className="h-36 w-full rounded-xl" /> : null}
            <pre className="max-w-full overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-950/80 p-3 font-mono text-sm text-zinc-400">
              {details ? JSON.stringify(details.plugin, null, 2) : '—'}
            </pre>
          </CardContent>
        </Card>

        <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="text-base font-semibold tracking-tight text-zinc-100">Конфиг плагина</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {error ? <InlineFeedback tone="error">{error}</InlineFeedback> : null}
            <textarea
              className="min-h-[400px] w-full resize-y rounded-xl border border-zinc-700 bg-zinc-950/80 p-3 font-mono text-sm text-zinc-300 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/50"
              onChange={(e) => setConfigText(e.target.value)}
              value={configText}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                className="border-cyan-400/40 bg-gradient-to-r from-cyan-500/80 to-blue-500/80 text-white hover:from-cyan-500 hover:to-blue-500"
                onClick={() => void saveConfig()}
                type="button"
              >
                Сохранить config
              </Button>
              <Button onClick={() => selected && void loadDetails(selected)} type="button" variant="secondary">
                Перезагрузить из файла
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
