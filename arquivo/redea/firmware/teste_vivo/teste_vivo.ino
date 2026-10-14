/*
 * Sketch minimo: existe so para responder uma pergunta.
 *
 * A placa nova entra em boot loop (CHIP_LP_WDT_RESET) tanto com o firmware do
 * REDEA quanto com o do JOQUEI, que roda em quatro outras placas. Trava antes
 * de qualquer saida serial, entao nao da para saber onde.
 *
 * Aqui nao ha display, nao ha LGFX, nao ha nada: so serial e um contador. Se
 * isto imprimir, a placa esta viva e o problema e o painel. Se nao imprimir
 * nem isto, o problema e mais fundo (PSRAM, clock, alimentacao).
 */
void setup() {
  Serial.begin(921600);
  delay(300);
  Serial.println("\n=== teste_vivo: a placa chegou ao setup ===");
  Serial.printf("psram: %u bytes\n", (unsigned) ESP.getPsramSize());
  Serial.printf("flash: %u bytes\n", (unsigned) ESP.getFlashChipSize());
  Serial.printf("cpu:   %u MHz\n", (unsigned) getCpuFrequencyMhz());
}

void loop() {
  static uint32_t n = 0;
  Serial.printf("vivo %u  uptime %lu ms\n", n++, (unsigned long) millis());
  delay(1000);
}
