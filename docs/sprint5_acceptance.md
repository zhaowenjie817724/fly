# Sprint 5 Acceptance (PC)

## Backend

Start FastAPI service:

```
python apps/service/server.py --config configs/service.yaml --run latest
```

WebSocket: `ws://<host>:8000/ws`

HTTP:
- `GET /health`
- `GET /status`
- `POST /command` (json)

Web Dashboard:
- `http://<host>:8000/`

## Mini Program MVP

Open `miniapp/` in WeChat DevTools and update the API host if needed.

## Expected Outputs

- Client receives telemetry/observation/event via WS.
- `POST /command` appends to runs/<run_id>/commands.jsonl.
