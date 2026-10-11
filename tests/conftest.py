"""Fixtures compartidas de la suite.

``corrida`` es una **corrida real del pipeline** (spec 2026-10-04 §9.4), no
una fabricada a mano: el auditor de la Ola 1 valida esquemas y aritmética, y
una corrida inventada (como el ``_make_run`` anterior, con llamadas sin
``response_sha256`` y conteos sin respaldo) la rechazaría por motivos ajenos
a cada test. Se genera una vez por sesión con ``ScriptedProvider`` (vota
``exclude`` ante "irrelevante", así hay exclusiones IA y un gold de dos
clases) y cada test recibe su propia copia.

Fase 2 de PR-E: la corrida avanza como en la vida real, con ``correr_hasta``
(``tests/hitl_helpers.py``): pausa en cada gate, ``decision.yml`` con el
``request_sha256`` de la solicitud vigente y reanudación. En el cribado a
texto completo (A0) la revisora etiqueta cada registro recuperado con la
propuesta de la IA (``etiquetar_auditoria``). El gold va en ``gold.yml`` de
una copia del demo, porque ``correr_hasta`` no pasa ``gold_labels``. La
recuperación de texto completo se inyecta con ``fetch_disponible``: con el FT
estricto (D2) un registro sin texto en abierto no llegaría a extracción.

``corrida_con_cita_marcada`` es la misma corrida con una síntesis que cita
``[2019]`` (un año, no un id del corpus): el verificador la marca, el gate
final se fuerza a humano y la revisora la adjudica como falso positivo en
``reporte/decision.yml`` (D8).
"""

from __future__ import annotations

import itertools
import shutil
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import correr_hasta

from revisia import cli
from revisia.config import load_protocol
from revisia.llm.registry import ProviderConfig
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.run_context import RunContext
from revisia.schemas.artifacts import GATED_STAGES
from revisia.schemas.records import SearchRecord

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"

# Marca de los tests que prueban la carga real de `.env` (`cli._load_dotenv`).
DOTENV_REAL = "dotenv_real"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", f"{DOTENV_REAL}: el test usa la carga real de .env de `revisia.cli.main`"
    )


@pytest.fixture(autouse=True)
def _sin_dotenv_real(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ningún test carga el ``.env`` real del repositorio (revisión final de la Ola 1, B3).

    ``cli.main`` carga ``.env`` buscándolo desde el directorio actual hacia arriba (D10): con
    una API key en la raíz del clon, cualquier test que llamara a ``main()`` la metía en el
    entorno de pytest (y en el de los tests siguientes). Solo los marcados con
    ``@pytest.mark.dotenv_real`` (que crean su propio ``.env`` en ``tmp_path``) la usan.
    """
    if request.node.get_closest_marker(DOTENV_REAL) is None:
        monkeypatch.setattr(cli, "_load_dotenv", lambda: None)


# Búsqueda simulada de la corrida de auditoría: 7 identificados (OpenAlex 4,
# Crossref 3), 1 duplicado por DOI, 2 exclusiones IA en T/A ("irrelevante") y
# 1 exclusión a texto completo ("secundario", solo para el proveedor FT).
REGISTROS_AUDITORIA: tuple[SearchRecord, ...] = (
    SearchRecord(
        record_id="10.1000/llm-1",
        title="LLM screening for systematic reviews",
        abstract="Recall 0.98 with a 60% workload reduction.",
        year=2024,
        doi="10.1000/llm-1",
        source_db="OpenAlex",
    ),
    SearchRecord(
        record_id="10.1000/llm-1-crossref",
        title="LLM screening for systematic reviews",
        abstract="Mismo artículo, otra base.",
        year=2024,
        doi="10.1000/LLM-1",
        source_db="Crossref",
    ),
    SearchRecord(
        record_id="10.1000/asreview",
        title="Active learning with ASReview",
        abstract="Active learning reduces screening workload by 70%.",
        year=2021,
        doi="10.1000/asreview",
        source_db="OpenAlex",
    ),
    SearchRecord(
        record_id="10.1000/ensemble",
        title="Ensemble de LLM para el cribado de títulos",
        abstract="Tres modelos votan con sesgo a recall.",
        year=2025,
        doi="10.1000/ensemble",
        source_db="Crossref",
    ),
    SearchRecord(
        record_id="10.1000/cocina",
        title="Estudio irrelevante sobre cocina mediterránea",
        abstract="Recetas.",
        year=2020,
        doi="10.1000/cocina",
        source_db="OpenAlex",
    ),
    SearchRecord(
        record_id="10.1000/botanica",
        title="Trabajo irrelevante de botánica",
        abstract="Plantas.",
        year=2019,
        doi="10.1000/botanica",
        source_db="Crossref",
    ),
    SearchRecord(
        record_id="10.1000/secundario",
        title="Cribado asistido con un desenlace secundario",
        abstract="Solo informa un desenlace secundario.",
        year=2023,
        doi="10.1000/secundario",
        source_db="OpenAlex",
    ),
)

# Gold humano de dos clases (4 relevantes, 2 irrelevantes).
GOLD_AUDITORIA: dict[str, bool] = {
    "10.1000/llm-1": True,
    "10.1000/asreview": True,
    "10.1000/ensemble": True,
    "10.1000/secundario": True,
    "10.1000/cocina": False,
    "10.1000/botanica": False,
}

# El proveedor de texto completo (el `default` del demo, `fake-1`) excluye
# además lo "secundario"; los miembros del ensemble T/A no.
PALABRAS_FT = {"irrelevante": "exclude", "dudoso": "unclear", "secundario": "exclude"}
RAZON_EXCLUSION_FT = "fuera de alcance"


def busqueda_auditoria(_query: str, n: int) -> list[SearchRecord]:
    """``search_fn`` de la corrida de auditoría (copias: el dedup muta)."""
    return [r.model_copy(deep=True) for r in REGISTROS_AUDITORIA[:n]]


def proveedor_auditoria(cfg: ProviderConfig) -> ScriptedProvider:
    """``build_provider`` de la corrida: un ``ScriptedProvider`` por modelo."""
    palabras = PALABRAS_FT if cfg.model == "fake-1" else None
    return ScriptedProvider(model=cfg.model, palabras=palabras)


# Síntesis con una cita real (un incluido) y otra que no está en el corpus.
SINTESIS_CON_CITA_MARCADA = "La IA reduce el cribado [10.1000/llm-1]. Lo confirma [2019]."
RAZON_FALSO_POSITIVO = "[2019] es un año, no una cita"


def proveedor_con_cita_marcada(cfg: ProviderConfig) -> ScriptedProvider:
    """Como ``proveedor_auditoria``; ``fake-1`` (síntesis) escribe ``[2019]``."""
    if cfg.model != "fake-1":
        return proveedor_auditoria(cfg)
    return ScriptedProvider(
        model=cfg.model, palabras=PALABRAS_FT, sintesis=SINTESIS_CON_CITA_MARCADA
    )


def etiquetar_auditoria(stage: str, solicitud: dict) -> dict | None:
    """La revisora humana de la corrida de auditoría.

    En T/A (A1) aprueba la propuesta en bloque (D5: sin etiquetas). En el texto
    completo (A0) etiqueta cada registro de ``must_label`` con la propuesta de
    la IA, con razón al excluir. En el resto de gates aprueba sin más.
    """
    if stage != "screening_ft":
        return None
    propuestas = {r["record_id"]: r.get("proposal") for r in solicitud.get("records", [])}
    records = {}
    for record_id in solicitud.get("must_label", []):
        if propuestas.get(record_id) == "exclude":
            records[record_id] = {"label": "exclude", "reason": RAZON_EXCLUSION_FT}
        else:
            records[record_id] = {"label": "include", "reason": None}
    return {"records": records} if records else None


def adjudicar_auditoria(stage: str, solicitud: dict) -> dict | None:
    """``etiquetar_auditoria`` que, además, adjudica las citas marcadas (D8)."""
    if stage != "reporte":
        return etiquetar_auditoria(stage, solicitud)
    flags = {
        str(indice): {"verdict": "false_positive", "reason": RAZON_FALSO_POSITIVO}
        for indice in solicitud.get("must_adjudicate", [])
    }
    return {"flags": flags} if flags else None


@pytest.fixture(scope="session")
def protocolo_auditoria(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copia del demo con el gold de la corrida de auditoría en ``gold.yml``."""
    destino = tmp_path_factory.mktemp("protocolo") / DEMO.name
    shutil.copytree(DEMO, destino)
    (destino / "gold.yml").write_text(
        yaml.safe_dump({"gold": GOLD_AUDITORIA}, allow_unicode=True), encoding="utf-8"
    )
    return destino


@pytest.fixture(scope="session")
def protocolo_con_cita_marcada(
    tmp_path_factory: pytest.TempPathFactory, protocolo_auditoria: Path
) -> Path:
    """``protocolo_auditoria`` con ``grounding: existence`` (id en el corpus o no)."""
    destino = tmp_path_factory.mktemp("protocolo-marcas") / DEMO.name
    shutil.copytree(protocolo_auditoria, destino)
    raw = yaml.safe_load((destino / "protocol.yml").read_text(encoding="utf-8"))
    raw["grounding"] = "existence"
    (destino / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), "utf-8")
    return destino


def busqueda_vacia(_query: str, _n: int) -> list[SearchRecord]:
    """``search_fn`` de una búsqueda que no devuelve ningún registro."""
    return []


def _correr(
    base_dir: Path,
    protocol_dir: Path,
    *,
    parar_en: str | None,
    rechazar: str | None = None,
    search_fn: Callable[[str, int], list[SearchRecord]] = busqueda_auditoria,
    proveedor: Callable[[ProviderConfig], ScriptedProvider] = proveedor_auditoria,
    etiquetar: Callable[[str, dict], dict | None] = etiquetar_auditoria,
) -> Path:
    """Corre el pipeline real con la revisora ``etiquetar`` (por defecto, ``etiquetar_auditoria``).

    Se detiene en la pausa de ``parar_en`` o, con ``rechazar``, cuando la revisora
    rechaza ese gate (``approved: false`` atado a su solicitud, como en la vida real).
    ``search_fn`` es la búsqueda simulada (por defecto, los siete registros de la auditoría) y
    ``proveedor`` el ``build_provider`` de la corrida (por defecto, ``proveedor_auditoria``).
    """
    protocol = load_protocol(protocol_dir)
    # Timestamp UTC real: el auditor lo usa como límite inferior de las marcas
    # de tiempo cuando no hay `run.json` (spec §9.3, `timing`).
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    ctx = RunContext(protocol.slug, base_dir, timestamp)

    def _revisora(stage: str, solicitud: dict) -> dict | None:
        if stage == rechazar:
            return {"approved": False, "reason": "sin respaldo"}
        return etiquetar(stage, solicitud)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline_mod, "build_provider", proveedor)
        result = correr_hasta(
            protocol,
            protocol_dir,
            ctx,
            search_fn=search_fn,
            fetch_fn=fetch_disponible,
            etiquetar=_revisora,
            parar_en=parar_en,
        )
    esperado = "rejected" if rechazar else "paused" if parar_en else "completed"
    assert result.status == esperado, result.message
    assert result.stage == (rechazar or parar_en), result.message
    return ctx.run_dir


@pytest.fixture(scope="session")
def _corrida_auditoria(tmp_path_factory: pytest.TempPathFactory, protocolo_auditoria: Path) -> Path:
    """Corrida real completada, generada una vez por sesión."""
    return _correr(tmp_path_factory.mktemp("auditoria"), protocolo_auditoria, parar_en=None)


@pytest.fixture(scope="session")
def _corrida_en_pausa_ft(
    tmp_path_factory: pytest.TempPathFactory, protocolo_auditoria: Path
) -> Path:
    """La misma corrida, detenida en el gate de texto completo."""
    return _correr(
        tmp_path_factory.mktemp("auditoria"), protocolo_auditoria, parar_en="screening_ft"
    )


@pytest.fixture(scope="session")
def _corrida_sin_registros(
    tmp_path_factory: pytest.TempPathFactory, protocolo_auditoria: Path
) -> Path:
    """Corrida real completada cuya búsqueda no devuelve ningún registro (0 incluidos)."""
    return _correr(
        tmp_path_factory.mktemp("sin-registros"),
        protocolo_auditoria,
        parar_en=None,
        search_fn=busqueda_vacia,
    )


@pytest.fixture(scope="session")
def _corrida_con_cita_marcada(
    tmp_path_factory: pytest.TempPathFactory, protocolo_con_cita_marcada: Path
) -> Path:
    """Corrida completada con una cita marcada y adjudicada por la revisora."""
    return _correr(
        tmp_path_factory.mktemp("cita-marcada"),
        protocolo_con_cita_marcada,
        parar_en=None,
        proveedor=proveedor_con_cita_marcada,
        etiquetar=adjudicar_auditoria,
    )


def _copia(origen: Path, tmp_path: Path) -> Path:
    destino = tmp_path / "runs" / origen.name
    shutil.copytree(origen, destino)
    return destino


@pytest.fixture
def corrida(_corrida_auditoria: Path, tmp_path: Path) -> Path:
    """Copia propia de la corrida real, en ``tmp_path/runs/<slug>-<timestamp>``."""
    return _copia(_corrida_auditoria, tmp_path)


@pytest.fixture
def corrida_en_pausa_ft(_corrida_en_pausa_ft: Path, tmp_path: Path) -> Path:
    """Copia propia de la corrida en pausa en ``screening_ft``."""
    return _copia(_corrida_en_pausa_ft, tmp_path)


@pytest.fixture
def corrida_sin_registros(_corrida_sin_registros: Path, tmp_path: Path) -> Path:
    """Copia propia de la corrida completada de una búsqueda sin registros."""
    return _copia(_corrida_sin_registros, tmp_path)


@pytest.fixture
def corrida_con_cita_marcada(_corrida_con_cita_marcada: Path, tmp_path: Path) -> Path:
    """Copia propia de la corrida con la cita ``[2019]`` adjudicada."""
    return _copia(_corrida_con_cita_marcada, tmp_path)


@pytest.fixture(scope="session")
def _corridas_cacheadas() -> dict[tuple, Path]:
    """Corridas reales de las fábricas de abajo, una por clave y sesión (revisión final, E7).

    Cada corrida cuesta unos segundos de pipeline real; muchos tests piden la misma (la clave
    es ``(fábrica, aprobados, rechazar)``) y casi todos la editan, así que cada llamada recibe
    una copia propia de la corrida cacheada.
    """
    return {}


def _copia_propia(origen: Path, tmp_path: Path, numero: int) -> Path:
    """Copia de ``origen`` en ``tmp_path/copia-<n>/runs/<nombre>`` (una por llamada)."""
    destino = tmp_path / f"copia-{numero}" / "runs" / origen.name
    shutil.copytree(origen, destino)
    return destino


@pytest.fixture
def rechazar_sin_registros(
    tmp_path_factory: pytest.TempPathFactory,
    protocolo_auditoria: Path,
    _corridas_cacheadas: dict[tuple, Path],
    tmp_path: Path,
) -> Callable[[str], Path]:
    """Fábrica de corridas reales de búsqueda vacía rechazadas en un gate (``rechazar``).

    Una corrida rechazada antes de la síntesis no hizo ninguna llamada a la IA (sin registros
    no hay nada que cribar): no tiene ``llm_calls.jsonl`` ni el diario de T/A. Cada llamada
    devuelve una copia propia de la corrida de esa etapa, generada una vez por sesión.
    """
    copias = itertools.count()

    def _rechazar(etapa: str) -> Path:
        clave = ("rechazar_sin_registros", etapa)
        if clave not in _corridas_cacheadas:
            _corridas_cacheadas[clave] = _correr(
                tmp_path_factory.mktemp("sin-registros-rechazada"),
                protocolo_auditoria,
                parar_en=None,
                rechazar=etapa,
                search_fn=busqueda_vacia,
            )
        return _copia_propia(_corridas_cacheadas[clave], tmp_path, next(copias))

    return _rechazar


@pytest.fixture
def detener_corrida(
    tmp_path_factory: pytest.TempPathFactory,
    protocolo_auditoria: Path,
    _corridas_cacheadas: dict[tuple, Path],
    tmp_path: Path,
) -> Callable[..., Path]:
    """Fábrica de corridas reales detenidas en un gate (pausadas o rechazadas).

    ``detener_corrida(aprobados=("screening_ta", "screening_ft"))`` aprueba esos gates y deja la
    corrida en pausa en el siguiente; con ``rechazar="extraccion"`` ese gate se rechaza. Es el
    mismo pipeline, el mismo proveedor y la misma revisora que ``corrida`` (con
    ``correr_hasta``), pero sin llegar al gate final: en esas corridas el manifiesto y el
    entregable todavía no existen (spec 2026-10-04 §4.2), y lo que el auditor exige de ellas
    no puede inventarse editando una corrida terminada. ``aprobados`` son los primeros gates de
    ``GATED_STAGES``, en orden: el pipeline no puede decidir un gate sin pasar por los previos.
    Con los cinco aprobados no queda ningún gate donde detenerse (``ValueError``): esa es la
    corrida completada, la fixture ``corrida``. Cada llamada devuelve una copia propia de la
    corrida de esa clave, generada una vez por sesión (E7).
    """
    copias = itertools.count()

    def _detener(*, aprobados: Sequence[str], rechazar: str | None = None) -> Path:
        aprobados = tuple(aprobados)
        assert aprobados == GATED_STAGES[: len(aprobados)], f"no es un prefijo: {aprobados}"
        if len(aprobados) == len(GATED_STAGES):
            raise ValueError(
                "con los cinco gates aprobados no queda ninguno donde detenerse: la corrida "
                "completada es la fixture `corrida`"
            )
        siguiente = GATED_STAGES[len(aprobados)]
        assert rechazar in (None, siguiente), f"solo se rechaza `{siguiente}`, no `{rechazar}`"
        clave = ("detener_corrida", aprobados, rechazar)
        if clave not in _corridas_cacheadas:
            _corridas_cacheadas[clave] = _correr(
                tmp_path_factory.mktemp("detenida"),
                protocolo_auditoria,
                parar_en=None if rechazar else siguiente,
                rechazar=rechazar,
            )
        return _copia_propia(_corridas_cacheadas[clave], tmp_path, next(copias))

    return _detener
