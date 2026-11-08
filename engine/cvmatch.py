"""Valutazione del CV rispetto a un annuncio (0-100), in stile software di selezione.

COSA FA
- legge il CV (PDF, DOCX o testo) e ne ricava un profilo: anni di esperienza, studi, lingue, skill, ruoli svolti;
- per ogni annuncio confronta CV e testo dell'annuncio su 7 criteri pesati, gli stessi su cui lavorano i sistemi di
  selezione (ATS) e i selezionatori: parole chiave, ruolo, esperienza, studi, lingue, settore, qualità del CV;
- controlla la "leggibilità ATS" del CV (sezioni riconoscibili, date, contatti, risultati numerici).

COSA NON È
Non è il software dell'azienda: nessun ATS pubblica la propria formula e molti (Greenhouse, Lever, Personio) non
assegnano un punteggio automatico. È una simulazione trasparente del confronto per parole chiave e requisiti,
il meccanismo comune a questi strumenti. Ogni punto è spiegato.
"""
import os
import re
import sys
import unicodedata
import zipfile
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import details  # noqa: E402
import rules  # noqa: E402

WEIGHTS = [("keywords", "Parole chiave e skill", 30), ("role", "Coerenza del ruolo", 20), ("experience", "Esperienza", 15),
           ("education", "Studi", 10), ("languages", "Lingue", 10), ("sector", "Settore", 10), ("quality", "Qualità del CV", 5)]

# concetti che i selezionatori cercano nei ruoli commerciali/tecnico-commerciali (oltre alle skill di details.SKILLS)
CONCEPTS = [
    ("Ciclo di vendita completo", r"sales cycles?|end[- ]to[- ]end sales|full[- ]cycle|ciclo di vendita|ciclo de venta"),
    ("Acquisizione nuovi clienti", r"new (business|clients?|customers?|logos?)|customer acquisition|nuovi clienti|acquisi\w+ (di )?client"),
    ("Analisi di mercato", r"market (analysis|research|mapping)|analisi di mercato|an[áa]lisis de mercado"),
    ("Gestione clienti / relazioni", r"relationships?|relations\b|client management|gestione (dei |delle )?(clienti|relazioni)"),
    ("Lead qualificati", r"qualified leads?|lead qualification|lead gen"),
    ("Fiere ed eventi", r"trade (shows?|fairs?)|\bevents?\b|fiere|conferences?"),
    ("Quota e target", r"\bquota\b|targets?\b|\bkpis?\b|obiettivi di vendita"),
    ("Upsell / cross-sell", r"up[- ]?sell|cross[- ]?sell|expansion"),
    ("Discovery e qualifica", r"discovery|qualif(y|ication)|needs analysis|analisi dei bisogni"),
    ("Proposte e offerte", r"proposals?|quotations?|offerte commerciali|preventiv"),
    ("NDA / DPA / contratti", r"\bnda\b|\bdpa\b|contracts?|contratti|commercial agreement"),
    ("Lavoro cross-funzionale", r"cross[- ]functional|product (team|management)|engineering team|interfunzional"),
    ("Clienti enterprise", r"enterprise (clients?|customers?|accounts?)|large accounts?|grandi clienti"),
    ("PMI / mid-market", r"\bsmbs?\b|\bsmes?\b|mid[- ]market|\bpmi\b"),
    ("Mercato internazionale", r"international|global|emea|europe\w*|internazional"),
    ("Presentazioni", r"presentations?|pitch|presentazioni"),
    ("Localizzazione prodotto", r"locali[sz]ation|product feedback|feedback di mercato|market feedback"),
    ("OEM e partner industriali", r"\boems?\b|suppliers?|fornitor"),
]
ALL_TERMS = details.SKILLS + CONCEPTS

ATS_NOTES = {
    "Greenhouse": "Questa azienda usa Greenhouse. Di norma non assegna un punteggio automatico al CV: i selezionatori leggono le candidature e cercano per parole chiave. Conta che le parole dell'annuncio siano nel CV e che le eventuali domande di candidatura abbiano risposte complete.",
    "Lever": "Questa azienda usa Lever. Il CV viene letto e reso ricercabile, senza punteggio automatico: i selezionatori filtrano per parole chiave e tag. Un PDF con testo selezionabile e titoli di sezione standard viene letto meglio.",
    "Ashby": "Questa azienda usa Ashby. Può affiancare al selezionatore una valutazione assistita dall'AI rispetto ai criteri dell'annuncio (se l'azienda la attiva): servono requisiti dichiarati in modo esplicito nel CV, non impliciti.",
    "Workable": "Questa azienda usa Workable, che può mostrare al selezionatore un indice di corrispondenza tra CV e annuncio. Le parole chiave dell'annuncio presenti nel CV pesano molto.",
    "SmartRecruiters": "Questa azienda usa SmartRecruiters, che ha una funzione di punteggio di corrispondenza (SmartAssistant) basata su skill, esperienza e studi. Titoli di ruolo e skill scritti come nell'annuncio aiutano.",
    "Personio": "Questa azienda usa Personio: gestione delle candidature senza punteggio automatico. Decide il selezionatore leggendo il CV.",
    "Recruitee": "Questa azienda usa Recruitee: candidature gestite a mano dal team, con ricerca per parole chiave.",
    "LinkedIn": "Candidatura da LinkedIn: il selezionatore vede un riepilogo di corrispondenza basato su skill e titoli del profilo LinkedIn, oltre al CV. Conviene allineare le skill del profilo a quelle dell'annuncio.",
}
ATS_DEFAULT = "Sistema di selezione dell'azienda non noto. Vale la regola generale: CV in PDF con testo selezionabile, sezioni con titoli standard, parole dell'annuncio riportate dove sono vere."

MONTHS = {m: i for i, names in enumerate([
    ("jan", "gen"), ("feb",), ("mar",), ("apr",), ("may", "mag"), ("jun", "giu"), ("jul", "lug"), ("aug", "ago"),
    ("sep", "set"), ("oct", "ott"), ("nov",), ("dec", "dic")], start=1) for m in names}
SECTION_RX = {
    "experience": r"work experience|professional experience|experience|esperienz\w+ (lavorativ\w+|professional\w+)|esperienze?|employment",
    "education": r"education|formazione|istruzione|studi|academic",
    "skills": r"(computer |technical |hard |soft )?skills|competenze|capacit[àa]",
    "languages": r"languages?|lingue",
    "projects": r"(university )?projects?|progetti",
}
# parole che bastano a riconoscere un titolo composto (in ordine: "competenze linguistiche" è Lingue, non Competenze)
SECTION_HINTS = [
    ("languages", r"\blingu\w+|\blanguages?\b"),
    ("projects", r"\bprogett\w+|\bprojects?\b"),
    ("experience", r"\besperienz\w+|\bexperiences?\b|\bemployment\b|\bcarriera\b|\bcareer\b"),
    ("education", r"\bformazione\b|\bistruzione\b|\beducation\b|\bstudi\b"),
    ("skills", r"\bcompetenze\b|\bskills?\b|\bcapacit[àa]\b|\bconoscenze\b"),
]
EDU_NEAR = re.compile(r"laurea|universit|politecnico|university|degree|master|bachelor|liceo|diploma|scuola|school|erasmus", re.I)


# ---------------------------------------------------------------- lettura del file

def extract_text(path: str) -> str:
    """Testo del CV da PDF (pypdf), DOCX (zip + XML) o file di testo."""
    low = path.lower()
    if low.endswith(".pdf"):
        try:  # PyMuPDF legge meglio i PDF di Canva e quelli tradotti; pypdf resta come riserva
            import pymupdf
            with pymupdf.open(path) as doc:
                text = "\n".join(page.get_text() for page in doc)
                for a, b in ((" ", " "), ("­", "-"), ("‐", "-"), ("‑", "-")):
                    text = text.replace(a, b)  # spazi e trattini "speciali" che alcuni PDF usano al posto di quelli normali
                return text
        except ImportError:
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    if low.endswith(".docx"):
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", "", xml))
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


# ---------------------------------------------------------------- profilo dal CV

def _sections(text: str) -> dict:
    """Divide il CV nelle sezioni riconosciute dai titoli."""
    marks = []
    for m in re.finditer(r"(?m)^\s*([A-Za-zÀ-ÿ ]{3,40})\s*:?\s*$", text):
        raw = m.group(1).strip()
        head = raw.lower()
        name = next((n for n, rx in SECTION_RX.items() if re.fullmatch(rx, head)), None)
        if not name and len(head.split()) <= 6 and (raw.isupper() or len(head.split()) <= 3):
            # titoli composti, tipici dei CV grafici: "COMPETENZE LINGUISTICHE", "ESPERIENZE PROFESSIONALI", "COMPETENZE TECNICHE E SOFT SKILLS"
            name = next((n for n, rx in SECTION_HINTS if re.search(rx, head)), None)
        if name:
            marks.append((m.start(), m.end(), name))
    out = {}
    for i, (s, e, name) in enumerate(marks):
        out[name] = out.get(name, "") + text[e: marks[i + 1][0] if i + 1 < len(marks) else len(text)]
    return out


def _months_of_experience(exp_text: str):
    """Somma i periodi 'April 2025 - Present' / '10/2022 - 07/2025' trovati nella sezione esperienza."""
    today = date.today()
    rng = re.compile(
        r"(?:(?P<m1>[A-Za-zà-ÿ]{3,9})\.?\s+|(?P<n1>\d{1,2})/)?(?P<y1>(?:19|20)\d{2})\s*[-–—]\s*"
        r"(?:(?P<pres>present|current|ongoing|today|oggi|presente|attuale|now|ad oggi|in corso)|(?:(?P<m2>[A-Za-zà-ÿ]{3,9})\.?\s+|(?P<n2>\d{1,2})/)?(?P<y2>(?:19|20)\d{2}))", re.I)

    def month(name, num, default):
        if num:
            return min(12, max(1, int(num)))
        return MONTHS.get(_norm(name or "").lower()[:3], default)

    total, ranges = 0, []
    for m in rng.finditer(exp_text):
        y1, m1 = int(m.group("y1")), month(m.group("m1"), m.group("n1"), 1)
        if m.group("pres"):
            y2, m2 = today.year, today.month
        else:
            y2, m2 = int(m.group("y2")), month(m.group("m2"), m.group("n2"), 12)
        months = (y2 - y1) * 12 + (m2 - m1) + 1
        if 0 < months < 600:
            total += months
            ranges.append(m.group(0))
    return total, ranges


def analyze_cv(text: str) -> dict:
    text = text.replace("\r", "")
    low = text.lower()
    sec = _sections(text)
    exp_text = sec.get("experience", "")
    months, ranges = _months_of_experience(exp_text or text)
    if not months and exp_text:
        # CV a colonne (Canva): le date finiscono lontano dalle descrizioni. Si cercano in tutto il testo,
        # saltando i periodi di studio (riconosciuti dalle righe vicine: laurea, università, politecnico...)
        lines = text.split("\n")
        keep = [ln for i, ln in enumerate(lines) if not EDU_NEAR.search(" ".join(lines[max(0, i - 2): i + 2]))]
        months, ranges = _months_of_experience("\n".join(keep))
    edu_text = sec.get("education", text)
    level = 2 if re.search(r"master|magistrale|msc|specialistica", edu_text, re.I) else 1 if re.search(r"bachelor|triennale|\blaurea\b|degree", edu_text, re.I) else 0
    fields = [lab for lab, rx in details.FIELDS if re.search(rx, edu_text, re.I)]
    if re.search(r"engineering and management|ingegneria gestionale|management engineering", text, re.I) and "gestionale" not in fields:
        fields.append("gestionale")
    langs = {}
    lang_text = sec.get("languages", "")  # solo la sezione Lingue: altrove "German HQ" non è una lingua parlata
    for name, rx in (("inglese", r"english|inglese"), ("italiano", r"italian[oa]?\b"), ("spagnolo", r"spanish|spagnolo|español"),
                     ("francese", r"french|francese"), ("tedesco", r"german|tedesco")):
        m = re.search(rf"(?:{rx})\W{{0,4}}(?P<lvl>a1|a2|b1|b2|c1|c2|native|madrelingua|mother tongue|fluent|fluente|"
                      rf"ottim\w+|excellent|advanced|avanzat\w+|professional\w*|buon\w+|good|intermedi\w+|discret\w+|scolastic\w+|basic|base)?", lang_text, re.I)
        if m:
            lvl = (m.group("lvl") or "dichiarata").upper()
            # livelli scritti a parole ("buona capacità"): si riportano come sono, senza inventare un livello europeo
            word = next((lab for lab, rx2 in (("fluente", r"FLUEN|OTTIM|EXCELLENT|ADVANCED|AVANZAT|PROFESSIONAL"), ("buono", r"BUON|GOOD"),
                                              ("intermedio", r"INTERMEDI|DISCRET"), ("base", r"SCOLASTIC|BASIC|BASE")) if re.match(rx2, lvl)), None)
            langs[name] = "madrelingua" if lvl in ("NATIVE", "MADRELINGUA", "MOTHER TONGUE") else word or lvl
    skills = [lab for lab, rx in details.SKILLS if re.search(rx, text, re.I)]
    concepts = [lab for lab, rx in CONCEPTS if re.search(rx, text, re.I)]
    families = [fam for fam, _, rx in rules.FAMILIES if re.search(rx, exp_text or text, re.I)]
    bullets = len(re.findall(r"(?m)^\s*[•\-–\*·▪●]\s+\S", text))
    quantified = len(re.findall(r"\b\d+(?:[.,]\d+)?\s?(?:%|k\b|m\b|€|\$|clients?|clienti|customers?|leads?|accounts?|deals?|people|persone)|"
                                r"\b(?:first|primi|prime)\s+\d+", low))
    words = len(re.findall(r"\w+", text))
    odd_caps = sorted(set(re.findall(r"\b[A-Z]{2}[a-z]{3,}\b", text)))[:6]            # es. "STrategy"
    typos = sorted({w for w in re.findall(r"\b[\w-]+\b", low) if w in {"funcional", "cross-funcional", "enigineer", "managment", "recieve", "responsability", "adress"}})
    return {
        "words": words, "months": months, "years": round(months / 12, 1), "ranges": ranges[:8],
        "education_level": level, "education_fields": fields, "languages": langs, "skills": skills, "concepts": concepts,
        "families": families, "sections": sorted(sec.keys()), "bullets": bullets, "quantified": quantified,
        "has_email": bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)), "has_phone": bool(re.search(r"\+?\d[\d\s().-]{7,}\d", text)),
        "has_linkedin": "linkedin.com" in low, "mobility_background": bool(rules.MOBILITY_STRONG.search(text)),
        "software_background": bool(re.search(r"software|saas|connected services|servizi connessi|platform|piattaforma", text, re.I)),
        "odd_caps": odd_caps, "typos": typos,
    }


def ats_readiness(p: dict) -> dict:
    """Quanto bene un sistema di selezione riesce a leggere il CV (0-100) e cosa sistemare."""
    checks = []

    def add(ok, label, fix=""):
        checks.append({"ok": bool(ok), "t": label, "fix": "" if ok else fix})

    add(p["words"] >= 150, "Testo leggibile dal sistema", "Il CV sembra un'immagine o ha pochissimo testo: esportalo da Canva come 'PDF standard' con testo selezionabile, non come immagine.")
    for key, lab in (("experience", "Esperienza"), ("education", "Formazione"), ("skills", "Competenze"), ("languages", "Lingue")):
        add(key in p["sections"], f"Sezione '{lab}' riconoscibile", f"Usa un titolo di sezione standard per '{lab}' su una riga a sé: i sistemi cercano proprio quei titoli.")
    add(p["months"] > 0, "Date delle esperienze leggibili", "Scrivi le date nel formato 'Mese Anno - Mese Anno' accanto a ogni esperienza.")
    add(p["has_email"] and p["has_phone"], "Contatti presenti (email e telefono)", "Aggiungi email e telefono come testo, non dentro un'immagine o un'icona.")
    add(p["bullets"] >= 5, "Esperienze descritte per punti", "Descrivi ogni esperienza con 3-6 punti elenco che iniziano con un verbo d'azione.")
    add(p["quantified"] >= 3, "Risultati con numeri", "Aggiungi numeri ai risultati (clienti acquisiti, valore dei contratti, lead generati, percentuali): oggi ce ne sono pochi.")
    add(300 <= p["words"] <= 900, "Lunghezza adeguata (1-2 pagine)", "Punta a 350-800 parole: sotto è troppo scarno per le parole chiave, sopra viene letto a metà.")
    add(not p["typos"] and not p["odd_caps"], "Nessun refuso evidente",
        "Possibili refusi: " + ", ".join(p["typos"] + p["odd_caps"]) + ". Un refuso su una parola chiave la rende introvabile per il sistema.")
    add(p["has_linkedin"], "Link al profilo LinkedIn", "Aggiungi il link al profilo LinkedIn: molti selezionatori lo aprono subito.")
    score = round(100 * sum(c["ok"] for c in checks) / len(checks))
    return {"score": score, "checks": checks}


# ---------------------------------------------------------------- confronto CV / annuncio

def _english_level_needed(text: str):
    m = re.search(r"(fluent|fluency|native|proficien\w+|excellent|c1|c2|advanced|business[- ]level|professional)\W+(\w+\W+){0,4}english|"
                  r"english\W+(\w+\W+){0,4}(fluent|fluency|native|proficien\w+|excellent|c1|c2|advanced)|"
                  r"inglese\W+(\w+\W+){0,3}(fluente|ottimo|c1|c2|avanzato)|(ottim\w+|fluente)\W+(\w+\W+){0,3}inglese", text, re.I)
    return "alto" if m else ("citato" if rules.ENGLISH_MENTION.search(text) else "")


def match(profile: dict, cv_text: str, job: dict, job_text: str) -> dict:
    """Punteggio 0-100 del CV per questo annuncio, con dettaglio per criterio."""
    jt = f"{job.get('title', '')}. {job_text or ''}"
    has_text = len(job_text or "") > 200
    parts, tips = {}, []

    # 1) parole chiave e skill dell'annuncio ritrovate nel CV
    wanted = [(lab, rx) for lab, rx in ALL_TERMS if re.search(rx, jt, re.I)]
    matched = [lab for lab, rx in wanted if re.search(rx, cv_text, re.I)]
    missing = [lab for lab, rx in wanted if lab not in matched]
    if not has_text or not wanted:
        parts["keywords"] = (15, "Testo dell'annuncio non disponibile o senza requisiti riconoscibili: valore neutro.")
    else:
        rate = len(matched) / len(wanted)
        weight = min(1.0, len(wanted) / 5)  # con pochissime parole chiave il dato è poco affidabile: pesa meno
        parts["keywords"] = (round(15 + (30 * rate - 15) * weight),
                             f"{len(matched)} su {len(wanted)} parole chiave dell'annuncio sono nel CV ({round(100 * rate)}%).")
        if missing:
            tips.append("Parole chiave dell'annuncio assenti dal CV: " + ", ".join(missing[:6]) + ". Aggiungile solo se corrispondono a cose che hai fatto davvero.")

    # 2) ruolo
    fam = job.get("role_family")
    near = {"tech_sales": {"bd", "sales"}, "bd": {"tech_sales", "sales"}, "sales": {"bd", "tech_sales"}, "change": {"affini"}, "affini": {"sales", "bd"}}
    if fam in profile["families"]:
        parts["role"] = (20, f"Il CV riporta già un ruolo {rules.FAMILY_LABEL.get(fam, fam)}.")
    elif near.get(fam, set()) & set(profile["families"]):
        parts["role"] = (14, "Ruolo vicino a quelli svolti: l'esperienza commerciale è trasferibile.")
    else:
        parts["role"] = (6, "Nel CV non c'è un ruolo dello stesso tipo: va spiegato perché sei adatta.")
        tips.append("Nel titolo o nel sommario del CV usa le parole del ruolo cercato, se descrivono davvero il tuo lavoro.")

    # 3) esperienza
    req = rules.years_required(job_text or "")
    senior = bool(re.search(r"\b(senior|sr|lead|staff|expert|principal)\b", job.get("title", ""), re.I))
    have = profile["years"]
    if req is None:
        pts, note = (6, "Ruolo senior: l'esperienza attuale è probabilmente sotto le attese.") if senior else (11, "L'annuncio non indica gli anni richiesti.")
    else:
        gap = req - have
        pts = 15 if gap <= 0.3 else 10 if gap <= 1.3 else 6 if gap <= 2.3 else 2
        note = f"Richiesti {req} anni, nel CV ne risultano circa {have}."
        if gap > 0.3:
            tips.append(f"L'annuncio chiede {req} anni: compensa mettendo in evidenza risultati concreti e responsabilità (primi clienti acquisiti, ciclo di vendita gestito da sola).")
    parts["experience"] = (pts, note)

    # 4) studi
    edu = details.extract(job.get("title", ""), job_text or "", req).get("education", []) if has_text else []
    need_master = any("magistrale" in e.lower() or "mba" in e.lower() for e in edu)
    if not edu:
        parts["education"] = (8, "L'annuncio non indica un titolo di studio.")
    elif profile["education_level"] >= (2 if need_master else 1):
        parts["education"] = (10, "Titolo di studio in linea con quanto richiesto.")
    else:
        parts["education"] = (4, "Il titolo richiesto non risulta dal CV.")

    # 5) lingue
    need = _english_level_needed(job_text or "")
    cv_en = (profile["languages"].get("inglese") or "").upper()
    if job.get("local_ad"):
        parts["languages"] = (2, "Annuncio in lingua locale: quasi certamente serve una lingua che non è nel CV.")
        tips.append("Prima di candidarti verifica se la lingua del paese è obbligatoria.")
    elif need == "alto" and cv_en in ("B1", "B2", "DICHIARATA", "", "BUONO", "INTERMEDIO", "BASE"):
        parts["languages"] = (6, f"L'annuncio chiede inglese fluente o avanzato; il CV dichiara {cv_en.lower() if len(cv_en) > 2 else cv_en or 'nessun livello'}.")
        tips.append("Inglese: l'annuncio chiede un livello alto. Se hai una certificazione o esperienze di lavoro in inglese (rapporti con la sede estera, trattative), scrivile in modo esplicito.")
    elif "preferibile" in (job.get("languages") or ""):
        parts["languages"] = (8, "Una lingua aggiuntiva è gradita ma non obbligatoria.")
    else:
        parts["languages"] = (10, "Le lingue richieste sono coperte dal CV.")

    # 6) settore
    if rules.PROFILE is not None:  # profilo utente: conta quante competenze del suo mestiere l'annuncio cita e il CV mostra
        in_job = [w for w, rx in rules.SKILL_LIST if rx.search(jt)]
        in_cv = [w for w in in_job if re.search(re.escape(w), cv_text, re.I)]
        if len(in_job) >= 2 and len(in_cv) >= 2:
            parts["sector"] = (10, "L'annuncio è nel tuo ambito: cita competenze che il CV mostra.")
        elif len(in_job) >= 2:
            parts["sector"] = (5, "L'annuncio è nel tuo ambito, ma il CV lo mostra poco.")
        else:
            parts["sector"] = (6, "Ambito diverso dal tuo: l'esperienza è trasferibile ma meno diretta.")
    elif (software_job := len(set(m.lower() for m in rules.SOFTWARE_WORDS.findall(jt))) >= 2) and profile["software_background"]:
        parts["sector"] = (10, "Annuncio in ambito software/tecnologia, come l'esperienza nel CV.")
    elif rules.PROFILE is None and software_job:
        parts["sector"] = (5, "Annuncio in ambito software, poco visibile nel CV.")
    elif rules.PROFILE is None:
        parts["sector"] = (6, "Settore diverso dal software: l'esperienza è trasferibile ma meno diretta.")
    if rules.PROFILE is None and profile["mobility_background"] and not rules.MOBILITY_STRONG.search(jt):
        tips.append("Il CV parla molto di mobility: per questo annuncio descrivi il lavoro in termini di software, piattaforme e vendita B2B, che valgono in ogni settore.")

    # 7) qualità del CV
    ready = ats_readiness(profile)["score"]
    parts["quality"] = (round(5 * ready / 100), f"Leggibilità del CV per i sistemi di selezione: {ready}/100.")

    breakdown = [{"k": lab, "pts": parts[key][0], "max": mx, "note": parts[key][1]} for key, lab, mx in WEIGHTS]
    score = max(0, min(100, sum(b["pts"] for b in breakdown)))
    # requisiti dichiarati: coperto ("ok"), non coperto ("gap") o non indicato nell'annuncio ("na"); servono ai filtri
    exp_pts, edu_pts, lang_pts = parts["experience"][0], parts["education"][0], parts["languages"][0]
    reqs = {"experience": "na" if (req is None and not senior) else ("ok" if exp_pts >= 15 else "gap"),
            "education": "na" if not edu else ("ok" if edu_pts >= 10 else "gap"),
            "languages": "ok" if lang_pts >= 8 else "gap"}
    return {"score": score, "breakdown": breakdown, "matched": matched, "missing": missing, "tips": tips[:4],
            "reqs": reqs, "gaps": sum(v == "gap" for v in reqs.values()),
            "keyword_rate": round(100 * len(matched) / len(wanted)) if wanted and has_text else None,
            "ats": ATS_NOTES.get(job.get("source"), ATS_DEFAULT)}
