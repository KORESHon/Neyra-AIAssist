import { useCallback, useEffect, useState } from 'react'
import { FlaskConical, Loader2, Plus, RefreshCw, RotateCcw, Trash2, Webhook } from 'lucide-react'
import { apiDelete, apiGet, apiPatch, apiPost } from '../api'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { EmptyState } from '../components/ui/empty-state'
import { InlineFeedback } from '../components/ui/inline-feedback'
import type { ApiEnvelope, WebhookDelivery, WebhookRoute } from '../types'

export function WebhooksPage() {
  const [routes, setRoutes] = useState<WebhookRoute[]>([])
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([])
  const [eventType, setEventType] = useState('chat.turn_completed')
  const [targetUrl, setTargetUrl] = useState('http://127.0.0.1:9999/webhook')
  const [secret, setSecret] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    const [r, d] = await Promise.all([
      apiGet<ApiEnvelope<{ routes: WebhookRoute[] }>>('/v1/webhooks/out/routes'),
      apiGet<ApiEnvelope<{ deliveries: WebhookDelivery[] }>>('/v1/webhooks/deliveries'),
    ])
    setRoutes(r.data.routes ?? [])
    setDeliveries(d.data.deliveries ?? [])
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function createRoute() {
    setError(null)
    setStatus('Создаю маршрут...')
    try {
      await apiPost<ApiEnvelope<WebhookRoute>>('/v1/webhooks/out/routes', {
        event_type: eventType,
        target_url: targetUrl,
        secret,
        enabled: true,
        max_retries: 3,
      })
      setStatus('Маршрут создан')
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function toggleRoute(route: WebhookRoute, enabled: boolean) {
    setError(null)
    try {
      await apiPatch<ApiEnvelope<WebhookRoute>>(`/v1/webhooks/out/routes/${route.route_id}`, { enabled })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function deleteRoute(route: WebhookRoute) {
    setError(null)
    try {
      await apiDelete<ApiEnvelope<unknown>>(`/v1/webhooks/out/routes/${route.route_id}`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function testRoute(route: WebhookRoute) {
    setError(null)
    try {
      await apiPost<ApiEnvelope<unknown>>(`/v1/webhooks/out/test/${route.route_id}`, {
        payload: { ping: true, source: 'ui_test' },
      })
      await load()
      setStatus(`Тест отправлен: ${route.route_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function retryDelivery(deliveryId: string) {
    setError(null)
    try {
      await apiPost<ApiEnvelope<unknown>>(`/v1/webhooks/deliveries/${deliveryId}/retry`, { delay_seconds: 0 })
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <section className="grid gap-6">
      {error ? <InlineFeedback tone="error">{error}</InlineFeedback> : null}
      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
            <Webhook className="h-4 w-4 text-cyan-300" />
            Новый webhook route (outbound)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <label className="grid gap-2 text-sm text-zinc-300">
              <span>event_type</span>
              <input
                className="rounded-xl border border-zinc-700 bg-zinc-950/80 px-3 py-2 font-mono text-sm text-zinc-300 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/50"
                onChange={(e) => setEventType(e.target.value)}
                value={eventType}
              />
            </label>
            <label className="grid gap-2 text-sm text-zinc-300">
              <span>target_url</span>
              <input
                className="rounded-xl border border-zinc-700 bg-zinc-950/80 px-3 py-2 font-mono text-sm text-zinc-300 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/50"
                onChange={(e) => setTargetUrl(e.target.value)}
                value={targetUrl}
              />
            </label>
            <label className="grid gap-2 text-sm text-zinc-300">
              <span>secret (optional)</span>
              <input
                className="rounded-xl border border-zinc-700 bg-zinc-950/80 px-3 py-2 font-mono text-sm text-zinc-300 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/50"
                onChange={(e) => setSecret(e.target.value)}
                value={secret}
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              className="gap-2 border-cyan-400/40 bg-gradient-to-r from-cyan-500/80 to-blue-500/80 text-white hover:from-cyan-500 hover:to-blue-500"
              onClick={() => void createRoute()}
              type="button"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Создать маршрут
            </Button>
            <Button className="gap-2" onClick={() => void load()} type="button" variant="secondary">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Обновить
            </Button>
          </div>
          {status ? <InlineFeedback tone="success">{status}</InlineFeedback> : <p className="text-sm text-zinc-400">Создай маршрут и протестируй доставку.</p>}
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="text-base font-semibold tracking-tight text-zinc-100">Маршруты</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-xl border border-zinc-800">
            <table className="min-w-[920px] w-full text-left text-sm">
            <thead>
              <tr className="bg-zinc-900/80 text-xs uppercase tracking-wide text-zinc-400">
                <th className="px-3 py-2">id</th>
                <th className="px-3 py-2">event_type</th>
                <th className="px-3 py-2">target</th>
                <th className="px-3 py-2">enabled</th>
                <th className="px-3 py-2">actions</th>
              </tr>
            </thead>
            <tbody>
              {routes.length === 0 ? (
                <tr>
                  <td className="px-3 py-4 text-zinc-500" colSpan={5}>
                    <EmptyState
                      description="Создай первый webhook route в форме выше."
                      icon={Webhook}
                      title="Нет маршрутов"
                    />
                  </td>
                </tr>
              ) : (
                routes.map((r) => (
                  <tr key={r.route_id} className="border-t border-zinc-800/80 text-zinc-300 hover:bg-zinc-800/30">
                    <td className="px-3 py-2.5 font-mono text-sm text-zinc-400">
                      <span className="inline-block max-w-[220px] truncate align-bottom" title={r.route_id}>
                        {r.route_id}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 font-mono text-sm text-zinc-400 break-all">{r.event_type}</td>
                    <td className="px-3 py-2.5 font-mono text-sm text-zinc-400 break-all">{r.target_url}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`inline-flex items-center gap-2 rounded-full px-2 py-1 text-xs ${
                          r.enabled ? 'bg-emerald-500/15 text-emerald-200' : 'bg-zinc-700/40 text-zinc-400'
                        }`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${r.enabled ? 'bg-emerald-400' : 'bg-zinc-500'}`} />
                        {r.enabled ? 'yes' : 'no'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          aria-label={r.enabled ? 'Disable route' : 'Enable route'}
                          className="rounded-lg border border-zinc-700 bg-zinc-900/60 p-2 text-zinc-300 transition hover:border-cyan-500/60 hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
                          onClick={() => void toggleRoute(r, !r.enabled)}
                          title={r.enabled ? 'Disable' : 'Enable'}
                          type="button"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </button>
                        <button
                          aria-label="Test route"
                          className="rounded-lg border border-zinc-700 bg-zinc-900/60 p-2 text-zinc-300 transition hover:border-cyan-500/60 hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
                          onClick={() => void testRoute(r)}
                          title="Test"
                          type="button"
                        >
                          <FlaskConical className="h-3.5 w-3.5" />
                        </button>
                        <button
                          aria-label="Delete route"
                          className="rounded-lg border border-zinc-700 bg-zinc-900/60 p-2 text-zinc-300 transition hover:border-rose-500/60 hover:text-rose-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                          onClick={() => void deleteRoute(r)}
                          title="Delete"
                          type="button"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          </div>
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="text-base font-semibold tracking-tight text-zinc-100">Deliveries / DLQ</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-xl border border-zinc-800">
            <table className="min-w-[980px] w-full text-left text-sm">
            <thead>
              <tr className="bg-zinc-900/80 text-xs uppercase tracking-wide text-zinc-400">
                <th className="px-3 py-2">delivery_id</th>
                <th className="px-3 py-2">route_id</th>
                <th className="px-3 py-2">status</th>
                <th className="px-3 py-2">attempts</th>
                <th className="px-3 py-2">error</th>
                <th className="px-3 py-2">retry</th>
              </tr>
            </thead>
            <tbody>
              {deliveries.length === 0 ? (
                <tr>
                  <td className="px-3 py-4 text-zinc-500" colSpan={6}>
                    <EmptyState
                      description="Они появятся после теста или реальной отправки webhook."
                      icon={FlaskConical}
                      title="Нет доставок"
                    />
                  </td>
                </tr>
              ) : (
                deliveries.slice(0, 30).map((d) => (
                  <tr key={d.delivery_id} className="border-t border-zinc-800/80 text-zinc-300 hover:bg-zinc-800/30">
                    <td className="px-3 py-2.5 font-mono text-sm text-zinc-400">
                      <span className="inline-block max-w-[220px] truncate align-bottom" title={d.delivery_id}>
                        {d.delivery_id}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 font-mono text-sm text-zinc-400">
                      <span className="inline-block max-w-[220px] truncate align-bottom" title={d.route_id}>
                        {d.route_id}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">{d.status}</td>
                    <td className="px-3 py-2.5">{d.attempts}</td>
                    <td className="px-3 py-2.5 font-mono text-sm text-zinc-400 break-all">{d.error || '—'}</td>
                    <td className="px-3 py-2.5">
                      <button
                        aria-label="Retry delivery"
                        className="rounded-lg border border-zinc-700 bg-zinc-900/60 p-2 text-zinc-300 transition hover:border-cyan-500/60 hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
                        onClick={() => void retryDelivery(d.delivery_id)}
                        title="retry"
                        type="button"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          </div>
        </CardContent>
      </Card>
    </section>
  )
}
