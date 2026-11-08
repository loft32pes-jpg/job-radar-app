"""Parti dell'API su luoghi, candidature e materiale scritto dall'AI (usate da index.py)."""
import json
import os
import re
import time
import unicodedata

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# ---------- luoghi: "Torino", "Turin", "都灵", "تورينو" portano tutti alla stessa città ----------
try:
    from unidecode import unidecode
except ImportError:  # senza la libreria si perdono solo le scritture non latine
    def unidecode(s):
        return s

COUNTRY_IT = {
    "IT": "Italia", "DE": "Germania", "FR": "Francia", "GB": "Regno Unito", "ES": "Spagna", "NL": "Paesi Bassi", "BE": "Belgio",
    "CH": "Svizzera", "AT": "Austria", "PL": "Polonia", "IE": "Irlanda", "PT": "Portogallo", "SE": "Svezia", "DK": "Danimarca",
    "NO": "Norvegia", "FI": "Finlandia", "CZ": "Repubblica Ceca", "HU": "Ungheria", "RO": "Romania", "GR": "Grecia",
    "LU": "Lussemburgo", "EE": "Estonia", "LV": "Lettonia", "LT": "Lituania", "HR": "Croazia", "SI": "Slovenia", "SK": "Slovacchia",
    "BG": "Bulgaria", "MT": "Malta", "CY": "Cipro"}
# nomi dei paesi nelle lingue più comuni (italiano, inglese, francese, tedesco, spagnolo, lingua del paese)
COUNTRY_NAMES = {
    "IT": "italia italy italie italien", "DE": "germania germany allemagne deutschland alemania",
    "FR": "francia france frankreich", "GB": "regno unito united kingdom uk gran bretagna great britain england inghilterra royaume uni reino unido",
    "ES": "spagna spain espagne spanien espana", "NL": "paesi bassi olanda netherlands holland pays bas niederlande nederland",
    "BE": "belgio belgium belgique belgien belgie", "CH": "svizzera switzerland suisse schweiz suiza",
    "AT": "austria autriche osterreich", "PL": "polonia poland pologne polen polska", "IE": "irlanda ireland irlande irland eire",
    "PT": "portogallo portugal", "SE": "svezia sweden suede schweden sverige suecia", "DK": "danimarca denmark danemark danemark danmark dinamarca",
    "NO": "norvegia norway norvege norwegen norge noruega", "FI": "finlandia finland finlande finnland suomi",
    "CZ": "repubblica ceca czechia czech republic tchequie tschechien cesko chequia", "HU": "ungheria hungary hongrie ungarn magyarorszag hungria",
    "RO": "romania roumanie rumanien", "GR": "grecia greece grece griechenland ellada", "LU": "lussemburgo luxembourg luxemburg luxemburgo",
    "EE": "estonia estonie estland eesti", "LV": "lettonia latvia lettonie lettland latvija letonia", "LT": "lituania lithuania lituanie litauen lietuva",
    "HR": "croazia croatia croatie kroatien hrvatska croacia", "SI": "slovenia slovenie slowenien slovenija eslovenia",
    "SK": "slovacchia slovakia slovaquie slowakei slovensko eslovaquia", "BG": "bulgaria bulgarie bulgarien balgariya",
    "MT": "malta malte", "CY": "cipro cyprus chypre zypern kypros chipre"}
_PLACES = None


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", unidecode(str(s or "")).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _places():
    global _PLACES
    if _PLACES is None:
        with open(os.path.join(ROOT, "engine_data", "cities.json"), encoding="utf-8") as f:
            data = json.load(f)
        flat = {}
        for cc, table in data.items():
            for alias, (lat, lon, pop, name) in table.items():
                if alias not in flat or pop > flat[alias][2]:
                    flat[alias] = (lat, lon, pop, name, cc)
        countries = {}
        for cc, names in COUNTRY_NAMES.items():
            for n in [COUNTRY_IT[cc].lower()] + names.split():
                countries[norm(n)] = cc
            for multi in re.findall(r"[a-z]+ [a-z]+(?: [a-z]+)?", names):
                countries[multi] = cc
        _PLACES = (flat, countries)
    return _PLACES


def _close(a: str, b: str) -> bool:
    """Al massimo una lettera di differenza (scritture diverse dello stesso nome: "du ling" e "dou ling")."""
    a, b = a.replace(" ", ""), b.replace(" ", "")
    if abs(len(a) - len(b)) > 1 or min(len(a), len(b)) < 4:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] or a[i:] == b[i + 1:] or a[i + 1:] == b[i:]


def find_place(q: str):
    n = norm(q)
    if len(n) < 2:
        return None
    flat, countries = _places()
    if n in countries:
        return {"type": "country", "country": COUNTRY_IT[countries[n]], "name": COUNTRY_IT[countries[n]]}
    hit = flat.get(n)
    if not hit and len(n.replace(" ", "")) >= 5:
        best = None
        for alias, v in flat.items():
            if v[2] >= 50000 and alias[:1] == n[:1] and _close(alias, n) and (not best or v[2] > best[2]):
                best = v
        hit = best
    if not hit:
        return None
    lat, lon, pop, name, cc = hit
    return {"type": "city", "name": name, "country": COUNTRY_IT.get(cc, cc), "cc": cc, "lat": lat, "lon": lon}


COUNTRY_EN = {"IT": "Italy", "DE": "Germany", "FR": "France", "GB": "United Kingdom", "ES": "Spain", "NL": "Netherlands",
              "BE": "Belgium", "CH": "Switzerland", "AT": "Austria", "PL": "Poland", "IE": "Ireland", "PT": "Portugal",
              "SE": "Sweden", "DK": "Denmark", "NO": "Norway", "FI": "Finland", "CZ": "Czechia", "HU": "Hungary",
              "RO": "Romania", "GR": "Greece", "LU": "Luxembourg", "EE": "Estonia", "LV": "Latvia", "LT": "Lithuania",
              "HR": "Croatia", "SI": "Slovenia", "SK": "Slovakia", "BG": "Bulgaria", "MT": "Malta", "CY": "Cyprus"}


def resolve_cities(typed):
    """Città scritte dalla persona (in qualsiasi lingua) -> città riconosciute, al massimo tre. Le altre si scartano."""
    out, seen = [], set()
    for t in (typed or [])[:6]:
        p = find_place(str(t)[:80])
        if p and p["type"] == "city" and p["name"] not in seen:
            seen.add(p["name"])
            out.append({"typed": str(t).strip()[:60], "name": p["name"], "country": p["country"], "cc": p["cc"],
                        "country_en": COUNTRY_EN.get(p["cc"], ""), "lat": p["lat"], "lon": p["lon"]})
    return out[:3]


# ---------- candidature ----------
STATES = ["interested", "applied", "replied", "cv_requested", "interview", "offer", "closed", "discarded"]
OLD_STATES = {"saved": "interested", "rejected": "closed"}

PERSON_RULES = """Regole che non si possono violare:
- Non inventare nulla: esperienze, aziende, numeri, risultati, titoli di studio, certificazioni, lingue, strumenti. Usa solo
  quello che c'è nel CV o nel profilo. Valorizzalo e collegalo a cosa chiede l'annuncio, con le parole dell'annuncio quando
  descrivono la stessa cosa.
- Se un requisito importante dell'annuncio non risulta dal profilo, non fingere: segnalalo in "attenzione".
- Scrivi nella lingua dell'annuncio (se l'annuncio è in italiano, in italiano). Tono professionale e naturale, frasi concrete,
  niente formule fatte e niente entusiasmo di maniera: vietati "sono entusiasta", "corrisponde perfettamente", "perfect fit",
  "I am excited", "I am writing to express my interest", "persona dinamica e motivata", "passionate". Si apre con un fatto
  concreto (cosa sai fare che serve a loro), non con una dichiarazione di interesse.
- Firma con [NOME] e non scrivere contatti: li aggiunge l'app."""

KIT_SYSTEM = """Sei un consulente di carriera bravo e concreto. Prepari tutto il materiale per candidarsi a UN annuncio preciso,
per UNA persona precisa.
""" + PERSON_RULES + """
Rispondi SOLO con JSON:
{"lingua": "<codice ISO della lingua dell'annuncio>",
 "lettera": "<lettera di presentazione, 180-260 parole, 3-4 paragrafi, che cita cose specifiche dell'annuncio e dell'azienda>",
 "oggetto_email": "<oggetto per candidarsi via email>",
 "email": "<email breve per candidarsi, 60-90 parole, che rimanda al CV allegato>",
 "messaggio_linkedin": "<messaggio a chi recluta, massimo 280 caratteri>",
 "perche_noi": "<2-3 frasi: perché proprio questa azienda e questo ruolo>",
 "aspettativa": "<risposta pronta alla domanda sulla retribuzione desiderata per questo annuncio, con la cifra>",
 "punti_forti": ["<3-5 punti: cosa del profilo risponde a cosa chiede l'annuncio>"],
 "domande": [{"d": "<domanda che i moduli di candidatura fanno spesso>", "r": "<risposta pronta>"}],
 "parole_chiave_cv": ["<parole dell'annuncio da far emergere nel CV, solo se vere per questa persona>"],
 "attenzione": ["<requisiti dell'annuncio che il profilo non mostra>"]}
In "domande" metti 5-7 voci: perché questo ruolo, esperienza più rilevante, disponibilità e preavviso, sede o lavoro da remoto,
trasferimento, permesso di lavoro, aspettativa economica. Le risposte su retribuzione, preavviso, sede e permesso seguono le
preferenze della persona scritte sopra: non lasciarle vaghe."""

FILL_SYSTEM = """Compili il modulo di candidatura di un annuncio per conto di una persona. Ricevi l'annuncio, il profilo della
persona e l'elenco delle domande del modulo (con le opzioni, se è una scelta).
""" + PERSON_RULES + """
- LINGUA: scrivi ogni risposta nella lingua in cui è scritta la DOMANDA del modulo (domande in inglese: risposte in inglese),
  anche se il profilo della persona è in italiano.
- Per le domande a scelta rispondi con il testo esatto di una delle opzioni. Per sì/no rispondi con l'opzione corrispondente.
- Campi brevi: risposta breve. Campi di testo lungo: 60-150 parole.
- Retribuzione, preavviso, sede, trasferimento e permesso di lavoro: rispondi sempre, seguendo le preferenze della persona
  (se l'aspettativa economica non è indicata la proponi tu, realistica per ruolo e paese). Se il campo è numerico scrivi solo
  il numero.
- Domande facoltative su genere, etnia, orientamento, disabilità, servizio militare o simili: lascia "" (decide la persona).
- Se la risposta richiede un dato che non hai e non puoi dedurre (per esempio una data di nascita), lascia "" e la persona
  lo completerà a mano.
Rispondi SOLO con JSON: {"risposte": [{"id": "<id del campo>", "r": "<risposta>"}], "lettera": "<lettera di presentazione
se il modulo ne ha bisogno, altrimenti ''>"}"""


APPLY_LABELS = {
    "modalita": {"any": "indifferente", "remote": "preferisce lavorare da remoto", "hybrid": "preferisce l'ibrido", "onsite": "preferisce lavorare in sede"},
    "trasferimento": {"si": "disponibile a trasferirsi, anche all'estero", "paese": "disponibile a trasferirsi solo nel suo paese", "no": "non disponibile a trasferirsi"},
    "preavviso": {"subito": "disponibile subito", "2w": "preavviso di 2 settimane", "1m": "preavviso di 1 mese", "2-3m": "preavviso di 2-3 mesi"},
    "permesso": {"ue": "cittadinanza UE, può lavorare in tutta l'Unione senza visto", "permesso": "ha un permesso di lavoro",
                 "sponsor": "ha bisogno dello sponsor per il visto"},
}


def apply_text(a: dict) -> str:
    ap = (a or {}).get("apply") or {}
    out = []
    ral = ap.get("ral") or "auto"
    if ral == "auto":
        out.append("Aspettativa economica: non indicata. Proponi tu una cifra lorda annua realistica per QUESTO ruolo, in QUESTO paese "
                   "e con questi anni di esperienza, come intervallo arrotondato (es. \"35.000-40.000 EUR lordi annui\") e nella valuta del paese.")
    else:
        out.append(f"Aspettativa economica indicata dalla persona: {ral} mila euro lordi annui (adattala alla valuta del paese se diversa, "
                   "senza scendere sotto il minimo indicato).")
    for k, labels in APPLY_LABELS.items():
        if ap.get(k) in labels:
            out.append(labels[ap[k]][:1].upper() + labels[ap[k]][1:])
    return "\n".join(out)


def person_text(profile: dict, cv_text: str) -> str:
    import ai
    a = (profile or {}).get("answers") or {}
    parts = [f"Lavoro che desidera: {a.get('desired', '')}", f"Lavoro attuale o più recente: {a.get('current') or 'non indicato'}",
             f"Anni di esperienza: {a.get('years', '?')}", f"Studi: {a.get('education') or 'non indicati'}",
             f"Punti di forza: {a.get('strengths') or 'non indicati'}", f"Lingue: {', '.join(a.get('languages') or [])}",
             f"Competenze: {', '.join(((profile or {}).get('skills') or [])[:25])}", apply_text(a)]
    if cv_text:
        parts.append("CV (contatti tolti):\n" + ai.scrub(cv_text)[:7000])
    return "\n".join(parts)


def job_text(job: dict, jd: str) -> str:
    return (f"ANNUNCIO\nRuolo: {job.get('title', '')}\nAzienda: {job.get('company', '')}\nLuogo: {job.get('city', '')} {job.get('country', '')}\n"
            f"Testo:\n{(jd or job.get('excerpt') or '(testo non disponibile: basati su titolo e azienda)')[:9000]}")


def clean_kit(data: dict) -> dict:
    s = lambda v, n: str(v or "").strip()[:n]
    lst = lambda v, n: [s(x, 300) for x in (v or []) if str(x or "").strip()][:n]
    return {"lingua": s(data.get("lingua"), 5), "lettera": s(data.get("lettera"), 4000), "oggetto_email": s(data.get("oggetto_email"), 200),
            "email": s(data.get("email"), 1500), "messaggio_linkedin": s(data.get("messaggio_linkedin"), 400),
            "perche_noi": s(data.get("perche_noi"), 800), "aspettativa": s(data.get("aspettativa"), 600), "punti_forti": lst(data.get("punti_forti"), 6),
            "domande": [{"d": s(q.get("d"), 200), "r": s(q.get("r"), 1200)} for q in (data.get("domande") or []) if isinstance(q, dict)][:8],
            "parole_chiave_cv": lst(data.get("parole_chiave_cv"), 15), "attenzione": lst(data.get("attenzione"), 6),
            "creato": time.strftime("%Y-%m-%d")}
