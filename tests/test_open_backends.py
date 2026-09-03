"""Tests de los backends abiertos nuevos (ERIC, DOAJ, UNESDOC, BVS). Todo offline."""

from __future__ import annotations

from revisia.agents import _http


def test_user_agent_identifica_a_revisia() -> None:
    assert _http.user_agent(None).startswith("revisia/")
    assert "mailto:x@y.z" in _http.user_agent("x@y.z")


def test_strip_html_limpia_etiquetas() -> None:
    assert _http.strip_html("<p>Hola <b>mundo</b></p>") == "Hola mundo"
    assert _http.strip_html(None) is None
    assert _http.strip_html("<p></p>") is None
