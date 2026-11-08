"""Prova: LinkedIn risponde dai server di GitHub come da un computer di casa?

Fa le stesse richieste della ricerca vera, allo stesso ritmo, ma per pochi minuti: prime pagine di ricerca in più paesi,
poi lettura degli annunci trovati. Scrive il risultato in prove/linkedin.json.
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(__file__))
from linkedin import Pacer  # noqa: E402
from sources import LI_SEARCH, _li_cards  # noqa: E402

QUERY = '"Business Development Manager" OR "Account Manager" OR "Sales Consultant" OR "Presales Engineer"'
COUNTRIES = ["Italy", "Spain", "France", "Germany", "United Kingdom", "Ireland", "Netherlands", "Belgium", "Switzerland",
             "Portugal", "Sweden", "Poland"]
MINUTES = float(os.environ.get("TEST_MINUTES", "4"))


def main():
    log = []
    pacer = Pacer(gap=0.8, log=lambda m: (log.append(m), print(m, flush=True)))
    pool = ThreadPoolExecutor(max_workers=3)
    t0 = time.time()
    urls = [f"{LI_SEARCH}?{urlencode({'keywords': QUERY, 'location': c, 'f_TPR': 'r86400', 'start': s})}"
            for s in (0, 10, 20) for c in COUNTRIES]
    ids, pages_ok = [], 0
    for page in pool.map(pacer.get, urls):
        if page is None:
            continue
        pages_ok += 1
        ids += [c[0] for c in _li_cards(page)]
    ids = list(dict.fromkeys(ids))
    t_search = time.time() - t0
    print(f"Ricerche riuscite: {pages_ok} su {len(urls)}, annunci trovati: {len(ids)}, blocchi: {pacer.blocks}", flush=True)

    deadline = t0 + MINUTES * 60

    def detail(jid):
        if pacer.dead or time.time() > deadline:
            return None
        return pacer.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}")

    read = with_text = 0
    for page in pool.map(detail, ids):
        if page is None:
            continue
        read += 1
        with_text += bool(re.search(r"show-more-less-html__markup", page))
    pool.shutdown(wait=False)
    total = time.time() - t0
    out = {"when": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "searches_ok": pages_ok, "searches": len(urls),
           "ads_found": len(ids), "ads_read": read, "ads_with_text": with_text, "blocks_429": pacer.blocks,
           "stopped_by_linkedin": pacer.dead, "seconds_search": round(t_search), "seconds_total": round(total),
           "reads_per_minute": round(read / max(1, total - t_search) * 60), "final_gap": round(pacer.gap, 2), "log": log[-20:]}
    print(json.dumps(out, indent=1), flush=True)
    path = Path(__file__).resolve().parent.parent / "prove" / "linkedin.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
