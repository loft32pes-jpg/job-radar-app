"""Ricerca che impara dalle scelte della persona.

Gli annunci che salva, a cui si candida, che aggiunge da fuori o che scarta nella bacheca sono le sue preferenze reali,
più precise dell'intervista e più recenti. Quando le scelte e l'intervista non dicono la stessa cosa, valgono le scelte:
- i ruoli degli annunci che le piacciono diventano ruoli cercati (gruppo "Come quelli che hai salvato");
- le parole di mestiere dei titoli che ha scelto allargano il filtro nelle sue città (decide poi il giudice AI);
- le aziende a cui si è candidata o di cui ha salvato annunci vengono seguite: nelle sue città si leggono tutti i loro annunci;
- un filtro dell'intervista che avrebbe tolto annunci che lei ha scelto si spegne (settore escluso, titolo escluso, livello);
- il giudice AI riceve gli esempi e i criteri ricavati dalle scelte, con le più recenti in primo piano.
Non si inventano ruoli: si generalizzano solo i titoli che la persona ha scelto. Quello che toglie dal profilo non torna.
"""
import hashlib
import os
import re
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(__file__))

VERSION = "v4"  # cambia quando cambia il modo di imparare: alla ricerca successiva si ricalcola tutto
LIKED = {"interested", "applied", "replied", "cv_requested", "interview", "offer", "closed", "saved"}
STRONG = {"applied", "replied", "cv_requested", "interview", "offer"}  # si è candidata: è la scelta che pesa di più
STATE_IT = {"interested": "SALVATO", "saved": "SALVATO", "closed": "SALVATO", "discarded": "SCARTATO"}
SYSTEM = """Aiuti un motore di ricerca di annunci di lavoro a imparare dalle scelte di una persona.
Ricevi la sua INTERVISTA iniziale, i ruoli già cercati e le sue SCELTE in ordine di tempo: annunci SALVATI, annunci a cui si è
CANDIDATA (la scelta più forte), annunci AGGIUNTI DA LEI trovati altrove (li ha cercati da sola: il motore non glieli aveva
mostrati) e annunci SCARTATI, a volte con il motivo.
Le scelte valgono più dell'intervista e le scelte recenti valgono più di quelle vecchie: se oggi sceglie annunci che
l'intervista escludeva o non prevedeva, ha cambiato idea e bisogna seguirla.
Ricava:
1. i titoli di ruolo da cercare in più perché la ricerca trovi TUTTI gli annunci simili a quelli scelti: stesso mestiere scritto
   in altri modi, varianti (junior, key, regional, specialist/manager/analyst). Niente ruoli che non derivano dagli annunci scelti,
   niente ruoli tipici degli annunci scartati. Titoli brevi (1-4 parole) come compaiono negli annunci, senza aziende, città o
   livelli inventati. In inglese e in italiano (come li scrivono le aziende italiane);
2. i criteri che il giudice degli annunci deve applicare d'ora in poi: cosa accomuna gli annunci scelti ("likes") e cosa
   accomuna quelli scartati ("dislikes"). Frasi brevi e concrete: tipo di ruolo, settore, tipo di azienda, livello, zona,
   contratto. Solo ciò che le scelte mostrano davvero, niente ipotesi. Ogni "like" deve essere vero per TUTTE le candidature
   e gli annunci aggiunti da lei: se si è candidata in settori diversi (es. software e largo consumo) non scrivere un settore
   solo, scrivi cosa hanno in comune i ruoli. Un "dislike" non deve mai descrivere un annuncio a cui si è candidata;
3. i punti in cui le scelte contraddicono l'intervista o le scelte più vecchie ("changes"): es. aveva escluso un settore e
   poi si è candidata lì; cercava un ruolo e scarta sempre quel ruolo. Solo contraddizioni vere, che si vedono in almeno due
   scelte o in una candidatura: un settore diverso da quello escluso non è una contraddizione. Nel dubbio, lista vuota.
Rispondi SOLO con JSON: {"titles_en": [max 12], "titles_it": [max 8],
"summary": "una frase in italiano, rivolta alla persona (tu), su cosa hai capito che le piace",
"likes": [max 5 frasi in italiano, max 14 parole l'una], "dislikes": [max 5 frasi, max 14 parole l'una],
"changes": [max 3 frasi in italiano rivolte alla persona (tu), es. "Avevi escluso X, ma ti sei candidata a Y: ora li tengo"]}"""

AGENCY = re.compile(r"hays|manpower|adecco|randstad|gi ?group|michael page|page personnel|page executive|\blhh\b|openjobmetis|"
                    r"synergie|grafton|umana|etjca|lavoropi|experis|kelly services|morgan philips|robert walters|praxi|recruit|"
                    r"resourcing|staffing|head ?hunt|executive search|agenzia|talent|just on business|j\.o\.b\.|selezione|interim", re.I)
ROLE = re.compile(r"manager|engineer|analyst|specialist|consultant|owner|executive|representative|developer|coordinator|officer|"
                  r"partner|lead|advisor|responsabile|analista|specialista|consulente|ingegnere|commerciale", re.I)
SENIOR = re.compile(r"\b(director|directeur|direttore|directora?|vp|vice president|head of|chief|principal)\b", re.I)
STAGE = re.compile(r"\b(intern|internship|working student|werkstudent|trainee programme|apprentice|stage|tirocinio|stagiaire)\b", re.I)
JOB_SITES = re.compile(r"linkedin|indeed|glassdoor|talent\.com|infojobs|monster|jooble|europa\.eu|welcometothejungle|google|"
                       r"bit\.ly|joinrs|jobrapido|subito|bakeca|arbeitnow|remotive|himalayas|remoteok|weworkremotely", re.I)


def clean_title(t):
    """'Account Manager - Piemonte (m/f)' -> 'Account Manager'; 'Digital Impulse | Business Analyst' -> 'Business Analyst'."""
    parts = [p.strip() for p in re.split(r"\s+[-–|•·]\s+|\s*\|\s*|\(|\[|,|/\s|:\s", str(t or "")) if p.strip()]
    t = next((p for p in parts if ROLE.search(p)), parts[0] if parts else "")
    t = re.sub(r"\b(italy|italia|torino|turin|milano|remote|hybrid|ibrido|m/f|f/m|h/f|stage|tirocinio)\b.*$", "", t, flags=re.I)
    t = re.sub(r"\s+(I{1,3}|IV|V|\d)$", "", t.strip())                      # livelli interni: "Solution Engineer I"
    t = re.sub(r"(?i)\s+(regions?|emea|europe)$", "", t)
    t = re.sub(r"(?i)^(junior|senior|jr\.?|sr\.?|associate|medior)\s+", "", t)
    t = re.sub(r"\s+", " ", t).strip(" -–&")[:60]
    return t.title() if t.isupper() and len(t) > 5 else t


def company_core(name):
    """'GOMA ELETTRONICA SpA' -> 'GOMA ELETTRONICA', 'Amazon Web Services (AWS)' -> 'Amazon Web Services'."""
    n = re.sub(r"\(.*?\)", " ", str(name or ""))
    n = re.split(r"\s+[-–|•·]\s+|,", n)[0]
    n = re.sub(r"(?i)\b(s\.?p\.?a\.?|s\.?r\.?l\.?|s\.?a\.?s\.?|inc\.?|ltd\.?|gmbh|b\.?v\.?|n\.?v\.?|ab|ag|plc|llc|group|gruppo)(?=\s|$)", " ", n)
    n = re.sub(r"(?i)\s+(italia|italy|europe|emea|iberia|world|netherlands|portugal|ireland|& latam|europe & latam)\s*$", " ", n)
    return re.sub(r"\s+", " ", n).strip(" -–&.,")[:40]


def company_from_url(url):
    """Annuncio aggiunto a mano dal sito di un'azienda, senza il nome: 'https://jobs.lavazza.com/...' -> 'Lavazza'."""
    try:
        u = urlparse(str(url or ""))
    except ValueError:
        return ""
    host = u.netloc.lower().split(":")[0]
    if re.search(r"myworkdayjobs|\.recruitee\.com$|\.personio\.(de|com)$|\.teamtailor\.com$|\.bamboohr\.com$|\.breezy\.hr$", host):
        return re.sub(r"(limited|group|careers|jobs)$", "", host.split(".")[0]).replace("-", " ").strip().title()
    m = re.search(r"(?:greenhouse\.io|lever\.co|ashbyhq\.com|workable\.com|smartrecruiters\.com)/([A-Za-z][\w-]{2,})", str(url))
    if m:
        return "" if m.group(1).lower() in ("jobs", "job", "embed") else m.group(1).replace("-", " ").title()
    if JOB_SITES.search(host):
        return ""
    parts = [p for p in host.split(".") if p not in ("www", "jobs", "careers", "career", "job", "lavoraconnoi", "lavora", "work",
                                                     "join", "apply", "recruiting", "hr", "people", "carriere", "karriere")]
    return parts[0].replace("-", " ").title() if len(parts) >= 2 and len(parts[0]) >= 3 else ""


def rows(tracker):
    """Le scelte nella bacheca, dalla più vecchia alla più recente."""
    out = []
    for url, f in ((tracker or {}).get("favs") or {}).items():
        j = f.get("job") or {}
        if not j.get("title"):
            continue
        log = [x for x in f.get("log") or [] if isinstance(x, dict)]
        state = f.get("state") or "interested"
        out.append({"title": str(j["title"])[:90], "company": (company_core(j.get("company")) or company_from_url(j.get("url") or url))[:40],
                    "city": str(j.get("city") or "")[:30], "state": state, "when": str((log[-1].get("t") if log else "") or f.get("saved_at") or ""),
                    "strong": state in STRONG or any(x.get("s") in STRONG for x in log), "own": bool(f.get("added_by_user")),
                    "why": str(f.get("why") or "")[:80], "jd": str(f.get("jd") or "")[:6000]})
    out.sort(key=lambda r: r["when"])
    return out


def examples(tracker):
    """(scelti, scartati) come li riceve il giudice: [titolo, azienda, nota]."""
    pos, neg = [], []
    for r in rows(tracker):
        if r["state"] == "discarded":
            neg.append((r["title"], r["company"], r["why"]))
        elif r["state"] in LIKED:
            pos.append((r["title"], r["company"], "candidata" if r["strong"] else "aggiunto da lei" if r["own"] else ""))
    return pos, neg


def _overrides(profile, liked):
    """Filtri dell'intervista smentiti dalle scelte: si spengono. Serve più di un annuncio, o una candidatura."""
    import rules
    out = {"unavoid": [], "unexclude": [], "gates_off": []}

    def enough(hit):
        return sum(2 if r["strong"] or r["own"] else 1 for r in liked if hit(r)) >= 2
    for w in profile.get("avoid_words") or []:
        rx = rules._words_rx([w])
        if rx and enough(lambda r: re.search(rx, f"{r['title']} {r['company']}", re.I) or len(re.findall(rx, r["jd"], re.I)) >= 3):
            out["unavoid"].append(w)
    for t in profile.get("exclude_titles") or []:
        rx = rules._words_rx([t])
        if rx and enough(lambda r: re.search(rx, r["title"], re.I)):
            out["unexclude"].append(t)
    if enough(lambda r: SENIOR.search(r["title"])):
        out["gates_off"].append("senior")
    if enough(lambda r: STAGE.search(r["title"])):
        out["gates_off"].append("stage")
    return out


def _words(liked, gone):
    """Parole di mestiere dei titoli scelti: nelle sue città fanno arrivare al giudice anche i titoli non previsti."""
    import rules
    score, bad = {}, {}
    for group, tally in ((liked, score), (gone, bad)):
        for r in group:
            toks = {t for run in rules.title_runs(clean_title(r["title"])) for t in run
                    if len(t) >= 5 and t not in rules.BROAD and not t.isdigit()}
            for t in toks:
                tally[t] = tally.get(t, 0) + (2 if r.get("strong") or r.get("own") else 1)
    keep = [w for w, n in score.items() if n >= 2 and bad.get(w, 0) < n]
    return sorted(keep, key=lambda w: (-score[w], w))[:30]


def learn(profile, tracker, log=print):
    """Ritorna il dizionario "learned" aggiornato (o quello vecchio se le scelte non sono cambiate)."""
    all_rows = rows(tracker)
    liked = [r for r in all_rows if r["state"] in LIKED]
    gone = [r for r in all_rows if r["state"] == "discarded"]
    pos, neg = examples(tracker)
    old = profile.get("learned") or {}
    off = {x.lower() for x in profile.get("learned_off") or []}
    sig = hashlib.sha1(repr((VERSION, sorted(pos), sorted(neg), sorted(off))).encode()).hexdigest()[:16]
    if old.get("sig") == sig:
        return old
    keep = {"deep": old.get("deep") or {}}  # ricerche profonde già fatte: non dipendono dalle scelte
    if not liked:
        return {"sig": sig, "titles_en": [], "titles_it": [], "pos": [], "neg": [list(x) for x in neg[-20:]], **keep}
    a = profile.get("answers") or {}
    cur = [t for c in profile.get("clusters") or [] if c.get("on", True) for t in c.get("titles_en", [])[:4]]

    def line(r):
        what = "CANDIDATA" if r["strong"] else "AGGIUNTO DA LEI" if r["own"] and r["state"] != "discarded" else STATE_IT.get(r["state"], "SALVATO")
        where = ", ".join(x for x in (r["company"], r["city"]) if x)
        return f"- {r['when'] or '?'} {what}: {r['title']}" + (f" ({where})" if where else "") + (f" perché: {r['why']}" if r["why"] else "")
    user = (f"INTERVISTA\nLavoro desiderato: {str(a.get('desired', ''))[:800]}\nLavoro attuale: {a.get('current') or 'non indicato'}\n"
            f"Anni di esperienza: {a.get('years', '?')}\nSettori preferiti: {a.get('prefer') or 'nessuno'}\n"
            f"Settori o lavori esclusi: {a.get('avoid') or 'nessuno'}\nCittà: {', '.join(a.get('cities') or []) or 'nessuna'}\n"
            f"RUOLI GIÀ CERCATI: {', '.join(cur)}\nSCELTE, dalla più vecchia alla più recente:\n" + "\n".join(line(r) for r in all_rows[-80:]))
    criteria, en, it, summary = old.get("criteria") or {}, [], [], old.get("summary") or ""
    try:
        import ai
        data, _model = ai.write_json(SYSTEM, user, [], budget_s=60)
        en, it = data.get("titles_en") or [], data.get("titles_it") or []
        summary = str(data.get("summary") or "")[:240]

        def short(v, n):
            return [re.sub(r"\s+", " ", str(x)).strip()[:160] for x in (v if isinstance(v, list) else []) if str(x).strip()][:n]
        criteria = {"likes": short(data.get("likes"), 5), "dislikes": short(data.get("dislikes"), 5), "changes": short(data.get("changes"), 3)}
    except Exception as e:  # senza AI si cercano i titoli salvati così come sono
        log(f"Apprendimento senza AI ({str(e)[:80]}): uso i titoli salvati")

    taken = set()

    def tidy(xs, n, role=False):  # almeno due parole: "Consultant" da solo prenderebbe mestieri diversissimi
        out = []
        for x in xs:
            x = clean_title(x)
            if 4 < len(x) <= 50 and 1 < len(x.split()) <= 4 and x.lower() not in off and x.lower() not in taken and (not role or ROLE.search(x)):
                taken.add(x.lower())
                out.append(x)
        return out[:n]
    # prima i titoli a cui si è candidata o che ha aggiunto lei, poi i più recenti: nessuno di questi deve restare fuori
    strong = [r["title"] for r in reversed(liked) if r["strong"] or r["own"]]
    rest = [r["title"] for r in reversed(liked) if not (r["strong"] or r["own"])]
    titles_en = tidy(strong, 14, role=True) + tidy(list(en), 12) + tidy(rest, 30, role=True)
    companies = []
    for r in sorted(reversed(liked), key=lambda r: not (r["strong"] or r["own"])):  # stabile: le più recenti restano davanti
        c = r["company"]
        if len(c) >= 3 and not AGENCY.search(c) and c.lower() not in off and c.lower() not in {x.lower() for x in companies}:
            companies.append(c)
    learned = {"sig": sig, "at": time.strftime("%Y-%m-%d"), "titles_en": titles_en[:36], "titles_it": tidy(it, 10),
               "summary": summary, "pos": [list(x) for x in pos[-20:]], "neg": [list(x) for x in neg[-20:]],
               "words": [w for w in _words(liked, gone) if w not in off], "companies": companies[:20], "criteria": criteria,
               **_overrides(profile, liked), **keep}
    log("Imparato dalle tue scelte: " + ", ".join(learned["titles_en"] + learned["titles_it"]))
    return learned


def view(lr):
    """Quello che l'app mostra in "Imparato dalle tue scelte"."""
    lr = lr or {}
    c = lr.get("criteria") or {}
    return {"titles": (lr.get("titles_en") or []) + (lr.get("titles_it") or []), "summary": lr.get("summary") or "", "at": lr.get("at") or "",
            "companies": lr.get("companies") or [], "words": lr.get("words") or [], "likes": c.get("likes") or [],
            "dislikes": c.get("dislikes") or [], "changes": c.get("changes") or [],
            "off": (lr.get("unavoid") or []) + (lr.get("unexclude") or [])}


def apply(profile):
    """Profilo per la ricerca: il gruppo dei ruoli imparati si aggiunge a quelli dell'intervista."""
    lr = profile.get("learned") or {}
    if not (lr.get("titles_en") or lr.get("titles_it")):
        return profile
    p = dict(profile)
    # in coda: un annuncio che rientra in un gruppo dell'intervista resta in quel gruppo; il gruppo imparato allarga la ricerca
    p["clusters"] = list(profile.get("clusters") or []) + [
        {"id": "cL", "name": "Come quelli che hai salvato", "tier": 1, "on": True, "why": lr.get("summary", ""),
         "titles_en": lr.get("titles_en") or [], "titles_it": lr.get("titles_it") or [], "titles_local": {}}]
    return p
