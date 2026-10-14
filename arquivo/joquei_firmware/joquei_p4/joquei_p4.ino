/*
 * JOQUEI - painel de atalhos touch para o PC, na Waveshare ESP32-P4-WIFI6-Touch-LCD-5.
 *
 * A tela pede uma pagina por id, estampa a arte que o PC manda, e devolve o id do
 * botao tocado. O agente Python executa e responde o ESTADO real da maquina (mic
 * mutado, volume) - e o que separa isto de um teclado de macros: o painel diz a
 * verdade sobre o PC.
 *
 * NADA DE CONTEUDO NEM DE VISUAL MORA AQUI. Quem compoe cada botao - gradiente,
 * canto arredondado, logo do app, capa do album, tipografia - e o
 * Pillow no PC, que tem antialiasing, alpha e as fontes da Microsoft. A LovyanGFX
 * desenha rapido mas desenha duro; icone feito com fillTriangle parece icone feito
 * com fillTriangle. Aqui a placa so estampa bitmap e desenha os ESTADOS por cima
 * (apertado, aceso), que precisam ser instantaneos e nao valem uma ida a serial.
 *
 * Efeito colateral: mexer no visual nao exige regravar a placa.
 *
 * A arte chega como JPEG e e decodificada UMA VEZ para um sprite na PSRAM. JPEG
 * porque RGB565 cru seriam 252 KB por card - uma pagina de 10 levaria 60 s
 * para aparecer. Em JPEG sao ~35 KB e a pagina entra em menos de um segundo.
 *
 * PAISAGEM: medido nesta placa (firmware/teste_rot) - fillScreen custa 16,4 ms
 * igual em rot 0 e rot 1. O comentario do MTS sobre 719 ms por quadro girado NAO
 * se reproduz aqui.
 *
 * Serial: UART0 -> ponte CH343 -> COM8, a 921600. Depende de CDCOnBoot=default.
 * NAO subir para 2 Mbps: medido, a ponte corrompe caracteres e o base64 chega
 * com buracos (ver o retry por "imgbad").
 *
 * Compilar e gravar (do diretorio JOQUEI):
 *   .\firmware\build.ps1 -Upload -Port COM8
 */
#define MTS_SKIP_PANEL_ID 1     // este painel TRAVA se voce ler o ID dele
#include "LGFX_P4_LCD5.h"
#include "ui_botoes.h"

LGFX_P4 tft;

// ----------------------------------------------------------------- geometria
// Tem de casar com paginas.py, que calcula o tamanho da arte a partir daqui.
static constexpr int TELA_W   = 1280;
static constexpr int TELA_H   = 720;
static constexpr int BARRA_H  = 72;
static constexpr int MARGEM   = 8;
static constexpr int VOLTAR_W = 108;
static constexpr int MAX_BTN  = 20;
// Slots de sprite na PSRAM. O PC precarrega todas as paginas; hoje sao ~20
// cards, entao o limite so importa quando o conteudo crescer. Quando o cache
// enche, o sprite menos usado sai (imgout).
static constexpr int MAX_ARTE = 96;

// -------------------------------------------------------------------- estado
struct Arte {
  char         id[72]   = "";
  uint16_t     w = 0, h = 0;
  uint8_t*     jpg = nullptr;    // buffer temporario, so durante a recepcao
  uint32_t     jpgLen = 0, jpgRecebido = 0;
  LGFX_Sprite* spr = nullptr;
  uint32_t     usadoEm = 0;
  bool         pronto = false;
};

struct Botao {
  char   id[72]       = "";
  char   arte[72]     = "";
  char   arteOn[72]   = "";
  char   stateKey[20] = "";
  bool   aceso        = false;
  bool   apertado     = false;
  bool   sujo         = true;
};

static Arte  g_arte[MAX_ARTE];
static Botao g_btn[MAX_BTN];
static int   g_nBtn = 0;
static int   g_cols = 5, g_rows = 2;

static char g_pagina[72] = "";
static char g_titulo[56] = "";
static char g_back[72]   = "";

static bool     g_online      = false;
static uint32_t g_ultimaMsg   = 0;
static uint32_t g_ultimoHello = 0;
static bool     g_temPagina   = false;
static bool     g_barraSuja   = true;
static int      g_micVol = -1, g_sysVol = -1;
static bool     g_micMudo = false;
static char     g_aviso[44] = "";
static uint32_t g_avisoAte  = 0;
static uint32_t g_relogio   = 0;   // contador de uso, para saber o sprite mais velho

// ------------------------------------------------------- parser JSON minimo

static const char* jsonValor(const char* j, const char* chave) {
  char alvo[40];
  snprintf(alvo, sizeof(alvo), "\"%s\"", chave);
  const char* p = strstr(j, alvo);
  if (!p) return nullptr;
  p += strlen(alvo);
  while (*p == ' ' || *p == ':') p++;
  return p;
}

static bool jsonStr(const char* j, const char* chave, char* out, size_t n) {
  const char* p = jsonValor(j, chave);
  if (!p || *p != '"') return false;
  p++;
  size_t i = 0;
  while (*p && *p != '"' && i < n - 1) out[i++] = *p++;
  out[i] = 0;
  return true;
}

static bool jsonBool(const char* j, const char* chave, bool* out) {
  const char* p = jsonValor(j, chave);
  if (!p) return false;
  if (!strncmp(p, "true", 4))  { *out = true;  return true; }
  if (!strncmp(p, "false", 5)) { *out = false; return true; }
  return false;
}

static bool jsonInt(const char* j, const char* chave, int* out) {
  const char* p = jsonValor(j, chave);
  if (!p || (*p != '-' && (*p < '0' || *p > '9'))) return false;
  *out = atoi(p);
  return true;
}

static const char* jsonProxObj(const char* p, const char** fim) {
  while (*p && *p != '{' && *p != ']') p++;
  if (*p != '{') return nullptr;
  const char* ini = p;
  int nivel = 0;
  bool naStr = false;
  for (; *p; p++) {
    if (naStr) { if (*p == '"') naStr = false; continue; }
    if (*p == '"') naStr = true;
    else if (*p == '{') nivel++;
    else if (*p == '}' && --nivel == 0) { *fim = p + 1; return ini; }
  }
  return nullptr;
}

// ------------------------------------------------------------------- base64

static inline int b64val(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}

static uint32_t b64decode(const char* s, uint8_t* out, uint32_t max) {
  uint32_t n = 0;
  int acc = 0, bits = 0;
  for (; *s; s++) {
    int v = b64val(*s);
    if (v < 0) continue;
    acc = (acc << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      if (n < max) out[n++] = (acc >> bits) & 0xFF;
    }
  }
  return n;
}

// --------------------------------------------------------------- cache de arte

static int achaArte(const char* id) {
  if (!id || !*id) return -1;
  for (int i = 0; i < MAX_ARTE; i++)
    if (g_arte[i].id[0] && !strcmp(g_arte[i].id, id)) return i;
  return -1;
}

static void liberaArte(Arte& a) {
  if (a.jpg) { free(a.jpg); a.jpg = nullptr; }
  if (a.spr) { a.spr->deleteSprite(); delete a.spr; a.spr = nullptr; }
  a.id[0] = 0;
  a.pronto = false;
  a.jpgLen = a.jpgRecebido = 0;
}

// Slot livre, ou o sprite usado ha mais tempo (LRU).
static int slotDeArte() {
  for (int i = 0; i < MAX_ARTE; i++)
    if (!g_arte[i].id[0]) return i;
  int pior = 0;
  for (int i = 1; i < MAX_ARTE; i++)
    if (g_arte[i].usadoEm < g_arte[pior].usadoEm) pior = i;
  Serial.printf("[arte] cache cheio, descartando %s\n", g_arte[pior].id);
  liberaArte(g_arte[pior]);
  return pior;
}

// ------------------------------------------------------------------- desenho

static void celula(int i, int* x, int* y, int* w, int* h) {
  int cw = TELA_W / g_cols;
  int ch = (TELA_H - BARRA_H) / g_rows;
  *x = (i % g_cols) * cw;
  *y = BARRA_H + (i / g_cols) * ch;
  *w = cw; *h = ch;
}

static void desenhaBotao(int i) {
  Botao& b = g_btn[i];
  int x, y, w, h;
  celula(i, &x, &y, &w, &h);
  int bx = x + MARGEM, by = y + MARGEM;
  int bw = w - MARGEM * 2, bh = h - MARGEM * 2;

  const char* quer = (b.aceso && b.arteOn[0]) ? b.arteOn : b.arte;
  int idx = achaArte(quer);

  if (idx >= 0 && g_arte[idx].pronto) {
    g_arte[idx].usadoEm = ++g_relogio;
    g_arte[idx].spr->pushSprite(bx, by);
  } else {
    // arte ainda vindo: pastilha neutra, nao um buraco preto
    tft.fillRect(x, y, w, h, JQ_FUNDO);
    tft.fillRoundRect(bx, by, bw, bh, 26, cor565(0x161B22));
    tft.drawRoundRect(bx, by, bw, bh, 26, cor565(0x21262D));
  }

  // Estados por cima da arte: instantaneos, sem ida a serial.
  if (b.apertado) {
    for (int k = 0; k < 4; k++)
      tft.drawRoundRect(bx + k, by + k, bw - 2 * k, bh - 2 * k, 26 - k,
                        cor565(0xFFFFFF));
  }
  b.sujo = false;
}

static void desenhaBarra() {
  tft.fillRect(0, 0, TELA_W, BARRA_H, JQ_BARRA);
  tft.fillRect(0, BARRA_H - 2, TELA_W, 2, cor565(0x21262D));

  int xTexto = 24;
  if (g_back[0]) {
    uint16_t c = JQ_TEXTO;
    int cx = 44, cy = BARRA_H / 2;
    for (int i = 0; i < 5; i++) {
      tft.drawLine(cx + 11, cy - 15 + i, cx - 6 + i, cy, c);
      tft.drawLine(cx - 6 + i, cy, cx + 11, cy + 15 - i, c);
    }
    tft.drawFastVLine(cx + 46, 14, BARRA_H - 28, cor565(0x30363D));
    xTexto = 72;
  }

  tft.setTextDatum(middle_left);
  tft.setFont(&fonts::FreeSansBold18pt7b);
  tft.setTextColor(JQ_TEXTO, JQ_BARRA);
  tft.drawString(g_titulo[0] ? g_titulo : "JOQUEI", xTexto, BARRA_H / 2);

  tft.fillCircle(TELA_W - 28, BARRA_H / 2, 9, g_online ? JQ_OK : JQ_ACESO);

  tft.setFont(&fonts::FreeSans9pt7b);
  tft.setTextDatum(middle_right);
  char txt[64];
  uint16_t corTxt = JQ_TEXTO_FRACO;
  if (g_aviso[0] && millis() < g_avisoAte) {
    snprintf(txt, sizeof(txt), "%s", g_aviso);
    corTxt = JQ_ACESO;
  } else if (!g_online) {
    snprintf(txt, sizeof(txt), "agente offline");
  } else if (g_sysVol >= 0) {
    if (g_micMudo) snprintf(txt, sizeof(txt), "vol %d%%   mic MUDO", g_sysVol);
    else           snprintf(txt, sizeof(txt), "vol %d%%   mic %d%%", g_sysVol, g_micVol);
  } else {
    snprintf(txt, sizeof(txt), "conectado");
  }
  tft.setTextColor(corTxt, JQ_BARRA);
  tft.drawString(txt, TELA_W - 46, BARRA_H / 2);
  g_barraSuja = false;
}

static void desenhaTudo() {
  tft.fillScreen(JQ_FUNDO);
  desenhaBarra();
  for (int i = 0; i < g_nBtn; i++) desenhaBotao(i);
}

static void avisa(const char* msg) {
  snprintf(g_aviso, sizeof(g_aviso), "%s", msg);
  g_avisoAte = millis() + 4000;
  g_barraSuja = true;
}

// ------------------------------------------------------------------- serial

static void pedePagina(const char* pid) {
  Serial.printf("{\"cmd\":\"page\",\"id\":\"%s\"}\n", pid);
}

static void enviaHello() {
  // Vai com a pagina atual: se o PC reiniciou e a placa ja esta desenhada, ele
  // retoma daqui em vez de jogar o usuario de volta para a home.
  Serial.printf("{\"cmd\":\"hello\",\"fw\":\"joquei-0.4\",\"page\":\"%s\"}\n", g_pagina);
  g_ultimoHello = millis();
}

static void aplicaLayout(const char* j) {
  jsonStr(j, "page",  g_pagina, sizeof(g_pagina));
  if (!jsonStr(j, "title", g_titulo, sizeof(g_titulo))) g_titulo[0] = 0;
  if (!jsonStr(j, "back",  g_back,  sizeof(g_back)))    g_back[0] = 0;

  int v;
  g_cols = (jsonInt(j, "cols", &v) && v > 0 && v <= 6) ? v : 5;
  g_rows = (jsonInt(j, "rows", &v) && v > 0 && v <= 4) ? v : 2;

  const char* arr = jsonValor(j, "buttons");
  int n = 0;
  if (arr) {
    const char* p = arr;
    const char* fim;
    while (n < MAX_BTN && n < g_cols * g_rows) {
      const char* obj = jsonProxObj(p, &fim);
      if (!obj) break;
      Botao& b = g_btn[n];
      b = Botao();
      jsonStr(obj, "id",        b.id,       sizeof(b.id));
      jsonStr(obj, "art",       b.arte,     sizeof(b.arte));
      jsonStr(obj, "art_on",    b.arteOn,   sizeof(b.arteOn));
      jsonStr(obj, "state_key", b.stateKey, sizeof(b.stateKey));
      n++;
      p = fim;
    }
  }
  g_nBtn = n;
  g_temPagina = true;
  Serial.printf("[pagina] %s: %d botoes, grade %dx%d\n", g_pagina, n, g_cols, g_rows);
  desenhaTudo();
}

static void aplicaImagem(char* j) {
  char id[72] = "";
  int w = 0, h = 0, i = 0, n = 1, tam = 0, off = 0;
  if (!jsonStr(j, "id", id, sizeof(id))) return;
  jsonInt(j, "w", &w); jsonInt(j, "h", &h);
  jsonInt(j, "i", &i); jsonInt(j, "n", &n); jsonInt(j, "len", &tam);
  jsonInt(j, "off", &off);
  if (w <= 0 || h <= 0 || tam <= 0) return;

  int idx = achaArte(id);

  // i = -1 e sondagem: o PC quer saber se ja temos esta arte antes de gastar a
  // serial com ela. Confere o tamanho tambem, senao uma arte reeditada no PC
  // ficaria velha na tela para sempre.
  if (i < 0) {
    bool tem = (idx >= 0 && g_arte[idx].pronto && g_arte[idx].jpgLen == (uint32_t)tam);
    if (tem) g_arte[idx].usadoEm = ++g_relogio;
    Serial.printf("{\"cmd\":\"imgok\",\"i\":-1,\"tem\":%s}\n", tem ? "true" : "false");
    return;
  }

  if (i == 0) {
    if (idx >= 0) liberaArte(g_arte[idx]);        // reenvio: comeca limpo
    idx = slotDeArte();
    Arte& a = g_arte[idx];
    strncpy(a.id, id, sizeof(a.id) - 1);
    a.w = w; a.h = h;
    a.jpgLen = tam; a.jpgRecebido = 0;
    a.jpg = (uint8_t*)ps_malloc(tam);
    a.usadoEm = ++g_relogio;
    if (!a.jpg) {
      Serial.printf("[arte] %s: sem PSRAM para %d bytes\n", id, tam);
      a.id[0] = 0;
      return;
    }
  }
  if (idx < 0 || !g_arte[idx].jpg) return;
  Arte& a = g_arte[idx];

  const char* d = jsonValor(j, "d");
  if (!d || *d != '"') return;
  d++;
  char* fimStr = (char*)strchr(d, '"');
  if (!fimStr) return;
  *fimStr = 0;
  // Escreve no deslocamento que o PC informou, nao onde paramos. Assim reenviar
  // um pedaco (confirmacao perdida) sobrescreve em vez de duplicar - era o que
  // corrompia o JPEG de vez em quando.
  if ((uint32_t)off >= a.jpgLen) return;
  uint32_t escreveu = b64decode(d, a.jpg + off, a.jpgLen - off);
  uint32_t fim = (uint32_t)off + escreveu;
  if (fim > a.jpgRecebido) a.jpgRecebido = fim;

  // Controle de fluxo: o PC so manda o proximo pedaco depois deste aviso. Buffer
  // grande sozinho nao basta - a arte e maior que qualquer buffer razoavel, e a
  // placa para de ler a serial enquanto decodifica.
  Serial.printf("{\"cmd\":\"imgok\",\"i\":%d}\n", i);

  if (i < n - 1) return;

  // Chegou o ultimo pedaco: o tamanho tem de fechar exatamente. Se nao fecha,
  // faltou dado no caminho - e dizer QUANTO faltou e o que separa "perdi bytes
  // na serial" de "o JPEG em si esta ruim".
  if (a.jpgRecebido != a.jpgLen) {
    Serial.printf("[arte] %s: faltaram %d bytes (%u de %u)\n", id,
                  (int)a.jpgLen - (int)a.jpgRecebido, a.jpgRecebido, a.jpgLen);
    Serial.printf("{\"cmd\":\"imgbad\",\"id\":\"%s\"}\n", id);
    liberaArte(a);
    return;
  }

  // Chegou inteira: decodifica UMA vez para sprite na PSRAM e joga o JPEG fora.
  a.spr = new LGFX_Sprite(&tft);
  a.spr->setPsram(true);
  a.spr->setColorDepth(16);
  // Se a PSRAM acabou, abre espaco jogando fora os sprites menos usados em vez
  // de simplesmente desistir - com 96 cards de tamanhos diferentes, "cabe" nao
  // e uma conta que se faz de antemao.
  int tentativas = 0;
  while (!a.spr->createSprite(a.w, a.h)) {
    int pior = -1;
    for (int k = 0; k < MAX_ARTE; k++) {
      if (&g_arte[k] == &a || !g_arte[k].pronto) continue;
      if (pior < 0 || g_arte[k].usadoEm < g_arte[pior].usadoEm) pior = k;
    }
    if (pior < 0 || ++tentativas > 12) {
      Serial.printf("[arte] %s: sem PSRAM para %ux%u\n", id, a.w, a.h);
      liberaArte(a);
      return;
    }
    Serial.printf("[arte] PSRAM cheia, descartando %s\n", g_arte[pior].id);
    liberaArte(g_arte[pior]);
  }
  bool ok = a.spr->drawJpg(a.jpg, a.jpgRecebido, 0, 0);
  free(a.jpg); a.jpg = nullptr;
  if (!ok) {
    Serial.printf("[arte] %s: jpeg invalido (%u bytes)\n", id, a.jpgRecebido);
    Serial.printf("{\"cmd\":\"imgbad\",\"id\":\"%s\"}\n", id);
    liberaArte(a);
    return;
  }
  a.pronto = true;
  Serial.printf("[arte] %s pronta: %ux%u, %u bytes\n", id, a.w, a.h, a.jpgRecebido);

  for (int k = 0; k < g_nBtn; k++)
    if (!strcmp(g_btn[k].arte, id) || !strcmp(g_btn[k].arteOn, id))
      g_btn[k].sujo = true;
}

static void aplicaEstado(const char* j) {
  int v;
  if (jsonInt(j, "sys_vol", &v) && v != g_sysVol) { g_sysVol = v; g_barraSuja = true; }
  if (jsonInt(j, "mic_vol", &v) && v != g_micVol) { g_micVol = v; g_barraSuja = true; }
  bool on;
  if (jsonBool(j, "mic_muted", &on) && on != g_micMudo) { g_micMudo = on; g_barraSuja = true; }

  for (int i = 0; i < g_nBtn; i++) {
    if (!g_btn[i].stateKey[0]) continue;
    if (jsonBool(j, g_btn[i].stateKey, &on) && on != g_btn[i].aceso) {
      g_btn[i].aceso = on;
      g_btn[i].sujo  = true;
    }
  }
}

static void processaLinha(char* linha) {
  g_ultimaMsg = millis();
  if (!g_online) { g_online = true; g_barraSuja = true; }

  char ev[16] = "";
  if (!jsonStr(linha, "ev", ev, sizeof(ev))) return;

  if      (!strcmp(ev, "layout")) aplicaLayout(linha);
  else if (!strcmp(ev, "img"))    aplicaImagem(linha);
  else if (!strcmp(ev, "state"))  aplicaEstado(linha);
  else if (!strcmp(ev, "quem")) enviaHello();
  else if (!strcmp(ev, "err")) {
    char msg[36] = "";
    jsonStr(linha, "msg", msg, sizeof(msg));
    avisa(msg);
  }
}

static void leSerial() {
  static char buf[12288];         // um pedaco de arte e ~9 KB de base64 numa linha
  static size_t n = 0;
  static bool estourou = false;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (n && !estourou) { buf[n] = 0; processaLinha(buf); }
      n = 0; estourou = false;
    } else if (n < sizeof(buf) - 1) {
      buf[n++] = c;
    } else {
      estourou = true;   // descarta a linha inteira em vez de processar truncado
      n = 0;
    }
  }
}

// -------------------------------------------------------------------- toque

static void leToque() {
  static int apertado = -1;
  static uint32_t soltouEm = 0;
  static bool voltarApertado = false;

  int32_t x, y;
  bool tocando = tft.getTouch(&x, &y);

  if (tocando && apertado < 0 && !voltarApertado && millis() - soltouEm > 120) {
    if (y < BARRA_H) {
      if (g_back[0] && x < VOLTAR_W) {
        voltarApertado = true;
        pedePagina(g_back);
      }
      return;
    }
    int cw = TELA_W / g_cols;
    int ch = (TELA_H - BARRA_H) / g_rows;
    int col = x / cw, lin = (y - BARRA_H) / ch;
    if (col >= g_cols || lin >= g_rows) return;
    int i = lin * g_cols + col;
    if (i < 0 || i >= g_nBtn) return;

    apertado = i;
    g_btn[i].apertado = true;
    desenhaBotao(i);                    // feedback antes de mandar, nao depois
    Serial.printf("{\"cmd\":\"btn\",\"page\":\"%s\",\"id\":\"%s\"}\n",
                  g_pagina, g_btn[i].id);

  } else if (!tocando) {
    if (apertado >= 0) {
      int i = apertado;
      apertado = -1;
      soltouEm = millis();
      // a pagina pode ter trocado enquanto o dedo ainda estava na tela
      if (i < g_nBtn) { g_btn[i].apertado = false; desenhaBotao(i); }
    }
    if (voltarApertado) { voltarApertado = false; soltouEm = millis(); }
  }
}

// -------------------------------------------------------------------- setup

void setup() {
  // ANTES do begin, e nao opcional: o padrao e 256 bytes, e a 2 Mbps cada delay()
  // do loop perderia milhares de bytes no meio de um JSON.
  Serial.setRxBufferSize(16384);
  Serial.begin(921600);
  delay(300);
  Serial.println("\n=== JOQUEI - painel de atalhos ESP32-P4 ===");

  if (!tft.init()) {
    Serial.println("[erro] painel nao subiu");
    while (true) delay(1000);
  }
  tft.setRotation(1);              // paisagem 1280x720 (medido: mesmo custo que 0)
  tft.setBrightness(200);
  Serial.printf("painel %s %dx%d | psram livre %u\n",
                tft.panelName, tft.width(), tft.height(),
                (unsigned)ESP.getFreePsram());

  tft.fillScreen(JQ_FUNDO);
  strcpy(g_titulo, "JOQUEI");
  desenhaBarra();
  tft.setFont(&fonts::FreeSans9pt7b);
  tft.setTextDatum(middle_center);
  tft.setTextColor(JQ_TEXTO_FRACO, JQ_FUNDO);
  tft.drawString("esperando o agente no PC...", TELA_W / 2, TELA_H / 2);

  enviaHello();
}

void loop() {
  leSerial();
  leToque();

  if (!g_temPagina && millis() - g_ultimoHello > 1500) enviaHello();

  if (g_online && millis() - g_ultimaMsg > 6000) {
    g_online = false;
    g_barraSuja = true;
  }
  if (g_aviso[0] && millis() > g_avisoAte) { g_aviso[0] = 0; g_barraSuja = true; }

  if (g_barraSuja) desenhaBarra();
  for (int i = 0; i < g_nBtn; i++) if (g_btn[i].sujo) desenhaBotao(i);

  // Nao dorme com dados na fila: cada ms de sono e centenas de bytes perdidos.
  if (!Serial.available()) delay(3);
}
