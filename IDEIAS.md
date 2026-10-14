# IDEIAS — o que fazer com o JOQUEI depois do R6

Levantado em 23/09/2026, logo depois de tirar o R6 do painel. Três frentes:
revisão do código do agente, pesquisa do que já existe por aí (e do que o Claude
Code oferece de hooks, statusline e CLI) e um redesenho do visual — ver a seção
1, que é o que já foi feito. Horas são estimativa.

Regra de leitura: **"fw"** marca o que exige regravar o firmware. Tudo o mais é
Python no PC e vale no minuto seguinte.

---

## 0. Feito no mesmo dia, depois do levantamento

- **A placa da mesa roda o firmware do RÉDEA** (`redea-1.0`). Compatível, mas o
  agente precisou de dois cuidados: não escrever na serial com pedaço em voo e
  não tratar `imgbad`+`imgok` como entrega. Ver `_CONTEXTO.md`.

- **Home virou tela inicial 5x3**: relógio, clima (Open-Meteo, cidade pelo IP),
  música com capa, Claude, FOCO (pomodoro) na fileira de cima; apps e mídia no
  meio; áudio e Bloquear (Win+L) embaixo. Cards 240x200.
- **Cards vivos com id fixo + versão + `i=0` no lugar** — resolve de vez o
  "pula sondagem" (2.2) e o problema dos ids por conteúdo: a placa redesenha só
  o card, sem piscar. Ver `_CONTEXTO.md`. A música deixou de alternar `ar0/ar1`.
- **Pomodoro** (era 5.2): toque começa, toque cancela, aviso na barra ao acabar.
- **Clima** (era 5.4) e **relógio**: `agent/vivos.py`.
- `botao_medidor` finalmente em uso (FOCO). A página Sistema (5.1) fica barata
  agora: é mais uma fonte viva.

- **Terminal do card de projeto nasce com ambiente limpo.** Se o agente for
  iniciado de dentro de uma sessão do Claude Code, ele herda `CLAUDECODE` e
  `CLAUDE_CODE_*`; o `claude` aberto pelo card virava sub-sessão sem transcript
  ("inherited CLAUDE_CODE_CHILD_SESSION marker"). `projetos.ambiente_limpo()`
  tira essas variáveis. Melhor ainda: iniciar o `JOQUEI.bat` fora do Claude
  (3.1, iniciar com o Windows, resolve de vez).

- **Segunda rodada da home (noite de 23/09):** relógio e clima
  saíram da grade; a hora foi para a **barra como texto**; entrou a tela de
  **descanso** (relógio grande, clima, próxima reunião via `.ics`) com entrada
  automática por ociosidade do PC; saíram Ant, Prox, Foco e Bloquear; heartbeat
  de 4 s para a barra não dizer "agente offline"; `title: "JOQUEI"` porque o
  firmware do RÉDEA escreve "REDEA" quando o título é vazio. 5.3 (agenda) FEITO.
- **Por que o relógio piscava:** era um JPEG de 9 KB substituído por minuto;
  ~7% chegam com bytes trocados nesta placa e alguns decodificam com lixo em
  vez de falhar. Texto na barra não tem esse problema. O conserto de verdade
  segue sendo CRC no firmware (2.8).
- **Apagar a tela de verdade no descanso** exige um evento `brilho` no
  firmware (PWM do backlight já existe no driver). Entra na regravação (2.8).

- **24/09, de madrugada, depois do "tá muito xoxinho":** pesquisa de decks DIY
  (seção 4.8), ícones Phosphor Fill com pastilhas, tela de descanso com céu por
  hora/tempo, e a feature nº 1 dos decks implementada: **perfis por janela em
  foco** (`claude`, `discord`) com a ação `digitar` protegida por `exigir`.

- **24/09, manhã:** card **Spotify** na home (logo parado, capa tocando) e a
  página **player** (capa grande, progresso, tempo restante, tocar/pausar,
  anterior, próxima). Agenda ganhou a **rota OAuth do Google** para contornar o
  Workspace. Pendente do usuário: criar o client OAuth (README) ou mandar o
  endereço secreto iCal.

- **24/09, manhã (2):** card **Falar** na página Claude (ditado nativo em modo
  toque, `alt+k` → `voice:pushToTalk`), **Spotify** como atalho na home (app da
  Store, abre por `spotify:`), home virou **4x3** com o card **Sistema** (CPU e
  RAM, o `botao_medidor` finalmente em uso). 5.1 (Sistema) parcialmente FEITO.

- **24/09, manhã (3):** **bandeja do Windows** (`agent/bandeja.py`, pystray):
  ícone ao lado do relógio com estado, Ligar/Desligar, Iniciar com o Windows
  (atalho em `shell:startup`, já criado), log em `joquei.log`. Substitui o
  `JOQUEI.bat`. 2.1 (log) e 3.1 (iniciar com o Windows) FEITOS. Home ficou
  **só com ícones** e logos reais (Claude do `claude.exe`, Spotify da Store via
  `icon_exe`). Cortar a energia da placa por software: **não dá** numa porta USB
  comum; o que dá é evento `brilho` no firmware (2.8) ou um hub com chave por
  porta (uhubctl).

- **24/09, manhã (4): regravação do firmware** (`redea-1.1`) com `dormir` /
  `acordar` / `brilho`. "Desligar" na bandeja apaga a tela de verdade; a tela
  de descanso baixa o backlight. 3.6 parcial e o item "brilho" de 2.8 FEITOS.
  Ficam para a próxima regravação: CRC no `img`, toque longo, swipe, `ack`
  visível, `fillRect` redundante, partição.

## 1. Visual — feito hoje

O que o redesenho mudou em `arte.py`, `paginas.py` e `config.json`, e por quê:

1. **Card Claude virou destino.** `type: page` agora conta como destino
   (antes só `icon_app`/`icon_file`): fundo laranja-escuro, aro claro, rótulo
   "CLAUDE" e sublinha "5 projetos" (id de arte `dev:n5`). Era grafite e sem
   nome, perdido entre os controles.
2. **Três andares no card de 240x308.** Rótulo de 21 → 24 px; campo opcional
   `sub` (15 px, cor fraca) só onde há informação real: Discord/Chrome
   "monitor 2", Mic "Discord + Windows", Print "Win+Shift+S".
3. **Nível de volume no card SOM.** `nivel_de: "sys_vol"` desenha barra de 10
   gomos na vaga do trilho de estado: "não está mudo, está em 60" numa leitura.
   Vol−/Vol+ ficam estáticos de propósito (SOM é o medidor, eles são os
   botões). O agente remanda a página quando o degrau de 5 muda, com debounce
   de 400 ms — cinco toques em Vol+ viram um card novo, não cinco. Ligado e
   testado com serial falsa.
4. **Cor por hash do nome** (`arte.cor_projeto`, paleta de 12): a cor do
   projeto não muda mais quando a lista muda de ordem.
5. **Card de projeto redesenhado.** Pastilha grande com monograma ("Norfolk
   AI" → NA), nome em 30 px, chip com o branch do git (ou "sem git"), idade
   ("agora", "ha 2 d"), Clawd pequeno no canto como marca de família. Dados
   por meia dúzia de `stat()` em `paginas.info_projeto`.
6. **Ids de arte carregam o que muda** (`proj:joquei:<hash6 de branch|idade>`):
   trocou o branch ou passou uma hora, a próxima abertura de `dev` manda card
   novo; o id do botão não muda. Mesma lógica do card de música.

Pesos: home 6–15 KB por card, dev 17–18 KB. Não feito, por escolha: nível
também em Vol−/Vol+ (três reenvios por toque para informação repetida) e
destaque do projeto mais recente (a ordem é fixa pela lista; não inventar
hierarquia sem saber qual projeto importa).

Também feito hoje, fora do visual: `JOQUEI.bat` só reinicia quando o agente
sai com código ≠ 0 (Ctrl+C agora para), `requirements.txt` ganhou `winsdk` e
perdeu `requests`, `--list` consertado.

---

## 2. Código do agente

Ordem por retorno. Os três primeiros são o que eu faria antes de qualquer
feature — as features abaixo ficam mais baratas depois deles.

### 2.1 Log em arquivo, com traceback — FEITO pela bandeja (joquei.log)
`JOQUEI.bat` reinicia em 3 s e o traceback some. Sem isso, cada bug
intermitente é adivinhação.
- `main()`: `logging.handlers.RotatingFileHandler(BASE.parent/"joquei.log", 2 MB, 3)`;
  `faulthandler.enable()` num arquivo (pega o access violation do comtypes que
  já aconteceu — comentário em `joquei_agent.py` na parte de áudio);
  `sys.excepthook` que loga antes de morrer.
- Os `print(f"[...]")` viram `log.info`. Um `[reinicio N]` no topo de cada subida.
- `JOQUEI.bat` só reinicia se `errorlevel` for diferente de 0 — **feito hoje**.

### 2.2 Recarregar `config.json` sem reiniciar a placa — 2 h (o "pula sondagem" já está feito)
Hoje só recarrega no `hello`, ou seja, quando a placa reinicia. Editar um botão e
ver na tela devia ser imediato — é metade da tese ("mexer no visual não regrava").
- `Ligacao.roda()`: checa `CONFIG_PATH.stat().st_mtime` a cada 2 s, fora do
  caminho do dedo. Mudou → `carregar_config()` no mesmo try/except que já existe,
  `painel.cfg = cfg`, **`painel.projetos = Projetos(cfg)`** (hoje o `hello`
  recarrega a config mas não refaz o `Projetos`, então mudar a lista de projetos
  exige reiniciar o agente), limpar do `painel._cache` e de `self.enviadas` as
  chaves das páginas fixas, `envia_pagina(self.pagina_atual)`.
- **Precisa do "pula sondagem"**: `envia_parte(i=-1)` pergunta à placa "já tem
  esta arte com este tamanho?". Se um card mudou de conteúdo e o JPEG deu o mesmo
  tamanho, a placa responde "tenho" e nada muda na tela. `enfileira(...,
  substituir=True)` que pula a sondagem. O RÉDEA já resolveu isso; é porte.
  Qualquer card vivo (volume, medidor, pomodoro) depende do mesmo fix.

### 2.3 Testar sem a placa — 3 h
Não há um teste sequer. Uma `PlacaFalsa` que fala o protocolo (responde `hello`,
`imgok` por pedaço, `imgbad` de propósito a cada N) roda a `Ligacao` inteira em
memória. `REDEA/agent/teste_remendo.py` é o molde. Com isso dá para mexer no
protocolo sem cabo.

### 2.4 Dividir `joquei_agent.py` — 2 h
700 linhas misturando áudio (pycaw), teclado, lançador, `Executor` e `Ligacao`.
Separar em `audio.py`, `teclado.py`, `acoes.py` (o `Executor`), `ligacao.py`; o
`joquei_agent.py` fica com `main()` e o modo de teste. Nenhuma lógica muda.

### 2.5 `Executor` como tabela, e config validada na carga — 2 h
- O `if/elif` de 20 ramos vira `dict[type -> método]`. Adicionar ação = uma
  função + uma linha. O `--list` passa a acusar `type` desconhecido.
- `carregar_config()` valida: `type` inexistente, `target` faltando, `id`
  duplicado, `state_key` que o `audio_state()` não produz, `icon` sem glyph.
  Hoje tudo isso só explode no toque, na frente da tela.

### 2.6 Teclado por `SendInput` — 1 h
`send_key()` usa `keybd_event`, que é a API velha e falha em janelas elevadas e
com layout de teclado diferente. O RÉDEA tem `digitar()`/`tecla()` com
`SendInput` unicode. Copiar. Pré-requisito para as macros de terminal (4.2).

### 2.7 Código morto e pequenos — 1 h
- `arte.para_rgb565`, `icones.para_rgb565`, `icones.icone_para_tela`,
  `icones.COR_CHAVE`: sobras da era pré-JPEG. Apagar.
- `Ligacao.enviados` (com "o") não é usado em lugar nenhum; o vivo é `enviadas`.
- `arte.botao_medidor` está pronto e nunca é chamado — ou vira a página Sistema
  (6.1) ou sai.
- `projetos._CORES` por índice não é mais usada pela arte (agora é hash do
  nome em `arte.cor_projeto`); apagar de `projetos.py`.
- `_indexar_atalhos()` cacheia o Menu Iniciar para sempre: instalou um app, só
  aparece depois de reiniciar. TTL de 5 min.
- `midia._agora()` faz `asyncio.run()` a cada 2 s, criando e destruindo um event
  loop. Funciona; um loop persistente na thread é mais limpo.
- Limpeza do `cache/` na subida: apagar JPEGs que não são da versão atual (era
  61% lixo antes de hoje).
- `requirements.txt` não listava `winsdk`, que o `midia.py` usa. **Corrigido hoje.**

### 2.8 Portar do firmware do RÉDEA — 4 h, **fw**
Vale uma única regravação juntando tudo:
- **`imgok` depois de desenhar.** Hoje a placa confirma o último pedaço antes do
  `drawJpg`; o PC manda a arte seguinte enquanto ninguém lê a UART, o RX estoura
  e a linha chega com 15-20 bytes a menos. É a origem real dos `imgbad`. O RÉDEA
  mediu: de várias artes corrompidas para zero.
- **Remendos** (`remendo.py` + `sx`/`sy` no `img`): só o retângulo que mudou vai
  no fio. 83% menos bytes por atualização de card vivo.
- `barra`/`aviso`: toast de verdade e texto na barra por 90 bytes (5.6) — o
  firmware do RÉDEA já tem; o do JOQUEI não.
- ~~**`brilho`**~~ FEITO em 24/09 (`dormir`/`acordar`/`brilho` no redea-1.1).
- **CRC no `img`** conferido na placa: medido em 23/09, ~7% das artes chegam
  com bytes trocados nesta placa; hoje só o `drawJpg` falhar denuncia.
- Toque longo e gesto de voltar (5.3, 5.4).
- Tirar o `fillRect` redundante da troca de página (~21 ms, medido).
- Partição: `default_8MB` num flash de 32 MB deixa 22 MB inacessíveis.

---

## 3. Usabilidade do painel

### 3.1 Iniciar com o Windows, sem janela — FEITO (bandeja + atalho em Inicializar)
Tarefa no Agendador "ao fazer logon", `pythonw`, "reiniciar se falhar" no lugar
do laço do `.bat`. Depende de 2.1 — sem console, o log é o único olho.

### 3.2 Erros que dizem o que fazer — 1 h
O `err` já vira 4 s de texto vermelho na barra (35 caracteres, desenhado pelo
firmware). Hoje chega a exceção crua. Mensagens acionáveis: "Discord fechado",
"terminal nao esta na frente", "projeto sumiu".

### 3.3 Toque longo — 3 h fw + 1 h PC, **fw**
`leToque()` dispara no primeiro contato. Segurar 600 ms → `{"cmd":"btn",...,
"hold":true}`; `acao()` usa `b["long"]` se existir. Melhor uso: **Vol+/Vol− com
repetição enquanto segura** (hoje é um passo por toque) e "Continuar" no card de
projeto. Duplo toque não vale: a primeira ação já disparou.

### 3.4 Gesto de voltar — 2 h, **fw**
Começou em x < 60 e andou > 200 px para a direita → `pedePagina(g_back)`.
Fazer junto com 3.3 numa regravação só.

### 3.5 `ack` visível — 1 h fw, **fw**
A placa ignora o `ack` hoje. Um aro verde de 300 ms confirmaria o toque sem
depender do estado mudar.

### 3.6 Barra viva — FEITO (o firmware do RÉDEA já tem `barra`; o relógio usa)
Texto que muda rápido (segundos de um timer, "sessão X terminou") por 90 bytes
em vez de um card de 35 KB.

---

## 4. Claude Code num painel de atalhos

O RÉDEA é o painel **de sessões**. O JOQUEI não deve duplicar isso. O que cabe
aqui é o que um painel de **atalhos** faz por quem vive no Claude Code: avisar,
levar até lá, digitar o óbvio, abrir o projeto certo do jeito certo.

Três fatos do código que barateiam tudo abaixo:
- **Estado aceso é de graça.** Qualquer botão com `state_key` já ganha `art_on`
  e `botao_icone(aceso=True)`. Basta o tick de estado devolver uma chave booleana
  nova. É exatamente como o mic fica vermelho.
- **Toast já existe.** `err` → 4 s na barra, sem firmware.
- **`sub` em `botao_projeto`** existe e está sem uso.

### 4.1 Card Claude que acende quando uma sessão precisa de você — 6-8 h ★
O botão `dev` (asterisco laranja) ganha `state_key: "claude_atencao"`. Acende
(campo vermelho) quando qualquer sessão está com aprovação pendente ou terminou o
turno e você ainda não voltou. **Toque aceso: foca a janela e a aba daquela
sessão. Toque apagado: abre `dev` como hoje.** Junto, `err` na barra: "REDEA
precisa de voce".

É o painel fazendo a única coisa que só um painel físico faz: avisar sem alt-tab
que uma das quatro sessões parou esperando um Enter, e levar até ela.

Como:
1. `~/.claude/settings.json`: hooks `Notification` (matcher
   `permission_prompt|idle_prompt`), `Stop` e `UserPromptSubmit`, `type:"command"`
   chamando `python agent/hook_claude.py <evento>`. O script lê o stdin
   (`session_id`, `cwd`, `hook_event_name`) e escreve/apaga
   `~/.claude/joquei/atencao/<session_id>.json`. `UserPromptSubmit` apaga (você
   voltou).
2. `agent/claude_estado.py` (novo): lista essa pasta, casa `session_id` com
   `~/.claude/sessions/<pid>.json` (copiar `vivas()`/`_pid_vivo()` de
   `REDEA/agent/sessoes.py`) para ter o `pid` e descartar sessão morta.
   `estado()` → `{"claude_atencao": bool}`.
3. `Ligacao.roda()`: `estado = {**audio_state(), **claude_estado.estado()}`;
   quando vira True, `self.recado({"ev":"err","id":"dev","msg":...})`.
4. `config.json`: `dev` ganha `state_key`, `label_on: "Precisa"`, `type:
   "claude_ou_pagina"`.
5. `Executor`: novo tipo — se há pendente, thread com `focar_sessao(pid)` +
   `garantir_aba(pid, titulo)` (copiar de `REDEA/agent/janelas.py`) e devolve
   `None`; senão devolve `"dev"`. Thread porque focar e girar aba leva até 1 s.
6. `arte.py`: nada. `dev:on` já renderiza.

Referências que fazem parecido: streamdeck-claude (uma tecla por sessão, via
hooks), claude-code-windows-notifications (hooks `Notification`+`Stop`, clique
foca o Windows Terminal), claude-status-display (hooks escrevem
`attention/<id>.json`, daemon lê — o mesmo padrão de arquivo).

### 4.2 Página Claude: macros para o terminal que está na frente — 4 h
Página fixa no `config.json`: Aprovar (Enter), Parar (Esc), Continua, `/compact`,
`/clear`, Ditar (4.4). Cada card digita no terminal em foco — **só se a janela da
frente for `WindowsTerminal.exe`**; se for o Discord, `err` "terminal nao esta
na frente" e não digita nada. Zero descoberta de sessão, zero risco de aba
errada: você já está olhando para a certa.
- `janelas.janela_da_frente()` → `(hwnd, exe)` via `GetForegroundWindow` +
  `_exe_da_janela()` que já existe. `digitar()` do RÉDEA (2.6).
- `Executor`: tipo `digitar` com `texto`, `enter`, `exigir_exe`.
- Home tem `grid` fixo 5x2 — a página Claude entra como 11º botão trocando para
  4x3, ou substitui o `snip`.

### 4.3 Card de projeto que sabe se já está aberto; Nova / Continuar — 5-6 h
Em `dev`, o card mostra "aberto" quando há sessão viva com `cwd` igual à pasta
(`sub="aberto"` em `botao_projeto`), e o toque **foca** em vez de abrir um
segundo `claude` (hoje dois toques = dois terminais). Projeto fechado abre
`proj/<id>`: **Nova** (`claude -n "<nome>"`), **Continuar** (`claude
--continue`), **Pasta** (Explorer). Devolve navegação em profundidade à tela.
- `--continue` é o que se quer 80% das vezes ao voltar. `-n` põe o nome no
  título do terminal, o que deixa o `garantir_aba` do RÉDEA mais confiável.
- `Projetos.abrir(pid, modo)`; `paginas.pagina("proj/<id>")`; `acao()` mapeia
  `nova|cont|pasta|focar`. `proj:x` e `proj:x:aberto` são dois sprites fixos,
  não estouram os 96 slots.

### 4.4 Ditar para o Claude com um toque — 0,5 h
O Claude Code tem ditado nativo (`/voice tap`, tecla rebindável em
`~/.claude/keybindings.json`, ex. `alt+k`). Um card `{"type":"key","target":
"alt+k"}` funciona **hoje** sem mexer em Python. Com 4.2 ganha a trava do exe.
Alternativa sem conta: `win+h` (ditado do Windows 11).

Sobre os dois microfones ES7210 da placa: não servem para isto pela UART (16 kHz
mono = 32 KB/s, no teto dos 38). O único uso honesto é a placa virar microfone
USB (UAC) pela USB-C do OTG — direção placa→PC, que o bug #12819 não afeta. Não
conferido se o core 3.3.11 tem TinyUSB UAC para o P4; sem isso é um mês às cegas.

### 4.5 Medidor de cota (5 h / 7 dias) com o `botao_medidor` parado — 4 h
A `statusLine` do Claude Code recebe `rate_limits.five_hour.used_percentage`,
`resets_at` e `seven_day` no stdin (Pro/Max). O comando da statusline faz `tee`
do JSON para `~/.claude/joquei/status.json` e segue imprimindo a linha normal.
Dois arcos na página Claude, "reseta 17:40" embaixo. Quantizar em 5% para o card
só ir quando mudar de verdade. Depende do "pula sondagem" (2.2).

### 4.6 Aprovar por hook HTTP, sem digitar Enter — 6 h + teste
`PermissionRequest` com `type:"http"` para um servidor mínimo no agente; o card
Aprovar responde `{"decision":{"behavior":"allow"}}`. **Não sei** se o diálogo do
terminal aparece enquanto o hook está pendente — se não aparecer, segurar a
resposta impede aprovar pelo teclado. Testar antes de construir. Por isso 4.1 e
4.2 usam Enter via SendInput, que o RÉDEA já provou.

---

## 4.7 O que existe de assistente físico para Claude Code (pesquisa de 23/09, noite)

Lidos: alonw0/claude-monitor-esp32, prabhavagrawal7/claude-ping,
777genius/claude-notifications-go, mark-mucchetti/stream-deck-claude-code,
msageha/claude-code-for-stream-deck, MoveCall/claude-desktop-buddy-esp32,
**anthropics/claude-desktop-buddy** (oficial, BLE — só para os apps desktop em
Developer Mode, não para o CLI), Arno-Z/WaveShare-ESP32-P4-Claude-Desktop-Buddy
(placa da mesma família, BLE pelo C6), HermannBjorgvin/Clawdmeter,
nsyll/clawdometer-eink, pickypg/claude-macropad, danielrosehill/Claude-Macropad-V2,
xz-code/claude-traffic-light.

Três padrões que se repetem:

1. **Um tile por sessão, cor por estado, toque foca a janela** — todos via
   hooks; máquina de estados idle / thinking / tool / **needs you** / done /
   error. O irmão mais próximo do JOQUEI é o stream-deck-claude-code. Aqui: é a
   4.1, e o RÉDEA já tem a leitura das sessões.
2. **Aprovar/negar no hardware** — BLE oficial (só desktop app) ou hook
   `PermissionRequest`/`PreToolUse` respondido pelo agente. Aqui: 4.6, ainda sem
   teste do timeout. Truque bom do claude-ping: subir a cadeia de PPID até achar
   a janela GUI da sessão, sem hardcode de terminal.
3. **Cota e contexto como decoração ambiente** — quase todos chamam a API para
   ler headers; a **statusline já entrega `rate_limits` e `context_window`** no
   stdin. Aqui: 4.5, com a arte da barra de gomos do SOM.

Ninguém usa câmera nem microfone do dispositivo; a voz vem do PC (`/voice`) e o
hardware aperta Space por HID. Nenhum é para tela grande: o JOQUEI é o único
com espaço para mostrar a pergunta inteira que o Claude fez.

## 4.8 O que os decks DIY fazem que o JOQUEI não fazia (pesquisa de 24/09)

Lidos: Bitfocus Companion, Macro Deck 3, OpenDeck, StreamController, Boatswain,
streamdeck-ui, FreeDeck-ino, Touch Portal (fechado), Stream32 (ESP32-S3
Waveshare, o irmão mais próximo em hardware), LucydDeck, ESP32MacroPad (XDA,
mesma tese), FreeTouchDeck, cyberdeck, EspDeck, openHASP, LoupixDeck, Elgato
Smart Profiles, deej. Veredito: o que separa eles do JOQUEI não é botão bonito,
é que **o painel muda conforme o que você está fazendo**.

Ranking do que tira o "xoxinho" (h = horas, fw = firmware):

1. **Perfil por janela em foco** — FEITO em 24/09.
2. **Página "Janelas" viva** — alt-tab na mesa: 15 cards com ícone do .exe e
   título das janelas abertas; toque foca. 4 h. `listar_janelas()` + `icones.py`.
3. **Variáveis no texto de qualquer card** — `label: "Vol {sys_vol}%"`,
   `sub: "{musica.titulo}"`; generaliza os `live`. 3 h.
4. **Botão de passos (latch)** — "Modo reunião": 1º toque muta mic, pausa
   música, Discord no monitor 2; 2º desfaz; o card diz o passo. 2 h.
5. **Gatilhos** — "reunião em 2 min → página reuniao + aviso"; o `vigia_ocioso`
   já é um gatilho fixo. 4 h.
6. **Botões sticky** — Mic e Som em toda página sem copiar (hoje copiados). 1 h.
7. **Breadcrumb na barra** — "home > Claude > Norfolk". 2 h (texto via `barra`).
8. **Slider por arraste no SOM** — 4 h fw + 1 h.
9. **Toque longo / repetição** — fw (3.3).
10. **Brilho e acordar no toque** — fw (2.8).

Ordem sugerida: 6 → 3 → 4 → 2 → 5 (sem firmware, ~14 h); 7–10 na regravação.

## 4.9 Telinhas de Spotify (pesquisa de 24/09) e o que ficou

Lidos: witnessmenow/Spotify-Diy-Thing, ThingPulse/esp32-spotify-remote,
ravnhzl/esp32-spotify-tft (mesma arquitetura: API → Python → serial → ESP32),
aidandug/spotify-now-playing, ESP32+Cloudflare Worker (dev.to),
ryanwa18/spotipi-eink, nonlineartom/spotify-circular-display (vinil girando,
letras do LRCLIB, gestos), ansonlichtfuss/spotify-desk-thing, ItsRiprod/DeskThing,
usenocturne/nocturne, idodov/pixoo64-media-album-art, e os de desktop
(spotify-taskbar-plugin, spotify-skin-rainmeter, Spotibar, WebNowPlaying).

Padrão comum: **capa grande + cor da capa no fundo + progresso extrapolado
entre leituras**; quem controla fino (curtir, shuffle, dispositivo, seek) usa a
Web API com Premium. **Feito hoje:** Web API com PKCE, capa 300 px, curtir /
aleatório / repetir com estado real, pular ±s, volume do Spotify.

Fica para depois:
- **Letras sincronizadas (LRCLIB)** — página `letras`, 3–4 linhas com a atual
  em destaque; `GET https://lrclib.net/api/get?track_name&artist_name&album_name&duration`
  (±2 s), exige `User-Agent` identificado, honrar 429. Sem escopo Spotify. ~6 h.
- **Fila: próximas 3** com capas 64 px — `GET /me/player/queue`. ~4 h.
- **Dispositivo Spotify Connect** — `GET /me/player/devices` + transferir. ~4 h.
- **Paleta dominante** da capa (`Image.quantize`) em vez da cor média. ~1 h.
- **Modo "só capa"** na tela de descanso quando há música (ThingPulse). ~2 h.
- Card "reautorizar Spotify" para quando o refresh token vencer (6 meses).

## 5. Conteúdo novo com hardware parado

### 5.1 Página Sistema com seis `botao_medidor` — 4 h
CPU, RAM, GPU, disco, rede, temperatura, arcos que ficam âmbar/vermelho sozinhos.
`psutil` para tudo menos GPU; `nvidia-smi --query-gpu` para a NVIDIA.
**A conta que manda:** 6 cards × 35 KB a cada 5 s = 42 KB/s, estoura os 38.
Então: quantizar em 5%, remandar só o card que cruzou um passo, e só quando
`pagina_atual == "sistema"`. Com remendo (2.8) fica folgado.

### 5.2 Pomodoro na mesa — FEITO
Card com os minutos que faltam (1 card/min, nada de tráfego); toque
inicia/pausa. Ao acabar: `err` "pausa" na barra e, opcional, `sequence` que muta
o mic e pausa a música — as ações já existem. Segundos na barra só com 3.6.

### 5.3 Agenda do dia — FEITO (tela de descanso)
Próximos 3 eventos; toque abre o Meet. Sem OAuth: URL secreta `.ics` do Google
Calendar, lida a cada 5 min. Só vale se houver reunião no meio das sessões.

### 5.4 Clima — FEITO
Open-Meteo sem chave. Menor valor da lista; está aqui porque custa quase nada.

### 5.5 Câmera → presença — mês, **fw**
A única ideia de câmera que respeita a tese: a placa **não manda imagem**, manda
`{"cmd":"presenca","aqui":false}` quando você sai da frente; o PC muta o mic,
pausa a música. Detecção tem de rodar na placa (esp-dl no P4, não conferido).
Precisa de um card para desligar a câmera.

### 5.6 Wi-Fi 6 pelo C6 como transporte — mês, **fw**
Substituiria os 38 KB/s por TCP local. Ataca o mesmo gargalo do USB nativo, que
está bloqueado por bug. Só registrado.

### 5.7 Volume por app — 1 h, mas **não fazer**
Já existe no RÉDEA (`som.py`). Enquanto os dois painéis alternarem na mesma
placa, duplicar é dívida.

---

## 6. Ordem sugerida

| # | o quê | horas | fw |
|---|---|---|---|
| 1 | 2.1 log em arquivo | 1 | |
| 2 | 4.4 card Ditar (só config) | 0,5 | |
| 3 | 2.2 reload de config + pula sondagem | 3 | |
| 4 | 4.1 card Claude que acende e foca ★ | 8 | |
| 5 | 2.6 + 4.2 SendInput e macros no terminal da frente | 5 | |
| 6 | 4.3 projeto aberto / Nova / Continuar | 6 | |
| 7 | 2.3 placa falsa para teste | 3 | |
| 8 | 2.4 + 2.5 + 2.7 arrumação do agente | 5 | |
| 9 | 4.5 medidor de cota | 4 | |
| 11 | 2.8 + 3.3 + 3.4 + 3.5 + 3.6 a regravação única | ~10 | sim |
| 12 | 5.1 página Sistema (depois do remendo) | 4 | |
| 13 | 3.1, 5.3 | 5 | |
| — | 4.6, 5.5, 5.6, mic UAC | mês, ou depende de teste | sim |

Se depois do item 4 a home não valer os 1280x720 de novo, o problema não é
conteúdo.

## Fontes consultadas
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/statusline
- https://code.claude.com/docs/en/cli-reference
- https://code.claude.com/docs/en/voice-dictation
- https://github.com/paultyng/agentsd
- https://github.com/JulienCr/streamdeck-claude
- https://github.com/chewrocca/claude-status-display
- https://github.com/zebastieneth/claude-code-windows-notifications
- https://open-meteo.com/en/docs
