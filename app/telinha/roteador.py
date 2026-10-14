"""
Toque -> passos -> resultado, e as paginas que abrem sozinhas.

TOQUE. Os passos de um botao rodam num pool de workers, nunca na thread
serial: abrir um app, falar com o OBS ou digitar no terminal podem levar
centenas de ms. O fim (ack/err e a navegacao) volta para a serial por recado.
Logo depois o coletor le o estado de novo - e o que faz o mic acender no ato.

PERFIL POR JANELA (`quando_foco`) e DESCANSO por ociosidade: portados do
agente antigo, comportamento identico (os comentarios dizem por que cada
espera existe).
"""

from __future__ import annotations

import concurrent.futures as cf
import time

from . import janelas


def _co_init():
    try:
        from comtypes import CoInitialize
        CoInitialize()          # pycaw em cada worker
    except Exception:
        pass


class Roteador:
    def __init__(self, nucleo):
        self.n = nucleo
        self.pool = cf.ThreadPoolExecutor(4, thread_name_prefix="acao", initializer=_co_init)
        self.pagina_por_foco = None
        self.foco_hwnd = None
        self.foco_visto_em = 0.0
        self.foco_saiu_em = 0.0
        self.proximo_foco = 0.0
        self.proximo_ocioso = 0.0
        self.descanso_auto = False
        self.pagina_antes = "home"

    # ------------------------------------------------------------- toque

    def toque(self, pid: str, bid: str) -> None:
        if bid == "_vazio":
            return                      # quadrado vazio entre botoes
        b = self.n.comp.botao(pid, bid)
        lig = self.n.lig
        if b is None:
            lig.envia({"ev": "err", "id": bid, "msg": "sem mapeamento"})
            print(f"[erro] {pid}/{bid}: sem mapeamento")
            return
        passos = b.get("toque") or []
        # navegacao pura nao precisa de worker: responde na hora
        if len(passos) == 1 and passos[0].get("type") == "page" and not b.get("depois"):
            lig.envia({"ev": "ack", "id": bid, "ok": True})
            print(f"[btn] {pid}/{bid} -> page")
            self._navega(passos[0]["page"])
            return
        self.pool.submit(self._roda_toque, pid, bid, b)

    def _roda_toque(self, pid: str, bid: str, b: dict) -> None:
        t0 = time.monotonic()
        try:
            destino = self.executar(b.get("toque") or [])
            destino = b.get("depois") or destino
            self.n.lig.recado({"ev": "ack", "id": bid, "ok": True})
            tipos = ",".join(p.get("type", "?") for p in b.get("toque") or [])
            print(f"[btn] {pid}/{bid} -> {tipos} ({(time.monotonic() - t0) * 1000:.0f} ms)")
            if destino:
                self.n.lig.recado({"_navegar": destino})
                self.descanso_auto = False
                self.pagina_por_foco = None
        except Exception as e:
            self.n.lig.recado({"ev": "err", "id": bid, "msg": str(e)[:60]})
            print(f"[erro] {pid}/{bid}: {e}")
        finally:
            self.n.atualizar_estado()

    def executar(self, passos: list) -> str | None:
        """Roda os passos em ordem. Devolve a pagina para onde ir, se algum
        passo pediu. Erro num passo para a sequencia."""
        destino = None
        for k, p in enumerate(passos):
            tipo = p.get("type")
            if tipo == "page":
                destino = p["page"]
            elif tipo == "nada":
                pass
            elif tipo == "sequence":
                destino = self.executar(p.get("steps", [])) or destino
            else:
                if tipo not in self.n.hosp.acoes:
                    raise ValueError(f"acao desconhecida: {tipo!r}")
                mid, fn = self.n.hosp.acoes[tipo]
                if mid not in self.n.hosp.ligados:
                    raise RuntimeError(f"modulo {mid} nao esta ligado")
                r = fn(p)
                if isinstance(r, str) and r:
                    destino = r
            if p.get("then"):
                destino = p["then"]
            # o delay e para o passo SEGUINTE; depois do ultimo, ninguem espera
            if k < len(passos) - 1:
                time.sleep(p.get("delay", 0.05))
        return destino

    def _navega(self, pid: str) -> None:
        self.descanso_auto = False
        self.pagina_por_foco = None
        self.n.lig.envia_pagina(pid)

    def navegou_na_mao(self) -> None:
        """Botao voltar da placa: o perfil por foco solta a pagina."""
        self.pagina_por_foco = None

    # ------------------------------------------------------------ vigias

    def vigia(self, agora: float) -> None:
        self._vigia_ocioso(agora)
        self._vigia_foco(agora)

    def _pagina_descanso(self) -> str:
        return (self.n.ajuste("descanso", {}) or {}).get("pagina", "descanso")

    def _vigia_ocioso(self, agora: float) -> None:
        """Sem teclado/mouse por `descanso.apos_min`: vai para o descanso
        sozinho; mexeu no PC: volta. So o automatico volta sozinho - quem tocou
        em Descansar quer que fique."""
        lig = self.n.lig
        if agora < self.proximo_ocioso or not lig.pagina_atual:
            return
        self.proximo_ocioso = agora + 2.0
        c = self.n.ajuste("descanso", {}) or {}
        apos = float(c.get("apos_min", 0) or 0) * 60
        desc = self._pagina_descanso()
        if apos <= 0 or not self.n.comp.pagina(desc):
            return
        ocioso = janelas_ociosidade()
        if lig.pagina_atual != desc:
            if ocioso >= apos:
                self.pagina_antes = lig.pagina_atual
                self.descanso_auto = True
                print(f"[descanso] PC parado ha {ocioso / 60:.0f} min")
                lig.envia_pagina(desc)
        elif self.descanso_auto and ocioso < 2.0:
            self.descanso_auto = False
            print("[descanso] voltou a mexer no PC")
            lig.envia_pagina(self.pagina_antes or self.n.inicio())

    def _vigia_foco(self, agora: float) -> None:
        """Paginas com `quando_foco` abrem quando aquela janela VEM para a
        frente e fecham quando ela sai. Age na BORDA, nao no estado: uma trava
        de 30 s depois de navegar na mao fazia o Claude recem-aberto cair na
        home por meio minuto."""
        lig = self.n.lig
        if agora < self.proximo_foco or not lig.pagina_atual \
                or lig.pagina_atual == self._pagina_descanso():
            return
        self.proximo_foco = agora + 0.3
        hwnd, exe, titulo = janelas.janela_da_frente()
        paginas = self.n.perfil.get("paginas", {})
        alvo = None
        for pid, pag in paginas.items():
            if any(janelas.regra_bate(r, exe, titulo) for r in pag.get("quando_foco") or []):
                alvo = pid
                break
        if alvo:
            # um quadro sem o simbolo de estado no titulo (o spinner do Claude
            # troca de glifo) nao conta como "voltou": 2 s de tolerancia
            veio = hwnd != self.foco_hwnd or agora - self.foco_visto_em > 2.0
            self.foco_hwnd, self.foco_visto_em = hwnd, agora
            self.foco_saiu_em = 0.0
            if veio and alvo != lig.pagina_atual:
                print(f"[foco] {alvo} veio para a frente")
                self.pagina_por_foco = alvo
                lig.envia_pagina(alvo)
            elif veio:
                self.pagina_por_foco = alvo
        elif self.pagina_por_foco and lig.pagina_atual == self.pagina_por_foco:
            # Saiu. Mesmo programa com outro titulo (sessao nova do Claude
            # subindo) espera mais: era o que fazia a pagina piscar a home.
            regras = (paginas.get(self.pagina_por_foco) or {}).get("quando_foco") or []
            mesmo_exe = any((r if isinstance(r, str) else str(r.get("exe", ""))).lower() == exe
                            for r in regras)
            espera = 6.0 if mesmo_exe else 1.5
            if not self.foco_saiu_em:
                self.foco_saiu_em = agora
            elif agora - self.foco_saiu_em >= espera:
                print(f"[foco] saiu; voltando para {self.n.inicio()}")
                self.pagina_por_foco = None
                self.foco_saiu_em = 0.0
                lig.envia_pagina(self.n.inicio())


def janelas_ociosidade() -> float:
    """Segundos desde o ultimo teclado/mouse no PC."""
    import ctypes

    class _LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = _LII()
    lii.cbSize = ctypes.sizeof(_LII)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0
