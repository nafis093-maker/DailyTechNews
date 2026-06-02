# THE BITSTREAM — Daily Tech News

An automated IT-news daily. A small Python agent crawls technology RSS feeds and
renders a **magazine-style edition** as a web page, a print-quality **PDF**, and
an **email digest**. This repo is set up to host the web edition on **Vercel**
and to **regenerate itself every morning** via GitHub Actions.

- `index.html` — the live homepage (latest edition)
- `editions/` — dated archive (`YYYY-MM-DD.html` + `.pdf`)
- `it_news_agent.py` — the crawler/renderer (RSS → beats → magazine HTML)
- `render_print.py` — PDF + email-digest renderer
- `.github/workflows/daily.yml` — daily rebuild + commit (triggers Vercel redeploy)

---

## 1 · Push this to your GitHub repo

From inside this folder:

```bash
git init
git add .
git commit -m "Initial commit: THE BITSTREAM daily tech news"
git branch -M main
git remote add origin https://github.com/nafis093-maker/DailyTechNews.git
git push -u origin main
```

If the repo already has commits and the push is rejected, either start clean
(`git push -u origin main --force`, only if you're sure it's empty) or pull
first (`git pull origin main --allow-unrelated-histories`) and re-push.

> A git repo is already initialized in this folder with the first commit made,
> so in practice you may only need the `git remote add` + `git push` lines.

---

## 2 · Host it on Vercel

1. Go to **vercel.com → Add New… → Project**.
2. **Import** the `DailyTechNews` repo (authorize GitHub if prompted).
3. Vercel detects a **static site** — leave the defaults:
   - Framework Preset: **Other**
   - Build Command: **(empty)**
   - Output Directory: **(empty / root)**
4. Click **Deploy**.

Your site goes live at `https://dailytechnews-<something>.vercel.app`. The
homepage is `index.html`; past issues live under `/editions/`.

Because the repo is connected to Vercel, **every future `git push` auto-deploys** —
which is exactly what the daily workflow below relies on.

### Optional: deploy from the CLI instead

```bash
npm i -g vercel
vercel            # follow the prompts, link to the repo
vercel --prod     # promote to production
```

---

## 3 · Make it update itself daily

The included GitHub Action (`.github/workflows/daily.yml`) runs every morning,
rebuilds the edition from live feeds, and commits the new files. The commit
triggers Vercel to redeploy, so the site stays current with no manual work.

To enable it:

1. On GitHub: **Settings → Actions → General → Workflow permissions →
   Read and write permissions** (lets the bot commit).
2. The schedule is `0 6 * * *` (06:00 UTC). Edit the cron in the workflow to
   change the time.
3. You can trigger a run anytime from the **Actions** tab → *Daily edition* →
   *Run workflow*.

---

## Run it locally

```bash
pip install -r requirements.txt
python it_news_agent.py --out . --open            # build + open the homepage
python it_news_agent.py --out . --pdf --summary   # also make the PDF + email digest
```

Outputs land at `index.html`, `latest.html`, and under `editions/`.
The email digest is written to `editions/<date>-email.txt` (subject line + body).

### Useful flags

| Flag | Meaning | Default |
|------|---------|---------|
| `--out DIR` | output directory (use `.` for this repo's root) | `./public` |
| `--pdf` | also render the print-quality PDF | off |
| `--summary` | also write the email digest | off |
| `--hours N` | only include stories newer than N hours (`0` = no filter) | `36` |
| `--per-section N` | max stories per beat | `5` |
| `--open` | open the homepage in your browser | off |

---

## Customize

Everything tunable lives at the top of `it_news_agent.py`:

- **`FEEDS`** — add/remove `(source label, RSS url)` pairs, or whole new beats.
- **`CLASSIFY_RULES`** — keywords that re-file stories into the right beat.
- **`MAGAZINE_NAME` / `TAGLINE`** — rename the publication.
- **`CSS`** (in `it_news_agent.py` for web, `render_print.py` for PDF) — the look.

## How it works

1. **Crawl** each feed (a dead feed is skipped, never fatal).
2. **Reclassify** stories from broad feeds into the most specific beat by keyword.
3. **Dedupe** by normalized title, keeping the newest copy.
4. **Filter** to recent stories; cap each beat.
5. **Pick a lead** — the newest story among the major beats.
6. **Render** the web page, the PDF, and the email digest.

The committed sample edition (June 1, 2026) was produced by this same code;
headlines are paraphrased and every story links to its original publisher.

## Notes

- The **web page** loads fonts from Google Fonts, so it needs no local font files.
- The **PDF** uses the bundled `fonts/` directory for offline-faithful rendering.
- PDF generation needs WeasyPrint's native libs (Pango/Cairo). The CI workflow
  installs them; locally see the WeasyPrint install docs for your OS.
