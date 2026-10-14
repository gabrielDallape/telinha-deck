"""Clima pelo Open-Meteo, sem chave; cidade pelo IP se lat/lon vazios. Vindo do vivos.py do agente."""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Codigos WMO que a Open-Meteo devolve -> (texto, familia do desenho)
CODIGOS = {
    0: ("Céu limpo", "sol"),
    1: ("Quase limpo", "sol"),
    2: ("Parcialmente nublado", "sol_nuvem"),
    3: ("Nublado", "nuvem"),
    45: ("Neblina", "neblina"), 48: ("Neblina", "neblina"),
    51: ("Chuvisco", "chuva"), 53: ("Chuvisco", "chuva"), 55: ("Chuvisco", "chuva"),
    56: ("Chuvisco gelado", "chuva"), 57: ("Chuvisco gelado", "chuva"),
    61: ("Chuva fraca", "chuva"), 63: ("Chuva", "chuva"), 65: ("Chuva forte", "chuva"),
    66: ("Chuva gelada", "chuva"), 67: ("Chuva gelada", "chuva"),
    71: ("Neve fraca", "neve"), 73: ("Neve", "neve"), 75: ("Neve forte", "neve"),
    77: ("Granizo", "neve"),
    80: ("Pancadas", "chuva"), 81: ("Pancadas", "chuva"), 82: ("Pancadas fortes", "chuva"),
    85: ("Neve", "neve"), 86: ("Neve", "neve"),
    95: ("Tempestade", "tempestade"), 96: ("Tempestade", "tempestade"),
    99: ("Tempestade", "tempestade"),
}


class Clima:
    """Tempo agora e o resumo do dia, da Open-Meteo (sem chave).

    Sem lat/lon no config, descobre a cidade pelo IP (ip-api.com) uma vez.
    Falhou a rede: fica com o ultimo valor bom, e o card diz ha quanto tempo.
    """

    def __init__(self, cfg: dict | None = None):
        c = cfg or {}
        self.lat = c.get("lat")
        self.lon = c.get("lon")
        self.cidade = c.get("cidade") or ""
        self.intervalo = max(5, int(c.get("atualiza_min", 15))) * 60
        self._dados: dict = {}
        self._versao = ""
        self._lock = threading.Lock()
        self._vivo = False
        self.erro = ""

    def comeca(self) -> None:
        if self._vivo:
            return
        self._vivo = True
        threading.Thread(target=self._roda, daemon=True, name="clima").start()

    def _roda(self) -> None:
        while True:
            try:
                self._passo()
                self.erro = ""
                espera = self.intervalo
            except Exception as e:
                self.erro = str(e)[:80]
                print(f"[clima] {e}")
                espera = 120          # falhou: tenta de novo em 2 min
            time.sleep(espera)

    def _geo(self) -> None:
        g = json.load(urllib.request.urlopen(
            "http://ip-api.com/json/?fields=status,city,lat,lon", timeout=8))
        if g.get("status") != "success":
            raise RuntimeError("geolocalizacao falhou")
        self.lat, self.lon = g["lat"], g["lon"]
        if not self.cidade:
            self.cidade = g.get("city", "")

    def _passo(self) -> None:
        if self.lat is None or self.lon is None:
            self._geo()
        q = urllib.parse.urlencode({
            "latitude": self.lat, "longitude": self.lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                       "is_day,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,"
                     "precipitation_probability_max",
            "timezone": "auto", "forecast_days": 1,
        })
        w = json.load(urllib.request.urlopen(
            "https://api.open-meteo.com/v1/forecast?" + q, timeout=10))
        cur, dia = w["current"], w["daily"]
        codigo = int(cur.get("weather_code", 0))
        texto, familia = CODIGOS.get(codigo, ("Tempo", "nuvem"))
        d = {
            "temp": int(round(cur["temperature_2m"])),
            "sensacao": int(round(cur.get("apparent_temperature", cur["temperature_2m"]))),
            "umidade": int(cur.get("relative_humidity_2m", 0)),
            "vento": int(round(cur.get("wind_speed_10m", 0))),
            "dia": bool(cur.get("is_day", 1)),
            "codigo": codigo, "texto": texto, "familia": familia,
            "max": int(round(dia["temperature_2m_max"][0])),
            "min": int(round(dia["temperature_2m_min"][0])),
            "chuva": int(dia.get("precipitation_probability_max", [0])[0] or 0),
            "cidade": self.cidade,
            "quando": time.time(),
        }
        chave = f"{d['temp']}|{d['codigo']}|{d['dia']}|{d['max']}|{d['min']}|{d['chuva']}"
        with self._lock:
            self._dados = d
            self._versao = hashlib.sha1(chave.encode()).hexdigest()[:8]

    @property
    def versao(self) -> str:
        with self._lock:
            return self._versao or "vazio"

    def dados(self) -> dict:
        with self._lock:
            return dict(self._dados)


# ---------------------------------------------------------------------- foco
