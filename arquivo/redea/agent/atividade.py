"""
O que a sessao esta FAZENDO, nao so em que estado ela esta.

O `sessoes.py` responde "trabalhando ou parada". Isso e pouco: um card que so
diz TRABALHANDO ha dez minutos nao informa nada que um LED nao informasse. O
transcript tem o resto, e ninguem le - cada `tool_use` tem nome, argumento e
carimbo de hora, e o `file-history-snapshot` guarda que arquivos foram tocados.

Daqui saem tres coisas, e cada uma resolve um pedaco do card:

    agora()     "Bash: cd C:/projetos/REDEA" - a ferramenta rodando
    pulso()     quantos eventos por minuto nos ultimos 20 - o sparkline
    tocados()   os arquivos que a sessao mexeu

Custo: uma passada na mesma cauda de 256 KB que o sessoes.py ja le.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import sessoes

JANELA_PULSO = 20        # minutos de historico no sparkline

# Como resumir cada ferramenta numa linha. A chave e o campo do input que
# interessa; o resto do dicionario de argumentos e ruido no card.
CAMPO = {
    "Bash": "command", "PowerShell": "command", "Read": "file_path",
    "Edit": "file_path", "Write": "file_path", "Glob": "pattern",
    "Grep": "pattern", "WebSearch": "query", "WebFetch": "url",
    "Task": "description", "Agent": "description", "Skill": "skill",
    "NotebookEdit": "notebook_path", "TodoWrite": None,
}

# Nome curto para caber no card.
APELIDO = {"PowerShell": "Shell", "NotebookEdit": "Notebook",
           "WebSearch": "Busca", "WebFetch": "Fetch", "TodoWrite": "Tarefas"}


def _hora(ts: str) -> float:
    """ISO do transcript -> epoch. Devolve 0 quando nao der para ler."""
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _resumo_input(nome: str, entrada) -> str:
    if not isinstance(entrada, dict):
        return ""
    campo = CAMPO.get(nome, "")
    if campo is None:
        return ""
    valor = entrada.get(campo) if campo else ""
    if not valor:
        # ferramenta desconhecida: pega o primeiro campo de texto que houver
        for v in entrada.values():
            if isinstance(v, str) and v.strip():
                valor = v
                break
    valor = " ".join(str(valor or "").split())
    if campo in ("file_path", "notebook_path") and valor:
        valor = Path(valor).name          # o caminho inteiro nao cabe
    return valor


class Atividade:
    """Uma leitura da cauda do transcript, com as tres visoes prontas."""

    def __init__(self, linhas: list):
        self.eventos: list = []       # (hora, nome, resumo)
        self.arquivos: list = []      # caminhos, mais recente primeiro
        self.turnos: list = []        # duracoes em ms

        vistos = set()
        for e in linhas:
            t = e.get("type")
            if t == "assistant":
                h = _hora(e.get("timestamp", ""))
                for c in (e.get("message") or {}).get("content") or []:
                    if c.get("type") == "tool_use":
                        nome = c.get("name", "?")
                        self.eventos.append(
                            (h, APELIDO.get(nome, nome),
                             _resumo_input(nome, c.get("input"))))
            elif t == "user":
                self.eventos.append((_hora(e.get("timestamp", "")), "", ""))
            elif t == "system" and e.get("subtype") == "turn_duration":
                self.turnos.append(int(e.get("durationMs") or 0))
            elif t == "file-history-snapshot":
                snap = (e.get("snapshot") or {}).get("trackedFileBackups") or {}
                for caminho in snap:
                    if caminho not in vistos:
                        vistos.add(caminho)
                        self.arquivos.append(caminho)
        self.arquivos.reverse()

    # ------------------------------------------------------------- visoes

    def agora(self) -> tuple:
        """(ferramenta, resumo) da ultima acao. ('', '') se nao houver."""
        for h, nome, resumo in reversed(self.eventos):
            if nome:
                return nome, resumo
        return "", ""

    def ultimas(self, n: int = 6) -> list:
        """As n ultimas ferramentas, mais recente primeiro."""
        saida = [e for e in reversed(self.eventos) if e[1]]
        return saida[:n]

    def pulso(self, minutos: int = JANELA_PULSO) -> list:
        """Eventos por minuto, do mais antigo ao mais novo. Vira sparkline.

        E o que faz o card parecer vivo sem custar nada: a forma da barra ja
        conta se a sessao esta a todo vapor ou so respirando, e muda no maximo
        uma vez por minuto - o que importa, porque cada mudanca de arte e um
        card inteiro atravessando a serial.
        """
        agora = time.time()
        baldes = [0] * minutos
        for h, _nome, _r in self.eventos:
            if not h:
                continue
            atras = (agora - h) / 60.0
            if 0 <= atras < minutos:
                baldes[minutos - 1 - int(atras)] += 1
        return baldes

    def tocados(self, n: int = 5) -> list:
        """Nomes dos arquivos que a sessao mexeu, mais recente primeiro."""
        return [Path(p).name for p in self.arquivos[:n]]

    def turno_medio(self) -> float:
        """Segundos por turno, mediana dos ultimos. Zero se nao houver."""
        if not self.turnos:
            return 0.0
        ult = sorted(self.turnos[-9:])
        return ult[len(ult) // 2] / 1000.0

    def ferramentas_do_dia(self) -> int:
        return sum(1 for _h, n, _r in self.eventos if n)


def ler(s: dict) -> Atividade:
    """Atividade de uma sessao devolvida por sessoes.vivas()."""
    tr = sessoes._transcript(s["sid"], s["cwd"])
    return Atividade(sessoes.cauda_util(tr) if tr else [])


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for s in sessoes.vivas():
        a = ler(s)
        nome, resumo = a.agora()
        print("== {} ({}) ==".format(s["nome"], s["estado"]))
        print("   agora:      {} {}".format(nome, resumo[:60]))
        print("   pulso:      {}".format(a.pulso()))
        print("   ferramentas:{}  turno medio {:.0f}s".format(
            a.ferramentas_do_dia(), a.turno_medio()))
        print("   arquivos:   {}".format(", ".join(a.tocados()) or "nenhum"))
        for h, n, r in a.ultimas(4):
            print("     - {} {}".format(n, r[:56]))
