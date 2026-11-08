"""Gestione degli utenti di Job Radar (si usa dal computer di chi amministra, non va online).

  py strumenti/admin.py aggiungi "Nome"     crea una persona e stampa il suo codice di accesso
  py strumenti/admin.py elenco              mostra le persone e i loro codici

I codici restano nel file .codici.json (mai nel repo). Nel ramo dati finisce solo l'impronta del codice.
Serve la cartella dati/ con il ramo "dati" del repo e il file .env con JR_SESSION_SECRET.
"""
import hashlib
import hmac
import json
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "dati" / "utenti" / "index.json"
CODES = REPO / ".codici.json"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # senza lettere e cifre che si confondono


def env(name):
    for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"Manca {name} nel file .env")


def code_hash(code: str) -> str:
    """Stessa impronta calcolata dall'app (api/_lib.py)."""
    clean = "".join(c for c in code.upper() if c.isalnum())
    return hmac.new(env("JR_SESSION_SECRET").encode(), clean.encode(), hashlib.sha256).hexdigest()


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "elenco"
    index, codes = load(INDEX, {}), load(CODES, {})
    if cmd == "aggiungi":
        name = sys.argv[2]
        code = "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(3))
        h = code_hash(code)
        uid = h[:12]
        index[uid] = {"name": name, "hash": h, "admin": len(index) == 0 and "--admin" in sys.argv}
        if "--admin" in sys.argv:
            index[uid]["admin"] = True
        codes[uid] = {"name": name, "code": code}
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        (INDEX.parent / uid).mkdir(exist_ok=True)
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        CODES.write_text(json.dumps(codes, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{name}: id {uid}, codice {code}")
    else:
        for uid, u in index.items():
            print(f"{u['name']}: id {uid}, codice {codes.get(uid, {}).get('code', '(non su questo computer)')}")


if __name__ == "__main__":
    main()
