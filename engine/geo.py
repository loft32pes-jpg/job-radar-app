"""Posizione geografica degli annunci (per la mappa): città -> coordinate, altrimenti centro del paese.

Dati: data/cities.json (GeoNames, CC BY 4.0, città europee oltre 15.000 abitanti, nomi in più lingue)
      scripts/europe_map.json (centri dei paesi)
"""
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, ROOT, read_json  # noqa: E402

ISO_BY_IT = {
    "Italia": "IT", "Germania": "DE", "Francia": "FR", "Regno Unito": "GB", "Spagna": "ES", "Paesi Bassi": "NL",
    "Belgio": "BE", "Svizzera": "CH", "Austria": "AT", "Polonia": "PL", "Irlanda": "IE", "Portogallo": "PT",
    "Svezia": "SE", "Danimarca": "DK", "Norvegia": "NO", "Finlandia": "FI", "Repubblica Ceca": "CZ", "Ungheria": "HU",
    "Romania": "RO", "Grecia": "GR", "Lussemburgo": "LU", "Estonia": "EE", "Lettonia": "LV", "Lituania": "LT",
    "Croazia": "HR", "Slovenia": "SI", "Malta": "MT", "Cipro": "CY",
}
NOISE = {"office", "offices", "remote", "hybrid", "area", "metropolitan", "greater", "region", "province", "city", "of",
         "the", "centre", "center", "hq", "headquarters", "campus", "office based", "ibrido", "sede", "di", "de", "et"}
_cities = None
_centers = None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _load():
    global _cities, _centers
    if _cities is None:
        _cities = read_json(DATA / "cities.json", {})
        m = read_json(ROOT / "scripts" / "europe_map.json", {"countries": []})
        _centers = {c["it"]: c["c"] for c in m["countries"] if c.get("c")}


def _candidates(text: str):
    """Possibili nomi di città, dal più specifico al meno: 'IRL - Dublin' -> dublin; 'London Office' -> london."""
    out = []
    for piece in re.split(r"[,/|()–—-]", text or ""):
        words = [w for w in _norm(piece).split() if w not in NOISE]
        for n in (3, 2, 1):
            for i in range(len(words) - n + 1):
                out.append(" ".join(words[i:i + n]))
    return out


def locate(city: str, country_it: str, location_raw: str = ""):
    """Ritorna (lat, lon, 'city'|'country', nome_città_ufficiale) oppure None."""
    _load()
    cc = ISO_BY_IT.get(country_it)
    if not cc:
        return None  # "Europa (remote)" o paese non mappato: niente posizione
    table = _cities.get(cc, {})
    for text in (city, location_raw):
        for cand in _candidates(text):
            hit = table.get(cand)
            if hit:
                return hit[0], hit[1], "city", (hit[3] if len(hit) > 3 else city)
    c = _centers.get(country_it)
    return (c[0], c[1], "country", "") if c else None
