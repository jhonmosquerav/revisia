"""Sink de metas por contexto (spec 2026-10-18 §4.4, D14; PR-0 lo define, PR-A lo consume)."""

from __future__ import annotations

import threading

import pytest

from revisia.provenance.runmeta import RunMeta
from revisia.provenance.sink import active_sinks, collecting, current_sink, emit, installed


def _meta(n: int) -> RunMeta:
    return RunMeta(
        provider="fake", model="m", temperature=0.0, prompt_sha256=f"{n:064x}", response_sha256="r"
    )


def test_sin_sink_emit_no_hace_nada_y_current_sink_es_none() -> None:
    assert current_sink() is None
    assert active_sinks() == ()
    emit(_meta(1))  # no lanza


def test_collecting_recoge_en_orden_y_se_retira_al_salir() -> None:
    with collecting() as metas:
        emit(_meta(1))
        emit(_meta(2))
        assert current_sink() is not None
    assert [m.prompt_sha256 for m in metas] == [f"{1:064x}", f"{2:064x}"]
    assert current_sink() is None
    emit(_meta(3))
    assert len(metas) == 2  # fuera del bloque ya no recoge


def test_sinks_anidados_reciben_todos_del_externo_al_interno() -> None:
    orden: list[str] = []
    with installed(lambda m: orden.append("externo")), collecting() as internos:
        emit(_meta(1))
    assert orden == ["externo"] and len(internos) == 1


def test_un_sink_que_lanza_propaga_el_error_y_corta_la_entrega() -> None:
    recibidos: list[RunMeta] = []

    def roto(_m: RunMeta) -> None:
        raise OSError("disco lleno")

    with (
        installed(roto),
        collecting() as metas,
        pytest.raises(OSError),
        installed(recibidos.append),
    ):
        emit(_meta(1))
    # La entrega va del sink externo al interno y no atrapa errores: el externo (el que en PR-A
    # escribe llm_calls.jsonl) es el roto, así que ni el colector ni el interno reciben la meta.
    # D14 no admite una meta «recogida» que no llegó a disco.
    assert recibidos == [] and metas == []


def test_otro_hilo_no_ve_el_sink_del_padre() -> None:
    visto: list[tuple] = []
    with collecting():
        hilo = threading.Thread(target=lambda: visto.append(active_sinks()))
        hilo.start()
        hilo.join()
    assert visto == [()]


def test_el_contexto_se_restaura_aunque_el_bloque_lance() -> None:
    with pytest.raises(ValueError), collecting():
        raise ValueError("x")
    assert active_sinks() == ()
