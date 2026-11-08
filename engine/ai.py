"""Un solo punto di accesso all'intelligenza artificiale, qualunque sia il fornitore.

Ordine di scelta (config.json, sezione "ai", "provider": "auto"):
1. un servizio compatibile OpenAI configurato a mano (Groq, Gemini, OpenRouter...: "base_url", "api_key", "model");
2. Claude, se c'è la chiave in "anthropic";
3. Pollinations: servizio pubblico gratuito, senza chiave e senza account (va bene per le prove);
4. il modello open source sul computer, se è stato scaricato.
A Pollinations e agli altri servizi online viene inviato solo il testo strettamente necessario, mai email e telefono.
"""
import json
import os
import re
import sys
import time
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))
from common import ROOT, read_json  # noqa: E402

POLLINATIONS = "https://text.pollinations.ai/openai"


class AIError(Exception):
    pass


def _cfg():
    return read_json(ROOT / "config.json", {})


def scrub(text: str) -> str:
    """Toglie email, telefoni e link personali prima di inviare un testo a un servizio online."""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[email]", text or "")
    text = re.sub(r"(?:\+|00)?\d[\d\s().-]{7,}\d", "[telefono]", text)
    return re.sub(r"https?://\S+|www\.\S+|linkedin\.com/\S+", "[link]", text)


def _openai_like(url, key, model, system, user, timeout=120):
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}, "temperature": 0.3,
            "seed": int(time.time()) % 100000}  # seme diverso a ogni chiamata: il servizio gratuito altrimenti ripete risposte in memoria
    headers = {"Content-Type": "application/json", "User-Agent": "JobRadar/1.0"}
    if key:
        headers["Authorization"] = "Bearer " + key
    with urlopen(Request(url, data=json.dumps(body).encode("utf-8"), headers=headers), timeout=timeout) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def _claude(key, system, user):
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    with client.messages.stream(model="claude-opus-5-5", max_tokens=8000, system=system,
                                messages=[{"role": "user", "content": user}]) as stream:
        msg = stream.get_final_message()
    return "".join(b.text for b in msg.content if b.type == "text")


_FOUND = {}


def models_of(p: dict) -> list:
    """Modelli da usare per un fornitore: quelli scritti in config.json, altrimenti l'elenco che il fornitore stesso
    dichiara (basta incollare la chiave: i nomi dei modelli non servono)."""
    listed = [p.get("model")] + list(p.get("judge_models") or p.get("models") or [])
    listed = list(dict.fromkeys(m for m in listed if m))
    if listed or not p.get("api_key"):
        return listed
    base = p["base_url"].rstrip("/")
    if base not in _FOUND:
        try:
            req = Request(base + "/models", headers={"Authorization": "Bearer " + p["api_key"], "User-Agent": "JobRadar/1.0"})
            with urlopen(req, timeout=15) as r:
                ids = [m["id"] for m in json.load(r).get("data", []) if m.get("active", True)]
            skip = re.compile(r"whisper|tts|guard|embed|vision|audio|image|orpheus|compound|allam|-8b|rerank", re.I)
            _FOUND[base] = [i for i in ids if not skip.search(i)][:4]
        except Exception:
            _FOUND[base] = []
    return _FOUND[base]


def providers():
    """Fornitori disponibili adesso, nell'ordine in cui verranno provati: [(nome, funzione)]."""
    cfg = _cfg()
    ai = cfg.get("ai", {})
    want = (ai.get("provider") or "auto").lower()
    out = []
    if want in ("auto", "custom"):
        # fornitore principale e fornitori di riserva ("extra"); per ognuno anche i modelli di riserva, perché ogni modello
        # ha una quota gratuita giornaliera sua: se il primo l'ha finita si passa al successivo
        for p in [ai] + list(ai.get("extra") or []):
            if not p.get("base_url") or (p is not ai and not p.get("api_key")):
                continue
            url = p["base_url"].rstrip("/") + ("" if p["base_url"].rstrip("/").endswith("/chat/completions") else "/chat/completions")
            for m in models_of(p):
                out.append((p.get("name") or "AI configurata",
                            lambda s, u, url=url, key=p.get("api_key", ""), m=m: _openai_like(url, key, m, s, u)))
    key = cfg.get("anthropic", {}).get("api_key", "")
    if key and want in ("auto", "claude"):
        out.append(("Claude", lambda s, u: _claude(key, s, u)))
    if want in ("auto", "pollinations"):
        out.append(("AI gratuita online", lambda s, u: _openai_like(POLLINATIONS, "", "openai", s, u)))
    if want in ("auto", "local"):
        try:
            import llm
            if llm.status()["model"]:
                out.append(("AI sul computer", lambda s, u: llm.chat(s, u, {"type": "object"}, max_tokens=3000)))
        except Exception:
            pass
    return out


def write_json(system: str, user: str, order, budget_s=50):
    """Per i testi da scrivere bene (candidature): prova i modelli nell'ordine dato, una volta ciascuno e senza attese,
    finché uno risponde. order = [[nome fornitore, modello], ...] (da modelli.json). Ritorna (dati, modello)."""
    ai = _cfg().get("ai", {})
    provs = {(p.get("name") or "AI configurata"): p for p in [ai] + list(ai.get("extra") or []) if p.get("base_url") and p.get("api_key")}
    t0, errors = time.time(), []
    for name, model in list(order or []) + [[n, m] for n, p in provs.items() for m in models_of(p)]:
        p = provs.get(name)
        if not p or time.time() - t0 > budget_s:
            continue
        url = p["base_url"].rstrip("/")
        url += "" if url.endswith("/chat/completions") else "/chat/completions"
        try:
            body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "response_format": {"type": "json_object"}, "temperature": 0.5}
            req = Request(url, data=json.dumps(body).encode("utf-8"),
                          headers={"Content-Type": "application/json", "User-Agent": "JobRadar/1.0", "Authorization": "Bearer " + p["api_key"]})
            with urlopen(req, timeout=max(8, min(45, budget_s - (time.time() - t0)))) as r:
                raw = json.load(r)["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", raw or "", re.S)
            return json.loads(m.group(0) if m else raw), model
        except Exception as e:
            errors.append(f"{model}: {getattr(e, 'code', type(e).__name__)}")
    raise AIError("Nessuna AI ha risposto (" + ", ".join(errors[-3:]) + "). Riprova tra un minuto.")


def chat_json(system: str, user: str, online_ok=True):
    """Chiede all'AI una risposta in JSON. Ritorna (dati, nome del fornitore). Prova i fornitori in ordine; AIError se nessuno risponde."""
    errors = []
    for name, fn in providers():
        if not online_ok and name != "AI sul computer":
            continue
        for attempt in range(3):
            try:
                raw = fn(system, user)
                m = re.search(r"\{.*\}", raw or "", re.S)
                return json.loads(m.group(0) if m else raw), name
            except Exception as e:  # risposta non leggibile o servizio occupato: si aspetta e si riprova, poi si passa al successivo
                errors.append(f"{name}: {type(e).__name__} {str(e)[:60]}")
                busy = getattr(e, "code", 0) in (402, 429, 503)  # il servizio gratuito accetta una richiesta ogni tanto
                try:
                    wait = float(e.headers.get("retry-after") or 0)
                except Exception:
                    wait = 0
                if wait > 90 or getattr(e, "code", 0) in (401, 402, 403, 404):
                    break  # quota di oggi finita o servizio non disponibile: inutile insistere, si passa al successivo
                if attempt < 2:
                    time.sleep(min(30, wait + 1) if wait else 25 if busy else 4)
    raise AIError("Nessuna AI ha risposto (" + ", ".join(errors[-3:]) + "). Controlla la connessione e riprova." if errors
                  else "Nessuna AI disponibile.")
