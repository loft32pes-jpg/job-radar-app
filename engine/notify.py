"""Notifica sul telefono a fine ricerca automatica. Disattivata finché non si compila la sezione "notify" di config.json.

Provider (tutti con la sola libreria standard):
  "callmebot"  WhatsApp gratuito. Serve un'attivazione una tantum: vedi LEGGIMI.txt.
  "telegram"   bot Telegram gratuito (token del bot + chat id).
  "twilio"     SMS a pagamento (account SID, auth token, numero mittente Twilio).
"""
import base64
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))


def build_message(summary: dict) -> str:
    lines = [f"Job Radar: {summary['added']} nuovi annunci (score max {summary['best']})."]
    for j in summary["top"][:3]:
        where = j.get("city") or j.get("country") or ""
        lines.append(f"- {j['title'][:60]}, {j['company'][:30]} ({where}) {j['score']}")
    lines.append("Apri Job Radar.html sul PC per i dettagli.")
    return "\n".join(lines)


def send(cfg: dict, text: str):
    """Ritorna (ok, dettaglio). Non solleva eccezioni."""
    provider = (cfg or {}).get("provider", "")
    try:
        if provider == "callmebot":
            c = cfg.get("callmebot", {})
            if not (c.get("phone") and c.get("apikey")):
                return False, "callmebot: telefono o apikey mancanti in config.json"
            url = "https://api.callmebot.com/whatsapp.php?" + urlencode(
                {"phone": c["phone"], "text": text, "apikey": c["apikey"]}, quote_via=quote)
            with urlopen(Request(url, headers={"User-Agent": "job-radar"}), timeout=30) as r:
                return 200 <= r.status < 300, f"callmebot: HTTP {r.status}"
        if provider == "telegram":
            c = cfg.get("telegram", {})
            if not (c.get("token") and c.get("chat_id")):
                return False, "telegram: token o chat_id mancanti in config.json"
            body = urlencode({"chat_id": c["chat_id"], "text": text}).encode()
            with urlopen(Request(f"https://api.telegram.org/bot{c['token']}/sendMessage", data=body), timeout=30) as r:
                return 200 <= r.status < 300, f"telegram: HTTP {r.status}"
        if provider == "twilio":
            c = cfg.get("twilio", {})
            if not all(c.get(k) for k in ("account_sid", "auth_token", "from", "to")):
                return False, "twilio: dati mancanti in config.json"
            body = urlencode({"From": c["from"], "To": c["to"], "Body": text}).encode()
            auth = base64.b64encode(f"{c['account_sid']}:{c['auth_token']}".encode()).decode()
            req = Request(f"https://api.twilio.com/2010-04-01/Accounts/{c['account_sid']}/Messages.json", data=body,
                          headers={"Authorization": f"Basic {auth}"})
            with urlopen(req, timeout=30) as r:
                return 200 <= r.status < 300, f"twilio: HTTP {r.status}"
        return False, "notifiche non configurate"
    except HTTPError as e:
        return False, f"{provider}: HTTP {e.code}"
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return False, f"{provider}: {str(e)[:60]}"
