"""Os projetos da pasta de trabalho: um card por projeto (branch e idade), e um
toque abre o Windows Terminal na pasta ja com o `claude` rodando.

Pagina: {"gerar": "projetos.lista"}. Texto "{projetos}" = "4 projetos".
"""
import time
from pathlib import Path

from telinha.sdk import Modulo, acao, provedor, texto, widget

from .fonte import Projetos as _Projetos


def _idade(segundos: float) -> str:
    """Em degraus grossos de proposito: o texto entra na aparencia, e
    aparencia nova e card remandado."""
    if segundos < 3600:
        return "agora"
    if segundos < 86400:
        return f"ha {int(segundos // 3600)} h"
    if segundos < 86400 * 60:
        return f"ha {int(segundos // 86400)} d"
    return f"ha {int(segundos // (86400 * 30))} meses"


def info_projeto(p: Path) -> dict:
    """Branch e idade por alguns stats. A idade e o mais novo entre a pasta, o
    que esta direto nela e o index do git (um commit mexe no index)."""
    branch = ""
    try:
        head = (p / ".git" / "HEAD").read_text(errors="ignore").strip()
        branch = head.rsplit("/", 1)[-1] if head.startswith("ref:") else head[:7]
    except OSError:
        pass
    mt = 0.0
    candidatos = [p, p / ".git" / "index", p / ".git" / "HEAD"]
    try:
        candidatos += [f for _, f in zip(range(60), p.iterdir())]
    except OSError:
        pass
    for f in candidatos:
        try:
            mt = max(mt, f.stat().st_mtime)
        except OSError:
            pass
    return {"branch": branch, "idade": _idade(time.time() - mt) if mt else ""}


class ProjetosMod(Modulo):
    def iniciar(self):
        self.p = _Projetos({"projetos": self.cfg})

    @provedor("projetos.lista")
    def lista(self, pagina):
        saida = []
        for pid, nome, caminho, _cor in self.p.itens():
            info = info_projeto(caminho)
            saida.append({"id": f"proj:{pid}",
                          "aparencia": {"widget": "projeto", "nome": nome, **info},
                          "toque": [{"type": "abrir_projeto", "projeto": pid}]})
        return saida

    @widget("projeto")
    def desenha(self, ap, w, h, aceso):
        a = self.ctx.arte
        return a.botao_projeto(w, h, ap["nome"], a.cor_projeto(ap["nome"]),
                               branch=ap.get("branch", ""), idade=ap.get("idade", ""))

    @acao("abrir_projeto")
    def abrir(self, p):
        self.p.abrir(p["projeto"])

    @texto("projetos")
    def contagem(self):
        n = len(self.p.itens())
        return f"{n} projeto" + ("" if n == 1 else "s")
