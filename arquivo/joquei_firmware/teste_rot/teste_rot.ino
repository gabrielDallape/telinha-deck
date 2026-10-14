// Mede o custo real de desenhar com a tela girada, para decidir se o painel do
// JOQUEI pode ficar em paisagem. O comentario do MTS falava de 719 ms por quadro.
#define MTS_SKIP_PANEL_ID 1
#include "LGFX_P4_LCD5.h"
LGFX_P4 tft;

static uint32_t mede(const char* nome, int rot, int repete, void (*fn)()) {
  tft.setRotation(rot);
  uint32_t t0 = millis();
  for (int i = 0; i < repete; i++) fn();
  uint32_t dt = millis() - t0;
  Serial.printf("%-28s rot=%d  %4u ms  (%u x, %.1f ms cada)\n",
                nome, rot, dt, repete, (float)dt / repete);
  return dt;
}

static void telaCheia()  { tft.fillScreen(random(0xFFFF)); }
static void botao()      { tft.fillRoundRect(20, 20, 240, 300, 22, random(0xFFFF)); }
static void botaoPaisagem(){ tft.fillRoundRect(20, 20, 300, 240, 22, random(0xFFFF)); }
static void texto()      { tft.setFont(&fonts::FreeSansBold18pt7b);
                           tft.drawString("JOQUEI 123", 40, 40); }

void setup() {
  Serial.begin(115200);
  delay(400);
  Serial.println("\n=== teste de custo de rotacao ===");
  if (!tft.init()) { Serial.println("painel nao subiu"); while (1) delay(1000); }
  tft.setBrightness(160);
  Serial.printf("painel %s\n\n", tft.panelName);

  mede("fillScreen", 0, 5, telaCheia);
  mede("fillScreen", 1, 5, telaCheia);
  mede("fillScreen", 2, 5, telaCheia);
  Serial.println();
  mede("botao 240x300", 0, 20, botao);
  mede("botao 240x300", 1, 20, botao);
  Serial.println();
  mede("botao 300x240", 0, 20, botaoPaisagem);
  mede("botao 300x240", 1, 20, botaoPaisagem);
  Serial.println();
  mede("drawString", 0, 20, texto);
  mede("drawString", 1, 20, texto);
  Serial.println("\n=== fim ===");
}
void loop() { delay(1000); }
