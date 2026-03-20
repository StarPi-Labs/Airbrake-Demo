#include <ESP32Servo.h>

// IO pin assignments
const int ANALOG_INPUT_PIN = 15;
const int SERVO_SIGNAL_PIN = 13;
const int LED_FEEDBACK_PIN = 2;

// Tuning parameters
const int ANALOG_DEADBAND = 6;      // Ignore tiny ADC jitter around idle value.
const int SERVO_MIN_US = 500;       // Per your servo spec.
const int SERVO_MAX_US = 2500;      
const int SERVO_CENTER_US = 1500;
const int SERVO_COMMAND_DEADBAND_US = 2;

// LED PWM feedback setup (ESP32 LEDC)
const int LED_PWM_FREQUENCY = 5000;
const int LED_PWM_RESOLUTION_BITS = 8; // 0..255 duty

Servo airbrakeServo;

void setup() {
  Serial.begin(115200);
  analogSetAttenuation(ADC_11db); // up to ~3.3V input

  ledcAttach(LED_FEEDBACK_PIN, LED_PWM_FREQUENCY, LED_PWM_RESOLUTION_BITS);
  ledcWrite(LED_FEEDBACK_PIN, 0);

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

  int targetPulseUs = map(latchedAnalog, 0, 4095, SERVO_MIN_US, SERVO_MAX_US);

  if (abs(targetPulseUs - lastPulseUs) >= SERVO_COMMAND_DEADBAND_US) {
    airbrakeServo.writeMicroseconds(targetPulseUs);
    lastPulseUs = targetPulseUs;
  }

  // LED feedback: 1500us -> 0%, 2500us -> 100% brightness.
  int ledDuty = map(constrain(lastPulseUs, SERVO_MIN_US, SERVO_MAX_US), SERVO_MIN_US, SERVO_MAX_US, 0, 255);
  ledcWrite(LED_FEEDBACK_PIN, ledDuty);

  Serial.print("Analog Latched: ");
  Serial.println(latchedAnalog);

  delay(20);
}
