"""OBS Studio pelo obs-websocket: live, gravar, pausar, replay, mute de fonte,
cena. As cenas sao lidas do OBS (pagina {"gerar": "obs.cenas"}) e o estado
(ao vivo, gravando, cena no ar) acende os botoes."""
from telinha.sdk import Modulo, acao, provedor

from .cliente import Obs, chave_cena

CORES = ["#E5484D", "#F5A524", "#30A46C", "#3E63DD", "#8E4EC6", "#12A594", "#D6409F", "#F76B15"]


class ObsMod(Modulo):
    def iniciar(self):
        self.o = Obs(self.cfg).comeca()

    def estado(self) -> dict:
        return self.o.estado()

    @acao("obs")
    def obs(self, p):
        self.o.executa(p)

    @provedor("obs.cenas")
    def cenas(self, pagina):
        pac = pagina.get("_pacote", "obs")
        return [{"id": f"{pac}.cena:{chave_cena(nome)[5:]}",
                 "aparencia": {"widget": "icone", "icon": "film", "peso": "controle",
                               "label": nome[:18], "label_on": nome[:18],
                               "color": CORES[k % len(CORES)]},
                 "toque": [{"type": "obs", "op": "cena", "cena": nome}],
                 "aceso": chave_cena(nome)}
                for k, nome in enumerate(self.o.cenas)]
