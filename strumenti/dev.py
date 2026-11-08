"""Prova l'app sul computer prima di pubblicarla: serve public/ e la funzione api/index.py su http://localhost:8790

  py strumenti/dev.py

Usa gli stessi dati veri (ramo dati su GitHub) con l'accesso che Git ha già salvato, i segreti di .env e le chiavi AI
del config.json del programma per computer, se c'è. Niente di questo viene scritto nel repo.
"""
import importlib.util
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORT = 8790

for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        if v.strip():
            os.environ.setdefault(k.strip(), v.strip())
if "JR_GH_TOKEN" not in os.environ:
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True,
                         env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}).stdout
    os.environ["JR_GH_TOKEN"] = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)["password"]
local_cfg = Path(os.environ.get("JR_LOCAL_CONFIG") or REPO.parent / "JobRadar" / "config.json")
if "JR_CONFIG" not in os.environ and local_cfg.exists():
    os.environ["JR_CONFIG"] = local_cfg.read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location("api_index", REPO / "api" / "index.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(REPO / "public"), **k)

    def _api(self):
        api.handler._run(self)

    def do_GET(self):
        return self._api() if self.path.startswith("/api/") else super().do_GET()

    def do_POST(self):
        return self._api()

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    print(f"Job Radar in prova su http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
