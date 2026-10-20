# Ola 2 · PR-F `feat/ola2-meta-benchmark` (meta-análisis por desenlace y benchmark) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el meta-análisis se haga por desenlace, ligado a los estudios incluidos y a su unidad de análisis (intervalo de predicción, Egger solo con k ≥ 10, subgrupos, duplicados y HKSJ opcional), y que el motor traiga `revisia benchmark` y `revisia benchmark-report` para validar modelos de cribado sobre un corpus congelado contra un gold, sin volver a citar 0,820 ni I² 90,7 % como evidencia (C3-benchmark, D6, D16, D23).

**Architecture:** F se hace en dos fases (§15). **F₁** (este documento, desde PR-0, en paralelo con A, B, C, D y E₁) cambia solo módulos que §15 asigna a F y que no dependen del pipeline: `meta_analysis.py` pasa a la forma v2 por desenlace **bajo los mismos nombres** (`meta_analyze`, `MetaAnalysisResult`), con dos propiedades de compatibilidad (`k`, `studies`) que mantienen intactos `pipeline.py` y `exports/methods.py` hasta F₂; el auditor no se toca y sigue coherente porque recalcula con la misma `meta_analyze` y renderiza con las mismas funciones; `protocol_files.EffectsFile` v2 exige `outcome`; los renders (Markdown, CSV de metafor, PNG) pasan a ser por desenlace; y `revisia benchmark-report` lee `benchmark.json`, construye efectos `logit(recall)` y escribe `pooled/`. **F₂** (otro redactor, sobre PR-E) liga el meta-análisis a los incluidos en el pipeline (`_meta_analysis(run, included_ids)`, `excluded_effects.json`, declaraciones), añade `stop_after`, `kind: benchmark` y el comando `revisia benchmark` completo con su preflight.

**Tech Stack:** Python 3.13 (suite también en 3.11/3.12 cuando PR-H esté debajo), Pydantic v2, PyYAML, pytest, ruff + black (línea 100), uv. Estadística en Python puro (sin numpy): `scipy` sigue siendo opcional y solo da los p-valores exactos de Q y de Egger, como hoy. `matplotlib` (extra `meta`) solo para los PNG.

**Spec:** `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`. Este plan implementa §10 (PR-F), D6, D16 y D23 en lo que no depende del pipeline, con los contratos de §4.2 («EffectInput v2 / EffectsFile v2 / MetaAnalysisResult v2 / ExcludedEffect», «BenchmarkPanel / BenchmarkResult»), la relación 29 (§4.3) como contrato para G₂, §15 (topología), §16 (método) y **§19 filas 1–10**, que vinculan (sobre todo la fila 3: `outcome` opcional en el modelo y obligatorio en `EffectsFile`; un efecto sin desenlace se agrupa como desenlace único; la forma por desenlace la define este plan). Plan hermano: `2026-10-18-ola2-pr0-contratos.md`, cuyas Tareas 12 y 13 dan los nombres que aquí se consumen tal cual.

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

F₁ se ejecuta en secuencia en el worktree `C:\revisia-wt\f` (rama `feat/ola2-meta-benchmark`, creada desde `feat/ola2-contratos` en la Tarea 17 de PR-0), en paralelo con H, A, B, C, D y E₁ en sus propios worktrees. F₂ continúa en la misma rama tras rebasarla sobre PR-E (§15: «0 (F₁) → E (F₂)»). Conflictos esperables, todos con resolución **por unión** (se conservan los cambios de ambos lados):

| Fichero | Con | Qué choca | Resolución |
|---|---|---|---|
| `revisia/exports/interop.py` | E (plan E, tarea E1.7) | E reescribe las líneas 28-57 (`render_robvis_csv` por herramienta) y añade `robvis_note` justo antes de `render_metafor_csv`, que F₁ cambia (`:60-76`): los bloques quedan contiguos | Unión: el código de E entero hasta `robvis_note` inclusive, después `render_metafor_csv` de F₁ |
| `revisia/exports/__init__.py` | E | imports y `__all__` contiguos (F₁ añade `render_outcome_forest_png` y `render_outcome_funnel_png`; E añade los suyos) | Unión de ambas listas, en orden alfabético como hoy |
| `tests/test_interop.py` | E | F₁ cambia la cabecera esperada de `test_metafor_csv_trae_yi_vi` (`:53`); E reescribe los tests de robvis, encima | Unión: los tests de robvis de E y el test de metafor de F₁ |
| `tests/test_auditor_meta_y_estados.py` | G₁ | F₁ cambia las líneas 90, 248 y 540-544; G₁ puede cambiar sus imports al partir `checks_flow.py` | Lo resuelve **G al rebasar sobre F** (G₂, §15), no F₂: unión de los imports de G₁ y las tres ediciones de F₁ |

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
  - `PooledEstimate` (`:63`) gana `test: Literal["z", "t"] = "z"`, `df: int | None = None` y `p_method: str = ""` (con `t`, el estadístico sigue en `z`; `p_method` vacío en DL, `"t (HKSJ)"` en la Tarea 5; el auditor lo ignora, `checks_flow.py:151`).
  - `Heterogeneity`, `EggerTest`: sin cambio.
  - `class SubgroupResult(BaseModel)`: `subgroup: str`, `k: int`, `random: PooledEstimate | None = None`, `heterogeneity: Heterogeneity | None = None`.
  - `class SubgroupTest(BaseModel)`: `q: float`, `df: int`, `p_value: float | None = None`, `p_method: str = ""`.
  - `class NotPooledOutcome(BaseModel)`: `outcome: str | None`, `k: int`, `study_ids: list[str]`.
  - `class OutcomeMeta(BaseModel)`: `outcome: str | None`, `k: int`, `measure: Measure`, `log_scale: bool`, `studies: list[StudyEffect]`, `fixed: PooledEstimate`, `random: PooledEstimate`, `heterogeneity: Heterogeneity`, `prediction_interval: PredictionInterval | None = None`, `egger: EggerTest | None = None`, `egger_note: str | None = None`, `subgroups: list[SubgroupResult] = []`, `q_between: SubgroupTest | None = None`, `duplicates: list[DuplicateEffect] = []`.
  - `class MetaAnalysisResult(BaseModel)` (sustituye a la plana, `:96`): `schema_version: int = ARTIFACT_SCHEMA_VERSION`, `random_method: RandomMethod = "DL"`, `outcomes: list[OutcomeMeta] = []`, `not_pooled: list[NotPooledOutcome] = []`, `excluded: int = Field(default=0, ge=0)`. Propiedades **no serializadas** (`@property`, no `computed_field`): `k -> int` = Σ `outcomes[].k`; `studies -> list[StudyEffect]` = concatenación de `outcomes[].studies` en orden. Docstring de `k`, literal en lo esencial: «Compatibilidad con `pipeline.py:1193` (`total_studies_ma` del CSV PRISMA2020) y con el "(k = N)" de `metodologia.md` (`methods.py:49-61`) hasta F₂. Cuenta **efectos** agregados, no estudios: con varios desenlaces o con `multiple_per_study` es mayor que el número de estudios. En F₁ coincide con lo que hoy comprueba el auditor (`len(effects)`, `checks_flow.py:1244`); F₂ y G₂ lo sustituyen por los `study_id` distintos (§19, fila propuesta n+9)».
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
    assert (res.schema_version, res.random_method) == (2, "DL")
    assert (res.excluded, res.not_pooled) == (0, [])
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
    assert o9.egger is None
    assert o9.egger_note == "Egger no calculado: k = 9 < 10 (Sterne et al. 2011)"
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
    tres = meta_analyze(
        [_e("a", 0.2, 0.04), _e("b", 0.4, 0.02), _e("c", 0.6, 0.01)], "precomputed"
    )
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
  - efectos idénticos: la guarda **no** es `SE_HK == 0` exacto (con yi = 0,7 × 4 los residuos valen ~1e-16 y `p` saldría 0), sino `q <= 1e-24`; entonces `SE_HK = 0.0`, `z = 0.0`, `p_value = 1.0`, IC `[μ̂, μ̂]`, sin división por cero;
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
    assert (r.test, r.df, r.p_method) == ("t", 12, "t (HKSJ)")
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


@pytest.mark.parametrize(
    ("yi", "vis"),
    [
        (0.3, (0.04, 0.02, 0.01)),
        # Residuos de ~1e-16 por redondeo: con la guarda `SE_HK == 0` exacta, p saldría 0.
        (0.7, (0.04, 0.02, 0.01, 0.03)),
    ],
)
def test_hksj_con_efectos_identicos_no_divide_por_cero(yi: float, vis: tuple[float, ...]) -> None:
    o = meta_analyze(
        [_e(f"s{i}", yi, v) for i, v in enumerate(vis)], "precomputed", random_method="HKSJ"
    ).outcomes[0]
    assert (o.random.se, o.random.z, o.random.p_value) == (0.0, 0.0, 1.0)
    assert o.random.ci_low == o.random.ci_high == pytest.approx(yi)


def test_sin_scipy_los_numeros_que_compara_el_auditor_no_cambian(monkeypatch) -> None:
    # `_meta_distinto` (audit/checks_flow.py:1843) ignora solo `p_value`/`p_method`.
    def _sin_p(valor):
        if isinstance(valor, dict):
            return {k: _sin_p(v) for k, v in valor.items() if k not in {"p_value", "p_method"}}
        return [_sin_p(v) for v in valor] if isinstance(valor, list) else valor

    efectos = _bcg() + [
        _e(f"x{i}", 0.1 * i, 0.01 * i, "otro", "g1" if i < 6 else "g2") for i in range(1, 12)
    ]
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
    # A y B: τ² = 0, θ = 0 y 1, SE = √0.5 → w = 2; θ̄ = 0.5;
    # Q = 2·0.25 + 2·0.25 = 1.0 (df 1).
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
    solo_uno = meta_analyze(
        [_e("a", 0.1, 0.1, "o", "A"), _e("b", 0.2, 0.1, "o", "A")], "precomputed"
    )
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
    3. k < 2 en un desenlace: `` f"el desenlace `{outcome}` tiene {k} efecto(s): el meta-análisis necesita al menos 2 por desenlace (k ≥ 2); añade efectos o quita ese desenlace" `` (conserva «k ≥ 2», que espera `test_errores_deterministas.py:249`). Razón de exigirlo **al cargar** (fila n+5): mantiene coherente en F₁ la relación 11 del auditor (`total_studies_ma == len(effects)`, `checks_flow.py:1244`), que no conoce `not_pooled`; D16 habla de k < 2 **tras filtrar** por incluidos, que es F₂.
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
    patron = r"unidad de análisis: `li-2024` aporta 27 efectos"
    with pytest.raises(ProtocolFilesError, match=patron):
        load_protocol_files(_escribir(tmp_path, _c3(multiple=False)))


def test_effects_de_c3_con_multiple_per_study_carga_y_queda_declarado(tmp_path: Path) -> None:
    efectos = load_protocol_files(_escribir(tmp_path, _c3(multiple=True))).effects
    assert efectos is not None and efectos.multiple_per_study.allowed is True
    assert "modelo × dataset" in efectos.multiple_per_study.justification
    assert meta_analyze(efectos.effects, efectos.measure).outcomes[0].k == 28


def test_random_method_outcome_y_k_por_desenlace() -> None:
    base = {"measure": "precomputed"}
    dos = [
        {"study_id": s, "outcome": "o", "yi": y, "vi": 0.02}
        for s, y in (("a", 0.1), ("b", 0.2))
    ]
    assert EffectsFile.model_validate({**base, "effects": dos}).random_method == "DL"
    hksj = EffectsFile.model_validate({**base, "effects": dos, "random_method": "HKSJ"})
    assert hksj.random_method == "HKSJ"
    with pytest.raises(ValidationError):
        EffectsFile.model_validate({**base, "effects": dos, "random_method": "REML"})
    with pytest.raises(ValidationError, match="espacios"):
        EffectsFile.model_validate({**base, "effects": [{**dos[0], "outcome": "o "}, dos[1]]})
    con_huerfano = [*dos, {"study_id": "c", "outcome": "otro", "yi": 0.3, "vi": 0.02}]
    with pytest.raises(ValidationError, match=r"el desenlace `otro` tiene 1 efecto\(s\).*k ≥ 2"):
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
- Modify: `tests/fakes.py` (añadido al final: `escribir_benchmark`).
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
    - (**Pendiente de OK del arquitecto, toca D6**; ver Step 0.) Por defecto, un efecto por (celda, corpus): `study_id = slug`, `yi` y `vi` = medias de `recall_effect` de sus réplicas, `outcome = "recall"`, sin `subgroup`; si algún corpus aporta > 1 réplica, nota `AVISO_PROMEDIO`. Con `replicas_as_effects=True`, un efecto por réplica: `study_id = f"{slug}#r{replica}"`, `subgroup = slug`, y nota `AVISO_EXPLORATORIO`.
    - Una réplica con `recall_effect(...) is None` no entra, con nota `"celda `<c>`, corpus `<s>`, réplica <r>: recall indefinido (sin positivos en el gold), excluida"`; una con `n_failed_records > 0` entra con nota `"celda `<c>`, corpus `<s>`, réplica <r>: <n> registros fallidos fuera de la matriz"`.
    - `meta = meta_analyze(efectos, "precomputed")` (DL); `recall*` = `expit` de `meta.outcomes[0].random` y su PI cuando hay desenlace agregado; si no, `None`.
    - Celdas en el orden de primera aparición; fuentes en el orden de `bench_dirs`.
  - `render_pooled_report(pooled: PooledBenchmark) -> str`: `# Benchmark agregado`; tabla de fuentes (`| Corpus | Registros | Positivos del gold | Réplicas |`); tabla `| Celda | Corpus (k) | Recall agregado | IC95% | IP95% | I² |` con `{:.3f}` y `—` donde no hay; las notas como lista; y por celda con desenlace agregado, una sección `## Celda: <c>` con `render_forest_markdown(cell.meta, display="proportion")` sin su título de nivel 1.
  - `write_pooled(pooled: PooledBenchmark, out_dir: str | Path) -> tuple[Path, Path]`: crea `out_dir` y escribe `meta_analysis.json` (`model_dump_json(indent=2)`, UTF-8) y `report.md`; devuelve ambas rutas.

- [ ] **Step 0: Comprobar el OK del arquitecto sobre los subgrupos (toca D6).** El diseño de esta tarea (`subgroup = corpus` solo con `--replicas-as-effects`; por defecto, réplicas promediadas y un efecto por corpus, fila propuesta n+8) está **pendiente de OK del arquitecto**. Antes de escribir código, el controlador comprueba en §19 del spec si la fila n+8 está aceptada. Si se **rechaza**, se aplica la alternativa literal de §10.2: un efecto por (corpus, celda, réplica) promediado por corpus con `outcome = "recall"` y **`subgroup = corpus` siempre**, agrupado por celda con `meta_analyze`; cambian `pool_benchmarks` (la regla «Por defecto…» de Interfaces) y las aserciones `o.subgroups == []` de `test_dos_corpus_promedian_replicas_y_agregan_por_celda` (pasan a `[("c1", 1), ("c2", 1)]`, sin `q_between` porque cada subgrupo tiene k = 1). El resto de la tarea no cambia.

- [ ] **Step 1: Ayudante de tests en `tests/fakes.py`** (no se importa un test desde otro; los tests de las Tareas 8 y 9 lo comparten). Añadir al final de `tests/fakes.py`, con sus imports en el bloque de cabecera (`hashlib`; `ScreeningMetrics`, `wilson_interval` de `revisia.metrics`; `Environment` de `revisia.schemas.artifacts`; `BenchmarkCellResult`, `BenchmarkProtocolInfo`, `BenchmarkResult` de `revisia.schemas.benchmark`). Es un añadido al final del fichero: si otra pista también añade a `fakes.py`, el conflicto se resuelve por unión.

```python
def _entorno() -> Environment:
    return Environment(
        engine_version="0.9.0",
        python_version="3.13.0",
        python_implementation="CPython",
        platform="x",
        created_utc="2026-10-19T00:00:00+00:00",
    )


def escribir_benchmark(
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
                n=tp + fn + 10,
                tp=tp,
                fp=2,
                fn=fn,
                tn=8,
                recall=tp / (tp + fn) if tp + fn else None,
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
```

(`n_gold_positives` usa `tp + fn` de la primera réplica de la primera celda; basta para el modelo.)

- [ ] **Step 2: Tests que fallan** — crear `tests/test_benchmark_report.py`:

```python
"""`benchmark-report`: efectos logit(recall) por corpus y agregación por celda (D6; §10.2)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from fakes import escribir_benchmark as benchmark

from revisia.benchmark.report import (
    AVISO_EXPLORATORIO,
    PooledBenchmark,
    pool_benchmarks,
    recall_effect,
    write_pooled,
)
from revisia.metrics import ScreeningMetrics


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
    assert (o.outcome, o.k, o.subgroups) == ("recall", 2, [])
    assert [s.study_id for s in o.studies] == ["c1", "c2"]
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

- [ ] **Step 3: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_benchmark_report.py -v`
Expected: FAIL (`ModuleNotFoundError: revisia.benchmark`).

- [ ] **Step 4: Implementar** según Interfaces (docstring del módulo: D6, D23, §10.2; por qué se promedian las réplicas; `expit` local).

- [ ] **Step 5: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_benchmark_report.py tests/test_benchmark_schemas.py -v && uv run python -c "import revisia, revisia.benchmark.report"`
Expected: PASS; el import no cicla (`revisia.schemas.benchmark` no se exporta desde `revisia.schemas`, PR-0 Tarea 13).

- [ ] **Step 6: Commit**

```bash
git add revisia/benchmark/__init__.py revisia/benchmark/report.py tests/fakes.py tests/test_benchmark_report.py
git commit -m "feat(benchmark): agregación logit(recall) por celda y corpus, con unidad de análisis (D6)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 9: `revisia benchmark-report` (`revisia/cli.py`)

**Files:**
- Modify: `revisia/cli.py`, con anclas fijas para no chocar con G₁, que ancla los suyos (`deposit`) en `export`: la función `_cmd_benchmark_report` justo **tras `_cmd_audit`** (`:527-548`); el subparser `p_benchmark_report` justo **tras `p_audit`** (`:692-696`); el despacho `if args.command == "benchmark-report": return _cmd_benchmark_report(args)` justo **tras el de `audit`** en `main` (`:738-739`), antes de cargar protocolo.
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
from fakes import escribir_benchmark as benchmark

from revisia import cli


def test_benchmark_report_escribe_pooled_en_el_primer_benchmark(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1)]})
    c2 = benchmark(tmp_path, "c2", {"a": [(18, 2)]})
    assert cli.main(["benchmark-report", str(c1), str(c2)]) == 0
    assert (c1 / "pooled" / "meta_analysis.json").is_file()
    assert (c1 / "pooled" / "report.md").is_file()
    salida = capsys.readouterr().out
    assert "a: recall 0.900" in salida and "k = 2" in salida


def test_benchmark_report_out_y_replicas_como_efectos(tmp_path: Path, capsys) -> None:
    c1 = benchmark(tmp_path, "c1", {"a": [(9, 1), (9, 1)]})
    c2 = benchmark(tmp_path, "c2", {"a": [(18, 2), (16, 4)]})
    out = tmp_path / "agregado"
    argv = ["benchmark-report", str(c1), str(c2), "--out", str(out), "--replicas-as-effects"]
    assert cli.main(argv) == 0
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

(El ayudante vive en `tests/fakes.py` desde la Tarea 8: ningún test importa otro test.)

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
| n+5 | D16, §10.1 | Unidad de análisis = `study_id` repetido dentro de un desenlace (`unit_of_analysis_violations`). `outcome` con espacios alrededor es error de carga. Cada desenlace necesita k ≥ 2 efectos al cargar (mensaje «tiene N efecto(s)»): así la relación 11 del auditor (`total_studies_ma == len(effects)`, `checks_flow.py:1244`), que no conoce `not_pooled`, sigue coherente en F₁; D16 habla de k < 2 **tras filtrar** por incluidos, y eso lo declara F₂ | Plan PR-F (F₁) |
| n+6 | §10.1 `effects_metafor.csv` | Una sola tabla con columnas `outcome,subgroup` añadidas al final (`study_id,label,measure,yi,vi,outcome,subgroup`); el funnel solo se dibuja con k ≥ 10, así que el demo (k = 4) deja de producir `funnel.png` | Plan PR-F (F₁) |
| n+7 | §10.1 `random_method` | `EffectsFile.random_method` se valida en F₁, pero el pipeline solo lo pasa a `meta_analyze` en F₂ (F₁ no toca `pipeline.py`) y el auditor en G₂. Ambas fases van en la misma PR: ninguna versión publicada lo ignora | Plan PR-F (F₁) |
| n+8 | §10.2 `benchmark-report` | **Pendiente de OK del arquitecto (toca D6).** Se agrupa por nombre de celda del panel. Por defecto, las réplicas de un corpus se promedian (yi y vi medios) y el corpus es el estudio; `subgroup = corpus` solo con `--replicas-as-effects` (con un efecto por corpus, cada subgrupo tendría k = 1). logit(recall) con corrección 0,5 solo si `tp` o `fn` es 0. Corpus repetido (slug o hash) → rc 2. `pooled/meta_analysis.json` guarda un `PooledBenchmark`. `--out` por defecto `<primer benchmark>/pooled`. Si se rechaza: alternativa literal de §10.2, `subgroup = corpus` siempre (Tarea 8, Step 0) | Plan PR-F (F₁) |
| n+9 | PRISMA2020 `total_studies_ma`, `metodologia.md` | (Para F₂ y G₂.) `total_studies_ma` y el «(k = N)» de `metodologia.md` = número de `study_id` distintos agregados, no Σk: la propiedad de compatibilidad `MetaAnalysisResult.k` de F₁ cuenta efectos (`pipeline.py:1193`, `methods.py:49-61`) | Plan PR-F (F₁, revisión) |
| n+10 | §4.1, §10.1 `meta_analysis.json` | §4.1 dice que existe «con efectos válidos tras filtrar» y §10.1 lo escribe con k < 2. Se adopta §10.1: `08_meta/meta_analysis.json` existe siempre que haya `effects.yml` en la instantánea; si ningún desenlace llega a k ≥ 2 tras filtrar, lleva `outcomes: []` y `excluded: n` | Plan PR-F (F₁, revisión) |
| n+11 | §4.2 `ExcludedEffect.reason` | `unit_of_analysis` no se produce nunca en ejecución: la violación es error de carga de `effects.yml` (rc 2). Propuesta: se conserva en el `Literal` (PR-0 ya lo dio) pero F₂ no lo emite, y G₂ da FAIL si aparece; retirarlo exigiría tocar el contrato de PR-0 | Plan PR-F (F₁, revisión) |
| n+12 | §10 tests, PI | «PI con los valores de `metafor::predict` sobre `dat.bcg`» se lee como `predict(rma(yi, vi, data=dat, method="DL"), pi.type="Riley")` (t con k − 2 gl, Higgins 2009): [−1,9988; 0,5706]. El `predict` por defecto (`test="z"`) usa el cuantil normal y da [−1,8582; 0,4299]. Valores calculados con numpy/scipy por el redactor y recalculados por el revisor; sin R. Si el implementador tiene R, anota la salida en el commit de la Tarea 4 | Plan PR-F (F₁, revisión) |
```

### Self-review de F₁

- **Cobertura de §10 que es de F₁:** `meta_analyze` v2 por desenlace (T3), PI con t de k − 2 gl y k ≥ 3 (T4), Egger solo k ≥ 10 con `egger_note` (T3), subgrupos con Q entre grupos (T6), duplicados a 1e-9 (T4), HKSJ opcional (T5), `EffectsFile` v2 con `outcome` obligatorio y mensaje de migración (rc 2), `multiple_per_study`, `random_method` y unidad de análisis (T7), `effects_metafor.csv` y forest/funnel por desenlace con funnel solo k ≥ 10 (T3), `benchmark-report` CLI y módulo (T8, T9). Tests de §10 que son de F₁: C3 sin `multiple_per_study` no carga y con él carga (T7); PI de `dat.bcg` a 4 decimales (T4); Egger `None` con k = 9 (T3); HKSJ sobre DL contra el cálculo manual (T5); `benchmark-report` sobre dos benchmarks sintéticos → subgrupos por corpus (T8, con `--replicas-as-effects`). Quedan para F₂: efecto de un no incluido → `excluded_effects`; k = 1 tras filtrar → sin meta-análisis declarado; el benchmark con el demo importado en dos celdas × 2 réplicas.
- **Valores numéricos:** μ̂, τ², Q, I² y SE de DL sobre `dat.bcg` coinciden con lo publicado por metafor (μ̂ ≈ −0,7141, τ² ≈ 0,3088, Q = 152,2330, I² = 92,12 %). El PI [−1,9988; 0,5706], el HKSJ (SE 0,180697; IC [−1,1078; −0,3204]; t −3,9520; p 0,001921) y su PI [−2,0002; 0,5719] se calcularon el 2026-10-19 con numpy 2.5.4 y scipy 1.18.1 aplicando las fórmulas de Higgins 2009 e IntHout 2014 (script en el scratchpad de la sesión, no versionado). El revisor independiente los recalculó con numpy y cuadran. **No se ejecutó R**: la lectura de «`metafor::predict`» como `pi.type="Riley"` va en la fila propuesta n+12.
- **Firmas verificadas contra el árbol (= `main` @ `c1af7c3`) el 2026-10-19:** `meta_analysis.py:29-214`, `schemas/effects.py:20-93`, `protocol_files.py:166-213,288-370`, `exports/forest.py:35-208`, `exports/interop.py:60-76`, `exports/__init__.py:16-54`, `exports/methods.py:40-63`, `pipeline.py:68,885-898,1144-1150,1193,1197-1200,1489-1490`, `audit/artifacts.py:40,582,612`, `audit/checks_flow.py:116,119,151,429-491,1236-1247,1843-1877,1880-1945,2161-2190`, `cli.py:527-548,609-797`, `metrics.py:30-53,121-138`. Los nombres de PR-0 (`RandomMethod`, `MultiplePerStudy`, `ExcludedEffect`, `ExcludedEffectsFile`, `PredictionInterval`, `DuplicateEffect`, `BenchmarkResult` y compañía, `Environment`) son los de las Tareas 12 y 13 de su plan.
- **Consistencia de tipos:** `OutcomeMeta`, `SubgroupResult`, `SubgroupTest`, `NotPooledOutcome` (T3) los rellenan T4–T6 y los consume T8; `meta_analyze(..., *, random_method)` (T5) lo consume T7; `unit_of_analysis_violations` (T7) queda para F₂ y G₂; `student_t_*` (T2) los consumen T4 y T5.
- **Proporción:** los bloques de código son tests con los valores del spec; los únicos algoritmos escritos son la t de Student, el PI, HKSJ y Q entre subgrupos, en fórmulas con su referencia.

---

## Fase F₂ (sobre PR-E)

**Estado de partida:** PR-0 + H + A + B + C + D + E (E₂ incluida) + F₁ rebasada. Lo que F₂ consume de cada pista, con la firma de su plan:

- **A** (`2026-10-19-ola2-pra-procedencia.md`, «ensure_snapshot»): `ensure_snapshot(protocol_dir, run_ctx, *, max_results, mailto) -> tuple[Path, RunInfo]` escribe `RunInfo(..., environment=collect_environment(...))` y lanza `PreOla2RunError` al reanudar una 0.8; `RunInfo.kind: RunKind = "review"` (PR-0 T5) **no lo escribe nadie todavía**; `write_manifest` copia `environment`.
- **B** (`2026-10-19-ola2-prb-identidad-registros.md`, Tarea 7): `ImportFormat = Literal["ris", "bibtex", "records_json"]` (`schemas/artifacts.py`); `import_format(path) -> ImportFormat | None`; `parse_records_json(text) -> list[SearchRecord]` (ids intactos, `record_id` repetido → `ValueError`); `import_file(path)`; `ignored_files(directory) -> list[str]`; `search_stage._import` pone `SearchLogEntry.format`.
- **C** (`2026-10-19-ola2-prc-texto-completo-extraccion.md`, «Estado en que C deja el pipeline»): `gates.failed_ids(decisions) -> list[str]` (T/A: sin votos y `ensemble_label is None`); `compute_screening_metrics` deja fuera de la matriz los registros con `ensemble_label` nulo; **contrato** `n_failed_records = len(failed_ids(decisions))` (§19 de C, fila n+9); `_FullTextStage(decisions, texts, retrieval)`; `render_methods(..., failed=...)`; fixtures `corrida_con_edicion_de_campo`, `corrida_con_rescate_con_texto`.
- **D** (`2026-10-19-ola2-prd-verificador.md`, «Estado en que D deja el pipeline»): `_write_deliverables(run, *, ..., retrieval, failed, verification: VerificationReport, ...) -> Path`; `report_payload(*, included, verification, documento, forced_human)`.
- **E₂** (`2026-10-19-ola2-pre-rob-por-herramienta.md`, «Estado en que E deja el pipeline»): `_Run.gate(..., fields=, domains=)`; `_rob_one(run, provider, cfg, spec, record, extraction, text)`; `_run_stages: … gate rob → apply_domain_edits → _meta_analysis(run) → _synthesize_and_verify → _write_deliverables → gate reporte`; `manifest_extra["rob"]`. E₂ no cambia `_meta_analysis` ni añade `stop_after`.
- **F₁** (arriba): el bloque «Interfaces que F₁ deja para F₂ y G₂».

Los números de línea de `pipeline.py` que se citan abajo son los de `c1af7c3` (`_meta_analysis` 885-898, `_write_deliverables` 1073-1201, `run_pipeline` 1234-1319, `_run_stages` 1322-1509); tras A–E se desplazan: el implementador localiza por nombre.

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
    p_method: str = ""            # "" en DL; "t (HKSJ)" con HKSJ

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
    def k(self) -> int: ...                      # compatibilidad: Σ outcomes[].k (cuenta efectos, no estudios; fila n+9)
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

Para F₂: `meta_analysis.json` existe siempre que haya `effects.yml` (fila n+10); `unit_of_analysis` no se emite (fila n+11); `total_studies_ma` = `study_id` distintos (fila n+9). `meta_analyze` no conoce los incluidos ni las exclusiones. `_meta_analysis(run, included_ids)` filtra, escribe `ExcludedEffectsFile` (PR-0) y fija el recuento con `result.model_copy(update={"excluded": n})`; con todo filtrado, `MetaAnalysisResult(outcomes=[], excluded=n, random_method=…)` es el resultado válido de §10.1. Debe pasar `random_method=effects.random_method` (supuesto n+7). F₂ añade `n_studies` (Tarea F2.1) y retira las propiedades `k`/`studies` (Tarea F2.2, fila n+20).

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

### Topología de F₂

En el mismo worktree `C:\revisia-wt\f`, rama `feat/ola2-meta-benchmark` rebasada sobre `feat/ola2-rob-por-herramienta`. Secuencial.

| Tarea | Fichero(s) | Depende de |
|---|---|---|
| F2.0 | rebase y reconciliación (controlador) | PR-E cerrada, F₁ |
| F2.1 | `orchestration/pipeline.py` (`_meta_analysis`, `meta_k`), `meta_analysis.py` (`n_studies`), `tests/conftest.py` (efectos de la auditoría; corrida sin registros sin efectos), tests | F2.0 |
| F2.2 | `exports/forest.py`, `exports/methods.py`, `exports/document.py`, `orchestration/pipeline.py` (`_write_deliverables`), `meta_analysis.py` (se retiran `k`/`studies`) | F2.1 |
| F2.3 | `orchestration/snapshot.py` (`kind`), `orchestration/run_context.py` (`create_at`), `llm/preflight.py` (`until`), `orchestration/pipeline.py` (`stop_after`, `kind`, docstring de `PipelineResult.stage`) | F2.0 |
| F2.4 | `revisia/benchmark/run.py` (preflight, huellas, protocolo de celda), `tests/conftest.py` (`protocolo_benchmark`) | F2.3 |
| F2.5 | `revisia/benchmark/run.py` (`run_benchmark`, `source.json`, `benchmark.json`, `benchmark.md`) | F2.4 |
| F2.6 | `revisia/cli.py` (`benchmark`), frontera | F2.5 |
| F2.7 | integración (controlador) | todas |

---

### Tarea F2.0: Rebase sobre E y reconciliación (controlador)

**Files:** los que choquen; ningún cambio de comportamiento.

**Interfaces:** ninguna nueva. Deja la rama sobre `feat/ola2-rob-por-herramienta` con la suite en verde.

- [ ] **Step 1: Rebase.** `git fetch && git rebase origin/feat/ola2-rob-por-herramienta`. Resolver por unión los conflictos de la tabla de la Topología de F₁ (`exports/interop.py`, `exports/__init__.py`, `tests/test_interop.py`); `tests/test_auditor_meta_y_estados.py` no choca aquí (lo resuelve G, §15). Si `tests/fakes.py` choca (F₁ añadió `escribir_benchmark` al final; C, D y E añadieron dobles), unión.
Expected: `git status` limpio tras `git rebase --continue`; `git log --oneline origin/feat/ola2-rob-por-herramienta..HEAD` lista los commits de F₁ (Tareas 2–9) y ninguno más.
- [ ] **Step 2: Símbolos que F₂ consume.**

Run: `uv run python -c "from revisia.ingest import parse_records_json, import_format, ignored_files; from revisia.schemas.artifacts import ImportFormat, RunKind; from revisia.orchestration.gates import failed_ids, report_payload; from revisia.orchestration.snapshot import collect_environment, protocol_fingerprint; from revisia.benchmark.report import pool_benchmarks; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Línea base tras el rebase.**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS con los XFAIL estrictos que traen A, C, D y E; anotar el recuento y la lista de XFAIL.

---

### Tarea F2.1: `_meta_analysis(run, included_ids)` y `excluded_effects.json` (D16)

**Files:**
- Modify: `revisia/orchestration/pipeline.py` (`_meta_analysis`, hoy `:885-898`; su llamada en `_run_stages`, hoy `:1421`; `meta_k=` de `render_prisma2020_flow_csv` **dentro de `_write_deliverables`**, hoy `:1193`).
- Modify: `revisia/meta_analysis.py` (propiedad `n_studies`; `k` y `studies` siguen hasta F2.2).
- Modify: `tests/conftest.py`: `protocolo_auditoria` escribe `effects.yml` con los tres incluidos (fila n+21); fixture de sesión nueva `protocolo_auditoria_sin_efectos` (copia sin `effects.yml`) y `_corrida_sin_registros` pasa a usarla (una revisión vacía no tiene efectos que declarar).
- Test: `tests/test_meta_pipeline.py` (nuevo); cambian los tests del Step 2.

**Interfaces:**
- Consumes: `ExcludedEffect`, `ExcludedEffectsFile` (PR-0); `meta_analyze(..., random_method=)` (F₁ T5); `EffectsFile.random_method` (F₁ T7).
- Produces:
  - `MetaAnalysisResult.n_studies -> int` (`@property`, no serializada): número de `study_id` distintos en `outcomes[].studies` (fila n+9).
  - `_meta_analysis(run: _Run, included_ids: Sequence[str]) -> tuple[MetaAnalysisResult | None, ExcludedEffectsFile | None, str]`: sin `effects.yml` → `(None, None, "raw")` y no escribe nada. Con él:
    1. `kept` = efectos con `study_id ∈ included_ids`, en el orden del fichero; cada uno de los demás → `ExcludedEffect(study_id, outcome, reason="not_included")`, en el orden del fichero;
    2. `included_without_effect` = `sorted(set(included_ids) − {study_id de los efectos})`;
    3. escribe `08_meta/excluded_effects.json` = `ExcludedEffectsFile(...).model_dump()` **siempre** que haya `effects.yml` (§4.1);
    4. `result = meta_analyze(kept, effects.measure, random_method=effects.random_method).model_copy(update={"excluded": len(excluded)})` y escribe `08_meta/meta_analysis.json` **siempre** (fila n+10); con k < 2 en todos los desenlaces, `outcomes == []`;
    5. devuelve `(result, exclusions, effects.display)`.
    `ExcludedEffect.reason = "unit_of_analysis"` no se produce (fila n+11).
  - En `_run_stages`: `meta_result, meta_exclusions, meta_display = _meta_analysis(run, [r.record_id for r in included])`; `meta_exclusions` viaja a `_write_deliverables` (kwarg nuevo, que F2.2 usa); `manifest_extra["meta_analysis"]` sigue siendo `meta_result.model_dump()`. En `_write_deliverables`, `render_prisma2020_flow_csv(counts, meta_k=meta_result.n_studies if meta_result is not None else None)`.
  - `tests/conftest.py`, constante y escritura en `protocolo_auditoria`:

```python
# Efectos de los tres estudios que incluye la corrida de auditoría (D16: un efecto por
# estudio incluido y desenlace). `secundario` se excluye en FT: no lleva efecto.
EFECTOS_AUDITORIA = """measure: precomputed
effects:
  - {study_id: "10.1000/llm-1", outcome: carga de cribado, yi: -0.62, vi: 0.05}
  - {study_id: "10.1000/asreview", outcome: carga de cribado, yi: -0.41, vi: 0.04}
  - {study_id: "10.1000/ensemble", outcome: carga de cribado, yi: -0.55, vi: 0.06}
"""
```

- [ ] **Step 1: Tests que fallan** — crear `tests/test_meta_pipeline.py` (todos los imports en la cabecera; las Tareas F2.2 añaden los suyos ahí, no a mitad de fichero):

```python
"""El meta-análisis se liga a los incluidos (spec 2026-10-18 §10.1, D16; relación 29)."""

from __future__ import annotations

import csv
import io
import shutil
from collections import Counter
from pathlib import Path

from conftest import _correr

from revisia.meta_analysis import MetaAnalysisResult
from revisia.schemas.effects import ExcludedEffectsFile

INCLUIDOS = ["10.1000/llm-1", "10.1000/asreview", "10.1000/ensemble"]


def _con_efectos(protocolo_auditoria: Path, tmp_path: Path, filas: list[str]) -> Path:
    destino = tmp_path / "proto" / protocolo_auditoria.name
    shutil.copytree(protocolo_auditoria, destino)
    texto = "measure: precomputed\neffects:\n" + "".join(f"  - {f}\n" for f in filas)
    (destino / "effects.yml").write_text(texto, encoding="utf-8")
    return destino


def _leer(run: Path) -> tuple[MetaAnalysisResult, ExcludedEffectsFile]:
    meta = MetaAnalysisResult.model_validate_json(
        (run / "08_meta" / "meta_analysis.json").read_text(encoding="utf-8")
    )
    excl = ExcludedEffectsFile.model_validate_json(
        (run / "08_meta" / "excluded_effects.json").read_text(encoding="utf-8")
    )
    return meta, excl


def _total_studies_ma(run: Path) -> str:
    ruta = run / "deliverable" / "interop" / "prisma2020_flow.csv"
    filas = list(csv.reader(io.StringIO(ruta.read_text(encoding="utf-8"))))
    columna = filas[0].index("n")
    (fila,) = [f for f in filas if f[0] == "total_studies_ma"]
    return fila[columna]


def test_efecto_de_un_no_incluido_va_a_excluded_effects(
    protocolo_auditoria: Path, tmp_path: Path
) -> None:
    filas = [
        '{study_id: "10.1000/llm-1", outcome: o, yi: -0.6, vi: 0.05}',
        '{study_id: "10.1000/asreview", outcome: o, yi: -0.4, vi: 0.04}',
        '{study_id: "10.1000/cocina", outcome: o, yi: 0.9, vi: 0.05}',
    ]
    proto = _con_efectos(protocolo_auditoria, tmp_path, filas)
    run = _correr(tmp_path / "runs", proto, parar_en=None)
    meta, excl = _leer(run)
    assert [(e.study_id, e.outcome, e.reason) for e in excl.excluded] == [
        ("10.1000/cocina", "o", "not_included")
    ]
    assert excl.included_without_effect == ["10.1000/ensemble"]
    assert [s.study_id for s in meta.outcomes[0].studies] == INCLUIDOS[:2]
    assert (meta.excluded, meta.n_studies) == (1, 2)
    # Relación 29 sobre el multiconjunto (study_id, outcome): agregados + excluidos == efectos.
    agregados = Counter((s.study_id, o.outcome) for o in meta.outcomes for s in o.studies)
    excluidos = Counter((e.study_id, e.outcome) for e in excl.excluded)
    assert agregados + excluidos == Counter(
        [("10.1000/llm-1", "o"), ("10.1000/asreview", "o"), ("10.1000/cocina", "o")]
    )
    assert _total_studies_ma(run) == "2"


def test_k_1_tras_filtrar_no_hay_meta_analisis(protocolo_auditoria: Path, tmp_path: Path) -> None:
    filas = [
        '{study_id: "10.1000/llm-1", outcome: o, yi: -0.6, vi: 0.05}',
        '{study_id: "10.1000/cocina", outcome: o, yi: 0.9, vi: 0.05}',
    ]
    run = _correr(tmp_path / "runs", _con_efectos(protocolo_auditoria, tmp_path, filas),
                  parar_en=None)
    meta, _ = _leer(run)
    assert (meta.outcomes, meta.excluded, meta.n_studies) == ([], 1, 0)
    assert [n.study_ids for n in meta.not_pooled] == [["10.1000/llm-1"]]
    assert _total_studies_ma(run) == "0"


def test_random_method_del_fichero_llega_al_resultado(
    protocolo_auditoria: Path, tmp_path: Path
) -> None:
    proto = _con_efectos(protocolo_auditoria, tmp_path, [])
    cuerpo = (protocolo_auditoria / "effects.yml").read_text(encoding="utf-8")
    texto = "random_method: HKSJ\n" + cuerpo
    (proto / "effects.yml").write_text(texto, encoding="utf-8")
    meta, _ = _leer(_correr(tmp_path / "runs", proto, parar_en=None))
    assert meta.random_method == "HKSJ" and meta.outcomes[0].random.test == "t"


def test_la_corrida_de_auditoria_agrega_sus_tres_incluidos(corrida: Path) -> None:
    meta, excl = _leer(corrida)
    assert [s.study_id for s in meta.outcomes[0].studies] == INCLUIDOS
    assert (excl.excluded, excl.included_without_effect) == ([], [])
    assert (meta.excluded, meta.n_studies) == (0, 3)
    assert _total_studies_ma(corrida) == "3"
```

- [ ] **Step 2: Cambiar las expectativas que D16 cambia** (exactas). Lista **cerrada** de XFAIL de F₂:
  - Valores nuevos (no `xfail`): `tests/test_auditor_meta_y_estados.py:112` `"4"` → `"3"`; `tests/test_audit.py:33-34` `deliverable` pasa de `"WARN"` a `"PASS"` con el comentario «sin aviso: los efectos son de los incluidos (D16)»; `tests/test_audit_flujo.py:1041-1048` se renombra `test_deliverable_no_avisa_cuando_los_efectos_son_de_los_incluidos`, afirma `deliverable.status == "PASS"` y conserva `"14 artefactos" in deliverable.detail`.
  - **Un solo `xfail(strict=True, reason="G₂: relación 29 (el auditor recalcula sin filtrar por incluidos)")`**: `tests/test_pipeline_fake.py::test_pipeline_fake_con_humano_audita_sin_fail`. Corre el demo (`examples/demo-mini-review`), cuyos cuatro efectos no son de sus incluidos, y el auditor de hoy recalcula con todos (`checks_flow.py:490`) y compara `total_studies_ma` con `len(effects)` (`:1244`).
  - Siguen en verde sin cambios, porque `_corrida_sin_registros` ya no tiene `effects.yml`: `tests/test_audit_aritmetica_ola1.py:905` (`test_arithmetic_pasa_en_la_corrida_sin_registros`), `:1089`, `:1435`; `tests/test_audit_flujo.py:1052` (`test_deliverable_avisa_de_una_revision_vacia`: WARN por «revisión vacía», publicable); `tests/test_audit_instantanea.py:749,807`.
  - Siguen en verde las corridas derivadas de `protocolo_auditoria` que usan C, D y E para sus fronteras (`corrida_con_juez`, `corrida_con_edicion_de_campo`, `corrida_con_rescate_con_texto`, `corrida_con_edicion_de_dominio`): incluyen los mismos tres estudios. Sus tests `…_solo_falla_lo_que_adapta_g2` no pueden ganar un FAIL nuevo; si lo ganan, es un fallo de F₂ y se corrige.
  - `tests/test_entregable_honesto.py:69-120` se reescriben en F2.2.

- [ ] **Step 3: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_pipeline.py -v`
Expected: FAIL (`08_meta/excluded_effects.json` no existe; `AttributeError: n_studies`).

- [ ] **Step 4: Implementar** según Interfaces.

- [ ] **Step 5: Run para verificar que pasa, con la suite entera**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS; XFAIL = los de F2.0 más `test_pipeline_fake_con_humano_audita_sin_fail` (si ya era XFAIL estricto de otra pista, se añade esta razón a la suya, sin duplicar el marcador); ningún XPASS. Los dos tests de `test_entregable_honesto.py` sobre el texto de la Ola 1 pueden fallar aquí solo si leen `metodologia.md` de una corrida: en ese caso se adelanta su reescritura de F2.2.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/pipeline.py revisia/meta_analysis.py tests/conftest.py tests/test_meta_pipeline.py tests/test_auditor_meta_y_estados.py tests/test_audit.py tests/test_audit_flujo.py tests/test_pipeline_fake.py
git commit -m "feat(meta): el meta-análisis agrega solo los efectos de los incluidos y lista los excluidos (D16)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea F2.2: Declaraciones y figuras por desenlace en el entregable; fuera `k`/`studies`

**Files:**
- Modify: `revisia/exports/forest.py` (`render_forest_markdown`), `revisia/exports/methods.py` (`_meta_analysis_text`, `render_methods`: sale `included_ids`), `revisia/exports/document.py:208-211,471-478` (`_FIGURAS_META` y su bucle), `revisia/orchestration/pipeline.py` (`_write_deliverables`), `revisia/meta_analysis.py` (se retiran `k` y `studies`).
- Test: `tests/test_meta_pipeline.py`, `tests/test_export_document.py` (añadir); cambian `tests/test_meta_analysis.py:38` (`res.k == 2` → `res.outcomes[0].k == 2`) y `tests/test_entregable_honesto.py:69-120` (incluida la `:89`, `included_ids=[s.study_id for s in meta.studies]`, que desaparece con el parámetro).

**Interfaces:**
- Consumes: `ExcludedEffectsFile`, `MultiplePerStudy` (PR-0); `render_outcome_forest_png`, `render_outcome_funnel_png` (F₁ T3).
- Produces:
  - `MetaAnalysisResult` sin `k` ni `studies` (fila n+20). Comprobación: `grep -rnE "\.(k|studies)\b" revisia tests` solo devuelve usos sobre `OutcomeMeta`/`SubgroupResult`/`NotPooledOutcome` (`o.k`, `o.studies`, `s.k`, `n.k`) y ninguno sobre un `MetaAnalysisResult` (`res.`, `meta.`, `meta_result.`, `result.`, `calculo.`); el implementador revisa cada línea que devuelva.
  - `render_forest_markdown(result, *, display="raw", exclusions: ExcludedEffectsFile | None = None) -> str`: con `exclusions` y algo que declarar, tras las líneas de cabecera, la sección `## Efectos excluidos del análisis` con una línea por efecto `` f"- `{study_id}` (desenlace `{outcome or 'único'}`): no está entre los incluidos" `` y, si hay, `` f"- Incluidos sin efecto declarado: {', '.join(ids)}" ``. Sin nada que declarar, el texto es **idéntico** al de F₁ (fila n+22).
  - `render_methods(*, ..., meta_result=None, meta_exclusions: ExcludedEffectsFile | None = None, multiple_per_study: MultiplePerStudy | None = None, ...)`: **sale `included_ids`** (ya no lo lee nadie); resto de kwargs como los deja E. `_meta_analysis_text(meta_result, meta_exclusions, multiple_per_study) -> str`, con este texto exacto, por partes, ids unidos con `", "` (más de 10: los 10 primeros y `f" (+{n - 10})"`):
    - base: `` f"cuantitativa: meta-análisis por desenlace ({modelo}) de los efectos de `effects.yml` de los estudios incluidos: {meta_result.n_studies} estudio(s) en {len(meta_result.outcomes)} desenlace(s)" ``, `modelo` = `"DerSimonian-Laird"` o `"DerSimonian-Laird con ajuste HKSJ"`;
    - con excluidos: `` f"; {n} efecto(s) excluido(s) por no estar entre los incluidos ({ids})" ``;
    - con incluidos sin efecto: `` f"; incluidos sin efecto declarado: {ids}" ``;
    - sin desenlaces agregados: `"; ningún desenlace llega a k ≥ 2 tras filtrar: sin meta-análisis"`;
    - con `multiple_per_study.allowed`: `` f"; varios efectos por estudio admitidos (`multiple_per_study`): {justification}" ``.
  - `_write_deliverables(run, *, ..., meta_result, meta_exclusions: ExcludedEffectsFile | None, meta_display, ...)`: pasa `meta_exclusions` a `render_forest_markdown` y a `render_methods` (con `multiple_per_study=run.files.effects.multiple_per_study` si hay efectos). Figuras: **antes de escribir**, borra de `deliverable/assets/` todo `forest*.png` y `funnel*.png` (una reanudación con otros desenlaces no deja figuras viejas); para el desenlace agregado `i` (1-based) escribe `forest.png`/`funnel.png` si `i == 1` y `forest-{i}.png`/`funnel-{i}.png` si no (fila n+18); funnel solo con k ≥ 10 (F₁). `effects_metafor.csv` se escribe siempre que haya `meta_result` (con `outcomes == []`, solo cabecera; el auditor de hoy lo exige con efectos, `checks_flow.py:2130`).
  - `exports/document.py`: `_FIGURAS_META` deja de ser una tupla fija y pasa a una función `_figuras_meta(run_dir: Path) -> list[tuple[str, str]]` que lee `08_meta/meta_analysis.json` (si no existe o no valida, la lista de hoy: `forest.png`, `funnel.png` con sus pies) y devuelve, para cada desenlace agregado `i`, `(forest[-i].png, f"Forest plot · {nombre}: efecto por estudio y combinado.")` y `(funnel[-i].png, f"Funnel plot · {nombre} (asimetría / sesgo de publicación).")`, con `nombre = outcome or "desenlace único"`; el bucle de `:471-478` itera sobre ella (solo añade las que existen, como hoy).

- [ ] **Step 1: Tests que fallan.** Añadir a la cabecera de `tests/test_meta_pipeline.py`: `import pytest` (`protocolo_auditoria` es una fixture: no se importa), `from revisia.config import load_protocol`, `from revisia.exports.forest import render_forest_markdown`, `from revisia.exports.methods import render_methods`, `from revisia.exports.prisma_flow import PrismaCounts`, `from revisia.meta_analysis import meta_analyze`, `from revisia.schemas.effects import EffectInput, ExcludedEffect, MultiplePerStudy` (y en `tests/test_export_document.py`, `import json` si falta). Y estos tests:

```python
def _resultado() -> MetaAnalysisResult:
    efectos = [
        EffectInput(study_id=s, yi=y, vi=0.05, outcome="o") for s, y in (("a", -0.6), ("b", -0.4))
    ]
    return meta_analyze(efectos, "precomputed").model_copy(update={"excluded": 1})


def _exclusiones() -> ExcludedEffectsFile:
    return ExcludedEffectsFile(
        excluded=[ExcludedEffect(study_id="z", outcome="o", reason="not_included")],
        included_without_effect=["c"],
    )


def test_meta_analisis_md_declara_los_excluidos_y_sin_ellos_no_cambia() -> None:
    con = render_forest_markdown(_resultado(), exclusions=_exclusiones())
    assert "## Efectos excluidos del análisis" in con
    assert "- `z` (desenlace `o`): no está entre los incluidos" in con
    assert "- Incluidos sin efecto declarado: c" in con
    vacio = render_forest_markdown(_resultado(), exclusions=ExcludedEffectsFile())
    assert vacio == render_forest_markdown(_resultado())


def test_metodologia_declara_filtrado_multiples_y_modelo(protocolo_auditoria: Path) -> None:
    md = render_methods(
        protocol=load_protocol(protocolo_auditoria),
        counts=PrismaCounts(),
        meta_result=_resultado(),
        meta_exclusions=_exclusiones(),
        multiple_per_study=MultiplePerStudy(allowed=True, justification="dos brazos"),
    )
    assert (
        "cuantitativa: meta-análisis por desenlace (DerSimonian-Laird) de los efectos de "
        "`effects.yml` de los estudios incluidos: 2 estudio(s) en 1 desenlace(s); 1 efecto(s) "
        "excluido(s) por no estar entre los incluidos (z); incluidos sin efecto declarado: c; "
        "varios efectos por estudio admitidos (`multiple_per_study`): dos brazos"
    ) in md


def test_k_1_tras_filtrar_se_declara_en_metodologia(
    protocolo_auditoria: Path, tmp_path: Path
) -> None:
    filas = [
        '{study_id: "10.1000/llm-1", outcome: o, yi: -0.6, vi: 0.05}',
        '{study_id: "10.1000/cocina", outcome: o, yi: 0.9, vi: 0.05}',
    ]
    run = _correr(tmp_path / "runs", _con_efectos(protocolo_auditoria, tmp_path, filas),
                  parar_en=None)
    metodos = (run / "deliverable" / "metodologia.md").read_text(encoding="utf-8")
    assert "ningún desenlace llega a k ≥ 2 tras filtrar: sin meta-análisis" in metodos
    assert "1 efecto(s) excluido(s) por no estar entre los incluidos (10.1000/cocina)" in metodos


def test_figuras_por_desenlace(protocolo_auditoria: Path, tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    filas = [
        '{study_id: "10.1000/llm-1", outcome: o1, yi: -0.6, vi: 0.05}',
        '{study_id: "10.1000/asreview", outcome: o1, yi: -0.4, vi: 0.04}',
        '{study_id: "10.1000/llm-1", outcome: o2, yi: 0.2, vi: 0.05}',
        '{study_id: "10.1000/ensemble", outcome: o2, yi: 0.3, vi: 0.04}',
    ]
    proto = _con_efectos(protocolo_auditoria, tmp_path, filas)
    proto.joinpath("effects.yml").write_text(
        "multiple_per_study: {allowed: true, justification: dos desenlaces}\n"
        + proto.joinpath("effects.yml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    run = _correr(tmp_path / "runs", proto, parar_en=None)
    assets = run / "deliverable" / "assets"
    assert (assets / "forest.png").is_file() and (assets / "forest-2.png").is_file()
    assert not (assets / "funnel.png").exists()  # k = 2 < 10
```

(`multiple_per_study` no hace falta para la unidad de análisis —`llm-1` aparece una vez por desenlace—; está para que `metodologia.md` lo declare. Si estorba al implementador, se quita sin cambiar el test.)

  Y en `tests/test_export_document.py`, con la fixture `run_dir` de ese fichero:

```python
def test_figuras_meta_por_desenlace_con_el_nombre_del_desenlace(run_dir: Path) -> None:
    assets = run_dir / "deliverable" / "assets"
    (assets / "forest-2.png").write_bytes((assets / "forest.png").read_bytes())
    meta = {"outcomes": [{"outcome": "mortalidad"}, {"outcome": "ingresos"}]}
    (run_dir / "08_meta").mkdir(exist_ok=True)
    (run_dir / "08_meta" / "meta_analysis.json").write_text(json.dumps(meta), "utf-8")
    html = assemble_html(run_dir)
    assert "Forest plot · mortalidad" in html and "Forest plot · ingresos" in html
```

  (`meta_analysis.json` incompleto: `_figuras_meta` solo lee `outcomes[].outcome` con un `TypeAdapter` mínimo propio, no `MetaAnalysisResult` entero; si no valida, cae a la lista de hoy. Si el implementador prefiere validar `MetaAnalysisResult`, escribe aquí un resultado real con `meta_analyze(...).model_dump_json()`.)

  Y reescribir `tests/test_entregable_honesto.py:69-120`:
  - la primera prueba llama a `render_methods(..., meta_result=meta, meta_exclusions=ExcludedEffectsFile(…))` (sin `included_ids`, también en la `:89`) y afirma las partes del texto nuevo y la ausencia de «no derivados de la extracción»;
  - `test_corrida_demo_declara_…` pasa a `test_corrida_demo_declara_los_efectos_excluidos` y afirma en `metodologia.md` `"4 efecto(s) excluido(s) por no estar entre los incluidos (estudio-bogota-2019, estudio-lima-2020, estudio-santiago-2021, estudio-medellin-2022)"`, `"incluidos sin efecto declarado: rec-1"` y `"ningún desenlace llega a k ≥ 2 tras filtrar: sin meta-análisis"`. `rec-1` **está** entre los incluidos de esa corrida: el test de hoy afirma «4 de los 4 estudios … no están entre los incluidos» y no «la corrida no incluyó ningún estudio», que es la rama de 0 incluidos (`methods.py:57-58`).
  - `tests/test_meta_analysis.py:38`: `assert res.k == 2` → `assert res.outcomes[0].k == 2`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_meta_pipeline.py tests/test_entregable_honesto.py tests/test_export_document.py -v`
Expected: FAIL (`TypeError: render_forest_markdown() got an unexpected keyword argument 'exclusions'`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa, con la suite**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && uv run pytest -p no:cacheprovider -m cronometrado && grep -rnE "\.(k|studies)\b" revisia tests`
Expected: PASS con los XFAIL de F2.1 y ninguno más; el `grep` solo devuelve usos sobre desenlaces/subgrupos (revisarlos uno a uno).

- [ ] **Step 5: Commit**

```bash
git add revisia/exports/forest.py revisia/exports/methods.py revisia/exports/document.py revisia/orchestration/pipeline.py revisia/meta_analysis.py tests/test_meta_pipeline.py tests/test_export_document.py tests/test_entregable_honesto.py tests/test_meta_analysis.py
git commit -m "feat(meta): metodologia.md y meta_analisis.md declaran el filtrado; figuras por desenlace con su nombre (D16)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea F2.3: `run_pipeline(..., stop_after=, kind=)`, `run.json.kind` y preflight hasta T/A (D23)

**Files:**
- Modify: `revisia/orchestration/snapshot.py` (`ensure_snapshot`, tal como la deja A; `RunKindMismatchError`), `revisia/orchestration/run_context.py` (`RunContext.create_at`), `revisia/llm/preflight.py` (`preflight(..., until=)`), `revisia/orchestration/pipeline.py` (`run_pipeline`, `_run_stages`, docstring de `PipelineResult.stage`, hoy `:162-163`).
- Test: `tests/test_stop_after.py` (nuevo).

`snapshot.py` y `run_context.py` son de A (§15) y `preflight.py` de A y B: F₂ solo añade un parámetro con default y una clase (fila n+23).

**Interfaces:**
- Consumes: `RunKind` (PR-0), `ProtocolMismatchError` (`snapshot.py`; rc 2 vía `_CONFIG_ERRORS` y `_run_guarded`), `STAGES`.
- Produces:
  - `class RunKindMismatchError(ProtocolMismatchError)` en `snapshot.py`, `files=["run.json"]`, mensaje: `` f"{run_dir}: corrida de tipo `{actual}`; se reanuda con la orden con que empezó ({orden})" `` con `orden` = `` "`revisia benchmark <protocolo> --panel <panel.yml>`" `` si `actual == "benchmark"` y `` "`revisia run --resume <run_dir>`" `` si no.
  - `ensure_snapshot(protocol_dir, run_ctx, *, max_results, mailto, kind: RunKind = "review") -> tuple[Path, RunInfo]`: en una corrida nueva escribe `RunInfo(..., kind=kind)`. La comprobación de tipo **no** está aquí (ver `run_pipeline`).
  - `RunContext.create_at(run_dir: str | Path, *, slug: str, timestamp: str) -> RunContext` (classmethod): como `__init__` (misma guarda `RunDirExistsError` de carpeta no vacía) pero con la carpeta exacta.
  - `preflight(..., until: str | None = None)`: con `until`, `stages_in_use` y `check_retired` solo miran las etapas de `STAGES` hasta `until` inclusive (en un benchmark, `busqueda`, `dedup` y `screening_ta`): el proveedor de extracción o de síntesis de un protocolo de benchmark no tiene por qué estar disponible (fila n+24). Con un `until` anterior a `sintesis` tampoco se ejecutan las comprobaciones de `grounding_issues` (D): un protocolo en `judge` sin `llm.verificador` no bloquea el benchmark.
  - `run_pipeline(protocol, protocol_dir, run_ctx, *, …, stop_after: Literal["screening_ta"] | None = None, kind: RunKind = "review") -> PipelineResult`, en este orden, **antes de tocar nada**:
    1. `(kind == "benchmark") != (stop_after == "screening_ta")` → `ValueError("kind='benchmark' y stop_after='screening_ta' van juntos")` (error de programación: los dos sentidos);
    2. `before = read_run_info(run_ctx.run_dir)`; `before is not None and before.kind != kind` → `RunKindMismatchError` (sin escribir `run.json`);
    3. preflight con `until=stop_after`; después `ensure_snapshot(..., kind=kind)`.
    En `_run_stages`, justo después de `_screen_ta` y **antes** del gate de T/A: con `stop_after == "screening_ta"`, `run.finish("completed", "screening_ta")` y `return PipelineResult("completed", f"Cribado T/A terminado (corrida {kind}): sin gates ni entregable.", metrics=run.metrics, run_dir=run.ctx.run_dir, stage="screening_ta")`. No hay `decisions_ledger.jsonl`, `review_request.yml`, `deliverable/` ni `manifest.yml` (relación 31; fila n+16). Docstring de `PipelineResult.stage`: «Gate en el que se detuvo la corrida (pausa o rechazo), `"screening_ta"` en una corrida de benchmark terminada (`stop_after`), o `None` si se completó».

- [ ] **Step 1: Tests que fallan** — crear `tests/test_stop_after.py`:

```python
"""`stop_after="screening_ta"` y `kind: benchmark` (spec 2026-10-18 §10.2, D23; relación 31)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from conftest import busqueda_auditoria, proveedor_auditoria
from fakes import fetch_disponible

from revisia.config import load_protocol
from revisia.llm.preflight import preflight
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.run_context import RunContext, RunDirExistsError
from revisia.orchestration.snapshot import RunKindMismatchError, read_run_info


def _ahora() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def _benchmark(protocolo: Path, run_dir: Path, monkeypatch) -> pipeline_mod.PipelineResult:
    monkeypatch.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
    protocol = load_protocol(protocolo)
    if (run_dir / "run.json").exists():
        ctx = RunContext.open(run_dir)
    else:
        ctx = RunContext.create_at(run_dir, slug=protocol.slug, timestamp=_ahora())
    return pipeline_mod.run_pipeline(
        protocol, protocolo, ctx, search_fn=busqueda_auditoria, fetch_fn=fetch_disponible,
        stop_after="screening_ta", kind="benchmark",
    )


def test_benchmark_se_detiene_tras_ta_sin_gates_ni_entregable(
    protocolo_auditoria: Path, tmp_path: Path, monkeypatch
) -> None:
    run_dir = tmp_path / "runs" / "fake-a-r1"
    resultado = _benchmark(protocolo_auditoria, run_dir, monkeypatch)
    assert (resultado.status, resultado.stage) == ("completed", "screening_ta")
    info = read_run_info(run_dir)
    assert (info.kind, info.status, info.stage) == ("benchmark", "completed", "screening_ta")
    assert info.slug == load_protocol(protocolo_auditoria).slug
    assert (run_dir / "03_screening" / "metrics.json").is_file()
    for ausente in ("decisions_ledger.jsonl", "deliverable", "manifest.yml", "screening_ta"):
        assert not (run_dir / ausente).exists(), ausente
    assert resultado.metrics is not None and resultado.metrics.n == 6


def test_benchmark_reanudado_no_repite_llamadas(
    protocolo_auditoria: Path, tmp_path: Path, monkeypatch
) -> None:
    run_dir = tmp_path / "runs" / "fake-a-r1"
    _benchmark(protocolo_auditoria, run_dir, monkeypatch)
    llamadas = (run_dir / "llm_calls.jsonl").read_bytes()
    _benchmark(protocolo_auditoria, run_dir, monkeypatch)
    assert (run_dir / "llm_calls.jsonl").read_bytes() == llamadas


def test_reanudar_un_benchmark_como_revision_es_rc_2_sin_tocar_run_json(
    protocolo_auditoria: Path, tmp_path: Path, monkeypatch
) -> None:
    run_dir = tmp_path / "runs" / "fake-a-r1"
    _benchmark(protocolo_auditoria, run_dir, monkeypatch)
    antes = (run_dir / "run.json").read_bytes()
    with pytest.raises(RunKindMismatchError, match="revisia benchmark"):
        pipeline_mod.run_pipeline(
            load_protocol(protocolo_auditoria), None, RunContext.open(run_dir),
            search_fn=busqueda_auditoria, fetch_fn=fetch_disponible,
        )
    assert (run_dir / "run.json").read_bytes() == antes


@pytest.mark.parametrize(
    "kwargs", [{"kind": "benchmark"}, {"stop_after": "screening_ta"}], ids=["sin-stop", "sin-kind"]
)
def test_kind_y_stop_after_van_juntos(
    protocolo_auditoria: Path, tmp_path: Path, kwargs: dict
) -> None:
    ctx = RunContext.create_at(tmp_path / "x", slug="s", timestamp=_ahora())
    with pytest.raises(ValueError, match="van juntos"):
        pipeline_mod.run_pipeline(
            load_protocol(protocolo_auditoria), protocolo_auditoria, ctx, **kwargs
        )
    assert not (tmp_path / "x" / "run.json").exists()


def test_preflight_hasta_screening_ta_ignora_las_etapas_posteriores(
    protocolo_auditoria: Path, tmp_path: Path
) -> None:
    raw = yaml.safe_load((protocolo_auditoria / "protocol.yml").read_text(encoding="utf-8"))
    raw["llm"]["extraccion"] = {"provider": "gemini", "model": "gemini-2.5-pro"}
    proto = tmp_path / protocolo_auditoria.name
    proto.mkdir()
    for f in protocolo_auditoria.iterdir():
        if f.is_file():
            (proto / f.name).write_bytes(f.read_bytes())
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    entorno = {}  # sin GEMINI_API_KEY
    completo = preflight(load_protocol(proto), proto, context="run", env=entorno)
    hasta_ta = preflight(
        load_protocol(proto), proto, context="run", env=entorno, until="screening_ta"
    )
    assert any("extraccion" in i.where for i in completo.errors)
    assert not any("extraccion" in i.where for i in hasta_ta.errors)


def test_judge_sin_verificador_no_bloquea_el_benchmark(
    protocolo_auditoria: Path, tmp_path: Path, monkeypatch
) -> None:
    # grounding_issues (D) es de la etapa `sintesis`: con until="screening_ta" no se ejecuta.
    raw = yaml.safe_load((protocolo_auditoria / "protocol.yml").read_text(encoding="utf-8"))
    raw["grounding"] = "judge"
    raw["llm"].pop("verificador", None)
    proto = tmp_path / protocolo_auditoria.name
    proto.mkdir()
    for f in protocolo_auditoria.iterdir():
        if f.is_file():
            (proto / f.name).write_bytes(f.read_bytes())
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    mensaje = "grounding: judge necesita llm.verificador"
    completo = preflight(load_protocol(proto), proto, context="run", env={})
    hasta_ta = preflight(load_protocol(proto), proto, context="run", env={}, until="screening_ta")
    assert any(mensaje in i.message for i in completo.errors)
    assert not any(mensaje in i.message for i in hasta_ta.errors)
    resultado = _benchmark(proto, tmp_path / "runs" / "fake-a-r1", monkeypatch)
    assert (resultado.status, resultado.stage) == ("completed", "screening_ta")


def test_create_at_no_reutiliza_una_carpeta_con_contenido(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "algo").write_text("1", encoding="utf-8")
    with pytest.raises(RunDirExistsError):
        RunContext.create_at(tmp_path / "x", slug="s", timestamp=_ahora())
```

(`metrics.n == 6`: los seis ids de `GOLD_AUDITORIA` están entre los registros de `busqueda_auditoria`. Si el `where` del preflight para la etapa de extracción no contiene `"extraccion"`, el implementador lo comprueba en `stages_in_use` y ajusta el literal del test, no el criterio.)

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_stop_after.py -v`
Expected: FAIL (`AttributeError: type object 'RunContext' has no attribute 'create_at'`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa, con la suite entera**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS con los XFAIL de F2.1 y ninguno más.

- [ ] **Step 5: Commit**

```bash
git add revisia/orchestration/snapshot.py revisia/orchestration/run_context.py revisia/llm/preflight.py revisia/orchestration/pipeline.py tests/test_stop_after.py
git commit -m "feat(pipeline): stop_after=screening_ta y run.json.kind=benchmark, preflight hasta T/A (D23)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea F2.4: Preflight del benchmark, huellas y protocolo de celda (`revisia/benchmark/run.py`)

**Files:**
- Create: `revisia/benchmark/run.py`.
- Modify: `tests/conftest.py` (`protocolo_benchmark`, junto a `protocolo_auditoria`: lo usan F2.4, F2.5 y F2.6; en `fakes.py` crearía un import circular).
- Test: `tests/test_benchmark_run.py` (nuevo).

**Interfaces:**
- Consumes: `BenchmarkPanel`, `BenchmarkCell` (PR-0 T13); `import_format`, `import_file`, `ignored_files` (B); `search_backends.db_key`, `MANUAL_ONLY` (`agents/search_backends.py:210,240`); `load_protocol_files`, `ProtocolFilesError`; `preflight(..., until=)` (F2.3); `PreflightIssue`, `PreflightReport` (`llm/preflight.py:92-115`); `protocol_fingerprint` (`snapshot.py`); `canonical_sha256`; `rechazar_claves_de_fusion`, `load_protocol` (`config.py`).
- Produces:
  - `corpus_fingerprint(imported_dir: Path) -> str`: `canonical_sha256([[nombre, sha256(bytes)] …])` de los ficheros con `import_format(p) is not None`, en orden de nombre. Es la huella **de la fuente** (para `source.json`, F2.5); la de `benchmark.json` sale de las corridas (F2.5).
  - `cell_protocol(protocol: ReviewProtocol, cell: BenchmarkCell) -> ReviewProtocol` = `protocol.model_copy(update={"llm": {**protocol.llm, "screening_ta": cell.to_provider_config()}}, deep=True)` (§10.2).
  - `benchmark_preflight(protocol: ReviewProtocol, protocol_dir: str | Path, panel: BenchmarkPanel, *, mailto: str | None = None, env: Mapping[str, str] | None = None, find_spec=None, which=None) -> PreflightReport` (sin red, antes de crear nada). Errores (`where` entre corchetes) y textos:
    1. `[databases]` vacío: `"un benchmark necesita declarar la base de la que sale el corpus (una base de importación manual, p. ej. Scopus)"`;
    2. `[databases]` por cada base cuya `db_key` no está en `MANUAL_ONLY`: `` f"`{db}` no es una base de importación manual: un benchmark corre sobre un corpus congelado (solo imported/, D23)" ``;
    3. `[imported/]` sin ningún fichero importable: `"sin corpus congelado: pon el corpus en imported/ (*.records.json nativo, D23, o RIS/BibTeX)"`; un fichero que `import_file` no lee: `` f"imported/{nombre}: {motivo}" ``; **avisos** por cada `ignored_files` y, si hay RIS/BibTeX, `"los registros sin DOI cambian de id al importar RIS/BibTeX: el gold de la exploratoria puede no casar; usa *.records.json (D23)"`;
    4. `[gold.yml]` sin gold o con una sola clase: `"el benchmark necesita gold.yml con las dos clases (incluir y excluir)"`; ids fuera del corpus importado: `` f"{n} ids del gold no están en el corpus importado ({ids})" `` (hasta 5); un `ProtocolFilesError` con su texto;
    5. `[ensemble]` si `"screening_ta" in protocol.ensemble`: `"screening_ta en ensemble: en un benchmark el modelo de T/A lo fija cada celda del panel"`;
    6. por celda, los issues de `preflight(cell_protocol(protocol, cell), protocol_dir, context="run", mailto=mailto, env=env, find_spec=find_spec, which=which, until="screening_ta")` con `where` prefijado `f"panel.cells[{cell.name}] · "` (deduplicados: los que no dependen de la celda se informan una vez).
  - `materialize_cell_protocol(protocol_dir: str | Path, cell: BenchmarkCell, slug: str, dest: Path) -> tuple[Path, ReviewProtocol]`: copia la carpeta del protocolo entera (con `imported/`) a `dest` y reescribe `protocol.yml` sobre el YAML original (`rechazar_claves_de_fusion`, `yaml.safe_load`) con `slug: <slug>` explícito (`load_protocol` usa el nombre de la carpeta si falta, `config.py:299`, y la carpeta es `protocols/<celda>`) y `llm.screening_ta = cell.to_provider_config().model_dump(mode="json", exclude_none=True)`; lo demás no cambia. Devuelve `(dest, load_protocol(dest))`. Si `dest` existe, no lo reescribe: lo carga y comprueba que `provider_for("screening_ta")` es el de la celda y `slug` el pedido (si no, `ValueError`). Es la forma materializada de `cell_protocol` (fila n+14).
  - `tests/conftest.py`: `protocolo_benchmark(tmp_path: Path) -> Path` (función, no fixture), con el cuerpo del test de abajo.

- [ ] **Step 1: Tests que fallan.** Añadir a `tests/conftest.py`, junto a `protocolo_auditoria` (con `json` en sus imports si falta):

```python
def protocolo_benchmark(tmp_path: Path) -> Path:
    """El demo con corpus nativo congelado, base manual, gold de dos clases y sin ensemble."""
    destino = tmp_path / "proto" / DEMO.name
    shutil.copytree(DEMO, destino)
    raw = yaml.safe_load((destino / "protocol.yml").read_text(encoding="utf-8"))
    raw.update({"databases": ["Scopus"], "ensemble": []})
    (destino / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), "utf-8")
    (destino / "imported").mkdir()
    corpus = [r.model_dump(mode="json") for r in REGISTROS_AUDITORIA]
    (destino / "imported" / "corpus.records.json").write_text(json.dumps(corpus), "utf-8")
    (destino / "gold.yml").write_text(yaml.safe_dump({"gold": GOLD_AUDITORIA}), "utf-8")
    return destino
```

  Y crear `tests/test_benchmark_run.py`:

```python
"""Preflight y protocolo de celda de `revisia benchmark` (spec 2026-10-18 §10.2, D23)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from conftest import protocolo_benchmark

from revisia.benchmark.run import (
    benchmark_preflight,
    corpus_fingerprint,
    materialize_cell_protocol,
)
from revisia.config import load_protocol
from revisia.schemas.benchmark import BenchmarkPanel

PANEL = BenchmarkPanel.model_validate(
    {
        "name": "panel-demo",
        "replicas": 2,
        "cells": [
            {"name": "fake-a", "provider": "fake", "model": "fake-a"},
            {"name": "fake-b", "provider": "fake", "model": "fake-b"},
        ],
    }
)


def _yaml(proto: Path, **cambios) -> None:
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw.update(cambios)
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), "utf-8")


def _errores(proto: Path) -> list[str]:
    informe = benchmark_preflight(load_protocol(proto), proto, PANEL)
    return [f"[{i.where}] {i.message}" for i in informe.errors]


def test_protocolo_de_benchmark_valido_pasa(tmp_path: Path) -> None:
    assert _errores(protocolo_benchmark(tmp_path)) == []


def _gold(proto: Path, texto: str) -> None:
    (proto / "gold.yml").write_text(texto, encoding="utf-8")


@pytest.mark.parametrize(
    ("cambio", "fragmento"),
    [
        (lambda p: _yaml(p, databases=[]), "necesita declarar la base"),
        (lambda p: _yaml(p, databases=["OpenAlex"]), "no es una base de importación manual"),
        (lambda p: shutil.rmtree(p / "imported"), "sin corpus congelado"),
        (lambda p: _gold(p, "gold:\n  '10.1000/llm-1': true\n"), "las dos clases"),
        (
            lambda p: _gold(p, "gold:\n  '10.1000/llm-1': true\n  'otro:1': false\n"),
            "1 ids del gold no están en el corpus importado (otro:1)",
        ),
        (lambda p: _yaml(p, ensemble=["screening_ta"]), "screening_ta en ensemble"),
    ],
    ids=["sin-bases", "base-con-api", "sin-imported", "una-clase", "gold-fuera", "ensemble"],
)
def test_preflight_de_benchmark_rechaza(tmp_path: Path, cambio, fragmento: str) -> None:
    proto = protocolo_benchmark(tmp_path)
    cambio(proto)
    errores = _errores(proto)
    assert any(fragmento in e for e in errores), errores


def test_huella_del_corpus_cambia_con_el_contenido(tmp_path: Path) -> None:
    proto = protocolo_benchmark(tmp_path)
    antes = corpus_fingerprint(proto / "imported")
    assert antes == corpus_fingerprint(proto / "imported")
    (proto / "imported" / "corpus.records.json").write_text("[]", "utf-8")
    assert corpus_fingerprint(proto / "imported") != antes


def test_protocolo_de_celda_cambia_solo_screening_ta_y_conserva_el_slug(tmp_path: Path) -> None:
    proto = protocolo_benchmark(tmp_path)
    original = load_protocol(proto)
    destino = tmp_path / "protocols" / "fake-b"
    _, celda = materialize_cell_protocol(proto, PANEL.cells[1], original.slug, destino)
    assert celda.slug == original.slug != destino.name
    assert celda.provider_for("screening_ta") == PANEL.cells[1].to_provider_config()
    assert celda.provider_for("extraccion") == original.provider_for("extraccion")
    assert (destino / "imported" / "corpus.records.json").is_file()
    otra_vez = materialize_cell_protocol(proto, PANEL.cells[1], original.slug, destino)[1]
    assert otra_vez == celda
    with pytest.raises(ValueError):
        materialize_cell_protocol(proto, PANEL.cells[0], original.slug, destino)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_benchmark_run.py -v`
Expected: FAIL (`ModuleNotFoundError: revisia.benchmark.run`).

- [ ] **Step 3: Implementar** según Interfaces (docstring del módulo: D6, D23, §10.2; el estudio vive fuera del motor).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider tests/test_benchmark_run.py tests/test_preflight.py tests/test_stop_after.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/benchmark/run.py tests/conftest.py tests/test_benchmark_run.py
git commit -m "feat(benchmark): preflight de corpus congelado y gold, huella del corpus y protocolo por celda (D23)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea F2.5: `run_benchmark`, `source.json`, `benchmark.json` y `benchmark.md`

**Files:**
- Modify: `revisia/benchmark/run.py`.
- Test: `tests/test_benchmark_run.py` (añadir; imports en la cabecera).

**Interfaces:**
- Consumes (importados por nombre en `run.py`, `from revisia.orchestration.pipeline import run_pipeline`, para que el test de la CLI pueda sustituirlo): `run_pipeline(..., stop_after="screening_ta", kind="benchmark")`, `RunContext.create_at`, `RunContext.open` (F2.3); `read_run_info`; `failed_ids` (C); `wilson_interval` (`metrics.py:121`); `BenchmarkResult`, `BenchmarkCellResult`, `BenchmarkProtocolInfo` (PR-0); `read_search_log` y `SearchLogEntry.file_sha256` (`schemas/artifacts.py:201`); `collect_environment`, `prompt_fingerprint`, `protocol_fingerprint` (A, `snapshot.py`); `PreflightError`.
- Produces:
  - `DEFAULT_MAX_RESULTS_BENCHMARK: Final[int] = 50`, el mismo valor que `cli.DEFAULT_MAX_RESULTS` (`cli.py:165`; `run.py` no importa `cli`); un test fija que coinciden.
  - `benchmark_dir(out_root: str | Path, protocol: ReviewProtocol, panel: BenchmarkPanel) -> Path` = `Path(out_root) / f"{protocol.slug}-{panel.name}"` (fila n+13).
  - `class BenchmarkSource(BaseModel)` (`B/source.json`): `panel_sha256: str` (`canonical_sha256(panel.model_dump(mode="json"))`), `protocol_sha256: dict[str, str]` (`protocol_fingerprint(protocol_dir)`), `corpus_sha256: str` (`corpus_fingerprint`), `created_utc: str`.
  - `run_benchmark(protocol: ReviewProtocol, protocol_dir: str | Path, panel: BenchmarkPanel, *, out_root: str | Path = "benchmarks", replicas: int | None = None, max_results: int = DEFAULT_MAX_RESULTS_BENCHMARK, mailto: str | None = None) -> tuple[Path, BenchmarkResult]`:
    1. `benchmark_preflight(protocol, protocol_dir, panel, mailto=mailto)`; con errores, `PreflightError(report)` **antes de crear nada**;
    2. `B = benchmark_dir(...)`; la huella de la fuente es `BenchmarkSource` sin `created_utc`. Si existe `B/source.json` y su huella difiere → `ValueError(f"{B}: ya existe con otro panel, protocolo o corpus ({campos distintos}); usa otro --out o otro name en el panel")` (rc 2; fila n+25). Si no existe, crea `B`, escribe `B/source.json` y `B/panel.yml` (`yaml.safe_dump(panel.model_dump(mode="json"), sort_keys=False, allow_unicode=True)`);
    3. `n = replicas or panel.replicas`; por celda (en orden) y réplica `k = 1..n`: `materialize_cell_protocol(protocol_dir, cell, protocol.slug, B/"protocols"/cell.name)`; `run_dir = B/"runs"/f"{cell.name}-r{k}"`. La corrida se **salta** solo si `read_run_info(run_dir)` existe con `status == "completed"` y `stage == "screening_ta"`; si existe con otro estado, `RunContext.open(run_dir)` y `run_pipeline` reanuda; si no, `RunContext.create_at(run_dir, slug=protocol.slug, timestamp=datetime.now(UTC).strftime("%Y%m%d-%H%M%S"))` (hora UTC real; la carpeta la fija `create_at`). Siempre `run_pipeline(protocolo_de_celda, dir_de_celda, ctx, max_results=max_results, mailto=mailto, stop_after="screening_ta", kind="benchmark")`. `RunInterrupted` y `RunCancelled` se propagan (la CLI responde);
    4. por corrida, con `ctx = RunContext.open(run_dir)`: `BenchmarkCellResult(cell, replica, run_dir="runs/<celda>-r<k>", metrics=ScreeningMetrics de 03_screening/metrics.json tal cual, recall_ci95=wilson_interval(tp, tp + fn), models_used=sorted({f"{m.provider}:{m.model}" for m in ctx.metas if m.outcome == "ok"}), n_calls=len(ctx.metas), n_failed_records=len(failed_ids(decisiones de 03_screening/decisions.json)))`. `n_calls` cuenta **todos los intentos**, también los fallidos (`llm_calls.jsonl` tiene una línea por intento, D14); `benchmark.md` lo dice;
    5. `BenchmarkProtocolInfo` **desde las corridas** (fila n+17): `corpus_sha256 = canonical_sha256(sorted([e.database, e.file_sha256] for e in read_search_log(run_dir).entries if e.db_key == "imported"))` y `gold_sha256 = sha256(bytes de run_dir/00_protocol/gold.yml)`, ambos iguales en todas las corridas (si no, `ValueError` nombrando la primera que difiere); `n_records = len(02_dedup/records.json)` de la primera corrida; `n_gold_positives = sum(gold.values())`; `environment=collect_environment(prompt_templates=prompt_fingerprint())`;
    6. escribe `B/benchmark.json` (`model_dump_json(indent=2)`) y `B/benchmark.md` (`render_benchmark_md`); devuelve `(B, resultado)`.
  - `render_benchmark_md(result: BenchmarkResult, panel_name: str) -> str`: `# Benchmark de cribado · {panel_name}`; `` f"- Protocolo `{slug}` · corpus `{corpus_sha256[:12]}` · {n_records} registros · {n_gold_positives} positivos en el gold" ``; línea fija `"- Corridas `kind: benchmark`: se detienen tras el cribado T/A, sin gates ni entregable; no son revisiones (D23)."`; tabla `| Celda | Réplica | Recall | IC95% Wilson | Lost-evidence | MCC | WMCC | κ | Llamadas | Fallidos |` (`{:.3f}`, `—` si `None`); `## Resumen por celda` con `| Celda | Réplicas | Recall medio | Rango | IC95% Wilson (réplicas agregadas) |`, donde el IC agregado es `wilson_interval(Σtp, Σ(tp + fn))`, seguido de la nota fija `"El IC agregado trata las réplicas como observaciones independientes; repiten el mismo corpus, así que es optimista. La agregación entre corpus está en `revisia benchmark-report`."` (fila n+28); y las notas `"«Llamadas» cuenta todos los intentos, también los fallidos (D14)."` y, si algún `n_failed_records > 0`, `"Los registros en los que la IA falló de forma determinista quedan fuera de la matriz (D9)."`.

- [ ] **Step 1: Tests que fallan.** Añadir a la cabecera de `tests/test_benchmark_run.py`: `import json`, `from conftest import proveedor_auditoria`, `from revisia import cli`, `from revisia.benchmark.run import DEFAULT_MAX_RESULTS_BENCHMARK, benchmark_dir, run_benchmark`, `from revisia.orchestration import pipeline as pipeline_mod`, `from revisia.schemas.benchmark import BenchmarkResult`. Y estos tests:

```python
def test_max_results_por_defecto_es_el_de_la_cli() -> None:
    assert DEFAULT_MAX_RESULTS_BENCHMARK == cli.DEFAULT_MAX_RESULTS


def test_benchmark_demo_dos_celdas_por_dos_replicas(tmp_path: Path, monkeypatch) -> None:
    # Frontera de §10.2: demo importado, ScriptedProvider, 2 celdas × 2 réplicas.
    monkeypatch.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
    proto = protocolo_benchmark(tmp_path)
    protocol = load_protocol(proto)
    carpeta, resultado = run_benchmark(protocol, proto, PANEL, out_root=tmp_path / "b")
    assert carpeta == benchmark_dir(tmp_path / "b", protocol, PANEL)
    leido = BenchmarkResult.model_validate_json((carpeta / "benchmark.json").read_text("utf-8"))
    assert leido == resultado
    assert [(c.cell, c.replica, c.run_dir) for c in leido.cells] == [
        ("fake-a", 1, "runs/fake-a-r1"),
        ("fake-a", 2, "runs/fake-a-r2"),
        ("fake-b", 1, "runs/fake-b-r1"),
        ("fake-b", 2, "runs/fake-b-r2"),
    ]
    # Siete registros importados, uno duplicado por DOI: seis tras el dedup.
    assert (leido.protocol.n_records, leido.protocol.n_gold_positives) == (6, 4)
    for celda in leido.cells:  # relación 31, lado productor
        run = carpeta / celda.run_dir
        info = json.loads((run / "run.json").read_text("utf-8"))
        assert (info["kind"], info["slug"]) == ("benchmark", protocol.slug)
        assert not (run / "decisions_ledger.jsonl").exists()
        assert not (run / "deliverable").exists()
        metricas = json.loads((run / "03_screening" / "metrics.json").read_text("utf-8"))
        assert celda.metrics.model_dump() == metricas
        assert celda.models_used == [f"fake:{celda.cell}"] and celda.n_failed_records == 0
        assert celda.n_calls == len((run / "llm_calls.jsonl").read_text("utf-8").splitlines())
    md = (carpeta / "benchmark.md").read_text(encoding="utf-8")
    assert md.startswith("# Benchmark de cribado · panel-demo")
    assert "## Resumen por celda" in md and "no son revisiones (D23)" in md
    assert "trata las réplicas como observaciones independientes" in md


def test_benchmark_reanudable_solo_salta_las_corridas_completadas(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
    proto = protocolo_benchmark(tmp_path)
    carpeta, _ = run_benchmark(load_protocol(proto), proto, PANEL, out_root=tmp_path / "b")
    # Una corrida interrumpida (run.json no completado) se reanuda aunque tenga métricas.
    run_json = carpeta / "runs" / "fake-b-r2" / "run.json"
    info = json.loads(run_json.read_text("utf-8"))
    run_json.write_text(json.dumps({**info, "status": "interrupted"}), "utf-8")
    llamadas_a = (carpeta / "runs" / "fake-a-r1" / "llm_calls.jsonl").read_bytes()
    run_benchmark(load_protocol(proto), proto, PANEL, out_root=tmp_path / "b")
    assert (carpeta / "runs" / "fake-a-r1" / "llm_calls.jsonl").read_bytes() == llamadas_a
    assert json.loads(run_json.read_text("utf-8"))["status"] == "completed"


@pytest.mark.parametrize("que_cambia", ["panel", "corpus", "gold"])
def test_benchmark_con_otra_fuente_en_la_misma_carpeta_falla(
    tmp_path: Path, monkeypatch, que_cambia: str
) -> None:
    monkeypatch.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
    proto = protocolo_benchmark(tmp_path)
    run_benchmark(load_protocol(proto), proto, PANEL, out_root=tmp_path / "b")
    panel = PANEL
    if que_cambia == "panel":
        panel = PANEL.model_copy(update={"replicas": 3})
    elif que_cambia == "corpus":
        corpus = proto / "imported" / "corpus.records.json"
        registros = json.loads(corpus.read_text("utf-8"))
        sin_duplicado = [r for r in registros if r["record_id"] != "10.1000/llm-1-crossref"]
        corpus.write_text(json.dumps(sin_duplicado), "utf-8")
    else:
        texto = (proto / "gold.yml").read_text(encoding="utf-8")
        (proto / "gold.yml").write_text(texto.replace("true", "false", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="ya existe con otro panel, protocolo o corpus"):
        run_benchmark(load_protocol(proto), proto, panel, out_root=tmp_path / "b")
```

(`n_records == 6`: en `REGISTROS_AUDITORIA` (`conftest.py:75-131`) hay siete registros y `10.1000/llm-1-crossref` comparte DOI con `10.1000/llm-1` (`10.1000/LLM-1` normalizado), así que el dedup deja seis. `test_benchmark_con_otra_fuente…[corpus]` quita justo ese duplicado, que no está en el gold: el preflight sigue limpio y lo que salta es la huella de `source.json`.)

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_benchmark_run.py -v -k "demo or reanudable or fuente or max_results"`
Expected: FAIL (`ImportError: cannot import name 'run_benchmark'`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider tests/test_benchmark_run.py tests/test_benchmark_report.py tests/test_stop_after.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/benchmark/run.py tests/test_benchmark_run.py
git commit -m "feat(benchmark): corridas por celda y réplica, reanudables con huella de la fuente; benchmark.json y benchmark.md (D6, D23)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea F2.6: `revisia benchmark` (`revisia/cli.py`) y frontera por CLI

**Files:**
- Modify: `revisia/cli.py`: `_cmd_benchmark` justo **tras `_cmd_audit`** (antes que `_cmd_benchmark_report` de F₁); subparser `p_benchmark` justo **tras `p_audit`** (antes que `p_benchmark_report`); despacho justo **tras el de `audit`** en `main` (antes que el de `benchmark-report`). G₁ ancla los suyos en `export`.
- Test: `tests/test_cli_benchmark.py` (nuevo).

**Interfaces:**
- Consumes: `load_panel` (PR-0 T13), `run_benchmark` (F2.5), `load_protocol`, `_print_preflight` (`cli.py:81`), `_run_guarded` (`cli.py:268`), `RunInterrupted`, `RunCancelled` (`run_context.py:64,83`).
- Produces: `revisia benchmark <protocol_dir> --panel PANEL [--replicas N] [--out DIR] [--max N] [--mailto EMAIL]` (`--out` por defecto `benchmarks`; `--max` por defecto `DEFAULT_MAX_RESULTS`). `_cmd_benchmark(args) -> int`, con las excepciones en **este orden** (`PreflightError` es un `ValueError`):
  1. `PreflightError` → `_print_preflight(exc.report)`, rc 2;
  2. `RunInterrupted` → en stderr `f"⏸ Benchmark interrumpido en {exc.run_dir} ({exc.error}). {RELANZAR}"`, rc 3;
  3. `RunCancelled` o `KeyboardInterrupt` → en stderr `f"⏹ Benchmark cancelado. {RELANZAR}"`, rc 130;
  4. `ValueError` (panel inválido de `load_panel`, `protocol.yml` inválido, fuente distinta en la carpeta) → `f"error: {exc}"` en stderr, rc 2;
  5. el resto de errores de configuración, delegando en `_run_guarded` (rc 2).
  `RELANZAR = "Vuelve a lanzar la misma orden: las corridas completadas no se repiten."` (nunca `revisia run --resume`, que en una corrida de benchmark da `RunKindMismatchError`; fila n+19). Al terminar, rc 0 e imprime una línea por corrida (`f"{cell}-r{replica}: recall {recall:.3f} · llamadas {n_calls} · fallidos {n}"`, `—` sin recall), las rutas de `benchmark.json` y `benchmark.md` y la sugerencia `f"Agrega corpus con: revisia benchmark-report {carpeta}"`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_cli_benchmark.py`:

```python
"""CLI `revisia benchmark` (spec 2026-10-18 §10.2, §16 criterio de cierre)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from conftest import protocolo_benchmark, proveedor_auditoria

from revisia import cli
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.run_context import RunCancelled, RunInterrupted

PANEL = {
    "name": "panel-demo",
    "replicas": 2,
    "cells": [
        {"name": "fake-a", "provider": "fake", "model": "fake-a"},
        {"name": "fake-b", "provider": "fake", "model": "fake-b"},
    ],
}


def _panel(tmp_path: Path, **cambios) -> str:
    ruta = tmp_path / "panel.yml"
    ruta.write_text(yaml.safe_dump({**PANEL, **cambios}), encoding="utf-8")
    return str(ruta)


def _argv(proto: Path, panel: str, out: Path) -> list[str]:
    return ["benchmark", str(proto), "--panel", panel, "--out", str(out)]


def test_benchmark_y_benchmark_report_de_punta_a_punta(
    tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
    proto = protocolo_benchmark(tmp_path)
    out = tmp_path / "benchmarks"
    assert cli.main(_argv(proto, _panel(tmp_path), out)) == 0
    carpeta = out / f"{proto.name}-panel-demo"
    assert (carpeta / "benchmark.json").is_file() and (carpeta / "benchmark.md").is_file()
    salida = capsys.readouterr().out
    assert "fake-a-r1: recall" in salida and "revisia benchmark-report" in salida
    assert cli.main(["benchmark-report", str(carpeta)]) == 0  # §16: … → pooled/
    assert (carpeta / "pooled" / "meta_analysis.json").is_file()


@pytest.mark.parametrize("caso", ["panel-invalido", "base-con-api"])
def test_benchmark_error_de_configuracion_sale_2(tmp_path: Path, capsys, caso: str) -> None:
    proto = protocolo_benchmark(tmp_path)
    panel = _panel(tmp_path, replicas=0) if caso == "panel-invalido" else _panel(tmp_path)
    if caso == "base-con-api":
        raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
        raw["databases"] = ["OpenAlex"]
        (proto / "protocol.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert cli.main(_argv(proto, panel, tmp_path / "b")) == 2
    err = capsys.readouterr().err
    assert ("panel.yml" if caso == "panel-invalido" else "importación manual") in err
    assert "Traceback" not in err and not (tmp_path / "b").exists()


@pytest.mark.parametrize(
    ("error", "rc", "marca"),
    [
        (RunInterrupted(Path("r"), "screening_ta", "429"), 3, "⏸ Benchmark interrumpido"),
        (RunCancelled(Path("r"), registered=True), 130, "⏹ Benchmark cancelado"),
        (KeyboardInterrupt(), 130, "⏹ Benchmark cancelado"),
    ],
    ids=["interrumpido", "cancelado", "ctrl-c"],
)
def test_benchmark_interrumpido_dice_que_se_relance_la_misma_orden(
    tmp_path: Path, monkeypatch, capsys, error: BaseException, rc: int, marca: str
) -> None:
    def _cae(*_a, **_k):
        raise error

    monkeypatch.setattr("revisia.benchmark.run.run_pipeline", _cae)
    proto = protocolo_benchmark(tmp_path)
    assert cli.main(_argv(proto, _panel(tmp_path), tmp_path / "b")) == rc
    err = capsys.readouterr().err
    assert marca in err and "Vuelve a lanzar la misma orden" in err and "--resume" not in err
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_cli_benchmark.py -v`
Expected: FAIL (`SystemExit: 2`: `invalid choice: 'benchmark'`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa, con la suite**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider tests/test_cli_benchmark.py tests/test_cli_benchmark_report.py -v && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX`
Expected: PASS; XFAIL = los anotados en F2.1.

- [ ] **Step 5: Commit**

```bash
git add revisia/cli.py tests/test_cli_benchmark.py
git commit -m "feat(cli): revisia benchmark (preflight rc 2, interrupción y Ctrl+C con la orden de relanzar)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Supuestos revocables de F₂ (filas propuestas para §19)

A continuación de las de F₁ (`n`…`n+12`):

```
| n+13 | §4.1, §10.2 carpeta del benchmark | `benchmarks/<slug>-<panel.name>/`, sin fecha: volver a lanzar la misma orden la reanuda | Plan PR-F (F₂) |
| n+14 | §10.2 protocolo de celda | `protocol.model_copy` (`cell_protocol`) se materializa en `benchmarks/…/protocols/<celda>/` con `slug:` explícito y `llm.screening_ta` de la celda: la instantánea `00_protocol/` de cada corrida dice el modelo que de verdad cribó, y `--resume` la verifica | Plan PR-F (F₂) |
| n+15 | §10.2 `runs/<celda>-r<k>/` | `RunContext.create_at(run_dir, slug, timestamp)` con la hora UTC real: la carpeta lleva celda y réplica, `run.json.slug` sigue siendo el del protocolo | Plan PR-F (F₂) |
| n+16 | D23, relación 31 | Una corrida `kind: benchmark` termina con `status: completed`, `stage: screening_ta`, sin `decisions_ledger.jsonl`, `review_request.yml`, `deliverable/` ni `manifest.yml`; su entorno está en `run.json` y en `benchmark.json`. Una corrida se salta al relanzar solo si está `completed` en `screening_ta` | Plan PR-F (F₂) |
| n+17 | §4.2 `BenchmarkResult.protocol` | `corpus_sha256` y `gold_sha256` salen de las corridas: `canonical_sha256` de `[database, file_sha256]` de las entradas `imported` de `01_search/log.json` y sha256 de `00_protocol/gold.yml`, iguales en todas (si no, error); `n_records` = registros tras el dedup de la primera corrida | Plan PR-F (F₂, revisión) |
| n+18 | §10.1 figuras | El primer desenlace agregado conserva `assets/forest.png`/`funnel.png`; los siguientes, `forest-<i>.png`/`funnel-<i>.png` (índice, nunca el nombre); se borran las figuras viejas antes de escribir; `document.py` pone el nombre del desenlace en el pie, leído de `meta_analysis.json` | Plan PR-F (F₂) |
| n+19 | §10.2 CLI | `revisia benchmark` interrumpido (rc 3) o cancelado (rc 130) dice «vuelve a lanzar la misma orden», no `revisia run --resume`; reanudar una corrida con otro `kind` es `RunKindMismatchError` (rc 2), lanzado antes de tocar `run.json` | Plan PR-F (F₂) |
| n+20 | §10.1 | `MetaAnalysisResult.n_studies` (`study_id` distintos agregados) sustituye a las propiedades de compatibilidad `k`/`studies` de F₁, que F2.2 retira; alimenta `total_studies_ma` y `metodologia.md` (fila n+9). `render_methods` pierde `included_ids` | Plan PR-F (F₂) |
| n+21 | §16, tests | La corrida de auditoría de `conftest.py` declara los efectos de sus tres incluidos (el caso de D16): su `deliverable` pasa de WARN a PASS y `total_studies_ma` de 4 a 3. La corrida sin registros pasa a no tener `effects.yml`. Único `xfail(strict=True)` de F₂ hasta G₂: `test_pipeline_fake_con_humano_audita_sin_fail` (el demo) | Plan PR-F (F₂) |
| n+22 | §10.1 `meta_analisis.md` | La sección «Efectos excluidos del análisis» solo aparece si hay algo que declarar: sin exclusiones, el Markdown es el que renderiza el auditor de hoy | Plan PR-F (F₂) |
| n+23 | §15 solapes | F₂ toca ficheros de A y B: `snapshot.py` (`kind` en `ensure_snapshot`, `RunKindMismatchError`), `run_context.py` (`create_at`) y `llm/preflight.py` (`until`); solo añade parámetros con default y clases, sin cambiar lo que esas pistas fijaron | Plan PR-F (F₂, revisión) |
| n+24 | §10.2 preflight | Con `stop_after`, el preflight general solo mira las etapas hasta `screening_ta` (`preflight(..., until=)`), y en un benchmark corre por celda antes de crear nada. `databases` vacío es error en un benchmark | Plan PR-F (F₂, revisión) |
| n+25 | §10.2 reanudación | Al crear la carpeta del benchmark se guarda `source.json` (huella del panel, del protocolo con su gold y del corpus de `imported/`); relanzar con otra fuente en la misma carpeta es rc 2 | Plan PR-F (F₂, revisión) |
| n+26 | relación 31 (G₂) | Propuesta: el auditor busca `../../benchmark.json` desde la corrida y comprueba que la referencia y copia sus métricas; si no existe (corrida suelta), WARN, no FAIL | Revisión de F₂ |
| n+27 | §11.2 (G₂) | Propuesta: en una corrida `kind: benchmark`, `environment`, `prompts` y `timing` se aplican como en una revisión; `manifest` queda N/A (no hay manifiesto) | Revisión de F₂ |
| n+28 | §10.2 Wilson | El IC de Wilson de las réplicas agregadas las trata como independientes, y lo declara `benchmark.md` (repiten el mismo corpus: es optimista) | Plan PR-F (F₂, revisión) |
| n+29 | relación 29 | Se define sobre el **multiconjunto** de pares `(study_id, outcome)`, no sobre el conjunto de `study_id`: agregados + excluidos == efectos de la instantánea, contando repeticiones (con `multiple_per_study` un estudio aparece varias veces). `included_without_effect` va ordenado | Plan PR-F (F₂, revisión) |
```

---

### Tarea F2.7: Integración de PR-F (controlador)

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`: `### Added`, `### Changed`, `### Cambios incompatibles`).
- Modify: `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` (§19).

**Interfaces:** ninguna de código. Deja PR-F abierta sobre `feat/ola2-rob-por-herramienta`.

- [ ] **Step 1: CHANGELOG.** En `### Added`:

```
- **Meta-análisis por desenlace, ligado a los incluidos** (spec Ola 2 §10.1; D16): cada efecto
  de `effects.yml` declara su `outcome` y se agrega por desenlace; solo cuentan los de estudios
  incluidos tras el texto completo (los demás van a `08_meta/excluded_effects.json` con los
  incluidos sin efecto); intervalo de predicción (Higgins 2009, t con k − 2 gl, k ≥ 3), Egger solo
  con k ≥ 10 (Sterne 2011), subgrupos con Q entre grupos, detección de duplicados y
  `random_method: HKSJ` opcional. Unidad de análisis: dos efectos del mismo estudio en un
  desenlace son error salvo `multiple_per_study`. Forest y funnel por desenlace (funnel con k ≥ 10).
- **`revisia benchmark`** (D6, D23): un panel de modelos (`panel.yml`) criba un corpus congelado
  (`imported/`) contra `gold.yml`; una corrida `kind: benchmark` por celda y réplica, que se
  detiene tras T/A sin gates ni entregable; `benchmark.json`/`benchmark.md` con recall,
  lost-evidence, MCC, WMCC, κ e IC de Wilson. Reanudable relanzando la orden.
- **`revisia benchmark-report`**: agrega uno o más `benchmark.json` en `logit(recall)` por celda,
  con la unidad de análisis por corpus (`--replicas-as-effects`, exploratorio).
```

En `### Changed`: `08_meta/meta_analysis.json` es `MetaAnalysisResult` v2 (`outcomes[]`, `not_pooled`, `excluded`, `random_method`) y existe siempre que haya `effects.yml`; `effects_metafor.csv` gana las columnas `outcome` y `subgroup`; `metodologia.md` declara el filtrado por incluidos; `total_studies_ma` cuenta estudios distintos; `run.json` lleva `kind`.

En `### Cambios incompatibles`: un `effects.yml` sin `outcome` es rc 2 con el mensaje de migración; dos efectos del mismo estudio en un desenlace, rc 2 sin `multiple_per_study`; cada desenlace necesita k ≥ 2 al cargar; Egger ya no se calcula con k < 10 y el funnel no se dibuja; el demo deja de producir `funnel.png`; `render_methods` pierde `included_ids`.

- [ ] **Step 2: §19 del spec.** Añadir **a continuación de la última fila existente**, con numeración consecutiva, las filas `n`…`n+12` de «Supuestos revocables de F₁» (la `n+8` según lo que haya decidido el arquitecto en el Step 0 de la Tarea 8), las `n+13`…`n+29` de F₂ y las que haya producido la revisión por tarea. Si el coordinador ya registró alguna, no se repite.

- [ ] **Step 3: Commit de documentación.**

```bash
git add CHANGELOG.md docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md
git commit -m "docs: CHANGELOG y desviaciones (§19) de PR-F" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Verificación completa, en las tres versiones.**

```bash
uv run black . && uv run ruff check --fix .
for PY in 3.11 3.12 3.13; do
  uv run --python "$PY" --extra dev --extra search --extra meta \
    pytest -p no:cacheprovider -q -n auto -m "not cronometrado" -rxX || exit 1
  uv run --python "$PY" --extra dev --extra search --extra meta \
    pytest -p no:cacheprovider -q -m cronometrado || exit 1
done
uv run --extra dev --extra search --extra meta \
  pytest -p no:cacheprovider -q -n auto --cov --cov-report=term -m "not cronometrado"
uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check
git diff --stat origin/feat/ola2-rob-por-herramienta -- revisia/audit | tail -1
grep -rnE "(meta_result|res|meta|result|calculo)\.(k|studies)\b|from test_" revisia tests
```

Expected:
- Verde en las tres versiones; XFAIL = los estrictos de A, C, D y E más `test_pipeline_fake_con_humano_audita_sin_fail`; ningún XPASS.
- Cobertura ≥ 90 %.
- Lint limpio.
- **Ningún cambio en `revisia/audit/`**: la penúltima orden no imprime nada.
- El último `grep` no devuelve nada (salvo nombres de variable que sean un `OutcomeMeta`; revisarlos).
- De punta a punta (§16): `revisia benchmark` sobre el demo importado con dos celdas fake → `benchmark.json`; `benchmark-report` → `pooled/` (lo cubre `tests/test_cli_benchmark.py`).
- Anota el recuento y la lista de XFAIL.

- [ ] **Step 5: Publicar y abrir la PR** (base `feat/ola2-rob-por-herramienta`, §15).

```bash
git push -u origin feat/ola2-meta-benchmark
gh pr create --base feat/ola2-rob-por-herramienta --head feat/ola2-meta-benchmark --title "Ola 2 · PR-F: meta-análisis por desenlace ligado a los incluidos, revisia benchmark y benchmark-report" --body "$(cat <<'EOF'
## Qué cierra

C3 en la parte del benchmark, D6, D16 y D23 (spec `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`, §10).

## Qué cambia

- `meta_analyze` v2 por desenlace: intervalo de predicción, Egger solo con k ≥ 10, subgrupos con Q entre grupos, duplicados y HKSJ opcional, con la t de Student en Python puro (los números no dependen de scipy).
- `effects.yml` v2: `outcome` obligatorio (rc 2 con mensaje de migración), `multiple_per_study`, `random_method`, unidad de análisis.
- El pipeline agrega solo los efectos de los incluidos y escribe `08_meta/excluded_effects.json`; `metodologia.md` y `meta_analisis.md` lo declaran; figuras por desenlace con su nombre.
- `run_pipeline(..., stop_after="screening_ta", kind="benchmark")`, preflight hasta T/A; `revisia benchmark` (con `source.json`) y `revisia benchmark-report`.

## Para PR-G₂

- Relación 29 (multiconjunto `(study_id, outcome)`): `meta_analysis.json` == `meta_analyze(efectos ∩ incluidos, measure, random_method=…)` con `excluded = len(excluded_effects.excluded)`; agregados (`outcomes[].studies` y `not_pooled[].study_ids`, con su desenlace) + excluidos == efectos de la instantánea; `included_without_effect` == `sorted(incluidos − estudios con efecto)`; sin `multiple_per_study.allowed`, `unit_of_analysis_violations == []`; `prediction_interval is None ⇔ k < 3`; `egger is None ⇔ k < 10` o `egger_note` de precisión constante; `total_studies_ma == n_studies`; `reason == "unit_of_analysis"` es FAIL.
- Relación 31: `run.json.kind == "benchmark"` ⇒ sin `decisions_ledger.jsonl`, `review_request.yml`, `deliverable/` ni `manifest.yml`; con `03_screening/metrics.json`; `../../benchmark.json` (si existe) referencia la corrida y copia su `metrics.json` tal cual.
- `derive_state`: `kind: benchmark` → `status: benchmark`, `reached` hasta `screening_ta`.
- Tests del auditor que edita F2.1 (valores nuevos, no `xfail`): `tests/test_auditor_meta_y_estados.py:112`, `tests/test_audit.py:33-34`, `tests/test_audit_flujo.py:1041-1048`. `tests/conftest.py`: `protocolo_auditoria` con `EFECTOS_AUDITORIA`, `protocolo_auditoria_sin_efectos` para la corrida sin registros.
- XFAIL estricto que G₂ vuelve verde (relación 29): `tests/test_pipeline_fake.py::test_pipeline_fake_con_humano_audita_sin_fail`.

## Cambios incompatibles

Ver CHANGELOG.

## Verificación

<recuento y XFAIL de la Tarea F2.7, Step 4>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: `gh` imprime la URL de la PR; `gh pr view --json baseRefName -q .baseRefName` da `feat/ola2-rob-por-herramienta`.

---

### Interfaces para G₂ (relaciones 29 y 31)

```python
# revisia/meta_analysis.py (además del bloque de F₁; k y studies ya no existen)
class MetaAnalysisResult(BaseModel):
    ...
    @property
    def n_studies(self) -> int: ...        # study_id distintos en outcomes[].studies
def unit_of_analysis_violations(effects) -> list[UnitViolation]: ...
def meta_analyze(effects, measure, *, random_method="DL") -> MetaAnalysisResult: ...

# revisia/orchestration/pipeline.py
def _meta_analysis(run, included_ids: Sequence[str]
                   ) -> tuple[MetaAnalysisResult | None, ExcludedEffectsFile | None, str]: ...
def run_pipeline(protocol, protocol_dir, run_ctx, *, ...,
                 stop_after: Literal["screening_ta"] | None = None,
                 kind: RunKind = "review") -> PipelineResult: ...
# _run_stages: … gate rob → apply_domain_edits → _meta_analysis(run, ids de los incluidos)
#   → _synthesize_and_verify → _write_deliverables(..., meta_exclusions=…) → gate reporte.
# Con stop_after: tras _screen_ta, finish("completed", "screening_ta") y fin, sin gate.

# revisia/orchestration/snapshot.py
class RunKindMismatchError(ProtocolMismatchError): ...
def ensure_snapshot(protocol_dir, run_ctx, *, max_results, mailto, kind: RunKind = "review"): ...

# revisia/orchestration/run_context.py
class RunContext:
    @classmethod
    def create_at(cls, run_dir, *, slug: str, timestamp: str) -> RunContext: ...

# revisia/llm/preflight.py
def preflight(protocol, protocol_dir, *, context, ...,
              until: str | None = None) -> PreflightReport: ...

# revisia/exports/forest.py, methods.py
def render_forest_markdown(result, *, display="raw",
                           exclusions: ExcludedEffectsFile | None = None) -> str: ...
def render_methods(*, ..., meta_result=None, meta_exclusions=None, multiple_per_study=None,
                   ...) -> str: ...                     # sin included_ids

# revisia/benchmark/run.py
def corpus_fingerprint(imported_dir: Path) -> str: ...
def cell_protocol(protocol, cell) -> ReviewProtocol: ...
def benchmark_preflight(protocol, protocol_dir, panel, *, mailto=None, env=None,
                        find_spec=None, which=None) -> PreflightReport: ...
def materialize_cell_protocol(protocol_dir, cell, slug, dest) -> tuple[Path, ReviewProtocol]: ...
def benchmark_dir(out_root, protocol, panel) -> Path: ...
class BenchmarkSource(BaseModel): ...                  # source.json
def run_benchmark(protocol, protocol_dir, panel, *, out_root="benchmarks", replicas=None,
                  max_results=DEFAULT_MAX_RESULTS_BENCHMARK, mailto=None
                  ) -> tuple[Path, BenchmarkResult]: ...
def render_benchmark_md(result: BenchmarkResult, panel_name: str) -> str: ...
```

Para G₂, por relación:
- **29**: recalcular con un `_meta_analysis`-equivalente sin escribir: `kept`/`excluded`/`included_without_effect` desde `00_protocol/effects.yml` y los incluidos efectivos (`04_fulltext/decisions.json`, `final_label == "include"`); comparar `meta_analysis.json` campo a campo como hoy (`_meta_distinto`, ignorando `p_value`/`p_method`) y `excluded_effects.json` entero; `meta_analisis.md` == `render_forest_markdown(calculo, display=…, exclusions=…)`; `total_studies_ma`/`total_reports_ma` == `n_studies`; el WARN `_meta_sin_incluidos` deja de tener sentido (el pipeline ya filtra) y pasa a WARN de `multiple_per_study.allowed` y de `duplicates` (§11.2).
- **31**: con `run.json.kind == "benchmark"`, mensaje de D23 en `provenance` y N/A sin cascada en el resto (§11.2), con lo que comprueba la tabla de arriba.
- **`derive_state`**: `kind: benchmark` → `status: benchmark`, `reached` hasta `screening_ta`; `publishable` es `False`.
- **Tests**: el XFAIL de F2.1 vuelve a verde; corridas para los checks en `tests/test_benchmark_run.py` (`run_benchmark` con `proveedor_auditoria`) y `tests/test_meta_pipeline.py` (`_con_efectos`).

**CAMBIO tras revisión** (después de que el redactor de G₂ consumiera este bloque):
1. Relación 29 sobre el **multiconjunto** `(study_id, outcome)`: agregados + excluidos == efectos de la instantánea contando repeticiones, no unión de conjuntos de ids (fila n+29).
2. `included_without_effect` va **ordenado** (`sorted`), no en el orden de los incluidos.
3. `k` y `studies` se retiran en F2.2 (antes decía F2.1); `render_methods` pierde `included_ids`.
4. `BenchmarkResult.protocol.corpus_sha256` y `gold_sha256` salen de las corridas (`01_search/log.json` y `00_protocol/gold.yml`), no de la carpeta del protocolo; la huella de la fuente va aparte, en `benchmarks/…/source.json` (filas n+17 y n+25).
5. Relación 31: `benchmark.json` se busca en `../../benchmark.json`; sin él, WARN (propuesta, fila n+26). `environment`, `prompts` y `timing` se aplican a una corrida de benchmark y `manifest` es N/A (propuesta, fila n+27).
6. `preflight(..., until=)` nuevo (fila n+24); `RunKindMismatchError` se lanza en `run_pipeline` antes de tocar `run.json`, no en `ensure_snapshot`.
7. La corrida de benchmark se salta al relanzar solo con `status == completed` y `stage == screening_ta`; `n_calls` cuenta todos los intentos.

### Self-review del plan (F₁ + F₂)

- **Cobertura de §10:** 10.1 completo: `meta_analyze` v2 (F₁ T3–T6), `_meta_analysis(run, included_ids)` con `excluded_effects.json` e `included_without_effect` (F2.1), declaraciones en `meta_analisis.md` y `metodologia.md` (F2.2), k < 2 tras filtrar con `outcomes: []` (F2.1, F2.2), `EffectsFile` v2 (F₁ T7), CSV de metafor y figuras por desenlace (F₁ T3, F2.2). 10.2 completo: CLI `benchmark` (F2.6) y `benchmark-report` (F₁ T9); preflight de corpus congelado, `databases` no vacío y manual, gold de dos clases con ids en el corpus y `screening_ta` sin ensemble (F2.4); `kind: benchmark`, `stop_after`, preflight hasta T/A, `metrics.json`, reanudable con huella de la fuente, `n_failed_records` (F2.3, F2.5); `benchmark.json`/`benchmark.md` con Wilson (F2.5); `pooled/` con la advertencia de unidad de análisis (F₁ T8). El check del auditor para `kind: benchmark` es de G₂ (contrato arriba). Tests de §10 con su tarea: C3 (F₁ T7), no incluido → `excluded_effects` y k = 1 tras filtrar (F2.1, F2.2), PI de `dat.bcg` (F₁ T4), Egger con k = 9 (F₁ T3), HKSJ (F₁ T5), demo importado 2 × 2 (F2.5 y F2.6), `benchmark-report` sobre dos benchmarks (F₁ T8). Relaciones 29 y 31 desde el lado productor (F2.1, F2.3, F2.5) y su contrato para G₂.
- **Firmas verificadas:** las de F₁ contra `c1af7c3` (Self-review de F₁). Las de F₂ contra el árbol (`pipeline.py:153-167,224-345,447-505,885-898,1073-1201,1234-1509`; `snapshot.py:106-177`; `run_context.py:64-145`; `llm/preflight.py:92-133,211,304-410,479-522`; `agents/search_backends.py:210-245`; `schemas/artifacts.py:181-201`; `config.py:277-299`; `cli.py:61-93,165,268-304,527-548,609-797`; `exports/document.py:208-211,471-478`; `exports/methods.py:40-63`; `metrics.py:121`; `tests/conftest.py:47,75-152,206-345`; `tests/test_audit_aritmetica_ola1.py:905-908,1089,1435`; `tests/test_audit_flujo.py:1041-1060`; `tests/test_pipeline_fake.py:390-402`; `tests/test_entregable_honesto.py:69-120`; `tests/test_meta_analysis.py:38`) y contra los bloques «Estado en que … deja el pipeline» de C, D y E, las Interfaces de A (`ensure_snapshot`, `collect_environment`, `prompt_fingerprint`) y B (Tarea 7). `RunInfo.kind` existe desde PR-0 y nadie lo escribía antes de F2.3.
- **Consistencia de tipos:** `MetaAnalysisResult` (F₁ T3) → `n_studies` (F2.1) → sin `k`/`studies` (F2.2); `ExcludedEffectsFile` (PR-0) → F2.1, F2.2; `run_pipeline(stop_after, kind)`, `RunContext.create_at`, `preflight(until=)` (F2.3) → F2.4, F2.5; `benchmark_preflight`/`cell_protocol`/`materialize_cell_protocol` (F2.4) → F2.5; `run_benchmark` (F2.5) → F2.6. Ayudantes de test: `escribir_benchmark` en `tests/fakes.py` (F₁ T8) y `protocolo_benchmark` en `tests/conftest.py` (F2.4); ningún test importa otro test.
- **Lo que queda abierto a propósito:** la fila n+8 (subgrupos del benchmark) espera el OK del arquitecto (F₁ T8, Step 0); las filas n+26 y n+27 son propuestas para G₂.
- **Proporción:** los bloques de código son tests con los valores del spec y del `conftest.py` real, más el resumen de firmas para G₂; los cuerpos de función solo se describen donde el spec no los fija (filtrado, materialización, reanudación, huellas).
