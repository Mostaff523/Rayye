# Rayye 0.3 implementation matrix

## Working and tested in software simulation

- Two seed zones and three seed devices; expandable plant/soil catalog; growth stages with distinct thresholds.
- Zone limits: max seconds, cooldown, estimated liters per day, flow-rate estimate, simultaneous-zone capacity, stop on upper threshold or timeout.
- Manual timed start/stop, preservation of auto mode on completion, global emergency stop.
- Device heartbeats, 4 planned soil sensor assignments, low-level sensor ingestion (3 planned); stale-data handling.
- In-app notifications, history and unread statuses; dashboard, summary windows, Saturday-based weeks, UTC epoch time, local display dates.
- Daily, weekly, monthly on-demand CSV; monthly archive CLI; migrations from simple v0.2 zone database; automated integration tests.
- REST/OpenAPI documentation and 10-second WebSocket snapshots.

## Not represented as complete

- Arduino Mega USB Serial device driver and protocol implementation: design only. Included firmware sketch demonstrates heartbeat and output-off safe state and intentionally does not actuate hardware.
- ESP32 communication protocol/firmware integration: pending actual network and message schema.
- FCM mobile push: notifications are queued in SQLite but not delivered to devices. Push requires Firebase credentials and token lifecycle.
- Pump/valve fault confirmation: requires current sensor, valve status or flow feedback. An event category exists but no false 'failure detected' claims are made.
- Secure public internet access: deployment design guidance, no hosted server or configured VPN.
- Automatic monthly archiving: CLI available; cron/Task Scheduler not installed.
- Auto water use while no tank sensor readings: system operates under software-only assumptions; do not use on hardware without validated tank-sensor interlocks.
- Real pump simultaneous operating capacity remains unverified; software defaults to two active zones purely for simulation.
- Weather suggestions, trained ML prediction, future forecasts, and watering schedules are postponed as requested.

## Important limitations and risks

This is an educational prototype. It is not an electrical safety controller. The emergency stop shuts down simulated software sessions only. True fail-off during an OS crash must be independent of the Pi and verified physically. Sensor calibrations, valve counts, electrical polarity, maximum fill rates, and relay wiring are not known. Back up the SQLite database independently from monthly CSV reports.
