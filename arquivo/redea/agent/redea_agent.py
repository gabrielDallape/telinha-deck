"""
REDEA - agente Windows para o painel de sessoes do Claude Code na ESP32-P4.

A placa desenha; este processo observa e executa. A tela pede uma pagina por id,
manda o id do card tocado, e recebe de volta o ESTADO real das sessoes - quem
esta trabalhando, quem parou e esta esperando voce.

O transporte e o mesmo do JOQUEI, de proposito: uma linha JSON por mensagem,
arte em JPEG por pedacos com confirmacao, 921600 baud. Ele ja foi medido e
apanhado o bastante para nao valer reescrever.

    placa -> PC   {"cmd":"hello","fw":"...","page":"..."}
                  {"cmd":"page","id":"ses/10164"}
                  {"cmd":"btn","page":"ses/10164","id":"seguir"}
                  {"cmd":"imgok","i":k,"tem":bool}
                  {"cmd":"imgbad","id":"..."}

    PC -> placa   {"ev":"layout","page":...,"grid":...,"buttons":[...]}
                  {"ev":"img","id":...,"i":k,"n":N,"off":bytes,"d":"<b64>"}
                  {"ev":"state","b0":true,"b1":false}
                  {"ev":"barra","txt":"2 sessoes  1 trabalhando"}
                  {"ev":"aviso","msg":"joquei terminou"}
                  {"ev":"quem"}
                  {"ev":"ack"|"err","id":...}
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import serial
from serial.tools import list_ports

import janelas
import remendo
import sessoes
import som

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.json"

KNOWN_USB_IDS = [
    (0x1A86, 0x55D3),   # WCH CH343, a ponte UART da placa
    (0x303A, None),     # Espressif, USB nativa
]

# Medido no JOQUEI, nesta mesma placa: com 9000 aparecem caracteres corrompidos
# de vez em quando; com 4000, nao. O retry por "imgbad" cobre o resto.
CHUNK_B64 = 4000


def carregar_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def achar_porta(preferida: str):
    if preferida and preferida != "auto":
        return preferida
    for p in list_ports.comports():
        for vid, pid in KNOWN_USB_IDS:
            if p.vid == vid and (pid is None or p.pid == pid):
                return p.device
    outras = [p.device for p in list_ports.comports() if p.device != "COM1"]
    return outras[0] if outras else None


# -------------------------------------------------------------- despachante

class Executor:
    """Executa o toque. Devolve o id de uma pagina quando o toque navega.

    Tudo que mexe em janela roda numa THREAD. Focar, girar ate a aba certa e
    digitar leva de 300 ms a 1 s, e o loop serial nao pode ficar parado nesse
    tempo: a arte pararia de fluir e o toque seguinte nao seria lido. O que der
    errado volta como aviso na barra.
    """

    TEXTOS = {"seguir": "continua", "aprovar": "", "parar": "", "focar": ""}

    def __init__(self, painel, ligacao=None):
        self.painel = painel
        self.lig = ligacao

    def executar(self, acao: dict):
        tipo = acao.get("type")

        if tipo == "page":
            return acao["page"]
        if tipo == "nada":
            return acao.get("then")

        if tipo == "abrir_claude":
            self._abrir_claude(acao["cwd"])
            return acao.get("then")

        if tipo in ("focar", "seguir", "aprovar", "parar", "pasta"):
            s = self.painel.sessao(acao["pid"])
            if not s:
                raise RuntimeError("sessao sumiu")
            if tipo == "pasta":
                os.startfile(s["cwd"])
                return acao.get("then")
            if self.lig is None:
                self._fazer(tipo, s)            # modo --test: erro na cara
            else:
                threading.Thread(target=self._fazer, args=(tipo, s),
                                 daemon=True, name=tipo).start()
            return acao.get("then")

        # --- som. Rapido o bastante para rodar no loop (pycaw responde em ms)
        if tipo == "app_mudo":
            som.mudo_app(acao["exe"])
            return acao.get("then")
        if tipo == "mudo":
            som.mudo_geral(acao["qual"])
            return acao.get("then")
        if tipo == "volume":
            som.volume_geral(acao["qual"], acao["delta"])
            return acao.get("then")
        if tipo == "atalho":
            janelas.combo(*acao["teclas"])
            return acao.get("then")
        if tipo == "midia":
            # tecla de midia vale para o sistema todo: nao precisa focar nada
            janelas.tecla(acao.get("key", "play_pause"))
            return acao.get("then")

        raise ValueError("acao desconhecida: {!r}".format(tipo))

    def _fazer(self, tipo: str, s: dict) -> None:
        """O que realmente chega ate o terminal da sessao."""
        try:
            # O titulo da aba e o ai-title da sessao: e por ele que janelas.py
            # confere se esta na aba certa antes de digitar qualquer coisa.
            alvo = s.get("titulo") or ""
            if tipo == "focar":
                if not janelas.garantir_aba(s["pid"], alvo):
                    raise RuntimeError("janela nao encontrada")
            elif tipo == "seguir":
                texto = self.painel.cfg.get("texto_continuar", "continua")
                janelas.mandar_para(s["pid"], texto, enter=True, alvo=alvo)
            elif tipo == "aprovar":
                # Enter sozinho: confirma a opcao ja destacada no prompt de
                # permissao. Sem prompt aberto, e uma linha vazia - inofensiva.
                janelas.mandar_para(s["pid"], "", enter=True, alvo=alvo)
            elif tipo == "parar":
                if not janelas.garantir_aba(s["pid"], alvo):
                    raise RuntimeError("janela nao encontrada")
                time.sleep(0.1)
                janelas.tecla("esc")
        except Exception as e:
            print("[erro] {} em {}: {}".format(tipo, s.get("nome"), e))
            if self.lig is not None:
                self.lig.recado({"ev": "aviso", "msg": str(e)[:40]})

    def _abrir_claude(self, cwd: str) -> None:
        """Windows Terminal ja na pasta, com o claude rodando.

        O `wt -d <pasta>` abre a aba direto na pasta, entao dispensa o cd. O
        -NoExit mantem o terminal vivo quando o comando sair, senao a janela
        fecharia na cara de quem tocou.
        """
        cmd = self.painel.cfg.get("comando") or "claude"
        wt = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WindowsApps/wt.exe"
        if wt.exists():
            subprocess.Popen([str(wt), "-d", cwd, "pwsh", "-NoExit", "-Command", cmd],
                             close_fds=True)
        else:
            subprocess.Popen(["cmd", "/c", "start", "", "cmd", "/k",
                              'cd /d "{}" && {}'.format(cwd, cmd)], close_fds=True)


# ------------------------------------------------------------------- serial

class Ligacao:
    """Uma conexao serial com a placa."""

    def __init__(self, ser, painel):
        self.ser = ser
        self.painel = painel
        self.exec = Executor(painel, self)
        self.pagina_atual = ""
        self.buf = b""

        self.enviadas: set = set()      # artes que a placa ja tem
        self.versoes: dict = {}         # id da arte -> versao que a placa tem
        self.img_placa: dict = {}       # id da arte -> a imagem que a placa tem
        self.fila: list = []
        self.pendente = None            # (pedaco, hora, tentativas)
        self.imgok = -2
        self.img_tem = False
        self.ruins: dict = {}
        self.refazer: list = []
        self.precarregado: set = set()

        self.recados: list = []
        self.recados_lock = threading.Lock()

        self.ultimo_estado: dict = {}
        self.ultima_barra = ""
        self.assinatura = ""            # o layout que a placa tem desenhado
        self.proximo_olhar = 0.0
        self.estados_vistos: dict = {}  # pid -> estado, para avisar quem parou

    # ------------------------------------------------------------- envio

    def envia(self, obj: dict) -> None:
        self.ser.write((json.dumps(obj, ensure_ascii=True) + "\n").encode())

    def recado(self, obj: dict) -> None:
        """Chamavel de outra thread: enfileira; quem escreve na serial e o loop."""
        with self.recados_lock:
            self.recados.append(obj)

    def envia_pagina(self, pid: str) -> bool:
        pag = self.painel.pagina(pid)
        if not pag:
            print("[erro] pagina desconhecida: {}".format(pid))
            return False
        self.envia(pag)
        self.pagina_atual = pid
        self.assinatura = self._assinatura(pag)
        print("[pagina] {}: {} cards".format(pid, len(pag["buttons"])))
        # A pagina que esta na tela passa na frente do precarregamento. Quem sai
        # da fila volta a contar como pendente, senao a precarga trava no meio a
        # cada navegacao.
        for t in self.fila:
            if not t["prio"]:
                self.precarregado.discard(t.get("pid", ""))
        self.fila = [t for t in self.fila if t["prio"]]
        self.pendente = None
        self.enfileira(pid, prio=True)
        self.ultimo_estado = {}         # forca o proximo state a ir inteiro
        return True

    @staticmethod
    def _assinatura(pag: dict) -> str:
        """O que faz a placa precisar de um layout novo: os ids e as artes."""
        return "|".join(b["id"] + ">" + b["art"] for b in pag["buttons"])

    def enfileira(self, pid: str, prio: bool) -> int:
        """Poe na fila o que a placa ainda nao tem - ou tem VELHO.

        O id da arte e estavel e o conteudo tem versao a parte. Quando so a
        versao muda, a imagem vai de novo com o MESMO id: o firmware troca o
        sprite e redesenha aquele botao sozinho, sem layout novo e sem o
        fillScreen que fazia a tela inteira piscar.

        Nesse caso a sondagem (i = -1) e pulada de proposito: ela existe para
        perguntar "voce ja tem esta arte?", e a resposta seria sim - pelo id e
        pelo tamanho - justamente quando queremos substituir.
        """
        novas = 0
        for chave, w, h, dados, versao in self.painel.artes_da_pagina(pid):
            if any(t["chave"] == chave for t in self.fila):
                continue
            ja_tem = chave in self.enviadas
            if ja_tem and self.versoes.get(chave, "") == versao:
                continue

            # Card que a placa ja tem e so mudou de conteudo: manda o RETANGULO
            # que mudou, nao o card. E a diferenca entre 16 KB e 2 KB por
            # atualizacao - e entre a serial saturada (com arte chegando
            # corrompida) e 5% de ocupacao.
            if ja_tem:
                nova = self.painel.imagem(chave, w, h)
                caixas = remendo.diferenca(self.img_placa.get(chave), nova)
                if caixas == []:
                    # o conteudo mudou mas o desenho ficou igual: nada a fazer
                    self.versoes[chave] = versao
                    continue
                if caixas:
                    novas += self._enfileira_remendos(chave, nova, caixas,
                                                      versao, prio, pid)
                    continue

            b64 = base64.b64encode(dados).decode("ascii")
            partes = [b64[i:i + CHUNK_B64] for i in range(0, len(b64), CHUNK_B64)]
            self.fila.append({"chave": chave, "w": w, "h": h, "len": len(dados),
                              "partes": partes, "i": 0 if ja_tem else -1,
                              "prio": prio, "pid": pid, "versao": versao,
                              "img": self.painel.imagem(chave, w, h),
                              "ultimo": True})
            novas += 1
        if novas:
            print("[arte] {}: {} imagens na fila{}".format(
                pid, novas, "" if prio else " (precarregando)"))
        return novas

    def _enfileira_remendos(self, chave, nova, caixas, versao, prio, pid) -> int:
        """Um item de fila por retangulo que mudou.

        So o ULTIMO carrega a versao: se um remendo do meio se perder, o card
        continua marcado como desatualizado e a proxima volta o refaz.
        """
        import arte as _arte
        n = 0
        for k, caixa in enumerate(caixas):
            recorte = remendo.recorta(nova, caixa)
            dados = _arte.para_jpeg(recorte, self.painel.qualidade)
            b64 = base64.b64encode(dados).decode("ascii")
            partes = [b64[i:i + CHUNK_B64] for i in range(0, len(b64), CHUNK_B64)]
            self.fila.append({
                "chave": chave, "w": recorte.width, "h": recorte.height,
                "len": len(dados), "partes": partes, "i": 0, "prio": prio,
                "pid": pid, "versao": versao, "sx": caixa[0], "sy": caixa[1],
                "caixa": caixa, "recorte": recorte, "img": nova,
                "ultimo": k == len(caixas) - 1})
            n += 1
        if n:
            print("[remendo] {}: {} pedaco(s), {} bytes".format(
                chave, n, sum(t["len"] for t in self.fila
                              if t["chave"] == chave and "sx" in t)))
        return n

    def bombeia_fila(self) -> None:
        """Manda UM pedaco por passagem.

        E o que mantem o toque respondendo enquanto a arte carrega: o painel
        nunca fica parado esperando bitmap, e a pagina aparece preenchendo.
        """
        if not self.fila and self.refazer:
            chave = self.refazer.pop(0)
            for pid in self.painel.paginas_conhecidas():
                if any(c == chave for c, _w, _h, _d, _v in self.painel.artes_da_pagina(pid)):
                    self.enfileira(pid, prio=True)
                    return
            return

        if not self.fila:
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
                    self.enviadas.add(t["chave"])       # a placa ja tem
                    self.versoes[t["chave"]] = t.get("versao", "")
                    self.img_placa[t["chave"]] = t.get("img")
                    self.fila.pop(0)
                    return
                t["i"] = i + 1
                if t["i"] >= len(t["partes"]):
                    self._concluiu(t)
                    self.fila.pop(0)
                return
            if time.monotonic() - quando < 1.2:
                return
            if tentativas < 1:
                self.pendente = (i, time.monotonic(), tentativas + 1)
                self.envia_parte(t, i)
                return
            print("[arte] {}: pedaco {} sem confirmacao, desistindo".format(
                t["chave"], i))
            self.fila.pop(0)
            self.pendente = None
            return

        self.imgok = -2
        self.envia_parte(t, t["i"])
        self.pendente = (t["i"], time.monotonic(), 0)

    def _concluiu(self, t: dict) -> None:
        """A placa confirmou o ultimo pedaco deste item."""
        chave = t["chave"]
        self.enviadas.add(chave)
        if "sx" in t:
            # espelha o que a placa acabou de desenhar, para o proximo diff
            base = self.img_placa.get(chave)
            if base is not None and t.get("recorte") is not None:
                base = base.copy()
                base.paste(t["recorte"], (t["sx"], t["sy"]))
                self.img_placa[chave] = base
            else:
                self.img_placa[chave] = t.get("img")
        else:
            self.img_placa[chave] = t.get("img")
            print("[arte] {}: {} bytes em {} partes".format(
                chave, t["len"], len(t["partes"])))
        if t.get("ultimo", True):
            self.versoes[chave] = t.get("versao", "")

    def envia_parte(self, t: dict, i: int) -> None:
        # "off" e o deslocamento em bytes DECODIFICADOS. Vai explicito para o
        # reenvio ser idempotente: quando uma confirmacao se perde e o pedaco e
        # mandado de novo, sem isso a placa soma o mesmo trecho duas vezes.
        if i < 0:
            self.envia({"ev": "img", "id": t["chave"], "w": t["w"], "h": t["h"],
                        "len": t["len"], "i": -1, "n": len(t["partes"])})
            return
        msg = {"ev": "img", "id": t["chave"], "w": t["w"], "h": t["h"],
               "len": t["len"], "off": i * (CHUNK_B64 * 3 // 4),
               "i": i, "n": len(t["partes"]), "d": t["partes"][i]}
        if "sx" in t:
            msg["sx"], msg["sy"] = t["sx"], t["sy"]
        self.envia(msg)

    # ------------------------------------------------------------ recepcao

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
                legivel = sum(32 <= ord(c) < 127 for c in txt)
                if legivel > len(txt) * 0.8:
                    print("[placa] {}".format(txt))
                continue
            try:
                self.trata(json.loads(txt))
            except json.JSONDecodeError:
                pass

    def trata(self, msg: dict) -> None:
        cmd = msg.get("cmd")

        if cmd == "imgok":
            self.imgok = msg.get("i", -1)
            self.img_tem = bool(msg.get("tem", False))
            return

        if cmd == "imgbad":
            chave = msg.get("id", "")
            n = self.ruins.get(chave, 0) + 1
            self.ruins[chave] = n
            self.enviadas.discard(chave)
            self.img_placa.pop(chave, None)
            self.versoes.pop(chave, None)
            if n <= 3:
                print("[arte] {}: chegou corrompida, remandando ({}/3)".format(chave, n))
                self.refazer.append(chave)
            else:
                print("[arte] {}: corrompeu {} vezes, desistindo".format(chave, n))
            return

        if cmd == "hello":
            print("[hello] fw={}".format(msg.get("fw", "?")))
            pag = msg.get("page", "")
            if pag and self.painel.pagina(pag):
                self.pagina_atual = pag     # a placa ja esta desenhada
                self.enfileira(pag, prio=True)
                self.ultimo_estado = {}
                return
            self.enviadas.clear()           # a placa reiniciou: perdeu os sprites
            self.versoes.clear()
            self.img_placa.clear()
            self.fila.clear()
            self.pendente = None
            self.precarregado.clear()
            try:
                self.painel.cfg = carregar_config()
            except Exception as e:
                print("[erro] config.json: {} - mantendo o anterior".format(e))
            self.envia_pagina("home")

        elif cmd == "page":
            self.envia_pagina(msg.get("id", "home"))

        elif cmd == "state":
            self.ultimo_estado = {}

        elif cmd == "btn":
            self.toque(msg.get("page", self.pagina_atual), msg.get("id", ""))

    def toque(self, pid: str, bid: str) -> None:
        acao = self.painel.acao(pid, bid)
        if acao is None:
            self.envia({"ev": "err", "id": bid, "msg": "sem mapeamento"})
            print("[erro] {}/{}: sem mapeamento".format(pid, bid))
            return
        try:
            destino = self.exec.executar(acao)
            self.envia({"ev": "ack", "id": bid, "ok": True})
            print("[btn] {}/{} -> {}".format(pid, bid, acao.get("type")))
            if destino:
                self.envia_pagina(destino)
        except Exception as e:
            self.envia({"ev": "err", "id": bid, "msg": str(e)[:40]})
            print("[erro] {}/{}: {}".format(pid, bid, e))

    # ----------------------------------------------------------- vigilancia

    def olha_sessoes(self) -> None:
        """O coracao do painel: o que mudou nas sessoes desde a ultima volta.

        Tres saidas, da mais barata para a mais cara:
          - estado (80 B): acende e apaga cards, sem redesenhar nada
          - barra  (90 B): o resumo em texto
          - layout (KB):   so quando a LISTA ou um titulo mudou
        """
        ss = self.painel.sessoes(forcar=True)

        # quem estava trabalhando e parou merece um aviso na barra
        for s in ss:
            antes = self.estados_vistos.get(s["pid"])
            if antes == "trabalhando" and s["estado"] != "trabalhando":
                self.envia({"ev": "aviso", "msg": (s["nome"][:24] + " terminou")})
        self.estados_vistos = {s["pid"]: s["estado"] for s in ss}

        estado = self.painel.estado()
        if estado != self.ultimo_estado:
            self.envia({"ev": "state", **estado})
            self.ultimo_estado = estado

        barra = self.painel.resumo()
        if barra != self.ultima_barra:
            self.envia({"ev": "barra", "txt": barra})
            self.ultima_barra = barra

        # O layout so vai de novo quando a pagina muda de FORMA - uma sessao
        # nasceu, morreu, um app comecou a tocar. Layout novo faz o firmware
        # chamar desenhaTudo(), que limpa a tela: se isso acontecesse a cada
        # mudanca de conteudo, o painel piscaria sem parar (e piscava).
        pag = self.painel.pagina(self.pagina_atual)
        if not pag:
            if self.pagina_atual.startswith("ses/"):
                self.envia_pagina("claude")     # a sessao desta pagina fechou
            return
        if self._assinatura(pag) != self.assinatura:
            self.envia_pagina(self.pagina_atual)
            return

        # Mesma forma: o que mudou foi o CONTEUDO de algum card. Vai como
        # imagem nova com o mesmo id, e a placa redesenha so aquele botao.
        self.enfileira(self.pagina_atual, prio=True)

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
            if agora >= self.proximo_olhar:
                self.olha_sessoes()
                self.proximo_olhar = agora + intervalo

            # Sem trabalho: BLOQUEIA no read em vez de girar em vazio. Nao usar
            # sleep - o timer do Windows tem granularidade de ~15 ms e ia CRIAR
            # latencia de toque. O read com timeout dorme no driver e acorda no
            # primeiro byte que a placa mandar.
            if not self.fila and not self.ser.in_waiting:
                self.buf += self.ser.read(1)


# ---------------------------------------------------------------- modo teste

def modo_teste(painel, args: list) -> int:
    ss = painel.sessoes()
    if not args:
        print("Sessoes vivas:")
        for i, s in enumerate(ss):
            print("  [{}] {:16s} pid={:<6d} {:12s} {} {}  ctx {}k".format(
                i, s["nome"], s["pid"], s["estado"], s["_modelo_curto"],
                s["effort"], s["ctx"] // 1000))
            print("      {}".format(s["titulo"]))
        import som as som_mod
        print("\nsom:", som_mod.geral())
        for a in som_mod.apps():
            print("   {:14s} vol {:3d} {}".format(
                a["nome"], a["vol"], "MUDO" if a["mudo"] else ""))
        print("\nbarra: {}".format(painel.resumo()))
        print("estado: {}".format(json.dumps(painel.estado())))
        for pid in painel.paginas_conhecidas():
            pag = painel.pagina(pid)
            if pag:
                print("\n  [{}] grade {}x{}: {}".format(
                    pid, pag["grid"]["cols"], pag["grid"]["rows"],
                    ", ".join(b["id"] for b in pag["buttons"])))
        return 0

    ex = Executor(painel)
    for spec in args:
        pid, _, bid = spec.rpartition("/")
        if not pid:
            pid, bid = "home", spec
        acao = painel.acao(pid, bid)
        if acao is None:
            print("[erro] {}/{}: sem mapeamento".format(pid, bid))
            continue
        try:
            destino = ex.executar(acao)
            print("[ok] {}/{} -> {}{}".format(
                pid, bid, acao.get("type"),
                ", vai para " + destino if destino else ""))
        except Exception as e:
            print("[erro] {}/{}: {}".format(pid, bid, e))
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        from comtypes import CoInitialize
        CoInitialize()          # sem isto o pycaw nao abre nesta thread
    except Exception as e:
        print("[aviso] COM nao inicializado: {} - o mixer fica vazio".format(e))
    cfg = carregar_config()
    from paginas import Painel
    painel = Painel(cfg)

    argv = sys.argv[1:]
    if argv and argv[0] in ("--test", "-t", "--list", "-l"):
        return modo_teste(painel, argv[1:])

    # Desenha a arte de todas as paginas numa thread, ja durante o arranque.
    # Sem isto os ~70 ms por card virariam quase um segundo de espera bem no
    # momento do toque. Na segunda execucao vem do cache em disco.
    def aquecer():
        t0 = time.monotonic()
        try:
            painel.pre_gerar()
            print("[arte] paginas prontas em {:.1f}s".format(time.monotonic() - t0))
        except Exception as e:
            print("[arte] precarregamento parou: {}".format(e))

    threading.Thread(target=aquecer, daemon=True, name="arte").start()

    intervalo = cfg.get("olhar_intervalo_ms", 700) / 1000.0
    baud = cfg.get("baud", 921600)

    while True:
        porta = achar_porta(cfg.get("port", "auto"))
        if not porta:
            print("[...] nenhuma porta serial, tentando de novo")
            time.sleep(2)
            continue
        try:
            ser = serial.Serial(porta, baud, timeout=0.005)
        except serial.SerialException as e:
            print("[erro] {}: {}".format(porta, e))
            time.sleep(2)
            continue

        print("[ok] conectado em {} @ {}".format(porta, baud))
        try:
            lig = Ligacao(ser, painel)
            # A placa so manda hello quando NAO tem pagina. Se o agente reinicia
            # com a placa ja desenhada, ela ficaria calada - entao aqui e o PC
            # que pergunta.
            lig.envia({"ev": "quem"})
            lig.roda(intervalo)
        except (serial.SerialException, OSError) as e:
            print("[desconectado] {}".format(e))
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
