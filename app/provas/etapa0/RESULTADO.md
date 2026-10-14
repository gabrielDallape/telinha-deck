# Etapa 0: resultado (07/10/2026)

Duas provas de risco do `PLANO.md`, feitas antes de escrever o app.

## O que foi testado

`prova.py` exercita de verdade cada peça suspeita, e a janela desenha a placa
virtual recebendo JPEG por WebSocket:

| peça | o que a prova faz | resultado |
|---|---|---|
| pycaw / comtypes | lê volume e mudo do Windows | ok |
| winsdk (SMTC) | pergunta o que está tocando | ok |
| pywin32 | extrai o ícone do explorer.exe | ok |
| Pillow + fontes | desenha um card com o `arte.py` e a Phosphor | ok |
| sounddevice + soundfile | lista saídas, decodifica um wav | ok |
| pyserial | acha a placa (COM9/COM13, CH343) | ok |
| obsws-python | importa | ok |
| FastAPI + uvicorn + WebSocket | serve a página e manda 12 JPEGs | ok |
| pywebview (WebView2, Edge 154) | janela com a placa virtual | 12 cards em ~340 ms, toque ida e volta ~2-4 ms |

## A descoberta que muda o plano

**O Smart App Control do Windows 11 está ligado nesta máquina, no modo de
impor** (`VerifiedAndReputablePolicyState = 1`). Ele **recusa qualquer `.exe`
sem assinatura digital**: o `TELINHA-prova.exe` do PyInstaller nem abre
("Uma política de Controle de Aplicativo bloqueou este arquivo", eventos 3033
e 3077 no log CodeIntegrity). Não é um aviso que dá para pular.

Consequências:
- **PyInstaller, Nuitka ou qualquer `.exe` nosso** só rodam em PCs com o Smart
  App Control desligado, ou depois de **assinados** com um certificado
  reconhecido. Um `Setup.exe` (Inno Setup) sem assinatura tem o mesmo problema.
- Computadores novos com Windows 11 vêm com o Smart App Control ligado. Para um
  produto, **assinatura de código é obrigatória**, não opcional.
- Desligar o Smart App Control **não tem volta** sem reinstalar o Windows. Não é
  um caminho.

## A rota que funciona hoje, sem assinatura

**Python embutível oficial + bibliotecas em `lib/` + o nosso código + um
lançador.** O `python.exe`/`pythonw.exe` é assinado pela Python Software
Foundation, e as bibliotecas do PyPI têm reputação. Testado
com o Smart App Control ligado, numa pasta fora do projeto, com o PATH reduzido
ao `System32`:

| | peças | janela |
|---|---|---|
| `python.exe -I iniciar.py --auto` | 7/7 | 12 cards, toque 2,4 ms |
| `pythonw.exe -I iniciar.py --auto` | 7/7 | 12 cards em 342 ms, toque 2,3 ms |

- `montar_pasta.py` monta a pasta do zero (baixa o Python 3.12.4 embutível,
  instala as bibliotecas fixadas em `lib/`, copia o código). 189 MB.
- O atalho do app aponta para `pythonw.exe -I iniciar.py`. Sem `.exe` nosso.
- Achado no caminho: com `pythonw.exe`, `sys.stdout` é `None`; quem chamar
  `sys.stdout.reconfigure` cai. O app novo tem de prever isso desde o início.
- Achado no caminho: com `from __future__ import annotations`, o FastAPI não
  resolve `ws: WebSocket` importado dentro de função e recusa o WebSocket (403).
  Importar no topo do módulo.

## O que ainda não foi provado

- **Num Windows limpo de verdade** (outro PC ou máquina virtual). Aqui o teste
  foi isolado (pasta fora do projeto, PATH só com o System32, `python -I`), mas é
  a mesma máquina. Windows 11 Home não tem o Windows Sandbox.
- **Windows 10 sem WebView2** instalado.
- **O instalador.** Sem `.exe`, instalar é extrair a pasta e criar atalhos. Falta
  provar se o script que faz isso passa pelo Smart App Control.

## Arquivos

- `prova.py`: as verificações, o servidor e a janela (`--diag`, `--auto`)
- `web/`: a página (React + Vite), `npm run build` gera `web/dist`
- `montar_pasta.py`: a pasta distribuível sem `.exe`
- `prova.spec`: o PyInstaller, guardado para quando houver certificado
