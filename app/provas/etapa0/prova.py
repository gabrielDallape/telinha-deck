"""
Etapa 0 do PLANO.md: provar, antes de escrever o app, que as pecas arriscadas
sobrevivem ao empacotamento e que a janela com a placa virtual funciona.

    python prova.py            abre a janela: diagnostico + placa virtual
    python prova.py --diag     so o diagnostico, em JSON, sem janela
    python prova.py --auto     abre a janela, espera a pagina desenhar a placa e
                               devolver o relatorio pelo WebSocket, e fecha.
                               Grava o resultado em prova_resultado.json

O mesmo arquivo roda como script e como TELINHA-prova.exe (PyInstaller). Cada
verificacao mexe numa peca suspeita de verdade, em vez de so importar:
  pycaw/comtypes  le o volume do Windows
  winsdk          pergunta ao Windows o que esta tocando (SMTC)
  pywin32         extrai o icone de um .exe
  Pillow+fontes   desenha um card com o arte.py do agente e a fonte Phosphor
  sounddevice     lista as saidas e decodifica um wav (sem tocar)
  pyserial        procura a placa nas portas
  obsws-python    importa o cliente do OBS
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

CONGELADO = getattr(sys, "frozen", False)
if CONGELADO:
    BASE = Path(sys._MEIPASS)
    AGENTE = BASE / "agent"
else:
    BASE = Path(__file__).resolve().parent
    AGENTE = BASE.parents[2] / "agent"
sys.path.insert(0, str(AGENTE))

# no topo de proposito: com `from __future__ import annotations` o FastAPI
# resolve a anotacao `ws: WebSocket` pelos globais do modulo. Importado dentro
# da funcao, ele trata `ws` como parametro de query e recusa o WebSocket (403).
from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

SAIDA = (Path(sys.executable).parent if CONGELADO else BASE) / "prova_resultado.json"


# ------------------------------------------------------------ verificacoes

def _verifica(nome: str, fn) -> dict:
    t0 = time.perf_counter()
    try:
        detalhe = fn()
        ok = True
    except Exception as e:
        detalhe = f"{type(e).__name__}: {e}"
        ok = False
        traceback.print_exc()
    return {"nome": nome, "ok": ok, "detalhe": str(detalhe)[:200],
            "ms": round((time.perf_counter() - t0) * 1000)}


def _pycaw():
    from comtypes import CoInitialize
    from pycaw.pycaw import AudioUtilities
    CoInitialize()
    ep = AudioUtilities.GetSpeakers().EndpointVolume
    return f"volume {round(ep.GetMasterVolumeLevelScalar() * 100)}%, mudo={bool(ep.GetMute())}"


def _smtc():
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Mgr)

    async def ler():
        mgr = await Mgr.request_async()
        ses = mgr.get_current_session()
        if ses is None:
            return "SMTC ok, nada tocando"
        props = await ses.try_get_media_properties_async()
        return f"SMTC ok: {props.title or '(sem titulo)'}"
    return asyncio.run(ler())


def _pywin32():
    import icones
    img = icones.icone_rgba(os.path.join(os.environ["WINDIR"], "explorer.exe"), 64)
    if img is None:
        raise RuntimeError("icone nao extraido")
    return f"icone do explorer {img.size[0]}x{img.size[1]}"


def _arte():
    import arte
    if not Path(arte.F_PHOSPHOR).exists():
        raise RuntimeError(f"fonte Phosphor ausente: {arte.F_PHOSPHOR}")
    img = arte.botao_icone(304, 200, {"icon": "broadcast", "label": "Live", "color": "#E5484D"})
    jpeg = arte.para_jpeg(img, 90)
    return f"card 304x200 em JPEG de {len(jpeg) // 1024} KB"


def _som():
    import numpy  # noqa: F401
    import sounddevice as sd
    import soundfile as sf
    saidas = [d["name"] for d in sd.query_devices() if d["max_output_channels"] > 0]
    wav = AGENTE / "pacotes" / "soundboard" / "sons" / "Ding.wav"
    dados, taxa = sf.read(str(wav), dtype="float32")
    return f"{len(saidas)} saidas; Ding.wav {len(dados) / taxa:.1f} s"


def _serial():
    from serial.tools import list_ports
    portas = [f"{p.device} ({p.vid:04X})" if p.vid else p.device for p in list_ports.comports()]
    placa = [p.device for p in list_ports.comports() if p.vid in (0x1A86, 0x303A)]
    return f"portas: {', '.join(portas) or 'nenhuma'}; placa: {', '.join(placa) or 'nao achada'}"


def _obs():
    import obsws_python  # noqa: F401
    import websocket  # noqa: F401
    return "obsws-python importa"


VERIFICACOES = [
    ("Audio do Windows (pycaw)", _pycaw),
    ("O que esta tocando (winsdk/SMTC)", _smtc),
    ("Icone de app (pywin32)", _pywin32),
    ("Arte do card (Pillow + fontes)", _arte),
    ("Soundboard (sounddevice + soundfile)", _som),
    ("Serial (pyserial)", _serial),
    ("OBS (obsws-python)", _obs),
]


def diagnostico() -> list:
    return [_verifica(n, f) for n, f in VERIFICACOES]


# ------------------------------------------------------- placa virtual

def _cards() -> list:
    """Doze cards da home de verdade, desenhados pelo arte.py do agente."""
    import arte
    specs = [
        {"icon": "mic", "label": "Mic", "color": "#5B6572"},
        {"icon": "volume", "label": "Som", "color": "#5B6572", "nivel": 58},
        {"icon": "broadcast", "label": "Live", "color": "#E5484D"},
        {"icon": "gravar", "label": "Gravar", "color": "#E5484D"},
        {"icon": "film", "label": "Cenas", "color": "#7C66DC", "type": "page"},
        {"icon": "megafone", "label": "Sons", "color": "#E5484D", "type": "page"},
        {"icon": "claude", "label": "Claude", "color": "#D97757", "type": "page"},
        {"icon": "apps", "label": "Apps", "color": "#7C66DC", "type": "page"},
        {"icon": "play", "label": "Tocar", "color": "#30A46C"},
        {"icon": "volume_down", "label": "Vol -", "color": "#3E63DD"},
        {"icon": "volume_up", "label": "Vol +", "color": "#3E63DD"},
        {"icon": "lua", "label": "Descansar", "color": "#6E56CF", "type": "page"},
    ]
    return [arte.para_jpeg(arte.botao_icone(304, 200, s), 90) for s in specs]


def cria_servidor(token: str, estado: dict):
    app = FastAPI()
    web = BASE / "web" / "dist"

    @app.get("/api/diag")
    def api_diag():
        return JSONResponse(estado["diag"])

    @app.websocket("/ws/placa")
    async def ws_placa(ws: WebSocket):
        # so a janela que o proprio app abriu conhece o token
        if ws.query_params.get("token") != token:
            await ws.close(code=4401)
            return
        await ws.accept()
        cards = await asyncio.to_thread(_cards)
        await ws.send_text(json.dumps({"ev": "layout", "cols": 4, "rows": 3,
                                       "w": 304, "h": 200, "n": len(cards)}))
        for i, jpeg in enumerate(cards):
            await ws.send_text(json.dumps({"ev": "img", "i": i, "len": len(jpeg)}))
            await ws.send_bytes(jpeg)
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                if "toque" in msg:
                    await ws.send_text(json.dumps({"ev": "eco", "i": msg["toque"],
                                                   "t": msg.get("t")}))
                elif "relatorio" in msg:
                    estado["relatorio"] = msg["relatorio"]
                    estado["fim"].set()
        except WebSocketDisconnect:
            pass

    app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
    return app


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    if sys.stdout is not None:          # pythonw.exe: sem console, stdout e None
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    auto = "--auto" in sys.argv
    t_inicio = time.perf_counter()

    if "--diag" in sys.argv:
        d = diagnostico()
        print(json.dumps(d, ensure_ascii=False, indent=2))
        SAIDA.write_text(json.dumps({"diag": d}, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if all(v["ok"] for v in d) else 1

    import uvicorn
    import webview

    token = secrets.token_urlsafe(16)
    estado = {"diag": diagnostico(), "relatorio": None, "fim": threading.Event()}
    porta = porta_livre()
    servidor = uvicorn.Server(uvicorn.Config(cria_servidor(token, estado), host="127.0.0.1",
                                             port=porta, log_level="warning"))
    threading.Thread(target=servidor.run, daemon=True, name="api").start()
    while not servidor.started:
        time.sleep(0.02)

    url = f"http://127.0.0.1:{porta}/?token={token}" + ("&auto=1" if auto else "")
    janela = webview.create_window("TELINHA - prova da etapa 0", url,
                                   width=1360, height=900, background_color="#0E1116")

    def vigia():
        # --auto: a pagina manda o relatorio depois de desenhar os 12 cards
        if estado["fim"].wait(timeout=60 if auto else None) and auto:
            time.sleep(0.5)
        if auto:
            janela.destroy()

    if auto:
        threading.Thread(target=vigia, daemon=True).start()
    webview.start()

    if auto:
        r = {"diag": estado["diag"], "janela": estado["relatorio"],
             "segundos_total": round(time.perf_counter() - t_inicio, 1)}
        SAIDA.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(r, ensure_ascii=False, indent=2))
        ok = all(v["ok"] for v in estado["diag"]) and bool(estado["relatorio"]) \
            and estado["relatorio"].get("ok")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
