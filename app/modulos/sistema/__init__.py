"""CPU e RAM num medidor. A leitura (psutil) so roda se algum card usar."""
from telinha.sdk import Modulo, versao, widget

from .fonte import Sistema as _Sistema


class Sistema(Modulo):
    def iniciar(self):
        self.s = _Sistema()
        self.s.comeca()

    @widget("sistema")
    def desenha(self, ap, w, h, aceso):
        d = self.s.dados()
        return self.ctx.arte.botao_medidor(
            w, h, "CPU", d["cpu"], "%", d["cpu"],
            f"RAM {d['ram']:.0f}%  ·  {d['ram_gb']:.1f} de {d['ram_total_gb']:.0f} GB")

    @versao("sistema")
    def ver(self, ap):
        return self.s.versao
