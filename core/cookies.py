import json
from utils.logger import get_logger
log = get_logger()

def parse_cookies(text, domain):
    """Kembalikan list cookie utk Playwright context.add_cookies().
    Mendukung:
    1) JSON array (ekspor extension 'EditThisCookie' / 'Cookie-Editor')
    2) String 'name=value; name2=value2' (dari DevTools document.cookie)
    domain contoh: '.shopee.co.id'"""
    text = text.strip()
    out = []
    if text.startswith("[") or text.startswith("{"):
        data = json.loads(text)
        if isinstance(data, dict):
            data = [data]
        for c in data:
            name = c.get("name"); val = c.get("value")
            if not name:
                continue
            out.append({
                "name": name,
                "value": val or "",
                "domain": c.get("domain") or domain,
                "path": c.get("path") or "/",
                "httpOnly": bool(c.get("httpOnly", False)),
                "secure": bool(c.get("secure", True)),
            })
    else:
        for part in text.split(";"):
            if "=" not in part:
                continue
            name, _, val = part.strip().partition("=")
            if not name:
                continue
            out.append({
                "name": name.strip(),
                "value": val.strip(),
                "domain": domain,
                "path": "/",
                "secure": True,
            })
    log.info(f"parsed {len(out)} cookies utk {domain}")
    return out
