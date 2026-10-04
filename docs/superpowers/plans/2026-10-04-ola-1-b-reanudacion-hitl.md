# Ola 1 · Pista B (reanudación y HITL por registro: PR-C, PR-D) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una corrida se pueda pausar, interrumpir y reanudar sin repetir la búsqueda ni ninguna llamada ya hecha, con cada decisión humana atada al hash de la solicitud que respondió (PR-C: A9, M12, `request_sha256`), y que el humano decida registro a registro en el cribado y cita a cita en el reporte, con el checklist trAIce y la metodología diciendo quién decidió de verdad (PR-D: C1, M5, M13).

**Architecture:** PR-C empieza con un refactor puro de `run_pipeline` (`_Run` con `gate`/`stop` y una función por etapa) y añade, en este orden: el diario por etapa (`orchestration/journal.py`: `StageJournal`, `journaled`); `RunContext` con `llm_calls.jsonl` volcado al registrar y JSON atómico; la instantánea del protocolo y `run.json` (`orchestration/snapshot.py`); la búsqueda y el dedup congelados en `01_search/` y `02_dedup/` (`orchestration/search_stage.py`); el estado y las interrupciones en `run.json` (`RunInterrupted`, `flow.resume_review`); los gates con `request_sha256` canónico, plantilla y ledger idempotente; un diario por cada etapa con LLM o red; `gold.json`; `revisia run --resume`; y PRISMA-S y métodos desde el log de búsqueda. PR-D añade la decisión por registro y por cita en `orchestration/hitl.py` (`RecordLabel`, `FlagReview`, `RecordPolicy`, `FlagPolicy`), las solicitudes y políticas de cada gate en `orchestration/gates.py` (funciones puras), su cableado en el pipeline (D5, D6, D7, rescates D2, `unclear` D9, M5) y el checklist trAIce y `metodologia.md` escritos desde `summarize_gates` (M13).

**Tech Stack:** Python 3.13 (suite también en 3.11/3.12 con venv desechable), Pydantic v2, PyYAML, pytest, ruff + black (línea 100), uv, gh.

**Spec:** `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md`. Este plan cubre §7 (PR-C) y §8 (PR-D), más lo que les exigen §3 (D1–D14, sobre todo D3–D9, D13 y D14), §4 (contratos de artefactos y relaciones de §4.4) y la topología de §10. Lee §3 antes de empezar: no se reabre ninguna decisión. Parte del estado del código **después de las 15 tareas** del plan hermano `2026-10-04-ola-1-a-cimientos.md` (PR-0 → PR-A → PR-B; 411 tests recogidos) y usa literalmente las firmas que produce PR-0 (sus bloques **Interfaces**). El auditor (PR-E, plan `2026-10-04-ola-1-c-auditor.md`) consume lo que produce este plan: los bloques **Interfaces** de las Tareas 3, 5, 8, 9, 20, 21 y 26 y el resumen "Contrato para el auditor" del final.

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes y commits **en español**, con el tono del repo. Las docstrings explican el porqué y citan la auditoría ("auditoría 2026-09-03, A9") o la decisión del spec ("D5").
- Estilo: `ruff` (reglas `E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100), ambos limpios. Los bloques de este plan ya salen formateados; si `ruff format` cambiara algo, se acepta su versión (black la respeta).
- `from __future__ import annotations` al inicio de todo módulo nuevo, también en los de `tests/`.
- **Sin sintaxis PEP 695** (`def f[T]`): la suite también corre en 3.11/3.12 (spec §11). Las funciones genéricas usan `TypeVar` y `# noqa: UP047`.
- Tests offline, sin red y deterministas. Ningún test invoca `claude`, WeasyPrint real ni APIs. El proveedor se sustituye con `monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)`; la búsqueda, con `search_fn=`; el texto completo, con `fetch_fn=` (`fetch_disponible`, `fetch_no_disponible` de `tests/fakes.py`). Un registro de prueba sin DOI, PMCID ni `oa_url`, y sin `--mailto`, no toca la red al recuperar.
- Línea base: **411 tests recogidos, en verde** (fin del plan A: `feat/ola1-flujo-prisma` rebasada sobre `feat/ola1-preflight`). Ningún test existente se borra; los que cambian de expectativa se listan en su tarea con el código exacto del cambio.
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider`; lint, `uv run ruff check . && uv run ruff format --check . && uv run black --check .`.
- Commits pequeños, al menos uno por tarea, en español con prefijo convencional (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`), terminados con la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Cada etapa con diario es su propio commit (spec §7).
- **Los implementadores no tocan** `CHANGELOG.md`, `README.md` ni el spec: los actualiza el integrador en las Tareas 19 y 28, con el texto exacto que dan esas tareas.
- **No tocar** `runs/` ni `protocols/<slug>/` distintos de `_TEMPLATE`. No cambiar `revisia.__version__` ni `pyproject.toml` (la 0.8.0 la publica el arquitecto, D13).
- `tests/` no es un paquete: los helpers compartidos se importan como `from fakes import ...` y `from hitl_helpers import ...` (pytest pone `tests/` en `sys.path`); ruff los ordena en el bloque de terceros, después de `import pytest`/`import yaml`.
- Ningún hash depende del sistema: lo que se hashea se lee con `read_text` (convierte CRLF) o en bytes UTF-8 (caché de texto completo, huellas del protocolo).
- Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base.

---

## Topología de ejecución (subagentes)

La Ola 1 son seis PRs apiladas, `0 → A → B → C → D → E`. El plan A cubre 0, A y B y deja creado el worktree de C (su Tarea 15, Step 8); este plan cubre C y D; el plan C cubre E.

| Pista | PR | Rama | Worktree | Se crea desde | Base de la PR | Cierra | Tareas |
|---|---|---|---|---|---|---|---|
| C | PR-C | `feat/ola1-reanudacion` | `C:\revisia-wt\c` | `feat/ola1-flujo-prisma` ya rebasada sobre A (plan A, Tarea 15) | `feat/ola1-flujo-prisma` | A9, M12, `request_sha256` | 1–19 |
| D | PR-D | `feat/ola1-hitl-por-registro` | `C:\revisia-wt\d` | `feat/ola1-reanudacion` (la crea la Tarea 19, Step 8) | `feat/ola1-reanudacion` | C1, M5, M13 | 20–28 |
| E · fase 2 | PR-E | `feat/ola1-auditor` rebasada sobre D | `C:\revisia-wt\e` | — | `feat/ola1-hitl-por-registro` | — | plan C |

Orden en el tiempo:

1. **PR-C (secuencial, `C:\revisia-wt\c`):** Tareas 1 → 18 y la integración (Tarea 19), que publica la rama, abre la PR y crea el worktree de D. Las Tareas 1–9 construyen la infraestructura (refactor, diario, `RunContext`, instantánea, búsqueda y dedup congelados, estado de la corrida, gates con hash); las 10–16 ponen el diario a cada etapa, un commit por etapa en el orden del spec (T/A → recuperación con caché → FT → extracción y 2.º extractor → RoB → síntesis y verificación; `gold.json` va entre T/A y recuperación); las 17–18 son el CLI y PRISMA-S.
2. **PR-D (secuencial, `C:\revisia-wt\d`):** Tareas 20 → 27 y la integración (Tarea 28), con el E2E de §11.
3. **PR-E fase 2:** se rebasa sobre D (plan C). La fase 1 de E corre en paralelo con todo este plan desde PR-0.

Por qué D va en su propio worktree y no en el de C: la revisión de PR-C puede pedir correcciones mientras D avanza; con dos worktrees, C se corrige en el suyo y D se rebasa (`git -C C:/revisia-wt/d rebase feat/ola1-reanudacion`) sin mezclar cambios sin commitear.

Solapes verificados y cómo se resuelven:

| Fichero | Pistas | Resolución |
|---|---|---|
| `revisia/orchestration/pipeline.py` | B (FT y conteos), C (refactor, diarios, estado), D (gates por registro, M5, M13) | Secuenciales B → C → D |
| `revisia/orchestration/hitl.py` | C (hash, plantilla, ledger idempotente), D (registros, citas) | Secuenciales; D lo reescribe entero en la Tarea 20 |
| `revisia/cli.py` | A (preflight), C (`--resume`, códigos de salida), E (`_cmd_audit`) | C solo toca `_cmd_run`, el parser de `run` y la cola de `main`; E solo `_cmd_audit` |
| `revisia/exports/checklist.py`, `revisia/exports/methods.py` | B, C (log de búsqueda), D (M13) | Secuenciales |
| `tests/test_pipeline_fake.py` | B, C (Tareas 1, 3, 9), E (fase 2) | E no lo toca en su fase 1 |
| `tests/fakes.py` | 0 (lo crea), C (Tarea 16: `sintesis=`, aditivo) | Ampliaciones solo aditivas |
| `tests/hitl_helpers.py` | C (lo crea, Tarea 9), D (Tareas 24 y 26, aditivas), E (lo usa) | E lo importa; no lo modifica |
| `tests/conftest.py` | solo E | C y D no lo crean |
| `CHANGELOG.md`, `README.md`, spec | integrador | Un commit de docs por PR, siempre después de rebasar |

**Ciclo por tarea:** implementador (subagente nuevo, TDD estricto: test rojo → código mínimo → verde → lint → commit) → revisor (subagente nuevo: primero cumplimiento del spec y de este plan, después calidad) → correcciones si las hay → siguiente tarea. Las tareas de integración (19 y 28) las ejecuta el controlador, que va de punta a punta sin pedir confirmación entre tareas y audita y corrige lo que encuentre. **El merge no lo hace nadie de este plan: lo decide el arquitecto.**

**Regla de merge de PRs apiladas** (la ejecuta el arquitecto; va escrita en el cuerpo de cada PR): mergear sin borrar la rama → `gh pr edit <n> --base main` en la PR que dependía de ella → borrar la rama mergeada → cerrar y reabrir la PR re-apuntada (`gh pr close <n> && gh pr reopen <n>`) para que corra el CI.

**Entorno de cada worktree:** el primer paso en un worktree nuevo es `uv sync --extra dev` (pytest, ruff y black están en el extra `dev`). El venv de desarrollo **no** instala `httpx` ni `google-genai`: los tests que pasan por el preflight de una corrida nueva del demo (OpenAlex) parchean `preflight._default_find_spec`, como ya hace el plan A.

**Conteos de tests recogidos** (verificados en un prototipo de punta a punta sobre el estado final del plan A): 411 → 412 → 415 → 419 → 421 → 426 → 429 → 431 → 436 → 441 → 442 → 443 → 444 → 445 → 446 → 447 → 451 → 460 → **461** (fin de PR-C; Tareas 1–18) → 477 → 479 → 482 → 485 → 492 → 494 → 496 → **499** (fin de PR-D; Tareas 20–27). La misma suite pasa en 3.11 y 3.12 al final de cada PR.

---

## Pista C · PR-C `feat/ola1-reanudacion` (worktree `C:\revisia-wt\c`)

Todas las tareas de esta pista se ejecutan en `C:\revisia-wt\c`, rama `feat/ola1-reanudacion`, creada por el plan A (Tarea 15, Step 8) desde `feat/ola1-flujo-prisma` ya rebasada. Primer paso: `uv sync --extra dev` y `uv run pytest -p no:cacheprovider` → 411 recogidos, en verde.

### Task 1: Refactor puro de `run_pipeline` (`_Run`, una función por etapa, `PipelineResult.stage`)

Primer commit de PR-C (spec §7): sin cambio de comportamiento. Los cinco bloques de gate casi iguales pasan a `_Run.gate()`/`_Run.stop()` y cada etapa a su función; `run_pipeline` conserva su firma pública. El único añadido observable es `PipelineResult.stage`, que la reanudación y los helpers de test necesitan.

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (fichero completo)
- Test: `tests/test_pipeline_fake.py` (un test nuevo al final)

**Interfaces:**
- Consumes: todo lo que ya importa `pipeline.py` al final del plan A; `MetaAnalysisResult` (`revisia/meta_analysis.py`) y `ExtractionAgreement` (`revisia/extraction_agreement.py`) para tipar.
- Produces:
  - `PipelineResult` + `stage: str | None = None` (gate en el que se detuvo; `None` si se completó). Posicionales sin cambios: `status, message, counts, included, narrative, hallucination_flagged, metrics, run_dir`.
  - `@dataclass(slots=True) class _Run`: `protocol`, `protocol_dir: Path`, `ctx: RunContext`, `question`, `criteria`, `form_fields`, `auto_approve`, `mailto`, `metrics: ScreeningMetrics | None = None`; `gate(stage: str, payload: dict) -> GateResult`; `stop(gate: GateResult, stage: str) -> PipelineResult | None`.
  - `@dataclass(slots=True) class _FullTextStage`: `decisions`, `texts`, `not_retrieved`.
  - Funciones privadas por etapa: `_search(run, *, max_results, search_fn)`, `_dedup(run, raw_records)`, `_load_gold(run, gold_labels)`, `_screen_ta(run, deduped, gold)`, `_fulltext(run, passed_ta, fetch_fn)`, `_extract(run, included)`, `_assess_rob(run, included, extractions, fulltexts)`, `_meta_analysis(run)`, `_synthesize_and_verify(run, included, extractions, fulltexts, embedder)`, `_build_counts(*, ...)`, `_write_deliverables(run, *, ...) -> Path`.
  - `run_pipeline(...)`: firma y resultados idénticos a los de PR-B.

- [ ] **Step 1: Test que falla** — añadir al final de `tests/test_pipeline_fake.py`:

```python


def test_pipeline_result_indica_la_etapa_de_la_pausa(tmp_path: Path) -> None:
    # Refactor de la Ola 1 (spec 2026-10-04 §7): el resultado dice en qué gate se
    # detuvo la corrida; la reanudación (PR-C) y los helpers de test lo usan.
    protocol = load_protocol(EXAMPLE)
    pausa = run_pipeline(
        protocol, EXAMPLE, RunContext(protocol.slug, tmp_path, "T-PAUSA"), search_fn=_fake_search
    )
    assert (pausa.status, pausa.stage) == ("paused", "screening_ta")

    completa = run_pipeline(
        protocol,
        EXAMPLE,
        RunContext(protocol.slug, tmp_path, "T-FIN"),
        auto_approve=True,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
    )
    assert (completa.status, completa.stage) == ("completed", None)
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_pipeline_fake.py::test_pipeline_result_indica_la_etapa_de_la_pausa -v`
Expected: FAIL con `AttributeError: 'PipelineResult' object has no attribute 'stage'`.

- [ ] **Step 3: Implementar** — sustituir `revisia/orchestration/pipeline.py` completo por:

```python
"""Pipeline del tracer bullet (recorrido por etapas, Python puro y testeable).

Encadena los agentes con un checkpoint humano tras el screening y otro antes de
finalizar el reporte, corriendo el verificador anti-alucinación sobre la
síntesis. Es ``orchestration/flow.py`` (Prefect) quien lo envuelve para una
corrida "de producción"; aquí vive la lógica, sin dependencias pesadas, para
poder testearla offline con el proveedor ``fake``.

Estructura (Ola 1, spec 2026-10-04 §7): ``run_pipeline`` solo encadena; cada
etapa vive en su función (``_search``, ``_dedup``, ``_screen_ta``,
``_fulltext``, ``_extract``, ``_assess_rob``, ``_synthesize_and_verify``,
``_build_counts``, ``_write_deliverables``) y comparte el estado de la
invocación en un ``_Run``, cuyos ``gate``/``stop`` sustituyen los cinco bloques
de checkpoint casi iguales de antes. Es la base de la reanudación por diario.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from revisia.agents import _http, search_backends
from revisia.agents import dedup as dedup_agent
from revisia.agents import extraccion as extraccion_agent
from revisia.agents import fulltext as fulltext_agent
from revisia.agents import reporte as reporte_agent
from revisia.agents import rob as rob_agent
from revisia.agents import screening as screening_agent
from revisia.agents import screening_ft as screening_ft_agent
from revisia.agents import verificador as verificador_agent
from revisia.config import ReviewProtocol
from revisia.exclusions import ExclusionBreakdown, compute_exclusion_breakdown, compute_ft_excluded
from revisia.exports import (
    PrismaCounts,
    render_bibtex,
    render_excluded_reports,
    render_extraction_table,
    render_flow_diagram,
    render_flow_markdown,
    render_forest_markdown,
    render_forest_png,
    render_funnel_png,
    render_metafor_csv,
    render_methods,
    render_prisma2020_flow_csv,
    render_prisma_2020_checklist,
    render_prisma_abstracts_checklist,
    render_prisma_s_checklist,
    render_robvis_csv,
    render_traice_checklist,
)
from revisia.extraction_agreement import (
    ExtractionAgreement,
    compute_extraction_agreement,
    select_double_extraction_subset,
)
from revisia.ingest import import_directory
from revisia.llm.registry import build_provider
from revisia.meta_analysis import MetaAnalysisResult, meta_analyze
from revisia.metrics import ScreeningMetrics, compute_screening_metrics
from revisia.orchestration.hitl import GateResult, review_gate
from revisia.orchestration.run_context import RunContext
from revisia.provenance.runmeta import sha256_text
from revisia.rag.embed import Embedder, HashEmbedder
from revisia.schemas.artifacts import ExcludedReport, RetrievalOutcome
from revisia.schemas.effects import EffectInput
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.records import SearchRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision
from revisia.schemas.verification import VerificationReport

SearchFn = Callable[[str, int], list[SearchRecord]]
FetchFn = Callable[[SearchRecord], fulltext_agent.FullText]


@dataclass(slots=True)
class PipelineResult:
    status: str  # "completed" | "paused" | "rejected"
    message: str
    counts: PrismaCounts = field(default_factory=PrismaCounts)
    included: list[SearchRecord] = field(default_factory=list)
    narrative: str | None = None
    hallucination_flagged: bool = False
    metrics: ScreeningMetrics | None = None
    run_dir: Path | None = None
    # Gate en el que se detuvo la corrida (pausa o rechazo); None si se completó.
    stage: str | None = None


def _criteria_to_text(ie: dict) -> str:
    criteria = ie.get("criteria", ie)
    lines: list[str] = []
    for dim, spec in criteria.items():
        if isinstance(spec, dict):
            inc = spec.get("inclusion", "")
            exc = spec.get("exclusion", "")
            lines.append(f"- {dim}: incluir={inc!r}; excluir={exc!r}")
        else:
            lines.append(f"- {dim}: {spec}")
    return "\n".join(lines)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _multi_database_search(
    protocol: ReviewProtocol,
    protocol_dir: Path,
    question_text: str,
    max_results: int,
    mailto: str | None,
) -> tuple[list[SearchRecord], list[dict[str, str]]]:
    """Busca en cada base declarada (con su cadena) + importación manual.

    Por cada base de ``protocol.databases`` lee su cadena en
    ``search_strings/<base>.txt`` (cae a la pregunta) y despacha al backend; las
    bases sin backend programático (Scopus/WoS) se cubren con los archivos
    RIS/BibTeX de ``imported/``. Un backend que falle (red, 5xx, JSON inválido)
    **no aborta la corrida**: se anota en ``failures`` para que quede en disco
    (``01_search/failures.json``) y en PRISMA-S conste qué base no respondió.
    La deduplicación posterior une los solapes.
    """
    databases = protocol.databases or ["openalex"]
    records: list[SearchRecord] = []
    failures: list[dict[str, str]] = []
    for db in databases:
        string_file = protocol_dir / "search_strings" / f"{search_backends.db_key(db)}.txt"
        query = question_text
        if string_file.exists():
            query = string_file.read_text(encoding="utf-8").strip() or question_text
        if search_backends.db_key(db) not in search_backends.BACKENDS:
            # Base sin backend (p. ej. Scopus): se incorpora vía imported/.
            continue
        try:
            records += search_backends.search_database(db, query, max_results, mailto=mailto)
        except Exception as exc:  # red, 5xx, JSON o validación: degradar, nunca abortar
            # Cualquier fallo del backend (incluida una ValidationError de pydantic,
            # que hereda de ValueError) queda registrado; el mensaje se redacta
            # porque httpx incluye la URL con api_key/email en el texto del error.
            error = _http.redact_secrets(f"{type(exc).__name__}: {exc}")
            failures.append({"db": db, "error": error})
            continue
    records += import_directory(protocol_dir / "imported")
    return records, failures


def _rob_table_md(tool: str, assessments: dict[str, RoBAssessment]) -> str:
    """Tabla Markdown de riesgo de sesgo (un estudio por fila + juicio global)."""
    lines = [f"# Riesgo de sesgo · {tool}", ""]
    if not assessments:
        lines.append("_(sin estudios evaluados)_")
        return "\n".join(lines)
    lines += ["| Estudio | Juicio global | Dominios |", "|---|---|---|"]
    for study_id, a in assessments.items():
        domains = "; ".join(f"{d.domain}={d.judgment}" for d in a.domains)
        lines.append(f"| {study_id} | {a.overall} | {domains} |")
    return "\n".join(lines)


@dataclass(slots=True)
class _Run:
    """Estado compartido de una invocación de ``run_pipeline``.

    Las funciones por etapa lo reciben en vez de una docena de argumentos.
    ``gate`` aplica el checkpoint de una etapa con la autonomía del protocolo y
    ``stop`` traduce un gate no aprobado en el ``PipelineResult`` con el que la
    corrida se detiene (antes, cinco bloques casi iguales).
    """

    protocol: ReviewProtocol
    protocol_dir: Path
    ctx: RunContext
    question: str
    criteria: str
    form_fields: list[dict]
    auto_approve: bool
    mailto: str | None
    metrics: ScreeningMetrics | None = None

    def gate(self, stage: str, payload: dict) -> GateResult:
        """Checkpoint humano de ``stage`` con la autonomía que fija el protocolo."""
        return review_gate(
            stage=stage,
            autonomy=self.protocol.autonomy_for(stage),
            run_ctx=self.ctx,
            review_payload=payload,
            auto_approve=self.auto_approve,
        )

    def stop(self, gate: GateResult, stage: str) -> PipelineResult | None:
        """``None`` si el gate aprobó; si no, el resultado con el que se detiene."""
        if gate.status == "approved":
            return None
        return PipelineResult(
            gate.status, gate.message, metrics=self.metrics, run_dir=self.ctx.run_dir, stage=stage
        )


@dataclass(slots=True)
class _FullTextStage:
    """Resultado de la recuperación y el cribado a texto completo."""

    decisions: list[ScreeningDecision]
    texts: dict[str, str]
    not_retrieved: int


def _search(run: _Run, *, max_results: int, search_fn: SearchFn | None) -> list[SearchRecord]:
    """Búsqueda multi-base (A2).

    ``search_fn`` inyectado (tests) tiene prioridad y conserva el contrato de
    una sola llamada; en producción se busca en todas las bases declaradas.
    """
    if search_fn is not None:
        return search_fn(run.question, max_results)
    raw_records, failures = _multi_database_search(
        run.protocol, run.protocol_dir, run.question, max_results, run.mailto
    )
    if failures:
        run.ctx.write_json("01_search/failures.json", failures)
        for failure in failures:
            print(
                f"⚠️  búsqueda · {failure['db']} no respondió ({failure['error']}); "
                "se continúa sin esa base"
            )
    return raw_records


def _dedup(run: _Run, raw_records: list[SearchRecord]) -> tuple[list[SearchRecord], int]:
    """Deduplicación determinista (A2)."""
    return dedup_agent.deduplicate(raw_records)


def _load_gold(run: _Run, gold_labels: dict[str, bool] | None) -> dict[str, bool]:
    """Gold standard humano: ``gold.yml`` del protocolo + etiquetas por código.

    Las pasadas por código tienen prioridad sobre las del fichero.
    """
    gold: dict[str, bool] = {}
    gold_file = _load_yaml(run.protocol_dir / "gold.yml")
    for rid, val in (gold_file.get("gold", gold_file) or {}).items():
        gold[rid] = bool(val)
    if gold_labels:
        gold.update(gold_labels)
    return gold


def _screen_ta(
    run: _Run, deduped: list[SearchRecord], gold: dict[str, bool]
) -> list[ScreeningDecision]:
    """Cribado T/A (A1): ensemble multi-modelo con voto sesgado a recall.

    Deja las métricas frente al gold (Recall/Lost-Evidence, MCC, WMCC, kappa)
    en ``run.metrics``.
    """
    members = [
        screening_agent.ScreenerMember(
            provider=build_provider(cfg),
            model_name=f"{cfg.provider}:{cfg.model}",
            temperature=cfg.temperature,
            seed=cfg.seed,
        )
        for cfg in run.protocol.screeners_for("screening_ta")
    ]
    decisions = []
    for record in deduped:
        decision, metas = screening_agent.screen_record(
            members,
            question=run.question,
            criteria=run.criteria,
            record=record,
        )
        decision.final_label = decision.human_label or decision.ensemble_label
        decisions.append(decision)
        for meta in metas:
            run.ctx.record_meta(meta)
    run.ctx.write_json("03_screening/decisions.json", [d.model_dump() for d in decisions])

    if gold:
        run.metrics = compute_screening_metrics(
            decisions, gold, fn_weight=run.protocol.thresholds.get("wmcc_fn_weight", 10.0)
        )
        run.ctx.write_json("03_screening/metrics.json", run.metrics.model_dump())
    return decisions


def _fulltext(run: _Run, passed_ta: list[SearchRecord], fetch_fn: FetchFn | None) -> _FullTextStage:
    """Texto completo + cribado a texto completo (A0).

    PRISMA estricto (D2; auditoría 2026-09-03, M11): un informe sin texto
    completo NO se criba con IA (antes se cribaba con el abstract y contaba
    como evaluado). Queda como "no recuperado", con su motivo en
    04_fulltext/retrieval.json, y no llega a extracción.
    """
    fetch = fetch_fn or (lambda rec: fulltext_agent.fetch_fulltext(rec, mailto=run.mailto))
    ft_cfg = run.protocol.provider_for("screening_ft")
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
            ft_provider,
            ft_model,
            question=run.question,
            criteria=run.criteria,
            record=record,
            text=ft.text,
            temperature=ft_cfg.temperature,
            seed=ft_cfg.seed,
        )
        decision.fulltext_status = "retrieved"
        decision.final_label = decision.human_label or decision.ensemble_label
        ft_decisions.append(decision)
        run.ctx.record_meta(meta)
    run.ctx.write_json("04_fulltext/retrieval.json", retrieval)
    run.ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])
    not_retrieved = sum(1 for d in ft_decisions if d.fulltext_status == "not_retrieved")
    return _FullTextStage(ft_decisions, fulltexts, not_retrieved)


def _extract(
    run: _Run, included: list[SearchRecord]
) -> tuple[dict[str, ExtractionRecord], ExtractionAgreement | None]:
    """Extracción de datos (A0) y, si hay 2.º extractor, doble extracción (≥20 %).

    El 2.º extractor es el primero de ``ensemble_llm['extraccion']``; el acuerdo
    entre extractores va a ``05_extraction/agreement.json`` (§6).
    """
    extract_cfg = run.protocol.provider_for("extraccion")
    extract_provider = build_provider(extract_cfg)
    extractions: dict[str, ExtractionRecord] = {}
    for record in included:
        extraction, meta = extraccion_agent.extract_record(
            extract_provider,
            record=record,
            form_fields=run.form_fields,
            temperature=extract_cfg.temperature,
            seed=extract_cfg.seed,
        )
        extractions[record.record_id] = extraction
        run.ctx.record_meta(meta)
    run.ctx.write_json(
        "05_extraction/extractions.json",
        {k: v.model_dump() for k, v in extractions.items()},
    )

    extraction_agreement = None
    second_extractors = run.protocol.ensemble_llm.get("extraccion", [])
    if second_extractors and included:
        subset = select_double_extraction_subset(included)
        second_cfg = second_extractors[0]
        second_provider = build_provider(second_cfg)
        secondary: dict[str, ExtractionRecord] = {}
        for record in subset:
            extraction2, meta2 = extraccion_agent.extract_record(
                second_provider,
                record=record,
                form_fields=run.form_fields,
                temperature=second_cfg.temperature,
                seed=second_cfg.seed,
            )
            secondary[record.record_id] = extraction2
            run.ctx.record_meta(meta2)
        primary_subset = {r.record_id: extractions[r.record_id] for r in subset}
        extraction_agreement = compute_extraction_agreement(primary_subset, secondary)
        run.ctx.write_json("05_extraction/agreement.json", extraction_agreement.model_dump())
    return extractions, extraction_agreement


def _assess_rob(
    run: _Run,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
    fulltexts: dict[str, str],
) -> dict[str, RoBAssessment]:
    """Riesgo de sesgo (A0) con la herramienta del protocolo."""
    rob_cfg = run.protocol.provider_for("rob")
    rob_provider = build_provider(rob_cfg)
    assessments: dict[str, RoBAssessment] = {}
    for record in included:
        assessment, meta = rob_agent.assess_rob(
            rob_provider,
            tool=run.protocol.rob_tool,
            record=record,
            extraction=extractions.get(record.record_id),
            text=fulltexts.get(record.record_id),
            temperature=rob_cfg.temperature,
            seed=rob_cfg.seed,
        )
        assessments[record.record_id] = assessment
        run.ctx.record_meta(meta)
    run.ctx.write_json(
        "07_rob/assessments.json",
        {k: v.model_dump() for k, v in assessments.items()},
    )
    return assessments


def _meta_analysis(run: _Run) -> tuple[MetaAnalysisResult | None, str]:
    """Meta-análisis cuantitativo (§8.1) · opcional, desde ``effects.yml``.

    Si el protocolo aporta tamaños de efecto, se sintetiza cuantitativamente
    (efectos fijos + aleatorios, I²/τ², Egger); si no, solo síntesis narrativa.
    Devuelve el resultado y el modo de presentación del forest.
    """
    effects_cfg = _load_yaml(run.protocol_dir / "effects.yml")
    meta_display = effects_cfg.get("display", "raw")  # "proportion" → forest en 0–1
    raw_effects = effects_cfg.get("effects", [])
    if not raw_effects:
        return None, meta_display
    measure = effects_cfg.get("measure", "precomputed")
    effects = [EffectInput.model_validate(e) for e in raw_effects]
    meta_result = meta_analyze(effects, measure)
    run.ctx.write_json("08_meta/meta_analysis.json", meta_result.model_dump())
    return meta_result, meta_display


def _synthesize_and_verify(
    run: _Run,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
    fulltexts: dict[str, str],
    embedder: Embedder | None,
) -> tuple[str, VerificationReport]:
    """Síntesis narrativa (A1) y verificador anti-alucinación (grounding).

    Modo según ``protocol.grounding``: "agent" (un modelo juzga; cruza idiomas,
    sin vectores), "existence" (solo id en corpus) o "embedder" (coseno léxico).
    """
    synth_cfg = run.protocol.provider_for("sintesis")
    synth_provider = build_provider(synth_cfg)
    narrative, meta = reporte_agent.synthesize_narrative(
        synth_provider,
        question=run.question,
        included=included,
        extractions=extractions,
        temperature=synth_cfg.temperature,
        seed=synth_cfg.seed,
    )
    run.ctx.record_meta(meta)

    sources = {r.record_id: (fulltexts.get(r.record_id) or r.abstract or "") for r in included}
    verify_kwargs: dict = {"sources": sources}
    grounding_mode = getattr(run.protocol, "grounding", "embedder")
    if grounding_mode == "agent":
        from revisia.rag.grounding import make_provider_judge

        verify_kwargs["judge"] = make_provider_judge(
            synth_provider, f"{synth_cfg.provider}:{synth_cfg.model}", temperature=0.0
        )
    elif grounding_mode != "existence":  # "embedder" (default)
        verify_kwargs["embedder"] = embedder or HashEmbedder()
    verification = verificador_agent.verify_narrative(
        "reporte",
        narrative,
        [r.record_id for r in included],
        **verify_kwargs,
    )
    run.ctx.write_json("06_synthesis/verification.json", verification.model_dump())
    return narrative, verification


def _build_counts(
    *,
    raw_records: list[SearchRecord],
    deduped: list[SearchRecord],
    discarded: int,
    excluded_ta: int,
    ta_breakdown: ExclusionBreakdown,
    passed_ta: list[SearchRecord],
    ft: _FullTextStage,
    excluded_ft: int,
    excluded_reports: list[ExcludedReport],
    ft_exclusion_reasons: dict[str, int],
    included: list[SearchRecord],
) -> PrismaCounts:
    """Conteos PRISMA 2020 de la corrida (diagrama, tabla, CSV y manifiesto)."""
    identified_by_source: dict[str, int] = {}
    for r in raw_records:
        identified_by_source[r.source_db] = identified_by_source.get(r.source_db, 0) + 1
    return PrismaCounts(
        identified=len(raw_records),
        identified_by_source=identified_by_source,
        duplicates_removed=discarded,
        screened=len(deduped),
        excluded_ta=excluded_ta,
        excluded_ta_human=ta_breakdown.excluded_human,
        excluded_ta_ai=ta_breakdown.excluded_ai,
        fulltext_sought=len(passed_ta),
        fulltext_not_retrieved=ft.not_retrieved,
        fulltext_rescued=0,  # los rescates humanos llegan con el HITL por registro (PR-D)
        fulltext_assessed=len(passed_ta) - ft.not_retrieved,
        excluded_ft=excluded_ft,
        excluded_ft_human=sum(1 for r in excluded_reports if r.reason_source == "human"),
        excluded_ft_ai=sum(1 for r in excluded_reports if r.reason_source == "ai"),
        ft_exclusion_reasons=ft_exclusion_reasons,
        included=len(included),
    )


def _write_deliverables(
    run: _Run,
    *,
    counts: PrismaCounts,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
    assessments: dict[str, RoBAssessment],
    narrative: str,
    excluded_reports: list[ExcludedReport],
    exclusion_breakdown: ExclusionBreakdown,
    extraction_agreement: ExtractionAgreement | None,
    meta_result: MetaAnalysisResult | None,
    meta_display: str,
) -> Path:
    """Escribe el entregable completo (``deliverable/``) y devuelve su carpeta."""
    protocol = run.protocol
    deliverable = run.ctx.deliverable_dir()
    (deliverable / "documento.md").write_text(
        f"# {protocol.title}\n\n## Síntesis narrativa (borrador)\n\n{narrative}\n",
        encoding="utf-8",
    )
    (deliverable / "prisma_flow.md").write_text(
        render_flow_diagram(counts) + "\n\n" + render_flow_markdown(counts) + "\n",
        encoding="utf-8",
    )
    (deliverable / "excluidos_texto_completo.md").write_text(
        render_excluded_reports(excluded_reports), encoding="utf-8"
    )
    (deliverable / "risk_of_bias.md").write_text(
        _rob_table_md(protocol.rob_tool, assessments), encoding="utf-8"
    )
    (deliverable / "tabla_extraccion.md").write_text(
        render_extraction_table(included, extractions), encoding="utf-8"
    )
    (deliverable / "referencias.bib").write_text(render_bibtex(included), encoding="utf-8")
    models_used = sorted({f"{m.provider}:{m.model}" for m in run.ctx.metas})
    (deliverable / "metodologia.md").write_text(
        render_methods(
            protocol=protocol,
            counts=counts,
            metrics=run.metrics,
            models=models_used,
            quantitative=meta_result is not None,
            exclusions=exclusion_breakdown,
            extraction_agreement=extraction_agreement,
        ),
        encoding="utf-8",
    )
    if meta_result is not None:
        (deliverable / "meta_analisis.md").write_text(
            render_forest_markdown(meta_result, display=meta_display), encoding="utf-8"
        )
        assets = deliverable / "assets"
        render_forest_png(meta_result, assets / "forest.png", display=meta_display)
        render_funnel_png(meta_result, assets / "funnel.png")
    (deliverable / "checklist_2020.md").write_text(render_prisma_2020_checklist(), encoding="utf-8")
    (deliverable / "checklist_s.md").write_text(
        render_prisma_s_checklist(
            databases=list(protocol.databases),
            search_window=protocol.search_window,
            counts=counts,
        ),
        encoding="utf-8",
    )
    (deliverable / "checklist_abstracts.md").write_text(
        render_prisma_abstracts_checklist(
            counts=counts,
            databases=list(protocol.databases),
            search_window=protocol.search_window,
            registration=protocol.registration,
        ),
        encoding="utf-8",
    )
    (deliverable / "checklist_traice.md").write_text(
        render_traice_checklist(
            run.ctx.metas,
            dict(protocol.autonomy),
            metrics=run.metrics,
            exclusions=exclusion_breakdown,
            search_window=protocol.search_window,
        ),
        encoding="utf-8",
    )

    # Interop con herramientas OSS del ecosistema (docs/integraciones.md).
    interop_dir = deliverable / "interop"
    interop_dir.mkdir(parents=True, exist_ok=True)
    if assessments:
        (interop_dir / "robvis.csv").write_text(render_robvis_csv(assessments), encoding="utf-8")
    (interop_dir / "prisma2020_flow.csv").write_text(
        render_prisma2020_flow_csv(
            counts, meta_k=meta_result.k if meta_result is not None else None
        ),
        encoding="utf-8",
    )
    if meta_result is not None:
        (interop_dir / "effects_metafor.csv").write_text(
            render_metafor_csv(meta_result), encoding="utf-8"
        )
    return deliverable


def run_pipeline(
    protocol: ReviewProtocol,
    protocol_dir: str | Path,
    run_ctx: RunContext,
    *,
    max_results: int = 25,
    auto_approve: bool = False,
    mailto: str | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    embedder: Embedder | None = None,
    gold_labels: dict[str, bool] | None = None,
) -> PipelineResult:
    """Ejecuta el tracer bullet end-to-end y devuelve su resultado."""
    protocol_dir = Path(protocol_dir)
    ie = _load_yaml(protocol_dir / "inclusion_exclusion.yml")
    form = _load_yaml(protocol_dir / "extraction_form.yml")
    run = _Run(
        protocol=protocol,
        protocol_dir=protocol_dir,
        ctx=run_ctx,
        question=protocol.question.text,
        criteria=_criteria_to_text(ie),
        form_fields=form.get("fields", []),
        auto_approve=auto_approve,
        mailto=mailto,
    )

    raw_records = _search(run, max_results=max_results, search_fn=search_fn)
    deduped, discarded = _dedup(run, raw_records)
    decisions = _screen_ta(run, deduped, _load_gold(run, gold_labels))
    passed = {d.record_id for d in decisions if d.final_label in {"include", "unclear"}}
    excluded_ta = sum(1 for d in decisions if d.final_label == "exclude")
    ta_payload = {
        "n_screened": len(deduped),
        "n_pass": len(passed),
        "n_excluded": excluded_ta,
        "pass_ids": sorted(passed),
    }
    if (stop := run.stop(run.gate("screening_ta", ta_payload), "screening_ta")) is not None:
        return stop

    passed_ta = [r for r in deduped if r.record_id in passed]
    ft = _fulltext(run, passed_ta, fetch_fn)
    # Hasta PR-D un `unclear` de FT sigue pasando (lo resolverá un humano, D1).
    included_ids = {d.record_id for d in ft.decisions if d.final_label in {"include", "unclear"}}
    excluded_ft = sum(1 for d in ft.decisions if d.final_label == "exclude")
    ft_payload = {
        "n_buscados": len(passed_ta),
        "n_no_recuperados": ft.not_retrieved,
        "n_evaluados": len(passed_ta) - ft.not_retrieved,
        "n_incluidos": len(included_ids),
        "n_excluidos": excluded_ft,
    }
    if (stop := run.stop(run.gate("screening_ft", ft_payload), "screening_ft")) is not None:
        return stop
    included = [r for r in passed_ta if r.record_id in included_ids]

    # Desglose de exclusiones humano vs IA (PRISMA-trAIce) sobre ambas fases; el
    # de solo T/A alimenta la nota ** del flow diagram oficial (trAIce R1).
    exclusion_breakdown = compute_exclusion_breakdown(decisions + ft.decisions)
    run_ctx.write_json("03_screening/exclusions.json", exclusion_breakdown.model_dump())
    ta_breakdown = compute_exclusion_breakdown(decisions)
    # Informes excluidos en elegibilidad (16b) y sus razones (cajas "Reason 1..n"
    # del flow oficial): una sola lista para el diagrama, la tabla y el auditor.
    excluded_reports = compute_ft_excluded(ft.decisions, passed_ta)
    run_ctx.write_json("04_fulltext/excluded.json", [r.model_dump() for r in excluded_reports])
    ft_exclusion_reasons = dict(Counter(r.reason for r in excluded_reports))

    extractions, extraction_agreement = _extract(run, included)
    extraction_gate = run.gate("extraccion", {"n_extraidos": len(extractions)})
    if (stop := run.stop(extraction_gate, "extraccion")) is not None:
        return stop
    assessments = _assess_rob(run, included, extractions, ft.texts)
    rob_gate = run.gate("rob", {"n_evaluados": len(assessments), "tool": protocol.rob_tool})
    if (stop := run.stop(rob_gate, "rob")) is not None:
        return stop

    meta_result, meta_display = _meta_analysis(run)
    narrative, verification = _synthesize_and_verify(run, included, extractions, ft.texts, embedder)
    counts = _build_counts(
        raw_records=raw_records,
        deduped=deduped,
        discarded=discarded,
        excluded_ta=excluded_ta,
        ta_breakdown=ta_breakdown,
        passed_ta=passed_ta,
        ft=ft,
        excluded_ft=excluded_ft,
        excluded_reports=excluded_reports,
        ft_exclusion_reasons=ft_exclusion_reasons,
        included=included,
    )
    deliverable = _write_deliverables(
        run,
        counts=counts,
        included=included,
        extractions=extractions,
        assessments=assessments,
        narrative=narrative,
        excluded_reports=excluded_reports,
        exclusion_breakdown=exclusion_breakdown,
        extraction_agreement=extraction_agreement,
        meta_result=meta_result,
        meta_display=meta_display,
    )

    # Checkpoint final del reporte (A1).
    final_gate = run.gate(
        "reporte",
        {
            "included": len(included),
            "hallucination_flagged": verification.hallucination_flagged,
            "deliverable": str(deliverable),
        },
    )
    manifest_extra: dict = {
        "verification": verification.model_dump(),
        "risk_of_bias": {k: v.model_dump() for k, v in assessments.items()},
        "exclusions": exclusion_breakdown.model_dump(),
    }
    if run.metrics is not None:
        manifest_extra["screening_metrics"] = run.metrics.model_dump()
    if extraction_agreement is not None:
        manifest_extra["extraction_agreement"] = extraction_agreement.model_dump()
    if meta_result is not None:
        manifest_extra["meta_analysis"] = meta_result.model_dump()
    run_ctx.write_manifest(
        protocol_snapshot=protocol.model_dump(mode="json"),
        counts=counts.model_dump(),
        extra=manifest_extra,
    )
    # Un reporte rechazado ya no se informa como "completed" (auditoría
    # 2026-09-03, C1): el manifiesto queda escrito arriba como rastro.
    status, message, stage = final_gate.status, final_gate.message, "reporte"
    if final_gate.status == "approved":
        status = "completed"
        message = f"Revisión completada · {counts.included} estudios incluidos."
        stage = None
    return PipelineResult(
        status=status,
        message=message,
        counts=counts,
        included=included,
        narrative=narrative,
        hallucination_flagged=verification.hallucination_flagged,
        metrics=run.metrics,
        run_dir=run_ctx.run_dir,
        stage=stage,
    )
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_pipeline_fake.py -v`
Expected: PASS, 8 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, **412 recogidos** (el refactor no cambia ningún resultado: los 411 anteriores siguen verdes sin tocarlos).

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/pipeline.py tests/test_pipeline_fake.py
git commit -m "refactor(pipeline): _Run con gate/stop y una función por etapa" -m "Refactor puro previo a la reanudación (spec 2026-10-04 §7): los cinco bloques de checkpoint casi iguales pasan a _Run.gate()/_Run.stop() y cada etapa a su función (_search, _dedup, _screen_ta, _fulltext, _extract, _assess_rob, _synthesize_and_verify, _build_counts, _write_deliverables). run_pipeline conserva su firma; PipelineResult gana stage (el gate en el que se detuvo). Sin cambio de comportamiento: la suite sigue en verde." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Diario por etapa (`orchestration/journal.py`: `JournalError`, `StageJournal`)

**Files:**
- Create: `revisia/orchestration/journal.py`
- Test: `tests/test_journal.py` (nuevo)

**Interfaces:**
- Consumes: `JOURNAL_PATHS`, `JournalEntry`, `JournalStage` (PR-0, `revisia/schemas/artifacts.py`); `RunContext.run_dir` (solo el atributo; el tipo se importa bajo `TYPE_CHECKING`).
- Produces:
  - `class JournalError(ValueError)` — diario o `llm_calls.jsonl` inconsistente (rc 2 en el CLI, Tarea 17).
  - `read_jsonl(path: Path, model: type[ModelT]) -> list[ModelT]` — lee un JSONL append-only; una **última** línea que no valida se recorta del fichero (caída a mitad de escritura) y se ignora; una línea inválida antes de la última lanza `JournalError("<path>: línea <n> corrupta (<motivo>).")`; si a la última línea válida le falta el `\n`, se añade.
  - `append_jsonl(path: Path, item: BaseModel) -> None` — una línea, modo `"a"`, `newline="\n"`, `flush` y `os.fsync`.
  - `class StageJournal`: `__init__(self, run_ctx: RunContext, stage: JournalStage)`; atributos `stage`, `path` (`run_dir / JOURNAL_PATHS[stage]`); `lookup(record_id: str, input_sha256: str) -> JournalEntry | None`; `append(entry: JournalEntry) -> None`. Al cargar, dos líneas con la misma clave `(record_id, input_sha256)` y distinta `output`, o una entrada de otra etapa, lanzan `JournalError`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_journal.py`:

```python
"""Diario por etapa (Ola 1, D3; auditoría 2026-09-03, A9; spec 2026-10-04 §7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from revisia.orchestration.journal import JournalError, StageJournal
from revisia.orchestration.run_context import RunContext
from revisia.schemas.artifacts import JournalEntry


def _entrada(record_id: str, *, salida: str = "include") -> JournalEntry:
    return JournalEntry(
        stage="screening_ta",
        record_id=record_id,
        input_sha256="in-1",
        output={"record_id": record_id, "ensemble_label": salida},
    )


def test_journal_recupera_ultima_linea_truncada(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    diario = StageJournal(ctx, "screening_ta")
    diario.append(_entrada("a"))
    diario.append(_entrada("b"))
    with diario.path.open("ab") as fh:  # caída a mitad de escribir la tercera línea
        fh.write(b'{"schema_version": 1, "stage": "screening_ta", "rec')

    recargado = StageJournal(ctx, "screening_ta")
    assert recargado.lookup("a", "in-1") is not None
    assert recargado.lookup("b", "in-1") is not None
    recargado.append(_entrada("c"))

    lineas = diario.path.read_text(encoding="utf-8").splitlines()
    assert [JournalEntry.model_validate_json(x).record_id for x in lineas] == ["a", "b", "c"]


def test_journal_linea_corrupta_intermedia_es_error(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    diario = StageJournal(ctx, "screening_ta")
    diario.append(_entrada("a"))
    with diario.path.open("ab") as fh:
        fh.write(b"esto no es json\n")
    diario.append(_entrada("b"))
    with pytest.raises(JournalError, match="línea 2 corrupta"):
        StageJournal(ctx, "screening_ta")


def test_journal_misma_clave_y_distinta_salida_es_error(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    diario = StageJournal(ctx, "screening_ta")
    diario.append(_entrada("a"))
    diario.append(_entrada("a", salida="exclude"))  # editado a mano: dos verdades
    with pytest.raises(JournalError, match="distinta salida"):
        StageJournal(ctx, "screening_ta")
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_journal.py -v`
Expected: ERROR de colección, `ModuleNotFoundError: No module named 'revisia.orchestration.journal'`.

- [ ] **Step 3: Implementar** — crear `revisia/orchestration/journal.py`:

```python
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
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ValidationError

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
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_journal.py -v`
Expected: PASS, 3 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 415 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/journal.py tests/test_journal.py
git commit -m "feat(orchestration): diario por etapa con recorte de la última línea truncada" -m "StageJournal guarda una línea JournalEntry por registro, clave (record_id, input_sha256), con flush y fsync. Al cargar recorta una última línea truncada (caída a mitad de escritura) y da JournalError ante una línea corrupta en medio o dos salidas distintas para la misma clave. Base de la reanudación (D3; auditoría 2026-09-03, A9)." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `RunContext` con `llm_calls.jsonl`, JSON atómico y carpeta nueva de verdad

**Files:**
- Modify: `revisia/orchestration/run_context.py` (fichero completo)
- Modify: `revisia/orchestration/pipeline.py` (import de `GATED_STAGES` l.69; las seis llamadas a `record_meta` en `_screen_ta`, `_fulltext`, `_extract`, `_assess_rob` y `_synthesize_and_verify`; la llamada a `write_manifest` al final de `run_pipeline`)
- Test: `tests/test_run_context.py` (nuevo); `tests/test_pipeline_fake.py` (import l.10-11; un test nuevo al final)

**Interfaces:**
- Consumes: `read_jsonl`, `append_jsonl` (Tarea 2); `LLMCall`, `LLMStage`, `GATED_STAGES` (PR-0).
- Produces:
  - `PROVENANCE_PIPELINE = "pipeline"` (sin cambios), `LLM_CALLS_FILE = "llm_calls.jsonl"`.
  - `class RunDirExistsError(FileExistsError)` — `RunContext(slug, runs_root, timestamp)` la lanza si la carpeta existe y no está vacía; el mensaje sugiere `revisia run --resume <run_dir>`. Una carpeta vacía se acepta.
  - `class RunInterrupted(RuntimeError)`: `__init__(self, run_dir: str | Path, stage: str | None, error: str)`; atributos `run_dir: Path`, `stage`, `error`; `str(exc)` = `"corrida interrumpida en '<stage>': <error>. Reanuda con: revisia run --resume <run_dir>"`.
  - `RunContext`: atributos `slug`, `timestamp`, `run_dir`, `ledger`, `llm_calls_path`, `metas: list[LLMCall]` (cargadas de `llm_calls.jsonl` al construir); `record_meta(meta: RunMeta, *, stage: LLMStage, record_id: str | None = None, role: str | None = None) -> LLMCall` (escribe la línea al instante y la añade a `metas`); `write_text(relpath, content) -> Path` y `write_json(relpath, data) -> Path` atómicos (temporal `<nombre>.tmp` + `os.replace`); `write_manifest(*, protocol_snapshot: dict, counts: dict, autonomy_effective: dict[str, str] | None = None, final_gate: dict | None = None, extra: dict | None = None) -> Path`.
  - `manifest.yml`: primeras claves sin cambios (`slug, created_utc, timestamp, provenance, protocol, counts, llm_calls, models_used, deterministic_token_level`); `llm_calls` = todas las líneas de `llm_calls.jsonl` en orden; añade `autonomy_effective` (`{}` si no se pasa) y `final_gate` (`{"forced_human": false, "reason": null}` si no se pasa). El bloque `run` llega en la Tarea 5.
  - En el pipeline, cada `LLMCall` lleva su etapa: T/A `stage="screening_ta"`, `record_id`, `role="member:<i>"`; FT `"screening_ft"`; extracción `"extraccion"`; 2.º extractor `"extraccion_2"`; RoB `"rob"`; síntesis `stage="sintesis", record_id="sintesis"`. El manifiesto recibe `autonomy_effective={g: protocol.autonomy_for(g) for g in GATED_STAGES}` y `final_gate={"forced_human": False, "reason": None}`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_run_context.py`:

```python
"""RunContext de la Ola 1: llamadas a disco al registrarlas, JSON atómico y carpeta
nueva de verdad (auditoría 2026-09-03, A9; spec 2026-10-04 §7)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from revisia.orchestration.run_context import RunContext, RunDirExistsError, RunInterrupted
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.artifacts import LLMCall


def _meta(model: str = "fake-1") -> RunMeta:
    return RunMeta(
        provider="fake",
        model=model,
        temperature=0.0,
        prompt_sha256=sha256_text("p"),
        response_sha256=sha256_text("r"),
        deterministic=True,
    )


def test_run_context_vuelca_llm_calls_al_registrar(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    call = ctx.record_meta(_meta(), stage="screening_ta", record_id="10.1/x", role="member:0")

    # En disco al volver, sin esperar al manifiesto (antes se perdían con un 429).
    lineas = ctx.llm_calls_path.read_text(encoding="utf-8").splitlines()
    assert [LLMCall.model_validate_json(x) for x in lineas] == [call]
    assert (call.stage, call.record_id, call.role) == ("screening_ta", "10.1/x", "member:0")
    assert ctx.metas == [call]

    # El manifiesto toma las llamadas del fichero: también las de otra invocación.
    otra = LLMCall.from_meta(_meta("fake-2"), stage="sintesis", record_id="sintesis")
    with ctx.llm_calls_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(otra.model_dump_json() + "\n")
    manifest = yaml.safe_load(
        ctx.write_manifest(protocol_snapshot={}, counts={}).read_text(encoding="utf-8")
    )
    assert [c["model"] for c in manifest["llm_calls"]] == ["fake-1", "fake-2"]
    assert manifest["models_used"] == ["fake:fake-1", "fake:fake-2"]
    assert manifest["final_gate"] == {"forced_human": False, "reason": None}
    assert not list(tmp_path.rglob("*.tmp"))  # escritura atómica, sin restos


def test_run_context_nuevo_no_reutiliza_carpeta_existente(tmp_path: Path) -> None:
    RunContext("demo", tmp_path, "T").write_json("03_screening/decisions.json", [])
    with pytest.raises(RunDirExistsError, match="--resume"):
        RunContext("demo", tmp_path, "T")
    # Una carpeta vacía (creada a mano antes de correr) sí se puede usar.
    (tmp_path / "demo-VACIA").mkdir()
    assert RunContext("demo", tmp_path, "VACIA").run_dir == tmp_path / "demo-VACIA"


def test_run_interrupted_dice_como_reanudar(tmp_path: Path) -> None:
    exc = RunInterrupted(tmp_path / "demo-T", "screening_ta", "RuntimeError: 429")
    assert (exc.stage, exc.error) == ("screening_ta", "RuntimeError: 429")
    assert f"revisia run --resume {tmp_path / 'demo-T'}" in str(exc)
```

En `tests/test_pipeline_fake.py`, sustituir

```python
import json
from pathlib import Path
```

por

```python
import json
from collections import Counter
from pathlib import Path
```

y añadir al final del fichero:

```python


def test_llm_calls_etiquetadas_por_etapa_y_registro(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T-CALLS")
    run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        auto_approve=True,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
    )
    lineas = (ctx.run_dir / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
    calls = [json.loads(x) for x in lineas]
    assert Counter(c["stage"] for c in calls) == {
        "screening_ta": 4,  # 2 registros × 2 miembros del ensemble
        "screening_ft": 2,
        "extraccion": 2,
        "extraccion_2": 1,
        "rob": 2,
        "sintesis": 1,
    }
    ta = [(c["record_id"], c["role"]) for c in calls if c["stage"] == "screening_ta"]
    assert ta == [
        ("rec-1", "member:0"),
        ("rec-1", "member:1"),
        ("rec-2", "member:0"),
        ("rec-2", "member:1"),
    ]
    manifest = yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["llm_calls"] == calls
    assert manifest["autonomy_effective"] == {
        "screening_ta": "A1",
        "screening_ft": "A0",
        "extraccion": "A0",
        "rob": "A0",
        "reporte": "A1",
    }
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_run_context.py tests/test_pipeline_fake.py -v`
Expected: ERROR de colección en `tests/test_run_context.py` (`ImportError: cannot import name 'RunDirExistsError'`) y FAIL en `test_llm_calls_etiquetadas_por_etapa_y_registro` (`FileNotFoundError`: no existe `llm_calls.jsonl`).

- [ ] **Step 3: Implementar `RunContext`** — sustituir `revisia/orchestration/run_context.py` completo por:

```python
"""Contexto de una corrida · carpeta ``runs/<slug>-<fecha>/`` reproducible.

Centraliza dónde se escriben los artefactos de una ejecución, registra cada
llamada a IA y escribe el ``manifest.yml`` que permite a otro investigador
reproducir (o entender la no-reproducibilidad de) la corrida.

Ola 1 (spec 2026-10-04 §7; auditoría 2026-09-03, A9): cada llamada llega a
``llm_calls.jsonl`` en cuanto se registra, no al final con el manifiesto (un
429 a mitad de corrida ya no las pierde); los JSON se escriben de forma atómica
y una corrida nueva nunca reutiliza una carpeta con contenido.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from revisia.orchestration.journal import append_jsonl, read_jsonl
from revisia.provenance.ledger import DecisionLedger
from revisia.provenance.runmeta import RunMeta, utc_now_iso
from revisia.schemas.artifacts import LLMCall, LLMStage

# Procedencia que el motor escribe en todo manifiesto que produce (auditoría
# 2026-09-03, C3): distingue una corrida real de una reconstrucción a mano.
PROVENANCE_PIPELINE = "pipeline"
# Llamadas a IA de la corrida, una línea `LLMCall` por llamada (spec §4.2).
LLM_CALLS_FILE = "llm_calls.jsonl"


class RunDirExistsError(FileExistsError):
    """La carpeta de una corrida nueva ya existe y tiene contenido.

    Con diarios, dos ``revisia run`` en el mismo segundo compartirían carpeta y
    el segundo reanudaría en silencio la corrida del primero.
    """


class RunInterrupted(RuntimeError):
    """La corrida se detuvo por un error a mitad (red, 429, bug): se reanuda (D14).

    Attributes:
        run_dir: carpeta de la corrida interrumpida.
        stage: etapa en curso cuando ocurrió el error.
        error: error original, redactado.
    """

    def __init__(self, run_dir: str | Path, stage: str | None, error: str) -> None:
        self.run_dir = Path(run_dir)
        self.stage = stage
        self.error = error
        donde = f" en '{stage}'" if stage else ""
        super().__init__(
            f"corrida interrumpida{donde}: {error}. "
            f"Reanuda con: revisia run --resume {self.run_dir}"
        )


class RunContext:
    """Estado y rutas de una ejecución concreta del pipeline."""

    def __init__(self, slug: str, runs_root: str | Path, timestamp: str) -> None:
        run_dir = Path(runs_root) / f"{slug}-{timestamp}"
        if run_dir.exists() and any(run_dir.iterdir()):
            raise RunDirExistsError(
                f"{run_dir} ya existe y no está vacía: una corrida nueva no reutiliza la "
                f"carpeta de otra. Para continuarla: revisia run --resume {run_dir}"
            )
        run_dir.mkdir(parents=True, exist_ok=True)
        self._setup(slug, timestamp, run_dir)

    def _setup(self, slug: str, timestamp: str, run_dir: Path) -> None:
        self.slug = slug
        self.timestamp = timestamp
        self.run_dir = run_dir
        self.ledger = DecisionLedger(run_dir / "decisions_ledger.jsonl")
        self.llm_calls_path = run_dir / LLM_CALLS_FILE
        self.metas: list[LLMCall] = read_jsonl(self.llm_calls_path, LLMCall)

    def stage_dir(self, name: str) -> Path:
        path = self.run_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def deliverable_dir(self) -> Path:
        path = self.run_dir / "deliverable"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def record_meta(
        self,
        meta: RunMeta,
        *,
        stage: LLMStage,
        record_id: str | None = None,
        role: str | None = None,
    ) -> LLMCall:
        """Registra una llamada a IA y la escribe al instante en ``llm_calls.jsonl``."""
        call = LLMCall.from_meta(meta, stage=stage, record_id=record_id, role=role)
        append_jsonl(self.llm_calls_path, call)
        self.metas.append(call)
        return call

    def write_text(self, relpath: str, content: str) -> Path:
        """Escribe un fichero de texto de forma atómica (temporal + ``os.replace``).

        Una caída a mitad nunca deja un JSON o YAML a medias: o queda el
        anterior o el nuevo.
        """
        path = self.run_dir / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
        return path

    def write_json(self, relpath: str, data: object) -> Path:
        return self.write_text(relpath, json.dumps(data, ensure_ascii=False, indent=2))

    def write_manifest(
        self,
        *,
        protocol_snapshot: dict,
        counts: dict,
        autonomy_effective: dict[str, str] | None = None,
        final_gate: dict | None = None,
        extra: dict | None = None,
    ) -> Path:
        """Escribe ``manifest.yml`` con todo lo necesario para reproducir.

        ``llm_calls`` sale de ``llm_calls.jsonl`` (todas las líneas, en orden),
        no de memoria: una corrida reanudada incluye las llamadas de todas sus
        invocaciones. Bloques de la Ola 1 (spec §4.3): ``autonomy_effective``
        (autonomía con la que se aplicó cada gate) y ``final_gate``.
        """
        calls = read_jsonl(self.llm_calls_path, LLMCall)
        manifest = {
            "slug": self.slug,
            "created_utc": utc_now_iso(),
            "timestamp": self.timestamp,
            "provenance": PROVENANCE_PIPELINE,
            "protocol": protocol_snapshot,
            "counts": counts,
            "llm_calls": [c.model_dump(mode="json") for c in calls],
            "models_used": sorted({f"{c.provider}:{c.model}" for c in calls}),
            "deterministic_token_level": (all(c.deterministic for c in calls) if calls else True),
            "autonomy_effective": dict(autonomy_effective or {}),
            "final_gate": dict(final_gate or {"forced_human": False, "reason": None}),
            **(extra or {}),
        }
        # La procedencia no es configurable desde `extra`: la fija el motor.
        manifest["provenance"] = PROVENANCE_PIPELINE
        return self.write_text(
            "manifest.yml", yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
        )
```

- [ ] **Step 4: Etiquetar las llamadas en el pipeline.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.schemas.artifacts import ExcludedReport, RetrievalOutcome
```

por

```python
from revisia.schemas.artifacts import GATED_STAGES, ExcludedReport, RetrievalOutcome
```

En `_screen_ta`, sustituir

```python
        decisions.append(decision)
        for meta in metas:
            run.ctx.record_meta(meta)
```

por

```python
        decisions.append(decision)
        for i, meta in enumerate(metas):
            run.ctx.record_meta(
                meta, stage="screening_ta", record_id=record.record_id, role=f"member:{i}"
            )
```

En `_fulltext`, sustituir

```python
        ft_decisions.append(decision)
        run.ctx.record_meta(meta)
```

por

```python
        ft_decisions.append(decision)
        run.ctx.record_meta(meta, stage="screening_ft", record_id=record.record_id)
```

En `_extract`, sustituir

```python
        extractions[record.record_id] = extraction
        run.ctx.record_meta(meta)
```

por

```python
        extractions[record.record_id] = extraction
        run.ctx.record_meta(meta, stage="extraccion", record_id=record.record_id)
```

y

```python
            secondary[record.record_id] = extraction2
            run.ctx.record_meta(meta2)
```

por

```python
            secondary[record.record_id] = extraction2
            run.ctx.record_meta(meta2, stage="extraccion_2", record_id=record.record_id)
```

En `_assess_rob`, sustituir

```python
        assessments[record.record_id] = assessment
        run.ctx.record_meta(meta)
```

por

```python
        assessments[record.record_id] = assessment
        run.ctx.record_meta(meta, stage="rob", record_id=record.record_id)
```

En `_synthesize_and_verify`, sustituir

```python
        seed=synth_cfg.seed,
    )
    run.ctx.record_meta(meta)
```

por

```python
        seed=synth_cfg.seed,
    )
    run.ctx.record_meta(meta, stage="sintesis", record_id="sintesis")
```

Y al final de `run_pipeline`, sustituir

```python
        counts=counts.model_dump(),
        extra=manifest_extra,
    )
```

por

```python
        counts=counts.model_dump(),
        autonomy_effective={g: protocol.autonomy_for(g) for g in GATED_STAGES},
        final_gate={"forced_human": False, "reason": None},
        extra=manifest_extra,
    )
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_run_context.py tests/test_pipeline_fake.py tests/test_provenance.py -v`
Expected: PASS (`test_write_manifest_declara_procedencia_no_sobrescribible` sigue en verde: los parámetros nuevos de `write_manifest` tienen default).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 419 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/orchestration/run_context.py revisia/orchestration/pipeline.py tests/test_run_context.py tests/test_pipeline_fake.py
git commit -m "feat(run_context): llm_calls.jsonl al registrar, JSON atómico y carpeta nueva de verdad (A9)" -m "Cada llamada a IA llega a llm_calls.jsonl en cuanto se registra, como LLMCall con su etapa, registro y rol; antes solo llegaba a disco con el manifiesto y un 429 la perdía. write_text/write_json escriben vía temporal + os.replace. RunContext da RunDirExistsError ante una carpeta con contenido. RunInterrupted lleva la orden de reanudar. El manifiesto toma llm_calls del fichero y añade autonomy_effective y final_gate (spec 2026-10-04 §4.3, §7)." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `journaled`: llamadas registradas antes que el diario

**Files:**
- Modify: `revisia/orchestration/journal.py` (imports; función nueva al final)
- Test: `tests/test_journal.py` (imports; dos tests nuevos al final)

**Interfaces:**
- Consumes: `StageJournal` (Tarea 2); `RunContext.record_meta` (Tarea 3); `canonical_sha256`, `RunMeta` (`revisia/provenance/runmeta.py`); `ScriptedProvider` (`tests/fakes.py`, PR-0).
- Produces: `journaled(journal: StageJournal, *, record_id: str, inputs: object, model: type[ModelT], compute: Callable[[], tuple[ModelT, list[RunMeta]]], run_ctx: RunContext, role_of: Callable[[int], str] | None = None) -> ModelT`. `input_sha256 = canonical_sha256(inputs)`; si el diario tiene `(record_id, input_sha256)`, devuelve `model.model_validate(entry.output)` sin llamar a nada; si no, `compute()` → `run_ctx.record_meta(meta, stage=journal.stage, record_id=record_id, role=role_of(i))` por cada meta → `journal.append(JournalEntry(..., output=value.model_dump(mode="json"), metas=calls))`. Un `inputs` distinto deja la entrada vieja como obsoleta (sigue en el fichero) y recalcula.

- [ ] **Step 1: Tests que fallan.** En `tests/test_journal.py`, sustituir los imports

```python
import pytest

from revisia.orchestration.journal import JournalError, StageJournal
from revisia.orchestration.run_context import RunContext
from revisia.schemas.artifacts import JournalEntry
```

por

```python
import pytest
from fakes import ScriptedProvider

from revisia.agents.screening import ScreenerMember, screen_record
from revisia.orchestration.journal import JournalError, StageJournal, journaled
from revisia.orchestration.run_context import RunContext
from revisia.schemas.artifacts import JournalEntry, LLMCall
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision
```

y añadir al final del fichero:

```python


def _cribado(proveedor: ScriptedProvider, criterios: str):
    """``compute`` de un cribado T/A de un solo miembro sobre el registro "a"."""
    miembro = ScreenerMember(provider=proveedor, model_name="fake:guion")
    registro = SearchRecord(record_id="a", title="Estudio a")
    return lambda: screen_record([miembro], question="¿X?", criteria=criterios, record=registro)


def _cribar(ctx: RunContext, proveedor: ScriptedProvider, criterios: str) -> ScreeningDecision:
    return journaled(
        StageJournal(ctx, "screening_ta"),
        record_id="a",
        inputs={"criteria": criterios},
        model=ScreeningDecision,
        compute=_cribado(proveedor, criterios),
        run_ctx=ctx,
        role_of=lambda i: f"member:{i}",
    )


def test_journal_entrada_obsoleta_por_input_sha_se_recalcula(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    proveedor = ScriptedProvider()
    primera = _cribar(ctx, proveedor, "c1")
    assert _cribar(ctx, proveedor, "c1") == primera  # del diario, sin llamar
    assert proveedor.calls == 1

    # Cambian los criterios: la entrada vieja queda obsoleta y se recalcula.
    _cribar(ctx, proveedor, "c2")
    assert proveedor.calls == 2
    lineas = StageJournal(ctx, "screening_ta").path.read_text("utf-8").splitlines()
    entradas = [JournalEntry.model_validate_json(x) for x in lineas]
    assert len(entradas) == 2  # la obsoleta sigue en el fichero: es válida
    assert entradas[0].input_sha256 != entradas[1].input_sha256

    # Cada meta del diario está, idéntica, en llm_calls.jsonl (spec §4.4, relación 12).
    lineas = ctx.llm_calls_path.read_text("utf-8").splitlines()
    llamadas = [LLMCall.model_validate_json(x) for x in lineas]
    assert [m for e in entradas for m in e.metas] == llamadas
    assert {(c.stage, c.record_id, c.role) for c in llamadas} == {("screening_ta", "a", "member:0")}


def test_journaled_registra_las_llamadas_antes_que_el_diario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = RunContext("demo", tmp_path, "T")

    def _caida(self, entry) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(StageJournal, "append", _caida)
    with pytest.raises(OSError):
        _cribar(ctx, ScriptedProvider(), "c1")
    # La llamada ya está en llm_calls.jsonl (huérfana, válida); el diario, vacío.
    assert len(ctx.llm_calls_path.read_text("utf-8").splitlines()) == 1
    assert not StageJournal(ctx, "screening_ta").path.exists()
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_journal.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'journaled' from 'revisia.orchestration.journal'`.

- [ ] **Step 3: Implementar.** En `revisia/orchestration/journal.py`, sustituir

```python
import os
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ValidationError

from revisia.schemas.artifacts import JOURNAL_PATHS, JournalEntry, JournalStage
```

por

```python
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ValidationError

from revisia.provenance.runmeta import RunMeta, canonical_sha256
from revisia.schemas.artifacts import JOURNAL_PATHS, JournalEntry, JournalStage
```

y añadir al final del fichero:

```python


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
        return model.model_validate(entry.output)
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
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_journal.py -v`
Expected: PASS, 5 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 421 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/journal.py tests/test_journal.py
git commit -m "feat(orchestration): journaled registra las llamadas antes que la decisión" -m "journaled calcula input_sha256 = canonical_sha256(inputs), devuelve la salida del diario si existe y, si no, llama, registra cada RunMeta en llm_calls.jsonl y solo después escribe la línea del diario: una caída deja llamadas huérfanas, nunca una decisión sin sus llamadas (spec 2026-10-04 §7). Un inputs distinto deja obsoleta la entrada anterior." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Instantánea del protocolo y `run.json` (`orchestration/snapshot.py`)

**Files:**
- Create: `revisia/orchestration/snapshot.py`
- Modify: `revisia/orchestration/run_context.py` (import l.24; constante tras `LLM_CALLS_FILE` l.30; clase nueva tras `RunDirExistsError` l.37-38; `RunContext.open` tras `__init__` l.71-72; bloque `run` en `write_manifest` l.136-148)
- Modify: `revisia/config.py` (`load_protocol`, l.148-162)
- Modify: `revisia/orchestration/pipeline.py` (import l.66-67; campos de `_Run` l.175-180; `_search` l.224-226; `_load_gold` l.243-248; `_meta_analysis` l.446; cabecera de `run_pipeline` l.645-663)
- Test: `tests/test_snapshot.py` (nuevo)

**Interfaces:**
- Consumes: `RunInfo` (PR-0); `RunContext` (Tarea 3); `revisia.__version__`.
- Produces:
  - `revisia.orchestration.snapshot`: `SNAPSHOT_DIR = "00_protocol"`; `SNAPSHOT_FILES = ("protocol.yml", "inclusion_exclusion.yml", "extraction_form.yml", "effects.yml", "gold.yml")` (más `search_strings/*.txt`); `SEARCH_STRINGS_DIR = "search_strings"`; `PROMPTS_DIR: Path` (= `revisia/prompts`, los tests lo parchean); `class ProtocolMismatchError(ValueError)` con `__init__(self, message: str, files: list[str] | None = None)` y atributo `files`; `protocol_fingerprint(protocol_dir: str | Path) -> dict[str, str]` (claves con `/`, SHA-256 del texto con CRLF→LF); `prompt_fingerprint() -> dict[str, str]` (claves `"<agente>/v1.md"`); `read_run_info(run_dir) -> RunInfo | None`; `write_run_info(run_dir, info: RunInfo) -> RunInfo` (atómica, pone `updated_utc`); `ensure_snapshot(protocol_dir: str | Path | None, run_ctx: RunContext, *, max_results: int, mailto: str | None) -> tuple[Path, RunInfo]`.
  - `ensure_snapshot` sin `run.json`: escribe `run.json` **primero** (`RunInfo(slug, timestamp, started_utc=ahora, engine_version=__version__, python_version=platform.python_version(), max_results, mailto_set=bool(mailto), protocol_sha256=protocol_fingerprint(protocol_dir), prompt_sha256=prompt_fingerprint(), status="running")`) y después copia a `00_protocol/` los ficheros de la huella. Con `run.json`: compara `00_protocol/`, los prompts del motor y, si se pasó, el `protocol_dir` original; cualquier diferencia lanza `ProtocolMismatchError` con los ficheros (`00_protocol/<f>`, `revisia/prompts/<f>`, `<protocol_dir>/<f>`); si todo coincide, añade la hora a `resumes`, `status="running"`, `stage=None`.
  - `revisia.orchestration.run_context`: `RUN_INFO_FILE = "run.json"`; `class LegacyRunError(ValueError)` (D13); `RunContext.open(run_dir: str | Path) -> RunContext` (slug y timestamp de `run.json`; `FileNotFoundError` si la carpeta no existe; `LegacyRunError("<run_dir>: corrida anterior a la Ola 1 (sin run.json); no se puede reanudar. Empieza una nueva con `revisia run <protocolo>`.")` si falta `run.json`). `manifest.yml` gana `run: {started_utc, resumes, engine_version, python_version, status}` cuando existe `run.json`.
  - `revisia.config.load_protocol(protocol_dir: str | Path, *, default_slug: str | None = None) -> ReviewProtocol` (slug: el declarado, o `default_slug`, o el nombre de la carpeta).
  - `run_pipeline(protocol, protocol_dir: str | Path | None, run_ctx, ...)`: llama a `ensure_snapshot` al empezar; criterios, formulario, gold y efectos salen de `00_protocol/`; `max_results` de `run.json`. `_Run` pasa a tener `snapshot_dir: Path` y `source_dir: Path | None` en lugar de `protocol_dir`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_snapshot.py`:

```python
"""Instantánea del protocolo y run.json (Ola 1, D3 y D13; spec 2026-10-04 §7)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from fakes import fetch_disponible

from revisia import __version__
from revisia.config import load_protocol
from revisia.orchestration import snapshot as snapshot_mod
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import LegacyRunError, RunContext
from revisia.orchestration.snapshot import (
    ProtocolMismatchError,
    prompt_fingerprint,
    protocol_fingerprint,
)
from revisia.schemas.artifacts import RunInfo
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _busqueda(query: str, n: int) -> list[SearchRecord]:
    return [
        SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex"),
        SearchRecord(record_id="rec-2", title="Active learning", source_db="OpenAlex"),
    ][:n]


def _run_info(ctx: RunContext) -> RunInfo:
    return RunInfo.model_validate_json((ctx.run_dir / "run.json").read_text(encoding="utf-8"))


def test_snapshot_y_run_json(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        max_results=10,
        auto_approve=True,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
    )

    instantanea = ctx.run_dir / "00_protocol"
    copiados = sorted(p.relative_to(instantanea).as_posix() for p in instantanea.rglob("*.*"))
    assert copiados == [
        "effects.yml",
        "extraction_form.yml",
        "inclusion_exclusion.yml",
        "protocol.yml",
        "search_strings/openalex.txt",
    ]
    info = _run_info(ctx)
    assert (info.slug, info.timestamp, info.max_results, info.mailto_set) == (
        "demo-mini-review",
        "T",
        10,
        False,
    )
    assert info.engine_version == __version__
    assert info.protocol_sha256 == protocol_fingerprint(EXAMPLE)
    assert info.protocol_sha256 == protocol_fingerprint(instantanea)
    assert set(info.prompt_sha256) == {
        "extraccion/v1.md",
        "reporte/v1.md",
        "rob/v1.md",
        "screening/v1.md",
        "screening_ft/v1.md",
    }
    assert info.resumes == []
    assert "mailto" not in json.loads((ctx.run_dir / "run.json").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["run"]["started_utc"] == info.started_utc
    assert manifest["run"]["engine_version"] == __version__


def test_huella_del_protocolo_ignora_crlf(tmp_path: Path) -> None:
    copia = tmp_path / "proto"
    shutil.copytree(EXAMPLE, copia)
    for path in [copia / "protocol.yml", copia / "search_strings" / "openalex.txt"]:
        texto = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        path.write_bytes(texto.replace("\n", "\r\n").encode("utf-8"))
    assert protocol_fingerprint(copia) == protocol_fingerprint(EXAMPLE)


def test_resume_con_prompt_modificado_falla(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda).status == "paused"

    prompts = tmp_path / "prompts"
    shutil.copytree(snapshot_mod.PROMPTS_DIR, prompts, ignore=shutil.ignore_patterns("*.py*"))
    cribado = prompts / "screening" / "v1.md"
    cribado.write_text(cribado.read_text(encoding="utf-8") + "\nNueva regla.\n", encoding="utf-8")
    monkeypatch.setattr(snapshot_mod, "PROMPTS_DIR", prompts)
    assert prompt_fingerprint() != _run_info(ctx).prompt_sha256

    with pytest.raises(ProtocolMismatchError, match="revisia/prompts/screening/v1.md") as exc:
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    assert exc.value.files == ["revisia/prompts/screening/v1.md"]


def test_resume_con_instantanea_alterada_falla(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    criterios = ctx.run_dir / "00_protocol" / "inclusion_exclusion.yml"
    criterios.write_text(criterios.read_text(encoding="utf-8") + "\n# editado\n", "utf-8")
    with pytest.raises(ProtocolMismatchError, match="00_protocol/inclusion_exclusion.yml"):
        run_pipeline(protocol, None, ctx, search_fn=_busqueda)


def test_run_context_open_y_slug_por_defecto(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)  # el demo no declara slug: sale de la carpeta
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)

    reabierto = RunContext.open(ctx.run_dir)
    assert (reabierto.slug, reabierto.timestamp, reabierto.run_dir) == (
        "demo-mini-review",
        "T",
        ctx.run_dir,
    )
    instantanea = ctx.run_dir / "00_protocol"
    assert load_protocol(instantanea).slug == "00_protocol"  # hallazgo 4 del spec (§2)
    assert load_protocol(instantanea, default_slug=reabierto.slug).slug == "demo-mini-review"

    antigua = tmp_path / "demo-v07"
    (antigua / "03_screening").mkdir(parents=True)
    with pytest.raises(LegacyRunError, match="anterior a la Ola 1"):
        RunContext.open(antigua)
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_snapshot.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'snapshot' from 'revisia.orchestration'`.

- [ ] **Step 3: Implementar el módulo** — crear `revisia/orchestration/snapshot.py`:

```python
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
```

- [ ] **Step 4: `RunContext.open`, `LegacyRunError` y el bloque `run`.** En `revisia/orchestration/run_context.py`, sustituir

```python
from revisia.schemas.artifacts import LLMCall, LLMStage
```

por

```python
from revisia.schemas.artifacts import LLMCall, LLMStage, RunInfo
```

sustituir

```python
LLM_CALLS_FILE = "llm_calls.jsonl"
```

por

```python
LLM_CALLS_FILE = "llm_calls.jsonl"
# Identidad, parámetros, huellas, historia y estado de la corrida (spec §4.3).
RUN_INFO_FILE = "run.json"
```

sustituir el final de la docstring de `RunDirExistsError`

```python
    el segundo reanudaría en silencio la corrida del primero.
    """
```

por

```python
    el segundo reanudaría en silencio la corrida del primero.
    """


class LegacyRunError(ValueError):
    """La carpeta no tiene ``run.json``: corrida anterior a la Ola 1 (D13).

    Sin instantánea del protocolo ni de la búsqueda, reanudarla obligaría a
    repetir la búsqueda con resultados distintos de los que ya se cribaron.
    """
```

sustituir

```python
        run_dir.mkdir(parents=True, exist_ok=True)
        self._setup(slug, timestamp, run_dir)
```

por

```python
        run_dir.mkdir(parents=True, exist_ok=True)
        self._setup(slug, timestamp, run_dir)

    @classmethod
    def open(cls, run_dir: str | Path) -> RunContext:
        """Reabre una corrida existente para reanudarla (slug y fecha de ``run.json``).

        Raises:
            FileNotFoundError: si la carpeta no existe.
            LegacyRunError: si no tiene ``run.json`` (corrida anterior a la Ola 1).
        """
        run_dir = Path(run_dir)
        if not run_dir.is_dir():
            raise FileNotFoundError(f"la carpeta {run_dir} no existe.")
        info_path = run_dir / RUN_INFO_FILE
        if not info_path.exists():
            raise LegacyRunError(
                f"{run_dir}: corrida anterior a la Ola 1 (sin run.json); no se puede reanudar. "
                "Empieza una nueva con `revisia run <protocolo>`."
            )
        info = RunInfo.model_validate_json(info_path.read_text(encoding="utf-8"))
        ctx = cls.__new__(cls)
        ctx._setup(info.slug, info.timestamp, run_dir)
        return ctx
```

y en `write_manifest`, sustituir

```python
        (autonomía con la que se aplicó cada gate) y ``final_gate``.
        """
        calls = read_jsonl(self.llm_calls_path, LLMCall)
```

por

```python
        (autonomía con la que se aplicó cada gate) y ``final_gate``, más ``run``
        (de ``run.json``) si la corrida lo tiene.
        """
        calls = read_jsonl(self.llm_calls_path, LLMCall)
        run_block: dict = {}
        info_path = self.run_dir / RUN_INFO_FILE
        if info_path.exists():
            info = RunInfo.model_validate_json(info_path.read_text(encoding="utf-8"))
            run_block["run"] = {
                "started_utc": info.started_utc,
                "resumes": list(info.resumes),
                "engine_version": info.engine_version,
                "python_version": info.python_version,
                "status": info.status,
            }
```

y

```python
            "deterministic_token_level": (all(c.deterministic for c in calls) if calls else True),
```

por

```python
            "deterministic_token_level": (all(c.deterministic for c in calls) if calls else True),
            **run_block,
```

- [ ] **Step 5: `load_protocol(default_slug=)`.** En `revisia/config.py`, sustituir

```python
def load_protocol(protocol_dir: str | Path) -> ReviewProtocol:
    """Carga y valida ``protocol.yml`` desde una carpeta de protocolo.

    Args:
        protocol_dir: carpeta que contiene ``protocol.yml``.

    Raises:
        FileNotFoundError: si no existe ``protocol.yml``.
    """
    base = Path(protocol_dir)
    protocol_file = base / "protocol.yml"
    if not protocol_file.exists():
        raise FileNotFoundError(f"No se encontró {protocol_file}.")
    raw = yaml.safe_load(protocol_file.read_text(encoding="utf-8")) or {}
    raw.setdefault("slug", base.name)
```

por

```python
def load_protocol(protocol_dir: str | Path, *, default_slug: str | None = None) -> ReviewProtocol:
    """Carga y valida ``protocol.yml`` desde una carpeta de protocolo.

    Args:
        protocol_dir: carpeta que contiene ``protocol.yml``.
        default_slug: slug si el protocolo no lo declara; por defecto, el
            nombre de la carpeta. Al reanudar se pasa el de ``run.json``: la
            instantánea vive en ``00_protocol/`` y ese nombre no es el slug.

    Raises:
        FileNotFoundError: si no existe ``protocol.yml``.
    """
    base = Path(protocol_dir)
    protocol_file = base / "protocol.yml"
    if not protocol_file.exists():
        raise FileNotFoundError(f"No se encontró {protocol_file}.")
    raw = yaml.safe_load(protocol_file.read_text(encoding="utf-8")) or {}
    raw.setdefault("slug", default_slug or base.name)
```

- [ ] **Step 6: El pipeline lee de `00_protocol/`.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.orchestration.run_context import RunContext
from revisia.provenance.runmeta import sha256_text
```

por

```python
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import ensure_snapshot
from revisia.provenance.runmeta import sha256_text
```

en `_Run`, sustituir

```python
    corrida se detiene (antes, cinco bloques casi iguales).
    """

    protocol: ReviewProtocol
    protocol_dir: Path
    ctx: RunContext
```

por

```python
    corrida se detiene (antes, cinco bloques casi iguales). ``snapshot_dir`` es
    ``00_protocol/``, la única fuente de criterios, formulario, efectos, gold y
    cadenas; ``source_dir`` es el protocolo original (``None`` al reanudar sin
    él).
    """

    protocol: ReviewProtocol
    snapshot_dir: Path
    source_dir: Path | None
    ctx: RunContext
```

en `_search` (provisional hasta la Tarea 6), sustituir

```python
    raw_records, failures = _multi_database_search(
        run.protocol, run.protocol_dir, run.question, max_results, run.mailto
    )
```

por

```python
    raw_records, failures = _multi_database_search(
        run.protocol, run.source_dir or run.snapshot_dir, run.question, max_results, run.mailto
    )
```

en `_load_gold`, sustituir

```python
    """Gold standard humano: ``gold.yml`` del protocolo + etiquetas por código.

    Las pasadas por código tienen prioridad sobre las del fichero.
    """
    gold: dict[str, bool] = {}
    gold_file = _load_yaml(run.protocol_dir / "gold.yml")
```

por

```python
    """Gold standard humano: ``00_protocol/gold.yml`` + etiquetas por código.

    Las pasadas por código tienen prioridad sobre las del fichero.
    """
    gold: dict[str, bool] = {}
    gold_file = _load_yaml(run.snapshot_dir / "gold.yml")
```

en `_meta_analysis`, sustituir

```python
    effects_cfg = _load_yaml(run.protocol_dir / "effects.yml")
```

por

```python
    effects_cfg = _load_yaml(run.snapshot_dir / "effects.yml")
```

y la cabecera de `run_pipeline`

```python
    protocol_dir: str | Path,
    run_ctx: RunContext,
    *,
    max_results: int = 25,
    auto_approve: bool = False,
    mailto: str | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    embedder: Embedder | None = None,
    gold_labels: dict[str, bool] | None = None,
) -> PipelineResult:
    """Ejecuta el tracer bullet end-to-end y devuelve su resultado."""
    protocol_dir = Path(protocol_dir)
    ie = _load_yaml(protocol_dir / "inclusion_exclusion.yml")
    form = _load_yaml(protocol_dir / "extraction_form.yml")
    run = _Run(
        protocol=protocol,
        protocol_dir=protocol_dir,
        ctx=run_ctx,
```

por

```python
    protocol_dir: str | Path | None,
    run_ctx: RunContext,
    *,
    max_results: int = 25,
    auto_approve: bool = False,
    mailto: str | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    embedder: Embedder | None = None,
    gold_labels: dict[str, bool] | None = None,
) -> PipelineResult:
    """Ejecuta el tracer bullet end-to-end y devuelve su resultado.

    Una corrida nueva copia el protocolo a ``00_protocol/`` y escribe
    ``run.json``; una que se reanuda (``run.json`` ya existe) verifica su
    instantánea y toma ``max_results`` de ``run.json``. ``protocol_dir`` puede
    ser ``None`` al reanudar.
    """
    snapshot_dir, run_info = ensure_snapshot(
        protocol_dir, run_ctx, max_results=max_results, mailto=mailto
    )
    max_results = run_info.max_results
    ie = _load_yaml(snapshot_dir / "inclusion_exclusion.yml")
    form = _load_yaml(snapshot_dir / "extraction_form.yml")
    run = _Run(
        protocol=protocol,
        snapshot_dir=snapshot_dir,
        source_dir=Path(protocol_dir) if protocol_dir is not None else None,
        ctx=run_ctx,
```

- [ ] **Step 7: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_snapshot.py -v`
Expected: PASS, 5 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 426 recogidos.

- [ ] **Step 8: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 9: Commit**

```bash
git add revisia/orchestration/snapshot.py revisia/orchestration/run_context.py revisia/config.py revisia/orchestration/pipeline.py tests/test_snapshot.py
git commit -m "feat(orchestration): instantánea del protocolo y run.json (D3, D13)" -m "Una corrida nueva escribe run.json (identidad, parámetros, huellas del protocolo y de los prompts con CRLF→LF, estado) y copia el protocolo a 00_protocol/, que pasa a ser la única fuente de criterios, formulario, efectos, gold y cadenas. Al reanudar, cualquier diferencia en 00_protocol/, en los prompts o en el protocolo original da ProtocolMismatchError con la lista de ficheros. RunContext.open reabre una corrida y da LegacyRunError sin run.json; load_protocol acepta default_slug. Spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Búsqueda congelada en `01_search/` con registro por base (`orchestration/search_stage.py`, M12)

**Files:**
- Create: `revisia/orchestration/search_stage.py`
- Modify: `revisia/ingest/manual_import.py` (imports l.15-16; `import_directory` l.104-116)
- Modify: `revisia/ingest/__init__.py` (l.5-11)
- Modify: `revisia/orchestration/pipeline.py` (imports l.26-27, l.61-62 y l.66-67; cuerpo de `_multi_database_search` l.122-153; `_search` l.222-239)
- Test: `tests/test_search_stage.py` (nuevo)

**Interfaces:**
- Consumes: `SearchLog`, `SearchLogEntry`, `QueryOrigin` (PR-0); `search_backends.db_key`, `BACKENDS`, `MANUAL_ONLY`, `search_database` (este último **por el módulo**, para que los tests lo parcheen); `_http.redact_secrets`; `SNAPSHOT_DIR`, `SEARCH_STRINGS_DIR`, `ProtocolMismatchError` (Tarea 5).
- Produces:
  - `revisia.ingest.manual_import.IMPORT_SUFFIXES = (".ris", ".bib", ".bibtex")`; `import_file(path: str | Path) -> list[SearchRecord]` (UTF-8; `ValueError` con otra extensión; `UnicodeDecodeError` con un RIS en UTF-16). `import_directory` la usa; `revisia.ingest` la reexporta.
  - `revisia.orchestration.search_stage`: `SEARCH_DIR = "01_search"`; `multi_database_search(protocol, *, strings_dir: Path, imported_dir: Path | None, question: str, max_results: int, mailto: str | None) -> tuple[list[SearchRecord], list[SearchLogEntry]]`; `run_search(protocol, *, source_dir: Path | None, strings_dir: Path, question: str, max_results: int, mailto: str | None, search_fn: SearchFn | None, run_ctx: RunContext) -> list[SearchRecord]`.
  - Una `SearchLogEntry` por base declarada (`kind="database"`, `declared=True`; sin bases, `database="openalex"` con `declared=False`): con backend, `backend="<módulo>.<función>"` (`"busqueda.search"` para OpenAlex), `query`/`query_origin` (`"file"` si `search_strings/<db_key>.txt` existe y no está vacío; si no, `"question_fallback"` con la pregunta), `query_file="00_protocol/search_strings/<db_key>.txt"` o `None`, `query_sha256=sha256_text(query)`, `max_results`, horas, `n_returned`, `source_db` (valores distintos devueltos), `status` `ok` o `failed` con `error` redactado; manual (`MANUAL_ONLY`), `status="manual_only"` y la cadena solo si hay fichero; desconocida, `status="unknown"` con `error`. Una entrada por fichero `.ris/.bib/.bibtex` de `imported/` (`database="imported/<fichero>"`, `db_key="imported"`, `kind="manual_import"`, `declared=True`, `file_sha256` de los bytes; un fichero ilegible queda `failed` y la corrida sigue). Con `search_fn`, una sola entrada `database="search_fn"`, `db_key="search_fn"`, `kind="injected"`, `declared=False`, `backend=<nombre de la función>`, `query=<pregunta>`, `query_origin=None`.
  - `run_search`: si existe `01_search/log.json`, devuelve `01_search/records.json` sin llamar a nada (tampoco a `search_fn`); si no, busca y escribe en este orden `records.json` (antes del dedup), `log.json` y, solo si alguna entrada falló, `failures.json` = `[{"db": database, "error": error}]`. Sin `source_dir` y sin log: `ProtocolMismatchError` (hace falta `imported/`).
  - `pipeline._multi_database_search(protocol, protocol_dir, question_text, max_results, mailto)` conserva firma y tupla `(registros, fallos)`: es un envoltorio de `multi_database_search` con las cadenas de `protocol_dir/search_strings`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_search_stage.py`:

```python
"""Búsqueda con registro por base y congelada en 01_search/ (auditoría 2026-09-03,
M12 y M7; spec 2026-10-04 §7)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from revisia.agents import search_backends
from revisia.config import load_protocol
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.search_stage import run_search
from revisia.provenance.runmeta import sha256_text
from revisia.schemas.artifacts import SearchLog
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"

_RIS = "TY  - JOUR\nTI  - Estudio importado de Scopus\nDO  - 10.9/scopus\nER  -\n"


def _protocolo(tmp_path: Path, databases: list[str]) -> Path:
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["databases"] = databases
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    (proto / "search_strings" / "openalex.txt").write_text("cadena openalex\n", encoding="utf-8")
    return proto


def _log(ctx: RunContext) -> SearchLog:
    return SearchLog.model_validate_json(
        (ctx.run_dir / "01_search" / "log.json").read_text(encoding="utf-8")
    )


def test_search_log_por_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proto = _protocolo(tmp_path, ["OpenAlex", "Europe PMC", "BVS", "Scopus"])
    (proto / "imported").mkdir()
    (proto / "imported" / "scopus.ris").write_text(_RIS, encoding="utf-8")

    def fake_search_database(db, query, max_results, *, mailto=None):
        if db == "BVS":
            raise RuntimeError("503 para https://bvs.example/?q=x&api_key=SECRETO")
        n = 2 if db == "OpenAlex" else 1
        fuente = "OpenAlex" if db == "OpenAlex" else "EuropePMC"
        return [
            SearchRecord(record_id=f"{db}:{i}", title=f"{db} {i}", source_db=fuente)
            for i in range(n)
        ]

    monkeypatch.setattr(search_backends, "search_database", fake_search_database)
    ctx = RunContext("demo", tmp_path / "runs", "T")
    records = run_search(
        load_protocol(proto),
        source_dir=proto,
        strings_dir=proto / "search_strings",
        question="pregunta del protocolo",
        max_results=7,
        mailto=None,
        search_fn=None,
        run_ctx=ctx,
    )

    log = _log(ctx)
    por_base = {e.database: e for e in log.entries}
    assert list(por_base) == ["OpenAlex", "Europe PMC", "BVS", "Scopus", "imported/scopus.ris"]
    openalex = por_base["OpenAlex"]
    assert (openalex.kind, openalex.status, openalex.n_returned) == ("database", "ok", 2)
    assert (openalex.query, openalex.query_origin) == ("cadena openalex", "file")
    assert openalex.query_file == "00_protocol/search_strings/openalex.txt"
    assert openalex.query_sha256 == sha256_text("cadena openalex")
    assert (openalex.backend, openalex.max_results) == ("busqueda.search", 7)
    assert openalex.started_utc and openalex.finished_utc
    europe = por_base["Europe PMC"]
    assert (europe.query, europe.query_origin, europe.query_file) == (
        "pregunta del protocolo",
        "question_fallback",
        None,
    )
    assert europe.source_db == ["EuropePMC"]
    bvs = por_base["BVS"]
    assert (bvs.status, bvs.n_returned) == ("failed", 0)
    assert "api_key=<redacted>" in bvs.error and "SECRETO" not in bvs.error
    assert por_base["Scopus"].status == "manual_only"
    importado = por_base["imported/scopus.ris"]
    assert (importado.kind, importado.status, importado.n_returned) == ("manual_import", "ok", 1)
    ris_bytes = (proto / "imported" / "scopus.ris").read_bytes()
    assert importado.file_sha256 == hashlib.sha256(ris_bytes).hexdigest()

    # records.json = lo devuelto; Σ n_returned de las entradas ok (relación 1).
    guardados = json.loads((ctx.run_dir / "01_search" / "records.json").read_text("utf-8"))
    assert [r["record_id"] for r in guardados] == [r.record_id for r in records]
    assert len(records) == sum(e.n_returned for e in log.entries if e.status == "ok") == 4
    fallos = json.loads((ctx.run_dir / "01_search" / "failures.json").read_text("utf-8"))
    assert fallos == [{"db": "BVS", "error": bvs.error}]


def test_import_ris_utf16_no_aborta(tmp_path: Path) -> None:
    proto = _protocolo(tmp_path, ["Scopus"])
    imported = proto / "imported"
    imported.mkdir()
    (imported / "a.ris").write_bytes(_RIS.encode("utf-16"))  # export típico de EndNote
    (imported / "b.bib").write_text("@article{k, title = {Desde BibTeX}}\n", encoding="utf-8")
    ctx = RunContext("demo", tmp_path / "runs", "T")

    records = run_search(
        load_protocol(proto),
        source_dir=proto,
        strings_dir=proto / "search_strings",
        question="q",
        max_results=5,
        mailto=None,
        search_fn=None,
        run_ctx=ctx,
    )

    assert [r.title for r in records] == ["Desde BibTeX"]
    por_base = {e.database: e for e in _log(ctx).entries}
    assert por_base["imported/a.ris"].status == "failed"
    assert por_base["imported/a.ris"].error.startswith("UnicodeDecodeError")
    assert por_base["imported/a.ris"].file_sha256
    assert por_base["imported/b.bib"].status == "ok"


def test_search_no_se_repite_al_reanudar(tmp_path: Path) -> None:
    llamadas: list[str] = []

    def busqueda_unica(query: str, n: int) -> list[SearchRecord]:
        if llamadas:
            raise AssertionError("la búsqueda no debe repetirse al reanudar")
        llamadas.append(query)
        return [SearchRecord(record_id="rec-1", title="Uno", source_db="OpenAlex")]

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=busqueda_unica).status == "paused"
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=busqueda_unica).status == "paused"
    assert len(llamadas) == 1
    (entrada,) = _log(ctx).entries
    assert (entrada.kind, entrada.database, entrada.n_returned) == ("injected", "search_fn", 1)
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_search_stage.py -v`
Expected: ERROR de colección, `ModuleNotFoundError: No module named 'revisia.orchestration.search_stage'`.

- [ ] **Step 3: Importación fichero a fichero.** En `revisia/ingest/manual_import.py`, sustituir

```python
from revisia.provenance.runmeta import sha256_text
from revisia.schemas.records import SearchRecord
```

por

```python
from revisia.provenance.runmeta import sha256_text
from revisia.schemas.records import SearchRecord

# Extensiones que se importan desde `imported/`.
IMPORT_SUFFIXES: tuple[str, ...] = (".ris", ".bib", ".bibtex")
```

y `import_directory` completa

```python
def import_directory(directory: str | Path) -> list[SearchRecord]:
    """Importa todos los ``.ris``/``.bib`` de una carpeta (vacío si no existe)."""
    base = Path(directory)
    if not base.exists():
        return []
    records: list[SearchRecord] = []
    for path in sorted(base.iterdir()):
        suffix = path.suffix.lower()
        if suffix == ".ris":
            records += parse_ris(path.read_text(encoding="utf-8"))
        elif suffix in (".bib", ".bibtex"):
            records += parse_bibtex(path.read_text(encoding="utf-8"))
    return records
```

por

```python
def import_file(path: str | Path) -> list[SearchRecord]:
    """Importa un fichero RIS o BibTeX en UTF-8.

    La búsqueda lo llama fichero a fichero para que uno ilegible quede como
    ``failed`` en ``01_search/log.json`` sin abortar la corrida (auditoría
    2026-09-03, M7).

    Raises:
        ValueError: si la extensión no es ``.ris``, ``.bib`` ni ``.bibtex``.
        UnicodeDecodeError: si el fichero no está en UTF-8 (p. ej. un RIS de
            EndNote exportado en UTF-16).
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".ris":
        return parse_ris(path.read_text(encoding="utf-8"))
    if suffix in (".bib", ".bibtex"):
        return parse_bibtex(path.read_text(encoding="utf-8"))
    raise ValueError(f"{path.name}: formato no soportado (usa .ris, .bib o .bibtex)")


def import_directory(directory: str | Path) -> list[SearchRecord]:
    """Importa todos los ``.ris``/``.bib`` de una carpeta (vacío si no existe)."""
    base = Path(directory)
    if not base.exists():
        return []
    records: list[SearchRecord] = []
    for path in sorted(base.iterdir()):
        if path.suffix.lower() in IMPORT_SUFFIXES:
            records += import_file(path)
    return records
```

En `revisia/ingest/__init__.py`, sustituir

```python
from revisia.ingest.manual_import import (
    import_directory,
    parse_bibtex,
    parse_ris,
)

__all__ = ["import_directory", "parse_bibtex", "parse_ris"]
```

por

```python
from revisia.ingest.manual_import import (
    import_directory,
    import_file,
    parse_bibtex,
    parse_ris,
)

__all__ = ["import_directory", "import_file", "parse_bibtex", "parse_ris"]
```

- [ ] **Step 4: El módulo de búsqueda** — crear `revisia/orchestration/search_stage.py`:

```python
"""Búsqueda multi-base con registro por base, congelada en ``01_search/`` (Ola 1).

Hasta la Ola 1 los registros crudos no se guardaban, ``01_search/`` solo existía
si alguna base fallaba, la pregunta sustituía en silencio a una cadena ausente
y una base sin backend (o mal escrita) se saltaba sin avisar; la cadena, la
fecha, los parámetros y el número de resultados por base no quedaban en ningún
sitio (auditoría 2026-09-03, M12; PRISMA-S 1, 8, 13 y 15).

Ahora cada fuente deja una entrada ``SearchLogEntry`` en ``01_search/log.json``
(una por base declarada, una por fichero de ``imported/`` y una ``injected`` si
la búsqueda la dio ``search_fn``) y los registros, **antes** del dedup (que muta
el registro conservado), van a ``01_search/records.json``. ``log.json`` es la
marca de búsqueda completa: si existe, al reanudar se cargan los registros y no
se vuelve a buscar (D3).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from revisia.agents import _http, search_backends
from revisia.ingest.manual_import import IMPORT_SUFFIXES, import_file
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import (
    SEARCH_STRINGS_DIR,
    SNAPSHOT_DIR,
    ProtocolMismatchError,
)
from revisia.provenance.runmeta import sha256_text, utc_now_iso
from revisia.schemas.artifacts import QueryOrigin, SearchLog, SearchLogEntry
from revisia.schemas.records import SearchRecord

SearchFn = Callable[[str, int], list[SearchRecord]]

SEARCH_DIR = "01_search"


def _error(exc: BaseException) -> str:
    """Mensaje del fallo, redactado: httpx incluye la URL con api_key/email."""
    return _http.redact_secrets(f"{type(exc).__name__}: {exc}")


def _query_for(strings_dir: Path, key: str, question: str) -> tuple[str, QueryOrigin, str | None]:
    """Cadena efectiva de una base: su ``search_strings/<key>.txt`` o la pregunta."""
    path = strings_dir / f"{key}.txt"
    text = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    if text:
        return text, "file", f"{SNAPSHOT_DIR}/{SEARCH_STRINGS_DIR}/{key}.txt"
    return question, "question_fallback", None


def _backend_name(key: str) -> str:
    fn = search_backends.BACKENDS[key]
    return f"{fn.__module__.rsplit('.', 1)[-1]}.{fn.__name__}"


def _search_database(
    db: str,
    *,
    declared: bool,
    strings_dir: Path,
    question: str,
    max_results: int,
    mailto: str | None,
) -> tuple[list[SearchRecord], SearchLogEntry]:
    """Busca en una base declarada y devuelve sus registros y su entrada del log."""
    key = search_backends.db_key(db)
    entry = SearchLogEntry(database=db, db_key=key, kind="database", declared=declared, status="ok")
    if key in search_backends.BACKENDS:
        query, origin, query_file = _query_for(strings_dir, key, question)
        entry.backend = _backend_name(key)
        entry.query, entry.query_origin, entry.query_file = query, origin, query_file
        entry.query_sha256 = sha256_text(query)
        entry.max_results = max_results
        entry.started_utc = utc_now_iso()
        try:
            records = search_backends.search_database(db, query, max_results, mailto=mailto)
        except Exception as exc:  # red, 5xx, JSON o validación: degradar, nunca abortar
            entry.status, entry.error = "failed", _error(exc)
            records = []
        entry.finished_utc = utc_now_iso()
        entry.n_returned = len(records)
        entry.source_db = sorted({r.source_db for r in records})
        return records, entry
    if key in search_backends.MANUAL_ONLY:
        # Se incorpora por importación (imported/); si hay cadena, se registra
        # igualmente: PRISMA-S 8 pide la estrategia de cada base.
        entry.status = "manual_only"
        query, origin, query_file = _query_for(strings_dir, key, question)
        if origin == "file":
            entry.query, entry.query_origin, entry.query_file = query, origin, query_file
            entry.query_sha256 = sha256_text(query)
        return [], entry
    entry.status = "unknown"
    entry.error = "base desconocida: sin backend ni importación manual (revisa el nombre)"
    return [], entry


def _import(path: Path) -> tuple[list[SearchRecord], SearchLogEntry]:
    """Importa un fichero de ``imported/``; un fallo queda en el log, no aborta (M7)."""
    entry = SearchLogEntry(
        database=f"imported/{path.name}",
        db_key="imported",
        kind="manual_import",
        declared=True,
        status="ok",
        started_utc=utc_now_iso(),
        file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    try:
        records = import_file(path)
    except Exception as exc:  # p. ej. un RIS exportado en UTF-16
        entry.status, entry.error = "failed", _error(exc)
        records = []
    entry.finished_utc = utc_now_iso()
    entry.n_returned = len(records)
    entry.source_db = sorted({r.source_db for r in records})
    return records, entry


def multi_database_search(
    protocol,
    *,
    strings_dir: Path,
    imported_dir: Path | None,
    question: str,
    max_results: int,
    mailto: str | None,
) -> tuple[list[SearchRecord], list[SearchLogEntry]]:
    """Busca en cada base declarada (con su cadena) e importa ``imported/``.

    Sin bases declaradas se busca en OpenAlex (``declared: false``). Una base
    que falla, un fichero que no se puede leer o una base desconocida quedan en
    su entrada del log: la corrida nunca se aborta por una fuente.
    """
    declared = list(protocol.databases)
    records: list[SearchRecord] = []
    entries: list[SearchLogEntry] = []
    for db in declared or ["openalex"]:
        found, entry = _search_database(
            db,
            declared=bool(declared),
            strings_dir=strings_dir,
            question=question,
            max_results=max_results,
            mailto=mailto,
        )
        records += found
        entries.append(entry)
    if imported_dir is not None and imported_dir.is_dir():
        for path in sorted(imported_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in IMPORT_SUFFIXES:
                found, entry = _import(path)
                records += found
                entries.append(entry)
    return records, entries


def run_search(
    protocol,
    *,
    source_dir: Path | None,
    strings_dir: Path,
    question: str,
    max_results: int,
    mailto: str | None,
    search_fn: SearchFn | None,
    run_ctx: RunContext,
) -> list[SearchRecord]:
    """Registros de la búsqueda de la corrida: de ``01_search/`` o buscándolos.

    Si ``01_search/log.json`` existe, carga ``records.json`` sin llamar a nada
    (tampoco a ``search_fn``). Si no, busca y escribe, en este orden,
    ``records.json``, ``log.json`` (marca de completitud) y ``failures.json``
    (derivado del log, solo si alguna entrada falló).

    Raises:
        ProtocolMismatchError: si hay que buscar y no se tiene la carpeta del
            protocolo original (``imported/`` no entra en la instantánea).
    """
    search_dir = run_ctx.run_dir / SEARCH_DIR
    if (search_dir / "log.json").exists():
        raw = json.loads((search_dir / "records.json").read_text(encoding="utf-8"))
        return [SearchRecord.model_validate(r) for r in raw]

    started = utc_now_iso()
    if search_fn is not None:
        records = search_fn(question, max_results)
        entries = [
            SearchLogEntry(
                database="search_fn",
                db_key="search_fn",
                kind="injected",
                declared=False,
                backend=getattr(search_fn, "__name__", None),
                status="ok",
                source_db=sorted({r.source_db for r in records}),
                query=question,
                query_sha256=sha256_text(question),
                max_results=max_results,
                started_utc=started,
                finished_utc=utc_now_iso(),
                n_returned=len(records),
            )
        ]
    else:
        if source_dir is None:
            raise ProtocolMismatchError(
                "la búsqueda de esta corrida no terminó (falta 01_search/log.json) y hay que "
                "repetirla: reanuda pasando también la carpeta del protocolo "
                "(`revisia run <protocolo> --resume <run_dir>`), que contiene imported/."
            )
        records, entries = multi_database_search(
            protocol,
            strings_dir=strings_dir,
            imported_dir=Path(source_dir) / "imported",
            question=question,
            max_results=max_results,
            mailto=mailto,
        )

    run_ctx.write_json(f"{SEARCH_DIR}/records.json", [r.model_dump(mode="json") for r in records])
    log = SearchLog(
        started_utc=started,
        finished_utc=utc_now_iso(),
        max_results=max_results,
        mailto_set=bool(mailto),
        entries=entries,
    )
    run_ctx.write_json(f"{SEARCH_DIR}/log.json", log.model_dump(mode="json"))
    failures = [{"db": e.database, "error": e.error or ""} for e in entries if e.status == "failed"]
    if failures:
        run_ctx.write_json(f"{SEARCH_DIR}/failures.json", failures)
        for failure in failures:
            print(
                f"⚠️  búsqueda · {failure['db']} no respondió ({failure['error']}); "
                "se continúa sin esa fuente"
            )
    return records
```

- [ ] **Step 5: El pipeline busca con `run_search`.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.agents import _http, search_backends
from revisia.agents import dedup as dedup_agent
```

por

```python
from revisia.agents import dedup as dedup_agent
```

sustituir

```python
from revisia.ingest import import_directory
from revisia.llm.registry import build_provider
```

por

```python
from revisia.llm.registry import build_provider
```

sustituir

```python
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import ensure_snapshot
```

por

```python
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.search_stage import multi_database_search, run_search
from revisia.orchestration.snapshot import SEARCH_STRINGS_DIR, ensure_snapshot
```

en `_multi_database_search`, sustituir el cuerpo (de la docstring al `return`)

```python
    """Busca en cada base declarada (con su cadena) + importación manual.

    Por cada base de ``protocol.databases`` lee su cadena en
    ``search_strings/<base>.txt`` (cae a la pregunta) y despacha al backend; las
    bases sin backend programático (Scopus/WoS) se cubren con los archivos
    RIS/BibTeX de ``imported/``. Un backend que falle (red, 5xx, JSON inválido)
    **no aborta la corrida**: se anota en ``failures`` para que quede en disco
    (``01_search/failures.json``) y en PRISMA-S conste qué base no respondió.
    La deduplicación posterior une los solapes.
    """
    databases = protocol.databases or ["openalex"]
    records: list[SearchRecord] = []
    failures: list[dict[str, str]] = []
    for db in databases:
        string_file = protocol_dir / "search_strings" / f"{search_backends.db_key(db)}.txt"
        query = question_text
        if string_file.exists():
            query = string_file.read_text(encoding="utf-8").strip() or question_text
        if search_backends.db_key(db) not in search_backends.BACKENDS:
            # Base sin backend (p. ej. Scopus): se incorpora vía imported/.
            continue
        try:
            records += search_backends.search_database(db, query, max_results, mailto=mailto)
        except Exception as exc:  # red, 5xx, JSON o validación: degradar, nunca abortar
            # Cualquier fallo del backend (incluida una ValidationError de pydantic,
            # que hereda de ValueError) queda registrado; el mensaje se redacta
            # porque httpx incluye la URL con api_key/email en el texto del error.
            error = _http.redact_secrets(f"{type(exc).__name__}: {exc}")
            failures.append({"db": db, "error": error})
            continue
    records += import_directory(protocol_dir / "imported")
    return records, failures
```

por

```python
    """Envoltorio de compatibilidad sobre ``search_stage.multi_database_search``.

    Conserva la firma y la tupla ``(registros, fallos)`` de antes de la Ola 1
    (la usan los tests de búsqueda multi-base). Lee las cadenas de
    ``<protocol_dir>/search_strings/`` y los RIS/BibTeX de ``imported/``; los
    fallos van redactados y una base sin backend no es un fallo (va por
    ``imported/``).
    """
    records, entries = multi_database_search(
        protocol,
        strings_dir=protocol_dir / "search_strings",
        imported_dir=protocol_dir / "imported",
        question=question_text,
        max_results=max_results,
        mailto=mailto,
    )
    failures = [{"db": e.database, "error": e.error or ""} for e in entries if e.status == "failed"]
    return records, failures
```

y en `_search`, sustituir la docstring y el cuerpo

```python
    """Búsqueda multi-base (A2).

    ``search_fn`` inyectado (tests) tiene prioridad y conserva el contrato de
    una sola llamada; en producción se busca en todas las bases declaradas.
    """
    if search_fn is not None:
        return search_fn(run.question, max_results)
    raw_records, failures = _multi_database_search(
        run.protocol, run.source_dir or run.snapshot_dir, run.question, max_results, run.mailto
    )
    if failures:
        run.ctx.write_json("01_search/failures.json", failures)
        for failure in failures:
            print(
                f"⚠️  búsqueda · {failure['db']} no respondió ({failure['error']}); "
                "se continúa sin esa base"
            )
    return raw_records
```

por

```python
    """Búsqueda multi-base (A2), congelada en ``01_search/`` (M12).

    ``search_fn`` inyectado (tests) tiene prioridad y conserva el contrato de
    una sola llamada; en producción se busca en todas las bases declaradas con
    las cadenas de ``00_protocol/search_strings/``. Si la búsqueda ya terminó
    (existe ``01_search/log.json``), se carga sin repetirla.
    """
    return run_search(
        run.protocol,
        source_dir=run.source_dir,
        strings_dir=run.snapshot_dir / SEARCH_STRINGS_DIR,
        question=run.question,
        max_results=max_results,
        mailto=run.mailto,
        search_fn=search_fn,
        run_ctx=run.ctx,
    )
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_search_stage.py tests/test_search_multibase.py -v`
Expected: PASS (los tests de `_multi_database_search` siguen en verde con el envoltorio).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 429 recogidos.

- [ ] **Step 7: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 8: Commit**

```bash
git add revisia/orchestration/search_stage.py revisia/ingest/manual_import.py revisia/ingest/__init__.py revisia/orchestration/pipeline.py tests/test_search_stage.py
git commit -m "feat(busqueda): log por base y búsqueda congelada en 01_search/ (M12, M7)" -m "Cada base declarada, cada fichero de imported/ y la búsqueda inyectada dejan su entrada en 01_search/log.json (cadena efectiva y su origen, hash, parámetros, horas, n, error redactado; manual_only y unknown explícitos). records.json se escribe antes del dedup y log.json marca la búsqueda completa: al reanudar no se vuelve a buscar. imported/ se lee fichero a fichero con import_file, así un RIS en UTF-16 queda failed y no aborta la corrida. _multi_database_search queda como envoltorio. Auditoría 2026-09-03, M12 y M7; spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Dedup congelado en `02_dedup/` con ids desambiguados (`deduplicate_with_report`)

**Files:**
- Modify: `revisia/agents/dedup.py` (docstring e imports l.8-15; `deduplicate` l.39-61)
- Modify: `revisia/orchestration/pipeline.py` (imports l.19-22 y l.69; `_dedup` l.226-228)
- Test: `tests/test_dedup.py` (imports l.5-6; dos tests nuevos al final)

**Interfaces:**
- Consumes: `DedupDuplicate`, `DedupRename`, `DedupReport` (PR-0); `parse_ris` (existente).
- Produces:
  - `revisia.agents.dedup.deduplicate_with_report(records: list[SearchRecord]) -> tuple[list[SearchRecord], DedupReport]`: conserva el primero de cada clave y le fusiona el `extra` de los duplicados (muta ese registro, como hoy); después, un `record_id` repetido entre los conservados pasa a `<id>#2`, `<id>#3`… en orden de aparición (saltando ids ocupados) **en una copia**. `DedupReport(n_in, n_out, duplicates=[{record_id, source_db, kept_record_id (id final), key}], renamed=[{from_id, to_id}])`.
  - `deduplicate(records) -> tuple[list[SearchRecord], int]` queda como envoltorio (`len(report.duplicates)`).
  - `pipeline._dedup`: con `02_dedup/dedup.json` (marca de etapa completa) carga `02_dedup/records.json` y el informe sin recalcular; si no, escribe `records.json` y después `dedup.json`.

- [ ] **Step 1: Tests que fallan.** En `tests/test_dedup.py`, sustituir los imports

```python
from revisia.agents.dedup import deduplicate
from revisia.schemas.records import SearchRecord
```

por

```python
import json
from pathlib import Path

from revisia.agents.dedup import deduplicate, deduplicate_with_report
from revisia.config import load_protocol
from revisia.ingest import parse_ris
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.schemas.artifacts import DedupReport
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"
```

y añadir al final del fichero:

```python


def test_dedup_ids_repetidos_se_desambiguan() -> None:
    # Hallazgo 3 del spec: el RIS conserva doi="https://doi.org/…" (otra clave de
    # dedup) pero su id es el mismo que el del artículo traído de OpenAlex.
    ris = "TY  - JOUR\nTI  - Mismo artículo\nDO  - https://doi.org/10.1000/ABC\nER  -\n"
    (importado,) = parse_ris(ris)
    openalex = SearchRecord(
        record_id="10.1000/abc", title="Mismo artículo", doi="10.1000/abc", source_db="OpenAlex"
    )
    assert importado.record_id == openalex.record_id == "10.1000/abc"

    unicos, informe = deduplicate_with_report([openalex, importado, importado.model_copy()])
    assert [r.record_id for r in unicos] == ["10.1000/abc", "10.1000/abc#2"]
    assert [(r.from_id, r.to_id) for r in informe.renamed] == [("10.1000/abc", "10.1000/abc#2")]
    assert (informe.n_in, informe.n_out) == (3, 2)
    (duplicado,) = informe.duplicates
    assert duplicado.kept_record_id == "10.1000/abc#2"  # el id final del conservado
    assert duplicado.key == "doi:https://doi.org/10.1000/abc"
    assert importado.record_id == "10.1000/abc"  # el original no se toca


def test_records_json_previo_a_fusion_de_dedup(tmp_path: Path) -> None:
    def busqueda(query: str, n: int) -> list[SearchRecord]:
        return [
            SearchRecord(record_id="a", title="Uno", doi="10.1/x", source_db="OpenAlex"),
            SearchRecord(
                record_id="b",
                title="Uno (PubMed)",
                doi="10.1/X",
                source_db="PubMed",
                extra={"pmcid": "PMC1"},
            ),
        ]

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=busqueda)

    crudos = json.loads((ctx.run_dir / "01_search" / "records.json").read_text("utf-8"))
    assert [r["extra"] for r in crudos] == [{}, {"pmcid": "PMC1"}]  # antes de la fusión
    unicos = json.loads((ctx.run_dir / "02_dedup" / "records.json").read_text("utf-8"))
    assert [(r["record_id"], r["extra"]) for r in unicos] == [("a", {"pmcid": "PMC1"})]
    informe = DedupReport.model_validate_json(
        (ctx.run_dir / "02_dedup" / "dedup.json").read_text("utf-8")
    )
    assert [(d.record_id, d.kept_record_id) for d in informe.duplicates] == [("b", "a")]
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_dedup.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'deduplicate_with_report' from 'revisia.agents.dedup'`.

- [ ] **Step 3: Implementar el informe.** En `revisia/agents/dedup.py`, sustituir

```python
y reporta cuántos se descartaron.
"""

from __future__ import annotations

import re

from revisia.schemas.records import SearchRecord
```

por

```python
y reporta cuántos se descartaron.

Ola 1 (spec 2026-10-04 §7): ``deduplicate_with_report`` deja la traza completa
(``02_dedup/dedup.json``) y desambigua los ``record_id`` repetidos entre los
conservados (``<id>#2``, ``#3``…): un RIS con ``DO https://doi.org/…`` produce
el mismo id que el artículo de OpenAlex con otra clave de dedup, y el diario y
las etiquetas humanas usan el id como clave (hallazgo 3 del spec).
"""

from __future__ import annotations

import re

from revisia.schemas.artifacts import DedupDuplicate, DedupRename, DedupReport
from revisia.schemas.records import SearchRecord
```

y `deduplicate` completa

```python
def deduplicate(records: list[SearchRecord]) -> tuple[list[SearchRecord], int]:
    """Deduplica una lista de registros.

    Conserva el primer registro de cada clave y le fusiona las claves de
    ``extra`` que aporten los duplicados posteriores (sin pisar las suyas), para
    no perder identificadores útiles —como el PMCID— por el orden de las bases.

    Returns:
        Tupla ``(únicos, n_descartados)``, preservando el orden de aparición.
    """
    seen: dict[str, SearchRecord] = {}
    unique: list[SearchRecord] = []
    discarded = 0
    for record in records:
        key = dedup_key(record)
        kept = seen.get(key)
        if kept is not None:
            discarded += 1
            _merge_extra(kept, record)
            continue
        seen[key] = record
        unique.append(record)
    return unique, discarded
```

por

```python
def deduplicate_with_report(
    records: list[SearchRecord],
) -> tuple[list[SearchRecord], DedupReport]:
    """Deduplica y devuelve la traza completa (``02_dedup/dedup.json``).

    Conserva el primer registro de cada clave y le fusiona las claves de
    ``extra`` que aporten los duplicados posteriores (sin pisar las suyas), para
    no perder identificadores útiles —como el PMCID— por el orden de las bases.
    Ojo: la fusión muta el registro conservado (por eso la búsqueda se congela
    antes, en ``01_search/records.json``).

    Después, un ``record_id`` repetido entre los conservados se renombra de forma
    determinista: la primera aparición conserva el id y las siguientes pasan a
    ``<id>#2``, ``<id>#3``… (saltando cualquier id ya ocupado). El renombrado
    devuelve una copia; el registro original no cambia.

    Returns:
        ``(únicos, informe)``, preservando el orden de aparición.
    """
    unique: list[SearchRecord] = []
    position: dict[str, int] = {}  # clave → índice en `unique`
    pairs: list[tuple[SearchRecord, int, str]] = []
    for record in records:
        key = dedup_key(record)
        index = position.get(key)
        if index is not None:
            _merge_extra(unique[index], record)
            pairs.append((record, index, key))
            continue
        position[key] = len(unique)
        unique.append(record)

    taken = {r.record_id for r in unique}
    seen_ids: dict[str, int] = {}
    renamed: list[DedupRename] = []
    for i, record in enumerate(unique):
        seen_ids[record.record_id] = seen_ids.get(record.record_id, 0) + 1
        if seen_ids[record.record_id] == 1:
            continue
        n = seen_ids[record.record_id]
        while f"{record.record_id}#{n}" in taken:
            n += 1
        new_id = f"{record.record_id}#{n}"
        taken.add(new_id)
        renamed.append(DedupRename(from_id=record.record_id, to_id=new_id))
        unique[i] = record.model_copy(update={"record_id": new_id})

    duplicates = [
        DedupDuplicate(
            record_id=record.record_id,
            source_db=record.source_db,
            kept_record_id=unique[index].record_id,
            key=key,
        )
        for record, index, key in pairs
    ]
    report = DedupReport(
        n_in=len(records), n_out=len(unique), duplicates=duplicates, renamed=renamed
    )
    return unique, report


def deduplicate(records: list[SearchRecord]) -> tuple[list[SearchRecord], int]:
    """Deduplica una lista de registros (envoltorio de ``deduplicate_with_report``).

    Returns:
        Tupla ``(únicos, n_descartados)``, preservando el orden de aparición.
    """
    unique, report = deduplicate_with_report(records)
    return unique, len(report.duplicates)
```

- [ ] **Step 4: Congelar el dedup en el pipeline.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
```

por

```python
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
```

sustituir

```python
from revisia.schemas.artifacts import GATED_STAGES, ExcludedReport, RetrievalOutcome
```

por

```python
from revisia.schemas.artifacts import (
    GATED_STAGES,
    DedupReport,
    ExcludedReport,
    RetrievalOutcome,
)
```

y `_dedup`

```python
def _dedup(run: _Run, raw_records: list[SearchRecord]) -> tuple[list[SearchRecord], int]:
    """Deduplicación determinista (A2)."""
    return dedup_agent.deduplicate(raw_records)
```

por

```python
def _dedup(run: _Run, raw_records: list[SearchRecord]) -> tuple[list[SearchRecord], int]:
    """Deduplicación determinista (A2), congelada en ``02_dedup/``.

    ``records.json`` se escribe antes que ``dedup.json``, la marca de etapa
    completa: al reanudar se cargan ambos sin recalcular.
    """
    dedup_dir = run.ctx.run_dir / "02_dedup"
    if (dedup_dir / "dedup.json").exists():
        raw = json.loads((dedup_dir / "records.json").read_text(encoding="utf-8"))
        report = DedupReport.model_validate_json(
            (dedup_dir / "dedup.json").read_text(encoding="utf-8")
        )
        return [SearchRecord.model_validate(r) for r in raw], len(report.duplicates)
    deduped, report = dedup_agent.deduplicate_with_report(raw_records)
    run.ctx.write_json("02_dedup/records.json", [r.model_dump(mode="json") for r in deduped])
    run.ctx.write_json("02_dedup/dedup.json", report.model_dump(mode="json"))
    return deduped, len(report.duplicates)
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_dedup.py -v`
Expected: PASS, 7 tests (los cinco existentes siguen en verde con el envoltorio).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 431 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/agents/dedup.py revisia/orchestration/pipeline.py tests/test_dedup.py
git commit -m "feat(dedup): informe en 02_dedup/ e ids repetidos desambiguados" -m "deduplicate_with_report deja la traza completa (duplicados con el id final del conservado y renombrados) y renombra de forma determinista un record_id repetido entre los conservados (<id>#2): un RIS con DO https://doi.org/… produce el mismo id que el artículo de OpenAlex con otra clave de dedup, y el diario y las etiquetas humanas usan el id como clave (hallazgo 3 del spec). El pipeline congela el resultado en 02_dedup/records.json y dedup.json. Spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Estado e interrupciones en `run.json`, preflight al empezar y `flow.resume_review`

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (imports l.27 y l.61-75; constante tras `FetchFn` l.83-84; `_Run` l.180-200; `run_pipeline` completo l.652-813, que pasa a `run_pipeline` + `_run_stages`)
- Modify: `revisia/orchestration/flow.py` (docstring e imports l.1-15; función nueva antes de `prefect_review_flow`)
- Modify: `revisia/agent_driver.py` (l.26-57)
- Test: `tests/test_reanudacion.py` (nuevo)

**Interfaces:**
- Consumes: `preflight`, `PreflightError` (PR-A); `RunInterruption`, `RunStatus` (PR-0); `read_run_info`, `write_run_info`, `SNAPSHOT_DIR`, `ProtocolMismatchError` (Tarea 5); `JournalError` (Tarea 2); `RunInterrupted`, `RunDirExistsError`, `LegacyRunError`, `RunContext.open` (Tareas 3 y 5); `DecisionFileError` (existente).
- Produces:
  - `run_pipeline` corre primero el preflight: `context="resume"` si existe `01_search/log.json` **o** si la búsqueda la inyecta `search_fn` (no hay bases que comprobar), `"run"` si no; con errores lanza `PreflightError(report)` sin escribir nada (ni `run.json`). Los avisos no se imprimen aquí (los imprime el CLI).
  - Errores de configuración o de entrada humana (`PreflightError`, `ProtocolMismatchError`, `JournalError`, `DecisionFileError`, `LegacyRunError`, `RunDirExistsError`) se relanzan tal cual. Cualquier otra excepción se registra en `run.json` (`interruptions += {utc, stage, error}` con el error redactado, `status="interrupted"`, `stage`) y se relanza como `RunInterrupted(run_dir, stage, error) from exc`. Un `KeyboardInterrupt` también se registra y se relanza tal cual.
  - `run.json.status`/`stage` al terminar cada invocación: `paused`/`rejected` con el gate (`_Run.stop`), `completed` con `stage=None`; en el gate final se escribe **antes** del manifiesto, que copia el estado en su bloque `run`.
  - `_Run` gana `stage: str | None` (etapa en curso), `finish(status, stage)` e `interrupted(error)`; `_run_stages(run, *, max_results, search_fn, fetch_fn, embedder, gold_labels) -> PipelineResult` encadena las etapas.
  - `revisia.orchestration.flow.resume_review(run_dir: str | Path, *, protocol_dir: str | Path | None = None, auto_approve: bool = False, mailto: str | None = None) -> PipelineResult`: `RunContext.open(run_dir)` + `load_protocol(run_dir / "00_protocol", default_slug=ctx.slug)` + `run_pipeline`. `run_review` no cambia de firma.
  - `revisia.agent_driver.run_review_with_agent(protocol_dir: str | Path | None, callback, *, timestamp: str | None = None, runs_root="runs", max_results=25, auto_approve=True, mailto=None, search_fn=None, fetch_fn=None, run_dir: str | Path | None = None)`: con `run_dir` reanuda (protocolo de la instantánea); sin él, `timestamp` y `protocol_dir` son obligatorios (`ValueError`).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_reanudacion.py`:

```python
"""Reanudación de corridas: estado en run.json, interrupciones y entrypoints (Ola 1,
D3 y D14; auditoría 2026-09-03, A9; spec 2026-10-04 §7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import ScriptedProvider, fetch_disponible

from revisia.agent_driver import run_review_with_agent
from revisia.config import load_protocol
from revisia.llm.preflight import PreflightError
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.flow import resume_review
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext, RunInterrupted
from revisia.orchestration.snapshot import read_run_info
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _busqueda(query: str, n: int) -> list[SearchRecord]:
    return [
        SearchRecord(
            record_id="rec-1",
            title="LLM screening for systematic reviews",
            abstract="We evaluate LLM screening.",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-2",
            title="Active learning with ASReview",
            abstract="Active learning reduces workload.",
            source_db="OpenAlex",
        ),
    ][:n]


def test_resume_toma_el_slug_de_run_json(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)  # el demo no declara `slug`
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda).status == "paused"

    result = resume_review(ctx.run_dir)

    assert (result.status, result.stage, result.run_dir) == ("paused", "screening_ta", ctx.run_dir)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo-mini-review-T"]
    info = read_run_info(ctx.run_dir)
    assert info.slug == "demo-mini-review"
    assert len(info.resumes) == 1


def test_estado_de_la_corrida_en_run_json(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("paused", "screening_ta")

    run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=_busqueda, fetch_fn=fetch_disponible
    )
    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("completed", None)


def test_interrupcion_queda_en_run_json_y_se_relanza(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proveedor = ScriptedProvider(fail_at=1)
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    with pytest.raises(RunInterrupted) as exc:
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)

    assert exc.value.stage == "screening_ta"
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert f"revisia run --resume {ctx.run_dir}" in str(exc.value)
    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("interrupted", "screening_ta")
    (interrupcion,) = info.interruptions
    assert interrupcion.stage == "screening_ta"
    assert interrupcion.error == "RuntimeError: 429 Too Many Requests"


def test_preflight_al_empezar_no_crea_nada(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    sin_proveedor = protocol.model_copy(update={"llm": {}, "ensemble_llm": {}})
    ctx = RunContext(protocol.slug, tmp_path, "T")
    with pytest.raises(PreflightError, match="screening_ft"):
        run_pipeline(sin_proveedor, EXAMPLE, ctx, search_fn=_busqueda)
    assert list(ctx.run_dir.iterdir()) == []  # ni run.json ni instantánea


def test_agent_driver_reanuda_con_run_dir(tmp_path: Path) -> None:
    def callback(req, schema):  # el demo usa `fake`: el callback no se llega a usar
        raise AssertionError("no debería llamarse")

    pausa = run_review_with_agent(
        EXAMPLE,
        callback,
        timestamp="T",
        runs_root=tmp_path,
        auto_approve=False,
        search_fn=_busqueda,
    )
    assert pausa.status == "paused"
    completa = run_review_with_agent(
        None, callback, run_dir=pausa.run_dir, auto_approve=True, fetch_fn=fetch_disponible
    )
    assert (completa.status, completa.run_dir) == ("completed", pausa.run_dir)
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'resume_review' from 'revisia.orchestration.flow'`.

- [ ] **Step 3: Imports y errores de configuración.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.agents import dedup as dedup_agent
```

por

```python
from revisia.agents import _http
from revisia.agents import dedup as dedup_agent
```

sustituir

```python
from revisia.llm.registry import build_provider
from revisia.meta_analysis import MetaAnalysisResult, meta_analyze
from revisia.metrics import ScreeningMetrics, compute_screening_metrics
from revisia.orchestration.hitl import GateResult, review_gate
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.search_stage import multi_database_search, run_search
from revisia.orchestration.snapshot import SEARCH_STRINGS_DIR, ensure_snapshot
from revisia.provenance.runmeta import sha256_text
from revisia.rag.embed import Embedder, HashEmbedder
from revisia.schemas.artifacts import (
    GATED_STAGES,
    DedupReport,
    ExcludedReport,
    RetrievalOutcome,
)
```

por

```python
from revisia.llm.preflight import PreflightError, preflight
from revisia.llm.registry import build_provider
from revisia.meta_analysis import MetaAnalysisResult, meta_analyze
from revisia.metrics import ScreeningMetrics, compute_screening_metrics
from revisia.orchestration.hitl import DecisionFileError, GateResult, review_gate
from revisia.orchestration.journal import JournalError
from revisia.orchestration.run_context import (
    LegacyRunError,
    RunContext,
    RunDirExistsError,
    RunInterrupted,
)
from revisia.orchestration.search_stage import multi_database_search, run_search
from revisia.orchestration.snapshot import (
    SEARCH_STRINGS_DIR,
    SNAPSHOT_DIR,
    ProtocolMismatchError,
    ensure_snapshot,
    read_run_info,
    write_run_info,
)
from revisia.provenance.runmeta import sha256_text, utc_now_iso
from revisia.rag.embed import Embedder, HashEmbedder
from revisia.schemas.artifacts import (
    GATED_STAGES,
    DedupReport,
    ExcludedReport,
    RetrievalOutcome,
    RunInterruption,
    RunStatus,
)
```

y sustituir

```python
SearchFn = Callable[[str, int], list[SearchRecord]]
FetchFn = Callable[[SearchRecord], fulltext_agent.FullText]
```

por

```python
SearchFn = Callable[[str, int], list[SearchRecord]]
FetchFn = Callable[[SearchRecord], fulltext_agent.FullText]

# Errores de configuración o de entrada humana: se relanzan tal cual (rc 2 en el
# CLI) y no cuentan como interrupción. Cualquier otro error a mitad de corrida
# queda en run.json y se relanza como RunInterrupted (rc 3, D14).
_CONFIG_ERRORS: tuple[type[BaseException], ...] = (
    PreflightError,
    ProtocolMismatchError,
    JournalError,
    DecisionFileError,
    LegacyRunError,
    RunDirExistsError,
)
```

- [ ] **Step 4: Estado en `_Run`.** Sustituir

```python
    auto_approve: bool
    mailto: str | None
    metrics: ScreeningMetrics | None = None

    def gate(self, stage: str, payload: dict) -> GateResult:
        """Checkpoint humano de ``stage`` con la autonomía que fija el protocolo."""
        return review_gate(
```

por

```python
    auto_approve: bool
    mailto: str | None
    metrics: ScreeningMetrics | None = None
    # Etapa en curso (la que queda en run.json si la corrida se interrumpe).
    stage: str | None = None

    def finish(self, status: RunStatus, stage: str | None) -> None:
        """Deja en ``run.json`` cómo termina esta invocación (spec §4.3)."""
        info = read_run_info(self.ctx.run_dir)
        if info is not None:
            write_run_info(
                self.ctx.run_dir, info.model_copy(update={"status": status, "stage": stage})
            )

    def interrupted(self, error: str) -> None:
        """Registra una interrupción en ``run.json`` (estado ``interrupted``, D14)."""
        info = read_run_info(self.ctx.run_dir)
        if info is None:
            return
        interruption = RunInterruption(utc=utc_now_iso(), stage=self.stage, error=error)
        write_run_info(
            self.ctx.run_dir,
            info.model_copy(
                update={
                    "interruptions": [*info.interruptions, interruption],
                    "status": "interrupted",
                    "stage": self.stage,
                }
            ),
        )

    def gate(self, stage: str, payload: dict) -> GateResult:
        """Checkpoint humano de ``stage`` con la autonomía que fija el protocolo."""
        self.stage = stage
        return review_gate(
```

y en `stop`, sustituir

```python
        if gate.status == "approved":
            return None
        return PipelineResult(
            gate.status, gate.message, metrics=self.metrics, run_dir=self.ctx.run_dir, stage=stage
        )
```

por

```python
        if gate.status == "approved":
            return None
        self.finish(gate.status, stage)
        return PipelineResult(
            gate.status, gate.message, metrics=self.metrics, run_dir=self.ctx.run_dir, stage=stage
        )
```

- [ ] **Step 5: `run_pipeline` + `_run_stages`.** Sustituir `run_pipeline` completo, desde la línea `def run_pipeline(` hasta el final del fichero (es la última función; el cuerpo es el de la Tarea 1 con las ediciones de las Tareas 3, 5, 6 y 7), por:

```python
def run_pipeline(
    protocol: ReviewProtocol,
    protocol_dir: str | Path | None,
    run_ctx: RunContext,
    *,
    max_results: int = 25,
    auto_approve: bool = False,
    mailto: str | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    embedder: Embedder | None = None,
    gold_labels: dict[str, bool] | None = None,
) -> PipelineResult:
    """Ejecuta el tracer bullet end-to-end y devuelve su resultado.

    Una corrida nueva copia el protocolo a ``00_protocol/`` y escribe
    ``run.json``; una que se reanuda (``run.json`` ya existe) verifica su
    instantánea y toma ``max_results`` de ``run.json``. ``protocol_dir`` puede
    ser ``None`` al reanudar.

    Antes de nada corre el preflight sin red (M6): con ``context="resume"`` si la
    búsqueda ya está congelada (``01_search/log.json``) o la inyecta
    ``search_fn`` (no hay bases que comprobar), y ``"run"`` si no.

    Raises:
        PreflightError, ProtocolMismatchError, JournalError, DecisionFileError:
            errores de configuración o de entrada humana (rc 2 en el CLI).
        RunInterrupted: cualquier otro error a mitad de corrida; queda en
            ``run.json`` (``status: interrupted``) y se reanuda (D14).
    """
    frozen = (run_ctx.run_dir / "01_search" / "log.json").exists()
    report = preflight(
        protocol,
        protocol_dir if protocol_dir is not None else run_ctx.run_dir / SNAPSHOT_DIR,
        context="resume" if frozen or search_fn is not None else "run",
        mailto=mailto,
    )
    if report.errors:
        raise PreflightError(report)
    snapshot_dir, run_info = ensure_snapshot(
        protocol_dir, run_ctx, max_results=max_results, mailto=mailto
    )
    ie = _load_yaml(snapshot_dir / "inclusion_exclusion.yml")
    form = _load_yaml(snapshot_dir / "extraction_form.yml")
    run = _Run(
        protocol=protocol,
        snapshot_dir=snapshot_dir,
        source_dir=Path(protocol_dir) if protocol_dir is not None else None,
        ctx=run_ctx,
        question=protocol.question.text,
        criteria=_criteria_to_text(ie),
        form_fields=form.get("fields", []),
        auto_approve=auto_approve,
        mailto=mailto,
    )
    try:
        return _run_stages(
            run,
            max_results=run_info.max_results,
            search_fn=search_fn,
            fetch_fn=fetch_fn,
            embedder=embedder,
            gold_labels=gold_labels,
        )
    except _CONFIG_ERRORS:
        raise
    except KeyboardInterrupt:
        run.interrupted("KeyboardInterrupt")
        raise
    except Exception as exc:
        error = _http.redact_secrets(f"{type(exc).__name__}: {exc}")
        run.interrupted(error)
        raise RunInterrupted(run_ctx.run_dir, run.stage, error) from exc


def _run_stages(
    run: _Run,
    *,
    max_results: int,
    search_fn: SearchFn | None,
    fetch_fn: FetchFn | None,
    embedder: Embedder | None,
    gold_labels: dict[str, bool] | None,
) -> PipelineResult:
    """Encadena las etapas; ``run.stage`` dice cuál está en curso."""
    protocol = run.protocol
    run.stage = "busqueda"
    raw_records = _search(run, max_results=max_results, search_fn=search_fn)
    run.stage = "dedup"
    deduped, discarded = _dedup(run, raw_records)
    run.stage = "screening_ta"
    decisions = _screen_ta(run, deduped, _load_gold(run, gold_labels))
    passed = {d.record_id for d in decisions if d.final_label in {"include", "unclear"}}
    excluded_ta = sum(1 for d in decisions if d.final_label == "exclude")
    ta_payload = {
        "n_screened": len(deduped),
        "n_pass": len(passed),
        "n_excluded": excluded_ta,
        "pass_ids": sorted(passed),
    }
    if (stop := run.stop(run.gate("screening_ta", ta_payload), "screening_ta")) is not None:
        return stop

    passed_ta = [r for r in deduped if r.record_id in passed]
    run.stage = "screening_ft"
    ft = _fulltext(run, passed_ta, fetch_fn)
    # Hasta PR-D un `unclear` de FT sigue pasando (lo resolverá un humano, D1).
    included_ids = {d.record_id for d in ft.decisions if d.final_label in {"include", "unclear"}}
    excluded_ft = sum(1 for d in ft.decisions if d.final_label == "exclude")
    ft_payload = {
        "n_buscados": len(passed_ta),
        "n_no_recuperados": ft.not_retrieved,
        "n_evaluados": len(passed_ta) - ft.not_retrieved,
        "n_incluidos": len(included_ids),
        "n_excluidos": excluded_ft,
    }
    if (stop := run.stop(run.gate("screening_ft", ft_payload), "screening_ft")) is not None:
        return stop
    included = [r for r in passed_ta if r.record_id in included_ids]

    # Desglose de exclusiones humano vs IA (PRISMA-trAIce) sobre ambas fases; el
    # de solo T/A alimenta la nota ** del flow diagram oficial (trAIce R1).
    exclusion_breakdown = compute_exclusion_breakdown(decisions + ft.decisions)
    run.ctx.write_json("03_screening/exclusions.json", exclusion_breakdown.model_dump())
    ta_breakdown = compute_exclusion_breakdown(decisions)
    # Informes excluidos en elegibilidad (16b) y sus razones (cajas "Reason 1..n"
    # del flow oficial): una sola lista para el diagrama, la tabla y el auditor.
    excluded_reports = compute_ft_excluded(ft.decisions, passed_ta)
    run.ctx.write_json("04_fulltext/excluded.json", [r.model_dump() for r in excluded_reports])
    ft_exclusion_reasons = dict(Counter(r.reason for r in excluded_reports))

    run.stage = "extraccion"
    extractions, extraction_agreement = _extract(run, included)
    extraction_gate = run.gate("extraccion", {"n_extraidos": len(extractions)})
    if (stop := run.stop(extraction_gate, "extraccion")) is not None:
        return stop
    run.stage = "rob"
    assessments = _assess_rob(run, included, extractions, ft.texts)
    rob_gate = run.gate("rob", {"n_evaluados": len(assessments), "tool": protocol.rob_tool})
    if (stop := run.stop(rob_gate, "rob")) is not None:
        return stop

    run.stage = "sintesis"
    meta_result, meta_display = _meta_analysis(run)
    narrative, verification = _synthesize_and_verify(run, included, extractions, ft.texts, embedder)
    run.stage = "reporte"
    counts = _build_counts(
        raw_records=raw_records,
        deduped=deduped,
        discarded=discarded,
        excluded_ta=excluded_ta,
        ta_breakdown=ta_breakdown,
        passed_ta=passed_ta,
        ft=ft,
        excluded_ft=excluded_ft,
        excluded_reports=excluded_reports,
        ft_exclusion_reasons=ft_exclusion_reasons,
        included=included,
    )
    deliverable = _write_deliverables(
        run,
        counts=counts,
        included=included,
        extractions=extractions,
        assessments=assessments,
        narrative=narrative,
        excluded_reports=excluded_reports,
        exclusion_breakdown=exclusion_breakdown,
        extraction_agreement=extraction_agreement,
        meta_result=meta_result,
        meta_display=meta_display,
    )

    # Checkpoint final del reporte (A1).
    final_gate = run.gate(
        "reporte",
        {
            "included": len(included),
            "hallucination_flagged": verification.hallucination_flagged,
            "deliverable": str(deliverable),
        },
    )
    # Un reporte rechazado ya no se informa como "completed" (auditoría
    # 2026-09-03, C1). El estado va a run.json antes del manifiesto, que lo copia.
    status, message, stage = final_gate.status, final_gate.message, "reporte"
    if final_gate.status == "approved":
        status = "completed"
        message = f"Revisión completada · {counts.included} estudios incluidos."
        stage = None
    run.finish(status, stage)
    manifest_extra: dict = {
        "verification": verification.model_dump(),
        "risk_of_bias": {k: v.model_dump() for k, v in assessments.items()},
        "exclusions": exclusion_breakdown.model_dump(),
    }
    if run.metrics is not None:
        manifest_extra["screening_metrics"] = run.metrics.model_dump()
    if extraction_agreement is not None:
        manifest_extra["extraction_agreement"] = extraction_agreement.model_dump()
    if meta_result is not None:
        manifest_extra["meta_analysis"] = meta_result.model_dump()
    run.ctx.write_manifest(
        protocol_snapshot=protocol.model_dump(mode="json"),
        counts=counts.model_dump(),
        autonomy_effective={g: protocol.autonomy_for(g) for g in GATED_STAGES},
        final_gate={"forced_human": False, "reason": None},
        extra=manifest_extra,
    )
    return PipelineResult(
        status=status,
        message=message,
        counts=counts,
        included=included,
        narrative=narrative,
        hallucination_flagged=verification.hallucination_flagged,
        metrics=run.metrics,
        run_dir=run.ctx.run_dir,
        stage=stage,
    )
```

- [ ] **Step 6: `resume_review`.** En `revisia/orchestration/flow.py`, sustituir

```python
"""Entrypoints de ejecución del pipeline.

``run_review`` es el entrypoint plano (sin Prefect): lo usan el CLI y los tests,
y corre con dependencias mínimas — clave para "clónalo y córrelo". ``prefect_review_flow``
lo envuelve en un ``@flow`` de Prefect para corridas observables/programables
(import perezoso: Prefect solo se exige si se usa este wrapper).
"""

from __future__ import annotations

from pathlib import Path

from revisia.config import load_protocol
from revisia.orchestration.pipeline import PipelineResult, run_pipeline
from revisia.orchestration.run_context import RunContext
```

por

```python
"""Entrypoints de ejecución del pipeline.

``run_review`` es el entrypoint plano (sin Prefect): lo usan el CLI y los tests,
y corre con dependencias mínimas — clave para "clónalo y córrelo". ``prefect_review_flow``
lo envuelve en un ``@flow`` de Prefect para corridas observables/programables
(import perezoso: Prefect solo se exige si se usa este wrapper). ``resume_review``
reanuda una corrida existente desde su carpeta (Ola 1, D3).
"""

from __future__ import annotations

from pathlib import Path

from revisia.config import load_protocol
from revisia.orchestration.pipeline import PipelineResult, run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import SNAPSHOT_DIR
```

y sustituir

```python
def prefect_review_flow(
```

por

```python
def resume_review(
    run_dir: str | Path,
    *,
    protocol_dir: str | Path | None = None,
    auto_approve: bool = False,
    mailto: str | None = None,
) -> PipelineResult:
    """Reanuda una corrida desde su carpeta (D3, D14).

    El protocolo sale de ``00_protocol/`` con el slug de ``run.json`` (un demo
    sin ``slug`` declarado no pasa a llamarse ``00_protocol``) y ``max_results``
    también de ``run.json``. Si se pasa ``protocol_dir``, su huella se compara
    con la de la corrida.

    Raises:
        LegacyRunError: la carpeta no tiene ``run.json`` (corrida anterior a la
            Ola 1, D13).
    """
    ctx = RunContext.open(run_dir)
    protocol = load_protocol(ctx.run_dir / SNAPSHOT_DIR, default_slug=ctx.slug)
    return run_pipeline(protocol, protocol_dir, ctx, auto_approve=auto_approve, mailto=mailto)


def prefect_review_flow(
```

- [ ] **Step 7: `run_review_with_agent(run_dir=)`.** En `revisia/agent_driver.py`, sustituir

```python
from revisia.orchestration.run_context import RunContext


def run_review_with_agent(
    protocol_dir: str | Path,
    callback: AgentCallback,
    *,
    timestamp: str,
    runs_root: str | Path = "runs",
    max_results: int = 25,
    auto_approve: bool = True,
    mailto: str | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
) -> PipelineResult:
    """Ejecuta el pipeline usando ``callback`` como motor de razonamiento.

    Args:
        protocol_dir: carpeta del protocolo (con ``protocol.yml``).
        callback: función ``(LLMRequest, schema|None) -> objeto|dict|str`` que el
            proveedor ``agent`` invoca por etapa; el agente la implementa leyendo
            ``req.prompt`` y devolviendo algo que cumpla ``schema``.
        timestamp: marca de tiempo de la corrida (``runs/<slug>-<timestamp>/``).
        auto_approve: por defecto ``True`` (el agente conduce y aprueba los
            checkpoints); pon ``False`` para pausar en cada gate HITL.
        search_fn / fetch_fn: inyecciones opcionales (tests / corpus fijado).

    Returns:
        El :class:`PipelineResult` de la corrida.
    """
    protocol = load_protocol(protocol_dir)
    ctx = RunContext(protocol.slug, runs_root, timestamp)
```

por

```python
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import SNAPSHOT_DIR


def run_review_with_agent(
    protocol_dir: str | Path | None,
    callback: AgentCallback,
    *,
    timestamp: str | None = None,
    runs_root: str | Path = "runs",
    max_results: int = 25,
    auto_approve: bool = True,
    mailto: str | None = None,
    search_fn: SearchFn | None = None,
    fetch_fn: FetchFn | None = None,
    run_dir: str | Path | None = None,
) -> PipelineResult:
    """Ejecuta el pipeline usando ``callback`` como motor de razonamiento.

    Args:
        protocol_dir: carpeta del protocolo (con ``protocol.yml``); puede ser
            ``None`` al reanudar con ``run_dir``.
        callback: función ``(LLMRequest, schema|None) -> objeto|dict|str`` que el
            proveedor ``agent`` invoca por etapa; el agente la implementa leyendo
            ``req.prompt`` y devolviendo algo que cumpla ``schema``.
        timestamp: marca de tiempo de una corrida nueva
            (``runs/<slug>-<timestamp>/``); obligatoria si no se pasa ``run_dir``.
        auto_approve: por defecto ``True`` (el agente conduce y aprueba los
            checkpoints); pon ``False`` para pausar en cada gate HITL.
        search_fn / fetch_fn: inyecciones opcionales (tests / corpus fijado).
        run_dir: carpeta de una corrida existente para reanudarla (Ola 1, D3):
            el protocolo sale de su ``00_protocol/`` y ``timestamp`` se ignora.

    Returns:
        El :class:`PipelineResult` de la corrida.
    """
    if run_dir is not None:
        ctx = RunContext.open(run_dir)
        protocol = load_protocol(ctx.run_dir / SNAPSHOT_DIR, default_slug=ctx.slug)
    else:
        if timestamp is None or protocol_dir is None:
            raise ValueError("una corrida nueva necesita protocol_dir y timestamp (o run_dir)")
        protocol = load_protocol(protocol_dir)
        ctx = RunContext(protocol.slug, runs_root, timestamp)
```

- [ ] **Step 8: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py -v`
Expected: PASS, 5 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 436 recogidos.

- [ ] **Step 9: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 10: Commit**

```bash
git add revisia/orchestration/pipeline.py revisia/orchestration/flow.py revisia/agent_driver.py tests/test_reanudacion.py
git commit -m "feat(orchestration): estado en run.json, RunInterrupted y resume_review (A9, D14)" -m "run_pipeline corre el preflight antes de escribir nada (context resume si la búsqueda está congelada o inyectada). Cada invocación deja su estado en run.json (paused/rejected/completed con el gate). Un error a mitad de corrida queda en run.json.interruptions (redactado) y se relanza como RunInterrupted; los errores de configuración se relanzan tal cual. resume_review reabre la carpeta y carga el protocolo de 00_protocol/ con el slug de run.json; run_review_with_agent acepta run_dir. Spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Gates con `request_sha256`, plantilla, decisión obsoleta y ledger idempotente

**Files:**
- Modify: `revisia/orchestration/hitl.py` (fichero completo)
- Modify: `revisia/orchestration/pipeline.py` (payload del gate `reporte` en `_run_stages`, l.883-891)
- Create: `tests/hitl_helpers.py`
- Modify: `tests/test_hitl.py` (fichero completo: los tests existentes cambian de expectativa y se añaden cinco)
- Modify: `tests/test_pipeline_fake.py` (import l.14-16; `test_rejected_final_gate_is_not_completed` l.134-144; `test_paused_run_final_gate_falla_en_auditoria` l.157-168)

**Interfaces:**
- Consumes: `canonical_sha256` (PR-0); `summarize_gates`, `AUTO_APPROVE_ACTOR`, `DecisionEntry` (PR-0); `ARTIFACT_SCHEMA_VERSION` (PR-0); `RunContext.write_text` (Tarea 3); `run_pipeline`, `RunContext.open` (Tareas 5 y 8).
- Produces (las consumen PR-D y el auditor):
  - Constantes `REQUEST_FILE = "review_request.yml"`, `TEMPLATE_FILE = "decision.template.yml"`, `DECISION_FILE = "decision.yml"`.
  - `GateResult(status, message, request_sha256: str | None = None, actor: str | None = None)`.
  - `HumanDecision` (`extra="allow"`): `request_sha256: str` (**obligatorio**), `approved: StrictBool`, `actor: str = "human:desconocido"`, `reason: str | None = None`.
  - `render_decision_template(*, stage: str, autonomy: str, request_sha256: str) -> str` (PR-D le añade `records` y `flags`, Tarea 21): comentarios con instrucciones, `request_sha256: "<sha>"`, `approved: null`, `actor: "human:desconocido"`, `reason: null`.
  - `review_gate(*, stage, autonomy, run_ctx, review_payload, auto_approve) -> GateResult`:
    - solicitud = `{"schema_version": 1, "stage", "autonomy", **review_payload}`; `request_sha256 = canonical_sha256(solicitud)`; `review_request.yml` = `{"request_sha256": sha, **solicitud}` (`sort_keys=False`) y `decision.template.yml`, ambos atómicos, solo en A0/A1.
    - A2/A3: una sola `auto-proceed` por `(stage, request_sha256)`, `actor="agent:<stage>"`, `detail={reason, request_sha256}`.
    - `decision.yml` con otro `request_sha256` → `paused` sin tocar el ledger ("responde a otra solicitud"). Sin `request_sha256` → `DecisionFileError`.
    - Sin `decision.yml`: si la decisión efectiva del ledger (`summarize_gates`) tiene ese `request_sha256`, se reutiliza (el ledger manda); si no, `auto_approve` crea la decisión sintética `HumanDecision(request_sha256=sha, approved=True, actor="auto-approve (demo)")`; si no, `paused` con un mensaje que nombra la solicitud, la plantilla y `Reanuda con: revisia run --resume <run_dir>`.
    - Ledger idempotente: si la decisión efectiva ya es `(acción, request_sha256, decision_sha256)`, no escribe nada; si esa tupla ya está más atrás (se cambió de opinión y se vuelve a una decisión idéntica), `DecisionFileError` pidiendo cambiar `reason`. `approve`/`reject` llevan `detail = {**extras y reason de decision.yml, request_sha256, decision_sha256, n_labels: 0, forced_human: false}` con `decision_sha256 = canonical_sha256(decision.model_dump(mode="json"))`.
  - `tests/hitl_helpers.py` (`from hitl_helpers import ...`): `leer_solicitud(run_dir: Path, stage: str) -> dict`; `responder_gate(run_dir: Path, stage: str, *, approved: bool = True, actor: str = "human:revisora", reason: str | None = None, records: dict[str, dict] | None = None) -> Path` (escribe `decision.yml` con el `request_sha256` vigente; PR-D le añade `flags`, Tarea 26); `correr_hasta(protocol, protocol_dir, ctx, *, search_fn, fetch_fn=None, etiquetar: Callable[[str, dict], dict | None] | None = None, parar_en: str | None = None, max_vueltas: int = 10) -> PipelineResult` (corre `run_pipeline` sin `auto_approve`; en cada pausa salvo `parar_en` escribe `decision.yml` con `responder_gate(**etiquetar(stage, solicitud))` y reanuda con `RunContext.open`; `AssertionError` si no termina).
  - Payload del gate `reporte` en PR-C: `{"included": n, "hallucination_flagged": bool, "documento_sha256": sha256_text(documento.md)}` (sin la ruta absoluta del entregable; PR-D lo sustituye por `report_payload`).

Por qué cambian tests existentes: `request_sha256` es obligatorio, así que ninguna `decision.yml` se puede escribir antes de correr (no se conoce el hash). `tests/test_hitl.py` pasa a responder en dos vueltas (pausa → decisión con el hash → gate) y sus `detail ==` pasan a subconjunto; los dos tests de `tests/test_pipeline_fake.py` que escribían `decision.yml` por adelantado pasan a `correr_hasta`.

- [ ] **Step 1: Tests que fallan.** Crear `tests/hitl_helpers.py`:

```python
"""Helpers de test del HITL por fichero (Ola 1, spec 2026-10-04 §7).

Los usan los tests de reanudación (PR-C), de HITL por registro (PR-D) y del
auditor (PR-E). Hacen lo que haría un humano: leer la solicitud vigente y
escribir ``decision.yml`` con su ``request_sha256``; ``correr_hasta`` encadena
"correr → pausa → decidir → reanudar" hasta que la corrida termina.

Uso (``tests/`` está en ``sys.path``)::

    from hitl_helpers import correr_hasta, responder_gate
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import yaml

from revisia.config import ReviewProtocol
from revisia.orchestration.pipeline import FetchFn, PipelineResult, SearchFn, run_pipeline
from revisia.orchestration.run_context import RunContext


def leer_solicitud(run_dir: Path, stage: str) -> dict:
    """``<run_dir>/<stage>/review_request.yml`` como mapa."""
    path = Path(run_dir) / stage / "review_request.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def responder_gate(
    run_dir: Path,
    stage: str,
    *,
    approved: bool = True,
    actor: str = "human:revisora",
    reason: str | None = None,
    records: dict[str, dict] | None = None,
) -> Path:
    """Escribe ``decision.yml`` para la solicitud vigente de ``stage``.

    Toma el ``request_sha256`` de ``review_request.yml``. ``records`` va tal
    cual (``{id: {label, reason}}``, cribado por registro, PR-D).
    """
    decision: dict = {
        "request_sha256": leer_solicitud(run_dir, stage)["request_sha256"],
        "approved": approved,
        "actor": actor,
    }
    if reason is not None:
        decision["reason"] = reason
    if records is not None:
        decision["records"] = records
    path = Path(run_dir) / stage / "decision.yml"
    path.write_text(yaml.safe_dump(decision, allow_unicode=True, sort_keys=False), "utf-8")
    return path


def correr_hasta(
    protocol: ReviewProtocol,
    protocol_dir: Path,
    ctx: RunContext,
    *,
    search_fn: SearchFn,
    fetch_fn: FetchFn | None = None,
    etiquetar: Callable[[str, dict], dict | None] | None = None,
    parar_en: str | None = None,
    max_vueltas: int = 10,
) -> PipelineResult:
    """Corre el pipeline y responde a cada pausa como un humano, hasta terminar.

    En cada pausa (salvo en ``parar_en``, donde devuelve el resultado) escribe
    ``decision.yml`` con ``responder_gate``. ``etiquetar(stage, solicitud)``
    devuelve los argumentos extra de ``responder_gate`` para ese gate
    (``{"records": …}``, ``{"approved": False, "reason": …}``…) o ``None`` para
    aprobar sin más. La primera vuelta usa ``ctx``; las siguientes reabren la
    carpeta con ``RunContext.open``, como ``revisia run --resume``.

    Raises:
        AssertionError: si la corrida no termina en ``max_vueltas``.
    """
    contexto = ctx
    for _ in range(max_vueltas):
        result = run_pipeline(
            protocol, protocol_dir, contexto, search_fn=search_fn, fetch_fn=fetch_fn
        )
        if result.status != "paused" or result.stage == parar_en:
            return result
        extra = (
            etiquetar(result.stage, leer_solicitud(ctx.run_dir, result.stage))
            if etiquetar
            else None
        )
        responder_gate(ctx.run_dir, result.stage, **(extra or {}))
        contexto = RunContext.open(ctx.run_dir)
    raise AssertionError(f"la corrida no terminó en {max_vueltas} vueltas")
```

Sustituir `tests/test_hitl.py` completo por:

```python
"""Tests del checkpoint humano file-based (auditoría 2026-09-03, C1 y bajos; Ola 1,
`request_sha256`, ledger idempotente: spec 2026-10-04 §4.3 y §7)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from revisia.orchestration.hitl import DecisionFileError, GateResult, review_gate
from revisia.orchestration.run_context import RunContext
from revisia.provenance.runmeta import canonical_sha256


def _solicitar(
    ctx: RunContext,
    *,
    payload: dict | None = None,
    autonomy: str = "A1",
    auto_approve: bool = False,
) -> GateResult:
    return review_gate(
        stage="reporte",
        autonomy=autonomy,
        run_ctx=ctx,
        review_payload={"included": 1} if payload is None else payload,
        auto_approve=auto_approve,
    )


def _decidir(ctx: RunContext, texto: str, sha: str) -> None:
    """Escribe decision.yml; ``@SHA@`` se sustituye por el hash de la solicitud."""
    path = ctx.stage_dir("reporte") / "decision.yml"
    path.write_text(texto.replace("@SHA@", sha), encoding="utf-8")


def _gate(tmp_path: Path, decision_text: str | None, *, auto_approve: bool = False):
    ctx = RunContext("demo", tmp_path, "T")
    if decision_text is None:
        return ctx, _solicitar(ctx, auto_approve=auto_approve)
    pausa = _solicitar(ctx)  # primera vuelta: escribe la solicitud y pausa
    _decidir(ctx, decision_text, pausa.request_sha256)
    return ctx, _solicitar(ctx, auto_approve=auto_approve)


def test_decision_string_false_does_not_approve(tmp_path: Path) -> None:
    # bool("false") es True: antes, esta decisión APROBABA.
    with pytest.raises(DecisionFileError, match="booleano"):
        _gate(tmp_path, 'request_sha256: "@SHA@"\napproved: "false"\n')


def test_decision_false_rechaza(tmp_path: Path) -> None:
    ctx, result = _gate(
        tmp_path, 'request_sha256: "@SHA@"\napproved: false\nactor: human:revisora\n'
    )
    assert result.status == "rejected"
    entry = ctx.ledger.read_all()[-1]
    assert entry.action == "reject"
    assert entry.actor == "human:revisora"


def test_decision_booleana_aprueba_y_registra_actor(tmp_path: Path) -> None:
    ctx, result = _gate(
        tmp_path, 'request_sha256: "@SHA@"\napproved: true\nactor: human:jhon\nreason: ok\n'
    )
    assert result.status == "approved"
    entry = ctx.ledger.read_all()[-1]
    assert entry.actor == "human:jhon"
    assert {"reason": "ok", "request_sha256": result.request_sha256}.items() <= entry.detail.items()


def test_campos_extra_se_conservan_en_el_ledger(tmp_path: Path) -> None:
    ctx, _ = _gate(tmp_path, 'request_sha256: "@SHA@"\napproved: true\nnota: revisado a mano\n')
    assert ctx.ledger.read_all()[-1].detail["nota"] == "revisado a mano"


@pytest.mark.parametrize(
    "text",
    [
        "- approved: true\n",  # raíz lista (antes: AttributeError)
        "",  # vacío (antes: rechazo silencioso de human:desconocido)
        "approved: [\n",  # YAML roto (antes: traceback de yaml)
        'request_sha256: "@SHA@"\nactor: human:x\n',  # falta approved
    ],
)
def test_malformed_decision_yaml_is_actionable(tmp_path: Path, text: str) -> None:
    with pytest.raises(DecisionFileError, match="decision.yml"):
        _gate(tmp_path, text)


def test_auto_approve_sin_decision(tmp_path: Path) -> None:
    ctx, result = _gate(tmp_path, None, auto_approve=True)
    assert result.status == "approved"
    entry = ctx.ledger.read_all()[-1]
    assert entry.actor == "auto-approve (demo)"
    assert set(entry.detail) == {"request_sha256", "decision_sha256", "n_labels", "forced_human"}
    assert (entry.detail["n_labels"], entry.detail["forced_human"]) == (0, False)


def test_sin_decision_pausa(tmp_path: Path) -> None:
    _, result = _gate(tmp_path, None)
    assert result.status == "paused"


# ── request_sha256 y ledger idempotente (Ola 1, spec 2026-10-04 §7) ─────────


def test_gate_exige_request_sha256(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _solicitar(ctx)
    plantilla = (ctx.run_dir / "reporte" / "decision.template.yml").read_text(encoding="utf-8")
    assert f'request_sha256: "{pausa.request_sha256}"' in plantilla
    assert "approved: null" in plantilla
    assert "revisia run --resume" in pausa.message and "decision.template.yml" in pausa.message

    _decidir(ctx, "approved: true\nactor: human:x\n", pausa.request_sha256)  # sin el hash
    with pytest.raises(DecisionFileError, match="request_sha256"):
        _solicitar(ctx)
    assert ctx.ledger.read_all() == []


def test_decision_obsoleta_pausa_sin_aplicar(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    vieja = _solicitar(ctx, payload={"included": 1})
    _decidir(ctx, 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n', vieja.request_sha256)

    nueva = _solicitar(ctx, payload={"included": 2})  # la solicitud cambió

    assert nueva.status == "paused"
    assert nueva.request_sha256 != vieja.request_sha256
    assert "otra solicitud" in nueva.message
    assert ctx.ledger.read_all() == []  # no se aplicó nada
    solicitud = yaml.safe_load(
        (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")
    )
    assert solicitud["request_sha256"] == nueva.request_sha256


def test_ledger_idempotente_al_reanudar(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _solicitar(ctx)
    _decidir(ctx, 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n', pausa.request_sha256)
    for _ in range(3):  # tres reanudaciones con la misma decisión
        assert _solicitar(ctx).status == "approved"
    assert [e.action for e in ctx.ledger.read_all()] == ["approve"]

    # Cambiar de opinión es legítimo y queda registrado (D14).
    _decidir(
        ctx, 'request_sha256: "@SHA@"\napproved: false\nactor: human:x\n', pausa.request_sha256
    )
    assert _solicitar(ctx).status == "rejected"
    assert _solicitar(ctx).status == "rejected"
    assert [e.action for e in ctx.ledger.read_all()] == ["approve", "reject"]

    # auto-proceed (A2) tampoco se duplica.
    for _ in range(2):
        _solicitar(ctx, autonomy="A2")
    assert [e.action for e in ctx.ledger.read_all()].count("auto-proceed") == 1


def test_ledger_reconstruye_decision_sin_decision_yml(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _solicitar(ctx)
    _decidir(ctx, 'request_sha256: "@SHA@"\napproved: true\nactor: human:x\n', pausa.request_sha256)
    assert _solicitar(ctx).status == "approved"
    (ctx.run_dir / "reporte" / "decision.yml").unlink()  # el canal de entrada desaparece

    result = _solicitar(ctx)

    assert (result.status, result.actor) == ("approved", "human:x")  # el ledger manda
    assert len(ctx.ledger.read_all()) == 1
    # Una solicitud distinta no hereda esa decisión.
    assert _solicitar(ctx, payload={"included": 2}).status == "paused"


def test_request_sha256_recomputable_desde_yaml(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    payload = {"records": [{"record_id": "10.1/ñ", "votes": [{"label": "include"}]}], "n": 1}
    result = _solicitar(ctx, payload=payload)
    solicitud = yaml.safe_load(
        (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")
    )
    sha = solicitud.pop("request_sha256")
    assert sha == result.request_sha256 == canonical_sha256(solicitud)
    assert (solicitud["schema_version"], solicitud["stage"], solicitud["autonomy"]) == (
        1,
        "reporte",
        "A1",
    )
```

En `tests/test_pipeline_fake.py`, sustituir

```python
import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible
```

por

```python
import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible
from hitl_helpers import correr_hasta
```

sustituir el principio de `test_rejected_final_gate_is_not_completed`

```python
def test_rejected_final_gate_is_not_completed(tmp_path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST")
    (ctx.stage_dir("reporte") / "decision.yml").write_text(
        "approved: false\nactor: human:revisora\nreason: síntesis sin respaldo\n",
        encoding="utf-8",
    )
    result = run_pipeline(
        protocol, EXAMPLE, ctx, max_results=10, auto_approve=True, search_fn=_fake_search
    )
    assert result.status == "rejected"  # antes: "completed"
```

por

```python
def test_rejected_final_gate_is_not_completed(tmp_path) -> None:
    # Desde la Ola 1 una decisión.yml lleva el request_sha256 de su solicitud, así
    # que no se puede escribir antes de correr: el humano responde a cada pausa
    # (aprueba los gates de juicio) y rechaza el reporte final.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST")

    def rechazar_el_reporte(stage: str, _solicitud: dict) -> dict | None:
        if stage == "reporte":
            return {"approved": False, "reason": "síntesis sin respaldo"}
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
        etiquetar=rechazar_el_reporte,
    )
    assert result.status == "rejected"  # antes: "completed"
```

y el principio de `test_paused_run_final_gate_falla_en_auditoria`

```python
def test_paused_run_final_gate_falla_en_auditoria(tmp_path) -> None:
    # Aprueba en humano las etapas de juicio previas al reporte (screening_ta,
    # screening_ft, extraccion, rob) para que, sin auto-approve, la corrida
    # llegue viva hasta el checkpoint final y pause justo ahí (A1): es ese gate
    # el que queremos ver fallar en la auditoría, no uno anterior.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST-PAUSED")
    decision_humana = "approved: true\nactor: human:revisora\n"
    for stage in ("screening_ta", "screening_ft", "extraccion", "rob"):
        (ctx.stage_dir(stage) / "decision.yml").write_text(decision_humana, encoding="utf-8")

    result = run_pipeline(protocol, EXAMPLE, ctx, auto_approve=False, search_fn=_fake_search)
```

por

```python
def test_paused_run_final_gate_falla_en_auditoria(tmp_path) -> None:
    # Aprueba en humano las etapas de juicio previas al reporte (screening_ta,
    # screening_ft, extraccion, rob), respondiendo a cada pausa con el
    # request_sha256 de su solicitud, para que la corrida llegue viva hasta el
    # checkpoint final y pause justo ahí (A1): es ese gate el que queremos ver
    # fallar en la auditoría, no uno anterior.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST-PAUSED")

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
        parar_en="reporte",
    )
```

(el resto de ambos tests no cambia).

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl.py tests/test_pipeline_fake.py -v`
Expected: FAIL 14 de los 15 tests de `tests/test_hitl.py`, todos salvo `test_sin_decision_pausa` (`AttributeError: 'GateResult' object has no attribute 'request_sha256'`, `FileNotFoundError` de `decision.template.yml`, `KeyError: 'request_sha256'`…), y los dos de `tests/test_pipeline_fake.py` que usan `correr_hasta` (`KeyError: 'request_sha256'` en `leer_solicitud`).

- [ ] **Step 3: Implementar el gate** — sustituir `revisia/orchestration/hitl.py` completo por:

```python
"""Checkpoint humano (HITL) reproducible y SIN servidor.

En lugar de depender del pause server de Prefect (que exigiría infraestructura
y rompería el "clónalo y córrelo"), el gate es file-based:

  * Escribe ``<stage>/review_request.yml`` con lo que el humano debe revisar y su
    ``request_sha256`` (hash canónico del contenido), y a su lado
    ``decision.template.yml``, la decisión a medio rellenar.
  * Si existe ``<stage>/decision.yml`` con el ``request_sha256`` de la solicitud
    vigente (o ``--auto-approve``), aplica la decisión y la registra en el ledger
    (validado: ``approved`` booleano estricto; un fichero inválido detiene la
    corrida con un mensaje accionable). Una decisión que responde a otra
    solicitud pausa sin aplicar nada.
  * Si no, devuelve estado ``paused``: el orquestador se detiene e indica al
    humano cómo rellenar la decisión y reanudar.

El ledger manda (Ola 1, spec 2026-10-04 §4.3): registrar es idempotente al
reanudar y, sin ``decision.yml``, la decisión ya registrada para la solicitud
vigente se reutiliza (``decision.yml`` es solo el canal de entrada). Las
decisiones quedan en el ledger → reproducibilidad "a nivel decisión".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import AUTO_APPROVE_ACTOR, DecisionEntry, summarize_gates
from revisia.provenance.runmeta import canonical_sha256
from revisia.schemas.artifacts import ARTIFACT_SCHEMA_VERSION

GateStatus = Literal["approved", "paused", "rejected"]

REQUEST_FILE = "review_request.yml"
TEMPLATE_FILE = "decision.template.yml"
DECISION_FILE = "decision.yml"


@dataclass(slots=True)
class GateResult:
    """Resultado de un gate.

    Attributes:
        status: ``approved`` | ``paused`` | ``rejected``.
        message: texto para el humano (pausa: qué revisar y cómo reanudar).
        request_sha256: hash de la solicitud vigente.
        actor: quién decidió (``None`` en una pausa).
    """

    status: GateStatus
    message: str
    request_sha256: str | None = None
    actor: str | None = None


class DecisionFileError(ValueError):
    """``decision.yml`` ilegible o inválido: mensaje accionable, no traceback."""


class HumanDecision(BaseModel):
    """Contenido validado de ``<stage>/decision.yml`` (auditoría 2026-09-03, C1).

    ``request_sha256`` ata la decisión a la solicitud que el humano revisó
    (D4): si la solicitud cambia, una decisión vieja no se aplica.
    ``approved`` es un booleano YAML estricto: la cadena ``"false"`` ya no
    aprueba (``bool("false")`` es ``True``). Los campos extra se conservan y
    viajan al ``detail`` del ledger.
    """

    model_config = ConfigDict(extra="allow")

    request_sha256: str
    approved: StrictBool
    actor: str = "human:desconocido"
    reason: str | None = None


def render_decision_template(*, stage: str, autonomy: str, request_sha256: str) -> str:
    """``decision.template.yml``: la decisión a medio rellenar (D4).

    ``approved: null`` la hace inválida tal cual: aprobar tiene que ser un acto
    deliberado. Las cadenas van entre comillas dobles (JSON es YAML válido).
    """
    lines = [
        f"# Decisión humana del gate '{stage}' (autonomía {autonomy}).",
        "#",
        "# 1. Revisa review_request.yml, en esta misma carpeta.",
        "# 2. Copia este fichero como decision.yml y pon `approved: true` (aprobar)",
        "#    o `approved: false` (rechazar). Tal cual NO es válido: `approved: null`",
        "#    no aprueba ni rechaza.",
        "# 3. Pon tu nombre en `actor` (human:<nombre>) y, si quieres, una razón.",
        "# 4. Reanuda: revisia run --resume <carpeta de esta corrida>",
        "#",
        "# `request_sha256` ata la decisión a esta solicitud: si la solicitud cambia,",
        "# una decisión vieja no se aplica y la corrida vuelve a pausar.",
        f"request_sha256: {json.dumps(request_sha256)}",
        "approved: null",
        'actor: "human:desconocido"',
        "reason: null",
    ]
    return "\n".join(lines) + "\n"


def _recorded(
    entries: list[DecisionEntry],
    *,
    stage: str,
    action: str,
    target: str | None,
    request_sha256: str,
    decision_sha256: str | None,
) -> bool:
    """¿Ya está en el ledger la tupla ``(stage, action, target, request, decision)``?"""
    return any(
        (
            e.stage,
            e.action,
            e.target,
            e.detail.get("request_sha256"),
            e.detail.get("decision_sha256"),
        )
        == (stage, action, target, request_sha256, decision_sha256)
        for e in entries
    )


def _register(
    run_ctx: RunContext,
    entries: list[DecisionEntry],
    *,
    stage: str,
    autonomy: str,
    decision: HumanDecision,
    request_sha256: str,
) -> None:
    """Registra la decisión en el ledger, una sola vez (idempotente al reanudar)."""
    decision_sha256 = canonical_sha256(decision.model_dump(mode="json"))
    action = "approve" if decision.approved else "reject"
    effective = summarize_gates(entries).get(stage)
    if effective is not None and (
        effective.action,
        effective.request_sha256,
        effective.decision_sha256,
    ) == (action, request_sha256, decision_sha256):
        return  # ya es la decisión efectiva: reanudar no la duplica
    if _recorded(
        entries,
        stage=stage,
        action=action,
        target=None,
        request_sha256=request_sha256,
        decision_sha256=decision_sha256,
    ):
        raise DecisionFileError(
            f"{stage}: esta misma decisión ya se registró antes y después se cambió; para "
            "volver a ella, cambia `reason` en decision.yml (el ledger no repite una "
            "decisión idéntica)."
        )
    detail = {
        **decision.model_dump(exclude={"approved", "actor", "request_sha256"}, exclude_none=True),
        "request_sha256": request_sha256,
        "decision_sha256": decision_sha256,
        "n_labels": 0,
        "forced_human": False,
    }
    run_ctx.ledger.append(
        DecisionEntry(
            stage=stage, actor=decision.actor, autonomy=autonomy, action=action, detail=detail
        )
    )


def review_gate(
    *,
    stage: str,
    autonomy: str,
    run_ctx: RunContext,
    review_payload: dict,
    auto_approve: bool,
) -> GateResult:
    """Aplica el checkpoint humano de una etapa según su autonomía.

    La solicitud es ``{schema_version, stage, autonomy, **review_payload}`` y su
    ``request_sha256`` es ``canonical_sha256`` de ese contenido: sin rutas
    absolutas ni horas, para que sea estable entre reanudaciones (spec §4.3).

    A2/A3 no pausan (registran ``auto-proceed`` y continúan). A0/A1 requieren
    una decisión: ``decision.yml`` con el hash vigente, la ya registrada en el
    ledger para esa solicitud, o ``auto_approve``; si no hay ninguna, pausan.
    """
    payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "stage": stage,
        "autonomy": autonomy,
        **review_payload,
    }
    request_sha256 = canonical_sha256(payload)
    entries = run_ctx.ledger.read_all()

    if autonomy in {"A2", "A3"}:
        if not _recorded(
            entries,
            stage=stage,
            action="auto-proceed",
            target=None,
            request_sha256=request_sha256,
            decision_sha256=None,
        ):
            run_ctx.ledger.append(
                DecisionEntry(
                    stage=stage,
                    actor=f"agent:{stage}",
                    autonomy=autonomy,
                    action="auto-proceed",
                    detail={
                        "reason": f"autonomía {autonomy}: ejecuta y notifica",
                        "request_sha256": request_sha256,
                    },
                )
            )
        return GateResult(
            "approved", f"{stage}: auto-proceed ({autonomy}).", request_sha256, f"agent:{stage}"
        )

    # A0/A1 → requiere humano.
    stage_dir = run_ctx.stage_dir(stage)
    run_ctx.write_text(
        f"{stage}/{REQUEST_FILE}",
        yaml.safe_dump(
            {"request_sha256": request_sha256, **payload}, allow_unicode=True, sort_keys=False
        ),
    )
    run_ctx.write_text(
        f"{stage}/{TEMPLATE_FILE}",
        render_decision_template(stage=stage, autonomy=autonomy, request_sha256=request_sha256),
    )
    request_path = stage_dir / REQUEST_FILE
    decision_path = stage_dir / DECISION_FILE
    resume = f"Reanuda con: revisia run --resume {run_ctx.run_dir}"

    decision = _read_decision(decision_path)
    if decision is not None and decision.request_sha256 != request_sha256:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}': {decision_path} responde a otra solicitud "
                f"(request_sha256 {decision.request_sha256[:12]}…; la vigente es "
                f"{request_sha256[:12]}…). No se aplicó nada: revisa {request_path} y "
                f"rellena de nuevo la decisión desde {stage_dir / TEMPLATE_FILE}. {resume}"
            ),
            request_sha256,
        )
    if decision is None:
        effective = summarize_gates(entries).get(stage)
        if effective is not None and effective.request_sha256 == request_sha256:
            # El ledger manda: la decisión de esta solicitud ya está registrada.
            approved = effective.action != "reject"
            return GateResult(
                "approved" if approved else "rejected",
                f"{stage}: {'aprobado' if approved else 'rechazado'} por {effective.actor} "
                "(decisión registrada en el ledger).",
                request_sha256,
                effective.actor,
            )
        if auto_approve:
            decision = HumanDecision(
                request_sha256=request_sha256, approved=True, actor=AUTO_APPROVE_ACTOR
            )
    if decision is None:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}' ({autonomy}). Revisa {request_path}, rellena "
                f"{stage_dir / TEMPLATE_FILE} y guárdalo como {decision_path} (o vuelve a "
                f"correr con --auto-approve). {resume}"
            ),
            request_sha256,
        )

    _register(
        run_ctx,
        entries,
        stage=stage,
        autonomy=autonomy,
        decision=decision,
        request_sha256=request_sha256,
    )
    if decision.approved:
        return GateResult(
            "approved", f"{stage}: aprobado por {decision.actor}.", request_sha256, decision.actor
        )
    return GateResult(
        "rejected", f"{stage}: rechazado por {decision.actor}.", request_sha256, decision.actor
    )


_DECISION_HINT = (
    "Se espera un mapa YAML con `request_sha256` (el de review_request.yml; parte de "
    "decision.template.yml), `approved: true` o `approved: false` (booleano, sin "
    "comillas) y, opcionalmente, `actor: human:<nombre>` y `reason: <texto>`."
)


def _read_decision(path: Path) -> HumanDecision | None:
    """Lee y valida ``decision.yml``; ``None`` si no existe.

    Raises:
        DecisionFileError: si el fichero está vacío, no es YAML válido, su raíz
            no es un mapa, falta ``request_sha256`` o ``approved`` no es un
            booleano.
    """
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DecisionFileError(f"{path}: YAML inválido ({exc}). {_DECISION_HINT}") from exc
    if raw is None:
        raise DecisionFileError(f"{path}: está vacío. {_DECISION_HINT}")
    if not isinstance(raw, dict):
        raise DecisionFileError(
            f"{path}: la raíz es {type(raw).__name__}, no un mapa. {_DECISION_HINT}"
        )
    try:
        return HumanDecision.model_validate(raw)
    except ValidationError as exc:
        detalle = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise DecisionFileError(f"{path}: decisión inválida ({detalle}). {_DECISION_HINT}") from exc
```

- [ ] **Step 4: Payload del reporte sin rutas absolutas.** En `revisia/orchestration/pipeline.py` (`_run_stages`), sustituir

```python
    # Checkpoint final del reporte (A1).
    final_gate = run.gate(
        "reporte",
        {
            "included": len(included),
            "hallucination_flagged": verification.hallucination_flagged,
            "deliverable": str(deliverable),
        },
    )
```

por

```python
    # Checkpoint final del reporte (A1). La solicitud no lleva rutas absolutas (su
    # hash tiene que ser estable entre reanudaciones): el documento va por su hash.
    documento = (deliverable / "documento.md").read_text(encoding="utf-8")
    final_gate = run.gate(
        "reporte",
        {
            "included": len(included),
            "hallucination_flagged": verification.hallucination_flagged,
            "documento_sha256": sha256_text(documento),
        },
    )
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl.py tests/test_pipeline_fake.py tests/test_cli_errores.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 441 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/orchestration/hitl.py revisia/orchestration/pipeline.py tests/hitl_helpers.py tests/test_hitl.py tests/test_pipeline_fake.py
git commit -m "feat(hitl): request_sha256 canónico, plantilla y ledger idempotente" -m "Cada solicitud lleva request_sha256 = canonical_sha256(payload) y decision.yml lo exige: una decisión de otra solicitud pausa sin aplicar nada. Junto a la solicitud se escribe decision.template.yml (approved: null, inválida hasta rellenarla, D4). Registrar es idempotente al reanudar y, sin decision.yml, la decisión del ledger para esa solicitud se reutiliza. El payload del reporte deja de llevar la ruta absoluta del entregable. tests/hitl_helpers.py (responder_gate, correr_hasta) para PR-C, PR-D y el auditor. Spec 2026-10-04 §4.3 y §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Diario del cribado T/A (A9: un 429 a mitad ya no pierde la etapa)

Primera de las etapas con diario (spec §7: un commit por etapa, en el orden T/A → recuperación → FT → extracción → RoB → síntesis y verificación).

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (imports l.22-23 y l.67; función nueva antes de `_screen_ta` l.323; cuerpo de `_screen_ta` l.328-354)
- Test: `tests/test_reanudacion.py` (import l.18-19; helper y test nuevos al final)

**Interfaces:**
- Consumes: `StageJournal`, `journaled` (Tareas 2 y 4); `screening_agent.screen_record` (existente; devuelve `(decision, metas)`, que es justo el contrato de `compute`).
- Produces: `03_screening/journal.jsonl` con una `JournalEntry` por registro (`stage="screening_ta"`, `output` = `ScreeningDecision` del ensemble **sin** campos humanos ni `final_label`, `metas` = una `LLMCall` por miembro con `role="member:<i>"`). `inputs` = `{"title", "abstract", "question", "criteria", "miembros": [[model_name, temperature, seed], …]}`. `_member_role(i) -> str` (`"member:<i>"`).

- [ ] **Step 1: Test que falla.** En `tests/test_reanudacion.py`, sustituir

```python
from revisia.orchestration.snapshot import read_run_info
from revisia.schemas.records import SearchRecord
```

por

```python
from revisia.orchestration.snapshot import read_run_info
from revisia.schemas.artifacts import JournalEntry
from revisia.schemas.records import SearchRecord
```

y añadir al final del fichero:

```python


def _diario(ctx: RunContext, relpath: str) -> list[JournalEntry]:
    path = ctx.run_dir / relpath
    if not path.exists():
        return []
    return [JournalEntry.model_validate_json(x) for x in path.read_text("utf-8").splitlines()]


def test_429_a_mitad_del_cribado_conserva_diario_y_reanuda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A9: un 429 en cualquier registro perdía la etapa entera. Dos miembros por
    # registro: la llamada 3 es la del primer miembro sobre rec-2.
    proveedor = ScriptedProvider(fail_at=3)
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    with pytest.raises(RunInterrupted):
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    assert [e.record_id for e in _diario(ctx, "03_screening/journal.jsonl")] == ["rec-1"]
    assert len(ctx.llm_calls_path.read_text("utf-8").splitlines()) == 2

    result = resume_review(ctx.run_dir)

    assert (result.status, result.stage) == ("paused", "screening_ta")
    # Cada registro se cribó una vez: rec-1 sale del diario; rec-2, al reanudar.
    assert sum("LLM screening" in p for p in proveedor.prompts) == 2
    assert sum("Active learning" in p for p in proveedor.prompts) == 3  # 1 fallida + 2
    entradas = _diario(ctx, "03_screening/journal.jsonl")
    assert [e.record_id for e in entradas] == ["rec-1", "rec-2"]
    assert [len(e.metas) for e in entradas] == [2, 2]
    assert len(ctx.llm_calls_path.read_text("utf-8").splitlines()) == 4
    info = read_run_info(ctx.run_dir)
    assert (info.status, len(info.interruptions), len(info.resumes)) == ("paused", 1, 1)
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py::test_429_a_mitad_del_cribado_conserva_diario_y_reanuda -v`
Expected: FAIL con `assert [] == ['rec-1']`: sin diario, el registro ya cribado se pierde con el 429.

- [ ] **Step 3: Implementar.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from dataclasses import dataclass, field
from pathlib import Path
```

por

```python
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
```

sustituir

```python
from revisia.orchestration.journal import JournalError
```

por

```python
from revisia.orchestration.journal import JournalError, StageJournal, journaled
```

justo antes de `_screen_ta`, sustituir

```python
def _screen_ta(
```

por

```python
def _member_role(i: int) -> str:
    """Rol de la llamada ``i`` del ensemble de T/A en ``llm_calls.jsonl``."""
    return f"member:{i}"


def _screen_ta(
```

y en `_screen_ta`, sustituir

```python
    Deja las métricas frente al gold (Recall/Lost-Evidence, MCC, WMCC, kappa)
    en ``run.metrics``.
    """
    members = [
        screening_agent.ScreenerMember(
            provider=build_provider(cfg),
            model_name=f"{cfg.provider}:{cfg.model}",
            temperature=cfg.temperature,
            seed=cfg.seed,
        )
        for cfg in run.protocol.screeners_for("screening_ta")
    ]
    decisions = []
    for record in deduped:
        decision, metas = screening_agent.screen_record(
            members,
            question=run.question,
            criteria=run.criteria,
            record=record,
        )
        decision.final_label = decision.human_label or decision.ensemble_label
        decisions.append(decision)
        for i, meta in enumerate(metas):
            run.ctx.record_meta(
                meta, stage="screening_ta", record_id=record.record_id, role=f"member:{i}"
            )
    run.ctx.write_json("03_screening/decisions.json", [d.model_dump() for d in decisions])
```

por

```python
    Cada registro pasa por el diario de T/A (``03_screening/journal.jsonl``): al
    reanudar, un registro ya cribado no se vuelve a llamar (A9). Deja las
    métricas frente al gold (Recall/Lost-Evidence, MCC, WMCC, kappa) en
    ``run.metrics``.
    """
    members = [
        screening_agent.ScreenerMember(
            provider=build_provider(cfg),
            model_name=f"{cfg.provider}:{cfg.model}",
            temperature=cfg.temperature,
            seed=cfg.seed,
        )
        for cfg in run.protocol.screeners_for("screening_ta")
    ]
    miembros = [[m.model_name, m.temperature, m.seed] for m in members]
    journal = StageJournal(run.ctx, "screening_ta")
    decisions = []
    for record in deduped:
        decision = journaled(
            journal,
            record_id=record.record_id,
            inputs={
                "title": record.title,
                "abstract": record.abstract,
                "question": run.question,
                "criteria": run.criteria,
                "miembros": miembros,
            },
            model=ScreeningDecision,
            compute=partial(
                screening_agent.screen_record,
                members,
                question=run.question,
                criteria=run.criteria,
                record=record,
            ),
            run_ctx=run.ctx,
            role_of=_member_role,
        )
        decision.final_label = decision.human_label or decision.ensemble_label
        decisions.append(decision)
    run.ctx.write_json("03_screening/decisions.json", [d.model_dump() for d in decisions])
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py tests/test_pipeline_fake.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 442 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/pipeline.py tests/test_reanudacion.py
git commit -m "feat(pipeline): diario del cribado T/A (A9)" -m "Cada registro cribado va a 03_screening/journal.jsonl en cuanto termina, con la llamada de cada miembro del ensemble en llm_calls.jsonl. Un 429 en el registro k ya no pierde los anteriores: al reanudar, cada registro se criba una sola vez. input_sha256 sobre título, abstract, pregunta, criterios y miembros (spec 2026-10-04 §7)." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Gold efectivo en `03_screening/gold.json` (D6)

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (`_screen_ta`, l.377-378)
- Test: `tests/test_snapshot.py` (test nuevo al final)

**Interfaces:**
- Consumes: `_load_gold` (Tarea 5: `00_protocol/gold.yml` + `gold_labels=`, que tienen prioridad).
- Produces: `03_screening/gold.json` = `{record_id: bool}` (claves ordenadas), solo si hay gold. `compute_screening_metrics` recibe ese mismo gold efectivo.

- [ ] **Step 1: Test que falla** — añadir al final de `tests/test_snapshot.py`:

```python


def test_gold_efectivo_persistido(tmp_path: Path) -> None:
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    (proto / "gold.yml").write_text('gold:\n  "rec-1": true\n  "rec-2": true\n', "utf-8")
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    run_pipeline(protocol, proto, ctx, search_fn=_busqueda, gold_labels={"rec-2": False})

    # 00_protocol/gold.yml más las etiquetas por código, que tienen prioridad.
    assert (ctx.run_dir / "00_protocol" / "gold.yml").exists()
    gold = json.loads((ctx.run_dir / "03_screening" / "gold.json").read_text(encoding="utf-8"))
    assert gold == {"rec-1": True, "rec-2": False}
    metricas = json.loads((ctx.run_dir / "03_screening" / "metrics.json").read_text("utf-8"))
    assert metricas["n"] == 2
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_snapshot.py::test_gold_efectivo_persistido -v`
Expected: FAIL con `FileNotFoundError` de `03_screening/gold.json`.

- [ ] **Step 3: Implementar.** En `revisia/orchestration/pipeline.py` (`_screen_ta`), sustituir

```python
    if gold:
        run.metrics = compute_screening_metrics(
```

por

```python
    if gold:
        # Gold efectivo (fichero + `gold_labels=`), para que el auditor recalcule
        # las métricas desde disco (D6).
        run.ctx.write_json("03_screening/gold.json", dict(sorted(gold.items())))
        run.metrics = compute_screening_metrics(
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_snapshot.py -v`
Expected: PASS, 6 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 443 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/pipeline.py tests/test_snapshot.py
git commit -m "feat(metrics): gold efectivo en 03_screening/gold.json (D6)" -m "El gold con el que se calculan las métricas (00_protocol/gold.yml más gold_labels=) queda en disco, para que el auditor recalcule recall y kappa en vez de creerse metrics.json. Spec 2026-10-04 §4.2 y §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Diario de la recuperación y caché del texto completo

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (import l.84; `_fulltext` completo l.388-449, que se parte en `_fetch_one`, `_cached_text`, `_retrieve` y `_fulltext`)
- Test: `tests/test_reanudacion.py` (imports l.9, l.14-15 y l.18-19; test nuevo al final)

**Interfaces:**
- Consumes: `StageJournal`, `journaled` (Tareas 2 y 4); `JournalError` (Tarea 2); `RetrievalOutcome` (PR-0); `correr_hasta` (Tarea 9).
- Produces:
  - `04_fulltext/retrieval.jsonl` (`stage="fulltext_retrieval"`, `metas=[]`, `output` = `RetrievalOutcome`), con `inputs` = `{"record_id", "doi", "extra": {k: extra[k] para k en ("fulltext_url", "oa_url", "pmcid", "pmid") presentes}, "mailto_set"}`.
  - Caché `04_fulltext/texts/<sha256_text(record_id)[:16]>.txt` en bytes UTF-8; `RetrievalOutcome.text_file` es esa ruta relativa. Al reanudar, el texto sale de la caché y se verifica contra `text_sha256`; si no coincide, `JournalError`.
  - `04_fulltext/retrieval.json` = `[{"record_id", **RetrievalOutcome}]` en el orden de `passed_ta` (ahora con `text_file`).
  - `_FullTextStage` sin cambios en esta tarea; `_retrieve(run, passed_ta, fetch_fn) -> tuple[dict[str, RetrievalOutcome], dict[str, str]]`.

- [ ] **Step 1: Test que falla.** En `tests/test_reanudacion.py`, sustituir

```python
from fakes import ScriptedProvider, fetch_disponible
```

por

```python
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import correr_hasta
```

sustituir

```python
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.flow import resume_review
```

por

```python
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.flow import resume_review
from revisia.orchestration.journal import JournalError
```

sustituir

```python
from revisia.orchestration.snapshot import read_run_info
from revisia.schemas.artifacts import JournalEntry
```

por

```python
from revisia.orchestration.snapshot import read_run_info
from revisia.provenance.runmeta import sha256_text
from revisia.schemas.artifacts import JournalEntry
```

y añadir al final del fichero:

```python


def test_recuperacion_en_diario_y_texto_en_cache(tmp_path: Path) -> None:
    descargas: list[str] = []

    def fetch(record: SearchRecord):
        descargas.append(record.record_id)
        return fetch_disponible(record)

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    pausa = correr_hasta(
        protocol, EXAMPLE, ctx, search_fn=_busqueda, fetch_fn=fetch, parar_en="screening_ft"
    )
    assert (pausa.status, pausa.stage) == ("paused", "screening_ft")
    assert descargas == ["rec-1", "rec-2"]

    # Reanudar no vuelve a descargar: el resultado sale del diario y el texto, de la caché.
    otra = run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)
    assert (otra.status, otra.stage) == ("paused", "screening_ft")
    assert descargas == ["rec-1", "rec-2"]
    cache = ctx.run_dir / "04_fulltext" / "texts" / f"{sha256_text('rec-1')[:16]}.txt"
    assert "LLM screening for systematic reviews" in cache.read_text(encoding="utf-8")
    entradas = _diario(ctx, "04_fulltext/retrieval.jsonl")
    assert [(e.record_id, e.metas) for e in entradas] == [("rec-1", []), ("rec-2", [])]

    # Un texto en caché alterado no se usa en silencio.
    cache.write_text("otro texto", encoding="utf-8")
    with pytest.raises(JournalError, match="caché"):
        run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py::test_recuperacion_en_diario_y_texto_en_cache -v`
Expected: FAIL: al reanudar se vuelve a descargar (`['rec-1', 'rec-2', 'rec-1', 'rec-2'] == ['rec-1', 'rec-2']`).

- [ ] **Step 3: Implementar.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.provenance.runmeta import sha256_text, utc_now_iso
```

por

```python
from revisia.provenance.runmeta import RunMeta, sha256_text, utc_now_iso
```

y sustituir `_fulltext` completo

```python
def _fulltext(run: _Run, passed_ta: list[SearchRecord], fetch_fn: FetchFn | None) -> _FullTextStage:
    """Texto completo + cribado a texto completo (A0).

    PRISMA estricto (D2; auditoría 2026-09-03, M11): un informe sin texto
    completo NO se criba con IA (antes se cribaba con el abstract y contaba
    como evaluado). Queda como "no recuperado", con su motivo en
    04_fulltext/retrieval.json, y no llega a extracción.
    """
    fetch = fetch_fn or (lambda rec: fulltext_agent.fetch_fulltext(rec, mailto=run.mailto))
    ft_cfg = run.protocol.provider_for("screening_ft")
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
            ft_provider,
            ft_model,
            question=run.question,
            criteria=run.criteria,
            record=record,
            text=ft.text,
            temperature=ft_cfg.temperature,
            seed=ft_cfg.seed,
        )
        decision.fulltext_status = "retrieved"
        decision.final_label = decision.human_label or decision.ensemble_label
        ft_decisions.append(decision)
        run.ctx.record_meta(meta, stage="screening_ft", record_id=record.record_id)
    run.ctx.write_json("04_fulltext/retrieval.json", retrieval)
    run.ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])
    not_retrieved = sum(1 for d in ft_decisions if d.fulltext_status == "not_retrieved")
    return _FullTextStage(ft_decisions, fulltexts, not_retrieved)
```

por

```python
# Claves de `SearchRecord.extra` que usa la recuperación de texto completo
# (`agents/fulltext.py`): entran en el `input_sha256` de su diario.
_RETRIEVAL_EXTRA: tuple[str, ...] = ("fulltext_url", "oa_url", "pmcid", "pmid")


def _fetch_one(
    run: _Run, fetch: FetchFn, record: SearchRecord
) -> tuple[RetrievalOutcome, list[RunMeta]]:
    """Recupera un texto completo y, si lo hay, lo guarda en la caché de la corrida.

    El fichero es ``04_fulltext/texts/<sha256(id)[:16]>.txt`` (ningún
    ``record_id`` como nombre de fichero, spec §4.1), en bytes UTF-8 para que su
    hash no dependa del fin de línea del sistema. Sin LLM: ninguna llamada.
    """
    ft = fetch(record)
    if not ft.available:
        # Un fetch_fn inyectado puede no dar motivo: el genérico es no_disponible.
        outcome = RetrievalOutcome(
            available=False,
            source_url=ft.source_url,
            reason=ft.reason or "no_disponible",
            detail=ft.detail,
        )
        return outcome, []
    text_file = f"04_fulltext/texts/{sha256_text(record.record_id)[:16]}.txt"
    path = run.ctx.run_dir / text_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ft.text.encode("utf-8"))
    outcome = RetrievalOutcome(
        available=True,
        source_url=ft.source_url,
        n_chars=len(ft.text),
        text_sha256=sha256_text(ft.text),
        text_file=text_file,
    )
    return outcome, []


def _cached_text(run: _Run, outcome: RetrievalOutcome) -> str:
    """Texto completo de la caché, verificado contra el hash de su diario."""
    text = (run.ctx.run_dir / outcome.text_file).read_bytes().decode("utf-8")
    if sha256_text(text) != outcome.text_sha256:
        raise JournalError(
            f"{outcome.text_file}: el texto en caché no coincide con el hash de su diario; "
            "la corrida ya no es fiable."
        )
    return text


def _retrieve(
    run: _Run, passed_ta: list[SearchRecord], fetch_fn: FetchFn | None
) -> tuple[dict[str, RetrievalOutcome], dict[str, str]]:
    """Recuperación de texto completo con diario (``04_fulltext/retrieval.jsonl``).

    Al reanudar no se vuelve a descargar nada: el resultado sale del diario y el
    texto, de la caché. Escribe ``04_fulltext/retrieval.json`` en el orden de
    ``passed_ta``.
    """
    fetch = fetch_fn or (lambda rec: fulltext_agent.fetch_fulltext(rec, mailto=run.mailto))
    journal = StageJournal(run.ctx, "fulltext_retrieval")
    outcomes: dict[str, RetrievalOutcome] = {}
    texts: dict[str, str] = {}
    for record in passed_ta:
        outcome = journaled(
            journal,
            record_id=record.record_id,
            inputs={
                "record_id": record.record_id,
                "doi": record.doi,
                "extra": {k: record.extra[k] for k in _RETRIEVAL_EXTRA if k in record.extra},
                "mailto_set": bool(run.mailto),
            },
            model=RetrievalOutcome,
            compute=partial(_fetch_one, run, fetch, record),
            run_ctx=run.ctx,
        )
        outcomes[record.record_id] = outcome
        if outcome.available:
            texts[record.record_id] = _cached_text(run, outcome)
    run.ctx.write_json(
        "04_fulltext/retrieval.json",
        [{"record_id": rid, **o.model_dump(mode="json")} for rid, o in outcomes.items()],
    )
    return outcomes, texts


def _fulltext(run: _Run, passed_ta: list[SearchRecord], fetch_fn: FetchFn | None) -> _FullTextStage:
    """Texto completo + cribado a texto completo (A0).

    PRISMA estricto (D2; auditoría 2026-09-03, M11): un informe sin texto
    completo NO se criba con IA (antes se cribaba con el abstract y contaba
    como evaluado). Queda como "no recuperado", con su motivo en
    04_fulltext/retrieval.json, y no llega a extracción.
    """
    outcomes, fulltexts = _retrieve(run, passed_ta, fetch_fn)
    ft_cfg = run.protocol.provider_for("screening_ft")
    ft_provider = build_provider(ft_cfg)
    ft_model = f"{ft_cfg.provider}:{ft_cfg.model}"
    ft_decisions: list[ScreeningDecision] = []
    for record in passed_ta:
        if not outcomes[record.record_id].available:
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
        decision, meta = screening_ft_agent.screen_fulltext(
            ft_provider,
            ft_model,
            question=run.question,
            criteria=run.criteria,
            record=record,
            text=fulltexts[record.record_id],
            temperature=ft_cfg.temperature,
            seed=ft_cfg.seed,
        )
        decision.fulltext_status = "retrieved"
        decision.final_label = decision.human_label or decision.ensemble_label
        ft_decisions.append(decision)
        run.ctx.record_meta(meta, stage="screening_ft", record_id=record.record_id)
    run.ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])
    not_retrieved = sum(1 for d in ft_decisions if d.fulltext_status == "not_retrieved")
    return _FullTextStage(ft_decisions, fulltexts, not_retrieved)
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py tests/test_pipeline_fake.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 444 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/pipeline.py tests/test_reanudacion.py
git commit -m "feat(pipeline): diario de la recuperación y caché del texto completo" -m "Cada intento de recuperación va a 04_fulltext/retrieval.jsonl y cada texto recuperado a 04_fulltext/texts/<sha256(id)[:16]>.txt (ningún record_id como nombre de fichero). Al reanudar no se descarga nada otra vez y un texto en caché que no coincide con su hash da JournalError. retrieval.json gana text_file. Spec 2026-10-04 §4.2 y §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Diario del cribado a texto completo

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (imports l.63-64; función nueva antes de `_fulltext` l.474; cabecera y bucle de `_fulltext` l.482-512)
- Test: `tests/test_reanudacion.py` (helper y test nuevos al final)

**Interfaces:**
- Consumes: `journaled` (Tarea 4); `_retrieve` (Tarea 12); `LLMProvider` (`revisia/llm/base.py`), `ProviderConfig` (`revisia/llm/registry.py`).
- Produces: `04_fulltext/journal.jsonl` (`stage="screening_ft"`, una `LLMCall` por línea; `output` = `ScreeningDecision` con `fulltext_status="retrieved"` y sin campos humanos). `inputs` = lo de T/A con el proveedor FT (`"miembros": [[ft_model, temperature, seed]]`) + `"text_sha256"`. Los no recuperados no pasan por el diario (no hay llamada). `_screen_ft_one(run, provider, model_name, cfg, record, text) -> tuple[ScreeningDecision, list[RunMeta]]`.

- [ ] **Step 1: Test que falla** — añadir al final de `tests/test_reanudacion.py`:

```python


def _llamadas(proveedor: ScriptedProvider, marca: str) -> int:
    """Llamadas del proveedor cuyo prompt contiene ``marca`` (identifica la etapa)."""
    return sum(marca in p for p in proveedor.prompts)


def test_cribado_ft_en_diario_no_se_repite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        parar_en="screening_ft",
    )
    assert _llamadas(proveedor, "TEXTO COMPLETO") == 2

    run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)

    assert _llamadas(proveedor, "TEXTO COMPLETO") == 2
    entradas = _diario(ctx, "04_fulltext/journal.jsonl")
    assert [(e.record_id, len(e.metas)) for e in entradas] == [("rec-1", 1), ("rec-2", 1)]
    assert all(e.output["fulltext_status"] == "retrieved" for e in entradas)
    assert all(e.output["final_label"] is None for e in entradas)  # sin campos humanos
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py::test_cribado_ft_en_diario_no_se_repite -v`
Expected: FAIL con `assert 4 == 2`: al reanudar se vuelve a cribar a texto completo.

- [ ] **Step 3: Implementar.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.llm.preflight import PreflightError, preflight
from revisia.llm.registry import build_provider
```

por

```python
from revisia.llm.base import LLMProvider
from revisia.llm.preflight import PreflightError, preflight
from revisia.llm.registry import ProviderConfig, build_provider
```

justo antes de `_fulltext`, sustituir

```python
def _fulltext(run: _Run, passed_ta: list[SearchRecord], fetch_fn: FetchFn | None) -> _FullTextStage:
```

por

```python
def _screen_ft_one(
    run: _Run,
    provider: LLMProvider,
    model_name: str,
    cfg: ProviderConfig,
    record: SearchRecord,
    text: str,
) -> tuple[ScreeningDecision, list[RunMeta]]:
    """Cribado a texto completo de un registro recuperado (``compute`` de su diario)."""
    decision, meta = screening_ft_agent.screen_fulltext(
        provider,
        model_name,
        question=run.question,
        criteria=run.criteria,
        record=record,
        text=text,
        temperature=cfg.temperature,
        seed=cfg.seed,
    )
    decision.fulltext_status = "retrieved"
    return decision, [meta]


def _fulltext(run: _Run, passed_ta: list[SearchRecord], fetch_fn: FetchFn | None) -> _FullTextStage:
```

en `_fulltext`, sustituir

```python
    outcomes, fulltexts = _retrieve(run, passed_ta, fetch_fn)
    ft_cfg = run.protocol.provider_for("screening_ft")
    ft_provider = build_provider(ft_cfg)
    ft_model = f"{ft_cfg.provider}:{ft_cfg.model}"
    ft_decisions: list[ScreeningDecision] = []
```

por

```python
    outcomes, fulltexts = _retrieve(run, passed_ta, fetch_fn)
    ft_cfg = run.protocol.provider_for("screening_ft")
    ft_provider = build_provider(ft_cfg)
    ft_model = f"{ft_cfg.provider}:{ft_cfg.model}"
    journal = StageJournal(run.ctx, "screening_ft")
    ft_decisions: list[ScreeningDecision] = []
```

y

```python
        decision, meta = screening_ft_agent.screen_fulltext(
            ft_provider,
            ft_model,
            question=run.question,
            criteria=run.criteria,
            record=record,
            text=fulltexts[record.record_id],
            temperature=ft_cfg.temperature,
            seed=ft_cfg.seed,
        )
        decision.fulltext_status = "retrieved"
        decision.final_label = decision.human_label or decision.ensemble_label
        ft_decisions.append(decision)
        run.ctx.record_meta(meta, stage="screening_ft", record_id=record.record_id)
```

por

```python
        decision = journaled(
            journal,
            record_id=record.record_id,
            inputs={
                "title": record.title,
                "abstract": record.abstract,
                "question": run.question,
                "criteria": run.criteria,
                "miembros": [[ft_model, ft_cfg.temperature, ft_cfg.seed]],
                "text_sha256": outcomes[record.record_id].text_sha256,
            },
            model=ScreeningDecision,
            compute=partial(
                _screen_ft_one,
                run,
                ft_provider,
                ft_model,
                ft_cfg,
                record,
                fulltexts[record.record_id],
            ),
            run_ctx=run.ctx,
        )
        decision.final_label = decision.human_label or decision.ensemble_label
        ft_decisions.append(decision)
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py tests/test_pipeline_fake.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 445 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/pipeline.py tests/test_reanudacion.py
git commit -m "feat(pipeline): diario del cribado a texto completo" -m "Cada registro recuperado se criba una sola vez: su decisión va a 04_fulltext/journal.jsonl con su llamada, y input_sha256 incluye el hash del texto. Spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Diarios de la extracción y del 2.º extractor

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (`_extract` l.554-596, con dos funciones nuevas antes; llamada en `_run_stages` l.968)
- Test: `tests/test_reanudacion.py` (test nuevo al final)

**Interfaces:**
- Consumes: `journaled` (Tarea 4).
- Produces: `05_extraction/journal.jsonl` (`stage="extraccion"`) y `05_extraction/journal_2.jsonl` (`stage="extraccion_2"`), una `LLMCall` por línea, `output` = `ExtractionRecord`. `_extraction_inputs(run, record, fulltexts, cfg) -> dict` = `{"record_id", "text_sha256" (o None), "form_fields", "proveedor": [f"{provider}:{model}", temperature, seed]}`; `_extract_one(run, provider, cfg, record) -> tuple[ExtractionRecord, list[RunMeta]]`; `_extract(run, included, fulltexts)` (gana `fulltexts`).

- [ ] **Step 1: Test que falla** — añadir al final de `tests/test_reanudacion.py`:

```python


def test_extraccion_y_segundo_extractor_en_diario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)  # el demo declara un 2.º extractor
    ctx = RunContext(protocol.slug, tmp_path, "T")
    correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        parar_en="extraccion",
    )
    assert _llamadas(proveedor, "extractor de datos") == 3  # 2 + 1 de la doble extracción

    run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)

    assert _llamadas(proveedor, "extractor de datos") == 3
    primero = _diario(ctx, "05_extraction/journal.jsonl")
    segundo = _diario(ctx, "05_extraction/journal_2.jsonl")
    assert [e.record_id for e in primero] == ["rec-1", "rec-2"]
    assert len(segundo) == 1
    assert {(m.stage, len(e.metas)) for e in segundo for m in e.metas} == {("extraccion_2", 1)}
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py::test_extraccion_y_segundo_extractor_en_diario -v`
Expected: FAIL con `assert 6 == 3`.

- [ ] **Step 3: Implementar.** En `revisia/orchestration/pipeline.py`, sustituir la cabecera de `_extract` y su primer bucle

```python
def _extract(
    run: _Run, included: list[SearchRecord]
) -> tuple[dict[str, ExtractionRecord], ExtractionAgreement | None]:
    """Extracción de datos (A0) y, si hay 2.º extractor, doble extracción (≥20 %).

    El 2.º extractor es el primero de ``ensemble_llm['extraccion']``; el acuerdo
    entre extractores va a ``05_extraction/agreement.json`` (§6).
    """
    extract_cfg = run.protocol.provider_for("extraccion")
    extract_provider = build_provider(extract_cfg)
    extractions: dict[str, ExtractionRecord] = {}
    for record in included:
        extraction, meta = extraccion_agent.extract_record(
            extract_provider,
            record=record,
            form_fields=run.form_fields,
            temperature=extract_cfg.temperature,
            seed=extract_cfg.seed,
        )
        extractions[record.record_id] = extraction
        run.ctx.record_meta(meta, stage="extraccion", record_id=record.record_id)
    run.ctx.write_json(
```

por

```python
def _extraction_inputs(
    run: _Run, record: SearchRecord, fulltexts: dict[str, str], cfg: ProviderConfig
) -> dict:
    """``inputs`` del diario de extracción (spec §7): registro, texto, formulario y proveedor."""
    text = fulltexts.get(record.record_id)
    return {
        "record_id": record.record_id,
        "text_sha256": sha256_text(text) if text is not None else None,
        "form_fields": run.form_fields,
        "proveedor": [f"{cfg.provider}:{cfg.model}", cfg.temperature, cfg.seed],
    }


def _extract_one(
    run: _Run, provider: LLMProvider, cfg: ProviderConfig, record: SearchRecord
) -> tuple[ExtractionRecord, list[RunMeta]]:
    """Extracción de un estudio (``compute`` de su diario)."""
    extraction, meta = extraccion_agent.extract_record(
        provider,
        record=record,
        form_fields=run.form_fields,
        temperature=cfg.temperature,
        seed=cfg.seed,
    )
    return extraction, [meta]


def _extract(
    run: _Run, included: list[SearchRecord], fulltexts: dict[str, str]
) -> tuple[dict[str, ExtractionRecord], ExtractionAgreement | None]:
    """Extracción de datos (A0) y, si hay 2.º extractor, doble extracción (≥20 %).

    El 2.º extractor es el primero de ``ensemble_llm['extraccion']``; el acuerdo
    entre extractores va a ``05_extraction/agreement.json`` (§6). Cada extractor
    tiene su diario (``05_extraction/journal.jsonl`` y ``journal_2.jsonl``).
    """
    extract_cfg = run.protocol.provider_for("extraccion")
    extract_provider = build_provider(extract_cfg)
    journal = StageJournal(run.ctx, "extraccion")
    extractions: dict[str, ExtractionRecord] = {}
    for record in included:
        extractions[record.record_id] = journaled(
            journal,
            record_id=record.record_id,
            inputs=_extraction_inputs(run, record, fulltexts, extract_cfg),
            model=ExtractionRecord,
            compute=partial(_extract_one, run, extract_provider, extract_cfg, record),
            run_ctx=run.ctx,
        )
    run.ctx.write_json(
```

sustituir el bucle del 2.º extractor

```python
        second_provider = build_provider(second_cfg)
        secondary: dict[str, ExtractionRecord] = {}
        for record in subset:
            extraction2, meta2 = extraccion_agent.extract_record(
                second_provider,
                record=record,
                form_fields=run.form_fields,
                temperature=second_cfg.temperature,
                seed=second_cfg.seed,
            )
            secondary[record.record_id] = extraction2
            run.ctx.record_meta(meta2, stage="extraccion_2", record_id=record.record_id)
```

por

```python
        second_provider = build_provider(second_cfg)
        journal_2 = StageJournal(run.ctx, "extraccion_2")
        secondary: dict[str, ExtractionRecord] = {}
        for record in subset:
            secondary[record.record_id] = journaled(
                journal_2,
                record_id=record.record_id,
                inputs=_extraction_inputs(run, record, fulltexts, second_cfg),
                model=ExtractionRecord,
                compute=partial(_extract_one, run, second_provider, second_cfg, record),
                run_ctx=run.ctx,
            )
```

y en `_run_stages`, sustituir

```python
    extractions, extraction_agreement = _extract(run, included)
```

por

```python
    extractions, extraction_agreement = _extract(run, included, ft.texts)
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py tests/test_pipeline_fake.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 446 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/pipeline.py tests/test_reanudacion.py
git commit -m "feat(pipeline): diarios de la extracción y del segundo extractor" -m "Cada extracción va a 05_extraction/journal.jsonl y cada una del segundo extractor a journal_2.jsonl, con input_sha256 sobre el registro, el hash del texto, el formulario y el proveedor. Spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Diario del riesgo de sesgo

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (import l.85; función nueva antes de `_assess_rob` l.631; cuerpo de `_assess_rob` l.637-652)
- Test: `tests/test_reanudacion.py` (test nuevo al final)

**Interfaces:**
- Consumes: `journaled`, `_extraction_inputs` (Tareas 4 y 14); `canonical_sha256`.
- Produces: `07_rob/journal.jsonl` (`stage="rob"`), `output` = `RoBAssessment`; `inputs` = `_extraction_inputs(...)` con el proveedor de RoB + `"extraction_sha256"` (`canonical_sha256` de la extracción del estudio) + `"tool"`. `_rob_one(run, provider, cfg, record, extraction, text) -> tuple[RoBAssessment, list[RunMeta]]`.

- [ ] **Step 1: Test que falla** — añadir al final de `tests/test_reanudacion.py`:

```python


def test_rob_en_diario_no_se_repite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    correr_hasta(
        protocol, EXAMPLE, ctx, search_fn=_busqueda, fetch_fn=fetch_disponible, parar_en="rob"
    )
    assert _llamadas(proveedor, "RIESGO DE SESGO") == 2

    run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)

    assert _llamadas(proveedor, "RIESGO DE SESGO") == 2
    entradas = _diario(ctx, "07_rob/journal.jsonl")
    assert [(e.record_id, len(e.metas)) for e in entradas] == [("rec-1", 1), ("rec-2", 1)]
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py::test_rob_en_diario_no_se_repite -v`
Expected: FAIL con `assert 4 == 2`.

- [ ] **Step 3: Implementar.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.provenance.runmeta import RunMeta, sha256_text, utc_now_iso
```

por

```python
from revisia.provenance.runmeta import RunMeta, canonical_sha256, sha256_text, utc_now_iso
```

justo antes de `_assess_rob`, sustituir

```python
def _assess_rob(
```

por

```python
def _rob_one(
    run: _Run,
    provider: LLMProvider,
    cfg: ProviderConfig,
    record: SearchRecord,
    extraction: ExtractionRecord | None,
    text: str | None,
) -> tuple[RoBAssessment, list[RunMeta]]:
    """Riesgo de sesgo de un estudio (``compute`` de su diario)."""
    assessment, meta = rob_agent.assess_rob(
        provider,
        tool=run.protocol.rob_tool,
        record=record,
        extraction=extraction,
        text=text,
        temperature=cfg.temperature,
        seed=cfg.seed,
    )
    return assessment, [meta]


def _assess_rob(
```

y en `_assess_rob`, sustituir

```python
    """Riesgo de sesgo (A0) con la herramienta del protocolo."""
    rob_cfg = run.protocol.provider_for("rob")
    rob_provider = build_provider(rob_cfg)
    assessments: dict[str, RoBAssessment] = {}
    for record in included:
        assessment, meta = rob_agent.assess_rob(
            rob_provider,
            tool=run.protocol.rob_tool,
            record=record,
            extraction=extractions.get(record.record_id),
            text=fulltexts.get(record.record_id),
            temperature=rob_cfg.temperature,
            seed=rob_cfg.seed,
        )
        assessments[record.record_id] = assessment
        run.ctx.record_meta(meta, stage="rob", record_id=record.record_id)
```

por

```python
    """Riesgo de sesgo (A0) con la herramienta del protocolo, con diario (``07_rob/``).

    La entrada del diario cubre lo de la extracción más el hash de la extracción
    del estudio y la herramienta (spec §7).
    """
    rob_cfg = run.protocol.provider_for("rob")
    rob_provider = build_provider(rob_cfg)
    journal = StageJournal(run.ctx, "rob")
    assessments: dict[str, RoBAssessment] = {}
    for record in included:
        extraction = extractions.get(record.record_id)
        extraction_sha256 = (
            canonical_sha256(extraction.model_dump(mode="json")) if extraction is not None else None
        )
        assessments[record.record_id] = journaled(
            journal,
            record_id=record.record_id,
            inputs={
                **_extraction_inputs(run, record, fulltexts, rob_cfg),
                "extraction_sha256": extraction_sha256,
                "tool": run.protocol.rob_tool,
            },
            model=RoBAssessment,
            compute=partial(
                _rob_one,
                run,
                rob_provider,
                rob_cfg,
                record,
                extraction,
                fulltexts.get(record.record_id),
            ),
            run_ctx=run.ctx,
        )
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 447 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/pipeline.py tests/test_reanudacion.py
git commit -m "feat(pipeline): diario del riesgo de sesgo" -m "Cada evaluación va a 07_rob/journal.jsonl; input_sha256 cubre lo de la extracción más el hash de la extracción del estudio y la herramienta. Spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Diarios de la síntesis y de la verificación; el juez de grounding registra sus llamadas

Sin estos dos diarios el gate final no convergería al reanudar: la síntesis volvería a llamar al LLM, cambiaría la narrativa y con ella el hash de la solicitud de `reporte` (hallazgo 1 del spec, §2).

**Files:**
- Modify: `revisia/rag/grounding.py` (import l.17-21; firma y docstring de `make_provider_judge` l.45-53; l.69-70)
- Modify: `revisia/orchestration/pipeline.py` (import l.26-28; `_synthesize_and_verify` completo l.718-760, con tres definiciones nuevas antes)
- Modify: `tests/fakes.py` (docstring de `ScriptedProvider` l.62-63; `__init__` l.73-75; `complete` l.112-113)
- Test: `tests/test_reanudacion.py` (imports l.4-6, l.8-10, l.13-14 y l.22-23; helpers y cuatro tests nuevos al final)

**Interfaces:**
- Consumes: `journaled` (Tarea 4); `GATED_STAGES`, `LLMCall` (PR-0); `correr_hasta`, `responder_gate` (Tarea 9).
- Produces:
  - `make_provider_judge(provider, model_name: str = "", *, temperature: float = 0.0, on_meta: Callable[[RunMeta], None] | None = None) -> GroundingJudge`: cada juicio entrega su `RunMeta` a `on_meta` (antes se descartaba).
  - `06_synthesis/journal.jsonl`: una línea `stage="sintesis"`, `record_id="sintesis"`, `output={"narrative": …}`, una `LLMCall`; `inputs` = `{"incluidos": [[id, título], …], "extracciones_sha256", "proveedor"}`.
  - `06_synthesis/verification.jsonl`: una línea `stage="verificacion"`, `record_id="verificacion"`, `output` = `VerificationReport`; `metas` = las llamadas del juez en modo `agent` (una por cita con fuente; 0 en `embedder`/`existence`); `inputs` = `{"narrativa_sha256", "fuentes_sha256", "modo"}`.
  - Privadas: `class _Narrative(BaseModel)` (`narrative: str`), `_synthesize_one(...)`, `_verify_one(...)`.
  - `tests/fakes.py`: `ScriptedProvider(..., sintesis: str | None = None)` (aditivo): con `sintesis`, `complete` devuelve ese texto (para tener citas `[id]` que verificar).

- [ ] **Step 1: Tests que fallan.** En `tests/fakes.py`, sustituir

```python
        prompts: prompt de cada llamada, en orden (para afirmar qué se cribó).
    """
```

por

```python
        prompts: prompt de cada llamada, en orden (para afirmar qué se cribó).
        sintesis: texto que devuelve ``complete`` (la síntesis narrativa); por
            defecto, uno sin citas. Con citas ``[id]`` el verificador tiene algo
            que comprobar (y con un id que no está en el corpus, marca).
    """
```

sustituir

```python
        criterio_exclusion: str = "fuera de alcance",
    ) -> None:
        self.model = model
```

por

```python
        criterio_exclusion: str = "fuera de alcance",
        sintesis: str | None = None,
    ) -> None:
        self.model = model
        self.sintesis = sintesis
```

y

```python
        # Sin tokens "[...]": el verificador no debe confundirlos con citas.
        text = "Síntesis de prueba (proveedor con guion · sin contenido real)."
```

por

```python
        # Por defecto sin tokens "[...]": el verificador no debe confundirlos con citas.
        text = self.sintesis or "Síntesis de prueba (proveedor con guion · sin contenido real)."
```

En `tests/test_reanudacion.py`, sustituir

```python
from __future__ import annotations

from pathlib import Path
```

por

```python
from __future__ import annotations

import shutil
from pathlib import Path
```

sustituir

```python
import pytest
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import correr_hasta
```

por

```python
import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import correr_hasta, responder_gate
```

sustituir

```python
from revisia.config import load_protocol
from revisia.llm.preflight import PreflightError
```

por

```python
from revisia.config import load_protocol
from revisia.llm.base import LLMRequest, LLMResponse
from revisia.llm.preflight import PreflightError
```

sustituir

```python
from revisia.schemas.artifacts import JournalEntry
from revisia.schemas.records import SearchRecord
```

por

```python
from revisia.schemas.artifacts import GATED_STAGES, JournalEntry, LLMCall
from revisia.schemas.records import SearchRecord
```

y añadir al final del fichero:

```python


def _proto_con(tmp_path: Path, **cambios) -> Path:
    """Copia del demo con cambios en protocol.yml."""
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw.update(cambios)
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), "utf-8")
    return proto


def _llm_calls(ctx: RunContext) -> list[LLMCall]:
    lineas = ctx.llm_calls_path.read_text(encoding="utf-8").splitlines()
    return [LLMCall.model_validate_json(x) for x in lineas]


def test_llamadas_del_juez_quedan_en_llm_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proveedor = ScriptedProvider(sintesis="La IA reduce el cribado [rec-1] y la carga [rec-2].")
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    proto = _proto_con(tmp_path, grounding="agent")
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(
        protocol, proto, ctx, auto_approve=True, search_fn=_busqueda, fetch_fn=fetch_disponible
    )

    juez = [c for c in _llm_calls(ctx) if c.stage == "verificacion"]
    assert [c.record_id for c in juez] == ["verificacion", "verificacion"]  # una por cita
    (entrada,) = _diario(ctx, "06_synthesis/verification.jsonl")
    assert entrada.metas == juez
    assert len(entrada.output["checks"]) == 2


class _SintesisCambiante(ScriptedProvider):
    """Cada síntesis sale distinta: sin diario, el gate final no convergería."""

    def complete(self, req: LLMRequest) -> LLMResponse:
        resp = super().complete(req)
        return LLMResponse(text=f"{resp.text} (versión {self.calls})", meta=resp.meta)


def test_gate_final_converge_tras_reanudar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = _SintesisCambiante()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    pausa = correr_hasta(
        protocol, EXAMPLE, ctx, search_fn=_busqueda, fetch_fn=fetch_disponible, parar_en="reporte"
    )
    assert (pausa.status, pausa.stage) == ("paused", "reporte")
    solicitud = (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")

    otra = run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)
    assert (otra.status, otra.stage) == ("paused", "reporte")
    assert (ctx.run_dir / "reporte" / "review_request.yml").read_text("utf-8") == solicitud

    responder_gate(ctx.run_dir, "reporte")
    final = run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)
    assert final.status == "completed"
    assert _llamadas(proveedor, "SWiM") == 1  # la síntesis se pidió una sola vez


def test_reanudar_no_repite_llamadas_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    primera = correr_hasta(protocol, EXAMPLE, ctx, search_fn=_busqueda, fetch_fn=fetch_disponible)
    assert primera.status == "completed"
    llamadas, lineas = proveedor.calls, len(_llm_calls(ctx))

    segunda = run_pipeline(
        protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible
    )

    assert segunda.status == "completed"
    assert proveedor.calls == llamadas  # 0 llamadas en la segunda pasada
    assert len(_llm_calls(ctx)) == lineas
    assert segunda.counts == primera.counts


def test_payloads_estables_entre_reanudaciones_y_sin_rutas_absolutas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proveedor = _SintesisCambiante()  # sin diario, cada invocación cambiaría el reporte
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    correr_hasta(protocol, EXAMPLE, ctx, search_fn=_busqueda, fetch_fn=fetch_disponible)

    def solicitudes() -> dict[str, str]:
        return {
            g: (ctx.run_dir / g / "review_request.yml").read_text(encoding="utf-8")
            for g in GATED_STAGES
        }

    antes = solicitudes()
    run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)
    assert solicitudes() == antes  # los cinco gates, byte a byte
    for texto in antes.values():
        assert str(tmp_path) not in texto
        assert tmp_path.as_posix() not in texto
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py tests/test_fakes.py -v`
Expected: FAIL `test_llamadas_del_juez_quedan_en_llm_calls` (ninguna llamada `verificacion` en `llm_calls.jsonl`), `test_gate_final_converge_tras_reanudar` (la solicitud de `reporte` cambia al reanudar), `test_reanudar_no_repite_llamadas_llm` (la segunda pasada vuelve a sintetizar) y `test_payloads_estables_entre_reanudaciones_y_sin_rutas_absolutas` (`correr_hasta` no termina: el hash de `reporte` cambia en cada vuelta). `tests/test_fakes.py` sigue en verde.

- [ ] **Step 3: El juez entrega sus llamadas.** En `revisia/rag/grounding.py`, sustituir

```python
from collections.abc import Callable

from pydantic import BaseModel, Field

from revisia.llm.base import LLMProvider, LLMRequest
```

por

```python
from collections.abc import Callable

from pydantic import BaseModel, Field

from revisia.llm.base import LLMProvider, LLMRequest
from revisia.provenance.runmeta import RunMeta
```

sustituir

```python
def make_provider_judge(
    provider: LLMProvider, model_name: str = "", *, temperature: float = 0.0
) -> GroundingJudge:
    """Construye un juez de grounding respaldado por un proveedor LLM.

    Args:
        provider: cualquier ``LLMProvider`` (``agent`` para costo cero en sesión).
        model_name: etiqueta del modelo (informativa).
        temperature: temperatura del juicio (0.0 = determinista en lo posible).
```

por

```python
def make_provider_judge(
    provider: LLMProvider,
    model_name: str = "",
    *,
    temperature: float = 0.0,
    on_meta: Callable[[RunMeta], None] | None = None,
) -> GroundingJudge:
    """Construye un juez de grounding respaldado por un proveedor LLM.

    Args:
        provider: cualquier ``LLMProvider`` (``agent`` para costo cero en sesión).
        model_name: etiqueta del modelo (informativa).
        temperature: temperatura del juicio (0.0 = determinista en lo posible).
        on_meta: recibe el ``RunMeta`` de cada llamada del juez. El pipeline lo
            usa para que lleguen a ``llm_calls.jsonl``; antes se descartaban y
            el juez hacía llamadas reales sin rastro (Ola 1, spec §7).
```

y

```python
        verdict, _meta = provider.structured(req, GroundingVerdict)
        return verdict
```

por

```python
        verdict, meta = provider.structured(req, GroundingVerdict)
        if on_meta is not None:
            on_meta(meta)
        return verdict
```

- [ ] **Step 4: Síntesis y verificación con diario.** En `revisia/orchestration/pipeline.py`, sustituir

```python
import yaml

from revisia.agents import _http
```

por

```python
import yaml
from pydantic import BaseModel

from revisia.agents import _http
```

y sustituir `_synthesize_and_verify` completo

```python
def _synthesize_and_verify(
    run: _Run,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
    fulltexts: dict[str, str],
    embedder: Embedder | None,
) -> tuple[str, VerificationReport]:
    """Síntesis narrativa (A1) y verificador anti-alucinación (grounding).

    Modo según ``protocol.grounding``: "agent" (un modelo juzga; cruza idiomas,
    sin vectores), "existence" (solo id en corpus) o "embedder" (coseno léxico).
    """
    synth_cfg = run.protocol.provider_for("sintesis")
    synth_provider = build_provider(synth_cfg)
    narrative, meta = reporte_agent.synthesize_narrative(
        synth_provider,
        question=run.question,
        included=included,
        extractions=extractions,
        temperature=synth_cfg.temperature,
        seed=synth_cfg.seed,
    )
    run.ctx.record_meta(meta, stage="sintesis", record_id="sintesis")

    sources = {r.record_id: (fulltexts.get(r.record_id) or r.abstract or "") for r in included}
    verify_kwargs: dict = {"sources": sources}
    grounding_mode = getattr(run.protocol, "grounding", "embedder")
    if grounding_mode == "agent":
        from revisia.rag.grounding import make_provider_judge

        verify_kwargs["judge"] = make_provider_judge(
            synth_provider, f"{synth_cfg.provider}:{synth_cfg.model}", temperature=0.0
        )
    elif grounding_mode != "existence":  # "embedder" (default)
        verify_kwargs["embedder"] = embedder or HashEmbedder()
    verification = verificador_agent.verify_narrative(
        "reporte",
        narrative,
        [r.record_id for r in included],
        **verify_kwargs,
    )
    run.ctx.write_json("06_synthesis/verification.json", verification.model_dump())
    return narrative, verification
```

por

```python
class _Narrative(BaseModel):
    """Salida del diario de síntesis: ``{narrative}`` (spec §4.3)."""

    narrative: str


def _synthesize_one(
    run: _Run,
    provider: LLMProvider,
    cfg: ProviderConfig,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
) -> tuple[_Narrative, list[RunMeta]]:
    """Síntesis narrativa (``compute`` del diario de síntesis)."""
    narrative, meta = reporte_agent.synthesize_narrative(
        provider,
        question=run.question,
        included=included,
        extractions=extractions,
        temperature=cfg.temperature,
        seed=cfg.seed,
    )
    return _Narrative(narrative=narrative), [meta]


def _verify_one(
    run: _Run,
    narrative: str,
    included: list[SearchRecord],
    sources: dict[str, str],
    *,
    provider: LLMProvider,
    cfg: ProviderConfig,
    embedder: Embedder | None,
) -> tuple[VerificationReport, list[RunMeta]]:
    """Verificación anti-alucinación (``compute`` de su diario).

    En modo ``agent`` cada juicio es una llamada al LLM: ``on_meta`` las recoge
    para que el diario y ``llm_calls.jsonl`` las registren.
    """
    metas: list[RunMeta] = []
    verify_kwargs: dict = {"sources": sources}
    grounding_mode = getattr(run.protocol, "grounding", "embedder")
    if grounding_mode == "agent":
        from revisia.rag.grounding import make_provider_judge

        verify_kwargs["judge"] = make_provider_judge(
            provider,
            f"{cfg.provider}:{cfg.model}",
            temperature=0.0,
            on_meta=metas.append,
        )
    elif grounding_mode != "existence":  # "embedder" (default)
        verify_kwargs["embedder"] = embedder or HashEmbedder()
    verification = verificador_agent.verify_narrative(
        "reporte",
        narrative,
        [r.record_id for r in included],
        **verify_kwargs,
    )
    return verification, metas


def _synthesize_and_verify(
    run: _Run,
    included: list[SearchRecord],
    extractions: dict[str, ExtractionRecord],
    fulltexts: dict[str, str],
    embedder: Embedder | None,
) -> tuple[str, VerificationReport]:
    """Síntesis narrativa (A1) y verificador anti-alucinación (grounding).

    Modo según ``protocol.grounding``: "agent" (un modelo juzga; cruza idiomas,
    sin vectores), "existence" (solo id en corpus) o "embedder" (coseno léxico).
    Las dos van al diario (``record_id`` ``"sintesis"`` y ``"verificacion"``):
    sin él, reanudar volvería a llamar al LLM, cambiaría la narrativa y con ella
    la solicitud del gate final, que no convergería nunca (spec §2, hallazgo 1).
    """
    synth_cfg = run.protocol.provider_for("sintesis")
    synth_provider = build_provider(synth_cfg)
    narrative = journaled(
        StageJournal(run.ctx, "sintesis"),
        record_id="sintesis",
        inputs={
            "incluidos": [[r.record_id, r.title] for r in included],
            "extracciones_sha256": canonical_sha256(
                {k: v.model_dump(mode="json") for k, v in extractions.items()}
            ),
            "proveedor": [
                f"{synth_cfg.provider}:{synth_cfg.model}",
                synth_cfg.temperature,
                synth_cfg.seed,
            ],
        },
        model=_Narrative,
        compute=partial(_synthesize_one, run, synth_provider, synth_cfg, included, extractions),
        run_ctx=run.ctx,
    ).narrative

    sources = {r.record_id: (fulltexts.get(r.record_id) or r.abstract or "") for r in included}
    verification = journaled(
        StageJournal(run.ctx, "verificacion"),
        record_id="verificacion",
        inputs={
            "narrativa_sha256": sha256_text(narrative),
            "fuentes_sha256": canonical_sha256(sources),
            "modo": getattr(run.protocol, "grounding", "embedder"),
        },
        model=VerificationReport,
        compute=partial(
            _verify_one,
            run,
            narrative,
            included,
            sources,
            provider=synth_provider,
            cfg=synth_cfg,
            embedder=embedder,
        ),
        run_ctx=run.ctx,
    )
    run.ctx.write_json("06_synthesis/verification.json", verification.model_dump())
    return narrative, verification
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_reanudacion.py tests/test_grounding.py tests/test_pipeline_fake.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 451 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/rag/grounding.py revisia/orchestration/pipeline.py tests/fakes.py tests/test_reanudacion.py
git commit -m "feat(pipeline): diarios de síntesis y verificación; el juez registra sus llamadas" -m "La narrativa va a 06_synthesis/journal.jsonl y el informe de verificación a 06_synthesis/verification.jsonl: al reanudar no se vuelve a sintetizar, la solicitud del gate final no cambia y el gate converge (hallazgo 1 del spec). make_provider_judge gana on_meta y sus llamadas llegan a llm_calls.jsonl con stage verificacion. Con esto, reanudar una corrida completa hace 0 llamadas. ScriptedProvider acepta sintesis= para tener citas que verificar. Spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: `revisia run --resume`, códigos de salida y `brain.has_run`

**Files:**
- Modify: `revisia/cli.py` (docstring l.6-8; imports l.12-15; `_cmd_run` l.157-198 con dos definiciones nuevas antes; parser de `run` l.389-393; cola de `main` l.495-529)
- Modify: `revisia/memory/brain.py` (método nuevo tras `_events_for`, l.95-96)
- Test: `tests/test_cli_reanudacion.py` (nuevo)

**Interfaces:**
- Consumes: `resume_review`, `run_review` (Tarea 8); `read_run_info` (Tarea 5); `RunInterrupted`, `RunDirExistsError`, `LegacyRunError` (Tareas 3 y 5); `ProtocolMismatchError` (Tarea 5); `JournalError` (Tarea 2); `PreflightError` (PR-A); `DecisionFileError`.
- Produces:
  - Parser de `run`: `protocol_dir` con `nargs="?"`; `--resume RUN_DIR`; `--max` con default `None` (`DEFAULT_MAX_RESULTS = 50` en corrida nueva; al reanudar manda `run.json` y se avisa si se pasa otro). `validate` no cambia.
  - `revisia run --resume <run_dir> [<protocolo>]`: sin preflight propio (lo corre `run_pipeline` con `context="resume"`); si se pasa la carpeta del protocolo, debe existir y se compara su huella. Aviso si la corrida empezó con `--mailto` y la reanudación no lo trae (`mailto_set` está en la huella de cada recuperación). `revisia run` sin protocolo ni `--resume` → rc 2.
  - `_run_guarded(command: Callable[[], int]) -> int`: `RunInterrupted` → rc 3 con `error: corrida interrumpida… Reanuda con: revisia run --resume <run_dir>`; `PreflightError` → rc 2 (imprime el informe); `DecisionFileError`, `ProtocolMismatchError`, `JournalError`, `LegacyRunError`, `RunDirExistsError`, `FileNotFoundError` → rc 2; `KeyboardInterrupt` → 130. `paused` sigue saliendo con 0 (D14) e imprime `  Reanuda con: revisia run --resume <run_dir>`.
  - `ResearchBrain.has_run(slug: str, timestamp: str) -> bool`; con `--brain`, una corrida completada que ya está sedimentada no se registra dos veces.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_cli_reanudacion.py`:

```python
"""`revisia run --resume` y códigos de salida de una corrida (Ola 1, D3, D13 y D14;
spec 2026-10-04 §7)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fakes import fetch_disponible

from revisia import cli
from revisia.config import load_protocol
from revisia.llm import preflight as preflight_mod
from revisia.memory import ResearchBrain
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext, RunInterrupted
from revisia.orchestration.snapshot import read_run_info
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


@pytest.fixture(autouse=True)
def entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin .env real y con httpx "instalado" para el preflight del demo (M6)."""
    monkeypatch.setattr(cli, "_load_dotenv", lambda: None)
    monkeypatch.setattr(preflight_mod, "_default_find_spec", lambda _name: object())


def _busqueda(query: str, n: int) -> list[SearchRecord]:
    # Sin DOI, PMCID ni oa_url: al reanudar desde el CLI la recuperación no toca la red.
    return [
        SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex"),
        SearchRecord(record_id="rec-2", title="Active learning", source_db="OpenAlex"),
    ][:n]


def _corrida_en_pausa(tmp_path: Path, proto: Path = EXAMPLE) -> Path:
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    assert run_pipeline(protocol, proto, ctx, search_fn=_busqueda).status == "paused"
    return ctx.run_dir


def test_cli_run_resume_reanuda_la_misma_carpeta(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    run_dir = _corrida_en_pausa(tmp_path)

    rc = cli.main(["run", "--resume", str(run_dir), "--auto-approve", "--max", "99"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "COMPLETED" in out
    assert "--max 99 se ignora al reanudar" in out
    assert sorted(p.name for p in (tmp_path / "runs").iterdir()) == [run_dir.name]
    info = read_run_info(run_dir)
    assert (info.status, len(info.resumes), info.max_results) == ("completed", 1, 25)


def test_cli_resume_avisa_si_falta_mailto(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda, mailto="revisora@example.org")
    assert cli.main(["run", "--resume", str(ctx.run_dir)]) == 0
    assert "empezó con --mailto" in capsys.readouterr().out


def test_cli_pausa_dice_como_reanudar(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run_dir = _corrida_en_pausa(tmp_path)
    assert cli.main(["run", "--resume", str(run_dir)]) == 0
    assert f"Reanuda con: revisia run --resume {run_dir}" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("error", "rc", "esperado"),
    [
        ("interrupcion", 3, "revisia run --resume"),
        ("ctrl_c", 130, "Ctrl+C"),
    ],
)
def test_cli_interrupcion_rc_3_con_instrucciones(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    error: str,
    rc: int,
    esperado: str,
) -> None:
    run_dir = tmp_path / "runs" / "demo-mini-review-T"

    def _falla(*_a, **_k):
        if error == "ctrl_c":
            raise KeyboardInterrupt
        raise RunInterrupted(run_dir, "screening_ta", "RuntimeError: 429 Too Many Requests")

    monkeypatch.setattr("revisia.orchestration.flow.run_review", _falla)
    assert cli.main(["run", str(EXAMPLE)]) == rc
    err = capsys.readouterr().err
    assert esperado in err
    assert "Traceback" not in err
    if error == "interrupcion":
        assert f"revisia run --resume {run_dir}" in err


def test_resume_de_corrida_anterior_a_la_ola_1_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    antigua = tmp_path / "runs" / "demo-20260901-120000"
    (antigua / "03_screening").mkdir(parents=True)
    (antigua / "manifest.yml").write_text("slug: demo\n", encoding="utf-8")

    rc = cli.main(["run", "--resume", str(antigua)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "anterior a la Ola 1" in err
    assert "revisia run <protocolo>" in err


def test_resume_con_protocolo_modificado_sale_2(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    run_dir = _corrida_en_pausa(tmp_path, proto)
    criterios = proto / "inclusion_exclusion.yml"
    criterios.write_text(criterios.read_text(encoding="utf-8") + "\n# nuevo criterio\n", "utf-8")

    rc = cli.main(["run", str(proto), "--resume", str(run_dir)])

    err = capsys.readouterr().err
    assert rc == 2
    assert "no coinciden" in err and "inclusion_exclusion.yml" in err
    assert read_run_info(run_dir).resumes == []  # no se tocó la corrida


def test_cli_run_sin_protocolo_ni_resume_sale_2(capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["run"]) == 2
    assert "--resume" in capsys.readouterr().err


def test_brain_no_sedimenta_dos_veces(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=_busqueda, fetch_fn=fetch_disponible
    )
    cerebro = tmp_path / "cerebro"
    assert not ResearchBrain(cerebro).has_run("demo-mini-review", "T")

    for _ in range(2):  # reanudar una corrida completada no la duplica en el cerebro
        assert cli.main(["run", "--resume", str(ctx.run_dir), "--brain", str(cerebro)]) == 0

    eventos = (cerebro / "genome" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(e)["timestamp"] for e in eventos] == ["T"]
    assert ResearchBrain(cerebro).has_run("demo-mini-review", "T")
    assert "ya estaba sedimentada" in capsys.readouterr().out
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_cli_reanudacion.py -v`
Expected: FAIL `test_cli_run_resume_reanuda_la_misma_carpeta`, `test_cli_resume_avisa_si_falta_mailto` y `test_cli_pausa_dice_como_reanudar` (`SystemExit: 2`: `--resume` no existe) y `test_cli_interrupcion_rc_3_con_instrucciones[interrupcion-3-…]` (`RunInterrupted` llega como traceback). El caso `ctrl_c` corta la sesión de pytest con el `KeyboardInterrupt` sin capturar: es justo lo que arregla esta tarea.

- [ ] **Step 3: `has_run`.** En `revisia/memory/brain.py`, sustituir

```python
    def _events_for(self, slug: str) -> list[dict[str, Any]]:
        return [e for e in self._read_events() if e.get("slug") == slug]
```

por

```python
    def _events_for(self, slug: str) -> list[dict[str, Any]]:
        return [e for e in self._read_events() if e.get("slug") == slug]

    def has_run(self, slug: str, timestamp: str) -> bool:
        """¿Ya está sedimentada la corrida ``<slug>-<timestamp>``?

        Al reanudar una corrida ya completada, ``--brain`` la volvería a
        registrar como actualización de sí misma (Ola 1, spec §7).
        """
        return any(str(e.get("timestamp")) == timestamp for e in self._events_for(slug))
```

- [ ] **Step 4: El CLI.** En `revisia/cli.py`, sustituir

```python
  * ``revisia run <dir>`` — ejecuta el pipeline end-to-end (tracer bullet),
    con checkpoints humanos. Usa ``--auto-approve`` para correrlo sin pausas.
"""
```

por

```python
  * ``revisia run <dir>`` — ejecuta el pipeline end-to-end (tracer bullet),
    con checkpoints humanos. Usa ``--auto-approve`` para correrlo sin pausas.
  * ``revisia run --resume <run_dir>`` — reanuda una corrida tras una pausa o
    una interrupción, sin repetir búsqueda ni llamadas ya hechas (Ola 1, D3).

Códigos de salida de ``run``: 0 completada o en pausa, 1 rechazada, 2 error de
configuración o de decisión, 3 interrumpida (se reanuda), 130 Ctrl+C.
"""
```

sustituir

```python
import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path
```

por

```python
import argparse
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
```

sustituir el principio de `_cmd_run`

```python
def _cmd_run(args: argparse.Namespace) -> int:
    from revisia.orchestration.flow import run_review

    prior = None
    if args.brain:
        from revisia.memory import ResearchBrain

        prior = ResearchBrain(args.brain).recall(load_protocol(args.protocol_dir).slug)
        if prior:
            print(
                f"🧠 Memoria previa: {prior.n_runs} corrida(s), última {prior.last_timestamp}, "
                f"{len(prior.last_included_ids)} incluidos. Esta corrida se registrará como "
                "actualización (living review)."
            )
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    result = run_review(
        args.protocol_dir,
        timestamp=timestamp,
        runs_root=args.runs_root,
        max_results=args.max,
        auto_approve=args.auto_approve,
        mailto=args.mailto,
    )
    icon = {"completed": "✓", "paused": "⏸", "rejected": "✗"}.get(result.status, "•")
    print(f"\n{icon} {result.status.upper()} · {result.message}")
    if result.run_dir:
        print(f"  Corrida: {result.run_dir}")
```

por

```python
# `--max` por defecto en una corrida nueva (al reanudar manda run.json).
DEFAULT_MAX_RESULTS = 50


def _run_guarded(command: Callable[[], int]) -> int:
    """Traduce las excepciones de una corrida en códigos de salida (Ola 1, D14).

    ``RunInterrupted`` → 3, con la orden de reanudar; errores de configuración o
    de decisión humana → 2; Ctrl+C → 130. Un error esperable nunca llega como
    traceback.
    """
    from revisia.llm.preflight import PreflightError
    from revisia.orchestration.hitl import DecisionFileError
    from revisia.orchestration.journal import JournalError
    from revisia.orchestration.run_context import (
        LegacyRunError,
        RunDirExistsError,
        RunInterrupted,
    )
    from revisia.orchestration.snapshot import ProtocolMismatchError

    try:
        return command()
    except RunInterrupted as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except PreflightError as exc:
        _print_preflight(exc.report)
        return 2
    except (
        DecisionFileError,
        ProtocolMismatchError,
        JournalError,
        LegacyRunError,
        RunDirExistsError,
        FileNotFoundError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(
            "\ninterrumpido (Ctrl+C): queda registrado en run.json. "
            "Reanuda con: revisia run --resume <carpeta de la corrida>",
            file=sys.stderr,
        )
        return 130


def _cmd_run(args: argparse.Namespace) -> int:
    from revisia.orchestration.flow import resume_review, run_review
    from revisia.orchestration.snapshot import read_run_info

    if args.resume is not None:
        info = read_run_info(args.resume)
        slug = info.slug if info is not None else None
        if info is not None and args.max is not None and args.max != info.max_results:
            print(
                f"⚠ --max {args.max} se ignora al reanudar: la corrida usa "
                f"max_results={info.max_results} (run.json)."
            )
        if info is not None and info.mailto_set and not args.mailto:
            # `mailto_set` entra en la huella de cada recuperación de texto completo:
            # sin él, las ya registradas se repetirían sin Unpaywall ni ID Converter.
            print(
                "⚠ la corrida empezó con --mailto y esta reanudación no lo trae: pásalo de "
                "nuevo o los textos completos se buscarán otra vez sin Unpaywall ni el ID "
                "Converter de PMC."
            )
    else:
        slug = load_protocol(args.protocol_dir).slug
    prior = None
    if args.brain and slug:
        from revisia.memory import ResearchBrain

        prior = ResearchBrain(args.brain).recall(slug)
        if prior:
            print(
                f"🧠 Memoria previa: {prior.n_runs} corrida(s), última {prior.last_timestamp}, "
                f"{len(prior.last_included_ids)} incluidos. Esta corrida se registrará como "
                "actualización (living review)."
            )
    if args.resume is not None:
        result = resume_review(
            args.resume,
            protocol_dir=args.protocol_dir,
            auto_approve=args.auto_approve,
            mailto=args.mailto,
        )
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        result = run_review(
            args.protocol_dir,
            timestamp=timestamp,
            runs_root=args.runs_root,
            max_results=DEFAULT_MAX_RESULTS if args.max is None else args.max,
            auto_approve=args.auto_approve,
            mailto=args.mailto,
        )
    icon = {"completed": "✓", "paused": "⏸", "rejected": "✗"}.get(result.status, "•")
    print(f"\n{icon} {result.status.upper()} · {result.message}")
    if result.run_dir:
        print(f"  Corrida: {result.run_dir}")
        if result.status == "paused":
            print(f"  Reanuda con: revisia run --resume {result.run_dir}")
```

en la parte de `--brain` de `_cmd_run`, sustituir

```python
        if args.brain and result.run_dir:
            from revisia.memory import ResearchBrain

            ResearchBrain(args.brain).record_from_run(result.run_dir)
            print(f"  Cerebro: revisión sedimentada en {args.brain}/")
            if prior is not None and result.counts is not None:
```

por

```python
        if args.brain and result.run_dir:
            from revisia.memory import ResearchBrain

            brain = ResearchBrain(args.brain)
            info = read_run_info(result.run_dir)
            if info is not None and brain.has_run(info.slug, info.timestamp):
                # Reanudar una corrida ya completada no la sedimenta dos veces.
                print(f"  Cerebro: esta corrida ya estaba sedimentada en {args.brain}/")
            else:
                brain.record_from_run(result.run_dir)
                print(f"  Cerebro: revisión sedimentada en {args.brain}/")
            if prior is not None and result.counts is not None:
```

en `build_parser`, sustituir

```python
    p_run = sub.add_parser("run", help="Ejecuta el pipeline end-to-end (tracer bullet).")
    p_run.add_argument("protocol_dir", help="Carpeta del protocolo (contiene protocol.yml).")
    p_run.add_argument(
        "--max", type=int, default=50, help="Máx. de registros a recuperar por base."
    )
```

por

```python
    p_run = sub.add_parser("run", help="Ejecuta el pipeline end-to-end (tracer bullet).")
    p_run.add_argument(
        "protocol_dir",
        nargs="?",
        default=None,
        help="Carpeta del protocolo (contiene protocol.yml). Opcional con --resume: si se "
        "pasa, se comprueba que no cambió desde que empezó la corrida.",
    )
    p_run.add_argument(
        "--resume",
        metavar="RUN_DIR",
        default=None,
        help="Reanuda una corrida existente (runs/<slug>-<fecha>) sin repetir la búsqueda "
        "ni las llamadas ya hechas.",
    )
    p_run.add_argument(
        "--max",
        type=int,
        default=None,
        help=f"Máx. de registros a recuperar por base (default: {DEFAULT_MAX_RESULTS}; al "
        "reanudar manda el de run.json).",
    )
```

y en `main`, sustituir

```python
    protocol_dir = args.protocol_dir
    if not Path(protocol_dir).exists():
```

por

```python
    if args.command == "run" and args.resume is not None:
        # Reanudar: el protocolo sale de la instantánea de la corrida (00_protocol/).
        if args.protocol_dir is not None and not Path(args.protocol_dir).exists():
            print(f"error: la carpeta {args.protocol_dir!r} no existe.", file=sys.stderr)
            return 2
        return _run_guarded(lambda: _cmd_run(args))
    protocol_dir = args.protocol_dir
    if protocol_dir is None:
        print(
            "error: falta la carpeta del protocolo (o --resume <run_dir> para reanudar).",
            file=sys.stderr,
        )
        return 2
    if not Path(protocol_dir).exists():
```

sustituir

```python
    if args.command == "run":
        from revisia.orchestration.hitl import DecisionFileError

        # Preflight sin red ANTES de crear ninguna carpeta (auditoría 2026-09-03,
```

por

```python
    if args.command == "run":
        # Preflight sin red ANTES de crear ninguna carpeta (auditoría 2026-09-03,
```

y

```python
        if report.errors:
            return 2

        try:
            return _cmd_run(args)
        except DecisionFileError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    parser.print_help()
```

por

```python
        if report.errors:
            return 2
        return _run_guarded(lambda: _cmd_run(args))
    parser.print_help()
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_cli_reanudacion.py tests/test_cli_errores.py tests/test_cli_validate.py tests/test_brain.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 460 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/cli.py revisia/memory/brain.py tests/test_cli_reanudacion.py
git commit -m "feat(cli): revisia run --resume y códigos de salida de la corrida (D13, D14)" -m "run --resume <run_dir> reanuda la misma carpeta (protocolo de 00_protocol/, max_results de run.json; --max distinto se ignora con aviso, igual que la falta de --mailto). RunInterrupted sale con 3 y la orden de reanudar; errores de configuración, de protocolo, de diario o una corrida anterior a la Ola 1 salen con 2; Ctrl+C con 130; la pausa sigue en 0 e imprime cómo reanudar. ResearchBrain.has_run evita sedimentar dos veces la misma corrida. Spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 18: PRISMA-S, resúmenes y métodos desde el log de búsqueda (M12)

**Files:**
- Modify: `revisia/exports/checklist.py` (imports `TYPE_CHECKING` l.18-20; tres funciones nuevas antes de `render_prisma_s_checklist` y su firma, l.108-119; l.137-140; `render_prisma_abstracts_checklist` l.180-192)
- Modify: `revisia/exports/methods.py` (imports l.13 y l.19-20; firma l.43-46; l.70-72)
- Modify: `revisia/orchestration/pipeline.py` (import l.91-95; `_write_deliverables` l.896-952)
- Test: `tests/test_flow_oficial_y_check.py` (imports l.5-12; test nuevo al final)

**Interfaces:**
- Consumes: `SearchLog`, `SearchLogEntry` (PR-0); `01_search/log.json` (Tarea 6).
- Produces:
  - `revisia.exports.checklist.engine_search_date(search_log: SearchLog) -> str` (`AAAA-MM-DD`: el `started_utc` más temprano de las entradas, o el del log).
  - `render_prisma_s_checklist(*, databases=None, search_window=None, counts=None, search_log: SearchLog | None = None) -> str`: con log, el ítem 8 lista la cadena ejecutada de cada base (`<base>: «cadena» (00_protocol/search_strings/<key>.txt)`, `⚠ sin cadena propia, se usó la pregunta «…»`, `importación manual (imported/)`, `base desconocida`, o `búsqueda inyectada (search_fn)`), y el 13 la fecha del motor por base, con `⚠ Difiere de search_window.executed (<fecha>)` si no coincide.
  - `render_prisma_abstracts_checklist(..., search_log=None)`: ítem 4 con `última búsqueda: <fecha del motor> (registrada por el motor)`.
  - `render_methods(..., search_log=None)`: cita las cadenas en `00_protocol/search_strings/`; con log, añade la fecha del motor y las bases sin cadena propia.
  - El pipeline lee `01_search/log.json` y lo pasa a los tres.

- [ ] **Step 1: Test que falla.** En `tests/test_flow_oficial_y_check.py`, sustituir los imports

```python
from revisia.check import AdherenceReport, ItemAdherence, render_adherence_md
from revisia.exports import (
    PrismaCounts,
    render_flow_diagram,
    render_flow_markdown,
    render_flow_updated,
    render_prisma_s_checklist,
)
```

por

```python
from revisia.check import AdherenceReport, ItemAdherence, render_adherence_md
from revisia.config import ReviewProtocol
from revisia.exports import (
    PrismaCounts,
    render_flow_diagram,
    render_flow_markdown,
    render_flow_updated,
    render_methods,
    render_prisma_abstracts_checklist,
    render_prisma_s_checklist,
)
from revisia.schemas.artifacts import SearchLog, SearchLogEntry
```

y añadir al final del fichero:

```python


def test_prisma_s_desde_el_log_de_busqueda() -> None:
    # M12: los ítems 8 y 13 decían lo declarado, no lo ejecutado.
    hora = "2026-10-04T10:00:00+00:00"
    log = SearchLog(
        started_utc=hora,
        finished_utc=hora,
        max_results=50,
        mailto_set=False,
        entries=[
            SearchLogEntry(
                database="OpenAlex",
                db_key="openalex",
                kind="database",
                declared=True,
                status="ok",
                query="cadena openalex",
                query_origin="file",
                query_file="00_protocol/search_strings/openalex.txt",
                started_utc=hora,
            ),
            SearchLogEntry(
                database="Europe PMC",
                db_key="europepmc",
                kind="database",
                declared=True,
                status="ok",
                query="la pregunta",
                query_origin="question_fallback",
                started_utc=hora,
            ),
            SearchLogEntry(
                database="Scopus",
                db_key="scopus",
                kind="database",
                declared=True,
                status="manual_only",
            ),
        ],
    )
    ventana = {"from": "2015-01-01", "to": "2026-12-31", "executed": "2026-06-26"}
    markdown = render_prisma_s_checklist(
        databases=["OpenAlex", "Europe PMC", "Scopus"], search_window=ventana, search_log=log
    )
    assert markdown.count("- [ ]") == 16
    item_8 = next(x for x in markdown.splitlines() if x.startswith("- [ ] 8."))
    assert "OpenAlex: «cadena openalex» (00_protocol/search_strings/openalex.txt)" in item_8
    assert "Europe PMC: ⚠ sin cadena propia, se usó la pregunta «la pregunta»" in item_8
    assert "Scopus: importación manual" in item_8
    item_13 = next(x for x in markdown.splitlines() if x.startswith("- [ ] 13."))
    assert "fecha del motor): 2026-10-04" in item_13
    assert "Difiere de search_window.executed (2026-06-26)" in item_13

    resumenes = render_prisma_abstracts_checklist(
        databases=["OpenAlex"], search_window=ventana, search_log=log
    )
    assert "última búsqueda: 2026-10-04 (registrada por el motor)" in resumenes
    protocolo = ReviewProtocol.model_validate(
        {"slug": "d", "title": "D", "question": {"text": "¿X?", "framework": "PEO"}}
    )
    metodos = render_methods(protocol=protocolo, counts=_COUNTS, search_log=log)
    assert "fecha registrada por el motor): 2026-10-04" in metodos
    assert "00_protocol/search_strings/" in metodos
    assert "Sin cadena propia en Europe PMC" in metodos
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_flow_oficial_y_check.py::test_prisma_s_desde_el_log_de_busqueda -v`
Expected: FAIL con `TypeError: render_prisma_s_checklist() got an unexpected keyword argument 'search_log'`.

- [ ] **Step 3: Checklists.** En `revisia/exports/checklist.py`, sustituir

```python
if TYPE_CHECKING:
    from revisia.exclusions import ExclusionBreakdown
    from revisia.metrics import ScreeningMetrics
```

por

```python
if TYPE_CHECKING:
    from revisia.exclusions import ExclusionBreakdown
    from revisia.metrics import ScreeningMetrics
    from revisia.schemas.artifacts import SearchLog
```

sustituir la cabecera de `render_prisma_s_checklist`

```python
def render_prisma_s_checklist(
    *,
    databases: list[str] | None = None,
    search_window: dict[str, str] | None = None,
    counts=None,
) -> str:
    """Renderiza el checklist PRISMA-S (16 ítems) pre-rellenando lo que el motor sabe.

    La búsqueda es la etapa más automatizada del pipeline, así que la mayor
    parte de la evidencia sale sola: bases, cadenas versionadas, ventana,
    fechas, totales por base y método de deduplicación.
    """
```

por

```python
def engine_search_date(search_log: SearchLog) -> str:
    """Fecha (UTC, ``AAAA-MM-DD``) en que el motor ejecutó la búsqueda.

    La más temprana de las entradas del log; si ninguna tiene hora, la de
    inicio del log. Es la fecha que se reporta, no la tecleada en
    ``search_window.executed`` (PRISMA-S 13).
    """
    starts = [e.started_utc for e in search_log.entries if e.started_utc]
    return min(starts or [search_log.started_utc])[:10]


def _strings_evidence(search_log: SearchLog) -> str:
    """PRISMA-S 8: la cadena efectiva de cada base, tal como se ejecutó."""
    parts: list[str] = []
    for entry in search_log.entries:
        if entry.kind == "injected":
            parts.append("búsqueda inyectada (search_fn): sin cadena por base")
        elif entry.kind != "database":
            continue
        elif entry.status == "unknown":
            parts.append(f"{entry.database}: base desconocida, sin búsqueda")
        elif entry.query_origin == "file":
            parts.append(f"{entry.database}: «{entry.query}» ({entry.query_file})")
        elif entry.query_origin == "question_fallback":
            parts.append(
                f"{entry.database}: ⚠ sin cadena propia, se usó la pregunta «{entry.query}»"
            )
        else:
            parts.append(f"{entry.database}: importación manual (imported/)")
    return "Cadenas ejecutadas (01_search/log.json) — " + " · ".join(parts) + "."


def _dates_evidence(search_log: SearchLog, search_window: dict[str, str] | None) -> str:
    """PRISMA-S 13: fecha de ejecución registrada por el motor, por base."""
    dated = [f"{e.database} {e.started_utc[:10]}" for e in search_log.entries if e.started_utc]
    text = f"Búsqueda ejecutada (fecha del motor): {engine_search_date(search_log)}"
    if dated:
        text += f" ({' · '.join(dated)})"
    declared = (search_window or {}).get("executed")
    if declared and declared != engine_search_date(search_log):
        text += (
            f". ⚠ Difiere de search_window.executed ({declared}): reporta la fecha del "
            "motor o explica la diferencia"
        )
    return text + "."


def render_prisma_s_checklist(
    *,
    databases: list[str] | None = None,
    search_window: dict[str, str] | None = None,
    counts=None,
    search_log: SearchLog | None = None,
) -> str:
    """Renderiza el checklist PRISMA-S (16 ítems) pre-rellenando lo que el motor sabe.

    La búsqueda es la etapa más automatizada del pipeline, así que la mayor
    parte de la evidencia sale sola: bases, cadenas versionadas, ventana,
    fechas, totales por base y método de deduplicación. Con ``search_log``
    (``01_search/log.json``, Ola 1) los ítems 8 y 13 salen de lo que el motor
    ejecutó de verdad: la cadena de cada base (señalando dónde se usó la
    pregunta) y la fecha registrada, no la tecleada (auditoría 2026-09-03, M12).
    """
```

sustituir

```python
        auto[16] = (
            f"Deduplicación determinista del motor (DOI/título normalizado): "
            f"{counts.duplicates_removed} duplicados eliminados."
        )
```

por

```python
        auto[16] = (
            f"Deduplicación determinista del motor (DOI/título normalizado): "
            f"{counts.duplicates_removed} duplicados eliminados."
        )
    if search_log is not None:
        auto[8] = _strings_evidence(search_log)
        auto[13] = _dates_evidence(search_log, search_window)
```

y en `render_prisma_abstracts_checklist`, sustituir

```python
    search_window: dict[str, str] | None = None,
    registration: dict[str, str] | None = None,
) -> str:
    """Renderiza el checklist PRISMA 2020 para resúmenes (12 ítems).

    Como el checklist principal, se emite de andamiaje: pre-rellena la
    evidencia que el pipeline conoce (fuentes, ventana, conteos, registro) y
    deja el juicio editorial al humano.
    """
    auto: dict[int, str] = {}
    if databases:
        executed = (search_window or {}).get("executed") or "(sin fecha ejecutada)"
        auto[4] = f"Bases: {', '.join(databases)} · última búsqueda: {executed}."
```

por

```python
    search_window: dict[str, str] | None = None,
    registration: dict[str, str] | None = None,
    search_log: SearchLog | None = None,
) -> str:
    """Renderiza el checklist PRISMA 2020 para resúmenes (12 ítems).

    Como el checklist principal, se emite de andamiaje: pre-rellena la
    evidencia que el pipeline conoce (fuentes, ventana, conteos, registro) y
    deja el juicio editorial al humano. Con ``search_log``, la fecha de la
    búsqueda (ítem 4) es la que registró el motor.
    """
    auto: dict[int, str] = {}
    if databases:
        executed = (search_window or {}).get("executed") or "(sin fecha ejecutada)"
        if search_log is not None:
            executed = f"{engine_search_date(search_log)} (registrada por el motor)"
        auto[4] = f"Bases: {', '.join(databases)} · última búsqueda: {executed}."
```

- [ ] **Step 4: Métodos.** En `revisia/exports/methods.py`, sustituir

```python
from revisia.metrics import fmt_metric
```

por

```python
from revisia.exports.checklist import engine_search_date
from revisia.metrics import fmt_metric
```

sustituir

```python
    from revisia.extraction_agreement import ExtractionAgreement
    from revisia.metrics import ScreeningMetrics
```

por

```python
    from revisia.extraction_agreement import ExtractionAgreement
    from revisia.metrics import ScreeningMetrics
    from revisia.schemas.artifacts import SearchLog
```

sustituir

```python
    exclusions: ExclusionBreakdown | None = None,
    extraction_agreement: ExtractionAgreement | None = None,
) -> str:
    """Renderiza la sección de métodos (``metodologia.md``) de la revisión."""
```

por

```python
    exclusions: ExclusionBreakdown | None = None,
    extraction_agreement: ExtractionAgreement | None = None,
    search_log: SearchLog | None = None,
) -> str:
    """Renderiza la sección de métodos (``metodologia.md``) de la revisión.

    Con ``search_log`` (Ola 1) la fecha de búsqueda es la registrada por el
    motor y se dice en qué bases se usó la pregunta como cadena (PRISMA-S 8).
    """
```

y

```python
        f"Ventana de búsqueda: {_window_line(protocol.search_window)}",
        "Cadenas de búsqueda: ver protocols/<slug>/search_strings/ (PRISMA-S).",
        "Criterios: ver inclusion_exclusion.yml (declarados antes de ver resultados).",
```

por

```python
        f"Ventana de búsqueda: {_window_line(protocol.search_window)}",
        "Cadenas de búsqueda: 00_protocol/search_strings/ de la corrida (copia congelada "
        "del protocolo; PRISMA-S).",
        "Criterios: ver inclusion_exclusion.yml (declarados antes de ver resultados).",
    ]
    if search_log is not None:
        lines.append(
            f"Búsqueda ejecutada (fecha registrada por el motor): {engine_search_date(search_log)}."
        )
        fallback = [e.database for e in search_log.entries if e.query_origin == "question_fallback"]
        if fallback:
            lines.append(
                f"Sin cadena propia en {', '.join(fallback)}: se usó la pregunta como cadena."
            )
    lines += [
```

- [ ] **Step 5: El pipeline pasa el log.** En `revisia/orchestration/pipeline.py`, sustituir

```python
    ExcludedReport,
    RetrievalOutcome,
    RunInterruption,
    RunStatus,
)
```

por

```python
    ExcludedReport,
    RetrievalOutcome,
    RunInterruption,
    RunStatus,
    SearchLog,
)
```

en `_write_deliverables`, sustituir

```python
    """Escribe el entregable completo (``deliverable/``) y devuelve su carpeta."""
    protocol = run.protocol
    deliverable = run.ctx.deliverable_dir()
```

por

```python
    """Escribe el entregable completo (``deliverable/``) y devuelve su carpeta."""
    protocol = run.protocol
    search_log = SearchLog.model_validate_json(
        (run.ctx.run_dir / "01_search" / "log.json").read_text(encoding="utf-8")
    )
    deliverable = run.ctx.deliverable_dir()
```

en la llamada a `render_methods`, sustituir

```python
            exclusions=exclusion_breakdown,
            extraction_agreement=extraction_agreement,
        ),
        encoding="utf-8",
    )
```

por

```python
            exclusions=exclusion_breakdown,
            extraction_agreement=extraction_agreement,
            search_log=search_log,
        ),
        encoding="utf-8",
    )
```

en la de `render_prisma_s_checklist`, sustituir

```python
            search_window=protocol.search_window,
            counts=counts,
        ),
        encoding="utf-8",
    )
```

por

```python
            search_window=protocol.search_window,
            counts=counts,
            search_log=search_log,
        ),
        encoding="utf-8",
    )
```

y en la de `render_prisma_abstracts_checklist`, sustituir

```python
            search_window=protocol.search_window,
            registration=protocol.registration,
        ),
```

por

```python
            search_window=protocol.search_window,
            registration=protocol.registration,
            search_log=search_log,
        ),
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_flow_oficial_y_check.py tests/test_interop.py tests/test_coverage_gaps.py tests/test_pipeline_fake.py -v`
Expected: PASS (los checklists sin log siguen igual).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, **461 recogidos** (fin de PR-C).

- [ ] **Step 7: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 8: Commit**

```bash
git add revisia/exports/checklist.py revisia/exports/methods.py revisia/orchestration/pipeline.py tests/test_flow_oficial_y_check.py
git commit -m "feat(exports): PRISMA-S y métodos desde el log de búsqueda (M12)" -m "Los ítems 8 y 13 de PRISMA-S, el ítem 4 del checklist de resúmenes y metodologia.md salen de 01_search/log.json: la cadena que de verdad se ejecutó en cada base (señalando dónde se usó la pregunta) y la fecha registrada por el motor, con aviso si difiere de search_window.executed. Las cadenas se citan en 00_protocol/search_strings/. Auditoría 2026-09-03, M12; spec 2026-10-04 §7." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 19: Integración de PR-C (controlador, `C:\revisia-wt\c`)

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`: `### Added`, `### Fixed`, `### Changed`, `### Cambios incompatibles`, ya con el texto de PR-0, PR-A y PR-B)
- Modify: `README.md` (quickstart, paso 4; sección "Checkpoint humano (`decision.yml`)")
- Modify: `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md` (§14, filas 14-24)

**Interfaces:** ninguna de código. Deja `feat/ola1-reanudacion` publicada, PR-C abierta con base `feat/ola1-flujo-prisma` y el worktree `C:\revisia-wt\d` creado.

- [ ] **Step 1: Al día con B.** Si `feat/ola1-flujo-prisma` recibió commits después de crear el worktree (correcciones de la revisión de PR-B):

```bash
git -C C:/revisia-wt/c rebase feat/ola1-flujo-prisma
```

Expected: sin conflictos (B solo toca documentación tras la Tarea 15 del plan A; si tocó código del pipeline, resolver a favor de C, que reestructura `pipeline.py`, y repetir la suite).

- [ ] **Step 2: CHANGELOG.** En `CHANGELOG.md`, sustituir

```
- `04_fulltext/retrieval.json`: por cada informe buscado, si se recuperó y, si
  no, por qué (`sin_url_oa`, `sin_httpx`, `error_http`, `texto_vacio`,
  `no_disponible`).

### Fixed
```

por

```
- `04_fulltext/retrieval.json`: por cada informe buscado, si se recuperó y, si
  no, por qué (`sin_url_oa`, `sin_httpx`, `error_http`, `texto_vacio`,
  `no_disponible`).
- **Corridas reanudables** (`revisia run --resume <run_dir>`; auditoría
  2026-09-03, A9): `run.json` (identidad, huellas del protocolo y de los
  prompts, historia y estado), instantánea del protocolo en `00_protocol/`,
  búsqueda y dedup congelados en `01_search/` y `02_dedup/`, un diario por cada
  etapa con LLM o red y `llm_calls.jsonl` escrito en cada llamada. Reanudar no
  repite la búsqueda ni ninguna llamada ya hecha. Un error a mitad de corrida
  (un 429, la red) queda en `run.json` y la corrida sale con código 3 y la
  orden de reanudar.
- `01_search/log.json` (auditoría 2026-09-03, M12): una entrada por base
  declarada, por fichero de `imported/` o por búsqueda inyectada, con la cadena
  efectiva (y si salió de `search_strings/` o de la pregunta), su hash, los
  parámetros, las horas, los resultados y el error redactado. PRISMA-S (ítems 8
  y 13), el checklist de resúmenes y `metodologia.md` salen de ahí.
- `02_dedup/dedup.json` con duplicados y renombrados: un `record_id` repetido
  entre los conservados pasa a `<id>#2`.
- `decision.template.yml` junto a cada `review_request.yml` y
  `03_screening/gold.json` con el gold efectivo.

### Fixed
```

sustituir

```
  `dbr_sought_reports` copiaba los evaluados; ahora llevan los conteos reales
  (auditoría 2026-09-03, M11).

### Changed
```

por

```
  `dbr_sought_reports` copiaba los evaluados; ahora llevan los conteos reales
  (auditoría 2026-09-03, M11).
- Un fichero ilegible en `imported/` (p. ej. un RIS exportado en UTF-16) ya no
  aborta la corrida: queda como `failed` en el log de búsqueda (M7, en parte).
- Las llamadas del juez de grounding (`grounding: agent`) no quedaban
  registradas en ningún sitio; ahora llegan a `llm_calls.jsonl`.
- La solicitud del gate final llevaba la ruta absoluta del entregable.

### Changed
```

sustituir

```
  motor; se deposita en OSF/Zenodo o junto al protocolo. Las negaciones
  anteriores (`!runs/*/manifest.yml`) nunca funcionaron.

### Cambios incompatibles
```

por

```
  motor; se deposita en OSF/Zenodo o junto al protocolo. Las negaciones
  anteriores (`!runs/*/manifest.yml`) nunca funcionaron.
- `--brain` no sedimenta dos veces la misma corrida (al reanudar una ya
  completada).
- `revisia run --max` vale 50 por defecto en una corrida nueva; al reanudar
  manda el de `run.json`.

### Cambios incompatibles
```

y sustituir

```
- Los registros sin texto completo ya no llegan a extracción. Con el demo sin
  el extra `search` ni `--mailto` puede no quedar ningún estudio incluido.

## [0.7.0] · 2026-09-28
```

por

```
- Los registros sin texto completo ya no llegan a extracción. Con el demo sin
  el extra `search` ni `--mailto` puede no quedar ningún estudio incluido.
- `decision.yml` exige `request_sha256` (viene en `decision.template.yml`): una
  decisión sin hash da error y una que responde a otra solicitud no se aplica.
- Una corrida nueva sobre una carpeta que ya tiene contenido da error (dos
  `revisia run` en el mismo segundo ya no comparten carpeta).
- Las corridas anteriores a esta versión (sin `run.json`) no se pueden
  reanudar: `revisia run --resume` sale con código 2.
- `RunContext.record_meta` exige `stage=`.

## [0.7.0] · 2026-09-28
```

- [ ] **Step 3: README.** En el quickstart, sustituir

```
# 4. Ejecutar el pipeline (se pausa en cada checkpoint humano)
uv run revisia run protocols/mi-revision --brain cerebro
```

por

```
# 4. Ejecutar el pipeline (se pausa en cada checkpoint humano)
uv run revisia run protocols/mi-revision --brain cerebro
#    tras decidir (o si se interrumpe): uv run revisia run --resume runs/mi-revision-<fecha>
```

Y sustituir la sección del checkpoint, desde `## Checkpoint humano (`decision.yml`)` hasta el final de la nota "Limitación actual" (justo antes de `## Exportar el artículo (HTML / PDF)`), por:

````markdown
## Checkpoint humano (`decision.yml`)

En cada etapa con autonomía A0/A1 el pipeline escribe
`runs/<slug>-<fecha>/<etapa>/review_request.yml` con lo que debes revisar y, a
su lado, `decision.template.yml`, y se pausa. Copia la plantilla como
`<etapa>/decision.yml`, rellénala y reanuda **la misma** corrida:

```yaml
request_sha256: "9f2c…"                 # viene en la plantilla: ata la decisión a ESTA solicitud
approved: true                          # booleano YAML, sin comillas (la plantilla trae null)
actor: human:tu-nombre                  # queda en decisions_ledger.jsonl
reason: revisé los 12 excluidos por IA  # opcional; los campos extra también se registran
```

```bash
uv run revisia run --resume runs/<slug>-<fecha>
```

Si la solicitud cambió desde que la revisaste, la decisión no se aplica y la
corrida vuelve a pausar con la solicitud nueva. Un `decision.yml` vacío, con
YAML roto, sin `request_sha256`, sin `approved` o con `"false"` entre comillas
detiene la corrida con un mensaje que dice qué corregir (código 2): no se toma
como rechazo ni como aprobación. Con `approved: false` en el reporte final la
corrida termina como `rejected` (código 1) y no se sedimenta en `--brain`.

Reanudar no repite la búsqueda ni ninguna llamada ya hecha: todo queda en los
diarios de la corrida. Si la corrida se interrumpe (un 429, la red), sale con
código 3, deja el error en `run.json` y se reanuda igual; con Ctrl+C, código
130. No reanudes la misma corrida en dos procesos a la vez, y si empezaste con
`--mailto`, pásalo también al reanudar.

> **Limitación actual (Ola 1 del plan de remediación).** La decisión todavía es
> por etapa, no registro a registro (llega con la PR-D de la Ola 1). Mientras
> tanto, `--auto-approve` sirve para demostraciones: `revisia audit` las marca
> con WARN en `hitl` y en `final_gate` porque ningún humano aprobó, aunque
> todavía no las declara no publicables (eso también llega en la Ola 1).
````

- [ ] **Step 4: Desviaciones en el spec.** En §14 del spec, añadir tras la fila 13:

```
| 14 | §7 refactor | `run_pipeline` queda en preflight + instantánea + `try/except`, y la cadena de etapas en `_run_stages`; además de las funciones del spec hay `_load_gold` y `_meta_analysis`. `_Run.gate(stage, payload)` no recibe `records`/`force_human` hasta PR-D, que añade también `flags` (lo necesita M5). `_Run` gana `stage`, `finish()` e `interrupted()` | Plan PR-C |
| 15 | §7 `RunContext` | `LegacyRunError(ValueError)` para D13 al abrir sin `run.json` (el CLI la mapea a rc 2); `RunContext.open` da `FileNotFoundError` si la carpeta no existe; `write_text` también es atómico; `write_manifest(..., autonomy_effective=None, final_gate=None, extra=None)` con defaults para no romper a los llamadores existentes | Plan PR-C |
| 16 | §7 `journal.py` | `read_jsonl`/`append_jsonl` públicos (`RunContext` los usa para `llm_calls.jsonl`, con la misma tolerancia a la última línea truncada); `StageJournal.append(entry: JournalEntry)`; `TypeVar` + `# noqa: UP047` en vez de PEP 695 por la matriz 3.11/3.12 | Plan PR-C |
| 17 | §7 `snapshot.py` | `PROMPTS_DIR` y `SEARCH_STRINGS_DIR` a nivel de módulo; `ProtocolMismatchError(message, files)`; `ensure_snapshot` escribe `run.json` antes de copiar (§4.2: "lo primero que se escribe"; la huella se calcula sobre el original, idéntico byte a byte a la copia) | Plan PR-C |
| 18 | §7 preflight en `run_pipeline` | Con `search_fn` inyectado también se usa `context="resume"`: no hay bases que comprobar, y con `"run"` el demo (OpenAlex) daría error de `httpx` en el venv de desarrollo. El pipeline no imprime los avisos (los imprime el CLI). Fila 8: sin `httpx` al reanudar, lo pendiente de recuperar queda `sin_httpx`; no se convierte en aviso | Plan PR-C |
| 19 | §7 `search_stage.py` | `multi_database_search(protocol, *, strings_dir, imported_dir, question, max_results, mailto)`; `backend = "<módulo>.<función>"`; las entradas de `imported/` llevan `db_key="imported"` y `declared=true`; una base manual registra su cadena si hay fichero; la inyectada es `database = db_key = "search_fn"` con `query_origin = null`; `failures.json` incluye los ficheros importados que fallan. Sin `log.json` y sin la carpeta del protocolo (reanudar sin ella) da `ProtocolMismatchError`: `imported/` no está en la instantánea | Plan PR-C |
| 20 | §7 gates y ledger | `review_gate` añade él mismo las claves comunes (`schema_version`, `stage`, `autonomy`); el `detail` de `approve`/`reject` ya lleva `n_labels: 0` y `forced_human: false` en PR-C; volver a una decisión idéntica a una anterior ya reemplazada da `DecisionFileError` (la tupla de §4.3 es única); `GateResult` gana `request_sha256` y `actor`; `render_decision_template(*, stage, autonomy, request_sha256)` en PR-C (PR-D añade `records` y `flags`); payload de `reporte` en PR-C = `{included, hallucination_flagged, documento_sha256}` | Plan PR-C |
| 21 | §7 `inputs` de los diarios | T/A: `miembros` como listas `[modelo, temperature, seed]`; recuperación: `extra` con `fulltext_url`, `oa_url`, `pmcid`, `pmid`; extracción y RoB: `proveedor` como lista, RoB con `extraction_sha256` y `tool`; síntesis: `incluidos`, `extracciones_sha256`, `proveedor`; verificación: `narrativa_sha256`, `fuentes_sha256`, `modo`. La caché de texto se escribe y se lee en bytes UTF-8 y se verifica contra `text_sha256` (`JournalError` si no coincide) | Plan PR-C |
| 22 | §7 CLI | `_run_guarded` mapea también `LegacyRunError` y `FileNotFoundError` (carpeta inexistente) a rc 2; aviso al reanudar sin `--mailto` si la corrida empezó con él (`mailto_set` entra en la huella de cada recuperación); un `KeyboardInterrupt` también queda en `run.json.interruptions` | Plan PR-C |
| 23 | §7 tests existentes | Cambian ya en PR-C (no en PR-D ni PR-E): `tests/test_hitl.py` (decisiones con `request_sha256`, `detail ==` → subconjunto) y `tests/test_pipeline_fake.py::test_rejected_final_gate_is_not_completed` y `::test_paused_run_final_gate_falla_en_auditoria` (pasan a `correr_hasta`), porque con el hash obligatorio ninguna `decision.yml` se puede escribir antes de correr | Código real |
| 24 | §7 helpers y dobles de test | `hitl_helpers` gana `leer_solicitud(run_dir, stage)`; `etiquetar` devuelve los kwargs de `responder_gate`; `correr_hasta` reabre la carpeta con `RunContext.open` en cada vuelta. `ScriptedProvider(sintesis=...)` (aditivo) para tener citas que verificar. `engine_search_date(log)` es pública; `render_prisma_abstracts_checklist` y `render_methods` también reciben `search_log` | Plan PR-C |
```

- [ ] **Step 5: Commit de documentación.**

```bash
git -C C:/revisia-wt/c add CHANGELOG.md README.md docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md
git -C C:/revisia-wt/c commit -m "docs: CHANGELOG, README y desviaciones de PR-C (reanudación)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Verificación completa** (en `C:\revisia-wt\c`).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, **461 recogidos** (411 + 50 de PR-C).

Run (3.11 y 3.12 con venv desechable; `requires-python >= 3.13` impide `uv run --python 3.11`):

```bash
TMP="$(mktemp -d)"
for PY in 3.11 3.12; do
  uv venv -q --python "$PY" "$TMP/venv$PY"
  uv pip install -q --python "$TMP/venv$PY" pydantic pyyaml python-dotenv markdown httpx nh3 pytest
  PYTHONPATH=. "$TMP/venv$PY/Scripts/python" -m pytest -p no:cacheprovider -q
done
```

Expected: PASS en ambas (459 passed, 2 skipped).

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`
Expected: limpio.

Run (humo de punta a punta, sin red: corrida nueva → pausa → `decision.yml` con el hash → `revisia run --resume` … → completada → `revisia audit`):

```bash
RUNS="$(mktemp -d)"
uv run python - "$RUNS" <<'PY'
import sys
sys.path.insert(0, "tests")
from pathlib import Path
from test_pipeline_fake import EXAMPLE, _fake_search
from revisia.config import load_protocol
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
protocol = load_protocol(EXAMPLE)
ctx = RunContext(protocol.slug, Path(sys.argv[1]), "E2E")
r = run_pipeline(protocol, EXAMPLE, ctx, search_fn=_fake_search)
print(r.status, r.stage)
PY
RUN="$RUNS/demo-mini-review-E2E"
for _ in 1 2 3 4 5 6; do
  ESTADO=$(uv run python -c "import json,sys; print(json.load(open(sys.argv[1]))['status'])" "$RUN/run.json")
  [ "$ESTADO" = "completed" ] && break
  uv run python - "$RUN" <<'PY'
import json, sys
sys.path.insert(0, "tests")
from pathlib import Path
from hitl_helpers import responder_gate
run = Path(sys.argv[1])
etapa = json.loads((run / "run.json").read_text(encoding="utf-8"))["stage"]
print("decide la revisora:", etapa, responder_gate(run, etapa))
PY
  uv run revisia run --resume "$RUN"
done
uv run revisia audit "$RUN" | tail -1
```

Expected: `paused screening_ta`; la revisora decide cinco veces (`screening_ta`, `screening_ft`, `extraccion`, `rob`, `reporte`); las cuatro primeras reanudaciones vuelven a pausar (`⏸ PAUSED` y `Reanuda con: revisia run --resume …`) en el gate siguiente y la quinta termina con `✓ COMPLETED · Revisión completada · 0 estudios incluidos.` (sin red no hay texto completo: PRISMA estricto, D2) y `✅ APTA para preparar publicación` con el auditor de la v0.7 (el auditor estricto llega con PR-E).

- [ ] **Step 7: Publicar y abrir PR-C** (sin merge).

```bash
git -C C:/revisia-wt/c push -u origin feat/ola1-reanudacion
gh pr create --base feat/ola1-flujo-prisma --head feat/ola1-reanudacion --title "Ola 1 · PR-C: corridas reanudables con diario por etapa y request_sha256 (A9, M12)" --body "$(cat <<'EOF'
## Qué cierra

- A9 de la auditoría 2026-09-03: un 429 en cualquier registro llegaba como traceback y perdía la etapa entera; `decisions.json` se escribía al final de cada bucle y las llamadas solo llegaban a disco con el manifiesto.
- M12: los registros crudos no se guardaban; la pregunta sustituía en silencio a una cadena ausente; una base sin backend se saltaba sin avisar; la cadena, la fecha y el número de resultados por base no se registraban.
- `request_sha256` (D4): una decisión humana queda atada a la solicitud que respondió.

## Qué cambia

- `run.json` + instantánea del protocolo en `00_protocol/` (`orchestration/snapshot.py`); reanudar con el protocolo o los prompts cambiados da error con la lista de ficheros.
- Diario por etapa (`orchestration/journal.py`) para T/A, recuperación (con caché del texto), FT, extracción y 2.º extractor, RoB, síntesis y verificación; `llm_calls.jsonl` escrito en cada llamada; el juez de grounding registra sus llamadas.
- Búsqueda y dedup congelados en `01_search/` (`log.json` por base) y `02_dedup/` (`dedup.json`, ids repetidos desambiguados).
- Gates con `request_sha256` canónico, `decision.template.yml`, decisión obsoleta → pausa, ledger idempotente y reconstruible sin `decision.yml`; ninguna solicitud lleva rutas absolutas.
- `revisia run --resume <run_dir>`; códigos 3 (interrumpida), 2 (configuración), 130 (Ctrl+C); `run.json` registra estado e interrupciones.
- PRISMA-S, checklist de resúmenes y `metodologia.md` desde el log de búsqueda.
- `tests/hitl_helpers.py` (`responder_gate`, `correr_hasta`) para PR-D y el auditor.

## Cambios incompatibles

- `decision.yml` exige `request_sha256`.
- Una carpeta de corrida con contenido no se reutiliza para una corrida nueva.
- Las corridas anteriores a la Ola 1 no se reanudan (D13).

## Verificación

- `uv run pytest -p no:cacheprovider`: 461 recogidos, en verde (base: 411).
- La misma suite en 3.11 y 3.12 con venv desechable: en verde.
- `ruff check`, `ruff format --check`, `black --check`, `uv lock --check`: limpios.
- Humo sin red: corrida → pausa → `decision.yml` con el hash → `revisia run --resume` (×5) → completada → `revisia audit` APTA.

## Pila

`main` ← PR-0 ← PR-A ← PR-B ← **PR-C** ← PR-D ← PR-E. Base: `feat/ola1-flujo-prisma`. Nunca `--delete-branch` mientras otra PR use una rama como base.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR.

- [ ] **Step 8: Traspaso a la pista D.**

```bash
git worktree add C:/revisia-wt/d -b feat/ola1-hitl-por-registro feat/ola1-reanudacion
(cd C:/revisia-wt/d && uv sync --extra dev && uv run pytest -p no:cacheprovider -q)
```

Expected: 461 tests en verde. El merge de PR-C lo decide el arquitecto.

---

## Pista D · PR-D `feat/ola1-hitl-por-registro` (worktree `C:\revisia-wt\d`)

Todas las tareas de esta pista se ejecutan en `C:\revisia-wt\d`, rama `feat/ola1-hitl-por-registro` (creada en la Tarea 19, Step 8; 461 tests en verde). Si la revisión de PR-C añade commits a `feat/ola1-reanudacion`, antes de seguir: `git -C C:/revisia-wt/d rebase feat/ola1-reanudacion`.

### Task 20: `decision.yml` por registro y por cita: modelos, políticas, validación y ledger (`hitl.py`)

**Files:**
- Modify: `revisia/orchestration/hitl.py` (fichero completo)
- Test: `tests/test_hitl_registros.py` (nuevo)

**Interfaces:**
- Consumes: todo lo de la Tarea 9; `summarize_gates`, `AUTO_APPROVE_ACTOR` (PR-0).
- Produces (las consumen el pipeline, los helpers de test y el auditor):
  - `class RecordLabel(BaseModel)` (`extra="forbid"`): `label: Literal["include", "exclude"] | None = None`, `reason: str | None = None` (`label: null` = sin etiqueta).
  - `class FlagReview(BaseModel)` (`extra="forbid"`): `verdict: Literal["false_positive"] | None = None`, `reason: str | None = None` (`verdict: null` = sin adjudicar).
  - `class HumanDecision(BaseModel)` (`extra="allow"`): `request_sha256: str`, `approved: StrictBool`, `actor: str = "human:desconocido"`, `reason: str | None = None`, `records: dict[str, RecordLabel] = {}`, `flags: dict[str, FlagReview] = {}`; las claves de `records`/`flags` se convierten a texto (un `2019:` sin comillas llega como `"2019"`).
  - `@dataclass(frozen=True, slots=True) class RecordHint`: `record_id: str`, `title: str`, `proposal: str | None`, `note: str = ""`.
  - `@dataclass(frozen=True, slots=True) class RecordPolicy`: `hints: tuple[RecordHint, ...]` (sus ids son los válidos), `must_label: frozenset[str] = frozenset()`, `must_resolve: frozenset[str] = frozenset()`, `rescue_ids: frozenset[str] = frozenset()`, `reason_on_exclude: bool = False`.
  - `@dataclass(frozen=True, slots=True) class FlaggedClaim`: `index: int`, `cited_id: str | None`, `claim: str`, `note: str | None = None`; `@dataclass(frozen=True, slots=True) class FlagPolicy`: `flagged: tuple[FlaggedClaim, ...]`.
  - `@dataclass(slots=True) class GateResult`: `status`, `message`, `request_sha256: str | None = None`, `actor: str | None = None`, `labels: dict[str, RecordLabel] = {}`, `flag_reviews: dict[str, FlagReview] = {}`.
  - `review_gate(*, stage, autonomy, run_ctx, review_payload, auto_approve, records: RecordPolicy | None = None, flags: FlagPolicy | None = None, force_human: bool = False) -> GateResult`:
    - `force_human` (M5): una autonomía A2/A3 pasa a A1 (en la solicitud y en el ledger) y `auto_approve` no aplica (pausa).
    - `auto_approve` con `records.must_resolve` no vacío: pausa (D9). Si no, decisión sintética `auto-approve (demo)` **sin validar** (no exige la completitud de A0; D9).
    - Validación de una `decision.yml` cuyo hash coincide (`DecisionFileError` con el motivo): siempre, `records` en un gate sin `RecordPolicy` y `flags` en un gate sin `FlagPolicy`; al aprobar, ids o índices que no están en la solicitud, `exclude` sin `reason` con `reason_on_exclude`, etiqueta sobre un `rescue_id` sin `reason`, y un único error con los ids de `must_label ∪ must_resolve` sin etiqueta y los índices sin `verdict: false_positive` + `reason` (`"para aprobar falta etiquetar o adjudicar: <hasta 20> (N en total)"`). Con `approved: false` no se aplica ninguna etiqueta ni adjudicación.
    - Ledger al aprobar, en este orden: una `label` por etiqueta no nula (orden de id; `target=record_id`, `detail={from: propuesta IA, to, reason, rescue, request_sha256, decision_sha256}`), una `flag_review` por adjudicación (orden de índice; `target="flag:<i>"`, `detail={cited_id, claim, verdict, reason, request_sha256, decision_sha256}`) y el `approve` (`detail={…, n_labels, forced_human}`). Un `reject` va solo. Tras una caída a medias, al reanudar solo se escriben las entradas que faltan.
    - Sin `decision.yml`, la decisión del ledger para la solicitud vigente se reconstruye con sus etiquetas y adjudicaciones (`GateResult.labels`/`flag_reviews`).
  - `render_decision_template(*, stage, autonomy, request_sha256) -> str` sin cambios en esta tarea (la Tarea 21 le añade `records` y `flags`).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_hitl_registros.py`:

```python
"""Decisión humana por registro y por cita en decision.yml (Ola 1, PR-D; auditoría
2026-09-03, C1 y M5; spec 2026-10-04 §4.3 y §8)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from revisia.orchestration.hitl import (
    DecisionFileError,
    FlaggedClaim,
    FlagPolicy,
    GateResult,
    RecordHint,
    RecordPolicy,
    review_gate,
)
from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import summarize_gates

_HINTS = (
    RecordHint("a", "Estudio A", "include"),
    RecordHint("b", "Estudio B", "exclude"),
    RecordHint("c", "Estudio C (no recuperado)", None),
)
_MARCAS = FlagPolicy(
    flagged=(
        FlaggedClaim(0, "2019", "Según [2019] la IA reduce la carga.", "id citado no está"),
        FlaggedClaim(3, "rec-9", "Otro estudio [rec-9] lo confirma.", "id citado no está"),
    )
)


def _gate(
    ctx: RunContext,
    stage: str,
    *,
    politica: RecordPolicy | None = None,
    marcas: FlagPolicy | None = None,
    autonomy: str = "A1",
    auto_approve: bool = False,
    force_human: bool = False,
) -> GateResult:
    return review_gate(
        stage=stage,
        autonomy=autonomy,
        run_ctx=ctx,
        review_payload={"n": 1},
        auto_approve=auto_approve,
        records=politica,
        flags=marcas,
        force_human=force_human,
    )


def _responder(
    tmp_path: Path,
    stage: str,
    *,
    politica: RecordPolicy | None = None,
    marcas: FlagPolicy | None = None,
    force_human: bool = False,
    **decision,
) -> tuple[RunContext, GateResult]:
    """Primera vuelta (pausa), decision.yml con el hash vigente y segunda vuelta.

    ``decision`` son los campos de decision.yml (``approved`` por defecto ``True``).
    """
    ctx = RunContext("demo", tmp_path, "T")
    pausa = _gate(ctx, stage, politica=politica, marcas=marcas, force_human=force_human)
    assert pausa.status == "paused"
    contenido = {
        "request_sha256": pausa.request_sha256,
        "approved": True,
        "actor": "human:ana",
        **decision,
    }
    (ctx.stage_dir(stage) / "decision.yml").write_text(
        yaml.safe_dump(contenido, allow_unicode=True), encoding="utf-8"
    )
    return ctx, _gate(ctx, stage, politica=politica, marcas=marcas, force_human=force_human)


# ── records (cribado por registro) ─────────────────────────────────────────


def test_decision_records_id_desconocido_es_error(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match="zzz"):
        _responder(
            tmp_path,
            "screening_ft",
            politica=RecordPolicy(hints=_HINTS),
            records={"zzz": {"label": "include"}},
        )


def test_records_en_gate_sin_registros_es_error(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match="`records` solo vale"):
        _responder(tmp_path, "rob", records={"a": {"label": "include"}})


def test_ft_exclude_sin_reason_es_error(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS, reason_on_exclude=True)
    with pytest.raises(DecisionFileError, match="'a' se excluye sin `reason`"):
        _responder(tmp_path, "screening_ft", politica=politica, records={"a": {"label": "exclude"}})


def test_rescate_sin_razon_es_error(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS, rescue_ids=frozenset({"c"}))
    with pytest.raises(DecisionFileError, match="'c' no se recuperó"):
        _responder(tmp_path, "screening_ft", politica=politica, records={"c": {"label": "include"}})


def test_ft_a0_aprobar_sin_etiquetar_todo_es_error(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS, must_label=frozenset({"a", "b"}))
    with pytest.raises(DecisionFileError, match=r"falta etiquetar o adjudicar: b \(1 en total\)"):
        _responder(
            tmp_path,
            "screening_ft",
            politica=politica,
            records={"a": {"label": "include"}, "b": {"label": None}},  # null = sin etiqueta
        )


def test_etiquetas_en_el_ledger_antes_del_approve(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS, rescue_ids=frozenset({"c"}), reason_on_exclude=True)
    ctx, result = _responder(
        tmp_path,
        "screening_ft",
        politica=politica,
        records={
            "b": {"label": "exclude", "reason": "población"},
            "c": {"label": "include", "reason": "texto pedido al autor"},
            "a": {"label": None},
        },
    )
    assert result.status == "approved"
    assert {k: v.label for k, v in result.labels.items()} == {"b": "exclude", "c": "include"}
    ledger = ctx.ledger.read_all()
    assert [(e.action, e.target) for e in ledger] == [
        ("label", "b"),
        ("label", "c"),
        ("approve", None),
    ]
    rescate = ledger[1].detail
    assert (rescate["from"], rescate["to"], rescate["rescue"]) == (None, "include", True)
    assert ledger[0].detail["from"] == "exclude"
    assert ledger[0].detail["decision_sha256"] == ledger[2].detail["decision_sha256"]
    assert ledger[2].detail["n_labels"] == 2
    assert summarize_gates(ledger)["screening_ft"].n_labels == 2


def test_rechazo_no_lleva_etiquetas(tmp_path: Path) -> None:
    ctx, result = _responder(
        tmp_path,
        "screening_ft",
        politica=RecordPolicy(hints=_HINTS),
        approved=False,
        records={"a": {"label": "exclude"}},
    )
    assert (result.status, result.labels) == ("rejected", {})
    assert [e.action for e in ctx.ledger.read_all()] == ["reject"]


def test_etiquetas_se_reconstruyen_desde_el_ledger(tmp_path: Path) -> None:
    politica = RecordPolicy(hints=_HINTS)
    ctx, _ = _responder(
        tmp_path, "screening_ta", politica=politica, records={"b": {"label": "include"}}
    )
    (ctx.run_dir / "screening_ta" / "decision.yml").unlink()
    result = _gate(ctx, "screening_ta", politica=politica)
    assert result.status == "approved"
    assert {k: v.label for k, v in result.labels.items()} == {"b": "include"}
    assert len(ctx.ledger.read_all()) == 2  # nada nuevo


def test_auto_approve_pausa_con_registros_por_resolver(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_resolve=frozenset({"b"}))
    result = _gate(ctx, "screening_ft", politica=politica, auto_approve=True)
    assert result.status == "paused"
    assert "`unclear` solo los resuelve un humano" in result.message
    assert ctx.ledger.read_all() == []


def test_auto_approve_no_exige_la_completitud_a0(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_label=frozenset({"a", "b"}))
    result = _gate(ctx, "screening_ft", politica=politica, auto_approve=True)
    assert (result.status, result.actor, result.labels) == ("approved", "auto-approve (demo)", {})


# ── flags (citas marcadas en el reporte, D8) ──────────────────────────────


def test_aprobar_con_citas_marcadas_exige_adjudicar_cada_una(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match=r"cita 3 \(1 en total\)"):
        _responder(
            tmp_path,
            "reporte",
            marcas=_MARCAS,
            force_human=True,
            flags={"0": {"verdict": "false_positive", "reason": "[2019] es un año"}},
        )


def test_adjudicacion_sin_razon_es_error(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match=r"cita 0 \(1 en total\)"):
        _responder(
            tmp_path,
            "reporte",
            marcas=_MARCAS,
            force_human=True,
            flags={
                "0": {"verdict": "false_positive", "reason": " "},
                "3": {"verdict": "false_positive", "reason": "rec-9 es una errata de rec-1"},
            },
        )


def test_rechazar_con_citas_marcadas_no_exige_adjudicar(tmp_path: Path) -> None:
    ctx, result = _responder(
        tmp_path, "reporte", marcas=_MARCAS, force_human=True, approved=False, reason="inventa"
    )
    assert result.status == "rejected"
    (rechazo,) = ctx.ledger.read_all()
    assert (rechazo.action, rechazo.detail["forced_human"]) == ("reject", True)


def test_flags_en_gate_sin_marcas_es_error(tmp_path: Path) -> None:
    with pytest.raises(DecisionFileError, match="`flags` solo vale"):
        _responder(tmp_path, "reporte", flags={"0": {"verdict": "false_positive", "reason": "x"}})


def test_flag_review_en_el_ledger_antes_del_approve(tmp_path: Path) -> None:
    ctx, result = _responder(
        tmp_path,
        "reporte",
        marcas=_MARCAS,
        force_human=True,
        flags={
            "3": {"verdict": "false_positive", "reason": "rec-9 es una errata de rec-1"},
            "0": {"verdict": "false_positive", "reason": "[2019] es un año, no un id"},
        },
    )
    assert result.status == "approved"
    ledger = ctx.ledger.read_all()
    assert [(e.action, e.target) for e in ledger] == [
        ("flag_review", "flag:0"),
        ("flag_review", "flag:3"),
        ("approve", None),
    ]
    marca = ledger[0].detail
    assert (marca["cited_id"], marca["verdict"]) == ("2019", "false_positive")
    assert marca["claim"] == "Según [2019] la IA reduce la carga."
    assert marca["reason"] == "[2019] es un año, no un id"
    assert {e.actor for e in ledger} == {"human:ana"}
    resumen = summarize_gates(ledger)["reporte"]
    assert (resumen.n_flag_reviews, resumen.forced_human) == (2, True)


def test_force_human_ignora_auto_approve_y_a2(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    result = _gate(
        ctx, "reporte", marcas=_MARCAS, autonomy="A2", auto_approve=True, force_human=True
    )
    assert result.status == "paused"
    assert "exige una decisión humana" in result.message
    solicitud = yaml.safe_load(
        (ctx.run_dir / "reporte" / "review_request.yml").read_text(encoding="utf-8")
    )
    assert solicitud["autonomy"] == "A1"  # la efectiva: A1 cuando está forzada
    assert ctx.ledger.read_all() == []
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_registros.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'FlaggedClaim' from 'revisia.orchestration.hitl'`.

- [ ] **Step 3: Implementar** — sustituir `revisia/orchestration/hitl.py` completo por:

```python
"""Checkpoint humano (HITL) reproducible y SIN servidor.

En lugar de depender del pause server de Prefect (que exigiría infraestructura
y rompería el "clónalo y córrelo"), el gate es file-based:

  * Escribe ``<stage>/review_request.yml`` con lo que el humano debe revisar y su
    ``request_sha256`` (hash canónico del contenido), y a su lado
    ``decision.template.yml``, la decisión a medio rellenar.
  * Si existe ``<stage>/decision.yml`` con el ``request_sha256`` de la solicitud
    vigente (o ``--auto-approve``), aplica la decisión y la registra en el ledger
    (validado: ``approved`` booleano estricto; un fichero inválido detiene la
    corrida con un mensaje accionable). Una decisión que responde a otra
    solicitud pausa sin aplicar nada.
  * Si no, devuelve estado ``paused``: el orquestador se detiene e indica al
    humano cómo rellenar la decisión y reanudar.

El ledger manda (Ola 1, spec 2026-10-04 §4.3): registrar es idempotente al
reanudar y, sin ``decision.yml``, la decisión ya registrada para la solicitud
vigente se reutiliza (``decision.yml`` es solo el canal de entrada). Las
decisiones quedan en el ledger → reproducibilidad "a nivel decisión".

Decisión por registro y por cita (Ola 1, PR-D; auditoría 2026-09-03, C1 y M5):
en los gates de cribado el humano etiqueta registros (``records``) según una
``RecordPolicy``; en el gate final, con citas marcadas por el verificador,
adjudica cada una (``flags``) según una ``FlagPolicy``. Cada etiqueta y cada
adjudicación quedan en el ledger, antes del ``approve`` al que pertenecen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator

from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import AUTO_APPROVE_ACTOR, DecisionEntry, summarize_gates
from revisia.provenance.runmeta import canonical_sha256
from revisia.schemas.artifacts import ARTIFACT_SCHEMA_VERSION

GateStatus = Literal["approved", "paused", "rejected"]

REQUEST_FILE = "review_request.yml"
TEMPLATE_FILE = "decision.template.yml"
DECISION_FILE = "decision.yml"
# Ids o índices que lista, como mucho, un error de decisión incompleta.
_MAX_LISTED = 20


class DecisionFileError(ValueError):
    """``decision.yml`` ilegible o inválido: mensaje accionable, no traceback."""


class RecordLabel(BaseModel):
    """Etiqueta humana de un registro en ``decision.yml`` (``records``; D1, D4).

    ``label: null`` cuenta como "no etiquetado", para que la plantilla pueda
    listar todos los registros. ``reason`` es obligatoria al excluir en FT y al
    rescatar un no recuperado.
    """

    model_config = ConfigDict(extra="forbid")

    label: Literal["include", "exclude"] | None = None
    reason: str | None = None


class FlagReview(BaseModel):
    """Adjudicación humana de una cita marcada por el verificador (``flags``; D8).

    Solo existe el veredicto ``false_positive``: si una marca es una
    alucinación real, el camino es rechazar (``approved: false``).
    ``verdict: null`` cuenta como "sin adjudicar".
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["false_positive"] | None = None
    reason: str | None = None


class HumanDecision(BaseModel):
    """Contenido validado de ``<stage>/decision.yml`` (auditoría 2026-09-03, C1).

    ``request_sha256`` ata la decisión a la solicitud que el humano revisó
    (D4): si la solicitud cambia, una decisión vieja no se aplica.
    ``approved`` es un booleano YAML estricto: la cadena ``"false"`` ya no
    aprueba (``bool("false")`` es ``True``). ``records`` (solo en cribado) y
    ``flags`` (solo en ``reporte`` con citas marcadas) llevan las claves como
    texto: un id ``2019`` sin comillas se lee como número y se convierte. Los
    campos extra se conservan y viajan al ``detail`` del ledger.
    """

    model_config = ConfigDict(extra="allow")

    request_sha256: str
    approved: StrictBool
    actor: str = "human:desconocido"
    reason: str | None = None
    records: dict[str, RecordLabel] = Field(default_factory=dict)
    flags: dict[str, FlagReview] = Field(default_factory=dict)

    @field_validator("records", "flags", mode="before")
    @classmethod
    def _claves_como_texto(cls, value: object) -> object:
        if isinstance(value, dict):
            return {str(k): v for k, v in value.items()}
        return value


@dataclass(frozen=True, slots=True)
class RecordHint:
    """Lo que la plantilla muestra de un registro (en comentarios saneados).

    Attributes:
        record_id: id del registro.
        title: título.
        proposal: etiqueta propuesta por la IA (``None`` si no hay: no recuperado).
        note: resumen de la propuesta (votos, criterio, motivo del no recuperado).
    """

    record_id: str
    title: str
    proposal: str | None
    note: str = ""


@dataclass(frozen=True, slots=True)
class RecordPolicy:
    """Qué se puede y qué se debe etiquetar en un gate de cribado (D1, D2, D9).

    Attributes:
        hints: un ``RecordHint`` por registro de la solicitud (son los ids válidos).
        must_label: ids que hay que etiquetar para aprobar (A0).
        must_resolve: ids ``unclear`` de FT: solo los resuelve un humano.
        rescue_ids: no recuperados; etiquetarlos es un rescate (razón obligatoria).
        reason_on_exclude: excluir exige razón (FT: va a la lista 16b).
    """

    hints: tuple[RecordHint, ...]
    must_label: frozenset[str] = frozenset()
    must_resolve: frozenset[str] = frozenset()
    rescue_ids: frozenset[str] = frozenset()
    reason_on_exclude: bool = False


@dataclass(frozen=True, slots=True)
class FlaggedClaim:
    """Una cita marcada por el verificador (``index`` = posición en ``checks``)."""

    index: int
    cited_id: str | None
    claim: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class FlagPolicy:
    """Citas marcadas que el humano debe adjudicar para aprobar el reporte (D8)."""

    flagged: tuple[FlaggedClaim, ...]


@dataclass(slots=True)
class GateResult:
    """Resultado de un gate.

    Attributes:
        status: ``approved`` | ``paused`` | ``rejected``.
        message: texto para el humano (pausa: qué revisar y cómo reanudar).
        request_sha256: hash de la solicitud vigente.
        actor: quién decidió (``None`` en una pausa).
        labels: etiquetas explícitas por registro de la decisión aprobada.
        flag_reviews: adjudicaciones de citas marcadas de la decisión aprobada.
    """

    status: GateStatus
    message: str
    request_sha256: str | None = None
    actor: str | None = None
    labels: dict[str, RecordLabel] = field(default_factory=dict)
    flag_reviews: dict[str, FlagReview] = field(default_factory=dict)


def render_decision_template(*, stage: str, autonomy: str, request_sha256: str) -> str:
    """``decision.template.yml``: la decisión a medio rellenar (D4).

    ``approved: null`` la hace inválida tal cual: aprobar tiene que ser un acto
    deliberado. Las cadenas van entre comillas dobles (JSON es YAML válido).
    """
    lines = [
        f"# Decisión humana del gate '{stage}' (autonomía {autonomy}).",
        "#",
        "# 1. Revisa review_request.yml, en esta misma carpeta.",
        "# 2. Copia este fichero como decision.yml y pon `approved: true` (aprobar)",
        "#    o `approved: false` (rechazar). Tal cual NO es válido: `approved: null`",
        "#    no aprueba ni rechaza.",
        "# 3. Pon tu nombre en `actor` (human:<nombre>) y, si quieres, una razón.",
        "# 4. Reanuda: revisia run --resume <carpeta de esta corrida>",
        "#",
        "# `request_sha256` ata la decisión a esta solicitud: si la solicitud cambia,",
        "# una decisión vieja no se aplica y la corrida vuelve a pausar.",
        f"request_sha256: {json.dumps(request_sha256)}",
        "approved: null",
        'actor: "human:desconocido"',
        "reason: null",
    ]
    return "\n".join(lines) + "\n"


def _listed(items: list[str]) -> str:
    """Hasta ``_MAX_LISTED`` elementos y el total, para un mensaje de error."""
    shown = ", ".join(items[:_MAX_LISTED])
    more = f" … y {len(items) - _MAX_LISTED} más" if len(items) > _MAX_LISTED else ""
    return f"{shown}{more} ({len(items)} en total)"


def _validate(
    path: Path,
    decision: HumanDecision,
    *,
    records: RecordPolicy | None,
    flags: FlagPolicy | None,
) -> None:
    """Valida ``records`` y ``flags`` de una decisión cuyo hash coincide (spec §8).

    Lo estructural se comprueba siempre (``records``/``flags`` en un gate que no
    los admite). Con ``approved: false`` no se aplica ninguna etiqueta ni
    adjudicación (nunca acompañan a un ``reject``), así que el resto solo se
    comprueba al aprobar.

    Raises:
        DecisionFileError: con el motivo y los ids o índices afectados.
    """
    if decision.records and records is None:
        raise DecisionFileError(
            f"{path}: `records` solo vale en los gates de cribado (screening_ta, screening_ft); "
            "este gate se aprueba o rechaza por etapa."
        )
    if decision.flags and flags is None:
        raise DecisionFileError(
            f"{path}: `flags` solo vale en el gate `reporte` con citas marcadas por el "
            "verificador, y esta solicitud no tiene ninguna."
        )
    if not decision.approved:
        return
    if records is not None:
        valid = {h.record_id for h in records.hints}
        unknown = sorted(set(decision.records) - valid)
        if unknown:
            raise DecisionFileError(
                f"{path}: `records` con ids que no están en la solicitud: {_listed(unknown)}."
            )
        for record_id, label in decision.records.items():
            sin_razon = not (label.reason or "").strip()
            if label.label == "exclude" and records.reason_on_exclude and sin_razon:
                raise DecisionFileError(
                    f"{path}: {record_id!r} se excluye sin `reason`; en este gate la razón es "
                    "obligatoria (va a la lista de excluidos, PRISMA 2020 16b)."
                )
            if label.label is not None and record_id in records.rescue_ids and sin_razon:
                raise DecisionFileError(
                    f"{path}: {record_id!r} no se recuperó; etiquetarlo es un rescate y necesita "
                    "`reason` (cómo se obtuvo el texto completo, D2)."
                )
    if flags is not None:
        valid_index = {str(c.index) for c in flags.flagged}
        unknown = sorted(set(decision.flags) - valid_index)
        if unknown:
            raise DecisionFileError(
                f"{path}: `flags` con índices que no son citas marcadas: {_listed(unknown)}."
            )
    pending: list[str] = []
    if records is not None:
        labeled = {rid for rid, lab in decision.records.items() if lab.label is not None}
        pending += sorted((records.must_label | records.must_resolve) - labeled)
    if flags is not None:
        for claim in flags.flagged:
            review = decision.flags.get(str(claim.index))
            done = (
                review is not None
                and review.verdict == "false_positive"
                and bool((review.reason or "").strip())
            )
            if not done:
                pending.append(f"cita {claim.index}")
    if pending:
        raise DecisionFileError(
            f"{path}: para aprobar falta etiquetar o adjudicar: {_listed(pending)}. Cada registro "
            "de must_label/must_resolve necesita `label` y cada cita de must_adjudicate "
            "`verdict: false_positive` con `reason`; si alguna cita marcada es real, rechaza "
            "(`approved: false`)."
        )


def _recorded(
    entries: list[DecisionEntry],
    *,
    stage: str,
    action: str,
    target: str | None,
    request_sha256: str,
    decision_sha256: str | None,
) -> bool:
    """¿Ya está en el ledger la tupla ``(stage, action, target, request, decision)``?"""
    return any(
        (
            e.stage,
            e.action,
            e.target,
            e.detail.get("request_sha256"),
            e.detail.get("decision_sha256"),
        )
        == (stage, action, target, request_sha256, decision_sha256)
        for e in entries
    )


def _register(
    run_ctx: RunContext,
    entries: list[DecisionEntry],
    *,
    stage: str,
    autonomy: str,
    decision: HumanDecision,
    request_sha256: str,
    labels: dict[str, RecordLabel],
    flag_reviews: dict[str, FlagReview],
    records: RecordPolicy | None,
    flags: FlagPolicy | None,
    force_human: bool,
) -> None:
    """Registra la decisión en el ledger, una sola vez (idempotente al reanudar).

    Con ``approve``, primero una ``label`` por etiqueta (en orden de id) y una
    ``flag_review`` por adjudicación (en orden de índice), después el
    ``approve`` (spec §4.3). Un ``reject`` va solo.
    """
    decision_sha256 = canonical_sha256(decision.model_dump(mode="json"))
    action = "approve" if decision.approved else "reject"
    effective = summarize_gates(entries).get(stage)
    if effective is not None and (
        effective.action,
        effective.request_sha256,
        effective.decision_sha256,
    ) == (action, request_sha256, decision_sha256):
        return  # ya es la decisión efectiva: reanudar no la duplica
    if _recorded(
        entries,
        stage=stage,
        action=action,
        target=None,
        request_sha256=request_sha256,
        decision_sha256=decision_sha256,
    ):
        raise DecisionFileError(
            f"{stage}: esta misma decisión ya se registró antes y después se cambió; para "
            "volver a ella, cambia `reason` en decision.yml (el ledger no repite una "
            "decisión idéntica)."
        )
    hashes = {"request_sha256": request_sha256, "decision_sha256": decision_sha256}
    pending: list[DecisionEntry] = []
    proposals = {h.record_id: h.proposal for h in records.hints} if records else {}
    for record_id in sorted(labels):
        label = labels[record_id]
        pending.append(
            DecisionEntry(
                stage=stage,
                actor=decision.actor,
                autonomy=autonomy,
                action="label",
                target=record_id,
                detail={
                    "from": proposals.get(record_id),
                    "to": label.label,
                    "reason": label.reason,
                    "rescue": bool(records and record_id in records.rescue_ids),
                    **hashes,
                },
            )
        )
    claims = {str(c.index): c for c in flags.flagged} if flags else {}
    for index in sorted(flag_reviews, key=int):
        review, claim = flag_reviews[index], claims[index]
        pending.append(
            DecisionEntry(
                stage=stage,
                actor=decision.actor,
                autonomy=autonomy,
                action="flag_review",
                target=f"flag:{index}",
                detail={
                    "cited_id": claim.cited_id,
                    "claim": claim.claim,
                    "verdict": review.verdict,
                    "reason": review.reason,
                    **hashes,
                },
            )
        )
    for entry in pending:  # tras una caída a medias, solo las que faltan
        if not _recorded(
            entries,
            stage=stage,
            action=entry.action,
            target=entry.target,
            request_sha256=request_sha256,
            decision_sha256=decision_sha256,
        ):
            run_ctx.ledger.append(entry)
    detail = {
        **decision.model_dump(
            exclude={"approved", "actor", "request_sha256", "records", "flags"},
            exclude_none=True,
        ),
        **hashes,
        "n_labels": len(labels),
        "forced_human": force_human,
    }
    run_ctx.ledger.append(
        DecisionEntry(
            stage=stage, actor=decision.actor, autonomy=autonomy, action=action, detail=detail
        )
    )


def _from_ledger(
    entries: list[DecisionEntry], stage: str, decision_sha256: str | None
) -> tuple[dict[str, RecordLabel], dict[str, FlagReview]]:
    """Etiquetas y adjudicaciones de una decisión ya registrada (el ledger manda)."""
    labels: dict[str, RecordLabel] = {}
    reviews: dict[str, FlagReview] = {}
    if decision_sha256 is None:
        return labels, reviews
    for e in entries:
        if e.stage != stage or e.detail.get("decision_sha256") != decision_sha256:
            continue
        if e.action == "label" and e.target is not None:
            labels[e.target] = RecordLabel(label=e.detail.get("to"), reason=e.detail.get("reason"))
        elif e.action == "flag_review" and e.target is not None:
            reviews[e.target.removeprefix("flag:")] = FlagReview(
                verdict=e.detail.get("verdict"), reason=e.detail.get("reason")
            )
    return labels, reviews


def review_gate(
    *,
    stage: str,
    autonomy: str,
    run_ctx: RunContext,
    review_payload: dict,
    auto_approve: bool,
    records: RecordPolicy | None = None,
    flags: FlagPolicy | None = None,
    force_human: bool = False,
) -> GateResult:
    """Aplica el checkpoint humano de una etapa según su autonomía.

    La solicitud es ``{schema_version, stage, autonomy, **review_payload}`` y su
    ``request_sha256`` es ``canonical_sha256`` de ese contenido: sin rutas
    absolutas ni horas, para que sea estable entre reanudaciones (spec §4.3).

    A2/A3 no pausan (registran ``auto-proceed`` y continúan). A0/A1 requieren
    una decisión: ``decision.yml`` con el hash vigente, la ya registrada en el
    ledger para esa solicitud, o ``auto_approve``; si no hay ninguna, pausan.

    ``records`` y ``flags`` habilitan la decisión por registro y por cita.
    ``--auto-approve`` aprueba con las etiquetas de la IA, salvo que haya
    registros que solo resuelve un humano (``must_resolve``): entonces pausa
    (D9). Con ``force_human`` (citas marcadas, M5) se ignoran ``auto_approve`` y
    una autonomía A2/A3, que pasa a A1 en la solicitud y el ledger.
    """
    if force_human and autonomy in {"A2", "A3"}:
        autonomy = "A1"
    payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "stage": stage,
        "autonomy": autonomy,
        **review_payload,
    }
    request_sha256 = canonical_sha256(payload)
    entries = run_ctx.ledger.read_all()

    if autonomy in {"A2", "A3"}:
        if not _recorded(
            entries,
            stage=stage,
            action="auto-proceed",
            target=None,
            request_sha256=request_sha256,
            decision_sha256=None,
        ):
            run_ctx.ledger.append(
                DecisionEntry(
                    stage=stage,
                    actor=f"agent:{stage}",
                    autonomy=autonomy,
                    action="auto-proceed",
                    detail={
                        "reason": f"autonomía {autonomy}: ejecuta y notifica",
                        "request_sha256": request_sha256,
                    },
                )
            )
        return GateResult(
            "approved", f"{stage}: auto-proceed ({autonomy}).", request_sha256, f"agent:{stage}"
        )

    # A0/A1 → requiere humano.
    stage_dir = run_ctx.stage_dir(stage)
    run_ctx.write_text(
        f"{stage}/{REQUEST_FILE}",
        yaml.safe_dump(
            {"request_sha256": request_sha256, **payload}, allow_unicode=True, sort_keys=False
        ),
    )
    run_ctx.write_text(
        f"{stage}/{TEMPLATE_FILE}",
        render_decision_template(stage=stage, autonomy=autonomy, request_sha256=request_sha256),
    )
    request_path = stage_dir / REQUEST_FILE
    decision_path = stage_dir / DECISION_FILE
    resume = f"Reanuda con: revisia run --resume {run_ctx.run_dir}"

    decision = _read_decision(decision_path)
    from_file = decision is not None
    if decision is not None and decision.request_sha256 != request_sha256:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}': {decision_path} responde a otra solicitud "
                f"(request_sha256 {decision.request_sha256[:12]}…; la vigente es "
                f"{request_sha256[:12]}…). No se aplicó nada: revisa {request_path} y "
                f"rellena de nuevo la decisión desde {stage_dir / TEMPLATE_FILE}. {resume}"
            ),
            request_sha256,
        )
    if decision is None:
        effective = summarize_gates(entries).get(stage)
        if effective is not None and effective.request_sha256 == request_sha256:
            # El ledger manda: la decisión de esta solicitud ya está registrada.
            approved = effective.action != "reject"
            labels, reviews = _from_ledger(entries, stage, effective.decision_sha256)
            return GateResult(
                "approved" if approved else "rejected",
                f"{stage}: {'aprobado' if approved else 'rechazado'} por {effective.actor} "
                "(decisión registrada en el ledger).",
                request_sha256,
                effective.actor,
                labels,
                reviews,
            )
        if auto_approve and force_human:
            return GateResult(
                "paused",
                (
                    f"Checkpoint humano en '{stage}': el verificador marcó citas y este gate "
                    "exige una decisión humana (M5); --auto-approve no aplica aquí. Revisa "
                    f"{request_path} y rellena {stage_dir / TEMPLATE_FILE} como "
                    f"{decision_path}. {resume}"
                ),
                request_sha256,
            )
        if auto_approve and records is not None and records.must_resolve:
            return GateResult(
                "paused",
                (
                    f"Checkpoint humano en '{stage}': {len(records.must_resolve)} registro(s) "
                    "`unclear` solo los resuelve un humano (D9): --auto-approve no adopta una "
                    f"etiqueta que la IA no dio. Etiquétalos en {decision_path} (`records`, "
                    f"desde {stage_dir / TEMPLATE_FILE}). {resume}"
                ),
                request_sha256,
            )
        if auto_approve:
            decision = HumanDecision(
                request_sha256=request_sha256, approved=True, actor=AUTO_APPROVE_ACTOR
            )
    if decision is None:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}' ({autonomy}). Revisa {request_path}, rellena "
                f"{stage_dir / TEMPLATE_FILE} y guárdalo como {decision_path} (o vuelve a "
                f"correr con --auto-approve). {resume}"
            ),
            request_sha256,
        )

    if from_file:
        # La sintética de --auto-approve no se valida: adopta las etiquetas de la
        # IA y no exige la completitud de A0 (D9).
        _validate(decision_path, decision, records=records, flags=flags)
    labels: dict[str, RecordLabel] = {}
    reviews: dict[str, FlagReview] = {}
    if decision.approved:
        labels = {rid: lab for rid, lab in decision.records.items() if lab.label is not None}
        reviews = dict(decision.flags) if flags is not None else {}
    _register(
        run_ctx,
        entries,
        stage=stage,
        autonomy=autonomy,
        decision=decision,
        request_sha256=request_sha256,
        labels=labels,
        flag_reviews=reviews,
        records=records,
        flags=flags,
        force_human=force_human,
    )
    if decision.approved:
        return GateResult(
            "approved",
            f"{stage}: aprobado por {decision.actor}.",
            request_sha256,
            decision.actor,
            labels,
            reviews,
        )
    return GateResult(
        "rejected", f"{stage}: rechazado por {decision.actor}.", request_sha256, decision.actor
    )


_DECISION_HINT = (
    "Se espera un mapa YAML con `request_sha256` (el de review_request.yml; parte de "
    "decision.template.yml), `approved: true` o `approved: false` (booleano, sin "
    "comillas) y, opcionalmente, `actor: human:<nombre>` y `reason: <texto>`."
)


def _read_decision(path: Path) -> HumanDecision | None:
    """Lee y valida ``decision.yml``; ``None`` si no existe.

    Raises:
        DecisionFileError: si el fichero está vacío, no es YAML válido, su raíz
            no es un mapa, falta ``request_sha256``, ``approved`` no es un
            booleano o ``records``/``flags`` traen campos desconocidos.
    """
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DecisionFileError(f"{path}: YAML inválido ({exc}). {_DECISION_HINT}") from exc
    if raw is None:
        raise DecisionFileError(f"{path}: está vacío. {_DECISION_HINT}")
    if not isinstance(raw, dict):
        raise DecisionFileError(
            f"{path}: la raíz es {type(raw).__name__}, no un mapa. {_DECISION_HINT}"
        )
    try:
        return HumanDecision.model_validate(raw)
    except ValidationError as exc:
        detalle = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise DecisionFileError(f"{path}: decisión inválida ({detalle}). {_DECISION_HINT}") from exc
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_registros.py tests/test_hitl.py -v`
Expected: PASS (16 + 15).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 477 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/hitl.py tests/test_hitl_registros.py
git commit -m "feat(hitl): decisión por registro y adjudicación de citas en decision.yml (C1, D8)" -m "decision.yml gana records ({id: {label, reason}}, solo en cribado) y flags ({índice: {verdict: false_positive, reason}}, solo en el reporte con citas marcadas). RecordPolicy y FlagPolicy dicen qué se puede y qué se debe decidir; la validación nombra los ids o índices y, al aprobar, exige etiquetar must_label/must_resolve y adjudicar cada cita marcada con razón. Cada label y cada flag_review va al ledger antes de su approve. --auto-approve pausa ante unclear (D9) y force_human ignora --auto-approve y A2/A3 (M5). Spec 2026-10-04 §4.3 y §8." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 21: Plantilla con registros y citas, saneada contra la inyección YAML (D4)

**Files:**
- Modify: `revisia/orchestration/hitl.py` (`render_decision_template` l.188-211, con una función nueva antes; llamada en `review_gate` l.523)
- Test: `tests/test_hitl_registros.py` (import l.11-19; dos tests nuevos al final)

**Interfaces:**
- Consumes: `RecordPolicy`, `FlagPolicy` (Tarea 20).
- Produces:
  - `render_decision_template(*, stage: str, autonomy: str, request_sha256: str, records: RecordPolicy | None, flags: FlagPolicy | None) -> str` (firma del spec §8): con `records`, un bloque `records:` con `"<id>": {label: null, reason: null}` por registro (clave con `json.dumps`) y, encima de cada uno, un comentario con título, propuesta IA, marcas (`obligatorio`, `unclear: resuélvelo`, `no recuperado: rescatable`) y la nota; con `flags`, un bloque `flags:` con `"<índice>": {verdict: null, reason: null}` y el comentario de la cita; la cabecera dice que, si una marca es real, hay que rechazar.
  - `_comment(text: str, limit: int = 200) -> str`: una línea `# …` sin saltos (`str.split()` también corta en `U+2028`, `\r`…) ni caracteres no imprimibles.

- [ ] **Step 1: Tests que fallan.** En `tests/test_hitl_registros.py`, sustituir

```python
from revisia.orchestration.hitl import (
    DecisionFileError,
    FlaggedClaim,
    FlagPolicy,
    GateResult,
    RecordHint,
    RecordPolicy,
    review_gate,
)
```

por

```python
from revisia.orchestration.hitl import (
    DecisionFileError,
    FlaggedClaim,
    FlagPolicy,
    GateResult,
    RecordHint,
    RecordPolicy,
    render_decision_template,
    review_gate,
)
```

y añadir al final del fichero:

```python


# ── decision.template.yml (D4) ────────────────────────────────────────────


def test_template_invalido_hasta_rellenarlo(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    politica = RecordPolicy(hints=_HINTS, must_label=frozenset({"a", "b"}))
    _gate(ctx, "screening_ft", politica=politica)
    carpeta = ctx.run_dir / "screening_ft"
    plantilla = (carpeta / "decision.template.yml").read_text(encoding="utf-8")
    datos = yaml.safe_load(plantilla)
    assert datos["approved"] is None
    assert datos["records"] == {
        "a": {"label": None, "reason": None},
        "b": {"label": None, "reason": None},
        "c": {"label": None, "reason": None},
    }

    (carpeta / "decision.yml").write_text(plantilla, encoding="utf-8")  # copiada tal cual
    with pytest.raises(DecisionFileError, match="booleano"):
        _gate(ctx, "screening_ft", politica=politica)

    datos["approved"] = True
    datos["records"]["a"]["label"] = "include"
    datos["records"]["b"] = {"label": "exclude", "reason": "diseño"}
    (carpeta / "decision.yml").write_text(yaml.safe_dump(datos), encoding="utf-8")
    assert _gate(ctx, "screening_ft", politica=politica).status == "approved"


def test_template_sanea_saltos_de_linea_del_llm() -> None:
    inyeccion = "fuera\napproved: true\nrecords: {a: x} actor: human:mallory\r\n"
    politica = RecordPolicy(
        hints=(RecordHint("10.1000/123", f"Título {inyeccion}", "exclude", inyeccion),),
        must_label=frozenset({"10.1000/123"}),
    )
    marcas = FlagPolicy(flagged=(FlaggedClaim(2, "2019", f"afirmación {inyeccion}", inyeccion),))
    plantilla = render_decision_template(
        stage="screening_ft", autonomy="A0", request_sha256="h", records=politica, flags=marcas
    )

    datos = yaml.safe_load(plantilla)
    assert datos["approved"] is None
    assert datos["actor"] == "human:desconocido"
    assert datos["records"] == {"10.1000/123": {"label": None, "reason": None}}
    assert datos["flags"] == {"2": {"verdict": None, "reason": None}}
    lineas = [x.strip() for x in plantilla.splitlines()]  # splitlines también corta en U+2028
    assert [x for x in lineas if x.startswith(("approved:", "actor:"))] == [
        "approved: null",
        'actor: "human:desconocido"',
    ]
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_registros.py -v`
Expected: FAIL `test_template_invalido_hasta_rellenarlo` (`KeyError: 'records'`: la plantilla no lista los registros) y `test_template_sanea_saltos_de_linea_del_llm` (`TypeError: render_decision_template() got an unexpected keyword argument 'records'`).

- [ ] **Step 3: Implementar.** En `revisia/orchestration/hitl.py`, sustituir la cabecera de `render_decision_template`

```python
def render_decision_template(*, stage: str, autonomy: str, request_sha256: str) -> str:
    """``decision.template.yml``: la decisión a medio rellenar (D4).

    ``approved: null`` la hace inválida tal cual: aprobar tiene que ser un acto
    deliberado. Las cadenas van entre comillas dobles (JSON es YAML válido).
    """
    lines = [
```

por

```python
def _comment(text: str, limit: int = 200) -> str:
    """Una línea de comentario YAML segura para texto que viene del LLM o del registro.

    Todo espacio (saltos de línea, retornos de carro, ``U+2028``…) pasa a un
    espacio y los caracteres no imprimibles desaparecen: un ``rationale`` con
    un salto de línea dentro de un comentario inyectaría claves
    (``approved: true``) en la plantilla (D4).
    """
    plain = "".join(ch for ch in " ".join(text.split()) if ch.isprintable())
    if len(plain) > limit:
        plain = plain[: limit - 1] + "…"
    return f"# {plain}"


def render_decision_template(
    *,
    stage: str,
    autonomy: str,
    request_sha256: str,
    records: RecordPolicy | None,
    flags: FlagPolicy | None,
) -> str:
    """``decision.template.yml``: la decisión a medio rellenar (D4).

    ``approved: null`` la hace inválida tal cual: aprobar tiene que ser un acto
    deliberado. Con ``records`` lista cada registro de la solicitud con
    ``label: null`` y su propuesta IA en un comentario; con ``flags``, cada cita
    marcada con ``verdict: null``. Las claves van entre comillas dobles
    (``json.dumps``): un id ``10.1000/123`` o ``2019`` no se lee como número.
    """
    lines = [
```

sustituir su final

```python
        f"request_sha256: {json.dumps(request_sha256)}",
        "approved: null",
        'actor: "human:desconocido"',
        "reason: null",
    ]
    return "\n".join(lines) + "\n"
```

por

```python
    ]
    if flags is not None:
        lines += [
            "#",
            "# Citas marcadas por el verificador: para APROBAR, adjudica cada una con",
            "# `verdict: false_positive` y una `reason`. Si alguna es una alucinación real,",
            "# rechaza (`approved: false`): no existe un veredicto «aceptar el riesgo» (D8).",
        ]
    if records is not None:
        lines += [
            "#",
            "# Registros: `label: include` o `label: exclude`, con `reason` (obligatoria al",
            "# excluir en texto completo y al rescatar un no recuperado). `label: null` deja",
            "# la propuesta de la IA como está: no es una decisión humana (D5).",
            f"# Obligatorio etiquetar: {len(records.must_label)} · `unclear` por resolver: "
            f"{len(records.must_resolve)} · no recuperados rescatables: {len(records.rescue_ids)}.",
        ]
    lines += [
        f"request_sha256: {json.dumps(request_sha256)}",
        "approved: null",
        'actor: "human:desconocido"',
        "reason: null",
    ]
    if records is not None:
        lines.append("records:")
        for hint in records.hints:
            marks = [
                text
                for ids, text in (
                    (records.must_label, "obligatorio"),
                    (records.must_resolve, "unclear: resuélvelo"),
                    (records.rescue_ids, "no recuperado: rescatable"),
                )
                if hint.record_id in ids
            ]
            summary = f"{hint.title} · propuesta IA: {hint.proposal or '—'}"
            if marks:
                summary += f" · {', '.join(marks)}"
            if hint.note:
                summary += f" · {hint.note}"
            lines.append(f"  {_comment(summary)}")
            key = json.dumps(hint.record_id, ensure_ascii=False)
            lines.append(f"  {key}: {{label: null, reason: null}}")
    if flags is not None:
        lines.append("flags:")
        for claim in flags.flagged:
            summary = f"[{claim.index}] cita {claim.cited_id!r}: «{claim.claim}»"
            if claim.note:
                summary += f" · {claim.note}"
            lines.append(f"  {_comment(summary)}")
            lines.append(f'  "{claim.index}": {{verdict: null, reason: null}}')
    return "\n".join(lines) + "\n"
```

y en `review_gate`, sustituir

```python
        render_decision_template(stage=stage, autonomy=autonomy, request_sha256=request_sha256),
```

por

```python
        render_decision_template(
            stage=stage,
            autonomy=autonomy,
            request_sha256=request_sha256,
            records=records,
            flags=flags,
        ),
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_registros.py tests/test_hitl.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 479 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/hitl.py tests/test_hitl_registros.py
git commit -m "feat(hitl): plantilla con registros y citas, saneada contra inyección YAML (D4)" -m "decision.template.yml lista cada registro de la solicitud con label: null y cada cita marcada con verdict: null, con la propuesta IA y el motivo en comentarios de una sola línea: un rationale del LLM con saltos de línea ya no puede inyectar claves como approved: true. Las claves van entre comillas para que 10.1000/123 o 2019 no se lean como números. Spec 2026-10-04 §8." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 22: Gate T/A por registro: solicitud con los votos, etiquetas explícitas (D1, D5) — `orchestration/gates.py`

**Files:**
- Create: `revisia/orchestration/gates.py`
- Modify: `revisia/orchestration/pipeline.py` (import l.69; `_Run.gate` l.244-253; bloque T/A de `_run_stages` l.1082-1092)
- Test: `tests/test_hitl_pipeline.py` (nuevo)

**Interfaces:**
- Consumes: `RecordHint`, `RecordLabel`, `RecordPolicy`, `FlagPolicy`, `review_gate(records=, flags=, force_human=)` (Tareas 20 y 21); `correr_hasta`, `leer_solicitud` (Tarea 9).
- Produces:
  - `revisia.orchestration.gates.ta_payload(*, decisions, records, autonomy) -> dict` (claves de §4.3 sin las comunes: `mode` (`"exceptions"` en A1, `"label_all"` en A0), `n_screened`, `n_proposed_pass`, `n_proposed_exclude`, `records` ordenados por id con `{record_id, title, year, doi, source_db, proposal, votes: [{model, label, confidence, rationale, criteria_violated}]}`, `must_label` (todos en A0, `[]` en A1)). La Tarea 23 le añade `quality` y `ai_excluded`.
  - `ta_policy(*, decisions, records, autonomy) -> RecordPolicy` (hints con la propuesta del ensemble y el resumen de votos; `must_label` en A0).
  - `apply_labels(decisions, labels: Mapping[str, RecordLabel], actor: str | None) -> list[ScreeningDecision]`: copias; `human_label`/`human_reason`/`human_actor` **solo** ante una etiqueta explícita (D5); `final_label = human_label or ensemble_label`.
  - `_Run.gate(stage, payload, *, records: RecordPolicy | None = None, flags: FlagPolicy | None = None, force_human: bool = False) -> GateResult`.
  - Pipeline: tras aprobar T/A, `03_screening/decisions.json` se reescribe con `human_*` y `final_label` (§4.2), y pasan a FT los `final_label ∈ {include, unclear}`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_hitl_pipeline.py`:

```python
"""HITL por registro en el pipeline (Ola 1, PR-D; auditoría 2026-09-03, C1, M5 y M13;
spec 2026-10-04 §8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import correr_hasta, leer_solicitud

from revisia.config import load_protocol
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _busqueda(query: str, n: int) -> list[SearchRecord]:
    """rec-2 lleva "irrelevante" en el título: el guion lo excluye en T/A y en FT."""
    return [
        SearchRecord(
            record_id="rec-1",
            title="LLM screening for systematic reviews",
            abstract="We evaluate LLM screening.",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-2",
            title="Estudio irrelevante para la pregunta",
            abstract="Otra cosa.",
            source_db="OpenAlex",
        ),
    ][:n]


@pytest.fixture()
def proveedor(monkeypatch: pytest.MonkeyPatch) -> ScriptedProvider:
    guion = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: guion)
    return guion


def _json(ctx: RunContext, relpath: str):
    return json.loads((ctx.run_dir / relpath).read_text(encoding="utf-8"))


def _por_id(ctx: RunContext, relpath: str) -> dict[str, dict]:
    return {d["record_id"]: d for d in _json(ctx, relpath)}


# ── Cribado T/A (D1, D5) ────────────────────────────────────────────────


def test_review_request_ta_lista_votos_por_miembro(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda).status == "paused"

    solicitud = leer_solicitud(ctx.run_dir, "screening_ta")
    assert (solicitud["mode"], solicitud["autonomy"], solicitud["must_label"]) == (
        "exceptions",
        "A1",
        [],
    )
    assert (solicitud["n_screened"], solicitud["n_proposed_pass"]) == (2, 1)
    assert solicitud["n_proposed_exclude"] == 1
    assert [r["record_id"] for r in solicitud["records"]] == ["rec-1", "rec-2"]
    rec2 = solicitud["records"][1]
    assert (rec2["proposal"], rec2["source_db"], rec2["title"]) == (
        "exclude",
        "OpenAlex",
        "Estudio irrelevante para la pregunta",
    )
    assert rec2["votes"] == [
        {
            "model": modelo,
            "label": "exclude",
            "confidence": 0.9,
            "rationale": "guion: exclude",
            "criteria_violated": ["fuera de alcance"],
        }
        for modelo in ("fake:fake-a", "fake:fake-b")
    ]
    plantilla = yaml.safe_load(
        (ctx.run_dir / "screening_ta" / "decision.template.yml").read_text(encoding="utf-8")
    )
    assert set(plantilla["records"]) == {"rec-1", "rec-2"}


def test_ta_a1_excepcion_humana_rescata_registro(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def rescatar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ta":
            return {"records": {"rec-2": {"label": "include", "reason": "sí trata de cribado"}}}
        return None

    pausa = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        etiquetar=rescatar,
        parar_en="screening_ft",
    )

    assert pausa.stage == "screening_ft"
    decisiones = _por_id(ctx, "03_screening/decisions.json")
    rec2 = decisiones["rec-2"]
    assert (rec2["ensemble_label"], rec2["human_label"], rec2["final_label"]) == (
        "exclude",
        "include",
        "include",
    )
    assert (rec2["human_reason"], rec2["human_actor"]) == ("sí trata de cribado", "human:revisora")
    assert decisiones["rec-1"]["human_label"] is None
    etiqueta = next(e for e in ctx.ledger.read_all() if e.action == "label")
    assert (etiqueta.target, etiqueta.detail["from"], etiqueta.detail["to"]) == (
        "rec-2",
        "exclude",
        "include",
    )
    assert len(_json(ctx, "04_fulltext/retrieval.json")) == 2  # rec-2 llega a texto completo


def test_ta_a1_sin_tocar_conserva_human_label_none(tmp_path: Path, proveedor) -> None:
    # D5: aprobar en bloque deja la exclusión como "IA avalada", no humana.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        parar_en="screening_ft",
    )

    decisiones = _por_id(ctx, "03_screening/decisions.json")
    assert [d["human_label"] for d in decisiones.values()] == [None, None]
    assert decisiones["rec-2"]["final_label"] == "exclude"
    assert not [e for e in ctx.ledger.read_all() if e.action == "label"]
    aprobacion = next(e for e in ctx.ledger.read_all() if e.stage == "screening_ta")
    assert (aprobacion.action, aprobacion.detail["n_labels"]) == ("approve", 0)
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py -v`
Expected: FAIL `test_review_request_ta_lista_votos_por_miembro` (`KeyError: 'mode'`) y `test_ta_a1_excepcion_humana_rescata_registro` (`DecisionFileError: … `records` solo vale en los gates de cribado`: el pipeline aún no pasa una `RecordPolicy`). `test_ta_a1_sin_tocar_conserva_human_label_none` ya pasa: es la guardia de D5 para el cableado de esta tarea.

- [ ] **Step 3: Implementar el módulo** — crear `revisia/orchestration/gates.py`:

```python
"""Solicitudes y políticas de los gates (Ola 1, PR-D; spec 2026-10-04 §4.3 y §8).

Funciones puras. Cada ``*_payload`` construye lo que el humano revisa en un gate
(las claves propias de §4.3; ``schema_version``, ``stage`` y ``autonomy`` las
pone ``review_gate``) y cada ``*_policy`` dice qué puede y qué debe decidir.
``apply_labels`` aplica después las etiquetas de la decisión aprobada.

Ningún payload lleva rutas absolutas ni horas: su hash (``request_sha256``)
tiene que ser estable entre reanudaciones, o el gate no convergería nunca.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision


def _mode(autonomy: str) -> str:
    """``label_all`` en A0 (el humano etiqueta cada registro); ``exceptions`` en A1."""
    return "label_all" if autonomy == "A0" else "exceptions"


def _votes(decision: ScreeningDecision) -> list[dict]:
    return [
        {
            "model": v.model,
            "label": v.label,
            "confidence": v.confidence,
            "rationale": v.rationale,
            "criteria_violated": list(v.criteria_violated),
        }
        for v in decision.votes
    ]


def _note(decision: ScreeningDecision) -> str:
    """Resumen de los votos para la plantilla (se sanea al escribirla)."""
    parts = []
    for v in decision.votes:
        criteria = f" [{', '.join(v.criteria_violated)}]" if v.criteria_violated else ""
        parts.append(f"{v.model}: {v.label} ({v.confidence:.2f}) «{v.rationale}»{criteria}")
    return " | ".join(parts)


def ta_payload(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    autonomy: str,
) -> dict:
    """Solicitud del gate ``screening_ta`` (spec §4.3).

    ``records`` ordenados por id, cada uno con la propuesta del ensemble y el
    voto de cada miembro; en A0 (``label_all``) todos van a ``must_label``.
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    by_id = {r.record_id: r for r in records}
    return {
        "mode": _mode(autonomy),
        "n_screened": len(decisions),
        "n_proposed_pass": sum(1 for d in decisions if d.ensemble_label in {"include", "unclear"}),
        "n_proposed_exclude": sum(1 for d in decisions if d.ensemble_label == "exclude"),
        "records": [
            {
                "record_id": d.record_id,
                "title": by_id[d.record_id].title,
                "year": by_id[d.record_id].year,
                "doi": by_id[d.record_id].doi,
                "source_db": by_id[d.record_id].source_db,
                "proposal": d.ensemble_label,
                "votes": _votes(d),
            }
            for d in decisions
        ],
        "must_label": [d.record_id for d in decisions] if autonomy == "A0" else [],
    }


def ta_policy(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    autonomy: str,
) -> RecordPolicy:
    """Qué puede etiquetar el humano en T/A: cualquier registro cribado (D1).

    En A1 (por defecto) aprueba la propuesta con excepciones opcionales; en A0
    tiene que etiquetarlos todos.
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    titles = {r.record_id: r.title for r in records}
    hints = tuple(
        RecordHint(d.record_id, titles.get(d.record_id, d.record_id), d.ensemble_label, _note(d))
        for d in decisions
    )
    must_label = frozenset(d.record_id for d in decisions) if autonomy == "A0" else frozenset()
    return RecordPolicy(hints=hints, must_label=must_label)


def apply_labels(
    decisions: Iterable[ScreeningDecision],
    labels: Mapping[str, RecordLabel],
    actor: str | None,
) -> list[ScreeningDecision]:
    """Aplica las etiquetas explícitas de una decisión aprobada (D5).

    ``human_label``, ``human_reason`` y ``human_actor`` se escriben solo ante
    una etiqueta explícita: la aprobación en bloque deja la propuesta IA como
    "IA avalada" (``human_label = None``), para que el desglose trAIce R1 siga
    significando algo. ``final_label`` es la humana si existe; si no, la del
    ensemble (``None`` en un no recuperado sin rescate). Devuelve copias.
    """
    labeled: list[ScreeningDecision] = []
    for decision in decisions:
        new = decision.model_copy(deep=True)
        label = labels.get(decision.record_id)
        if label is not None and label.label is not None:
            new.human_label = label.label
            new.human_reason = label.reason
            new.human_actor = actor
        new.final_label = new.human_label or new.ensemble_label
        labeled.append(new)
    return labeled
```

- [ ] **Step 4: Cablear T/A.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.orchestration.hitl import DecisionFileError, GateResult, review_gate
```

por

```python
from revisia.orchestration.gates import apply_labels, ta_payload, ta_policy
from revisia.orchestration.hitl import (
    DecisionFileError,
    FlagPolicy,
    GateResult,
    RecordPolicy,
    review_gate,
)
```

sustituir `_Run.gate`

```python
    def gate(self, stage: str, payload: dict) -> GateResult:
        """Checkpoint humano de ``stage`` con la autonomía que fija el protocolo."""
        self.stage = stage
        return review_gate(
            stage=stage,
            autonomy=self.protocol.autonomy_for(stage),
            run_ctx=self.ctx,
            review_payload=payload,
            auto_approve=self.auto_approve,
        )
```

por

```python
    def gate(
        self,
        stage: str,
        payload: dict,
        *,
        records: RecordPolicy | None = None,
        flags: FlagPolicy | None = None,
        force_human: bool = False,
    ) -> GateResult:
        """Checkpoint humano de ``stage`` con la autonomía que fija el protocolo.

        ``records`` habilita la decisión por registro (cribado), ``flags`` la
        adjudicación de citas marcadas y ``force_human`` exige humano (M5).
        """
        self.stage = stage
        return review_gate(
            stage=stage,
            autonomy=self.protocol.autonomy_for(stage),
            run_ctx=self.ctx,
            review_payload=payload,
            auto_approve=self.auto_approve,
            records=records,
            flags=flags,
            force_human=force_human,
        )
```

y en `_run_stages`, sustituir

```python
    decisions = _screen_ta(run, deduped, _load_gold(run, gold_labels))
    passed = {d.record_id for d in decisions if d.final_label in {"include", "unclear"}}
    excluded_ta = sum(1 for d in decisions if d.final_label == "exclude")
    ta_payload = {
        "n_screened": len(deduped),
        "n_pass": len(passed),
        "n_excluded": excluded_ta,
        "pass_ids": sorted(passed),
    }
    if (stop := run.stop(run.gate("screening_ta", ta_payload), "screening_ta")) is not None:
        return stop
```

por

```python
    decisions = _screen_ta(run, deduped, _load_gold(run, gold_labels))
    ta_autonomy = protocol.autonomy_for("screening_ta")
    ta_gate = run.gate(
        "screening_ta",
        ta_payload(decisions=decisions, records=deduped, autonomy=ta_autonomy),
        records=ta_policy(decisions=decisions, records=deduped, autonomy=ta_autonomy),
    )
    if (stop := run.stop(ta_gate, "screening_ta")) is not None:
        return stop
    # D5: solo las etiquetas explícitas pasan a human_label; decisions.json se
    # reescribe con ellas (spec §4.2).
    decisions = apply_labels(decisions, ta_gate.labels, ta_gate.actor)
    run.ctx.write_json("03_screening/decisions.json", [d.model_dump() for d in decisions])
    passed = {d.record_id for d in decisions if d.final_label in {"include", "unclear"}}
    excluded_ta = sum(1 for d in decisions if d.final_label == "exclude")
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py tests/test_pipeline_fake.py tests/test_reanudacion.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 482 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/orchestration/gates.py revisia/orchestration/pipeline.py tests/test_hitl_pipeline.py
git commit -m "feat(pipeline): cribado T/A con decisión humana por registro (C1, D1, D5)" -m "La solicitud de screening_ta lista cada registro con la propuesta del ensemble y el voto de cada miembro; el revisor aprueba con excepciones (A1) o etiqueta todo (A0). apply_labels escribe human_label, human_reason y human_actor solo ante una etiqueta explícita: aprobar en bloque deja la exclusión como IA avalada. decisions.json se reescribe tras el gate. Funciones puras en orchestration/gates.py. Spec 2026-10-04 §4.3 y §8." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 23: Métricas sobre la propuesta IA y calidad en la solicitud T/A (D6, D7)

**Files:**
- Modify: `revisia/metrics.py` (docstring l.115-116; l.130-131)
- Modify: `revisia/orchestration/gates.py` (import l.14-16; función nueva antes de `ta_payload` y su firma, l.48-61; final de `ta_payload` l.78-82)
- Modify: `revisia/orchestration/pipeline.py` (llamada a `ta_payload` en `_run_stages`, l.1108)
- Test: `tests/test_hitl_pipeline.py` (imports l.6-7, l.14-15 y l.18; helper y tres tests nuevos al final)

**Interfaces:**
- Consumes: `ScreeningMetrics` (existente); `protocol.thresholds`.
- Produces:
  - `compute_screening_metrics` mide **siempre** `ensemble_label` (D6): un rescate humano no mejora el recall de la IA.
  - `ta_payload(*, decisions, records, autonomy, metrics: ScreeningMetrics | None = None, thresholds: Mapping[str, float] | None = None) -> dict` gana `quality` = `None` sin gold o `{recall, recall_target, kappa, kappa_min, gold_positives (tp + fn), recall_meets_target (None si falta algo)}` y `ai_excluded` = ids con `ensemble_label == "exclude"`, en orden de id (D7).

- [ ] **Step 1: Tests que fallan.** En `tests/test_hitl_pipeline.py`, sustituir

```python
import json
from pathlib import Path
```

por

```python
import json
import shutil
from pathlib import Path
```

sustituir

```python
from revisia.config import load_protocol
from revisia.orchestration import pipeline as pipeline_mod
```

por

```python
from revisia.config import load_protocol
from revisia.metrics import compute_screening_metrics
from revisia.orchestration import pipeline as pipeline_mod
```

sustituir

```python
from revisia.schemas.records import SearchRecord
```

por

```python
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision
```

y añadir al final del fichero:

```python


# ── Calidad de la propuesta IA (D6, D7) ──────────────────────────────────


def _proto_con_gold(tmp_path: Path) -> Path:
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)  # el demo declara recall_target: 0.95
    (proto / "gold.yml").write_text('gold:\n  "rec-1": true\n  "rec-2": true\n', "utf-8")
    return proto


def test_metricas_miden_la_propuesta_ia(tmp_path: Path, proveedor) -> None:
    # D6: un rescate humano no mejora el recall de la IA.
    rescatada = ScreeningDecision(
        record_id="x", ensemble_label="exclude", human_label="include", final_label="include"
    )
    metricas = compute_screening_metrics([rescatada], {"x": True})
    assert (metricas.tp, metricas.fn, metricas.recall) == (0, 1, 0.0)

    proto = _proto_con_gold(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    def rescatar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ta":
            return {"records": {"rec-2": {"label": "include", "reason": "relevante"}}}
        return None

    correr_hasta(
        protocol,
        proto,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        etiquetar=rescatar,
        parar_en="screening_ft",
    )
    assert _json(ctx, "03_screening/metrics.json")["recall"] == 0.5


def test_review_request_ta_informa_recall_y_exclusiones_ia(tmp_path: Path, proveedor) -> None:
    proto = _proto_con_gold(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(protocol, proto, ctx, search_fn=_busqueda)

    solicitud = leer_solicitud(ctx.run_dir, "screening_ta")
    assert solicitud["quality"] == {
        "recall": 0.5,
        "recall_target": 0.95,
        "kappa": 0.0,
        "kappa_min": None,
        "gold_positives": 2,
        "recall_meets_target": False,
    }
    assert solicitud["ai_excluded"] == ["rec-2"]


def test_review_request_ta_sin_gold_no_informa_calidad(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    solicitud = leer_solicitud(ctx.run_dir, "screening_ta")
    assert (solicitud["quality"], solicitud["ai_excluded"]) == (None, ["rec-2"])
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py -v`
Expected: FAIL `test_metricas_miden_la_propuesta_ia` (`assert (1, 0, 1.0) == (0, 1, 0.0)`: se medía `final_label`), `test_review_request_ta_informa_recall_y_exclusiones_ia` y `test_review_request_ta_sin_gold_no_informa_calidad` (`KeyError: 'quality'`).

- [ ] **Step 3: D6.** En `revisia/metrics.py` (`compute_screening_metrics`), sustituir

```python
    Args:
        decisions: decisiones del cribado (se usa ``final_label``/``ensemble_label``).
```

por

```python
    Args:
        decisions: decisiones del cribado; se mide ``ensemble_label``, la
            propuesta de la IA (D6): κ y recall evalúan el sistema, no al
            humano que lo corrige.
```

y

```python
        label = decision.final_label or decision.ensemble_label
        pred.append(label != "exclude")
```

por

```python
        # Nunca `final_label`: con etiquetas humanas mediría humano + IA (D6).
        pred.append(decision.ensemble_label != "exclude")
```

- [ ] **Step 4: D7.** En `revisia/orchestration/gates.py`, sustituir

```python
from collections.abc import Iterable, Mapping

from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
```

por

```python
from collections.abc import Iterable, Mapping

from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
```

sustituir

```python
def ta_payload(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    autonomy: str,
) -> dict:
    """Solicitud del gate ``screening_ta`` (spec §4.3).

    ``records`` ordenados por id, cada uno con la propuesta del ensemble y el
    voto de cada miembro; en A0 (``label_all``) todos van a ``must_label``.
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    by_id = {r.record_id: r for r in records}
    return {
```

por

```python
def _quality(metrics: ScreeningMetrics | None, thresholds: Mapping[str, float]) -> dict | None:
    """Calidad de la propuesta IA frente al gold y los umbrales del protocolo (D7)."""
    if metrics is None:
        return None
    recall_target = thresholds.get("recall_target")
    meets = None
    if metrics.recall is not None and recall_target is not None:
        meets = metrics.recall >= recall_target
    return {
        "recall": metrics.recall,
        "recall_target": recall_target,
        "kappa": metrics.cohen_kappa,
        "kappa_min": thresholds.get("kappa_min"),
        "gold_positives": metrics.tp + metrics.fn,
        "recall_meets_target": meets,
    }


def ta_payload(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    autonomy: str,
    metrics: ScreeningMetrics | None = None,
    thresholds: Mapping[str, float] | None = None,
) -> dict:
    """Solicitud del gate ``screening_ta`` (spec §4.3).

    ``records`` ordenados por id, cada uno con la propuesta del ensemble y el
    voto de cada miembro; en A0 (``label_all``) todos van a ``must_label``.
    ``quality`` (``None`` sin gold) y ``ai_excluded`` le dicen al revisor, antes
    de aprobar, si un recall bajo umbral bloqueará la publicación y qué
    exclusiones de la IA tendría que etiquetar para evitarlo (D7).
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    by_id = {r.record_id: r for r in records}
    return {
```

y

```python
        "must_label": [d.record_id for d in decisions] if autonomy == "A0" else [],
    }


def ta_policy(
```

por

```python
        "must_label": [d.record_id for d in decisions] if autonomy == "A0" else [],
        "quality": _quality(metrics, thresholds or {}),
        "ai_excluded": [d.record_id for d in decisions if d.ensemble_label == "exclude"],
    }


def ta_policy(
```

En `revisia/orchestration/pipeline.py` (`_run_stages`), sustituir

```python
        ta_payload(decisions=decisions, records=deduped, autonomy=ta_autonomy),
```

por

```python
        ta_payload(
            decisions=decisions,
            records=deduped,
            autonomy=ta_autonomy,
            metrics=run.metrics,
            thresholds=protocol.thresholds,
        ),
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py tests/test_metrics.py tests/test_pipeline_fake.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 485 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/metrics.py revisia/orchestration/gates.py revisia/orchestration/pipeline.py tests/test_hitl_pipeline.py
git commit -m "feat(screening): métricas sobre la propuesta IA y calidad en la solicitud T/A (D6, D7)" -m "compute_screening_metrics mide siempre ensemble_label: con etiquetas humanas, final_label mediría humano más IA. La solicitud de screening_ta lleva quality (recall, recall_target, kappa, kappa_min, positivos del gold, si alcanza el umbral) y ai_excluded: el revisor sabe antes de aprobar qué exclusiones de la IA tendría que etiquetar para que un recall bajo no bloquee la publicación. Spec 2026-10-04 §3 y §8." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 24: Gate FT por registro: `unclear` solo con humano, rescates y 16b humana (C1, D1, D2, D9)

**Files:**
- Modify: `revisia/orchestration/gates.py` (import l.16-19; dos funciones públicas y una privada antes de `apply_labels`, l.129)
- Modify: `revisia/orchestration/pipeline.py` (import l.69; `_FullTextStage` l.291-293; final de `_fulltext` l.573-575; `_build_counts` l.874-896; bloque FT de `_run_stages` l.1128-1150; llamada a `_build_counts` l.1175-1177)
- Modify: `tests/hitl_helpers.py` (función nueva antes de `correr_hasta`; docstring y bucle de `correr_hasta`)
- Test: `tests/test_hitl_pipeline.py` (imports l.12-13 y l.17-18; helpers y siete tests nuevos al final)

**Interfaces:**
- Consumes: `RetrievalOutcome` (PR-0); `_retrieve` (Tarea 12); `apply_labels` (Tarea 22).
- Produces:
  - `ft_payload(*, decisions, records, retrieval: Mapping[str, RetrievalOutcome], autonomy) -> dict` (§4.3): `mode`, `n_sought`, `n_retrieved`, `n_not_retrieved`, `records` ordenados por id con `{record_id, title, year, doi, fulltext, fulltext_reason, fulltext_source_url, proposal | null, confidence | null, rationale | null, criteria_violated}`, `must_label` (A0: todos los recuperados; A1: los `unclear`), `must_resolve` (los `unclear`) y `rescuable` (los no recuperados).
  - `ft_policy(*, decisions, records, retrieval, autonomy) -> RecordPolicy` (`must_label`, `must_resolve`, `rescue_ids` = no recuperados, `reason_on_exclude=True`; la nota de un no recuperado es su motivo).
  - `_FullTextStage(decisions, texts, retrieval: dict[str, RetrievalOutcome])` (sustituye `not_retrieved: int`).
  - Pipeline: tras aprobar FT, `apply_labels`; `04_fulltext/decisions.json` se reescribe; **solo `include`** llega a extracción (un `unclear` no aprobado por un humano nunca pasa); 16b, `ft_exclusion_reasons` y el desglose usan las decisiones etiquetadas. `_build_counts(*, ..., ft_decisions, ...)`: `fulltext_not_retrieved` = no recuperados sin etiqueta humana, `fulltext_rescued` = no recuperados con etiqueta, `fulltext_assessed = sought − not_retrieved` (relación 8 de §4.4).
  - `tests/hitl_helpers.aceptar_lo_obligatorio(stage: str, solicitud: dict) -> dict | None`: etiqueta cada id de `must_label ∪ must_resolve` con la propuesta IA (`include` si es `unclear` o no hay) y razón; `None` si no hay nada obligatorio. `correr_hasta` la usa cuando `etiquetar` falta o devuelve `None`.

Por qué cambia `tests/hitl_helpers.py`: con FT en A0 (el default del demo) aprobar exige etiquetar cada recuperado; sin una respuesta por defecto que lo haga, todos los tests que usan `correr_hasta` hasta el final darían `DecisionFileError`.

- [ ] **Step 1: Tests que fallan.** En `tests/test_hitl_pipeline.py`, sustituir

```python
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import correr_hasta, leer_solicitud
```

por

```python
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible
from hitl_helpers import correr_hasta, leer_solicitud, responder_gate
```

sustituir

```python
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.pipeline import run_pipeline
```

por

```python
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.hitl import DecisionFileError
from revisia.orchestration.pipeline import run_pipeline
```

y añadir al final del fichero:

```python


# ── Cribado a texto completo (C1, D1, D2, D9) ────────────────────────────


def _busqueda_ft(query: str, n: int) -> list[SearchRecord]:
    """Dos registros que pasan T/A; lo que decide FT lo pone el texto completo."""
    return [
        SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex"),
        SearchRecord(record_id="rec-2", title="Active learning", source_db="OpenAlex"),
    ][:n]


def _texto(**extra: str):
    """``fetch_fn`` que añade texto al de ``fetch_disponible`` (p. ej. "dudoso")."""

    def fetch(record: SearchRecord):
        ft = fetch_disponible(record)
        ft.text += " " + extra.get(record.record_id.replace("-", "_"), "")
        return ft

    return fetch


def _proto(tmp_path: Path, **autonomy: str) -> Path:
    proto = tmp_path / "proto"
    shutil.copytree(EXAMPLE, proto)
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["autonomy"].update(autonomy)
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), "utf-8")
    return proto


def _ft(ctx: RunContext) -> dict[str, dict]:
    return _por_id(ctx, "04_fulltext/decisions.json")


def test_ft_unclear_sin_resolver_impide_aprobar(tmp_path: Path, proveedor) -> None:
    # C1: hasta la Ola 1 un `unclear` de FT entraba en extracción y en los incluidos.
    proto = _proto(tmp_path, screening_ft="A1")
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    fetch = _texto(rec_1="Resultado dudoso.")
    correr_hasta(
        protocol, proto, ctx, search_fn=_busqueda_ft, fetch_fn=fetch, parar_en="screening_ft"
    )
    solicitud = leer_solicitud(ctx.run_dir, "screening_ft")
    assert (solicitud["must_resolve"], solicitud["must_label"]) == (["rec-1"], ["rec-1"])

    responder_gate(ctx.run_dir, "screening_ft")  # aprueba sin resolver el unclear
    with pytest.raises(DecisionFileError, match=r"rec-1 \(1 en total\)"):
        run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), fetch_fn=fetch)

    responder_gate(
        ctx.run_dir, "screening_ft", records={"rec-1": {"label": "include", "reason": "cumple"}}
    )
    result = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), fetch_fn=fetch)
    assert result.stage == "extraccion"
    assert _ft(ctx)["rec-1"]["final_label"] == "include"


def test_auto_approve_no_resuelve_unclear_ft(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    result = run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        auto_approve=True,
        search_fn=_busqueda_ft,
        fetch_fn=_texto(rec_2="Caso dudoso."),
    )
    assert (result.status, result.stage) == ("paused", "screening_ft")
    assert "`unclear` solo los resuelve un humano" in result.message


def test_ft_a0_pipeline_exige_etiquetar_los_recuperados(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)  # FT en A0 por defecto
    ctx = RunContext(protocol.slug, tmp_path, "T")
    fetch = fetch_no_disponible(["rec-2"])
    correr_hasta(
        protocol, EXAMPLE, ctx, search_fn=_busqueda_ft, fetch_fn=fetch, parar_en="screening_ft"
    )
    solicitud = leer_solicitud(ctx.run_dir, "screening_ft")
    assert (solicitud["mode"], solicitud["must_label"], solicitud["rescuable"]) == (
        "label_all",
        ["rec-1"],
        ["rec-2"],
    )
    assert (solicitud["n_sought"], solicitud["n_retrieved"], solicitud["n_not_retrieved"]) == (
        2,
        1,
        1,
    )
    no_recuperado = solicitud["records"][1]
    assert (no_recuperado["fulltext"], no_recuperado["fulltext_reason"]) == (
        "not_retrieved",
        "no_disponible",
    )
    assert no_recuperado["proposal"] is None and no_recuperado["confidence"] is None

    responder_gate(ctx.run_dir, "screening_ft")
    with pytest.raises(DecisionFileError, match=r"rec-1 \(1 en total\)"):
        run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)


def test_ft_a0_exclusion_humana_en_todos(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def etiquetar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {
                "records": {
                    "rec-1": {"label": "include", "reason": "cumple"},
                    "rec-2": {"label": "exclude", "reason": "población no elegible"},
                }
            }
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
        etiquetar=etiquetar,
    )

    assert result.status == "completed"
    c = result.counts
    assert (c.excluded_ft, c.excluded_ft_human, c.excluded_ft_ai, c.included) == (1, 1, 0, 1)
    assert all(d["human_label"] for d in _ft(ctx).values())  # A0: todo recuperado etiquetado
    assert _ft(ctx)["rec-2"]["human_actor"] == "human:revisora"


def test_rescate_de_no_recuperado_cuenta_como_evaluado(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def rescatar(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {
                "records": {
                    "rec-1": {"label": "include", "reason": "cumple"},
                    "rec-2": {"label": "include", "reason": "PDF por préstamo interbibliotecario"},
                }
            }
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_no_disponible(["rec-2"]),
        etiquetar=rescatar,
    )

    c = result.counts
    assert (c.fulltext_sought, c.fulltext_not_retrieved, c.fulltext_rescued) == (2, 0, 1)
    assert (c.fulltext_assessed, c.included) == (2, 2)
    rec2 = _ft(ctx)["rec-2"]
    assert (rec2["fulltext_status"], rec2["votes"], rec2["final_label"]) == (
        "not_retrieved",
        [],
        "include",
    )
    rescate = next(e for e in ctx.ledger.read_all() if e.target == "rec-2")
    assert (rescate.action, rescate.detail["rescue"], rescate.detail["from"]) == (
        "label",
        True,
        None,
    )


def test_no_recuperado_sin_rescate_permite_aprobar(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_no_disponible(["rec-2"]),
    )
    c = result.counts
    assert result.status == "completed"
    assert (c.fulltext_not_retrieved, c.fulltext_rescued, c.fulltext_assessed) == (1, 0, 1)
    assert c.included == 1
    assert _ft(ctx)["rec-2"]["final_label"] is None


def test_16b_razon_humana(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    def excluir(stage: str, _solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return {
                "records": {
                    "rec-1": {"label": "include", "reason": "cumple"},
                    "rec-2": {"label": "exclude", "reason": "diseño no elegible"},
                }
            }
        return None

    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
        etiquetar=excluir,
    )
    assert result.counts.ft_exclusion_reasons == {"diseño no elegible": 1}
    (excluido,) = _json(ctx, "04_fulltext/excluded.json")
    assert (excluido["record_id"], excluido["reason_source"]) == ("rec-2", "human")
    md = (ctx.run_dir / "deliverable" / "excluidos_texto_completo.md").read_text("utf-8")
    assert "diseño no elegible | humano |" in md
```

En `tests/hitl_helpers.py`, sustituir

```python
def correr_hasta(
```

por

```python
def aceptar_lo_obligatorio(stage: str, solicitud: dict) -> dict | None:
    """Etiqueta lo obligatorio de un gate de cribado con la propuesta de la IA.

    Responde como una revisora que revisa cada registro de ``must_label`` y
    ``must_resolve`` y coincide con la IA; un ``unclear`` (o un registro sin
    propuesta) lo incluye. Sin nada obligatorio, ``None`` (aprobar sin más).
    """
    obligatorios = sorted(
        set(solicitud.get("must_label", [])) | set(solicitud.get("must_resolve", []))
    )
    if not obligatorios:
        return None
    propuestas = {r["record_id"]: r.get("proposal") for r in solicitud.get("records", [])}
    return {
        "records": {
            rid: {
                "label": p if (p := propuestas.get(rid)) in ("include", "exclude") else "include",
                "reason": "revisado: de acuerdo con la propuesta",
            }
            for rid in obligatorios
        }
    }


def correr_hasta(
```

en la docstring de `correr_hasta`, sustituir

```python
    En cada pausa (salvo en ``parar_en``, donde devuelve el resultado) escribe
    ``decision.yml`` con ``responder_gate``. ``etiquetar(stage, solicitud)``
    devuelve los argumentos extra de ``responder_gate`` para ese gate
    (``{"records": …}``, ``{"approved": False, "reason": …}``…) o ``None`` para
    aprobar sin más. La primera vuelta usa ``ctx``; las siguientes reabren la
    carpeta con ``RunContext.open``, como ``revisia run --resume``.
```

por

```python
    En cada pausa (salvo en ``parar_en``, donde devuelve el resultado) escribe
    ``decision.yml`` con ``responder_gate``. ``etiquetar(stage, solicitud)``
    devuelve los argumentos extra de ``responder_gate`` para ese gate
    (``{"records": …}``, ``{"approved": False, "reason": …}``…) o ``None``; con
    ``None`` (o sin ``etiquetar``) se responde con ``aceptar_lo_obligatorio``,
    que etiqueta lo que el gate exige y, si no exige nada, aprueba sin más. La
    primera vuelta usa ``ctx``; las siguientes reabren la carpeta con
    ``RunContext.open``, como ``revisia run --resume``.
```

y en su bucle, sustituir

```python
        extra = (
            etiquetar(result.stage, leer_solicitud(ctx.run_dir, result.stage))
            if etiquetar
            else None
        )
        responder_gate(ctx.run_dir, result.stage, **(extra or {}))
```

por

```python
        solicitud = leer_solicitud(ctx.run_dir, result.stage)
        extra = etiquetar(result.stage, solicitud) if etiquetar else None
        if extra is None:
            extra = aceptar_lo_obligatorio(result.stage, solicitud)
        responder_gate(ctx.run_dir, result.stage, **(extra or {}))
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py -v`
Expected: FAIL `test_ft_unclear_sin_resolver_impide_aprobar` (`KeyError: 'must_resolve'`), `test_auto_approve_no_resuelve_unclear_ft` (`('completed', None) == ('paused', 'screening_ft')`: el `unclear` pasa), `test_ft_a0_pipeline_exige_etiquetar_los_recuperados` (`KeyError: 'mode'`) y `test_ft_a0_exclusion_humana_en_todos`, `test_rescate_de_no_recuperado_cuenta_como_evaluado` y `test_16b_razon_humana` (`DecisionFileError: … `records` solo vale en los gates de cribado`: el gate FT aún no tiene `RecordPolicy`). `test_no_recuperado_sin_rescate_permite_aprobar` ya pasa (guardia).

- [ ] **Step 3: Solicitud y política FT.** En `revisia/orchestration/gates.py`, sustituir

```python
from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision
```

por

```python
from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
from revisia.schemas.artifacts import RetrievalOutcome
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision
```

y sustituir

```python
def apply_labels(
```

por

```python
def _ft_requirements(
    decisions: list[ScreeningDecision], autonomy: str
) -> tuple[list[str], list[str], list[str]]:
    """``(must_label, must_resolve, rescuable)`` del gate de texto completo (D1, D2)."""
    retrieved = [d.record_id for d in decisions if d.fulltext_status == "retrieved"]
    unclear = [d.record_id for d in decisions if d.ensemble_label == "unclear"]
    rescuable = [d.record_id for d in decisions if d.fulltext_status == "not_retrieved"]
    must_label = retrieved if autonomy == "A0" else unclear
    return must_label, unclear, rescuable


def ft_payload(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    retrieval: Mapping[str, RetrievalOutcome],
    autonomy: str,
) -> dict:
    """Solicitud del gate ``screening_ft`` (spec §4.3).

    Un registro por informe buscado, recuperado o no. ``must_label`` son todos
    los recuperados en A0 y solo los ``unclear`` en A1; ``must_resolve``, los
    ``unclear`` (nunca pasan sin humano); ``rescuable``, los no recuperados, que
    el humano puede evaluar si consiguió el texto por otra vía (D2).
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    by_id = {r.record_id: r for r in records}
    must_label, must_resolve, rescuable = _ft_requirements(decisions, autonomy)
    rows = []
    for d in decisions:
        vote = d.votes[0] if d.votes else None
        outcome = retrieval.get(d.record_id)
        rows.append(
            {
                "record_id": d.record_id,
                "title": by_id[d.record_id].title,
                "year": by_id[d.record_id].year,
                "doi": by_id[d.record_id].doi,
                "fulltext": d.fulltext_status,
                "fulltext_reason": outcome.reason if outcome else None,
                "fulltext_source_url": outcome.source_url if outcome else None,
                "proposal": d.ensemble_label,
                "confidence": vote.confidence if vote else None,
                "rationale": vote.rationale if vote else None,
                "criteria_violated": list(vote.criteria_violated) if vote else [],
            }
        )
    return {
        "mode": _mode(autonomy),
        "n_sought": len(decisions),
        "n_retrieved": sum(1 for d in decisions if d.fulltext_status == "retrieved"),
        "n_not_retrieved": len(rescuable),
        "records": rows,
        "must_label": must_label,
        "must_resolve": must_resolve,
        "rescuable": rescuable,
    }


def ft_policy(
    *,
    decisions: Iterable[ScreeningDecision],
    records: Iterable[SearchRecord],
    retrieval: Mapping[str, RetrievalOutcome],
    autonomy: str,
) -> RecordPolicy:
    """Qué puede y debe etiquetar el humano en FT (D1, D2, D9).

    Excluir exige razón (va a la lista 16b) y etiquetar un no recuperado es un
    rescate, también con razón.
    """
    decisions = sorted(decisions, key=lambda d: d.record_id)
    titles = {r.record_id: r.title for r in records}
    must_label, must_resolve, rescuable = _ft_requirements(decisions, autonomy)
    hints = []
    for d in decisions:
        note = _note(d)
        outcome = retrieval.get(d.record_id)
        if d.fulltext_status == "not_retrieved" and outcome is not None:
            note = f"no recuperado: {outcome.reason} ({outcome.detail or 'sin detalle'})"
        hints.append(
            RecordHint(d.record_id, titles.get(d.record_id, d.record_id), d.ensemble_label, note)
        )
    return RecordPolicy(
        hints=tuple(hints),
        must_label=frozenset(must_label),
        must_resolve=frozenset(must_resolve),
        rescue_ids=frozenset(rescuable),
        reason_on_exclude=True,
    )


def apply_labels(
```

- [ ] **Step 4: Cablear FT y los conteos.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.orchestration.gates import apply_labels, ta_payload, ta_policy
```

por

```python
from revisia.orchestration.gates import (
    apply_labels,
    ft_payload,
    ft_policy,
    ta_payload,
    ta_policy,
)
```

en `_FullTextStage`, sustituir

```python
    decisions: list[ScreeningDecision]
    texts: dict[str, str]
    not_retrieved: int
```

por

```python
    decisions: list[ScreeningDecision]
    texts: dict[str, str]
    retrieval: dict[str, RetrievalOutcome]
```

al final de `_fulltext`, sustituir

```python
    run.ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])
    not_retrieved = sum(1 for d in ft_decisions if d.fulltext_status == "not_retrieved")
    return _FullTextStage(ft_decisions, fulltexts, not_retrieved)
```

por

```python
    run.ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])
    return _FullTextStage(ft_decisions, fulltexts, outcomes)
```

en `_build_counts`, sustituir

```python
    passed_ta: list[SearchRecord],
    ft: _FullTextStage,
    excluded_ft: int,
```

por

```python
    passed_ta: list[SearchRecord],
    ft_decisions: list[ScreeningDecision],
    excluded_ft: int,
```

sustituir

```python
    """Conteos PRISMA 2020 de la corrida (diagrama, tabla, CSV y manifiesto)."""
    identified_by_source: dict[str, int] = {}
```

por

```python
    """Conteos PRISMA 2020 de la corrida (diagrama, tabla, CSV y manifiesto).

    Un no recuperado que el humano rescató (D2) cuenta como evaluado; uno sin
    rescate, como no recuperado (spec §4.4, relación 8).
    """
    not_retrieved = [d for d in ft_decisions if d.fulltext_status == "not_retrieved"]
    unrescued = sum(1 for d in not_retrieved if d.human_label is None)
    identified_by_source: dict[str, int] = {}
```

y

```python
        fulltext_not_retrieved=ft.not_retrieved,
        fulltext_rescued=0,  # los rescates humanos llegan con el HITL por registro (PR-D)
        fulltext_assessed=len(passed_ta) - ft.not_retrieved,
```

por

```python
        fulltext_not_retrieved=unrescued,
        fulltext_rescued=len(not_retrieved) - unrescued,
        fulltext_assessed=len(passed_ta) - unrescued,
```

en `_run_stages`, sustituir el bloque FT

```python
    ft = _fulltext(run, passed_ta, fetch_fn)
    # Hasta PR-D un `unclear` de FT sigue pasando (lo resolverá un humano, D1).
    included_ids = {d.record_id for d in ft.decisions if d.final_label in {"include", "unclear"}}
    excluded_ft = sum(1 for d in ft.decisions if d.final_label == "exclude")
    ft_payload = {
        "n_buscados": len(passed_ta),
        "n_no_recuperados": ft.not_retrieved,
        "n_evaluados": len(passed_ta) - ft.not_retrieved,
        "n_incluidos": len(included_ids),
        "n_excluidos": excluded_ft,
    }
    if (stop := run.stop(run.gate("screening_ft", ft_payload), "screening_ft")) is not None:
        return stop
    included = [r for r in passed_ta if r.record_id in included_ids]

    # Desglose de exclusiones humano vs IA (PRISMA-trAIce) sobre ambas fases; el
    # de solo T/A alimenta la nota ** del flow diagram oficial (trAIce R1).
    exclusion_breakdown = compute_exclusion_breakdown(decisions + ft.decisions)
    run.ctx.write_json("03_screening/exclusions.json", exclusion_breakdown.model_dump())
    ta_breakdown = compute_exclusion_breakdown(decisions)
    # Informes excluidos en elegibilidad (16b) y sus razones (cajas "Reason 1..n"
    # del flow oficial): una sola lista para el diagrama, la tabla y el auditor.
    excluded_reports = compute_ft_excluded(ft.decisions, passed_ta)
```

por

```python
    ft = _fulltext(run, passed_ta, fetch_fn)
    ft_autonomy = protocol.autonomy_for("screening_ft")
    ft_gate = run.gate(
        "screening_ft",
        ft_payload(
            decisions=ft.decisions, records=passed_ta, retrieval=ft.retrieval, autonomy=ft_autonomy
        ),
        records=ft_policy(
            decisions=ft.decisions, records=passed_ta, retrieval=ft.retrieval, autonomy=ft_autonomy
        ),
    )
    if (stop := run.stop(ft_gate, "screening_ft")) is not None:
        return stop
    # Un `unclear` nunca pasa sin etiqueta humana (D1, D9) y un rescate entra como
    # evaluado por humano (D2): solo `include` llega a extracción.
    ft_decisions = apply_labels(ft.decisions, ft_gate.labels, ft_gate.actor)
    run.ctx.write_json("04_fulltext/decisions.json", [d.model_dump() for d in ft_decisions])
    included_ids = {d.record_id for d in ft_decisions if d.final_label == "include"}
    excluded_ft = sum(1 for d in ft_decisions if d.final_label == "exclude")
    included = [r for r in passed_ta if r.record_id in included_ids]

    # Desglose de exclusiones humano vs IA (PRISMA-trAIce) sobre ambas fases; el
    # de solo T/A alimenta la nota ** del flow diagram oficial (trAIce R1).
    exclusion_breakdown = compute_exclusion_breakdown(decisions + ft_decisions)
    run.ctx.write_json("03_screening/exclusions.json", exclusion_breakdown.model_dump())
    ta_breakdown = compute_exclusion_breakdown(decisions)
    # Informes excluidos en elegibilidad (16b) y sus razones (cajas "Reason 1..n"
    # del flow oficial): una sola lista para el diagrama, la tabla y el auditor.
    excluded_reports = compute_ft_excluded(ft_decisions, passed_ta)
```

y en la llamada a `_build_counts`, sustituir

```python
        passed_ta=passed_ta,
        ft=ft,
        excluded_ft=excluded_ft,
```

por

```python
        passed_ta=passed_ta,
        ft_decisions=ft_decisions,
        excluded_ft=excluded_ft,
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py tests/test_pipeline_fake.py tests/test_reanudacion.py -v`
Expected: PASS (los tests de PR-B y PR-C con `--auto-approve` siguen en verde: D9 no exige la completitud de A0).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 492 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/orchestration/gates.py revisia/orchestration/pipeline.py tests/hitl_helpers.py tests/test_hitl_pipeline.py
git commit -m "feat(pipeline): cribado a texto completo por registro con rescates (C1, D1, D2, D9)" -m "La solicitud de screening_ft lista cada informe buscado con su recuperación y la propuesta IA; en A0 hay que etiquetar cada recuperado y un unclear solo lo resuelve un humano (con --auto-approve, pausa). Solo include llega a extracción: hasta ahora un unclear entraba en extracción y en los incluidos. Un no recuperado se puede rescatar con razón y cuenta como evaluado por humano; la razón humana va a la lista 16b y a las cajas de exclusión. Spec 2026-10-04 §4.4 y §8." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 25: Extracción y RoB se aprueban con la tabla completa y el hash del artefacto (D1)

**Files:**
- Modify: `revisia/orchestration/gates.py` (imports l.16-20; dos funciones nuevas antes de `apply_labels`, l.222)
- Modify: `revisia/orchestration/pipeline.py` (import l.69-75; gates de extracción y RoB en `_run_stages`, l.1173-1180)
- Test: `tests/test_hitl_pipeline.py` (import l.19-20; dos tests nuevos al final)

**Interfaces:**
- Consumes: `ExtractionAgreement`, `ExtractionRecord`, `RoBAssessment`; `canonical_sha256`.
- Produces:
  - `extraction_payload(*, included, extractions: Mapping[str, ExtractionRecord], agreement: ExtractionAgreement | None) -> dict` (§4.3): `n_studies`, `studies[{record_id, title, fields{key: {value, source_quote, status, confidence}}}]`, `second_extraction{n_studies, n_field_pairs, value_agreement, presence_kappa} | None`, `artifact_sha256 = canonical_sha256({id: extracción.model_dump(mode="json")})` (= `canonical_sha256` de `05_extraction/extractions.json` leído).
  - `rob_payload(*, tool, included, assessments: Mapping[str, RoBAssessment]) -> dict` (§4.3): `tool`, `n_studies`, `studies[{record_id, title, overall, domains[{domain, judgment, rationale, support_quote}]}]`, `artifact_sha256` de `07_rob/assessments.json`.
  - `records` en `extraccion`/`rob` sigue siendo un error (`DecisionFileError`, Tarea 20): se aprueban por etapa (D1).

- [ ] **Step 1: Tests que fallan.** En `tests/test_hitl_pipeline.py`, sustituir

```python
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
```

por

```python
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.provenance.runmeta import canonical_sha256
```

y añadir al final del fichero:

```python


# ── Extracción y RoB: aprobación por etapa con la tabla completa (D1) ─────


def test_extraccion_y_rob_payload_con_tabla_y_hash_del_artefacto(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, EXAMPLE, ctx, parar_en="extraccion", **kwargs)

    solicitud = leer_solicitud(ctx.run_dir, "extraccion")
    extracciones = _json(ctx, "05_extraction/extractions.json")
    assert solicitud["n_studies"] == 2
    assert [s["record_id"] for s in solicitud["studies"]] == ["rec-1", "rec-2"]
    for estudio in solicitud["studies"]:
        campos = extracciones[estudio["record_id"]]["fields"]
        assert estudio["fields"] == {
            k: {x: v[x] for x in ("value", "source_quote", "status", "confidence")}
            for k, v in campos.items()
        }
    assert set(solicitud["second_extraction"]) == {
        "n_studies",
        "n_field_pairs",
        "value_agreement",
        "presence_kappa",
    }
    assert solicitud["artifact_sha256"] == canonical_sha256(extracciones)

    correr_hasta(protocol, EXAMPLE, RunContext.open(ctx.run_dir), parar_en="rob", **kwargs)
    solicitud = leer_solicitud(ctx.run_dir, "rob")
    evaluaciones = _json(ctx, "07_rob/assessments.json")
    assert (solicitud["tool"], solicitud["n_studies"]) == ("RoB2", 2)
    rec1 = solicitud["studies"][0]
    assert rec1["overall"] == evaluaciones["rec-1"]["overall"]
    assert len(rec1["domains"]) == len(evaluaciones["rec-1"]["domains"])
    assert solicitud["artifact_sha256"] == canonical_sha256(evaluaciones)


def test_records_en_extraccion_es_error(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
        parar_en="extraccion",
    )
    responder_gate(ctx.run_dir, "extraccion", records={"rec-1": {"label": "exclude"}})
    with pytest.raises(DecisionFileError, match="`records` solo vale"):
        run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py -v`
Expected: FAIL `test_extraccion_y_rob_payload_con_tabla_y_hash_del_artefacto` (`KeyError: 'n_studies'`). `test_records_en_extraccion_es_error` ya pasa desde la Tarea 20 (guardia del cableado).

- [ ] **Step 3: Implementar.** En `revisia/orchestration/gates.py`, sustituir

```python
from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
from revisia.schemas.artifacts import RetrievalOutcome
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningDecision
```

por

```python
from revisia.extraction_agreement import ExtractionAgreement
from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
from revisia.provenance.runmeta import canonical_sha256
from revisia.schemas.artifacts import RetrievalOutcome
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.records import SearchRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision
```

y sustituir

```python
def apply_labels(
```

por

```python
def extraction_payload(
    *,
    included: Iterable[SearchRecord],
    extractions: Mapping[str, ExtractionRecord],
    agreement: ExtractionAgreement | None,
) -> dict:
    """Solicitud del gate ``extraccion``: la tabla completa por estudio (D1).

    Se aprueba por etapa; ``artifact_sha256`` ata la aprobación al contenido de
    ``05_extraction/extractions.json`` (``canonical_sha256``).
    """
    included = list(included)
    return {
        "n_studies": len(included),
        "studies": [
            {
                "record_id": r.record_id,
                "title": r.title,
                "fields": {
                    key: {
                        "value": f.value,
                        "source_quote": f.source_quote,
                        "status": f.status,
                        "confidence": f.confidence,
                    }
                    for key, f in extractions[r.record_id].fields.items()
                },
            }
            for r in included
        ],
        "second_extraction": (
            None
            if agreement is None
            else {
                "n_studies": agreement.n_studies,
                "n_field_pairs": agreement.n_field_pairs,
                "value_agreement": agreement.value_agreement,
                "presence_kappa": agreement.presence_kappa,
            }
        ),
        "artifact_sha256": canonical_sha256(
            {k: v.model_dump(mode="json") for k, v in extractions.items()}
        ),
    }


def rob_payload(
    *,
    tool: str,
    included: Iterable[SearchRecord],
    assessments: Mapping[str, RoBAssessment],
) -> dict:
    """Solicitud del gate ``rob``: dominios y juicio por estudio (D1).

    ``artifact_sha256`` ata la aprobación al contenido de
    ``07_rob/assessments.json``.
    """
    included = list(included)
    return {
        "tool": tool,
        "n_studies": len(included),
        "studies": [
            {
                "record_id": r.record_id,
                "title": r.title,
                "overall": assessments[r.record_id].overall,
                "domains": [
                    {
                        "domain": d.domain,
                        "judgment": d.judgment,
                        "rationale": d.rationale,
                        "support_quote": d.support_quote,
                    }
                    for d in assessments[r.record_id].domains
                ],
            }
            for r in included
        ],
        "artifact_sha256": canonical_sha256(
            {k: v.model_dump(mode="json") for k, v in assessments.items()}
        ),
    }


def apply_labels(
```

En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.orchestration.gates import (
    apply_labels,
    ft_payload,
    ft_policy,
    ta_payload,
    ta_policy,
)
```

por

```python
from revisia.orchestration.gates import (
    apply_labels,
    extraction_payload,
    ft_payload,
    ft_policy,
    rob_payload,
    ta_payload,
    ta_policy,
)
```

y en `_run_stages`, sustituir

```python
    extraction_gate = run.gate("extraccion", {"n_extraidos": len(extractions)})
    if (stop := run.stop(extraction_gate, "extraccion")) is not None:
        return stop
    run.stage = "rob"
    assessments = _assess_rob(run, included, extractions, ft.texts)
    rob_gate = run.gate("rob", {"n_evaluados": len(assessments), "tool": protocol.rob_tool})
    if (stop := run.stop(rob_gate, "rob")) is not None:
        return stop
```

por

```python
    # Extracción y RoB se aprueban por etapa (D1): la solicitud lleva la tabla
    # completa por estudio y el hash del artefacto aprobado.
    extraction_gate = run.gate(
        "extraccion",
        extraction_payload(
            included=included, extractions=extractions, agreement=extraction_agreement
        ),
    )
    if (stop := run.stop(extraction_gate, "extraccion")) is not None:
        return stop
    run.stage = "rob"
    assessments = _assess_rob(run, included, extractions, ft.texts)
    rob_gate = run.gate(
        "rob", rob_payload(tool=protocol.rob_tool, included=included, assessments=assessments)
    )
    if (stop := run.stop(rob_gate, "rob")) is not None:
        return stop
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 494 recogidos.

- [ ] **Step 5: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/gates.py revisia/orchestration/pipeline.py tests/test_hitl_pipeline.py
git commit -m "feat(pipeline): extracción y RoB con la tabla completa y el hash del artefacto (D1)" -m "Las solicitudes de extraccion y rob listan cada estudio con sus campos o sus dominios, el acuerdo de la doble extracción y el canonical_sha256 del artefacto aprobado (extractions.json, assessments.json): la aprobación por etapa queda atada a lo que el humano vio. Spec 2026-10-04 §4.3 y §8." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 26: Gate final forzado a humano con citas marcadas y adjudicación por cita (M5, D8)

**Files:**
- Modify: `revisia/orchestration/gates.py` (imports l.18-19 y l.24; tres funciones nuevas antes de `apply_labels`, l.310)
- Modify: `revisia/orchestration/pipeline.py` (import l.72-77; función nueva antes de `run_pipeline` l.1026; gate `reporte` en `_run_stages` l.1224-1234; `write_manifest` l.1257-1258)
- Modify: `tests/hitl_helpers.py` (`responder_gate`: firma y docstring l.38-44; l.52-54)
- Test: `tests/test_hitl_pipeline.py` (imports l.20-21; fixture, helper y dos tests nuevos al final)

**Interfaces:**
- Consumes: `FlaggedClaim`, `FlagPolicy`, `force_human` (Tarea 20); `VerificationReport`, `CitationCheck`; `sha256_text`.
- Produces:
  - `report_payload(*, included, verification: VerificationReport, documento: str, grounding_mode: str, forced_human: bool) -> dict` (§4.3): `forced_human`, `forced_reason` (`"hallucination_flagged"` | `None`), `n_included`, `included` (ids), `verification{mode, n_checks, n_flagged, hallucination_flagged, flagged[{index, cited_id, claim (≤ 300 car.), note}]}` con `index` = posición en `verification.json.checks`, `must_adjudicate` (todos los índices marcados), `documento_sha256 = sha256_text(documento.md)`.
  - `report_policy(verification) -> FlagPolicy | None` (`None` sin marcas; `claim` también recortado a 300).
  - `pipeline._autonomy_effective(protocol, *, forced_human: bool) -> dict[str, str]`: autonomía de cada gate de `GATED_STAGES`, con `reporte` en A1 si está forzado y se declaró A2/A3.
  - Con `verification.hallucination_flagged`, el gate `reporte` se llama con `force_human=True` y la `FlagPolicy`; `manifest.yml` lleva `final_gate: {forced_human: true, reason: "hallucination_flagged"}` y `autonomy_effective.reporte` efectiva.
  - `tests/hitl_helpers.responder_gate(..., flags: dict[str, dict] | None = None)` (aditivo).

- [ ] **Step 1: Tests que fallan.** En `tests/hitl_helpers.py`, sustituir

```python
    records: dict[str, dict] | None = None,
) -> Path:
    """Escribe ``decision.yml`` para la solicitud vigente de ``stage``.

    Toma el ``request_sha256`` de ``review_request.yml``. ``records`` va tal
    cual (``{id: {label, reason}}``, cribado por registro, PR-D).
    """
```

por

```python
    records: dict[str, dict] | None = None,
    flags: dict[str, dict] | None = None,
) -> Path:
    """Escribe ``decision.yml`` para la solicitud vigente de ``stage``.

    Toma el ``request_sha256`` de ``review_request.yml``. ``records`` va tal
    cual (``{id: {label, reason}}``, cribado por registro) y ``flags`` también
    (``{índice: {verdict, reason}}``, citas marcadas del reporte; PR-D).
    """
```

y

```python
    if records is not None:
        decision["records"] = records
    path = Path(run_dir) / stage / "decision.yml"
```

por

```python
    if records is not None:
        decision["records"] = records
    if flags is not None:
        decision["flags"] = flags
    path = Path(run_dir) / stage / "decision.yml"
```

En `tests/test_hitl_pipeline.py`, sustituir

```python
from revisia.orchestration.run_context import RunContext
from revisia.provenance.runmeta import canonical_sha256
```

por

```python
from revisia.orchestration.run_context import RunContext
from revisia.orchestration.snapshot import read_run_info
from revisia.provenance.ledger import summarize_gates
from revisia.provenance.runmeta import canonical_sha256
```

y añadir al final del fichero:

```python


# ── Gate final con citas marcadas (M5, D8) ───────────────────────────────


@pytest.fixture()
def con_cita_inventada(monkeypatch: pytest.MonkeyPatch) -> ScriptedProvider:
    """Síntesis con una cita real y otra que no está en el corpus (``[2019]``)."""
    guion = ScriptedProvider(sintesis="La IA reduce el cribado [rec-1]. Lo confirma [2019].")
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: guion)
    return guion


def _proto_reporte(tmp_path: Path) -> Path:
    proto = _proto(tmp_path, reporte="A2")  # el gate final ni siquiera pausaría
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw["grounding"] = "existence"  # solo se comprueba que el id esté en el corpus
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), "utf-8")
    return proto


def test_gate_final_forzado_a_humano_si_hallucination_flagged(
    tmp_path: Path, con_cita_inventada
) -> None:
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")

    result = run_pipeline(
        protocol,
        proto,
        ctx,
        auto_approve=True,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
    )

    assert (result.status, result.stage) == ("paused", "reporte")
    assert "exige una decisión humana" in result.message
    solicitud = leer_solicitud(ctx.run_dir, "reporte")
    assert solicitud["autonomy"] == "A1"  # A2 declarada, A1 efectiva
    assert (solicitud["forced_human"], solicitud["forced_reason"]) == (
        True,
        "hallucination_flagged",
    )
    (marca,) = solicitud["verification"]["flagged"]
    assert (marca["cited_id"], solicitud["must_adjudicate"]) == ("2019", [marca["index"]])
    assert solicitud["verification"]["mode"] == "existence"
    manifest = yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["final_gate"] == {"forced_human": True, "reason": "hallucination_flagged"}
    assert manifest["autonomy_effective"]["reporte"] == "A1"
    assert not [e for e in ctx.ledger.read_all() if e.stage == "reporte"]


def test_reporte_con_citas_adjudicadas_se_completa(tmp_path: Path, con_cita_inventada) -> None:
    proto = _proto_reporte(tmp_path)
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    kwargs = {"search_fn": _busqueda_ft, "fetch_fn": fetch_disponible}
    correr_hasta(protocol, proto, ctx, parar_en="reporte", **kwargs)
    (indice,) = leer_solicitud(ctx.run_dir, "reporte")["must_adjudicate"]

    responder_gate(
        ctx.run_dir,
        "reporte",
        flags={str(indice): {"verdict": "false_positive", "reason": "[2019] es un año"}},
    )
    result = run_pipeline(protocol, proto, RunContext.open(ctx.run_dir), **kwargs)

    assert result.status == "completed"
    reporte = [e for e in ctx.ledger.read_all() if e.stage == "reporte"]
    assert [(e.action, e.target) for e in reporte] == [
        ("flag_review", f"flag:{indice}"),
        ("approve", None),
    ]
    resumen = summarize_gates(ctx.ledger.read_all())["reporte"]
    assert (resumen.forced_human, resumen.n_flag_reviews) == (True, 1)
    assert read_run_info(ctx.run_dir).status == "completed"
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py -v`
Expected: FAIL `test_gate_final_forzado_a_humano_si_hallucination_flagged` (con `reporte` en A2 la corrida se completa pese a la cita inventada: `('completed', None) == ('paused', 'reporte')`) y `test_reporte_con_citas_adjudicadas_se_completa` (`FileNotFoundError` de `reporte/review_request.yml`: en A2 el gate no pide nada).

- [ ] **Step 3: Solicitud y política del reporte.** En `revisia/orchestration/gates.py`, sustituir

```python
from revisia.orchestration.hitl import RecordHint, RecordLabel, RecordPolicy
from revisia.provenance.runmeta import canonical_sha256
```

por

```python
from revisia.orchestration.hitl import (
    FlaggedClaim,
    FlagPolicy,
    RecordHint,
    RecordLabel,
    RecordPolicy,
)
from revisia.provenance.runmeta import canonical_sha256, sha256_text
```

sustituir

```python
from revisia.schemas.screening import ScreeningDecision
```

por

```python
from revisia.schemas.screening import ScreeningDecision
from revisia.schemas.verification import CitationCheck, VerificationReport

# Longitud máxima de una afirmación marcada en la solicitud del reporte (§4.3).
_CLAIM_CHARS = 300
```

y

```python
def apply_labels(
```

por

```python
def _flagged(verification: VerificationReport) -> list[tuple[int, CitationCheck]]:
    """Citas marcadas, con su posición en ``verification.checks``."""
    return [
        (i, c)
        for i, c in enumerate(verification.checks)
        if not c.exists_in_corpus or not c.grounded
    ]


def report_payload(
    *,
    included: Iterable[SearchRecord],
    verification: VerificationReport,
    documento: str,
    grounding_mode: str,
    forced_human: bool,
) -> dict:
    """Solicitud del gate final ``reporte`` (spec §4.3; M5, D8).

    ``must_adjudicate`` son todas las citas marcadas (``index`` = posición en
    ``verification.json.checks``); el documento entra solo por su hash:
    ``documento_sha256 = sha256_text(documento.md)``.
    """
    included = list(included)
    flagged = _flagged(verification)
    return {
        "forced_human": forced_human,
        "forced_reason": "hallucination_flagged" if forced_human else None,
        "n_included": len(included),
        "included": [r.record_id for r in included],
        "verification": {
            "mode": grounding_mode,
            "n_checks": len(verification.checks),
            "n_flagged": len(flagged),
            "hallucination_flagged": verification.hallucination_flagged,
            "flagged": [
                {
                    "index": i,
                    "cited_id": c.cited_id,
                    "claim": c.claim[:_CLAIM_CHARS],
                    "note": c.note,
                }
                for i, c in flagged
            ],
        },
        "must_adjudicate": [i for i, _ in flagged],
        "documento_sha256": sha256_text(documento),
    }


def report_policy(verification: VerificationReport) -> FlagPolicy | None:
    """``FlagPolicy`` del gate final, o ``None`` si el verificador no marcó nada."""
    flagged = _flagged(verification)
    if not flagged:
        return None
    return FlagPolicy(
        flagged=tuple(
            FlaggedClaim(i, c.cited_id, c.claim[:_CLAIM_CHARS], c.note) for i, c in flagged
        )
    )


def apply_labels(
```

- [ ] **Step 4: M5 en el pipeline.** En `revisia/orchestration/pipeline.py`, sustituir

```python
    ft_payload,
    ft_policy,
    rob_payload,
    ta_payload,
    ta_policy,
)
```

por

```python
    ft_payload,
    ft_policy,
    report_payload,
    report_policy,
    rob_payload,
    ta_payload,
    ta_policy,
)
```

justo antes de `run_pipeline`, sustituir

```python
def run_pipeline(
```

por

```python
def _autonomy_effective(protocol: ReviewProtocol, *, forced_human: bool) -> dict[str, str]:
    """Autonomía con la que se aplica cada gate (spec §4.3, ``autonomy_effective``).

    Con citas marcadas (M5) el gate final exige humano: una autonomía A2/A3
    declarada para ``reporte`` pasa a A1.
    """
    effective = {g: protocol.autonomy_for(g) for g in GATED_STAGES}
    if forced_human and effective["reporte"] in {"A2", "A3"}:
        effective["reporte"] = "A1"
    return effective


def run_pipeline(
```

en `_run_stages`, sustituir

```python
    # Checkpoint final del reporte (A1). La solicitud no lleva rutas absolutas (su
    # hash tiene que ser estable entre reanudaciones): el documento va por su hash.
    documento = (deliverable / "documento.md").read_text(encoding="utf-8")
    final_gate = run.gate(
        "reporte",
        {
            "included": len(included),
            "hallucination_flagged": verification.hallucination_flagged,
            "documento_sha256": sha256_text(documento),
        },
    )
```

por

```python
    # Checkpoint final del reporte (A1). La solicitud no lleva rutas absolutas (su
    # hash tiene que ser estable entre reanudaciones): el documento va por su hash.
    # Con citas marcadas el gate exige humano y cada cita se adjudica (M5, D8).
    forced = verification.hallucination_flagged
    documento = (deliverable / "documento.md").read_text(encoding="utf-8")
    final_gate = run.gate(
        "reporte",
        report_payload(
            included=included,
            verification=verification,
            documento=documento,
            grounding_mode=getattr(protocol, "grounding", "embedder"),
            forced_human=forced,
        ),
        flags=report_policy(verification),
        force_human=forced,
    )
```

y en la llamada a `write_manifest`, sustituir

```python
        autonomy_effective={g: protocol.autonomy_for(g) for g in GATED_STAGES},
        final_gate={"forced_human": False, "reason": None},
```

por

```python
        autonomy_effective=_autonomy_effective(protocol, forced_human=forced),
        final_gate={"forced_human": forced, "reason": "hallucination_flagged" if forced else None},
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py tests/test_reanudacion.py tests/test_pipeline_fake.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 496 recogidos.

- [ ] **Step 6: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 7: Commit**

```bash
git add revisia/orchestration/gates.py revisia/orchestration/pipeline.py tests/hitl_helpers.py tests/test_hitl_pipeline.py
git commit -m "feat(pipeline): gate final forzado a humano con citas marcadas (M5, D8)" -m "Si el verificador marca citas, el gate reporte exige decisión humana aunque se pase --auto-approve o reporte esté en A2/A3, y su solicitud lista cada cita marcada en must_adjudicate. Aprobar exige adjudicar cada una como falso positivo con razón (una flag_review por cita en el ledger, antes del approve); si alguna es real, se rechaza. El manifiesto registra final_gate.forced_human y la autonomía efectiva. Hasta ahora la bandera solo se imprimía. Spec 2026-10-04 §3 (D8) y §8." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 27: Checklist trAIce y métodos con la autonomía efectiva y los actores reales (M13)

**Files:**
- Modify: `revisia/exports/checklist.py` (imports l.12-21; dos funciones nuevas antes de `render_traice_checklist` y su cabecera, l.264-280; l.291-297)
- Modify: `revisia/exports/methods.py` (imports l.11-22; firma de `render_methods` l.46-53; l.94-95, l.115-117, l.130-131 y l.137-139)
- Modify: `revisia/orchestration/pipeline.py` (import l.103; `_write_deliverables` l.931-1003; su llamada en `_run_stages` l.1234-1238)
- Test: `tests/test_hitl_pipeline.py` (helper y tres tests nuevos al final)

**Interfaces:**
- Consumes: `summarize_gates`, `GateSummary`, `AUTO_APPROVE_ACTOR`, `HUMAN_ACTOR_PREFIX`, `GATED_STAGES` (PR-0); `JUDGMENT_STAGES` (`revisia/config.py`); `_autonomy_effective` (Tarea 26).
- Produces:
  - `revisia.exports.checklist.describe_gate(stage: str, summary: GateSummary | None) -> str`: `"pendiente de la decisión final"` (`reporte` sin decisión) o `"pendiente (sin decisión registrada)"`; `"auto-proceed (<actor>, autonomía <A>): sin revisión humana"`; `"aprobado por auto-approve (demo): NO es una validación humana"`; `"aprobado|rechazado por humano (<actor>)"` + ` · N etiqueta(s) por registro`, ` · N cita(s) marcada(s) adjudicada(s)`, ` · forzado a humano por citas marcadas`; `"… por <actor> (no humano)"`.
  - `human_validation_summary(gates: Mapping[str, GateSummary]) -> str` (sobre `JUDGMENT_STAGES` con decisión: "un humano resolvió todos…" o "⚠ gates de juicio sin decisión humana: …; decláralo").
  - `render_traice_checklist(run_metas, autonomy_effective: Mapping[str, str], *, gates: Mapping[str, GateSummary] | None = None, forced_human: bool = False, metrics=None, exclusions=None, search_window=None) -> str`: desaparece el texto fijo "checkpoints HITL registrados"; sección "Autonomía efectiva y decisión por gate" con una línea por `GATED_STAGES`: `- <gate> (<autonomía>): <describe_gate>`.
  - `render_methods(..., gates=None, autonomy_effective=None, forced_human=False)`: las afirmaciones fijas de `methods.py:76,94,109,116` se sustituyen por lo que pasó en cada gate.
  - El pipeline escribe ambos antes del gate final con `summarize_gates(ledger)` y la autonomía efectiva: el gate `reporte` figura "pendiente de la decisión final".

- [ ] **Step 1: Tests que fallan** — añadir al final de `tests/test_hitl_pipeline.py`:

```python


# ── trAIce y métodos con lo que pasó de verdad (M13) ──────────────────────


def _entregable(ctx: RunContext, nombre: str) -> str:
    return (ctx.run_dir / "deliverable" / nombre).read_text(encoding="utf-8")


def test_traice_autonomia_efectiva_y_actores_reales(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    humano = RunContext(protocol.slug, tmp_path, "HUMANO")
    correr_hasta(protocol, EXAMPLE, humano, search_fn=_busqueda_ft, fetch_fn=fetch_disponible)
    traice = _entregable(humano, "checklist_traice.md")
    assert "checkpoints HITL registrados" not in traice  # el texto fijo de antes
    assert "- screening_ta (A1): aprobado por humano (human:revisora)" in traice
    assert (
        "- screening_ft (A0): aprobado por humano (human:revisora) · 2 etiqueta(s) por registro"
        in traice
    )
    # Se escribe antes del gate final: ese gate figura pendiente.
    assert "- reporte (A1): pendiente de la decisión final" in traice
    assert "un humano resolvió todos los gates de juicio" in traice

    demo = RunContext(protocol.slug, tmp_path, "DEMO")
    run_pipeline(
        protocol,
        EXAMPLE,
        demo,
        auto_approve=True,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
    )
    traice = _entregable(demo, "checklist_traice.md")
    assert "- rob (A0): aprobado por auto-approve (demo): NO es una validación humana" in traice
    assert "⚠ gates de juicio sin decisión humana" in traice


def test_traice_reporte_forzado_figura_en_a1(tmp_path: Path, con_cita_inventada) -> None:
    proto = _proto_reporte(tmp_path)  # reporte declarado en A2
    protocol = load_protocol(proto)
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T")
    run_pipeline(
        protocol, proto, ctx, auto_approve=True, search_fn=_busqueda_ft, fetch_fn=fetch_disponible
    )
    traice = _entregable(ctx, "checklist_traice.md")
    assert "- reporte (A1): pendiente de la decisión final · exige decisión humana" in traice


def test_methods_sin_texto_fijo_de_validacion_humana(tmp_path: Path, proveedor) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        auto_approve=True,
        search_fn=_busqueda_ft,
        fetch_fn=fetch_disponible,
    )
    metodos = _entregable(ctx, "metodologia.md")
    for fijo in (
        "checkpoint humano (HITL)",
        "revisión humana campo a campo",
        "Juicio final humano (A0)",
        "la decisión final es siempre humana",
    ):
        assert fijo not in metodos
    assert (
        "Título/abstract: aprobado por auto-approve (demo): NO es una validación humana "
        "(autonomía A1)" in metodos
    )
    assert "⚠ gates de juicio sin decisión humana" in metodos
    assert "Reporte final: pendiente de la decisión final (autonomía A1)." in metodos
```

- [ ] **Step 2: Verificar que fallan**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py -v`
Expected: FAIL `test_traice_autonomia_efectiva_y_actores_reales`, `test_traice_reporte_forzado_figura_en_a1` y `test_methods_sin_texto_fijo_de_validacion_humana` (los textos fijos siguen ahí y no hay líneas por gate).

- [ ] **Step 3: Checklist trAIce.** En `revisia/exports/checklist.py`, sustituir

```python
from collections.abc import Iterable
from typing import TYPE_CHECKING

from revisia.metrics import fmt_metric
from revisia.provenance.runmeta import RunMeta

if TYPE_CHECKING:
    from revisia.exclusions import ExclusionBreakdown
    from revisia.metrics import ScreeningMetrics
    from revisia.schemas.artifacts import SearchLog
```

por

```python
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from revisia.config import JUDGMENT_STAGES
from revisia.metrics import fmt_metric
from revisia.provenance.ledger import AUTO_APPROVE_ACTOR, HUMAN_ACTOR_PREFIX
from revisia.provenance.runmeta import RunMeta
from revisia.schemas.artifacts import GATED_STAGES

if TYPE_CHECKING:
    from revisia.exclusions import ExclusionBreakdown
    from revisia.metrics import ScreeningMetrics
    from revisia.schemas.artifacts import GateSummary, SearchLog
```

sustituir la cabecera de `render_traice_checklist`

```python
def render_traice_checklist(
    run_metas: Iterable[RunMeta],
    autonomy: dict[str, str],
    *,
    metrics: ScreeningMetrics | None = None,
    exclusions: ExclusionBreakdown | None = None,
    search_window: dict[str, str] | None = None,
) -> str:
    """Renderiza el checklist PRISMA-trAIce a partir de la procedencia real.

    Args:
        run_metas: todos los ``RunMeta`` registrados en la corrida.
        autonomy: nivel de autonomía aplicado por etapa.
        metrics: métricas de cribado frente al gold standard, si se calcularon.
        exclusions: desglose de exclusiones humano vs IA, si se calculó.
        search_window: ventana temporal de la búsqueda declarada en el protocolo.
    """
```

por

```python
def describe_gate(stage: str, summary: GateSummary | None) -> str:
    """Quién decidió de verdad un gate, en una frase (M13).

    Sale del ledger reducido por ``summarize_gates`` (el mismo reductor que usa
    el auditor, D12): nunca se afirma una validación humana que no ocurrió.
    """
    if summary is None:
        if stage == "reporte":
            return "pendiente de la decisión final"
        return "pendiente (sin decisión registrada)"
    if summary.action == "auto-proceed":
        return f"auto-proceed ({summary.actor}, autonomía {summary.autonomy}): sin revisión humana"
    if summary.actor == AUTO_APPROVE_ACTOR:
        return "aprobado por auto-approve (demo): NO es una validación humana"
    verb = "aprobado" if summary.action == "approve" else "rechazado"
    if not summary.actor.startswith(HUMAN_ACTOR_PREFIX):
        return f"{verb} por {summary.actor} (no humano)"
    extras = []
    if summary.n_labels:
        extras.append(f"{summary.n_labels} etiqueta(s) por registro")
    if summary.n_flag_reviews:
        extras.append(f"{summary.n_flag_reviews} cita(s) marcada(s) adjudicada(s)")
    if summary.forced_human:
        extras.append("forzado a humano por citas marcadas")
    return f"{verb} por humano ({summary.actor})" + "".join(f" · {e}" for e in extras)


def human_validation_summary(gates: Mapping[str, GateSummary]) -> str:
    """¿Resolvió un humano cada gate de juicio con decisión? (M13)."""
    reached = [s for s in JUDGMENT_STAGES if s in gates]
    if not reached:
        return "ningún gate de juicio tiene todavía una decisión registrada."
    without_human = [s for s in reached if not gates[s].actor.startswith(HUMAN_ACTOR_PREFIX)]
    if without_human:
        detail = ", ".join(f"{s} ({gates[s].actor})" for s in without_human)
        return (
            f"⚠ gates de juicio sin decisión humana: {detail}. Sin revisión humana la "
            "corrida no es evidencia publicable; decláralo."
        )
    return f"un humano resolvió todos los gates de juicio con decisión ({', '.join(reached)})."


def render_traice_checklist(
    run_metas: Iterable[RunMeta],
    autonomy_effective: Mapping[str, str],
    *,
    gates: Mapping[str, GateSummary] | None = None,
    forced_human: bool = False,
    metrics: ScreeningMetrics | None = None,
    exclusions: ExclusionBreakdown | None = None,
    search_window: dict[str, str] | None = None,
) -> str:
    """Renderiza el checklist PRISMA-trAIce a partir de la procedencia real.

    Args:
        run_metas: todos los ``RunMeta`` registrados en la corrida.
        autonomy_effective: autonomía con la que se aplica cada gate (la
            declarada, o A1 en ``reporte`` si el gate quedó forzado a humano).
        gates: decisión efectiva por gate (``summarize_gates`` del ledger). El
            checklist se escribe antes del gate final, que figura "pendiente".
        forced_human: el gate final exige humano por citas marcadas (M5).
        metrics: métricas de cribado frente al gold standard, si se calcularon.
        exclusions: desglose de exclusiones humano vs IA, si se calculó.
        search_window: ventana temporal de la búsqueda declarada en el protocolo.
    """
    gates = gates or {}
```

y

```python
        "- Prompts: versionados en revisia/prompts/ y hash-eados por llamada (RunMeta).",
        "- Validación humana: checkpoints HITL registrados en decisions_ledger.jsonl.",
        "",
        "## Autonomía por etapa",
    ]
    for stage, level in autonomy.items():
        lines.append(f"- {stage}: {level}")
```

por

```python
        "- Prompts: versionados en revisia/prompts/ y hash-eados por llamada (RunMeta).",
        f"- Validación humana: {human_validation_summary(gates)}",
        "",
        "## Autonomía efectiva y decisión por gate",
    ]
    for stage in GATED_STAGES:
        if stage not in autonomy_effective:
            continue
        line = f"- {stage} ({autonomy_effective[stage]}): {describe_gate(stage, gates.get(stage))}"
        if stage == "reporte" and forced_human and stage not in gates:
            line += " · exige decisión humana: el verificador marcó citas"
        lines.append(line)
```

- [ ] **Step 4: Métodos.** En `revisia/exports/methods.py`, sustituir

```python
from typing import TYPE_CHECKING

from revisia.exports.checklist import engine_search_date
from revisia.metrics import fmt_metric

if TYPE_CHECKING:
    from revisia.config import ReviewProtocol
    from revisia.exclusions import ExclusionBreakdown
    from revisia.exports.prisma_flow import PrismaCounts
    from revisia.extraction_agreement import ExtractionAgreement
    from revisia.metrics import ScreeningMetrics
    from revisia.schemas.artifacts import SearchLog
```

por

```python
from collections.abc import Mapping
from typing import TYPE_CHECKING

from revisia.exports.checklist import describe_gate, engine_search_date, human_validation_summary
from revisia.metrics import fmt_metric

if TYPE_CHECKING:
    from revisia.config import ReviewProtocol
    from revisia.exclusions import ExclusionBreakdown
    from revisia.exports.prisma_flow import PrismaCounts
    from revisia.extraction_agreement import ExtractionAgreement
    from revisia.metrics import ScreeningMetrics
    from revisia.schemas.artifacts import GateSummary, SearchLog
```

sustituir

```python
    extraction_agreement: ExtractionAgreement | None = None,
    search_log: SearchLog | None = None,
) -> str:
    """Renderiza la sección de métodos (``metodologia.md``) de la revisión.

    Con ``search_log`` (Ola 1) la fecha de búsqueda es la registrada por el
    motor y se dice en qué bases se usó la pregunta como cadena (PRISMA-S 8).
    """
```

por

```python
    extraction_agreement: ExtractionAgreement | None = None,
    search_log: SearchLog | None = None,
    gates: Mapping[str, GateSummary] | None = None,
    autonomy_effective: Mapping[str, str] | None = None,
    forced_human: bool = False,
) -> str:
    """Renderiza la sección de métodos (``metodologia.md``) de la revisión.

    Con ``search_log`` (Ola 1) la fecha de búsqueda es la registrada por el
    motor y se dice en qué bases se usó la pregunta como cadena (PRISMA-S 8).
    Quién decidió cada fase sale de ``gates`` (``summarize_gates`` del ledger) y
    de la autonomía efectiva, no de un texto fijo: si un gate de juicio no lo
    resolvió un humano, el método lo dice (M13).
    """
    gates = gates or {}
    autonomy = dict(autonomy_effective or {})

    def decision(stage: str) -> str:
        level = autonomy.get(stage) or protocol.autonomy_for(stage)
        return f"{describe_gate(stage, gates.get(stage))} (autonomía {level})"

```

sustituir

```python
        f"Dos fases (título/abstract y texto completo) con ensemble multi-modelo "
        f"sesgado a recall y checkpoint humano (HITL). Acuerdo: {kappa}.",
```

por

```python
        "Dos fases (título/abstract y texto completo) con ensemble multi-modelo sesgado a "
        f"recall. Título/abstract: {decision('screening_ta')}. Texto completo: "
        f"{decision('screening_ft')}. Acuerdo: {kappa}.",
```

sustituir

```python
        "Formulario configurable (extraction_form.yml) con cita textual de origen por "
        "campo (anti-alucinación); autonomía A0 (revisión humana campo a campo).",
    ]
```

por

```python
        "Formulario configurable (extraction_form.yml) con cita textual de origen por "
        "campo (anti-alucinación). La tabla de extracción se aprueba por etapa: "
        f"{decision('extraccion')}.",
    ]
```

sustituir

```python
        f"Herramienta: {protocol.rob_tool}. No excluye estudios automáticamente; "
        "pondera su peso en la síntesis. Juicio final humano (A0).",
```

por

```python
        f"Herramienta: {protocol.rob_tool}. No excluye estudios automáticamente; "
        f"pondera su peso en la síntesis. Decisión: {decision('rob')}.",
```

y

```python
        f"Modelos: {ia_models}. Parámetros (temperatura/top_p/seed) y hash de prompt "
        "registrados por llamada en manifest.yml. Validación humana: checkpoints HITL "
        "en cada etapa; la decisión final es siempre humana.",
```

por

```python
        f"Modelos: {ia_models}. Parámetros (temperatura/top_p/seed) y hash de prompt "
        "registrados por llamada en manifest.yml. Validación humana: "
        f"{human_validation_summary(gates)} Reporte final: {decision('reporte')}"
        + (" — exige decisión humana: el verificador marcó citas." if forced_human else "."),
```

- [ ] **Step 5: El pipeline los escribe desde el ledger.** En `revisia/orchestration/pipeline.py`, sustituir

```python
from revisia.provenance.runmeta import RunMeta, canonical_sha256, sha256_text, utc_now_iso
```

por

```python
from revisia.provenance.ledger import summarize_gates
from revisia.provenance.runmeta import RunMeta, canonical_sha256, sha256_text, utc_now_iso
```

en `_write_deliverables`, sustituir

```python
    meta_result: MetaAnalysisResult | None,
    meta_display: str,
) -> Path:
    """Escribe el entregable completo (``deliverable/``) y devuelve su carpeta."""
    protocol = run.protocol
```

por

```python
    meta_result: MetaAnalysisResult | None,
    meta_display: str,
    forced_human: bool,
) -> Path:
    """Escribe el entregable completo (``deliverable/``) y devuelve su carpeta.

    El checklist trAIce y ``metodologia.md`` dicen quién decidió cada gate según
    el ledger (M13); se escriben antes del gate final, que figura pendiente.
    """
    protocol = run.protocol
    gates = summarize_gates(run.ctx.ledger.read_all())
    autonomy_effective = _autonomy_effective(protocol, forced_human=forced_human)
```

en la llamada a `render_methods`, sustituir

```python
            extraction_agreement=extraction_agreement,
            search_log=search_log,
        ),
        encoding="utf-8",
    )
```

por

```python
            extraction_agreement=extraction_agreement,
            search_log=search_log,
            gates=gates,
            autonomy_effective=autonomy_effective,
            forced_human=forced_human,
        ),
        encoding="utf-8",
    )
```

en la de `render_traice_checklist`, sustituir

```python
        render_traice_checklist(
            run.ctx.metas,
            dict(protocol.autonomy),
            metrics=run.metrics,
```

por

```python
        render_traice_checklist(
            run.ctx.metas,
            autonomy_effective,
            gates=gates,
            forced_human=forced_human,
            metrics=run.metrics,
```

y en `_run_stages`, sustituir

```python
        meta_result=meta_result,
        meta_display=meta_display,
    )

    # Checkpoint final del reporte (A1). La solicitud no lleva rutas absolutas (su
```

por

```python
        meta_result=meta_result,
        meta_display=meta_display,
        forced_human=verification.hallucination_flagged,
    )

    # Checkpoint final del reporte (A1). La solicitud no lleva rutas absolutas (su
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl_pipeline.py tests/test_coverage_gaps.py tests/test_pipeline_fake.py -v`
Expected: PASS (los tests de `render_methods` sin `gates` siguen en verde).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, **499 recogidos** (fin de PR-D).

- [ ] **Step 7: Lint** — comando de Global Constraints. Expected: limpio.

- [ ] **Step 8: Commit**

```bash
git add revisia/exports/checklist.py revisia/exports/methods.py revisia/orchestration/pipeline.py tests/test_hitl_pipeline.py
git commit -m "feat(exports): trAIce y métodos con la autonomía efectiva y los actores reales (M13)" -m "checklist_traice.md y metodologia.md dicen, gate por gate y desde el ledger (summarize_gates, el mismo reductor del auditor, D12), quién decidió de verdad: humano (con sus etiquetas y adjudicaciones), auto-approve, auto-proceed o pendiente, con la autonomía efectiva. Desaparecen los textos fijos (checkpoints HITL registrados, revisión humana campo a campo, juicio final humano A0, la decisión final es siempre humana); si un gate de juicio no lo resolvió un humano, lo dicen. Auditoría 2026-09-03, M13; spec 2026-10-04 §8." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 28: Integración de PR-D y E2E de §11 (controlador, `C:\revisia-wt\d`)

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`, ya con el texto de PR-0 a PR-C)
- Modify: `README.md` (sección "Checkpoint humano (`decision.yml`)", reescrita entera)
- Modify: `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md` (§14, filas 25-31)

**Interfaces:** ninguna de código. Deja `feat/ola1-hitl-por-registro` publicada y PR-D abierta con base `feat/ola1-reanudacion`; es el punto de partida de la fase 2 de PR-E.

- [ ] **Step 1: Al día con C.** Si `feat/ola1-reanudacion` recibió commits después de crear el worktree (correcciones de la revisión de PR-C, o su commit de documentación de la Tarea 19 si se creó el worktree antes):

```bash
git -C C:/revisia-wt/d rebase feat/ola1-reanudacion
```

Expected: sin conflictos (D no toca la documentación hasta este paso). Repetir `uv run pytest -p no:cacheprovider` → 499.

- [ ] **Step 2: CHANGELOG.** En `CHANGELOG.md`, sustituir

```
- `decision.template.yml` junto a cada `review_request.yml` y
  `03_screening/gold.json` con el gold efectivo.

### Fixed
```

por

```
- `decision.template.yml` junto a cada `review_request.yml` y
  `03_screening/gold.json` con el gold efectivo.
- **Decisión humana por registro** en el cribado (auditoría 2026-09-03, C1;
  PRISMA 2020, ítem 8; trAIce R1): `decision.yml` gana
  `records: {"<id>": {label, reason}}`. En título/abstract (A1) se aprueba la
  propuesta de la IA con excepciones; en texto completo (A0) se etiqueta cada
  informe recuperado y un `unclear` solo lo resuelve un humano. Un informe no
  recuperado se puede rescatar con una razón y cuenta como evaluado por
  humano. `human_label` se escribe solo ante una etiqueta explícita: aprobar en
  bloque deja la exclusión como "IA avalada".
- **Citas marcadas adjudicadas** (M5): si el verificador marca citas, el gate
  final exige humano (aunque se pase `--auto-approve` o `reporte` esté en
  A2/A3) y aprobar exige adjudicar cada cita como falso positivo con razón
  (`flags: {"<índice>": {verdict: false_positive, reason}}`); si alguna es
  real, se rechaza. Cada etiqueta y cada adjudicación queda en el ledger.
- La solicitud de título/abstract informa del recall y el kappa frente al gold
  y de qué exclusiones de la IA habría que etiquetar para que un recall bajo
  umbral no bloquee la publicación. Las de extracción y RoB llevan la tabla
  completa por estudio y el hash del artefacto aprobado.

### Fixed
```

sustituir

```
- La solicitud del gate final llevaba la ruta absoluta del entregable.

### Changed
```

por

```
- La solicitud del gate final llevaba la ruta absoluta del entregable.
- Un `unclear` del cribado a texto completo pasaba a extracción, RoB, síntesis
  y a los incluidos sin que nadie lo resolviera (C1).
- `checklist_traice.md` y `metodologia.md` afirmaban una validación humana
  fija ("checkpoints HITL registrados", "revisión humana campo a campo", "la
  decisión final es siempre humana"); ahora dicen, gate por gate y desde el
  ledger, quién decidió de verdad y con qué autonomía efectiva (M13).
- `hallucination_flagged` solo se imprimía; ahora bloquea la aprobación
  silenciosa del reporte (M5).

### Changed
```

sustituir

```
- `revisia run --max` vale 50 por defecto en una corrida nueva; al reanudar
  manda el de `run.json`.

### Cambios incompatibles
```

por

```
- `revisia run --max` vale 50 por defecto en una corrida nueva; al reanudar
  manda el de `run.json`.
- Las métricas de cribado miden siempre la propuesta de la IA
  (`ensemble_label`) frente al gold, nunca la decisión final humano + IA (D6).
- `--auto-approve` aprueba con las etiquetas de la IA y no exige etiquetar
  cada registro en A0, pero pausa si hay un `unclear` en texto completo (D9).

### Cambios incompatibles
```

y sustituir

```
- `RunContext.record_meta` exige `stage=`.

## [0.7.0] · 2026-09-28
```

por

```
- `RunContext.record_meta` exige `stage=`.
- Aprobar el cribado a texto completo en A0 exige etiquetar cada informe
  recuperado, y ningún `unclear` pasa sin etiqueta humana.
- Con citas marcadas por el verificador, el reporte final ya no se aprueba sin
  adjudicar cada cita, ni con `--auto-approve`.
- `render_traice_checklist` recibe la autonomía efectiva por gate (segundo
  argumento) y, opcionalmente, `gates` y `forced_human`.

## [0.7.0] · 2026-09-28
```

- [ ] **Step 3: README.** Sustituir la sección del checkpoint, desde `## Checkpoint humano (`decision.yml`)` hasta el final de la nota "Limitación actual" (justo antes de `## Exportar el artículo (HTML / PDF)`), por:

````markdown
## Checkpoint humano (`decision.yml`)

En cada etapa con autonomía A0/A1 el pipeline escribe
`runs/<slug>-<fecha>/<etapa>/review_request.yml` con lo que debes revisar y, a
su lado, `decision.template.yml`, y se pausa. Copia la plantilla como
`<etapa>/decision.yml`, rellénala y reanuda **la misma** corrida:

```bash
uv run revisia run --resume runs/<slug>-<fecha>
```

La plantilla trae `approved: null` (no vale tal cual: aprobar tiene que ser un
acto deliberado) y un `request_sha256` que ata la decisión a esa solicitud: si
la solicitud cambia, la decisión no se aplica y la corrida vuelve a pausar.

**Cribado (`screening_ta`, `screening_ft`): decisión por registro.** La
solicitud lista cada registro con la propuesta de la IA (y el voto de cada
modelo en título/abstract) y la plantilla trae una línea por registro:

```yaml
request_sha256: "9f2c…"
approved: true
actor: human:tu-nombre
reason: revisé las 12 exclusiones de la IA
records:
  "10.1000/abc": {label: include, reason: trata cribado con LLM}   # rescata una exclusión de la IA
  "rec-7": {label: exclude, reason: población no elegible}
  "rec-9": {label: null, reason: null}                              # sin etiqueta: queda la propuesta IA
```

- En título/abstract (A1, por defecto) apruebas la propuesta de la IA y
  etiquetas solo las excepciones. Si el protocolo tiene gold, la solicitud
  dice el recall y el kappa de la IA y lista sus exclusiones (`ai_excluded`):
  con un recall bajo `recall_target`, etiquétalas para que la corrida sea
  publicable.
- En texto completo (A0, por defecto) etiquetas cada informe recuperado
  (`must_label`); excluir exige `reason`, que va a la lista de excluidos
  (PRISMA 2020, 16b). Un `unclear` nunca pasa sin etiqueta humana
  (`must_resolve`). Un informe no recuperado (`rescuable`) se puede rescatar si
  conseguiste el texto por otra vía: etiquétalo con `reason`.
- Una etiqueta explícita queda como decisión humana (`human_label`) en
  `decisions.json` y en el ledger; aprobar en bloque deja la propuesta como
  "IA avalada".

**Extracción y RoB** se aprueban por etapa: la solicitud trae la tabla
completa por estudio y el hash del artefacto que apruebas (`records` ahí es un
error).

**Reporte final con citas marcadas.** Si el verificador marcó citas, este gate
exige decisión humana (aunque pases `--auto-approve`) y, para aprobar, cada
cita marcada necesita una adjudicación con razón:

```yaml
flags:
  "3": {verdict: false_positive, reason: "[2019] es un año, no un id de estudio"}
```

Si alguna marca es una alucinación real, rechaza (`approved: false`): no hay
un veredicto "aceptar el riesgo".

Un `decision.yml` vacío, con YAML roto, sin `request_sha256` ni `approved`,
con ids que no están en la solicitud o incompleto para aprobar detiene la
corrida con un mensaje que nombra qué falta (código 2): no se toma como
rechazo ni como aprobación. Con `approved: false` en el reporte final la
corrida termina como `rejected` (código 1) y no se sedimenta en `--brain`.
Reanudar no repite la búsqueda ni ninguna llamada ya hecha; una corrida
interrumpida (un 429, la red) sale con código 3 y se reanuda igual. No
reanudes la misma corrida en dos procesos a la vez, y si empezaste con
`--mailto`, pásalo también al reanudar.

`--auto-approve` sirve para demostraciones: aprueba con las etiquetas de la IA
(actor `auto-approve (demo)`, que el checklist trAIce y `metodologia.md`
declaran como no humano) y pausa si hay un `unclear` en texto completo o citas
marcadas.

> **Limitación actual (Ola 1 del plan de remediación).** `revisia audit` todavía
> marca `--auto-approve` solo con WARN en `hitl` y en `final_gate`, sin
> declararlo no publicable; el auditor estricto llega con la última PR de la
> Ola 1.
````

- [ ] **Step 4: Desviaciones en el spec.** En §14 del spec, añadir tras la fila 24:

```
| 25 | §8 `gates.py` | Además de las siete funciones del spec, `report_policy(verification) -> FlagPolicy \| None`. Todas con argumentos por nombre; `ta_payload(..., metrics=None, thresholds=None)` para `quality` (D7); el payload de FT ordena `records` por id, como el de T/A | Plan PR-D |
| 26 | §8 `hitl.py` | `RecordHint(record_id, title, proposal, note="")` y `FlaggedClaim(index, cited_id, claim, note=None)`; `RecordPolicy` con defaults; las claves de `records`/`flags` se convierten a texto; la validación de contenido (ids, razones, completitud) solo se hace al aprobar (con `approved: false` nada se aplica) y la estructural (`records`/`flags` en un gate que no los admite) siempre; la decisión sintética de `--auto-approve` no se valida (D9: no exige la completitud A0); `force_human` con `--auto-approve` pausa con su propio mensaje; sin `decision.yml`, la reconstrucción desde el ledger devuelve también etiquetas y adjudicaciones | Plan PR-D |
| 27 | §8 ledger y payloads | `claim` de las citas marcadas recortado a 300 caracteres también en la `FlagPolicy` y en el `detail` de `flag_review`; un `label` lleva `from: null` en un no recuperado | Plan PR-D |
| 28 | §8 M13 | `render_traice_checklist(run_metas, autonomy_effective, *, gates=None, forced_human=False, metrics, exclusions, search_window)`: el segundo posicional pasa a ser la autonomía efectiva; `describe_gate(stage, summary)` y `human_validation_summary(gates)` públicas en `exports/checklist.py`, las usa también `methods.py`. Autonomía efectiva calculada por `pipeline._autonomy_effective` | Plan PR-D |
| 29 | §8 helpers de test | `responder_gate(..., flags=None)` (aditivo) y `aceptar_lo_obligatorio(stage, solicitud)`: `correr_hasta` responde con ella cuando `etiquetar` falta o devuelve `None` (con FT en A0 aprobar exige etiquetar cada recuperado). El test unitario `test_ft_a0_aprobar_sin_etiquetar_todo_es_error` va en `tests/test_hitl_registros.py` y su versión de pipeline se llama `test_ft_a0_pipeline_exige_etiquetar_los_recuperados` | Plan PR-D |
| 30 | §8 tests nuevos | Además de los del spec: `test_rescate_sin_razon_es_error`, `test_etiquetas_en_el_ledger_antes_del_approve`, `test_rechazo_no_lleva_etiquetas`, `test_etiquetas_se_reconstruyen_desde_el_ledger`, `test_auto_approve_pausa_con_registros_por_resolver`, `test_auto_approve_no_exige_la_completitud_a0`, `test_force_human_ignora_auto_approve_y_a2`, `test_review_request_ta_sin_gold_no_informa_calidad`, `test_reporte_con_citas_adjudicadas_se_completa`, `test_traice_reporte_forzado_figura_en_a1` | Plan PR-D |
| 31 | README | PR-D deja la nota "Limitación actual" reducida al auditor (`--auto-approve` aún solo da WARN); la quita PR-E, como dice §10 | Plan PR-D |
```

- [ ] **Step 5: Commit de documentación.**

```bash
git -C C:/revisia-wt/d add CHANGELOG.md README.md docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md
git -C C:/revisia-wt/d commit -m "docs: CHANGELOG, README y desviaciones de PR-D (HITL por registro)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Verificación completa** (en `C:\revisia-wt\d`): suite 3.13 (**499 recogidos**), el bucle de 3.11/3.12 de la Tarea 19 Step 6 (497 passed, 2 skipped en ambas), `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`. Expected: todo en verde y limpio.

- [ ] **Step 7: E2E de §11 con el demo y el proveedor fake, sin red.** Corrida nueva → pausa en `screening_ta` → `decision.yml` con el hash → `revisia run --resume` → … → completada → `revisia audit`. Sin red no hay texto completo en abierto, así que en `screening_ft` la revisora rescata los dos informes (D2):

```bash
RUNS="$(mktemp -d)"
uv run python - "$RUNS" <<'PY'
import sys
sys.path.insert(0, "tests")
from pathlib import Path
from test_pipeline_fake import EXAMPLE, _fake_search
from revisia.config import load_protocol
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
protocol = load_protocol(EXAMPLE)
ctx = RunContext(protocol.slug, Path(sys.argv[1]), "E2E")
r = run_pipeline(protocol, EXAMPLE, ctx, search_fn=_fake_search)
print(r.status, r.stage)
PY
RUN="$RUNS/demo-mini-review-E2E"
for _ in 1 2 3 4 5 6; do
  ESTADO=$(uv run python -c "import json,sys; print(json.load(open(sys.argv[1]))['status'])" "$RUN/run.json")
  [ "$ESTADO" = "completed" ] && break
  uv run python - "$RUN" <<'PY'
import json, sys
sys.path.insert(0, "tests")
from pathlib import Path
from hitl_helpers import leer_solicitud, responder_gate
run = Path(sys.argv[1])
etapa = json.loads((run / "run.json").read_text(encoding="utf-8"))["stage"]
solicitud = leer_solicitud(run, etapa)
records = None
if etapa == "screening_ft":  # sin red no hay texto en abierto: la revisora rescata (D2)
    records = {rid: {"label": "include", "reason": "PDF conseguido por la revisora"}
               for rid in solicitud["rescuable"]}
responder_gate(run, etapa, records=records)
print("decidido:", etapa, solicitud["request_sha256"][:12])
PY
  uv run revisia run --resume "$RUN"
done
uv run revisia audit "$RUN" | tail -1
grep -c '"action":"label"' "$RUN/decisions_ledger.jsonl"
grep "screening_ft (A0)" "$RUN/deliverable/checklist_traice.md"
```

Expected: `paused screening_ta`; cinco decisiones (`screening_ta`, `screening_ft`, `extraccion`, `rob`, `reporte`), las cuatro primeras reanudaciones pausan en el gate siguiente y la quinta termina con `✓ COMPLETED · Revisión completada · 2 estudios incluidos.`; `revisia audit` → `✅ APTA para preparar publicación` (con el auditor de la v0.7; el veredicto estricto de §11 lo da PR-E); `2` etiquetas en el ledger (los dos rescates); y la línea `- screening_ft (A0): aprobado por humano (human:revisora) · 2 etiqueta(s) por registro`.

La misma corrida con `--auto-approve` (`uv run revisia run --resume "$RUN2" --auto-approve` sobre una corrida nueva en pausa) termina `COMPLETED · 0 estudios incluidos` y su `checklist_traice.md` dice `aprobado por auto-approve (demo): NO es una validación humana` en cada gate de juicio; que `revisia audit` la declare **NO publicable** es criterio de cierre de PR-E (D8).

- [ ] **Step 8: Publicar y abrir PR-D** (sin merge).

```bash
git -C C:/revisia-wt/d push -u origin feat/ola1-hitl-por-registro
gh pr create --base feat/ola1-reanudacion --head feat/ola1-hitl-por-registro --title "Ola 1 · PR-D: HITL por registro, citas adjudicadas y trAIce con actores reales (C1, M5, M13)" --body "$(cat <<'EOF'
## Qué cierra

- C1 de la auditoría 2026-09-03 (lo que dejó la Ola 0): ningún código asignaba `human_label`, así que el diagrama trAIce siempre decía "excluidos por humano: 0" y el ítem 8 de PRISMA 2020 no se podía reportar con honestidad; un `unclear` de FT pasaba a extracción y a los incluidos.
- M5: `hallucination_flagged` solo se imprimía.
- M13: el checklist trAIce y `metodologia.md` afirmaban una validación humana fija.

## Qué cambia

- `decision.yml` gana `records` (cribado, por registro) y `flags` (reporte, por cita marcada); `RecordPolicy`/`FlagPolicy` y una validación que nombra qué falta; `decision.template.yml` lista registros y citas con la propuesta IA en comentarios saneados (D4).
- `orchestration/gates.py`: solicitudes de §4.3 (votos por miembro, `quality` y `ai_excluded` en T/A, recuperación y `must_*` en FT, tabla y hash del artefacto en extracción y RoB, citas marcadas en el reporte) y `apply_labels` (D5: solo etiquetas explícitas).
- FT: un `unclear` solo lo resuelve un humano (con `--auto-approve`, pausa; D9); rescate de no recuperados con razón (D2); razón humana en la lista 16b.
- Métricas sobre `ensemble_label` (D6).
- M5: con citas marcadas el gate final exige humano y adjudicación por cita; `flag_review` en el ledger antes del `approve`; `manifest.final_gate`.
- M13: trAIce y métodos desde `summarize_gates` con la autonomía efectiva.

## Cambios incompatibles

- Aprobar FT en A0 exige etiquetar cada recuperado; ningún `unclear` pasa sin humano.
- Con citas marcadas, el reporte no se aprueba sin adjudicarlas, ni con `--auto-approve`.
- `render_traice_checklist` recibe la autonomía efectiva.

## Verificación

- `uv run pytest -p no:cacheprovider`: 499 recogidos, en verde (base: 461).
- La misma suite en 3.11 y 3.12 con venv desechable: en verde.
- `ruff check`, `ruff format --check`, `black --check`, `uv lock --check`: limpios.
- E2E de §11 sin red: corrida → pausa → `decision.yml` con el hash → `revisia run --resume` (×5, con rescate en FT) → completada con 2 incluidos → `revisia audit` APTA.

## Pila

`main` ← PR-0 ← PR-A ← PR-B ← PR-C ← **PR-D** ← PR-E. Base: `feat/ola1-reanudacion`. Nunca `--delete-branch` mientras otra PR use una rama como base.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR.

- [ ] **Step 9: Traspaso a PR-E.** La fase 2 del auditor se rebasa sobre esta rama según la Tarea 11 del plan `2026-10-04-ola-1-c-auditor.md`: `git -C C:/revisia-wt/e rebase --onto feat/ola1-hitl-por-registro feat/ola1-contratos feat/ola1-auditor` (`--onto` reaplica solo los commits de E aunque PR-0 haya recibido correcciones después de crear su worktree). El merge de PR-D lo decide el arquitecto.

---

## Contrato para el auditor (PR-E)

Lo que PR-C y PR-D dejan en disco y en código, tal como lo produce el prototipo de este plan. El plan del auditor se escribe contra esto.

**Código (firmas exactas):**
- `tests/hitl_helpers.py`: `leer_solicitud(run_dir: Path, stage: str) -> dict`; `responder_gate(run_dir: Path, stage: str, *, approved: bool = True, actor: str = "human:revisora", reason: str | None = None, records: dict[str, dict] | None = None, flags: dict[str, dict] | None = None) -> Path`; `aceptar_lo_obligatorio(stage: str, solicitud: dict) -> dict | None`; `correr_hasta(protocol, protocol_dir, ctx, *, search_fn, fetch_fn=None, etiquetar: Callable[[str, dict], dict | None] | None = None, parar_en: str | None = None, max_vueltas: int = 10) -> PipelineResult` (sin `auto_approve`; `etiquetar` devuelve kwargs de `responder_gate` o `None` → `aceptar_lo_obligatorio`; reabre con `RunContext.open` en cada vuelta).
- `revisia.orchestration.run_context`: `PROVENANCE_PIPELINE`, `LLM_CALLS_FILE = "llm_calls.jsonl"`, `RUN_INFO_FILE = "run.json"`, `RunDirExistsError(FileExistsError)`, `LegacyRunError(ValueError)`, `RunInterrupted(RuntimeError)(run_dir, stage, error)`; `RunContext(slug, runs_root, timestamp)`, `RunContext.open(run_dir)`, `.run_dir`, `.slug`, `.timestamp`, `.ledger`, `.llm_calls_path`, `.metas: list[LLMCall]`, `.record_meta(meta, *, stage, record_id=None, role=None) -> LLMCall`, `.write_text`, `.write_json`, `.write_manifest(*, protocol_snapshot, counts, autonomy_effective=None, final_gate=None, extra=None)`.
- `revisia.orchestration.snapshot`: `SNAPSHOT_DIR = "00_protocol"`, `SNAPSHOT_FILES`, `SEARCH_STRINGS_DIR`, `PROMPTS_DIR`, `ProtocolMismatchError(message, files)`, `protocol_fingerprint(dir) -> dict[str, str]`, `prompt_fingerprint() -> dict[str, str]`, `read_run_info(run_dir) -> RunInfo | None`, `write_run_info(run_dir, info) -> RunInfo`, `ensure_snapshot(protocol_dir, run_ctx, *, max_results, mailto) -> tuple[Path, RunInfo]`.
- `revisia.orchestration.journal`: `JournalError(ValueError)`, `read_jsonl(path, model)`, `append_jsonl(path, item)`, `StageJournal(run_ctx, stage)` (`.lookup`, `.append`, `.path`), `journaled(...)`.
- `revisia.orchestration.search_stage`: `SEARCH_DIR = "01_search"`, `multi_database_search(...)`, `run_search(...)`. `revisia.agents.dedup.deduplicate_with_report(records) -> tuple[list[SearchRecord], DedupReport]`.
- `revisia.orchestration.hitl`: `REQUEST_FILE`, `TEMPLATE_FILE`, `DECISION_FILE`, `DecisionFileError`, `RecordLabel(label: Literal["include","exclude"] | None = None, reason: str | None = None)` (`extra="forbid"`), `FlagReview(verdict: Literal["false_positive"] | None = None, reason: str | None = None)` (`extra="forbid"`), `HumanDecision(request_sha256: str, approved: StrictBool, actor: str = "human:desconocido", reason: str | None = None, records: dict[str, RecordLabel] = {}, flags: dict[str, FlagReview] = {})` (`extra="allow"`), `RecordHint`, `RecordPolicy`, `FlaggedClaim`, `FlagPolicy`, `GateResult(status, message, request_sha256=None, actor=None, labels={}, flag_reviews={})`, `review_gate(*, stage, autonomy, run_ctx, review_payload, auto_approve, records=None, flags=None, force_human=False) -> GateResult`, `render_decision_template(*, stage, autonomy, request_sha256, records, flags) -> str`.
- `revisia.orchestration.gates`: `ta_payload`, `ta_policy`, `ft_payload`, `ft_policy`, `extraction_payload`, `rob_payload`, `report_payload`, `report_policy`, `apply_labels`.
- `revisia.orchestration.flow.resume_review(run_dir, *, protocol_dir=None, auto_approve=False, mailto=None)`; `revisia.exports.checklist.describe_gate(stage, summary)`, `human_validation_summary(gates)`, `engine_search_date(log)`; `revisia.memory.ResearchBrain.has_run(slug, timestamp)`.

**`review_request.yml`** (`{request_sha256, **solicitud}`, con `request_sha256 = canonical_sha256(solicitud)`), en este orden de claves:
- Comunes: `request_sha256`, `schema_version` (1), `stage`, `autonomy` (la efectiva: A1 en `reporte` forzado).
- `screening_ta`: `mode`, `n_screened`, `n_proposed_pass`, `n_proposed_exclude`, `records[{record_id, title, year, doi, source_db, proposal, votes[{model, label, confidence, rationale, criteria_violated}]}]` (por id), `must_label`, `quality{recall, recall_target, kappa, kappa_min, gold_positives, recall_meets_target} | null`, `ai_excluded`.
- `screening_ft`: `mode`, `n_sought`, `n_retrieved`, `n_not_retrieved`, `records[{record_id, title, year, doi, fulltext, fulltext_reason, fulltext_source_url, proposal, confidence, rationale, criteria_violated}]` (por id), `must_label`, `must_resolve`, `rescuable`.
- `extraccion`: `n_studies`, `studies[{record_id, title, fields{key: {value, source_quote, status, confidence}}}]`, `second_extraction{n_studies, n_field_pairs, value_agreement, presence_kappa} | null`, `artifact_sha256` (= `canonical_sha256(json.load(05_extraction/extractions.json))`).
- `rob`: `tool`, `n_studies`, `studies[{record_id, title, overall, domains[{domain, judgment, rationale, support_quote}]}]`, `artifact_sha256` (de `07_rob/assessments.json`).
- `reporte`: `forced_human`, `forced_reason`, `n_included`, `included`, `verification{mode, n_checks, n_flagged, hallucination_flagged, flagged[{index, cited_id, claim, note}]}`, `must_adjudicate`, `documento_sha256` (= `sha256_text(deliverable/documento.md)` leído con `read_text`).

**`run.json`** (`RunInfo`, escrito de forma atómica e indentado): `schema_version`, `slug`, `timestamp`, `started_utc`, `engine_version`, `python_version`, `max_results`, `mailto_set`, `protocol_sha256` (claves `protocol.yml`, `inclusion_exclusion.yml`, `extraction_form.yml`, `effects.yml`, `gold.yml` si existen y `search_strings/<f>.txt`), `prompt_sha256` (claves `"<agente>/v1.md"`), `resumes` (una hora por invocación posterior a la primera), `interruptions[{utc, stage, error}]`, `status` (`running` durante la invocación; al salir `paused`/`rejected` con `stage` = gate, `completed` con `stage: null`, `interrupted` con la etapa en curso), `stage`, `updated_utc`.

**Ledger (`decisions_ledger.jsonl`, una línea compacta por entrada):**
- `label`: `stage` ∈ {`screening_ta`, `screening_ft`}, `target` = `record_id`, `actor` = el de `decision.yml`, `detail = {from, to, reason, rescue, request_sha256, decision_sha256}` (`from` = propuesta IA o `null` en un no recuperado).
- `flag_review`: `stage = "reporte"`, `target = "flag:<index>"`, `detail = {cited_id, claim, verdict, reason, request_sha256, decision_sha256}`.
- `approve`/`reject`: `detail = {**extras y reason de decision.yml, request_sha256, decision_sha256, n_labels, forced_human}`; las `label`/`flag_review` de una aprobación van antes, en orden de id/índice; un `reject` va solo.
- `auto-proceed`: `actor = "agent:<stage>"`, `detail = {reason, request_sha256}`; `--auto-approve`: `actor = "auto-approve (demo)"`, `action = "approve"`, `n_labels = 0`.

**Campos humanos:** `03_screening/decisions.json` y `04_fulltext/decisions.json` (listas de `ScreeningDecision`) llevan `human_label`, `human_reason`, `human_actor` y `final_label` tras aprobar el gate (se reescriben al aprobar; antes, `final_label = ensemble_label` y los `human_*` en `null`). Los diarios (`journal.jsonl`) guardan la salida de la IA sin campos humanos (`final_label: null`).

**`manifest.yml`:** primeras claves sin cambios; después `run{started_utc, resumes, engine_version, python_version, status}`, `autonomy_effective{gate: nivel}` para los cinco `GATED_STAGES`, `final_gate{forced_human, reason}` y los bloques de siempre (`verification`, `risk_of_bias`, `exclusions`, …). `llm_calls` = las líneas de `llm_calls.jsonl` en orden. Se escribe después del gate final en cada invocación que lo alcanza.

---

## Self-review

Lo hizo el autor del plan antes de entregarlo, sobre un prototipo que aplicó las 15 tareas del plan A y las 26 de código de este plan (cada tarea: test rojo, implementación, suite completa, `ruff check`, `ruff format --check`, `black --check`); los bloques de código de este documento se generaron desde ese prototipo. El controlador lo repite tras cada integración.

**1. Cobertura del spec.**

| Requisito | Tarea |
|---|---|
| §7 refactor puro (`_Run` con `gate`/`stop`, funciones por etapa, `PipelineResult.stage`), primer commit, suite en verde | 1 |
| §7 `journal.py`: `JournalError`, `StageJournal` (`lookup`, `append` con `fsync`), recorte de la última línea truncada, línea corrupta o salida distinta → error | 2 |
| §7 `journaled` (llamadas antes que el diario; entrada obsoleta por `input_sha256`) | 4 |
| §7 `RunContext`: `RunDirExistsError`, `open`, `llm_calls.jsonl`, `record_meta(..., stage, record_id, role) -> LLMCall`, `write_json` atómico, `RunInterrupted`; manifiesto desde `llm_calls.jsonl` | 3, 5 |
| §4.3 manifiesto: `run`, `autonomy_effective`, `final_gate`, escrito después del gate final | 3, 5, 8, 26 |
| §7 `snapshot.py`: `00_protocol/`, `run.json`, huellas CRLF→LF, `prompt_fingerprint`, `ProtocolMismatchError`; `load_protocol(default_slug=)` (hallazgo 4) | 5 |
| §7 `search_stage.py`, `01_search/{records,log,failures}.json` en orden, `import_file`, envoltorio `_multi_database_search` | 6 |
| §7 `deduplicate_with_report`, `02_dedup/{records,dedup}.json` (hallazgos 2 y 3) | 7 |
| §7 preflight al empezar (`resume`/`run`), `RunInterrupted` y `run.json.interruptions`, `flow.resume_review`, `agent_driver(run_dir=)` | 8 |
| §7 / D4 `review_gate`: `request_sha256` canónico, `decision.template.yml`, decisión obsoleta → pausa, ledger idempotente, reconstrucción desde el ledger, payloads sin rutas absolutas | 9, 16 |
| §7 diario por etapa, un commit cada una, en el orden del spec, con los `inputs` de la tabla | 10, 12, 13, 14, 15, 16 |
| §7 `make_provider_judge(..., on_meta=)` | 16 |
| §7 / D6 `03_screening/gold.json` | 11 |
| §7 CLI: `protocol_dir` `nargs="?"`, `--resume`, `--max` default `None`, rc 3/2/130, mensaje de pausa; `brain.has_run` | 17 |
| §7 PRISMA-S y métodos desde el log (y el ítem 4 de resúmenes) | 18 |
| §7 `tests/hitl_helpers.py` (`responder_gate`, `correr_hasta`) | 9 (y 24, 26 aditivos) |
| §7 los 30 tests nombrados | 2 (2), 3 (2), 4 (1), 5 (2), 6 (3), 7 (2), 8 (1), 9 (5), 10 (1), 11 (1), 16 (4), 17 (5), 18 (1) |
| §8 `hitl.py`: `RecordLabel`, `FlagReview`, `HumanDecision` (+`request_sha256`, `records`, `flags`), `RecordPolicy`, `FlagPolicy`, `GateResult` ampliado, validación completa, `force_human`, D9 | 9, 20 |
| §8 / D4 plantilla con registros y citas, saneada | 21 |
| §8 `gates.py` y `apply_labels` (D5) | 22, 23, 24, 25, 26 |
| §8 / D6 métricas sobre `ensemble_label`; D7 `quality` y `ai_excluded` | 23 |
| §8 / C1 FT: `unclear` solo con humano, rescates (D2), `excluded_ft_human/ai`, 16b con razón humana | 24 |
| §8 / D1 extracción y RoB con tabla y `artifact_sha256` | 25 |
| §8 / M5, D8: `force_human`, `FlagPolicy`, `flag_review` antes del `approve`, `manifest.final_gate` | 20, 26 |
| §8 / M13 / D12: trAIce y métodos con autonomía efectiva y actores reales vía `summarize_gates` | 27 |
| §8 / D9 `--auto-approve` | 20, 24 |
| §8 los 27 tests nombrados | 20 (9), 21 (2), 22 (3), 23 (2), 24 (6), 25 (2), 26 (1), 27 (2) |
| §4.4 relaciones 1-4 (búsqueda y dedup) | 6, 7 |
| §4.4 relaciones 5-10 (cribado, FT, conteos) | 22, 23, 24 |
| §4.4 relaciones 12-13 (diarios y llamadas) | 4, 10–16 |
| §4.4 relaciones 14-18 (`run.json`, gates, manifiesto) | 5, 8, 9, 20, 26 |
| §10 cadena apilada, worktrees, solapes, regla de merge | Topología, 19, 28 |
| §11 criterio de cierre (3.13, 3.11/3.12, lint, `uv lock --check`) y E2E con el demo | 19, 28 |
| §13.4 cambios incompatibles en el CHANGELOG | 19, 28 |
| CHANGELOG/README solo por el integrador, con texto exacto | 19, 28 |

**2. Placeholders.** Ningún paso dice "TBD", "TODO", "implementar después" ni "similar a la Tarea N"; todo paso que cambia código trae el código (las sustituciones dan el bloque exacto que se cambia y el que lo reemplaza; la única excepción es la Tarea 8, Step 5, que sustituye "desde `def run_pipeline(` hasta el final del fichero", un rango sin ambigüedad). Las tareas 19 y 28 no tienen test de pytest porque no cambian código: llevan comandos con su salida esperada.

**3. Coherencia de nombres y firmas.** Las firmas de PR-0 se usan literalmente (`LLMCall.from_meta`, `JournalEntry`, `RunInfo`, `SearchLog`/`SearchLogEntry`, `DedupReport`, `RetrievalOutcome`, `GateSummary`, `summarize_gates`, `canonical_sha256`, `AUTO_APPROVE_ACTOR`, `HUMAN_ACTOR_PREFIX`, `GATED_STAGES`, `JOURNAL_PATHS`, `ScriptedProvider`, `fetch_disponible`, `fetch_no_disponible`), igual que las de PR-A (`preflight(..., context=)`, `PreflightError(report)`) y PR-B (`FullText.reason/detail`, `compute_ft_excluded`, `render_excluded_reports`). `StageJournal`/`journaled` (Tareas 2 y 4) son los que usan las Tareas 10–16; `RunContext.open` (5) el que usan `resume_review` (8), `correr_hasta` (9) y el CLI (17); `review_gate` crece de la Tarea 9 a la 20 sin cambiar sus argumentos previos; `_Run.gate` gana `records`/`flags`/`force_human` en la 22 y los usan la 24 y la 26; `_autonomy_effective` (26) lo usa la 27. Conteos de tests verificados en el prototipo: 411 → 461 (PR-C) → 499 (PR-D), en 3.13, 3.11 y 3.12.

## Desviaciones respecto del spec

Se registran también en §14 del spec (Tareas 19 y 28, filas 14-31). Ninguna reabre D1–D14.

1. **Estructura del refactor** (§7): `run_pipeline` queda en preflight + instantánea + `try/except` (unas 70 líneas) y la cadena de etapas en `_run_stages`; hay además `_load_gold` y `_meta_analysis`. Por qué: la captura de interrupciones (Tarea 8) necesita envolver toda la cadena sin mezclarla con la preparación. `_Run.gate(stage, payload)` no recibe `records`/`force_human` hasta PR-D, que añade también `flags` (M5 necesita la `FlagPolicy`).
2. **`RunContext`** (§7): `LegacyRunError(ValueError)` para D13 (el spec pide rc 2 pero no nombra la excepción); `RunContext.open` da `FileNotFoundError` si la carpeta no existe; `write_text` también es atómico; los parámetros nuevos de `write_manifest` tienen default para no romper a los llamadores existentes.
3. **`journal.py`** (§7): `read_jsonl`/`append_jsonl` públicos porque `RunContext` necesita la misma tolerancia a la última línea truncada para `llm_calls.jsonl`; `StageJournal.append` recibe una `JournalEntry`. Funciones genéricas con `TypeVar` y `# noqa: UP047` (no PEP 695) por la matriz 3.11/3.12.
4. **`snapshot.py`** (§7): `ensure_snapshot` escribe `run.json` antes de copiar (§4.2 dice "es lo primero que se escribe"; la huella se calcula sobre el original, que es idéntico byte a byte a la copia); `PROMPTS_DIR` es atributo del módulo para que los tests lo parcheen; `ProtocolMismatchError` guarda la lista en `.files`.
5. **Preflight en `run_pipeline`** (§7): con `search_fn` inyectado también se usa `context="resume"`. Por qué (código real): no hay bases que comprobar y, con `"run"`, el demo (OpenAlex) daría error de `httpx` en el venv de desarrollo y en todos los tests del pipeline. Los avisos no se imprimen ahí (los imprime el CLI). Sobre la desviación 8 del plan A: sin `httpx` al reanudar, lo pendiente de recuperar queda `sin_httpx`; no se convierte en aviso.
6. **`search_stage.py`** (§7): firma de `multi_database_search` con argumentos por nombre; `backend = "<módulo>.<función>"`; entradas de `imported/` con `db_key="imported"` y `declared=true`; una base manual registra su cadena si hay fichero; la inyectada es `database = db_key = "search_fn"`; `failures.json` incluye los ficheros importados que fallan. Reanudar sin la carpeta del protocolo cuando la búsqueda no terminó da `ProtocolMismatchError`, porque `imported/` no está en la instantánea (§4.2).
7. **Gates y ledger en PR-C** (§7, §4.3): `review_gate` añade las claves comunes de la solicitud; el `detail` de `approve`/`reject` ya lleva `n_labels: 0` y `forced_human: false`; volver a una decisión idéntica a una anterior ya reemplazada da `DecisionFileError` (la tupla de §4.3 es única); `render_decision_template` nace sin `records`/`flags` y los gana en PR-D con la firma del spec; el payload de `reporte` de PR-C es `{included, hallucination_flagged, documento_sha256}`.
8. **`inputs` de los diarios** (§7): concretados como listas y hashes (fila 21 de §14); la caché de texto va en bytes UTF-8 y se verifica contra `text_sha256`.
9. **CLI** (§7): `LegacyRunError` y `FileNotFoundError` también salen con rc 2; aviso al reanudar sin `--mailto` si la corrida empezó con él (`mailto_set` entra en la huella de cada recuperación y, si falta, se repetirían); un Ctrl+C también queda en `run.json.interruptions`.
10. **Tests existentes en PR-C, no en PR-D/PR-E** (código real): `tests/test_hitl.py` (decisiones con `request_sha256`, `detail ==` → subconjunto) y dos tests de `tests/test_pipeline_fake.py` cambian ya en PR-C, porque con el hash obligatorio ninguna `decision.yml` se puede escribir antes de correr. `test_paused_run_final_gate_falla_en_auditoria` queda con `correr_hasta(..., parar_en="reporte")`; PR-E solo cambia su aserción.
11. **Helpers y dobles de test**: `leer_solicitud`, `aceptar_lo_obligatorio` y `responder_gate(..., flags=)` además de las firmas del spec; `etiquetar` devuelve kwargs de `responder_gate`; `ScriptedProvider(sintesis=...)` (aditivo) para tener citas que verificar. Por qué: con FT en A0, `correr_hasta` sin una respuesta por defecto no podría terminar ninguna corrida; y el gate final forzado necesita citas marcadas.
12. **`gates.py`** (§8): `report_policy` además de las funciones del spec; argumentos por nombre; el payload de FT ordena por id como el de T/A.
13. **`hitl.py`** (§8): `RecordHint`/`FlaggedClaim` con `note`; las claves de `records`/`flags` se convierten a texto; la validación de contenido solo se hace al aprobar (con `approved: false` nada se aplica) y la estructural siempre; la decisión sintética de `--auto-approve` no se valida (D9 dice que no exige la completitud A0); la reconstrucción desde el ledger devuelve también etiquetas y adjudicaciones; `claim` recortado a 300 caracteres también en la política y en el ledger.
14. **M13** (§8): el segundo posicional de `render_traice_checklist` pasa a ser `autonomy_effective`; `describe_gate` y `human_validation_summary` son públicas para que `methods.py` diga lo mismo que el checklist.
15. **README**: PR-D deja la nota "Limitación actual" reducida a lo que aún falta (el auditor estricto); la quita PR-E, como dice §10.
