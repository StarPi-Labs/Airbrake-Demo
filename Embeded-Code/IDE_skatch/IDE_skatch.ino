#include <ESP32Servo.h>

// I moved this to Pin 34 (a safe, input-only pin for ADC)
const int ANALOG_INPUT_PIN = 34; 
const int SERVO_SIGNAL_PIN = 13;
const int LED_FEEDBACK_PIN = 2;

const int ANALOG_DEADBAND = 6;      
const int SERVO_MIN_US = 500;       
const int SERVO_MAX_US = 2500;      
const int SERVO_CENTER_US = 1500;
const int SERVO_COMMAND_DEADBAND_US = 2;

const int LED_PWM_FREQUENCY = 5000;
const int LED_PWM_RESOLUTION_BITS = 8; 

Servo airbrakeServo;

void setup() {
  Serial.begin(115200);
  
  // 1. Setup Servo first
  airbrakeServo.setPeriodHertz(50);
  airbrakeServo.attach(SERVO_SIGNAL_PIN, SERVO_MIN_US, SERVO_MAX_US);
  airbrakeServo.writeMicroseconds(SERVO_CENTER_US);

  delay(100); // Give the ESP32 a moment to assign timers

  // 2. Setup LED second
  ledcAttach(LED_FEEDBACK_PIN, LED_PWM_FREQUENCY, LED_PWM_RESOLUTION_BITS);
  ledcWrite(LED_FEEDBACK_PIN, 0);
  
  Serial.println("Setup Complete. Turn your potentiometer!");
}

void loop() {
  static int latchedAnalog = -1;
  static int lastPulseUs = SERVO_CENTER_US;

  // Read the knob
  int analogValue = analogRead(ANALOG_INPUT_PIN);
  
  if (latchedAnalog < 0) {
    latchedAnalog = analogValue;
  } else if (abs(analogValue - latchedAnalog) >= ANALOG_DEADBAND) {
    latchedAnalog = analogValue;
  }

  // Calculate where the servo should go
  int targetPulseUs = map(latchedAnalog, 0, 4095, SERVO_MIN_US, SERVO_MAX_US);

  if (abs(targetPulseUs - lastPulseUs) >= SERVO_COMMAND_DEADBAND_US) {
    lastPulseUs = targetPulseUs;
  }
  
  // Move servo
  airbrakeServo.writeMicroseconds(lastPulseUs);

  // Update LED
  int ledDuty = map(constrain(lastPulseUs, SERVO_MIN_US, SERVO_MAX_US), SERVO_MIN_US, SERVO_MAX_US, 0, 255);
  ledcWrite(LED_FEEDBACK_PIN, ledDuty);

  Serial.print("Analog Latched: ");
  Serial.println(latchedAnalog);

  delay(20);
}