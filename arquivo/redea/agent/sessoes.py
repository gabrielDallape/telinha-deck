"""
Le o que o Claude Code ja escreve no disco e transforma em estado de painel.

Nada aqui e adivinhado por heuristica: o proprio CLI mantem dois arquivos que
dizem tudo.

    ~/.claude/sessions/<pid>.json      uma sessao VIVA. Tem pid, cwd, o nome
                                       derivado ("joquei-45"), e o campo que
                                       vale o painel inteiro: "status", que e
                                       "busy" ou "idle", com "statusUpdatedAt".

    ~/.claude/projects/<slug>/<id>.jsonl   o transcript. Tem "ai-title" (o titulo
                                       que o proprio Claude deu a conversa),
                                       "last-prompt", o modelo, o effort, o
                                       usage de tokens e a duracao do turno.

O transcript chega a 10 MB. Ler o arquivo inteiro para pegar quatro campos que
o CLI reescreve a cada turno seria absurdo dentro do loop serial, entao aqui se
le so a CAUDA - os ultimos 256 KB - e se procura de tras para frente.
"""

from __future__ import annotations

import ctypes
import json
import os
import time
from pathlib import Path

RAIZ = Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))
DIR_SESSOES = RAIZ / "sessions"
DIR_PROJETOS = RAIZ / "projects"

CAUDA = 256 * 1024      # quanto do fim do transcript vale a pena ler
PARADA_APOS = 20 * 60   # idle mais que isto: a sessao esfriou

# Janela de contexto por modelo. So serve para a barra de "quanto ja encheu";
# um numero errado aqui nao quebra nada, so desenha a barra na altura errada.
JANELA = {"claude-opus-5": 200_000, "claude-sonnet-5": 1_000_000,
          "claude-fable-5-1": 200_000, "claude-haiku-4-5": 200_000}
JANELA_PADRAO = 200_000

CURTO = {"claude-opus-5": "Opus 5", "claude-sonnet-5": "Sonnet 5",
         "claude-fable-5-1": "Fable 5.1", "claude-haiku-4-5": "Haiku 4.5"}


# ------------------------------------------------------------- processo vivo

_kernel32 = ctypes.windll.kernel32
_SYNCHRONIZE = 0x00100000


def _pid_vivo(pid: int) -> bool:
    """O arquivo de sessao fica para tras quando o CLI morre de forma feia.

    Sem esta checagem o painel mostra sessao fantasma de terminal fechado ha
    dias. OpenProcess com SYNCHRONIZE basta e nao exige privilegio.
    """
    h = _kernel32.OpenProcess(_SYNCHRONIZE, False, int(pid))
    if not h:
        return False
    _kernel32.CloseHandle(h)
    return True


# ------------------------------------------------------------ cauda do jsonl

def _cauda(caminho: Path, n: int = CAUDA) -> list:
    """Ultimas linhas JSON completas do arquivo, ja decodificadas."""
    try:
        tam = caminho.stat().st_size
        with open(caminho, "rb") as f:
            if tam > n:
                f.seek(tam - n)
                f.readline()        # a primeira linha lida veio cortada no meio
            bruto = f.read()
    except OSError:
        return []
    saida = []
    for linha in bruto.split(b"\n"):
        if not linha.strip():
            continue
        try:
            saida.append(json.loads(linha))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    return saida


def cauda_util(caminho, minimo: int = 25, teto: int = 8 * 1024 * 1024) -> list:
    """Cauda que cresce ate ter linhas suficientes para valer alguma coisa.

    256 KB parecia muito ate aparecer um turno com um dump de crash de 16 KB e
    varias saidas de comando longas: a cauda inteira virou SEIS linhas, e a
    timeline do card mostrou um item so. O tamanho em bytes nao diz nada sobre
    quantos eventos ha ali - depende do que a sessao andou fazendo.

    Entao le-se 256 KB, e se vierem poucas linhas dobra-se ate conseguir (ou
    ate o teto). Quase sempre para na primeira tentativa; so paga mais quem
    realmente tem linhas gigantes.
    """
    n = CAUDA
    linhas = _cauda(caminho, n)
    while len(linhas) < minimo and n < teto:
        n *= 4
        novas = _cauda(caminho, n)
        if len(novas) <= len(linhas):
            break          # o arquivo acabou: nao adianta crescer mais
        linhas = novas
    return linhas


def _slug(cwd: str) -> str:
    """C:/Users/x/JOQUEI -> C--Users-x-JOQUEI, a regra do proprio CLI."""
    return "".join(c if c.isalnum() else "-" for c in cwd)


def _transcript(sid: str, cwd: str):
    direto = DIR_PROJETOS / _slug(cwd) / (sid + ".jsonl")
    if direto.exists():
        return direto
    # A regra de slug pode mudar entre versoes do CLI; o id da sessao nao.
    for p in DIR_PROJETOS.glob("*/" + sid + ".jsonl"):
        return p
    return None


# --------------------------------------------------------------- leitura

_VAZIO = (("titulo", ""), ("prompt", ""), ("modelo", ""), ("effort", ""),
          ("ctx", 0), ("janela", JANELA_PADRAO), ("turno_ms", 0),
          ("branch", ""), ("modo", ""), ("permissao", ""), ("respondeu", False))


def _detalhe(caminho) -> dict:
    """O que der para saber do transcript, sem explodir se faltar campo."""
    d = dict(_VAZIO)
    linhas = cauda_util(caminho)
    if not linhas:
        return d

    visto = set()
    for e in reversed(linhas):
        t = e.get("type")
        if t in visto:
            continue

        if t == "ai-title":
            d["titulo"] = (e.get("aiTitle") or "").strip()
        elif t == "last-prompt":
            d["prompt"] = " ".join((e.get("lastPrompt") or "").split())
        elif t == "permission-mode":
            d["permissao"] = e.get("permissionMode") or ""
        elif t == "mode":
            d["modo"] = e.get("mode") or ""
        elif t == "system" and e.get("subtype") == "turn_duration":
            d["turno_ms"] = int(e.get("durationMs") or 0)
        elif t == "assistant":
            m = e.get("message") or {}
            d["modelo"] = m.get("model") or ""
            d["effort"] = e.get("effort") or ""
            ramo = e.get("gitBranch") or ""
            d["branch"] = "" if ramo == "HEAD" else ramo
            u = m.get("usage") or {}
            # O que ocupa a janela e o prompt inteiro que subiu: o cache lido
            # conta igual. So "input_tokens" daria 2 num turno de 150 mil.
            d["ctx"] = (int(u.get("input_tokens") or 0)
                        + int(u.get("cache_read_input_tokens") or 0)
                        + int(u.get("cache_creation_input_tokens") or 0))
            d["janela"] = JANELA.get(d["modelo"], JANELA_PADRAO)
            d["respondeu"] = any(c.get("type") == "text"
                                 for c in m.get("content") or [])
        else:
            continue
        visto.add(t)
        if len(visto) >= 6:
            break
    return d


def _nome_bonito(bruto: str, cwd: str) -> str:
    """'joquei-45' -> 'joquei'. O sufixo numerico e ruido de desambiguacao."""
    if bruto:
        base = bruto.rsplit("-", 1)
        if len(base) == 2 and base[1].isdigit():
            bruto = base[0]
        if bruto:
            return bruto
    return Path(cwd).name or cwd


def vivas() -> list:
    """Sessoes do Claude Code abertas agora, a mais quente primeiro."""
    if not DIR_SESSOES.is_dir():
        return []
    agora = time.time()
    saida = []
    for arq in DIR_SESSOES.glob("*.json"):
        try:
            s = json.loads(arq.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        pid, sid, cwd = s.get("pid"), s.get("sessionId"), s.get("cwd") or ""
        if not (pid and sid) or not _pid_vivo(pid):
            continue

        status = s.get("status") or "idle"
        desde = max(0.0, agora - (s.get("statusUpdatedAt") or 0) / 1000.0)
        tr = _transcript(sid, cwd)
        det = _detalhe(tr) if tr else dict(_VAZIO)

        if status == "busy":
            estado = "trabalhando"
        elif desde > PARADA_APOS:
            estado = "parada"
        else:
            estado = "pronta"

        item = {"pid": int(pid), "sid": sid, "cwd": cwd,
                "nome": _nome_bonito(s.get("name") or "", cwd),
                "estado": estado, "desde": desde,
                "aberta_ha": max(0.0, agora - (s.get("startedAt") or 0) / 1000.0),
                "versao": s.get("version") or ""}
        item.update(det)
        saida.append(item)

    # Trabalhando primeiro (e o que voce quer ver), depois pronta, depois parada.
    ordem = {"trabalhando": 0, "pronta": 1, "parada": 2}
    saida.sort(key=lambda x: (ordem.get(x["estado"], 9), x["desde"]))
    return saida


def modelo_curto(m: str) -> str:
    if not m:
        return ""
    return CURTO.get(m, m.replace("claude-", "").replace("-", " ").title())


# ------------------------------------------------------------- projetos

def _generica(cwd: str) -> bool:
    """Pasta guarda-chuva, nao projeto.

    Rodar o claude uma vez na raiz do Desktop nao faz do Desktop um projeto, e
    um card "Desktop" no painel nao leva a lugar nenhum.
    """
    p = Path(cwd).resolve()
    lar = Path.home().resolve()
    return p == lar or p.parent == p or p in {
        lar / "Desktop", lar / "Documents", lar / "Downloads",
        lar / "Documentos", lar / "Downloads"}


_rec_cache: list = []
_rec_ate = 0.0


def recentes(limite: int = 10) -> list:
    """Pastas onde voce ja rodou o Claude, mais recente primeiro.

    Sai de ~/.claude/projects, nao de uma varredura do Desktop: a lista ja vem
    filtrada pelo unico criterio que importa aqui - voce trabalhou ali.

    GUARDADA POR 30 s. A varredura custa 12,5 ms - abre uma pasta por projeto e
    le a cauda do transcript de cada um so para descobrir o cwd - e o painel
    remonta a home a cada 700 ms para saber se o layout mudou. Sem o cache,
    isso era quase 2% de um core queimado para redescobrir a mesma lista. Pasta
    nova aparece no proximo meio minuto.
    """
    global _rec_cache, _rec_ate
    agora = time.monotonic()
    if _rec_cache and agora < _rec_ate:
        return _rec_cache[:limite]
    if not DIR_PROJETOS.is_dir():
        return []
    achados = []
    for pasta in DIR_PROJETOS.iterdir():
        if not pasta.is_dir():
            continue
        jsonls = list(pasta.glob("*.jsonl"))
        if not jsonls:
            continue
        novo = max(jsonls, key=lambda p: p.stat().st_mtime)
        # O cwd real vem de dentro do transcript: reverter o slug e impossivel
        # (nao da para saber se o '-' era barra, espaco ou ponto).
        cwd = ""
        for e in _cauda(novo, 64 * 1024):
            if e.get("cwd"):
                cwd = e["cwd"]
                break
        if not cwd or not Path(cwd).is_dir() or _generica(cwd):
            continue
        achados.append({"cwd": cwd, "nome": Path(cwd).name,
                        "quando": novo.stat().st_mtime})
    achados.sort(key=lambda x: x["quando"], reverse=True)
    _rec_cache, _rec_ate = achados, agora + 30.0
    return achados[:limite]


def uso_hoje() -> dict:
    """Mensagens, sessoes e tokens do dia, do cache de stats do proprio CLI."""
    vazio = {"msgs": 0, "sessoes": 0, "tools": 0, "tokens": 0, "dia": ""}
    try:
        s = json.loads((RAIZ / "stats-cache.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return vazio
    dias = s.get("dailyActivity") or []
    if not dias:
        return vazio
    ult = max(dias, key=lambda d: d.get("date", ""))
    tokens = 0
    for d in s.get("dailyModelTokens") or []:
        if d.get("date") == ult.get("date"):
            tokens = sum(int(v) for v in (d.get("tokensByModel") or {}).values())
    return {"msgs": int(ult.get("messageCount") or 0),
            "sessoes": int(ult.get("sessionCount") or 0),
            "tools": int(ult.get("toolCallCount") or 0),
            "tokens": tokens, "dia": ult.get("date", "")}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t0 = time.monotonic()
    ss = vivas()
    for s in ss:
        print("[{:12s}] {:18s} pid={:<6d} {}/{} ctx={}k  ha {:.0f}s".format(
            s["estado"], s["nome"], s["pid"], modelo_curto(s["modelo"]),
            s["effort"], s["ctx"] // 1000, s["desde"]))
        print("   " + s["titulo"])
        print("   > " + s["prompt"][:90])
    print("\n{} sessoes em {:.0f} ms".format(ss and len(ss) or 0,
                                             (time.monotonic() - t0) * 1000))
    print("recentes:", [p["nome"] for p in recentes()])
    print("hoje:", uso_hoje())
