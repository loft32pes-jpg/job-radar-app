"""AI generativa locale e gratuita: motore open source llama.cpp + modello open source Qwen3 4B (licenza Apache 2.0).

Tutto gira su questo computer: il CV e gli annunci non escono. Il motore (20 MB) è nel pacchetto, il modello (2,5 GB)
si scarica una volta sola, al primo uso, da Hugging Face. Serve a tradurre il CV e a riscriverlo per un annuncio.
"""
import json
import os
import subprocess
import sys
import threading
import time
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, ROOT  # noqa: E402

ENGINE = ROOT / "runtime" / "llama" / "llama-server.exe"
MODEL = DATA / "models" / "llm" / "qwen3-4b-instruct-q4.gguf"
MODEL_URL = "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
MODEL_BYTES = 2497281120
PORT = 8790
_lock = threading.Lock()
_state = {"proc": None, "down": None, "error": ""}   # down: None oppure percentuale 0-100 mentre scarica


def status() -> dict:
    ready = MODEL.exists() and MODEL.stat().st_size == MODEL_BYTES
    return {"engine": ENGINE.exists(), "model": ready, "downloading": _state["down"], "error": _state["error"],
            "size_gb": round(MODEL_BYTES / 1e9, 1)}


def _download():
    part = MODEL.with_suffix(".part")
    try:
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        done = part.stat().st_size if part.exists() else 0
        req = Request(MODEL_URL, headers={"User-Agent": "JobRadar/1.0", **({"Range": f"bytes={done}-"} if done else {})})
        with urlopen(req, timeout=60) as r, open(part, "ab" if done else "wb") as f:
            if done and r.status != 206:  # il server non riprende: si riparte da capo
                f.truncate(0)
                done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                _state["down"] = round(100 * done / MODEL_BYTES, 1)
        if part.stat().st_size != MODEL_BYTES:
            raise OSError("scaricamento incompleto")
        part.replace(MODEL)
        _state["error"] = ""
    except Exception as e:
        _state["error"] = f"Scaricamento del modello non riuscito ({str(e)[:80]}). Controlla la connessione e riprova: riparte da dove era arrivato."
    finally:
        _state["down"] = None


def start_download() -> bool:
    with _lock:
        if _state["down"] is not None or status()["model"]:
            return False
        _state["down"], _state["error"] = 0.0, ""
    threading.Thread(target=_download, daemon=True).start()
    return True


def _alive() -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
            return b"ok" in r.read()
    except Exception:
        return False


def _ensure():
    """Avvia il motore al primo uso (carica il modello in memoria: 10-30 secondi) e lo lascia acceso finché Job Radar è aperto."""
    with _lock:
        if _alive():
            return
        if not ENGINE.exists():
            raise RuntimeError("Motore AI non trovato nel pacchetto (cartella runtime\\llama).")
        if not status()["model"]:
            raise RuntimeError("Modello AI non ancora scaricato.")
        # pochi thread: se il computer sta già lavorando, tanti thread si pestano i piedi e l'AI rallenta moltissimo
        threads = max(2, min(4, (os.cpu_count() or 4) // 4))
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        _state["proc"] = subprocess.Popen(
            [str(ENGINE), "-m", str(MODEL), "-c", "8192", "--host", "127.0.0.1", "--port", str(PORT), "-t", str(threads), "--parallel", "1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        for _ in range(120):
            if _alive():
                return
            if _state["proc"].poll() is not None:
                break
            time.sleep(1)
        raise RuntimeError("Il motore AI non parte: forse il computer non ha abbastanza memoria libera (servono circa 4 GB).")


def stop():
    p = _state.get("proc")
    if p and p.poll() is None:
        p.terminate()


def chat(system: str, user: str, schema=None, max_tokens=2500, temperature=0.2) -> str:
    _ensure()
    body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature, "max_tokens": max_tokens, "cache_prompt": True}
    if schema:
        body["response_format"] = {"type": "json_object", "schema": schema}
    req = Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=1200) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def _obj_schema(ids):
    return {"type": "object", "properties": {str(i): {"type": "string"} for i in ids}, "required": [str(i) for i in ids]}


TRANSLATE_SYSTEM = """Sei un traduttore professionista di curriculum vitae. Traduci ogni blocco {src} in {dst}, con il lessico che si usa
davvero nei CV in {dst} (titoli di sezione standard, verbi d'azione, termini di business e tecnologia correnti).
Regole: non aggiungere e non togliere informazioni; nomi di persona, aziende, prodotti, università, email, numeri, date e sigle restano
identici; i mesi e parole come "in corso" si traducono; mantieni maiuscole e minuscole dello stile originale (un titolo tutto maiuscolo
resta tutto maiuscolo); la traduzione deve essere lunga più o meno come l'originale. Rispondi solo con il JSON richiesto: per ogni numero
di blocco, la sua traduzione."""


def translate_blocks(blocks: dict, direction: str, batch=10) -> dict:
    """blocks: {id: testo}. Ritorna {id: traduzione}. A gruppi, così ogni risposta resta breve e affidabile."""
    names = {"it": "italiano", "en": "inglese"}
    system = TRANSLATE_SYSTEM.format(src="dall'" + names[direction[:2]], dst=names[direction[3:]])
    import cvtranslate
    out = {}
    for k, t in blocks.items():  # link, numeri, date e titoli standard si traducono per regola: più veloci e sempre uguali
        ruled = cvtranslate.rule_translate(t, direction)
        if ruled is not None:
            out[k] = ruled
    ids = [k for k in blocks if k not in out]
    for i in range(0, len(ids), batch):
        part = ids[i:i + batch]
        user = "\n".join(f"[{k}] {blocks[k]}" for k in part)
        raw = chat(system, user, _obj_schema(part), max_tokens=1800, temperature=0.1)
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
        for k in part:
            out[k] = str(data.get(str(k)) or blocks[k]).strip()
    return out


REWRITE_SYSTEM = """Sei un consulente di carriera che sistema CV. Ricevi il CV diviso in blocchi numerati (testo dentro un'impaginazione
fissa) e l'obiettivo. Riscrivi solo i blocchi dove la modifica migliora davvero il CV.
Regole obbligatorie:
- Non inventare nulla: niente esperienze, numeri, strumenti, certificazioni o lingue che il CV non contiene già. Puoi riformulare,
  rendere esplicito ciò che c'è e usare i termini dell'annuncio quando descrivono la stessa cosa che il CV dice con altre parole.
- Non toccare nomi, date, contatti, titoli di sezione, nomi di aziende e università.
- Ogni blocco riscritto è lungo all'incirca come l'originale (al massimo il 15% in più) e resta nella lingua del CV.
- Frasi concrete, con un verbo d'azione all'inizio; niente aggettivi vuoti.
Rispondi solo con il JSON richiesto: "changes" è la lista dei blocchi riscritti (numero e testo nuovo, da 3 a 8 blocchi),
"notes" spiega in 2-4 frasi brevi cosa hai cambiato e perché."""
REWRITE_SCHEMA = {"type": "object", "required": ["changes", "notes"], "properties": {
    "changes": {"type": "array", "maxItems": 8, "items": {"type": "object", "required": ["id", "text"],
                                                           "properties": {"id": {"type": "integer"}, "text": {"type": "string"}}}},
    "notes": {"type": "array", "maxItems": 4, "items": {"type": "string"}}}}


def rewrite(segments: list, job, job_text: str, missing: list, lang: str) -> dict:
    """Stessa forma di deep.rewrite: {"ok", "segments": {id: testo}, "notes": [...]}. Non solleva eccezioni."""
    blocks = "\n".join(f"[{s['id']}] {s['text']}" for s in segments if len(s["text"]) > 25)
    if job:
        goal = (f"OBIETTIVO: adattare il CV a questo annuncio.\nRuolo: {job.get('title', '')}\nAzienda: {job.get('company', '')}\n"
                f"Annuncio (estratto):\n{(job_text or '')[:3500]}\n\nParole chiave dell'annuncio che non risultano nel CV: "
                f"{', '.join(missing[:10]) or 'nessuna'}. Usale solo dove il CV descrive già quella cosa con altre parole.")
    else:
        goal = ("OBIETTIVO: migliorare il CV in generale: punti più concreti, verbi d'azione all'inizio, risultati in evidenza, "
                "termini standard che i software di selezione riconoscono.")
    user = f"{goal}\n\nLingua del CV: {'italiano' if lang == 'it' else 'inglese'}\n\nBLOCCHI DEL CV\n{blocks}"
    try:
        raw = chat(REWRITE_SYSTEM, user, REWRITE_SCHEMA, max_tokens=2200, temperature=0.3)
        data = json.loads(raw)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"L'AI locale non ha risposto in modo leggibile ({type(e).__name__}): riprova."}
    orig = {s["id"]: s["text"] for s in segments}
    out = {}
    for c in data.get("changes", []):
        i, t = c.get("id"), str(c.get("text") or "").strip()
        if i in orig and t and t != orig[i] and len(t) <= len(orig[i]) * 1.35 + 20:  # blocchi troppo più lunghi non entrerebbero
            out[str(i)] = t
    return {"ok": True, "segments": out, "notes": [str(n) for n in data.get("notes", [])][:4], "model": "Qwen3 4B (sul tuo computer)"}
