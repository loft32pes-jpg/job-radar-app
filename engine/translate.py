"""Traduzione in italiano di titoli e riassunti degli annunci in lingua locale.

Usa l'endpoint pubblico di Google Traduttore (nessuna chiave). Se non risponde si tiene il testo originale:
la traduzione è un aiuto alla lettura, mai un requisito per mostrare l'annuncio.
"""
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_last = 0.0
_failures = 0


def to_italian(text: str):
    """Ritorna il testo tradotto, oppure None se la traduzione non è disponibile."""
    global _last, _failures
    text = (text or "").strip()
    if not text or _failures >= 5:  # servizio giù: smettiamo di provarci per questa ricerca
        return None
    wait = 0.25 - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.time()
    url = "https://translate.googleapis.com/translate_a/single?" + urlencode(
        {"client": "gtx", "sl": "auto", "tl": "it", "dt": "t", "q": text[:1500]})
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        out = "".join(part[0] for part in data[0] if part and part[0]).strip()
        return out or None
    except Exception:
        _failures += 1
        return None
