"""Feedback dialog: thumbs, "what should come next?" and optional free text.

Only shown when telemetry is on (otherwise the answers would go nowhere).
Vote counts are never shown, and the free text is never displayed in the app.
"""
from __future__ import annotations

from typing import Iterable, Optional

import streamlit as st

from telemetry.events import enabled, log_event

# Stored as keys, not labels: labels can change, old rows stay readable.
# Never reuse a key with a new meaning: old rows keep the old one.
# "factory_planning" (until v3.0) meant the planner that already exists;
# "factory_from_save" is the new idea.
NEXT_FEATURES = {
    "supply_chain": "Supply chain page",
    "factory_from_save": "Factory from your save",
}
# One line per feature, same keys as NEXT_FEATURES, shown under the pills.
FEATURE_HELP = {
    "supply_chain": "Imports, warehouses and deliveries to your shops in one place: "
                    "paused imports, items that run out, stock that isn't moving.",
    "factory_from_save": "Load your factory from the save (machines, workers, recipes) "
                         "and check if production covers what your shops sell.",
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


def _feedback_form(page: str) -> None:
    """Body of the dialog. Inside st.dialog every click reruns only the dialog,
    not the page behind it: nothing closes or recalculates while the user answers."""
    st.markdown("**Is the analyzer useful to you?**")
    rating = st.feedback("thumbs", key="fb_rating")          # 1 = up, 0 = down, None
    options = list(NEXT_FEATURES.values()) + [OTHER_LABEL]
    topics = st.pills("What should come next?", options,
                      selection_mode="multi", key="fb_topics") or []
    st.caption("  \n".join(f"**{NEXT_FEATURES[k]}**: {text}" for k, text in FEATURE_HELP.items()))
    other = ""
    if OTHER_LABEL in topics:
        other = st.text_area("What would you like?", max_chars=OTHER_MAX_CHARS,
                             key="fb_other")
    st.caption("Anonymous: no save data is recorded. Answers are only read by the developer.")
    nothing = rating is None and not topics
    if st.button("Send", key="fb_send", type="primary", disabled=nothing):
        log_event("feedback_sent", page=page, **feedback_props(rating, topics, other))
        st.session_state[_SENT_KEY] = True
        st.rerun()                                            # closes the dialog


@st.dialog("💬 Feedback — what should come next?")
def _feedback_dialog(page: str) -> None:
    _feedback_form(page)


def render_feedback_button(page: str) -> None:
    """Sidebar button that opens the feedback dialog. Hidden when telemetry is off."""
    if not enabled():
        return
    if st.session_state.get(_SENT_KEY):
        st.caption("💬 Thanks for the feedback!")
        return
    if st.button("💬 Feedback", key="fb_open", width="stretch",
                 help="Tell us if the analyzer helps and what should come next."):
        _feedback_dialog(page)
