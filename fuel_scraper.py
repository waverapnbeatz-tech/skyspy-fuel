#!/usr/bin/env python3
"""SKYSPY FUEL: cautious HTML extraction, no station API required.

Only public pages; never bypass logins/captcha/robots rules. On a parse error
export null instead of guessing. Official ONO site does not publish report dates.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

TZ = ZoneInfo("Europe/Prague")
USER_AGENT = "SKYSPY-FUEL/0.1 (personal Czech fuel-price dashboard; 1 fetch/hour)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
DATE_PATTERN = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
PRICE_PATTERN = re.compile(r"(?<!\d)(\d{2})[,.](\d{2})(?!\d)")
FUEL_LABELS = ("Benzín", "Nafta", "LPG", "CNG", "Premium benzín", "Premium diesel")
VALID_STATES = {"fresh", "stale", "unknown_date", "missing", "error"}


def validate_price(text: str) -> float:
    m = PRICE_PATTERN.search(text)
    if not m:
        raise ValueError(f"Chybí cena: {text[:80]!r}")
    p = Decimal(m.group(1) + "." + m.group(2))
    if not Decimal("15.00") <= p <= Decimal("99.99"):
        raise ValueError(f"Cena mimo očekávané rozmezí: {p}")
    return float(p)


def reported_date(text: str, now: datetime) -> date | None:
    t = text.casefold()
    if "včera" in t or "vcera" in t:
        return now.date() - timedelta(days=1)
    if re.search(r"\bdnes\b", t):
        return now.date()
    relative = re.search(r"\b(\d{1,3})\s*dn[ií]\b", t)
    if relative:
        return now.date() - timedelta(days=int(relative.group(1)))
    m = DATE_PATTERN.search(text)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def freshness(d: date | None, now: datetime) -> str:
    if d is None:
        return "unknown_date"
    age = (now.date() - d).days
    return "fresh" if 0 <= age <= 3 else "stale"


def record(price: float | None = None, d: date | None = None, now: datetime | None = None, status: str | None = None) -> dict:
    now = now or datetime.now(TZ)
    return {"price": price, "reported_date": d.isoformat() if d else None,
            "status": status or (freshness(d, now) if price is not None else "missing")}


def text_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for el in soup(["script", "style", "noscript", "nav", "footer"]):
        el.decompose()
    return [s.strip() for s in soup.get_text("\n", strip=True).splitlines() if s.strip()]


def normalized(text: str) -> str:
    """Case/diacritics/punctuation insensitive comparison for Czech station addresses."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                    if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def fuel_label(line: str) -> str | None:
    """Allow both a heading (Benzín) and an inline label (Benzín 44,50)."""
    n = normalized(line)
    for label in ("Premium benzín", "Premium diesel", "Benzín", "Nafta", "LPG", "CNG"):
        ln = normalized(label)
        if n == ln or n.startswith(ln + " "):
            return label
    return None


def fuel_record_from_lines(lines: list[str], label: str, now: datetime) -> dict:
    positions = [i for i, item in enumerate(lines) if fuel_label(item) == label]
    if len(positions) != 1:
        raise ValueError(f"Sekce {label} nenalezena jednoznačně (nalezeno {len(positions)})")
    idx = positions[0]
    end = next((j for j in range(idx + 1, min(idx + 9, len(lines)))
                if fuel_label(lines[j])), min(idx + 9, len(lines)))
    area = " ".join(lines[idx:end])
    try:
        price = validate_price(area)
    except ValueError:
        return record()
    # Datums may be explicit or relative. No date => unknown_date, never fresh.
    d = reported_date(area, now)
    return record(price, d, now)


def parse_mbenzin(html: str, now: datetime, expected_address: str) -> tuple[dict, dict]:
    lines = text_lines(html)
    first_nearby = next((i for i, s in enumerate(lines) if normalized(s) ==
                         "cerpaci stanice v okoli"), len(lines))
    own = lines[:first_nearby]
    first_fuel = next((i for i, s in enumerate(own) if fuel_label(s) == "Benzín"), len(own))
    # Check address in the station header, not in nearby station recommendations.
    header = normalized(" ".join(own[:first_fuel]))
    if normalized(expected_address) not in header:
        raise ValueError(f"Nesedí adresa stanice v hlavičce: {expected_address}")
    return (fuel_record_from_lines(own, "Benzín", now),
            fuel_record_from_lines(own, "Nafta", now))


def parse_mbenzin_listing(html: str, now: datetime, address: str, station_name: str) -> tuple[dict, dict]:
    """Safely extract one exact station from the city list, never its neighbor."""
    lines = text_lines(html)
    addr = normalized(address)
    name = normalized(station_name)
    candidates = [i for i, s in enumerate(lines)
                  if normalized(s) == addr and name in [normalized(v) for v in lines[max(0, i-4):i]]]
    if not candidates:
        raise ValueError(f"Stanice {station_name}, {address} není v přehledu jednoznačně nalezena")
    parsed = []
    for i in candidates:
        # Each city's row always ends at 'Premium diesel'. Do not bleed into another row.
        end = next((j + 1 for j in range(i+1, min(i+46, len(lines)))
                    if fuel_label(lines[j]) == "Premium diesel"), None)
        if end is None:
            continue
        block = lines[i+1:end]
        try:
            b = fuel_record_from_lines(block, "Benzín", now)
            d = fuel_record_from_lines(block, "Nafta", now)
            if b["price"] is not None or d["price"] is not None:
                parsed.append((b, d))
        except ValueError:
            continue
    if not parsed:
        raise ValueError(f"Stanice {station_name}, {address}: ceny v přehledu nenalezeny")
    # Repeated blocks are acceptable only if they agree (not mixed station prices).
    distinct = {(x["price"], y["price"]) for x,y in parsed}
    if len(distinct) != 1:
        raise ValueError("Rozdílné ceny stejné stanice ve více sekcích přehledu")
    return parsed[0]


def parse_ono(html: str, now: datetime) -> tuple[dict, dict]:
    soup = BeautifulSoup(html, "html.parser")
    for el in soup(["script", "style", "noscript"]):
        el.decompose()
    parts = [re.sub(r"\s+", " ", s.strip()) for s in soup.stripped_strings if s.strip()]
    if "cvikov" not in " ".join(parts).casefold():
        raise ValueError("Stránka není ceník Cvikov")

    def fuel(label: str) -> dict:
        positions = [i for i, s in enumerate(parts) if s.upper() == label]
        if len(positions) != 1:
            raise ValueError(f"Štítek {label}: {len(positions)} výskytů")
        i = positions[0]
        subsequent = parts[i + 1:i + 5]
        if not subsequent:
            return record()
        # ONO writes 42<sup>90</sup>, soup.stripped_strings => "42", "90".
        if re.fullmatch(r"\d{2,3}", subsequent[0]) and len(subsequent) >= 2 and re.fullmatch(r"\d{2}", subsequent[1]):
            value = subsequent[0] + "," + subsequent[1]
        else:
            value = subsequent[0]
        try:
            # Official station page gives no date. Do NOT claim a fresh report.
            return record(validate_price(value), None, now)
        except ValueError:
            return record()

    return fuel("NATURAL 95"), fuel("DIESEL")


def robots_allowed(session: requests.Session, url: str) -> bool:
    u = urlparse(url)
    robots_url = f"{u.scheme}://{u.netloc}/robots.txt"
    resp = session.get(robots_url, headers=HEADERS, timeout=12)
    if resp.status_code in (404, 410):
        return True
    if resp.status_code != 200:
        raise RuntimeError(f"robots.txt: HTTP {resp.status_code}; čtení pozastaveno")
    robot = RobotFileParser()
    robot.parse(resp.text.splitlines())
    return robot.can_fetch(USER_AGENT, url)


def fetch_station(station: dict, now: datetime, session: requests.Session) -> dict:
    url = station["url"]
    result = {"id": station["id"], "name": station["name"],
              "location": station["location"], "source_url": url,
              "source_kind": station["source_kind"],
              "checked_at": None, "natural95": record(status="error"),
              "diesel": record(status="error"), "error": None}
    try:
        if not robots_allowed(session, url):
            raise RuntimeError("robots.txt nepovoluje strojové čtení")
        response = session.get(url, headers=HEADERS, timeout=(10, 20))
        response.raise_for_status()
        if len(response.content) > 2_000_000:
            raise ValueError("Příliš velká odpověď")
        if station["source_kind"] == "mbenzin":
            try:
                n95, diesel = parse_mbenzin(response.text, now, station["expected_address"])
                if n95["price"] is None and diesel["price"] is None:
                    raise ValueError("Detail neobsahuje ceny")
            except ValueError as detail_error:
                # Use the precise city-list entry only; never scrape a neighboring station.
                fallback_url = station.get("fallback_url")
                if not fallback_url or not station.get("listing_address") or not station.get("listing_name"):
                    raise
                if not robots_allowed(session, fallback_url):
                    raise RuntimeError("robots.txt nepovoluje přehled stanic") from detail_error
                listing = session.get(fallback_url, headers=HEADERS, timeout=(10, 20))
                listing.raise_for_status()
                if len(listing.content) > 2_000_000:
                    raise ValueError("Příliš velká odpověď přehledu") from detail_error
                try:
                    n95, diesel = parse_mbenzin_listing(
                        listing.text, now, station["listing_address"], station["listing_name"])
                except ValueError as listing_error:
                    raise ValueError(f"Detail: {detail_error}; přehled: {listing_error}") from listing_error
        elif station["source_kind"] == "ono":
            n95, diesel = parse_ono(response.text, now)
        else:
            raise ValueError("Neznámý typ zdroje")
        if n95["price"] is None and diesel["price"] is None:
            raise ValueError("Zdroj nevrátil žádnou platnou cenu")
        result.update(natural95=n95, diesel=diesel, checked_at=now.isoformat())
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        result["error"] = str(exc)[:240]
    return result


def run(config: Path, output: Path, *, now: datetime | None = None, session: requests.Session | None = None) -> dict:
    now = now or datetime.now(TZ)
    configs = json.loads(config.read_text(encoding="utf-8"))["stations"]
    with requests.Session() if session is None else session as s:
        stations = [fetch_station(item, now, s) for item in configs]
    doc = {"schema_version": 1, "generated_at": now.isoformat(),
           "timezone": "Europe/Prague", "unit": "Kč/l", "stations": stations}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Read SKYSPY fuel prices from public HTML pages")
    p.add_argument("--config", type=Path, default=Path("config/stations.json"))
    p.add_argument("--output", type=Path, default=Path("docs/prices.json"))
    args = p.parse_args()
    data = run(args.config, args.output)
    for item in data["stations"]:
        print(item["name"], "N95", item["natural95"], "Nafta", item["diesel"], item["error"] or "OK")
