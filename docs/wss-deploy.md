# WSS Deployment Notes

Neyra gateway exposes:
- HTTP API: `/v1/*`
- WebSocket endpoints:
  - `/v1/ws/chat`
  - `/v1/ws/audio`

## Local Development

- Start API: `python main.py --mode api`
- Use `ws://127.0.0.1:8787/v1/ws/chat` and `ws://127.0.0.1:8787/v1/ws/audio`

## Production

Use reverse proxy (Nginx/Caddy/Traefik) with TLS termination:
- external clients connect only via `wss://...`
- proxy upstream to local `ws://127.0.0.1:8787`

Important:
- keep `Upgrade` and `Connection` headers for websocket upgrade
- forward `Authorization` header (or use `?token=` query)
- enforce external HTTPS/WSS only (no plain WS on public interface)
