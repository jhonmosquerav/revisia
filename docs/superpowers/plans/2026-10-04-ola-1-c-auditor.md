# Ola 1 · Pista E (auditor exigente: PR-E) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir `revisia audit` en un auditor que comprueba la **coherencia** de una corrida, no solo que sus ficheros existan: esquemas, ledger, plausibilidad temporal, aritmética del flujo PRISMA, decisiones humanas por registro atadas a su solicitud, umbrales del protocolo según lo que miden (D7), adjudicación de citas marcadas (D8), instantánea del protocolo (D13) y log de búsqueda. Cierra C3 en la parte del auditor, A11 y M5 en el auditor, y con él la Ola 1 de la auditoría 2026-09-03.

**Architecture:** `revisia/audit.py` pasa a ser el paquete `revisia/audit/` (spec §9.1): `model` (informe, `Status` con `N/A`), `artifacts` (loaders que nunca lanzan, `Loaded[T]`, `RunArtifacts`, `AuditContext`), `state` (`RunState`, `derive_state`), un módulo `checks_*` por familia y `render`. `__init__` guarda el registro ordenado de checks (`CheckSpec`) y `_run_one`, que hace al auditor *fail-closed*: una fila por check, siempre; un check que revienta es FAIL; un `N/A` nunca aparece sin algún FAIL. Se desarrolla en dos fases: la **fase 1** (Tareas 1-10) arranca desde PR-0 en paralelo con A, B, C y D y trabaja con los artefactos que ya existen; la **fase 2** (Tareas 11-16) se rebasa sobre PR-D y añade lo que consume los artefactos nuevos (`run.json`, `00_protocol/`, `01_search/`, `02_dedup/`, diarios, `llm_calls.jsonl`, etiquetas por registro). La Tarea 17 (controlador) integra la PR y cierra la ola.

**Tech Stack:** Python 3.13 (suite también en 3.11/3.12 con venv desechable), Pydantic v2 (`TypeAdapter`), PyYAML (`CSafeLoader` si existe), pytest, ruff + black (línea 100), uv, gh.

**Spec:** `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md`. Este plan cubre §9 (PR-E) con sus dos fases, más lo que exigen §3 (D7 umbrales según lo que miden, potencia del gold e intervalo de Wilson; D8 citas marcadas adjudicadas → WARN, sin adjudicar → FAIL; D13 corridas anteriores: FAIL en `protocol_snapshot`, auditables con las relaciones v0.7), §4 (contratos y las 18 relaciones de §4.4) y §10-§11 (topología y cierre de la ola). Lee §3 antes de empezar; D1-D14 no se reabren. Planes hermanos: `2026-10-04-ola-1-a-cimientos.md` (PR-0, PR-A, PR-B; su Tarea 5 crea el worktree de esta pista) y `2026-10-04-ola-1-b-reanudacion-hitl.md` (PR-C, PR-D; de él salen los artefactos que consume la fase 2).

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes y commits **en español**, con el tono del repo. Las docstrings explican el porqué y citan la auditoría ("auditoría 2026-09-03, C3") o la decisión del spec ("D7").
- Estilo: `ruff` (reglas `E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100). Ambos limpios. Si `ruff format` une dos líneas que caben en una, se acepta su versión (black la respeta).
- `from __future__ import annotations` al inicio de todo módulo nuevo, también en los de `tests/`.
- Compatibilidad con 3.11 (la suite corre en 3.11/3.12 con venv desechable): nada de `class X[T]` ni `def f[T]` de 3.12; los genéricos usan `TypeVar` + `Generic` con `# noqa: UP046`/`UP047` y el motivo.
- Tests offline, sin red y deterministas. Ningún test invoca `claude`, WeasyPrint real ni APIs. Las corridas salen del pipeline real con `ScriptedProvider` y `fetch_disponible` (`tests/fakes.py`, PR-0).
- El auditor **nunca lanza**: los loaders devuelven `Loaded` con el error y `_run_one` convierte cualquier excepción de un check en FAIL. **Una fila por check, siempre**; `N/A` solo cuando la etapa no se alcanzó o la raíz del check ya falló en otra fila.
- Constantes importadas, no duplicadas: `STAGES`, `JUDGMENT_STAGES`, `KNOWN_THRESHOLDS`, `GATED_STAGES`, `JOURNAL_PATHS`, `LEDGER_ACTIONS`, `GATE_DECISION_ACTIONS`, `HUMAN_ACTOR_PREFIX`, `AUTO_APPROVE_ACTOR`, `summarize_gates`, `recall_biased_label`, `compute_exclusion_breakdown`, las funciones de `metrics.py` y, en la fase 2, `SNAPSHOT_DIR` y `protocol_fingerprint` de `orchestration/snapshot.py`.
- Línea base: **fase 1, 364 tests recogidos** (`feat/ola1-contratos` con PR-0, plan A Tarea 5). **Fase 2: la suite de `feat/ola1-hitl-por-registro`** tras integrar PR-D (`N_D`; 499 según el plan B, lo confirma el controlador en la Tarea 11). Ningún test existente se borra salvo `_make_run` (spec §9.4); los que cambian de expectativa están en su tarea con el código exacto.
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider`; lint, `uv run ruff check . && uv run ruff format --check . && uv run black --check .`.
- Commits pequeños, al menos uno por tarea, en español con prefijo convencional (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`), terminados con la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Los implementadores no tocan** `CHANGELOG.md`, `README.md`, `AGENTS.md`, `docs/auditoria/` ni el spec: los actualiza el integrador en la Tarea 17, con el texto exacto que da esa tarea.
- **No tocar** `runs/` ni `protocols/<slug>/` distintos de `_TEMPLATE`. No cambiar `revisia.__version__` ni `pyproject.toml` (la 0.8.0 la publica el arquitecto, D13).
- `tests/` no es un paquete: los helpers compartidos se importan como `from fakes import ...`, `from audit_fixtures import ...` y `from hitl_helpers import ...` (pytest pone `tests/` en `sys.path`). `ruff` los clasifica como terceros: van en el bloque de terceros, después de `import pytest`/`import yaml`.
- Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base.

---

## Topología de ejecución (subagentes)

La Ola 1 son seis PRs apiladas, `0 → A → B → C → D → E`. Este plan cubre E, la última: se abre **una sola PR** al terminar la fase 2, con base `feat/ola1-hitl-por-registro`.

| Fase | Rama | Worktree | Se desarrolla desde | Tareas | En paralelo con |
|---|---|---|---|---|---|
| E · fase 1 | `feat/ola1-auditor` | `C:\revisia-wt\e` | `feat/ola1-contratos` (PR-0), creada en la Tarea 5 Step 7 del plan A | 1-10 | A, B, C y D |
| E · fase 2 | `feat/ola1-auditor` rebasada | `C:\revisia-wt\e` | `feat/ola1-hitl-por-registro` (PR-D integrada) | 11-16 | — |
| Integración | `feat/ola1-auditor` | `C:\revisia-wt\e` | — | 17 (controlador) | — |

Si el worktree no existe todavía (el plan A lo crea en su Tarea 5 Step 7), créalo antes de la Tarea 1:

```bash
git -C C:/revisia worktree add C:/revisia-wt/e -b feat/ola1-auditor feat/ola1-contratos
cd C:/revisia-wt/e && uv sync --extra dev && uv run pytest -p no:cacheprovider -q
```

Expected: 364 tests en verde. **Todas las tareas de este plan se ejecutan en `C:\revisia-wt\e`.**

Orden en el tiempo:

1. **Fase 1 (en paralelo con A-D):** Tareas 1 → 10. Solo usa artefactos que ya escribe el pipeline de PR-0 (manifiesto, ledger, `03`-`08`, entregable, gates); por eso, sin `run.json`, la aritmética es la de v0.7. La fixture de corrida real inyecta `fetch_fn=fetch_disponible` desde el principio: con el FT estricto de PR-B (D2) un registro sin texto en abierto ya no llega a extracción.
2. **Fase 2 (tras integrar PR-D):** Tarea 11 (rebase sobre PR-D; la fixture pasa a `correr_hasta`, porque `decision.yml` ya exige `request_sha256`), y Tareas 12 → 16 con los artefactos nuevos.
3. **Integración y cierre de la ola:** Tarea 17 (controlador): CHANGELOG, README, `AGENTS.md`, §11 de la auditoría, §14 del spec, matriz 3.13/3.11/3.12, criterio de cierre de §11 de punta a punta y `gh pr create`. Sin merge.

Solapes con las otras pistas y cómo se resuelven:

| Fichero | Pistas | Resolución |
|---|---|---|
| `revisia/cli.py` | A (`main`, `_cmd_validate`, `run`), C (`--resume`), E (`_cmd_audit`) | E solo toca `_cmd_audit` (icono de `N/A` y ancho de columna): el rebase de la Tarea 11 no tiene conflictos (verificado en un prototipo con PR-0..PR-D) |
| `revisia/metrics.py` | C/D (`compute_screening_metrics`), E (`kappa_from_matrix`, `wilson_interval`) | Hunks distintos; sin conflictos en el prototipo |
| `revisia/audit.py` → `revisia/audit/` | solo E | — |
| `tests/conftest.py` | solo E | A-D no lo crean (verificado en el plan A y en el prototipo de C/D) |
| `tests/test_audit.py` | solo E | — |
| `tests/test_pipeline_fake.py` | B, C, D, E (fase 2) | E solo añade al final dos tests de frontera y una afirmación en `test_paused_run_final_gate_falla_en_auditoria` (Tarea 16) |
| `CHANGELOG.md`, `README.md`, `AGENTS.md`, auditoría, spec | integrador | Un commit de docs en la Tarea 17, después del rebase |

**Ciclo por tarea:** implementador (subagente nuevo, TDD estricto: test rojo → código mínimo → verde → lint → commit) → revisor (subagente nuevo: primero cumplimiento del spec y de este plan, después calidad) → correcciones si las hay → siguiente tarea. La Tarea 17 la ejecuta el controlador. El controlador ejecuta de punta a punta sin pedir confirmación entre tareas; audita y corrige lo que encuentre. **El merge no lo hace nadie de este plan: lo decide el arquitecto.**

**Verificación del plan (hecha al escribirlo):** el código de las Tareas 1-10 se aplicó sobre PR-0 en una copia desechable, tarea a tarea, con la suite y el lint en verde en cada una (364 → 514 tests; también en 3.11). Las Tareas 11-16 se aplicaron sobre el prototipo final del plan B (PR-0..PR-D, sus Tareas 1-28 aplicadas, 499 tests) con la fase 1 rebasada encima: el rebase no tuvo conflictos, cada tarea dejó la suite y el lint en verde (742 al final, también en 3.11) y el criterio de cierre de §11 (Tarea 17 Step 9) pasó de punta a punta. Si PR-D cambia al integrarse algún nombre que este plan consume (lista en "Pendientes de conciliación"), el controlador lo concilia en la Tarea 11.

**Conteo de tests:** fase 1: 364 → 366 (T1) → 373 (T2) → 374 (T3) → 394 (T4) → 421 (T5) → 434 (T6) → 472 (T7) → 487 (T8) → 505 (T9) → **514** (T10). Fase 2, sobre `N_D` (la suite de PR-D; 499 según el plan B): `N_D + 150` tras el rebase (649) → `+1` (T11, 650) → `+25` (T12, 675) → `+17` (T13, 692) → `+23` (T14, 715) → `+25` (T15, 740) → `+2` (T16) = **`N_D + 243` (742)**.

**Entorno del worktree:** `uv sync --extra dev` (pytest, ruff y black están en el extra `dev`). El venv de desarrollo no instala `httpx`; ningún test lo necesita.

---

## Fase 1 · desde PR-0 (worktree `C:\revisia-wt\e`, rama `feat/ola1-auditor`)

### Task 1: Partición de `revisia/audit.py` en el paquete `revisia/audit/`

**Files:**
- Move: `revisia/audit.py` → `revisia/audit/__init__.py`
- Create: `revisia/audit/model.py`, `revisia/audit/render.py`
- Test: `tests/test_audit_paquete.py` (nuevo)

**Interfaces:**
- Consumes: el `revisia/audit.py` de hoy (505 líneas): `AuditCheck`, `AuditReport`, `run_audit`, `render_audit_md`, `_load_manifest`, `_read_ledger`, `_STATUS_ICON`.
- Produces (sin cambio de comportamiento; spec §9.1, primer commit):
  - `revisia.audit.model.AuditCheck(check_id: str, item_ref: str, status: str, detail: str)` (frozen)
  - `revisia.audit.model.AuditReport(run_dir: Path, checks: list[AuditCheck])` con `n_fail`, `n_warn`, `publishable`
  - `revisia.audit.render.render_audit_md(report: AuditReport) -> str`
  - `revisia.audit.__all__ = ["AuditCheck", "AuditReport", "render_audit_md", "run_audit"]`; `from revisia.audit import run_audit, render_audit_md, AuditReport, AuditCheck` sigue funcionando (lo usan `cli.py:308` y `tests/test_pipeline_fake.py`).

- [ ] **Step 1: Test que falla — crear `tests/test_audit_paquete.py`**

```python
"""El auditor es un paquete y conserva su API pública (spec 2026-10-04 §9.1)."""

from __future__ import annotations

from pathlib import Path

import revisia.audit as audit
from revisia.audit import AuditCheck, AuditReport, render_audit_md, run_audit
from revisia.audit.model import AuditCheck as AuditCheckModelo
from revisia.audit.model import AuditReport as AuditReportModelo
from revisia.audit.render import render_audit_md as render_modulo


def test_audit_es_un_paquete_con_la_api_de_siempre() -> None:
    assert Path(audit.__file__).name == "__init__.py"
    assert AuditCheck is AuditCheckModelo
    assert AuditReport is AuditReportModelo
    assert render_audit_md is render_modulo
    assert callable(run_audit)
    assert set(audit.__all__) >= {"AuditCheck", "AuditReport", "render_audit_md", "run_audit"}


def test_render_del_paquete_igual_que_antes(tmp_path) -> None:
    report = AuditReport(
        run_dir=tmp_path,
        checks=[AuditCheck("manifest", "PRISMA 27 / trAIce M2", "PASS", "ok")],
    )
    markdown = render_audit_md(report)
    assert "| manifest | PRISMA 27 / trAIce M2 | ✅ PASS | ok |" in markdown
    assert "APTA para preparar publicación" in markdown
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_paquete.py -v`
Expected: ERROR de colección, `ModuleNotFoundError: No module named 'revisia.audit.model'; 'revisia.audit' is not a package`.

- [ ] **Step 3: Mover el módulo al paquete**

```bash
mkdir -p revisia/audit
git mv revisia/audit.py revisia/audit/__init__.py
```

- [ ] **Step 4: Sacar las dataclasses y el render de `__init__.py`**

En `revisia/audit/__init__.py`, sustituir

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from revisia.config import JUDGMENT_STAGES
from revisia.orchestration.run_context import PROVENANCE_PIPELINE

_STATUS_ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}


@dataclass(frozen=True)
class AuditCheck:
    """Resultado de una verificación puntual de la auditoría."""

    check_id: str
    item_ref: str  # ítem PRISMA / trAIce que respalda la verificación
    status: str  # PASS | WARN | FAIL
    detail: str


@dataclass(frozen=True)
class AuditReport:
    """Informe completo de auditoría de una corrida."""

    run_dir: Path
    checks: list[AuditCheck]

    @property
    def n_fail(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def publishable(self) -> bool:
        return self.n_fail == 0


def _load_manifest(run_dir: Path) -> dict | None:
```

por

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml

from revisia.audit.model import AuditCheck, AuditReport
from revisia.audit.render import render_audit_md
from revisia.config import JUDGMENT_STAGES
from revisia.orchestration.run_context import PROVENANCE_PIPELINE

__all__ = ["AuditCheck", "AuditReport", "render_audit_md", "run_audit"]


def _load_manifest(run_dir: Path) -> dict | None:
```

En `revisia/audit/__init__.py`, sustituir

```python
            )

    return AuditReport(run_dir=run, checks=checks)


def render_audit_md(report: AuditReport) -> str:
    """Renderiza el informe de auditoría como Markdown."""
    verdict = (
        "**APTA para preparar publicación** (sin FAIL; resuelve los WARN y decláralos)."
        if report.publishable
        else "**NO publicable tal cual** (hay verificaciones FAIL)."
    )
    lines = [
        "# Auditoría de corrida · revisia",
        "",
        f"- Corrida: `{report.run_dir}`",
        f"- Resultado: {verdict}",
        f"- Verificaciones: {len(report.checks)} · FAIL={report.n_fail} · WARN={report.n_warn}",
        "",
        "| Verificación | Ítem de reporte | Estado | Evidencia |",
        "|---|---|---|---|",
    ]
    for check in report.checks:
        icon = _STATUS_ICON.get(check.status, "•")
        lines.append(
            f"| {check.check_id} | {check.item_ref} | {icon} {check.status} | {check.detail} |"
        )
    lines += [
        "",
        "> El auditor es determinista: verifica artefactos en disco contra PRISMA 2020, "
        "PRISMA-S y PRISMA-trAIce. Un PASS no sustituye el juicio del revisor humano.",
    ]
    return "\n".join(lines)
```

por

```python
            )

    return AuditReport(run_dir=run, checks=checks)
```

- [ ] **Step 5: Crear `model.py` y `render.py`**

Crear `revisia/audit/model.py`:

```python
"""Modelo del informe de auditoría (``AuditCheck``, ``AuditReport``)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AuditCheck:
    """Resultado de una verificación puntual de la auditoría."""

    check_id: str
    item_ref: str  # ítem PRISMA / trAIce que respalda la verificación
    status: str  # PASS | WARN | FAIL
    detail: str


@dataclass(frozen=True)
class AuditReport:
    """Informe completo de auditoría de una corrida."""

    run_dir: Path
    checks: list[AuditCheck]

    @property
    def n_fail(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def publishable(self) -> bool:
        return self.n_fail == 0
```

Crear `revisia/audit/render.py`:

```python
"""Informe de auditoría en Markdown (``<run_dir>/audit.md``)."""

from __future__ import annotations

from revisia.audit.model import AuditReport

_STATUS_ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}


def render_audit_md(report: AuditReport) -> str:
    """Renderiza el informe de auditoría como Markdown."""
    verdict = (
        "**APTA para preparar publicación** (sin FAIL; resuelve los WARN y decláralos)."
        if report.publishable
        else "**NO publicable tal cual** (hay verificaciones FAIL)."
    )
    lines = [
        "# Auditoría de corrida · revisia",
        "",
        f"- Corrida: `{report.run_dir}`",
        f"- Resultado: {verdict}",
        f"- Verificaciones: {len(report.checks)} · FAIL={report.n_fail} · WARN={report.n_warn}",
        "",
        "| Verificación | Ítem de reporte | Estado | Evidencia |",
        "|---|---|---|---|",
    ]
    for check in report.checks:
        icon = _STATUS_ICON.get(check.status, "•")
        lines.append(
            f"| {check.check_id} | {check.item_ref} | {icon} {check.status} | {check.detail} |"
        )
    lines += [
        "",
        "> El auditor es determinista: verifica artefactos en disco contra PRISMA 2020, "
        "PRISMA-S y PRISMA-trAIce. Un PASS no sustituye el juicio del revisor humano.",
    ]
    return "\n".join(lines)
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_paquete.py tests/test_audit.py -v`
Expected: PASS, 2 + 23 tests (los 23 de hoy, sin tocarlos).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 366 recogidos.

- [ ] **Step 7: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 8: Commit**

```bash
git add revisia/audit tests/test_audit_paquete.py
git commit -m "refactor(audit): el auditor pasa a ser el paquete revisia/audit/" -m "Primer commit de PR-E (spec 2026-10-04 §9.1): partición sin cambio de comportamiento. AuditCheck y AuditReport van a audit/model.py y render_audit_md a audit/render.py; run_audit sigue en audit/__init__.py. La API pública no cambia y los 23 tests del auditor pasan sin tocarlos." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `kappa_from_matrix` y `wilson_interval`, públicas en `revisia/metrics.py`

**Files:**
- Modify: `revisia/metrics.py` (`cohen_kappa`, l.91-104)
- Test: `tests/test_metrics_auditor.py` (nuevo)

**Interfaces:**
- Consumes: `confusion`, `mcc` (existentes).
- Produces (spec §9.1, "dos públicas nuevas"):
  - `revisia.metrics.kappa_from_matrix(tp: int, fp: int, fn: int, tn: int) -> float | None` — misma fórmula que `cohen_kappa`; `None` si `n=0` o `pe=1`.
  - `revisia.metrics.wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None` — `None` si `n <= 0`; extremos acotados a `[0, 1]`.
  - `cohen_kappa(pred, gold)` pasa a delegar en `kappa_from_matrix(*confusion(pred, gold))` (mismo resultado).

- [ ] **Step 1: Test que falla — crear `tests/test_metrics_auditor.py`**

```python
"""Funciones de métricas públicas para el auditor (spec 2026-10-04 §9.1, D7)."""

from __future__ import annotations

import math

import pytest

from revisia.metrics import cohen_kappa, confusion, kappa_from_matrix, mcc, wilson_interval


@pytest.mark.parametrize(
    ("pred", "gold"),
    [
        ([True, True, False, False], [True, False, True, False]),
        ([True, True, True, False, False], [True, True, False, False, False]),
        ([True, True, True], [True, False, True]),
    ],
)
def test_kappa_from_matrix_coincide_con_cohen_kappa(pred, gold) -> None:
    assert kappa_from_matrix(*confusion(pred, gold)) == cohen_kappa(pred, gold)


def test_kappa_from_matrix_indefinido_y_no_informativo() -> None:
    assert kappa_from_matrix(0, 0, 0, 0) is None
    assert kappa_from_matrix(5, 0, 0, 0) is None  # pe = 1
    # IA de una sola clase con gold mixto: número (0.0), no None (A11).
    assert kappa_from_matrix(3, 2, 0, 0) == 0.0


def test_kappa_c3_imposible_con_fn_cero() -> None:
    # Auditoría 2026-09-03, C3: con n=47 y FN=0 ninguna matriz da κ=0.75 y MCC=0.71.
    pares = set()
    for tp in range(1, 47):
        for fp in range(0, 47 - tp):
            tn = 47 - tp - fp
            kappa, phi = kappa_from_matrix(tp, fp, 0, tn), mcc(tp, fp, 0, tn)
            if kappa is not None and phi is not None:
                pares.add((round(kappa, 2), round(phi, 2)))
    assert pares and (0.75, 0.71) not in pares


def test_wilson_interval_valores_conocidos() -> None:
    bajo, alto = wilson_interval(33, 34)
    assert math.isclose(bajo, 0.8508, abs_tol=1e-4)
    assert math.isclose(alto, 0.9948, abs_tol=1e-4)
    bajo, alto = wilson_interval(5, 5)
    assert alto == 1.0
    assert math.isclose(bajo, 0.5655, abs_tol=1e-4)
    bajo, alto = wilson_interval(0, 10)
    assert bajo == 0.0 and math.isclose(alto, 0.2775, abs_tol=1e-4)


def test_wilson_interval_sin_datos_y_z_configurable() -> None:
    assert wilson_interval(0, 0) is None
    ancho_95 = wilson_interval(8, 10)
    ancho_99 = wilson_interval(8, 10, z=2.576)
    assert ancho_99[0] < ancho_95[0] and ancho_99[1] > ancho_95[1]
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_metrics_auditor.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'kappa_from_matrix' from 'revisia.metrics'`.

- [ ] **Step 3: Implementar**

En `revisia/metrics.py`, sustituir

```python
    return ((tp * tn) - (fp * fnw)) / denom if denom else None


def cohen_kappa(pred: list[bool], gold: list[bool]) -> float | None:
    """Cohen's kappa entre dos clasificaciones binarias.
```

por

```python
    return ((tp * tn) - (fp * fnw)) / denom if denom else None


def kappa_from_matrix(tp: int, fp: int, fn: int, tn: int) -> float | None:
    """Cohen's kappa a partir de la matriz de confusión.

    Pública para que el auditor recalcule κ desde la matriz de
    ``metrics.json`` sin rehacer las listas de etiquetas (spec 2026-10-04
    §9.1; auditoría 2026-09-03, C3: κ=0.75 con MCC=0.71 y FN=0 es imposible).
    ``None`` si ``n=0`` o si ``pe=1`` (ambas clasificaciones constantes en la
    misma clase).
    """
    n = tp + fp + fn + tn
    if n == 0:
        return None
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    return (po - pe) / (1 - pe) if (1 - pe) else None


def cohen_kappa(pred: list[bool], gold: list[bool]) -> float | None:
    """Cohen's kappa entre dos clasificaciones binarias.
```

En `revisia/metrics.py`, sustituir

```python
    sola de las dos sea de una sola clase.
    """
    tp, fp, fn, tn = confusion(pred, gold)
    n = tp + fp + fn + tn
    if n == 0:
        return None
    po = (tp + tn) / n
    pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
    return (po - pe) / (1 - pe) if (1 - pe) else None


def compute_screening_metrics(
```

por

```python
    sola de las dos sea de una sola clase.
    """
    return kappa_from_matrix(*confusion(pred, gold))


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Intervalo de Wilson para una proporción ``k/n`` (95 % con ``z=1.96``).

    El auditor lo informa junto al recall (D7): con pocos positivos en el gold
    un recall de 1.0 es compatible con valores muy por debajo del umbral, y el
    intervalo lo hace visible. A diferencia del intervalo de Wald, no colapsa a
    un punto cuando ``k`` es 0 o ``n``. ``None`` si ``n <= 0``.
    """
    if n <= 0:
        return None
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centro = (p + z2 / (2 * n)) / denom
    radio = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, centro - radio), min(1.0, centro + radio)


def compute_screening_metrics(
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_metrics_auditor.py tests/test_metrics.py -v`
Expected: PASS (7 nuevos; los de `test_metrics.py` siguen en verde).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 373 recogidos.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 6: Commit**

```bash
git add revisia/metrics.py tests/test_metrics_auditor.py
git commit -m "feat(metrics): kappa_from_matrix y wilson_interval públicas para el auditor" -m "El auditor recalcula κ desde la matriz de metrics.json (C3: κ=0.75 con MCC=0.71 y FN=0 es imposible) e informa el intervalo de Wilson al 95 % del recall (D7). cohen_kappa delega en kappa_from_matrix. Spec 2026-10-04 §9.1." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Corrida real del pipeline como fixture (`tests/conftest.py`, `tests/audit_fixtures.py`)

**Files:**
- Create: `tests/conftest.py`, `tests/audit_fixtures.py`
- Modify: `tests/test_audit.py` (se elimina `_make_run`, l.12-87; los 23 tests pasan a la corrida real con las mismas afirmaciones)
- Test: `tests/test_corrida_auditoria.py` (nuevo)

**Interfaces:**
- Consumes: `fakes.ScriptedProvider(model=..., *, palabras=None)`, `fakes.fetch_disponible` (PR-0); `revisia.orchestration.pipeline.run_pipeline(protocol, protocol_dir, run_ctx, *, max_results, search_fn, fetch_fn, gold_labels)` y `pipeline.build_provider` (monkeypatch); `RunContext(slug, runs_root, timestamp)`; `GATED_STAGES`, `JOURNAL_PATHS` (PR-0); `revisia.metrics.kappa_from_matrix`, `mcc`, `wmcc` (Tarea 2).
- Produces:
  - `tests/conftest.py`: `DEMO`, `REGISTROS_AUDITORIA` (7 registros: 1 duplicado por DOI, 2 "irrelevante", 1 "secundario"), `GOLD_AUDITORIA` (4 relevantes, 2 irrelevantes), `PALABRAS_FT`, `DECISION_HUMANA`, `busqueda_auditoria(_query: str, n: int) -> list[SearchRecord]`, `proveedor_auditoria(cfg: ProviderConfig) -> ScriptedProvider`; fixtures `_corrida_auditoria` (sesión) y `corrida` (copia por test en `tmp_path/runs/<slug>-<timestamp>`).
  - `tests/audit_fixtures.py`: `auditar(run_dir: Path) -> AuditReport` (con el invariante `N/A ⇒ FAIL` y una fila por check), `fila(report, check_id) -> AuditCheck`, `edit_json(path, fn)`, `edit_yaml(path, fn)`, `edit_ledger(run_dir, fn)`, `editar_protocolo(run_dir, fn)`, `editar_llamadas(run_dir, fn)`, `reetiquetar_llamadas(run_dir, *, provider="agent", deterministic=False, inicio=None, paso=None)`, `primera_llamada(run_dir) -> datetime`, `comprimir_llamadas(run_dir, *, ventana=timedelta(microseconds=1300))`, `metricas_validas(tp, fp, fn, tn, *, fn_weight=10.0) -> dict`, `escribir_metricas(run_dir, metrics)`, `pausar_en_screening_ft(run_dir)`. Los editores tocan todas las copias de un dato a la vez (manifiesto, `llm_calls.jsonl`, diarios, `00_protocol/`) para que en la fase 2 rompan solo la relación que el test quiere romper.

La corrida (demo con `ScriptedProvider` por modelo y `fetch_disponible`): 7 identificados (OpenAlex 4, Crossref 3), 1 duplicado, 6 cribados, 2 exclusiones IA en T/A, 4 evaluados a texto completo, 1 exclusión IA a texto completo ("secundario", solo para el proveedor FT `fake-1`), 3 incluidos, 24 llamadas, 5 gates aprobados por `human:revisora` (los `decision.yml` se escriben antes de correr, como en `test_pipeline_fake.py`). El timestamp es UTC real: sin `run.json`, el auditor lo usa como límite inferior de las marcas de tiempo.

- [ ] **Step 1: Test que falla — crear `tests/test_corrida_auditoria.py`**

```python
"""La corrida real de ``tests/conftest.py`` tiene lo que los tests del auditor necesitan."""

from __future__ import annotations

import json

import yaml


def test_corrida_real_tiene_exclusiones_ia_y_gold_de_dos_clases(corrida) -> None:
    manifest = yaml.safe_load((corrida / "manifest.yml").read_text(encoding="utf-8"))
    counts = manifest["counts"]
    assert (counts["identified"], counts["duplicates_removed"], counts["screened"]) == (7, 1, 6)
    assert (counts["excluded_ta"], counts["excluded_ft"], counts["included"]) == (2, 1, 3)
    assert counts["identified_by_source"] == {"OpenAlex": 4, "Crossref": 3}
    # 6 registros × 2 miembros T/A + 4 FT + 3 extracciones + 1 doble + 3 RoB + 1 síntesis.
    assert len(manifest["llm_calls"]) == 24
    assert {c["provider"] for c in manifest["llm_calls"]} == {"fake"}
    metrics = json.loads((corrida / "03_screening" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["tp"] > 0 and metrics["tn"] > 0  # gold de dos clases
    ledger = (corrida / "decisions_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    actores = {json.loads(line)["actor"] for line in ledger}
    assert actores == {"human:revisora"}
    assert len(ledger) == 5
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_corrida_auditoria.py -v`
Expected: ERROR, `fixture 'corrida' not found`.

- [ ] **Step 3: Crear `tests/conftest.py`**

```python
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
```

- [ ] **Step 4: Crear `tests/audit_fixtures.py`**

```python
"""Ayudas de los tests del auditor (spec 2026-10-04 §9.4).

Contiene solo lo que el pipeline no puede producir: helpers de edición de una
corrida (para romper una relación cada vez) y ``auditar``, que comprueba en
cada llamada el invariante del auditor (**si hay algún N/A, hay al menos un
FAIL**: un N/A nunca puede ocultar nada en una corrida publicable, §9.2) y que
hay una sola fila por check.

Los helpers de edición sirven tanto para las corridas de la fase 1 de PR-E
(solo manifiesto) como para las de la Ola 1 (``llm_calls.jsonl``, diarios y
``00_protocol/``): editan todas las copias de un dato a la vez, para romper
solo la relación que el test quiere romper.

Uso (``tests/`` está en ``sys.path`` porque no es un paquete)::

    from audit_fixtures import auditar, edit_json, fila
"""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from revisia.audit import AuditCheck, AuditReport, run_audit
from revisia.metrics import ScreeningMetrics, kappa_from_matrix, mcc, wmcc
from revisia.schemas.artifacts import JOURNAL_PATHS


def auditar(run_dir: Path) -> AuditReport:
    """``run_audit`` + el invariante ``N/A ⇒ FAIL`` y una fila por check."""
    report = run_audit(run_dir)
    ids = [c.check_id for c in report.checks]
    assert len(ids) == len(set(ids)), f"filas repetidas: {ids}"
    if any(c.status == "N/A" for c in report.checks):
        assert report.n_fail > 0, "N/A sin ningún FAIL: el N/A estaría ocultando algo"
    return report


def fila(report: AuditReport, check_id: str) -> AuditCheck:
    """La fila ``check_id`` del informe (falla si no está)."""
    matches = [c for c in report.checks if c.check_id == check_id]
    assert matches, f"sin fila {check_id!r}: {[c.check_id for c in report.checks]}"
    return matches[0]


def _apply(data: Any, fn: Callable[[Any], Any]) -> Any:
    """Aplica ``fn``: muta ``data`` en sitio o devuelve un mapa/lista que lo sustituye.

    Cualquier otro valor devuelto se ignora, para que ``lambda d: d.pop("k")``
    funcione como edición en sitio cuando el valor extraído es un escalar. Para
    borrar un mapa o una lista anidados usa ``del`` en una función: devolverlos
    sustituiría el documento entero.
    """
    result = fn(data)
    return result if isinstance(result, dict | list) else data


def edit_json(path: Path, fn: Callable[[Any], Any]) -> None:
    """Carga ``path``, aplica ``fn`` (ver :func:`_apply`) y lo reescribe."""
    data = _apply(json.loads(path.read_text(encoding="utf-8")), fn)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def edit_yaml(path: Path, fn: Callable[[Any], Any]) -> None:
    """Como :func:`edit_json`, para YAML (conserva el orden de claves)."""
    data = _apply(yaml.safe_load(path.read_text(encoding="utf-8")), fn)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, items: list[dict]) -> None:
    text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    path.write_text(text, encoding="utf-8")


def edit_ledger(run_dir: Path, fn: Callable[[list[dict]], Any]) -> None:
    """Edita ``decisions_ledger.jsonl`` como lista de dicts (una línea por entrada)."""
    path = run_dir / "decisions_ledger.jsonl"
    _write_jsonl(path, _apply(_read_jsonl(path), fn))


def editar_protocolo(run_dir: Path, fn: Callable[[dict], Any]) -> None:
    """Edita el protocolo registrado: ``manifest.protocol`` y, si existe, la
    instantánea ``00_protocol/protocol.yml`` (Ola 1), para que el test no
    dependa de qué fuente lea el auditor."""
    manifest = run_dir / "manifest.yml"
    if manifest.exists():
        edit_yaml(manifest, lambda m: fn(m["protocol"]))
    snapshot = run_dir / "00_protocol" / "protocol.yml"
    if snapshot.exists():
        edit_yaml(snapshot, fn)


def _llamadas(run_dir: Path) -> list[dict]:
    jsonl = run_dir / "llm_calls.jsonl"
    if jsonl.exists():
        return _read_jsonl(jsonl)
    manifest = yaml.safe_load((run_dir / "manifest.yml").read_text(encoding="utf-8"))
    return list(manifest["llm_calls"])


def editar_llamadas(run_dir: Path, fn: Callable[[list[dict]], Any]) -> None:
    """Edita las llamadas IA en todas sus copias a la vez.

    ``fn`` recibe la lista de llamadas (las de ``llm_calls.jsonl`` si existe; si
    no, las del manifiesto) y la muta o devuelve otra. Se reescriben
    ``llm_calls.jsonl``, las ``metas`` de los diarios que citaban cada llamada
    (relación 12 de §4.4) y el manifiesto, con ``models_used`` y
    ``deterministic_token_level`` recalculados.
    """
    old = _llamadas(run_dir)
    new = _apply(copy.deepcopy(old), fn)
    jsonl = run_dir / "llm_calls.jsonl"
    if jsonl.exists():
        _write_jsonl(jsonl, new)
        replacement = {json.dumps(o, sort_keys=True): n for o, n in zip(old, new, strict=False)}
        for rel in JOURNAL_PATHS.values():
            path = run_dir / rel
            if path.exists():
                entries = _read_jsonl(path)
                for entry in entries:
                    entry["metas"] = [
                        replacement.get(json.dumps(m, sort_keys=True), m) for m in entry["metas"]
                    ]
                _write_jsonl(path, entries)
    manifest_path = run_dir / "manifest.yml"
    if manifest_path.exists():

        def _manifest(manifest: dict) -> None:
            manifest["llm_calls"] = new
            manifest["models_used"] = sorted({f"{c['provider']}:{c['model']}" for c in new})
            manifest["deterministic_token_level"] = all(c["deterministic"] for c in new)

        edit_yaml(manifest_path, _manifest)


def reetiquetar_llamadas(
    run_dir: Path,
    *,
    provider: str = "agent",
    deterministic: bool = False,
    inicio: datetime | None = None,
    paso: timedelta | None = None,
) -> None:
    """Reescribe las llamadas como si vinieran de otro proveedor (coherente).

    Con ``inicio`` y ``paso``, la llamada ``i`` pasa a ``inicio + i·paso`` (para
    simular ráfagas o pausas).
    """

    def _editar(calls: list[dict]) -> None:
        for i, call in enumerate(calls):
            call.update(provider=provider, deterministic=deterministic)
            if inicio is not None and paso is not None:
                call["timestamp_utc"] = (inicio + i * paso).isoformat()

    editar_llamadas(run_dir, _editar)


def primera_llamada(run_dir: Path) -> datetime:
    """Marca de tiempo de la primera llamada IA de la corrida."""
    return datetime.fromisoformat(_llamadas(run_dir)[0]["timestamp_utc"])


def comprimir_llamadas(run_dir: Path, *, ventana: timedelta = timedelta(microseconds=1300)) -> None:
    """Síntoma C3: todas las llamadas (no fake) dentro de ``ventana`` (1,3 ms)."""
    n = len(_llamadas(run_dir))
    reetiquetar_llamadas(run_dir, inicio=primera_llamada(run_dir), paso=ventana / max(n - 1, 1))


def metricas_validas(tp: int, fp: int, fn: int, tn: int, *, fn_weight: float = 10.0) -> dict:
    """Un ``ScreeningMetrics`` válido y coherente con su matriz (como ``model_dump``)."""

    def _ratio(num: int, den: int) -> float | None:
        return num / den if den else None

    return ScreeningMetrics(
        n=tp + fp + fn + tn,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        recall=_ratio(tp, tp + fn),
        lost_evidence=_ratio(fn, tp + fn),
        precision=_ratio(tp, tp + fp),
        mcc=mcc(tp, fp, fn, tn),
        wmcc=wmcc(tp, fp, fn, tn, fn_weight=fn_weight),
        wmcc_fn_weight=fn_weight,
        cohen_kappa=kappa_from_matrix(tp, fp, fn, tn),
    ).model_dump()


def escribir_metricas(run_dir: Path, metrics: dict) -> None:
    """Sustituye ``03_screening/metrics.json``."""
    path = run_dir / "03_screening" / "metrics.json"
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def pausar_en_screening_ft(run_dir: Path) -> None:
    """Deja la corrida como si se hubiera detenido en el gate FT (fase 1 de PR-E).

    Lo que el pipeline aún no habría escrito desaparece: la decisión FT, los
    gates posteriores, las etapas posteriores, el manifiesto y el desglose de
    exclusiones (se escribe tras aprobar el gate FT).
    """
    edit_ledger(run_dir, lambda entries: [e for e in entries if e["stage"] == "screening_ta"])
    (run_dir / "screening_ft" / "decision.yml").unlink()
    for gate in ("extraccion", "rob", "reporte"):
        shutil.rmtree(run_dir / gate)
    for rel in ("05_extraction", "06_synthesis", "07_rob", "08_meta", "deliverable"):
        shutil.rmtree(run_dir / rel)
    (run_dir / "manifest.yml").unlink()
    (run_dir / "03_screening" / "exclusions.json").unlink()
```

- [ ] **Step 5: Verificar la fixture**

Run: `uv run pytest -p no:cacheprovider tests/test_corrida_auditoria.py -v`
Expected: PASS, 1 test.

- [ ] **Step 6: `tests/test_audit.py` sobre la corrida real (adiós a `_make_run`)**

Las afirmaciones no cambian todavía: el auditor sigue siendo el de hoy y la corrida real lo satisface igual que `_make_run`. Los cambios de expectativa de §9.4 llegan con cada check (Tareas 4, 5 y 8).

Sustituir el contenido completo de `tests/test_audit.py` por:

```python
"""Tests de la auditoría post-corrida (transparencia metodológica verificable).

Corren sobre ``corrida`` (``tests/conftest.py``): una corrida real del
pipeline con decisiones humanas, copiada a ``tmp_path`` en cada test.
"""

from __future__ import annotations

import json

from audit_fixtures import auditar, edit_ledger, edit_yaml, fila

from revisia.audit import render_audit_md


def test_audit_corrida_completa_es_publicable(corrida) -> None:
    report = auditar(corrida)
    assert report.n_fail == 0
    assert report.publishable
    statuses = {c.check_id: c.status for c in report.checks}
    assert statuses["manifest"] == "PASS"
    assert statuses["prompts"] == "PASS"
    assert statuses["hitl"] == "PASS"
    assert statuses["deliverable"] == "PASS"
    assert statuses["gold"] == "PASS"
    assert statuses["registration"] == "PASS"
    assert statuses["final_gate"] == "PASS"
    markdown = render_audit_md(report)
    assert "APTA" in markdown
    assert "trAIce M8" in markdown


def _sin_humanos(entries: list[dict]) -> None:
    for entry in entries:
        entry["actor"] = "agent:screener"


def test_audit_sin_decisiones_humanas_advierte_hitl(corrida) -> None:
    edit_ledger(corrida, _sin_humanos)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "WARN"
    assert "NO publicable sin revisión humana" in hitl.detail


def test_audit_sin_gold_advierte(corrida) -> None:
    (corrida / "03_screening" / "metrics.json").unlink()
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_corrida_vacia_falla(tmp_path) -> None:
    run = tmp_path / "runs" / "vacia"
    run.mkdir(parents=True)
    report = auditar(run)
    assert report.n_fail >= 2  # manifest + ledger + deliverable
    assert not report.publishable
    assert "NO publicable" in render_audit_md(report)


def test_cli_audit_escribe_informe(corrida, tmp_path, capsys) -> None:
    from revisia.cli import main

    assert main(["audit", str(corrida)]) == 0
    assert (corrida / "audit.md").exists()
    out = capsys.readouterr().out
    assert "APTA" in out

    empty = tmp_path / "runs" / "vacia"
    empty.mkdir(parents=True)
    assert main(["audit", str(empty)]) == 1


def test_audit_fails_on_reconstruction_provenance(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(provenance="reconstruction"))
    report = auditar(corrida)
    assert fila(report, "provenance").status == "FAIL"
    assert report.publishable is False


def _sin_procedencia(manifest: dict) -> None:
    del manifest["provenance"]


def test_audit_sin_procedencia_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", _sin_procedencia)
    check = fila(auditar(corrida), "provenance")
    assert check.status == "FAIL"
    assert "ausente" in check.detail


def test_audit_procedencia_pipeline_pasa(corrida) -> None:
    assert fila(auditar(corrida), "provenance").status == "PASS"


def test_audit_sin_manifiesto_no_duplica_fail_de_procedencia(corrida) -> None:
    (corrida / "manifest.yml").unlink()
    report = auditar(corrida)
    assert "provenance" not in {c.check_id for c in report.checks}


def _sin_reporte(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e["stage"] != "reporte"]


def test_audit_sin_decision_de_reporte_falla_gate_final(corrida) -> None:
    edit_ledger(corrida, _sin_reporte)
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "pausada o incompleta" in final_gate.detail
    assert report.publishable is False


def _set_ultima_decision_reporte(run, *, action: str, actor: str) -> None:
    """Reescribe la entrada `reporte` del ledger de la corrida."""

    def _editar(entries: list[dict]) -> None:
        for entry in entries:
            if entry["stage"] == "reporte":
                entry["action"] = action
                entry["actor"] = actor

    edit_ledger(run, _editar)


def test_audit_reporte_rechazado_falla_gate_final(corrida) -> None:
    _set_ultima_decision_reporte(corrida, action="reject", actor="human:revisora")
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "rechazado" in final_gate.detail
    assert "human:revisora" in final_gate.detail
    assert report.publishable is False


def test_audit_reporte_aprobado_pasa_gate_final(corrida) -> None:
    assert fila(auditar(corrida), "final_gate").status == "PASS"


def test_audit_gate_final_auto_approve_no_es_humano_advierte(corrida) -> None:
    # `--auto-approve` sin decision.yml deja actor "auto-approve (demo)": no es
    # aprobación humana, así que no puede ser PASS (revisión final 2026-09-25).
    _set_ultima_decision_reporte(corrida, action="approve", actor="auto-approve (demo)")
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "WARN"
    assert "no lo aprobó un humano" in final_gate.detail
    assert "auto-approve (demo)" in final_gate.detail
    assert report.publishable  # WARN no bloquea publicabilidad, a diferencia de FAIL


def test_audit_gate_final_auto_proceed_advierte(corrida) -> None:
    # `reporte` en A2/A3 se auto-ejecuta y notifica (agent:reporte): tampoco es
    # una decisión humana.
    _set_ultima_decision_reporte(corrida, action="auto-proceed", actor="agent:reporte")
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "WARN"
    assert "no lo aprobó un humano" in final_gate.detail
    assert "agent:reporte" in final_gate.detail


def test_audit_gate_final_accion_desconocida_falla(corrida) -> None:
    _set_ultima_decision_reporte(corrida, action="otra-cosa", actor="human:revisor")
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "Acción desconocida" in final_gate.detail
    assert "otra-cosa" in final_gate.detail


def test_audit_sin_ledger_no_duplica_fail_de_final_gate(corrida) -> None:
    # El ledger ausente ya produce un FAIL propio (§3); final_gate no debe
    # añadir un segundo FAIL redundante (mismo criterio que "provenance" con
    # manifest ausente).
    (corrida / "decisions_ledger.jsonl").unlink()
    report = auditar(corrida)
    assert "final_gate" not in {c.check_id for c in report.checks}
    assert fila(report, "ledger").status == "FAIL"


def test_audit_ledger_vacio_no_duplica_fail_de_final_gate(corrida) -> None:
    (corrida / "decisions_ledger.jsonl").write_text("", encoding="utf-8")
    report = auditar(corrida)
    assert "final_gate" not in {c.check_id for c in report.checks}


def _escribir_metricas(run, metrics: dict) -> None:
    (run / "03_screening" / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")


def test_audit_gold_kappa_no_calculable_advierte(corrida) -> None:
    _escribir_metricas(corrida, {"recall": 1.0, "cohen_kappa": None})
    gold = fila(auditar(corrida), "gold")
    assert gold.status == "WARN"  # antes: PASS con κ inventado
    assert "no calculable" in gold.detail


def test_audit_gold_matriz_con_valor_null_advierte(corrida) -> None:
    """``tp``/``fp``/``fn``/``tn`` presentes pero con algún valor ``null`` (no
    numérico): la matriz debe tratarse como ilegible en vez de romper la
    auditoría con un TypeError al sumar ``None`` con ``int``."""
    _escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.5, "mcc": 0.4, "tp": None, "fp": 2, "fn": 0, "tn": 0},
    )
    gold = fila(auditar(corrida), "gold")
    assert gold.status == "WARN"
    assert "matriz de confusión ilegible" in gold.detail


def test_audit_ia_una_sola_clase_con_gold_mixto_advierte(corrida) -> None:
    """Caso A11 (decisión D6): con matriz (tp=3, fp=2, fn=0, tn=0) el gold es
    mixto (3 relevantes, 2 irrelevantes) pero la IA asignó una sola clase
    (siempre "relevante": fn+tn=0) — kappa=0.0 (no None) y mcc=None no debe
    pasar como PASS; hay que mirar mcc y la matriz, no solo κ."""
    _escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.0, "mcc": None, "tp": 3, "fp": 2, "fn": 0, "tn": 0},
    )
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_una_sola_clase_con_matriz_advierte(corrida) -> None:
    """Caso real de los ``metrics.json`` de v0.6.0: matriz completa con gold de
    una sola clase (todo relevante: tp=3, fn=2, fp=0, tn=0 → tn+fp == 0), con
    mcc=0.0 y kappa numérico (ninguno de los dos es None). El chequeo de
    ``gold_una_sola_clase`` sobre la matriz debe advertir igual, porque un
    gold sin la clase "irrelevante" no es informativo aunque mcc/kappa den
    un número."""
    _escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.0, "mcc": 0.0, "tp": 3, "fp": 0, "fn": 2, "tn": 0},
    )
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_mcc_none_formato_antiguo_sin_matriz_advierte(corrida) -> None:
    """``metrics.json`` de formato antiguo (sin tp/fp/fn/tn): sin matriz no se
    puede evaluar si el gold o la IA son de una sola clase, así que la
    decisión se apoya solo en que mcc esté explícitamente en null; sigue
    siendo WARN."""
    _escribir_metricas(corrida, {"recall": 1.0, "cohen_kappa": 0.42, "mcc": None})
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_sano_con_matriz_completa_pasa(corrida) -> None:
    _escribir_metricas(
        corrida,
        {"recall": 0.8, "cohen_kappa": 0.75, "mcc": 0.6, "tp": 4, "fp": 1, "fn": 1, "tn": 4},
    )
    assert fila(auditar(corrida), "gold").status == "PASS"
```

- [ ] **Step 7: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit.py -v`
Expected: PASS, 23 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 374 recogidos (pytest no recoge `conftest.py` ni `audit_fixtures.py`).

- [ ] **Step 8: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 9: Commit**

```bash
git add tests/conftest.py tests/audit_fixtures.py tests/test_audit.py tests/test_corrida_auditoria.py
git commit -m "test(audit): corrida real del pipeline como fixture del auditor" -m "tests/conftest.py genera una vez por sesión una corrida del demo con ScriptedProvider (exclusiones IA en T/A y a texto completo, gold de dos clases) y fetch_disponible, con los decision.yml humanos escritos antes de correr; cada test recibe su copia. Se elimina _make_run, que construía una corrida incoherente que el auditor nuevo rechazaría por schemas y arithmetic. tests/audit_fixtures.py: auditar (invariante N/A ⇒ FAIL), fila y editores que tocan todas las copias de un dato. Spec 2026-10-04 §9.4." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Infraestructura: carga que nunca lanza, estado de la corrida, `N/A` y registro fail-closed

**Files:**
- Modify: `revisia/audit/model.py`, `revisia/audit/render.py`, `revisia/audit/__init__.py` (contenido completo)
- Create: `revisia/audit/state.py`, `revisia/audit/artifacts.py`, `revisia/audit/checks_provenance.py`, `revisia/audit/checks_hitl.py`, `revisia/audit/checks_flow.py`, `revisia/audit/checks_quality.py`, `revisia/audit/checks_search.py`
- Modify: `revisia/cli.py` (`_cmd_audit`, l.306-326: icono de `N/A` y ancho de columna)
- Modify: `tests/test_audit.py` (los tres `…no_duplica…`: de "id ausente" a `N/A`, spec §9.4)
- Test: `tests/test_audit_infra.py` (nuevo)

**Interfaces:**
- Consumes: `summarize_gates`, `DecisionEntry` (PR-0); `RunInfo`, `GateSummary`, `GATED_STAGES` (PR-0); `STAGES`, `ReviewProtocol` (`config.py`); `HumanDecision` (`orchestration/hitl.py`); `ScreeningMetrics`, `ExclusionBreakdown`, `ExtractionAgreement`, `MetaAnalysisResult`, `PrismaCounts`, `RunMeta` y los esquemas de `revisia/schemas/` para validar.
- Produces:
  - `revisia.audit.model`: `Status = Literal["PASS", "WARN", "FAIL", "N/A"]`; `STATUS_ICON: dict[str, str]` (`N/A` → ➖); `Verdict = tuple[Status, str]`; `AuditCheck(check_id, item_ref, status: Status, detail)`; `AuditReport(run_dir, checks, state: RunState | None = None)` + `n_fail`, `n_warn`, `n_na`, `publishable` (`n_fail == 0`).
  - `revisia.audit.state`: `RunStateStatus = Literal["completed", "paused", "rejected", "interrupted", "unknown"]`; `RunState(status, reached: frozenset[str], pending_stage: str | None = None)` + `describe() -> str`, `na_detail() -> str` ("no aplica: corrida en pausa en `screening_ft`; se verificará al reanudar."); `derive_state(*, run_info: RunInfo | None, gates: Mapping[str, GateSummary], requests: Set[str], ledger_ok: bool) -> RunState`.
  - `revisia.audit.artifacts`: `Loaded[T](path: str, present: bool, value: T | None = None, error: str | None = None)` + `ok`; `SearchFailure`; `format_validation(exc, *, limit=3) -> str`; `read_text`, `read_json(run_dir, rel, *, root=(dict, list))`, `read_yaml(run_dir, rel, *, root=dict)`, `read_jsonl(run_dir, rel) -> Loaded[list[tuple[int, Any]]]` (nunca lanzan); `validate(loaded, adapter) -> Loaded[T]`; `ARTIFACT_ADAPTERS: dict[str, TypeAdapter]`, `MANIFEST_ADAPTERS: dict[str, TypeAdapter]`; `RunArtifacts(run_dir)` con `exists`, `text`, `json`, `yaml`, `jsonl`, `artifact(rel)`, `decision(gate)`, `run_info()`; `load_run(run_dir) -> RunArtifacts`; `LedgerView(present, entries, errors, read_error)` + `usable`, `decisions`; `AuditContext(artifacts)` con `manifest`, `manifest_dict`, `manifest_section(key)`, `llm_calls`, `ledger`, `gates`, `requests`, `run_info`, `state`, `protocol`.
  - `revisia.audit`: `CheckSpec(check_id: str, item_ref: str, stage: str | None, fn: Callable[[AuditContext], Verdict])`; `CHECKS: tuple[CheckSpec, ...]`; `_run_one(spec, ctx) -> AuditCheck`; `_enforce_invariant(checks) -> list[AuditCheck]`; `run_audit(run_dir) -> AuditReport`.
  - `revisia.audit.render._md_cell(text) -> str` (escapa `|`, saltos de línea → `<br>`).

Los checks de hoy se **portan** a sus módulos con la misma semántica (salvo `N/A`): las Tareas 5-9 los endurecen. Reglas de `N/A` (spec §9.2): si la etapa del check no se alcanzó, o si su raíz ya dio FAIL en otra fila (`provenance`/`prompts` sin manifiesto, `hitl`/`final_gate` sin ledger). `derive_state`: `unknown` si el ledger no sirve y no hay `run.json` (se exige todo); `rejected`; `completed` si `reporte` pasó (`approve` o `auto-proceed`; quién decidió lo juzga `final_gate`); `interrupted` si `run.json` lo dice; si no, el primer gate sin decisión: `paused` con `review_request.yml`, `interrupted` sin ella. `reached` = etapas anteriores al gate pendiente, más `reporte` si es ese gate (el manifiesto y el entregable se escriben al evaluar el gate final).

- [ ] **Step 1: Test que falla — crear `tests/test_audit_infra.py`**

```python
"""Infraestructura del auditor: carga que nunca lanza, estado, N/A, fail-closed y render.

Spec 2026-10-04 §9.1-§9.2. Las corridas salen de la fixture ``corrida``
(``tests/conftest.py``).
"""

from __future__ import annotations

import pytest
from audit_fixtures import auditar, fila, pausar_en_screening_ft

import revisia.audit as audit_pkg
from revisia.audit import CHECKS, AuditCheck, AuditReport, CheckSpec, render_audit_md
from revisia.audit.artifacts import read_json, read_jsonl, read_text, read_yaml
from revisia.audit.render import _md_cell
from revisia.audit.state import derive_state
from revisia.config import STAGES
from revisia.schemas.artifacts import GateSummary, RunInfo

# ── Loaders: nunca lanzan ───────────────────────────────────────────────


def test_loaders_ausente_directorio_y_raiz_inesperada(tmp_path) -> None:
    (tmp_path / "carpeta.json").mkdir()
    (tmp_path / "lista.yml").write_text("- a\n- b\n", encoding="utf-8")
    (tmp_path / "texto.json").write_text('"hola"', encoding="utf-8")
    ausente = read_json(tmp_path, "no-existe.json")
    assert (ausente.present, ausente.ok, ausente.error) == (False, False, None)
    assert read_text(tmp_path, "carpeta.json").error == "no es un fichero"
    assert "la raíz es lista, no mapa" in read_yaml(tmp_path, "lista.yml").error
    assert "la raíz es str" in read_json(tmp_path, "texto.json").error


@pytest.mark.parametrize(
    "contenido",
    [b"{\n", "{}".encode("utf-16"), b"\x89PNG\r\n\x1a\n\x00\xff\xfe"],
    ids=["json-truncado", "utf16", "binario"],
)
def test_loaders_json_invalido_utf16_o_binario(tmp_path, contenido: bytes) -> None:
    (tmp_path / "x.json").write_bytes(contenido)
    loaded = read_json(tmp_path, "x.json")
    assert loaded.present and not loaded.ok and loaded.error


def test_read_jsonl_conserva_las_lineas_legibles_y_numera_las_corruptas(tmp_path) -> None:
    (tmp_path / "x.jsonl").write_text('{"a": 1}\n\nno-json\n{"b": 2}\n', encoding="utf-8")
    loaded = read_jsonl(tmp_path, "x.jsonl")
    assert loaded.value == [(1, {"a": 1}), (4, {"b": 2})]
    assert loaded.error.startswith("línea 3: JSON inválido")


def test_manifiesto_con_raiz_lista_no_revienta(corrida) -> None:
    (corrida / "manifest.yml").write_text("- slug: demo\n", encoding="utf-8")
    report = auditar(corrida)
    assert fila(report, "manifest").status == "FAIL"
    assert len(report.checks) == len(CHECKS)


@pytest.mark.parametrize(
    "contenido",
    ["slug: demo\n".encode("utf-16"), b"\x00\x01\xff\xfe binario"],
    ids=["utf16", "binario"],
)
def test_manifiesto_utf16_o_binario_no_revienta(corrida, contenido: bytes) -> None:
    (corrida / "manifest.yml").write_bytes(contenido)
    report = auditar(corrida)
    assert fila(report, "manifest").status == "FAIL"
    assert fila(report, "provenance").status == "N/A"


# ── Fail-closed e invariante N/A ⇒ FAIL ────────────────────────────────


def test_check_que_revienta_es_fail_y_el_resto_sigue(corrida, monkeypatch) -> None:
    def _roto(_ctx):
        raise KeyError("campo-que-no-existe")

    roto = tuple(
        CheckSpec(s.check_id, s.item_ref, s.stage, _roto) if s.check_id == "gold" else s
        for s in CHECKS
    )
    monkeypatch.setattr(audit_pkg, "CHECKS", roto)
    report = auditar(corrida)
    gold = fila(report, "gold")
    assert gold.status == "FAIL"
    assert "error interno del auditor (KeyError)" in gold.detail
    assert "no se considera verificada" in gold.detail
    assert len(report.checks) == len(CHECKS)
    assert fila(report, "final_gate").status == "PASS"


def test_invariante_na_sin_fail_se_convierte_en_fail() -> None:
    checks = [
        AuditCheck("a", "x", "PASS", "ok"),
        AuditCheck("b", "x", "N/A", "no aplica: algo"),
    ]
    resultado = audit_pkg._enforce_invariant(checks)
    assert [c.status for c in resultado] == ["PASS", "FAIL"]
    assert "N/A sin ningún FAIL" in resultado[1].detail
    con_fail = [*checks, AuditCheck("c", "x", "FAIL", "roto")]
    assert audit_pkg._enforce_invariant(con_fail) == con_fail


# ── Estado de la corrida ────────────────────────────────────────────────


def _gate(stage: str, action: str = "approve", actor: str = "human:ana") -> GateSummary:
    return GateSummary(
        stage=stage, action=action, actor=actor, autonomy="A1", timestamp_utc="2026-10-04T12:00Z"
    )


def _gates(*stages: str, **acciones: str) -> dict[str, GateSummary]:
    return {s: _gate(s, acciones.get(s, "approve")) for s in stages}


def test_derive_state_completada_y_desconocida() -> None:
    completa = _gates("screening_ta", "screening_ft", "extraccion", "rob", "reporte")
    estado = derive_state(run_info=None, gates=completa, requests=set(), ledger_ok=True)
    assert (estado.status, estado.reached) == ("completed", frozenset(STAGES))
    desconocido = derive_state(run_info=None, gates={}, requests=set(), ledger_ok=False)
    assert (desconocido.status, desconocido.reached) == ("unknown", frozenset(STAGES))
    assert "se exige todo" in desconocido.describe()


def test_derive_state_pausa_en_screening_ft() -> None:
    estado = derive_state(
        run_info=None,
        gates=_gates("screening_ta"),
        requests={"screening_ta", "screening_ft"},
        ledger_ok=True,
    )
    assert (estado.status, estado.pending_stage) == ("paused", "screening_ft")
    assert estado.reached == frozenset({"protocolo", "busqueda", "dedup", "screening_ta"})
    assert estado.na_detail() == (
        "no aplica: corrida en pausa en `screening_ft`; se verificará al reanudar."
    )


def test_derive_state_sin_solicitud_es_interrumpida_y_rechazo_gana() -> None:
    interrumpida = derive_state(
        run_info=None, gates=_gates("screening_ta"), requests={"screening_ta"}, ledger_ok=True
    )
    assert (interrumpida.status, interrumpida.pending_stage) == ("interrupted", "screening_ft")
    rechazada = derive_state(
        run_info=None,
        gates=_gates("screening_ta", "screening_ft", screening_ft="reject"),
        requests={"screening_ta", "screening_ft"},
        ledger_ok=True,
    )
    assert (rechazada.status, rechazada.pending_stage) == ("rejected", "screening_ft")
    assert "screening_ft" not in rechazada.reached


def test_derive_state_pausa_o_rechazo_en_reporte_audita_el_reporte() -> None:
    previas = _gates("screening_ta", "screening_ft", "extraccion", "rob")
    estado = derive_state(
        run_info=None, gates=previas, requests={"reporte", *previas}, ledger_ok=True
    )
    assert (estado.status, estado.pending_stage) == ("paused", "reporte")
    assert estado.reached == frozenset(STAGES)


def test_derive_state_run_json_interrumpida() -> None:
    info = RunInfo(
        slug="demo",
        timestamp="20261004-120000",
        started_utc="2026-10-04T12:00:00+00:00",
        engine_version="0.8.0",
        python_version="3.13.0",
        max_results=50,
        mailto_set=False,
        status="interrupted",
        stage="extraccion",
    )
    estado = derive_state(
        run_info=info, gates=_gates("screening_ta"), requests=set(), ledger_ok=False
    )
    assert (estado.status, estado.pending_stage) == ("interrupted", "extraccion")


def test_pausa_en_screening_ft_deja_na_las_etapas_posteriores(corrida) -> None:
    pausar_en_screening_ft(corrida)
    report = auditar(corrida)
    assert report.state is not None
    assert (report.state.status, report.state.pending_stage) == ("paused", "screening_ft")
    for check_id in ("exclusions", "deliverable", "grounding", "manifest", "provenance"):
        assert fila(report, check_id).status == "N/A", check_id
        assert "en pausa en `screening_ft`" in fila(report, check_id).detail
    assert fila(report, "gold").status != "N/A"  # T/A sí se alcanzó
    assert fila(report, "final_gate").status == "FAIL"
    assert not report.publishable


# ── Render ─────────────────────────────────────────────────────────────


def test_md_cell_escapa_barras_y_saltos() -> None:
    assert _md_cell("a|b\nc\r\nd") == "a\\|b<br>c<br>d"


def test_render_escapa_sin_cambiar_el_numero_de_filas(tmp_path) -> None:
    checks = [
        AuditCheck("schemas", "PRISMA 27", "FAIL", "x.json: loc|a: msg\nsegunda línea"),
        AuditCheck("gold", "trAIce M9/R2", "N/A", "no aplica"),
    ]
    markdown = render_audit_md(AuditReport(run_dir=tmp_path, checks=checks))
    filas = [line for line in markdown.splitlines() if line.startswith("| ") and "---" not in line]
    assert len(filas) == 1 + len(checks)  # cabecera + una por check
    assert all(line.count(" | ") == 3 for line in filas)
    assert "loc\\|a: msg<br>segunda línea" in markdown
    assert "➖ N/A" in markdown
    assert "N/A=1" in markdown


def test_render_incluye_el_estado(corrida) -> None:
    markdown = render_audit_md(auditar(corrida))
    assert "Estado deducido: completada" in markdown


def test_cli_audit_muestra_na(corrida, capsys) -> None:
    from revisia.cli import main

    pausar_en_screening_ft(corrida)
    assert main(["audit", str(corrida)]) == 1
    out = capsys.readouterr().out
    assert "➖ N/A  exclusions" in out
    assert "Traceback" not in out
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_infra.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'CHECKS' from 'revisia.audit'`.

- [ ] **Step 3: Modelo del informe**

Sustituir el contenido completo de `revisia/audit/model.py` por:

```python
"""Modelo del informe de auditoría (``AuditCheck``, ``AuditReport``, ``Status``)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from revisia.audit.state import RunState

# ``N/A`` = la etapa del check no se alcanzó (corrida en pausa, interrumpida o
# rechazada) o su raíz ya dio FAIL en otra fila. Invariante del auditor: si hay
# algún N/A, hay al menos un FAIL (spec 2026-10-04 §9.2).
Status = Literal["PASS", "WARN", "FAIL", "N/A"]

STATUS_ICON: dict[str, str] = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌", "N/A": "➖"}

# Lo que devuelve cada check: estado y evidencia. El registro (``CheckSpec``)
# pone el id y el ítem de reporte.
Verdict = tuple[Status, str]


@dataclass(frozen=True)
class AuditCheck:
    """Resultado de una verificación puntual de la auditoría."""

    check_id: str
    item_ref: str  # ítem PRISMA / trAIce que respalda la verificación
    status: Status
    detail: str


@dataclass(frozen=True)
class AuditReport:
    """Informe completo de auditoría de una corrida.

    ``checks`` tiene siempre una fila por check registrado, en el mismo orden:
    la forma del informe es estable y comparable entre corridas. ``state`` es
    el estado que el auditor dedujo de la corrida (``None`` solo en informes
    construidos a mano).
    """

    run_dir: Path
    checks: list[AuditCheck]
    state: RunState | None = None

    @property
    def n_fail(self) -> int:
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def n_na(self) -> int:
        return sum(1 for c in self.checks if c.status == "N/A")

    @property
    def publishable(self) -> bool:
        return self.n_fail == 0
```

- [ ] **Step 4: Estado de la corrida — crear `revisia/audit/state.py`**

````python
"""Estado de una corrida deducido de sus artefactos (spec 2026-10-04 §9.2).

El auditor no audita igual una corrida terminada que una en pausa: en una
pausa, lo que está después del gate pendiente todavía no existe y exigirlo
daría FAIL falsos. ``derive_state`` deduce el estado de ``run.json`` (si
existe), del ledger validado y de qué gates tienen ``review_request.yml``.
Las filas de checks cuya etapa no se alcanzó salen ``N/A``; como una pausa
siempre deja ``final_gate`` en FAIL, un ``N/A`` no puede ocultar nada en una
corrida publicable.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
from typing import Literal

from revisia.config import STAGES
from revisia.schemas.artifacts import GATED_STAGES, GateSummary, RunInfo

RunStateStatus = Literal["completed", "paused", "rejected", "interrupted", "unknown"]

# Acciones con las que un gate deja pasar la corrida a la etapa siguiente.
_PASSED = frozenset({"approve", "auto-proceed"})

_DESCRIPCION = {
    "paused": "en pausa en",
    "rejected": "rechazada en",
    "interrupted": "interrumpida en",
}


@dataclass(frozen=True)
class RunState:
    """Estado deducido de una corrida.

    Attributes:
        status: ``completed`` | ``paused`` | ``rejected`` | ``interrupted`` |
            ``unknown`` (ledger ilegible o vacío y sin ``run.json``: se exige
            todo).
        reached: etapas de ``config.STAGES`` cuyos artefactos deben existir.
        pending_stage: gate en el que está detenida la corrida (``None`` si
            terminó o si el estado es desconocido).
    """

    status: RunStateStatus
    reached: frozenset[str]
    pending_stage: str | None = None

    def describe(self) -> str:
        """Descripción legible: ``completada``, ``en pausa en `screening_ft```…"""
        if self.status == "completed":
            return "completada"
        if self.status == "unknown":
            return "desconocido (ledger ilegible o vacío y sin run.json): se exige todo"
        return f"{_DESCRIPCION[self.status]} `{self.pending_stage}`"

    def na_detail(self) -> str:
        """Detalle de una fila ``N/A`` por etapa no alcanzada."""
        return f"no aplica: corrida {self.describe()}; se verificará al reanudar."


def _reached_until(pending: str) -> frozenset[str]:
    """Etapas anteriores al gate pendiente (más ``reporte`` si es ese gate).

    El manifiesto y el entregable se escriben al evaluar el gate final, con
    cualquier resultado (spec §4.2): una corrida en pausa o rechazada en
    ``reporte`` se audita entera.
    """
    idx = STAGES.index(pending)
    reached = set(STAGES[:idx])
    if pending == "reporte":
        reached.add("reporte")
    return frozenset(reached)


def derive_state(
    *,
    run_info: RunInfo | None,
    gates: Mapping[str, GateSummary],
    requests: Set[str],
    ledger_ok: bool,
) -> RunState:
    """Deduce el estado de la corrida.

    Args:
        run_info: ``run.json`` validado, o ``None`` (corrida anterior a la Ola
            1 o fichero ausente).
        gates: decisión efectiva por etapa (``summarize_gates`` del ledger).
        requests: gates con ``<gate>/review_request.yml`` en disco.
        ledger_ok: el ledger existe, se lee entero y tiene entradas.

    Reglas (en este orden): ``unknown`` si el ledger no sirve y no hay
    ``run.json``; ``rejected`` si la decisión efectiva de algún gate es
    ``reject``; ``completed`` si ``reporte`` pasó (``approve`` o
    ``auto-proceed``: quién decidió lo juzga ``final_gate``);
    ``interrupted`` si ``run.json`` lo dice; si no, el primer gate sin
    decisión: ``paused`` con solicitud, ``interrupted`` sin ella.
    """
    everything = frozenset(STAGES)
    if not ledger_ok and run_info is None:
        return RunState("unknown", everything)

    for gate in GATED_STAGES:
        summary = gates.get(gate)
        if summary is not None and summary.action == "reject":
            return RunState("rejected", _reached_until(gate), gate)

    reporte = gates.get("reporte")
    if reporte is not None and reporte.action in _PASSED:
        return RunState("completed", everything)

    pending = next((g for g in GATED_STAGES if g not in gates), None)
    if run_info is not None and run_info.status == "interrupted":
        stage = run_info.stage if run_info.stage in STAGES else pending
        if stage is None:
            return RunState("unknown", everything)
        return RunState("interrupted", _reached_until(stage), stage)
    if pending is None:
        return RunState("unknown", everything)
    if pending in requests:
        return RunState("paused", _reached_until(pending), pending)
    return RunState("interrupted", _reached_until(pending), pending)
````

- [ ] **Step 5: Carga robusta — crear `revisia/audit/artifacts.py`**

```python
"""Carga robusta de los artefactos de una corrida (spec 2026-10-04 §9.1).

Los loaders **nunca lanzan**: devuelven un :class:`Loaded` con el valor o con
el error (``OSError``, ``UnicodeDecodeError``, JSON/YAML inválido, raíz de tipo
inesperado, ``ValidationError``, ``RecursionError``). Antes de la Ola 1 un
``manifest.yml`` con raíz de lista reventaba el auditor con ``AttributeError``
y una línea corrupta del ledger se descartaba en silencio (auditoría
2026-09-03, A11/C3): un auditor que revienta o que ignora lo ilegible no
verifica nada.

``AuditContext`` reúne lo que los checks comparten (manifiesto, ledger,
decisiones efectivas, estado, protocolo) y lo calcula una sola vez.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Generic, TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError

from revisia.audit.state import RunState, derive_state
from revisia.config import STAGES, ReviewProtocol
from revisia.exclusions import ExclusionBreakdown
from revisia.exports import PrismaCounts
from revisia.extraction_agreement import ExtractionAgreement
from revisia.meta_analysis import MetaAnalysisResult
from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import HumanDecision
from revisia.provenance.ledger import DecisionEntry, summarize_gates
from revisia.provenance.runmeta import RunMeta
from revisia.schemas.artifacts import GATED_STAGES, GateSummary, RunInfo
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision
from revisia.schemas.verification import VerificationReport

# `TypeVar` + `Generic` y no la sintaxis `class Loaded[T]` de 3.12: la suite
# también corre en 3.11 (spec 2026-10-04 §11; M24 es de la Ola 2).
T = TypeVar("T")

# El loader en C es órdenes de magnitud más rápido con manifiestos de miles de
# `llm_calls`; PyYAML sin libyaml no lo trae.
_YAML_LOADER: type = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


@dataclass(frozen=True)
class Loaded(Generic[T]):  # noqa: UP046 (compatibilidad con 3.11)
    """Resultado de cargar un artefacto: nunca una excepción.

    Attributes:
        path: ruta relativa al directorio de la corrida, con ``/``.
        present: el fichero existe.
        value: el contenido cargado (``None`` si falta o no se pudo cargar;
            en un ``.jsonl`` con líneas corruptas, las líneas legibles).
        error: por qué no se pudo cargar o validar (``None`` si se pudo).
    """

    path: str
    present: bool
    value: T | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.present and self.error is None


class SearchFailure(BaseModel):
    """Una entrada de ``01_search/failures.json``."""

    db: str
    error: str


def _type_names(root: type | tuple[type, ...]) -> str:
    kinds = root if isinstance(root, tuple) else (root,)
    names = {dict: "mapa", list: "lista"}
    return " o ".join(names.get(k, k.__name__) for k in kinds)


def _root_name(value: object) -> str:
    return {dict: "mapa", list: "lista"}.get(type(value), type(value).__name__)


def format_validation(exc: ValidationError, *, limit: int = 3) -> str:
    """``loc: msg; loc: msg (+k más)`` a partir de una ``ValidationError``."""
    errors = exc.errors()
    parts = [
        f"{'.'.join(str(p) for p in err['loc']) or '(raíz)'}: {err['msg']}"
        for err in errors[:limit]
    ]
    if len(errors) > limit:
        parts.append(f"+{len(errors) - limit} más")
    return "; ".join(parts)


def read_text(run_dir: Path, rel: str) -> Loaded[str]:
    """Lee un fichero de texto UTF-8."""
    path = run_dir / rel
    if not path.exists():
        return Loaded(rel, False)
    if not path.is_file():
        return Loaded(rel, True, error="no es un fichero")
    try:
        return Loaded(rel, True, path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return Loaded(rel, True, error="no es texto UTF-8 (¿UTF-16 o binario?)")
    except OSError as exc:
        return Loaded(rel, True, error=f"no se pudo leer ({type(exc).__name__})")


def read_json(
    run_dir: Path, rel: str, *, root: type | tuple[type, ...] = (dict, list)
) -> Loaded[Any]:
    """Lee un JSON y comprueba el tipo de su raíz."""
    text = read_text(run_dir, rel)
    if not text.ok:
        return Loaded(rel, text.present, error=text.error)
    try:
        value = json.loads(text.value)
    except (ValueError, RecursionError) as exc:
        return Loaded(rel, True, error=f"JSON inválido ({exc})")
    if not isinstance(value, root):
        return Loaded(rel, True, error=f"la raíz es {_root_name(value)}, no {_type_names(root)}")
    return Loaded(rel, True, value)


def read_yaml(run_dir: Path, rel: str, *, root: type | tuple[type, ...] = dict) -> Loaded[Any]:
    """Lee un YAML (``CSafeLoader`` si está disponible) y comprueba su raíz."""
    text = read_text(run_dir, rel)
    if not text.ok:
        return Loaded(rel, text.present, error=text.error)
    try:
        value = yaml.load(text.value, Loader=_YAML_LOADER)
    except (yaml.YAMLError, ValueError, RecursionError) as exc:
        return Loaded(rel, True, error=f"YAML inválido ({type(exc).__name__})")
    if not isinstance(value, root):
        return Loaded(rel, True, error=f"la raíz es {_root_name(value)}, no {_type_names(root)}")
    return Loaded(rel, True, value)


def read_jsonl(run_dir: Path, rel: str) -> Loaded[list[tuple[int, Any]]]:
    """Lee un ``.jsonl``: ``value`` = ``[(número de línea, objeto)]`` legibles.

    Una línea que no es JSON no se descarta en silencio: queda en ``error``,
    una por línea de texto y con su número de línea (las líneas en blanco se
    ignoran). Antes de la Ola 1 el auditor las saltaba (auditoría 2026-09-03).
    """
    text = read_text(run_dir, rel)
    if not text.ok:
        return Loaded(rel, text.present, error=text.error)
    lines: list[tuple[int, Any]] = []
    errors: list[str] = []
    for number, line in enumerate(text.value.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            lines.append((number, json.loads(line)))
        except (ValueError, RecursionError) as exc:
            errors.append(f"línea {number}: JSON inválido ({exc})")
    return Loaded(rel, True, lines, "\n".join(errors) or None)


def validate(loaded: Loaded[Any], adapter: TypeAdapter[T]) -> Loaded[T]:  # noqa: UP047
    """Valida un artefacto cargado contra su modelo (sin lanzar)."""
    if not loaded.ok:
        return Loaded(loaded.path, loaded.present, error=loaded.error)
    try:
        return Loaded(loaded.path, True, adapter.validate_python(loaded.value))
    except ValidationError as exc:
        return Loaded(loaded.path, True, error=format_validation(exc))
    except RecursionError:
        return Loaded(loaded.path, True, error="estructura demasiado anidada")


# Artefactos JSON de la corrida y el modelo contra el que se validan.
ARTIFACT_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "01_search/failures.json": TypeAdapter(list[SearchFailure]),
    "03_screening/decisions.json": TypeAdapter(list[ScreeningDecision]),
    "03_screening/metrics.json": TypeAdapter(ScreeningMetrics),
    "03_screening/exclusions.json": TypeAdapter(ExclusionBreakdown),
    "04_fulltext/decisions.json": TypeAdapter(list[ScreeningDecision]),
    "05_extraction/extractions.json": TypeAdapter(dict[str, ExtractionRecord]),
    "05_extraction/agreement.json": TypeAdapter(ExtractionAgreement),
    "06_synthesis/verification.json": TypeAdapter(VerificationReport),
    "07_rob/assessments.json": TypeAdapter(dict[str, RoBAssessment]),
    "08_meta/meta_analysis.json": TypeAdapter(MetaAnalysisResult),
}

# Secciones de ``manifest.yml`` con modelo (las copias de los artefactos y los
# bloques que escribe el motor).
MANIFEST_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "protocol": TypeAdapter(ReviewProtocol),
    "counts": TypeAdapter(PrismaCounts),
    "llm_calls": TypeAdapter(list[RunMeta]),
    "models_used": TypeAdapter(list[str]),
    "deterministic_token_level": TypeAdapter(bool),
    "screening_metrics": TypeAdapter(ScreeningMetrics),
    "verification": TypeAdapter(VerificationReport),
    "exclusions": TypeAdapter(ExclusionBreakdown),
    "extraction_agreement": TypeAdapter(ExtractionAgreement),
    "meta_analysis": TypeAdapter(MetaAnalysisResult),
    "risk_of_bias": TypeAdapter(dict[str, RoBAssessment]),
}

_DECISION_ADAPTER: TypeAdapter[HumanDecision] = TypeAdapter(HumanDecision)
_RUN_INFO_ADAPTER: TypeAdapter[RunInfo] = TypeAdapter(RunInfo)


class RunArtifacts:
    """Artefactos de una corrida, cargados bajo demanda y una sola vez."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self._cache: dict[tuple[str, str], Loaded[Any]] = {}

    def _memo(self, kind: str, rel: str, load: Any) -> Loaded[Any]:
        key = (kind, rel)
        if key not in self._cache:
            self._cache[key] = load()
        return self._cache[key]

    def exists(self, rel: str) -> bool:
        return (self.run_dir / rel).exists()

    def text(self, rel: str) -> Loaded[str]:
        return self._memo("text", rel, lambda: read_text(self.run_dir, rel))

    def json(self, rel: str) -> Loaded[Any]:
        return self._memo("json", rel, lambda: read_json(self.run_dir, rel))

    def yaml(self, rel: str) -> Loaded[Any]:
        return self._memo("yaml", rel, lambda: read_yaml(self.run_dir, rel))

    def jsonl(self, rel: str) -> Loaded[list[tuple[int, Any]]]:
        return self._memo("jsonl", rel, lambda: read_jsonl(self.run_dir, rel))

    def artifact(self, rel: str) -> Loaded[Any]:
        """Artefacto JSON de :data:`ARTIFACT_ADAPTERS`, validado contra su modelo."""
        return self._memo("model", rel, lambda: validate(self.json(rel), ARTIFACT_ADAPTERS[rel]))

    def decision(self, gate: str) -> Loaded[HumanDecision]:
        """``<gate>/decision.yml`` validado como ``HumanDecision``."""
        rel = f"{gate}/decision.yml"
        return self._memo("decision", rel, lambda: validate(self.yaml(rel), _DECISION_ADAPTER))

    def run_info(self) -> Loaded[RunInfo]:
        """``run.json`` validado (ausente en corridas anteriores a la Ola 1)."""
        return self._memo(
            "run_info", "run.json", lambda: validate(self.json("run.json"), _RUN_INFO_ADAPTER)
        )


def load_run(run_dir: str | Path) -> RunArtifacts:
    """Prepara la carga de los artefactos de ``run_dir`` (nada se lee todavía)."""
    return RunArtifacts(Path(run_dir))


@dataclass(frozen=True)
class LedgerView:
    """El ledger validado línea a línea.

    Attributes:
        present: ``decisions_ledger.jsonl`` existe.
        entries: ``(número de línea, entrada)`` de las líneas válidas.
        errors: una por línea que no es JSON o no valida ``DecisionEntry``.
        read_error: el fichero no se pudo leer entero.
    """

    present: bool
    entries: tuple[tuple[int, DecisionEntry], ...]
    errors: tuple[str, ...]
    read_error: str | None

    @property
    def usable(self) -> bool:
        """Se lee entero, sin líneas corruptas y con al menos una entrada."""
        return self.present and not self.read_error and not self.errors and bool(self.entries)

    @property
    def decisions(self) -> list[DecisionEntry]:
        return [entry for _, entry in self.entries]


_DECISION_ENTRY = TypeAdapter(DecisionEntry)


class AuditContext:
    """Lo que comparten los checks de una corrida, calculado una vez."""

    def __init__(self, artifacts: RunArtifacts) -> None:
        self.art = artifacts
        self.run_dir = artifacts.run_dir
        self._sections: dict[str, Loaded[Any]] = {}

    @cached_property
    def manifest(self) -> Loaded[Any]:
        return self.art.yaml("manifest.yml")

    @cached_property
    def manifest_dict(self) -> dict[str, Any] | None:
        """El manifiesto si se pudo leer y su raíz es un mapa."""
        return self.manifest.value if self.manifest.ok else None

    def manifest_section(self, key: str) -> Loaded[Any]:
        """Sección ``key`` de :data:`MANIFEST_ADAPTERS`, validada.

        ``present`` es ``False`` si el manifiesto no se pudo leer o no tiene esa
        clave.
        """
        if key not in self._sections:
            rel = f"manifest.yml#{key}"
            manifest = self.manifest_dict or {}
            if key not in manifest:
                self._sections[key] = Loaded(rel, False)
            else:
                raw = Loaded(rel, True, manifest[key])
                self._sections[key] = validate(raw, MANIFEST_ADAPTERS[key])
        return self._sections[key]

    @cached_property
    def llm_calls(self) -> list[dict[str, Any]]:
        """Las llamadas del manifiesto que son mapas (las demás las marca ``schemas``)."""
        calls = (self.manifest_dict or {}).get("llm_calls")
        return [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []

    @cached_property
    def ledger(self) -> LedgerView:
        raw = self.art.jsonl("decisions_ledger.jsonl")
        if not raw.present or raw.value is None:
            return LedgerView(raw.present, (), (), raw.error)
        entries: list[tuple[int, DecisionEntry]] = []
        errors = (raw.error or "").splitlines()
        for number, obj in raw.value:
            try:
                entries.append((number, _DECISION_ENTRY.validate_python(obj)))
            except ValidationError as exc:
                errors.append(f"línea {number}: {format_validation(exc, limit=2)}")
        return LedgerView(True, tuple(entries), tuple(errors), None)

    @cached_property
    def gates(self) -> dict[str, GateSummary]:
        """Decisión efectiva por etapa (el reductor único del ledger, D12)."""
        return summarize_gates(self.ledger.decisions)

    @cached_property
    def requests(self) -> frozenset[str]:
        """Gates con ``review_request.yml`` en disco."""
        return frozenset(
            g for g in GATED_STAGES if (self.run_dir / g / "review_request.yml").is_file()
        )

    @cached_property
    def run_info(self) -> RunInfo | None:
        loaded = self.art.run_info()
        return loaded.value if loaded.ok else None

    @cached_property
    def state(self) -> RunState:
        """Estado deducido; ante un error interno, ``unknown`` (se exige todo)."""
        try:
            return derive_state(
                run_info=self.run_info,
                gates=self.gates,
                requests=self.requests,
                ledger_ok=self.ledger.usable,
            )
        except Exception:  # fail-closed: un error propio nunca relaja la auditoría
            return RunState("unknown", frozenset(STAGES))

    @cached_property
    def protocol(self) -> ReviewProtocol | None:
        """El protocolo tal como lo registró el manifiesto (``None`` si no valida)."""
        loaded = self.manifest_section("protocol")
        return loaded.value if loaded.ok else None
```

- [ ] **Step 6: Los checks de hoy, portados a sus módulos**

Crear `revisia/audit/checks_provenance.py`:

```python
"""Checks de procedencia: ``manifest``, ``provenance``, ``prompts``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.orchestration.run_context import PROVENANCE_PIPELINE

_NA_MANIFIESTO = "no aplica: el manifiesto no se pudo leer (ver `manifest`)."


def check_manifest(ctx: AuditContext) -> Verdict:
    """trAIce M2: manifiesto con las llamadas IA y los modelos usados."""
    if ctx.manifest_dict is None:
        return "FAIL", "manifest.yml ausente o ilegible: la corrida no es reproducible."
    models = ctx.manifest_dict.get("models_used") or []
    calls = ctx.llm_calls
    if models and calls:
        return "PASS", (
            f"manifest.yml con {len(calls)} llamada(s) IA y modelos: {', '.join(map(str, models))}."
        )
    if calls or models:
        return "WARN", "manifest.yml presente pero con procedencia IA incompleta."
    return "WARN", "manifest.yml sin llamadas IA registradas (¿corrida determinista/fake?)."


def check_provenance(ctx: AuditContext) -> Verdict:
    """Procedencia: la corrida la produjo el pipeline (auditoría 2026-09-03, C3)."""
    if ctx.manifest_dict is None:
        return "N/A", _NA_MANIFIESTO
    provenance = ctx.manifest_dict.get("provenance")
    if provenance == PROVENANCE_PIPELINE:
        return "PASS", (
            "El manifiesto declara `provenance: pipeline` (marca escrita por el motor; "
            "no es una firma)."
        )
    found = "ausente" if provenance is None else repr(provenance)
    return "FAIL", (
        f"Procedencia {found}: el manifiesto no declara `provenance: pipeline`. "
        "Una corrida reconstruida, o generada antes de que el motor registrara "
        "su procedencia, no es evidencia publicable: regenérala con `revisia run`."
    )


def check_prompts(ctx: AuditContext) -> Verdict:
    """trAIce M6: cada llamada con su prompt hash-eado."""
    if ctx.manifest_dict is None:
        return "N/A", _NA_MANIFIESTO
    calls = ctx.llm_calls
    hashed = [c for c in calls if c.get("prompt_sha256")]
    if calls and len(hashed) == len(calls):
        return "PASS", f"{len(hashed)}/{len(calls)} llamadas con prompt hash-eado (RunMeta)."
    if calls:
        return "WARN", f"Solo {len(hashed)}/{len(calls)} llamadas llevan prompt_hash."
    return "WARN", "Sin llamadas IA que auditar."
```

Crear `revisia/audit/checks_hitl.py`:

```python
"""Checks del ledger y de la supervisión humana: ``ledger``, ``hitl``, ``final_gate``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.config import JUDGMENT_STAGES

_NA_LEDGER = "no aplica: sin ledger legible (ver `ledger`)."


def check_ledger(ctx: AuditContext) -> Verdict:
    """trAIce M8: el ledger de decisiones existe y tiene entradas."""
    if not ctx.ledger.entries:
        return "FAIL", "decisions_ledger.jsonl ausente o vacío: sin trazabilidad de decisiones."
    return "PASS", f"{len(ctx.ledger.entries)} decisiones en el ledger."


def check_hitl(ctx: AuditContext) -> Verdict:
    """trAIce M8: decisiones humanas en las etapas de juicio."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    ledger = ctx.ledger.decisions
    human = [e for e in ledger if e.actor.startswith("human")]
    judgment = [e for e in ledger if e.stage in JUDGMENT_STAGES]
    judgment_human = [e for e in judgment if e.actor.startswith("human")]
    if judgment and not judgment_human:
        return "WARN", (
            f"{len(ledger)} decisiones registradas, pero NINGUNA humana en etapas de "
            "juicio (¿--auto-approve?). Apta para demo; NO publicable sin revisión humana."
        )
    return "PASS", f"{len(ledger)} decisiones en el ledger; {len(human)} humana(s)."


def check_final_gate(ctx: AuditContext) -> Verdict:
    """Gate de honestidad: decisión humana sobre el reporte final."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    reporte = [e for e in ctx.ledger.decisions if e.stage == "reporte"]
    if not reporte:
        return "FAIL", "Sin decisión sobre el reporte final: la corrida está pausada o incompleta."
    last = reporte[-1]
    if last.action == "approve" and last.actor.startswith("human"):
        return "PASS", f"Reporte final aprobado por humano ({last.actor})."
    if last.action in ("approve", "auto-proceed"):
        return "WARN", f"El reporte final no lo aprobó un humano: {last.actor}/{last.action}."
    if last.action == "reject":
        return "FAIL", f"El reporte final fue rechazado por {last.actor}."
    return "FAIL", f"Acción desconocida {last.action} en la decisión final."
```

Crear `revisia/audit/checks_flow.py`:

```python
"""Checks del flujo PRISMA: ``exclusions``, ``deliverable``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict

DELIVERABLE_FILES: tuple[str, ...] = (
    "documento.md",
    "prisma_flow.md",
    "metodologia.md",
    "tabla_extraccion.md",
    "risk_of_bias.md",
    "referencias.bib",
    "checklist_2020.md",
    "checklist_traice.md",
)


def check_exclusions(ctx: AuditContext) -> Verdict:
    """trAIce R1: exclusiones humano/IA separadas."""
    if ctx.art.exists("03_screening/exclusions.json"):
        return "PASS", "Desglose de exclusiones humano/IA presente (03_screening/exclusions.json)."
    return "WARN", "Sin desglose de exclusiones humano vs IA."


def check_deliverable(ctx: AuditContext) -> Verdict:
    """PRISMA 16/17/18/27: entregable completo."""
    missing = [name for name in DELIVERABLE_FILES if not ctx.art.exists(f"deliverable/{name}")]
    if not missing:
        return "PASS", f"Entregable completo ({len(DELIVERABLE_FILES)} artefactos)."
    return "FAIL", "Faltan artefactos del entregable: " + ", ".join(missing) + "."
```

Crear `revisia/audit/checks_quality.py`:

```python
"""Checks de calidad del cribado y de la síntesis: ``gold``, ``grounding``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict


def check_gold(ctx: AuditContext) -> Verdict:
    """trAIce M9/R2: métricas del cribado IA contra un gold humano."""
    loaded = ctx.art.json("03_screening/metrics.json")
    if not loaded.present:
        return "WARN", (
            "Sin gold standard: no hay recall/kappa del cribado IA vs humano. "
            "Crea gold.yml (revisia gold-template) antes de publicar."
        )
    if not loaded.ok or not isinstance(loaded.value, dict):
        return "WARN", "metrics.json ilegible."
    metrics = loaded.value
    recall = metrics.get("recall")
    kappa = metrics.get("cohen_kappa")
    # mcc solo cuenta como indefinido si la clave está presente y es null: un
    # metrics.json de formato antiguo (sin "mcc") no debe convertir un PASS
    # previo en WARN.
    mcc_indefinido = "mcc" in metrics and metrics.get("mcc") is None
    # La matriz cuenta como presente solo si sus cuatro celdas son enteras.
    matriz = {k: metrics.get(k) for k in ("tp", "fp", "fn", "tn")}
    tiene_matriz = all(k in metrics for k in matriz)
    legible = tiene_matriz and all(
        isinstance(v, int) and not isinstance(v, bool) for v in matriz.values()
    )
    una_sola_clase = legible and (
        matriz["tp"] + matriz["fn"] == 0 or matriz["tn"] + matriz["fp"] == 0
    )
    if tiene_matriz and not legible:
        return "WARN", (
            f"Métricas vs gold humano: recall={recall} · metrics.json con matriz de confusión "
            "ilegible (tp/fp/fn/tn con algún valor no numérico)."
        )
    if kappa is None or mcc_indefinido or una_sola_clase:
        return "WARN", (
            f"Métricas vs gold humano: recall={recall} · kappa/mcc no calculable: métricas "
            "indefinidas o no informativas (el gold o la IA asignaron una sola clase). Amplía "
            "el gold con registros relevantes e irrelevantes."
        )
    return "PASS", (
        f"Métricas vs gold humano: recall={recall} · kappa={kappa} (accuracy omitida a propósito)."
    )


def check_grounding(ctx: AuditContext) -> Verdict:
    """trAIce M8/M9: verificación anti-alucinación de la síntesis."""
    loaded = ctx.art.json("06_synthesis/verification.json")
    if not loaded.present:
        return "WARN", "Sin verification.json: la síntesis no pasó por el verificador."
    if not loaded.ok or not isinstance(loaded.value, dict):
        return "WARN", "verification.json ilegible."
    if loaded.value.get("hallucination_flagged"):
        return "WARN", (
            "El verificador marcó citas posiblemente no fundamentadas: revisar antes de usar."
        )
    return "PASS", "Grounding de citas verificado sin banderas."
```

Crear `revisia/audit/checks_search.py`:

```python
"""Checks de búsqueda y registro: ``search_window``, ``registration``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict

_NA_PROTOCOLO = "no aplica: sin protocolo legible en el manifiesto (ver `manifest`)."


def _protocol_section(ctx: AuditContext, key: str) -> dict | None:
    if ctx.manifest_dict is None:
        return None
    protocol = ctx.manifest_dict.get("protocol")
    if not isinstance(protocol, dict):
        return {}
    section = protocol.get(key)
    return section if isinstance(section, dict) else {}


def check_search_window(ctx: AuditContext) -> Verdict:
    """PRISMA-S: ventana temporal de la búsqueda."""
    window = _protocol_section(ctx, "search_window")
    if window is None:
        return "N/A", _NA_PROTOCOLO
    if window.get("executed"):
        return "PASS", f"Búsqueda ejecutada declarada: {window.get('executed')}."
    return "WARN", "search_window.executed vacío: declara cuándo se ejecutó la búsqueda."


def check_registration(ctx: AuditContext) -> Verdict:
    """PRISMA 24a: registro del protocolo."""
    registration = _protocol_section(ctx, "registration")
    if registration is None:
        return "N/A", _NA_PROTOCOLO
    declared = {k: v for k, v in registration.items() if v}
    if declared:
        return "PASS", (
            "Registro declarado: " + ", ".join(f"{k}={v}" for k, v in declared.items()) + "."
        )
    return "WARN", "Sin registro (PROSPERO/OSF): preregistra el protocolo antes de publicar."
```

- [ ] **Step 7: Registro, `_run_one` e invariante**

Sustituir el contenido completo de `revisia/audit/__init__.py` por:

```python
"""Auditoría post-corrida · transparencia metodológica verificable.

``run_audit`` inspecciona una carpeta ``runs/<slug>-<fecha>/`` y verifica, con
evidencia en disco, que la corrida puede defenderse ante los estándares de
reporte que el sistema promete:

- **PRISMA 2020** (selección documentada, flow diagram, registro, datos abiertos)
- **PRISMA-S** (ventana temporal de búsqueda declarada y ejecutada)
- **PRISMA-trAIce** (modelos y versiones, prompts hash-eados, supervisión
  humana, exclusiones IA/humano separadas, evaluación contra gold humano,
  procedencia de la corrida (pipeline vs reconstrucción), decisión humana
  sobre el reporte final)

Cada verificación produce ``PASS`` (evidencia presente y coherente), ``WARN``
(aceptable pero debe declararse/mejorarse antes de publicar), ``FAIL`` (la
corrida no es publicable tal cual) o ``N/A`` (la etapa no se alcanzó o la raíz
del check ya falló; nunca sin algún FAIL). El resultado se imprime y se
escribe en ``<run_dir>/audit.md``: el auditor es un agente determinista, lee
artefactos, no opina.

Estructura (spec 2026-10-04 §9.1): ``model`` (informe), ``artifacts`` (carga
que nunca lanza), ``state`` (estado de la corrida), ``checks_*`` (un módulo
por familia) y ``render`` (Markdown). Aquí vive el registro ordenado de checks
y ``_run_one``, que hace al auditor *fail-closed*: un check que revienta es un
FAIL, no un traceback ni un PASS.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from revisia.audit import (
    checks_flow,
    checks_hitl,
    checks_provenance,
    checks_quality,
    checks_search,
)
from revisia.audit.artifacts import AuditContext, load_run
from revisia.audit.model import AuditCheck, AuditReport, Verdict
from revisia.audit.render import render_audit_md

__all__ = ["AuditCheck", "AuditReport", "CheckSpec", "CHECKS", "render_audit_md", "run_audit"]


@dataclass(frozen=True)
class CheckSpec:
    """Un check registrado.

    Attributes:
        check_id: id estable de la fila del informe.
        item_ref: ítem PRISMA / trAIce que respalda la verificación.
        stage: etapa de ``config.STAGES`` a partir de la cual el check aplica;
            si la corrida no la alcanzó, la fila sale ``N/A``. ``None`` =
            siempre aplica (los checks "por etapa" miran el estado ellos mismos).
        fn: la verificación; devuelve ``(estado, evidencia)``.
    """

    check_id: str
    item_ref: str
    stage: str | None
    fn: Callable[[AuditContext], Verdict]


# Orden del informe (spec §9.3). Una fila por check, siempre.
CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec("manifest", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_manifest),
    CheckSpec("provenance", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_provenance),
    CheckSpec("prompts", "trAIce M6", "reporte", checks_provenance.check_prompts),
    CheckSpec("ledger", "trAIce M8 / PRISMA 8", None, checks_hitl.check_ledger),
    CheckSpec("hitl", "trAIce M8/R1 / PRISMA 8", None, checks_hitl.check_hitl),
    CheckSpec("final_gate", "trAIce M8", None, checks_hitl.check_final_gate),
    CheckSpec("exclusions", "trAIce R1", "screening_ft", checks_flow.check_exclusions),
    CheckSpec("deliverable", "PRISMA 16/16b/17/18/27", "reporte", checks_flow.check_deliverable),
    CheckSpec("gold", "trAIce M9/R2", "screening_ta", checks_quality.check_gold),
    CheckSpec("grounding", "trAIce M8/M9", "sintesis", checks_quality.check_grounding),
    CheckSpec("search_window", "PRISMA-S 9/13", "busqueda", checks_search.check_search_window),
    CheckSpec("registration", "PRISMA 24a", None, checks_search.check_registration),
)


def _run_one(spec: CheckSpec, ctx: AuditContext) -> AuditCheck:
    """Ejecuta un check: ``N/A`` si su etapa no se alcanzó; FAIL si revienta."""
    if spec.stage is not None and spec.stage not in ctx.state.reached:
        return AuditCheck(spec.check_id, spec.item_ref, "N/A", ctx.state.na_detail())
    try:
        status, detail = spec.fn(ctx)
    except Exception as exc:  # fail-closed: un check roto no verifica nada
        return AuditCheck(
            spec.check_id,
            spec.item_ref,
            "FAIL",
            f"error interno del auditor ({type(exc).__name__}): {exc} — la corrida no se "
            "considera verificada.",
        )
    return AuditCheck(spec.check_id, spec.item_ref, status, detail)


def _enforce_invariant(checks: list[AuditCheck]) -> list[AuditCheck]:
    """Invariante ``N/A ⇒ FAIL``: si un N/A apareciera sin ningún FAIL (un defecto
    del auditor), se convierte en FAIL; un N/A nunca puede dejar publicable una
    corrida que no se verificó entera (spec §9.2)."""
    if any(c.status == "FAIL" for c in checks) or all(c.status != "N/A" for c in checks):
        return checks
    result: list[AuditCheck] = []
    for check in checks:
        if check.status == "N/A":
            check = AuditCheck(
                check.check_id,
                check.item_ref,
                "FAIL",
                f"error interno del auditor: N/A sin ningún FAIL que lo justifique "
                f"({check.detail}) — la corrida no se considera verificada.",
            )
        result.append(check)
    return result


def run_audit(run_dir: str | Path) -> AuditReport:
    """Audita una corrida y devuelve el informe (una fila por check registrado)."""
    run = Path(run_dir)
    ctx = AuditContext(load_run(run))
    checks = _enforce_invariant([_run_one(spec, ctx) for spec in CHECKS])
    return AuditReport(run_dir=run, checks=checks, state=ctx.state)
```

- [ ] **Step 8: Render con `_md_cell`, estado y `N/A`**

Sustituir el contenido completo de `revisia/audit/render.py` por:

```python
"""Informe de auditoría en Markdown (``<run_dir>/audit.md``)."""

from __future__ import annotations

from revisia.audit.model import STATUS_ICON, AuditReport


def _md_cell(text: object) -> str:
    """Escapa una celda de tabla Markdown.

    Un ``|`` sin escapar o un salto de línea dentro del detalle (p. ej. un
    error de Pydantic o una ruta con ``|``) partirían la fila y cambiarían el
    número de columnas del informe (spec 2026-10-04 §9.1).
    """
    value = str(text).replace("|", "\\|")
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def render_audit_md(report: AuditReport) -> str:
    """Renderiza el informe de auditoría como Markdown."""
    verdict = (
        "**APTA para preparar publicación** (sin FAIL; resuelve los WARN y decláralos)."
        if report.publishable
        else "**NO publicable tal cual** (hay verificaciones FAIL)."
    )
    lines = [
        "# Auditoría de corrida · revisia",
        "",
        f"- Corrida: `{report.run_dir}`",
    ]
    if report.state is not None:
        lines.append(f"- Estado deducido: {report.state.describe()}")
    lines += [
        f"- Resultado: {verdict}",
        f"- Verificaciones: {len(report.checks)} · FAIL={report.n_fail} · WARN={report.n_warn}"
        f" · N/A={report.n_na}",
        "",
        "| Verificación | Ítem de reporte | Estado | Evidencia |",
        "|---|---|---|---|",
    ]
    for check in report.checks:
        icon = STATUS_ICON.get(check.status, "•")
        lines.append(
            f"| {_md_cell(check.check_id)} | {_md_cell(check.item_ref)} | "
            f"{icon} {check.status} | {_md_cell(check.detail)} |"
        )
    lines += [
        "",
        "> El auditor es determinista: verifica artefactos en disco contra PRISMA 2020, "
        "PRISMA-S y PRISMA-trAIce. Un PASS no sustituye el juicio del revisor humano. "
        "➖ N/A = la etapa no se alcanzó o su raíz ya falló en otra fila; nunca aparece "
        "sin algún FAIL.",
    ]
    return "\n".join(lines)
```

- [ ] **Step 9: CLI: icono de `N/A` y ancho de columna (spec §9.1; los códigos 0/1/2 no cambian)**

En `revisia/cli.py`, sustituir

```python
    """Audita una corrida terminada contra PRISMA 2020 / PRISMA-S / trAIce."""
    from revisia.audit import render_audit_md, run_audit

    run_dir = Path(args.run_dir)
```

por

```python
    """Audita una corrida terminada contra PRISMA 2020 / PRISMA-S / trAIce."""
    from revisia.audit import render_audit_md, run_audit
    from revisia.audit.model import STATUS_ICON

    run_dir = Path(args.run_dir)
```

En `revisia/cli.py`, sustituir

```python
    out.write_text(markdown, encoding="utf-8")
    for check in report.checks:
        icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(check.status, "•")
        print(f"{icon} {check.status:<4} {check.check_id:<13} [{check.item_ref}] {check.detail}")
    verdict = "APTA para preparar publicación" if report.publishable else "NO publicable tal cual"
    print(
```

por

```python
    out.write_text(markdown, encoding="utf-8")
    for check in report.checks:
        icon = STATUS_ICON.get(check.status, "•")
        print(f"{icon} {check.status:<4} {check.check_id:<17} [{check.item_ref}] {check.detail}")
    verdict = "APTA para preparar publicación" if report.publishable else "NO publicable tal cual"
    print(
```

- [ ] **Step 10: Tests existentes que pasan a `N/A` (spec §9.4)**

En `tests/test_audit.py`, sustituir

```python
    assert fila(auditar(corrida), "provenance").status == "PASS"


def test_audit_sin_manifiesto_no_duplica_fail_de_procedencia(corrida) -> None:
    (corrida / "manifest.yml").unlink()
    report = auditar(corrida)
    assert "provenance" not in {c.check_id for c in report.checks}


def _sin_reporte(entries: list[dict]) -> list[dict]:
```

por

```python
    assert fila(auditar(corrida), "provenance").status == "PASS"


def test_audit_sin_manifiesto_no_duplica_fail_de_procedencia(corrida) -> None:
    # Una fila por check, siempre: la de procedencia sale N/A (su raíz, el
    # manifiesto, ya dio FAIL) en vez de omitirse o duplicar el FAIL.
    (corrida / "manifest.yml").unlink()
    report = auditar(corrida)
    assert fila(report, "manifest").status == "FAIL"
    assert fila(report, "provenance").status == "N/A"


def _sin_reporte(entries: list[dict]) -> list[dict]:
```

En `tests/test_audit.py`, sustituir

```python
    (corrida / "decisions_ledger.jsonl").unlink()
    report = auditar(corrida)
    assert "final_gate" not in {c.check_id for c in report.checks}
    assert fila(report, "ledger").status == "FAIL"


def test_audit_ledger_vacio_no_duplica_fail_de_final_gate(corrida) -> None:
```

por

```python
    (corrida / "decisions_ledger.jsonl").unlink()
    report = auditar(corrida)
    assert fila(report, "final_gate").status == "N/A"
    assert fila(report, "ledger").status == "FAIL"


def test_audit_ledger_vacio_no_duplica_fail_de_final_gate(corrida) -> None:
```

En `tests/test_audit.py`, sustituir

```python
    (corrida / "decisions_ledger.jsonl").write_text("", encoding="utf-8")
    report = auditar(corrida)
    assert "final_gate" not in {c.check_id for c in report.checks}


def _escribir_metricas(run, metrics: dict) -> None:
```

por

```python
    (corrida / "decisions_ledger.jsonl").write_text("", encoding="utf-8")
    report = auditar(corrida)
    assert fila(report, "final_gate").status == "N/A"
    assert fila(report, "ledger").status == "FAIL"


def _escribir_metricas(run, metrics: dict) -> None:
```

- [ ] **Step 11: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_infra.py tests/test_audit.py tests/test_pipeline_fake.py -v`
Expected: PASS (20 nuevos; los 23 de `test_audit.py`; `test_pipeline_fake.py` intacto).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 394 recogidos.

- [ ] **Step 12: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 13: Commit**

```bash
git add revisia/audit revisia/cli.py tests/test_audit.py tests/test_audit_infra.py
git commit -m "feat(audit): carga que nunca lanza, estado de la corrida, N/A y fail-closed" -m "audit/artifacts.py: loaders que capturan OSError, UnicodeDecodeError, JSON/YAML inválido, raíz inesperada, ValidationError y RecursionError (Loaded[T]), AuditContext. audit/state.py: RunState y derive_state (pausa, rechazo, interrupción). Registro ordenado de CheckSpec con _run_one fail-closed (un check que revienta es FAIL) y una fila por check, con N/A si la etapa no se alcanzó o su raíz ya falló; invariante N/A ⇒ FAIL. Los checks de hoy se portan a audit/checks_*.py. render escapa | y saltos de línea; el CLI muestra ➖ N/A. Spec 2026-10-04 §9.1-§9.2." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `manifest`, `provenance`, `schemas`, `prompts` y `ledger` exigentes

**Files:**
- Modify: `revisia/audit/checks_provenance.py` (contenido completo), `revisia/audit/checks_hitl.py` (contenido completo: `check_ledger` nuevo), `revisia/audit/__init__.py` (registra `schemas`)
- Modify: `tests/test_audit.py` (`manifest` pasa a WARN por `fake`; los seis tests de `gold` escriben un `ScreeningMetrics` válido y los de matriz `null`/ausente afirman además `schemas == FAIL`, spec §9.4)
- Test: `tests/test_audit_procedencia.py` (nuevo)

**Interfaces:**
- Consumes: `ARTIFACT_ADAPTERS`, `MANIFEST_ADAPTERS`, `Loaded`, `AuditContext` (Tarea 4); `LEDGER_ACTIONS`, `GATE_DECISION_ACTIONS` (PR-0); `STAGES`, `JUDGMENT_STAGES`; `ReviewProtocol.autonomy_for`.
- Produces: `check_manifest`, `check_provenance`, `check_schemas`, `check_prompts` (`checks_provenance.py`); `effective_autonomy(ctx) -> dict[str, str] | None` y `check_ledger` (`checks_hitl.py`); fila `schemas` (`PRISMA 27 / trAIce M5`, siempre aplica) tras `provenance`.

Reglas (spec §9.3, filas 1, 2, 3, 5 y 7): `manifest` FAIL si falta, no es YAML o su raíz no es un mapa; WARN sin llamadas o con algún `provider: fake` ("corrida de demostración, no evidencia"). `schemas` valida cada artefacto presente contra su modelo (secciones del manifiesto, JSON de `ARTIFACT_ADAPTERS`, `review_request.yml` como mapa y `decision.yml` como `HumanDecision`) y lista hasta 5 errores `ruta: loc: msg`; el ledger tiene su propio check, con número de línea. `prompts` exige `prompt_sha256` y `response_sha256` (WARN si falta alguno: el FAIL lo da `schemas`). `ledger` FAIL: ausente o vacío; línea corrupta o que no valida `DecisionEntry` (antes se descartaba en silencio, `audit.py:85-86`); `stage ∉ STAGES`; `action ∉ LEDGER_ACTIONS` (las `propose`/`exclude`/`verify` de C3); gates decididos por primera vez fuera del orden de `STAGES` (tras un rechazo se puede volver a decidir una etapa anterior, D14); autonomía distinta de la efectiva.

- [ ] **Step 1: Test que falla — crear `tests/test_audit_procedencia.py`**

```python
"""Checks de procedencia y ledger: ``manifest``, ``schemas``, ``prompts``, ``ledger``.

Spec 2026-10-04 §9.3 (filas 1, 3, 5 y 7) y §9.4 (familias robustez, ``schemas``
y ``ledger``). Cada test rompe una sola cosa de la corrida real.
"""

from __future__ import annotations

import pytest
from audit_fixtures import (
    auditar,
    edit_json,
    edit_ledger,
    edit_yaml,
    editar_llamadas,
    fila,
    reetiquetar_llamadas,
)

from revisia.audit import CHECKS
from revisia.config import STAGES

ARTEFACTOS_JSON = (
    "03_screening/decisions.json",
    "03_screening/metrics.json",
    "03_screening/exclusions.json",
    "04_fulltext/decisions.json",
    "05_extraction/extractions.json",
    "05_extraction/agreement.json",
    "06_synthesis/verification.json",
    "07_rob/assessments.json",
    "08_meta/meta_analysis.json",
)

# ── manifest ───────────────────────────────────────────────────────────


def test_manifest_yaml_invalido_falla(corrida) -> None:
    (corrida / "manifest.yml").write_text("slug: [sin cerrar\n", encoding="utf-8")
    manifest = fila(auditar(corrida), "manifest")
    assert manifest.status == "FAIL"
    assert "ilegible (YAML inválido" in manifest.detail


def test_manifest_sin_llamadas_advierte(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(llm_calls=[], models_used=[]))
    manifest = fila(auditar(corrida), "manifest")
    assert manifest.status == "WARN"
    assert "sin llamadas IA" in manifest.detail


def test_manifest_proveedor_real_pasa(corrida) -> None:
    reetiquetar_llamadas(corrida, provider="gemini", deterministic=False)
    manifest = fila(auditar(corrida), "manifest")
    assert manifest.status == "PASS"
    assert "gemini:fake-a" in manifest.detail


# ── schemas y robustez ────────────────────────────────────────────────


def test_schemas_corrida_real_pasa(corrida) -> None:
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "PASS"
    assert "artefactos validan su modelo" in schemas.detail


@pytest.mark.parametrize("rel", ARTEFACTOS_JSON)
def test_artefacto_json_invalido_falla_schemas(corrida, rel: str) -> None:
    (corrida / rel).write_text("{no es json", encoding="utf-8")
    report = auditar(corrida)
    schemas = fila(report, "schemas")
    assert schemas.status == "FAIL"
    assert f"{rel}: JSON inválido" in schemas.detail
    assert len(report.checks) == len(CHECKS)


def test_schemas_metricas_sin_matriz_falla(corrida) -> None:
    # La forma exacta del metrics.json de la reconstrucción C3.
    edit_json(
        corrida / "03_screening" / "metrics.json",
        lambda _m: {"n": 47, "recall": 1.0, "mcc": 0.71, "cohen_kappa": 0.75},
    )
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "03_screening/metrics.json: tp: Field required" in schemas.detail


def test_schemas_llamada_sin_response_sha256_falla(corrida) -> None:
    editar_llamadas(corrida, lambda calls: calls[0].pop("response_sha256"))
    report = auditar(corrida)
    assert "manifest.yml#llm_calls: 0.response_sha256" in fila(report, "schemas").detail
    assert fila(report, "schemas").status == "FAIL"
    assert fila(report, "prompts").status == "WARN"


def test_schemas_verificacion_sin_stage_falla(corrida) -> None:
    edit_json(corrida / "06_synthesis" / "verification.json", lambda v: v.pop("stage"))
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "06_synthesis/verification.json: stage: Field required" in schemas.detail


def test_schemas_herramienta_rob_desconocida_falla(corrida) -> None:
    def _herramienta(assessments: dict) -> None:
        for assessment in assessments.values():
            assessment["tool"] = "Cochrane-RoB"

    edit_json(corrida / "07_rob" / "assessments.json", _herramienta)
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "07_rob/assessments.json" in schemas.detail


def test_schemas_decision_con_approved_no_booleano_falla(corrida) -> None:
    (corrida / "screening_ta" / "decision.yml").write_text(
        'approved: "sí"\nactor: human:revisora\n', encoding="utf-8"
    )
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "screening_ta/decision.yml:" in schemas.detail
    assert "approved: Input should be a valid boolean" in schemas.detail


# ── ledger ─────────────────────────────────────────────────────────────


def test_ledger_linea_corrupta_falla_con_numero_de_linea(corrida) -> None:
    path = corrida / "decisions_ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.insert(1, '{"stage": "screening_ft", "actor": ')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = auditar(corrida)
    ledger = fila(report, "ledger")
    assert ledger.status == "FAIL"
    assert "línea 2: JSON inválido" in ledger.detail
    # Con el ledger ilegible no se relaja nada: se exigen todas las etapas.
    assert report.state is not None and report.state.reached == frozenset(STAGES)


def test_ledger_linea_que_no_valida_decision_entry_falla(corrida) -> None:
    edit_ledger(corrida, lambda entries: entries[0].pop("actor"))
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "línea 1: actor: Field required" in ledger.detail


@pytest.mark.parametrize("accion", ["propose", "exclude", "verify"])
def test_ledger_acciones_que_el_motor_no_emite_fallan(corrida, accion: str) -> None:
    def _insertar(entries: list[dict]) -> None:
        entries.insert(0, {**entries[0], "action": accion, "actor": "agent:opus+sonnet"})

    edit_ledger(corrida, _insertar)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert f"línea 1: acción `{accion}` que el motor no emite" in ledger.detail


def test_ledger_etapa_desconocida_falla(corrida) -> None:
    edit_ledger(corrida, lambda entries: entries[0].update(stage="cribado"))
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "etapa desconocida `cribado`" in ledger.detail


def test_ledger_etapas_desordenadas_falla(corrida) -> None:
    edit_ledger(corrida, lambda entries: [entries[-1], *entries[:-1]])
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "gates fuera del orden de STAGES: reporte → screening_ta" in ledger.detail


def test_ledger_autonomia_distinta_de_la_efectiva_falla(corrida) -> None:
    def _autonomia(entries: list[dict]) -> None:
        for entry in entries:
            if entry["stage"] == "screening_ft":
                entry["autonomy"] = "A1"

    edit_ledger(corrida, _autonomia)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "autonomía A1 en `screening_ft`, la efectiva es A0" in ledger.detail


def test_ledger_volver_a_decidir_tras_un_rechazo_es_valido(corrida) -> None:
    # D14: se puede reanudar después de un reject; queda rastro de ambas.
    def _rechazo_y_vuelta(entries: list[dict]) -> list[dict]:
        def _gate(stage: str) -> dict:
            return next(e for e in entries if (e["stage"], e["action"]) == (stage, "approve"))

        ta, ft = _gate("screening_ta"), _gate("screening_ft")
        rechazo = {
            **ft,
            "action": "reject",
            "detail": {**ft["detail"], "decision_sha256": "0" * 64},
        }
        otra_ta = {**ta, "detail": {**ta["detail"], "decision_sha256": "1" * 64, "reason": "otra"}}
        i = entries.index(ta) + 1
        return [*entries[:i], rechazo, otra_ta, *entries[i:]]

    edit_ledger(corrida, _rechazo_y_vuelta)
    report = auditar(corrida)
    assert fila(report, "ledger").status == "PASS"
    assert fila(report, "final_gate").status == "PASS"
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_procedencia.py -v`
Expected: FAIL en la mayoría: `AssertionError: sin fila 'schemas'`, detalles distintos en `manifest` y `ledger`.

- [ ] **Step 3: `checks_provenance.py`**

Sustituir el contenido completo de `revisia/audit/checks_provenance.py` por:

```python
"""Checks de procedencia: ``manifest``, ``provenance``, ``schemas``, ``prompts``.

``schemas`` valida cada artefacto presente contra el modelo que lo produce:
la reconstrucción de la auditoría 2026-09-03 (C3) traía un ``metrics.json``
sin matriz de confusión y un ``verification.json`` sin ``stage`` que ningún
código del motor puede escribir, y el auditor anterior los daba por buenos
porque solo miraba que existieran.
"""

from __future__ import annotations

from revisia.audit.artifacts import (
    ARTIFACT_ADAPTERS,
    MANIFEST_ADAPTERS,
    AuditContext,
    Loaded,
)
from revisia.audit.model import Verdict
from revisia.orchestration.run_context import PROVENANCE_PIPELINE
from revisia.schemas.artifacts import GATED_STAGES

_NA_MANIFIESTO = "no aplica: el manifiesto no se pudo leer (ver `manifest`)."
_MAX_ERRORES = 5


def check_manifest(ctx: AuditContext) -> Verdict:
    """trAIce M2: manifiesto legible, con las llamadas IA y los modelos usados."""
    loaded = ctx.manifest
    if not loaded.present:
        return "FAIL", "manifest.yml ausente: la corrida no es reproducible."
    if not loaded.ok:
        return "FAIL", f"manifest.yml ilegible ({loaded.error}): la corrida no es reproducible."
    # Las del propio manifiesto (desde la Ola 1, copia de llm_calls.jsonl).
    raw_calls = ctx.manifest_dict.get("llm_calls")
    calls = [c for c in raw_calls if isinstance(c, dict)] if isinstance(raw_calls, list) else []
    if not calls:
        return "WARN", "manifest.yml sin llamadas IA registradas: no hay procedencia que auditar."
    fakes = sum(1 for c in calls if c.get("provider") == "fake")
    if fakes:
        return "WARN", (
            f"corrida de demostración, no evidencia: {fakes}/{len(calls)} llamadas con "
            "proveedor `fake`."
        )
    models = ctx.manifest_dict.get("models_used") or []
    return "PASS", (
        f"manifest.yml con {len(calls)} llamada(s) IA y modelos: "
        f"{', '.join(map(str, models)) or '(sin models_used)'}."
    )


def check_provenance(ctx: AuditContext) -> Verdict:
    """Procedencia: la corrida la produjo el pipeline (auditoría 2026-09-03, C3)."""
    if ctx.manifest_dict is None:
        return "N/A", _NA_MANIFIESTO
    provenance = ctx.manifest_dict.get("provenance")
    if provenance == PROVENANCE_PIPELINE:
        return "PASS", (
            "El manifiesto declara `provenance: pipeline` (marca escrita por el motor; "
            "no es una firma)."
        )
    found = "ausente" if provenance is None else repr(provenance)
    return "FAIL", (
        f"Procedencia {found}: el manifiesto no declara `provenance: pipeline`. "
        "Una corrida reconstruida, o generada antes de que el motor registrara "
        "su procedencia, no es evidencia publicable: regenérala con `revisia run`."
    )


def _validated(ctx: AuditContext) -> list[Loaded]:
    """Todos los artefactos presentes con modelo, ya validados (sin el ledger,
    que tiene su propio check con número de línea)."""
    results: list[Loaded] = []
    if ctx.manifest.present:
        if not ctx.manifest.ok:
            results.append(ctx.manifest)
        else:
            results += [ctx.manifest_section(key) for key in MANIFEST_ADAPTERS]
    if ctx.art.exists("run.json"):
        results.append(ctx.art.run_info())
    results += [ctx.art.artifact(rel) for rel in ARTIFACT_ADAPTERS if ctx.art.exists(rel)]
    for gate in GATED_STAGES:
        if ctx.art.exists(f"{gate}/review_request.yml"):
            results.append(ctx.art.yaml(f"{gate}/review_request.yml"))
        if ctx.art.exists(f"{gate}/decision.yml"):
            results.append(ctx.art.decision(gate))
    return [r for r in results if r.present]


def check_schemas(ctx: AuditContext) -> Verdict:
    """PRISMA 27 / trAIce M5: cada artefacto presente valida el modelo que lo produce."""
    validated = _validated(ctx)
    errors = [f"{r.path}: {r.error}" for r in validated if not r.ok]
    if errors:
        shown = "; ".join(errors[:_MAX_ERRORES])
        more = f" (+{len(errors) - _MAX_ERRORES} más)" if len(errors) > _MAX_ERRORES else ""
        return "FAIL", (
            f"{len(errors)} artefacto(s) no cargan o no validan su modelo: {shown}{more}."
        )
    return "PASS", f"{len(validated)} artefactos validan su modelo."


def check_prompts(ctx: AuditContext) -> Verdict:
    """trAIce M6: cada llamada con el hash de su prompt y de su respuesta."""
    if ctx.manifest_dict is None:
        return "N/A", _NA_MANIFIESTO
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
```

- [ ] **Step 4: `check_ledger` en `checks_hitl.py`**

Sustituir el contenido completo de `revisia/audit/checks_hitl.py` por:

```python
"""Checks del ledger y de la supervisión humana: ``ledger``, ``hitl``, ``final_gate``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.config import JUDGMENT_STAGES, STAGES
from revisia.provenance.ledger import GATE_DECISION_ACTIONS, LEDGER_ACTIONS
from revisia.schemas.artifacts import GATED_STAGES

_NA_LEDGER = "no aplica: sin ledger legible (ver `ledger`)."
_MAX_PROBLEMAS = 5


def effective_autonomy(ctx: AuditContext) -> dict[str, str] | None:
    """Autonomía efectiva de cada gate según el protocolo registrado.

    ``None`` si no hay protocolo legible (sin manifiesto, o corrida en pausa
    antes de escribirlo).
    """
    if ctx.protocol is None:
        return None
    return {gate: ctx.protocol.autonomy_for(gate) for gate in GATED_STAGES}


def _limitar(problems: list[str]) -> str:
    shown = "; ".join(problems[:_MAX_PROBLEMAS])
    more = len(problems) - _MAX_PROBLEMAS
    return shown + (f" (+{more} más)" if more > 0 else "")


def check_ledger(ctx: AuditContext) -> Verdict:
    """trAIce M8 / PRISMA 8: ledger legible, con lo que el motor escribe y en orden.

    Una línea corrupta ya no se descarta en silencio (antes, ``audit.py:85-86``)
    y una acción que ``review_gate`` nunca emite (``propose``/``exclude``/
    ``verify`` en la reconstrucción C3) delata un ledger escrito a mano.
    """
    view = ctx.ledger
    if not view.present:
        return "FAIL", "decisions_ledger.jsonl ausente: sin trazabilidad de decisiones."
    if view.read_error:
        return "FAIL", f"decisions_ledger.jsonl ilegible ({view.read_error})."
    if not view.entries and not view.errors:
        return "FAIL", "decisions_ledger.jsonl vacío: sin trazabilidad de decisiones."

    problems = list(view.errors)
    for number, entry in view.entries:
        if entry.stage not in STAGES:
            problems.append(f"línea {number}: etapa desconocida `{entry.stage}`")
        if entry.action not in LEDGER_ACTIONS:
            problems.append(f"línea {number}: acción `{entry.action}` que el motor no emite")

    # Los gates se deciden por primera vez en el orden de STAGES; tras un
    # rechazo se puede volver a decidir una etapa anterior (D14).
    first: dict[str, int] = {}
    for number, entry in view.entries:
        if entry.action in GATE_DECISION_ACTIONS and entry.stage in STAGES:
            first.setdefault(entry.stage, number)
    ordered = sorted(first, key=first.__getitem__)
    if ordered != sorted(ordered, key=STAGES.index):
        problems.append("gates fuera del orden de STAGES: " + " → ".join(ordered))

    autonomy = effective_autonomy(ctx)
    if autonomy is not None:
        for number, entry in view.entries:
            expected = autonomy.get(entry.stage)
            if expected is not None and entry.autonomy != expected:
                problems.append(
                    f"línea {number}: autonomía {entry.autonomy} en `{entry.stage}`, "
                    f"la efectiva es {expected}"
                )

    if problems:
        return "FAIL", f"{len(problems)} problema(s) en el ledger: {_limitar(problems)}."
    note = "" if autonomy is not None else " (autonomía no verificable: sin protocolo legible)"
    return "PASS", f"{len(view.entries)} entradas válidas, en orden{note}."


def check_hitl(ctx: AuditContext) -> Verdict:
    """trAIce M8: decisiones humanas en las etapas de juicio."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    ledger = ctx.ledger.decisions
    human = [e for e in ledger if e.actor.startswith("human")]
    judgment = [e for e in ledger if e.stage in JUDGMENT_STAGES]
    judgment_human = [e for e in judgment if e.actor.startswith("human")]
    if judgment and not judgment_human:
        return "WARN", (
            f"{len(ledger)} decisiones registradas, pero NINGUNA humana en etapas de "
            "juicio (¿--auto-approve?). Apta para demo; NO publicable sin revisión humana."
        )
    return "PASS", f"{len(ledger)} decisiones en el ledger; {len(human)} humana(s)."


def check_final_gate(ctx: AuditContext) -> Verdict:
    """Gate de honestidad: decisión humana sobre el reporte final."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    reporte = [e for e in ctx.ledger.decisions if e.stage == "reporte"]
    if not reporte:
        return "FAIL", "Sin decisión sobre el reporte final: la corrida está pausada o incompleta."
    last = reporte[-1]
    if last.action == "approve" and last.actor.startswith("human"):
        return "PASS", f"Reporte final aprobado por humano ({last.actor})."
    if last.action in ("approve", "auto-proceed"):
        return "WARN", f"El reporte final no lo aprobó un humano: {last.actor}/{last.action}."
    if last.action == "reject":
        return "FAIL", f"El reporte final fue rechazado por {last.actor}."
    return "FAIL", f"Acción desconocida {last.action} en la decisión final."
```

- [ ] **Step 5: Registrar `schemas`**

En `revisia/audit/__init__.py`, sustituir

```python
    CheckSpec("manifest", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_manifest),
    CheckSpec("provenance", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_provenance),
    CheckSpec("prompts", "trAIce M6", "reporte", checks_provenance.check_prompts),
    CheckSpec("ledger", "trAIce M8 / PRISMA 8", None, checks_hitl.check_ledger),
```

por

```python
    CheckSpec("manifest", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_manifest),
    CheckSpec("provenance", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_provenance),
    CheckSpec("schemas", "PRISMA 27 / trAIce M5", None, checks_provenance.check_schemas),
    CheckSpec("prompts", "trAIce M6", "reporte", checks_provenance.check_prompts),
    CheckSpec("ledger", "trAIce M8 / PRISMA 8", None, checks_hitl.check_ledger),
```

- [ ] **Step 6: Tests existentes que cambian (spec §9.4)**

En `tests/test_audit.py`, sustituir

```python
from __future__ import annotations

import json

from audit_fixtures import auditar, edit_ledger, edit_yaml, fila

from revisia.audit import render_audit_md
```

por

```python
from __future__ import annotations

from audit_fixtures import (
    auditar,
    edit_ledger,
    edit_yaml,
    escribir_metricas,
    fila,
    metricas_validas,
)

from revisia.audit import render_audit_md
```

En `tests/test_audit.py`, sustituir

```python
    assert report.publishable
    statuses = {c.check_id: c.status for c in report.checks}
    assert statuses["manifest"] == "PASS"
    assert statuses["prompts"] == "PASS"
    assert statuses["hitl"] == "PASS"
```

por

```python
    assert report.publishable
    statuses = {c.check_id: c.status for c in report.checks}
    # Proveedor fake: "corrida de demostración, no evidencia" (spec 2026-10-04 §9.3).
    assert statuses["manifest"] == "WARN"
    assert "corrida de demostración" in fila(report, "manifest").detail
    assert statuses["schemas"] == "PASS"
    assert statuses["ledger"] == "PASS"
    assert statuses["prompts"] == "PASS"
    assert statuses["hitl"] == "PASS"
```

En `tests/test_audit.py`, sustituir

```python
    assert fila(report, "ledger").status == "FAIL"


def _escribir_metricas(run, metrics: dict) -> None:
    (run / "03_screening" / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")


def test_audit_gold_kappa_no_calculable_advierte(corrida) -> None:
    _escribir_metricas(corrida, {"recall": 1.0, "cohen_kappa": None})
    gold = fila(auditar(corrida), "gold")
    assert gold.status == "WARN"  # antes: PASS con κ inventado
```

por

```python
    assert fila(report, "ledger").status == "FAIL"


def test_audit_gold_kappa_no_calculable_advierte(corrida) -> None:
    # Gold e IA constantes en la misma clase: κ y MCC indefinidos (None).
    escribir_metricas(corrida, metricas_validas(5, 0, 0, 0))
    gold = fila(auditar(corrida), "gold")
    assert gold.status == "WARN"  # antes: PASS con κ inventado
```

En `tests/test_audit.py`, sustituir

```python
    numérico): la matriz debe tratarse como ilegible en vez de romper la
    auditoría con un TypeError al sumar ``None`` con ``int``."""
    _escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.5, "mcc": 0.4, "tp": None, "fp": 2, "fn": 0, "tn": 0},
    )
    gold = fila(auditar(corrida), "gold")
    assert gold.status == "WARN"
    assert "matriz de confusión ilegible" in gold.detail


def test_audit_ia_una_sola_clase_con_gold_mixto_advierte(corrida) -> None:
```

por

```python
    numérico): la matriz debe tratarse como ilegible en vez de romper la
    auditoría con un TypeError al sumar ``None`` con ``int``."""
    escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.5, "mcc": 0.4, "tp": None, "fp": 2, "fn": 0, "tn": 0},
    )
    report = auditar(corrida)
    gold = fila(report, "gold")
    assert gold.status == "WARN"
    assert "matriz de confusión ilegible" in gold.detail
    assert fila(report, "schemas").status == "FAIL"


def test_audit_ia_una_sola_clase_con_gold_mixto_advierte(corrida) -> None:
```

En `tests/test_audit.py`, sustituir

```python
    (siempre "relevante": fn+tn=0) — kappa=0.0 (no None) y mcc=None no debe
    pasar como PASS; hay que mirar mcc y la matriz, no solo κ."""
    _escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.0, "mcc": None, "tp": 3, "fp": 2, "fn": 0, "tn": 0},
    )
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_una_sola_clase_con_matriz_advierte(corrida) -> None:
```

por

```python
    (siempre "relevante": fn+tn=0) — kappa=0.0 (no None) y mcc=None no debe
    pasar como PASS; hay que mirar mcc y la matriz, no solo κ."""
    escribir_metricas(corrida, metricas_validas(3, 2, 0, 0))
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_una_sola_clase_con_matriz_advierte(corrida) -> None:
```

En `tests/test_audit.py`, sustituir

```python
    gold sin la clase "irrelevante" no es informativo aunque mcc/kappa den
    un número."""
    _escribir_metricas(
        corrida,
        {"recall": 1.0, "cohen_kappa": 0.0, "mcc": 0.0, "tp": 3, "fp": 0, "fn": 2, "tn": 0},
    )
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_mcc_none_formato_antiguo_sin_matriz_advierte(corrida) -> None:
```

por

```python
    gold sin la clase "irrelevante" no es informativo aunque mcc/kappa den
    un número."""
    escribir_metricas(corrida, metricas_validas(3, 0, 2, 0))
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_mcc_none_formato_antiguo_sin_matriz_advierte(corrida) -> None:
```

En `tests/test_audit.py`, sustituir

```python
    decisión se apoya solo en que mcc esté explícitamente en null; sigue
    siendo WARN."""
    _escribir_metricas(corrida, {"recall": 1.0, "cohen_kappa": 0.42, "mcc": None})
    assert fila(auditar(corrida), "gold").status == "WARN"


def test_audit_gold_sano_con_matriz_completa_pasa(corrida) -> None:
    _escribir_metricas(
        corrida,
        {"recall": 0.8, "cohen_kappa": 0.75, "mcc": 0.6, "tp": 4, "fp": 1, "fn": 1, "tn": 4},
    )
    assert fila(auditar(corrida), "gold").status == "PASS"
```

por

```python
    decisión se apoya solo en que mcc esté explícitamente en null; sigue
    siendo WARN."""
    escribir_metricas(corrida, {"recall": 1.0, "cohen_kappa": 0.42, "mcc": None})
    report = auditar(corrida)
    assert fila(report, "gold").status == "WARN"
    assert fila(report, "schemas").status == "FAIL"


def test_audit_gold_sano_con_matriz_completa_pasa(corrida) -> None:
    escribir_metricas(corrida, metricas_validas(4, 1, 1, 4))
    assert fila(auditar(corrida), "gold").status == "PASS"
```

- [ ] **Step 7: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_procedencia.py tests/test_audit.py tests/test_audit_infra.py -v`
Expected: PASS (27 nuevos).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 421 recogidos.

- [ ] **Step 8: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 9: Commit**

```bash
git add revisia/audit tests/test_audit.py tests/test_audit_procedencia.py
git commit -m "feat(audit): schemas, ledger y manifiesto exigentes (C3, A11)" -m "schemas valida cada artefacto presente contra el modelo que lo produce (el metrics.json sin matriz y el verification.json sin stage de C3 dejan de pasar). ledger da FAIL con número de línea ante una línea corrupta, una acción que el motor no emite, gates desordenados o una autonomía distinta de la efectiva. manifest avisa de corridas fake. Spec 2026-10-04 §9.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `timing` y `response_overlap` (plausibilidad temporal, C3)

**Files:**
- Create: `revisia/audit/checks_timing.py`
- Modify: `revisia/audit/__init__.py` (registra `timing` tras `prompts` y `response_overlap` al final)
- Test: `tests/test_audit_timing.py` (nuevo)

**Interfaces:**
- Consumes: `AuditContext.llm_calls`, `.ledger`, `.run_info`, `.manifest_dict` (Tarea 4); `editar_llamadas`, `reetiquetar_llamadas`, `primera_llamada`, `comprimir_llamadas`, `edit_ledger`, `edit_yaml` (Tarea 3).
- Produces: `revisia.audit.checks_timing.parse_utc(value: object) -> tuple[datetime | None, str | None]`; constantes `TOLERANCIA = timedelta(seconds=2)`, `MIN_LLAMADAS_HEURISTICA = 20`, `MEDIANA_MINIMA = timedelta(milliseconds=5)`, `MIN_MARCAS_LEDGER = 4`, `MIN_LLAMADAS_SOLAPE = 10`, `UMBRAL_SOLAPE = 0.5`; `check_timing`, `check_response_overlap`. Filas `timing` (`PRISMA 27 / trAIce M2`, siempre aplica) y `response_overlap` (`trAIce M2`, etapa `reporte`).

Reglas (spec §9.3, filas 6 y 21): **FAIL** si una marca no tiene zona o no se lee; si cae fuera de [inicio, `manifest.created_utc`] ±2 s (inicio = `run.json.started_utc` o, sin él, `manifest.timestamp` con `%Y%m%d-%H%M%S`, que es UTC); si el ledger retrocede más de 2 s; si una llamada declara `deterministic: true` con un proveedor que no es `fake`. **WARN** (nunca FAIL): ≥ 20 llamadas no exentas con mediana de separación < 5 ms (el mensaje menciona las API por lotes); ≥ 4 marcas del ledger con ≥ 50 % sin fracción de segundo (horas tecleadas); límite inferior no verificable ("TEST"). Solo `provider == "fake" and deterministic` está exento de las heurísticas. `response_overlap`: WARN si dos modelos distintos, no fake, con ≥ 10 llamadas cada uno comparten ≥ 50 % de sus `response_sha256` (C3: los 46 de Sonnet dentro de los de Opus; también delata A8).

- [ ] **Step 1: Test que falla — crear `tests/test_audit_timing.py`**

```python
"""Plausibilidad temporal: ``timing`` y ``response_overlap`` (spec 2026-10-04 §9.3).

Las heurísticas solo dan WARN; lo imposible (marcas fuera de la corrida, sin
zona, ledger que retrocede, determinismo declarado por un proveedor real) da
FAIL. Las corridas ``fake`` deterministas están exentas de las heurísticas.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from audit_fixtures import (
    auditar,
    comprimir_llamadas,
    edit_ledger,
    edit_yaml,
    editar_llamadas,
    fila,
    primera_llamada,
    reetiquetar_llamadas,
)


def test_timing_corrida_real_pasa(corrida) -> None:
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS"
    assert "exentas de las heurísticas" in timing.detail


def test_timing_llamadas_en_1_3_ms_solo_advierte(corrida) -> None:
    # Síntoma C3: 24 llamadas no fake en 1,3 ms. Es una heurística: WARN, no FAIL.
    comprimir_llamadas(corrida)
    report = auditar(corrida)
    timing = fila(report, "timing")
    assert timing.status == "WARN"
    assert "24 llamadas no fake con una mediana de 0.057 ms" in timing.detail
    assert "API por lotes" in timing.detail
    assert report.publishable


def test_timing_fake_determinista_exento_aunque_sea_instantaneo(corrida) -> None:
    reetiquetar_llamadas(
        corrida,
        provider="fake",
        deterministic=True,
        inicio=primera_llamada(corrida),
        paso=timedelta(microseconds=10),
    )
    assert fila(auditar(corrida), "timing").status == "PASS"


def test_timing_determinista_no_fake_falla(corrida) -> None:
    reetiquetar_llamadas(corrida, provider="gemini", deterministic=True)
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "`deterministic: true` con proveedor `gemini`" in timing.detail


def _desplazar_ledger(run, delta: timedelta) -> None:
    def _editar(entries: list[dict]) -> None:
        for entry in entries:
            marca = datetime.fromisoformat(entry["timestamp_utc"]) + delta
            entry["timestamp_utc"] = marca.isoformat()

    edit_ledger(run, _editar)


def test_timing_ledger_anterior_al_inicio_falla(corrida) -> None:
    # Síntoma C3: ledger fechado una semana antes de la corrida.
    _desplazar_ledger(corrida, -timedelta(days=7))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "ledger línea 1 anterior al inicio de la corrida" in timing.detail


def test_timing_llamada_posterior_al_manifiesto_falla(corrida) -> None:
    def _tarde(calls: list[dict]) -> None:
        calls[-1]["timestamp_utc"] = "2099-01-01T00:00:00.123456+00:00"

    editar_llamadas(corrida, _tarde)
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "llm_calls[23] posterior al manifiesto" in timing.detail


def test_timing_marca_sin_zona_falla(corrida) -> None:
    edit_ledger(corrida, lambda e: e[0].update(timestamp_utc="2026-10-04T12:00:00.5"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "ledger línea 1: sin zona horaria" in timing.detail


def test_timing_ledger_que_retrocede_falla(corrida) -> None:
    def _adelantar_la_segunda(entries: list[dict]) -> None:
        marca = datetime.fromisoformat(entries[1]["timestamp_utc"]) + timedelta(seconds=30)
        entries[1]["timestamp_utc"] = marca.isoformat()

    edit_ledger(corrida, _adelantar_la_segunda)
    final = primera_llamada(corrida) + timedelta(minutes=5)
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(created_utc=final.isoformat()))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "ledger línea 3: retrocede" in timing.detail


def test_timing_pausa_de_dias_sin_aviso(corrida) -> None:
    # Una pausa humana de días no mueve la mediana: llamadas reales cada 400 ms,
    # con la mitad tres días después. Sin WARN ni FAIL.
    inicio = primera_llamada(corrida)

    def _pausa(calls: list[dict]) -> None:
        for i, call in enumerate(calls):
            call.update(provider="gemini", deterministic=False)
            pausa = timedelta(days=3) if i >= 12 else timedelta(0)
            call["timestamp_utc"] = (inicio + i * timedelta(milliseconds=400) + pausa).isoformat()

    editar_llamadas(corrida, _pausa)
    final = inicio + timedelta(days=3, hours=1)
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(created_utc=final.isoformat()))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "PASS", timing.detail
    assert "mediana entre llamadas no fake 400 ms" in timing.detail


def test_timing_horas_redondas_en_el_ledger_advierten(corrida) -> None:
    def _redondear(entries: list[dict]) -> None:
        for entry in entries:
            marca = datetime.fromisoformat(entry["timestamp_utc"]).replace(microsecond=0)
            entry["timestamp_utc"] = marca.isoformat()

    edit_ledger(corrida, _redondear)
    n = len((corrida / "decisions_ledger.jsonl").read_text(encoding="utf-8").splitlines())
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert f"{n}/{n} marcas del ledger sin fracción de segundo" in timing.detail


def test_timing_limite_inferior_no_verificable_advierte(corrida) -> None:
    # Sin run.json, el inicio sale de `manifest.timestamp`; "TEST" no se puede leer.
    (corrida / "run.json").unlink(missing_ok=True)
    edit_yaml(corrida / "manifest.yml", lambda m: m.update(timestamp="TEST"))
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "WARN"
    assert "límite inferior no verificable (timestamp `TEST`" in timing.detail


# ── response_overlap ────────────────────────────────────────────────────


def test_response_overlap_fake_no_cuenta(corrida) -> None:
    assert fila(auditar(corrida), "response_overlap").status == "PASS"


def test_response_overlap_hashes_de_un_modelo_dentro_de_otro_advierte(corrida) -> None:
    # Síntoma C3: los hashes de respuesta de Sonnet son un subconjunto de los de Opus.
    def _solape(calls: list[dict]) -> None:
        for i, call in enumerate(calls):
            modelo = "opus" if i < 12 else "sonnet"
            call.update(provider="agent", model=modelo, deterministic=False)
            call["response_sha256"] = f"{i % 12:064x}"

    editar_llamadas(corrida, _solape)
    overlap = fila(auditar(corrida), "response_overlap")
    assert overlap.status == "WARN"
    assert "`agent:opus` y `agent:sonnet` comparten 12 de 12 respuestas" in overlap.detail
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_timing.py -v`
Expected: FAIL, `AssertionError: sin fila 'timing'` (y `'response_overlap'`).

- [ ] **Step 3: Crear `revisia/audit/checks_timing.py`**

```python
"""Checks de plausibilidad temporal: ``timing``, ``response_overlap``.

La reconstrucción de la auditoría 2026-09-03 (C3) tenía 140 llamadas en
1,3 ms, un ledger fechado una semana antes de la corrida y a horas redondas,
y los 46 hashes de respuesta de Sonnet dentro de los 94 de Opus. Ninguna de
esas huellas es una firma, pero juntas encarecen mucho fabricar una corrida.

Reglas (spec 2026-10-04 §9.3):

- **FAIL** si una marca no tiene zona horaria o no se puede leer; si cae fuera
  de [inicio de la corrida, ``manifest.created_utc``] con 2 s de tolerancia;
  si el ledger retrocede más de 2 s; si una llamada declara
  ``deterministic: true`` con un proveedor que no es ``fake`` (ningún
  proveedor real lo garantiza: todos ponen ``False``).
- **WARN** (heurísticas, nunca FAIL): ≥ 20 llamadas no exentas con una
  mediana de separación < 5 ms; ≥ 4 marcas del ledger con ≥ 50 % sin
  fracción de segundo; límite inferior no verificable.
- Solo ``provider == "fake" and deterministic`` está exento de las
  heurísticas (las corridas de demostración son instantáneas).
"""

from __future__ import annotations

import re
import statistics
from datetime import UTC, datetime, timedelta
from itertools import combinations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict

TOLERANCIA = timedelta(seconds=2)
MIN_LLAMADAS_HEURISTICA = 20
MEDIANA_MINIMA = timedelta(milliseconds=5)
MIN_MARCAS_LEDGER = 4
MIN_LLAMADAS_SOLAPE = 10
UMBRAL_SOLAPE = 0.5
_TIMESTAMP_CORRIDA = re.compile(r"^\d{8}-\d{6}$")
_MAX = 5
_NA_MANIFIESTO = "no aplica: el manifiesto no se pudo leer (ver `manifest`)."


def parse_utc(value: object) -> tuple[datetime | None, str | None]:
    """``(marca, None)`` o ``(None, motivo)``; una marca sin zona no vale."""
    if not isinstance(value, str):
        return None, f"no es una cadena ({value!r})"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None, f"no es ISO-8601 (`{value}`)"
    if parsed.tzinfo is None:
        return None, f"sin zona horaria (`{value}`)"
    return parsed, None


def _exenta(call: dict) -> bool:
    return call.get("provider") == "fake" and call.get("deterministic") is True


def _limite_inferior(ctx: AuditContext) -> tuple[datetime | None, str | None, str | None]:
    """``(inicio, aviso, fallo)`` de la corrida.

    El inicio es ``run.json.started_utc`` o, sin ``run.json``,
    ``manifest.timestamp`` si cumple ``%Y%m%d-%H%M%S`` (es UTC, ``cli.py``).
    """
    if ctx.run_info is not None:
        parsed, error = parse_utc(ctx.run_info.started_utc)
        return parsed, None, (f"run.json.started_utc: {error}" if error else None)
    stamp = str((ctx.manifest_dict or {}).get("timestamp", ""))
    if _TIMESTAMP_CORRIDA.match(stamp):
        return datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=UTC), None, None
    return None, f"límite inferior no verificable (timestamp `{stamp}`, sin run.json)", None


def _limitar(items: list[str]) -> str:
    more = len(items) - _MAX
    return "; ".join(items[:_MAX]) + (f" (+{more} más)" if more > 0 else "")


def check_timing(ctx: AuditContext) -> Verdict:
    """PRISMA 27 / trAIce M2: las marcas de tiempo son posibles."""
    fails: list[str] = []
    warns: list[str] = []
    marks: list[tuple[str, datetime]] = []

    calls = ctx.llm_calls
    call_marks: list[tuple[dict, datetime]] = []
    for i, call in enumerate(calls):
        parsed, error = parse_utc(call.get("timestamp_utc"))
        if error:
            fails.append(f"llm_calls[{i}]: {error}")
        else:
            call_marks.append((call, parsed))
            marks.append((f"llm_calls[{i}]", parsed))
        if call.get("deterministic") is True and call.get("provider") != "fake":
            fails.append(
                f"llm_calls[{i}]: `deterministic: true` con proveedor `{call.get('provider')}` "
                "(ningún proveedor real lo garantiza)"
            )

    ledger_marks: list[tuple[int, datetime]] = []
    for number, entry in ctx.ledger.entries:
        parsed, error = parse_utc(entry.timestamp_utc)
        if error:
            fails.append(f"ledger línea {number}: {error}")
        else:
            ledger_marks.append((number, parsed))
            marks.append((f"ledger línea {number}", parsed))

    lower, lower_warn, lower_fail = _limite_inferior(ctx)
    warns += [lower_warn] if lower_warn else []
    fails += [lower_fail] if lower_fail else []
    upper = None
    if ctx.manifest_dict is not None and "created_utc" in ctx.manifest_dict:
        upper, error = parse_utc(ctx.manifest_dict.get("created_utc"))
        if error:
            fails.append(f"manifest.created_utc: {error}")

    for label, mark in marks:
        if lower is not None and mark < lower - TOLERANCIA:
            fails.append(f"{label} anterior al inicio de la corrida ({mark.isoformat()})")
        if upper is not None and mark > upper + TOLERANCIA:
            fails.append(f"{label} posterior al manifiesto ({mark.isoformat()})")

    latest: datetime | None = None
    for number, mark in ledger_marks:
        if latest is not None and mark < latest - TOLERANCIA:
            back = (latest - mark).total_seconds()
            fails.append(f"ledger línea {number}: retrocede {back:.0f} s")
        latest = mark if latest is None else max(latest, mark)

    heuristic = sorted(mark for call, mark in call_marks if not _exenta(call))
    median_ms: float | None = None
    if len(heuristic) >= 2:
        gaps = [b - a for a, b in zip(heuristic, heuristic[1:], strict=False)]
        median = statistics.median(gaps)
        median_ms = median.total_seconds() * 1000
        if len(heuristic) >= MIN_LLAMADAS_HEURISTICA and median < MEDIANA_MINIMA:
            warns.append(
                f"{len(heuristic)} llamadas no fake con una mediana de {median_ms:.3f} ms entre "
                "marcas: una llamada real tarda ≥ 300 ms (≥ 1 s con `claude -p`); si usaste una "
                "API por lotes, decláralo"
            )
    if len(ledger_marks) >= MIN_MARCAS_LEDGER:
        redondas = sum(1 for _, mark in ledger_marks if mark.microsecond == 0)
        if redondas * 2 >= len(ledger_marks):
            warns.append(
                f"{redondas}/{len(ledger_marks)} marcas del ledger sin fracción de segundo: "
                "huelen a horas tecleadas"
            )

    if fails:
        return "FAIL", f"{len(fails)} marca(s) imposibles: {_limitar(fails)}."
    if warns:
        return "WARN", "; ".join(warns) + "."
    detail = f"{len(marks)} marcas dentro de [inicio, manifiesto] ±2 s"
    if median_ms is not None:
        detail += f"; mediana entre llamadas no fake {median_ms:.0f} ms"
    elif calls:
        detail += "; llamadas fake deterministas, exentas de las heurísticas"
    return "PASS", detail + "."


def check_response_overlap(ctx: AuditContext) -> Verdict:
    """trAIce M2: dos modelos distintos no devuelven las mismas respuestas."""
    if ctx.manifest_dict is None:
        return "N/A", _NA_MANIFIESTO
    hashes: dict[str, list[str]] = {}
    for call in ctx.llm_calls:
        if call.get("provider") == "fake" or not call.get("response_sha256"):
            continue
        key = f"{call.get('provider')}:{call.get('model')}"
        hashes.setdefault(key, []).append(str(call["response_sha256"]))
    eligible = {m: set(h) for m, h in hashes.items() if len(h) >= MIN_LLAMADAS_SOLAPE}
    findings: list[str] = []
    for a, b in combinations(sorted(eligible), 2):
        common = eligible[a] & eligible[b]
        smaller = min(len(eligible[a]), len(eligible[b]))
        if smaller and len(common) / smaller >= UMBRAL_SOLAPE:
            findings.append(f"`{a}` y `{b}` comparten {len(common)} de {smaller} respuestas")
    if findings:
        return "WARN", (
            "; ".join(findings) + ": dos modelos distintos no dan las mismas respuestas "
            "(reconstrucción, C3, o un callback `agent` que no distingue modelos, A8)."
        )
    return "PASS", (
        f"sin respuestas compartidas entre modelos ({len(eligible)} modelo(s) no fake con "
        f"≥ {MIN_LLAMADAS_SOLAPE} llamadas)."
    )
```

- [ ] **Step 4: Registrar los dos checks**

En `revisia/audit/__init__.py`, sustituir

```python
    checks_quality,
    checks_search,
)
from revisia.audit.artifacts import AuditContext, load_run
```

por

```python
    checks_quality,
    checks_search,
    checks_timing,
)
from revisia.audit.artifacts import AuditContext, load_run
```

En `revisia/audit/__init__.py`, sustituir

```python
    CheckSpec("schemas", "PRISMA 27 / trAIce M5", None, checks_provenance.check_schemas),
    CheckSpec("prompts", "trAIce M6", "reporte", checks_provenance.check_prompts),
    CheckSpec("ledger", "trAIce M8 / PRISMA 8", None, checks_hitl.check_ledger),
    CheckSpec("hitl", "trAIce M8/R1 / PRISMA 8", None, checks_hitl.check_hitl),
```

por

```python
    CheckSpec("schemas", "PRISMA 27 / trAIce M5", None, checks_provenance.check_schemas),
    CheckSpec("prompts", "trAIce M6", "reporte", checks_provenance.check_prompts),
    CheckSpec("timing", "PRISMA 27 / trAIce M2", None, checks_timing.check_timing),
    CheckSpec("ledger", "trAIce M8 / PRISMA 8", None, checks_hitl.check_ledger),
    CheckSpec("hitl", "trAIce M8/R1 / PRISMA 8", None, checks_hitl.check_hitl),
```

En `revisia/audit/__init__.py`, sustituir

```python
    CheckSpec("search_window", "PRISMA-S 9/13", "busqueda", checks_search.check_search_window),
    CheckSpec("registration", "PRISMA 24a", None, checks_search.check_registration),
)


def _run_one(spec: CheckSpec, ctx: AuditContext) -> AuditCheck:
```

por

```python
    CheckSpec("search_window", "PRISMA-S 9/13", "busqueda", checks_search.check_search_window),
    CheckSpec("registration", "PRISMA 24a", None, checks_search.check_registration),
    CheckSpec("response_overlap", "trAIce M2", "reporte", checks_timing.check_response_overlap),
)


def _run_one(spec: CheckSpec, ctx: AuditContext) -> AuditCheck:
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_timing.py -v`
Expected: PASS, 13 tests. Las llamadas en 1,3 ms dan solo WARN y la corrida sigue publicable.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 434 recogidos.

- [ ] **Step 6: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 7: Commit**

```bash
git add revisia/audit tests/test_audit_timing.py
git commit -m "feat(audit): plausibilidad temporal y respuestas compartidas entre modelos (C3)" -m "timing da FAIL ante marcas sin zona, fuera de la corrida (±2 s), un ledger que retrocede o deterministic: true con un proveedor real, y WARN (nunca FAIL) ante ≥ 20 llamadas con mediana < 5 ms o un ledger a horas redondas; las corridas fake deterministas están exentas. response_overlap avisa cuando dos modelos comparten la mitad de sus respuestas (C3, A8). Spec 2026-10-04 §9.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `stage_artifacts`, `arithmetic` (v0.7 y §9.3), `exclusions` y `deliverable`; corrida v0.7 de referencia

**Files:**
- Modify: `revisia/audit/checks_flow.py` (contenido completo), `revisia/audit/__init__.py` (registra `stage_artifacts` y `arithmetic` tras `final_gate`)
- Modify: `tests/audit_fixtures.py` (añade `write_legacy_v07`)
- Test: `tests/test_audit_flujo.py` (nuevo)

**Interfaces:**
- Consumes: `recall_biased_label` (`llm/ensemble.py`), `compute_exclusion_breakdown`, `select_double_extraction_subset`, `confusion`, `kappa_from_matrix`, `mcc`, `wmcc`, `render_prisma2020_flow_csv`, `PrismaCounts`, `ReviewProtocol.screeners_for`.
- Produces: `revisia.audit.checks_flow`: `TA`, `FT`, `CSV`, `STAGE_ARTIFACTS`, `CONDITIONAL_ARTIFACTS`, `MANIFEST_COPIES`, `DELIVERABLE_FILES` (los 8 de hoy + `checklist_s.md`, `checklist_abstracts.md`, `interop/prisma2020_flow.csv`; `meta_analisis.md` si hubo meta-análisis); `included_ids(ctx) -> list[str] | None`; `check_stage_artifacts`, `check_arithmetic`, `check_exclusions`, `check_deliverable`. Filas `stage_artifacts` (`PRISMA 16/27`, por etapa) y `arithmetic` (`PRISMA 16 / trAIce R1`, etapa `reporte`).
- Produces (`tests/audit_fixtures.py`): `write_legacy_v07(tmp_path: Path) -> Path` — una corrida coherente del motor v0.7, sin `run.json`: 5 identificados (1 duplicado), un screener, 1 exclusión IA en T/A y 1 a texto completo, 2 incluidos, 12 llamadas reales, 5 gates humanos.

`arithmetic` (spec §4.4 y §9.3) junta relaciones con nombre ("`9 · excluded_ft == #(final FT == exclude)`") y da FAIL si alguna se rompe (con sus valores), WARN si alguna no se puede verificar y PASS con el número verificado. En la fase 1 todas las corridas carecen de `run.json`, así que el embudo es el de v0.7 (`excluded_ta + fulltext_assessed == screened`; un `unclear` a texto completo cuenta como incluido); la fase 2 añade las relaciones de la Ola 1. Además: Σ `identified_by_source`, `screened`, votos por screener T/A configurado, `ensemble_label == recall_biased_label(votes)`, `final == human or ensemble`, claves de extracciones y evaluaciones = incluidos y su `study_id`, `tool == protocol.rob_tool`, `n_studies` de la doble extracción, CSV PRISMA2020, cota inferior de llamadas (`screened·|ensemble| + evaluados por IA + 2·incluidos + doble + 1`), `models_used` y `deterministic_token_level`, métricas recalculadas desde la matriz (`math.isclose(abs_tol=1e-9)`), `wmcc_fn_weight` del protocolo y las copias del manifiesto iguales a sus ficheros.

- [ ] **Step 1: Test que falla — crear `tests/test_audit_flujo.py`**

```python
"""Checks del flujo PRISMA: ``stage_artifacts``, ``arithmetic``, ``exclusions``, ``deliverable``.

Spec 2026-10-04 §4.4 y §9.3 (filas 11-14). Cada caso de ``arithmetic`` rompe
una sola relación de la corrida real y comprueba que el auditor la nombra.
"""

from __future__ import annotations

import csv
import io
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from audit_fixtures import (
    auditar,
    edit_json,
    edit_yaml,
    editar_llamadas,
    editar_protocolo,
    fila,
    write_legacy_v07,
)

TA = "03_screening/decisions.json"
FT = "04_fulltext/decisions.json"


def _counts(**cambios) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        edit_yaml(run / "manifest.yml", lambda m: m["counts"].update(cambios))

    return _editar


def _json(rel: str, fn: Callable) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        edit_json(run / rel, fn)

    return _editar


def _csv(clave: str, valor: str) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        path = run / "deliverable" / "interop" / "prisma2020_flow.csv"
        rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
        header = rows[0]
        for row in rows[1:]:
            if row[header.index("data")] == clave:
                row[header.index("n")] = valor
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        path.write_text(buf.getvalue(), encoding="utf-8")

    return _editar


def _decision(rid: str, **cambios) -> Callable[[list[dict]], None]:
    def _editar(decisions: list[dict]) -> None:
        for decision in decisions:
            if decision["record_id"] == rid:
                decision.update(cambios)

    return _editar


def _sin_clave(clave: str) -> Callable[[dict], None]:
    def _editar(data: dict) -> None:
        del data[clave]

    return _editar


def _sin_la_ultima(decisions: list[dict]) -> None:
    del decisions[-1]


def _herramienta_rob(assessments: dict) -> None:
    for assessment in assessments.values():
        assessment["tool"] = "ROBINS-I"


RELACIONES_ROTAS = [
    pytest.param(
        _counts(identified_by_source={"OpenAlex": 40, "Crossref": 40, "Europe PMC": 40}),
        "1 · Σ identified_by_source == identified",
        id="identified_by_source-40-40-40",
    ),
    pytest.param(_counts(duplicates_removed=0), "4 · screened", id="duplicados"),
    pytest.param(
        _json(TA, _sin_la_ultima), "5 · len(03_screening/decisions.json)", id="ta-de-menos"
    ),
    pytest.param(
        _json(TA, _decision("10.1000/cocina", ensemble_label="unclear", final_label="unclear")),
        "5 · ensemble_label == recall_biased_label",
        id="ensemble-manipulado",
    ),
    pytest.param(
        _json(TA, _decision("10.1000/cocina", final_label="include")),
        "5 · final_label == human_label or ensemble_label",
        id="final-sin-humano",
    ),
    pytest.param(_counts(excluded_ta=3), "6 · excluded_ta ==", id="excluded-ta"),
    pytest.param(_counts(excluded_ta_ai=1), "6 · excluded_ta_human + excluded_ta_ai", id="ta-h-ia"),
    pytest.param(
        _json(FT, _decision("10.1000/asreview", record_id="10.1000/otro")),
        "7 · ids de 04_fulltext == pasan T/A",
        id="ids-ft",
    ),
    pytest.param(_counts(excluded_ft=2), "9 · excluded_ft ==", id="excluded-ft"),
    pytest.param(
        _counts(ft_exclusion_reasons={"fuera de alcance": 2}),
        "9 · Σ ft_exclusion_reasons",
        id="razones-ft",
    ),
    pytest.param(_counts(included=4), "10 · included == fulltext_assessed", id="included"),
    pytest.param(
        _json("05_extraction/extractions.json", _sin_clave("10.1000/llm-1")),
        "10 · claves de 05_extraction/extractions.json",
        id="extracciones",
    ),
    pytest.param(
        _json("07_rob/assessments.json", _sin_clave("10.1000/llm-1")),
        "10 · claves de 07_rob/assessments.json",
        id="evaluaciones",
    ),
    pytest.param(
        _json("03_screening/exclusions.json", lambda e: e.update(total_excluded=5)),
        "10 · exclusions.total_excluded",
        id="total-excluidos",
    ),
    pytest.param(_csv("records_screened", "9"), "11 · CSV records_screened", id="csv"),
    pytest.param(
        _json("07_rob/assessments.json", _herramienta_rob),
        "§9.3 · assessment.tool == protocol.rob_tool",
        id="herramienta-rob",
    ),
    pytest.param(
        _json("05_extraction/agreement.json", lambda a: a.update(n_studies=2)),
        "§9.3 · extraction_agreement.n_studies",
        id="doble-extraccion",
    ),
]


@pytest.mark.parametrize(("romper", "relacion"), RELACIONES_ROTAS)
def test_arithmetic_cada_relacion_rota_falla(corrida, romper, relacion: str) -> None:
    romper(corrida)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert relacion in arithmetic.detail


def test_arithmetic_corrida_real_pasa(corrida) -> None:
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "PASS"
    assert "relaciones verificadas" in arithmetic.detail


def test_arithmetic_corrida_v07_usa_las_relaciones_v07(tmp_path) -> None:
    report = auditar(write_legacy_v07(tmp_path))
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "PASS"
    assert "relaciones v0.7: corrida sin run.json" in arithmetic.detail


def test_arithmetic_kappa_y_mcc_manipulados_fallan(corrida) -> None:
    # Síntoma C3: κ y MCC que ninguna matriz produce.
    edit_json(
        corrida / "03_screening" / "metrics.json",
        lambda m: m.update(cohen_kappa=0.75, mcc=0.71),
    )
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§9.3 · cohen_kappa recalculado desde la matriz: 0.75 ≠ 1.0" in arithmetic.detail
    assert "§9.3 · mcc recalculado desde la matriz: 0.71 ≠ 1.0" in arithmetic.detail


def test_arithmetic_voto_de_un_modelo_no_configurado_falla(corrida) -> None:
    def _intruso(decisions: list[dict]) -> None:
        decisions[0]["votes"][1]["model"] = "fake:intruso"

    edit_json(corrida / TA, _intruso)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§9.3 · un voto por screener T/A configurado: 10.1000/llm-1" in arithmetic.detail


def test_arithmetic_menos_llamadas_que_decisiones_falla(corrida) -> None:
    editar_llamadas(corrida, lambda calls: calls[:10])
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "llamadas ≥ cota inferior de las decisiones: 10 llamadas < 24" in arithmetic.detail


def test_arithmetic_copia_del_manifiesto_distinta_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["exclusions"].update(excluded_human=3))
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "copia `exclusions` del manifiesto == 03_screening/exclusions.json" in arithmetic.detail


def test_arithmetic_models_used_incoherente_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["models_used"].append("anthropic:opus"))
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§9.3 · models_used == modelos de llm_calls" in arithmetic.detail


def test_arithmetic_wmcc_fn_weight_distinto_del_protocolo_falla(corrida) -> None:
    editar_protocolo(corrida, lambda p: p["thresholds"].update(wmcc_fn_weight=5.0))
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert "§9.3 · wmcc_fn_weight == protocolo: 10.0 ≠ 5.0" in arithmetic.detail


def test_arithmetic_sin_csv_no_verificable_advierte(corrida) -> None:
    (corrida / "deliverable" / "interop" / "prisma2020_flow.csv").unlink()
    report = auditar(corrida)
    arithmetic = fila(report, "arithmetic")
    assert arithmetic.status == "WARN"
    assert "no verificables: 11 · CSV PRISMA2020" in arithmetic.detail
    assert fila(report, "deliverable").status == "FAIL"


# ── stage_artifacts ────────────────────────────────────────────────────


def test_stage_artifacts_falta_04_fulltext_falla(corrida) -> None:
    # Síntoma C3: faltaban 01, 02, 04, 05 y 07.
    shutil.rmtree(corrida / "04_fulltext")
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "FAIL"
    assert "screening_ft: 04_fulltext/decisions.json" in stage.detail


def test_stage_artifacts_doble_extraccion_declarada_sin_fichero_falla(corrida) -> None:
    (corrida / "05_extraction" / "agreement.json").unlink()
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "FAIL"
    assert "extraccion: 05_extraction/agreement.json" in stage.detail


def test_stage_artifacts_corrida_real_pasa(corrida) -> None:
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "PASS"
    assert "etapas alcanzadas presentes" in stage.detail


# ── exclusions ─────────────────────────────────────────────────────────


def test_exclusions_ausente_falla(corrida) -> None:
    (corrida / "03_screening" / "exclusions.json").unlink()
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert "ausente" in exclusions.detail


def test_exclusions_distinta_del_recalculo_falla(corrida) -> None:
    # Síntoma C3: `excluded_human: 3` que el motor no puede generar.
    edit_json(corrida / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=3))
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert "excluded_human 3 ≠" in exclusions.detail


def test_exclusions_sin_decisiones_no_se_recalcula_y_falla(corrida) -> None:
    (corrida / TA).unlink()
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert "no se puede recalcular" in exclusions.detail


def test_exclusions_conteos_ta_distintos_del_recalculo_falla(corrida) -> None:
    edit_yaml(
        corrida / "manifest.yml",
        lambda m: m["counts"].update(excluded_ta_human=1, excluded_ta_ai=1),
    )
    exclusions = fila(auditar(corrida), "exclusions")
    assert exclusions.status == "FAIL"
    assert "counts.excluded_ta_human/ai 1/1 ≠ 0/2 (solo T/A)" in exclusions.detail


# ── deliverable ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "nombre",
    ["checklist_s.md", "checklist_abstracts.md", "interop/prisma2020_flow.csv"],
)
def test_deliverable_exige_checklists_y_csv(corrida, nombre: str) -> None:
    (corrida / "deliverable" / nombre).unlink()
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert f"{nombre} (falta)" in deliverable.detail


def test_deliverable_exige_meta_analisis_si_hubo_efectos(corrida) -> None:
    (corrida / "deliverable" / "meta_analisis.md").unlink()
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert "meta_analisis.md (falta)" in deliverable.detail


def test_deliverable_fichero_vacio_falla(corrida) -> None:
    (corrida / "deliverable" / "metodologia.md").write_text("  \n", encoding="utf-8")
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert "metodologia.md (vacío)" in deliverable.detail
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_flujo.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'write_legacy_v07' from 'audit_fixtures'`.

- [ ] **Step 3: `write_legacy_v07` en `tests/audit_fixtures.py`**

En `tests/audit_fixtures.py`, sustituir

```python
import shutil
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
```

por

```python
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
```

En `tests/audit_fixtures.py`, sustituir

```python
import yaml

from revisia.audit import AuditCheck, AuditReport, run_audit
from revisia.metrics import ScreeningMetrics, kappa_from_matrix, mcc, wmcc
from revisia.schemas.artifacts import JOURNAL_PATHS


def auditar(run_dir: Path) -> AuditReport:
```

por

```python
import yaml

from revisia.audit import AuditCheck, AuditReport, run_audit
from revisia.config import ReviewProtocol
from revisia.exclusions import compute_exclusion_breakdown
from revisia.exports import PrismaCounts, render_prisma2020_flow_csv
from revisia.metrics import ScreeningMetrics, kappa_from_matrix, mcc, wmcc
from revisia.provenance.ledger import DecisionEntry
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.artifacts import JOURNAL_PATHS
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision, ScreeningVote
from revisia.schemas.verification import CitationCheck, VerificationReport


def auditar(run_dir: Path) -> AuditReport:
```

En `tests/audit_fixtures.py`, sustituir

```python
    (run_dir / "manifest.yml").unlink()
    (run_dir / "03_screening" / "exclusions.json").unlink()
```

por

```python
    (run_dir / "manifest.yml").unlink()
    (run_dir / "03_screening" / "exclusions.json").unlink()


# ── Corrida v0.7 (anterior a la Ola 1) ──────────────────────────────────

_V07_INICIO = datetime(2026, 9, 20, 10, 0, 0, tzinfo=UTC)
_V07_MODELO = "gemini:gemini-2.5-flash"
# record_id → (título, etiqueta T/A, etiqueta FT o None si no pasó T/A).
_V07_REGISTROS = {
    "10.2000/a": ("Cribado con LLM en revisiones de salud", "include", "include"),
    "10.2000/b": ("Estudio ajeno al cribado", "exclude", None),
    "10.2000/c": ("Cribado sin métricas de desempeño", "include", "exclude"),
    "10.2000/d": ("Ensemble de modelos para cribar títulos", "include", "include"),
}


def _v07_marca(segundos: float) -> str:
    return (_V07_INICIO + timedelta(seconds=segundos, microseconds=250_000)).isoformat()


def _v07_decision(record_id: str, label: str, phase: str) -> dict:
    vote = ScreeningVote(
        model=_V07_MODELO,
        label=label,
        confidence=0.8,
        rationale=f"v0.7: {label}",
        criteria_violated=["sin métricas"] if label == "exclude" else [],
    )
    decision = ScreeningDecision(
        record_id=record_id,
        phase=phase,
        votes=[vote],
        ensemble_label=label,
        final_label=label,
        citations_checked=[record_id],
    )
    # v0.7 no tenía los campos que añade la Ola 1.
    return decision.model_dump(exclude={"fulltext_status", "human_reason", "human_actor"})


def write_legacy_v07(tmp_path: Path) -> Path:
    """Escribe una corrida coherente del motor v0.7 (sin ``run.json``).

    Es lo que dejaba el pipeline antes de la Ola 1: 5 identificados (1
    duplicado), un solo screener, 1 exclusión IA en T/A y 1 a texto completo,
    2 incluidos, 12 llamadas de un proveedor real y los 5 gates aprobados por
    un humano. El auditor la evalúa con las relaciones v0.7 (D13).
    """
    run = tmp_path / "runs" / "legado-v07-20260920-100000"
    for sub in ("03_screening", "04_fulltext", "05_extraction", "06_synthesis", "07_rob"):
        (run / sub).mkdir(parents=True)
    (run / "deliverable" / "interop").mkdir(parents=True)

    ta = [
        _v07_decision(rid, label, "title_abstract") for rid, (_, label, _) in _V07_REGISTROS.items()
    ]
    ft = [
        _v07_decision(rid, label, "fulltext")
        for rid, (_, _, label) in _V07_REGISTROS.items()
        if label is not None
    ]
    included = [d["record_id"] for d in ft if d["final_label"] == "include"]
    extractions = {rid: ExtractionRecord(study_id=rid).model_dump() for rid in included}
    assessments = {
        rid: RoBAssessment(study_id=rid, tool="RoB2", overall="low").model_dump()
        for rid in included
    }
    verification = VerificationReport(
        stage="reporte",
        checks=[
            CitationCheck(
                claim="El cribado con LLM alcanza recall alto [10.2000/a].",
                cited_id="10.2000/a",
                exists_in_corpus=True,
                grounded=True,
            )
        ],
    ).model_dump()
    decisions = [ScreeningDecision.model_validate(d) for d in [*ta, *ft]]
    exclusions = compute_exclusion_breakdown(decisions).model_dump()
    counts = {
        "identified": 5,
        "identified_by_source": {"OpenAlex": 3, "Crossref": 2},
        "duplicates_removed": 1,
        "removed_automation": 0,
        "removed_other": 0,
        "screened": 4,
        "excluded_ta": 1,
        "excluded_ta_human": 0,
        "excluded_ta_ai": 1,
        "fulltext_assessed": 3,
        "fulltext_abstract_only": 0,
        "excluded_ft": 1,
        "ft_exclusion_reasons": {"sin métricas": 1},
        "included": 2,
    }
    # 4 T/A + 3 FT + 2 extracciones + 2 RoB + 1 síntesis, una cada 1,2 s.
    calls = [
        RunMeta(
            provider="gemini",
            model="gemini-2.5-flash",
            seed=7,
            temperature=0.0,
            prompt_sha256=sha256_text(f"prompt {i}"),
            response_sha256=sha256_text(f"respuesta {i}"),
            timestamp_utc=_v07_marca(1 + 1.2 * i),
            deterministic=False,
        ).model_dump()
        for i in range(12)
    ]
    protocol = ReviewProtocol(
        slug="legado-v07",
        title="Corrida v0.7 de referencia",
        question={"text": "¿Sirven los LLM para cribar?", "framework": "PICO"},
        databases=["OpenAlex", "Crossref"],
        registration={"osf": "OSF-LEGADO"},
        search_window={"from": "2015-01-01", "to": "2026-09-01", "executed": "2026-09-20"},
        llm={"default": {"provider": "gemini", "model": "gemini-2.5-flash", "seed": 7}},
    ).model_dump(mode="json")
    manifest = {
        "slug": "legado-v07",
        "created_utc": _v07_marca(60),
        "timestamp": "20260920-100000",
        "provenance": "pipeline",
        "protocol": protocol,
        "counts": counts,
        "llm_calls": calls,
        "models_used": [_V07_MODELO],
        "deterministic_token_level": False,
        "verification": verification,
        "risk_of_bias": assessments,
        "exclusions": exclusions,
    }

    def _json(rel: str, data: object) -> None:
        (run / rel).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    _json("03_screening/decisions.json", ta)
    _json("03_screening/exclusions.json", exclusions)
    _json("04_fulltext/decisions.json", ft)
    _json("05_extraction/extractions.json", extractions)
    _json("06_synthesis/verification.json", verification)
    _json("07_rob/assessments.json", assessments)
    (run / "manifest.yml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    gates = (
        ("screening_ta", "A1"),
        ("screening_ft", "A0"),
        ("extraccion", "A0"),
        ("rob", "A0"),
        ("reporte", "A1"),
    )
    ledger = []
    for i, (gate, autonomy) in enumerate(gates):
        (run / gate).mkdir()
        (run / gate / "review_request.yml").write_text(f"stage: {gate}\n", encoding="utf-8")
        (run / gate / "decision.yml").write_text(
            "approved: true\nactor: human:revisora\n", encoding="utf-8"
        )
        entry = DecisionEntry(
            stage=gate,
            actor="human:revisora",
            autonomy=autonomy,
            action="approve",
            timestamp_utc=_v07_marca(6 + 10 * i),
        )
        ledger.append(entry.model_dump_json() + "\n")
    (run / "decisions_ledger.jsonl").write_text("".join(ledger), encoding="utf-8")

    deliverable = run / "deliverable"
    for name in (
        "prisma_flow.md",
        "metodologia.md",
        "tabla_extraccion.md",
        "risk_of_bias.md",
        "referencias.bib",
        "checklist_2020.md",
        "checklist_traice.md",
        "checklist_s.md",
        "checklist_abstracts.md",
    ):
        (deliverable / name).write_text(f"# {name} (v0.7)\n", encoding="utf-8")
    (deliverable / "documento.md").write_text(
        "# Corrida v0.7\n\nEl cribado con LLM alcanza recall alto [10.2000/a].\n",
        encoding="utf-8",
    )
    (deliverable / "interop" / "prisma2020_flow.csv").write_text(
        render_prisma2020_flow_csv(PrismaCounts.model_validate(counts)), encoding="utf-8"
    )
    return run
```

- [ ] **Step 4: `checks_flow.py`**

Sustituir el contenido completo de `revisia/audit/checks_flow.py` por:

```python
"""Checks del flujo PRISMA: ``stage_artifacts``, ``arithmetic``, ``exclusions``, ``deliverable``.

``arithmetic`` verifica las relaciones entre artefactos de la spec 2026-10-04
§4.4 (las que ya se pueden comprobar con lo que hay en disco) más las de §9.3:
la reconstrucción C3 declaraba 120 identificados con 140 llamadas para 120
registros cribados por dos modelos, y el auditor anterior no sumaba nada.
Sin ``run.json`` (corrida anterior a la Ola 1) se aplican las relaciones v0.7
del embudo (un ``unclear`` a texto completo contaba como incluido): esa
corrida ya no es publicable (D13), pero el diagnóstico sigue siendo útil.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.exclusions import compute_exclusion_breakdown
from revisia.extraction_agreement import select_double_extraction_subset
from revisia.llm.ensemble import recall_biased_label
from revisia.metrics import kappa_from_matrix, mcc, wmcc
from revisia.schemas.records import SearchRecord

TA = "03_screening/decisions.json"
FT = "04_fulltext/decisions.json"
CSV = "deliverable/interop/prisma2020_flow.csv"
_MAX = 6

# Artefactos que toda etapa alcanzada deja en disco (spec §4.2; los de la Ola 1
# llegan con PR-B..PR-D).
STAGE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "screening_ta": (TA,),
    "screening_ft": (FT, "03_screening/exclusions.json"),
    "extraccion": ("05_extraction/extractions.json",),
    "rob": ("07_rob/assessments.json",),
    "sintesis": ("06_synthesis/verification.json",),
    "reporte": ("manifest.yml",),
}
# Artefactos que existen si el manifiesto registra su copia.
CONDITIONAL_ARTIFACTS: dict[str, tuple[str, str]] = {
    "screening_metrics": ("screening_ta", "03_screening/metrics.json"),
    "extraction_agreement": ("extraccion", "05_extraction/agreement.json"),
    "meta_analysis": ("rob", "08_meta/meta_analysis.json"),
}
# Copias del manifiesto que deben coincidir con su fichero (§9.3).
MANIFEST_COPIES: dict[str, str] = {
    "exclusions": "03_screening/exclusions.json",
    "screening_metrics": "03_screening/metrics.json",
    "verification": "06_synthesis/verification.json",
    "risk_of_bias": "07_rob/assessments.json",
    "extraction_agreement": "05_extraction/agreement.json",
    "meta_analysis": "08_meta/meta_analysis.json",
}

DELIVERABLE_FILES: tuple[str, ...] = (
    "documento.md",
    "prisma_flow.md",
    "metodologia.md",
    "tabla_extraccion.md",
    "risk_of_bias.md",
    "referencias.bib",
    "checklist_2020.md",
    "checklist_traice.md",
    "checklist_s.md",
    "checklist_abstracts.md",
    "interop/prisma2020_flow.csv",
)


def _limitar(items: list[str]) -> str:
    more = len(items) - _MAX
    return "; ".join(items[:_MAX]) + (f" (+{more} más)" if more > 0 else "")


def included_ids(ctx: AuditContext) -> list[str] | None:
    """Incluidos según las decisiones a texto completo (``None`` si no se leen).

    Relaciones v0.7 (sin ``run.json``): ``include`` o ``unclear``.
    """
    ft = ctx.art.artifact(FT)
    if not ft.ok:
        return None
    return [d.record_id for d in ft.value if d.final_label in {"include", "unclear"}]


def check_stage_artifacts(ctx: AuditContext) -> Verdict:
    """PRISMA 16/27: cada etapa alcanzada dejó sus artefactos (§4.2)."""
    required: list[tuple[str, str]] = []
    for stage, rels in STAGE_ARTIFACTS.items():
        if stage in ctx.state.reached:
            required += [(stage, rel) for rel in rels]
    manifest = ctx.manifest_dict or {}
    for key, (stage, rel) in CONDITIONAL_ARTIFACTS.items():
        if key in manifest and stage in ctx.state.reached:
            required.append((stage, rel))
    missing = [f"{stage}: {rel}" for stage, rel in required if not ctx.art.exists(rel)]
    if missing:
        return "FAIL", f"faltan artefactos de etapas alcanzadas: {_limitar(missing)}."
    stages = sorted({stage for stage, _ in required}, key=list(STAGE_ARTIFACTS).index)
    return "PASS", (
        f"{len(required)} artefactos de {len(stages)} etapas alcanzadas presentes "
        f"({', '.join(stages)})."
    )


@dataclass(frozen=True)
class _Relation:
    name: str
    ok: bool | None  # None = no verificable
    detail: str = ""


class _Relations:
    """Acumula relaciones verificadas, rotas y no verificables."""

    def __init__(self) -> None:
        self.items: list[_Relation] = []

    def eq(self, name: str, left: Any, right: Any) -> None:
        self.items.append(_Relation(name, left == right, f"{left!r} ≠ {right!r}"))

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.items.append(_Relation(name, ok, detail))

    def unverifiable(self, name: str, why: str) -> None:
        self.items.append(_Relation(name, None, why))

    def when(self, ready: bool, name: str, why: str, fn: Callable[[], None]) -> None:
        if ready:
            fn()
        else:
            self.unverifiable(name, why)


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, abs_tol=1e-9)


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def _read_csv(ctx: AuditContext) -> dict[str, str] | None:
    loaded = ctx.art.text(CSV)
    if not loaded.ok:
        return None
    try:
        rows = list(csv.DictReader(io.StringIO(loaded.value)))
    except csv.Error:
        return None
    return {row.get("data", ""): row.get("n", "") for row in rows}


def _screeners(ctx: AuditContext) -> list[str] | None:
    if ctx.protocol is None:
        return None
    try:
        return [f"{c.provider}:{c.model}" for c in ctx.protocol.screeners_for("screening_ta")]
    except KeyError:
        return None


def _funnel(ctx: AuditContext, rel: _Relations) -> None:
    counts_loaded = ctx.manifest_section("counts")
    counts = counts_loaded.value if counts_loaded.ok else None
    ta_loaded, ft_loaded = ctx.art.artifact(TA), ctx.art.artifact(FT)
    ta = ta_loaded.value if ta_loaded.ok else None
    ft = ft_loaded.value if ft_loaded.ok else None
    sin_conteos = "manifest.counts ausente o inválido"
    sin_ta, sin_ft = f"{TA} ausente o inválido", f"{FT} ausente o inválido"

    if counts is None:
        rel.unverifiable("conteos del embudo", sin_conteos)
        return
    if counts.identified_by_source:
        rel.eq(
            "1 · Σ identified_by_source == identified",
            sum(counts.identified_by_source.values()),
            counts.identified,
        )
    rel.eq(
        "4 · screened == identified − duplicates_removed − removed_*",
        counts.screened,
        counts.identified
        - counts.duplicates_removed
        - counts.removed_automation
        - counts.removed_other,
    )
    rel.eq(
        "v0.7 · excluded_ta + fulltext_assessed == screened",
        counts.excluded_ta + counts.fulltext_assessed,
        counts.screened,
    )
    rel.eq(
        "10 · included == fulltext_assessed − excluded_ft",
        counts.included,
        counts.fulltext_assessed - counts.excluded_ft,
    )
    rel.eq(
        "9 · Σ ft_exclusion_reasons == excluded_ft",
        sum(counts.ft_exclusion_reasons.values()),
        counts.excluded_ft,
    )
    if counts.excluded_ta_human is not None and counts.excluded_ta_ai is not None:
        rel.eq(
            "6 · excluded_ta_human + excluded_ta_ai == excluded_ta",
            counts.excluded_ta_human + counts.excluded_ta_ai,
            counts.excluded_ta,
        )

    def _ta() -> None:
        rel.eq(f"5 · len({TA}) == screened", len(ta), counts.screened)
        rel.eq(
            "6 · excluded_ta == #(final T/A == exclude)",
            counts.excluded_ta,
            sum(1 for d in ta if d.final_label == "exclude"),
        )
        bad_ensemble = [
            d.record_id
            for d in ta
            if d.votes and d.ensemble_label != recall_biased_label([v.label for v in d.votes])
        ]
        rel.check(
            "5 · ensemble_label == recall_biased_label(votes)",
            not bad_ensemble,
            ", ".join(bad_ensemble),
        )
        bad_final = [
            d.record_id for d in ta if d.final_label != (d.human_label or d.ensemble_label)
        ]
        rel.check(
            "5 · final_label == human_label or ensemble_label", not bad_final, ", ".join(bad_final)
        )
        screeners = _screeners(ctx)
        if screeners is None:
            rel.unverifiable("§9.3 · votos de los screeners T/A", "protocolo no legible")
        else:
            bad_votes = [
                d.record_id
                for d in ta
                if len(d.votes) != len(screeners) or any(v.model not in screeners for v in d.votes)
            ]
            rel.check(
                "§9.3 · un voto por screener T/A configurado",
                not bad_votes,
                f"{', '.join(bad_votes)} (screeners: {', '.join(screeners)})",
            )

    rel.when(ta is not None, "relaciones del cribado T/A", sin_ta, _ta)

    def _ft() -> None:
        passed = {d.record_id for d in ta if d.final_label in {"include", "unclear"}}
        rel.check(
            "7 · ids de 04_fulltext == pasan T/A",
            {d.record_id for d in ft} == passed,
            f"{sorted({d.record_id for d in ft} ^ passed)}",
        )
        rel.eq(f"v0.7 · len({FT}) == fulltext_assessed", len(ft), counts.fulltext_assessed)
        rel.eq(
            "9 · excluded_ft == #(final FT == exclude)",
            counts.excluded_ft,
            sum(1 for d in ft if d.final_label == "exclude"),
        )
        bad = [
            d.record_id
            for d in ft
            if len(d.votes) != 1 or d.final_label != (d.human_label or d.ensemble_label)
        ]
        rel.check("v0.7 · un voto FT y final == human or ensemble", not bad, ", ".join(bad))
        rel.eq(
            "v0.7 · included == #(final FT ∈ {include, unclear})",
            counts.included,
            len(included_ids(ctx) or []),
        )

    rel.when(
        ta is not None and ft is not None,
        "relaciones del texto completo",
        sin_ft if ft is None else sin_ta,
        _ft,
    )


def _included_artifacts(ctx: AuditContext, rel: _Relations) -> None:
    ids = included_ids(ctx)
    if ids is None:
        rel.unverifiable("10 · artefactos de los incluidos", f"{FT} ausente o inválido")
        return
    for path, label in (
        ("05_extraction/extractions.json", "extracciones"),
        ("07_rob/assessments.json", "evaluaciones"),
    ):
        loaded = ctx.art.artifact(path)
        if not loaded.ok:
            rel.unverifiable(f"10 · claves de {path}", f"{path} ausente o inválido")
            continue
        rel.check(
            f"10 · claves de {path} == incluidos",
            set(loaded.value) == set(ids),
            f"{label}: {sorted(set(loaded.value) ^ set(ids))}",
        )
        bad = [k for k, v in loaded.value.items() if v.study_id != k]
        rel.check(f"10 · study_id == clave en {path}", not bad, ", ".join(bad))
    assessments = ctx.art.artifact("07_rob/assessments.json")
    if assessments.ok and ctx.protocol is not None:
        tools = sorted({a.tool for a in assessments.value.values()})
        rel.check(
            "§9.3 · assessment.tool == protocol.rob_tool",
            all(t == ctx.protocol.rob_tool for t in tools),
            f"{tools} ≠ {ctx.protocol.rob_tool}",
        )
    agreement = ctx.art.artifact("05_extraction/agreement.json")
    if agreement.ok:
        subset = select_double_extraction_subset([SearchRecord(record_id=i, title="") for i in ids])
        rel.eq(
            "§9.3 · extraction_agreement.n_studies == subconjunto de doble extracción",
            agreement.value.n_studies,
            len(subset),
        )
    exclusions = ctx.art.artifact("03_screening/exclusions.json")
    counts = ctx.manifest_section("counts")
    if exclusions.ok and counts.ok:
        rel.eq(
            "10 · exclusions.total_excluded == excluded_ta + excluded_ft",
            exclusions.value.total_excluded,
            counts.value.excluded_ta + counts.value.excluded_ft,
        )


def _csv(ctx: AuditContext, rel: _Relations) -> None:
    counts = ctx.manifest_section("counts")
    values = _read_csv(ctx)
    if values is None or not counts.ok:
        rel.unverifiable("11 · CSV PRISMA2020", f"{CSV} o manifest.counts ilegible")
        return
    c = counts.value
    expected = {
        "database_results": c.identified,
        "duplicates": c.duplicates_removed,
        "records_screened": c.screened,
        "records_excluded": c.excluded_ta,
        "dbr_sought_reports": c.fulltext_assessed,  # v0.7: buscados = evaluados
        "dbr_notretrieved_reports": 0,
        "dbr_assessed": c.fulltext_assessed,
        "new_studies": c.included,
    }
    for key, value in expected.items():
        rel.eq(f"11 · CSV {key}", values.get(key), str(value))


def _calls(ctx: AuditContext, rel: _Relations) -> None:
    manifest = ctx.manifest_dict or {}
    calls = ctx.llm_calls
    rel.eq(
        "§9.3 · models_used == modelos de llm_calls",
        sorted(manifest.get("models_used") or []),
        sorted({f"{c.get('provider')}:{c.get('model')}" for c in calls}),
    )
    rel.eq(
        "§9.3 · deterministic_token_level == all(deterministic)",
        manifest.get("deterministic_token_level"),
        all(c.get("deterministic") is True for c in calls) if calls else True,
    )
    counts = ctx.manifest_section("counts")
    if not counts.ok:
        rel.unverifiable("§9.3 · cota inferior de llamadas", "manifest.counts ilegible")
        return
    c = counts.value
    members = len(_screeners(ctx) or [None])
    agreement = ctx.art.artifact("05_extraction/agreement.json")
    doubles = agreement.value.n_studies if agreement.ok else 0
    floor = (
        c.screened * members
        + (c.fulltext_assessed - c.fulltext_rescued)
        + 2 * c.included
        + doubles
        + 1
    )
    rel.check(
        "§9.3 · llamadas ≥ cota inferior de las decisiones",
        len(calls) >= floor,
        f"{len(calls)} llamadas < {floor} = {c.screened}·{members} + "
        f"{c.fulltext_assessed - c.fulltext_rescued} + 2·{c.included} + {doubles} + 1",
    )


def _metrics(ctx: AuditContext, rel: _Relations) -> None:
    loaded = ctx.art.artifact("03_screening/metrics.json")
    if not loaded.present:
        return
    if not loaded.ok:
        rel.unverifiable("§9.3 · métricas desde la matriz", "metrics.json inválido")
        return
    m = loaded.value
    tp, fp, fn, tn = m.tp, m.fp, m.fn, m.tn
    rel.eq("§9.3 · n == tp+fp+fn+tn", m.n, tp + fp + fn + tn)
    recomputed = {
        "recall": _ratio(tp, tp + fn),
        "lost_evidence": _ratio(fn, tp + fn),
        "precision": _ratio(tp, tp + fp),
        "mcc": mcc(tp, fp, fn, tn),
        "wmcc": wmcc(tp, fp, fn, tn, fn_weight=m.wmcc_fn_weight),
        "cohen_kappa": kappa_from_matrix(tp, fp, fn, tn),
    }
    for name, value in recomputed.items():
        declared = getattr(m, name)
        rel.check(
            f"§9.3 · {name} recalculado desde la matriz",
            _close(declared, value),
            f"{declared!r} ≠ {value!r}",
        )
    if ctx.protocol is not None:
        rel.eq(
            "§9.3 · wmcc_fn_weight == protocolo",
            m.wmcc_fn_weight,
            float(ctx.protocol.thresholds.get("wmcc_fn_weight", 10.0)),
        )


def _copies(ctx: AuditContext, rel: _Relations) -> None:
    manifest = ctx.manifest_dict or {}
    for key, path in MANIFEST_COPIES.items():
        loaded = ctx.art.json(path)
        if key not in manifest and not loaded.present:
            continue
        if key not in manifest:
            rel.check(f"§9.3 · copia `{key}` del manifiesto", False, f"{path} sin copia")
        elif not loaded.present:
            rel.check(f"§9.3 · copia `{key}` del manifiesto", False, f"{path} ausente")
        elif not loaded.ok:
            rel.unverifiable(f"§9.3 · copia `{key}` del manifiesto", f"{path} ilegible")
        else:
            rel.check(
                f"§9.3 · copia `{key}` del manifiesto == {path}",
                manifest[key] == loaded.value,
                "distinta",
            )


def check_arithmetic(ctx: AuditContext) -> Verdict:
    """PRISMA 16 / trAIce R1: los artefactos cuadran entre sí (§4.4, §9.3)."""
    if ctx.manifest_dict is None:
        return "N/A", "no aplica: el manifiesto no se pudo leer (ver `manifest`)."
    rel = _Relations()
    _funnel(ctx, rel)
    _included_artifacts(ctx, rel)
    _csv(ctx, rel)
    _calls(ctx, rel)
    _metrics(ctx, rel)
    _copies(ctx, rel)

    broken = [f"{r.name}: {r.detail}" for r in rel.items if r.ok is False]
    unverifiable = [f"{r.name} ({r.detail})" for r in rel.items if r.ok is None]
    verified = sum(1 for r in rel.items if r.ok)
    mode = " (relaciones v0.7: corrida sin run.json)" if ctx.run_info is None else ""
    if broken:
        return "FAIL", f"{len(broken)} relación(es) rota(s){mode}: {_limitar(broken)}."
    if unverifiable:
        return "WARN", (
            f"{verified} relaciones verificadas{mode}; no verificables: {_limitar(unverifiable)}."
        )
    return "PASS", f"{verified} relaciones verificadas{mode}."


def check_exclusions(ctx: AuditContext) -> Verdict:
    """trAIce R1: el desglose humano/IA coincide con el recálculo desde las decisiones."""
    loaded = ctx.art.artifact("03_screening/exclusions.json")
    if not loaded.present:
        return "FAIL", "03_screening/exclusions.json ausente: sin desglose humano/IA (trAIce R1)."
    if not loaded.ok:
        return "FAIL", f"03_screening/exclusions.json inválido ({loaded.error})."
    ta, ft = ctx.art.artifact(TA), ctx.art.artifact(FT)
    if not (ta.ok and ft.ok):
        return "FAIL", (
            f"no se puede recalcular el desglose: falta o no valida {TA if not ta.ok else FT}."
        )
    declared = loaded.value
    recomputed = compute_exclusion_breakdown([*ta.value, *ft.value])
    diffs = [
        f"{field} {getattr(declared, field)} ≠ {getattr(recomputed, field)}"
        for field in type(recomputed).model_fields
        if getattr(declared, field) != getattr(recomputed, field)
    ]
    counts = ctx.manifest_section("counts")
    if counts.ok and counts.value.excluded_ta_human is not None:
        ta_only = compute_exclusion_breakdown(ta.value)
        c = counts.value
        if (c.excluded_ta_human, c.excluded_ta_ai) != (ta_only.excluded_human, ta_only.excluded_ai):
            diffs.append(
                f"counts.excluded_ta_human/ai {c.excluded_ta_human}/{c.excluded_ta_ai} ≠ "
                f"{ta_only.excluded_human}/{ta_only.excluded_ai} (solo T/A)"
            )
    if diffs:
        return "FAIL", f"distinto del recálculo desde las decisiones: {'; '.join(diffs)}."
    return "PASS", (
        f"coincide con el recálculo: {recomputed.total_excluded} exclusiones "
        f"({recomputed.excluded_human} humanas, {recomputed.excluded_ai} IA)."
    )


def check_deliverable(ctx: AuditContext) -> Verdict:
    """PRISMA 16/16b/17/18/27: entregable completo y sin ficheros vacíos."""
    required = list(DELIVERABLE_FILES)
    if "meta_analysis" in (ctx.manifest_dict or {}) or ctx.art.exists("08_meta/meta_analysis.json"):
        required.append("meta_analisis.md")
    problems: list[str] = []
    for name in required:
        loaded = ctx.art.text(f"deliverable/{name}")
        if not loaded.present:
            problems.append(f"{name} (falta)")
        elif not loaded.ok or not loaded.value.strip():
            problems.append(f"{name} ({'vacío' if loaded.ok else loaded.error})")
    if problems:
        return "FAIL", f"Entregable incompleto: {', '.join(problems)}."
    return "PASS", f"Entregable completo ({len(required)} artefactos)."
```

- [ ] **Step 5: Registrar `stage_artifacts` y `arithmetic`**

En `revisia/audit/__init__.py`, sustituir

```python
    CheckSpec("hitl", "trAIce M8/R1 / PRISMA 8", None, checks_hitl.check_hitl),
    CheckSpec("final_gate", "trAIce M8", None, checks_hitl.check_final_gate),
    CheckSpec("exclusions", "trAIce R1", "screening_ft", checks_flow.check_exclusions),
    CheckSpec("deliverable", "PRISMA 16/16b/17/18/27", "reporte", checks_flow.check_deliverable),
```

por

```python
    CheckSpec("hitl", "trAIce M8/R1 / PRISMA 8", None, checks_hitl.check_hitl),
    CheckSpec("final_gate", "trAIce M8", None, checks_hitl.check_final_gate),
    CheckSpec("stage_artifacts", "PRISMA 16/27", None, checks_flow.check_stage_artifacts),
    CheckSpec("arithmetic", "PRISMA 16 / trAIce R1", "reporte", checks_flow.check_arithmetic),
    CheckSpec("exclusions", "trAIce R1", "screening_ft", checks_flow.check_exclusions),
    CheckSpec("deliverable", "PRISMA 16/16b/17/18/27", "reporte", checks_flow.check_deliverable),
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_flujo.py -v`
Expected: PASS, 38 tests (17 relaciones rotas parametrizadas).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 472 recogidos.

- [ ] **Step 7: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 8: Commit**

```bash
git add revisia/audit tests/audit_fixtures.py tests/test_audit_flujo.py
git commit -m "feat(audit): artefactos por etapa, aritmética del embudo, exclusiones y entregable" -m "stage_artifacts exige los artefactos de cada etapa alcanzada (C3: faltaban 04, 05, 07). arithmetic verifica las relaciones de §4.4 y §9.3 que ya se pueden comprobar (embudo v0.7 sin run.json, votos, incluidos, CSV PRISMA2020, cota inferior de llamadas, métricas desde la matriz, copias del manifiesto). exclusions recalcula el desglose humano/IA; deliverable exige checklists S y de resúmenes, CSV y meta_analisis.md si hubo efectos. write_legacy_v07 para auditar corridas antiguas como diagnóstico (D13). Spec 2026-10-04 §9.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `hitl` y `final_gate` exigentes (D8, C1)

**Files:**
- Modify: `revisia/audit/checks_hitl.py` (contenido completo: `check_hitl` y `check_final_gate` nuevos)
- Modify: `tests/test_audit.py` (spec §9.4: `…sin_decisiones_humanas_advierte_hitl` → `…_falla_hitl`; los dos de auto-approve/auto-proceed pasan a FAIL y se renombran `…_falla`; la pausa en `reporte` dice "en pausa en `reporte`")
- Test: `tests/test_audit_hitl.py` (nuevo)

**Interfaces:**
- Consumes: `AuditContext.gates` (`summarize_gates`), `.state`, `.requests`; `AUTO_APPROVE_ACTOR`, `HUMAN_ACTOR_PREFIX`, `GATE_DECISION_ACTIONS` (PR-0); `pausar_en_screening_ft` (Tarea 3).
- Produces: `check_hitl`, `check_final_gate` (`checks_hitl.py`).

Reglas (spec §9.3 "`hitl` en detalle", fase 1, y fila 10): `hitl` FAIL si la decisión efectiva de una etapa de juicio alcanzada no es de un actor `human:`; si hay **cualquier** actor `auto-approve (demo)` en el ledger (D8); si se saltó un gate (etapa de juicio sin decisión y otra posterior decidida); si una decisión humana no tiene su `<gate>/review_request.yml` (no pasó por el gate: así es la reconstrucción C3); si `exclusions.excluded_human` supera el número de `label` con `to: exclude` (la vía independiente contra el `excluded_human: 3` de C3, que funciona aunque falte `decisions.json`). WARN con actor `human:desconocido`. `final_gate` FAIL: acción desconocida; pausa ("corrida en pausa en `X`: sin decisión final."); interrupción; rechazo (en `reporte` o en un gate intermedio); `auto-approve`/`auto-proceed` (antes WARN); aprobación humana sin `reporte/review_request.yml`.

- [ ] **Step 1: Test que falla — crear `tests/test_audit_hitl.py`**

```python
"""Supervisión humana y gate final: ``hitl`` y ``final_gate`` (spec 2026-10-04 §9.3).

D8: ``auto-approve (demo)`` o ``auto-proceed`` en un gate de juicio o en el
final es FAIL. Una etapa de juicio alcanzada sin decisión humana, un gate
saltado o una decisión humana sin su ``review_request.yml`` también.
"""

from __future__ import annotations

import pytest
from audit_fixtures import auditar, edit_json, edit_ledger, fila, pausar_en_screening_ft

from revisia.schemas.artifacts import GATED_STAGES


def _actor(stage: str, actor: str):
    def _editar(entries: list[dict]) -> None:
        for entry in entries:
            if entry["stage"] == stage:
                entry["actor"] = actor

    return _editar


@pytest.mark.parametrize("gate", GATED_STAGES)
def test_hitl_auto_approve_en_cualquier_gate_falla(corrida, gate: str) -> None:
    edit_ledger(corrida, _actor(gate, "auto-approve (demo)"))
    report = auditar(corrida)
    hitl = fila(report, "hitl")
    assert hitl.status == "FAIL"
    assert f"decisiones de `auto-approve (demo)` en {gate}" in hitl.detail
    assert not report.publishable
    if gate == "reporte":
        assert fila(report, "final_gate").status == "FAIL"


def test_hitl_excluded_human_sin_etiquetas_falla(corrida) -> None:
    # Síntoma C3, por una vía que no necesita decisions.json.
    edit_json(corrida / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=3))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "exclusions.json declara 3 exclusiones humanas" in hitl.detail


def test_hitl_etiquetas_exclude_respaldan_exclusiones_humanas(corrida) -> None:
    def _etiqueta(entries: list[dict]) -> list[dict]:
        ta = entries[0]
        label = {
            **ta,
            "action": "label",
            "target": "10.1000/cocina",
            "detail": {"from": "exclude", "to": "exclude", "reason": "fuera de alcance"},
        }
        return [label, *entries]

    edit_ledger(corrida, _etiqueta)
    edit_json(corrida / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=1))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "PASS"
    assert "1 etiqueta(s) por registro" in hitl.detail


def test_hitl_actor_desconocido_advierte(corrida) -> None:
    edit_ledger(corrida, _actor("screening_ft", "human:desconocido"))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "WARN"
    assert "`screening_ft`: actor `human:desconocido`" in hitl.detail


def test_hitl_gate_saltado_falla(corrida) -> None:
    edit_ledger(corrida, lambda entries: [e for e in entries if e["stage"] != "screening_ft"])
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "gate saltado: `screening_ft` sin decisión y `extraccion` decidida" in hitl.detail


def test_hitl_decision_humana_sin_solicitud_falla(corrida) -> None:
    (corrida / "extraccion" / "review_request.yml").unlink()
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`extraccion`: decisión humana sin solicitud" in hitl.detail


def test_hitl_corrida_real_pasa(corrida) -> None:
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "PASS"
    assert "decisión humana en 4 etapa(s) de juicio" in hitl.detail


# ── Estado de la corrida y gate final ─────────────────────────────────


def test_pausa_en_screening_ft_final_gate_falla_y_hitl_pasa_en_ta(corrida) -> None:
    pausar_en_screening_ft(corrida)
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert final_gate.detail == "corrida en pausa en `screening_ft`: sin decisión final."
    hitl = fila(report, "hitl")
    assert hitl.status == "PASS"
    assert "decisión humana en 1 etapa(s)" in hitl.detail
    for check_id in ("arithmetic", "deliverable", "grounding", "exclusions"):
        assert fila(report, check_id).status == "N/A"


def test_corrida_interrumpida_sin_solicitud_falla_el_gate_final(corrida) -> None:
    pausar_en_screening_ft(corrida)
    (corrida / "screening_ft" / "review_request.yml").unlink()
    report = auditar(corrida)
    assert report.state is not None and report.state.status == "interrupted"
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "corrida interrumpida en `screening_ft`" in final_gate.detail


def test_rechazo_en_un_gate_intermedio_falla_el_gate_final(corrida) -> None:
    def _rechazar_ft(entries: list[dict]) -> list[dict]:
        ft = next(e for e in entries if (e["stage"], e["action"]) == ("screening_ft", "approve"))
        previas = [e for e in entries if e["stage"] == "screening_ta"]
        return [*previas, {**ft, "action": "reject"}]

    edit_ledger(corrida, _rechazar_ft)
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "corrida rechazada en `screening_ft` por human:revisora" in final_gate.detail


def test_final_gate_aprobacion_sin_solicitud_falla(corrida) -> None:
    # Síntoma C3: un `approve` humano de reporte que no pasó por el gate.
    (corrida / "reporte" / "review_request.yml").unlink()
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "falta `reporte/review_request.yml`" in final_gate.detail
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_hitl.py -v`
Expected: FAIL en los de auto-approve, gate saltado, solicitud ausente, `excluded_human` y estado (el `hitl` portado solo da WARN/PASS y `final_gate` dice "pausada o incompleta").

- [ ] **Step 3: `checks_hitl.py`**

Sustituir el contenido completo de `revisia/audit/checks_hitl.py` por:

```python
"""Checks del ledger y de la supervisión humana: ``ledger``, ``hitl``, ``final_gate``.

Antes de la Ola 1, ``hitl`` nunca daba FAIL y una aprobación de
``--auto-approve`` en el gate final solo era WARN: una corrida sin ninguna
decisión humana salía "APTA para preparar publicación" (auditoría 2026-09-03,
C1/A11). Ahora una etapa de juicio sin decisión humana, un ``auto-approve``
en cualquier gate (D8) o un gate final sin aprobación humana son FAIL.
"""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.config import JUDGMENT_STAGES, STAGES
from revisia.provenance.ledger import (
    AUTO_APPROVE_ACTOR,
    GATE_DECISION_ACTIONS,
    HUMAN_ACTOR_PREFIX,
    LEDGER_ACTIONS,
)
from revisia.schemas.artifacts import GATED_STAGES

_NA_LEDGER = "no aplica: sin ledger legible (ver `ledger`)."
_MAX_PROBLEMAS = 5


def effective_autonomy(ctx: AuditContext) -> dict[str, str] | None:
    """Autonomía efectiva de cada gate según el protocolo registrado.

    ``None`` si no hay protocolo legible (sin manifiesto, o corrida en pausa
    antes de escribirlo).
    """
    if ctx.protocol is None:
        return None
    return {gate: ctx.protocol.autonomy_for(gate) for gate in GATED_STAGES}


def _limitar(problems: list[str]) -> str:
    shown = "; ".join(problems[:_MAX_PROBLEMAS])
    more = len(problems) - _MAX_PROBLEMAS
    return shown + (f" (+{more} más)" if more > 0 else "")


def check_ledger(ctx: AuditContext) -> Verdict:
    """trAIce M8 / PRISMA 8: ledger legible, con lo que el motor escribe y en orden.

    Una línea corrupta ya no se descarta en silencio (antes, ``audit.py:85-86``)
    y una acción que ``review_gate`` nunca emite (``propose``/``exclude``/
    ``verify`` en la reconstrucción C3) delata un ledger escrito a mano.
    """
    view = ctx.ledger
    if not view.present:
        return "FAIL", "decisions_ledger.jsonl ausente: sin trazabilidad de decisiones."
    if view.read_error:
        return "FAIL", f"decisions_ledger.jsonl ilegible ({view.read_error})."
    if not view.entries and not view.errors:
        return "FAIL", "decisions_ledger.jsonl vacío: sin trazabilidad de decisiones."

    problems = list(view.errors)
    for number, entry in view.entries:
        if entry.stage not in STAGES:
            problems.append(f"línea {number}: etapa desconocida `{entry.stage}`")
        if entry.action not in LEDGER_ACTIONS:
            problems.append(f"línea {number}: acción `{entry.action}` que el motor no emite")

    # Los gates se deciden por primera vez en el orden de STAGES; tras un
    # rechazo se puede volver a decidir una etapa anterior (D14).
    first: dict[str, int] = {}
    for number, entry in view.entries:
        if entry.action in GATE_DECISION_ACTIONS and entry.stage in STAGES:
            first.setdefault(entry.stage, number)
    ordered = sorted(first, key=first.__getitem__)
    if ordered != sorted(ordered, key=STAGES.index):
        problems.append("gates fuera del orden de STAGES: " + " → ".join(ordered))

    autonomy = effective_autonomy(ctx)
    if autonomy is not None:
        for number, entry in view.entries:
            expected = autonomy.get(entry.stage)
            if expected is not None and entry.autonomy != expected:
                problems.append(
                    f"línea {number}: autonomía {entry.autonomy} en `{entry.stage}`, "
                    f"la efectiva es {expected}"
                )

    if problems:
        return "FAIL", f"{len(problems)} problema(s) en el ledger: {_limitar(problems)}."
    note = "" if autonomy is not None else " (autonomía no verificable: sin protocolo legible)"
    return "PASS", f"{len(view.entries)} entradas válidas, en orden{note}."


def _excluded_human(ctx: AuditContext) -> int | None:
    """``excluded_human`` declarado (fichero o, si no se lee, la copia del manifiesto)."""
    loaded = ctx.art.artifact("03_screening/exclusions.json")
    if loaded.ok:
        return loaded.value.excluded_human
    copy = ctx.manifest_section("exclusions")
    return copy.value.excluded_human if copy.ok else None


def check_hitl(ctx: AuditContext) -> Verdict:
    """trAIce M8/R1 / PRISMA 8: decide un humano en cada etapa de juicio alcanzada."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    decisions = ctx.ledger.decisions
    fails: list[str] = []
    warns: list[str] = []

    auto = sorted({e.stage for e in decisions if e.actor == AUTO_APPROVE_ACTOR}, key=STAGES.index)
    if auto:
        fails.append(
            f"decisiones de `{AUTO_APPROVE_ACTOR}` en {', '.join(auto)} "
            "(D8: --auto-approve no es revisión humana)"
        )

    reached = [s for s in JUDGMENT_STAGES if s in ctx.state.reached]
    for stage in reached:
        gate = ctx.gates.get(stage)
        if gate is None:
            later = [g for g in GATED_STAGES[GATED_STAGES.index(stage) + 1 :] if g in ctx.gates]
            fails.append(
                f"gate saltado: `{stage}` sin decisión y `{later[0]}` decidida"
                if later
                else f"`{stage}` alcanzada sin decisión"
            )
        elif not gate.actor.startswith(HUMAN_ACTOR_PREFIX):
            fails.append(
                f"`{stage}`: decisión efectiva de `{gate.actor}` ({gate.action}), no humana"
            )
        elif stage not in ctx.requests:
            fails.append(
                f"`{stage}`: decisión humana sin solicitud (falta `{stage}/review_request.yml`)"
            )
        elif gate.actor == "human:desconocido":
            warns.append(f"`{stage}`: actor `human:desconocido` (declara `actor:` en decision.yml)")

    # Vía independiente contra el `excluded_human: 3` de C3: cada exclusión
    # humana deja una entrada `label` con `to: exclude` (spec §4.3).
    declared = _excluded_human(ctx)
    labels_exclude = sum(
        1 for e in decisions if e.action == "label" and e.detail.get("to") == "exclude"
    )
    if declared is not None and declared > labels_exclude:
        fails.append(
            f"exclusions.json declara {declared} exclusiones humanas y el ledger solo registra "
            f"{labels_exclude} etiquetas `exclude`"
        )

    if fails:
        return "FAIL", f"{_limitar(fails)}."
    if warns:
        return "WARN", f"{_limitar(warns)}."
    actors = sorted({ctx.gates[s].actor for s in reached})
    n_labels = sum(1 for e in decisions if e.action == "label")
    return "PASS", (
        f"decisión humana en {len(reached)} etapa(s) de juicio alcanzada(s) "
        f"({', '.join(actors) or 'ninguna'}); {n_labels} etiqueta(s) por registro."
    )


def check_final_gate(ctx: AuditContext) -> Verdict:
    """trAIce M8: el reporte final lo aprueba un humano, a través de su gate."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    reporte = [e for e in ctx.ledger.decisions if e.stage == "reporte"]
    if reporte and reporte[-1].action not in GATE_DECISION_ACTIONS | {"flag_review"}:
        last = reporte[-1]
        return "FAIL", f"Acción desconocida `{last.action}` en la decisión final ({last.actor})."

    state = ctx.state
    if state.status == "paused":
        return "FAIL", f"corrida en pausa en `{state.pending_stage}`: sin decisión final."
    if state.status == "interrupted":
        return "FAIL", f"corrida interrumpida en `{state.pending_stage}`: sin decisión final."
    if state.status == "rejected":
        actor = ctx.gates[state.pending_stage].actor
        if state.pending_stage == "reporte":
            return "FAIL", f"El reporte final fue rechazado por {actor}."
        return "FAIL", (
            f"corrida rechazada en `{state.pending_stage}` por {actor}: sin decisión final."
        )

    gate = ctx.gates.get("reporte")
    if gate is None:
        return "FAIL", "Sin decisión sobre el reporte final."
    if gate.action != "approve" or not gate.actor.startswith(HUMAN_ACTOR_PREFIX):
        return "FAIL", (
            f"El reporte final no lo aprobó un humano: {gate.actor}/{gate.action} "
            "(D8: el gate final exige una decisión humana)."
        )
    if "reporte" not in ctx.requests:
        return "FAIL", (
            "aprobación humana sin solicitud: falta `reporte/review_request.yml` "
            "(la decisión no pasó por el gate)."
        )
    return "PASS", f"Reporte final aprobado por humano ({gate.actor})."
```

- [ ] **Step 4: Tests existentes que cambian de expectativa (spec §9.4)**

En `tests/test_audit.py`, sustituir

```python
        entry["actor"] = "agent:screener"


def test_audit_sin_decisiones_humanas_advierte_hitl(corrida) -> None:
    edit_ledger(corrida, _sin_humanos)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "WARN"
    assert "NO publicable sin revisión humana" in hitl.detail


def test_audit_sin_gold_advierte(corrida) -> None:
```

por

```python
        entry["actor"] = "agent:screener"


def test_audit_sin_decisiones_humanas_falla_hitl(corrida) -> None:
    # Antes WARN y "APTA": una corrida sin ninguna decisión humana en las
    # etapas de juicio no es publicable (auditoría 2026-09-03, C1/A11).
    edit_ledger(corrida, _sin_humanos)
    report = auditar(corrida)
    hitl = fila(report, "hitl")
    assert hitl.status == "FAIL"
    assert "`screening_ta`: decisión efectiva de `agent:screener` (approve), no humana" in (
        hitl.detail
    )
    assert report.publishable is False


def test_audit_sin_gold_advierte(corrida) -> None:
```

En `tests/test_audit.py`, sustituir

```python
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "pausada o incompleta" in final_gate.detail
    assert report.publishable is False


def _set_ultima_decision_reporte(run, *, action: str, actor: str) -> None:
```

por

```python
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "en pausa en `reporte`" in final_gate.detail
    assert report.publishable is False


def _set_ultima_decision_reporte(run, *, action: str, actor: str) -> None:
```

En `tests/test_audit.py`, sustituir

```python
    assert fila(auditar(corrida), "final_gate").status == "PASS"


def test_audit_gate_final_auto_approve_no_es_humano_advierte(corrida) -> None:
    # `--auto-approve` sin decision.yml deja actor "auto-approve (demo)": no es
    # aprobación humana, así que no puede ser PASS (revisión final 2026-09-25).
    _set_ultima_decision_reporte(corrida, action="approve", actor="auto-approve (demo)")
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "WARN"
    assert "no lo aprobó un humano" in final_gate.detail
    assert "auto-approve (demo)" in final_gate.detail
    assert report.publishable  # WARN no bloquea publicabilidad, a diferencia de FAIL


def test_audit_gate_final_auto_proceed_advierte(corrida) -> None:
    # `reporte` en A2/A3 se auto-ejecuta y notifica (agent:reporte): tampoco es
    # una decisión humana.
    _set_ultima_decision_reporte(corrida, action="auto-proceed", actor="agent:reporte")
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "WARN"
    assert "no lo aprobó un humano" in final_gate.detail
    assert "agent:reporte" in final_gate.detail
```

por

```python
    assert fila(auditar(corrida), "final_gate").status == "PASS"


def test_audit_gate_final_auto_approve_no_es_humano_falla(corrida) -> None:
    # `--auto-approve` sin decision.yml deja actor "auto-approve (demo)": no es
    # aprobación humana. Antes WARN; con D8 es FAIL y la corrida no es publicable.
    _set_ultima_decision_reporte(corrida, action="approve", actor="auto-approve (demo)")
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
    assert "no lo aprobó un humano" in final_gate.detail
    assert "auto-approve (demo)" in final_gate.detail
    assert report.publishable is False


def test_audit_gate_final_auto_proceed_falla(corrida) -> None:
    # `reporte` en A2/A3 se auto-ejecuta y notifica (agent:reporte): tampoco es
    # una decisión humana (D8).
    _set_ultima_decision_reporte(corrida, action="auto-proceed", actor="agent:reporte")
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "no lo aprobó un humano" in final_gate.detail
    assert "agent:reporte" in final_gate.detail
```

- [ ] **Step 5: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_hitl.py tests/test_audit.py tests/test_pipeline_fake.py -v`
Expected: PASS (15 nuevos). `test_pipeline_fake.py` sigue en verde: su corrida rechazada y su corrida en pausa dan FAIL en `final_gate`.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 487 recogidos.

- [ ] **Step 6: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 7: Commit**

```bash
git add revisia/audit/checks_hitl.py tests/test_audit.py tests/test_audit_hitl.py
git commit -m "feat(audit): hitl y gate final sin auto-approve (D8, C1)" -m "hitl da FAIL sin decisión humana en una etapa de juicio alcanzada, ante cualquier auto-approve, un gate saltado, una decisión humana sin su review_request.yml o más exclusiones humanas que etiquetas exclude en el ledger (C3). final_gate da FAIL con auto-approve o auto-proceed (antes WARN), en pausa (\"en pausa en X\"), interrumpida o rechazada. Una corrida con --auto-approve ya no es publicable. Spec 2026-10-04 §9.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: `gold`, `thresholds` (D7), `grounding` (D8) y `search_window`

**Files:**
- Modify: `revisia/audit/checks_quality.py` (contenido completo), `revisia/audit/checks_search.py` (`check_search_window`), `revisia/audit/__init__.py` (registra `thresholds` tras `gold`)
- Test: `tests/test_audit_calidad.py` (nuevo)

**Interfaces:**
- Consumes: `KNOWN_THRESHOLDS` (PR-0), `wilson_interval`, `fmt_metric`, `ScreeningMetrics`, `HUMAN_ACTOR_PREFIX`, `included_ids` y `TA` (Tarea 7), `write_legacy_v07` (Tarea 7), `editar_protocolo`, `escribir_metricas`, `metricas_validas` (Tarea 3).
- Produces (`checks_quality.py`): `potencia_minima(target: float) -> int | None` (⌈1/(1−umbral)⌉ con redondeo; `None` con umbral ≥ 1); `ai_exclusions_without_label(ctx) -> int | None`; `check_gold`, `check_thresholds`, `check_grounding`. Fila `thresholds` (`trAIce M9/R2 / PRISMA 8, 24c`, etapa `screening_ta`).

Reglas: `gold` como hoy, sobre `ScreeningMetrics` validado (WARN sin gold, con κ o MCC `None` o con el gold o la IA de una sola clase; la matriz ilegible la da `schemas`). `thresholds` (D7): **FAIL** si el recall IA queda bajo `recall_target` (el detalle dice cuántas exclusiones IA de T/A quedan sin etiqueta humana y cómo remediarlo: etiquetarlas en `screening_ta/decision.yml` y reanudar); WARN si κ < `kappa_min` (desviación a declarar, PRISMA 24c: el caso A11 de κ = 0,0 nunca vuelve a ser PASS), si el recall alcanza el umbral con menos de ⌈1/(1−umbral)⌉ positivos (20 para 0,95: gold sin potencia), si un umbral no es medible, si hay una clave desconocida (`kapa_min`) o si no se declara ninguno; el detalle informa siempre el intervalo de Wilson al 95 % ("recall 0.95 [IC95 0.76–0.99] ≥ 0.95 con 20 positivos; κ 0.93 ≥ 0.60"). La rebaja a WARN cuando todas las exclusiones IA tienen etiqueta humana llega en la fase 2 (Tarea 15). `grounding` (D8): FAIL si una cita marcada no tiene `flag_review` humana en la decisión efectiva de `reporte` (mismo `decision_sha256`, `verdict: false_positive` y razón), si la adjudica un actor no humano, si `hallucination_flagged` no es lo que da `recompute_flag` o si `exists_in_corpus: true` para un id que no está entre los incluidos; WARN con `checks: []` y algún incluido, y si todas las marcas están adjudicadas por un humano; `N/A` si `verification.json` falta o no valida (lo marcan `stage_artifacts` y `schemas`). `search_window`: sin `01_search/log.json` la fecha la tecleó un humano y nunca es PASS (C3: el auditor anterior la aprobaba por eso).

- [ ] **Step 1: Test que falla — crear `tests/test_audit_calidad.py`**

```python
"""Calidad: ``thresholds`` (D7), ``grounding`` (D8), ``search_window`` y ``registration``.

Spec 2026-10-04 §9.3 (filas 16, 17, 19, 20) y §9.4 (familias ``thresholds`` y
``grounding``). La corrida real tiene ``recall_target: 0.95`` y un gold de 4
positivos (recall 1.0): sin potencia, así que su ``thresholds`` es WARN.
"""

from __future__ import annotations

from audit_fixtures import (
    auditar,
    edit_json,
    edit_ledger,
    editar_protocolo,
    escribir_metricas,
    fila,
    metricas_validas,
    write_legacy_v07,
)

from revisia.audit.checks_quality import potencia_minima

# ── thresholds (D7) ────────────────────────────────────────────────────


def test_potencia_minima_del_gold() -> None:
    assert potencia_minima(0.95) == 20
    assert potencia_minima(0.9) == 10
    assert potencia_minima(0.8) == 5
    assert potencia_minima(1.0) is None


def test_thresholds_recall_bajo_umbral_con_exclusiones_ia_sin_revisar_falla(corrida) -> None:
    escribir_metricas(corrida, metricas_validas(18, 0, 2, 10))
    report = auditar(corrida)
    thresholds = fila(report, "thresholds")
    assert thresholds.status == "FAIL"
    assert "recall 0.90 [IC95 0.70–0.97] < 0.95 con 20 positivos" in thresholds.detail
    assert "2 exclusiones IA de T/A sin etiqueta humana" in thresholds.detail
    assert "screening_ta/decision.yml" in thresholds.detail
    assert not report.publishable


def test_thresholds_kappa_cero_bajo_kappa_min_advierte_nunca_pasa(corrida) -> None:
    # El caso exacto de A11: κ = 0.0 daba PASS. Con recall alto y gold
    # suficiente, un κ bajo es sobreinclusión: desviación a declarar (WARN).
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kappa_min": 0.6})
    )
    escribir_metricas(corrida, metricas_validas(20, 5, 0, 0))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "κ 0.00 < 0.60: desviación del protocolo, decláralo (PRISMA 24c)" in thresholds.detail
    assert "recall 1.00 [IC95 0.84–1.00] ≥ 0.95 con 20 positivos" in thresholds.detail


def test_thresholds_recall_igual_al_umbral_con_gold_suficiente_pasa(corrida) -> None:
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kappa_min": 0.6})
    )
    escribir_metricas(corrida, metricas_validas(19, 0, 1, 10))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "PASS"
    assert thresholds.detail == (
        "recall 0.95 [IC95 0.76–0.99] ≥ 0.95 con 20 positivos; κ 0.93 ≥ 0.60."
    )


def test_thresholds_recall_perfecto_con_pocos_positivos_advierte(corrida) -> None:
    escribir_metricas(corrida, metricas_validas(5, 0, 0, 5))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "recall 1.00 [IC95 0.57–1.00] ≥ 0.95 con solo 5 positivos" in thresholds.detail
    assert "con menos de 20 un solo fallo ya baja del umbral" in thresholds.detail


def test_thresholds_recall_bajo_con_gold_pequeno_sigue_fallando(corrida) -> None:
    # Un recall por debajo nunca se excusa por gold pequeño (D7).
    escribir_metricas(corrida, metricas_validas(3, 0, 1, 4))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "FAIL"
    assert "recall 0.75 [IC95 0.30–0.95] < 0.95 con 4 positivos" in thresholds.detail


def test_thresholds_declarado_sin_gold_advierte(corrida) -> None:
    (corrida / "03_screening" / "metrics.json").unlink()
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "recall_target 0.95 no medible (sin gold)" in thresholds.detail


def test_thresholds_clave_desconocida_advierte(corrida) -> None:
    editar_protocolo(
        corrida, lambda p: p.update(thresholds={"recall_target": 0.95, "kapa_min": 0.6})
    )
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "clave(s) desconocida(s) en thresholds: `kapa_min`" in thresholds.detail


def test_thresholds_sin_umbrales_advierte(corrida) -> None:
    editar_protocolo(corrida, lambda p: p.update(thresholds={}))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "ningún umbral declarado" in thresholds.detail


# ── grounding (D8) ─────────────────────────────────────────────────────


def _citas(*checks: dict, flagged: bool | None = None):
    def _editar(verification: dict) -> None:
        verification["checks"] = list(checks)
        verification["hallucination_flagged"] = (
            any(not c["exists_in_corpus"] or not c["grounded"] for c in checks)
            if flagged is None
            else flagged
        )

    return _editar


def _cita(cited_id: str, *, existe: bool = True, fundamentada: bool = True) -> dict:
    return {
        "claim": f"Afirmación que cita [{cited_id}].",
        "cited_id": cited_id,
        "exists_in_corpus": existe,
        "grounded": fundamentada,
        "note": None if existe else "id citado no está en el corpus",
    }


VERIFICATION = "06_synthesis/verification.json"


def test_grounding_sin_citas_con_incluidos_advierte(corrida) -> None:
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "WARN"
    assert "la síntesis no cita ningún estudio (3 incluidos)" in grounding.detail


def test_grounding_citas_fundamentadas_pasa(corrida) -> None:
    edit_json(corrida / VERIFICATION, _citas(_cita("10.1000/llm-1"), _cita("10.1000/asreview")))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "PASS"
    assert grounding.detail == "2 citas, ninguna marcada; 2/3 incluidos citados."


def test_grounding_marca_sin_adjudicar_falla(corrida) -> None:
    # `[2019]` es el falso positivo conocido del verificador (C2): sin
    # adjudicación humana, la corrida no es publicable (D8).
    edit_json(corrida / VERIFICATION, _citas(_cita("10.1000/llm-1"), _cita("2019", existe=False)))
    report = auditar(corrida)
    grounding = fila(report, "grounding")
    assert grounding.status == "FAIL"
    assert "1 cita(s) marcada(s) sin adjudicar por un humano (D8): índices [1]" in grounding.detail
    assert not report.publishable


def test_grounding_adjudicacion_de_actor_no_humano_falla(corrida) -> None:
    edit_json(corrida / VERIFICATION, _citas(_cita("2019", existe=False)))

    def _adjudicar(entries: list[dict]) -> list[dict]:
        *previas, reporte = entries
        reporte["detail"] = {"decision_sha256": "d" * 64, "request_sha256": "r" * 64}
        review = {
            **reporte,
            "actor": "agent:verificador",
            "action": "flag_review",
            "target": "flag:0",
            "detail": {
                "cited_id": "2019",
                "verdict": "false_positive",
                "reason": "es un año",
                "decision_sha256": "d" * 64,
            },
        }
        return [*previas, review, reporte]

    edit_ledger(corrida, _adjudicar)
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "adjudicación de un actor no humano: agent:verificador" in grounding.detail


def test_grounding_bandera_inconsistente_falla(corrida) -> None:
    edit_json(corrida / VERIFICATION, _citas(_cita("2019", existe=False), flagged=False))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "bandera inconsistente: hallucination_flagged=False" in grounding.detail


def test_grounding_existe_en_el_corpus_un_id_que_no_esta_incluido_falla(corrida) -> None:
    edit_json(corrida / VERIFICATION, _citas(_cita("10.9999/fantasma")))
    grounding = fila(auditar(corrida), "grounding")
    assert grounding.status == "FAIL"
    assert "exists_in_corpus: true para ids que no están entre los incluidos: 0" in (
        grounding.detail
    )


# ── search_window y registration ──────────────────────────────────────


def test_search_window_fecha_tecleada_solo_advierte(tmp_path) -> None:
    # Síntoma C3: el auditor anterior daba PASS porque el humano tecleó una fecha.
    # Sin 01_search/log.json (corrida v0.7) nadie más la registró.
    window = fila(auditar(write_legacy_v07(tmp_path)), "search_window")
    assert window.status == "WARN"
    assert "fecha tecleada (`executed: 2026-09-20`), no registrada por el motor" in window.detail


def test_search_window_sin_from_to_advierte(corrida) -> None:
    editar_protocolo(corrida, lambda p: p.update(search_window={}))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "ventana sin `from` ni `to`" in window.detail


def test_registration_sin_registro_advierte(corrida) -> None:
    editar_protocolo(corrida, lambda p: p.update(registration={}))
    registration = fila(auditar(corrida), "registration")
    assert registration.status == "WARN"
    assert "Sin registro" in registration.detail
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_calidad.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'potencia_minima' from 'revisia.audit.checks_quality'`.

- [ ] **Step 3: `checks_quality.py`**

Sustituir el contenido completo de `revisia/audit/checks_quality.py` por:

```python
"""Checks de calidad del cribado y de la síntesis: ``gold``, ``thresholds``, ``grounding``.

``thresholds`` aplica D7: los umbrales del protocolo según lo que mide cada
métrica. Un recall bajo ``recall_target`` significa estudios relevantes
perdidos y es FAIL mientras quede alguna exclusión IA de T/A sin etiqueta
humana; un κ bajo ``kappa_min`` (acuerdo humano-IA) es una desviación a
declarar (WARN). El caso de la auditoría 2026-09-03 (A11: κ=0.0 con PASS)
deja de pasar en limpio. ``grounding`` aplica D8: una cita marcada por el
verificador sin adjudicar por un humano es FAIL.
"""

from __future__ import annotations

import math

from revisia.audit.artifacts import AuditContext
from revisia.audit.checks_flow import TA, included_ids
from revisia.audit.model import Verdict
from revisia.config import KNOWN_THRESHOLDS
from revisia.metrics import ScreeningMetrics, fmt_metric, wilson_interval
from revisia.provenance.ledger import HUMAN_ACTOR_PREFIX

METRICS = "03_screening/metrics.json"
VERIFICATION = "06_synthesis/verification.json"


def _matrix_note(ctx: AuditContext) -> str:
    """Por qué ``metrics.json`` no valida (el FAIL lo da ``schemas``)."""
    raw = ctx.art.json(METRICS)
    if not raw.ok or not isinstance(raw.value, dict):
        return "metrics.json ilegible (ver `schemas`)."
    keys = ("tp", "fp", "fn", "tn")
    if all(k in raw.value for k in keys):
        return (
            f"Métricas vs gold humano: recall={raw.value.get('recall')} · metrics.json con "
            "matriz de confusión ilegible (tp/fp/fn/tn con algún valor no numérico; ver "
            "`schemas`)."
        )
    return "metrics.json sin matriz de confusión: métricas no verificables (ver `schemas`)."


def check_gold(ctx: AuditContext) -> Verdict:
    """trAIce M9/R2: métricas del cribado IA contra un gold humano, informativas."""
    loaded = ctx.art.artifact(METRICS)
    if not loaded.present:
        return "WARN", (
            "Sin gold standard: no hay recall/kappa del cribado IA vs humano. "
            "Crea gold.yml (revisia gold-template) antes de publicar."
        )
    if not loaded.ok:
        return "WARN", _matrix_note(ctx)
    m: ScreeningMetrics = loaded.value
    gold_una_clase = m.tp + m.fn == 0 or m.tn + m.fp == 0
    ia_una_clase = m.tp + m.fp == 0 or m.fn + m.tn == 0
    if m.cohen_kappa is None or m.mcc is None or gold_una_clase or ia_una_clase:
        return "WARN", (
            f"Métricas vs gold humano: recall={fmt_metric(m.recall)} · kappa/mcc no calculable: "
            "métricas indefinidas o no informativas (el gold o la IA asignaron una sola clase). "
            "Amplía el gold con registros relevantes e irrelevantes."
        )
    return "PASS", (
        f"Métricas vs gold humano (n={m.n}): recall={fmt_metric(m.recall)} · "
        f"kappa={fmt_metric(m.cohen_kappa)} · MCC={fmt_metric(m.mcc)} (accuracy omitida a "
        "propósito)."
    )


def potencia_minima(target: float) -> int | None:
    """Positivos mínimos del gold para que un solo fallo no baje del umbral.

    ⌈1/(1−umbral)⌉: 20 para 0,95; 10 para 0,90. ``None`` con umbral ≥ 1
    (ningún gold tiene potencia). El redondeo evita que el error de coma
    flotante convierta 5,000000000000001 en 6.
    """
    if target >= 1:
        return None
    return math.ceil(round(1 / (1 - target), 9))


def ai_exclusions_without_label(ctx: AuditContext) -> int | None:
    """Exclusiones IA de T/A sin etiqueta humana (``None`` si no se leen las decisiones)."""
    loaded = ctx.art.artifact(TA)
    if not loaded.ok:
        return None
    return sum(1 for d in loaded.value if d.ensemble_label == "exclude" and d.human_label is None)


def _ic(k: int, n: int) -> str:
    low, high = wilson_interval(k, n) or (0.0, 1.0)
    return f"[IC95 {low:.2f}–{high:.2f}]"


def check_thresholds(ctx: AuditContext) -> Verdict:
    """trAIce M9/R2 / PRISMA 8, 24c: umbrales del protocolo según lo que miden (D7)."""
    if ctx.protocol is None:
        return "WARN", "umbrales no verificables: sin protocolo legible en el manifiesto."
    thresholds = ctx.protocol.thresholds
    fails: list[str] = []
    warns: list[str] = []
    passes: list[str] = []

    unknown = sorted(set(thresholds) - KNOWN_THRESHOLDS)
    if unknown:
        warns.append(
            "clave(s) desconocida(s) en thresholds: "
            + ", ".join(f"`{k}`" for k in unknown)
            + f" (¿errata? se entienden {', '.join(sorted(KNOWN_THRESHOLDS))})"
        )
    recall_target = thresholds.get("recall_target")
    kappa_min = thresholds.get("kappa_min")
    if recall_target is None and kappa_min is None:
        warns.append("ningún umbral declarado: declara al menos `recall_target` en el protocolo")

    loaded = ctx.art.artifact(METRICS)
    m: ScreeningMetrics | None = loaded.value if loaded.ok else None
    why = "sin gold" if not loaded.present else "metrics.json no válido"

    if recall_target is not None:
        if m is None or m.recall is None:
            motivo = why if m is None else "el gold no tiene positivos"
            warns.append(f"recall_target {recall_target:.2f} no medible ({motivo})")
        else:
            positives = m.tp + m.fn
            recall = f"recall {m.recall:.2f} {_ic(m.tp, positives)}"
            if m.recall < recall_target:
                pending = ai_exclusions_without_label(ctx)
                quedan = "un número no verificable de" if pending is None else str(pending)
                fails.append(
                    f"{recall} < {recall_target:.2f} con {positives} positivos y {quedan} "
                    "exclusiones IA de T/A sin etiqueta humana: etiquétalas en "
                    "`screening_ta/decision.yml` y reanuda (D7, D14)"
                )
            else:
                minimo = potencia_minima(recall_target)
                if minimo is None or positives < minimo:
                    warns.append(
                        f"{recall} ≥ {recall_target:.2f} con solo {positives} positivos en el "
                        f"gold: con menos de {minimo or '∞'} un solo fallo ya baja del umbral "
                        "(gold sin potencia)"
                    )
                else:
                    passes.append(f"{recall} ≥ {recall_target:.2f} con {positives} positivos")

    if kappa_min is not None:
        if m is None or m.cohen_kappa is None:
            warns.append(
                f"kappa_min {kappa_min:.2f} no medible ({why if m is None else 'κ indefinido'})"
            )
        elif m.cohen_kappa < kappa_min:
            warns.append(
                f"κ {m.cohen_kappa:.2f} < {kappa_min:.2f}: desviación del protocolo, decláralo "
                "(PRISMA 24c)"
            )
        else:
            passes.append(f"κ {m.cohen_kappa:.2f} ≥ {kappa_min:.2f}")

    if fails:
        return "FAIL", "; ".join(fails + warns + passes) + "."
    if warns:
        return "WARN", "; ".join(warns + passes) + "."
    return "PASS", "; ".join(passes) + "."


def _adjudications(ctx: AuditContext) -> dict[int, str]:
    """Citas adjudicadas como falso positivo en la decisión efectiva de ``reporte``.

    ``{índice: actor}`` de las entradas ``flag_review`` con el mismo
    ``decision_sha256`` que el ``approve`` efectivo, ``verdict:
    false_positive`` y razón no vacía (spec §4.3). Sin ``decision_sha256``
    (ledger anterior a la Ola 1) no hay adjudicación posible.
    """
    gate = ctx.gates.get("reporte")
    if gate is None or gate.action != "approve" or gate.decision_sha256 is None:
        return {}
    result: dict[int, str] = {}
    for entry in ctx.ledger.decisions:
        if entry.stage != "reporte" or entry.action != "flag_review":
            continue
        detail = entry.detail
        if detail.get("decision_sha256") != gate.decision_sha256:
            continue
        if detail.get("verdict") != "false_positive" or not str(detail.get("reason") or "").strip():
            continue
        target = entry.target or ""
        if target.startswith("flag:") and target[5:].isdigit():
            result[int(target[5:])] = entry.actor
    return result


def check_grounding(ctx: AuditContext) -> Verdict:
    """trAIce M8/M9: citas de la síntesis verificadas; las marcadas, adjudicadas (D8)."""
    loaded = ctx.art.artifact(VERIFICATION)
    if not loaded.ok:
        estado = "ausente" if not loaded.present else "inválido"
        return "N/A", (f"no aplica: {VERIFICATION} {estado} (ver `stage_artifacts` y `schemas`).")
    report = loaded.value
    checks = report.checks
    ids = included_ids(ctx)
    fails: list[str] = []

    recomputed = any(not c.exists_in_corpus or not c.grounded for c in checks)
    if report.hallucination_flagged != recomputed:
        fails.append(
            f"bandera inconsistente: hallucination_flagged={report.hallucination_flagged} y "
            f"los checks dan {recomputed} (recompute_flag)"
        )
    if ids is not None:
        phantom = [
            f"{i} (`{c.cited_id}`)"
            for i, c in enumerate(checks)
            if c.exists_in_corpus and c.cited_id not in ids
        ]
        if phantom:
            fails.append(
                "exists_in_corpus: true para ids que no están entre los incluidos: "
                + ", ".join(phantom)
            )

    flagged = [i for i, c in enumerate(checks) if not c.exists_in_corpus or not c.grounded]
    adjudicated = _adjudications(ctx)
    missing = [i for i in flagged if i not in adjudicated]
    non_human = sorted(
        {adjudicated[i] for i in flagged if i in adjudicated}
        - {a for a in adjudicated.values() if a.startswith(HUMAN_ACTOR_PREFIX)}
    )
    if missing:
        fails.append(
            f"{len(missing)} cita(s) marcada(s) sin adjudicar por un humano (D8): índices "
            f"{missing}; adjudícalas en `reporte/decision.yml` (`flags`) o rechaza el reporte"
        )
    if non_human:
        fails.append(f"adjudicación de un actor no humano: {', '.join(non_human)}")

    if fails:
        return "FAIL", "; ".join(fails) + "."
    if flagged:
        actors = sorted({adjudicated[i] for i in flagged})
        return "WARN", (
            f"{len(flagged)} citas marcadas, adjudicadas como falsos positivos por "
            f"{', '.join(actors)}: decláralo."
        )
    n_included = len(ids) if ids is not None else 0
    if not checks:
        if n_included:
            return "WARN", (
                f"la síntesis no cita ningún estudio ({n_included} incluidos): no hay citas que "
                "verificar."
            )
        return "PASS", "sin incluidos ni citas que verificar."
    cited = len({c.cited_id for c in checks if ids is not None and c.cited_id in ids})
    return "PASS", f"{len(checks)} citas, ninguna marcada; {cited}/{n_included} incluidos citados."
```

- [ ] **Step 4: `check_search_window`**

Sustituir el contenido completo de `revisia/audit/checks_search.py` por:

```python
"""Checks de búsqueda y registro: ``search_window``, ``registration``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict

_NA_PROTOCOLO = "no aplica: sin protocolo legible en el manifiesto (ver `manifest`)."


def _protocol_section(ctx: AuditContext, key: str) -> dict | None:
    if ctx.manifest_dict is None:
        return None
    protocol = ctx.manifest_dict.get("protocol")
    if not isinstance(protocol, dict):
        return {}
    section = protocol.get(key)
    return section if isinstance(section, dict) else {}


def check_search_window(ctx: AuditContext) -> Verdict:
    """PRISMA-S 9/13: ventana de la búsqueda declarada y fecha de ejecución registrada.

    Sin ``01_search/log.json`` la fecha la tecleó un humano en el protocolo: el
    auditor anterior daba PASS por eso (auditoría 2026-09-03, C3/M12). Desde
    la Ola 1 la registra el motor.
    """
    window = _protocol_section(ctx, "search_window")
    if window is None:
        return "N/A", _NA_PROTOCOLO
    warns: list[str] = []
    missing = [k for k in ("from", "to") if not window.get(k)]
    if missing:
        warns.append(f"ventana sin `{'` ni `'.join(missing)}` (PRISMA-S 9)")
    executed = window.get("executed")
    if executed:
        warns.append(
            f"fecha tecleada (`executed: {executed}`), no registrada por el motor "
            "(sin 01_search/log.json)"
        )
    else:
        warns.append("sin fecha de ejecución: ni `executed` ni 01_search/log.json")
    return "WARN", "; ".join(warns) + "."


def check_registration(ctx: AuditContext) -> Verdict:
    """PRISMA 24a: registro del protocolo."""
    registration = _protocol_section(ctx, "registration")
    if registration is None:
        return "N/A", _NA_PROTOCOLO
    declared = {k: v for k, v in registration.items() if v}
    if declared:
        return "PASS", (
            "Registro declarado: " + ", ".join(f"{k}={v}" for k, v in declared.items()) + "."
        )
    return "WARN", "Sin registro (PROSPERO/OSF): preregistra el protocolo antes de publicar."
```

- [ ] **Step 5: Registrar `thresholds`**

En `revisia/audit/__init__.py`, sustituir

```python
    CheckSpec("deliverable", "PRISMA 16/16b/17/18/27", "reporte", checks_flow.check_deliverable),
    CheckSpec("gold", "trAIce M9/R2", "screening_ta", checks_quality.check_gold),
    CheckSpec("grounding", "trAIce M8/M9", "sintesis", checks_quality.check_grounding),
    CheckSpec("search_window", "PRISMA-S 9/13", "busqueda", checks_search.check_search_window),
```

por

```python
    CheckSpec("deliverable", "PRISMA 16/16b/17/18/27", "reporte", checks_flow.check_deliverable),
    CheckSpec("gold", "trAIce M9/R2", "screening_ta", checks_quality.check_gold),
    CheckSpec(
        "thresholds",
        "trAIce M9/R2 / PRISMA 8, 24c",
        "screening_ta",
        checks_quality.check_thresholds,
    ),
    CheckSpec("grounding", "trAIce M8/M9", "sintesis", checks_quality.check_grounding),
    CheckSpec("search_window", "PRISMA-S 9/13", "busqueda", checks_search.check_search_window),
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_calidad.py tests/test_audit.py -v`
Expected: PASS (18 nuevos; los seis de `gold` de `test_audit.py` siguen en verde).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, 505 recogidos.

- [ ] **Step 7: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 8: Commit**

```bash
git add revisia/audit tests/test_audit_calidad.py
git commit -m "feat(audit): umbrales según lo que miden (D7), citas marcadas sin adjudicar (D8) y ventana de búsqueda" -m "thresholds lee recall_target y kappa_min (A11): un recall bajo el umbral con exclusiones IA sin revisar es FAIL; un κ bajo es una desviación a declarar (WARN); un recall que alcanza el umbral con un gold sin potencia también es WARN, y el detalle da el intervalo de Wilson. grounding da FAIL con una cita marcada sin adjudicar por un humano (M5 en el auditor). search_window ya no da PASS por una fecha tecleada. Spec 2026-10-04 §3 y §9.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: La reconstrucción C3 no es publicable, por siete vías (cierre de la fase 1)

**Files:**
- Modify: `tests/audit_fixtures.py` (añade `write_c3_reconstruction`)
- Test: `tests/test_audit_c3.py` (nuevo)

**Interfaces:**
- Consumes: `meta_analyze`, `EffectInput`, `RunMeta`, `sha256_text`; `comprimir_llamadas`, `edit_json`, `edit_ledger`, `edit_yaml` (Tarea 3).
- Produces: `write_c3_reconstruction(tmp_path: Path, provenance: str = "pipeline") -> Path`, fiel a la evidencia de C3 (informe de auditoría §3): 140 llamadas `agent` entre `08:07:47.515524` y `08:07:47.516860` (94 de Opus, 46 de Sonnet con sus hashes de respuesta dentro de los de Opus); ledger con `propose`/`exclude`/`verify` a horas redondas una semana antes; `metrics.json` = `{n: 47, recall: 1.0, mcc: 0.71, cohen_kappa: 0.75}` sin matriz; solo `03_screening/`, `06_synthesis/`, `08_meta/` y `deliverable/`; `identified_by_source` 40/40/40 con 28 identificados y 0 duplicados; `excluded_human: 3`.

- [ ] **Step 1: Test que falla — crear `tests/test_audit_c3.py`**

```python
"""La reconstrucción C3 deja de ser publicable, y por más de una vía.

Auditoría 2026-09-03, C3: la corrida fundacional era una reconstrucción y el
auditor la declaraba "APTA". La Ola 0 añadió ``provenance: pipeline``, que se
falsifica con una línea; la Ola 1 exige que la corrida no sea publicable aunque
la procedencia esté falsificada, por al menos siete checks independientes, y
que cada síntoma, aplicado solo a una corrida coherente, baste (spec
2026-10-04 §9.4 y §11).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from audit_fixtures import (
    auditar,
    comprimir_llamadas,
    edit_json,
    edit_ledger,
    edit_yaml,
    fila,
    write_c3_reconstruction,
)

VIAS_C3 = {"schemas", "ledger", "timing", "hitl", "stage_artifacts", "arithmetic", "final_gate"}


def test_audit_c3_reconstruccion_no_es_publicable_por_varias_vias(tmp_path) -> None:
    report = auditar(write_c3_reconstruction(tmp_path, provenance="pipeline"))
    fails = {c.check_id for c in report.checks if c.status == "FAIL"}
    assert fails >= VIAS_C3
    assert len(fails) >= 7
    assert fila(report, "provenance").status == "PASS"  # la marca falsificada no basta
    assert not report.publishable


def test_audit_c3_con_su_procedencia_real_tambien_falla_provenance(tmp_path) -> None:
    report = auditar(write_c3_reconstruction(tmp_path, provenance="reconstruction"))
    assert fila(report, "provenance").status == "FAIL"
    assert {c.check_id for c in report.checks if c.status == "FAIL"} >= VIAS_C3


def _accion_desconocida(run: Path) -> None:
    edit_ledger(
        run,
        lambda e: [{**e[0], "action": "propose", "actor": "agent:opus+sonnet"}, *e],
    )


def _metricas_sin_matriz(run: Path) -> None:
    edit_json(
        run / "03_screening" / "metrics.json",
        lambda _m: {"n": 47, "recall": 1.0, "mcc": 0.71, "cohen_kappa": 0.75},
    )


def _sin_04_fulltext(run: Path) -> None:
    shutil.rmtree(run / "04_fulltext")


def _excluded_human_3(run: Path) -> None:
    edit_json(run / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=3))


def _ledger_una_semana_antes(run: Path) -> None:
    def _editar(entries: list[dict]) -> None:
        for entry in entries:
            marca = datetime.fromisoformat(entry["timestamp_utc"]) - timedelta(days=7)
            entry["timestamp_utc"] = marca.isoformat()

    edit_ledger(run, _editar)


def _fuentes_40_40_40(run: Path) -> None:
    fuentes = {"OpenAlex": 40, "Crossref": 40, "Europe PMC": 40}
    edit_yaml(run / "manifest.yml", lambda m: m["counts"].update(identified_by_source=fuentes))


SINTOMAS: list = [
    pytest.param(_accion_desconocida, "ledger", "FAIL", id="accion-desconocida"),
    pytest.param(_metricas_sin_matriz, "schemas", "FAIL", id="metricas-sin-matriz"),
    pytest.param(_sin_04_fulltext, "stage_artifacts", "FAIL", id="falta-04-fulltext"),
    pytest.param(_excluded_human_3, "hitl", "FAIL", id="excluded-human-3"),
    pytest.param(_ledger_una_semana_antes, "timing", "FAIL", id="ledger-una-semana-antes"),
    pytest.param(_fuentes_40_40_40, "arithmetic", "FAIL", id="identified-by-source-40-40-40"),
    # Una heurística temporal nunca basta sola: 1,3 ms es WARN.
    pytest.param(comprimir_llamadas, "timing", "WARN", id="llamadas-en-1-3-ms-solo-advierte"),
]


@pytest.mark.parametrize(("sintoma", "check_id", "esperado"), SINTOMAS)
def test_audit_c3_cada_sintoma_basta_solo(
    corrida, sintoma: Callable[[Path], None], check_id: str, esperado: str
) -> None:
    assert auditar(corrida).publishable  # la corrida coherente de partida
    sintoma(corrida)
    report = auditar(corrida)
    assert fila(report, check_id).status == esperado
    assert report.publishable is (esperado != "FAIL")
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_c3.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'write_c3_reconstruction' from 'audit_fixtures'`.

- [ ] **Step 3: `write_c3_reconstruction` en `tests/audit_fixtures.py`**

En `tests/audit_fixtures.py`, sustituir

```python
from revisia.exclusions import compute_exclusion_breakdown
from revisia.exports import PrismaCounts, render_prisma2020_flow_csv
from revisia.metrics import ScreeningMetrics, kappa_from_matrix, mcc, wmcc
from revisia.provenance.ledger import DecisionEntry
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.artifacts import JOURNAL_PATHS
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.rob import RoBAssessment
```

por

```python
from revisia.exclusions import compute_exclusion_breakdown
from revisia.exports import PrismaCounts, render_prisma2020_flow_csv
from revisia.meta_analysis import meta_analyze
from revisia.metrics import ScreeningMetrics, kappa_from_matrix, mcc, wmcc
from revisia.provenance.ledger import DecisionEntry
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.schemas.artifacts import JOURNAL_PATHS
from revisia.schemas.effects import EffectInput
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.rob import RoBAssessment
```

En `tests/audit_fixtures.py`, sustituir

```python
    )
    return run
```

por

```python
    )
    return run


# ── Reconstrucción C3 (auditoría 2026-09-03 §3) ─────────────────────────


def _c3_llamadas() -> list[dict]:
    """140 llamadas `agent` en 1,3 ms: 94 de Opus y 46 de Sonnet, cuyos hashes de
    respuesta son un subconjunto exacto de los de Opus."""
    inicio = datetime(2026, 7, 6, 8, 7, 47, 515524, tzinfo=UTC)
    paso = timedelta(microseconds=1336) / 139
    calls = []
    for i in range(140):
        opus = i < 94
        respuesta = i if opus else (i - 94) * 2  # Sonnet repite respuestas de Opus
        calls.append(
            RunMeta(
                provider="agent",
                model="opus" if opus else "sonnet",
                temperature=0.0,
                prompt_sha256=sha256_text(f"c3 prompt {i}"),
                response_sha256=sha256_text(f"c3 respuesta {respuesta}"),
                timestamp_utc=(inicio + i * paso).isoformat(),
                deterministic=False,
            ).model_dump()
        )
    return calls


def write_c3_reconstruction(tmp_path: Path, provenance: str = "pipeline") -> Path:
    """La reconstrucción de la corrida fundacional, fiel a la evidencia de C3.

    Con ``provenance="pipeline"`` (por defecto) se falsifica la única marca que
    la Ola 0 sabía comprobar: el resto de checks tiene que delatarla por sí
    solo. Evidencia reproducida (``docs/auditoria/2026-09-03-auditoria-completa.md``
    §3, C3):

    - 140 ``llm_calls`` entre ``08:07:47.515524`` y ``08:07:47.516860``; los 46
      hashes de respuesta de Sonnet son un subconjunto de los 94 de Opus.
    - Ledger con ``propose``/``exclude``/``verify`` (que ``review_gate`` nunca
      emite) a horas redondas, una semana antes de la corrida.
    - ``metrics.json`` = ``{n: 47, recall: 1.0, mcc: 0.71, kappa: 0.75}`` sin
      matriz (con FN=0, κ > MCC es imposible); ``excluded_human: 3``.
    - Solo ``03_screening/``, ``06_synthesis/``, ``08_meta/`` y ``deliverable/``;
      ``identified_by_source`` 40/40/40 con 28 identificados (lo que declara
      su ``metodologia.md``) y 0 duplicados.
    """
    run = tmp_path / "runs" / "prisma-ia-origen-20260706-080747"
    for sub in ("03_screening", "06_synthesis", "08_meta", "deliverable"):
        (run / sub).mkdir(parents=True)

    meta = meta_analyze(
        [
            EffectInput(study_id="Li:ChatGPT v4.0:BB2016", yi=2.52306, vi=0.14403),
            EffectInput(study_id="Li:ChatGPT v4.0:BB2016 (dup)", yi=2.52306, vi=0.14403),
            EffectInput(study_id="Li:Claude:BB2016", yi=3.04452, vi=0.69841),
        ],
        "precomputed",
    ).model_dump()
    manifest = {
        "slug": "prisma-ia-origen",
        "created_utc": "2026-07-06T08:07:49.869602+00:00",
        "timestamp": "20260706-080747",
        "provenance": provenance,
        "engine": "revisia 0.4.0",
        "protocol": {
            "question": {"text": "¿Cómo se aplica la IA a las etapas de la metodología PRISMA?"},
            "search_window": {"from": "2019-01-01", "to": "2026-06-29", "executed": "2026-06-29"},
            "registration": {"prospero": "", "osf": ""},
        },
        "counts": {
            "identified": 28,
            "identified_by_source": {"OpenAlex": 40, "Crossref": 40, "Europe PMC": 40},
            "duplicates_removed": 0,
            "removed_automation": 0,
            "removed_other": 0,
            "screened": 120,
            "excluded_ta": 92,
            "excluded_ta_human": 0,
            "excluded_ta_ai": 92,
            "fulltext_assessed": 28,
            "fulltext_abstract_only": 10,
            "excluded_ft": 3,
            "ft_exclusion_reasons": {
                "RS de dominio que solo USA una herramienta de IA": 2,
                "Registro sin texto ni abstract verificable": 1,
            },
            "included": 25,
        },
        "llm_calls": _c3_llamadas(),
        "models_used": ["agent:opus", "agent:sonnet"],
        "deterministic_token_level": False,
        "meta_analysis": meta,
    }
    (run / "manifest.yml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    ledger = [
        ("screening_ta", "agent:opus+sonnet", "A1", "propose", None, "00:00"),
        ("screening_ta", "human:jhon", "A1", "approve", None, "00:05"),
        ("screening_ft", "human:jhon", "A0", "exclude", "3 RS de dominio / sin texto", "00:10"),
        ("extraccion", "human:jhon", "A0", "verify", None, "00:20"),
        ("rob", "human:jhon", "A0", "verify", None, "00:30"),
        ("reporte", "human:jhon", "A1", "approve", None, "00:40"),
    ]
    lines = []
    for stage, actor, autonomy, action, target, hora in ledger:
        entry = {"stage": stage, "actor": actor, "autonomy": autonomy, "action": action}
        if target is not None:
            entry["target"] = target
        entry["timestamp_utc"] = f"2026-06-29T{hora}:00+00:00"
        lines.append(json.dumps(entry, ensure_ascii=False) + "\n")
    (run / "decisions_ledger.jsonl").write_text("".join(lines), encoding="utf-8")

    def _json(rel: str, data: object) -> None:
        (run / rel).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    _json(
        "03_screening/metrics.json",
        {
            "n": 47,
            "recall": 1.0,
            "lost_evidence": 0.0,
            "cohen_kappa": 0.75,
            "mcc": 0.71,
            "wmcc": 0.83,
        },
    )
    _json(
        "03_screening/exclusions.json",
        {
            "total_excluded": 95,
            "excluded_ai": 92,
            "excluded_human": 3,
            "overridden_to_include": 0,
            "overridden_to_exclude": 3,
        },
    )
    _json(
        "06_synthesis/verification.json",
        {"hallucination_flagged": False, "n_claims": 21, "n_grounded": 21},
    )
    _json("08_meta/meta_analysis.json", meta)
    for name in (
        "checklist_2020.md",
        "checklist_abstracts.md",
        "checklist_s.md",
        "checklist_traice.md",
        "documento.md",
        "meta_analisis.md",
        "metodologia.md",
        "prisma_flow.md",
        "referencias.bib",
        "risk_of_bias.md",
        "tabla_extraccion.md",
    ):
        (run / "deliverable" / name).write_text(f"# {name}\n", encoding="utf-8")
    return run
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_c3.py -v`
Expected: PASS, 9 tests: la reconstrucción con la procedencia falsificada falla `schemas`, `ledger`, `timing`, `hitl`, `stage_artifacts`, `arithmetic` y `final_gate` (además de `exclusions` y `deliverable`); cada síntoma basta solo; "1,3 ms" solo da WARN.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, **514 recogidos** (364 + 150 de la fase 1).

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 6: Commit**

```bash
git add tests/audit_fixtures.py tests/test_audit_c3.py
git commit -m "test(audit): la reconstrucción C3 no es publicable, por siete vías" -m "write_c3_reconstruction reproduce la evidencia de C3 (auditoría 2026-09-03 §3) con la procedencia falsificada a pipeline: la marca de la Ola 0 ya no basta. test_audit_c3_reconstruccion_no_es_publicable_por_varias_vias exige FAIL en schemas, ledger, timing, hitl, stage_artifacts, arithmetic y final_gate; test_audit_c3_cada_sintoma_basta_solo aplica cada síntoma a una corrida coherente y comprueba que basta (1,3 ms solo es WARN). Spec 2026-10-04 §9.4." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Verificación de la fase 1 (3.11 y 3.12, lint, lock)**

Con venv desechable (`requires-python >= 3.13` impide `uv run --python 3.11`; M24 es Ola 2):

```bash
TMP="$(mktemp -d)"
for PY in 3.11 3.12; do
  uv venv -q --python "$PY" "$TMP/venv$PY"
  uv pip install -q --python "$TMP/venv$PY" pydantic pyyaml python-dotenv markdown httpx nh3 pytest
  PYTHONPATH=. "$TMP/venv$PY/Scripts/python" -m pytest -p no:cacheprovider -q
done
```

Expected: PASS en ambas versiones (514 recogidos).

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`
Expected: limpio.

La fase 1 termina aquí. **No se abre PR todavía** (spec §9: una sola PR al terminar la fase 2). La rama queda local en el worktree hasta la Tarea 11.

---

## Fase 2 · sobre PR-D (worktree `C:\revisia-wt\e`, rama `feat/ola1-auditor` rebasada)

Empieza cuando PR-D (`feat/ola1-hitl-por-registro`) está integrada en su rama, con su suite en verde. El plan B la deja en **499 tests** (`N_D`); si el número real es otro, el controlador lo anota y los conteos de esta fase se desplazan en la misma cantidad.

### Task 11: Rebase sobre PR-D y la corrida real con `correr_hasta`

**Files:**
- Rebase: `feat/ola1-auditor` (Tareas 1-10) sobre `feat/ola1-hitl-por-registro`
- Modify: `tests/conftest.py` (la corrida avanza con `correr_hasta`; fixture `corrida_en_pausa_ft`), `tests/audit_fixtures.py` (sale `pausar_en_screening_ft`), `tests/test_audit_hitl.py` y `tests/test_audit_infra.py` (usan la pausa real), `tests/test_corrida_auditoria.py` (afirmaciones de la Ola 1 y un test nuevo)

**Interfaces:**
- Consumes (PR-C/PR-D, plan B):
  - `hitl_helpers.correr_hasta(protocol: ReviewProtocol, protocol_dir: Path, ctx: RunContext, *, search_fn: SearchFn, fetch_fn: FetchFn | None = None, etiquetar: Callable[[str, dict], dict | None] | None = None, parar_en: str | None = None, max_vueltas: int = 10) -> PipelineResult` — escribe cada `decision.yml` con `responder_gate` y reabre con `RunContext.open`.
  - La solicitud de `screening_ft` (`review_request.yml`): `records[].record_id`, `records[].proposal`, `must_label` (A0: todos los recuperados).
  - `revisia.schemas.artifacts.RunInfo` (`status`, `stage`), `run.json`, `llm_calls.jsonl`, `00_protocol/` (copia el `gold.yml` del protocolo), `PrismaCounts.fulltext_sought`, `.fulltext_not_retrieved`, `.excluded_ft_human`, `.excluded_ft_ai`.
  - Entradas `label` del ledger con `detail = {from, to, reason, request_sha256, decision_sha256}`.
- Produces (`tests/conftest.py`): `RAZON_EXCLUSION_FT = "fuera de alcance"`; `etiquetar_auditoria(stage: str, solicitud: dict) -> dict | None` (la revisora: aprueba T/A en bloque y etiqueta a texto completo cada registro de `must_label` con la propuesta de la IA); fixture de sesión `protocolo_auditoria` (copia del demo con el gold en `gold.yml`, porque `correr_hasta` no pasa `gold_labels`); `_correr(tmp_path_factory, protocol_dir, *, parar_en: str | None) -> Path`; fixtures `_corrida_en_pausa_ft` (sesión) y `corrida_en_pausa_ft` (copia por test). Sale `DECISION_HUMANA` (las decisiones ya no se escriben antes de correr).

Desde PR-C, `decision.yml` exige el `request_sha256` de su solicitud (D4): la fixture de la fase 1, que escribe las cinco decisiones antes de correr, deja de servir. Ahora la corrida se comporta como en la vida real: pausa, decisión atada a la solicitud y reanudación; el texto completo (A0, D1) queda etiquetado registro a registro (4 etiquetas, 1 exclusión humana). `pausar_en_screening_ft` (que simulaba la pausa borrando artefactos) se sustituye por una corrida detenida de verdad en ese gate.

- [ ] **Step 1: Rebase**

```bash
cd C:/revisia-wt/e
git status --short   # limpio
git rebase --onto feat/ola1-hitl-por-registro feat/ola1-contratos feat/ola1-auditor
uv sync --extra dev
```

Expected: el rebase aplica los commits de las Tareas 1-10 sin conflictos (verificado contra el prototipo del plan B: `revisia/cli.py` y `revisia/metrics.py` se fusionan solos; E solo toca `_cmd_audit` y añade dos funciones en `metrics.py`). Si aparece un conflicto en esos dos ficheros, conserva los dos lados: lo de PR-A..PR-D tal cual y, encima, lo de E (`STATUS_ICON` y el ancho `{check.check_id:<17}` en `_cmd_audit`; `kappa_from_matrix`, `wilson_interval` y `cohen_kappa` delegando).

- [ ] **Step 2: Verificar la rotura esperada**

Run: `uv run pytest -p no:cacheprovider`
Expected: `N_D + 150` recogidos (649 con `N_D = 499`): **502 passed, 2 skipped, 145 errors**. Los 145 son los tests de las Tareas 3-10 que usan la fixture `corrida` (también el de `test_corrida_auditoria.py`), con `DecisionFileError: …/screening_ta/decision.yml: decisión inválida (request_sha256: Field required)` en el setup. Los demás tests (PR-0..PR-D y los de la fase 1 que no usan la corrida) pasan.

- [ ] **Step 3: Test que falla — `tests/test_corrida_auditoria.py` con lo que deja una corrida de la Ola 1**

Sustituir el contenido completo de `tests/test_corrida_auditoria.py` por:

```python
"""Las corridas reales de ``tests/conftest.py`` tienen lo que los tests del auditor necesitan."""

from __future__ import annotations

import json

import yaml

from revisia.schemas.artifacts import RunInfo


def _ledger(run) -> list[dict]:
    lines = (run / "decisions_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line]


def test_corrida_real_tiene_exclusiones_ia_y_gold_de_dos_clases(corrida) -> None:
    manifest = yaml.safe_load((corrida / "manifest.yml").read_text(encoding="utf-8"))
    counts = manifest["counts"]
    assert (counts["identified"], counts["duplicates_removed"], counts["screened"]) == (7, 1, 6)
    assert (counts["excluded_ta"], counts["excluded_ft"], counts["included"]) == (2, 1, 3)
    assert (counts["fulltext_sought"], counts["fulltext_not_retrieved"]) == (4, 0)
    assert (counts["excluded_ft_human"], counts["excluded_ft_ai"]) == (1, 0)
    assert counts["identified_by_source"] == {"OpenAlex": 4, "Crossref": 3}
    # 6 registros × 2 miembros T/A + 4 FT + 3 extracciones + 1 doble + 3 RoB + 1 síntesis.
    llamadas = (corrida / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(manifest["llm_calls"]) == len(llamadas) == 24
    assert {c["provider"] for c in manifest["llm_calls"]} == {"fake"}
    metrics = json.loads((corrida / "03_screening" / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["tp"] > 0 and metrics["tn"] > 0  # gold de dos clases
    ledger = _ledger(corrida)
    assert {e["actor"] for e in ledger} == {"human:revisora"}
    assert [e["stage"] for e in ledger if e["action"] == "approve"] == [
        "screening_ta",
        "screening_ft",
        "extraccion",
        "rob",
        "reporte",
    ]
    # FT en A0: una etiqueta humana por registro recuperado (D1).
    labels = {e["target"]: e["detail"]["to"] for e in ledger if e["action"] == "label"}
    assert labels == {
        "10.1000/llm-1": "include",
        "10.1000/asreview": "include",
        "10.1000/ensemble": "include",
        "10.1000/secundario": "exclude",
    }
    info = RunInfo.model_validate_json((corrida / "run.json").read_text(encoding="utf-8"))
    assert info.status == "completed"
    assert (corrida / "00_protocol" / "gold.yml").exists()


def test_corrida_en_pausa_ft_se_detuvo_en_el_gate_de_texto_completo(corrida_en_pausa_ft) -> None:
    info = RunInfo.model_validate_json(
        (corrida_en_pausa_ft / "run.json").read_text(encoding="utf-8")
    )
    assert (info.status, info.stage) == ("paused", "screening_ft")
    assert (corrida_en_pausa_ft / "screening_ft" / "review_request.yml").exists()
    assert not (corrida_en_pausa_ft / "screening_ft" / "decision.yml").exists()
    assert not (corrida_en_pausa_ft / "manifest.yml").exists()
    assert [e["stage"] for e in _ledger(corrida_en_pausa_ft)] == ["screening_ta"]
```

- [ ] **Step 4: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_corrida_auditoria.py -v`
Expected: ERROR en los dos: `DecisionFileError … request_sha256: Field required` y `fixture 'corrida_en_pausa_ft' not found`.

- [ ] **Step 5: `tests/conftest.py`: la corrida pasa por cada gate**

Sustituir el contenido completo de `tests/conftest.py` por:

```python
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
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fakes import ScriptedProvider, fetch_disponible
from hitl_helpers import correr_hasta

from revisia.config import load_protocol
from revisia.llm.registry import ProviderConfig
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.run_context import RunContext
from revisia.schemas.records import SearchRecord

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"

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


@pytest.fixture(scope="session")
def protocolo_auditoria(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copia del demo con el gold de la corrida de auditoría en ``gold.yml``."""
    destino = tmp_path_factory.mktemp("protocolo") / DEMO.name
    shutil.copytree(DEMO, destino)
    (destino / "gold.yml").write_text(
        yaml.safe_dump({"gold": GOLD_AUDITORIA}, allow_unicode=True), encoding="utf-8"
    )
    return destino


def _correr(
    tmp_path_factory: pytest.TempPathFactory, protocol_dir: Path, *, parar_en: str | None
) -> Path:
    protocol = load_protocol(protocol_dir)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    ctx = RunContext(protocol.slug, tmp_path_factory.mktemp("auditoria"), timestamp)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
        result = correr_hasta(
            protocol,
            protocol_dir,
            ctx,
            search_fn=busqueda_auditoria,
            fetch_fn=fetch_disponible,
            etiquetar=etiquetar_auditoria,
            parar_en=parar_en,
        )
    esperado = "paused" if parar_en else "completed"
    assert result.status == esperado, result.message
    return ctx.run_dir


@pytest.fixture(scope="session")
def _corrida_auditoria(tmp_path_factory: pytest.TempPathFactory, protocolo_auditoria: Path) -> Path:
    """Corrida real completada, generada una vez por sesión."""
    return _correr(tmp_path_factory, protocolo_auditoria, parar_en=None)


@pytest.fixture(scope="session")
def _corrida_en_pausa_ft(
    tmp_path_factory: pytest.TempPathFactory, protocolo_auditoria: Path
) -> Path:
    """La misma corrida, detenida en el gate de texto completo."""
    return _correr(tmp_path_factory, protocolo_auditoria, parar_en="screening_ft")


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
```

- [ ] **Step 6: La pausa real sustituye a `pausar_en_screening_ft`**

En `tests/audit_fixtures.py`, sustituir

```python
import copy
import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
```

por

```python
import copy
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
```

En `tests/audit_fixtures.py`, sustituir

```python
    path = run_dir / "03_screening" / "metrics.json"
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def pausar_en_screening_ft(run_dir: Path) -> None:
    """Deja la corrida como si se hubiera detenido en el gate FT (fase 1 de PR-E).

    Lo que el pipeline aún no habría escrito desaparece: la decisión FT, los
    gates posteriores, las etapas posteriores, el manifiesto y el desglose de
    exclusiones (se escribe tras aprobar el gate FT).
    """
    edit_ledger(run_dir, lambda entries: [e for e in entries if e["stage"] == "screening_ta"])
    (run_dir / "screening_ft" / "decision.yml").unlink()
    for gate in ("extraccion", "rob", "reporte"):
        shutil.rmtree(run_dir / gate)
    for rel in ("05_extraction", "06_synthesis", "07_rob", "08_meta", "deliverable"):
        shutil.rmtree(run_dir / rel)
    (run_dir / "manifest.yml").unlink()
    (run_dir / "03_screening" / "exclusions.json").unlink()


# ── Corrida v0.7 (anterior a la Ola 1) ──────────────────────────────────
```

por

```python
    path = run_dir / "03_screening" / "metrics.json"
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Corrida v0.7 (anterior a la Ola 1) ──────────────────────────────────
```

En `tests/test_audit_hitl.py`, sustituir

```python
from __future__ import annotations

import pytest
from audit_fixtures import auditar, edit_json, edit_ledger, fila, pausar_en_screening_ft

from revisia.schemas.artifacts import GATED_STAGES
```

por

```python
from __future__ import annotations

import json

import pytest
from audit_fixtures import auditar, edit_json, edit_ledger, fila

from revisia.schemas.artifacts import GATED_STAGES
```

En `tests/test_audit_hitl.py`, sustituir

```python
    assert "exclusions.json declara 3 exclusiones humanas" in hitl.detail


def test_hitl_etiquetas_exclude_respaldan_exclusiones_humanas(corrida) -> None:
    def _etiqueta(entries: list[dict]) -> list[dict]:
        ta = entries[0]
        label = {
            **ta,
            "action": "label",
            "target": "10.1000/cocina",
            "detail": {"from": "exclude", "to": "exclude", "reason": "fuera de alcance"},
        }
        return [label, *entries]

    edit_ledger(corrida, _etiqueta)
    edit_json(corrida / "03_screening" / "exclusions.json", lambda e: e.update(excluded_human=1))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "PASS"
    assert "1 etiqueta(s) por registro" in hitl.detail


def test_hitl_actor_desconocido_advierte(corrida) -> None:
```

por

```python
    assert "exclusions.json declara 3 exclusiones humanas" in hitl.detail


def test_hitl_etiquetas_exclude_respaldan_exclusiones_humanas(corrida) -> None:
    # La revisora excluyó "secundario" a texto completo (A0): la exclusión
    # humana de exclusions.json tiene su `label` con `to: exclude` en el ledger.
    exclusions = json.loads((corrida / "03_screening" / "exclusions.json").read_text("utf-8"))
    assert exclusions["excluded_human"] == 1
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "PASS"
    assert "4 etiqueta(s) por registro" in hitl.detail


def test_hitl_actor_desconocido_advierte(corrida) -> None:
```

En `tests/test_audit_hitl.py`, sustituir

```python
# ── Estado de la corrida y gate final ─────────────────────────────────


def test_pausa_en_screening_ft_final_gate_falla_y_hitl_pasa_en_ta(corrida) -> None:
    pausar_en_screening_ft(corrida)
    report = auditar(corrida)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
```

por

```python
# ── Estado de la corrida y gate final ─────────────────────────────────


def test_pausa_en_screening_ft_final_gate_falla_y_hitl_pasa_en_ta(corrida_en_pausa_ft) -> None:
    report = auditar(corrida_en_pausa_ft)
    final_gate = fila(report, "final_gate")
    assert final_gate.status == "FAIL"
```

En `tests/test_audit_hitl.py`, sustituir

```python
        assert fila(report, check_id).status == "N/A"


def test_corrida_interrumpida_sin_solicitud_falla_el_gate_final(corrida) -> None:
    pausar_en_screening_ft(corrida)
    (corrida / "screening_ft" / "review_request.yml").unlink()
    report = auditar(corrida)
    assert report.state is not None and report.state.status == "interrupted"
    final_gate = fila(report, "final_gate")
```

por

```python
        assert fila(report, check_id).status == "N/A"


def test_corrida_interrumpida_sin_solicitud_falla_el_gate_final(corrida_en_pausa_ft) -> None:
    (corrida_en_pausa_ft / "screening_ft" / "review_request.yml").unlink()
    report = auditar(corrida_en_pausa_ft)
    assert report.state is not None and report.state.status == "interrupted"
    final_gate = fila(report, "final_gate")
```

En `tests/test_audit_infra.py`, sustituir

```python
from __future__ import annotations

import pytest
from audit_fixtures import auditar, fila, pausar_en_screening_ft

import revisia.audit as audit_pkg
```

por

```python
from __future__ import annotations

import pytest
from audit_fixtures import auditar, fila

import revisia.audit as audit_pkg
```

En `tests/test_audit_infra.py`, sustituir

```python
    assert (estado.status, estado.pending_stage) == ("interrupted", "extraccion")


def test_pausa_en_screening_ft_deja_na_las_etapas_posteriores(corrida) -> None:
    pausar_en_screening_ft(corrida)
    report = auditar(corrida)
    assert report.state is not None
    assert (report.state.status, report.state.pending_stage) == ("paused", "screening_ft")
```

por

```python
    assert (estado.status, estado.pending_stage) == ("interrupted", "extraccion")


def test_pausa_en_screening_ft_deja_na_las_etapas_posteriores(corrida_en_pausa_ft) -> None:
    report = auditar(corrida_en_pausa_ft)
    assert report.state is not None
    assert (report.state.status, report.state.pending_stage) == ("paused", "screening_ft")
```

En `tests/test_audit_infra.py`, sustituir

```python
    assert "Estado deducido: completada" in markdown


def test_cli_audit_muestra_na(corrida, capsys) -> None:
    from revisia.cli import main

    pausar_en_screening_ft(corrida)
    assert main(["audit", str(corrida)]) == 1
    out = capsys.readouterr().out
    assert "➖ N/A  exclusions" in out
```

por

```python
    assert "Estado deducido: completada" in markdown


def test_cli_audit_muestra_na(corrida_en_pausa_ft, capsys) -> None:
    from revisia.cli import main

    assert main(["audit", str(corrida_en_pausa_ft)]) == 1
    out = capsys.readouterr().out
    assert "➖ N/A  exclusions" in out
```

- [ ] **Step 7: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_corrida_auditoria.py tests/test_audit_hitl.py tests/test_audit_infra.py -v`
Expected: PASS (2 + 15 + 20).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, `N_D + 151` recogidos (650), 2 skipped.

- [ ] **Step 8: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 9: Commit**

```bash
git add tests/conftest.py tests/audit_fixtures.py tests/test_audit_hitl.py tests/test_audit_infra.py tests/test_corrida_auditoria.py
git commit -m "test(audit): la corrida de los tests del auditor pasa por cada gate con correr_hasta" -m "Desde PR-C decision.yml exige el request_sha256 de su solicitud (D4): la corrida de la fase 1, con las decisiones escritas antes de correr, ya no arranca. Ahora pausa en cada gate, la revisora responde a la solicitud vigente (texto completo etiquetado registro a registro, D1) y reanuda. pausar_en_screening_ft deja paso a una corrida detenida de verdad en el gate FT. Spec 2026-10-04 §9.4." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: `protocol_snapshot` (D13), esquemas de los artefactos nuevos y artefactos de la Ola 1 por etapa

**Files:**
- Modify: `revisia/audit/artifacts.py` (adaptadores y modelos de los artefactos nuevos; `jsonl_models`; `decision` con modelo legado; `llm_calls`, `protocol`, `snapshot_protocol`, `protocol_raw`)
- Modify: `revisia/audit/checks_provenance.py` (`LEGACY_RUN`, `check_protocol_snapshot`; `schemas` valida los `.jsonl`)
- Modify: `revisia/audit/checks_flow.py` (`STAGE_ARTIFACTS_OLA1`, diarios condicionales, lista 16b en el entregable)
- Modify: `revisia/audit/checks_search.py` (el protocolo sale de la instantánea), `revisia/audit/__init__.py` (registra `protocol_snapshot` tras `schemas`)
- Test: `tests/test_audit_instantanea.py` (nuevo)

**Interfaces:**
- Consumes (PR-C/PR-D): `revisia.orchestration.snapshot.SNAPSHOT_DIR` (`"00_protocol"`) y `protocol_fingerprint(protocol_dir: str | Path) -> dict[str, str]` (rutas relativas → sha256 del texto con CRLF→LF); `RunInfo.protocol_sha256`, `.slug`; `revisia.schemas.artifacts`: `JOURNAL_PATHS`, `LLMCall`, `JournalEntry`, `SearchLog`, `DedupReport`, `RetrievalOutcome`, `ExcludedReport`, `RunStatus`; `revisia.orchestration.hitl.HumanDecision`; bloques `run`, `autonomy_effective` y `final_gate` del manifiesto; `deliverable/excluidos_texto_completo.md` (16b).
- Produces (`artifacts.py`): `RetrievalRow(RetrievalOutcome)` con `record_id`; `LegacyDecision` (`approved: StrictBool`, `actor`, `reason`; extra permitido); `ManifestRun`; `ManifestFinalGate`; `JSONL_ADAPTERS` (`llm_calls.jsonl` → `LLMCall`, cada diario → `JournalEntry`); siete entradas nuevas en `ARTIFACT_ADAPTERS` (`01_search/records.json`, `01_search/log.json`, `02_dedup/records.json`, `02_dedup/dedup.json`, `03_screening/gold.json`, `04_fulltext/retrieval.json`, `04_fulltext/excluded.json`); `RunArtifacts.jsonl_models(rel) -> Loaded[list[tuple[int, Any]]]`; `RunArtifacts.decision(gate)` valida `HumanDecision` con `run.json` y `LegacyDecision` sin él; `AuditContext.snapshot_protocol -> Loaded`, `.protocol_raw -> dict | None`; `.protocol` y `.llm_calls` prefieren `00_protocol/` y `llm_calls.jsonl`.
- Produces (`checks_provenance.py`): `LEGACY_RUN: str`; `check_protocol_snapshot(ctx) -> Verdict`. Fila `protocol_snapshot` (`PRISMA 24b / trAIce M1`, etapa `protocolo`). (`checks_flow.py`): `STAGE_ARTIFACTS_OLA1: dict[str, tuple[str, ...]]`.

Reglas (spec §9.3, filas 3, 4, 11, 14 y 20; D13): `protocol_snapshot` da **FAIL** sin `run.json`, con el mensaje exacto de D13 ("anterior a la Ola 1 (motor < 0.8): sin instantánea ni decisiones por registro; regenera la corrida con el motor actual."): la corrida se sigue auditando entera como diagnóstico, con las relaciones v0.7. Con `run.json`: FAIL si falta un fichero de la lista de huellas, si su hash no coincide (CRLF→LF, como `protocol_fingerprint`), si `run.json` no registra `protocol.yml`, o si la instantánea no valida o no es el `manifest.protocol`; WARN con ficheros en `00_protocol/` fuera de la lista. `schemas` valida además los artefactos nuevos, cada línea de `llm_calls.jsonl` y de los diarios (FAIL con su número de línea) y los bloques nuevos del manifiesto; el `decision.yml` de una corrida anterior se valida con `LegacyDecision`, porque exigirle `request_sha256` solo repetiría el FAIL de `protocol_snapshot`. Con `run.json`, `stage_artifacts` exige los artefactos de §4.2 de cada etapa alcanzada (`run.json`, `00_protocol/protocol.yml`, `01_search/`, `02_dedup/`, `llm_calls.jsonl`, `retrieval.jsonl`/`.json`, `excluded.json`, diarios) y los diarios que dependen del trabajo hecho (FT con algún recuperado, extracción y RoB con algún incluido, segundo extractor con doble extracción); `deliverable` exige la lista 16b. `registration`, `search_window` y `thresholds` leen el protocolo de la instantánea.

- [ ] **Step 1: Test que falla — crear `tests/test_audit_instantanea.py`**

```python
"""Artefactos de la Ola 1: ``protocol_snapshot`` (D13), esquemas, etapas y lista 16b.

Spec 2026-10-04 §9.3 (filas 3, 4, 11, 14 y 20) y §9.4 (familias
``protocol_snapshot``, ``schemas`` y ``deliverable``, F2).
"""

from __future__ import annotations

import pytest
from audit_fixtures import auditar, edit_json, edit_yaml, editar_protocolo, fila, write_legacy_v07

from revisia.audit.checks_provenance import LEGACY_RUN

# ── protocol_snapshot ─────────────────────────────────────────────────


def test_protocol_snapshot_corrida_real_pasa(corrida) -> None:
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "PASS"
    assert "6 ficheros de 00_protocol/ con el hash de run.json" in snapshot.detail


def test_protocol_snapshot_corrida_anterior_a_la_ola_1_falla_pero_se_diagnostica(tmp_path) -> None:
    # D13: no publicable, pero auditable como diagnóstico con las relaciones v0.7.
    report = auditar(write_legacy_v07(tmp_path))
    snapshot = fila(report, "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert snapshot.detail == (
        "anterior a la Ola 1 (motor < 0.8): sin instantánea ni decisiones por registro; "
        "regenera la corrida con el motor actual."
    )
    assert snapshot.detail == f"{LEGACY_RUN}."
    assert fila(report, "arithmetic").status == "PASS"
    assert "relaciones v0.7" in fila(report, "arithmetic").detail
    assert fila(report, "schemas").status == "PASS"  # sus decision.yml son de v0.7
    assert not report.publishable


def test_protocol_snapshot_hash_alterado_falla(corrida) -> None:
    path = corrida / "00_protocol" / "inclusion_exclusion.yml"
    path.write_text(path.read_text(encoding="utf-8") + "# editado a mano\n", encoding="utf-8")
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "`00_protocol/inclusion_exclusion.yml`: hash distinto del de run.json" in (
        snapshot.detail
    )


def test_protocol_snapshot_fichero_de_la_lista_ausente_falla(corrida) -> None:
    (corrida / "00_protocol" / "effects.yml").unlink()
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "`00_protocol/effects.yml` ausente" in snapshot.detail


def test_protocol_snapshot_instantanea_distinta_del_manifiesto_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["protocol"].update(title="Otro título"))
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "FAIL"
    assert "no coincide con `manifest.protocol`" in snapshot.detail


def test_protocol_snapshot_fichero_extra_advierte(corrida) -> None:
    (corrida / "00_protocol" / "notas.txt").write_text("apuntes\n", encoding="utf-8")
    snapshot = fila(auditar(corrida), "protocol_snapshot")
    assert snapshot.status == "WARN"
    assert "`notas.txt`" in snapshot.detail


def test_registration_lee_la_instantanea(corrida) -> None:
    # Solo la instantánea pierde el registro: el auditor la lee a ella.
    edit_yaml(corrida / "00_protocol" / "protocol.yml", lambda p: p.update(registration={}))
    assert fila(auditar(corrida), "registration").status == "WARN"
    editar_protocolo(corrida, lambda p: p.update(registration={"osf": "OSF-1"}))
    assert fila(auditar(corrida), "registration").status == "PASS"


# ── schemas de los artefactos de la Ola 1 ─────────────────────────────

ARTEFACTOS_OLA1 = (
    "01_search/records.json",
    "01_search/log.json",
    "02_dedup/records.json",
    "02_dedup/dedup.json",
    "03_screening/gold.json",
    "04_fulltext/retrieval.json",
    "04_fulltext/excluded.json",
    "run.json",
)


@pytest.mark.parametrize("rel", ARTEFACTOS_OLA1)
def test_schemas_artefacto_de_la_ola_1_invalido_falla(corrida, rel: str) -> None:
    (corrida / rel).write_text('{"no": "valida"}', encoding="utf-8")
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert rel in schemas.detail


def test_schemas_linea_de_diario_invalida_falla_con_su_numero(corrida) -> None:
    path = corrida / "03_screening" / "journal.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"input_sha256"', '"input"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "03_screening/journal.jsonl: línea 2: input_sha256: Field required" in schemas.detail


def test_schemas_llamada_sin_etapa_en_llm_calls_jsonl_falla(corrida) -> None:
    path = corrida / "llm_calls.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace('"stage":"screening_ta"', '"stage":"cribado"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "llm_calls.jsonl: línea 1: stage" in schemas.detail


def test_schemas_retrieval_sin_motivo_de_fallo_falla(corrida) -> None:
    def _sin_motivo(rows: list[dict]) -> None:
        rows[0].update(available=False, reason=None)

    edit_json(corrida / "04_fulltext" / "retrieval.json", _sin_motivo)
    schemas = fila(auditar(corrida), "schemas")
    assert schemas.status == "FAIL"
    assert "04_fulltext/retrieval.json" in schemas.detail


# ── stage_artifacts y deliverable de la Ola 1 ─────────────────────────


@pytest.mark.parametrize(
    ("rel", "etapa"),
    [
        ("01_search/log.json", "busqueda"),
        ("02_dedup/dedup.json", "dedup"),
        ("03_screening/journal.jsonl", "screening_ta"),
        ("04_fulltext/excluded.json", "screening_ft"),
        ("05_extraction/journal_2.jsonl", "extraccion"),
        ("06_synthesis/verification.jsonl", "sintesis"),
    ],
)
def test_stage_artifacts_exige_los_artefactos_de_la_ola_1(corrida, rel: str, etapa: str) -> None:
    (corrida / rel).unlink()
    stage = fila(auditar(corrida), "stage_artifacts")
    assert stage.status == "FAIL"
    assert f"{etapa}: {rel}" in stage.detail


def test_deliverable_exige_la_lista_16b(corrida) -> None:
    (corrida / "deliverable" / "excluidos_texto_completo.md").unlink()
    deliverable = fila(auditar(corrida), "deliverable")
    assert deliverable.status == "FAIL"
    assert "excluidos_texto_completo.md (falta)" in deliverable.detail
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_instantanea.py -v`
Expected: ERROR de colección, `ImportError: cannot import name 'LEGACY_RUN' from 'revisia.audit.checks_provenance'`.

- [ ] **Step 3: Modelos y adaptadores de los artefactos nuevos (`artifacts.py`)**

En `revisia/audit/artifacts.py`, sustituir

```python
from typing import Any, Generic, TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError

from revisia.audit.state import RunState, derive_state
```

por

```python
from typing import Any, Generic, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, StrictBool, TypeAdapter, ValidationError

from revisia.audit.state import RunState, derive_state
```

En `revisia/audit/artifacts.py`, sustituir

```python
from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import HumanDecision
from revisia.provenance.ledger import DecisionEntry, summarize_gates
from revisia.provenance.runmeta import RunMeta
from revisia.schemas.artifacts import GATED_STAGES, GateSummary, RunInfo
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision
```

por

```python
from revisia.metrics import ScreeningMetrics
from revisia.orchestration.hitl import HumanDecision
from revisia.orchestration.snapshot import SNAPSHOT_DIR
from revisia.provenance.ledger import DecisionEntry, summarize_gates
from revisia.provenance.runmeta import RunMeta
from revisia.schemas.artifacts import (
    GATED_STAGES,
    JOURNAL_PATHS,
    DedupReport,
    ExcludedReport,
    GateSummary,
    JournalEntry,
    LLMCall,
    RetrievalOutcome,
    RunInfo,
    RunStatus,
    SearchLog,
)
from revisia.schemas.extraction import ExtractionRecord
from revisia.schemas.records import SearchRecord
from revisia.schemas.rob import RoBAssessment
from revisia.schemas.screening import ScreeningDecision
```

En `revisia/audit/artifacts.py`, sustituir

```python
    db: str
    error: str


def _type_names(root: type | tuple[type, ...]) -> str:
```

por

```python
    db: str
    error: str


class RetrievalRow(RetrievalOutcome):
    """Una fila de ``04_fulltext/retrieval.json``: ``{record_id, **RetrievalOutcome}``."""

    record_id: str


class LegacyDecision(BaseModel):
    """``decision.yml`` de una corrida anterior a la Ola 1 (sin ``request_sha256``).

    Se valida con su propio modelo: la corrida ya falla ``protocol_snapshot``
    (D13) y exigirle el contrato nuevo solo repetiría ese FAIL en ``schemas``.
    """

    model_config = ConfigDict(extra="allow")

    approved: StrictBool
    actor: str = "human:desconocido"
    reason: str | None = None


class ManifestRun(BaseModel):
    """Bloque ``run`` del manifiesto (copia de ``run.json``, spec §4.3)."""

    started_utc: str
    resumes: list[str]
    engine_version: str
    python_version: str
    status: RunStatus


class ManifestFinalGate(BaseModel):
    """Bloque ``final_gate`` del manifiesto (M5, spec §4.3)."""

    forced_human: bool
    reason: str | None = None


def _type_names(root: type | tuple[type, ...]) -> str:
```

En `revisia/audit/artifacts.py`, sustituir

```python
    "07_rob/assessments.json": TypeAdapter(dict[str, RoBAssessment]),
    "08_meta/meta_analysis.json": TypeAdapter(MetaAnalysisResult),
}

# Secciones de ``manifest.yml`` con modelo (las copias de los artefactos y los
```

por

```python
    "07_rob/assessments.json": TypeAdapter(dict[str, RoBAssessment]),
    "08_meta/meta_analysis.json": TypeAdapter(MetaAnalysisResult),
    "01_search/records.json": TypeAdapter(list[SearchRecord]),
    "01_search/log.json": TypeAdapter(SearchLog),
    "02_dedup/records.json": TypeAdapter(list[SearchRecord]),
    "02_dedup/dedup.json": TypeAdapter(DedupReport),
    "03_screening/gold.json": TypeAdapter(dict[str, bool]),
    "04_fulltext/retrieval.json": TypeAdapter(list[RetrievalRow]),
    "04_fulltext/excluded.json": TypeAdapter(list[ExcludedReport]),
}

# Artefactos ``.jsonl`` (una línea, un modelo): llamadas y diarios (D3).
JSONL_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "llm_calls.jsonl": TypeAdapter(LLMCall),
    **{rel: TypeAdapter(JournalEntry) for rel in JOURNAL_PATHS.values()},
}

# Secciones de ``manifest.yml`` con modelo (las copias de los artefactos y los
```

En `revisia/audit/artifacts.py`, sustituir

```python
    "meta_analysis": TypeAdapter(MetaAnalysisResult),
    "risk_of_bias": TypeAdapter(dict[str, RoBAssessment]),
}

_DECISION_ADAPTER: TypeAdapter[HumanDecision] = TypeAdapter(HumanDecision)
_RUN_INFO_ADAPTER: TypeAdapter[RunInfo] = TypeAdapter(RunInfo)


class RunArtifacts:
```

por

```python
    "meta_analysis": TypeAdapter(MetaAnalysisResult),
    "risk_of_bias": TypeAdapter(dict[str, RoBAssessment]),
    "run": TypeAdapter(ManifestRun),
    "autonomy_effective": TypeAdapter(dict[str, str]),
    "final_gate": TypeAdapter(ManifestFinalGate),
}

_DECISION_ADAPTER: TypeAdapter[HumanDecision] = TypeAdapter(HumanDecision)
_LEGACY_DECISION_ADAPTER: TypeAdapter[LegacyDecision] = TypeAdapter(LegacyDecision)
_RUN_INFO_ADAPTER: TypeAdapter[RunInfo] = TypeAdapter(RunInfo)


class RunArtifacts:
```

En `revisia/audit/artifacts.py`, sustituir

```python
        return self._memo("model", rel, lambda: validate(self.json(rel), ARTIFACT_ADAPTERS[rel]))

    def decision(self, gate: str) -> Loaded[HumanDecision]:
        """``<gate>/decision.yml`` validado como ``HumanDecision``."""
        rel = f"{gate}/decision.yml"
        return self._memo("decision", rel, lambda: validate(self.yaml(rel), _DECISION_ADAPTER))

    def run_info(self) -> Loaded[RunInfo]:
```

por

```python
        return self._memo("model", rel, lambda: validate(self.json(rel), ARTIFACT_ADAPTERS[rel]))

    def jsonl_models(self, rel: str) -> Loaded[list[tuple[int, Any]]]:
        """Artefacto ``.jsonl`` de :data:`JSONL_ADAPTERS`, validado línea a línea.

        ``value`` = ``[(número de línea, modelo)]`` de las líneas válidas;
        ``error`` = una línea de texto por línea inválida, con su número.
        """

        def _load() -> Loaded[list[tuple[int, Any]]]:
            raw = self.jsonl(rel)
            if not raw.present or raw.value is None:
                return raw
            adapter = JSONL_ADAPTERS[rel]
            items: list[tuple[int, Any]] = []
            errors = (raw.error or "").splitlines()
            for number, obj in raw.value:
                try:
                    items.append((number, adapter.validate_python(obj)))
                except ValidationError as exc:
                    errors.append(f"línea {number}: {format_validation(exc, limit=2)}")
            return Loaded(rel, True, items, "\n".join(errors) or None)

        return self._memo("jsonl_models", rel, _load)

    def decision(self, gate: str) -> Loaded[Any]:
        """``<gate>/decision.yml`` validado: ``HumanDecision`` o, sin ``run.json``
        (corrida anterior a la Ola 1), ``LegacyDecision``."""
        rel = f"{gate}/decision.yml"
        adapter = _DECISION_ADAPTER if self.exists("run.json") else _LEGACY_DECISION_ADAPTER
        return self._memo("decision", rel, lambda: validate(self.yaml(rel), adapter))

    def run_info(self) -> Loaded[RunInfo]:
```

En `revisia/audit/artifacts.py`, sustituir

```python
    @cached_property
    def llm_calls(self) -> list[dict[str, Any]]:
        """Las llamadas del manifiesto que son mapas (las demás las marca ``schemas``)."""
        calls = (self.manifest_dict or {}).get("llm_calls")
        return [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []
```

por

```python
    @cached_property
    def llm_calls(self) -> list[dict[str, Any]]:
        """Las llamadas IA de la corrida, como mapas.

        Las de ``llm_calls.jsonl`` si existe (la fuente, escrita en cada llamada);
        si no, las del manifiesto. Las que no son mapas las marca ``schemas``.
        """
        raw = self.art.jsonl("llm_calls.jsonl")
        if raw.present and raw.value is not None:
            return [c for _, c in raw.value if isinstance(c, dict)]
        calls = (self.manifest_dict or {}).get("llm_calls")
        return [c for c in calls if isinstance(c, dict)] if isinstance(calls, list) else []
```

En `revisia/audit/artifacts.py`, sustituir

```python
            return RunState("unknown", frozenset(STAGES))

    @cached_property
    def protocol(self) -> ReviewProtocol | None:
        """El protocolo tal como lo registró el manifiesto (``None`` si no valida)."""
        loaded = self.manifest_section("protocol")
        return loaded.value if loaded.ok else None
```

por

```python
            return RunState("unknown", frozenset(STAGES))

    @cached_property
    def snapshot_protocol(self) -> Loaded[Any]:
        """``00_protocol/protocol.yml`` validado como ``ReviewProtocol``.

        Como ``load_protocol`` al reanudar (spec §2, hallazgo 4), el ``slug`` que
        el protocolo no declare sale de ``run.json``, no del nombre de la carpeta.
        """
        raw = self.art.yaml(f"{SNAPSHOT_DIR}/protocol.yml")
        if not raw.ok:
            return raw
        data = dict(raw.value)
        slug = self.run_info.slug if self.run_info else (self.manifest_dict or {}).get("slug")
        if slug:
            data.setdefault("slug", slug)
        return validate(Loaded(raw.path, True, data), MANIFEST_ADAPTERS["protocol"])

    @cached_property
    def protocol_raw(self) -> dict[str, Any] | None:
        """El protocolo como mapa: la instantánea si existe; si no, el manifiesto."""
        snapshot = self.art.yaml(f"{SNAPSHOT_DIR}/protocol.yml")
        if snapshot.ok:
            return snapshot.value
        raw = (self.manifest_dict or {}).get("protocol")
        return raw if isinstance(raw, dict) else None

    @cached_property
    def protocol(self) -> ReviewProtocol | None:
        """El protocolo de la corrida (``None`` si no valida).

        ``00_protocol/`` es la única fuente desde la Ola 1 (D3); sin
        instantánea, el que registró el manifiesto.
        """
        if self.art.exists(f"{SNAPSHOT_DIR}/protocol.yml"):
            loaded = self.snapshot_protocol
        else:
            loaded = self.manifest_section("protocol")
        return loaded.value if loaded.ok else None
```

- [ ] **Step 4: `check_protocol_snapshot` y `schemas` con los `.jsonl`**

En `revisia/audit/checks_provenance.py`, sustituir

```python
from revisia.audit.artifacts import (
    ARTIFACT_ADAPTERS,
    MANIFEST_ADAPTERS,
    AuditContext,
```

por

```python
from revisia.audit.artifacts import (
    ARTIFACT_ADAPTERS,
    JSONL_ADAPTERS,
    MANIFEST_ADAPTERS,
    AuditContext,
```

En `revisia/audit/checks_provenance.py`, sustituir

```python
from revisia.audit.model import Verdict
from revisia.orchestration.run_context import PROVENANCE_PIPELINE
from revisia.schemas.artifacts import GATED_STAGES

_NA_MANIFIESTO = "no aplica: el manifiesto no se pudo leer (ver `manifest`)."
```

por

```python
from revisia.audit.model import Verdict
from revisia.orchestration.run_context import PROVENANCE_PIPELINE
from revisia.orchestration.snapshot import SNAPSHOT_DIR, protocol_fingerprint
from revisia.schemas.artifacts import GATED_STAGES

# D13: una corrida sin run.json no es publicable (spec 2026-10-04 §3).
LEGACY_RUN = (
    "anterior a la Ola 1 (motor < 0.8): sin instantánea ni decisiones por registro; "
    "regenera la corrida con el motor actual"
)

_NA_MANIFIESTO = "no aplica: el manifiesto no se pudo leer (ver `manifest`)."
```

En `revisia/audit/checks_provenance.py`, sustituir

```python
        results.append(ctx.art.run_info())
    results += [ctx.art.artifact(rel) for rel in ARTIFACT_ADAPTERS if ctx.art.exists(rel)]
    for gate in GATED_STAGES:
        if ctx.art.exists(f"{gate}/review_request.yml"):
```

por

```python
        results.append(ctx.art.run_info())
    results += [ctx.art.artifact(rel) for rel in ARTIFACT_ADAPTERS if ctx.art.exists(rel)]
    results += [ctx.art.jsonl_models(rel) for rel in JSONL_ADAPTERS if ctx.art.exists(rel)]
    for gate in GATED_STAGES:
        if ctx.art.exists(f"{gate}/review_request.yml"):
```

En `revisia/audit/checks_provenance.py`, sustituir

```python
    return "PASS", f"{len(validated)} artefactos validan su modelo."


def check_prompts(ctx: AuditContext) -> Verdict:
    """trAIce M6: cada llamada con el hash de su prompt y de su respuesta."""
```

por

```python
    return "PASS", f"{len(validated)} artefactos validan su modelo."


def check_protocol_snapshot(ctx: AuditContext) -> Verdict:
    """PRISMA 24b / trAIce M1: la corrida usó el protocolo que dice haber usado.

    Compara ``00_protocol/`` con las huellas de ``run.json`` (texto con CRLF
    convertido a LF, como ``snapshot.protocol_fingerprint``) y la instantánea con
    el protocolo que registró el manifiesto. Sin ``run.json`` la corrida es
    anterior a la Ola 1 y no es publicable (D13), aunque el resto se audite
    como diagnóstico.
    """
    loaded = ctx.art.run_info()
    if not loaded.present:
        return "FAIL", f"{LEGACY_RUN}."
    if not loaded.ok:
        return "FAIL", f"run.json ilegible o inválido ({loaded.error}) (ver `schemas`)."
    registered = loaded.value.protocol_sha256
    snapshot = ctx.run_dir / SNAPSHOT_DIR
    actual = protocol_fingerprint(snapshot) if snapshot.is_dir() else {}
    fails: list[str] = []
    for rel, sha in sorted(registered.items()):
        if rel not in actual:
            fails.append(f"`{SNAPSHOT_DIR}/{rel}` ausente")
        elif actual[rel] != sha:
            fails.append(f"`{SNAPSHOT_DIR}/{rel}`: hash distinto del de run.json")
    if "protocol.yml" not in registered:
        fails.append("run.json no registra la huella de `protocol.yml`")
    manifest_protocol = (ctx.manifest_dict or {}).get("protocol")
    if manifest_protocol is not None:
        snap = ctx.snapshot_protocol
        if not snap.ok:
            fails.append(f"`{SNAPSHOT_DIR}/protocol.yml` no valida ({snap.error})")
        elif snap.value.model_dump(mode="json") != manifest_protocol:
            fails.append(
                f"la instantánea `{SNAPSHOT_DIR}/protocol.yml` no coincide con `manifest.protocol`"
            )
    if fails:
        return "FAIL", "; ".join(fails) + "."
    files = (
        sorted(p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file())
        if snapshot.is_dir()
        else []
    )
    extra = [f for f in files if f not in registered]
    if extra:
        return "WARN", (
            f"ficheros en {SNAPSHOT_DIR}/ fuera de la lista de hashes de run.json: "
            + ", ".join(f"`{f}`" for f in extra)
            + "."
        )
    return "PASS", (
        f"{len(registered)} ficheros de {SNAPSHOT_DIR}/ con el hash de run.json; la instantánea "
        "coincide con el protocolo del manifiesto."
    )


def check_prompts(ctx: AuditContext) -> Verdict:
    """trAIce M6: cada llamada con el hash de su prompt y de su respuesta."""
```

- [ ] **Step 5: Artefactos de la Ola 1 por etapa y lista 16b (`checks_flow.py`)**

En `revisia/audit/checks_flow.py`, sustituir

```python
from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.exclusions import compute_exclusion_breakdown
from revisia.extraction_agreement import select_double_extraction_subset
```

por

```python
from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.config import STAGES
from revisia.exclusions import compute_exclusion_breakdown
from revisia.extraction_agreement import select_double_extraction_subset
```

En `revisia/audit/checks_flow.py`, sustituir

```python
    "sintesis": ("06_synthesis/verification.json",),
    "reporte": ("manifest.yml",),
}
# Artefactos que existen si el manifiesto registra su copia.
```

por

```python
    "sintesis": ("06_synthesis/verification.json",),
    "reporte": ("manifest.yml",),
}
# Artefactos de la Ola 1 (spec §4.2): solo se exigen con run.json.
STAGE_ARTIFACTS_OLA1: dict[str, tuple[str, ...]] = {
    "protocolo": ("run.json", "00_protocol/protocol.yml"),
    "busqueda": ("01_search/records.json", "01_search/log.json"),
    "dedup": ("02_dedup/records.json", "02_dedup/dedup.json"),
    "screening_ta": ("03_screening/journal.jsonl", "llm_calls.jsonl"),
    "screening_ft": (
        "04_fulltext/retrieval.jsonl",
        "04_fulltext/retrieval.json",
        "04_fulltext/excluded.json",
    ),
    "sintesis": ("06_synthesis/journal.jsonl", "06_synthesis/verification.jsonl"),
}
# Artefactos que existen si el manifiesto registra su copia.
```

En `revisia/audit/checks_flow.py`, sustituir

```python
    return [d.record_id for d in ft.value if d.final_label in {"include", "unclear"}]


def check_stage_artifacts(ctx: AuditContext) -> Verdict:
    """PRISMA 16/27: cada etapa alcanzada dejó sus artefactos (§4.2)."""
```

por

```python
    return [d.record_id for d in ft.value if d.final_label in {"include", "unclear"}]


def _journals_ola1(ctx: AuditContext) -> list[tuple[str, str]]:
    """Diarios que existen si su etapa tuvo trabajo: FT con algún recuperado,
    extracción y RoB con algún incluido, 2.º extractor con doble extracción."""
    required: list[tuple[str, str]] = []
    reached = ctx.state.reached
    ft = ctx.art.artifact(FT)
    if "screening_ft" in reached and ft.ok and any(d.votes for d in ft.value):
        required.append(("screening_ft", "04_fulltext/journal.jsonl"))
    extractions = ctx.art.artifact("05_extraction/extractions.json")
    if extractions.ok and extractions.value:
        if "extraccion" in reached:
            required.append(("extraccion", "05_extraction/journal.jsonl"))
        if "rob" in reached:
            required.append(("rob", "07_rob/journal.jsonl"))
    if "extraccion" in reached and ctx.art.exists("05_extraction/agreement.json"):
        required.append(("extraccion", "05_extraction/journal_2.jsonl"))
    return required


def check_stage_artifacts(ctx: AuditContext) -> Verdict:
    """PRISMA 16/27: cada etapa alcanzada dejó sus artefactos (§4.2)."""
```

En `revisia/audit/checks_flow.py`, sustituir

```python
        if key in manifest and stage in ctx.state.reached:
            required.append((stage, rel))
    missing = [f"{stage}: {rel}" for stage, rel in required if not ctx.art.exists(rel)]
    if missing:
        return "FAIL", f"faltan artefactos de etapas alcanzadas: {_limitar(missing)}."
    stages = sorted({stage for stage, _ in required}, key=list(STAGE_ARTIFACTS).index)
    return "PASS", (
        f"{len(required)} artefactos de {len(stages)} etapas alcanzadas presentes "
```

por

```python
        if key in manifest and stage in ctx.state.reached:
            required.append((stage, rel))
    if ctx.art.exists("run.json"):
        for stage, rels in STAGE_ARTIFACTS_OLA1.items():
            if stage in ctx.state.reached:
                required += [(stage, rel) for rel in rels]
        required += _journals_ola1(ctx)
    missing = [f"{stage}: {rel}" for stage, rel in required if not ctx.art.exists(rel)]
    if missing:
        return "FAIL", f"faltan artefactos de etapas alcanzadas: {_limitar(missing)}."
    stages = sorted({stage for stage, _ in required}, key=STAGES.index)
    return "PASS", (
        f"{len(required)} artefactos de {len(stages)} etapas alcanzadas presentes "
```

En `revisia/audit/checks_flow.py`, sustituir

```python
    """PRISMA 16/16b/17/18/27: entregable completo y sin ficheros vacíos."""
    required = list(DELIVERABLE_FILES)
    if "meta_analysis" in (ctx.manifest_dict or {}) or ctx.art.exists("08_meta/meta_analysis.json"):
        required.append("meta_analisis.md")
```

por

```python
    """PRISMA 16/16b/17/18/27: entregable completo y sin ficheros vacíos."""
    required = list(DELIVERABLE_FILES)
    if ctx.art.exists("run.json"):
        required.append("excluidos_texto_completo.md")  # 16b (desde la Ola 1)
    if "meta_analysis" in (ctx.manifest_dict or {}) or ctx.art.exists("08_meta/meta_analysis.json"):
        required.append("meta_analisis.md")
```

- [ ] **Step 6: El protocolo, de la instantánea (`checks_search.py`)**

En `revisia/audit/checks_search.py`, sustituir

```python
from revisia.audit.model import Verdict

_NA_PROTOCOLO = "no aplica: sin protocolo legible en el manifiesto (ver `manifest`)."


def _protocol_section(ctx: AuditContext, key: str) -> dict | None:
    if ctx.manifest_dict is None:
        return None
    protocol = ctx.manifest_dict.get("protocol")
    if not isinstance(protocol, dict):
        return {}
    section = protocol.get(key)
    return section if isinstance(section, dict) else {}
```

por

```python
from revisia.audit.model import Verdict

_NA_PROTOCOLO = "no aplica: sin protocolo legible (ni instantánea ni manifiesto)."


def _protocol_section(ctx: AuditContext, key: str) -> dict | None:
    """Sección del protocolo: de la instantánea ``00_protocol/`` si existe."""
    protocol = ctx.protocol_raw
    if protocol is None:
        return None
    section = protocol.get(key)
    return section if isinstance(section, dict) else {}
```

- [ ] **Step 7: Registrar `protocol_snapshot`**

En `revisia/audit/__init__.py`, sustituir

```python
    CheckSpec("provenance", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_provenance),
    CheckSpec("schemas", "PRISMA 27 / trAIce M5", None, checks_provenance.check_schemas),
    CheckSpec("prompts", "trAIce M6", "reporte", checks_provenance.check_prompts),
    CheckSpec("timing", "PRISMA 27 / trAIce M2", None, checks_timing.check_timing),
```

por

```python
    CheckSpec("provenance", "PRISMA 27 / trAIce M2", "reporte", checks_provenance.check_provenance),
    CheckSpec("schemas", "PRISMA 27 / trAIce M5", None, checks_provenance.check_schemas),
    CheckSpec(
        "protocol_snapshot",
        "PRISMA 24b / trAIce M1",
        "protocolo",
        checks_provenance.check_protocol_snapshot,
    ),
    CheckSpec("prompts", "trAIce M6", "reporte", checks_provenance.check_prompts),
    CheckSpec("timing", "PRISMA 27 / trAIce M2", None, checks_timing.check_timing),
```

- [ ] **Step 8: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_instantanea.py -v`
Expected: PASS, 25 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, `N_D + 176` recogidos (675), 2 skipped.

- [ ] **Step 9: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 10: Commit**

```bash
git add revisia/audit tests/test_audit_instantanea.py
git commit -m "feat(audit): instantánea del protocolo (D13), esquemas y artefactos de la Ola 1" -m "protocol_snapshot compara 00_protocol/ con las huellas de run.json y con el protocolo del manifiesto; una corrida sin run.json es anterior a la Ola 1 y no es publicable (D13), aunque se audita entera como diagnóstico. schemas valida los artefactos nuevos y los .jsonl línea a línea; stage_artifacts exige los de §4.2 por etapa alcanzada y deliverable la lista 16b. El protocolo se lee de la instantánea. Spec 2026-10-04 §3 y §9.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: `search_log` (PRISMA-S, M12), `search_window` con la fecha del motor y marcas de `run.json` y del log

**Files:**
- Modify: `revisia/audit/checks_search.py` (`check_search_log`; `search_window` con la fecha del log)
- Modify: `revisia/audit/checks_timing.py` (marcas de `run.json` y de `01_search/log.json`, relación 14)
- Modify: `revisia/audit/__init__.py` (registra `search_log` antes de `search_window`)
- Test: `tests/test_audit_busqueda.py` (nuevo)

**Interfaces:**
- Consumes (PR-A/PR-C): `SearchLog(started_utc, finished_utc, max_results, mailto_set, entries)`; `SearchLogEntry(database, db_key, kind: database|manual_import|injected, declared, backend, status: ok|failed|manual_only|unknown, source_db: list[str], query, query_origin: file|question_fallback|…, query_file, query_sha256, max_results, started_utc, finished_utc, n_returned, error, file_sha256)`; `01_search/failures.json` (`[{db, error}]`); `00_protocol/search_strings/<db_key>.txt`; `revisia.agents.search_backends.db_key(db: str) -> str`; `sha256_text`; `RunInfo.resumes`, `.interruptions[].utc`; `parse_utc` (Tarea 6).
- Produces: `revisia.audit.checks_search.LOG = "01_search/log.json"`; `check_search_log(ctx) -> Verdict`. Fila `search_log` (`PRISMA-S 1/8/13/15`, etapa `busqueda`).

Reglas (spec §4.4 relaciones 1-3 y 14; §9.3 filas 6, 18 y 19): `search_log` da **FAIL** sin log o con log inválido; con una base declarada sin entrada (salvo búsqueda inyectada); con `status: unknown`; con un `failed` sin error, con registros o ausente de `failures.json`; si `query_sha256` no es el hash de la cadena, si `query_origin` y `query_file` no concuerdan o si la cadena no es la de `00_protocol/search_strings/<db_key>.txt`; si Σ `n_returned` de las entradas `ok` ≠ registros de `01_search/records.json`, o si los `source_db` del log no son los de esos registros. **WARN** con una búsqueda inyectada (`search_fn`, como la de los tests), una base caída, una base de importación manual sin registros importados, el fallback a la pregunta (PRISMA-S 8) o `n_returned == max_results` (¿truncados?). `search_window` pasa a PASS solo con la fecha del motor (el `started_utc` más temprano del log) y una ventana completa; avisa si la `executed` tecleada difiere. `timing` añade las marcas de `run.json` (`resumes` ascendente, interrupciones) y del log (ninguna entrada termina antes de empezar).

- [ ] **Step 1: Test que falla — crear `tests/test_audit_busqueda.py`**

```python
"""Búsqueda registrada por el motor: ``search_log``, ``search_window`` y marcas de tiempo.

Spec 2026-10-04 §4.4 (relaciones 1-3 y 14) y §9.3 (filas 6, 18 y 19). La
corrida real usa una búsqueda inyectada (``search_fn``); ``_log_de_bases`` la
convierte en la de una base declarada, como la dejaría ``revisia run``.
"""

from __future__ import annotations

import json

from audit_fixtures import auditar, edit_json, editar_protocolo, fila

from revisia.provenance.runmeta import sha256_text

LOG = "01_search/log.json"


def _log_de_bases(run, **cambios) -> None:
    """El log de una búsqueda en OpenAlex con su cadena de ``00_protocol/``."""
    cadena = (run / "00_protocol" / "search_strings" / "openalex.txt").read_text("utf-8").strip()

    def _editar(log: dict) -> None:
        entry = log["entries"][0]
        entry.update(
            database="OpenAlex",
            db_key="openalex",
            kind="database",
            declared=True,
            backend="search_backends.openalex_search",
            query=cadena,
            query_origin="file",
            query_file="00_protocol/search_strings/openalex.txt",
            query_sha256=sha256_text(cadena),
        )
        entry.update(cambios)

    edit_json(run / LOG, _editar)


def _anadir_entrada(run, entrada: dict) -> None:
    """Añade al log una entrada de base declarada, sin cadena ni registros."""

    def _editar(log: dict) -> None:
        base = {
            "kind": "database",
            "declared": True,
            "source_db": [],
            "max_results": 25,
            "started_utc": log["started_utc"],
            "finished_utc": log["finished_utc"],
            "n_returned": 0,
        }
        log["entries"].append({**base, **entrada})

    edit_json(run / LOG, _editar)


# ── search_log ─────────────────────────────────────────────────────────


def test_search_log_busqueda_inyectada_advierte(corrida) -> None:
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "búsqueda inyectada (`search_fn`)" in search_log.detail


def test_search_log_base_con_su_cadena_pasa(corrida) -> None:
    _log_de_bases(corrida)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "PASS"
    assert "cada base con su cadena registrada; 7 registros" in search_log.detail


def test_search_log_ausente_falla(corrida) -> None:
    (corrida / LOG).unlink()
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "01_search/log.json ausente" in search_log.detail


def test_search_log_base_declarada_sin_entrada_falla(corrida) -> None:
    _log_de_bases(corrida)
    editar_protocolo(corrida, lambda p: p.update(databases=["OpenAlex", "Europe PMC"]))
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "bases declaradas sin entrada en el log: Europe PMC" in search_log.detail


def test_search_log_cadena_distinta_de_la_instantanea_falla(corrida) -> None:
    _log_de_bases(corrida, query="otra cadena", query_sha256=sha256_text("otra cadena"))
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "cadena distinta de `00_protocol/search_strings/openalex.txt`" in search_log.detail


def test_search_log_query_sha256_falso_falla(corrida) -> None:
    _log_de_bases(corrida, query_sha256="0" * 64)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`query_sha256` no es el hash de la cadena (relación 3)" in search_log.detail


def test_search_log_tope_de_max_results_advierte(corrida) -> None:
    _log_de_bases(corrida, max_results=7)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "7 resultados = max_results (¿truncados?)" in search_log.detail


def test_search_log_base_caida_advierte(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(
        corrida,
        {
            "database": "Crossref",
            "db_key": "crossref",
            "status": "failed",
            "error": "HTTPStatusError: 503",
            "n_returned": 0,
            "source_db": [],
        },
    )
    failures = [{"db": "Crossref", "error": "HTTPStatusError: 503"}]
    (corrida / "01_search" / "failures.json").write_text(json.dumps(failures), encoding="utf-8")
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "`Crossref` falló (HTTPStatusError: 503)" in search_log.detail


def test_search_log_fallo_que_no_esta_en_failures_json_falla(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(
        corrida,
        {"database": "Crossref", "db_key": "crossref", "status": "failed", "error": "x"},
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "no está en 01_search/failures.json (relación 2)" in search_log.detail


def test_search_log_fallback_a_la_pregunta_advierte(corrida) -> None:
    pregunta = "machine learning and large language models for systematic review screening"
    _log_de_bases(
        corrida,
        query=pregunta,
        query_origin="question_fallback",
        query_file=None,
        query_sha256=sha256_text(pregunta),
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "WARN"
    assert "`OpenAlex`: sin cadena propia, se usó la pregunta (PRISMA-S 8)" in search_log.detail


def test_search_log_base_desconocida_falla(corrida) -> None:
    _log_de_bases(corrida)
    _anadir_entrada(
        corrida,
        {"database": "Scopsu", "db_key": "scopsu", "status": "unknown", "n_returned": 0},
    )
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "`Scopsu`: status `unknown`" in search_log.detail


def test_search_log_registros_que_no_suman_falla(corrida) -> None:
    _log_de_bases(corrida, n_returned=9)
    search_log = fila(auditar(corrida), "search_log")
    assert search_log.status == "FAIL"
    assert "Σ n_returned 9 ≠ 7 registros en 01_search/records.json (relación 1)" in (
        search_log.detail
    )


# ── search_window desde el log ─────────────────────────────────────────


def _fecha_del_motor(run) -> str:
    log = json.loads((run / LOG).read_text(encoding="utf-8"))
    return log["started_utc"][:10]


def test_search_window_fecha_tecleada_distinta_de_la_del_motor_advierte(corrida) -> None:
    window = fila(auditar(corrida), "search_window")
    assert window.status == "WARN"
    assert "`executed: 2026-06-26` tecleada distinta de la fecha del motor" in window.detail


def test_search_window_con_la_fecha_del_motor_pasa(corrida) -> None:
    fecha = _fecha_del_motor(corrida)
    editar_protocolo(corrida, lambda p: p["search_window"].update(executed=fecha))
    window = fila(auditar(corrida), "search_window")
    assert window.status == "PASS"
    assert f"búsqueda ejecutada por el motor el {fecha}" in window.detail


# ── timing con run.json y el log ──────────────────────────────────────


def test_timing_log_que_termina_antes_de_empezar_falla(corrida) -> None:
    def _al_reves(log: dict) -> None:
        log["entries"][0]["finished_utc"] = "2026-01-01T00:00:00.5+00:00"

    edit_json(corrida / LOG, _al_reves)
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "finished_utc anterior a started_utc" in timing.detail


def test_timing_resumes_que_no_suben_fallan(corrida) -> None:
    edit_json(corrida / "run.json", lambda info: info["resumes"].reverse())
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "run.json: `resumes` no es ascendente" in timing.detail


def test_timing_reanudacion_anterior_al_inicio_falla(corrida) -> None:
    edit_json(
        corrida / "run.json",
        lambda info: info["resumes"].insert(0, "2026-01-01T00:00:00.5+00:00"),
    )
    timing = fila(auditar(corrida), "timing")
    assert timing.status == "FAIL"
    assert "run.json resumes[0] anterior al inicio de la corrida" in timing.detail
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_busqueda.py -v`
Expected: FAIL: `AssertionError: sin fila 'search_log'` en los de `search_log`; `search_window` sigue en WARN con la fecha del motor; los tres de `timing` no ven las marcas de `run.json` ni del log.

- [ ] **Step 3: `check_search_log` y `search_window` (`checks_search.py`)**

Sustituir el contenido completo de `revisia/audit/checks_search.py` por:

```python
"""Checks de búsqueda y registro: ``search_log``, ``search_window``, ``registration``.

Desde la Ola 1 el motor registra la búsqueda en ``01_search/log.json``: una
entrada por base declarada, por fichero importado o por búsqueda inyectada,
con la cadena efectiva, su hash, los parámetros, las horas y cuántos registros
devolvió (PRISMA-S 1/8/13; auditoría 2026-09-03, M12). Antes la fecha y las
cadenas salían de lo que el humano tecleaba en ``protocol.yml``.
"""

from __future__ import annotations

from collections import Counter

from revisia.agents import search_backends
from revisia.audit.artifacts import AuditContext
from revisia.audit.checks_timing import parse_utc
from revisia.audit.model import Verdict
from revisia.provenance.runmeta import sha256_text

LOG = "01_search/log.json"
_NA_PROTOCOLO = "no aplica: sin protocolo legible (ni instantánea ni manifiesto)."
_MAX = 5


def _limitar(items: list[str]) -> str:
    more = len(items) - _MAX
    return "; ".join(items[:_MAX]) + (f" (+{more} más)" if more > 0 else "")


def _protocol_section(ctx: AuditContext, key: str) -> dict | None:
    """Sección del protocolo: de la instantánea ``00_protocol/`` si existe."""
    protocol = ctx.protocol_raw
    if protocol is None:
        return None
    section = protocol.get(key)
    return section if isinstance(section, dict) else {}


def check_search_log(ctx: AuditContext) -> Verdict:
    """PRISMA-S 1/8/13/15: la búsqueda quedó registrada por el motor, base a base."""
    loaded = ctx.art.artifact(LOG)
    if not loaded.present:
        return "FAIL", (
            f"{LOG} ausente: la búsqueda no la registró el motor (cadenas, fechas y n por base; "
            "PRISMA-S 8/13)."
        )
    if not loaded.ok:
        return "FAIL", f"{LOG} inválido ({loaded.error})."
    entries = loaded.value.entries
    fails: list[str] = []
    warns: list[str] = []

    if any(e.kind == "injected" for e in entries):
        warns.append("búsqueda inyectada (`search_fn`): no corresponde a las bases declaradas")
    elif ctx.protocol is not None:
        logged = {e.db_key for e in entries if e.kind == "database"}
        missing = [db for db in ctx.protocol.databases if search_backends.db_key(db) not in logged]
        if missing:
            fails.append(f"bases declaradas sin entrada en el log: {', '.join(missing)}")

    failures = ctx.art.json("01_search/failures.json")
    failed_dbs = (
        {f.get("db") for f in failures.value if isinstance(f, dict)}
        if failures.ok and isinstance(failures.value, list)
        else set()
    )
    imported = sum(e.n_returned for e in entries if e.kind == "manual_import" and e.status == "ok")
    for e in entries:
        name = f"`{e.database}`"
        if e.status == "unknown":
            fails.append(f"{name}: status `unknown` ({e.error})")
        if e.status == "failed":
            warns.append(f"{name} falló ({e.error})")
            if not e.error or e.n_returned != 0:
                fails.append(f"{name}: `failed` sin error o con registros (relación 2)")
            if e.database not in failed_dbs:
                fails.append(f"{name}: `failed` y no está en 01_search/failures.json (relación 2)")
        if e.status == "manual_only" and not imported:
            warns.append(f"{name} es de importación manual y no hay registros importados")
        if e.query_origin == "question_fallback":
            warns.append(f"{name}: sin cadena propia, se usó la pregunta (PRISMA-S 8)")
        if e.status == "ok" and e.max_results is not None and e.n_returned == e.max_results:
            warns.append(f"{name}: {e.n_returned} resultados = max_results (¿truncados?)")
        if e.query is not None and e.query_sha256 != sha256_text(e.query):
            fails.append(f"{name}: `query_sha256` no es el hash de la cadena (relación 3)")
        if (e.query_origin == "file") != (e.query_file is not None):
            fails.append(f"{name}: `query_origin` y `query_file` no concuerdan (relación 3)")
        if e.query_origin == "file" and e.query_file is not None:
            text = ctx.art.text(e.query_file)
            expected = f"00_protocol/search_strings/{e.db_key}.txt"
            if e.query_file != expected or not text.ok:
                fails.append(f"{name}: la cadena no está en `{expected}`")
            elif text.value.strip() != e.query or sha256_text(text.value.strip()) != e.query_sha256:
                fails.append(f"{name}: cadena distinta de `{e.query_file}`")

    records = ctx.art.artifact("01_search/records.json")
    if not records.ok:
        fails.append("01_search/records.json ausente o inválido")
    else:
        returned = sum(e.n_returned for e in entries if e.status == "ok")
        if returned != len(records.value):
            fails.append(
                f"Σ n_returned {returned} ≠ {len(records.value)} registros en "
                "01_search/records.json (relación 1)"
            )
        sources = set(Counter(r.source_db for r in records.value))
        declared = {s for e in entries for s in e.source_db}
        if sources != declared:
            fails.append(
                f"source_db del log {sorted(declared)} ≠ los de records.json {sorted(sources)}"
            )

    if fails:
        return "FAIL", f"{_limitar(fails)}."
    if warns:
        return "WARN", f"{_limitar(warns)}."
    ok = sum(1 for e in entries if e.status == "ok")
    return "PASS", (
        f"{len(entries)} entradas en el log ({ok} `ok`), cada base con su cadena registrada; "
        f"{len(records.value)} registros."
    )


def _engine_date(ctx: AuditContext) -> str | None:
    """Fecha de ejecución que registró el motor: el ``started_utc`` más temprano del log."""
    loaded = ctx.art.artifact(LOG)
    if not loaded.ok:
        return None
    stamps = [loaded.value.started_utc] + [e.started_utc for e in loaded.value.entries]
    parsed = [p for p, _ in (parse_utc(s) for s in stamps if s) if p is not None]
    return min(parsed).date().isoformat() if parsed else None


def check_search_window(ctx: AuditContext) -> Verdict:
    """PRISMA-S 9/13: ventana de la búsqueda declarada y fecha de ejecución registrada.

    Sin ``01_search/log.json`` la fecha la tecleó un humano en el protocolo: el
    auditor anterior daba PASS por eso (auditoría 2026-09-03, C3/M12). Desde
    la Ola 1 la registra el motor.
    """
    window = _protocol_section(ctx, "search_window")
    if window is None:
        return "N/A", _NA_PROTOCOLO
    warns: list[str] = []
    missing = [k for k in ("from", "to") if not window.get(k)]
    if missing:
        warns.append(f"ventana sin `{'` ni `'.join(missing)}` (PRISMA-S 9)")
    executed = window.get("executed")
    engine = _engine_date(ctx)
    if engine is None:
        if executed:
            warns.append(
                f"fecha tecleada (`executed: {executed}`), no registrada por el motor "
                "(sin 01_search/log.json)"
            )
        else:
            warns.append("sin fecha de ejecución: ni `executed` ni 01_search/log.json")
    elif executed and str(executed) != engine:
        warns.append(
            f"`executed: {executed}` tecleada distinta de la fecha del motor ({engine}, "
            "01_search/log.json): corrígela o declara por qué"
        )
    if warns:
        return "WARN", "; ".join(warns) + "."
    return "PASS", (
        f"búsqueda ejecutada por el motor el {engine} (01_search/log.json); ventana "
        f"{window.get('from')} → {window.get('to')}."
    )


def check_registration(ctx: AuditContext) -> Verdict:
    """PRISMA 24a: registro del protocolo (leído de la instantánea si existe)."""
    registration = _protocol_section(ctx, "registration")
    if registration is None:
        return "N/A", _NA_PROTOCOLO
    declared = {k: v for k, v in registration.items() if v}
    if declared:
        return "PASS", (
            "Registro declarado: " + ", ".join(f"{k}={v}" for k, v in declared.items()) + "."
        )
    return "WARN", "Sin registro (PROSPERO/OSF): preregistra el protocolo antes de publicar."
```

- [ ] **Step 4: Marcas de `run.json` y del log (`checks_timing.py`)**

En `revisia/audit/checks_timing.py`, sustituir

```python
    return "; ".join(items[:_MAX]) + (f" (+{more} más)" if more > 0 else "")


def check_timing(ctx: AuditContext) -> Verdict:
    """PRISMA 27 / trAIce M2: las marcas de tiempo son posibles."""
```

por

```python
    return "; ".join(items[:_MAX]) + (f" (+{more} más)" if more > 0 else "")


def _marcas_ola1(ctx: AuditContext, fails: list[str]) -> list[tuple[str, datetime]]:
    """Marcas de ``run.json`` (reanudaciones, interrupciones) y del log de búsqueda.

    También son imposibles un ``resumes`` que no sube y una entrada del log que
    termina antes de empezar (relación 14 de §4.4).
    """
    marks: list[tuple[str, datetime]] = []

    def _mark(label: str, value: object) -> datetime | None:
        parsed, error = parse_utc(value)
        if error:
            fails.append(f"{label}: {error}")
            return None
        marks.append((label, parsed))
        return parsed

    if ctx.run_info is not None:
        resumes = [_mark(f"run.json resumes[{i}]", v) for i, v in enumerate(ctx.run_info.resumes)]
        valid = [r for r in resumes if r is not None]
        if valid != sorted(valid):
            fails.append("run.json: `resumes` no es ascendente")
        for i, interruption in enumerate(ctx.run_info.interruptions):
            _mark(f"run.json interruptions[{i}]", interruption.utc)
    log = ctx.art.artifact("01_search/log.json")
    if log.ok:
        spans = [("01_search/log.json", log.value.started_utc, log.value.finished_utc)]
        spans += [
            (f"01_search/log.json `{e.database}`", e.started_utc, e.finished_utc)
            for e in log.value.entries
        ]
        for label, start, end in spans:
            started = _mark(f"{label} started_utc", start) if start else None
            finished = _mark(f"{label} finished_utc", end) if end else None
            if started and finished and finished < started:
                fails.append(f"{label}: finished_utc anterior a started_utc")
    return marks


def check_timing(ctx: AuditContext) -> Verdict:
    """PRISMA 27 / trAIce M2: las marcas de tiempo son posibles."""
```

En `revisia/audit/checks_timing.py`, sustituir

```python
            ledger_marks.append((number, parsed))
            marks.append((f"ledger línea {number}", parsed))

    lower, lower_warn, lower_fail = _limite_inferior(ctx)
```

por

```python
            ledger_marks.append((number, parsed))
            marks.append((f"ledger línea {number}", parsed))

    marks += _marcas_ola1(ctx, fails)

    lower, lower_warn, lower_fail = _limite_inferior(ctx)
```

- [ ] **Step 5: Registrar `search_log`**

En `revisia/audit/__init__.py`, sustituir

```python
    ),
    CheckSpec("grounding", "trAIce M8/M9", "sintesis", checks_quality.check_grounding),
    CheckSpec("search_window", "PRISMA-S 9/13", "busqueda", checks_search.check_search_window),
    CheckSpec("registration", "PRISMA 24a", None, checks_search.check_registration),
```

por

```python
    ),
    CheckSpec("grounding", "trAIce M8/M9", "sintesis", checks_quality.check_grounding),
    CheckSpec("search_log", "PRISMA-S 1/8/13/15", "busqueda", checks_search.check_search_log),
    CheckSpec("search_window", "PRISMA-S 9/13", "busqueda", checks_search.check_search_window),
    CheckSpec("registration", "PRISMA 24a", None, checks_search.check_registration),
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_busqueda.py -v`
Expected: PASS, 17 tests.

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, `N_D + 193` recogidos (692), 2 skipped.

- [ ] **Step 7: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 8: Commit**

```bash
git add revisia/audit tests/test_audit_busqueda.py
git commit -m "feat(audit): log de búsqueda registrado por el motor (PRISMA-S, M12)" -m "search_log exige 01_search/log.json con una entrada por base declarada, su cadena de 00_protocol/search_strings/ con su hash, los fallos en failures.json y Σ n_returned igual a los registros de 01_search/records.json (relaciones 1-3). search_window solo da PASS con la fecha que registró el motor. timing añade las marcas de run.json y del log (relación 14). Spec 2026-10-04 §4.4 y §9.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: `arithmetic` de la Ola 1 (relaciones 1-13 de §4.4 con `run.json`)

**Files:**
- Modify: `revisia/audit/checks_flow.py` (`check_arithmetic` con las relaciones v0.8)
- Test: `tests/test_audit_aritmetica_ola1.py` (nuevo)

**Interfaces:**
- Consumes (PR-A..PR-D): `PrismaCounts` con `fulltext_sought`, `fulltext_not_retrieved`, `fulltext_rescued`, `fulltext_assessed`, `excluded_ft_human`, `excluded_ft_ai`, `ft_exclusion_reasons`, `removed_*`; `ScreeningDecision.fulltext_status`, `.human_label`, `.human_reason`, `.human_actor`, `.final_label`; `DedupReport(n_in, n_out, duplicates, renamed)`; `RetrievalRow`; `ExcludedReport(record_id, title, year, doi, reason, reason_source)`; `JournalEntry(stage, record_id, input_sha256, output, metas: list[LLMCall])`; `LLMCall(stage, record_id, role)`; `JOURNAL_PATHS`; `03_screening/gold.json` (Tarea 12).
- Produces: `check_arithmetic` con dos ramas: sin `run.json`, las relaciones v0.7 de la Tarea 7 (el detalle lo dice: "relaciones v0.7: corrida sin run.json"); con él, las de la Ola 1. Las relaciones tienen nombre con su número de §4.4 ("`7 · retrieved ⇔ retrieval.available ⇔ un voto`").

Relaciones nuevas (spec §4.4): **1** `identified == len(01_search/records.json)` e `identified_by_source == Counter(source_db)`; **4** `dedup.n_in == identified`, `n_in − n_out == len(duplicates) == duplicates_removed`, `n_out == screened == len(02_dedup/records.json)`, ids únicos; **5** `03_screening/decisions.json` en el orden de `02_dedup/records.json`; **6** `fulltext_sought == screened − excluded_ta == #(final T/A ∈ {include, unclear})`; **7** ids de `04_fulltext` = los que pasan T/A y `retrieved ⇔ retrieval.available ⇔ un voto` (un no recuperado no se criba con IA, D2); **8** `fulltext_assessed == fulltext_sought − fulltext_not_retrieved == #(final FT ≠ null)`, `fulltext_not_retrieved`/`fulltext_rescued` según haya humano; **9** `excluded_ft_human + excluded_ft_ai == excluded_ft == len(excluded.json)`, razones = `Counter(reason)` de `excluded.json`, `reason_source == human ⇔ human_label == exclude`; **10** `included == #(final FT == include)`; **11** CSV PRISMA2020 con los campos nuevos; **12** las metas de cada línea de diario están en `llm_calls.jsonl` y en el número esperado por etapa; **13** el consolidado (`decisions.json`, `extractions.json`, `assessments.json`, `verification.json`) es una línea de su diario sin los campos humanos. Además `manifest.llm_calls == llm_calls.jsonl` y las métricas se recalculan desde `03_screening/gold.json`.

- [ ] **Step 1: Test que falla — crear `tests/test_audit_aritmetica_ola1.py`**

```python
"""``arithmetic`` con los artefactos de la Ola 1: relaciones 1-13 de §4.4 (F2).

Cada caso rompe una relación de la corrida real (búsqueda, dedup, recuperación,
16b, CSV, diarios, métricas desde ``gold.json``) y comprueba que el auditor la
nombra. Las relaciones v0.7 siguen cubiertas en ``tests/test_audit_flujo.py``.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from audit_fixtures import auditar, edit_json, edit_yaml, fila

from revisia.schemas.artifacts import JOURNAL_PATHS


def _json(rel: str, fn: Callable) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        edit_json(run / rel, fn)

    return _editar


def _counts(**cambios) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        edit_yaml(run / "manifest.yml", lambda m: m["counts"].update(cambios))

    return _editar


def _csv(clave: str, valor: str) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        path = run / "deliverable" / "interop" / "prisma2020_flow.csv"
        rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
        header = rows[0]
        for row in rows[1:]:
            if row[header.index("data")] == clave:
                row[header.index("n")] = valor
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(rows)
        path.write_text(buf.getvalue(), encoding="utf-8")

    return _editar


def _jsonl(rel: str, fn: Callable[[list[dict]], None]) -> Callable[[Path], None]:
    def _editar(run: Path) -> None:
        path = run / rel
        entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        fn(entries)
        text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
        path.write_text(text, encoding="utf-8")

    return _editar


def _quitar_ultimo(items: list) -> None:
    del items[-1]


def _no_disponible(rows: list[dict]) -> None:
    rows[0].update(available=False, reason="no_disponible", text_file=None, text_sha256=None)


def _invertir_origen(reports: list[dict]) -> None:
    for report in reports:
        report["reason_source"] = "ai" if report["reason_source"] == "human" else "human"


def _cambiar_respuesta(entries: list[dict]) -> None:
    entries[0]["metas"][0]["response_sha256"] = "0" * 64


def _quitar_un_voto(entries: list[dict]) -> None:
    del entries[0]["metas"][-1]


def _id_repetido(records: list[dict]) -> None:
    records[1]["record_id"] = records[0]["record_id"]


def _recortar_manifiesto(manifest: dict) -> None:
    del manifest["llm_calls"][-1]


def _rationale(decisions: list[dict]) -> None:
    decisions[0]["votes"][0]["rationale"] = "editado a mano"


def _campo_extraido(extractions: dict) -> None:
    primera = next(iter(extractions.values()))
    primera["extractor"] = "human:editora"


def _invertir_gold(gold: dict) -> None:
    gold["10.1000/cocina"] = True


RELACIONES_OLA1 = [
    pytest.param(
        _json("01_search/records.json", _quitar_ultimo),
        "1 · identified == len(01_search/records.json)",
        id="registros-de-la-busqueda",
    ),
    pytest.param(
        _json("01_search/records.json", lambda r: r[0].update(source_db="Crossref")),
        "1 · identified_by_source == Counter(source_db) de records.json",
        id="fuentes-de-la-busqueda",
    ),
    pytest.param(
        _json("02_dedup/dedup.json", lambda d: d.update(n_in=8)),
        "4 · dedup.n_in == identified",
        id="dedup-n-in",
    ),
    pytest.param(
        _json("02_dedup/dedup.json", lambda d: d.update(duplicates=[])),
        "4 · n_in − n_out == len(duplicates) == duplicates_removed",
        id="dedup-duplicados",
    ),
    pytest.param(
        _json("02_dedup/records.json", _id_repetido),
        "4 · ids de 02_dedup/records.json únicos",
        id="dedup-ids-repetidos",
    ),
    pytest.param(
        _json("03_screening/decisions.json", lambda d: d.reverse()),
        "5 · 03_screening/decisions.json en el orden de 02_dedup/records.json",
        id="orden-de-ta",
    ),
    pytest.param(
        _counts(fulltext_sought=5), "6 · fulltext_sought == screened − excluded_ta", id="sought"
    ),
    pytest.param(
        _counts(fulltext_not_retrieved=1),
        "8 · fulltext_assessed == fulltext_sought − fulltext_not_retrieved",
        id="no-recuperados",
    ),
    pytest.param(
        _json("04_fulltext/retrieval.json", _no_disponible),
        "7 · retrieved ⇔ retrieval.available ⇔ un voto",
        id="no-recuperado-cribado-por-ia",
    ),
    pytest.param(
        _json("04_fulltext/excluded.json", lambda r: r.clear()),
        "9 · excluded_ft == len(04_fulltext/excluded.json)",
        id="16b-vacia",
    ),
    pytest.param(
        _json("04_fulltext/excluded.json", lambda r: r[0].update(reason="otra razón")),
        "9 · ft_exclusion_reasons == Counter(reason) de excluded.json",
        id="16b-razones",
    ),
    pytest.param(
        _json("04_fulltext/excluded.json", _invertir_origen),
        "9 · reason_source == human ⇔ human_label == exclude",
        id="16b-origen",
    ),
    pytest.param(
        _counts(excluded_ft_ai=5),
        "9 · excluded_ft_human + excluded_ft_ai == excluded_ft",
        id="ft-humano-ia",
    ),
    pytest.param(
        _json("04_fulltext/decisions.json", lambda d: d[0].update(final_label="unclear")),
        "10 · included == #(final FT == include)",
        id="incluidos-ft",
    ),
    pytest.param(_csv("dbr_sought_reports", "9"), "11 · CSV dbr_sought_reports", id="csv-sought"),
    pytest.param(
        _csv("dbr_notretrieved_reports", "2"),
        "11 · CSV dbr_notretrieved_reports",
        id="csv-no-recuperados",
    ),
    pytest.param(
        _jsonl(JOURNAL_PATHS["screening_ta"], _cambiar_respuesta),
        "12 · metas de 03_screening/journal.jsonl en llm_calls.jsonl",
        id="meta-que-no-esta-en-llm-calls",
    ),
    pytest.param(
        _jsonl(JOURNAL_PATHS["screening_ta"], _quitar_un_voto),
        "12 · llamadas por línea en 03_screening/journal.jsonl",
        id="miembros-por-linea",
    ),
    pytest.param(
        _json("03_screening/decisions.json", _rationale),
        "13 · 03_screening/decisions.json == una línea de 03_screening/journal.jsonl",
        id="consolidado-ta",
    ),
    pytest.param(
        _json("05_extraction/extractions.json", _campo_extraido),
        "13 · 05_extraction/extractions.json == una línea de 05_extraction/journal.jsonl",
        id="consolidado-extraccion",
    ),
    pytest.param(
        lambda run: edit_yaml(run / "manifest.yml", _recortar_manifiesto),
        "§4.3 · manifest.llm_calls == líneas de llm_calls.jsonl",
        id="manifiesto-vs-llm-calls",
    ),
    pytest.param(
        _json("03_screening/gold.json", _invertir_gold),
        "§9.3 · matriz == recálculo desde decisions.json y gold.json",
        id="metricas-desde-gold",
    ),
]


@pytest.mark.parametrize(("romper", "relacion"), RELACIONES_OLA1)
def test_arithmetic_ola1_cada_relacion_rota_falla(corrida, romper, relacion: str) -> None:
    romper(corrida)
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "FAIL"
    assert relacion in arithmetic.detail


def test_arithmetic_corrida_de_la_ola_1_pasa_sin_relaciones_v07(corrida) -> None:
    arithmetic = fila(auditar(corrida), "arithmetic")
    assert arithmetic.status == "PASS"
    assert "v0.7" not in arithmetic.detail
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_aritmetica_ola1.py -v`
Expected: FAIL en los 22 casos parametrizados (`arithmetic` no ve las relaciones de la Ola 1: PASS o el nombre de la relación no aparece) y en `test_arithmetic_corrida_de_la_ola_1_pasa_sin_relaciones_v07`.

- [ ] **Step 3: `checks_flow.py`**

Sustituir el contenido completo de `revisia/audit/checks_flow.py` por:

```python
"""Checks del flujo PRISMA: ``stage_artifacts``, ``arithmetic``, ``exclusions``, ``deliverable``.

``arithmetic`` verifica las relaciones entre artefactos de la spec 2026-10-04
§4.4 más las de §9.3: la reconstrucción C3 declaraba 120 identificados con
140 llamadas para 120 registros cribados por dos modelos, y el auditor anterior
no sumaba nada. Con ``run.json`` (corrida de la Ola 1) se aplican las 13
primeras relaciones de §4.4 completas, con búsqueda, dedup, recuperación,
diarios y lista 16b. Sin ``run.json`` (corrida anterior a la Ola 1) se aplican
las relaciones v0.7 del embudo (un ``unclear`` a texto completo contaba como
incluido): esa corrida ya no es publicable (D13), pero el diagnóstico sigue
siendo útil.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.config import STAGES
from revisia.exclusions import compute_exclusion_breakdown
from revisia.extraction_agreement import select_double_extraction_subset
from revisia.llm.ensemble import recall_biased_label
from revisia.metrics import confusion, kappa_from_matrix, mcc, wmcc
from revisia.schemas.artifacts import JOURNAL_PATHS
from revisia.schemas.records import SearchRecord

TA = "03_screening/decisions.json"
FT = "04_fulltext/decisions.json"
CSV = "deliverable/interop/prisma2020_flow.csv"
_MAX = 6
# Campos que el humano (o el gate) añade a una decisión; el diario guarda la
# propuesta de la IA sin ellos (relación 13 de §4.4).
_HUMAN_FIELDS = ("human_label", "final_label", "human_reason", "human_actor")

# Artefactos que toda etapa alcanzada deja en disco (spec §4.2).
STAGE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "screening_ta": (TA,),
    "screening_ft": (FT, "03_screening/exclusions.json"),
    "extraccion": ("05_extraction/extractions.json",),
    "rob": ("07_rob/assessments.json",),
    "sintesis": ("06_synthesis/verification.json",),
    "reporte": ("manifest.yml",),
}
# Artefactos de la Ola 1 (spec §4.2): solo se exigen con run.json.
STAGE_ARTIFACTS_OLA1: dict[str, tuple[str, ...]] = {
    "protocolo": ("run.json", "00_protocol/protocol.yml"),
    "busqueda": ("01_search/records.json", "01_search/log.json"),
    "dedup": ("02_dedup/records.json", "02_dedup/dedup.json"),
    "screening_ta": ("03_screening/journal.jsonl", "llm_calls.jsonl"),
    "screening_ft": (
        "04_fulltext/retrieval.jsonl",
        "04_fulltext/retrieval.json",
        "04_fulltext/excluded.json",
    ),
    "sintesis": ("06_synthesis/journal.jsonl", "06_synthesis/verification.jsonl"),
}
# Artefactos que existen si el manifiesto registra su copia.
CONDITIONAL_ARTIFACTS: dict[str, tuple[str, str]] = {
    "screening_metrics": ("screening_ta", "03_screening/metrics.json"),
    "extraction_agreement": ("extraccion", "05_extraction/agreement.json"),
    "meta_analysis": ("rob", "08_meta/meta_analysis.json"),
}
# Copias del manifiesto que deben coincidir con su fichero (§9.3).
MANIFEST_COPIES: dict[str, str] = {
    "exclusions": "03_screening/exclusions.json",
    "screening_metrics": "03_screening/metrics.json",
    "verification": "06_synthesis/verification.json",
    "risk_of_bias": "07_rob/assessments.json",
    "extraction_agreement": "05_extraction/agreement.json",
    "meta_analysis": "08_meta/meta_analysis.json",
}

DELIVERABLE_FILES: tuple[str, ...] = (
    "documento.md",
    "prisma_flow.md",
    "metodologia.md",
    "tabla_extraccion.md",
    "risk_of_bias.md",
    "referencias.bib",
    "checklist_2020.md",
    "checklist_traice.md",
    "checklist_s.md",
    "checklist_abstracts.md",
    "interop/prisma2020_flow.csv",
)


def _limitar(items: list[str]) -> str:
    more = len(items) - _MAX
    return "; ".join(items[:_MAX]) + (f" (+{more} más)" if more > 0 else "")


def included_ids(ctx: AuditContext) -> list[str] | None:
    """Incluidos según las decisiones a texto completo (``None`` si no se leen).

    Desde la Ola 1, ``final_label == include``: un ``unclear`` lo resuelve un
    humano (D1). Relaciones v0.7 (sin ``run.json``): ``include`` o ``unclear``.
    """
    ft = ctx.art.artifact(FT)
    if not ft.ok:
        return None
    labels = {"include", "unclear"} if ctx.run_info is None else {"include"}
    return [d.record_id for d in ft.value if d.final_label in labels]


def _journals_ola1(ctx: AuditContext) -> list[tuple[str, str]]:
    """Diarios que existen si su etapa tuvo trabajo: FT con algún recuperado,
    extracción y RoB con algún incluido, 2.º extractor con doble extracción."""
    required: list[tuple[str, str]] = []
    reached = ctx.state.reached
    ft = ctx.art.artifact(FT)
    if "screening_ft" in reached and ft.ok and any(d.votes for d in ft.value):
        required.append(("screening_ft", "04_fulltext/journal.jsonl"))
    extractions = ctx.art.artifact("05_extraction/extractions.json")
    if extractions.ok and extractions.value:
        if "extraccion" in reached:
            required.append(("extraccion", "05_extraction/journal.jsonl"))
        if "rob" in reached:
            required.append(("rob", "07_rob/journal.jsonl"))
    if "extraccion" in reached and ctx.art.exists("05_extraction/agreement.json"):
        required.append(("extraccion", "05_extraction/journal_2.jsonl"))
    return required


def check_stage_artifacts(ctx: AuditContext) -> Verdict:
    """PRISMA 16/27: cada etapa alcanzada dejó sus artefactos (§4.2)."""
    required: list[tuple[str, str]] = []
    for stage, rels in STAGE_ARTIFACTS.items():
        if stage in ctx.state.reached:
            required += [(stage, rel) for rel in rels]
    manifest = ctx.manifest_dict or {}
    for key, (stage, rel) in CONDITIONAL_ARTIFACTS.items():
        if key in manifest and stage in ctx.state.reached:
            required.append((stage, rel))
    if ctx.art.exists("run.json"):
        for stage, rels in STAGE_ARTIFACTS_OLA1.items():
            if stage in ctx.state.reached:
                required += [(stage, rel) for rel in rels]
        required += _journals_ola1(ctx)
    missing = [f"{stage}: {rel}" for stage, rel in required if not ctx.art.exists(rel)]
    if missing:
        return "FAIL", f"faltan artefactos de etapas alcanzadas: {_limitar(missing)}."
    stages = sorted({stage for stage, _ in required}, key=STAGES.index)
    return "PASS", (
        f"{len(required)} artefactos de {len(stages)} etapas alcanzadas presentes "
        f"({', '.join(stages)})."
    )


@dataclass(frozen=True)
class _Relation:
    name: str
    ok: bool | None  # None = no verificable
    detail: str = ""


class _Relations:
    """Acumula relaciones verificadas, rotas y no verificables."""

    def __init__(self) -> None:
        self.items: list[_Relation] = []

    def eq(self, name: str, left: Any, right: Any) -> None:
        self.items.append(_Relation(name, left == right, f"{left!r} ≠ {right!r}"))

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.items.append(_Relation(name, ok, detail))

    def unverifiable(self, name: str, why: str) -> None:
        self.items.append(_Relation(name, None, why))

    def when(self, ready: bool, name: str, why: str, fn: Callable[[], None]) -> None:
        if ready:
            fn()
        else:
            self.unverifiable(name, why)


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, abs_tol=1e-9)


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def _read_csv(ctx: AuditContext) -> dict[str, str] | None:
    loaded = ctx.art.text(CSV)
    if not loaded.ok:
        return None
    try:
        rows = list(csv.DictReader(io.StringIO(loaded.value)))
    except csv.Error:
        return None
    return {row.get("data", ""): row.get("n", "") for row in rows}


def _screeners(ctx: AuditContext) -> list[str] | None:
    if ctx.protocol is None:
        return None
    try:
        return [f"{c.provider}:{c.model}" for c in ctx.protocol.screeners_for("screening_ta")]
    except KeyError:
        return None


def _value(loaded: Any) -> Any:
    return loaded.value if loaded.ok else None


def _funnel(ctx: AuditContext, rel: _Relations) -> None:
    counts = _value(ctx.manifest_section("counts"))
    ta, ft = _value(ctx.art.artifact(TA)), _value(ctx.art.artifact(FT))
    sin_ta, sin_ft = f"{TA} ausente o inválido", f"{FT} ausente o inválido"
    if counts is None:
        rel.unverifiable("conteos del embudo", "manifest.counts ausente o inválido")
        return
    if counts.identified_by_source:
        rel.eq(
            "1 · Σ identified_by_source == identified",
            sum(counts.identified_by_source.values()),
            counts.identified,
        )
    rel.eq(
        "4 · screened == identified − duplicates_removed − removed_*",
        counts.screened,
        counts.identified
        - counts.duplicates_removed
        - counts.removed_automation
        - counts.removed_other,
    )
    rel.eq(
        "10 · included == fulltext_assessed − excluded_ft",
        counts.included,
        counts.fulltext_assessed - counts.excluded_ft,
    )
    rel.eq(
        "9 · Σ ft_exclusion_reasons == excluded_ft",
        sum(counts.ft_exclusion_reasons.values()),
        counts.excluded_ft,
    )
    if counts.excluded_ta_human is not None and counts.excluded_ta_ai is not None:
        rel.eq(
            "6 · excluded_ta_human + excluded_ta_ai == excluded_ta",
            counts.excluded_ta_human + counts.excluded_ta_ai,
            counts.excluded_ta,
        )
    if ctx.run_info is None:
        rel.eq(
            "v0.7 · excluded_ta + fulltext_assessed == screened",
            counts.excluded_ta + counts.fulltext_assessed,
            counts.screened,
        )
    else:
        _counts_v08(ctx, rel, counts)
    rel.when(
        ta is not None, "relaciones del cribado T/A", sin_ta, lambda: _ta(ctx, rel, counts, ta)
    )
    if ta is not None and ft is not None:
        if ctx.run_info is None:
            _ft_v07(ctx, rel, counts, ta, ft)
        else:
            _ft_v08(ctx, rel, counts, ta, ft)
    else:
        rel.unverifiable("relaciones del texto completo", sin_ft if ft is None else sin_ta)


def _counts_v08(ctx: AuditContext, rel: _Relations, counts: Any) -> None:
    """Relaciones 1, 4, 6, 8 y 9 con los conteos de la Ola 1 y la búsqueda/dedup."""
    rel.eq(
        "6 · fulltext_sought == screened − excluded_ta",
        counts.fulltext_sought,
        counts.screened - counts.excluded_ta,
    )
    rel.eq(
        "8 · fulltext_assessed == fulltext_sought − fulltext_not_retrieved",
        counts.fulltext_assessed,
        counts.fulltext_sought - counts.fulltext_not_retrieved,
    )
    rel.eq(
        "9 · excluded_ft_human + excluded_ft_ai == excluded_ft",
        counts.excluded_ft_human + counts.excluded_ft_ai,
        counts.excluded_ft,
    )
    records = _value(ctx.art.artifact("01_search/records.json"))
    if records is None:
        rel.unverifiable("1 · 01_search/records.json", "ausente o inválido")
    else:
        rel.eq("1 · identified == len(01_search/records.json)", counts.identified, len(records))
        rel.eq(
            "1 · identified_by_source == Counter(source_db) de records.json",
            dict(sorted(counts.identified_by_source.items())),
            dict(sorted(Counter(r.source_db for r in records).items())),
        )
    dedup = _value(ctx.art.artifact("02_dedup/dedup.json"))
    deduped = _value(ctx.art.artifact("02_dedup/records.json"))
    if dedup is None or deduped is None:
        rel.unverifiable("4 · 02_dedup/", "dedup.json o records.json ausente o inválido")
        return
    rel.eq("4 · dedup.n_in == identified", dedup.n_in, counts.identified)
    rel.eq(
        "4 · n_in − n_out == len(duplicates) == duplicates_removed",
        (dedup.n_in - dedup.n_out, len(dedup.duplicates)),
        (counts.duplicates_removed, counts.duplicates_removed),
    )
    rel.eq(
        "4 · n_out == screened == len(02_dedup/records.json)",
        (dedup.n_out, len(deduped)),
        (counts.screened, counts.screened),
    )
    ids = [r.record_id for r in deduped]
    rel.check("4 · ids de 02_dedup/records.json únicos", len(ids) == len(set(ids)))


def _ta(ctx: AuditContext, rel: _Relations, counts: Any, ta: list[Any]) -> None:
    rel.eq(f"5 · len({TA}) == screened", len(ta), counts.screened)
    rel.eq(
        "6 · excluded_ta == #(final T/A == exclude)",
        counts.excluded_ta,
        sum(1 for d in ta if d.final_label == "exclude"),
    )
    bad_ensemble = [
        d.record_id
        for d in ta
        if d.votes and d.ensemble_label != recall_biased_label([v.label for v in d.votes])
    ]
    rel.check(
        "5 · ensemble_label == recall_biased_label(votes)",
        not bad_ensemble,
        ", ".join(bad_ensemble),
    )
    bad_final = [d.record_id for d in ta if d.final_label != (d.human_label or d.ensemble_label)]
    rel.check(
        "5 · final_label == human_label or ensemble_label", not bad_final, ", ".join(bad_final)
    )
    screeners = _screeners(ctx)
    if screeners is None:
        rel.unverifiable("§9.3 · votos de los screeners T/A", "protocolo no legible")
    else:
        bad_votes = [
            d.record_id
            for d in ta
            if len(d.votes) != len(screeners) or any(v.model not in screeners for v in d.votes)
        ]
        rel.check(
            "§9.3 · un voto por screener T/A configurado",
            not bad_votes,
            f"{', '.join(bad_votes)} (screeners: {', '.join(screeners)})",
        )
    if ctx.run_info is not None:
        deduped = _value(ctx.art.artifact("02_dedup/records.json"))
        if deduped is not None:
            rel.eq(
                f"5 · {TA} en el orden de 02_dedup/records.json",
                [d.record_id for d in ta],
                [r.record_id for r in deduped],
            )
        rel.eq(
            "6 · fulltext_sought == #(final T/A ∈ {include, unclear})",
            counts.fulltext_sought,
            sum(1 for d in ta if d.final_label in {"include", "unclear"}),
        )


def _passed(ta: list[Any]) -> list[str]:
    return [d.record_id for d in ta if d.final_label in {"include", "unclear"}]


def _ft_v07(ctx: AuditContext, rel: _Relations, counts: Any, ta: list[Any], ft: list[Any]) -> None:
    passed = set(_passed(ta))
    rel.check(
        "7 · ids de 04_fulltext == pasan T/A",
        {d.record_id for d in ft} == passed,
        f"{sorted({d.record_id for d in ft} ^ passed)}",
    )
    rel.eq(f"v0.7 · len({FT}) == fulltext_assessed", len(ft), counts.fulltext_assessed)
    rel.eq(
        "9 · excluded_ft == #(final FT == exclude)",
        counts.excluded_ft,
        sum(1 for d in ft if d.final_label == "exclude"),
    )
    bad = [
        d.record_id
        for d in ft
        if len(d.votes) != 1 or d.final_label != (d.human_label or d.ensemble_label)
    ]
    rel.check("v0.7 · un voto FT y final == human or ensemble", not bad, ", ".join(bad))
    rel.eq(
        "v0.7 · included == #(final FT ∈ {include, unclear})",
        counts.included,
        len(included_ids(ctx) or []),
    )


def _ft_v08(ctx: AuditContext, rel: _Relations, counts: Any, ta: list[Any], ft: list[Any]) -> None:
    """Relaciones 7, 8, 9 y 10 con recuperación, rescates y la lista 16b."""
    passed = _passed(ta)
    rel.check(
        "7 · ids de 04_fulltext == pasan T/A",
        [d.record_id for d in ft] == passed,
        f"{sorted({d.record_id for d in ft} ^ set(passed))}",
    )
    retrieval = _value(ctx.art.artifact("04_fulltext/retrieval.json"))
    if retrieval is None:
        rel.unverifiable("7 · retrieved ⇔ available ⇔ un voto", "04_fulltext/retrieval.json")
    else:
        available = {row.record_id: row.available for row in retrieval}
        bad = [
            d.record_id
            for d in ft
            if len(
                {d.fulltext_status == "retrieved", available.get(d.record_id), len(d.votes) == 1}
            )
            != 1
        ]
        rel.check("7 · retrieved ⇔ retrieval.available ⇔ un voto", not bad, ", ".join(bad))
    not_retrieved = [d for d in ft if d.fulltext_status == "not_retrieved"]
    rel.eq(
        "8 · fulltext_not_retrieved == #(no recuperado sin humano)",
        counts.fulltext_not_retrieved,
        sum(1 for d in not_retrieved if d.human_label is None),
    )
    rel.eq(
        "8 · fulltext_rescued == #(no recuperado con humano)",
        counts.fulltext_rescued,
        sum(1 for d in not_retrieved if d.human_label is not None),
    )
    rel.eq(
        "8 · fulltext_assessed == #(final FT ≠ null)",
        counts.fulltext_assessed,
        sum(1 for d in ft if d.final_label is not None),
    )
    excluded = [d for d in ft if d.final_label == "exclude"]
    rel.eq("9 · excluded_ft == #(final FT == exclude)", counts.excluded_ft, len(excluded))
    reports = _value(ctx.art.artifact("04_fulltext/excluded.json"))
    if reports is None:
        rel.unverifiable("9 · lista 16b", "04_fulltext/excluded.json ausente o inválido")
    else:
        rel.eq(
            "9 · excluded_ft == len(04_fulltext/excluded.json)", counts.excluded_ft, len(reports)
        )
        rel.eq(
            "9 · ft_exclusion_reasons == Counter(reason) de excluded.json",
            dict(sorted(counts.ft_exclusion_reasons.items())),
            dict(sorted(Counter(r.reason for r in reports).items())),
        )
        human = {d.record_id for d in excluded if d.human_label == "exclude"}
        bad = [
            r.record_id for r in reports if (r.reason_source == "human") != (r.record_id in human)
        ]
        rel.check("9 · reason_source == human ⇔ human_label == exclude", not bad, ", ".join(bad))
    rel.eq(
        "10 · included == #(final FT == include)",
        counts.included,
        sum(1 for d in ft if d.final_label == "include"),
    )


def _included_artifacts(ctx: AuditContext, rel: _Relations) -> None:
    ids = included_ids(ctx)
    if ids is None:
        rel.unverifiable("10 · artefactos de los incluidos", f"{FT} ausente o inválido")
        return
    for path, label in (
        ("05_extraction/extractions.json", "extracciones"),
        ("07_rob/assessments.json", "evaluaciones"),
    ):
        loaded = ctx.art.artifact(path)
        if not loaded.ok:
            rel.unverifiable(f"10 · claves de {path}", f"{path} ausente o inválido")
            continue
        rel.check(
            f"10 · claves de {path} == incluidos",
            set(loaded.value) == set(ids),
            f"{label}: {sorted(set(loaded.value) ^ set(ids))}",
        )
        bad = [k for k, v in loaded.value.items() if v.study_id != k]
        rel.check(f"10 · study_id == clave en {path}", not bad, ", ".join(bad))
    assessments = ctx.art.artifact("07_rob/assessments.json")
    if assessments.ok and ctx.protocol is not None:
        tools = sorted({a.tool for a in assessments.value.values()})
        rel.check(
            "§9.3 · assessment.tool == protocol.rob_tool",
            all(t == ctx.protocol.rob_tool for t in tools),
            f"{tools} ≠ {ctx.protocol.rob_tool}",
        )
    agreement = ctx.art.artifact("05_extraction/agreement.json")
    if agreement.ok:
        subset = select_double_extraction_subset([SearchRecord(record_id=i, title="") for i in ids])
        rel.eq(
            "§9.3 · extraction_agreement.n_studies == subconjunto de doble extracción",
            agreement.value.n_studies,
            len(subset),
        )
    exclusions = ctx.art.artifact("03_screening/exclusions.json")
    counts = ctx.manifest_section("counts")
    if exclusions.ok and counts.ok:
        rel.eq(
            "10 · exclusions.total_excluded == excluded_ta + excluded_ft",
            exclusions.value.total_excluded,
            counts.value.excluded_ta + counts.value.excluded_ft,
        )


def _csv(ctx: AuditContext, rel: _Relations) -> None:
    counts = ctx.manifest_section("counts")
    values = _read_csv(ctx)
    if values is None or not counts.ok:
        rel.unverifiable("11 · CSV PRISMA2020", f"{CSV} o manifest.counts ilegible")
        return
    c = counts.value
    v07 = ctx.run_info is None  # v0.7: buscados = evaluados, no recuperados = 0
    expected = {
        "database_results": c.identified,
        "duplicates": c.duplicates_removed,
        "records_screened": c.screened,
        "records_excluded": c.excluded_ta,
        "dbr_sought_reports": c.fulltext_assessed if v07 else c.fulltext_sought,
        "dbr_notretrieved_reports": 0 if v07 else c.fulltext_not_retrieved,
        "dbr_assessed": c.fulltext_assessed,
        "new_studies": c.included,
    }
    for key, value in expected.items():
        rel.eq(f"11 · CSV {key}", values.get(key), str(value))


def _calls(ctx: AuditContext, rel: _Relations) -> None:
    manifest = ctx.manifest_dict or {}
    calls = ctx.llm_calls
    rel.eq(
        "§9.3 · models_used == modelos de llm_calls",
        sorted(manifest.get("models_used") or []),
        sorted({f"{c.get('provider')}:{c.get('model')}" for c in calls}),
    )
    rel.eq(
        "§9.3 · deterministic_token_level == all(deterministic)",
        manifest.get("deterministic_token_level"),
        all(c.get("deterministic") is True for c in calls) if calls else True,
    )
    if ctx.art.exists("llm_calls.jsonl"):
        rel.check(
            "§4.3 · manifest.llm_calls == líneas de llm_calls.jsonl",
            manifest.get("llm_calls") == calls,
            "distintas (o en otro orden)",
        )
    counts = ctx.manifest_section("counts")
    if not counts.ok:
        rel.unverifiable("§9.3 · cota inferior de llamadas", "manifest.counts ilegible")
        return
    c = counts.value
    members = len(_screeners(ctx) or [None])
    agreement = ctx.art.artifact("05_extraction/agreement.json")
    doubles = agreement.value.n_studies if agreement.ok else 0
    floor = (
        c.screened * members
        + (c.fulltext_assessed - c.fulltext_rescued)
        + 2 * c.included
        + doubles
        + 1
    )
    rel.check(
        "§9.3 · llamadas ≥ cota inferior de las decisiones",
        len(calls) >= floor,
        f"{len(calls)} llamadas < {floor} = {c.screened}·{members} + "
        f"{c.fulltext_assessed - c.fulltext_rescued} + 2·{c.included} + {doubles} + 1",
    )


def _metrics(ctx: AuditContext, rel: _Relations) -> None:
    loaded = ctx.art.artifact("03_screening/metrics.json")
    if not loaded.present:
        return
    if not loaded.ok:
        rel.unverifiable("§9.3 · métricas desde la matriz", "metrics.json inválido")
        return
    m = loaded.value
    tp, fp, fn, tn = m.tp, m.fp, m.fn, m.tn
    rel.eq("§9.3 · n == tp+fp+fn+tn", m.n, tp + fp + fn + tn)
    recomputed = {
        "recall": _ratio(tp, tp + fn),
        "lost_evidence": _ratio(fn, tp + fn),
        "precision": _ratio(tp, tp + fp),
        "mcc": mcc(tp, fp, fn, tn),
        "wmcc": wmcc(tp, fp, fn, tn, fn_weight=m.wmcc_fn_weight),
        "cohen_kappa": kappa_from_matrix(tp, fp, fn, tn),
    }
    for name, value in recomputed.items():
        declared = getattr(m, name)
        rel.check(
            f"§9.3 · {name} recalculado desde la matriz",
            _close(declared, value),
            f"{declared!r} ≠ {value!r}",
        )
    if ctx.protocol is not None:
        rel.eq(
            "§9.3 · wmcc_fn_weight == protocolo",
            m.wmcc_fn_weight,
            float(ctx.protocol.thresholds.get("wmcc_fn_weight", 10.0)),
        )
    if ctx.run_info is None:
        return
    gold, ta = ctx.art.artifact("03_screening/gold.json"), ctx.art.artifact(TA)
    if not (gold.ok and ta.ok):
        rel.unverifiable(
            "§9.3 · métricas desde decisions.json y gold.json", "gold.json o decisions.json"
        )
        return
    by_id = {d.record_id: d for d in ta.value}
    pairs = [
        (by_id[rid].ensemble_label != "exclude", truth)
        for rid, truth in gold.value.items()
        if rid in by_id
    ]
    matrix = confusion([p for p, _ in pairs], [t for _, t in pairs])
    rel.eq(
        "§9.3 · matriz == recálculo desde decisions.json y gold.json (ensemble_label, D6)",
        (tp, fp, fn, tn),
        matrix,
    )


def _copies(ctx: AuditContext, rel: _Relations) -> None:
    manifest = ctx.manifest_dict or {}
    for key, path in MANIFEST_COPIES.items():
        loaded = ctx.art.json(path)
        if key not in manifest and not loaded.present:
            continue
        if key not in manifest:
            rel.check(f"§9.3 · copia `{key}` del manifiesto", False, f"{path} sin copia")
        elif not loaded.present:
            rel.check(f"§9.3 · copia `{key}` del manifiesto", False, f"{path} ausente")
        elif not loaded.ok:
            rel.unverifiable(f"§9.3 · copia `{key}` del manifiesto", f"{path} ilegible")
        else:
            rel.check(
                f"§9.3 · copia `{key}` del manifiesto == {path}",
                manifest[key] == loaded.value,
                "distinta",
            )


def _key(item: Any) -> str:
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def _expected_metas(stage: str, entry: dict, members: int | None) -> set[int] | None:
    """Llamadas que debe llevar una línea de diario (relación 12)."""
    if stage == "screening_ta":
        return {members} if members else None
    if stage == "fulltext_retrieval":
        return {0}
    if stage == "verificacion":
        checks = (entry.get("output") or {}).get("checks") or []
        return {0, len(checks)}
    return {1}


def _journals(ctx: AuditContext, rel: _Relations) -> None:
    """Relación 12: cada meta de cada diario está, idéntica, en llm_calls.jsonl."""
    calls = {_key(c) for c in ctx.llm_calls}
    members = len(_screeners(ctx) or []) or None
    for stage, path in JOURNAL_PATHS.items():
        loaded = ctx.art.jsonl(path)
        if not loaded.present or loaded.value is None:
            continue
        missing: list[str] = []
        wrong_count: list[str] = []
        for number, entry in loaded.value:
            if not isinstance(entry, dict):
                continue
            metas = entry.get("metas") or []
            for meta in metas:
                tagged = meta.get("stage") == stage and meta.get("record_id") == entry.get(
                    "record_id"
                )
                if _key(meta) not in calls or not tagged:
                    missing.append(f"línea {number}")
            expected = _expected_metas(stage, entry, members)
            if expected is not None and len(metas) not in expected:
                wrong_count.append(f"línea {number}: {len(metas)} llamadas")
        rel.check(f"12 · metas de {path} en llm_calls.jsonl", not missing, ", ".join(missing))
        rel.check(f"12 · llamadas por línea en {path}", not wrong_count, ", ".join(wrong_count))


def _consolidated(ctx: AuditContext, rel: _Relations) -> None:
    """Relación 13: cada consolidado coincide, sin campos humanos, con su diario."""

    def _strip(item: Any) -> str:
        data = json.loads(json.dumps(item, ensure_ascii=False))
        if isinstance(data, dict):
            for name in _HUMAN_FIELDS:
                data.pop(name, None)
        return _key(data)

    def _compare(journal: str, items: dict[str, Any], label: str) -> None:
        loaded = ctx.art.jsonl(journal)
        if not items:
            return
        if not loaded.present or loaded.value is None:
            rel.unverifiable(f"13 · {label} == {journal}", "diario ausente")
            return
        outputs: dict[str, set[str]] = {}
        for _, entry in loaded.value:
            if isinstance(entry, dict):
                outputs.setdefault(entry.get("record_id"), set()).add(_strip(entry.get("output")))
        bad = [rid for rid, item in items.items() if _strip(item) not in outputs.get(rid, set())]
        rel.check(f"13 · {label} == una línea de {journal}", not bad, ", ".join(bad))

    def _load(path: str) -> Any:
        return ctx.art.json(path).value if ctx.art.json(path).ok else None

    ta = _load(TA)
    if isinstance(ta, list):
        _compare(JOURNAL_PATHS["screening_ta"], {d["record_id"]: d for d in ta}, TA)
    ft = _load(FT)
    if isinstance(ft, list):
        retrieved = {d["record_id"]: d for d in ft if d.get("fulltext_status") == "retrieved"}
        _compare(JOURNAL_PATHS["screening_ft"], retrieved, FT)
    rows = _load("04_fulltext/retrieval.json")
    if isinstance(rows, list):
        outcomes = {r["record_id"]: {k: v for k, v in r.items() if k != "record_id"} for r in rows}
        _compare(JOURNAL_PATHS["fulltext_retrieval"], outcomes, "04_fulltext/retrieval.json")
    for path, stage in (
        ("05_extraction/extractions.json", "extraccion"),
        ("07_rob/assessments.json", "rob"),
    ):
        data = _load(path)
        if isinstance(data, dict):
            _compare(JOURNAL_PATHS[stage], data, path)
    verification = _load("06_synthesis/verification.json")
    if isinstance(verification, dict):
        _compare(
            JOURNAL_PATHS["verificacion"],
            {"verificacion": verification},
            "06_synthesis/verification.json",
        )


def check_arithmetic(ctx: AuditContext) -> Verdict:
    """PRISMA 16 / trAIce R1: los artefactos cuadran entre sí (§4.4, §9.3)."""
    if ctx.manifest_dict is None:
        return "N/A", "no aplica: el manifiesto no se pudo leer (ver `manifest`)."
    rel = _Relations()
    _funnel(ctx, rel)
    _included_artifacts(ctx, rel)
    _csv(ctx, rel)
    _calls(ctx, rel)
    _metrics(ctx, rel)
    _copies(ctx, rel)
    if ctx.run_info is not None:
        _journals(ctx, rel)
        _consolidated(ctx, rel)

    broken = [f"{r.name}: {r.detail}" for r in rel.items if r.ok is False]
    unverifiable = [f"{r.name} ({r.detail})" for r in rel.items if r.ok is None]
    verified = sum(1 for r in rel.items if r.ok)
    mode = " (relaciones v0.7: corrida sin run.json)" if ctx.run_info is None else ""
    if broken:
        return "FAIL", f"{len(broken)} relación(es) rota(s){mode}: {_limitar(broken)}."
    if unverifiable:
        return "WARN", (
            f"{verified} relaciones verificadas{mode}; no verificables: {_limitar(unverifiable)}."
        )
    return "PASS", f"{verified} relaciones verificadas{mode}."


def check_exclusions(ctx: AuditContext) -> Verdict:
    """trAIce R1: el desglose humano/IA coincide con el recálculo desde las decisiones."""
    loaded = ctx.art.artifact("03_screening/exclusions.json")
    if not loaded.present:
        return "FAIL", "03_screening/exclusions.json ausente: sin desglose humano/IA (trAIce R1)."
    if not loaded.ok:
        return "FAIL", f"03_screening/exclusions.json inválido ({loaded.error})."
    ta, ft = ctx.art.artifact(TA), ctx.art.artifact(FT)
    if not (ta.ok and ft.ok):
        return "FAIL", (
            f"no se puede recalcular el desglose: falta o no valida {TA if not ta.ok else FT}."
        )
    declared = loaded.value
    recomputed = compute_exclusion_breakdown([*ta.value, *ft.value])
    diffs = [
        f"{field} {getattr(declared, field)} ≠ {getattr(recomputed, field)}"
        for field in type(recomputed).model_fields
        if getattr(declared, field) != getattr(recomputed, field)
    ]
    counts = ctx.manifest_section("counts")
    if counts.ok and counts.value.excluded_ta_human is not None:
        ta_only = compute_exclusion_breakdown(ta.value)
        c = counts.value
        if (c.excluded_ta_human, c.excluded_ta_ai) != (ta_only.excluded_human, ta_only.excluded_ai):
            diffs.append(
                f"counts.excluded_ta_human/ai {c.excluded_ta_human}/{c.excluded_ta_ai} ≠ "
                f"{ta_only.excluded_human}/{ta_only.excluded_ai} (solo T/A)"
            )
    if diffs:
        return "FAIL", f"distinto del recálculo desde las decisiones: {'; '.join(diffs)}."
    return "PASS", (
        f"coincide con el recálculo: {recomputed.total_excluded} exclusiones "
        f"({recomputed.excluded_human} humanas, {recomputed.excluded_ai} IA)."
    )


def check_deliverable(ctx: AuditContext) -> Verdict:
    """PRISMA 16/16b/17/18/27: entregable completo y sin ficheros vacíos."""
    required = list(DELIVERABLE_FILES)
    if ctx.art.exists("run.json"):
        required.append("excluidos_texto_completo.md")  # 16b (desde la Ola 1)
    if "meta_analysis" in (ctx.manifest_dict or {}) or ctx.art.exists("08_meta/meta_analysis.json"):
        required.append("meta_analisis.md")
    problems: list[str] = []
    for name in required:
        loaded = ctx.art.text(f"deliverable/{name}")
        if not loaded.present:
            problems.append(f"{name} (falta)")
        elif not loaded.ok or not loaded.value.strip():
            problems.append(f"{name} ({'vacío' if loaded.ok else loaded.error})")
    if problems:
        return "FAIL", f"Entregable incompleto: {', '.join(problems)}."
    return "PASS", f"Entregable completo ({len(required)} artefactos)."
```

- [ ] **Step 4: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_aritmetica_ola1.py tests/test_audit_flujo.py -v`
Expected: PASS (23 nuevos; los 38 de la Tarea 7, sobre la corrida v0.7 y la de la Ola 1, siguen en verde).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, `N_D + 216` recogidos (715), 2 skipped.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 6: Commit**

```bash
git add revisia/audit/checks_flow.py tests/test_audit_aritmetica_ola1.py
git commit -m "feat(audit): aritmética del embudo de la Ola 1 (relaciones 1-13)" -m "Con run.json, arithmetic verifica búsqueda, dedup, recuperación de texto completo, la lista 16b, el CSV PRISMA2020, los diarios contra llm_calls.jsonl y el consolidado contra su diario (relaciones 1-13 de §4.4). Sin run.json sigue con las relaciones v0.7 y lo dice. Spec 2026-10-04 §4.4 y §9.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: HITL por registro, `request_hash`, gate final de la Ola 1, rebaja de `thresholds` (D7) y citas marcadas reales (D8)

**Files:**
- Modify: `revisia/audit/checks_hitl.py` (relación 16 en `ledger`; `hitl` por registro; `check_request_hash`; relaciones 17 y 18 en `final_gate`)
- Modify: `revisia/audit/checks_quality.py` (`thresholds`: WARN cuando todas las exclusiones IA tienen etiqueta humana)
- Modify: `revisia/audit/__init__.py` (registra `request_hash` tras `hitl`)
- Modify: `tests/conftest.py` (corrida con una cita marcada y adjudicada)
- Test: `tests/test_audit_hitl_registro.py` (nuevo)

**Interfaces:**
- Consumes (PR-C/PR-D): `HumanDecision(request_sha256, approved, actor, reason, records: dict[str, RecordLabel], flags: dict[str, FlagReview])`; `GateSummary(stage, action, actor, autonomy, request_sha256, decision_sha256, n_labels, n_flag_reviews, forced_human, timestamp_utc)` (vía `summarize_gates`); `canonical_sha256`, `sha256_text`; entradas `label` (`detail = {from, to, reason, request_sha256, decision_sha256}`), `flag_review` (`target = "flag:<i>"`, `detail = {cited_id, claim, verdict, reason, request_sha256, decision_sha256}`) y `approve`/`reject` (`detail = {request_sha256, decision_sha256}`); solicitudes con `records`, `must_label`, `must_resolve`, `artifact_sha256` (extracción, RoB), `documento_sha256`, `must_adjudicate`, `forced_human`; `manifest.autonomy_effective` y `manifest.final_gate`; `fakes.ScriptedProvider(..., sintesis=...)` y `responder_gate(..., flags=...)` (vía `correr_hasta`).
- Consumes (este plan): `effective_autonomy(ctx)` y `check_ledger` (Tarea 5), `check_hitl` y `check_final_gate` (Tarea 8), `ai_exclusions_without_label` y `check_grounding` (Tarea 9), `_correr` y `etiquetar_auditoria` (Tarea 11).
- Produces (`checks_hitl.py`): `check_request_hash(ctx) -> Verdict`. Fila `request_hash` (`trAIce M8`, siempre aplica; `N/A` sin `run.json`). (`tests/conftest.py`): `SINTESIS_CON_CITA_MARCADA`, `RAZON_FALSO_POSITIVO`, `proveedor_con_cita_marcada(cfg)`, `adjudicar_auditoria(stage, solicitud) -> dict | None`, fixture de sesión `protocolo_con_cita_marcada` (`grounding: existence`), `_corrida_con_cita_marcada` y `corrida_con_cita_marcada`; `_correr` gana `proveedor=` y `etiquetar=`.

Reglas (spec §9.3 "`hitl` en detalle", fase 2; §4.4 relaciones 15-18; D7, D8): `ledger` da FAIL con una tupla `(stage, action, target, decision_sha256)` repetida, con `label`/`flag_review` junto a un `reject` o después de su `approve` (relación 16). `hitl` por registro, con `run.json` y en los gates de cribado aprobados: L (las `label` de la decisión efectiva) = H (`human_label` de `decisions.json`) = D (`records` de `decision.yml`); cada `label` del mismo actor que el `approve`, con `from` = la propuesta de la IA y la razón = `human_reason`; a texto completo en A0 cada recuperado etiquetado, ningún `unclear` sin resolver, exclusión humana con razón, un no recuperado sin rescate humano no tiene `final_label` y un rescate lleva razón. `request_hash` (relación 15): el `request_sha256` de cada solicitud se recalcula desde su contenido y es el de su `decision.yml` y el de cada entrada de la decisión efectiva; `decision.yml` es la decisión registrada (`decision_sha256`) y del mismo actor; los ids de la solicitud son los de `decisions.json`; los artefactos y el documento aprobados tienen el hash de la solicitud. `final_gate`: con citas marcadas, `forced_human` en el manifiesto y en el gate y un `flag_review` humano por cita (relación 17); `run.json` `completed` sin `approve` del reporte (relación 18). `thresholds` (D7): recall bajo el umbral con **todas** las exclusiones IA de T/A etiquetadas por un humano baja a WARN ("decláralo"). `grounding` (D8) se prueba sobre una corrida real cuya síntesis cita `[2019]`: el verificador la marca, el gate final se fuerza a humano y la revisora la adjudica como falso positivo → WARN y publicable; sin su `flag_review`, FAIL.

- [ ] **Step 1: Test que falla — la corrida con una cita marcada (`tests/conftest.py`) y `tests/test_audit_hitl_registro.py`**

En `tests/conftest.py`, sustituir

```python
recuperación de texto completo se inyecta con ``fetch_disponible``: con el FT
estricto (D2) un registro sin texto en abierto no llegaría a extracción.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
```

por

```python
recuperación de texto completo se inyecta con ``fetch_disponible``: con el FT
estricto (D2) un registro sin texto en abierto no llegaría a extracción.

``corrida_con_cita_marcada`` es la misma corrida con una síntesis que cita
``[2019]`` (un año, no un id del corpus): el verificador la marca, el gate
final se fuerza a humano y la revisora la adjudica como falso positivo en
``reporte/decision.yml`` (D8).
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
```

En `tests/conftest.py`, sustituir

```python
    return ScriptedProvider(model=cfg.model, palabras=palabras)


def etiquetar_auditoria(stage: str, solicitud: dict) -> dict | None:
    """La revisora humana de la corrida de auditoría.
```

por

```python
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
```

En `tests/conftest.py`, sustituir

```python
    return {"records": records} if records else None


@pytest.fixture(scope="session")
def protocolo_auditoria(tmp_path_factory: pytest.TempPathFactory) -> Path:
```

por

```python
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
```

En `tests/conftest.py`, sustituir

```python
    return destino


def _correr(
    tmp_path_factory: pytest.TempPathFactory, protocol_dir: Path, *, parar_en: str | None
) -> Path:
    protocol = load_protocol(protocol_dir)
```

por

```python
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


def _correr(
    tmp_path_factory: pytest.TempPathFactory,
    protocol_dir: Path,
    *,
    parar_en: str | None,
    proveedor: Callable[[ProviderConfig], ScriptedProvider] = proveedor_auditoria,
    etiquetar: Callable[[str, dict], dict | None] = etiquetar_auditoria,
) -> Path:
    protocol = load_protocol(protocol_dir)
```

En `tests/conftest.py`, sustituir

```python
    ctx = RunContext(protocol.slug, tmp_path_factory.mktemp("auditoria"), timestamp)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
        result = correr_hasta(
            protocol,
```

por

```python
    ctx = RunContext(protocol.slug, tmp_path_factory.mktemp("auditoria"), timestamp)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pipeline_mod, "build_provider", proveedor)
        result = correr_hasta(
            protocol,
```

En `tests/conftest.py`, sustituir

```python
            search_fn=busqueda_auditoria,
            fetch_fn=fetch_disponible,
            etiquetar=etiquetar_auditoria,
            parar_en=parar_en,
        )
```

por

```python
            search_fn=busqueda_auditoria,
            fetch_fn=fetch_disponible,
            etiquetar=etiquetar,
            parar_en=parar_en,
        )
```

En `tests/conftest.py`, sustituir

```python
    return _correr(tmp_path_factory, protocolo_auditoria, parar_en="screening_ft")


def _copia(origen: Path, tmp_path: Path) -> Path:
    destino = tmp_path / "runs" / origen.name
```

por

```python
    return _correr(tmp_path_factory, protocolo_auditoria, parar_en="screening_ft")


@pytest.fixture(scope="session")
def _corrida_con_cita_marcada(
    tmp_path_factory: pytest.TempPathFactory, protocolo_con_cita_marcada: Path
) -> Path:
    """Corrida completada con una cita marcada y adjudicada por la revisora."""
    return _correr(
        tmp_path_factory,
        protocolo_con_cita_marcada,
        parar_en=None,
        proveedor=proveedor_con_cita_marcada,
        etiquetar=adjudicar_auditoria,
    )


def _copia(origen: Path, tmp_path: Path) -> Path:
    destino = tmp_path / "runs" / origen.name
```

En `tests/conftest.py`, sustituir

```python
    """Copia propia de la corrida en pausa en ``screening_ft``."""
    return _copia(_corrida_en_pausa_ft, tmp_path)
```

por

```python
    """Copia propia de la corrida en pausa en ``screening_ft``."""
    return _copia(_corrida_en_pausa_ft, tmp_path)


@pytest.fixture
def corrida_con_cita_marcada(_corrida_con_cita_marcada: Path, tmp_path: Path) -> Path:
    """Copia propia de la corrida con la cita ``[2019]`` adjudicada."""
    return _copia(_corrida_con_cita_marcada, tmp_path)
```

Crear `tests/test_audit_hitl_registro.py`:

```python
"""HITL por registro y decisiones atadas a su solicitud (spec 2026-10-04 §9.3, F2).

``ledger`` (relación 16), ``request_hash`` (relación 15), ``hitl`` por
registro (L = etiquetas del ledger, H = ``human_label`` de ``decisions.json``,
D = ``records`` de ``decision.yml``), ``final_gate`` (relaciones 17 y 18),
la rebaja de ``thresholds`` (D7) y la adjudicación de ``grounding`` (D8).

La corrida real tiene el T/A aprobado en bloque (A1, D5) y el texto completo
etiquetado registro a registro (A0): 4 etiquetas, una exclusión humana.
"""

from __future__ import annotations

import pytest
from audit_fixtures import (
    auditar,
    edit_json,
    edit_ledger,
    edit_yaml,
    escribir_metricas,
    fila,
    metricas_validas,
    write_legacy_v07,
)

FT = "04_fulltext/decisions.json"


def _indice(entries: list[dict], stage: str, action: str) -> int:
    return next(i for i, e in enumerate(entries) if (e["stage"], e["action"]) == (stage, action))


def _decision_ft(rid: str, **cambios):
    def _editar(decisions: list[dict]) -> None:
        for decision in decisions:
            if decision["record_id"] == rid:
                decision.update(cambios)

    return _editar


# ── ledger: relación 16 ───────────────────────────────────────────────


def test_ledger_etiqueta_despues_de_su_approve_falla(corrida) -> None:
    def _mover(entries: list[dict]) -> list[dict]:
        i = _indice(entries, "screening_ft", "label")
        label = entries.pop(i)
        j = _indice(entries, "screening_ft", "approve")
        return [*entries[: j + 1], label, *entries[j + 1 :]]

    edit_ledger(corrida, _mover)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "`label` después de su `approve` (relación 16)" in ledger.detail


def test_ledger_etiquetas_con_un_reject_fallan(corrida) -> None:
    def _rechazar(entries: list[dict]) -> None:
        entries[_indice(entries, "screening_ft", "approve")]["action"] = "reject"

    edit_ledger(corrida, _rechazar)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "`label` acompaña a un `reject` (relación 16)" in ledger.detail


def test_ledger_tupla_repetida_falla(corrida) -> None:
    def _repetir(entries: list[dict]) -> list[dict]:
        i = _indice(entries, "screening_ft", "label")
        return [*entries[: i + 1], entries[i], *entries[i + 1 :]]

    edit_ledger(corrida, _repetir)
    ledger = fila(auditar(corrida), "ledger")
    assert ledger.status == "FAIL"
    assert "repite la tupla de la línea" in ledger.detail


# ── request_hash: relación 15 ─────────────────────────────────────────


def test_request_hash_corrida_real_pasa(corrida) -> None:
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "PASS"
    assert request.detail == "5 decisiones humanas atadas a su solicitud (hash recalculado)."


def test_request_hash_solicitud_editada_falla(corrida) -> None:
    edit_yaml(corrida / "screening_ta" / "review_request.yml", lambda r: r.update(n_screened=9))
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`screening_ta`: solicitud editada" in request.detail


def test_request_hash_decision_de_otra_solicitud_falla(corrida) -> None:
    def _otra(entries: list[dict]) -> None:
        entries[_indice(entries, "extraccion", "approve")]["detail"]["request_sha256"] = "0" * 64

    edit_ledger(corrida, _otra)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`extraccion`: la decisión efectiva responde a otra solicitud" in request.detail


def test_request_hash_actor_de_decision_yml_distinto_falla(corrida) -> None:
    edit_yaml(corrida / "rob" / "decision.yml", lambda d: d.update(actor="human:otra"))
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`rob`: actor de decision.yml (human:otra) ≠ ledger (human:revisora)" in request.detail


def test_request_hash_etiqueta_fuera_de_la_solicitud_falla(corrida) -> None:
    def _fuera(entries: list[dict]) -> None:
        entries[_indice(entries, "screening_ft", "label")]["target"] = "10.9999/fantasma"

    edit_ledger(corrida, _fuera)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`screening_ft`: etiquetas fuera de la solicitud: 10.9999/fantasma" in request.detail


def test_request_hash_ids_de_la_solicitud_distintos_de_decisions_json_falla(corrida) -> None:
    def _quitar(decisions: list[dict]) -> None:
        del decisions[-1]

    edit_json(corrida / "03_screening" / "decisions.json", _quitar)
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert "`screening_ta`: ids de la solicitud ≠ ids de 03_screening/decisions.json" in (
        request.detail
    )


@pytest.mark.parametrize(
    ("rel", "gate"),
    [
        ("05_extraction/extractions.json", "extraccion"),
        ("07_rob/assessments.json", "rob"),
        ("deliverable/documento.md", "reporte"),
    ],
)
def test_request_hash_artefacto_aprobado_modificado_falla(corrida, rel: str, gate: str) -> None:
    path = corrida / rel
    if rel.endswith(".json"):
        edit_json(path, lambda data: data.update(añadido={"study_id": "añadido"}))
    else:
        path.write_text(path.read_text(encoding="utf-8") + "\nañadido\n", encoding="utf-8")
    request = fila(auditar(corrida), "request_hash")
    assert request.status == "FAIL"
    assert f"`{gate}`: " in request.detail and "no es el" in request.detail


# ── hitl por registro ────────────────────────────────────────────────


def test_hitl_human_label_sin_label_en_el_ledger_falla(corrida) -> None:
    def _sin_etiqueta(entries: list[dict]) -> list[dict]:
        del entries[_indice(entries, "screening_ft", "label")]
        return entries

    edit_ledger(corrida, _sin_etiqueta)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`screening_ft`: etiquetas del ledger ≠ human_label de decisions.json" in hitl.detail


def test_hitl_from_distinto_de_la_propuesta_de_la_ia_falla(corrida) -> None:
    def _from(entries: list[dict]) -> None:
        entries[_indice(entries, "screening_ft", "label")]["detail"]["from"] = "unclear"

    edit_ledger(corrida, _from)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "≠ ensemble_label de la IA" in hitl.detail


def test_hitl_decision_yml_distinta_del_ledger_falla(corrida) -> None:
    def _editar(decision: dict) -> None:
        decision["records"]["10.1000/llm-1"]["label"] = "exclude"
        decision["records"]["10.1000/llm-1"]["reason"] = "cambio de opinión"

    edit_yaml(corrida / "screening_ft" / "decision.yml", _editar)
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`screening_ft`: etiquetas del ledger ≠ records de decision.yml" in hitl.detail


def test_hitl_ft_a0_con_un_recuperado_sin_etiquetar_falla(corrida) -> None:
    def _sin_etiqueta(entries: list[dict]) -> list[dict]:
        return [e for e in entries if e.get("target") != "10.1000/asreview"]

    edit_ledger(corrida, _sin_etiqueta)
    edit_json(corrida / FT, _decision_ft("10.1000/asreview", human_label=None, human_actor=None))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "FT en A0: 1 recuperado(s) sin etiqueta humana (10.1000/asreview…)" in hitl.detail


def test_hitl_unclear_sin_resolver_falla(corrida) -> None:
    edit_json(corrida / FT, _decision_ft("10.1000/ensemble", final_label="unclear"))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "FT: `unclear` sin resolver por un humano: 10.1000/ensemble" in hitl.detail


def test_hitl_exclusion_humana_ft_sin_razon_falla(corrida) -> None:
    edit_json(corrida / FT, _decision_ft("10.1000/secundario", human_reason=None))
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "FT: exclusión humana sin razón: 10.1000/secundario" in hitl.detail


def test_hitl_no_recuperado_cribado_por_ia_falla(corrida) -> None:
    edit_json(
        corrida / FT,
        _decision_ft(
            "10.1000/llm-1",
            fulltext_status="not_retrieved",
            votes=[],
            ensemble_label=None,
            human_label=None,
            human_reason=None,
            human_actor=None,
            final_label="include",
        ),
    )
    hitl = fila(auditar(corrida), "hitl")
    assert hitl.status == "FAIL"
    assert "`10.1000/llm-1` no recuperado con final_label sin rescate humano" in hitl.detail


def test_hitl_corrida_v07_sin_etiquetas_se_audita_por_etapa(tmp_path) -> None:
    # Las reglas por registro son del contrato de la Ola 1; una corrida v0.7 se
    # audita por etapa (su FAIL de publicabilidad lo da protocol_snapshot, D13).
    report = auditar(write_legacy_v07(tmp_path))
    assert fila(report, "hitl").status == "PASS"
    assert fila(report, "request_hash").status == "N/A"


# ── final_gate: relaciones 17 y 18 ────────────────────────────────────


def test_final_gate_forced_human_sin_citas_marcadas_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["final_gate"].update(forced_human=True))
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "forced_human=True y hallucination_flagged=False (relación 17)" in final_gate.detail


def test_final_gate_run_json_completed_sin_aprobar_el_reporte_falla(corrida) -> None:
    def _rechazar(entries: list[dict]) -> None:
        entries[_indice(entries, "reporte", "approve")]["action"] = "reject"

    edit_ledger(corrida, _rechazar)
    final_gate = fila(auditar(corrida), "final_gate")
    assert final_gate.status == "FAIL"
    assert "run.json dice `completed` sin un `approve` del reporte (relación 18)" in (
        final_gate.detail
    )


# ── thresholds (D7) y grounding (D8) con etiquetas humanas ───────────


def test_thresholds_recall_bajo_con_todas_las_exclusiones_ia_etiquetadas_advierte(corrida) -> None:
    def _etiquetar(decisions: list[dict]) -> None:
        for decision in decisions:
            if decision["ensemble_label"] == "exclude":
                decision.update(human_label="exclude", human_reason="revisada a mano")

    edit_json(corrida / "03_screening" / "decisions.json", _etiquetar)
    escribir_metricas(corrida, metricas_validas(18, 0, 2, 10))
    thresholds = fila(auditar(corrida), "thresholds")
    assert thresholds.status == "WARN"
    assert "todas las exclusiones IA de T/A tienen etiqueta humana: decláralo (D7)" in (
        thresholds.detail
    )


def test_grounding_marca_real_adjudicada_por_la_revisora_advierte(
    corrida_con_cita_marcada,
) -> None:
    # Corrida real: la síntesis cita [2019], que no está en el corpus; el gate
    # final se fuerza a humano y la revisora la adjudica como falso positivo.
    report = auditar(corrida_con_cita_marcada)
    grounding = fila(report, "grounding")
    assert grounding.status == "WARN"
    assert "1 citas marcadas, adjudicadas como falsos positivos por human:revisora" in (
        grounding.detail
    )
    assert fila(report, "final_gate").status == "PASS"
    assert report.n_fail == 0
    assert report.publishable


def test_grounding_marca_real_sin_su_adjudicacion_falla(corrida_con_cita_marcada) -> None:
    def _sin_adjudicar(entries: list[dict]) -> list[dict]:
        return [e for e in entries if e["action"] != "flag_review"]

    edit_ledger(corrida_con_cita_marcada, _sin_adjudicar)
    grounding = fila(auditar(corrida_con_cita_marcada), "grounding")
    assert grounding.status == "FAIL"
    assert "1 cita(s) marcada(s) sin adjudicar por un humano (D8): índices [1]" in (
        grounding.detail
    )
```

- [ ] **Step 2: Verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_hitl_registro.py -v`
Expected: FAIL en los de `ledger` (relación 16), `request_hash` (`AssertionError: sin fila 'request_hash'`), `hitl` por registro, `final_gate` (relaciones 17 y 18) y `thresholds` (sigue en FAIL). Pasan ya los que no dependen de esta tarea: la corrida v0.7 por etapa y los dos de `grounding` (la adjudicación de D8 está desde la Tarea 9; ahora se prueba con una marca real).

- [ ] **Step 3: `checks_hitl.py`**

Sustituir el contenido completo de `revisia/audit/checks_hitl.py` por:

```python
"""Checks del ledger y de la supervisión humana.

``ledger``, ``hitl``, ``request_hash`` y ``final_gate``.

Antes de la Ola 1, ``hitl`` nunca daba FAIL y una aprobación de
``--auto-approve`` en el gate final solo era WARN: una corrida sin ninguna
decisión humana salía "APTA para preparar publicación" (auditoría 2026-09-03,
C1/A11). Ahora una etapa de juicio sin decisión humana, un ``auto-approve``
en cualquier gate (D8) o un gate final sin aprobación humana son FAIL. Desde
la Ola 1 el humano decide registro a registro en el cribado (D1): las
etiquetas del ledger, las de ``decisions.json`` y las de ``decision.yml``
tienen que coincidir, y cada decisión tiene que responder a la solicitud que
el humano revisó (``request_sha256``, D4).
"""

from __future__ import annotations

from typing import Any

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict
from revisia.config import JUDGMENT_STAGES, STAGES
from revisia.provenance.ledger import (
    AUTO_APPROVE_ACTOR,
    GATE_DECISION_ACTIONS,
    HUMAN_ACTOR_PREFIX,
    LEDGER_ACTIONS,
    DecisionEntry,
)
from revisia.provenance.runmeta import canonical_sha256, sha256_text
from revisia.schemas.artifacts import GATED_STAGES, GateSummary

_NA_LEDGER = "no aplica: sin ledger legible (ver `ledger`)."
_MAX_PROBLEMAS = 5
# Decisiones de cribado (por registro) y su consolidado.
SCREENING_DECISIONS = {
    "screening_ta": "03_screening/decisions.json",
    "screening_ft": "04_fulltext/decisions.json",
}
# Artefacto aprobado en bloque y su hash en la solicitud (spec §4.3).
APPROVED_ARTIFACTS = {
    "extraccion": "05_extraction/extractions.json",
    "rob": "07_rob/assessments.json",
}


def effective_autonomy(ctx: AuditContext) -> dict[str, str] | None:
    """Autonomía efectiva de cada gate.

    La que registró el manifiesto (``autonomy_effective``, Ola 1) o, sin ella,
    la del protocolo. ``None`` si no hay ninguna fuente legible (corrida en
    pausa antes de escribir el manifiesto y sin protocolo).
    """
    registered = ctx.manifest_section("autonomy_effective")
    if registered.ok:
        return dict(registered.value)
    if ctx.protocol is None:
        return None
    return {gate: ctx.protocol.autonomy_for(gate) for gate in GATED_STAGES}


def _limitar(problems: list[str]) -> str:
    shown = "; ".join(problems[:_MAX_PROBLEMAS])
    more = len(problems) - _MAX_PROBLEMAS
    return shown + (f" (+{more} más)" if more > 0 else "")


def _relation_16(entries: tuple[tuple[int, DecisionEntry], ...]) -> list[str]:
    """Relación 16: ``label``/``flag_review`` antes de su ``approve``, nunca con un
    ``reject``, y la tupla ``(stage, action, target, request, decision)`` única."""
    problems: list[str] = []
    closing: dict[tuple[str, Any], list[tuple[int, str]]] = {}
    for number, entry in entries:
        sha = entry.detail.get("decision_sha256")
        if entry.action in GATE_DECISION_ACTIONS and sha is not None:
            closing.setdefault((entry.stage, sha), []).append((number, entry.action))
    seen: dict[tuple, int] = {}
    for number, entry in entries:
        request = entry.detail.get("request_sha256")
        key = (
            entry.stage,
            entry.action,
            entry.target,
            request,
            entry.detail.get("decision_sha256"),
        )
        if request is not None and key in seen:
            problems.append(
                f"línea {number}: repite la tupla de la línea {seen[key]} (relación 16)"
            )
        seen.setdefault(key, number)
        if entry.action not in ("label", "flag_review"):
            continue
        decided = closing.get((entry.stage, entry.detail.get("decision_sha256")), [])
        if any(action == "reject" for _, action in decided):
            problems.append(
                f"línea {number}: `{entry.action}` acompaña a un `reject` (relación 16)"
            )
        elif decided and min(n for n, _ in decided) < number:
            problems.append(
                f"línea {number}: `{entry.action}` después de su `approve` (relación 16)"
            )
    return problems


def check_ledger(ctx: AuditContext) -> Verdict:
    """trAIce M8 / PRISMA 8: ledger legible, con lo que el motor escribe y en orden.

    Una línea corrupta ya no se descarta en silencio (antes, ``audit.py:85-86``)
    y una acción que ``review_gate`` nunca emite (``propose``/``exclude``/
    ``verify`` en la reconstrucción C3) delata un ledger escrito a mano.
    """
    view = ctx.ledger
    if not view.present:
        return "FAIL", "decisions_ledger.jsonl ausente: sin trazabilidad de decisiones."
    if view.read_error:
        return "FAIL", f"decisions_ledger.jsonl ilegible ({view.read_error})."
    if not view.entries and not view.errors:
        return "FAIL", "decisions_ledger.jsonl vacío: sin trazabilidad de decisiones."

    problems = list(view.errors)
    for number, entry in view.entries:
        if entry.stage not in STAGES:
            problems.append(f"línea {number}: etapa desconocida `{entry.stage}`")
        if entry.action not in LEDGER_ACTIONS:
            problems.append(f"línea {number}: acción `{entry.action}` que el motor no emite")

    # Los gates se deciden por primera vez en el orden de STAGES; tras un
    # rechazo se puede volver a decidir una etapa anterior (D14).
    first: dict[str, int] = {}
    for number, entry in view.entries:
        if entry.action in GATE_DECISION_ACTIONS and entry.stage in STAGES:
            first.setdefault(entry.stage, number)
    ordered = sorted(first, key=first.__getitem__)
    if ordered != sorted(ordered, key=STAGES.index):
        problems.append("gates fuera del orden de STAGES: " + " → ".join(ordered))

    autonomy = effective_autonomy(ctx)
    if autonomy is not None:
        for number, entry in view.entries:
            expected = autonomy.get(entry.stage)
            if expected is not None and entry.autonomy != expected:
                problems.append(
                    f"línea {number}: autonomía {entry.autonomy} en `{entry.stage}`, "
                    f"la efectiva es {expected}"
                )
    problems += _relation_16(view.entries)

    if problems:
        return "FAIL", f"{len(problems)} problema(s) en el ledger: {_limitar(problems)}."
    note = "" if autonomy is not None else " (autonomía no verificable: sin protocolo legible)"
    return "PASS", f"{len(view.entries)} entradas válidas, en orden{note}."


def _excluded_human(ctx: AuditContext) -> int | None:
    """``excluded_human`` declarado (fichero o, si no se lee, la copia del manifiesto)."""
    loaded = ctx.art.artifact("03_screening/exclusions.json")
    if loaded.ok:
        return loaded.value.excluded_human
    copy = ctx.manifest_section("exclusions")
    return copy.value.excluded_human if copy.ok else None


def _labels(ctx: AuditContext, gate: GateSummary) -> list[DecisionEntry]:
    """Entradas ``label`` de la decisión efectiva de un gate (mismo ``decision_sha256``)."""
    return [
        e
        for e in ctx.ledger.decisions
        if e.stage == gate.stage
        and e.action == "label"
        and gate.decision_sha256 is not None
        and e.detail.get("decision_sha256") == gate.decision_sha256
    ]


def _record_labels(ctx: AuditContext, stage: str, gate: GateSummary) -> list[str]:
    """D1/D5: etiquetas del ledger (L), de ``decisions.json`` (H) y de
    ``decision.yml`` (D) de un gate de cribado aprobado; y, a texto completo,
    lo que el humano tiene que resolver (spec §9.3, ``hitl`` fase 2)."""
    problems: list[str] = []
    loaded = ctx.art.artifact(SCREENING_DECISIONS[stage])
    if not loaded.ok:
        return [f"`{stage}`: {SCREENING_DECISIONS[stage]} ausente o inválido"]
    decisions = {d.record_id: d for d in loaded.value}
    entries = _labels(ctx, gate)
    labels: dict[str, str] = {}
    for entry in entries:
        target, to = entry.target or "", entry.detail.get("to")
        if target in labels and labels[target] != to:
            problems.append(f"`{stage}`: etiquetas que chocan para `{target}`")
        labels[target] = to
        if entry.actor != gate.actor:
            problems.append(
                f"`{stage}`: la etiqueta de `{target}` es de {entry.actor}, no de {gate.actor}"
            )
        decision = decisions.get(target)
        if decision is not None and entry.detail.get("from") != decision.ensemble_label:
            problems.append(f"`{stage}`: `from` de `{target}` ≠ ensemble_label de la IA")
        if decision is not None and entry.detail.get("reason") != decision.human_reason:
            problems.append(f"`{stage}`: razón de `{target}` ≠ human_reason")
    human = {rid: d.human_label for rid, d in decisions.items() if d.human_label is not None}
    if labels != human:
        diff = sorted(set(labels.items()) ^ set(human.items()))
        problems.append(f"`{stage}`: etiquetas del ledger ≠ human_label de decisions.json {diff}")
    decision_file = ctx.art.decision(stage)
    if decision_file.ok:
        records = getattr(decision_file.value, "records", None) or {}
        written = {
            rid: (r.label if hasattr(r, "label") else r.get("label")) for rid, r in records.items()
        }
        written = {rid: label for rid, label in written.items() if label is not None}
        if written != labels:
            problems.append(f"`{stage}`: etiquetas del ledger ≠ records de decision.yml")
    if stage == "screening_ft":
        problems += _fulltext_rules(ctx, gate, list(decisions.values()))
    return problems


def _fulltext_rules(ctx: AuditContext, gate: GateSummary, decisions: list[Any]) -> list[str]:
    problems: list[str] = []
    autonomy = (effective_autonomy(ctx) or {}).get("screening_ft", gate.autonomy)
    unlabeled = [
        d.record_id for d in decisions if d.fulltext_status == "retrieved" and d.human_label is None
    ]
    if autonomy == "A0" and unlabeled:
        problems.append(
            f"FT en A0: {len(unlabeled)} recuperado(s) sin etiqueta humana ({unlabeled[0]}…)"
        )
    unclear = [d.record_id for d in decisions if d.final_label == "unclear"]
    if unclear:
        problems.append(f"FT: `unclear` sin resolver por un humano: {', '.join(unclear)}")
    no_reason = [
        d.record_id
        for d in decisions
        if d.human_label == "exclude" and not (d.human_reason or "").strip()
    ]
    if no_reason:
        problems.append(f"FT: exclusión humana sin razón: {', '.join(no_reason)}")
    for d in decisions:
        if d.fulltext_status != "not_retrieved":
            continue
        if d.human_label is None and d.final_label is not None:
            problems.append(f"FT: `{d.record_id}` no recuperado con final_label sin rescate humano")
        if d.human_label is not None and not (d.human_reason or "").strip():
            problems.append(f"FT: rescate de `{d.record_id}` sin razón")
    return problems


def check_hitl(ctx: AuditContext) -> Verdict:
    """trAIce M8/R1 / PRISMA 8: decide un humano en cada etapa de juicio alcanzada."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    decisions = ctx.ledger.decisions
    fails: list[str] = []
    warns: list[str] = []

    auto = sorted({e.stage for e in decisions if e.actor == AUTO_APPROVE_ACTOR}, key=STAGES.index)
    if auto:
        fails.append(
            f"decisiones de `{AUTO_APPROVE_ACTOR}` en {', '.join(auto)} "
            "(D8: --auto-approve no es revisión humana)"
        )

    reached = [s for s in JUDGMENT_STAGES if s in ctx.state.reached]
    for stage in reached:
        gate = ctx.gates.get(stage)
        if gate is None:
            later = [g for g in GATED_STAGES[GATED_STAGES.index(stage) + 1 :] if g in ctx.gates]
            fails.append(
                f"gate saltado: `{stage}` sin decisión y `{later[0]}` decidida"
                if later
                else f"`{stage}` alcanzada sin decisión"
            )
        elif not gate.actor.startswith(HUMAN_ACTOR_PREFIX):
            fails.append(
                f"`{stage}`: decisión efectiva de `{gate.actor}` ({gate.action}), no humana"
            )
        elif stage not in ctx.requests:
            fails.append(
                f"`{stage}`: decisión humana sin solicitud (falta `{stage}/review_request.yml`)"
            )
        else:
            if gate.actor == "human:desconocido":
                warns.append(
                    f"`{stage}`: actor `human:desconocido` (declara `actor:` en decision.yml)"
                )
            if (
                ctx.run_info is not None
                and stage in SCREENING_DECISIONS
                and gate.action == "approve"
            ):
                fails += _record_labels(ctx, stage, gate)

    # Vía independiente contra el `excluded_human: 3` de C3: cada exclusión
    # humana deja una entrada `label` con `to: exclude` (spec §4.3).
    declared = _excluded_human(ctx)
    labels_exclude = sum(
        1 for e in decisions if e.action == "label" and e.detail.get("to") == "exclude"
    )
    if declared is not None and declared > labels_exclude:
        fails.append(
            f"exclusions.json declara {declared} exclusiones humanas y el ledger solo registra "
            f"{labels_exclude} etiquetas `exclude`"
        )

    if fails:
        return "FAIL", f"{_limitar(fails)}."
    if warns:
        return "WARN", f"{_limitar(warns)}."
    actors = sorted({ctx.gates[s].actor for s in reached})
    n_labels = sum(1 for e in decisions if e.action == "label")
    return "PASS", (
        f"decisión humana en {len(reached)} etapa(s) de juicio alcanzada(s) "
        f"({', '.join(actors) or 'ninguna'}); {n_labels} etiqueta(s) por registro."
    )


def _request_ids(request: dict) -> list[str] | None:
    records = request.get("records")
    if not isinstance(records, list):
        return None
    return [r.get("record_id") for r in records if isinstance(r, dict)]


def check_request_hash(ctx: AuditContext) -> Verdict:
    """trAIce M8: cada decisión humana responde a la solicitud que el humano revisó.

    Relación 15 de §4.4: el ``request_sha256`` de cada solicitud se recalcula
    desde su contenido y es el que llevan su ``decision.yml`` y las entradas
    de la decisión efectiva; los hashes de los artefactos aprobados coinciden
    con el disco. Una solicitud editada o una decisión de otra solicitud
    delatan una aprobación que no fue la que se registró (D4).
    """
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    if ctx.run_info is None:
        return "N/A", (
            "no aplica: corrida anterior a la Ola 1, sus decisiones no llevan request_sha256 "
            "(ver `protocol_snapshot`)."
        )
    fails: list[str] = []
    checked = 0
    for stage in GATED_STAGES:
        loaded = ctx.art.yaml(f"{stage}/review_request.yml")
        gate = ctx.gates.get(stage)
        if not loaded.present or gate is None or gate.action == "auto-proceed":
            continue
        if not loaded.ok:
            fails.append(f"`{stage}/review_request.yml` ilegible ({loaded.error})")
            continue
        request = dict(loaded.value)
        declared = request.pop("request_sha256", None)
        if declared != canonical_sha256(request):
            fails.append(
                f"`{stage}`: solicitud editada (su request_sha256 no es el de su contenido)"
            )
        if gate.request_sha256 != declared:
            fails.append(f"`{stage}`: la decisión efectiva responde a otra solicitud")
        for entry in _labels(ctx, gate):
            if entry.detail.get("request_sha256") != gate.request_sha256:
                fails.append(f"`{stage}`: etiqueta de `{entry.target}` de otra solicitud")
        decision = ctx.art.decision(stage)
        if decision.ok:
            if decision.value.request_sha256 != declared:
                fails.append(f"`{stage}`: decision.yml responde a otra solicitud")
            if canonical_sha256(decision.value.model_dump(mode="json")) != gate.decision_sha256:
                fails.append(f"`{stage}`: decision.yml no es la decisión registrada en el ledger")
            if decision.value.actor != gate.actor:
                fails.append(
                    f"`{stage}`: actor de decision.yml ({decision.value.actor}) ≠ "
                    f"ledger ({gate.actor})"
                )
        fails += _request_contents(ctx, stage, gate, request)
        checked += 1
    if fails:
        return "FAIL", f"{_limitar(fails)}."
    return "PASS", f"{checked} decisiones humanas atadas a su solicitud (hash recalculado)."


def _request_contents(ctx: AuditContext, stage: str, gate: GateSummary, request: dict) -> list[str]:
    """Lo que la solicitud dice que se aprobó coincide con el disco."""
    problems: list[str] = []
    ids = _request_ids(request)
    if ids is not None and stage in SCREENING_DECISIONS:
        decisions = ctx.art.artifact(SCREENING_DECISIONS[stage])
        if decisions.ok and sorted(ids) != sorted(d.record_id for d in decisions.value):
            problems.append(f"`{stage}`: ids de la solicitud ≠ ids de {SCREENING_DECISIONS[stage]}")
        outside = sorted({e.target for e in _labels(ctx, gate)} - set(ids))
        if outside:
            problems.append(f"`{stage}`: etiquetas fuera de la solicitud: {', '.join(outside)}")
    if stage in APPROVED_ARTIFACTS and "artifact_sha256" in request:
        loaded = ctx.art.json(APPROVED_ARTIFACTS[stage])
        if not loaded.ok or canonical_sha256(loaded.value) != request["artifact_sha256"]:
            problems.append(f"`{stage}`: {APPROVED_ARTIFACTS[stage]} no es el artefacto aprobado")
    if stage == "reporte" and "documento_sha256" in request:
        loaded = ctx.art.text("deliverable/documento.md")
        if not loaded.ok or sha256_text(loaded.value) != request["documento_sha256"]:
            problems.append("`reporte`: deliverable/documento.md no es el documento aprobado")
    return problems


def _relation_17(ctx: AuditContext, gate: GateSummary) -> list[str]:
    """Relación 17: con citas marcadas, el gate final fue humano y adjudicó cada una."""
    problems: list[str] = []
    block = ctx.manifest_section("final_gate")
    verification = ctx.art.artifact("06_synthesis/verification.json")
    if not block.ok or not verification.ok:
        return problems
    flagged = verification.value.hallucination_flagged
    if block.value.forced_human != flagged:
        problems.append(
            f"manifest.final_gate.forced_human={block.value.forced_human} y "
            f"hallucination_flagged={flagged} (relación 17)"
        )
    if not flagged:
        return problems
    if not gate.forced_human:
        problems.append("hay citas marcadas y la decisión final no se forzó a humana (relación 17)")
    if gate.action != "approve":
        return problems
    indices = [
        i
        for i, c in enumerate(verification.value.checks)
        if not c.exists_in_corpus or not c.grounded
    ]
    reviews = {
        e.target
        for e in ctx.ledger.decisions
        if e.stage == "reporte"
        and e.action == "flag_review"
        and e.actor == gate.actor
        and e.detail.get("decision_sha256") == gate.decision_sha256
        and e.detail.get("verdict") == "false_positive"
        and str(e.detail.get("reason") or "").strip()
    }
    missing = [i for i in indices if f"flag:{i}" not in reviews]
    if missing:
        problems.append(
            f"citas marcadas {missing} sin `flag_review` de {gate.actor} en ese `approve` "
            "(relación 17)"
        )
    return problems


def check_final_gate(ctx: AuditContext) -> Verdict:
    """trAIce M8: el reporte final lo aprueba un humano, a través de su gate."""
    if not ctx.ledger.entries:
        return "N/A", _NA_LEDGER
    reporte = [e for e in ctx.ledger.decisions if e.stage == "reporte"]
    if reporte and reporte[-1].action not in GATE_DECISION_ACTIONS | {"flag_review"}:
        last = reporte[-1]
        return "FAIL", f"Acción desconocida `{last.action}` en la decisión final ({last.actor})."

    state = ctx.state
    # Relación 18: run.json dice `completed` solo si el reporte se aprobó.
    note = ""
    if ctx.run_info is not None and ctx.run_info.status == "completed":
        effective = ctx.gates.get("reporte")
        if effective is None or effective.action != "approve":
            note = " run.json dice `completed` sin un `approve` del reporte (relación 18)."
    if state.status == "paused":
        return "FAIL", f"corrida en pausa en `{state.pending_stage}`: sin decisión final.{note}"
    if state.status == "interrupted":
        return "FAIL", f"corrida interrumpida en `{state.pending_stage}`: sin decisión final.{note}"
    if state.status == "rejected":
        actor = ctx.gates[state.pending_stage].actor
        if state.pending_stage == "reporte":
            return "FAIL", f"El reporte final fue rechazado por {actor}.{note}"
        return "FAIL", (
            f"corrida rechazada en `{state.pending_stage}` por {actor}: sin decisión final.{note}"
        )

    gate = ctx.gates.get("reporte")
    if gate is None:
        return "FAIL", f"Sin decisión sobre el reporte final.{note}"
    if gate.action != "approve" or not gate.actor.startswith(HUMAN_ACTOR_PREFIX):
        return "FAIL", (
            f"El reporte final no lo aprobó un humano: {gate.actor}/{gate.action} "
            f"(D8: el gate final exige una decisión humana).{note}"
        )
    if "reporte" not in ctx.requests:
        return "FAIL", (
            "aprobación humana sin solicitud: falta `reporte/review_request.yml` "
            "(la decisión no pasó por el gate)."
        )
    problems = _relation_17(ctx, gate)
    if problems:
        return "FAIL", f"{_limitar(problems)}."
    return "PASS", f"Reporte final aprobado por humano ({gate.actor})."
```

- [ ] **Step 4: Rebaja de `thresholds` (`checks_quality.py`)**

En `revisia/audit/checks_quality.py`, sustituir

```python
            if m.recall < recall_target:
                pending = ai_exclusions_without_label(ctx)
                quedan = "un número no verificable de" if pending is None else str(pending)
                fails.append(
                    f"{recall} < {recall_target:.2f} con {positives} positivos y {quedan} "
                    "exclusiones IA de T/A sin etiqueta humana: etiquétalas en "
                    "`screening_ta/decision.yml` y reanuda (D7, D14)"
                )
            else:
                minimo = potencia_minima(recall_target)
```

por

```python
            if m.recall < recall_target:
                pending = ai_exclusions_without_label(ctx)
                if pending == 0:
                    # D7: un humano revisó cada exclusión de la IA; ningún estudio
                    # relevante quedó fuera sin que alguien lo mirara.
                    warns.append(
                        f"{recall} < {recall_target:.2f} con {positives} positivos, pero todas "
                        "las exclusiones IA de T/A tienen etiqueta humana: decláralo (D7)"
                    )
                else:
                    quedan = "un número no verificable de" if pending is None else str(pending)
                    fails.append(
                        f"{recall} < {recall_target:.2f} con {positives} positivos y {quedan} "
                        "exclusiones IA de T/A sin etiqueta humana: etiquétalas en "
                        "`screening_ta/decision.yml` y reanuda (D7, D14)"
                    )
            else:
                minimo = potencia_minima(recall_target)
```

- [ ] **Step 5: Registrar `request_hash`**

En `revisia/audit/__init__.py`, sustituir

```python
    CheckSpec("ledger", "trAIce M8 / PRISMA 8", None, checks_hitl.check_ledger),
    CheckSpec("hitl", "trAIce M8/R1 / PRISMA 8", None, checks_hitl.check_hitl),
    CheckSpec("final_gate", "trAIce M8", None, checks_hitl.check_final_gate),
    CheckSpec("stage_artifacts", "PRISMA 16/27", None, checks_flow.check_stage_artifacts),
```

por

```python
    CheckSpec("ledger", "trAIce M8 / PRISMA 8", None, checks_hitl.check_ledger),
    CheckSpec("hitl", "trAIce M8/R1 / PRISMA 8", None, checks_hitl.check_hitl),
    CheckSpec("request_hash", "trAIce M8", None, checks_hitl.check_request_hash),
    CheckSpec("final_gate", "trAIce M8", None, checks_hitl.check_final_gate),
    CheckSpec("stage_artifacts", "PRISMA 16/27", None, checks_flow.check_stage_artifacts),
```

- [ ] **Step 6: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_hitl_registro.py tests/test_audit_hitl.py tests/test_audit.py -v`
Expected: PASS (25 nuevos; los de las Tareas 5 y 8 siguen en verde).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, `N_D + 241` recogidos (740), 2 skipped.

- [ ] **Step 7: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 8: Commit**

```bash
git add revisia/audit tests/conftest.py tests/test_audit_hitl_registro.py
git commit -m "feat(audit): HITL por registro y decisiones atadas a su solicitud (D1, D4, D8)" -m "hitl exige que las etiquetas del ledger, las de decisions.json y las de decision.yml coincidan y que el texto completo en A0 esté etiquetado registro a registro. request_hash recalcula el hash de cada solicitud y lo ata a su decisión, a sus etiquetas y a los artefactos aprobados (relación 15). ledger verifica el orden de las etiquetas (relación 16) y final_gate las citas marcadas (relación 17) y run.json (relación 18). thresholds baja a WARN cuando un humano revisó todas las exclusiones IA (D7). grounding se prueba con una cita marcada real, adjudicada por la revisora (D8). Spec 2026-10-04 §4.4 y §9.3." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: Frontera pipeline ↔ auditor en `tests/test_pipeline_fake.py` (cierre de la fase 2)

**Files:**
- Modify: `tests/test_pipeline_fake.py` (una afirmación en `test_paused_run_final_gate_falla_en_auditoria`; dos tests al final)

**Interfaces:**
- Consumes: lo que ya importa `tests/test_pipeline_fake.py` tras PR-D (`ScriptedProvider`, `fetch_disponible`, `correr_hasta`, `run_audit`, `run_pipeline`, `RunContext`, `EXAMPLE`, `_fake_search`).
- Produces: `test_pipeline_fake_con_humano_audita_sin_fail` y `test_pipeline_auto_approve_no_es_publicable` (spec §9.4, tests de frontera).

Estos tests no siguen el ciclo rojo → verde: fijan la frontera. Si `test_pipeline_fake_con_humano_audita_sin_fail` falla, el pipeline y el auditor leen el contrato de §4 de forma distinta: el detalle del FAIL dice qué relación; corrige el auditor (o, si el pipeline incumple el contrato, avisa al controlador), nunca el test.

- [ ] **Step 1: Los tests**

En `tests/test_pipeline_fake.py`, sustituir

```python
    final_gate = next(c for c in report.checks if c.check_id == "final_gate")
    assert final_gate.status == "FAIL"


def test_ft_no_recuperado_no_se_criba_con_ia(
```

por

```python
    final_gate = next(c for c in report.checks if c.check_id == "final_gate")
    assert final_gate.status == "FAIL"
    assert "en pausa en `reporte`" in final_gate.detail


def test_ft_no_recuperado_no_se_criba_con_ia(
```

En `tests/test_pipeline_fake.py`, sustituir

```python
        "reporte": "A1",
    }
```

por

```python
        "reporte": "A1",
    }


# ── Frontera del contrato con el auditor (spec 2026-10-04 §9.4, PR-E) ──


def _etiquetar_como_la_ia(stage: str, solicitud: dict) -> dict | None:
    """La revisora acepta, registro a registro, la propuesta de la IA a texto completo (A0)."""
    if stage != "screening_ft":
        return None
    propuestas = {r["record_id"]: r.get("proposal") for r in solicitud.get("records", [])}
    records = {
        rid: (
            {"label": "exclude", "reason": "fuera de alcance"}
            if propuestas.get(rid) == "exclude"
            else {"label": "include", "reason": None}
        )
        for rid in solicitud.get("must_label", [])
    }
    return {"records": records} if records else None


def test_pipeline_fake_con_humano_audita_sin_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Lo que escribe el pipeline con un humano en cada gate audita sin ningún
    # FAIL: si el pipeline y el auditor leen el contrato de §4 distinto, falla.
    monkeypatch.setattr(
        pipeline_mod, "build_provider", lambda cfg: ScriptedProvider(model=cfg.model)
    )
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST-FRONTERA")
    result = correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
        etiquetar=_etiquetar_como_la_ia,
    )
    assert result.status == "completed"
    report = run_audit(ctx.run_dir)
    assert {c.check_id: c.detail for c in report.checks if c.status == "FAIL"} == {}
    assert report.publishable


def test_pipeline_auto_approve_no_es_publicable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # D8: `--auto-approve` sirve para demostraciones; la corrida no es publicable.
    monkeypatch.setattr(
        pipeline_mod, "build_provider", lambda cfg: ScriptedProvider(model=cfg.model)
    )
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "TEST-AUTO")
    result = run_pipeline(
        protocol,
        EXAMPLE,
        ctx,
        auto_approve=True,
        search_fn=_fake_search,
        fetch_fn=fetch_disponible,
    )
    assert result.status == "completed"
    report = run_audit(ctx.run_dir)
    assert not report.publishable
    statuses = {c.check_id: c.status for c in report.checks}
    assert statuses["hitl"] == statuses["final_gate"] == "FAIL"
    final_gate = next(c for c in report.checks if c.check_id == "final_gate")
    assert "auto-approve (demo)" in final_gate.detail
```

- [ ] **Step 2: Verificar**

Run: `uv run pytest -p no:cacheprovider tests/test_pipeline_fake.py -v`
Expected: PASS (los de PR-D y los 2 nuevos).

Run: `uv run pytest -p no:cacheprovider`
Expected: PASS, **`N_D + 243` recogidos (742)**, 2 skipped.

- [ ] **Step 3: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio. Si `ruff format` reordena algo, acepta su versión y repite.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pipeline_fake.py
git commit -m "test(audit): frontera pipeline-auditor con humano y con --auto-approve" -m "Una corrida del pipeline con un humano en cada gate audita sin ningún FAIL: si el pipeline y el auditor leen el contrato de §4 distinto, este test lo delata. La misma corrida con --auto-approve no es publicable (hitl y final_gate en FAIL, D8). La pausa en el gate final dice en pausa en reporte. Spec 2026-10-04 §9.4." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Verificación de la fase 2 (3.11 y 3.12, lint, lock)**

```bash
TMP="$(mktemp -d)"
for PY in 3.11 3.12; do
  uv venv -q --python "$PY" "$TMP/venv$PY"
  uv pip install -q --python "$TMP/venv$PY" pydantic pyyaml python-dotenv markdown httpx nh3 pytest
  PYTHONPATH=. "$TMP/venv$PY/Scripts/python" -m pytest -p no:cacheprovider -q
done
```

Expected: PASS en ambas versiones (742 recogidos con `N_D = 499`).

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`
Expected: limpio.

---

## Integración y cierre de la Ola 1

### Task 17: Integración de PR-E y cierre de la ola (controlador, `C:\revisia-wt\e`)

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`, ya con el texto de PR-0 a PR-D: `### Added`, `### Fixed`, `### Changed`, `### Cambios incompatibles`)
- Modify: `README.md` (bloque de `revisia audit` tras el quickstart; nota "Limitación actual" del checkpoint; párrafo "Auditoría abierta"; árbol "Estructura"; tabla "Defaults de buenas prácticas")
- Modify: `AGENTS.md` (filas `verificador` y `auditor`; punto 4 de "Las auditorías")
- Modify: `docs/auditoria/2026-09-03-auditoria-completa.md` (§11: subsección "Ola 1 · cerrada")
- Modify: `docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md` (§14, filas 32-45)

**Interfaces:** ninguna de código. Deja `feat/ola1-auditor` publicada y PR-E abierta con base `feat/ola1-hitl-por-registro`. **Sin merge.**

Los textos de abajo se anclan en el estado de los ficheros tras las integraciones de PR-0 a PR-D (planes A y B, Tareas 5, 14, 15, 19 y 28): se comprobó, aplicando esas integraciones sobre la documentación actual, que cada fragmento a sustituir aparece una sola vez.

- [ ] **Step 1: Al día con D**

Si `feat/ola1-hitl-por-registro` recibió commits después de la Tarea 11 (su commit de documentación de la Tarea 28 del plan B, correcciones de revisión):

```bash
git -C C:/revisia-wt/e rebase feat/ola1-hitl-por-registro
```

Run: `uv run pytest -p no:cacheprovider`
Expected: en verde, `N_D + 243` recogidos (742 con `N_D = 499`). Sin conflictos: E no toca la documentación hasta este paso.

- [ ] **Step 2: CHANGELOG**

En `CHANGELOG.md`, sustituir

```markdown
  umbral no bloquee la publicación. Las de extracción y RoB llevan la tabla
  completa por estudio y el hash del artefacto aprobado.

### Fixed
```

por

```markdown
  umbral no bloquee la publicación. Las de extracción y RoB llevan la tabla
  completa por estudio y el hash del artefacto aprobado.
- **Auditor exigente** (`revisia audit`; auditoría 2026-09-03, C3, A11 y M5):
  el auditor pasa a ser el paquete `revisia/audit/` y comprueba que la corrida
  es coherente, no solo que sus ficheros existan. Una fila por check, siempre:
  `N/A` solo si la etapa no se alcanzó o la raíz del check ya falló, y un
  error interno es FAIL, nunca un PASS por omisión. Checks nuevos: `schemas`
  (cada artefacto contra su modelo), `protocol_snapshot` (`00_protocol/`
  contra las huellas de `run.json`), `timing` (marcas de tiempo posibles; las
  heurísticas de una reconstrucción solo avisan), `ledger` (orden y unicidad),
  `request_hash` (cada decisión atada a la solicitud que el humano revisó),
  `stage_artifacts`, `arithmetic` (las relaciones del flujo PRISMA de punta a
  punta: búsqueda, dedup, cribado, recuperación, 16b, CSV, diarios),
  `thresholds` (`recall_target` y `kappa_min` del protocolo, con el intervalo
  de Wilson del recall), `search_log` y `response_overlap`. `hitl` comprueba
  las etiquetas por registro (ledger, `decisions.json` y `decision.yml`
  coinciden) y `grounding`, que cada cita marcada la adjudicó un humano.
- `revisia.metrics.kappa_from_matrix(tp, fp, fn, tn)` y
  `revisia.metrics.wilson_interval(k, n)`, públicas.

### Fixed
```

sustituir

```markdown
- `hallucination_flagged` solo se imprimía; ahora bloquea la aprobación
  silenciosa del reporte (M5).

### Changed
```

por

```markdown
- `hallucination_flagged` solo se imprimía; ahora bloquea la aprobación
  silenciosa del reporte (M5).
- `revisia audit` aprobaba la reconstrucción de la corrida de referencia (C3):
  140 llamadas en 1,3 ms, un ledger fechado una semana antes, `excluded_human:
  3` sin ninguna decisión humana, métricas sin matriz que las respalde y etapas
  sin sus artefactos. Ahora la declara no publicable por once checks distintos.
- `gold` daba PASS con κ = 0,0 aunque el protocolo pidiera `kappa_min: 0.6`:
  nadie leía los umbrales (A11).
- `search_window` daba PASS a una fecha de ejecución tecleada a mano.

### Changed
```

sustituir

```markdown
- `--auto-approve` aprueba con las etiquetas de la IA y no exige etiquetar
  cada registro en A0, pero pausa si hay un `unclear` en texto completo (D9).

### Cambios incompatibles
```

por

```markdown
- `--auto-approve` aprueba con las etiquetas de la IA y no exige etiquetar
  cada registro en A0, pero pausa si hay un `unclear` en texto completo (D9).
- Una corrida en pausa o interrumpida se audita con lo que tiene: los checks de
  las etapas que no alcanzó dan `N/A` (➖ en la consola) y el gate final, FAIL.

### Cambios incompatibles
```

y sustituir

```markdown
- `render_traice_checklist` recibe la autonomía efectiva por gate (segundo
  argumento) y, opcionalmente, `gates` y `forced_human`.

## [0.7.0] · 2026-09-28
```

por

```markdown
- `render_traice_checklist` recibe la autonomía efectiva por gate (segundo
  argumento) y, opcionalmente, `gates` y `forced_human`.
- El auditor es más estricto (D7, D8): `--auto-approve` o una etapa de juicio
  sin decisión humana, un recall bajo `recall_target` con exclusiones de la IA
  sin revisar y una cita marcada sin adjudicar pasan a FAIL, y la corrida deja
  de ser publicable. Un κ bajo `kappa_min` es una desviación a declarar (WARN).
- Las corridas anteriores a esta versión (sin `run.json`) dan FAIL en
  `protocol_snapshot` y no son publicables (D13); se siguen auditando enteras
  como diagnóstico. Regenéralas con el motor actual.
- `revisia.audit` es un paquete: `from revisia.audit import run_audit,
  render_audit_md, AuditReport, AuditCheck` sigue funcionando; `AuditReport`
  gana `state` y `n_na`, y `AuditCheck.status` admite `N/A`.

## [0.7.0] · 2026-09-28
```

- [ ] **Step 3: README**

Tras el quickstart ("Y al terminar, **audita la corrida** antes de usarla:"), sustituir

````markdown
```bash
uv run revisia audit runs/mi-revision-<fecha>
# ✅/⚠️/❌ por verificación (manifest, prompts, HITL, gold, grounding, registro…)
# → escribe runs/.../audit.md con el veredicto de publicabilidad
```
````

por

````markdown
```bash
uv run revisia audit runs/mi-revision-<fecha>
# ✅/⚠️/❌/➖ por verificación: esquemas, instantánea del protocolo, marcas de tiempo,
#   ledger y HITL por registro, aritmética del flujo PRISMA, umbrales, grounding, búsqueda…
# → escribe runs/.../audit.md con el estado de la corrida y el veredicto de publicabilidad
```

El auditor comprueba que la corrida es **coherente**, no solo que sus ficheros
existan: cada artefacto valida su modelo, el protocolo usado es el de
`00_protocol/`, los conteos del diagrama salen de los registros, cada decisión
humana responde a la solicitud que se revisó y los umbrales del protocolo
(`recall_target`, `kappa_min`) se cumplen o se declaran. Una corrida con
`--auto-approve`, sin decisión humana en una etapa de juicio, con citas
marcadas sin adjudicar o anterior a la Ola 1 (sin `run.json`) **no es
publicable**.
````

En "Checkpoint humano (`decision.yml`)", quitar la nota "Limitación actual" que dejó PR-D (spec §10): sustituir

```markdown
declaran como no humano) y pausa si hay un `unclear` en texto completo o citas
marcadas.

> **Limitación actual (Ola 1 del plan de remediación).** `revisia audit` todavía
> marca `--auto-approve` solo con WARN en `hitl` y en `final_gate`, sin
> declararlo no publicable; el auditor estricto llega con la última PR de la
> Ola 1.
```

por

```markdown
declaran como no humano) y pausa si hay un `unclear` en texto completo o citas
marcadas. `revisia audit` declara esa corrida **no publicable** (FAIL en
`hitl` y en `final_gate`).
```

En la nota "Auditoría abierta (2026-09-03)", sustituir

```markdown
> determinista, capa de proveedores), pero **tres promesas de este README aún no
> se cumplen en el código**: la decisión humana registro a registro, el
> verificador anti-alucinación en su modo por defecto, y la reproducibilidad de
> la corrida de referencia. El plan de remediación en tres olas está en el
> informe. **La Ola 0 se cerró el 2026-09-25** (PRs #8–#10): seguridad del motor
> y del exportador, un reporte rechazado ya no figura como completado, el
> auditor exige procedencia y decisión humana final, modelo por defecto vigente
> y métricas indefinidas marcadas como tales (estado en §11 del informe). Hasta
> cerrar la Ola 1, trata las salidas como borradores que requieren revisión
> humana completa, no como evidencia publicable.
```

por

```markdown
> determinista, capa de proveedores), pero **tres promesas de este README no se
> cumplían en el código**: la decisión humana registro a registro, el
> verificador anti-alucinación en su modo por defecto, y la reproducibilidad de
> la corrida de referencia. El plan de remediación en tres olas está en el
> informe. **La Ola 0 se cerró el 2026-09-25** (PRs #8–#10): seguridad del motor
> y del exportador, un reporte rechazado ya no figura como completado, el
> auditor exige procedencia y decisión humana final, modelo por defecto vigente
> y métricas indefinidas marcadas como tales. **La Ola 1** cumple la primera
> promesa y endurece el auditor: decisión humana por registro atada a la
> solicitud revisada, corridas reanudables, preflight sin red, flujo PRISMA
> estricto y un `revisia audit` que comprueba la coherencia de la corrida y
> declara no publicable lo que no tiene un humano detrás (estado en §11 del
> informe). Sigue abierta la Ola 2: hasta que el verificador compruebe de
> verdad (C2), una síntesis sin citas marcadas no prueba que esté
> fundamentada, y las cifras del benchmark fundacional siguen siendo
> ilustrativas.
```

En el árbol de "Estructura", sustituir

```markdown
  audit.py            # auditor post-corrida (PRISMA 2020 / -S / trAIce)
```

por

```markdown
  audit/              # auditor post-corrida (PRISMA 2020 / -S / trAIce), un módulo por familia de checks
```

En la tabla de "Defaults de buenas prácticas", sustituir la fila

```markdown
| Sin metaanálisis | `effects.yml` → efectos fijos/aleatorios, I²/τ², Egger (cuando hay efectos poolables) |
```

por

```markdown
| Sin metaanálisis | `effects.yml` → efectos fijos/aleatorios, I²/τ², Egger (cuando hay efectos poolables) |
| Umbrales de calidad decorativos | `revisia audit` lee `recall_target` y `kappa_min` del protocolo: un recall bajo el umbral con exclusiones de la IA sin revisar hace la corrida **no publicable**; un κ bajo es una desviación a declarar (PRISMA 24c); el recall se informa con su intervalo de Wilson y avisa si el gold no tiene positivos suficientes |
```

- [ ] **Step 4: AGENTS.md**

En `AGENTS.md`, sustituir

```markdown
| `verificador` | Grounding de citas contra el corpus | 🤖/⚙️ (embedder, agente o existencia) | A2 | Marca citas sin respaldo; bloquea la aprobación silenciosa |
```

por

```markdown
| `verificador` | Grounding de citas contra el corpus | 🤖/⚙️ (embedder, agente o existencia) | A2 | Marca citas sin respaldo; con alguna marcada, el gate final exige humano y una adjudicación por cita (M5), y el auditor da FAIL a las que nadie adjudicó |
```

sustituir

```markdown
| `auditor` | Auditoría post-corrida (`revisia audit`) | ⚙️ determinista | A2 | Verifica evidencia PRISMA 2020/-S/trAIce en disco; PASS/WARN/FAIL |
```

por

```markdown
| `auditor` | Auditoría post-corrida (`revisia audit`) | ⚙️ determinista | A2 | Verifica la coherencia de la corrida (esquemas, instantánea del protocolo, marcas de tiempo, ledger, HITL por registro, aritmética PRISMA, umbrales, búsqueda); PASS/WARN/FAIL/N/A, *fail-closed* |
```

y sustituir

```markdown
4. **Auditor post-corrida** — `revisia audit runs/<slug>-<fecha>` verifica
   manifest, procedencia de la corrida (`provenance: pipeline`), prompts
   hash-eados, supervisión humana, decisión humana sobre el reporte final,
   exclusiones IA/humano separadas (trAIce R1), gold (WARN si κ/MCC no son
   informativos), grounding, ventana de búsqueda y registro; emite `audit.md`
   con veredicto de publicabilidad.
```

por

```markdown
4. **Auditor post-corrida** — `revisia audit runs/<slug>-<fecha>` comprueba
   que la corrida es coherente, no solo que sus ficheros existan: esquemas de
   cada artefacto, instantánea del protocolo (`00_protocol/` contra
   `run.json`), plausibilidad de las marcas de tiempo, orden del ledger,
   decisión humana en cada etapa de juicio con las etiquetas por registro
   atadas a la solicitud revisada (`request_sha256`), aritmética del flujo
   PRISMA de punta a punta, umbrales del protocolo (`recall_target`,
   `kappa_min`), citas marcadas adjudicadas, log de búsqueda y procedencia;
   emite `audit.md` con el estado de la corrida y el veredicto de
   publicabilidad. Es *fail-closed*: un error interno es FAIL, y una corrida
   con `--auto-approve` nunca es publicable.
```

- [ ] **Step 5: Auditoría §11: la Ola 1 cerrada**

En `docs/auditoria/2026-09-03-auditoria-completa.md`, sustituir el párrafo final

```markdown
Siguen abiertos, en el orden de §8: el resto de la Ola 1 (HITL por registro y
auditor exigente) y la Ola 2 (rigor y honestidad de las afirmaciones, incluido
el verificador anti-alucinación C2).
```

por

```markdown
### Ola 1 · cerrada (PR-0 a PR-E, ramas `feat/ola1-*`)

Diseño, decisiones (D1-D14) y desviaciones en
[`docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md`](../superpowers/specs/2026-10-04-ola-1-remediacion-design.md);
detalle de cambios en `CHANGELOG.md`.

| Hallazgo | Estado | Qué se hizo |
|---|---|---|
| **C1** · checkpoint humano | Cerrado | `decision.yml` por registro (`records`) y atado a su solicitud (`request_sha256`); en texto completo (A0) cada informe recuperado lleva etiqueta humana y un `unclear` solo lo resuelve un humano; `human_label` solo ante una etiqueta explícita (PR-C, PR-D). El auditor exige decisión humana en cada etapa de juicio y que el ledger, `decisions.json` y `decision.yml` digan lo mismo (PR-E). |
| **C3** · corrida de referencia | Parcial | Hecho (auditor): esquemas, aritmética del flujo, marcas de tiempo, ledger, artefactos por etapa e instantánea del protocolo; la reconstrucción con la procedencia falsificada a `pipeline` da FAIL en once checks (`tests/test_audit_c3.py`). Queda (Ola 2): regenerar el benchmark con el pipeline real. |
| **A9** · corridas no reanudables | Cerrado | `revisia run --resume`: `run.json`, instantánea en `00_protocol/`, búsqueda y dedup congelados, un diario por etapa y `llm_calls.jsonl`; reanudar no repite ninguna llamada (PR-C). |
| **A11** · auditor por existencia | Cerrado | `thresholds` lee `recall_target` y `kappa_min` (D7): un recall bajo el umbral con exclusiones de la IA sin revisar es FAIL; un κ bajo, una desviación a declarar; un gold sin potencia avisa, con el intervalo de Wilson (PR-E). Las métricas miden la propuesta de la IA (D6, PR-D). |
| **M5** · `hallucination_flagged` solo se imprimía | Cerrado | Con citas marcadas, el gate final exige humano y una adjudicación por cita (PR-D); el auditor da FAIL a una cita marcada sin adjudicar y WARN a las adjudicadas (D8, PR-E). |
| **M6** · errores de configuración a mitad de corrida | Cerrado | Preflight sin red en `validate` y `run` (código 2) antes de crear la corrida; `.env` cargado (PR-A). |
| **M11** · flujo PRISMA sin no recuperados | Cerrado | Texto completo estricto: un no recuperado no se criba con IA y va a su caja; lista 16b de excluidos con su razón; CSV PRISMA2020 con los conteos reales (PR-B). |
| **M12** · búsqueda sin registrar | Cerrado | `01_search/log.json` por base con la cadena efectiva, su hash, los parámetros, las horas y los resultados (PR-C); el auditor lo exige (`search_log`) y `search_window` usa su fecha (PR-E). |
| **M13** · trAIce y métodos con una validación fija | Cerrado | `checklist_traice.md` y `metodologia.md` dicen, gate por gate y desde el ledger, quién decidió y con qué autonomía efectiva (PR-D). |
| **M23** · negaciones de `runs/` en `.gitignore` | Cerrado | `runs/` se ignora entero: una corrida se deposita con su revisión (D11, PR-B). |

Las corridas anteriores a la Ola 1 no se reanudan ni son publicables (D13):
`revisia audit` las sigue auditando enteras, como diagnóstico.

Sigue abierta, en el orden de §8, la Ola 2 (rigor y honestidad de las
afirmaciones), incluidos el verificador anti-alucinación (C2) y la
regeneración del benchmark (C3).
```

- [ ] **Step 6: Desviaciones en el spec**

En §14 del spec, añadir tras la fila 31:

```
| 32 | §9.1 `artifacts.py` | Además de los nombres de §9.1: `Loaded[T]` (dataclass genérica congelada; `TypeVar` + `Generic` por 3.11), `LedgerView`, `SearchFailure`, `RetrievalRow`, `LegacyDecision`, `ManifestRun`, `ManifestFinalGate`, `format_validation`, `validate`, `ARTIFACT_ADAPTERS`, `MANIFEST_ADAPTERS` y `JSONL_ADAPTERS`; `RunArtifacts` memoiza cada lectura | Plan PR-E |
| 33 | §9.1-§9.2 `model.py`, `__init__` | `Verdict = tuple[Status, str]` y `STATUS_ICON`; `_enforce_invariant` convierte en FAIL los `N/A` de un informe sin ningún FAIL (red de seguridad del invariante); `AuditReport` gana `state` y `n_na` | Plan PR-E |
| 34 | §9.2 `derive_state` | `completed` también con `auto-proceed` en `reporte`; `reached` incluye `reporte` cuando la pausa es en `reporte`; `interrupted` sale de `run.json.stage` o, sin `run.json`, del primer gate de juicio sin decisión ni solicitud | Plan PR-E |
| 35 | §9.3 `schemas` | No valida el ledger (lo hace `ledger`, con número de línea); valida las secciones del manifiesto con modelo y `decision.yml`, este con `LegacyDecision` en una corrida sin `run.json` (D13 ya da FAIL en `protocol_snapshot`) | Plan PR-E |
| 36 | §9.3 `manifest` y llamadas | `manifest` comprueba sus propias `llm_calls`; los demás checks leen `llm_calls.jsonl` si existe. `arithmetic` añade `manifest.llm_calls == llm_calls.jsonl` y el orden de T/A igual al de `02_dedup/records.json` | Plan PR-E |
| 37 | §9.3 `hitl` | FAIL también ante una decisión humana sin su `review_request.yml` (así es la reconstrucción C3); las reglas por registro solo se aplican con `run.json`; la relación 5 (L ≠ H) vive en `hitl` | Plan PR-E |
| 38 | §9.3 `final_gate` | FAIL a una aprobación humana sin `reporte/review_request.yml`; el detalle de una pausa es "corrida en pausa en `X`: sin decisión final." y añade la relación 18 cuando `run.json` dice `completed` | Plan PR-E |
| 39 | §9.3 `request_hash` | `N/A` sin `run.json`; `records`, `artifact_sha256` y `documento_sha256` se comprueban solo si la solicitud lleva esas claves | Plan PR-E |
| 40 | §9.3 `search_log` | Con una búsqueda inyectada (`search_fn`) no se exige una entrada por base declarada: WARN | Plan PR-E |
| 41 | §9.3 `thresholds` | `potencia_minima(target) = ⌈1/(1−umbral)⌉` redondeando a 9 decimales antes del techo (0,95 → 20 y 0,8 → 5 pese a la coma flotante); con umbral ≥ 1, `None` (nunca hay potencia) | Plan PR-E |
| 42 | §9.4 tests | Renombrados por su expectativa nueva: `test_audit_sin_decisiones_humanas_falla_hitl`, `test_audit_gate_final_auto_approve_no_es_humano_falla`, `test_audit_gate_final_auto_proceed_falla`. La fase 1 simula la pausa en FT (`pausar_en_screening_ft`); la fase 2 la sustituye por una corrida detenida de verdad (`corrida_en_pausa_ft`) | Plan PR-E |
| 43 | §9.4 fixtures | La reconstrucción C3 tiene 28 identificados con `identified_by_source` 40/40/40 y sin CSV de interop; en la fase 2 el gold va en `gold.yml` (copia del demo) porque `correr_hasta` no pasa `gold_labels`; D8 se prueba además sobre una corrida real cuya síntesis cita `[2019]`, adjudicada con `flags` | Plan PR-E |
| 44 | §9 CLI | `revisia audit` alinea la columna del check a 17 caracteres (`protocol_snapshot`) y muestra `➖ N/A` | Plan PR-E |
| 45 | §10 rebase de E | `git rebase --onto feat/ola1-hitl-por-registro feat/ola1-contratos feat/ola1-auditor`: solo se reaplican los commits de E aunque PR-0 haya recibido correcciones después de crear su worktree | Plan PR-E |
```

- [ ] **Step 7: Commit de documentación**

```bash
git -C C:/revisia-wt/e add CHANGELOG.md README.md AGENTS.md docs/auditoria/2026-09-03-auditoria-completa.md docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md
git -C C:/revisia-wt/e commit -m "docs: cierre de la Ola 1 (auditor exigente, README, AGENTS, auditoría §11)" -m "CHANGELOG del auditor exigente (C3, A11, M5); el README pierde la nota de limitación y explica qué comprueba revisia audit; AGENTS.md describe el auditor y el verificador como son ahora; §11 de la auditoría registra la Ola 1 como cerrada; desviaciones de PR-E en §14 del spec." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Verificación completa (en `C:\revisia-wt\e`)**

Run: `uv run pytest -p no:cacheprovider`
Expected: en verde, `N_D + 243` recogidos (742), 2 skipped.

Matriz 3.11/3.12 con venv desechable:

```bash
TMP="$(mktemp -d)"
for PY in 3.11 3.12; do
  uv venv -q --python "$PY" "$TMP/venv$PY"
  uv pip install -q --python "$TMP/venv$PY" pydantic pyyaml python-dotenv markdown httpx nh3 pytest
  PYTHONPATH=. "$TMP/venv$PY/Scripts/python" -m pytest -p no:cacheprovider -q
done
```

Expected: en verde en ambas versiones.

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`
Expected: limpio.

- [ ] **Step 9: Criterio de cierre de la Ola 1 (spec §11), de punta a punta y sin red**

Con el demo y el proveedor fake con guion; la búsqueda y la recuperación de texto completo se sustituyen en el módulo, como en los tests. Todo lo demás pasa por el CLI real (`revisia run` → pausa → `decision.yml` con el `request_sha256` → `revisia run --resume` → … → `revisia audit`):

```bash
cd C:/revisia-wt/e
PYTHONIOENCODING=utf-8 uv run python - <<'PY'
"""Criterio de cierre de la Ola 1 (spec 2026-10-04 §11), de punta a punta y sin red.

El demo con proveedores ``fake`` con guion (``tests/fakes.py``); la búsqueda y la
recuperación de texto completo se sustituyen en el módulo, como en los tests, y
el preflight ve ``httpx`` aunque el venv de desarrollo no lo instale. Todo lo
demás pasa por el CLI real: ``revisia run`` → pausa → ``decision.yml`` con el
``request_sha256`` → ``revisia run --resume`` → … → ``revisia audit``.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, "tests")
from audit_fixtures import write_c3_reconstruction
from fakes import ScriptedProvider, fetch_disponible

from revisia import cli
from revisia.agents import fulltext as fulltext_agent
from revisia.agents import search_backends
from revisia.audit import run_audit
from revisia.llm import preflight
from revisia.orchestration import pipeline as pipeline_mod
from revisia.schemas.records import SearchRecord

REGISTROS = [
    SearchRecord(record_id="e2e-1", title="LLM screening for systematic reviews", source_db="OpenAlex"),
    SearchRecord(record_id="e2e-2", title="Active learning with ASReview", source_db="OpenAlex"),
    SearchRecord(record_id="e2e-3", title="Estudio irrelevante de cocina", source_db="OpenAlex"),
]

pipeline_mod.build_provider = lambda cfg: ScriptedProvider(model=cfg.model)
search_backends.search_database = lambda db, query, n, *, mailto=None: [
    r.model_copy() for r in REGISTROS
]
fulltext_agent.fetch_fulltext = lambda record, mailto=None: fetch_disponible(record)
preflight._default_find_spec = lambda name: object()

root = Path(tempfile.mkdtemp())
demo = root / "demo-mini-review"
shutil.copytree("examples/demo-mini-review", demo)

# 1 · Con un humano en cada gate → APTA.
runs = root / "runs"
assert cli.main(["run", str(demo), "--runs-root", str(runs)]) == 0  # pausa en screening_ta
run_dir = next(runs.iterdir())
for _ in range(10):
    info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if info["status"] == "completed":
        break
    stage = info["stage"]
    request = yaml.safe_load((run_dir / stage / "review_request.yml").read_text(encoding="utf-8"))
    decision = {
        "request_sha256": request["request_sha256"],
        "approved": True,
        "actor": "human:revisora",
    }
    if request.get("must_label"):
        proposals = {r["record_id"]: r.get("proposal") for r in request.get("records", [])}
        decision["records"] = {
            rid: (
                {"label": "exclude", "reason": "fuera de alcance"}
                if proposals.get(rid) == "exclude"
                else {"label": "include", "reason": None}
            )
            for rid in request["must_label"]
        }
    (run_dir / stage / "decision.yml").write_text(
        yaml.safe_dump(decision, allow_unicode=True), encoding="utf-8"
    )
    assert cli.main(["run", "--resume", str(run_dir)]) == 0
assert info["status"] == "completed", info
assert cli.main(["audit", str(run_dir)]) == 0, "la corrida con humano debería ser APTA"

# 2 · La misma corrida con --auto-approve → NO publicable.
runs_auto = root / "runs-auto"
assert cli.main(["run", str(demo), "--runs-root", str(runs_auto), "--auto-approve"]) == 0
assert cli.main(["audit", str(next(runs_auto.iterdir()))]) == 1

# 3 · La reconstrucción C3 con la procedencia falsificada → NO publicable por ≥ 7 checks.
c3 = write_c3_reconstruction(root / "c3", provenance="pipeline")
fails = [c.check_id for c in run_audit(c3).checks if c.status == "FAIL"]
assert cli.main(["audit", str(c3)]) == 1
assert len(fails) >= 7, fails
print(f"\nE2E Ola 1 OK · C3 no publicable por {len(fails)} checks: {', '.join(fails)}")
PY
```

Expected: la corrida con humano pausa en cada uno de los cinco gates, termina `completed` y `revisia audit` sale con 0 (`✅ APTA para preparar publicación`, con WARN en `manifest` por ser una corrida de demostración); la corrida con `--auto-approve` sale con 1 (`❌ NO publicable`: FAIL en `hitl` y `final_gate`); la reconstrucción C3 sale con 1 y la última línea es `E2E Ola 1 OK · C3 no publicable por 11 checks: schemas, protocol_snapshot, timing, ledger, hitl, final_gate, stage_artifacts, arithmetic, exclusions, deliverable, search_log`.

- [ ] **Step 10: Publicar y abrir PR-E (sin merge)**

Si los Steps 1 y 8 dieron otros conteos que 742 y 499, corrígelos en la sección "Verificación" del cuerpo:

```bash
git -C C:/revisia-wt/e push -u origin feat/ola1-auditor
gh pr create --base feat/ola1-hitl-por-registro --head feat/ola1-auditor --title "Ola 1 · PR-E: auditor exigente y cierre de la ola (C3-auditor, A11, M5)" --body "$(cat <<'EOF'
## Qué cierra

- C3 en la parte del auditor (auditoría 2026-09-03): `revisia audit` aprobaba la reconstrucción de la corrida de referencia porque solo miraba que los ficheros existieran.
- A11: los umbrales `recall_target` y `kappa_min` del protocolo no los leía nadie (κ = 0,0 salía PASS).
- M5 en el auditor: una cita marcada sin adjudicar ya no deja la corrida publicable (D8).
- Con esta PR se cierra la Ola 1 (README sin la nota de limitación, `AGENTS.md`, §11 de la auditoría).

## Qué cambia

- `revisia/audit.py` → paquete `revisia/audit/` (`model`, `artifacts`, `state`, `checks_*`, `render`). Loaders que nunca lanzan, registro ordenado de checks y *fail-closed*: una fila por check, un error interno es FAIL y un `N/A` nunca aparece sin algún FAIL.
- Estado de la corrida (completada, en pausa, interrumpida, rechazada): los checks de etapas no alcanzadas dan `N/A` y el gate final dice dónde se detuvo.
- Checks nuevos: `schemas`, `protocol_snapshot` (D13), `timing`, `ledger` (relación 16), `request_hash` (relación 15), `stage_artifacts`, `arithmetic` (relaciones 1-14 de §4.4 y las de §9.3), `thresholds` (D7, con Wilson y potencia del gold), `search_log`, `response_overlap`.
- `hitl` y `final_gate` exigentes: `--auto-approve`, una etapa de juicio sin humano o un gate final sin aprobación humana son FAIL (D8); etiquetas por registro coherentes entre ledger, `decisions.json` y `decision.yml` (D1).
- `revisia.metrics.kappa_from_matrix` y `wilson_interval`, públicas.
- Tests sobre una corrida real del pipeline (`tests/conftest.py`), no fabricada a mano; la reconstrucción C3 con la procedencia falsificada (`tests/audit_fixtures.py`).

## Cambios incompatibles

- Auto-approve, recall bajo umbral sin revisar y citas marcadas sin adjudicar pasan a FAIL.
- Las corridas anteriores a la Ola 1 (sin `run.json`) no son publicables (D13).
- `AuditCheck.status` admite `N/A`; `AuditReport` gana `state` y `n_na`.

## Verificación

- `uv run pytest -p no:cacheprovider`: 742 recogidos, en verde (base PR-D: 499).
- La misma suite en 3.11 y 3.12 con venv desechable: en verde.
- `ruff check`, `ruff format --check`, `black --check`, `uv lock --check`: limpios.
- Criterio de cierre de la Ola 1 (§11), de punta a punta y sin red: `revisia run` → pausa → `decision.yml` con el hash → `revisia run --resume` → … → `revisia audit` **APTA**; la misma corrida con `--auto-approve` → **NO publicable**; la reconstrucción C3 con la procedencia falsificada → **NO publicable** por once checks.

## Pila

`main` ← PR-0 ← PR-A ← PR-B ← PR-C ← PR-D ← **PR-E**. Base: `feat/ola1-hitl-por-registro`. Nunca `--delete-branch` mientras otra PR use una rama como base.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR.

- [ ] **Step 11: Traspaso al arquitecto**

El merge lo decide el arquitecto, en el orden de la pila (`0 → A → B → C → D → E`). Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base: merge sin borrar → `gh pr edit <n> --base main` en la siguiente → borrar la rama → cerrar y reabrir la PR para disparar el CI (spec §10). La versión 0.8.0 (D13) la publica el arquitecto; este plan no toca `revisia.__version__` ni `pyproject.toml`.

---

## Self-review

**1. Cobertura de §9.3 (un check, una tarea que lo implementa y su test):**

| # | Check | Fase 1 | Fase 2 |
|---|---|---|---|
| 1 | `manifest` | T4 (portado), T5 | T12 (bloques nuevos en `schemas`) |
| 2 | `provenance` | T4, T5 | — |
| 3 | `schemas` | T5 | T12 (artefactos nuevos, `.jsonl` por línea, `LegacyDecision`) |
| 4 | `protocol_snapshot` | — | T12 |
| 5 | `prompts` | T4, T5 | — |
| 6 | `timing` | T6 | T13 (`run.json` y log, relación 14) |
| 7 | `ledger` | T5 | T15 (relación 16) |
| 8 | `hitl` | T8 | T11 (corrida real con etiquetas), T15 (por registro) |
| 9 | `request_hash` | — | T15 |
| 10 | `final_gate` | T8 | T15 (relaciones 17 y 18), T16 (frontera) |
| 11 | `stage_artifacts` | T7 | T12 |
| 12 | `arithmetic` | T7 (v0.7 y §9.3) | T14 (relaciones 1-13) |
| 13 | `exclusions` | T7 | — |
| 14 | `deliverable` | T7 | T12 (16b) |
| 15 | `gold` | T4, T9 | — |
| 16 | `thresholds` | T9 | T15 (rebaja a WARN, D7) |
| 17 | `grounding` | T9 | T15 (marca real adjudicada) |
| 18 | `search_log` | — | T13 |
| 19 | `search_window` | T9 | T13 (fecha del motor) |
| 20 | `registration` | T4 | T12 (lee la instantánea) |
| 21 | `response_overlap` | T6 | — |

§9.1 (paquete, `kappa_from_matrix`, `wilson_interval`, invariantes): T1, T2, T4. §9.2 (estado y `N/A`): T4, con la pausa simulada en T3/T8 y la real en T11. §3: D7 en T9 y T15 (umbral según lo que mide, potencia ⌈1/(1−umbral)⌉, Wilson); D8 en T8 (`hitl`, `final_gate`), T9 y T15 (`grounding`); D13 en T7 (`write_legacy_v07`) y T12 (`protocol_snapshot`, mensaje exacto). §4.4: relaciones 1-14 en T7/T13/T14, 15 y 16 en T15, 17 y 18 en T15.

**2. Tests de §9.4:** los cambios de expectativa de la tabla de §9.4 están en T3 (`_make_run` fuera, la corrida real), T4 (`N/A` en vez de "id ausente"), T5 (`gold` con `ScreeningMetrics` válido), T8 (los tres renombrados) y T16 (`test_paused_run_final_gate_falla_en_auditoria`). Familias nuevas: robustez y render (T4), `schemas`/`ledger` (T5), `timing` (T6), `arithmetic`, `exclusions`, `deliverable` (T7, T12, T14), `hitl` y estado (T8, T11, T15), `thresholds`/`grounding` (T9, T15), C3 (T10), `request_hash` (T15), `search_*` y `protocol_snapshot` (T12, T13), frontera del contrato (T16).

**3. Sin marcadores pendientes:** no hay marcadores de trabajo pendiente, remisiones a otra tarea en lugar de código ni pasos sin código; cada paso que cambia un fichero trae el contenido completo o el fragmento exacto a sustituir, que aparece una sola vez en el fichero (comprobado aplicando el plan sobre copias limpias). `N_D` (499 según el plan B) es el único número que el controlador confirma al ejecutar (Tarea 11); los conteos de la fase 2 se dan también en absoluto.

**4. Firmas coherentes entre tareas:** lo que produce una tarea es lo que consumen las siguientes (`Loaded`, `RunArtifacts`, `AuditContext`, `RunState`, `CheckSpec`, `Verdict`, los helpers de `audit_fixtures`); los nombres de PR-0 a PR-D se toman del contrato del plan B y se verificaron contra su prototipo final.

**5. Verificación al escribir el plan:** fase 1 tarea a tarea sobre PR-0 (364 → 514, lint limpio, 3.11 en verde); fase 2 tarea a tarea sobre el prototipo final del plan B con la fase 1 rebasada (499 + 150 → 742, lint limpio, 3.11 y 3.12 en verde). Un script reaplicó el texto de este plan sobre copias limpias: la fase 1 entera (T1-T10, conteo y lint en cada tarea, resultado idéntico al código verificado) y, sobre el prototipo del plan B, la fase 1 rebasada más T11 y T12 (con sus pasos rojos: 145 errores tras el rebase, `ImportError` de `LEGACY_RUN`); para T13-T16 el replay no llegó a terminar, pero sus bloques salen del mismo código verificado y el generador comprueba que reconstruyen cada fichero. La documentación de la Tarea 17 se aplicó sobre la de PR-D simulada desde los planes A y B (cada fragmento, único) y el E2E de la Tarea 17 Step 9, tal como está escrito, pasó.

---

## Desviaciones respecto del spec

Ninguna reabre D1-D14. Son precisiones que el spec deja abiertas o decisiones de implementación; el integrador las registra en §14 (Tarea 17 Step 6, filas 32-45):

1. **Nombres extra en `artifacts.py`** (§9.1): `Loaded[T]` es una dataclass genérica congelada (`TypeVar` + `Generic`, por 3.11); además `LedgerView`, `SearchFailure`, `RetrievalRow`, `LegacyDecision`, `ManifestRun`, `ManifestFinalGate`, `format_validation`, `validate`, `ARTIFACT_ADAPTERS`, `MANIFEST_ADAPTERS` y `JSONL_ADAPTERS`; `RunArtifacts` memoiza cada lectura.
2. **`Verdict = tuple[Status, str]`, `STATUS_ICON` y `_enforce_invariant`** (§9.1-§9.2): la red de seguridad del invariante convierte en FAIL los `N/A` de un informe sin ningún FAIL. `AuditReport` gana `state` y `n_na`.
3. **`derive_state`** (§9.2): `completed` también con `auto-proceed` en `reporte`; `reached` incluye `reporte` cuando la pausa es en `reporte`; `interrupted` sale de `run.json.stage` o del primer gate sin decisión ni solicitud.
4. **`schemas`** (§9.3 fila 3): no valida el ledger (es de `ledger`, con número de línea); valida las secciones del manifiesto con modelo y `decision.yml` (con `LegacyDecision` sin `run.json`).
5. **Llamadas** (§9.3 filas 1 y 12): `manifest` comprueba sus propias `llm_calls`; los demás checks leen `llm_calls.jsonl` si existe; `arithmetic` añade `manifest.llm_calls == llm_calls.jsonl` y el orden de T/A.
6. **`hitl`** (fila 8): FAIL también ante una decisión humana sin su `review_request.yml`; reglas por registro solo con `run.json`; la relación 5 (L ≠ H) se comprueba aquí.
7. **`final_gate`** (fila 10): FAIL a una aprobación humana sin `reporte/review_request.yml`; detalle "corrida en pausa en `X`: sin decisión final." con la nota de la relación 18.
8. **`request_hash`** (fila 9): `N/A` sin `run.json`; `records`, `artifact_sha256` y `documento_sha256` solo si la solicitud los trae.
9. **`search_log`** (fila 18): con una búsqueda inyectada no se exige una entrada por base declarada (WARN).
10. **`potencia_minima`** (D7): redondeo a 9 decimales antes del techo; `None` con umbral ≥ 1.
11. **Tests renombrados** (§9.4): `…_falla_hitl`, `…_auto_approve_no_es_humano_falla`, `…_auto_proceed_falla`; la pausa en FT se simula en la fase 1 y es real en la fase 2.
12. **Fixtures** (§9.4): C3 con 28 identificados (40/40/40 por base) y sin CSV de interop; gold de la fase 2 en `gold.yml`; D8 probado además sobre una corrida real con `[2019]` adjudicado.
13. **CLI**: columna de 17 caracteres y `➖ N/A`.
14. **Rebase con `--onto`** (§10): solo se reaplican los commits de E, aunque PR-0 cambie después de crear el worktree (el plan B, Tarea 28 Step 9, usa el mismo comando).

Además, decisiones internas del plan que no cambian el spec: la Tarea 4 porta los checks de hoy a sus módulos antes de reescribirlos (cada tarea posterior parte de un auditor en verde); `checks_search` importa `parse_utc` de `checks_timing`; la autonomía efectiva sale de `manifest.autonomy_effective` cuando existe.

## Pendientes de conciliación (firmas consumidas de PR-C/PR-D)

La fase 2 consume estos nombres tal como los define el contrato del plan B ("Contrato para el auditor") y su prototipo final. Si PR-D cambia alguno al integrarse, el controlador lo concilia en la Tarea 11 antes de seguir:

- `tests/hitl_helpers.py`: `correr_hasta(protocol, protocol_dir, ctx, *, search_fn, fetch_fn=None, etiquetar=None, parar_en=None, max_vueltas=10) -> PipelineResult` (y, a través de él, `responder_gate(..., records=None, flags=None)`, `aceptar_lo_obligatorio` y `RunContext.open`).
- `tests/fakes.py`: `ScriptedProvider(model, *, fail_at=None, palabras=None, criterio_exclusion="fuera de alcance", sintesis=None)`, `fetch_disponible`.
- `revisia.orchestration.snapshot`: `SNAPSHOT_DIR`, `protocol_fingerprint(protocol_dir) -> dict[str, str]`.
- `revisia.orchestration.hitl.HumanDecision` (`request_sha256`, `approved`, `actor`, `reason`, `records: dict[str, RecordLabel]`, `flags: dict[str, FlagReview]`).
- `revisia.schemas.artifacts`: `RunInfo` (`slug`, `started_utc`, `protocol_sha256`, `resumes`, `interruptions[].utc`, `status`, `stage`), `RunStatus`, `LLMCall`, `JournalEntry`, `SearchLog`/`SearchLogEntry`, `DedupReport`, `RetrievalOutcome`, `ExcludedReport`, `GateSummary`, `JOURNAL_PATHS`.
- `revisia.provenance.runmeta.canonical_sha256`, `sha256_text`; `revisia.agents.search_backends.db_key`.
- Formatos en disco del contrato: claves de `review_request.yml` por gate (`records[].record_id`/`proposal`, `must_label`, `must_resolve`, `artifact_sha256`, `documento_sha256`, `must_adjudicate`, `forced_human`), `detail` de `label`/`flag_review`/`approve`, campos humanos de `decisions.json`, bloques `run`/`autonomy_effective`/`final_gate` del manifiesto, `llm_calls.jsonl`, `01_search/`, `02_dedup/`, `03_screening/gold.json`, `04_fulltext/retrieval.json` y `excluded.json`, y la lista 16b del entregable.
