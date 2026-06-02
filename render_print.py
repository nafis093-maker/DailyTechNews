#!/usr/bin/env python3
"""Print + email rendering for THE BITSTREAM.

Data-driven so it works for both the curated sample and live agent crawls:

    render_pdf(by_beat, lead, date, total, src_count, feeds, out_path)
    subject, body = email_summary(by_beat, lead, date, total)

PDF rendering needs `weasyprint` and the bundled ./fonts directory; if either
is missing, render_pdf raises and callers can skip it gracefully.
"""
from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

FONTS = Path(__file__).parent / "fonts"
NAME = "THE BITSTREAM"
TAGLINE = "An IT & Technology Daily — automatically compiled"
LAUNCH_DATE = dt.date(2026, 6, 1)


def _uri(p: str) -> str:
    return (FONTS / p).resolve().as_uri()


def _long_date(d: dt.date) -> str:
    try:
        return d.strftime("%A, %B %-d, %Y")
    except ValueError:           # Windows
        return d.strftime("%A, %B %d, %Y")


def _issue(d: dt.date) -> int:
    return (d - LAUNCH_DATE).days + 1


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def fmt_time(d):
    if not d:
        return "filed recently"
    h = int((dt.datetime.utcnow() - d).total_seconds() // 3600)
    if h < 1:
        return "just now"
    return f"{h}h ago" if h < 24 else f"{h // 24}d ago"


# --------------------------------------------------------------------------- #
#  PDF                                                                        #
# --------------------------------------------------------------------------- #

def _css(date: dt.date) -> str:
    foot = f'"{NAME}  ·  No. {_issue(date):03d}  ·  {date.strftime("%B %d, %Y")}  ·  page "'
    return f"""
@font-face{{font-family:'Fraunces';src:url('{_uri("Fraunces.ttf")}');font-weight:100 900;font-style:normal;}}
@font-face{{font-family:'Fraunces';src:url('{_uri("Fraunces-Italic.ttf")}');font-weight:100 900;font-style:italic;}}
@font-face{{font-family:'Newsreader';src:url('{_uri("Newsreader.ttf")}');font-weight:100 900;font-style:normal;}}
@font-face{{font-family:'Newsreader';src:url('{_uri("Newsreader-Italic.ttf")}');font-weight:100 900;font-style:italic;}}
@font-face{{font-family:'Space Mono';src:url('{_uri("SpaceMono-Regular.ttf")}');font-weight:400;}}
@font-face{{font-family:'Space Mono';src:url('{_uri("SpaceMono-Bold.ttf")}');font-weight:700;}}
:root{{--paper:#f4efe3;--ink:#1b1714;--ink-2:#5a5147;--ink-3:#8a7f70;--accent:#bf3b1c;--rule:#d8cdb6;--rule-strong:#1b1714;}}
@page{{size:A4;margin:15mm 14mm 16mm;background:var(--paper);
  @bottom-center{{content:{foot} counter(page) " / " counter(pages);
    font-family:'Space Mono',monospace;font-size:7.5pt;letter-spacing:.12em;color:#8a7f70;text-transform:uppercase;}}}}
*{{margin:0;padding:0;box-sizing:border-box}}
html{{background:var(--paper)}}
body{{font-family:'Newsreader',Georgia,serif;color:var(--ink);font-size:9.6pt;line-height:1.5}}
.kicker{{font-family:'Space Mono',monospace;font-size:7pt;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);font-weight:700;display:block;margin-bottom:3pt}}
.folio{{display:flex;justify-content:space-between;font-family:'Space Mono',monospace;font-size:7.5pt;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-2);border-bottom:.5pt solid var(--rule);padding-bottom:5pt}}
.folio .dot{{color:var(--accent)}}
.masthead{{text-align:center;padding:14pt 0 8pt;border-bottom:2.5pt double var(--rule-strong)}}
.masthead h1{{font-family:'Fraunces',serif;font-weight:900;font-size:58pt;line-height:.9;letter-spacing:-.02em}}
.masthead .tag{{font-family:'Space Mono',monospace;font-size:7.5pt;letter-spacing:.26em;text-transform:uppercase;color:var(--ink-2);margin-top:8pt}}
.lead{{padding:12pt 0 8pt;border-bottom:.5pt solid var(--rule)}}
.lead .kicker{{font-size:8pt}}
.lead h2{{font-family:'Fraunces',serif;font-weight:800;font-size:30pt;line-height:1.0;letter-spacing:-.015em;margin:5pt 0 8pt}}
.lead .body{{columns:2;column-gap:9mm;text-align:justify}}
.lead .body p{{margin-bottom:5pt}}
.lead .body .leadin{{font-family:'Fraunces',serif;font-weight:900;font-size:12pt;font-variant:small-caps;letter-spacing:.03em;color:var(--accent)}}
.byline{{font-family:'Space Mono',monospace;font-size:7pt;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);margin-top:7pt}}
.byline b{{color:var(--accent)}}
.section-head{{display:flex;align-items:center;gap:8pt;margin:16pt 0 9pt;break-after:avoid;break-inside:avoid}}
.section-head h2{{font-family:'Space Mono',monospace;font-size:9pt;letter-spacing:.22em;text-transform:uppercase;font-weight:700;white-space:nowrap}}
.section-head .line{{flex:1;height:.8pt;background:var(--rule-strong)}}
.section-head .count{{font-family:'Space Mono',monospace;font-size:7pt;color:var(--ink-3)}}
.cols{{columns:2;column-gap:9mm}}
.story{{break-inside:avoid;margin-bottom:7pt;padding-bottom:6pt;border-bottom:.5pt solid var(--rule)}}
.story .kicker{{font-size:6.5pt;margin-bottom:2pt}}
.story h3{{font-family:'Fraunces',serif;font-weight:700;font-size:12.5pt;line-height:1.08;letter-spacing:-.01em;margin-bottom:3pt}}
.story p{{font-size:9pt;color:var(--ink-2);margin-bottom:3pt}}
.story .src{{font-family:'Space Mono',monospace;font-size:6.5pt;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}}
.story .src b{{color:var(--accent)}}
.colophon{{margin-top:16pt;border-top:2.5pt double var(--rule-strong);padding-top:8pt;font-family:'Space Mono',monospace;font-size:7pt;letter-spacing:.05em;color:var(--ink-3);line-height:1.6;break-inside:avoid}}
.colophon b{{color:var(--ink)}}
"""


def _card(a) -> str:
    summ = f"<p>{esc(a.summary)}</p>" if a.summary else ""
    return (f'<article class="story"><span class="kicker">{esc(a.beat.split(" & ")[0])}</span>'
            f'<h3>{esc(a.title)}</h3>{summ}'
            f'<div class="src"><b>{esc(a.source)}</b> · {fmt_time(a.published)}</div></article>')


def _html(by_beat, lead, date, total, src_count, feeds) -> str:
    w = lead.summary.split()
    mid = len(w) // 2 or len(w)
    p1 = f'<span class="leadin">{esc(" ".join(w[:4]))}</span> {esc(" ".join(w[4:mid]))}'
    p2 = esc(" ".join(w[mid:]))
    used = {lead.link}
    fp = []
    for arts in by_beat.values():
        for a in arts:
            if a.link not in used:
                fp.append(a); used.add(a.link); break
        if len(fp) >= 4:
            break
    secs = []
    for beat, arts in by_beat.items():
        rest = [a for a in arts if a.link != lead.link]
        if not rest:
            continue
        secs.append(f'<div class="section-head"><h2>{esc(beat)}</h2><span class="line"></span>'
                    f'<span class="count">{len(rest):02d} stories</span></div>'
                    f'<div class="cols">{"".join(_card(a) for a in rest)}</div>')
    srcs = ", ".join(sorted({s for sl in feeds.values() for s, _ in sl}))
    ld = _long_date(date)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{_css(date)}</style></head><body>
<div class="folio"><span>{esc(ld)}</span><span>Vol. I <span class="dot">·</span> No. {_issue(date):03d}</span>
<span>{total} stories <span class="dot">·</span> {src_count} sources</span></div>
<header class="masthead"><h1>{esc(NAME)}</h1><div class="tag">{esc(TAGLINE)}</div></header>
<section class="lead"><span class="kicker">Lead Story · {esc(lead.beat)}</span><h2>{esc(lead.title)}</h2>
<div class="body"><p>{p1}</p><p>{p2}</p></div>
<div class="byline">Filed by <b>{esc(lead.source)}</b> · {fmt_time(lead.published)} · {esc(lead.domain)}</div></section>
<div class="section-head"><h2>The Front Page</h2><span class="line"></span></div>
<div class="cols">{"".join(_card(a) for a in fp)}</div>
{"".join(secs)}
<footer class="colophon"><b>{esc(NAME)}</b> is compiled automatically by an RSS-crawling agent.
Headlines link to their original publishers; summaries are condensed from each outlet's feed.<br>
<b>Wire sources ·</b> {esc(srcs)}</footer></body></html>"""


def render_pdf(by_beat, lead, date, total, src_count, feeds, out_path) -> Path:
    from weasyprint import HTML            # imported lazily so it's optional
    html_str = _html(by_beat, lead, date, total, src_count, feeds)
    HTML(string=html_str, base_url=str(Path(__file__).parent)).write_pdf(str(out_path))
    return Path(out_path)


# --------------------------------------------------------------------------- #
#  EMAIL SUMMARY                                                              #
# --------------------------------------------------------------------------- #

def email_summary(by_beat, lead, date, total):
    """Return (subject, plain-text body) — a digest suitable for an email body."""
    ld = _long_date(date)
    subject = f"{NAME} — IT Daily, {date.strftime('%a %b %d, %Y')} ({total} stories)"
    lines = [
        "Good morning,", "",
        f"Today's IT briefing — {total} stories across {len([b for b in by_beat if by_beat[b]])} "
        f"beats. Full edition (with working links) attached as PDF.", "",
        f"LEAD — {lead.title}",
        f"{lead.summary}  ({lead.source})", "",
    ]
    for beat, arts in by_beat.items():
        rest = [a for a in arts if a.link != lead.link][:3]
        if not rest:
            continue
        lines.append(beat.upper())
        for a in rest:
            lines.append(f"  • {a.title} ({a.source})")
        lines.append("")
    lines += [f"— {NAME}, auto-compiled {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    return subject, "\n".join(lines)


if __name__ == "__main__":
    import edition_data
    data, lead, total, src_count = edition_data.get_edition()
    d = dt.date(2026, 6, 1)
    render_pdf(data, lead, d, total, src_count, edition_data.m.FEEDS, "the-bitstream-2026-06-01.pdf")
    subj, body = email_summary(data, lead, d, total)
    Path("email-summary.txt").write_text(f"Subject: {subj}\n\n{body}", encoding="utf-8")
    print("PDF + email-summary.txt written")
    print("SUBJECT:", subj)
