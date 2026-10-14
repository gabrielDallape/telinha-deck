"""Agenda (.ics ou login no Google): card com as proximas reunioes e a
proxima de hoje na barra do topo."""
import datetime as dt

from telinha.sdk import Modulo, versao, widget

from .fonte import Agenda as _Agenda


class Agenda(Modulo):
    def iniciar(self):
        self.a = _Agenda(self.cfg, self.ctx.segredos)
        self.a.comeca()

    @widget("agenda")
    def desenha(self, ap, w, h, aceso):
        return self.ctx.arte.botao_agenda(w, h, self.a.dados())

    @versao("agenda")
    def ver(self, ap):
        return self.a.versao

    def barra(self):
        hoje = dt.datetime.now().astimezone().date()
        for e in self.a.proximos(1):
            if e.get("dia_inteiro") or e["inicio"].date() != hoje:
                return ""
            return f"{e['inicio'].strftime('%H:%M')} {e['titulo'][:24]}"
        return ""
