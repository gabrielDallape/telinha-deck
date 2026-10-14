"""Soundboard: cada arquivo de som de uma pasta vira um botao. Toque toca,
tocar de novo para, sons se sobrepoem; saidas multiplas (alto-falante + cabo
virtual) para a call ou a live ouvirem.

Pagina: {"gerar": "soundboard.sons", "pasta": "sons"} - `pasta` relativa a do
pacote; `pasta` do config do modulo acrescenta uma pasta do usuario.
"""
import hashlib
from pathlib import Path

from telinha.sdk import Modulo, acao, provedor

from . import mixer

CORES = ["#E5484D", "#F5A524", "#30A46C", "#3E63DD", "#8E4EC6", "#12A594", "#D6409F", "#F76B15"]


class Soundboard(Modulo):
    @provedor("soundboard.sons")
    def sons(self, pagina):
        pastas = [Path(pagina.get("_dir", ".")) / pagina.get("pasta", "sons")]
        if self.cfg.get("pasta"):
            pastas.insert(0, Path(self.cfg["pasta"]))
        modelo = pagina.get("modelo") or {}
        cores = pagina.get("cores") or CORES
        pac = pagina.get("_pacote", "soundboard")
        saida = []
        for k, arq in enumerate(mixer.listar(pastas)):
            chave = hashlib.sha1(str(arq).encode()).hexdigest()[:8]
            saida.append({"id": f"{pac}.som:{chave}",
                          "aparencia": {"widget": "icone", "icon": "waveform", "peso": "controle",
                                        **modelo, "label": arq.stem[:18],
                                        "color": cores[k % len(cores)]},
                          "toque": [{"type": "som", "arquivo": str(arq)}]})
        return saida

    @acao("som")
    def som(self, p):
        r = mixer.mixer(self.cfg).tocar(p["arquivo"], p.get("volume"), p.get("modo", "alternar"))
        self.ctx.log(f"{Path(p['arquivo']).name}: {r}")

    @acao("som_parar")
    def parar(self, p):
        mixer.mixer(self.cfg).parar()
