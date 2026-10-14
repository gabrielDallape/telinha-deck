"""
Monta as paginas do painel, a arte de cada card e o que cada toque faz.

A tela nao sabe o que e uma sessao do Claude nem o que e um mixer: ela pede uma
pagina por id, estampa os bitmaps que chegam e devolve o id do card tocado.

    home ---- Claude    -> claude -> ses/<pid> -> focar, continuar, aprovar, parar
         ---- Som       -> som    -> volume por aplicativo
         ---- Projetos  -> projetos -> abre o terminal com o claude rodando
         ---- Musica, Microfone, Recorte: agem no toque, sem sair da home

O ID DA ARTE E ESTAVEL; o conteudo tem VERSAO a parte. Essa e a regra que
importa mais aqui, e custou uma tela piscando para ser aprendida: o firmware
redesenha a tela INTEIRA (fillScreen) toda vez que recebe um layout. Se o id da
arte mudasse junto com o conteudo - como mudava quando a chave era um hash -,
cada ferramenta que uma sessao roda mandava um layout novo e a tela piscava.

Com o id fixo, o conteudo novo vai como uma imagem com o MESMO id: o firmware
troca o sprite e marca sujo so aquele botao. Nada pisca, e o layout so e
remandado quando a pagina muda de forma de verdade (uma sessao nasceu ou morreu).

As outras duas regras, que vem da serial a 38 KB/s:

  - O que muda a cada SEGUNDO nao entra na arte: vai para a barra, que custa
    90 bytes contra 16 KB de um card.
  - Valor continuo entra na versao em FAIXAS, nunca cru (volume em degraus de
    5, contexto em 10%), senao o card e refeito a cada leitura.
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

import arte
import atividade
import midia
import sessoes
import som as som_mod

# Tem de casar com o firmware: e daqui que sai o tamanho exato de cada card.
TELA_W, TELA_H, BARRA_H, MARGEM = 1280, 720, 72, 8

CACHE_DIR = Path(__file__).resolve().parent / "cache"

CORES_PROJ = [arte.ROXO, arte.AZUL, arte.VERDE, arte.AMBAR, arte.LARANJA,
              0x12A594, 0xE93D82, 0x6E56CF]

# Artes cujo conteudo muda em uso. Nao vao para o cache em disco - encheriam a
# pasta de lixo - e sao as unicas que carregam versao.
VIVAS = ("ses:", "info:", "linha:", "arqs:", "som:", "nav:", "mus:", "uso:")

ACOES = [
    ("focar", "Focar", "traz a janela", "focar", arte.AZUL),
    ("seguir", "Continuar", "manda 'continua'", "seguir", arte.VERDE),
    ("aprovar", "Aprovar", "confirma o que ela pediu", "aprovar", arte.AMBAR),
    ("parar", "Parar", "manda esc", "parar", arte.VERMELHO),
    ("pasta", "Pasta", "abre no explorer", "pasta", arte.TEXTO_MORTO),
]

ACOES_SOM = [
    ("sys_menos", "Volume -", "do sistema", "parar", arte.AZUL),
    ("sys_mais", "Volume +", "do sistema", "seguir", arte.AZUL),
    ("sys_mudo", "Mudo", "do sistema", "recusar", arte.VERMELHO),
    ("mic_mudo", "Microfone", "mudo do mic", "recusar", arte.ROXO),
]

ACOES_HOME = [
    ("mic", "Microfone", "muta e desmuta", "recusar", arte.ROXO),
    ("print", "Recorte", "win + shift + s", "pasta", arte.VERDE),
]

TODAS_ACOES = ACOES + ACOES_SOM + ACOES_HOME


def _versao_arte() -> str:
    """Mexer no arte.py invalida o cache em disco inteiro."""
    p = Path(__file__).resolve().parent / "arte.py"
    try:
        return str(int(p.stat().st_mtime))
    except OSError:
        return "0"


def _faixa(valor: float, passo: int = 10) -> int:
    """Valor continuo -> degrau, para nao refazer arte a cada leitura."""
    return int(max(0.0, valor) // passo)


def _h(*partes) -> str:
    return hashlib.sha1("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:10]


class Painel:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.qualidade = int(cfg.get("jpeg_quality", 90))
        self._cache: dict = {}
        self._lock = threading.Lock()
        self._versao = _versao_arte()
        CACHE_DIR.mkdir(exist_ok=True)

        self._ses: list = []
        self._ses_ate = 0.0
        self._ttl = float(cfg.get("sessoes_ttl_s", 1.0))
        self._projs: list = []
        self._apps: list = []
        self._ver: dict = {}        # id da arte -> versao do conteudo
        self._pil: dict = {}        # a imagem em si, para o diff dos remendos

        self.musica = midia.Musica()
        self.musica.comeca()

    # ------------------------------------------------------------- sessoes

    def sessoes(self, forcar: bool = False) -> list:
        """Lista viva, guardada por um segundo, ja com a atividade lida."""
        agora = time.monotonic()
        if not forcar and self._ses and agora < self._ses_ate:
            return self._ses
        ss = sessoes.vivas()
        for s in ss:
            s["_modelo_curto"] = sessoes.modelo_curto(s.get("modelo", ""))
            try:
                a = atividade.ler(s)
                s["_ativ"] = a
                s["_agora"] = a.agora() if s["estado"] == "trabalhando" else ("", "")
                s["_pulso"] = a.pulso()
                s["_arquivos"] = a.tocados(4)
            except Exception:
                s["_ativ"], s["_agora"], s["_pulso"] = None, ("", ""), []
                s["_arquivos"] = []
        self._ses, self._ses_ate = ss, agora + self._ttl
        return ss

    def sessao(self, pid: int):
        for s in self.sessoes():
            if s["pid"] == pid:
                return s
        return None

    def resumo(self) -> str:
        """A linha da barra: o que muda depressa demais para caber num card."""
        ss = self.sessoes()
        if not ss:
            return "nenhuma sessao do claude aberta"
        trab = [s for s in ss if s["estado"] == "trabalhando"]
        if trab:
            s = trab[0]
            ferr, resumo = s.get("_agora") or ("", "")
            if ferr:
                return "{}: {} {}".format(s["nome"][:10], ferr, resumo)[:43]
            return "{} trabalhando".format(len(trab))[:43]
        prontas = sum(1 for s in ss if s["estado"] == "pronta")
        if prontas:
            return "{} pronta{} para voce".format(
                prontas, "s" if prontas > 1 else "")[:43]
        return "{} sessoes paradas".format(len(ss))[:43]

    def estado(self) -> dict:
        """Quais cards estao acesos."""
        d = {"b{}".format(i): s["estado"] == "trabalhando"
             for i, s in enumerate(self.sessoes())}
        for i, a in enumerate(self._apps):
            d["m{}".format(i)] = bool(a.get("mudo"))
        g = som_mod.geral()
        d["sysm"] = bool(g.get("sys_mudo"))
        d["micm"] = bool(g.get("mic_mudo"))
        return d

    # ------------------------------------------------------------- geometria

    @staticmethod
    def tamanho_card(cols: int, rows: int) -> tuple:
        cw = TELA_W // cols
        ch = (TELA_H - BARRA_H) // rows
        return cw - 2 * MARGEM, ch - 2 * MARGEM

    @staticmethod
    def _grade(n: int) -> dict:
        """Grade para n cards. Nunca menos de 3 colunas."""
        if n <= 6:
            return {"cols": 3, "rows": 2}
        if n <= 8:
            return {"cols": 4, "rows": 2}
        if n <= 10:
            return {"cols": 5, "rows": 2}
        return {"cols": 5, "rows": 3}

    # --------------------------------------------------------------- paginas

    def paginas_conhecidas(self) -> list:
        pids = ["home", "claude", "som", "projetos"]
        pids += ["ses/{}".format(s["pid"]) for s in self.sessoes()]
        return pids

    def _envelope(self, pid, titulo, back, grid, cards) -> dict:
        return {"ev": "layout", "page": pid, "title": titulo, "back": back,
                "grid": grid, "buttons": cards}

    def _card(self, bid, art, versao="", art_on="", state_key=""):
        """Registra a versao do conteudo e devolve o card com id de arte fixo."""
        if versao:
            self._ver[art] = versao
            if art_on:
                self._ver[art_on] = versao
        return {"id": bid, "art": art, "art_on": art_on, "state_key": state_key}

    def pagina(self, pid: str):
        if pid == "home":
            return self._home()
        if pid == "claude":
            return self._claude()
        if pid == "som":
            return self._som()
        if pid == "projetos":
            return self._projetos()
        if pid.startswith("ses/"):
            try:
                return self._sessao(int(pid[4:]))
            except ValueError:
                return None
        return None

    def _home(self) -> dict:
        """O menu. Cada card e uma funcao do painel; o Claude e uma delas."""
        ss = self.sessoes()
        trab = sum(1 for s in ss if s["estado"] == "trabalhando")
        prontas = sum(1 for s in ss if s["estado"] == "pronta")
        g = som_mod.geral()

        cards = [
            self._card("claude", "nav:claude",
                       _h(len(ss), trab, prontas)),
            self._card("som", "nav:som",
                       _h(len(som_mod.apps()), _faixa(g.get("sys_vol", 0), 10),
                          _faixa(g.get("mic_vol", 0), 10))),
            self._card("projetos", "nav:projetos",
                       _h(len(sessoes.recentes(limite=12)))),
        ]
        chave_mus = self.musica.chave
        cards.append(self._card("musica", "mus:atual", _h(chave_mus)))
        for bid, _r, _s, _i, _c in ACOES_HOME:
            sk = "micm" if bid == "mic" else ""
            cards.append(self._card(bid, "acao:" + bid, "",
                                    ("acao:" + bid + ":on") if sk else "", sk))

        env = self._envelope("home", "REDEA", "", self._grade(len(cards)), cards)
        env["_musica"] = True
        return env

    def _claude(self) -> dict:
        """As sessoes do Claude Code. Era a home antes; agora e uma funcao."""
        ss = self.sessoes()
        if not ss:
            return self._envelope("claude", "Claude", "home",
                                  {"cols": 3, "rows": 2},
                                  [self._card("nada", "vazio:claude")])
        cards = []
        for i, s in enumerate(ss):
            art = "ses:{}".format(s["pid"])
            cards.append(self._card("ses:{}".format(s["pid"]), art,
                                    self._ver_sessao(s), art + ":on",
                                    "b{}".format(i)))
        return self._envelope("claude", "Claude", "home",
                              self._grade(len(cards)), cards)

    def _projetos(self) -> dict:
        """Abrir o claude num projeto recente, com um toque."""
        abertos = set()
        for s in self.sessoes():
            try:
                abertos.add(Path(s["cwd"]).resolve())
            except OSError:
                continue
        projs = []
        for p in sessoes.recentes(limite=12):
            try:
                if Path(p["cwd"]).resolve() in abertos:
                    continue
            except OSError:
                continue
            projs.append(p)
        self._projs = projs[:10]
        if not self._projs:
            return self._envelope("projetos", "Projetos", "home",
                                  {"cols": 3, "rows": 2},
                                  [self._card("nada", "vazio:projetos")])
        cards = [self._card("proj:{}".format(i), "proj:{}".format(i))
                 for i in range(len(self._projs))]
        return self._envelope("projetos", "Projetos", "home",
                              self._grade(len(cards)), cards)

    def _sessao(self, pid: int):
        """A sessao por dentro: o pedido, o que rodou, o que mexeu, e as acoes."""
        s = self.sessao(pid)
        if not s:
            return None
        a = s.get("_ativ")
        cards = [
            self._card("info", "info:{}".format(pid), self._ver_info(s)),
            self._card("linha", "linha:{}".format(pid),
                       _h(*(n + r[:28] for _x, n, r in (a.ultimas(6) if a else [])))),
            self._card("arqs", "arqs:{}".format(pid),
                       _h(",".join(a.tocados(6) if a else []), s.get("branch", ""))),
        ]
        for bid, _r, _sub, _ic, _c in ACOES:
            cards.append(self._card(bid, "acao:" + bid))
        return self._envelope("ses/{}".format(pid), s["nome"][:22], "claude",
                              self._grade(len(cards)), cards)

    def _som(self) -> dict:
        """O mixer: um card por app com audio, mais o sistema e o microfone."""
        apps = som_mod.apps()
        self._apps = apps
        cards = []
        for i, a in enumerate(apps[:4]):
            art = "som:{}".format(self._id_app(a["exe"]))
            cards.append(self._card("app:{}".format(i), art,
                                    _h(_faixa(a.get("vol", 0), 5), a.get("mudo")),
                                    art + ":on", "m{}".format(i)))
        for bid, _rot, _sub, _ic, _cor in ACOES_SOM:
            sk = {"sys_mudo": "sysm", "mic_mudo": "micm"}.get(bid, "")
            cards.append(self._card(bid, "acao:" + bid, "",
                                    ("acao:" + bid + ":on") if sk else "", sk))
        if not apps:
            cards.insert(0, self._card("nada", "vazio:som"))
        return self._envelope("som", "Som", "home", self._grade(len(cards)), cards)

    # ----------------------------------------------------------------- acoes

    def acao(self, pid: str, bid: str):
        if bid.startswith("ses:"):
            return {"type": "page", "page": "ses/" + bid[4:]}
        if bid in ("claude", "som", "projetos"):
            return {"type": "page", "page": bid}
        if bid in ("info", "linha", "arqs", "nada"):
            return {"type": "nada"}
        if bid == "musica":
            return {"type": "midia", "key": "play_pause"}
        if bid == "mic":
            return {"type": "mudo", "qual": "mic"}
        if bid == "print":
            return {"type": "atalho", "teclas": ["win", "shift", "s"]}

        if bid.startswith("proj:"):
            try:
                i = int(bid[5:])
            except ValueError:
                return None
            if i >= len(self._projs):
                return None
            return {"type": "abrir_claude", "cwd": self._projs[i]["cwd"],
                    "then": "claude"}

        if bid.startswith("app:"):
            try:
                i = int(bid[4:])
            except ValueError:
                return None
            if i >= len(self._apps):
                return None
            return {"type": "app_mudo", "exe": self._apps[i]["exe"]}

        if bid in ("sys_menos", "sys_mais"):
            return {"type": "volume", "qual": "sys",
                    "delta": -5 if bid == "sys_menos" else 5}
        if bid == "sys_mudo":
            return {"type": "mudo", "qual": "sys"}
        if bid == "mic_mudo":
            return {"type": "mudo", "qual": "mic"}

        if pid.startswith("ses/"):
            try:
                alvo = int(pid[4:])
            except ValueError:
                return None
            if bid in ("focar", "seguir", "aprovar", "parar", "pasta"):
                return {"type": bid, "pid": alvo}
        return None

    # ------------------------------------------------------------ versoes

    def _ver_sessao(self, s: dict) -> str:
        ferr, resumo = s.get("_agora") or ("", "")
        return _h(s.get("nome", ""), s.get("titulo", ""), s.get("_modelo_curto", ""),
                  s.get("effort", ""),
                  "parada" if s["estado"] == "parada" else "viva",
                  _faixa((s.get("ctx") or 0) * 100.0 / max(1, s.get("janela") or 1)),
                  ferr, resumo[:34], ",".join(s.get("_arquivos") or []),
                  ",".join(str(min(9, v)) for v in (s.get("_pulso") or [])))

    def _ver_info(self, s: dict) -> str:
        return _h(s.get("titulo", ""), s.get("prompt", ""), s.get("branch", ""),
                  s.get("permissao", ""), s.get("_modelo_curto", ""),
                  s.get("effort", ""), s["estado"], (s.get("turno_ms") or 0) // 1000)

    @staticmethod
    def _id_app(exe: str) -> str:
        return exe.replace(".", "_")[:20]

    def versao(self, art: str) -> str:
        return self._ver.get(art, "")

    # ------------------------------------------------------------------ arte

    def artes_da_pagina(self, pid: str) -> list:
        """[(id, w, h, jpeg, versao)] de tudo que a pagina precisa desenhar."""
        pag = self.pagina(pid)
        if not pag:
            return []
        w, h = self.tamanho_card(pag["grid"]["cols"], pag["grid"]["rows"])
        saida = []
        for b in pag["buttons"]:
            for chave in (b["art"], b.get("art_on") or ""):
                if not chave:
                    continue
                dados = self.arte(chave, w, h)
                if dados:
                    saida.append((chave, w, h, dados, self.versao(chave)))
        return saida

    def _caminho_cache(self, cache_id: str) -> Path:
        h = hashlib.sha1((cache_id + "|" + self._versao).encode()).hexdigest()[:20]
        return CACHE_DIR / (h + ".jpg")

    def arte(self, chave: str, w: int, h: int):
        viva = chave.startswith(VIVAS)
        cache_id = "{}@{}x{}#{}".format(chave, w, h, self.versao(chave))
        if cache_id in self._cache:
            return self._cache[cache_id]

        arq = self._caminho_cache(cache_id)
        if not viva and arq.exists():
            dados = arq.read_bytes()
            self._cache[cache_id] = dados
            return dados

        with self._lock:
            if cache_id in self._cache:
                return self._cache[cache_id]
            try:
                img = self._render(chave, w, h)
            except Exception as e:
                print("[arte] {}: {}".format(chave, e))
                img = None
            dados = arte.para_jpeg(img, self.qualidade) if img is not None else None
            # so as versoes vivas mais novas ficam na memoria: sem isso o cache
            # cresce um card a cada ferramenta que uma sessao roda
            if viva:
                prefixo = "{}@{}x{}#".format(chave, w, h)
                for k in [k for k in self._cache if k.startswith(prefixo)]:
                    del self._cache[k]
                for k in [k for k in self._pil if k.startswith(prefixo)]:
                    del self._pil[k]
                if img is not None:
                    self._pil[cache_id] = img
            self._cache[cache_id] = dados
            if dados and not viva:
                try:
                    arq.write_bytes(dados)
                except OSError:
                    pass
            return dados

    def imagem(self, chave: str, w: int, h: int):
        """A imagem da versao atual, para o diff dos remendos.

        Guardada junto com o JPEG em `arte()`; se nao estiver la (veio do cache
        em disco, por exemplo), desenha de novo - custa os mesmos 15 ms.
        """
        cache_id = "{}@{}x{}#{}".format(chave, w, h, self.versao(chave))
        img = self._pil.get(cache_id)
        if img is not None:
            return img
        try:
            img = self._render(chave, w, h)
        except Exception:
            return None
        if img is not None:
            self._pil[cache_id] = img
        return img

    def _render(self, chave: str, w: int, h: int):
        aceso = chave.endswith(":on")
        base = chave[:-3] if aceso else chave

        if base.startswith("ses:"):
            s = self.sessao(int(base[4:]))
            if not s:
                return None
            if aceso:
                s = dict(s, estado="trabalhando")
            elif s["estado"] == "trabalhando":
                s = dict(s, estado="pronta", _agora=("", ""))
            return arte.card_sessao(w, h, s, aceso)

        if base.startswith("info:"):
            s = self.sessao(int(base[5:]))
            return arte.card_info(w, h, s) if s else None

        if base.startswith("linha:"):
            s = self.sessao(int(base[6:]))
            a = s.get("_ativ") if s else None
            return arte.card_timeline(w, h, a.ultimas(6) if a else [])

        if base.startswith("arqs:"):
            s = self.sessao(int(base[5:]))
            a = s.get("_ativ") if s else None
            return arte.card_arquivos(w, h, a.tocados(6) if a else [],
                                      s.get("branch", "") if s else "",
                                      a.turno_medio() if a else 0.0)

        if base.startswith("acao:"):
            bid = base[5:]
            for i, rot, sub, ic, cor in TODAS_ACOES:
                if i == bid:
                    return arte.card_acao(w, h, rot, sub, ic, cor, aceso)
            return None

        if base.startswith("proj:"):
            i = int(base[5:])
            if i >= len(self._projs):
                return None
            return arte.card_projeto(w, h, self._projs[i]["nome"],
                                     CORES_PROJ[i % len(CORES_PROJ)])

        if base.startswith("som:"):
            alvo = base[4:]
            for a in self._apps:
                if self._id_app(a["exe"]) == alvo:
                    return arte.card_app_som(w, h, a, aceso)
            return None

        if base == "nav:claude":
            ss = self.sessoes()
            trab = sum(1 for s in ss if s["estado"] == "trabalhando")
            prontas = sum(1 for s in ss if s["estado"] == "pronta")
            if trab:
                sub, cor = ("{} trabalhando".format(trab), arte.LARANJA)
            elif prontas:
                sub, cor = ("{} esperando voce".format(prontas), arte.VERDE)
            else:
                sub, cor = ("nenhuma trabalhando", arte.TEXTO_MORTO)
            linhas = []
            for s in ss[:3]:
                c = arte.ESTADOS.get(s["estado"], (arte.VERDE, ""))[0]
                linhas.append((s["nome"][:14],
                               min(1.0, (s.get("ctx") or 0) / max(1, s.get("janela") or 1)),
                               c))
            return arte.card_navegar(w, h, "Claude", sub, "raio", cor,
                                     str(len(ss)), linhas)

        if base == "nav:som":
            apps = som_mod.apps()
            g = som_mod.geral()
            linhas = [("sistema", g.get("sys_vol", 0) / 100.0, arte.AZUL),
                      ("microfone", g.get("mic_vol", 0) / 100.0, arte.ROXO)]
            return arte.card_navegar(
                w, h, "Som",
                "{} app{} com audio".format(len(apps), "s" if len(apps) != 1 else ""),
                "volume", arte.AZUL, "{}".format(g.get("sys_vol", 0)), linhas)

        if base == "nav:projetos":
            n = len(sessoes.recentes(limite=12))
            return arte.card_navegar(w, h, "Projetos",
                                     "{} pastas recentes".format(n), "mais",
                                     arte.ROXO, str(n))

        if base.startswith("mus:"):
            _chave, e = self.musica.instantanea()
            if not e.get("titulo"):
                return arte.card_vazio(w, h, "Nada tocando", "")
            return arte.card_musica(w, h, e.get("capa"), e["titulo"],
                                    e.get("artista", ""), e.get("tocando", True))

        if base == "vazio:claude":
            return arte.card_vazio(w, h, "Nenhuma sessao",
                                   "abra o claude em algum projeto")
        if base == "vazio:som":
            return arte.card_vazio(w, h, "Ninguem tocando", "nenhum app com audio")
        if base == "vazio:projetos":
            return arte.card_vazio(w, h, "Nada recente", "")
        return None

    def pre_gerar(self) -> None:
        """Desenha a arte de todas as paginas. Roda numa thread no arranque."""
        for pid in self.paginas_conhecidas():
            pag = self.pagina(pid)
            if not pag:
                continue
            w, h = self.tamanho_card(pag["grid"]["cols"], pag["grid"]["rows"])
            for b in pag["buttons"]:
                for chave in (b["art"], b.get("art_on") or ""):
                    if chave:
                        self.arte(chave, w, h)
