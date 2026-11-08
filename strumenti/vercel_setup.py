"""Pubblica l'app su Vercel dal computer di chi amministra.

  py strumenti/vercel_setup.py crea        crea il progetto e carica le variabili segrete (una volta sola)
  py strumenti/vercel_setup.py pubblica    pubblica la versione attuale

Legge l'accesso Vercel da .vercel-token (mai nel repo). I valori segreti non vengono mai stampati.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOKEN = (REPO / ".vercel-token").read_text(encoding="utf-8").strip()
PROJECT = "job-radar"


def vercel(*args, stdin=None):
    cmd = "npx --yes vercel " + " ".join(args) + " --token " + TOKEN
    r = subprocess.run(cmd, shell=True, cwd=REPO, input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout + "\n" + r.stderr).replace(TOKEN, "<token>")
    return r.returncode, out


def env_value(name):
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "=") and line.split("=", 1)[1].strip():
            return line.split("=", 1)[1].strip()
    return None


def git_token():
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True,
                         env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}).stdout
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)["password"]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pubblica"
    if cmd == "crea":
        code, out = vercel("link", "--yes", "--project", PROJECT)
        print("progetto:", "collegato" if code == 0 else "ERRORE", "\n".join(out.strip().splitlines()[-3:]))
        cfg = json.dumps(json.loads((Path(os.environ.get("JR_LOCAL_CONFIG") or REPO.parent / "JobRadar" / "config.json")).read_text(encoding="utf-8")), ensure_ascii=False)
        values = {"JR_SESSION_SECRET": env_value("JR_SESSION_SECRET"), "JR_GH_TOKEN": env_value("JR_GH_TOKEN") or git_token(),
                  "JR_CONFIG": cfg}
        for name, value in values.items():
            vercel("env", "rm", name, "production", "--yes")
            code, out = vercel("env", "add", name, "production", stdin=value)
            print(f"variabile {name}:", "caricata" if code == 0 else "ERRORE " + out.strip().splitlines()[-1][:200])
    code, out = vercel("deploy", "--prod", "--yes")
    lines = [l for l in out.strip().splitlines() if l.strip()]
    print("pubblicazione:", "riuscita" if code == 0 else "ERRORE")
    print("\n".join(lines[-8:]))


if __name__ == "__main__":
    main()
