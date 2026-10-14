"""
A conversa com a placa pela serial. Portada do agente antigo (telinha_agent.py),
onde cada detalhe abaixo custou uma depuracao - os comentarios dizem qual.

Protocolo, uma linha JSON por mensagem:

    placa -> PC   {"cmd":"hello","fw":"...","page":""}   {"cmd":"page","id":...}
                  {"cmd":"btn","page":...,"id":...}       {"cmd":"state"}
                  {"cmd":"imgok","i":k,"tem":bool}        {"cmd":"imgbad","id":...}
    PC -> placa   {"ev":"layout",...}  {"ev":"img",...}  {"ev":"state",...}
                  {"ev":"barra","txt"} {"ev":"brilho","v"} {"ev":"dormir"|"acordar"}
                  {"ev":"ack"|"err","id",...}  {"ev":"quem"}

Esta thread e DONA da porta e nao chama codigo de modulo: acao vai para o
pool do roteador, arte vem pronta do compositor (com prazo), estado vem do
coletor. Outras threads falam com ela por `recado()`.
"""

from __future__ import annotations

import base64
import json
import threading
import time

from serial.tools import list_ports

# base64 por linha: com 9000 aparecem caracteres corrompidos de vez em quando;
# com 4000, nao. O retry por "imgbad" cobre o resto.
CHUNK_B64 = 4000
KNOWN_USB_IDS = [(0x1A86, 0x55D3), (0x303A, None)]   # CH343 da placa, USB nativa


class Desligar(Exception):
    pass


def e_a_placa(porta: str, baud: int, espera: float = 1.5) -> bool:
    """Pergunta "quem" e espera um hello. A CH343 nao e so da placa (a bancada
    LoRa usa a mesma ponte). DTR/RTS baixos para nao resetar ninguem."""
    import serial
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
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def achar_porta(preferida: str, baud: int):
    if preferida and preferida != "auto":
        return preferida
    for p in list_ports.comports():
        if any(p.vid == vid and (pid is None or p.pid == pid) for vid, pid in KNOWN_USB_IDS):
            if e_a_placa(p.device, baud):
                return p.device
    return None


class TelaVirtual:
    """Sem placa: a janela do app continua funcionando. Guarda a pagina "na
    tela", executa toques e navega - e o que a Ligacao faria, sem serial."""

    placa = False
    fw = ""

    def __init__(self, nucleo, pagina: str = ""):
        self.n = nucleo
        self.pagina_atual = pagina

    def envia(self, obj: dict) -> None:
        if obj.get("ev") == "err":
            print(f"[erro] {obj.get('id')}: {obj.get('msg')}")

    def envia_pagina(self, pid: str) -> bool:
        if not self.n.comp.pagina(pid):
            return False
        self.pagina_atual = pid
        return True

    def recado(self, obj: dict) -> None:
        if "_navegar" in obj:
            self.envia_pagina(obj["_navegar"])
        elif "_toque" in obj:
            self.n.rot.toque(*obj["_toque"])
        elif "_recarregar" in obj:
            self.n.recarregar()
        else:
            self.envia(obj)


class Ligacao:
    placa = True

    def __init__(self, ser, nucleo):
        self.ser = ser
        self.n = nucleo
        self.pagina_atual = ""
        self.fw = ""
        self.buf = b""
        self.imgok = -2          # ultimo pedaco que a placa confirmou
        self.img_tem = False     # a placa respondeu "ja tenho esta arte"
        self.ruins: dict = {}
        self.refazer: list = []
        self.enviadas: set = set()
        self.fila: list = []
        self.pendente = None     # (indice do pedaco, hora do envio, tentativas)
        self.precarregado: set = set()
        self.precarga_volta: dict = {}  # pagina -> quando tentar de novo (arte atrasada)
        self.adiados: list = []
        self.recados: list = []
        self.recados_lock = threading.Lock()
        self.versao_placa: dict = {}
        self.artes_vistas: tuple = ()
        self.proximo_vivos = 0.0
        self.ultimo_estado: dict = {}
        self.estado_enviado_em = 0.0
        self.versao_estado = -1
        self.forcar_estado = False
        self.barra_vista = None
        self.nivel_visto = self.nivel_alvo = -1
        self.nivel_quando = 0.0
        self.proximo_comando = 0.0
        self.bytes_arte = 0      # para o "serial x%" da interface

    # ------------------------------------------------------------- envio

    def _escreve(self, obj: dict) -> None:
        self.ser.write((json.dumps(obj, ensure_ascii=True) + "\n").encode())

    def envia(self, obj: dict) -> None:
        """Evento que NAO e pedaco de arte. Com um pedaco em voo, espera: a placa
        nao le a UART enquanto decodifica o JPEG, e um layout cuspido nesse
        intervalo chegava com o cabecalho mastigado. Custa no maximo ~80 ms."""
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
        """Chamavel de qualquer thread."""
        with self.recados_lock:
            self.recados.append(obj)

    def envia_pagina(self, pid: str) -> bool:
        pag = self.n.comp.pagina(pid)
        if not pag:
            print(f"[erro] pagina desconhecida: {pid}")
            return False
        # brilho por pagina (a de descanso baixa o backlight); saindo dela, volta
        brilho = pag.get("_brilho")
        if brilho:
            self.envia({"ev": "brilho", "v": int(brilho)})
        elif self.pagina_atual and (self.n.comp.pagina(self.pagina_atual) or {}).get("_brilho"):
            self.envia({"ev": "brilho", "v": int(self.n.ajuste("brilho", 200))})
        self.envia({k: v for k, v in pag.items() if not k.startswith("_")})
        self.pagina_atual = pid
        self.artes_vistas = tuple(b["art"] for b in pag["buttons"])
        print(f"[pagina] {pid}: {len(pag['buttons'])} botoes")
        # A pagina vista passa na frente da precarga. Quem sai da fila volta a
        # contar como pendente (senao a precarga travava no meio a cada
        # navegacao). O pedaco em voo fica: abortar mandava o mesmo pedaco duas
        # vezes e deixava um JPEG pela metade na placa.
        em_voo = self.fila[0] if (self.fila and self.pendente is not None) else None
        for t in self.fila:
            if not t["prio"] and t is not em_voo:
                self.precarregado.discard(t.get("pid", ""))
        self.fila = [t for t in self.fila if t["prio"] or t is em_voo]
        self.enfileira(pid, prio=True)
        # a placa zera o "aceso" ao receber layout: o estado tem de ir de novo
        self.ultimo_estado = {}
        self.forcar_estado = True
        return True

    def enfileira(self, pid: str, prio: bool, so: set | None = None) -> int:
        """Artes da pagina que a placa ainda nao tem. Fixa: sondagem primeiro
        (i=-1, a placa diz se ja tem). Viva com versao nova: i=0 direto - a
        sondagem compara id+tamanho e duas horas com o mesmo tamanho de JPEG
        deixariam o relogio parado."""
        novas = 0
        espera = 0.25 if prio else 0.0
        prontas = self.n.comp.artes_da_pagina(pid, espera)
        if not prio and so is None and len(prontas) < self.n.comp.total_artes(pid):
            # card vivo cuja versao mudou (o clima chegou da rede) ainda esta
            # desenhando: a precarga volta a esta pagina daqui a pouco
            self.precarregado.discard(pid)
            self.precarga_volta[pid] = time.monotonic() + 1.0
        for chave, w, h, dados, versao in prontas:
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
            print(f"[arte] {pid}: {novas} imagens na fila" + ("" if prio else " (precarregando)"))
        return novas

    def bombeia_fila(self) -> None:
        """UM pedaco por passagem: o toque responde enquanto a arte carrega."""
        self._despacha_adiados()

        if not self.fila and self.refazer:
            chave = self.refazer.pop(0)
            for pid in self.n.comp.paginas():
                if any(c == chave for c, *_ in self.n.comp.artes_da_pagina(pid, 0.0)):
                    self.enfileira(pid, prio=True, so={chave})
                    return
            return

        if not self.fila:
            if not self.pagina_atual:
                return
            agora = time.monotonic()
            for pid in self.n.comp.paginas():
                if pid not in self.precarregado and agora >= self.precarga_volta.get(pid, 0.0):
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
                    self.enviadas.add(t["chave"])
                    self.fila.pop(0)
                    return
                t["i"] = i + 1
                if t["i"] >= len(t["partes"]):
                    self.fila.pop(0)
                    if t.get("falhou"):
                        # imgbad e DEPOIS o imgok deste pedaco: acabou, mas a
                        # arte nao existe la; o reenvio ja esta agendado
                        return
                    self.enviadas.add(t["chave"])
                    if t.get("versao") is not None:
                        self.versao_placa[t["chave"]] = t["versao"]
                    print(f"[arte] {t['chave']}: {t['len']} bytes em {len(t['partes'])} partes")
                return
            if time.monotonic() - quando < 1.2:
                return
            if tentativas < 1:
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
        if i < 0:
            self._escreve({"ev": "img", "id": t["chave"], "w": t["w"], "h": t["h"],
                           "len": t["len"], "i": -1, "n": len(t["partes"])})
            return
        # "off" explicito: o reenvio de um pedaco e idempotente na placa
        self._escreve({"ev": "img", "id": t["chave"], "w": t["w"], "h": t["h"],
                       "len": t["len"], "off": i * (CHUNK_B64 * 3 // 4),
                       "i": i, "n": len(t["partes"]), "d": t["partes"][i]})
        self.bytes_arte += len(t["partes"][i])

    # ----------------------------------------------------------- recepcao

    def bombeia(self) -> None:
        n = self.ser.in_waiting
        if n:
            self.buf += self.ser.read(n)
        while b"\n" in self.buf:
            linha, self.buf = self.buf.split(b"\n", 1)
            txt = linha.decode("utf-8", "replace").strip()
            if not txt:
                continue
            if txt[0] != "{":
                # o log do ROM sai a 115200 e chega como lixo: nao poluir
                if sum(32 <= ord(c) < 127 for c in txt) > len(txt) * 0.8:
                    print(f"[placa] {txt}")
                continue
            try:
                self.trata(json.loads(txt))
            except json.JSONDecodeError:
                pass

    def trata(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "imgbad":
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
        elif cmd == "imgok":
            self.imgok = msg.get("i", -1)
            self.img_tem = bool(msg.get("tem", False))
        elif cmd == "hello":
            self.fw = msg.get("fw", "?")
            print(f"[hello] fw={self.fw}")
            pag = msg.get("page", "")
            if pag and self.n.comp.pagina(pag):
                # a placa ja esta desenhada: retoma nela (o layout vai mesmo
                # assim, o config pode ter mudado; layout igual nao pisca)
                self.envia_pagina(pag)
                return
            # a placa reiniciou: perdeu os sprites. Perfil relido do disco.
            self.enviadas.clear()
            self.versao_placa.clear()
            self.fila.clear()
            self.pendente = None
            self.precarregado.clear()
            self.n.recarregar()
            self.envia_pagina(self.n.inicio())
        elif cmd == "page":
            self.n.rot.navegou_na_mao()
            self.envia_pagina(msg.get("id") or self.n.inicio())
        elif cmd == "state":
            self.forcar_estado = True
        elif cmd == "btn":
            self.n.rot.toque(msg.get("page", self.pagina_atual), msg.get("id", ""))

    # ------------------------------------------------------- vivos e estado

    def verifica_vivos(self, agora: float) -> None:
        """Compara a pagina de agora com o que a placa mostra e corrige: card
        vivo com versao nova vai no lugar; ids diferentes = layout novo; arte
        que ainda nao foi (desenho atrasado, imgbad) entra na fila."""
        if agora < self.proximo_vivos or not self.pagina_atual:
            return
        pag = self.n.comp.pagina(self.pagina_atual)
        if not pag:
            return
        vivos = pag.get("_vivos", {})
        self.proximo_vivos = agora + (0.25 if vivos else 2.0)
        ids = tuple(b["art"] for b in pag["buttons"])
        if ids != self.artes_vistas:
            self.envia_pagina(self.pagina_atual)
            return
        mudou = {a for a, v in vivos.items() if self.versao_placa.get(a) != v}
        na_fila = {t["chave"] for t in self.fila}
        faltam = {c for b in pag["buttons"] for c in (b["art"], b["art_on"])
                  if c and c not in vivos and c not in self.enviadas and c not in na_fila}
        if mudou or faltam:
            self.enfileira(self.pagina_atual, prio=True, so=(mudou | faltam))

    def atualiza_nivel(self, estado: dict, agora: float) -> None:
        """Volume em degraus de 5 com 400 ms de debounce: cinco toques em Vol+
        viram UM card novo."""
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
        self.n.comp.niveis["sys_vol"] = v

    def manda_estado(self, agora: float) -> None:
        versao, estado = self.n.coletor.ultimo()
        if versao == self.versao_estado and not self.forcar_estado \
                and agora - self.estado_enviado_em < 4.0:
            return
        self.versao_estado = versao
        # heartbeat a cada 4 s: a placa diz "agente offline" depois de 6 s calada
        if estado != self.ultimo_estado or self.forcar_estado or agora - self.estado_enviado_em >= 4.0:
            self.envia({"ev": "state", **estado})
            self.ultimo_estado = estado
            self.estado_enviado_em = agora
        self.forcar_estado = False
        self.atualiza_nivel(estado, agora)

    def atualiza_barra(self) -> None:
        if not self.n.ajuste("barra_relogio", True):
            return
        txt = self.n.comp.texto_barra()
        if txt != self.barra_vista:
            self.barra_vista = txt
            self.envia({"ev": "barra", "txt": txt})

    def ve_comando(self, agora: float) -> None:
        """comando.txt da bandeja: "dormir" apaga a tela e encerra."""
        if agora < self.proximo_comando:
            return
        self.proximo_comando = agora + 0.5
        cmd = self.n.le_comando()
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

    # -------------------------------------------------------------- loop

    def roda(self) -> None:
        proxima_barra = 0.0
        while True:
            self.bombeia()
            self.bombeia_fila()
            if self.recados:
                with self.recados_lock:
                    pendentes, self.recados = self.recados, []
                for obj in pendentes:
                    if "_navegar" in obj:
                        self.envia_pagina(obj["_navegar"])
                    elif "_toque" in obj:           # toque vindo da janela do app
                        self.n.rot.toque(*obj["_toque"])
                    elif "_recarregar" in obj:      # perfil salvo pela janela
                        self.n.recarregar()
                        self.envia_pagina(self.pagina_atual or self.n.inicio())
                    else:
                        self.envia(obj)
            agora = time.monotonic()
            self.verifica_vivos(agora)
            self.ve_comando(agora)
            self.n.rot.vigia(agora)
            self.manda_estado(agora)
            if agora >= proxima_barra:
                proxima_barra = agora + 1.0
                self.atualiza_barra()
                self.n.grava_estado(conectado=True, porta=self.ser.port,
                                    pagina=self.pagina_atual, fw=self.fw)
            # Sem trabalho: BLOQUEIA no read (timeout de 5 ms) em vez de girar
            # em vazio - o loop chegou a 6300 voltas/s e queimava um core. Nada
            # de sleep: o timer do Windows tem ~15 ms e criaria latencia de toque.
            if not self.fila and not self.ser.in_waiting and not self.recados:
                self.buf += self.ser.read(1)
