"""
Monta a pasta distribuivel da prova SEM .exe proprio: o Python embutivel
oficial (python.exe/pythonw.exe assinados pela Python Software Foundation) +
as bibliotecas em lib/ + o nosso codigo + um lancador.

Por que assim, e nao PyInstaller: o Smart App Control do Windows 11 (ligado
nesta maquina, modo "impor") recusa qualquer .exe sem assinatura digital - o
TELINHA-prova.exe do PyInstaller nem abre ("Uma politica de Controle de
Aplicativo bloqueou este arquivo"). O python.exe oficial e assinado, e as
bibliotecas do PyPI tem reputacao; com eles, tudo roda. Ver RESULTADO.md.

    python montar_pasta.py [destino]      (padrao: ./pasta/TELINHA)

Depois:  <destino>\\python\\python.exe -I <destino>\\iniciar.py --auto
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PY_VERSAO = "3.12.4"          # tem de casar com as .pyd das bibliotecas
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
AGENTE = RAIZ / "agent"

# Rodas binarias (casam com cp312/win_amd64) e puras (proxy_tools so tem sdist)
BINARIAS = [
    "pyserial==3.5", "pycaw", "comtypes", "pywin32", "Pillow", "winsdk",
    "sounddevice", "soundfile", "numpy", "obsws-python",
    "fastapi==0.115.0", "uvicorn==0.30.6", "websockets==16.0",
]
PURAS = ["pywebview==6.2.1", "proxy_tools", "bottle", "pythonnet", "clr_loader"]

LANCADOR = '''\
# Lancador: o python.exe oficial (assinado) roda o nosso codigo. site.addsitedir
# processa os .pth da pasta lib (o pywin32 precisa deles para achar as DLLs).
import runpy, site, sys
from pathlib import Path
raiz = Path(__file__).resolve().parent
site.addsitedir(str(raiz / "lib"))
alvo = raiz / "app" / "provas" / "etapa0" / "prova.py"
sys.argv = [str(alvo)] + sys.argv[1:]
runpy.run_path(str(alvo), run_name="__main__")
'''


def pip(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *args], check=True)


def main() -> int:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI / "pasta" / "TELINHA"
    if destino.exists():
        print(f"{destino} ja existe; apague antes")
        return 1
    (destino / "python").mkdir(parents=True)

    url = f"https://www.python.org/ftp/python/{PY_VERSAO}/python-{PY_VERSAO}-embed-amd64.zip"
    print("baixando", url)
    zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url).read())).extractall(destino / "python")

    lib = destino / "lib"
    print("bibliotecas binarias")
    pip("--target", str(lib), "--python-version", "3.12", "--only-binary=:all:",
        "--platform", "win_amd64", *BINARIAS)
    print("bibliotecas puras")
    pip("--target", str(lib), "--upgrade", "--no-deps", *PURAS)

    print("codigo")
    prova = destino / "app" / "provas" / "etapa0"
    prova.mkdir(parents=True)
    shutil.copy2(AQUI / "prova.py", prova)
    shutil.copytree(AQUI / "web" / "dist", prova / "web" / "dist")
    (destino / "agent").mkdir()
    for nome in ("arte.py", "icones.py"):
        shutil.copy2(AGENTE / nome, destino / "agent")
    shutil.copytree(AGENTE / "fontes", destino / "agent" / "fontes")
    sons = destino / "agent" / "pacotes" / "soundboard" / "sons"
    sons.mkdir(parents=True)
    shutil.copy2(AGENTE / "pacotes" / "soundboard" / "sons" / "Ding.wav", sons)
    (destino / "iniciar.py").write_text(LANCADOR, encoding="utf-8")

    total = sum(f.stat().st_size for f in destino.rglob("*") if f.is_file())
    print(f"pronto: {destino} ({total / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
