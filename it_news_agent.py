#!/usr/bin/env python3
"""
THE BITSTREAM — an automated IT-news daily.

This agent crawls a curated set of IT/technology RSS feeds, sorts the stories
into beats (AI, Security, Hardware, Software/Dev, Business, Gadgets), removes
duplicates, picks a lead story, and renders a magazine-style HTML edition.

USAGE
-----
    python it_news_agent.py                 # build today's edition into ./editions
    python it_news_agent.py --open          # ...and open it in your browser
    python it_news_agent.py --out ./public  # choose an output directory
    python it_news_agent.py --per-section 6 # max stories per beat
    python it_news_agent.py --hours 48      # only stories newer than N hours

Each run writes:
    <out>/editions/YYYY-MM-DD.html   (the dated archive)
    <out>/latest.html                (always the most recent edition)

RUN IT DAILY (pick your platform)
---------------------------------
  Linux / macOS (cron) — edit `crontab -e`, run every day at 07:00:
      0 7 * * *  /usr/bin/python3 /path/to/it_news_agent.py --out /path/to/public

  macOS (launchd) — create ~/Library/LaunchAgents/com.bitstream.daily.plist
  with a StartCalendarInterval, pointing ProgramArguments at this script.

  Windows (Task Scheduler) — create a Basic Task, trigger Daily, action:
      Program:  python
      Arguments: C:\\path\\to\\it_news_agent.py --out C:\\path\\to\\public

DEPENDENCIES
------------
    pip install feedparser
(`requests` is optional; the script falls back to urllib if it is absent.)
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import sys
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import feedparser

# --------------------------------------------------------------------------- #
#  CONFIG — edit freely. Add/remove feeds and beats here.                      #
# --------------------------------------------------------------------------- #

MAGAZINE_NAME = "THE BITSTREAM"
TAGLINE = "An IT & Technology Daily — automatically compiled"
# Issue numbers count up from this date so editions feel like a real run.
LAUNCH_DATE = dt.date(2026, 6, 1)

# Beats, in the order they appear in the edition. Each maps to a list of feeds.
# Feeds are (source_label, url). Stories inherit their feed's beat, but a
# keyword pass (CLASSIFY_RULES below) can re-file stories from broad feeds.
FEEDS: dict[str, list[tuple[str, str]]] = {
    "AI & Machine Learning": [
        ("TechCrunch AI",   "https://techcrunch.com/category/artificial-intelligence/feed/"),
        ("VentureBeat AI",  "https://venturebeat.com/category/ai/feed/"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ],
    "Cybersecurity": [
        ("The Hacker News",   "https://feeds.feedburner.com/TheHackersNews"),
        ("BleepingComputer",  "https://www.bleepingcomputer.com/feed/"),
        ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
        ("Dark Reading",      "https://www.darkreading.com/rss.xml"),
    ],
    "Hardware & Chips": [
        ("Tom's Hardware", "https://www.tomshardware.com/feeds/all"),
        ("AnandTech",      "https://www.anandtech.com/rss/"),
    ],
    "Software & Dev": [
        ("The Register", "https://www.theregister.com/headlines.atom"),
        ("InfoQ",        "https://feed.infoq.com/"),
        ("GitHub Blog",  "https://github.blog/feed/"),
        ("Ars Technica Tech", "https://feeds.arstechnica.com/arstechnica/technology-lab"),
    ],
    "Business & Big Tech": [
        ("TechCrunch",   "https://techcrunch.com/feed/"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("The Verge",    "https://www.theverge.com/rss/index.xml"),
    ],
    "Gadgets & Consumer": [
        ("Engadget",  "https://www.engadget.com/rss.xml"),
        ("TechRadar", "https://www.techradar.com/rss"),
    ],
}

# Beats whose newest story may be promoted to the front-page lead.
LEAD_ELIGIBLE = ["Hardware & Chips", "AI & Machine Learning",
                 "Business & Big Tech", "Cybersecurity"]

# Keyword re-classification for stories that arrive via broad feeds.
# First matching beat wins; stories that match nothing keep their feed's beat.
CLASSIFY_RULES: list[tuple[str, list[str]]] = [
    ("Cybersecurity", ["vulnerabilit", "cve-", "breach", "ransomware", "malware",
                        "exploit", "zero-day", "zero day", "phishing", "hacker",
                        "infostealer", "patch tuesday", "data leak"]),
    ("AI & Machine Learning", ["openai", "anthropic", "llm", "gpt", "gemini",
                               "machine learning", "neural", "model ", "agentic",
                               " ai ", "artificial intelligence", "chatbot"]),
    ("Hardware & Chips", ["chip", "semiconductor", "gpu", "cpu", "nvidia", "intel",
                          "amd", "tsmc", "arm ", "ryzen", "processor", "silicon",
                          "wafer", "foundry"]),
    ("Gadgets & Consumer", ["laptop", "smartphone", "iphone", "android", "headphone",
                            "earbud", "wearable", "tablet", "monitor", "router"]),
]

DEFAULT_HOURS = 36          # ignore stories older than this many hours
DEFAULT_PER_SECTION = 5     # max stories shown per beat
FRONTPAGE_COUNT = 4         # cards in the "Front Page" highlight grid
SUMMARY_CHARS = 320         # truncate summaries to roughly this length
REQUEST_TIMEOUT = 12        # seconds per feed

# --------------------------------------------------------------------------- #
#  QUALITY FILTER (strict mode)                                               #
# --------------------------------------------------------------------------- #

# URL fragments that mark non-articles: events, contests, sponsor/marketing.
JUNK_URL_PARTS = ["/events/", "/event/", "/webinar", "/contest", "/sponsored",
                  "/sponsor", "/whitepaper", "/awards", "/advertise", "/promo",
                  "/subscribe", "/newsletter", "/podcast", "/deals/"]

# Title/summary phrases that mark non-news (events, housekeeping, listicles-of-deals).
JUNK_TEXT = ["name that toon", "infosecurity europe", "rsa conference",
             "register now", "watch the keynote here", "how to watch",
             "[an rx global event]", "win a ", "giveaway", "sweepstakes",
             "best deals", "deal of the day", "discount code", "coupon",
             "save up to", "% off", "prime day deals"]

# Off-topic subject matter to drop in strict mode (science/health/lifestyle that
# rides in on general-tech feeds like Ars Technica's main feed).
OFFTOPIC_TEXT = ["catnip", "octopus", "ebola", "vaccine", "dinosaur", "asteroid",
                 "comet", "telescope", "fossil", "archaeolog", "espresso",
                 "recipe", "wine ", "cocktail", "horoscope", "celebrity",
                 "royal family", "nfl", "nba ", "premier league", " recipe",
                 "bluetooth speaker named", "caused a 10-hour delay", "flight from",
                 "deplaning", "tsa rescreening", "scuba diving", "weight loss",
                 "skincare", "mattress", "best mattress"]

# A story must contain at least one of these to count as IT/tech (strict gate).
TECH_TERMS = [
    "ai", "artificial intelligence", "machine learning", "llm", "model", "gpt",
    "chatbot", "agent", "neural", "openai", "anthropic", "gemini", "nvidia",
    "intel", "amd", "qualcomm", "arm", "tsmc", "chip", "semiconductor", "gpu",
    "cpu", "processor", "silicon", "wafer", "foundry", "ram", "memory", "ssd",
    "software", "hardware", "app", "operating system", "windows", "linux",
    "macos", "android", "ios", "kernel", "api", "sdk", "developer", "code",
    "programming", "open-source", "open source", "github", "cloud", "server",
    "data center", "datacenter", "cyber", "security", "vulnerab", "exploit",
    "malware", "ransomware", "phishing", "breach", "patch", "cve", "encryption",
    "laptop", "smartphone", "iphone", "pixel", "galaxy", "tablet", "wearable",
    "router", "gpu", "startup", "saas", "database", "quantum", "robot",
    "drone", "vr", "ar ", "chipmaker", "compute", "inference", "data breach",
    "tech", "technology", "computing", "internet", "browser", "network",
    "password", "vault", "brute-force", "brute force", "credential", "login",
    "authentication", "auth", "firewall", "vpn", "trojan", "rat", "botnet",
    "spyware", "ddos", "zero-day", "zero day", "infostealer", "spear-phishing",
    "spear phishing", "data leak", "hacker", "hacked", "hijack", "rce",
    "privilege escalation", "supply chain", "mfa", "passkey", "data center",
]

# Feeds that are tech by definition — stories from these skip the keyword gate
# (they still go through the junk + off-topic filters).
TRUSTED_TECH_SOURCES = {
    "The Hacker News", "BleepingComputer", "Krebs on Security", "Dark Reading",
    "Tom's Hardware", "AnandTech", "The Register", "InfoQ", "GitHub Blog",
    "Ars Technica Tech", "TechCrunch", "TechCrunch AI", "VentureBeat AI",
    "MIT Tech Review",
}

# POPULAR-NEWS-SITES ALLOWLIST. A story is only kept if its link points to one
# of these established publishers. This blocks personal blogs and aggregator
# spill-over (e.g. Hacker News linking out to someone's hobby site). To trust a
# new outlet, add its bare domain here.
NEWS_DOMAINS = {
    "techcrunch.com", "venturebeat.com", "technologyreview.com",
    "thehackernews.com", "bleepingcomputer.com", "krebsonsecurity.com",
    "darkreading.com", "tomshardware.com", "anandtech.com", "theregister.com",
    "infoq.com", "github.blog", "arstechnica.com", "theverge.com",
    "engadget.com", "techradar.com", "wired.com", "zdnet.com", "cnet.com",
    "reuters.com", "bloomberg.com", "theinformation.com", "axios.com",
    "nytimes.com", "wsj.com", "ft.com", "cnbc.com", "apnews.com", "bbc.com",
}

# Cryptic/low-context titles (e.g. bare Hacker News post names) get a small
# penalty so a meatier story wins the lead and the front page.
MIN_TITLE_WORDS = 3

# --------------------------------------------------------------------------- #
#  DATA MODEL                                                                  #
# --------------------------------------------------------------------------- #


@dataclass
class Article:
    title: str
    link: str
    summary: str
    source: str
    beat: str
    published: dt.datetime | None = None

    @property
    def domain(self) -> str:
        try:
            return urlparse(self.link).netloc.replace("www.", "")
        except Exception:
            return ""


# --------------------------------------------------------------------------- #
#  FETCH + PARSE                                                               #
# --------------------------------------------------------------------------- #

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def clean_summary(raw: str, limit: int = SUMMARY_CHARS) -> str:
    text = strip_html(raw)
    # Drop boilerplate that some feeds append.
    text = re.split(r"(The post .* appeared first|Read more|Continue reading)", text)[0].strip()
    if len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0]
        text = cut.rstrip(".,;: ") + "\u2026"
    return text


def parse_date(entry) -> dt.datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return dt.datetime(*value[:6])
            except Exception:
                pass
    return None


def fetch_feed(source: str, url: str) -> list[Article]:
    """Fetch one feed. Never raises — a dead feed just yields nothing."""
    try:
        parsed = feedparser.parse(
            url,
            request_headers={"User-Agent": "BitstreamAgent/1.0 (+rss reader)"},
        )
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"  ! {source}: {exc}", file=sys.stderr)
        return []

    if getattr(parsed, "bozo", False) and not parsed.entries:
        print(f"  ! {source}: could not parse ({getattr(parsed, 'bozo_exception', '')})",
              file=sys.stderr)
        return []

    out: list[Article] = []
    for entry in parsed.entries:
        title = strip_html(entry.get("title", "")).strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        summary = clean_summary(entry.get("summary", entry.get("description", "")))
        out.append(Article(title=title, link=link, summary=summary,
                            source=source, beat="", published=parse_date(entry)))
    return out


def collect(feeds: dict[str, list[tuple[str, str]]]) -> list[Article]:
    articles: list[Article] = []
    for beat, sources in feeds.items():
        for source, url in sources:
            print(f"  · {beat:<22} <- {source}")
            for art in fetch_feed(source, url):
                art.beat = beat
                articles.append(art)
    return articles


# --------------------------------------------------------------------------- #
#  CLASSIFY, DEDUPE, RANK                                                      #
# --------------------------------------------------------------------------- #


def reclassify(articles: list[Article]) -> None:
    """Re-file stories from broad feeds into the most specific matching beat."""
    for art in articles:
        haystack = f" {art.title.lower()} {art.summary.lower()} "
        for beat, keywords in CLASSIFY_RULES:
            if any(k in haystack for k in keywords):
                art.beat = beat
                break


def _is_tech(text: str) -> bool:
    # word-ish match so "ai" doesn't fire inside "said"/"campaign"
    return any(re.search(rf"(?<![a-z]){re.escape(t)}", text) for t in TECH_TERMS)


def quality_filter(articles: list[Article]) -> list[Article]:
    """Strict mode: drop events/contests/marketing, off-topic items, and
    anything that doesn't clearly read as IT/technology news."""
    kept: list[Article] = []
    for a in articles:
        url = a.link.lower()
        text = f"{a.title.lower()} {a.summary.lower()}"

        # Popular-news-sites gate: link must be on an approved publisher domain.
        dom = a.domain
        if not any(dom == d or dom.endswith("." + d) for d in NEWS_DOMAINS):
            continue
        if any(p in url for p in JUNK_URL_PARTS):
            continue
        if any(p in text for p in JUNK_TEXT):
            continue
        if any(p in text for p in OFFTOPIC_TEXT):
            continue
        # Title must be a real headline, not a one-word post name.
        if len(re.findall(r"\w+", a.title)) < MIN_TITLE_WORDS:
            continue
        # Strict relevance gate: must look like tech, UNLESS it comes from a
        # feed that is tech by definition (those only face junk/off-topic checks).
        if a.source not in TRUSTED_TECH_SOURCES and not _is_tech(f" {text} "):
            continue
        kept.append(a)
    return kept


def _norm(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower())


def dedupe(articles: list[Article]) -> list[Article]:
    seen: set[str] = set()
    out: list[Article] = []
    for art in sorted(articles, key=lambda a: a.published or dt.datetime.min, reverse=True):
        key = _norm(art.title)[:60]
        if key in seen or not key:
            continue
        seen.add(key)
        out.append(art)
    return out


def recent_only(articles: list[Article], hours: int) -> list[Article]:
    if hours <= 0:
        return articles
    cutoff = dt.datetime.utcnow() - dt.timedelta(hours=hours)
    kept = [a for a in articles if a.published is None or a.published >= cutoff]
    # If date filtering nukes everything (feeds without timestamps), keep all.
    return kept or articles


def _lead_score(a: Article) -> float:
    """Prefer substantive, clearly-newsy stories for the lead."""
    score = 0.0
    summary_len = len(a.summary)
    score += min(summary_len, 240) / 60          # rewards a real summary
    score += min(len(re.findall(r"\w+", a.title)), 12) / 4  # rewards a full headline
    if a.published:                               # mild recency nudge
        h = (dt.datetime.utcnow() - a.published).total_seconds() / 3600
        score += max(0, 3 - h / 8)
    # Bare aggregator posts (no summary) shouldn't lead.
    if summary_len < 40:
        score -= 3
    # Reviews / first-person opinion make weak leads.
    if re.search(r"\b(i tried|i was|review|hands-on|opinion)\b", a.title.lower()):
        score -= 2
    return score


def pick_lead(by_beat: dict[str, list[Article]]) -> Article | None:
    pool: list[Article] = []
    for beat in LEAD_ELIGIBLE:
        pool.extend(by_beat.get(beat, [])[:3])    # top few from each major beat
    if not pool:
        pool = [a for arts in by_beat.values() for a in arts]
    if not pool:
        return None
    return max(pool, key=_lead_score)


# --------------------------------------------------------------------------- #
#  RENDER (magazine HTML)                                                      #
# --------------------------------------------------------------------------- #

CSS = """
:root{
  --paper:#f4efe3; --paper-2:#ece5d4; --panel:#f9f5ec;
  --ink:#1b1714; --ink-2:#5a5147; --ink-3:#8a7f70;
  --accent:#bf3b1c; --accent-2:#16433b;
  --rule:#d8cdb6; --rule-strong:#1b1714;
  --backdrop:#26221d;
  --serif:"Newsreader",Georgia,serif;
  --display:"Fraunces","Newsreader",Georgia,serif;
  --mono:"Space Mono",ui-monospace,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{
  background:var(--backdrop);
  font-family:var(--serif);color:var(--ink);
  line-height:1.55;padding:28px 16px;
  background-image:radial-gradient(circle at 20% 0,rgba(255,255,255,.04),transparent 60%);
}
.page{
  max-width:1180px;margin:0 auto;background:var(--paper);
  padding:clamp(22px,4vw,60px);
  box-shadow:0 30px 80px rgba(0,0,0,.5),0 2px 0 rgba(0,0,0,.2);
  position:relative;
  background-image:
    repeating-linear-gradient(0deg,rgba(120,100,70,.022) 0 1px,transparent 1px 3px),
    radial-gradient(circle at 80% 10%,rgba(191,59,28,.04),transparent 45%);
}
a{color:inherit;text-decoration:none}

/* ---- folio bar ---- */
.folio{
  display:flex;justify-content:space-between;align-items:center;
  font-family:var(--mono);font-size:11px;letter-spacing:.18em;
  text-transform:uppercase;color:var(--ink-2);
  border-bottom:1px solid var(--rule);padding-bottom:10px;flex-wrap:wrap;gap:6px;
}
.folio .dot{color:var(--accent)}

/* ---- masthead ---- */
.masthead{text-align:center;padding:30px 0 16px;border-bottom:3px double var(--rule-strong)}
.masthead h1{
  font-family:var(--display);font-weight:900;
  font-size:clamp(44px,11vw,128px);line-height:.9;letter-spacing:-.02em;
  font-optical-sizing:auto;
}
.masthead .tag{
  font-family:var(--mono);font-size:11px;letter-spacing:.32em;text-transform:uppercase;
  color:var(--ink-2);margin-top:16px;
}
.dateline{
  display:flex;justify-content:center;gap:22px;flex-wrap:wrap;
  font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink-2);margin-top:14px;border-top:1px solid var(--rule);padding-top:12px;
}

/* ---- kickers ---- */
.kicker{
  font-family:var(--mono);font-size:11px;letter-spacing:.2em;text-transform:uppercase;
  color:var(--accent);font-weight:700;display:inline-block;
}
.section-head{
  display:flex;align-items:center;gap:16px;margin:46px 0 22px;
}
.section-head h2{
  font-family:var(--mono);font-size:13px;letter-spacing:.28em;text-transform:uppercase;
  white-space:nowrap;color:var(--ink);font-weight:700;
}
.section-head .line{flex:1;height:1px;background:var(--rule-strong)}
.section-head .count{font-family:var(--mono);font-size:11px;color:var(--ink-3);letter-spacing:.1em}

/* ---- lead ---- */
.lead{padding:34px 0 8px;border-bottom:1px solid var(--rule)}
.lead .kicker{margin-bottom:14px}
.lead h2{
  font-family:var(--display);font-weight:800;letter-spacing:-.015em;
  font-size:clamp(30px,5.4vw,62px);line-height:1.02;margin-bottom:18px;
}
.lead h2 a{background-image:linear-gradient(var(--accent),var(--accent));
  background-size:0% 2px;background-repeat:no-repeat;background-position:0 100%;
  transition:background-size .3s ease}
.lead h2 a:hover{background-size:100% 2px}
.lead .dek{font-size:clamp(17px,2.2vw,22px);color:var(--ink-2);
  font-style:italic;max-width:60ch;margin-bottom:18px}
.lead .body{columns:2;column-gap:42px;font-size:16px}
.lead .body p{margin-bottom:12px;break-inside:avoid}
.lead .body p:first-child::first-letter{
  font-family:var(--display);font-weight:900;float:left;font-size:74px;
  line-height:.72;padding:6px 10px 0 0;color:var(--accent)}
.byline{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink-3);margin-top:14px}
.byline a{border-bottom:1px solid var(--accent);color:var(--accent)}

/* ---- grids ---- */
.frontpage{display:grid;grid-template-columns:repeat(4,1fr);gap:0}
.frontpage .story{padding:20px;border-right:1px solid var(--rule)}
.frontpage .story:last-child{border-right:none}
.beat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:26px 32px}

.story .kicker{font-size:10px;margin-bottom:9px}
.story h3{font-family:var(--display);font-weight:700;font-size:21px;
  line-height:1.12;letter-spacing:-.01em;margin-bottom:8px}
.story h3 a{background-image:linear-gradient(var(--ink),var(--ink));
  background-size:0% 1px;background-repeat:no-repeat;background-position:0 100%;
  transition:background-size .3s ease}
.story h3 a:hover{background-size:100% 1px}
.story p{font-size:14.5px;color:var(--ink-2);margin-bottom:10px}
.story .src{font-family:var(--mono);font-size:10px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-3)}
.story .src b{color:var(--accent);font-weight:700}

/* a few editorial 2-col beats get a leading wide story */
.beat-grid.lead-left{grid-template-columns:1.6fr 1fr 1fr}

/* ---- colophon ---- */
.colophon{margin-top:54px;border-top:3px double var(--rule-strong);padding-top:20px;
  font-family:var(--mono);font-size:11px;letter-spacing:.08em;color:var(--ink-3);
  line-height:1.7}
.colophon b{color:var(--ink)}
.sources-list{margin-top:8px;color:var(--ink-2)}

/* ---- entrance animation ---- */
.reveal{opacity:0;transform:translateY(14px);animation:rise .7s cubic-bezier(.2,.7,.2,1) forwards}
@keyframes rise{to{opacity:1;transform:none}}

@media(max-width:880px){
  .frontpage{grid-template-columns:repeat(2,1fr)}
  .frontpage .story:nth-child(2n){border-right:none}
  .beat-grid,.beat-grid.lead-left{grid-template-columns:1fr 1fr}
  .lead .body{columns:1}
}
@media(max-width:560px){
  .frontpage,.beat-grid,.beat-grid.lead-left{grid-template-columns:1fr}
  .frontpage .story{border-right:none;border-bottom:1px solid var(--rule)}
}
"""

HEAD = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} — {date}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700;9..144,900&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>{css}</style></head><body><main class="page">"""

FOOT = "</main></body></html>"


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def fmt_time(d: dt.datetime | None) -> str:
    if not d:
        return "filed recently"
    delta = dt.datetime.utcnow() - d
    h = int(delta.total_seconds() // 3600)
    if h < 1:
        return "just now"
    if h < 24:
        return f"{h}h ago"
    return f"{h // 24}d ago"


def card(a: Article) -> str:
    summary = f"<p>{esc(a.summary)}</p>" if a.summary else ""
    return f"""<article class="story">
  <span class="kicker">{esc(a.beat.split(' & ')[0])}</span>
  <h3><a href="{esc(a.link)}" target="_blank" rel="noopener">{esc(a.title)}</a></h3>
  {summary}
  <div class="src"><b>{esc(a.source)}</b> &nbsp;·&nbsp; {fmt_time(a.published)}</div>
</article>"""


def render_lead(a: Article) -> str:
    # Split the summary into ~two pseudo-paragraphs for the two-column body.
    words = a.summary.split()
    mid = len(words) // 2 or len(words)
    p1, p2 = " ".join(words[:mid]), " ".join(words[mid:])
    body = f"<p>{esc(p1)}</p>" + (f"<p>{esc(p2)}</p>" if p2 else "")
    return f"""<section class="lead reveal" style="animation-delay:.05s">
  <span class="kicker">Lead Story &nbsp;·&nbsp; {esc(a.beat)}</span>
  <h2><a href="{esc(a.link)}" target="_blank" rel="noopener">{esc(a.title)}</a></h2>
  <div class="body">{body}</div>
  <div class="byline">Filed by <a href="{esc(a.link)}" target="_blank" rel="noopener">{esc(a.source)}</a>
     &nbsp;·&nbsp; {fmt_time(a.published)} &nbsp;·&nbsp; {esc(a.domain)}</div>
</section>"""


def render_section(beat: str, arts: list[Article], lead_left=False) -> str:
    if not arts:
        return ""
    cards = "\n".join(card(a) for a in arts)
    cls = "beat-grid lead-left" if lead_left and len(arts) >= 3 else "beat-grid"
    return f"""<section class="reveal">
  <div class="section-head">
    <h2>{esc(beat)}</h2><span class="line"></span>
    <span class="count">{len(arts):02d} stories</span>
  </div>
  <div class="{cls}">{cards}</div>
</section>"""


def render_page(by_beat: dict[str, list[Article]], lead: Article | None,
                date: dt.date, total: int, source_count: int) -> str:
    issue = (date - LAUNCH_DATE).days + 1
    long_date = date.strftime("%A, %B %-d, %Y") if sys.platform != "win32" \
        else date.strftime("%A, %B %d, %Y")

    head = HEAD.format(name=esc(MAGAZINE_NAME), date=esc(long_date), css=CSS)

    folio = f"""<div class="folio">
      <span>{esc(long_date)}</span>
      <span>Vol. I <span class="dot">·</span> No. {issue:03d}</span>
      <span>{total} stories <span class="dot">·</span> {source_count} sources</span>
    </div>"""

    mast = f"""<header class="masthead reveal">
      <h1>{esc(MAGAZINE_NAME)}</h1>
      <div class="tag">{esc(TAGLINE)}</div>
      <div class="dateline">
        <span>Auto-compiled edition</span><span>Tech wire</span>
        <span>{esc(long_date)}</span>
      </div>
    </header>"""

    lead_html = render_lead(lead) if lead else ""

    # Front-page highlights: top story from each beat (excluding the lead).
    highlights: list[Article] = []
    used = {lead.link} if lead else set()
    for beat, arts in by_beat.items():
        for a in arts:
            if a.link not in used:
                highlights.append(a)
                used.add(a.link)
                break
        if len(highlights) >= FRONTPAGE_COUNT:
            break
    fp = ""
    if highlights:
        fp_cards = "\n".join(card(a) for a in highlights)
        fp = f"""<section class="reveal">
          <div class="section-head"><h2>The Front Page</h2><span class="line"></span></div>
          <div class="frontpage">{fp_cards}</div>
        </section>"""

    # Beat sections (skip the lead's already-used story, keep order).
    sections = []
    for i, (beat, arts) in enumerate(by_beat.items()):
        remaining = [a for a in arts if a.link not in {lead.link} ] if lead else arts
        sections.append(render_section(beat, remaining, lead_left=(i % 2 == 0)))

    src_names = ", ".join(sorted({s for sl in FEEDS.values() for s, _ in sl}))
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    colophon = f"""<footer class="colophon">
      <b>{esc(MAGAZINE_NAME)}</b> is compiled automatically by an RSS-crawling agent.
      Every headline links to its original publisher; summaries are condensed from
      each outlet's own feed. Built {stamp}.
      <div class="sources-list"><b>Wire sources &nbsp;·&nbsp;</b> {esc(src_names)}</div>
    </footer>"""

    return head + folio + mast + lead_html + fp + "\n".join(sections) + colophon + FOOT


# --------------------------------------------------------------------------- #
#  ORCHESTRATION                                                               #
# --------------------------------------------------------------------------- #


def build_edition(out_dir: Path, hours: int, per_section: int,
                  make_pdf: bool = False, make_summary: bool = False) -> Path:
    print("Crawling feeds…")
    articles = collect(FEEDS)
    print(f"  collected {len(articles)} raw items")

    reclassify(articles)
    articles = dedupe(articles)
    articles = recent_only(articles, hours)
    before = len(articles)
    articles = quality_filter(articles)
    print(f"  {before} after dedupe+recency -> {len(articles)} after quality filter")

    by_beat: dict[str, list[Article]] = {beat: [] for beat in FEEDS}
    for a in articles:
        by_beat.setdefault(a.beat, []).append(a)
    for beat in by_beat:
        by_beat[beat].sort(key=lambda a: a.published or dt.datetime.min, reverse=True)
        by_beat[beat] = by_beat[beat][:per_section]
    by_beat = {b: v for b, v in by_beat.items() if v}  # drop empty beats

    lead = pick_lead(by_beat)
    today = dt.date.today()
    source_count = sum(len(v) for v in FEEDS.values())
    page = render_page(by_beat, lead, today, len(articles), source_count)

    editions = out_dir / "editions"
    editions.mkdir(parents=True, exist_ok=True)
    dated = editions / f"{today.isoformat()}.html"
    dated.write_text(page, encoding="utf-8")
    (out_dir / "latest.html").write_text(page, encoding="utf-8")
    (out_dir / "index.html").write_text(page, encoding="utf-8")  # site homepage
    print(f"Wrote {dated}")

    if make_pdf:
        try:
            import render_print
            pdf_path = editions / f"{today.isoformat()}.pdf"
            render_print.render_pdf(by_beat, lead, today, len(articles),
                                    source_count, FEEDS, pdf_path)
            print(f"Wrote {pdf_path}")
        except Exception as exc:  # weasyprint/fonts missing -> skip, don't fail
            print(f"  ! PDF skipped: {exc}", file=sys.stderr)

    if make_summary:
        try:
            import render_print
            subject, body = render_print.email_summary(by_beat, lead, today, len(articles))
            txt = editions / f"{today.isoformat()}-email.txt"
            txt.write_text(f"Subject: {subject}\n\n{body}", encoding="utf-8")
            print(f"Wrote {txt}")
        except Exception as exc:
            print(f"  ! summary skipped: {exc}", file=sys.stderr)

    return dated


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compile a magazine-style IT news daily.")
    ap.add_argument("--out", default="./public", type=Path, help="output directory")
    ap.add_argument("--hours", type=int, default=DEFAULT_HOURS,
                    help="only include stories newer than N hours (0 = no filter)")
    ap.add_argument("--per-section", type=int, default=DEFAULT_PER_SECTION,
                    help="max stories per beat")
    ap.add_argument("--open", action="store_true", help="open the edition when done")
    ap.add_argument("--pdf", action="store_true",
                    help="also render a print-quality PDF (needs weasyprint + ./fonts)")
    ap.add_argument("--summary", action="store_true",
                    help="also write an email-ready digest (<date>-email.txt)")
    args = ap.parse_args(argv)

    path = build_edition(args.out, args.hours, args.per_section,
                         make_pdf=args.pdf, make_summary=args.summary)
    if args.open:
        webbrowser.open(path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
