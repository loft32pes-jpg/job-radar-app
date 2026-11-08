"""Dove vive il CV sul computer e come si applica agli annunci.

Il CV resta in locale nella cartella profilo/ (testo estratto + profilo). Non viene mai inviato a nessuno,
tranne quando si chiede l'analisi approfondita con Claude per un singolo annuncio.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import cvmatch  # noqa: E402
import tracker  # noqa: E402
from common import ARCHIVE, DATA, ROOT, normalize_url, read_json, write_json  # noqa: E402

PROFILE_DIR = ROOT / "profilo"
CV_TXT = PROFILE_DIR / "cv.txt"
CV_PROFILE = PROFILE_DIR / "cv_profile.json"
TEXTS = DATA / "texts"
TEXT_MAX = 9000


def load():
    """(testo, profilo) del CV salvato, oppure (None, None)."""
    if not CV_TXT.exists():
        return None, None
    text = CV_TXT.read_text(encoding="utf-8")
    profile = read_json(CV_PROFILE, None) or cvmatch.analyze_cv(text)
    return text, profile


def save_text(text: str, filename: str = "") -> dict:
    PROFILE_DIR.mkdir(exist_ok=True)
    text = text.replace("\x00", "").strip()
    CV_TXT.write_text(text, encoding="utf-8")
    profile = cvmatch.analyze_cv(text)
    profile["filename"] = filename
    profile["readiness"] = cvmatch.ats_readiness(profile)
    write_json(CV_PROFILE, profile)
    return profile


def save_file(path: str, filename: str = "") -> dict:
    return save_text(cvmatch.extract_text(path), filename or os.path.basename(path))


def remove():
    for f in (CV_TXT, CV_PROFILE):
        if f.exists():
            f.unlink()
    for f in ARCHIVE.glob("????-??-??.json"):
        data = read_json(f, None)
        if data:
            for j in data.get("jobs", []):
                j.pop("cv", None)
            write_json(f, data)


def save_texts(day: str, texts: dict):
    """Testi degli annunci del giorno (servono al confronto col CV e all'analisi con Claude)."""
    old = read_json(TEXTS / f"{day}.json", {})
    old.update({k: v[:TEXT_MAX] for k, v in texts.items() if v})
    write_json(TEXTS / f"{day}.json", old)


def job_text(day: str, url: str) -> str:
    return read_json(TEXTS / f"{day}.json", {}).get(normalize_url(url), "")


def apply_to_archives() -> int:
    """Ricalcola il punteggio CV per tutti gli annunci in archivio. Ritorna quanti annunci ha valutato."""
    text, profile = load()
    if not text:
        return 0
    import rules
    import searchprofile
    rules.configure(searchprofile.load())
    n = 0
    for f in ARCHIVE.glob("????-??-??.json"):
        data = read_json(f, None)
        if not data:
            continue
        texts = read_json(TEXTS / f"{f.stem}.json", {})
        for j in data.get("jobs", []):
            j["cv"] = cvmatch.match(profile, text, j, texts.get(normalize_url(j["url"]), ""))
            n += 1
        write_json(f, data)
    # i preferiti hanno la loro copia dell'annuncio: va aggiornata anche quella
    tracker.refresh_snapshots(lambda job, jt: job.__setitem__("cv", cvmatch.match(profile, text, job, jt)))
    # i testi oltre i 30 giorni seguono la sorte degli archivi
    keep = {f.stem for f in ARCHIVE.glob("????-??-??.json")}
    for f in TEXTS.glob("????-??-??.json"):
        if f.stem not in keep:
            f.unlink()
    return n
