"""
atualizador.py -- Verifica e aplica atualizacoes automaticas do Garra da Pantera.

Uso: chamar verificar_atualizacao() no inicio de garra_da_pantera.py, antes da GUI.
"""

import hashlib
import os
import re
import sys
import json
import zipfile
import tempfile
import subprocess
import urllib.request
from pathlib import Path

REPO = "RAFAELOS1997/Garra-da-Pantera"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def _pasta_app() -> Path:
    """Pasta raiz da instalacao (onde ficam VERSAO.txt e os arquivos do programa).

    Quando congelado pelo PyInstaller, `__file__` deste modulo nao aponta
    para um caminho real em disco -- o modulo vive empacotado dentro do
    proprio executavel -- entao a pasta correta e a que contem o executavel
    (`sys.executable`), nao `Path(__file__).parent`.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()


VERSAO_FILE = _pasta_app() / "VERSAO.txt"


def _versao_local() -> str:
    """Retorna a versao instalada localmente."""
    try:
        return VERSAO_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0.0.0"


def _versao_remota(api_url: str = API_URL):
    """Retorna (tag, url_do_zip, url_do_checksum) da release mais recente no GitHub.

    Uma release publica tres ZIPs: codigo-fonte (`*.zip`), build congelada
    (`*-exe.zip`) e o instalador (`*-Installer.exe`, ignorado aqui pois nao
    e um ZIP). Uma instalacao congelada (`sys.frozen`) so aceita o asset
    `-exe.zip`; uma instalacao por codigo-fonte so aceita o `.zip` comum --
    nunca aplica o pacote do outro modo.
    """
    req = urllib.request.Request(
        api_url, headers={"User-Agent": "GarraDaPantera-Updater"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    tag = data["tag_name"].lstrip("v")
    assets = {asset["name"]: asset["browser_download_url"] for asset in data.get("assets", [])}

    frozen = getattr(sys, "frozen", False)
    if frozen:
        candidatos = [nome for nome in assets if nome.endswith("-exe.zip")]
        descricao = "congelada (.exe)"
    else:
        candidatos = [nome for nome in assets if nome.endswith(".zip") and not nome.endswith("-exe.zip")]
        descricao = "de codigo-fonte"
    if not candidatos:
        raise RuntimeError(f"Nenhuma release {descricao} encontrada (nenhum asset .zip compativel).")

    zip_nome = candidatos[0]
    checksum_nome = zip_nome + ".sha256"
    if checksum_nome not in assets:
        raise RuntimeError(
            f"Nenhum arquivo {checksum_nome} encontrado na release; a atualizacao nao pode ser "
            "verificada e foi cancelada por seguranca."
        )

    return tag, assets[zip_nome], assets[checksum_nome]


def _baixar_checksum_esperado(checksum_url: str) -> str:
    """Baixa e interpreta o arquivo <nome>.zip.sha256 (formato `sha256sum`: hash + nome do arquivo)."""
    req = urllib.request.Request(checksum_url, headers={"User-Agent": "GarraDaPantera-Updater"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        texto = resp.read().decode("utf-8", errors="ignore").strip()
    match = re.match(r"^([0-9a-fA-F]{64})", texto)
    if not match:
        raise RuntimeError("Arquivo de checksum invalido ou corrompido.")
    return match.group(1).lower()


def _sha256_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest().lower()


def _versao_maior(nova: str, atual: str) -> bool:
    """Retorna True se 'nova' e maior que 'atual'."""
    def partes(v):
        return tuple(int(x) for x in v.split("."))
    try:
        return partes(nova) > partes(atual)
    except ValueError:
        return False


def _baixar_e_verificar(zip_url: str, checksum_url: str, tmp_dir: Path) -> Path:
    """Baixa o ZIP para uma pasta temporaria e so o devolve se o SHA-256 bater
    exatamente com o publicado junto da release. Qualquer divergencia apaga o
    download e levanta, para que o chamador nunca aplique um pacote nao
    verificado (por exemplo, uma release corrompida ou uma resposta
    adulterada por um MITM que nao tenha comprometido tambem o asset de
    checksum)."""
    zip_path = tmp_dir / "update.zip"
    urllib.request.urlretrieve(zip_url, zip_path)
    print("[Atualizador] Download concluido. Verificando integridade...")

    esperado = _baixar_checksum_esperado(checksum_url)
    obtido = _sha256_arquivo(zip_path)
    if obtido != esperado:
        zip_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"SHA-256 nao confere (esperado {esperado[:12]}..., obtido {obtido[:12]}...); "
            "atualizacao descartada por seguranca."
        )
    return zip_path


def _aplicar(zip_path: Path, nova_versao: str, tmp_dir: Path) -> None:
    """Extrai o ZIP ja verificado e aplica a atualizacao via script .bat.

    Numa instalacao congelada, o `.bat` precisa esperar o processo atual
    (que mantem `GarraDaPantera.exe` aberto/travado pelo Windows) terminar
    de fato antes de conseguir sobrescreve-lo -- por isso espera o PID
    desaparecer do `tasklist` em vez de um `timeout` fixo, que podia falhar
    se o encerramento demorasse mais que o tempo fixo (comum com CUDA/torch
    ainda descarregando)."""
    pasta_atual = _pasta_app()
    frozen = getattr(sys, "frozen", False)

    pasta_extraida = tmp_dir / "extraido"
    pasta_extraida.mkdir()
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(pasta_extraida)

    # Se o ZIP contem subpasta unica, entra nela
    itens = list(pasta_extraida.iterdir())
    pasta_nova = itens[0] if (len(itens) == 1 and itens[0].is_dir()) else pasta_extraida

    if frozen:
        comando_relancar = f'start "" "{pasta_atual / "GarraDaPantera.exe"}"'
    else:
        comando_relancar = f'start "" "{sys.executable}" "{pasta_atual / "garra_da_pantera.py"}"'

    pid = os.getpid()
    bat_path = tmp_dir / "aplicar_update.bat"
    linhas = [
        "@echo off",
        f"echo Aplicando atualizacao {nova_versao}...",
        ":espera",
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul',
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >nul",
        "  goto espera",
        ")",
        f'xcopy /E /Y /I "{pasta_nova}\\*" "{pasta_atual}\\"',
        "echo Atualizacao concluida!",
        comando_relancar,
        'del "%~f0"',
    ]
    bat_path.write_text("\r\n".join(linhas) + "\r\n", encoding="utf-8")

    print("[Atualizador] Reiniciando com a nova versao...")
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(["cmd.exe", "/c", str(bat_path)], creationflags=creationflags)
    sys.exit(0)


def verificar_atualizacao(silencioso: bool = False) -> None:
    """
    Verifica se ha nova versao no GitHub Releases.
    Se houver, baixa, verifica o SHA-256 publicado junto da release e so
    entao aplica (o programa e reiniciado). Uma release sem checksum, um
    checksum que nao bate, ou qualquer falha de rede/API nunca aplicam nada
    e nunca impedem o uso do programa.

    Parametros
    ----------
    silencioso : bool
        Se True, nao imprime nada quando ja esta atualizado.
    """
    try:
        atual = _versao_local()
        nova, zip_url, checksum_url = _versao_remota()

        if not _versao_maior(nova, atual):
            if not silencioso:
                print(f"[Atualizador] Programa atualizado (v{atual}).")
            return

        print(f"[Atualizador] Nova versao: {nova}  (instalada: {atual})")
        print(f"[Atualizador] Baixando versao {nova}...")
        tmp_dir = Path(tempfile.mkdtemp(prefix="garra_update_"))
        zip_path = _baixar_e_verificar(zip_url, checksum_url, tmp_dir)
        _aplicar(zip_path, nova, tmp_dir)

    except Exception as exc:
        # Erro de rede, API ou checksum nao deve impedir o uso do programa
        print(f"[Atualizador] Nao foi possivel verificar atualizacoes: {exc}")


if __name__ == "__main__":
    verificar_atualizacao()
