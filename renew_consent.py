#!/usr/bin/env python3
"""Renew the accommodation consent on the AGH DSNet panel (Windows/Linux).

Target: https://panel.dsnet.agh.edu.pl/en/accommodation/#acc_consent
Logs in, submits the consent control in the #acc_consent section, verifies.

Credentials come only from DSNET_EMAIL/DSNET_PASSWORD env vars or a
credentials file OUTSIDE the repo (default: %APPDATA%\\dsnet-consent\\credentials.env
on Windows, ~/.config/dsnet-consent/credentials.env on Linux; override with
DSNET_CREDENTIALS_FILE). State/logs live in %LOCALAPPDATA%\\dsnet-consent or
~/.local/state/dsnet-consent.

Schedule it every 48h10m (173400s) via deploy.sh / deploy.ps1 (both work
piped: curl -sSL <raw>/deploy.sh | bash, irm <raw>/deploy.ps1 | iex), or any
scheduler plus --if-due (enforced via the state file). Interval override:
RENEW_INTERVAL_SECONDS. Exit codes: 0 ok/not-due, 1 failed, 2 misconfigured.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = os.environ.get("DSNET_BASE_URL", "https://panel.dsnet.agh.edu.pl").rstrip("/")
LOGIN_PATH = "/en/login"
ACCOMMODATION_PATH = "/en/accommodation/"
CONSENT_ANCHOR_ID = "acc_consent"
INTERVAL = int(os.environ.get("RENEW_INTERVAL_SECONDS", str(48 * 3600 + 10 * 60)))
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = 30
MAX_ATTEMPTS = 3
STALE_LOCK_SECONDS = 3600


def default_dirs() -> tuple[Path, Path]:
    if os.name == "nt":
        config = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        state = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return config / "dsnet-consent", state / "dsnet-consent"


CONFIG_DIR, STATE_DIR = default_dirs()
CREDENTIALS_FILE = Path(os.environ.get(
    "DSNET_CREDENTIALS_FILE", str(CONFIG_DIR / "credentials.env")))


class ConfigError(Exception):
    pass


class RenewalError(Exception):
    pass


class FormParser(HTMLParser):
    """Collect forms with their inputs/buttons, links, and #acc_consent position."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self.links: list[dict] = []
        self.acc_consent_pos: int | None = None
        self._pos = 0
        self._form: dict | None = None
        self._select: dict | None = None
        self._link: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._pos += 1
        if tag == "form":
            self._form = {"action": a.get("action", ""),
                          "method": a.get("method", "get").lower(),
                          "inputs": [], "buttons": [], "pos": self._pos}
            self.forms.append(self._form)
        elif self._form is not None:
            if tag == "input":
                self._form["inputs"].append({"name": a.get("name"),
                                             "value": a.get("value", ""),
                                             "type": (a.get("type") or "text").lower(),
                                             "disabled": "disabled" in a})
            elif tag == "button":
                self._form["buttons"].append({"name": a.get("name"),
                                              "value": a.get("value", ""),
                                              "type": (a.get("type") or "submit").lower()})
            elif tag == "textarea":
                self._form["inputs"].append({"name": a.get("name"), "value": "",
                                             "type": "textarea", "disabled": "disabled" in a})
            elif tag == "select":
                self._select = {"name": a.get("name"), "options": [],
                                "disabled": "disabled" in a}
            elif tag == "option" and self._select is not None:
                self._select["options"].append(a.get("value", ""))
        if a.get("id") == CONSENT_ANCHOR_ID:
            self.acc_consent_pos = self._pos
        if tag == "a" and a.get("href"):
            self._link = {"href": a["href"], "text": "", "pos": self._pos}

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None
        elif tag == "select" and self._select is not None and self._form is not None:
            self._form["inputs"].append({"name": self._select["name"],
                                         "value": self._select["options"][0] if self._select["options"] else "",
                                         "type": "select", "disabled": self._select["disabled"]})
            self._select = None
        elif tag == "a" and self._link is not None:
            self.links.append(self._link)
            self._link = None

    def handle_data(self, data):
        if self._link is not None:
            self._link["text"] += data


def build_post_data(form: dict, overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    data: dict[str, str] = {}
    radios: set[str] = set()
    for inp in form["inputs"]:
        name, itype = inp.get("name"), inp.get("type")
        if not name or inp.get("disabled") or itype in ("submit", "button", "image"):
            continue
        if itype == "radio":
            if name in radios:
                continue
            radios.add(name)
        if itype == "checkbox":
            data[name] = inp.get("value") or "on"
        else:
            data[name] = overrides.get(name, inp.get("value", ""))
    for btn in form["buttons"]:
        if btn.get("type") == "submit" and btn.get("name"):
            data[btn["name"]] = btn.get("value") or ""
            break
    for key, value in overrides.items():
        data.setdefault(key, value)
    return data


def find_login_form(parser: FormParser) -> dict | None:
    for form in parser.forms:
        names = {i.get("name") for i in form["inputs"]}
        if "_username" in names and "_password" in names:
            return form
    return parser.forms[0] if parser.forms else None


def find_consent_control(parser: FormParser):
    anchor = parser.acc_consent_pos
    if anchor is not None:
        after = [f for f in parser.forms if f["pos"] > anchor]
        if after:
            return "form", after[0]
        links = [l for l in parser.links
                 if l["pos"] > anchor and "consent" in l["href"].lower()]
        return ("link", links[0]) if links else None
    for form in parser.forms:
        if "consent" in (form["action"] or "").lower():
            return "form", form
    for link in parser.links:
        if "consent" in link["href"].lower():
            return "link", link
    return None


def make_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def fetch(opener, url: str, data: bytes | None = None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            return resp.geturl(), resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return url, e.code, e.read().decode("utf-8", "replace")


def is_login_page(url: str) -> bool:
    return "/login" in urllib.parse.urlparse(url).path


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def load_credentials() -> tuple[str, str]:
    email = os.environ.get("DSNET_EMAIL", "")
    password = os.environ.get("DSNET_PASSWORD", "")
    if email and password:
        return email, password
    if CREDENTIALS_FILE.is_file():
        if os.name == "posix":
            mode = stat.S_IMODE(CREDENTIALS_FILE.stat().st_mode)
            if mode & 0o077:
                raise ConfigError(
                    f"{CREDENTIALS_FILE} is group/world-readable (mode {oct(mode)}); "
                    f"chmod 600 it or use DSNET_EMAIL/DSNET_PASSWORD env vars")
        values = {}
        for line in CREDENTIALS_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = unquote(value.strip())
        email = email or values.get("DSNET_EMAIL", "")
        password = password or values.get("DSNET_PASSWORD", "")
    if not email or not password:
        raise ConfigError(
            "no credentials: set DSNET_EMAIL/DSNET_PASSWORD or create "
            f"{CREDENTIALS_FILE} (see setup_credentials.sh / setup_credentials.ps1)")
    return email, password


def log(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    if sys.stderr is not None:
        print(line, file=sys.stderr, flush=True)
    try:
        with open(STATE_DIR / "renew_consent.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def login(opener, email: str, password: str) -> None:
    url, _, html = fetch(opener, BASE_URL + LOGIN_PATH)
    parser = FormParser()
    parser.feed(html)
    form = find_login_form(parser)
    if form is None:
        raise RenewalError("login form not found on the login page")
    action = urllib.parse.urljoin(url, form["action"] or LOGIN_PATH)
    data = build_post_data(form, {"_username": email, "_password": password})
    final_url, _, _ = fetch(opener, action, urllib.parse.urlencode(data).encode())
    if is_login_page(final_url):
        raise RenewalError("login rejected (wrong credentials or login flow changed)")
    log(f"logged in, landing page: {final_url}")


def renew_consent(opener, dry_run: bool = False) -> bool:
    page_url, _, html = fetch(opener, BASE_URL + ACCOMMODATION_PATH)
    if is_login_page(page_url):
        raise RenewalError("not logged in when opening the accommodation page")
    parser = FormParser()
    parser.feed(html)
    control = find_consent_control(parser)
    if control is None:
        log("no pending consent control in #acc_consent - consent already valid")
        return True
    kind, target = control
    if kind == "form":
        action = urllib.parse.urljoin(page_url, target["action"] or page_url)
        data = build_post_data(target)
        log(f"consent form found (action={target['action'] or page_url}, fields={sorted(data)})")
        if dry_run:
            log("dry-run: not submitting")
            return True
        if target["method"] == "get":
            sep = "&" if urllib.parse.urlparse(action).query else "?"
            fetch(opener, action + sep + urllib.parse.urlencode(data))
        else:
            fetch(opener, action, urllib.parse.urlencode(data).encode())
    else:
        log(f"consent link found (href={target['href']!r})")
        if dry_run:
            log("dry-run: not following link")
            return True
        fetch(opener, urllib.parse.urljoin(page_url, target["href"]))
    page_url2, _, html2 = fetch(opener, BASE_URL + ACCOMMODATION_PATH)
    if is_login_page(page_url2):
        raise RenewalError("session lost after submitting consent")
    parser2 = FormParser()
    parser2.feed(html2)
    if find_consent_control(parser2) is not None:
        snapshot = STATE_DIR / "last_failure.html"
        snapshot.write_text(html2, encoding="utf-8")
        os.chmod(snapshot, 0o600)
        raise RenewalError(
            "consent still pending after submit - page structure may have changed; "
            f"snapshot saved to {snapshot}")
    log("consent renewed successfully")
    return True


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)


def acquire_lock() -> Path | None:
    lock = STATE_DIR / "run.lock"
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return lock
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > STALE_LOCK_SECONDS:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            return None
    return None


def is_due() -> bool:
    stamp = STATE_DIR / "last_success"
    if not stamp.is_file():
        return True
    try:
        last = float(stamp.read_text(encoding="utf-8").strip())
    except ValueError:
        return True
    return (time.time() - last) >= INTERVAL


def mark_success() -> None:
    tmp = STATE_DIR / ".last_success.tmp"
    tmp.write_text(f"{time.time():.0f}\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE_DIR / "last_success")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--if-due", action="store_true",
                    help=f"run only if >= {INTERVAL}s since last success")
    ap.add_argument("--dry-run", action="store_true",
                    help="log in and report the consent control without submitting")
    args = ap.parse_args()

    os.umask(0o077)
    ensure_state_dir()
    lock = acquire_lock()
    if lock is None:
        log("another run is in progress, exiting")
        return 0
    try:
        if args.if_due and not is_due():
            log(f"not due yet (interval {INTERVAL}s since last success)")
            return 0
        try:
            email, password = load_credentials()
        except ConfigError as e:
            if args.dry_run:
                _, _, html = fetch(make_opener(), BASE_URL + LOGIN_PATH)
                parser = FormParser()
                parser.feed(html)
                form = find_login_form(parser)
                if form:
                    log("login form action=%r fields=%s" % (
                        form["action"], [(i["name"], i["type"]) for i in form["inputs"]]))
                    return 0
                log("no form found on login page")
                return 1
            log(f"CONFIG ERROR: {e}")
            return 2
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                opener = make_opener()
                login(opener, email, password)
                renew_consent(opener, dry_run=args.dry_run)
                if not args.dry_run:
                    mark_success()
                log("done")
                return 0
            except (RenewalError, urllib.error.URLError, OSError) as e:
                log(f"attempt {attempt}/{MAX_ATTEMPTS} failed: {e}")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(5 * attempt)
        log("renewal failed after all attempts")
        return 1
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
