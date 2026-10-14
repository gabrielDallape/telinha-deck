// Desenho da grade de botoes da TELINHA.
//
// Os icones sao VETORIAIS, feitos com primitivas da LovyanGFX. Nao ha fonte de
// icones nem PNG embarcado de proposito: cada icone custa ~10 linhas e zero flash,
// e escala para qualquer tamanho de botao sem serrilhar. Numa tela de 720x1280 com
// grade 3x4 o botao tem 240x302 - icone de 96 px fica confortavel.
//
// As funcoes sao template no tipo do canvas para aceitar tanto o LGFX_P4 quanto um
// LGFX_Sprite sem precisar acertar qual e a classe base exata da LovyanGFX v1.
#pragma once
#include <LovyanGFX.hpp>

// ------------------------------------------------------------------- paleta

static inline uint16_t cor565(uint32_t rgb) {
  return lgfx::color565((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF);
}

// "#5865F2" -> RGB565. Aceita com ou sem '#'; devolve o padrao se vier torto.
static inline uint16_t corHex(const char* s, uint16_t padrao) {
  if (!s || !*s) return padrao;
  if (*s == '#') s++;
  uint32_t v = 0; int n = 0;
  for (; n < 6 && s[n]; n++) {
    char c = s[n]; uint8_t d;
    if      (c >= '0' && c <= '9') d = c - '0';
    else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
    else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
    else return padrao;
    v = (v << 4) | d;
  }
  return (n == 6) ? cor565(v) : padrao;
}

// Magenta puro: o "vazio" dos bitmaps que o PC manda (ver agent/icones.py).
// Nenhum logo real usa exatamente este valor - e o agente desvia quem chegar perto.
#define COR_CHAVE_565 0xF81F

#define JQ_FUNDO      cor565(0x0E1116)
#define JQ_BARRA      cor565(0x161B22)
#define JQ_TEXTO      cor565(0xE6EDF3)
#define JQ_TEXTO_FRACO cor565(0x8B949E)
#define JQ_ACESO      cor565(0xE5484D)
#define JQ_OK         cor565(0x30A46C)

// ------------------------------------------------------------------- icones
// Todos desenham centrados em (cx,cy) dentro de uma caixa de lado `t`.

template <typename G> void icoChat(G& g, int cx, int cy, int t, uint16_t c) {
  int w = t, h = t * 7 / 10;
  g.fillRoundRect(cx - w / 2, cy - h / 2 - t / 10, w, h, t / 6, c);
  // cauda do balao, no canto de baixo a esquerda
  g.fillTriangle(cx - w / 4, cy + h / 2 - t / 10, cx - w / 8, cy + h / 2 - t / 10,
                 cx - w / 3, cy + h / 2 + t / 6, c);
}

template <typename G> void icoGlobo(G& g, int cx, int cy, int t, uint16_t c) {
  int r = t / 2;
  g.drawCircle(cx, cy, r, c);
  g.drawCircle(cx, cy, r - 1, c);
  g.drawFastHLine(cx - r, cy, r * 2, c);
  g.drawFastHLine(cx - r * 9 / 10, cy - r / 2, r * 18 / 10, c);
  g.drawFastHLine(cx - r * 9 / 10, cy + r / 2, r * 18 / 10, c);
  g.drawEllipse(cx, cy, r / 2, r, c);   // meridiano
}

template <typename G> void icoGamepad(G& g, int cx, int cy, int t, uint16_t c) {
  int w = t, h = t * 6 / 10;
  g.fillRoundRect(cx - w / 2, cy - h / 2, w, h, h / 2, c);
  // recortes em cor de fundo formam o direcional e os botoes
  uint16_t f = JQ_FUNDO;
  int dx = cx - w / 4, dy = cy;
  g.fillRect(dx - t / 12, dy - t / 32, t / 6, t / 16, f);
  g.fillRect(dx - t / 32, dy - t / 12, t / 16, t / 6, f);
  g.fillCircle(cx + w / 4 + t / 12, cy - t / 16, t / 20, f);
  g.fillCircle(cx + w / 4 - t / 12, cy + t / 16, t / 20, f);
}

template <typename G> void icoMic(G& g, int cx, int cy, int t, uint16_t c) {
  int cw = t * 7 / 20, ch = t * 11 / 20;
  int top = cy - t * 9 / 20;
  g.fillRoundRect(cx - cw / 2, top, cw, ch, cw / 2, c);     // capsula
  int r = t * 7 / 20;
  for (int i = 0; i < t / 24 + 2; i++)                       // arco do suporte
    g.drawArc(cx, top + ch - r / 2, r - i, r - i, 20, 160, c);
  g.fillRect(cx - t / 40, top + ch + r / 3, t / 20 + 1, t / 8, c);  // haste
  g.fillRect(cx - t / 5, cy + t * 9 / 20, t * 2 / 5, t / 20 + 1, c); // base
}

template <typename G> void icoVolume(G& g, int cx, int cy, int t, uint16_t c,
                                     int ondas = 2) {
  int x = cx - t / 3;
  g.fillRect(x, cy - t / 8, t / 6, t / 4, c);                 // corpo
  g.fillTriangle(x + t / 6, cy - t / 8, x + t / 6, cy + t / 8,
                 x + t / 2, cy + t / 3, c);                   // cone (baixo)
  g.fillTriangle(x + t / 6, cy - t / 8, x + t / 2, cy - t / 3,
                 x + t / 2, cy + t / 3, c);                   // cone (cima)
  for (int i = 1; i <= ondas; i++) {                          // ondas sonoras
    int r = t / 4 + i * t / 8;
    for (int k = 0; k < 2; k++) g.drawArc(x + t / 2, cy, r - k, r - k, -55, 55, c);
  }
}

template <typename G> void icoVolMais(G& g, int cx, int cy, int t, uint16_t c) {
  icoVolume(g, cx - t / 8, cy, t * 8 / 10, c, 0);
  int px = cx + t * 3 / 10, e = t / 5;
  g.fillRect(px - e / 2, cy - t / 24, e, t / 12 + 1, c);
  g.fillRect(px - t / 24, cy - e / 2, t / 12 + 1, e, c);
}

template <typename G> void icoVolMenos(G& g, int cx, int cy, int t, uint16_t c) {
  icoVolume(g, cx - t / 8, cy, t * 8 / 10, c, 0);
  int px = cx + t * 3 / 10, e = t / 5;
  g.fillRect(px - e / 2, cy - t / 24, e, t / 12 + 1, c);
}

template <typename G> void icoPlay(G& g, int cx, int cy, int t, uint16_t c) {
  g.fillTriangle(cx - t / 4, cy - t / 3, cx - t / 4, cy + t / 3, cx + t / 3, cy, c);
}

template <typename G> void icoNext(G& g, int cx, int cy, int t, uint16_t c) {
  g.fillTriangle(cx - t / 3, cy - t / 3, cx - t / 3, cy + t / 3, cx + t / 12, cy, c);
  g.fillRect(cx + t / 6, cy - t / 3, t / 10 + 1, t * 2 / 3, c);
}

template <typename G> void icoImagem(G& g, int cx, int cy, int t, uint16_t c) {
  int w = t, h = t * 8 / 10;
  int x = cx - w / 2, y = cy - h / 2;
  g.drawRoundRect(x, y, w, h, t / 12, c);
  g.drawRoundRect(x + 1, y + 1, w - 2, h - 2, t / 12, c);
  g.fillCircle(x + w / 4, y + h / 3, t / 14, c);              // sol
  g.fillTriangle(x + w / 6, y + h - 3, x + w / 2, y + h / 3,
                 x + w - 3, y + h - 3, c);                    // montanha
}

template <typename G> void icoLock(G& g, int cx, int cy, int t, uint16_t c) {
  int w = t * 7 / 10, h = t * 5 / 10;
  g.fillRoundRect(cx - w / 2, cy - h / 6, w, h, t / 12, c);   // corpo
  int r = t / 4;
  for (int i = 0; i < t / 20 + 2; i++)                        // aro
    g.drawArc(cx, cy - h / 6, r - i, r - i, 180, 360, c);
  g.fillCircle(cx, cy + h / 6, t / 22, JQ_FUNDO);             // furo da chave
}

template <typename G> void icoDot(G& g, int cx, int cy, int t, uint16_t c) {
  g.fillCircle(cx, cy, t / 5, c);
}

// Barra diagonal de "cortado" - usada quando o botao esta com o estado ativo
// (mic mutado, audio mutado). E o que faz a tela dizer a verdade sobre o PC.
template <typename G> void icoCortado(G& g, int cx, int cy, int t, uint16_t c) {
  int r = t / 2;
  for (int i = -(t / 24 + 1); i <= t / 24 + 1; i++)
    g.drawLine(cx - r + i, cy - r, cx + r + i, cy + r, c);
}

// Despacha pelo nome vindo do config.json do PC.
template <typename G>
void desenhaIcone(G& g, const char* nome, int cx, int cy, int t, uint16_t c) {
  if      (!strcmp(nome, "chat"))        icoChat(g, cx, cy, t, c);
  else if (!strcmp(nome, "globe"))       icoGlobo(g, cx, cy, t, c);
  else if (!strcmp(nome, "gamepad"))     icoGamepad(g, cx, cy, t, c);
  else if (!strcmp(nome, "mic"))         icoMic(g, cx, cy, t, c);
  else if (!strcmp(nome, "volume"))      icoVolume(g, cx, cy, t, c);
  else if (!strcmp(nome, "volume_up"))   icoVolMais(g, cx, cy, t, c);
  else if (!strcmp(nome, "volume_down")) icoVolMenos(g, cx, cy, t, c);
  else if (!strcmp(nome, "play"))        icoPlay(g, cx, cy, t, c);
  else if (!strcmp(nome, "next"))        icoNext(g, cx, cy, t, c);
  else if (!strcmp(nome, "image"))       icoImagem(g, cx, cy, t, c);
  else if (!strcmp(nome, "lock"))        icoLock(g, cx, cy, t, c);
  else                                   icoDot(g, cx, cy, t, c);
}
