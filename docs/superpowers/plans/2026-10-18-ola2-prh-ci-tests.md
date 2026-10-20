# Ola 2 · PR-H `feat/ola2-ci-tests` (CI multiplataforma y tests que faltaban) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la suite corra en la matriz `ubuntu-latest`/`windows-latest` × Python 3.11/3.12/3.13 con `uv lock --check`, cobertura ≥ 90 % y humo de empaquetado, y que los huecos de la auditoría 2026-09-03 en tests (A13 entrypoints, M18 parsers Crossref/S2, M19 ruta de texto completo, M20 proveedores API) y el test de pico de memoria sensible a los extras (memoria de la Ola 1) queden cerrados antes de que las demás pistas se desarrollen sobre esta rama.

**Architecture:** `pyproject.toml` baja el suelo a 3.11 (ya probado en la Ola 1 con venv desechable), fija `target-version py311`, añade `pytest-cov` y la configuración de cobertura; `ci.yml` pasa de un job a cuatro (`lint`, `test` en matriz, `build` y `sdk-smoke`, §19 fila 6), con acciones fijadas por SHA y el extra `pdf` solo en Ubuntu. Los tests nuevos son offline: dobles de cliente HTTP (`httpx.MockTransport` para la red real de `fetch_fulltext`, clientes falsos para los SDK) y fixtures JSON reales recortadas; los de entrypoints corren el pipeline con el proveedor `fake` y un protocolo cuya única fuente es `imported/` (sin red), y el CLI `run` en un subproceso.

**Tech Stack:** Python 3.11/3.12/3.13, uv 0.11.x, GitHub Actions (`actions/checkout`, `astral-sh/setup-uv` fijados por SHA), pytest + pytest-xdist + pytest-cov, httpx (`MockTransport`), pypdf, ruff + black (línea 100).

**Spec:** `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`, §12 (PR-H) y D25; método §16; topología §15 (H es la segunda PR de la cadena: base `feat/ola2-contratos`, y base a su vez de PR-A). Plan hermano: `2026-10-18-ola2-pr0-contratos.md` (sus bloques **Interfaces** son la fuente de las firmas que aquí se consumen: `ScriptedProvider`, `fetch_disponible`, `RunMeta` v2).

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes y commits **en español**, con el tono del repo; las docstrings citan la auditoría («auditoría 2026-09-03, A13») o la decisión («D25»).
- Estilo: `ruff` (`E,F,I,UP,B,SIM`, línea 100, **`target-version py311`** desde la Tarea 2) y `black` (línea 100, `py311`), limpios en cada commit. `from __future__ import annotations` en todo módulo nuevo.
- Tests offline y deterministas; ninguno invoca `claude`, APIs reales ni WeasyPrint (la única comprobación real de WeasyPrint sigue siendo el paso «WeasyPrint importable» del CI, solo Ubuntu).
- Línea base: la suite de PR-0 en verde (recuento final anotado en el cuerpo de la PR-0; parte de 2 103 en `main` @ `c1af7c3`). Ningún test existente se borra; los dos `cronometrado` cambian su cota en Windows (Tarea 3) y `_SCRIPT_MEDIDO` precalienta imports (Tarea 3).
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"` y `uv run pytest -p no:cacheprovider -m cronometrado`; desde la Tarea 2 también `uv run --python 3.11 pytest …` y `--python 3.12`; lint, `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`.
- Commits pequeños, al menos uno por tarea, prefijo convencional, terminados con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Los implementadores no tocan** `CHANGELOG.md`, `README.md`, `AGENTS.md`, `RELEASING.md` (es de PR-I, §13), `docs/auditoria/` ni el spec; el controlador actualiza `CHANGELOG.md` y §19 en la Tarea 9. `CONTRIBUTING.md` **sí** se actualiza aquí (Tarea 8): describe el entorno y los comandos que esta PR cambia.
- No cambiar `revisia.__version__`. En `pyproject.toml` solo lo que lista la Tarea 2.
- Fixtures de red: solo JSON recortado de respuestas reales, con su procedencia en `tests/fixtures/README.md`; sin correos ni claves dentro (`mailto` fuera de la URL guardada).
- Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base.

## Review Focus

1. **Una celda Windows que falla por ruta larga o por tiempo** no se apaga ni se marca `skip`: se acorta `--basetemp`, se dobla la cota `cronometrado` o se documenta (riesgo 9). → Tareas 3 y 8 (`--basetemp` en Windows; `cota_de_tiempo`).
2. **`uv lock --check` en el CI con otra versión de uv que la local** puede dar un lock distinto sin que nadie haya tocado dependencias: el CI fija la versión de uv. → Tarea 8.
3. **El subproceso de `revisia run` lee `.env` del directorio actual**: si el test corre desde la raíz del repo con un `.env` real, carga claves ajenas. → Tarea 4 (`cwd=tmp_path`).
4. **Un `effects.yml`/`gold.yml` ausente en el protocolo offline** no debe hacer que el pipeline toque la red ni falle: la única fuente es `imported/`; sin DOI ni `oa_url` ningún registro consulta Unpaywall. → Tarea 4.
5. **Un cliente simulado que no responde a una URL que el código sí llama** (ID Converter antes de Unpaywall) haría que el test pase por la ruta equivocada: el manejador falla con `AssertionError` ante una URL no prevista. → Tarea 6.

---

## Topología de ejecución (subagentes)

Secuencial, en el worktree `C:\revisia-wt\h` (rama `feat/ola2-ci-tests`, creada desde `feat/ola2-contratos` en la Tarea 17 de PR-0). PR-A se desarrolla en paralelo desde PR-0 y se basa en H al abrir su PR; A, B, E₁, F₁ y G₁ no tocan `pyproject.toml`, `ci.yml`, `CONTRIBUTING.md` ni los tests nuevos de aquí (§15, tabla de solapes), así que no hay conflictos que prever.

| Tarea | Fichero(s) | Depende de |
|---|---|---|
| 1 | worktree y línea base | PR-0 cerrada |
| 2 | `pyproject.toml`, `uv.lock`, `tests/test_pyproject.py` | 1 |
| 3 | `tests/audit_fixtures.py`, `tests/test_audit_hitl_registro.py`, `tests/test_audit_infra.py` | 1 |
| 4 | `tests/test_entrypoints.py`, `tests/fakes.py` (`protocolo_offline`) | 1 |
| 5 | `tests/fixtures/*.json`, `tests/fixtures/README.md`, `tests/test_search_backends_parsers.py`, `tests/fakes.py` (`ClienteJSON`) | 1 |
| 6 | `tests/test_fulltext_fallback.py`, `tests/fakes.py` (`pdf_minimo`) | 1 |
| 7 | `tests/test_providers_api.py` | 1 |
| 8 | `.github/workflows/ci.yml`, `tests/test_ci_workflow.py`, `CONTRIBUTING.md` | 2, 3 |
| 9 | integración (controlador) | todas |

**Ciclo por tarea (§16):** implementador (subagente nuevo, TDD) → revisor (subagente nuevo: spec y plan primero, calidad después) → correcciones. Desviaciones a §19 del spec (Tarea 9). El controlador no pide confirmación entre tareas; **el merge lo decide el arquitecto.**

---

## Tarea 1: Worktree y línea base (controlador)

**Files:** ninguno.

- [ ] **Step 1:** Comprobar el worktree que creó PR-0 (si no existe, crearlo igual que allí).

```bash
cd C:/revisia-wt/h && git log --oneline -1 && git branch --show-current
```

Expected: rama `feat/ola2-ci-tests`, último commit = el `docs:` de integración de PR-0.

- [ ] **Step 2:** Entorno y suite.

```bash
uv sync --extra dev --extra search --extra meta
uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado
```

Expected: PASS; anotar el recuento (`N₀`).

---

## Tarea 2: `pyproject.toml`: Python ≥ 3.11, cobertura y lock

**Files:**
- Modify: `pyproject.toml` (`requires-python`, `classifiers`, `[project.optional-dependencies].dev`, `[tool.ruff].target-version`, `[tool.black].target-version`, secciones nuevas `[tool.coverage.run]` y `[tool.coverage.report]`).
- Modify: `uv.lock` (regenerado).
- Test: `tests/test_pyproject.py` (nuevo).

**Interfaces:**
- Produces (D25, §12):
  - `requires-python = ">=3.11"`; classifiers `Programming Language :: Python :: 3.11`, `3.12` y `3.13`.
  - `dev` gana `"pytest-cov>=5.0"`.
  - `[tool.ruff] target-version = "py311"`; `[tool.black] target-version = ["py311"]`.
  - `[tool.coverage.run] source = ["revisia"]`, `branch = false` (la cota se mide por líneas, como la auditoría); `[tool.coverage.report] fail_under = 90`, `show_missing = true`, `exclude_also = ["if TYPE_CHECKING:", "pragma: no cover"]`. Sin `omit`.
  - `uv.lock` con `requires-python = ">=3.11"` en cabecera.

- [ ] **Step 1: Test que falla** — crear `tests/test_pyproject.py`:

```python
"""Lo que `pyproject.toml` y `uv.lock` declaran para la matriz del CI (spec 2026-10-18 §12, D25)."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_requires_python_311_y_classifiers() -> None:
    project = _pyproject()["project"]
    assert project["requires-python"] == ">=3.11"
    for version in ("3.11", "3.12", "3.13"):
        assert f"Programming Language :: Python :: {version}" in project["classifiers"]


def test_herramientas_apuntan_a_py311() -> None:
    tool = _pyproject()["tool"]
    assert tool["ruff"]["target-version"] == "py311"
    assert tool["black"]["target-version"] == ["py311"]


def test_pytest_cov_en_dev_y_cobertura_con_cota_90() -> None:
    data = _pyproject()
    dev = data["project"]["optional-dependencies"]["dev"]
    assert any(d.startswith("pytest-cov") for d in dev)
    assert data["tool"]["coverage"]["run"]["source"] == ["revisia"]
    assert "omit" not in data["tool"]["coverage"]["run"]
    assert data["tool"]["coverage"]["report"]["fail_under"] == 90


def test_uv_lock_resuelto_para_311() -> None:
    cabecera = (ROOT / "uv.lock").read_text(encoding="utf-8")[:400]
    assert 'requires-python = ">=3.11"' in cabecera
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_pyproject.py -v`
Expected: FAIL en los cuatro (`">=3.13"`, `py313`, sin `pytest-cov`, sin `[tool.coverage]`).

- [ ] **Step 3: Implementar** los cambios de Interfaces en `pyproject.toml` (comentario junto a `requires-python`: «3.11 es el suelo que la suite ya cumplía en la Ola 1 con venv desechable; D25») y regenerar el lock:

```bash
uv lock
uv sync --extra dev --extra search --extra meta
```

- [ ] **Step 4: Run para verificar que pasa, en las tres versiones**

Run: `uv run pytest -p no:cacheprovider tests/test_pyproject.py -v`
Expected: PASS.

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`
Expected: limpio (con `py311` ruff deja de proponer sintaxis de 3.12+; si `ruff` o `black` reformatean algo por el cambio de objetivo, se acepta su versión y va en el mismo commit).

Run (ahora `uv run --python` funciona porque el lock cubre 3.11; uv recrea `.venv` con cada versión y avisa; al final se vuelve a 3.13):

```bash
for PY in 3.11 3.12 3.13; do
  uv run --python "$PY" --extra dev --extra search --extra meta pytest -p no:cacheprovider -q -n auto -m "not cronometrado" || exit 1
done
uv sync --extra dev --extra search --extra meta
```

Expected: PASS en las tres (uv descarga el intérprete que falte).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_pyproject.py
git commit -m "build: requires-python >= 3.11, objetivo py311, pytest-cov y cota de cobertura 90 (D25, M24)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 3: Tests sensibles al entorno: pico de memoria, cota de tiempo en Windows y la corrida real no versionada (M21)

**Files:**
- Modify: `tests/audit_fixtures.py` (función nueva `cota_de_tiempo`).
- Modify: `tests/test_audit_hitl_registro.py` (`_SCRIPT_MEDIDO`, línea 478; `_PICO_MAXIMO`, 474; `timeout=10` en la línea 560).
- Modify: `tests/test_audit_infra.py:449` (`timeout=10`).
- Modify: `tests/test_export_document.py:240-249` (borrar `_REAL_RUN` y `test_export_corrida_real`; M21).
- Test: `tests/test_audit_fixtures.py` (añadir).

**Interfaces:**
- Produces:
  - `audit_fixtures.cota_de_tiempo(segundos: int) -> int`: `segundos * 2` si `sys.platform == "win32"`, si no `segundos` (§12: «tolerancia ×2 en Windows»; los *runners* de GitHub en Windows son más lentos y la cota mide al auditor, no a la plataforma).
  - `_SCRIPT_MEDIDO` importa `revisia.audit.run_audit`, `revisia.meta_analysis`, `scipy.stats` (si existe), `yaml.CSafeLoader` (si existe) y **después** llama a `tracemalloc.start()`; comentario sobre `_PICO_MAXIMO`: «memoria del auditor, no de los imports: los perezosos (scipy, libyaml) se precalientan antes de medir, así la cota no depende de qué extras hay instalados».
  - M21 (auditoría 2026-09-03: «un test depende de la corrida real no versionada y de una ruta relativa al cwd; se salta en CI»): `test_export_corrida_real` y `_REAL_RUN = Path("runs/prisma-ia-origen-20260706-080747")` se **borran**. Sus dos aserciones verificables (`"mermaid" not in html`, PNG embebidos en base64) ya las cubren `test_mermaid_reemplazado_por_tabla_estatica` (`:146-148`) y `test_html_autocontenido_sin_recursos_externos` (`:130-137`) sobre la fixture `run_dir`; la tercera (el título de la revisión real) no es del motor. Un test nuevo fija que ningún fichero de `tests/` vuelva a apuntar a `runs/`.

- [ ] **Step 1: Test que falla** — añadir a `tests/test_audit_fixtures.py`:

```python
def test_cota_de_tiempo_dobla_solo_en_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    from audit_fixtures import cota_de_tiempo

    monkeypatch.setattr(sys, "platform", "win32")
    assert cota_de_tiempo(10) == 20
    monkeypatch.setattr(sys, "platform", "linux")
    assert cota_de_tiempo(10) == 10


def test_el_script_medido_precalienta_los_imports_antes_de_tracemalloc() -> None:
    from test_audit_hitl_registro import _SCRIPT_MEDIDO

    antes = _SCRIPT_MEDIDO.index("tracemalloc.start()")
    for modulo in ("revisia.meta_analysis", "scipy.stats", "yaml", "revisia.audit"):
        assert modulo in _SCRIPT_MEDIDO[:antes], modulo


def test_ningun_test_depende_de_una_corrida_real_en_runs() -> None:
    # M21: la corrida real no se versiona (D11 de la Ola 1); un test que la busque por ruta
    # relativa al cwd se salta en CI y no verifica nada.
    patron = re.compile(r"""Path\(\s*["']runs/""")
    culpables = [p.name for p in Path(__file__).parent.glob("test_*.py") if patron.search(p.read_text(encoding="utf-8"))]
    assert culpables == []
```

(`import re`, `import sys`, `import pytest` y `from pathlib import Path` si faltan en el fichero.)

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_fixtures.py -v -k "cota or precalienta or corrida_real"`
Expected: FAIL (`ImportError: cota_de_tiempo`; `scipy.stats` no está antes de `tracemalloc.start()`; `culpables == ["test_export_document.py"]`).

- [ ] **Step 3: Implementar**: `cota_de_tiempo` en `tests/audit_fixtures.py`; `_SCRIPT_MEDIDO` con los imports precalentados dentro de `try/except ImportError` para `scipy.stats` y `from yaml import CSafeLoader`; cambiar `timeout=10` por `timeout=cota_de_tiempo(10)` en `tests/test_audit_hitl_registro.py:560` y `tests/test_audit_infra.py:449` (importar `cota_de_tiempo` de `audit_fixtures`); borrar `_REAL_RUN` y `test_export_corrida_real` de `tests/test_export_document.py` (y el `import` que quede sin uso, si lo hay).

- [ ] **Step 4: Run para verificar que pasa, con y sin el extra `meta`**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_fixtures.py tests/test_audit_hitl_registro.py -v -k "cota or precalienta or pico"`
Expected: PASS.

Run (sin scipy, en un venv desechable, para fijar que la cota ya no depende de los extras):

```bash
TMP="$(mktemp -d)"
uv venv -q --python 3.13 "$TMP/sin-meta"
uv pip install -q --python "$TMP/sin-meta" -e . pytest pytest-xdist
PYTHONPATH=. "$TMP/sin-meta/Scripts/python" -m pytest -p no:cacheprovider tests/test_audit_hitl_registro.py -k pico -q
```

Expected: PASS (en POSIX la ruta es `bin/python`). Con el extra `meta` del venv principal, el mismo test también PASS: la cota ya no cambia con los extras.

Run: `uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/audit_fixtures.py tests/test_audit_fixtures.py tests/test_audit_hitl_registro.py tests/test_audit_infra.py tests/test_export_document.py
git commit -m "test: pico de memoria con imports precalentados, cota x2 en Windows y sin tests sobre la corrida real (M21, memoria Ola 1, riesgo 9)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 4: Tests de entrypoints (A13)

**Files:**
- Modify: `tests/fakes.py` (función nueva `protocolo_offline`).
- Test: `tests/test_entrypoints.py` (nuevo).

**Interfaces:**
- Consumes: `run_review`, `resume_review` (`revisia.orchestration.flow`, firmas vigentes: `run_review(protocol_dir, *, timestamp, runs_root="runs", max_results=25, auto_approve=False, mailto=None)`, `resume_review(run_dir, *, protocol_dir=None, auto_approve=False, mailto=None)`); `run_review_with_agent(protocol_dir, callback, *, timestamp=None, runs_root="runs", max_results=25, auto_approve=True, mailto=None, search_fn=None, fetch_fn=None, run_dir=None)` (`revisia.agent_driver`; PR-A cambia el default de `auto_approve` a `False`: estos tests lo pasan **siempre explícito**); `main` (`revisia.cli`); `responder_gate` (`hitl_helpers`); fixture `corrida` (`tests/conftest.py`: corrida completada con `03_screening/decisions.json`); `_fabricate_model` (`revisia.llm.providers.fake`).
- Produces:
  - `fakes.protocolo_offline(dest: Path, *, provider: str = "fake", model: str = "fake-1") -> Path`: copia `examples/demo-mini-review` a `dest`, pone `databases: [Scopus]` (base de importación manual: `search_stage` no llama a ningún backend), escribe `dest/imported/corpus.ris` con **dos** registros sin DOI, sin URL y sin PMCID (`TY  - JOUR`, `TI`, `AU`, `PY  - 2021`, `AB`, `ER  -`; títulos distintos: `"LLM screening for systematic reviews"` y `"Active learning with ASReview"`), borra `search_strings/` y `effects.yml`, y sustituye el `provider`/`model` de **todas** las entradas de `llm` y `ensemble_llm` por los dados. Sin DOI ni `oa_url`, `fetch_fulltext` no toca la red (`sin_url_oa`), así que la corrida completa sin red con 0 incluidos. Devuelve `dest`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_entrypoints.py`:

```python
"""Entrypoints de ejecución (auditoría 2026-09-03, A13): flow, agent_driver y CLI, offline.

Lo que ya cubrían otros ficheros no se repite: `new` (`test_flow_oficial_y_check.py:145,152`),
`export` (`test_export_document.py:218-234`), `check` (`test_flow_oficial_y_check.py:164`),
`audit` (`test_audit.py:78,85`), `validate` con protocolos inválidos (`test_cli_validate.py`) y
el rc 3 de `run` (`test_cli_reanudacion.py::test_cli_interrupcion_rc_3_con_instrucciones`, en
proceso: un fallo transitorio no se reproduce en un subproceso sin red).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from fakes import protocolo_offline
from hitl_helpers import responder_gate

from revisia.agent_driver import run_review_with_agent
from revisia.cli import main
from revisia.llm.providers.fake import _fabricate_model
from revisia.orchestration.flow import resume_review, run_review
from revisia.provenance.ledger import DecisionLedger

ROOT = Path(__file__).resolve().parent.parent
_CLI = "import sys; from revisia.cli import main; sys.exit(main(sys.argv[1:]))"


@pytest.fixture(autouse=True)
def _sin_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("revisia.cli._load_dotenv", lambda: None)


def test_protocolo_offline_no_declara_fuentes_con_backend(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    assert raw["databases"] == ["Scopus"]
    assert (proto / "imported" / "corpus.ris").read_text(encoding="utf-8").count("ER  -") == 2
    assert not (proto / "search_strings").exists() and not (proto / "effects.yml").exists()
    assert {c["provider"] for c in raw["llm"].values()} == {"fake"}


def test_run_review_de_punta_a_punta_sin_red(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    result = run_review(proto, timestamp="T", runs_root=tmp_path / "runs", auto_approve=True)
    assert result.status == "completed"
    assert result.counts is not None and result.counts.identified == 2
    assert result.counts.fulltext_not_retrieved == 2 and result.counts.included == 0
    run_dir = result.run_dir
    assert run_dir.parent == tmp_path / "runs"
    assert (run_dir / "run.json").exists() and (run_dir / "manifest.yml").exists()
    log = json.loads((run_dir / "01_search" / "log.json").read_text(encoding="utf-8"))
    assert {e["kind"] for e in log["entries"]} == {"database", "manual_import"}
    assert all(e["status"] in {"manual_only", "ok"} for e in log["entries"])


def test_run_review_pausa_en_el_gate_y_resume_review_continua(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    pausa = run_review(proto, timestamp="T", runs_root=tmp_path / "runs", auto_approve=False)
    assert (pausa.status, pausa.stage) == ("paused", "screening_ta")
    responder_gate(pausa.run_dir, "screening_ta")
    final = resume_review(pausa.run_dir, protocol_dir=proto, auto_approve=True)
    assert final.status == "completed"
    acciones = [e.action for e in DecisionLedger(pausa.run_dir / "decisions_ledger.jsonl").read_all()]
    assert acciones[0] in {"label", "approve"} and "approve" in acciones


def _callback(req, schema):
    return _fabricate_model(schema) if schema is not None else "Síntesis de prueba del agente."


def test_agent_driver_sin_auto_approve_pausa_en_el_primer_gate(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p", provider="agent", model="session-agent")
    result = run_review_with_agent(
        proto, _callback, timestamp="T", runs_root=tmp_path / "runs", auto_approve=False
    )
    assert (result.status, result.stage) == ("paused", "screening_ta")
    ledger = DecisionLedger(result.run_dir / "decisions_ledger.jsonl").read_all()
    assert not any(e.action == "approve" for e in ledger)


def test_agent_driver_con_auto_approve_explicito_completa_y_reanuda(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p", provider="agent", model="session-agent")
    result = run_review_with_agent(
        proto, _callback, timestamp="T", runs_root=tmp_path / "runs", auto_approve=True
    )
    assert result.status == "completed"
    otra = run_review_with_agent(None, _callback, run_dir=result.run_dir, auto_approve=True)
    assert otra.status == "completed" and otra.run_dir == result.run_dir


def test_cli_gold_template_desde_una_corrida(corrida: Path, tmp_path: Path, capsys) -> None:
    out = tmp_path / "gold_template.yml"
    assert main(["gold-template", str(corrida), "--out", str(out)]) == 0
    texto = out.read_text(encoding="utf-8")
    assert texto.startswith("# gold.yml") and "\ngold:\n" in texto
    ids = json.loads((corrida / "03_screening" / "decisions.json").read_text(encoding="utf-8"))
    assert texto.count('  # "') == len({d["record_id"] for d in ids})
    assert "Plantilla gold" in capsys.readouterr().out
    assert main(["gold-template", str(tmp_path / "sin-corrida")]) == 2
    assert "decisions.json" in capsys.readouterr().err


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _CLI, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def test_cli_run_en_subproceso_sale_0_y_deja_la_corrida(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    runs = tmp_path / "runs"
    proc = _run_cli("run", str(proto), "--auto-approve", "--runs-root", str(runs), cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "COMPLETED" in proc.stdout and "Traceback" not in proc.stderr
    corridas = list(runs.iterdir())
    assert len(corridas) == 1 and (corridas[0] / "manifest.yml").exists()


def test_cli_run_en_subproceso_sale_2_con_a3_en_una_etapa_de_juicio(tmp_path: Path) -> None:
    proto = protocolo_offline(tmp_path / "p")
    raw = yaml.safe_load((proto / "protocol.yml").read_text(encoding="utf-8"))
    raw.setdefault("autonomy", {})["screening_ta"] = "A3"
    (proto / "protocol.yml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    proc = _run_cli("run", str(proto), "--auto-approve", "--runs-root", str(tmp_path / "runs"), cwd=tmp_path)
    assert proc.returncode == 2 and "A3" in proc.stderr and "Traceback" not in proc.stderr
    assert not (tmp_path / "runs").exists()


def test_cli_validate_del_protocolo_offline_sale_0(tmp_path: Path, capsys) -> None:
    proto = protocolo_offline(tmp_path / "p")
    assert main(["validate", str(proto)]) == 0
    salida = capsys.readouterr()
    assert salida.out and "error" not in salida.err.lower()
```

El rc 3 (`RunInterrupted`) no se reproduce en un subproceso sin red ni dobles inyectables; lo cubre en proceso `tests/test_cli_reanudacion.py::test_cli_interrupcion_rc_3_con_instrucciones` (Ola 1). Se deja constancia en la docstring del fichero.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_entrypoints.py -v`
Expected: FAIL (`ImportError: cannot import name 'protocolo_offline' from 'fakes'`).

- [ ] **Step 3: Implementar** `protocolo_offline` en `tests/fakes.py` según Interfaces (docstring: por qué Scopus + `imported/` es la única forma de que `run_review` y el CLI corran sin red ni dobles, A13). Si algún test del paso 1 revela una expectativa falsa del plan (p. ej. la primera acción del ledger), se ajusta la aserción al comportamiento real **documentado** del motor y se anota en §19.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_entrypoints.py tests/test_fakes.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fakes.py tests/test_entrypoints.py
git commit -m "test: entrypoints run_review, resume_review, agent_driver y CLI run/gold-template offline (A13)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 5: Parsers de Crossref y Semantic Scholar con fixtures reales recortadas (M18)

**Files:**
- Create: `tests/fixtures/crossref_works.json`, `tests/fixtures/s2_paper_search.json`, `tests/fixtures/README.md`.
- Modify: `tests/fakes.py` (clase nueva `ClienteJSON`).
- Test: `tests/test_search_backends_parsers.py` (nuevo).

**Interfaces:**
- Consumes: `search_backends.crossref_search`, `search_backends.semantic_scholar_search`, `search_backends._client` (indirección que los tests sustituyen, como `tests/test_search_multibase.py:75`).
- Produces:
  - `fakes.ClienteJSON(payload: dict)`: context manager con `get(url, params=None)` que devuelve un objeto con `raise_for_status()` y `json()`; guarda `last_url` y `last_params` (es el `_FakeClient` de `test_search_multibase.py` hecho compartible; ese fichero no se toca).
  - Fixtures: respuestas reales **recortadas a tres ítems**, capturadas una vez con red por el implementador y guardadas en UTF-8 con LF:

```bash
curl -s "https://api.crossref.org/works?query=large+language+models+systematic+review+screening&rows=3&filter=has-abstract:true&mailto=<tu-correo>" > tests/fixtures/crossref_works.json
curl -s "https://api.semanticscholar.org/graph/v1/paper/search?query=large+language+models+systematic+review+screening&limit=3&fields=title,abstract,year,externalIds,authors,url,openAccessPdf" > tests/fixtures/s2_paper_search.json
```

  Recorte y ediciones, siempre anotadas en `tests/fixtures/README.md` (fecha, URL sin `mailto`, qué se borró): Crossref: conservar `status`, `message-type`, `message.total-results`, `message.items`; borrar `message.facets` y `message.query`; en el **tercer** ítem borrar la clave `DOI` (para ejercitar el `record_id` de respaldo). S2: conservar `total`, `offset`, `data`; en el **tercer** paper borrar `externalIds.DOI`; al menos un paper con `openAccessPdf.url` (si la consulta no lo trae, repetir con otra consulta antes de editar). Ningún correo ni clave en los ficheros.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_search_backends_parsers.py`:

```python
"""Parsers de Crossref y Semantic Scholar sobre respuestas reales recortadas (auditoría 2026-09-03, M18)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fakes import ClienteJSON

from revisia.agents import search_backends
from revisia.agents.search_backends import crossref_search, semantic_scholar_search

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _carga(nombre: str) -> dict:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def test_las_fixtures_no_llevan_correo_ni_claves() -> None:
    for nombre in ("crossref_works.json", "s2_paper_search.json"):
        texto = (FIXTURES / nombre).read_text(encoding="utf-8")
        assert "mailto=" not in texto and "api_key" not in texto
        assert not _CORREO.search(texto), nombre
    assert (FIXTURES / "README.md").read_text(encoding="utf-8").count("https://api.") >= 2


def test_crossref_parsea_los_tres_items_reales(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _carga("crossref_works.json")
    cliente = ClienteJSON(payload)
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: cliente)
    records = crossref_search("q", 10, mailto="revisora@example.org")
    items = payload["message"]["items"]
    assert len(records) == len(items) == 3
    assert cliente.last_params == {"query": "q", "rows": 10, "mailto": "revisora@example.org"}
    for rec, it in zip(records, items, strict=True):
        doi = (it.get("DOI") or "").lower().strip() or None
        assert rec.doi == doi
        assert (rec.record_id == doi) if doi else rec.record_id.startswith("crossref:")
        assert rec.title == (it["title"][0] if it.get("title") else "(sin título)")
        partes = (it.get("issued") or {}).get("date-parts") or [[None]]
        assert rec.year == (partes[0][0] if partes and partes[0] else None)  # misma guarda que el parser
        assert rec.url == it.get("URL") and rec.source_db == "Crossref"
        if it.get("abstract"):
            assert rec.abstract and "<" not in rec.abstract  # JATS (<jats:p>) fuera
        assert len(rec.authors) == len([a for a in it.get("author", []) if a.get("given") or a.get("family")])
    assert sum(1 for r in records if r.doi is None) == 1
    assert any(it.get("abstract") for it in items)


def test_semantic_scholar_parsea_los_tres_papers_reales(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _carga("s2_paper_search.json")
    cliente = ClienteJSON(payload)
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: cliente)
    records = semantic_scholar_search("q", 10)
    papers = payload["data"]
    assert len(records) == len(papers) == 3
    assert cliente.last_params["limit"] == 10 and "externalIds" in cliente.last_params["fields"]
    for rec, p in zip(records, papers, strict=True):
        doi = ((p.get("externalIds") or {}).get("DOI") or "").lower().strip() or None
        assert rec.doi == doi
        assert rec.record_id == (doi or f"s2:{p['paperId']}")
        assert rec.title == (p.get("title") or "(sin título)") and rec.year == p.get("year")
        assert rec.abstract == p.get("abstract") and rec.url == p.get("url")
        assert rec.authors == [a["name"] for a in p.get("authors", []) if a.get("name")]
        oa = (p.get("openAccessPdf") or {}).get("url")
        assert (rec.extra.get("oa_url") == oa) if oa else ("oa_url" not in rec.extra)
        assert rec.source_db == "SemanticScholar"
    assert sum(1 for r in records if r.doi is None) == 1
    assert any("oa_url" in r.extra for r in records)


def test_max_results_recorta_los_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: ClienteJSON(_carga("crossref_works.json")))
    assert len(crossref_search("q", 2)) == 2
    monkeypatch.setattr(search_backends, "_client", lambda timeout=60.0: ClienteJSON(_carga("s2_paper_search.json")))
    assert len(semantic_scholar_search("q", 1)) == 1
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_search_backends_parsers.py -v`
Expected: FAIL (`ImportError: ClienteJSON`; después, fixtures ausentes).

- [ ] **Step 3: Implementar**: `ClienteJSON` en `tests/fakes.py`; capturar y recortar las fixtures (una sola vez con red; validar con `python -m json.tool`); escribir `tests/fixtures/README.md` (procedencia, fecha, recortes y ediciones; licencia de los metadatos: Crossref y S2 permiten reutilizar metadatos bibliográficos).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_search_backends_parsers.py tests/test_search_multibase.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures tests/fakes.py tests/test_search_backends_parsers.py
git commit -m "test: parsers de Crossref y Semantic Scholar con respuestas reales recortadas (M18)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 6: Ruta de texto completo Unpaywall → PDF/HTML con `httpx.MockTransport` (M19)

**Files:**
- Modify: `tests/fakes.py` (función nueva `pdf_minimo`).
- Test: `tests/test_fulltext_fallback.py` (nuevo).

**Interfaces:**
- Consumes: `fetch_fulltext(record, *, mailto=None, max_chars=20000)` (`revisia.agents.fulltext`), `ncbi.IDCONV_URL`, `httpx.MockTransport`, `httpx.Response`.
- Produces:
  - `fakes.pdf_minimo(texto: str) -> bytes`: un PDF 1.4 de una página con `texto` en Helvetica 12, construido a mano (catálogo, páginas, página, contenido `BT /F1 12 Tf 72 712 Td (texto) Tj ET`, fuente; tabla `xref` con offsets reales y `trailer`). Verificado el 2026-10-18: `pypdf.PdfReader(...).pages[0].extract_text()` devuelve el texto. `texto` solo ASCII sin paréntesis ni barras (el test lo garantiza).
  - Fixture local del test `cliente_simulado(monkeypatch)`: sustituye `httpx.Client` por `lambda **kw: _Client(transport=httpx.MockTransport(manejador), **kw)` (el `Client` real con transporte simulado), de modo que **todas** las conexiones de `fetch_fulltext` (ID Converter vía `_http.make_client`, Unpaywall y la descarga) pasan por `manejador(request) -> httpx.Response`; una URL no prevista lanza `AssertionError` con la URL (Review Focus 5).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_fulltext_fallback.py`:

```python
"""Ruta Unpaywall → PDF/HTML de `fetch_fulltext` con la red simulada (auditoría 2026-09-03, M19)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from fakes import pdf_minimo

from revisia.agents import ncbi
from revisia.agents.fulltext import fetch_fulltext
from revisia.schemas.records import SearchRecord

UNPAYWALL = "https://api.unpaywall.org/v2/"
PDF_URL = "https://repo.example/articulo.pdf"
HTML_URL = "https://repo.example/articulo.html"
SIN_PMCID = {"status": "ok", "records": [{"doi": "10.1000/xyz", "status": "error", "errmsg": "invalid article id"}]}


def _registro() -> SearchRecord:
    return SearchRecord(record_id="10.1000/xyz", title="t", abstract="resumen", doi="10.1000/xyz")


@pytest.fixture
def cliente_simulado(monkeypatch: pytest.MonkeyPatch) -> Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]:
    """Instala un manejador para toda conexión httpx y devuelve la lista de peticiones vistas."""

    def instalar(manejador):
        vistas: list[httpx.Request] = []
        real = httpx.Client

        def enrutado(request: httpx.Request) -> httpx.Response:
            vistas.append(request)
            return manejador(request)

        monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(enrutado), **kw))
        # El ID Converter pasa por `ncbi._throttle` (0,34 s entre llamadas): sin esto cada test
        # duerme. `ncbi._sleep` es la indirección prevista para tests (`ncbi.py:32`).
        monkeypatch.setattr(ncbi, "_sleep", lambda _s: None)
        return vistas

    return instalar


def _manejador(unpaywall: httpx.Response, descarga: httpx.Response | None = None):
    def manejador(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(ncbi.IDCONV_URL):
            return httpx.Response(200, json=SIN_PMCID)
        if url.startswith(UNPAYWALL):
            assert request.url.params.get("email") == "revisora@example.org"
            return unpaywall
        if descarga is not None and url in (PDF_URL, HTML_URL):
            return descarga
        raise AssertionError(f"URL no prevista por el test: {url}")

    return manejador


def test_pdf_minimo_es_legible_por_pypdf() -> None:
    pypdf = pytest.importorskip("pypdf")
    import io

    datos = pdf_minimo("Texto completo de prueba")
    assert datos.startswith(b"%PDF-1.4") and datos.rstrip().endswith(b"%%EOF")
    assert pypdf.PdfReader(io.BytesIO(datos)).pages[0].extract_text() == "Texto completo de prueba"
    with pytest.raises(ValueError):
        pdf_minimo("con (paréntesis)")


def test_unpaywall_url_for_pdf_descarga_y_extrae_el_pdf(cliente_simulado) -> None:
    pytest.importorskip("pypdf")
    vistas = cliente_simulado(
        _manejador(
            httpx.Response(200, json={"best_oa_location": {"url_for_pdf": PDF_URL, "url": HTML_URL}}),
            httpx.Response(200, content=pdf_minimo("Texto completo de prueba"), headers={"content-type": "application/pdf"}),
        )
    )
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert ft.available is True and ft.reason is None
    assert "Texto completo de prueba" in ft.text and ft.source_url == PDF_URL
    assert [str(r.url).split("?")[0] for r in vistas] == [ncbi.IDCONV_URL, f"{UNPAYWALL}10.1000/xyz", PDF_URL]


def test_unpaywall_url_html_se_limpia(cliente_simulado) -> None:
    cliente_simulado(
        _manejador(
            httpx.Response(200, json={"best_oa_location": {"url": HTML_URL}}),
            httpx.Response(200, content=b"<html><script>x()</script><body><p>Texto <b>completo</b> en HTML.</p></body></html>", headers={"content-type": "text/html; charset=utf-8"}),
        )
    )
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert ft.available is True and ft.text == "Texto completo en HTML." and ft.source_url == HTML_URL


def test_unpaywall_404_es_sin_url_oa(cliente_simulado) -> None:
    cliente_simulado(_manejador(httpx.Response(404)))
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert (ft.available, ft.reason) == (False, "sin_url_oa") and ft.text == "resumen"


def test_unpaywall_503_es_error_http_transitorio(cliente_simulado) -> None:
    cliente_simulado(_manejador(httpx.Response(503)))
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert (ft.available, ft.reason) == (False, "error_http") and "503" in (ft.detail or "")


def test_descarga_404_tras_unpaywall_es_error_http(cliente_simulado) -> None:
    cliente_simulado(_manejador(httpx.Response(200, json={"best_oa_location": {"url": HTML_URL}}), httpx.Response(404)))
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert (ft.available, ft.reason) == (False, "error_http")


def test_pdf_sin_texto_extraible_es_texto_vacio(cliente_simulado) -> None:
    pytest.importorskip("pypdf")
    cliente_simulado(_manejador(httpx.Response(200, json={"best_oa_location": {"url_for_pdf": PDF_URL}}), httpx.Response(200, content=b"%PDF-1.4\n%%EOF\n", headers={"content-type": "application/pdf"})))
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org")
    assert (ft.available, ft.reason) == (False, "texto_vacio")


def test_el_recorte_a_max_chars_se_aplica_al_texto_descargado(cliente_simulado) -> None:
    cliente_simulado(_manejador(httpx.Response(200, json={"best_oa_location": {"url": HTML_URL}}), httpx.Response(200, content=b"<p>" + b"palabra " * 5_000 + b"</p>", headers={"content-type": "text/html"})))
    ft = fetch_fulltext(_registro(), mailto="revisora@example.org", max_chars=100)
    assert ft.available is True and len(ft.text) == 100


def test_sin_mailto_no_se_consulta_unpaywall(cliente_simulado) -> None:
    def ninguna(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"sin --mailto no debe salir ninguna petición: {request.url}")

    vistas = cliente_simulado(ninguna)
    ft = fetch_fulltext(_registro())
    assert (ft.available, ft.reason) == (False, "sin_url_oa") and vistas == []
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_fulltext_fallback.py -v`
Expected: FAIL (`ImportError: pdf_minimo`).

- [ ] **Step 3: Implementar** `pdf_minimo` en `tests/fakes.py` (añadir `import io` a los imports del fichero, que hoy no lo trae). El algoritmo no se deduce de la firma, así que va aquí:

```python
def pdf_minimo(texto: str) -> bytes:
    if not texto.isascii() or any(c in texto for c in "()\\"):
        raise ValueError("pdf_minimo: solo ASCII sin paréntesis ni barras")
    contenido = f"BT /F1 12 Tf 72 712 Td ({texto}) Tj ET".encode()
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n" + contenido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = io.BytesIO()
    salida.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for numero, objeto in enumerate(objetos, 1):
        offsets.append(salida.tell())
        salida.write(f"{numero} 0 obj\n".encode() + objeto + b"\nendobj\n")
    xref = salida.tell()
    salida.write(f"xref\n0 {len(objetos) + 1}\n".encode() + b"0000000000 65535 f \n")
    for offset in offsets:
        salida.write(f"{offset:010d} 00000 n \n".encode())
    salida.write(
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return salida.getvalue()
```

Si alguna aserción del paso 1 no coincide con el comportamiento real de `fetch_fulltext` (p. ej. el texto HTML limpio con un espacio distinto), se corrige la aserción al comportamiento documentado del módulo, nunca el módulo (PR-H no toca `revisia/`).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_fulltext_fallback.py tests/test_fulltext.py tests/test_errores_deterministas.py -v -k "fulltext or unpaywall or pdf"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fakes.py tests/test_fulltext_fallback.py
git commit -m "test: ruta Unpaywall → PDF/HTML de fetch_fulltext con httpx.MockTransport y un PDF mínimo (M19)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 7: Proveedores API con clientes falsos (M20)

**Files:**
- Test: `tests/test_providers_api.py` (nuevo).

**Interfaces:**
- Consumes: `GeminiProvider` (`_client`, `_config`), `OpenAIProvider`/`LocalOpenAIProvider`/`ZaiProvider`/`OpenRouterProvider` (`_client`), `AnthropicProvider` (`_client`); `RunMeta` v2 (PR-0); `sha256_text`.
- Produces: solo tests. Los SDK **no** están instalados en la matriz del CI (extras `gemini`/`openai`/`anthropic` fuera; el job `sdk-smoke` de la Tarea 8 comprueba aparte, con los SDK reales, que la superficie imitada existe; §19 fila 6): los «transports falsos» son objetos que imitan la superficie que cada proveedor usa (`models.generate_content`, `chat.completions.create`, `beta.chat.completions.parse`, `messages.create`), inyectados por `monkeypatch` en `_client` (y en `_config` de Gemini, que importa `google.genai.types`). Lo que **PR-A** cambia (`*_applied`, `model_source`, `backend_version`, `prompt_sha256` del texto enviado en `local_openai`) va en tests `xfail(strict=True, reason="PR-A …")`: hoy fallan a propósito y PR-A, al implementarlo, quita el marcador (un XPASS estricto rompe la suite, así que no puede olvidarse).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_providers_api.py`:

```python
"""Proveedores API con clientes falsos (auditoría 2026-09-03, M20): plomería y RunMeta, sin SDK ni red."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from revisia.llm.base import LLMProvider, LLMRequest
from revisia.llm.providers.anthropic_api import AnthropicProvider
from revisia.llm.providers.gemini import GeminiProvider
from revisia.llm.providers.local_openai import LocalOpenAIProvider
from revisia.llm.providers.openai_api import OpenAIProvider
from revisia.llm.providers.openai_compat import OpenRouterProvider, ZaiProvider
from revisia.provenance.runmeta import sha256_text


class Salida(BaseModel):
    etiqueta: str
    n: int


REQ = LLMRequest(prompt="¿Incluir?", system="Eres un cribador.", temperature=0.3, seed=42)
V1 = sha256_text("Eres un cribador.\n¿Incluir?")  # fórmula de la 0.8: system + "\n" + prompt


# ── Gemini ───────────────────────────────────────────────────────────────────


class _Gemini:
    def __init__(self) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        parsed = Salida(etiqueta="include", n=1) if "response_schema" in str(kw.get("config")) else None
        return SimpleNamespace(
            text='{"etiqueta": "include", "n": 1}',
            parsed=parsed,
            model_version="gemini-3.5-flash-lite-001",
            usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=5),
        )


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch) -> tuple[GeminiProvider, _Gemini]:
    cliente = _Gemini()
    proveedor = GeminiProvider("gemini-3.5-flash-lite")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    monkeypatch.setattr(proveedor, "_config", lambda req, **extra: {"temperature": req.temperature, "seed": req.seed, **extra})
    return proveedor, cliente


def test_gemini_complete_y_structured_con_cliente_falso(gemini) -> None:
    proveedor, cliente = gemini
    assert isinstance(proveedor, LLMProvider)
    resp = proveedor.complete(REQ)
    assert resp.text.startswith("{") and resp.meta.provider == "gemini"
    assert (resp.meta.model_version, resp.meta.input_tokens, resp.meta.output_tokens) == ("gemini-3.5-flash-lite-001", 11, 5)
    assert resp.meta.prompt_sha256 == V1 and resp.meta.deterministic is False
    obj, meta = proveedor.structured(REQ, Salida)
    assert obj == Salida(etiqueta="include", n=1) and meta.prompt_sha256 == V1
    assert cliente.llamadas[1]["config"]["response_schema"] is Salida
    assert (meta.seed, meta.temperature) == (42, 0.3)  # lo pedido, como la v1


@pytest.mark.xfail(strict=True, reason="PR-A (spec §5.2): lo aplicado y model_source=backend")
def test_gemini_runmeta_v2_aplicado(gemini) -> None:
    # `backend_version` no se afirma aquí: sin el SDK instalado (matriz del CI) PR-A lo deja
    # en None; PR-A lo prueba con `importlib.metadata.version` sustituido.
    proveedor, _ = gemini
    meta = proveedor.complete(REQ).meta
    assert (meta.seed_applied, meta.temperature_applied) == (42, 0.3)
    assert meta.model_source == "backend"


# ── OpenAI y compatibles ─────────────────────────────────────────────────────


class _OpenAI:
    def __init__(self, *, parsed: bool = True, content: str | None = '{"etiqueta": "include", "n": 1}') -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=self._parse)))
        self._parsed, self._content = parsed, content

    def _resp(self, message: Any) -> Any:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            model="gpt-4o-mini-2024-07-18",
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )

    def _create(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        return self._resp(SimpleNamespace(content=self._content))

    def _parse(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        parsed = Salida(etiqueta="include", n=1) if self._parsed else None
        return self._resp(SimpleNamespace(parsed=parsed, content=self._content, refusal="no" if not self._parsed else None))


def test_openai_complete_y_structured_pasan_los_parametros(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _OpenAI()
    proveedor = OpenAIProvider("gpt-4o-mini")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    resp = proveedor.complete(REQ)
    assert resp.meta.model_version == "gpt-4o-mini-2024-07-18" and resp.meta.prompt_sha256 == V1
    assert (resp.meta.input_tokens, resp.meta.output_tokens) == (7, 3)
    assert cliente.llamadas[0]["seed"] == 42 and cliente.llamadas[0]["temperature"] == 0.3
    assert cliente.llamadas[0]["messages"][0] == {"role": "system", "content": "Eres un cribador."}
    obj, meta = proveedor.structured(REQ, Salida)
    assert obj.etiqueta == "include" and cliente.llamadas[1]["response_format"] is Salida and meta.prompt_sha256 == V1


def test_openai_rehusar_structured_es_error_accionable(monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = OpenAIProvider("gpt-4o-mini")
    monkeypatch.setattr(proveedor, "_client", lambda: _OpenAI(parsed=False))
    with pytest.raises(RuntimeError, match="salida estructurada"):
        proveedor.structured(REQ, Salida)


def test_local_openai_inyecta_el_schema_en_el_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _OpenAI()
    proveedor = LocalOpenAIProvider("llama")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    obj, meta = proveedor.structured(REQ, Salida)
    enviado = cliente.llamadas[0]["messages"][-1]["content"]
    assert obj.n == 1 and enviado.startswith("¿Incluir?") and '"etiqueta"' in enviado
    assert cliente.llamadas[0]["response_format"] == {"type": "json_object"}
    assert meta.prompt_sha256 == V1  # la 0.8 hashea el prompt ORIGINAL, no el enviado (A7)


@pytest.mark.xfail(strict=True, reason="PR-A (spec §5.2, A7): prompt_sha256 del texto enviado con el schema")
def test_local_openai_prompt_sha256_es_del_texto_enviado(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _OpenAI()
    proveedor = LocalOpenAIProvider("llama")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    _, meta = proveedor.structured(REQ, Salida)
    enviado = cliente.llamadas[0]["messages"][-1]["content"]
    assert meta.prompt_sha256 == sha256_text(f"Eres un cribador.\n{enviado}") and meta.schema_sha256 is None


@pytest.mark.parametrize(("clase", "variable"), [(ZaiProvider, "ZAI_API_KEY"), (OpenRouterProvider, "OPENROUTER_API_KEY")])
def test_gateways_exigen_su_key_y_usan_su_base_url(monkeypatch: pytest.MonkeyPatch, clase, variable: str) -> None:
    monkeypatch.delenv(variable, raising=False)
    with pytest.raises(RuntimeError, match=variable):
        clase("m").complete(REQ)
    monkeypatch.setenv(variable, "k")
    proveedor = clase("m")
    assert proveedor.base_url and proveedor.base_url.startswith("https://")
    cliente = _OpenAI()
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    assert proveedor.complete(REQ).meta.provider == clase.name


# ── Anthropic ────────────────────────────────────────────────────────────────


class _Anthropic:
    def __init__(self, *, tool_use: bool = True) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)
        self._tool_use = tool_use

    def _create(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        bloques = [SimpleNamespace(type="text", text="hola ")]
        if "tools" in kw and self._tool_use:
            bloques = [SimpleNamespace(type="tool_use", input={"etiqueta": "include", "n": 1})]
        return SimpleNamespace(content=bloques, model="claude-sonnet-5-5-20260601", usage=SimpleNamespace(input_tokens=9, output_tokens=2))


def test_anthropic_complete_y_structured_por_tool_use(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _Anthropic()
    proveedor = AnthropicProvider("claude-sonnet-5-5")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    resp = proveedor.complete(REQ)
    assert resp.text == "hola " and resp.meta.model_version == "claude-sonnet-5-5-20260601"
    assert cliente.llamadas[0]["system"] == "Eres un cribador." and "seed" not in cliente.llamadas[0]
    obj, meta = proveedor.structured(REQ, Salida)
    assert obj.n == 1 and cliente.llamadas[1]["tool_choice"] == {"type": "tool", "name": "Salida"}
    assert meta.prompt_sha256 == V1 and (meta.seed, meta.temperature) == (42, 0.3)


def test_anthropic_sin_tool_use_es_error_accionable(monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = AnthropicProvider("claude-sonnet-5-5")
    monkeypatch.setattr(proveedor, "_client", lambda: _Anthropic(tool_use=False))
    with pytest.raises(RuntimeError, match="tool_use"):
        proveedor.structured(REQ, Salida)


@pytest.mark.xfail(strict=True, reason="PR-A (spec §5.2, A6): seed_applied None, temperature aplicada, model_source=backend")
def test_anthropic_runmeta_v2_aplicado(monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = AnthropicProvider("claude-sonnet-5-5")
    monkeypatch.setattr(proveedor, "_client", lambda: _Anthropic())
    meta = proveedor.complete(REQ).meta
    assert (meta.seed_applied, meta.temperature_applied, meta.model_source) == (None, 0.3, "backend")
    _, meta_structured = proveedor.structured(REQ, Salida)
    assert meta_structured.schema_sha256  # el schema viaja como tool: su hash aparte (A7)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_providers_api.py -v`
Expected: los tests sin marcador PASS o FAIL según la plomería real; los tres `xfail` salen `XFAIL`. Si alguno sin marcador falla, la causa es una aserción del plan que no coincide con el código (p. ej. el texto del error): se ajusta al comportamiento real **sin tocar `revisia/`** y se anota en §19. Esta tarea es solo de tests: el «rojo» de TDD aquí es el `XFAIL` que PR-A convertirá en verde.

- [ ] **Step 3: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_providers_api.py tests/test_llm_registry.py -v`
Expected: PASS con 3 XFAIL.

- [ ] **Step 4: Commit**

```bash
git add tests/test_providers_api.py
git commit -m "test: proveedores API con clientes falsos; RunMeta v2 aplicado en xfail estricto para PR-A (M20)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 8: CI en matriz, `uv lock --check`, cobertura, `uv build`, humo de los SDK y `CONTRIBUTING.md`

**Files:**
- Modify: `.github/workflows/ci.yml` (reescritura completa).
- Modify: `CONTRIBUTING.md` (sección «Entorno de desarrollo» y «Antes de abrir un PR»).
- Test: `tests/test_ci_workflow.py` (nuevo).
- Test: `tests/test_sdk_superficie.py` (nuevo; lo corre el job `sdk-smoke`).

**Interfaces:**
- Produces (D25, §12):
  - `permissions: contents: read` a nivel de workflow; `on: push (main)` como hoy y `pull_request` **sin filtro de rama** (las PR de la ola van apiladas con base `feat/ola2-*`: con `branches: [main]` ninguna tendría CI hasta pasar su base a `main`; §19 fila 15, aprobada 2026-10-20); `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}`.
  - Acciones **solo** las dos ya fijadas por SHA en el fichero actual: `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5` (v4) y `astral-sh/setup-uv@e58605a9b6da7c637471fab8847a5e5a6b8df081` (v5), esta última con `enable-cache: true` y `version: "0.11.26"` (la versión local con la que se regeneró `uv.lock`; `uv lock --check` compara resoluciones y otra versión podría dar un lock distinto, Review Focus 2).
  - Job `lint` (`ubuntu-latest`, Python 3.13): `uv lock --check`, `uv sync --extra dev`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run black --check .`.
  - Job `test`: `strategy: {fail-fast: false, matrix: {os: [ubuntu-latest, windows-latest], python: ["3.11", "3.12", "3.13"]}}`, `runs-on: ${{ matrix.os }}`, `defaults.run.shell: bash`; pasos: checkout; setup-uv (`python-version: ${{ matrix.python }}`); **solo Ubuntu** (`if: runner.os == 'Linux'`): `sudo apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0`, `uv sync --extra dev --extra search --extra meta --extra pdf`, `uv run python -c "import weasyprint; print(weasyprint.__version__)"`; **solo Windows** (`if: runner.os == 'Windows'`): `uv sync --extra dev --extra search --extra meta`; ambos: `uv run python -c "import httpx, pypdf, scipy; print('extras ok')"` (sin esto, `importorskip` saltaría tests en silencio); tests **sin cobertura** (`if: "!(matrix.os == 'ubuntu-latest' && matrix.python == '3.13')"`): `uv run pytest -q -rs -n auto -m "not cronometrado" $BASETEMP` y `uv run pytest -q -rs -m cronometrado $BASETEMP`, donde en Windows `BASETEMP="--basetemp=${RUNNER_TEMP}/p"` (ruta corta; Review Focus 1) y en Linux vacío; tests **con cobertura** (`if: matrix.os == 'ubuntu-latest' && matrix.python == '3.13'`): `uv run pytest -q -rs -n auto -m "not cronometrado" --cov --cov-report=xml --cov-report=term --cov-fail-under=0` (la primera pasada no juzga: pytest-cov aplicaría el `fail_under` del `pyproject` a un subconjunto) y `uv run pytest -q -rs -m cronometrado --cov --cov-append --cov-report=xml --cov-report=term --cov-fail-under=90` (la cota se juzga sobre la suma de las dos pasadas).
  - Job `build` (`ubuntu-latest`): checkout; setup-uv; `uv build`; `uv run --no-project python -m zipfile -l dist/*.whl | grep -cE "revisia/(rob/tools/RoB2\.yml|prompts/screening/v1\.md)$"` debe dar `2`; `uv run --no-project python -m tarfile -l dist/*.tar.gz | grep -c "^runs/"` debe dar `0` (humo del empaquetado: los datos viajan, las corridas no).
  - Job `sdk-smoke` (`ubuntu-latest`, Python 3.13; §19 fila 6): checkout; setup-uv (misma versión y caché); `uv sync --extra dev --extra gemini --extra openai --extra anthropic`; `uv run pytest -q -rs tests/test_sdk_superficie.py` con `env: REVISIA_SDK_SMOKE: "1"`. Sin red ni claves reales: las claves son ficticias y ningún test llama a la API.
  - `tests/test_sdk_superficie.py`: `_sdk(nombre)` devuelve el módulo con `importlib.import_module`; si falta y `REVISIA_SDK_SMOKE` vale `"1"`, **falla** (`pytest.fail`: en el job de humo un SDK ausente es un error, no un salto); si no, `pytest.skip` con la razón (en la matriz se salta y `-rs` lo muestra). Tres tests, uno por SDK, que construyen el cliente **con el `_client()` del propio proveedor** (`monkeypatch.setenv` de `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ZAI_API_KEY`, `OPENROUTER_API_KEY` con `"clave-ficticia"`) y comprueban la superficie que imitan los clientes falsos de la Tarea 7: `GeminiProvider(...)._client().models.generate_content` invocable y `GeminiProvider(...)._config(REQ)` construye un `GenerateContentConfig` con `temperature` y `seed`; `OpenAIProvider`, `ZaiProvider`, `OpenRouterProvider` y `LocalOpenAIProvider`: `_client().chat.completions.create` y `_client().beta.chat.completions.parse` invocables; `AnthropicProvider(...)._client().messages.create` invocable. Comprobado el 2026-10-19 con las versiones de `uv.lock` (openai 2.44.0, anthropic 0.112.0, google-genai 2.10.0): toda esa superficie existe. Si una subida del lock la rompe, el fallo es del proveedor (territorio de PR-A, §15): se marca ese test `xfail(strict=True, reason=…)` con la causa y se abre la corrección, nunca se borra el test.
  - `CONTRIBUTING.md`: «Requiere **Python 3.11+**»; la lista «Antes de abrir un PR» añade `uv lock --check` y una línea de cobertura (`uv run pytest -q -n auto -m "not cronometrado" --cov --cov-report=term` → ≥ 90 %); un párrafo «El CI corre la suite en Ubuntu y Windows con 3.11, 3.12 y 3.13».

- [ ] **Step 1: Test que falla** — crear `tests/test_ci_workflow.py`:

```python
"""El workflow de CI cumple D25 (spec 2026-10-18 §12): matriz, permisos, lock, cobertura, acciones fijadas."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _pasos(job: str) -> list[dict]:
    return _workflow()["jobs"][job]["steps"]


def test_permisos_minimos_y_tres_jobs() -> None:
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    # PyYAML lee la clave `on` como True.
    disparadores = wf[True]
    assert disparadores["push"] == {"branches": ["main"]}
    assert not (disparadores["pull_request"] or {}).get("branches")  # PR apiladas también
    assert set(wf["jobs"]) == {"lint", "test", "build", "sdk-smoke"}
    assert wf["jobs"]["test"]["runs-on"] == "${{ matrix.os }}"


def test_matriz_seis_celdas_sin_fail_fast() -> None:
    estrategia = _workflow()["jobs"]["test"]["strategy"]
    assert estrategia["fail-fast"] is False
    assert estrategia["matrix"]["os"] == ["ubuntu-latest", "windows-latest"]
    assert estrategia["matrix"]["python"] == ["3.11", "3.12", "3.13"]


def test_acciones_fijadas_por_sha_y_uv_con_version() -> None:
    texto = CI.read_text(encoding="utf-8")
    usos = re.findall(r"uses:\s*(\S+)", texto)
    assert usos and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in usos)
    for paso in _pasos("test") + _pasos("lint") + _pasos("build") + _pasos("sdk-smoke"):
        if "setup-uv" in paso.get("uses", ""):
            assert paso["with"]["enable-cache"] is True and re.fullmatch(r"\d+\.\d+\.\d+", str(paso["with"]["version"]))


def test_lint_comprueba_el_lock_y_el_formato() -> None:
    runs = " ".join(p.get("run", "") for p in _pasos("lint"))
    for orden in ("uv lock --check", "ruff check .", "ruff format --check .", "black --check ."):
        assert orden in runs


def test_pdf_solo_en_ubuntu_y_cobertura_solo_en_ubuntu_313() -> None:
    for paso in _pasos("test"):
        run = paso.get("run", "")
        cond = paso.get("if", "")
        if "--extra pdf" in run or "apt-get" in run or "weasyprint" in run:
            assert "Linux" in cond, run
        if "--cov" in run:
            assert "ubuntu-latest" in cond and "3.13" in cond, run
        if "cronometrado" in run and "not cronometrado" not in run and "--cov" in run:
            assert "--cov-fail-under=90" in run and "--cov-append" in run
    runs = " ".join(p.get("run", "") for p in _pasos("test"))
    assert "import httpx, pypdf, scipy" in runs and "--basetemp" in runs


def test_build_hace_humo_del_empaquetado() -> None:
    runs = " ".join(p.get("run", "") for p in _pasos("build"))
    assert "uv build" in runs and "zipfile -l" in runs and "rob/tools/RoB2" in runs and "tarfile -l" in runs


def test_sdk_smoke_instala_los_tres_sdk_y_no_admite_saltos() -> None:
    job = _workflow()["jobs"]["sdk-smoke"]
    assert job["runs-on"] == "ubuntu-latest"
    runs = " ".join(p.get("run", "") for p in job["steps"])
    for extra in ("--extra gemini", "--extra openai", "--extra anthropic"):
        assert extra in runs
    paso = next(p for p in job["steps"] if "test_sdk_superficie" in p.get("run", ""))
    assert paso["env"]["REVISIA_SDK_SMOKE"] == "1"
```

Y crear `tests/test_sdk_superficie.py` según Interfaces (en local, sin los SDK, sus tres tests salen `SKIPPED`; con `REVISIA_SDK_SMOKE=1` y sin los SDK, `FAILED`).

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_ci_workflow.py -v`
Expected: FAIL (un solo job `test`, sin `permissions`, sin matriz, sin `sdk-smoke`).

- [ ] **Step 3: Implementar** `.github/workflows/ci.yml` según Interfaces (comentarios en español que expliquen cada decisión: por qué Pango solo en Ubuntu, por qué `--basetemp` en Windows, por qué la versión de uv fija) y los párrafos de `CONTRIBUTING.md`.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_ci_workflow.py -v && uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text(encoding='utf-8')); print('yaml ok')"`
Expected: PASS.

Run (simula localmente los comandos de las celdas, en Windows: esta máquina):

```bash
uv lock --check && uv run pytest -q -rs -n auto -m "not cronometrado" --basetemp="${TEMP}/p" && uv run pytest -q -rs -m cronometrado --basetemp="${TEMP}/p"
uv run pytest -q -n auto -m "not cronometrado" --cov --cov-report=term | tail -3
uv build && uv run --no-project python -m zipfile -l dist/*.whl | grep -cE "revisia/(rob/tools/RoB2\.yml|prompts/screening/v1\.md)$"
```

Expected: verde; cobertura total ≥ 90 % (hoy 95 %); `2`. Borrar `dist/`, `coverage.xml` y `.coverage*` (están en `.gitignore`).

Run (el job `sdk-smoke` en local, con los SDK del lock):

```bash
REVISIA_SDK_SMOKE=1 uv run --extra dev --extra gemini --extra openai --extra anthropic pytest -p no:cacheprovider -q -rs tests/test_sdk_superficie.py
```

Expected: 3 passed, ningún skip. Después `uv sync --extra dev --extra search --extra meta` para volver al entorno de trabajo.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml tests/test_ci_workflow.py tests/test_sdk_superficie.py CONTRIBUTING.md
git commit -m "ci: matriz ubuntu/windows x 3.11-3.13, uv lock --check, cobertura 90 en ubuntu/3.13, humo de uv build y de los SDK (D25, M22, M24)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Tarea 9: Integración de PR-H (controlador)

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`: `### Added` y `### Changed`).
- Modify: `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` (§19).

**Interfaces:** ninguna de código. Deja PR-H abierta sobre `feat/ola2-contratos` con el CI verde en las seis celdas.

- [ ] **Step 1: CHANGELOG.** En `### Added`:

```
- **CI multiplataforma** (D25): matriz `ubuntu-latest`/`windows-latest` × Python 3.11/3.12/3.13 con
  `uv lock --check`, cobertura con `pytest-cov` (≥ 90 % en Ubuntu/3.13), `permissions: contents: read`,
  extra `pdf` solo en Ubuntu y humo de `uv build`. Tests nuevos: entrypoints (`run_review`,
  `resume_review`, `agent_driver`, CLI `run` en subproceso y `gold-template`; A13), parsers de Crossref
  y Semantic Scholar con respuestas reales recortadas (M18), ruta Unpaywall → PDF/HTML con
  `httpx.MockTransport` (M19) y proveedores API con clientes falsos (M20). El test de pico de memoria
  precalienta los imports perezosos y los `cronometrado` toleran ×2 en Windows.
```

En `### Changed`: ``- `requires-python` baja a `>= 3.11` (amplía, no rompe); `ruff`/`black` apuntan a `py311`; `CONTRIBUTING.md` describe la matriz y los comandos nuevos.``

- [ ] **Step 2: §19 del spec.** Las filas 5–8 de §19 ya registran las decisiones del arquitecto del 2026-10-19 sobre los supuestos de este plan (cobertura 90 %, SDK fuera de la matriz con `sdk-smoke`, rc 3 en proceso, uv fijado): no se repiten. «§15, §16 CI en PR apiladas» (`pull_request` sin filtro de rama) ya está registrada como fila 15 de §19 (aprobada 2026-10-20); no se repite. Añadir **a continuación de la última fila existente**, con numeración consecutiva (plantilla; completar con lo que la revisión por tarea haya producido):

```
| n | §12 CI | `--basetemp=${RUNNER_TEMP}/p` en Windows; la primera pasada con cobertura lleva `--cov-fail-under=0` y la cota se juzga en la segunda (`--cov-append`) | Plan PR-H |
| n+1 | §12 M21 | `test_export_corrida_real` y `_REAL_RUN` se borran: sus aserciones del motor ya las cubren los tests sobre la fixture `run_dir`; un test fija que ningún test apunte a `runs/` | Plan PR-H |
| n+2 | §12 A13 | `new`, `export`, `check` y `audit` por `main([...])` ya estaban cubiertos (ficheros citados en la docstring de `test_entrypoints.py`); PR-H añade `gold-template`, `run` en subproceso (rc 0 y 2), `run_review`, `resume_review` y `agent_driver` | Plan PR-H |
```

- [ ] **Step 3: Commit de documentación.**

```bash
git add CHANGELOG.md docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md
git commit -m "docs: CHANGELOG y desviaciones (§19) de PR-H, CI multiplataforma y tests A13/M18-M20" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 4: Verificación completa local, en las tres versiones.**

```bash
for PY in 3.11 3.12 3.13; do
  uv run --python "$PY" --extra dev --extra search --extra meta pytest -p no:cacheprovider -q -n auto -m "not cronometrado" || exit 1
  uv run --python "$PY" --extra dev --extra search --extra meta pytest -p no:cacheprovider -q -m cronometrado || exit 1
done
uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check
```

Expected: verde en las tres; lint limpio. Anotar el recuento final `N₁` (desde `N₀` + los tests de las Tareas 2–8, con 3 XFAIL).

- [ ] **Step 5: Publicar y abrir la PR** (base `feat/ola2-contratos`, §15).

```bash
git push -u origin feat/ola2-ci-tests
gh pr create --base feat/ola2-contratos --head feat/ola2-ci-tests --title "Ola 2 · PR-H: CI multiplataforma y tests A13/M18/M19/M20" --body "$(cat <<'EOF'
## Qué cierra

M22 y M24 (CI sin matriz, sin `uv lock --check`, sin cobertura, sin `permissions`; `requires-python >= 3.13`), A13 (entrypoints sin tests), M18 (parsers Crossref/S2), M19 (ruta de texto completo), M20 (proveedores API) y el test de pico de memoria sensible a los extras (memoria de la Ola 1). Spec: `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` §12, D25.

## Qué cambia

- `pyproject.toml`: `requires-python >= 3.11`, `py311` en ruff/black, `pytest-cov` en `dev`, `[tool.coverage]` con `fail_under = 90`; `uv.lock` regenerado.
- `.github/workflows/ci.yml`: jobs `lint` (ruff, black, `uv lock --check`), `test` (matriz 2 × 3, `fail-fast: false`, caché de uv, Pango + extra `pdf` solo en Ubuntu, cobertura en Ubuntu/3.13, `--basetemp` corto en Windows), `build` (`uv build` + humo del wheel y del sdist) y `sdk-smoke` (los tres SDK reales, sin red: existe la superficie que imitan los clientes falsos). Acciones fijadas por SHA; uv fijado en 0.11.26.
- Tests: `test_entrypoints.py`, `test_search_backends_parsers.py` (+ `tests/fixtures/`), `test_fulltext_fallback.py`, `test_providers_api.py` (3 `xfail(strict)` que PR-A vuelve verdes), `test_pyproject.py`, `test_ci_workflow.py`, `test_sdk_superficie.py`; `_SCRIPT_MEDIDO` precalienta imports; `cota_de_tiempo` ×2 en Windows.
- `CONTRIBUTING.md`: Python 3.11+, `uv lock --check`, cobertura, matriz. `revisia/` no cambia.

## Verificación

- CI: seis celdas en verde; `lint`, `build` y `sdk-smoke` en verde; cobertura <X> % en Ubuntu/3.13 (cota 90).
- Local (Windows): suite en 3.11, 3.12 y 3.13; `ruff`, `black`, `uv lock --check` limpios. <N₁> recogidos (base PR-0: <N₀>).

## Pila

`main` ← PR-0 ← **PR-H** ← PR-A ← … (spec §15). No borrar la rama al mergear mientras PR-A la use como base.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR; el CI arranca.

- [ ] **Step 6: Criterio de cierre de la PR (§12, §16).** Esperar al CI (`gh pr checks <n> --watch`) y comprobar:

- `lint`: verde (`uv lock --check` incluido).
- `test`: **las seis celdas** verdes. Una celda Windows roja por tiempo o rutas no se apaga: se corrige (cota, `--basetemp`, un test concreto con `tmp_path` más corto) y se anota en §19; si una celda falla por un test que depende de la plataforma de forma legítima, se marca con `pytest.mark.skipif(sys.platform == …, reason=…)` **con la razón escrita**, nunca en bloque (riesgo 9).
- Cobertura en Ubuntu/3.13 ≥ 90 % (leer el `term` del log; anotar la cifra en el cuerpo de la PR).
- `build`: verde (los seis YAML de RoB y las plantillas viajan en el wheel; el sdist no lleva `runs/`).
- `sdk-smoke`: verde, 3 passed y ningún skip.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run black --check .`, `uv lock --check` limpios en local.

Expected: todo verde. Actualizar el cuerpo de la PR con `<X>`, `<N₀>` y `<N₁>` reales (`gh pr edit <n> --body-file …`). Sin merge: lo decide el arquitecto. A partir de aquí PR-A rebasa sobre `feat/ola2-ci-tests` antes de abrir su PR (§15).

---

## Self-review (hecha al escribir el plan)

- **Cobertura de §12, §15 (M18–M21) y D25:** `requires-python >= 3.11`, `py311`, `pytest-cov`, `[tool.coverage]` (T2); `permissions`, `lint` con `uv lock --check`, matriz 2 × 3 con `fail-fast: false`, caché, extras por plataforma, `-n auto` + `cronometrado`, cobertura en Ubuntu/3.13, `build` con `uv build` y `zipfile -l`, acciones por SHA (T8); A13 (T4); M18 (T5); M19 (T6); M20 (T7); M21, pico de memoria con imports precalentados y tolerancia ×2 en Windows (T3). Revisión independiente del 2026-10-18 incorporada (13 hallazgos: `union_mode`, validador de NOS y `test_hitl.py:224` eran de PR-0; M21, `ncbi._sleep`, la guarda de `date-parts` y `--cov-fail-under=0` en la primera pasada son de aquí). «Los tests que escriben rutas largas usan `tmp_path` corto» se resuelve de forma general con `--basetemp` en Windows (T8) y, si hace falta, caso a caso en el cierre (T9, Step 6).
- **Firmas verificadas contra `main` @ `c1af7c3` el 2026-10-18:** `run_review`/`resume_review` (`orchestration/flow.py`), `run_review_with_agent` (`agent_driver.py`), `_cmd_gold_template`/`_cmd_run`/`main` (`cli.py`), `crossref_search`/`semantic_scholar_search`/`_client` (`agents/search_backends.py`), `fetch_fulltext`/`_unpaywall_url`/`_resolve_pmcid` (`agents/fulltext.py`), `ncbi.IDCONV_URL`/`idconv` (`agents/ncbi.py`), `_client`/`_config`/`_messages` de los proveedores (`llm/providers/*.py`), `_SCRIPT_MEDIDO`/`_PICO_MAXIMO` (`tests/test_audit_hitl_registro.py:474-486`), los dos `timeout=10` (`tests/test_audit_hitl_registro.py:560`, `tests/test_audit_infra.py:449`), `check_databases` (una base `MANUAL_ONLY` con `imported/` no toca la red; `databases: []` sí buscaría en OpenAlex), `_FakeClient` de `tests/test_search_multibase.py:22-47`. `httpx` 0.28.1 trae `MockTransport`; el PDF mínimo de T6 se verificó con pypdf.
- **Consistencia entre tareas:** `protocolo_offline` (T4), `ClienteJSON` (T5) y `pdf_minimo` (T6) viven en `tests/fakes.py`, que PR-0 ya amplió; `cota_de_tiempo` (T3) en `tests/audit_fixtures.py`; T8 depende de T2 (lock) y T3 (cotas) para que las celdas Windows pasen.
- **Proporción:** los bloques de código son tests y el único algoritmo que la firma no determina (`pdf_minimo`); el YAML del CI se describe por pasos y condiciones, no se transcribe.
