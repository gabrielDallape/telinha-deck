# TELINHA — agente Windows

Metade "PC" do painel touch. A placa manda só a **página e o id do botão**; este
agente decide o que aquilo faz, lendo `config.json`, e compõe a arte de cada
botão em Pillow. Trocar um ícone, uma cor ou uma função **não exige regravar o
firmware**.

## Instalar

```powershell
pip install -r requirements.txt
```

## Testar sem a placa

```powershell
python telinha_agent.py --list          # lista páginas e botões e mostra o estado do áudio
python telinha_agent.py --test mic      # dispara uma ação como se fosse um toque
python telinha_agent.py --test discord vol_up
```

## Rodar de verdade

**Pela bandeja (recomendado):** `pythonw agentandeja.py`. Um ícone aparece
ao lado do relógio: verde conectado, âmbar esperando a placa, cinza desligado.
Clique com o direito: **Ligar/Desligar painel**, **Iniciar com o Windows**
(cria/remove o atalho na pasta Inicializar), abrir o config, o log e a pasta.
O agente roda como processo filho sem janela e o que ele imprime vai para
`telinha.log` na raiz. Se o agente cair, a bandeja o sobe de novo.

**Desligar apaga a tela de verdade.** A bandeja manda a placa dormir
(`{"ev":"dormir"}`, firmware `redea-1.1`+): backlight desligado, toque
ignorado, só a serial fica escutando. **Ligar** sobe o agente, cuja primeira
mensagem acorda a placa e redesenha. A energia continua vindo do USB (não há
chave por software numa porta comum), mas com a tela apagada e o loop parado o
consumo é de miliamperes. A tela de descanso também baixa o brilho
(`descanso.brilho`, padrão 40) e volta ao de trabalho (`brilho`, 200) ao sair.

**Pelo terminal:**

```powershell
python telinha_agent.py
```

Ou, da raiz do projeto, `TELINHA.bat` — sobe o agente e o reinicia se ele cair.

Acha a porta sozinho (`"port": "auto"` procura o CH343 da placa e o USB-CDC do
ESP32-P4). Se pegar a porta errada, fixe em `config.json`: `"port": "COM8"`.
Reconecta sozinho se você desplugar a placa; sem placa, fica esperando.

## Pacotes de app

Cada app que o painel conhece é uma pasta em `pacotes/<app>/` com um
`pacote.json`: como achar o app no PC (`detectar`), o card que leva a ele
(`entrada`) e as páginas que ele traz (`paginas`). Na subida e a cada `hello`, o
agente junta as páginas dos pacotes **ativos** ao `config.json`, e daí em diante
é tudo página normal (foco por janela, cards vivos, cache).

| pacote | detecta por | traz |
|---|---|---|
| `claude` | `claude` no PATH | página Claude (abre com o terminal do Claude na frente) e Modelo |
| `discord` | atalho no Menu Iniciar | página Discord (abre com o Discord na frente) |
| `soundboard` | sempre | um botão por arquivo de som na pasta `sons/` |
| `obs` | OBS instalado | Live, Gravar, Pausar, Replay, Mic, Sons; Cenas lidas do OBS |

- **Ativo** = detectado, menos `pacotes.desligados`, mais `pacotes.forcar`.
- **Nomes:** a página de início ganha o id do pacote (`obs`), as outras
  `<pacote>.<página>` (`obs.cenas`), e os botões `<pacote>.<botão>`. Referências
  a páginas do próprio pacote (`page`, `then`, `back`) são reescritas. Não
  repita id de botão entre páginas do mesmo pacote: o id é o id da arte.
- **Personalizar sem mexer no pacote:** uma página do `config.json` com o mesmo
  id ganha da do pacote.
- A página **`apps`** (botão de grade na home) é gerada com a entrada de cada
  pacote ativo. `{"pacote": "obs"}` no lugar de um botão, em qualquer página,
  vira a entrada daquele pacote (ou some, se ele não estiver ativo).
- **Páginas geradas:** `"gerar": "sons"` (arquivos da `pasta`) ou
  `"gerar": "obs_cenas"`. Os botões são lidos a cada abertura, até 15 menos os
  fixos; os `buttons` da página vêm depois deles.

**Soundboard:** solte `.wav/.mp3/.ogg/.flac` em `pacotes/soundboard/sons/` ou
na pasta de `sons.pasta`. Toque toca, tocar de novo para, sons se sobrepõem.
Para a call/live ouvir, instale o VB-Audio Cable e ponha `"CABLE Input"` em
`sons.saidas`. O som vai para o alto-falante **e** para o cabo, e o
Discord/OBS escutam o "CABLE Output" como microfone. `python -m sounddevice`
lista os nomes das saídas.

**OBS:** OBS 28+ → Ferramentas → Configurações do servidor WebSocket → ligar,
porta 4455. A senha vai em `obs.senha`. O agente só tenta conectar com o OBS
aberto, e o estado (live, gravando, cena no ar) acende os botões sozinho.

## Páginas

- `home` — fixa, vem do `config.json`. Grade 4x3, cards 304x200, **só ícones**
  (logos reais do Discord, Chrome, Spotify e Claude): Discord, Chrome, Spotify,
  Claude / Música (o que está tocando), Mic, Som (com o nível), Print / Vol−,
  Vol+, Descansar. Uma vaga livre. Card sem `label` nem `sub` centraliza e
  aumenta o ícone.
  A **hora** vai como texto na barra do topo (`barra_relogio`), junto com a
  próxima reunião de hoje.
- `descanso` — três cards grandes quase pretos: relógio, clima e próxima
  reunião. Entra pelo botão Descansar, ou sozinha depois de
  `descanso.apos_min` sem teclado/mouse no PC (aí volta sozinha quando você
  mexer). Toque em qualquer card volta para a home.
- `claude` e `discord` — **perfis por janela em foco**: abrem sozinhas quando
  o Windows Terminal com o Claude Code (título contém "claude") ou o Discord
  vêm para a frente, e voltam para a home quando saem. `quando_foco` na
  página: lista de exes (`"discord.exe"`) ou regras `{"exe": ..., "titulo_tem":
  [...]}`. Navegar na mão (toque ou voltar) trava o automático por 30 s.
- `dev` — gerada: um card por projeto de `projetos.lista` (ou, com a lista
  vazia, o que tiver cara de projeto em `projetos.raiz`). Um toque abre o
  Windows Terminal na pasta já com `claude` rodando.

## Cards vivos

Botão com `live` muda de conteúdo sozinho, sem regravar nada e sem piscar a
tela: a arte tem id fixo e uma versão; quando a versão muda, o agente manda só
aquela imagem e a placa troca o sprite no lugar.

| `live` | o que mostra | atualiza |
|---|---|---|
| `relogio` | hora, dia da semana, data | a cada minuto |
| `clima` | temperatura, condição, máx/mín, chuva, cidade (Open-Meteo, sem chave) | `clima.atualiza_min` (15) |
| `musica` | capa, título, artista, tocando/pausado (SMTC do Windows) | quando a faixa muda |
| `foco` | pomodoro: minutos que faltam num arco (`type: foco` para o toque) | a cada minuto |
| `agenda` | próxima reunião e as duas seguintes, de um `.ics` | `agenda.atualiza_min` (5) e a cada minuto |
| `sistema` | CPU e RAM (psutil) num medidor; a thread só liga se algum card usar | a cada 5 s, em degraus de 5% |

`nivel_de: "sys_vol"` num botão desenha o volume atual como barra de gomos
(é o card SOM). O card Claude conta os projetos sozinho.

`estilo: "grande"` num card `relogio`/`clima` usa a versão da tela de descanso.

Config relacionado: `clima` (`lat`/`lon` vazios = cidade pelo IP; `cidade`
sobrescreve o nome), `agenda.ics_url`, `descanso.apos_min`, `barra_relogio`.

**Mídia:** o card de mídia da home mostra o que está tocando em qualquer app
(YouTube, videoaula, Spotify) e o toque dá **play/pause** nisso. O Spotify tem
o atalho próprio ao lado. A página `player` (capa grande, progresso, curtir,
aleatório, repetir) continua no config, mas sem botão na home por enquanto.
Funciona com qualquer app que apareça no controle de mídia do Windows
(Spotify, YouTube no Chrome, etc.).

**Falar com o Claude pelo painel:** o card "Falar" da página Claude manda
`alt+k`, que está ligado a `voice:pushToTalk` em `~/.claude/keybindings.json`,
com o ditado em modo toque (`voice.mode: "tap"` no `settings.json`): um toque
grava, outro para e o texto entra no prompt. Segurar espaço continua valendo.
Exige a janela do Claude na frente.

**Remote e Modelo:** "Remote" (celular) digita `/remote-control` + Enter na
sessão em foco, e ela passa a aparecer no app do Claude no celular e em
claude.ai/code. "Modelo" abre a página `modelo`: Opus 5.5 e Fable 5.1 digitam
`/model claude-opus-5-5` / `/model claude-fable-5-1` e voltam (`then`) para a
página Claude. Outro modelo é só mais um card ali no `config.json`.

**Apps da Store (Spotify):** não têm .exe nem atalho no Menu Iniciar. O card
usa `focus_or_launch` com `target: "Spotify"` (foca pela janela) e
`launch: "spotify:"` (abre pelo protocolo quando não há janela).

**Ligar o Spotify de verdade (Web API):** o controle de mídia do Windows só
dá uma miniatura de 150 px. Com a Web API o card tem capa nítida, posição
exata, curtir, aleatório, repetir e o nome do dispositivo. Uma vez só:

1. Abra https://developer.spotify.com/dashboard com a sua conta do Spotify e
   clique **Create app**.
2. Nome "TELINHA", descrição qualquer, **Redirect URI**
   `http://127.0.0.1:8765/callback`, marque **Web API**, salve.
3. Em Settings do app copie o **Client ID** e cole em `config.json` →
   `spotify.client_id`. Não precisa do secret (o login é PKCE).
4. Reinicie o agente. O navegador abre uma vez pedindo autorização; o token
   com renovação fica em `agent/segredos/spotify_token.json`.

Quando o Spotify está tocando ele manda no card; parado, o controle de mídia
do Windows (YouTube, aula no navegador) volta a valer.

**Ligar a agenda do Google — rota 1, sem login:** Google Agenda no navegador → engrenagem →
Configurações → sua agenda, na lista da esquerda → "Integrar agenda" →
copie o **Endereço secreto no formato iCal** e cole em `agenda.ics_url`.
Reinicie a placa (ou o agente) e o card passa a mostrar as reuniões. A URL é
secreta: quem tiver ela lê sua agenda; não a coloque em repositório.

**Rota 2, com login (para Workspace em que o admin escondeu o endereço
secreto):**

1. Abra https://console.cloud.google.com com a conta da agenda. Crie um projeto
   (qualquer nome, ex. "TELINHA").
2. Menu **APIs e serviços → Biblioteca** → procure **Google Calendar API** →
   Ativar.
3. **APIs e serviços → Tela de permissão OAuth** → tipo **Interno** (só sua
   organização; não precisa de verificação do Google) → nome "JOQUEI", seu
   e-mail → salvar. Em escopos, adicione `.../auth/calendar.readonly`.
4. **APIs e serviços → Credenciais → Criar credenciais → ID do cliente OAuth**
   → tipo **App para computador** → criar → **Baixar JSON**.
5. Salve o arquivo como `agent/segredos/google_client_secret.json` (a pasta
   está no `.gitignore`).
6. Reinicie o agente. O navegador abre uma vez para você logar; o token com
   renovação fica em `agent/segredos/google_token.json`. Daí em diante o card
   lê a agenda sozinho a cada 5 min.

Se o passo 3 não oferecer "Interno" (conta sem Workspace), escolha Externo e
adicione seu e-mail em "Usuários de teste".

## Tipos de ação em `config.json`

| `type` | o que faz | campos |
|---|---|---|
| `focus_or_launch` | traz a janela pra frente (e maximiza no monitor); se não existe, abre | `target`, `monitor` |
| `focus` | só foca; erro se a janela não existe | `target`, `monitor` |
| `launch` | abre um programa (nome do Menu Iniciar ou caminho absoluto) | `target` |
| `url` | abre um site no navegador padrão | `target` |
| `shell` | roda um comando | `target` |
| `key` | envia um atalho de teclado | `target: "ctrl+shift+m"` |
| `key_app` | atalho só se aquele app estiver aberto | `app`, `target`, `exigir` |
| `musica_ou_app` | tocando: abre a página `page` (player); parado: abre o app (`target`, `uri`, `web`); `so_app` sempre abre o app | `target`, `uri`, `web`, `page`, `so_app` |
| `spotify` | controle fino pela Web API: `op: curtir \| aleatorio \| repetir \| pular \| play_pause` (`segundos` no pular) | `op`, `segundos` |
| `media` | tecla de mídia/volume nativa | `key: play_pause \| next \| prev \| volume_up \| volume_down` |
| `mic_toggle` / `mic_mute` / `mic_unmute` | microfone padrão (via pycaw) | — |
| `sys_mute_toggle` | mute do alto-falante | — |
| `volume` | volume exato | `device: sys\|mic`, `value: 0-100` |
| `page` | navega para outra página | `page` |
| `digitar` | digita na janela em foco (SendInput), só se ela bater com `exigir` | `texto`, `enter`, `tecla: "esc"`, `exigir` (exe ou regra), `erro` |
| `foco` | começa ou cancela o pomodoro do card `live: foco` | — |
| `nada` | só existe para ter arte (card informativo) | — |
| `som` | toca um arquivo no soundboard (tocar de novo para) | `arquivo`, `volume`, `modo: alternar \| reiniciar \| sobrepor` |
| `som_parar` | para todos os sons | — |
| `obs` | OBS pelo WebSocket, em thread | `op: cena \| live \| gravar \| pausar \| replay \| mute \| camera_virtual`, `cena`, `fonte` |
| `sequence` | macro: vários passos em ordem | `steps[]`, `delay` por passo |

Outros campos do botão:

- `state_key` (`mic_muted`, `sys_muted`, `sp_curtida`, `sp_aleatorio`,
  `sp_repetir`) faz a tela pintar o botão conforme o estado real do PC — é isso
  que dá o ícone de mic vermelho quando mutado, ou o coração aceso na faixa
  curtida.
- `label_on` é o rótulo quando aceso.
- `live` transforma o botão num card vivo (ver acima).
- `icon_exe` extrai o logo de um .exe pelo caminho (apps sem atalho: Store,
  `~/.local/bin/claude.exe`); `icon_app` pelo nome do Menu Iniciar; `icon_file`
  usa uma imagem; `icon` usa um glifo da **Phosphor Fill** (`agent/fontes/`, MIT):
  nomes em `arte.PH` (`mic`, `volume`, `play`, `aprovar`, `fone`...). O Segoe
  Fluent fica de reserva.
- `"_off": true` desliga um botão sem apagar a entrada.

## Protocolo serial (uma linha JSON por mensagem)

```
placa -> PC   {"cmd":"hello","fw":"redea-1.1","page":""}  pede a home
              {"cmd":"page","id":"dev"}                 pede uma página
              {"cmd":"btn","page":"home","id":"mic"}    toque
              {"cmd":"state"}                           pede o estado agora
              {"cmd":"imgok","i":k}                     confirma um pedaço de arte
              {"cmd":"imgbad","id":"..."}               arte chegou corrompida

PC -> placa   {"ev":"layout","page":"home","grid":{...},"buttons":[...]}
              {"ev":"img","id":"...","w":..,"h":..,"len":N,"off":..,"i":k,"n":N,"d":"<b64>"}
              {"ev":"state","mic_muted":false,"mic_vol":82,
                            "sys_muted":false,"sys_vol":49}
              {"ev":"quem"}                             "você está aí?"
              {"ev":"dormir"} | {"ev":"acordar"}          tela apaga / acende (fw redea-1.1+)
              {"ev":"brilho","v":40}                   backlight 5-255
              {"ev":"barra","txt":"..."}               texto na barra do topo
              {"ev":"ack","id":"discord","ok":true}
              {"ev":"err","id":"discord","msg":"..."}
```

Um `hello` recarrega o `config.json` do disco, então reiniciar a placa já
aplica as suas edições sem reiniciar o agente. Mexer no `arte.py` invalida o
cache de JPEGs em `cache/`; a primeira subida depois renderiza tudo de novo.
Arte de card vivo não vai para o disco: só a última versão fica em memória.
