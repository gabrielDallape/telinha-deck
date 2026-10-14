"""Relogio: hora, dia da semana e data. `estilo: "grande"` e o da tela de descanso."""
from telinha.sdk import Modulo, versao, widget

from .fonte import Relogio as _Relogio


class Relogio(Modulo):
    def iniciar(self):
        self.r = _Relogio()

    @widget("relogio")
    def desenha(self, ap, w, h, aceso):
        a = self.ctx.arte
        if ap.get("estilo") == "grande":
            return a.botao_relogio_grande(w, h, **self.r.dados())
        return a.botao_relogio(w, h, **self.r.dados())

    @versao("relogio")
    def ver(self, ap):
        return self.r.versao
