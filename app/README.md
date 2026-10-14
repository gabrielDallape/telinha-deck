# TELINHA: o app

Núcleo novo da etapa 1 do `PLANO.md`. Faz o que o `agent/` fazia, organizado em
núcleo + módulos, com os dados fora da pasta do programa.

## Rodar

De dentro de `app/`:

```powershell
python -m telinha bandeja          # ícone na bandeja; sobe e vigia o núcleo
python -m telinha janela           # a janela (também: duplo clique no ícone da bandeja)
python -m telinha rodar            # só o núcleo, no console
python -m telinha lista            # pacotes, módulos, páginas e o tamanho das artes
python -m telinha testa home/mic   # dispara um botão como se fosse um toque (mexe no PC!)
python -m pytest testes -q         # o núcleo inteiro contra a placa falsa
```

## A janela

A placa desenhada na tela, espelhando a de verdade (ou uma tela virtual, sem
placa).

- **Editar** (padrão): clicar num botão abre as propriedades à direita, com o
  card como vai ficar (preview ao vivo). Tudo salva sozinho quando você para de
  mexer. Duplo clique testa o botão.
- **Adicionar:** a biblioteca à direita (widgets por categoria e "Seus apps",
  do Menu Iniciar). Arraste para um quadrado vazio, ou clique para pôr no
  primeiro livre. "Pasta" cria uma página dentro da atual.
- **Organizar:** arraste um botão para outro quadrado (ocupado: os dois
  trocam). Solte em cima de uma pasta para guardar lá dentro.
- **Páginas:** criar, renomear (o título no alto), mudar a grade, apagar.
- **Desfazer/refazer:** Ctrl+Z e Ctrl+Y (as setas no topo). Delete apaga o
  botão selecionado.
- **Usar:** clicar num botão é o mesmo que tocar na placa.
- **Módulos:** ligar e desligar pacotes de apps e configurar cada módulo
  (cidade do clima, Spotify, OBS…).

Formulários das ações e itens da biblioteca vêm do `modulo.json` de cada
módulo (`acoes` com `campos`, e `biblioteca`).

A janela é só uma vista: fala com o núcleo pela API local (`telinha/api.py`,
127.0.0.1:47800, token em `%APPDATA%\TELINHA\api.json`). Fechar a janela não
desliga o painel. O código está em `app/editor/` (React + Vite):

```powershell
cd app/editor; npm run build      # gera app/telinha/web, que o núcleo serve
```

## Onde fica cada coisa

| | onde |
|---|---|
| programa | `app/telinha/` (núcleo), `app/modulos/`, `app/pacotes/` |
| **seus dados** | `%APPDATA%\TELINHA\` |
| páginas e botões | `%APPDATA%\TELINHA\perfil.json` (esquema 2) |
| versões anteriores do perfil | `%APPDATA%\TELINHA\perfil.hist\` (as últimas 50) |
| tokens (Spotify, Google) | `%APPDATA%\TELINHA\segredos\` |
| ícones e imagens do perfil | `%APPDATA%\TELINHA\arquivos\` ("arquivos/x.png" no perfil) |
| log | `%APPDATA%\TELINHA\telinha.log` |

Na primeira abertura, sem `perfil.json`, o app importa o `agent/config.json`,
os tokens de `agent/segredos/` e os logos de `agent/logos/`. Depois disso,
**editar o `agent/config.json` não muda mais nada**: o perfil é o de
`%APPDATA%`. Mudou o perfil? A placa aplica no próximo `hello` (reinicie a placa
ou o núcleo).

## Peças do núcleo

| arquivo | faz |
|---|---|
| `nucleo.py` | junta tudo; acha a porta, reconecta |
| `ligacao.py` | a serial: fila de arte, confirmações, reenvio, precarga, cards vivos. **Não chama código de módulo** |
| `compositor.py` | perfil → layout e JPEG; **calcula o id da arte** (`<botão>~<hash da aparência>`); desenha num pool com prazo |
| `roteador.py` | toque → passos num pool de workers; perfil por janela; descanso por ociosidade |
| `estado.py` | coletor: pergunta o estado aos módulos numa thread |
| `hospedeiro.py` | carrega módulos, registra o que oferecem, liga só os usados, modo seguro |
| `perfil.py` | esquema 2, histórico, importação do agente, pacotes de app |
| `sdk.py` | o que um módulo vê (ver a docstring) |
| `arte.py`, `icones.py`, `janelas.py`, `apps.py` | desenho e Windows, vindos do agente |

## Botão no esquema 2

```json
{
  "id": "mic",
  "aparencia": {"widget": "icone", "icon": "mic", "color": "#5B6572"},
  "toque": [{"type": "mic_toggle"},
            {"type": "key_app", "app": "discord", "target": "ctrl+alt+shift+m", "exigir": false}],
  "aceso": "mic_muted"
}
```

`aparencia` é como ele parece, `toque` é a lista de passos e `aceso` é a chave
de estado que o acende. Opcional: `depois` (página para onde ir depois).

## Módulos

Um por pasta em `modulos/`, com `modulo.json` + `__init__.py` (uma subclasse de
`Modulo`, ver `telinha/sdk.py`). Um módulo só liga se o perfil usa algo dele, ou
com `"sempre": true`. Três quedas seguidas ao iniciar desligam o módulo (modo
seguro; o contador fica em `%APPDATA%\TELINHA\modulos\<id>\quedas`).

| módulo | oferece |
|---|---|
| `audio` | mic/som mudo e volume; estados `mic_muted`, `sys_muted`, `sys_vol`… |
| `janelas` | `focus_or_launch`, `focus`, `launch`, `url`, `shell`, `key`, `media`, `key_app`, `digitar` |
| `midia` | widget `musica` (padrão, `player`, `controle`); `spotify`, `musica_ou_app`; estados `sp_*` |
| `relogio`, `clima`, `agenda`, `sistema`, `foco` | os widgets de mesmo nome; agenda põe a próxima reunião na barra; `foco` é ação também |
| `projetos` | página `gerar: projetos.lista`, widget `projeto`, `abrir_projeto`, texto `{projetos}` |
| `soundboard` | página `gerar: soundboard.sons`, `som`, `som_parar` |
| `obs` | página `gerar: obs.cenas`, `obs`; estados `obs_live`, `obs_rec`, `obs_pausa`, `obsc_*` |

Os pacotes de app (`pacotes/<app>/pacote.json`) já estão no esquema 2. Ver a
seção "Pacotes de app" do `agent/README.md`, que continua valendo.
