export type ApiEnvelope<T> = {
  ok: boolean
  trace_id: string
  data: T
}

export type HealthData = Record<string, unknown>

export type MemoryStats = {
  short_memory_size: number
  long_memory_records: number
  people_records: number
}

export type PluginRow = {
  id: string
  name: string
  description: string
  version: string
  enabled: boolean
  lifecycle: string
  cli_modes: string[]
  main_script: string
  plugin_dir: string
}

export type BalanceData = {
  provider: string
  hint?: string
  limit?: number | null
  limit_remaining?: number | null
  usage?: number
  usage_daily?: number
  usage_weekly?: number
  usage_monthly?: number
  label?: string
}

export type WebhookRoute = {
  route_id: string
  event_type: string
  target_url: string
  enabled: boolean
  max_retries: number
  created_at: string
  updated_at: string
  secret_masked?: string
}

export type WebhookDelivery = {
  delivery_id: string
  route_id: string
  event_type: string
  status: string
  attempts: number
  status_code?: number
  error?: string
  created_at: string
  updated_at: string
}
