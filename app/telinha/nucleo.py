"""
O nucleo: junta perfil, modulos, compositor, coletor e roteador, e mantem a
conexao com a placa (acha a porta, reconecta quando o cabo sai).

    python -m telinha rodar
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from . import caminhos, perfil as perfil_mod
from .compositor import Compositor
from .estado import Coletor
from .hospedeiro import Hospedeiro
from .ligacao import Desligar, Ligacao, TelaVirtual, achar_porta
from .roteador import Roteador


def _resolver_app():
    """Indice do Menu Iniciar, para detectar pacotes de app (lazy)."""
    from .apps import resolver_app
    return resolver_app


class Nucleo:
    def __init__(self):
        caminhos.prepara()
        self.hosp = Hospedeiro(self)
        self.hosp.descobrir()
        self.perfil_usuario = self._le_perfil()
        self.hosp.carregar(self.perfil_usuario)
        self.perfil = self._efetivo()
        self.hosp.ligar(self.perfil)
        self.comp = Compositor(self.hosp, self.perfil)
        self.coletor = Coletor(self)
        self.rot = Roteador(self)
        # sem placa, a "tela" e virtual: a janela do app funciona do mesmo jeito
        self.lig = TelaVirtual(self, self.inicio())
        self.api_token = ""
        self.desfazer_pilha: list = []
        self.refazer_pilha: list = []
        self.coletor.comeca()

    # -------------------------------------------------------------- perfil

    def _le_perfil(self) -> dict:
        p = perfil_mod.ler()
        if p is not None:
            return p
        agente = caminhos.PROGRAMA.parent / "agent"
        if (agente / "config.json").exists():
            print(f"[perfil] primeira abertura: importando {agente / 'config.json'}")
            p = perfil_mod.importa_agente(agente)
        else:
            p = {"esquema": 2, "inicio": "home", "ajustes": {}, "modulos": {},
                 "paginas": {"home": {"titulo": " ", "botoes": [{"pacote": "soundboard"}]}}}
        perfil_mod.salvar(p)
        return p

    def _efetivo(self) -> dict:
        try:
            resolver = _resolver_app()
        except Exception:
            resolver = None
        return perfil_mod.com_pacotes(self.perfil_usuario, resolver)

    def recarregar(self) -> None:
        """hello da placa: perfil relido do disco (editado a mao ou pelo editor).
        Perfil quebrado nao derruba nada: fica o anterior."""
        try:
            self.perfil_usuario = self._le_perfil()
        except Exception as e:
            print(f"[erro] perfil.json: {e} - mantendo o anterior")
            return
        self.hosp.carregar(self.perfil_usuario)
        self.perfil = self._efetivo()
        self.hosp.reconfigurar(self.perfil)
        self.comp.troca_perfil(self.perfil)

    def aplicar_perfil(self, perfil: dict, registrar: bool = True) -> None:
        """Perfil novo vindo da janela: grava (com historico) e a placa
        redesenha a pagina atual - so as artes que mudaram vao de novo.
        `registrar`: entra na pilha de desfazer (desfazer/refazer nao entram)."""
        import copy
        if registrar:
            self.desfazer_pilha.append(copy.deepcopy(self.perfil_usuario))
            del self.desfazer_pilha[:-50]
            self.refazer_pilha.clear()
        perfil_mod.salvar(perfil)
        self.perfil_usuario = perfil
        self.lig.recado({"_recarregar": True})

    def desfazer(self) -> bool:
        import copy
        if not self.desfazer_pilha:
            return False
        self.refazer_pilha.append(copy.deepcopy(self.perfil_usuario))
        self.aplicar_perfil(self.desfazer_pilha.pop(), registrar=False)
        return True

    def refazer(self) -> bool:
        import copy
        if not self.refazer_pilha:
            return False
        self.desfazer_pilha.append(copy.deepcopy(self.perfil_usuario))
        self.aplicar_perfil(self.refazer_pilha.pop(), registrar=False)
        return True

    def ajuste(self, chave: str, padrao=None):
        return (self.perfil.get("ajustes") or {}).get(chave, padrao)

    def inicio(self) -> str:
        return self.perfil.get("inicio", "home")

    # ----------------------------------------------------- para os modulos

    def aviso(self, mid: str, msg: str) -> None:
        print(f"[{mid}] {msg}")
        self.lig.recado({"ev": "err", "id": mid, "msg": msg[:35]})

    def atualizar_estado(self) -> None:
        self.coletor.agora()

    def modulo(self, mid: str):
        return self.hosp.modulo(mid)

    # ------------------------------------------------------- bandeja

    def grava_estado(self, **campos) -> None:
        try:
            caminhos.ESTADO.write_text(json.dumps({**campos, "quando": time.time()}),
                                       encoding="utf-8")
        except OSError:
            pass

    def le_comando(self) -> str:
        try:
            cmd = caminhos.COMANDO.read_text(encoding="utf-8").strip().lower()
            caminhos.COMANDO.unlink()
            return cmd
        except OSError:
            return ""

    # ---------------------------------------------------------- serial

    def rodar(self, ser_fabrica=None) -> int:
        """Loop de conexao. `ser_fabrica` (testes) devolve uma placa falsa."""
        import serial
        from . import api
        threading.Thread(target=self.comp.pre_desenhar, daemon=True, name="precarga").start()
        try:
            api.comeca(self)
        except Exception as e:
            print(f"[api] nao subiu: {e}")
        avisou = False
        while True:
            if ser_fabrica:
                ser = ser_fabrica()
            else:
                baud = int(self.ajuste("baud", 921600))
                porta = achar_porta(self.ajuste("porta", "auto"), baud)
                if not porta:
                    self.grava_estado(conectado=False, porta="", pagina="")
                    if not avisou:
                        print("[...] nenhuma porta responde como a placa, tentando de novo")
                        avisou = True
                    time.sleep(2)
                    continue
                try:
                    ser = serial.Serial(porta, baud, timeout=0.005)
                except serial.SerialException as e:
                    print(f"[erro] {porta}: {e}")
                    time.sleep(2)
                    continue
            print(f"[ok] conectado em {ser.port}")
            avisou = False
            try:
                self.lig = Ligacao(ser, self)
                # a placa so manda hello quando NAO tem pagina: se o nucleo
                # reinicia com ela desenhada, quem pergunta e o PC
                self.lig.envia({"ev": "quem"})
                self.lig.roda()
            except Desligar:
                self.grava_estado(conectado=False, porta="", pagina="", dormindo=True)
                print("[sono] encerrado a pedido da bandeja")
                self.hosp.parar()
                return 0
            except (serial.SerialException, OSError) as e:
                self.grava_estado(conectado=False, porta="", pagina="")
                print(f"[desconectado] {e}")
            except KeyboardInterrupt:
                print("\n[saindo]")
                self.hosp.parar()
                return 0
            finally:
                try:
                    ser.close()
                except Exception:
                    pass
                self.lig = TelaVirtual(self, self.lig.pagina_atual)
            if ser_fabrica:
                return 0
            time.sleep(1)
