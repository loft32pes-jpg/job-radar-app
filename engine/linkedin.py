"""LinkedIn: ricerca pubblica (senza login) su tutti i paesi europei, ultime 24 ore.

Come cerca:
- per ogni paese più ricerche "a gruppi" (parole unite da OR): technical sales, business development e vendita,
  change management e ruoli affini, più un gruppo nella lingua del paese;
- c'è un tempo massimo (config "max_minutes"), non un numero fisso di annunci: dopo la prima pagina di ogni ricerca
  si continua a sfogliare solo dove escono ancora annunci pertinenti, partendo dalle ricerche più ricche;
- poi legge gli annunci non ancora in archivio, dal più adatto al profilo, finché c'è tempo. Quelli non letti
  restano in elenco solo se il titolo è in italiano o inglese, segnalati come "da verificare".

Ritmo: tre richieste in parallelo, circa 1,7 al secondo in tutto (a 3 al secondo LinkedIn risponde 429). Al blocco fa una pausa, rallenta e riprova;
solo dopo quattro blocchi di fila smette e tiene quello che ha (la pagina lo segnala come risultato parziale).
"""
import html
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(__file__))
import rules  # noqa: E402
from sources import LI_SEARCH, Blocked, _li_cards, _li_criteria, _open, make, parse_dt, strip_html  # noqa: E402

Q_TECH = '"sales engineer" OR "presales" OR "pre-sales" OR "solutions engineer" OR "solutions consultant" OR "technical account manager" OR "technical sales"'
Q_SALES = '"business development" OR "account executive" OR "account manager" OR "sales development" OR "partnerships" OR "key account" OR "inside sales"'
Q_OTHER = '"change management" OR "customer success" OR "business transformation" OR "sales operations" OR "go-to-market"'
Q_NATIVE = {
    "it": '"tecnico commerciale" OR "sviluppo commerciale" OR "commerciale" OR "prevendita" OR "business developer"',
    "es": '"desarrollo de negocio" OR "ingeniero de ventas" OR "preventa" OR "ejecutivo de cuentas" OR "comercial" OR "técnico comercial"',
    "fr": '"ingénieur commercial" OR "ingénieur d\'affaires" OR "avant-vente" OR "développement commercial" OR "technico-commercial"',
    "de": '"Vertriebsingenieur" OR "Vertrieb" OR "Presales" OR "Geschäftsentwicklung" OR "Key Account"',
    "pt": '"desenvolvimento de negócio" OR "gestor de contas" OR "comercial" OR "pré-venda"',
    "nl": '"accountmanager" OR "business developer" OR "commercieel" OR "sales engineer"',
}
# (nome per LinkedIn, lingua del gruppo locale, paese grande?)
COUNTRIES = [
    ("Italy", "it", True), ("Spain", "es", True), ("France", "fr", True), ("Germany", "de", True),
    ("United Kingdom", None, True), ("Ireland", None, True), ("Netherlands", "nl", True), ("Belgium", "fr", True),
    ("Switzerland", "de", True), ("Portugal", "pt", True), ("Austria", "de", False), ("Luxembourg", "fr", False),
    ("Sweden", None, True), ("Denmark", None, False), ("Norway", None, False), ("Finland", None, False),
    ("Poland", None, True), ("Czechia", None, False), ("Hungary", None, False), ("Romania", None, False),
    ("Greece", None, False), ("Estonia", None, False), ("Latvia", None, False), ("Lithuania", None, False),
    ("Croatia", None, False), ("Slovenia", None, False), ("Slovakia", None, False), ("Bulgaria", None, False),
    ("Malta", None, False), ("Cyprus", None, False),
]
IT_NAME = {"Italia": "Italy", "Spagna": "Spain", "Francia": "France", "Germania": "Germany", "Regno Unito": "United Kingdom",
           "Irlanda": "Ireland", "Paesi Bassi": "Netherlands", "Belgio": "Belgium", "Svizzera": "Switzerland", "Portogallo": "Portugal",
           "Lussemburgo": "Luxembourg", "Svezia": "Sweden", "Danimarca": "Denmark", "Norvegia": "Norway", "Finlandia": "Finland",
           "Polonia": "Poland", "Repubblica Ceca": "Czechia", "Ungheria": "Hungary", "Grecia": "Greece", "Lettonia": "Latvia",
           "Lituania": "Lithuania", "Croazia": "Croatia", "Slovacchia": "Slovakia", "Cipro": "Cyprus"}
LI_NAME_FIX = {"Czechia": "Czech Republic"}  # nome riconosciuto da rules.infer_country


class Pacer:
    """Ritmo delle richieste condiviso tra più lavoratori in parallelo; gestisce i blocchi 429 con pause comuni."""

    def __init__(self, gap=0.6, max_streak=4, log=None):
        self.gap, self.max_streak, self.streak, self.blocks, self.count = gap, max_streak, 0, 0, 0
        self.next_slot, self.hold_until = 0.0, 0.0
        self.base, self.clean = gap, 0
        self.lock = threading.Lock()
        self.log = log or (lambda m: None)

    @property
    def dead(self):
        # conta solo i blocchi di fila: qualche "rallenta" è normale e non deve fermare tutto
        return self.streak >= self.max_streak

    def get(self, url, timeout=25):
        """Ritorna il testo della pagina, oppure None se LinkedIn non collabora."""
        for _ in range(3):
            if self.dead:
                return None
            with self.lock:  # ogni richiesta prenota il suo istante di partenza: il ritmo complessivo resta quello voluto
                now = time.time()
                slot = max(now, self.next_slot, self.hold_until)
                self.next_slot = slot + self.gap
                self.count += 1
            if slot > now:
                time.sleep(slot - now)
            try:
                page = _open(url, "text/html", timeout=timeout)
                self.streak = 0
                self.clean += 1
                if self.clean >= 80 and self.gap > self.base:  # 80 risposte buone di fila: si torna piano piano al ritmo normale
                    self.gap, self.clean = max(self.base, self.gap * 0.9), 0
                return page
            except Blocked:
                with self.lock:
                    if time.time() < self.hold_until:
                        continue  # un altro lavoratore ha già avviato la pausa
                    self.streak += 1
                    self.blocks += 1
                    self.clean = 0
                    if self.dead:
                        self.log("  LinkedIn: blocco prolungato, mi fermo e tengo quanto raccolto")
                        return None
                    pause = 20 * self.streak
                    self.gap = min(1.5, self.gap * 1.25)  # dopo un blocco si va più piano
                    self.hold_until = time.time() + pause
                    self.log(f"  LinkedIn chiede di rallentare: pausa di {pause} secondi")
            except Exception:
                return None
        return None


def _priority(title: str) -> int:
    """Più alto = letto prima: ruoli più vicini al profilo, livello junior, niente senior."""
    cls = rules.classify(title)
    if not cls:
        return -1
    p = cls[1]
    if re.search(r"\b(junior|graduate|associate|entry)\b", title, re.I):
        p += 8
    if re.search(r"\b(senior|sr|lead|staff|expert|enterprise|strategic)\b", title, re.I):
        p -= 15
    return p


LOCAL_MILES = 25  # raggio della ricerca per città (LinkedIn ragiona in miglia: circa 40 km)


def fetch_linkedin(cfg, since, log=None, known_ids=(), on_read=None, local_since=None, cached=None):
    """known_ids: annunci LinkedIn già in archivio (non serve rileggerli, basta sapere che sono ancora nella finestra)."""
    log = log or (lambda m: None)
    if not cfg.get("enabled", True):
        return [], {"name": "LinkedIn", "ok": False, "reason": "disattivato in config.json"}
    # Tempo massimo per LinkedIn: la ricerca intera deve stare in 10-15 minuti. Dentro questo tempo
    # non c'è un numero fisso di annunci: si sfoglia e si legge il più possibile, partendo dai più adatti.
    budget = float(cfg.get("max_minutes", 12)) * 60
    t0 = time.time()
    search_until = t0 + budget * float(cfg.get("search_share", 0.28))
    max_search = int(cfg.get("max_requests", 0))   # 0 = nessun tetto di numero, vale solo il tempo
    max_details = int(cfg.get("max_details", 0))
    seconds = max(3600, int((datetime.now(timezone.utc) - since).total_seconds()))
    pacer = Pacer(gap=float(cfg.get("gap_seconds", 0.8)), log=log)
    pool = ThreadPoolExecutor(max_workers=int(cfg.get("workers", 3)))
    known_ids = set(known_ids)

    def can_search():
        return not pacer.dead and time.time() < search_until and (not max_search or pacer.count < max_search)

    # 1) ricerca: prima pagina di ogni gruppo in ogni paese (nessun paese resta fuori), poi si continua a sfogliare
    #    solo le ricerche che stanno ancora dando annunci pertinenti, partendo da quelle che ne danno di più
    found = {}       # id annuncio -> dati della card
    per_country = {}
    active = []
    plan = rules.SEARCH  # con un profilo utente le ricerche vengono dai suoi gruppi di ruoli
    groups = plan["groups"] if plan else [Q_SALES, Q_TECH, Q_OTHER]
    native = plan["native"] if plan else Q_NATIVE
    wanted = {IT_NAME.get(n, n) for n in plan["countries"]} if plan and plan.get("countries") else None
    # vicino casa (città scelte dalla persona): tutte le ricerche, annunci dell'ultima settimana, raggio di circa 40 km
    local_secs = max(seconds, int((datetime.now(timezone.utc) - local_since).total_seconds())) if local_since else seconds
    lang_of = {n: lg for n, lg, _b in COUNTRIES}
    # un titolo per ricerca: le ricerche "a gruppi" (titoli uniti da OR) restituiscono solo una parte degli annunci
    # (prova su Torino, 7 giorni: 21 annunci con i gruppi, 145 cercando titolo per titolo). La prima città è la principale.
    en_titles = {t.lower() for c in (rules.PROFILE or {}).get("clusters", []) if c.get("on", True) for t in c.get("titles_en", [])}
    for n_place, p in enumerate((plan or {}).get("places") or []):
        cname = next((n for n in lang_of if n == p.get("country_en")), None) or p.get("country_en") or ""
        lang = lang_of.get(cname)
        terms = [t for t in plan.get("local") or [] if lang == "it" or t.lower() in en_titles]
        terms = terms[:40 if n_place == 0 else 16] or [plan["core"]] + plan["big"]
        for q in terms:
            active.append((cname, q, set(), {"location": f"{p['name']}, {cname}".strip(", "), "distance": LOCAL_MILES,
                                             "secs": local_secs, "near": p["name"]}))
    for name, lang, big in COUNTRIES:
        if wanted and name not in wanted:
            continue
        if plan and plan.get("core"):  # ricerca larga ovunque, quelle di dettaglio solo dove il mercato è grande
            qs = [plan["core"]] + (plan["big"] if big or (wanted and len(wanted) <= 6) else [])
        else:
            qs = groups
        for q in qs + ([native[lang]] if lang in native else []):
            active.append((name, q, set(), {}))
    start, cut = 0, False
    while active and start < 1000:  # LinkedIn non va oltre i 1000 risultati per ricerca
        if start and not can_search():  # la prima pagina si fa sempre per tutti
            break

        def search(item, start=start):
            name, q, _seen, loc = item
            if pacer.dead or (start and time.time() > search_until):
                return None
            args = {"keywords": q, "location": loc.get("location") or name, "f_TPR": f"r{loc.get('secs') or seconds}", "start": start}
            if loc.get("distance"):
                args["distance"] = loc["distance"]
            return pacer.get(f"{LI_SEARCH}?{urlencode(args)}")

        nxt = []
        for (name, q, seen, loc), page in zip(active, pool.map(search, active)):
            if page is None:
                continue
            cards = list(_li_cards(page))
            fresh = {c[0] for c in cards} - seen
            seen |= fresh
            good = _collect(cards, name, found, per_country, loc.get("near"))
            # si sfoglia finché escono annunci dei ruoli della persona. Nelle sue città ogni ricerca va fino in fondo: le ricerche
            # si sovrappongono ("Account Manager" e "Key Account Manager"), contare solo gli annunci mai visti la fermerebbe presto
            mine = sum(1 for c in cards if c[0] in fresh and _priority(c[1]) >= 0)
            if len(cards) >= 7 and fresh and (good or (loc.get("near") and mine)):
                nxt.append((good + (1000 if loc.get("near") else 0), name, q, seen, loc))
        if cut or pacer.dead:
            break
        nxt.sort(key=lambda x: -x[0])
        active, start = [x[1:] for x in nxt], start + 10
    n_search = pacer.count
    log(f"  LinkedIn: {len(found)} annunci pertinenti in {len([c for c in per_country.values() if c])} paesi ({n_search} ricerche)")

    # 2) lettura degli annunci nuovi, fino allo scadere del tempo: prima i più adatti al profilo,
    #    alternando i paesi (il migliore di ogni paese passa davanti al decimo di un paese grande)
    rank = {}
    near_rank = {p["name"]: 160 - 30 * n for n, p in enumerate((plan or {}).get("places") or [])}
    for c, ids in per_country.items():
        for r, i in enumerate(sorted((i for i in ids if i not in known_ids), key=lambda i: -found[i]["prio"])):
            # i titoli in una lingua che non è italiano o inglese si leggono per ultimi: di rado restano in elenco
            rank[i] = found[i]["prio"] - 1.5 * r - (40 if rules.probably_other_language(found[i]["title"], "") else 0) \
                + (near_rank.get(found[i].get("near"), 0) if found[i].get("near") else 0)  # prima la città principale
    order = sorted(rank, key=lambda i: -rank[i])
    log(f"  LinkedIn: {len(order)} annunci nuovi da leggere, dal più adatto ({len(found) - len(order)} già in archivio)")
    deadline = t0 + budget
    if max_details:
        order = order[:max_details]
    # testi già letti in ricerche passate (anche con un profilo diverso): non si rileggono, il tempo va agli annunci nuovi
    cached = cached or {}
    for jid in [i for i in order if i in cached]:
        found[jid]["text"] = cached[jid]
        if on_read:
            try:
                on_read(_job(jid, found[jid]))
            except Exception:
                pass
    if cached:
        before = len(order)
        order = [i for i in order if i not in cached]
        log(f"  LinkedIn: {before - len(order)} testi già letti in passato, ne restano {len(order)} da leggere")

    def detail(jid):
        if pacer.dead or time.time() > deadline:
            return None
        # endpoint pubblico "leggero" dell'annuncio: stessa descrizione e stessi dati, un sesto del peso
        return pacer.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}")

    read = 0
    for jid, page in zip(order, pool.map(detail, order)):
        if page is None:
            continue
        read += 1
        m = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page, re.S)
        found[jid]["text"] = strip_html(m.group(1)) if m else ""
        found[jid]["criteria"] = _li_criteria(page)
        if on_read:  # chi ascolta (il giudice AI) riceve l'annuncio appena letto, senza aspettare la fine
            try:
                on_read(_job(jid, found[jid]))
            except Exception:
                pass
        if read % 100 == 0:
            log(f"  LinkedIn: letti {read} annunci su {len(order)}")
    pool.shutdown(wait=False)
    log(f"  LinkedIn: letti {read} annunci su {len(order)} in {round((time.time() - t0) / 60)} minuti")

    jobs = [_job(jid, f) for jid, f in found.items()]
    reason = ""
    if pacer.dead:  # risultato parziale: va detto, perché la finestra delle 24 ore non è completa
        reason = f"interrotta da LinkedIn dopo {len(jobs)} annunci: risultato parziale, riprova più tardi" if jobs else "bloccato da LinkedIn (riprova più tardi)"
    return jobs, {"name": "LinkedIn (ricerca pubblica)", "ok": not pacer.dead, "reason": reason}


def _job(jid, f):
    # la card ha solo la data (senza ora): la finestra 24h è garantita dal filtro f_TPR della ricerca
    j = make(f["title"], f["company"], f["location"], f"https://www.linkedin.com/jobs/view/{jid}", "LinkedIn",
             parse_dt(f["date"]), f.get("text", ""))
    j["logo"], j["criteria"] = f["logo"], f.get("criteria", {})
    if f.get("near"):
        j["near"] = f["near"]
    return j


def _collect(cards, country, found, per_country, near=None):
    """Aggiunge le card pertinenti non ancora viste. Ritorna quante ne ha aggiunte."""
    cname = LI_NAME_FIX.get(country, country)
    added = 0
    for jid, title, company, location, d, logo in cards:
        if jid in found:
            if near and not found[jid].get("near"):
                found[jid]["near"] = near  # già trovato con la ricerca per paese: si segna che è anche vicino casa
            continue
        prio = _priority(title)
        if prio < 0:
            continue
        # LinkedIn scrive spesso solo la città o l'area ("Greater Bilbao Metropolitan Area"): il paese è quello cercato
        loc = location if rules.infer_country(location) else f"{location}, {cname}".strip(", ")
        found[jid] = {"title": title, "company": company, "location": loc, "date": d, "logo": logo, "prio": prio}
        if near:
            found[jid]["near"] = near
        per_country.setdefault(country, []).append(jid)
        added += 1
    return added
