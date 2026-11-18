# Suggested milestones

1. **v0.3 Software prototype (this ZIP)**: SQLite data model, two-zone simulation, plant/soil stages, telemetry, alerts, reports, emergency stop, REST/WS API, tests.
2. **Hardware communications**: define Mega USB Serial message protocol and ESP32 uplink; implement ACKs, boot-safe states, hardware watchdog and fail-off bench tests. Validate real pump capacity, actuator feedback and wiring.
3. **Flutter integration**: device/zone setup screen, sensor chart, growth stages, manual button, thresholds, notification inbox, reports and WebSocket status.
4. **Cloud-ready hardening**: implement push delivery, secured identity and token rotation, TLS gateway/VPN, backups, observability, recovery and stronger concurrency/SQLite transaction model.
5. **Deferred enhancements**: weather-based recommendations, 7-day forecast predictions, ML evaluation. No scheduled watering in the current release.

## Test command

`python -m pytest -q`

For collaborative development: add PR checks for formatting, static analysis, integration tests, and test against mock serial traffic before connecting live pumps.
