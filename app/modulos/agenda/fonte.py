"""Agenda: .ics ou login no Google. Vindo do vivos.py do agente."""

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

class Agenda:
    """Proximas reunioes, de um calendario .ics (Google Agenda: Configuracoes
    da agenda > "Endereco secreto no formato iCal"). Sem OAuth, sem chave.

    Le numa thread a cada `atualiza_min`; expande recorrencias com a
    recurring-ical-events. Sem URL no config, o card explica como configurar.
    """

    def __init__(self, cfg: dict | None = None, segredos: Path | None = None):
        c = cfg or {}
        self.url = (c.get("ics_url") or "").strip()
        # Rota 2: login no Google (OAuth) - para conta Workspace em que o admin
        # escondeu o endereco secreto iCal. Precisa do client_secret.json de um
        # projeto no Google Cloud (ver README) e de um login no navegador, uma vez.
        # tokens e client_secret moram em DADOS/segredos (caminho relativo = la)
        base = Path(segredos) if segredos else Path(__file__).resolve().parent
        self.google_secret = c.get("google_client_secret") or ""
        self.google_token = str(base / "google_token.json")
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
