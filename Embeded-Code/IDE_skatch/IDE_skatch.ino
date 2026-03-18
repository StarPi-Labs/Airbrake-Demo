#include <ESP_FlexyStepper.h>

// IO pin assignments
const int ANALOG_INPUT_PIN = 15;
const int MOTOR_STEP_PIN = 33;
const int MOTOR_DIRECTION_PIN = 25;

// Tuning parameters
const int ANALOG_DEADBAND = 6;         // Ignore tiny ADC jitter around idle value.
const long MIN_TARGET_POS = -2000;
const long MAX_TARGET_POS = 2000;
const float MAX_SPEED_STEPS_S = 1200.0f;
const float ACCEL_STEPS_S2 = 2200.0f;

ESP_FlexyStepper stepper;

float floatMap(float x, float in_min, float in_max, float out_min, float out_max) {
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

void setup() {
  Serial.begin(115200);
  analogSetAttenuation(ADC_11db); // up to ~3.3V input

  stepper.connectToPins(MOTOR_STEP_PIN, MOTOR_DIRECTION_PIN);
  stepper.setSpeedInStepsPerSecond(MAX_SPEED_STEPS_S);
  stepper.setAccelerationInStepsPerSecondPerSecond(ACCEL_STEPS_S2);
  stepper.setDecelerationInStepsPerSecondPerSecond(ACCEL_STEPS_S2);
  stepper.startAsService(0);
}

void loop() {
  static int latchedAnalog = -1;

  int analogValue = analogRead(ANALOG_INPUT_PIN);
  if (latchedAnalog < 0) {
    latchedAnalog = analogValue;
  } else if (abs(analogValue - latchedAnalog) >= ANALOG_DEADBAND) {
    latchedAnalog = analogValue;
  }

  float voltage = floatMap((float)latchedAnalog, 0.0f, 4095.0f, 0.0f, 3.3f);
  long desiredPosition = (long)floatMap((float)latchedAnalog, 0.0f, 4095.0f, (float)MIN_TARGET_POS, (float)MAX_TARGET_POS);
  stepper.setTargetPositionInSteps(desiredPosition);
  long localCurrentPosition = stepper.getCurrentPositionInSteps();

  Serial.print("Analog Raw: ");
  Serial.print(analogValue);
  Serial.print(", Analog Latched: ");
  Serial.print(latchedAnalog);
  Serial.print(", Voltage: ");
  Serial.print(voltage, 3);
  Serial.print(" V, Target Pos: ");
  Serial.print(desiredPosition);
  Serial.print(", Current Pos: ");
  Serial.println(localCurrentPosition);

  delay(20);
}
