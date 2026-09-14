"""Single source of truth for how a classified status is labeled and
colored -- shared by the HTML email (src/email_template.py) and the
Streamlit dashboard (streamlit_app.py) so they can't drift apart."""

STATUS_STYLE = {
    "on_track": {"label": "On track", "bg": "#E6F4EA", "fg": "#1E7A42"},
    "blocked": {"label": "Blocked", "bg": "#FBEAE5", "fg": "#B8452E"},
    "at_risk": {"label": "At risk", "bg": "#FCF3E3", "fg": "#B8791E"},
    "no_response": {"label": "No response", "bg": "#F1F3F7", "fg": "#5B6472"},
}

FALLBACK_STYLE = {"label": "Unknown", "bg": "#F1F3F7", "fg": "#5B6472"}


def style_for(status: str) -> dict:
    return STATUS_STYLE.get(status, {**FALLBACK_STYLE, "label": status})
