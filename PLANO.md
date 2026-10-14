# TELINHA — plano do software

Escrito em 07/10/2026. O objetivo é sair de "um agente Python que lê um JSON"
para **um aplicativo instalável, local, modular**, que controla a placa e mais
tarde pode ser baixado e atualizado por outras pessoas. Tudo o que funciona
hoje continua funcionando, e várias coisas melhoram.

---

## 1. Decisões que guiam todo o resto

1. **A placa continua burra.** O protocolo serial de hoje fica. Firmware só muda
   quando ganhar *capacidade* nova (botões de tamanhos diferentes, remendo), e o
   app conversa com firmware velho e novo.
2. **Python continua sendo o motor.** pycaw, SMTC, SendInput, Pillow, Spotify e
   agenda já funcionam. Reescrever em outra linguagem são meses para voltar ao
   ponto de hoje. A interface é web (React), dentro de uma janela nativa.
3. **O núcleo não sabe o que é Spotify.** Toda função é módulo. O núcleo sabe
   falar com a placa, montar páginas, rotear toques e carregar módulos.
4. **As regras duras viram código do núcleo, não disciplina.** Card vivo com id
   fixo e versão, nada lento no loop serial, `exigir` antes de digitar: quem
   escreve um módulo não consegue quebrar essas regras.
5. **Programa e dados separados desde o primeiro dia.** O programa fica em
   `Arquivos de Programas`, e os seus dados (config, contas, cache, módulos
   baixados) em `%APPDATA%\TELINHA`. É isso que deixa atualizar sem perder nada.
6. **Ninguém precisa da placa para usar o editor.** O app tem uma *placa
   virtual*, que mostra na tela do PC exatamente o que a placa mostraria. Serve
   para desenvolver, para dar suporte e para demonstrar o produto.
7. **O código novo nasce ao lado do antigo.** O `agent/` de hoje roda a placa
   até o app novo passar na lista de paridade (seção 9). A troca é um clique, e
   a volta também.

---

## 2. Arquitetura

```
TELINHA.exe  (um processo; a bandeja vigia e reinicia se cair)
│
├── NÚCLEO ─────────────────────────────────────────────────────────────
│   ├─ Ligação       porta serial, protocolo, fila de arte, confirmações,
│   │                retry por imgbad, remendo parcial (do RÉDEA),
│   │                orçamento de bytes/s, negociação de capacidades
│   ├─ Compositor    perfil → página → layout + arte (cache em disco/memória)
│   ├─ Roteador      toque → ação → passos; navegação; perfis por janela/evento
│   ├─ Estado        barramento de chaves (mic_muted, obs_live…) → `state`
│   ├─ Hospedeiro    carrega módulos, dá a cada um uma thread/pool,
│   │                isola erros, desliga módulo que cai em loop
│   ├─ Armazém       perfis, config, contas (Gerenciador de Credenciais),
│   │                histórico de versões do perfil, migrações de esquema
│   └─ API local     HTTP + WebSocket em 127.0.0.1, com token de sessão
│
├── MÓDULOS ────────────────────────────────────────────────────────────
│   áudio · mídia · spotify · agenda · clima · sistema · foco · projetos
│   claude · discord · obs · soundboard · atalhos de app (pacotes) · …
│
└── INTERFACE ──────────────────────────────────────────────────────────
    janela (pywebview → WebView2 do Windows) com o editor React
    ícone na bandeja: ligar/desligar, abrir, status
```

### Threads (o que garante que a placa nunca trava)

| quem | onde roda | pode bloquear? |
|---|---|---|
| Ligação (serial) | thread própria, dona exclusiva da porta | nunca |
| Ação de toque | pool de workers; resultado volta por fila | sim, até o timeout (5 s) |
| Módulo vivo (clima, OBS…) | thread do módulo | sim |
| Render de arte | pool de 2 workers, com prioridade para a página visível | sim |
| API e interface | asyncio (uvicorn) | não |

Toda comunicação entre elas é por fila. A thread serial **não chama código de
módulo**: só lê o que já está pronto. Um módulo travado vira um aviso na barra.

### Capacidades do firmware

O `hello` passa a trazer `"caps": ["remendo", "spans", "brilho"]`. Firmware
antigo, sem `caps`, cai no modo de hoje. Assim o app não exige regravar a placa
de ninguém para funcionar, e os recursos novos aparecem quando a placa os tem.

---

## 3. Modelo de dados: o coração do app

Hoje um botão mistura três coisas: como ele parece, o que ele faz e de que
estado ele acende. Separadas, cada uma vira uma peça reutilizável no editor:

```
Perfil
 └─ Página ("home", "obs", "obs.cenas")
     ├─ tipo: fixa | gerada (provedor) | rota com parâmetro (sessao/<id>)
     ├─ gatilhos: janela em foco, evento ("claude pediu permissão"), horário
     ├─ grade: 4x3, 5x3… (com "spans": botão 2x1, 2x2)
     └─ Botão (slot)
         ├─ aparência   widget + parâmetros   (ícone fixo, "capa da música", "relógio")
         ├─ ao tocar    lista de passos       (tecla, abrir app, página, módulo.ação)
         ├─ segurar     outra lista (opcional)
         └─ aceso por   chave de estado       ("mic_muted", "obs.live")
```

- **Arquivo:** um perfil é um JSON com `"esquema": 2`. O `config.json` de hoje é
  importado automaticamente na primeira abertura (o esquema 1).
- **Histórico:** cada salvamento guarda a versão anterior (últimas 50). "Desfazer"
  e "voltar para ontem" ficam de graça, e um perfil quebrado nunca deixa a tela
  inutilizável.
- **Id de arte:** o núcleo calcula. Arte fixa = hash da aparência; arte viva = id
  fixo do botão + versão do widget. O módulo nunca escolhe id.
- **Páginas que pulam:** um evento de módulo pode abrir uma página por cima e
  fechá-la sozinha. É assim que o "Claude quer rodar `npm install`: Aprovar /
  Negar" aparece sem você navegar.

---

## 4. Módulos

### Dois tipos

| | **Pacote** (só dados) | **Módulo** (código Python) |
|---|---|---|
| serve para | atalhos de um app: Fusion, SolidWorks, Photoshop, VS Code | integrações com estado: Spotify, OBS, Claude, agenda |
| contém | `pacote.json`: detectar, páginas, botões com teclas | `modulo.json` + `__init__.py` |
| é seguro compartilhar? | sim, não roda código | só de fonte confiável |
| quem cria | qualquer um, pelo editor | desenvolvedor |

Os `agent/pacotes/` que já existem são o tipo da esquerda.

### Como um módulo se parece

```python
# modulos/spotify/__init__.py
from telinha.sdk import Modulo, acao, widget, provedor, estado

class Spotify(Modulo):
    contas = ["spotify"]                       # pede login na tela de contas

    @acao("curtir", nome="Curtir faixa")
    def curtir(self, ctx):
        self.api(ctx.conta).curtir_toggle()

    @widget("tocando", nome="Tocando agora", tamanhos=["1x1", "2x2"])
    def tocando(self, ctx, w, h):
        return self.desenha_capa(w, h)         # Image do Pillow

    def versao_tocando(self):                  # o núcleo compara e manda só se mudou
        return self.faixa_id + ("|p" if self.pausado else "")

    @provedor("playlists")                     # página gerada: um botão por playlist
    def playlists(self, ctx):
        return [self.botao_tocar(p) for p in self.api(ctx.conta).playlists()]

    @estado("curtida")                         # vira a chave "spotify.curtida"
    def curtida(self):
        return self.faixa_curtida
```

```json
// modulos/spotify/modulo.json
{
  "id": "spotify", "nome": "Spotify", "versao": "1.0.0", "sdk": 1,
  "permissoes": ["rede", "contas"],
  "config": {
    "intervalo_s": {"tipo": "numero", "padrao": 3, "rotulo": "Atualizar a cada (s)"}
  }
}
```

- `config` vira **formulário automático** no editor. Ninguém escreve tela de
  configuração para módulo.
- `permissoes` aparece ao instalar um módulo de terceiros (rede, teclado,
  arquivos, áudio).
- Um módulo só liga quando algum botão usa algo dele. Nada roda à toa (como o
  `Sistema` faz hoje com o psutil).
- O núcleo dá ao módulo: log, armazenamento próprio, contas, `ctx.janela_da_frente`,
  `ctx.recado()` para a barra, e utilitários de arte (`arte.botao_icone`, fontes,
  paleta), para que todo módulo saia com a cara do produto.

### Módulos da versão 1

| módulo | de onde vem | o que acrescenta |
|---|---|---|
| áudio | `telinha_agent.py` (pycaw) | + **volume por app**, com o `som.py` do RÉDEA (o "deej com tela") |
| mídia | `midia.py` | — |
| spotify | `spotify.py` | + várias contas, playlists como página gerada |
| agenda | `vivos.Agenda` | + várias agendas e contas |
| clima, relógio, sistema, foco | `vivos.py` | — |
| projetos | `projetos.py` | — |
| claude | página atual + `sessoes.py`/`atividade.py` do RÉDEA | + cards por sessão, **hooks** com Aprovar/Negar com contexto |
| discord | pacote atual | — |
| obs | `obs.py` | + teste real, fontes de áudio |
| soundboard | `sons.py` | + assistente do cabo virtual |
| atalhos de app | `pacotes.py` | + pacotes Fusion 360, SolidWorks, Photoshop, Premiere, VS Code |
| janelas | `janelas.py` | ação "mandar app para o monitor 2" etc. |

---

## 5. A interface

Uma janela, quatro áreas:

```
┌─ BIBLIOTECA ───────┬─ PLACA (virtual ou espelho da real) ─┬─ PROPRIEDADES ────┐
│ 🔍 buscar           │  Home ▸ OBS ▸ Cenas                  │ Botão "Live"       │
│ ▾ Meus apps         │  ┌─────┬─────┬─────┬─────┐           │ Aparência          │
│   OBS ✓  Fusion +   │  │LIVE │GRAV │PAUS │REPL │           │  ícone, cor, rótulo│
│ ▾ Widgets           │  ├─────┼─────┼─────┼─────┤           │ Ao tocar           │
│   relógio, capa…    │  │CENAS│ MIC │SONS │HOME │           │  1. obs › live     │
│ ▾ Ações             │  └─────┴─────┴─────┴─────┘           │  + passo  ⏺ gravar │
│   tecla, abrir app… │  [desfazer] [histórico] [testar]     │ Aceso quando       │
│                     │                                       │  obs.live          │
├─────────────────────┴───────────────────────────────────────┴────────────────────┤
│ ● Placa conectada (COM13) · fw telinha-1.2 · serial 8%   Contas · Configurações  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **Placa:** recebe pelo WebSocket os mesmos JPEGs que vão para a serial, então o
  que você vê é o que a placa mostra. Clicar num botão seleciona; dois cliques
  "tocam" (testa a ação de verdade). Arrastar da biblioteca cria o botão.
- **Gravar atalho:** aperte as teclas e o passo é criado.
- **Pastas:** arrastar um botão para cima de outro cria uma sub-página.
- **Salvar é automático**, com histórico, e a placa atualiza na hora.
- **Contas:** Spotify e Google com várias contas, tokens no Gerenciador de
  Credenciais do Windows (sai o `agent/segredos/`).
- **Primeira abertura (assistente):** plugue a placa → o app acha a porta →
  confere o firmware (oferece gravar se for preciso) → mostra os apps
  encontrados → monta uma home inicial. Em dois minutos a pessoa tem tela.

**Tecnologia:** React + TypeScript + Vite, dnd-kit para arrastar. O build gera
arquivos estáticos que o núcleo serve. Node 24 já está instalado aqui.

---

## 6. Qualidade

- **Placa falsa** (vem do `teste_remendo.py` do RÉDEA): responde `imgok`, conta
  bytes e simula corrupção. Os testes de protocolo rodam sem hardware.
- **Imagens de referência:** cada widget renderizado vira um PNG de referência.
  Mexeu no desenho, o teste mostra a diferença lado a lado.
- **Contrato de módulo:** todo módulo passa num teste genérico (carrega, lista
  ações, renderiza widgets em todos os tamanhos, desliga limpo).
- **Modo seguro:** módulo que derruba o início três vezes seguidas é desligado,
  com aviso no app e na barra.
- **Log** rotativo em `%APPDATA%\TELINHA\logs`, com botão "copiar diagnóstico".

---

## 7. Distribuição (local agora, online depois)

| peça | escolha | por quê |
|---|---|---|
| empacotar | **Python embutível oficial** + `lib/` + código; atalho para `pythonw.exe -I iniciar.py` | o Smart App Control do Windows 11 recusa `.exe` sem assinatura; o `pythonw.exe` é assinado pela PSF (etapa 0) |
| empacotar, com certificado | PyInstaller **onedir** (`prova.spec` guardado) | quando houver assinatura: um `.exe` com o nome e o ícone do produto |
| instalador | extrair a pasta + criar atalhos; `Setup.exe` só assinado | um `Setup.exe` sem assinatura é barrado igual |
| janela | pywebview + WebView2 | o WebView2 já vem no Windows 11; o instalador baixa no Windows 10 |
| atualização | manifesto JSON + pacote assinado (Ed25519) | o app nunca instala algo que não foi assinado por você |
| canais | estável e beta | você testa no beta antes de soltar |
| firmware | `esptool` embutido + `.bin` pronto | o cliente nunca vê FQBN, `postv3` nem o patch da LovyanGFX |
| módulos | atualizam separados do app | corrigir o Spotify não exige versão nova do app inteiro |

**Custos e cuidados para quando for público:**
- **Certificado de assinatura de código: obrigatório, não opcional.** A etapa 0
  mostrou que o Smart App Control (ligado de fábrica em Windows 11 novos) não
  avisa: ele bloqueia o `.exe` sem assinatura. Sem certificado, a única rota é a
  do Python embutível.
- O Spotify e o Google limitam quantas pessoas podem logar num app que não foi
  aprovado por eles. O assistente pode guiar a pessoa a criar o próprio Client ID
  do Spotify (os quatro passos do README).
- Sem telemetria por padrão. Relatório de erro só com consentimento.

---

## 8. Etapas

Cada etapa termina com algo que funciona e tem um critério de "pronto".

### Etapa 0 — Provas de risco ✅ feita em 07/10/2026 (`app/provas/etapa0/RESULTADO.md`)
Resultado: todas as peças funcionam e a janela desenha a placa virtual (12
cards em ~340 ms, toque em ~3 ms), **mas o `.exe` do PyInstaller é barrado pelo
Smart App Control**. A distribuição passa a ser o Python embutível assinado + o
nosso código (provado, `montar_pasta.py`), e o `.exe` próprio fica para quando
houver certificado. Falta testar num Windows limpo de verdade.

Plano original:
Duas coisas podem derrubar o plano inteiro. Por isso vêm primeiro:
1. **Empacotar:** um `.exe` de teste com pycaw, winsdk (SMTC), pywebview,
   sounddevice e Pillow, rodando num Windows limpo (máquina virtual ou outro
   PC). O pycaw/comtypes e o winsdk são os suspeitos de dar problema congelados.
2. **Janela:** pywebview abrindo uma página React servida pelo uvicorn, com
   WebSocket recebendo JPEG e desenhando a placa virtual.

**Pronto quando:** os dois rodam fora desta máquina. Se algo falhar, troca-se a
peça (Nuitka no lugar do PyInstaller, Tauri no lugar do pywebview) antes de
haver código em cima.

### Etapa 1 — Núcleo novo, mesma tela — 🟡 rodando na placa desde 07/10/2026
Feito: núcleo (`ligacao`, `compositor`, `roteador`, `estado`, `hospedeiro`,
`perfil`), SDK, 11 módulos portados, esquema 2 com histórico, importação do
agente, dados em `%APPDATA%\TELINHA`, placa falsa com 14 testes, bandeja nova.
Na placa real: 60 artes, precarga completa, perfil por janela funcionando, CPU
~1% de um núcleo. **Falta:** conferir os toques na placa e trocar o
atalho de iniciar com o Windows.

Plano original:
- Ligação, compositor, roteador, estado, hospedeiro e armazém, com a placa falsa.
- Os módulos portados um a um, sem mudar comportamento.
- O importador do `config.json` + pacotes → perfil esquema 2.
- Dados em `%APPDATA%\TELINHA`.

**Pronto quando:** a lista de paridade (seção 9) passa inteira com a placa real,
e a bandeja troca do `agent/` para o app novo.

### Etapa 2 — O app com janela
- Bandeja nova + janela: status, placa virtual/espelho, lista de módulos
  ligar/desligar, configurações gerais (porta, brilho, descanso).

**Pronto quando:** dá para usar o dia inteiro sem abrir um JSON, exceto para
editar botões.

### Etapa 3 — Editor
- Biblioteca, arrastar e soltar, propriedades, passos de ação, gravar atalho,
  pastas, desfazer, histórico, "testar".

**Pronto quando:** você recria a sua home e a página do OBS do zero, só pela
janela.

### Etapa 4 — Contas e formulários
- Tela de contas com várias contas, e o formulário automático de cada módulo.

**Pronto quando:** Spotify pessoal e de trabalho trocam por um seletor no botão.

### Etapa 5 — Módulos de produto
- Volume por app, sessões do Claude com hooks, OBS testado de verdade,
  soundboard com cabo virtual, pacotes de atalho (Fusion, SolidWorks, Photoshop,
  Premiere, VS Code).
- Firmware novo com `caps`: botões 2x1/2x2 e remendo.

**Pronto quando:** cada módulo tem um caso de uso que você usa ou mostraria
numa demonstração.

### Etapa 6 — Instalador
- `Setup.exe`, assistente de primeira abertura, gravação de firmware pelo app.

**Pronto quando:** alguém que não é você instala, pluga a placa e tem uma tela
funcionando sem ajuda.

### Etapa 7 — Online
- Página de download, atualização automática assinada, canal beta, catálogo de
  pacotes e módulos.

---

## 9. Lista de paridade (o que não pode se perder)

- [ ] acha a porta sozinho (CH343 / Espressif) e reconecta ao desplugar
- [ ] precarga das páginas, cache de arte em disco, retry por `imgbad`
- [ ] home: Discord/Chrome/Spotify abrindo no monitor 2, mídia ao vivo com capa,
      mic (Windows + atalho do Discord), som com nível, recorte, vol −/+,
      descansar, apps, projetos
- [ ] barra: hora + próxima reunião de hoje, "agente offline" quando cai
- [ ] descanso: relógio, clima, agenda grandes; entra sozinho após ociosidade,
      volta ao mexer; brilho baixo
- [ ] dormir/acordar pela bandeja
- [ ] agenda por `.ics` e por login do Google
- [ ] player: capa, progresso, curtir, aleatório, repetir (Spotify Web API)
- [ ] `musica_ou_app`: tocando → player, parado → abre o app
- [ ] projetos: um toque abre o terminal na pasta com o `claude`
- [ ] página Claude por foco: Falar (alt+k), Aprovar, Recusar, Remote, Usage,
      Modelo (`/model` + confirmar), Limpar, sempre com `exigir`
- [ ] página Discord por foco: mic, surdo, som, volume, monitor 2
- [ ] soundboard: pasta → botões, sobreposição, parar
- [ ] OBS: live, gravar, pausar, replay, cenas lidas do OBS, acesas pelo estado
- [ ] estado aceso: mic, som, curtida, aleatório, repetir, OBS
- [ ] cards vivos sem piscar: relógio, clima, música, foco, agenda, sistema
- [ ] `--list` e `--test` (viram comandos do app: `telinha lista`, `telinha testa`)

---

## 10. Estrutura de pastas

```
TELINHA/
├─ app/
│  ├─ telinha/
│  │  ├─ nucleo/      ligacao.py  compositor.py  roteador.py  estado.py
│  │  │               hospedeiro.py  armazem.py  migracoes.py  capacidades.py
│  │  ├─ sdk/         Modulo, @acao, @widget, @provedor, @estado, ctx
│  │  ├─ arte/        base de desenho, fontes, ícones, paleta (o arte.py dividido)
│  │  ├─ api/         servidor.py (FastAPI), rotas, websocket da placa virtual
│  │  ├─ bandeja.py
│  │  └─ __main__.py  `python -m telinha` / TELINHA.exe
│  ├─ modulos/        audio/ midia/ spotify/ agenda/ clima/ sistema/ foco/
│  │                  projetos/ claude/ obs/ soundboard/ janelas/
│  ├─ pacotes/        claude/ discord/ fusion360/ solidworks/ …
│  └─ testes/         placa_falsa.py, referencias/ (PNGs), test_*.py
├─ editor/            React + Vite (build → app/telinha/api/estatico/)
├─ instalador/        telinha.spec (PyInstaller), telinha.iss (Inno Setup)
├─ firmware/          como hoje
├─ agent/             o agente atual, até a etapa 1 terminar
└─ arquivo/           como hoje
```

---

## 11. O que fica de fora de propósito

- **Mac e Linux:** a camada de sistema (áudio, janelas, mídia) é toda Windows.
  O desenho por módulos deixa a porta aberta, mas não agora.
- **Blocos visuais (tipo Scratch):** a lista de passos resolve 95% dos casos.
  Os blocos entram quando alguém pedir "se… senão" de verdade.
- **Loja com pagamento e módulos de terceiros com código:** antes, só pacotes
  (dados) compartilháveis.
- **Wi-Fi na placa:** a USB resolve energia e dados de uma vez.
- **Ler a tela de jogos:** descartado em 2026-09 e continua descartado.
