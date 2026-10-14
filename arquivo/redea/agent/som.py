"""
Volume por APLICATIVO, que e a coisa util que todo deck caseiro deixa de fora.

O deej resolveu isso com potenciometro fisico e virou padrao do nicho; o
NativMix refez em PyQt. Nenhum dos dois tem tela - e um painel touch de 5" pode
mostrar o que o deej nao mostra: quem esta fazendo barulho AGORA, com o nome e
o icone do app, e o nivel de cada um.

Tudo sai do pycaw (Core Audio do Windows). O mixer de volume do sistema le
exatamente a mesma coisa.

Cuidado com COM: cada thread que tocar nisto precisa de CoInitialize(), e os
ponteiros nao podem ser guardados entre leituras - a sessao de audio some
quando o app fecha, e usar o ponteiro velho derruba o processo com access
violation. Por isso aqui se relista a cada leitura e so se guarda o resultado.
"""

from __future__ import annotations

import time

try:
    from comtypes import CoInitialize, CoUninitialize
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    TEM_PYCAW = True
except Exception:
    TEM_PYCAW = False

# Processos que aparecem no mixer mas nao sao "apps" para quem olha o painel.
IGNORAR = {"", "audiodg.exe", "svchost.exe", "explorer.exe",
           "ShellExperienceHost.exe", "SystemSettings.exe"}

# Nome bonito para os suspeitos de sempre.
BONITO = {
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
    "Discord.exe": "Discord", "Spotify.exe": "Spotify", "steam.exe": "Steam",
    "vlc.exe": "VLC", "Code.exe": "VS Code", "WindowsTerminal.exe": "Terminal",
    "RainbowSix.exe": "R6", "obs64.exe": "OBS", "Teams.exe": "Teams",
    "slack.exe": "Slack", "zoom.exe": "Zoom", "WhatsApp.exe": "WhatsApp",
}

_cache: list = []
_ate = 0.0
_TTL = 1.5


def _nome_bonito(exe: str) -> str:
    if exe in BONITO:
        return BONITO[exe]
    base = exe[:-4] if exe.lower().endswith(".exe") else exe
    return base[:1].upper() + base[1:]


def apps(forcar: bool = False) -> list:
    """Apps com sessao de audio agora: [{exe, nome, vol, mudo, tocando}].

    Guardado por 1,5 s - relistar as sessoes COM custa uns milissegundos e o
    loop serial pergunta a cada volta.
    """
    global _cache, _ate
    agora = time.monotonic()
    if not forcar and _cache and agora < _ate:
        return _cache
    if not TEM_PYCAW:
        return []

    saida = []
    try:
        CoInitialize()
        for s in AudioUtilities.GetAllSessions():
            if not s.Process:
                continue
            try:
                exe = s.Process.name()
            except Exception:
                continue
            if exe in IGNORAR:
                continue
            try:
                v = s.SimpleAudioVolume
                # o medidor de pico diz quem esta REALMENTE fazendo barulho,
                # e nao so quem tem uma sessao de audio aberta parada
                try:
                    pico = s._ctl.QueryInterface(  # noqa: SLF001
                        __import__("pycaw.pycaw", fromlist=["IAudioMeterInformation"])
                        .IAudioMeterInformation).GetPeakValue()
                except Exception:
                    pico = 0.0
                saida.append({"exe": exe, "nome": _nome_bonito(exe),
                              "vol": round(v.GetMasterVolume() * 100),
                              "mudo": bool(v.GetMute()),
                              "pico": float(pico)})
            except Exception:
                continue
    except Exception:
        return _cache

    # quem esta tocando primeiro, depois por nome: a ordem do card nao pode
    # dancar a cada leitura ou a arte e remandada a toa
    saida.sort(key=lambda a: (-(a["pico"] > 0.001), a["nome"].lower()))
    _cache, _ate = saida, agora + _TTL
    return saida


def _sessao_do(exe: str):
    for s in AudioUtilities.GetAllSessions():
        if s.Process:
            try:
                if s.Process.name() == exe:
                    return s
            except Exception:
                continue
    return None


def mudo_app(exe: str) -> bool:
    """Alterna o mudo de um app. Devolve o estado novo."""
    if not TEM_PYCAW:
        raise RuntimeError("pycaw ausente")
    CoInitialize()
    s = _sessao_do(exe)
    if s is None:
        raise RuntimeError("app sem audio")
    v = s.SimpleAudioVolume
    novo = not bool(v.GetMute())
    v.SetMute(1 if novo else 0, None)
    apps(forcar=True)
    return novo


def volume_app(exe: str, delta: int) -> int:
    """Sobe ou desce o volume de um app. Devolve o novo valor, 0 a 100."""
    if not TEM_PYCAW:
        raise RuntimeError("pycaw ausente")
    CoInitialize()
    s = _sessao_do(exe)
    if s is None:
        raise RuntimeError("app sem audio")
    v = s.SimpleAudioVolume
    novo = max(0, min(100, round(v.GetMasterVolume() * 100) + delta))
    v.SetMasterVolume(novo / 100.0, None)
    apps(forcar=True)
    return novo


# --------------------------------------------------------- saida e microfone

_endpoints: dict = {}


def _endpoint(qual: str):
    """O endpoint vive o processo todo.

    Recriar a cada leitura fazia o comtypes derrubar ponteiros COM no __del__
    com access violation - foi o que o JOQUEI apanhou primeiro.
    """
    if qual in _endpoints:
        return _endpoints[qual]
    CoInitialize()
    dev = AudioUtilities.GetMicrophone() if qual == "mic" else AudioUtilities.GetSpeakers()
    pronto = getattr(dev, "EndpointVolume", None)
    if pronto is not None:
        ep = pronto
    else:
        cru = getattr(dev, "_dev", dev)
        ep = cast(cru.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None),
                  POINTER(IAudioEndpointVolume))
    _endpoints[qual] = ep
    return ep


def geral() -> dict:
    """Volume e mudo do sistema e do microfone."""
    if not TEM_PYCAW:
        return {}
    out = {}
    for qual, cm, cv in (("sys", "sys_mudo", "sys_vol"),
                         ("mic", "mic_mudo", "mic_vol")):
        try:
            ep = _endpoint(qual)
            out[cm] = bool(ep.GetMute())
            out[cv] = round(ep.GetMasterVolumeLevelScalar() * 100)
        except Exception:
            _endpoints.clear()
    return out


def mudo_geral(qual: str) -> bool:
    ep = _endpoint(qual)
    novo = 0 if ep.GetMute() else 1
    ep.SetMute(novo, None)
    return bool(novo)


def volume_geral(qual: str, delta: int) -> int:
    ep = _endpoint(qual)
    novo = max(0, min(100, round(ep.GetMasterVolumeLevelScalar() * 100) + delta))
    ep.SetMasterVolumeLevelScalar(novo / 100.0, None)
    return novo


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("geral:", geral())
    for a in apps():
        print("  {:14s} vol {:3d}  {}  pico {:.3f}".format(
            a["nome"], a["vol"], "MUDO" if a["mudo"] else "    ", a["pico"]))
    if not apps():
        print("  (nenhum app com audio agora)")
