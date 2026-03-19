#include <ESP32Servo.h>

// IO pin assignments
const int ANALOG_INPUT_PIN = 15;
const int SERVO_SIGNAL_PIN = 33;

// Tuning parameters
const int ANALOG_DEADBAND = 6;      // Ignore tiny ADC jitter around idle value.
const int SERVO_MIN_US = 500;       // Per your servo spec.
const int SERVO_MAX_US = 2500;      // Per your servo spec.
const int SERVO_CENTER_US = 1500;
const int SERVO_COMMAND_DEADBAND_US = 2;

Servo airbrakeServo;

float floatMap(float x, float in_min, float in_max, float out_min, float out_max) {
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

void setup() {
  Serial.begin(115200);
  analogSetAttenuation(ADC_11db); // up to ~3.3V input

  airbrakeServo.setPeriodHertz(50);
  airbrakeServo.attach(SERVO_SIGNAL_PIN, SERVO_MIN_US, SERVO_MAX_US);
  airbrakeServo.writeMicroseconds(SERVO_CENTER_US);
}

void loop() {
  static int latchedAnalog = -1;
  static int lastPulseUs = SERVO_CENTER_US;

  int analogValue = analogRead(ANALOG_INPUT_PIN);
  if (latchedAnalog < 0) {
    latchedAnalog = analogValue;
  } else if (abs(analogValue - latchedAnalog) >= ANALOG_DEADBAND) {
    latchedAnalog = analogValue;
  }

  float voltage = floatMap((float)latchedAnalog, 0.0f, 4095.0f, 0.0f, 3.3f);
  int targetPulseUs = map(latchedAnalog, 0, 4095, SERVO_MIN_US, SERVO_MAX_US);

  if (abs(targetPulseUs - lastPulseUs) >= SERVO_COMMAND_DEADBAND_US) {
    airbrakeServo.writeMicroseconds(targetPulseUs);
    lastPulseUs = targetPulseUs;
  }

  int servoAngleDeg = map(lastPulseUs, SERVO_MIN_US, SERVO_MAX_US, 0, 180);

  Serial.print("Analog Raw: ");
  Serial.print(analogValue);
  Serial.print(", Analog Latched: ");
  Serial.print(latchedAnalog);
  Serial.print(", Voltage: ");
  Serial.print(voltage, 3);
  Serial.print(" V, Servo Pulse: ");
  Serial.print(lastPulseUs);
  Serial.print(" us, Servo Angle: ");
  Serial.println(servoAngleDeg);

  delay(20);
}
