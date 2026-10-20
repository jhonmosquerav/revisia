"""Sink de metas por contexto (spec 2026-10-18 §4.4, D14).

Cada intento de llamada a un LLM produce una ``RunMeta`` (una por intento). Para
que llegue a ``llm_calls.jsonl`` sin que los proveedores conozcan el run, quien
llama instala un *sink* y el proveedor hace ``emit(meta)``.

Se usa un ``ContextVar`` y no un global: las llamadas de un registro no deben
mezclarse con las de otro, y un hilo nuevo (sin ``contextvars.copy_context()``)
no hereda los sinks del padre. Ese aislamiento es lo que D14 necesita.

PR-0 solo define el mecanismo, sin consumidores; PR-A engancha ``journaled`` y
``RunContext.record_meta``.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from revisia.provenance.runmeta import RunMeta

MetaSink = Callable[[RunMeta], None]

_SINKS: contextvars.ContextVar[tuple[MetaSink, ...]] = contextvars.ContextVar(
    "revisia_meta_sinks", default=()
)


def active_sinks() -> tuple[MetaSink, ...]:
    """Los sinks activos en este contexto, del más externo al más interno."""
    return _SINKS.get()


def current_sink() -> MetaSink | None:
    """El sink más interno activo, o ``None`` si no hay ninguno."""
    sinks = _SINKS.get()
    return sinks[-1] if sinks else None


def emit(meta: RunMeta) -> None:
    """Entrega ``meta`` a todos los sinks activos, del más externo al más interno.

    No atrapa excepciones: un fallo al escribir ``llm_calls.jsonl`` tiene que
    verse, D14 no admite metas perdidas en silencio. Sin sinks, no hace nada.
    """
    for sink in _SINKS.get():
        sink(meta)


@contextmanager
def installed(sink: MetaSink) -> Iterator[None]:
    """Activa ``sink`` durante el bloque y lo retira al salir (también si lanza)."""
    token = _SINKS.set((*_SINKS.get(), sink))
    try:
        yield
    finally:
        _SINKS.reset(token)


@contextmanager
def collecting() -> Iterator[list[RunMeta]]:
    """Activa un sink que acumula en la lista devuelta; al salir lo retira."""
    metas: list[RunMeta] = []
    with installed(metas.append):
        yield metas
