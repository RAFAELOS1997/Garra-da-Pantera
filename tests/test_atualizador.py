import ast
import hashlib
import http.server
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import atualizador as up


class _FakeGithubAPI:
    """A tiny local HTTP server standing in for api.github.com's
    /releases/latest endpoint plus the two asset download URLs, so these
    tests never touch the real network."""

    def __init__(self, assets):
        self.assets = assets
        self.server = http.server.HTTPServer(("127.0.0.1", 0), self._make_handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _make_handler(fake_self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/releases/latest":
                    body = json.dumps({
                        "tag_name": "v9.9.9",
                        "assets": [
                            {"name": name, "browser_download_url": f"{fake_self.base_url}/{name}"}
                            for name in fake_self.assets
                        ],
                    }).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path.lstrip("/") in fake_self.assets:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(fake_self.assets[self.path.lstrip("/")])
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *args):
                pass

        return Handler

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    @property
    def api_url(self):
        return f"{self.base_url}/releases/latest"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class AtualizadorTests(unittest.TestCase):
    def test_module_source_is_syntactically_valid(self):
        # Regression test for a real bug found in review: the update-apply
        # .bat script was built from string literals with raw, unescaped
        # newlines inside single-quoted strings, which is a SyntaxError —
        # meaning the entire auto-update feature silently never ran (its
        # only caller wraps the import in try/except Exception).
        ast.parse((APP / "atualizador.py").read_text(encoding="utf-8"))

    def test_versao_maior_compares_numerically(self):
        self.assertTrue(up._versao_maior("2.10.0", "2.9.0"))
        self.assertFalse(up._versao_maior("1.0.0", "2.0.0"))
        self.assertFalse(up._versao_maior("2.0.0", "2.0.0"))

    def test_versao_remota_returns_zip_and_checksum_urls(self):
        zip_bytes = b"conteudo fake do zip"
        checksum_bytes = f"{hashlib.sha256(zip_bytes).hexdigest()}  garra.zip\n".encode()
        api = _FakeGithubAPI({
            "garra-da-pantera-v9.9.9.zip": zip_bytes,
            "garra-da-pantera-v9.9.9.zip.sha256": checksum_bytes,
        })
        try:
            tag, zip_url, checksum_url = up._versao_remota(api_url=api.api_url)
            self.assertEqual(tag, "9.9.9")
            self.assertTrue(zip_url.endswith(".zip"))
            self.assertTrue(checksum_url.endswith(".zip.sha256"))
        finally:
            api.close()

    def test_versao_remota_raises_without_checksum_asset(self):
        api = _FakeGithubAPI({"garra-da-pantera-v9.9.9.zip": b"x"})
        try:
            with self.assertRaises(RuntimeError):
                up._versao_remota(api_url=api.api_url)
        finally:
            api.close()

    def test_baixar_e_verificar_accepts_matching_checksum(self):
        zip_bytes = b"conteudo fake do zip"
        checksum_bytes = f"{hashlib.sha256(zip_bytes).hexdigest()}  garra.zip\n".encode()
        api = _FakeGithubAPI({
            "garra-da-pantera-v9.9.9.zip": zip_bytes,
            "garra-da-pantera-v9.9.9.zip.sha256": checksum_bytes,
        })
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                zip_url = f"{api.base_url}/garra-da-pantera-v9.9.9.zip"
                checksum_url = f"{api.base_url}/garra-da-pantera-v9.9.9.zip.sha256"
                zip_path = up._baixar_e_verificar(zip_url, checksum_url, tmp_dir)
                self.assertTrue(zip_path.exists())
                self.assertEqual(zip_path.read_bytes(), zip_bytes)
        finally:
            api.close()

    def test_baixar_e_verificar_rejects_wrong_checksum_and_deletes_file(self):
        zip_bytes = b"conteudo fake do zip"
        wrong_checksum = f"{'0' * 64}  garra.zip\n".encode()
        api = _FakeGithubAPI({
            "garra-da-pantera-v9.9.9.zip": zip_bytes,
            "garra-da-pantera-v9.9.9.zip.sha256": wrong_checksum,
        })
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                zip_url = f"{api.base_url}/garra-da-pantera-v9.9.9.zip"
                checksum_url = f"{api.base_url}/garra-da-pantera-v9.9.9.zip.sha256"
                with self.assertRaises(RuntimeError):
                    up._baixar_e_verificar(zip_url, checksum_url, tmp_dir)
                self.assertFalse((tmp_dir / "update.zip").exists())
        finally:
            api.close()

    def test_verificar_atualizacao_never_raises_when_api_unreachable(self):
        original = up.API_URL
        up.API_URL = "http://127.0.0.1:1/unreachable"
        try:
            up.verificar_atualizacao(silencioso=True)  # must not raise
        finally:
            up.API_URL = original

    def test_aplicar_builds_a_syntactically_valid_bat_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            zip_path = tmp_dir / "update.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("garra_da_pantera.py", "# fake\n")
            with mock.patch.object(up.subprocess, "Popen") as popen, \
                 self.assertRaises(SystemExit):
                up._aplicar(zip_path, "9.9.9", tmp_dir)
            popen.assert_called_once()
            self.assertIn("cmd.exe", popen.call_args[0][0])
            bat_text = (tmp_dir / "aplicar_update.bat").read_text(encoding="utf-8")
            self.assertIn("xcopy", bat_text)
            self.assertNotIn('"\n"', bat_text)  # no leftover unterminated-string artifacts


if __name__ == "__main__":
    unittest.main()
