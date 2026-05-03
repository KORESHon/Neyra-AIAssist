import { useCallback, useEffect, useState } from 'react'
import { Activity, Brain, Database, RefreshCw, Wallet } from 'lucide-react'
import { apiGet, apiPost } from '../api'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { EmptyState } from '../components/ui/empty-state'
import { InlineFeedback } from '../components/ui/inline-feedback'
import { cn } from '../lib/utils'
import type { ApiEnvelope, BalanceData, HealthData, MemoryPolicies, MemoryStats, PluginRow } from '../types'

export function DashboardPage() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthData | null>(null)
  const [memory, setMemory] = useState<MemoryStats | null>(null)
  const [plugins, setPlugins] = useState<PluginRow[]>([])
  const [balance, setBalance] = useState<BalanceData | null>(null)
  const [memPolicies, setMemPolicies] = useState<MemoryPolicies | null>(null)
  const [ltmBusy, setLtmBusy] = useState(false)
  const [ltmMsg, setLtmMsg] = useState<string | null>(null)
  const [pruneDays, setPruneDays] = useState('90')
  const [sumDays, setSumDays] = useState('60')
  const [sumCompress, setSumCompress] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [h, m, p, b, pol] = await Promise.all([
        apiGet<ApiEnvelope<HealthData>>('/v1/health'),
        apiGet<ApiEnvelope<MemoryStats>>('/v1/memory/stats'),
        apiGet<ApiEnvelope<{ plugins: PluginRow[] }>>('/v1/plugins'),
        apiGet<ApiEnvelope<BalanceData>>('/v1/llm/balance'),
        apiGet<ApiEnvelope<MemoryPolicies>>('/v1/memory/policies'),
      ])
      setHealth(h.data)
      setMemory(m.data)
      setPlugins(p.data.plugins ?? [])
      setBalance(b.data)
      setMemPolicies(pol.data)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function runLtm(
    path: '/v1/memory/prune' | '/v1/memory/summarize',
    body: Record<string, unknown>,
  ) {
    setLtmBusy(true)
    setLtmMsg(null)
    try {
      const r = await apiPost<ApiEnvelope<unknown>>(path, body)
      setLtmMsg(JSON.stringify(r.data, null, 2))
      await load()
    } catch (e) {
      setLtmMsg(e instanceof Error ? e.message : String(e))
    } finally {
      setLtmBusy(false)
    }
  }

  const healthStatus = String((health?.status as string | undefined) ?? 'unknown')
  const healthUptime = String((health?.uptime_seconds as string | number | undefined) ?? '—')
  const healthVersion = String((health?.version as string | number | undefined) ?? '—')
  const healthStatusLower = healthStatus.toLowerCase()
  const healthStatusTone = healthStatusLower === 'ok' || healthStatusLower === 'online' || healthStatusLower === 'healthy'
    ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200'
    : healthStatusLower === 'unknown'
      ? 'border-zinc-600/50 bg-zinc-700/20 text-zinc-300'
      : 'border-amber-400/30 bg-amber-500/10 text-amber-200'
  const healthDotTone = healthStatusLower === 'ok' || healthStatusLower === 'online' || healthStatusLower === 'healthy'
    ? 'bg-emerald-400'
    : healthStatusLower === 'unknown'
      ? 'bg-zinc-400'
      : 'bg-amber-400'

  return (
    <section className="grid gap-6">
      <div className="flex justify-end">
        <Button
          className="gap-2 border-cyan-400/40 bg-gradient-to-r from-cyan-500/80 to-blue-500/80 text-white hover:from-cyan-500 hover:to-blue-500"
          disabled={loading}
          onClick={() => void load()}
          type="button"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Обновление…' : 'Обновить данные'}
        </Button>
      </div>
      {error ? <InlineFeedback tone="error">{error}</InlineFeedback> : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
              <Activity className="h-4 w-4 text-cyan-300" />
              Health
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className={cn('inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm', healthStatusTone)}>
              <span className={cn('h-2 w-2 rounded-full', healthDotTone)} />
              Status: {healthStatus}
            </div>
            <div className="grid gap-2 text-sm text-zinc-300">
              <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/70 px-3 py-2">
                <span className="text-zinc-400">Uptime</span>
                <span className="font-mono text-zinc-200">{healthUptime}s</span>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/70 px-3 py-2">
                <span className="text-zinc-400">Version</span>
                <span className="font-mono text-zinc-200">{healthVersion}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
              <Brain className="h-4 w-4 text-cyan-300" />
              Память
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="h-full rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">Краткая память</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-zinc-100">{memory?.short_memory_size ?? '—'}</p>
              </div>
              <div className="h-full rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">RAG</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-zinc-100">{memory?.long_memory_records ?? '—'}</p>
              </div>
              <div className="h-full rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">PeopleDB</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-zinc-100">{memory?.people_records ?? '—'}</p>
              </div>
            </div>
            <div className="mt-6 border-t border-zinc-800 pt-6">
              <p className="mb-3 text-sm font-medium text-zinc-200">Обслуживание LTM</p>
              <p className="mb-4 text-xs text-zinc-500">
                Нужен токен уровня maint или admin. Политики и расписание авто-джобов — ниже.
              </p>
              <div className="mb-4 grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs text-zinc-400">
                  Prune: старше (дней)
                  <input
                    className="rounded-lg border border-zinc-700 bg-zinc-950/80 px-2 py-1.5 font-mono text-sm text-zinc-200"
                    onChange={(e) => setPruneDays(e.target.value)}
                    type="text"
                    value={pruneDays}
                  />
                </label>
                <label className="grid gap-1 text-xs text-zinc-400">
                  Summarize: старше (дней)
                  <input
                    className="rounded-lg border border-zinc-700 bg-zinc-950/80 px-2 py-1.5 font-mono text-sm text-zinc-200"
                    onChange={(e) => setSumDays(e.target.value)}
                    type="text"
                    value={sumDays}
                  />
                </label>
              </div>
              <label className="mb-4 flex cursor-pointer items-center gap-2 text-sm text-zinc-400">
                <input
                  checked={sumCompress}
                  className="rounded border-zinc-600"
                  onChange={(e) => setSumCompress(e.target.checked)}
                  type="checkbox"
                />
                Summarize: сжатие через LLM (digest в RAG)
              </label>
              <div className="flex flex-wrap gap-2">
                <Button
                  className="border-zinc-600 bg-zinc-800 text-zinc-100 hover:bg-zinc-700"
                  disabled={ltmBusy}
                  onClick={() =>
                    void runLtm('/v1/memory/prune', {
                      older_than_days: Number(pruneDays) || 90,
                      dry_run: true,
                    })
                  }
                  type="button"
                >
                  Prune (dry-run)
                </Button>
                <Button
                  className="border-amber-500/40 bg-amber-900/40 text-amber-100 hover:bg-amber-900/60"
                  disabled={ltmBusy}
                  onClick={() =>
                    void runLtm('/v1/memory/prune', {
                      older_than_days: Number(pruneDays) || 90,
                      dry_run: false,
                    })
                  }
                  type="button"
                >
                  Prune
                </Button>
                <Button
                  className="border-zinc-600 bg-zinc-800 text-zinc-100 hover:bg-zinc-700"
                  disabled={ltmBusy}
                  onClick={() =>
                    void runLtm('/v1/memory/summarize', {
                      older_than_days: Number(sumDays) || 60,
                      dry_run: true,
                      max_entries: 500,
                      compress_with_llm: sumCompress,
                    })
                  }
                  type="button"
                >
                  Summarize (dry-run)
                </Button>
                <Button
                  className="border-cyan-500/40 bg-cyan-900/30 text-cyan-100 hover:bg-cyan-900/50"
                  disabled={ltmBusy}
                  onClick={() =>
                    void runLtm('/v1/memory/summarize', {
                      older_than_days: Number(sumDays) || 60,
                      dry_run: false,
                      max_entries: 500,
                      compress_with_llm: sumCompress,
                    })
                  }
                  type="button"
                >
                  Summarize
                </Button>
              </div>
              {ltmMsg ? (
                <pre className="mt-4 max-h-48 overflow-auto rounded-lg border border-zinc-800 bg-zinc-950/80 p-3 text-left text-xs text-zinc-300">
                  {ltmMsg}
                </pre>
              ) : null}
              {memPolicies ? (
                <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950/40 p-3 text-xs text-zinc-500">
                  <p className="mb-1 font-mono text-zinc-400">/v1/memory/policies</p>
                  <p>archive: {memPolicies.ltm_archive_dir ?? '—'} · embed: {memPolicies.embedding_model ?? '—'}</p>
                  <p className="mt-1 break-all">
                    auto_prune: {JSON.stringify(memPolicies.ltm_auto_prune ?? {})}
                  </p>
                  <p className="mt-1 break-all">
                    auto_summarize: {JSON.stringify(memPolicies.ltm_auto_summarize ?? {})}
                  </p>
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
              <Wallet className="h-4 w-4 text-fuchsia-300" />
              Баланс LLM
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {balance?.hint ? <p className="text-sm text-zinc-400">{balance.hint}</p> : null}
            <div className="grid gap-4 md:grid-cols-4">
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">Provider</p>
                <p className="mt-2 text-lg font-semibold tracking-tight text-zinc-100">{balance?.provider ?? '—'}</p>
              </div>
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">Остаток</p>
                <p className="mt-2 text-lg font-semibold tracking-tight text-zinc-100">{balance?.limit_remaining ?? '—'}</p>
              </div>
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">Лимит</p>
                <p className="mt-2 text-lg font-semibold tracking-tight text-zinc-100">{balance?.limit ?? '—'}</p>
              </div>
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">Usage total</p>
                <p className="mt-2 text-lg font-semibold tracking-tight text-zinc-100">{balance?.usage ?? '—'}</p>
              </div>
            </div>
            <p className="text-sm text-zinc-400">
              Сутки/неделя/месяц:{' '}
              <span className="font-mono text-zinc-300">
                {balance?.usage_daily ?? '—'} / {balance?.usage_weekly ?? '—'} / {balance?.usage_monthly ?? '—'}
              </span>
            </p>
          </CardContent>
        </Card>

        <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
              <Database className="h-4 w-4 text-cyan-300" />
              Плагины (read-only обзор)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-xl border border-zinc-800">
              <table className="min-w-[760px] w-full text-left text-sm">
              <thead>
                <tr className="bg-zinc-900/80 text-xs uppercase tracking-wide text-zinc-400">
                  <th className="px-3 py-2">id</th>
                  <th className="px-3 py-2">версия</th>
                  <th className="px-3 py-2">lifecycle</th>
                  <th className="px-3 py-2">enabled</th>
                  <th className="px-3 py-2">script</th>
                </tr>
              </thead>
              <tbody>
                {plugins.length === 0 ? (
                  <tr>
                    <td className="px-3 py-4 text-zinc-500" colSpan={5}>
                      <EmptyState
                        action={
                          <a
                            className="inline-flex items-center rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 transition hover:border-cyan-500/50 hover:text-cyan-100"
                            href="/api-docs"
                          >
                            Перейти к документации
                          </a>
                        }
                        description="Проверь запуск ядра и доступность `/v1/plugins`."
                        icon={Database}
                        title="Нет данных по плагинам"
                      />
                    </td>
                  </tr>
                ) : (
                  plugins.map((row) => (
                    <tr key={row.id} className="border-t border-zinc-800/80 text-zinc-300 hover:bg-zinc-800/30">
                      <td className="px-3 py-2 font-mono text-sm text-zinc-400">
                        <span className="inline-block max-w-[180px] truncate align-bottom" title={row.id}>
                          {row.id}
                        </span>
                      </td>
                      <td className="px-3 py-2">{row.version}</td>
                      <td className="px-3 py-2">{row.lifecycle}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`inline-flex items-center gap-2 rounded-full px-2 py-1 text-xs ${
                            row.enabled ? 'bg-emerald-500/15 text-emerald-200' : 'bg-zinc-700/40 text-zinc-400'
                          }`}
                        >
                          <span className={`h-1.5 w-1.5 rounded-full ${row.enabled ? 'bg-emerald-400' : 'bg-zinc-500'}`} />
                          {row.enabled ? 'enabled' : 'disabled'}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-sm text-zinc-400 break-all">{row.main_script || '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
