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

Using ONLY the search results provided, write a morning market briefing following the
exact structure below. Keep total prose to 600–800 words.

Output clean HTML for an email body (no <html>/<head>/<body> tags).
Use these CSS classes for color-coding — they are already defined in the email template:
  - <span class="pos">+1.2%</span>   → green  (gains, bullish signals, rate-cut odds up)
  - <span class="neg">-1.4%</span>   → red    (losses, bearish signals, warnings)
  - <span class="neu">flat</span>    → grey   (unchanged, neutral)
  - <span class="badge bull">RISK-ON</span>  or  <span class="badge bear">RISK-OFF</span>
    or  <span class="badge mix">MIXED</span>   → sentiment pill in Pre-Market Snapshot
  - Wrap the entire Key Takeaways section in <div class="takeaways">...</div>
  - Wrap each theme status word in Longer-Term Currents:
      <span class="tag str">Strengthened</span> / <span class="tag wkn">Weakened</span> /
      <span class="tag unc">Unchanged</span>

<structure>
<h2>What Matters Most This Morning</h2>
2–3 sentence summary of the single most important market-moving theme.

<h2>Pre-Market Snapshot</h2>
HTML table with columns: Index | Direction | Change% (use pos/neg spans on the % values).
Include S&P 500, Nasdaq, Dow, Russell 2000, VIX. Add global indices if notable.
One line with a sentiment badge and primary reason.

<h2>Market Movers</h2>
Bulleted list: 5–10 stocks/ETFs. Wrap each move % in pos or neg span. One-line reason each.

<h2>Macro & Rates</h2>
Key data last 24h + scheduled today — one sentence each on why it matters.
2-year and 10-year Treasury yields (use pos/neg as appropriate) + what they signal.

<h2>Cross-Asset Check</h2>
DXY, oil (WTI/Brent), gold — use pos/neg spans on moves. Crypto only if risk-sentiment relevant.
1–2 sentences: do cross-assets confirm or contradict the equity narrative?

<h2>Short-Term Setups (Today / This Week)</h2>
3–6 numbered items. For each: what is bullish, bearish, or a non-event.

<h2>Longer-Term Currents</h2>
3–5 themes. For each, end with a tag: Strengthened / Weakened / Unchanged.

<h2>Key Takeaways</h2>
Wrap in <div class="takeaways"><ul>...</ul></div>.
Max 5 bullets. 1–2 macro/policy. 1–2 indices/sectors. 1–2 single-name stories.
Each bullet = cause + likely effect.

<hr>
<p><strong>Sources</strong></p>
<ul>Hyperlinked list of sources used.</ul>
</structure>

Flag data conflicts and potential overreactions explicitly.

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
    /* ── Reset & base ── */
    body      {{ font-family: -apple-system, Arial, sans-serif; max-width: 680px;
                margin: 0 auto; background: #f0f2f5; padding: 0; color: #1a1a1a; }}
    .wrapper  {{ background: #ffffff; border-radius: 8px; overflow: hidden;
                margin: 16px auto; box-shadow: 0 2px 12px rgba(0,0,0,.10); }}

    /* ── Header banner ── */
    .header   {{ background: linear-gradient(135deg, #0a2342 0%, #1a4a7a 100%);
                padding: 22px 28px 16px; }}
    .header h1 {{ color: #ffffff; font-size: 20px; margin: 0 0 4px;
                 letter-spacing: 0.3px; }}
    .header .sub {{ color: #a8c4e0; font-size: 12px; margin: 0; }}

    /* ── Content area ── */
    .content  {{ padding: 20px 28px 8px; }}

    /* ── Section headers ── */
    h2 {{ font-size: 11px; font-weight: 700; text-transform: uppercase;
          letter-spacing: 1px; color: #0a2342; margin: 24px 0 8px;
          padding-left: 10px; border-left: 3px solid #1a6fbc; }}

    /* ── Tables ── */
    table  {{ border-collapse: collapse; width: 100%; margin: 8px 0 12px;
              font-size: 13px; }}
    th     {{ background: #0a2342; color: #fff; padding: 8px 12px;
              text-align: left; font-weight: 600; font-size: 12px; }}
    td     {{ padding: 7px 12px; border-bottom: 1px solid #edf0f4; }}
    tr:nth-child(even) td {{ background: #f7f9fc; }}

    /* ── Lists ── */
    ul  {{ padding-left: 20px; margin: 4px 0 10px; }}
    ol  {{ padding-left: 20px; margin: 4px 0 10px; }}
    li  {{ margin: 6px 0; font-size: 14px; line-height: 1.5; }}
    p   {{ font-size: 14px; margin: 6px 0 10px; line-height: 1.6; }}

    /* ── Color classes ── */
    .pos  {{ color: #15803d; font-weight: 600; }}
    .neg  {{ color: #dc2626; font-weight: 600; }}
    .neu  {{ color: #6b7280; font-weight: 500; }}

    /* ── Sentiment badges ── */
    .badge      {{ display: inline-block; padding: 2px 10px; border-radius: 99px;
                   font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }}
    .badge.bull {{ background: #dcfce7; color: #15803d; }}
    .badge.bear {{ background: #fee2e2; color: #dc2626; }}
    .badge.mix  {{ background: #fef9c3; color: #92400e; }}

    /* ── Theme status tags ── */
    .tag      {{ display: inline-block; padding: 1px 8px; border-radius: 4px;
                 font-size: 11px; font-weight: 600; }}
    .tag.str  {{ background: #dcfce7; color: #15803d; }}
    .tag.wkn  {{ background: #fee2e2; color: #dc2626; }}
    .tag.unc  {{ background: #f1f5f9; color: #475569; }}

    /* ── Key Takeaways box ── */
    .takeaways    {{ background: #f0f6ff; border: 1px solid #bfdbfe;
                    border-left: 4px solid #1a6fbc; border-radius: 6px;
                    padding: 12px 18px; margin: 8px 0 16px; }}
    .takeaways li {{ font-size: 13.5px; margin: 7px 0; }}

    /* ── Misc ── */
    hr      {{ border: none; border-top: 1px solid #e5e7eb; margin: 20px 0; }}
    a       {{ color: #1a6fbc; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .footer {{ font-size: 11px; color: #9ca3af; padding: 12px 28px 20px;
               border-top: 1px solid #e5e7eb; margin-top: 8px; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <h1>📊 Morning Market Briefing</h1>
      <p class="sub">{date} &nbsp;·&nbsp; US Eastern &nbsp;·&nbsp; Pre-market edition</p>
    </div>
    <div class="content">
      {body}
    </div>
    <p class="footer">
      Generated by Llama 3.3 70B via Groq &nbsp;·&nbsp;
      For informational purposes only &nbsp;·&nbsp; Not investment advice.
    </p>
  </div>
</body>
</html>"""


def send_email(html: str, date: str) -> None:
    sender   = "kurellsa@gmail.com"
    password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
    subject  = f"📊 Market Briefing — {date}"

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

