import { useState } from 'react'

type Mode = 'swagger' | 'redoc'

export function DocsPage() {
  const [mode, setMode] = useState<Mode>('swagger')
  const src = mode === 'swagger' ? '/docs' : '/redoc'
  return (
    <section className="stack">
      <article className="card">
        <h2>Встроенная API документация</h2>
        <div className="actions">
          <button className={mode === 'swagger' ? 'btn' : 'btn secondary'} onClick={() => setMode('swagger')} type="button">
            Swagger
          </button>
          <button className={mode === 'redoc' ? 'btn' : 'btn secondary'} onClick={() => setMode('redoc')} type="button">
            ReDoc
          </button>
          <a className="btn secondary link-btn" href="/openapi.json" rel="noreferrer" target="_blank">
            OpenAPI JSON
          </a>
        </div>
      </article>
      <article className="card docs-frame-wrap">
        <iframe className="docs-frame" src={src} title="Neyra API docs" />
      </article>
    </section>
  )
}
