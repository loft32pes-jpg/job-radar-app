"""Estrae dal testo dell'annuncio le informazioni per la scheda: livello, skill, studi, documenti, contratto, trasferte.

Solo quello che è scritto nell'annuncio: se un dato non c'è, il campo resta vuoto (mai stime).
"""
import re

SKILLS = [  # (etichetta, regex)
    ("Salesforce", r"salesforce"), ("HubSpot", r"hubspot"), ("MS Dynamics", r"dynamics 365|microsoft dynamics"),
    ("Pipedrive", r"pipedrive"), ("CRM", r"\bcrm\b"), ("Sales Navigator", r"sales navigator"),
    ("Outreach/Salesloft", r"\boutreach\.io|salesloft"), ("Gong", r"\bgong\b"),
    ("MEDDIC", r"meddp?icc?"), ("Challenger Sale", r"challenger (sale|selling)"), ("SPIN selling", r"\bspin selling"),
    ("Solution selling", r"solution selling|consultative selling|value[- ]based selling|value selling"),
    ("Prospecting", r"prospecting|lead generation|outbound|cold call"), ("Negoziazione", r"negotiat|negoziazion"),
    ("Pipeline e forecast", r"pipeline management|forecast"), ("Account planning", r"account planning|account management"),
    ("Demo di prodotto", r"product demo|demonstrations?|\bdemos?\b|presentazioni"), ("Gare e RFP", r"\brfps?\b|\brfi\b|tender|gare d.appalto"),
    ("SaaS", r"\bsaas\b"), ("Cloud", r"\bcloud\b"), ("AWS", r"\baws\b|amazon web services"), ("Azure", r"\bazure\b"),
    ("Google Cloud", r"\bgcp\b|google cloud"), ("API e integrazioni", r"\bapis?\b|integration"), ("ERP / SAP", r"\berp\b|\bsap\b"),
    ("SQL", r"\bsql\b"), ("Python", r"\bpython\b"), ("Excel", r"\bexcel\b"), ("Power BI / Tableau", r"power ?bi|tableau|looker"),
    ("Data analytics", r"analytics|data analysis|analisi dei dati"), ("AI / Machine learning", r"(?-i:\bAI\b)|artificial intelligence|intelligenza artificiale|machine learning|\bllm"),  # "AI" solo maiuscolo: in italiano "ai" è una preposizione
    ("Cybersecurity", r"cyber ?security|information security|sicurezza informatica"), ("IoT", r"\biot\b|internet of things"),
    ("Networking", r"networking|\blan\b|\bwan\b|5g"), ("Go-to-market", r"go[- ]to[- ]market|\bgtm\b"),
    ("Partnership / canale", r"channel partner|partner ecosystem|reseller|alliances?"),
    ("Stakeholder management", r"stakeholder"), ("Change management", r"change management|adkar|prosci"),
    ("Project management", r"project management|\bpmp\b|prince2|gestione (di )?progett"), ("Agile / Scrum", r"\bagile\b|scrum"),
    ("Customer success", r"customer success|onboarding|retention|churn"), ("Contratti B2B", r"contract negotiation|contratti"),
]

BASE_SKILLS = list(SKILLS)


def set_extra_skills(words):
    """Aggiunge alle competenze riconosciute quelle del profilo di ricerca dell'utente (parole chiave del suo mestiere)."""
    have = {lab.lower() for lab, _ in BASE_SKILLS}
    extra = []
    for w in words or []:
        w = w.strip()
        if len(w) > 2 and w.lower() not in have:
            have.add(w.lower())
            extra.append((w[:1].upper() + w[1:], r"(?<!\w)" + re.escape(w).replace(r"\ ", r"[\s\-]+") + r"(?!\w)"))
    SKILLS[:] = BASE_SKILLS + extra


EDU = [
    ("Laurea magistrale / Master", r"master'?s? degree|\bmaster in\b|laurea magistrale|\bmsc\b|m\.sc|specialistica"),
    ("MBA", r"\bmba\b"),
    ("Laurea triennale / Bachelor", r"bachelor|laurea triennale|undergraduate degree|\bbsc\b|\bba degree"),
    ("Laurea", r"university degree|college degree|\bdegree\b|\blaurea\b|higher education|diploma universitario"),
]
FIELDS = [("ingegneria", r"engineering|ingegneria"), ("economia/business", r"economics|economia|business administration|business"),
          ("informatica", r"computer science|informatica|\bstem\b"), ("gestionale", r"gestionale|industrial engineering|management engineering"),
          ("marketing", r"marketing")]

DOCS = [
    ("CV", r"\bcv\b|resume|résumé|curriculum"), ("Lettera di motivazione", r"cover letter|motivation letter|lettera di (motivazione|presentazione)"),
    ("Portfolio", r"portfolio"), ("Referenze", r"\breferences\b|referenze"),
    ("Patente B", r"driving licen[cs]e|driver.?s licen[cs]e|patente"),
    ("Controllo dei precedenti", r"background check|casellario"),
]


def _find(text, pairs, limit):
    out = []
    for label, rx in pairs:
        m = re.search(rx, text, re.I)
        if m:
            out.append((m.start(), label))
    return [label for _, label in sorted(out)][:limit]


def level(title, text, years, criteria):
    sen = (criteria or {}).get("seniority", "")
    base = {"entry level": "Junior", "associate": "Junior / Associate", "mid-senior level": "Mid-Senior", "internship": "Stage",
            "director": "Senior", "executive": "Senior", "not applicable": ""}.get(sen.lower(), "")
    if not base:
        if re.search(r"\b(junior|graduate|entry[- ]level|trainee)\b", title, re.I):
            base = "Junior"
        elif re.search(r"\b(senior|sr|lead|principal|staff)\b", title, re.I):
            base = "Senior"
        elif years is not None:
            base = "Junior" if years <= 2 else "Mid" if years <= 5 else "Senior"
    if years:
        return f"{base or 'Esperienza'} ({years}+ anni)"
    return base or "Non indicato"


def extract(title: str, text: str, years, criteria=None) -> dict:
    t = text or ""
    d = {"level": level(title, t, years, criteria)}
    d["skills"] = _find(f"{title} {t}", SKILLS, 10)

    edu = _find(t, EDU, 4)
    if "Laurea" in edu and len(edu) > 1:
        edu.remove("Laurea")  # c'è già il tipo di laurea specifico
    fields = []
    for m in re.finditer(r"(degree|laurea|bachelor|master)[^.;]{0,60}", t, re.I):
        fields += [lab for lab, rx in FIELDS if re.search(rx, m.group(0), re.I)]
    fields = list(dict.fromkeys(fields))
    if edu and fields:
        edu.append("Ambito: " + ", ".join(fields[:3]))
    if edu and re.search(r"or equivalent (practical )?experience|o esperienza equivalente", t, re.I):
        edu.append("o esperienza equivalente")
    d["education"] = edu

    docs = _find(t, DOCS, 5)
    if re.search(r"no visa sponsorship|unable to (offer|provide)? ?(visa )?sponsor|cannot sponsor|not (able to )?(offer|provide) (visa )?sponsorship", t, re.I):
        docs.append("Permesso di lavoro già valido (niente visto sponsorizzato)")
    elif re.search(r"right to work|work permit|work authori[sz]ation|eligible to work|legally authori[sz]ed|permesso di (lavoro|soggiorno)", t, re.I):
        docs.append("Permesso di lavoro nel paese")
    elif re.search(r"visa sponsorship (is )?(available|provided|offered)|we (can|will) sponsor", t, re.I):
        docs.append("Visto sponsorizzabile dall'azienda")
    d["documents"] = docs

    contract = []
    emp = (criteria or {}).get("employment", "")
    if re.search(r"full[- ]time|tempo pieno", f"{emp} {t}", re.I):
        contract.append("Full-time")
    if re.search(r"part[- ]time", f"{emp} {t}", re.I):
        contract.append("Part-time")
    if re.search(r"permanent|tempo indeterminato|\bcdi\b|unbefristet", t, re.I):
        contract.append("Indeterminato")
    if re.search(r"fixed[- ]term|temporary|tempo determinato|\bcdd\b|maternity cover|parental leave cover", f"{emp} {t}", re.I):
        contract.append("Determinato")
    if re.search(r"\bcontractor\b|freelance|partita iva", f"{emp} {t}", re.I):
        contract.append("Contractor")
    d["contract"] = ", ".join(dict.fromkeys(contract))

    m = re.search(r"travel[^.;]{0,40}?(\d{1,2})\s?%|(\d{1,2})\s?%[^.;]{0,25}travel|trasferte[^.;]{0,30}?(\d{1,2})\s?%", t, re.I)
    if m:
        d["travel"] = f"Trasferte fino al {next(g for g in m.groups() if g)}%"
    elif re.search(r"willing(ness)? to travel|frequent travel|travel (is )?required|disponibilit\w+ (a|alle) trasferte", t, re.I):
        d["travel"] = "Trasferte richieste"
    else:
        d["travel"] = ""

    d["industry"] = (criteria or {}).get("industries", "")
    d["function"] = (criteria or {}).get("function", "")

    m = re.search(r"((as an?|in this role|you will|your role|the role|nel ruolo|la risorsa|il candidato|sarai|ti occuperai)[^.]{20,260}\.)", t, re.I)
    d["excerpt"] = m.group(1).strip() if m else ""
    return d
