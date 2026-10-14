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
    }

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
        self._estado: dict = {}
        self._chave = ""
        self._faixa = ""      # assinatura real da musica
        self._giro = 0        # alterna o id do card entre dois valores
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

    def _passo(self) -> None:
        novo = _agora()
        # A chave entra no id da arte: muda de musica, muda de card. O hash
        # da capa entra junto porque duas faixas podem ter o mesmo titulo.
        if novo.get("titulo"):
            faixa = f"{novo['titulo']}|{novo['artista']}"
            if novo.get("capa"):
                faixa += "|" + hashlib.sha1(novo["capa"]).hexdigest()[:8]
        else:
            faixa = ""
        with self._lock:
            if faixa != self._faixa:
                # O id do card ALTERNA entre dois valores em vez de ser o
                # hash da faixa. Um id novo por musica ia comendo os 96
                # slots de sprite da placa, e o que ela despejava para abrir
                # espaco eram os cards do R6 - que o PC ja dava por
                # entregues e nunca remandava. Meia hora de musica deixava
                # o R6 cinza ate reiniciar a placa.
                self._faixa = faixa
                self._giro = (self._giro + 1) % 2
            self._chave = f"ar{self._giro}" if faixa else ""
            self._estado = novo

    @property
    def estado(self) -> dict:
        with self._lock:
            return dict(self._estado)

    @property
    def chave(self) -> str:
        """Id do card. Vazio quando nao ha nada tocando."""
        with self._lock:
            return self._chave

    def instantanea(self) -> tuple:
        """(chave, estado) lidos JUNTOS.

        Ler os dois em momentos diferentes deixava o JPEG da faixa nova gravado
        no cache sob a chave da faixa velha - e como a chave ja estava no cache,
        o card mostrava a musica errada ate o processo reiniciar.
        """
        with self._lock:
            return self._chave, dict(self._estado)
