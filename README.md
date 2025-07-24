//Declaring all variables needed.
//Neccasary Libraries
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_BNO055.h>
#include <WiFi.h>
#include <Adafruit_NeoPixel.h>

// Wi-Fi Credentials for WiFi connection (SETUP LOOP)
const char* ssid = "WiFi name";
const char* password = "Password";

// BNO055 and LCD initialization (called bno and lcd) 
Adafruit_BNO055 bno = Adafruit_BNO055(55, 0x28);
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Buttons(SETUP LOOP)
const int scrollButtonPin = 12;
const int enterButtonPin = 13;

// State machine
#define STATE_DEFAULT 0
#define STATE_PRESET_MENU 1
#define STATE_PRESET_SELECTED 2
#define STATE_IP_DISPLAY 3
int currentState = STATE_DEFAULT;
int selectedOption = 0;
bool presetActive = false; // Track if a preset is active

// Presets (aligned with Thonny)
float presets[6][3] = {
  {17.2, 1.7, -75.0},
  {-31.4, -13.3, 60.0},
  {-22.5, -2.9, -170.0},
  {-7.0, 43.7, 15.0},
  {-44.0, 31.9, 180.0},
  {2.6, 12.2, -110.0}
};

// Current preset values (updated by GUI or hardware)
float currentPresetX = 0.0;
float currentPresetY = 0.0;
float currentPresetZ = 0.0;

// Wi-Fi server
WiFiServer server(1234);
WiFiClient client;
bool wifiConnected = false;

// LED strip setup
#define LED_PIN 10 // used to control the leds 
#define LED_COUNT 21// 21 leds used in groups of 7 for each axis (x,y and z)
Adafruit_NeoPixel strip(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800); //specifies the speed and the order of colors sed to led strip

unsigned long lastFlashTime = 0;// to keep track of when the leds were fashed 
bool flashState = false; // are leds on or off
unsigned long lastButtonPress = 0; // For accidental presses of button or noise from button

// Normalized angles so that it corresponds to the standard STAR
float normalizeAngle(float angle) {
  if (angle >= 180.0) {
    return angle - 360.0;
  }
  return angle;
}
//all variables are now declared

//setup loop that runs once upon start-up to help with debugging.
void setup() {
  Wire.begin(6, 7); // for SCL and SDA
  Serial.begin(115200);

  WiFi.begin(ssid, password);

  unsigned long startTime = millis();
  while (millis() - startTime < 10000 && WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println("\nWiFi connected.");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    server.begin();
  } else {
    Serial.println("\nWiFi connection failed.");
  }

  if (!bno.begin()) {
    Serial.println("BNO055 not detected!");
    while (1);
  }
  Serial.println("BNO055 initialized.");

  lcd.init();
  lcd.backlight();

  pinMode(scrollButtonPin, INPUT_PULLUP);
  pinMode(enterButtonPin, INPUT_PULLUP);

  strip.begin();
  strip.setBrightness(50);
  strip.clear();
  strip.show();
}


//Repeated loop that is the logic behind the Device functions
void loop() {
  if (wifiConnected) {
    if (!client || !client.connected()) {
      client = server.available();
      if (client) {
        Serial.println("New client connected");
        while (client.available()) client.read(); // Clear buffer
      }
    }
    if (client && client.connected() && client.available()) {
      String incoming = client.readStringUntil('\n');
      incoming.trim();
      if (incoming.startsWith("PRESET:")) {
        if (incoming == "PRESET:CLEAR") {
          currentState = STATE_DEFAULT;
          presetActive = false;
          currentPresetX = 0.0;
          currentPresetY = 0.0;
          currentPresetZ = 0.0;
          lcd.clear();
          lcd.setCursor(0, 0); lcd.print("X:");
          lcd.setCursor(0, 1); lcd.print("Y:");
          if (wifiConnected && client.connected()) {
            client.println("PRESET:CLEAR");
          }
          Serial.println("Received clear command");
        } else {
          float presetX = 0.0, presetY = 0.0, presetZ = 0.0;
          if (sscanf(incoming.c_str(), "PRESET:x:%f,y:%f,z:%f", &presetX, &presetY, &presetZ) == 3) {
            currentState = STATE_PRESET_SELECTED;
            presetActive = true;
            currentPresetX = presetX;
            currentPresetY = presetY;
            currentPresetZ = presetZ;
            lcd.clear();
            lcd.setCursor(0, 0); lcd.print("X:"); lcd.print(currentPresetX, 2);
            lcd.setCursor(0, 1); lcd.print("Y:"); lcd.print(currentPresetY, 2);
            lcd.setCursor(8, 1); lcd.print(" Z:"); lcd.print(currentPresetZ, 2);
            Serial.print("Received preset: X:"); Serial.print(currentPresetX, 2);
            Serial.print(", Y:"); Serial.print(currentPresetY, 2);
            Serial.print(", Z:"); Serial.println(currentPresetZ, 2);
          }
        }
      }
    }
  }

  sensors_event_t event;
  bno.getEvent(&event);

  unsigned long currentTime = millis();
  if (currentTime - lastFlashTime >= 500) {
    flashState = !flashState;
    lastFlashTime = currentTime;
  }

  // Debounce button press
  if (currentTime - lastButtonPress > 200) {
    if (digitalRead(enterButtonPin) == LOW) {
      lastButtonPress = currentTime;
      if (currentState == STATE_DEFAULT) {
        currentState = STATE_PRESET_MENU;
        selectedOption = 0;
        lcd.clear();
        displayPresetMenu();
      } else if (currentState == STATE_PRESET_SELECTED || currentState == STATE_IP_DISPLAY) {
        currentState = STATE_DEFAULT;
        presetActive = false;
        currentPresetX = 0.0;
        currentPresetY = 0.0;
        currentPresetZ = 0.0;
        lcd.clear();
        lcd.setCursor(0, 0); lcd.print("X:");
        lcd.setCursor(0, 1); lcd.print("Y:");
        if (wifiConnected && client && client.connected()) {
          client.println("PRESET:CLEAR");
        }
      } else if (currentState == STATE_PRESET_MENU && selectedOption > 0) {
        currentState = STATE_PRESET_SELECTED;
        presetActive = true;
        currentPresetX = presets[selectedOption - 1][0];
        currentPresetY = presets[selectedOption - 1][1];
        currentPresetZ = presets[selectedOption - 1][2];
        lcd.clear();
        lcd.setCursor(0, 0); lcd.print("X:"); lcd.print(currentPresetX, 2);
        lcd.setCursor(0, 1); lcd.print("Y:"); lcd.print(currentPresetY, 2);
        lcd.setCursor(8, 1); lcd.print(" Z:"); lcd.print(currentPresetZ, 2);
        if (wifiConnected && client && client.connected()) {
          client.print("PRESET:X:"); client.print(currentPresetX, 2);
          client.print(",Y:"); client.print(currentPresetY, 2);
          client.print(",Z:"); client.println(currentPresetZ, 2);
        }
      } else if (currentState == STATE_PRESET_MENU && selectedOption == 0) {
        currentState = STATE_IP_DISPLAY;
        lcd.clear();
        displayIPAddress();
      }
      delay(50); // Additional debounce
    }
  }

  if (digitalRead(scrollButtonPin) == LOW && currentTime - lastButtonPress > 200) {
    lastButtonPress = currentTime;
    if (currentState == STATE_PRESET_MENU) {
      selectedOption = (selectedOption + 1) % 7;
      lcd.clear();
      displayPresetMenu();
    }
    delay(50); // Additional debounce
  }

  switch (currentState) {
    case STATE_DEFAULT: {
      float xAngle = normalizeAngle(event.orientation.x);
      float yAngle = normalizeAngle(event.orientation.y);
      float zAngle = normalizeAngle(event.orientation.z);

      lcd.setCursor(0, 0); lcd.print("                ");
      lcd.setCursor(0, 0); lcd.print("X:"); lcd.print(xAngle, 2);
      lcd.setCursor(0, 1); lcd.print("                ");
      lcd.setCursor(0, 1); lcd.print("Y:"); lcd.print(yAngle, 2);
      lcd.setCursor(8, 1); lcd.print(" Z:"); lcd.print(zAngle, 2);

      if (wifiConnected && client && client.connected()) {
        client.print("X:"); client.print(xAngle, 2);
        client.print(",Y:"); client.print(yAngle, 2);
        client.print(",Z:"); client.println(zAngle, 2);
      }

      strip.clear();
      updateLEDsDefault(xAngle, 0, 6);
      updateLEDsDefault(yAngle, 7, 13);
      updateLEDsDefault(zAngle, 14, 20);
      strip.show();
      break;
    }

    case STATE_PRESET_MENU:
      break; // Handled by button press logic

    case STATE_PRESET_SELECTED: {
      float xAngle = normalizeAngle(event.orientation.x);
      float yAngle = normalizeAngle(event.orientation.y);
      float zAngle = normalizeAngle(event.orientation.z);

      lcd.setCursor(0, 0); lcd.print("                ");
      lcd.setCursor(0, 0); lcd.print("X:"); lcd.print(currentPresetX, 2);
      lcd.setCursor(0, 1); lcd.print("                ");
      lcd.setCursor(0, 1); lcd.print("Y:"); lcd.print(currentPresetY, 2);
      lcd.setCursor(8, 1); lcd.print(" Z:"); lcd.print(currentPresetZ, 2);

      if (wifiConnected && client && client.connected()) {
        client.print("X:"); client.print(xAngle, 2);
        client.print(",Y:"); client.print(yAngle, 2);
        client.print(",Z:"); client.println(zAngle, 2);
      }

      strip.clear();
      updateLEDs(xAngle, 0, 6, currentPresetX);
      updateLEDs(yAngle, 7, 13, currentPresetY);
      updateLEDs(zAngle, 14, 20, currentPresetZ);
      strip.show();
      break;
    }

    case STATE_IP_DISPLAY:
      displayIPAddress();
      break;
  }

  delay(20);
}

void updateLEDsDefault(float angle, int startIndex, int endIndex) {
  int centerIndex = (startIndex + endIndex) / 2;
  float normalizedAngle = angle;
  int ledOffset = constrain((int)(abs(normalizedAngle) / 60), 0, 3);
  int direction = (normalizedAngle >= 0) ? 1 : -1;

  strip.setPixelColor(centerIndex, strip.Color(0, 150, 0));
  for (int i = 1; i <= ledOffset; i++) {
    int ledIndex = centerIndex + (direction * i);
    if (ledIndex >= startIndex && ledIndex <= endIndex) {
      strip.setPixelColor(ledIndex, strip.Color(150, 0, 0));
    }
  }
}

void updateLEDs(float angle, int startIndex, int endIndex, float presetAngle) {
  int centerIndex = (startIndex + endIndex) / 2;
  float deviation = angle - presetAngle;
  int ledOffset = constrain((int)(abs(deviation) / 10), 0, 3);
  int direction = (deviation >= 0) ? 1 : -1;

  strip.setPixelColor(centerIndex, strip.Color(0, 150, 0));
  for (int i = 1; i <= ledOffset; i++) {
    int ledIndex = centerIndex + (direction * i);
    if (ledIndex >= startIndex && ledIndex <= endIndex) {
      strip.setPixelColor(ledIndex, strip.Color(150, 0, 0));
    }
  }

  if (abs(deviation) <= 0.5) {
    for (int i = startIndex; i <= endIndex; i++) {
      strip.setPixelColor(i, flashState ? strip.Color(0, 150, 0) : strip.Color(0, 0, 0));
    }
  }
}

void displayPresetMenu() {
  lcd.setCursor(0, 0);
  if (selectedOption == 0) {
    lcd.print("WiFi IP        ");
  } else {
    lcd.print("Preset ");
    lcd.print(selectedOption);
    lcd.print("       ");
  }
  lcd.setCursor(0, 1);
  lcd.print("Select with Enter");
}

void displayIPAddress() {
  lcd.setCursor(0, 0);
  lcd.print("IP             ");
  lcd.setCursor(0, 1);
  if (wifiConnected) {
    lcd.print(WiFi.localIP().toString());
    lcd.print("    ");
  } else {
    lcd.print("No WiFi Conn   ");
  }
}
