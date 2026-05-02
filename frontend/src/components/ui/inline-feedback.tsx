import { AlertCircle, CheckCircle2, Info } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

type Tone = 'error' | 'success' | 'info'

const toneStyles: Record<Tone, string> = {
  error: 'border-rose-500/40 bg-rose-500/10 text-rose-200',
  success: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200',
  info: 'border-cyan-500/35 bg-cyan-500/10 text-cyan-100',
}

const toneIcon = {
  error: AlertCircle,
  success: CheckCircle2,
  info: Info,
} satisfies Record<Tone, typeof Info>

type InlineFeedbackProps = {
  tone: Tone
  children: ReactNode
  className?: string
}

export function InlineFeedback({ tone, children, className }: InlineFeedbackProps) {
  const Icon = toneIcon[tone]
  return (
    <div className={cn('flex items-start gap-2 rounded-xl border px-4 py-3 text-sm', toneStyles[tone], className)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div>{children}</div>
    </div>
  )
}
