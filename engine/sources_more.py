"""Altre fonti: EURES (portale ufficiale UE), board remote (RemoteOK, Himalayas, We Work Remotely), Jooble (con chiave).

Stesse convenzioni di sources.py: ogni funzione ritorna (annunci, meta_fonte).
"""
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))
import rules  # noqa: E402
from sources import UA, _open, favicon, get_json, make, parse_dt, strip_html  # noqa: E402

ISO2_EN = {  # codice paese -> nome inglese riconosciuto da rules.infer_country
    "IT": "Italy", "DE": "Germany", "FR": "France", "GB": "United Kingdom", "UK": "United Kingdom", "ES": "Spain",
    "NL": "Netherlands", "BE": "Belgium", "CH": "Switzerland", "AT": "Austria", "PL": "Poland", "IE": "Ireland",
    "PT": "Portugal", "SE": "Sweden", "DK": "Denmark", "NO": "Norway", "FI": "Finland", "CZ": "Czech Republic",
    "HU": "Hungary", "RO": "Romania", "GR": "Greece", "LU": "Luxembourg", "EE": "Estonia", "LV": "Latvia",
    "LT": "Lithuania", "HR": "Croatia", "SI": "Slovenia", "MT": "Malta", "CY": "Cyprus",
}
EURES_COUNTRIES = ["it", "fr", "nl", "ie", "be", "at", "lu", "pt", "pl", "se", "dk", "fi", "cz", "hu", "ro", "gr",
                   "ee", "lv", "lt", "hr", "si", "mt", "cy", "no"]
EURES_KEYWORDS = ["sales engineer", "business development", "account executive", "account manager", "customer success",
                  "change management"]


def fetch_eures(since, keywords=None):
    """EURES: portale ufficiale UE della mobilità professionale. API JSON pubblica del sito, filtro 'ultime 24h'."""
    period = "LAST_DAY" if (datetime.now(timezone.utc) - since) <= timedelta(hours=26) else "LAST_WEEK"

    def one(args):
        cc, kw = args
        body = json.dumps({
            "resultsPerPage": 50, "page": 1, "sortSearch": "MOST_RECENT", "publicationPeriod": period,
            "keywords": [{"keyword": kw, "specificSearchCode": "EVERYWHERE"}], "locationCodes": [cc],
            "requiredExperienceCodes": [], "positionScheduleCodes": [], "sectorCodes": [],
            "educationAndQualificationLevelCodes": [], "occupationUris": [], "skillUris": [], "requiredLanguages": [],
        }).encode()
        req = Request("https://europa.eu/eures/api/jv-searchengine/public/jv-search/search", data=body,
                      headers={"User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json"})
        with urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    tasks = [(c, k) for c in EURES_COUNTRIES for k in (keywords or EURES_KEYWORDS)]
    jobs, errors, seen = [], 0, set()
    with ThreadPoolExecutor(max_workers=6) as ex:
        for f in [ex.submit(one, t) for t in tasks]:
            try:
                data = f.result()
            except Exception:
                errors += 1
                continue
            for r in data.get("jvs", []):
                if r["id"] in seen or not (r.get("employer") or {}).get("name"):
                    continue  # senza nome dell'azienda non è un annuncio utilizzabile
                seen.add(r["id"])
                # la lingua dell'annuncio la valuta rules.evaluate: quelli in lingua locale entrano solo se citano l'inglese
                codes = list((r.get("locationMap") or {}).keys())
                loc = ", ".join(ISO2_EN.get(c.upper(), c) for c in codes)
                lang = (r.get("availableLanguages") or ["en"])[0]
                j = make(r.get("title"), r["employer"]["name"], loc,
                         f"https://europa.eu/eures/portal/jv-se/jv-details/{r['id']}?lang={lang}", "EURES",
                         parse_dt(r.get("creationDate")), strip_html(r.get("description")))
                site = re.sub(r"^https?://(www\.)?", "", (r["employer"].get("website") or "")).split("/")[0]
                j["logo"] = favicon(site)
                j["criteria"] = {"employment": ", ".join(r.get("positionScheduleCodes") or []).replace("fulltime", "Full-time").replace("parttime", "Part-time")}
                jobs.append(j)
    ok = errors < len(tasks)
    return jobs, {"name": "EURES (portale UE)", "ok": ok, "reason": "" if ok else "portale non raggiungibile"}


def fetch_remote_boards(since):
    """RemoteOK, Himalayas, We Work Remotely. Tengono solo annunci aperti a chi lavora dall'Europa."""
    jobs, problems = [], []
    try:  # RemoteOK chiede di citare la fonte: il link dell'annuncio rimanda al loro sito
        for r in get_json("https://remoteok.com/api")[1:]:
            loc = (r.get("location") or "").strip()
            if loc and rules.in_europe(loc):
                j = make(r.get("position"), r.get("company"), f"Remote, {loc}", r.get("url"), "RemoteOK",
                         parse_dt(r.get("date")), strip_html(r.get("description")))
                j["logo"] = r.get("company_logo") or r.get("logo") or ""
                jobs.append(j)
    except Exception as e:
        problems.append(f"RemoteOK: {str(e)[:40]}")
    try:
        for r in get_json("https://himalayas.app/jobs/api?limit=100").get("jobs", []):
            restr = r.get("locationRestrictions") or []
            if isinstance(restr, str):
                restr = [restr]
            if restr and not any(rules.infer_country(x) or re.search(r"europe|emea|\beu\b", x, re.I) for x in restr):
                continue  # aperto solo a paesi extra-Europa
            loc = "Remote, " + (", ".join(restr) if restr else "Europe")
            j = make(r.get("title"), r.get("companyName"), loc, r.get("applicationLink") or r.get("guid"),
                     "Himalayas", parse_dt(r.get("pubDate")), strip_html(r.get("description") or r.get("excerpt")))
            sen = r.get("seniority") or []
            j["logo"] = r.get("companyLogo") or ""
            j["criteria"] = {"employment": r.get("employmentType") or "",
                             "seniority": {"Entry-level": "Entry level", "Junior": "Entry level", "Mid-level": "Mid-Senior level",
                                           "Senior": "Director"}.get(sen[0] if isinstance(sen, list) and sen else "", "")}
            jobs.append(j)
    except Exception as e:
        problems.append(f"Himalayas: {str(e)[:40]}")
    for cat in ("remote-sales-and-marketing-jobs", "remote-customer-support-jobs", "remote-management-and-finance-jobs"):
        try:
            root = ET.fromstring(_open(f"https://weworkremotely.com/categories/{cat}.rss"))
        except Exception as e:
            problems.append(f"We Work Remotely: {str(e)[:40]}")
            continue
        for it in root.iter("item"):
            region = f"{it.findtext('region') or ''} {it.findtext('country') or ''}".strip()
            if not re.search(r"anywhere|europe|emea|worldwide|\beu\b", region, re.I) and not rules.infer_country(region):
                continue
            full = it.findtext("title") or ""
            company, sep, title = full.partition(": ")
            j = make(title if sep else full, company if sep else "", f"Remote, {region or 'Worldwide'}",
                     it.findtext("link"), "We Work Remotely", parse_dt(it.findtext("pubDate")),
                     strip_html(it.findtext("description")))
            media = it.find("{http://search.yahoo.com/mrss/}content")
            j["logo"] = media.get("url", "") if media is not None else ""
            j["criteria"] = {"employment": it.findtext("type") or ""}
            jobs.append(j)
    ok = len(problems) < 3
    return jobs, {"name": "Board remote (RemoteOK, Himalayas, WWR)", "ok": ok, "reason": "; ".join(problems)}


def fetch_jooble(cfg, queries, since):
    """Jooble aggrega molti portali. Richiede una chiave gratuita (jooble.org/api/about), da mettere in config.json."""
    key = cfg.get("api_key", "")
    if not key:
        return [], {"name": "Jooble", "ok": False, "reason": "chiave non inserita in config.json (opzionale, gratuita)"}
    # La chiave gratuita interroga l'indice internazionale (jooble.org): funziona per paese, non per città,
    # e i siti nazionali (it.jooble.org ecc.) rispondono 403. Quindi: una ricerca per paese, più pagine se servono.
    locations = ["Italy", "United Kingdom", "Germany", "France", "Netherlands", "Spain", "Ireland", "Switzerland",
                 "Belgium", "Austria", "Sweden", "Denmark", "Poland", "Portugal"]
    since_day = since.strftime("%Y-%m-%d")
    jobs, errors, total, seen = [], 0, 0, set()
    for loc in locations:
        for kw in queries["li"][:4]:
            for page in (1, 2, 3):
                total += 1
                body = json.dumps({"keywords": kw, "location": loc, "page": page, "datecreatedfrom": since_day}).encode()
                req = Request(f"https://jooble.org/api/{key}", data=body,
                              headers={"Content-Type": "application/json", "User-Agent": UA})
                try:
                    with urlopen(req, timeout=30) as r:
                        data = json.loads(r.read().decode("utf-8", "replace"))
                except Exception:
                    errors += 1
                    break
                rows = data.get("jobs", [])
                for r in rows:
                    if r.get("id") in seen:
                        continue
                    seen.add(r.get("id"))
                    place = r.get("location") or ""
                    if not rules.infer_country(place):
                        place = f"{place}, {loc}".strip(", ")  # spesso manca il paese: aggiungiamo quello cercato
                    j = make(r.get("title"), r.get("company"), place, r.get("link"), "Jooble",
                             parse_dt(r.get("updated")), strip_html(r.get("snippet")), r.get("salary") or None)
                    j["criteria"] = {"employment": r.get("type") or ""}
                    jobs.append(j)
                time.sleep(0.4)
                if not rows or (data.get("totalCount") or 0) <= page * len(rows):
                    break  # non ci sono altre pagine
    ok = errors < total
    return jobs, {"name": "Jooble", "ok": ok, "reason": "" if ok else "chiave non valida o servizio non raggiungibile"}


TALENT_HOST = {"GB": "uk"}  # sottodominio di Talent.com per paese (di norma il codice in minuscolo)


def _talent_page(host, params):
    """Una pagina di risultati di Talent.com: gli annunci stanno nei dati della pagina (Next.js), testo compreso."""
    from urllib.parse import urlencode
    page = _open(f"https://{host}.talent.com/jobs?{urlencode(params)}", "text/html", timeout=30)
    flight = "".join(json.loads('"' + c + '"') for c in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', page, re.S))
    i = flight.find('{"jobs":[')
    if i < 0:
        return []
    jobs, _ = json.JSONDecoder().raw_decode(flight, i + 8)
    for j in jobs:  # il testo completo è un blocco a parte ("$2c" -> "2c:T870,<p>...")
        ref = str(j.get("enrich_jobdesc_html") or "")
        if ref.startswith("$"):
            m = re.search(re.escape(ref[1:]) + r":T([0-9a-f]+),", flight)
            j["_html"] = flight[m.end():m.end() + int(m.group(1), 16)] if m else ""
    return jobs


def fetch_talent(places, terms, since):
    """Talent.com (aggregatore con molti portali nazionali): annunci vicino alle città scelte dalla persona.

    places: [{"name", "cc", "lat", "lon"}]; terms: titoli da cercare uno per uno. Ritorna annunci con "near" = città cercata.
    """
    if not places or not terms:
        return [], {"name": "Talent.com", "ok": True, "reason": ""}
    days = max(1, int((datetime.now(timezone.utc) - since).total_seconds() // 86400))
    window = "1" if days <= 1 else "3" if days <= 3 else "7" if days <= 7 else "30"
    tasks = [(p, t) for p in places for t in terms]
    jobs, seen, errors = [], set(), 0

    def one(task):
        p, term = task
        host = TALENT_HOST.get(p["cc"], p["cc"].lower())
        out = []
        for n in (1, 2, 3, 4):
            got = _talent_page(host, {"k": term, "l": p["name"], "date": window, "p": n})
            out += got
            time.sleep(0.5)
            if len(got) < 12:
                break  # non ci sono altre pagine
        return p, out

    with ThreadPoolExecutor(max_workers=2) as ex:
        for f in [ex.submit(one, t) for t in tasks]:
            try:
                p, rows = f.result()
            except Exception:
                errors += 1
                continue
            for r in rows:
                if r.get("id") in seen:
                    continue
                seen.add(r.get("id"))
                country = ISO2_EN.get(str(r.get("enrich_geo_country") or p["cc"]).upper(), ISO2_EN.get(p["cc"], ""))
                town = r.get("enrich_geo_city") or (r.get("source_location") or "").split(",")[0]
                text = strip_html(r.get("_html") or "") or (r.get("source_jobdesc_text") or "")
                url = r.get("source_link") or f"https://{TALENT_HOST.get(p['cc'], p['cc'].lower())}.talent.com/view?id={r.get('id')}"
                j = make(r.get("source_title"), r.get("enrich_company_name") or r.get("system_company_name"),
                         f"{town}, {country}".strip(", "), url, "Talent.com", parse_dt(r.get("system_date_found")), text)
                j["near"] = p["name"]
                try:
                    j["lat"], j["lon"] = float(r["enrich_geo_lat"]), float(r["enrich_geo_lon"])
                except (KeyError, TypeError, ValueError):
                    pass
                jobs.append(j)
    ok = errors < len(tasks)
    return jobs, {"name": "Talent.com", "ok": ok, "reason": "" if ok else "non raggiungibile in questo momento"}
