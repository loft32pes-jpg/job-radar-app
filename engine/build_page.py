"""Genera "Job Radar.html" (file unico, si apre con doppio clic) dagli archivi degli ultimi 14 giorni."""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
import tracker  # noqa: E402
from common import ARCHIVE, DATA, ROOT, normalize_url, read_json  # noqa: E402

SHOW_DAYS = 14
KEEP_DAYS = 30
REQUIRED = ("title", "company", "url")
OUTPUT = ROOT / "Job Radar.html"


def load_days():
    today = date.today()
    days = []
    for f in sorted(ARCHIVE.glob("????-??-??.json"), reverse=True):
        try:
            d = date.fromisoformat(f.stem)
        except ValueError:
            continue
        if (today - d).days > KEEP_DAYS:
            f.unlink()
            continue
        data = read_json(f, None)
        if not data:
            continue
        data["jobs"] = [j for j in data.get("jobs", []) if all(j.get(k) for k in REQUIRED)]
        for j in data["jobs"]:
            j["_k"] = normalize_url(j["url"])  # stessa chiave usata da preferiti e scartati
        data.setdefault("date", f.stem)
        if (today - d).days < SHOW_DAYS:
            days.append(data)
    return days


def main():
    days = load_days()
    template = (ROOT / "scripts" / "template.html").read_text(encoding="utf-8")
    europe = read_json(ROOT / "scripts" / "europe_map.json", None)
    cv = read_json(ROOT / "profilo" / "cv_profile.json", None)  # solo il profilo sintetico: il testo del CV non entra nella pagina
    deep_on = bool(read_json(ROOT / "config.json", {}).get("anthropic", {}).get("api_key"))
    hub = read_json(ROOT / "profilo" / "hub" / "index.json", {"active": None, "items": []})
    hub["items"] = [{k: v for k, v in it.items() if k != "file"} for it in hub["items"]]
    import searchprofile
    prof = searchprofile.load()
    if prof:
        families = [{"id": c["id"], "label": c["name"]} for c in prof["clusters"] if c.get("on", True)]
        if prof.get("title_words"):
            families.append({"id": "cx", "label": "Altri ruoli possibili"})
    else:
        families = [{"id": i, "label": lab} for i, lab in (("tech_sales", "Technical Sales"), ("bd", "Business Development"),
                                                             ("sales", "Sales B2B"), ("change", "Change Management"), ("affini", "Ruoli affini"))]
    payload = json.dumps({"days": days, "map": europe, "cv": cv, "hub": hub, "deep": deep_on, "profile": prof, "families": families,
                          "run": read_json(DATA / "ultima_ricerca.json", None), "tracker": tracker.public(),
                          "i18n": read_json(ROOT / "scripts" / "i18n_en.json", {"exact": {}, "rx": [], "sub": []}),
                          "companies": [{"n": c.get("name", ""), "d": c.get("domain", "")} for c in read_json(DATA / "companies.json", [])]}, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/").replace("<!--", "<\\!--")
    OUTPUT.write_text(template.replace("__DATA__", payload), encoding="utf-8")
    print(f"Pagina generata: {len(days)} giorni, {sum(len(d['jobs']) for d in days)} annunci")
    return OUTPUT


if __name__ == "__main__":
    main()
