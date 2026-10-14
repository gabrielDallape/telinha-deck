"""O que esta tocando, de qualquer app (controle de midia do Windows, SMTC), e o
Spotify pela Web API quando configurado: capa nitida, curtir, aleatorio,
repetir. Widget "musica" (estilos: padrao, "player", "controle")."""
import os

from telinha.sdk import Modulo, acao, versao, widget

from .smtc import Musica


class Midia(Modulo):
    def iniciar(self):
        self.m = Musica()
        self.m.segredos = self.ctx.segredos
        self.m.comeca()
        self.m.liga_spotify(self.cfg.get("spotify"))

    # ------------------------------------------------------------- widget

    @widget("musica")
    def desenha(self, ap, w, h, aceso):
        a = self.ctx.arte
        _chave, e = self.m.instantanea()
        estilo = ap.get("estilo", "")
        if estilo == "player":
            pos, dur = self.m.posicao(e)
            return a.botao_player(w, h, e.get("capa"), e.get("titulo", ""),
                                  e.get("artista", ""), e.get("tocando", False),
                                  pos, dur, e.get("app", ""))
        if estilo == "controle":
            tocando = bool(e.get("titulo")) and e.get("tocando", False)
            return {"icon": "pause" if tocando else "play",
                    "label": "Pausar" if tocando else "Tocar"}
        if e.get("titulo"):
            return a.botao_musica(w, h, e.get("capa"), e["titulo"], e.get("artista", ""),
                                  e.get("tocando", True), e.get("app", ""))
        return {"icon": ap.get("icon", "play"), "label": ap.get("label", "Play")}

    @versao("musica")
    def ver(self, ap):
        # o player anda com o progresso (degraus de 10 s); os outros so mudam
        # com a faixa e com tocando/pausado
        if ap.get("estilo") == "player":
            return self.m.chave_fina or "vazio"
        return self.m.chave or "vazio"

    # -------------------------------------------------------------- estado

    def estado(self) -> dict:
        e = self.m.estado
        return {"sp_curtida": bool(e.get("sp_curtida")),
                "sp_aleatorio": bool(e.get("sp_aleatorio")),
                "sp_repetir": e.get("sp_repetir", "off") not in ("off", None)}

    # --------------------------------------------------------------- acoes

    @acao("spotify")
    def spotify(self, p):
        """Controles finos da Web API. Play/pause/proxima seguem pelas teclas
        de midia, que valem para qualquer app."""
        sp = self.m.spotify
        if sp is None:
            raise RuntimeError("Spotify nao configurado (client_id)")
        op = p.get("op", "")
        if op == "curtir":
            self.ctx.log(f"curtida: {sp.curtir_toggle()}")
        elif op == "aleatorio":
            self.ctx.log(f"aleatorio: {sp.aleatorio_toggle()}")
        elif op == "repetir":
            self.ctx.log(f"repetir: {sp.repetir_ciclo()}")
        elif op == "pular":
            sp.pular(float(p.get("segundos", 15)))
        elif op == "play_pause":
            sp.play_pause()
        else:
            raise ValueError(f"op do spotify desconhecida: {op!r}")

    @acao("musica_ou_app")
    def musica_ou_app(self, p):
        """Tocando: abre o player do painel. Parado: abre o app (instalado, o
        protocolo spotify:, ou o player web)."""
        if self.m.estado.get("titulo") and not p.get("so_app"):
            return p.get("page", "player")
        from telinha.apps import abrir_app, resolver_app
        alvo = p.get("target", "Spotify")
        if resolver_app(alvo):
            abrir_app(alvo)
        else:
            try:
                os.startfile(p.get("uri", "spotify:"))
            except OSError:
                os.startfile(p.get("web", "https://open.spotify.com"))
