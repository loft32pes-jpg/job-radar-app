"""API dell'app Job Radar (una sola funzione, più azioni: /api/index?a=...).

I dati di ogni persona stanno nel ramo "dati" del repo privato: questa funzione li legge e li scrive con un accesso
riservato (JR_GH_TOKEN). Le chiavi AI arrivano da JR_CONFIG. Niente di tutto questo arriva al telefono.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _candidature as cand  # noqa: E402

REPO = os.environ.get("JR_REPO", "loft32pes-jpg/job-radar")              # repo PRIVATO con i dati (ramo "dati")
RUN_REPO = os.environ.get("JR_RUN_REPO", "loft32pes-jpg/job-radar-app")  # repo PUBBLICO del codice: lì gira la ricerca
BRANCH = "dati"
GH = f"https://api.github.com/repos/{REPO}"
SESSION_DAYS = 90
MIN_GAP_MIN = 45  # tra una ricerca e l'altra della stessa persona: LinkedIn e le quote AI non reggono ricerche a raffica
# quante persone al massimo: ogni ricerca giornaliera costa circa 17 minuti dei 2.000 mensili gratuiti di GitHub
# (chi non apre l'app da più di 10 giorni non viene cercato e non consuma)
MAX_USERS = int(os.environ.get("JR_MAX_USERS") or 8)


class Fail(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


# ---------- accesso ----------
def _secret():
    return os.environ["JR_SESSION_SECRET"].encode()


def code_hash(code: str) -> str:
    clean = "".join(c for c in str(code).upper() if c.isalnum())
    return hmac.new(_secret(), clean.encode(), hashlib.sha256).hexdigest()


def make_token(uid: str) -> str:
    exp = str(int(time.time()) + SESSION_DAYS * 86400)
    sig = hmac.new(_secret(), f"{uid}.{exp}".encode(), hashlib.sha256).hexdigest()[:40]
    return f"{uid}.{exp}.{sig}"


def check_token(token: str) -> str:
    try:
        uid, exp, sig = str(token).split(".")
        good = hmac.new(_secret(), f"{uid}.{exp}".encode(), hashlib.sha256).hexdigest()[:40]
        if hmac.compare_digest(sig, good) and int(exp) > time.time() and uid.isalnum():
            return uid
    except (ValueError, AttributeError):
        pass
    raise Fail("Accesso scaduto: apri di nuovo il tuo link personale.", 401)


# ---------- archivio dati su GitHub ----------
def gh(method, url, body=None, raw=False):
    headers = {"Authorization": "Bearer " + os.environ["JR_GH_TOKEN"], "User-Agent": "job-radar-app",
               "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    req = Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as r:
            data = r.read()
            return r.status, (data if raw else (json.loads(data) if data else {}))
    except HTTPError as e:
        return e.code, (b"" if raw else {})


def read(path, default=None):
    status, data = gh("GET", f"{GH}/contents/{quote(path)}?ref={BRANCH}", raw=True)
    if status != 200:
        return default
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        return default


def write(path, obj, message):
    """Scrive un file JSON nel ramo dati. Se nel frattempo è cambiato (ricerca in corso) riprova con la versione nuova."""
    content = base64.b64encode(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode()
    for _ in range(4):
        status, meta = gh("GET", f"{GH}/contents/{quote(path)}?ref={BRANCH}")
        body = {"message": message, "content": content, "branch": BRANCH}
        if status == 200 and isinstance(meta, dict) and meta.get("sha"):
            body["sha"] = meta["sha"]
        status, _ = gh("PUT", f"{GH}/contents/{quote(path)}", body)
        if status in (200, 201):
            return
        time.sleep(0.6)
    raise Fail("Non sono riuscito a salvare. Riprova tra un momento.", 503)


def start_search(uid):
    status, _ = gh("POST", f"https://api.github.com/repos/{RUN_REPO}/actions/workflows/ricerca.yml/dispatches",
                   {"ref": "main", "inputs": {"utente": uid}})
    if status != 204:
        raise Fail("Non sono riuscito ad avviare la ricerca. Riprova tra qualche minuto.", 503)
    write(f"utenti/{uid}/stato.json", {"running": True, "queued": True,
                                       "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, "Ricerca richiesta")


def minutes_since(iso):
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 60
    except (ValueError, TypeError):
        return 1e9


def clean_state(st):
    """Una ricerca "in corso" da più di 65 minuti si è persa per strada: non si lascia l'app bloccata ad aspettare."""
    st = st or {"running": False}
    if st.get("running") and minutes_since(st.get("started_at")) > 65:
        st = {"running": False, "ok": False, "error": "L'ultima ricerca non è arrivata in fondo. Riprova."}
    return st


# ---------- azioni ----------
def a_login(body, _uid):
    users = read("utenti/index.json", {})
    h = code_hash(body.get("code", ""))
    for uid, u in users.items():
        if hmac.compare_digest(u.get("hash", ""), h):
            return {"token": make_token(uid), "name": u.get("name", "")}
    time.sleep(1.2)  # rallenta chi prova codici a caso
    raise Fail("Codice non riconosciuto. Controlla di averlo scritto come te l'hanno mandato.", 401)


def a_entra(body, _uid):
    """Ingresso senza codice: basta il nome. L'accesso resta su questo dispositivo; per gli altri c'è il link personale."""
    name = " ".join(str(body.get("name") or "").split())[:40]
    if len(name) < 2:
        raise Fail("Scrivi come ti chiami.")
    users = read("utenti/index.json", {}) or {}
    if len(users) >= MAX_USERS:
        raise Fail("In questo momento Job Radar è al completo. Chiedi a chi ti ha mandato il link di farti posto.", 403)
    uid = secrets.token_hex(6)
    users[uid] = {"name": name, "created": time.strftime("%Y-%m-%d"), "visto": time.strftime("%Y-%m-%d")}
    write("utenti/index.json", users, "Nuova persona")
    return {"token": make_token(uid), "name": name}


def a_dati(_body, uid):
    paths = ["utenti/index.json", f"utenti/{uid}/profilo.json", f"utenti/{uid}/risultati.json", f"utenti/{uid}/stato.json",
             f"utenti/{uid}/preferiti.json", f"utenti/{uid}/imparato.json"]
    with ThreadPoolExecutor(6) as ex:
        users, prof, res, st, fav, lr = ex.map(read, paths)
    import learn
    for url, f in ((fav or {}).get("favs") or {}).items():
        f["state"] = cand.OLD_STATES.get(f.get("state"), f.get("state") or "interested")
        if isinstance(f.get("job"), dict) and not f["job"].get("company"):  # aggiunto dal sito di un'azienda senza il nome
            f["job"]["company"] = learn.company_from_url(f["job"].get("url") or url)
    if not users or uid not in users:
        raise Fail("Accesso non più valido.", 401)
    today = time.strftime("%Y-%m-%d")
    if users[uid].get("visto") != today:  # la ricerca di ogni mattina si fa solo per chi usa l'app
        users[uid]["visto"] = today
        try:
            write("utenti/index.json", users, "Ultimo accesso")
        except Fail:
            pass
    summary = None
    if prof:
        lr = lr or {}
        summary = {"notify": prof.get("notify") or {}, "answers": prof.get("answers") or {}, "clusters": [{"name": c["name"], "on": c.get("on", True)}
                                                                     for c in prof.get("clusters", [])],
                   "learned": learn.view(lr)}
    res = res or {}
    return {"name": users[uid].get("name", ""), "profile": summary, "run": res.get("run"), "families": res.get("families") or {},
            "jobs": res.get("jobs") or [], "state": clean_state(st), "tracker": fav or {},
            "token": make_token(uid)}  # l'accesso si rinnova a ogni apertura: chi usa l'app non deve mai rientrare


def a_stato(_body, uid):
    return {"state": clean_state(read(f"utenti/{uid}/stato.json"))}


def a_intervista(body, _uid):
    import searchprofile
    ans = body.get("answers") or {}
    if len(str(ans.get("desired") or "").strip()) < 8:
        raise Fail("Descrivi con qualche parola il lavoro che cerchi.")
    try:
        prof = searchprofile.build(ans, None)
    except Exception as e:
        raise Fail("Vale non riesce a rispondere in questo momento. Riprova tra un minuto.", 503) from e
    return {"profile": prof}


def a_profilo(body, uid):
    import searchprofile
    prof = body.get("profile") or {}
    clusters = [c for c in prof.get("clusters") or [] if c.get("titles_en") or c.get("titles_it")]
    if not any(c.get("on", True) for c in clusters):
        raise Fail("Lascia attivo almeno un gruppo di ruoli.")
    st = clean_state(read(f"utenti/{uid}/stato.json"))
    if st.get("running"):
        raise Fail("C'è una ricerca in corso: aspetta che finisca, poi puoi cambiare la ricerca.")
    answers = prof.get("answers") or {}
    answers["places"] = cand.resolve_cities(answers.get("cities"))
    answers["cities"] = [p["typed"] for p in answers["places"]]
    clean = searchprofile._normalize({**prof, "clusters": clusters}, answers, prof.get("provider") or "")
    for c, src in zip(clean["clusters"], sorted(clusters, key=lambda c: c.get("tier", 2))):
        c["on"] = bool(src.get("on", True))
    clean["version"] = int(time.time())  # la ricerca riparte da zero quando il profilo cambia
    old = read(f"utenti/{uid}/profilo.json", {}) or {}
    if old.get("learned_off"):  # i ruoli imparati che ha tolto restano tolti anche se rifà l'intervista
        clean["learned_off"] = old["learned_off"]
    if old.get("notify"):  # e gli avvisi sul telefono restano accesi
        clean["notify"] = old["notify"]
    write(f"utenti/{uid}/profilo.json", clean, "Profilo aggiornato")
    write(f"utenti/{uid}/risultati.json", {"run": None, "families": {}, "jobs": []}, "Profilo cambiato: risultati azzerati")
    start_search(uid)
    return {"started": True}


def a_aggiorna(_body, uid):
    st = clean_state(read(f"utenti/{uid}/stato.json"))
    if st.get("running"):
        return {"started": False, "state": st}
    if not read(f"utenti/{uid}/profilo.json"):
        raise Fail("Prima fai l'intervista con Vale: serve per sapere cosa cercare.")
    wait = MIN_GAP_MIN - minutes_since(st.get("at"))
    if st.get("ok") and wait > 0:
        raise Fail(f"L'ultima ricerca è di poco fa. Puoi rilanciarla tra {int(wait) + 1} minuti.")
    start_search(uid)
    return {"started": True}


def _tracker(uid):
    t = read(f"utenti/{uid}/preferiti.json", {}) or {}
    t.setdefault("favs", {})
    t.setdefault("hidden", {})
    for f in t["favs"].values():  # stati della prima versione
        f["state"] = cand.OLD_STATES.get(f.get("state"), f.get("state") or "interested")
    return t


def _jd(uid, key):
    """Testo completo dell'annuncio, dall'ultima ricerca (resta salvato con la candidatura anche quando l'annuncio sparisce)."""
    from common import normalize_url
    texts = read(f"utenti/{uid}/testi.json", {}) or {}
    return texts.get(normalize_url(key)) or texts.get(key) or ""


def _page_text(page, n=12000):
    """Testo di una pagina qualsiasi senza menu, piè di pagina e moduli (es. il selettore delle lingue del sito)."""
    import re as _re
    import sources
    page = _re.sub(r"(?is)<(header|nav|footer|select|form|noscript)\b.*?</\1>", " ", page or "")
    return sources.strip_html(page, n)


def _fetch_jd(url):
    """Annuncio non letto durante la ricerca: si legge adesso dalla sua pagina (LinkedIn: versione pubblica leggera)."""
    import re as _re
    try:
        import sources
        m = _re.search(r"linkedin\.com/jobs/view/(?:[^/?]*-)?(\d+)", url)
        if m:
            page = sources._open(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}", "text/html", timeout=12)
            body = _re.search(r"show-more-less-html__markup[^>]*>(.*?)</div>", page, _re.S)
            return sources.strip_html(body.group(1) if body else page, 12000)
        return _page_text(sources._open(url, "text/html", timeout=12))
    except Exception:
        return ""


def _save_job(t, uid, key, job, state="interested"):
    today = time.strftime("%Y-%m-%d")
    job = {k: v for k, v in (job or {}).items() if k not in ("reasons",) or len(json.dumps(v)) < 4000}
    t["favs"][key] = {"job": job, "state": state, "note": "", "saved_at": today, "jd": (_jd(uid, key) or _fetch_jd(key))[:12000],
                      "log": [{"s": state, "t": today}]}
    return t["favs"][key]


def a_preferito(body, uid):
    """Candidature: salva un annuncio (con il suo testo completo), cambia stato, note, nascondi."""
    key = str(body.get("key") or "")[:400]
    if not key:
        raise Fail("Annuncio non indicato.")
    path = f"utenti/{uid}/preferiti.json"
    t = _tracker(uid)
    favs, hidden = t["favs"], t["hidden"]
    if "hide" in body:
        if body["hide"]:
            hidden[key] = time.strftime("%Y-%m-%d")
        else:
            hidden.pop(key, None)
    if "fav" in body:
        if body["fav"] and key not in favs:
            _save_job(t, uid, key, body.get("job"), body.get("state") if body.get("state") in cand.STATES else "interested")
        elif not body["fav"]:
            favs.pop(key, None)
    if key in favs:
        f = favs[key]
        if body.get("state") in cand.STATES and body["state"] != f.get("state"):
            f["state"] = body["state"]
            f.setdefault("log", []).append({"s": body["state"], "t": time.strftime("%Y-%m-%d")})
        if "note" in body:
            f["note"] = str(body["note"])[:3000]
        if "why" in body:  # perché l'ha scartato: la ricerca e il giudice imparano da qui
            f["why"] = " ".join(str(body["why"] or "").split())[:200]
    write(path, t, "Candidature aggiornate")
    return {"tracker": t}


def a_preferenze(body, uid):
    """Preferenze per candidarsi (retribuzione, sede, preavviso...): cambiano il materiale scritto dall'AI, non la ricerca."""
    prof = read(f"utenti/{uid}/profilo.json", None)
    if not prof:
        raise Fail("Prima fai l'intervista con Vale.")
    allowed = {"ral": {"auto", "25-30", "30-35", "35-45", "45-60", "60+"}, **{k: set(v) for k, v in cand.APPLY_LABELS.items()}}
    ap = prof.setdefault("answers", {}).setdefault("apply", {})
    for k, ok in allowed.items():
        if body.get(k) in ok:
            ap[k] = body[k]
    write(f"utenti/{uid}/profilo.json", prof, "Preferenze per candidarsi")
    return {"apply": ap}


def a_citta(body, uid):
    """Città dove cercare vicino casa. Non azzera i risultati: valgono dalla prossima ricerca (o subito, se chiesto)."""
    prof = read(f"utenti/{uid}/profilo.json", None)
    if not prof:
        raise Fail("Prima fai l'intervista con Vale.")
    places = cand.resolve_cities(body.get("cities") or [])
    typed = [str(c).strip() for c in body.get("cities") or [] if str(c).strip()]
    if len(places) < min(len(typed), 3):
        missing = [t for t in typed if cand.norm(t) not in {cand.norm(p["typed"]) for p in places}]
        raise Fail(f"Non riconosco la città «{missing[0] if missing else typed[0]}». Prova a scriverla in un altro modo.")
    ans = prof.setdefault("answers", {})
    ans["places"], ans["cities"] = places, [p["typed"] for p in places]
    write(f"utenti/{uid}/profilo.json", prof, "Città dove cercare")
    started = False
    if body.get("cerca"):
        st = clean_state(read(f"utenti/{uid}/stato.json"))
        if not st.get("running") and (not st.get("ok") or minutes_since(st.get("at")) >= MIN_GAP_MIN):
            start_search(uid)
            started = True
    return {"places": places, "started": started}


def a_impara(body, uid):
    """Ruolo, parola o azienda imparati dalle scelte che la persona non vuole: si tolgono e non tornano più."""
    import learn
    prof = read(f"utenti/{uid}/profilo.json", None)
    if not prof:
        raise Fail("Prima fai l'intervista con Vale.")
    t = str(body.get("off") or "").strip()[:60]
    lr = read(f"utenti/{uid}/imparato.json", {}) or {}
    if t:
        off = prof.setdefault("learned_off", [])
        if t.lower() not in {x.lower() for x in off}:
            off.append(t)
        write(f"utenti/{uid}/profilo.json", prof, "Ruolo imparato tolto")
        for k in ("titles_en", "titles_it", "words", "companies"):
            lr[k] = [x for x in lr.get(k) or [] if x.lower() != t.lower()]
        write(f"utenti/{uid}/imparato.json", lr, "Ruolo imparato tolto")
    return {"learned": learn.view(lr)}


def _read_ad(url):
    """Titolo, azienda, luogo e testo di un annuncio da un link qualsiasi (LinkedIn, siti aziendali, portali)."""
    import html as _html
    import re as _re
    import sources
    m = _re.search(r"linkedin\.com/.*?(?:jobs/view/(?:[^/?]*-)?|currentJobId=)(\d{6,})", url)
    if m:
        url = f"https://www.linkedin.com/jobs/view/{m.group(1)}"
        try:
            page = sources._open(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}", "text/html", timeout=15)
        except Exception:  # versione leggera non disponibile: si legge la pagina pubblica dell'annuncio (più sotto)
            page = ""
    if m and page:
        pick = lambda rx: sources.strip_html((_re.search(rx, page, _re.S) or [None, ""])[1], 300)
        body = _re.search(r"show-more-less-html__markup[^>]*>(.*?)</div>", page, _re.S)
        return url, {"title": pick(r'top-card-layout__title[^>]*>(.*?)</h'), "company": pick(r'topcard__org-name-link[^>]*>(.*?)</a>'),
                     "city": pick(r'topcard__flavor--bullet[^>]*>(.*?)</span>'), "source": "LinkedIn"}, \
            sources.strip_html(body.group(1) if body else page, 12000)
    page = sources._open(url, "text/html", timeout=15)
    for raw in _re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, _re.S):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        for d in (data if isinstance(data, list) else data.get("@graph") or [data]):
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                org = d.get("hiringOrganization") or {}
                loc = d.get("jobLocation") or {}
                loc = (loc[0] if isinstance(loc, list) and loc else loc) or {}
                addr = loc.get("address") or {} if isinstance(loc, dict) else {}
                return url, {"title": _html.unescape(str(d.get("title") or ""))[:200],
                             "company": str(org.get("name") if isinstance(org, dict) else org or "")[:120],
                             "city": str(addr.get("addressLocality") or "")[:80] if isinstance(addr, dict) else "", "source": "Aggiunto da te"}, \
                    sources.strip_html(_html.unescape(str(d.get("description") or "")), 12000)
    t = _re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', page) or _re.search(r"<title>(.*?)</title>", page, _re.S)
    site = _re.search(r'<meta[^>]+property="og:site_name"[^>]+content="([^"]+)"', page)
    return url, {"title": _html.unescape(t.group(1).strip())[:200] if t else "",
                 "company": _html.unescape(site.group(1).strip())[:120] if site else "", "city": "", "source": "Aggiunto da te"}, \
        _page_text(page)


def a_importa(body, uid):
    """Annuncio trovato altrove (link incollato): entra nella bacheca e la ricerca impara a trovarne di simili."""
    url = str(body.get("url") or "").strip()[:800]
    if not url.startswith(("http://", "https://")):
        raise Fail("Incolla il link completo dell'annuncio (inizia con https://).")
    try:
        url, job, text = _read_ad(url)
    except Exception:
        raise Fail("Non riesco ad aprire questo link. Se è LinkedIn, copia il link dalla pagina dell'annuncio.")
    if not job.get("title"):
        raise Fail("In questa pagina non trovo un annuncio di lavoro.")
    job["url"] = url
    if not job.get("company"):  # sito dell'azienda senza il nome scritto nella pagina: lo dice l'indirizzo
        import learn
        job["company"] = learn.company_from_url(url)
    t = _tracker(uid)
    if url not in t["favs"]:
        _save_job(t, uid, url, job, "interested")
        if text:
            t["favs"][url]["jd"] = text[:12000]
        t["favs"][url]["added_by_user"] = True
        write(f"utenti/{uid}/preferiti.json", t, "Annuncio aggiunto")
    return {"tracker": t, "job": job}


NTFY = "https://ntfy.sh/"
APP_URL = os.environ.get("JR_APP_URL", "https://job-radar-ivory-phi.vercel.app")


def ntfy_send(topic, title, text):
    """Notifica sul telefono (app ntfy). Il canale è un nome casuale che conosce solo la persona."""
    req = Request(NTFY + topic, data=text.encode("utf-8"), method="POST",
                  headers={"Title": title.encode("utf-8").decode("latin-1", "ignore"), "Click": APP_URL, "Tags": "briefcase",
                           "Content-Type": "text/plain; charset=utf-8"})
    with urlopen(req, timeout=15) as r:
        return r.status == 200


def a_avvisi(body, uid):
    """Accende, spegne o prova gli avvisi sul telefono."""
    prof = read(f"utenti/{uid}/profilo.json", None)
    if not prof:
        raise Fail("Prima fai l'intervista con Vale.")
    n = prof.get("notify") or {}
    if body.get("on") is True and not n.get("topic"):
        n = {"topic": "jobradar-" + secrets.token_hex(10), "min": 70}
    elif body.get("on") is False:
        n = {}
    if body.get("min") in (60, 70, 80):
        n["min"] = body["min"]
    if n != (prof.get("notify") or {}):
        prof["notify"] = n
        write(f"utenti/{uid}/profilo.json", prof, "Avvisi sul telefono")
    if body.get("prova") and n.get("topic"):
        try:
            ntfy_send(n["topic"], "Job Radar: avvisi attivi", "Da ora ti scrivo qui quando trovo annunci nuovi adatti a te.")
        except Exception:
            raise Fail("Non riesco a mandare l'avviso di prova. Riprova tra un momento.", 503)
    return {"notify": n}


def a_luogo(body, _uid):
    return {"place": cand.find_place(str(body.get("q") or "")[:80])}


_ORDER = {"t": 0, "v": []}


def _writing_order():
    if time.time() - _ORDER["t"] > 1800:
        _ORDER["v"], _ORDER["t"] = (read("modelli.json", {}) or {}).get("scrittura") or [], time.time()
    return _ORDER["v"]


def a_kit(body, uid):
    """Tutto il materiale per candidarsi a un annuncio: lettera, email, messaggio, risposte alle domande dei moduli."""
    import ai
    key = str(body.get("key") or "")[:400]
    t = _tracker(uid)
    f = t["favs"].get(key) or _save_job(t, uid, key, body.get("job"))
    if not f.get("jd"):
        f["jd"] = _fetch_jd(key)[:12000]
    prof = read(f"utenti/{uid}/profilo.json", {}) or {}
    user = cand.person_text(prof, str(body.get("cv") or "")) + "\n\n" + cand.job_text(f["job"], f.get("jd"))
    try:
        data, model = ai.write_json(cand.KIT_SYSTEM, user, _writing_order(), budget_s=48)
    except Exception as e:
        raise Fail("L'AI non risponde in questo momento. Riprova tra un minuto.", 503) from e
    f["kit"] = dict(cand.clean_kit(data), modello=model)
    write(f"utenti/{uid}/preferiti.json", t, "Materiale per la candidatura")
    return {"tracker": t, "kit": f["kit"]}


def a_compila(body, uid):
    """Il modulo di candidatura aperto nel browser: risposte per ogni domanda, scritte sull'annuncio di quella pagina."""
    import ai
    from common import normalize_url
    url = str(body.get("url") or "")[:600]
    fields = [x for x in (body.get("fields") or []) if isinstance(x, dict)][:40]
    t = _tracker(uid)
    match = next((f for k, f in t["favs"].items() if normalize_url(k) == normalize_url(url) or
                  (f.get("job", {}).get("company") and f["job"]["company"].lower() in str(body.get("title", "")).lower())), None)
    job = match["job"] if match else {"title": body.get("title", ""), "company": ""}
    jd = (match or {}).get("jd") or str(body.get("page") or "")[:9000]
    prof = read(f"utenti/{uid}/profilo.json", {}) or {}
    ask = "\n".join(f"- id {x.get('id')}: {str(x.get('label') or '')[:200]}" + (f" (opzioni: {' | '.join(map(str, x.get('options') or []))[:300]})" if x.get('options') else "")
                    + (" [testo lungo]" if x.get("long") else "") for x in fields)
    user = cand.person_text(prof, str(body.get("cv") or "")) + "\n\n" + cand.job_text(job, jd) + "\n\nDOMANDE DEL MODULO\n" + (ask or "(nessuna)")
    import re as _re
    wants_letter = any(_re.search(r"cover.?letter|lettera|motivation|motivazione|anschreiben|lettre", str(x.get("label", "")) + " " + str(x.get("name", "")), _re.I)
                       for x in fields)
    if wants_letter:
        user += "\n\nIl modulo chiede una lettera di presentazione: scrivila in \"lettera\" (180-260 parole), nella lingua delle domande."
    try:
        data, model = ai.write_json(cand.FILL_SYSTEM, user, _writing_order(), budget_s=48)
    except Exception as e:
        raise Fail("L'AI non risponde in questo momento. Riprova tra un minuto.", 503) from e
    answers = {str(r.get("id")): str(r.get("r") or "")[:3000] for r in (data.get("risposte") or []) if isinstance(r, dict)}
    letter = str(data.get("lettera") or "") or ((match or {}).get("kit") or {}).get("lettera", "")
    return {"answers": answers, "letter": letter, "job": {"title": job.get("title"), "company": job.get("company")},
            "key": next((k for k, f in t["favs"].items() if f is match), None), "model": model}


ACTIONS = {"login": a_login, "entra": a_entra, "citta": a_citta, "impara": a_impara, "importa": a_importa, "avvisi": a_avvisi, "dati": a_dati, "stato": a_stato, "intervista": a_intervista, "profilo": a_profilo,
           "aggiorna": a_aggiorna, "preferito": a_preferito, "luogo": a_luogo, "kit": a_kit, "compila": a_compila, "preferenze": a_preferenze}


def handle(action, body, token):
    fn = ACTIONS.get(action)
    if not fn:
        raise Fail("Richiesta non riconosciuta.", 404)
    uid = None if action in ("login", "entra") else check_token(token)
    return fn(body or {}, uid)


class handler(BaseHTTPRequestHandler):
    def _run(self):
        action = (parse_qs(urlparse(self.path).query).get("a") or [""])[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            token = (self.headers.get("Authorization") or "").replace("Bearer ", "")
            out, status = dict(handle(action, body, token), ok=True), 200
        except Fail as e:
            out, status = {"ok": False, "error": str(e)}, e.status
        except Exception as e:  # mai mostrare dettagli tecnici a chi usa l'app
            print("ERRORE", action, type(e).__name__, str(e)[:300])
            out, status = {"ok": False, "error": "Qualcosa non ha funzionato. Riprova tra un momento."}, 500
        data = json.dumps(out, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _run
    do_POST = _run

    def log_message(self, *_):
        pass
