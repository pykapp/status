#!/usr/bin/env python3
"""Render the status page (DESIGN.md §15).

One HTML file and one Atom feed, from two inputs and a clock:

  probes.json     what the external prober last saw, as Better Stack's
                  `GET /api/v2/monitors` answers it (or missing: unknown)
  incidents.json  what a human has posted, as GitHub's issues API answers
                  `repos/pykapp/status/issues?labels=incident&state=all`
  --now           the moment of rendering, for the tests; the clock otherwise

The page is text and inline SVG and loads nothing: no script from anywhere,
no stylesheet, no image, no font. That is the S3 lesson §15 tells—a status
page that fetches its own red marker cannot show it—and `test_generate.py`
reads the rendered bytes to hold it.

The deadman's switch is here and in the page. Here: the prober's newest
`last_checked_at` is the heartbeat, and a heartbeat older than
STALE_AFTER_MINUTES, or none, renders `we can't currently confirm service
health` rather than green. In the page: an inline script with no network
compares the page's own `as of` to the viewer's clock and says the same thing
if the page itself has gone stale—the case where the renderer stopped, which
this script cannot see because it is the renderer. A reader with no script
gets the rule in a sentence beside the time, and the page asks the browser to
reload itself every ten minutes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path

STALE_AFTER_MINUTES = 20
RECENT_DAYS = 30
SITE = "https://pykapp.github.io/status/"
INCIDENTS_REPO = "https://github.com/pykapp/status"
TITLE = "people you know—status"

UNKNOWN_SENTENCE = "we can't currently confirm service health"
OK_SENTENCE = "all good"
TROUBLE_SENTENCE = "something's wrong"

# The two grounds the page paints. Named, so the marks' contrast is measured
# against what is on the screen and not against a copy of it.
LIGHT_GROUND = "#ffffff"
DARK_GROUND = "#111111"

# A mark's colour is laid over its shape and never replaces it (§15). The green
# and the red are the launcher icon's: `icon_quadrant_br` and `icon_quadrant_tr`
# in androidApp/src/main/res/values/colors.xml, which test_generate.py reads so
# the page cannot drift from the icon. Those quadrants hold one L* by
# construction, so in greyscale, and to anybody who cannot tell red from green,
# the two marks are one grey: the filled, barred and hollow discs say the state
# and the colour only repeats it. Unknown has no colour and draws in the text's
# own ink, because it must not look like either.
#
# The dark shades hold each hue and chroma in LCh and raise L* from 40 to 62.
# The icon's own shades give the dark ground 2.9:1, under WCAG's 3:1 for a
# graphic; at 62 each gives it the 6.4:1 the light shade gives white.
MARK_COLOURS = {
    "ok": {"light": "#40690E", "dark": "#7AA349"},
    "trouble": {"light": "#A43C31", "dark": "#E77665"},
}


# ── inputs ────────────────────────────────────────────────────────────────────

def parse_time(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def load_probes(path: Path | None) -> list[dict] | None:
    """The prober's monitors, or None when nothing could be read: unknown, never green."""
    if path is None or not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    monitors = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(monitors, list):
        return None
    probes = []
    for monitor in monitors:
        attributes = monitor.get("attributes", {}) if isinstance(monitor, dict) else {}
        status = attributes.get("status")
        probes.append({
            "name": attributes.get("pronounceable_name") or attributes.get("url") or "probe",
            "state": "up" if status == "up" else "down" if status == "down" else "unknown",
            "checked": parse_time(attributes.get("last_checked_at")),
            "regions": attributes.get("regions") or [],
        })
    return probes


def load_incidents(path: Path | None) -> list[dict]:
    if path is None or not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    incidents = []
    for issue in raw:
        if not isinstance(issue, dict) or "pull_request" in issue:
            continue
        incidents.append({
            "title": str(issue.get("title") or "incident"),
            "body": str(issue.get("body") or ""),
            "url": str(issue.get("html_url") or INCIDENTS_REPO),
            "opened": parse_time(issue.get("created_at")),
            "updated": parse_time(issue.get("updated_at")) or parse_time(issue.get("created_at")),
            "closed": parse_time(issue.get("closed_at")),
        })
    return incidents


# ── the decision ──────────────────────────────────────────────────────────────

def decide(probes: list[dict] | None, now: dt.datetime) -> tuple[str, dt.datetime | None]:
    """The overall state and the heartbeat it rests on. Default unknown, never healthy."""
    if not probes:
        return "unknown", None
    heartbeats = [p["checked"] for p in probes if p["checked"] is not None]
    if not heartbeats:
        return "unknown", None
    heartbeat = max(heartbeats)
    if now - heartbeat > dt.timedelta(minutes=STALE_AFTER_MINUTES):
        return "unknown", heartbeat
    if any(p["state"] == "down" for p in probes):
        return "trouble", heartbeat
    if any(p["state"] == "unknown" for p in probes):
        return "unknown", heartbeat
    return "ok", heartbeat


SENTENCES = {"ok": OK_SENTENCE, "trouble": TROUBLE_SENTENCE, "unknown": UNKNOWN_SENTENCE}


# ── rendering ─────────────────────────────────────────────────────────────────

def when(moment: dt.datetime | None) -> str:
    """`10:32 utc on 8 september 2026`: a date, in the voice, never a countdown."""
    if moment is None:
        return "never"
    return moment.strftime("%H:%M utc on %-d %B %Y").lower()


def mark(state: str) -> str:
    """The state as inline SVG: a filled disc for good, a hollow one for unknown, a barred one for trouble.

    The shape is the state and the class only colours it (MARK_COLOURS); `unknown` has no colour rule.
    """
    if state == "ok":
        return '<svg class="mark ok" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="currentColor"/></svg>'
    if state == "trouble":
        return ('<svg class="mark trouble" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">'
                '<circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/>'
                '<line x1="3" y1="11" x2="11" y2="3" stroke="currentColor" stroke-width="1.5"/></svg>')
    return '<svg class="mark unknown" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>'


def mark_rules(scheme: str) -> str:
    """The coloured marks' CSS for one colour scheme. Unknown has no rule, so it keeps the text's colour."""
    return " ".join(f".mark.{state} {{ color: {shades[scheme]}; }}" for state, shades in MARK_COLOURS.items())


def text(value: str) -> str:
    """Element text: `<`, `>` and `&` escaped, quotes left as a person typed them. Attributes use `html.escape` as is."""
    return html.escape(value, quote=False)


def paragraphs(body: str) -> str:
    """A human's markdown, as escaped paragraphs. No HTML from anybody is ever rendered."""
    blocks = [b.strip() for b in body.replace("\r\n", "\n").split("\n\n") if b.strip()]
    return "".join(f"<p>{text(b)}</p>" for b in blocks) or ""


def render_html(state: str, heartbeat: dt.datetime | None, probes: list[dict] | None, incidents: list[dict], now: dt.datetime) -> str:
    current = [i for i in incidents if i["closed"] is None]
    recent = [i for i in incidents if i["closed"] is not None and now - i["closed"] <= dt.timedelta(days=RECENT_DAYS)]
    current.sort(key=lambda i: i["opened"] or now, reverse=True)
    recent.sort(key=lambda i: i["closed"], reverse=True)

    probe_rows = ""
    window = dt.timedelta(minutes=STALE_AFTER_MINUTES)
    for p in (probes or []):
        # A row checked longer ago than the window says unknown, as the headline does.
        fresh = p["checked"] is not None and now - p["checked"] <= window
        shown = ("ok" if p["state"] == "up" else "trouble" if p["state"] == "down" else "unknown") if fresh else "unknown"
        probe_rows += (
            f'<li>{mark(shown)} '
            f'{text(p["name"])}—{text(p["state"])}, checked {when(p["checked"])}'
            + (f' from {text(", ".join(str(r) for r in p["regions"]))}' if p["regions"] else "")
            + "</li>"
        )
    if not probe_rows:
        probe_rows = "<li>no probe has reported</li>"

    def incident_block(i: dict) -> str:
        span = f'opened {when(i["opened"])}' + (f', resolved {when(i["closed"])}' if i["closed"] else "")
        return (f'<article><h3><a href="{html.escape(i["url"])}">{text(i["title"])}</a></h3>'
                f'<p class="dim">{span}</p>{paragraphs(i["body"])}</article>')

    current_html = "".join(incident_block(i) for i in current) or "<p>nothing is being worked on right now</p>"
    recent_html = "".join(incident_block(i) for i in recent) or f"<p>nothing in the last {RECENT_DAYS} days</p>"

    light_marks, dark_marks = mark_rules("light"), mark_rules("dark")
    as_of = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="600">
<title>{text(TITLE)}</title>
<link rel="alternate" type="application/atom+xml" title="incidents" href="feed.xml">
<style>
  /* No external anything: this file is the whole page (DESIGN.md §15). */
  body {{ margin: 0; padding: 2rem 1.25rem; max-width: 40rem; font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #111; background: {LIGHT_GROUND}; }}
  {light_marks}
  @media (prefers-color-scheme: dark) {{ body {{ color: #eee; background: {DARK_GROUND}; }} {dark_marks} }}
  h1 {{ font-size: 1.1rem; font-weight: 600; margin: 0 0 1.5rem; }}
  h2 {{ font-size: 1rem; font-weight: 600; margin: 2rem 0 .5rem; }}
  h3 {{ font-size: 1rem; font-weight: 600; margin: 1rem 0 .25rem; }}
  #state {{ font-size: 1.4rem; margin: 0 0 .25rem; display: flex; align-items: center; gap: .6rem; }}
  .dim {{ opacity: .7; margin: 0 0 1rem; }}
  ul {{ padding-left: 1.2rem; }} li {{ margin: .25rem 0; }}
  svg {{ vertical-align: -1px; }}
  a {{ color: inherit; }}
  article {{ margin-bottom: 1.25rem; }}
</style>
</head>
<body>
<h1>people you know—status</h1>

<div id="status" data-as-of="{as_of}" data-stale-after-minutes="{STALE_AFTER_MINUTES}" data-state="{state}">
  <p id="state">{mark(state)} <span id="sentence">{text(SENTENCES[state])}</span></p>
  <p class="dim" id="asof">as of {when(now)}, from a probe last heard from {when(heartbeat)}.
  if that is more than {STALE_AFTER_MINUTES} minutes ago, {UNKNOWN_SENTENCE}.</p>
</div>

<h2>what is being checked, from outside</h2>
<ul>{probe_rows}</ul>

<h2>now</h2>
{current_html}

<h2>the last {RECENT_DAYS} days</h2>
{recent_html}

<h2>subscribe</h2>
<p><a href="feed.xml">rss</a> · email: <a href="{INCIDENTS_REPO}">watch the incidents repository</a> (watch → custom → issues), which mails every incident as it is posted and closed.</p>
<p class="dim">this page is rendered by a job that shares nothing with the app: a different provider, a different network, a domain that is not ours. it loads no script, image, font or stylesheet from anywhere, and defaults to unknown when the probe goes quiet.</p>

<script>
/* The deadman's switch, viewer's side. No network: only this page's own
   `as of` against the viewer's clock. If the renderer stopped, the page is
   what stops saying green, in the headline and on every row. */
(function () {{
  var box = document.getElementById("status");
  var asOf = Date.parse(box.getAttribute("data-as-of"));
  var window = Number(box.getAttribute("data-stale-after-minutes")) * 60 * 1000;
  if (isNaN(asOf) || Date.now() - asOf > window) {{
    document.getElementById("sentence").textContent = {json.dumps(UNKNOWN_SENTENCE)};
    var marks = document.querySelectorAll("svg.mark");
    for (var i = 0; i < marks.length; i++) {{ marks[i].outerHTML = {json.dumps(mark("unknown"))}; }}
    box.setAttribute("data-state", "unknown");
  }}
}})();
</script>
</body>
</html>
"""


def render_feed(incidents: list[dict], now: dt.datetime) -> str:
    def stamp(moment: dt.datetime | None) -> str:
        return (moment or now).strftime("%Y-%m-%dT%H:%M:%SZ")

    entries = ""
    for i in sorted(incidents, key=lambda i: i["updated"] or now, reverse=True)[:50]:
        state = "resolved" if i["closed"] else "open"
        entries += f"""  <entry>
    <title>{html.escape(i["title"])} ({state})</title>
    <link href="{html.escape(i["url"])}"/>
    <id>{html.escape(i["url"])}</id>
    <updated>{stamp(i["updated"])}</updated>
    <content type="text">{html.escape(i["body"])}</content>
  </entry>
"""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{html.escape(TITLE)}</title>
  <link href="{SITE}"/>
  <link rel="self" href="{SITE}feed.xml"/>
  <id>{SITE}</id>
  <updated>{stamp(now)}</updated>
{entries}</feed>
"""


def render(probes_path: Path | None, incidents_path: Path | None, out: Path, now: dt.datetime) -> str:
    probes = load_probes(probes_path)
    incidents = load_incidents(incidents_path)
    state, heartbeat = decide(probes, now)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render_html(state, heartbeat, probes, incidents, now))
    (out / "feed.xml").write_text(render_feed(incidents, now))
    (out / ".nojekyll").write_text("")
    return state


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--probes", type=Path, default=None)
    parser.add_argument("--incidents", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=Path("docs"))
    parser.add_argument("--now", type=str, default=None, help="ISO 8601, for the tests")
    args = parser.parse_args(argv)
    now = parse_time(args.now) or dt.datetime.now(dt.timezone.utc)
    state = render(args.probes, args.incidents, args.out, now)
    print(f"rendered {args.out / 'index.html'}: {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
