"""O que esta tocando no Windows: titulo, artista e a CAPA do album.

Le a mesma coisa que aquele painelzinho que aparece quando voce mexe no volume -
a SMTC (System Media Transport Controls). Funciona com Spotify, YouTube no
navegador, players locais: qualquer app que se registre no Windows.

E a capa que faz o card. Sem ela isto e so mais um botao de play com texto;
com ela o painel mostra o que esta tocando do outro lado da mesa.

A leitura e assincrona (API do WinRT) e roda numa thread propria, longe do loop
serial - a primeira chamada leva uns 200 ms e o dedo nao pode esperar por isso.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time

try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _Mgr,
    )
    from winsdk.windows.storage.streams import Buffer, InputStreamOptions

    HAVE_SMTC = True
except Exception:
    HAVE_SMTC = False


async def _ler() -> dict:
    mgr = await _Mgr.request_async()
    ses = mgr.get_current_session()
    if not ses:
        return {}

    props = await ses.try_get_media_properties_async()
    info = ses.get_playback_info()

    # PlaybackStatus.PLAYING == 4. Comparar pelo numero evita depender do nome
    # do enum, que ja mudou entre versoes do winsdk.
    try:
        tocando = int(info.playback_status) == 4
    except Exception:
        tocando = "PLAYING" in str(info.playback_status).upper()

    out = {
        "titulo": (props.title or "").strip(),
        "artista": (props.artist or props.album_artist or "").strip(),
        "album": (props.album_title or "").strip(),
        "tocando": tocando,
        "capa": None,
        "app": str(ses.source_app_user_model_id or ""),
        "pos": None, "dur": None, "lido_em": time.time(),
    }
    # Linha do tempo: posicao e duracao em segundos. Nem todo player informa
    # (o YouTube no navegador as vezes manda so a posicao); ai fica None e o
    # card nao desenha a barra. A posicao so e atualizada pelo app em eventos,
    # entao quem le extrapola com `lido_em` enquanto estiver tocando.
    try:
        tl = ses.get_timeline_properties()
        pos = tl.position.total_seconds()
        dur = tl.end_time.total_seconds() - tl.start_time.total_seconds()
        if dur > 0:
            out["pos"], out["dur"] = max(0.0, pos), dur
    except Exception:
        pass

    # A capa vem como stream, nao como bytes: abre, le em pedacos, fecha.
    if props.thumbnail:
        try:
            fluxo = await props.thumbnail.open_read_async()
            buf = Buffer(fluxo.size)
            await fluxo.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
            out["capa"] = bytes(buf)
        except Exception:
            pass
    return out


def _agora() -> dict:
    if not HAVE_SMTC:
        return {}
    try:
        return asyncio.run(_ler())
    except Exception:
        return {}


class Musica:
    """Estado da faixa atual, atualizado numa thread.

    Quem pergunta le o ultimo valor conhecido e nunca bloqueia: a consulta a
    SMTC custa centenas de milissegundos e nao pode entrar no caminho do dedo.
    """

    def __init__(self, intervalo: float = 2.0):
        self.intervalo = intervalo
        self.spotify = None          # spotify.Spotify, se configurado (liga_spotify)
        self._estado: dict = {}
        self._chave = ""
        self._faixa = ""      # assinatura real da musica
        self._lock = threading.Lock()
        self._vivo = False

    def comeca(self) -> None:
        if self._vivo or not HAVE_SMTC:
            return
        self._vivo = True
        threading.Thread(target=self._roda, daemon=True, name="musica").start()

    def _roda(self) -> None:
        while True:
            try:
                self._passo()
            except Exception as e:
                print(f"[musica] {e}")
            time.sleep(self.intervalo)

    def liga_spotify(self, cfg: dict | None) -> None:
        """Com Client ID no config, o Spotify passa a ser lido pela Web API:
        capa grande, posicao exata, curtida, aleatorio, repetir. Quando ele
        esta tocando, ganha da SMTC; parado, a SMTC (YouTube, aula...) volta."""
        from . import spotify
        sp = spotify.Spotify(cfg, getattr(self, "segredos", None))
        if sp.configurado:
            sp.comeca()
            self.spotify = sp

    def _passo(self) -> None:
        novo = _agora()
        if self.spotify is not None:
            sp = self.spotify.estado
            if sp.get("titulo") and (sp.get("tocando") or not novo.get("titulo")):
                novo = sp
        # A chave entra no id da arte: muda de musica, muda de card. O hash
        # da capa entra junto porque duas faixas podem ter o mesmo titulo.
        if novo.get("titulo"):
            faixa = f"{novo['titulo']}|{novo['artista']}"
            if novo.get("capa"):
                faixa += "|" + hashlib.sha1(novo["capa"]).hexdigest()[:8]
        else:
            faixa = ""
        with self._lock:
            # A chave e a VERSAO do card, nao o id dele: o id na placa e fixo
            # (o proprio botao) e a arte e trocada no lugar quando a versao
            # muda. Entra o "tocando" porque a bolinha verde/cinza faz parte
            # do desenho. Sem faixa, versao vazia: o card vira o play comum.
            self._faixa = faixa
            self._chave = (hashlib.sha1(f"{faixa}|{novo.get('tocando')}".encode())
                           .hexdigest()[:8]) if faixa else ""
            self._estado = novo

    @property
    def estado(self) -> dict:
        with self._lock:
            return dict(self._estado)

    @property
    def chave(self) -> str:
        """Versao do card: muda com a faixa e com tocando/pausado."""
        with self._lock:
            return self._chave

    def posicao(self, e: dict | None = None) -> tuple:
        """(posicao_s, duracao_s) agora, extrapolando desde a ultima leitura."""
        e = e if e is not None else self.estado
        if e.get("pos") is None or not e.get("dur"):
            return None, None
        pos = e["pos"]
        if e.get("tocando"):
            pos += time.time() - e.get("lido_em", time.time())
        return min(pos, e["dur"]), e["dur"]

    @property
    def chave_fina(self) -> str:
        """Versao do PLAYER: alem da faixa, o progresso em degraus de 10 s.
        So o card do player usa; o da home nao precisa andar."""
        base = self.chave
        if not base:
            return ""
        pos, dur = self.posicao()
        return base if pos is None else f"{base}:{int(pos // 10)}"

    def instantanea(self) -> tuple:
        """(chave, estado) lidos JUNTOS.

        Ler os dois em momentos diferentes deixava o JPEG da faixa nova gravado
        no cache sob a chave da faixa velha - e como a chave ja estava no cache,
        o card mostrava a musica errada ate o processo reiniciar.
        """
        with self._lock:
            return self._chave, dict(self._estado)
