"""Riscrittura e traduzione del CV con l'AI configurata (vedi ai.py). All'AI online non arrivano mai email, telefono e link."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import ai  # noqa: E402
import cvtranslate  # noqa: E402

REWRITE_SYSTEM = """Sei un consulente di carriera che sistema CV. Ricevi il CV diviso in blocchi numerati (testo dentro un'impaginazione
fissa) e l'obiettivo. Riscrivi i blocchi dove la modifica migliora davvero il CV.
Regole obbligatorie:
- Non inventare nulla: niente esperienze, numeri, strumenti, certificazioni o lingue che il CV non contiene già. Puoi riformulare,
  rendere esplicito ciò che c'è e usare i termini dell'annuncio quando descrivono la stessa cosa che il CV dice con altre parole.
- Una parola chiave dell'annuncio si usa SOLO se il CV descrive già quell'attività con altre parole. Se il CV non ne parla,
  non aggiungerla: meglio un CV onesto con una parola in meno che un'attività mai svolta.
- Non toccare nomi, date, contatti, titoli di sezione, nomi di aziende e università: non includere quei blocchi.
- Ogni blocco riscritto è lungo all'incirca come l'originale (al massimo il 15% in più) e resta nella lingua del CV.
- Frasi concrete, con un verbo d'azione all'inizio dei punti elenco; niente aggettivi vuoti.
Rispondi SOLO con un oggetto JSON: {"changes": [{"id": <numero del blocco>, "text": "<testo nuovo>"}, ...],
"notes": ["<cosa hai cambiato e perché, da 2 a 4 frasi brevi in italiano>"]}. Di norma da 4 a 10 blocchi."""

TRANSLATE_SYSTEM = """Sei un traduttore professionista di curriculum vitae. Traduci ogni blocco {src} in {dst}, con il lessico che si usa
davvero nei CV in {dst}. Non aggiungere e non togliere informazioni; nomi di persona, aziende, prodotti, università, numeri e sigle
restano identici; mantieni maiuscole e minuscole dello stile originale; la traduzione è lunga più o meno come l'originale.
Rispondi SOLO con un oggetto JSON che ha per chiave il numero di ogni blocco e per valore la sua traduzione: {{"12": "...", "13": "..."}}."""


def available() -> bool:
    return any(name != "AI sul computer" for name, _ in ai.providers())


def _personal(text: str) -> bool:
    """Blocchi di contatti e dati anagrafici: non si mandano all'AI e non si riscrivono."""
    return bool(re.search(r"@|https?://|www\.|linkedin\.com|\+?\d[\d\s().-]{7,}\d", text))


def rewrite(segments: list, job, job_text: str, missing: list, lang: str) -> dict:
    """{"ok", "segments": {id: testo}, "notes": [...], "model"}. Non solleva eccezioni."""
    usable = [s for s in segments if len(s["text"]) > 25 and not _personal(s["text"])]
    blocks = "\n".join(f"[{s['id']}] {s['text']}" for s in usable)
    if job:
        goal = (f"OBIETTIVO: adattare il CV a questo annuncio.\nRuolo: {job.get('title', '')}\nAzienda: {job.get('company', '')}\n"
                f"Annuncio:\n{(job_text or '(testo non disponibile: basati sul titolo)')[:6000]}\n\nParole chiave dell'annuncio che un confronto "
                f"automatico non trova nel CV: {', '.join(missing[:12]) or 'nessuna'}. Usale solo dove il CV descrive già quella cosa con altre parole.")
    else:
        goal = ("OBIETTIVO: migliorare il CV in generale: punti elenco più concreti, verbi d'azione all'inizio, risultati in evidenza, "
                "termini standard che i software di selezione riconoscono.")
    user = f"{goal}\n\nLingua del CV: {'italiano' if lang == 'it' else 'inglese'}\n\nBLOCCHI DEL CV\n{blocks}"
    try:
        data, provider = ai.chat_json(REWRITE_SYSTEM, user)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    orig = {s["id"]: s["text"] for s in usable}
    out = {}
    for c in data.get("changes") or []:
        try:
            i = int(c.get("id"))
        except (TypeError, ValueError, AttributeError):
            continue
        t = str(c.get("text") or "").strip()
        if i in orig and t and t != orig[i] and len(t) <= len(orig[i]) * 1.35 + 20:  # blocchi troppo più lunghi non entrerebbero
            out[str(i)] = t
    return {"ok": True, "segments": out, "notes": [str(n) for n in (data.get("notes") or [])][:4], "model": provider}


def translate_blocks(blocks: dict, direction: str, batch=18) -> dict:
    """{id: traduzione}. Link, numeri, date e titoli standard per regola; il resto all'AI, a gruppi."""
    names = {"it": "italiano", "en": "inglese"}
    system = TRANSLATE_SYSTEM.format(src="dall'" + names[direction[:2]], dst=names[direction[3:]])
    out = {}
    for k, t in blocks.items():
        ruled = cvtranslate.rule_translate(t, direction)
        if ruled is not None or _personal(t):
            out[k] = ruled if ruled is not None else t
    ids = [k for k in blocks if k not in out]
    for i in range(0, len(ids), batch):
        part = ids[i:i + batch]
        data, _ = ai.chat_json(system, "\n".join(f"[{k}] {blocks[k]}" for k in part))
        for k in part:
            out[k] = str(data.get(str(k)) or blocks[k]).strip()
    return out
