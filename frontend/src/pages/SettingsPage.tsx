import { useState } from 'react'
import { KeyRound, Loader2, SlidersHorizontal, Sparkles } from 'lucide-react'
import { apiPost, getToken, setToken } from '../api'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { InlineFeedback } from '../components/ui/inline-feedback'
import type { ApiEnvelope } from '../types'

export function SettingsPage() {
  const [token, setTokenInput] = useState(getToken())
  const [model, setModel] = useState('')
  const [temperature, setTemperature] = useState('0.8')
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function applyRuntime() {
    setError(null)
    setStatus('Применение...')
    setLoading(true)
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
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="grid gap-6 lg:grid-cols-2">
      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
            <KeyRound className="h-4 w-4 text-cyan-300" />
            Bearer Token
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="grid gap-2 text-sm text-zinc-300">
            <span>Токен API (локальное хранение в браузере)</span>
            <input
              autoComplete="off"
              className="rounded-xl border border-zinc-700 bg-zinc-950/80 px-3 py-2 font-mono text-sm text-zinc-300 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/50"
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="опционально"
              type="password"
              value={token}
            />
          </label>
          <Button
            className="border-cyan-400/40 bg-gradient-to-r from-cyan-500/80 to-blue-500/80 text-white hover:from-cyan-500 hover:to-blue-500"
            onClick={() => {
              setToken(token)
              setStatus('Токен сохранён')
            }}
            type="button"
          >
            Сохранить токен
          </Button>
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
            <SlidersHorizontal className="h-4 w-4 text-fuchsia-300" />
            Runtime config (allowlist)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="grid gap-2 text-sm text-zinc-300">
            <span>openrouter.model</span>
            <input
              className="rounded-xl border border-zinc-700 bg-zinc-950/80 px-3 py-2 text-sm text-zinc-300 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/50"
              onChange={(e) => setModel(e.target.value)}
              placeholder="например qwen/qwen3-235b-a22b-2507"
              value={model}
            />
          </label>
          <label className="grid gap-2 text-sm text-zinc-300">
            <span>openrouter.temperature</span>
            <input
              className="rounded-xl border border-zinc-700 bg-zinc-950/80 px-3 py-2 font-mono text-sm text-zinc-300 outline-none transition focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/50"
              onChange={(e) => setTemperature(e.target.value)}
              value={temperature}
            />
            <span className="text-xs text-zinc-500">Рекомендуемый диапазон: 0.0 - 1.5</span>
          </label>
          <Button
            className="gap-2 border-cyan-400/40 bg-gradient-to-r from-cyan-500/80 to-blue-500/80 text-white hover:from-cyan-500 hover:to-blue-500"
            disabled={loading}
            onClick={() => void applyRuntime()}
            type="button"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Применить
          </Button>
          {error ? <InlineFeedback tone="error">{error}</InlineFeedback> : null}
          {status ? <InlineFeedback tone="success">{status}</InlineFeedback> : <p className="text-sm text-zinc-400">Измени параметры и нажми "Применить".</p>}
        </CardContent>
      </Card>
    </section>
  )
}
