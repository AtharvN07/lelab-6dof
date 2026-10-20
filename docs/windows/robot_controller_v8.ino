/*
 * robot_controller_v8.ino — LeRobot-compatible Arduino Mega firmware.
 *
 * Protocol (115200 baud, newline-terminated):
 *   PING\n         →  PONG
 *   HOME\n         →  OK:HOME:90,90,90,90,90,90
 *   STATE\n        →  OK:STATE:b,s,e,w,r,g   (servo degrees 0-180)
 *   A:b,s,e,w,r,g\n  →  OK:A:b,s,e,w,r,g   (absolute servo degrees)
 *   D:d0,d1,d2,d3,d4,d5\n →  OK:D:b,s,e,w,r,g   (delta servo degrees)
 *
 * Joint order: 0=base 1=shoulder 2=elbow 3=wrist 4=rotate 5=gripper
 *
 * Hardware:
 *   Arduino Mega 2560
 *   PCA9685 PWM board (I2C addr 0x40) — 6 servos on channels 0-5
 *   L298N motor driver — optional rover (same pins as before)
 *
 * Smooth stepping: 1 deg per 10ms loop tick.
 * EEPROM trim calibration preserved from v7.
 */

#include <Wire.h>
#include <EEPROM.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

#define SERVOMIN 150
#define SERVOMAX 600

int pos[6]    = {90, 90, 90, 90, 90, 90};
int target[6] = {90, 90, 90, 90, 90, 90};

// ── EEPROM trim calibration ─────────────────────────────────────────────────
#define EEPROM_MAGIC_ADDR 0
#define EEPROM_MAGIC_VAL  0xA5
#define EEPROM_TRIM_ADDR  1
int trim[6] = {0, 0, 0, 0, 0, 0};

// ── L298N rover pins (optional) ─────────────────────────────────────────────
#define ENA 5
#define ENB 6
#define IN1 7
#define IN2 8
#define IN3 9
#define IN4 10

#define MOVE_DURATION 1000
#define ROVER_SPEED   255

enum RoverPhase { IDLE, RUNNING };
RoverPhase roverPhase = IDLE;
unsigned long phaseStartTime = 0;

// ── Helpers ─────────────────────────────────────────────────────────────────
int angleToPulse(int channel, int angle) {
  int a = constrain(angle + trim[channel], 0, 180);
  return map(a, 0, 180, SERVOMIN, SERVOMAX);
}

void saveAllTrims() {
  for (int i = 0; i < 6; i++)
    EEPROM.put(EEPROM_TRIM_ADDR + i * sizeof(int), trim[i]);
  EEPROM.update(EEPROM_MAGIC_ADDR, EEPROM_MAGIC_VAL);
}

void saveTrim(int ch) {
  EEPROM.put(EEPROM_TRIM_ADDR + ch * sizeof(int), trim[ch]);
  EEPROM.update(EEPROM_MAGIC_ADDR, EEPROM_MAGIC_VAL);
}

void loadTrims() {
  if (EEPROM.read(EEPROM_MAGIC_ADDR) == EEPROM_MAGIC_VAL) {
    for (int i = 0; i < 6; i++) {
      int v;
      EEPROM.get(EEPROM_TRIM_ADDR + i * sizeof(int), v);
      trim[i] = constrain(v, -90, 90);
    }
  } else {
    for (int i = 0; i < 6; i++) trim[i] = 0;
    saveAllTrims();
  }
}

void stopMotors() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  analogWrite(ENA, 0);    analogWrite(ENB, 0);
}

void startMove(int m1, int m2, int m3, int m4) {
  digitalWrite(IN1, m1); digitalWrite(IN2, m2);
  digitalWrite(IN3, m3); digitalWrite(IN4, m4);
  analogWrite(ENA, ROVER_SPEED);
  analogWrite(ENB, ROVER_SPEED);
  roverPhase     = RUNNING;
  phaseStartTime = millis();
}

void updateRover() {
  if (roverPhase == IDLE) return;
  if (millis() - phaseStartTime >= (unsigned long)MOVE_DURATION) {
    stopMotors();
    roverPhase = IDLE;
  }
}

void printTargets(const char* prefix) {
  Serial.print(prefix);
  for (int i = 0; i < 6; i++) {
    Serial.print(target[i]);
    if (i < 5) Serial.print(",");
  }
  Serial.println();
}

void printTrims() {
  Serial.print("OK:TRIM:");
  for (int i = 0; i < 6; i++) {
    Serial.print(trim[i]);
    if (i < 5) Serial.print(",");
  }
  Serial.println();
}

// ── Setup ───────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(50);

  loadTrims();

  Wire.begin();
  pca.begin();
  pca.setPWMFreq(50);

  pinMode(ENA, OUTPUT); pinMode(ENB, OUTPUT);
  pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);

  delay(1000);
  for (int i = 0; i < 6; i++)
    pca.setPWM(i, 0, angleToPulse(i, pos[i]));

  Serial.println("READY");
}

// ── Main loop ───────────────────────────────────────────────────────────────
void loop() {
  updateRover();

  if (Serial.available()) {
    char cmd = Serial.read();

    // Multi-char commands: A: D: P: H: S: C: V Z
    if (cmd=='A'||cmd=='D'||cmd=='P'||
        cmd=='H'||cmd=='S'||cmd=='C'||cmd=='V'||cmd=='Z') {

      char rest[63];
      int n = Serial.readBytesUntil('\n', rest, 62);
      rest[n] = '\0';
      if (n > 0 && rest[n-1] == '\r') { rest[n-1] = '\0'; n--; }

      if (cmd == 'P' && strncmp(rest, "ING", 3) == 0) {
        Serial.println("PONG");
      }
      else if (cmd == 'H' && strncmp(rest, "OME", 3) == 0) {
        for (int i = 0; i < 5; i++) target[i] = 90;   // arm joints center
        target[5] = 0;                                 // gripper OPEN at home
        printTargets("OK:HOME:");
      }
      else if (cmd == 'S' && strncmp(rest, "TATE", 4) == 0) {
        printTargets("OK:STATE:");
      }
      // A:b,s,e,w,r,g  — absolute servo degrees (6 values)
      else if (cmd == 'A' && rest[0] == ':') {
        char* p = rest + 1;
        int vals[6] = {90,90,90,90,90,90};
        for (int i = 0; i < 6; i++) {
          vals[i] = (int)atoi(p);
          char* comma = strchr(p, ',');
          if (!comma) break;
          p = comma + 1;
        }
        for (int i = 0; i < 6; i++)
          target[i] = constrain(vals[i], 0, 180);
        printTargets("OK:A:");
      }
      // D:d0,d1,d2,d3,d4,wire  — delta servo degrees + gripper wire convention
      // wire: 1=close (target[5]=90), -1=open (target[5]=0), 0=no change
      else if (cmd == 'D' && rest[0] == ':') {
        char* p = rest + 1;
        int deltas[5] = {0,0,0,0,0};
        int gripper_wire = 0;
        for (int i = 0; i < 5; i++) {
          deltas[i] = (int)atoi(p);
          char* comma = strchr(p, ',');
          if (!comma) break;
          p = comma + 1;
        }
        // 6th value is gripper wire convention
        gripper_wire = (int)atoi(p);
        for (int i = 0; i < 5; i++)
          target[i] = constrain(target[i] + deltas[i], 0, 180);
        if      (gripper_wire == 1)  target[5] = 90;  // close
        else if (gripper_wire == -1) target[5] = 0;   // open
        printTargets("OK:D:");
      }
      // C:ch  — capture trim
      else if (cmd == 'C' && rest[0] == ':') {
        int ch = atoi(rest + 1);
        if (ch >= 0 && ch < 6) {
          trim[ch] += (target[ch] - 90);
          trim[ch]  = constrain(trim[ch], -90, 90);
          saveTrim(ch);
          target[ch] = 90; pos[ch] = 90;
          Serial.print("OK:CAPTURE:"); Serial.print(ch);
          Serial.print(":"); Serial.println(trim[ch]);
        } else {
          Serial.println("ERR:C:BADCHANNEL");
        }
      }
      else if (cmd == 'V') {
        printTrims();
      }
      else if (cmd == 'Z') {
        if (strncmp(rest, ":ALL", 4) == 0) {
          for (int i = 0; i < 6; i++) trim[i] = 0;
          saveAllTrims();
          Serial.println("OK:ZERO:ALL");
        } else if (rest[0] == ':') {
          int ch = atoi(rest + 1);
          if (ch >= 0 && ch < 6) {
            trim[ch] = 0; saveTrim(ch);
            Serial.print("OK:ZERO:"); Serial.println(ch);
          } else {
            Serial.println("ERR:Z:BADCHANNEL");
          }
        }
      }
      else {
        Serial.print("ERR:UNKNOWN:"); Serial.print(cmd); Serial.println(rest);
      }
      return;
    }

    // Keyboard teleop fallback (Serial Monitor)
    switch (cmd) {
      case '1': startMove(HIGH,LOW,  HIGH,LOW);  break;
      case '2': startMove(LOW,HIGH,  LOW,HIGH);  break;
      case '3': startMove(LOW,HIGH,  HIGH,LOW);  break;
      case '4': startMove(HIGH,LOW,  LOW,HIGH);  break;
      case '5': roverPhase=IDLE; stopMotors();   break;
    }
    switch (cmd) {
      case 'a': target[0] -= 5; break;
      case 'd': target[0] += 5; break;
      case 'w': target[1] += 5; break;
      case 's': target[1] -= 5; break;
      case 'j': target[2] += 5; break;
      case 'l': target[2] -= 5; break;
      case 'i': target[3] += 5; break;
      case 'k': target[3] -= 5; break;
      case 'u': target[4] += 5; break;
      case 'o': target[4] -= 5; break;
      case 'g': target[5] = 0;  break;
      case 'h': target[5] = 90; break;
    }
  }

  // Smooth servo step: 1 deg per 10ms
  for (int i = 0; i < 6; i++) {
    target[i] = constrain(target[i], 0, 180);
    if      (pos[i] < target[i]) pos[i]++;
    else if (pos[i] > target[i]) pos[i]--;
    pca.setPWM(i, 0, angleToPulse(i, pos[i]));
  }
  delay(10);
}
