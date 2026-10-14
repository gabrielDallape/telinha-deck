"""
Prova que o remendo funciona, sem depender de alguem tocar na tela.

Simula a placa, carrega a pagina das sessoes, e entao muda o conteudo de um
card do jeito que a vida muda - a ferramenta que a sessao esta rodando - para
medir quanto isso custa na serial antes e depois.

    python teste_remendo.py
"""

from __future__ import annotations

import json
import sys
import time

import paginas
import redea_agent


class PlacaFalsa:
    """Responde imgok a cada pedaco, como o firmware faz."""

    def __init__(self):
        self.para_pc = b""
        self.artes: dict = {}       # id -> bytes recebidos
        self.remendos = 0
        self.inteiros = 0
        self.bytes = 0

    @property
    def in_waiting(self):
        return len(self.para_pc)

    def read(self, n=1):
        d, self.para_pc = self.para_pc[:n], self.para_pc[n:]
        return d

    def write(self, dados):
        self.bytes += len(dados)
        msg = json.loads(dados.decode())
        if msg.get("ev") == "img":
            i = msg["i"]
            if i == -1:
                tem = msg["id"] in self.artes
                self.para_pc += (json.dumps({"cmd": "imgok", "i": -1,
                                             "tem": tem}) + "\n").encode()
            else:
                if i == 0:
                    if "sx" in msg:
                        self.remendos += 1
                    else:
                        self.inteiros += 1
                        self.artes[msg["id"]] = 0
                self.para_pc += (json.dumps({"cmd": "imgok", "i": i}) + "\n").encode()
        return len(dados)

    def close(self):
        pass


def escoa(lig, limite=20000):
    for _ in range(limite):
        lig.bombeia()
        lig.bombeia_fila()
        if not lig.fila and lig.pendente is None:
            return
    raise RuntimeError("a fila nao esvaziou")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cfg = redea_agent.carregar_config()
    painel = paginas.Painel(cfg)
    ser = PlacaFalsa()
    lig = redea_agent.Ligacao(ser, painel)

    ss = painel.sessoes()
    if not ss:
        print("nenhuma sessao aberta: abra o claude em algum projeto")
        return 1

    lig.trata({"cmd": "hello", "fw": "teste", "page": ""})
    escoa(lig)
    lig.trata({"cmd": "page", "id": "claude"})
    escoa(lig)
    print("carga inicial da pagina claude: {} cards, {:.0f} KB".format(
        ser.inteiros, ser.bytes / 1024))

    # Agora a vida acontece: a sessao troca de ferramenta. E a mudanca mais
    # frequente que existe neste painel, e era ela que saturava a serial.
    alvo = painel._ses[0]
    antes_b, antes_i, antes_r = ser.bytes, ser.inteiros, ser.remendos

    for k, (ferr, arg) in enumerate([("Bash", "npm test"),
                                     ("Edit", "paginas.py"),
                                     ("Read", "arte.py"),
                                     ("Busca", "esp32 p4 mipi dsi")]):
        alvo["_agora"] = (ferr, arg)
        alvo["estado"] = "trabalhando"
        painel._ses_ate = time.monotonic() + 999   # congela: a mudanca e a nossa
        lig.enfileira("claude", prio=True)
        escoa(lig)

    gastou = ser.bytes - antes_b
    print("\n4 trocas de ferramenta:")
    print("   remendos: {}   cards inteiros: {}".format(
        ser.remendos - antes_r, ser.inteiros - antes_i))
    print("   gastou {:.1f} KB  ({:.1f} KB por troca)".format(
        gastou / 1024, gastou / 1024 / 4))
    inteiro = len(painel.arte(painel._ver and "ses:{}".format(alvo["pid"]) or "", 410, 308) or b"")
    if inteiro:
        print("   um card inteiro custaria {:.1f} KB".format(inteiro / 1024))
        print("   economia: {:.0f}%".format(
            100 - (gastou / 4) * 100.0 / inteiro))
    print("\n   na serial a 38 KB/s isso e {:.2f} s por troca".format(
        gastou / 4 / 1024 / 38))
    return 0


if __name__ == "__main__":
    sys.exit(main())
