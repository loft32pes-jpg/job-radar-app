"""Sceglie ogni giorno i modelli AI gratuiti migliori tra quelli disponibili con le chiavi configurate.

Ogni giorno escono modelli nuovi e quelli vecchi vengono spenti: invece di scriverli a mano nel codice, si chiede a ogni
fornitore l'elenco dei suoi modelli, si mettono in ordine (più recenti e più grandi prima) e si prova ciascuno con una
richiesta minima. Restano solo quelli che rispondono davvero con il piano gratuito.

Uso: python engine/modelli.py dati/modelli.json      (la configurazione con le chiavi arriva da JR_CONFIG)
Risultato: {"aggiornato": ..., "fornitori": {"Groq": {"scrittura": [...], "giudice": [...]}, ...}, "scrittura": [[fornitore, modello], ...]}
"""
import json
import os
import re
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SKIP = re.compile(r"whisper|tts|guard|embed|image|audio|vision|transcribe|robot|computer|live|native|lyria|veo|banana|aqa|"
                  r"deep-research|antigravity|customtools|allam|prompt|imagen|omni|clip|realtime|-8b\b|1b\b|3b\b|instant|orpheus|gemma", re.I)


def _get(url, key, body=None, timeout=40):
    req = Request(url, data=json.dumps(body).encode() if body is not None else None,
                  headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "JobRadar/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)


def rank(model: str) -> float:
    """Punteggio a occhio, dai nomi: versione più alta, modello più grande, "pro" sopra "flash" sopra "lite"."""
    m = model.lower()
    nums = [float(x) for x in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d.]*b\b)", m.split("/")[-1])[:1]]
    size = max([float(x) for x in re.findall(r"(\d+(?:\.\d+)?)b\b", m)] or [0])
    score = (nums[0] if nums else 0) * 10 + min(size, 400) / 8
    score += 30 if "pro" in m else 12 if "flash" in m or "gpt-oss" in m else 0
    parts = set(re.split(r"[-_/.:]", m))
    score -= 14 if parts & {"lite", "mini", "nano", "small", "tiny"} else 0
    score -= 6 if "preview" in m or "exp" in m else 0
    score -= 4 if "latest" in m else 0
    return score


def probe(base, key, model):
    body = {"model": model, "messages": [{"role": "user", "content": 'Rispondi solo con JSON: {"ok": true}'}],
            "response_format": {"type": "json_object"}}
    t = time.time()
    try:
        out = _get(base + "/chat/completions", key, body, timeout=35)
        json.loads(re.search(r"\{.*\}", out["choices"][0]["message"]["content"], re.S).group(0))
        return round(time.time() - t, 1), None
    except HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, type(e).__name__


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "modelli.json"
    ai = json.loads(os.environ["JR_CONFIG"]).get("ai", {})
    result = {"aggiornato": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "fornitori": {}, "scrittura": []}
    candidates = []
    for p in [ai] + list(ai.get("extra") or []):
        if not (p.get("base_url") and p.get("api_key")):
            continue
        base, name = p["base_url"].rstrip("/"), p.get("name") or "AI"
        try:
            ids = [m["id"] for m in _get(base + "/models", p["api_key"]).get("data", []) if m.get("active", True)]
        except Exception as e:
            print(f"{name}: elenco modelli non disponibile ({type(e).__name__})")
            continue
        # niente "pro" (fuori dal piano gratuito) né alias "-latest" (stessa quota di un altro modello): ogni modello in più
        # ha la sua quota giornaliera, quindi più modelli = più annunci valutati
        ids = sorted({i for i in ids if not SKIP.search(i) and not re.search(r"(?<![a-z])pro\b|latest", i)}, key=rank, reverse=True)[:14]
        ok, busy = [], []
        for mid in ids:
            sec, err = probe(base, p["api_key"], mid)
            print(f"{name} {mid}: " + (f"risponde in {sec} s" if sec is not None else f"non disponibile ({err})"))
            if sec is not None and sec < 25:
                ok.append(mid)
            elif err == 503:  # sovraccarico del momento, non quota finita: al giudice serve lo stesso (se non risponde esce da solo)
                busy.append(mid)
        if ok:
            result["fornitori"][name] = {"scrittura": ok[:4], "giudice": (ok + busy)[:8]}
            candidates += [(rank(m), name, m) for m in ok[:4]]
    result["scrittura"] = [[n, m] for _, n, m in sorted(candidates, reverse=True)]
    if not result["scrittura"]:
        print("Nessun modello disponibile: tengo la scelta di ieri")
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("Ordine per scrivere le candidature:", ", ".join(f"{m} ({n})" for n, m in result["scrittura"][:6]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
