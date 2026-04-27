import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { apiGetText } from '../api'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'

type Mode = 'swagger' | 'redoc'
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
  const src = mode === 'swagger' ? '/docs' : '/redoc'

  useEffect(() => {
    let cancelled = false
    async function loadDoc() {
      try {
        setError('')
        const text = await apiGetText(`/v1/docs/markdown/${doc}`)
        if (!cancelled) setMarkdown(text)
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e))
          setMarkdown('')
        }
      }
    }
    void loadDoc()
    return () => {
      cancelled = true
    }
  }, [doc])

  return (
    <section className="grid gap-4">
      <Card className="col-span-2">
        <CardHeader>
          <CardTitle>Встроенная API документация</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="actions">
            <Button onClick={() => setMode('swagger')} variant={mode === 'swagger' ? 'default' : 'secondary'}>
              Swagger
            </Button>
            <Button onClick={() => setMode('redoc')} variant={mode === 'redoc' ? 'default' : 'secondary'}>
              ReDoc
            </Button>
            <a className="btn secondary link-btn" href="/openapi.json" rel="noreferrer" target="_blank">
              OpenAPI JSON
            </a>
          </div>
        </CardContent>
      </Card>
      <Card className="docs-frame-wrap">
        <iframe className="docs-frame" src={src} title="Neyra API docs" />
      </Card>
      <Card className="docs-md-wrap">
        <CardHeader>
          <CardTitle>Документация (Markdown)</CardTitle>
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
          {error ? <div className="banner error">{error}</div> : null}
          <article className="prose prose-invert max-w-none rounded-lg border border-border bg-background/50 p-3">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown || '—'}</ReactMarkdown>
          </article>
        </CardContent>
      </Card>
    </section>
  )
}
