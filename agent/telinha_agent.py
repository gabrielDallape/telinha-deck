"""
TELINHA - agente Windows para o painel touch ESP32-P4.

A placa desenha; este processo decide e executa. A tela pede uma pagina por id,
manda o id do botao tocado, e recebe de volta o ESTADO real do PC (mic mutado,
volume) - e o que faz o painel dizer a verdade em vez de so disparar comandos.

Protocolo, uma linha JSON por mensagem, UTF-8:

    placa -> PC   {"cmd":"hello","fw":"..."}          pede a home
                  {"cmd":"page","id":"dev"}           pede uma pagina
                  {"cmd":"btn","page":"home","id":"mic"}
                  {"cmd":"state"}

                  {"cmd":"imgok","i":k}               confirma um pedaco de arte

    PC -> placa   {"ev":"layout","page":...,"title":...,"back":...,
                   "grid":{...},"buttons":[{"id","art","art_on","state_key"}]}
                  {"ev":"img","id":...,"w":...,"h":...,"len":N,"off":bytes,
                   "i":k,"n":total,"d":"<b64 de um pedaco do JPEG>"}
                  {"ev":"state","mic_muted":false,"sys_vol":42,...}
                  {"ev":"ack"|"err","id":...}

O visual inteiro de cada botao e composto aqui (ver arte.py) e vai para a placa
como JPEG; ela so estampa. Mexer no visual nao exige regravar o firmware.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import serial
from serial.tools import list_ports

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"

KNOWN_USB_IDS = [
    (0x1A86, 0x55D3),  # WCH CH343, a ponte UART da placa
    (0x303A, None),    # Espressif, USB nativa
]

# base64 por linha. O tamanho e um acordo: cada pedaco custa uma ida-e-volta de
# confirmacao, entao pedaco pequeno multiplica latencia; pedaco grande precisa de
# buffer na placa (12 KB de linha, 16 KB de RX). Medido: com 9000 aparecem
# caracteres corrompidos de vez em quando; com 4000, nao. O retry por "imgbad"
# cobre o resto.
CHUNK_B64 = 4000

ESTADO_PATH = BASE / "estado.json"
COMANDO_PATH = BASE / "comando.txt"     # a bandeja escreve "dormir"; o agente le e obedece


class Desligar(Exception):
    """Pedido da bandeja: apagar a tela da placa e encerrar o agente."""


def grava_estado(**campos) -> None:
    """Um JSON pequeno para a bandeja (bandeja.py) saber se a placa esta falando."""
    try:
        ESTADO_PATH.write_text(json.dumps({"quando": time.time(), **campos}), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------- audio (pycaw)

try:
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL, CoInitialize
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    HAVE_PYCAW = True
except Exception:
    HAVE_PYCAW = False

# Os endpoints ficam em cache. Recriar a cada leitura (1x por segundo) fazia o
# comtypes derrubar ponteiros COM no __del__ com "access violation" - o objeto
# morria fora da ordem em que o COM espera. Um endpoint vive o processo todo.
_cache_audio: dict = {}


def _endpoint(qual: str):
    if qual in _cache_audio:
        return _cache_audio[qual]
    dev = AudioUtilities.GetMicrophone() if qual == "mic" else AudioUtilities.GetSpeakers()
    # A API do pycaw e inconsistente: GetSpeakers() devolve o wrapper AudioDevice
    # (que ja expoe .EndpointVolume) e GetMicrophone() devolve o IMMDevice cru.
    pronto = getattr(dev, "EndpointVolume", None)
    if pronto is not None:
        ep = pronto
    else:
        cru = getattr(dev, "_dev", dev)
        ep = cast(cru.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                  POINTER(IAudioEndpointVolume))
    _cache_audio[qual] = ep
    return ep


def _invalida_audio() -> None:
    """Dispositivo padrao trocou (fone plugado, monitor ligado): refaz o cache."""
    _cache_audio.clear()


def audio_state() -> dict:
    if not HAVE_PYCAW:
        return {}
    out = {}
    for qual, chave_mute, chave_vol in (("sys", "sys_muted", "sys_vol"),
                                        ("mic", "mic_muted", "mic_vol")):
        try:
            ep = _endpoint(qual)
            out[chave_mute] = bool(ep.GetMute())
            out[chave_vol] = round(ep.GetMasterVolumeLevelScalar() * 100)
        except Exception:
            _invalida_audio()
    return out


def _exigir_pycaw() -> None:
    if not HAVE_PYCAW:
        raise RuntimeError("pycaw nao instalado: pip install pycaw comtypes")


def toggle_mute(qual: str) -> bool:
    _exigir_pycaw()
    ep = _endpoint(qual)
    novo = 0 if ep.GetMute() else 1
    ep.SetMute(novo, None)
    return bool(novo)


def set_mute(qual: str, muted: bool) -> bool:
    _exigir_pycaw()
    _endpoint(qual).SetMute(1 if muted else 0, None)
    return muted


def set_volume(qual: str, pct: int) -> int:
    _exigir_pycaw()
    pct = max(0, min(100, int(pct)))
    _endpoint(qual).SetMasterVolumeLevelScalar(pct / 100.0, None)
    return pct


# ------------------------------------------------------------ teclado / midia

user32 = ctypes.windll.user32
KEYEVENTF_KEYUP = 0x0002

VK = {
    "play_pause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2,
    "volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD,
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "tab": 0x09, "esc": 0x1B, "enter": 0x0D, "space": 0x20,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "prtsc": 0x2C,
}


def _vk(nome: str) -> int:
    nome = nome.strip().lower()
    if nome in VK:
        return VK[nome]
    if len(nome) == 1:
        return user32.VkKeyScanW(ord(nome.upper())) & 0xFF
    raise ValueError(f"tecla desconhecida: {nome}")


def send_key(combo: str) -> None:
    teclas = [_vk(p) for p in combo.split("+") if p.strip()]
    for k in teclas:
        user32.keybd_event(k, 0, 0, 0)
    for k in reversed(teclas):
        user32.keybd_event(k, 0, KEYEVENTF_KEYUP, 0)


# ----------------------------------------------------------------- ociosidade

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def ociosidade_s() -> float:
    """Segundos desde o ultimo teclado/mouse no Windows (GetLastInputInfo)."""
    li = _LASTINPUTINFO()
    li.cbSize = ctypes.sizeof(li)
    if not user32.GetLastInputInfo(ctypes.byref(li)):
        return 0.0
    return (ctypes.windll.kernel32.GetTickCount() - li.dwTime) / 1000.0


# ------------------------------------------------------------------- lancador

_START_MENUS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
]
_atalhos_cache: dict | None = None


def _indexar_atalhos() -> dict:
    global _atalhos_cache
    if _atalhos_cache is not None:
        return _atalhos_cache
    idx = {}
    for raiz in _START_MENUS:
        if not raiz.is_dir():
            continue
        for lnk in raiz.rglob("*.lnk"):
            idx.setdefault(lnk.stem.lower(), lnk)
    _atalhos_cache = idx
    return idx


def resolver_app(nome: str):
    idx = _indexar_atalhos()
    alvo = nome.lower()
    if alvo in idx:
        return idx[alvo]
    parciais = [p for chave, p in idx.items() if alvo in chave]
    if parciais:
        return min(parciais, key=lambda p: len(p.stem))
    return None


def abrir_app(alvo: str) -> None:
    # "spotify:", "https://..." - protocolo: e assim que se abre app da Store,
    # que nao tem .exe nem atalho no Menu Iniciar
    if ":" in alvo and not Path(alvo).drive and "\\" not in alvo and "/" not in alvo.split(":", 1)[0]:
        os.startfile(alvo)
        return
    p = Path(os.path.expandvars(alvo))
    if p.exists():
        os.startfile(str(p))
        return
    lnk = resolver_app(alvo)
    if lnk:
        os.startfile(str(lnk))
        return
    subprocess.Popen(["cmd", "/c", "start", "", alvo], shell=False)


# -------------------------------------------------------------- despachante

class Executor:
    """Executa uma acao. Devolve o id de uma pagina quando o toque navega."""

    def __init__(self, painel, ligacao=None):
        self.painel = painel
        self.lig = ligacao      # None em --test: tudo sincrono

    def executar(self, acao: dict) -> str | None:
        tipo = acao.get("type")

        if tipo == "page":
            return acao["page"]

        if tipo == "focus_or_launch":
            alvo = acao["target"]
            import janelas
            if not janelas.focar_ou_none(alvo, acao.get("monitor"),
                                         acao.get("maximize", True)):
                # `launch` quando o que abre nao e o que se foca: app da Store
                # foca pelo exe ("Spotify") mas abre pelo protocolo ("spotify:")
                abrir_app(acao.get("launch") or alvo)

        elif tipo == "focus":
            import janelas
            if not janelas.focar_ou_none(acao["target"], acao.get("monitor"),
                                         acao.get("maximize", True)):
                raise RuntimeError("janela nao encontrada")

        elif tipo == "launch":
            abrir_app(acao["target"])

        elif tipo == "url":
            os.startfile(acao["target"])

        elif tipo == "shell":
            subprocess.Popen(acao["target"], shell=True)

        elif tipo == "key":
            send_key(acao["target"])

        elif tipo == "media":
            send_key(acao["key"])

        elif tipo == "key_app":
            # Atalho global de um app especifico. So dispara se ele estiver
            # aberto: solto, o atalho cairia em quem estiver na frente.
            import janelas
            if janelas.rodando(acao["app"]):
                send_key(acao["target"])
            elif acao.get("exigir", True):
                raise RuntimeError(f"{acao['app']} nao esta aberto")

        elif tipo == "mic_toggle":
            toggle_mute("mic")
        elif tipo == "mic_mute":
            set_mute("mic", True)
        elif tipo == "mic_unmute":
            set_mute("mic", False)
        elif tipo == "sys_mute_toggle":
            toggle_mute("sys")
        elif tipo == "volume":
            set_volume(acao.get("device", "sys"), acao["value"])

        elif tipo == "nada":
            pass

        elif tipo == "spotify":
            # controles finos da Web API: curtir, aleatorio, repetir, pular.
            # Play/pause/proxima/anterior seguem pelas teclas de midia, que
            # funcionam para qualquer app.
            sp = self.painel.musica.spotify
            if sp is None:
                raise RuntimeError("Spotify nao configurado (client_id)")
            op = acao.get("op", "")
            if op == "curtir":
                print("[spotify] curtida:", sp.curtir_toggle())
            elif op == "aleatorio":
                print("[spotify] aleatorio:", sp.aleatorio_toggle())
            elif op == "repetir":
                print("[spotify] repetir:", sp.repetir_ciclo())
            elif op == "pular":
                sp.pular(float(acao.get("segundos", 15)))
            elif op == "play_pause":
                sp.play_pause()
            else:
                raise ValueError(f"op do spotify desconhecida: {op!r}")

        elif tipo == "musica_ou_app":
            # Tocando algo: abre o player do painel. Parado: abre o app
            # (Spotify instalado, o protocolo spotify:, ou o player web).
            if self.painel.musica.estado.get("titulo") and not acao.get("so_app"):
                return acao.get("page", "player")
            alvo = acao.get("target", "Spotify")
            if resolver_app(alvo):
                abrir_app(alvo)
            else:
                try:
                    os.startfile(acao.get("uri", "spotify:"))
                except OSError:
                    os.startfile(acao.get("web", "https://open.spotify.com"))

        elif tipo == "digitar":
            # Digita na janela em foco - mas SO se ela for a esperada. Solto,
            # um "continua" + Enter cairia no Discord ou num shell qualquer.
            import janelas
            regra = acao.get("exigir", {"exe": "windowsterminal.exe"})
            if regra and not janelas.frente_bate(regra):
                raise RuntimeError(acao.get("erro", "janela certa nao esta na frente"))
            if acao.get("texto"):
                janelas.digitar(acao["texto"])
            if acao.get("tecla"):
                janelas.atalho([_vk(t) for t in acao["tecla"].split("+") if t.strip()])
            elif acao.get("enter", False):
                janelas.atalho([VK["enter"]])
            if acao.get("confirmar"):
                # O /model no meio da conversa abre um dialogo do Claude Code
                # que pede Enter. Espera ele aparecer em thread (nada lento no
                # loop serial) e so aperta se a janela ainda for a certa.
                def _confirma(espera=float(acao["confirmar"]), regra=regra):
                    time.sleep(espera)
                    if not regra or janelas.frente_bate(regra):
                        janelas.atalho([VK["enter"]])
                threading.Thread(target=_confirma, daemon=True).start()

        elif tipo == "foco":
            print(f"[foco] {self.painel.foco.toque()}")

        elif tipo == "som":
            # decodificar um mp3 na primeira vez leva dezenas de ms: fora do loop
            import sons
            cfg_sons = self.painel.cfg.get("sons")
            self._fundo(acao, lambda: print(f"[sons] {Path(acao['arquivo']).name}: "
                                            + sons.mixer(cfg_sons).tocar(
                                                acao["arquivo"], acao.get("volume"),
                                                acao.get("modo", "alternar"))))

        elif tipo == "som_parar":
            import sons
            sons.mixer(self.painel.cfg.get("sons")).parar()

        elif tipo == "obs":
            # rede: nunca no loop serial
            if not self.painel.obs:
                raise RuntimeError("pacote do OBS nao esta ativo")
            self._fundo(acao, lambda: self.painel.obs.executa(acao))

        elif tipo == "abrir_projeto":
            self.painel.projetos.abrir(acao["projeto"])

        elif tipo == "sequence":
            passos = acao["steps"]
            for k, passo in enumerate(passos):
                self.executar(passo)
                # O delay existe para dar tempo ao passo SEGUINTE. Dormir depois
                # do ultimo eram 50 ms de espera com ninguem atras.
                if k < len(passos) - 1:
                    time.sleep(passo.get("delay", 0.05))

        else:
            raise ValueError(f"acao desconhecida: {tipo!r}")

        # Acoes lentas (rede, RPC) NAO podem rodar aqui: seguram o ack e a
        # leitura da serial, e o painel inteiro fica morto. Mandar para uma
        # thread e avisar pela barra com self.lig.recado({"ev":"err",...}).
        return acao.get("then")

    def _fundo(self, acao: dict, fn) -> None:
        """Roda `fn` numa thread; o erro volta pela barra. Em --test, na hora."""
        if self.lig is None:
            fn()
            return

        def corre():
            try:
                fn()
            except Exception as e:
                print(f"[erro] {acao.get('id', '?')}: {e}")
                self.lig.recado({"ev": "err", "id": acao.get("id", ""), "msg": str(e)[:60]})
        threading.Thread(target=corre, daemon=True).start()


# ------------------------------------------------------------------- serial

def e_a_placa(porta: str, baud: int, espera: float = 1.5) -> bool:
    """Pergunta "quem" e espera um hello. A CH343 nao e so da placa: as placas
    da bancada LoRa usam a mesma ponte, e o agente pegava a primeira da lista e
    ficava falando sozinho com uma delas. DTR/RTS ficam baixos para nao
    resetar quem estiver do outro lado."""
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = porta, baud, 0.1
    s.dtr = s.rts = False
    try:
        s.open()
        s.write(b'{"ev":"quem"}\n')
        fim, buf = time.monotonic() + espera, b""
        while time.monotonic() < fim:
            buf += s.read(512)
            if b'"cmd":"hello"' in buf:
                return True
        return False
    except (serial.SerialException, OSError):
        return False  # aberta por outro programa, ou sumiu
    finally:
        try:
            s.close()
        except Exception:
            pass


def achar_porta(preferida: str, baud: int):
    if preferida and preferida != "auto":
        return preferida
    conhecidas = [p.device for p in list_ports.comports()
                  if any(p.vid == vid and (pid is None or p.pid == pid)
                         for vid, pid in KNOWN_USB_IDS)]
    for porta in conhecidas:
        if e_a_placa(porta, baud):
            return porta
    return None


def carregar_config() -> dict:
    """config.json + as paginas dos pacotes ativos (pacotes/<app>/pacote.json)."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    import pacotes
    return pacotes.aplicar(cfg, resolver_app)


class Ligacao:
    """Uma conexao serial com a placa."""

    def __init__(self, ser, painel):
        self.ser = ser
        self.painel = painel
        self.exec = Executor(painel, self)
        self.pagina_atual = ""
        self.enviados: set = set()      # ids de icone que a placa ja tem
        self.ultimo_estado: dict = {}
        self.proximo_estado = 0.0
        self.buf = b""
        self.imgok = -2         # ultimo pedaco de arte que a placa confirmou
        self.img_tem = False    # a placa respondeu "ja tenho esta arte"
        self.ruins: dict = {}   # arte -> quantas vezes chegou corrompida
        self.refazer: list = [] # chaves a remandar
        self.enviadas: set = set()
        self.fila: list = []    # artes por mandar, uma pagina de cada vez
        self.pendente = None    # (indice do pedaco, hora do envio, tentativas)
        self.precarregado: set = set()
        self.adiados: list = [] # eventos segurados ate o pedaco em voo confirmar
        self.recados: list = []
        self.recados_lock = threading.Lock()
        # Cards vivos: a versao de cada arte que a PLACA tem agora. Quando a
        # pagina diz outra versao, a arte nova vai no lugar (i=0 direto) e a
        # placa redesenha so aquele card.
        self.versao_placa: dict = {}
        self.artes_vistas: tuple = ()   # ids de arte do layout que esta na tela
        self.proximo_vivos = 0.0
        # Degrau de volume (0, 5, ... 100) que o card SOM esta mostrando, e o
        # que ele deveria mostrar. Os dois divergem por ate 400 ms de proposito.
        self.nivel_visto = -1
        self.nivel_alvo = -1
        self.nivel_quando = 0.0
        self.estado_enviado_em = 0.0    # heartbeat: a barra da placa diz "offline" apos 6 s calada
        self.barra_vista = None         # texto que a barra do topo esta mostrando
        self.descanso_auto = False      # entrou na tela de descanso por ociosidade, nao por toque
        self.pagina_antes = "home"
        self.proximo_ocioso = 0.0
        self.proximo_foco = 0.0
        self.pagina_por_foco = None     # pagina que o painel abriu sozinho por causa da janela em foco
        self.foco_hwnd = None           # ultima janela que bateu com um quando_foco
        self.foco_visto_em = 0.0        # quando ela bateu pela ultima vez
        self.foco_saiu_em = 0.0         # quando a janela do perfil deixou de estar na frente

    # ------------------------------------------------------------- envio

    def _escreve(self, obj: dict) -> None:
        self.ser.write((json.dumps(obj, ensure_ascii=True) + "\n").encode())

    def envia(self, obj: dict) -> None:
        """Manda um evento que NAO e pedaco de arte (layout, state, err).

        Se ha um pedaco de arte em voo, espera ele ser confirmado. A placa nao
        le a UART enquanto decodifica um JPEG (o firmware telinha_p4 confirma o
        ultimo pedaco so DEPOIS de desenhar, por isso mesmo); um layout de
        1,5 KB ou um `state` cuspido nesse intervalo e o que fazia a arte
        chegar com o cabecalho mastigado - "jpeg invalido" com o tamanho
        certo. Adiar custa no maximo um pedaco (~80 ms).
        """
        if self.pendente is not None:
            self.adiados.append(obj)
            return
        self._escreve(obj)

    def _despacha_adiados(self) -> None:
        if self.adiados and self.pendente is None:
            pendentes, self.adiados = self.adiados, []
            for obj in pendentes:
                self._escreve(obj)

    def recado(self, obj: dict) -> None:
        """Chamavel de outra thread: enfileira; quem escreve na serial e o loop."""
        with self.recados_lock:
            self.recados.append(obj)

    def envia_pagina(self, pid: str) -> bool:
        pag = self.painel.pagina(pid)
        if not pag:
            print(f"[erro] pagina desconhecida: {pid}")
            return False
        # Brilho: a tela de descanso baixa o backlight (firmware redea-1.1+;
        # os antigos ignoram o evento). Ao sair dela, volta ao de trabalho.
        c = self.painel.cfg.get("descanso") or {}
        if pid == "descanso":
            self.envia({"ev": "brilho", "v": int(c.get("brilho", 40))})
        elif self.pagina_atual == "descanso":
            self.envia({"ev": "brilho", "v": int(self.painel.cfg.get("brilho", 200))})
        self.envia(pag)
        self.pagina_atual = pid
        self.artes_vistas = tuple(b["art"] for b in pag["buttons"])
        print(f"[pagina] {pid}: {len(pag['buttons'])} botoes")
        # A pagina que o usuario esta vendo passa na frente do precarregamento.
        # Quem sai da fila volta a contar como pendente: sem isso a pagina ficava
        # marcada como precarregada e as artes descartadas nunca mais eram
        # mandadas - a precarga travava no meio a cada navegacao.
        # O pedaco em voo (fila[0] com pendente) fica: abortar no meio mandava
        # o mesmo pedaco duas vezes e deixava a placa com um JPEG pela metade.
        em_voo = self.fila[0] if (self.fila and self.pendente is not None) else None
        for t in self.fila:
            if not t["prio"] and t is not em_voo:
                self.precarregado.discard(t.get("pid", ""))
        self.fila = [t for t in self.fila if t["prio"] or t is em_voo]
        self.enfileira(pid, prio=True)
        # A placa zera o "aceso" de todos os botoes ao receber um layout. Sem
        # esquecer o ultimo estado aqui, o proximo tick achava que nada mudou e
        # o mic mudo nascia apagado na pagina nova por ate 4 s.
        self.ultimo_estado = {}
        self.proximo_estado = 0.0
        return True

    def enfileira(self, pid: str, prio: bool, so: set | None = None) -> int:
        """Poe na fila as artes da pagina que a placa ainda nao tem.

        Arte fixa: comeca pela sondagem (i=-1), e a placa diz se ja tem.
        Card vivo com versao diferente da que a placa tem: vai com i=0 direto,
        SEM sondagem - a sondagem compara id+tamanho, e duas versoes do relogio
        com o mesmo tamanho de JPEG fariam a placa dizer "ja tenho" e ficar
        com a hora velha. `so` restringe a um conjunto de ids (os que mudaram).
        """
        novas = 0
        for chave, w, h, dados, versao in self.painel.artes_da_pagina(pid):
            if so is not None and chave not in so:
                continue
            if any(t["chave"] == chave for t in self.fila):
                continue
            substituir = versao is not None and self.versao_placa.get(chave) != versao
            if not substituir and chave in self.enviadas:
                continue
            b64 = base64.b64encode(dados).decode("ascii")
            partes = [b64[i:i + CHUNK_B64] for i in range(0, len(b64), CHUNK_B64)]
            self.fila.append({"chave": chave, "w": w, "h": h, "len": len(dados),
                              "partes": partes, "i": 0 if substituir else -1,
                              "prio": prio, "pid": pid, "versao": versao})
            novas += 1
        if novas:
            print(f"[arte] {pid}: {novas} imagens na fila"
                  + ("" if prio else " (precarregando)"))
        return novas

    def bombeia_fila(self) -> None:
        """Manda UM pedaco por passagem.

        E o que mantem o toque respondendo enquanto a arte carrega: o painel nunca
        fica parado esperando bitmap, e a pagina aparece preenchendo aos poucos.
        """
        self._despacha_adiados()

        if not self.fila and self.refazer:
            chave = self.refazer.pop(0)
            for pid in self.painel.paginas_conhecidas():
                if any(c == chave for c, *_ in self.painel.artes_da_pagina(pid)):
                    self.enfileira(pid, prio=True, so={chave})
                    return
            return

        if not self.fila:
            # Fila vazia: adianta as outras paginas. Com tudo precarregado a
            # navegacao e instantanea - o conjunto inteiro cabe folgado na PSRAM.
            if not self.pagina_atual:
                return
            for pid in self.painel.paginas_conhecidas():
                if pid not in self.precarregado:
                    self.precarregado.add(pid)
                    if self.enfileira(pid, prio=False):
                        return
            return
        t = self.fila[0]

        if self.pendente is not None:
            i, quando, tentativas = self.pendente
            if self.imgok >= i:
                self.pendente = None
                if i == -1 and self.img_tem:
                    # a placa ja tem esta arte, com o mesmo tamanho: nao remandar
                    self.enviadas.add(t["chave"])
                    self.fila.pop(0)
                    return
                t["i"] = i + 1
                if t["i"] >= len(t["partes"]):
                    self.fila.pop(0)
                    if t.get("falhou"):
                        # a placa mandou imgbad E DEPOIS o imgok deste pedaco
                        # (firmware telinha_p4): a transferencia acabou, mas a arte
                        # nao existe la. Marcar como entregue aqui era o que
                        # fazia o reenvio agendado ser pulado como "ja tem".
                        return
                    self.enviadas.add(t["chave"])
                    if t.get("versao") is not None:
                        self.versao_placa[t["chave"]] = t["versao"]
                    print(f"[arte] {t['chave']}: {t['len']} bytes em "
                          f"{len(t['partes'])} partes")
                return
            if time.monotonic() - quando < 1.2:
                return
            if tentativas < 1:                      # uma segunda chance
                self.pendente = (i, time.monotonic(), tentativas + 1)
                self.envia_parte(t, i)
                return
            print(f"[arte] {t['chave']}: pedaco {i} sem confirmacao, desistindo")
            self.fila.pop(0)
            self.pendente = None
            return

        self.imgok = -2
        self.envia_parte(t, t["i"])
        self.pendente = (t["i"], time.monotonic(), 0)

    def envia_parte(self, t: dict, i: int) -> None:
        # "off" e o deslocamento em bytes DECODIFICADOS deste pedaco. Vai
        # explicito para o reenvio ser idempotente: quando uma confirmacao se
        # perdia e o pedaco era mandado de novo, a placa somava o mesmo trecho
        # duas vezes e o JPEG chegava corrompido.
        if i < 0:
            # sondagem: so os metadados. A placa responde se ja tem esta arte,
            # o que evita remandar 1,3 MB toda vez que o agente reinicia.
            self._escreve({"ev": "img", "id": t["chave"], "w": t["w"], "h": t["h"],
                        "len": t["len"], "i": -1, "n": len(t["partes"])})
            return
        self._escreve({"ev": "img", "id": t["chave"], "w": t["w"], "h": t["h"],
                    "len": t["len"], "off": i * (CHUNK_B64 * 3 // 4),
                    "i": i, "n": len(t["partes"]), "d": t["partes"][i]})

    # ------------------------------------------------------------ recepcao

    def bombeia(self) -> None:
        """Le o que houver na serial e trata cada linha completa.

        Usa in_waiting em vez de read(n) as cegas: read() bloqueia ate o timeout,
        e com centenas de confirmacoes de arte isso somava dezenas de segundos de
        espera pura. Aqui nunca se espera por dado que nao chegou.
        """
        n = self.ser.in_waiting
        if n:
            self.buf += self.ser.read(n)
        while b"\n" in self.buf:
            linha, self.buf = self.buf.split(b"\n", 1)
            txt = linha.decode("utf-8", "replace").strip()
            if not txt:
                continue
            if txt[0] != "{":
                # o log do ROM sai a 115200 e chega como lixo aqui: nao poluir
                legivel = sum(32 <= ord(c) < 127 for c in txt)
                if legivel > len(txt) * 0.8:
                    print(f"[placa] {txt}")
                continue
            try:
                self.trata(json.loads(txt))
            except json.JSONDecodeError:
                pass

    def trata(self, msg: dict) -> None:
        cmd = msg.get("cmd")

        if cmd == "imgbad":
            # A arte chegou corrompida (caractere trocado na serial). Manda de
            # novo em vez de deixar um botao cinza na tela para sempre.
            chave = msg.get("id", "")
            n = self.ruins.get(chave, 0) + 1
            self.ruins[chave] = n
            self.enviadas.discard(chave)
            self.versao_placa.pop(chave, None)
            if self.fila and self.fila[0]["chave"] == chave:
                self.fila[0]["falhou"] = True
            if n <= 3:
                print(f"[arte] {chave}: chegou corrompida, remandando ({n}/3)")
                self.refazer.append(chave)
            else:
                print(f"[arte] {chave}: corrompeu {n} vezes, desistindo")
            return

        if cmd == "imgok":
            self.imgok = msg.get("i", -1)
            self.img_tem = bool(msg.get("tem", False))
            return

        if cmd == "hello":
            print(f"[hello] fw={msg.get('fw', '?')}")
            pag = msg.get("page", "")
            if pag and self.painel.pagina(pag):
                # A placa ja esta desenhada: retoma na pagina dela. O layout vai
                # mesmo assim, ANTES de qualquer arte (nada em voo aqui, entao
                # nao se mistura com pedaco): se o config mudou desde a ultima
                # vez, a placa estaria com botoes em posicoes velhas para
                # sempre. O firmware telinha_p4 nao redesenha layout igual, entao
                # no caso comum nao pisca.
                self.envia_pagina(pag)
                return
            # a placa reiniciou: perdeu os sprites, refaz tudo
            self.enviadas.clear()
            self.versao_placa.clear()
            self.fila.clear()
            self.pendente = None
            self.precarregado.clear()
            try:
                self.painel.cfg = carregar_config()
            except Exception as e:
                # config salvo pela metade num editor derrubava o processo:
                # JSONDecodeError e ValueError, e o main() so pega SerialException
                print(f"[erro] config.json: {e} - mantendo o anterior")
            self.envia_pagina("home")

        elif cmd == "page":
            # botao voltar da placa: navegacao na mao. O perfil por foco solta
            # a pagina e so volta a agir quando OUTRA janela vier para a frente.
            self.pagina_por_foco = None
            self.envia_pagina(msg.get("id", "home"))

        elif cmd == "state":
            self.proximo_estado = 0.0

        elif cmd == "btn":
            self.toque(msg.get("page", self.pagina_atual), msg.get("id", ""))

    def toque(self, pid: str, bid: str) -> None:
        acao = self.painel.acao(pid, bid)
        if acao is None:
            self.envia({"ev": "err", "id": bid, "msg": "sem mapeamento"})
            print(f"[erro] {pid}/{bid}: sem mapeamento")
            return
        try:
            destino = self.exec.executar(acao)
            self.envia({"ev": "ack", "id": bid, "ok": True})
            print(f"[btn] {pid}/{bid} -> {acao.get('type')}")
            # A acao mudou o estado do PC. Sem isto, mutar o mic sem navegar
            # esperava o tick inteiro para o botao acender: 296 ms na mediana,
            # ate 930 ms, no botao mais apertado do painel. Ler custa 0,14 ms.
            self.proximo_estado = 0.0
            if destino:
                self.descanso_auto = False
                self.pagina_por_foco = None
                self.envia_pagina(destino)
        except Exception as e:
            self.envia({"ev": "err", "id": bid, "msg": str(e)[:60]})
            print(f"[erro] {pid}/{bid}: {e}")

    def atualiza_nivel(self, estado: dict, agora: float) -> None:
        """O volume mudou de degrau: o card SOM ganha arte nova.

        O nivel entra no id da arte em degraus de 5 (`sysmute:nivel:60`), entao
        cada degrau e um sprite fixo - no maximo 21. Debounce de 400 ms porque o
        volume anda em rajadas: cinco toques em Vol+ viram UM card novo, nao
        cinco. Segue o mesmo caminho do card de musica: layout remandado so na
        pagina que tem o card.
        """
        v = estado.get("sys_vol")
        if v is None:
            return
        degrau = int(round(v / 5.0) * 5)
        if degrau != self.nivel_alvo:
            self.nivel_alvo = degrau
            self.nivel_quando = agora + 0.4
        if self.nivel_alvo == self.nivel_visto or agora < self.nivel_quando:
            return
        self.nivel_visto = self.nivel_alvo
        # daqui em diante e o verifica_vivos() que percebe a versao nova
        self.painel.niveis["sys_vol"] = v

    def verifica_vivos(self, agora: float) -> None:
        """Compara a pagina de agora com o que a placa mostra e corrige.

        Duas coisas podem ter mudado. Um card vivo mudou de versao (bateu o
        minuto, trocou a musica, o volume andou): so aquela arte vai, com i=0,
        e a placa redesenha so o card. Ou a pagina mudou de IDS de arte (a
        idade de um projeto virou "ha 1 h"): ai e layout novo mesmo.

        A cada 250 ms numa pagina com cards vivos; a cada 2 s nas outras -
        montar a pagina `dev` custa uns 300 stat() e nao precisa ser feito
        duzentas vezes por segundo.
        """
        if agora < self.proximo_vivos or not self.pagina_atual:
            return
        pag = self.painel.pagina(self.pagina_atual)
        if not pag:
            return
        vivos_ = pag.get("_vivos", {})
        self.proximo_vivos = agora + (0.25 if vivos_ else 2.0)

        ids = tuple(b["art"] for b in pag["buttons"])
        if ids != self.artes_vistas:
            self.envia_pagina(self.pagina_atual)
            return
        mudou = {a for a, v in vivos_.items() if self.versao_placa.get(a) != v}
        if mudou:
            self.enfileira(self.pagina_atual, prio=True, so=mudou)

    def atualiza_barra(self) -> None:
        """A hora (e a proxima reuniao de hoje) como TEXTO na barra do topo.

        90 bytes por minuto, sem JPEG: nao tem como chegar corrompido nem
        piscar - foi o que tirou o relogio da grade. O firmware antigo
        (joquei-0.4) ignora `barra`; o telinha_p4 (ex-redea_p4) desenha.
        """
        if not self.painel.cfg.get("barra_relogio", True):
            return
        txt = self.painel.texto_barra()
        if txt != self.barra_vista:
            self.barra_vista = txt
            self.envia({"ev": "barra", "txt": txt})

    def vigia_ocioso(self, agora: float) -> None:
        """Sem teclado/mouse por `descanso.apos_min`: vai para a tela de
        descanso sozinho; mexeu no PC: volta para onde estava. So o descanso
        automatico volta sozinho - quem tocou em Descansar quer que fique."""
        if agora < self.proximo_ocioso or not self.pagina_atual:
            return
        self.proximo_ocioso = agora + 2.0
        c = self.painel.cfg.get("descanso") or {}
        apos = float(c.get("apos_min", 0) or 0) * 60
        if apos <= 0 or not self.painel.pagina("descanso"):
            return
        ocioso = ociosidade_s()
        if self.pagina_atual != "descanso":
            if ocioso >= apos:
                self.pagina_antes = self.pagina_atual
                self.descanso_auto = True
                print(f"[descanso] PC parado ha {ocioso / 60:.0f} min")
                self.envia_pagina("descanso")
        elif self.descanso_auto and ocioso < 2.0:
            self.descanso_auto = False
            print("[descanso] voltou a mexer no PC")
            self.envia_pagina(self.pagina_antes or "home")

    def vigia_foco(self, agora: float) -> None:
        """Perfil por janela em foco: a feature que todo deck tem.

        Paginas do config com `quando_foco` (lista de exes ou de regras com
        titulo) abrem sozinhas quando aquela janela VEM para a frente e fecham
        (volta para a home) quando ela sai. Na tela de descanso nao mexe.

        Age na BORDA, nao no estado. Antes havia uma trava de 30 s depois de
        qualquer navegacao na mao, e o caminho mais comum de abrir o Claude -
        home > dev > toque no projeto - caia justo dentro dela: o terminal novo
        vinha para a frente e o painel ficava na home por meio minuto. Agora a
        navegacao na mao so vale para a janela que esta na frente; outra janela
        do Claude (sessao nova, alt-tab entre duas) abre a pagina na hora.
        """
        if agora < self.proximo_foco or not self.pagina_atual or self.pagina_atual == "descanso":
            return
        self.proximo_foco = agora + 0.3
        import janelas
        hwnd, exe, titulo = janelas.janela_da_frente()
        alvo = None
        for pid, pag in self.painel.cfg.get("pages", {}).items():
            regras = pag.get("quando_foco") or []
            if any(janelas.regra_bate(r, exe, titulo) for r in regras):
                alvo = pid
                break
        if alvo:
            # Janela nova, ou a mesma voltando depois de um tempo fora. Um
            # quadro sem o simbolo de estado no titulo (o spinner do Claude
            # troca de glifo) nao conta como "voltou": 2 s de tolerancia.
            veio = hwnd != self.foco_hwnd or agora - self.foco_visto_em > 2.0
            self.foco_hwnd, self.foco_visto_em = hwnd, agora
            self.foco_saiu_em = 0.0
            if veio and alvo != self.pagina_atual:
                print(f"[foco] {alvo} veio para a frente")
                self.pagina_por_foco = alvo
                self.envia_pagina(alvo)
            elif veio:
                self.pagina_por_foco = alvo
        elif self.pagina_por_foco and self.pagina_atual == self.pagina_por_foco:
            # Saiu. Espera antes de voltar: um clique na barra de tarefas nao
            # pode piscar a home. Se a frente e o MESMO programa com outro
            # titulo (o terminal de uma sessao que ainda esta subindo - o
            # Claude leva uns segundos para por o simbolo no titulo -, ou uma
            # aba de pwsh ao lado), espera mais: era isso que fazia a pagina
            # ir para a home e voltar ao abrir a segunda sessao.
            regras = (self.painel.cfg.get("pages", {}).get(self.pagina_por_foco) or {}).get("quando_foco") or []
            mesmo_exe = any((r if isinstance(r, str) else str(r.get("exe", ""))).lower() == exe
                            for r in regras)
            espera = 6.0 if mesmo_exe else 1.5
            if not self.foco_saiu_em:
                self.foco_saiu_em = agora
            elif agora - self.foco_saiu_em >= espera:
                print("[foco] saiu; voltando para a home")
                self.pagina_por_foco = None
                self.foco_saiu_em = 0.0
                self.envia_pagina("home")

    def ve_comando(self, agora: float) -> None:
        """comando.txt da bandeja. "dormir": apaga a tela da placa e encerra.

        A ordem vai DEPOIS de qualquer pedaco em voo (linhas sao atomicas, entao
        basta escrever) e e a ultima coisa que sai: o firmware acorda com
        qualquer mensagem seguinte, e a seguinte sera o "quem" do agente que a
        bandeja subir de novo.
        """
        if agora < getattr(self, "proximo_comando", 0.0):
            return
        self.proximo_comando = agora + 0.5
        if not COMANDO_PATH.exists():
            return
        try:
            cmd = COMANDO_PATH.read_text(encoding="utf-8").strip().lower()
            COMANDO_PATH.unlink()
        except OSError:
            return
        if cmd == "dormir":
            print("[sono] apagando a tela e encerrando")
            self._escreve({"ev": "dormir"})
            try:
                self.ser.flush()
            except Exception:
                pass
            raise Desligar()
        if cmd == "acordar":
            self._escreve({"ev": "acordar"})

    # --------------------------------------------------------------- loop

    def roda(self, intervalo: float) -> None:
        while True:
            self.bombeia()
            self.bombeia_fila()

            if self.recados:
                with self.recados_lock:
                    pendentes, self.recados = self.recados, []
                for obj in pendentes:
                    self.envia(obj)

            agora = time.monotonic()

            # Cards vivos (relogio, clima, musica, SOM, foco): arte nova no lugar
            self.verifica_vivos(agora)
            self.ve_comando(agora)
            self.vigia_foco(agora)

            aviso = self.painel.foco.aviso()
            if aviso:
                # `err` e o unico toast que o firmware tem: 4 s de texto na barra
                self.envia({"ev": "err", "id": "foco", "msg": aviso[:35]})
                print(f"[foco] {aviso}")

            if agora >= self.proximo_estado:
                estado = audio_state()
                # estados do Spotify entram no mesmo `state`: os botoes com
                # state_key sp_* acendem sozinhos (curtida, aleatorio, repetir)
                m = self.painel.musica.estado
                estado["sp_curtida"] = bool(m.get("sp_curtida"))
                estado["sp_aleatorio"] = bool(m.get("sp_aleatorio"))
                estado["sp_repetir"] = m.get("sp_repetir", "off") not in ("off", None)
                if self.painel.obs:
                    estado.update(self.painel.obs.estado())
                # Manda tambem quando nada mudou, a cada 4 s: e o heartbeat. O
                # firmware telinha_p4 escreve "agente offline" na barra depois de
                # 6 s sem mensagem - era o que fazia o painel parecer desligado
                # e "conectar" so quando se tocava nele.
                if estado != self.ultimo_estado or agora - self.estado_enviado_em >= 4.0:
                    self.envia({"ev": "state", **estado})
                    self.ultimo_estado = estado
                    self.estado_enviado_em = agora
                self.proximo_estado = agora + intervalo
                grava_estado(conectado=True, porta=self.ser.port, pagina=self.pagina_atual)
                self.atualiza_barra()
                self.vigia_ocioso(agora)

            self.atualiza_nivel(self.ultimo_estado, agora)

            # Sem trabalho: BLOQUEIA no read em vez de girar em vazio.
            # O loop rodava a 6300 voltas/s e queimava um core inteiro da
            # maquina. Nao usar sleep: o timer do Windows tem
            # granularidade de ~15 ms e ia CRIAR latencia de toque. O read com
            # timeout dorme no driver e acorda no primeiro byte que a placa
            # mandar, entao o dedo nao espera nada.
            if not self.fila and not self.ser.in_waiting:
                self.buf += self.ser.read(1)



def modo_teste(cfg: dict, painel, ids: list) -> int:
    if HAVE_PYCAW:
        CoInitialize()
    if not ids:
        print("Pacotes:")
        for r in cfg.get("_pacotes", []):
            marca = "ATIVO" if r["ativo"] else ("instalado, desligado" if r["instalado"] else "nao encontrado")
            print(f"  {r['id']:12s} {r['nome']:22s} {marca}")
        print("\nPaginas e botoes:")
        for pid in painel.paginas_conhecidas():
            pag = painel.pagina(pid)
            if not pag:
                continue
            g = pag["grid"]
            w, h = painel.tamanho_botao(g["cols"], g["rows"])
            print(f"\n  [{pid}] {pag['title'] or '(home)'} - grade {g['cols']}x{g['rows']}, "
                  f"cards {w}x{h}")
            for b in pag["buttons"]:
                acao = painel.acao(pid, b["id"]) or {}
                jpeg = painel.arte(b["art"], w, h, pid)
                tam = f"{len(jpeg) // 1024} KB" if jpeg else "SEM ARTE"
                print(f"    {b['id']:18s} {acao.get('type', '?'):18s} {tam:9s} "
                      f"{b['art']}" + (f"  (+{b['art_on']})" if b.get("art_on") else ""))
        print("\nEstado de audio:", json.dumps(audio_state()))
        return 0

    ex = Executor(painel)
    for spec in ids:
        pid, _, bid = spec.rpartition("/") if "/" in spec else ("home", "", spec)
        acao = painel.acao(pid, bid)
        if acao is None:
            print(f"[erro] {pid}/{bid}: sem mapeamento")
            continue
        try:
            destino = ex.executar(acao)
            print(f"[ok] {pid}/{bid} -> {acao.get('type')}"
                  + (f", vai para {destino}" if destino else ""))
        except Exception as e:
            print(f"[erro] {pid}/{bid}: {e}")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if HAVE_PYCAW:
        CoInitialize()
    else:
        print("[aviso] pycaw ausente: mute de microfone desativado", file=sys.stderr)

    cfg = carregar_config()
    from paginas import Painel
    painel = Painel(cfg)
    painel.musica.liga_spotify(cfg.get("spotify"))
    # O card SOM nasce ja com o nivel certo: sem isto a primeira home ia sem a
    # barra de gomos e era remandada um segundo depois.
    painel.niveis["sys_vol"] = audio_state().get("sys_vol")

    argv = sys.argv[1:]
    if argv and argv[0] in ("--test", "-t", "--list", "-l"):
        return modo_teste(cfg, painel, argv[1:])

    # Renderiza a arte de todas as paginas numa thread, ja durante o arranque.
    # Sem isto os ~70 ms por card viravam quase um segundo de espera no momento
    # do toque. Na segunda execucao vem do cache em disco e leva milissegundos.
    def aquecer():
        t0 = time.monotonic()
        try:
            painel.pre_gerar()
            print(f"[arte] todas as paginas prontas em {time.monotonic() - t0:.1f}s")
        except Exception as e:
            print(f"[arte] precarregamento parou: {e}")

    threading.Thread(target=aquecer, daemon=True, name="arte").start()

    intervalo = cfg.get("state_interval_ms", 1000) / 1000.0
    baud = cfg.get("baud", 921600)

    while True:
        porta = achar_porta(cfg.get("port", "auto"), baud)
        if not porta:
            grava_estado(conectado=False, porta="", pagina="")
            if not getattr(main, "avisou_sem_placa", False):
                print("[...] nenhuma porta responde como a placa, tentando de novo")
                main.avisou_sem_placa = True
            time.sleep(2)
            continue
        try:
            ser = serial.Serial(porta, baud, timeout=0.005)
        except serial.SerialException as e:
            print(f"[erro] {porta}: {e}")
            time.sleep(2)
            continue

        print(f"[ok] conectado em {porta} @ {baud}")
        main.avisou_sem_placa = False
        try:
            lig = Ligacao(ser, painel)
            # A placa so manda hello quando NAO tem pagina. Se o agente reinicia
            # com a placa ja desenhada, ela ficaria calada e o precarregamento
            # nunca retomaria - entao aqui e o PC que pergunta.
            lig.envia({"ev": "quem"})
            lig.roda(intervalo)
        except Desligar:
            grava_estado(conectado=False, porta="", pagina="", dormindo=True)
            print("[sono] agente encerrado a pedido da bandeja")
            return 0
        except (serial.SerialException, OSError) as e:
            grava_estado(conectado=False, porta="", pagina="")
            print(f"[desconectado] {e}")
        except KeyboardInterrupt:
            print("\n[saindo]")
            return 0
        finally:
            try:
                ser.close()
            except Exception:
                pass
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
