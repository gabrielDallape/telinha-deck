"""Fontes vivas da home: relogio, clima e o timer de foco.

Um card vivo tem id FIXO na placa e muda de conteudo. Cada fonte aqui expoe:

    .versao   string curta que muda exatamente quando o card tem de ser
              redesenhado ("1432" para o relogio, um hash para o clima)
    .dados()  o que a arte desenha, num dict

Quem compara versoes e manda a arte nova e a `Ligacao` (telinha_agent.py): ela
guarda a versao que a placa tem de cada id e, quando difere da atual, manda a
imagem com `i=0` direto - a placa troca o sprite e redesenha SO aquele card,
sem piscar a tela. E o mesmo caminho do card de musica.

A leitura do clima e de rede e roda numa thread; o relogio e o foco sao
calculo puro e nao precisam de thread.
"""

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

# ------------------------------------------------------------------- relogio

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


class Relogio:
    @property
    def versao(self) -> str:
        return time.strftime("%H%M")

    def dados(self) -> dict:
        t = time.localtime()
        return {"hora": time.strftime("%H:%M", t),
                "dia_semana": DIAS[t.tm_wday],
                "data": f"{t.tm_mday} de {MESES[t.tm_mon - 1]}"}


# --------------------------------------------------------------------- clima

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

class Foco:
    """Pomodoro de um toque: toque comeca, toque de novo cancela.

    Tres estados - parado, rodando, acabou. O card mostra os minutos que faltam
    e muda de versao uma vez por minuto (um card de ~8 KB por minuto: nada).
    Quando acaba, `aviso()` devolve a mensagem UMA vez, para a barra da tela.
    """

    def __init__(self, minutos: int = 25):
        self.total = max(1, int(minutos)) * 60
        self.estado = "parado"
        self.fim = 0.0
        self.acabou_em = 0.0
        self._aviso = ""

    def _tick(self) -> None:
        agora = time.time()
        if self.estado == "rodando" and agora >= self.fim:
            self.estado = "acabou"
            self.acabou_em = agora
            self._aviso = f"Foco: {self.total // 60} min. Pausa!"
        elif self.estado == "acabou" and agora - self.acabou_em > 600:
            self.estado = "parado"      # dez minutos depois, volta sozinho

    def toque(self) -> str:
        self._tick()
        if self.estado == "parado":
            self.estado = "rodando"
            self.fim = time.time() + self.total
            return "comecou"
        self.estado = "parado"
        return "parou"

    def restante(self) -> int:
        self._tick()
        if self.estado != "rodando":
            return 0
        return max(0, int(self.fim - time.time()))

    @property
    def versao(self) -> str:
        self._tick()
        if self.estado == "rodando":
            return f"r{math.ceil(self.restante() / 60)}"
        return self.estado

    def dados(self) -> dict:
        self._tick()
        r = self.restante()
        return {"estado": self.estado,
                "restante_min": math.ceil(r / 60),
                "total_min": self.total // 60,
                "pct": 100.0 * (1 - r / self.total) if self.estado == "rodando"
                       else (100.0 if self.estado == "acabou" else 0.0)}

    def aviso(self) -> str:
        self._tick()
        a, self._aviso = self._aviso, ""
        return a


# -------------------------------------------------------------------- agenda

class Agenda:
    """Proximas reunioes, de um calendario .ics (Google Agenda: Configuracoes
    da agenda > "Endereco secreto no formato iCal"). Sem OAuth, sem chave.

    Le numa thread a cada `atualiza_min`; expande recorrencias com a
    recurring-ical-events. Sem URL no config, o card explica como configurar.
    """

    def __init__(self, cfg: dict | None = None):
        c = cfg or {}
        self.url = (c.get("ics_url") or "").strip()
        # Rota 2: login no Google (OAuth) - para conta Workspace em que o admin
        # escondeu o endereco secreto iCal. Precisa do client_secret.json de um
        # projeto no Google Cloud (ver README) e de um login no navegador, uma vez.
        base = Path(__file__).resolve().parent
        self.google_secret = c.get("google_client_secret") or ""
        self.google_token = str(base / "segredos" / "google_token.json")
        if self.google_secret and not Path(self.google_secret).is_absolute():
            self.google_secret = str(base / self.google_secret)
        self.google_agendas = c.get("google_agendas") or ["primary"]
        self.intervalo = max(1, int(c.get("atualiza_min", 5))) * 60
        self.janela_dias = int(c.get("dias", 7))
        self._eventos: list = []
        self._lock = threading.Lock()
        self._vivo = False
        self.erro = ""
        self.lido_em = 0.0

    @property
    def modo(self) -> str:
        if self.google_secret and Path(self.google_secret).exists():
            return "google"
        return "ics" if self.url else ""

    @property
    def configurado(self) -> bool:
        return bool(self.modo)

    def comeca(self) -> None:
        if self._vivo or not self.configurado:
            return
        self._vivo = True
        threading.Thread(target=self._roda, daemon=True, name="agenda").start()

    def _roda(self) -> None:
        while True:
            try:
                self._passo()
                self.erro = ""
                espera = self.intervalo
            except urllib.error.HTTPError as e:
                # O endereco PUBLICO (/public/basic.ics) da 404 quando a agenda
                # nao e publica - que e o normal. O que funciona sem login e o
                # "Endereco secreto no formato iCal" (/private-<token>/basic.ics).
                if e.code in (401, 403, 404) and "/public/" in self.url:
                    self.erro = "agenda privada: use o Endereco secreto iCal"
                else:
                    self.erro = f"HTTP {e.code}"
                print(f"[agenda] {self.erro}")
                espera = 120
            except Exception as e:
                self.erro = str(e)[:80]
                print(f"[agenda] {e}")
                espera = 120
            time.sleep(espera)

    # ---- Google (OAuth)

    def _credenciais(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        escopo = ["https://www.googleapis.com/auth/calendar.readonly"]
        cred = None
        if Path(self.google_token).exists():
            cred = Credentials.from_authorized_user_file(self.google_token, escopo)
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        if not cred or not cred.valid:
            # abre o navegador UMA vez; o token com refresh fica em segredos/
            flow = InstalledAppFlow.from_client_secrets_file(self.google_secret, escopo)
            cred = flow.run_local_server(port=0, open_browser=True,
                                         authorization_prompt_message="",
                                         success_message="TELINHA ligada a sua agenda. Pode fechar.")
            Path(self.google_token).parent.mkdir(exist_ok=True)
            Path(self.google_token).write_text(cred.to_json(), encoding="utf-8")
        return cred

    def _passo_google(self) -> None:
        import datetime as dt
        cred = self._credenciais()
        agora = dt.datetime.now().astimezone()
        q = urllib.parse.urlencode({
            "timeMin": (agora - dt.timedelta(hours=1)).isoformat(),
            "timeMax": (agora + dt.timedelta(days=self.janela_dias)).isoformat(),
            "singleEvents": "true", "orderBy": "startTime", "maxResults": 25,
        })
        saida = []
        for cal in self.google_agendas:
            url = f"https://www.googleapis.com/calendar/v3/calendars/{urllib.parse.quote(cal, safe='')}/events?{q}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {cred.token}"})
            resp = json.load(urllib.request.urlopen(req, timeout=15))
            for it in resp.get("items", []):
                if it.get("status") == "cancelled":
                    continue
                ini, fim = it.get("start", {}), it.get("end", {})
                if "dateTime" in ini:
                    inicio = dt.datetime.fromisoformat(ini["dateTime"]).astimezone()
                    termino = dt.datetime.fromisoformat(fim["dateTime"]).astimezone() if "dateTime" in fim else inicio + dt.timedelta(hours=1)
                    dia_inteiro = False
                else:
                    inicio = dt.datetime.combine(dt.date.fromisoformat(ini["date"]), dt.time.min).astimezone()
                    termino = dt.datetime.combine(dt.date.fromisoformat(fim["date"]), dt.time.min).astimezone() if "date" in fim else inicio + dt.timedelta(days=1)
                    dia_inteiro = True
                saida.append({"titulo": (it.get("summary") or "(sem titulo)").strip(),
                              "inicio": inicio, "fim": termino, "dia_inteiro": dia_inteiro,
                              "link": it.get("hangoutLink") or it.get("htmlLink", "")})
        saida.sort(key=lambda e: e["inicio"])
        with self._lock:
            self._eventos = saida
            self.lido_em = time.time()

    # ---- .ics

    def _passo(self) -> None:
        if self.modo == "google":
            return self._passo_google()
        import datetime as dt
        import icalendar
        import recurring_ical_events

        dados = urllib.request.urlopen(self.url, timeout=15).read()
        cal = icalendar.Calendar.from_ical(dados)
        agora = dt.datetime.now().astimezone()
        ini = agora - dt.timedelta(hours=1)
        fim = agora + dt.timedelta(days=self.janela_dias)
        saida = []
        for ev in recurring_ical_events.of(cal).between(ini, fim):
            ds = ev.get("DTSTART").dt
            de = ev.get("DTEND").dt if ev.get("DTEND") else None
            dia_inteiro = not isinstance(ds, dt.datetime)
            if dia_inteiro:
                inicio = dt.datetime.combine(ds, dt.time.min).astimezone()
                termino = (dt.datetime.combine(de, dt.time.min).astimezone()
                           if de else inicio + dt.timedelta(days=1))
            else:
                inicio = ds.astimezone() if ds.tzinfo else ds.astimezone()
                termino = ((de.astimezone() if de.tzinfo else de.astimezone())
                           if de else inicio + dt.timedelta(hours=1))
            saida.append({"titulo": str(ev.get("SUMMARY", "")).strip() or "(sem titulo)",
                          "inicio": inicio, "fim": termino, "dia_inteiro": dia_inteiro})
        saida.sort(key=lambda e: e["inicio"])
        with self._lock:
            self._eventos = saida
            self.lido_em = time.time()

    def proximos(self, n: int = 3) -> list:
        import datetime as dt
        agora = dt.datetime.now().astimezone()
        with self._lock:
            evs = [e for e in self._eventos if e["fim"] > agora]
        # reunioes com hora primeiro; dia inteiro so se nao houver outra hoje
        return evs[:n]

    @property
    def versao(self) -> str:
        if not self.configurado:
            return "nao"
        ps = self.proximos()
        chave = "|".join(f"{e['titulo']}@{e['inicio'].isoformat()}" for e in ps)
        # o "em 35 min" muda por minuto
        return hashlib.sha1(f"{chave}|{time.strftime('%H%M')}|{self.erro}".encode()).hexdigest()[:8]

    def dados(self) -> dict:
        import datetime as dt
        agora = dt.datetime.now().astimezone()
        ps = []
        for e in self.proximos():
            faltam = int((e["inicio"] - agora).total_seconds() // 60)
            ps.append({**e, "em_min": faltam,
                       "hoje": e["inicio"].date() == agora.date(),
                       "amanha": e["inicio"].date() == (agora + dt.timedelta(days=1)).date(),
                       "rolando": e["inicio"] <= agora < e["fim"]})
        return {"configurado": self.configurado, "erro": self.erro,
                "lido": bool(self.lido_em), "proximos": ps}


# ------------------------------------------------------------------- sistema

class Sistema:
    """CPU e memoria, via psutil, numa thread. Versao em degraus de 5%: o card
    so e remandado quando o numero que aparece muda."""

    def __init__(self, intervalo: float = 5.0):
        self.intervalo = intervalo
        self._d = {"cpu": 0.0, "ram": 0.0, "ram_gb": 0.0, "ram_total_gb": 0.0}
        self._lock = threading.Lock()
        self._vivo = False

    def comeca(self) -> None:
        if self._vivo:
            return
        self._vivo = True
        threading.Thread(target=self._roda, daemon=True, name="sistema").start()

    def _roda(self) -> None:
        import psutil
        psutil.cpu_percent(None)
        while True:
            try:
                m = psutil.virtual_memory()
                d = {"cpu": psutil.cpu_percent(interval=1.0), "ram": m.percent,
                     "ram_gb": (m.total - m.available) / 2**30, "ram_total_gb": m.total / 2**30}
                with self._lock:
                    self._d = d
            except Exception as e:
                print(f"[sistema] {e}")
            time.sleep(max(0.5, self.intervalo - 1.0))

    def dados(self) -> dict:
        with self._lock:
            return dict(self._d)

    @property
    def versao(self) -> str:
        d = self.dados()
        return f"{int(d['cpu'] // 5) * 5}|{int(d['ram'] // 5) * 5}"
