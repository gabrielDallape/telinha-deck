"""Spotify pela Web API: o que esta tocando, com capa grande, e os controles finos.

Por que nao bastar o controle de midia do Windows (midia.py): a SMTC entrega
uma miniatura de 150 px e nenhum estado alem de tocando/pausado. A Web API da
capa em 640 px, posicao exata, se a faixa e curtida, aleatorio, repetir, o
dispositivo que esta tocando - e deixa mudar tudo isso. E o que toda "telinha
de Spotify" da internet usa.

Login: Authorization Code com PKCE, que nao precisa de client secret - so do
Client ID de um app criado em https://developer.spotify.com/dashboard com a
redirect URI http://127.0.0.1:<porta>/callback. Na primeira subida o navegador
abre uma vez; o refresh token fica em segredos/spotify_token.json.

Limite honesto: app em "Development mode" so funciona para a conta dona (e ate
5 convidadas). E o caso aqui.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

API = "https://api.spotify.com/v1"
ESCOPOS = ("user-read-playback-state user-modify-playback-state "
           "user-read-currently-playing user-library-read user-library-modify")


class Spotify:
    def __init__(self, cfg: dict | None = None, segredos: Path | None = None):
        c = cfg or {}
        self.client_id = (c.get("client_id") or "").strip()
        self.porta = int(c.get("redirect_port", 8765))
        self.intervalo = float(c.get("intervalo_s", 3.0))
        base = Path(segredos) if segredos else Path(__file__).resolve().parent / "segredos"
        self.token_path = base / "spotify_token.json"
        self._token: dict = {}
        self._estado: dict = {}
        self._capas: dict = {}          # url -> bytes (as ultimas 4)
        self._curtidas: dict = {}       # id da faixa -> bool
        self._lock = threading.Lock()
        self._vivo = False
        self.erro = ""
        self.autorizando = False

    # ------------------------------------------------------------ estado

    @property
    def configurado(self) -> bool:
        return bool(self.client_id)

    @property
    def estado(self) -> dict:
        with self._lock:
            return dict(self._estado)

    @property
    def ativo(self) -> bool:
        """Ha um player do Spotify com faixa (tocando ou pausado ha pouco)."""
        e = self.estado
        return bool(e.get("titulo")) and (e.get("tocando") or time.time() - e.get("lido_em", 0) < 600)

    def comeca(self) -> None:
        if self._vivo or not self.configurado:
            return
        self._vivo = True
        threading.Thread(target=self._roda, daemon=True, name="spotify").start()

    def _roda(self) -> None:
        while True:
            try:
                self._passo()
                self.erro = ""
                espera = self.intervalo if self._estado.get("tocando") else self.intervalo * 2.5
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    espera = float(e.headers.get("Retry-After", 5))
                    self.erro = f"limite da API, esperando {espera:.0f}s"
                elif e.code in (401, 403):
                    self.erro = f"HTTP {e.code}: token"
                    self._token = {}
                    espera = 10
                else:
                    self.erro = f"HTTP {e.code}"
                    espera = 10
                print(f"[spotify] {self.erro}")
            except Exception as e:
                self.erro = str(e)[:80]
                print(f"[spotify] {e}")
                espera = 15
            time.sleep(espera)

    # ------------------------------------------------------------- login

    def _carrega_token(self) -> None:
        if not self._token and self.token_path.exists():
            try:
                self._token = json.loads(self.token_path.read_text(encoding="utf-8"))
            except Exception:
                self._token = {}

    def _salva_token(self, dados: dict) -> None:
        if "refresh_token" not in dados and self._token.get("refresh_token"):
            dados["refresh_token"] = self._token["refresh_token"]
        dados["expires_at"] = time.time() + int(dados.get("expires_in", 3600)) - 60
        self._token = dados
        self.token_path.parent.mkdir(exist_ok=True)
        self.token_path.write_text(json.dumps(dados), encoding="utf-8")

    def _troca(self, form: dict) -> dict:
        req = urllib.request.Request("https://accounts.spotify.com/api/token",
                                     data=urllib.parse.urlencode(form).encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        return json.load(urllib.request.urlopen(req, timeout=15))

    def _autoriza(self) -> None:
        """Abre o navegador UMA vez (PKCE) e espera o callback local."""
        self.autorizando = True
        try:
            verificador = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
            desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).decode().rstrip("=")
            redirect = f"http://127.0.0.1:{self.porta}/callback"
            estado_csrf = secrets.token_urlsafe(12)
            url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
                "client_id": self.client_id, "response_type": "code", "redirect_uri": redirect,
                "scope": ESCOPOS, "code_challenge_method": "S256", "code_challenge": desafio,
                "state": estado_csrf})
            codigo = {}

            class Callback(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                    if q.get("state", [""])[0] == estado_csrf and "code" in q:
                        codigo["code"] = q["code"][0]
                        corpo = "<h2 style='font-family:sans-serif'>TELINHA ligada ao Spotify. Pode fechar.</h2>"
                    else:
                        corpo = "<h2 style='font-family:sans-serif'>Falhou: " + q.get("error", ["?"])[0] + "</h2>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(corpo.encode("utf-8"))

                def log_message(self, *a):
                    pass

            servidor = http.server.HTTPServer(("127.0.0.1", self.porta), Callback)
            servidor.timeout = 180
            print("[spotify] abrindo o navegador para autorizar...")
            webbrowser.open(url)
            servidor.handle_request()
            servidor.server_close()
            if "code" not in codigo:
                raise RuntimeError("autorizacao nao concluida")
            dados = self._troca({"client_id": self.client_id, "grant_type": "authorization_code",
                                 "code": codigo["code"], "redirect_uri": redirect,
                                 "code_verifier": verificador})
            self._salva_token(dados)
            print("[spotify] autorizado")
        finally:
            self.autorizando = False

    def _acesso(self) -> str:
        self._carrega_token()
        if not self._token.get("refresh_token"):
            self._autoriza()
        elif time.time() >= self._token.get("expires_at", 0):
            dados = self._troca({"client_id": self.client_id, "grant_type": "refresh_token",
                                 "refresh_token": self._token["refresh_token"]})
            self._salva_token(dados)
        return self._token["access_token"]

    # --------------------------------------------------------------- API

    def _req(self, metodo: str, caminho: str, params: dict | None = None,
             corpo: dict | None = None):
        url = API + caminho + (("?" + urllib.parse.urlencode(params)) if params else "")
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(url, data=dados, method=metodo,
                                     headers={"Authorization": f"Bearer {self._acesso()}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status == 204 or r.length == 0:
                    return r.status, None
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return 204, None
            raise

    def _capa(self, imagens: list) -> bytes | None:
        """A imagem de ~300 px (basta para 624 px de card e pesa 5x menos que a de 640)."""
        if not imagens:
            return None
        ordenadas = sorted(imagens, key=lambda i: abs((i.get("width") or 300) - 300))
        url = ordenadas[0].get("url")
        if not url:
            return None
        if url not in self._capas:
            self._capas[url] = urllib.request.urlopen(url, timeout=10).read()
            while len(self._capas) > 4:
                self._capas.pop(next(iter(self._capas)))
        return self._capas[url]

    def _passo(self) -> None:
        status, p = self._req("GET", "/me/player", {"additional_types": "track,episode"})
        if status == 204 or not p or not p.get("item"):
            # sem dispositivo ativo: o Spotify nao esta aberto em lugar nenhum
            with self._lock:
                if self._estado and time.time() - self._estado.get("lido_em", 0) > 30:
                    self._estado = {}
            return
        it = p["item"]
        eh_podcast = it.get("type") == "episode"
        artista = it.get("show", {}).get("name", "") if eh_podcast else \
            ", ".join(a.get("name", "") for a in it.get("artists", []))
        imagens = (it.get("images") if eh_podcast else it.get("album", {}).get("images")) or []
        fid = it.get("id", "")
        curtida = None
        if fid and not eh_podcast:
            if fid not in self._curtidas:
                self._curtidas[fid] = self._esta_curtida(fid)
            curtida = self._curtidas[fid]
        e = {
            "titulo": it.get("name", ""),
            "artista": artista,
            "album": "" if eh_podcast else it.get("album", {}).get("name", ""),
            "tocando": bool(p.get("is_playing")),
            "capa": self._capa(imagens),
            "app": "Spotify",
            "pos": (p.get("progress_ms") or 0) / 1000.0,
            "dur": (it.get("duration_ms") or 0) / 1000.0 or None,
            "lido_em": time.time(),
            "faixa_id": fid,
            "sp_curtida": bool(curtida),
            "sp_aleatorio": bool(p.get("shuffle_state")),
            "sp_repetir": p.get("repeat_state", "off"),
            "dispositivo": (p.get("device") or {}).get("name", ""),
            "volume": (p.get("device") or {}).get("volume_percent"),
        }
        with self._lock:
            self._estado = e

    # ---------------------------------------------------------- controles

    def _exige(self) -> dict:
        e = self.estado
        if not e.get("titulo"):
            raise RuntimeError("Spotify nao esta tocando")
        return e

    def play_pause(self) -> None:
        e = self._exige()
        self._req("PUT", "/me/player/pause" if e["tocando"] else "/me/player/play")
        with self._lock:
            self._estado["tocando"] = not e["tocando"]

    def proxima(self) -> None:
        self._exige(); self._req("POST", "/me/player/next")

    def anterior(self) -> None:
        self._exige(); self._req("POST", "/me/player/previous")

    def pular(self, segundos: float) -> None:
        e = self._exige()
        pos = max(0.0, e["pos"] + (time.time() - e["lido_em"] if e["tocando"] else 0) + segundos)
        if e.get("dur"):
            pos = min(pos, e["dur"] - 1)
        self._req("PUT", "/me/player/seek", {"position_ms": int(pos * 1000)})
        with self._lock:
            self._estado["pos"], self._estado["lido_em"] = pos, time.time()

    def _esta_curtida(self, fid: str) -> bool:
        # Fev/2026: a biblioteca passou para /me/library (uris); o /me/tracks
        # antigo ficou "deprecated" mas ainda responde. Tenta o novo, cai no velho.
        for caminho, params in (("/me/library/contains", {"uris": f"spotify:track:{fid}"}),
                                ("/me/tracks/contains", {"ids": fid})):
            try:
                _, c = self._req("GET", caminho, params)
                if isinstance(c, list) and c:
                    return bool(c[0])
            except urllib.error.HTTPError as e:
                if e.code in (400, 404, 405):
                    continue
                raise
        return False

    def curtir_toggle(self) -> bool:
        e = self._exige()
        fid = e.get("faixa_id")
        if not fid:
            raise RuntimeError("podcast nao curte")
        novo = not e.get("sp_curtida")
        metodo = "PUT" if novo else "DELETE"
        try:
            self._req(metodo, "/me/library", {"uris": f"spotify:track:{fid}"})
        except urllib.error.HTTPError as err:
            if err.code not in (400, 404, 405):
                raise
            self._req(metodo, "/me/tracks", {"ids": fid})
        self._curtidas[fid] = novo
        with self._lock:
            self._estado["sp_curtida"] = novo
        return novo

    def aleatorio_toggle(self) -> bool:
        e = self._exige()
        novo = not e.get("sp_aleatorio")
        self._req("PUT", "/me/player/shuffle", {"state": "true" if novo else "false"})
        with self._lock:
            self._estado["sp_aleatorio"] = novo
        return novo

    def repetir_ciclo(self) -> str:
        e = self._exige()
        prox = {"off": "context", "context": "track", "track": "off"}[e.get("sp_repetir", "off")]
        self._req("PUT", "/me/player/repeat", {"state": prox})
        with self._lock:
            self._estado["sp_repetir"] = prox
        return prox

    def volume(self, pct: int) -> None:
        self._exige()
        self._req("PUT", "/me/player/volume", {"volume_percent": max(0, min(100, int(pct)))})
