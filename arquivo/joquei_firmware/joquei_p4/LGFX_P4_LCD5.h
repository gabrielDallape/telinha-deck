// LGFX para as telas Waveshare com ESP32-P4 (MIPI-DSI).
//
// Diferenca estrutural em relacao ao LGFX_WS7B.h das telas S3: la o painel era RGB
// PARALELO e comia 20 GPIOs; aqui e MIPI-DSI em pinos DEDICADOS, fora da matriz de
// GPIO (datasheet ESP32-P4 sec. 2.2 e 4.2.1.7, pinos fisicos 34-40). O painel custa
// ZERO GPIO - e por isso que o radio e o GPS cabem nesta placa.
//
// O framebuffer de 720*1280*2 = 1.843.200 B mora na PSRAM. Se ESP.getPsramSize()
// der 0, a tela NAO sobe: falta PSRAM=enabled no FQBN (ver AMBIENTE_BUILD.md).
//
// POR QUE DETECTAR O PAINEL EM VEZ DE FIXAR: a pesquisa nos esquematicos da
// Waveshare nao achou o modelo do controlador - ele fica no FPC do painel, nao na
// PCB. Entao perguntamos ao proprio painel pelo ID, como o LovyanGFX faz na config
// do M5Tab5 (que e a mesma familia: P4 + DSI + 720x1280). O log diz o que achou.
#pragma once
#define LGFX_USE_V1
#include <LovyanGFX.hpp>

#if !defined(CONFIG_IDF_TARGET_ESP32P4)
  #error "Este header e so para ESP32-P4. Use -Board p4."
#endif

// Os paineis DSI nao entram pelo LovyanGFX.hpp - precisam de include explicito.
#include "lgfx/v1/platforms/esp32p4/Bus_DSI.hpp"
#include "lgfx/v1/platforms/esp32p4/Panel_ILI9881C.hpp"
#include "lgfx/v1/platforms/esp32p4/Panel_ST7123.hpp"
#include "lgfx/v1/platforms/esp32p4/Touch_ST7123.hpp"
// O painel real desta placa. Nao vem na LovyanGFX - ver o cabecalho do arquivo.
#include "Panel_HX8394.h"

// --------------------------------------------------------------- pinos da placa
// Rastreados no esquematico oficial (ESP32-P4-WIFI6-Touch-LCD-5-Schematic.pdf).
// Nenhum destes sai no header de 40 vias - sao internos da placa.
#define P4_LCD_BL_PWM   26   // backlight, PWM
#define P4_LCD_BL_EN    33   // backlight, enable
#define P4_LCD_RST      27   // reset do painel
#define P4_TP_SDA        7   // I2C do toque
#define P4_TP_SCL        8
#define P4_TP_RST       23   // reset do controlador de toque

// Rastro do init pela serial. Existe porque uma falha de DSI nao da panic: ela
// TRAVA (readParams espera resposta de um painel que nao responde), e sem rastro
// voce so ve a placa emudecer sem saber em qual passo.
#ifndef MTS_LOG
  #define MTS_LOG(fmt, ...) do { Serial.printf("[lgfx] " fmt "\n", ##__VA_ARGS__); Serial.flush(); } while(0)
#endif

class LGFX_P4 : public lgfx::LGFX_Device
{
  lgfx::Bus_DSI     _dsi;
  lgfx::Light_PWM   _luz;
  lgfx::Panel_DSI*  _pnl = nullptr;
  lgfx::ITouch*     _tp  = nullptr;

public:
  // Preenchidos pela deteccao, para o sketch poder imprimir e decidir layout.
  const char* panelName = "?";
  int panelW = 0, panelH = 0;

  LGFX_P4() {}

  // Envia a sequencia do HX8394 DEPOIS que o DPI ja esta rodando, comando a
  // comando e com log. Usado com MTS_PANEL_BARE=1: o Panel_DSI cru sobe o DPI sem
  // travar, e so entao inicializamos o painel - que e a ordem do driver oficial
  // (o DPI existe quando panel_hx8394_init roda). O log e o ponto: uma escrita DSI
  // que nao retorna deixa a placa muda, e sem ele voce so sabe que "travou".
  // logar=true so para depurar: o Serial.flush() entre os comandos ATRAPALHA o
  // barramento DSI e o travamento muda de lugar a cada build (medido: L1[00],
  // depois L0[15], depois L0[11], conforme o log em volta mudava). Em uso normal,
  // mande sem log e confira o retorno.
  bool enviarInitHX8394(bool logar = false)
  {
    if (logar) {
      return hx8394EnviarInit(_dsi, [](size_t lista, int i, uint8_t cmd, int n) {
        MTS_LOG("    L%d[%02d] cmd=%02X (%d bytes)", (int)lista, i, cmd, n);
      });
    }
    return hx8394EnviarInit(_dsi, [](size_t, int, uint8_t, int) { });
  }

  bool init_impl(bool use_reset, bool use_clear) override
  {
    // Reset do painel por GPIO direto. As placas P4 da Waveshare NAO tem expansor
    // de I/O (ao contrario da S3-Touch-LCD-7B, onde ate o CS do cartao passava
    // pelo CH422G) - entao aqui e um pino comum.
    // ---------------------------------------------------------------------
    // 0. LIGAR O PAINEL. Este passo nao existe em nenhuma biblioteca generica e
    // nao esta em datasheet nenhum: e um chip de habilitacao de energia no
    // endereco I2C 0x45, no mesmo barramento do toque (GPIO 7/8).
    //
    // SEM ISTO o painel fica DESENERGIZADO, e ai:
    //   - readParams (ID do painel) trava
    //   - writeParams trava em algum ponto variavel da sequencia
    // e o travamento nao da erro, porque panel_io_dbi_tx_param SEMPRE devolve
    // ESP_OK: quem bloqueia sao esperas ocupadas sem timeout no HAL
    //   while (mipi_dsi_host_ll_gen_is_write_fifo_full(hal->host));
    // (esp_lcd/dsi/esp_lcd_panel_io_dbi.c e hal/mipi_dsi_hal.c).
    //
    // Transcrito de esp_lcd_new_panel_hx8394() do componente oficial da Waveshare
    // (Waveshare-ESP32-components, display/lcd/esp_lcd_hx8394). O segundo inteiro
    // de espera no fim e do original - nao encurte.
    MTS_LOG("0. habilitando energia do painel (I2C 0x45)");
    lgfx::i2c::init(1, P4_TP_SDA, P4_TP_SCL);
    lgfx::i2c::writeRegister8(1, 0x45, 0x95, 0x11, 0, 100000);
    lgfx::i2c::writeRegister8(1, 0x45, 0x95, 0x17, 0, 100000);
    lgfx::i2c::writeRegister8(1, 0x45, 0x96, 0x00, 0, 100000);
    lgfx::delay(100);
    lgfx::i2c::writeRegister8(1, 0x45, 0x96, 0xFF, 0, 100000);
    lgfx::delay(1000);
    MTS_LOG("   painel energizado");

    // O RESET DESTA PLACA E ATIVO-ALTO. Isto nao e detalhe: e a causa do bug que
    // custou a tarde inteira. O BSP da Waveshare traz .flags.reset_active_high = 1
    // e o porte independente da mesma placa no xiaozhi-esp32 concorda.
    //
    // A LovyanGFX assume o contrario (ativo-baixo, repouso em HIGH): o
    // Panel_Device::init termina com rst_control(true) -> gpio_hi, ou seja, deixa
    // o painel PRESO EM RESET nesta placa. Por isso pin_rst fica em GPIO_NUM_NC na
    // config do painel: o reset e feito aqui, com a polaridade certa.
    //
    // Com o painel em reset ele fica MUDO, e ai o modo de falha e cruel: o
    // esp_lcd_new_panel_io_dbi liga ACK por comando (fixo, sem opcao), entao o
    // host faz bus turn-around e ESPERA resposta a cada comando. Sem resposta, a
    // FIFO enche e o HAL gira para sempre num while() sem timeout. O comando em
    // que trava MUDA conforme o codigo em volta - e a FIFO saturando em pontos
    // diferentes, nao um comando "venenoso" (esp-idf issues #15137, #15358, #18194).
    MTS_LOG("1. reset do painel no GPIO %d (ATIVO-ALTO)", P4_LCD_RST);
    lgfx::pinMode(P4_LCD_RST, lgfx::pin_mode_t::output);
    lgfx::gpio_hi(P4_LCD_RST); lgfx::delay(20);   // assert
    lgfx::gpio_lo(P4_LCD_RST); lgfx::delay(120);  // release -> estado de operacao

    {
      auto cfg = _dsi.config();
      cfg.bus_id    = 0;
      cfg.lane_num  = HX8394_LANE_NUM;    // 2 lanes (datasheet P4 4.2.1.7)
      // 700 Mbps e o valor do header oficial da Waveshare. Com 960 (que e o do
      // M5Tab5, painel ILI9881C) a tela fica preta.
      cfg.lane_mbps = HX8394_LANE_MBPS;
      // O PHY do DSI tem alimentacao PROPRIA (VDD_MIPI_DPHY, 2,25-2,75 V), servida
      // por um LDO interno do P4 - nao pelo trilho de 3,3 V da placa.
      cfg.ldo_chan_id    = 3;
      cfg.ldo_voltage_mv = 2500;
      _dsi.config(cfg);
    }
    MTS_LOG("2. Bus_DSI.init() (2 lanes @ 960 Mbps, LDO ch3 2500 mV)");
    if (!_dsi.init()) {
      MTS_LOG("   FALHOU");
      return false;
    }
    MTS_LOG("   ok (%d lanes @ %d Mbps)", HX8394_LANE_NUM, HX8394_LANE_MBPS);
    lgfx::delay(80);


    // ---------------------------------------------------------- quem e voce?
    // MTS_SKIP_PANEL_ID=1 pula esta etapa. Vale quando o painel nao responde a
    // leitura por DBI: alguns modulos so aceitam escrita, e o readParams fica
    // esperando resposta que nunca vem.
    bool ehIli = false, ehSt = false;
#if !defined(MTS_SKIP_PANEL_ID) || (MTS_SKIP_PANEL_ID == 0)
    MTS_LOG("3. lendo o ID do painel...");
    for (int i = 0; i < 3 && !ehIli && !ehSt; ++i) {
      uint8_t id[3] = {0, 0, 0};
      MTS_LOG("   3.%d readParams(0xF4) [ST7123?]", i);
      _dsi.readParams(0xF4, id, 2);
      MTS_LOG("       -> %02X %02X", id[0], id[1]);
      if (id[0] == 0x71 && id[1] == 0x23) { ehSt = true; break; }

      // ILI9881C so responde o ID depois de trocar para a pagina 1
      MTS_LOG("   3.%d pagina 1 + readParams(0x00/01/02) [ILI9881C?]", i);
      static constexpr uint8_t pag1[] = { 0x98, 0x81, 0x01 };
      _dsi.writeParams(0xFF, pag1, 3);
      _dsi.readParams(0x00, &id[0], 1);
      _dsi.readParams(0x01, &id[1], 1);
      _dsi.readParams(0x02, &id[2], 1);
      MTS_LOG("       -> %02X %02X %02X", id[0], id[1], id[2]);
      if (id[0] == 0x98 && id[1] == 0x81) {
        static constexpr uint8_t pag0[] = { 0x98, 0x81, 0x00 };
        _dsi.writeParams(0xFF, pag0, 3);
        ehIli = true;
        break;
      }
    }
#else
    MTS_LOG("3. deteccao de ID PULADA (MTS_SKIP_PANEL_ID)");
#endif

#if !defined(MTS_PANEL_BARE) || (MTS_PANEL_BARE == 0)
    // ---- o caminho normal: HX8394, o painel real desta placa
    if (!ehSt && !ehIli) {
      auto p = new lgfx::Panel_HX8394();
      _pnl = p; _tp = new lgfx::Touch_GT911();
      panelName = "HX8394"; panelW = 720; panelH = 1280;
      auto d = p->config_detail();
      d.dpi_freq_mhz       = HX8394_DPI_FREQ_MHZ;
      d.hsync_back_porch   = HX8394_HSYNC_BP;
      d.hsync_pulse_width  = HX8394_HSYNC_PW;
      d.hsync_front_porch  = HX8394_HSYNC_FP;
      d.vsync_back_porch   = HX8394_VSYNC_BP;
      d.vsync_pulse_width  = HX8394_VSYNC_PW;
      d.vsync_front_porch  = HX8394_VSYNC_FP;
      p->config_detail(d);
    } else
#endif
#if defined(MTS_PANEL_BARE) && (MTS_PANEL_BARE == 1)
    // BISSECAO: Panel_DSI cru, SEM a sequencia de inicializacao de fabricante
    // (getInitParams devolve nullptr na classe base). Serve para separar duas
    // hipoteses quando o init trava:
    //   passa aqui  -> o DPI/framebuffer estao ok, o painel e que nao e ILI9881C
    //   trava aqui  -> o problema e o esp_lcd_new_panel_dpi (timings ou PSRAM)
    {
      auto p = new lgfx::Panel_DSI();
      _pnl = p; _tp = nullptr;
      panelName = "Panel_DSI cru (bissecao)";
      panelW = 720; panelH = 1280;
      auto d = p->config_detail();
      d.dpi_freq_mhz = 80;
      d.hsync_back_porch = 140; d.hsync_pulse_width = 40; d.hsync_front_porch = 40;
      d.vsync_back_porch = 20;  d.vsync_pulse_width = 4;  d.vsync_front_porch = 20;
      p->config_detail(d);
    }
#else
    if (ehSt) {
      auto p = new lgfx::Panel_ST7123();
      _pnl = p; _tp = new lgfx::Touch_ST7123();
      panelName = "ST7123"; panelW = 720; panelH = 1280;
      auto d = p->config_detail();
      d.dpi_freq_mhz = 80;
      d.hsync_back_porch = 40;  d.hsync_pulse_width = 2;  d.hsync_front_porch = 40;
      d.vsync_back_porch = 8;   d.vsync_pulse_width = 2;
      d.vsync_front_porch = 220;  // encolher isto faz o TOQUE parar de funcionar
      p->config_detail(d);
    } else {
      // Sem ID: assumimos ILI9881C, que e o controlador classico de 720x1280 e o
      // que o M5Tab5 usa com o mesmo SoC. Se a imagem sair rolando ou deslocada,
      // e AQUI (porches e dpi_freq_mhz) que se mexe primeiro.
      auto p = new lgfx::Panel_ILI9881C();
      _pnl = p; _tp = new lgfx::Touch_GT911();
      panelName = ehIli ? "ILI9881C" : "ILI9881C (assumido, sem ID)";
      panelW = 720; panelH = 1280;
      auto d = p->config_detail();
      d.dpi_freq_mhz = 80;
      d.hsync_back_porch = 140; d.hsync_pulse_width = 40; d.hsync_front_porch = 40;
      d.vsync_back_porch = 20;  d.vsync_pulse_width = 4;  d.vsync_front_porch = 20;
      p->config_detail(d);
    }
#endif
    if (_pnl == nullptr) return false;
    MTS_LOG("4. painel escolhido: %s (%dx%d)", panelName, panelW, panelH);

    setPanel(_pnl);
    {
      auto cfg = _pnl->config();
      cfg.memory_width  = panelW; cfg.memory_height = panelH;
      cfg.panel_width   = panelW; cfg.panel_height  = panelH;
      cfg.offset_x = 0; cfg.offset_y = 0; cfg.offset_rotation = 0;
      cfg.readable = true; cfg.rgb_order = true; cfg.bus_shared = false;
      cfg.pin_cs = GPIO_NUM_NC;
      cfg.pin_rst = GPIO_NUM_NC;   // ja resetamos por GPIO la em cima
      _pnl->config(cfg);
      _pnl->setBus(&_dsi);
    }
    if (_tp) {
      auto cfg = _tp->config();
      cfg.pin_sda = P4_TP_SDA; cfg.pin_scl = P4_TP_SCL;
      cfg.pin_rst = P4_TP_RST; cfg.pin_int = -1;   // o INT nao esta fiado a GPIO
      cfg.freq = 400000; cfg.i2c_port = 1; cfg.bus_shared = false;
      cfg.x_min = 0; cfg.x_max = panelW - 1;
      cfg.y_min = 0; cfg.y_max = panelH - 1;
      cfg.offset_rotation = 0;
      _tp->config(cfg);
      _pnl->setTouch(_tp);
    }
    {
      // O backlight tem DOIS pinos: um enable e um PWM. O enable e digital comum;
      // so o PWM entra no LovyanGFX.
      lgfx::pinMode(P4_LCD_BL_EN, lgfx::pin_mode_t::output);
      lgfx::gpio_hi(P4_LCD_BL_EN);
      auto cfg = _luz.config();
      cfg.pin_bl = P4_LCD_BL_PWM;
      cfg.freq = 5000;
      cfg.pwm_channel = 7;
      cfg.offset = 0;
      cfg.invert = false;
      _luz.config(cfg);
      _pnl->setLight(&_luz);
    }

    MTS_LOG("5. LGFX_Device::init_impl() - aloca framebuffer de %d KB na PSRAM",
            (panelW * panelH * 2) / 1024);
    bool r = lgfx::LGFX_Device::init_impl(use_reset, use_clear);
    MTS_LOG("   %s", r ? "ok" : "FALHOU");
    return r;
  }
};
