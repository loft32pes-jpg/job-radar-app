"""Hub dei CV: più versioni del curriculum (originale, tradotta), tutte sul computer in profilo/hub/.

Una sola versione alla volta è "in uso" per il match con gli annunci. La traduzione produce una nuova versione
nello stesso formato dell'originale (PDF con il testo sostituito, o DOCX con gli stessi stili).
"""
import os
import re
import shutil
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
import cvmatch  # noqa: E402
import cvstore  # noqa: E402
import cvtranslate  # noqa: E402
from common import read_json, write_json  # noqa: E402

HUB = cvstore.PROFILE_DIR / "hub"
INDEX = HUB / "index.json"
LANG_NAME = {"it": "italiano", "en": "inglese"}


def _index():
    return read_json(INDEX, {"active": None, "items": []})


def _save(idx):
    HUB.mkdir(parents=True, exist_ok=True)
    write_json(INDEX, idx)


def listing():
    idx = _index()
    return {"active": idx["active"], "items": [{k: v for k, v in it.items() if k != "file"} for it in idx["items"]]}


def _entry(idx, cv_id):
    return next((it for it in idx["items"] if it["id"] == cv_id), None)


def path_of(cv_id):
    it = _entry(_index(), cv_id)
    return (HUB / it["file"], it) if it else (None, None)


def add_file(src_path: str, name: str, kind="originale", source_id=None, activate=True) -> dict:
    """Aggiunge un CV all'hub. Ritorna la voce creata (con 'words' per i controlli)."""
    HUB.mkdir(parents=True, exist_ok=True)
    idx = _index()
    cv_id = f"cv{int(time.time() * 1000)}"
    ext = os.path.splitext(name)[1].lower() or ".txt"
    stored = cv_id + ext
    shutil.copyfile(src_path, HUB / stored)
    text = cvmatch.extract_text(str(HUB / stored))
    entry = {"id": cv_id, "name": name, "file": stored, "ext": ext, "kind": kind, "from": source_id,
             "lang": cvtranslate.detect_lang(text), "words": len(re.findall(r"\w+", text)),
             "created": time.strftime("%Y-%m-%d %H:%M")}
    idx["items"].append(entry)
    if activate or not idx["active"]:
        idx["active"] = cv_id
    _save(idx)
    if idx["active"] == cv_id:
        cvstore.save_text(text, name)
    return entry


def activate(cv_id: str) -> bool:
    idx = _index()
    it = _entry(idx, cv_id)
    if not it:
        return False
    idx["active"] = cv_id
    _save(idx)
    cvstore.save_text(cvmatch.extract_text(str(HUB / it["file"])), it["name"])
    return True


def delete(cv_id: str):
    idx = _index()
    it = _entry(idx, cv_id)
    if not it:
        return
    for f in (HUB / it["file"], HUB / f"{cv_id}_segs.json"):
        if f.exists():
            f.unlink()
    idx["items"] = [x for x in idx["items"] if x["id"] != cv_id]
    if idx["active"] == cv_id:
        idx["active"] = idx["items"][-1]["id"] if idx["items"] else None
        if idx["active"]:
            _save(idx)
            activate(idx["active"])
            return
        cvstore.remove()
    _save(idx)


# ---------------------------------------------------------------- traduzione

def _docx_segments(path):
    """Paragrafi di un DOCX (testo dei w:t uniti), nell'ordine del documento."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    segs = []
    for i, m in enumerate(re.finditer(r"<w:p[ >].*?</w:p>", xml, re.S)):
        text = "".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", m.group(0), re.S))
        text = re.sub(r"&amp;", "&", re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", text))).strip()
        if text:
            segs.append({"id": len(segs), "para": i, "text": text})
    return segs


def _docx_build(src, segs, out):
    """Riscrive il DOCX mettendo la traduzione nel primo tratto di testo di ogni paragrafo (lo stile resta quello)."""
    by_para = {s["para"]: (s.get("translated") or s["text"]) for s in segs}
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    with zipfile.ZipFile(src) as zin:
        xml = zin.read("word/document.xml").decode("utf-8")
        counter = {"i": -1}

        def repl_para(m):
            counter["i"] += 1
            if counter["i"] not in by_para:
                return m.group(0)
            state = {"first": True}

            def repl_t(t):
                if state["first"]:
                    state["first"] = False
                    return f'<w:t xml:space="preserve">{esc(by_para[counter["i"]])}</w:t>'
                return "<w:t></w:t>"
            return re.sub(r"<w:t(?:\s[^>]*)?>.*?</w:t>", repl_t, m.group(0), flags=re.S)

        new_xml = re.sub(r"<w:p[ >].*?</w:p>", repl_para, xml, flags=re.S)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                zout.writestr(item, new_xml.encode("utf-8") if item.filename == "word/document.xml" else zin.read(item.filename))


def start_translation(cv_id: str, engine: str = "argos"):
    """Estrae i blocchi di testo e li traduce. Ritorna i segmenti da rivedere nella pagina."""
    path, it = path_of(cv_id)
    if not it:
        return None, "CV non trovato."
    if it["ext"] not in (".pdf", ".docx"):
        return None, "La traduzione nello stesso formato funziona con PDF e DOCX. Carica il CV in uno di questi formati."
    direction = "it_en" if it["lang"] == "it" else "en_it"
    if it["ext"] == ".pdf":
        segs, _ = cvtranslate.extract_segments(str(path))
        if sum(len(s["text"]) for s in segs) < 150:
            return None, "Nel PDF non c'è testo selezionabile (sembra un'immagine): da Canva scaricalo come 'PDF standard'."
        if engine == "argos":
            cvtranslate.translate_segments(segs, direction)
    else:
        segs = _docx_segments(str(path))
        if engine == "argos":
            for s, t in zip(segs, cvtranslate.translate_texts([s["text"] for s in segs], direction)):
                s["translated"] = t
    if engine == "ai":  # AI configurata (online): veloce e naturale; se non risponde si ripiega sul traduttore del computer
        import cvai
        try:
            done = cvai.translate_blocks({s["id"]: s["text"] for s in segs}, direction)
            for s in segs:
                s["translated"] = done[s["id"]]
        except Exception:
            for s, t in zip(segs, cvtranslate.translate_texts([s["text"] for s in segs], direction)):
                s["translated"] = t
    if engine == "local":  # modello generativo open source sul computer: più naturale, più lento
        import llm
        done = llm.translate_blocks({s["id"]: s["text"] for s in segs}, direction)
        for s in segs:
            s["translated"] = done[s["id"]]
    write_json(HUB / f"{cv_id}_segs.json", {"direction": direction, "segs": segs})
    return {"direction": direction, "from": LANG_NAME[direction[:2]], "to": LANG_NAME[direction[3:]],
            "segments": [{"id": s["id"], "text": (s.get("bullet", "") + " " + s["text"]).strip(), "translated": s["translated"],
                          "page": s.get("page", 0)} for s in segs]}, ""


def finish_translation(cv_id: str, edited: dict):
    """Genera il file tradotto con le correzioni fatte a mano e lo aggiunge all'hub."""
    path, it = path_of(cv_id)
    saved = read_json(HUB / f"{cv_id}_segs.json", None)
    if not it or not saved:
        return None, "Traduzione non trovata: riparti da 'Traduci'."
    segs = saved["segs"]
    for s in segs:
        if str(s["id"]) in edited:
            s["translated"] = str(edited[str(s["id"])]).strip() or s["translated"]
    to = saved["direction"][3:]
    base = os.path.splitext(it["name"])[0]
    name = f"{base} ({to.upper()}){it['ext']}"
    tmp = HUB / ("_build" + it["ext"])
    info = {"shrunk": 0, "failed": []}
    if it["ext"] == ".pdf":
        info = cvtranslate.build_pdf(str(path), segs, str(tmp))
    else:
        _docx_build(str(path), segs, str(tmp))
    entry = add_file(str(tmp), name, kind="tradotto", source_id=cv_id, activate=False)
    tmp.unlink()
    return {"entry": {k: v for k, v in entry.items() if k != "file"}, "shrunk": info["shrunk"], "failed": len(info["failed"])}, ""


# ---------------------------------------------------------------- modifica (miglioramento generale o per un annuncio)

HEAD_SKILLS = re.compile(r"^(hard |soft |technical |digital )?(skills?|competenze|competenze tecniche|conoscenze)\b", re.I)
HEAD_SUMMARY = re.compile(r"^(profilo|profile|summary|sommario|about( me)?|chi sono|presentazione)\b", re.I)


def _segments_of(path, it):
    if it["ext"] == ".pdf":
        return cvtranslate.extract_segments(str(path))[0]
    return _docx_segments(str(path))


def _after_heading(segs, rx):
    """Il blocco di testo che segue un titolo di sezione (es. quello sotto 'Competenze')."""
    for i, s in enumerate(segs[:-1]):
        if len(s["text"]) < 40 and rx.search(s["text"].strip()):
            return segs[i + 1]["id"]
    return None


def start_edit(cv_id: str):
    """Blocchi di testo del CV pronti per essere modificati nella pagina (stesso meccanismo della traduzione)."""
    path, it = path_of(cv_id)
    if not it:
        return None, "CV non trovato."
    if it["ext"] not in (".pdf", ".docx"):
        return None, "La modifica nello stesso formato funziona con PDF e DOCX. Carica il CV in uno di questi formati."
    segs = _segments_of(path, it)
    if sum(len(s["text"]) for s in segs) < 150:
        return None, "Nel file non c'è testo selezionabile (sembra un'immagine): da Canva scaricalo come 'PDF standard'."
    for s in segs:
        s["translated"] = s["text"]
    write_json(HUB / f"{cv_id}_segs.json", {"direction": None, "segs": segs})
    return {"name": it["name"], "lang": it["lang"], "ext": it["ext"],
            "skills_seg": _after_heading(segs, HEAD_SKILLS), "summary_seg": _after_heading(segs, HEAD_SUMMARY),
            "segments": [{"id": s["id"], "text": s["text"], "bullet": s.get("bullet", ""), "page": s.get("page", 0)} for s in segs]}, ""


def finish_edit(cv_id: str, edited: dict, label: str):
    """Genera il CV modificato (stessa impaginazione) e lo aggiunge all'hub. Ritorna anche il testo nuovo, per il punteggio."""
    path, it = path_of(cv_id)
    saved = read_json(HUB / f"{cv_id}_segs.json", None)
    if not it or not saved:
        return None, "Modifica non trovata: riapri l'editor."
    segs, changed = saved["segs"], 0
    for s in segs:
        new = str(edited.get(str(s["id"]), s["text"])).strip()
        if new and new != s["text"]:
            changed += 1
        s["translated"] = new or s["text"]
    if not changed:
        return None, "Non hai cambiato nessun blocco di testo."
    base = re.sub(r"\s*\((adattato|migliorato)[^)]*\)$", "", os.path.splitext(it["name"])[0])
    label = re.sub(r"[^\w .&-]", "", label or "migliorato")[:40].strip() or "migliorato"
    name = f"{base} ({label}){it['ext']}"
    tmp = HUB / ("_build" + it["ext"])
    info = {"shrunk": 0, "failed": []}
    if it["ext"] == ".pdf":
        # i blocchi non toccati restano esattamente com'erano: si riscrivono solo quelli modificati
        info = cvtranslate.build_pdf(str(path), [s for s in segs if s["translated"] != s["text"]], str(tmp))
    else:
        _docx_build(str(path), [s for s in segs if s["translated"] != s["text"]], str(tmp))
    entry = add_file(str(tmp), name, kind="adattato", source_id=cv_id, activate=False)
    tmp.unlink()
    text = cvmatch.extract_text(str(HUB / entry["file"]))
    return {"entry": {k: v for k, v in entry.items() if k != "file"}, "changed": changed, "shrunk": info["shrunk"],
            "failed": len(info["failed"]), "text": text}, ""

