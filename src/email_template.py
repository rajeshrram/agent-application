"""Renders the daily status email as HTML -- deterministically, from the
structured StatusEntry data, not from the LLM's free-text summary. The LLM
narrative is still generated (src/llm.generate_summary) and used as the
draft text for the DB / approval UI, and included here as an intro line,
but the per-person table below it is built directly from real rows so a
model wording quirk can never scramble who's actually blocked.

Table-based layout with inline styles throughout (no external CSS, no
flexbox/grid) so it renders consistently across Gmail, Outlook, and mobile
mail clients -- not just a modern browser.
"""
import html
from typing import Dict, List

from src.status_style import STATUS_STYLE, style_for

_INK = "#161A22"
_MUTED = "#5B6472"
_BORDER = "#E3E6EC"


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def _status_pill(status: str) -> str:
    style = style_for(status)
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
        f'background:{style["bg"]};color:{style["fg"]};font-size:12px;font-weight:600;'
        f'font-family:Helvetica,Arial,sans-serif;white-space:nowrap;">{_esc(style["label"])}</span>'
    )


def render_status_email_html(date: str, entries: List[Dict], narrative: str) -> str:
    """entries: list of {name, classified_status, blocker_description}."""
    counts = {"on_track": 0, "blocked": 0, "at_risk": 0, "no_response": 0}
    for e in entries:
        counts[e["classified_status"]] = counts.get(e["classified_status"], 0) + 1

    stat_cells = "".join(
        f'<td align="center" style="padding:14px 8px;">'
        f'<div style="font-family:Helvetica,Arial,sans-serif;font-size:26px;font-weight:700;'
        f'color:{STATUS_STYLE[key]["fg"]};line-height:1;">{counts[key]}</div>'
        f'<div style="font-family:Helvetica,Arial,sans-serif;font-size:11px;color:{_MUTED};'
        f'text-transform:uppercase;letter-spacing:0.04em;margin-top:4px;">{STATUS_STYLE[key]["label"]}</div>'
        f"</td>"
        for key in ("on_track", "blocked", "at_risk", "no_response")
    )

    rows = ""
    for e in sorted(entries, key=lambda e: e["classified_status"] != "blocked"):
        blocker = e.get("blocker_description") or "—"
        rows += (
            f'<tr>'
            f'<td style="padding:12px 4px;border-top:1px solid {_BORDER};font-family:Helvetica,Arial,sans-serif;'
            f'font-size:14px;color:{_INK};font-weight:600;white-space:nowrap;">{_esc(e["name"])}</td>'
            f'<td style="padding:12px 4px;border-top:1px solid {_BORDER};white-space:nowrap;">{_status_pill(e["classified_status"])}</td>'
            f'<td style="padding:12px 4px;border-top:1px solid {_BORDER};font-family:Helvetica,Arial,sans-serif;'
            f'font-size:13px;color:{_MUTED};">{_esc(blocker)}</td>'
            f"</tr>"
        )
    if not entries:
        rows = (
            f'<tr><td colspan="3" style="padding:16px 4px;font-family:Helvetica,Arial,sans-serif;'
            f'font-size:13px;color:{_MUTED};">No status recorded for this date.</td></tr>'
        )

    return f"""\
<!doctype html>
<html>
<body style="margin:0;padding:0;background:#EDEFF2;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EDEFF2;padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0"
               style="background:#FFFFFF;border:1px solid {_BORDER};border-radius:12px;overflow:hidden;max-width:600px;width:100%;">
          <tr>
            <td style="padding:24px 28px 8px;">
              <div style="font-family:Helvetica,Arial,sans-serif;font-size:11px;font-weight:600;letter-spacing:0.06em;
                          text-transform:uppercase;color:{_MUTED};">Pulse</div>
              <div style="font-family:Helvetica,Arial,sans-serif;font-size:22px;font-weight:700;color:{_INK};margin-top:4px;">
                {_esc(date)}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 20px 4px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>{stat_cells}</tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:4px 28px 8px;">
              <div style="font-family:Helvetica,Arial,sans-serif;font-size:13.5px;line-height:1.6;color:{_INK};
                          border-top:1px solid {_BORDER};padding-top:16px;">
                {_esc(narrative)}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 28px 24px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                {rows}
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:14px 28px;background:#F7F8FA;border-top:1px solid {_BORDER};">
              <div style="font-family:Helvetica,Arial,sans-serif;font-size:11.5px;color:{_MUTED};">
                Sent automatically by Pulse · JIRA + Slack + Nebius + Gmail
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
