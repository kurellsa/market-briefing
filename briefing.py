#!/usr/bin/env python3
"""Daily market briefing — Groq (Llama 3.3 70B) + Tavily + Gmail SMTP."""

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

from groq import Groq
from tavily import TavilyClient

# ── Config ────────────────────────────────────────────────────────────────────
RECIPIENTS = ["nagapavan.mummadi@gmail.com", "stevehydr@gmail.com"]
TIMEZONE   = "America/New_York"
MODEL      = "llama-3.3-70b-versatile"

SEARCH_QUERIES = [
    "US stock market premarket futures S&P 500 Nasdaq {date}",
    "biggest stock movers premarket earnings news {date}",
    "US Treasury yields dollar index DXY gold oil prices {date}",
    "Federal Reserve macro economic data CPI jobs news {date}",
    "geopolitical risk market sentiment news {date}",
]

SYSTEM_PROMPT = """You are a professional markets strategist writing a concise daily \
morning briefing for an active individual investor (mix of swing trades and long-term \
core positions, US Eastern timezone). Be direct, precise, and actionable. \
Highlight narrative/data mismatches. Describe scenarios — never forecast prices."""

BRIEFING_PROMPT = """\
Today's date: {date}

Using ONLY the search results provided, write a morning market briefing in the exact \
structure below. Keep total prose to 600–800 words. Output clean HTML for an email \
(use <h2>, <p>, <ul>, <li>, <table>, <strong>, <em>; no <html>/<head>/<body> tags).

<structure>
<h2>What Matters Most This Morning</h2>
2–3 sentence summary of the single most important market-moving theme.

<h2>Pre-Market Snapshot</h2>
HTML table: Index | Futures | Change%. Include S&P 500, Nasdaq, Dow, Russell 2000.
Add VIX and one or two notable global indices if relevant.
One line: Sentiment (risk-on / risk-off / mixed) and primary reason.

<h2>Market Movers</h2>
Bulleted list: 5–10 stocks or ETFs with move size, direction, one-line reason
(earnings, guidance, macro, M&A, regulatory). Flag any mega-cap or sector-leader moves.

<h2>Macro & Rates</h2>
Key data released in the last 24h and scheduled today — one sentence each on why it matters.
2-year and 10-year Treasury yields + what they signal for growth/inflation.

<h2>Cross-Asset Check</h2>
Dollar index (DXY), oil (WTI/Brent), gold. Crypto only if risk-sentiment relevant.
1–2 sentences: do cross-assets confirm or contradict the equity narrative?

<h2>Short-Term Setups (Today / This Week)</h2>
3–6 numbered items to watch over the next 1–5 trading days.
For each: what outcome would be bullish, bearish, or a non-event.

<h2>Longer-Term Currents</h2>
3–5 ongoing themes beyond this week (AI capex, rate-cut path, credit, geopolitics, etc.).
For each: does today's newsflow strengthen, weaken, or leave this theme unchanged?

<h2>Key Takeaways</h2>
Max 5 bullets. 1–2 on macro/policy. 1–2 on indices/sectors. 1–2 on single-name stories.
Each bullet = cause + likely effect (not just a headline).

<hr>
<p><strong>Sources</strong></p>
<ul>Hyperlinked list of sources used.</ul>
</structure>

If data is uncertain or conflicting, say so explicitly.
Flag any move that looks like a potential overreaction.

--- SEARCH RESULTS ---
{search_results}
--- END SEARCH RESULTS ---
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_today() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%A, %B %d, %Y")


def run_searches(tavily: TavilyClient, date: str) -> str:
    blocks = []
    for template in SEARCH_QUERIES:
        query = template.format(date=date)
        try:
            resp = tavily.search(query=query, search_depth="basic", max_results=5)
            blocks.append(f"### Query: {query}")
            for r in resp.get("results", []):
                title   = r.get("title", "")
                content = r.get("content", "").strip()
                url     = r.get("url", "")
                blocks.append(f"**{title}**\n{content}\n{url}")
        except Exception as exc:
            blocks.append(f"[Search failed for '{query}': {exc}]")
    return "\n\n".join(blocks)


def generate_briefing(client: Groq, date: str, search_results: str) -> str:
    prompt = BRIEFING_PROMPT.format(date=date, search_results=search_results)
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=2500,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    )
    return response.choices[0].message.content or ""


def wrap_html(body: str, date: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body  {{ font-family: -apple-system, Arial, sans-serif; max-width: 680px;
             margin: 0 auto; padding: 24px 16px; color: #1a1a1a; line-height: 1.55; }}
    h1   {{ color: #0a2342; border-bottom: 3px solid #0a2342; padding-bottom: 8px;
            font-size: 20px; margin-bottom: 4px; }}
    h2   {{ color: #0a2342; font-size: 15px; margin-top: 22px; margin-bottom: 6px;
            text-transform: uppercase; letter-spacing: 0.5px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 14px; }}
    th   {{ background: #0a2342; color: #fff; padding: 7px 11px; text-align: left; }}
    td   {{ padding: 6px 11px; border-bottom: 1px solid #e4e8ee; }}
    tr:nth-child(even) {{ background: #f6f8fb; }}
    ul   {{ padding-left: 18px; margin: 6px 0; }}
    li   {{ margin: 5px 0; font-size: 14px; }}
    p    {{ font-size: 14px; margin: 6px 0; }}
    hr   {{ border: none; border-top: 1px solid #dde2ea; margin: 20px 0; }}
    .footer {{ font-size: 11px; color: #999; margin-top: 16px; }}
    a    {{ color: #0a2342; }}
  </style>
</head>
<body>
  <h1>Morning Market Briefing &mdash; {date}</h1>
  {body}
  <p class="footer">Generated by Llama 3.3 70B via Groq &middot; For informational purposes only &middot; Not investment advice.</p>
</body>
</html>"""


def send_email(html: str, date: str) -> None:
    sender   = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    subject  = f"Morning Market Briefing — {date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Market Briefing <{sender}>"
    msg["To"]      = ", ".join(RECIPIENTS)

    msg.attach(MIMEText("Please open this email in an HTML-capable client.", "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(sender, password)
        smtp.sendmail(sender, RECIPIENTS, msg.as_string())

    print(f"Sent to: {', '.join(RECIPIENTS)}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    date = get_today()
    print(f"[1/4] Date: {date}")

    tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    groq   = Groq(api_key=os.environ["GROQ_API_KEY"])

    print("[2/4] Running web searches...")
    search_results = run_searches(tavily, date)

    print("[3/4] Generating briefing with Llama 3.3 70B (Groq)...")
    briefing_html = generate_briefing(groq, date, search_results)

    print("[4/4] Sending email...")
    full_html = wrap_html(briefing_html, date)
    send_email(full_html, date)

    print("Done.")


if __name__ == "__main__":
    main()

