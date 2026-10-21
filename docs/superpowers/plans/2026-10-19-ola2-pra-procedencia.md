# Ola 2 · PR-A `feat/ola2-procedencia` (procedencia honesta, `claude -p` acotado y `agent` con modelo) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada llamada a un LLM quede registrada **al ocurrir y por intento**, con lo que de verdad viajó al backend (parámetros aplicados, hash del texto enviado, plantilla con versión y hash, versión del SDK o del CLI, latencia y coste), que `claude -p` corra acotado por capacidad detectada (versión mínima, `--json-schema`, `--max-turns`, `--max-budget-usd`, entorno por allowlist), que los proveedores separen el fallo transitorio del determinista (D9), que `agent` diga qué modelo contestó y no apruebe solo, y que `run.json` y el manifiesto lleven el entorno de la corrida (A6, A7, A8, A10, A15, M17, D9 en proveedores, D11, D14).

**Architecture:** Los proveedores construyen y **emiten** un `RunMeta` v2 por intento con un único helper (`revisia/llm/meta.py`: `emit_attempt`, `APPLIED_PARAMS`, clasificación de errores); `journaled` instala un sink que escribe cada meta en `llm_calls.jsonl` en el acto, deduplica por identidad las que el `compute` devuelve y, ante un `DeterministicCallError`, deja una línea `failed` definitiva y lanza `RecordFailedError` (subclase de `JournalError`: rc 2 hasta que PR-C la convierta en «pendiente de humano»). `ClaudeCodeProvider` consulta `claude --version`/`--help` una vez por proceso (`probe_cli`) y el preflight bloquea por debajo de `MIN_CLI_VERSION` o sin `--safe-mode`/`--tools`. `ensure_snapshot` escribe `environment` y rechaza reanudar una corrida 0.8; `write_manifest` lo copia. **`pipeline.py` no se toca** (§15): todo se engancha en `journal.py`, `snapshot.py`, `run_context.py`, los proveedores, los agentes y los exportadores. Las Tareas 1–7 dependen solo de PR-0; la puerta de la sonda (Tarea 8) va justo antes de lo que la necesita (Tareas 9–11).

**Tech Stack:** Python 3.13 en desarrollo; la suite también en 3.11/3.12 tras rebasar sobre PR-H (sin sintaxis de 3.12+). Pydantic v2, `contextvars` (sink de PR-0), `subprocess` (dobles en todos los tests), `importlib.metadata`, pytest + pytest-xdist, ruff + black (línea 100), uv, gh.

**Spec:** `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`. Este plan implementa §5 entero (5.1–5.5) y la parte de §4.2/§4.3 que le toca (relaciones 19–21 del lado productor). Lee antes §3 (D9, D10, D11, D12, D14, D24), §4.2, §15 y **§19 filas 1–8** (decisiones del arquitecto; vinculan). Planes hermanos: `2026-10-18-ola2-pr0-contratos.md` (sus bloques **Interfaces** son la fuente de `RunMeta` v2, `sink.py`, `TransientCallError`/`DeterministicCallError`, `LLMRequest.prompt_template`, `Environment`, `RunInfo` v2, `JournalEntry` v2/`JournalFailure`, `ScriptedProvider`, `tool_spec_fingerprint`, la sonda) y `2026-10-18-ola2-prh-ci-tests.md` (deja cuatro `xfail(strict=True, raises=AssertionError)` en `tests/test_providers_api.py` y el job `sdk-smoke` con `tests/test_sdk_superficie.py`, que esta PR pone en verde).

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes y commits **en español**, con el tono del repo; las docstrings citan la auditoría («auditoría 2026-09-03, A7») o la decisión («D14»).
- Estilo: `ruff` (`E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100), limpios en cada commit. `from __future__ import annotations` en todo módulo nuevo. Nada de sintaxis exclusiva de 3.12+ (`type X =`, `def f[T]`): tras el rebase la matriz corre en 3.11.
- **`revisia/orchestration/pipeline.py` no se toca** (§15). Ficheros de otras pistas que esta PR toca **mínimamente**, con el conflicto previsto: `revisia/agents/extraccion.py` (C) y `revisia/agents/rob.py` (E₁): solo `load_prompt` → `load_template` y el `prompt_template` del `LLMRequest` (dos líneas cada uno); `revisia/schemas/artifacts.py` (PR-0): solo se retira `RunInfo.prompt_sha256`. `revisia/rag/*` (D), `revisia/audit/*` (G), `pyproject.toml` y `ci.yml` (H) **no se tocan**.
- Tests offline y deterministas: ninguno invoca `claude`, APIs ni SDK reales. `subprocess.run` del CLI se sustituye siempre; el único proceso hijo real es `sys.executable` (Tarea 10, fuga de entorno). `git` nunca corre en la suite: una fixture autouse fija `snapshot.git_state` (Tarea 6), salvo en los tests marcados `git_real`.
- Línea base: la suite de PR-0 en verde (recuento anotado en el cuerpo de PR-0). Ningún test existente se borra; los que cambian de expectativa se listan en su tarea con el cambio exacto.
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"` y `uv run pytest -p no:cacheprovider -m cronometrado`; lint (un paso propio en cada tarea, antes del commit), `uv run ruff check . && uv run ruff format --check . && uv run black --check .` con Expected «sin errores; `N files already formatted`». Los tests de este plan se escriben con líneas ≤ 100 columnas: si un bloque del plan pasa de 100, el implementador lo parte como haría `black`, sin cambiar las aserciones.
- Commits pequeños, al menos uno por tarea, prefijo convencional, terminados con `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- **Los implementadores no tocan** `CHANGELOG.md`, `README.md`, `AGENTS.md`, `docs/auditoria/` ni el spec: los actualiza el controlador en la Tarea 13.
- `MIN_CLI_VERSION`, la clave del objeto validado por `--json-schema`, el `subtype` de éxito, los `subtype` de límite y la compatibilidad de `--max-turns 1` con `--json-schema` **se leen de la sonda** (`docs/superpowers/sondas/<fecha>-claude-cli.md`, Tarea 8; la sonda de PR-0, Tarea 16, hace dos llamadas, la segunda con `--max-turns 1`, y registra `subtype` y `total_cost_usd`). En este plan aparecen como marcadores `«SONDA:…»`; nunca se inventan. Los tests los usan a través de las constantes, nunca por su valor, y uno comprueba que ninguna constante es un marcador.
- Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base (§15).

## Review Focus

Entradas que el spec implica y que ningún test de §5 ejercita; cada una tiene su test en la tarea dueña:

1. **El shim `claude.CMD` de Windows con `--json-schema`**: el schema es JSON con `"`, que la guardia BatBadBut (`claude_code.py:148-192`, A1) rechaza; con el shim, **cada** llamada estructurada fallaría. Lo esperable: con un shim `.cmd`/`.bat` el schema viaja en el texto (como hoy) y el preflight lo avisa. → Tarea 10 (`test_json_schema_con_shim_cmd_viaja_en_el_texto`, `test_preflight_avisa_del_shim_cmd`).
2. **Un error global disfrazado de error de registro** (401 por credencial vencida, 403 por permiso): si se clasificara determinista, cada registro iría al humano como «la IA falló» y la corrida seguiría. Lo esperable: 401 y 403 son transitorios (se corrige la credencial o el permiso y se reanuda). → Tareas 2 y 11 (`test_outcome_for_status`, `test_401_es_transitorio_y_accionable`).
3. **Un `claude` que no arranca, cuelga o imprime una versión ilegible** al sondearlo: lo esperable es un error de preflight con el motivo (rc 2), no una traza ni un sondeo repetido en cada llamada. → Tarea 9 (`test_probe_cli_que_no_arranca_es_cli_probe_error`, `test_preflight_sonda_fallida_es_error`, `test_proveedor_con_sonda_fallida_da_preflight_error`).
4. **Nombres de variables de entorno en Windows** (`Path`, `SystemRoot`) **y proxies en minúsculas** en POSIX: la allowlist debe casar sin distinguir mayúsculas, o el CLI arranca sin `PATH`/`SYSTEMROOT` o sin proxy. → Tarea 10 (`test_allowlist_casa_sin_distinguir_mayusculas`) y la comprobación real del arquitecto (Tarea 13, Step 5).
5. **Intentos fallidos en `llm_calls.jsonl` de una corrida que se reanuda**: el auditor actual (G) no los conoce; no debe dar FAIL por una línea `transient_error` huérfana (son válidas desde la Ola 1), y el desfase conocido (`models_used` sobre llamadas `ok`, `checks_flow.py:1255-1296`) queda fijado en un `xfail(strict=True)` para PR-G₂. → Tareas 3 y 6.

---

## Topología de ejecución (subagentes)

Worktree `C:\revisia-wt\a`, rama `feat/ola2-procedencia`, creada desde `feat/ola2-contratos` en la Tarea 17 de PR-0. Secuencial, tarea a tarea. Al final (Tarea 12) se rebasa sobre `feat/ola2-ci-tests` (PR-H), se ponen en verde sus cuatro `xfail(strict=True)` y la PR se abre con base `feat/ola2-ci-tests` (§15).

| Tarea | Fichero(s) | Depende de |
|---|---|---|
| 1 | `revisia/prompts/__init__.py`, `revisia/agents/{screening,screening_ft,extraccion,rob,reporte}.py` | PR-0 |
| 2 | `revisia/llm/meta.py` (nuevo), `revisia/llm/providers/fake.py`, `tests/fakes.py` | 1 |
| 3 | `revisia/orchestration/journal.py`, `tests/test_reanudacion.py` | 2 |
| 4 | `revisia/llm/providers/{gemini,openai_api,local_openai,openai_compat,anthropic_api}.py` | 2 |
| 5 | `revisia/llm/providers/agent.py`, `revisia/agent_driver.py`, `revisia/llm/preflight.py` | 2 |
| 6 | `revisia/orchestration/snapshot.py`, `revisia/orchestration/run_context.py`, `revisia/schemas/artifacts.py`, `tests/conftest.py` | 1, 3 |
| 7 | `revisia/exports/methods.py`, `revisia/exports/checklist.py` | 2, 6 |
| 8 | puerta de la sonda del CLI (controlador) | informe de la sonda |
| 9 | `revisia/llm/providers/claude_code.py` (sonda), `revisia/llm/preflight.py`, `tests/conftest.py`, `tests/fakes.py` | 2, 8 |
| 10 | `claude_code.py` (comando y entorno), `revisia/llm/registry.py`, `preflight.py`, `.env.example`, `protocols/_TEMPLATE/protocol.yml` | 9 |
| 11 | `claude_code.py` (intentos, metas, D9) | 3, 10 |
| 12 | rebase sobre H, `tests/test_providers_api.py` (xfail → verde) | 1–11 |
| 13 | integración (controlador) | todas |

Si la sonda aún no está cuando terminan las Tareas 1–7, el controlador se detiene en la Tarea 8 y avisa; lo hecho queda commiteado.

**Ciclo por tarea (§16):** implementador (subagente nuevo, TDD estricto: test rojo → código mínimo → verde → lint → commit) → revisor (subagente nuevo: primero cumplimiento del spec y de este plan, después calidad) → correcciones. Desviaciones descubiertas en revisión se corrigen y se anotan para §19 (Tarea 13), sin consultar, salvo que cambien una decisión D1–D6. **El merge lo decide el arquitecto.**

**Números de línea:** son los de `main` @ `c1af7c3`. PR-0 desplaza algunos (`runmeta.py`, `base.py`, `artifacts.py`, `tests/fakes.py`); en esos ficheros busca por nombre.

---

## Tarea 1: Plantillas versionadas con hash (`revisia/prompts/__init__.py`) y `prompt_template` en cada agente

**Files:**
- Modify: `revisia/prompts/__init__.py:16-21` (`load_prompt` sigue igual; funciones nuevas al lado).
- Modify: `revisia/orchestration/snapshot.py:57-59,76-81` (`_text_sha256` y `prompt_fingerprint` delegan en `revisia.prompts`: una sola fuente para el hash de plantillas, M10).
- Modify: `revisia/agents/screening.py:57,66-71`, `revisia/agents/screening_ft.py:40,46`, `revisia/agents/extraccion.py:49,54`, `revisia/agents/rob.py:94,101`, `revisia/agents/reporte.py:43,48` (cada uno: `tpl = load_template("<agente>")`, `tpl.text.format(...)` y `prompt_template=tpl.template` en su `LLMRequest`).
- Test: `tests/test_prompts.py` (nuevo).

**Interfaces:**
- Consumes: `LLMRequest.prompt_template` (PR-0, Tarea 2); `sha256_text`.
- Produces (§5.2, A7, D10):
  - `PROMPT_VERSIONS: dict[str, str] = {"screening": "v1", "screening_ft": "v1", "extraccion": "v1", "rob": "v1", "reporte": "v1"}`. Cada pista que crea un `v2.md` (C, D, E) cambia **su** clave; ningún test fija los valores (se derivan del diccionario).
  - `load_prompt(agent: str, version: str = "v1") -> str` **no cambia** (firma y retorno de `c1af7c3`): el código de C, D y E que aún la llame sigue funcionando (supuesto §19).
  - `class PromptTemplate(NamedTuple)`: `text: str`, `template: str` (`"<agente>/<versión>.md"`), `sha256: str`. Se desempaqueta como la terna de §5.2.
  - `load_template(agent: str, version: str | None = None) -> PromptTemplate`: `version=None` usa `PROMPT_VERSIONS[agent]` (`KeyError` con el texto `PROMPT_VERSIONS` si el agente no está); fichero inexistente → `FileNotFoundError` con el nombre `"<agente>/<versión>.md"`.
  - `text_sha256(path: Path) -> str`: SHA-256 del texto UTF-8 con CRLF → LF. **Única** regla de hash de plantillas y del protocolo: `snapshot._text_sha256` pasa a ser este mismo objeto (M10).
  - `template_fingerprint(prompts_dir: Path | None = None) -> dict[str, str]`: `{"<agente>/<versión>.md": text_sha256}` de `prompts_dir/*/*.md` (por defecto `_PROMPTS_DIR`), ordenado. `snapshot.prompt_fingerprint()` la llama con su `PROMPTS_DIR` (los tests lo sustituyen, `tests/test_snapshot.py:103-106`).
  - `template_sha256(name: str) -> str`: `text_sha256(_PROMPTS_DIR / name)` con `functools.lru_cache`; `FileNotFoundError` si no existe. Lo usa `emit_attempt` (Tarea 2).
  - Cada agente de A usa `load_template` y rellena `LLMRequest(prompt_template=tpl.template, …)` (relación 19).

- [ ] **Step 1: Test que falla** — crear `tests/test_prompts.py`:

```python
"""Plantillas versionadas con hash y su nombre en cada petición (spec 2026-10-18 §5.2; A7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from revisia import prompts as prompts_mod
from revisia.agents.extraccion import extract_record
from revisia.agents.reporte import synthesize_narrative
from revisia.agents.rob import assess_rob
from revisia.agents.screening import ScreenerMember, screen_record
from revisia.agents.screening_ft import screen_fulltext
from revisia.llm.providers.fake import FakeProvider
from revisia.orchestration import snapshot as snapshot_mod
from revisia.orchestration.snapshot import prompt_fingerprint
from revisia.prompts import (
    PROMPT_VERSIONS,
    PromptTemplate,
    load_prompt,
    load_template,
    template_sha256,
    text_sha256,
)
from revisia.schemas.records import SearchRecord

AGENTES = ("screening", "screening_ft", "extraccion", "rob", "reporte")


def _vigente(agente: str) -> str:
    return f"{agente}/{PROMPT_VERSIONS[agente]}.md"


def test_prompt_versions_apunta_a_plantillas_que_existen_con_su_hash() -> None:
    assert set(PROMPT_VERSIONS) == set(AGENTES)
    huellas = prompt_fingerprint()
    for agente in AGENTES:
        tpl = load_template(agente)
        assert isinstance(tpl, PromptTemplate) and tpl.template == _vigente(agente)
        assert tpl.sha256 == template_sha256(tpl.template) == huellas[tpl.template]


def test_load_template_es_una_terna_y_load_prompt_sigue_devolviendo_texto() -> None:
    texto, nombre, sha = load_template("screening", "v1")
    assert nombre == "screening/v1.md" and "{question}" in texto and len(sha) == 64
    assert load_prompt("screening") == texto  # firma de la Ola 1 intacta


def test_load_template_desconocido_es_error_claro() -> None:
    with pytest.raises(FileNotFoundError, match="screening/v9.md"):
        load_template("screening", "v9")
    with pytest.raises(KeyError, match="PROMPT_VERSIONS"):
        load_template("inexistente")


def test_una_sola_regla_de_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert snapshot_mod._text_sha256 is text_sha256  # M10
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "v1.md").write_bytes(b"linea 1\r\nlinea 2\r\n")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "v1.md").write_bytes(b"linea 1\nlinea 2\n")
    monkeypatch.setattr(prompts_mod, "_PROMPTS_DIR", tmp_path)
    template_sha256.cache_clear()
    try:
        assert template_sha256("a/v1.md") == template_sha256("b/v1.md")
    finally:
        template_sha256.cache_clear()


class _Grabadora(FakeProvider):
    """Anota el `prompt_template` de cada petición."""

    def __init__(self) -> None:
        super().__init__()
        self.plantillas: list[str | None] = []

    def structured(self, req, schema):
        self.plantillas.append(req.prompt_template)
        return super().structured(req, schema)

    def complete(self, req):
        self.plantillas.append(req.prompt_template)
        return super().complete(req)


def test_cada_agente_declara_su_plantilla_en_la_peticion() -> None:
    p = _Grabadora()
    rec = SearchRecord(record_id="r", title="T")
    miembro = ScreenerMember(provider=p, model_name="fake:fake-1")
    screen_record([miembro], question="q", criteria="c", record=rec)
    screen_fulltext(p, "fake:fake-1", question="q", criteria="c", record=rec, text="t")
    extract_record(p, record=rec, form_fields=[{"key": "n"}])
    assess_rob(p, tool="RoB2", record=rec)
    synthesize_narrative(p, question="q", included=[rec], extractions={})
    assert p.plantillas == [_vigente(a) for a in AGENTES]
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_prompts.py -v`
Expected: FAIL con `ImportError: cannot import name 'PROMPT_VERSIONS'`.

- [ ] **Step 3: Implementar** en `revisia/prompts/__init__.py` las firmas de Interfaces (docstring del módulo: la versión vigente vive en `PROMPT_VERSIONS`; `load_template` es la vía con nombre y hash; el hash es el mismo que `run.json.environment.prompt_templates`, relación 19). En `snapshot.py`: `from revisia.prompts import template_fingerprint` y `from revisia.prompts import text_sha256 as _text_sha256`; `prompt_fingerprint()` → `template_fingerprint(PROMPTS_DIR)` (la Tarea 6 le añade las especificaciones de RoB). Cambiar los cinco agentes.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_prompts.py tests/test_pipeline_fake.py tests/test_snapshot.py tests/test_rob.py -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/prompts/__init__.py revisia/orchestration/snapshot.py revisia/agents/screening.py revisia/agents/screening_ft.py revisia/agents/extraccion.py revisia/agents/rob.py revisia/agents/reporte.py tests/test_prompts.py
git commit -m "feat(prompts): PROMPT_VERSIONS, load_template con nombre y hash, prompt_template en cada agente (A7)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 2: Meta por intento con lo aplicado (`revisia/llm/meta.py`) y dobles que emiten

**Files:**
- Create: `revisia/llm/meta.py`.
- Modify: `revisia/llm/providers/fake.py:70-93` (`_meta`, `complete`, `structured`).
- Modify: `tests/fakes.py` (`ScriptedProvider._llamar`, `_meta`, `complete`, `structured`; la versión que dejó PR-0, Tarea 15).
- Test: `tests/test_llm_meta.py` (nuevo).

**Interfaces:**
- Consumes: `RunMeta` v2, `Outcome`, `ModelSource`, `RUNMETA_SCHEMA_VERSION` (PR-0 T3); `emit` (PR-0 T4); `TransientCallError`, `DeterministicCallError` (PR-0 T2); `template_sha256` (T1); `available_providers` (`registry.py:71-73`).
- Produces (§5.2, A6, A7, D9, D14):
  - `AppliedParam = Literal["seed", "temperature", "top_p"]`.
  - `APPLIED_PARAMS: dict[str, frozenset[AppliedParam]]`, claves == `available_providers()`: `gemini`, `openai`, `zai`, `openrouter`, `local_openai` → `{"seed", "temperature", "top_p"}`; `anthropic` → `{"temperature", "top_p"}`; `claude_code`, `agent`, `fake` → `frozenset()` (el doble no usa parámetros: honesto, supuesto §19). Es la tabla que los proveedores cumplen y la que lee `metodologia.md` (Tarea 7).
  - `emit_attempt(provider: str, model: str, req: LLMRequest, *, sent_prompt: str, response_text: str, attempt: int = 1, outcome: Outcome = "ok", model_version: str | None = None, model_source: ModelSource | None = None, schema_sha256: str | None = None, backend_version: str | None = None, latency_ms: int | None = None, cost_usd: float | None = None, effort: str | None = None, input_tokens: int | None = None, output_tokens: int | None = None, deterministic: bool = False) -> RunMeta`: construye la meta, la **emite** (`sink.emit`) y devuelve **el mismo objeto** (`journaled` deduplica por identidad, Tarea 3). Rellena: `seed`/`temperature`/`top_p` = lo pedido en `req`; `<p>_applied` = valor de `req` si `p ∈ APPLIED_PARAMS[provider]`, si no `None`; `prompt_sha256 = sha256_text(f"{req.system or ''}\n{sent_prompt}")` (A7: `sent_prompt` es el texto que viajó, con schema inyectado y sufijo de reintento si van en el texto); `response_sha256 = sha256_text(response_text)`; `prompt_template = req.prompt_template` y su `template_sha256` (o `None`); `model_source` = el pasado o, si es `None`, `"backend"` con `model_version` no nulo y `"config"` sin él.
  - `outcome_for_status(status: int) -> Outcome`: `401`, `403`, `408`, `429` y `≥ 500` → `"transient_error"` (401/403: credencial y permiso son globales y se arreglan sin regenerar la corrida; §19 fila 14, aprobada 2026-10-20); resto de `4xx` (400, 404, 413, 422…) → `"deterministic_error"`. Coincide con la docstring de `DeterministicCallError` de PR-0 («4xx distinto de 401/403/408/429»).
  - `classify_sdk_error(exc: BaseException) -> Outcome | None`: status de `exc.status_code` o `exc.code` (si es `int`) → `outcome_for_status`; `TimeoutError`, `ConnectionError` o una clase en la MRO llamada `APITimeoutError`, `APIConnectionError`, `TimeoutException`, `ConnectError`, `ReadTimeout`, `ConnectTimeout` o `RemoteProtocolError` → `"transient_error"`; lo demás → `None` (se propaga sin clasificar).
  - `error_for(outcome: Outcome) -> type[RuntimeError]`: `transient_error` → `TransientCallError`; `deterministic_error` e `invalid_output` → `DeterministicCallError`.
  - `sdk_version(dist: str) -> str | None`: `metadata.version(dist)` (con `from importlib import metadata`, para que los tests sustituyan `metadata.version`); `None` si `PackageNotFoundError`. Sin caché.
  - `FakeProvider` y `ScriptedProvider` emiten cada llamada con `emit_attempt(..., deterministic=True)`; `ScriptedProvider` emite también la llamada que falla (`fail_at` → `outcome="transient_error"`, `fail_deterministic_at` → `"deterministic_error"`, `response_text=""`) **antes** de lanzar.

- [ ] **Step 1: Test que falla** — crear `tests/test_llm_meta.py`:

```python
"""Meta por intento: lo pedido, lo aplicado, el texto enviado y la plantilla (§5.2; A6, A7, D9)."""

from __future__ import annotations

import pytest
from fakes import ScriptedProvider
from pydantic import BaseModel

from revisia.llm import meta as meta_mod
from revisia.llm.base import DeterministicCallError, LLMRequest, TransientCallError
from revisia.llm.meta import (
    APPLIED_PARAMS,
    classify_sdk_error,
    emit_attempt,
    error_for,
    outcome_for_status,
    sdk_version,
)
from revisia.llm.providers.fake import FakeProvider
from revisia.llm.registry import available_providers
from revisia.prompts import template_sha256
from revisia.provenance.runmeta import sha256_text
from revisia.provenance.sink import collecting

REQ = LLMRequest(
    prompt="¿Incluir?",
    system="Eres un cribador.",
    temperature=0.3,
    seed=42,
    prompt_template="screening/v1.md",
)


class _Out(BaseModel):
    n: int


def test_applied_params_cubre_todos_los_proveedores() -> None:
    assert set(APPLIED_PARAMS) == set(available_providers())
    assert (
        APPLIED_PARAMS["claude_code"]
        == APPLIED_PARAMS["agent"]
        == APPLIED_PARAMS["fake"]
        == frozenset()
    )
    assert APPLIED_PARAMS["anthropic"] == {"temperature", "top_p"}
    for p in ("gemini", "openai", "zai", "openrouter", "local_openai"):
        assert APPLIED_PARAMS[p] == {"seed", "temperature", "top_p"}


def test_emit_attempt_rellena_lo_pedido_lo_aplicado_y_la_plantilla() -> None:
    with collecting() as metas:
        meta = emit_attempt(
            "openai",
            "gpt-x",
            REQ,
            sent_prompt="¿Incluir?\nSCHEMA",
            response_text="{}",
            attempt=2,
            outcome="invalid_output",
        )
    assert len(metas) == 1 and metas[0] is meta
    assert (meta.seed, meta.temperature) == (42, 0.3)
    assert (meta.seed_applied, meta.temperature_applied, meta.top_p_applied) == (42, 0.3, None)
    assert meta.prompt_sha256 == sha256_text("Eres un cribador.\n¿Incluir?\nSCHEMA")
    assert meta.prompt_template == "screening/v1.md"
    assert meta.prompt_template_sha256 == template_sha256("screening/v1.md")
    assert (meta.attempt, meta.outcome, meta.model_source) == (2, "invalid_output", "config")
    anth = emit_attempt(
        "anthropic", "c", REQ, sent_prompt="x", response_text="", model_version="c-2026"
    )
    assert (anth.seed_applied, anth.temperature_applied, anth.model_source) == (
        None,
        0.3,
        "backend",
    )
    cc = emit_attempt("claude_code", "opus", REQ, sent_prompt="x", response_text="")
    assert (cc.seed_applied, cc.temperature_applied, cc.top_p_applied) == (None, None, None)
    sin_plantilla = emit_attempt(
        "fake", "f", LLMRequest(prompt="p"), sent_prompt="p", response_text=""
    )
    assert (sin_plantilla.prompt_template, sin_plantilla.prompt_template_sha256) == (None, None)


@pytest.mark.parametrize(
    ("status", "esperado"),
    [
        (400, "deterministic_error"),
        (413, "deterministic_error"),
        (403, "transient_error"),
        (404, "deterministic_error"),
        (422, "deterministic_error"),
        (401, "transient_error"),
        (408, "transient_error"),
        (429, "transient_error"),
        (500, "transient_error"),
        (503, "transient_error"),
    ],
)
def test_outcome_for_status(status: int, esperado: str) -> None:
    assert outcome_for_status(status) == esperado


def test_classify_sdk_error_por_status_nombre_o_tipo() -> None:
    class APIStatusError(Exception):
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    class ClientError(Exception):  # google-genai: `.code`
        code = 400

    class APITimeoutError(Exception):
        pass

    assert classify_sdk_error(APIStatusError(429)) == "transient_error"
    assert classify_sdk_error(APIStatusError(400)) == "deterministic_error"
    assert classify_sdk_error(ClientError()) == "deterministic_error"
    assert classify_sdk_error(APITimeoutError()) == "transient_error"
    assert classify_sdk_error(TimeoutError()) == "transient_error"
    assert classify_sdk_error(ConnectionResetError()) == "transient_error"
    assert classify_sdk_error(ValueError("x")) is None
    assert error_for("transient_error") is TransientCallError
    assert error_for("deterministic_error") is error_for("invalid_output") is DeterministicCallError


def test_sdk_version_none_si_no_esta_instalado(monkeypatch: pytest.MonkeyPatch) -> None:
    def _version(dist: str) -> str:
        if dist != "openai":
            raise meta_mod.metadata.PackageNotFoundError(dist)
        return "2.44.0"

    monkeypatch.setattr(meta_mod.metadata, "version", _version)
    assert sdk_version("openai") == "2.44.0"
    assert sdk_version("no-existe") is None


def test_fake_y_scripted_emiten_cada_llamada_tambien_la_fallida() -> None:
    with collecting() as metas:
        _, meta = FakeProvider().structured(REQ, _Out)
    assert len(metas) == 1 and metas[0] is meta and meta.deterministic and meta.seed_applied is None
    p = ScriptedProvider(fail_at=2)
    with collecting() as metas:
        p.complete(REQ)
        with pytest.raises(TransientCallError):
            p.complete(REQ)
    assert [m.outcome for m in metas] == ["ok", "transient_error"]
    d = ScriptedProvider(fail_deterministic_at=1)
    with collecting() as metas, pytest.raises(DeterministicCallError):
        d.complete(REQ)
    assert [m.outcome for m in metas] == ["deterministic_error"]
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_llm_meta.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'revisia.llm.meta'`.

- [ ] **Step 3: Implementar** `revisia/llm/meta.py` con las firmas de Interfaces (docstring: una meta por intento, emitida en el acto, D14; «lo pedido» frente a «lo aplicado», A6; hash del texto enviado, A7; tabla de clasificación de D9 con 401 y 403 como transitorios y por qué). `FakeProvider._meta` y el de `ScriptedProvider` pasan a `emit_attempt(self.name, self.model, req, sent_prompt=req.prompt, response_text=text, deterministic=True)`; el resto de su comportamiento no cambia.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_llm_meta.py tests/test_fakes.py tests/test_journal.py tests/test_pipeline_fake.py -v`
Expected: PASS (los hashes de `fake` no cambian: envía el prompt tal cual).

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/llm/meta.py revisia/llm/providers/fake.py tests/fakes.py tests/test_llm_meta.py
git commit -m "feat(llm): emit_attempt, APPLIED_PARAMS y clasificación de errores; los dobles emiten cada intento (A6, A7, D9, D14)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 3: Registro en el acto, por intento, y fallo determinista en el diario (`journal.py`)

**Files:**
- Modify: `revisia/orchestration/journal.py:170-213` (`journaled`) y clase nueva tras `JournalError` (línea 39).
- Modify: `tests/test_reanudacion.py:150` (`== 2` → `== 3`) y `:161` (`== 4` → `== 5`): la llamada 3 (la que lanza el 429) ahora queda registrada como intento `transient_error` (D14; es justo lo que la Ola 1 perdía, fila 45j).
- Test: `tests/test_journal.py` y `tests/test_reanudacion.py` (añadir al final).

**Interfaces:**
- Consumes: `installed` (PR-0 T4); `JournalEntry` v2, `JournalFailure` (PR-0 T5); `DeterministicCallError`; `emit_attempt` (T2); `RunContext.record_meta` (`run_context.py:154-166`, sin cambios de firma); `redact_secrets` (`revisia/agents/_http.py:107`).
- Produces (§5.1, D9, D14; **lo consume PR-C** en el pipeline):
  - `class RecordFailedError(JournalError)`: `__init__(self, *, stage: str, record_id: str, failure: JournalFailure)`; atributos `stage`, `record_id`, `failure`; mensaje `f"la IA falló de forma determinista en {record_id!r} ({stage}): {failure.message}. Este registro necesita decisión humana (D9); este motor aún no lo lleva al gate: revisa el error o empieza una corrida nueva."`. Al ser `JournalError`, ya está en `_CONFIG_ERRORS` (`pipeline.py:137-145`): el pipeline deshace el `running` y el CLI sale con **rc 2** (`cli.py:294-304`) en vez del bucle de rc 3 de hoy (M15), sin tocar `pipeline.py` ni el CLI. **PR-C** la atrapa en cada etapa **antes** de que llegue a `_CONFIG_ERRORS` (un `except RecordFailedError` alrededor de cada `journaled`) y lleva el registro al gate como `must_label`/campos a rellenar.
  - `journaled(...)` conserva su firma (`journal.py:170-179`). Comportamiento nuevo, en este orden:
    1. Entrada en el diario con `status == "failed"` → `RecordFailedError` sin llamar a `compute` (una línea `failed` es definitiva, §4.2).
    2. Si no hay entrada: instala con `installed(...)` un sink que, por cada meta emitida, llama **en el acto** a `run_ctx.record_meta(meta, stage=journal.stage, record_id=record_id, role=role_of(k) if role_of else None)`, donde `k` es el número de metas `ok` emitidas **antes** que esta (los intentos fallidos de un miembro llevan su rol; supuesto §19; limitación: si un proveedor que no emite ocupa una posición anterior, `k` no lo cuenta y el rol de las metas emitidas después puede desplazarse), y guarda la `LLMCall` resultante y la meta original.
    3. `compute()`. Si lanza `DeterministicCallError`: escribe `JournalEntry(status="failed", output=None, error=JournalFailure(type=type(exc).__name__, message=redact_secrets(str(exc))[:1000], attempts=exc.attempts), metas=<las LLMCall escritas>)` y lanza `RecordFailedError(...) from exc`. Cualquier otra excepción se propaga sin línea de diario (las metas ya están en disco).
    4. Las metas que `compute` devuelve y que **no** se emitieron (comparación por identidad, `is`) se registran después, en orden, con `role_of(i)` por su posición en la lista devuelta (proveedores de terceros sin sink: el sink es opcional, §18.4). Las emitidas no se registran dos veces.
    5. `journal.append(JournalEntry(..., metas=<todas las LLMCall de este registro, en orden>))`.

- [ ] **Step 1: Test que falla** — añadir al final de `tests/test_journal.py`:

```python
# ── Ola 2: registro por intento en el acto y fallo determinista (spec 2026-10-18 §5.1; D9, D14) ──

from revisia.llm.base import DeterministicCallError, TransientCallError  # noqa: E402
from revisia.llm.meta import emit_attempt  # noqa: E402
from revisia.llm.providers.fake import _fabricate_model  # noqa: E402
from revisia.orchestration.journal import RecordFailedError  # noqa: E402
from revisia.provenance.runmeta import RunMeta, sha256_text  # noqa: E402


def _cribar_con(ctx: RunContext, proveedores: list, record_id: str = "a") -> ScreeningDecision:
    miembros = [
        ScreenerMember(provider=p, model_name=f"fake:{i}") for i, p in enumerate(proveedores)
    ]
    registro = SearchRecord(record_id=record_id, title="Estudio")
    return journaled(
        StageJournal(ctx, "screening_ta"),
        record_id=record_id,
        inputs={"n": len(proveedores)},
        model=ScreeningDecision,
        compute=lambda: screen_record(miembros, question="¿X?", criteria="c", record=registro),
        run_ctx=ctx,
        role_of=lambda i: f"member:{i}",
    )


def _llamadas(ctx: RunContext) -> list[LLMCall]:
    return [
        LLMCall.model_validate_json(x) for x in ctx.llm_calls_path.read_text("utf-8").splitlines()
    ]


def _entradas(ctx: RunContext) -> list[JournalEntry]:
    path = StageJournal(ctx, "screening_ta").path
    return [JournalEntry.model_validate_json(x) for x in path.read_text("utf-8").splitlines()]


class _DosIntentos:
    """El 1.er intento no valida y el 2.º sí; entre ambos mira cuántas líneas hay en disco."""

    name = "fake"

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self.lineas_antes_del_segundo: int | None = None

    def structured(self, req, schema):
        emit_attempt(
            self.name,
            "m",
            req,
            sent_prompt=req.prompt,
            response_text="basura",
            attempt=1,
            outcome="invalid_output",
        )
        self.lineas_antes_del_segundo = len(self.ctx.llm_calls_path.read_text("utf-8").splitlines())
        obj = _fabricate_model(schema)
        meta = emit_attempt(
            self.name,
            "m",
            req,
            sent_prompt=req.prompt,
            response_text=obj.model_dump_json(),
            attempt=2,
        )
        return obj, meta


def test_sink_registra_cada_intento_en_el_acto(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    proveedor = _DosIntentos(ctx)
    _cribar_con(ctx, [proveedor])
    assert proveedor.lineas_antes_del_segundo == 1  # el intento 1 ya estaba en disco
    llamadas = _llamadas(ctx)
    assert [(c.attempt, c.outcome, c.role) for c in llamadas] == [
        (1, "invalid_output", "member:0"),
        (2, "ok", "member:0"),
    ]
    (entrada,) = _entradas(ctx)
    assert entrada.metas == llamadas  # la línea del diario lleva el intento fallido y el bueno


def test_fallo_del_segundo_miembro_deja_la_llamada_del_primero_registrada(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    with pytest.raises(TransientCallError):
        _cribar_con(ctx, [ScriptedProvider(), ScriptedProvider(fail_at=1)])
    assert [(c.role, c.outcome) for c in _llamadas(ctx)] == [
        ("member:0", "ok"),
        ("member:1", "transient_error"),
    ]
    assert not StageJournal(
        ctx, "screening_ta"
    ).path.exists()  # B10: sin decisión, con sus llamadas


def test_fallo_determinista_deja_linea_failed_definitiva(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    proveedor = ScriptedProvider(fail_deterministic_at=1)
    with pytest.raises(RecordFailedError) as exc:
        _cribar_con(ctx, [proveedor], "r1")
    assert (exc.value.stage, exc.value.record_id) == ("screening_ta", "r1")
    assert (exc.value.failure.type, exc.value.failure.attempts) == ("DeterministicCallError", 1)
    (entrada,) = _entradas(ctx)
    assert (entrada.status, entrada.output, entrada.error.type) == (
        "failed",
        None,
        "DeterministicCallError",
    )
    assert [c.outcome for c in entrada.metas] == ["deterministic_error"]
    with pytest.raises(RecordFailedError):  # al reanudar: sin llamar otra vez (D9)
        _cribar_con(ctx, [proveedor], "r1")
    assert proveedor.calls == 1


def test_fallo_determinista_redacta_el_mensaje(tmp_path: Path) -> None:
    class _Filtra:
        name = "fake"

        def structured(self, req, schema):
            raise DeterministicCallError(
                "400: clave sk-ant-api03-abcdefghijklmnop0123456789 inválida"
            )

    ctx = RunContext("demo", tmp_path, "T")
    with pytest.raises(RecordFailedError):
        _cribar_con(ctx, [_Filtra()])
    (entrada,) = _entradas(ctx)
    assert "sk-ant" not in entrada.error.message and "<redacted>" in entrada.error.message


def test_metas_devueltas_sin_emitir_se_registran_como_antes(tmp_path: Path) -> None:
    class _Tercero:  # proveedor de terceros: devuelve la meta pero no conoce el sink
        name = "otro"

        def structured(self, req, schema):
            meta = RunMeta(
                provider="otro",
                model="m",
                temperature=0.0,
                prompt_sha256="p",
                response_sha256=sha256_text("r"),
            )
            return _fabricate_model(schema), meta

    ctx = RunContext("demo", tmp_path, "T")
    # El que emite va primero: con el que no emite delante, el rol se desplazaría (§19).
    _cribar_con(ctx, [ScriptedProvider(), _Tercero()])
    assert [(c.provider, c.role) for c in _llamadas(ctx)] == [
        ("fake", "member:0"),
        ("otro", "member:1"),
    ]
    assert len(_entradas(ctx)[0].metas) == 2
```

Cambios de expectativa en `tests/test_reanudacion.py` (D14: el intento fallido ya no se pierde):
- `:150`: `assert len(ctx.llm_calls_path.read_text("utf-8").splitlines()) == 2` → `== 3`, y añadir debajo `assert LLMCall.model_validate_json(ctx.llm_calls_path.read_text("utf-8").splitlines()[-1]).outcome == "transient_error"` (importar `LLMCall` si no está).
- `:161`: `== 4` → `== 5`. `[len(e.metas) for e in entradas] == [2, 2]` no cambia (el intento fallido no pertenece a la entrada que se escribe al reanudar).

Y al final de `tests/test_reanudacion.py` (M15 hasta PR-C: rc 2 con mensaje, sin bucle de rc 3 ni llamada repetida):

```python
def test_fallo_determinista_sale_2_y_no_repite_la_llamada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    from revisia.cli import main
    from revisia.orchestration.journal import RecordFailedError

    proveedor = ScriptedProvider(fail_deterministic_at=1)
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    with pytest.raises(RecordFailedError):
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    assert read_run_info(ctx.run_dir).interruptions == []  # error de configuración, no caída
    assert main(["run", "--resume", str(ctx.run_dir)]) == 2
    assert "necesita decisión humana" in capsys.readouterr().err
    assert proveedor.calls == 1  # la línea failed es definitiva
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_journal.py tests/test_reanudacion.py -v`
Expected: FAIL con `ImportError: cannot import name 'RecordFailedError'`.

- [ ] **Step 3: Implementar** en `revisia/orchestration/journal.py` según Interfaces (la regla de roles y la deduplicación por identidad van en la docstring de `journaled`, con D14 y el porqué: si falla el segundo miembro, la llamada pagada del primero ya está en disco). El docstring del módulo pasa a citar también la Ola 2 (§5.1).

- [ ] **Step 4: Run para verificar que pasa, incluido el auditor**

Run: `uv run pytest -p no:cacheprovider tests/test_journal.py tests/test_reanudacion.py tests/test_errores_deterministas.py -v`
Expected: PASS.

Run (Review Focus 5): `uv run pytest -p no:cacheprovider -n auto tests/test_audit*.py tests/test_auditor_meta_y_estados.py tests/test_corrida_auditoria.py`
Expected: PASS. Si algún check del auditor da FAIL por una línea `transient_error` huérfana, **no se toca `revisia/audit/`** (es de G): se anota el check y el síntoma para §19 y para el plan de PR-G, y se marca ese test `xfail(strict=True, reason="PR-G: <check> no conoce los intentos fallidos (D14)")`.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/journal.py tests/test_journal.py tests/test_reanudacion.py
git commit -m "feat(journal): metas por intento escritas en el acto y línea failed definitiva ante un fallo determinista (D9, D14)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 4: Proveedores API honestos y con D9 (`gemini`, `openai`, `local_openai`, `zai`, `openrouter`, `anthropic`)

**Files:**
- Modify: `revisia/llm/providers/gemini.py:60-96`, `revisia/llm/providers/openai_api.py:49-95`, `revisia/llm/providers/local_openai.py:39-58`, `revisia/llm/providers/anthropic_api.py:63-108`. `openai_compat.py` hereda (sin cambios salvo docstring).
- Test: `tests/test_providers_procedencia.py` (nuevo). Sus dobles de cliente son provisionales: `tests/test_providers_api.py` de PR-H solo existe tras el rebase, y en la Tarea 12 ambos ficheros pasan a usar los mismos dobles (M8).

**Interfaces:**
- Consumes: `emit_attempt`, `classify_sdk_error`, `error_for`, `sdk_version` (T2); `canonical_sha256`.
- Produces (§5.2, §5.3 último punto, A6, A7, D9):
  - Cada intento (cada llamada al SDK) emite **una** meta con `emit_attempt`: `sent_prompt` = el texto de usuario que viajó (`gemini`, `openai`, `anthropic`: `req.prompt`; `local_openai`/`zai`/`openrouter` en `structured`: el prompt aumentado con el schema); `schema_sha256 = canonical_sha256(schema.model_json_schema())` cuando el schema viaja aparte (`gemini` `response_schema`, `openai` `response_format`, `anthropic` tool), `None` cuando va en el texto (`local_openai`); `model_version` de la respuesta (`model_version` en Gemini, `model` en OpenAI y Anthropic) ⇒ `model_source="backend"`; `backend_version = sdk_version("google-genai" | "openai" | "anthropic")`; `latency_ms` = `time.perf_counter()` alrededor de la llamada, en ms enteros.
  - `_config(req, **extra)` de Gemini, `_messages`, `_kwargs` y `_client` **conservan su firma** (los dobles de PR-H y `tests/test_sdk_superficie.py` los sustituyen).
  - Errores (D9): excepción del SDK con `classify_sdk_error(exc) != None` → meta con ese `outcome`, `response_text=""`, y `raise error_for(outcome)(f"{self.name}: {exc}") from exc`; con `None` → se propaga sin meta. Sin respuesta estructurada (`parsed is None` en OpenAI, sin `tool_use` en Anthropic), bloqueo de contenido en Gemini (`resp.text` vacío con `getattr(getattr(resp, "prompt_feedback", None), "block_reason", None)` o el `finish_reason` del primer candidato, leído con `getattr(..., None)` en cada paso, en `{"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"}`; los dobles de PR-H no traen esos atributos y no deben romper, M9) o salida que no valida → meta `invalid_output` (bloqueo: `deterministic_error`) y `DeterministicCallError` con los textos de hoy (`"salida estructurada"`, `"tool_use"`) más `"bloqueo de contenido"` en Gemini. Un intento por llamada (sin reintentos en API; §17).

- [ ] **Step 1: Test que falla** — crear `tests/test_providers_procedencia.py`:

```python
"""Proveedores API: lo aplicado, el texto enviado y D9 (spec 2026-10-18 §5.2-§5.3; A6, A7, D9)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from revisia.llm import meta as meta_mod
from revisia.llm.base import DeterministicCallError, LLMRequest, TransientCallError
from revisia.llm.providers.anthropic_api import AnthropicProvider
from revisia.llm.providers.gemini import GeminiProvider
from revisia.llm.providers.local_openai import LocalOpenAIProvider
from revisia.llm.providers.openai_api import OpenAIProvider
from revisia.llm.providers.openai_compat import OpenRouterProvider, ZaiProvider
from revisia.provenance.runmeta import canonical_sha256, sha256_text
from revisia.provenance.sink import collecting


class Salida(BaseModel):
    etiqueta: str
    n: int


REQ = LLMRequest(prompt="¿Incluir?", system="Eres un cribador.", temperature=0.3, seed=42)
V1 = sha256_text("Eres un cribador.\n¿Incluir?")
JSON_OK = '{"etiqueta": "include", "n": 1}'


class _ErrorSDK(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"Error code: {status}")
        self.status_code = status


def _respuesta_openai(content: str | None = JSON_OK, parsed: Any = "auto") -> Any:
    obj = Salida(etiqueta="include", n=1) if parsed == "auto" else parsed
    msg = SimpleNamespace(content=content, parsed=obj, refusal=None if obj else "no")
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg)],
        model="gpt-x-2026",
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
    )


class _OpenAI:
    def __init__(self, *, fallo: Exception | None = None, **resp: Any) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.fallo, self.resp = fallo, resp
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._llamar))
        self.beta = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=self._llamar))
        )

    def _llamar(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        if self.fallo is not None:
            raise self.fallo
        return _respuesta_openai(**self.resp)


class _Gemini:
    def __init__(
        self,
        *,
        fallo: Exception | None = None,
        texto: str | None = JSON_OK,
        bloqueo: str | None = None,
    ) -> None:
        self.fallo, self.texto, self.bloqueo = fallo, texto, bloqueo
        self.models = SimpleNamespace(generate_content=self._generar)

    def _generar(self, **kw: Any) -> Any:
        if self.fallo is not None:
            raise self.fallo
        return SimpleNamespace(
            text=self.texto,
            parsed=None,
            model_version="gemini-x-001",
            prompt_feedback=SimpleNamespace(block_reason=self.bloqueo),
            candidates=[],
            usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=5),
        )


class _Anthropic:
    def __init__(self, *, fallo: Exception | None = None) -> None:
        self.fallo = fallo
        self.messages = SimpleNamespace(create=self._crear)

    def _crear(self, **kw: Any) -> Any:
        if self.fallo is not None:
            raise self.fallo
        bloques = (
            [SimpleNamespace(type="tool_use", input={"etiqueta": "include", "n": 1})]
            if "tools" in kw
            else [SimpleNamespace(type="text", text="hola")]
        )
        return SimpleNamespace(
            content=bloques,
            model="claude-x-2026",
            usage=SimpleNamespace(input_tokens=9, output_tokens=2),
        )


def _con_cliente(monkeypatch: pytest.MonkeyPatch, nombre: str, cliente: Any) -> Any:
    monkeypatch.setenv("ZAI_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    clases = {
        "gemini": GeminiProvider,
        "openai": OpenAIProvider,
        "local_openai": LocalOpenAIProvider,
        "zai": ZaiProvider,
        "openrouter": OpenRouterProvider,
        "anthropic": AnthropicProvider,
    }
    proveedor = clases[nombre]("m")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    if nombre == "gemini":
        monkeypatch.setattr(
            proveedor,
            "_config",
            lambda req, **extra: {"temperature": req.temperature, "seed": req.seed, **extra},
        )
    return proveedor


def _cliente_de(nombre: str, **kw: Any) -> Any:
    return {"gemini": _Gemini, "anthropic": _Anthropic}.get(nombre, _OpenAI)(**kw)


TODOS = ["gemini", "openai", "local_openai", "zai", "openrouter", "anthropic"]


@pytest.mark.parametrize("nombre", TODOS)
@pytest.mark.parametrize(
    ("status", "error", "outcome"),
    [
        (400, DeterministicCallError, "deterministic_error"),
        (403, TransientCallError, "transient_error"),
        (429, TransientCallError, "transient_error"),
        (503, TransientCallError, "transient_error"),
    ],
)
def test_error_4xx_es_determinista_y_429_transitorio(
    monkeypatch: pytest.MonkeyPatch, nombre: str, status: int, error: type, outcome: str
) -> None:
    proveedor = _con_cliente(monkeypatch, nombre, _cliente_de(nombre, fallo=_ErrorSDK(status)))
    with collecting() as metas, pytest.raises(error, match=str(status)):
        proveedor.structured(REQ, Salida)
    (meta,) = metas
    assert (meta.outcome, meta.attempt, meta.response_sha256) == (outcome, 1, sha256_text(""))


@pytest.mark.parametrize("nombre", TODOS)
def test_error_desconocido_se_propaga_sin_clasificar(
    monkeypatch: pytest.MonkeyPatch, nombre: str
) -> None:
    proveedor = _con_cliente(monkeypatch, nombre, _cliente_de(nombre, fallo=ValueError("bug")))
    with collecting() as metas, pytest.raises(ValueError, match="bug"):
        proveedor.complete(REQ)
    assert metas == []


@pytest.mark.parametrize(
    ("nombre", "seed", "source"),
    [
        ("gemini", 42, "backend"),
        ("openai", 42, "backend"),
        ("local_openai", 42, "backend"),
        ("zai", 42, "backend"),
        ("openrouter", 42, "backend"),
        ("anthropic", None, "backend"),
    ],
)
def test_runmeta_v2_aplicado_por_proveedor(
    monkeypatch: pytest.MonkeyPatch, nombre: str, seed: int | None, source: str
) -> None:
    proveedor = _con_cliente(monkeypatch, nombre, _cliente_de(nombre))
    with collecting() as metas:
        meta = proveedor.complete(REQ).meta
    assert metas[0] is meta
    assert (meta.seed_applied, meta.temperature_applied, meta.model_source) == (seed, 0.3, source)
    assert (meta.seed, meta.temperature) == (42, 0.3)  # lo pedido no cambia
    assert meta.prompt_sha256 == V1 and meta.latency_ms is not None and meta.latency_ms >= 0


@pytest.mark.parametrize("nombre", ["gemini", "openai", "anthropic"])
def test_schema_que_viaja_aparte_tiene_su_hash_y_no_toca_el_del_prompt(
    monkeypatch: pytest.MonkeyPatch, nombre: str
) -> None:
    _, meta = _con_cliente(monkeypatch, nombre, _cliente_de(nombre)).structured(REQ, Salida)
    assert (
        meta.schema_sha256 == canonical_sha256(Salida.model_json_schema())
        and meta.prompt_sha256 == V1
    )


@pytest.mark.parametrize("nombre", ["local_openai", "zai", "openrouter"])
def test_schema_en_el_texto_entra_en_el_hash_del_prompt(
    monkeypatch: pytest.MonkeyPatch, nombre: str
) -> None:
    cliente = _OpenAI()
    _, meta = _con_cliente(monkeypatch, nombre, cliente).structured(REQ, Salida)
    enviado = cliente.llamadas[0]["messages"][-1]["content"]
    assert (
        '"etiqueta"' in enviado
        and meta.prompt_sha256 == sha256_text(f"Eres un cribador.\n{enviado}") != V1
    )
    assert meta.schema_sha256 is None


def test_backend_version_es_la_del_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(meta_mod.metadata, "version", lambda dist: {"openai": "2.44.0"}[dist])
    assert (
        _con_cliente(monkeypatch, "openai", _OpenAI()).complete(REQ).meta.backend_version
        == "2.44.0"
    )


def test_salidas_rechazadas_son_deterministas(monkeypatch: pytest.MonkeyPatch) -> None:
    with collecting() as metas, pytest.raises(DeterministicCallError, match="salida estructurada"):
        _con_cliente(monkeypatch, "openai", _OpenAI(parsed=None)).structured(REQ, Salida)
    assert metas[0].outcome == "invalid_output"
    with pytest.raises(DeterministicCallError, match="bloqueo de contenido"):
        _con_cliente(monkeypatch, "gemini", _Gemini(texto=None, bloqueo="SAFETY")).complete(REQ)
    with collecting() as metas, pytest.raises(DeterministicCallError):
        _con_cliente(monkeypatch, "local_openai", _OpenAI(content="no es json")).structured(
            REQ, Salida
        )
    assert metas[0].outcome == "invalid_output"
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_providers_procedencia.py -v`
Expected: FAIL (`seed_applied` es `None`, sin metas en el sink, errores sin clasificar).

- [ ] **Step 3: Implementar** según Interfaces. `_meta` de cada proveedor desaparece o pasa a delegar en `emit_attempt`; el `structured` de `local_openai` (`local_openai.py:39-58`) construye `augmented` como hoy y lo pasa como `sent_prompt`. Docstrings: qué se aplica de verdad en cada backend (A6; Anthropic no admite `seed`).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_providers_procedencia.py tests/test_llm_registry.py tests/test_fakes.py -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/llm/providers/gemini.py revisia/llm/providers/openai_api.py revisia/llm/providers/local_openai.py revisia/llm/providers/openai_compat.py revisia/llm/providers/anthropic_api.py tests/test_providers_procedencia.py
git commit -m "feat(llm): proveedores API con lo aplicado, texto enviado, versión del SDK y errores transitorio/determinista (A6, A7, D9)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 5: `agent` informa el modelo y `agent_driver` no aprueba solo (A8)

**Files:**
- Modify: `revisia/llm/providers/agent.py:41-43` (`AgentCallback`), `:85-145` (`AgentProvider`), clase nueva `AgentReply` tras `AgentCallback`.
- Modify: `revisia/agent_driver.py:37` (`auto_approve: bool = False`), `:53-54` (docstring de `auto_approve`), `:70-80` (mensaje de pausa).
- Modify: `revisia/llm/preflight.py:182-209` (`_stage_issues`: aviso de miembros `agent`).
- Test: `tests/test_agent_provider.py`, `tests/test_preflight.py` (añadir).

**Interfaces:**
- Consumes: `emit_attempt`, `error_for` (T2); `screeners_for` (`config.py:221`).
- Produces (§5.4, A8):
  - `@dataclass(frozen=True, slots=True) class AgentReply`: `payload: BaseModel | dict | str`, `model: str | None = None`, `usage: dict | None = None`. `AgentCallback = Callable[[LLMRequest, type[BaseModel] | None], BaseModel | dict | str | AgentReply]`.
  - `AgentProvider`: con `AgentReply.model` → `model_version = reply.model`, `model_source = "callback"`; sin él → `model_version=None`, `model_source = "config"`. `model` sigue siendo el de la config («lo pedido», como en los demás proveedores; supuesto §19). Tokens de `usage["input_tokens"]`/`usage["output_tokens"]`. Una meta por llamada al callback; salida que no valida → meta `invalid_output` y `DeterministicCallError` con el texto de hoy (`"no produjo una salida válida para {schema}"`); sin callback → `RuntimeError` de hoy, sin meta.
  - `preflight._stage_issues`: si `screeners_for("screening_ta")` tiene ≥ 2 miembros `provider: agent` → aviso en `screening_ta`: `"el callback no informa el modelo: dos miembros `agent` pueden ser el mismo modelo (devuelve AgentReply(model=…) para registrarlo)"` (en `validate` y en `run`).
  - `run_review_with_agent(..., auto_approve: bool = False, ...)`; con `result.status == "paused"` imprime `f"\n⏸ PAUSED · {result.message}"` (la misma línea que el CLI, `cli.py:389-390`).

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_agent_provider.py`:

```python
# ── Ola 2: el callback informa el modelo; el driver no aprueba solo (spec 2026-10-18 §5.4; A8) ──

import inspect  # noqa: E402
from pathlib import Path  # noqa: E402

from revisia.agent_driver import run_review_with_agent  # noqa: E402
from revisia.llm.base import DeterministicCallError  # noqa: E402
from revisia.llm.providers.agent import AgentReply  # noqa: E402
from revisia.provenance.sink import collecting  # noqa: E402
from revisia.schemas.records import SearchRecord  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def test_agent_reply_informa_el_modelo() -> None:
    def cb(req, schema):
        return AgentReply(
            payload={"include": True, "reason": "x"},
            model="claude-opus-5-5",
            usage={"input_tokens": 10, "output_tokens": 3},
        )

    with agent.use_agent_callback(cb), collecting() as metas:
        _, meta = _provider().structured(LLMRequest(prompt="¿incluir?"), _Decision)
    assert metas == [meta]
    assert (meta.model_version, meta.model_source, meta.input_tokens, meta.output_tokens) == (
        "claude-opus-5-5",
        "callback",
        10,
        3,
    )
    assert meta.seed_applied is None and meta.temperature_applied is None


def test_agent_sin_modelo_en_la_respuesta_es_config() -> None:
    with agent.use_agent_callback(lambda req, schema: {"include": False, "reason": "y"}):
        _, meta = _provider().structured(LLMRequest(prompt="x"), _Decision)
    assert (meta.model_version, meta.model_source) == (None, "config")


def test_agent_salida_invalida_es_determinista() -> None:
    with agent.use_agent_callback(lambda req, schema: {"x": 1}), collecting() as metas:
        with pytest.raises(DeterministicCallError, match="_Decision"):
            _provider().structured(LLMRequest(prompt="x"), _Decision)
    assert [m.outcome for m in metas] == ["invalid_output"]


def test_agent_driver_no_auto_aprueba_por_defecto(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    assert inspect.signature(run_review_with_agent).parameters["auto_approve"].default is False

    def _busqueda(_q: str, n: int) -> list[SearchRecord]:
        return [SearchRecord(record_id="rec-1", title="LLM screening", source_db="OpenAlex")][:n]

    resultado = run_review_with_agent(
        EXAMPLE, lambda req, schema: {}, timestamp="T", runs_root=tmp_path, search_fn=_busqueda
    )
    assert resultado.status == "paused"
    salida = capsys.readouterr().out
    assert "⏸ PAUSED ·" in salida and "revisia run --resume" in salida
```

Y en `tests/test_preflight.py`:

```python
def test_preflight_avisa_de_dos_miembros_agent_sin_modelo_informado(proto_dir: Path) -> None:
    protocolo = _proto(
        llm={"default": {"provider": "fake", "model": "f"}},
        ensemble_llm={
            "screening_ta": [
                {"provider": "agent", "model": "opus"},
                {"provider": "agent", "model": "sonnet"},
            ]
        },
    )
    with use_agent_callback(lambda _req, _schema: {}):
        for contexto in ("validate", "run"):
            report = _run(protocolo, proto_dir, context=contexto)
            assert "dos miembros `agent` pueden ser el mismo modelo" in _messages(report.warnings)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_agent_provider.py tests/test_preflight.py -v`
Expected: FAIL con `ImportError: cannot import name 'AgentReply'`.

- [ ] **Step 3: Implementar** según Interfaces (docstring del módulo `agent.py`: un ejemplo con `AgentReply`; A8). La docstring de `run_review_with_agent` dice que pausa en cada gate salvo `auto_approve=True` explícito (solo demos: no publicable).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_agent_provider.py tests/test_preflight.py tests/test_reanudacion.py -v`
Expected: PASS (`test_agent_driver_reanuda_con_run_dir` ya pasa `auto_approve` explícito).

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/llm/providers/agent.py revisia/agent_driver.py revisia/llm/preflight.py tests/test_agent_provider.py tests/test_preflight.py
git commit -m "feat(agent): AgentReply con el modelo que contestó y agent_driver sin auto-aprobación por defecto (A8)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 6: `environment` en `run.json` y en el manifiesto; corridas 0.8 no reanudables (A15, D12)

**Files:**
- Modify: `revisia/orchestration/snapshot.py:76-81` (`prompt_fingerprint`), `:106-177` (`ensure_snapshot`), funciones y clase nuevas.
- Modify: `revisia/orchestration/run_context.py:56-61` (docstring de `LegacyRunError`: la clase cubre ya dos casos, sin `run.json` (anterior a la Ola 1, D13) y, por su subclase `PreOla2RunError`, sin `environment` (anterior a la Ola 2, D12); ambos rc 2, M3) y `:190-238` (`write_manifest`).
- Modify: `revisia/schemas/artifacts.py` (`RunInfo`: se retira `prompt_sha256`, `artifacts.py:125` en `c1af7c3`; docstring de `RunInfo`).
- Modify: `tests/conftest.py:53-70`: marca `git_real` en `pytest_configure` y fixture autouse `_git_state_fijo` que, salvo en los tests con esa marca, sustituye `snapshot.git_state` por `lambda *a, **k: ("0" * 40, False)` (ningún test lanza `git`; I8).
- Modify: `tests/test_snapshot.py:72-78`: la aserción sobre `info.prompt_sha256` pasa a `environment.prompt_templates`, con el conjunto **derivado**: `assert {f"{a}/{v}.md" for a, v in PROMPT_VERSIONS.items()} | {f"rob/{t}.yml" for t in get_args(RoBTool)} <= set(info.environment.prompt_templates)` (importar `get_args`, `PROMPT_VERSIONS` y `RoBTool` de `revisia.schemas.rob`). **E₁ edita esas mismas líneas** (sus especificaciones y plantillas): al rebasar, se conserva esta forma derivada. Y `:107`: `_run_info(ctx).prompt_sha256` → `_run_info(ctx).environment.prompt_templates`.
- Test: `tests/test_snapshot.py`, `tests/test_run_context.py` (añadir).

**Interfaces:**
- Consumes: `Environment`, `ENVIRONMENT_PACKAGES`, `RunInfo` v2 (PR-0 T5); `tool_spec_fingerprint` (PR-0 T10, importado por nombre en `snapshot.py` para que los tests lo sustituyan); `template_fingerprint` (T1); `LegacyRunError` (`run_context.py:56`).
- Produces (§5.5, §4.2 «RunInfo v2», relaciones 19 y 20, D12; **lo consume PR-G**):
  - `REPO_ROOT: Path = Path(revisia.__file__).resolve().parent.parent`.
  - `git_state(repo_root: Path | None = None) -> tuple[str | None, bool | None]`: si `not (root / ".git").exists()` → `(None, None)` (`exists`, no `is_dir`: en un worktree `.git` es un fichero); si no, `git -C <root> rev-parse HEAD` y `git -C <root> status --porcelain --untracked-files=no` con `timeout=5`, `capture_output`, `text`; cualquier fallo → `(None, None)`. `functools.lru_cache` (una vez por proceso; la docstring lo dice). `collect_environment` la busca como atributo del módulo en cada llamada (la fixture la sustituye).
  - `installed_packages() -> dict[str, str]`: `importlib.metadata.version` de cada nombre de `ENVIRONMENT_PACKAGES` presente, en ese orden.
  - `collect_environment(*, prompt_templates: Mapping[str, str]) -> Environment`: `engine_version=revisia.__version__`, `python_version=platform.python_version()`, `python_implementation=platform.python_implementation()`, `platform=platform.platform()`, `git_commit`/`git_dirty` de `git_state()`, `packages=installed_packages()`, `prompt_templates=dict(prompt_templates)`, `created_utc=utc_now_iso()`.
  - `prompt_fingerprint() -> dict[str, str]`: `template_fingerprint(PROMPTS_DIR)` (T1) más `tool_spec_fingerprint()` (claves `"rob/<tool>.yml"`).
  - `class PreOla2RunError(LegacyRunError)`: mensaje (D12): `f"{run_dir}: corrida anterior a la Ola 2 (motor < 0.9): sin procedencia aplicada ni verificación por juez; regenera la corrida con el motor actual (`revisia run <protocolo>`)."`. Al ser `LegacyRunError`, el pipeline ya la trata como error de configuración y el CLI sale con rc 2 (`pipeline.py:137-145`, `cli.py:294-304`) sin tocar `pipeline.py`.
  - `ensure_snapshot`: corrida nueva → `RunInfo(..., environment=collect_environment(prompt_templates=prompt_fingerprint()))` (sin `prompt_sha256`); al reanudar, `info.environment is None` → `PreOla2RunError` antes de tocar nada; la comparación de huellas usa `info.environment.prompt_templates`, y una clave `rob/<tool>.yml` distinta se nombra `revisia/rob/tools/<tool>.yml` en `ProtocolMismatchError.files`.
  - `write_manifest`: añade `"environment": info.environment.model_dump(mode="json")` (bloque de primer nivel, tras `run`) cuando `run.json` lo tiene; `models_used` y `deterministic_token_level` se calculan solo sobre las llamadas con `outcome == "ok"` (relación 20); `llm_calls` sigue listando todas. **Desfase conocido con el auditor de hoy** (`checks_flow.py:1255-1296`, relación «§9.3 · models_used == modelos de llm_calls», dentro del check `arithmetic`): recalcula sobre todas las llamadas, así que un modelo con solo intentos fallidos da FAIL hasta PR-G₂; queda fijado en un `xfail(strict=True)` (I5).

- [ ] **Step 1: Tests que fallan** — añadir al final de `tests/test_snapshot.py`:

```python
# ── Ola 2: entorno de la corrida y corridas 0.8 (spec 2026-10-18 §5.5; A15, D12) ──

import platform  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import get_args  # noqa: E402

from audit_fixtures import auditar, fila  # noqa: E402
from fakes import ScriptedProvider  # noqa: E402

from revisia.cli import main  # noqa: E402
from revisia.orchestration import pipeline as pipeline_mod  # noqa: E402
from revisia.orchestration.snapshot import PreOla2RunError, git_state  # noqa: E402
from revisia.prompts import PROMPT_VERSIONS  # noqa: E402
from revisia.schemas.artifacts import LLMCall  # noqa: E402
from revisia.schemas.rob import RoBTool  # noqa: E402

VIGENTES = {f"{a}/{v}.md" for a, v in PROMPT_VERSIONS.items()}
ESPECIFICACIONES = {f"rob/{t}.yml" for t in get_args(RoBTool)}


def _completa(tmp_path: Path) -> RunContext:
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
    return ctx


def _llamadas(ctx: RunContext) -> list[LLMCall]:
    lineas = ctx.llm_calls_path.read_text("utf-8").splitlines()
    return [LLMCall.model_validate_json(x) for x in lineas]


def test_environment_en_run_json_y_manifest_coinciden(tmp_path: Path) -> None:
    ctx = _completa(tmp_path)
    crudo = json.loads((ctx.run_dir / "run.json").read_text(encoding="utf-8"))
    assert "prompt_sha256" not in crudo  # D12: su sitio es environment.prompt_templates
    env = _run_info(ctx).environment
    assert env is not None and env.engine_version == __version__
    assert env.python_version == platform.python_version()
    assert env.python_implementation == platform.python_implementation()
    assert (env.git_commit, env.git_dirty) == ("0" * 40, False)  # fixture autouse
    assert "pydantic" in env.packages and env.prompt_templates == prompt_fingerprint()
    assert VIGENTES | ESPECIFICACIONES <= set(env.prompt_templates)
    manifest = yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))
    assert manifest["environment"] == env.model_dump(mode="json")


def test_prompt_template_sha_coincide_con_environment(tmp_path: Path) -> None:
    ctx = _completa(tmp_path)
    plantillas = _run_info(ctx).environment.prompt_templates
    con_plantilla = [c for c in _llamadas(ctx) if c.prompt_template is not None]
    assert {c.prompt_template for c in con_plantilla} == VIGENTES
    for c in con_plantilla:  # relación 19
        assert c.prompt_template_sha256 == plantillas[c.prompt_template]


@pytest.mark.git_real
def test_git_commit_solo_desde_un_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    git_state.cache_clear()
    assert git_state(tmp_path) == (None, None)  # sin .git
    git_state.cache_clear()  # la respuesta está cacheada por argumento
    (tmp_path / ".git").write_text("gitdir: ../otro", encoding="utf-8")  # worktree: fichero
    respuestas = {"rev-parse": "abc123\n", "status": " M x.py\n"}

    def _git(cmd, **kw):
        return SimpleNamespace(returncode=0, stdout=respuestas[cmd[3]], stderr="")

    monkeypatch.setattr(snapshot_mod.subprocess, "run", _git)
    assert git_state(tmp_path) == ("abc123", True)
    git_state.cache_clear()

    def _cuelga(cmd, **kw):
        raise snapshot_mod.subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(snapshot_mod.subprocess, "run", _cuelga)
    assert git_state(tmp_path) == (None, None)
    git_state.cache_clear()


def _como_corrida_08(ctx: RunContext) -> None:
    ruta = ctx.run_dir / "run.json"
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    crudo.pop("environment")
    crudo["prompt_sha256"] = {"screening/v1.md": "a" * 64}
    ruta.write_text(json.dumps(crudo), encoding="utf-8")


def test_reanudar_una_corrida_08_sale_2_con_el_mensaje_de_d12(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda).status == "paused"
    _como_corrida_08(ctx)
    with pytest.raises(PreOla2RunError, match="anterior a la Ola 2") as exc:
        run_pipeline(protocol, None, ctx, search_fn=_busqueda)
    assert isinstance(exc.value, LegacyRunError)
    assert main(["run", "--resume", str(ctx.run_dir)]) == 2
    assert "regenera la corrida con el motor actual" in capsys.readouterr().err


def test_especificacion_de_rob_alterada_se_nombra_al_reanudar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    alterada = {**snapshot_mod.tool_spec_fingerprint(), "rob/RoB2.yml": "0" * 64}
    monkeypatch.setattr(snapshot_mod, "tool_spec_fingerprint", lambda: alterada)
    with pytest.raises(ProtocolMismatchError) as exc:
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    assert exc.value.files == ["revisia/rob/tools/RoB2.yml"]


@pytest.mark.xfail(strict=True, reason="PR-G₂: relación 20 sobre llamadas ok")
def test_modelo_con_solo_intentos_fallidos_audita_sin_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # El manifiesto cuenta solo llamadas ok (relación 20); el auditor de hoy
    # (checks_flow.py:1255-1296) recalcula sobre todas y da FAIL en `arithmetic`.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    fallido = ScriptedProvider("solo-fallo", fail_at=1)
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: fallido)
    with pytest.raises(RunInterrupted):
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    monkeypatch.setattr(
        pipeline_mod, "build_provider", lambda cfg: ScriptedProvider(model=cfg.model)
    )
    resultado = run_pipeline(
        protocol, None, ctx, auto_approve=True, search_fn=_busqueda, fetch_fn=fetch_disponible
    )
    assert resultado.status == "completed"
    assert (
        "fake:solo-fallo"
        not in yaml.safe_load((ctx.run_dir / "manifest.yml").read_text(encoding="utf-8"))[
            "models_used"
        ]
    )
    aritmetica = fila(auditar(ctx.run_dir), "arithmetic")
    assert not (aritmetica.status == "FAIL" and "models_used" in aritmetica.detail)
```

(Importar `RunInterrupted` de `revisia.orchestration.run_context` junto a `LegacyRunError` en la cabecera del fichero.)

Y en `tests/test_run_context.py`:

```python
def test_manifest_models_used_solo_con_llamadas_ok(tmp_path: Path) -> None:
    ctx = RunContext("demo", tmp_path, "T")
    ctx.record_meta(_meta("fake-1"), stage="screening_ta", record_id="a")
    fallida = _meta("solo-fallo").model_copy(
        update={"outcome": "transient_error", "deterministic": False}
    )
    ctx.record_meta(fallida, stage="screening_ta", record_id="b")
    ruta = ctx.write_manifest(protocol_snapshot={}, counts={})
    manifest = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    assert manifest["models_used"] == ["fake:fake-1"]  # relación 20: solo llamadas ok
    assert manifest["deterministic_token_level"] is True
    assert len(manifest["llm_calls"]) == 2  # el intento fallido sigue listado
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_snapshot.py tests/test_run_context.py -v`
Expected: FAIL con `ImportError: cannot import name 'PreOla2RunError'`.

- [ ] **Step 3: Implementar** según Interfaces. Docstring del módulo `snapshot.py`: el entorno se escribe una vez al crear la corrida (A15) y su `prompt_templates` es la referencia de la relación 19; por qué una corrida sin `environment` no se reanuda (D12: mezclaría metas v1 y v2 en el mismo `llm_calls.jsonl`). Comprobar con `grep -rn "prompt_sha256" revisia/audit revisia/exports revisia/cli.py` que nada lee `RunInfo.prompt_sha256` (verificado en `c1af7c3`: solo `snapshot.py`).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_snapshot.py tests/test_run_context.py tests/test_cli_reanudacion.py tests/test_errores_deterministas.py tests/test_reanudacion.py -v`
Expected: PASS, con `test_modelo_con_solo_intentos_fallidos_audita_sin_fail` en `XFAIL` (si sale `XPASS`, el auditor ya cuenta solo llamadas `ok`: quitar el marcador y anotarlo).

Run: `uv run pytest -p no:cacheprovider -n auto tests/test_audit*.py tests/test_corrida_auditoria.py`
Expected: PASS (el auditor ignora el bloque nuevo; si un check lo rechaza, mismo protocolo que en la Tarea 3, Step 4).

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/orchestration/snapshot.py revisia/orchestration/run_context.py revisia/schemas/artifacts.py tests/conftest.py tests/test_snapshot.py tests/test_run_context.py
git commit -m "feat(snapshot): environment en run.json y manifest, especificaciones de RoB en la huella y corridas 0.8 con rc 2 (A15, D12)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 7: `metodologia.md` y `checklist_traice.md` dicen qué se aplicó (M2, M6 de trAIce)

**Files:**
- Modify: `revisia/exports/methods.py:237-241` (párrafo «Uso de IA (PRISMA-trAIce)» de `render_methods`).
- Modify: `revisia/exports/checklist.py:541-549` (cabecera de `render_traice_checklist`) y dos secciones nuevas antes de `## Autonomía efectiva y decisión por gate`.
- Test: `tests/test_declaracion_procedencia.py` (nuevo).

**Interfaces:**
- Consumes: `APPLIED_PARAMS`, `emit_attempt` (T2); `stages_in_use` (`preflight.py:152-179`); `RunMeta` v2. **Sin cambiar las firmas** de `render_methods` ni de `render_traice_checklist` (el pipeline no se toca: `methods` deriva lo aplicado del protocolo y de `APPLIED_PARAMS`, que los proveedores cumplen por test; `checklist` lo lee de las metas reales; supuesto §19).
- Produces (§5.5):
  - `_decimal(x: float) -> str` en `methods.py` (`str(x).replace(".", ",")`; `0.0` → `"0,0"`).
  - `methods`: la frase `Parámetros (temperatura/top_p/seed) y hash de prompt registrados por llamada en manifest.yml.` se sustituye por `Parámetros por etapa: {etapas}. Hash del texto enviado y plantilla de prompt con versión registrados por llamada en llm_calls.jsonl y manifest.yml.`, con `{etapas}` = para cada `(where, cfg)` de `stages_in_use(protocol)`, unidos con `" · "`: `f"{where} ({cfg.provider}:{cfg.model}): temperatura declarada {_decimal(cfg.temperature)}; {estado}"` con `estado = "aplicada"` si `"temperature" ∈ APPLIED_PARAMS[cfg.provider]`, si no ``f"no aplicable en `{cfg.provider}`"``; y, si `cfg.seed is not None`, `f"; seed declarada {cfg.seed}; {estado_seed}"` con la misma regla.
  - `checklist`: la línea `Total de llamadas a IA registradas` pasa a `f"- Llamadas a IA registradas: {n_ok} con respuesta válida; {n_fallidas} intentos fallidos (registrados también, D14)"`; `Modelos usados` sale solo de las metas `ok`; la línea de prompts pasa a `"- Prompts: plantillas versionadas en revisia/prompts/ ({plantillas}); hash del texto enviado (prompt_sha256) y de la plantilla (prompt_template_sha256) por llamada."` con `{plantillas}` = las `prompt_template` distintas de las metas `ok`, ordenadas, o `"ninguna registrada"`. Secciones nuevas: `## Modelos y versiones (M2)` con una línea por `(provider, model)` de las metas `ok`: `f"- {provider}:{model}: versión del modelo {versiones o 'no informada'} (origen: {model_source}); backend {backend_version o 'no informado'}"`; y `## Parámetros aplicados (M6)` con una línea por `(provider, model)` de las metas `ok`: `f"- {provider}:{model}: temperatura declarada {t}; {'aplicada' si alguna meta `ok` tiene temperature_applied no nulo, si no f'no aplicable en `{provider}`'}"`, más el mismo tramo para `seed` si alguna meta `ok` la pidió. Todo lo que el checklist cuenta o lista, salvo el número de intentos fallidos, sale **solo de las metas `ok`** (M11; coherente con la relación 20).

- [ ] **Step 1: Test que falla** — crear `tests/test_declaracion_procedencia.py`:

```python
"""Qué se aplicó de verdad, dicho en metodologia.md y checklist_traice.md (spec 2026-10-18 §5.5)."""

from __future__ import annotations

from revisia.config import ReviewProtocol
from revisia.exports import PrismaCounts, render_methods, render_traice_checklist
from revisia.llm.base import LLMRequest
from revisia.llm.meta import emit_attempt


def _proto(llm: dict) -> ReviewProtocol:
    return ReviewProtocol.model_validate(
        {
            "slug": "d",
            "title": "D",
            "question": {"text": "¿X?", "framework": "PEO", "components": {"P": "x"}},
            "llm": llm,
        }
    )


def test_metodologia_declara_temperatura_no_aplicable_en_claude_code() -> None:
    md = render_methods(
        protocol=_proto({"default": {"provider": "claude_code", "model": "opus"}}),
        counts=PrismaCounts(),
    )
    assert "temperatura declarada 0,0; no aplicable en `claude_code`" in md
    assert "Parámetros (temperatura/top_p/seed)" not in md


def test_metodologia_declara_lo_aplicado_por_proveedor() -> None:
    md = render_methods(
        protocol=_proto(
            {
                "default": {"provider": "gemini", "model": "g", "seed": 42},
                "sintesis": {"provider": "anthropic", "model": "c", "temperature": 0.2, "seed": 7},
            }
        ),
        counts=PrismaCounts(),
    )
    assert (
        "extraccion (gemini:g): temperatura declarada 0,0; aplicada; seed declarada 42; aplicada"
        in md
    )
    assert (
        "sintesis (anthropic:c): temperatura declarada 0,2; aplicada; "
        "seed declarada 7; no aplicable en `anthropic`" in md
    )


def test_traice_cuenta_intentos_versiones_y_parametros_aplicados() -> None:
    req = LLMRequest(prompt="p", temperature=0.0, prompt_template="screening/v1.md")
    metas = [
        emit_attempt(
            "claude_code",
            "opus",
            req,
            sent_prompt="p",
            response_text="x",
            attempt=1,
            outcome="invalid_output",
            backend_version="2.9.0",
        ),
        emit_attempt(
            "claude_code",
            "opus",
            req,
            sent_prompt="p",
            response_text="y",
            attempt=2,
            backend_version="2.9.0",
        ),
        emit_attempt(
            "gemini",
            "g",
            req,
            sent_prompt="p",
            response_text="z",
            model_version="g-001",
            backend_version="2.10.0",
        ),
        emit_attempt(
            "gemini",
            "solo-fallo",
            req,
            sent_prompt="p",
            response_text="",
            outcome="transient_error",
        ),
    ]
    md = render_traice_checklist(metas, {})
    assert "- Llamadas a IA registradas: 2 con respuesta válida; 2 intentos fallidos" in md
    assert "- Modelos usados: claude_code:opus, gemini:g" in md
    assert "solo-fallo" not in md  # M11: versiones y parámetros, solo de las metas ok
    assert "(screening/v1.md)" in md
    assert (
        "- claude_code:opus: versión del modelo no informada (origen: config); backend 2.9.0" in md
    )
    assert "- gemini:g: versión del modelo g-001 (origen: backend); backend 2.10.0" in md
    assert "- claude_code:opus: temperatura declarada 0,0; no aplicable en `claude_code`" in md
    assert "- gemini:g: temperatura declarada 0,0; aplicada" in md
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_declaracion_procedencia.py -v`
Expected: FAIL (`AssertionError`: las frases nuevas no están).

- [ ] **Step 3: Implementar** según Interfaces. Las líneas que se pegan en un manuscrito siguen la regla de `render_methods` (cada frase cierta; sin imperativos).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_declaracion_procedencia.py tests/test_entregable_honesto.py tests/test_coverage_gaps.py tests/test_pipeline_fake.py -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/exports/methods.py revisia/exports/checklist.py tests/test_declaracion_procedencia.py
git commit -m "feat(exports): metodologia y checklist trAIce declaran parámetros aplicados, versiones e intentos (M2, M6; A6, A15)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 8: Puerta de la sonda del CLI y valores que fija (controlador)

Las Tareas 1–7 no necesitan la sonda; las 9–11 sí. Esta tarea va justo antes de ellas.

**Files:** ninguno de código. Lee `docs/superpowers/sondas/<YYYY-MM-DD>-claude-cli.md` (lo escribe el arquitecto con `scripts/sonda_claude_cli.py` de PR-0, Tarea 16, D11, §14.2 paso 0). La sonda hace dos llamadas `-p --json-schema`: la segunda añade `--max-turns 1` si el `--help` lo anuncia; de las dos registra `subtype` y `total_cost_usd`.

**Interfaces:**
- Produces (los copian las Tareas 9–11, nunca se inventan):
  - `«SONDA:MIN_CLI_VERSION»`: la línea `MIN_CLI_VERSION candidata: X.Y.Z` de `## Para PR-A`.
  - `«SONDA:CLAVE_JSON_SCHEMA»`: la línea `- clave: \`K\`` de `## Dónde viene el objeto validado`, con `- válido: sí`.
  - `«SONDA:SUBTYPE_OK»`: la línea `- subtype: \`S\`` de `## Dónde viene el objeto validado` (primera llamada, con éxito).
  - `«SONDA:MAX_TURNS_CON_JSON_SCHEMA»`: `True` si `## Para PR-A` dice `MAX_TURNS con --json-schema: compatible`; `False` si dice `incompatible` o `no anunciado`.
  - `«SONDA:SUBTYPES_DE_LIMITE»`: el conjunto de `subtype` de error que la sonda haya visto (el de la segunda llamada si fue `incompatible`), como literal de `frozenset` de cadenas; `frozenset()` si no vio ninguno. El de «presupuesto agotado» no se puede observar con suscripción: lo cubre la regla de prefijo de la Tarea 11 (supuesto §19).

- [ ] **Step 1: Comprobar que la sonda existe y sirve.**

```bash
ls docs/superpowers/sondas/*-claude-cli.md
grep -n "MIN_CLI_VERSION candidata\|esta versión no sirve\|^- clave:\|^- válido:\|^- subtype:\|MAX_TURNS con --json-schema" docs/superpowers/sondas/*-claude-cli.md
```

Expected: un informe con `MIN_CLI_VERSION candidata: X.Y.Z`, `- clave: \`…\`` distinta de `ninguna`, `- válido: sí`, `- subtype: \`…\`` en las dos llamadas y la línea `MAX_TURNS con --json-schema: …`.
**Si falta el fichero o alguna de esas líneas, dice «esta versión no sirve», la clave es `ninguna` o `válido: no`: detente aquí y avisa al arquitecto** con este texto: «PR-A necesita la sonda del CLI (D11): actualiza el CLI (`npm i -g @anthropic-ai/claude-code@latest`) y ejecuta `python scripts/sonda_claude_cli.py` desde un terminal con sesión válida; commitea el informe en `docs/superpowers/sondas/`». No se sigue con valores supuestos. Lo hecho en las Tareas 1–7 queda commiteado.

- [ ] **Step 2: Anotar los cinco valores** en el cuerpo de la PR (Tarea 13) y en el mensaje a los implementadores de las Tareas 9–11. `MIN_CLI_VERSION` es la versión **probada** (cota conservadora: la menor que anuncia los tres flags puede ser anterior, pero no se ha visto).

---

## Tarea 9: Sonda del CLI en el proveedor y en el preflight (`probe_cli`, `CliCapabilities`, `MIN_CLI_VERSION`)

**Files:**
- Modify: `revisia/llm/providers/claude_code.py` (constantes y funciones de módulo nuevas tras la línea 61; `ClaudeCodeProvider._capabilities`).
- Modify: `revisia/llm/preflight.py:211-282` (`check_provider`) y `:479-522` (`preflight`): parámetro `probe`.
- Modify: `tests/conftest.py:53-70` (marca `cli_claude_real` y fixture autouse), `tests/fakes.py` (`capacidades_cli`).
- Test: `tests/test_claude_code_provider.py` y `tests/test_preflight.py` (añadir).

**Interfaces:**
- Consumes: valores de la Tarea 8; `PreflightError`, `PreflightReport`, `PreflightIssue` (`preflight.py:92-125`).
- Produces (§5.3, D11):
  - Constantes de la sonda, todas en esta tarea y con la ruta y la fecha del informe en un comentario (Tarea 8): `MIN_CLI_VERSION: str = "«SONDA:MIN_CLI_VERSION»"`; `JSON_SCHEMA_RESULT_KEY: str = "«SONDA:CLAVE_JSON_SCHEMA»"`; `SUBTYPE_OK: str = "«SONDA:SUBTYPE_OK»"`; `LIMIT_SUBTYPES: frozenset[str] = «SONDA:SUBTYPES_DE_LIMITE»`; `USE_MAX_TURNS: bool = «SONDA:MAX_TURNS_CON_JSON_SCHEMA»`. Las usan las Tareas 10 y 11.
  - `PROBED_FLAGS: tuple[str, ...] = ("--safe-mode", "--tools", "--json-schema", "--max-turns", "--max-budget-usd", "--strict-mcp-config", "--no-session-persistence", "--effort", "--append-system-prompt")`; `REQUIRED_FLAGS: tuple[str, ...] = ("--safe-mode", "--tools")`.
  - `@dataclass(frozen=True, slots=True) class CliCapabilities`: `version: str | None`, `flags: frozenset[str]`; `has(flag: str) -> bool`.
  - `class CliProbeError(RuntimeError)`.
  - `parse_cli_version(text: str) -> tuple[int, int, int] | None` (primer `\d+\.\d+\.\d+`).
  - `probe_cli(cli: str, *, timeout: float = 20.0) -> CliCapabilities`: `[cli, "--version"]` y `[cli, "--help"]` con `subprocess.run(capture_output=True, text=True, encoding="utf-8", timeout=timeout, env=subprocess_env(clean_env=False))` (la función de la Tarea 10; hasta entonces, `dict(os.environ)`); un flag está anunciado si aparece como palabra completa (`(?<![\w-])<flag>(?![\w-])`). Caché por proceso en `_PROBE_CACHE: dict[str, CliCapabilities]` con la ruta como clave; un fallo (`FileNotFoundError`, `TimeoutExpired`, código ≠ 0) → `CliProbeError` con el motivo y **no se cachea**. `clear_probe_cache() -> None`.
  - `capability_problems(caps: CliCapabilities) -> list[str]`: versión ilegible o `< MIN_CLI_VERSION` → `f"CLI de Claude Code {caps.version or 'sin versión legible'} por debajo de {MIN_CLI_VERSION}: actualiza el CLI (npm i -g @anthropic-ai/claude-code@latest)"`; por cada flag de `REQUIRED_FLAGS` ausente → `f"el CLI no anuncia {flag} en --help: sin él la llamada no queda aislada; actualiza el CLI (npm i -g @anthropic-ai/claude-code@latest)"`.
  - `ClaudeCodeProvider._capabilities() -> CliCapabilities`: `probe_cli(self._resolve_cli())` (se busca como atributo del módulo en cada llamada, para que los tests lo sustituyan); un `CliProbeError` se convierte en `PreflightError` con el issue `f"no se pudo consultar {cli} --version/--help: {exc}"` (rc 2, como en el preflight; M4); con `capability_problems` no vacío lanza `PreflightError(PreflightReport(tuple(PreflightIssue("error", "claude_code", m) for m in problemas)))` **antes** de lanzar `claude -p` (defensa en profundidad: rc 2 en el pipeline, que ya trata `PreflightError` como error de configuración, `pipeline.py:137-145`).
  - `preflight(..., probe: Probe | None = None)` y `check_provider(..., probe: Probe | None = None)`, con `Probe = Callable[[str], CliCapabilities]` y default `_default_probe(cli)` que importa `revisia.llm.providers.claude_code` dentro de la función y llama a `claude_code.probe_cli(cli)`. Para `claude_code` con el binario encontrado (`which` devuelve ruta): `CliProbeError` → error `f"no se pudo consultar {ruta} --version/--help: {exc}"`; cada `capability_problems` → error.
  - `tests/fakes.py`: `capacidades_cli(*, sin: Iterable[str] = (), version: str | None = None) -> CliCapabilities` (todas las de `PROBED_FLAGS` menos `sin`; versión `MIN_CLI_VERSION` por defecto).
  - `tests/conftest.py`: `CLI_CLAUDE_REAL = "cli_claude_real"` registrada en `pytest_configure` (como `DOTENV_REAL`); fixture autouse `_cli_claude_simulado` que, salvo en tests con esa marca, sustituye `claude_code.probe_cli` por `lambda cli, *, timeout=20.0: capacidades_cli()`. Así ningún test existente lanza `claude --help`.

- [ ] **Step 1: Tests que fallan** — añadir al final de `tests/test_claude_code_provider.py`:

```python
# ── Ola 2: sonda del CLI por capacidad (spec 2026-10-18 §5.3; D11) ────────────

from fakes import capacidades_cli  # noqa: E402

from revisia.llm.preflight import PreflightError  # noqa: E402

HELP_COMPLETO = (
    "Usage: claude\n  --safe-mode\n  --tools <t>\n  --json-schema <s>\n"
    "  --max-turns <n>\n  --max-budget-usd <x>\n"
)


def _sonda(respuestas: dict, llamadas: list):
    def _run(cmd, **kw):
        llamadas.append((cmd[1], kw.get("timeout")))
        salida = respuestas[cmd[1]]
        if isinstance(salida, BaseException):
            raise salida
        return SimpleNamespace(returncode=0, stdout=salida, stderr="")

    return _run


def test_constantes_de_la_sonda_no_son_marcadores() -> None:
    assert cc.parse_cli_version(cc.MIN_CLI_VERSION) is not None
    constantes = (cc.MIN_CLI_VERSION, cc.JSON_SCHEMA_RESULT_KEY, cc.SUBTYPE_OK, *cc.LIMIT_SUBTYPES)
    for valor in constantes:
        assert valor and "«" not in valor and "SONDA" not in valor
    assert isinstance(cc.USE_MAX_TURNS, bool) and isinstance(cc.LIMIT_SUBTYPES, frozenset)


def test_proveedor_con_sonda_fallida_da_preflight_error(monkeypatch) -> None:
    def _rota(cli, *, timeout=20.0):
        raise cc.CliProbeError("salió con código 1")

    recorder: list[dict] = []
    monkeypatch.setattr(cc, "probe_cli", _rota)
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")], recorder))
    with pytest.raises(PreflightError, match="no se pudo consultar"):
        _provider().complete(LLMRequest(prompt="x"))
    assert recorder == []


@pytest.mark.cli_claude_real
def test_probe_cli_lee_version_y_flags_y_se_cachea(monkeypatch) -> None:
    cc.clear_probe_cache()
    llamadas: list = []
    respuestas = {"--version": "99.0.0 (Claude Code)", "--help": HELP_COMPLETO}
    monkeypatch.setattr(cc.subprocess, "run", _sonda(respuestas, llamadas))
    caps = cc.probe_cli("C:/bin/claude.exe")
    assert caps.version == "99.0.0" and caps.has("--safe-mode") and not caps.has("--bare")
    assert cc.probe_cli("C:/bin/claude.exe") is caps
    assert llamadas == [("--version", 20.0), ("--help", 20.0)]
    assert cc.capability_problems(caps) == []
    cc.clear_probe_cache()


@pytest.mark.cli_claude_real
@pytest.mark.parametrize(
    "fallo", [FileNotFoundError(), cc.subprocess.TimeoutExpired(cmd="claude", timeout=20)]
)
def test_probe_cli_que_no_arranca_es_cli_probe_error(monkeypatch, fallo) -> None:
    cc.clear_probe_cache()
    llamadas: list = []
    monkeypatch.setattr(
        cc.subprocess, "run", _sonda({"--version": fallo, "--help": fallo}, llamadas)
    )
    for _ in range(2):  # un fallo no se cachea: se vuelve a intentar
        with pytest.raises(cc.CliProbeError):
            cc.probe_cli("claude")
    assert len(llamadas) == 2


def test_capability_problems_version_y_flags_obligatorios() -> None:
    assert cc.capability_problems(capacidades_cli()) == []
    viejo = cc.capability_problems(capacidades_cli(version="0.0.1"))
    assert len(viejo) == 1 and "npm i -g @anthropic-ai/claude-code@latest" in viejo[0]
    assert "npm i -g" in cc.capability_problems(capacidades_cli(version=None))[0]
    sin = cc.capability_problems(capacidades_cli(sin=["--safe-mode", "--tools"]))
    assert len(sin) == 2 and "--safe-mode" in sin[0] and "--tools" in sin[1]


def test_proveedor_sin_safe_mode_no_lanza_el_cli(monkeypatch) -> None:
    recorder: list[dict] = []
    monkeypatch.setattr(
        cc, "probe_cli", lambda cli, *, timeout=20.0: capacidades_cli(sin=["--safe-mode"])
    )
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")], recorder))
    with pytest.raises(PreflightError, match="--safe-mode"):
        _provider().complete(LLMRequest(prompt="x"))
    assert recorder == []
```

Y al final de `tests/test_preflight.py`:

```python
# ── Ola 2: versión mínima y flags del CLI (spec 2026-10-18 §5.3; D11) ────────

from fakes import capacidades_cli  # noqa: E402

from revisia.llm.providers.claude_code import CliProbeError  # noqa: E402


def _claude_code() -> ReviewProtocol:
    return _proto(llm={"default": {"provider": "claude_code", "model": "sonnet"}})


def test_probe_cli_sin_safe_mode_es_error_de_preflight(proto_dir: Path) -> None:
    report = _run(_claude_code(), proto_dir, probe=lambda cli: capacidades_cli(sin=["--safe-mode"]))
    assert "--safe-mode" in _messages(report.errors)
    assert _run(_claude_code(), proto_dir, probe=lambda cli: capacidades_cli()).ok


def test_preflight_cli_antiguo_es_error_con_la_orden_de_actualizar(proto_dir: Path) -> None:
    report = _run(_claude_code(), proto_dir, probe=lambda cli: capacidades_cli(version="0.0.1"))
    assert "npm i -g @anthropic-ai/claude-code@latest" in _messages(report.errors)


def test_preflight_sonda_fallida_es_error(proto_dir: Path) -> None:
    def _rota(cli: str):
        raise CliProbeError("salió con código 1")

    report = _run(_claude_code(), proto_dir, probe=_rota)
    assert "no se pudo consultar /usr/local/bin/claude --version/--help" in _messages(report.errors)


def test_preflight_sin_binario_no_sondea(proto_dir: Path) -> None:
    def _no_llamar(cli: str):
        raise AssertionError("sin binario no se sondea")

    assert not _run(_claude_code(), proto_dir, which=_sin_binario, probe=_no_llamar).ok
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_claude_code_provider.py tests/test_preflight.py -v`
Expected: FAIL con `ImportError: cannot import name 'capacidades_cli'`.

- [ ] **Step 3: Implementar** según Interfaces, sustituyendo los cinco marcadores por los valores de la Tarea 8. La fixture autouse va en `tests/conftest.py` junto a `_sin_dotenv_real`, con docstring (ningún test lanza `claude --help` real; los que prueban la sonda llevan `@pytest.mark.cli_claude_real` y sustituyen `subprocess.run`).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_claude_code_provider.py tests/test_preflight.py tests/test_cli_validate.py tests/test_llm_registry.py tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/llm/providers/claude_code.py revisia/llm/preflight.py tests/conftest.py tests/fakes.py tests/test_claude_code_provider.py tests/test_preflight.py
git commit -m "feat(claude_code): probe_cli cacheado, MIN_CLI_VERSION de la sonda y error de preflight sin --safe-mode/--tools (D11)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 10: Comando de `claude -p` por capacidad y entorno por allowlist (A10, M17)

**Files:**
- Modify: `revisia/llm/providers/claude_code.py:69-146` (`__init__`, `_subprocess_env` → `subprocess_env`, `_command`).
- Modify: `revisia/llm/registry.py:48,51-68,76-107` (`_BUDGET_PROVIDERS`, `ProviderConfig.max_budget_usd`, `build_provider`).
- Modify: `revisia/llm/preflight.py:211-282` (`max_budget_usd` fuera de `claude_code`; avisos del shim y del presupuesto).
- Modify: `.env.example:18-27` (documentar `REVISIA_CLAUDE_CODE_ENV_EXTRA`); `protocols/_TEMPLATE/protocol.yml` (comentario de `max_budget_usd` junto a `effort`).
- Test: `tests/test_claude_code_provider.py`, `tests/test_preflight.py`, `tests/test_llm_registry.py` (añadir).

**Interfaces:**
- Consumes: `CliCapabilities`, `_capabilities()`, `USE_MAX_TURNS`, `JSON_SCHEMA_RESULT_KEY` (T9).
- Produces (§5.3, A10, M17, D11):
  - `ENV_ALLOWLIST: frozenset[str]` = exactamente `{"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CONFIG_DIR"}`; `ENV_EXTRA_VAR = "REVISIA_CLAUDE_CODE_ENV_EXTRA"`.
  - `subprocess_env(*, clean_env: bool, environ: Mapping[str, str] | None = None) -> dict[str, str]` (función de módulo; `environ` por defecto `os.environ`): copia solo las variables cuyo nombre, **en mayúsculas**, está en `{n.upper() for n in ENV_ALLOWLIST}` o en los nombres de `ENV_EXTRA_VAR` (separados por comas, con espacios recortados), conservando el nombre original; añade `_ENDPOINT_OVERRIDE_VARS` (`claude_code.py:51`) salvo que `clean_env` y haya `CLAUDE_CODE_OAUTH_TOKEN` (la regla de hoy, `claude_code.py:101-105`). `ClaudeCodeProvider._subprocess_env()` delega en ella.
  - `ClaudeCodeProvider.__init__(..., max_budget_usd: float | None = None)`; `DEFAULT_MAX_BUDGET_USD: float = 1.0`; `MAX_TURNS: int = 1`.
  - `_uses_json_schema(caps: CliCapabilities) -> bool`: `caps.has("--json-schema")` **y** el CLI resuelto no es un shim `.cmd`/`.bat` (Review Focus 1: el schema lleva `"`, que la guardia BatBadBut rechaza; con shim viaja en el texto, como hoy).
  - `_command(req: LLMRequest, *, schema_json: str | None = None) -> list[str]`: lo de hoy (`claude_code.py:119-146`, con `--safe-mode` y `--tools ""` siempre) más, en este orden tras `--safe-mode`: `["--max-turns", "1"]` si `caps.has("--max-turns")` y `USE_MAX_TURNS`; `["--json-schema", schema_json]` si `schema_json is not None`; `["--max-budget-usd", f"{budget:.2f}"]` si `caps.has("--max-budget-usd")` y `ANTHROPIC_API_KEY` no vacía en `subprocess_env(...)`, con `budget = self.max_budget_usd if not None else DEFAULT_MAX_BUDGET_USD` (supuesto §19). Después `--effort` y `--append-system-prompt` como hoy, y la guardia del shim.
  - `registry.py`: `_BUDGET_PROVIDERS = frozenset({"claude_code"})`; `ProviderConfig.max_budget_usd: float | None = Field(default=None, ge=0.01)` (un céntimo como mínimo: `--max-budget-usd` se formatea con dos decimales, M2); `build_provider` lo pasa como `max_budget_usd=` solo si no es `None` y rechaza (`ValueError`, como `effort`) un proveedor fuera de `_BUDGET_PROVIDERS`.
  - `preflight.check_provider`: `max_budget_usd` fuera de `claude_code` → error (texto paralelo al de `effort`); `claude_code` con binario `.cmd`/`.bat` → aviso `"el CLI es un shim .cmd/.bat: --json-schema no se usa (BatBadBut) y el schema viaja en el texto del prompt; instala el binario nativo (claude.exe) para validación por el CLI"`; `ANTHROPIC_API_KEY` en `env` y `--max-budget-usd` no anunciado → aviso `"con ANTHROPIC_API_KEY el coste por llamada no queda acotado: el CLI no anuncia --max-budget-usd (M17)"`; `ANTHROPIC_API_KEY` en `env` y el flag anunciado → aviso `f"con ANTHROPIC_API_KEY el CLI factura por API: tope de {budget:.2f} USD por llamada (llm.<etapa>.max_budget_usd; M17)"`, con el `budget` de esa etapa (M2: quien corre con API key sabe que paga y cuánto como máximo por llamada).

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_claude_code_provider.py`:

```python
# ── Ola 2: comando por capacidad y entorno por allowlist (spec 2026-10-18 §5.3; A10, M17) ──

import subprocess as subprocess_real  # noqa: E402
import sys  # noqa: E402


def _respuesta_schema(obj: dict, *, como_texto: bool) -> str:
    valor = json.dumps(obj) if como_texto else obj
    datos = {
        "type": "result",
        "is_error": False,
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "result": "",
    }
    datos[cc.JSON_SCHEMA_RESULT_KEY] = valor
    return json.dumps(datos)


def test_env_allowlist_fija_la_lista() -> None:
    assert cc.ENV_ALLOWLIST == frozenset(
        {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "SYSTEMDRIVE",
            "COMSPEC",
            "WINDIR",
            "TEMP",
            "TMP",
            "HOME",
            "USERPROFILE",
            "HOMEDRIVE",
            "HOMEPATH",
            "APPDATA",
            "LOCALAPPDATA",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "TZ",
            "TERM",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
            "REQUESTS_CA_BUNDLE",
            "NODE_EXTRA_CA_CERTS",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "no_proxy",
            "CLAUDE_CODE_OAUTH_TOKEN",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "CLAUDE_CONFIG_DIR",
        }
    )


def test_subprocess_env_es_allowlist_y_no_filtra_variables_ajenas(monkeypatch) -> None:
    monkeypatch.setenv("REVISIA_TEST_LEAK", "fuga")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    monkeypatch.setenv("CORP_CA", "x")
    monkeypatch.setenv(cc.ENV_EXTRA_VAR, " CORP_CA , OTRA_INEXISTENTE")
    env = cc.subprocess_env(clean_env=False)
    assert (
        "REVISIA_TEST_LEAK" not in env
        and env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok"
        and env["CORP_CA"] == "x"
    )
    hijo = subprocess_real.run(
        [sys.executable, "-c", "import os; print(os.environ.get('REVISIA_TEST_LEAK'))"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert hijo.returncode == 0 and hijo.stdout.strip() == "None"


def test_allowlist_casa_sin_distinguir_mayusculas() -> None:
    env = cc.subprocess_env(
        clean_env=False,
        environ={"Path": "p", "SystemRoot": "C:\\Windows", "https_proxy": "h", "OTRA": "y"},
    )
    assert env == {"Path": "p", "SystemRoot": "C:\\Windows", "https_proxy": "h"}


def test_json_schema_solo_si_el_cli_lo_anuncia(monkeypatch) -> None:
    obj = {"include": True, "reason": "ok"}
    recorder: list[dict] = []
    monkeypatch.setattr(cc.shutil, "which", lambda _n: r"C:\bin\claude.exe")
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory([_respuesta_schema(obj, como_texto=False)], recorder),
    )
    out, meta = _provider().structured(LLMRequest(prompt="¿incluir?"), _Decision)
    cmd = recorder[0]["cmd"]
    assert (
        out.include is True and recorder[0]["input"] == "¿incluir?"
    )  # el schema no va en el texto
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == _Decision.model_json_schema()
    recorder.clear()
    monkeypatch.setattr(
        cc, "probe_cli", lambda cli, *, timeout=20.0: capacidades_cli(sin=["--json-schema"])
    )
    monkeypatch.setattr(
        cc.subprocess, "run", _fake_run_factory([_result_json(json.dumps(obj))], recorder)
    )
    _provider().structured(LLMRequest(prompt="¿incluir?"), _Decision)
    assert "--json-schema" not in recorder[0]["cmd"] and "JSON Schema" in recorder[0]["input"]


@pytest.mark.parametrize("como_texto", [False, True])
def test_objeto_validado_se_lee_de_la_clave_de_la_sonda(monkeypatch, como_texto: bool) -> None:
    monkeypatch.setattr(cc.shutil, "which", lambda _n: r"C:\bin\claude.exe")
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory(
            [_respuesta_schema({"include": False, "reason": "r"}, como_texto=como_texto)]
        ),
    )
    assert _provider().structured(LLMRequest(prompt="x"), _Decision)[0].include is False


def test_json_schema_con_shim_cmd_viaja_en_el_texto(monkeypatch) -> None:
    recorder: list[dict] = []
    monkeypatch.setattr(cc.shutil, "which", lambda _n: r"C:\npm\claude.CMD")
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory([_result_json(json.dumps({"include": True, "reason": "r"}))], recorder),
    )
    _provider().structured(LLMRequest(prompt="x"), _Decision)
    assert "--json-schema" not in recorder[0]["cmd"] and "JSON Schema" in recorder[0]["input"]


@pytest.mark.parametrize("usar", [True, False])
def test_max_turns_1_si_se_anuncia_y_la_sonda_lo_valida(monkeypatch, usar: bool) -> None:
    recorder: list[dict] = []
    monkeypatch.setattr(cc, "USE_MAX_TURNS", usar)
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")], recorder))
    _provider().complete(LLMRequest(prompt="x"))
    cmd = recorder[0]["cmd"]
    assert ("--max-turns" in cmd) is usar and (not usar or cmd[cmd.index("--max-turns") + 1] == "1")


def test_max_budget_solo_con_api_key(monkeypatch) -> None:
    def _cmd(provider, *, caps=None) -> list[str]:
        recorder: list[dict] = []
        if caps is not None:
            monkeypatch.setattr(cc, "probe_cli", lambda cli, *, timeout=20.0: caps)
        monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")], recorder))
        provider.complete(LLMRequest(prompt="x"))
        return recorder[0]["cmd"]

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "--max-budget-usd" not in _cmd(_provider())  # suscripción: no aplica
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ficticia")
    cmd = _cmd(_provider())
    assert cmd[cmd.index("--max-budget-usd") + 1] == "1.00"  # default M17
    cmd = _cmd(cc.ClaudeCodeProvider("sonnet", max_budget_usd=0.25))
    assert cmd[cmd.index("--max-budget-usd") + 1] == "0.25"
    assert "--max-budget-usd" not in _cmd(
        _provider(), caps=capacidades_cli(sin=["--max-budget-usd"])
    )
```

En `tests/test_llm_registry.py`:

```python
def test_max_budget_usd_solo_en_claude_code() -> None:
    from revisia.llm.providers.claude_code import ClaudeCodeProvider

    proveedor = build_provider(
        ProviderConfig(provider="claude_code", model="sonnet", max_budget_usd=0.5)
    )
    assert isinstance(proveedor, ClaudeCodeProvider) and proveedor.max_budget_usd == 0.5
    with pytest.raises(ValueError, match="max_budget_usd"):
        build_provider(ProviderConfig(provider="fake", model="f", max_budget_usd=0.5))
    with pytest.raises(ValidationError):
        ProviderConfig(provider="claude_code", model="sonnet", max_budget_usd=0.001)
```

En `tests/test_preflight.py`:

```python
def test_preflight_max_budget_fuera_de_claude_code_es_error(proto_dir: Path) -> None:
    report = _run(
        _proto(llm={"default": {"provider": "fake", "model": "f", "max_budget_usd": 1.0}}),
        proto_dir,
    )
    assert "max_budget_usd" in _messages(report.errors)


def test_preflight_avisa_del_shim_cmd(proto_dir: Path) -> None:
    report = _run(
        _claude_code(),
        proto_dir,
        which=lambda _n: r"C:\npm\claude.cmd",
        probe=lambda cli: capacidades_cli(),
    )
    assert report.ok and "BatBadBut" in _messages(report.warnings)


def test_preflight_avisa_si_hay_api_key_y_no_hay_tope_de_coste(proto_dir: Path) -> None:
    sin_tope = _run(
        _claude_code(),
        proto_dir,
        env={"ANTHROPIC_API_KEY": "k"},
        probe=lambda cli: capacidades_cli(sin=["--max-budget-usd"]),
    )
    assert "no queda acotado" in _messages(sin_tope.warnings)
    con_tope = _run(
        _claude_code(),
        proto_dir,
        env={"ANTHROPIC_API_KEY": "k"},
        probe=lambda cli: capacidades_cli(),
    )
    assert "tope de 1.00 USD por llamada" in _messages(con_tope.warnings)
    assert "factura por API" not in _messages(_run(_claude_code(), proto_dir).warnings)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_claude_code_provider.py tests/test_llm_registry.py tests/test_preflight.py -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'ENV_ALLOWLIST'`).

- [ ] **Step 3: Implementar** según Interfaces (las constantes de la sonda ya están, Tarea 9). En esta tarea `structured` solo cambia lo necesario para leer `JSON_SCHEMA_RESULT_KEY` (valor `str` → `json.loads` tras `_extract_json`; `dict` → tal cual) cuando `_uses_json_schema`; los intentos y metas son de la Tarea 11. Docstrings: por qué allowlist (A10: `os.environ` entero filtraba cualquier secreto al CLI) y por qué no `--bare`. `.env.example`: una línea comentada `# REVISIA_CLAUDE_CODE_ENV_EXTRA=  # nombres extra (coma) que pasan al CLI: CA o proxy corporativos`.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_claude_code_provider.py tests/test_llm_registry.py tests/test_preflight.py tests/test_config.py -v`
Expected: PASS (los tests de hoy de entorno, `test_token_de_suscripcion_se_propaga_al_subproceso`, `test_clean_env_quita_overrides_de_endpoint_con_token` y `test_sin_clean_env_conserva_el_entorno`, siguen en verde sin cambios).

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/llm/providers/claude_code.py revisia/llm/registry.py revisia/llm/preflight.py .env.example protocols/_TEMPLATE/protocol.yml tests/test_claude_code_provider.py tests/test_llm_registry.py tests/test_preflight.py
git commit -m "feat(claude_code): --json-schema, --max-turns y --max-budget-usd por capacidad; entorno por allowlist (A10, M17, D11)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 11: Intentos de `claude -p` con meta propia y errores clasificados (A6, A7, D9, D14)

**Files:**
- Modify: `revisia/llm/providers/claude_code.py:194-333` (`_invoke`, `_meta`, `complete`, `structured`).
- Modify: `tests/test_claude_code_provider.py:101-133`: los tres tests de hoy de `structured` (`test_structured_valida_aunque_venga_con_fences`, `test_structured_reintenta_tras_json_invalido`, `test_structured_agota_reintentos_y_falla`) prueban el modo «schema en el texto»: cada uno empieza con `monkeypatch.setattr(cc, "probe_cli", lambda cli, *, timeout=20.0: capacidades_cli(sin=["--json-schema"]))`. El tercero espera `DeterministicCallError` (subclase de `RuntimeError`: `match="JSON"` sigue). Y `_result_json` (`tests/test_claude_code_provider.py:28-40`) pasa de `"subtype": "success"` a `"subtype": cc.SUBTYPE_OK` (el valor real lo fija la sonda).
- Test: `tests/test_claude_code_provider.py` (añadir).

**Interfaces:**
- Consumes: `emit_attempt`, `error_for` (T2); `_capabilities`, `JSON_SCHEMA_RESULT_KEY`, `SUBTYPE_OK`, `LIMIT_SUBTYPES` (T9); `_uses_json_schema`, `_command` (T10); `canonical_sha256`.
- Produces (§5.2, §5.3 «Reintentos», D9):
  - Cada subproceso lanzado es un intento con su meta (`emit_attempt("claude_code", self.model, req, ...)`): `sent_prompt` = el stdin enviado (modo texto: `req.prompt` + instrucción con el schema + sufijo de reintento; modo `--json-schema`: `req.prompt` + sufijo de reintento si lo hay); `schema_sha256 = canonical_sha256(schema.model_json_schema())` solo en modo `--json-schema`; `attempt` desde 1 dentro de la llamada; `backend_version = caps.version`; `effort = self.effort`; `cost_usd = data.get("total_cost_usd")`; `latency_ms` medido alrededor de `subprocess.run`; `model_source="config"` (el JSON de `claude -p` no trae el modelo, §5.2); tokens de `usage`.
  - Clasificación de cada intento (en este orden):
    - `FileNotFoundError` → `RuntimeError` de hoy, **sin** meta (no hubo intento).
    - `TimeoutExpired` → meta `transient_error`, `TransientCallError` con el texto de hoy («no respondió en …»).
    - stdout que no es JSON → meta `transient_error`, `TransientCallError` (fallo del CLI, no del registro).
    - **Primero por `subtype`** del JSON (I2): `subtype ∈ LIMIT_SUBTYPES` o que empiece por `"error_max_"` (presupuesto o turnos agotados; el prefijo cubre el `subtype` de presupuesto, que la sonda no puede observar con suscripción: supuesto §19) → meta `deterministic_error` y `DeterministicCallError(f"Claude Code se detuvo por un límite ({subtype}): presupuesto o turnos agotados. Sube llm.<etapa>.max_budget_usd en protocol.yml (o revisa --max-turns) para la próxima corrida.", attempts=k)`.
    - Después, con código ≠ 0 o `is_error`, por el código HTTP **anclado**: `re.search(r"API Error: (\d{3})", texto)` sobre `result`/stderr. `401` (o, sin código, «authenticat» en el texto) → meta `transient_error` y `TransientCallError` con el mensaje accionable de hoy (`setup-token`); `403`, `408`, `429` y `≥ 500` → `transient_error`; cualquier otro `4xx` (400, 404, 413, 422) → meta `deterministic_error`, `DeterministicCallError(f"Claude Code devolvió un error: {texto[:500]}", attempts=k)`; sin código reconocible (`overloaded` sin número, red, causa desconocida) → `transient_error`. Un `404` suelto en el texto sin `API Error:` delante no cuenta.
    - Sin `is_error`, código 0 y `subtype` distinto de `SUBTYPE_OK` (y no nulo) → meta `transient_error`, `TransientCallError` (estado del CLI que la sonda no vio: reanudar es seguro).
    - En `structured`, salida que no valida (o sin la clave `JSON_SCHEMA_RESULT_KEY` en modo `--json-schema`) → meta `invalid_output` y reintento con el sufijo de hoy (`claude_code.py:318-322`); agotados `max_retries + 1` intentos → `DeterministicCallError(f"Claude Code no produjo JSON válido para {schema.__name__} tras {n} intentos. Último error: …", attempts=n)`. Cada intento conserva `outcome="invalid_output"`; el agotamiento lo dice la excepción (supuesto §19).
    - Intento válido → meta `ok` (`response_text = obj.model_dump_json()` en `structured`, el texto en `complete`), que es la que se devuelve.

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_claude_code_provider.py`:

```python
# ── Ola 2: cada intento con su meta y D9 (spec 2026-10-18 §5.2-§5.3; A6, A7, D9, D14) ──

from revisia.llm.base import DeterministicCallError, TransientCallError  # noqa: E402
from revisia.llm.providers.anthropic_api import AnthropicProvider  # noqa: E402
from revisia.provenance.runmeta import canonical_sha256, sha256_text  # noqa: E402
from revisia.provenance.sink import collecting  # noqa: E402

REQ_CC = LLMRequest(
    prompt="¿incluir?",
    system="eres un cribador",
    temperature=0.3,
    seed=42,
    prompt_template="screening/v1.md",
)


def _modo_texto(monkeypatch) -> None:
    monkeypatch.setattr(
        cc, "probe_cli", lambda cli, *, timeout=20.0: capacidades_cli(sin=["--json-schema"])
    )


def test_claude_code_reintento_emite_tres_metas_con_outcome(monkeypatch) -> None:
    _modo_texto(monkeypatch)
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("basura")] * 3))
    with collecting() as metas, pytest.raises(DeterministicCallError) as exc:
        _provider().structured(REQ_CC, _Decision)
    assert exc.value.attempts == 3
    assert [(m.attempt, m.outcome) for m in metas] == [
        (1, "invalid_output"),
        (2, "invalid_output"),
        (3, "invalid_output"),
    ]


def test_prompt_sha256_es_del_texto_enviado_con_schema_y_sufijo(monkeypatch) -> None:
    # A7 (auditoría: `57b517…` registrado frente a `2f1666…` enviado): el hash es el del stdin real.
    _modo_texto(monkeypatch)
    recorder: list[dict] = []
    bueno = _result_json(json.dumps({"include": True, "reason": "ok"}))
    monkeypatch.setattr(
        cc.subprocess, "run", _fake_run_factory([_result_json("basura"), bueno], recorder)
    )
    with collecting() as metas:
        _, meta = _provider().structured(REQ_CC, _Decision)
    plantilla = sha256_text("eres un cribador\n¿incluir?")
    enviados = [r["input"] for r in recorder]
    assert "JSON Schema" in enviados[0] and "no validó" in enviados[1]
    assert [m.prompt_sha256 for m in metas] == [
        sha256_text(f"eres un cribador\n{t}") for t in enviados
    ]
    assert len({plantilla, *(m.prompt_sha256 for m in metas)}) == 3  # ninguno es el de la plantilla
    assert meta is metas[-1] and meta.schema_sha256 is None


def test_con_json_schema_el_schema_tiene_su_hash(monkeypatch) -> None:
    monkeypatch.setattr(cc.shutil, "which", lambda _n: r"C:\bin\claude.exe")
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory([_respuesta_schema({"include": True, "reason": "r"}, como_texto=False)]),
    )
    _, meta = _provider().structured(REQ_CC, _Decision)
    assert meta.schema_sha256 == canonical_sha256(_Decision.model_json_schema())
    assert meta.prompt_sha256 == sha256_text("eres un cribador\n¿incluir?")


def test_applied_none_en_claude_code_y_seed_none_en_anthropic(monkeypatch) -> None:
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([_result_json("ok")]))
    meta = _provider().complete(REQ_CC).meta
    assert (meta.seed_applied, meta.temperature_applied, meta.top_p_applied) == (None, None, None)
    assert (meta.seed, meta.temperature) == (42, 0.3)  # lo pedido sigue registrado
    anthropic = AnthropicProvider("claude-x")
    cliente = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kw: SimpleNamespace(
                content=[SimpleNamespace(type="text", text="t")], model="claude-x-1", usage=None
            )
        )
    )
    monkeypatch.setattr(anthropic, "_client", lambda: cliente)
    meta_a = anthropic.complete(REQ_CC).meta
    assert (meta_a.seed_applied, meta_a.temperature_applied) == (None, 0.3)


def test_meta_lleva_version_del_cli_coste_latencia_effort_y_plantilla(monkeypatch) -> None:
    salida = json.dumps(
        {"type": "result", "is_error": False, "result": "ok", "total_cost_usd": 0.0123, "usage": {}}
    )
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([salida]))
    meta = cc.ClaudeCodeProvider("sonnet", effort="low").complete(REQ_CC).meta
    assert (meta.backend_version, meta.cost_usd, meta.effort, meta.model_source) == (
        cc.MIN_CLI_VERSION,
        0.0123,
        "low",
        "config",
    )
    assert meta.latency_ms is not None and meta.prompt_template == "screening/v1.md"


@pytest.mark.parametrize(
    ("texto", "error", "outcome"),
    [
        ("API Error: 400 prompt is too long", DeterministicCallError, "deterministic_error"),
        ("API Error: 413 request too large", DeterministicCallError, "deterministic_error"),
        ("API Error: 403 permission_error", TransientCallError, "transient_error"),
        ("API Error: 429 rate_limit_error", TransientCallError, "transient_error"),
        ("API Error: 529 overloaded_error", TransientCallError, "transient_error"),
        ("el fichero 404.txt no cuenta", TransientCallError, "transient_error"),  # sin anclar
        ("algo raro sin código", TransientCallError, "transient_error"),
    ],
)
def test_error_4xx_es_determinista_y_429_transitorio(
    monkeypatch, texto: str, error: type, outcome: str
) -> None:
    monkeypatch.setattr(
        cc.subprocess, "run", _fake_run_factory([_result_json(texto, is_error=True)])
    )
    with collecting() as metas, pytest.raises(error):
        _provider().complete(REQ_CC)
    assert [m.outcome for m in metas] == [outcome]


def test_limite_de_presupuesto_o_turnos_es_determinista_y_dice_que_subir(monkeypatch) -> None:
    subtype = next(iter(sorted(cc.LIMIT_SUBTYPES)), "error_max_budget_usd")
    salida = json.dumps({"type": "result", "subtype": subtype, "is_error": True, "result": ""})
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([salida]))
    with collecting() as metas, pytest.raises(DeterministicCallError, match="max_budget_usd"):
        _provider().complete(REQ_CC)
    assert [m.outcome for m in metas] == ["deterministic_error"]


def test_401_es_transitorio_y_accionable(monkeypatch) -> None:
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory([_result_json("Failed to authenticate. API Error: 401", is_error=True)]),
    )
    with pytest.raises(TransientCallError, match="setup-token"):
        _provider().complete(REQ_CC)


def test_timeout_es_transitorio_y_cli_ausente_no_es_intento(monkeypatch) -> None:
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        _fake_run_factory([cc.subprocess.TimeoutExpired(cmd="claude", timeout=1)]),
    )
    with collecting() as metas, pytest.raises(TransientCallError, match="no respondió"):
        _provider().complete(REQ_CC)
    assert [m.outcome for m in metas] == ["transient_error"]
    monkeypatch.setattr(cc.subprocess, "run", _fake_run_factory([FileNotFoundError()]))
    with collecting() as metas, pytest.raises(RuntimeError, match="claude"):
        _provider().complete(REQ_CC)
    assert metas == []
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_claude_code_provider.py -v`
Expected: FAIL (sin metas en el sink; `seed_applied` y `attempts` ausentes).

- [ ] **Step 3: Implementar** según Interfaces. `_invoke` devuelve el JSON parseado y la latencia; la clasificación vive en una función privada de módulo con la tabla en su docstring (D9: primero `subtype`, después el código anclado; por qué 401, 403 y lo desconocido son transitorios: reanudar es seguro, mandar al humano por un error global no lo es; y por qué un límite agotado es determinista: repetir con el mismo tope da lo mismo). `_meta` de hoy (`claude_code.py:273-286`) desaparece en favor de `emit_attempt`.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_claude_code_provider.py tests/test_journal.py tests/test_llm_meta.py -v`
Expected: PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add revisia/llm/providers/claude_code.py tests/test_claude_code_provider.py
git commit -m "feat(claude_code): una meta por intento con texto enviado, coste, latencia y versión del CLI; errores transitorio/determinista (A6, A7, D9, D14)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 12: Rebase sobre PR-H y sus cuatro `xfail(strict=True)` en verde (controlador + implementador)

**Files:**
- Rebase: `feat/ola2-procedencia` sobre `feat/ola2-ci-tests`.
- Modify: `tests/fakes.py` y `tests/test_providers_procedencia.py` (M8): los dobles de cliente de PR-H (`_Gemini`, `_OpenAI`, `_Anthropic` de `tests/test_providers_api.py`) pasan a `tests/fakes.py` como `ClienteGeminiFalso`, `ClienteOpenAIFalso` y `ClienteAnthropicFalso`, con dos parámetros de palabra clave añadidos (`fallo: Exception | None = None`, que lanzan en vez de responder, y, en Gemini, `bloqueo: str | None = None`); `tests/test_providers_api.py` y `tests/test_providers_procedencia.py` los importan con `from fakes import …` y los dobles provisionales de la Tarea 4 se borran. Las aserciones de ambos ficheros no cambian.
- Modify: `tests/test_providers_api.py` (de PR-H, Tarea 7): quitar el marcador de `test_gemini_runmeta_v2_aplicado`, `test_local_openai_prompt_sha256_es_del_texto_enviado`, `test_anthropic_runmeta_v2_aplicado` y `test_anthropic_structured_hashea_el_schema_aparte` (el cuarto lo separó la revisión de PR-H: A7, schema aparte en Anthropic); en `test_local_openai_inyecta_el_schema_en_el_prompt` la última línea `assert meta.prompt_sha256 == V1  # la 0.8 hashea el prompt ORIGINAL…` pasa a `assert meta.prompt_sha256 != V1  # A7: hash del texto enviado (PR-A)`.

**Interfaces:** ninguna nueva. Consume el estado de PR-H (`tests/test_providers_api.py`, `tests/test_sdk_superficie.py`, `ci.yml` con `sdk-smoke`, `requires-python >= 3.11`).

- [ ] **Step 1: Rebase.**

```bash
git fetch origin
git rebase origin/feat/ola2-ci-tests
```

Expected: conflictos, si los hay, solo en `tests/fakes.py` (H añade `protocolo_offline`, `ClienteJSON`, `pdf_minimo`; A cambia `ScriptedProvider` y añade `capacidades_cli`) y en `tests/conftest.py`: se conservan ambos lados.

- [ ] **Step 2: Comprobar que los cuatro xfail ahora pasan (XPASS estricto = FAIL).**

Run: `uv run pytest -p no:cacheprovider tests/test_providers_api.py -v`
Expected: cuatro `FAILED … [XPASS(strict)]` y `test_local_openai_inyecta_el_schema_en_el_prompt` FAILED en la aserción de `V1`.

- [ ] **Step 3: Quitar los tres marcadores, cambiar la aserción y unificar los dobles** según Files.

- [ ] **Step 4: Run para verificar que pasa, también el humo de los SDK y en 3.11.**

```bash
uv run pytest -p no:cacheprovider tests/test_providers_api.py tests/test_providers_procedencia.py -v
REVISIA_SDK_SMOKE=1 uv run --extra dev --extra gemini --extra openai --extra anthropic pytest -p no:cacheprovider -q -rs tests/test_sdk_superficie.py
uv run --python 3.11 --extra dev --extra search --extra meta pytest -p no:cacheprovider -q -n auto -m "not cronometrado"
```

Expected: PASS sin XFAIL ni XPASS en esos dos ficheros; `sdk-smoke` 3 passed sin skips (la superficie real que imitan los dobles sigue existiendo: `_config`, `chat.completions.create`, `beta.chat.completions.parse`, `messages.create`); suite verde en 3.11.

- [ ] **Step 5: Lint**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: sin errores y todos los ficheros ya formateados.

- [ ] **Step 6: Commit**

```bash
git add tests/fakes.py tests/test_providers_api.py tests/test_providers_procedencia.py
git commit -m "test: RunMeta v2 aplicado en proveedores API sin xfail; dobles de cliente comunes en fakes (A6, A7)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 13: Integración de PR-A (controlador)

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`: `### Added` y `### Changed`).
- Modify: `README.md:394-402` (ejemplo de `run_review_with_agent`).
- Modify: `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` (§19).

**Interfaces:** ninguna de código. Deja PR-A abierta sobre `feat/ola2-ci-tests` con el CI verde.

- [ ] **Step 1: CHANGELOG.** En `### Added`:

```
- **Procedencia aplicada** (spec Ola 2 §5; auditoría 2026-09-03, A6, A7, A15, D14): cada intento de
  llamada a un LLM llega a `llm_calls.jsonl` en el acto con lo que viajó de verdad (`seed_applied`,
  `temperature_applied`, `top_p_applied`), el hash del texto enviado (con el schema y el sufijo de
  reintento), la plantilla con versión y hash (`PROMPT_VERSIONS`, `load_template`), el hash del schema
  cuando viaja aparte, la versión del SDK o del CLI, latencia y coste; `run.json` y `manifest.yml`
  llevan `environment` (motor, Python, plataforma, commit, paquetes, hashes de plantillas y de las
  especificaciones de RoB). `metodologia.md` y `checklist_traice.md` declaran qué parámetros se
  aplicaron («temperatura declarada 0,0; no aplicable en `claude_code`»).
- **`claude -p` acotado por capacidad** (A10, M17, D11): versión mínima `<MIN_CLI_VERSION>` y
  `--safe-mode`/`--tools` obligatorios (error de preflight), `--json-schema`, `--max-turns 1` y
  `--max-budget-usd` (con `ANTHROPIC_API_KEY`; `llm.<etapa>.max_budget_usd`, 1,00 por defecto) cuando
  el CLI los anuncia, y entorno por allowlist (`REVISIA_CLAUDE_CODE_ENV_EXTRA` para añadir nombres).
- **Fallo transitorio frente a determinista en los proveedores** (D9): 401/403/408/429/5xx/red/timeout
  se reanudan; los demás 4xx (400, 404, 413, 422), un bloqueo de contenido, un límite de presupuesto o
  de turnos de `claude -p` o la salida inválida tras los reintentos dejan una línea `failed` definitiva
  en el diario (hasta que el pipeline la lleve al gate, `revisia run` sale con rc 2 y dice que el
  registro necesita decisión humana). **`agent` informa el modelo** con `AgentReply` (A8).
```

En `### Changed`:

```
- `run_review_with_agent` ya no aprueba solo: `auto_approve=False` por defecto (A8).
- `RunInfo.prompt_sha256` se retira: su sitio es `run.json.environment.prompt_templates` (D12). Una
  corrida sin `environment` (motor < 0.9) no se reanuda: `revisia run --resume` sale con rc 2.
- Los proveedores emiten una meta por intento (sink de `revisia.provenance.sink`); un proveedor de
  terceros que no emita sigue funcionando y solo pierde las metas de los intentos fallidos.
```

- [ ] **Step 2: README** (`README.md:402`): tras `result = run_review_with_agent(...)` añadir dentro del bloque el comentario `# pausa en cada gate HITL; auto_approve=True solo para una demo (no publicable)` y debajo del bloque una frase: «Si el callback sabe qué modelo contestó, devuelve `AgentReply(payload, model=…)`: queda en la procedencia (`model_source: callback`).» El resto de la documentación de procedencia es de PR-I (§13).

- [ ] **Step 3: §19 del spec.** Añadir **a continuación de la última fila existente**, con numeración consecutiva (copiar y completar con lo que haya producido la revisión por tarea; sustituir los marcadores por los valores de la sonda):

```
| n | §5.1, D9, §15 | `journaled` (journal.py, de A) escribe la línea `failed` y lanza `RecordFailedError(stage, record_id, failure)`, **subclase de `JournalError`**: ya está en `_CONFIG_ERRORS` (`pipeline.py:137-145`) y el CLI sale con rc 2 (`cli.py:294-304`) y el mensaje «necesita decisión humana», en vez del bucle de rc 3 (M15), sin tocar `pipeline.py`. Una línea `failed` se relee sin llamar. PR-C la atrapa en cada etapa antes de `_CONFIG_ERRORS` y lleva el registro al gate | Plan PR-A (decisión del orquestador, B2) |
| n+1 | §5.1, D14 | Rol de cada intento en el ensemble: `role_of(k)` con `k` = metas `ok` emitidas antes en ese registro (los intentos fallidos de un miembro llevan su rol). Las metas devueltas y no emitidas (proveedores de terceros) se registran después con `role_of(i)` por su posición; las emitidas no se duplican (identidad). **Limitación:** con un proveedor que no emite en una posición anterior, el rol de las metas emitidas puede desplazarse (`k` no lo cuenta) | Plan PR-A (B1) |
| n+2 | §5.1, §15 | `make_provider_judge` no se toca (`rag/*` es de D): su `on_meta` sigue siendo un colector y el sink es la fuente de verdad; `journaled` deduplica por identidad | Plan PR-A |
| n+3 | §4.2 `model_source`, §5.4 | `RunMeta.model` sigue siendo el modelo pedido (v1); el id que da el backend o el callback va a `model_version`, y `model_source` dice **de dónde salió `model_version`** (`backend`, `callback`, o `config` cuando no hay ninguno). En `agent`, `AgentReply.model` → `model_version` | Plan PR-A (M1) |
| n+4 | §5.2 | `APPLIED_PARAMS["fake"] = ∅` (el doble no usa parámetros); `deterministic` sigue en `True` | Plan PR-A |
| n+5 | D9, §5.3 | 401/403 → transitorio: ya registrada como fila 14 de §19 (aprobada 2026-10-20); no se repite. Lo que la fila 14 no cubre: las excepciones no clasificables se propagan sin meta | Plan PR-A (I1) |
| n+6 | §5.3, D9 | Clasificación de `claude -p`: primero por `subtype` del JSON (límite de presupuesto o de turnos → determinista, con mensaje que dice cómo subir `llm.<etapa>.max_budget_usd`); después por el código HTTP anclado (`API Error: (\d{3})`), nunca por un `4\d\d` suelto; sin código reconocible, stdout no JSON o `subtype` desconocido → transitorio. `SUBTYPE_OK` = `<S>` y `LIMIT_SUBTYPES` = `<conjunto>` de la sonda; el prefijo `error_max_` cubre el `subtype` de presupuesto, que la sonda no puede observar con suscripción | Plan PR-A (I2) |
| n+7 | §5.3 | Cada intento conserva su `outcome` (`invalid_output` aunque sea el último); el agotamiento lo dicen `DeterministicCallError(attempts=n)` y la línea `failed`. **Nota para PR-G:** la última meta de un registro `failed` no tiene por qué ser `deterministic_error` | Plan PR-A (M5) |
| n+8 | §5.3, M17 | `ProviderConfig.max_budget_usd: float \| None` (`ge=0.01`, solo `claude_code`); `--max-budget-usd` va siempre que el CLI lo anuncie y haya `ANTHROPIC_API_KEY`, con el valor del protocolo o 1,00 por defecto (el spec decía «solo si el protocolo lo declara» y «default 1.0» a la vez); con API key el preflight avisa del tope por llamada | Plan PR-A (M2) |
| n+9 | §5.3, A1 | Con un shim `.cmd`/`.bat` no se pasa `--json-schema` (el schema lleva `"` y la guardia BatBadBut lo rechazaría en cada llamada): el schema viaja en el texto y el preflight lo avisa | Plan PR-A |
| n+10 | D11, §4.4 | `MIN_CLI_VERSION = <X.Y.Z>` (la versión probada por la sonda del <fecha>: cota conservadora), objeto validado en la clave `<K>`, `--max-turns 1` con `--json-schema`: <compatible \| incompatible → sin `--max-turns`>. La sonda de PR-0 (Tarea 16) hace una segunda llamada con `--max-turns 1` y registra `subtype` y `total_cost_usd` de ambas; la puerta de la sonda va antes de la Tarea 9, no al principio | Plan PR-A (I3) |
| n+11 | §15 | PR-A toca además `run_context.py` (`write_manifest`, docstring de `LegacyRunError`), `artifacts.py` (solo retira `RunInfo.prompt_sha256`), `llm/preflight.py`, `llm/registry.py`, `tests/conftest.py` (marcas `cli_claude_real` y `git_real`, sonda y `git_state` simulados autouse) y dos líneas de `agents/{screening,screening_ft,extraccion,rob,reporte}.py` (`load_template` y `prompt_template`); `extraccion.py` (C), `rob.py` (E₁) y `tests/test_snapshot.py:72-78` (E₁) tendrán un conflicto trivial al rebasar: se conserva la forma derivada de `PROMPT_VERSIONS` y `get_args(RoBTool)` | Plan PR-A (I6) |
| n+12 | §5.5 | Sin tocar `pipeline.py`, `metodologia.md` deriva lo aplicado del protocolo y de `APPLIED_PARAMS` (que los proveedores cumplen por test) y `checklist_traice.md` de las metas `ok` (M11); `models_used` del manifiesto cuenta solo llamadas `ok` (relación 20), el de `metodologia.md` (pipeline) sigue sobre todas hasta que C toque el pipeline | Plan PR-A |
| n+13 | §4.3 rel. 20, §11.2 | Desfase con el auditor de hoy: la relación «§9.3 · models_used == modelos de llm_calls» del check `arithmetic` (`checks_flow.py:1255-1296`) recalcula sobre todas las llamadas; un modelo con solo intentos fallidos da FAIL hasta PR-G₂. Fijado en `tests/test_snapshot.py::test_modelo_con_solo_intentos_fallidos_audita_sin_fail` (`xfail(strict=True)`), que PR-G₂ vuelve verde | Plan PR-A (I5) |
| n+14 | D12 | Reanudar una corrida sin `environment` lanza `PreOla2RunError` (subclase de `LegacyRunError`, cuya docstring cubre ya los dos casos) desde `ensure_snapshot`: rc 2 sin tocar `pipeline.py` ni el CLI | Plan PR-A (M3) |
| n+15 | §5.4 | El aviso de preflight de A8 sale cuando el ensemble de `screening_ta` tiene ≥ 2 miembros `agent` (el preflight no puede saber si el callback devolverá `AgentReply`) | Plan PR-A |
| n+16 | §5.2 | `load_prompt(agent, version="v1") -> str` no cambia (C, D y E la pueden seguir llamando); la terna de §5.2 la da `load_template(agent, version=None) -> PromptTemplate(text, template, sha256)`, que usan los agentes de A. Una sola regla de hash (`revisia.prompts.text_sha256`, que `snapshot._text_sha256` reutiliza) | Plan PR-A (I7, M10) |
| n+17 | §4.2 `Environment` | `git_state` se calcula una vez por proceso (`lru_cache`) si existe `<raíz>/.git` (fichero o carpeta: en un worktree es un fichero); `git status --porcelain --untracked-files=no` para `git_dirty`. En la suite, una fixture autouse lo fija a `("0"*40, False)` salvo en los tests `git_real` | Plan PR-A (I8) |
| n+18 | D14 | `tests/test_reanudacion.py:150,161`: el 429 simulado ya cuenta como una línea `transient_error` en `llm_calls.jsonl` (3 y 5 líneas en vez de 2 y 4) | Plan PR-A |
| n+19 | §5.3, D11 (propuesta) | La sonda debería comprobar también `CLAUDE_CODE_GIT_BASH_PATH` (el CLI nativo de Windows la usa para localizar Git Bash): si el arquitecto la tiene definida y la llamada real de la Tarea 13 falla sin ella, entra en `ENV_ALLOWLIST`; mientras, `REVISIA_CLAUDE_CODE_ENV_EXTRA` la cubre | Plan PR-A (I4; **para el arquitecto**) |
```

- [ ] **Step 4: Commit de documentación.**

```bash
git add CHANGELOG.md README.md docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md
git commit -m "docs: CHANGELOG, README del agent_driver y desviaciones (§19) de PR-A" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Verificación completa local, en las tres versiones.**

```bash
for PY in 3.11 3.12 3.13; do
  uv run --python "$PY" --extra dev --extra search --extra meta pytest -p no:cacheprovider -q -n auto -m "not cronometrado" || exit 1
  uv run --python "$PY" --extra dev --extra search --extra meta pytest -p no:cacheprovider -q -m cronometrado || exit 1
done
uv run --extra dev --extra search --extra meta pytest -p no:cacheprovider -q -n auto --cov --cov-report=term -m "not cronometrado"
uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check
! grep -rn "«SONDA" revisia tests
```

Expected: verde en las tres versiones; los únicos `XFAIL` son `test_modelo_con_solo_intentos_fallidos_audita_sin_fail` (PR-G₂) y, si la Tarea 3 los añadió, los del auditor anotados para G; cobertura ≥ 90 %; lint limpio; `! grep` sale con 0 (ningún marcador `«SONDA` en el código). Anotar el recuento final.

- [ ] **Step 6: Comprobación real de la allowlist (arquitecto, I4).** Los tests no lanzan el CLI; esta llamada sí. El controlador pide al arquitecto que la ejecute desde un terminal con sesión válida en el worktree `C:\revisia-wt\a`:

```bash
uv run python - <<'PY'
from pydantic import BaseModel

from revisia.llm.base import LLMRequest
from revisia.llm.providers import claude_code as cc
from revisia.provenance.sink import collecting


class Salida(BaseModel):
    respuesta: str
    numero: int


env = cc.subprocess_env(clean_env=False)
print("variables que pasan al CLI:", sorted(env))
proveedor = cc.ClaudeCodeProvider("sonnet")
req = LLMRequest(prompt="Responde exactamente con respuesta='hola' y numero=7.")
with collecting() as metas:
    obj, meta = proveedor.structured(req, Salida)
print(obj)
print([(m.attempt, m.outcome) for m in metas], meta.backend_version, meta.cost_usd)
print("json-schema:", meta.schema_sha256 is not None)
PY
```

Expected: `respuesta='hola' numero=7`; `[(1, 'ok')]`; `backend_version` = la versión del CLI instalado (≥ `MIN_CLI_VERSION`); `json-schema: True` con el binario nativo (`False` con el shim `.cmd`, que es lo previsto); en la lista de variables no aparece ninguna fuera de `ENV_ALLOWLIST`, de `REVISIA_CLAUDE_CODE_ENV_EXTRA` ni de las de endpoint. Si falla por el entorno (p. ej. el CLI nativo de Windows no encuentra Git Bash), se repite con `REVISIA_CLAUDE_CODE_ENV_EXTRA=CLAUDE_CODE_GIT_BASH_PATH` (o la variable que nombre el error), se anota en §19 (fila n+19) y la variable entra en `ENV_ALLOWLIST` en un commit de esta PR, con su test en `test_env_allowlist_fija_la_lista`.

- [ ] **Step 7: Publicar y abrir la PR** (base `feat/ola2-ci-tests`, §15).

```bash
git push -u origin feat/ola2-procedencia
gh pr create --base feat/ola2-ci-tests --head feat/ola2-procedencia --title "Ola 2 · PR-A: procedencia aplicada, claude -p acotado y agent con modelo" --body "$(cat <<'EOF'
## Qué cierra

A6, A7, A8, A10, A15, M17, D9 (proveedores), D11 y D14 de la auditoría 2026-09-03 (spec `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` §5). Cierra la limitación B10/45j de la Ola 1: si falla el segundo miembro del ensemble, la llamada pagada del primero queda registrada.

## Qué cambia

- `revisia/llm/meta.py`: `emit_attempt`, `APPLIED_PARAMS`, clasificación de errores (D9). Todos los proveedores emiten una meta por intento con lo aplicado, el hash del texto enviado, la plantilla, la versión del SDK/CLI, latencia y coste.
- `revisia/orchestration/journal.py`: registro en el acto por intento; línea `failed` definitiva y `RecordFailedError` (rc 2 con «necesita decisión humana») ante un fallo determinista (PR-C lo lleva al gate).
- `claude_code`: `probe_cli` cacheado, `MIN_CLI_VERSION = <X.Y.Z>` (sonda del <fecha>), `--json-schema` (objeto en `<K>`), `--max-turns 1`, `--max-budget-usd` con API key, entorno por allowlist; sin `--json-schema` con un shim `.cmd`.
- `agent`: `AgentReply(payload, model, usage)`; `agent_driver` con `auto_approve=False`.
- `run.json`/`manifest.yml`: `environment`; corridas 0.8 → rc 2 al reanudar (D12).
- `metodologia.md`/`checklist_traice.md`: parámetros aplicados, versiones e intentos.
- Los cuatro `xfail(strict=True)` de PR-H en `tests/test_providers_api.py`, en verde.

## Cambios incompatibles

`RunInfo.prompt_sha256` → `environment.prompt_templates`; corridas 0.8 no reanudables; `agent_driver` no aprueba solo; los proveedores emiten metas por intento (los de terceros siguen funcionando).

## Verificación

- Suite en 3.11, 3.12 y 3.13 (Windows local): <N> recogidos, en verde (1 `xfail` estricto para PR-G₂: relación 20 sobre llamadas ok); cobertura <X> %.
- Llamada real con `ClaudeCodeProvider` y el entorno de la allowlist (arquitecto): <resultado>.
- `sdk-smoke`: 3 passed. `ruff`, `black`, `uv lock --check`: limpios.

## Pila

`main` ← PR-0 ← PR-H ← **PR-A** ← PR-B ← … (spec §15). No borrar la rama al mergear mientras PR-B la use como base.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR; el CI arranca. Esperar `gh pr checks <n> --watch`: `lint`, las seis celdas de `test`, `build` y `sdk-smoke` en verde. Sustituir `<N>`, `<X>`, `<X.Y.Z>`, `<K>`, `<fecha>` y `<resultado>` con `gh pr edit <n> --body-file …`. Sin merge: lo decide el arquitecto.

---

## Self-review (hecha al escribir el plan)

- **Cobertura de §5:** 5.1 sink y registro por intento (T3; dobles que emiten, T2; `make_provider_judge` sin tocar, §19 n+2); 5.2 `*_applied` por proveedor (T2 tabla, T4 API, T11 `claude_code`, T5 `agent`), `prompt_sha256` del texto enviado (T4 `local_openai`, T11 `claude_code`), `schema_sha256` (T4, T11), `prompt_template`/`prompt_template_sha256` y `PROMPT_VERSIONS`/`load_template` (T1, T2), `model_source` (T2, T4, T11, T5), `backend_version`/`latency_ms`/`cost_usd` (T4, T11), `prompt_fingerprint` con RoB (T6); 5.3 `probe_cli`/`CliCapabilities`/`PreflightError` (T9), `--json-schema`/`--max-turns`/`--max-budget-usd` y `ENV_ALLOWLIST` (T10), reintentos con meta y D9 (T11), D9 en SDK (T4); 5.4 (T5); 5.5 `environment` en `run.json` y manifiesto y D12 (T6), `metodologia.md`/`checklist_traice.md` (T7). Tests nombrados en §5, todos presentes: `test_sink_registra_cada_intento_en_el_acto` y `test_fallo_del_segundo_miembro_deja_la_llamada_del_primero_registrada` (T3), `test_claude_code_reintento_emite_tres_metas_con_outcome`, `test_prompt_sha256_es_del_texto_enviado_con_schema_y_sufijo`, `test_applied_none_en_claude_code_y_seed_none_en_anthropic` (T11), `test_probe_cli_sin_safe_mode_es_error_de_preflight` (T9), `test_json_schema_solo_si_el_cli_lo_anuncia`, `test_subprocess_env_es_allowlist_y_no_filtra_variables_ajenas`, `test_max_budget_solo_con_api_key` (T10), `test_agent_reply_informa_el_modelo`, `test_agent_driver_no_auto_aprueba_por_defecto` (T5), `test_environment_en_run_json_y_manifest_coinciden`, `test_prompt_template_sha_coincide_con_environment` (T6), `test_error_4xx_es_determinista_y_429_transitorio` (T4 por proveedor API; T11 en `claude_code`). PR-H: los tres `xfail` y `sdk-smoke` (T12).
- **Firmas verificadas contra `c1af7c3` (2026-10-19):** `journaled`/`StageJournal`/`append_jsonl` (`journal.py:102-213`), `RunContext.record_meta`/`write_manifest` (`run_context.py:154-238`), `ensure_snapshot`/`prompt_fingerprint`/`_text_sha256` (`snapshot.py:57-177`), `RunInfo` (`artifacts.py:107-130`, `prompt_sha256` en 125; nadie más lo lee: `grep` en `revisia/`), `LLMCall.from_meta` (`artifacts.py:146-158`), `load_prompt` (`prompts/__init__.py:16-21`) y sus cinco llamadas, `ClaudeCodeProvider` (`claude_code.py:64-333`), proveedores API (`gemini.py:48-96`, `openai_api.py:30-95`, `local_openai.py:39-58`, `openai_compat.py:25-38`, `anthropic_api.py:43-108`), `AgentProvider`/`AgentCallback` (`agent.py:43,85-145`), `run_review_with_agent` (`agent_driver.py:30-80`), `ProviderConfig`/`build_provider`/`_EFFORT_PROVIDERS` (`registry.py:48-107`), `check_provider`/`preflight`/`stages_in_use` (`preflight.py:152-282,479-522`), `_CONFIG_ERRORS` con `LegacyRunError` y `PreflightError` (`pipeline.py:137-145`, con `JournalError` para `RecordFailedError`), CLI rc 2 para `LegacyRunError` y `JournalError` (`cli.py:294-304`), `render_methods` (`methods.py:67-252`), `render_traice_checklist` (`checklist.py:507-612`), `redact_secrets` (`agents/_http.py:107`), fixture autouse y `pytest_configure` (`tests/conftest.py:53-70`), tests de hoy de `claude_code` (`tests/test_claude_code_provider.py:73-354`), recuentos de `tests/test_reanudacion.py:150,161`. Las firmas de PR-0 y PR-H son las de sus bloques Interfaces.
- **Consistencia entre tareas:** `emit_attempt`/`APPLIED_PARAMS`/`error_for` (T2) los consumen T3, T4, T11, T5 y T7; `RecordFailedError` (T3) es el contrato con PR-C; `capacidades_cli` y la marca `cli_claude_real` (T9) los usan T10 y T11; `subprocess_env` (T10) lo usa `probe_cli` (T9, con `os.environ` hasta T10); las cinco constantes de la sonda (`MIN_CLI_VERSION`, `JSON_SCHEMA_RESULT_KEY`, `SUBTYPE_OK`, `LIMIT_SUBTYPES`, `USE_MAX_TURNS`) se definen en T9 con los valores de T8, y T10/T11 solo las consumen; `template_fingerprint`/`text_sha256` (T1) los consume `snapshot` (T1, T6).
- **Proporción:** los bloques de código son tests con los valores del spec y textos exactos de copia; ningún cuerpo de función salvo la regla de roles y de deduplicación de `journaled`, descrita en prosa.
- **Revisión independiente (2026-10-19) incorporada:** B1 (test de roles con el proveedor que emite delante y limitación en §19), B2 (`RecordFailedError(JournalError)`: rc 2 sin tocar el pipeline), I1 (401/403 transitorios; §19 fila 14, aprobada 2026-10-20), I2 (`claude -p` clasificado por `subtype` y código anclado; límites deterministas), I3 (puerta de la sonda antes de la Tarea 9; segunda llamada con `--max-turns 1` en la sonda de PR-0), I4 (llamada real del arquitecto en la Tarea 13), I5 (`xfail` estricto para PR-G₂), I6 (conjuntos derivados de `PROMPT_VERSIONS` y `get_args(RoBTool)`), I7 (`load_prompt` intacto; `load_template` nuevo), I8 (`git_state` fijado por fixture; `.git` puede ser fichero) y M1–M11 (líneas de `agent_driver.py` y `pipeline.py` corregidas, `ge=0.01`, lint por tarea, líneas ≤ 100, dobles comunes tras el rebase, `getattr` en Gemini, una sola regla de hash, checklist sobre metas `ok`).
- **Marcadores:** los cinco `«SONDA:…»` no son huecos del plan: son valores que el spec (D11) asigna a la sonda del arquitecto; la Tarea 8 detiene la ejecución si faltan y la Tarea 13 comprueba que no quede ninguno en el código.
