import { Blocks, Bot, Cable, ShieldCheck } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'

export function HomePage() {
  return (
    <section className="grid gap-6">
      <Card className="border-zinc-800 bg-zinc-900/50 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-xl font-semibold tracking-tight text-zinc-100">
            <Bot className="h-5 w-5 text-cyan-300" />
            Нейра: микро-сайт
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-zinc-300">
          <p className="max-w-4xl leading-relaxed">
            Это единая панель управления: состояние ядра, API, плагины, вебхуки и эксплуатационная документация.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
              <p className="mb-2 flex items-center gap-2 text-sm font-semibold tracking-tight text-zinc-100">
                <Blocks className="h-4 w-4 text-cyan-300" />
                Основные разделы
              </p>
              <ul className="space-y-2 text-sm text-zinc-300">
                <li>Дашборд: здоровье ядра, память, баланс модели.</li>
                <li>Плагины: включение/выключение, конфиг, invoke.</li>
                <li>Вебхуки: маршруты и доставки/DLQ.</li>
                <li>API Docs: Swagger + OpenAPI JSON + Markdown docs.</li>
              </ul>
            </div>
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/70 p-4">
              <p className="mb-2 flex items-center gap-2 text-sm font-semibold tracking-tight text-zinc-100">
                <ShieldCheck className="h-4 w-4 text-fuchsia-300" />
                Техническая информация
              </p>
              <p className="text-sm text-zinc-300">
                Internal API локальный: поднимается вместе с
                <span className="mx-1 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-200">python main.py</span>
                и использует конфиг
                <span className="ml-1 rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-200">
                  interfaces/internal_api/config.yaml
                </span>
                .
              </p>
              <p className="mt-3 flex items-center gap-2 text-xs text-zinc-500">
                <Cable className="h-3.5 w-3.5" />
                Панель рассчитана на локальную эксплуатацию и быстрый операционный контроль.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </section>
  )
}
