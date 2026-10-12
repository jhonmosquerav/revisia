"""Instantánea del protocolo y ``run.json`` (Ola 1, D3 y D13; spec 2026-10-04 §7).

Una corrida reanudable tiene que saber con qué protocolo empezó. Al crearla se
escribe ``run.json`` (lo primero, con las huellas del protocolo y de los
prompts del motor) y se copia el protocolo a ``00_protocol/``: protocol.yml,
criterios, formulario, efectos, gold y cadenas de búsqueda. Desde ese momento
``00_protocol/`` es la única fuente de criterios, formulario, efectos, gold y
cadenas: editar el protocolo original a mitad de corrida no cambia la corrida, y
al reanudar cualquier diferencia se detecta (``ProtocolMismatchError``) en vez
de mezclar dos protocolos en una misma revisión.

Las huellas van sobre el texto UTF-8 con CRLF convertido a LF: con ``autocrlf``
en Windows, el hash de los bytes cambiaría entre clones (spec §4.1).
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from revisia import __version__
from revisia.orchestration.run_context import RUN_INFO_FILE, RunContext
from revisia.provenance.runmeta import sha256_text, utc_now_iso
from revisia.schemas.artifacts import RunInfo

SNAPSHOT_DIR = "00_protocol"
# Ficheros del protocolo que entran en la instantánea, si existen (spec §4.2),
# además de `search_strings/*.txt`. `imported/` no: la búsqueda queda congelada
# en `01_search/` y el log guarda el hash de cada fichero importado.
SNAPSHOT_FILES: tuple[str, ...] = (
    "protocol.yml",
    "inclusion_exclusion.yml",
    "extraction_form.yml",
    "effects.yml",
    "gold.yml",
)
SEARCH_STRINGS_DIR = "search_strings"
# Plantillas de prompt del motor (`revisia/prompts/<agente>/<versión>.md`).
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class ProtocolMismatchError(ValueError):
    """El protocolo o los prompts no coinciden con los de la corrida (rc 2 en el CLI).

    Attributes:
        files: ficheros distintos (``00_protocol/…``, ``revisia/prompts/…`` o
            del protocolo original).
    """

    def __init__(self, message: str, files: list[str] | None = None) -> None:
        self.files = list(files or [])
        super().__init__(message)


def _text_sha256(path: Path) -> str:
    """SHA-256 del texto UTF-8 con CRLF convertido a LF."""
    return sha256_text(path.read_bytes().decode("utf-8").replace("\r\n", "\n"))


def protocol_fingerprint(protocol_dir: str | Path) -> dict[str, str]:
    """Huella ``{ruta relativa con /: sha256}`` de los ficheros que se congelan."""
    base = Path(protocol_dir)
    fingerprint: dict[str, str] = {}
    for name in SNAPSHOT_FILES:
        if (base / name).is_file():
            fingerprint[name] = _text_sha256(base / name)
    strings = base / SEARCH_STRINGS_DIR
    if strings.is_dir():
        for path in sorted(strings.glob("*.txt")):
            fingerprint[f"{SEARCH_STRINGS_DIR}/{path.name}"] = _text_sha256(path)
    return fingerprint


def prompt_fingerprint() -> dict[str, str]:
    """Huella ``{"<agente>/<versión>.md": sha256}`` de los prompts del motor."""
    return {
        f"{path.parent.name}/{path.name}": _text_sha256(path)
        for path in sorted(PROMPTS_DIR.glob("*/*.md"))
    }


def read_run_info(run_dir: str | Path) -> RunInfo | None:
    """``run.json`` validado, o ``None`` si la corrida no lo tiene."""
    path = Path(run_dir) / RUN_INFO_FILE
    if not path.exists():
        return None
    return RunInfo.model_validate_json(path.read_text(encoding="utf-8"))


def write_run_info(run_dir: str | Path, info: RunInfo) -> RunInfo:
    """Escribe ``run.json`` de forma atómica con ``updated_utc`` al día y lo devuelve."""
    info = info.model_copy(update={"updated_utc": utc_now_iso()})
    path = Path(run_dir) / RUN_INFO_FILE
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(info.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return info


def _differences(expected: dict[str, str], actual: dict[str, str]) -> list[str]:
    return sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))


def ensure_snapshot(
    protocol_dir: str | Path | None,
    run_ctx: RunContext,
    *,
    max_results: int,
    mailto: str | None,
) -> tuple[Path, RunInfo]:
    """Crea la instantánea de una corrida nueva o verifica la de una que se reanuda.

    Sin ``run.json``: escribe ``run.json`` (estado ``running``) y copia el
    protocolo a ``00_protocol/``. Con ``run.json``: comprueba que
    ``00_protocol/`` y los prompts del motor siguen coincidiendo con sus huellas
    y, si se pasó ``protocol_dir``, también el protocolo original; si todo
    coincide, añade la hora a ``resumes`` y vuelve a ``running``.

    Returns:
        ``(00_protocol/, run_info)``.

    Raises:
        ProtocolMismatchError: con la lista de ficheros distintos.
        ValueError: corrida nueva sin ``protocol_dir``.
    """
    snapshot = run_ctx.run_dir / SNAPSHOT_DIR
    info = read_run_info(run_ctx.run_dir)
    if info is None:
        if protocol_dir is None:
            raise ValueError("una corrida nueva necesita la carpeta del protocolo")
        source = Path(protocol_dir)
        info = write_run_info(
            run_ctx.run_dir,
            RunInfo(
                slug=run_ctx.slug,
                timestamp=run_ctx.timestamp,
                started_utc=utc_now_iso(),
                engine_version=__version__,
                python_version=platform.python_version(),
                max_results=max_results,
                mailto_set=bool(mailto),
                protocol_sha256=protocol_fingerprint(source),
                prompt_sha256=prompt_fingerprint(),
            ),
        )
        for relpath in info.protocol_sha256:
            target = snapshot / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relpath, target)
        return snapshot, info

    files = [
        f"{SNAPSHOT_DIR}/{k}"
        for k in _differences(info.protocol_sha256, protocol_fingerprint(snapshot))
    ]
    files += [
        f"revisia/prompts/{k}" for k in _differences(info.prompt_sha256, prompt_fingerprint())
    ]
    if protocol_dir is not None:
        original = protocol_fingerprint(protocol_dir)
        files += [
            f"{Path(protocol_dir).as_posix()}/{k}"
            for k in _differences(info.protocol_sha256, original)
        ]
    if files:
        raise ProtocolMismatchError(
            "el protocolo o los prompts no coinciden con los de la corrida "
            f"({', '.join(files)}): una corrida se reanuda con el protocolo y el motor con "
            "los que empezó. Para usar el protocolo editado, empieza una corrida nueva.",
            files,
        )
    info = info.model_copy(
        update={"resumes": [*info.resumes, utc_now_iso()], "status": "running", "stage": None}
    )
    return snapshot, write_run_info(run_ctx.run_dir, info)
