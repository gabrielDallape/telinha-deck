"""
Carrega os modulos e mantem o registro do que cada um oferece: acoes, widgets,
versoes, provedores de pagina e textos. O resto do nucleo so fala com o
registro; nada aqui sabe o que e Spotify.

Um modulo so e LIGADO (`iniciar`) se o perfil usa algo dele, ou se o
`modulo.json` diz `"sempre": true`. Um modulo que falha ao carregar ou ao
iniciar fica de fora, com aviso - o painel sobe sem ele. Tres quedas seguidas
no arranque (contadas em DADOS/modulos/<id>/quedas) desligam o modulo ate
alguem religa-lo: e o modo seguro.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
import threading
import traceback

from . import caminhos
from .sdk import Contexto, Modulo

MAX_QUEDAS = 3


class Hospedeiro:
    def __init__(self, nucleo):
        self.nucleo = nucleo
        self.manifestos: dict = {}     # id -> modulo.json
        self.modulos: dict = {}        # id -> instancia (carregados)
        self.ligados: set = set()
        self.acoes: dict = {}          # nome -> (id, metodo)
        self.widgets: dict = {}
        self.versoes: dict = {}
        self.provedores: dict = {}
        self.textos: dict = {}
        self.erros: dict = {}          # id -> texto do erro
        self._lock = threading.Lock()

    # ------------------------------------------------------------ descoberta

    def descobrir(self) -> None:
        if str(caminhos.PROGRAMA) not in sys.path:
            sys.path.insert(0, str(caminhos.PROGRAMA))
        for pasta in sorted(caminhos.MODULOS.iterdir()):
            arq = pasta / "modulo.json"
            if not arq.is_file():
                continue
            try:
                m = json.loads(arq.read_text(encoding="utf-8"))
            except ValueError as e:
                self.erros[pasta.name] = f"modulo.json invalido: {e}"
                continue
            m.setdefault("id", pasta.name)
            m["_pasta"] = str(pasta)
            self.manifestos[m["id"]] = m

    def _cfg(self, mid: str, perfil: dict) -> dict:
        padrao = {k: v.get("padrao") for k, v in (self.manifestos[mid].get("config") or {}).items()
                  if isinstance(v, dict)}
        return {**padrao, **((perfil.get("modulos") or {}).get(mid) or {})}

    def carregar(self, perfil: dict) -> None:
        for mid, man in self.manifestos.items():
            if mid in self.modulos:
                continue
            quedas = self._quedas(mid)
            if quedas >= MAX_QUEDAS:
                self.erros[mid] = f"desligado depois de {quedas} quedas no arranque (modo seguro)"
                print(f"[modulos] {mid}: {self.erros[mid]}")
                continue
            try:
                pacote = importlib.import_module(f"modulos.{mid}")
                classes = [c for _, c in inspect.getmembers(pacote, inspect.isclass)
                           if issubclass(c, Modulo) and c is not Modulo
                           and c.__module__.startswith(f"modulos.{mid}")]
                if len(classes) != 1:
                    raise RuntimeError(f"esperava 1 classe Modulo, achei {len(classes)}")
                dados = caminhos.DADOS_MODULOS / mid
                dados.mkdir(parents=True, exist_ok=True)
                ctx = Contexto(mid, self._cfg(mid, perfil), dados, caminhos.SEGREDOS, self.nucleo)
                inst = classes[0](ctx)
                inst.id = mid
                self._registra(mid, inst)
                self.modulos[mid] = inst
            except Exception as e:
                self.erros[mid] = f"{type(e).__name__}: {e}"
                print(f"[modulos] {mid} nao carregou: {self.erros[mid]}")
                traceback.print_exc()

    def _registra(self, mid: str, inst) -> None:
        tabelas = {"acao": self.acoes, "widget": self.widgets, "versao": self.versoes,
                   "provedor": self.provedores, "texto": self.textos}
        for _, metodo in inspect.getmembers(inst, inspect.ismethod):
            marca = getattr(metodo, "_telinha", None)
            if not marca:
                continue
            tipo, nome = marca
            tab = tabelas[tipo]
            if nome in tab:
                print(f"[modulos] {mid}: {tipo} '{nome}' ja e de {tab[nome][0]}, ignorado")
                continue
            tab[nome] = (mid, metodo)

    # ----------------------------------------------------------- ligar/desligar

    def usados(self, perfil: dict) -> set:
        """Modulos que o perfil usa: por acao, widget, provedor, texto ou `sempre`."""
        texto_perfil = json.dumps(perfil.get("paginas", {}), ensure_ascii=False)
        usados = {mid for mid, m in self.manifestos.items() if m.get("sempre")}
        for pag in (perfil.get("paginas") or {}).values():
            if pag.get("gerar") in self.provedores:
                usados.add(self.provedores[pag["gerar"]][0])
            for b in pag.get("botoes", []):
                w = (b.get("aparencia") or {}).get("widget")
                if w in self.widgets:
                    usados.add(self.widgets[w][0])
                for passo in b.get("toque", []):
                    if passo.get("type") in self.acoes:
                        usados.add(self.acoes[passo["type"]][0])
        for nome, (mid, _) in self.textos.items():
            if "{" + nome + "}" in texto_perfil:
                usados.add(mid)
        # chaves de estado: um modulo que declara `estados` no manifesto e
        # ligado se algum botao acende por uma delas
        for mid, m in self.manifestos.items():
            for chave in m.get("estados", []):
                if f'"aceso": "{chave}' in texto_perfil:
                    usados.add(mid)
        return {m for m in usados if m in self.modulos}

    def ligar(self, perfil: dict) -> None:
        for mid in sorted(self.usados(perfil) - self.ligados):
            inst = self.modulos[mid]
            self._anota_queda(mid, +1)
            try:
                inst.iniciar()
                self.ligados.add(mid)
                print(f"[modulos] {mid} ligado")
            except Exception as e:
                self.erros[mid] = f"iniciar: {type(e).__name__}: {e}"
                print(f"[modulos] {mid} nao iniciou: {self.erros[mid]}")
                traceback.print_exc()
            finally:
                self._anota_queda(mid, 0)

    def parar(self) -> None:
        for mid in list(self.ligados):
            try:
                self.modulos[mid].parar()
            except Exception:
                pass
        self.ligados.clear()

    def reconfigurar(self, perfil: dict) -> None:
        """Perfil novo (hello, editor): config nova para cada modulo, liga os que
        passaram a ser usados. Os que deixaram de ser usados seguem ligados ate
        o proximo arranque - desligar thread no meio e pedir problema."""
        for mid, inst in self.modulos.items():
            inst.ctx.cfg = inst.cfg = self._cfg(mid, perfil)
        self.ligar(perfil)

    # -------------------------------------------------------------- quedas

    def _quedas(self, mid: str) -> int:
        try:
            return int((caminhos.DADOS_MODULOS / mid / "quedas").read_text())
        except (OSError, ValueError):
            return 0

    def _anota_queda(self, mid: str, delta: int) -> None:
        """+1 antes de iniciar, zera depois: se o processo morrer no meio do
        iniciar, o contador fica e o arranque seguinte sabe."""
        arq = caminhos.DADOS_MODULOS / mid / "quedas"
        try:
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(str(self._quedas(mid) + 1 if delta else 0))
        except OSError:
            pass

    # ---------------------------------------------------------- consultas

    def modulo(self, mid: str):
        return self.modulos.get(mid) if mid in self.ligados else None

    def estado(self) -> dict:
        saida = {}
        for mid in list(self.ligados):
            try:
                saida.update(self.modulos[mid].estado() or {})
            except Exception as e:
                print(f"[{mid}] estado: {e}")
        return saida

    def barra(self) -> list:
        partes = []
        for mid in sorted(self.ligados):
            try:
                t = self.modulos[mid].barra()
                if t:
                    partes.append(t)
            except Exception as e:
                print(f"[{mid}] barra: {e}")
        return partes

    def tick(self, agora: float) -> None:
        for mid in list(self.ligados):
            try:
                self.modulos[mid].tick(agora)
            except Exception as e:
                print(f"[{mid}] tick: {e}")

    def texto(self, nome: str) -> str | None:
        if nome not in self.textos:
            return None
        mid, fn = self.textos[nome]
        if mid not in self.ligados:
            return None
        try:
            return str(fn())
        except Exception as e:
            print(f"[{mid}] texto {nome}: {e}")
            return None
