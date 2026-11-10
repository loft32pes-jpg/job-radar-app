"""Ricerca che impara dalle scelte della persona.

Gli annunci che salva, a cui si candida o che scarta nella bacheca sono le sue preferenze reali, più precise dell'intervista:
- i ruoli degli annunci che le piacciono diventano ruoli cercati (gruppo "Come quelli che hai salvato");
- il giudice AI riceve esempi di annunci salvati e scartati e vota di conseguenza.
Non si inventano ruoli: si generalizzano solo i titoli che la persona ha salvato. I ruoli che toglie dal profilo non tornano.
"""
import hashlib
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

LIKED = {"interested", "applied", "replied", "cv_requested", "interview", "offer", "closed", "saved"}
SYSTEM = """Aiuti un motore di ricerca di annunci di lavoro a imparare dalle scelte di una persona.
Ricevi il lavoro che desidera, i ruoli già cercati, i titoli degli annunci che ha SALVATO o a cui si è CANDIDATA e quelli
che ha SCARTATO. Ricava i titoli di ruolo da cercare in più perché la ricerca trovi TUTTI gli annunci simili a quelli salvati.
Regole:
- Solo ruoli che generalizzano gli annunci salvati (stesso mestiere scritto in altri modi, varianti junior/key/regional).
  Niente ruoli nuovi che non derivano dagli esempi salvati, niente ruoli tipici degli annunci scartati.
- Titoli brevi (1-4 parole) come compaiono negli annunci, senza aziende, città o livelli inventati.
- In inglese e in italiano (come li scrivono le aziende italiane).
Rispondi SOLO con JSON: {"titles_en": [max 12], "titles_it": [max 8], "summary": "una frase in italiano, rivolta alla persona (tu),
su cosa hai capito che le piace"}"""


def clean_title(t):
    """'Account Manager - Piemonte (m/f)' -> 'Account Manager'."""
    t = re.split(r"\s+[-–|•·]\s+|\(|\[|,|/\s|:\s", str(t or ""))[0]
    t = re.sub(r"\b(italy|italia|torino|turin|milano|remote|hybrid|ibrido|m/f|f/m|h/f|stage|tirocinio)\b.*$", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" -–")[:60]


def examples(tracker):
    pos, neg = [], []
    for f in ((tracker or {}).get("favs") or {}).values():
        j = f.get("job") or {}
        if not j.get("title"):
            continue
        row = (j["title"][:90], (j.get("company") or "")[:40])
        if f.get("state") == "discarded":
            neg.append(row + (str(f.get("why") or "")[:80],))
        elif f.get("state") in LIKED:
            pos.append(row)
    return pos, neg


def learn(profile, tracker, log=print):
    """Ritorna il dizionario "learned" aggiornato (o quello vecchio se le scelte non sono cambiate)."""
    pos, neg = examples(tracker)
    old = profile.get("learned") or {}
    off = {x.lower() for x in profile.get("learned_off") or []}
    sig = hashlib.sha1(repr((sorted(pos), sorted(neg), sorted(off))).encode()).hexdigest()[:16]
    if old.get("sig") == sig:
        return old
    if not pos:
        return {"sig": sig, "titles_en": [], "titles_it": [], "pos": [], "neg": [list(x) for x in neg[-20:]]}
    a = profile.get("answers") or {}
    cur = [t for c in profile.get("clusters") or [] if c.get("on", True) for t in c.get("titles_en", [])[:4]]
    user = (f"LAVORO DESIDERATO: {a.get('desired', '')[:800]}\nRUOLI GIÀ CERCATI: {', '.join(cur)}\n"
            f"ANNUNCI SALVATI O CANDIDATA:\n" + "\n".join(f"- {t} ({c})" for t, c in pos[-40:]) +
            "\nANNUNCI SCARTATI:\n" + ("\n".join(f"- {t} ({c})" + (f" perché: {w}" if w else "") for t, c, w in neg[-30:]) or "- nessuno"))
    base = [clean_title(t) for t, _ in pos]
    try:
        import ai
        data, _model = ai.write_json(SYSTEM, user, [], budget_s=60)
        en, it, summary = data.get("titles_en") or [], data.get("titles_it") or [], str(data.get("summary") or "")[:240]
    except Exception as e:  # senza AI si cercano i titoli salvati così come sono
        log(f"Apprendimento senza AI ({str(e)[:80]}): uso i titoli salvati")
        en, it, summary = [], [], ""

    taken = set()

    def tidy(xs, n):  # almeno due parole: "Consultant" da solo prenderebbe mestieri diversissimi
        out = []
        for x in xs:
            x = clean_title(x)
            if 4 < len(x) <= 50 and 1 < len(x.split()) <= 4 and x.lower() not in off and x.lower() not in taken:
                taken.add(x.lower())
                out.append(x)
        return out[:n]
    titles_en = tidy(list(en) + base, 30)
    learned = {"sig": sig, "at": time.strftime("%Y-%m-%d"), "titles_en": titles_en, "titles_it": tidy(it, 10),
               "summary": summary, "pos": [list(x) for x in pos[-20:]], "neg": [list(x) for x in neg[-20:]]}
    log("Imparato dalle tue scelte: " + ", ".join(learned["titles_en"] + learned["titles_it"]))
    return learned


def apply(profile):
    """Profilo per la ricerca: il gruppo dei ruoli imparati si aggiunge a quelli dell'intervista (in testa)."""
    lr = profile.get("learned") or {}
    if not (lr.get("titles_en") or lr.get("titles_it")):
        return profile
    p = dict(profile)
    # in coda: un annuncio che rientra in un gruppo dell'intervista resta in quel gruppo; il gruppo imparato allarga la ricerca
    p["clusters"] = list(profile.get("clusters") or []) + [
        {"id": "cL", "name": "Come quelli che hai salvato", "tier": 1, "on": True, "why": lr.get("summary", ""),
         "titles_en": lr.get("titles_en") or [], "titles_it": lr.get("titles_it") or [], "titles_local": {}}]
    return p
