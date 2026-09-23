"""Feedback box: thumbs, "what should come next?" and optional free text.

Only shown when telemetry is on (otherwise the answers would go nowhere).
Vote counts are never shown, and the free text is never displayed in the app.
"""
from __future__ import annotations

from typing import Iterable, Optional

import streamlit as st

from telemetry.events import enabled, log_event

# Stored as keys, not labels: labels can change, old rows stay readable.
NEXT_FEATURES = {
    "supply_chain": "Supply chain page",
    "factory_planning": "Factory planning",
}
OTHER_KEY, OTHER_LABEL = "other", "Something else"
OTHER_MAX_CHARS = 300
_SENT_KEY = "_feedback_sent"


def feedback_props(rating: Optional[int], topics: Iterable[str], other_text: str) -> dict:
    """Widget values → props of the feedback_sent event."""
    label_to_key = {label: key for key, label in NEXT_FEATURES.items()}
    label_to_key[OTHER_LABEL] = OTHER_KEY
    keys = [label_to_key[t] for t in (topics or []) if t in label_to_key]
    text = (other_text or "").strip()[:OTHER_MAX_CHARS] or None
    if OTHER_KEY not in keys:
        text = None                            # text only counts with "Something else"
    return {"rating": rating, "topics": keys, "other_text": text}


def render_feedback(page: str) -> None:
    if not enabled():
        return
    with st.expander("💬 Feedback — what should come next?"):
        if st.session_state.get(_SENT_KEY):
            st.caption("Thanks, noted.")
            return
        st.markdown("**Is the analyzer useful to you?**")
        rating = st.feedback("thumbs", key="fb_rating")          # 1 = up, 0 = down, None
        options = list(NEXT_FEATURES.values()) + [OTHER_LABEL]
        topics = st.pills("What should come next?", options,
                          selection_mode="multi", key="fb_topics") or []
        other = ""
        if OTHER_LABEL in topics:
            other = st.text_area("What would you like?", max_chars=OTHER_MAX_CHARS,
                                 key="fb_other")
        nothing = rating is None and not topics
        if st.button("Send", key="fb_send", disabled=nothing):
            log_event("feedback_sent", page=page, **feedback_props(rating, topics, other))
            st.session_state[_SENT_KEY] = True
            st.caption("Thanks, noted.")
        st.caption("Anonymous: no save data is recorded. Answers are only read by the developer.")
