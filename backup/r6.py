"""
Ponte com o projeto r6-tatica: navegar mapa -> bomb -> tatica e mandar pro time.

Como a escrita funciona (lido de lib/supabase.ts e app/api/sala/route.ts do
projeto): nao existe service_role em lugar nenhum. As escritas sao funcoes
SECURITY DEFINER no Postgres que exigem o PIN do time. Entao o JOQUEI chama a
MESMA RPC que o site chama - `mandar_tatica` com p_pin - e nao precisa do Next
rodando, nem de cookie, nem de sessao.

As credenciais sao lidas do .env.local do proprio projeto r6, nunca copiadas para
dentro do JOQUEI: um segredo tem um dono so, e o dono e aquele repositorio.

A FONTE DOS NOMES E O data/mapas.ts, NAO o taticas.json. O campo `mapaPtBr` das
taticas vem da extracao dos PDFs e traz nome de BOMB no lugar do mapa - foi por
isso que o Border apareceu como "Alfandega", que e um bomb dele. O catalogo
tambem e a unica fonte que lista mapa e bomb SEM tatica nenhuma, e ver o que o
time ainda nao cobriu e metade da utilidade da tela.

Os dois arquivos sao relidos quando mudam no disco: o r6-tatica e editado em
paralelo, e servir catalogo velho e pior do que nao servir nada.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

import requests

TIMEOUT = 6


def _ler_env(projeto: Path) -> dict:
    env = {}
    for nome in (".env.local", ".env"):
        p = projeto / nome
        if not p.exists():
            continue
        for linha in p.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            k, v = linha.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def sem_acento(s: str) -> str:
    """As fontes da tela cobrem ASCII, entao 'Chale' em vez de tofu."""
    return "".join(c for c in unicodedata.normalize("NFD", str(s))
                   if unicodedata.category(c) != "Mn")


def _ts_para_json(texto: str, nome_const: str = "MAPAS"):
    """Le um array literal de um arquivo .ts sem precisar de Node.

    So aguenta literais simples - que e o caso do data/mapas.ts. Se algum dia
    deixar de aguentar, devolve None e quem chama cai no plano B em vez de
    quebrar o painel inteiro.
    """
    try:
        i = texto.index(nome_const)
        # Pula a anotacao de tipo: em "MAPAS: Mapa[] = [", o primeiro "[" e o do
        # tipo, nao o do array. O "=" e a fronteira confiavel.
        i = texto.index("=", i)
        i = texto.index("[", i)
        nivel, fim, na_str, aspa = 0, -1, False, ""
        for k in range(i, len(texto)):
            c = texto[k]
            if na_str:
                if c == "\\":
                    continue
                if c == aspa:
                    na_str = False
                continue
            if c in "\"'":
                na_str, aspa = True, c
            elif c == "[":
                nivel += 1
            elif c == "]":
                nivel -= 1
                if nivel == 0:
                    fim = k
                    break
        if fim < 0:
            return None
        bloco = texto[i:fim + 1]
        bloco = re.sub(r"/\*.*?\*/", "", bloco, flags=re.S)
        bloco = re.sub(r"//[^\n]*", "", bloco)
        bloco = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', bloco)
        bloco = re.sub(r",(\s*[}\]])", r"\1", bloco)
        return json.loads(bloco)
    except Exception:
        return None


class R6:
    def __init__(self, caminho_projeto: str):
        self.projeto = Path(caminho_projeto)
        self.env = _ler_env(self.projeto)
        self.url = self.env.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
        self.anon = self.env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
        self.pin = self.env.get("PIN_TIME", "")
        self._taticas: list = []
        self._mapas: list = []
        self._mtimes = (0.0, 0.0)
        self._no_ar_val: str | None = None
        self._no_ar_ate = 0.0

    # ------------------------------------------------------------- catalogo

    @property
    def _arq_taticas(self) -> Path:
        return self.projeto / "data" / "taticas.json"

    @property
    def _arq_mapas(self) -> Path:
        return self.projeto / "data" / "mapas.ts"

    def assinatura(self) -> tuple:
        """mtime dos dois arquivos de dados. Serve de chave de cache tambem."""
        def m(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0
        return (m(self._arq_taticas), m(self._arq_mapas))

    def _carregar(self) -> None:
        atual = self.assinatura()
        if atual == self._mtimes and self._mapas:
            return
        self._mtimes = atual

        try:
            self._taticas = json.loads(self._arq_taticas.read_text(encoding="utf-8"))
        except Exception:
            self._taticas = []

        cat = None
        if self._arq_mapas.exists():
            cat = _ts_para_json(self._arq_mapas.read_text(encoding="utf-8"))
        if cat:
            self._mapas = cat
        else:
            # Plano B: catalogo deduzido das taticas. Perde mapas e bombs vazios
            # e volta a usar o mapaPtBr, que pode trazer nome de bomb.
            vistos = {}
            for t in self._taticas:
                mid = t.get("mapaId", "")
                if mid and mid not in vistos:
                    vistos[mid] = {"id": mid, "nome": t.get("mapaPtBr") or mid,
                                   "capa": None, "bombs": []}
            self._mapas = list(vistos.values())
            print("[r6] nao consegui ler data/mapas.ts; usando nomes das taticas")

        print(f"[r6] catalogo: {len(self._mapas)} mapas, "
              f"{sum(len(m.get('bombs') or []) for m in self._mapas)} bombs, "
              f"{len(self._taticas)} taticas")

    @property
    def ok(self) -> bool:
        self._carregar()
        return bool(self.url and self.anon and self._mapas)

    @property
    def taticas(self) -> list:
        self._carregar()
        return self._taticas

    # ------------------------------------------------------------ navegacao

    def mapas(self) -> list:
        """Todos os mapas do pool: [(id, nome, n_taticas)] - inclusive com zero.

        Mapa vazio aparece de proposito: e assim que se ve o que o time ainda
        nao cobriu, e e o que o catalogo do site faz.
        """
        self._carregar()
        conta = {}
        for t in self._taticas:
            mid = t.get("mapaId", "")
            conta[mid] = conta.get(mid, 0) + 1
        return [(m["id"], sem_acento(m.get("nome") or m["id"]), conta.get(m["id"], 0))
                for m in self._mapas]

    def _mapa(self, mapa_id: str) -> dict | None:
        self._carregar()
        return next((m for m in self._mapas if m.get("id") == mapa_id), None)

    def nome_mapa(self, mapa_id: str) -> str:
        m = self._mapa(mapa_id)
        return sem_acento(m.get("nome") or mapa_id) if m else mapa_id

    def bombs(self, mapa_id: str) -> list:
        """[(bombId, nome, andar, n_taticas)] do mapa, na ordem do catalogo.

        No fim entra um "Sem bomb" quando ha taticas ainda nao atribuidas - o
        README do site conta que 15 estao nessa situacao.
        """
        m = self._mapa(mapa_id)
        conta = {}
        for t in self.taticas:
            if t.get("mapaId") != mapa_id:
                continue
            b = t.get("bombId") or ""
            conta[b] = conta.get(b, 0) + 1

        saida = []
        for b in (m.get("bombs") or []) if m else []:
            saida.append((b["id"],
                          sem_acento(b.get("apelido") or b.get("nome") or b["id"]),
                          sem_acento(b.get("andar") or ""),
                          conta.get(b["id"], 0)))
        if conta.get("", 0):
            saida.append((f"{mapa_id}::sembomb", "Sem bomb", "a definir", conta[""]))
        return saida

    def nome_bomb(self, mapa_id: str, bomb_id: str) -> str:
        if bomb_id.endswith("::sembomb"):
            return "Sem bomb"
        m = self._mapa(mapa_id)
        for b in (m.get("bombs") or []) if m else []:
            if b.get("id") == bomb_id:
                return sem_acento(b.get("apelido") or b.get("nome") or bomb_id)
        return bomb_id

    def andar_bomb(self, mapa_id: str, bomb_id: str) -> str:
        if bomb_id.endswith("::sembomb"):
            return "a definir"
        m = self._mapa(mapa_id)
        for b in (m.get("bombs") or []) if m else []:
            if b.get("id") == bomb_id:
                return sem_acento(b.get("andar") or "")
        return ""

    def taticas_do_bomb(self, mapa_id: str, bomb_id: str) -> list:
        """[(taticaId, nome, lado)] daquele bomb."""
        solto = bomb_id.endswith("::sembomb")
        saida = []
        for t in self.taticas:
            if t.get("mapaId") != mapa_id:
                continue
            bid = t.get("bombId") or ""
            if (solto and bid) or (not solto and bid != bomb_id):
                continue
            saida.append((t["id"], sem_acento(t.get("nome", t["id"])), t.get("lado", "")))
        return saida

    # ----------------------------------------------------------------- arte

    def _publico(self, url: str):
        if not url:
            return None
        p = self.projeto / "public" / str(url).lstrip("/")
        return p if p.exists() else None

    def foto_do_mapa(self, mapa_id: str):
        """A capa que o catalogo aponta - sem chute por nome de arquivo."""
        m = self._mapa(mapa_id)
        if m and m.get("capa"):
            p = self._publico(m["capa"])
            if p:
                return p
        pasta = self.projeto / "public" / "mapas"
        if pasta.is_dir():
            for p in sorted(pasta.glob("*.jpg")):
                if p.stem == mapa_id or p.stem.startswith(mapa_id):
                    return p
        return None

    def planta_do_bomb(self, mapa_id: str, bomb_id: str):
        """Planta de alguma tatica daquele bomb, para o card nao ficar liso."""
        for tid, _, _ in self.taticas_do_bomb(mapa_id, bomb_id):
            d = self.detalhe(tid)
            if d["planta"]:
                return d["planta"]
        return None

    def detalhe(self, tid: str) -> dict:
        """Planta do andar e icones dos operadores - a arte do card da tatica."""
        for t in self.taticas:
            if t.get("id") != tid:
                continue
            imgs = t.get("imagens") or []
            ops = []
            for s in (t.get("slots") or []):
                cam = self._publico(s.get("icone", ""))
                if cam:
                    ops.append(str(cam))
            return {
                "nome": sem_acento(t.get("nome", tid)),
                "lado": t.get("lado", ""),
                "planta": self._publico(imgs[0]) if imgs else None,
                "operadores": ops,
            }
        return {"nome": tid, "lado": "", "planta": None, "operadores": []}

    def nome_da_tatica(self, tid: str) -> str:
        for t in self.taticas:
            if t.get("id") == tid:
                return sem_acento(t.get("nome", tid))
        return tid or ""

    # -------------------------------------------------------------- escrita

    def _headers(self) -> dict:
        return {
            "apikey": self.anon,
            "Authorization": f"Bearer {self.anon}",
            "Content-Type": "application/json",
        }

    def mandar(self, tatica_id: str | None) -> None:
        """Chama a RPC mandar_tatica. Levanta com mensagem curta se falhar."""
        if not self.url or not self.anon:
            raise RuntimeError("sem credenciais do Supabase")
        if not self.pin:
            raise RuntimeError("falta PIN_TIME no .env.local")

        r = requests.post(
            f"{self.url}/rest/v1/rpc/mandar_tatica",
            headers=self._headers(),
            json={"p_pin": self.pin, "p_tatica_id": tatica_id},
            timeout=TIMEOUT,
        )
        if r.status_code >= 300:
            corpo = (r.text or "")[:120]
            if "42501" in corpo or "PIN" in corpo.upper():
                raise RuntimeError("PIN recusado")
            raise RuntimeError(f"HTTP {r.status_code}")
        self._no_ar_val = tatica_id
        self._no_ar_ate = 0.0

    def no_ar(self) -> str | None:
        """Qual tatica esta no ar, SEM tocar na rede.

        A consulta custa ~650 ms e era chamada em cada navegacao - no caminho do
        dedo, que e o pior lugar possivel. Aqui devolve so o que ja se sabe; quem
        vai a rede e atualiza(), numa thread.
        """
        return self._no_ar_val

    def atualiza(self, ttl: float = 5.0) -> str | None:
        """Le o estado da sala. Bloqueia - chamar fora do caminho do toque."""
        agora = time.monotonic()
        if self._no_ar_ate > agora:
            return self._no_ar_val
        if not self.url or not self.anon:
            return None
        try:
            r = requests.get(
                f"{self.url}/rest/v1/estado_sala",
                headers=self._headers(),
                params={"id": "eq.1", "select": "tatica_id"},
                timeout=TIMEOUT,
            )
            if r.ok:
                dados = r.json()
                self._no_ar_val = dados[0].get("tatica_id") if dados else None
                self._no_ar_ate = agora + ttl
                return self._no_ar_val
        except Exception:
            pass
        # Marcar o prazo TAMBEM na falha: sem isto, com o Supabase fora do ar a
        # condicao inicial nunca saia do lugar e cada pagina de bomb pagava um
        # timeout de 6 s dentro do loop serial.
        self._no_ar_ate = agora + max(1.0, ttl)
        return self._no_ar_val
