"""
Soundboard: toca arquivos de som em uma ou mais saidas de audio ao mesmo tempo.

Por que mais de uma saida: o som que toca so no alto-falante, o pessoal da call
ou da live nao ouve. Com um cabo virtual (VB-Audio Cable) na lista, o mesmo som
vai para o "CABLE Input", e o Discord/OBS escutam o "CABLE Output" como se
fosse um microfone. Config:

    "sons": {"saidas": ["padrao", "CABLE Input"], "volume": 80, "pasta": "C:/..."}

`saidas` casa por pedaco do nome (`python -m sounddevice` lista os nomes).
"padrao" e a saida padrao do Windows.

Cada saida tem UM stream aberto e um mixer no callback: sons se sobrepoem, e
tocar de novo o mesmo som enquanto ele toca para ele (modo "alternar", o padrao
de todo soundboard). O arquivo e decodificado uma vez e fica em memoria,
reamostrado para a taxa da saida.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

EXTENSOES = (".wav", ".mp3", ".ogg", ".flac")


class _Saida:
    def __init__(self, sd, indice: int):
        info = sd.query_devices(indice)
        self.nome = info["name"]
        self.taxa = int(info["default_samplerate"])
        self.vozes: list = []           # [chave, amostras (n,2), posicao, ganho]
        self.lock = threading.Lock()
        self.stream = sd.OutputStream(device=indice, samplerate=self.taxa,
                                      channels=2, dtype="float32",
                                      latency="low", callback=self._mistura)
        self.stream.start()

    def _mistura(self, saida, quadros, _tempo, _status):
        saida.fill(0)
        with self.lock:
            vivas = []
            for voz in self.vozes:
                chave, dados, pos, ganho = voz
                pedaco = dados[pos:pos + quadros]
                saida[:len(pedaco)] += pedaco * ganho
                voz[2] = pos + len(pedaco)
                if voz[2] < len(dados):
                    vivas.append(voz)
            self.vozes = vivas
        np.clip(saida, -1.0, 1.0, out=saida)

    def toca(self, chave: str, dados, ganho: float) -> None:
        with self.lock:
            self.vozes.append([chave, dados, 0, ganho])

    def para(self, chave: str | None = None) -> bool:
        with self.lock:
            antes = len(self.vozes)
            self.vozes = [v for v in self.vozes if chave is not None and v[0] != chave]
            return len(self.vozes) != antes

    def tocando(self, chave: str) -> bool:
        with self.lock:
            return any(v[0] == chave for v in self.vozes)


class Mixer:
    def __init__(self, cfg: dict | None):
        import sounddevice as sd
        self.sd = sd
        self.cfg = dict(cfg or {})
        self.saidas: list = []
        self._decod: dict = {}          # (arquivo, mtime, taxa) -> amostras
        self.lock = threading.Lock()
        for nome in self.cfg.get("saidas") or ["padrao"]:
            idx = self._achar(nome)
            if idx is None:
                print(f"[sons] saida '{nome}' nao encontrada")
                continue
            if any(s.indice == idx for s in self.saidas):
                continue
            try:
                s = _Saida(sd, idx)
                s.indice = idx
                self.saidas.append(s)
                print(f"[sons] saida: {s.nome} @ {s.taxa} Hz")
            except Exception as e:
                print(f"[sons] nao abriu '{nome}': {e}")

    def _achar(self, nome: str) -> int | None:
        if nome.lower() in ("padrao", "padrão", "default", ""):
            return self.sd.default.device[1]
        alvo = nome.lower()
        for i, d in enumerate(self.sd.query_devices()):
            if d["max_output_channels"] > 0 and alvo in d["name"].lower():
                return i
        return None

    def _amostras(self, arquivo: str, taxa: int):
        import soundfile as sf
        p = Path(arquivo)
        k = (str(p), p.stat().st_mtime, taxa)
        with self.lock:
            if k in self._decod:
                return self._decod[k]
        dados, origem = sf.read(str(p), dtype="float32", always_2d=True)
        if dados.shape[1] == 1:
            dados = np.repeat(dados, 2, axis=1)
        dados = dados[:, :2]
        if origem != taxa and len(dados) > 1:
            # linear basta para efeito sonoro, e nao puxa scipy
            n = int(len(dados) * taxa / origem)
            x = np.linspace(0, len(dados) - 1, n)
            base = np.arange(len(dados))
            dados = np.stack([np.interp(x, base, dados[:, c]) for c in range(2)],
                             axis=1).astype("float32")
        dados = np.ascontiguousarray(dados)
        with self.lock:
            self._decod[k] = dados
        return dados

    def tocar(self, arquivo: str, volume: int | None = None,
              modo: str = "alternar") -> str:
        """Devolve "tocando" ou "parado" (quando o toque parou o proprio som)."""
        if not self.saidas:
            raise RuntimeError("nenhuma saida de audio")
        if not Path(arquivo).is_file():
            raise RuntimeError(f"som nao encontrado: {Path(arquivo).name}")
        chave = str(Path(arquivo))
        if modo == "alternar" and any(s.tocando(chave) for s in self.saidas):
            for s in self.saidas:
                s.para(chave)
            return "parado"
        if modo == "reiniciar":
            for s in self.saidas:
                s.para(chave)
        vol = self.cfg.get("volume", 100) if volume is None else volume
        ganho = max(0.0, min(1.0, float(vol) / 100.0))
        for s in self.saidas:
            s.toca(chave, self._amostras(arquivo, s.taxa), ganho)
        return "tocando"

    def parar(self) -> bool:
        return any([s.para() for s in self.saidas])


_mixer: Mixer | None = None
_mixer_lock = threading.Lock()


def mixer(cfg: dict | None) -> Mixer:
    """Um mixer por processo; refeito se as saidas do config mudarem."""
    global _mixer
    with _mixer_lock:
        if _mixer is None or _mixer.cfg.get("saidas") != (cfg or {}).get("saidas"):
            for s in (_mixer.saidas if _mixer else []):
                try:
                    s.stream.close()
                except Exception:
                    pass
            _mixer = Mixer(cfg)
        else:
            _mixer.cfg = dict(cfg or {})
        return _mixer


def listar(pastas: list) -> list:
    """[(Path)] dos sons nas pastas, por nome. Pasta que nao existe nao conta."""
    vistos, saida = set(), []
    for pasta in pastas:
        p = Path(pasta)
        if not p.is_dir():
            continue
        for arq in sorted(p.iterdir(), key=lambda a: a.name.lower()):
            if arq.suffix.lower() in EXTENSOES and arq.stem.lower() not in vistos:
                vistos.add(arq.stem.lower())
                saida.append(arq)
    return saida
