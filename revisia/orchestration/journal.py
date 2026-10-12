"""Diario por etapa: reanudar sin repetir trabajo (Ola 1, D3; auditoría 2026-09-03, A9).

Hasta la Ola 1, ``decisions.json`` se escribía al final de cada bucle y los
``RunMeta`` solo llegaban a disco con el manifiesto: un 429 a mitad del cribado
perdía la etapa entera. Cada etapa con LLM o red escribe ahora una línea por
registro en su diario (``JOURNAL_PATHS``) en cuanto lo termina, y al reanudar
lo que ya está en el diario no se vuelve a calcular.

La clave de una entrada es ``(record_id, input_sha256)``, con
``input_sha256 = canonical_sha256(inputs)`` sobre lo que determina el resultado
(registro, pregunta, criterios, modelo…). Si algo de eso cambia, la entrada
queda obsoleta (sigue en el fichero y es válida) y el registro se recalcula.

Una caída a mitad de escritura deja, como mucho, la última línea truncada: al
cargar se recorta. Una línea corrupta en medio, o dos líneas con la misma clave
y distinta salida, son un ``JournalError``: alguien tocó el diario a mano y la
corrida ya no es fiable.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ValidationError

from revisia.provenance.runmeta import RunMeta, canonical_sha256
from revisia.schemas.artifacts import JOURNAL_PATHS, JournalEntry, JournalStage

if TYPE_CHECKING:
    from revisia.orchestration.run_context import RunContext

# TypeVar clásico y no PEP 695 (`def f[T]`): la suite también corre en 3.11/3.12.
ModelT = TypeVar("ModelT", bound=BaseModel)


class JournalError(ValueError):
    """Un diario (o ``llm_calls.jsonl``) inconsistente: no se puede reanudar con él."""


def read_jsonl(path: Path, model: type[ModelT]) -> list[ModelT]:  # noqa: UP047
    """Lee un JSONL append-only y valida cada línea con ``model``.

    Una última línea que no valida es la huella de una caída a mitad de
    escritura: se recorta del fichero (para que la siguiente no se pegue a ella)
    y se ignora. Una línea inválida antes de la última es corrupción y lanza
    ``JournalError`` con su número de línea. Si la última línea es válida pero
    le falta el salto final, se añade.
    """
    if not path.exists():
        return []
    data = path.read_bytes()
    lines = data.split(b"\n")
    last = max((i for i, line in enumerate(lines) if line.strip()), default=-1)
    items: list[ModelT] = []
    offset = 0
    for number, line in enumerate(lines):
        start = offset
        offset += len(line) + 1
        if not line.strip():
            continue
        try:
            items.append(model.model_validate_json(line))
        except ValidationError as exc:
            if number != last:
                motivo = exc.errors()[0]["msg"]
                raise JournalError(f"{path}: línea {number + 1} corrupta ({motivo}).") from exc
            with path.open("r+b") as fh:
                fh.truncate(start)
            return items
    if data and not data.endswith(b"\n"):
        with path.open("ab") as fh:
            fh.write(b"\n")
    return items


def append_jsonl(path: Path, item: BaseModel) -> None:
    """Añade ``item`` como una línea y la fuerza a disco (``flush`` + ``fsync``).

    Saltos LF también en Windows: el diario se lee por bytes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(item.model_dump_json() + "\n")
        fh.flush()
        os.fsync(fh.fileno())


class StageJournal:
    """Diario de una etapa: ``lookup`` por ``(record_id, input_sha256)`` y ``append``."""

    def __init__(self, run_ctx: RunContext, stage: JournalStage) -> None:
        self.stage = stage
        self.path = run_ctx.run_dir / JOURNAL_PATHS[stage]
        self._entries: dict[tuple[str, str], JournalEntry] = {}
        for entry in read_jsonl(self.path, JournalEntry):
            if entry.stage != stage:
                raise JournalError(
                    f"{self.path}: entrada de la etapa {entry.stage!r} en el diario de {stage!r}."
                )
            key = (entry.record_id, entry.input_sha256)
            previous = self._entries.get(key)
            if previous is not None and previous.output != entry.output:
                raise JournalError(
                    f"{self.path}: dos entradas para {entry.record_id!r} con la misma entrada "
                    "y distinta salida."
                )
            self._entries.setdefault(key, entry)

    def lookup(self, record_id: str, input_sha256: str) -> JournalEntry | None:
        """Entrada vigente de ``record_id`` para esa entrada, o ``None``."""
        return self._entries.get((record_id, input_sha256))

    def append(self, entry: JournalEntry) -> None:
        """Escribe ``entry`` al final del diario, ya en disco al volver."""
        if entry.stage != self.stage:
            raise ValueError(f"entrada de {entry.stage!r} en el diario de {self.stage!r}")
        append_jsonl(self.path, entry)
        self._entries.setdefault((entry.record_id, entry.input_sha256), entry)


def entry_output(  # noqa: UP047
    entry: JournalEntry, model: type[ModelT], *, source: Path | str
) -> ModelT:
    """``entry.output`` validado como ``model``; si ya no valida, ``JournalError``.

    Un diario editado a mano, o un modelo que cambió entre versiones, deja una
    salida que ya no valida. Dejar pasar el ``ValidationError`` lo convertía en
    ``RunInterrupted`` (rc 3) y cada reanudación fallaba igual, un bucle sin
    salida (revisión de la Tarea 8): es un error del diario (rc 2), como la caché
    alterada. ``source`` nombra el diario para que el mensaje diga dónde mirar.
    """
    try:
        return model.model_validate(entry.output)
    except ValidationError as exc:
        error = exc.errors()[0]
        donde = ".".join(str(parte) for parte in error["loc"]) or model.__name__
        raise JournalError(
            f"{source}: la salida de {entry.record_id!r} ya no valida como {model.__name__} "
            f"({donde}: {error['msg']}); el diario se editó a mano o el modelo cambió: "
            "la corrida ya no es fiable, empieza una nueva."
        ) from exc


def journaled(  # noqa: UP047
    journal: StageJournal,
    *,
    record_id: str,
    inputs: object,
    model: type[ModelT],
    compute: Callable[[], tuple[ModelT, list[RunMeta]]],
    run_ctx: RunContext,
    role_of: Callable[[int], str] | None = None,
) -> ModelT:
    """Salida de ``record_id`` desde el diario o, si falta, calculada y registrada.

    ``inputs`` es todo lo que determina el resultado; su ``canonical_sha256`` es
    la clave junto con ``record_id``. Si no hay entrada: ``compute()`` (devuelve
    ``(salida, metas)``), después ``run_ctx.record_meta`` por cada llamada y
    **después** ``journal.append``. Una caída entre medias deja llamadas
    huérfanas (reales y válidas), nunca una decisión sin sus llamadas (spec
    2026-10-04 §7). ``role_of(i)`` etiqueta la llamada ``i`` (``member:<i>``
    en el ensemble de T/A).
    """
    input_sha256 = canonical_sha256(inputs)
    entry = journal.lookup(record_id, input_sha256)
    if entry is not None:
        return entry_output(entry, model, source=journal.path)
    value, metas = compute()
    calls = [
        run_ctx.record_meta(
            meta,
            stage=journal.stage,
            record_id=record_id,
            role=role_of(i) if role_of is not None else None,
        )
        for i, meta in enumerate(metas)
    ]
    journal.append(
        JournalEntry(
            stage=journal.stage,
            record_id=record_id,
            input_sha256=input_sha256,
            output=value.model_dump(mode="json"),
            metas=calls,
        )
    )
    return value
