"""Session-local model state shared by the main page and model settings page."""

import streamlit as st

from agent.recommender import WeldingRecommender
from services.llm.router import LLMRouter


def get_recommender() -> WeldingRecommender:
    if "_recommender" not in st.session_state:
        st.session_state["_recommender"] = WeldingRecommender()
    agent = st.session_state["_recommender"]
    # Read configuration on rerun; retain model/status state when nothing changed.
    # Constructing a router does not perform any network calls.
    current = LLMRouter()
    if agent.llm.config != current.config or agent.llm.config_error != current.config_error:
        agent.llm = current
        if "recommendation" in st.session_state:
            st.session_state["_model_config_changed"] = True
    return agent
