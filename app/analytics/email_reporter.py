"""SMTP email reporter for daily cost summary.

Uses aiosmtplib for async. Falls back to logging if SMTP not configured.
"""
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EmailMessage_:
    to: list[str]
    subject: str
    body_html: str
    body_text: str


async def send_email(msg: EmailMessage_) -> bool:
    """Send via SMTP. Returns True on success."""
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        logger.info("smtp_not_configured_logging_only", subject=msg.subject, to=msg.to)
        logger.info("email_body_text", body=msg.body_text[:2000])
        return False

    try:
        import aiosmtplib

        email = EmailMessage()
        email["From"] = settings.SMTP_FROM
        email["To"] = ", ".join(msg.to)
        email["Subject"] = msg.subject
        email.set_content(msg.body_text)
        email.add_alternative(msg.body_html, subtype="html")

        await aiosmtplib.send(
            email,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_USE_TLS,
            start_tls=not settings.SMTP_USE_TLS and settings.SMTP_PORT == 587,
        )
        logger.info("email_sent", to=msg.to, subject=msg.subject)
        return True
    except Exception as e:
        logger.warning("email_send_failed", error=str(e))
        return False


def format_daily_cost_email(report: dict) -> EmailMessage_:
    """Build the daily cost email from analytics.queries.daily_cost_report output."""
    day = report.get("day", "")
    summary = report.get("summary", {})
    by_model = report.get("by_model", [])
    csat = report.get("csat", {})

    messages = summary.get("messages", 0)
    tokens = summary.get("tokens", 0)
    cost = summary.get("cost_usd", 0)
    cached = summary.get("cached", 0)
    cache_pct = (cached / messages * 100) if messages else 0

    up = csat.get("up", 0)
    down = csat.get("down", 0)
    csat_score = csat.get("csat")
    csat_str = f"{csat_score * 100:.0f}%" if csat_score is not None else "no feedback"

    # HTML body
    model_rows_html = "".join(
        f"<tr><td>{m.get('model', '?')}</td>"
        f"<td style='text-align:right'>{m.get('message_count', 0):,}</td>"
        f"<td style='text-align:right'>${m.get('cost_usd', 0):.4f}</td></tr>"
        for m in by_model
    )
    body_html = f"""
    <h2>Daily Chatbot Report — {day}</h2>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">
      <tr><td><b>Messages</b></td><td>{messages:,}</td></tr>
      <tr><td><b>Tokens</b></td><td>{tokens:,}</td></tr>
      <tr><td><b>Cost</b></td><td>${cost}</td></tr>
      <tr><td><b>Cached</b></td><td>{cached:,} ({cache_pct:.0f}%)</td></tr>
      <tr><td><b>CSAT</b></td><td>{csat_str} (👍 {up} / 👎 {down})</td></tr>
    </table>
    <h3>By model</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">
      <tr><th>Model</th><th>Messages</th><th>Cost</th></tr>
      {model_rows_html or '<tr><td colspan="3">No traffic today</td></tr>'}
    </table>
    """

    # Plain text body (fallback for clients without HTML)
    model_rows_text = "\n".join(
        f"  - {m.get('model', '?')}: {m.get('message_count', 0):,} msgs / ${m.get('cost_usd', 0):.4f}"
        for m in by_model
    )
    body_text = f"""Daily Chatbot Report — {day}

Messages: {messages:,}
Tokens:   {tokens:,}
Cost:     ${cost}
Cached:   {cached:,} ({cache_pct:.0f}%)
CSAT:     {csat_str} (👍 {up} / 👎 {down})

By model:
{model_rows_text or '  (no traffic today)'}
"""

    to_list = [e.strip() for e in settings.COST_REPORT_RECIPIENTS.split(",") if e.strip()]
    return EmailMessage_(
        to=to_list,
        subject=f"[Chatbot] Daily cost — {day} — ${cost}",
        body_html=body_html,
        body_text=body_text,
    )
