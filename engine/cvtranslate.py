"""Traduzione del CV, tutta sul computer (nessun invio online).

Motore: modelli italiano-inglese e inglese-italiano inclusi nel pacchetto (data/models), eseguiti con CTranslate2.
PDF: il testo viene sostituito dentro il PDF originale, blocco per blocco, mantenendo posizione, dimensione,
colore e grassetto. È un lavoro "al meglio": i font originali (es. quelli di Canva) non sono riutilizzabili, quindi
il testo tradotto usa un font standard simile, rimpicciolito quando la frase tradotta è più lunga dello spazio.

Flusso: extract_segments() -> translate_segments() -> (revisione a mano nella pagina) -> build_pdf().
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA  # noqa: E402

from pathlib import Path  # noqa: E402

MODELS = DATA / "models"
FONTS = {(False, False): "helv", (True, False): "hebo", (False, True): "heit", (True, True): "hebi"}
_PLAIN = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "‐": "-", "­": "-",
          "…": "...", "€": "EUR ", " ": " ", "•": "-"}


def _plain(text: str) -> str:
    """Caratteri tipografici -> equivalenti semplici, presenti nel font standard e letti bene dagli ATS."""
    return "".join(_PLAIN.get(c, c) for c in text)
BULLETS = "•●▪·◦‣∙*-–"
_loaded = {}

# intestazioni e formule tipiche del CV: tradotte a mano, il modello generico le sbaglia spesso
GLOSSARY = {
    "it_en": {
        "esperienza lavorativa": "Work Experience", "esperienze lavorative": "Work Experience", "esperienza professionale": "Work Experience",
        "esperienze professionali": "Work Experience", "esperienza": "Experience", "formazione": "Education", "istruzione": "Education",
        "istruzione e formazione": "Education", "competenze": "Skills", "competenze informatiche": "Computer Skills",
        "competenze tecniche": "Technical Skills", "competenze trasversali": "Soft Skills", "lingue": "Languages",
        "progetti universitari": "University Projects", "progetti": "Projects", "contatti": "Contacts", "profilo": "Profile", "profilo professionale": "Professional Profile",
        "profilo personale": "Personal Profile", "altro": "Other", "competenze e conoscenze": "Skills",
        "telefono": "Phone", "data di nascita": "Date of birth", "certificazioni": "Certifications", "interessi": "Interests",
        "madrelingua": "Native", "italiano (madrelingua)": "Italian (Native)", "presente": "Present", "oggi": "Present",
        "competenze tecniche e soft skills": "Technical and Soft Skills", "competenze linguistiche": "Languages",
        "conoscenze linguistiche": "Languages", "anagrafica e contatti": "Personal Details and Contacts", "dati personali": "Personal Details",
        "altre informazioni": "Additional Information", "recapito": "Phone", "indirizzo": "Address", "email": "Email",
        "data e luogo di nascita": "Date and place of birth", "luogo di nascita": "Place of birth", "ingegnere gestionale": "Management Engineer",
        "in corso": "Present", "esperienze": "Experience", "hobby": "Hobbies", "hobby e interessi": "Hobbies and Interests",
        "volontariato": "Volunteering", "pubblicazioni": "Publications", "corsi": "Courses", "premi": "Awards", "obiettivo": "Objective",
        "chi sono": "About me", "sommario": "Summary", "patente": "Driving licence", "patente b": "Driving licence (B)", "patente tipo b": "Driving licence (B)",
    },
    "en_it": {
        "work experience": "Esperienza lavorativa", "professional experience": "Esperienza professionale", "experience": "Esperienza",
        "education": "Formazione", "skills": "Competenze", "computer skills": "Competenze informatiche",
        "technical skills": "Competenze tecniche", "soft skills": "Competenze trasversali", "languages": "Lingue",
        "university projects": "Progetti universitari", "projects": "Progetti", "contacts": "Contatti", "profile": "Profilo",
        "phone": "Telefono", "date of birth": "Data di nascita", "certifications": "Certificazioni", "interests": "Interessi",
        "native": "Madrelingua", "present": "Presente", "about me": "Chi sono", "summary": "Sommario", "address": "Indirizzo",
        "personal details": "Dati personali", "additional information": "Altre informazioni", "volunteering": "Volontariato",
        "awards": "Premi", "courses": "Corsi", "publications": "Pubblicazioni", "hobbies": "Hobby", "ongoing": "In corso",
    },
}
POSTFIX = {  # correzioni dopo la traduzione automatica (parola intera, senza distinzione maiuscole)
    "it_en": [(r"\bworking experience\b", "Work Experience"), (r"\bcommercial development\b", "Business Development"),
              (r"\btrade agreements?\b", "commercial agreements"), (r"\bmadrelingua\b", "Native"),
              (r"\bmother tongue\b", "Native"), (r"\bmanagement engineering\b", "Engineering and Management"),
              (r"^stage\b", "Internship"), (r"\bgoto-market\b", "Go-to-Market"), (r"\bmaster degree\b", "Master's Degree"), (r"\bbachelor in\b", "Bachelor's Degree in"),
              (r"\bsales b2b\b", "B2B Sales"), (r"\btriennial degree\b", "Bachelor's Degree"), (r"\bmagistral degree\b", "Master's Degree")],
    "en_it": [(r"\bsviluppo aziendale\b", "sviluppo commerciale")],
}
# righe di date ("OTTOBRE 2024 - IN CORSO  TORINO(TO)"): mesi e "in corso" si traducono per regola, il resto (luogo, ente) resta com'è
_MONTHS = [("gennaio", "January"), ("febbraio", "February"), ("marzo", "March"), ("aprile", "April"), ("maggio", "May"), ("giugno", "June"),
           ("luglio", "July"), ("agosto", "August"), ("settembre", "September"), ("ottobre", "October"), ("novembre", "November"), ("dicembre", "December")]
_NOW = [("in corso", "Present"), ("ad oggi", "Present"), ("oggi", "Present"), ("presente", "Present"), ("attuale", "Present")]
_DATE_LINE = {
    "it_en": re.compile(r"^(?:(?:" + "|".join(m for m, _ in _MONTHS) + r")\.?\s+)?(?:19|20)\d{2}\s*[-–—]\s*(?:(?:(?:" + "|".join(m for m, _ in _MONTHS) +
                        r")\.?\s+)?(?:19|20)\d{2}|" + "|".join(n for n, _ in _NOW) + r")(?P<rest>\s.*)?$", re.I),
    "en_it": re.compile(r"^(?:(?:" + "|".join(e for _, e in _MONTHS) + r")\.?\s+)?(?:19|20)\d{2}\s*[-–—]\s*(?:(?:(?:" + "|".join(e for _, e in _MONTHS) +
                        r")\.?\s+)?(?:19|20)\d{2}|present|current|ongoing|today)(?P<rest>\s.*)?$", re.I),
}


def _date_line(clean: str, direction: str):
    """Traduce una riga di sole date; None se la riga non è una riga di date."""
    m = _DATE_LINE[direction].match(clean)
    if not m:
        return None
    rest = m.group("rest") or ""
    head = clean[:len(clean) - len(rest)] if rest else clean
    pairs = _MONTHS + _NOW if direction == "it_en" else [(e, i) for i, e in _MONTHS] + [("present", "in corso"), ("current", "in corso"), ("ongoing", "in corso"), ("today", "in corso")]
    upper = head.isupper()
    for a, b in pairs:
        head = re.sub(r"(?<![A-Za-zÀ-ÿ])" + re.escape(a) + r"(?![A-Za-zÀ-ÿ])", b, head, flags=re.I)
    return (head.upper() if upper else head) + rest


KEEP = re.compile(r"^[\W\d_]*$|@|https?://|www\.|linkedin\.com")  # numeri, date numeriche, email, link: non si traducono


def detect_lang(text: str) -> str:
    """'it' oppure 'en' (le uniche due lingue gestite)."""
    w = re.findall(r"[a-zà-ÿ]+", text.lower())
    it = sum(x in {"e", "di", "il", "la", "per", "con", "che", "presso", "della", "del", "delle", "dei", "in", "le", "esperienza", "formazione", "competenze", "lingue", "laurea"} for x in w)
    en = sum(x in {"the", "and", "of", "for", "with", "at", "to", "in", "experience", "education", "skills", "languages", "degree", "managed", "led"} for x in w)
    return "it" if it >= en else "en"


def _engine(direction: str):
    if direction not in _loaded:
        import ctranslate2
        import sentencepiece as spm
        d = MODELS / direction
        if not (d / "model").exists():
            raise FileNotFoundError(f"Modello di traduzione mancante: {d}")
        _loaded[direction] = (ctranslate2.Translator(str(d / "model"), device="cpu"),
                              spm.SentencePieceProcessor(model_file=str(d / "sentencepiece.model")))
    return _loaded[direction]


def _split_sentences(text: str):
    parts = re.split(r"(?<=[.!?;:])\s+(?=[A-ZÀ-Ý0-9\"'(])", text.strip())
    return [p for p in parts if p]


def rule_translate(text: str, direction: str):
    """Traduzione per regola (link e numeri invariati, righe di date, titoli del glossario). None se serve un traduttore vero."""
    clean = re.sub(r"\s+", " ", text or "").strip()
    key = clean.lower().rstrip(":").strip()
    if not clean or re.search(r"https?://|www\.|linkedin\.com", clean) or             KEEP.search(clean) and not re.search(r"[A-Za-zÀ-ÿ]{4,}\s+[A-Za-zÀ-ÿ]{4,}", re.sub(r"\S*@\S*", "", clean)):
        return clean
    dated = _date_line(clean, direction)
    if dated is not None:
        return dated
    if key in GLOSSARY[direction]:
        word = GLOSSARY[direction][key]
        return (word.upper() if clean.isupper() and len(clean) > 3 else word) + (":" if clean.endswith(":") else "")
    return None


def translate_texts(texts, direction: str):
    """Traduce una lista di frasi/paragrafi. direction: 'it_en' oppure 'en_it'."""
    tr, sp = _engine(direction)
    gloss, out, jobs = GLOSSARY[direction], [None] * len(texts), []
    for i, t in enumerate(texts):
        clean = re.sub(r"\s+", " ", t or "").strip()
        key = clean.lower().rstrip(":").strip()
        dated = _date_line(clean, direction)
        if not clean or re.search(r"https?://|www\.|linkedin\.com", clean) or \
                KEEP.search(clean) and not re.search(r"[A-Za-zÀ-ÿ]{4,}\s+[A-Za-zÀ-ÿ]{4,}", re.sub(r"\S*@\S*", "", clean)):
            out[i] = clean                      # niente da tradurre: numeri, email, link (anche spezzati su due righe)
        elif dated is not None:
            out[i] = dated
        elif key in gloss:
            word = gloss[key].upper() if clean.isupper() and len(clean) > 3 else gloss[key]
            out[i] = word + (":" if clean.endswith(":") else "")
        else:
            sents = _split_sentences(clean)
            jobs.append((i, len(sents)))
            out[i] = sents
    flat = [s for i, _ in jobs for s in out[i]]
    if flat:
        res = tr.translate_batch([sp.encode(s, out_type=str) for s in flat], beam_size=4, max_decoding_length=300,
                                 repetition_penalty=1.1)
        done = [sp.decode(r.hypotheses[0]).strip() for r in res]
        k = 0
        for i, n in jobs:
            text = " ".join(done[k:k + n])
            k += n
            for rx, rep in POSTFIX[direction]:
                text = re.sub(rx, rep, text, flags=re.I)
            src = re.sub(r"\s+", " ", texts[i]).strip()
            if src.isupper() and len(src) > 3:
                text = text.upper()             # titoli tutti maiuscoli restano maiuscoli
            elif src[:1].isupper() and text[:1].islower():
                text = text[:1].upper() + text[1:]
            if not src.endswith(".") and text.endswith(".") and not src.endswith((":", ";", "!", "?")):
                text = text[:-1]                # niente punto aggiunto dove non c'era
            out[i] = text
    return out


# ---------------------------------------------------------------- PDF: estrazione dei blocchi di testo

def _rgb(color_int):
    return ((color_int >> 16) & 255) / 255, ((color_int >> 8) & 255) / 255, (color_int & 255) / 255


def extract_segments(pdf_path: str):
    """Blocchi di testo del PDF con posizione e stile. Ritorna (segmenti, n_pagine)."""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    segs = []
    for pno, page in enumerate(doc):
        pw = page.rect.width
        pending = None
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            cur = None
            for line in b["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in line["spans"]).strip()
                x0, y0, x1, y1 = line["bbox"]
                x0 = max(x0, spans[0]["bbox"][0])  # gli spazi iniziali (usati per far posto a un logo) non contano
                if len(text) == 1 and (text in BULLETS or "" <= text <= ""):
                    # Word mette il pallino dell'elenco su una riga a sé, accanto al testo: lo si ricorda per la riga che segue
                    pending = [x0, y0, x1, y1]
                    cur = None
                    continue
                main = max(spans, key=lambda s: len(s["text"]))
                style = {"size": round(main["size"], 1), "bold": bool(main["flags"] & 16) or "bold" in main["font"].lower(),
                         "italic": bool(main["flags"] & 2), "color": main["color"]}
                bullet = text[:1] in BULLETS and len(text) > 2 and text[1:2] in "  	"
                marked = pending is not None and abs((pending[1] + pending[3]) / 2 - (y0 + y1) / 2) < style["size"] * 0.7 and x0 > pending[0]
                bw = b["bbox"][2] - b["bbox"][0]
                if cur is not None:
                    reach = (cur["lines"][-1][2] - b["bbox"][0]) / max(bw, 1)       # quanto arriva a destra l'ultima riga del blocco aperto
                    tail = cur["text"].rstrip()
                    glue = tail.endswith((",", "-", ":")) or tail.split()[-1].lower() in (
                        "e", "ed", "di", "a", "al", "il", "la", "per", "con", "in", "and", "of", "the", "to", "for")
                    # una riga che finisce presto, oppure con un punto o un numero prima del margine, chiude il blocco: la successiva è un altro punto
                    short_end = text[:1].isupper() and not glue and (reach < 0.72 or (reach < 0.9 and tail[-1:] in ".)0123456789"))
                else:
                    short_end = False
                new = (cur is None or bullet or marked or short_end or abs(style["size"] - cur["size"]) > 0.6 or style["bold"] != cur["bold"]
                       or style["color"] != cur["color"] or y0 - cur["bbox"][3] > style["size"] * 0.9)
                if new:
                    cur = {"page": pno, "bbox": [x0, y0, x1, y1], "lines": [[x0, y0, x1, y1]], "text": text[1:].strip() if bullet else text,
                           "bullet": text[0] if bullet else "", **style}
                    if marked:  # il pallino sta a sinistra del testo: si tiene la sua posizione e il rientro del testo
                        cur["bullet"], cur["tx"] = "•", x0
                        cur["lines"].insert(0, pending)
                        cur["bbox"][0] = pending[0]
                        pending = None
                    segs.append(cur)
                else:
                    cur["text"] += " " + text
                    cur["lines"].append([x0, y0, x1, y1])
                    bb = cur["bbox"]
                    cur["bbox"] = [min(bb[0], x0), min(bb[1], y0), max(bb[2], x1), max(bb[3], y1)]
        # allineamento: di base a sinistra. Centrato solo se è evidente: più righe con inizi diversi ma lo stesso centro,
        # oppure una riga sola, corta, al centro della pagina, che non parte dal margine sinistro comune agli altri blocchi.
        # (Un paragrafo largo quanto la pagina ha il centro al centro della pagina, ma è allineato a sinistra.)
        mine = [s for s in segs if s["page"] == pno]
        lefts = {}
        for s in mine:
            k = round(s["bbox"][0])
            lefts[k] = lefts.get(k, 0) + 1
        for s in mine:
            xs = [ln[0] for ln in s["lines"]]
            centers = [(ln[0] + ln[2]) / 2 for ln in s["lines"]]
            if len(s["lines"]) > 1:
                centered = max(xs) - min(xs) > 4 and max(centers) - min(centers) < 4
            else:
                x0, x1 = s["bbox"][0], s["bbox"][2]
                centered = abs((x0 + x1) / 2 - pw / 2) < 3 and (x1 - x0) < 0.6 * pw and lefts.get(round(x0), 0) < 2
            s["align"] = 1 if centered else 0
    for i, s in enumerate(segs):
        s["id"] = i
    n = len(doc)
    doc.close()
    return segs, n


def translate_segments(segs, direction: str):
    out = translate_texts([s["text"] for s in segs], direction)
    for s, t in zip(segs, out):
        s["translated"] = t
    return segs


# ---------------------------------------------------------------- PDF: riscrittura

def build_pdf(src_path: str, segs, out_path: str) -> dict:
    """Sostituisce nel PDF ogni blocco con la sua traduzione. Ritorna quante righe sono state rimpicciolite o non entrate."""
    import pymupdf
    doc = pymupdf.open(src_path)
    shrunk, failed = 0, []
    by_page = {}
    for s in segs:
        by_page.setdefault(s["page"], []).append(s)
    for pno, items in by_page.items():
        page = doc[pno]
        for s in items:                      # 1) togli il testo originale, lasciando sfondi e grafica
            for ln in s["lines"]:
                page.add_redact_annot(pymupdf.Rect(ln) + (-0.5, -0.5, 0.5, 0.5), fill=False, cross_out=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        pw, ph = page.rect.width, page.rect.height
        for s in items:                      # 2) scrivi la traduzione nello stesso punto
            text = _plain((s.get("translated") or s["text"]).strip())
            x0, y0, x1, y1 = s["bbox"]
            # spazio disponibile: a destra fino al blocco vicino o al margine, in basso fino al blocco successivo nella stessa colonna
            right = min([o["bbox"][0] - 4 for o in items if o is not s and o["bbox"][0] > x1 and o["bbox"][1] < y1 and o["bbox"][3] > y0] + [pw - 18])
            below = min([o["bbox"][1] - 1 for o in items if o is not s and o["bbox"][1] >= y1 - 1 and o["bbox"][0] < right and o["bbox"][2] > x0] + [ph - 12])
            if s.get("align") == 1:
                half = max(pw / 2 - x0, x1 - pw / 2, 60) + 20
                rect_x0, rect_x1 = max(10, pw / 2 - half), min(pw - 10, pw / 2 + half)
            else:
                rect_x0, rect_x1 = x0, max(x1, right)
            # Font standard del PDF (Helvetica): è quello che i software di selezione rileggono senza errori.
            # Con i font di Windows incorporati, trattini e spazi vengono estratti come caratteri "speciali".
            font = FONTS[(s["bold"], s["italic"])]
            size, done = s["size"], False
            indent = (s["tx"] - x0 if s.get("tx") else s["size"] * 0.95) if s.get("bullet") else 0   # il puntino è disegnato, non scritto
            for _ in range(12):
                rect = pymupdf.Rect(rect_x0 + indent, y0 - size * 0.25, rect_x1, max(y1 + size * 0.45, below))
                rc = page.insert_textbox(rect, text, fontsize=size, fontname=font, color=_rgb(s["color"]),
                                         align=s.get("align", 0), lineheight=1.18)
                if rc >= 0:
                    done = True
                    break
                size *= 0.94
            if not done:
                failed.append(s["id"])
                continue
            if size < s["size"] * 0.97:
                shrunk += 1
            if s.get("bullet"):
                first = s["lines"][0]
                cy = (first[1] + first[3]) / 2
                page.draw_circle((x0 + s["size"] * 0.22, cy), s["size"] * 0.15, color=None, fill=_rgb(s["color"]))
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return {"shrunk": shrunk, "failed": failed}
