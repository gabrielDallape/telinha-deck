"""
Monta as paginas do painel, a arte de cada botao, e resolve o que cada toque faz.

A tela nao sabe nada sobre apps, projetos, musica ou clima: ela pede uma pagina
por id, estampa os bitmaps que chegam e devolve o id do botao tocado. Todo o
conteudo E todo o visual moram aqui - o que deixa o painel crescer, e o visual
mudar, sem tocar no firmware.

    home  ->  dev  --toque--> abre o terminal do projeto com o Claude rodando

Paginas fixas vem do config.json. Paginas geradas (hoje so `dev`) sao montadas
na hora a partir do que existe no disco.

CARDS VIVOS. Um botao com `live` (relogio, clima, musica, foco), com `nivel_de`
(o SOM com o volume) ou que conta projetos (o Claude) tem id de arte FIXO - o
proprio id do botao - e uma VERSAO, que muda quando o desenho tem de mudar. A
pagina devolve `_vivos = {id_da_arte: versao}`; a Ligacao compara com o que a
placa tem e manda a arte nova no lugar, sem redesenhar a pagina. Arte viva nao
vai para o cache em disco: fica so a ultima versao em memoria.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import arte
import midia
import sons
import projetos as projetos_mod
import vivos

# Tem de casar com o firmware (telinha_p4.ino). Daqui sai o tamanho exato da arte
# de cada botao, e e por isso que o PC pode compor o botao inteiro em vez de
# mandar so o icone.
TELA_W, TELA_H, BARRA_H, MARGEM = 1280, 720, 72, 8


CACHE_DIR = Path(__file__).resolve().parent / "cache"


def _idade(segundos: float) -> str:
    """'ha 2 h', 'ha 3 d': em ASCII, sem acento, e em degraus grossos de
    proposito - o texto entra no id da arte, e id novo e card remandado."""
    if segundos < 3600:
        return "agora"
    if segundos < 86400:
        return f"ha {int(segundos // 3600)} h"
    if segundos < 86400 * 60:
        return f"ha {int(segundos // 86400)} d"
    return f"ha {int(segundos // (86400 * 30))} meses"


def info_projeto(p: Path) -> dict:
    """Branch e idade lidos do disco por alguns stats: nada que passe de ms.

    A idade e o mais novo entre a pasta, o que esta direto nela e o index do
    git - salvar um arquivo em `agent/` nao mexe no mtime da raiz, mas um
    commit ou um `git add` mexe no index.
    """
    branch = ""
    try:
        head = (p / ".git" / "HEAD").read_text(errors="ignore").strip()
        branch = head.rsplit("/", 1)[-1] if head.startswith("ref:") else head[:7]
    except OSError:
        pass
    mt = 0.0
    candidatos = [p, p / ".git" / "index", p / ".git" / "HEAD"]
    try:
        candidatos += [f for _, f in zip(range(60), p.iterdir())]
    except OSError:
        pass
    for f in candidatos:
        try:
            mt = max(mt, f.stat().st_mtime)
        except OSError:
            pass
    return {"branch": branch, "idade": _idade(time.time() - mt) if mt else ""}


def _versao_arte() -> str:
    """Assinatura do codigo de desenho: mexer no arte.py invalida o cache todo."""
    partes = []
    for nome in ("arte.py", "icones.py"):
        p = Path(__file__).resolve().parent / nome
        partes.append(str(int(p.stat().st_mtime)) if p.exists() else "0")
    return "-".join(partes)


class Painel:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.qualidade = int(cfg.get("jpeg_quality", 90))
        self._cache: dict = {}      # id da arte -> bytes JPEG (arte fixa)
        self._vivo_cache: dict = {} # (id, w, h) -> (versao, bytes) - so a ultima
        self._lock = threading.Lock()
        CACHE_DIR.mkdir(exist_ok=True)
        # O que esta tocando. Vive numa thread propria: a consulta a SMTC custa
        # centenas de ms e nao pode entrar no caminho do dedo.
        self.musica = midia.Musica()
        self.musica.comeca()
        self.projetos = projetos_mod.Projetos(cfg)
        # As outras fontes vivas. O clima le a rede numa thread; relogio e foco
        # sao calculo puro.
        self.relogio = vivos.Relogio()
        self.clima = vivos.Clima(cfg.get("clima"))
        self.clima.comeca()
        self.foco = vivos.Foco(cfg.get("foco_min", 25))
        self.agenda = vivos.Agenda(cfg.get("agenda"))
        self.agenda.comeca()
        # So liga o que alguma pagina usa: a leitura de CPU (psutil) custa CPU
        # o dia inteiro e nao faz sentido rodar sem um card para mostrar.
        self.sistema = vivos.Sistema()
        if self._alguem_usa("sistema"):
            self.sistema.comeca()
        # Niveis que entram na arte (ex.: {"sys_vol": 62}). Quem preenche e o
        # agente, a partir do `state`, com debounce.
        self.niveis: dict = {}
        # Botoes de paginas geradas (`gerar`): o id nao esta no config, entao
        # arte e acao acham o spec aqui.
        self._gerados: dict = {}
        # OBS so liga se o pacote dele estiver ativo: sem isso, uma thread
        # procurando a janela do OBS o dia inteiro em PC que nem tem OBS.
        self.obs = None
        if "obs" in self.cfg.get("pages", {}):
            import obs as obs_mod
            self.obs = obs_mod.Obs(cfg.get("obs")).comeca()

    def _alguem_usa(self, live: str) -> bool:
        return any(b.get("live") == live
                   for pg in self.cfg.get("pages", {}).values()
                   for b in pg.get("buttons", []))

    # ------------------------------------------------------- cache em disco

    def _caminho_cache(self, cache_id: str) -> Path:
        h = hashlib.sha1(f"{cache_id}|{_versao_arte()}".encode()).hexdigest()[:20]
        return CACHE_DIR / f"{h}.jpg"

    def paginas_conhecidas(self) -> list:
        """Paginas navegaveis, na ordem em que vale a pena precarregar.

        `dev` tem de entrar aqui por dois motivos: entra na precarga (senao os
        cards de projeto sao pagos no dedo) E o retry de arte corrompida
        consegue achar de que pagina a chave veio - sem isso um `imgbad` num
        card de projeto nao achava a pagina e o card nunca era remandado.
        """
        pids = list(self.cfg.get("pages", {}))
        if self.projetos.itens():
            pids.append("dev")
        return pids

    def pre_gerar(self, aviso=None) -> None:
        """Renderiza a arte de TODAS as paginas. Feito numa thread no arranque.

        Sem isto, os ~70 ms por card viravam quase um segundo de espera no
        momento do toque, justamente quando o usuario esta olhando a tela.
        """
        for pid in self.paginas_conhecidas():
            self.artes_da_pagina(pid)
            if aviso:
                aviso(pid)

    # ------------------------------------------------------------- geometria

    @staticmethod
    def tamanho_botao(cols: int, rows: int) -> tuple:
        cw = TELA_W // cols
        ch = (TELA_H - BARRA_H) // rows
        return cw - 2 * MARGEM, ch - 2 * MARGEM

    @staticmethod
    def _grade(n: int) -> dict:
        """Grade para n botoes. Nunca menos de 3 colunas.

        Uma grade 2x2 para dois botoes daria cards de 624x308, e cada sprite
        desses come 384 KB de PSRAM - por pagina que talvez nunca seja aberta.
        Manter 3x2 padroniza o tamanho da arte (o que ajuda o cache) e deixa
        espaco vazio em vez de card gigante.
        """
        if n <= 6:
            return {"cols": 3, "rows": 2}
        if n <= 8:
            return {"cols": 4, "rows": 2}
        if n <= 10:
            return {"cols": 5, "rows": 2}
        return {"cols": 5, "rows": 3}

    # ----------------------------------------------------------- cards vivos

    def _spec(self, bid: str) -> dict | None:
        if bid in self._gerados:
            return self._gerados[bid]
        for pagina in self.cfg.get("pages", {}).values():
            for b in pagina.get("buttons", []):
                if b.get("id") == bid:
                    return b
        return None

    def versao_viva(self, spec: dict) -> str | None:
        """Versao do card, ou None se ele e arte fixa."""
        live = spec.get("live")
        partes = []
        if live == "musica":
            # o player anda com o progresso (degraus de 10 s); os outros cards
            # de musica so mudam com a faixa e com tocando/pausado
            fina = spec.get("estilo") == "player"
            partes.append((self.musica.chave_fina if fina else self.musica.chave) or "vazio")
        elif live in ("relogio", "clima", "foco", "agenda", "sistema"):
            partes.append(getattr(self, live).versao)
        if spec.get("nivel_de"):
            v = self.niveis.get(spec["nivel_de"])
            partes.append(str(int(round(v / 5.0) * 5)) if v is not None else "x")
        if spec.get("type") == "page" and spec.get("page") == "dev":
            partes.append(f"n{len(self.projetos.itens())}")
        return "|".join(partes) if partes else None

    def texto_barra(self) -> str:
        """O que vai escrito na barra do topo: a hora e a proxima reuniao de hoje.

        Texto puro, 90 bytes, sem JPEG - nao tem como chegar corrompido nem
        piscar. A fonte da barra e ASCII: sem acento.
        """
        txt = time.strftime("%H:%M")
        for e in self.agenda.proximos(1):
            if e.get("dia_inteiro") or not e["inicio"].date() == __import__("datetime").datetime.now().astimezone().date():
                break
            txt += f"   {e['inicio'].strftime('%H:%M')} {arte._ascii(e['titulo'])[:24]}"
        return txt[:46]

    # --------------------------------------------------------------- paginas

    def pagina(self, pid: str) -> dict | None:
        if pid in self.cfg.get("pages", {}):
            if self.cfg["pages"][pid].get("gerar"):
                return self._pagina_gerada(pid)
            return self._pagina_fixa(pid)
        if pid == "dev":
            return self._pagina_dev()
        return None

    def _envelope(self, pid, title, back, grid, botoes) -> dict:
        return {"ev": "layout", "page": pid, "title": title, "back": back,
                "grid": grid, "buttons": botoes}

    def _pagina_fixa(self, pid: str, gerados: list | None = None) -> dict:
        p = self.cfg["pages"][pid]
        specs = (gerados or []) + [b for b in p.get("buttons", []) if not b.get("_off")]
        grid = p.get("grid") or self._grade(len(specs))
        botoes, vivos_ = [], {}
        for b in specs:
            botoes.append({
                "id": b["id"],
                "art": b["id"],
                "art_on": (b["id"] + ":on") if b.get("state_key") else "",
                "state_key": b.get("state_key", ""),
            })
            versao = self.versao_viva(b)
            if versao is not None:
                vivos_[b["id"]] = versao
        env = self._envelope(pid, p.get("title", ""), p.get("back", ""), grid, botoes)
        env["_vivos"] = vivos_
        return env

    def _pagina_gerada(self, pid: str) -> dict:
        """Pagina cujos botoes vem de algo vivo: os sons de uma pasta, as cenas
        do OBS. Os botoes fixos da pagina (`buttons`) vem depois dos gerados.
        O conteudo e lido a cada abertura - soltou um mp3 na pasta, ele aparece
        na proxima vez que a pagina abrir."""
        p = self.cfg["pages"][pid]
        fixos = [b for b in p.get("buttons", []) if not b.get("_off")]
        cabe = 15 - len(fixos)
        try:
            gerados = self._gerar(p)[:max(0, cabe)]
        except Exception as e:
            print(f"[pagina] {pid}: {e}")
            gerados = []
        for b in gerados:
            self._gerados[b["id"]] = b
        return self._pagina_fixa(pid, gerados)

    def _gerar(self, p: dict) -> list:
        tipo, pac = p["gerar"], p.get("_pacote", "")
        cores = p.get("cores") or ["#E5484D", "#F5A524", "#30A46C", "#3E63DD",
                                   "#8E4EC6", "#12A594", "#D6409F", "#F76B15"]
        if tipo == "sons":
            pastas = [Path(p.get("_dir", ".")) / p.get("pasta", "sons")]
            extra = (self.cfg.get("sons") or {}).get("pasta")
            if extra:
                pastas.insert(0, Path(extra))
            saida = []
            for k, arq in enumerate(sons.listar(pastas)):
                chave = hashlib.sha1(str(arq).encode()).hexdigest()[:8]
                saida.append({**(p.get("modelo") or {}),
                              "id": f"{pac}.som:{chave}", "label": arq.stem[:18],
                              "icon": (p.get("modelo") or {}).get("icon", "waveform"),
                              "color": cores[k % len(cores)],
                              "type": "som", "arquivo": str(arq)})
            return saida
        if tipo == "obs_cenas":
            if not self.obs:
                return []
            import obs as obs_mod
            return [{"id": f"{pac}.cena:{obs_mod.chave_cena(nome)[5:]}",
                     "label": nome[:18], "icon": "film", "color": cores[k % len(cores)],
                     "peso": "controle", "label_on": nome[:18],
                     "sub": "", "state_key": obs_mod.chave_cena(nome),
                     "type": "obs", "op": "cena", "cena": nome}
                    for k, nome in enumerate(self.obs.cenas)]
        raise ValueError(f"gerar desconhecido: {tipo!r}")

    def _pagina_dev(self) -> dict:
        """Os projetos. Um toque abre o terminal na pasta com o Claude rodando."""
        itens = self.projetos.itens()
        botoes = []
        for pid, _nome, caminho, _cor in itens:
            # branch e idade entram no id: mudou o branch ou passou uma hora, o
            # card e outro e a placa recebe um novo. O id do BOTAO nao muda.
            info = info_projeto(caminho)
            marca = hashlib.sha1(f"{info['branch']}|{info['idade']}".encode()
                                 ).hexdigest()[:6]
            botoes.append({"id": f"proj:{pid}", "art": f"proj:{pid}:{marca}",
                           "art_on": "", "state_key": ""})
        if not botoes:
            return self._envelope("dev", "Nenhum projeto", "home",
                                  {"cols": 1, "rows": 1}, [])
        return self._envelope("dev", "Projetos", "home",
                              self._grade(len(botoes)), botoes)

    # ----------------------------------------------------------------- acoes

    def acao(self, pid: str, bid: str) -> dict | None:
        if bid.startswith("proj:"):
            return {"type": "abrir_projeto", "projeto": bid[5:]}
        p = self.cfg.get("pages", {}).get(pid)
        if p:
            for b in p.get("buttons", []):
                if b.get("id") == bid:
                    return b
        return self._gerados.get(bid)

    # ------------------------------------------------------------------ arte

    def artes_da_pagina(self, pid: str) -> list:
        """[(id_da_arte, w, h, jpeg, versao)] de tudo que a pagina desenha.

        `versao` e None para arte fixa; para card vivo e a versao que estes
        bytes representam - a Ligacao guarda isso como "o que a placa tem".
        """
        pag = self.pagina(pid)
        if not pag:
            return []
        w, h = self.tamanho_botao(pag["grid"]["cols"], pag["grid"]["rows"])
        vivos_ = pag.get("_vivos", {})
        saida = []
        for b in pag["buttons"]:
            for chave in (b["art"], b.get("art_on") or ""):
                if not chave:
                    continue
                versao = vivos_.get(chave)
                dados = self.arte(chave, w, h, pid, versao)
                if dados:
                    saida.append((chave, w, h, dados, versao))
        return saida

    def arte(self, chave: str, w: int, h: int, pid: str = "",
             versao: str | None = None) -> bytes | None:
        if versao is None:
            spec = self._spec(chave)
            if spec is not None:
                versao = self.versao_viva(spec)

        if versao is not None:
            # card vivo: so a ultima versao, so em memoria
            k = (chave, w, h)
            guardado = self._vivo_cache.get(k)
            if guardado and guardado[0] == versao:
                return guardado[1]
            with self._lock:
                guardado = self._vivo_cache.get(k)
                if guardado and guardado[0] == versao:
                    return guardado[1]
                dados = self._renderiza(chave, w, h)
                if dados:
                    self._vivo_cache[k] = (versao, dados)
                return dados

        # o spec entra na chave: sem ele, mudar cor/peso/rotulo no config.json
        # seguia servindo a arte velha do disco (so o arte.py invalidava)
        spec = self._spec(chave.removesuffix(":on"))
        assinatura = json.dumps(spec, sort_keys=True, ensure_ascii=False) if spec else ""
        cache_id = f"{chave}@{w}x{h}|{assinatura}"
        if cache_id in self._cache:
            return self._cache[cache_id]
        arq = self._caminho_cache(cache_id)
        if arq.exists():
            dados = arq.read_bytes()
            self._cache[cache_id] = dados
            return dados

        # o lock serializa o render: a thread de precarregamento e o pedido do
        # usuario podem querer a MESMA arte, e renderizar duas vezes e desperdicio
        with self._lock:
            if cache_id in self._cache:
                return self._cache[cache_id]
            dados = self._renderiza(chave, w, h)
            self._cache[cache_id] = dados
            if dados:
                try:
                    arq.write_bytes(dados)
                except OSError:
                    pass
            return dados

    def _renderiza(self, chave: str, w: int, h: int) -> bytes | None:
        try:
            img = self._render(chave, w, h)
        except Exception as e:
            print(f"[arte] {chave}: {e}")
            img = None
        return arte.para_jpeg(img, self.qualidade) if img is not None else None

    def _render(self, chave: str, w: int, h: int):
        aceso = chave.endswith(":on")
        base = chave[:-3] if aceso else chave

        if base.startswith("proj:"):
            alvo = base.split(":")[1]
            for pid, nome, caminho, _cor in self.projetos.itens():
                if pid == alvo:
                    info = info_projeto(caminho)
                    return arte.botao_projeto(w, h, nome, arte.cor_projeto(nome),
                                              branch=info["branch"],
                                              idade=info["idade"])
            return None

        spec = self._spec(base)
        if spec is None:
            return None
        live = spec.get("live")

        if live == "musica" and not aceso:
            _chave, e = self.musica.instantanea()
            estilo = spec.get("estilo", "")
            if estilo == "player":
                pos, dur = self.musica.posicao(e)
                return arte.botao_player(w, h, e.get("capa"), e.get("titulo", ""),
                                         e.get("artista", ""), e.get("tocando", False),
                                         pos, dur, e.get("app", ""))
            if estilo == "controle":
                tocando = bool(e.get("titulo")) and e.get("tocando", False)
                spec = {**spec, "icon": "pause" if tocando else "play",
                        "label": "Pausar" if tocando else "Tocar"}
            elif e.get("titulo"):
                return arte.botao_musica(w, h, e.get("capa"), e["titulo"],
                                         e.get("artista", ""), e.get("tocando", True),
                                         e.get("app", ""))
            else:
                spec = {**spec, "icon": spec.get("icon", "play"),
                        "label": spec.get("label", "Play")}
        elif live == "relogio":
            if spec.get("estilo") == "grande":
                return arte.botao_relogio_grande(w, h, **self.relogio.dados())
            return arte.botao_relogio(w, h, **self.relogio.dados())
        elif live == "clima":
            if spec.get("estilo") == "grande":
                return arte.botao_clima_grande(w, h, self.clima.dados())
            return arte.botao_clima(w, h, self.clima.dados())
        elif live == "foco":
            return arte.botao_foco(w, h, self.foco.dados())
        elif live == "agenda":
            return arte.botao_agenda(w, h, self.agenda.dados())
        elif live == "sistema":
            d = self.sistema.dados()
            return arte.botao_medidor(w, h, "CPU", d["cpu"], "%", d["cpu"],
                                      f"RAM {d['ram']:.0f}%  ·  {d['ram_gb']:.1f} de {d['ram_total_gb']:.0f} GB")

        spec = dict(spec)
        if spec.get("nivel_de"):
            v = self.niveis.get(spec["nivel_de"])
            if v is not None:
                spec["nivel"] = int(v)
        if spec.get("type") == "page" and spec.get("page") == "dev" and spec.get("sub") == "{projetos}":
            # so quem pedir no config ve a contagem; a home e so icone
            n = len(self.projetos.itens())
            spec["sub"] = f"{n} projeto" + ("" if n == 1 else "s")
        return arte.botao_icone(w, h, spec, aceso)
