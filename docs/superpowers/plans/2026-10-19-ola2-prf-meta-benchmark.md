# Ola 2 · PR-F `feat/ola2-meta-benchmark` (meta-análisis por desenlace y benchmark) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el meta-análisis se haga por desenlace, ligado a los estudios incluidos y a su unidad de análisis (intervalo de predicción, Egger solo con k ≥ 10, subgrupos, duplicados y HKSJ opcional), y que el motor traiga `revisia benchmark` y `revisia benchmark-report` para validar modelos de cribado sobre un corpus congelado contra un gold, sin volver a citar 0,820 ni I² 90,7 % como evidencia (C3-benchmark, D6, D16, D23).

**Architecture:** F se hace en dos fases (§15). **F₁** (este documento, desde PR-0, en paralelo con A, B, C, D y E₁) cambia solo módulos que §15 asigna a F y que no dependen del pipeline: `meta_analysis.py` pasa a la forma v2 por desenlace **bajo los mismos nombres** (`meta_analyze`, `MetaAnalysisResult`), con dos propiedades de compatibilidad (`k`, `studies`) que mantienen intactos `pipeline.py` y `exports/methods.py` hasta F₂; el auditor no se toca y sigue coherente porque recalcula con la misma `meta_analyze` y renderiza con las mismas funciones; `protocol_files.EffectsFile` v2 exige `outcome`; los renders (Markdown, CSV de metafor, PNG) pasan a ser por desenlace; y `revisia benchmark-report` lee `benchmark.json`, construye efectos `logit(recall)` y escribe `pooled/`. **F₂** (otro redactor, sobre PR-E) liga el meta-análisis a los incluidos en el pipeline (`_meta_analysis(run, included_ids)`, `excluded_effects.json`, declaraciones), añade `stop_after`, `kind: benchmark` y el comando `revisia benchmark` completo con su preflight.

**Tech Stack:** Python 3.13 (suite también en 3.11/3.12 cuando PR-H esté debajo), Pydantic v2, PyYAML, pytest, ruff + black (línea 100), uv. Estadística en Python puro (sin numpy): `scipy` sigue siendo opcional y solo da los p-valores exactos de Q y de Egger, como hoy. `matplotlib` (extra `meta`) solo para los PNG.

**Spec:** `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`. Este plan implementa §10 (PR-F), D6, D16 y D23 en lo que no depende del pipeline, con los contratos de §4.2 («EffectInput v2 / EffectsFile v2 / MetaAnalysisResult v2 / ExcludedEffect», «BenchmarkPanel / BenchmarkResult»), la relación 29 (§4.3) como contrato para G₂, §15 (topología), §16 (método) y **§19 filas 1–8**, que vinculan (sobre todo la fila 3: `outcome` opcional en el modelo y obligatorio en `EffectsFile`; un efecto sin desenlace se agrupa como desenlace único; la forma por desenlace la define este plan). Plan hermano: `2026-10-18-ola2-pr0-contratos.md`, cuyas Tareas 12 y 13 dan los nombres que aquí se consumen tal cual.

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes y commits **en español**, con el tono del repo. Las docstrings citan la decisión («D16») o la fuente estadística (Higgins, Thompson y Spiegelhalter 2009; IntHout, Ioannidis y Borm 2014; Sterne et al. 2011; Cochrane Handbook §10.11.3.1 y §23.3).
- Estilo: `ruff` (`E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100), limpios en cada commit. `from __future__ import annotations` en todo módulo nuevo, también en `tests/`.
- **F₁ no toca** `revisia/orchestration/pipeline.py`, `revisia/exports/methods.py` ni nada bajo `revisia/audit/` (§15: el pipeline va en secuencia B→C→D→E→F₂; `methods.py` lo tocan A, C, D y E antes; `audit/*` es solo de G, y G₁ lo está partiendo en paralelo). La compatibilidad hasta F₂ es la de la Tarea 3.
- De `revisia/exports/interop.py` (E toca `render_robvis_csv`) F₁ solo cambia `render_metafor_csv`.
- Tests offline y deterministas; ninguno invoca `claude`, APIs ni WeasyPrint. Los que necesitan `scipy` o `matplotlib` usan `pytest.importorskip` **después** de las aserciones que no los necesitan.
- Los números que el auditor compara (`checks_flow.py:1843-1877`, todo salvo `p_value`/`p_method`, `checks_flow.py:151`) no pueden depender de que `scipy` esté instalado: intervalo de predicción y HKSJ usan la t de Student en Python puro de la Tarea 2.
- Línea base: la suite de PR-0 en verde (recuento final anotado en el cuerpo de la PR-0; parte de 2 103 en `main` @ `c1af7c3`). Ningún test existente se borra; los que cambian de expectativa se listan en su tarea con el cambio exacto.
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"` y después `uv run pytest -p no:cacheprovider -m cronometrado`; lint, `uv run ruff check . && uv run ruff format --check . && uv run black --check .`.
- Commits pequeños, al menos uno por tarea, en español con prefijo convencional, terminados con `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- **Los implementadores no tocan** `CHANGELOG.md`, `README.md`, `AGENTS.md`, `docs/` (salvo este plan) ni el spec (§15): los actualiza el integrador al cerrar PR-F (fase F₂).
- No cambiar `revisia.__version__` ni `pyproject.toml`. No tocar `runs/` ni `protocols/<slug>/` distintos de `_TEMPLATE`; `protocols/prisma-ia-origen/` es del arquitecto (git-ignorado) y ningún test lo lee.
- Convenciones de la Ola 1 (§4): `canonical_json`, horas ISO-8601 UTC (`utc_now_iso`, `revisia/provenance/runmeta.py:28`), rutas relativas con `/`, ningún `record_id` ni nombre de desenlace como nombre de fichero.
- `tests/` no es un paquete: los dobles se importan como `from fakes import …`.
- Los números de línea citados son de `main` @ `c1af7c3`; PR-0 añade modelos tras `EffectInput` (`schemas/effects.py:23`) y `schema_version` a `MetaAnalysisResult` (`meta_analysis.py:96`), así que pueden desplazarse unas líneas.

## Review Focus

Entradas que el spec implica y que ninguna tarea probaría sin estas líneas; cada una tiene su test en la tarea dueña:

1. **Un `effects.yml` legado (sin `outcome`) en la instantánea de una corrida 0.8 que se reanuda** debe salir con rc 2 y el mensaje de migración, no con un `ValidationError` crudo ni un traceback (D12: no reanudable, pero con mensaje). → Tarea 7 (los casos nuevos entran en `CASOS_INVALIDOS`, que ya se prueba con `validate`, `run` y `--resume`).
2. **El auditor en un equipo sin `scipy` frente a un motor con `scipy`**: el intervalo de predicción y el IC de HKSJ deben salir idénticos, o la relación «`meta_analysis.json` == `meta_analyze(...)`» daría FAIL por entorno. → Tarea 5 (`test_sin_scipy_los_numeros_que_compara_el_auditor_no_cambian`).
3. **Efectos idénticos con HKSJ** (Q = 0, τ² = 0, varianza de Hartung-Knapp 0): no puede haber `ZeroDivisionError`; el IC colapsa al punto y se declara. → Tarea 5.
4. **Un desenlace escrito con espacios alrededor** (`"mortalidad "` frente a `"mortalidad"`) partiría en silencio un desenlace en dos: se rechaza al cargar. → Tarea 7.
5. **Un `benchmark.json` con una celda de recall indefinido** (`tp + fn == 0`) o con registros fallidos no puede romper `benchmark-report` (división por cero en el logit) ni entrar sin nota. → Tarea 8.

---

## Topología de ejecución (subagentes)

F₁ se ejecuta en secuencia en el worktree `C:\revisia-wt\f` (rama `feat/ola2-meta-benchmark`, creada desde `feat/ola2-contratos` en la Tarea 17 de PR-0), en paralelo con H, A, B, C, D y E₁ en sus propios worktrees. F₂ continúa en la misma rama tras rebasarla sobre PR-E (§15: «0 (F₁) → E (F₂)»); los conflictos esperables al rebasar son los de `tests/test_auditor_meta_y_estados.py` (G₁ puede cambiar sus imports al partir `checks_flow.py`) y ninguno en código de producción.

| Tarea | Fichero(s) | Depende de |
|---|---|---|
| 1 | worktree y línea base | PR-0 cerrada |
| 2 | `revisia/meta_analysis.py` (t de Student) | 1 |
| 3 | `revisia/meta_analysis.py` (forma v2), `revisia/exports/forest.py`, `revisia/exports/interop.py` (`render_metafor_csv`), `revisia/exports/__init__.py`, tests | 2 |
| 4 | `revisia/meta_analysis.py` (PI, duplicados), `revisia/exports/forest.py` | 3 |
| 5 | `revisia/meta_analysis.py` (HKSJ), `revisia/exports/forest.py` | 4 |
| 6 | `revisia/meta_analysis.py` (subgrupos), `revisia/exports/forest.py` | 5 |
| 7 | `revisia/protocol_files.py`, `examples/demo-mini-review/effects.yml`, tests | 3 |
| 8 | `revisia/benchmark/__init__.py`, `revisia/benchmark/report.py` | 6 |
| 9 | `revisia/cli.py` (`benchmark-report`) | 8 |

**Ciclo por tarea (§16):** implementador (subagente nuevo, TDD estricto: test rojo → código mínimo → verde → lint → commit) → revisor (subagente nuevo: primero cumplimiento del spec y de este plan, después calidad) → correcciones. Desviaciones descubiertas en revisión se corrigen y se anotan para §19 (las registra el integrador al cerrar PR-F), no se consultan, salvo que cambien una decisión D1–D6. **El merge lo decide el arquitecto.**

---

## Fase F₁ (desde PR-0)

### Tarea 1: Worktree y línea base (controlador)

**Files:** ninguno.

**Interfaces:** ninguna de código.

- [ ] **Step 1: Worktree.** Si la Tarea 17 de PR-0 no lo creó: `git worktree add C:\revisia-wt\f -b feat/ola2-meta-benchmark feat/ola2-contratos`. Después `uv sync --extra dev --extra search --extra meta` en el worktree (scipy y matplotlib entran con `meta`).

- [ ] **Step 2: Comprobar los contratos de PR-0 que se consumen.**

Run: `uv run python -c "from revisia.schemas.effects import EffectInput, RandomMethod, MultiplePerStudy, ExcludedEffect, ExcludedEffectsFile, PredictionInterval, DuplicateEffect; from revisia.schemas.benchmark import BenchmarkResult, BenchmarkCellResult, BenchmarkProtocolInfo; from revisia.meta_analysis import MetaAnalysisResult; print(MetaAnalysisResult.model_fields['schema_version'].default)"`
Expected: imprime `2`.

- [ ] **Step 3: Línea base.**

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS; anotar el recuento.

---

### Tarea 2: t de Student en Python puro (`revisia/meta_analysis.py`)

El intervalo de predicción y HKSJ necesitan cuantiles de t. Con `scipy` opcional, un cálculo «con scipy si está» daría números distintos en el motor y en el auditor, y `_meta_distinto` (`audit/checks_flow.py:1843`) solo ignora `p_value`/`p_method`. Por eso son de Python puro siempre.

**Files:**
- Modify: `revisia/meta_analysis.py` (funciones nuevas tras `_t_sf_two_sided`, línea 46; `_t_sf_two_sided` de Egger no cambia).
- Test: `tests/test_t_student.py` (nuevo).

**Interfaces:**
- Produces: `student_t_sf(t: float, df: int) -> float` (P(T > t), cualquier signo de `t`; `df ≥ 1`, si no `ValueError`) y `student_t_quantile(p: float, df: int) -> float` (cuantil de cola inferior para `0.5 < p < 1`, si no `ValueError`).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_t_student.py`:

```python
"""t de Student en Python puro para PI y HKSJ (spec 2026-10-18 §10.1; Tarea 2 del plan PR-F)."""

from __future__ import annotations

import pytest

from revisia.meta_analysis import student_t_quantile, student_t_sf


@pytest.mark.parametrize(
    ("df", "esperado"),
    [
        (1, 12.7062047362),
        (2, 4.3026527297),
        (8, 2.3060041352),
        (11, 2.2009851601),
        (12, 2.1788128297),
        (30, 2.0422724563),
    ],
)
def test_cuantil_0975_contra_tablas(df: int, esperado: float) -> None:
    assert student_t_quantile(0.975, df) == pytest.approx(esperado, abs=1e-9)


def test_cola_y_cuantil_son_inversos_y_simetricos() -> None:
    for df in (1, 3, 11, 50):
        q = student_t_quantile(0.9, df)
        assert student_t_sf(q, df) == pytest.approx(0.1, abs=1e-12)
        assert student_t_sf(-q, df) == pytest.approx(0.9, abs=1e-12)
    assert student_t_sf(0.0, 7) == pytest.approx(0.5, abs=1e-15)


@pytest.mark.parametrize(("p", "df"), [(0.5, 3), (1.0, 3), (0.2, 3), (0.975, 0)])
def test_fuera_de_dominio_falla(p: float, df: int) -> None:
    with pytest.raises(ValueError):
        student_t_quantile(p, df)


def test_coincide_con_scipy_si_esta() -> None:
    stats = pytest.importorskip("scipy.stats")
    for df in range(1, 120):
        for p in (0.9, 0.95, 0.975, 0.995):
            assert student_t_quantile(p, df) == pytest.approx(float(stats.t.ppf(p, df)), abs=1e-10)
        for t in (0.1, 1.0, 2.5, 7.0):
            assert student_t_sf(t, df) == pytest.approx(float(stats.t.sf(t, df)), abs=1e-12)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_t_student.py -v`
Expected: FAIL (`ImportError: cannot import name 'student_t_quantile'`).

- [ ] **Step 3: Implementar.** El algoritmo no lo determinan la firma ni los tests; es este (Press et al., *Numerical Recipes* 3.ª ed., §6.4):
  - Beta incompleta regularizada `I_x(a, b)` por fracción continua con el método de Lentz modificado (`tiny = 1e-300`, `eps = 1e-15`, hasta 300 iteraciones; `ArithmeticError` si no converge), prefactor `exp(lgamma(a+b) − lgamma(a) − lgamma(b) + a·log x + b·log1p(−x))`, usando la fracción de `I_x(a,b)` si `x < (a+1)/(a+b+2)` y `1 − I_{1−x}(b,a)` si no.
  - `student_t_sf(t, df)`: `x = df/(df + t²)`; `cola = ½·I_x(df/2, ½)`; devuelve `cola` si `t ≥ 0`, `1 − cola` si no.
  - `student_t_quantile(p, df)`: bisección sobre `student_t_sf(·, df) = 1 − p` en `[0, hi]`, con `hi` duplicado desde 1 hasta acotar, hasta `hi − lo < 1e-13`.
  (Verificado en un script al escribir el plan: error máximo 4,8e-13 frente a `scipy` 1.18.1 en df 1–199.)

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_t_student.py tests/test_meta_analysis.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/meta_analysis.py tests/test_t_student.py
git commit -m "feat(meta): t de Student en Python puro para PI y HKSJ (independiente de scipy)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 3: `MetaAnalysisResult` v2 por desenlace y renders por desenlace

El cambio de forma rompe a todos los consumidores de `MetaAnalysisResult` a la vez, así que va en una tarea: modelo, `meta_analyze`, renders y los tests que leen la forma vieja. Consumidores verificados con `grep` (todos los usos del paquete):

| Consumidor | Uso | Tratamiento en F₁ |
|---|---|---|
| `orchestration/pipeline.py:68,896-897` | `meta_analyze(effects.effects, effects.measure)` y `model_dump()` a `08_meta/meta_analysis.json` | sin cambio: recibe y escribe la v2 |
| `orchestration/pipeline.py:1144-1150` | `render_forest_markdown`, `render_forest_png`, `render_funnel_png` | sin cambio: mismas firmas (Tarea 3) |
| `orchestration/pipeline.py:1193` | `meta_result.k` (caja `total_studies_ma` del CSV PRISMA2020) | propiedad de compatibilidad `k` |
| `orchestration/pipeline.py:1197-1200` | `render_metafor_csv(meta_result)` | misma firma, CSV con dos columnas más |
| `orchestration/pipeline.py:1489-1490` | `manifest_extra["meta_analysis"] = meta_result.model_dump()` | sin cambio |
| `exports/methods.py:49,56,61` | `meta_result.k`, `meta_result.studies` | propiedades de compatibilidad |
| `exports/forest.py:35,127,181`, `exports/interop.py:60` | leen la forma plana | se reescriben aquí |
| `protocol_files.py:34,210` | `meta_analyze` para validar que es calculable | Tarea 7 |
| `audit/artifacts.py:40,582,612` | `TypeAdapter(MetaAnalysisResult)` del JSON y de la copia del manifiesto | sin cambio: valida la v2 |
| `audit/checks_flow.py:116,490,1908` | `meta_analyze(...)` y compara su `model_dump()` campo a campo con el JSON | sin cambio: motor y auditor llaman a la misma función |
| `audit/checks_flow.py:1932-1934` | `render_forest_markdown(calculo, display=…)` y `render_metafor_csv(calculo)` frente a los ficheros | sin cambio: mismas funciones a ambos lados |
| `audit/checks_flow.py:1915` | `_P_SEGUN_ENTORNO` ignora el p tras `- Q = ` y `- Intercepto = ` | el render conserva esos prefijos (Tarea 3 y 6) |
| `audit/checks_flow.py:1236-1247,2161` | `len(efectos.effects)` y `study_id` de `EffectsFile` | sin cambio (no leen el resultado) |

**Files:**
- Modify: `revisia/meta_analysis.py:49-214` (modelos y `meta_analyze`).
- Modify: `revisia/exports/forest.py:35-208`, `revisia/exports/interop.py:60-76` (solo `render_metafor_csv`), `revisia/exports/__init__.py:16-21,44-47` (exportar los dos renders nuevos).
- Test: `tests/test_meta_desenlaces.py` (nuevo); cambian `tests/test_meta_analysis.py`, `tests/test_interop.py:43-56`, `tests/test_auditor_meta_y_estados.py:90,540-544`.

**Interfaces:**
- Consumes: `EffectInput`, `Measure`, `PredictionInterval`, `DuplicateEffect`, `RandomMethod` (PR-0, `revisia/schemas/effects.py`); `ARTIFACT_SCHEMA_VERSION`.
- Produces (en `revisia/meta_analysis.py`; nombres finales, las Tareas 4–6 rellenan los campos que aquí quedan con su default):
  - `EGGER_MIN_K: Final[int] = 10`, `PI_MIN_K: Final[int] = 3`, `DUPLICATE_TOL: Final[float] = 1e-9`.
  - `StudyEffect` (`:49`) gana `subgroup: str | None = None`.
  - `PooledEstimate` (`:63`) gana `test: Literal["z", "t"] = "z"` y `df: int | None = None` (con `t`, el estadístico sigue en `z`).
  - `Heterogeneity`, `EggerTest`: sin cambio.
  - `class SubgroupResult(BaseModel)`: `subgroup: str`, `k: int`, `random: PooledEstimate | None = None`, `heterogeneity: Heterogeneity | None = None`.
  - `class SubgroupTest(BaseModel)`: `q: float`, `df: int`, `p_value: float | None = None`, `p_method: str = ""`.
  - `class NotPooledOutcome(BaseModel)`: `outcome: str | None`, `k: int`, `study_ids: list[str]`.
  - `class OutcomeMeta(BaseModel)`: `outcome: str | None`, `k: int`, `measure: Measure`, `log_scale: bool`, `studies: list[StudyEffect]`, `fixed: PooledEstimate`, `random: PooledEstimate`, `heterogeneity: Heterogeneity`, `prediction_interval: PredictionInterval | None = None`, `egger: EggerTest | None = None`, `egger_note: str | None = None`, `subgroups: list[SubgroupResult] = []`, `q_between: SubgroupTest | None = None`, `duplicates: list[DuplicateEffect] = []`.
  - `class MetaAnalysisResult(BaseModel)` (sustituye a la plana, `:96`): `schema_version: int = ARTIFACT_SCHEMA_VERSION`, `random_method: RandomMethod = "DL"`, `outcomes: list[OutcomeMeta] = []`, `not_pooled: list[NotPooledOutcome] = []`, `excluded: int = Field(default=0, ge=0)`. Propiedades **no serializadas** (`@property`, no `computed_field`): `k -> int` = Σ `outcomes[].k`; `studies -> list[StudyEffect]` = concatenación de `outcomes[].studies` en orden. Docstring: «compatibilidad con `pipeline.py:1193` y `methods.py:49-61` hasta F₂».
  - `meta_analyze(effects: Sequence[EffectInput], measure: Measure) -> MetaAnalysisResult` (la Tarea 5 añade `*, random_method`). Agrupa por `outcome` en orden de primera aparición (`None` es un desenlace más: el «desenlace único» de §19 fila 3). Un desenlace con k < 2 va a `not_pooled` (no lanza); `[]` da `outcomes == []`. Lanza `ValueError` solo por datos (faltan datos de la medida, varianza ≤ 0), como hoy. Egger (`_egger`, `:125`, sin cambio de cuerpo) solo con `k ≥ EGGER_MIN_K`; si no, `egger_note = f"Egger no calculado: k = {k} < {EGGER_MIN_K} (Sterne et al. 2011)"`; con k ≥ 10 y `_egger` → `None` (precisión constante), `egger_note = "Egger no calculado: la precisión es la misma en todos los estudios (regresión indefinida)"`.
  - En `revisia/exports/forest.py`: `render_forest_markdown(result: MetaAnalysisResult, *, display: str = "raw") -> str` (misma firma), `render_outcome_forest_png(outcome: OutcomeMeta, out_path: Path, *, display: str = "raw") -> bool`, `render_outcome_funnel_png(outcome: OutcomeMeta, out_path: Path) -> bool` (`False` sin escribir si `outcome.k < EGGER_MIN_K` o sin matplotlib), y las de compatibilidad con la misma firma de hoy: `render_forest_png(result, out_path, *, display="raw") -> bool` y `render_funnel_png(result, out_path) -> bool`, que delegan en el **primer** desenlace agregado (`False` si `result.outcomes == []`).
  - En `revisia/exports/interop.py`: `render_metafor_csv(result: MetaAnalysisResult) -> str` con cabecera `study_id,label,measure,yi,vi,outcome,subgroup` (columnas nuevas al final; `None` → celda vacía), una fila por estudio de cada desenlace, en orden. Docstring: ``metafor::rma(yi, vi, data=dat, subset = outcome == "<desenlace>")``.

**Formato de `meta_analisis.md`** (el auditor lo compara con lo que renderiza; `checks_flow.py:1915` y los tests de `test_auditor_meta_y_estados.py:166-195` anclan estas líneas, así que se conservan tal cual dentro de cada desenlace):

```
# Meta-análisis cuantitativo

- Modelo de efectos aleatorios: **DerSimonian-Laird**
- Desenlaces agregados: **<n>**
[- Desenlaces sin agregar (k < 2): `<desenlace o «único»>` (k = 1: <ids>); …]

## Desenlace: <outcome>            ← «## Desenlace único» si outcome is None
- Medida: **…**  (como hoy, línea 58-59)
- Estudios (k): **<k>**
### Forest plot                    ← tabla como hoy (líneas 64-78)
### Heterogeneidad                 ← «- Q = …» e «- I² = … · τ² = …» como hoy (84-85)
### Efecto combinado               ← «- Fijos: …» y «- Aleatorios: …» como hoy (89-103)
### Sesgo de publicación           ← «- Intercepto = …» como hoy, o «- <egger_note>»

_Síntesis cuantitativa orientativa: …_   (pie como hoy, una sola vez)
```

- [ ] **Step 1: Tests que fallan** — crear `tests/test_meta_desenlaces.py` (las Tareas 4–6 añaden aquí):

```python
"""Meta-análisis v2 por desenlace (spec 2026-10-18 §4.2, §10.1, D16; §19 fila 3)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from revisia.exports.forest import (
    render_forest_markdown,
    render_funnel_png,
    render_outcome_forest_png,
    render_outcome_funnel_png,
)
from revisia.exports.interop import render_metafor_csv
from revisia.meta_analysis import EGGER_MIN_K, MetaAnalysisResult, meta_analyze
from revisia.schemas.effects import EffectInput


def _e(sid: str, yi: float, vi: float, outcome: str | None = None, subgroup: str | None = None):
    return EffectInput(study_id=sid, yi=yi, vi=vi, outcome=outcome, subgroup=subgroup)


def _dos_desenlaces() -> list[EffectInput]:
    return [
        _e("a", 0.2, 0.04, "mort"),
        _e("x", 1.0, 0.1, "hosp"),
        _e("b", 0.4, 0.04, "mort"),
        _e("y", 1.2, 0.1, "hosp"),
    ]


def test_sin_desenlace_es_un_desenlace_unico() -> None:
    res = meta_analyze([_e("a", 0.2, 0.04), _e("b", 0.4, 0.04)], "precomputed")
    assert (res.schema_version, res.random_method, res.excluded, res.not_pooled) == (2, "DL", 0, [])
    (o,) = res.outcomes
    assert (o.outcome, o.k, o.measure, o.log_scale) == (None, 2, "precomputed", False)
    assert o.fixed.estimate == pytest.approx(0.3, abs=1e-9)
    # Compatibilidad hasta F₂ (pipeline.py:1193, methods.py:49-61): propiedades, no campos.
    assert res.k == 2 and [s.study_id for s in res.studies] == ["a", "b"]
    assert "k" not in res.model_dump() and "studies" not in res.model_dump()


def test_agrupa_por_desenlace_en_orden_de_aparicion() -> None:
    res = meta_analyze(_dos_desenlaces(), "precomputed")
    assert [(o.outcome, o.k, [s.study_id for s in o.studies]) for o in res.outcomes] == [
        ("mort", 2, ["a", "b"]),
        ("hosp", 2, ["x", "y"]),
    ]
    assert res.k == 4


def test_desenlace_con_un_estudio_no_se_agrega_y_se_declara() -> None:
    res = meta_analyze(_dos_desenlaces()[:3], "precomputed")
    assert [o.outcome for o in res.outcomes] == ["mort"]
    assert [(n.outcome, n.k, n.study_ids) for n in res.not_pooled] == [("hosp", 1, ["x"])]
    solo = meta_analyze([_e("a", 0.2, 0.04)], "precomputed")
    assert (solo.outcomes, solo.k, solo.not_pooled[0].study_ids) == ([], 0, ["a"])
    assert meta_analyze([], "precomputed").outcomes == []


def test_v2_valida_desde_json_y_admite_el_resultado_vacio_de_f2() -> None:
    res = meta_analyze(_dos_desenlaces(), "precomputed")
    assert MetaAnalysisResult.model_validate_json(res.model_dump_json()) == res
    vacio = MetaAnalysisResult(outcomes=[], excluded=3)  # §10.1: k < 2 tras filtrar
    assert (vacio.model_dump()["outcomes"], vacio.excluded, vacio.k) == ([], 3, 0)


def test_egger_solo_desde_k_10() -> None:
    assert EGGER_MIN_K == 10
    nueve = meta_analyze([_e(f"s{i}", 0.1 * i, 0.01 * i) for i in range(1, 10)], "precomputed")
    o9 = nueve.outcomes[0]
    assert o9.egger is None and o9.egger_note == "Egger no calculado: k = 9 < 10 (Sterne et al. 2011)"
    diez = meta_analyze([_e(f"s{i}", 0.1 * i, 0.01 * i) for i in range(1, 11)], "precomputed")
    assert diez.outcomes[0].egger is not None and diez.outcomes[0].egger_note is None
    iguales = meta_analyze([_e(f"s{i}", 0.1 * i, 0.04) for i in range(1, 11)], "precomputed")
    assert iguales.outcomes[0].egger is None
    assert "regresión indefinida" in iguales.outcomes[0].egger_note


def test_forest_markdown_por_desenlace_conserva_las_lineas_que_ancla_el_auditor() -> None:
    md = render_forest_markdown(meta_analyze(_dos_desenlaces(), "precomputed"))
    assert md.startswith("# Meta-análisis cuantitativo\n")
    assert "- Modelo de efectos aleatorios: **DerSimonian-Laird**" in md
    assert md.index("## Desenlace: mort") < md.index("## Desenlace: hosp")
    assert md.count("- Estudios (k): **2**") == 2
    assert md.count("| **Combinado (fijos)** | ") == 2 and md.count("- Aleatorios: ") == 2
    assert len(re.findall(r"^- Q = .*\bp=", md, re.MULTILINE)) == 2
    assert md.count("- Egger no calculado: k = 2 < 10 (Sterne et al. 2011)") == 2
    assert md.count("_Síntesis cuantitativa orientativa") == 1


def test_forest_markdown_desenlace_unico_y_no_agregados() -> None:
    res = meta_analyze([_e("a", 0.0, 0.1), _e("b", 2.197, 0.1)], "precomputed")
    md = render_forest_markdown(res, display="proportion")
    assert "## Desenlace único" in md and "0.500" in md and "0.900" in md
    parcial = render_forest_markdown(meta_analyze(_dos_desenlaces()[:3], "precomputed"))
    assert "- Desenlaces sin agregar (k < 2): `hosp` (k = 1: x)" in parcial


def test_metafor_csv_por_desenlace() -> None:
    texto = render_metafor_csv(meta_analyze(_dos_desenlaces(), "precomputed"))
    lineas = texto.strip().splitlines()
    assert lineas[0] == "study_id,label,measure,yi,vi,outcome,subgroup"
    assert lineas[1:] == [
        "a,,precomputed,0.2,0.04,mort,",
        "b,,precomputed,0.4,0.04,mort,",
        "x,,precomputed,1,0.1,hosp,",
        "y,,precomputed,1.2,0.1,hosp,",
    ]


def test_funnel_solo_con_k_10_y_forest_por_desenlace(tmp_path: Path) -> None:
    cuatro = meta_analyze([_e(f"s{i}", 0.1 * i, 0.01 * i) for i in range(1, 5)], "precomputed")
    assert render_funnel_png(cuatro, tmp_path / "funnel.png") is False
    assert render_outcome_funnel_png(cuatro.outcomes[0], tmp_path / "f.png") is False
    assert not (tmp_path / "funnel.png").exists() and not (tmp_path / "f.png").exists()
    pytest.importorskip("matplotlib")
    diez = meta_analyze([_e(f"s{i}", 0.1 * i, 0.01 * i) for i in range(1, 11)], "precomputed")
    assert render_outcome_funnel_png(diez.outcomes[0], tmp_path / "g.png") is True
    assert render_outcome_forest_png(cuatro.outcomes[0], tmp_path / "forest.png") is True
    assert (tmp_path / "g.png").stat().st_size > 0 and (tmp_path / "forest.png").exists()
```

- [ ] **Step 2: Cambiar los tests que leen la forma plana** (cambios exactos; ninguno se borra):
  - `tests/test_meta_analysis.py`: en `test_forest_markdown_display_proportion`, `test_fixed_effect_pooled_estimate` y `test_weights_suman_100`, leer `o = res.outcomes[0]` y usar `o.fixed`, `o.heterogeneity`, `o.random`, `o.studies` (`res.k == 2` sigue valiendo por la propiedad). `test_egger_requiere_tres_estudios` pasa a `test_egger_no_se_calcula_con_dos_ni_con_tres_estudios` y afirma `egger is None` en ambos con `egger_note` que contiene `"< 10"`. `test_menos_de_dos_estudios_falla` pasa a `test_menos_de_dos_estudios_no_agrega_y_lo_declara`: `res.outcomes == []` y `res.not_pooled[0].study_ids == ["a"]`. `test_varianza_no_positiva_falla` no cambia.
  - `tests/test_interop.py:53`: la cabecera esperada pasa a `"study_id,label,measure,yi,vi,outcome,subgroup"`; el resto no cambia.
  - `tests/test_auditor_meta_y_estados.py:90`: `meta["random"]["estimate"] *= 3` → `meta["outcomes"][0]["random"]["estimate"] *= 3` (la aserción de la línea 98, `"random.estimate" in detalle`, sigue valiendo: el detalle es `.outcomes[0].random.estimate`). Líneas 540-544: `meta["k"]` → `sum(o["k"] for o in meta["outcomes"])`.

- [ ] **Step 3: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_desenlaces.py tests/test_meta_analysis.py tests/test_interop.py -v`
Expected: FAIL (`ImportError: cannot import name 'EGGER_MIN_K'`).

- [ ] **Step 4: Implementar** según Interfaces. `meta_analyze` extrae el cálculo de hoy (`:172-213`) a una función privada por desenlace, `_pool_outcome(outcome, effects, measure) -> OutcomeMeta`; `_pool` y `_egger` no cambian. Los renders PNG por desenlace son el cuerpo de hoy (`forest.py:136-178,187-208`) sobre `OutcomeMeta`; el título del PNG lleva el desenlace si lo hay.

- [ ] **Step 5: Run para verificar que pasa, con la suite entera**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_desenlaces.py tests/test_meta_analysis.py tests/test_interop.py tests/test_auditor_meta_y_estados.py tests/test_entregable_honesto.py tests/test_audit_flujo.py -v`
Expected: PASS (el auditor recalcula la v2 y renderiza con las mismas funciones; `metodologia.md` sigue diciendo `(k = 4)` por la propiedad).

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add revisia/meta_analysis.py revisia/exports/forest.py revisia/exports/interop.py revisia/exports/__init__.py tests/test_meta_desenlaces.py tests/test_meta_analysis.py tests/test_interop.py tests/test_auditor_meta_y_estados.py
git commit -m "feat(meta): MetaAnalysisResult v2 por desenlace, Egger solo con k >= 10 y renders por desenlace (D16)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 4: Intervalo de predicción y duplicados

**Files:**
- Modify: `revisia/meta_analysis.py` (`_pool_outcome`), `revisia/exports/forest.py` (`render_forest_markdown`).
- Test: `tests/test_meta_desenlaces.py` (añadir).

**Interfaces:**
- Consumes: `student_t_quantile` (Tarea 2), `OutcomeMeta` (Tarea 3), `PredictionInterval`, `DuplicateEffect` (PR-0).
- Produces: `OutcomeMeta.prediction_interval` relleno con `k ≥ PI_MIN_K` (`None` si no); `OutcomeMeta.duplicates` relleno.
  - **PI** (Higgins, Thompson y Spiegelhalter 2009, *JRSS A* 172:137-159): `μ̂ ± t_{k−2; 0,975} · √(τ̂² + SE(μ̂)²)`, con `μ̂` y `SE(μ̂)` los de `random` (los de HKSJ cuando la Tarea 5 lo active) y `df = k − 2`.
  - **Duplicados**: dos efectos del mismo desenlace lo son si `|Δyi| ≤ DUPLICATE_TOL` y `|Δvi| ≤ DUPLICATE_TOL`; los grupos son las clases de esa relación cerrada transitivamente, en orden de primera aparición; `study_ids` en orden de entrada, `yi`/`vi` del primero. Se detectan y se informan; **no** se excluyen (los declara el auditor como WARN, §11.2).
  - Render, dentro de «### Efecto combinado» y tras «- Aleatorios: …»: `- Intervalo de predicción 95 % (t con {df} gl): [{low:+.3f}, {high:+.3f}]` (con `display="proportion"`, `[{expit(low):.3f}, {expit(high):.3f}]`), o `- Intervalo de predicción no calculado (requiere k ≥ 3).`. Con duplicados, una sección `### Efectos duplicados` con una línea por grupo: `- {", ".join(study_ids)}: yi = {yi:+.4f}, vi = {vi:.4f} (¿el mismo efecto contado dos veces?)`.

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_meta_desenlaces.py`:

```python
import math

# dat.bcg (metafor; Colditz et al. 1994): (tpos, tneg, cpos, cneg) de los 13 ensayos de BCG.
BCG = (
    (4, 119, 11, 128),
    (6, 300, 29, 274),
    (3, 228, 11, 209),
    (62, 13536, 248, 12619),
    (33, 5036, 47, 5761),
    (180, 1361, 372, 1079),
    (8, 2537, 10, 619),
    (505, 87886, 499, 87892),
    (29, 7470, 45, 7232),
    (17, 1699, 65, 1600),
    (186, 50448, 141, 27197),
    (5, 2493, 3, 2338),
    (27, 16886, 29, 17825),
)


def _bcg(outcome: str | None = "tuberculosis") -> list[EffectInput]:
    """logRR y su varianza (`escalc(measure="RR")`), como efectos precomputados."""
    efectos = []
    for i, (tpos, tneg, cpos, cneg) in enumerate(BCG, start=1):
        n1, n0 = tpos + tneg, cpos + cneg
        yi = math.log((tpos / n1) / (cpos / n0))
        vi = 1 / tpos - 1 / n1 + 1 / cpos - 1 / n0
        efectos.append(EffectInput(study_id=f"bcg-{i}", yi=yi, vi=vi, outcome=outcome))
    return efectos


def test_dl_reproduce_metafor_en_dat_bcg() -> None:
    # metafor::rma(yi, vi, data=dat.bcg-escalc, method="DL"): μ̂ = -0.7141, τ² = 0.3088.
    o = meta_analyze(_bcg(), "precomputed").outcomes[0]
    assert o.k == 13
    assert o.random.estimate == pytest.approx(-0.7141, abs=5e-5)
    assert o.random.se == pytest.approx(0.1787, abs=5e-5)
    assert o.heterogeneity.tau2 == pytest.approx(0.3088, abs=5e-5)
    assert o.heterogeneity.q == pytest.approx(152.2330, abs=5e-5)
    assert o.heterogeneity.i2 == pytest.approx(92.1173, abs=5e-5)


def test_intervalo_de_prediccion_higgins_en_dat_bcg() -> None:
    # μ̂ ± t(0.975; 11)·√(τ² + SE²) = -0.7141 ± 2.200985·√(0.30876 + 0.17874²).
    pi = meta_analyze(_bcg(), "precomputed").outcomes[0].prediction_interval
    assert pi is not None and pi.df == 11
    assert (round(pi.low, 4), round(pi.high, 4)) == (-1.9988, 0.5706)


def test_intervalo_de_prediccion_solo_desde_k_3() -> None:
    dos = meta_analyze([_e("a", 0.2, 0.04), _e("b", 0.4, 0.04)], "precomputed").outcomes[0]
    assert dos.prediction_interval is None
    tres = meta_analyze([_e("a", 0.2, 0.04), _e("b", 0.4, 0.02), _e("c", 0.6, 0.01)], "precomputed")
    assert tres.outcomes[0].prediction_interval.df == 1
    md = render_forest_markdown(meta_analyze(_bcg(), "precomputed"))
    assert "- Intervalo de predicción 95 % (t con 11 gl): [-1.999, +0.571]" in md
    assert "- Intervalo de predicción no calculado (requiere k ≥ 3)." in render_forest_markdown(
        meta_analyze([_e("a", 0.2, 0.04), _e("b", 0.4, 0.04)], "precomputed")
    )


def test_duplicados_se_detectan_por_desenlace_y_no_se_excluyen() -> None:
    efectos = [
        _e("a", 0.5, 0.04, "o"),
        _e("b", 0.5 + 5e-10, 0.04, "o"),
        _e("c", 0.9, 0.05, "o"),
        _e("d", 0.5, 0.04, "otro"),
        _e("e", 0.1, 0.02, "otro"),
    ]
    res = meta_analyze(efectos, "precomputed")
    o, otro = res.outcomes
    assert [(d.study_ids, d.yi, d.vi) for d in o.duplicates] == [(["a", "b"], 0.5, 0.04)]
    assert o.k == 3 and otro.duplicates == []
    assert "- a, b: yi = +0.5000, vi = 0.0400" in render_forest_markdown(res)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_desenlaces.py -v -k "bcg or prediccion or duplicados"`
Expected: FAIL en `prediction_interval is None` y `duplicates == []` (el DL de `dat.bcg` ya pasa: es el cálculo de hoy).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_desenlaces.py tests/test_meta_analysis.py tests/test_auditor_meta_y_estados.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/meta_analysis.py revisia/exports/forest.py tests/test_meta_desenlaces.py
git commit -m "feat(meta): intervalo de predicción (Higgins 2009, t con k-2 gl) y detección de duplicados" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 5: HKSJ opcional sobre DerSimonian-Laird

**Files:**
- Modify: `revisia/meta_analysis.py` (`meta_analyze`, `_pool_outcome`), `revisia/exports/forest.py`.
- Test: `tests/test_meta_desenlaces.py` (añadir).

**Interfaces:**
- Consumes: `student_t_sf`, `student_t_quantile` (Tarea 2), `RandomMethod` (PR-0).
- Produces: `meta_analyze(effects: Sequence[EffectInput], measure: Measure, *, random_method: RandomMethod = "DL") -> MetaAnalysisResult` (firma final, §10.1). `MetaAnalysisResult.random_method` = el pedido. Con `"HKSJ"`, `OutcomeMeta.random` es (Hartung y Knapp 2001; Sidik y Jonkman 2002; IntHout, Ioannidis y Borm 2014, *BMC Med Res Methodol* 14:25), con `τ̂²` el de DL y `w*ᵢ = 1/(vᵢ + τ̂²)`:
  - `q = Σ w*ᵢ (yᵢ − μ̂)² / (k − 1)`, `SE_HK = √(q / Σ w*ᵢ)` (sin truncar `q` a 1);
  - `ci = μ̂ ± t_{k−1; 0,975} · SE_HK`; `z = μ̂ / SE_HK`; `p_value = 2 · student_t_sf(|z|, k − 1)`; `p_method = "t (HKSJ)"`; `test = "t"`; `df = k − 1`;
  - con `SE_HK == 0` (efectos idénticos): `z = 0.0`, `p_value = 1.0`, IC `[μ̂, μ̂]`, sin división por cero;
  - `fixed` y `heterogeneity` no cambian; el PI (Tarea 4) usa `SE_HK`.
  - Render: la cabecera dice `- Modelo de efectos aleatorios: **DerSimonian-Laird con ajuste HKSJ** (IC y prueba con t de k − 1 gl)`, y la línea de aleatorios escribe `t=` y `gl=` en vez de `z=`.

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_meta_desenlaces.py`:

```python
import sys


def test_hksj_sobre_dl_contra_el_calculo_manual_en_dat_bcg() -> None:
    # q = Σw*(y-μ̂)²/(k-1) = 1.021990; SE_HK = √(q/Σw*) = 0.180697; t(0.975; 12) = 2.178813.
    res = meta_analyze(_bcg(), "precomputed", random_method="HKSJ")
    assert res.random_method == "HKSJ"
    o = res.outcomes[0]
    assert o.heterogeneity.tau2 == pytest.approx(0.3088, abs=5e-5)  # τ² sigue siendo el de DL
    r = o.random
    assert (r.test, r.df) == ("t", 12)
    assert r.estimate == pytest.approx(-0.7141, abs=5e-5)
    assert r.se == pytest.approx(0.180697, abs=5e-7)
    assert (round(r.ci_low, 4), round(r.ci_high, 4)) == (-1.1078, -0.3204)
    assert r.z == pytest.approx(-3.9520, abs=5e-5)
    assert r.p_value == pytest.approx(0.001921, abs=5e-7)
    assert (round(o.prediction_interval.low, 4), round(o.prediction_interval.high, 4)) == (
        -2.0002,
        0.5719,
    )
    assert (o.fixed.test, o.fixed.df) == ("z", None)


def test_dl_por_defecto_conserva_la_normal() -> None:
    r = meta_analyze(_bcg(), "precomputed").outcomes[0].random
    assert (r.test, r.df) == ("z", None)
    assert r.ci_low == pytest.approx(r.estimate - 1.96 * r.se, abs=1e-12)


def test_hksj_con_efectos_identicos_no_divide_por_cero() -> None:
    o = meta_analyze(
        [_e("a", 0.3, 0.04), _e("b", 0.3, 0.02), _e("c", 0.3, 0.01)],
        "precomputed",
        random_method="HKSJ",
    ).outcomes[0]
    assert (o.random.se, o.random.z, o.random.p_value) == (0.0, 0.0, 1.0)
    assert o.random.ci_low == o.random.ci_high == pytest.approx(0.3)


def test_sin_scipy_los_numeros_que_compara_el_auditor_no_cambian(monkeypatch) -> None:
    # `_meta_distinto` (audit/checks_flow.py:1843) ignora solo `p_value`/`p_method`.
    def _sin_p(valor):
        if isinstance(valor, dict):
            return {k: _sin_p(v) for k, v in valor.items() if k not in {"p_value", "p_method"}}
        return [_sin_p(v) for v in valor] if isinstance(valor, list) else valor

    efectos = _bcg() + [_e(f"x{i}", 0.1 * i, 0.01 * i, "otro", "g1" if i < 6 else "g2") for i in range(1, 12)]
    con = meta_analyze(efectos, "precomputed", random_method="HKSJ").model_dump()
    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "scipy.stats", None)
    sin = meta_analyze(efectos, "precomputed", random_method="HKSJ").model_dump()
    assert _sin_p(sin) == _sin_p(con)


def test_render_hksj() -> None:
    md = render_forest_markdown(meta_analyze(_bcg(), "precomputed", random_method="HKSJ"))
    assert "**DerSimonian-Laird con ajuste HKSJ**" in md and "gl=12" in md
```

(El caso `"otro"` usa `subgroup`, que la Tarea 6 aún no agrega: aquí solo viaja en `StudyEffect.subgroup`; el test vuelve a cubrirlo con subgrupos al cerrar la Tarea 6.)

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_desenlaces.py -v -k "hksj or normal or scipy"`
Expected: FAIL (`TypeError: meta_analyze() got an unexpected keyword argument 'random_method'`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_desenlaces.py tests/test_meta_analysis.py tests/test_t_student.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/meta_analysis.py revisia/exports/forest.py tests/test_meta_desenlaces.py
git commit -m "feat(meta): random_method HKSJ opcional sobre DL (IntHout 2014), sin división por cero" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 6: Subgrupos con Q entre grupos

**Files:**
- Modify: `revisia/meta_analysis.py` (`_pool_outcome`), `revisia/exports/forest.py`.
- Test: `tests/test_meta_desenlaces.py` (añadir).

**Interfaces:**
- Consumes: `SubgroupResult`, `SubgroupTest` (Tarea 3), `_chi2_sf` (`meta_analysis.py:29`, sin cambio).
- Produces: `OutcomeMeta.subgroups` y `OutcomeMeta.q_between`.
  - Dentro de un desenlace, o ningún efecto tiene `subgroup` (→ `subgroups == []`, `q_between is None`) o lo tienen todos; mezclar es `ValueError("desenlace `<o>`: `subgroup` en unos efectos y en otros no; decláralo en todos o en ninguno")`.
  - Un `SubgroupResult` por valor, en orden de primera aparición. Con `k_j ≥ 2`, `random` y `heterogeneity` salen del mismo modelo del desenlace (DL o HKSJ) **con su propio τ²** (Cochrane Handbook §10.11.3.1; Borenstein et al. 2009, cap. 19); con `k_j == 1`, `random = heterogeneity = None`.
  - `q_between` con al menos dos subgrupos con `random`: `θ̄ = Σ wⱼθⱼ / Σ wⱼ`, `wⱼ = 1/SEⱼ²`, `q = Σ wⱼ(θⱼ − θ̄)²`, `df = G' − 1` (G' = subgrupos con `random`), `p_value, p_method = _chi2_sf(q, df)`. Si no, `None`.
  - Render: sección `### Subgrupos` con la tabla `| Subgrupo | k | Aleatorios | IC95% |` (`—` sin `random`) y la línea `- Q = {q:.3f} entre subgrupos (df={df}, p={p} · {p_method})`, que empieza por `- Q = ` para que `_P_SEGUN_ENTORNO` (`audit/checks_flow.py:1915`) ignore su p-valor, que depende de `scipy`.

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_meta_desenlaces.py`:

```python
def _con_subgrupos() -> list[EffectInput]:
    return [
        _e("a1", -0.1, 1.0, "o", "A"),
        _e("a2", 0.1, 1.0, "o", "A"),
        _e("b1", 0.9, 1.0, "o", "B"),
        _e("b2", 1.1, 1.0, "o", "B"),
        _e("c1", 5.0, 1.0, "o", "C"),
    ]


def test_subgrupos_con_q_entre_grupos() -> None:
    # A y B: τ² = 0, θ = 0 y 1, SE = √0.5 → w = 2; θ̄ = 0.5; Q = 2·0.25 + 2·0.25 = 1.0 (df 1).
    o = meta_analyze(_con_subgrupos(), "precomputed").outcomes[0]
    assert [(s.subgroup, s.k) for s in o.subgroups] == [("A", 2), ("B", 2), ("C", 1)]
    a, b, c = o.subgroups
    assert a.random.estimate == pytest.approx(0.0, abs=1e-12)
    assert b.random.estimate == pytest.approx(1.0, abs=1e-12)
    assert a.random.se == pytest.approx(math.sqrt(0.5), abs=1e-12)
    assert (c.random, c.heterogeneity) == (None, None)
    assert o.q_between.q == pytest.approx(1.0, abs=1e-12) and o.q_between.df == 1
    md = render_forest_markdown(meta_analyze(_con_subgrupos(), "precomputed"))
    assert re.search(r"^- Q = 1\.000 entre subgrupos \(df=1, p=", md, re.MULTILINE)
    pytest.importorskip("scipy")
    assert o.q_between.p_value == pytest.approx(0.317311, abs=5e-7)


def test_sin_subgrupos_no_hay_q_entre() -> None:
    o = meta_analyze(_bcg(), "precomputed").outcomes[0]
    assert (o.subgroups, o.q_between) == ([], None)
    solo_uno = meta_analyze([_e("a", 0.1, 0.1, "o", "A"), _e("b", 0.2, 0.1, "o", "A")], "precomputed")
    assert solo_uno.outcomes[0].q_between is None  # un único subgrupo con random


def test_subgrupo_en_unos_si_y_en_otros_no_falla() -> None:
    with pytest.raises(ValueError, match="`subgroup` en unos efectos y en otros no"):
        meta_analyze([_e("a", 0.1, 0.1, "o", "A"), _e("b", 0.2, 0.1, "o")], "precomputed")


def test_subgrupos_con_hksj_usan_el_mismo_metodo() -> None:
    o = meta_analyze(_con_subgrupos(), "precomputed", random_method="HKSJ").outcomes[0]
    assert {(s.subgroup, s.random.test, s.random.df) for s in o.subgroups if s.random} == {
        ("A", "t", 1),
        ("B", "t", 1),
    }
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_desenlaces.py -v -k "subgrupo"`
Expected: FAIL (`subgroups == []`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa, con la suite entera**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_desenlaces.py -v`
Expected: PASS (incluido `test_sin_scipy_los_numeros_que_compara_el_auditor_no_cambian`, ahora con subgrupos y `q_between`).

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/meta_analysis.py revisia/exports/forest.py tests/test_meta_desenlaces.py
git commit -m "feat(meta): subgrupos con τ² propio y Q entre subgrupos (Cochrane §10.11.3.1)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 7: `EffectsFile` v2 (`revisia/protocol_files.py`)

**Files:**
- Modify: `revisia/protocol_files.py:166-213` (`EffectsFile`); `revisia/meta_analysis.py` (`UnitViolation`, `unit_of_analysis_violations`).
- Modify: `examples/demo-mini-review/effects.yml` (añadir `outcome` a los cuatro efectos y actualizar el comentario de cabecera: «por desenlace; IC, intervalo de predicción, Egger solo con k ≥ 10»).
- Test: `tests/test_effects_file_v2.py` (nuevo); cambian `tests/test_errores_deterministas.py:236-251` y `tests/test_auditor_meta_y_estados.py:245-254`.

**Interfaces:**
- Consumes: `MultiplePerStudy`, `RandomMethod` (PR-0), `meta_analyze` (Tarea 5).
- Produces:
  - En `revisia/meta_analysis.py`: `class UnitViolation(NamedTuple)`: `outcome: str | None`, `study_id: str`, `n: int`; `unit_of_analysis_violations(effects: Sequence[EffectInput]) -> list[UnitViolation]` (un `study_id` repetido dentro de un desenlace, en orden de primera aparición; la usan `EffectsFile`, F₂ y G₂ para la relación 29).
  - `EffectsFile` v2: `measure: Measure = "precomputed"`, `display: str = "raw"`, `effects: list[EffectInput] = []`, `multiple_per_study: MultiplePerStudy | None = None`, `random_method: RandomMethod = "DL"`. Con `effects` no vacío, `_calculable` valida en este orden y lanza `ValueError` con estos textos (`_detalle`, `protocol_files.py:288`, quita el prefijo de pydantic; `ProtocolFilesError` da rc 2 en `validate`, `run` y `--resume`):
    1. Efectos sin `outcome`: `f"{n} de {total} efectos sin `outcome` (el primero, `{study_id}`): desde la 0.9 cada efecto declara su desenlace y el meta-análisis agrega por desenlace (D16). Migración: añade `outcome: <desenlace>` a cada efecto, con el mismo nombre en los que se agregan juntos; si un estudio aporta varios efectos al mismo desenlace, declara también `multiple_per_study: {{allowed: true, justification: \"…\"}}`"`. Constante `EFFECTS_MIGRATION_HINT` con la parte que empieza en «Migración:».
    2. `outcome` vacío o con espacios alrededor: `` f"`{study_id}`: `outcome` {outcome!r} vacío o con espacios al principio o al final" ``.
    3. k < 2 en un desenlace: `` f"el desenlace `{outcome}` tiene {k} estudio: el meta-análisis necesita al menos 2 por desenlace (k ≥ 2); añade estudios o quita ese desenlace" `` (conserva «k ≥ 2», que espera `test_errores_deterministas.py:249`).
    4. Datos de la medida, finitud y varianza: el bucle de hoy (`protocol_files.py:195-208`), sin cambio.
    5. Unidad de análisis, sin `multiple_per_study.allowed`: `` f"unidad de análisis: `{study_id}` aporta {n} efectos al desenlace `{outcome}` (Cochrane Handbook §23.3); deja uno por estudio o declara `multiple_per_study: {{allowed: true, justification: \"…\"}}`" ``.
    6. `meta_analyze(self.effects, self.measure, random_method=self.random_method)` calculable (como hoy, `:209-212`; aquí salta también la mezcla de `subgroup`).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_effects_file_v2.py`:

```python
"""`effects.yml` v2: outcome obligatorio, unidad de análisis y random_method (D16; §10.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from revisia.meta_analysis import UnitViolation, meta_analyze, unit_of_analysis_violations
from revisia.protocol_files import EffectsFile, ProtocolFilesError, load_protocol_files
from revisia.schemas.effects import EffectInput

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-mini-review"
LEGADO = (
    "measure: precomputed\neffects:\n"
    "  - {study_id: a, yi: 0.1, vi: 0.02}\n  - {study_id: b, yi: 0.2, vi: 0.03}\n"
)


def _c3(*, multiple: bool) -> str:
    """La forma del `effects.yml` de C3 en v2: 28 efectos, 27 de un mismo artículo (§2)."""
    filas = [
        f"  - {{study_id: li-2024, label: 'Li 2024 · celda {i}', outcome: sensibilidad, "
        f"yi: {1.0 + 0.05 * i:.2f}, vi: {0.05 + 0.002 * i:.3f}}}\n"
        for i in range(27)
    ]
    filas.append("  - {study_id: islar-2025, outcome: sensibilidad, yi: 2.1, vi: 0.2}\n")
    cabecera = "measure: precomputed\ndisplay: proportion\n"
    if multiple:
        cabecera += (
            "multiple_per_study:\n  allowed: true\n"
            "  justification: 27 combinaciones modelo × dataset de un mismo artículo\n"
        )
    return cabecera + "effects:\n" + "".join(filas)


def _escribir(tmp_path: Path, texto: str) -> Path:
    (tmp_path / "effects.yml").write_text(texto, encoding="utf-8")
    return tmp_path


def test_effects_sin_outcome_no_carga_y_explica_la_migracion(tmp_path: Path) -> None:
    with pytest.raises(ProtocolFilesError) as exc:
        load_protocol_files(_escribir(tmp_path, LEGADO))
    mensaje = str(exc.value)
    assert "effects.yml" in mensaje and "2 de 2 efectos sin `outcome`" in mensaje
    assert "Migración:" in mensaje and "multiple_per_study" in mensaje


def test_effects_de_c3_no_carga_sin_multiple_per_study(tmp_path: Path) -> None:
    with pytest.raises(ProtocolFilesError, match=r"unidad de análisis: `li-2024` aporta 27 efectos"):
        load_protocol_files(_escribir(tmp_path, _c3(multiple=False)))


def test_effects_de_c3_con_multiple_per_study_carga_y_queda_declarado(tmp_path: Path) -> None:
    efectos = load_protocol_files(_escribir(tmp_path, _c3(multiple=True))).effects
    assert efectos is not None and efectos.multiple_per_study.allowed is True
    assert "modelo × dataset" in efectos.multiple_per_study.justification
    assert meta_analyze(efectos.effects, efectos.measure).outcomes[0].k == 28


def test_random_method_outcome_y_k_por_desenlace() -> None:
    base = {"measure": "precomputed"}
    dos = [{"study_id": s, "outcome": "o", "yi": y, "vi": 0.02} for s, y in (("a", 0.1), ("b", 0.2))]
    assert EffectsFile.model_validate({**base, "effects": dos}).random_method == "DL"
    assert EffectsFile.model_validate({**base, "effects": dos, "random_method": "HKSJ"}).random_method == "HKSJ"
    with pytest.raises(ValidationError):
        EffectsFile.model_validate({**base, "effects": dos, "random_method": "REML"})
    with pytest.raises(ValidationError, match="espacios"):
        EffectsFile.model_validate({**base, "effects": [{**dos[0], "outcome": "o "}, dos[1]]})
    con_huerfano = [*dos, {"study_id": "c", "outcome": "otro", "yi": 0.3, "vi": 0.02}]
    with pytest.raises(ValidationError, match=r"el desenlace `otro` tiene 1 estudio.*k ≥ 2"):
        EffectsFile.model_validate({**base, "effects": con_huerfano})


def test_unit_of_analysis_violations() -> None:
    efectos = [
        EffectInput(study_id="s", yi=0.1, vi=0.1, outcome="o"),
        EffectInput(study_id="s", yi=0.2, vi=0.1, outcome="o"),
        EffectInput(study_id="s", yi=0.3, vi=0.1, outcome="p"),
    ]
    assert unit_of_analysis_violations(efectos) == [UnitViolation("o", "s", 2)]


def test_el_demo_carga_con_outcome() -> None:
    efectos = load_protocol_files(DEMO).effects
    assert efectos is not None and len(efectos.effects) == 4
    assert all(e.outcome for e in efectos.effects)
```

- [ ] **Step 2: Cambiar las fixtures de efectos sin `outcome`** (cambios exactos):
  - `tests/test_errores_deterministas.py:236-245`: en `_EFECTOS_UN_ESTUDIO`, `_EFECTOS_SIN_VI` y `_EFECTOS_VARIANZA_CERO`, cada efecto gana `outcome: o` (p. ej. `{study_id: a, outcome: o, yi: 0.1, vi: 0.02}`), para que sigan probando su error y no el de migración. `CASOS_INVALIDOS` (`:247`) gana dos casos:
    - `"effects-sin-outcome": ("effects.yml", "measure: precomputed\neffects:\n  - {study_id: a, yi: 0.1, vi: 0.02}\n  - {study_id: b, yi: 0.2, vi: 0.03}\n", "sin `outcome`")`;
    - `"effects-unidad-de-analisis": ("effects.yml", "measure: precomputed\neffects:\n  - {study_id: a, outcome: o, yi: 0.1, vi: 0.02}\n  - {study_id: a, outcome: o, yi: 0.2, vi: 0.03}\n", "unidad de análisis")`.
    Ambos entran solos en `test_fichero_auxiliar_invalido_sale_2_antes_de_crear_la_corrida` (`validate` y `run`) y en `test_fichero_auxiliar_invalido_al_reanudar_sale_2_y_conserva_la_pausa` (Review Focus 1).
  - `tests/test_auditor_meta_y_estados.py:248`: `_efectos_con_estudios` escribe `{{study_id: {i}, outcome: o, yi: …, vi: 0.02}}`.

- [ ] **Step 3: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_effects_file_v2.py tests/test_errores_deterministas.py -v -k "effects or efectos or outcome or unidad or demo"`
Expected: FAIL (`ImportError: cannot import name 'UnitViolation'`; los casos nuevos de `CASOS_INVALIDOS` salen con rc 0).

- [ ] **Step 4: Implementar** según Interfaces, y añadir `outcome` al demo.

- [ ] **Step 5: Run para verificar que pasa, con la suite entera** (el demo alimenta las corridas de `conftest.py` que audita la suite)

Run: `uv run pytest -p no:cacheprovider tests/test_effects_file_v2.py tests/test_errores_deterministas.py tests/test_auditor_meta_y_estados.py tests/test_audit.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add revisia/protocol_files.py revisia/meta_analysis.py examples/demo-mini-review/effects.yml tests/test_effects_file_v2.py tests/test_errores_deterministas.py tests/test_auditor_meta_y_estados.py
git commit -m "feat(protocolo): effects.yml v2 con outcome obligatorio, unidad de análisis y random_method (D16)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 8: Agregación del benchmark (`revisia/benchmark/report.py`)

**Files:**
- Create: `revisia/benchmark/__init__.py` (solo docstring: «Benchmark de cribado: el motor trae el método, el estudio vive fuera (D6, D23)»; F₂ añade aquí `run.py`), `revisia/benchmark/report.py`.
- Test: `tests/test_benchmark_report.py` (nuevo).

**Interfaces:**
- Consumes: `BenchmarkResult`, `BenchmarkCellResult`, `BenchmarkProtocolInfo` (PR-0, `revisia/schemas/benchmark.py`); `ScreeningMetrics` (`revisia/metrics.py:30`); `meta_analyze`, `MetaAnalysisResult` (Tareas 3–6); `EffectInput`; `ARTIFACT_SCHEMA_VERSION`; `utc_now_iso`.
- Produces (en `revisia/benchmark/report.py`):
  - `AVISO_PROMEDIO: Final[str] = "Unidad de análisis: {n} corpus aportan más de una réplica. Las réplicas de un mismo corpus no son estudios independientes: se promedian (yi y vi medios por corpus) antes de agregar."` (con `.format(n=…)`).
  - `AVISO_EXPLORATORIO: Final[str] = "Exploratorio (--replicas-as-effects): cada réplica entra como un efecto. Las réplicas de un corpus no son independientes, así que el IC y el I² subestiman la incertidumbre; no lo uses como resultado principal."`
  - `class PooledSource(BaseModel)`: `path: str`, `slug: str`, `corpus_sha256: str`, `gold_sha256: str`, `n_records: int`, `n_gold_positives: int`, `replicas: int`.
  - `class PooledCell(BaseModel)`: `cell: str`, `models_used: list[str]`, `n_corpora: int`, `meta: MetaAnalysisResult`, `recall: float | None = None`, `recall_ci95: tuple[float, float] | None = None`, `recall_pi95: tuple[float, float] | None = None` (todos en escala de proporción, `expit` del efecto aleatorio, su IC y su PI).
  - `class PooledBenchmark(BaseModel)`: `schema_version: int = ARTIFACT_SCHEMA_VERSION`, `replicas_as_effects: bool`, `sources: list[PooledSource]`, `cells: list[PooledCell]`, `notes: list[str] = []`, `created_utc: str = Field(default_factory=utc_now_iso)`.
  - `load_benchmark(bench_dir: str | Path) -> BenchmarkResult`: lee `<bench_dir>/benchmark.json`; ausente, ilegible o inválido → `ValueError(f"{ruta}: {motivo}")`.
  - `recall_effect(metrics: ScreeningMetrics) -> tuple[float, float] | None`: `yi = log(tp/fn)`, `vi = 1/tp + 1/fn` (logit de la proporción y su varianza); con `tp == 0` o `fn == 0`, corrección 0,5 en ambas celdas (como `_log_or`, `schemas/effects.py:70-74`); `None` si `tp + fn == 0`.
  - `pool_benchmarks(bench_dirs: Sequence[str | Path], *, replicas_as_effects: bool = False) -> PooledBenchmark`. Reglas:
    - Corpus = `protocol.slug` de cada `benchmark.json`; un `slug` o un `corpus_sha256` repetido → `ValueError("el mismo corpus aparece dos veces (<slug>): las corridas de un mismo corpus no son estudios independientes")`.
    - Se agrupa por **nombre de celda** (`BenchmarkCellResult.cell`): una celda es el «modelo» del panel. Si una misma celda declara `models_used` distintos entre corpus, nota `"celda `<c>`: modelos distintos entre corpus (<lista>)"`.
    - Por defecto, un efecto por (celda, corpus): `study_id = slug`, `yi` y `vi` = medias de `recall_effect` de sus réplicas, `outcome = "recall"`, sin `subgroup`; si algún corpus aporta > 1 réplica, nota `AVISO_PROMEDIO`. Con `replicas_as_effects=True`, un efecto por réplica: `study_id = f"{slug}#r{replica}"`, `subgroup = slug`, y nota `AVISO_EXPLORATORIO`.
    - Una réplica con `recall_effect(...) is None` no entra, con nota `"celda `<c>`, corpus `<s>`, réplica <r>: recall indefinido (sin positivos en el gold), excluida"`; una con `n_failed_records > 0` entra con nota `"celda `<c>`, corpus `<s>`, réplica <r>: <n> registros fallidos fuera de la matriz"`.
    - `meta = meta_analyze(efectos, "precomputed")` (DL); `recall*` = `expit` de `meta.outcomes[0].random` y su PI cuando hay desenlace agregado; si no, `None`.
    - Celdas en el orden de primera aparición; fuentes en el orden de `bench_dirs`.
  - `render_pooled_report(pooled: PooledBenchmark) -> str`: `# Benchmark agregado`; tabla de fuentes (`| Corpus | Registros | Positivos del gold | Réplicas |`); tabla `| Celda | Corpus (k) | Recall agregado | IC95% | IP95% | I² |` con `{:.3f}` y `—` donde no hay; las notas como lista; y por celda con desenlace agregado, una sección `## Celda: <c>` con `render_forest_markdown(cell.meta, display="proportion")` sin su título de nivel 1.
  - `write_pooled(pooled: PooledBenchmark, out_dir: str | Path) -> tuple[Path, Path]`: crea `out_dir` y escribe `meta_analysis.json` (`model_dump_json(indent=2)`, UTF-8) y `report.md`; devuelve ambas rutas.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_benchmark_report.py`:

```python
"""`benchmark-report`: efectos logit(recall) por corpus y agregación por celda (D6; §10.2)."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pytest

from revisia.benchmark.report import (
    AVISO_EXPLORATORIO,
    PooledBenchmark,
    pool_benchmarks,
    recall_effect,
    write_pooled,
)
from revisia.metrics import ScreeningMetrics, wilson_interval
from revisia.schemas.artifacts import Environment
from revisia.schemas.benchmark import BenchmarkCellResult, BenchmarkProtocolInfo, BenchmarkResult


def _entorno() -> Environment:
    return Environment(
        engine_version="0.9.0",
        python_version="3.13.0",
        python_implementation="CPython",
        platform="x",
        created_utc="2026-10-19T00:00:00+00:00",
    )


def benchmark(
    raiz: Path,
    slug: str,
    celdas: dict[str, list[tuple[int, int]]],
    fallidos: dict[tuple[str, int], int] | None = None,
) -> Path:
    """Escribe ``<raiz>/<slug>/benchmark.json``; ``celdas``: nombre → [(tp, fn) por réplica];
    ``fallidos``: (celda, réplica) → registros fallidos."""
    cells = [
        BenchmarkCellResult(
            cell=nombre,
            replica=r,
            run_dir=f"runs/{nombre}-r{r}",
            metrics=ScreeningMetrics(
                n=tp + fn + 10, tp=tp, fp=2, fn=fn, tn=8, recall=tp / (tp + fn) if tp + fn else None
            ),
            recall_ci95=wilson_interval(tp, tp + fn),
            models_used=[f"fake:{nombre}"],
            n_calls=tp + fn + 10,
            n_failed_records=(fallidos or {}).get((nombre, r), 0),
        )
        for nombre, replicas in celdas.items()
        for r, (tp, fn) in enumerate(replicas, start=1)
    ]
    positivos = sum(celdas[next(iter(celdas))][0])
    resultado = BenchmarkResult(
        protocol=BenchmarkProtocolInfo(
            slug=slug, corpus_sha256=hashlib.sha256(slug.encode()).hexdigest(),
            gold_sha256="0" * 64, n_records=positivos + 10, n_gold_positives=positivos,
        ),
        environment=_entorno(),
        cells=cells,
    )
    carpeta = raiz / slug
    carpeta.mkdir(parents=True)
    (carpeta / "benchmark.json").write_text(resultado.model_dump_json(indent=2), encoding="utf-8")
    return carpeta


def test_recall_effect_logit_varianza_y_correccion() -> None:
    assert recall_effect(ScreeningMetrics(n=20, tp=9, fp=0, fn=1, tn=10)) == pytest.approx(
        (math.log(9), 1 / 9 + 1)
    )
    assert recall_effect(ScreeningMetrics(n=20, tp=10, fp=0, fn=0, tn=10)) == pytest.approx(
        (math.log(10.5 / 0.5), 1 / 10.5 + 1 / 0.5)
    )
    assert recall_effect(ScreeningMetrics(n=10, tp=0, fp=0, fn=0, tn=10)) is None


def test_dos_corpus_promedian_replicas_y_agregan_por_celda(tmp_path: Path) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1), (9, 1)], "b": [(8, 2), (8, 2)]})
    c2 = benchmark(tmp_path, "c2", {"a": [(18, 2), (18, 2)], "b": [(16, 4), (16, 4)]})
    pooled = pool_benchmarks([c1, c2])
    assert [c.cell for c in pooled.cells] == ["a", "b"]
    a = pooled.cells[0]
    (o,) = a.meta.outcomes
    assert (o.outcome, o.k, [s.study_id for s in o.studies], o.subgroups) == ("recall", 2, ["c1", "c2"], [])
    assert o.random.estimate == pytest.approx(math.log(9), abs=1e-12)  # τ² = 0: mismo logit
    assert a.recall == pytest.approx(0.9, abs=1e-12) and a.n_corpora == 2
    assert any(n.startswith("Unidad de análisis: 2 corpus") for n in pooled.notes)
    assert [s.replicas for s in pooled.sources] == [2, 2]


def test_replicas_como_efectos_dan_subgrupos_por_corpus_y_duplicados(tmp_path: Path) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1), (9, 1)]})
    c2 = benchmark(tmp_path, "c2", {"a": [(18, 2), (16, 4)]})
    o = pool_benchmarks([c1, c2], replicas_as_effects=True).cells[0].meta.outcomes[0]
    assert o.k == 4 and [(s.subgroup, s.k) for s in o.subgroups] == [("c1", 2), ("c2", 2)]
    assert [d.study_ids for d in o.duplicates] == [["c1#r1", "c1#r2"]]
    assert AVISO_EXPLORATORIO in pool_benchmarks([c1, c2], replicas_as_effects=True).notes


def test_un_solo_corpus_no_agrega_y_lo_declara(tmp_path: Path) -> None:
    celda = pool_benchmarks([benchmark(tmp_path, "c1", {"a": [(9, 1)]})]).cells[0]
    assert (celda.meta.outcomes, celda.recall) == ([], None)
    assert celda.meta.not_pooled[0].study_ids == ["c1"]


def test_recall_indefinido_y_registros_fallidos_quedan_anotados(tmp_path: Path) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1), (0, 0)]}, fallidos={("a", 1): 3})
    c2 = benchmark(tmp_path, "c2", {"a": [(18, 2)]})
    pooled = pool_benchmarks([c1, c2])
    assert pooled.cells[0].meta.outcomes[0].k == 2
    assert any("réplica 2: recall indefinido" in n for n in pooled.notes)
    assert any("réplica 1: 3 registros fallidos" in n for n in pooled.notes)


def test_mismo_corpus_dos_veces_o_sin_benchmark_json_falla(tmp_path: Path) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1)]})
    with pytest.raises(ValueError, match="el mismo corpus aparece dos veces"):
        pool_benchmarks([c1, c1])
    with pytest.raises(ValueError, match="benchmark.json"):
        pool_benchmarks([tmp_path / "no-existe"])


def test_write_pooled_escribe_json_valido_y_report(tmp_path: Path) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1)]})
    c2 = benchmark(tmp_path, "c2", {"a": [(18, 2)]})
    json_path, md_path = write_pooled(pool_benchmarks([c1, c2]), tmp_path / "pooled")
    assert (json_path.name, md_path.name) == ("meta_analysis.json", "report.md")
    leido = PooledBenchmark.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert leido.cells[0].recall == pytest.approx(0.9)
    md = md_path.read_text(encoding="utf-8")
    assert md.startswith("# Benchmark agregado") and "## Celda: a" in md and "0.900" in md
```

(La línea `n_gold_positives` del ayudante usa `tp + fn` de la primera réplica de la primera celda; basta para el modelo.)

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_benchmark_report.py -v`
Expected: FAIL (`ModuleNotFoundError: revisia.benchmark`).

- [ ] **Step 3: Implementar** según Interfaces (docstring del módulo: D6, D23, §10.2; por qué se promedian las réplicas; `expit` local).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_benchmark_report.py tests/test_benchmark_schemas.py -v && uv run python -c "import revisia, revisia.benchmark.report"`
Expected: PASS; el import no cicla (`revisia.schemas.benchmark` no se exporta desde `revisia.schemas`, PR-0 Tarea 13).

- [ ] **Step 5: Commit**

```bash
git add revisia/benchmark/__init__.py revisia/benchmark/report.py tests/test_benchmark_report.py
git commit -m "feat(benchmark): agregación logit(recall) por celda y corpus, con unidad de análisis (D6)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 9: `revisia benchmark-report` (`revisia/cli.py`)

**Files:**
- Modify: `revisia/cli.py` (función nueva `_cmd_benchmark_report` tras `_cmd_audit`, `:527-548`; subparser en `build_parser`, `:609-725`; rama en `main`, `:728-743`, junto a las órdenes que no cargan protocolo).
- Test: `tests/test_cli_benchmark_report.py` (nuevo).

**Interfaces:**
- Consumes: `pool_benchmarks`, `write_pooled` (Tarea 8).
- Produces: `revisia benchmark-report <benchmark_dir>… [--out DIR] [--replicas-as-effects]` (§10.2). `--out` por defecto `<primer benchmark_dir>/pooled`. rc 0 al escribir; rc 2 con `ValueError` (sin `benchmark.json`, inválido, corpus repetido) y el mensaje en `stderr`, sin traceback. Imprime una línea por celda (`f"{cell}: recall {recall:.3f} (IC95% [{lo:.3f}, {hi:.3f}]) · k = {k}"` o `f"{cell}: sin agregar (k < 2)"`), las notas con `⚠` y las dos rutas escritas. `help` del subparser: «Agrega uno o más benchmark.json (corpus distintos): logit(recall) por celda, sin Egger bajo k = 10». `--replicas-as-effects`: «Exploratorio: cada réplica como un efecto (viola la unidad de análisis; ver report.md)».

- [ ] **Step 1: Tests que fallan** — crear `tests/test_cli_benchmark_report.py`:

```python
"""CLI `revisia benchmark-report` (spec 2026-10-18 §10.2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_benchmark_report import benchmark

from revisia import cli


def test_benchmark_report_escribe_pooled_en_el_primer_benchmark(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1)]})
    c2 = benchmark(tmp_path, "c2", {"a": [(18, 2)]})
    assert cli.main(["benchmark-report", str(c1), str(c2)]) == 0
    assert (c1 / "pooled" / "meta_analysis.json").is_file() and (c1 / "pooled" / "report.md").is_file()
    salida = capsys.readouterr().out
    assert "a: recall 0.900" in salida and "k = 2" in salida


def test_benchmark_report_out_y_replicas_como_efectos(tmp_path: Path, capsys) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1), (9, 1)]})
    c2 = benchmark(tmp_path, "c2", {"a": [(18, 2), (16, 4)]})
    out = tmp_path / "agregado"
    assert cli.main(["benchmark-report", str(c1), str(c2), "--out", str(out), "--replicas-as-effects"]) == 0
    assert "Exploratorio" in (out / "report.md").read_text(encoding="utf-8")
    assert "⚠ Exploratorio" in capsys.readouterr().out


@pytest.mark.parametrize("caso", ["sin-json", "repetido"])
def test_benchmark_report_error_de_uso_sale_2(tmp_path: Path, capsys, caso: str) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1)]})
    argv = [str(tmp_path / "nada")] if caso == "sin-json" else [str(c1), str(c1)]
    assert cli.main(["benchmark-report", *argv]) == 2
    err = capsys.readouterr().err
    assert ("benchmark.json" if caso == "sin-json" else "mismo corpus") in err
    assert "Traceback" not in err
```

(`from test_benchmark_report import benchmark` funciona porque pytest pone `tests/` en `sys.path`, como `from fakes import …`.)

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_cli_benchmark_report.py -v`
Expected: FAIL (`SystemExit: 2` de argparse: `invalid choice: 'benchmark-report'`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa, con la suite y el lint**

Run: `uv run pytest -p no:cacheprovider tests/test_cli_benchmark_report.py tests/test_benchmark_report.py -v`
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado && uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: PASS y lint limpio. Anotar el recuento de tests para el cuerpo de la PR.

- [ ] **Step 5: Commit**

```bash
git add revisia/cli.py tests/test_cli_benchmark_report.py
git commit -m "feat(cli): revisia benchmark-report (pooled/meta_analysis.json y report.md)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Supuestos revocables de F₁ (filas propuestas para §19)

El integrador de PR-F las añade **a continuación de la última fila** de §19, con numeración consecutiva (`n` = la siguiente libre):

```
| n | §4.2 `MetaAnalysisResult` v2, §15 | La v2 sustituye a la plana bajo los mismos nombres (`meta_analyze`, `MetaAnalysisResult`). Hasta F₂ la compatibilidad son dos propiedades no serializadas, `k` (Σ k de los desenlaces agregados) y `studies` (concatenación), que usan `pipeline.py:1193` y `methods.py:49-61`, y `render_forest_png`/`render_funnel_png` con su firma de hoy sobre el primer desenlace. `audit/*` no se toca: recalcula con la misma `meta_analyze` y renderiza con las mismas funciones, así que sigue coherente | Plan PR-F (F₁) |
| n+1 | §4.2 `MetaAnalysisResult` v2 | Forma por desenlace: `{schema_version, random_method, outcomes: [OutcomeMeta], not_pooled: [{outcome, k, study_ids}], excluded}`; `OutcomeMeta` = `{outcome, k, measure, log_scale, studies, fixed, random, heterogeneity, prediction_interval, egger, egger_note, subgroups: [{subgroup, k, random, heterogeneity}], q_between, duplicates}`. `q_between` va en el desenlace, no en cada subgrupo (es un contraste entre grupos). Un desenlace con k < 2 va a `not_pooled` en vez de lanzar | Plan PR-F (F₁) |
| n+2 | §10.1 PI y HKSJ | La t de Student es de Python puro (beta incompleta por fracción continua y bisección; error < 1e-12 frente a scipy): con `scipy` opcional, el auditor sin scipy daría otro PI u otro IC y FAIL por entorno. El PI usa el SE del `random` reportado (el de HKSJ con HKSJ) y t con k − 2 gl | Plan PR-F (F₁) |
| n+3 | §10.1 subgrupos | `subgroup` en todos los efectos de un desenlace o en ninguno; τ² propio por subgrupo; un subgrupo con k = 1 no tiene `random` y no entra en Q entre grupos | Plan PR-F (F₁) |
| n+4 | §4.3 relación 29 | `egger is None` también con k ≥ 10 si todas las precisiones son iguales (regresión de Egger indefinida); lo dice `egger_note`. G₂ lee la relación como «`egger is None` ⇔ k < 10 o `egger_note` de precisión constante» | Plan PR-F (F₁) |
| n+5 | D16, §10.1 | Unidad de análisis = `study_id` repetido dentro de un desenlace (`unit_of_analysis_violations`). `outcome` con espacios alrededor es error de carga. Cada desenlace necesita k ≥ 2 al cargar; tras filtrar (F₂), k < 2 se declara | Plan PR-F (F₁) |
| n+6 | §10.1 `effects_metafor.csv` | Una sola tabla con columnas `outcome,subgroup` añadidas al final (`study_id,label,measure,yi,vi,outcome,subgroup`); el funnel solo se dibuja con k ≥ 10, así que el demo (k = 4) deja de producir `funnel.png` | Plan PR-F (F₁) |
| n+7 | §10.1 `random_method` | `EffectsFile.random_method` se valida en F₁, pero el pipeline solo lo pasa a `meta_analyze` en F₂ (F₁ no toca `pipeline.py`) y el auditor en G₂. Ambas fases van en la misma PR: ninguna versión publicada lo ignora | Plan PR-F (F₁) |
| n+8 | §10.2 `benchmark-report` | Se agrupa por nombre de celda del panel. Por defecto, las réplicas de un corpus se promedian (yi y vi medios) y el corpus es el estudio; `subgroup = corpus` solo con `--replicas-as-effects` (con un efecto por corpus, cada subgrupo tendría k = 1). logit(recall) con corrección 0,5 solo si `tp` o `fn` es 0. Corpus repetido (slug o hash) → rc 2. `pooled/meta_analysis.json` guarda un `PooledBenchmark`. `--out` por defecto `<primer benchmark>/pooled` | Plan PR-F (F₁) |
```

### Self-review de F₁

- **Cobertura de §10 que es de F₁:** `meta_analyze` v2 por desenlace (T3), PI con t de k − 2 gl y k ≥ 3 (T4), Egger solo k ≥ 10 con `egger_note` (T3), subgrupos con Q entre grupos (T6), duplicados a 1e-9 (T4), HKSJ opcional (T5), `EffectsFile` v2 con `outcome` obligatorio y mensaje de migración (rc 2), `multiple_per_study`, `random_method` y unidad de análisis (T7), `effects_metafor.csv` y forest/funnel por desenlace con funnel solo k ≥ 10 (T3), `benchmark-report` CLI y módulo (T8, T9). Tests de §10 que son de F₁: C3 sin `multiple_per_study` no carga y con él carga (T7); PI de `dat.bcg` a 4 decimales (T4); Egger `None` con k = 9 (T3); HKSJ sobre DL contra el cálculo manual (T5); `benchmark-report` sobre dos benchmarks sintéticos → subgrupos por corpus (T8, con `--replicas-as-effects`). Quedan para F₂: efecto de un no incluido → `excluded_effects`; k = 1 tras filtrar → sin meta-análisis declarado; el benchmark con el demo importado en dos celdas × 2 réplicas.
- **Valores numéricos:** μ̂, τ², Q, I² y SE de DL sobre `dat.bcg` coinciden con lo publicado por metafor (μ̂ ≈ −0,7141, τ² ≈ 0,3088, Q = 152,2330, I² = 92,12 %). El PI [−1,9988; 0,5706], el HKSJ (SE 0,180697; IC [−1,1078; −0,3204]; t −3,9520; p 0,001921) y su PI [−2,0002; 0,5719] se calcularon el 2026-10-19 con numpy 2.5.4 y scipy 1.18.1 aplicando las fórmulas de Higgins 2009 e IntHout 2014 (script en el scratchpad de la sesión, no versionado). **No se ejecutó R**: `metafor::predict` con su opción por defecto (`test="z"`) da un PI con cuantil normal, [−1,8582; 0,4299], no el de t con k − 2 gl; si el implementador tiene R, anota en el commit de la Tarea 4 la salida de `predict(rma(yi, vi, data=dat, method="DL"), pi.type="Riley")` y confirma que coincide; si no coincide, manda la fórmula de Higgins (§10.1) y la diferencia se registra en §19.
- **Firmas verificadas contra el árbol (= `main` @ `c1af7c3`) el 2026-10-19:** `meta_analysis.py:29-214`, `schemas/effects.py:20-93`, `protocol_files.py:166-213,288-370`, `exports/forest.py:35-208`, `exports/interop.py:60-76`, `exports/__init__.py:16-54`, `exports/methods.py:40-63`, `pipeline.py:68,885-898,1144-1150,1193,1197-1200,1489-1490`, `audit/artifacts.py:40,582,612`, `audit/checks_flow.py:116,119,151,429-491,1236-1247,1843-1877,1880-1945,2161-2190`, `cli.py:527-548,609-797`, `metrics.py:30-53,121-138`. Los nombres de PR-0 (`RandomMethod`, `MultiplePerStudy`, `ExcludedEffect`, `ExcludedEffectsFile`, `PredictionInterval`, `DuplicateEffect`, `BenchmarkResult` y compañía, `Environment`) son los de las Tareas 12 y 13 de su plan.
- **Consistencia de tipos:** `OutcomeMeta`, `SubgroupResult`, `SubgroupTest`, `NotPooledOutcome` (T3) los rellenan T4–T6 y los consume T8; `meta_analyze(..., *, random_method)` (T5) lo consume T7; `unit_of_analysis_violations` (T7) queda para F₂ y G₂; `student_t_*` (T2) los consumen T4 y T5.
- **Proporción:** los bloques de código son tests con los valores del spec; los únicos algoritmos escritos son la t de Student, el PI, HKSJ y Q entre subgrupos, en fórmulas con su referencia.

---

## Fase F₂ (sobre PR-E)

Pendiente: la escribe el redactor de F₂.

### Interfaces que F₁ deja para F₂ y G₂

En `revisia/meta_analysis.py`:

```python
EGGER_MIN_K: Final[int] = 10
PI_MIN_K: Final[int] = 3
DUPLICATE_TOL: Final[float] = 1e-9

def student_t_sf(t: float, df: int) -> float: ...
def student_t_quantile(p: float, df: int) -> float: ...

class StudyEffect(BaseModel):
    study_id: str
    label: str | None = None
    yi: float
    vi: float
    se: float
    ci_low: float
    ci_high: float
    weight_fixed: float
    weight_random: float
    subgroup: str | None = None

class PooledEstimate(BaseModel):
    model: str
    estimate: float
    se: float
    ci_low: float
    ci_high: float
    z: float                      # estadístico z, o t con test == "t" (HKSJ)
    p_value: float
    test: Literal["z", "t"] = "z"
    df: int | None = None

class Heterogeneity(BaseModel):  # sin cambio
    q: float; df: int; i2: float; tau2: float; p_value: float | None = None; p_method: str = ""

class EggerTest(BaseModel):      # sin cambio
    intercept: float; se: float; t: float; p_value: float; p_method: str

class SubgroupResult(BaseModel):
    subgroup: str
    k: int
    random: PooledEstimate | None = None
    heterogeneity: Heterogeneity | None = None

class SubgroupTest(BaseModel):
    q: float
    df: int
    p_value: float | None = None
    p_method: str = ""

class NotPooledOutcome(BaseModel):
    outcome: str | None
    k: int
    study_ids: list[str]

class OutcomeMeta(BaseModel):
    outcome: str | None
    k: int
    measure: Measure
    log_scale: bool
    studies: list[StudyEffect]
    fixed: PooledEstimate
    random: PooledEstimate
    heterogeneity: Heterogeneity
    prediction_interval: PredictionInterval | None = None   # None ⇔ k < 3
    egger: EggerTest | None = None                          # None ⇔ k < 10 o precisión constante
    egger_note: str | None = None                           # None ⇔ egger is not None
    subgroups: list[SubgroupResult] = []
    q_between: SubgroupTest | None = None
    duplicates: list[DuplicateEffect] = []

class MetaAnalysisResult(BaseModel):          # 08_meta/meta_analysis.json v2 (relación 29)
    schema_version: int = ARTIFACT_SCHEMA_VERSION
    random_method: RandomMethod = "DL"
    outcomes: list[OutcomeMeta] = []
    not_pooled: list[NotPooledOutcome] = []
    excluded: int = Field(default=0, ge=0)
    @property
    def k(self) -> int: ...                      # compatibilidad: Σ outcomes[].k
    @property
    def studies(self) -> list[StudyEffect]: ...  # compatibilidad: concatenación

class UnitViolation(NamedTuple):
    outcome: str | None
    study_id: str
    n: int

def unit_of_analysis_violations(effects: Sequence[EffectInput]) -> list[UnitViolation]: ...

def meta_analyze(
    effects: Sequence[EffectInput], measure: Measure, *, random_method: RandomMethod = "DL"
) -> MetaAnalysisResult: ...
```

Para F₂: `meta_analyze` no conoce los incluidos ni las exclusiones. `_meta_analysis(run, included_ids)` filtra, escribe `ExcludedEffectsFile` (PR-0) y fija el recuento con `result.model_copy(update={"excluded": n})`; con todo filtrado, `MetaAnalysisResult(outcomes=[], excluded=n, random_method=…)` es el resultado válido de §10.1. Debe pasar `random_method=effects.random_method` (supuesto n+7). Si F₂ retira el uso de las propiedades `k`/`studies` en `pipeline.py` y `methods.py`, las propiedades se quedan hasta que G₂ confirme que el auditor no las necesita.

Para G₂ (relación 29): «conjunto agregado» de un desenlace = `[s.study_id for s in o.studies]`; los efectos analizados = esos ∪ `not_pooled[].study_ids`; `prediction_interval is None ⇔ k < PI_MIN_K`; `egger is None ⇔ k < EGGER_MIN_K` salvo `egger_note` de precisión constante (supuesto n+4); el recálculo debe pasar el `random_method` de `00_protocol/effects.yml` (hoy `checks_flow.py:490` llama sin él). `p_value`/`p_method` de `q_between` siguen dependiendo de `scipy` y van en `_META_SEGUN_ENTORNO`.

En `revisia/protocol_files.py`:

```python
EFFECTS_MIGRATION_HINT: Final[str]

class EffectsFile(BaseModel):
    measure: Measure = "precomputed"
    display: str = "raw"
    effects: list[EffectInput] = []
    multiple_per_study: MultiplePerStudy | None = None
    random_method: RandomMethod = "DL"
```

En `revisia/exports/forest.py` e `interop.py`:

```python
def render_forest_markdown(result: MetaAnalysisResult, *, display: str = "raw") -> str: ...
def render_outcome_forest_png(outcome: OutcomeMeta, out_path: Path, *, display: str = "raw") -> bool: ...
def render_outcome_funnel_png(outcome: OutcomeMeta, out_path: Path) -> bool: ...   # False si k < 10
def render_forest_png(result: MetaAnalysisResult, out_path: Path, *, display: str = "raw") -> bool: ...  # 1.er desenlace
def render_funnel_png(result: MetaAnalysisResult, out_path: Path) -> bool: ...     # 1.er desenlace, k ≥ 10
def render_metafor_csv(result: MetaAnalysisResult) -> str: ...  # study_id,label,measure,yi,vi,outcome,subgroup
```

En `revisia/benchmark/report.py` (F₂ añade `revisia/benchmark/run.py` para `revisia benchmark`):

```python
AVISO_PROMEDIO: Final[str]
AVISO_EXPLORATORIO: Final[str]

class PooledSource(BaseModel): path: str; slug: str; corpus_sha256: str; gold_sha256: str; n_records: int; n_gold_positives: int; replicas: int
class PooledCell(BaseModel): cell: str; models_used: list[str]; n_corpora: int; meta: MetaAnalysisResult; recall: float | None = None; recall_ci95: tuple[float, float] | None = None; recall_pi95: tuple[float, float] | None = None
class PooledBenchmark(BaseModel): schema_version: int = ARTIFACT_SCHEMA_VERSION; replicas_as_effects: bool; sources: list[PooledSource]; cells: list[PooledCell]; notes: list[str] = []; created_utc: str

def load_benchmark(bench_dir: str | Path) -> BenchmarkResult: ...
def recall_effect(metrics: ScreeningMetrics) -> tuple[float, float] | None: ...
def pool_benchmarks(bench_dirs: Sequence[str | Path], *, replicas_as_effects: bool = False) -> PooledBenchmark: ...
def render_pooled_report(pooled: PooledBenchmark) -> str: ...
def write_pooled(pooled: PooledBenchmark, out_dir: str | Path) -> tuple[Path, Path]: ...
```

CLI: `revisia benchmark-report <benchmark_dir>… [--out DIR] [--replicas-as-effects]` (rc 0/2). F₂ añade `revisia benchmark` en una función y un subparser propios de `cli.py`; G añade `deposit` en los suyos (§15).
