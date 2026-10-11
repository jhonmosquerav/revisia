"""Checks de procedencia: ``manifest``, ``provenance``, ``schemas``, ``prompts`` y
``protocol_snapshot``.

``schemas`` valida cada artefacto presente contra el modelo que lo produce:
la reconstrucción de la auditoría 2026-09-03 (C3) traía un ``metrics.json``
sin matriz de confusión y un ``verification.json`` sin ``stage`` que ningún
código del motor puede escribir, y el auditor anterior los daba por buenos
porque solo miraba que existieran. Desde la Ola 1 valida también los
artefactos nuevos, cada línea de ``llm_calls.jsonl`` y de los diarios (con su
número de línea) y los bloques nuevos del manifiesto.

``protocol_snapshot`` comprueba que la corrida usó el protocolo que dice haber
usado (``00_protocol/`` frente a las huellas de ``run.json`` y al protocolo del
manifiesto). Sin ``run.json`` la corrida es anterior a la Ola 1 y no es
publicable (D13).

El manifiesto, ``run.json`` y la instantánea son entrada no confiable: ningún
valor suyo se interpola en un detalle sin pasar por ``short_text``/``short_repr``
(bomba de alias; revisiones de la Tarea 4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from revisia.audit.artifacts import (
    ARTIFACT_ADAPTERS,
    JSONL_ADAPTERS,
    LLM_CALLS_ILEGIBLE,
    MANIFEST_ADAPTERS,
    NA_MANIFIESTO,
    AuditContext,
    Loaded,
    short_repr,
    short_text,
    sufijo_mas,
)
from revisia.audit.model import Verdict
from revisia.orchestration.run_context import PROVENANCE_PIPELINE
from revisia.orchestration.snapshot import SNAPSHOT_DIR, protocol_fingerprint
from revisia.schemas.artifacts import GATED_STAGES

# D13: una corrida sin run.json no es publicable (spec 2026-10-04 §3).
LEGACY_RUN = (
    "anterior a la Ola 1 (motor < 0.8): sin instantánea ni decisiones por registro; "
    "regenera la corrida con el motor actual"
)

_MAX_ERRORES = 5
_MAX_MODELOS = 10
_LIMITE_MODELO = 60  # caracteres por modelo listado: diez de 120 ya pasaban de 1 000
_LIMITE_ERROR = 300  # caracteres por artefacto con error: un `loc` hostil no llena el detalle
_MAX_FICHEROS = 5  # ficheros de `00_protocol/` que se listan por motivo; el resto se cuenta
_LIMITE_RUTA = 60  # caracteres de la ruta de un fichero de `00_protocol/` (viene de run.json)


def _nombres(models: Any) -> str:
    """Los modelos del manifiesto en una línea, acotada en número y en longitud.

    Cada elemento pasa por ``short_text``: ``str`` de una lista anidada hostil (bomba de
    alias) cuelga el auditor, y una cadena enorme llenaría el detalle. ``models_used``
    puede no ser ni una lista (``schemas`` lo marca): entonces se muestra acotado.
    """
    if not isinstance(models, list | tuple):
        return short_text(models)
    names = ", ".join(short_text(m, limit=_LIMITE_MODELO) for m in models[:_MAX_MODELOS])
    return names + sufijo_mas(len(models) - _MAX_MODELOS)


def check_manifest(ctx: AuditContext) -> Verdict:
    """trAIce M2: manifiesto legible, con las llamadas IA y los modelos usados."""
    loaded = ctx.manifest
    if not loaded.present:
        return "FAIL", "manifest.yml ausente: la corrida no es reproducible."
    if not loaded.ok:
        # El motivo (YAML inválido, demasiado anidado, raíz de otro tipo…) va en la fila.
        return "FAIL", f"manifest.yml ilegible ({loaded.error}): la corrida no es reproducible."
    # Las del propio manifiesto (desde la Ola 1, copia de llm_calls.jsonl): este check audita lo
    # que el manifiesto dice de sí mismo, y `arithmetic` que la copia coincida con el original.
    calls = ctx.manifest_llm_calls
    if not calls:
        return "WARN", "manifest.yml sin llamadas IA registradas: no hay procedencia que auditar."
    fakes = sum(1 for c in calls if c.get("provider") == "fake")
    if fakes:
        return "WARN", (
            f"corrida de demostración, no evidencia: {fakes}/{len(calls)} llamadas con "
            "proveedor `fake`."
        )
    models = (ctx.manifest_dict or {}).get("models_used") or []
    return "PASS", (
        f"manifest.yml con {len(calls)} llamada(s) IA y modelos: "
        f"{_nombres(models) or '(sin models_used)'}."
    )


def check_provenance(ctx: AuditContext) -> Verdict:
    """Procedencia: la corrida la produjo el pipeline (auditoría 2026-09-03, C3)."""
    if ctx.manifest_dict is None:
        return "N/A", NA_MANIFIESTO
    provenance = ctx.manifest_dict.get("provenance")
    if provenance == PROVENANCE_PIPELINE:
        return "PASS", (
            "El manifiesto declara `provenance: pipeline` (marca escrita por el motor; "
            "no es una firma)."
        )
    # El manifiesto es entrada no confiable: `short_repr`, no `repr` (bomba de alias).
    found = "ausente" if provenance is None else short_repr(provenance)
    return "FAIL", (
        f"Procedencia {found}: el manifiesto no declara `provenance: pipeline`. "
        "Una corrida reconstruida, o generada antes de que el motor registrara "
        "su procedencia, no es evidencia publicable: regenérala con `revisia run`."
    )


def _validated(ctx: AuditContext) -> list[Loaded[Any]]:
    """Todos los artefactos presentes con modelo, ya validados.

    Sin el ledger, que tiene su propio check con número de línea. Se pide cada uno y se
    filtra por ``present``: los cargadores no lanzan, ni siquiera ante un fichero ilegible.
    """
    results: list[Loaded[Any]] = []
    if ctx.manifest.ok:
        results += [ctx.manifest_section(key) for key in MANIFEST_ADAPTERS]
    else:
        results.append(ctx.manifest)  # ausente (se descarta) o ilegible (el error se ve)
    results.append(ctx.art.run_info())
    results += [ctx.art.artifact(rel) for rel in ARTIFACT_ADAPTERS]
    results += [ctx.art.jsonl_models(rel) for rel in JSONL_ADAPTERS]
    for gate in GATED_STAGES:
        results.append(ctx.art.yaml(f"{gate}/review_request.yml"))
        results.append(ctx.art.decision(gate))
    return [r for r in results if r.present]


def check_schemas(ctx: AuditContext) -> Verdict:
    """PRISMA 27 / trAIce M5: cada artefacto presente valida el modelo que lo produce."""
    validated = _validated(ctx)
    errors = [
        short_text(f"{r.path}: {r.error}", limit=_LIMITE_ERROR) for r in validated if not r.ok
    ]
    if errors:
        shown = "; ".join(errors[:_MAX_ERRORES])
        more = sufijo_mas(len(errors) - _MAX_ERRORES, "artefacto")
        return "FAIL", (
            f"{len(errors)} artefacto(s) no cargan o no validan su modelo: {shown}{more}."
        )
    return "PASS", f"{len(validated)} artefactos validan su modelo."


def _ruta(rel: str) -> str:
    """Un fichero de ``00_protocol/`` para un detalle (la ruta viene de ``run.json``: acotada)."""
    return f"`{SNAPSHOT_DIR}/{short_text(rel, limit=_LIMITE_RUTA)}`"


def _existe(path: Path) -> bool:
    """``path`` existe (aunque no sea un fichero); un error al comprobarlo cuenta como que no."""
    try:
        return path.exists()
    except Exception:  # fail-closed hacia «ausente», que también es un FAIL
        return False


def _es_carpeta(ruta: object) -> bool:
    try:
        return isinstance(ruta, str | Path) and Path(ruta).is_dir()
    except Exception:  # una ruta que no se puede consultar no se da por carpeta
        return False


def _causa_huella(exc: Exception) -> str:
    """Qué falló al calcular la huella de ``00_protocol/``, por el tipo de la excepción.

    Se distinguen la codificación, una carpeta donde se esperaba un fichero y la falta de permiso.
    En Windows leer una carpeta lanza ``PermissionError`` (en POSIX, ``IsADirectoryError``), así
    que ante un ``OSError`` se mira si la ruta que trae es una carpeta. El mensaje de la excepción
    no se cita: puede llevar rutas o texto del fichero.
    """
    if isinstance(exc, UnicodeDecodeError):
        return "un fichero no es texto UTF-8 legible"
    if isinstance(exc, OSError):
        if isinstance(exc, IsADirectoryError) or _es_carpeta(exc.filename):
            return "hay una carpeta donde se esperaba un fichero"
        if isinstance(exc, PermissionError):
            return "un fichero no se puede leer: sin permiso"
        return "un fichero no se pudo leer"
    return "un fichero no se pudo leer o interpretar"


def _fuera_de_la_lista(snapshot: Path, registered: dict[str, str]) -> list[str] | str:
    """Ficheros de ``00_protocol/`` que ``run.json`` no registra (o el tipo del error si falla)."""
    try:
        if not snapshot.is_dir():
            return []
        files = sorted(
            p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file()
        )
    except Exception as exc:  # fail-closed: no listar la carpeta no es no tener extras
        return type(exc).__name__
    return [f for f in files if f not in registered]


def check_protocol_snapshot(ctx: AuditContext) -> Verdict:
    """PRISMA 24b / trAIce M1: la corrida usó el protocolo que dice haber usado.

    Compara ``00_protocol/`` con las huellas de ``run.json`` (texto con CRLF convertido a LF,
    como ``snapshot.protocol_fingerprint``) y la instantánea con el protocolo que registró el
    manifiesto. Sin ``run.json`` la corrida es anterior a la Ola 1 y no es publicable (D13),
    aunque el resto se audite como diagnóstico.

    ``run.json``, la instantánea y el manifiesto son entrada no confiable: las rutas y los
    errores que entran en el detalle van acotados, las listas se cortan y un fichero ilegible
    de ``00_protocol/`` es un FAIL, no una excepción.
    """
    loaded = ctx.art.run_info()
    if not loaded.present:
        return "FAIL", f"{LEGACY_RUN}."
    if not loaded.ok:
        error = short_text(loaded.error, limit=_LIMITE_ERROR)
        return "FAIL", f"run.json ilegible o inválido ({error}) (ver `schemas`)."
    registered = loaded.value.protocol_sha256
    snapshot = ctx.run_dir / SNAPSHOT_DIR
    try:
        actual = protocol_fingerprint(snapshot) if snapshot.is_dir() else {}
    except Exception as exc:  # un fichero que no es texto UTF-8, una carpeta o sin permiso
        return "FAIL", (
            f"no se pudo calcular la huella de {SNAPSHOT_DIR}/ ({type(exc).__name__}): "
            f"{_causa_huella(exc)}."
        )
    ausentes = [rel for rel in sorted(registered) if rel not in actual]
    distintos = [
        rel for rel in sorted(registered) if rel in actual and actual[rel] != registered[rel]
    ]
    # Lo que `run.json` registra y existe sin ser un fichero (una carpeta con ese nombre) no está
    # «ausente»: se dice lo que es, y no se repite luego como «no valida».
    fails = [
        f"{_ruta(rel)} {'no es un fichero' if _existe(snapshot / rel) else 'ausente'}"
        for rel in ausentes[:_MAX_FICHEROS]
    ]
    fails += [f"{_ruta(rel)}: hash distinto del de run.json" for rel in distintos[:_MAX_FICHEROS]]
    resto = max(len(ausentes) - _MAX_FICHEROS, 0) + max(len(distintos) - _MAX_FICHEROS, 0)
    if "protocol.yml" not in registered:
        fails.append("run.json no registra la huella de `protocol.yml`")
    snap = ctx.snapshot_protocol
    # Una corrida en pausa aún no tiene manifiesto (spec §4.2): no hay con qué contrastar la
    # instantánea y basta con que valide. Pero un manifiesto legible sin `protocol` no sale del
    # motor, que lo escribe siempre: se rechaza en vez de dejarlo sin contrastar.
    manifest = ctx.manifest_dict
    if not snap.present:
        if "protocol.yml" not in registered:  # si lo registra, ya consta como ausente
            fails.append(f"{_ruta('protocol.yml')} ausente")
    elif not snap.ok:
        # Si `run.json` lo registra y no está entre los ficheros leídos (falta o no es un
        # fichero), ya consta arriba: repetirlo como «no valida» solapaba los dos mensajes.
        if "protocol.yml" not in registered or "protocol.yml" in actual:
            error = short_text(snap.error, limit=_LIMITE_ERROR)
            fails.append(f"{_ruta('protocol.yml')} no valida ({error})")
    elif manifest is not None:
        if "protocol" not in manifest:
            fails.append("el manifiesto no trae `protocol` con el que contrastar la instantánea")
        elif snap.value.model_dump(mode="json") != manifest["protocol"]:
            fails.append(
                f"la instantánea {_ruta('protocol.yml')} no coincide con `manifest.protocol`"
            )
    if fails:
        return "FAIL", "; ".join(fails) + sufijo_mas(resto, "fichero") + "."
    extras = _fuera_de_la_lista(snapshot, registered)
    if isinstance(extras, str):
        return "WARN", f"no se pudo listar {SNAPSHOT_DIR}/ para buscar ficheros extra ({extras})."
    if extras:
        listados = ", ".join(
            f"`{short_text(f, limit=_LIMITE_RUTA)}`" for f in extras[:_MAX_FICHEROS]
        )
        return "WARN", (
            f"ficheros en {SNAPSHOT_DIR}/ fuera de la lista de hashes de run.json: {listados}"
            f"{sufijo_mas(len(extras) - _MAX_FICHEROS)}."
        )
    contraste = (
        "coincide con el protocolo del manifiesto"
        if manifest is not None
        else "valida como protocolo (sin manifiesto legible con el que compararla)"
    )
    return "PASS", (
        f"{len(registered)} ficheros de {SNAPSHOT_DIR}/ con el hash de run.json; la instantánea "
        f"{contraste}."
    )


def check_prompts(ctx: AuditContext) -> Verdict:
    """trAIce M6: cada llamada con el hash de su prompt y de su respuesta."""
    if ctx.manifest_dict is None:
        return "N/A", NA_MANIFIESTO
    if ctx.llm_calls_ilegible is not None:
        # No se audita la copia del manifiesto en su lugar: daría por verificado lo no leído.
        return "WARN", f"no se pueden auditar los hashes: {LLM_CALLS_ILEGIBLE}."
    calls = ctx.llm_calls
    if not calls:
        return "WARN", "Sin llamadas IA que auditar."
    complete = [c for c in calls if c.get("prompt_sha256") and c.get("response_sha256")]
    if len(complete) == len(calls):
        return "PASS", (
            f"{len(calls)}/{len(calls)} llamadas con prompt_sha256 y response_sha256 (RunMeta)."
        )
    return "WARN", (
        f"{len(calls) - len(complete)}/{len(calls)} llamadas sin hash de prompt o de "
        "respuesta (ver `schemas`)."
    )
