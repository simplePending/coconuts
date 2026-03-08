// ---------------- ULTRASONIC SENSOR PINS ----------------
#define TAP_TRIG 13
#define TAP_ECHO 12

#define MALAUHOG_TRIG 3
#define MALAUHOG_ECHO 10

#define MALAKATAD_TRIG 5
#define MALAKATAD_ECHO 7

#define MALAKANIN_TRIG 9
#define MALAKANIN_ECHO 8

// ---------------- RELAY PINS ----------------
#define CONVEYOR_RELAY A0
#define TAP_RELAY 11
#define MALAUHOG_RELAY 2
#define MALAKATAD_RELAY 4
#define MALAKANIN_RELAY 6

// ---------------- STATE MACHINE ----------------
enum State {
  IDLE,
  MOTOR_RUNNING,
  COCONUT_DETECTED,
  TAPPING,
  WAITING_CLASSIFICATION,
  ROUTING,
  COMPLETE
};

State currentState = IDLE;

bool coconutProcessing = false;
unsigned long routeStart = 0;

int pendingRoute = 0;

const int DIST_THRESHOLD = 20;
const unsigned long ROUTE_TIMEOUT_MS = 8000;  // increased from 5000 to give coconut travel time

// DETECT_DELAY removed — relay now fires immediately on detection

// ------------------------------------------------

void setup() {

  Serial.begin(9600);

  pinMode(TAP_TRIG, OUTPUT);
  pinMode(TAP_ECHO, INPUT);

  pinMode(MALAUHOG_TRIG, OUTPUT);
  pinMode(MALAUHOG_ECHO, INPUT);

  pinMode(MALAKATAD_TRIG, OUTPUT);
  pinMode(MALAKATAD_ECHO, INPUT);

  pinMode(MALAKANIN_TRIG, OUTPUT);
  pinMode(MALAKANIN_ECHO, INPUT);

  pinMode(CONVEYOR_RELAY, OUTPUT);
  pinMode(TAP_RELAY, OUTPUT);
  pinMode(MALAUHOG_RELAY, OUTPUT);
  pinMode(MALAKATAD_RELAY, OUTPUT);
  pinMode(MALAKANIN_RELAY, OUTPUT);

  digitalWrite(CONVEYOR_RELAY, LOW);
  digitalWrite(TAP_RELAY, LOW);
  digitalWrite(MALAUHOG_RELAY, LOW);
  digitalWrite(MALAKATAD_RELAY, LOW);
  digitalWrite(MALAKANIN_RELAY, LOW);

  Serial.println("System Ready");
}

// ------------------------------------------------

void loop() {

  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    handleCommand(cmd);
  }

  switch(currentState) {

    case IDLE:
      break;

    case MOTOR_RUNNING:

      if(!coconutProcessing){

        long dist = readUltrasonic(TAP_TRIG, TAP_ECHO);

        if(dist > 0 && dist < DIST_THRESHOLD){

          coconutProcessing = true;
          currentState = COCONUT_DETECTED;
          Serial.println("DETECTED");

        }
      }

    break;

    case COCONUT_DETECTED:

      digitalWrite(CONVEYOR_RELAY, LOW);
      Serial.println("MOTOR_STOPPED");

      currentState = TAPPING;

    break;

    case TAPPING:
    break;

    case WAITING_CLASSIFICATION:
    break;

    case ROUTING:

      if(pendingRoute != 0){

        int relayPin = -1;
        bool detected = false;

        if(pendingRoute == 1){

          relayPin = MALAUHOG_RELAY;
          long d = readUltrasonic(MALAUHOG_TRIG, MALAUHOG_ECHO);
          if(d > 0 && d < DIST_THRESHOLD) detected = true;

        }

        else if(pendingRoute == 2){

          relayPin = MALAKATAD_RELAY;
          long d = readUltrasonic(MALAKATAD_TRIG, MALAKATAD_ECHO);
          if(d > 0 && d < DIST_THRESHOLD) detected = true;

        }

        else if(pendingRoute == 3){

          relayPin = MALAKANIN_RELAY;
          long d = readUltrasonic(MALAKANIN_TRIG, MALAKANIN_ECHO);
          if(d > 0 && d < DIST_THRESHOLD) detected = true;

        }

        // Fire relay after 1 second delay on detection — gives time to push coconut
        if(detected){

          delay(1000);  // 1 second delay before firing relay

          digitalWrite(relayPin, HIGH);
          delay(500);
          digitalWrite(relayPin, LOW);

          if(pendingRoute == 1) Serial.println("ROUTED_MALAUHOG");
          if(pendingRoute == 2) Serial.println("ROUTED_MALAKATAD");
          if(pendingRoute == 3) Serial.println("ROUTED_MALAKANIN");

          pendingRoute = 0;
          currentState = COMPLETE;

        }

        // Timeout fallback — force relay if coconut never detected
        else if(millis() - routeStart > ROUTE_TIMEOUT_MS){

          delay(1000);  // 1 second delay before firing relay

          if(relayPin != -1){
            digitalWrite(relayPin, HIGH);
            delay(500);
            digitalWrite(relayPin, LOW);
          }

          Serial.println("ROUTE_TIMEOUT");

          pendingRoute = 0;
          currentState = COMPLETE;

        }
      }

    break;

    case COMPLETE:

      coconutProcessing = false;
      currentState = IDLE;

      Serial.println("ROUTED");

    break;

  }

  delay(10);  // reduced from 50ms — faster ultrasonic polling during ROUTING

}

// ------------------------------------------------

long readUltrasonic(int trig, int echo){

  digitalWrite(trig, LOW);
  delayMicroseconds(2);

  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);

  long duration = pulseIn(echo, HIGH, 20000);

  if(duration == 0) return -1;

  return duration / 58;
}

// ------------------------------------------------

void handleCommand(String cmd){

  if(cmd == "START_MOTOR"){

    digitalWrite(CONVEYOR_RELAY, HIGH);
    currentState = MOTOR_RUNNING;

    Serial.println("MOTOR_ON");

  }

  else if(cmd == "STOP_MOTOR"){

    digitalWrite(CONVEYOR_RELAY, LOW);
    currentState = IDLE;

    Serial.println("MOTOR_OFF");

  }

  else if(cmd == "TAP"){

    digitalWrite(TAP_RELAY, HIGH);
    delay(150);
    digitalWrite(TAP_RELAY, LOW);

    Serial.println("TAP_DONE");

    currentState = WAITING_CLASSIFICATION;

  }

  else if(cmd == "ROUTE_MALAUHOG"){

    pendingRoute = 1;
    routeStart = millis();
    currentState = ROUTING;

  }

  else if(cmd == "ROUTE_MALAKATAD"){

    pendingRoute = 2;
    routeStart = millis();
    currentState = ROUTING;

  }

  else if(cmd == "ROUTE_MALAKANIN"){

    pendingRoute = 3;
    routeStart = millis();
    currentState = ROUTING;

  }

}
