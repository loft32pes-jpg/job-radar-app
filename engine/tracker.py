"""Preferiti, stato delle candidature, note e annunci scartati.

Vive in data/preferiti.json e non scade mai: un preferito conserva una copia completa dell'annuncio (e del suo testo),
così resta visibile anche quando l'archivio dei giorni viene ripulito.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from common import ARCHIVE, DATA, normalize_url, read_json, write_json  # noqa: E402

FILE = DATA / "preferiti.json"
TEXTS = DATA / "texts"
STATUSES = ("", "da_candidare", "candidata", "colloquio", "offerta", "chiusa")


def load() -> dict:
    t = read_json(FILE, None) or {}
    t.setdefault("fav", {})
    t.setdefault("hidden", {})
    return t


def public() -> dict:
    """Quello che serve alla pagina: i preferiti senza il testo completo dell'annuncio."""
    t = load()
    return {"fav": {k: {x: y for x, y in v.items() if x != "text"} for k, v in t["fav"].items()}, "hidden": t["hidden"]}


def find_job(url: str):
    """(annuncio, testo) cercando prima negli archivi dei giorni, poi tra i preferiti."""
    key = normalize_url(url)
    for f in sorted(ARCHIVE.glob("????-??-??.json"), reverse=True):
        for j in (read_json(f, {}) or {}).get("jobs", []):
            if normalize_url(j.get("url", "")) == key:
                return j, read_json(TEXTS / f"{f.stem}.json", {}).get(key, "")
    fav = load()["fav"].get(key)
    return (fav["job"], fav.get("text", "")) if fav else (None, "")


def _now():
    return datetime.now().astimezone().isoformat(timespec="minutes")


def set_fav(url: str, on: bool):
    t, key = load(), normalize_url(url)
    if not on:
        t["fav"].pop(key, None)
    elif key not in t["fav"]:
        job, text = find_job(url)
        if not job:
            return None
        t["fav"][key] = {"job": job, "text": text, "saved_at": _now(), "status": "", "note": ""}
        t["hidden"].pop(key, None)
    write_json(FILE, t)
    return {k: v for k, v in t["fav"].get(key, {}).items() if k not in ("text", "job")}


def set_track(url: str, status=None, note=None):
    """Stato e nota di una candidatura: impostarli salva l'annuncio tra i preferiti."""
    if set_fav(url, True) is None:
        return None
    t, key = load(), normalize_url(url)
    f = t["fav"][key]
    if status is not None and status in STATUSES and status != f.get("status"):
        f["status"], f["status_at"] = status, _now()
        if status == "candidata":
            f["applied_at"] = _now()
    if note is not None:
        f["note"] = str(note)[:2000]
    write_json(FILE, t)
    return {k: v for k, v in f.items() if k not in ("text", "job")}


def set_hidden(url: str, on: bool):
    t, key = load(), normalize_url(url)
    if on:
        t["hidden"][key] = _now()
        t["fav"].pop(key, None)
    else:
        t["hidden"].pop(key, None)
    write_json(FILE, t)
    return True


def refresh_snapshots(update):
    """Applica update(job, testo) alla copia di ogni preferito (per esempio per ricalcolare il match con il CV)."""
    t = load()
    for f in t["fav"].values():
        update(f["job"], f.get("text", ""))
    if t["fav"]:
        write_json(FILE, t)
