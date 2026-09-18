"""
atualizador.py -- Verifica e aplica atualizacoes automaticas do Garra da Pantera.

Uso: chamar verificar_atualizacao() no inicio de garra_da_pantera.py, antes da GUI.
"""

import os
import sys
import json
import zipfile
import tempfile
import subprocess
import urllib.request
from pathlib import Path

REPO = "RAFAELOS1997/Garra-da-Pantera"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
VERSAO_FILE = Path(__file__).parent / "VERSAO.txt"


def _versao_local() -> str:
    """Retorna a versao instalada localmente."""
    try:
        return VERSAO_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0.0.0"


def _versao_remota():
    """Retorna (tag, url_do_zip) da release mais recente no GitHub."""
    req = urllib.request.Request(
        API_URL, headers={"User-Agent": "GarraDaPantera-Updater"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    tag = data["tag_name"].lstrip("v")
    zip_url = None
    for asset in data.get("assets", []):
        if asset["name"].endswith(".zip"):
            zip_url = asset["browser_download_url"]
            break

    if not zip_url:
        raise RuntimeError("Nenhum arquivo ZIP encontrado na release.")

    return tag, zip_url


def _versao_maior(nova: str, atual: str) -> bool:
    """Retorna True se 'nova' e maior que 'atual'."""
    def partes(v):
        return tuple(int(x) for x in v.split("."))
    try:
        return partes(nova) > partes(atual)
    except ValueError:
        return False


def _baixar_e_aplicar(zip_url: str, nova_versao: str) -> None:
    """Baixa o ZIP e aplica a atualizacao via script .bat."""
    print(f"[Atualizador] Baixando versao {nova_versao}...")

    pasta_atual = Path(__file__).parent.resolve()
    tmp_dir = Path(tempfile.mkdtemp(prefix="garra_update_"))
    zip_path = tmp_dir / "update.zip"

    urllib.request.urlretrieve(zip_url, zip_path)
    print("[Atualizador] Download concluido. Extraindo...")

    pasta_extraida = tmp_dir / "extraido"
    pasta_extraida.mkdir()
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(pasta_extraida)

    # Se o ZIP contem subpasta unica, entra nela
    itens = list(pasta_extraida.iterdir())
    pasta_nova = itens[0] if (len(itens) == 1 and itens[0].is_dir()) else pasta_extraida

    exe_atual = sys.executable
    script_principal = pasta_atual / "garra_da_pantera.py"
    bat_path = tmp_dir / "aplicar_update.bat"

    bat_path.write_text(
        "@echo off
"
        f"echo Aplicando atualizacao {nova_versao}...
"
        "timeout /t 2 /nobreak >nul
"
        f'xcopy /E /Y /I "{pasta_nova}\*" "{pasta_atual}\"
'
        "echo Atualizacao concluida!
"
        f'start "" "{exe_atual}" "{script_principal}"
'
        'del "%~f0"
',
        encoding="utf-8",
    )

    print("[Atualizador] Reiniciando com a nova versao...")
    subprocess.Popen(["cmd.exe", "/c", str(bat_path)], creationflags=subprocess.CREATE_NEW_CONSOLE)
    sys.exit(0)


def verificar_atualizacao(silencioso: bool = False) -> None:
    """
    Verifica se ha nova versao no GitHub Releases.
    Se houver, baixa e aplica automaticamente (o programa e reiniciado).

    Parametros
    ----------
    silencioso : bool
        Se True, nao imprime nada quando ja esta atualizado.
    """
    try:
        atual = _versao_local()
        nova, zip_url = _versao_remota()

        if _versao_maior(nova, atual):
            print(f"[Atualizador] Nova versao: {nova}  (instalada: {atual})")
            _baixar_e_aplicar(zip_url, nova)
        else:
            if not silencioso:
                print(f"[Atualizador] Programa atualizado (v{atual}).")

    except Exception as exc:
        # Erro de rede ou API nao deve impedir o uso do programa
        print(f"[Atualizador] Nao foi possivel verificar atualizacoes: {exc}")


if __name__ == "__main__":
    verificar_atualizacao()
