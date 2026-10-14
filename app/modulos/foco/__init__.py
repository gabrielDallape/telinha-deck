"""Pomodoro: o card mostra os minutos que faltam; o toque comeca ou cancela."""
from telinha.sdk import Modulo, acao, versao, widget

from .fonte import Foco as _Foco


class Foco(Modulo):
    def iniciar(self):
        self.f = _Foco(int(self.cfg.get("min") or 25))

    @acao("foco")
    def toque(self, passo):
        self.ctx.log(self.f.toque())

    @widget("foco")
    def desenha(self, ap, w, h, aceso):
        return self.ctx.arte.botao_foco(w, h, self.f.dados())

    @versao("foco")
    def ver(self, ap):
        return self.f.versao

    def tick(self, agora):
        aviso = self.f.aviso()
        if aviso:
            self.ctx.aviso(aviso)
