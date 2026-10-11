# Ola 1 · Pista A (cimientos: PR-0, PR-A, PR-B) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poner los cimientos de la Ola 1 de la auditoría 2026-09-03 en tres PRs apiladas: los contratos de artefactos que comparten pipeline y auditor (PR-0), el preflight sin red de proveedores y bases (PR-A, M6) y el flujo PRISMA estricto con informes no recuperados y lista 16b (PR-B, M11, M23).

**Architecture:** PR-0 añade código sin cambiar comportamiento: un módulo de contratos (`revisia/schemas/artifacts.py`), hashes canónicos y el reductor único del ledger, campos aditivos y dobles de prueba compartidos. PR-A crea `revisia/llm/preflight.py`, una función pura con `env`/`find_spec`/`which` inyectables, y la conecta a `validate` y `run` antes de crear la carpeta de la corrida. PR-B registra el motivo de cada fallo de recuperación, deja de cribar con IA los informes sin texto completo y propaga los conteos nuevos al diagrama, la tabla, el CSV PRISMA2020, `metodologia.md` y la lista 16b.

**Tech Stack:** Python 3.13 (suite también en 3.11/3.12 con venv desechable), Pydantic v2, PyYAML, python-dotenv (ya es dependencia del núcleo), pytest, ruff + black (línea 100), uv, gh.

**Spec:** `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md`. Este plan cubre §4 (PR-0), §5 (PR-A), §6 (PR-B) y la topología de §10. Lee §3 (decisiones D1–D14) antes de empezar; no se reabren. Planes hermanos: `2026-10-04-ola-1-b-reanudacion-hitl.md` (PR-C, PR-D) y `2026-10-04-ola-1-c-auditor.md` (PR-E), escritos contra las firmas que produce PR-0 (bloques **Interfaces** de las Tareas 1–4).

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes y commits **en español**, con el tono del repo. Las docstrings explican el porqué y citan la auditoría ("auditoría 2026-09-03, M6") o la decisión del spec ("D2").
- Estilo: `ruff` (reglas `E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100). Ambos limpios. Si `ruff format` une dos f-strings que caben en una línea, se acepta su versión (black la respeta).
- `from __future__ import annotations` al inicio de todo módulo nuevo, también en los de `tests/`.
- Tests offline, sin red y deterministas. Ningún test invoca `claude`, WeasyPrint real ni APIs. El preflight se prueba con `env`, `find_spec` y `which` falsos.
- Línea base: **330 tests recogidos, en verde** (`main` @ `412d529`; la rama `feat/ola1-contratos` @ `69fd6ca` solo añade el spec). Ningún test existente se borra; los que cambian de expectativa se listan en su tarea con el código exacto del cambio.
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider`; lint, `uv run ruff check . && uv run ruff format --check . && uv run black --check .`.
- Commits pequeños, al menos uno por tarea, en español con prefijo convencional (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), terminados con la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Los implementadores no tocan** `CHANGELOG.md`, `README.md` ni el spec: los actualiza el integrador en las Tareas 5, 14 y 15, con el texto exacto que dan esas tareas.
- **No tocar** `runs/` ni `protocols/<slug>/` distintos de `_TEMPLATE` (no versionados).
- No cambiar `revisia.__version__` ni `pyproject.toml` (la 0.8.0 la publica el arquitecto, D13).
- `tests/` no es un paquete: los dobles compartidos se importan como `from fakes import ...` (pytest pone `tests/` en `sys.path`). `ruff` los clasifica como terceros, así que van en el bloque de terceros, después de `import pytest`/`import yaml`.
- Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base.

---

## Topología de ejecución (subagentes)

La Ola 1 son seis PRs apiladas, `0 → A → B → C → D → E`, como en la Ola 0. Este plan cubre 0, A y B; los planes hermanos cubren C, D (`…-b-reanudacion-hitl.md`) y E (`…-c-auditor.md`).

| Pista | PR | Rama | Worktree | Se crea desde | Base de la PR | Cierra | Plan · tareas |
|---|---|---|---|---|---|---|---|
| 0 | PR-0 | `feat/ola1-contratos` | `C:\revisia` | `main` (ya creada; el spec ya está commiteado) | `main` | spec, planes, contratos | este · 1–5 |
| A | PR-A | `feat/ola1-preflight` | `C:\revisia-wt\a` | `feat/ola1-contratos` tras la Tarea 5 | `feat/ola1-contratos` | M6 | este · 6–8, 14 |
| B | PR-B | `feat/ola1-flujo-prisma` | `C:\revisia-wt\b` | `feat/ola1-contratos` tras la Tarea 5 | `feat/ola1-preflight` (tras rebase, Tarea 15) | M11, M23 | este · 9–13, 15 |
| E · fase 1 | PR-E | `feat/ola1-auditor` | `C:\revisia-wt\e` | `feat/ola1-contratos` tras la Tarea 5 | `feat/ola1-hitl-por-registro` | C3-auditor, A11, M5 auditor | `…-c-auditor.md` |
| C | PR-C | `feat/ola1-reanudacion` | `C:\revisia-wt\c` | `feat/ola1-flujo-prisma` ya rebasada sobre A (tras la Tarea 15) | `feat/ola1-flujo-prisma` | A9, M12, `request_sha256` | `…-b-reanudacion-hitl.md` |
| D | PR-D | `feat/ola1-hitl-por-registro` | `C:\revisia-wt\d` | `feat/ola1-reanudacion` | `feat/ola1-reanudacion` | C1, M5, M13 | `…-b-reanudacion-hitl.md` |
| E · fase 2 | PR-E | `feat/ola1-auditor` rebasada sobre D | `C:\revisia-wt\e` | — | `feat/ola1-hitl-por-registro` | — | `…-c-auditor.md` |

Orden en el tiempo:

1. **Fase 0 (secuencial, `C:\revisia`):** Tareas 1 → 2 → 3 → 4 y la integración de PR-0 (Tarea 5), que además crea los worktrees de A, B y E.
2. **Fase 1 (en paralelo desde PR-0):** pista A (6 → 7 → 8), pista B (9 → 10 → 11 → 12 → 13) y la fase 1 de E (su plan). Cada pista en su worktree y su rama.
3. **Integración de A y B:** Tarea 14 (PR-A) y después la Tarea 15 (rebase de B sobre A y PR-B). Verificado en un prototipo: A y B tocan ficheros disjuntos y el rebase no tiene conflictos.
4. **Fase 2:** C sobre B rebasada, después D. E sigue con su fase 1 en paralelo.
5. **Fase 3:** E se rebasa sobre D, hace su fase 2 y es la última PR. El cierre de la ola (README sin la nota de limitación, `AGENTS.md`, auditoría §11) va en E.

Solapes verificados y cómo se resuelven:

| Fichero | Pistas | Resolución |
|---|---|---|
| `revisia/cli.py` | A (`_load_dotenv`, `_print_preflight`, `_cmd_validate`, arranque de `run` en `main`), C (`--resume`, excepciones), E (`_cmd_audit`) | A y E tocan funciones distintas; C se apila sobre A |
| `revisia/orchestration/pipeline.py` | B (bloque FT y conteos), C (refactor), D | Secuenciales: B → C → D |
| `revisia/orchestration/hitl.py` | C (hash, idempotencia), D (registros) | Secuenciales |
| `revisia/exports/checklist.py`, `revisia/exports/methods.py` | B (ítem 16, línea de conteos), C, D | Secuenciales |
| `revisia/exports/prisma_flow.py` | 0 (campos), B (cajas, validador, 16b) | Secuenciales |
| `tests/test_pipeline_fake.py` | B, C, D, E (fase 2) | E no lo toca en la fase 1 |
| `tests/test_cli_validate.py`, `tests/test_cli_errores.py` | A | Nadie más los toca en la fase 1 |
| `tests/fakes.py` | 0 lo crea; el resto lo importa | Ampliaciones posteriores, solo aditivas y en la PR que las necesite |
| `tests/conftest.py` | solo E (fase 1) | A y B no lo crean |
| `CHANGELOG.md`, `README.md`, spec | integrador | Un commit de docs por PR, siempre después de rebasar |

Aviso para la fase 1 de E: se desarrolla sin el FT estricto de B. Su fixture de corrida real debe inyectar `fetch_fn=fetch_disponible` (de `tests/fakes.py`, PR-0) desde el principio; si no, al rebasar sobre D la corrida dejaría de tener incluidos (D2).

**Ciclo por tarea:** implementador (subagente nuevo, TDD estricto: test rojo → código mínimo → verde → lint → commit) → revisor (subagente nuevo: primero cumplimiento del spec y de este plan, después calidad) → correcciones si las hay → siguiente tarea. Las tareas de integración (5, 14, 15) las ejecuta el controlador. El controlador ejecuta de punta a punta sin pedir confirmación entre tareas; audita y corrige lo que encuentre. **El merge no lo hace nadie de este plan: lo decide el arquitecto.**

**Regla de merge de PRs apiladas** (la decide y ejecuta el arquitecto; se deja escrita en el cuerpo de cada PR): mergear sin borrar la rama → `gh pr edit <n> --base main` en la PR que dependía de ella → borrar la rama mergeada → cerrar y reabrir la PR re-apuntada (`gh pr close <n> && gh pr reopen <n>`) para que corra el CI. Con `--delete-branch` GitHub cierra la PR dependiente en vez de re-apuntarla.

**Entorno de cada worktree:** el primer paso en un worktree nuevo es `uv sync --extra dev` (pytest, ruff y black están en el extra `dev`; `uv run` no instala extras por su cuenta). Necesita red una vez, o la caché de uv.

---

## Pista 0 · PR-0 `feat/ola1-contratos` (worktree `C:\revisia`)

### Task 1: Contratos de artefactos (`revisia/schemas/artifacts.py`)

**Files:**
- Create: `revisia/schemas/artifacts.py`
- Test: `tests/test_artifacts.py` (nuevo)

**Interfaces:**
- Consumes: `revisia.provenance.runmeta.RunMeta`, `utc_now_iso() -> str` (existentes); `revisia.config.STAGES` (solo en el test).
- Produces (firmas exactas; los planes hermanos se escriben contra ellas):
  - `ARTIFACT_SCHEMA_VERSION: int = 1`
  - `RunStatus = Literal["running", "paused", "rejected", "completed", "interrupted"]`
  - `LLMStage = Literal["screening_ta", "screening_ft", "extraccion", "extraccion_2", "rob", "sintesis", "verificacion"]`
  - `JournalStage = Literal["screening_ta", "fulltext_retrieval", "screening_ft", "extraccion", "extraccion_2", "rob", "sintesis", "verificacion"]`
  - `FulltextReason = Literal["sin_url_oa", "sin_httpx", "error_http", "texto_vacio", "no_disponible"]`
  - `SearchEntryKind = Literal["database", "manual_import", "injected"]`; `SearchEntryStatus = Literal["ok", "failed", "manual_only", "unknown"]`; `QueryOrigin = Literal["file", "question_fallback"]`; `ReasonSource = Literal["human", "ai"]`; `GateAction = Literal["approve", "reject", "auto-proceed"]`
  - `JOURNAL_PATHS: dict[str, str]` (clave = `JournalStage`, valor = ruta relativa con `/`)
  - `GATED_STAGES: tuple[str, ...] = ("screening_ta", "screening_ft", "extraccion", "rob", "reporte")`
  - `class RunInterruption(BaseModel)`: `utc: str`, `stage: str | None = None`, `error: str`
  - `class RunInfo(BaseModel)`: `schema_version: int = 1`, `slug: str`, `timestamp: str`, `started_utc: str`, `engine_version: str`, `python_version: str`, `max_results: int`, `mailto_set: bool`, `protocol_sha256: dict[str, str] = {}`, `prompt_sha256: dict[str, str] = {}`, `resumes: list[str] = []`, `interruptions: list[RunInterruption] = []`, `status: RunStatus = "running"`, `stage: str | None = None`, `updated_utc: str = utc_now_iso()`
  - `class LLMCall(RunMeta)`: + `stage: LLMStage`, `record_id: str | None = None`, `role: str | None = None`; `@classmethod from_meta(cls, meta: RunMeta, *, stage: LLMStage, record_id: str | None = None, role: str | None = None) -> LLMCall`
  - `class JournalEntry(BaseModel)`: `schema_version: int = 1`, `stage: JournalStage`, `record_id: str`, `input_sha256: str`, `output: dict`, `metas: list[LLMCall] = []`, `timestamp_utc: str = utc_now_iso()`
  - `class SearchLogEntry(BaseModel)`: `database: str`, `db_key: str`, `kind: SearchEntryKind`, `declared: bool`, `backend: str | None = None`, `status: SearchEntryStatus`, `source_db: list[str] = []`, `query: str | None = None`, `query_origin: QueryOrigin | None = None`, `query_file: str | None = None`, `query_sha256: str | None = None`, `max_results: int | None = None`, `started_utc: str | None = None`, `finished_utc: str | None = None`, `n_returned: int = 0`, `error: str | None = None`, `file_sha256: str | None = None`
  - `class SearchLog(BaseModel)`: `schema_version: int = 1`, `started_utc: str`, `finished_utc: str`, `max_results: int`, `mailto_set: bool`, `entries: list[SearchLogEntry] = []`
  - `class DedupDuplicate(BaseModel)`: `record_id: str`, `source_db: str`, `kept_record_id: str`, `key: str`
  - `class DedupRename(BaseModel)`: `from_id: str`, `to_id: str`
  - `class DedupReport(BaseModel)`: `schema_version: int = 1`, `n_in: int`, `n_out: int`, `duplicates: list[DedupDuplicate] = []`, `renamed: list[DedupRename] = []`
  - `class RetrievalOutcome(BaseModel)`: `available: bool`, `source_url: str | None = None`, `reason: FulltextReason | None = None`, `detail: str | None = None`, `n_chars: int = 0`, `text_sha256: str | None = None`, `text_file: str | None = None`; validador: `reason is None` ⇔ `available` (si no, `ValidationError`)
  - `class ExcludedReport(BaseModel)`: `record_id: str`, `title: str`, `year: int | None = None`, `doi: str | None = None`, `reason: str`, `reason_source: ReasonSource`
  - `class GateSummary(BaseModel)`: `stage: str`, `action: GateAction`, `actor: str`, `autonomy: str`, `request_sha256: str | None = None`, `decision_sha256: str | None = None`, `n_labels: int = 0`, `n_flag_reviews: int = 0`, `forced_human: bool = False`, `timestamp_utc: str`

- [ ] **Step 1: Test que falla** — crear `tests/test_artifacts.py`:

```python
"""Contratos de artefactos de la Ola 1 (spec 2026-10-04 §4; PR-0)."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from revisia.config import STAGES
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.artifacts import (
    ARTIFACT_SCHEMA_VERSION,
    GATED_STAGES,
    JOURNAL_PATHS,
    DedupReport,
    ExcludedReport,
    FulltextReason,
    GateSummary,
    JournalEntry,
    JournalStage,
    LLMCall,
    LLMStage,
    RetrievalOutcome,
    RunInfo,
    RunStatus,
    SearchLog,
    SearchLogEntry,
)


def _meta() -> RunMeta:
    return RunMeta(
        provider="fake",
        model="fake-1",
        temperature=0.0,
        prompt_sha256=sha256_text("p"),
        response_sha256=sha256_text("r"),
        deterministic=True,
    )


def test_journal_paths_cubren_cada_etapa_con_diario() -> None:
    assert set(JOURNAL_PATHS) == set(get_args(JournalStage))
    rutas = list(JOURNAL_PATHS.values())
    assert len(set(rutas)) == len(rutas)
    assert all(r.endswith(".jsonl") and "\\" not in r for r in rutas)
    assert JOURNAL_PATHS["screening_ta"] == "03_screening/journal.jsonl"
    assert JOURNAL_PATHS["fulltext_retrieval"] == "04_fulltext/retrieval.jsonl"
    assert JOURNAL_PATHS["screening_ft"] == "04_fulltext/journal.jsonl"
    assert JOURNAL_PATHS["extraccion"] == "05_extraction/journal.jsonl"
    assert JOURNAL_PATHS["extraccion_2"] == "05_extraction/journal_2.jsonl"
    assert JOURNAL_PATHS["rob"] == "07_rob/journal.jsonl"
    assert JOURNAL_PATHS["sintesis"] == "06_synthesis/journal.jsonl"
    assert JOURNAL_PATHS["verificacion"] == "06_synthesis/verification.jsonl"


def test_etapas_llm_son_las_de_diario_menos_la_recuperacion() -> None:
    assert set(get_args(JournalStage)) - set(get_args(LLMStage)) == {"fulltext_retrieval"}


def test_gated_stages_en_orden_canonico() -> None:
    assert GATED_STAGES == ("screening_ta", "screening_ft", "extraccion", "rob", "reporte")
    posiciones = [STAGES.index(s) for s in GATED_STAGES]
    assert posiciones == sorted(posiciones)


def test_literales_del_contrato() -> None:
    assert set(get_args(RunStatus)) == {
        "running",
        "paused",
        "rejected",
        "completed",
        "interrupted",
    }
    assert set(get_args(FulltextReason)) == {
        "sin_url_oa",
        "sin_httpx",
        "error_http",
        "texto_vacio",
        "no_disponible",
    }


def test_llm_call_hereda_runmeta_y_etiqueta() -> None:
    call = LLMCall.from_meta(_meta(), stage="screening_ta", record_id="10.1/x", role="member:0")
    assert isinstance(call, RunMeta)
    assert (call.stage, call.record_id, call.role) == ("screening_ta", "10.1/x", "member:0")
    assert call.prompt_sha256 == _meta().prompt_sha256
    assert LLMCall.model_validate_json(call.model_dump_json()) == call
    with pytest.raises(ValidationError):
        LLMCall.from_meta(_meta(), stage="busqueda")


def test_journal_entry_ida_y_vuelta() -> None:
    entry = JournalEntry(
        stage="screening_ft",
        record_id="10.1/x",
        input_sha256=sha256_text("in"),
        output={"record_id": "10.1/x", "ensemble_label": "include"},
        metas=[LLMCall.from_meta(_meta(), stage="screening_ft", record_id="10.1/x")],
    )
    assert entry.schema_version == ARTIFACT_SCHEMA_VERSION == 1
    assert entry.timestamp_utc.endswith("+00:00")
    assert JournalEntry.model_validate_json(entry.model_dump_json()) == entry
    with pytest.raises(ValidationError):
        JournalEntry(stage="dedup", record_id="x", input_sha256="h", output={})


def test_run_info_por_defecto_corriendo_y_sin_correo() -> None:
    info = RunInfo(
        slug="demo",
        timestamp="20261004-120000",
        started_utc="2026-10-04T12:00:00+00:00",
        engine_version="0.7.0",
        python_version="3.13.0",
        max_results=50,
        mailto_set=False,
    )
    assert info.status == "running"
    assert info.resumes == [] and info.interruptions == []
    assert "mailto" not in info.model_dump()
    with pytest.raises(ValidationError):
        RunInfo.model_validate({**info.model_dump(), "status": "pausada"})


def test_search_log_entrada_minima_y_tipos() -> None:
    entry = SearchLogEntry(
        database="Europe PMC",
        db_key="europepmc",
        kind="database",
        declared=True,
        backend="europepmc_search",
        status="ok",
        query="llm screening",
        query_origin="file",
        query_file="00_protocol/search_strings/europepmc.txt",
        query_sha256=sha256_text("llm screening"),
        max_results=50,
        n_returned=3,
        source_db=["EuropePMC"],
    )
    log = SearchLog(
        started_utc="2026-10-04T12:00:00+00:00",
        finished_utc="2026-10-04T12:00:05+00:00",
        max_results=50,
        mailto_set=True,
        entries=[entry],
    )
    assert SearchLog.model_validate_json(log.model_dump_json()) == log
    with pytest.raises(ValidationError):
        SearchLogEntry(database="x", db_key="x", kind="database", declared=True, status="caida")


def test_dedup_report_con_duplicados_y_renombrados() -> None:
    report = DedupReport.model_validate(
        {
            "n_in": 3,
            "n_out": 2,
            "duplicates": [
                {"record_id": "b", "source_db": "Crossref", "kept_record_id": "a", "key": "doi:1"}
            ],
            "renamed": [{"from_id": "c", "to_id": "c#2"}],
        }
    )
    assert report.duplicates[0].kept_record_id == "a"
    assert report.renamed[0].to_id == "c#2"


def test_retrieval_outcome_motivo_solo_si_no_se_recupera() -> None:
    ok = RetrievalOutcome(available=True, source_url="https://x", n_chars=10)
    assert ok.reason is None
    fallo = RetrievalOutcome(available=False, reason="sin_url_oa")
    assert fallo.n_chars == 0
    with pytest.raises(ValidationError, match="necesita un motivo"):
        RetrievalOutcome(available=False)
    with pytest.raises(ValidationError, match="no lleva motivo"):
        RetrievalOutcome(available=True, reason="error_http")


def test_excluded_report_exige_origen_de_la_razon() -> None:
    rep = ExcludedReport(record_id="a", title="T", reason="población", reason_source="ai")
    assert rep.year is None and rep.doi is None
    with pytest.raises(ValidationError):
        ExcludedReport(record_id="a", title="T", reason="x", reason_source="agente")


def test_gate_summary_acciones_validas() -> None:
    summary = GateSummary(
        stage="reporte",
        action="approve",
        actor="human:revisora",
        autonomy="A1",
        timestamp_utc="2026-10-04T12:00:00+00:00",
    )
    assert (summary.n_labels, summary.n_flag_reviews, summary.forced_human) == (0, 0, False)
    with pytest.raises(ValidationError):
        GateSummary(stage="reporte", action="label", actor="h", autonomy="A1", timestamp_utc="t")
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_artifacts.py -v`
Expected: ERROR de colección, `ModuleNotFoundError: No module named 'revisia.schemas.artifacts'`.

- [ ] **Step 3: Implementar** — crear `revisia/schemas/artifacts.py`:

```python
"""Contratos de los artefactos de una corrida (Ola 1 · PR-0).

Un solo módulo con los modelos y constantes que comparten la pista del
pipeline (PR-A a PR-D) y la del auditor (PR-E): ambas importan de aquí en vez
de duplicar nombres de fichero, etapas o campos. La auditoría 2026-09-03 (C3,
A11) mostró que un auditor que "sabe" los artefactos por su cuenta deja de
detectar incoherencias en cuanto el pipeline cambia; con un contrato único,
productor y verificador no se pueden contradecir en silencio.

La especificación completa (qué fichero existe cuándo y qué relaciones deben
cumplirse entre ellos) está en
``docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md`` §4.

Convenciones (spec §4.1): horas ISO-8601 UTC con zona (``utc_now_iso``), rutas
relativas con ``/``, ``schema_version`` en todo JSON nuevo. Ningún
``record_id`` se usa como nombre de fichero (los DOI llevan ``/``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from revisia.provenance.runmeta import RunMeta, utc_now_iso

# Versión del esquema de todos los artefactos JSON nuevos de la Ola 1. Sube
# solo con un cambio incompatible de alguno de estos modelos.
ARTIFACT_SCHEMA_VERSION: int = 1

# Estados de una corrida en ``run.json`` (spec §4.3). ``paused`` sigue saliendo
# con rc 0; ``interrupted`` es un error a mitad de corrida que se reanuda (D14).
RunStatus = Literal["running", "paused", "rejected", "completed", "interrupted"]

# Etapas que llaman a un LLM y, por tanto, etiquetan cada ``LLMCall``.
LLMStage = Literal[
    "screening_ta",
    "screening_ft",
    "extraccion",
    "extraccion_2",
    "rob",
    "sintesis",
    "verificacion",
]

# Etapas con diario por registro (D3): las de LLM más la recuperación de texto
# completo, que no llama a ningún LLM pero sí a la red.
JournalStage = Literal[
    "screening_ta",
    "fulltext_retrieval",
    "screening_ft",
    "extraccion",
    "extraccion_2",
    "rob",
    "sintesis",
    "verificacion",
]

# Motivo por el que no se recuperó un texto completo (auditoría 2026-09-03,
# M11: hasta la Ola 1 el fallo no se guardaba). ``no_disponible`` es el motivo
# genérico cuando quien recupera no da uno (p. ej. un ``fetch_fn`` inyectado).
FulltextReason = Literal["sin_url_oa", "sin_httpx", "error_http", "texto_vacio", "no_disponible"]

# Ruta (relativa al directorio de la corrida) del diario de cada etapa (§4.2).
JOURNAL_PATHS: dict[str, str] = {
    "screening_ta": "03_screening/journal.jsonl",
    "fulltext_retrieval": "04_fulltext/retrieval.jsonl",
    "screening_ft": "04_fulltext/journal.jsonl",
    "extraccion": "05_extraction/journal.jsonl",
    "extraccion_2": "05_extraction/journal_2.jsonl",
    "rob": "07_rob/journal.jsonl",
    "sintesis": "06_synthesis/journal.jsonl",
    "verificacion": "06_synthesis/verification.jsonl",
}

# Etapas con checkpoint humano, en el orden canónico de ``config.STAGES``. Los
# ficheros del gate viven en ``<run_dir>/<gate>/`` (review_request.yml,
# decision.template.yml, decision.yml).
GATED_STAGES: tuple[str, ...] = ("screening_ta", "screening_ft", "extraccion", "rob", "reporte")

SearchEntryKind = Literal["database", "manual_import", "injected"]
SearchEntryStatus = Literal["ok", "failed", "manual_only", "unknown"]
QueryOrigin = Literal["file", "question_fallback"]
ReasonSource = Literal["human", "ai"]
GateAction = Literal["approve", "reject", "auto-proceed"]


class RunInterruption(BaseModel):
    """Una interrupción registrada en ``run.json`` (error redactado)."""

    utc: str
    stage: str | None = None
    error: str


class RunInfo(BaseModel):
    """``run.json``: identidad, parámetros, huellas, historia y estado de la corrida.

    Es lo primero que se escribe (spec §4.2). ``mailto_set`` registra si hubo
    correo, nunca el correo. ``protocol_sha256`` va sobre ``00_protocol/``
    (texto con CRLF convertido a LF) y ``prompt_sha256`` sobre
    ``revisia/prompts/`` con claves ``"<agente>/v1.md"``.
    """

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    slug: str
    timestamp: str
    started_utc: str
    engine_version: str
    python_version: str
    max_results: int
    mailto_set: bool
    protocol_sha256: dict[str, str] = Field(default_factory=dict)
    prompt_sha256: dict[str, str] = Field(default_factory=dict)
    resumes: list[str] = Field(default_factory=list)
    interruptions: list[RunInterruption] = Field(default_factory=list)
    status: RunStatus = "running"
    stage: str | None = None
    updated_utc: str = Field(default_factory=utc_now_iso)


class LLMCall(RunMeta):
    """Una línea de ``llm_calls.jsonl``: el ``RunMeta`` más su contexto.

    Append-only, en orden de finalización de la llamada. Una caída puede dejar
    llamadas huérfanas (reales, sin decisión en el diario): son válidas.
    ``record_id`` vale ``"sintesis"``/``"verificacion"`` en las etapas globales
    y ``role`` es ``"member:<i>"`` en el ensemble de T/A.
    """

    stage: LLMStage
    record_id: str | None = None
    role: str | None = None

    @classmethod
    def from_meta(
        cls,
        meta: RunMeta,
        *,
        stage: LLMStage,
        record_id: str | None = None,
        role: str | None = None,
    ) -> LLMCall:
        """Etiqueta un ``RunMeta`` con su etapa, registro y rol."""
        data = meta.model_dump()
        data.update(stage=stage, record_id=record_id, role=role)
        return cls.model_validate(data)


class JournalEntry(BaseModel):
    """Una línea del diario de una etapa (D3).

    La clave es ``(record_id, input_sha256)``. Una entrada cuyo
    ``input_sha256`` ya no corresponde a las entradas vigentes queda obsoleta,
    pero sigue siendo válida. ``output`` es el resultado serializado de la etapa
    (``ScreeningDecision`` sin campos humanos, ``RetrievalOutcome``,
    ``ExtractionRecord``, ``RoBAssessment``, ``{"narrative": ...}`` o
    ``VerificationReport``).
    """

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    stage: JournalStage
    record_id: str
    input_sha256: str
    output: dict
    metas: list[LLMCall] = Field(default_factory=list)
    timestamp_utc: str = Field(default_factory=utc_now_iso)


class SearchLogEntry(BaseModel):
    """Una entrada de ``01_search/log.json``: una base, un fichero importado o
    la búsqueda inyectada (PRISMA-S 1/8/13; auditoría 2026-09-03, M12)."""

    database: str
    db_key: str
    kind: SearchEntryKind
    declared: bool
    backend: str | None = None
    status: SearchEntryStatus
    source_db: list[str] = Field(default_factory=list)
    query: str | None = None
    query_origin: QueryOrigin | None = None
    query_file: str | None = None
    query_sha256: str | None = None
    max_results: int | None = None
    started_utc: str | None = None
    finished_utc: str | None = None
    n_returned: int = 0
    error: str | None = None
    file_sha256: str | None = None


class SearchLog(BaseModel):
    """``01_search/log.json``: su existencia marca la búsqueda como completa."""

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    started_utc: str
    finished_utc: str
    max_results: int
    mailto_set: bool
    entries: list[SearchLogEntry] = Field(default_factory=list)


class DedupDuplicate(BaseModel):
    """Un registro descartado por duplicado y el que se conservó en su lugar."""

    record_id: str
    source_db: str
    kept_record_id: str
    key: str


class DedupRename(BaseModel):
    """Un ``record_id`` repetido entre los conservados, renombrado (``<id>#2``)."""

    from_id: str
    to_id: str


class DedupReport(BaseModel):
    """``02_dedup/dedup.json``: trazabilidad completa de la deduplicación."""

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    n_in: int
    n_out: int
    duplicates: list[DedupDuplicate] = Field(default_factory=list)
    renamed: list[DedupRename] = Field(default_factory=list)


class RetrievalOutcome(BaseModel):
    """Resultado de recuperar el texto completo de un registro (D2, M11).

    ``reason`` es nulo si y solo si ``available``: un fallo sin motivo, o un
    éxito con motivo, no es un resultado válido.
    """

    available: bool
    source_url: str | None = None
    reason: FulltextReason | None = None
    detail: str | None = None
    n_chars: int = 0
    text_sha256: str | None = None
    text_file: str | None = None

    @model_validator(mode="after")
    def _motivo_solo_si_falla(self) -> RetrievalOutcome:
        if self.available and self.reason is not None:
            raise ValueError("un texto completo recuperado no lleva motivo de fallo")
        if not self.available and self.reason is None:
            raise ValueError("un texto completo no recuperado necesita un motivo")
        return self


class ExcludedReport(BaseModel):
    """Un informe excluido en elegibilidad, con su razón (PRISMA 2020, 16b)."""

    record_id: str
    title: str
    year: int | None = None
    doi: str | None = None
    reason: str
    reason_source: ReasonSource


class GateSummary(BaseModel):
    """Decisión efectiva de un gate, reducida del ledger por ``summarize_gates``.

    La decisión efectiva de una etapa es su **última** entrada ``approve``,
    ``reject`` o ``auto-proceed`` (D14: se puede reanudar tras un rechazo y
    todas quedan registradas). Lo usan el pipeline (checklist trAIce y
    ``metodologia.md``, M13) y el auditor, para que no se contradigan (D12).

    Attributes:
        stage: etapa del gate.
        action: ``approve`` | ``reject`` | ``auto-proceed``.
        actor: quién decidió (``human:<n>``, ``auto-approve (demo)``,
            ``agent:<etapa>``).
        autonomy: autonomía con la que se aplicó el gate.
        request_sha256: hash de la solicitud a la que responde (``None`` en
            entradas anteriores a la Ola 1).
        decision_sha256: hash de la ``decision.yml`` aplicada (``None`` en
            ``auto-proceed`` y en entradas anteriores a la Ola 1).
        n_labels: entradas ``label`` de esa etapa con el mismo
            ``decision_sha256`` (contadas en el ledger, no tomadas del
            ``detail``: así el auditor puede contrastarlas).
        n_flag_reviews: ídem con ``flag_review`` (citas adjudicadas, D8).
        forced_human: el gate exigió humano por ``hallucination_flagged`` (M5).
        timestamp_utc: hora de la entrada efectiva.
    """

    stage: str
    action: GateAction
    actor: str
    autonomy: str
    request_sha256: str | None = None
    decision_sha256: str | None = None
    n_labels: int = 0
    n_flag_reviews: int = 0
    forced_human: bool = False
    timestamp_utc: str
```

- [ ] **Step 4: Verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_artifacts.py -v`
Expected: PASS, 12 tests.

Run: `uv run python -c "import revisia.schemas.artifacts; import revisia.provenance.ledger"`
Expected: sin salida (no hay import circular).

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/schemas/artifacts.py tests/test_artifacts.py
git commit -m "feat(schemas): contratos de artefactos de la Ola 1" -m "revisia/schemas/artifacts.py reúne los modelos y constantes que comparten pipeline y auditor: RunInfo, LLMCall, JournalEntry, SearchLog, DedupReport, RetrievalOutcome, ExcludedReport, GateSummary, JOURNAL_PATHS y GATED_STAGES (spec 2026-10-04 §4.3 y §4.5). Sin cambio de comportamiento." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Hashes canónicos y reductor del ledger

**Files:**
- Modify: `revisia/provenance/runmeta.py` (import `json` junto a `import hashlib`, l.16-17; dos funciones nuevas tras `utc_now_iso`, l.27-29)
- Modify: `revisia/provenance/ledger.py` (imports l.10-16; constantes antes de `class DecisionEntry`, l.19; función nueva al final del fichero, tras l.62)
- Test: `tests/test_contratos_provenance.py` (nuevo)

**Interfaces:**
- Consumes: `GateSummary` (Tarea 1); `DecisionEntry` (existente: `stage`, `actor`, `autonomy`, `action`, `target`, `detail: dict`, `timestamp_utc`).
- Produces:
  - `revisia.provenance.runmeta.canonical_json(value: object) -> str` (`json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)`; lanza `ValueError` con NaN/inf)
  - `revisia.provenance.runmeta.canonical_sha256(value: object) -> str` (SHA-256 hex de `canonical_json(value).encode("utf-8")`)
  - `revisia.provenance.ledger.LEDGER_ACTIONS: frozenset[str]` = `{"approve", "reject", "auto-proceed", "label", "flag_review"}`
  - `revisia.provenance.ledger.GATE_DECISION_ACTIONS: frozenset[str]` = `{"approve", "reject", "auto-proceed"}`
  - `revisia.provenance.ledger.HUMAN_ACTOR_PREFIX: str = "human:"`
  - `revisia.provenance.ledger.AUTO_APPROVE_ACTOR: str = "auto-approve (demo)"`
  - `revisia.provenance.ledger.summarize_gates(entries: Iterable[DecisionEntry]) -> dict[str, GateSummary]` — clave = etapa con decisión efectiva (la última `approve|reject|auto-proceed` en orden de fichero); `request_sha256`/`decision_sha256`/`forced_human` salen de `detail`; `n_labels`/`n_flag_reviews` cuentan las `label`/`flag_review` de esa etapa con el mismo `decision_sha256` (0 si es `None`). Las etapas sin decisión no aparecen.

- [ ] **Step 1: Test que falla** — crear `tests/test_contratos_provenance.py`:

```python
"""Hashes canónicos y reductor del ledger (spec 2026-10-04 §4.1, §4.3; PR-0)."""

from __future__ import annotations

import hashlib
import math

import pytest

from revisia.provenance.ledger import (
    AUTO_APPROVE_ACTOR,
    GATE_DECISION_ACTIONS,
    HUMAN_ACTOR_PREFIX,
    LEDGER_ACTIONS,
    DecisionEntry,
    summarize_gates,
)
from revisia.provenance.runmeta import canonical_json, canonical_sha256

# ── canonical_json / canonical_sha256 ───────────────────────────────────


def test_canonical_json_ordena_claves_sin_espacios_y_utf8_literal() -> None:
    assert canonical_json({"b": 1, "a": "ñ", "c": [1, {"z": None, "y": True}]}) == (
        '{"a":"ñ","b":1,"c":[1,{"y":true,"z":null}]}'
    )


def test_canonical_sha256_no_depende_del_orden_de_insercion() -> None:
    uno = {"stage": "screening_ta", "records": [{"id": "10.1/x", "label": "include"}]}
    otro = {"records": [{"label": "include", "id": "10.1/x"}], "stage": "screening_ta"}
    assert canonical_sha256(uno) == canonical_sha256(otro)
    esperado = hashlib.sha256(canonical_json(uno).encode("utf-8")).hexdigest()
    assert canonical_sha256(uno) == esperado
    assert len(esperado) == 64


@pytest.mark.parametrize("valor", [math.nan, math.inf, -math.inf])
def test_canonical_json_rechaza_no_finitos(valor: float) -> None:
    with pytest.raises(ValueError):
        canonical_json({"recall": valor})


# ── Constantes del ledger ────────────────────────────────────────────────


def test_constantes_del_ledger() -> None:
    assert set(LEDGER_ACTIONS) == {"approve", "reject", "auto-proceed", "label", "flag_review"}
    assert set(GATE_DECISION_ACTIONS) == {"approve", "reject", "auto-proceed"}
    assert GATE_DECISION_ACTIONS < LEDGER_ACTIONS
    assert HUMAN_ACTOR_PREFIX == "human:"
    assert AUTO_APPROVE_ACTOR == "auto-approve (demo)"
    # Las acciones de la reconstrucción C3 no las emite el motor.
    assert not {"propose", "exclude", "verify"} & LEDGER_ACTIONS


# ── summarize_gates ──────────────────────────────────────────────────────


def _e(stage: str, action: str, actor: str = "human:ana", **detail) -> DecisionEntry:
    target = detail.pop("target", None)
    return DecisionEntry(
        stage=stage, actor=actor, autonomy="A1", action=action, target=target, detail=detail
    )


def test_summarize_gates_ledger_vacio() -> None:
    assert summarize_gates([]) == {}


def test_summarize_gates_ultima_decision_gana_tras_rechazo() -> None:
    resumen = summarize_gates(
        [
            _e("screening_ta", "reject", request_sha256="r1", decision_sha256="d1"),
            _e("screening_ta", "approve", request_sha256="r1", decision_sha256="d2"),
        ]
    )
    ta = resumen["screening_ta"]
    assert (ta.action, ta.request_sha256, ta.decision_sha256) == ("approve", "r1", "d2")


def test_summarize_gates_cuenta_solo_etiquetas_de_la_decision_efectiva() -> None:
    resumen = summarize_gates(
        [
            # Decisión anterior (rechazada, ya sin etiquetas) y una etiqueta huérfana.
            _e("screening_ft", "label", target="a", decision_sha256="viejo"),
            _e("screening_ft", "reject", decision_sha256="viejo"),
            # Decisión efectiva con dos etiquetas.
            _e("screening_ft", "label", target="a", decision_sha256="nuevo"),
            _e("screening_ft", "label", target="b", decision_sha256="nuevo"),
            _e("screening_ft", "approve", decision_sha256="nuevo", request_sha256="r"),
            # Una etiqueta de otra etapa con el mismo hash no cuenta.
            _e("screening_ta", "label", target="z", decision_sha256="nuevo"),
        ]
    )
    assert resumen["screening_ft"].n_labels == 2
    assert resumen["screening_ft"].n_flag_reviews == 0
    assert "screening_ta" not in resumen  # sin approve/reject/auto-proceed


def test_summarize_gates_flag_reviews_y_forced_human() -> None:
    resumen = summarize_gates(
        [
            _e("reporte", "flag_review", target="flag:0", decision_sha256="d"),
            _e("reporte", "flag_review", target="flag:3", decision_sha256="d"),
            _e("reporte", "approve", decision_sha256="d", forced_human=True),
        ]
    )
    reporte = resumen["reporte"]
    assert (reporte.n_flag_reviews, reporte.forced_human) == (2, True)
    assert reporte.actor.startswith(HUMAN_ACTOR_PREFIX)


def test_summarize_gates_auto_proceed_y_ledger_antiguo() -> None:
    resumen = summarize_gates(
        [
            _e("sintesis", "auto-proceed", actor="agent:sintesis", reason="autonomía A2"),
            # Entrada de la Ola 0: sin hashes en el detail.
            _e("reporte", "approve", actor=AUTO_APPROVE_ACTOR, reason="demo"),
        ]
    )
    assert resumen["sintesis"].action == "auto-proceed"
    assert resumen["sintesis"].decision_sha256 is None
    assert resumen["reporte"].request_sha256 is None
    assert resumen["reporte"].n_labels == 0
    assert resumen["reporte"].actor == AUTO_APPROVE_ACTOR
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_provenance.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'AUTO_APPROVE_ACTOR' from 'revisia.provenance.ledger'`.

- [ ] **Step 3: Implementar `canonical_json`/`canonical_sha256`** en `revisia/provenance/runmeta.py`. Sustituir

```python
import hashlib
from datetime import UTC, datetime
```

por

```python
import hashlib
import json
from datetime import UTC, datetime
```

y, justo después de la función `utc_now_iso` (antes de `class RunMeta`), añadir:

```python
def canonical_json(value: object) -> str:
    """Serialización JSON canónica: claves ordenadas, sin espacios, UTF-8 literal.

    Es la base de todos los hashes de contenido de la Ola 1 (``request_sha256``,
    ``decision_sha256``, ``input_sha256`` del diario): dos estructuras iguales
    dan el mismo texto sin importar el orden de inserción de sus claves.
    ``allow_nan=False`` rechaza ``NaN``/``Infinity``, que no son JSON y harían
    el hash irreproducible fuera de Python (spec 2026-10-04 §4.1).

    Raises:
        ValueError: si ``value`` contiene ``NaN`` o infinitos.
        TypeError: si ``value`` no es serializable a JSON.
    """
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def canonical_sha256(value: object) -> str:
    """SHA-256 hexadecimal de ``canonical_json(value)`` codificado en UTF-8."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Implementar el ledger** en `revisia/provenance/ledger.py`. Sustituir el bloque de imports

```python
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from revisia.provenance.runmeta import utc_now_iso
```

por

```python
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from revisia.provenance.runmeta import utc_now_iso

if TYPE_CHECKING:
    from revisia.schemas.artifacts import GateSummary

# Acciones que el motor escribe en el ledger (spec 2026-10-04 §4.3). El auditor
# rechaza cualquier otra: la reconstrucción de la auditoría 2026-09-03 (C3)
# traía `propose`, `exclude` y `verify`, que ningún código del motor emite.
LEDGER_ACTIONS: frozenset[str] = frozenset(
    {"approve", "reject", "auto-proceed", "label", "flag_review"}
)
# Subconjunto que cierra un gate: la última de una etapa es su decisión efectiva.
GATE_DECISION_ACTIONS: frozenset[str] = frozenset({"approve", "reject", "auto-proceed"})
# Prefijo de los actores humanos (`human:<nombre>`, el de `decision.yml`).
HUMAN_ACTOR_PREFIX = "human:"
# Actor sintético de `--auto-approve`: no es humano (D8, D9).
AUTO_APPROVE_ACTOR = "auto-approve (demo)"
```

`GateSummary` se importa solo para tipar y, dentro de la función, en tiempo de ejecución: `revisia.schemas.artifacts` importa `revisia.provenance.runmeta`, que carga el paquete `revisia.provenance` y con él este módulo; un import a nivel de módulo sería circular. Añadir al final del fichero:

```python


def summarize_gates(entries: Iterable[DecisionEntry]) -> dict[str, GateSummary]:
    """Reduce el ledger a la decisión efectiva de cada etapa (D12, D14).

    La decisión efectiva de una etapa es su **última** entrada ``approve``,
    ``reject`` o ``auto-proceed`` en el orden del fichero (se puede reanudar
    tras un rechazo; todas quedan registradas). ``n_labels`` y
    ``n_flag_reviews`` cuentan las entradas ``label``/``flag_review`` de esa
    etapa que llevan el mismo ``decision_sha256`` que la decisión efectiva; si
    esta no lo tiene (``auto-proceed`` o ledger anterior a la Ola 1), valen 0.

    Es el único reductor del ledger: lo usan el pipeline (checklist trAIce y
    métodos, M13) y el auditor, para que no se contradigan (auditoría
    2026-09-03, C3/M13). Las etapas sin decisión no aparecen en el resultado.
    """
    from revisia.schemas.artifacts import GateSummary

    entries = list(entries)
    effective: dict[str, DecisionEntry] = {}
    for entry in entries:
        if entry.action in GATE_DECISION_ACTIONS:
            effective[entry.stage] = entry

    summaries: dict[str, GateSummary] = {}
    for stage, decision in effective.items():
        decision_sha = decision.detail.get("decision_sha256")
        n_labels = n_flags = 0
        if decision_sha is not None:
            for entry in entries:
                if entry.stage != stage or entry.detail.get("decision_sha256") != decision_sha:
                    continue
                if entry.action == "label":
                    n_labels += 1
                elif entry.action == "flag_review":
                    n_flags += 1
        summaries[stage] = GateSummary(
            stage=stage,
            action=decision.action,
            actor=decision.actor,
            autonomy=decision.autonomy,
            request_sha256=decision.detail.get("request_sha256"),
            decision_sha256=decision_sha,
            n_labels=n_labels,
            n_flag_reviews=n_flags,
            forced_human=bool(decision.detail.get("forced_human", False)),
            timestamp_utc=decision.timestamp_utc,
        )
    return summaries
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_provenance.py -v`
Expected: PASS, 11 tests.

Run: `uv run python -c "import revisia.provenance.ledger as l; import revisia.schemas.artifacts; print(l.summarize_gates([]))"`
Expected: `{}`.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS (330 + 23 = 353 recogidos).

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/provenance/runmeta.py revisia/provenance/ledger.py tests/test_contratos_provenance.py
git commit -m "feat(provenance): hashes canónicos y reductor único del ledger" -m "canonical_json/canonical_sha256 (claves ordenadas, sin NaN) son la base de request_sha256, decision_sha256 e input_sha256. summarize_gates reduce el ledger a la decisión efectiva por etapa (la última approve/reject/auto-proceed) y cuenta las label/flag_review de esa decisión; lo comparten pipeline y auditor (D12). LEDGER_ACTIONS, HUMAN_ACTOR_PREFIX y AUTO_APPROVE_ACTOR como constantes. Spec 2026-10-04 §4.1 y §4.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Campos y constantes aditivos (`KNOWN_THRESHOLDS`, `ScreeningDecision`, `PrismaCounts`)

**Files:**
- Modify: `revisia/config.py` (constante tras `JUDGMENT_STAGES`, l.51)
- Modify: `revisia/schemas/screening.py` (docstring de `ScreeningDecision` l.40-48; campos tras `citations_checked`, l.56)
- Modify: `revisia/exports/prisma_flow.py` (docstring de `PrismaCounts` l.46-49; campos l.64-66)
- Test: `tests/test_contratos_aditivos.py` (nuevo)

**Interfaces:**
- Consumes: nada de las tareas anteriores.
- Produces:
  - `revisia.config.KNOWN_THRESHOLDS: frozenset[str]` = `{"kappa_min", "recall_target", "wmcc_fn_weight"}`
  - `ScreeningDecision` + `fulltext_status: Literal["retrieved", "not_retrieved"] | None = None`, `human_reason: str | None = None`, `human_actor: str | None = None`
  - `PrismaCounts` + `fulltext_sought: int = 0`, `fulltext_not_retrieved: int = 0`, `fulltext_rescued: int = 0`, `excluded_ft_human: int = 0`, `excluded_ft_ai: int = 0` (PR-0 aún conserva `fulltext_abstract_only`; lo retira PR-B, Tarea 10)

- [ ] **Step 1: Test que falla** — crear `tests/test_contratos_aditivos.py`:

```python
"""Campos y constantes aditivos de PR-0: no cambian el comportamiento (spec §4.5)."""

from __future__ import annotations

from pathlib import Path

from revisia.config import KNOWN_THRESHOLDS, load_protocol
from revisia.exports import PrismaCounts
from revisia.schemas.screening import ScreeningDecision

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"


def test_known_thresholds_cubre_la_plantilla_y_el_pipeline() -> None:
    assert set(KNOWN_THRESHOLDS) == {"kappa_min", "recall_target", "wmcc_fn_weight"}
    assert set(load_protocol(TEMPLATE_DIR).thresholds) <= KNOWN_THRESHOLDS


def test_screening_decision_campos_nuevos_opcionales() -> None:
    antigua = {"record_id": "a", "ensemble_label": "include", "final_label": "include"}
    decision = ScreeningDecision.model_validate(antigua)
    assert decision.fulltext_status is None
    assert decision.human_reason is None and decision.human_actor is None
    no_recuperado = ScreeningDecision(
        record_id="b", phase="fulltext", fulltext_status="not_retrieved"
    )
    assert no_recuperado.votes == [] and no_recuperado.ensemble_label is None


def test_prisma_counts_campos_nuevos_valen_cero() -> None:
    counts = PrismaCounts(identified=10, screened=8, included=2)
    assert (
        counts.fulltext_sought,
        counts.fulltext_not_retrieved,
        counts.fulltext_rescued,
        counts.excluded_ft_human,
        counts.excluded_ft_ai,
    ) == (0, 0, 0, 0, 0)
    assert PrismaCounts.model_validate(counts.model_dump()) == counts
```

(El último test no pasa `fulltext_assessed` a propósito: en PR-B el validador de manifiestos antiguos fija `fulltext_sought = fulltext_assessed` cuando falta `fulltext_sought`, y así este test sigue en verde.)

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_aditivos.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'KNOWN_THRESHOLDS' from 'revisia.config'`.

- [ ] **Step 3: Implementar.** En `revisia/config.py`, justo después de la línea `JUDGMENT_STAGES: tuple[str, ...] = (...)`, añadir:

```python

# Claves de `thresholds` que el motor entiende (spec 2026-10-04 §4.5). El
# auditor avisa de cualquier otra: una errata como `kapa_min` desactivaba el
# umbral en silencio (auditoría 2026-09-03, A11; D7).
KNOWN_THRESHOLDS: frozenset[str] = frozenset({"kappa_min", "recall_target", "wmcc_fn_weight"})
```

En `revisia/schemas/screening.py`, en la docstring de `ScreeningDecision`, tras la línea `citations_checked: ids verificados contra el corpus (anti-alucinación).`, añadir:

```
        fulltext_status: solo en ``fulltext``: ``"retrieved"`` o
            ``"not_retrieved"``. Un no recuperado no se criba con IA: lleva
            ``votes == []`` y ``ensemble_label is None`` (D2; auditoría
            2026-09-03, M11).
        human_reason: razón de la etiqueta humana (obligatoria al excluir en FT
            y al rescatar un no recuperado).
        human_actor: actor de ``decision.yml`` que puso la etiqueta humana.
```

y tras el campo `citations_checked: list[str] = Field(default_factory=list)` añadir:

```python
    fulltext_status: Literal["retrieved", "not_retrieved"] | None = None
    human_reason: str | None = None
    human_actor: str | None = None
```

En `revisia/exports/prisma_flow.py`, en la docstring de `PrismaCounts`, sustituir

```
        fulltext_assessed: informes evaluados para elegibilidad.
        fulltext_abstract_only: de los evaluados, cuántos sin texto completo
            recuperable (se evaluaron con título/abstract; limitación declarada).
        excluded_ft: excluidos en la evaluación de elegibilidad.
```

por

```
        fulltext_sought: informes buscados para recuperación (pasaron T/A).
        fulltext_not_retrieved: informes buscados que no se recuperaron y que
            nadie rescató (caja "informes no recuperados").
        fulltext_rescued: no recuperados que el revisor consiguió por otra vía
            y evaluó (D2); cuentan como evaluados.
        fulltext_assessed: informes evaluados para elegibilidad.
        fulltext_abstract_only: de los evaluados, cuántos sin texto completo
            recuperable (se evaluaron con título/abstract; limitación declarada).
        excluded_ft: excluidos en la evaluación de elegibilidad.
        excluded_ft_human: de los excluidos en elegibilidad, cuántos por
            decisión humana (PRISMA-trAIce R1).
        excluded_ft_ai: de los excluidos en elegibilidad, cuántos por la IA.
```

y los campos

```python
    fulltext_assessed: int = 0
    fulltext_abstract_only: int = 0
    excluded_ft: int = 0
```

por

```python
    fulltext_sought: int = 0
    fulltext_not_retrieved: int = 0
    fulltext_rescued: int = 0
    fulltext_assessed: int = 0
    fulltext_abstract_only: int = 0
    excluded_ft: int = 0
    excluded_ft_human: int = 0
    excluded_ft_ai: int = 0
```

Los renderers no se tocan: las cajas nuevas llegan en PR-B.

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_aditivos.py -v`
Expected: PASS, 3 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS (356 recogidos): nada cambia de comportamiento.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/config.py revisia/schemas/screening.py revisia/exports/prisma_flow.py tests/test_contratos_aditivos.py
git commit -m "feat(contratos): KNOWN_THRESHOLDS y campos aditivos de cribado y conteos PRISMA" -m "ScreeningDecision gana fulltext_status, human_reason y human_actor; PrismaCounts gana fulltext_sought, fulltext_not_retrieved, fulltext_rescued, excluded_ft_human y excluded_ft_ai (todos con default). Sin cambio de comportamiento: los usan PR-B, PR-D y el auditor. Spec 2026-10-04 §4.3 y §4.5." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Dobles de prueba compartidos (`tests/fakes.py`)

**Files:**
- Create: `tests/fakes.py`
- Test: `tests/test_fakes.py` (nuevo)

**Interfaces:**
- Consumes: `revisia.llm.providers.fake._fabricate_model(schema: type[BaseModel]) -> BaseModel` (existente, privada; se reutiliza a propósito para construir instancias válidas igual que `FakeProvider`); `revisia.agents.fulltext.FullText` (existente; en PR-0 aún sin `reason`/`detail`).
- Produces:
  - `fakes.PALABRAS_POR_DEFECTO: dict[str, ScreeningLabel]` = `{"irrelevante": "exclude", "dudoso": "unclear"}`
  - `class fakes.ScriptedProvider` (cumple `revisia.llm.base.LLMProvider`): `name = "fake"`; `__init__(self, model: str = "fake-guion", *, fail_at: int | None = None, palabras: Mapping[str, ScreeningLabel] | None = None, criterio_exclusion: str = "fuera de alcance")`; atributos `model: str`, `fail_at: int | None`, `palabras: dict[str, ScreeningLabel]`, `criterio_exclusion: str`, `calls: int`, `prompts: list[str]`; métodos `label_for(prompt: str) -> ScreeningLabel`, `complete(req: LLMRequest) -> LLMResponse`, `structured(req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]`. Cada `RunMeta` lleva `provider="fake"` y `deterministic=True`. `fail_at=k` (1, 2, …) hace que la llamada número `k` lance `RuntimeError("429 Too Many Requests")`; las demás responden. `calls` cuenta todas las llamadas, incluida la que falla. En `structured`, si el schema tiene un campo `label` con los tres valores de `ScreeningLabel`, pone la etiqueta del guion (primera palabra clave que aparezca en el prompt, sin distinguir mayúsculas; si ninguna, `include`), `confidence=0.9`, `rationale="guion: <label>"` y `criteria_violated=[criterio_exclusion]` solo si excluye.
  - `fakes.fetch_disponible(record: SearchRecord) -> FullText` (siempre `available=True`, `source_url` estable)
  - `fakes.fetch_no_disponible(ids: Iterable[str]) -> Callable[[SearchRecord], FullText]` (los `ids` dados devuelven `FullText(text=abstract, available=False)`; el resto, `fetch_disponible`)
  - Uso en un test de pipeline: `monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)` con `from revisia.orchestration import pipeline as pipeline_mod`.

- [ ] **Step 1: Test que falla** — crear `tests/test_fakes.py`:

```python
"""Los dobles compartidos de la Ola 1 hacen lo que prometen (tests/fakes.py)."""

from __future__ import annotations

import pytest
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible

from revisia.agents.extraccion import extract_record
from revisia.agents.screening import ScreenerMember, screen_record
from revisia.agents.screening_ft import screen_fulltext
from revisia.llm.base import LLMProvider, LLMRequest
from revisia.schemas.records import SearchRecord


def _rec(rid: str, title: str, abstract: str = "") -> SearchRecord:
    return SearchRecord(record_id=rid, title=title, abstract=abstract)


def _cribar(proveedor: ScriptedProvider, record: SearchRecord):
    member = ScreenerMember(provider=proveedor, model_name="fake:guion")
    return screen_record([member], question="¿X?", criteria="- c: incluir", record=record)


def test_cumple_el_protocolo_y_declara_fake_determinista() -> None:
    proveedor = ScriptedProvider()
    assert isinstance(proveedor, LLMProvider)
    respuesta = proveedor.complete(LLMRequest(prompt="sintetiza"))
    assert "[" not in respuesta.text
    assert (respuesta.meta.provider, respuesta.meta.deterministic) == ("fake", True)
    assert respuesta.meta.model == "fake-guion"


@pytest.mark.parametrize(
    ("titulo", "esperado"),
    [
        ("Estudio irrelevante para la pregunta", "exclude"),
        ("Un caso DUDOSO", "unclear"),
        ("LLM screening for systematic reviews", "include"),
    ],
)
def test_etiqueta_por_palabra_clave_en_el_cribado(titulo: str, esperado: str) -> None:
    decision, metas = _cribar(ScriptedProvider(), _rec("r", titulo))
    assert decision.ensemble_label == esperado
    assert decision.votes[0].label == esperado
    assert len(metas) == 1


def test_exclusion_lleva_criterio_violado() -> None:
    proveedor = ScriptedProvider(criterio_exclusion="población")
    decision, _ = screen_fulltext(
        proveedor,
        "fake:guion",
        question="¿X?",
        criteria="- c",
        record=_rec("r", "T"),
        text="texto irrelevante",
    )
    assert decision.ensemble_label == "exclude"
    assert decision.votes[0].criteria_violated == ["población"]


def test_esquemas_sin_etiqueta_se_fabrican_como_fake() -> None:
    extraccion, meta = extract_record(
        ScriptedProvider(), record=_rec("r", "irrelevante"), form_fields=[{"key": "n"}]
    )
    assert extraccion.study_id == "r"
    assert meta.provider == "fake"


def test_cuenta_llamadas_y_falla_en_la_k() -> None:
    proveedor = ScriptedProvider(fail_at=2)
    _cribar(proveedor, _rec("a", "registro alfa"))
    with pytest.raises(RuntimeError, match="429 Too Many Requests"):
        _cribar(proveedor, _rec("b", "registro beta"))
    _cribar(proveedor, _rec("c", "registro gamma"))  # tras el fallo sigue respondiendo
    assert proveedor.calls == 3
    assert "registro alfa" in proveedor.prompts[0]
    assert "registro beta" in proveedor.prompts[1]


def test_fetch_disponible_y_no_disponible() -> None:
    a, b = _rec("10.1/a", "Título A", "resumen A"), _rec("10.1/b", "Título B", "resumen B")
    ft = fetch_disponible(a)
    assert ft.available is True and "Título A" in ft.text and ft.source_url
    fetch = fetch_no_disponible(["10.1/b"])
    assert fetch(a).available is True
    no = fetch(b)
    assert (no.available, no.text) == (False, "resumen B")
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_fakes.py -v`
Expected: ERROR de colección, `ModuleNotFoundError: No module named 'fakes'`.

- [ ] **Step 3: Implementar** — crear `tests/fakes.py`:

```python
"""Dobles de prueba compartidos por las pistas de la Ola 1 (spec 2026-10-04 §4.5).

``FakeProvider`` vota siempre ``include`` (el primer valor del ``Literal``,
``fake.py:30``): con él no hay exclusiones, ni gold de dos clases, ni
``unclear`` (hallazgo 5 de la exploración de la Ola 1). ``ScriptedProvider``
etiqueta según palabras clave del prompt, puede simular un 429 en la llamada
``k`` y cuenta las llamadas, para que los tests de reanudación (A9) puedan
afirmar que nada se llama dos veces.

Los ``fetch_fn`` de prueba sustituyen la recuperación de texto completo, que
en la Ola 1 sigue PRISMA estricto (D2): sin ellos, ningún registro de prueba
tiene texto en abierto y nada llega a extracción.

Uso desde un test (``tests/`` está en ``sys.path`` porque no es un paquete)::

    from fakes import ScriptedProvider, fetch_disponible

    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline, "build_provider", lambda cfg: proveedor)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import TypeVar, get_args

from pydantic import BaseModel

from revisia.agents.fulltext import FullText
from revisia.llm.base import LLMRequest, LLMResponse
from revisia.llm.providers.fake import _fabricate_model
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningLabel

SchemaT = TypeVar("SchemaT", bound=BaseModel)

# Palabra clave (sin distinguir mayúsculas) → etiqueta. Gana la primera que
# aparezca en el prompt, en este orden; sin coincidencia, ``include``.
PALABRAS_POR_DEFECTO: dict[str, ScreeningLabel] = {
    "irrelevante": "exclude",
    "dudoso": "unclear",
}

_ETIQUETAS = frozenset({"include", "exclude", "unclear"})


class ScriptedProvider:
    """Proveedor con guion: etiqueta por palabra clave, cuenta llamadas y falla a pedido.

    Conserva ``provider="fake"`` y ``deterministic=True`` en cada ``RunMeta``,
    como ``FakeProvider``: el auditor exime de sus heurísticas temporales solo
    a ese proveedor (spec §9.3, ``timing``).

    Attributes:
        model: modelo que declara en ``RunMeta.model``.
        fail_at: número de llamada (1, 2, …) que lanza
            ``RuntimeError("429 Too Many Requests")`` en vez de responder; las
            demás responden con normalidad. ``None`` = nunca falla.
        calls: llamadas recibidas (``complete`` + ``structured``), incluida la
            que falla.
        prompts: prompt de cada llamada, en orden (para afirmar qué se cribó).
    """

    name = "fake"

    def __init__(
        self,
        model: str = "fake-guion",
        *,
        fail_at: int | None = None,
        palabras: Mapping[str, ScreeningLabel] | None = None,
        criterio_exclusion: str = "fuera de alcance",
    ) -> None:
        self.model = model
        self.fail_at = fail_at
        self.palabras: dict[str, ScreeningLabel] = dict(
            PALABRAS_POR_DEFECTO if palabras is None else palabras
        )
        self.criterio_exclusion = criterio_exclusion
        self.calls = 0
        self.prompts: list[str] = []

    def label_for(self, prompt: str) -> ScreeningLabel:
        """Etiqueta que el guion asigna a ``prompt``."""
        texto = prompt.lower()
        for palabra, etiqueta in self.palabras.items():
            if palabra.lower() in texto:
                return etiqueta
        return "include"

    def _llamar(self, req: LLMRequest) -> None:
        self.calls += 1
        self.prompts.append(req.prompt)
        if self.fail_at is not None and self.calls == self.fail_at:
            raise RuntimeError("429 Too Many Requests")

    def _meta(self, req: LLMRequest, text: str) -> RunMeta:
        return RunMeta(
            provider=self.name,
            model=self.model,
            seed=req.seed,
            temperature=req.temperature,
            top_p=req.top_p,
            prompt_sha256=sha256_text(f"{req.system or ''}\n{req.prompt}"),
            response_sha256=sha256_text(text),
            deterministic=True,
        )

    def complete(self, req: LLMRequest) -> LLMResponse:
        self._llamar(req)
        # Sin tokens "[...]": el verificador no debe confundirlos con citas.
        text = "Síntesis de prueba (proveedor con guion · sin contenido real)."
        return LLMResponse(text=text, meta=self._meta(req, text))

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        self._llamar(req)
        data = _fabricate_model(schema).model_dump()
        fields = schema.model_fields
        if "label" in fields and set(get_args(fields["label"].annotation)) >= _ETIQUETAS:
            label = self.label_for(req.prompt)
            data["label"] = label
            if "confidence" in fields:
                data["confidence"] = 0.9
            if "rationale" in fields:
                data["rationale"] = f"guion: {label}"
            if "criteria_violated" in fields:
                data["criteria_violated"] = [self.criterio_exclusion] if label == "exclude" else []
        obj = schema.model_validate(data)
        return obj, self._meta(req, obj.model_dump_json())


def fetch_disponible(record: SearchRecord) -> FullText:
    """``fetch_fn`` de prueba: todo registro tiene texto completo en abierto."""
    text = f"Texto completo de prueba de «{record.title}». {record.abstract or ''}".strip()
    return FullText(
        text=text,
        available=True,
        source_url=f"https://example.org/texto/{sha256_text(record.record_id)[:16]}",
    )


def fetch_no_disponible(ids: Iterable[str]) -> Callable[[SearchRecord], FullText]:
    """``fetch_fn`` de prueba: los ``ids`` dados no se recuperan; el resto sí.

    El ``FullText`` de un no recuperado lleva el abstract en ``text`` y
    ``available=False``, como el fallback real de
    :func:`revisia.agents.fulltext.fetch_fulltext`.
    """
    sin_texto = frozenset(ids)

    def _fetch(record: SearchRecord) -> FullText:
        if record.record_id in sin_texto:
            return FullText(text=record.abstract or "", available=False)
        return fetch_disponible(record)

    return _fetch
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_fakes.py -v`
Expected: PASS, 8 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, **364 recogidos** (pytest no recoge `tests/fakes.py`: no empieza por `test_`).

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio (si `ruff` pide reordenar imports, `uv run ruff check --fix tests/test_fakes.py` y repetir).

- [ ] **Step 6: Commit**

```bash
git add tests/fakes.py tests/test_fakes.py
git commit -m "test: dobles compartidos de la Ola 1 (ScriptedProvider y fetch_fn de prueba)" -m "ScriptedProvider etiqueta por palabra clave (irrelevante -> exclude, dudoso -> unclear), simula un 429 en la llamada k y cuenta las llamadas, con provider=fake y deterministic=True. fetch_disponible y fetch_no_disponible(ids) sustituyen la recuperación de texto completo, que en la Ola 1 es PRISMA estricto (D2). Spec 2026-10-04 §4.5." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Integración de PR-0 (controlador)

**Files:**
- Modify: `CHANGELOG.md` (bloque `## [Unreleased]`, sección `### Added`)
- Modify: `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md` (§14, filas 1-4)

**Interfaces:** ninguna de código. Deja la rama `feat/ola1-contratos` publicada y los worktrees `C:\revisia-wt\a`, `C:\revisia-wt\b` y `C:\revisia-wt\e` creados.

- [ ] **Step 1: Comprobar que los tres planes ya están commiteados en la rama** (se commitearon al escribirlos, antes de la Tarea 1).

Run: `git log --oneline main..HEAD -- docs/superpowers/plans/2026-10-04-ola-1-a-cimientos.md docs/superpowers/plans/2026-10-04-ola-1-b-reanudacion-hitl.md docs/superpowers/plans/2026-10-04-ola-1-c-auditor.md`
Expected: al menos un commit `docs(plan): …` que los añade. Si falta alguno, se escribe y se commitea antes de seguir: PR-0 los lleva (spec §4.5).

- [ ] **Step 2: CHANGELOG.** En `CHANGELOG.md`, sustituir

```
  `--effort`); pedirlo en otro proveedor es un error de config.

### Fixed
```

por

```
  `--effort`); pedirlo en otro proveedor es un error de config.
- **Contratos de artefactos de la Ola 1** (`revisia/schemas/artifacts.py`):
  modelos y constantes que comparten el pipeline y el auditor (`RunInfo`,
  `LLMCall`, `JournalEntry`, `SearchLog`, `DedupReport`, `RetrievalOutcome`,
  `ExcludedReport`, `GateSummary`, `JOURNAL_PATHS`, `GATED_STAGES`), hashes
  canónicos (`canonical_json`/`canonical_sha256`), el reductor único del ledger
  (`summarize_gates`) y `KNOWN_THRESHOLDS`. `ScreeningDecision` y `PrismaCounts`
  ganan campos opcionales, sin cambio de comportamiento. Diseño en
  `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md`.

### Fixed
```

- [ ] **Step 3: Desviaciones en el spec.** La tabla de §14 del spec está vacía (termina en `| # | Dónde | Cambio | Origen |` y `|---|---|---|---|`). Añadir debajo de esa línea separadora:

```
| 1 | §4.5 `artifacts.py` | Además de los nombres de §4.5: `RunInterruption`, `DedupDuplicate` y `DedupRename` (tipan las listas que §4.3 describe como `{…}`), los alias `SearchEntryKind`, `SearchEntryStatus`, `QueryOrigin`, `ReasonSource` y `GateAction`, y `LLMCall.from_meta(meta, *, stage, record_id=None, role=None)` | Plan PR-0 |
| 2 | §4.5 `GateSummary` | Campos: `stage`, `action`, `actor`, `autonomy`, `request_sha256`, `decision_sha256`, `n_labels`, `n_flag_reviews`, `forced_human`, `timestamp_utc`. `n_labels` y `n_flag_reviews` se cuentan en el ledger (misma etapa y mismo `decision_sha256`), no se leen del `detail`, para que el auditor pueda contrastarlos | Plan PR-0 |
| 3 | §4.5 `ledger.py` | `GATE_DECISION_ACTIONS = {approve, reject, auto-proceed}` además de `LEDGER_ACTIONS`; ambas `frozenset` | Plan PR-0 |
| 4 | §4.5 `tests/fakes.py` | `ScriptedProvider` registra además `prompts` y admite `palabras` y `criterio_exclusion`; `fail_at` cuenta desde 1 y solo falla esa llamada | Plan PR-0 |
```

- [ ] **Step 4: Commit de documentación.**

```bash
git add CHANGELOG.md docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md
git commit -m "docs: CHANGELOG y desviaciones de PR-0 (contratos de la Ola 1)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Verificación completa.**

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 364 recogidos.

Run (3.11 y 3.12 con venv desechable; `requires-python >= 3.13` impide `uv run --python 3.11`, M24 es Ola 2):

```bash
TMP="$(mktemp -d)"
for PY in 3.11 3.12; do
  uv venv -q --python "$PY" "$TMP/venv$PY"
  uv pip install -q --python "$TMP/venv$PY" pydantic pyyaml python-dotenv markdown httpx nh3 pytest
  PYTHONPATH=. "$TMP/venv$PY/Scripts/python" -m pytest -p no:cacheprovider -q
done
```

Expected: PASS en ambas versiones.

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`
Expected: limpio.

- [ ] **Step 6: Publicar la rama y abrir PR-0** (sin merge).

```bash
git push -u origin feat/ola1-contratos
gh pr create --base main --head feat/ola1-contratos --title "Ola 1 · PR-0: spec, planes y contratos de artefactos" --body "$(cat <<'EOF'
## Qué es

Primera PR de la Ola 1 del plan de remediación (auditoría 2026-09-03, §8). Trae el diseño, los tres planes de implementación y el **contrato de artefactos** que comparten la pista del pipeline (PR-A a PR-D) y la del auditor (PR-E). No cambia el comportamiento del motor.

## Qué cambia

- `revisia/schemas/artifacts.py`: modelos y constantes de §4.3 y §4.5 del spec.
- `revisia/provenance/runmeta.py`: `canonical_json`, `canonical_sha256`.
- `revisia/provenance/ledger.py`: `LEDGER_ACTIONS`, `GATE_DECISION_ACTIONS`, `HUMAN_ACTOR_PREFIX`, `AUTO_APPROVE_ACTOR`, `summarize_gates`.
- `revisia/config.py`: `KNOWN_THRESHOLDS`.
- Campos opcionales en `ScreeningDecision` y `PrismaCounts`.
- `tests/fakes.py`: `ScriptedProvider`, `fetch_disponible`, `fetch_no_disponible`.
- Spec `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md` y planes `docs/superpowers/plans/2026-10-04-ola-1-*.md`.

## Verificación

- `uv run pytest -p no:cacheprovider`: 364 recogidos, en verde (base: 330).
- La misma suite en 3.11 y 3.12 con venv desechable: en verde.
- `ruff check`, `ruff format --check`, `black --check`, `uv lock --check`: limpios.

## Pila

`main` ← **PR-0** ← PR-A ← PR-B ← PR-C ← PR-D ← PR-E. Al mergear, no borrar la rama mientras otra PR la use como base: merge sin borrar → `gh pr edit <n> --base main` en la siguiente → borrar la rama → cerrar y reabrir la siguiente para que corra el CI.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR.

- [ ] **Step 7: Worktrees de la fase 1.**

```bash
git worktree add C:/revisia-wt/a -b feat/ola1-preflight feat/ola1-contratos
git worktree add C:/revisia-wt/b -b feat/ola1-flujo-prisma feat/ola1-contratos
git worktree add C:/revisia-wt/e -b feat/ola1-auditor feat/ola1-contratos
for WT in a b e; do (cd "C:/revisia-wt/$WT" && uv sync --extra dev && uv run pytest -p no:cacheprovider -q); done
```

Expected: tres worktrees, cada uno con 364 tests en verde. A partir de aquí, las pistas A, B y E (fase 1) corren en paralelo. (El worktree de E lo usa el plan `2026-10-04-ola-1-c-auditor.md`; si ese plan ya lo creó, se omite su línea.)

---

## Pista A · PR-A `feat/ola1-preflight` (worktree `C:\revisia-wt\a`)

Todas las tareas de esta pista se ejecutan en `C:\revisia-wt\a`, rama `feat/ola1-preflight` (creada en la Tarea 5, Step 7).

### Task 6: Preflight de proveedores, etapas y modelos (`revisia/llm/preflight.py`)

**Files:**
- Create: `revisia/llm/preflight.py`
- Test: `tests/test_preflight.py` (nuevo)

**Interfaces:**
- Consumes: `ReviewProtocol.screeners_for(stage) -> list[ProviderConfig]` y `ReviewProtocol.provider_for(stage) -> ProviderConfig` (lanzan `KeyError` sin proveedor ni `default`); `ProviderConfig` (`provider`, `model`, `effort`); `revisia.llm.registry.available_providers() -> list[str]`, `revisia.llm.registry._EFFORT_PROVIDERS: frozenset[str]` (fuente única de qué proveedores aceptan `effort`); `revisia.llm.registry._BUILDERS` (solo en el test); `revisia.llm.deprecations.retirement_for(model) -> Retirement | None`; `revisia.llm.providers.agent.get_agent_callback()` y `use_agent_callback(cb)` (test).
- Produces (firmas exactas; PR-C las usa en `run_pipeline` y en el CLI):
  - `PreflightContext = Literal["validate", "run", "resume"]`
  - `FindSpec = Callable[[str], object | None]`; `Which = Callable[[str], str | None]`
  - `@dataclass(frozen=True, slots=True) class Requirement`: `sdk_module: str | None`, `extra: str | None`, `env_var: str | None`, `binary: str | None`, `runtime_callback: bool = False`
  - `PROVIDER_REQUIREMENTS: dict[str, Requirement]` (claves == `available_providers()`)
  - `@dataclass(frozen=True, slots=True) class PreflightIssue`: `level: Literal["error", "warning"]`, `where: str`, `message: str`
  - `@dataclass(frozen=True, slots=True) class PreflightReport`: `issues: tuple[PreflightIssue, ...]`; propiedades `errors -> tuple[PreflightIssue, ...]`, `warnings -> tuple[PreflightIssue, ...]`, `ok -> bool`
  - `class PreflightError(ValueError)`: `__init__(self, report: PreflightReport)`; atributo `report`
  - `stages_in_use(protocol: ReviewProtocol) -> list[tuple[str, ProviderConfig]]` (`where` ∈ `screening_ta` o `screening_ta[i]` si hay ensemble, `screening_ft`, `extraccion`, `extraccion_2`, `rob`, `sintesis` o `sintesis (y juez de grounding)`; omite las etapas sin proveedor)
  - `check_provider(cfg: ProviderConfig, *, where: str, context: PreflightContext, env: Mapping[str, str], find_spec: FindSpec, which: Which) -> list[PreflightIssue]`
  - `check_retired(protocol: ReviewProtocol, today: date) -> list[PreflightIssue]` (absorbe `cli._retired_model_problems`, `cli.py:66-89`; mismos textos)
  - `preflight(protocol: ReviewProtocol, protocol_dir: str | Path, *, context: PreflightContext, mailto: str | None = None, env: Mapping[str, str] | None = None, find_spec: FindSpec | None = None, which: Which | None = None, today: date | None = None) -> PreflightReport`
  - Puntos de inyección de módulo para los tests del CLI: `_default_find_spec: FindSpec = importlib.util.find_spec`, `_default_which: Which = shutil.which` (`preflight` los lee en cada llamada).
  - La Tarea 7 añade `check_databases(...)` y la parte de bases y `mailto` de `preflight`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_preflight.py`:

```python
"""Preflight sin red de una corrida (auditoría 2026-09-03, M6; spec 2026-10-04 §5).

Todos con ``env``, ``find_spec`` y ``which`` falsos: no dependen del venv.
"""

from __future__ import annotations

import importlib
import inspect
import tomllib
from datetime import date
from pathlib import Path

import pytest

from revisia.config import ReviewProtocol
from revisia.llm.preflight import (
    PROVIDER_REQUIREMENTS,
    PreflightError,
    PreflightIssue,
    PreflightReport,
    check_retired,
    preflight,
    stages_in_use,
)
from revisia.llm.providers.agent import use_agent_callback
from revisia.llm.registry import _BUILDERS, available_providers

ROOT = Path(__file__).resolve().parent.parent
HOY = date(2026, 10, 4)


def _todo_instalado(_name: str) -> object:
    return object()


def _con_claude(_name: str) -> str:
    return "/usr/local/bin/claude"


def _sin_binario(_name: str) -> None:
    return None


def _proto(**overrides) -> ReviewProtocol:
    raw = {
        "slug": "demo",
        "title": "Demo",
        "question": {"text": "¿X afecta Y?", "framework": "PEO", "components": {"P": "x"}},
        "databases": ["OpenAlex"],
        "llm": {"default": {"provider": "fake", "model": "fake-1"}},
    }
    raw.update(overrides)
    return ReviewProtocol.model_validate(raw)


@pytest.fixture()
def proto_dir(tmp_path: Path) -> Path:
    (tmp_path / "search_strings").mkdir()
    (tmp_path / "search_strings" / "openalex.txt").write_text("llm AND screening", "utf-8")
    return tmp_path


def _run(protocol: ReviewProtocol, proto_dir: Path, **kwargs) -> PreflightReport:
    kwargs.setdefault("context", "validate")
    kwargs.setdefault("env", {})
    kwargs.setdefault("find_spec", _todo_instalado)
    kwargs.setdefault("which", _con_claude)
    kwargs.setdefault("today", HOY)
    return preflight(protocol, proto_dir, **kwargs)


def _messages(issues: tuple[PreflightIssue, ...]) -> str:
    return "\n".join(f"[{i.where}] {i.message}" for i in issues)


# ── Deriva entre la tabla y el código ───────────────────────────────────


def test_preflight_cubre_todos_los_proveedores_del_registro() -> None:
    assert set(PROVIDER_REQUIREMENTS) == set(available_providers())
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = pyproject["project"]["optional-dependencies"]
    for name, req in PROVIDER_REQUIREMENTS.items():
        if req.extra is not None:
            assert req.extra in extras, f"{name}: extra {req.extra!r} inexistente"


def test_preflight_env_key_coincide_con_la_del_proveedor() -> None:
    for name, req in PROVIDER_REQUIREMENTS.items():
        module_path, class_name = _BUILDERS[name]
        cls = getattr(importlib.import_module(module_path), class_name)
        if name == "gemini":
            # GeminiProvider no tiene `env_key`: lee el literal (gemini.py:43).
            assert f'os.environ.get("{req.env_var}")' in inspect.getsource(cls)
        elif req.env_var is not None:
            assert cls.env_key == req.env_var, name
    # local_openai tiene env_key, pero su key es opcional: no se exige.
    assert PROVIDER_REQUIREMENTS["local_openai"].env_var is None


# ── Proveedores ──────────────────────────────────────────────────────────


def test_preflight_sdk_ausente_es_error_con_extra_sugerido(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "openai", "model": "gpt-5"}})
    report = _run(
        protocol,
        proto_dir,
        env={"OPENAI_API_KEY": "sk-x"},
        find_spec=lambda name: None if name == "openai" else object(),
    )
    assert not report.ok
    assert "uv sync --extra openai" in _messages(report.errors)


def test_preflight_paquete_padre_ausente_no_revienta(proto_dir: Path) -> None:
    def find_spec(name: str) -> object:
        if name == "google.genai":
            raise ModuleNotFoundError("No module named 'google'")
        return object()

    protocol = _proto(llm={"default": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}})
    report = _run(protocol, proto_dir, env={"GEMINI_API_KEY": "k"}, find_spec=find_spec)
    assert "uv sync --extra gemini" in _messages(report.errors)


def test_preflight_key_ausente_es_error(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "gemini", "model": "gemini-3.5-flash-lite"}})
    sin_key = _run(protocol, proto_dir, env={"GEMINI_API_KEY": ""})
    errores = [i for i in sin_key.errors if "GEMINI_API_KEY" in i.message]
    # Mismo proveedor en las cinco etapas: un solo error que las nombra todas.
    assert len(errores) == 1
    assert "screening_ft" in errores[0].where and "sintesis" in errores[0].where
    assert _run(protocol, proto_dir, env={"GEMINI_API_KEY": "k"}).ok


def test_preflight_local_openai_no_exige_key(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "local_openai", "model": "llama3.1:8b"}})
    assert _run(protocol, proto_dir, env={}).ok


def test_preflight_claude_code_sin_binario_es_error(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "claude_code", "model": "sonnet"}})
    report = _run(protocol, proto_dir, which=_sin_binario)
    assert "'claude'" in _messages(report.errors)
    assert _run(protocol, proto_dir, which=_con_claude).ok


def test_preflight_agent_sin_callback_error_en_run_aviso_en_validate(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "agent", "model": "session-agent"}})
    en_validate = _run(protocol, proto_dir, context="validate")
    assert en_validate.ok
    assert "callback" in _messages(en_validate.warnings)
    for context in ("run", "resume"):
        report = _run(protocol, proto_dir, context=context, mailto="x@y.z")
        assert "callback" in _messages(report.errors), context
    with use_agent_callback(lambda _req, _schema: {}):
        assert _run(protocol, proto_dir, context="run", mailto="x@y.z").ok


def test_preflight_effort_fuera_de_claude_code_es_error(proto_dir: Path) -> None:
    protocol = _proto(
        llm={"default": {"provider": "gemini", "model": "gemini-3.5-flash-lite", "effort": "high"}}
    )
    report = _run(protocol, proto_dir, env={"GEMINI_API_KEY": "k"})
    assert "effort='high'" in _messages(report.errors)


def test_preflight_proveedor_desconocido_es_error(proto_dir: Path) -> None:
    protocol = _proto(llm={"default": {"provider": "gemni", "model": "x"}})
    report = _run(protocol, proto_dir)
    assert "proveedor desconocido 'gemni'" in _messages(report.errors)
    exc = PreflightError(report)
    assert exc.report is report
    assert "gemni" in str(exc)


def test_preflight_etapa_sin_proveedor_ni_default_es_error(proto_dir: Path) -> None:
    # M6: hoy un FT sin proveedor se descubre tras gastar el cribado T/A.
    protocol = _proto(llm={"screening_ta": {"provider": "fake", "model": "fake-1"}})
    report = _run(protocol, proto_dir)
    wheres = {i.where for i in report.errors}
    assert {"screening_ft", "extraccion", "rob", "sintesis"} <= wheres
    assert "screening_ta" not in wheres
    assert [w for w, _ in stages_in_use(protocol)] == ["screening_ta"]


def test_preflight_revisa_ensemble_y_segundo_extractor(proto_dir: Path) -> None:
    protocol = _proto(
        ensemble=["screening_ta"],
        ensemble_llm={
            "screening_ta": [
                {"provider": "fake", "model": "fake-a"},
                {"provider": "openai", "model": "gpt-5"},
            ],
            "extraccion": [
                {"provider": "anthropic", "model": "claude-x"},
                {"provider": "gemini", "model": "gemini-3.5-flash-lite"},
            ],
        },
    )
    report = _run(protocol, proto_dir, env={})
    errores = _messages(report.errors)
    assert "[screening_ta[1]]" in errores and "OPENAI_API_KEY" in errores
    assert "[extraccion_2]" in errores and "ANTHROPIC_API_KEY" in errores
    assert "GEMINI_API_KEY" not in errores  # el 2.º miembro de extracción no se usa
    assert "solo se usa el primero" in _messages(report.warnings)


def test_preflight_modelo_retirado_es_error_y_futuro_aviso() -> None:
    retirado = _proto(llm={"default": {"provider": "fake", "model": "gemini-2.0-flash"}})
    assert check_retired(retirado, HOY)[0].level == "error"
    futuro = _proto(llm={"default": {"provider": "fake", "model": "gemini-3.1-flash-lite"}})
    aviso = check_retired(futuro, HOY)
    assert aviso[0].level == "warning" and "2027-05-07" in aviso[0].message
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_preflight.py -v`
Expected: ERROR de colección, `ModuleNotFoundError: No module named 'revisia.llm.preflight'`.

- [ ] **Step 3: Implementar** — crear `revisia/llm/preflight.py`:

```python
"""Preflight sin red: lo que haría fallar una corrida, detectado antes de empezar.

Hasta la Ola 1, los proveedores se construían al entrar en cada etapa: una API
key ausente para el cribado a texto completo se descubría después de gastar el
cribado de título/abstract, y ``revisia validate`` devolvía 0 con "(sin
proveedor)" (auditoría 2026-09-03, M6). Este módulo revisa, sin tocar la red ni
importar ningún SDK, todo lo que el pipeline va a necesitar: proveedor conocido,
SDK instalado, key en el entorno, binario ``claude``, ``effort`` solo en
``claude_code``, etapas sin proveedor, bases desconocidas, modelos retirados y
``httpx`` (D10).

``env``, ``find_spec`` y ``which`` son inyectables: los tests no dependen de lo
que tenga instalado el venv. ``context`` decide tres cosas: el callback de
``agent`` solo existe en tiempo de corrida (``run``/``resume``: error si falta;
``validate``: aviso); el aviso de ``mailto`` solo tiene sentido en ``run``; en
``resume`` la búsqueda está congelada y se saltan bases y búsqueda.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from revisia.llm.deprecations import retirement_for
from revisia.llm.providers.agent import get_agent_callback
from revisia.llm.registry import _EFFORT_PROVIDERS, available_providers

if TYPE_CHECKING:
    from revisia.config import ReviewProtocol
    from revisia.llm.registry import ProviderConfig

PreflightContext = Literal["validate", "run", "resume"]
FindSpec = Callable[[str], object | None]
Which = Callable[[str], str | None]

# Puntos de inyección por defecto. Los tests de este módulo pasan `env`,
# `find_spec` y `which` explícitos; los del CLI sustituyen estos con monkeypatch.
_default_find_spec: FindSpec = importlib.util.find_spec
_default_which: Which = shutil.which


@dataclass(frozen=True, slots=True)
class Requirement:
    """Lo que necesita un proveedor para funcionar en esta máquina.

    Attributes:
        sdk_module: módulo importable del SDK (``None`` si no usa ninguno).
        extra: extra de ``pyproject.toml`` que lo instala.
        env_var: variable de entorno con la API key (``None`` si no se exige).
        binary: ejecutable que debe estar en el ``PATH``.
        runtime_callback: necesita un callback registrado en tiempo de corrida.
    """

    sdk_module: str | None
    extra: str | None
    env_var: str | None
    binary: str | None
    runtime_callback: bool = False


# Verificado contra `revisia/llm/providers/*.py` y los extras de pyproject.toml.
# Dos tests impiden la deriva: claves == available_providers() y env_var == la
# variable que lee cada clase.
PROVIDER_REQUIREMENTS: dict[str, Requirement] = {
    "gemini": Requirement("google.genai", "gemini", "GEMINI_API_KEY", None),
    "openai": Requirement("openai", "openai", "OPENAI_API_KEY", None),
    "anthropic": Requirement("anthropic", "anthropic", "ANTHROPIC_API_KEY", None),
    # Endpoint local (Ollama/vLLM/LM Studio): la key es opcional.
    "local_openai": Requirement("openai", "local", None, None),
    "zai": Requirement("openai", "zai", "ZAI_API_KEY", None),
    "openrouter": Requirement("openai", "openrouter", "OPENROUTER_API_KEY", None),
    "claude_code": Requirement(None, None, None, "claude"),
    "agent": Requirement(None, None, None, None, runtime_callback=True),
    "fake": Requirement(None, None, None, None),
}


@dataclass(frozen=True, slots=True)
class PreflightIssue:
    """Un problema detectado: ``where`` dice en qué parte del protocolo."""

    level: Literal["error", "warning"]
    where: str
    message: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    """Resultado del preflight. ``ok`` es ``True`` si no hay errores."""

    issues: tuple[PreflightIssue, ...]

    @property
    def errors(self) -> tuple[PreflightIssue, ...]:
        return tuple(i for i in self.issues if i.level == "error")

    @property
    def warnings(self) -> tuple[PreflightIssue, ...]:
        return tuple(i for i in self.issues if i.level == "warning")

    @property
    def ok(self) -> bool:
        return not self.errors


class PreflightError(ValueError):
    """El preflight encontró errores: la corrida no debe arrancar (rc 2 en el CLI)."""

    def __init__(self, report: PreflightReport) -> None:
        self.report = report
        detalle = "; ".join(f"[{i.where}] {i.message}" for i in report.errors)
        super().__init__(f"preflight con {len(report.errors)} error(es): {detalle}")


def _error(where: str, message: str) -> PreflightIssue:
    return PreflightIssue("error", where, message)


def _warning(where: str, message: str) -> PreflightIssue:
    return PreflightIssue("warning", where, message)


def _importable(module: str, find_spec: FindSpec) -> bool:
    """``find_spec`` envuelto: ``find_spec("google.genai")`` LANZA si falta ``google``."""
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _resolve(protocol: ReviewProtocol, stage: str) -> ProviderConfig | None:
    """Proveedor de una etapa, o ``None`` si no tiene ni hay ``default``."""
    try:
        return protocol.provider_for(stage)
    except KeyError:
        return None


def stages_in_use(protocol: ReviewProtocol) -> list[tuple[str, ProviderConfig]]:
    """Proveedores que el pipeline usará de verdad, con la etapa que los usa.

    Miembros de T/A (``screeners_for``), FT, extracción, el primer miembro de
    ``ensemble_llm["extraccion"]`` (2.º extractor), RoB y síntesis (que también
    hace de juez con ``grounding: agent``). Una etapa sin proveedor ni
    ``default`` no aparece: la señala :func:`preflight` como error.
    """
    try:
        members = protocol.screeners_for("screening_ta")
    except KeyError:
        members = []
    used = [
        (f"screening_ta[{i}]" if len(members) > 1 else "screening_ta", cfg)
        for i, cfg in enumerate(members)
    ]
    candidates: list[tuple[str, ProviderConfig | None]] = [
        ("screening_ft", _resolve(protocol, "screening_ft")),
        ("extraccion", _resolve(protocol, "extraccion")),
        ("extraccion_2", next(iter(protocol.ensemble_llm.get("extraccion", [])), None)),
        ("rob", _resolve(protocol, "rob")),
        (
            "sintesis (y juez de grounding)" if protocol.grounding == "agent" else "sintesis",
            _resolve(protocol, "sintesis"),
        ),
    ]
    used += [(where, cfg) for where, cfg in candidates if cfg is not None]
    return used


def _stage_issues(protocol: ReviewProtocol) -> list[PreflightIssue]:
    """Etapas con LLM sin proveedor ni ``default``, y 2.º extractor ambiguo."""
    issues: list[PreflightIssue] = []
    for stage in ("screening_ta", "screening_ft", "extraccion", "rob", "sintesis"):
        try:
            if stage == "screening_ta":
                protocol.screeners_for(stage)
            else:
                protocol.provider_for(stage)
        except KeyError:
            issues.append(
                _error(
                    stage,
                    f"la etapa {stage!r} no tiene proveedor LLM ni hay un 'default' en el "
                    f"bloque llm de protocol.yml: añade llm.{stage} o llm.default.",
                )
            )
    extractores = protocol.ensemble_llm.get("extraccion", [])
    if len(extractores) > 1:
        issues.append(
            _warning(
                "extraccion_2",
                f"ensemble_llm.extraccion declara {len(extractores)} modelos, pero solo se "
                "usa el primero como 2.º extractor.",
            )
        )
    return issues


def check_provider(
    cfg: ProviderConfig,
    *,
    where: str,
    context: PreflightContext,
    env: Mapping[str, str],
    find_spec: FindSpec,
    which: Which,
) -> list[PreflightIssue]:
    """Comprueba que el proveedor de ``cfg`` puede funcionar en esta máquina."""
    req = PROVIDER_REQUIREMENTS.get(cfg.provider)
    if req is None:
        return [
            _error(
                where,
                f"proveedor desconocido {cfg.provider!r}. "
                f"Disponibles: {', '.join(available_providers())}.",
            )
        ]
    issues: list[PreflightIssue] = []
    if cfg.effort is not None and cfg.provider not in _EFFORT_PROVIDERS:
        issues.append(
            _error(
                where,
                f"effort={cfg.effort!r} no aplica al proveedor {cfg.provider!r}; solo lo "
                f"aceptan: {', '.join(sorted(_EFFORT_PROVIDERS))}.",
            )
        )
    if req.sdk_module is not None and not _importable(req.sdk_module, find_spec):
        issues.append(
            _error(
                where,
                f"el proveedor {cfg.provider!r} necesita el paquete {req.sdk_module!r}, que "
                f"no está instalado: `uv sync --extra {req.extra}`.",
            )
        )
    if req.env_var is not None and not env.get(req.env_var):
        issues.append(
            _error(
                where,
                f"falta la variable de entorno {req.env_var} (API key de {cfg.provider!r}): "
                "ponla en .env (ver .env.example) o en el entorno.",
            )
        )
    if req.binary is not None and which(req.binary) is None:
        issues.append(
            _error(
                where,
                f"no se encontró el ejecutable {req.binary!r} de Claude Code en el PATH: "
                "instálalo e inicia sesión antes de correr.",
            )
        )
    if req.runtime_callback and get_agent_callback() is None:
        if context == "validate":
            issues.append(
                _warning(
                    where,
                    "el proveedor 'agent' solo funciona con un callback registrado en "
                    "tiempo de corrida (revisia conducido desde un agente); `revisia run` "
                    "desde la terminal fallará.",
                )
            )
        else:
            issues.append(
                _error(
                    where,
                    "el proveedor 'agent' no tiene callback registrado "
                    "(set_agent_callback/use_agent_callback): en una corrida desatendida "
                    "no hay agente a quien preguntar; elige otro proveedor.",
                )
            )
    return issues


def _configured_models(protocol: ReviewProtocol) -> list[str]:
    """Ids de modelo de todas las etapas y miembros de ensemble del protocolo."""
    models = {cfg.model for cfg in protocol.llm.values()}
    models |= {cfg.model for members in protocol.ensemble_llm.values() for cfg in members}
    return sorted(models)


def check_retired(protocol: ReviewProtocol, today: date) -> list[PreflightIssue]:
    """Modelos retirados por su proveedor (auditoría 2026-09-03, C4).

    Absorbe ``cli._retired_model_problems``: un modelo ya apagado es un error;
    uno con retiro anunciado, un aviso.
    """
    issues: list[PreflightIssue] = []
    for model in _configured_models(protocol):
        retirement = retirement_for(model)
        if retirement is None:
            continue
        fecha = retirement.shutdown.isoformat()
        if retirement.is_past(today):
            issues.append(
                _error(
                    "llm",
                    f"el modelo {model!r} fue retirado por su proveedor el {fecha}; "
                    "las llamadas fallarán. Cámbialo en protocol.yml.",
                )
            )
        else:
            issues.append(
                _warning("llm", f"el modelo {model!r} se retira el {fecha}; planifica el cambio.")
            )
    return issues


def _merge(issues: list[PreflightIssue]) -> tuple[PreflightIssue, ...]:
    """Une los problemas idénticos de varias etapas en uno (``where`` combinado).

    Con el mismo proveedor en cinco etapas, "falta GEMINI_API_KEY" sale una vez.
    """
    merged: dict[tuple[Literal["error", "warning"], str], list[str]] = {}
    for issue in issues:
        wheres = merged.setdefault((issue.level, issue.message), [])
        if issue.where not in wheres:
            wheres.append(issue.where)
    return tuple(
        PreflightIssue(level, ", ".join(wheres), message)
        for (level, message), wheres in merged.items()
    )


def preflight(
    protocol: ReviewProtocol,
    protocol_dir: str | Path,
    *,
    context: PreflightContext,
    mailto: str | None = None,
    env: Mapping[str, str] | None = None,
    find_spec: FindSpec | None = None,
    which: Which | None = None,
    today: date | None = None,
) -> PreflightReport:
    """Revisa, sin red, todo lo que la corrida va a necesitar (M6, D10).

    Args:
        context: ``"validate"``, ``"run"`` o ``"resume"`` (ver docstring del módulo).
        mailto: correo de ``--mailto``; sin él, ``run`` avisa.
        env: entorno a revisar (``os.environ`` por defecto).
        find_spec: como ``importlib.util.find_spec`` (puede lanzar).
        which: como ``shutil.which``.
        today: fecha para los modelos retirados (hoy por defecto).
    """
    env = os.environ if env is None else env
    find_spec = _default_find_spec if find_spec is None else find_spec
    which = _default_which if which is None else which
    today = date.today() if today is None else today

    issues = _stage_issues(protocol)
    for where, cfg in stages_in_use(protocol):
        issues += check_provider(
            cfg, where=where, context=context, env=env, find_spec=find_spec, which=which
        )
    issues += check_retired(protocol, today)
    return PreflightReport(_merge(issues))
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_preflight.py -v`
Expected: PASS, 13 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 377 recogidos (el CLI aún no usa el módulo).

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/llm/preflight.py tests/test_preflight.py
git commit -m "feat(llm): preflight sin red de proveedores, etapas y modelos retirados (M6)" -m "revisia/llm/preflight.py comprueba, sin red ni SDK: proveedor conocido, SDK importable (find_spec envuelto: google.genai lanza si falta google), API key en el entorno, binario claude, effort solo en claude_code, callback de agent (error en run/resume, aviso en validate), etapas sin proveedor ni default y modelos retirados (absorbe cli._retired_model_problems). PROVIDER_REQUIREMENTS con dos tests contra la deriva. Auditoría 2026-09-03, M6; D10." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Preflight de bases, búsqueda y `mailto`; bases de suscripción manuales

**Files:**
- Modify: `revisia/llm/preflight.py` (import de `search_backends`; constante `_IMPORT_SUFFIXES`; función nueva `check_databases` antes de `_configured_models`; final de `preflight`)
- Modify: `revisia/agents/search_backends.py` (comentario y conjunto `MANUAL_ONLY`, l.204-223)
- Test: `tests/test_preflight.py` (añadir al final)

**Interfaces:**
- Consumes: todo lo de la Tarea 6; `search_backends.db_key(db) -> str`, `search_backends.BACKENDS: dict[str, SearchFn]`, `search_backends.MANUAL_ONLY: set[str]`.
- Produces:
  - `check_databases(protocol: ReviewProtocol, protocol_dir: str | Path, *, find_spec: FindSpec) -> list[PreflightIssue]`: error por base desconocida (ni en `BACKENDS` ni en `MANUAL_ONLY`) y por `httpx` ausente con alguna base con backend (incluido el OpenAlex por defecto); aviso por base con backend sin `search_strings/<key>.txt` o con el fichero vacío, por base manual sin ficheros `.ris/.bib/.bibtex` en `imported/`, por `databases: []` y por `httpx` ausente con solo bases manuales.
  - `preflight(...)`: si `context != "resume"`, añade `check_databases`; si `context == "run"` y no hay `mailto`, aviso con `where="mailto"`.
  - `MANUAL_ONLY` gana `cinahl`, `cochrane`, `cochranelibrary`, `central`, `proquest`, `econlit`, `jstor`, `ieeexplore`, `acm`, `sciencedirect`, `ebsco`, `ovid`.

- [ ] **Step 1: Tests que fallan** — añadir al final de `tests/test_preflight.py`:

```python


# ── Bases y búsqueda ─────────────────────────────────────────────────────


def _sin_httpx(name: str) -> object | None:
    return None if name == "httpx" else object()


def test_preflight_base_desconocida_es_error(proto_dir: Path) -> None:
    report = _run(_proto(databases=["OpenAlex", "Scopuss"]), proto_dir)
    assert "base desconocida 'Scopuss'" in _messages(report.errors)


@pytest.mark.parametrize(
    "db",
    [
        "CINAHL",
        "Cochrane",
        "Cochrane Library",
        "CENTRAL",
        "ProQuest",
        "EconLit",
        "JSTOR",
        "IEEE Xplore",
        "ACM",
        "ScienceDirect",
        "EBSCO",
        "Ovid",
    ],
)
def test_preflight_bases_de_suscripcion_son_manuales(proto_dir: Path, db: str) -> None:
    report = _run(_proto(databases=["OpenAlex", db]), proto_dir)
    assert report.ok, _messages(report.errors)


def test_preflight_manual_sin_imported_avisa(proto_dir: Path) -> None:
    protocol = _proto(databases=["OpenAlex", "Scopus"])
    assert "imported/" in _messages(_run(protocol, proto_dir).warnings)
    (proto_dir / "imported").mkdir()
    (proto_dir / "imported" / "scopus.ris").write_text("TY  - JOUR\nER  -\n", "utf-8")
    assert "imported/" not in _messages(_run(protocol, proto_dir).warnings)


def test_preflight_backend_sin_cadena_avisa(proto_dir: Path) -> None:
    (proto_dir / "search_strings" / "europepmc.txt").write_text("   \n", "utf-8")
    protocol = _proto(databases=["OpenAlex", "Crossref", "Europe PMC"])
    avisos = _messages(_run(protocol, proto_dir).warnings)
    assert "search_strings/crossref.txt" in avisos
    assert "search_strings/europepmc.txt" in avisos  # vacío cuenta como ausente
    assert "search_strings/openalex.txt" not in avisos


def test_preflight_databases_vacio_avisa_openalex(proto_dir: Path) -> None:
    avisos = _messages(_run(_proto(databases=[]), proto_dir).warnings)
    assert "OpenAlex" in avisos


def test_preflight_httpx_ausente_es_error_con_bases_con_backend(proto_dir: Path) -> None:
    report = _run(_proto(databases=["OpenAlex"]), proto_dir, find_spec=_sin_httpx)
    assert "uv sync --extra search" in _messages(report.errors)
    # Solo bases manuales: no hay búsqueda programática, pero todo quedará como
    # no recuperado → aviso, no error.
    (proto_dir / "imported").mkdir()
    (proto_dir / "imported" / "wos.ris").write_text("TY  - JOUR\nER  -\n", "utf-8")
    solo_manual = _run(_proto(databases=["Web of Science"]), proto_dir, find_spec=_sin_httpx)
    assert solo_manual.ok
    assert "no recuperados" in _messages(solo_manual.warnings)


def test_preflight_sin_mailto_avisa(proto_dir: Path) -> None:
    assert "--mailto" in _messages(_run(_proto(), proto_dir, context="run").warnings)
    assert "--mailto" not in _messages(
        _run(_proto(), proto_dir, context="run", mailto="x@y.z").warnings
    )
    assert "--mailto" not in _messages(_run(_proto(), proto_dir, context="validate").warnings)


def test_preflight_resume_salta_bases_y_busqueda(proto_dir: Path) -> None:
    # Al reanudar, la búsqueda está congelada en 01_search/: ni bases ni httpx.
    report = _run(_proto(databases=["Scopuss"]), proto_dir, context="resume", find_spec=_sin_httpx)
    assert report.ok
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_preflight.py -v`
Expected: FAIL (`AssertionError`: el texto esperado no está en el informe) `test_preflight_base_desconocida_es_error`, `test_preflight_manual_sin_imported_avisa`, `test_preflight_backend_sin_cadena_avisa`, `test_preflight_databases_vacio_avisa_openalex`, `test_preflight_httpx_ausente_es_error_con_bases_con_backend` y `test_preflight_sin_mailto_avisa`. Pasan ya, porque todavía nadie mira las bases: los 12 casos de `test_preflight_bases_de_suscripcion_son_manuales` (fallarían si se implementara `check_databases` sin ampliar `MANUAL_ONLY`; por eso el Step 3 va primero) y `test_preflight_resume_salta_bases_y_busqueda` (documenta el contrato de `resume`). Los 13 de la Tarea 6 siguen en verde.

- [ ] **Step 3: `MANUAL_ONLY`** en `revisia/agents/search_backends.py`. Sustituir el comentario y el conjunto

```python
# Bases sin API abierta de búsqueda: se ingestan por importación manual (RIS/BibTeX).
# Redalyc/Dialnet/SciELO solo ofrecen cosecha OAI-PMH (sin texto libre); Google
# Scholar no tiene API; Mendeley/DynaMed/Lens exigen credenciales por usuario;
# PEDro solo HTML.
MANUAL_ONLY = {
```

por

```python
# Bases sin API abierta de búsqueda: se ingestan por importación manual (RIS/BibTeX).
# Redalyc/Dialnet/SciELO solo ofrecen cosecha OAI-PMH (sin texto libre); Google
# Scholar no tiene API; Mendeley/DynaMed/Lens exigen credenciales por usuario;
# PEDro solo HTML. Las de suscripción (CINAHL, Cochrane/CENTRAL, ProQuest, EconLit,
# JSTOR, IEEE Xplore, ACM, ScienceDirect, EBSCO, Ovid) también: sin ellas aquí, el
# preflight las daría por "base desconocida" (auditoría 2026-09-03, M6; D10).
MANUAL_ONLY = {
```

y, dentro del conjunto, tras `"pedro",` añadir:

```python
    "cinahl",
    "cochrane",
    "cochranelibrary",
    "central",
    "proquest",
    "econlit",
    "jstor",
    "ieeexplore",
    "acm",
    "sciencedirect",
    "ebsco",
    "ovid",
```

- [ ] **Step 4: `check_databases`** en `revisia/llm/preflight.py`. En los imports, antes de `from revisia.llm.deprecations import retirement_for`, añadir:

```python
from revisia.agents import search_backends
```

Tras `_default_which: Which = shutil.which` añadir:

```python

# Extensiones que `ingest.manual_import.import_directory` sabe leer.
_IMPORT_SUFFIXES = frozenset({".ris", ".bib", ".bibtex"})
```

Justo antes de `def _configured_models(` insertar:

```python
def check_databases(
    protocol: ReviewProtocol, protocol_dir: str | Path, *, find_spec: FindSpec
) -> list[PreflightIssue]:
    """Bases declaradas, cadenas de búsqueda, importación manual y ``httpx``."""
    base = Path(protocol_dir)
    issues: list[PreflightIssue] = []
    databases = list(protocol.databases)
    with_backend: list[str] = []
    manual: list[str] = []
    if not databases:
        issues.append(
            _warning(
                "databases",
                "`databases` está vacío: se buscará solo en OpenAlex (por defecto). "
                "Declara las bases en protocol.yml para que PRISMA-S las liste.",
            )
        )
        with_backend.append("OpenAlex")
    for db in databases:
        key = search_backends.db_key(db)
        where = f"databases.{db}"
        if key in search_backends.BACKENDS:
            with_backend.append(db)
            string_file = base / "search_strings" / f"{key}.txt"
            text = string_file.read_text(encoding="utf-8") if string_file.exists() else ""
            if not text.strip():
                issues.append(
                    _warning(
                        where,
                        f"sin cadena en search_strings/{key}.txt (o el fichero está vacío): "
                        "se usará la pregunta como cadena. PRISMA-S 8 pide la cadena exacta "
                        "de cada base.",
                    )
                )
        elif key in search_backends.MANUAL_ONLY:
            manual.append(db)
        else:
            issues.append(
                _error(
                    where,
                    f"base desconocida {db!r} (clave {key!r}): no tiene backend ni es de "
                    "importación manual. Revisa la ortografía; si la consultas en su web y "
                    "exportas a RIS/BibTeX, deja el fichero en imported/ y quítala de "
                    "`databases` (o pide añadirla a MANUAL_ONLY).",
                )
            )
    imported = base / "imported"
    has_imports = imported.is_dir() and any(
        p.suffix.lower() in _IMPORT_SUFFIXES for p in imported.iterdir()
    )
    if not has_imports:
        for db in manual:
            issues.append(
                _warning(
                    f"databases.{db}",
                    f"{db!r} es de importación manual y no hay ficheros .ris/.bib en "
                    "imported/: exporta sus resultados ahí o no aportará registros.",
                )
            )
    if not _importable("httpx", find_spec):
        if with_backend:
            issues.append(
                _error(
                    "busqueda",
                    "falta httpx (extra `search`): fallarían todas las bases con backend "
                    f"({', '.join(with_backend)}) y la recuperación de texto completo. "
                    "Instálalo con `uv sync --extra search`.",
                )
            )
        else:
            issues.append(
                _warning(
                    "texto_completo",
                    "falta httpx (extra `search`): no se recuperará ningún texto completo y "
                    "todos los registros quedarán como no recuperados. "
                    "`uv sync --extra search`.",
                )
            )
    return issues


```

Al final de `preflight`, sustituir

```python
    issues += check_retired(protocol, today)
    return PreflightReport(_merge(issues))
```

por

```python
    issues += check_retired(protocol, today)
    if context != "resume":
        issues += check_databases(protocol, protocol_dir, find_spec=find_spec)
        if context == "run" and not mailto:
            issues.append(
                _warning(
                    "mailto",
                    "sin --mailto no se consultan Unpaywall ni el ID Converter de PMC: más "
                    "registros quedarán como no recuperados.",
                )
            )
    return PreflightReport(_merge(issues))
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_preflight.py -v`
Expected: PASS, 32 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 396 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/llm/preflight.py revisia/agents/search_backends.py tests/test_preflight.py
git commit -m "feat(llm): preflight de bases, cadenas, importación manual, httpx y mailto (M6)" -m "check_databases da error por base desconocida y por httpx ausente con bases con backend, y avisa de cadenas ausentes o vacías (PRISMA-S 8), bases manuales sin imported/, databases vacío y httpx ausente con solo bases manuales. run sin --mailto avisa; resume salta bases y búsqueda (congeladas). MANUAL_ONLY gana CINAHL, Cochrane/CENTRAL, ProQuest, EconLit, JSTOR, IEEE Xplore, ACM, ScienceDirect, EBSCO y Ovid. Auditoría 2026-09-03, M6; D10." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Preflight en el CLI y carga de `.env`

**Files:**
- Modify: `revisia/cli.py` (docstring l.1-8; import l.22; sustituir `_configured_models` y `_retired_model_problems`, l.59-89, por `_load_dotenv` y `_print_preflight`; `_cmd_validate`, l.92-129; `main`, l.485-487 y l.516-529)
- Modify: `tests/test_cli_validate.py` (docstring e imports l.1-14; fixture nueva; firmas de los tests de l.35, l.44 y l.72; tres tests nuevos al final)
- Modify: `tests/test_cli_errores.py` (imports l.11-12; fixture nueva; firmas de los tests de l.50 y l.77)

**Interfaces:**
- Consumes: `preflight(...)`, `PreflightReport`, `revisia.llm.preflight._default_find_spec` (Tareas 6-7).
- Produces:
  - `revisia.cli._load_dotenv() -> None` (llamada al inicio de `main`; `find_dotenv(usecwd=True)` + `load_dotenv(path, override=False)`; los tests la sustituyen por un no-op)
  - `revisia.cli._print_preflight(report: PreflightReport) -> None` (avisos a stdout, `aviso [<where>]: …`; errores a stderr, `error [<where>]: …`)
  - `_cmd_validate` devuelve 2 ante cualquier error de preflight y no imprime "✓ Protocolo válido".
  - `run`: el preflight (`context="run"`, `mailto=args.mailto`) corre antes de `_cmd_run`; con errores sale con 2 sin crear `runs_root`.
  - Desaparecen `cli._configured_models` y `cli._retired_model_problems` (absorbidos por `preflight._configured_models` y `check_retired`; ningún test los importa).
  - Fixtures de test: `entorno_listo` (en `tests/test_cli_validate.py`) y `httpx_instalado` (en `tests/test_cli_errores.py`).

Por qué cambian tests existentes: con el preflight, `validate`/`run` miran el entorno. La plantilla usa Gemini (SDK `google.genai` y `GEMINI_API_KEY`) y bases con backend; el demo usa el proveedor `fake` y OpenAlex. El venv de desarrollo no instala ni `google-genai` ni `httpx`, así que sin parchear `find_spec` y la key esos tests darían rc 2 por el entorno y no por lo que prueban.

- [ ] **Step 1: Tests (los nuevos fallan; los existentes pasan a usar fixtures).** En `tests/test_cli_validate.py`, sustituir la cabecera

```python
"""`revisia validate` detiene el quickstart ante un modelo retirado (C4, D7)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from revisia import cli

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"
```

por

```python
"""`revisia validate`/`run`: modelos retirados (C4, D7) y preflight sin red (M6, D10)."""

from __future__ import annotations

import os
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml

from revisia import cli
from revisia.llm import preflight as preflight_mod

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "protocols" / "_TEMPLATE"


@pytest.fixture()
def entorno_listo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Máquina "configurada": key de Gemini, SDKs y httpx instalados, sin .env real.

    La plantilla usa Gemini y bases con backend: sin esto, el preflight (M6)
    daría rc 2 por el entorno del venv de pruebas, no por el protocolo.
    """
    monkeypatch.setattr(cli, "_load_dotenv", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(preflight_mod, "_default_find_spec", lambda _name: object())
```

Sustituir la firma de `test_validate_avisa_retiro_futuro_sin_fallar` (l.35-37)

```python
def test_validate_avisa_retiro_futuro_sin_fallar(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
```

por

```python
def test_validate_avisa_retiro_futuro_sin_fallar(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    entorno_listo: None,
) -> None:
```

la de `test_validate_plantilla_pasa` (l.44)

```python
def test_validate_plantilla_pasa(capsys: pytest.CaptureFixture) -> None:
```

por

```python
def test_validate_plantilla_pasa(capsys: pytest.CaptureFixture, entorno_listo: None) -> None:
```

y la de `test_run_con_modelo_por_retirarse_avisa_y_ejecuta` (l.72-74)

```python
def test_run_con_modelo_por_retirarse_avisa_y_ejecuta(
    tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
```

por

```python
def test_run_con_modelo_por_retirarse_avisa_y_ejecuta(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    entorno_listo: None,
) -> None:
```

(los cuerpos no cambian). Añadir al final del fichero:

```python


# ── Preflight en el CLI (auditoría 2026-09-03, M6; spec 2026-10-04 §5) ──────


def _protocolo_sin_proveedor_ft(tmp_path: Path) -> Path:
    """Protocolo que carga pero no puede correr: solo T/A tiene proveedor."""
    proto = tmp_path / "p"
    shutil.copytree(TEMPLATE_DIR, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["llm"] = {"screening_ta": {"provider": "fake", "model": "fake-1"}}
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return proto


def test_cli_validate_sale_2_con_error_de_preflight(
    tmp_path: Path, capsys: pytest.CaptureFixture, entorno_listo: None
) -> None:
    # M6: antes devolvía 0 e imprimía "(sin proveedor)".
    rc = cli.main(["validate", str(_protocolo_sin_proveedor_ft(tmp_path))])
    captured = capsys.readouterr()
    assert rc == 2
    assert "screening_ft" in captured.err
    assert "Protocolo válido" not in captured.out


def test_cli_run_preflight_falla_sin_crear_runs_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    entorno_listo: None,
) -> None:
    def _no_debe_correr(*_a, **_k):
        raise AssertionError("run_review no debe llamarse si el preflight falla")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _no_debe_correr)
    runs_root = tmp_path / "runs"
    proto = _protocolo_sin_proveedor_ft(tmp_path)
    rc = cli.main(["run", str(proto), "--runs-root", str(runs_root)])
    assert rc == 2
    assert "screening_ft" in capsys.readouterr().err
    assert not runs_root.exists()


def test_cli_carga_dotenv_sin_sobrescribir_el_entorno(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "REVISIA_PRUEBA_DOTENV=desde-dotenv\nGEMINI_API_KEY=desde-dotenv\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "del-entorno")
    # setenv + delenv: la variable no existe, pero monkeypatch la borrará al
    # terminar aunque la cree load_dotenv (no se filtra a otros tests).
    monkeypatch.setenv("REVISIA_PRUEBA_DOTENV", "provisional")
    monkeypatch.delenv("REVISIA_PRUEBA_DOTENV")

    assert cli.main(["brain", str(tmp_path / "sin-cerebro")]) == 1  # cualquier subcomando

    assert os.environ["REVISIA_PRUEBA_DOTENV"] == "desde-dotenv"
    assert os.environ["GEMINI_API_KEY"] == "del-entorno"  # override=False
```

En `tests/test_cli_errores.py`, sustituir

```python
from revisia.cli import main
from revisia.orchestration.hitl import DecisionFileError
```

por

```python
from revisia import cli
from revisia.cli import main
from revisia.llm import preflight as preflight_mod
from revisia.orchestration.hitl import DecisionFileError
```

justo antes de `def _protocolo_con_autonomia(` añadir:

```python
@pytest.fixture()
def httpx_instalado(monkeypatch: pytest.MonkeyPatch) -> None:
    """El demo (proveedor fake + OpenAlex) solo necesita httpx para pasar el
    preflight (M6); el venv de pruebas no lo instala. Sin .env real."""
    monkeypatch.setattr(cli, "_load_dotenv", lambda: None)
    monkeypatch.setattr(preflight_mod, "_default_find_spec", lambda _name: object())


```

y cambiar las firmas de `test_cli_run_decision_invalida_sale_2` (l.50-52) y `test_cli_run_rechazado_sale_1_y_no_sedimenta` (l.77-79):

```python
def test_cli_run_decision_invalida_sale_2(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch, httpx_instalado: None
) -> None:
```

```python
def test_cli_run_rechazado_sale_1_y_no_sedimenta(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    httpx_instalado: None,
) -> None:
```

(los cuerpos no cambian).

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_cli_validate.py tests/test_cli_errores.py -v`
Expected: ERROR en los siete tests que usan `entorno_listo`/`httpx_instalado` (`AttributeError: <module 'revisia.cli'> has no attribute '_load_dotenv'`) y FAIL en `test_cli_carga_dotenv_sin_sobrescribir_el_entorno` (`KeyError: 'REVISIA_PRUEBA_DOTENV'`). El resto, en verde.

- [ ] **Step 3: Implementar en `revisia/cli.py`.**

En la docstring del módulo, sustituir

```
  * ``revisia validate <dir>`` — carga y valida un protocol.yml y muestra
    el pipeline configurado (etapas, autonomía, proveedor por etapa).
```

por

```
  * ``revisia validate <dir>`` — carga y valida un protocol.yml, corre el
    preflight sin red (proveedores, SDK, keys, bases, modelos retirados) y
    muestra el pipeline configurado (etapas, autonomía, proveedor por etapa).
```

Sustituir el import

```python
from revisia.llm.deprecations import retirement_for
```

por

```python
from revisia.llm.preflight import PreflightReport, preflight
```

Sustituir las funciones `_configured_models` y `_retired_model_problems` completas (l.59-89) por:

```python
def _load_dotenv() -> None:
    """Carga ``.env`` sin sobrescribir el entorno (D10).

    El README pide poner la API key en ``.env``, pero hasta la Ola 1 ningún
    módulo lo leía (``python-dotenv`` era dependencia sin uso). Se busca desde
    el directorio actual hacia arriba; una variable ya definida en el entorno
    gana siempre (``override=False``).
    """
    from dotenv import find_dotenv, load_dotenv

    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)


def _print_preflight(report: PreflightReport) -> None:
    """Imprime los problemas del preflight agrupados por nivel.

    Los avisos van a stdout y los errores a stderr, como el resto del CLI.
    """
    if report.warnings:
        print("  Avisos del preflight:")
        for issue in report.warnings:
            print(f"    aviso [{issue.where}]: {issue.message}")
    if report.errors:
        print(f"error: el preflight encontró {len(report.errors)} error(es):", file=sys.stderr)
        for issue in report.errors:
            print(f"  error [{issue.where}]: {issue.message}", file=sys.stderr)
```

En `_cmd_validate`, sustituir el principio

```python
def _cmd_validate(protocol, protocol_dir: str) -> int:
    # Modelos retirados (auditoría 2026-09-03, C4): calculados antes para no
    # imprimir "✓ Protocolo válido" cuando el protocolo carga pero usaría un
    # modelo que ya no responde (revisión final, ítem 4).
    errors, avisos_retiro = _retired_model_problems(protocol, _today())
    if errors:
        print(
            f"⚠ Protocolo carga, pero usa modelo(s) retirado(s): "
            f"{protocol.title}  [{protocol.slug}]"
        )
    else:
```

por

```python
def _cmd_validate(protocol, protocol_dir: str) -> int:
    # Preflight sin red (auditoría 2026-09-03, M6; D10): antes devolvía 0 con
    # "(sin proveedor)" o sin la API key. Se calcula antes de imprimir para no
    # decir "✓ Protocolo válido" de un protocolo que no podría correr.
    report = preflight(protocol, protocol_dir, context="validate", today=_today())
    if report.errors:
        print(
            f"✗ El protocolo carga, pero el preflight encontró {len(report.errors)} "
            f"error(es): {protocol.title}  [{protocol.slug}]"
        )
    else:
```

y su final

```python
    for aviso in avisos_retiro:
        print(f"  aviso: {aviso}")
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 2 if errors else 0
```

por

```python
    _print_preflight(report)
    return 2 if report.errors else 0
```

En `main`, sustituir

```python
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
```

por

```python
def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    parser = build_parser()
```

y, en la rama `run`, sustituir

```python
        # Modelos retirados (auditoría 2026-09-03, C4): el quickstart del README
        # va directo a `run` sin pasar por `validate`, así que el 404 a mitad de
        # corrida seguía ocurriendo. Se ataja aquí, antes de crear ninguna
        # carpeta de corrida (revisión final, ítem 3).
        errors, avisos_retiro = _retired_model_problems(protocol, _today())
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 2
        for aviso in avisos_retiro:
            print(f"aviso: {aviso}")
```

por

```python
        # Preflight sin red ANTES de crear ninguna carpeta (auditoría 2026-09-03,
        # M6 y C4): el quickstart va directo a `run` sin pasar por `validate`, y
        # una key ausente para FT se descubría tras gastar el cribado T/A.
        report = preflight(
            protocol, protocol_dir, context="run", mailto=args.mailto, today=_today()
        )
        _print_preflight(report)
        if report.errors:
            return 2
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_cli_validate.py tests/test_cli_errores.py tests/test_deprecations.py -v`
Expected: PASS todos (los de modelos retirados siguen viendo `gemini-2.0-flash` y `2026-06-01` en stderr y `2027-05-07` en stdout).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, **399 recogidos**.

Run: `grep -n "_retired_model_problems\|_configured_models\|retirement_for" revisia/cli.py`
Expected: sin resultados.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/cli.py tests/test_cli_validate.py tests/test_cli_errores.py
git commit -m "feat(cli): preflight en validate y run (rc 2) y carga de .env (M6)" -m "validate imprime los problemas del preflight agrupados por nivel y sale con 2 ante cualquier error (antes 0 con '(sin proveedor)'); run corre el preflight antes de crear la carpeta de la corrida. main carga .env con find_dotenv(usecwd=True) y override=False. Los tests de CLI que dependen del entorno usan fixtures con find_spec y la key falsos. Auditoría 2026-09-03, M6; D10." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Pista B · PR-B `feat/ola1-flujo-prisma` (worktree `C:\revisia-wt\b`)

Todas las tareas de esta pista se ejecutan en `C:\revisia-wt\b`, rama `feat/ola1-flujo-prisma` (creada en la Tarea 5, Step 7), en paralelo con la pista A. No tocan ningún fichero de A: el rebase de la Tarea 15 no tiene conflictos.

### Task 9: Motivo de no recuperación en `FullText`

**Files:**
- Modify: `revisia/agents/fulltext.py` (docstring del módulo l.9-11; imports l.18-19; `FullText` l.26-32; `fetch_fulltext` l.110 y ramas de fallo l.125-126, l.129-130, l.137-138, l.145-146)
- Modify: `tests/test_fulltext.py` (imports l.3-6; aserción en `test_fetch_fulltext_fallback_a_abstract_sin_red`, l.31-35; tests nuevos al final)
- Modify: `tests/test_pmc_ncbi.py` (aserciones de `reason` en los tests de l.318, l.344 y l.356)

**Interfaces:**
- Consumes: `FulltextReason` (Tarea 1); `revisia.agents._http.redact_secrets(text: str) -> str` (existente).
- Produces: `FullText` (dataclass `slots=True`): `text: str`, `available: bool`, `source_url: str | None = None`, `reason: FulltextReason | None = None`, `detail: str | None = None`. `fetch_fulltext` pone `reason="sin_url_oa"` (sin URL de acceso abierto; l.126), `"sin_httpx"` (l.130), `"error_http"` (red, 4xx/5xx o error de parseo de la respuesta; l.138) y `"texto_vacio"` (respuesta sin texto extraíble; l.146), con `detail` redactado; un recuperado lleva `reason=None`, `detail=None`. El fallback sigue llevando el abstract en `text`.

- [ ] **Step 1: Tests que fallan.** En `tests/test_fulltext.py`, sustituir los imports

```python
from __future__ import annotations

from revisia.agents.fulltext import fetch_fulltext, resolve_oa_url, strip_html
from revisia.schemas.records import SearchRecord
```

por

```python
from __future__ import annotations

import sys
import types

import pytest

from revisia.agents.fulltext import fetch_fulltext, resolve_oa_url, strip_html
from revisia.schemas.records import SearchRecord
```

al final de `test_fetch_fulltext_fallback_a_abstract_sin_red` (tras `assert ft.text == "resumen del estudio"`) añadir

```python
    assert ft.reason == "sin_url_oa"
```

y añadir al final del fichero:

```python


# ── Motivo del fallo (auditoría 2026-09-03, M11; spec 2026-10-04 §6) ────────


def _httpx_falso(*, error: Exception | None = None, body: bytes = b"", ctype: str = "text/html"):
    """Módulo ``httpx`` sustituto: un ``Client`` que responde o lanza, sin red."""

    class _Resp:
        headers = {"content-type": ctype}
        content = body

        def raise_for_status(self) -> None:
            if error is not None:
                raise error

    class _Client:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> bool:
            return False

        def get(self, _url: str) -> _Resp:
            return _Resp()

    modulo = types.ModuleType("httpx")
    modulo.Client = _Client  # type: ignore[attr-defined]
    return modulo


@pytest.mark.parametrize(
    ("caso", "esperado"),
    [
        ("sin_url", "sin_url_oa"),
        ("sin_httpx", "sin_httpx"),
        ("error_http", "error_http"),
        ("texto_vacio", "texto_vacio"),
    ],
)
def test_fetch_fulltext_registra_motivo(
    monkeypatch: pytest.MonkeyPatch, caso: str, esperado: str
) -> None:
    extra = {} if caso == "sin_url" else {"oa_url": "https://oa.example/p?api_key=SECRETO"}
    rec = SearchRecord(record_id="r", title="t", abstract="resumen", extra=extra)
    if caso == "sin_httpx":
        monkeypatch.setitem(sys.modules, "httpx", None)  # `import httpx` → ImportError
    elif caso == "error_http":
        error = RuntimeError("503 Service Unavailable para https://oa.example/p?api_key=SECRETO")
        monkeypatch.setitem(sys.modules, "httpx", _httpx_falso(error=error))
    elif caso == "texto_vacio":
        monkeypatch.setitem(sys.modules, "httpx", _httpx_falso(body=b"<html><body> </body></html>"))

    ft = fetch_fulltext(rec)

    assert ft.available is False
    assert ft.reason == esperado
    assert ft.detail
    assert "SECRETO" not in ft.detail  # el detalle va redactado
    assert ft.text == "resumen"  # compatibilidad: el abstract sigue en text


def test_fetch_fulltext_recuperado_sin_motivo(monkeypatch: pytest.MonkeyPatch) -> None:
    html = b"<html><body><p>Texto completo del estudio.</p></body></html>"
    monkeypatch.setitem(sys.modules, "httpx", _httpx_falso(body=html))
    rec = SearchRecord(record_id="r", title="t", extra={"oa_url": "https://oa.example/p"})
    ft = fetch_fulltext(rec)
    assert (ft.available, ft.reason, ft.detail) == (True, None, None)
    assert ft.text == "Texto completo del estudio."
```

En `tests/test_pmc_ncbi.py`:
- en `test_fetch_fulltext_prefiere_bioc`, tras `assert "PMC7654321" in (ft.source_url or "")`, añadir `    assert ft.reason is None`;
- en `test_fetch_fulltext_sin_pmcid_ni_mailto_no_toca_red`, tras `assert ft.text == "solo abstract"`, añadir

```python
    assert ft.reason == "sin_url_oa"
    assert "--mailto" in (ft.detail or "")
```

- en `test_fetch_fulltext_bioc_no_oa_cae_a_abstract`, tras `assert ft.available is False and ft.text == "abs"`, añadir `    assert ft.reason == "sin_url_oa"`.

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_fulltext.py tests/test_pmc_ncbi.py -v`
Expected: FAIL con `AttributeError: 'FullText' object has no attribute 'reason'` en los cuatro casos de `test_fetch_fulltext_registra_motivo`, en `test_fetch_fulltext_recuperado_sin_motivo`, en `test_fetch_fulltext_fallback_a_abstract_sin_red` y en los tres de `test_pmc_ncbi.py` tocados.

- [ ] **Step 3: Implementar** en `revisia/agents/fulltext.py`. Al final de la docstring del módulo, tras `` ``pypdf`` para extraer PDFs. Sin ellas, cae al abstract sin romper.``, añadir el párrafo:

```
Cada fallo deja su motivo en ``FullText.reason`` (y un ``detail`` redactado):
hasta la Ola 1 un registro sin texto se cribaba con el abstract y el motivo se
perdía (auditoría 2026-09-03, M11). El pipeline ya no criba esos registros
(D2): van a la caja "informes no recuperados" del diagrama PRISMA.
```

Sustituir los imports

```python
from revisia.agents import ncbi
from revisia.schemas.records import SearchRecord
```

por

```python
from revisia.agents import _http, ncbi
from revisia.schemas.artifacts import FulltextReason
from revisia.schemas.records import SearchRecord
```

Sustituir `FullText` completo por:

```python
@dataclass(slots=True)
class FullText:
    """Resultado de la adquisición de texto completo.

    ``reason`` es ``None`` si y solo si ``available``. Si no se recuperó,
    ``text`` sigue llevando el abstract por compatibilidad, pero el pipeline lo
    ignora (D2). ``detail`` va redactado (``_http.redact_secrets``).
    """

    text: str
    available: bool
    source_url: str | None = None
    reason: FulltextReason | None = None
    detail: str | None = None
```

En `fetch_fulltext`, sustituir la línea

```python
    fallback = FullText(text=record.abstract or "", available=False)
```

por

```python

    def fallback(reason: FulltextReason, detail: str) -> FullText:
        return FullText(
            text=record.abstract or "",
            available=False,
            reason=reason,
            detail=_http.redact_secrets(detail),
        )
```

y el bloque desde `url = resolve_oa_url(record, mailto=mailto)` hasta el final de la función por:

```python
    url = resolve_oa_url(record, mailto=mailto)
    if not url:
        return fallback(
            "sin_url_oa",
            "sin URL de acceso abierto (ni PMCID con texto en BioC, ni oa_url, ni "
            "Unpaywall)" + ("" if mailto else "; sin --mailto no se consulta Unpaywall"),
        )
    try:
        import httpx
    except ImportError:
        return fallback("sin_httpx", "httpx no está instalado (extra `search`)")
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            raw = resp.content
    except Exception as exc:  # red, 4xx/5xx, TLS…: no recuperado, con su motivo
        return fallback("error_http", f"{type(exc).__name__}: {exc}")

    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        text = _extract_pdf(raw)
    else:
        text = strip_html(raw.decode("utf-8", errors="ignore"))

    if not text:
        return fallback("texto_vacio", f"{url} no devolvió texto extraíble")
    return FullText(text=text[:max_chars], available=True, source_url=url)
```

(El `# pragma: no cover` del `ImportError` desaparece: ahora la rama tiene test.)

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_fulltext.py tests/test_pmc_ncbi.py -v`
Expected: PASS todos.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 369 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/agents/fulltext.py tests/test_fulltext.py tests/test_pmc_ncbi.py
git commit -m "feat(fulltext): registrar el motivo de cada texto completo no recuperado (M11)" -m "FullText gana reason (sin_url_oa, sin_httpx, error_http, texto_vacio) y detail redactado; antes el motivo se perdía. El fallback conserva el abstract en text por compatibilidad. Auditoría 2026-09-03, M11; spec 2026-10-04 §6." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Conteos PRISMA estrictos en diagrama, tabla, CSV y métodos

**Files:**
- Modify: `revisia/exports/prisma_flow.py` (fichero completo: docstring, imports, `PrismaCounts` con validador, `_ft_split`, `render_flow_diagram`, `render_flow_markdown`)
- Modify: `revisia/exports/interop.py:110-112`
- Modify: `revisia/exports/methods.py:77-79`
- Modify: `tests/test_flow_oficial_y_check.py` (`_COUNTS` l.14-27; aserciones l.40-41 y l.45; test nuevo)
- Modify: `tests/test_interop.py` (test nuevo antes de `test_checklist_abstracts_prerellena_evidencia`, l.91)
- Modify: `tests/test_coverage_gaps.py` (test nuevo al final)
- Modify: `tests/test_export_document.py` (imports l.14-17; test nuevo antes de `test_html_autocontenido_sin_recursos_externos`)

**Interfaces:**
- Consumes: campos de `PrismaCounts` de la Tarea 3.
- Produces:
  - `PrismaCounts` **sin** `fulltext_abstract_only`; `@model_validator(mode="before") _manifiesto_anterior_a_la_ola_1`: si el dato es un dict sin `fulltext_sought`, fija `fulltext_sought = fulltext_assessed`, `fulltext_not_retrieved = 0` y, si tampoco trae `excluded_ft_human`/`excluded_ft_ai`, `excluded_ft_human = 0` y `excluded_ft_ai = excluded_ft`; siempre descarta `fulltext_abstract_only`.
  - Mermaid con nodos `S["Informes buscados para recuperación (n = …)"]`, `N["Informes no recuperados (n = …)"]`, `E["Informes evaluados para elegibilidad (n = …)"]` (con `<br/>(rescatados por el revisor: n = …)***` si `fulltext_rescued > 0`), aristas `C --> S`, `S --> N`, `S --> E`, `E --> F`, y `F` con `por humano (n = …) · por IA (n = …)**`.
  - Tabla con filas `Informes buscados para recuperación`, `Informes no recuperados`, `Informes evaluados para elegibilidad`, `— rescatados por el revisor` (si > 0), `Excluidos en elegibilidad`, `— excluidos por humano (elegibilidad)`, `— excluidos por IA (elegibilidad)`.
  - CSV PRISMA2020: `dbr_sought_reports = fulltext_sought`, `dbr_notretrieved_reports = fulltext_not_retrieved`, `dbr_assessed = fulltext_assessed`.
  - `metodologia.md`: `buscados a texto completo=… · no recuperados=… · evaluados para elegibilidad=…`.

El pipeline todavía pasa `fulltext_abstract_only=` a `PrismaCounts` (lo cambia la Tarea 12): el validador lo descarta y la suite sigue en verde entre tareas.

- [ ] **Step 1: Tests (nuevos que fallan y existentes ajustados).** En `tests/test_flow_oficial_y_check.py`, sustituir `_COUNTS` completo por:

```python
_COUNTS = PrismaCounts(
    identified=120,
    identified_by_source={"openalex": 40, "crossref": 40, "europepmc": 40},
    duplicates_removed=20,
    screened=100,
    excluded_ta=70,
    excluded_ta_human=10,
    excluded_ta_ai=60,
    fulltext_sought=30,
    fulltext_not_retrieved=8,
    fulltext_assessed=22,
    excluded_ft=5,
    excluded_ft_human=2,
    excluded_ft_ai=3,
    ft_exclusion_reasons={"población incorrecta": 3, "sin datos de desenlace": 2},
    included=17,
)
```

En `test_flow_diagram_plantilla_oficial_v1`, sustituir

```python
    assert "Informes evaluados para elegibilidad (n = 30)" in mermaid
    assert "sin texto completo recuperable: n = 8" in mermaid
```

por

```python
    assert "Informes evaluados para elegibilidad (n = 22)" in mermaid
```

y

```python
    assert "Estudios incluidos en la revisión (n = 25)" in mermaid
```

por

```python
    assert "Estudios incluidos en la revisión (n = 17)" in mermaid
```

Añadir justo después de ese test:

```python


def test_flow_diagram_buscados_no_recuperados_evaluados() -> None:
    # PRISMA estricto (D2; auditoría 2026-09-03, M11): los no recuperados tienen
    # su caja y no cuentan como evaluados.
    mermaid = render_flow_diagram(_COUNTS)
    assert 'S["Informes buscados para recuperación (n = 30)"]' in mermaid
    assert 'N["Informes no recuperados (n = 8)"]' in mermaid
    assert 'E["Informes evaluados para elegibilidad (n = 22)"]' in mermaid
    for arista in ("C --> S", "S --> N", "S --> E", "E --> F"):
        assert arista in mermaid
    assert "Informes excluidos (n = 5)<br/>por humano (n = 2) · por IA (n = 3)**" in mermaid
    assert "rescatados por el revisor" not in mermaid
    assert "sin texto completo recuperable" not in mermaid  # caja retirada

    con_rescate = _COUNTS.model_copy(
        update={"fulltext_not_retrieved": 6, "fulltext_rescued": 2, "fulltext_assessed": 24}
    )
    mermaid = render_flow_diagram(con_rescate)
    assert "(rescatados por el revisor: n = 2)***" in mermaid
    assert "\\*** Informes que el motor no pudo recuperar" in mermaid

    table = render_flow_markdown(_COUNTS)
    assert "| Informes buscados para recuperación | 30 |" in table
    assert "| Informes no recuperados | 8 |" in table
    assert "| Informes evaluados para elegibilidad | 22 |" in table
    assert "| — excluidos por humano (elegibilidad) | 2 |" in table
    assert "| — excluidos por IA (elegibilidad) | 3 |" in table
    assert "| — rescatados por el revisor | 2 |" in render_flow_markdown(con_rescate)
```

En `tests/test_interop.py`, justo antes de `def test_checklist_abstracts_prerellena_evidencia() -> None:` añadir:

```python
def test_prisma_csv_dbr_notretrieved_real() -> None:
    # Auditoría 2026-09-03, M11: dbr_notretrieved_reports era un 0 literal y
    # dbr_sought_reports copiaba los evaluados.
    counts = PrismaCounts(
        screened=80,
        excluded_ta=50,
        fulltext_sought=30,
        fulltext_not_retrieved=8,
        fulltext_assessed=22,
        excluded_ft=5,
        included=17,
    )
    rows = render_prisma2020_flow_csv(counts).strip().splitlines()

    def n_de(data: str) -> str:
        return next(r for r in rows if r.startswith(f"{data},")).rsplit(",", 1)[1]

    assert n_de("dbr_sought_reports") == "30"
    assert n_de("dbr_notretrieved_reports") == "8"
    assert n_de("dbr_assessed") == "22"
    assert n_de("records_excluded") == "50"
    assert n_de("new_studies") == "17"


```

Al final de `tests/test_coverage_gaps.py` añadir:

```python


def test_methods_reporta_buscados_y_no_recuperados() -> None:
    protocol = ReviewProtocol.model_validate(
        {
            "slug": "demo",
            "title": "Demo",
            "question": {"text": "¿X afecta Y?", "framework": "PEO", "components": {"P": "x"}},
        }
    )
    counts = PrismaCounts(
        identified=50,
        screened=40,
        fulltext_sought=12,
        fulltext_not_retrieved=4,
        fulltext_assessed=8,
        included=5,
    )
    md = render_methods(protocol=protocol, counts=counts, models=["fake:fake-1"])
    assert "buscados a texto completo=12" in md
    assert "no recuperados=4" in md
    assert "evaluados para elegibilidad=8" in md
    assert "texto completo=8 " not in md  # la cifra ambigua de antes
```

En `tests/test_export_document.py`, sustituir

```python
import pytest

from revisia.cli import main
from revisia.exports.document import assemble_html, export_run
```

por

```python
import pytest
import yaml

from revisia.cli import main
from revisia.exports import PrismaCounts
from revisia.exports.document import assemble_html, export_run
```

y, justo antes de `def test_html_autocontenido_sin_recursos_externos(run_dir: Path) -> None:`, añadir:

```python
def test_counts_manifiesto_antiguo_se_lee_sin_mentir(run_dir: Path) -> None:
    # Manifiesto v0.7 (D13): sin fulltext_sought y con el campo retirado
    # fulltext_abstract_only. Lo que de verdad pasó: los 28 se "evaluaron" (10
    # con el abstract), nada quedó como no recuperado y nadie etiquetó.
    counts = PrismaCounts.model_validate(yaml.safe_load(_MANIFEST)["counts"])
    assert counts.fulltext_sought == counts.fulltext_assessed == 28
    assert counts.fulltext_not_retrieved == 0
    assert (counts.excluded_ft_human, counts.excluded_ft_ai) == (0, 3)
    assert "fulltext_abstract_only" not in counts.model_dump()
    # Sigue siendo exportable: la tabla del flujo sale del manifiesto antiguo.
    html = assemble_html(run_dir)
    assert "Informes buscados para recuperación" in html
    assert "Informes no recuperados" in html


```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_flow_oficial_y_check.py tests/test_interop.py tests/test_coverage_gaps.py tests/test_export_document.py -v`
Expected: FAIL `test_flow_diagram_buscados_no_recuperados_evaluados` (no hay nodo `S`), `test_prisma_csv_dbr_notretrieved_real` (`'22' == '30'`), `test_methods_reporta_buscados_y_no_recuperados` y `test_counts_manifiesto_antiguo_se_lee_sin_mentir` (`0 == 28`). `test_flow_diagram_plantilla_oficial_v1` ajustado ya pasa.

- [ ] **Step 3: Implementar `prisma_flow.py`** — sustituir el fichero completo por:

````python
"""Diagrama de flujo PRISMA 2020 · plantillas oficiales, con conteos reales.

Implementa la estructura de las **plantillas oficiales** del flow diagram
PRISMA 2020 (CC BY 4.0; Page MJ, et al. BMJ 2021;372:n71):

- **v1 · nuevas revisiones, solo bases de datos/registros** — el render por
  defecto, con las cajas oficiales: identificación (con desglose por base),
  eliminados antes del cribado (duplicados / automatización / otros), cribados,
  excluidos (con separación humano vs IA — nota ** de la plantilla oficial y
  requisito PRISMA-trAIce R1), informes buscados / no recuperados / evaluados,
  excluidos con **razones** (también humano vs IA), e incluidos. Un informe sin
  texto completo no se evalúa: cuenta como "no recuperado" (PRISMA estricto, D2
  de la Ola 1; auditoría 2026-09-03, M11).
- **v3 · revisiones actualizadas** — :func:`render_flow_updated` añade la
  columna "estudios de la versión previa" y los totales nuevos/acumulados;
  se alimenta de la memoria del investigador (living review).

Todo se computa de forma determinista del recorrido real del pipeline y se
renderiza como Mermaid (portable, versionable) + tabla Markdown.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

_FOOTER = (
    "\n> Estructura de cajas según la plantilla oficial PRISMA 2020 (CC BY 4.0). "
    "Fuente: Page MJ, et al. BMJ 2021;372:n71. doi:10.1136/bmj.n71."
)


class PrismaCounts(BaseModel):
    """Conteos del flujo PRISMA 2020 (plantilla oficial v1).

    Attributes:
        identified: registros identificados en las búsquedas.
        identified_by_source: desglose por base (nota * de la plantilla oficial).
        duplicates_removed: duplicados eliminados antes del cribado.
        removed_automation: marcados inelegibles por herramientas automáticas
            antes del cribado (caja oficial; 0 si el motor no pre-filtra).
        removed_other: eliminados por otras razones antes del cribado.
        screened: registros cribados (título/abstract).
        excluded_ta: excluidos en cribado de título/abstract.
        excluded_ta_human: de los excluidos en T/A, cuántos por decisión humana
            (nota ** de la plantilla oficial · PRISMA-trAIce R1).
        excluded_ta_ai: de los excluidos en T/A, cuántos por la IA sin
            intervención humana.
        fulltext_sought: informes buscados para recuperación (pasaron T/A).
        fulltext_not_retrieved: informes buscados que no se recuperaron y que
            nadie rescató (caja "informes no recuperados").
        fulltext_rescued: no recuperados que el revisor consiguió por otra vía
            y evaluó (D2); cuentan como evaluados.
        fulltext_assessed: informes evaluados para elegibilidad
            (``fulltext_sought − fulltext_not_retrieved``).
        excluded_ft: excluidos en la evaluación de elegibilidad.
        excluded_ft_human: de los excluidos en elegibilidad, cuántos por
            decisión humana (PRISMA-trAIce R1).
        excluded_ft_ai: de los excluidos en elegibilidad, cuántos por la IA.
        ft_exclusion_reasons: razones de exclusión en texto completo → n
            (cajas "Reason 1..n" de la plantilla oficial).
        included: estudios incluidos en la síntesis.
    """

    identified: int = 0
    identified_by_source: dict[str, int] = Field(default_factory=dict)
    duplicates_removed: int = 0
    removed_automation: int = 0
    removed_other: int = 0
    screened: int = 0
    excluded_ta: int = 0
    excluded_ta_human: int | None = None
    excluded_ta_ai: int | None = None
    fulltext_sought: int = 0
    fulltext_not_retrieved: int = 0
    fulltext_rescued: int = 0
    fulltext_assessed: int = 0
    excluded_ft: int = 0
    excluded_ft_human: int = 0
    excluded_ft_ai: int = 0
    ft_exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    included: int = 0

    @model_validator(mode="before")
    @classmethod
    def _manifiesto_anterior_a_la_ola_1(cls, data: object) -> object:
        """Lee los conteos de un manifiesto v0.7 sin inventar nada (D13).

        Antes de la Ola 1 no existía ``fulltext_sought``: todo registro que
        pasaba T/A se "evaluaba" (con el abstract si no había texto completo) y
        ningún humano etiquetaba registros. Lo que de verdad pasó: buscados =
        evaluados, no recuperados = 0 y todas las exclusiones en elegibilidad
        son de la IA. ``fulltext_abstract_only`` se retira (contaba evaluaciones
        con el abstract, que ya no existen, D2).
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        data.pop("fulltext_abstract_only", None)
        if "fulltext_sought" not in data:
            data["fulltext_sought"] = data.get("fulltext_assessed", 0)
            data.setdefault("fulltext_not_retrieved", 0)
            if "excluded_ft_human" not in data and "excluded_ft_ai" not in data:
                data["excluded_ft_human"] = 0
                data["excluded_ft_ai"] = data.get("excluded_ft", 0)
        return data


def _by_source_lines(counts: PrismaCounts) -> str:
    if not counts.identified_by_source:
        return ""
    parts = [f"{db} (n = {n})" for db, n in sorted(counts.identified_by_source.items())]
    return "<br/>" + " · ".join(parts)


def _ta_split(counts: PrismaCounts) -> str:
    if counts.excluded_ta_human is None and counts.excluded_ta_ai is None:
        return ""
    human = counts.excluded_ta_human or 0
    ai = counts.excluded_ta_ai or 0
    return f"<br/>por humano (n = {human}) · por IA (n = {ai})**"


def _ft_split(counts: PrismaCounts) -> str:
    return (
        f"<br/>por humano (n = {counts.excluded_ft_human}) · por IA (n = {counts.excluded_ft_ai})**"
    )


def _reason_lines(counts: PrismaCounts) -> str:
    if not counts.ft_exclusion_reasons:
        return ""
    ordered = sorted(counts.ft_exclusion_reasons.items(), key=lambda kv: (-kv[1], kv[0]))
    return "".join(f"<br/>{reason} (n = {n})" for reason, n in ordered)


def render_flow_diagram(counts: PrismaCounts) -> str:
    """Renderiza el flow diagram PRISMA 2020 (plantilla v1 oficial) en Mermaid."""
    rescued = (
        f"<br/>(rescatados por el revisor: n = {counts.fulltext_rescued})***"
        if counts.fulltext_rescued
        else ""
    )
    lines = [
        "```mermaid",
        "flowchart TB",
        '    subgraph FASE_ID["Identificación de estudios vía bases de datos y registros"]',
        f'        A["Registros identificados (n = {counts.identified})*'
        f'{_by_source_lines(counts)}"]',
        '        B["Registros eliminados antes del cribado:'
        f"<br/>Duplicados (n = {counts.duplicates_removed})"
        f"<br/>Marcados inelegibles por automatización (n = {counts.removed_automation})"
        f'<br/>Otras razones (n = {counts.removed_other})"]',
        "        A --> B",
        "    end",
        '    subgraph FASE_SCR["Cribado"]',
        f'        C["Registros cribados (n = {counts.screened})"]',
        f'        D["Registros excluidos (n = {counts.excluded_ta}){_ta_split(counts)}"]',
        f'        S["Informes buscados para recuperación (n = {counts.fulltext_sought})"]',
        f'        N["Informes no recuperados (n = {counts.fulltext_not_retrieved})"]',
        f'        E["Informes evaluados para elegibilidad (n = {counts.fulltext_assessed})'
        f'{rescued}"]',
        f'        F["Informes excluidos (n = {counts.excluded_ft}){_ft_split(counts)}'
        f'{_reason_lines(counts)}"]',
        "        C --> D",
        "        C --> S",
        "        S --> N",
        "        S --> E",
        "        E --> F",
        "    end",
        '    subgraph FASE_INC["Incluidos"]',
        f'        G["Estudios incluidos en la revisión (n = {counts.included})'
        f'<br/>Informes de estudios incluidos (n = {counts.included})"]',
        "    end",
        "    A --> C",
        "    E --> G",
        "```",
        "",
        "\\* Desglose por base cuando el motor lo conoce (nota de la plantilla oficial).",
        "\\** Separación de exclusiones humano vs automatización: nota ** de la "
        "plantilla oficial y requisito PRISMA-trAIce (ítem R1).",
    ]
    if counts.fulltext_rescued:
        lines.append(
            "\\*** Informes que el motor no pudo recuperar en abierto y que el revisor "
            "consiguió por otra vía: los evaluó el humano, no la IA."
        )
    lines.append(_FOOTER)
    return "\n".join(lines)


def render_flow_updated(
    counts: PrismaCounts,
    *,
    previous_included: int,
    new_included: int,
    dropped_from_previous: int = 0,
) -> str:
    """Flow diagram para **revisiones actualizadas** (plantilla v3 · living review).

    Se alimenta de la memoria del investigador (``--brain``): la corrida previa
    aporta la columna "estudios incluidos en la versión anterior" y esta corrida
    los nuevos; el total consolida ambos (menos los retirados).
    """
    total = previous_included - dropped_from_previous + new_included
    lines = [
        "```mermaid",
        "flowchart TB",
        '    subgraph PREV["Estudios previos"]',
        f'        P["Estudios incluidos en la versión anterior (n = {previous_included})"]',
        "    end",
        '    subgraph NEW["Identificación de nuevos estudios (esta corrida)"]',
        f'        A["Registros identificados (n = {counts.identified})"]',
        f'        C["Registros cribados (n = {counts.screened})"]',
        f'        E["Informes evaluados (n = {counts.fulltext_assessed})"]',
        f'        N["Estudios nuevos incluidos (n = {new_included})"]',
        "        A --> C",
        "        C --> E",
        "        E --> N",
        "    end",
        '    subgraph TOT["Incluidos (acumulado)"]',
        f'        T["Total de estudios incluidos en la revisión (n = {total})'
        + (
            f"<br/>Retirados de la versión anterior (n = {dropped_from_previous})"
            if dropped_from_previous
            else ""
        )
        + '"]',
        "    end",
        "    P --> T",
        "    N --> T",
        "```",
        "",
        "> Plantilla oficial v3 (revisiones actualizadas) alimentada por la memoria "
        "del investigador (living review).",
        _FOOTER,
    ]
    return "\n".join(lines)


def render_flow_markdown(counts: PrismaCounts) -> str:
    """Renderiza los conteos como tabla Markdown (todas las cajas oficiales)."""
    rows: list[tuple[str, object]] = [
        ("Identificados", counts.identified),
    ]
    for db, n in sorted(counts.identified_by_source.items()):
        rows.append((f"— identificados en {db}", n))
    rows += [
        ("Duplicados eliminados", counts.duplicates_removed),
        ("Marcados inelegibles por automatización (pre-cribado)", counts.removed_automation),
        ("Eliminados por otras razones (pre-cribado)", counts.removed_other),
        ("Cribados (T/A)", counts.screened),
        ("Excluidos en T/A", counts.excluded_ta),
    ]
    if counts.excluded_ta_human is not None or counts.excluded_ta_ai is not None:
        rows += [
            ("— excluidos por humano", counts.excluded_ta_human or 0),
            ("— excluidos por IA", counts.excluded_ta_ai or 0),
        ]
    rows += [
        ("Informes buscados para recuperación", counts.fulltext_sought),
        ("Informes no recuperados", counts.fulltext_not_retrieved),
        ("Informes evaluados para elegibilidad", counts.fulltext_assessed),
    ]
    if counts.fulltext_rescued:
        rows.append(("— rescatados por el revisor", counts.fulltext_rescued))
    rows += [
        ("Excluidos en elegibilidad", counts.excluded_ft),
        ("— excluidos por humano (elegibilidad)", counts.excluded_ft_human),
        ("— excluidos por IA (elegibilidad)", counts.excluded_ft_ai),
    ]
    for reason, n in sorted(counts.ft_exclusion_reasons.items(), key=lambda kv: (-kv[1], kv[0])):
        rows.append((f"— razón: {reason}", n))
    rows.append(("Incluidos", counts.included))
    lines = ["| Etapa | n |", "|---|---|"]
    lines += [f"| {label} | {value} |" for label, value in rows]
    return "\n".join(lines)
````

- [ ] **Step 4: CSV y métodos.** En `revisia/exports/interop.py`, sustituir

```python
        "dbr_sought_reports": counts.fulltext_assessed,
        "dbr_notretrieved_reports": 0,
        "dbr_assessed": counts.fulltext_assessed,
```

por

```python
        # Cajas de texto completo con los conteos reales (auditoría 2026-09-03,
        # M11: `dbr_notretrieved_reports` era un 0 literal).
        "dbr_sought_reports": counts.fulltext_sought,
        "dbr_notretrieved_reports": counts.fulltext_not_retrieved,
        "dbr_assessed": counts.fulltext_assessed,
```

En `revisia/exports/methods.py`, sustituir

```python
        f"Flujo PRISMA: identificados={counts.identified} · duplicados={counts.duplicates_removed} "
        f"· cribados={counts.screened} · texto completo={counts.fulltext_assessed} "
        f"· incluidos={counts.included}.",
```

por

```python
        f"Flujo PRISMA: identificados={counts.identified} · duplicados={counts.duplicates_removed} "
        f"· cribados={counts.screened} · buscados a texto completo={counts.fulltext_sought} "
        f"· no recuperados={counts.fulltext_not_retrieved} "
        f"· evaluados para elegibilidad={counts.fulltext_assessed} "
        f"· incluidos={counts.included}. Un informe sin texto completo no se evalúa "
        "(PRISMA 2020: cuenta como no recuperado).",
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_flow_oficial_y_check.py tests/test_interop.py tests/test_coverage_gaps.py tests/test_export_document.py -v`
Expected: PASS todos.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 373 recogidos (el pipeline aún pasa `fulltext_abstract_only`; el validador lo descarta).

Run: `grep -rn "fulltext_abstract_only" revisia tests`
Expected: en `revisia/`, solo `orchestration/pipeline.py` (lo quita la Tarea 12) y el validador de `exports/prisma_flow.py` con su docstring; en `tests/`, solo `tests/test_export_document.py` (el `_MANIFEST` antiguo y el test que lo lee).

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/exports/prisma_flow.py revisia/exports/interop.py revisia/exports/methods.py tests/test_flow_oficial_y_check.py tests/test_interop.py tests/test_coverage_gaps.py tests/test_export_document.py
git commit -m "feat(prisma): cajas de informes buscados, no recuperados y evaluados (M11)" -m "El diagrama y su tabla siguen la plantilla PRISMA 2020: buscados -> no recuperados / evaluados, con rescatados por el revisor si los hay y exclusiones en elegibilidad por humano/IA. Se retira PrismaCounts.fulltext_abstract_only; un model_validator lee los manifiestos v0.7 sin inventar (buscados = evaluados, no recuperados = 0). El CSV PRISMA2020 lleva dbr_sought/notretrieved/assessed reales y metodologia.md informa de los tres. Auditoría 2026-09-03, M11; D2, D13." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Lista 16b de informes excluidos (`compute_ft_excluded`, `render_excluded_reports`)

**Files:**
- Modify: `revisia/exclusions.py` (imports l.10-14; constante; función nueva al final)
- Modify: `revisia/exports/prisma_flow.py` (import bajo `TYPE_CHECKING`; funciones nuevas al final)
- Modify: `revisia/exports/__init__.py` (import y `__all__`)
- Modify: `revisia/exports/checklist.py:57` (evidencia del ítem 16)
- Modify: `tests/test_coverage_gaps.py` (imports l.5-14; test nuevo al final)

**Interfaces:**
- Consumes: `ExcludedReport` (Tarea 1); `ScreeningDecision` con `human_reason` (Tarea 3); `SearchRecord`.
- Produces:
  - `revisia.exclusions.RAZON_NO_ESPECIFICADA: str = "criterio no especificado"`
  - `revisia.exclusions.compute_ft_excluded(decisions: Iterable[ScreeningDecision], records: Iterable[SearchRecord]) -> list[ExcludedReport]`: uno por decisión con `final_label or human_label or ensemble_label == "exclude"`, en el orden de `decisions`; si `human_label == "exclude"`, `reason = human_reason` (o la constante si está vacía) y `reason_source="human"`; si no, el primer `criteria_violated` de los votos (o la constante) y `reason_source="ai"`; `title`/`year`/`doi` del registro (si falta, `title=record_id`).
  - `revisia.exports.prisma_flow.render_excluded_reports(reports: list[ExcludedReport]) -> str` (reexportada en `revisia.exports`): Markdown con cabecera 16b y tabla `| Informe | Año | DOI | Razón | Origen |`, celdas en una línea con `|` escapado, origen `humano`/`IA`; sin informes, un texto en cursiva.
  - El ítem 16 de `render_prisma_2020_checklist()` cita `deliverable/excluidos_texto_completo.md (16b)`.

- [ ] **Step 1: Test que falla.** En `tests/test_coverage_gaps.py`, sustituir

```python
from revisia.config import ReviewProtocol
from revisia.exclusions import compute_exclusion_breakdown
from revisia.exports import PrismaCounts, render_methods
```

por

```python
from revisia.config import ReviewProtocol
from revisia.exclusions import compute_exclusion_breakdown, compute_ft_excluded
from revisia.exports import (
    PrismaCounts,
    render_excluded_reports,
    render_methods,
    render_prisma_2020_checklist,
)
```

y `from revisia.schemas.screening import ScreeningDecision` por `from revisia.schemas.screening import ScreeningDecision, ScreeningVote`. Añadir al final:

```python


def test_excluidos_16b_con_razon_y_origen() -> None:
    def ft(rid: str, ia: str, violados: list[str], humano=None, razon=None):
        return ScreeningDecision(
            record_id=rid,
            phase="fulltext",
            fulltext_status="retrieved",
            votes=[
                ScreeningVote(model="fake:x", label=ia, confidence=0.9, criteria_violated=violados)
            ],
            ensemble_label=ia,
            human_label=humano,
            human_reason=razon,
            final_label=humano or ia,
        )

    records = [
        SearchRecord(record_id="10.1/a", title="Estudio A | piloto", year=2021, doi="10.1/a"),
        SearchRecord(record_id="b", title="Estudio B"),
        SearchRecord(record_id="c", title="Estudio C"),
        SearchRecord(record_id="d", title="Estudio D"),
    ]
    decisions = [
        ft("10.1/a", "exclude", ["población incorrecta", "diseño"]),  # IA, primer criterio
        ft("b", "exclude", []),  # IA sin criterio
        ft("c", "include", [], humano="exclude", razon="sin grupo control"),  # humano
        ft("d", "include", []),  # incluido: no aparece
        ScreeningDecision(record_id="e", phase="fulltext", fulltext_status="not_retrieved"),
    ]
    reports = compute_ft_excluded(decisions, records)
    assert [(r.record_id, r.reason, r.reason_source) for r in reports] == [
        ("10.1/a", "población incorrecta", "ai"),
        ("b", "criterio no especificado", "ai"),
        ("c", "sin grupo control", "human"),
    ]
    assert (reports[0].year, reports[0].doi) == (2021, "10.1/a")

    md = render_excluded_reports(reports)
    assert "PRISMA 2020, ítem 16b" in md
    assert "| Estudio A \\| piloto (`10.1/a`) | 2021 | 10.1/a | población incorrecta | IA |" in md
    assert "| Estudio C (`c`) | — | — | sin grupo control | humano |" in md
    assert "ningún informe excluido" in render_excluded_reports([])
    assert "excluidos_texto_completo.md (16b)" in render_prisma_2020_checklist()
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_coverage_gaps.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'compute_ft_excluded' from 'revisia.exclusions'`.

- [ ] **Step 3: `compute_ft_excluded`** en `revisia/exclusions.py`. Sustituir

```python
from collections.abc import Iterable

from pydantic import BaseModel

from revisia.schemas.screening import ScreeningDecision
```

por

```python
from collections.abc import Iterable

from pydantic import BaseModel

from revisia.schemas.artifacts import ExcludedReport
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision

# Razón cuando ni el humano ni la IA nombraron un criterio.
RAZON_NO_ESPECIFICADA = "criterio no especificado"
```

y añadir al final del fichero:

```python


def compute_ft_excluded(
    decisions: Iterable[ScreeningDecision], records: Iterable[SearchRecord]
) -> list[ExcludedReport]:
    """Informes excluidos en elegibilidad con su razón y su origen (PRISMA 2020, 16b).

    La razón es la humana si el humano excluyó (``human_label == "exclude"``,
    con su ``human_reason``); si no, el primer ``criteria_violated`` de la IA o
    "criterio no especificado". ``reason_source`` lo dice explícitamente
    (PRISMA-trAIce R1): ``ft_exclusion_reasons`` se deriva de esta lista para
    que el diagrama, la tabla 16b y el auditor cuenten lo mismo.
    """
    by_id = {r.record_id: r for r in records}
    reports: list[ExcludedReport] = []
    for decision in decisions:
        final = decision.final_label or decision.human_label or decision.ensemble_label
        if final != "exclude":
            continue
        if decision.human_label == "exclude":
            reason = (decision.human_reason or "").strip() or RAZON_NO_ESPECIFICADA
            source = "human"
        else:
            violated = [c for v in decision.votes for c in v.criteria_violated]
            reason = violated[0] if violated else RAZON_NO_ESPECIFICADA
            source = "ai"
        record = by_id.get(decision.record_id)
        reports.append(
            ExcludedReport(
                record_id=decision.record_id,
                title=record.title if record is not None else decision.record_id,
                year=record.year if record is not None else None,
                doi=record.doi if record is not None else None,
                reason=reason,
                reason_source=source,
            )
        )
    return reports
```

- [ ] **Step 4: `render_excluded_reports`** en `revisia/exports/prisma_flow.py`. Sustituir

```python
from pydantic import BaseModel, Field, model_validator
```

por

```python
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from revisia.schemas.artifacts import ExcludedReport
```

y añadir al final del fichero:

```python


_ORIGEN = {"human": "humano", "ai": "IA"}


def _md_cell(value: object) -> str:
    """Celda de tabla Markdown: una sola línea y con ``|`` escapado."""
    return " ".join(str(value).split()).replace("|", "\\|")


def render_excluded_reports(reports: list[ExcludedReport]) -> str:
    """Informes excluidos en elegibilidad con su razón (PRISMA 2020, ítem 16b).

    Va a ``deliverable/excluidos_texto_completo.md``. Cada fila dice si la razón
    la dio un humano o la IA (PRISMA-trAIce R1): una exclusión de la IA que
    nadie revisó no se presenta como juicio humano.
    """
    lines = [
        "# Informes excluidos tras evaluar el texto completo",
        "",
        "PRISMA 2020, ítem 16b: informes evaluados para elegibilidad y excluidos, "
        "con su razón y quién la dio (PRISMA-trAIce R1).",
        "",
    ]
    if not reports:
        lines.append("_(ningún informe excluido en la evaluación de elegibilidad)_")
        return "\n".join(lines) + "\n"
    lines += ["| Informe | Año | DOI | Razón | Origen |", "|---|---|---|---|---|"]
    for rep in reports:
        year = "—" if rep.year is None else str(rep.year)
        doi = _md_cell(rep.doi) if rep.doi else "—"
        lines.append(
            f"| {_md_cell(rep.title)} (`{_md_cell(rep.record_id)}`) | {year} | {doi} "
            f"| {_md_cell(rep.reason)} | {_ORIGEN[rep.reason_source]} |"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Reexportar y checklist.** En `revisia/exports/__init__.py`, añadir `render_excluded_reports,` a la lista importada de `revisia.exports.prisma_flow` (entre `PrismaCounts,` y `render_flow_diagram,`) y `"render_excluded_reports",` a `__all__` (entre `"render_bibtex",` y `"render_extraction_table",`). En `revisia/exports/checklist.py`, sustituir

```python
    16: "Diagrama de flujo PRISMA en deliverable/prisma_flow.md.",
```

por

```python
    16: (
        "Diagrama de flujo PRISMA en deliverable/prisma_flow.md (16a); informes "
        "excluidos con su razón en deliverable/excluidos_texto_completo.md (16b)."
    ),
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_coverage_gaps.py -v -W error::SyntaxWarning`
Expected: PASS todos.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 374 recogidos.

- [ ] **Step 7: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 8: Commit**

```bash
git add revisia/exclusions.py revisia/exports/prisma_flow.py revisia/exports/__init__.py revisia/exports/checklist.py tests/test_coverage_gaps.py
git commit -m "feat(prisma): lista 16b de informes excluidos con razón y origen" -m "compute_ft_excluded deriva, de las decisiones de texto completo, cada informe excluido con su razón (la humana si excluyó el humano; si no, el primer criterio violado de la IA) y reason_source explícito (PRISMA-trAIce R1). render_excluded_reports la vuelca a Markdown; el ítem 16 del checklist la cita. Spec 2026-10-04 §6; PRISMA 2020 16b." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Pipeline FT estricto (no recuperados sin IA, conteos y entregables)

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (imports l.12-13, l.28-31, l.56-61; bloque FT l.262-307; razones de exclusión l.317-323; conteos l.474-477; entregables tras `prisma_flow.md`, l.488)
- Modify: `tests/test_pipeline_fake.py` (imports l.10-19; `test_pipeline_end_to_end_offline` l.51-72; dos tests nuevos al final)

**Interfaces:**
- Consumes: `FullText.reason/detail` (Tarea 9), `PrismaCounts` nuevo (Tarea 10), `compute_ft_excluded`, `render_excluded_reports` (Tarea 11), `RetrievalOutcome` (Tarea 1), `ScriptedProvider`, `fetch_disponible`, `fetch_no_disponible` (Tarea 4).
- Produces (lo que PR-C convierte en diario y PR-D en HITL por registro):
  - Un registro con `available=False` no se criba con IA: `ScreeningDecision(record_id, phase="fulltext", fulltext_status="not_retrieved", votes=[], ensemble_label=None)` con `final_label=None`; no entra en `included`, extracción ni RoB.
  - Los recuperados se criban como hoy, con `fulltext_status="retrieved"`; `fulltexts` solo guarda textos recuperados.
  - `04_fulltext/retrieval.json`: `list[{"record_id": str, **RetrievalOutcome.model_dump()}]` en el orden de `passed_ta` (`reason = ft.reason or "no_disponible"`; en los recuperados, `n_chars` y `text_sha256 = sha256_text(text)`; `text_file=None` hasta la caché de PR-C).
  - `04_fulltext/excluded.json`: `[ExcludedReport.model_dump()]` y `deliverable/excluidos_texto_completo.md`, tras el gate FT.
  - Payload del gate FT: `{n_buscados, n_no_recuperados, n_evaluados, n_incluidos, n_excluidos}`.
  - `PrismaCounts(fulltext_sought=len(passed_ta), fulltext_not_retrieved=nr, fulltext_rescued=0, fulltext_assessed=len(passed_ta) - nr, excluded_ft_human=#human, excluded_ft_ai=#ai, ft_exclusion_reasons=Counter(reason))`; un `unclear` de FT sigue contando como incluido hasta PR-D.

- [ ] **Step 1: Tests que fallan.** En `tests/test_pipeline_fake.py`, sustituir los imports

```python
import yaml

from revisia.audit import run_audit
from revisia.config import load_protocol
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
```

por

```python
import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible

from revisia.audit import run_audit
from revisia.config import load_protocol
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
```

En `test_pipeline_end_to_end_offline`, sustituir

```python
        auto_approve=True,
        search_fn=_fake_search,
    )

    assert result.status == "completed"
    assert result.counts.identified == 3
    assert result.counts.duplicates_removed == 1
    assert result.counts.screened == 2
    assert result.counts.included == 2  # el proveedor fake incluye todo
```

por

```python
        auto_approve=True,
        search_fn=_fake_search,
        # PRISMA estricto (D2): sin texto completo nada llega a extracción, y los
        # registros simulados no tienen texto en abierto.
        fetch_fn=fetch_disponible,
    )

    assert result.status == "completed"
    assert result.counts.identified == 3
    assert result.counts.duplicates_removed == 1
    assert result.counts.screened == 2
    assert result.counts.fulltext_sought == 2
    assert result.counts.fulltext_not_retrieved == 0
    assert result.counts.fulltext_assessed == 2
    assert result.counts.included == 2  # el proveedor fake incluye todo
```

y tras `assert (deliverable / "checklist_traice.md").exists()` añadir

```python
    assert (deliverable / "excluidos_texto_completo.md").exists()
```

Añadir al final del fichero:

```python


def test_ft_no_recuperado_no_se_criba_con_ia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M11/D2: antes, un registro sin texto completo se cribaba con el abstract y
    # contaba como evaluado.
    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST-NR")
    result = run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        max_results=10,
        auto_approve=True,
        search_fn=_fake_search,
        fetch_fn=fetch_no_disponible(["rec-2"]),
    )

    assert result.status == "completed"
    c = result.counts
    assert (c.screened, c.fulltext_sought, c.fulltext_not_retrieved) == (2, 2, 1)
    assert (c.fulltext_assessed, c.included) == (1, 1)
    # El proveedor de FT solo vio el registro recuperado.
    prompts_ft = [p for p in proveedor.prompts if "TEXTO COMPLETO" in p]
    assert len(prompts_ft) == 1
    assert "Active learning with ASReview" not in prompts_ft[0]

    run = ctx.run_dir
    ft = json.loads((run / "04_fulltext" / "decisions.json").read_text(encoding="utf-8"))
    no_recuperado = next(d for d in ft if d["record_id"] == "rec-2")
    assert no_recuperado["fulltext_status"] == "not_retrieved"
    assert no_recuperado["votes"] == []
    assert no_recuperado["ensemble_label"] is None
    assert no_recuperado["final_label"] is None
    recuperacion = json.loads((run / "04_fulltext" / "retrieval.json").read_text(encoding="utf-8"))
    assert {r["record_id"]: r["reason"] for r in recuperacion} == {
        "rec-1": None,
        "rec-2": "no_disponible",
    }
    # No entra en extracción ni en RoB.
    extracciones = json.loads(
        (run / "05_extraction" / "extractions.json").read_text(encoding="utf-8")
    )
    assert set(extracciones) == {"rec-1"}
    flujo = (run / "deliverable" / "prisma_flow.md").read_text(encoding="utf-8")
    assert "Informes no recuperados (n = 1)" in flujo


def test_ft_exclusion_ia_llega_a_16b(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = ScriptedProvider(criterio_exclusion="población incorrecta")
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)

    def fetch(record: SearchRecord):
        ft = fetch_disponible(record)
        if record.record_id == "rec-2":
            ft.text += " Este estudio es irrelevante para la pregunta."
        return ft

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST-16B")
    result = run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=_fake_search, fetch_fn=fetch
    )
    c = result.counts
    assert (c.excluded_ft, c.excluded_ft_ai, c.excluded_ft_human) == (1, 1, 0)
    assert c.ft_exclusion_reasons == {"población incorrecta": 1}
    excluidos = json.loads(
        (ctx.run_dir / "04_fulltext" / "excluded.json").read_text(encoding="utf-8")
    )
    assert [(e["record_id"], e["reason_source"]) for e in excluidos] == [("rec-2", "ai")]
    md = (ctx.run_dir / "deliverable" / "excluidos_texto_completo.md").read_text(encoding="utf-8")
    assert "población incorrecta | IA |" in md
```

(`test_pipeline_pausa_sin_auto_approve`, `test_pipeline_ensemble_y_metricas`, `test_rejected_final_gate_is_not_completed` y `test_paused_run_final_gate_falla_en_auditoria` no cambian: sin `fetch_fn` todos los registros quedan no recuperados, sin red —sin `pmcid`, `oa_url` ni `mailto`—, y lo que afirman no depende de los incluidos.)

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_pipeline_fake.py -v`
Expected: FAIL `test_pipeline_end_to_end_offline` (falta `excluidos_texto_completo.md`), `test_ft_no_recuperado_no_se_criba_con_ia` (`(2, 2, 0) == (2, 2, 1)`: el no recuperado todavía se criba y cuenta como evaluado) y `test_ft_exclusion_ia_llega_a_16b` (`FileNotFoundError` de `04_fulltext/excluded.json`).

- [ ] **Step 3: Imports** en `revisia/orchestration/pipeline.py`. Sustituir

```python
from collections.abc import Callable
from dataclasses import dataclass, field
```

por

```python
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
```

sustituir

```python
from revisia.exclusions import compute_exclusion_breakdown
from revisia.exports import (
    PrismaCounts,
    render_bibtex,
```

por

```python
from revisia.exclusions import compute_exclusion_breakdown, compute_ft_excluded
from revisia.exports import (
    PrismaCounts,
    render_bibtex,
    render_excluded_reports,
```

y sustituir

```python
from revisia.orchestration.run_context import RunContext
from revisia.rag.embed import Embedder, HashEmbedder
from revisia.schemas.effects import EffectInput
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.records import SearchRecord
from revisia.schemas.rob import RoBAssessment
```

por

```python
from revisia.orchestration.run_context import RunContext
from revisia.provenance.runmeta import sha256_text
from revisia.rag.embed import Embedder, HashEmbedder
from revisia.schemas.artifacts import RetrievalOutcome
from revisia.schemas.effects import EffectInput
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.records import SearchRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision
```

- [ ] **Step 4: Bloque FT** (desde `# ── 5. Texto completo + cribado a full-text (A0) ──` hasta el cierre de `ft_gate = review_gate(...)`, l.262-303). Sustituir

```python
    # ── 5. Texto completo + cribado a full-text (A0) ────────────────────
    fetch = fetch_fn or (lambda rec: fulltext_agent.fetch_fulltext(rec, mailto=mailto))
    ft_cfg = protocol.provider_for("screening_ft")
    ft_provider = build_provider(ft_cfg)
    ft_model = f"{ft_cfg.provider}:{ft_cfg.model}"
    fulltexts: dict[str, str] = {}
    ft_decisions = []
    ft_abstract_only = 0
    for record in passed_ta:
        ft = fetch(record)
        if not ft.available:
            ft_abstract_only += 1
        fulltexts[record.record_id] = ft.text or (record.abstract or "")
        decision, meta = screening_ft_agent.screen_fulltext(
```

por

```python
    # ── 5. Texto completo + cribado a full-text (A0) ────────────────────
    # PRISMA estricto (D2; auditoría 2026-09-03, M11): un informe sin texto
    # completo NO se criba con IA (antes se cribaba con el abstract y contaba
    # como evaluado). Queda como "no recuperado", con su motivo en
    # 04_fulltext/retrieval.json, y no llega a extracción.
    fetch = fetch_fn or (lambda rec: fulltext_agent.fetch_fulltext(rec, mailto=mailto))
    ft_cfg = protocol.provider_for("screening_ft")
    ft_provider = build_provider(ft_cfg)
    ft_model = f"{ft_cfg.provider}:{ft_cfg.model}"
    fulltexts: dict[str, str] = {}
    ft_decisions: list[ScreeningDecision] = []
    retrieval: list[dict] = []
    for record in passed_ta:
        ft = fetch(record)
        if not ft.available:
            # Un fetch_fn inyectado puede no dar motivo: el genérico es no_disponible.
            outcome = RetrievalOutcome(
                available=False,
                source_url=ft.source_url,
                reason=ft.reason or "no_disponible",
                detail=ft.detail,
            )
            retrieval.append({"record_id": record.record_id, **outcome.model_dump()})
            ft_decisions.append(
                ScreeningDecision(
                    record_id=record.record_id,
                    phase="fulltext",
                    fulltext_status="not_retrieved",
                    votes=[],
                    ensemble_label=None,
                )
            )
            continue
        outcome = RetrievalOutcome(
            available=True,
            source_url=ft.source_url,
            n_chars=len(ft.text),
            text_sha256=sha256_text(ft.text),
        )
        retrieval.append({"record_id": record.record_id, **outcome.model_dump()})
        fulltexts[record.record_id] = ft.text
        decision, meta = screening_ft_agent.screen_fulltext(
```

Después, sustituir

```python
        decision.final_label = decision.human_label or decision.ensemble_label
        ft_decisions.append(decision)
        run_ctx.record_meta(meta)
    run_ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])

    included_ids = {d.record_id for d in ft_decisions if d.final_label in {"include", "unclear"}}
    excluded_ft = sum(1 for d in ft_decisions if d.final_label == "exclude")

    ft_gate = review_gate(
        stage="screening_ft",
        autonomy=protocol.autonomy_for("screening_ft"),
        run_ctx=run_ctx,
        review_payload={
            "n_evaluados": len(passed_ta),
            "n_incluidos": len(included_ids),
            "n_excluidos": excluded_ft,
        },
```

por

```python
        decision.fulltext_status = "retrieved"
        decision.final_label = decision.human_label or decision.ensemble_label
        ft_decisions.append(decision)
        run_ctx.record_meta(meta)
    run_ctx.write_json("04_fulltext/retrieval.json", retrieval)
    run_ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])

    not_retrieved = sum(1 for d in ft_decisions if d.fulltext_status == "not_retrieved")
    # Hasta PR-D un `unclear` de FT sigue pasando (lo resolverá un humano, D1).
    included_ids = {d.record_id for d in ft_decisions if d.final_label in {"include", "unclear"}}
    excluded_ft = sum(1 for d in ft_decisions if d.final_label == "exclude")

    ft_gate = review_gate(
        stage="screening_ft",
        autonomy=protocol.autonomy_for("screening_ft"),
        run_ctx=run_ctx,
        review_payload={
            "n_buscados": len(passed_ta),
            "n_no_recuperados": not_retrieved,
            "n_evaluados": len(passed_ta) - not_retrieved,
            "n_incluidos": len(included_ids),
            "n_excluidos": excluded_ft,
        },
```

- [ ] **Step 5: Razones, conteos y entregable.** Sustituir

```python
    # Razones de exclusión en elegibilidad (cajas "Reason 1..n" del flow oficial).
    ft_exclusion_reasons: dict[str, int] = {}
    for d in ft_decisions:
        if d.final_label == "exclude":
            violated = [c for v in d.votes for c in v.criteria_violated]
            reason = violated[0] if violated else "criterio no especificado"
            ft_exclusion_reasons[reason] = ft_exclusion_reasons.get(reason, 0) + 1
```

por

```python
    # Informes excluidos en elegibilidad (16b) y sus razones (cajas "Reason 1..n"
    # del flow oficial): una sola lista para el diagrama, la tabla y el auditor.
    excluded_reports = compute_ft_excluded(ft_decisions, passed_ta)
    run_ctx.write_json("04_fulltext/excluded.json", [r.model_dump() for r in excluded_reports])
    ft_exclusion_reasons = dict(Counter(r.reason for r in excluded_reports))
```

En `counts = PrismaCounts(...)`, sustituir

```python
        fulltext_assessed=len(passed_ta),
        fulltext_abstract_only=ft_abstract_only,
        excluded_ft=excluded_ft,
        ft_exclusion_reasons=ft_exclusion_reasons,
```

por

```python
        fulltext_sought=len(passed_ta),
        fulltext_not_retrieved=not_retrieved,
        fulltext_rescued=0,  # los rescates humanos llegan con el HITL por registro (PR-D)
        fulltext_assessed=len(passed_ta) - not_retrieved,
        excluded_ft=excluded_ft,
        excluded_ft_human=sum(1 for r in excluded_reports if r.reason_source == "human"),
        excluded_ft_ai=sum(1 for r in excluded_reports if r.reason_source == "ai"),
        ft_exclusion_reasons=ft_exclusion_reasons,
```

Y sustituir

```python
    (deliverable / "risk_of_bias.md").write_text(
```

por

```python
    (deliverable / "excluidos_texto_completo.md").write_text(
        render_excluded_reports(excluded_reports), encoding="utf-8"
    )
    (deliverable / "risk_of_bias.md").write_text(
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_pipeline_fake.py -v`
Expected: PASS, 7 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, **376 recogidos**.

Run: `grep -rn "fulltext_abstract_only\|ft_abstract_only" revisia`
Expected: solo `revisia/exports/prisma_flow.py` (el `data.pop("fulltext_abstract_only", None)` del validador y su docstring).

- [ ] **Step 7: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 8: Commit**

```bash
git add revisia/orchestration/pipeline.py tests/test_pipeline_fake.py
git commit -m "feat(pipeline): FT con PRISMA estricto: los no recuperados no se criban con IA (M11)" -m "Un registro sin texto completo queda como ScreeningDecision(fulltext_status=not_retrieved, votes=[], ensemble_label=None), no se criba ni entra en extracción. 04_fulltext/retrieval.json guarda el motivo; 04_fulltext/excluded.json y deliverable/excluidos_texto_completo.md, la lista 16b. PrismaCounts con buscados, no recuperados, evaluados y exclusiones en elegibilidad por humano/IA. Los tests de extremo a extremo inyectan fetch_fn. Auditoría 2026-09-03, M11; D2." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Las corridas no se versionan (`.gitignore`, D11)

**Files:**
- Modify: `.gitignore:14-21`

**Interfaces:** ninguna de código. Tarea sin test de pytest: la verificación es `git check-ignore`.

- [ ] **Step 1: Reproducir el estado actual** (evidencia antes del cambio).

Run: `git check-ignore -v runs/demo-20261004-120000/manifest.yml; git ls-files runs | wc -l`
Expected: `.gitignore:19:runs/*/	runs/demo-20261004-120000/manifest.yml` (la negación `!runs/*/manifest.yml` no re-incluye nada) y `0`.

- [ ] **Step 2: Implementar.** En `.gitignore`, sustituir

```gitignore
# Outputs de ejecuciones: se ignoran salvo el manifest y los entregables,
# que son los artefactos reproducibles que SÍ se versionan/comparten.
# OJO: estas negaciones son inoperantes porque `runs/*/` excluye el directorio
# padre (git no re-incluye hijos de un directorio ignorado). Hoy ninguna corrida
# se versiona. Decidir qué se versiona de una corrida es trabajo de la Ola 1.
runs/*/
!runs/*/manifest.yml
!runs/*/deliverable/
```

por

```gitignore
# Corridas (`runs/<slug>-<fecha>/`): NO se versionan en el repo del motor (D11
# de la Ola 1; auditoría 2026-09-03, M23). Una corrida pertenece a su revisión,
# no al motor: deposítala completa (manifest.yml, decisions_ledger.jsonl,
# deliverable/…) en OSF/Zenodo o junto al protocolo. Las antiguas negaciones
# `!runs/*/manifest.yml` y `!runs/*/deliverable/` nunca funcionaron (git no
# re-incluye hijos de un directorio ignorado): esto no deja fuera nada que antes
# se versionara.
runs/
```

- [ ] **Step 3: Verificar**

Run: `git check-ignore -v runs/demo-20261004-120000/manifest.yml runs/demo-20261004-120000/deliverable/prisma_flow.md`
Expected: las dos rutas con `.gitignore:21:runs/`.

Run: `git status --short`
Expected: solo ` M .gitignore`.

Run: `uv run pytest -p no:cacheprovider -q`
Expected: PASS, 376 recogidos.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore(git): las corridas no se versionan en el repo del motor (M23)" -m "runs/ se ignora entero, con un comentario que lo explica: una corrida pertenece a su revisión y se deposita en OSF/Zenodo o junto al protocolo. Las negaciones anteriores (!runs/*/manifest.yml) nunca funcionaron, así que nada que antes se versionara queda fuera. Auditoría 2026-09-03, M23; D11." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Integración de A y B (controlador)

### Task 14: Integración de PR-A (`C:\revisia-wt\a`)

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`: `### Added`; secciones nuevas `### Changed` y `### Cambios incompatibles` antes de `## [0.7.0]`)
- Modify: `README.md` (quickstart, pasos 2 y 3; tabla "Defaults de buenas prácticas")
- Modify: `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md` (§14, filas 5-8)

**Interfaces:** ninguna de código. Deja publicada `feat/ola1-preflight` y abierta PR-A con base `feat/ola1-contratos`.

- [ ] **Step 1: Al día con PR-0.** Si `feat/ola1-contratos` recibió commits después de crear el worktree (correcciones de revisión de PR-0):

```bash
git -C C:/revisia-wt/a fetch origin
git -C C:/revisia-wt/a rebase feat/ola1-contratos
```

Expected: sin conflictos (PR-A no toca ficheros de PR-0 salvo para importarlos).

- [ ] **Step 2: CHANGELOG.** En `CHANGELOG.md`, sustituir

```
  `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md`.

### Fixed
```

por

```
  `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md`.
- **Preflight sin red** (`revisia/llm/preflight.py`; auditoría 2026-09-03, M6):
  antes de empezar, `revisia validate` y `revisia run` comprueban proveedor
  conocido, SDK instalado (con el `uv sync --extra …` que falta), API key en el
  entorno, binario `claude`, `effort` solo en `claude_code`, etapas sin
  proveedor, bases desconocidas, cadenas de búsqueda ausentes, modelos
  retirados y `httpx`. `run` lo hace antes de crear la carpeta de la corrida.
- `revisia` carga `.env` (desde el directorio actual hacia arriba) sin
  sobrescribir las variables ya definidas: el README pedía la API key ahí y
  ningún módulo lo leía.

### Fixed
```

y sustituir

```
- El `effort` de `claude_code` se valida al construir el proveedor.

## [0.7.0] · 2026-09-28
```

por

```
- El `effort` de `claude_code` se valida al construir el proveedor.

### Changed
- `MANUAL_ONLY` incluye CINAHL, Cochrane/CENTRAL, ProQuest, EconLit, JSTOR,
  IEEE Xplore, ACM, ScienceDirect, EBSCO y Ovid: se incorporan por importación
  RIS/BibTeX y el preflight no las da por desconocidas.

### Cambios incompatibles
- `revisia validate` y `revisia run` salen con código 2 ante cualquier error de
  preflight. Antes `validate` devolvía 0 con "(sin proveedor)" o sin la API key,
  y el fallo aparecía a mitad de corrida.

## [0.7.0] · 2026-09-28
```

- [ ] **Step 3: README.** En el quickstart, sustituir

```
cp .env.example .env   # edita .env y pon tu API key (default: Gemini, tier gratis)
```

por

```
cp .env.example .env   # edita .env y pon tu API key (default: Gemini, tier gratis)
#    revisia lee ese .env (desde la carpeta actual hacia arriba) sin pisar variables ya exportadas.
```

y

```
#     edita protocols/mi-revision/protocol.yml y preregistra (PRISMA-P)
```

por

```
#     edita protocols/mi-revision/protocol.yml y preregistra (PRISMA-P)
uv run revisia validate protocols/mi-revision
#     preflight sin red: proveedor, SDK, API key, bases y modelos (código 2 si algo falla)
```

En la tabla de "Defaults de buenas prácticas", tras la fila que empieza por `| Un solo cribador / sin kappa |`, añadir:

```
| Corrida que falla a mitad por configuración | `validate` y `run` hacen un **preflight sin red** (proveedor, SDK, API key, binario `claude`, etapas sin proveedor, bases desconocidas, cadenas ausentes, modelos retirados, `httpx`) y salen con código 2 antes de crear la carpeta de la corrida |
```

- [ ] **Step 4: Desviaciones en el spec.** En §14 del spec, añadir tras la fila 4:

```
| 5 | §5 `PreflightError` | `PreflightError(report)` guarda el informe en `.report`; su mensaje lista los errores | Plan PR-A |
| 6 | §5 `preflight()` | Los problemas idénticos de varias etapas se unen en uno (`where` combinado: "falta GEMINI_API_KEY" sale una vez). `stages_in_use` omite las etapas sin proveedor; el error lo emite `preflight`. Puntos de inyección `_default_find_spec`/`_default_which` para los tests del CLI | Plan PR-A |
| 7 | §5 tests existentes | Además de `tests/test_cli_validate.py:35,44,72`, cambian `tests/test_cli_errores.py:50,77` (`run` del demo): el venv de desarrollo no instala `httpx` y el demo usa OpenAlex, así que necesitan `find_spec` falso | Código real |
| 8 | §5 `context="resume"` | Se salta también la comprobación de `httpx`, que va con "bases y búsqueda". Si al reanudar queda recuperación de texto completo pendiente y falta `httpx`, esos registros quedarán como no recuperados con motivo `sin_httpx`; PR-C decide si lo convierte en aviso | Literal del spec |
```

- [ ] **Step 5: Commit de documentación.**

```bash
git -C C:/revisia-wt/a add CHANGELOG.md README.md docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md
git -C C:/revisia-wt/a commit -m "docs: CHANGELOG, README y desviaciones de PR-A (preflight)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Verificación completa** (en `C:\revisia-wt\a`).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 399 recogidos.

Run (3.11 y 3.12):

```bash
TMP="$(mktemp -d)"
for PY in 3.11 3.12; do
  uv venv -q --python "$PY" "$TMP/venv$PY"
  uv pip install -q --python "$TMP/venv$PY" pydantic pyyaml python-dotenv markdown httpx nh3 pytest
  PYTHONPATH=. "$TMP/venv$PY/Scripts/python" -m pytest -p no:cacheprovider -q
done
```

Expected: PASS en ambas.

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`
Expected: limpio.

Run (humo, sin red): `uv run revisia validate examples/demo-mini-review; echo "rc=$?"`
Expected: si el venv no tiene `httpx`, `rc=2` con `error [busqueda]: falta httpx (extra \`search\`)…`; con `uv sync --extra search`, `rc=0`. En ningún caso traceback.

- [ ] **Step 7: Publicar y abrir PR-A** (sin merge).

```bash
git -C C:/revisia-wt/a push -u origin feat/ola1-preflight
gh pr create --base feat/ola1-contratos --head feat/ola1-preflight --title "Ola 1 · PR-A: preflight sin red de proveedores y bases (M6)" --body "$(cat <<'EOF'
## Qué cierra

M6 de la auditoría 2026-09-03: una API key ausente para el cribado a texto completo se descubría después de gastar el cribado T/A, y `revisia validate` devolvía 0 con "(sin proveedor)". D10 del spec de la Ola 1.

## Qué cambia

- `revisia/llm/preflight.py`: proveedor conocido, SDK importable (con el `uv sync --extra …` sugerido), API key, binario `claude`, `effort` solo en `claude_code`, callback de `agent`, etapas sin proveedor, modelos retirados (absorbe `cli._retired_model_problems`), bases desconocidas, cadenas ausentes, importación manual, `httpx` y `--mailto`. `env`, `find_spec` y `which` inyectables.
- `revisia validate` y `revisia run` salen con 2 ante cualquier error de preflight; `run` lo comprueba antes de crear la carpeta de la corrida.
- `main` carga `.env` sin sobrescribir el entorno.
- `MANUAL_ONLY` gana las bases de suscripción comunes.

## Cambios incompatibles

`validate`/`run` salen con código 2 ante problemas que antes aparecían a mitad de corrida.

## Verificación

- `uv run pytest -p no:cacheprovider`: 399 recogidos, en verde.
- La misma suite en 3.11 y 3.12 con venv desechable: en verde.
- `ruff check`, `ruff format --check`, `black --check`, `uv lock --check`: limpios.

## Pila

`main` ← PR-0 ← **PR-A** ← PR-B ← PR-C ← PR-D ← PR-E. Base: `feat/ola1-contratos`. Al mergear PR-0, re-apuntar esta PR con `gh pr edit <n> --base main` antes de borrar la rama de PR-0, y cerrar/reabrir para el CI.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR.

---

### Task 15: Rebase de B sobre A e integración de PR-B (`C:\revisia-wt\b`)

**Files:**
- Modify: `CHANGELOG.md` (`### Added`, `### Fixed`, `### Changed`, `### Cambios incompatibles` de `## [Unreleased]`, ya con el texto de PR-A)
- Modify: `README.md` ("Salida", párrafos tras el manifiesto, árbol "Estructura")
- Modify: `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md` (§14, filas 9-13)

**Interfaces:** ninguna de código. Deja `feat/ola1-flujo-prisma` rebasada sobre `feat/ola1-preflight`, publicada y con PR-B abierta; es el punto de partida de PR-C (plan `2026-10-04-ola-1-b-reanudacion-hitl.md`).

- [ ] **Step 1: Rebase sobre A** (con PR-A ya integrada, Tarea 14).

```bash
git -C C:/revisia-wt/b rebase feat/ola1-preflight
```

Expected: sin conflictos (verificado en un prototipo: A y B tocan ficheros disjuntos; los de documentación solo los toca el integrador, y B aún no tiene commit de documentación).

Run (en `C:\revisia-wt\b`): `uv run pytest -p no:cacheprovider`
Expected: PASS, **411 recogidos** (330 + 34 de PR-0 + 35 de PR-A + 12 de PR-B).

- [ ] **Step 2: CHANGELOG.** En `CHANGELOG.md`, sustituir

```
  sobrescribir las variables ya definidas: el README pedía la API key ahí y
  ningún módulo lo leía.

### Fixed
```

por

```
  sobrescribir las variables ya definidas: el README pedía la API key ahí y
  ningún módulo lo leía.
- `deliverable/excluidos_texto_completo.md` y `04_fulltext/excluded.json`:
  informes excluidos al evaluar el texto completo, con su razón y su origen
  humano/IA (PRISMA 2020, ítem 16b; PRISMA-trAIce R1).
- `04_fulltext/retrieval.json`: por cada informe buscado, si se recuperó y, si
  no, por qué (`sin_url_oa`, `sin_httpx`, `error_http`, `texto_vacio`,
  `no_disponible`).

### Fixed
```

sustituir

```
- El `effort` de `claude_code` se valida al construir el proveedor.

### Changed
```

por

```
- El `effort` de `claude_code` se valida al construir el proveedor.
- CSV del paquete PRISMA2020: `dbr_notretrieved_reports` era un 0 literal y
  `dbr_sought_reports` copiaba los evaluados; ahora llevan los conteos reales
  (auditoría 2026-09-03, M11).

### Changed
```

sustituir

```
  RIS/BibTeX y el preflight no las da por desconocidas.

### Cambios incompatibles
```

por

```
  RIS/BibTeX y el preflight no las da por desconocidas.
- **Texto completo con PRISMA estricto** (auditoría 2026-09-03, M11): un
  registro sin texto completo recuperable ya no se criba con IA ni cuenta como
  evaluado; va a la caja "informes no recuperados". El diagrama, su tabla y
  `metodologia.md` informan de buscados, no recuperados y evaluados, y las
  exclusiones en elegibilidad se desglosan por humano/IA.
- `runs/` se ignora entero (M23): una corrida pertenece a su revisión, no al
  motor; se deposita en OSF/Zenodo o junto al protocolo. Las negaciones
  anteriores (`!runs/*/manifest.yml`) nunca funcionaron.

### Cambios incompatibles
```

y sustituir

```
  y el fallo aparecía a mitad de corrida.

## [0.7.0] · 2026-09-28
```

por

```
  y el fallo aparecía a mitad de corrida.
- Desaparece `PrismaCounts.fulltext_abstract_only`. Los manifiestos anteriores
  se siguen leyendo (buscados = evaluados, no recuperados = 0), así que
  `revisia export` funciona con corridas viejas.
- Los registros sin texto completo ya no llegan a extracción. Con el demo sin
  el extra `search` ni `--mailto` puede no quedar ningún estudio incluido.

## [0.7.0] · 2026-09-28
```

- [ ] **Step 3: README.** En "Salida", sustituir

```
- `prisma_flow.md` · diagrama de flujo con la estructura de la **plantilla
  oficial** PRISMA 2020: desglose por base, exclusiones **humano vs IA**
  (nota ** oficial · trAIce R1) y **razones de exclusión** en elegibilidad;
  con `--brain` y memoria previa se emite además `prisma_flow_updated.md`
  (plantilla v3 · living review)
```

por

```
- `prisma_flow.md` · diagrama de flujo con la estructura de la **plantilla
  oficial** PRISMA 2020: desglose por base, informes buscados / **no
  recuperados** / evaluados, exclusiones **humano vs IA** (nota ** oficial ·
  trAIce R1) y **razones de exclusión** en elegibilidad; con `--brain` y
  memoria previa se emite además `prisma_flow_updated.md` (plantilla v3 ·
  living review)
- `excluidos_texto_completo.md` · informes excluidos al evaluar el texto
  completo, con su razón y su origen humano/IA (PRISMA 2020, ítem 16b)
```

Tras el párrafo

```
…todo con un **manifiesto reproducible** (modelo, versión, seed, prompts
hash-eados, exclusiones humano/IA, acuerdo de extracción, decisiones con timestamp).
```

añadir:

```

> **Texto completo: PRISMA estricto.** Un registro cuyo texto completo no se
> puede recuperar en abierto (BioC-PMC, `oa_url`, Unpaywall) **no se criba con
> IA**: queda en la caja «informes no recuperados» del diagrama, con su motivo
> en `04_fulltext/retrieval.json`. Para recuperar más, instala el extra
> `search` y pasa `--mailto` (Unpaywall e ID Converter de PMC). Con el demo sin
> red puede no quedar ningún estudio incluido: es el resultado honesto.

> **Las corridas no se versionan en este repositorio** (`runs/` está en
> `.gitignore`): una corrida pertenece a su revisión, no al motor. Deposítala
> completa (manifiesto, ledger, entregable) en OSF/Zenodo o junto a tu protocolo.
```

En el árbol de "Estructura", sustituir

```
runs/                 # OUTPUTS reproducibles (una carpeta por ejecución)
```

por

```
runs/                 # OUTPUTS de cada corrida (git las ignora: se depositan con la revisión)
```

- [ ] **Step 4: Desviaciones en el spec.** En §14 del spec, añadir tras la fila 8:

```
| 9 | §6 pipeline | PR-B ya escribe `04_fulltext/retrieval.json` (formato de §4.2, con `text_file: null` hasta la caché de PR-C) y `04_fulltext/excluded.json`; M11 pide guardar el motivo del fallo y la lista 16b ya existe | Plan PR-B |
| 10 | §6 pipeline | El payload del gate FT gana `n_buscados` y `n_no_recuperados`; `n_evaluados` pasa a ser los evaluados (antes, los buscados). PR-D lo sustituye por `ft_payload` | Plan PR-B |
| 11 | §4.3 validador de `PrismaCounts` | Para un manifiesto sin `fulltext_sought` también fija `excluded_ft_human = 0` y `excluded_ft_ai = excluded_ft` (en v0.7 ningún código ponía `human_label`): sin esto, el diagrama de una corrida antigua diría "por humano 0 · por IA 0" con exclusiones | Plan PR-B |
| 12 | §6 conteos | `excluded_ft_human`/`excluded_ft_ai` se cuentan por `reason_source` de la lista 16b. Hoy equivale a `0`/`excluded_ft`, y sigue siendo correcto cuando PR-D añada etiquetas humanas | Plan PR-B |
| 13 | §6 `exports/checklist.py` | El ítem 16 del checklist PRISMA 2020 cita `excluidos_texto_completo.md` (16b) | §10 lista `checklist.py` en B |
```

- [ ] **Step 5: Commit de documentación.**

```bash
git -C C:/revisia-wt/b add CHANGELOG.md README.md docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md
git -C C:/revisia-wt/b commit -m "docs: CHANGELOG, README y desviaciones de PR-B (flujo PRISMA estricto)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Verificación completa** (en `C:\revisia-wt\b`): suite 3.13 (411 recogidos), el bucle de 3.11/3.12 de la Tarea 14 Step 6, lint y `uv lock --check`. Expected: todo en verde y limpio.

Run (humo del entregable, sin red):

```bash
uv run python - <<'EOF'
from pathlib import Path
from tempfile import mkdtemp

import sys
sys.path.insert(0, "tests")
from fakes import fetch_no_disponible
from test_pipeline_fake import EXAMPLE, _fake_search

from revisia.config import load_protocol
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext

protocol = load_protocol(EXAMPLE)
ctx = RunContext(protocol.slug, Path(mkdtemp()), "HUMO")
r = run_pipeline(protocol, EXAMPLE, ctx, auto_approve=True, search_fn=_fake_search,
                 fetch_fn=fetch_no_disponible(["rec-2"]))
print(r.counts.fulltext_sought, r.counts.fulltext_not_retrieved, r.counts.included)
print((ctx.run_dir / "deliverable" / "prisma_flow.md").read_text(encoding="utf-8")[:900])
EOF
```

Expected: `2 1 1` y un Mermaid con `Informes buscados para recuperación (n = 2)` y `Informes no recuperados (n = 1)`.

- [ ] **Step 7: Publicar y abrir PR-B** (sin merge).

```bash
git -C C:/revisia-wt/b push -u origin feat/ola1-flujo-prisma
gh pr create --base feat/ola1-preflight --head feat/ola1-flujo-prisma --title "Ola 1 · PR-B: flujo PRISMA estricto con informes no recuperados (M11, M23)" --body "$(cat <<'EOF'
## Qué cierra

- M11 de la auditoría 2026-09-03: un registro sin texto completo se cribaba con el abstract y contaba como evaluado; `dbr_notretrieved_reports` era un 0 literal; no había lista 16b y el motivo del fallo no se guardaba. D2 del spec de la Ola 1 (PRISMA estricto con rescate humano, que llega en PR-D).
- M23: `runs/` se ignora entero (D11).

## Qué cambia

- `FullText.reason`/`detail` (redactado) en cada rama de fallo de `fetch_fulltext`.
- El pipeline no criba con IA los no recuperados: `ScreeningDecision(fulltext_status="not_retrieved", votes=[], ensemble_label=None)`; no llegan a extracción. `04_fulltext/retrieval.json` con el motivo.
- `PrismaCounts` con buscados / no recuperados / rescatados / evaluados y exclusiones en elegibilidad por humano/IA; se retira `fulltext_abstract_only` (los manifiestos antiguos se siguen leyendo).
- Diagrama Mermaid, tabla, CSV PRISMA2020 y `metodologia.md` con los conteos reales.
- Lista 16b: `compute_ft_excluded`, `render_excluded_reports`, `04_fulltext/excluded.json` y `deliverable/excluidos_texto_completo.md`.

## Cambios incompatibles

- Desaparece `PrismaCounts.fulltext_abstract_only`.
- Los no recuperados ya no llegan a extracción: con el demo sin red puede no quedar ningún incluido.

## Verificación

- `uv run pytest -p no:cacheprovider`: 411 recogidos, en verde (rebasada sobre PR-A).
- La misma suite en 3.11 y 3.12 con venv desechable: en verde.
- `ruff check`, `ruff format --check`, `black --check`, `uv lock --check`: limpios.

## Pila

`main` ← PR-0 ← PR-A ← **PR-B** ← PR-C ← PR-D ← PR-E. Base: `feat/ola1-preflight`. Nunca `--delete-branch` mientras otra PR use una rama como base.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR.

- [ ] **Step 8: Traspaso a la pista de reanudación.** Crear el worktree de PR-C desde la rama ya rebasada (lo usa el plan `2026-10-04-ola-1-b-reanudacion-hitl.md`):

```bash
git worktree add C:/revisia-wt/c -b feat/ola1-reanudacion feat/ola1-flujo-prisma
(cd C:/revisia-wt/c && uv sync --extra dev && uv run pytest -p no:cacheprovider -q)
```

Expected: 411 tests en verde. El merge de PR-0, PR-A y PR-B lo decide el arquitecto.

---

## Self-review

Lo hizo el autor del plan antes de entregarlo; el controlador lo repite tras cada integración.

**1. Cobertura del spec.**

| Requisito | Tarea |
|---|---|
| §4.1 `canonical_json`, `canonical_sha256` en `runmeta.py` | 2 |
| §4.1 rutas con `/`, `schema_version: 1`, horas con zona | 1 (`JOURNAL_PATHS`, `ARTIFACT_SCHEMA_VERSION`, `utc_now_iso`) |
| §4.2 rutas de diario (`03_screening/journal.jsonl` … `06_synthesis/verification.jsonl`) | 1 (`JOURNAL_PATHS` + test literal) |
| §4.2 `04_fulltext/retrieval.json`, `04_fulltext/excluded.json`, `deliverable/excluidos_texto_completo.md` | 12 |
| §4.2 `GATED_STAGES` | 1 |
| §4.3 `RunInfo`, `LLMCall`, `JournalEntry`, `SearchLog`/`SearchLogEntry`, `DedupReport`, `RetrievalOutcome` (nulo ⇔ `available`), `ExcludedReport` | 1 |
| §4.3 `ScreeningDecision` + `fulltext_status`, `human_reason`, `human_actor` | 3 |
| §4.3 `PrismaCounts` campos nuevos (PR-0) y retirada de `fulltext_abstract_only` con validador (PR-B) | 3, 10 |
| §4.3 Ledger: `LEDGER_ACTIONS`, decisión efectiva | 2 |
| §4.4 relaciones 8, 9, 10 (lado pipeline, sin rescates hasta PR-D) y 11 (CSV) | 10, 11, 12 |
| §4.5 `artifacts.py` completo, `HUMAN_ACTOR_PREFIX`, `AUTO_APPROVE_ACTOR`, `summarize_gates`, `KNOWN_THRESHOLDS`, `tests/fakes.py` | 1, 2, 3, 4 |
| §4.5 spec y planes en PR-0 | 5 |
| §5 `Requirement`, `PROVIDER_REQUIREMENTS`, `PreflightIssue`, `PreflightReport`, `PreflightError`, `PreflightContext`, `stages_in_use`, `check_provider`, `check_retired`, `preflight` | 6 |
| §5 `check_databases`, `mailto`, `resume` | 7 |
| §5 `MANUAL_ONLY` ampliado | 7 |
| §5 `_load_dotenv`, `_cmd_validate` rc 2, `run` sin crear `runs_root` | 8 |
| §5 los 21 tests nombrados | 6 (13 de proveedores), 7 (8), 8 (3 de CLI) |
| §6 `FullText.reason/detail` y ramas `fulltext.py:126,130,138,146` | 9 |
| §6 pipeline FT estricto y conteos (`fulltext_rescued = 0`, `unclear` cuenta como incluido hasta PR-D) | 12 |
| §6 `compute_ft_excluded`, `ft_exclusion_reasons` derivado | 11, 12 |
| §6 diagrama, tabla, `render_excluded_reports` | 10, 11 |
| §6 CSV `dbr_*` reales, `methods.py` | 10 |
| §6 `.gitignore` `runs/` (D11) | 13 |
| §6 los 7 tests nombrados | 9, 10, 11, 12 |
| §10 cadena apilada, paralelismo, worktrees, solapes, ciclo de revisión, regla de merge | Topología, 5, 14, 15 |
| §11 criterio de cierre (3.13, 3.11/3.12, lint, `uv lock --check`) | 5, 14, 15 |
| CHANGELOG/README solo por el integrador, texto exacto | 5, 14, 15 |

**2. Placeholders.** Ningún paso dice "TBD", "TODO", "implementar después" ni "similar a la Tarea N"; todo paso que cambia código trae el código. Las tareas 13-15 no tienen test de pytest porque no cambian código: llevan comandos de verificación con salida esperada.

**3. Coherencia de nombres y firmas.** `GateSummary` (Tarea 1) es lo que devuelve `summarize_gates` (Tarea 2). `FulltextReason` (Tarea 1) tipa `FullText.reason` (Tarea 9) y `RetrievalOutcome.reason` (Tareas 1 y 12). `ExcludedReport` (Tarea 1) lo producen `compute_ft_excluded` y lo consume `render_excluded_reports` (Tarea 11) y el pipeline (Tarea 12). Los campos de `PrismaCounts` añadidos en la Tarea 3 son los que usan las Tareas 10 y 12. `fetch_disponible`/`fetch_no_disponible`/`ScriptedProvider` (Tarea 4) se usan con esas firmas en la Tarea 12. `_default_find_spec` (Tarea 6) es lo que parchean las fixtures de la Tarea 8. Conteos de tests verificados en un prototipo: 330 → 353 → 356 → 364 (PR-0); 377 → 396 → 399 (PR-A); 369 → 373 → 374 → 376 (PR-B sobre PR-0); 411 (B rebasada sobre A).

## Desviaciones respecto del spec

Se registran también en §14 del spec (Tareas 5, 14 y 15). Ninguna reabre D1–D14.

1. **Nombres extra en `artifacts.py`** (§4.5): `RunInterruption`, `DedupDuplicate`, `DedupRename`, los alias `SearchEntryKind`, `SearchEntryStatus`, `QueryOrigin`, `ReasonSource`, `GateAction` y `LLMCall.from_meta`. Por qué: §4.3 describe esas listas como `{…}` y hay que tiparlas para validar; `from_meta` evita que cada etapa copie el `RunMeta` a mano.
2. **Campos de `GateSummary`** (§4.5 los enumera de forma laxa): `stage, action, actor, autonomy, request_sha256, decision_sha256, n_labels, n_flag_reviews, forced_human, timestamp_utc`. `n_labels`/`n_flag_reviews` se cuentan en el ledger por `decision_sha256`, no se copian del `detail`, para que el auditor pueda contrastar el `n_labels` que declara el `approve`.
3. **`GATE_DECISION_ACTIONS`** además de `LEDGER_ACTIONS`, ambas `frozenset` (el spec escribe un conjunto literal): el reductor y el auditor necesitan el subconjunto que cierra un gate.
4. **`ScriptedProvider`** registra además `prompts` y admite `palabras` y `criterio_exclusion`; `fail_at` cuenta desde 1 y solo falla esa llamada. Por qué: `test_ft_no_recuperado_no_se_criba_con_ia` necesita saber qué vio el proveedor de FT, y la 16b necesita un criterio violado.
5. **`PreflightError(report)`** guarda el informe; el spec solo da `class PreflightError(ValueError): ...`.
6. **Problemas del preflight unidos** cuando el mensaje es idéntico (`where` combinado), y `stages_in_use` omite las etapas sin proveedor (el error lo emite `preflight`). Por qué: con Gemini en cinco etapas, la falta de key salía cinco veces.
7. **Tests existentes que cambian en PR-A**: además de `tests/test_cli_validate.py:35,44,72` (citados en el encargo), `tests/test_cli_errores.py:50,77`. Por qué (código real): el venv de desarrollo no instala `httpx` y el demo usa OpenAlex; sin `find_spec` falso, `run` saldría con 2 por el entorno.
8. **`context="resume"` también salta `httpx`** (literal del spec: "se saltan las comprobaciones de bases y de búsqueda"). Consecuencia anotada para PR-C: una recuperación pendiente sin `httpx` al reanudar deja registros `sin_httpx`.
9. **PR-B ya escribe `04_fulltext/retrieval.json` y `04_fulltext/excluded.json`** con el formato de §4.2 (§6 no los menciona). Por qué: M11 pide guardar el motivo del fallo y la lista 16b ya se calcula; PR-C los reescribe desde su diario con el mismo formato y añade `text_file`.
10. **Payload del gate FT en PR-B**: gana `n_buscados` y `n_no_recuperados`, y `n_evaluados` pasa a ser los evaluados; si no, la solicitud al humano mentiría hasta PR-D.
11. **Validador de `PrismaCounts`**: para manifiestos sin `fulltext_sought` también fija `excluded_ft_human = 0` y `excluded_ft_ai = excluded_ft`, que es lo que pasó en v0.7 (nadie ponía `human_label`).
12. **`excluded_ft_human/ai`** se cuentan por `reason_source` de la lista 16b en lugar de fijar `0`/`excluded_ft`: mismo valor hoy, correcto cuando PR-D añada etiquetas.
13. **`exports/checklist.py`**: el ítem 16 cita la lista 16b (§10 lo lista entre los ficheros de B; §6 no lo detalla).

