# Rayye Irrigation Backend v0.3 (Simulation)

Backend update from uploaded Rayye v0.2 prototype. Python FastAPI + SQLite, documented OpenAPI REST at `/docs`, simple real-time status WebSocket at `/ws/live`, GitHub-friendly tests and documentation. **No actual physical hardware is controlled.** Do not connect this prototype to a live irrigation pump without verified firmware, relay wiring, isolation, pump-rating checks, monitoring, and on-device watchdogs.

## Getting started

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate  | macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# Windows PowerShell: $env:RAYYE_API_TOKEN="replace-with-a-long-random-secret"
# macOS/Linux: export RAYYE_API_TOKEN="replace-with-a-long-random-secret"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m pytest -q
```

Test with `Authorization: Bearer <token>`. For LAN use `--host 0.0.0.0` only on a trusted network and configure host firewall. **Never directly port-forward this HTTP development server to the public internet.** For remote access use an authenticated VPN such as Tailscale or a hardened HTTPS reverse proxy with a secure identity layer. This prototype has a shared bearer token and does **not** have production user accounts or role-based access.

## Current project assumptions

- 1 Raspberry Pi decision-maker (represented by this service), 1 Arduino Mega on **USB Serial**, 2 ESP32s (Wi-Fi transport is a configurable placeholder pending final protocol).
- 2 irrigation zones, 4 soil-moisture sensors and 3 water-level sensors planned. Assign the moisture sensors explicitly per zone with `POST /zones/{id}/sensors`; send moisture readings through `POST /telemetry`, water-level readings through `POST /water-levels`.
- 2–4 valves undecided, so the number of valves and pump electrical ratings are **not** hardcoded. A capacity of 2 simultaneously active zones is the **simulated** starting setting, not proof of real pump capacity. Before any live actuation, validate pump output and permitted concurrent valve flow.
- Every zone has configurable cooldown, max duration, daily **estimated** water allowance, growth stage, low/high moisture thresholds, plant, soil, and area. Automatic watering stops on upper threshold, timeout, stale sensor data, or daily allowance. Manual ON/OFF actions and timed watering are available. Manual sessions leave saved automatic mode unchanged.
- Normal telemetry suggested every 15 minutes; active irrigation every 5–10 seconds. The backend's active stale threshold is 20 seconds. Without recent data, automatic watering fails safe. Emergency stop sets all zones to manual.
- No watering scheduling. Weather and ML recommendations remain postponed. Growth-stage threshold management is implemented now.
- Readings stored as Unix timestamps (UTC epoch seconds). User-facing report boundaries use `Africa/Cairo`, with Saturday as the weekly starting day.
- Plant/soil starter entries are names only, not scientifically validated moisture calibration values. Configure plant growth-stage bands explicitly. Sensor calibration is critical for coir and other substrates.
- No flow sensor: water consumption is calculated from configured nominal liters/minute times elapsed watering time and marked **estimated**.

## Important endpoints

| Task | REST endpoint |
|---|---|
| Full API schema | `GET /openapi.json` and `/docs` |
| System / zone status | `GET /status`, `GET /zones` |
| Zone creation and configuration | `POST /zones`, `PUT /zones/{id}` |
| Sensor assignments and readings | `POST /zones/{id}/sensors`, `POST /telemetry`, `POST /water-levels` |
| Device registration/heartbeat | `GET /devices`, `POST /devices`, `POST /devices/{id}/heartbeat` |
| Manual timed or ON/OFF | `POST /zones/{id}/manual` with `{ "action":"start", "duration_seconds":30 }` or `{ "action":"stop" }` |
| Emergency halt | `POST /stop` |
| Starter plant and soil catalog | `GET/POST /plants`, `GET/POST /soils` |
| Growth stages | `PUT /plants/{id}/stages`, `GET /plants/{id}/stages` |
| Notifications and read status | `GET /notifications`, `POST /notifications/{id}/read` |
| Dashboard and aggregates | `GET /dashboard`, `GET /reports/summary?period=week` |
| Daily/weekly/monthly CSV | `GET /exports/{kind}?period=month&date=2026-11-17` |
| Installation configuration | `GET /setup`, `PUT /setup` |
| Real-time status snapshots | `WS /ws/live` (10-second polling, token in initial JSON message) |

CSV kinds: `sensor_readings`, `watering_events`, `water_consumption`, `faults`. Monthly durable archive example:

```bash
python -m app.archive --month 2026-11 --out archives
```

Generates `archives/2026/11/` with four distinct CSV files. Schedule this once monthly using cron/task scheduler if ongoing archival is needed; the CLI itself is on-demand. Raw history in SQLite is not deleted.

## Notification channels

In-app notifications are persisted and visible in the API. All eight selected event types have enumerated severity mappings: disconnected sensor, lost device, low water level, pump/valve failure, excessive moisture, emergency stop, watering completion, daily limit. **Mobile push is a defined integration requirement, but FCM delivery, push-token storage and credentials are not yet implemented**, nor is physical pump/valve failure detectable without feedback hardware. `push_status=pending` is a queue marker and does not imply successful delivery. Do not treat this as a fully functional push notification service.

## Secure Flutter integration

Use standard REST API with bearer authentication, never ship a static public production API token in a distributed app. For WebSockets, the prototype expects an initial JSON message `{ "token": "<secret>" }` and sends status every 10 seconds; use `wss://` when remotely connected. For a real rollout, replace this temporary token mechanism with scoped, expiring credentials and a secure remote access gateway. API calls should use UTC times from the backend and render with the device's selected timezone (typically Egypt).

See `docs/IMPLEMENTATION_STATUS.md`, `docs/HARDWARE_CONTRACT.md`, and `docs/MILESTONES.md`.
