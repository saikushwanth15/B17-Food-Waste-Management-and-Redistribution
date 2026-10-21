"""Tiny UI helpers shared by all pages."""
import streamlit as st


def flash(message, kind="success"):
    """Remember a message so it survives st.rerun() and is shown on the next run."""
    st.session_state["_flash"] = (kind, message)


def show_flash():
    if "_flash" in st.session_state:
        kind, message = st.session_state.pop("_flash")
        getattr(st, kind)(message)
