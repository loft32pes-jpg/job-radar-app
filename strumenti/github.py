"""Operazioni su GitHub dal computer di chi amministra, con l'accesso che Git ha già salvato (nessuna chiave in chiaro).

  py strumenti/github.py segreto NOME file.json     carica un segreto cifrato nel repo pubblico della ricerca
  py strumenti/github.py lancia [id utente]          avvia la ricerca sui server di GitHub
  py strumenti/github.py stato                       ultime esecuzioni
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "loft32pes-jpg/job-radar-app"   # repo pubblico del codice, dove gira la ricerca (i dati stanno in loft32pes-jpg/job-radar)
API = f"https://api.github.com/repos/{REPO}"


def token():
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True,
                         timeout=30, env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}).stdout
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)["password"]


def call(method, url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Authorization": "Bearer " + token(), "Accept": "application/vnd.github+json",
                                          "User-Agent": "job-radar-admin"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    cmd = sys.argv[1]
    if cmd == "segreto":
        from nacl import encoding, public
        name, value = sys.argv[2], open(sys.argv[3], encoding="utf-8").read()
        _, key = call("GET", f"{API}/actions/secrets/public-key")
        box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
        enc = base64.b64encode(box.encrypt(value.encode("utf-8"))).decode()
        status, _ = call("PUT", f"{API}/actions/secrets/{name}", {"encrypted_value": enc, "key_id": key["key_id"]})
        print(f"segreto {name}: {'caricato' if status in (201, 204) else 'ERRORE ' + str(status)}")
    elif cmd == "lancia":
        uid = sys.argv[2] if len(sys.argv) > 2 else ""
        status, r = call("POST", f"{API}/actions/workflows/ricerca.yml/dispatches", {"ref": "main", "inputs": {"utente": uid}})
        print("ricerca avviata" if status == 204 else f"ERRORE {status} {r.get('message')}")
    elif cmd == "stato":
        _, r = call("GET", f"{API}/actions/runs?per_page=6")
        for w in r.get("workflow_runs", []):
            print(w["name"], "|", w["event"], "|", w["status"], w.get("conclusion") or "", "|", w["created_at"], "|", w["html_url"])


if __name__ == "__main__":
    main()
