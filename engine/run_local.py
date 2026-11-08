"""Job Radar locale: cerca gli annunci delle ultime 24h in Europa, filtra, valuta e genera "Job Radar.html".

Uso: python scripts/run_local.py [--no-open] [--hours 24] [--notify]
Non richiede installazioni: solo libreria standard di Python.
"""
import argparse
import os
import re
import sys
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import build_page  # noqa: E402
import cvstore  # noqa: E402
import details  # noqa: E402
import linkedin  # noqa: E402
import translate  # noqa: E402
import geo  # noqa: E402
import judge  # noqa: E402
import notify  # noqa: E402
import rules  # noqa: E402
import searchprofile  # noqa: E402
import sources  # noqa: E402
import sources_more  # noqa: E402
import tracker  # noqa: E402
from common import ARCHIVE, DATA, ROOT, normalize_url, read_json, write_json  # noqa: E402

QUERIES = {
    "en": ["business development software", "sales engineer", "pre-sales solutions consultant",
           "account executive SaaS", "technical account manager", "change management", "customer success",
           "sales operations"],
    "it": ["sviluppo commerciale software", "consulente vendite tecniche software"],
    "li": ["sales engineer", "business development", "account executive software", "pre-sales",
           "technical account manager", "change management consultant"],
}


def verify_on_page(job: dict):
    """Riapre la pagina dell'annuncio e rivaluta con il testo completo (le API danno spesso descrizioni tagliate)."""
    try:
        m = re.search(r"greenhouse\.io/([\w-]+)/jobs/(\d+)", job["url"]) if job["source"] == "Greenhouse" else None
        if m:  # le pagine Greenhouse sono dinamiche: il testo completo è nell'API del singolo annuncio
            page = sources.get_json(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}").get("content", "")
            page = __import__("html").unescape(page)
        else:
            page = sources._open(job["url"], "text/html", timeout=25)
    except Exception:
        return job  # pagina non leggibile: teniamo la valutazione sul testo dell'API
    full = sources.strip_html(page, 40000)
    if len(full) > len(job.get("text", "")):
        job = dict(job, text=full)
    ev, why = rules.evaluate(job)
    return ev if ev else {"_dropped": why}


def title_ok(title: str) -> bool:
    return rules.classify(title) is not None


def run(hours: int = 24, log=print, do_notify: bool = False):
    """Esegue la ricerca completa e riscrive archivio e pagina. Ritorna un riepilogo."""
    try:  # il computer non deve andare in sospensione a metà ricerca (vale finché Job Radar è aperto)
        import ctypes
        # anche lo schermo resta acceso: sui portatili recenti, a schermo spento Windows rallenta la rete e la ricerca
        # passa da un quarto d'ora a quaranta minuti
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
    except Exception:
        pass
    cfg = read_json(ROOT / "config.json", {})
    queries, eures_kw = QUERIES, None
    if rules.configure(searchprofile.load()):  # profilo dell'utente: ruoli, competenze e ricerche vengono da lì
        plan = rules.SEARCH
        queries, eures_kw = {"en": plan["en"], "it": plan["it"], "li": plan["en"][:6]}, plan["eures"]
        rules.JUDGE_ON = bool(judge._models()[1])
        log("Profilo di ricerca: " + ", ".join(rules.FAMILY_LABEL.values()))
    started = datetime.now(timezone.utc)
    since = started - timedelta(hours=hours)
    # vicino casa gli annunci sono pochi ogni giorno: per le città scelte si guarda l'ultima settimana
    places = (rules.SEARCH or {}).get("places") or []
    local_since = started - timedelta(days=7)
    today = datetime.now().astimezone().date().isoformat()
    run_at = started.astimezone().isoformat(timespec="minutes")

    def local(d):
        return d.astimezone().strftime("%d/%m %H:%M")

    log(f"Job Radar: annunci pubblicati in Europa dal {local(since)} al {local(started)}")
    # Archivio: ogni annuncio già visto resta dov'è; se è ancora nella finestra delle 24 ore torna nell'elenco di oggi
    files, known, sig_seen, dropped = {}, {}, {}, set()
    for f in ARCHIVE.glob("????-??-??.json"):
        data = read_json(f, None)
        if not data:
            continue
        files[f.stem] = data
        dropped.update(data.get("dropped") or [])  # già bocciati dall'AI: non si rileggono ogni giorno
        for j in data.get("jobs", []):
            known[normalize_url(j["url"])] = j
            sig_seen[(j["company"].lower(), j["title"].lower(), j["country"])] = j
    files.setdefault(today, {"date": today, "jobs": []})
    known_li = {k.rsplit("/", 1)[-1] for k in list(known) + list(dropped) if "linkedin.com/jobs/view/" in k}
    steps = [
        ("Adzuna", lambda: sources.fetch_adzuna(cfg.get("adzuna", {}), queries, since)),
        ("Arbeitnow", lambda: sources.fetch_arbeitnow(since)),
        ("Remotive", lambda: sources.fetch_remotive(since)),
        ("Jobicy", lambda: sources.fetch_jobicy(since)),
        ("EURES (portale UE)", lambda: sources_more.fetch_eures(since, eures_kw)),
        ("Board remote", lambda: sources_more.fetch_remote_boards(since)),
        ("Jooble", lambda: sources_more.fetch_jooble(cfg.get("jooble", {}), queries, since)),
        ("Board aziendali", lambda: sources.fetch_boards(since)),
    ]
    if places:
        steps.insert(0, ("Talent.com (vicino a " + ", ".join(p["name"] for p in places) + ")",
                         lambda: sources_more.fetch_talent(places, rules.SEARCH.get("local") or [], local_since)))
    raw, metas = [], []

    def in_scope(j):
        """Annuncio completo, dentro la finestra di tempo e in Europa."""
        if not j["url"] or not j["title"] or not j["company"]:
            return False
        posted = sources.parse_dt(j["posted_at"])
        if j.get("near"):  # cercato vicino casa: vale l'ultima settimana
            if j["source"] != "LinkedIn" and (not posted or posted < local_since):
                return False
        elif j["source"] == "Jooble":
            # Jooble dichiara solo il giorno (senza ora): vale se è il giorno di inizio finestra o successivo
            if not posted or posted.date() < since.date():
                return False
        elif j["source"] != "LinkedIn" and (not posted or posted < since):
            return False  # data non verificabile o fuori finestra
        if not rules.in_europe(j["location"]):
            return False
        if rules.NON_EUROPE.search(j["title"]) and not rules.infer_country(j["location"]):
            return False  # es. "Solutions Architect - Sydney" con località generica "Remote"
        return True

    # Il giudice AI lavora mentre la ricerca è ancora in corso: ogni annuncio che supera le regole gli arriva subito
    live = judge.Live(rules.PROFILE if rules.JUDGE_ON else None)
    sig_key = {}

    def prejudge(j):
        if not live.on or not in_scope(j):
            return
        key = normalize_url(j["url"])
        if key in known or key in dropped:
            return
        ev, _why = rules.evaluate(j)
        if not ev or ev["score"] < 30:
            return
        country = rules.infer_country(ev["location"]) or "Europa (remote)"
        sig = (ev["company"].lower(), ev["title"].lower(), country)
        if sig in sig_seen or sig in sig_key:
            return
        sig_key[sig] = key
        live.submit(key, {"title": ev["title"], "company": ev["company"], "country": country}, ev.get("text", ""))

    # LinkedIn è la fonte più lenta (una richiesta al secondo su 30 paesi): parte subito e lavora in parallelo alle altre
    log("Fonte: LinkedIn (30 paesi, in parallelo alle altre fonti) ...")
    li_pool = ThreadPoolExecutor(max_workers=1)
    li_future = li_pool.submit(linkedin.fetch_linkedin, cfg.get("linkedin", {}), since, log, known_li, prejudge, local_since)
    for name, fn in steps:
        log(f"Fonte: {name} ...")
        try:
            jobs, meta = fn()
        except Exception as e:  # una fonte che si rompe non ferma le altre
            jobs, meta = [], {"name": name, "ok": False, "reason": str(e)[:100]}
        metas.append(meta)
        raw += jobs
        for j in jobs:
            try:
                prejudge(j)
            except Exception:
                pass
        log(f"  {len(jobs)} annunci grezzi" + ("" if meta["ok"] else f" (non raggiunta: {meta['reason']})"))
    log("In attesa di LinkedIn (legge gli annunci dal più adatto) ...")
    try:
        jobs, meta = li_future.result()
    except Exception as e:
        jobs, meta = [], {"name": "LinkedIn", "ok": False, "reason": str(e)[:100]}
    li_pool.shutdown(wait=False)
    metas.append(meta)
    raw += jobs
    log(f"  LinkedIn: {len(jobs)} annunci grezzi" + ("" if meta["ok"] else f" (non raggiunta: {meta['reason']})"))

    log("Filtri e punteggio ...")
    survivors = []
    discarded, added, batch_keys, in_window = {}, 0, set(), 0
    for j in raw:
        if not in_scope(j):
            continue
        key = normalize_url(j["url"])
        if key in dropped:
            continue
        if key in known and not rules.classify(known[key]["title"]):
            continue  # già in archivio ma fuori dai ruoli della persona: non torna in elenco
        if key in known:  # già in archivio e ancora nella finestra: resta nell'elenco, senza rivalutarlo
            if known[key].get("last_seen") != run_at:
                known[key]["last_seen"] = run_at
                in_window += 1
            continue
        if key in batch_keys:
            continue
        batch_keys.add(key)
        ev, why = rules.evaluate(j)
        if not ev:
            if why != "titolo non target":
                discarded[why] = discarded.get(why, 0) + 1
            continue
        if ev["score"] < (30 if rules.PROFILE else rules.MIN_SCORE):  # con il profilo decide il giudice AI
            discarded["score sotto soglia"] = discarded.get("score sotto soglia", 0) + 1
            continue
        survivors.append(ev)

    # seconda verifica sul testo completo dell'annuncio
    # LinkedIn ed EURES hanno già il testo; Adzuna/Jooble rimandano a pagine di terzi variabili
    skip = ("LinkedIn", "Adzuna", "Jooble", "EURES", "SmartRecruiters")
    to_check = [e for e in survivors if e["source"] not in skip]
    if to_check:
        log(f"Verifica sulla pagina dell'annuncio ({len(to_check)}) ...")
        with ThreadPoolExecutor(max_workers=4) as ex:
            checked = dict(zip((id(e) for e in to_check), ex.map(verify_on_page, to_check)))
    else:
        checked = {}
    new_jobs, new_texts = [], {}
    for e in survivors:
        ev = checked.get(id(e), e)
        if "_dropped" in ev:
            discarded[ev["_dropped"]] = discarded.get(ev["_dropped"], 0) + 1
            continue
        if ev["score"] < (30 if rules.PROFILE else rules.MIN_SCORE):  # con il profilo decide il giudice AI
            discarded["score sotto soglia"] = discarded.get("score sotto soglia", 0) + 1
            continue
        key = normalize_url(ev["url"])
        country = rules.infer_country(ev["location"]) or "Europa (remote)"
        sig = (ev["company"].lower(), ev["title"].lower(), country)
        if sig in sig_seen:  # stesso annuncio ripubblicato (o su più fonti): vale quello già in elenco
            if sig_seen[sig].get("last_seen") != run_at:
                sig_seen[sig]["last_seen"] = run_at
                in_window += 1
            continue
        city = re.sub(r"\s*\([A-Z]{2}\)\s*$", "", ev["location"].split(",")[0]).strip() or country
        pos = geo.locate(city, country, ev["location"])
        info = details.extract(ev["title"], ev.get("text", ""), rules.years_required(ev.get("text", "")), ev.get("criteria"))
        job = {
            "title": ev["title"], "company": ev["company"], "city": city, "country": country, "url": ev["url"],
            "source": ev["source"], "posted_at": ev["posted_at"], "score": ev["score"], "rationale": ev["rationale"],
            "reasons": ev["reasons"], "languages": ev["languages"], "mode": ev["mode"], "salary": ev["salary"],
            "role_family": ev["role_family"], "logo": ev.get("logo") or "", **info,
            "first_seen": run_at, "last_seen": run_at,
        }
        if j_near := ev.get("near"):
            job["near"] = j_near
        sig_seen[sig] = job
        if ev.get("lat") is not None and (not pos or pos[2] != "city"):  # la fonte dà già le coordinate del paese
            pos = (ev["lat"], ev["lon"], "city", "")
        if pos:
            job["lat"], job["lon"], job["geo"] = round(pos[0], 3), round(pos[1], 3), pos[2]
            if pos[2] == "city" and pos[3]:
                job["city"] = pos[3]  # nome ufficiale (es. "Bristol; London" -> "Bristol")
        if job["city"] == country or job["city"].lower() in ("remote", "europe", "emea"):
            job["city"] = ""  # nessuna città indicata: l'annuncio resta, con la sola indicazione del paese
        if ev.get("local_ad"):
            job["local_ad"] = True
            if cfg.get("translate", {}).get("enabled", True):  # annuncio in lingua locale: titolo e riassunto in italiano
                it = translate.to_italian(ev["title"])
                if it and it.lower() != ev["title"].lower():
                    job["title_it"] = it
                if job.get("excerpt"):
                    job["excerpt"] = translate.to_italian(job["excerpt"]) or job["excerpt"]
        new_texts[key] = ev.get("text", "")
        known[key] = job
        files[today]["jobs"].append(job)
        new_jobs.append(job)
        added += 1

    if rules.PROFILE and new_jobs:
        # giudizio AI: legge titolo e inizio dell'annuncio e dice quanto è adatto alla persona. Chi non c'entra esce dall'elenco.
        ranked = sorted(new_jobs, key=lambda j: -j["score"])
        votes = live.close(120)  # voti già dati durante la ricerca (finisce la coda rimasta)
        for j in ranked:
            key = normalize_url(j["url"])
            vote = votes.get(key) or votes.get(sig_key.get((j["company"].lower(), j["title"].lower(), j["country"])))
            if vote:
                j.update(vote)
        left = [j for j in ranked if "ai_fit" not in j]
        log(f"Giudizio AI: {len(ranked) - len(left)} annunci già valutati durante la ricerca, {len(left)} da valutare ora ...")
        judge.run(rules.PROFILE, [(j, new_texts.get(normalize_url(j["url"]), "")) for j in left], log, budget_s=240)
        out = 0
        for j in ranked:
            fit = j.get("ai_fit")
            if fit is None:
                keep = j["role_family"] != rules.OTHER and j["score"] >= rules.MIN_SCORE  # non valutato: resta solo se regge a regole
            else:
                excluded = bool(j.pop("ai_x", False))            # settore escluso dall'utente: fuori, qualunque sia il voto
                liked = bool(j.pop("ai_p", False)) or j.get("preferred")
                keep = fit >= 40 and not excluded                 # sotto 40 c'entra poco o niente
                j["score_rules"] = j["score"]
                j["score"] = min(100, round(0.25 * j["score"] + 0.75 * fit) + (8 if liked else 0))
                if liked and not any(r["t"] == "Settore che preferisci" for r in j["reasons"]):
                    j["reasons"].insert(1, {"t": "Settore che preferisci", "k": "ok"})
                    j["preferred"] = True
                j["reasons"].insert(1, {"t": j.get("ai_why") or "Valutato dall'AI", "k": "ok" if fit >= 60 else "warn"})
            if not keep:
                key = normalize_url(j["url"])
                if fit is not None:
                    files[today].setdefault("dropped", []).append(key)
                files[today]["jobs"].remove(j)
                known.pop(key, None)
                new_texts.pop(key, None)
                new_jobs.remove(j)
                added -= 1
                out += 1
        if out:
            discarded["non adatto secondo il giudizio AI"] = out
    consulted = [m["name"] for m in metas if m["ok"]]
    def plain(reason):  # gli errori tecnici di rete diventano una frase leggibile
        return "non raggiungibile in questo momento (rete)" if re.search(r"urlopen|getaddrinfo|timed out|Errno", reason or "") else reason
    failed = [{"name": m["name"], "reason": plain(m["reason"])} for m in metas if not m["ok"]]
    for m in metas:
        for d in m.get("dead", []):
            log(f"  board non raggiunto: {d}")
    total = in_window + added
    files[today].update(generated_at=run_at, sources_consulted=consulted, sources_failed=failed)
    for day, data in files.items():
        data["jobs"].sort(key=lambda j: -j["score"])
        write_json(ARCHIVE / f"{day}.json", data)
    minutes = round((datetime.now(timezone.utc) - started).total_seconds() / 60)
    write_json(DATA / "ultima_ricerca.json", {
        "at": run_at, "since": since.astimezone().isoformat(timespec="minutes"), "hours": hours, "total": total, "added": added,
        "minutes": minutes, "sources_consulted": consulted, "sources_failed": failed,
    })
    cvstore.save_texts(today, new_texts)
    if cvstore.CV_TXT.exists():
        n = cvstore.apply_to_archives()
        log(f"CV confrontato con {n} annunci")
    log(f"Annunci nella finestra delle {hours} ore: {total}, di cui {added} mai visti prima ({minutes} minuti di ricerca)")
    if discarded:
        log("Scartati: " + ", ".join(f"{k} ({v})" for k, v in sorted(discarded.items(), key=lambda x: -x[1])))
    path = build_page.main()

    top = sorted(new_jobs, key=lambda j: -j["score"])
    summary = {"added": added, "total": total, "best": top[0]["score"] if top else 0, "top": top[:3], "path": path}
    if do_notify:
        ncfg = cfg.get("notify", {})
        if ncfg.get("provider") and added > 0:
            ok, detail = notify.send(ncfg, notify.build_message(summary))
            log(("Notifica inviata" if ok else "Notifica NON inviata") + f" ({detail})")
        elif ncfg.get("provider"):
            log("Nessun nuovo annuncio: notifica non inviata")
    log("Fatto.")
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # ricerca finita: lo schermo può tornare a spegnersi
    except Exception:
        pass
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true", help="non aprire il browser a fine ricerca")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--notify", action="store_true", help="invia la notifica sul telefono (se configurata)")
    args = ap.parse_args()
    logfile = ROOT / "data" / "ultimo_log.txt"  # utile quando parte da solo, senza finestra
    logfile.write_text("", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        with open(logfile, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} {msg}\n")

    try:
        summary = run(args.hours, log=log, do_notify=args.notify)
    except Exception as e:
        log(f"ERRORE: {type(e).__name__}: {e}")
        raise
    print(f"Pagina: {summary['path']}")
    if not args.no_open:
        webbrowser.open(summary["path"].as_uri())


if __name__ == "__main__":
    main()
