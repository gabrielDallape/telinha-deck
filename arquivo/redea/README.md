# RÉDEA

Painel touch de 5" que mostra as sessões do Claude Code rodando na máquina — e
deixa você mexer nelas sem largar o que está fazendo.

Irmão do JOQUEI, mesma placa, mesmo transporte, conteúdo novo: onde o JOQUEI
tinha o catálogo tático do R6, aqui cada card é um agente trabalhando.

```
home ─┬─ Claude     → as sessões → ses/<pid> → o pedido · o que rodou · arquivos
      │                                        Focar · Continuar · Aprovar · Parar
      ├─ Som        → volume por aplicativo, sistema e microfone
      ├─ Projetos   → abre o terminal com o claude rodando na pasta
      ├─ Música     → toque dá play/pause, com a capa do álbum
      ├─ Microfone  → muta e desmuta, aceso quando mudo
      └─ Recorte    → win + shift + s
```

A home é um menu de funções. O Claude é **uma** delas, não o painel inteiro.

## O card de uma sessão

Não é um LED com nome. Cada card carrega, de cima para baixo:

- **o estado** na cor e na faixa lateral — laranja trabalhando, verde pronta, cinza parada
- **o nome do projeto** e o **título que o próprio Claude deu à conversa**
- **o que ela está fazendo agora**: `Bash  cd C:/Users/.../REDEA` — a ferramenta
  que está rodando neste instante, com o argumento resumido
- **os arquivos que ela mexeu**, em chips
- **um sparkline** da atividade dos últimos 20 minutos: a forma já diz se está a
  todo vapor, respirando ou parada, antes de você ler uma palavra
- **modelo, effort e a barra de contexto**, que fica âmbar em 60% e vermelha em 85%

E a barra do topo mostra o que muda depressa demais para caber num card —
`sidehustles: Busca limite dispensa de licitação` — porque texto na barra custa
90 bytes e um card custa 16 KB.

## O que ele sabe, e como

Nada é adivinhado. O próprio CLI escreve tudo no disco, e o painel só lê:

| Arquivo | O que sai dali |
|---|---|
| `~/.claude/sessions/<pid>.json` | sessão **viva**: pid, pasta, nome, e `status` = `busy` / `idle` com carimbo de hora |
| `~/.claude/projects/<slug>/<id>.jsonl` | `ai-title` (o título que o Claude deu à conversa), `last-prompt`, modelo, effort, tokens do turno, duração, branch |
| `~/.claude/stats-cache.json` | mensagens, ferramentas e tokens do dia |

O transcript chega a 10 MB, então `sessoes.py` lê só os últimos 256 KB e
procura de trás para frente — os campos que interessam são reescritos a cada
turno e estão sempre no fim.

Sessão fantasma (terminal fechado na marra) é descartada checando se o pid
ainda vive, via `OpenProcess`.

## Os três estados

| | quando | no card |
|---|---|---|
| **TRABALHANDO** | `status: busy` | laranja, card aceso |
| **PRONTA** | `idle` há menos de 20 min | verde |
| **PARADA** | `idle` há mais de 20 min | cinza |

Quando uma sessão sai de *trabalhando*, a barra pisca `<nome> terminou` por 4
segundos. É o "acabei, vem cá" sem alt-tab.

## As ações, e o que elas realmente fazem

O pid que o CLI grava é o do **node**, que não tem janela. Quem tem é o
terminal que o hospeda, um ancestral dele — `janelas.py` sobe a árvore de pais
até achar uma janela visível.

E o Windows Terminal põe várias abas num processo só, então focar a janela não
basta: digitar ali podia cair **na sessão errada**. O título da janela é o da
aba ativa, e o Claude Code põe o `ai-title` nele — então o painel confere onde
está e anda com `ctrl+tab` até chegar. **Se não chegar, não digita nada.**

| Card | O que faz |
|---|---|
| **Focar** | traz a janela e a aba daquela sessão para a frente |
| **Continuar** | digita `continua` + Enter (o texto está no `config.json`) |
| **Aprovar** | Enter sozinho: confirma a opção destacada num pedido de permissão. Sem prompt aberto, é uma linha vazia, inofensiva |
| **Parar** | Esc |
| **Pasta** | abre o projeto no Explorer |

Tudo isso roda numa thread: focar + girar aba + digitar leva de 300 ms a 1 s, e
o loop serial não pode parar nesse tempo. O que falhar volta como aviso na barra.

## A arquitetura, em uma frase

**A placa é burra de propósito.** O PC compõe cada card inteiro no Pillow —
gradiente, canto arredondado, o asterisco do Claude, a barra de contexto,
tipografia — e manda como JPEG. A placa estampa o bitmap e desenha só os
estados que precisam ser instantâneos (apertado, aceso).

Efeito colateral que é metade do valor: **mexer no visual não exige regravar a
placa.**

### O id da arte é estável; o conteúdo tem versão à parte

Esta é a regra que mais importa, e custou uma tela piscando para ser aprendida.

O firmware redesenha a tela **inteira** (`fillScreen`) toda vez que recebe um
layout. Na primeira versão o id da arte era um hash do conteúdo — então cada
ferramenta que uma sessão rodava gerava um id novo, que gerava um layout novo,
que apagava e repintava a tela. O painel piscava a cada poucos segundos.

Agora o id é fixo (`ses:10164`) e o conteúdo carrega uma versão separada.
Quando só a versão muda, a imagem vai de novo **com o mesmo id**: o firmware
troca o sprite e marca sujo apenas aquele botão. O layout só é remandado quando
a página muda de forma de verdade — uma sessão nasceu ou morreu.

Dos dois lados há uma trava: o agente pula a sondagem `i = -1` ao substituir uma
arte (senão a placa responderia "já tenho essa" e nada mudaria), e o firmware
compara a assinatura do layout recebido com a do que está na tela e não
redesenha se forem iguais.

Medido depois da correção: **zero redesenhos de tela inteira** em 70 s, com 13
cards atualizados no mesmo período.

### Só o retângulo que mudou vai no fio

Um card é caro (16 a 24 KB) e quase nunca muda inteiro: o que muda é uma faixa
— a linha da ferramenta, a barra de contexto, o sparkline.

`remendo.py` compara a imagem nova com a que a placa tem, em dez faixas
horizontais, agrupa as vizinhas que mudaram e recorta só esses retângulos. O
evento `img` ganhou `sx`/`sy`: a placa desenha o recorte por cima do sprite que
já está lá e redesenha apenas aquele botão. **83% menos bytes por troca de
ferramenta.** Quando não compensa — mudou mais de 55% da área, ou a placa já
descartou aquela arte — cai sozinho no card inteiro.

É a mesma ideia do [RemoteWebViewServer](https://github.com/strange-v/RemoteWebViewServer),
com uma vantagem: aqui o servidor sabe o que desenhou, então o diff é exato e
não precisa de heurística.

### A confirmação do último pedaço sai depois de desenhar

O firmware confirma cada pedaço de arte para o PC mandar o próximo. O último
pedaço é diferente: a confirmação sai **depois** do `drawJpg`, não antes.

Enquanto a placa decodifica, ninguém lê a UART. Confirmando antes, o PC já
disparava a próxima arte e a linha chegava com 15 ou 20 bytes a menos — era a
origem do `chegou corrompida` que aparecia sem explicação desde o começo.

### Duas regras que vêm da serial a 38 KB/s

1. **Nada que muda sozinho entra na arte.** Segundo, token exato, "há 3 min" —
   cada mudança dessas é um card de 35 KB atravessando o cabo. O que muda
   depressa vai para a **barra**, que é texto e custa 90 bytes.

2. **Estado binário não redesenha.** Vai como `art` + `art_on` + `state_key`:
   as duas versões sobem uma vez e a placa alterna sozinha, sem serial.
   É assim que o card fica laranja no instante em que a sessão começa a trabalhar.

A grade da home também é estável (3×2) de propósito: mudar o tamanho do card
invalidaria o cache inteiro, e uma sessão nova faria a tela toda ser
retransmitida. Com a grade fixa, uma sessão nova custa um card. O buraco que
sobraria com poucas sessões é preenchido com projetos recentes.

## Medido nesta máquina

| | |
|---|---|
| Ler as 4 sessões com atividade, arquivos e sparkline | **31 ms** |
| Compor um card no Pillow | **15 ms** |
| Uma volta do vigia (ler sessões + remontar a home) | **7,2 ms**, a cada 700 ms |
| Montar a home | **2,2 ms** (era 14,9 antes do cache de `recentes()`) |
| **Serial em regime, 4 sessões, 2 trabalhando** | **3,15 KB/s — 8,3% dos 38 KB/s** |
| Redesenhos de tela inteira | **0** |
| Bytes de uma troca de ferramenta | **3,5 KB** (era 20,8 KB — o card inteiro) |
| 100 s na página `claude`, 93 remendos + 5 cards | **8,2% da serial, 0 corrompidas** |
| Primeira carga da home | ~114 KB, **3 s** |
| Binário do firmware | **443,5 KB**, 13% do flash |
| PSRAM livre depois do framebuffer | **31,6 MB** de 32 |

Os 8,3% são o preço de o painel acompanhar as sessões ao vivo: nove cards
remandados por minuto, todos porque a ferramenta em execução mudou. Sobra 92%
da serial para a navegação, que é o que o dedo sente.

`recentes()` é guardada por 30 s: a varredura custava 12,5 ms e era refeita a
cada 700 ms só para descobrir a mesma lista. Sem o cache, montar a home custava
14,9 ms; com ele, 2,18 ms.

## A placa rev v3.2 (leia antes de gravar)

Esta placa (serial `5B90124374`) traz **ESP32-P4 revision v3.2**, ROM
`esp32p4-eco7-20260109`, 400 MHz — silício de produção, não as amostras de
engenharia das placas anteriores. Isso quebra o firmware em **dois** pontos
independentes, e os dois foram atravessados aqui:

### 1. Bootloader: `ChipVariant` no FQBN

Sintoma: boot loop eterno, `rst:0x10 (CHIP_LP_WDT_RESET)`, e **nem uma linha**
do sketch — nem um `Serial.println` no topo do `setup()`. O log do ROM para em
`entry 0x4ff29ed0` e reinicia.

Causa: o `boards.txt` do core 3.3.11 lista `ChipVariant.prev3` **antes** de
`postv3`. Um FQBN que não traz essa chave pega o default do arduino-cli, que é
`prev3` → bootloader `esp32p4_es` (amostra de engenharia, 360 MHz). No silício
de produção ele trava antes de o console subir.

Correção: `ChipVariant=postv3` no FQBN — já é o default do `build.ps1`, e
`-Variant prev3` volta ao comportamento antigo para as placas velhas.

### 2. LovyanGFX: o clock do PHY do MIPI-DSI

Sintoma: agora o sketch roda e loga, mas aborta no init do display:

```
[lgfx] 2. Bus_DSI.init() (2 lanes @ 960 Mbps, LDO ch3 2500 mV)
abort() was called at PC 0x4002645b on core 1
```

Causa: `Bus_DSI.cpp:37` usa `MIPI_DSI_PHY_CLK_SRC_DEFAULT`, que no
`clk_tree_defs.h` ainda aponta para `..._LEGACY` = `SOC_MOD_CLK_PLL_F20M` —
uma fonte que o rev3 não tem. O switch do `mipi_dsi_ll` cai no `default:` e
chama `abort()`.

Correção: usar `MIPI_DSI_PHY_PLLREF_CLK_SRC_DEFAULT`, que é `SOC_MOD_CLK_XTAL`
e vale nas duas gerações. **É um patch na biblioteca**, em
`Documents/Arduino/libraries/LovyanGFX/src/lgfx/v1/platforms/esp32p4/Bus_DSI.cpp`,
com o original guardado ao lado como `.orig-antes-do-patch-redea`. Atualizar a
LovyanGFX desfaz o patch e o boot loop volta.

Armadilha: `MIPI_DSI_PHY_PLLREF_CLK_SRC_DEFAULT` é **enumerador, não macro**.
Um `#if defined(...)` em volta dele dá sempre falso e cai de volta no legado —
foi o que aconteceu na primeira tentativa, com sintoma idêntico ao de não ter
patch nenhum.

O mesmo par de problemas está descrito no
[issue #17 do M5Tab-Macintosh](https://github.com/amcchord/M5Tab-Macintosh/issues/17).

## Peças

```
agent/sessoes.py      lê ~/.claude: sessões vivas, detalhe, projetos, uso
agent/atividade.py    o que a sessão está FAZENDO: ferramenta, sparkline, arquivos
agent/janelas.py      acha a janela pelo pid, gira até a aba certa, digita
agent/som.py          volume por aplicativo, sistema e microfone (pycaw)
agent/midia.py        o que está tocando e a capa do álbum (SMTC)
agent/remendo.py      acha o retângulo que mudou, para não mandar o card todo
agent/arte.py         TODA a composição visual, em Pillow
agent/paginas.py      monta as páginas, resolve o toque, cache de arte
agent/redea_agent.py  loop serial, protocolo, fila de arte, vigia das sessões
agent/preview.py      a tela inteira num PNG, sem precisar da placa
agent/config.json     porta, baud, qualidade, o texto do Continuar

firmware/redea_p4/    firmware da placa (só estampa bitmap e lê o toque)
firmware/build.ps1    arduino-cli, FQBN, gravação
```

## Som

Um mixer por aplicativo. O [deej](https://github.com/NiklasRichter2222/deej)
resolveu isso com potenciômetro físico e virou padrão do nicho; o
[NativMix](https://github.com/knoelliX/NativMix) refez em PyQt. Nenhum dos dois
tem tela — e a tela mostra o que o potenciômetro não mostra: quem está fazendo
barulho agora, com nome e nível. Um toque muta o app, o card aceso é o app mudo,
e abaixo vão volume e mudo do sistema e do microfone.

## Rodar

```powershell
pip install -r agent/requirements.txt

# ver as páginas e as sessões sem a placa
python agent/redea_agent.py --test

# ver a tela como ela vai ficar
python agent/preview.py --todas      # sai em agent/preview/

# gravar a placa
.\firmware\build.ps1 -ListPorts
.\firmware\build.ps1 -Upload -Port COM8

# subir o painel
.\REDEA.bat
```

A porta é achada sozinha pelo VID/PID (`1A86:55D3`, a ponte CH343). Para fixar,
ponha o `COMx` em `config.json`.

## Protocolo

Uma linha JSON por mensagem, 921600 baud. O mesmo do JOQUEI, com dois eventos
novos (`barra` e `aviso`) no lugar do que ali eram volume e mic.

```
placa → PC   {"cmd":"hello","fw":"redea-1.0","page":"home"}
             {"cmd":"page","id":"ses/10164"}
             {"cmd":"btn","page":"ses/10164","id":"seguir"}
             {"cmd":"imgok","i":k,"tem":bool}     confirma pedaço de arte
             {"cmd":"imgbad","id":"..."}          chegou corrompida

PC → placa   {"ev":"layout","page":...,"grid":...,"buttons":[...]}
             {"ev":"img","id":...,"i":k,"n":N,"off":bytes,"d":"<b64>"}
             {"ev":"img",...,"sx":X,"sy":Y}        remendo: só um retângulo
             {"ev":"state","b0":true,"b1":false}  acende/apaga card
             {"ev":"barra","txt":"2 sessoes  1 trabalhando"}
             {"ev":"aviso","msg":"joquei terminou"}
             {"ev":"quem"}                        "você está aí?"
             {"ev":"ack"|"err","id":...}
```

## Limites conhecidos

- **Aba errada**: se o Windows Terminal mudar como escreve o título, o painel
  perde a referência e recusa digitar (não erra a sessão, só não age). Focar
  continua funcionando.
- **Sessões fora do Windows Terminal** (VS Code, tmux via SSH): o painel lista e
  mostra o estado normalmente, mas achar a "aba" não se aplica — só o Focar
  funciona, e olhe lá.
- **Contexto acima da janela**: sessões compactadas mostram mais tokens que a
  janela do modelo. A barra satura em 100%, o número segue real.
- **`uso` vem do `stats-cache.json`**, que o CLI recalcula de tempos em tempos —
  o card mostra a data a que os números se referem, que nem sempre é hoje.

## O que ficou para depois

- **Tiles com diff** no lugar de mandar o card inteiro, como o
  [RemoteWebViewServer](https://github.com/strange-v/RemoteWebViewServer) faz:
  ataca os 38 KB/s sem depender do USB.
- **Decode JPEG por hardware + PPA**, como o
  [ESP32-P4-Allsky-Display](https://github.com/chvvkumar/ESP32-P4-Allsky-Display):
  ataca os 79 ms de decode por card.
- **USB nativo** como transporte. O [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32)
  faz rede por USB RNDIS no P4, o que é a evidência de que o periférico enumera.
- **Responder pelo painel sem digitar**, pelo named pipe que o CLI expõe em
  `messagingSocketPath`. Depende de protocolo interno não publicado — por isso
  aqui é SendInput, que não quebra quando o CLI muda de versão.
