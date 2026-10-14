// Panel_HX8394 - driver LovyanGFX para o painel das telas Waveshare ESP32-P4.
//
// POR QUE ESTE ARQUIVO EXISTE: a LovyanGFX traz Panel_ILI9881C, Panel_EK79007 e
// Panel_ST7123 para P4, mas NAO o HX8394 - que e o controlador que a Waveshare
// monta na ESP32-P4-WIFI6-Touch-LCD-5. Sem a sequencia de fabricante certa, o
// painel fica PRETO com o backlight aceso (medido: com a sequencia do ILI9881C o
// barramento ate TRAVA no primeiro writeParams).
//
// Como o modelo foi descoberto: o esquematico da Waveshare nao diz (o controlador
// fica no FPC do painel), e o painel nao responde a leitura de ID por DBI - o
// readParams(0xF4) trava. A resposta veio do codigo oficial: todos os exemplos de
// display de github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-5 usam o componente
// esp_lcd_hx8394.
//
// A sequencia e os timings abaixo sao transcritos de:
//   examples/esp-idf/07_Displaycolorbar/components/esp_lcd_hx8394/
//     esp_lcd_hx8394.c            -> vendor_specific_init_code_default[]
//     include/esp_lcd_hx8394.h    -> HX8394_720_1280_PANEL_30HZ_DPI_CONFIG
//                                    e HX8394_PANEL_BUS_DSI_2CH_CONFIG
#pragma once
#include "lgfx/v1/platforms/esp32p4/Panel_DSI.hpp"

#if SOC_MIPI_DSI_SUPPORTED

// Parametros do barramento e do DPI, do header oficial da Waveshare.
// NAO chute estes numeros: com lane 960 Mbps / DPI 80 MHz (valores do M5Tab5, que
// usa ILI9881C) o painel nao acende.
#define HX8394_LANE_NUM        2
#define HX8394_LANE_MBPS     700
#define HX8394_DPI_FREQ_MHZ   58
#define HX8394_HSYNC_BP       20
#define HX8394_HSYNC_PW       20
#define HX8394_HSYNC_FP       40
#define HX8394_VSYNC_BP       10
#define HX8394_VSYNC_PW        4
#define HX8394_VSYNC_FP       24

namespace lgfx
{
 inline namespace v1
 {
  struct Panel_HX8394 : public Panel_DSI
  {
    // A sequencia vai pela propria LovyanGFX (Panel_DSI::init_panel), e nao a mao.
    // Isso importa: no driver oficial da Waveshare o DPI JA EXISTE quando o vendor
    // init e enviado, e a LovyanGFX chama init_dpi() antes de init_panel() - mesma
    // ordem. Tentar mandar antes do DPI trava no meio da lista (medido: com o
    // preambulo antes do DPI, trava no 0xBD; sem preambulo, trava no 0xB2 final).
    const uint8_t* getInitParams(size_t n) const override
    {
      switch (n) {
        case 0: return preamb;
        case 1: return list0;
        case 2: return list1;
        default: return nullptr;
      }
    }
    size_t getInitDelay(size_t n) const override
    {
      switch (n) {
        case 0: return 120;   // depois do SLPOUT do preambulo
        case 1: return 200;   // depois do SLPOUT da lista de fabricante
        case 2: return 80;    // depois do DISPON
        default: return 0;
      }
    }

  public:
    // PREAMBULO - de panel_hx8394_init(), NAO da tabela vendor_specific. Sem ele o
    // painel engasga no meio da lista. O 0xBA=0x61 diz ao painel que sao 2 lanes.
    static constexpr uint8_t preamb[] = {
      1, 0x11,             // SLPOUT
      2, 0x36, 0x00,       // MADCTL, ordem RGB
      2, 0x3A, 0x55,       // COLMOD, RGB565
      2, 0xBA, 0x61,       // DSI_INT0 = 2 lanes
      0
    };

    // Formato exigido por Panel_DSI::init_panel():
    //   [ tam, cmd, dado... ]  onde tam = 1 + numero de bytes de dado
    //   lista termina com um zero
    // A quebra em duas listas nao e estetica: e onde a sequencia oficial pede
    // espera (200 ms depois do SLPOUT, 80 ms depois do DISPON).
    static constexpr uint8_t list0[] = {
      4, 0xB9, 0xFF,0x83,0x94,
     11, 0xB1, 0x48,0x0A,0x6A,0x09,0x33,0x54,0x71,0x71,0x2E,0x45,
      7, 0xBA, 0x61,0x03,0x68,0x6B,0xB2,0xC0,
      7, 0xB2, 0x00,0x80,0x64,0x0C,0x06,0x2F,
     22, 0xB4, 0x1C,0x78,0x1C,0x78,0x1C,0x78,0x01,0x0C,0x86,0x75,0x00,0x3F,
                0x1C,0x78,0x1C,0x78,0x1C,0x78,0x01,0x0C,0x86,
     34, 0xD3, 0x00,0x00,0x00,0x00,0x00,0x00,0x08,0x08,0x32,0x10,0x05,0x00,
                0x05,0x32,0x13,0xC1,0x00,0x01,0x32,0x10,0x08,0x00,0x00,0x37,
                0x03,0x07,0x07,0x37,0x05,0x05,0x37,0x0C,0x40,
     45, 0xD5, 0x18,0x18,0x18,0x18,0x22,0x23,0x20,0x21,0x04,0x05,0x06,0x07,
                0x00,0x01,0x02,0x03,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,
                0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,
                0x18,0x18,0x18,0x18,0x19,0x19,0x19,0x19,
     45, 0xD6, 0x18,0x18,0x19,0x19,0x21,0x20,0x23,0x22,0x03,0x02,0x01,0x00,
                0x07,0x06,0x05,0x04,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,
                0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,0x18,
                0x18,0x18,0x18,0x18,0x19,0x19,0x18,0x18,
     59, 0xE0, 0x07,0x08,0x09,0x0D,0x10,0x14,0x16,0x13,0x24,0x36,0x48,0x4A,
                0x58,0x6F,0x76,0x80,0x97,0xA5,0xA8,0xB5,0xC6,0x62,0x63,0x68,
                0x6F,0x72,0x78,0x7F,0x7F,0x00,0x02,0x08,0x0D,0x0C,0x0E,0x0F,
                0x10,0x24,0x36,0x48,0x4A,0x58,0x6F,0x78,0x82,0x99,0xA4,0xA0,
                0xB1,0xC0,0x5E,0x5E,0x64,0x6B,0x6C,0x73,0x7F,0x7F,
      2, 0xCC, 0x0B,
      3, 0xC0, 0x1F,0x73,
      3, 0xB6, 0x6B,0x6B,
      2, 0xD4, 0x02,
      2, 0xBD, 0x01,
      2, 0xB1, 0x00,
      2, 0xBD, 0x00,
      8, 0xBF, 0x40,0x81,0x50,0x00,0x1A,0xFC,0x01,
      2, 0x3A, 0x50,
      1, 0x11,               // SLPOUT - o delay de 200 ms vem no getInitDelay(0)
      0
    };
    static constexpr uint8_t list1[] = {
     13, 0xB2, 0x00,0x80,0x64,0x0C,0x06,0x2F,0x00,0x00,0x00,0x00,0xC0,0x18,
      1, 0x29,               // DISPON - delay de 80 ms no getInitDelay(1)
      0
    };

    static const uint8_t* lista(size_t n) { return n == 0 ? list0 : (n == 1 ? list1 : nullptr); }
    static size_t esperaMs(size_t n)      { return n == 0 ? 200  : (n == 1 ? 80   : 0); }
  };
 }
}

// Envia a sequencia de fabricante comando a comando, logando cada um. O log e o
// ponto todo: uma escrita DSI que nao retorna deixa a placa muda, e sem isto voce
// so sabe que "travou no init".
// Devolve false no primeiro comando que falhar.
// Comandos do PREAMBULO, de panel_hx8394_init() do driver oficial.
#define HX8394_CMD_DSI_INT0  0xBA
#define HX8394_DSI_2_LANE    0x61

template <typename LOGFN>
inline bool hx8394EnviarInit(lgfx::Bus_DSI& bus, LOGFN log)
{
  // O PREAMBULO nao esta na tabela vendor_specific_init_code_default[] - ele vem
  // ANTES dela, no codigo de panel_hx8394_init(). Sem ele o painel aceita a lista
  // inteira e depois TRAVA no 0xB2 que vem depois do SLPOUT (medido). A ordem
  // aqui e copia fiel do driver oficial.
  log(9, 0, 0x11, 0);
  if (!bus.writeParams(0x11, nullptr, 0)) return false;   // SLPOUT
  lgfx::delay(120);

  uint8_t v;
  v = 0x00; log(9, 1, 0x36, 1);
  if (!bus.writeParams(0x36, &v, 1)) return false;        // MADCTL, ordem RGB
  v = 0x55; log(9, 2, 0x3A, 1);
  if (!bus.writeParams(0x3A, &v, 1)) return false;        // COLMOD, RGB565
  v = HX8394_DSI_2_LANE; log(9, 3, HX8394_CMD_DSI_INT0, 1);
  if (!bus.writeParams(HX8394_CMD_DSI_INT0, &v, 1)) return false;  // 2 lanes

  for (size_t n = 0; n < 2; ++n) {
    const uint8_t* p = lgfx::Panel_HX8394::lista(n);
    size_t len;
    int i = 0;
    while (0 != (len = p[0])) {
      log(n, i, p[1], (int)(len - 1));
      if (!bus.writeParams(p[1], &p[2], len - 1)) return false;
      p += len + 1;
      ++i;
    }
    lgfx::delay(lgfx::Panel_HX8394::esperaMs(n));
  }
  return true;
}

#endif
