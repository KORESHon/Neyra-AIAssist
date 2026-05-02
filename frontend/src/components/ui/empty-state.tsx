import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

type EmptyStateProps = {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-5 py-6 text-center">
      <Icon className="mx-auto mb-3 h-8 w-8 text-zinc-500" />
      <p className="text-sm font-semibold tracking-tight text-zinc-200">{title}</p>
      <p className="mt-1 text-sm text-zinc-400">{description}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  )
}
