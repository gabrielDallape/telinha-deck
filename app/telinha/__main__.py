"""
    python -m telinha rodar            o nucleo (o que a bandeja sobe)
    python -m telinha bandeja          o icone ao lado do relogio
    python -m telinha janela           a janela do app (placa na tela, editar botoes)
    python -m telinha lista            pacotes, modulos, paginas e o tamanho das artes
    python -m telinha testa home/mic   dispara um botao como se fosse um toque

Rodar de dentro de `app/` (ou com app/ no PYTHONPATH).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

VERSAO = "0.1.0"


def _console() -> None:
    if sys.stdout is not None:          # pythonw: sem console, stdout e None
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def lista() -> int:
    from telinha.nucleo import Nucleo
    from telinha.compositor import tamanho_botao
    n = Nucleo()
    print(f"TELINHA {VERSAO}\n\nPacotes:")
    for r in n.perfil.get("_pacotes", []):
        marca = "ATIVO" if r["ativo"] else ("instalado, desligado" if r["instalado"] else "nao encontrado")
        print(f"  {r['id']:12s} {r['nome']:22s} {marca}")
    print("\nModulos:")
    for mid in sorted(n.hosp.manifestos):
        st = "ligado" if mid in n.hosp.ligados else ("ERRO: " + n.hosp.erros[mid] if mid in n.hosp.erros
                                                     else "carregado, sem uso")
        print(f"  {mid:12s} {st}")
    time.sleep(1.5)            # fontes vivas (musica, clima) dao a primeira leitura
    print("\nPaginas e botoes:")
    total = 0
    for pid in n.comp.paginas():
        pag = n.comp.pagina(pid)
        g = pag["grid"]
        w, h = tamanho_botao(g["cols"], g["rows"])
        print(f"\n  [{pid}] {pag['title'].strip() or '(sem titulo)'} - grade {g['cols']}x{g['rows']}, cards {w}x{h}")
        for b in pag["buttons"]:
            jpeg = n.comp.arte(b["art"], pag["_vivos"].get(b["art"]), espera=10.0)
            botao = n.comp.botao(pid, b["id"]) or {}
            tipos = ",".join(p.get("type", "?") for p in botao.get("toque", [])) or "-"
            tam = f"{len(jpeg) // 1024} KB" if jpeg else "SEM ARTE"
            total += 1
            print(f"    {b['id'][:26]:26s} {tipos[:24]:24s} {tam:9s}"
                  + (" vivo" if b["art"] in pag["_vivos"] else "")
                  + ("  +aceso" if b["art_on"] else ""))
    print(f"\n{total} botoes. Estado: {n.coletor.ultimo()[1]}")
    return 0


def testa(alvos: list) -> int:
    from telinha.nucleo import Nucleo
    n = Nucleo()
    for alvo in alvos:
        pid, _, bid = alvo.rpartition("/") if "/" in alvo else (n.inicio(), "", alvo)
        n.comp.pagina(pid)
        b = n.comp.botao(pid, bid)
        if b is None:
            print(f"[erro] {pid}/{bid}: sem mapeamento")
            continue
        try:
            destino = n.rot.executar(b.get("toque") or [])
            destino = b.get("depois") or destino
            print(f"[ok] {pid}/{bid}" + (f" -> vai para {destino}" if destino else ""))
        except Exception as e:
            print(f"[erro] {pid}/{bid}: {e}")
    time.sleep(0.5)
    return 0


def janela() -> int:
    """Abre a janela no nucleo que esta rodando (a bandeja o sobe). A janela e
    so uma vista: fechar a janela nao desliga o painel."""
    import json
    import urllib.request
    from telinha import caminhos
    try:
        info = json.loads(caminhos.API.read_text(encoding="utf-8"))
        url = f"http://127.0.0.1:{info['porta']}/?token={info['token']}"
        urllib.request.urlopen(f"http://127.0.0.1:{info['porta']}/api/tudo?token={info['token']}", timeout=3)
    except Exception:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0, "O TELINHA nao esta rodando. Ligue pelo icone da bandeja (ou: python -m telinha bandeja).",
            "TELINHA", 0x40)
        return 1
    import webview
    webview.create_window("TELINHA", url, width=1500, height=900, min_size=(1000, 640),
                          background_color="#0B0E13")
    webview.start()
    return 0


def main() -> int:
    _console()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "rodar"
    if cmd == "rodar":
        from telinha.nucleo import Nucleo
        print(f"TELINHA {VERSAO}")
        return Nucleo().rodar()
    if cmd == "lista":
        return lista()
    if cmd == "testa":
        return testa(sys.argv[2:])
    if cmd == "janela":
        return janela()
    if cmd == "bandeja":
        from telinha.bandeja import Bandeja
        Bandeja().roda()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
