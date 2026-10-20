# Ola 2 · PR-0 `feat/ola2-contratos` (contratos entre pistas) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poner en `main` el contrato que las ocho pistas de la Ola 2 importan (modelos v2 de artefactos, errores de llamada, sink de metas, acciones del ledger, modelos de decisión por campo y dominio, especificaciones oficiales de RoB como datos, `normalize_doi`, dobles de prueba y la sonda del CLI `claude`) **sin cambiar el comportamiento del motor**.

**Architecture:** Todo es aditivo o con defaults que reproducen la v1: los modelos v2 validan los artefactos que la 0.8 escribe hoy, las excepciones nuevas son subclases de `RuntimeError`, el sink no tiene consumidores, las acciones nuevas del ledger no las emite nadie todavía y las seis especificaciones de RoB son YAML de paquete con un cargador puro. Las únicas rupturas son las que D12 y D5 declaran: `ARTIFACT_SCHEMA_VERSION` pasa a 2 y `RoBTool` pierde `GRADE` (un `protocol.yml` con `rob_tool: GRADE` deja de cargar).

**Tech Stack:** Python 3.13 (suite también en 3.11/3.12 con venv desechable hasta PR-H), Pydantic v2, PyYAML, pytest, ruff + black (línea 100), uv, gh. La sonda del CLI es stdlib puro y corre con el Python 3.11 del sistema del arquitecto.

**Spec:** `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`. Este plan implementa §4 (contratos; §4.4 es la lista de entregables) y la parte de §15 que arranca la ola. Lee §3 (D1–D27) antes de empezar; no se reabren. El plan hermano `2026-10-18-ola2-prh-ci-tests.md` (PR-H) se escribe contra las firmas de los bloques **Interfaces** de aquí; los planes de PR-A a PR-I se escribirán después, contra lo mismo.

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes y commits **en español**, con el tono del repo. Las docstrings explican el porqué y citan la auditoría («auditoría 2026-09-03, A6») o la decisión del spec («D14»).
- Estilo: `ruff` (reglas `E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100), ambos limpios en cada commit. `from __future__ import annotations` al inicio de todo módulo nuevo, también en `tests/` y en `scripts/`.
- **Sin cambio de comportamiento**: ningún test existente se borra. Los que cambian de expectativa se listan en su tarea con el cambio exacto (hay cinco: `tests/test_artifacts.py:160`, `tests/test_hitl.py:224-228`, `tests/test_hitl.py:256`, `tests/test_contratos_provenance.py::test_constantes_del_ledger`, `tests/test_rob.py::test_cada_herramienta_tiene_dominios`).
- Tests offline y deterministas; ninguno invoca `claude`, APIs ni WeasyPrint. La sonda del CLI se prueba con `subprocess.run` sustituido.
- Línea base: **2 103 tests recogidos, en verde** (`main` @ `c1af7c3`, v0.8.0; `uv sync --extra dev --extra search --extra meta`). Cada tarea termina con la suite entera en verde.
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"` y después `uv run pytest -p no:cacheprovider -m cronometrado`; lint, `uv run ruff check . && uv run ruff format --check . && uv run black --check .`.
- Commits pequeños, al menos uno por tarea, en español con prefijo convencional (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), terminados con la línea `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Los implementadores no tocan** `CHANGELOG.md`, `README.md`, `AGENTS.md`, `docs/auditoria/` ni el spec: los actualiza el controlador en la Tarea 17 con el texto exacto que da esa tarea (§15).
- No cambiar `revisia.__version__` ni `pyproject.toml` (lo primero es de 0.9.0, D7; lo segundo es de PR-H). `requires-python` sigue en `>= 3.13` durante esta PR: la comprobación en 3.11/3.12 va con venv desechable (Tarea 17).
- No tocar `runs/` ni `protocols/<slug>/` distintos de `_TEMPLATE`.
- Convenciones de la Ola 1 que siguen (§4): `canonical_json`, horas ISO-8601 UTC (`utc_now_iso`), rutas relativas con `/`, ningún `record_id` como nombre de fichero, claves de registro entre comillas en YAML.
- `tests/` no es un paquete: los dobles se importan como `from fakes import …` (pytest pone `tests/` en `sys.path`); ruff los clasifica como terceros (bloque de terceros, tras `import pytest`).
- Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base (§15).

## Review Focus

Entradas que el spec implica pero que ninguna tarea probaría sin estas líneas; cada una tiene su test añadido a la tarea dueña:

1. **Una línea v1 de `llm_calls.jsonl` o de un diario** (sin `schema_version`, `attempt`, `outcome`, `error`) debe seguir validando como `LLMCall`/`JournalEntry` v2 con los defaults de la v1: si no, `RunContext.open` y `StageJournal` rompen toda corrida 0.8 al reanudar (D12 dice «no reanudable» pero con rc 2 y mensaje, no con un `ValidationError` crudo). → Tareas 3 y 5.
2. **Un `decision.yml` con `fields:` o `domains:` en un gate de cribado**, o con `text_file` en cualquier gate, debe dar `DecisionFileError` con un mensaje que diga que esa forma no vale aquí todavía, no un `AttributeError` al leer `.label`. → Tarea 7.
3. **Un YAML de herramienta con un dominio repetido, un ítem crítico que no existe o una escala vacía** debe fallar al cargar, no al evaluar el primer estudio real (riesgo 5 del spec). → Tarea 10.
4. **Un DOI con prefijo `doi:`, URL-encoded (`%2F`), en mayúsculas, con `)` o `.` final, o que no empieza por `10.`**: `normalize_doi` devuelve la forma canónica o `None`, nunca una cadena a medias (A4). → Tarea 14.
5. **La sonda del CLI con un `claude` que no existe, que devuelve JSON inválido o cuyo `--help` no anuncia `--safe-mode`** debe escribir el informe igual (rc 0) y dejar constancia: la sonda existe para registrar lo que hay, no para fallar. → Tarea 16.

---

## Topología de ejecución (subagentes)

Esta PR es la raíz de la cadena de §15: `main ← PR-0 ← PR-H ← PR-A ← PR-B ← PR-C ← PR-D ← PR-E ← PR-F ← PR-G ← PR-I`. Se ejecuta en secuencia, en un solo worktree (`C:\revisia-wt\0`, rama `feat/ola2-contratos` creada desde `main`), tarea a tarea. Al cerrar (Tarea 17) el controlador crea los worktrees de las pistas que arrancan desde PR-0 en paralelo: H, A, B, E₁, F₁ y G₁ (§15).

Orden de las tareas y por qué: primero lo que todo lo demás importa (errores y `prompt_template` en `llm/base.py`, `RunMeta` v2, el sink), después los contratos de artefactos (`artifacts.py`, ledger, `hitl.py`), después los modelos por etapa (extracción, RoB y sus especificaciones, verificación, efectos, benchmark), después lo independiente (`normalize_doi`, dobles de prueba, sonda) y por último la integración.

| Tarea | Fichero(s) | Depende de |
|---|---|---|
| 1 | rama, spec y planes | — |
| 2 | `revisia/llm/base.py` | 1 |
| 3 | `revisia/provenance/runmeta.py` | 1 |
| 4 | `revisia/provenance/sink.py` | 3 |
| 5 | `revisia/schemas/artifacts.py` | 3 |
| 6 | `revisia/provenance/ledger.py` | 5 |
| 7 | `revisia/orchestration/hitl.py` | 5 |
| 8 | `revisia/schemas/extraction.py` | 5 |
| 9 | `revisia/schemas/rob.py`, `revisia/agents/rob.py` (solo `TOOL_DOMAINS`), `protocols/_TEMPLATE/protocol.yml` (comentario) | 5 |
| 10 | `revisia/schemas/rob_tools.py`, `revisia/rob/tools/*.yml` | 9 |
| 11 | `revisia/schemas/verification.py` | 5 |
| 12 | `revisia/schemas/effects.py`, `revisia/meta_analysis.py` (solo `schema_version`) | 5 |
| 13 | `revisia/schemas/benchmark.py` | 5, 10 |
| 14 | `revisia/ingest/doi.py` | 1 |
| 15 | `tests/fakes.py` | 2 |
| 16 | `scripts/sonda_claude_cli.py` | 1 |
| 17 | integración (controlador) | todas |

**Ciclo por tarea (§16):** implementador (subagente nuevo, TDD estricto: test rojo → código mínimo → verde → lint → commit) → revisor (subagente nuevo: primero cumplimiento del spec y de este plan, después calidad) → correcciones → siguiente tarea. Desviaciones descubiertas en revisión se corrigen y se anotan en §19 del spec (Tarea 17), no se consultan, salvo que cambien una decisión D1–D6. El controlador ejecuta de punta a punta sin pedir confirmación entre tareas. **El merge lo decide el arquitecto.**

**Entorno del worktree:** el primer paso es `uv sync --extra dev --extra search --extra meta` (pytest, pytest-xdist, ruff, black; httpx y pypdf para los tests que los piden; scipy para el meta-análisis). Necesita red una vez, o la caché de uv.

---

## Tarea 1: Rama, spec y planes en la PR (controlador)

**Files:**
- Create: worktree `C:\revisia-wt\0`, rama `feat/ola2-contratos`.
- Traer: `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` (rama `claude/wizardly-moser-5daa81`, commits `57278d5..24d26d6`, aprobado el 2026-10-18) y los dos planes (`docs/superpowers/plans/2026-10-18-ola2-pr0-contratos.md`, `…-prh-ci-tests.md`, commiteados en la rama `claude/peaceful-rubin-464b82`).

**Interfaces:** ninguna de código.

- [ ] **Step 1: Crear la rama y el worktree desde `main`.**

```bash
git -C C:/revisia fetch origin
git -C C:/revisia worktree add C:/revisia-wt/0 -b feat/ola2-contratos origin/main
cd C:/revisia-wt/0
```

Expected: `git log --oneline -1` muestra `c1af7c3`.

- [ ] **Step 2: Traer el spec aprobado** (la rama `claude/wizardly-moser-5daa81` es `main` más cuatro commits de documentación, así que el *fast-forward* es limpio).

```bash
git merge --ff-only claude/wizardly-moser-5daa81
```

Expected: `git log --oneline -1` muestra `24d26d6 docs(spec): Ola 2 aprobada por el arquitecto (2026-10-18)` y existe `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`.

- [ ] **Step 3: Traer los planes** (el commit `docs(plan): …` de la rama `claude/peaceful-rubin-464b82` que añade los dos ficheros).

```bash
HASH="$(git log --format=%H -1 claude/peaceful-rubin-464b82 -- docs/superpowers/plans/2026-10-18-ola2-pr0-contratos.md)"
git cherry-pick "$HASH"
```

Expected: existen `docs/superpowers/plans/2026-10-18-ola2-pr0-contratos.md` y `docs/superpowers/plans/2026-10-18-ola2-prh-ci-tests.md`.

- [ ] **Step 4: Entorno y línea base.**

```bash
uv sync --extra dev --extra search --extra meta
uv run pytest -p no:cacheprovider --collect-only -q | tail -1
uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado
```

Expected: `2103 tests collected`; suite en verde.

---

## Tarea 2: Errores de llamada y `prompt_template` (`revisia/llm/base.py`)

**Files:**
- Modify: `revisia/llm/base.py` (`LLMRequest`, línea 26; nuevas clases tras `SchemaT`).
- Test: `tests/test_contratos_llm.py` (nuevo).

**Interfaces:**
- Consumes: nada nuevo.
- Produces (D9, §4.4):
  - `class TransientCallError(RuntimeError)`: el intento falló por algo que reanudar puede arreglar (429, 5xx, red, timeout).
  - `class DeterministicCallError(RuntimeError)`: el intento falló por algo que repetir no arregla (4xx distinto de 408/429, bloqueo de contenido, salida que no valida tras los reintentos). Constructor: `(message: str, *, attempts: int = 1)`; atributo `attempts`.
  - `LLMRequest.prompt_template: str | None = None` (último campo del dataclass; `"extraccion/v2.md"` cuando el agente renderiza una plantilla versionada; lo rellenan los agentes en PR-A).

- [ ] **Step 1: Test que falla** — crear `tests/test_contratos_llm.py`:

```python
"""Errores de llamada y `prompt_template` del contrato LLM (spec 2026-10-18 §4.4, D9)."""

from __future__ import annotations

import dataclasses

import pytest

from revisia.llm.base import DeterministicCallError, LLMRequest, TransientCallError


def test_los_errores_de_llamada_son_runtime_error_y_distintos_entre_si() -> None:
    # Subclases de RuntimeError: el código de la Ola 1 que atrapa RuntimeError (rc 3) sigue
    # atrapándolos; distintos entre sí para que D9 pueda separar «reanudar» de «al humano».
    assert issubclass(TransientCallError, RuntimeError)
    assert issubclass(DeterministicCallError, RuntimeError)
    assert not issubclass(DeterministicCallError, TransientCallError)
    assert not issubclass(TransientCallError, DeterministicCallError)


def test_deterministic_call_error_lleva_los_intentos() -> None:
    exc = DeterministicCallError("salida inválida", attempts=3)
    assert str(exc) == "salida inválida"
    assert exc.attempts == 3
    assert DeterministicCallError("400").attempts == 1


def test_llm_request_admite_prompt_template_y_sigue_siendo_inmutable() -> None:
    req = LLMRequest(prompt="p")
    assert req.prompt_template is None
    con = dataclasses.replace(req, prompt_template="extraccion/v2.md")
    assert con.prompt_template == "extraccion/v2.md"
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.prompt_template = "x"  # type: ignore[misc]
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_llm.py -v`
Expected: FAIL con `ImportError: cannot import name 'DeterministicCallError'`.

- [ ] **Step 3: Implementar** en `revisia/llm/base.py`: las dos excepciones (docstring con D9 y la regla «transitorio se reanuda; determinista pasa al humano») y el campo `prompt_template: str | None = None` al final de `LLMRequest` (docstring: nombre con versión de la plantilla renderizada, el que viaja a `RunMeta.prompt_template`, A7).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_llm.py tests/test_llm_registry.py tests/test_fakes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/llm/base.py tests/test_contratos_llm.py
git commit -m "feat(llm): TransientCallError, DeterministicCallError y LLMRequest.prompt_template (D9, A7)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 3: `RunMeta` v2 y `Outcome` (`revisia/provenance/runmeta.py`)

**Files:**
- Modify: `revisia/provenance/runmeta.py` (`RunMeta`, línea 56).
- Test: `tests/test_contratos_provenance.py` (añadir una sección al final).

**Interfaces:**
- Consumes: nada nuevo.
- Produces (§4.2 «RunMeta v2»; todos los campos v1 se conservan con su significado, «lo pedido»):
  - `RUNMETA_SCHEMA_VERSION: int = 2` (vive aquí porque `schemas.artifacts` importa este módulo y no al revés; la Tarea 5 fija que es igual a `ARTIFACT_SCHEMA_VERSION`).
  - `Outcome = Literal["ok", "invalid_output", "transient_error", "deterministic_error"]`; `ModelSource = Literal["config", "backend", "callback"]`.
  - `RunMeta` gana, con estos defaults (reproducen la v1: una línea v1 valida sin tocarla): `schema_version: int = RUNMETA_SCHEMA_VERSION`, `seed_applied: int | None = None`, `temperature_applied: float | None = None`, `top_p_applied: float | None = None`, `schema_sha256: str | None = None`, `prompt_template: str | None = None`, `prompt_template_sha256: str | None = None`, `attempt: int = Field(default=1, ge=1)`, `outcome: Outcome = "ok"`, `effort: str | None = None`, `backend_version: str | None = None`, `latency_ms: int | None = Field(default=None, ge=0)`, `cost_usd: float | None = Field(default=None, ge=0.0)`, `model_source: ModelSource = "config"`.
  - `prompt_sha256` cambia solo de **significado** (docstring): hash del texto enviado, con el schema inyectado y el sufijo de reintento cuando van en el texto (A7); lo hacen cumplir los proveedores en PR-A. `response_sha256` sigue obligatorio: un intento fallido hashea el texto crudo recibido (o `""`), lo fija PR-A.
  - `LLMCall` (artifacts.py) hereda todo sin cambios.

- [ ] **Step 1: Test que falla** — añadir al final de `tests/test_contratos_provenance.py`:

```python
# ── RunMeta v2 (spec 2026-10-18 §4.2; A6, A7, D12, D14) ─────────────────


def _meta_v1() -> dict:
    """Una línea de llm_calls.jsonl escrita por la 0.8: sin ningún campo de la v2."""
    return {
        "provider": "gemini",
        "model": "gemini-3.5-flash-lite",
        "temperature": 0.0,
        "prompt_sha256": "a" * 64,
        "response_sha256": "b" * 64,
        "timestamp_utc": "2026-10-01T00:00:00+00:00",
    }


def test_runmeta_v1_valida_con_los_defaults_de_la_v2() -> None:
    meta = RunMeta.model_validate(_meta_v1())
    assert meta.schema_version == RUNMETA_SCHEMA_VERSION == 2
    assert (meta.seed_applied, meta.temperature_applied, meta.top_p_applied) == (None, None, None)
    assert (meta.schema_sha256, meta.prompt_template, meta.prompt_template_sha256) == (
        None,
        None,
        None,
    )
    assert (meta.attempt, meta.outcome, meta.model_source) == (1, "ok", "config")
    assert (meta.effort, meta.backend_version, meta.latency_ms, meta.cost_usd) == (
        None,
        None,
        None,
        None,
    )
    assert meta.deterministic is False


def test_runmeta_v2_acota_intento_resultado_y_origen_del_modelo() -> None:
    with pytest.raises(ValidationError):
        RunMeta.model_validate({**_meta_v1(), "attempt": 0})
    with pytest.raises(ValidationError):
        RunMeta.model_validate({**_meta_v1(), "outcome": "error"})
    with pytest.raises(ValidationError):
        RunMeta.model_validate({**_meta_v1(), "model_source": "guess"})
    with pytest.raises(ValidationError):
        RunMeta.model_validate({**_meta_v1(), "latency_ms": -1})
    assert set(get_args(Outcome)) == {"ok", "invalid_output", "transient_error", "deterministic_error"}
    assert set(get_args(ModelSource)) == {"config", "backend", "callback"}


def test_runmeta_v2_un_intento_fallido_se_serializa_completo() -> None:
    fallido = RunMeta.model_validate(
        {**_meta_v1(), "attempt": 2, "outcome": "invalid_output", "model_source": "backend"}
    )
    volcado = fallido.model_dump(mode="json")
    assert volcado["attempt"] == 2 and volcado["outcome"] == "invalid_output"
    assert RunMeta.model_validate(volcado) == fallido
```

Añadir a los imports del fichero: `from pydantic import ValidationError` y, de `revisia.provenance.runmeta`, `RUNMETA_SCHEMA_VERSION, ModelSource, Outcome, RunMeta`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_provenance.py -v -k runmeta`
Expected: FAIL con `ImportError: cannot import name 'RUNMETA_SCHEMA_VERSION'`.

- [ ] **Step 3: Implementar** en `revisia/provenance/runmeta.py`: la constante, los dos `Literal` y los campos del bloque Interfaces, en ese orden, tras `deterministic`. Actualizar la docstring de `RunMeta` (tabla de atributos: «lo pedido» frente a «lo aplicado», A6; `prompt_sha256` del texto enviado, A7; una meta por intento, D14).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_provenance.py tests/test_provenance.py tests/test_artifacts.py tests/test_run_context.py -v`
Expected: PASS (ningún test existente cambia: todo es default).

- [ ] **Step 5: Commit**

```bash
git add revisia/provenance/runmeta.py tests/test_contratos_provenance.py
git commit -m "feat(provenance): RunMeta v2 con lo aplicado, intento, resultado y plantilla (A6, A7, D12, D14)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 4: Sink de metas por contexto (`revisia/provenance/sink.py`)

**Files:**
- Create: `revisia/provenance/sink.py`.
- Modify: `revisia/provenance/__init__.py` (exportar `emit`, `collecting`, `installed`, `current_sink`, `MetaSink`).
- Test: `tests/test_sink.py` (nuevo).

**Interfaces:**
- Consumes: `RunMeta` (Tarea 3).
- Produces (D14, §4.4 «sin consumidores todavía»; PR-A engancha `journaled` y `RunContext.record_meta`):
  - `MetaSink = Callable[[RunMeta], None]`.
  - `emit(meta: RunMeta) -> None`: entrega `meta` a **todos** los sinks activos en el contexto actual, del más externo al más interno; sin sinks, no hace nada.
  - `collecting() -> Iterator[list[RunMeta]]` (`@contextmanager`): activa un sink que acumula en la lista que devuelve; al salir, lo retira.
  - `installed(sink: MetaSink) -> Iterator[None]` (`@contextmanager`): activa un sink arbitrario durante el bloque.
  - `current_sink() -> MetaSink | None`: el sink más interno activo, o `None`.
  - `active_sinks() -> tuple[MetaSink, ...]`: los activos, del más externo al más interno.
  - Implementación: un `contextvars.ContextVar[tuple[MetaSink, ...]]` con default `()`; cada context manager hace `set` al entrar y `reset(token)` al salir. Un hilo nuevo sin `contextvars.copy_context()` no ve los sinks del padre: es el aislamiento que D14 necesita para que las llamadas de un registro no se cuelen en otro.

- [ ] **Step 1: Test que falla** — crear `tests/test_sink.py`:

```python
"""Sink de metas por contexto (spec 2026-10-18 §4.4, D14; PR-0 lo define, PR-A lo consume)."""

from __future__ import annotations

import threading

from revisia.provenance.runmeta import RunMeta
from revisia.provenance.sink import active_sinks, collecting, current_sink, emit, installed


def _meta(n: int) -> RunMeta:
    return RunMeta(
        provider="fake", model="m", temperature=0.0, prompt_sha256=f"{n:064x}", response_sha256="r"
    )


def test_sin_sink_emit_no_hace_nada_y_current_sink_es_none() -> None:
    assert current_sink() is None
    assert active_sinks() == ()
    emit(_meta(1))  # no lanza


def test_collecting_recoge_en_orden_y_se_retira_al_salir() -> None:
    with collecting() as metas:
        emit(_meta(1))
        emit(_meta(2))
        assert current_sink() is not None
    assert [m.prompt_sha256 for m in metas] == [f"{1:064x}", f"{2:064x}"]
    assert current_sink() is None
    emit(_meta(3))
    assert len(metas) == 2  # fuera del bloque ya no recoge


def test_sinks_anidados_reciben_todos_del_externo_al_interno() -> None:
    orden: list[str] = []
    with installed(lambda m: orden.append("externo")), collecting() as internos:
        emit(_meta(1))
    assert orden == ["externo"] and len(internos) == 1


def test_un_sink_que_lanza_propaga_el_error_y_corta_la_entrega() -> None:
    import pytest

    recibidos: list[RunMeta] = []

    def roto(_m: RunMeta) -> None:
        raise OSError("disco lleno")

    with installed(roto), collecting() as metas, pytest.raises(OSError):
        with installed(recibidos.append):
            emit(_meta(1))
    # La entrega va del sink externo al interno y no atrapa errores: el externo (el que en PR-A
    # escribe llm_calls.jsonl) es el roto, así que ni el colector ni el interno reciben la meta.
    # D14 no admite una meta «recogida» que no llegó a disco.
    assert recibidos == [] and metas == []


def test_otro_hilo_no_ve_el_sink_del_padre() -> None:
    visto: list[tuple] = []
    with collecting():
        hilo = threading.Thread(target=lambda: visto.append(active_sinks()))
        hilo.start()
        hilo.join()
    assert visto == [()]


def test_el_contexto_se_restaura_aunque_el_bloque_lance() -> None:
    import pytest

    with pytest.raises(ValueError), collecting():
        raise ValueError("x")
    assert active_sinks() == ()
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_sink.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'revisia.provenance.sink'`.

- [ ] **Step 3: Implementar** `revisia/provenance/sink.py` con las firmas del bloque Interfaces. `emit` recorre `active_sinks()` en orden y llama a cada uno sin atrapar excepciones (un fallo al escribir `llm_calls.jsonl` tiene que verse; D14 no admite metas perdidas en silencio). Docstring del módulo: por qué un `ContextVar` (una llamada de un registro no se mezcla con otra ni con otro hilo) y qué engancha PR-A. Exportar en `revisia/provenance/__init__.py`.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_sink.py tests/test_provenance.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/provenance/sink.py revisia/provenance/__init__.py tests/test_sink.py
git commit -m "feat(provenance): MetaSink por contexto (emit, collecting, installed) sin consumidores (D14)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 5: Contratos de artefactos v2 (`revisia/schemas/artifacts.py`)

**Files:**
- Modify: `revisia/schemas/artifacts.py` (`ARTIFACT_SCHEMA_VERSION`, línea 29; `RunInfo`, 107; `JournalEntry`, 161; `RetrievalOutcome`, 241; `GateSummary`, 276; literales y modelos nuevos).
- Modify: `tests/test_artifacts.py:160` (`== 1` → `== 2`), `tests/test_hitl.py:224-228` (la tupla `(1, "reporte", "A1")` → `(2, …)`) y `tests/test_hitl.py:256` (`"schema_version": 1` → `2`): `review_gate` escribe `ARTIFACT_SCHEMA_VERSION` en la solicitud (`hitl.py:766`).
- Test: `tests/test_artifacts.py` (añadir una sección).

**Interfaces:**
- Consumes: `RUNMETA_SCHEMA_VERSION` (Tarea 3), `utc_now_iso`.
- Produces (§4.1, §4.2, D12, D17, D20, D21, D23):
  - `ARTIFACT_SCHEMA_VERSION: int = 2` (D12; su docstring ya dice que sube con un cambio de estos modelos). Todo JSON con `schema_version` pasa a escribir 2; los JSON v1 siguen leyéndose (el campo es `int`).
  - Literales nuevos: `RunKind = Literal["review", "benchmark"]`; `QuoteStatus = Literal["exact", "normalized", "not_found", "none"]`; `SourceText = Literal["fulltext", "abstract"]`; `RecordStatus = Literal["ok", "failed"]`; `GroundingMode = Literal["existence", "judge", "embedder"]`; `FulltextSource = Literal["oa", "human_rescue"]`; `WithheldReason = Literal["copyright", "private"]`.
  - `ENVIRONMENT_PACKAGES: tuple[str, ...] = ("pydantic", "pyyaml", "python-dotenv", "markdown", "nh3", "httpx", "pypdf", "scipy", "matplotlib", "google-genai", "openai", "anthropic", "weasyprint")` (nombres de distribución para `importlib.metadata.version`; PR-A recorre la tupla y guarda los presentes).
  - `class Environment(BaseModel)`: `engine_version: str`, `python_version: str`, `python_implementation: str`, `platform: str`, `git_commit: str | None = None`, `git_dirty: bool | None = None`, `packages: dict[str, str] = {}`, `prompt_templates: dict[str, str] = {}` (claves `"<agente>/<ver>.md"` y `"rob/<tool>.yml"`), `created_utc: str`.
  - `RunInfo` gana `kind: RunKind = "review"` y `environment: Environment | None = None` (`None` = corrida anterior a la Ola 2; PR-A lo escribe en `ensure_snapshot`; `prompt_sha256` se retira en PR-A, §5.5, no aquí).
  - `class JournalFailure(BaseModel)`: `type: str`, `message: str` (redactado por quien la escribe), `attempts: int = Field(ge=1)`.
  - `JournalEntry` v2: `output: dict | None` (sigue siendo obligatorio: sin la clave no valida), `error: JournalFailure | None = None`, `status: RecordStatus = "ok"`; `model_validator(mode="after")`: `(status == "failed") == (output is None) == (error is not None)`, si no `ValueError("una entrada failed lleva output nulo y error; una ok, output y sin error")`.
  - `RetrievalOutcome` v2: `truncated: bool = False`, `n_chars_total: int | None = None`, `source: FulltextSource = "oa"`, `rescue_file: str | None = None`, `rescue_file_sha256: str | None = None`; validador (además del de `reason`): `source == "human_rescue"` ⇔ `rescue_file is not None and rescue_file_sha256 is not None`; `truncated` ⇒ `n_chars_total is not None and n_chars_total > n_chars`.
  - `GateSummary.n_edits: int = 0` (lo cuenta `summarize_gates`, Tarea 6).
  - `class WithheldFile(BaseModel)`: `relpath: str`, `sha256: str`, `n_bytes: int`. `class WithheldDir(BaseModel)`: `path: str`, `reason: WithheldReason`, `files: list[WithheldFile] = []`. `class DepositSource(BaseModel)`: `slug: str`, `timestamp: str`, `manifest_sha256: str`. `class DepositInfo(BaseModel)`: `schema_version: int = ARTIFACT_SCHEMA_VERSION`, `created_utc: str = Field(default_factory=utc_now_iso)`, `source_run: DepositSource`, `withheld: list[WithheldDir]`, `engine_version: str`. Constante `DEPOSIT_FILE = "deposit.json"`; `WITHHELD_DIRS: tuple[str, ...] = ("04_fulltext/texts/", "screening_ft/rescues/")` (D17).

- [ ] **Step 1: Tests que fallan** — añadir al final de `tests/test_artifacts.py`:

```python
# ── Ola 2 · contratos v2 (spec 2026-10-18 §4.1, §4.2; D12, D17, D20, D21, D23) ──


def test_schema_version_sube_a_2_y_coincide_con_runmeta() -> None:
    assert ARTIFACT_SCHEMA_VERSION == RUNMETA_SCHEMA_VERSION == 2
    assert set(get_args(RunKind)) == {"review", "benchmark"}
    assert set(get_args(QuoteStatus)) == {"exact", "normalized", "not_found", "none"}
    assert set(get_args(GroundingMode)) == {"existence", "judge", "embedder"}
    assert set(get_args(FulltextSource)) == {"oa", "human_rescue"}
    assert len(ENVIRONMENT_PACKAGES) == 13 and len(set(ENVIRONMENT_PACKAGES)) == 13


def test_run_info_v1_valida_y_es_review_sin_entorno() -> None:
    v1 = {
        "schema_version": 1,
        "slug": "s",
        "timestamp": "T",
        "started_utc": "2026-10-01T00:00:00+00:00",
        "engine_version": "0.8.0",
        "python_version": "3.13.0",
        "max_results": 5,
        "mailto_set": False,
    }
    info = RunInfo.model_validate(v1)
    assert (info.kind, info.environment) == ("review", None)
    assert RunInfo.model_validate({**v1, "kind": "benchmark"}).kind == "benchmark"
    with pytest.raises(ValidationError):
        RunInfo.model_validate({**v1, "kind": "piloto"})


def test_environment_minimo_y_con_plantillas() -> None:
    env = Environment(
        engine_version="0.9.0",
        python_version="3.13.0",
        python_implementation="CPython",
        platform="Windows-11",
        created_utc="2026-10-18T00:00:00+00:00",
        prompt_templates={"extraccion/v2.md": "a" * 64, "rob/RoB2.yml": "b" * 64},
    )
    assert (env.git_commit, env.git_dirty, env.packages) == (None, None, {})
    assert Environment.model_validate(env.model_dump()) == env


def _entrada_v1() -> dict:
    return {
        "schema_version": 1,
        "stage": "screening_ta",
        "record_id": "r",
        "input_sha256": "i" * 64,
        "output": {"record_id": "r"},
    }


def test_journal_entry_v1_es_ok_y_la_failed_exige_output_nulo_y_error() -> None:
    assert JournalEntry.model_validate(_entrada_v1()).status == "ok"
    fallo = {"type": "DeterministicCallError", "message": "400", "attempts": 3}
    failed = JournalEntry.model_validate(
        {**_entrada_v1(), "output": None, "error": fallo, "status": "failed"}
    )
    assert failed.error is not None and failed.error.attempts == 3
    for incoherente in (
        {**_entrada_v1(), "status": "failed"},  # failed con output
        {**_entrada_v1(), "output": None},  # ok sin output
        {**_entrada_v1(), "error": fallo},  # ok con error
        {**_entrada_v1(), "output": None, "status": "failed"},  # failed sin error
    ):
        with pytest.raises(ValidationError):
            JournalEntry.model_validate(incoherente)
    with pytest.raises(ValidationError):
        JournalEntry.model_validate({k: v for k, v in _entrada_v1().items() if k != "output"})


def test_retrieval_outcome_v2_rescate_humano_y_recorte() -> None:
    oa = RetrievalOutcome(available=True, n_chars=10, text_sha256="t")
    assert (oa.source, oa.truncated, oa.n_chars_total, oa.rescue_file) == ("oa", False, None, None)
    rescate = RetrievalOutcome(
        available=True,
        n_chars=10,
        source="human_rescue",
        rescue_file="screening_ft/rescues/a.pdf",
        rescue_file_sha256="f" * 64,
    )
    assert rescate.source == "human_rescue"
    with pytest.raises(ValidationError):  # rescate sin fichero
        RetrievalOutcome(available=True, source="human_rescue")
    with pytest.raises(ValidationError):  # fichero sin ser rescate
        RetrievalOutcome(available=True, rescue_file="screening_ft/rescues/a.pdf")
    recortado = RetrievalOutcome(available=True, n_chars=120_000, n_chars_total=150_000, truncated=True)
    assert recortado.truncated
    with pytest.raises(ValidationError):  # truncated sin total
        RetrievalOutcome(available=True, n_chars=10, truncated=True)
    with pytest.raises(ValidationError):  # total no mayor que lo guardado
        RetrievalOutcome(available=True, n_chars=10, n_chars_total=10, truncated=True)


def test_gate_summary_n_edits_vale_cero_por_defecto() -> None:
    resumen = GateSummary(
        stage="extraccion", action="approve", actor="human:ana", autonomy="A0", timestamp_utc="t"
    )
    assert resumen.n_edits == 0


def test_deposit_info_lista_lo_retenido_con_sus_hashes() -> None:
    info = DepositInfo(
        source_run=DepositSource(slug="s", timestamp="T", manifest_sha256="m" * 64),
        withheld=[
            WithheldDir(
                path="04_fulltext/texts/",
                reason="copyright",
                files=[WithheldFile(relpath="04_fulltext/texts/0001.txt", sha256="a" * 64, n_bytes=12)],
            )
        ],
        engine_version="0.9.0",
    )
    assert info.schema_version == 2 and info.created_utc
    assert WITHHELD_DIRS == ("04_fulltext/texts/", "screening_ft/rescues/")
    assert DEPOSIT_FILE == "deposit.json"
    with pytest.raises(ValidationError):
        WithheldDir(path="x/", reason="porque sí")
```

Imports a añadir en `tests/test_artifacts.py`: `from revisia.provenance.runmeta import RUNMETA_SCHEMA_VERSION` y, de `revisia.schemas.artifacts`, `DEPOSIT_FILE, ENVIRONMENT_PACKAGES, WITHHELD_DIRS, DepositInfo, DepositSource, Environment, FulltextSource, GroundingMode, QuoteStatus, RunKind, WithheldDir, WithheldFile`.

Cambios de expectativa (D12):
- `tests/test_artifacts.py:160`: `assert entry.schema_version == ARTIFACT_SCHEMA_VERSION == 1` → `assert entry.schema_version == ARTIFACT_SCHEMA_VERSION == 2`.
- `tests/test_hitl.py:224-228`: `(solicitud["schema_version"], solicitud["stage"], solicitud["autonomy"]) == (1, "reporte", "A1")` → `(2, "reporte", "A1")`.
- `tests/test_hitl.py:256`: `{"schema_version": 1, "stage": "reporte", …}` → `{"schema_version": 2, "stage": "reporte", …}`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_artifacts.py -v`
Expected: FAIL con `ImportError` (nombres nuevos).

- [ ] **Step 3: Implementar** en `revisia/schemas/artifacts.py`: la constante a 2 (docstring: Ola 2, D12), los literales y `ENVIRONMENT_PACKAGES` junto a los literales existentes, `Environment` antes de `RunInfo`, los campos de `RunInfo`, `JournalFailure` antes de `JournalEntry` y su validador, los campos y el validador de `RetrievalOutcome`, `n_edits` en `GateSummary` (docstring: ediciones `edit_field`/`edit_domain` de la decisión efectiva), y el bloque de depósito al final (D17). La docstring del módulo pasa a citar también el spec de la Ola 2 §4.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"`
Expected: PASS (los únicos cambios de expectativa son los dos de arriba; el auditor no compara `schema_version` con nada, verificado en `revisia/audit/` el 2026-10-18).

- [ ] **Step 5: Commit**

```bash
git add revisia/schemas/artifacts.py tests/test_artifacts.py tests/test_hitl.py
git commit -m "feat(schemas): artefactos v2: Environment, kind, JournalEntry con fallo, RetrievalOutcome con rescate y recorte, DepositInfo (D12, D17, D20, D21, D23)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 6: Acciones nuevas del ledger y `n_edits` (`revisia/provenance/ledger.py`)

**Files:**
- Modify: `revisia/provenance/ledger.py` (`LEDGER_ACTIONS`, línea 30; `summarize_gates`, 145).
- Modify: `tests/test_contratos_provenance.py::test_constantes_del_ledger` (línea 50).
- Test: `tests/test_contratos_provenance.py` (añadir).

**Interfaces:**
- Consumes: `GateSummary.n_edits` (Tarea 5).
- Produces (§4.2 «Ledger»):
  - `LEDGER_ACTIONS` = `{approve, reject, auto-proceed, label, flag_review, edit_field, edit_domain, rescue_text}`; `GATE_DECISION_ACTIONS` no cambia.
  - `EDIT_ACTIONS: frozenset[str] = frozenset({"edit_field", "edit_domain"})`.
  - `summarize_gates` cuenta en `n_edits` las entradas `edit_field`/`edit_domain` de la etapa con el `decision_sha256` de la decisión efectiva (misma regla que `n_labels`); `rescue_text` no cuenta en ningún contador (su contrato es la relación 23, que verifica el auditor por `target`).
  - Contenido de cada acción (lo escriben PR-C y PR-E; aquí solo se documenta en la docstring de `DecisionEntry`): `edit_field`: stage `extraccion`, `target = "<study_id>#<key>"`, `detail{from, to, reason, request_sha256, decision_sha256}`; `edit_domain`: stage `rob`, `target = "<study_id>#<domain_id>"` o `"<study_id>#overall"`, mismo `detail`; `rescue_text`: stage `screening_ft`, `target = record_id`, `detail{text_file, file_sha256, n_chars, request_sha256, decision_sha256}`. Las ediciones se escriben antes de su `approve`, en orden de id y clave; nunca acompañan a un `reject`.

- [ ] **Step 1: Tests** — en `tests/test_contratos_provenance.py` cambiar la primera línea de `test_constantes_del_ledger` por:

```python
    assert set(LEDGER_ACTIONS) == {
        "approve",
        "reject",
        "auto-proceed",
        "label",
        "flag_review",
        "edit_field",
        "edit_domain",
        "rescue_text",
    }
    assert set(EDIT_ACTIONS) == {"edit_field", "edit_domain"}
    assert EDIT_ACTIONS < LEDGER_ACTIONS and not EDIT_ACTIONS & GATE_DECISION_ACTIONS
```

y añadir, tras `test_summarize_gates_flag_reviews_y_forced_human`:

```python
def test_summarize_gates_cuenta_las_ediciones_de_la_decision_efectiva() -> None:
    resumen = summarize_gates(
        [
            _e("extraccion", "edit_field", target="s1#n", decision_sha256="viejo"),
            _e("extraccion", "reject", decision_sha256="viejo", request_sha256="r"),
            _e("extraccion", "edit_field", target="s1#n", decision_sha256="d"),
            _e("extraccion", "edit_field", target="s2#edad", decision_sha256="d"),
            _e("extraccion", "approve", decision_sha256="d", request_sha256="r"),
            _e("rob", "edit_domain", target="s1#D1", decision_sha256="x"),
            _e("rob", "edit_domain", target="s1#overall", decision_sha256="x"),
            _e("rob", "approve", decision_sha256="x", request_sha256="q"),
            _e("screening_ft", "rescue_text", target="s3", decision_sha256="y"),
            _e("screening_ft", "label", target="s3", decision_sha256="y"),
            _e("screening_ft", "approve", decision_sha256="y", request_sha256="p"),
        ]
    )
    assert (resumen["extraccion"].n_edits, resumen["extraccion"].n_labels) == (2, 0)
    assert resumen["rob"].n_edits == 2
    # `rescue_text` no es etiqueta ni edición: va atado a su `label` (relación 23).
    assert (resumen["screening_ft"].n_edits, resumen["screening_ft"].n_labels) == (0, 1)
```

Import: `EDIT_ACTIONS` desde `revisia.provenance.ledger`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_provenance.py -v -k "constantes or ediciones"`
Expected: FAIL (`ImportError: EDIT_ACTIONS`).

- [ ] **Step 3: Implementar** en `revisia/provenance/ledger.py`: las constantes (comentario: spec 2026-10-18 §4.2; quién las emite), el contador en el bucle de `summarize_gates` (`elif entry.action in EDIT_ACTIONS: n_edits += 1`) y `n_edits=n_edits` en el `GateSummary`. Docstring de `DecisionEntry.action`: lista las ocho acciones con su `target` y `detail`.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_contratos_provenance.py tests/test_audit_hitl.py tests/test_hitl.py -v`
Expected: PASS (`checks_hitl.py:292` acepta las acciones nuevas porque lee `LEDGER_ACTIONS`; nadie las emite todavía).

- [ ] **Step 5: Commit**

```bash
git add revisia/provenance/ledger.py tests/test_contratos_provenance.py
git commit -m "feat(ledger): acciones edit_field, edit_domain y rescue_text; n_edits en GateSummary (D3, D5, D21)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 7: Decisión por campo y por dominio: modelos (`revisia/orchestration/hitl.py`)

**Files:**
- Modify: `revisia/orchestration/hitl.py` (`RecordLabel`, línea 123; `HumanDecision`, 151; `_validate`, 449).
- Test: `tests/test_hitl.py` (añadir una sección).

**Interfaces:**
- Consumes: `plain_text` (ledger).
- Produces (§4.2 «decision.yml»; solo modelos y validación estructural; las políticas `FieldPolicy`/`DomainPolicy`, `edit_field`/`edit_domain` en `_register` y `GateResult.edits` son de PR-C y PR-E):
  - `RecordLabel.text_file: str | None = None`; `field_validator`: si no es `None`, debe casar con `^rescues/[^/\\]+$` **y** el componente tras `rescues/` no puede ser `.` ni `..` (relativo, un solo nombre de fichero bajo `rescues/`); si no, `ValueError("text_file debe ser rescues/<nombre>, relativo a screening_ft/")`. Que el fichero exista lo comprueba el gate de FT (PR-C).
  - `_claves_a_texto(value: object) -> object`: función de módulo con la lógica que hoy está en el `@classmethod` `HumanDecision._claves_como_texto` (`hitl.py:172-190`); el classmethod pasa a delegar en ella y `FieldEdits.fields` y `DomainEdits.domains` la usan en su propio `field_validator(mode="before")` (misma regla: claves escalares a texto; nulos, listas y mapas rechazados).
  - `class FieldEdit(BaseModel)` (`extra="forbid"`): `value: str | int | float | None`, `reason: str`; `field_validator("reason")`: `plain_text(reason)` no vacío, si no `ValueError("reason es obligatoria en una edición")`.
  - `class FieldEdits(BaseModel)` (`extra="forbid"`): `fields: dict[str, FieldEdit]` (obligatorio).
  - `class DomainEdit(BaseModel)` (`extra="forbid"`): `judgment: str`, `reason: str` (misma regla de `reason`).
  - `class DomainEdits(BaseModel)` (`extra="forbid"`): `domains: dict[str, DomainEdit] = {}`, `overall: DomainEdit | None = None`.
  - `RecordDecision = Annotated[RecordLabel | FieldEdits | DomainEdits, Field(union_mode="left_to_right")]` (el `union_mode` va en la **unión**, no en el `dict`: puesto en `records` pydantic rechaza la clase al definirla con «Unable to apply constraint 'union_mode' to schema of type 'dict'»; verificado el 2026-10-18); `HumanDecision.records: dict[str, RecordDecision] = Field(default_factory=dict)`. Con `left_to_right`, `{}` sigue siendo un `RecordLabel` «sin etiquetar» (como hoy) y `{"fields": …}` / `{"domains": …}` / `{"overall": …}` caen en su modelo porque `RecordLabel` tiene `extra="forbid"`; una mezcla (`label` + `fields`) no valida en ninguno y es `ValidationError`.
  - `_validate` gana dos comprobaciones estructurales **antes** del `if not decision.approved: return` (se comprueban siempre, como las de «`records` en un gate que no los admite»): (a) algún valor de `records` que no sea `RecordLabel` → `DecisionFileError(f"{path}: `records` con ediciones por campo o por dominio ({_listed(ids)}): este gate etiqueta registros (label/reason); la corrección por campo (extraccion) y por dominio (rob) llegan con sus políticas en la Ola 2 (PR-C, PR-E).")`; (b) algún `RecordLabel.text_file` no nulo → `DecisionFileError(f"{path}: `text_file` en {_listed(ids)}: el rescate con texto completo llega en la Ola 2 (PR-C); este motor todavía no lo ingiere.")`. PR-C y PR-E sustituyen (a) y (b) por sus políticas.
  - `GateResult.labels: dict[str, RecordLabel]` no cambia de tipo: `review_gate` sigue construyéndolo solo con `RecordLabel` (garantizado por (a)).

- [ ] **Step 1: Tests que fallan** — añadir al final de `tests/test_hitl.py`:

```python
# ── Ola 2 · modelos de decisión por campo y por dominio (spec 2026-10-18 §4.2; D3, D5, D21) ──


def test_field_edits_y_domain_edits_son_estrictos() -> None:
    edits = FieldEdits.model_validate({"fields": {"n": {"value": 240, "reason": "tabla 1"}}})
    assert edits.fields["n"].value == 240
    with pytest.raises(ValidationError):  # clave desconocida
        FieldEdits.model_validate({"fields": {"n": {"value": 1, "reason": "r", "extra": 1}}})
    with pytest.raises(ValidationError):  # razón en blanco
        FieldEdit(value="x", reason="   ")
    with pytest.raises(ValidationError):  # razón solo con marcas invisibles
        DomainEdit(judgment="low", reason="\u200b")
    dominios = DomainEdits.model_validate(
        {"domains": {"D1": {"judgment": "high", "reason": "sin cegamiento"}}, "overall": None}
    )
    assert dominios.domains["D1"].judgment == "high" and dominios.overall is None
    assert DomainEdits.model_validate({"overall": {"judgment": "high", "reason": "r"}}).domains == {}


@pytest.mark.parametrize(
    ("crudo", "tipo"),
    [
        ({}, RecordLabel),
        ({"label": "include", "reason": "ok"}, RecordLabel),
        ({"fields": {"n": {"value": "240", "reason": "r"}}}, FieldEdits),
        ({"domains": {"D1": {"judgment": "low", "reason": "r"}}}, DomainEdits),
        ({"overall": {"judgment": "low", "reason": "r"}}, DomainEdits),
    ],
)
def test_human_decision_records_admite_las_tres_formas(crudo: dict, tipo: type) -> None:
    decision = HumanDecision.model_validate(
        {"request_sha256": "h", "approved": True, "records": {"s1": crudo}}
    )
    assert isinstance(decision.records["s1"], tipo)


def test_human_decision_records_rechaza_una_mezcla_de_formas() -> None:
    with pytest.raises(ValidationError):
        HumanDecision.model_validate(
            {
                "request_sha256": "h",
                "approved": True,
                "records": {"s1": {"label": "include", "fields": {}}},
            }
        )


@pytest.mark.parametrize("ruta", ["rescues/a.pdf", "rescues/texto completo.txt"])
def test_record_label_text_file_relativo_bajo_rescues(ruta: str) -> None:
    assert RecordLabel(label="include", reason="r", text_file=ruta).text_file == ruta


@pytest.mark.parametrize(
    "ruta",
    [
        "a.pdf",
        "rescues/../x.pdf",
        "rescues/..",
        "rescues/.",
        "/tmp/rescues/a.pdf",
        "C:\\rescues\\a.pdf",
        "rescues/",
        "rescues/a/b.pdf",
    ],
)
def test_record_label_text_file_rechaza_rutas_fuera_de_rescues(ruta: str) -> None:
    with pytest.raises(ValidationError):
        RecordLabel(label="include", reason="r", text_file=ruta)


def _decision_con(tmp_path: Path, records: dict) -> Path:
    path = tmp_path / "decision.yml"
    path.write_text(
        yaml.safe_dump({"request_sha256": "h", "approved": True, "records": records}), "utf-8"
    )
    return path


def test_validate_rechaza_ediciones_en_un_gate_de_cribado_con_mensaje(tmp_path: Path) -> None:
    hints = (RecordHint(record_id="s1", title="t", proposal="include"),)
    policy = RecordPolicy(hints=hints)
    path = _decision_con(tmp_path, {"s1": {"fields": {"n": {"value": 1, "reason": "r"}}}})
    decision = HumanDecision.model_validate(yaml.safe_load(path.read_text("utf-8")))
    with pytest.raises(DecisionFileError, match="ediciones por campo o por dominio"):
        hitl._validate(path, decision, records=policy, flags=None)


def test_validate_rechaza_text_file_mientras_no_haya_rescate_con_texto(tmp_path: Path) -> None:
    hints = (RecordHint(record_id="s1", title="t", proposal=None),)
    policy = RecordPolicy(hints=hints, rescue_ids=frozenset({"s1"}))
    path = _decision_con(
        tmp_path, {"s1": {"label": "include", "reason": "pdf propio", "text_file": "rescues/a.pdf"}}
    )
    decision = HumanDecision.model_validate(yaml.safe_load(path.read_text("utf-8")))
    with pytest.raises(DecisionFileError, match="text_file"):
        hitl._validate(path, decision, records=policy, flags=None)
```

Imports a añadir en `tests/test_hitl.py` (si faltan): `from pathlib import Path`, `import yaml`, `from pydantic import ValidationError`, `from revisia.orchestration import hitl`, y de `revisia.orchestration.hitl`: `DecisionFileError, DomainEdit, DomainEdits, FieldEdit, FieldEdits, HumanDecision, RecordHint, RecordLabel, RecordPolicy`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_hitl.py -v -k "edits or text_file or tres_formas or mezcla"`
Expected: FAIL (`ImportError: FieldEdits`).

- [ ] **Step 3: Implementar** en `revisia/orchestration/hitl.py`: los cuatro modelos tras `FlagReview` (docstrings con D3, D5), el alias `RecordDecision`, el campo `text_file` con su validador en `RecordLabel`, el tipo de `HumanDecision.records` con `union_mode="left_to_right"`, y las dos guardas en `_validate` (la docstring del módulo gana un párrafo: «Ola 2: `records` admite tres formas según el gate; en esta versión solo la de cribado se aplica»).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"`
Expected: PASS (ningún `decision.yml` que hoy valida cambia de resultado: una decisión con `fields:` ya fallaba por `extra="forbid"`, solo cambia el mensaje).

- [ ] **Step 5: Commit**

```bash
git add revisia/orchestration/hitl.py tests/test_hitl.py
git commit -m "feat(hitl): modelos FieldEdits/DomainEdits y RecordLabel.text_file con validación estructural (D3, D5, D21)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 8: Extracción v2 (`revisia/schemas/extraction.py`)

**Files:**
- Modify: `revisia/schemas/extraction.py` (`ExtractionField`, línea 19; `ExtractionRecord`, 38).
- Test: `tests/test_schemas.py` (añadir).

**Interfaces:**
- Consumes: `ARTIFACT_SCHEMA_VERSION`, `QuoteStatus`, `SourceText`, `RecordStatus` (Tarea 5).
- Produces (§4.2 «ExtractionField v2 / ExtractionRecord v2»; `ExtractionAgreement` v2 vive en `revisia/extraction_agreement.py`, que es «solo PR-C» en §15, y se hace allí):
  - `ExtractionField` conserva `value`, `source_quote`, `source_locator`, `confidence`, `status` y gana: `quote_status: QuoteStatus = "none"`, `quote_offset: int | None = Field(default=None, ge=0)`, `human_value: str | int | float | None = None`, `human_reason: str | None = None`, `human_actor: str | None = None`, `human_edited: bool = False`; `@property final_value -> str | int | float | None` = `human_value` si `human_edited`, si no `value`; `model_validator`: `human_edited` ⇒ `human_reason` y `human_actor` no nulos; `not human_edited` ⇒ los tres `human_*` nulos.
  - `ExtractionRecord` gana: `schema_version: int = ARTIFACT_SCHEMA_VERSION`, `source_text: SourceText = "abstract"` (la 0.8 solo leía el resumen: el default reproduce la v1), `text_sha256: str | None = None`, `truncated: bool = False`, `status: RecordStatus = "ok"`.
  - Docstring del módulo: se corrige «revisión humana campo a campo del 20 % mínimo» por «el humano aprueba la tabla por estudio y corrige campo a campo (D3); la concordancia IA–IA del 20 % es una señal (D4)».

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_schemas.py`:

```python
def test_extraction_field_v2_final_value_y_coherencia_humana() -> None:
    campo = ExtractionField(value="240")
    assert (campo.quote_status, campo.quote_offset, campo.human_edited) == ("none", None, False)
    assert campo.final_value == "240"
    editado = ExtractionField(
        value="240", human_value=236, human_reason="tabla 2", human_actor="human:ana", human_edited=True
    )
    assert editado.final_value == 236
    with pytest.raises(ValidationError):  # editado sin razón ni actor
        ExtractionField(value="1", human_value="2", human_edited=True)
    with pytest.raises(ValidationError):  # valor humano sin marcar la edición
        ExtractionField(value="1", human_value="2")
    with pytest.raises(ValidationError):
        ExtractionField(value="1", quote_status="maybe")


def test_extraction_record_v1_valida_como_abstract_ok() -> None:
    v1 = {"study_id": "s", "fields": {"n": {"value": "240"}}, "extractor": "agent:extraccion"}
    rec = ExtractionRecord.model_validate(v1)
    assert (rec.schema_version, rec.source_text, rec.text_sha256, rec.truncated, rec.status) == (
        2,
        "abstract",
        None,
        False,
        "ok",
    )
    assert ExtractionRecord(study_id="s", status="failed").fields == {}
```

Imports: `import pytest`, `from pydantic import ValidationError` (si faltan), `ExtractionRecord`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_schemas.py -v -k extraction`
Expected: FAIL (`quote_status` desconocido / `final_value` inexistente).

- [ ] **Step 3: Implementar** en `revisia/schemas/extraction.py` según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_schemas.py tests/test_pipeline_fake.py tests/test_exports_biblio_extraction.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/schemas/extraction.py tests/test_schemas.py
git commit -m "feat(schemas): ExtractionField/ExtractionRecord v2 con quote_status, valores humanos y final_value (D3, D22)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 9: RoB v2 sin GRADE y con NOS casos-controles (`revisia/schemas/rob.py`)

**Files:**
- Modify: `revisia/schemas/rob.py` (`RoBTool`, línea 15; `RoBDomain`, 19; `RoBAssessment`, 28).
- Modify: `revisia/agents/rob.py` (`TOOL_DOMAINS`: quitar la clave `GRADE`, añadir `NewcastleOttawaCaseControl`; nada más: el agente es de PR-E).
- Modify: `protocols/_TEMPLATE/protocol.yml:44-46` (comentario de `rob_tool`: quitar `GRADE (certeza agregada)`, añadir `NewcastleOttawaCaseControl`).
- Modify: `tests/test_rob.py::test_cada_herramienta_tiene_dominios` (la tupla de herramientas).
- Test: `tests/test_schemas.py` (añadir).

**Interfaces:**
- Consumes: `ARTIFACT_SCHEMA_VERSION`, `QuoteStatus`, `SourceText`, `RecordStatus`.
- Produces (D5, §4.2 «RoBAssessment v2»):
  - `RoBTool = Literal["RoB2", "ROBINS-I", "NewcastleOttawa", "NewcastleOttawaCaseControl", "AMSTAR2", "QUADAS-2"]`. `GRADE` sale: un `protocol.yml` con `rob_tool: GRADE` deja de cargar (`ValidationError` → rc 2 en `validate`/`run`; el mensaje de preflight de §9 lo pone PR-E). `NewcastleOttawa` sigue siendo el formulario de cohortes.
  - `RoBJudgment` se conserva como alias (lo usa `_RoBDomainOut` del agente hasta PR-E) pero ningún modelo de este módulo lo exige ya.
  - `RoBDomain` v2: `domain: str` (nombre legible, como hoy), `id: str | None = None` (id oficial de la especificación; PR-E lo rellena siempre en el agente y el check `rob` de PR-G da FAIL a un dominio sin `id`, pero **el esquema lo deja opcional** para que una evaluación 0.8 siga cargando en el diagnóstico: §19 fila 2), `judgment: str` (validado contra la escala por quien conoce la herramienta: `RoBToolSpec.scale_for`, Tarea 10), `rationale: str = ""`, `support_quote: str | None = None`, `quote_status: QuoteStatus = "none"`, `answers: dict[str, str] = {}`, `human_judgment: str | None = None`, `human_reason: str | None = None`, `human_actor: str | None = None`; validador: `human_judgment` no nulo ⇒ `human_reason` y `human_actor` no nulos.
  - `class RoBApplicability(BaseModel)`: `id: str`, `judgment: str`, `rationale: str = ""` (QUADAS-2).
  - `RoBAssessment` v2: `schema_version: int = ARTIFACT_SCHEMA_VERSION`, `study_id`, `tool: RoBTool`, `tool_version: str | None = None`, `domains: list[RoBDomain] = []`, `applicability: list[RoBApplicability] = []`, `overall_llm: str | None = None`, `overall_algorithm: str | None = None`, `overall_human: str | None = None`, `overall_reason: str | None = None`, `overall: str | None = None` (final), `source_text: SourceText = "abstract"`, `status: RecordStatus = "ok"`; validador: `overall_human` no nulo ⇒ `overall_reason` no nulo. El agente de hoy sigue poniendo `overall` directamente (PR-E separa `overall_llm`/`overall_algorithm`).

- [ ] **Step 1: Tests** — añadir a `tests/test_schemas.py`:

```python
def test_rob_tool_sin_grade_y_con_nos_casos_controles() -> None:
    assert set(get_args(RoBTool)) == {
        "RoB2",
        "ROBINS-I",
        "NewcastleOttawa",
        "NewcastleOttawaCaseControl",
        "AMSTAR2",
        "QUADAS-2",
    }
    with pytest.raises(ValidationError):
        RoBAssessment(study_id="s", tool="GRADE")


def test_rob_assessment_v1_valida_y_los_campos_humanos_van_atados() -> None:
    v1 = {
        "study_id": "s",
        "tool": "RoB2",
        "domains": [{"domain": "Proceso de aleatorización", "judgment": "low"}],
        "overall": "low",
    }
    a = RoBAssessment.model_validate(v1)
    assert (a.schema_version, a.tool_version, a.overall_llm, a.overall_algorithm) == (2, None, None, None)
    assert a.domains[0].id is None and a.domains[0].quote_status == "none"
    with pytest.raises(ValidationError):
        RoBDomain(domain="D1", judgment="low", human_judgment="high")
    with pytest.raises(ValidationError):
        RoBAssessment(study_id="s", tool="RoB2", overall_human="high")
    ok = RoBAssessment(study_id="s", tool="RoB2", overall_human="high", overall_reason="r")
    assert ok.overall_human == "high"
```

Imports: `from typing import get_args`; `from revisia.schemas.rob import RoBAssessment, RoBDomain, RoBTool`.

Cambio de expectativa en `tests/test_rob.py:11`: la tupla pasa a `("RoB2", "ROBINS-I", "NewcastleOttawa", "NewcastleOttawaCaseControl", "AMSTAR2", "QUADAS-2")` (sin `GRADE`; D5).

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_schemas.py tests/test_rob.py -v -k rob`
Expected: FAIL (`GRADE` sigue en el Literal; `KeyError: 'NewcastleOttawaCaseControl'` en `TOOL_DOMAINS`).

- [ ] **Step 3: Implementar**: `revisia/schemas/rob.py` según Interfaces (docstring del módulo: GRADE califica certeza por desenlace y vuelve como etapa propia, D5); en `revisia/agents/rob.py` quitar la entrada `"GRADE"` de `TOOL_DOMAINS` y añadir `"NewcastleOttawaCaseControl": ["Selección", "Comparabilidad", "Exposición"]` (provisional hasta PR-E, que sustituye `TOOL_DOMAINS` por las especificaciones; comentario que lo diga); el comentario de la plantilla.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"`
Expected: PASS (`interop.render_robvis_csv` y `pipeline._rob_table_md` siguen leyendo `domain`/`judgment`/`overall`).

- [ ] **Step 5: Commit**

```bash
git add revisia/schemas/rob.py revisia/agents/rob.py protocols/_TEMPLATE/protocol.yml tests/test_schemas.py tests/test_rob.py
git commit -m "feat(schemas): RoBAssessment v2 por herramienta; RoBTool sin GRADE y con NOS casos-controles (D5)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 10: Especificaciones oficiales de RoB como datos (`revisia/schemas/rob_tools.py`, `revisia/rob/tools/*.yml`)

**Files:**
- Create: `revisia/rob/__init__.py` (docstring: paquete de datos y, en PR-E, `aggregate.py`), `revisia/rob/tools/RoB2.yml`, `ROBINS-I.yml`, `NewcastleOttawa.yml`, `NewcastleOttawaCaseControl.yml`, `AMSTAR2.yml`, `QUADAS-2.yml` (el nombre del fichero es el literal de `RoBTool`, para que la clave `rob/<tool>.yml` de `environment.prompt_templates` se derive de `protocol.rob_tool` sin tabla).
- Create: `revisia/schemas/rob_tools.py`.
- Test: `tests/test_rob_tools.py` (nuevo).

**Interfaces:**
- Consumes: `RoBTool` (Tarea 9), `sha256_text`, `yaml.safe_load`.
- Produces (§4.2 «RoBToolSpec», §4.4, D5; riesgo 5):
  - `class SignallingQuestion(BaseModel)` (`extra="forbid"`): `id: str`, `text: str` (paráfrasis propia, `max_length=200`), `answers: list[str]` (≥ 2).
  - `class RoBDomainSpec(BaseModel)` (`extra="forbid"`): `id: str`, `name: str`, `signalling_questions: list[SignallingQuestion] = []`, `scale: list[str] | None = None` (escala propia del dominio; si es `None`, la de la herramienta).
  - `class ApplicabilitySpec(BaseModel)` (`extra="forbid"`): `id: str`, `name: str`.
  - `class ToolSource(BaseModel)` (`extra="forbid"`): `citation: str`, `url: str`, `version: str`, `license_note: str` (por qué no se transcribe el texto oficial).
  - `class RoBToolSpec(BaseModel)` (`extra="forbid"`): `id: RoBTool`, `name: str`, `version: str`, `unit: Literal["domain", "item", "star"]`, `judgment_scale: list[str]` (≥ 2), `overall_scale: list[str] | None = None`, `domains: list[RoBDomainSpec]` (≥ 1), `aggregation: Literal["rob2", "robins_i", "amstar2", "nos_stars", "none"]`, `critical_items: list[str] = []`, `applicability: list[ApplicabilitySpec] = []`, `robvis_template: Literal["rob2", "robins_i", "quadas2", "generic"]`, `source: ToolSource`. Validadores: ids de dominios únicos; `critical_items` ⊆ ids de dominios; ids de preguntas únicos en toda la herramienta; `judgment_scale` y cada `scale` de dominio con ≥ 2 valores y sin repetidos; `aggregation == "none"` ⇒ `overall_scale is None`; `aggregation ∈ {rob2, robins_i, amstar2}` ⇒ `overall_scale` no nulo (son algoritmos que producen un juicio global); `nos_stars` admite `overall_scale` nulo (la suma de estrellas no se mapea a una escala salvo que la especificación la aporte). Métodos: `domain_ids -> tuple[str, ...]` (en orden), `scale_for(domain_id: str) -> tuple[str, ...]` (`KeyError` si el id no existe), `n_questions -> int`.
  - `TOOLS_DIR: Path = Path(__file__).resolve().parent.parent / "rob" / "tools"`; `tool_spec_path(tool: RoBTool) -> Path` = `TOOLS_DIR / f"{tool}.yml"`.
  - `load_tool_spec(tool: RoBTool) -> RoBToolSpec`: lee con `yaml.safe_load` (texto UTF-8) y valida; `ValueError` con el nombre del fichero si no valida (el YAML es del paquete: un error aquí es un error del motor, no del usuario).
  - `tool_spec_fingerprint() -> dict[str, str]`: `{"rob/<tool>.yml": sha256 del texto con CRLF→LF}` de los seis, ordenado por clave (PR-A lo mezcla en `environment.prompt_templates`; la misma regla de hash que `snapshot._text_sha256`).
  - **Contenido de los seis YAML** (estructura oficial; las preguntas llevan id oficial, paráfrasis corta propia en español y, en `source`, la referencia; **nunca el texto literal**):

| Fichero | `unit` | Dominios/ítems (ids, en orden) | Preguntas señalizadoras por dominio | `judgment_scale` | `overall_scale` | `aggregation` | `critical_items` | `applicability` | `robvis_template` | `source.version` |
|---|---|---|---|---|---|---|---|---|---|---|
| `RoB2.yml` | `domain` | `D1` aleatorización, `D2` desviaciones de la intervención prevista (efecto de la **asignación**), `D3` datos de resultado faltantes, `D4` medición del resultado, `D5` selección del resultado informado | `1.1–1.3` (3), `2.1–2.7` (7), `3.1–3.4` (4), `4.1–4.5` (5), `5.1–5.3` (3) = **22**; `answers: [Y, PY, PN, N, NI]` | `[low, some_concerns, high]` | igual | `rob2` | `[]` | `[]` | `rob2` | `RoB 2 · 2019-08-22` (Sterne et al., BMJ 2019; riskofbias.info; CC BY-NC-ND) |
| `ROBINS-I.yml` | `domain` | `D1` confusión, `D2` selección de participantes, `D3` clasificación de intervenciones, `D4` desviaciones de la intervención prevista, `D5` datos faltantes, `D6` medición de resultados, `D7` selección del resultado informado | `1.1–1.8` (8), `2.1–2.5` (5), `3.1–3.3` (3), `4.1–4.6` (6), `5.1–5.5` (5), `6.1–6.4` (4), `7.1–7.3` (3) = **34**; `answers: [Y, PY, PN, N, NI]` | `[low, moderate, serious, critical, no_information]` | igual | `robins_i` | `[]` | `[]` | `robins_i` | `ROBINS-I · 2016` (Sterne et al., BMJ 2016; riskofbias.info) |
| `NewcastleOttawa.yml` (cohortes) | `star` | `S1` representatividad de la cohorte expuesta, `S2` selección de la no expuesta, `S3` comprobación de la exposición, `S4` ausencia del desenlace al inicio, `C1` comparabilidad (diseño/análisis), `O1` evaluación del desenlace, `O2` seguimiento suficiente, `O3` adecuación del seguimiento = **8 ítems** | ninguna (`[]`): cada ítem es la pregunta; su `name` es la paráfrasis | `["0", "1"]` (estrellas) | `None` | `nos_stars` | `[]` | `[]` | `generic` | `NOS cohortes` (Wells et al., OHRI; URL de OHRI) |
| `NewcastleOttawaCaseControl.yml` | `star` | `S1` definición adecuada de los casos, `S2` representatividad de los casos, `S3` selección de los controles, `S4` definición de los controles, `C1` comparabilidad, `E1` comprobación de la exposición, `E2` mismo método para casos y controles, `E3` tasa de no respuesta = **8 ítems** | `[]` | `["0", "1"]`; `C1` `scale: ["0", "1", "2"]` | `None` | `nos_stars` | `[]` | `[]` | `generic` | `NOS casos-controles` (Wells et al., OHRI) |
| `AMSTAR2.yml` | `item` | `1`…`16` (los 16 ítems, con `name` = paráfrasis) | `[]` | `[yes, partial_yes, no]`; `scale` por ítem: `2, 4, 7, 8, 9` → `[yes, partial_yes, no]`; `11, 12, 15` → `[yes, no, no_meta_analysis]`; el resto → `[yes, no]` | `[high, moderate, low, critically_low]` | `amstar2` | `["2", "4", "7", "9", "11", "13", "15"]` | `[]` | `generic` | `AMSTAR 2 · 2017` (Shea et al., BMJ 2017; amstar.ca; CC BY-NC) |
| `QUADAS-2.yml` | `domain` | `patient_selection`, `index_test`, `reference_standard`, `flow_and_timing` | `1.1–1.3` (3), `2.1–2.2` (2), `3.1–3.2` (2), `4.1–4.4` (4) = **11**; `answers: [Y, N, U]` | `[low, high, unclear]` | `None` | `none` | `[]` | `patient_selection`, `index_test`, `reference_standard` | `quadas2` | `QUADAS-2 · 2011` (Whiting et al., Ann Intern Med 2011; bristol.ac.uk/quadas) |

En `NewcastleOttawa.yml` (cohortes) `C1` también lleva `scale: ["0", "1", "2"]` (máximo 9 estrellas en ambos formularios).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_rob_tools.py`:

```python
"""Especificaciones oficiales de RoB como datos (spec 2026-10-18 §4.2, §4.4; D5; riesgo 5)."""

from __future__ import annotations

from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from revisia.schemas.rob import RoBTool
from revisia.schemas.rob_tools import (
    TOOLS_DIR,
    RoBToolSpec,
    load_tool_spec,
    tool_spec_fingerprint,
    tool_spec_path,
)

HERRAMIENTAS = get_args(RoBTool)


@pytest.mark.parametrize("tool", HERRAMIENTAS)
def test_cada_herramienta_tiene_su_yaml_y_carga(tool: str) -> None:
    assert tool_spec_path(tool) == TOOLS_DIR / f"{tool}.yml"
    spec = load_tool_spec(tool)
    assert spec.id == tool
    assert spec.source.url.startswith("https://") and spec.source.version and spec.source.license_note
    for dominio in spec.domains:
        assert len(spec.scale_for(dominio.id)) >= 2
        for q in dominio.signalling_questions:
            assert q.id and 0 < len(q.text) <= 200 and len(q.answers) >= 2


def test_rob2_estructura_oficial() -> None:
    spec = load_tool_spec("RoB2")
    assert spec.domain_ids == ("D1", "D2", "D3", "D4", "D5")
    assert [len(d.signalling_questions) for d in spec.domains] == [3, 7, 4, 5, 3]
    assert spec.n_questions == 22
    assert spec.judgment_scale == ["low", "some_concerns", "high"] == spec.overall_scale
    assert (spec.unit, spec.aggregation, spec.robvis_template) == ("domain", "rob2", "rob2")
    assert spec.domains[1].signalling_questions[0].answers == ["Y", "PY", "PN", "N", "NI"]
    assert [q.id for q in spec.domains[0].signalling_questions] == ["1.1", "1.2", "1.3"]


def test_robins_i_estructura_oficial() -> None:
    spec = load_tool_spec("ROBINS-I")
    assert spec.domain_ids == tuple(f"D{i}" for i in range(1, 8))
    assert [len(d.signalling_questions) for d in spec.domains] == [8, 5, 3, 6, 5, 4, 3]
    assert spec.n_questions == 34
    assert spec.judgment_scale == ["low", "moderate", "serious", "critical", "no_information"]
    assert (spec.aggregation, spec.robvis_template) == ("robins_i", "robins_i")


@pytest.mark.parametrize(
    ("tool", "ids"),
    [
        ("NewcastleOttawa", ("S1", "S2", "S3", "S4", "C1", "O1", "O2", "O3")),
        ("NewcastleOttawaCaseControl", ("S1", "S2", "S3", "S4", "C1", "E1", "E2", "E3")),
    ],
)
def test_nos_ocho_items_y_nueve_estrellas(tool: str, ids: tuple[str, ...]) -> None:
    spec = load_tool_spec(tool)
    assert spec.domain_ids == ids
    assert (spec.unit, spec.aggregation, spec.overall_scale, spec.robvis_template) == (
        "star",
        "nos_stars",
        None,
        "generic",
    )
    assert spec.scale_for("C1") == ("0", "1", "2")
    assert sum(int(spec.scale_for(i)[-1]) for i in spec.domain_ids) == 9
    assert spec.n_questions == 0


def test_amstar2_dieciseis_items_siete_criticos() -> None:
    spec = load_tool_spec("AMSTAR2")
    assert spec.domain_ids == tuple(str(i) for i in range(1, 17))
    assert spec.critical_items == ["2", "4", "7", "9", "11", "13", "15"]
    assert {i for i in spec.domain_ids if "partial_yes" in spec.scale_for(i)} == {"2", "4", "7", "8", "9"}
    assert {i for i in spec.domain_ids if "no_meta_analysis" in spec.scale_for(i)} == {"11", "12", "15"}
    assert spec.overall_scale == ["high", "moderate", "low", "critically_low"]
    assert (spec.unit, spec.aggregation, spec.robvis_template) == ("item", "amstar2", "generic")


def test_quadas2_cuatro_dominios_tres_de_aplicabilidad_sin_global() -> None:
    spec = load_tool_spec("QUADAS-2")
    assert spec.domain_ids == ("patient_selection", "index_test", "reference_standard", "flow_and_timing")
    assert [len(d.signalling_questions) for d in spec.domains] == [3, 2, 2, 4]
    assert [a.id for a in spec.applicability] == ["patient_selection", "index_test", "reference_standard"]
    assert spec.judgment_scale == ["low", "high", "unclear"]
    assert (spec.overall_scale, spec.aggregation, spec.robvis_template) == (None, "none", "quadas2")


def _minima(**cambios) -> dict:
    base = {
        "id": "RoB2",
        "name": "x",
        "version": "v",
        "unit": "domain",
        "judgment_scale": ["low", "high"],
        "overall_scale": ["low", "high"],
        "domains": [{"id": "D1", "name": "a"}, {"id": "D2", "name": "b"}],
        "aggregation": "rob2",
        "robvis_template": "rob2",
        "source": {"citation": "c", "url": "https://x", "version": "v", "license_note": "n"},
    }
    base.update(cambios)
    return base


@pytest.mark.parametrize(
    "cambios",
    [
        {"domains": [{"id": "D1", "name": "a"}, {"id": "D1", "name": "b"}]},  # id repetido
        {"critical_items": ["D9"]},  # crítico inexistente
        {"judgment_scale": ["low"]},  # escala de un valor
        {"judgment_scale": ["low", "low"]},  # escala con repetidos
        {"overall_scale": None},  # rob2 produce un juicio global: necesita su escala
        {"aggregation": "none"},  # sin agregación no hay escala global (y aquí viene una)
        {"domains": [{"id": "D1", "name": "a", "scale": []}]},  # escala vacía
        {"extra": 1},  # clave desconocida
        {
            "domains": [
                {"id": "D1", "name": "a", "signalling_questions": [{"id": "1.1", "text": "t", "answers": ["Y", "N"]}]},
                {"id": "D2", "name": "b", "signalling_questions": [{"id": "1.1", "text": "t", "answers": ["Y", "N"]}]},
            ]
        },  # pregunta repetida entre dominios
    ],
)
def test_una_especificacion_incoherente_no_carga(cambios: dict) -> None:
    with pytest.raises(ValidationError):
        RoBToolSpec.model_validate(_minima(**cambios))


def test_scale_for_desconocido_es_key_error() -> None:
    with pytest.raises(KeyError):
        load_tool_spec("RoB2").scale_for("D9")


def test_fingerprint_cubre_los_seis_con_la_clave_rob_tool_yml() -> None:
    huella = tool_spec_fingerprint()
    assert set(huella) == {f"rob/{t}.yml" for t in HERRAMIENTAS}
    assert all(len(h) == 64 for h in huella.values())
    assert list(huella) == sorted(huella)


def test_los_yaml_son_mapas_planos_sin_anclas_ni_fusion() -> None:
    for tool in HERRAMIENTAS:
        texto = tool_spec_path(tool).read_text(encoding="utf-8")
        assert "&" not in texto and "<<" not in texto  # sin anclas: lo que se lee es lo que se ve
        assert isinstance(yaml.safe_load(texto), dict)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_rob_tools.py -v`
Expected: FAIL (`ModuleNotFoundError: revisia.schemas.rob_tools`).

- [ ] **Step 3: Implementar** `revisia/schemas/rob_tools.py` según Interfaces y escribir los seis YAML con la tabla de arriba. Cada YAML empieza con un comentario de cabecera: herramienta, versión, fuente (URL), y la frase «Las preguntas son paráfrasis propias con el id oficial; el texto literal está en la fuente (licencia <…>)». Las paráfrasis son del implementador (una línea por pregunta, en español, ≤ 200 caracteres), nunca una traducción palabra por palabra. El `name` de cada dominio/ítem en español; el `name` oficial en inglés puede ir entre paréntesis.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_rob_tools.py -v && uv run ruff check . && uv run black --check .`
Expected: PASS y lint limpio.

- [ ] **Step 5: Comprobar que los YAML viajan en el wheel** (hatchling incluye todo lo que hay bajo `revisia/`, como `prompts/*/v1.md`; PR-H lo fija en el CI):

```bash
uv build --wheel
uv run python -m zipfile -l dist/revisia-0.8.0-py3-none-any.whl | grep -c "revisia/rob/tools/"
rm -rf dist
```

Expected: `6` (y `dist/` borrado: está en `.gitignore`, pero no se deja basura).

- [ ] **Step 6: Commit**

```bash
git add revisia/rob revisia/schemas/rob_tools.py tests/test_rob_tools.py
git commit -m "feat(rob): seis especificaciones oficiales de RoB como datos y su cargador (D5, A12)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 11: Verificación v2 (`revisia/schemas/verification.py`)

**Files:**
- Modify: `revisia/schemas/verification.py` (`CitationCheck`, línea 15; `VerificationReport`, 33).
- Test: `tests/test_schemas.py` (añadir).

**Interfaces:**
- Consumes: `ARTIFACT_SCHEMA_VERSION`, `QuoteStatus`, `GroundingMode`.
- Produces (§4.2 «VerificationReport v2 / CitationCheck v2», D2, D15, D22):
  - `class JudgeInfo(BaseModel)`: `provider: str`, `model: str`.
  - `class UncitedClaim(BaseModel)`: `claim_index: int = Field(ge=0)`, `sentence: str = Field(max_length=300)`, `numbers: list[str]`.
  - `CitationCheck` v2 (todos con default para que la v1 valide): `index: int | None = None`, `claim_index: int | None = None`, `claim: str = Field(max_length=600)` (hoy sin tope; el contexto de 120 caracteres de la v1 cabe), `cited_id`, `exists_in_corpus`, `source_available: bool = True`, `numbers_in_claim: list[str] = []`, `numbers_missing: list[str] = []`, `grounded`, `support_quote: str | None = None`, `quote_status: QuoteStatus = "none"`, `verdict_reason: str | None = None`, `note`.
  - `VerificationReport` v2: `schema_version: int = ARTIFACT_SCHEMA_VERSION`, `stage`, `mode: GroundingMode | None = None` (v1 no lo guardaba), `judge: JudgeInfo | None = None`, `n_claims: int = 0`, `n_uncited_quantitative: int = 0`, `uncited_quantitative: list[UncitedClaim] = []`, `checks`, `hallucination_flagged`, `notes`; validador: `n_uncited_quantitative == len(uncited_quantitative)`; `mode == "judge"` ⇒ `judge is not None`. `flagged_indices()` y `recompute_flag()` no cambian (la regla de «cita marcada» es la misma; `grounded` se calcula con la regla de §4.2 en PR-D).

- [ ] **Step 1: Tests** — añadir a `tests/test_schemas.py`:

```python
def test_verification_report_v1_valida_sin_modo_ni_juez() -> None:
    v1 = {
        "stage": "reporte",
        "checks": [{"claim": "A", "cited_id": "rec-1", "exists_in_corpus": True, "grounded": True}],
        "hallucination_flagged": False,
    }
    report = VerificationReport.model_validate(v1)
    assert (report.schema_version, report.mode, report.judge, report.n_claims) == (2, None, None, 0)
    check = report.checks[0]
    assert (check.index, check.source_available, check.numbers_missing, check.quote_status) == (
        None,
        True,
        [],
        "none",
    )


def test_verification_report_v2_coherencia_de_modo_y_cifras_sin_cita() -> None:
    with pytest.raises(ValidationError):  # judge sin juez
        VerificationReport(stage="reporte", mode="judge")
    with pytest.raises(ValidationError):  # contador distinto de la lista
        VerificationReport(stage="reporte", n_uncited_quantitative=1)
    ok = VerificationReport(
        stage="reporte",
        mode="judge",
        judge=JudgeInfo(provider="zai", model="glm"),
        n_uncited_quantitative=1,
        uncited_quantitative=[UncitedClaim(claim_index=3, sentence="El 40 % …", numbers=["40"])],
    )
    assert ok.judge is not None and ok.judge.model == "glm"
    with pytest.raises(ValidationError):
        CitationCheck(claim="x" * 601, cited_id="r")
```

Imports: `JudgeInfo`, `UncitedClaim` desde `revisia.schemas.verification`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_schemas.py -v -k verification`
Expected: FAIL (`ImportError: JudgeInfo`).

- [ ] **Step 3: Implementar** según Interfaces. Docstring del módulo: los tres modos (D2), afirmaciones y no citas (D15), `source_available` y cifras (C2).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_schemas.py tests/test_verificador.py tests/test_grounding.py tests/test_audit_calidad.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/schemas/verification.py tests/test_schemas.py
git commit -m "feat(schemas): VerificationReport/CitationCheck v2: modo, juez, afirmaciones y cifras (D2, D15, D22)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 12: Efectos v2 (`revisia/schemas/effects.py`, `revisia/meta_analysis.py`)

**Files:**
- Modify: `revisia/schemas/effects.py` (`EffectInput`, línea 23; modelos nuevos).
- Modify: `revisia/meta_analysis.py` (`MetaAnalysisResult`, línea 96: solo `schema_version`).
- Test: `tests/test_schemas.py` (añadir).

**Interfaces:**
- Consumes: `ARTIFACT_SCHEMA_VERSION`.
- Produces (§4.2 «EffectInput v2 / EffectsFile v2 / MetaAnalysisResult v2 / ExcludedEffect», D16):
  - `EffectInput` gana `outcome: str | None = None` y `subgroup: str | None = None`. Aquí `outcome` es opcional porque `examples/demo-mini-review/effects.yml` y los tests de `meta_analyze` no lo traen; **PR-F** lo hace obligatorio en `protocol_files.EffectsFile` v2 con el mensaje de migración (§10.1), que es donde el usuario lo ve.
  - `RandomMethod = Literal["DL", "HKSJ"]`; `class MultiplePerStudy(BaseModel)`: `allowed: bool`, `justification: str` (no vacía si `allowed`). Los consume `protocol_files.EffectsFile` v2 en PR-F (`protocol_files.py` es «solo F», §15).
  - `ExcludedReason = Literal["not_included", "unit_of_analysis", "invalid"]`; `class ExcludedEffect(BaseModel)`: `study_id: str`, `outcome: str | None = None`, `reason: ExcludedReason`, `detail: str | None = None`. `class ExcludedEffectsFile(BaseModel)`: `schema_version: int = ARTIFACT_SCHEMA_VERSION`, `excluded: list[ExcludedEffect] = []`, `included_without_effect: list[str] = []` (`08_meta/excluded_effects.json`, §4.1).
  - `class PredictionInterval(BaseModel)`: `low: float`, `high: float`, `df: int = Field(ge=1)`. `class DuplicateEffect(BaseModel)`: `study_ids: list[str]` (≥ 2), `yi: float`, `vi: float`.
  - `MetaAnalysisResult.schema_version: int = ARTIFACT_SCHEMA_VERSION` (`meta_analysis.py`). La forma por desenlace (`outcomes: [...]`, PI, subgrupos, duplicados) no es aditiva y la hace PR-F sobre su propio módulo; aquí viajan los modelos hoja que F y G comparten.

- [ ] **Step 1: Tests** — añadir a `tests/test_schemas.py`:

```python
def test_effect_input_v2_outcome_y_subgrupo_opcionales_en_el_modelo() -> None:
    e = EffectInput(study_id="s", yi=0.1, vi=0.01)
    assert (e.outcome, e.subgroup) == (None, None)
    assert EffectInput(study_id="s", yi=0.1, vi=0.01, outcome="recall", subgroup="c1").outcome == "recall"


def test_modelos_hoja_del_meta_analisis_v2() -> None:
    assert set(get_args(RandomMethod)) == {"DL", "HKSJ"}
    with pytest.raises(ValidationError):
        MultiplePerStudy(allowed=True, justification="")
    assert MultiplePerStudy(allowed=False, justification="").allowed is False
    excl = ExcludedEffectsFile(
        excluded=[ExcludedEffect(study_id="s", outcome="o", reason="not_included")],
        included_without_effect=["t"],
    )
    assert excl.schema_version == 2
    with pytest.raises(ValidationError):
        ExcludedEffect(study_id="s", reason="porque")
    with pytest.raises(ValidationError):
        PredictionInterval(low=0.0, high=1.0, df=0)
    with pytest.raises(ValidationError):
        DuplicateEffect(study_ids=["solo"], yi=0.0, vi=1.0)


def test_meta_analysis_result_lleva_schema_version_2() -> None:
    resultado = meta_analyze(
        [EffectInput(study_id=f"s{i}", yi=0.1 * i, vi=0.04) for i in range(1, 4)], "precomputed"
    )
    assert resultado.schema_version == 2
```

Imports: de `revisia.schemas.effects`: `DuplicateEffect, EffectInput, ExcludedEffect, ExcludedEffectsFile, MultiplePerStudy, PredictionInterval, RandomMethod`; `from revisia.meta_analysis import meta_analyze`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_schemas.py -v -k "effect or meta_analysis"`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implementar** según Interfaces (en `effects.py` los modelos nuevos van tras `EffectInput`; docstring con D16 y Cochrane Handbook §23.3).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_schemas.py tests/test_meta_analysis.py tests/test_interop.py tests/test_auditor_meta_y_estados.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/schemas/effects.py revisia/meta_analysis.py tests/test_schemas.py
git commit -m "feat(schemas): efectos v2: outcome/subgroup, MultiplePerStudy, ExcludedEffect, PI y duplicados (D16)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 13: Panel y resultado del benchmark (`revisia/schemas/benchmark.py`)

**Files:**
- Create: `revisia/schemas/benchmark.py`.
- Test: `tests/test_benchmark_schemas.py` (nuevo).

**Interfaces:**
- Consumes: `ProviderConfig` y `MODEL_NAME_PATTERN` (`revisia.llm.registry`), `ScreeningMetrics` (`revisia.metrics`), `Environment`, `ARTIFACT_SCHEMA_VERSION` (Tarea 5), `rechazar_claves_de_fusion` (`revisia.config`). `revisia.metrics` importa `revisia.schemas.screening`, así que este módulo **no se exporta** desde `revisia/schemas/__init__.py` (evita el ciclo al importar el paquete).
- Produces (§4.2 «BenchmarkPanel / BenchmarkResult», D6, D23):
  - `class BenchmarkCell(ProviderConfig)` (`extra="forbid"`): `name: str` (único en el panel; `^[a-z0-9][a-z0-9_-]{0,39}$`, porque es parte del nombre de carpeta `runs/<celda>-r<k>/`); hereda `provider`, `model`, `temperature = 0.0`, `top_p`, `seed`, `effort`. `to_provider_config() -> ProviderConfig`.
  - `class BenchmarkPanel(BaseModel)` (`extra="forbid"`): `name: str`, `replicas: int = Field(default=1, ge=1)`, `cells: list[BenchmarkCell]` (≥ 1; nombres únicos).
  - `load_panel(path: str | Path) -> BenchmarkPanel`: UTF-8, `rechazar_claves_de_fusion(fh, "panel.yml")`, `yaml.safe_load`, raíz mapa, validación. Todo fallo (un `yaml.YAMLError`, incluida la `ConstructorError` de las claves de fusión; una raíz que no es mapa; un `ValidationError`) se relanza como `ValueError(f"{path}: {exc}")` con `from exc`: un solo tipo de error para el CLI de PR-F (rc 2).
  - `class BenchmarkProtocolInfo(BaseModel)`: `slug: str`, `corpus_sha256: str`, `gold_sha256: str`, `n_records: int = Field(ge=0)`, `n_gold_positives: int = Field(ge=0)`.
  - `class BenchmarkCellResult(BaseModel)`: `cell: str`, `replica: int = Field(ge=1)`, `run_dir: str` (relativa a la carpeta del benchmark, con `/`), `metrics: ScreeningMetrics`, `recall_ci95: tuple[float, float] | None = None` (Wilson; `None` si el recall es indefinido), `models_used: list[str] = []`, `n_calls: int = Field(default=0, ge=0)`, `n_failed_records: int = Field(default=0, ge=0)`; validador: `recall_ci95` ⇒ `0 ≤ lo ≤ hi ≤ 1`.
  - `class BenchmarkResult(BaseModel)`: `schema_version: int = ARTIFACT_SCHEMA_VERSION`, `protocol: BenchmarkProtocolInfo`, `environment: Environment`, `cells: list[BenchmarkCellResult]`, `created_utc: str = Field(default_factory=utc_now_iso)`; validador: `(cell, replica)` únicos.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_benchmark_schemas.py`:

```python
"""Panel y resultado de `revisia benchmark` (spec 2026-10-18 §4.2; D6, D23). Solo modelos en PR-0."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from revisia.llm.registry import ProviderConfig
from revisia.metrics import ScreeningMetrics
from revisia.schemas.artifacts import Environment
from revisia.schemas.benchmark import (
    BenchmarkCell,
    BenchmarkCellResult,
    BenchmarkPanel,
    BenchmarkProtocolInfo,
    BenchmarkResult,
    load_panel,
)

PANEL = """
name: panel-demo
replicas: 2
cells:
  - name: fake-a
    provider: fake
    model: fake-a
  - name: glm
    provider: zai
    model: glm-4.6
    temperature: 0.0
"""


def test_panel_carga_desde_yaml_y_las_celdas_son_provider_config(tmp_path: Path) -> None:
    path = tmp_path / "panel.yml"
    path.write_text(PANEL, encoding="utf-8")
    panel = load_panel(path)
    assert (panel.name, panel.replicas, [c.name for c in panel.cells]) == ("panel-demo", 2, ["fake-a", "glm"])
    cfg = panel.cells[1].to_provider_config()
    assert isinstance(cfg, ProviderConfig) and not isinstance(cfg, BenchmarkCell)
    assert (cfg.provider, cfg.model, cfg.temperature, cfg.effort) == ("zai", "glm-4.6", 0.0, None)


@pytest.mark.parametrize(
    "crudo",
    [
        {"name": "p", "cells": []},  # sin celdas
        {"name": "p", "replicas": 0, "cells": [{"name": "a", "provider": "fake", "model": "m"}]},
        {"name": "p", "cells": [{"name": "a", "provider": "fake", "model": "m"}] * 2},  # repetida
        {"name": "p", "cells": [{"name": "A b", "provider": "fake", "model": "m"}]},  # nombre no apto
        {"name": "p", "cells": [{"name": "a", "provider": "fake", "model": "m", "x": 1}]},  # extra
        {"name": "p", "cells": [{"name": "a", "provider": "fake", "model": "-x"}]},  # patrón de modelo
    ],
)
def test_panel_invalido_no_valida(crudo: dict) -> None:
    with pytest.raises(ValidationError):
        BenchmarkPanel.model_validate(crudo)


def test_load_panel_rechaza_claves_de_fusion(tmp_path: Path) -> None:
    path = tmp_path / "panel.yml"
    path.write_text("base: &b {provider: fake, model: m}\nname: p\ncells:\n  - {<<: *b, name: a}\n", "utf-8")
    with pytest.raises(ValueError, match="fusión"):
        load_panel(path)


def _entorno() -> Environment:
    return Environment(
        engine_version="0.9.0",
        python_version="3.13.0",
        python_implementation="CPython",
        platform="x",
        created_utc="2026-10-18T00:00:00+00:00",
    )


def _celda(**cambios) -> dict:
    base = {
        "cell": "fake-a",
        "replica": 1,
        "run_dir": "runs/fake-a-r1",
        "metrics": ScreeningMetrics(n=10, tp=4, fp=1, fn=1, tn=4, recall=0.8).model_dump(),
        "recall_ci95": (0.376, 0.964),
    }
    base.update(cambios)
    return base


def test_benchmark_result_celdas_unicas_e_ic_acotado() -> None:
    protocolo = BenchmarkProtocolInfo(slug="s", corpus_sha256="c" * 64, gold_sha256="g" * 64, n_records=10, n_gold_positives=5)
    ok = BenchmarkResult(protocol=protocolo, environment=_entorno(), cells=[BenchmarkCellResult(**_celda())])
    assert ok.schema_version == 2 and ok.created_utc
    with pytest.raises(ValidationError):  # (celda, réplica) repetida
        BenchmarkResult(protocol=protocolo, environment=_entorno(), cells=[BenchmarkCellResult(**_celda())] * 2)
    with pytest.raises(ValidationError):
        BenchmarkCellResult(**_celda(recall_ci95=(0.9, 0.5)))
    with pytest.raises(ValidationError):
        BenchmarkCellResult(**_celda(recall_ci95=(0.0, 1.5)))
    assert BenchmarkCellResult(**_celda(recall_ci95=None)).recall_ci95 is None
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_benchmark_schemas.py -v`
Expected: FAIL (`ModuleNotFoundError: revisia.schemas.benchmark`).

- [ ] **Step 3: Implementar** `revisia/schemas/benchmark.py` según Interfaces (docstring con D6 y D23: corridas `kind: benchmark`, corpus congelado, el estudio vive fuera del motor).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_benchmark_schemas.py tests/test_schemas.py tests/test_metrics.py -v && uv run python -c "import revisia.schemas, revisia.schemas.benchmark"`
Expected: PASS; el import no cicla.

- [ ] **Step 5: Commit**

```bash
git add revisia/schemas/benchmark.py tests/test_benchmark_schemas.py
git commit -m "feat(schemas): BenchmarkPanel, BenchmarkResult y load_panel (D6, D23)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 14: `normalize_doi` (`revisia/ingest/doi.py`)

**Files:**
- Create: `revisia/ingest/doi.py`.
- Test: `tests/test_doi.py` (nuevo).

**Interfaces:**
- Consumes: `urllib.parse.unquote`, `re`.
- Produces (§6, D19; **sin cablear**: `SearchRecord.doi`, los backends, `manual_import` y `dedup` lo adoptan en PR-B):
  - `DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")`.
  - `normalize_doi(value: object) -> str | None`: `None` si `value` no es `str` o está vacío tras `strip()`; `unquote` (URL-decode); quita, sin distinguir mayúsculas y las veces que haga falta al principio, `https?://(dx\.)?doi\.org/`, `doi:` (con espacios opcionales tras los dos puntos) e `info:doi/`; `lower()`; quita puntuación final `.,;)]`; devuelve el resultado si casa con `DOI_RE`, si no `None`.
  - `doi_url(doi: str) -> str` → `f"https://doi.org/{doi}"` (sin re-normalizar: recibe uno ya normalizado).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_doi.py`:

```python
"""La única normalización de DOI del paquete (spec 2026-10-18 §6, D19; auditoría A4)."""

from __future__ import annotations

import pytest

from revisia.ingest.doi import DOI_RE, doi_url, normalize_doi


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("10.1000/abc", "10.1000/abc"),
        ("10.1000/ABC", "10.1000/abc"),
        ("https://doi.org/10.1000/ABC", "10.1000/abc"),  # la evidencia de A4
        ("HTTPS://DOI.ORG/10.1000/abc", "10.1000/abc"),
        ("http://dx.doi.org/10.1000/abc", "10.1000/abc"),
        ("doi:10.1000/abc", "10.1000/abc"),
        ("DOI: 10.1000/abc", "10.1000/abc"),
        ("info:doi/10.1000/abc", "10.1000/abc"),
        ("https://doi.org/10.1000%2Fabc", "10.1000/abc"),  # URL-encoded
        ("  10.1000/abc.  ", "10.1000/abc"),
        ("10.1000/abc).", "10.1000/abc"),
        ("10.1000/abc;", "10.1000/abc"),
        ("10.1000/abc]", "10.1000/abc"),
        ("10.1016/j.jclinepi.2021.03.001", "10.1016/j.jclinepi.2021.03.001"),
        ("10.1000/a(b)c", "10.1000/a(b)c"),  # paréntesis interno se conserva
    ],
)
def test_normalize_doi_tabla(crudo: str, esperado: str) -> None:
    assert normalize_doi(crudo) == esperado


@pytest.mark.parametrize(
    "no_doi",
    ["", "   ", "abc", "11.1000/abc", "10.12/abc", "10.1000/", "10.1000", "PMC123", "https://example.org/x", None, 10.1, ["10.1000/abc"]],
)
def test_normalize_doi_lo_que_no_es_doi_es_none(no_doi: object) -> None:
    assert normalize_doi(no_doi) is None


def test_normalize_doi_es_idempotente() -> None:
    for crudo in ("https://doi.org/10.1000/ABC", "doi:10.1000/abc", "10.1000/abc"):
        una = normalize_doi(crudo)
        assert una is not None and normalize_doi(una) == una


def test_doi_url_y_patron() -> None:
    assert doi_url("10.1000/abc") == "https://doi.org/10.1000/abc"
    assert DOI_RE.match("10.1000/abc") and not DOI_RE.match("10.1000/a b")
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_doi.py -v`
Expected: FAIL (`ModuleNotFoundError: revisia.ingest.doi`).

- [ ] **Step 3: Implementar** `revisia/ingest/doi.py` según Interfaces (docstring: los cuatro normalizadores de hoy que sustituye, con sus rutas: `busqueda._normalize_doi`, `open_backends._doi`, `search_backends`/`ncbi` `lower().strip()`, `manual_import._record_id`; A4). No tocar `revisia/ingest/__init__.py` más que para exportar `normalize_doi` y `doi_url`.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_doi.py tests/test_search_multibase.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/ingest/doi.py revisia/ingest/__init__.py tests/test_doi.py
git commit -m "feat(ingest): normalize_doi y doi_url, la única normalización de DOI (D19, A4); sin cablear" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 15: `ScriptedProvider` ampliado y `fetch_disponible_largo` (`tests/fakes.py`)

**Files:**
- Modify: `tests/fakes.py` (`ScriptedProvider.__init__`, línea 71; `_llamar`, 102; `structured`, 126; función nueva tras `fetch_no_disponible`, 153).
- Modify: `tests/test_reanudacion.py:99` (`"RuntimeError: 429 Too Many Requests"` → `"TransientCallError: 429 Too Many Requests"`: la interrupción registra el nombre de la clase y ese test usa `ScriptedProvider(fail_at=1)`). `tests/test_reanudacion.py:209` **no** cambia: lanza un `RuntimeError` explícito, no el del doble. Hallazgo del redactor de PR-A, 2026-10-19.
- Test: `tests/test_fakes.py` (añadir).

**Interfaces:**
- Consumes: `TransientCallError`, `DeterministicCallError` (Tarea 2); `GroundingVerdict` (`revisia.rag.grounding`); `_ExtractionOut` (`revisia.agents.extraccion`) y `_RoBOut` (`revisia.agents.rob`) por identidad de clase (son privados del agente; si PR-C/PR-E los cambian, actualizan este import en su PR).
- Produces (§4.4 «tests/fakes.py»; los consumen PR-A, PR-C, PR-D, PR-E y PR-F):
  - `ScriptedProvider.__init__` gana, como argumentos de palabra clave: `fail_deterministic_at: int | None = None` (número de llamada, desde 1, que lanza `DeterministicCallError("400 Bad Request: el contexto excede el límite del modelo", attempts=1)`; `ValueError` si `< 1`; puede convivir con `fail_at` en llamadas distintas, y si coinciden gana el determinista), `judge: Mapping[str, bool] | None = None`, `extraccion: Mapping[str, str | None] | None = None`, `rob: Mapping[str, str] | None = None`.
  - `fail_at` pasa a lanzar `TransientCallError("429 Too Many Requests")` (subclase de `RuntimeError`: los tests de la Ola 1 con `pytest.raises(RuntimeError, match="429")` siguen pasando).
  - `structured` por schema: (1) etiqueta de cribado, como hoy; (2) `schema is GroundingVerdict` y `judge` no es `None`: busca cada palabra de `judge` (sin distinguir mayúsculas) en el texto entre `AFIRMACIÓN:` y `TEXTO FUENTE CITADO:` del prompt (o en todo el prompt si no están); gana la primera del dict que aparezca; `grounded` = su valor, `support_quote` = la primera frase de la fuente si `grounded`, `reason = f"guion: {palabra}"`; sin coincidencia, `grounded=False` y `reason="guion: sin palabra clave"` (fail-closed). Con `judge=None` se fabrica como hoy (`grounded=True`): PR-D decide si cambia ese default; (3) `schema is _ExtractionOut` y `extraccion` no es `None`: `fields = [{"key": k, "value": v, "source_quote": v, "found": v is not None, "confidence": 0.9} …]` en el orden del dict; (4) `schema is _RoBOut` y `rob` no es `None`: `domains = [{"domain": d, "judgment": j, "rationale": f"guion: {j}", "support_quote": None} …]` para cada clave distinta de `"overall"`; `overall = rob.get("overall", "unclear")`; (5) lo demás, `_fabricate_model` como hoy. La meta sigue siendo `_meta(req, obj.model_dump_json())`.
  - `fetch_disponible_largo(n_chars: int) -> Callable[[SearchRecord], FullText]`: `fetch_fn` cuyo texto tiene **exactamente** `n_chars` caracteres (`ValueError` si `n_chars < 1`): párrafos `"Párrafo {k} del texto completo de prueba de «{title}»: {k * 7} participantes."` unidos con `"\n\n"` hasta cubrir `n_chars`, cortado a `n_chars`. `available=True`, `source_url` como `fetch_disponible`. Lo usan los tests de D20 (recorte) y D15 (ventana por párrafos).

- [ ] **Step 1: Tests que fallan** — añadir al final de `tests/test_fakes.py`:

```python
# ── Ola 2 (spec 2026-10-18 §4.4): fallo determinista, juez, extracción y RoB con guion ──


def test_fail_at_es_transitorio_y_fail_deterministic_at_determinista() -> None:
    from revisia.llm.base import DeterministicCallError, TransientCallError

    transitorio = ScriptedProvider(fail_at=1)
    with pytest.raises(TransientCallError, match="429"):
        _cribar(transitorio, _rec("a", "alfa"))
    determinista = ScriptedProvider(fail_deterministic_at=2)
    _cribar(determinista, _rec("a", "alfa"))
    with pytest.raises(DeterministicCallError, match="400") as exc:
        _cribar(determinista, _rec("b", "beta"))
    assert exc.value.attempts == 1
    _cribar(determinista, _rec("c", "gamma"))  # la 3.ª responde con normalidad
    assert determinista.calls == 3
    with pytest.raises(ValueError, match="desde 1"):
        ScriptedProvider(fail_deterministic_at=0)


def test_judge_por_palabra_clave_es_fail_closed() -> None:
    from revisia.rag.grounding import GroundingVerdict, make_provider_judge

    juez = make_provider_judge(ScriptedProvider(judge={"recall 0.98": True, "mortalidad": False}))
    fuente = "We evaluate LLM screening with recall 0.98. Workload fell 60%."
    assert juez("El cribado alcanzó recall 0.98 [rec-1].", fuente).grounded is True
    assert juez("Redujo la mortalidad en sepsis [rec-1].", fuente).grounded is False
    sin_palabra = juez("Una afirmación cualquiera [rec-1].", fuente)
    assert sin_palabra.grounded is False and "sin palabra clave" in sin_palabra.reason
    # La palabra se busca en la afirmación, no en la fuente: "recall 0.98" está en la fuente
    # pero no en la afirmación.
    assert juez("Afirmación sin cifras [rec-1].", fuente).grounded is False
    # Sin guion, el veredicto fabricado sigue siendo el de hoy (grounded=True); PR-D lo revisa.
    sin_guion = make_provider_judge(ScriptedProvider())("x", "y")
    assert isinstance(sin_guion, GroundingVerdict) and sin_guion.grounded is True


def test_extraccion_por_clave_rellena_el_formulario() -> None:
    proveedor = ScriptedProvider(extraccion={"n": "240", "edad": None})
    extraccion, _ = extract_record(
        proveedor, record=_rec("r", "T"), form_fields=[{"key": "n"}, {"key": "edad"}]
    )
    assert extraccion.fields["n"].value == "240" and extraccion.fields["n"].status == "needs_review"
    assert extraccion.fields["edad"].value is None and extraccion.fields["edad"].status == "not_found"


def test_rob_por_dominio_y_global() -> None:
    from revisia.agents.rob import assess_rob

    proveedor = ScriptedProvider(rob={"Proceso de aleatorización": "high", "overall": "high"})
    assessment, _ = assess_rob(proveedor, tool="RoB2", record=_rec("r", "T"))
    assert [(d.domain, d.judgment) for d in assessment.domains] == [("Proceso de aleatorización", "high")]
    assert assessment.overall == "high"


def test_fetch_disponible_largo_tiene_exactamente_n_caracteres() -> None:
    from fakes import fetch_disponible_largo

    rec = _rec("10.1/a", "Título A")
    for n in (1, 50, 1_000, 120_001):
        ft = fetch_disponible_largo(n)(rec)
        assert ft.available is True and len(ft.text) == n
    assert "\n\n" in fetch_disponible_largo(1_000)(rec).text  # párrafos para la ventana de D15
    with pytest.raises(ValueError):
        fetch_disponible_largo(0)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_fakes.py -v`
Expected: FAIL (`TypeError: unexpected keyword argument 'fail_deterministic_at'`).

- [ ] **Step 3: Implementar** en `tests/fakes.py` según Interfaces. Actualizar la docstring del módulo (qué pista usa cada guion) y la de `ScriptedProvider` (atributos nuevos).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_fakes.py tests/test_reanudacion.py tests/test_hitl_pipeline.py tests/test_pipeline_fake.py -v`
Expected: PASS (los tests de la Ola 1 que esperan `RuntimeError` con `429` siguen en verde).

- [ ] **Step 5: Commit**

```bash
git add tests/fakes.py tests/test_fakes.py
git commit -m "test(fakes): ScriptedProvider con fallo determinista, juez, extracción y RoB con guion; fetch_disponible_largo" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 16: Sonda del CLI `claude` (`scripts/sonda_claude_cli.py`)

**Files:**
- Create: `scripts/sonda_claude_cli.py` (stdlib puro; sin importar `revisia`; compatible con **Python 3.11**, que es el `python` del sistema del arquitecto).
- Create: `docs/superpowers/sondas/README.md` (qué es una sonda, cómo se ejecuta, qué se redacta, que su salida la commitea el arquitecto).
- Test: `tests/test_sonda_claude_cli.py` (nuevo).

**Interfaces:**
- Consumes: `subprocess.run`, `shutil.which`, `json`, `re`, `argparse`, `datetime`, `pathlib`.
- Produces (D11; §4.4; lo ejecuta el arquitecto antes de PR-A, §14.2 paso 0):
  - CLI: `python scripts/sonda_claude_cli.py [--cli claude] [--model sonnet] [--out docs/superpowers/sondas/<YYYY-MM-DD>-claude-cli.md] [--timeout 120]`. Siempre termina con rc 0 y escribe el informe; los fallos quedan dentro del informe (Review Focus 5).
  - Pasos, en orden: `<cli> --version`; `<cli> --help`; una llamada `-p` con `--output-format json --model <model> --no-session-persistence --tools "" --strict-mcp-config --json-schema <SCHEMA>` y, **solo si `--help` lo anuncia**, `--safe-mode`; prompt por stdin: `"Responde exactamente con respuesta='hola' y numero=7."`. `SCHEMA = {"type": "object", "properties": {"respuesta": {"type": "string"}, "numero": {"type": "integer"}}, "required": ["respuesta", "numero"], "additionalProperties": false}` (dos campos, D11). `cwd` temporal vacío, como el proveedor.
  - Funciones puras, probadas: `detect_flags(help_text: str) -> dict[str, bool]` con las claves `--safe-mode`, `--tools`, `--json-schema`, `--max-turns`, `--max-budget-usd`, `--bare`, `--strict-mcp-config`, `--no-session-persistence` (una bandera está anunciada si aparece como palabra completa en el `--help`); `parse_version(text: str) -> str | None` (primer `\d+\.\d+\.\d+`); `locate_structured(data: object, schema: dict) -> dict` → `{"where": "result" | "structured_output" | "<otra clave>" | None, "valid": bool}`: busca en `result` (si es texto, intenta `json.loads`; si es dict, tal cual) y en cualquier otra clave de primer nivel cuyo valor sea un dict con las claves `required` del schema; `valid` = tiene las dos claves con los tipos del schema; `redact(text: str, secrets: Iterable[str]) -> str`: sustituye cada valor no vacío de `secrets` por `<redacted>` y además `sk-[A-Za-z0-9_-]{16,}` y `Bearer \S+`; `render_report(*, cli, version, flags, help_text, command, returncode, stdout, stderr, located, date) -> str` (Markdown con secciones fijas y estas cadenas exactas, que los tests buscan: `## Versión`; `## Flags anunciados` (tabla `| flag | anunciado |` con `sí`/`no`); `## --help crudo` (fenced `text`); `## Comando` (fenced; el schema inline se sustituye por `<schema>` si pasa de 300 caracteres); `## Código de salida` (`None` si el proceso no llegó a correr); `## stdout crudo` (fenced `json` si `json.loads` funciona, `text` si no); `## stderr` (fenced; incluye el nombre de la excepción, p. ej. `FileNotFoundError`, cuando la hubo); `## Dónde viene el objeto validado` con las líneas `- clave: `<where>`` (o `- clave: ninguna`), `- válido: sí` / `- válido: no` y `- claves de primer nivel: …`; `## Para PR-A` con la línea `MIN_CLI_VERSION candidata: <versión>` si `--safe-mode`, `--tools` y `--json-schema` están anunciados y, si no, `esta versión no sirve: actualiza el CLI (npm i -g @anthropic-ai/claude-code@latest)`).
  - `main(argv: list[str] | None = None) -> int`: orquesta, redacta con `secrets = [os.environ.get(v, "") for v in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")]`, crea la carpeta de salida y escribe UTF-8 con LF; imprime la ruta. `FileNotFoundError` del CLI → informe con `returncode=None` y el error en «stderr»; `TimeoutExpired` igual. Sin `--bare` (rompe la suscripción, §2).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_sonda_claude_cli.py`:

```python
"""La sonda del CLI `claude` registra lo que hay sin invocar el CLI real (D11; spec §4.4)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

RUTA = Path(__file__).resolve().parent.parent / "scripts" / "sonda_claude_cli.py"


def _modulo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sonda_claude_cli", RUTA)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


HELP_NPM = "Usage: claude [options]\n  --json-schema <schema>\n  --max-budget-usd <n>\n  --bare\n  --tools <list>\n"
HELP_COMPLETO = HELP_NPM + "  --safe-mode\n  --max-turns <n>\n  --strict-mcp-config\n  --no-session-persistence\n"


def test_el_script_no_importa_revisia_y_corre_en_311() -> None:
    texto = RUTA.read_text(encoding="utf-8")
    assert "import revisia" not in texto and "from revisia" not in texto
    assert "from __future__ import annotations" in texto
    # Sin sintaxis exclusiva de 3.12+: ni `type X =` ni genéricos PEP 695.
    assert "\ntype " not in texto and "def main[" not in texto


def test_detect_flags_distingue_el_shim_npm_del_cli_completo() -> None:
    sonda = _modulo()
    npm = sonda.detect_flags(HELP_NPM)
    assert (npm["--json-schema"], npm["--max-budget-usd"], npm["--bare"], npm["--tools"]) == (True, True, True, True)
    assert (npm["--safe-mode"], npm["--max-turns"]) == (False, False)
    assert sonda.detect_flags(HELP_COMPLETO)["--safe-mode"] is True
    assert sonda.detect_flags("--safe-modern")["--safe-mode"] is False  # palabra completa


def test_parse_version() -> None:
    sonda = _modulo()
    assert sonda.parse_version("2.1.126 (Claude Code)") == "2.1.126"
    assert sonda.parse_version("sin versión") is None


def test_locate_structured_en_result_texto_dict_u_otra_clave() -> None:
    sonda = _modulo()
    schema = {"required": ["respuesta", "numero"], "properties": {"respuesta": {"type": "string"}, "numero": {"type": "integer"}}}
    assert sonda.locate_structured({"result": '{"respuesta": "hola", "numero": 7}'}, schema) == {"where": "result", "valid": True}
    assert sonda.locate_structured({"result": {"respuesta": "hola", "numero": 7}}, schema) == {"where": "result", "valid": True}
    assert sonda.locate_structured({"result": "texto", "structured_output": {"respuesta": "hola", "numero": 7}}, schema) == {"where": "structured_output", "valid": True}
    assert sonda.locate_structured({"result": '{"respuesta": "hola", "numero": "7"}'}, schema) == {"where": "result", "valid": False}
    assert sonda.locate_structured({"result": "nada"}, schema) == {"where": None, "valid": False}
    assert sonda.locate_structured("no es json", schema) == {"where": None, "valid": False}


def test_redact_tapa_tokens_y_valores_del_entorno() -> None:
    sonda = _modulo()
    texto = "Authorization: Bearer abc.def token=sk-ant-0123456789abcdefXYZ otra cosa"
    assert "abc.def" not in sonda.redact(texto, ["abc.def"]) and "sk-ant" not in sonda.redact(texto, [])
    assert sonda.redact("limpio", ["", None]) == "limpio"


def _fake_run(respuestas: dict[str, subprocess.CompletedProcess | Exception]):
    def _run(cmd, **_kwargs):
        clave = "-p" if "-p" in cmd else cmd[1]
        salida = respuestas[clave]
        if isinstance(salida, Exception):
            raise salida
        return salida

    return _run


def _ok(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


@pytest.mark.parametrize("help_text", [HELP_NPM, HELP_COMPLETO])
def test_main_escribe_el_informe_y_solo_usa_safe_mode_si_se_anuncia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, help_text: str
) -> None:
    sonda = _modulo()
    comandos: list[list[str]] = []
    respuestas = {
        "--version": _ok("2.1.126 (Claude Code)"),
        "--help": _ok(help_text),
        "-p": _ok(json.dumps({"result": '{"respuesta": "hola", "numero": 7}', "total_cost_usd": 0.0, "usage": {}})),
    }
    fake = _fake_run(respuestas)

    def _run(cmd, **kwargs):
        comandos.append(list(cmd))
        return fake(cmd, **kwargs)

    monkeypatch.setattr(sonda.subprocess, "run", _run)
    monkeypatch.setattr(sonda.shutil, "which", lambda _c: "C:/npm/claude.CMD")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok-secreto-123")
    out = tmp_path / "sondas" / "x.md"
    assert sonda.main(["--out", str(out), "--model", "sonnet"]) == 0
    informe = out.read_text(encoding="utf-8")
    llamada = next(c for c in comandos if "-p" in c)
    assert ("--safe-mode" in llamada) is ("--safe-mode" in help_text)
    assert "--json-schema" in llamada and "--bare" not in llamada
    assert "--tools" in llamada and llamada[llamada.index("--tools") + 1] == ""
    assert "2.1.126" in informe and "## Dónde viene el objeto validado" in informe
    assert "`result`" in informe and "válido: sí" in informe
    assert "tok-secreto-123" not in informe
    esperado = "MIN_CLI_VERSION candidata: 2.1.126" if "--safe-mode" in help_text else "no sirve"
    assert esperado in informe


def test_main_con_cli_ausente_o_json_invalido_escribe_el_informe_igual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sonda = _modulo()
    monkeypatch.setattr(sonda.shutil, "which", lambda _c: None)
    monkeypatch.setattr(sonda.subprocess, "run", _fake_run({"--version": FileNotFoundError("claude"), "--help": FileNotFoundError("claude"), "-p": FileNotFoundError("claude")}))
    out = tmp_path / "a.md"
    assert sonda.main(["--out", str(out)]) == 0
    assert "FileNotFoundError" in out.read_text(encoding="utf-8")

    monkeypatch.setattr(sonda.shutil, "which", lambda _c: "/usr/bin/claude")
    monkeypatch.setattr(sonda.subprocess, "run", _fake_run({"--version": _ok("2.1.300"), "--help": _ok(HELP_COMPLETO), "-p": _ok("esto no es JSON {")}))
    out2 = tmp_path / "b.md"
    assert sonda.main(["--out", str(out2)]) == 0
    informe = out2.read_text(encoding="utf-8")
    assert "```text" in informe and "válido: no" in informe


def test_main_por_defecto_escribe_en_docs_superpowers_sondas_con_la_fecha(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sonda = _modulo()
    monkeypatch.setattr(sonda, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sonda.shutil, "which", lambda _c: None)
    monkeypatch.setattr(sonda.subprocess, "run", _fake_run({"--version": FileNotFoundError(), "--help": FileNotFoundError(), "-p": FileNotFoundError()}))
    assert sonda.main([]) == 0
    ficheros = list((tmp_path / "docs" / "superpowers" / "sondas").glob("*-claude-cli.md"))
    assert len(ficheros) == 1 and len(ficheros[0].name) == len("2026-10-18-claude-cli.md")


def test_el_script_corre_como_proceso_con_help() -> None:
    proc = subprocess.run(
        [sys.executable, "-I", str(RUTA), "--help"], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0
    for opcion in ("--cli", "--model", "--out", "--timeout"):
        assert opcion in proc.stdout
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_sonda_claude_cli.py -v`
Expected: FAIL (`AssertionError` del `spec_from_file_location`: el fichero no existe).

- [ ] **Step 3: Implementar** `scripts/sonda_claude_cli.py` según Interfaces, con `REPO_ROOT = Path(__file__).resolve().parent.parent` como módulo-global (los tests lo sustituyen), un `if __name__ == "__main__": raise SystemExit(main())`, docstring de módulo con D11 (por qué una sonda y no una suposición; una sesión anidada no puede hacer la llamada real, 401) y las instrucciones de uso. Escribir `docs/superpowers/sondas/README.md` (≤ 30 líneas): qué es, cómo se ejecuta desde un terminal con sesión válida (`python scripts/sonda_claude_cli.py` tras `npm i -g @anthropic-ai/claude-code@latest`), que el informe va redactado y que el arquitecto lo commitea para que PR-A fije `MIN_CLI_VERSION` y el contrato de `--json-schema`.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_sonda_claude_cli.py -v && uv run ruff check scripts tests && uv run black --check scripts tests`
Expected: PASS y lint limpio.

- [ ] **Step 5: Comprobar con el Python 3.11 del sistema** (el arquitecto lo ejecutará así):

```bash
python --version && python -I scripts/sonda_claude_cli.py --help
```

Expected: `Python 3.11.x` y la ayuda del script, sin `SyntaxError`.

- [ ] **Step 6: Commit**

```bash
git add scripts/sonda_claude_cli.py docs/superpowers/sondas/README.md tests/test_sonda_claude_cli.py
git commit -m "feat(scripts): sonda del CLI claude (--help, --version, -p --json-schema) con informe redactado (D11)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 17: Integración de PR-0 (controlador)

**Files:**
- Modify: `CHANGELOG.md` (bloque `## [Unreleased]`, sección `### Added`; crear el bloque si no existe, encima del `## [0.8.0]`).
- Modify: `README.md:522` y `AGENTS.md:34` (las dos menciones de `GRADE` como herramienta de RoB; D5 dice «sale de `RoBTool` **y del README**»).
- Modify: `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` (§19, tabla de desviaciones).

**Interfaces:** ninguna de código. Deja la rama `feat/ola2-contratos` publicada, la PR abierta (sin merge) y los worktrees de las pistas que arrancan desde PR-0.

- [ ] **Step 0: GRADE fuera de README y AGENTS (D5).** En `README.md:522` sustituir `RoB2/ROBINS-I/GRADE` por `RoB2/ROBINS-I/NOS/AMSTAR-2/QUADAS-2`; en `AGENTS.md:34` sustituir `(RoB2/ROBINS-I/NOS/AMSTAR-2/QUADAS-2/GRADE)` por `(RoB2/ROBINS-I/NOS cohortes y casos-controles/AMSTAR-2/QUADAS-2; GRADE queda fuera: califica certeza por desenlace, D5)`. El resto de la documentación de RoB por herramienta es de PR-I (§13).

- [ ] **Step 1: CHANGELOG.** Añadir en `### Added` de `## [Unreleased]`:

```
- **Contratos de la Ola 2** (spec `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`, §4):
  `RunMeta` v2 (lo aplicado frente a lo pedido, intento y resultado, plantilla, versión del
  backend, latencia y coste), `MetaSink` por contexto (`revisia/provenance/sink.py`),
  `TransientCallError`/`DeterministicCallError`, artefactos v2 (`Environment`, `RunInfo.kind`,
  `JournalEntry` con fallo, `RetrievalOutcome` con rescate humano y recorte, `DepositInfo`),
  acciones `edit_field`/`edit_domain`/`rescue_text` del ledger, modelos `FieldEdits`/`DomainEdits`
  de `decision.yml`, extracción/RoB/verificación/efectos v2, `BenchmarkPanel`/`BenchmarkResult`,
  seis especificaciones oficiales de RoB como datos (`revisia/rob/tools/*.yml`),
  `ingest.doi.normalize_doi` (sin cablear) y la sonda `scripts/sonda_claude_cli.py`.
  `ARTIFACT_SCHEMA_VERSION` pasa a 2. Sin cambio de comportamiento del motor.
```

y en `### Changed` (crearla si no existe) una línea: ``- `RoBTool` ya no admite `GRADE` (califica certeza por desenlace, no riesgo de sesgo por estudio; vuelve como etapa propia) y gana `NewcastleOttawaCaseControl` (D5). Un `protocol.yml` con `rob_tool: GRADE` deja de cargar.``

- [ ] **Step 2: Desviaciones en el spec (§19).** Las filas 1–4 de §19 ya registran las decisiones del arquitecto del 2026-10-19 sobre los supuestos de este plan (versión de esquema única, `RoBDomain.id`, `outcome` y formas diferidas, NOS y RoB 2): no se repiten. Añadir **a continuación de la última fila existente**, con numeración consecutiva, las que siguen (copiar tal cual y añadir las que la revisión por tarea haya producido):

```
| n | §4.2 `RunMeta` v2 | Defaults que reproducen la v1: `attempt=1`, `outcome="ok"`, `model_source="config"`, el resto `None`. El auditor (PR-G) distingue una línea v1 por la ausencia de `outcome`/`attempt` en el JSON crudo, no por el modelo | Plan PR-0 |
| n+1 | §4.2 `decision.yml` | `HumanDecision.records: dict[str, RecordLabel \| FieldEdits \| DomainEdits]` (`left_to_right`); `reason` no vacía y `text_file` con forma `rescues/<nombre>` se validan en el modelo; `_validate` rechaza con mensaje las formas que ningún gate aplica todavía | Plan PR-0 |
| n+2 | §4.2 `RoBToolSpec` | Los ficheros de especificación se llaman por el literal de `RoBTool` (`rob/<tool>.yml` sin tabla) | Plan PR-0 |
| n+3 | §4.4 `tests/fakes.py` | `fail_at` lanza `TransientCallError`; `judge` fail-closed solo cuando se pasa un guion (sin guion, el veredicto fabricado sigue siendo `grounded=True` hasta PR-D) | Plan PR-0 |
| n+4 | §4.4 sonda | La sonda detecta `--safe-mode` en `--help` y solo lo añade si está; rc 0 siempre; `MIN_CLI_VERSION` candidata en el informe | Plan PR-0 |
| n+5 | §4.2 `RoBToolSpec` | §4.2 dice «las cinco especificaciones» y §4.4/D5 «seis»: son seis (NOS en dos formularios). El validador de `overall_scale` exige escala global a `rob2`/`robins_i`/`amstar2`, la prohíbe con `none` y la deja opcional en `nos_stars` | Plan PR-0 |
| n+6 | D5, §13 | Las dos menciones de GRADE en `README.md:522` y `AGENTS.md:34` se quitan en PR-0 (D5 lo pide junto con `RoBTool`); el resto de la documentación de RoB por herramienta sigue en PR-I | Plan PR-0 |
```

- [ ] **Step 3: Commit de documentación.**

```bash
git add CHANGELOG.md README.md AGENTS.md docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md
git commit -m "docs: CHANGELOG, GRADE fuera de README/AGENTS (D5) y desviaciones (§19) de PR-0" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 4: Verificación completa.**

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS; el recuento sube desde 2 103 (anotar el número final en el cuerpo de la PR).

Run (3.11 y 3.12 con venv desechable; `requires-python >= 3.13` impide `uv run --python 3.11` hasta PR-H):

```bash
TMP="$(mktemp -d)"
for PY in 3.11 3.12; do
  uv venv -q --python "$PY" "$TMP/venv$PY"
  uv pip install -q --python "$TMP/venv$PY" pydantic pyyaml python-dotenv markdown nh3 httpx pypdf scipy pytest pytest-xdist
  PYTHONPATH=. "$TMP/venv$PY/Scripts/python" -m pytest -p no:cacheprovider -q -n auto -m "not cronometrado"
done
```

Expected: PASS en ambas versiones (en POSIX la ruta es `bin/python`).

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`
Expected: limpio.

- [ ] **Step 5: Publicar la rama y abrir PR-0** (sin merge).

```bash
git push -u origin feat/ola2-contratos
gh pr create --base main --head feat/ola2-contratos --title "Ola 2 · PR-0: spec, planes y contratos entre pistas" --body "$(cat <<'EOF'
## Qué es

Primera PR de la Ola 2 del plan de remediación (auditoría 2026-09-03, §8; spec `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`, aprobado el 2026-10-18). Trae el diseño, los planes de PR-0 y PR-H y el **contrato** que las ocho pistas importan. No cambia el comportamiento del motor.

## Qué cambia

- `revisia/llm/base.py`: `TransientCallError`, `DeterministicCallError`, `LLMRequest.prompt_template` (D9, A7).
- `revisia/provenance/`: `RunMeta` v2 (A6, A7, D14), `sink.py` (D14, sin consumidores), acciones `edit_field`/`edit_domain`/`rescue_text` y `GateSummary.n_edits`.
- `revisia/schemas/artifacts.py`: `ARTIFACT_SCHEMA_VERSION = 2`, `Environment`, `RunInfo.kind/environment`, `JournalEntry` con fallo, `RetrievalOutcome` con rescate y recorte, `DepositInfo` (D12, D17, D20, D21, D23).
- `revisia/schemas/{extraction,rob,verification,effects,benchmark,rob_tools}.py`: modelos v2 y el panel del benchmark; `RoBTool` sin `GRADE` y con `NewcastleOttawaCaseControl` (D5).
- `revisia/rob/tools/*.yml`: seis especificaciones oficiales (ids, conteos, escalas, agregación), con paráfrasis propias y referencia a la fuente.
- `revisia/orchestration/hitl.py`: `FieldEdits`, `DomainEdits`, `RecordLabel.text_file` (solo modelos y validación estructural).
- `revisia/ingest/doi.py`: `normalize_doi` (sin cablear hasta PR-B).
- `tests/fakes.py`: `ScriptedProvider` con fallo determinista, juez, extracción y RoB con guion; `fetch_disponible_largo`.
- `scripts/sonda_claude_cli.py` + `docs/superpowers/sondas/README.md` (D11): la ejecuta el arquitecto antes de PR-A.

## Cambios incompatibles

- `rob_tool: GRADE` deja de cargar (D5). `schema_version` de los artefactos pasa a 2 (D12); los v1 siguen leyéndose.

## Verificación

- `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"` + `-m cronometrado`: <N> recogidos, en verde (base: 2 103).
- La misma suite en 3.11 y 3.12 con venv desechable: en verde.
- `ruff check`, `ruff format --check`, `black --check`, `uv lock --check`: limpios.
- Los seis YAML de RoB viajan en el wheel (`python -m zipfile -l`).

## Pila

`main` ← **PR-0** ← PR-H ← PR-A ← PR-B ← PR-C ← PR-D ← PR-E ← PR-F ← PR-G ← PR-I (spec §15). Al mergear, no borrar la rama mientras otra PR la use como base: merge sin borrar → `gh pr edit <n> --base main` en la siguiente → borrar la rama → cerrar y reabrir la siguiente para que corra el CI.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR.

- [ ] **Step 6: Worktrees de las pistas que arrancan desde PR-0** (§15: H, A, B, E₁, F₁, G₁).

```bash
for P in h a b e f g; do
  case $P in
    h) R=feat/ola2-ci-tests;; a) R=feat/ola2-procedencia;; b) R=feat/ola2-identidad-registros;;
    e) R=feat/ola2-rob-por-herramienta;; f) R=feat/ola2-meta-benchmark;; g) R=feat/ola2-auditor;;
  esac
  git -C C:/revisia worktree add "C:/revisia-wt/$P" -b "$R" feat/ola2-contratos
  (cd "C:/revisia-wt/$P" && uv sync --extra dev --extra search --extra meta && uv run pytest -p no:cacheprovider -q -n auto -m "not cronometrado")
done
```

Expected: seis worktrees con la suite en verde. H sigue su plan (`2026-10-18-ola2-prh-ci-tests.md`); A, B, E₁, F₁ y G₁ esperan a sus planes.

---

## Self-review (hecha al escribir el plan)

- **Cobertura de §4.4:** `runmeta.py` (T3), `sink.py` (T4), `llm/base.py` (T2), `artifacts.py` (T5), `extraction.py` (T8), `rob.py` (T9), `verification.py` (T11), `effects.py` (T12), `rob_tools.py` + seis YAML (T10), `benchmark.py` (T13), `ingest/doi.py` (T14), `scripts/sonda_claude_cli.py` (T16), `ledger.py` (T6), `hitl.py` (T7), `tests/fakes.py` (T15), spec y planes (T1, T17). `ExtractionAgreement` v2 y la forma por desenlace de `MetaAnalysisResult` quedan declaradas en §19 como diferidas a PR-C y PR-F (viven en módulos que §15 asigna a esas pistas).
- **Firmas verificadas contra `main` @ `c1af7c3` el 2026-10-18:** `RunMeta` (`runmeta.py:56-85`), `LEDGER_ACTIONS`/`summarize_gates` (`ledger.py:30,145`), `RecordLabel`/`HumanDecision`/`_validate` (`hitl.py:123,151,449`), `RunInfo`/`JournalEntry`/`RetrievalOutcome`/`GateSummary` (`artifacts.py:107,161,241,276`), `RoBTool` (`rob.py:15`), `LLMRequest` (`base.py:26`), `ScriptedProvider` (`fakes.py:48-141`), `TOOL_DOMAINS` (`agents/rob.py:23-62`), `make_provider_judge` y su prompt (`rag/grounding.py`), `_ExtractionOut`/`_RoBOut` (`agents/extraccion.py`, `agents/rob.py`), `ProviderConfig`/`MODEL_NAME_PATTERN` (`llm/registry.py`), `ScreeningMetrics` (`metrics.py`), `rechazar_claves_de_fusion` (`config.py`). El auditor no compara `schema_version` con ninguna constante (`grep` en `revisia/audit/` sin resultados).
- **Consistencia de tipos entre tareas:** `QuoteStatus`, `SourceText`, `RecordStatus`, `GroundingMode`, `RunKind` se definen en T5 y los consumen T8, T9, T11; `Environment` (T5) lo consume T13; `TransientCallError`/`DeterministicCallError` (T2) los consume T15; `RoBTool` (T9) lo consume T10.
- **Proporción:** los bloques de código son tests (nombres y aserciones con los valores del spec) y la tabla de las seis especificaciones; ningún cuerpo de función.
- **Revisión independiente (2026-10-18) incorporada:** `union_mode` va en la unión (`Annotated`), no en el `dict` (pydantic rechazaba la clase); el validador de `overall_scale` admite `None` con `nos_stars` (si no, los dos YAML de NOS no cargaban); `tests/test_hitl.py:224-228` también cambia con `schema_version = 2`; GRADE sale de `README.md:522` y `AGENTS.md:34` en la Tarea 17; `text_file` rechaza `rescues/.` y `rescues/..`; `_claves_a_texto` como función de módulo; los conteos de las seis herramientas de RoB se confirmaron con alta certeza.
