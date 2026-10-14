# PyInstaller, modo pasta (onedir): o onefile descompacta tudo a cada abertura,
# fica lento e assusta antivirus. Gerar:  pyinstaller prova.spec --noconfirm
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

AQUI = Path(SPECPATH)
AGENTE = AQUI.parents[2] / "agent"

a = Analysis(
    [str(AQUI / "prova.py")],
    pathex=[str(AGENTE)],
    datas=[
        (str(AQUI / "web" / "dist"), "web/dist"),
        # arte.py acha a Phosphor em Path(__file__).parent / "fontes"
        (str(AGENTE / "fontes"), "fontes"),
        (str(AGENTE / "pacotes" / "soundboard" / "sons" / "Ding.wav"),
         "agent/pacotes/soundboard/sons"),
    ],
    hiddenimports=[
        "arte", "icones",
        "winsdk.windows.media.control", "winsdk.windows.storage.streams",
        *collect_submodules("uvicorn"),
    ],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TELINHA-prova",
          console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="TELINHA-prova", upx=False)
