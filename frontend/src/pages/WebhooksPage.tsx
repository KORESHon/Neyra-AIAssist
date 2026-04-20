import { useCallback, useEffect, useState } from 'react'
import { apiDelete, apiGet, apiPatch, apiPost } from '../api'
import type { ApiEnvelope, WebhookDelivery, WebhookRoute } from '../types'

export function WebhooksPage() {
  const [routes, setRoutes] = useState<WebhookRoute[]>([])
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([])
  const [eventType, setEventType] = useState('chat.turn_completed')
  const [targetUrl, setTargetUrl] = useState('http://127.0.0.1:9999/webhook')
  const [secret, setSecret] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const [r, d] = await Promise.all([
      apiGet<ApiEnvelope<{ routes: WebhookRoute[] }>>('/v1/webhooks/out/routes'),
      apiGet<ApiEnvelope<{ deliveries: WebhookDelivery[] }>>('/v1/webhooks/deliveries'),
    ])
    setRoutes(r.data.routes ?? [])
    setDeliveries(d.data.deliveries ?? [])
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
    <section className="stack">
      {error ? <div className="banner error">{error}</div> : null}
      <article className="card">
        <h2>Новый webhook route (outbound)</h2>
        <div className="form-grid">
          <label className="token-field">
            <span>event_type</span>
            <input onChange={(e) => setEventType(e.target.value)} value={eventType} />
          </label>
          <label className="token-field">
            <span>target_url</span>
            <input onChange={(e) => setTargetUrl(e.target.value)} value={targetUrl} />
          </label>
          <label className="token-field">
            <span>secret (optional)</span>
            <input onChange={(e) => setSecret(e.target.value)} value={secret} />
          </label>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => void createRoute()} type="button">
            Создать маршрут
          </button>
          <button className="btn secondary" onClick={() => void load()} type="button">
            Обновить
          </button>
        </div>
        <p className="muted small">{status || '—'}</p>
      </article>

      <article className="card">
        <h2>Маршруты</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>id</th>
                <th>event_type</th>
                <th>target</th>
                <th>enabled</th>
                <th>actions</th>
              </tr>
            </thead>
            <tbody>
              {routes.length === 0 ? (
                <tr>
                  <td className="muted" colSpan={5}>
                    нет маршрутов
                  </td>
                </tr>
              ) : (
                routes.map((r) => (
                  <tr key={r.route_id}>
                    <td className="mono">{r.route_id}</td>
                    <td className="mono">{r.event_type}</td>
                    <td className="mono small">{r.target_url}</td>
                    <td>{r.enabled ? 'yes' : 'no'}</td>
                    <td className="actions-inline">
                      <button className="btn tiny" onClick={() => void toggleRoute(r, !r.enabled)} type="button">
                        {r.enabled ? 'Disable' : 'Enable'}
                      </button>
                      <button className="btn tiny secondary" onClick={() => void testRoute(r)} type="button">
                        Test
                      </button>
                      <button className="btn tiny secondary" onClick={() => void deleteRoute(r)} type="button">
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>

      <article className="card">
        <h2>Deliveries / DLQ</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>delivery_id</th>
                <th>route_id</th>
                <th>status</th>
                <th>attempts</th>
                <th>error</th>
                <th>retry</th>
              </tr>
            </thead>
            <tbody>
              {deliveries.length === 0 ? (
                <tr>
                  <td className="muted" colSpan={6}>
                    нет доставок
                  </td>
                </tr>
              ) : (
                deliveries.slice(0, 30).map((d) => (
                  <tr key={d.delivery_id}>
                    <td className="mono small">{d.delivery_id}</td>
                    <td className="mono">{d.route_id}</td>
                    <td>{d.status}</td>
                    <td>{d.attempts}</td>
                    <td className="mono small">{d.error || '—'}</td>
                    <td>
                      <button className="btn tiny secondary" onClick={() => void retryDelivery(d.delivery_id)} type="button">
                        retry
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  )
}
