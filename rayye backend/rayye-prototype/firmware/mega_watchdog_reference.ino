// REFERENCE ONLY: not a complete relay/valve controller.
// Independent communication watchdog. All outputs OFF after missed heartbeats.
// Configure pins and output polarity ONLY after electrical validation.
const unsigned long HEARTBEAT_TIMEOUT_MS = 3000;
unsigned long lastHeartbeat = 0;
const int VALVE_PINS[] = {22, 23, 24, 25}; // PLACEHOLDERS, NOT VERIFIED
const int OUTPUT_OFF = LOW;                  // PLACEHOLDER, VERIFY RELAY POLARITY
void outputsOff() {
  for (int pin : VALVE_PINS) digitalWrite(pin, OUTPUT_OFF);
}
void setup() {
  Serial.begin(115200);
  for (int pin : VALVE_PINS) { digitalWrite(pin, OUTPUT_OFF); pinMode(pin, OUTPUT); }
  outputsOff();
  lastHeartbeat = millis();
}
void loop() {
  // Safety design demonstration: only recognizes PING heartbeats.
  // NO ACTUATION COMMANDS ARE ACCEPTED BY THIS REFERENCE.
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line == "PING") { lastHeartbeat = millis(); Serial.println("ACK"); }
  }
  if (millis() - lastHeartbeat > HEARTBEAT_TIMEOUT_MS) outputsOff();
}
