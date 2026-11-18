# Hardware integration contract (not live)

**Pi**: owns decision logic and notifications. **Mega**: obeys explicit actuator commands once a real protocol is implemented, must force all outputs OFF upon lost heartbeat or emergency condition. **2 ESP32s**: report mapped sensor telemetry. Mega uses USB Serial; ESP32 communication not yet selected.

1. Mega boots with every output OFF (verify active-low relay board behavior before use). It should wait for authenticated/validated host commands (NOT implemented in the reference sketch).
2. Pi periodically sends a heartbeat, Mega acknowledges and resets a short hardware-independent timeout. If messages cease, Mega turns outputs OFF and requires a new verified command. The reference firmware illustrates heartbeat logic but accepts no actuation commands.
3. Every command should have sequence ID, zone ID, bounded duration, acknowledgment and timeout. Confirm pump capacity from datasheets and field measurements before enabling concurrent valves.
4. ESP32 sensor reports should include unique device ID, sensor ID, timestamps, calibrated percent, and quality flag. A stale or disconnected sensor suspends automatic irrigation for its zone.
5. Water level drop below configured threshold blocks starts. Treat inconsistent tank data as unsafe until sensor design and assignment verified.
6. Add hardware-rated emergency cutout, flyback protection, isolation and adequate power budget. Any pump/valve fault classification requires hardware feedback that is not available today.

The `.ino` file is **not** a working irrigation controller and uses **placeholder** pins and output polarity. Do not upload it to real relay-connected hardware without modifying and reviewing it for your build.
