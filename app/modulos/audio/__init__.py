"""Microfone e alto-falante padrao do Windows (pycaw): mudo, volume, e o
estado que acende o botao de mic vermelho e a barra de gomos do SOM.

COM: cada thread que toca no pycaw precisa de CoInitialize (o nucleo ja faz
nos workers e no coletor) e o endpoint e guardado POR THREAD. Recriar a cada
leitura derrubava o processo com access violation no __del__; compartilhar um
objeto COM entre apartamentos e pedir o mesmo problema.
"""
import threading
from ctypes import POINTER, cast

from telinha.sdk import Modulo, acao


class Audio(Modulo):
    def iniciar(self):
        from comtypes import CLSCTX_ALL  # noqa: F401  (falha cedo se faltar)
        from pycaw.pycaw import AudioUtilities  # noqa: F401
        self._local = threading.local()

    def _endpoint(self, qual: str):
        cache = getattr(self._local, "eps", None)
        if cache is None:
            cache = self._local.eps = {}
        if qual in cache:
            return cache[qual]
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        dev = AudioUtilities.GetMicrophone() if qual == "mic" else AudioUtilities.GetSpeakers()
        # GetSpeakers() devolve o wrapper (com .EndpointVolume); GetMicrophone(), o IMMDevice cru
        ep = getattr(dev, "EndpointVolume", None)
        if ep is None:
            cru = getattr(dev, "_dev", dev)
            ep = cast(cru.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                      POINTER(IAudioEndpointVolume))
        cache[qual] = ep
        return ep

    def _invalida(self):
        """Dispositivo padrao trocou (fone plugado): refaz na proxima leitura."""
        self._local.eps = {}

    def estado(self) -> dict:
        out = {}
        for qual, mudo, vol in (("sys", "sys_muted", "sys_vol"), ("mic", "mic_muted", "mic_vol")):
            try:
                ep = self._endpoint(qual)
                out[mudo] = bool(ep.GetMute())
                out[vol] = round(ep.GetMasterVolumeLevelScalar() * 100)
            except Exception:
                self._invalida()
        return out

    def _alterna(self, qual):
        ep = self._endpoint(qual)
        ep.SetMute(0 if ep.GetMute() else 1, None)

    @acao("mic_toggle")
    def mic_toggle(self, passo):
        self._alterna("mic")

    @acao("mic_mute")
    def mic_mute(self, passo):
        self._endpoint("mic").SetMute(1, None)

    @acao("mic_unmute")
    def mic_unmute(self, passo):
        self._endpoint("mic").SetMute(0, None)

    @acao("sys_mute_toggle")
    def sys_mute_toggle(self, passo):
        self._alterna("sys")

    @acao("volume")
    def volume(self, passo):
        pct = max(0, min(100, int(passo["value"])))
        self._endpoint(passo.get("device", "sys")).SetMasterVolumeLevelScalar(pct / 100.0, None)
