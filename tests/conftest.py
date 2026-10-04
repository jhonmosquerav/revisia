"""Fixtures compartidas de la suite.

``corrida`` es una **corrida real del pipeline** (spec 2026-10-04 §9.4), no
una fabricada a mano: el auditor de la Ola 1 valida esquemas y aritmética, y
una corrida inventada (como el ``_make_run`` anterior, con llamadas sin
``response_sha256`` y conteos sin respaldo) la rechazaría por motivos ajenos
a cada test. Se genera una vez por sesión con ``ScriptedProvider`` (vota
``exclude`` ante "irrelevante", así hay exclusiones IA y un gold de dos
clases) y cada test recibe su propia copia.

Fase 1 de PR-E: los ``decision.yml`` humanos se escriben antes de correr, como
en ``tests/test_pipeline_fake.py``. La recuperación de texto completo se
inyecta con ``fetch_disponible`` desde el principio: con el FT estricto de
PR-B (D2) un registro sin texto en abierto ya no llega a extracción.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fakes import ScriptedProvider, fetch_disponible

from revisia.config import load_protocol
from revisia.llm.registry import ProviderConfig
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.run_context import RunContext
from revisia.schemas.artifacts import GATED_STAGES
from revisia.schemas.records import SearchRecord

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"

# Búsqueda simulada de la corrida de auditoría: 7 identificados (OpenAlex 4,
# Crossref 3), 1 duplicado por DOI, 2 exclusiones IA en T/A ("irrelevante") y
# 1 exclusión IA a texto completo ("secundario", solo para el proveedor FT).
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

DECISION_HUMANA = "approved: true\nactor: human:revisora\n"


def busqueda_auditoria(_query: str, n: int) -> list[SearchRecord]:
    """``search_fn`` de la corrida de auditoría (copias: el dedup muta)."""
    return [r.model_copy(deep=True) for r in REGISTROS_AUDITORIA[:n]]


def proveedor_auditoria(cfg: ProviderConfig) -> ScriptedProvider:
    """``build_provider`` de la corrida: un ``ScriptedProvider`` por modelo."""
    palabras = PALABRAS_FT if cfg.model == "fake-1" else None
    return ScriptedProvider(model=cfg.model, palabras=palabras)


@pytest.fixture(scope="session")
def _corrida_auditoria(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Corrida real del pipeline, generada una vez por sesión."""
    protocol = load_protocol(DEMO)
    # Timestamp UTC real: el auditor lo usa como límite inferior de las marcas
    # de tiempo cuando no hay `run.json` (spec §9.3, `timing`).
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    ctx = RunContext(protocol.slug, tmp_path_factory.mktemp("auditoria"), timestamp)
    for stage in GATED_STAGES:
        (ctx.stage_dir(stage) / "decision.yml").write_text(DECISION_HUMANA, encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
        result = pipeline_mod.run_pipeline(
            protocol,
            DEMO,
            ctx,
            max_results=50,
            search_fn=busqueda_auditoria,
            fetch_fn=fetch_disponible,
            gold_labels=GOLD_AUDITORIA,
        )
    assert result.status == "completed", result.message
    return ctx.run_dir


@pytest.fixture
def corrida(_corrida_auditoria: Path, tmp_path: Path) -> Path:
    """Copia propia de la corrida real, en ``tmp_path/runs/<slug>-<timestamp>``."""
    destino = tmp_path / "runs" / _corrida_auditoria.name
    shutil.copytree(_corrida_auditoria, destino)
    return destino
