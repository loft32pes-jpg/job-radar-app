"""Utilità condivise: percorsi, normalizzazione URL, lettura/scrittura JSON."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ARCHIVE = DATA / "archive"
TMP = DATA / "tmp"
DOCS = ROOT / "docs"

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "gh_jid_src", "source", "src", "ref", "refid", "trackingid",
    "trk", "lever-source", "lever-origin", "rx_c", "rx_campaign", "rx_ch",
    "rx_group", "rx_job", "rx_medium", "rx_r", "rx_source", "rx_ts", "rx_vp",
}


def normalize_url(url: str) -> str:
    """Forma canonica per il dedup: niente fragment, niente parametri di tracking."""
    p = urlparse(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING_PARAMS]
    path = re.sub(r"/+$", "", p.path)
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", urlencode(query), ""))


def read_json(path: Path, default):
    if Path(path).name == "config.json" and os.environ.get("JR_CONFIG"):
        return json.loads(os.environ["JR_CONFIG"])  # online la configurazione (chiavi comprese) arriva dall'ambiente
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
