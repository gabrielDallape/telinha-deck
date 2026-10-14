"""
O que um modulo ve do TELINHA. Um modulo e uma pasta em `modulos/<id>/` com um
`modulo.json` e um `__init__.py` que define UMA subclasse de `Modulo`:

    from telinha.sdk import Modulo, acao, widget, versao, provedor, texto

    class Exemplo(Modulo):
        def iniciar(self):            # liga threads, abre conexoes
            ...
        def estado(self) -> dict:     # chaves que acendem botoes ("aceso")
            return {"exemplo_on": True}
        def barra(self) -> str:       # pedaco de texto na barra do topo
            return ""
        def tick(self, agora):        # chamado a cada volta do coletor (~1 s)
            ...

        @acao("exemplo")              # passo {"type": "exemplo", ...} de um toque
        def faz(self, passo):         # roda num worker, pode demorar (timeout)
            return "outra_pagina"     # opcional: navega

        @widget("exemplo")            # aparencia {"widget": "exemplo", ...}
        def desenha(self, ap, w, h, aceso):
            return imagem_pillow      # ou um dict que ajusta o icone padrao
                                      # ({"icon": "play"}), ou None = icone padrao

        @versao("exemplo")            # card vivo: muda a versao, a arte e refeita
        def versao_exemplo(self, ap):
            return str(self.contador)

        @provedor("exemplo.lista")    # pagina com "gerar": "exemplo.lista"
        def lista(self, pagina):
            return [botao, ...]       # botoes no esquema 2

        @texto("exemplo")             # "{exemplo}" num rotulo vira isto
        def texto_exemplo(self):
            return "3 itens"

Regras que o nucleo garante e o modulo nao precisa (nem consegue) quebrar:
  - o modulo nunca escolhe id de arte; card vivo tem id fixo e versao;
  - acao roda num worker, nunca no loop serial;
  - `estado`, `versao`, `texto` e `barra` tem de ser baratos (le o ultimo valor
    que uma thread do modulo calculou). O coletor os chama a cada segundo.
"""

from __future__ import annotations

from pathlib import Path


def _marca(tipo: str, nome: str):
    def deco(fn):
        fn._telinha = (tipo, nome)
        return fn
    return deco


def acao(nome: str):
    return _marca("acao", nome)


def widget(nome: str):
    return _marca("widget", nome)


def versao(nome: str):
    return _marca("versao", nome)


def provedor(nome: str):
    return _marca("provedor", nome)


def texto(nome: str):
    return _marca("texto", nome)


class Contexto:
    """O que o nucleo empresta a um modulo."""

    def __init__(self, mid: str, cfg: dict, dados: Path, segredos: Path, nucleo):
        self.id = mid
        self.cfg = cfg
        self.dados = dados
        self.segredos = segredos
        self._nucleo = nucleo

    def log(self, msg: str) -> None:
        print(f"[{self.id}] {msg}")

    def aviso(self, msg: str) -> None:
        """Texto curto na barra da placa por 4 s (o toast do firmware)."""
        self._nucleo.aviso(self.id, msg)

    def atualizar_estado(self) -> None:
        """Pede ao coletor uma leitura agora (o estado mudou por fora)."""
        self._nucleo.atualizar_estado()

    def modulo(self, mid: str):
        """Outro modulo carregado, ou None."""
        return self._nucleo.modulo(mid)

    @property
    def arte(self):
        from . import arte
        return arte


class Modulo:
    id = ""

    def __init__(self, ctx: Contexto):
        self.ctx = ctx
        self.cfg = ctx.cfg

    def iniciar(self) -> None:
        pass

    def parar(self) -> None:
        pass

    def estado(self) -> dict:
        return {}

    def barra(self) -> str:
        return ""

    def tick(self, agora: float) -> None:
        pass
