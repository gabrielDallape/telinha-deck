"""
API local do nucleo, para a janela do app. So escuta em 127.0.0.1 e exige o
token que o nucleo sorteia a cada arranque (gravado em DADOS/api.json, que so
o usuario le). A janela abre em http://127.0.0.1:<porta>/?token=<token>.

Nada aqui escreve na serial: toque, navegacao e perfil novo viram recado para
a thread da placa (ou para a tela virtual, sem placa).

Leitura
    GET  /api/tudo                  status, pagina na tela, estado, paginas, modulos
    GET  /api/pagina/<id>           layout + botoes completos (esquema 2)
    GET  /api/arte?c=<id>&v=<ver>   o JPEG que a placa recebe
    GET  /api/catalogo              widgets, acoes (com formulario), icones, biblioteca
    GET  /api/apps                  apps do Menu Iniciar
    GET  /api/icone_app?nome=       o icone de um app, em PNG
    GET  /api/modulos               modulos com a configuracao de cada um
    POST /api/previa {pagina, botao, aceso?}   o card como vai ficar, sem salvar
Placa
    POST /api/toque   {pagina, botao}          como se o dedo tocasse
    POST /api/navegar {pagina}
Perfil (cada mudanca entra no desfazer)
    POST /api/botao       {pagina, botao, pos?}       cria ou troca um botao
    POST /api/apagar      {pagina, botao}
    POST /api/mover       {pagina, botao, pos}        arrastar; ocupado = troca
    POST /api/para_pasta  {pagina, botao, destino}    soltar em cima de uma pasta
    POST /api/pasta       {pagina, pos, titulo}       pagina nova + botao que leva a ela
    POST /api/pagina_nova {titulo, grade?}
    POST /api/pagina_editar {pagina, titulo?, grade?}
    POST /api/pagina_apagar {pagina}
    POST /api/modulo      {id, cfg}
    POST /api/pacote      {id, ativo}
    POST /api/desfazer    POST /api/refazer
"""

from __future__ import annotations

import asyncio
import copy
import io
import json
import secrets
import socket
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import arte, caminhos
from .compositor import grade_para, tamanho_botao

PORTA_PREFERIDA = 47800
FORA_APPS = ("uninstall", "desinstalar", "readme", "leia-me", "help", "ajuda", "website",
             "documentation", "documentacao", "license", "release notes", "manual")


def _porta() -> int:
    for p in (PORTA_PREFERIDA, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("sem porta livre")


def cria(n) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    token = n.api_token
    icones_app: dict = {}

    @app.middleware("http")
    async def exige_token(req: Request, prox):
        if req.url.path.startswith("/api/"):
            if req.headers.get("x-token") != token and req.query_params.get("token") != token:
                return JSONResponse({"erro": "token"}, status_code=401)
        return await prox(req)

    def _limpa(pag: dict) -> dict:
        return {k: v for k, v in pag.items() if not k.startswith("_") or k == "_vivos"}

    # ----------------------------------------------------------- leitura

    @app.get("/api/tudo")
    def tudo():
        lig = n.lig
        pid = lig.pagina_atual or n.inicio()
        pag = n.comp.pagina(pid) or {}
        pags = n.perfil["paginas"]
        return {
            "conectado": lig.placa,
            "porta": getattr(getattr(lig, "ser", None), "port", ""),
            "fw": getattr(lig, "fw", ""),
            "pagina": pid,
            "inicio": n.inicio(),
            "layout": _limpa(pag),
            "barra": n.comp.texto_barra(),
            "estado": n.coletor.ultimo()[1],
            "paginas": [{"id": p, "titulo": (pags[p].get("titulo") or "").strip() or p,
                         "pacote": pags[p].get("_pacote", ""), "gerada": bool(pags[p].get("gerar")),
                         "voltar": pags[p].get("voltar", ""),
                         "do_usuario": p in n.perfil_usuario.get("paginas", {})}
                        for p in n.comp.paginas()],
            "modulos": [{"id": mid, "nome": m.get("nome", mid), "ligado": mid in n.hosp.ligados,
                         "erro": n.hosp.erros.get(mid, "")}
                        for mid, m in sorted(n.hosp.manifestos.items())],
            "pacotes": n.perfil.get("_pacotes", []),
            "pode_desfazer": bool(n.desfazer_pilha),
            "pode_refazer": bool(n.refazer_pilha),
        }

    @app.get("/api/pagina/{pid}")
    def pagina(pid: str):
        pag = n.comp.pagina(pid)
        if not pag:
            raise HTTPException(404, "pagina desconhecida")
        cru = n.perfil["paginas"][pid]
        fixos = {b.get("id") for b in cru.get("botoes", [])}
        # _fixo: esta no perfil (editavel); sem ele, veio de um provedor (sons, cenas)
        botoes = []
        for b in pag["buttons"]:
            if b["id"] == "_vazio":
                botoes.append(None)
            else:
                botoes.append({**n.comp.botao(pid, b["id"]), "_fixo": b["id"] in fixos})
        return {**_limpa(pag), "botoes": botoes, "gerar": cru.get("gerar", ""),
                "pacote": cru.get("_pacote", ""), "do_usuario": pid in n.perfil_usuario.get("paginas", {})}

    @app.get("/api/arte")
    def arte_(c: str, v: str = ""):
        dados = n.comp.arte(c, v or None, espera=5.0)
        if not dados:
            raise HTTPException(404, "arte nao pronta")
        return Response(dados, media_type="image/jpeg",
                        headers={"Cache-Control": "max-age=3600" if not v else "no-store"})

    @app.get("/api/catalogo")
    def catalogo():
        """Tudo que a janela oferece: widgets, acoes (com o formulario de cada
        uma), icones (com o codepoint da Phosphor) e a biblioteca de botoes."""
        h = n.hosp
        acoes = [{"id": "page", "modulo": "", "rotulo": "Ir para uma página",
                  "campos": {"page": {"tipo": "pagina", "rotulo": "Página"}}}]
        for a, (mid, _) in sorted(h.acoes.items()):
            esq = h.manifestos[mid].get("acoes") or {}
            esq = esq.get(a, {}) if isinstance(esq, dict) else {}
            acoes.append({"id": a, "modulo": mid, "rotulo": esq.get("rotulo", a),
                          "campos": esq.get("campos")})
        roxo = {"widget": "icone", "icon": "apps", "color": "#7C66DC"}
        biblioteca = [
            {"id": "pagina", "nome": "Ir para página", "descricao": "Leva a outra página do painel.",
             "categoria": "Navegação", "icone": "apps",
             "botao": {"aparencia": {**roxo, "label": "Página"},
                       "toque": [{"type": "page", "page": n.inicio()}]}},
            {"id": "pasta", "nome": "Pasta", "descricao": "Uma página nova dentro desta, para agrupar botões.",
             "categoria": "Navegação", "icone": "apps", "pasta": True,
             "botao": {"aparencia": {**roxo, "label": "Pasta"}, "toque": []}},
        ]
        for mid, m in sorted(h.manifestos.items()):
            if mid not in h.modulos:
                continue
            for it in m.get("biblioteca") or []:
                biblioteca.append({**it, "modulo": mid, "id": f"{mid}.{it['id']}"})
        entradas = {b.get("_pacote"): b for b in
                    (n.perfil["paginas"].get("apps") or {}).get("botoes", [])}
        for r in n.perfil.get("_pacotes", []):
            if r["ativo"] and r["id"] in n.perfil.get("paginas", {}):
                ap = (entradas.get(r["id"]) or {}).get("aparencia") or {**roxo, "label": r["nome"]}
                biblioteca.append({
                    "id": f"pacote.{r['id']}", "nome": r["nome"], "categoria": "Pacotes de apps",
                    "descricao": f"Abre a página do {r['nome']}, com os atalhos dele.",
                    "icone": "apps", "modulo": "", "icone_app": ap.get("icon_app", ""),
                    "botao": {"aparencia": dict(ap), "toque": [{"type": "page", "page": r["id"]}]}})
        return {
            "widgets": [{"id": "icone", "modulo": "", "nome": "Ícone"}] +
                       [{"id": w, "modulo": mid, "nome": h.manifestos[mid].get("nome", mid)}
                        for w, (mid, _) in sorted(h.widgets.items())],
            "acoes": acoes,
            "icones": [{"nome": k, "cp": v} for k, v in sorted(arte.PH.items())],
            "biblioteca": biblioteca,
        }

    @app.get("/api/apps")
    def apps():
        from .apps import _indexar
        nomes = {lnk.stem for lnk in _indexar().values()
                 if not any(f in lnk.stem.lower() for f in FORA_APPS)}
        return sorted(nomes, key=str.lower)

    @app.get("/api/icone_app")
    def icone_app(nome: str):
        if nome not in icones_app:
            from . import icones
            png = b""
            try:
                exe = icones.resolver_exe(nome)
                img = icones.icone_rgba(exe, 64) if exe else None
                if img is not None:
                    buf = io.BytesIO()
                    img.save(buf, "PNG")
                    png = buf.getvalue()
            except Exception:
                pass
            icones_app[nome] = png
        if not icones_app[nome]:
            raise HTTPException(404, "sem icone")
        return Response(icones_app[nome], media_type="image/png",
                        headers={"Cache-Control": "max-age=86400"})

    @app.post("/api/previa")
    async def previa(req: Request):
        """O card como vai ficar, sem salvar: o editor mostra enquanto voce mexe."""
        d = await req.json()
        pag = n.comp.pagina(d.get("pagina", "")) or {}
        g = pag.get("grid") or grade_para(1)
        w, h = tamanho_botao(g["cols"], g["rows"])
        try:
            img = await asyncio.to_thread(n.comp.desenha, d["botao"], w, h, bool(d.get("aceso")))
        except Exception as e:
            raise HTTPException(400, f"nao desenhou: {e}")
        return Response(arte.para_jpeg(img, 88), media_type="image/jpeg")

    @app.get("/api/modulos")
    def modulos():
        h = n.hosp
        return [{"id": mid, "nome": m.get("nome", mid), "versao": m.get("versao", ""),
                 "ligado": mid in h.ligados, "erro": h.erros.get(mid, ""),
                 "config": m.get("config") or {},
                 "valores": h.modulos[mid].cfg if mid in h.modulos else {},
                 "itens": len(m.get("biblioteca") or [])}
                for mid, m in sorted(h.manifestos.items())]

    # ------------------------------------------------------------- placa

    @app.post("/api/toque")
    async def toque(req: Request):
        d = await req.json()
        n.lig.recado({"_toque": [d["pagina"], d["botao"]]})
        return {"ok": True}

    @app.post("/api/navegar")
    async def navegar(req: Request):
        d = await req.json()
        if not n.comp.pagina(d["pagina"]):
            raise HTTPException(404, "pagina desconhecida")
        n.lig.recado({"_navegar": d["pagina"]})
        return {"ok": True}

    # ------------------------------------------------------------ perfil

    def _pagina_do_usuario(p: dict, pid: str) -> dict:
        """Pagina de pacote editada vira copia no perfil (a do perfil ganha)."""
        pags = p.setdefault("paginas", {})
        if pid not in pags:
            if pid not in n.perfil.get("paginas", {}):
                raise HTTPException(404, "pagina desconhecida")
            pags[pid] = copy.deepcopy(n.perfil["paginas"][pid])
        return pags[pid]

    def _fixa(pag: dict, pid: str) -> dict:
        """Primeira edicao pela janela: a grade e as posicoes que estao na tela
        ficam escritas, para nada pular de lugar quando um botao entra ou sai."""
        fixos = [b for b in pag.get("botoes", []) if not b.get("desligado")]
        if not pag.get("grade"):
            pag["grade"] = (n.comp.pagina(pid) or {}).get("grid") or grade_para(len(fixos))
        for i, b in enumerate(n.comp.posiciona(fixos, pag["grade"])):
            if b is not None:
                b["pos"] = i
        return pag

    def _editar(pid: str):
        p = copy.deepcopy(n.perfil_usuario)
        return p, _fixa(_pagina_do_usuario(p, pid), pid)

    def _novo_id(base: str) -> str:
        usados = {b.get("id") for pg in n.perfil.get("paginas", {}).values() for b in pg.get("botoes", [])}
        base = "".join(c if c.isalnum() else "_" for c in base.lower()).strip("_")[:24] or "botao"
        i, nid = 2, base
        while nid in usados:
            nid, i = f"{base}{i}", i + 1
        return nid

    def _slug(t: str) -> str:
        base = "".join(c if c.isalnum() else "_" for c in t.lower()).strip("_")[:20] or "pagina"
        i, pid = 2, base
        while pid in n.perfil.get("paginas", {}):
            pid, i = f"{base}{i}", i + 1
        return pid

    @app.post("/api/botao")
    async def botao(req: Request):
        d = await req.json()
        b = d["botao"]
        if not isinstance(b.get("aparencia"), dict):
            raise HTTPException(400, "botao precisa de aparencia")
        b = {k: v for k, v in b.items() if not k.startswith("_") or k == "_comment"}
        if not b.get("id"):
            b["id"] = _novo_id(b["aparencia"].get("label") or "botao")
        p, pag = _editar(d["pagina"])
        lista = pag.setdefault("botoes", [])
        i = next((k for k, x in enumerate(lista) if x.get("id") == b["id"]), None)
        if i is not None:
            b.setdefault("pos", lista[i].get("pos"))
            lista[i] = b
        else:
            if isinstance(d.get("pos"), int):
                b["pos"] = d["pos"]
            lista.append(b)
        n.aplicar_perfil(p)
        return {"ok": True, "id": b["id"]}

    @app.post("/api/apagar")
    async def apagar(req: Request):
        d = await req.json()
        p, pag = _editar(d["pagina"])
        pag["botoes"] = [x for x in pag.get("botoes", []) if x.get("id") != d["botao"]]
        n.aplicar_perfil(p)
        return {"ok": True}

    @app.post("/api/mover")
    async def mover(req: Request):
        d = await req.json()
        p, pag = _editar(d["pagina"])
        lista = pag.get("botoes", [])
        b = next((x for x in lista if x.get("id") == d["botao"]), None)
        if b is None:
            raise HTTPException(404, "botao nao esta nesta pagina")
        outro = next((x for x in lista if x.get("pos") == d["pos"] and x is not b), None)
        if outro is not None:
            outro["pos"] = b.get("pos")
        b["pos"] = int(d["pos"])
        n.aplicar_perfil(p)
        return {"ok": True}

    @app.post("/api/para_pasta")
    async def para_pasta(req: Request):
        d = await req.json()
        p, de = _editar(d["pagina"])
        b = next((x for x in de.get("botoes", []) if x.get("id") == d["botao"]), None)
        if b is None:
            raise HTTPException(404, "botao nao esta nesta pagina")
        para = _pagina_do_usuario(p, d["destino"])
        de["botoes"].remove(b)
        b.pop("pos", None)
        para.setdefault("botoes", []).append(b)
        n.aplicar_perfil(p)
        return {"ok": True}

    @app.post("/api/pasta")
    async def pasta(req: Request):
        d = await req.json()
        titulo = (d.get("titulo") or "Pasta").strip()
        p, pag = _editar(d["pagina"])
        pid = _slug(titulo)
        p["paginas"][pid] = {"titulo": titulo, "voltar": d["pagina"],
                             "grade": {"cols": 4, "rows": 3}, "botoes": []}
        ap = {"widget": "icone", "icon": "apps", "label": titulo, "color": "#7C66DC",
              **(d.get("aparencia") or {})}
        novo = {"id": _novo_id("pasta_" + titulo), "aparencia": ap,
                "toque": [{"type": "page", "page": pid}]}
        if isinstance(d.get("pos"), int):
            novo["pos"] = d["pos"]
        pag.setdefault("botoes", []).append(novo)
        n.aplicar_perfil(p)
        return {"ok": True, "pagina": pid, "id": novo["id"]}

    @app.post("/api/pagina_nova")
    async def pagina_nova(req: Request):
        d = await req.json()
        titulo = (d.get("titulo") or "Página").strip()
        p = copy.deepcopy(n.perfil_usuario)
        pid = _slug(titulo)
        p.setdefault("paginas", {})[pid] = {"titulo": titulo, "voltar": n.inicio(),
                                            "grade": d.get("grade") or {"cols": 4, "rows": 3},
                                            "botoes": []}
        n.aplicar_perfil(p)
        return {"ok": True, "pagina": pid}

    @app.post("/api/pagina_editar")
    async def pagina_editar(req: Request):
        d = await req.json()
        p, pag = _editar(d["pagina"])
        if "titulo" in d:
            pag["titulo"] = d["titulo"]
        if d.get("grade"):
            g = {"cols": max(1, min(6, int(d["grade"]["cols"]))),
                 "rows": max(1, min(4, int(d["grade"]["rows"])))}
            if g["cols"] * g["rows"] > 20:
                raise HTTPException(400, "no máximo 20 botões por página (limite da placa)")
            pag["grade"] = g
            # botao que ficou fora da grade nova vai para o primeiro quadrado livre
            for b in pag.get("botoes", []):
                if isinstance(b.get("pos"), int) and b["pos"] >= g["cols"] * g["rows"]:
                    b.pop("pos")
        n.aplicar_perfil(p)
        return {"ok": True}

    @app.post("/api/pagina_apagar")
    async def pagina_apagar(req: Request):
        d = await req.json()
        pid = d["pagina"]
        if pid in (n.inicio(), "descanso"):
            raise HTTPException(400, "esta página não pode ser apagada")
        p = copy.deepcopy(n.perfil_usuario)
        if pid not in p.get("paginas", {}):
            raise HTTPException(400, "é página de um pacote: desligue o pacote em Módulos")
        del p["paginas"][pid]
        for pag in p["paginas"].values():
            pag["botoes"] = [b for b in pag.get("botoes", [])
                             if not any(s.get("page") == pid for s in b.get("toque", []))]
        n.aplicar_perfil(p)
        if n.lig.pagina_atual == pid:
            n.lig.recado({"_navegar": n.inicio()})
        return {"ok": True}

    @app.post("/api/desfazer")
    def desfazer():
        return {"ok": n.desfazer()}

    @app.post("/api/refazer")
    def refazer():
        return {"ok": n.refazer()}

    @app.post("/api/modulo")
    async def modulo(req: Request):
        d = await req.json()
        p = copy.deepcopy(n.perfil_usuario)
        mods = p.setdefault("modulos", {})
        mods[d["id"]] = {**(mods.get(d["id"]) or {}), **d["cfg"]}
        n.aplicar_perfil(p)
        return {"ok": True}

    @app.post("/api/pacote")
    async def pacote(req: Request):
        d = await req.json()
        p = copy.deepcopy(n.perfil_usuario)
        opc = p.setdefault("pacotes", {})
        desl, forc = set(opc.get("desligados", [])), set(opc.get("forcar", []))
        instalado = any(r["id"] == d["id"] and r["instalado"] for r in n.perfil.get("_pacotes", []))
        if d["ativo"]:
            desl.discard(d["id"])
            if not instalado:
                forc.add(d["id"])
        else:
            desl.add(d["id"])
            forc.discard(d["id"])
        opc["desligados"], opc["forcar"] = sorted(desl), sorted(forc)
        n.aplicar_perfil(p)
        return {"ok": True}

    @app.get("/fonte/phosphor.ttf")
    def fonte():
        return Response((caminhos.FONTES / "Phosphor-Fill.ttf").read_bytes(), media_type="font/ttf",
                        headers={"Cache-Control": "max-age=86400"})

    web = caminhos.PROGRAMA / "telinha" / "web"
    if web.is_dir():
        app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
    return app


def comeca(n) -> None:
    import uvicorn
    n.api_token = secrets.token_urlsafe(18)
    porta = _porta()
    srv = uvicorn.Server(uvicorn.Config(cria(n), host="127.0.0.1", port=porta,
                                        log_level="warning", access_log=False))
    threading.Thread(target=srv.run, daemon=True, name="api").start()
    caminhos.API.write_text(json.dumps({"porta": porta, "token": n.api_token}), encoding="utf-8")
    print(f"[api] http://127.0.0.1:{porta}")
