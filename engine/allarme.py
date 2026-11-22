"""Avviso a chi amministra quando le ricerche di una persona falliscono più volte di fila.

Usa gli avvisi sul telefono (ntfy) del profilo di chi amministra: basta che in Job Radar abbia attivato «Avvisi sul
telefono». Nel registro pubblico non si stampa né il canale né il nome della persona.

Uso (nel workflow, solo quando la ricerca è fallita): python engine/allarme.py <id persona>   (dalla cartella dati)
"""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

AVVISA_A = (2, 4, 8, 16)  # dopo quante ricerche fallite di fila: non si riempie il telefono a ogni giro


def main():
    uid = sys.argv[1]
    base = Path("utenti")
    try:
        st = json.loads((base / uid / "stato.json").read_text(encoding="utf-8"))
        index = json.loads((base / "index.json").read_text(encoding="utf-8"))
    except Exception:
        return 0
    fails = int(st.get("fails") or 0)
    if fails not in AVVISA_A:
        print("Ricerche fallite di fila:", fails)
        return 0
    name = (index.get(uid) or {}).get("name") or "una persona"
    sent = 0
    for aid, u in index.items():
        if not u.get("admin"):
            continue
        try:
            topic = (json.loads((base / aid / "profilo.json").read_text(encoding="utf-8")).get("notify") or {}).get("topic")
        except Exception:
            topic = ""
        if not topic:
            continue
        text = (f"Le ultime {fails} ricerche di {name} non sono arrivate in fondo: l'app non si aggiorna. "
                f"Errore: {str(st.get('detail') or st.get('error') or '')[:200]}")
        try:
            req = Request("https://ntfy.sh/" + topic, data=text.encode("utf-8"), method="POST",
                          headers={"Title": "Job Radar: ricerche ferme", "Tags": "warning", "Priority": "high"})
            urlopen(req, timeout=15).close()
            sent += 1
        except Exception:
            pass
    print("Ricerche fallite di fila:", fails, "- avvisi inviati:", sent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
