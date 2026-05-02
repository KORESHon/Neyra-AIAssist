import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { BookOpenText, ExternalLink, FileText } from 'lucide-react'
import remarkGfm from 'remark-gfm'
import { apiGetText } from '../api'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { EmptyState } from '../components/ui/empty-state'
import { InlineFeedback } from '../components/ui/inline-feedback'
import { Skeleton } from '../components/ui/skeleton'

type Mode = 'swagger'
type DocKey = 'readme-ru' | 'readme-en' | 'help-ru' | 'help-en' | 'docs-ru-index' | 'docs-en-index'

const DOC_OPTIONS: Array<{ key: DocKey; label: string }> = [
  { key: 'readme-ru', label: 'README-RU' },
  { key: 'readme-en', label: 'README-EN' },
  { key: 'help-ru', label: 'HELP-RU' },
  { key: 'help-en', label: 'HELP-EN' },
  { key: 'docs-ru-index', label: 'DOCS RU INDEX' },
  { key: 'docs-en-index', label: 'DOCS EN INDEX' },
]

export function DocsPage() {
  const [mode, setMode] = useState<Mode>('swagger')
  const [doc, setDoc] = useState<DocKey>('readme-ru')
  const [markdown, setMarkdown] = useState<string>('Загрузка...')
  const [error, setError] = useState<string>('')
  const [loadingDoc, setLoadingDoc] = useState(false)
  const src = mode === 'swagger' ? '/docs' : '/docs'

  useEffect(() => {
    let cancelled = false
    async function loadDoc() {
      try {
        setError('')
        setLoadingDoc(true)
        const text = await apiGetText(`/v1/docs/markdown/${doc}`)
        if (!cancelled) setMarkdown(text)
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setMarkdown('')
        }
      } finally {
        if (!cancelled) setLoadingDoc(false)
      }
    }
    void loadDoc()
    return () => {
      cancelled = true
    }
  }, [doc])

  return (
    <section className="grid gap-6">
      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-zinc-100">
            <BookOpenText className="h-4 w-4 text-cyan-300" />
            Встроенная API документация
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-2 md:gap-3">
            <Button onClick={() => setMode('swagger')} variant={mode === 'swagger' ? 'default' : 'secondary'}>
              Swagger
            </Button>
            <a
              className="inline-flex items-center gap-2 rounded-md border border-zinc-700 bg-zinc-900/70 px-3 py-2 text-sm text-zinc-300 transition hover:border-cyan-500/50 hover:text-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
              href="/openapi.json"
              rel="noreferrer"
              target="_blank"
            >
              OpenAPI JSON
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          </div>
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardContent className="p-4">
          <div className="rounded-xl bg-zinc-100 p-4">
            <iframe className="min-h-[600px] w-full rounded-lg bg-white" src={src} title="Neyra API docs" />
          </div>
        </CardContent>
      </Card>

      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="text-base font-semibold tracking-tight text-zinc-100">Документация (Markdown)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-3 flex flex-wrap gap-2">
            {DOC_OPTIONS.map((o) => (
              <Button
                key={o.key}
                onClick={() => setDoc(o.key)}
                size="sm"
                variant={doc === o.key ? 'default' : 'secondary'}
              >
                {o.label}
              </Button>
            ))}
          </div>
          {error ? <InlineFeedback tone="error">{error}</InlineFeedback> : null}
          {loadingDoc ? (
            <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-950/60 p-4">
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : markdown ? (
            <article className="prose prose-zinc prose-invert max-w-none rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 prose-headings:tracking-tight prose-headings:text-zinc-100 prose-p:leading-7 prose-p:text-zinc-300 prose-li:text-zinc-300 prose-code:text-cyan-300 prose-blockquote:border-zinc-600 prose-blockquote:text-zinc-300 prose-pre:border prose-pre:border-zinc-700 prose-pre:bg-zinc-900/90">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
            </article>
          ) : (
            <EmptyState
              description="Проверь backend endpoint `/v1/docs/markdown/*` или выбери другой раздел."
              icon={FileText}
              title="Документация недоступна"
            />
          )}
        </CardContent>
      </Card>
    </section>
  )
}
