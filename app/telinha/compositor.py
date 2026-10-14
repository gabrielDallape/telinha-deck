"""
Do perfil para o que a placa entende: layout de pagina e JPEG de cada botao.

ID DA ARTE e responsabilidade daqui, nunca do modulo: `<botao>~<hash>`, em que
o hash cobre a aparencia. Mudou cor, icone ou rotulo no editor, o id muda e a
placa baixa a arte nova (antes, so o comprimento do JPEG denunciava a troca).
Card vivo mantem esse id e ganha uma VERSAO (relogio virou o minuto, musica
trocou): a placa troca o sprite no lugar, sem piscar.

DESENHO em pool de 2 threads com tempo limite. A thread serial pede a arte e
espera no maximo um pouco; se o widget demorar, a arte fica para a proxima
volta (a Ligacao confere de 250 ms em 250 ms o que falta). Um modulo lento ou
travado nunca segura o toque.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import threading
import time
from pathlib import Path

from . import arte, caminhos

# Tem de casar com o firmware (telinha_p4.ino)
TELA_W, TELA_H, BARRA_H, MARGEM = 1280, 720, 72, 8
MAX_ID = 60          # o firmware guarda 72 bytes de id, com folga para ":on"
VAZIO = "_vazio"     # quadrado vazio entre botoes: um sprite so, da cor da tela


def tamanho_botao(cols: int, rows: int) -> tuple:
    cw = TELA_W // cols
    ch = (TELA_H - BARRA_H) // rows
    return cw - 2 * MARGEM, ch - 2 * MARGEM


def grade_para(n: int) -> dict:
    """Nunca menos de 3 colunas: card gigante come PSRAM a toa (ver o agente)."""
    if n <= 6:
        return {"cols": 3, "rows": 2}
    if n <= 8:
        return {"cols": 4, "rows": 2}
    if n <= 10:
        return {"cols": 5, "rows": 2}
    return {"cols": 5, "rows": 3}


def _versao_desenho() -> str:
    """Mexer no arte.py ou no icones.py invalida o cache em disco."""
    base = Path(arte.__file__).parent
    return "-".join(str(int((base / n).stat().st_mtime)) for n in ("arte.py", "icones.py"))


def _h(obj, n: int = 6) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:n]


class Compositor:
    def __init__(self, hospedeiro, perfil: dict):
        self.hosp = hospedeiro
        self.perfil = perfil
        self.qualidade = int(perfil.get("ajustes", {}).get("jpeg_qualidade", 90))
        self.niveis: dict = {}          # {"sys_vol": 62}, com debounce da Ligacao
        self.versao_desenho = _versao_desenho()
        self._botoes: dict = {}         # (pagina, botao) -> botao (esquema 2)
        self._artes: dict = {}          # id da arte -> (botao, w, h, aceso)
        self._cache: dict = {}          # cache_id -> bytes (arte fixa)
        self._vivo: dict = {}           # (id, w, h) -> (versao, bytes)
        self._gerados: dict = {}        # pagina -> ultimos botoes do provedor
        self._voando: dict = {}         # chave de render -> Future
        self._lock = threading.Lock()
        self._pool = cf.ThreadPoolExecutor(2, thread_name_prefix="arte")
        self._pool_prov = cf.ThreadPoolExecutor(1, thread_name_prefix="provedor")

    def troca_perfil(self, perfil: dict) -> None:
        self.perfil = perfil
        self.qualidade = int(perfil.get("ajustes", {}).get("jpeg_qualidade", 90))
        self._gerados.clear()

    # ------------------------------------------------------------- paginas

    def paginas(self) -> list:
        """Ordem da precarga: a de inicio primeiro, depois o resto."""
        pags = list(self.perfil.get("paginas", {}))
        ini = self.perfil.get("inicio", "home")
        return ([ini] if ini in pags else []) + [p for p in pags if p != ini]

    def _botoes_da_pagina(self, pid: str, pag: dict) -> list:
        fixos = [b for b in pag.get("botoes", []) if not b.get("desligado")]
        if not pag.get("gerar"):
            return fixos
        nome = pag["gerar"]
        if nome not in self.hosp.provedores:
            return fixos
        mid, fn = self.hosp.provedores[nome]
        if mid not in self.hosp.ligados:
            return fixos
        # Provedor e codigo de modulo: roda fora da thread serial, com prazo.
        # Estourou o prazo, fica a lista anterior.
        fut = self._pool_prov.submit(fn, pag)
        try:
            gerados = fut.result(timeout=1.0)[:max(0, 15 - len(fixos))]
            self._gerados[pid] = gerados
        except cf.TimeoutError:
            print(f"[pagina] {pid}: provedor {nome} lento, usando a lista anterior")
            gerados = self._gerados.get(pid, [])
        except Exception as e:
            print(f"[pagina] {pid}: provedor {nome}: {e}")
            gerados = self._gerados.get(pid, [])
        return gerados + fixos

    def id_arte(self, b: dict) -> str:
        tipo = (b.get("toque") or [{}])[0].get("type", "")
        base = b["id"]
        h = _h({"ap": b.get("aparencia", {}), "t": tipo, "a": bool(b.get("aceso"))}, 5)
        if len(base) + 6 > MAX_ID:
            base = "b" + hashlib.sha1(base.encode()).hexdigest()[:12]
        return f"{base}~{h}"

    @staticmethod
    def posiciona(botoes: list, grade: dict) -> list:
        """Botao com `pos` vai para aquele quadrado; os outros enchem os livres
        em ordem. Buraco entre botoes vira None (quadrado vazio); o que sobra no
        fim e cortado - o firmware enche a grade em ordem."""
        n = grade["cols"] * grade["rows"]
        slots = [None] * n
        soltos = []
        for b in botoes:
            p = b.get("pos")
            if isinstance(p, int) and 0 <= p < n and slots[p] is None:
                slots[p] = b
            else:
                soltos.append(b)
        livres = (i for i in range(n) if slots[i] is None)
        for b in soltos:
            i = next(livres, None)
            if i is None:
                break                   # nao cabe: fica de fora (a grade e pequena)
            slots[i] = b
        while slots and slots[-1] is None:
            slots.pop()
        return slots

    def pagina(self, pid: str) -> dict | None:
        pag = (self.perfil.get("paginas") or {}).get(pid)
        if pag is None:
            return None
        botoes = self._botoes_da_pagina(pid, pag)
        grade = pag.get("grade") or grade_para(len(botoes))
        w, h = tamanho_botao(grade["cols"], grade["rows"])
        saida, vivos = [], {}
        for b in self.posiciona(botoes, grade):
            if b is None:
                vazio = f"{VAZIO}{w}x{h}"
                self._artes[vazio] = (None, w, h, False)
                saida.append({"id": VAZIO, "art": vazio, "art_on": "", "state_key": ""})
                continue
            self._botoes[(pid, b["id"])] = b
            art = self.id_arte(b)
            self._artes[art] = (b, w, h, False)
            item = {"id": b["id"], "art": art, "art_on": "", "state_key": b.get("aceso", "")}
            if b.get("aceso"):
                item["art_on"] = art + ":on"
                self._artes[art + ":on"] = (b, w, h, True)
            v = self.versao(b)
            if v is not None:
                vivos[art] = v
            saida.append(item)
        return {"ev": "layout", "page": pid, "title": pag.get("titulo", ""),
                "back": pag.get("voltar", ""), "grid": grade, "buttons": saida,
                "_vivos": vivos, "_brilho": pag.get("brilho")}

    def botao(self, pid: str, bid: str) -> dict | None:
        if (pid, bid) not in self._botoes:
            self.pagina(pid)
        return self._botoes.get((pid, bid))

    # ----------------------------------------------------------- vivos

    def _textos(self, ap: dict) -> dict:
        """'{projetos}' num rotulo: o texto vem do modulo e faz o card ser vivo."""
        saida = {}
        for k in ("label", "label_on", "sub"):
            v = ap.get(k)
            if isinstance(v, str) and "{" in v and "}" in v:
                nome = v[v.index("{") + 1:v.index("}")]
                t = self.hosp.texto(nome)
                if t is not None:
                    saida[k] = v.replace("{" + nome + "}", t)
        return saida

    def versao(self, b: dict) -> str | None:
        ap = b.get("aparencia") or {}
        partes = []
        w = ap.get("widget", "icone")
        if w in self.hosp.versoes:
            mid, fn = self.hosp.versoes[w]
            if mid in self.hosp.ligados:
                try:
                    partes.append(str(fn(ap)))
                except Exception as e:
                    print(f"[{mid}] versao {w}: {e}")
                    partes.append("erro")
        if ap.get("nivel_de"):
            v = self.niveis.get(ap["nivel_de"])
            partes.append(str(int(round(v / 5.0) * 5)) if v is not None else "x")
        textos = self._textos(ap)
        if textos:
            partes.append(_h(textos, 6))
        return "|".join(partes) if partes else None

    # ------------------------------------------------------------- arte

    def artes_da_pagina(self, pid: str, espera: float = 0.25) -> list:
        """[(id_arte, w, h, jpeg, versao)] do que ja esta desenhado.

        O que ainda nao esta pronto NAO entra: fica desenhando no pool e a
        Ligacao manda na volta seguinte."""
        pag = self.pagina(pid)
        if not pag:
            return []
        saida = []
        for item in pag["buttons"]:
            for chave in (item["art"], item["art_on"]):
                if not chave:
                    continue
                versao = pag["_vivos"].get(item["art"]) if not chave.endswith(":on") else None
                dados = self.arte(chave, versao, espera)
                if dados:
                    saida.append((chave, *self._artes[chave][1:3], dados, versao))
        return saida

    def total_artes(self, pid: str) -> int:
        """Quantas artes a pagina tem (com as variantes acesas), prontas ou nao."""
        pag = self.pagina(pid) or {"buttons": []}
        return sum(1 + bool(b["art_on"]) for b in pag["buttons"])

    def arte(self, chave: str, versao: str | None = None, espera: float = 0.25) -> bytes | None:
        if chave not in self._artes:
            return None
        b, w, h, aceso = self._artes[chave]
        if versao is not None:
            k = (chave, w, h)
            g = self._vivo.get(k)
            if g and g[0] == versao:
                return g[1]
            return self._desenha(("v", chave, versao), chave, espera,
                                 lambda d: self._vivo.__setitem__(k, (versao, d)))
        cache_id = f"{chave}@{w}x{h}|{self.versao_desenho}"
        if cache_id in self._cache:
            return self._cache[cache_id]
        arq = caminhos.CACHE / (hashlib.sha1(cache_id.encode()).hexdigest()[:20] + ".jpg")
        if arq.exists():
            dados = arq.read_bytes()
            self._cache[cache_id] = dados
            return dados

        def guarda(d):
            self._cache[cache_id] = d
            try:
                arq.write_bytes(d)
            except OSError:
                pass
        return self._desenha(("f", cache_id), chave, espera, guarda)

    def _desenha(self, chave_voo, chave: str, espera: float, guarda) -> bytes | None:
        with self._lock:
            fut = self._voando.get(chave_voo)
            if fut is None:
                fut = self._pool.submit(self._renderiza, chave)

                def fim(f, guarda=guarda, kv=chave_voo):
                    try:
                        d = f.result()
                        if d:
                            guarda(d)
                    finally:
                        with self._lock:
                            self._voando.pop(kv, None)
                fut.add_done_callback(fim)
                self._voando[chave_voo] = fut
        try:
            return fut.result(timeout=espera)
        except cf.TimeoutError:
            return None
        except Exception:
            return None

    def _renderiza(self, chave: str) -> bytes | None:
        b, w, h, aceso = self._artes[chave]
        try:
            if b is None:                   # quadrado vazio: so a cor da tela
                from PIL import Image
                img = Image.new("RGB", (w, h), (0x0E, 0x11, 0x16))
            else:
                img = self.desenha(b, w, h, aceso)
        except Exception as e:
            print(f"[arte] {chave}: {e}")
            img = None
        return arte.para_jpeg(img, self.qualidade) if img is not None else None

    def desenha(self, b: dict, w: int, h: int, aceso: bool):
        ap = dict(b.get("aparencia") or {})
        widget = ap.get("widget", "icone")
        if widget != "icone" and widget in self.hosp.widgets and not aceso:
            mid, fn = self.hosp.widgets[widget]
            if mid in self.hosp.ligados:
                # o widget devolve uma imagem pronta, ou um dict que ajusta o
                # icone padrao (o player parado vira "Play"), ou None
                img = fn(ap, w, h, aceso)
                if isinstance(img, dict):
                    ap.update(img)
                elif img is not None:
                    return img
        # o tipo do primeiro passo decide o peso (pagina = destino colorido)
        ap["type"] = (b.get("toque") or [{}])[0].get("type", "")
        if b.get("aceso"):
            ap["state_key"] = b["aceso"]
        if ap.get("nivel_de"):
            v = self.niveis.get(ap["nivel_de"])
            if v is not None:
                ap["nivel"] = int(v)
        ap.update(self._textos(ap))
        return arte.botao_icone(w, h, ap, aceso)

    # ------------------------------------------------------------ precarga

    def pre_desenhar(self, aviso=None) -> None:
        """Desenha tudo no arranque (numa thread): ~70 ms por card viravam
        quase um segundo de espera no toque. Do cache em disco, milissegundos."""
        t0 = time.monotonic()
        for pid in self.paginas():
            self.artes_da_pagina(pid, espera=30.0)
            if aviso:
                aviso(pid)
        print(f"[arte] todas as paginas prontas em {time.monotonic() - t0:.1f}s")

    def texto_barra(self) -> str:
        txt = time.strftime("%H:%M")
        for parte in self.hosp.barra():
            txt += "   " + parte
        return arte._ascii(txt)[:46]
