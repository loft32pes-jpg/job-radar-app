"""Preparazione ai colloqui: ricerca sul web dell'azienda, piano di preparazione, simulazione con correzione delle risposte.

Al web va solo il nome dell'azienda e il ruolo, mai i dati della persona. All'AI arrivano il profilo e il testo del CV
senza email, telefono e link (come per il materiale delle candidature).
"""
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
# siti che non si lasciano leggere o che non dicono niente dell'azienda: restano solo come risultato di ricerca
NO_FETCH = re.compile(r"glassdoor\.|linkedin\.|indeed\.|facebook\.|instagram\.|tiktok\.|x\.com|twitter\.|youtube\.|reddit\.|"
                      r"crunchbase\.|zoominfo\.|teamtailor|greenhouse\.io|lever\.co|ashbyhq|workable\.", re.I)
NOT_OFFICIAL = re.compile(NO_FETCH.pattern + r"|wikipedia\.|bloomberg\.|forbes\.|techcrunch\.|sifted\.|dealroom\.|pitchbook\.|"
                          r"comparably\.|kununu\.|welcometothejungle|builtin|g2\.com|capterra|trustpilot|news|blog", re.I)

ROUNDS = {"hr": "primo colloquio conoscitivo con le risorse umane (screening)", "manager": "colloquio con il responsabile del team",
          "tecnico": "colloquio tecnico o caso pratico", "assessment": "assessment o colloquio di gruppo", "finale": "colloquio finale con la direzione"}
MODES = {"video": "in videochiamata", "presenza": "di persona", "telefono": "al telefono"}
LANGS = {"it": "italiano", "en": "inglese", "es": "spagnolo", "fr": "francese", "de": "tedesco", "nl": "olandese", "pt": "portoghese"}
TYPES = ["presentazione", "motivazione", "azienda", "ruolo", "competenze", "comportamentale", "situazionale", "curiosita", "scomoda", "pratica"]


# ---------- ricerca sul web (gratis, senza chiavi) ----------
def _get(url, timeout=8):
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                                "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"})
    with urlopen(req, timeout=timeout) as r:
        return r.read(1_500_000).decode("utf-8", "replace")


def _text(page, n):
    page = re.sub(r"(?is)<(script|style|noscript|svg|header|nav|footer|form|select)\b.*?</\1>", " ", page or "")
    page = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</div>", ". ", page)
    t = html.unescape(re.sub(r"<[^>]+>", " ", page))
    t = re.sub(r"\s+", " ", t)
    return re.sub(r"(\. ){2,}", ". ", t).strip()[:n]


def search(q, n=8, fallback=True):
    """Risultati di DuckDuckGo (versione html); se non risponde e fallback=True, Bing in formato RSS. [{t, u, s}]"""
    out = []
    try:
        page = _get("https://html.duckduckgo.com/html/?q=" + quote_plus(q))
        for m in re.finditer(r'class="result__a" href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', page, re.S):
            u = m.group(1)
            if "uddg=" in u:
                u = unquote(parse_qs(urlparse(u if u.startswith("http") else "https:" + u).query).get("uddg", [""])[0])
            if u.startswith("http") and "duckduckgo.com/y.js" not in u:
                out.append({"t": _text(m.group(2), 160), "u": u, "s": _text(m.group(3), 400)})
    except Exception:
        pass
    if not out and fallback:
        try:
            page = _get("https://www.bing.com/search?format=rss&q=" + quote_plus(q))
            for t, u, d in re.findall(r"<item><title>(.*?)</title><link>(.*?)</link><description>(.*?)</description>", page, re.S):
                out.append({"t": _text(t, 160), "u": html.unescape(u), "s": _text(d, 400)})
        except Exception:
            pass
    return out[:n]


def youtube(q, n=6):
    """Video di YouTube (pagina dei risultati, senza chiave). [{id, t, ch, len}]"""
    try:
        page = _get("https://www.youtube.com/results?search_query=" + quote_plus(q) + "&hl=it")
        m = re.search(r"var ytInitialData = (\{.*?\});</script>", page, re.S)
        data = json.loads(m.group(1)) if m else {}
    except Exception:
        return []
    out, seen = [], set()

    def walk(x):
        if isinstance(x, dict):
            v = x.get("videoRenderer")
            if isinstance(v, dict) and v.get("videoId") and v["videoId"] not in seen:
                seen.add(v["videoId"])
                runs = lambda k: "".join(r.get("text", "") for r in ((v.get(k) or {}).get("runs") or []))
                out.append({"id": v["videoId"], "t": runs("title")[:140], "ch": runs("ownerText")[:60],
                            "len": ((v.get("lengthText") or {}).get("simpleText") or "")[:10]})
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(data)
    return out[:n]


def wikipedia(company, lang):
    """Riassunto di Wikipedia, solo se la voce parla davvero di un'azienda con quel nome."""
    for wl in dict.fromkeys([lang if lang in ("it", "en", "es", "fr", "de", "nl") else "en", "en"]):
        try:
            res = json.loads(_get(f"https://{wl}.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch="
                                  + quote_plus(company + " azienda" if wl == "it" else company + " company")))
            for hit in res.get("query", {}).get("search", []):
                if company.lower().split()[0] not in hit["title"].lower():
                    continue
                s = json.loads(_get(f"https://{wl}.wikipedia.org/api/rest_v1/page/summary/" + quote_plus(hit["title"].replace(" ", "_"))))
                ext = s.get("extract") or ""
                if re.search(r"compan|azienda|societ|startup|start-up|empresa|entreprise|unternehmen|bedrijf|firm|founded|fondat", ext, re.I):
                    return {"t": s.get("title"), "u": (s.get("content_urls") or {}).get("desktop", {}).get("page", ""), "s": ext[:1500]}
        except Exception:
            continue
    return None


def _site(results, company):
    """Sito ufficiale: il primo risultato che non è un portale, una testata o un social e il cui indirizzo somiglia al nome."""
    key = re.sub(r"[^a-z0-9]", "", company.lower())[:8]
    for r in results:
        host = urlparse(r["u"]).netloc.lower()
        if not NOT_OFFICIAL.search(r["u"]) and key and key[:5] in host.replace("-", "").replace(".", ""):
            labels = host.split(".")
            keep = 3 if len(labels) > 2 and labels[-2] in ("co", "com", "org", "net") else 2
            return "https://" + ".".join(labels[-keep:])  # app.eu.legora.com -> legora.com
    return ""


def _pages_of_site(home):
    """Home page del sito ufficiale più le pagine "chi siamo", "carriere", "valori" che la home collega."""
    out = []
    try:
        page = _get(home, 8)
    except Exception:
        return out
    out.append({"u": home, "s": _text(page, 2500)})
    links = []
    for href in re.findall(r'href="([^"#]+)"', page):
        u = href if href.startswith("http") else home.rstrip("/") + "/" + href.lstrip("/")
        if urlparse(u).netloc.lower() == urlparse(home).netloc.lower() and \
                re.search(r"about|chi-siamo|company|azienda|careers?|lavora|jobs|culture|values|valori|mission|who-we-are|nosotros|empresa", u, re.I):
            links.append(u.split("?")[0])
    for u in list(dict.fromkeys(links))[:3]:
        try:
            out.append({"u": u, "s": _text(_get(u, 7), 2500)})
        except Exception:
            pass
    return out


def official_domain(company):
    """Dominio ufficiale dal servizio gratuito di Clearbit, solo se il nome coincide (es. Factorial -> factorialhr.com)."""
    try:
        for x in json.loads(_get("https://autocomplete.clearbit.com/v1/companies/suggest?query=" + quote_plus(company), 5))[:5]:
            if re.sub(r"\W", "", str(x.get("name", "")).lower()) == re.sub(r"\W", "", company.lower()) and x.get("domain"):
                return x["domain"]
    except Exception:
        pass
    return ""


def news(q, lang, n=8):
    """Notizie recenti da Google News (feed RSS pubblico, senza chiave)."""
    gl = {"it": ("it", "IT"), "es": ("es", "ES"), "fr": ("fr", "FR"), "de": ("de", "DE"), "nl": ("nl", "NL")}.get(lang, ("en", "US"))
    try:
        page = _get(f"https://news.google.com/rss/search?q={quote_plus(q)}&hl={gl[0]}&gl={gl[1]}&ceid={gl[1]}:{gl[0]}", 8)
    except Exception:
        return []
    out = []
    for item in re.findall(r"<item>(.*?)</item>", page, re.S)[:n]:
        t = re.search(r"<title>(.*?)</title>", item, re.S)
        u = re.search(r"<link>(.*?)</link>", item, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", item, re.S)
        if t and u:
            out.append({"t": _text(t.group(1), 200), "u": html.unescape(u.group(1).strip()), "s": (d.group(1)[:16] if d else ""), "k": "notizie"})
    return out


def ddg_many(queries, deadline):
    """Più ricerche una dopo l'altra (DuckDuckGo blocca le raffiche); si ferma se blocca o se il tempo finisce."""
    t0, out = time.time(), {}
    for k, q in queries.items():
        if time.time() - t0 > deadline:
            break
        res = search(q, fallback=(k == "sito"))  # per le domande dei colloqui Bing in RSS non trova niente di utile
        out[k] = res
        if not res:
            break
    return out


def ai_search(company, title, groq_key, lang):
    """Se la ricerca normale non trova come fa i colloqui l'azienda, la fa un'AI che naviga (Groq, gratis entro la quota)."""
    if not groq_key:
        return ""
    q = (f"Search the web for how {company} runs its hiring process and job interviews, especially for a role like "
         f"\"{title}\": interview stages, assessments or case studies, questions candidates report (Glassdoor, Indeed, Reddit, blogs), "
         f"what they look for, company values. Answer in {LANGS.get(lang, 'English')} with a compact list of facts, each with its source URL.")
    for model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
        try:
            body = {"model": model, "messages": [{"role": "user", "content": q}], "tools": [{"type": "browser_search"}],
                    "tool_choice": "required", "reasoning_effort": "low", "max_completion_tokens": 1800}
            req = Request("https://api.groq.com/openai/v1/chat/completions", data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json", "User-Agent": "JobRadar/1.0", "Authorization": "Bearer " + groq_key})
            with urlopen(req, timeout=40) as r:
                return str(json.load(r)["choices"][0]["message"].get("content") or "")[:6000]
        except Exception:
            continue
    return ""


def gather(job, lang, deadline=20, groq_key=""):
    """Tutto quello che si trova gratis sul web su un'azienda, per prepararsi a un colloquio. Al web va solo azienda e ruolo."""
    company = " ".join(str(job.get("company") or "").split())[:80]
    title = re.sub(r"\s*[(\[].*?[)\]]", "", " ".join(str(job.get("title") or "").split()))[:90]
    if not company:
        return {"web": [], "video": [], "pagine": [], "wiki": None, "sito": "", "ai": ""}
    t0 = time.time()
    domain = official_domain(company)
    root = domain.split(".")[0] if domain else ""
    # nomi ambigui (Factorial, Mews...): si aggiunge il nome del sito per non trovare altro
    qn = company if not root or re.sub(r"\W", "", company.lower()) == root else f"{company} {root}"
    queries = {"colloquio": f"{qn} interview questions process", "ruolo": f"{qn} {title} interview",
               **({"colloquio_it": f"{qn} colloquio di lavoro domande"} if lang == "it" else {}),
               "cultura": f"{qn} company culture values"}
    if not domain:
        queries = {"sito": f"{company} official website", **queries}
    ex = ThreadPoolExecutor(8)
    fut = {"ddg": ex.submit(ddg_many, queries, deadline * 0.45), "notizie": ex.submit(news, qn, lang),
           "video_colloquio": ex.submit(youtube, f"{qn} interview"), "video_azienda": ex.submit(youtube, f"life at {qn}"),
           "wiki": ex.submit(wikipedia, company, lang)}
    wait(list(fut.values()), timeout=deadline * 0.55)
    got = {k: (f.result() if f.done() and not f.exception() else None) for k, f in fut.items()}
    ddg = got["ddg"] or {}
    web, seen = [], set()
    for k in ("colloquio", "colloquio_it", "ruolo", "cultura"):
        for r in ddg.get(k) or []:
            if r["u"] not in seen:
                seen.add(r["u"])
                web.append(dict(r, k=k))
    if not got["video_colloquio"] and not got["video_azienda"]:
        got["video_azienda"] = youtube(f"{qn} company")
    video, vseen = [], set()
    for v in (got["video_colloquio"] or [])[:4] + (got["video_azienda"] or [])[:4]:
        if v["id"] not in vseen:
            vseen.add(v["id"])
            video.append(v)
    home = f"https://{domain}" if domain else _site((ddg.get("sito") or []) + web, company)
    readable = [r["u"] for r in web if not NO_FETCH.search(r["u"]) and not (home and urlparse(r["u"]).netloc in home)][:3]
    found_hiring = sum(1 for r in web if re.search(r"interview|colloqui|hiring|recruit|selezione|glassdoor|candidat|assessment", r["t"] + " " + r["s"], re.I))
    pf = [ex.submit(_pages_of_site, home)] if home else []
    af = [ex.submit(lambda u: {"u": u, "s": _text(_get(u, 7), 3000)}, u) for u in readable]
    aif = ex.submit(ai_search, company, title, groq_key, lang) if found_hiring < 4 else None
    wait(pf + af + ([aif] if aif else []), timeout=max(4, deadline - (time.time() - t0)) + (24 if aif else 0))
    pages = []
    for f in pf:
        if f.done() and not f.exception():
            pages += f.result()
    for f in af:
        if f.done() and not f.exception() and len(f.result()["s"]) > 300:
            pages.append(f.result())
    ai_text = aif.result() if aif and aif.done() and not aif.exception() else ""
    ex.shutdown(wait=False, cancel_futures=True)
    return {"web": web[:24] + (got["notizie"] or [])[:8], "video": video[:8], "pagine": pages[:6], "wiki": got["wiki"],
            "sito": home, "ai": ai_text, "secondi": round(time.time() - t0)}


def sources_text(g):
    parts = []
    if g.get("wiki"):
        parts.append(f"[WIKIPEDIA] {g['wiki']['t']} ({g['wiki']['u']})\n{g['wiki']['s']}")
    for p in g.get("pagine") or []:
        parts.append(f"[PAGINA] {p['u']}\n{p['s']}")
    for r in g.get("web") or []:
        parts.append(f"[RISULTATO {r['k']}] {r['t']} ({r['u']})\n{r['s']}")
    if g.get("ai"):
        parts.append("[RICERCA DI UN'AI CHE HA NAVIGATO IL WEB: usala, ma con prudenza]\n" + g["ai"])
    for i, v in enumerate(g.get("video") or []):
        parts.append(f"[VIDEO {i}] {v['t']} - canale {v['ch']} {v['len']}")
    return "\n\n".join(parts)[:18000]


# ---------- testi per l'AI ----------
def meeting_text(c):
    lang = LANGS.get(c.get("lang") or "", "")
    return ("COLLOQUIO\n"
            f"Tipo: {ROUNDS.get(c.get('round'), c.get('round') or 'primo colloquio')}\n"
            f"Modalità: {MODES.get(c.get('mode'), 'non indicata')}\n"
            f"Chi intervista: {c.get('with') or 'non indicato'}\n"
            f"Lingua del colloquio: {lang or 'non indicata: usa la lingua dell annuncio'}\n"
            + (f"Note della persona: {c['notes']}\n" if c.get("notes") else ""))


def research_brief(r):
    """La ricerca sull'azienda in poche righe, per il piano e per correggere le risposte."""
    if not r:
        return "RICERCA SULL'AZIENDA: non disponibile."
    a, s = r.get("azienda") or {}, r.get("selezione") or {}
    lines = ["RICERCA SULL'AZIENDA", a.get("chi_sono", ""), "Prodotti: " + "; ".join(a.get("prodotti") or []),
             "Clienti e mercato: " + (a.get("mercato") or ""), "Numeri: " + "; ".join(a.get("numeri") or []),
             "Notizie: " + "; ".join(n.get("t", "") for n in a.get("notizie") or []), "Cultura e valori: " + "; ".join(a.get("cultura") or []),
             "Concorrenti: " + "; ".join(a.get("concorrenti") or []), "Fasi della selezione: " + "; ".join(s.get("fasi") or []),
             "Cosa cercano: " + "; ".join(s.get("cosa_cercano") or []), "Domande riportate da chi ha fatto il colloquio: " + " | ".join(s.get("domande_riportate") or [])]
    return "\n".join(x for x in lines if x and not x.endswith(": "))


RESEARCH_SYSTEM = """Sei una ricercatrice che prepara una candidata a un colloquio di lavoro. Ricevi l'annuncio e i risultati di
una ricerca sul web sull'azienda (pagine del sito, risultati di ricerca con un estratto, Wikipedia, titoli di video).
Regole:
- Usa le fonti ricevute. Fatti, numeri, date, nomi e notizie SOLO se compaiono nelle fonti o nell'annuncio: mai inventarli,
  mai completarli a memoria. Se una cosa non risulta, lasciala vuota e mettila in "non_trovato".
- Per l'azienda puoi aggiungere conoscenze generali sicure e stabili (che cosa fa, settore), mai numeri a memoria.
- Le "domande_riportate" sono domande che chi ha fatto il colloquio in questa azienda riporta online (Glassdoor, Indeed, blog):
  copiale come sono scritte nelle fonti, nella loro lingua. Se nelle fonti non ce ne sono, lista vuota.
- Scrivi in italiano, frasi brevi e concrete. Le fonti si citano con l'indirizzo esatto ricevuto.
Rispondi SOLO con JSON:
{"azienda": {"chi_sono": "<3-5 frasi: cosa fa, per chi, dove, quanto è grande>",
  "prodotti": ["<prodotti o servizi principali>"], "mercato": "<clienti, mercati, posizione rispetto ai concorrenti>",
  "numeri": ["<numeri con il nome della testata o del sito tra parentesi, mai l'indirizzo: dipendenti, fatturato, finanziamenti, clienti, anno di fondazione>"],
  "notizie": [{"t": "<notizia recente in una frase, con la data se c'è>", "u": "<indirizzo esatto della fonte ricevuta>"}], "cultura": ["<valori e modo di lavorare, con le parole dell'azienda>"],
  "concorrenti": ["<concorrenti principali>"]},
 "selezione": {"fasi": ["<fasi del processo di selezione, se le fonti le descrivono>"], "cosa_cercano": ["<qualità e competenze che cercano>"],
  "domande_riportate": ["<domande vere riportate online>"], "consigli": ["<consigli specifici per il colloquio in questa azienda>"]},
 "video": [{"i": <numero del VIDEO>, "perche": "<perché guardarlo prima del colloquio>"}],
 "fonti": ["<indirizzi delle fonti più utili, massimo 8>"], "non_trovato": ["<cose utili che non hai trovato>"]}
In "video" scegli al massimo 4 video utili (sull'azienda, sul lavorare lì, sui suoi prodotti, sui colloqui): niente video di
altre aziende con lo stesso nome."""

PLAN_SYSTEM = """Sei una coach di carriera esperta di selezione del personale: prepari una persona a UN colloquio preciso.
Ricevi il profilo e il CV della persona, l'annuncio, la ricerca sull'azienda e i dati del colloquio.
Regole che non si possono violare:
- LINGUA: "pitch" e il campo "star" delle storie sono nella LINGUA DEL COLLOQUIO. TUTTI gli altri campi sono in ITALIANO,
  anche se l'annuncio e il colloquio sono in un'altra lingua: la persona legge la preparazione in italiano.
- Non inventare nulla sulla persona. Esperienze, episodi, progetti, clienti, numeri, risultati, strumenti: solo quelli scritti
  nel CV o nel profilo. Se il CV non racconta un episodio preciso, la storia NON si inventa: si scrive come traccia da
  completare, con segnaposto tra parentesi quadre al posto dei fatti che mancano, es. "Situation: [un cliente che ...]. Action:
  [cosa hai fatto tu] ...". Lo stesso per "prova" nei punti forti: cita il CV o indica quale episodio scegliere.
- Sull'azienda usa la ricerca ricevuta; niente numeri a memoria.
- Concreto e specifico per questa azienda e questo ruolo: niente consigli generici validi per qualunque colloquio.
Rispondi SOLO con JSON:
{"lingua": "<codice ISO della lingua del colloquio>",
 "in_breve": "<in italiano, 3-4 frasi: cosa aspettarsi da questo colloquio e su cosa giocarsi tutto>",
 "pitch": "<nella lingua del colloquio: risposta a 'parlami di te', 60-90 secondi parlati, solo fatti del CV: chi è, cosa ha fatto di rilevante, perché questo ruolo adesso>",
 "perche_azienda": ["<in italiano: 3-4 motivi veri e specifici per scegliere questa azienda, legati alla ricerca>"],
 "percorso": "<in italiano, 3-4 frasi: come questo ruolo si inserisce nel suo percorso, da dove viene e dove la porta>",
 "punti_forti": [{"punto": "<in italiano: cosa del profilo risponde a cosa chiedono>", "prova": "<in italiano: quale fatto del CV raccontare>"}],
 "punti_deboli": [{"rischio": "<in italiano: cosa può preoccupare chi seleziona>", "risposta": "<in italiano: come rispondere senza nascondere nulla>"}],
 "storie": [{"titolo": "<in italiano, nome breve>", "star": "<nella lingua del colloquio: Situazione, Compito, Azione, Risultato in 4-6 frasi, con segnaposto dove il CV non dà i fatti>", "per": "<in italiano: a quali domande risponde>"}],
 "domande_da_fare": ["<nella lingua del colloquio: 5 domande intelligenti da fare a chi intervista, specifiche per questa azienda e questo ruolo>"],
 "parole_chiave": ["<parole dell'annuncio e dell'azienda da usare nelle risposte, nella lingua del colloquio>"],
 "stipendio": "<in italiano: come rispondere se chiedono la retribuzione, con una cifra realistica per ruolo e paese>",
 "promemoria": ["<in italiano: 4-6 cose pratiche per il giorno del colloquio, adatte alla modalità>"]}
3-4 punti forti, 2-3 punti deboli, 3 storie."""

QUESTIONS_SYSTEM = """Sei una selezionatrice esperta (HR recruiter) e prepari la simulazione di UN colloquio preciso. Ricevi il profilo
e il CV della persona, l'annuncio, la ricerca sull'azienda e i dati del colloquio.
Prepara le domande che questa azienda farà davvero a questa persona per questo ruolo, nell'ordine di un colloquio vero:
apertura e presentazione, motivazione e perché questa azienda, esperienza e competenze per il ruolo, domande comportamentali
("raccontami di una volta in cui"), situazionali ("cosa faresti se"), una prova pratica tipica del ruolo (es. per un ruolo di
vendita: "vendimi il nostro prodotto" o una telefonata simulata), curiosità e personalità, domande scomode sui punti deboli
del profilo (anni di esperienza, cambi di lavoro, requisiti mancanti), disponibilità e retribuzione.
Regole:
- Le domande sono nella LINGUA DEL COLLOQUIO (se non indicata, quella dell'annuncio), formulate come le direbbe chi intervista.
- Usa le domande riportate online per questa azienda, se ci sono (copiandole quasi alla lettera).
- Calibra sul tipo di colloquio: un primo colloquio con le risorse umane è più su motivazione e profilo, uno con il
  responsabile più sul ruolo e sui casi pratici.
- "perche" e "traccia" in italiano: cosa vuole scoprire chi chiede e come impostare la risposta per questa persona,
  citando l'esperienza del CV da usare. Mai inventare esperienze.
Rispondi SOLO con JSON:
{"lingua": "<codice ISO>", "domande": [{"d": "<domanda>", "it": "<traduzione italiana se la domanda non è in italiano, altrimenti ''>",
  "tipo": "<presentazione|motivazione|azienda|ruolo|competenze|comportamentale|situazionale|pratica|curiosita|scomoda>",
  "perche": "<cosa vuole scoprire>", "traccia": "<come rispondere, 1-2 frasi>"}]}
Da 14 a 16 domande."""

EVAL_SYSTEM = """Sei una coach di colloqui di lavoro, esigente ma gentile. Ricevi la domanda del colloquio, cosa vuole scoprire chi la
fa, la risposta che la persona ha dato (scritta o dettata a voce, quindi può avere errori di trascrizione da ignorare), il suo
profilo e CV, l'annuncio e la ricerca sull'azienda.
Valuta la risposta come la valuterebbe chi seleziona in QUESTA azienda per QUESTO ruolo: contenuto, struttura, esempi
concreti, collegamento al ruolo e all'azienda, lunghezza adatta a un colloquio parlato, tono, lingua.
Regole:
- Sii specifica: cita le parole della persona quando dici cosa va e cosa no.
- La "risposta_migliore" è la sua risposta riscritta al meglio, nella LINGUA DELLA DOMANDA, parlabile in 45-90 secondi.
  Usa i fatti della sua risposta e del CV; NON inventare esperienze, numeri o risultati: dove servirebbe un dato che non hai,
  metti un segnaposto tra parentesi quadre, es. [numero di clienti].
- Se ha risposto in una lingua diversa da quella della domanda, segnalalo in "migliora".
- Se la risposta è vuota o di poche parole, voto basso e spiega cosa ci si aspettava.
- Tutto in italiano tranne "risposta_migliore" e "rilancio".
Rispondi SOLO con JSON:
{"voto": <1-10>, "giudizio": "<una frase: come suonerebbe a chi seleziona>", "bene": ["<cosa funziona>"], "migliora": ["<cosa cambiare, concreto>"],
 "risposta_migliore": "<risposta riscritta>", "rilancio": "<la domanda di approfondimento che chi seleziona farebbe dopo questa risposta>"}"""


def _s(v, n):
    return str(v or "").strip()[:n]


EMPTY = re.compile(r"^\W*(non[ _]trovat[oaie]|non disponibile|n\.?\s?d\.?|n/?a|none|null|unknown|nessun[oa]?)\W*$", re.I)


def _l(v, n, m=400):
    return [_s(x, m) for x in (v or []) if isinstance(x, (str, int, float)) and str(x).strip() and not EMPTY.match(str(x).strip())][:n]


def clean_research(d, g):
    a, s = d.get("azienda") or {}, d.get("selezione") or {}
    vids = g.get("video") or []
    picked = []
    for v in d.get("video") or []:
        try:
            i = int(v.get("i"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= i < len(vids) and vids[i]["id"] not in {p["id"] for p in picked}:
            picked.append(dict(vids[i], perche=_s(v.get("perche"), 200)))
    known = {r["u"] for r in g.get("web") or []} | {p["u"] for p in g.get("pagine") or []} | ({g["wiki"]["u"]} if g.get("wiki") else set())
    return {"azienda": {"chi_sono": _s(a.get("chi_sono"), 1200), "prodotti": _l(a.get("prodotti"), 8), "mercato": _s(a.get("mercato"), 600),
                        "numeri": _l(a.get("numeri"), 8), "cultura": _l(a.get("cultura"), 8), "concorrenti": _l(a.get("concorrenti"), 8, 80),
                        "notizie": [{"t": _s(n.get("t"), 300), "u": next((k for k in known if _s(n.get("u"), 400)[:70] and k.startswith(_s(n.get("u"), 400)[:70])), "")}
                                    for n in a.get("notizie") or [] if isinstance(n, dict) and n.get("t")][:6]},
            "selezione": {"fasi": _l(s.get("fasi"), 8), "cosa_cercano": _l(s.get("cosa_cercano"), 8),
                          "domande_riportate": _l(s.get("domande_riportate"), 12, 300), "consigli": _l(s.get("consigli"), 6)},
            "video": picked[:4] or vids[:3], "fonti": [u for u in _l(d.get("fonti"), 10, 400) if u in known],
            "non_trovato": _l(d.get("non_trovato"), 6), "sito": g.get("sito") or "",
            "trovati": {"risultati": len(g.get("web") or []), "pagine": len(g.get("pagine") or []), "video": len(vids)},
            "creato": time.strftime("%Y-%m-%d %H:%M")}


def clean_plan(d):
    pairs = lambda v, a, b, n: [{a: _s(x.get(a), 300), b: _s(x.get(b), 900)} for x in (v or []) if isinstance(x, dict) and x.get(a)][:n]
    return {"lingua": _s(d.get("lingua"), 5).lower(), "in_breve": _s(d.get("in_breve"), 900), "pitch": _s(d.get("pitch"), 2000),
            "perche_azienda": _l(d.get("perche_azienda"), 5, 500), "percorso": _s(d.get("percorso"), 900),
            "punti_forti": pairs(d.get("punti_forti"), "punto", "prova", 5), "punti_deboli": pairs(d.get("punti_deboli"), "rischio", "risposta", 4),
            "storie": [{"titolo": _s(x.get("titolo"), 120), "star": _s(x.get("star"), 1500), "per": _s(x.get("per"), 300)}
                       for x in d.get("storie") or [] if isinstance(x, dict) and x.get("star")][:4],
            "domande_da_fare": _l(d.get("domande_da_fare"), 6, 300), "parole_chiave": _l(d.get("parole_chiave"), 14, 60),
            "stipendio": _s(d.get("stipendio"), 700), "promemoria": _l(d.get("promemoria"), 7, 300), "creato": time.strftime("%Y-%m-%d %H:%M")}


def _overlap(a, b):
    wa, wb = set(re.findall(r"\w{4,}", a.lower())), set(re.findall(r"\w{4,}", b.lower()))
    return len(wa & wb) / max(1, min(len(wa), len(wb)))


def clean_questions(d, start=0, reported=()):
    out = []
    for i, q in enumerate(x for x in d.get("domande") or [] if isinstance(x, dict) and str(x.get("d") or "").strip()):
        t = _s(q.get("tipo"), 20).lower()
        out.append({"id": f"q{start + i + 1}", "d": _s(q.get("d"), 400), "it": _s(q.get("it"), 400), "tipo": t if t in TYPES else "ruolo",
                    "perche": _s(q.get("perche"), 400), "traccia": _s(q.get("traccia"), 500), "online": any(_overlap(str(q.get("d") or ""), r) >= 0.5 for r in reported), "prove": []})
    return out[:18]


def clean_eval(d, answer):
    try:
        voto = max(1, min(10, int(round(float(d.get("voto"))))))
    except (TypeError, ValueError):
        voto = 5
    return {"risposta": _s(answer, 4000), "voto": voto, "giudizio": _s(d.get("giudizio"), 400), "bene": _l(d.get("bene"), 5),
            "migliora": _l(d.get("migliora"), 5), "risposta_migliore": _s(d.get("risposta_migliore"), 2500),
            "rilancio": _s(d.get("rilancio"), 400), "t": time.strftime("%Y-%m-%d %H:%M")}
