"""Fonti di annunci, tutte raggiungibili dal PC senza login.

Ogni funzione ritorna (lista_annunci, meta_fonte). Un annuncio è un dict con:
title, company, location, url, source, posted_at (ISO UTC), text (descrizione, può essere vuota).
La data è sempre quella dichiarata dalla fonte; le date non verificabili non entrano (vedi run_local).
"""
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, read_json  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
EPOCH0 = datetime.min.replace(tzinfo=timezone.utc)
TEXT_MAX = 15000


class Blocked(Exception):
    """La fonte ci ha chiesto di rallentare o ci ha bloccato: ci fermiamo senza insistere."""


def _open(url: str, accept: str = "*/*", timeout: int = 25) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en,it;q=0.8"})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except HTTPError as e:
            if e.code in (429, 999):
                raise Blocked(f"HTTP {e.code}")
            raise
        except (URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def get_json(url: str, timeout: int = 25):
    return json.loads(_open(url, "application/json", timeout))


def strip_html(s: str, n: int = TEXT_MAX) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S)
    s = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", ". ", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()[:n]


def parse_dt(v):
    """ISO / epoch (s o ms) / RFC822 -> datetime UTC, oppure None."""
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc)
        s = str(v).strip()
        if re.match(r"^\w{3}, \d", s):
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(s).astimezone(timezone.utc)
        d = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T", 1))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, TypeError):
        return None


def make(title, company, location, url, source, posted, text="", salary=None):
    return {
        "title": (title or "").strip(), "company": (company or "").strip(), "location": (location or "").strip(),
        "url": (url or "").strip(), "source": source,
        "posted_at": (posted or EPOCH0).astimezone(timezone.utc).isoformat(timespec="minutes"),
        "text": text, "salary": salary,
    }


# ---------------------------------------------------------------- API gratuite

def fetch_adzuna(cfg, queries, since):
    app_id, app_key = cfg.get("app_id", ""), cfg.get("app_key", "")
    if not (app_id and app_key):
        return [], {"name": "Adzuna", "ok": False, "reason": "chiavi non inserite in config.json (opzionale, gratuite)"}
    countries = ["gb", "de", "fr", "it", "es", "nl", "at", "be", "ch", "pl"]
    tasks = [(c, q) for c in countries for q in queries["en"]] + [("it", q) for q in queries["it"]]
    days = max(1, int((datetime.now(timezone.utc) - since).total_seconds() // 86400) + 1)

    def one(t):
        country, q = t
        params = {"app_id": app_id, "app_key": app_key, "results_per_page": 50, "max_days_old": days,
                  "what_or": q, "sort_by": "date", "content-type": "application/json"}
        return country, get_json(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?{urlencode(params)}")

    jobs, errors = [], 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for f in [ex.submit(one, t) for t in tasks]:
            try:
                country, data = f.result()
            except Exception:
                errors += 1
                continue
            for r in data.get("results", []):
                sal = None
                if str(r.get("salary_is_predicted")) == "0" and r.get("salary_min"):
                    sal = f"{int(r['salary_min']):,}-{int(r.get('salary_max') or r['salary_min']):,}".replace(",", ".")
                jobs.append(make(r.get("title"), (r.get("company") or {}).get("display_name"),
                                 f"{(r.get('location') or {}).get('display_name', '')} ({country.upper()})",
                                 r.get("redirect_url"), "Adzuna", parse_dt(r.get("created")),
                                 strip_html(r.get("description")), sal))
    ok = errors < len(tasks)
    return jobs, {"name": "Adzuna", "ok": ok, "reason": "" if ok else "tutte le chiamate fallite"}


def fetch_arbeitnow(since):
    jobs = []
    try:
        for page in (1, 2, 3, 4):
            for r in get_json(f"https://www.arbeitnow.com/api/job-board-api?page={page}").get("data", []):
                j = make(r.get("title"), r.get("company_name"), r.get("location"), r.get("url"),
                         "Arbeitnow", parse_dt(r.get("created_at")), strip_html(r.get("description")))
                j["criteria"] = {"employment": ", ".join(r.get("job_types") or [])}
                jobs.append(j)
    except Exception as e:
        return jobs, {"name": "Arbeitnow", "ok": bool(jobs), "reason": str(e)[:100]}
    return jobs, {"name": "Arbeitnow", "ok": True, "reason": ""}


def fetch_remotive(since):
    try:
        data = get_json("https://remotive.com/api/remote-jobs?category=sales&limit=100")
        data2 = get_json("https://remotive.com/api/remote-jobs?category=customer-support&limit=50")
    except Exception as e:
        return [], {"name": "Remotive", "ok": False, "reason": str(e)[:100]}
    jobs = []
    for r in data.get("jobs", []) + data2.get("jobs", []):
        loc = r.get("candidate_required_location") or ""
        j = make(r.get("title"), r.get("company_name"), f"Remote, {loc}" if loc else "Remote", r.get("url"),
                 "Remotive", parse_dt(r.get("publication_date")), strip_html(r.get("description")))
        j["logo"] = r.get("company_logo") or ""
        j["criteria"] = {"employment": (r.get("job_type") or "").replace("_", " ")}
        jobs.append(j)
    return jobs, {"name": "Remotive", "ok": True, "reason": ""}


def fetch_jobicy(since):
    jobs = []
    try:
        for industry in ("business", "marketing"):
            data = get_json(f"https://jobicy.com/api/v2/remote-jobs?count=50&geo=europe&industry={industry}")
            for r in data.get("jobs", []):
                geo = r.get("jobGeo") or "Europe"
                j = make(html.unescape(r.get("jobTitle") or ""), r.get("companyName"), f"Remote, {geo}",
                         r.get("url"), "Jobicy", parse_dt(r.get("pubDate")),
                         strip_html(r.get("jobDescription") or r.get("jobExcerpt")))
                jt = r.get("jobType")
                j["logo"] = r.get("companyLogo") or ""
                j["criteria"] = {"employment": ", ".join(jt) if isinstance(jt, list) else (jt or ""),
                                 "seniority": {"Junior": "Entry level", "Midweight": "Mid-Senior level", "Senior": "Director"}.get(r.get("jobLevel") or "", "")}
                jobs.append(j)
    except Exception as e:
        return jobs, {"name": "Jobicy", "ok": bool(jobs), "reason": str(e)[:100]}
    return jobs, {"name": "Jobicy", "ok": True, "reason": ""}


# ---------------------------------------------------------------- board ATS aziendali

def ats_greenhouse(slug):
    for r in get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs").get("jobs", []):
        yield make(r.get("title"), r.get("company_name") or slug, (r.get("location") or {}).get("name"),
                   r.get("absolute_url"), "Greenhouse", parse_dt(r.get("first_published")),
                   f"Lingua annuncio: {r['language']}." if r.get("language") else "")


def ats_lever(slug):
    for r in get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        yield make(r.get("text"), slug, (r.get("categories") or {}).get("location"), r.get("hostedUrl"), "Lever",
                   parse_dt(r.get("createdAt")), strip_html(r.get("descriptionPlain") or r.get("description")))


def ats_ashby(slug):
    for r in get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}").get("jobs", []):
        yield make(r.get("title"), slug, r.get("location"), r.get("jobUrl"), "Ashby", parse_dt(r.get("publishedAt")),
                   strip_html(r.get("descriptionPlain") or r.get("descriptionHtml")))


def ats_workable(slug):
    data = get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    for r in data.get("jobs", []):
        loc = ", ".join(x for x in (r.get("city"), r.get("country")) if x)
        yield make(r.get("title"), data.get("name") or slug, loc, r.get("url"), "Workable",
                   parse_dt(r.get("published_on") or r.get("created_at")), strip_html(r.get("description")))


def ats_personio(slug):
    root = ET.fromstring(_open(f"https://{slug}.jobs.personio.de/xml"))
    for p in root.iter("position"):
        g = lambda tag: (p.findtext(tag) or "").strip()  # noqa: E731
        yield make(g("name"), slug, g("office"), f"https://{slug}.jobs.personio.de/job/{g('id')}", "Personio",
                   parse_dt(g("createdAt")), "")


def ats_smartrecruiters(slug):
    seen = set()
    for q in ("sales", "business development", "customer success", "solutions"):
        data = get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&q={quote(q)}")
        for r in data.get("content", []):
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            loc = r.get("location") or {}
            full = loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), (loc.get("country") or "").upper()) if x)
            if loc.get("remote"):
                full = f"Remote, {full}"
            yield make(r.get("name"), (r.get("company") or {}).get("name") or slug, full,
                       f"https://jobs.smartrecruiters.com/{slug}/{r['id']}", "SmartRecruiters", parse_dt(r.get("releasedDate")),
                       f"Settore: {(r.get('industry') or {}).get('label', '')}. Funzione: {(r.get('function') or {}).get('label', '')}.")


def ats_recruitee(slug):
    for r in get_json(f"https://{slug}.recruitee.com/api/offers/").get("offers", []):
        yield make(r.get("title"), r.get("company_name") or slug, r.get("location") or r.get("city"), r.get("careers_url"),
                   "Recruitee", parse_dt(r.get("published_at") or r.get("created_at")),
                   strip_html((r.get("description") or "") + " " + (r.get("requirements") or "")))


def ats_teamtailor(slug):
    """Teamtailor: lo "slug" è l'indirizzo del sito carriere (es. https://careers.azienda.com o https://azienda.teamtailor.com)."""
    base = slug if slug.startswith("http") else f"https://{slug}.teamtailor.com"
    page = _open(base.rstrip("/") + "/jobs.rss", "application/rss+xml")
    for item in re.findall(r"<item>(.*?)</item>", page, re.S):
        g = lambda tag: html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", item, re.S) or [None, ""])[1])).strip()  # noqa: E731
        loc = " ".join(re.findall(r"<tt:(?:city|name|location)[^>]*>(.*?)</tt:", item)) or g("location")
        yield make(g("title"), slug, loc, g("link"), "Teamtailor", parse_dt(g("pubDate")), strip_html(g("description")))


def ats_successfactors(slug, max_pages=25, max_details=40):
    """SAP SuccessFactors (Career Site Builder), usato dalle grandi aziende: Intesa Sanpaolo, Lavazza... Lo "slug" è
    l'indirizzo del sito carriere (es. jobs.intesasanpaolo.com). L'elenco non ha date né testo: si apre la pagina solo
    degli annunci con un titolo nei ruoli della persona (al massimo max_details), per data e testo."""
    import rules
    host = slug.replace("https://", "").replace("http://", "").strip("/")
    rows, seen = [], set()
    for page in range(max_pages):
        html_ = _open(f"https://{host}/search/?q=&startrow={page * 25}", "text/html", timeout=20)
        new = 0
        for tr in re.findall(r'<tr class="data-row[^"]*"[^>]*>(.*?)</tr>', html_, re.S):
            m = re.search(r'href="(/job/[^"]+)"[^>]*class="jobTitle-link"[^>]*>(.*?)</a>|class="jobTitle-link"[^>]*href="(/job/[^"]+)"[^>]*>(.*?)</a>', tr)
            if not m:
                continue
            path, title = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            if path in seen:
                continue
            seen.add(path)
            new += 1
            loc = re.search(r'class="jobLocation"[^>]*>\s*([^<]+?)\s*<', tr)
            rows.append((html.unescape(title).strip(), path, html.unescape(loc.group(1)) if loc else ""))
        for path, tile in re.findall(r'<li class="job-tile[^"]*"[^>]*data-url="(/job/[^"]+)"(.*?)</li>', html_, re.S):
            if path in seen:
                continue
            seen.add(path)
            new += 1
            t = re.search(r'class="jobTitle-link[^"]*"[^>]*>\s*(.*?)\s*</a>', tile, re.S)
            cc = re.search(r'section-country-value">\s*([^<]+?)\s*<', tile)
            place = path.split("/")[2].split("-")[0]  # /job/<sede>-<titolo>/<id>/
            rows.append((html.unescape(t.group(1)).strip() if t else "", path, ", ".join(x for x in (place, cc.group(1) if cc else "") if x)))
        if not new:
            break
    # filtro largo (come nelle città della persona): quello vero lo applica poi la ricerca, con il giudice
    wanted = [r for r in rows if not rules.PROFILE or rules.classify(r[0], "x", "")][:max_details]

    def detail(r):
        title, path, loc = r
        try:
            d = _open(f"https://{host}{path}", "text/html", timeout=15)
        except Exception:
            return None
        body = re.search(r'class="jobdescription"[^>]*>(.*?)</span>\s*</div>', d, re.S) or re.search(r'itemprop="description"[^>]*>(.*?)</span>', d, re.S)
        when = re.search(r'datePosted"[^>]*content="([^"]+)"|itemprop="datePosted"[^>]*>([^<]+)<', d)
        posted = None
        if when:
            raw = (when.group(1) or when.group(2) or "").strip()
            posted = parse_dt(raw)
            if not posted:
                try:
                    posted = datetime.strptime(raw, "%a %b %d %H:%M:%S UTC %Y").replace(tzinfo=timezone.utc)
                except ValueError:
                    posted = None
        company = re.search(r'<meta property="og:site_name" content="([^"]+)"', d)
        city = re.search(r'addressLocality[^>]*content="([^"]+)"', d)
        if city and city.group(1).strip() and city.group(1).strip().lower() not in loc.lower():
            loc = f"{city.group(1).strip()}, {loc}" if loc else city.group(1).strip()
        return make(title, company.group(1) if company else host, loc, f"https://{host}{path}", "Sito carriere", posted,
                    strip_html(body.group(1) if body else ""))
    with ThreadPoolExecutor(max_workers=6) as ex:
        for j in ex.map(detail, wanted):
            if j:
                yield j


ATS = {"successfactors": ats_successfactors, "greenhouse": ats_greenhouse, "lever": ats_lever, "ashby": ats_ashby, "workable": ats_workable, "personio": ats_personio,
       "smartrecruiters": ats_smartrecruiters, "recruitee": ats_recruitee, "teamtailor": ats_teamtailor}


def favicon(domain: str) -> str:
    """Logo dell'azienda dal favicon del suo sito (servizio pubblico di Google)."""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128" if domain else ""


def _company(entry):
    try:
        jobs = [j for j in ATS[entry["ats"]](entry["slug"]) if j["url"]]
        for j in jobs:
            if j["company"].lower() == entry["slug"].lower():
                j["company"] = entry["name"]  # lo slug tecnico diventa il nome vero
            if entry.get("citta"):
                j["hq"] = entry["citta"]  # sede dell'azienda: vale quando la località dell'annuncio è un codice interno
            j["logo"] = favicon(entry.get("domain", ""))
        return jobs, None
    except HTTPError as e:
        return [], f"{entry['name']}: HTTP {e.code}"
    except Exception as e:  # rete, XML, JSON
        return [], f"{entry['name']}: {str(e)[:50]}"


def fetch_boards(since):
    # aziende fisse (grandi tech europee) + quelle trovate per la persona nel "mercato nascosto" (siti carriere delle sue città)
    companies, seen = [], set()
    for c in read_json(DATA / "companies.json", []) + read_json(DATA / "board_personali.json", []):
        if c.get("ats") in ATS and c.get("slug") and (c["ats"], c["slug"].lower()) not in seen:
            seen.add((c["ats"], c["slug"].lower()))
            companies.append(c)
    jobs, dead = [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res, err in ex.map(_company, companies):
            jobs += res
            if err:
                dead.append(err)
    ok = not companies or len(dead) < len(companies)
    return jobs, {"name": f"Board aziendali ({len(companies) - len(dead)}/{len(companies)} raggiunti)", "ok": ok,
                  "reason": "", "dead": dead}


# ---------------------------------------------------------------- LinkedIn (ricerca pubblica, senza login)

LI_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LI_LOCATIONS = ["Italy", "Germany", "France", "Netherlands", "Spain", "United Kingdom", "Ireland", "Switzerland", "Belgium", "Austria"]


def _li_cards(page: str):
    for block in page.split("<li>")[1:]:
        m_id = re.search(r'data-entity-urn="urn:li:jobPosting:(\d+)"', block)
        m_t = re.search(r'base-search-card__title">\s*(.*?)\s*</h3>', block, re.S)
        m_c = re.search(r'base-search-card__subtitle">.*?>\s*([^<]+?)\s*</a>|base-search-card__subtitle">\s*([^<]+?)\s*</h4>', block, re.S)
        m_l = re.search(r'job-search-card__location">\s*(.*?)\s*</span>', block, re.S)
        m_d = re.search(r'<time[^>]*datetime="([\d-]+)"', block)
        m_logo = re.search(r'data-delayed-url="(https://media\.licdn\.com/[^"]+)"', block)
        if m_id and m_t:
            company = (m_c.group(1) or m_c.group(2)) if m_c else ""
            yield (m_id.group(1), html.unescape(m_t.group(1)), html.unescape(company or ""),
                   html.unescape(m_l.group(1)) if m_l else "", m_d.group(1) if m_d else None,
                   html.unescape(m_logo.group(1)) if m_logo else "")


LI_CRITERIA = {"seniority level": "seniority", "livello di anzianità": "seniority", "employment type": "employment",
               "tipo di impiego": "employment", "job function": "function", "funzione lavorativa": "function",
               "industries": "industries", "settori": "industries"}


def _li_criteria(page: str) -> dict:
    """Riquadro strutturato della pagina pubblica: livello, tipo di contratto, funzione, settore."""
    out = {}
    for h, v in re.findall(r'job-criteria-subheader">\s*(.*?)\s*</h3>\s*<span[^>]*job-criteria-text[^>]*>\s*(.*?)\s*</span>', page, re.S):
        key = LI_CRITERIA.get(html.unescape(h).strip().lower())
        if key:
            out[key] = html.unescape(re.sub(r"\s+", " ", v)).strip()
    return out


