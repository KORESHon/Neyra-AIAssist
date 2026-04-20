export function HomePage() {
  return (
    <section className="card stack">
      <h2>Нейра: микро-сайт</h2>
      <p>
        Это единая панель управления: состояние ядра, API, плагины, вебхуки и эксплуатационная документация.
      </p>
      <ul className="stats">
        <li>Раздел «Дашборд»: здоровье ядра, память, баланс модели.</li>
        <li>Раздел «Плагины»: включение/выключение, конфиг, операции reload/restart/invoke.</li>
        <li>Раздел «Вебхуки»: входящие endpoint-ы и исходящие маршруты с доставками/DLQ.</li>
        <li>Раздел «API Docs»: встроенные Swagger/ReDoc и OpenAPI JSON.</li>
      </ul>
      <p className="muted">
        Internal API локальный: поднимается вместе с `python main.py`, параметры bind — в
        `interfaces/internal_api/config.yaml`.
      </p>
    </section>
  )
}
