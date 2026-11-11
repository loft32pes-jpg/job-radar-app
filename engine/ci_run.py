"""Ricerca completa per una persona, sui server di GitHub.

Uso: python engine/ci_run.py <id utente>
Si aspetta il ramo "dati" scaricato nella cartella dati/ e la configurazione (chiavi comprese) nella variabile JR_CONFIG.
Prepara una cartella di lavoro con la stessa forma del programma per computer (scripts/, data/, profilo/), lancia la
ricerca e riporta nel ramo dati: risultati.json (quello che l'app mostra), l'archivio degli ultimi giorni e lo stato.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("JR_WORK") or (REPO / ".lavoro"))
KEEP_DAYS = 8  # una settimana: serve alla ricerca vicino casa e a non rileggere gli annunci già bocciati
JOB_FIELDS = ("title", "title_it", "company", "city", "country", "url", "source", "posted_at", "score", "rationale", "reasons",
              "languages", "mode", "salary", "role_family", "logo", "lat", "lon", "geo", "first_seen", "last_seen", "ai_fit",
              "ai_why", "preferred", "local_ad", "near", "excerpt", "skills", "years", "level", "education", "contract", "unread")


def normalize(url):
    sys.path.insert(0, str(REPO / "engine"))
    from common import normalize_url
    return normalize_url(url)


def read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def notify(prof, new):
    """Avviso sul telefono (ntfy) con i migliori annunci nuovi. Nel registro pubblico non va né il canale né i titoli."""
    n = prof.get("notify") or {}
    if not n.get("topic"):
        return
    places = [p["name"] for p in (prof.get("answers") or {}).get("places") or []]
    good = [j for j in new if j.get("score", 0) >= int(n.get("min") or 70)]
    if not good:
        return
    good.sort(key=lambda j: (places.index(j["near"]) if j.get("near") in places else len(places), -j["score"]))
    lines = [f"{j['score']} · {j.get('title_it') or j['title']} · {j['company']}" + (f" · {j['city']}" if j.get("city") else "") for j in good[:6]]
    if len(good) > 6:
        lines.append(f"e altri {len(good) - 6}")
    title = f"Job Radar: {len(good)} " + ("annuncio nuovo" if len(good) == 1 else "annunci nuovi")
    from urllib.request import Request, urlopen
    try:
        req = Request("https://ntfy.sh/" + n["topic"], data="\n".join(lines).encode("utf-8"), method="POST",
                      headers={"Title": title, "Click": os.environ.get("JR_APP_URL", "https://job-radar-ivory-phi.vercel.app"),
                               "Tags": "briefcase", "Content-Type": "text/plain; charset=utf-8"})
        urlopen(req, timeout=15).close()
        print("Avviso sul telefono inviato")
    except Exception:
        print("Avviso sul telefono non inviato")


def main():
    uid = sys.argv[1]
    user = REPO / "dati" / "utenti" / uid
    profile = user / "profilo.json"
    if not profile.exists():
        print(f"Utente {uid}: nessun profilo, niente da cercare")
        return 0
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(REPO / "engine", WORK / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    (WORK / "data" / "archive").mkdir(parents=True)
    (WORK / "profilo").mkdir()
    write(WORK / "data" / "testi_letti.json", read(user / "testi.json", {}))  # testi già letti: LinkedIn non li rilegge
    for f in (REPO / "engine_data").glob("*.json"):
        shutil.copy(f, WORK / "data" / f.name)
    # se il profilo è cambiato dall'ultima ricerca, gli annunci in archivio erano stati scelti con quello vecchio: si riparte
    version = str(read(profile, {}).get("version", ""))
    mark = user / "archivio" / "versione.txt"
    same = mark.exists() and mark.read_text(encoding="utf-8").strip() == version
    for f in (user / "archivio").glob("????-??-??.json"):
        if same:
            shutil.copy(f, WORK / "data" / "archive" / f.name)
    # la ricerca impara dalle scelte nella bacheca (annunci salvati, candidature, scartati)
    sys.path.insert(0, str(REPO / "engine"))
    import learn
    # (in un file suo: il profilo lo scrive solo l'app, così il salvataggio dei risultati non entra mai in conflitto)
    prof_now = read(profile, {})
    prof_now["learned"] = read(user / "imparato.json", {})
    learned = learn.learn(prof_now, read(user / "preferiti.json", {}), log=lambda m: None)
    if learned != prof_now["learned"]:
        write(user / "imparato.json", learned)
    prof_now["learned"] = learned
    # ruoli mai cercati finora nella città principale: la prima volta si guarda l'ultimo mese (pochi per ricerca, per il tempo)
    import searchprofile
    applied = learn.apply(prof_now)
    deep_done = dict(learned.get("deep") or {})
    deep_new = [t for t in searchprofile.search_plan(applied)["local"] if t.lower() not in deep_done][:6]
    applied["deep_terms"] = deep_new
    write(WORK / "profilo" / "ricerca.json", applied)
    # i modelli AI scelti stamattina da modelli.py (i più nuovi che rispondono davvero) al posto di quelli scritti a mano
    cfg = json.loads(os.environ["JR_CONFIG"])
    chosen = read(REPO / "dati" / "modelli.json", {}).get("fornitori", {})
    for p in [cfg.get("ai", {})] + list(cfg.get("ai", {}).get("extra") or []):
        picked = (chosen.get(p.get("name") or "") or {}).get("giudice")
        if picked:
            p["judge_models"] = picked
            if p is cfg.get("ai"):
                p["model"] = picked[0]
    if os.environ.get("JR_LI_MINUTES"):  # con poche persone attive la ricerca può durare di più e leggere tutto
        cfg.setdefault("linkedin", {})["max_minutes"] = float(os.environ["JR_LI_MINUTES"])
    if os.environ.get("JR_LI_SHARE"):  # quota del tempo per sfogliare le ricerche (il resto è per leggere gli annunci)
        cfg.setdefault("linkedin", {})["search_share"] = float(os.environ["JR_LI_SHARE"])
    (WORK / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    t0 = time.time()
    # il motore legge la configurazione da JR_CONFIG (non dal file): deve ricevere quella con le modifiche qui sopra
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", JR_CONFIG=json.dumps(cfg, ensure_ascii=False))
    # l'uscita del motore (titoli, ruoli cercati) non va nel registro dell'esecuzione, che nel repo pubblico è visibile a tutti
    code = subprocess.run([sys.executable, str(WORK / "scripts" / "run_local.py"), "--no-open"], cwd=WORK, env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True).returncode
    log = (WORK / "data" / "ultimo_log.txt").read_text(encoding="utf-8") if (WORK / "data" / "ultimo_log.txt").exists() else ""
    run = read(WORK / "data" / "ultima_ricerca.json", None)
    if code != 0 or not run:
        write(user / "stato.json", {"running": False, "ok": False, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                    "error": "La ricerca non è arrivata in fondo. Riprova tra qualche minuto."})
        print("Ricerca non riuscita: " + " | ".join(l for l in log.splitlines()[-40:] if "Traceback" in l or "Error" in l)[-600:])
        return 1

    # annunci dentro la finestra dell'ultima ricerca = quelli visti in questa ricerca
    jobs, today = [], date.today()
    arch = user / "archivio"
    arch.mkdir(exist_ok=True)
    for old in arch.glob("*.json"):
        old.unlink()
    mark.write_text(version, encoding="utf-8")
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    def still_new(j):
        """Trovato da poco con una ricerca sull'ultimo mese: le ricerche settimanali non lo rivedono, resta in elenco 7 giorni."""
        try:
            return bool(j.get("old_find")) and datetime.fromisoformat(j["first_seen"]) > week_ago
        except (KeyError, ValueError, TypeError):
            return False
    for f in sorted((WORK / "data" / "archive").glob("????-??-??.json"), reverse=True):
        if (today - date.fromisoformat(f.stem)).days > KEEP_DAYS:
            continue
        shutil.copy(f, arch / f.name)
        for j in read(f, {}).get("jobs", []):
            if j.get("last_seen") == run["at"] or still_new(j):
                jobs.append({k: j[k] for k in JOB_FIELDS if j.get(k) not in (None, "", [], {})})
    if deep_new:  # la ricerca è arrivata in fondo: questi ruoli hanno avuto la loro ricerca sull'ultimo mese
        deep_done.update({t.lower(): today.isoformat() for t in deep_new})
        learned = dict(learned, deep=deep_done)
        write(user / "imparato.json", learned)
    # annunci uguali a quelli che ha già scartato (stesso titolo e azienda, anche ripubblicati con un altro link): fuori
    gone = {(str((f.get("job") or {}).get("title", "")).lower(), str((f.get("job") or {}).get("company", "")).lower())
            for f in (read(user / "preferiti.json", {}).get("favs") or {}).values() if f.get("state") == "discarded"}
    jobs = [j for j in jobs if (j["title"].lower(), j["company"].lower()) not in gone]
    jobs.sort(key=lambda j: -j["score"])

    # testo completo degli annunci in elenco: serve a chi salva un annuncio (lo rilegge anche quando è sparito dal sito)
    texts = read(user / "testi.json", {})
    for f in sorted((WORK / "data" / "texts").glob("????-??-??.json")):
        texts.update(read(f, {}))
    # stesso annuncio pubblicato con più marchi dello stesso gruppo (es. MioDottore, Doctoralia, Jameda): uno solo, il migliore
    import re as _re

    def words(t):
        return set(_re.findall(r"\w{4,}", (t or "")[:2000].lower()))
    seen_ad, unique = {}, []
    for j in jobs:  # già in ordine di voto
        w = words(texts.get(normalize(j["url"])))
        sig = (_re.sub(r"\W+", " ", j["title"].lower()).strip(), (j.get("city") or "").lower())
        day = (j.get("posted_at") or "")[:10]
        dup = False
        for prev_w, prev_day in seen_ad.get(sig, []):  # stesso titolo e città: doppione se il testo è quasi uguale
            if w and prev_w:
                dup = len(w & prev_w) / max(1, min(len(w), len(prev_w))) >= 0.7
            else:  # manca un testo: doppione solo se pubblicato lo stesso giorno
                dup = day == prev_day
            if dup:
                break
        if dup:
            continue
        seen_ad.setdefault(sig, []).append((w, day))
        unique.append(j)
    jobs = unique
    keep = {normalize(j["url"]) for j in jobs}
    write(user / "testi.json", {k: v[:12000] for k, v in texts.items() if k in keep and v})

    prof = learn.apply(dict(read(profile, {}), learned=learned))
    fams = {c.get("id") or f"c{i}": c["name"] for i, c in enumerate(prof.get("clusters", [])) if c.get("on", True)}
    fams["cx"] = "Altri ruoli possibili"
    notes = [l.split(" ", 1)[1].strip() for l in log.splitlines() if "Quota gratuita" in l][:1]
    notes = ["Oggi la quota gratuita dell'intelligenza artificiale è finita a metà ricerca: alcuni annunci hanno un voto meno preciso."] if notes else []
    write(user / "risultati.json", {"run": dict(run, seconds=round(time.time() - t0), notes=notes), "families": fams, "jobs": jobs})
    write(user / "stato.json", {"running": False, "ok": True, "at": run["at"], "total": len(jobs), "minutes": run.get("minutes")})
    notify(read(profile, {}), [j for j in jobs if j.get("first_seen") == run["at"]])
    print(f"{len(jobs)} annunci, {round((time.time() - t0) / 60)} minuti")
    print("\n".join(l for l in log.splitlines() if "LinkedIn:" in l or "Giudizio AI:" in l or "finestra" in l)[-2500:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
