"""Koszt i saldo Ollama Cloud.

Czyta GET /api/usage i GET /api/balance. Klucz API pochodzi ze zmiennej
OLLAMA_API_KEY, z pliku podanego w --key-file albo z ~/.config/ollama/api-key.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://ollama.com"
TIMEOUT = 20
DEFAULT_KEY_FILE = Path.home() / ".config" / "ollama" / "api-key"
__version__ = "1.0.0"


class ApiError(Exception):
    def __init__(self, status, detail="", retry_after=None):
        super().__init__(f"HTTP {status}: {detail}" if status else detail)
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


def read_key(args):
    key = (os.environ.get("OLLAMA_API_KEY") or "").strip()
    if key:
        return key, "OLLAMA_API_KEY"
    path = Path(args.key_file).expanduser() if args.key_file else DEFAULT_KEY_FILE
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line, str(path)
    return "", None


def get_json(path, key):
    req = urllib.request.Request(
        BASE + path,
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "ollama-cost/" + __version__,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            body = json.loads(body).get("error", body)
        except Exception:
            pass
        raise ApiError(exc.code, str(body)[:300], exc.headers.get("Retry-After"))
    except urllib.error.URLError as exc:
        raise ApiError(0, str(exc.reason))
    except json.JSONDecodeError:
        raise ApiError(0, "odpowiedź nie jest JSON-em")


def fetch_usage(key, rng):
    path = f"/api/usage?range={rng}&group_by=model"
    try:
        return get_json(path, key)
    except ApiError as exc:
        # starsze API odrzuca nieznane parametry kodem 400
        if exc.status == 400:
            return get_json(f"/api/usage?range={rng}", key)
        raise


def local(iso):
    if not iso:
        return "?"
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso


def usd(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "?"
    if value == 0:
        return "$0.00"
    if abs(value) < 1:
        return f"${value:.4f}"
    return f"${value:,.2f}"


def tokens(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return "?"
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} mld"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} mln"
    return f"{value:,}".replace(",", " ")


def render_usage(usage):
    totals = usage.get("totals") or {}
    req = totals.get("request_count")
    cost = totals.get("usage_usd")
    lines = [
        f"Zakres {usage.get('range', '?')}, czas lokalny Europe/Warsaw",
        f"  od {local(usage.get('from'))} do {local(usage.get('until'))}",
        f"  zapytania: {tokens(req)}",
    ]
    inp = totals.get("input_tokens")
    cached = totals.get("cached_input_tokens")
    out = totals.get("output_tokens")
    if inp is not None:
        share = ""
        try:
            if inp:
                share = f" (cache {100 * float(cached or 0) / float(inp):.0f}%)"
        except Exception:
            share = ""
        lines.append(f"  tokeny: wejście {tokens(inp)}{share}, wyjście {tokens(out)}")
    line = f"  koszt: {usd(cost)}"
    try:
        if req:
            line += f" ({float(cost) * 1000 / float(req):.2f} USD / 1000 zapytań)"
    except Exception:
        pass
    lines.append(line)

    groups = totals.get("groups") or []
    if groups:
        groups = sorted(groups, key=lambda g: float(g.get("usage_usd") or 0), reverse=True)
        lines.append("")
        lines.append("Po modelach:")
        for g in groups:
            try:
                pct = 100 * float(g.get("usage_usd") or 0) / float(cost)
                pct_s = f"{pct:3.0f}%"
            except Exception:
                pct_s = "  ?"
            lines.append(
                f"  {str(g.get('model', '?')):24s} {tokens(g.get('request_count')):>8s} zap. "
                f"{usd(g.get('usage_usd')):>9s} {pct_s}"
            )
    return lines


def render_balance(balance):
    included = balance.get("included") or {}
    purchased = balance.get("purchased") or {}
    lines = ["", "Kredyt:"]
    if "session" in included or "weekly" in included:
        for name, label in (("session", "sesja"), ("weekly", "tydzień")):
            part = included.get(name) or {}
            if part:
                lines.append(
                    f"  {label}: zostało {part.get('remaining_percent', '?')}%, "
                    f"reset {local(part.get('resets_at'))}"
                )
    else:
        left = included.get("balance_usd")
        allowance = included.get("allowance_usd")
        period = (included.get("period") or {}).get("until")
        if left is not None:
            pct = ""
            try:
                if allowance:
                    pct = f", zostało {100 * float(left) / float(allowance):.0f}%"
            except Exception:
                pct = ""
            lines.append(f"  w planie: {usd(left)} z {usd(allowance)}{pct}, odnowienie {local(period)}")
    if purchased.get("balance_usd") is not None:
        lines.append(f"  dokupione: {usd(purchased.get('balance_usd'))}")
    return lines


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ollama-cost",
        description="Koszt i saldo Ollama Cloud",
    )
    parser.add_argument("--range", choices=["24h", "7d", "30d"], default="7d")
    parser.add_argument("--json", action="store_true", help="surowy JSON obu odpowiedzi")
    parser.add_argument("--key-file", help="plik z kluczem API")
    parser.add_argument(
        "--max-usd",
        type=float,
        help="próg kosztu dla zakresu, przekroczenie daje kod wyjścia 3",
    )
    parser.add_argument("--version", action="version", version="ollama-cost " + __version__)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    key, source = read_key(args)
    if not key:
        print(
            "Brak klucza API. Ustaw OLLAMA_API_KEY albo wpisz klucz do "
            f"{DEFAULT_KEY_FILE} (albo podaj --key-file).",
            file=sys.stderr,
        )
        return 2

    try:
        usage = fetch_usage(key, args.range)
        balance = get_json("/api/balance", key)
    except ApiError as exc:
        if exc.status == 401:
            print(f"Klucz API odrzucony (401). Sprawdź klucz z {source}.", file=sys.stderr)
        elif exc.status == 429:
            print(f"Limit zapytań API, spróbuj po {exc.retry_after or '?'} s.", file=sys.stderr)
        elif exc.status == 403:
            print("Konto zawieszone (403).", file=sys.stderr)
        elif exc.status == 503:
            print("Ollama chwilowo nie raportuje salda (503).", file=sys.stderr)
        elif exc.status == 404:
            print("Endpoint nie istnieje (404). Sprawdź, czy to konto Ollama Cloud.", file=sys.stderr)
        else:
            print(f"Błąd odczytu: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"usage": usage, "balance": balance}, ensure_ascii=False, indent=2))
        return 0

    lines = render_usage(usage) + render_balance(balance)
    try:
        cost = float((usage.get("totals") or {}).get("usage_usd") or 0)
    except Exception:
        cost = 0.0
    if args.max_usd is not None:
        lines.append("")
        if cost > args.max_usd:
            lines.append(f"PRÓG: {usd(cost)} przekracza {usd(args.max_usd)}.")
            print("\n".join(lines))
            return 3
        lines.append(f"PRÓG: {usd(cost)} mieści się w {usd(args.max_usd)}.")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
