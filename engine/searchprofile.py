"""Profilo di ricerca dell'utente: nasce dall'intervista iniziale (lavoro desiderato a parole, esperienza, lingue, paesi,
cose da evitare) e, se c'è, dal CV. L'AI lo allarga in gruppi di ruoli realmente alla portata della persona.

Sta in profilo/ricerca.json. Da qui prendono le ricerche (LinkedIn e le altre fonti) e il punteggio (rules.py).
"""
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import ai  # noqa: E402
from common import ROOT, read_json, write_json  # noqa: E402

FILE = ROOT / "profilo" / "ricerca.json"
LANG_NAMES = {"it": "italiano", "en": "inglese", "es": "spagnolo", "fr": "francese", "de": "tedesco", "pt": "portoghese",
              "nl": "olandese", "pl": "polacco", "sv": "svedese", "da": "danese", "no": "norvegese", "fi": "finlandese",
              "cs": "ceco", "hu": "ungherese", "ro": "rumeno", "el": "greco"}
LOCAL_SEARCH_LANGS = ("es", "fr", "de", "pt", "nl")  # lingue in cui LinkedIn viene interrogato anche con i titoli locali
TIER_POINTS = {1: 40, 2: 33, 3: 26}
# parole troppo comuni nei titoli per dire qualcosa da sole
GENERIC_WORDS = {"manager", "business", "corporate", "market", "program", "programma", "portfolio", "portafoglio", "senior", "junior",
                 "specialist", "responsabile", "management", "associate", "executive", "officer", "lead", "team", "project", "progetto"}

SYSTEM = """Sei un orientatore di carriera esperto del mercato del lavoro europeo. Una persona descrive il lavoro che cerca.
Devi costruire il suo profilo di ricerca: i gruppi di ruoli da cercare negli annunci.

Obiettivo: allargare al massimo le opportunità REALI. Includi tutti i ruoli che questa persona può davvero svolgere con le
competenze e l'esperienza che ha: il ruolo chiesto, i ruoli equivalenti chiamati in altro modo, i ruoli vicini che usano le
stesse competenze, e i ruoli "ponte" raggiungibili con un piccolo salto. NON includere ruoli che richiedono competenze o
titoli che la persona non ha, ruoli di un altro mestiere, o ruoli messi lì solo per fare numero: ogni gruppo deve reggere
alla domanda "questa persona verrebbe presa in considerazione?". Rispetta il livello di esperienza indicato.

IL LAVORO DESIDERATO COMANDA. La persona può voler cambiare mestiere: se finora ha fatto un lavoro e ne desidera un altro,
i gruppi di tier 1 sono il lavoro che DESIDERA; l'esperienza passata serve a capire quali competenze si trasferiscono e quali
ruoli fanno da ponte tra ciò che ha fatto e ciò che vuole fare. Non riproporle il lavoro da cui vuole uscire.

Rispondi SOLO con un oggetto JSON in questa forma:
{
 "summary": "una frase in italiano, in seconda persona, che riassume cosa cerchi per lei/lui",
 "clusters": [
   {"name": "nome breve del gruppo di ruoli (in inglese se è il nome usato negli annunci)",
    "tier": 1,
    "why": "perché è alla sua portata, una frase breve in italiano",
    "titles_en": ["da 4 a 8 titoli di lavoro in inglese, come compaiono davvero negli annunci"],
    "titles_it": ["da 2 a 6 titoli in italiano"],
    "titles_local": {"es": ["2-4 titoli"], "fr": ["2-4"], "de": ["2-4"], "pt": ["1-3"], "nl": ["1-3"]}}
 ],
 "skills": ["da 12 a 20 competenze, strumenti o parole chiave che gli annunci adatti contengono, in inglese e italiano, 1-3 parole l'una"],
 "avoid_words": ["parole e frasi che negli annunci indicano i settori o i tipi di lavoro che la persona ha ESCLUSO, in inglese e
                  italiano (es. per il settore bancario: banking, bank, banca, bancario, retail banking)"],
 "prefer_words": ["parole e frasi che negli annunci indicano i suoi settori PREFERITI, in inglese e italiano (es. per la
                   telefonia: telecommunications, telecom, telco, telefonia, mobile operator)"],
 "exclude_titles": ["parole nel titolo che indicano un altro mestiere da scartare, simile nel nome ma diverso"],
 "title_words": ["da 10 a 18 parole singole (inglese e italiano) che compaiono nei titoli dei lavori adatti a questa persona anche
                  quando il titolo non è tra quelli elencati sopra: es. analyst, consultant, innovation, venture, strategy, startup"],
 "search_keywords": ["da 3 a 5 ricerche per parole chiave (2-3 parole in inglese l'una) per trovare annunci adatti che hanno titoli
                      imprevisti: es. startup innovation, venture capital analyst, corporate innovation"]
}
REGOLA SUI TITOLI: usa solo titoli STANDARD, quelli che le aziende scrivono davvero in cima agli annunci e che una persona
cercherebbe su LinkedIn ("Business Analyst", "Innovation Consultant", "Venture Capital Analyst", "Program Manager").
Mai titoli inventati o iper-specifici ("Business Analyst for Startups", "Analista Raising Fondi"): la specializzazione va nelle
"skills", non nel titolo. Un titolo deve poter comparire identico in centinaia di annunci.
tier 1 = esattamente il lavoro chiesto (1-2 gruppi); tier 2 = ruoli vicini, stesse competenze (1-3 gruppi);
tier 3 = ruoli ponte (0-2 gruppi). Da 3 a 6 gruppi in tutto. Titoli brevi (1-4 parole), senza livello (niente Junior/Senior)."""


def load():
    p = read_json(FILE, None)
    return p if p and p.get("clusters") else None


def save(profile: dict):
    profile["saved_at"] = datetime.now().astimezone().isoformat(timespec="minutes")
    write_json(FILE, profile)
    return profile


def _clean_list(v, n, maxlen=60):
    out = []
    for x in v if isinstance(v, list) else []:
        x = re.sub(r"\s+", " ", str(x)).strip(" .,;:\"'")
        if 2 <= len(x) <= maxlen and x.lower() not in (y.lower() for y in out):
            out.append(x)
    return out[:n]


def _titles(v, n):
    """Titoli puliti: senza livello (Junior/Senior) e senza la specializzazione dopo il trattino."""
    out = []
    for t in _clean_list(v, 12):
        t = re.split(r"\s[–—-]\s", t)[0]
        t = re.sub(r"(?i)\b(junior|senior|jr|sr|mid[- ]level|entry[- ]level)\b\.?", "", t)
        t = re.sub(r"\s+", " ", t).strip(" -,")
        if len(t) > 2 and t.lower() not in (x.lower() for x in out):
            out.append(t)
    return out[:n]


def _skills(v):
    out = []
    for x in v if isinstance(v, list) else []:
        out += [y for y in re.split(r"\s*/\s*", str(x))]  # "Market analysis / Analisi di mercato" sono due parole chiave
    return _clean_list(out, 30, 40)


def _normalize(data: dict, answers: dict, provider: str) -> dict:
    clusters = []
    for c in (data.get("clusters") or [])[:6]:
        titles_en, titles_it = _titles(c.get("titles_en"), 8), _titles(c.get("titles_it"), 6)
        if not titles_en and not titles_it:
            continue
        local = c.get("titles_local") if isinstance(c.get("titles_local"), dict) else {}
        tier = c.get("tier") if c.get("tier") in (1, 2, 3) else 2
        clusters.append({"id": f"c{len(clusters)}", "name": re.sub(r"\s+", " ", str(c.get("name") or titles_en[0]))[:40], "tier": tier,
                         "why": str(c.get("why") or "")[:200], "on": True, "titles_en": titles_en, "titles_it": titles_it,
                         "titles_local": {k: _titles(local.get(k), 4) for k in LOCAL_SEARCH_LANGS}})
    clusters.sort(key=lambda c: c["tier"])
    for i, c in enumerate(clusters):
        c["id"] = f"c{i}"
    return {"version": 1, "answers": answers, "summary": str(data.get("summary") or "")[:300], "clusters": clusters,
            "skills": _skills(data.get("skills")),
            # da evitare: frasi di più parole, oppure parole singole solo se le ha scritte la persona ("sales" da solo scarterebbe mezzo mondo)
            "avoid_words": _clean_list(data.get("avoid_words"), 20, 40) if str(answers.get("avoid") or "").strip() else [],
            "exclude_titles": _clean_list(data.get("exclude_titles"), 16, 40),
            "prefer_words": _clean_list(data.get("prefer_words"), 16, 40) if str(answers.get("prefer") or "").strip() else [],
            "title_words": [w for w in _clean_list(data.get("title_words"), 24, 24) if " " not in w and len(w) > 3 and w.lower() not in GENERIC_WORDS],
            "search_keywords": _clean_list(data.get("search_keywords"), 5, 40), "provider": provider}


def _fallback(answers: dict) -> dict:
    """Senza AI: i ruoli sono quelli scritti dall'utente, separati da virgole o a capo. Nessun allargamento."""
    parts = [p.strip() for p in re.split(r"[,;\n/]| e | o | or | and ", answers.get("desired", "")) if 2 < len(p.strip()) <= 50][:8]
    return {"summary": "Cerco gli annunci con i ruoli che hai scritto. Senza AI la ricerca non viene allargata ai ruoli affini.",
            "clusters": [{"name": parts[0] if parts else "Ruolo cercato", "tier": 1, "why": "È il ruolo che hai indicato.",
                          "titles_en": parts, "titles_it": parts, "titles_local": {}}], "skills": [], "avoid_words": [], "exclude_titles": []}


def build(answers: dict, cv_profile=None) -> dict:
    """Costruisce la proposta di profilo dall'intervista. Non la salva: l'utente la rivede e la conferma."""
    langs = ", ".join(LANG_NAMES.get(x, x) for x in answers.get("languages") or ["it", "en"])
    lines = [f"LAVORO CERCATO (parole sue): {answers.get('desired', '').strip()[:1500]}",
             f"Anni di esperienza: {answers.get('years', 'non indicati')}", f"Livello cercato: {answers.get('level') or 'coerente con gli anni'}",
             f"Lingue di lavoro: {langs}", f"Titolo di studio: {answers.get('education') or 'non indicato'}",
             f"Punti di forza dichiarati: {answers.get('strengths') or 'non indicati'}",
             f"Lavoro attuale o più recente: {answers.get('current') or 'non indicato'}",
             f"Settori PREFERITI: {answers.get('prefer') or 'nessuna preferenza'}",
             f"Settori o tipi di lavoro ESCLUSI: {answers.get('avoid') or 'niente'}"]
    if cv_profile:
        lines.append("DAL CV: competenze riconosciute: " + ", ".join((cv_profile.get("skills") or []) + (cv_profile.get("concepts") or []))
                     + f"; anni di esperienza rilevati: {cv_profile.get('years')}; studi: livello {cv_profile.get('education_level')}"
                     + f" ({', '.join(cv_profile.get('education_fields') or [])})")
    if answers.get("cv_excerpt"):
        lines.append("ESTRATTO DEL CV (esperienze):\n" + ai.scrub(answers["cv_excerpt"])[:2500])
    try:
        data, provider = ai.chat_json(SYSTEM, "\n".join(lines))
        lists = ["skills", "title_words", "search_keywords"] + (["avoid_words"] if str(answers.get("avoid") or "").strip() else []) \
            + (["prefer_words"] if str(answers.get("prefer") or "").strip() else [])
        if any(not data.get(k) for k in lists):
            # con risposte lunghe l'AI a volte si ferma ai gruppi di ruoli: le liste di parole si chiedono a parte
            names = ", ".join(str(c.get("name")) for c in data.get("clusters") or [])
            more, _ = ai.chat_json(SYSTEM + "\n\nI gruppi di ruoli sono già stati scelti: " + names + '. Ora rispondi SOLO con le liste: '
                                   '{"skills": [...], "avoid_words": [...], "prefer_words": [...], "exclude_titles": [...], '
                                   '"title_words": [...], "search_keywords": [...]}', "\n".join(lines))
            for k in ("skills", "avoid_words", "prefer_words", "exclude_titles", "title_words", "search_keywords"):
                data[k] = data.get(k) or more.get(k)
        prof = _normalize(data, answers, provider)
        if not prof["clusters"]:
            raise ai.AIError("risposta senza ruoli")
        prof["ai_error"] = ""
    except Exception as e:
        prof = _normalize(_fallback(answers), answers, "nessuna AI")
        prof["ai_error"] = str(e)[:200]
    return prof


# ---------------------------------------------------------------- dal profilo alle ricerche

def _or_query(titles, n=7):
    return " OR ".join(f'"{t}"' for t in titles[:n])


def search_plan(profile: dict) -> dict:
    """Le ricerche da fare: gruppi OR per LinkedIn (uno per gruppo di ruoli), titoli locali per lingua, parole per le altre fonti."""
    on = [c for c in profile["clusters"] if c.get("on", True)]
    groups = [_or_query(c["titles_en"]) for c in on if c["titles_en"]]
    native = {"it": _or_query([t for c in on for t in c["titles_it"][:3]], 8)}
    for lg in LOCAL_SEARCH_LANGS:
        ts = [t for c in on for t in (c.get("titles_local") or {}).get(lg, [])[:2]]
        if ts:
            native[lg] = _or_query(ts, 8)
    first = [t for c in on for t in c["titles_en"][:2]]
    groups += [k for k in profile.get("search_keywords") or []][:4]  # ricerche larghe: le filtra poi il giudice AI
    # LinkedIn: una ricerca "larga" con i titoli principali di tutti i gruppi (fatta in ogni paese) e, solo nei paesi grandi,
    # le ricerche dei gruppi più vicini alla richiesta più due larghe. Meno ricerche = più tempo per leggere gli annunci.
    core, k = [], 0
    while len(core) < 9 and k < 3:
        core += [c["titles_en"][k] for c in on if len(c["titles_en"]) > k]
        k += 1
    near = sorted((c for c in on if c["titles_en"]), key=lambda c: c.get("tier", 2))[:4]
    # vicino casa: ogni titolo cercato da solo (i portali nazionali non capiscono gli OR), prima italiano poi inglese
    local = []
    for c in sorted(on, key=lambda c: c.get("tier", 2)):
        n_it, n_en = (4, 14) if c.get("id") == "cL" else (3, 3)  # i ruoli imparati dalle sue scelte si cercano tutti
        for t in c["titles_it"][:n_it] + c["titles_en"][:n_en]:
            if t.lower() not in {x.lower() for x in local}:
                local.append(t)
    lr = profile.get("learned") or {}
    off = {str(x).lower() for x in profile.get("learned_off") or []}
    return {"groups": groups[:10], "native": {k: v for k, v in native.items() if v},
            # aziende che segue: nelle sue città si cercano per nome, ultimi 30 giorni (gli annunci restano aperti a lungo)
            "companies": [c for c in lr.get("companies") or [] if c.lower() not in off][:10],
            # ricerche nuove (ruoli appena imparati): la prima volta guardano l'ultimo mese, non solo l'ultima settimana
            "deep": {str(t).lower() for t in profile.get("deep_terms") or []},
            "core": _or_query(core, 9),
            "big": [_or_query(c["titles_en"]) for c in near] + [k for k in profile.get("search_keywords") or []][:2],
            "en": first[:8], "it": [t for c in on for t in c["titles_it"][:1]][:4], "eures": first[:6], "local": local[:40]}
