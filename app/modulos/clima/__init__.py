"""Clima pelo Open-Meteo (sem chave). A leitura de rede roda numa thread."""
from telinha.sdk import Modulo, versao, widget

from .fonte import Clima as _Clima


class Clima(Modulo):
    def iniciar(self):
        self.c = _Clima(self.cfg)
        self.c.comeca()

    @widget("clima")
    def desenha(self, ap, w, h, aceso):
        a = self.ctx.arte
        if ap.get("estilo") == "grande":
            return a.botao_clima_grande(w, h, self.c.dados())
        return a.botao_clima(w, h, self.c.dados())

    @versao("clima")
    def ver(self, ap):
        return self.c.versao
