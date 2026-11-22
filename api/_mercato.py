"""Mercato nascosto: aziende delle città della persona che probabilmente assumono nei suoi ruoli senza averlo scritto
sui portali (LinkedIn, Indeed...). Tre segnali gratuiti:
1. notizie recenti (Google News): round di finanziamento, nuove sedi, espansioni, piani di assunzione;
2. aziende che nelle sue città pubblicano annunci per altri ruoli (crescono, ma il suo ruolo non l'hanno pubblicato);
3. siti carriere delle aziende (Greenhouse, Lever, Ashby, Workable, Personio, Recruitee, SmartRecruiters, Teamtailor):
   molte startup pubblicano solo lì. Se un'azienda ne ha uno, la ricerca lo legge da quel momento a ogni giro.
Al web va solo il nome della città, delle aziende e delle parole di ricerca, mai i dati della persona.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import _colloqui as coll

NEWS_Q = {
    "IT": ["{c} startup round", "startup {adj} raccoglie", "startup {adj} round seed", "{c} round Series A", "{c} aumento di capitale startup",
           "azienda {adj} nuove assunzioni", "{c} apre nuova sede", "{c} nuovo hub innovazione", "{c} scaleup investimento",
           "{c} software azienda cresce", "{c} azienda espansione internazionale", "{c} venture capital investe"],
    "ES": ["{c} startup ronda financiación", "startup {adj} levanta millones", "{c} empresa contratará", "{c} startup raises",
           "{c} nueva oficina tecnológica", "{c} scaleup hiring", "{c} startup Serie A", "{c} hub tecnológico abre"],
    "NL": ["{c} startup raises", "{c} scale-up funding", "{c} haalt miljoen op", "{c} opent kantoor", "{c} startup hiring",
           "{c} scaleup expands", "{c} Series A", "{c} startup investering"],
}
ADJ = {"Torino": "torinese", "Milano": "milanese", "Roma": "romana", "Bologna": "bolognese", "Napoli": "napoletana",
       "Firenze": "fiorentina", "Genova": "genovese", "Barcelona": "barcelonesa", "Madrid": "madrileña", "Valencia": "valenciana"}
NEWS_LANG = {"IT": "it", "ES": "es", "NL": "nl", "FR": "fr", "DE": "de"}

ATS_RX = [  # (ats, regex sul codice della pagina, gruppo con lo slug)
    ("greenhouse", r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)"),
    ("lever", r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
    ("workable", r"apply\.workable\.com/([A-Za-z0-9_-]+)"),
    ("recruitee", r"([A-Za-z0-9-]+)\.recruitee\.com"),
    ("personio", r"([A-Za-z0-9-]+)\.jobs\.personio\.(?:de|com)"),
    ("smartrecruiters", r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
    ("teamtailor", r"([A-Za-z0-9-]+)\.teamtailor\.com"),
]
BAD_SLUG = {"embed", "js", "assets", "static", "api", "www", "careers", "jobs", "widget", "v1", "cdn", "app"}
CAREERS = re.compile(r"career|carrier|jobs?\b|lavora|work-with-us|join|trabaja|empleo|werken|vacature|vacancies|opportunit|talent", re.I)


def _get(url, timeout=8):
    return coll._get(url, timeout)


def city_name(p):
    """Nome della città nella lingua delle notizie locali (Torino, non Turin)."""
    return p.get("typed") if p.get("cc") == "IT" and p.get("typed") else p.get("name")


def news_signals(places, days=120):
    """Titoli di notizie recenti con segnali di crescita, per ogni città. [{t, u, d, citta}]"""
    jobs = []
    for p in places[:3]:
        c = city_name(p)
        for q in NEWS_Q.get(p.get("cc"), ["{c} startup raises", "{c} company expands hiring", "{c} new office"]):
            jobs.append((p, q.format(c=c, adj=ADJ.get(c, c))))
    out, seen = [], set()
    with ThreadPoolExecutor(10) as ex:
        res = list(ex.map(lambda pq: (pq[0], coll.news(pq[1], NEWS_LANG.get(pq[0].get("cc"), "en"), n=25)), jobs))
    limit = time.time() - days * 86400
    for p, items in res:
        for it in items:
            key = re.sub(r"\W+", " ", it["t"].lower())[:80]
            if key in seen:
                continue
            try:
                when = time.mktime(time.strptime(it.get("s", "")[:16], "%a, %d %b %Y"))
            except ValueError:
                when = time.time()
            if when < limit:
                continue
            seen.add(key)
            out.append({"t": it["t"], "u": it["u"], "d": time.strftime("%Y-%m-%d", time.localtime(when)), "citta": p.get("typed") or p.get("name")})
    return out[:300]


HIDDEN_NAME = re.compile(r"confiden|riservat|anonym|anonim|undisclosed|stealth|harnham|robert walters|hays|recruit|headhunt|"
                         r"selection|search|consult(ing)? partners|work ?force|people ?solution|jobs?|empleo|uitzend", re.I)


def archive_companies(jobs, agency_rx):
    """Aziende con annunci nelle città della persona (di qualsiasi ruolo): stanno assumendo lì."""
    by = {}
    for j in jobs or []:
        if not j.get("near") or not j.get("company") or agency_rx.search(j["company"]) or HIDDEN_NAME.search(j["company"]):
            continue
        e = by.setdefault(j["company"].strip(), {"n": 0, "titoli": [], "citta": j["near"]})
        e["n"] += 1
        if len(e["titoli"]) < 4:
            e["titoli"].append(str(j.get("title") or "")[:80])
    return sorted(([k, v] for k, v in by.items()), key=lambda x: -x[1]["n"])[:80]


SYSTEM = """Sei una consulente di carriera esperta del mercato del lavoro locale. Aiuti una persona a trovare aziende
che probabilmente assumono nel suo ruolo SENZA averlo pubblicato sui portali (il "mercato nascosto"): chi ha appena
raccolto un finanziamento, apre una sede, si espande, cresce in fretta, o assume in altri reparti.
Ricevi: il profilo della persona (ruoli che cerca, esperienza, settori esclusi), le sue città, notizie recenti numerate
e l'elenco delle aziende che hanno annunci nelle sue città.
Regole:
- Scegli SOLO aziende che compaiono nelle notizie o nell'elenco ricevuto. Mai aziende inventate o prese a memoria.
- Solo aziende dove il ruolo che la persona cerca può esistere davvero (dimensione, settore, fase). Escludi le agenzie per il
  lavoro, le aziende dei settori che ha escluso, le pubbliche amministrazioni, le notizie che non parlano di un'azienda precisa.
- Escludi le aziende che ha già in bacheca.
- Preferisci segnali recenti e forti (finanziamenti, espansioni, nuove sedi nelle sue città) e aziende nelle sue città.
- Scrivi in italiano, frasi brevi e concrete, rivolte alla persona (tu).
Rispondi SOLO con JSON:
{"aziende": [{"nome": "<nome dell'azienda come nelle fonti>", "citta": "<una delle sue città>", "settore": "<settore, 2-4 parole>",
 "segnale": "<cosa fa pensare che assumano, con la data se c'è>", "notizia": <numero della notizia o null>,
 "perche": "<perché fa per te, 1-2 frasi>", "ruolo": "<il ruolo da proporre, con il titolo che userebbero loro>",
 "contatto": "<chi cercare su LinkedIn per scrivere: es. 'Head of Sales', 'founder', 'responsabile HR'>",
 "come": "<come presentarti: candidatura spontanea, messaggio su LinkedIn, evento, presentazione da un contatto>",
 "priorita": "<alta|media>"}]}
Da 15 a 25 aziende, in ordine di priorità, distribuite tra le sue città con più spazio alla prima città.
Le grandi aziende che pubblicano già tutto sui portali valgono poco: preferisci startup, scaleup e PMI in crescita."""

MSG_SYSTEM = """Scrivi per una persona una candidatura spontanea a un'azienda che non ha pubblicato annunci nel suo ruolo.
""" + "\n".join(l for l in __import__("_candidature").PERSON_RULES.splitlines()[1:]) + """
- È una candidatura spontanea: niente "ho visto il vostro annuncio". Si apre con il motivo concreto per cui scrivi proprio ora
  (il segnale: finanziamento, nuova sede, crescita) e con cosa puoi fare per loro nel ruolo proposto.
- Scrivi nella lingua dell'azienda e della città (Italia: italiano; altrove: inglese, salvo aziende chiaramente locali).
Rispondi SOLO con JSON: {"lingua": "<codice ISO>", "oggetto": "<oggetto dell'email>", "email": "<email, 110-160 parole>",
 "linkedin": "<messaggio per chi indicato come contatto, massimo 300 caratteri>"}"""


def clean(data, news, archive_names, have):
    known = [n.lower() for n in archive_names]
    titles = " || ".join(n["t"].lower() for n in news)
    out, seen = [], set()
    for a in (data.get("aziende") or [])[:24]:
        if not isinstance(a, dict):
            continue
        name = coll._s(a.get("nome"), 80)
        low = name.lower()
        if len(name) < 2 or low in seen or low in have:
            continue
        # solo aziende davvero presenti nelle fonti (basta la parola principale del nome), mai agenzie o nomi nascosti
        main = max(re.findall(r"\w{3,}", low) or [low], key=len)
        if HIDDEN_NAME.search(name) or not (any(low == k or low in k or k in low for k in known)
                                            or re.search(r"\b" + re.escape(main) + r"\b", titles)):
            continue
        seen.add(low)
        try:
            ni = int(a.get("notizia")) if a.get("notizia") is not None else None
        except (TypeError, ValueError):
            ni = None
        n = news[ni] if ni is not None and 0 <= ni < len(news) else None
        out.append({"nome": name, "citta": coll._s(a.get("citta"), 40), "settore": coll._s(a.get("settore"), 60),
                    "segnale": coll._s(a.get("segnale"), 300), "notizia": {"t": n["t"], "u": n["u"], "d": n["d"]} if n else None,
                    "perche": coll._s(a.get("perche"), 400), "ruolo": coll._s(a.get("ruolo"), 120), "contatto": coll._s(a.get("contatto"), 120),
                    "come": coll._s(a.get("come"), 300), "priorita": "alta" if str(a.get("priorita")).lower().startswith("a") else "media"})
    return out


def careers(company, hint_domain=""):
    """Sito, pagina carriere e piattaforma degli annunci di un'azienda. {sito, carriere, ats, slug}"""
    domain = hint_domain or coll.official_domain(company)
    if not domain:
        for r in coll.search(f"{company} careers jobs", n=5):
            host = urlparse(r["u"]).netloc.lower()
            if not coll.NOT_OFFICIAL.search(r["u"]) and re.sub(r"\W", "", company.lower())[:5] in host.replace(".", "").replace("-", ""):
                domain = host.removeprefix("www.")
                break
    out = {"sito": f"https://{domain}" if domain else "", "carriere": "", "ats": "", "slug": ""}
    if not domain:
        return out
    pages = []
    try:
        home = _get(out["sito"], 8)
        pages.append(home)
        links = [urljoin(out["sito"] + "/", h) for h in re.findall(r'href="([^"#]+)"', home)]
        cand = [u for u in links if CAREERS.search(u) and len(u) < 200]
        cand.sort(key=lambda u: (urlparse(u).netloc.endswith(domain) is False, len(u)))
        for u in cand[:2]:
            try:
                pages.append(_get(u, 8))
                out["carriere"] = out["carriere"] or u
            except Exception:
                continue
    except Exception:
        pass
    blob = " ".join(pages) + " " + out["carriere"]
    for ats, rx in ATS_RX:
        for m in re.finditer(rx, blob):
            slug = m.group(1).strip(".")
            if slug.lower() not in BAD_SLUG:
                out["ats"], out["slug"] = ats, slug
                if ats == "teamtailor" and out["carriere"] and "teamtailor.com" not in out["carriere"]:
                    out["slug"] = "https://" + urlparse(out["carriere"]).netloc  # sito carriere con dominio dell'azienda
                return out
    return out


def open_jobs(ats, slug, company, classify):
    """Annunci aperti sul sito carriere e quanti sono nei ruoli della persona."""
    import sources
    try:
        jobs = list(sources.ATS[ats](slug))[:300]
    except Exception:
        return None
    import rules

    def fits(j):  # nei suoi ruoli (non basta una parola in comune: quella è la rete larga che poi filtra il giudice) e in Europa
        c = j.get("title") and classify(j["title"], None, company)
        return bool(c) and c[0] != "cx" and rules.in_europe(j.get("location") or "")
    mine = [j for j in jobs if fits(j)]
    return {"n": len(jobs), "tuoi": [{"t": j["title"][:120], "u": j.get("url") or "", "luogo": (j.get("location") or "")[:80]} for j in mine[:6]]}
