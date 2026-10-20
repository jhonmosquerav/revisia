# Ola 2 · PR-I `feat/ola2-cierre` (Qdrant fuera, 0.9.0 y la documentación de la ola) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar el motor de la Ola 2 listo para publicarse como **0.9.0** (D7): quitar la promesa de Qdrant (D27, M16), fijar la versión en todos los sitios, cerrar el criterio de §16 por CLI y poner la documentación pública (README, AGENTS, arquitectura, benchmark, metodología, CHANGELOG, auditoría §11 y RELEASING) a la altura de lo que el motor hace de verdad.

**Architecture:** Dos tipos de trabajo. **Código** (Tareas 1–4, implementador + revisor por tarea, TDD): D27 en `pyproject.toml`, `uv.lock`, `.env.example` y `revisia/rag/`; la cita del doble `fake` en la síntesis (decisión de §16, condicionada al OK del arquitecto); un test de punta a punta que recorre el criterio de cierre de §16 con `revisia.cli.main`; y el bump a 0.9.0 con un test que fija que la versión coincide en todos los sitios. **Documentación** (Tareas 5–10, controlador-integrador): cada documento se reescribe contra un test de `tests/test_documentacion.py` que fija lo que tiene que decir (y lo que ya no puede decir), y el mapa de los checks del auditor en `docs/arquitectura.md` se contrasta con `revisia.audit.CHECKS`, no con una lista copiada. La Tarea 11 verifica §16 punto por punto, pone §19 al día y abre la PR.

**Tech Stack:** Python 3.11–3.13, Pydantic v2, PyYAML, pytest + pytest-xdist, ruff + black (línea 100), uv **0.11.26** (la del CI, §19 fila 8), gh.

**Spec:** `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`: §13 (esta PR), D4, D5, D7, D12, D17, D27, §14 (solo se documenta lo que sigue), §15 (topología y quién toca qué), §16 (criterio de cierre del motor), §18.4 (cambios incompatibles) y **§19 filas 1–10** (vinculantes; la 8 pide documentar en `RELEASING.md` la política de versión de uv). Estado de partida: los planes de PR-0, H, A, B, C, D, E, F y G en `docs/superpowers/plans/` (sus bloques Interfaces, «Estado en que X deja el pipeline» y sus tareas de integración, que ya editaron partes del README, de AGENTS y del CHANGELOG).

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes, documentación y commits **en español**, con el tono del repo (frases cortas, el porqué antes que el qué, decisiones citadas como «D27», «§16», hallazgos como «auditoría 2026-09-03, M16»).
- **§15 en esta PR:** solo el integrador toca `CHANGELOG.md`, `README.md`, `AGENTS.md`, `docs/auditoria/` y el spec. En PR-I ese es justo el trabajo, así que **las Tareas 5–11 son del controlador, que actúa como integrador**, y las ejecuta él mismo (sin subagente implementador; un revisor independiente sí revisa cada una). Los implementadores de las Tareas 1–4 **no tocan** esos ficheros.
- Versión: exactamente **`0.9.0`**. Fecha de `CHANGELOG.md` y de `CITATION.cff` (`date-released`): la del commit del bump (`date +%F`), la misma en los dos.
- `uv.lock` se regenera y se comprueba **solo** con la versión de uv del CI: `uvx uv@0.11.26 lock` y `uvx uv@0.11.26 lock --check` (§19 fila 8; otra versión podría dar un lock que el CI rechace). Antes de usarla, comprobar que `.github/workflows/ci.yml` sigue diciendo `version: "0.11.26"`; si dice otra, usar esa. En este plan, «`uv lock --check`» significa siempre `uvx uv@0.11.26 lock --check`.
- **CI en PR apiladas (fila I-17):** los Expected de «CI verde» dependen de la decisión del orquestador de que el plan de H quite el filtro de rama de `pull_request` (así una PR con base `feat/ola2-auditor` también corre el CI). Si el arquitecto la rechaza, la regla pasa a ser: suite local en 3.11, 3.12 y 3.13 (Tarea 11, Step 2) y, cuando le toque el merge, `gh pr edit <n> --base main` y cerrar y reabrir la PR para disparar el CI.
- Estilo: `ruff` (`E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100) limpios en cada commit; `from __future__ import annotations` en todo módulo nuevo, también en `tests/`. Los imports de `fakes`, `hitl_helpers` y `conftest` van en el bloque de terceros, tras `import pytest`.
- Tests offline y deterministas; ninguno invoca `claude`, APIs, la red ni WeasyPrint. El humo por subproceso de la Tarea 11 sí usa la red (OpenAlex, como el demo) y no es un test.
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX` y después `uv run pytest -p no:cacheprovider -m cronometrado`; lint, `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uvx uv@0.11.26 lock --check`.
- Commits pequeños, al menos uno por tarea, con prefijo convencional (`feat:`, `fix:`, `test:`, `docs:`, `chore:`) y terminados con `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- Grafía única en la documentación pública: «AMSTAR 2», «RoB 2», «QUADAS-2», «ROBINS-I» (como los nombres de las especificaciones de PR-0); «AMSTAR-2» desaparece del README, AGENTS y `docs/`.
- La documentación no cita **0,820** ni **I² 90,7 %** como evidencia en ningún sitio; solo `docs/benchmark-cribado.md` las nombra, dentro de su «Nota histórica» (§13, C3).
- No tocar `runs/` ni `protocols/<slug>/` distintos de `_TEMPLATE` (en particular, `protocols/prisma-ia-origen/` es del arquitecto: §14.2).
- Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base (§15). El merge, el tag `v0.9.0` y el release los decide el arquitecto: esta PR no los hace.

## Review Focus

Entradas que el spec implica y que ninguna tarea probaría sin estas líneas; cada una tiene su test en la tarea dueña:

1. **La versión desincronizada entre `pyproject.toml`, `revisia/__init__.py`, `CITATION.cff` y `uv.lock`** (el bump de un sitio y no de otro): `uv lock --check` rompe el CI y Zenodo archiva metadatos de otra versión. → Tarea 4 (`test_version_sincronizada_en_pyproject_paquete_citation_y_lock`) y Tarea 9 (el CHANGELOG tiene la sección de esa versión).
2. **Quien siga pidiendo el extra `rag`** (`uv sync --extra rag`) o importe `InMemoryVectorStore`: tiene que encontrarlo en «Cambios incompatibles», y en el árbol no puede quedar ningún resto que lo prometa (lock, `.env.example`, docstrings). → Tarea 1 (`test_sin_extra_rag_ni_qdrant_d27`, `test_rag_ya_no_promete_un_store_vectorial_d27`) y Tarea 9.
3. **El demo de siempre** (`revisia run examples/demo-mini-review --auto-approve`, `grounding: existence`) con el doble que ahora cita: no puede quedar en pausa por una cita marcada ni marcar nada. → Tarea 2 (`test_demo_existence_con_auto_approve_termina_sin_marcas`).
4. **Un prompt de síntesis sin bloque de estudios o con «(sin estudios incluidos)»**: el doble no cita nada ni falla. → Tarea 2 (`test_fake_sin_bloque_de_estudios_no_cita`, `test_fake_sin_incluidos_no_cita`).
5. **Un check que se añada al auditor después de esta PR** y no llegue a `docs/arquitectura.md`: el mapa se compara con `CHECKS` en un test, no con una lista copiada. → Tarea 6 (`test_arquitectura_mapea_cada_check_con_su_modulo`).

---

## Topología de ejecución

PR-I se desarrolla desde PR-G y su PR tiene base `feat/ola2-auditor` (§15). Un solo worktree, `C:\revisia-wt\i`, en secuencia.

| Tarea | Quién | Fichero(s) | Depende de |
|---|---|---|---|
| 0 | controlador | worktree, línea base, comprobaciones de partida | PR-G abierta |
| 1 | implementador | `pyproject.toml`, `uv.lock`, `.env.example`, `revisia/rag/{store,__init__,embed}.py`, `tests/test_rag.py`, `tests/test_pyproject.py` | 0 |
| 2 | implementador (puerta: OK del arquitecto) | `revisia/llm/providers/fake.py`, `tests/test_fake_provider.py` | 0 |
| 3 | implementador | `tests/test_cierre_motor.py` | 2 |
| 4 | implementador | `pyproject.toml`, `revisia/__init__.py`, `CITATION.cff`, `uv.lock`, `tests/test_pyproject.py` | 1 |
| 5 | controlador | `README.md`, `tests/test_documentacion.py` (nuevo) | 2, 4 |
| 6 | controlador | `AGENTS.md`, `docs/arquitectura.md`, `tests/test_documentacion.py` | 5 |
| 7 | controlador | `docs/benchmark-cribado.md`, `docs/metodologia/README.md`, `tests/test_documentacion.py` | 5 |
| 8 | controlador | `RELEASING.md`, `SECURITY.md`, `tests/test_documentacion.py` | 4 |
| 9 | controlador | `CHANGELOG.md`, `tests/test_documentacion.py` | 1, 2, 4 |
| 10 | controlador | `docs/auditoria/2026-09-03-auditoria-completa.md` (§11), `tests/test_documentacion.py` | 9 |
| 11 | controlador | spec (§19), verificación de §16, PR | todas |

**Ciclo por tarea (§16):** en las Tareas 1–4, implementador (subagente nuevo, TDD estricto: test rojo → código mínimo → verde → lint → commit) → revisor (subagente nuevo: primero cumplimiento del spec y de este plan, después calidad) → correcciones. En las 5–10, el controlador escribe el test y el documento y un revisor nuevo lee el documento contra el spec, el código y este plan. Las desviaciones descubiertas en revisión se corrigen y se anotan para §19 (Tarea 11), no se consultan, salvo que cambien una decisión D1–D6. **El merge lo decide el arquitecto.**

**Números de línea.** Los que cita este plan son de `main` @ `c1af7c3`. Las integraciones de PR-0, A, C, D y E ya editaron líneas del README, de AGENTS y del CHANGELOG, así que en el worktree de I pueden estar desplazadas: cada tarea documental da, junto a la línea, un patrón de `grep` para localizarla.

---

## Tarea 0: Worktree desde G, línea base y estado de partida (controlador)

**Files:** worktree `C:\revisia-wt\i`, rama `feat/ola2-cierre`.

**Interfaces:** ninguna de código.

- [ ] **Step 1: Crear la rama desde la punta de PR-G.**

```bash
git -C C:/revisia fetch origin
git -C C:/revisia worktree add C:/revisia-wt/i -b feat/ola2-cierre origin/feat/ola2-auditor
cd C:/revisia-wt/i
uv sync --extra dev --extra search --extra meta
```

Expected: `git log --oneline -1` muestra el último commit de `feat/ola2-auditor` (el de la Tarea G2.11).

- [ ] **Step 2: Suite en verde.**

```bash
uv run pytest -p no:cacheprovider --collect-only -q | tail -1
uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX
uv run pytest -p no:cacheprovider -m cronometrado
uv run ruff check . && uv run ruff format --check . && uv run black --check . && uvx uv@0.11.26 lock --check
```

Expected: verde, **0 XFAIL y 0 XPASS** (G2.10 los dejó en cero); lint limpio. Anotar el recuento `N₀` (va al cuerpo de la PR).

- [ ] **Step 3: Comprobar lo que dejaron las integraciones anteriores.** Si un Expected no se cumple, el arreglo va en la tarea documental de ese fichero (5–10) y se anota para §19.

```bash
grep -n "doble 20\|doble extracción 20\|+doble" README.md AGENTS.md docs/arquitectura.md
grep -n "Limitación conocida (Ola 2, M15)" README.md
grep -n "GRADE" README.md AGENTS.md
grep -n "grounding: agent" README.md docs/*.md protocols/_TEMPLATE/protocol.yml examples/demo-mini-review/protocol.yml
grep -n "^grounding:" examples/demo-mini-review/protocol.yml protocols/_TEMPLATE/protocol.yml
grep -n "auto_approve=True solo para una demo" README.md
grep -c "^| [0-9]* |" docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md
```

Expected:
- La primera orden solo encuentra `docs/arquitectura.md:20` (C quitó «doble 20 %» del README y de AGENTS; la arquitectura es de I).
- La segunda no imprime nada (C sustituyó la viñeta de M15 en su Tarea 13).
- `GRADE` solo aparece en frases que dicen que queda fuera (PR-0, Tarea 17, Step 0; E, Tarea E2.6).
- `grounding: agent` solo en las dos filas de la tabla de defaults del README (`README.md:475-476` en `c1af7c3`), que D dejó para I.
- `grounding` del demo: `existence` o ausente (default `existence`); el de `_TEMPLATE`: `existence` explícito (D, §19 n+14). G₂ **no** pasó el demo a `judge`: su fila n+19 sustituye a la n+14 de D y deja a PR-I el cierre por CLI. En G₂, `protocolo_auditoria` (y con ella `corrida`) ya está en `judge` con juez `fake-juez` y es APTA; la frontera D2 usa `corrida_existence`; el cierre completo en proceso es `corrida_ola2_completa` (`test_frontera_de_la_ola_2_completa_es_apta`, G2.10); y `test_pipeline_fake_con_humano_audita_sin_fail` (el demo) espera `fallos == {"grounding"}`. Comprobarlo: `grep -n "fake-juez\|corrida_existence" tests/conftest.py` y `grep -n 'fallos == {"grounding"}' tests/test_pipeline_fake.py` encuentran cada uno al menos una línea.
- El comentario de `auto_approve` del README existe (A, Tarea 13).
- Anotar el número de la última fila de §19 (`L`): las filas de PR-I se numeran desde `L + 1`.

- [ ] **Step 4: Estado de la comprobación real de PR-A.** PR-A pidió al arquitecto una llamada real con `ClaudeCodeProvider` (Tarea 13, Step 6).

```bash
gh pr list --state all --head feat/ola2-procedencia --json number,body --jq '.[0].body' | grep -n "<resultado>\|Llamada real"
```

Expected: la línea «Llamada real con `ClaudeCodeProvider`…» con un resultado, sin el marcador `<resultado>`. Si el marcador sigue, la comprobación queda **pendiente antes del tag `v0.9.0`**: se dice en el cuerpo de la PR de I (Tarea 11, Step 6), no bloquea esta PR.

Sin commit.

---

## Tarea 1: Qdrant desaparece como promesa (D27, M16)

**Files:**
- Modify: `pyproject.toml:45` (borrar la línea `rag = ["qdrant-client>=1.10"]`).
- Modify: `uv.lock` (regenerado: sin `qdrant-client` ni sus dependencias exclusivas, sin la marca `extra == 'rag'`; en `c1af7c3`, `uv.lock:2040-2054,2239,2273`).
- Modify: `.env.example:57-62` (borrar el bloque «Vector store para grounding/RAG» entero, comentario incluido).
- Modify: `revisia/rag/store.py`: docstring de módulo (`:1-6`) sin «store» ni Qdrant; borrar la clase `InMemoryVectorStore` (`:30-51`). `cosine` y `semantic_similarity` se quedan **sin cambios** (los usa el modo `embedder`, D27; `revisia/agents/verificador.py:22`).
- Modify: `revisia/rag/__init__.py`: docstring (`:1`) sin «store», import (`:6`) y `__all__` (`:12`) sin `InMemoryVectorStore`.
- Modify: `revisia/rag/embed.py:7` (docstring: «no exige Qdrant ni API» → «no exige servicios externos ni API»).
- Test: `tests/test_rag.py` (un test nuevo), `tests/test_pyproject.py` (de PR-H; un test nuevo).
- `rag/*` es de D (§15): PR-I solo toca docstrings, la clase muerta y el `__init__` (fila I-15).

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `revisia.rag.__all__ == ["Embedder", "GeminiEmbedder", "HashEmbedder", "cosine", "semantic_similarity"]`; el paquete deja de exportar `InMemoryVectorStore` (cambio incompatible, lo declara la Tarea 9).

- [ ] **Step 1: Localizar todos los usos** (antes de tocar nada).

```bash
grep -rni "InMemoryVectorStore\|qdrant\|extra rag" --include=*.py --include=*.toml --include=*.md --include=*.yml --include=*.lock --include=.env.example . | grep -v "^./docs/superpowers/\|^./docs/auditoria/\|^./CHANGELOG.md\|^./.venv/\|^./.claude/\|^./.superpowers/"
```

Expected: exactamente `pyproject.toml:45`, `.env.example:61-62` (y el comentario de `:57-60`), `revisia/rag/store.py:3,30`, `revisia/rag/__init__.py:6,12`, `revisia/rag/embed.py:7` y las líneas de `uv.lock`. Ningún test usa `InMemoryVectorStore` (comprobado en `c1af7c3`). Si aparece otro uso, se trata igual y se anota para §19.

- [ ] **Step 2: Tests que fallan.**

En `tests/test_rag.py`:

```python
def test_rag_ya_no_promete_un_store_vectorial_d27() -> None:
    import revisia.rag as rag
    import revisia.rag.embed as embed
    import revisia.rag.store as store

    assert not hasattr(rag, "InMemoryVectorStore")
    assert not hasattr(store, "InMemoryVectorStore")
    assert "InMemoryVectorStore" not in rag.__all__
    for modulo in (rag, store, embed):
        assert "qdrant" not in (modulo.__doc__ or "").lower(), modulo.__name__
    # El modo `embedder` sigue usando la similitud (D27).
    assert rag.semantic_similarity is store.semantic_similarity
```

En `tests/test_pyproject.py`:

```python
def test_sin_extra_rag_ni_qdrant_d27() -> None:
    extras = _pyproject()["project"]["optional-dependencies"]
    assert "rag" not in extras
    assert not any("qdrant" in dep for deps in extras.values() for dep in deps)
    assert "qdrant" not in (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert "QDRANT" not in (ROOT / ".env.example").read_text(encoding="utf-8")
```

- [ ] **Step 3: Run para verificar que fallan.**

Run: `uv run pytest -p no:cacheprovider tests/test_rag.py::test_rag_ya_no_promete_un_store_vectorial_d27 tests/test_pyproject.py::test_sin_extra_rag_ni_qdrant_d27 -v`
Expected: FAIL en los dos (`hasattr` verdadero; `"rag" in extras`).

- [ ] **Step 4: Implementar.** Borrar lo listado en Files. Docstring nueva de `store.py` (una línea y un párrafo): similitud coseno y semántica para el modo `embedder` del verificador (experimental, D2); sin store vectorial (D27, auditoría 2026-09-03, M16). Regenerar el lock con la versión del CI:

```bash
grep -n 'version: "' .github/workflows/ci.yml
uvx uv@0.11.26 lock
git diff --stat uv.lock
```

Expected: la versión del CI es `0.11.26`; el diff de `uv.lock` solo quita paquetes (`qdrant-client` y los que solo él traía) y las líneas del extra `rag`.

- [ ] **Step 5: Run para verificar que pasan, y la suite.**

Run: `uv run pytest -p no:cacheprovider tests/test_rag.py tests/test_pyproject.py -v && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -q && uvx uv@0.11.26 lock --check`
Expected: PASS; suite en verde; el lock limpio. Repetir el `grep` del Step 1: solo quedan menciones en `docs/superpowers/`, `docs/auditoria/` y el CHANGELOG histórico.

- [ ] **Step 6: Commit.**

```bash
git add pyproject.toml uv.lock .env.example revisia/rag/store.py revisia/rag/__init__.py revisia/rag/embed.py tests/test_rag.py tests/test_pyproject.py
git commit -m "chore!: Qdrant desaparece como promesa: sin extra rag, QDRANT_* ni InMemoryVectorStore (D27, M16)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 2: Cierre de §16 «con una adjudicación» por CLI (decisión del arquitecto)

### La decisión

§16 pide que el motor se cierre con una corrida **por CLI**, con el demo y el proveedor `fake`, que pase por «etiquetas, una edición de campo, una edición de dominio, un rescate con texto y **una adjudicación**». La adjudicación no es alcanzable hoy: `FakeProvider.complete` (`revisia/llm/providers/fake.py:82-89` en `c1af7c3`) devuelve un texto **sin** `[id]`, así que la síntesis del demo no tiene afirmaciones, el juez no se llama y no hay nada que marcar. D lo propuso como fila n+25 y G₂ lo dejó para I (fila **n+19** de G): G₂ prueba el cierre **en proceso** con `corrida_ola2_completa` (juez, edición de campo y de dominio, rescate con texto y adjudicación; `tests/test_pipeline_fake.py::test_frontera_de_la_ola_2_completa_es_apta`, G2.10), con `ScriptedProvider`, no por CLI.

| | (a) `FakeProvider.complete` cita un id incluido | (b) Reformular §16 |
|---|---|---|
| Qué cambia | El borrador del doble cita el primer estudio del bloque `estudios` del prompt. Con `grounding: judge` y un verificador `fake` (fail-closed, D §19 n+11) esa cita sale marcada y el gate final exige adjudicarla | §16 dice que la adjudicación se prueba en proceso (`corrida_ola2_completa`, G2.10); el criterio por CLI se queda sin ella |
| Coste | Un cambio de ~15 líneas en `fake.py` y sus tests; cambian las salidas del demo (la síntesis cita un estudio). **El `FakeProvider` real corre en muchas corridas de la suite**: todo `run_pipeline`/`correr_hasta`/`cli.main(["run"…])` que no sustituye `build_provider` (inventario de partida abajo). En `existence` la cita sale fundamentada, así que solo rompen los tests que fijan el texto o los hashes de la síntesis, `n_claims == 0` o el aviso «síntesis sin citas»; en `embedder`, la cita sale **marcada** (la similitud léxica entre el borrador del doble y el resumen queda bajo 0,12) y `--auto-approve` **pausa** en el gate final | Una edición del spec y una fila de §19 |
| Lo que gana un lector | Ve por CLI, con el demo, el camino entero de M5/D8: cita marcada → gate final forzado a humano → adjudicación con razón → auditor WARN | Nada visible: la adjudicación sigue probada, pero solo por quien lea los tests |

**El demo se queda en `existence` con las dos opciones** (fila I-8). Pasarlo a `judge` con un verificador `fake` rompería el quickstart: el juez `fake` es *fail-closed* (D §19 n+11), la cita saldría marcada y `--auto-approve` pausaría en el gate final (humano forzado, M5). Por eso la frontera de §16 con `judge` corre sobre una **copia** del demo (Tarea 3), y `test_pipeline_fake_con_humano_audita_sin_fail` sigue como lo deja G₂ (`fallos == {"grounding"}`: el demo es una demostración, no una revisión publicable).

**Recomendación: (a).** §16 es el criterio de cierre del **motor** y el demo es la puerta de entrada pública: si la única ruta que demuestra la adjudicación es un doble de tests, el criterio público queda más débil que el escrito, que es lo contrario del título de la ola. El coste es pequeño y acotado: con `grounding: existence` (el default del demo) una cita a un id del corpus sale fundamentada, así que el `--auto-approve` del quickstart no cambia de comportamiento (Review Focus 3). Precedente de alcance: D ya tocó `fake.py` (fail-closed en `structured`, §19 n+11), aunque `llm/providers/*` es de A (fila I-15). **El caso `embedder`:** `protocols/_TEMPLATE/protocol.yml:140` declara hoy `grounding: embedder` (D lo pasa a `existence` explícito, D §19 n+14; la Tarea 0 lo comprueba), y `tests/test_hitl_pipeline.py` corre al menos un caso en `embedder`: con (a), una corrida `embedder` + `fake` + `--auto-approve` pausa en el gate final por la cita marcada. Es honesto (`embedder` es experimental y no publicable, D2), pero cada test así se ajusta para adjudicar o pasa a `existence`, con su razón. **(b)** es la alternativa razonable si el arquitecto prefiere no cambiar ninguna salida del demo a estas alturas, o si el inventario del Step 0a resulta grande.

**Inventario de partida** (`c1af7c3`; ficheros con corridas que no sustituyen `build_provider` en todas sus llamadas, `grep -c "build_provider"` frente a llamadas de `run_pipeline`/`correr_hasta`/`cli.main`/`_correr`): `test_cli_reanudacion.py` (40 llamadas, 0 parches), `test_hitl_pipeline.py` (75/7), `test_reanudacion.py` (36/12), `test_errores_deterministas.py` (20/4), `test_audit_hitl_registro.py` (20/1), `test_pipeline_fake.py` (13/4), `test_snapshot.py` (7/0), `test_auditor_meta_y_estados.py` (5/1), `test_search_stage.py` (4/0), `test_audit_aritmetica_ola1.py` (2/1), `test_cli_errores.py` (1/0), `test_dedup.py` (1/0). Las pistas A–G añaden más; el inventario real lo da el Step 0a.

- [ ] **Step 0a: Medir el coste de (a) antes de la puerta** (implementador, en una rama desechable `tmp/pri-fake-cita` desde `feat/ola2-cierre`, sin commit en la rama de la PR): aplicar solo el cambio de `FakeProvider.complete` (Interfaces de abajo) y correr la suite.

```bash
git switch -c tmp/pri-fake-cita
# … cambio de `complete` …
uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -q -rf 2>&1 | tee ../i-inventario-fake.txt | tail -40
git restore . && git switch feat/ola2-cierre && git branch -D tmp/pri-fake-cita
```

Expected: la lista de tests que fallan con (a), cada uno con su causa en una línea (texto o hash de la síntesis fijado; `n_claims`; aviso «sin citas»; pausa por `embedder`). Esa lista se adjunta a la pregunta del Step 0.

- [ ] **Step 0: Puerta.** La opción la decide el arquitecto con el inventario del Step 0a delante (fila propuesta I-1 de §19, Tarea 11). Con **(a)**, seguir con los Steps 1–6. Con **(b)**, saltar al Step 7 y no tocar `fake.py`.

**Files (a):**
- Modify: `revisia/llm/providers/fake.py` (`complete`; función privada nueva `_first_included_id`).
- Test: `tests/test_fake_provider.py` (nuevo).

**Interfaces (a):**
- Consumes:
  - `synthesize_narrative(provider, *, question, included, extractions, temperature=0.2, seed=None) -> tuple[str, RunMeta]` (`revisia/agents/reporte.py`; desde D, los estudios van en `document_block("estudios", _studies_block(...))`: `<<<DOCUMENTO id=estudios>>>\n- [<id>] <título>\n…\n<<<FIN>>>`; plan D, Tarea 2);
  - `split_claims(narrative, corpus_ids) -> list[Claim]`, `Claim.citations: tuple[tuple[str, bool], ...]` (`revisia/agents/verificador.py`, plan D, Tarea 3);
  - `REGISTROS_AUDITORIA`, `busqueda_auditoria` (`tests/conftest.py`), `fetch_disponible` (`tests/fakes.py`), `run_pipeline` y `load_protocol`.
- Produces: `FakeProvider.complete(req) -> LLMResponse`:
  - si `req.prompt` contiene el bloque `<<<DOCUMENTO id=estudios>>>` … `<<<FIN>>>` y dentro hay una línea `- [<id>] ` (regex `^- \[([^\]\n]+)\] `, `re.MULTILINE`, solo en el cuerpo del bloque), el texto es exactamente `f"Borrador de síntesis narrativa (proveedor fake · sin contenido real) [{id}]. Configura un proveedor LLM real en protocol.yml para generar la síntesis."`;
  - si no, el texto de hoy, sin corchetes;
  - la meta se emite como hoy (desde A, por `emit_attempt`, plan A Tarea 2; `deterministic=True`, `response_sha256` del texto devuelto): no se toca.
  - El comentario de `fake.py:84-85` («SIN tokens "[...]"») se sustituye por el porqué de la cita: el doble cita un estudio incluido para que el demo con `grounding: judge` recorra la verificación y la adjudicación (§16); en `existence` la cita existe y no se marca.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_fake_provider.py`:

```python
"""El doble `fake` cita un estudio incluido en la síntesis (spec 2026-10-18 §16, decisión de PR-I)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import busqueda_auditoria
from fakes import fetch_disponible

from revisia.agents.reporte import synthesize_narrative
from revisia.agents.verificador import split_claims
from revisia.config import load_protocol
from revisia.llm.base import LLMRequest
from revisia.llm.providers.fake import FakeProvider
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext
from revisia.schemas.records import SearchRecord

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"
A = SearchRecord(record_id="10.1000/a", title="Estudio A", abstract="x", year=2024)
B = SearchRecord(record_id="10.1000/b", title="Estudio B", abstract="y", year=2025)


def _sintesis(included: list[SearchRecord]) -> str:
    texto, _ = synthesize_narrative(
        FakeProvider(), question="¿Sirve?", included=included, extractions={}
    )
    return texto


def test_fake_cita_el_primer_incluido_del_bloque_de_estudios() -> None:
    texto = _sintesis([A, B])
    assert "[10.1000/a]" in texto and "[10.1000/b]" not in texto
    claims = split_claims(texto, ["10.1000/a", "10.1000/b"])
    assert [c.citations for c in claims] == [(("10.1000/a", True),)]


def test_fake_sin_bloque_de_estudios_no_cita() -> None:
    resp = FakeProvider().complete(LLMRequest(prompt="- [10.1000/a] fuera del bloque"))
    assert "[" not in resp.text


def test_fake_sin_incluidos_no_cita() -> None:
    assert "[" not in _sintesis([])


def test_fake_complete_es_determinista() -> None:
    primero, segundo = (FakeProvider().complete(LLMRequest(prompt="p")) for _ in range(2))
    assert primero.text == segundo.text
    assert primero.meta.deterministic and primero.meta.response_sha256 == segundo.meta.response_sha256


def test_demo_existence_con_auto_approve_termina_sin_marcas(tmp_path: Path) -> None:
    # Review Focus 3: el quickstart del README no cambia de comportamiento.
    proto = tmp_path / "proto"
    shutil.copytree(DEMO, proto)
    protocol = load_protocol(proto)
    assert protocol.grounding == "existence"
    ctx = RunContext(protocol.slug, tmp_path / "runs", "T-FAKE-CITA")
    result = run_pipeline(
        protocol, proto, ctx, auto_approve=True,
        search_fn=busqueda_auditoria, fetch_fn=fetch_disponible,
    )
    assert result.status == "completed"
    informe = json.loads((ctx.run_dir / "06_synthesis" / "verification.json").read_text("utf-8"))
    assert informe["mode"] == "existence"
    assert informe["n_claims"] == 1 and informe["hallucination_flagged"] is False
```

(El código de test no pasa de 99 columnas: `black` lo parte.)

- [ ] **Step 2: Run para verificar que fallan.**

Run: `uv run pytest -p no:cacheprovider tests/test_fake_provider.py -v`
Expected: FAIL en `test_fake_cita_el_primer_incluido_del_bloque_de_estudios` y en `test_demo_existence…` (`n_claims == 0`); los otros tres pasan ya (fijan lo que no debe cambiar).

- [ ] **Step 3: Implementar** `FakeProvider.complete` y `_first_included_id(prompt: str) -> str | None` según Interfaces.

- [ ] **Step 4: Run del fichero y de la suite.**

Run: `uv run pytest -p no:cacheprovider tests/test_fake_provider.py -v && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX -q`
Expected: el fichero en verde. En la suite, los tests del inventario del Step 0a se ajustan **uno por uno**, con la expectativa nueva y la razón en el mensaje del commit; ninguno se borra. `test_pipeline_fake_con_humano_audita_sin_fail` (demo en `existence`, `ScriptedProvider`) **no** cambia: sigue con `fallos == {"grounding"}`. Si `AVISOS_DE_LA_DEMO` (`tests/test_pipeline_fake.py`) conserva la entrada `"grounding"  # la síntesis del doble no cita ningún estudio`, se quita (en `existence` `grounding` es FAIL, no WARN, y el comentario ya no es cierto); cualquier otro aviso que cambie por esta cita se ajusta con su comentario.

- [ ] **Step 5: Lint.**

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: limpio.

- [ ] **Step 6: Commit.**

```bash
git add revisia/llm/providers/fake.py tests/test_fake_provider.py tests
git commit -m "feat(fake): la síntesis del doble cita el primer estudio incluido, para cerrar §16 por CLI con una adjudicación" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7 (solo con (b)): Reformular §16 en el spec** (lo hace el controlador: el spec es del integrador). En el primer punto del criterio de cierre del motor (§16, «`revisia run` (`grounding: judge`, …)»), sustituir «, un rescate con texto y una adjudicación» por «y un rescate con texto (la adjudicación de una cita marcada se prueba en proceso con `corrida_ola2_completa`, `tests/test_pipeline_fake.py::test_frontera_de_la_ola_2_completa_es_apta`: el doble `fake` no cita)». La fila I-1 de §19 registra (b). Commit `docs(spec): §16 sin adjudicación por CLI (decisión del arquitecto)`.

---

## Tarea 3: El criterio de cierre de §16 como test de punta a punta por CLI

**Files:**
- Create: `tests/test_cierre_motor.py`.

**Interfaces:**
- Consumes:
  - `revisia.cli.main(argv: list[str]) -> int` (subcomandos `run`, `run --resume`, `audit`, `deposit`; `run` con `--runs-root`);
  - `revisia.agents.fulltext` (se sustituye su `fetch_fulltext` con `monkeypatch`: el pipeline lo llama por atributo de módulo, `pipeline.py:609` en `c1af7c3`);
  - `tests/hitl_helpers.py`: `responder_gate`, `leer_solicitud`, `aceptar_lo_obligatorio`, `editar_campo(study_id, key, value, reason, *, base)` (plan C, Tarea 9), `editar_dominio(study_id, target, judgment, reason, *, base)` (plan E, Tarea E2.4), `rescatar_con_texto(run_dir, record_id, nombre, contenido, *, reason, base)` (plan C, Tarea 10);
  - `tests/conftest.py`: `REGISTROS_AUDITORIA`, `GOLD_AUDITORIA`, `EDICION_DE_CAMPO` (plan C, Tarea 12), `EDICION_DE_DOMINIO` (plan E, Tarea E2.5);
  - `tests/fakes.py`: `fetch_no_disponible(ids)`;
  - `revisia.schemas.artifacts.RunInfo` (`run.json`: `status`, `stage`).
- Produces: tres tests que **son** el criterio de §16 en lo que no cubre ya otro test: el camino `judge` con humano hasta **APTA**, el mismo protocolo en `existence` → NO publicable solo por `grounding`, y la copia de depósito de la corrida APTA con el mismo veredicto. Los demás puntos de §16 ya tienen test (Tarea 11, Step 3).

**Cómo se monta la corrida (decisiones de este plan, fila I-2 de §19).** «Por CLI» es `revisia.cli.main([...])` en proceso, como `tests/test_cli_benchmark.py` (F): la búsqueda no toca la red porque el protocolo usa una base manual con corpus congelado, y el texto completo se sustituye con `monkeypatch`, porque un registro con DOI consultaría NCBI.
- Protocolo (`protocolo_cierre(tmp_path, grounding)`): copia de `examples/demo-mini-review` con `databases: ["Scopus"]`; `imported/corpus.records.json` = `REGISTROS_AUDITORIA` (`model_dump(mode="json")`, formato nativo, D23); `gold.yml` = `GOLD_AUDITORIA`; `grounding` dado; con `judge`, `llm.verificador = {provider: fake, model: fake-juez, temperature: 0.0, seed: 7}` (distinto `provider:model` que la síntesis `fake:fake-1`; fabricante desconocido, sin aviso de familia, D24). Todo el resto del demo (ensemble `fake-a`/`fake-b`, segundo extractor, RoB 2, `effects.yml`) igual. Proveedor `fake` real en todas las etapas: **sin** sustituir `build_provider`.
- Texto completo: `fetch_no_disponible(["10.1000/secundario"])`, envuelto para aceptar y descartar `**kwargs` (`mailto`, `max_chars`).
- La revisora, compuesta con `base=`: en T/A, `aceptar_lo_obligatorio`; en FT, etiqueta lo obligatorio y rescata `10.1000/secundario` con `rescues/secundario.txt` (un texto de tres párrafos que menciona «screening» y «workload») y razón «texto por préstamo interbibliotecario»; en extracción, `editar_campo(*EDICION_DE_CAMPO, base=aceptar_lo_obligatorio)`; en RoB, `editar_dominio(*EDICION_DE_DOMINIO, base=aceptar_lo_obligatorio)`; en `reporte`, `flags` con `{"verdict": "false_positive", "reason": "el juez fake rechaza por diseño (fail-closed)"}` para cada índice de `must_adjudicate`.
- Bucle: `cli.main(["run", proto, "--runs-root", raíz])` → la única carpeta bajo `raíz` es la corrida → mientras `run.json.status == "paused"`, responder el gate `run.json.stage` con `responder_gate(run_dir, stage, **(revisora(stage, leer_solicitud(run_dir, stage)) or {}))` y `cli.main(["run", "--resume", run_dir])`; máximo 8 vueltas.

- [ ] **Step 1: Escribir los ayudantes y los tests** — crear `tests/test_cierre_motor.py`. Los ayudantes van en código porque deciden cómo se monta el cierre; los nombres de `hitl_helpers` y `conftest` son los de los planes C y E (si el bloque Interfaces del plan dueño dice otro, manda ese y se anota).

```python
"""Criterio de cierre del motor 0.9.0 por CLI (spec 2026-10-18 §16; plan PR-I, Tarea 3)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from conftest import (
    EDICION_DE_CAMPO,
    EDICION_DE_DOMINIO,
    GOLD_AUDITORIA,
    REGISTROS_AUDITORIA,
)
from fakes import fetch_no_disponible
from hitl_helpers import (
    aceptar_lo_obligatorio,
    editar_campo,
    editar_dominio,
    leer_solicitud,
    rescatar_con_texto,
    responder_gate,
)

from revisia import cli
from revisia.agents import fulltext as fulltext_mod
from revisia.audit import run_audit

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"
GATES = ["screening_ta", "screening_ft", "extraccion", "rob", "reporte"]
NO_RECUPERADO = "10.1000/secundario"
TEXTO_RESCATE = (
    "Methods. Two reviewers screened 1 200 records.\n\n"
    "Results. LLM screening reached high recall and reduced workload.\n\n"
    "Discussion. Screening with LLMs needs a human gold standard."
).encode("utf-8")
RAZON_RESCATE = "texto por préstamo interbibliotecario"
RAZON_ADJUDICACION = "el juez fake rechaza por diseño (fail-closed): falso positivo del doble"

# Avisos de la corrida de cierre: cada uno con su porqué. Empieza vacío (Step 2: el rojo lista
# los que salen) y el revisor de la tarea aprueba cada entrada, una por una.
AVISOS_DEL_CIERRE: frozenset[str] = frozenset()


def protocolo_cierre(tmp_path: Path, grounding: str) -> Path:
    """El demo con corpus nativo congelado (D23), gold de dos clases y el modo dado."""
    destino = tmp_path / "proto" / DEMO.name
    shutil.copytree(DEMO, destino)
    ficha = destino / "protocol.yml"
    raw = yaml.safe_load(ficha.read_text(encoding="utf-8"))
    raw.update({"databases": ["Scopus"], "grounding": grounding})
    if grounding == "judge":
        raw["llm"]["verificador"] = {
            "provider": "fake", "model": "fake-juez", "temperature": 0.0, "seed": 7,
        }
    ficha.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    (destino / "imported").mkdir()
    corpus = [r.model_dump(mode="json") for r in REGISTROS_AUDITORIA]
    (destino / "imported" / "corpus.records.json").write_text(json.dumps(corpus), "utf-8")
    (destino / "gold.yml").write_text(yaml.safe_dump({"gold": GOLD_AUDITORIA}), "utf-8")
    return destino


def _sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un registro con DOI consultaría NCBI: el texto completo sale del doble."""
    fetch = fetch_no_disponible([NO_RECUPERADO])
    monkeypatch.setattr(fulltext_mod, "fetch_fulltext", lambda record, **_: fetch(record))


def revisora_cierre(
    run_dir: Path, *, adjudicar: bool = True
) -> Callable[[str, dict], dict | None]:
    """La revisora humana: etiqueta, rescata con texto, edita un campo y un dominio, adjudica."""
    rescate = rescatar_con_texto(
        run_dir, NO_RECUPERADO, "secundario.txt", TEXTO_RESCATE, reason=RAZON_RESCATE,
        base=aceptar_lo_obligatorio,
    )
    campo = editar_campo(*EDICION_DE_CAMPO, base=aceptar_lo_obligatorio)
    dominio = editar_dominio(*EDICION_DE_DOMINIO, base=aceptar_lo_obligatorio)

    def revisora(stage: str, solicitud: dict) -> dict | None:
        if stage == "screening_ft":
            return rescate(stage, solicitud)
        if stage == "extraccion":
            return campo(stage, solicitud)
        if stage == "rob":
            return dominio(stage, solicitud)
        if stage == "reporte" and adjudicar:
            flags = {
                str(i): {"verdict": "false_positive", "reason": RAZON_ADJUDICACION}
                for i in solicitud.get("must_adjudicate", [])
            }
            return {"flags": flags} if flags else None
        return aceptar_lo_obligatorio(stage, solicitud)

    return revisora


def correr_por_cli(
    proto: Path, raiz: Path, *, adjudicar: bool = True
) -> tuple[Path, list[int], list[str]]:
    """`revisia run` y `revisia run --resume` hasta terminar, respondiendo cada pausa."""
    codigos = [cli.main(["run", str(proto), "--runs-root", str(raiz)])]
    (run_dir,) = [p for p in raiz.iterdir() if p.is_dir()]
    revisora = revisora_cierre(run_dir, adjudicar=adjudicar)
    pausas: list[str] = []
    for _ in range(8):
        info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        if info["status"] != "paused":
            return run_dir, codigos, pausas
        stage = info["stage"]
        pausas.append(stage)
        extra = revisora(stage, leer_solicitud(run_dir, stage)) or {}
        responder_gate(run_dir, stage, **extra)
        codigos.append(cli.main(["run", "--resume", str(run_dir)]))
    raise AssertionError(f"la corrida no terminó en 8 vueltas: {pausas}")


def _ledger(run_dir: Path) -> list[dict]:
    lineas = (run_dir / "decisions_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(linea) for linea in lineas if linea.strip()]


def _estados(informe) -> dict[str, str]:
    return {c.check_id: c.status for c in informe.checks}


def test_cierre_judge_con_humano_por_cli_es_apto(tmp_path, monkeypatch, capsys) -> None:
    _sin_red(monkeypatch)
    proto = protocolo_cierre(tmp_path, "judge")
    run_dir, codigos, pausas = correr_por_cli(proto, tmp_path / "runs")
    assert codigos == [0] * len(codigos)
    assert pausas == GATES  # pausa en los cinco gates, en orden
    acciones = {(e["action"], e["stage"]) for e in _ledger(run_dir)}
    assert {("edit_field", "extraccion"), ("edit_domain", "rob"),
            ("rescue_text", "screening_ft"), ("flag_review", "reporte")} <= acciones
    verificacion = json.loads((run_dir / "06_synthesis" / "verification.json").read_text("utf-8"))
    assert verificacion["mode"] == "judge" and verificacion["hallucination_flagged"] is True
    capsys.readouterr()
    assert cli.main(["audit", str(run_dir)]) == 0
    assert "APTA para preparar publicación" in capsys.readouterr().out
    informe = run_audit(run_dir)
    assert [c.check_id for c in informe.checks if c.status == "FAIL"] == []
    avisos = {c.check_id for c in informe.checks if c.status == "WARN"}
    assert avisos <= AVISOS_DEL_CIERRE, sorted(avisos - AVISOS_DEL_CIERRE)


def test_cierre_existence_por_cli_no_es_publicable_solo_por_grounding(
    tmp_path, monkeypatch
) -> None:
    _sin_red(monkeypatch)
    run_dir, _, pausas = correr_por_cli(protocolo_cierre(tmp_path, "existence"), tmp_path / "runs")
    assert pausas == GATES
    assert cli.main(["audit", str(run_dir)]) == 1
    assert {k for k, v in _estados(run_audit(run_dir)).items() if v == "FAIL"} == {"grounding"}


def test_cierre_deposito_de_la_corrida_apta_audita_apto(tmp_path, monkeypatch) -> None:
    _sin_red(monkeypatch)
    run_dir, _, _ = correr_por_cli(protocolo_cierre(tmp_path, "judge"), tmp_path / "runs")
    destino = tmp_path / "deposito" / run_dir.name
    assert cli.main(["deposit", str(run_dir), "--out", str(destino)]) == 0
    textos = destino / "04_fulltext" / "texts"
    assert not textos.exists() or not any(textos.iterdir())
    assert not (destino / "screening_ft" / "rescues").exists()  # D17: retenido
    assert (destino / "deposit.json").is_file()
    assert cli.main(["audit", str(destino)]) == 0
    assert _estados(run_audit(destino)) == _estados(run_audit(run_dir))
```

- La acción del ledger de la adjudicación es `flag_review` (`LEDGER_ACTIONS`, `revisia/provenance/ledger.py:30-31`), con `stage: "reporte"`. Si el ledger de la Ola 2 nombra el campo de etapa de otra forma, manda `DecisionEntry` (PR-0, Tarea 6).
- `AVISOS_DEL_CIERRE` se rellena en el Step 3 con **un comentario por aviso** que diga de dónde sale (proveedor `fake`, gold sin especificidad porque el doble lo incluye todo, cita adjudicada, búsqueda manual…), como `AVISOS_DE_LA_DEMO` en `tests/test_pipeline_fake.py`. **El revisor de la tarea aprueba cada entrada, una por una**; un aviso que no se explique por cómo se monta el cierre es un desacuerdo entre pipeline y auditor y se investiga (superpowers:systematic-debugging), no se añade.
- Con **(b)** (Tarea 2, Step 7): `correr_por_cli(..., adjudicar=False)`, sin `("flag_review", "reporte")` en el conjunto esperado y con `hallucination_flagged is False`; el resto igual.

- [ ] **Step 2: Run para ver el rojo.**

Run: `uv run pytest -p no:cacheprovider tests/test_cierre_motor.py -v`
Expected: `test_cierre_judge_con_humano_por_cli_es_apto` FALLA **por comportamiento** en la última aserción, con la lista ordenada de los WARN reales (`AVISOS_DEL_CIERRE` está vacío). Los otros dos pasan ya: fijan lo que G y D dejaron. Si cualquiera falla antes (rc ≠ 0, una pausa de más o de menos, una acción ausente, un FAIL), se para: es un hallazgo de cierre, se corrige en la pista dueña del código con su propio test rojo y se anota en §19.

- [ ] **Step 3: Fijar `AVISOS_DEL_CIERRE`** con los avisos del Step 2, cada uno con su comentario; revisión aviso por aviso.

- [ ] **Step 4: Run para verificar que pasan, y la suite.**

Run: `uv run pytest -p no:cacheprovider tests/test_cierre_motor.py -v && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX -q`
Expected: PASS; suite en verde, 0 XFAIL.
- [ ] **Step 5: Lint y commit.**

```bash
uv run ruff check . && uv run ruff format --check . && uv run black --check .
git add tests/test_cierre_motor.py
git commit -m "test: criterio de cierre del motor (§16) de punta a punta por CLI: judge APTA, existence no publicable, depósito igual" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 4: Versión 0.9.0 en todos los sitios (D7)

**Files:**
- Modify: `pyproject.toml:7` (`version = "0.9.0"`).
- Modify: `revisia/__init__.py:12` (`__version__ = "0.9.0"`).
- Modify: `CITATION.cff:22-23` (`version: "0.9.0"`, `date-released: "<fecha del commit>"`). El bloque `identifiers` no se toca aquí: el DOI de la 0.9.0 lo emite Zenodo tras el release (`RELEASING.md`, Tarea 8).
- Modify: `uv.lock` (la línea `version` del paquete `revisia`, `uv.lock:2190` en `c1af7c3`; la reescribe `uvx uv@0.11.26 lock`).
- Test: `tests/test_pyproject.py` (un test nuevo).

**Interfaces:**
- Produces: `revisia.__version__ == "0.9.0"`; `revisia --version` imprime `revisia 0.9.0`; `run.json.environment.engine_version` de toda corrida nueva vale `0.9.0` (A lo toma de `revisia.__version__`).

«Los tres sitios» de §13 son los de `RELEASING.md:8-12`; `uv.lock` es el cuarto (sin él, `uv lock --check` falla en el CI). La línea de «Cómo citar» del README (`README.md:538`, `v0.8.0`) es del integrador: Tarea 5.

- [ ] **Step 1: Test que falla** — en `tests/test_pyproject.py` (añadir `import re`, `import yaml` y `import revisia` en sus bloques):

```python
def test_version_sincronizada_en_pyproject_paquete_citation_y_lock() -> None:
    version = _pyproject()["project"]["version"]
    assert revisia.__version__ == version
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["version"] == version
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(citation["date-released"]))
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    assert f'name = "revisia"\nversion = "{version}"' in lock
```

El test fija la **igualdad**, no el número: sirve para todo release futuro.

- [ ] **Step 2: Run para verificar que pasa hoy (0.8.0 en los cuatro) y que falla con un bump parcial.**

Run: `uv run pytest -p no:cacheprovider tests/test_pyproject.py::test_version_sincronizada_en_pyproject_paquete_citation_y_lock -v`
Expected: PASS con 0.8.0. Cambiar solo `pyproject.toml` a `0.9.0` y repetir: FAIL (`revisia.__version__ == version`). Es el rojo de esta tarea.

- [ ] **Step 3: Completar el bump** en `revisia/__init__.py` y `CITATION.cff`, y regenerar el lock:

```bash
uvx uv@0.11.26 lock
git diff uv.lock
```

Expected: el diff de `uv.lock` es solo `version = "0.8.0"` → `"0.9.0"` en el paquete `revisia`.

- [ ] **Step 4: Run.**

Run: `uv run pytest -p no:cacheprovider tests/test_pyproject.py tests/test_snapshot.py -v && uv run revisia --version && uvx uv@0.11.26 lock --check`
Expected: PASS; `revisia 0.9.0`; lock limpio.

- [ ] **Step 5: Commit.**

```bash
git add pyproject.toml revisia/__init__.py CITATION.cff uv.lock tests/test_pyproject.py
git commit -m "chore(release): 0.9.0 en pyproject, paquete, CITATION y lock, con test de sincronía (D7)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 5: README (controlador-integrador)

**Files:**
- Modify: `README.md`.
- Create: `tests/test_documentacion.py` (lo amplían las Tareas 6–10).

**Interfaces:**
- Consumes: el comportamiento real de 0.9.0 (planes A–G e I); `revisia.__version__`.
- Produces: `tests/test_documentacion.py` con `ROOT = Path(__file__).resolve().parent.parent` y `_texto(ruta: str) -> str` (UTF-8), que usan las Tareas 6–10.

- [ ] **Step 1: Test que falla** — crear `tests/test_documentacion.py`:

```python
"""Lo que la documentación pública afirma sobre el motor 0.9.0 (spec 2026-10-18 §13)."""

from __future__ import annotations

from pathlib import Path

import revisia

ROOT = Path(__file__).resolve().parent.parent


def _texto(ruta: str) -> str:
    return (ROOT / ruta).read_text(encoding="utf-8")


def test_readme_dice_lo_que_hace_0_9() -> None:
    readme = _texto("README.md")
    for afirmacion in (
        "grounding: judge", "llm.verificador", "`existence`", "`embedder`",
        "revisia benchmark", "revisia benchmark-report", "revisia deposit",
        "concordancia IA–IA", "edit_field", "edit_domain", "text_file",
        "AMSTAR 2", "QUADAS-2", "seed_applied", "environment",
        "Ubuntu y Windows", "actions/workflows/ci.yml/badge.svg", "python-3.11%2B",
        f"(v{revisia.__version__})",
    ):
        assert afirmacion in readme, afirmacion


def test_readme_ya_no_afirma_lo_que_dejo_de_ser_cierto() -> None:
    readme = _texto("README.md")
    for obsoleto in (
        "doble 20", "+doble", "Limitación conocida (Ola 2, M15)", "grounding: agent",
        "'embedder' (default", "tests-317", "python-3.13%2B", "Python 3.13+",
        "0,820", "90,7", "RoB2/ROBINS-I/GRADE", "AMSTAR-2", "no quedan en `llm_calls.jsonl`",
        "`records` ahí es un",
    ):
        assert obsoleto not in readme, obsoleto
```

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py -v`
Expected: FAIL en los dos (faltan `revisia benchmark`, el badge…; sobran `grounding: agent`, `tests-317`…).

- [ ] **Step 2: Reescribir el README** según esta tabla. La columna «Contenido» decide qué tiene que decir cada pasaje; la prosa es del integrador, con el tono del README. «Patrón» localiza la línea si se desplazó.

| Línea (`c1af7c3`) | Patrón | Contenido |
|---|---|---|
| 13 | `python-3.13` | Badge `python-3.11%2B` («Python 3.11+»). |
| 14 | `tests-317` | Badge del **estado del CI**, no un recuento fijo (fila I-3): `<a href="https://github.com/jhonmosquerav/revisia/actions/workflows/ci.yml"><img src="https://github.com/jhonmosquerav/revisia/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>`. |
| 39-44 | `→ verificador` | Diagrama del flujo: el verificador va **solo** tras la síntesis (es la única etapa que cita, AGENTS «Las auditorías» 1); extracción «(corrección por campo; concordancia IA–IA 20 %)» (ya de C); «riesgo de sesgo por herramienta»; «meta-análisis por desenlace (si hay efectos)». |
| 47-48 | `` `verificador` = `` | Qué hace el verificador: parte la síntesis en afirmaciones; por cada par (afirmación, cita) busca las cifras en la fuente completa sin IA y, en `judge`, pregunta a un juez de **otro modelo** (`llm.verificador`); `existence` (el default) solo comprueba que el id cite un estudio del corpus y **no es publicable**; `embedder` es experimental. |
| 54-55 | `I²/τ², Egger)` | Meta-análisis por desenlace, solo con los efectos de los incluidos (los demás a `08_meta/excluded_effects.json`), intervalo de predicción (k ≥ 3), Egger y funnel solo con k ≥ 10, unidad de análisis vigilada. |
| 65 | `risk_of_bias.md` | Tabla de riesgo de sesgo **por herramienta** (RoB 2, ROBINS-I, NOS cohortes y casos-controles, AMSTAR 2, QUADAS-2), con su escala y su regla de agregación oficial. El nombre del fichero no cambia (E, §19 m+8). |
| 74-75 | `manifiesto reproducible` | Manifiesto con `environment` (motor, Python, plataforma, commit, paquetes, hashes de plantillas y de especificaciones de RoB) y cada intento de llamada con lo que **viajó** (`seed_applied`, `temperature_applied`), no solo lo pedido. |
| 77-82 | `Texto completo: PRISMA estricto` | Añadir: el texto se lee hasta `fulltext.max_chars` (120 000) y el recorte se declara; un no recuperado se puede rescatar **con su texto** (`text_file: rescues/<fichero>` en `screening_ft/decision.yml`). |
| 84-86 | `Las corridas no se versionan` | Para depositar: `revisia deposit runs/<corrida> --out <carpeta>` copia la corrida **sin** los textos completos (copyright) y con sus hashes en `deposit.json`; la copia audita con el mismo veredicto (D17). |
| 90-104 | `audita la corrida` | Lista de lo que comprueba: añadir procedencia por intento, entorno, extracción, RoB, meta-análisis, verificación por juez y depósito. Lista de «no es publicable»: añadir `grounding: existence`/`embedder` (D2), una corrida anterior a 0.9 (sin `environment`, D12) y una corrida de benchmark (D23). |
| 117 | `**Reproducible**` | Por intento: lo aplicado y lo pedido, hash del texto enviado, plantilla con versión, versión del SDK o del CLI; `environment` en `run.json` y en el manifiesto. |
| 118 | `doble revisor` | Sustituir «doble revisor» por: corrección humana por campo y por dominio; verificación por juez de otro modelo; concordancia IA–IA como señal, no como doble extracción (D4). |
| 123 | `Python 3.13+` | «requiere Python 3.11+ y uv». |
| 196-198 | `**Extracción y RoB** se aprueban por etapa` | Sustituir por la corrección por campo y por dominio, con un ejemplo YAML de cada una: `records: {"<study_id>": {fields: {<clave>: {value: …, reason: …}}}}` (extracción, `edit_field`) y `records: {"<study_id>": {domains: {D2: {judgment: high, reason: …}}, overall: {judgment: …, reason: …}}}` (RoB, `edit_domain`); el global que cuenta lo calcula la regla de la herramienta sobre los juicios finales; un estudio en el que la IA falló llega con todas sus claves (dominios) obligatorias. |
| 226-235 | `no quedan en \`llm_calls.jsonl\`` | Cada intento de llamada queda en `llm_calls.jsonl` en el momento en que ocurre, también los fallidos (D14); reanudar solo repite las del registro en curso. |
| 251-255 | — | Ya sustituida por C (D9: un fallo determinista llega al gate como pendiente de humano). Solo comprobar. |
| 282-302 | `## Estado` | Añadir: verificación por juez, RoB por herramienta, extracción sobre texto completo con corrección por campo, `revisia benchmark`/`benchmark-report`, `revisia deposit`, CI en Ubuntu y Windows × Python 3.11/3.12/3.13 con cobertura ≥ 90 %. «doble extracción con kappa» ya lo cambió C. |
| 304-324 | `Auditoría abierta (2026-09-03)` | La sección **se queda** hasta 1.0.0 (§14.4). Actualizar el final: la Ola 2 cierra el motor en 0.9.0 (verificador por juez, procedencia aplicada, RoB oficial, meta-análisis ligado a los incluidos, benchmark por comando); **pendiente: re-auditoría y corrida real (D1)**; hasta entonces el veredicto de la auditoría sigue vigente. Remitir a §11 del informe. |
| 370-373 | `inyectando el JSON Schema` | Con un CLI que lo anuncia, el schema viaja con `--json-schema` (con un shim `.cmd`, en el texto: §19 de A); versión mínima del CLI (`MIN_CLI_VERSION`, error de preflight por debajo); entorno del subproceso por allowlist; `seed_applied`/`temperature_applied` quedan `null` porque el CLI no los admite. |
| 394-407 | `run_review_with_agent` | Ya de A. Comprobar que dice `auto_approve=False` por defecto y `AgentReply`. |
| 409-426 | `## Panel multi-modelo` | Añadir `revisia benchmark <protocolo> --panel panel.yml` y `revisia benchmark-report <carpeta>…`, con remisión a `docs/benchmark-cribado.md`. |
| 428-438 | `**Grounding por agente.**` | Título y párrafo nuevos: «Verificador por juez». Tabla de los tres modos (`existence`: default, barato, no publicable; `judge`: juez de otro modelo, el único publicable; `embedder`: experimental). El YAML de ejemplo de D (`grounding: judge` + `llm.verificador`) se conserva. Mismo fabricante que la síntesis → aviso (D24). |
| 475-476 | `grounding: agent` | `grounding: judge` con `llm.verificador` de otro fabricante (verificación cross-lingual y de otro modelo). |
| 477 | `Sin metaanálisis` | `effects.yml` por desenlace (`outcome`), ligado a los incluidos, PI, Egger con k ≥ 10, unidad de análisis (`multiple_per_study`). |
| 496-516 | `## Estructura` | Añadir `rob/` (especificaciones oficiales y reglas de agregación), `text/` (cita literal y documentos delimitados), `ingest/` (DOI e importación manual), `benchmark/` (`revisia benchmark`) y `scripts/` (sonda del CLI `claude`). `rag/`: «similitud para el modo `embedder` y juez del verificador». |
| 522 | `RoB2/ROBINS-I` | Ya sin GRADE (PR-0, que escribió `RoB2/ROBINS-I/NOS/AMSTAR-2/QUADAS-2`). Unificar la grafía: `RoB 2/ROBINS-I/NOS/AMSTAR 2/QUADAS-2`. |
| 538 | `(v0.8.0)` | `(v0.9.0)`. |
| 541-543 | `DOI de versión` | Añadir el DOI de la v0.8.0 **solo** si ya está en `CITATION.cff` (`grep "v0.8.0" CITATION.cff`); el de la 0.9.0 llega tras el release. |

- [ ] **Step 3: Run.**

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py -v && grep -n "0,820\|90,7\|Qdrant" README.md`
Expected: PASS; el `grep` no imprime nada.

- [ ] **Step 4: Revisión independiente** (subagente nuevo): lee el README entero contra el spec (D2, D4, D5, D9, D12, D14, D16, D17, D20–D23, D27) y los planes, y comprueba cada afirmación nueva contra el código del worktree (`grep` de cada comando, opción y fichero que nombra). Correcciones antes del commit.

- [ ] **Step 5: Commit.**

```bash
git add README.md tests/test_documentacion.py
git commit -m "docs(readme): verificador por juez, procedencia aplicada, RoB por herramienta, benchmark, depósito y CI multiplataforma (0.9.0)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 6: AGENTS y `docs/arquitectura.md`, con el mapa del auditor (controlador-integrador)

**Files:**
- Modify: `AGENTS.md:26-69` (tabla del equipo y «Las auditorías»).
- Modify: `docs/arquitectura.md` (diagrama, contratos, «Dónde está cada cosa» y sección nueva «El auditor por dentro»).
- Modify: `tests/test_documentacion.py`.

**Interfaces:**
- Consumes: `revisia.audit.CHECKS` (`CheckSpec(check_id, item_ref, stage, fn)`, `revisia/audit/__init__.py:70` en `c1af7c3`; al final de G₂, **26** filas, ver la nota del mapa).

- [ ] **Step 1: Tests que fallan.**

```python
from revisia.audit import CHECKS  # en el bloque de imports


def test_agents_describe_el_equipo_de_la_ola_2() -> None:
    agents = _texto("AGENTS.md")
    fila = next(x for x in agents.splitlines() if x.startswith("| `verificador` |"))
    assert "juez" in fila and "llm.verificador" in fila and "judge" in fila
    for afirmacion in ("edit_field", "edit_domain", "concordancia IA–IA", "revisia benchmark",
                       "revisia deposit", "environment", "existence"):
        assert afirmacion in agents, afirmacion
    for obsoleto in ("doble extracción 20", "/GRADE)", "AMSTAR-2"):
        assert obsoleto not in agents, obsoleto


def test_arquitectura_mapea_cada_check_con_su_modulo() -> None:
    texto = _texto("docs/arquitectura.md")
    filas = [x for x in texto.splitlines() if x.startswith("| ") and "`check" not in x]
    for orden, spec in enumerate(CHECKS, start=1):
        modulo = spec.fn.__module__.rsplit(".", 1)[-1]
        fila = next((x for x in filas if f"| `{spec.check_id}` |" in x), None)
        assert fila is not None, spec.check_id
        assert fila.startswith(f"| {orden} |") and f"`{modulo}`" in fila, fila
    assert "+doble" not in texto and "doble 20" not in texto
    assert "revisia deposit" in texto and "revisia benchmark" in texto
```

(El formato lo fija el controlador, que escribe el test y el documento: filas `| orden | \`id\` | ítem | etapa | \`módulo\` | qué comprueba |` bajo la cabecera `| # | Check | Ítem | Etapa | Módulo | Qué comprueba |`. El filtro `"\`check" not in x` del test solo excluye líneas con un nombre de función `check_…`; si el controlador cambia el formato, ajusta el filtro en el mismo commit.)

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py -k "agents or arquitectura" -v`
Expected: FAIL en los dos nuevos; `test_arquitectura_cita_el_paquete_del_auditor` (`tests/test_entregable_honesto.py:250`) sigue en verde.

- [ ] **Step 2: AGENTS.md.** Filas de la tabla del equipo (`c1af7c3`; C, D y E ya cambiaron `extraccion`, `verificador` y `rob`: se comprueban y se completan):

| Fila | Cambio |
|---|---|
| `screening_ta` (31) | Verificación: + «un fallo determinista de la IA lo lleva al gate como pendiente de humano (D9)». |
| `screening_ft` (32) | Etapa: + «rescate con el texto que aporta el humano (`text_file`)». |
| `extraccion` (33) | De C: comprobar «concordancia IA–IA del 20 % como señal» y `edit_field`. |
| `rob` (34) | De E: comprobar las seis especificaciones y `edit_domain`; que diga «GRADE queda fuera: califica certeza por desenlace (D5)». |
| `meta-analisis` (35) | Por desenlace, solo efectos de los incluidos (`excluded_effects.json`), PI, Egger con k ≥ 10, unidad de análisis (`multiple_per_study`). |
| `verificador` (37) | Tipo: «🤖 LLM con juez propio (`llm.verificador` ≠ `sintesis`) · ⚙️ cifras y `existence`». Etapa: la de D. Verificación: la de D + «solo `judge` es publicable (D2)». |
| `auditor` (39) | + entorno (D12), procedencia por intento, extracción, RoB, meta-análisis, verificación por juez, depósito (D17) y benchmark (D23); módulos de ≤ 900 líneas (D26). |

Tras la tabla, un párrafo «Fuera del pipeline»: `revisia benchmark` (corridas `kind: benchmark` que se detienen tras T/A, sin gates ni entregable: nunca son revisiones, D23) y `revisia deposit` (copia de depósito sin textos completos, D17). En «Las auditorías»: 1 (verificador por juez y cifras deterministas; `existence` no publicable), 4 (los checks nuevos; corridas 0.8 y `existence` no publicables) y 5 (`environment` y metas por intento).

- [ ] **Step 3: `docs/arquitectura.md`.**
- Diagrama (`:15-56`): `EXT` → «📊 extracción sobre texto completo · A0<br/>corrección por campo · concordancia IA–IA»; `ROB` → «⚖️ riesgo de sesgo por herramienta · A0<br/>RoB 2 · ROBINS-I · NOS · AMSTAR 2 · QUADAS-2»; `MA` → «📈 meta-análisis por desenlace · A2<br/>ligado a los incluidos · PI · Egger k ≥ 10»; `VER` → «Verificador por juez<br/>afirmación × cita · cifras sin IA»; quitar la arista `SCR -.-> VER` (`:47`); nodos nuevos `DEP["📦 revisia deposit<br/>copia sin textos completos"]` (desde `DEL`) y `BENCH["🧪 revisia benchmark<br/>panel × corpus congelado · kind: benchmark"]` (desde `NEW`, punteada).
- Contrato 2 (`:65-67`): una meta por intento con lo aplicado y lo pedido; `environment` en `run.json` y en el manifiesto. Contrato 3 (`:68-70`): las afirmaciones pasan por cifras deterministas y un juez de otro modelo antes del gate humano.
- «Dónde está cada cosa» (`:74-81`): Defensa + `rob/`, `text/` y `deposit`; fila nueva «Benchmark | `benchmark/` | `benchmark` · `benchmark-report`».
- Sección nueva **«El auditor por dentro (D26)»**: un párrafo (un módulo por familia, ninguno de más de 900 líneas, fail-closed, el orden de la tabla es el de `audit.md`) y el mapa. Las columnas Orden, Ítem, Etapa y Módulo se **copian de `CHECKS`** con:

```bash
uv run python -c "from revisia.audit import CHECKS; [print(f'| {i} | \`{s.check_id}\` | {s.item_ref} | {s.stage or \"—\"} | \`{s.fn.__module__.rsplit(\".\", 1)[-1]}\` |') for i, s in enumerate(CHECKS, 1)]"
```

y la columna «Qué comprueba» es esta (orden esperado tras G₂; si `CHECKS` dice otro, manda `CHECKS` y se anota):

| # | Check | Qué comprueba |
|---|---|---|
| 1 | `manifest` | Manifiesto presente y coherente con `run.json`; todo `fake` → «corrida de demostración» |
| 2 | `provenance` | `provenance: pipeline`; una corrida de benchmark se declara «no es una revisión» (D23, relación 31) |
| 3 | `environment` | `run.json.environment` válido e igual al del manifiesto; SemVer; plantillas y especificaciones hasheadas; sin `environment` → anterior a la Ola 2 (D12) |
| 4 | `schemas` | Cada artefacto valida su modelo |
| 5 | `protocol_snapshot` | `00_protocol/` igual a las huellas de `run.json` |
| 6 | `prompts` | Cada llamada `ok` con hashes, plantilla, `outcome` y `attempt`; WARN con más del 20 % de intentos fallidos |
| 7 | `timing` | Marcas de tiempo plausibles sobre las llamadas `ok`; `attempt` creciente por registro |
| 8 | `ledger` | Ledger ordenado y con acciones válidas (también `edit_field`, `edit_domain`, `rescue_text`) |
| 9 | `hitl` | Decisión humana en cada etapa de juicio y por registro |
| 10 | `request_hash` | Cada decisión atada a la solicitud que se revisó (`request_sha256`; `concordance`) |
| 11 | `final_gate` | Gate final humano; relación 17 |
| 12 | `stage_artifacts` | Artefactos de cada etapa alcanzada |
| 13 | `deposit` | Sin `deposit.json`: no es copia de depósito; con él, relación 30 (hashes de lo retenido) |
| 14 | `arithmetic` | Embudo PRISMA, diarios y consolidados; relaciones 19–23 y 26 (`agreement.json` recalculado) |
| 15 | `meta_analysis` | Relación 29: agregado = efectos ∩ incluidos; PI y Egger según k; unidad de análisis |
| 16 | `exclusions` | Exclusiones humano/IA y lista 16b |
| 17 | `extraction` | Relaciones 22, 24 y 25: fuente, `quote_status` recalculado, ediciones ⇔ ledger |
| 18 | `rob` | Relaciones 22 y 27: dominios y escala de la especificación, global por la regla, ediciones ⇔ ledger; GRADE → FAIL |
| 19 | `deliverable` | Entregables presentes y coherentes |
| 20 | `gold` | Gold anclado a la instantánea; métricas recalculadas |
| 21 | `thresholds` | `recall_target` y `kappa_min` del protocolo |
| 22 | `grounding` | `judge` con juez ≠ redactor; afirmaciones y `grounded` recalculados (relación 28); `existence`/`embedder` → FAIL (D2) |
| 23 | `search_log` | Log de búsqueda por base (PRISMA-S) |
| 24 | `search_window` | Ventana de la búsqueda frente a la fecha del motor |
| 25 | `registration` | Registro del protocolo (PRISMA 24a) |
| 26 | `response_overlap` | Respuestas idénticas entre miembros; dos `agent` sin modelo informado |

**Nota del mapa (fila I-6):** son **26** filas (corregido en el plan de G₂ tras su revisión; antes decía 25): la Ola 1 deja 21 (`revisia/audit/__init__.py:70-102`), G₁ añade `environment` y `deposit` (23) y G₂ tres más. El test de Step 1 compara con `CHECKS`, así que el número no se copia a mano.

- [ ] **Step 4: Run, revisión y commit.**

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py tests/test_entregable_honesto.py -v`
Expected: PASS. Revisión independiente: el mapa contra `CHECKS` y contra §11.2 del spec; AGENTS contra los planes C, D y E.

```bash
git add AGENTS.md docs/arquitectura.md tests/test_documentacion.py
git commit -m "docs: AGENTS y arquitectura de la Ola 2, con el mapa de los checks del auditor contrastado con CHECKS" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 7: `docs/benchmark-cribado.md` reescrito y notas de metodología (controlador-integrador)

**Files:**
- Modify (reescritura completa): `docs/benchmark-cribado.md`.
- Modify: `docs/metodologia/README.md` (sección nueva al final).
- Modify: `tests/test_documentacion.py`.

**Interfaces:**
- Consumes: CLI de F (`revisia benchmark <protocol_dir> --panel PANEL [--replicas N] [--out DIR] [--max N] [--mailto EMAIL]`, rc 0/2/3/130, reanudable relanzando la misma orden; `revisia benchmark-report <benchmark_dir>… [--out DIR] [--replicas-as-effects]`), `BenchmarkPanel` (`{name, replicas, cells: [{name, provider, model, temperature: 0.0, effort?}]}`), salidas `benchmarks/<slug>-<panel.name>/{panel.yml, runs/<celda>-r<k>/, benchmark.json, benchmark.md}` (sin fecha: relanzar la orden reanuda; F §19 n+13) y `pooled/`.

- [ ] **Step 1: Tests que fallan.**

```python
def test_benchmark_doc_es_metodo_y_comando() -> None:
    doc = _texto("docs/benchmark-cribado.md")
    for afirmacion in ("revisia benchmark", "revisia benchmark-report", "panel.yml",
                       "imported/", ".records.json", "gold.yml", "kind: benchmark",
                       "benchmarks/<slug>-<panel.name>/", "benchmark.json", "Wilson", "unidad de análisis", "--replicas-as-effects"):
        assert afirmacion in doc, afirmacion
    cuerpo, _, nota = doc.partition("## Nota histórica")
    assert nota, "falta la nota histórica"
    for cifra in ("0,820", "0.820", "90,7", "90.7"):
        assert cifra not in cuerpo, cifra
    assert "docs/auditoria/2026-09-03-auditoria-completa.md" in nota


def test_metodologia_declara_grade_y_unidad_de_analisis() -> None:
    kb = _texto("docs/metodologia/README.md")
    for afirmacion in ("GRADE", "certeza", "por desenlace", "unidad de análisis", "23.3",
                       "multiple_per_study", "concordancia IA–IA", "MECIR C43"):
        assert afirmacion in kb, afirmacion
```

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py -k "benchmark or metodologia" -v`
Expected: FAIL en los dos.

- [ ] **Step 2: Reescribir `docs/benchmark-cribado.md`** con estas secciones (sin la tabla «Panel de referencia» de `:51-65`: los modelos del panel son del estudio externo, D6; fila I-10):
1. **Qué mide.** La sensibilidad del cribado título/abstract de cada modelo en **tu** corpus contra **tu** gold. Una corrida de benchmark nunca es una revisión: `kind: benchmark`, se detiene tras T/A, sin gates ni entregable, y `revisia audit` la declara no publicable sin cascada (D23).
2. **Requisitos del protocolo** (rc 2 si faltan): todas las bases manuales con `imported/` (corpus congelado: `*.records.json` nativo, D23, o RIS/BibTeX con el aviso de que los ids sin DOI cambian); `gold.yml` con las dos clases y todos sus ids en el corpus; `screening_ta` sin ensemble (lo fija cada celda).
3. **Preparar corpus y gold.** Corrida exploratoria → copiar `02_dedup/records.json` a `imported/corpus.records.json` → `revisia gold-template` → etiquetar (D18, §14.2).
4. **El panel.** Un `panel.yml` de ejemplo con dos celdas genéricas (`provider`/`model` de marcador), `replicas: 3`, `temperature: 0.0`.
5. **Correr.** `revisia benchmark protocols/<slug> --panel panel.yml`; la carpeta es `benchmarks/<slug>-<panel.name>/`, sin fecha (F §19 n+13): relanzar la misma orden reanuda (una celda con `metrics.json` no se repite) y otro panel con el mismo nombre es rc 2; códigos de salida.
6. **Salida.** `benchmark.json` y `benchmark.md`: recall, lost-evidence, MCC, WMCC, κ, IC de Wilson; `n_failed_records` (registros en que la IA falló, fuera de la matriz con nota).
7. **Agregar varios corpus.** `revisia benchmark-report`: `logit(recall)` por (corpus, modelo), subgrupos por corpus, intervalo de predicción, sin Egger bajo k = 10, duplicados detectados; unidad de análisis: las réplicas se promedian por corpus antes de agregar (`--replicas-as-effects`, solo exploratorio).
8. **Dónde vive el estudio.** Panel, gold, resultados y artículo viven fuera del repositorio (D6); el motor solo trae el comando.
9. **`## Nota histórica`** (al final): el artículo fundacional citó sensibilidad 0,820 e I² 90,7 % a partir de una corrida que la auditoría identificó como reconstrucción, con 27 de 28 efectos de un mismo artículo (C3); no son evidencia; remitir a `docs/auditoria/2026-09-03-auditoria-completa.md` (C3 y §11).

- [ ] **Step 3: `docs/metodologia/README.md`**, sección nueva «## Decisiones metodológicas del motor (Ola 2)» con tres notas cortas, cada una con su fuente (fila I-9):
- **GRADE no es riesgo de sesgo por estudio.** Califica la **certeza** de la evidencia **por desenlace** sobre el conjunto de estudios (GRADE Handbook); `rob_tool: GRADE` es un error de configuración y GRADE volverá como etapa propia tras la síntesis (D5, spec §17). Mientras, el revisor lo hace fuera del motor y lo declara.
- **Unidad de análisis.** Cochrane Handbook §23.3: dos efectos del mismo estudio en el mismo desenlace no son independientes; `effects.yml` lo rechaza salvo `multiple_per_study: {allowed: true, justification}`, que `metodologia.md` declara; solo agregan los efectos de los estudios incluidos (D16). En `benchmark-report`, las réplicas se promedian por corpus.
- **Extracción.** La «doble extracción» del motor es una **concordancia IA–IA** del 20 %, una señal de qué revisar primero; no es la doble extracción humana independiente de MECIR C43. Lo que sí hay: el humano revisa cada tabla y corrige campo a campo (`edit_field`, D3, D4).

- [ ] **Step 4: Run, revisión y commit.**

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py -v && grep -rn "0,820\|90,7" README.md AGENTS.md docs --include=*.md | grep -v "docs/superpowers/\|docs/auditoria/\|docs/benchmark-cribado.md"`
Expected: PASS; el `grep` no imprime nada. Revisión independiente: cada opción y fichero del documento contra `revisia/cli.py` y `revisia/benchmark/` del worktree.

```bash
git add docs/benchmark-cribado.md docs/metodologia/README.md tests/test_documentacion.py
git commit -m "docs: benchmark de cribado como método y comando (C3, D6) y notas de metodología sobre GRADE, unidad de análisis y concordancia IA–IA" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 8: `RELEASING.md` y `SECURITY.md` (controlador-integrador)

**Files:**
- Modify (reescritura): `RELEASING.md` (hoy 35 líneas; desactualizado según la auditoría, hallazgos bajos).
- Modify: `SECURITY.md:8-13` (tabla de versiones soportadas: `0.9.x ✅`, `< 0.9 ❌`; la frase de `:13` pasa a «La 0.9.0 incluye las correcciones de seguridad de las Olas 0, 1 y 2…», con el acotamiento de `claude -p` de la Ola 2: versión mínima, `--safe-mode`, entorno por allowlist). Es el quinto sitio que cambia con cada versión (fila I-16).
- Modify: `tests/test_documentacion.py`.

- [ ] **Step 1: Test que falla.**

```python
import re  # en el bloque de imports


def test_releasing_documenta_matriz_lock_y_version_de_uv() -> None:
    releasing = _texto("RELEASING.md")
    ci = _texto(".github/workflows/ci.yml")
    version_uv = re.search(r'(?m)^\s*version:\s*"(\d+\.\d+\.\d+)"', ci).group(1)
    for afirmacion in (version_uv, f"uvx uv@{version_uv} lock", "uv lock --check",
                       "-m cronometrado", "Ubuntu y Windows", "3.11", "3.12", "3.13",
                       "uv.lock", "CITATION.cff", "revisia/__init__.py", "SECURITY.md",
                       "date-released", "90 %"):
        assert afirmacion in releasing, afirmacion


def test_security_soporta_la_serie_actual() -> None:
    mayor_menor = ".".join(revisia.__version__.split(".")[:2])
    assert f"| {mayor_menor}.x" in _texto("SECURITY.md")
```

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py::test_releasing_documenta_matriz_lock_y_version_de_uv -v`
Expected: FAIL.

- [ ] **Step 2: Reescribir `RELEASING.md`** con estas secciones:
1. **Bump de versión**: `pyproject.toml`, `revisia/__init__.py`, `CITATION.cff` (`version` y `date-released`, que se revisa: la fecha del release, no la del primer commit) y `uv.lock` regenerado con `uvx uv@<versión del CI> lock`; `tests/test_pyproject.py` falla si no coinciden. La línea de «Cómo citar» del README y la tabla de versiones de `SECURITY.md` (en una serie nueva). `CHANGELOG.md`: mover `Unreleased` a la versión y actualizar los enlaces del pie.
2. **Verificación antes del tag**: en local, `uvx uv@<versión del CI> lock --check` (el job `lint` corre el equivalente, `uv lock --check`, con esa versión), ruff, black, `uv run pytest -n auto -m "not cronometrado"` y **después, en serie**, `uv run pytest -m cronometrado` (cotas de tiempo de pared que fallan en falso con `-n auto`); cobertura ≥ 90 % (`--cov`). En el CI: `lint` (incluye `uv lock --check`), la matriz `ubuntu-latest`/`windows-latest` × Python 3.11/3.12/3.13 (6 celdas, `fail-fast: false`), cobertura en Ubuntu/3.13, `build` (`uv build` y contenido del wheel) y `sdk-smoke`. Una celda Windows roja no se apaga: se corrige o se marca con razón (riesgo 9).
3. **Política de versión de uv** (§19 fila 8, texto a fijar): la versión de uv está fijada en `setup-uv` del CI (`version: "0.11.26"`) para que `uv lock --check` sea reproducible; en local no se fija (`[tool.uv] required-version` no existe a propósito), así que el lock se regenera siempre con `uvx uv@<esa versión> lock`. Subir la versión de uv es **un commit propio** que cambia `ci.yml`, regenera `uv.lock` con la versión nueva y actualiza este documento.
4. **DOI vía Zenodo**: el webhook archiva el release; añadir el DOI de la versión al bloque `identifiers` de `CITATION.cff` y a «Cómo citar» del README (el DOI concept no cambia).
5. **Versiones intermedias (D7)**: la 0.9.0 publica el motor de la Ola 2 antes de la corrida real, para que esa corrida registre un `engine_version` liberado; la 1.0.0 llega con la corrida depositada y la re-auditoría y es documental respecto a 0.9.x (§14).
6. **Checklist** con casillas para todo lo anterior, incluidas `date-released` revisada el día del release y `SECURITY.md` al día. Y una nota: con PR apiladas el CI corre en cada PR si `pull_request` no filtra la rama (fila I-17); si no, suite local en las tres versiones y `gh pr edit --base main` + cerrar y reabrir al mergear.

- [ ] **Step 3: `SECURITY.md`** según Files.

- [ ] **Step 4: Run y commit.**

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py -v`
Expected: PASS.

```bash
git add RELEASING.md SECURITY.md tests/test_documentacion.py
git commit -m "docs(releasing): matriz, -m cronometrado, uv lock --check, versión de uv (§19 fila 8) y SECURITY.md en 0.9.x" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 9: `CHANGELOG.md` 0.9.0 con «Cambios incompatibles» completo (controlador-integrador)

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`, que llega con lo que añadieron las integraciones de PR-0, H, A, B, C, D, E, F y G; y los enlaces del pie, `CHANGELOG.md:739-740` en `c1af7c3`).
- Modify: `tests/test_documentacion.py`.

- [ ] **Step 1: Test que falla.**

```python
def test_changelog_tiene_la_version_con_sus_cambios_incompatibles() -> None:
    changelog = _texto("CHANGELOG.md")
    version = revisia.__version__
    _, _, resto = changelog.partition(f"## [{version}] · ")
    assert resto, f"falta la sección {version}"
    seccion = resto.split("\n## [", 1)[0]
    _, _, incompatibles = seccion.partition("### Cambios incompatibles")
    for tema in ("`grounding`", "de `embedder` a `existence`", "`judge`", "`llm.verificador`",
                 "`[2019]`", "prisma-ia-origen", "GRADE", "robvis.csv", "`outcome`",
                 "multiple_per_study", "Egger", "funnel.png", "render_methods",
                 "prompt_sha256", "Una corrida 0.8", "por intento", "401", "RecordFailedError",
                 "MIN_CLI_VERSION", "--safe-mode", "allowlist", "--max-budget-usd",
                 "auto_approve", "concordance", "record_id", "`rag`", "InMemoryVectorStore",
                 "QDRANT", "requires-python >= 3.11", "fail-closed"):
        assert tema in incompatibles, tema
    for no_es_incompatible in ("load_template", "risk_of_bias.md"):
        assert no_es_incompatible not in incompatibles, no_es_incompatible
    for subseccion in ("### Removed", "### Documentación"):
        assert subseccion in seccion, subseccion
    assert f"[{version}]: https://github.com/jhonmosquerav/revisia/compare/v0.8.0...v{version}" \
        in changelog
    assert f"[Unreleased]: https://github.com/jhonmosquerav/revisia/compare/v{version}...HEAD" \
        in changelog
```

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py::test_changelog_tiene_la_version_con_sus_cambios_incompatibles -v`
Expected: FAIL (no hay sección `0.9.0`).

- [ ] **Step 2: Componer la sección.**
- `## [Unreleased]` queda vacío encima; debajo, `## [0.9.0] · <fecha del bump>` con lo que traía `Unreleased`, en este orden: `### Added`, `### Fixed`, `### Changed`, `### Removed`, `### Documentación`, `### Cambios incompatibles` (el de la 0.8.0 con las dos nuevas antes de la última), y con una sola subsección de cada tipo (las integraciones pudieron dejar varias). **No** van en «Cambios incompatibles»: `load_template` (aditivo; `load_prompt` no cambia, A §19 n+16) ni `risk_of_bias.md` (conserva el nombre, E m+8).
- Entradas de PR-I: en `### Removed` (nueva, Keep a Changelog): extra `rag`, `QDRANT_*` de `.env.example` e `InMemoryVectorStore` (D27, M16). En `### Changed`: el doble `fake` cita el primer estudio incluido en su síntesis (§16; solo con (a)); `0.9.0` en pyproject, paquete, CITATION y lock. En `### Documentación` (como en la 0.7.0): README, AGENTS, arquitectura con el mapa del auditor, benchmark como método y comando, notas de metodología, `RELEASING.md`, `SECURITY.md` (0.9.x), auditoría §11.
- `### Cambios incompatibles` **consolidado** (las de cada integración se funden aquí; §18.4 completo más lo que añadieron los planes). Texto base, que el integrador completa con lo que haya registrado cada integración y no esté abajo:

```
- **Verificación (D2).** El default de `grounding` pasa de `embedder` a `existence` (comprueba que
  la cita exista y nada más). `grounding` solo admite `existence`, `judge` y `embedder`
  (experimental); `agent` queda como alias obsoleto de `judge`. `judge` exige `llm.verificador` con un `provider:model` distinto del de `sintesis`
  (rc 2 si falta o coincide). Una corrida publicable exige `judge`: `existence` y `embedder` dan
  FAIL en `grounding`. `[2019]` y `[1]` ya no son citas. `report_payload` pierde
  `grounding_mode`. Los dobles `fake` juzgan *fail-closed*.
- **`protocols/prisma-ia-origen`**, y todo protocolo con `grounding: agent` sin `llm.verificador`,
  da rc 2 en `validate` y `run` hasta que se añada `llm.verificador` de otro modelo.
- **Riesgo de sesgo (D5).** `rob_tool: GRADE` es rc 2 (GRADE califica certeza por desenlace); la
  escala única `low/some_concerns/high/unclear` desaparece (cada herramienta usa la suya);
  `robvis.csv` lleva `D1…Dn`, `Overall` y `Weight`.
- **Meta-análisis (D16).** Un `effects.yml` sin `outcome` es rc 2 con el mensaje de migración; dos
  efectos del mismo estudio en un desenlace, rc 2 sin `multiple_per_study`; cada desenlace
  necesita k ≥ 2; Egger y el funnel solo con k ≥ 10 (el demo, con k = 4, deja de producir
  `funnel.png`); `meta_analysis.json` es v2 (por desenlace); `render_methods` pierde el argumento
  `included_ids`.
- **`claude -p` (D11, A10, M17).** Versión mínima del CLI (`MIN_CLI_VERSION`): por debajo, o sin
  `--safe-mode`/`--tools` en su `--help`, es error de preflight. El subproceso recibe el entorno
  por allowlist, no `os.environ` entero (`REVISIA_CLAUDE_CODE_ENV_EXTRA` añade nombres). Con
  `ANTHROPIC_API_KEY`, cada llamada lleva `--max-budget-usd` (1,00 por defecto;
  `llm.<etapa>.max_budget_usd`).
- **Procedencia (D12, D14).** `RunInfo.prompt_sha256` pasa a `run.json.environment.prompt_templates`;
  `schema_version` de los artefactos es 2. Una corrida 0.8 (sin `environment`) no se reanuda
  (rc 2) ni es publicable (FAIL en `environment`). Los proveedores emiten una meta por intento: un
  proveedor de terceros sigue funcionando y solo pierde las metas de los intentos fallidos.
- **Errores (D9).** 401, 403, 408, 429, 5xx, red y timeout son transitorios (se reanudan); 400,
  404, 413, 422, un bloqueo de contenido, un límite de presupuesto o de turnos de `claude -p` y la
  salida inválida tras los reintentos son deterministas: dejan una línea `failed` definitiva y
  `journaled` lanza `RecordFailedError` (subclase de `JournalError`); T/A, FT, extracción y RoB
  llevan el registro al gate humano, y la síntesis, que no tiene gate, sale con rc 2. Las
  métricas de cribado excluyen los registros en que la IA falló.
- **HITL.** `run_review_with_agent` ya no aprueba solo (`auto_approve=False`). La solicitud de
  `extraccion` lleva `concordance` en vez de `second_extraction`; `agreement.json` es v2.
- **Identidad (D19).** `SearchRecord.doi` se normaliza al construirse; los `record_id` de una
  corrida nueva pueden diferir de los de la 0.8 para el mismo artículo; un título de relleno ya
  no fusiona registros.
- **Paquete (D27).** Se elimina el extra `rag`; `QDRANT_*` sale de `.env.example`; `revisia.rag`
  deja de exportar `InMemoryVectorStore` (`cosine` y `semantic_similarity` siguen).
- **Python.** `requires-python >= 3.11` (amplía, no rompe).
```

- Pie: `[Unreleased]: …/compare/v0.9.0...HEAD` y `[0.9.0]: …/compare/v0.8.0...v0.9.0` encima de `[0.8.0]`.

- [ ] **Step 3: Run y commit.**

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py -v && grep -c "^### Cambios incompatibles" CHANGELOG.md`
Expected: PASS; el recuento es el de antes de la ola más uno (una por versión: 0.8.0 y 0.9.0, ninguna repetida dentro de 0.9.0).

```bash
git add CHANGELOG.md tests/test_documentacion.py
git commit -m "docs(changelog): 0.9.0 con los cambios incompatibles de la Ola 2 consolidados (§18.4)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 10: Auditoría §11 «Ola 2 · motor cerrado» (controlador-integrador)

**Files:**
- Modify: `docs/auditoria/2026-09-03-auditoria-completa.md` (§11: subsección nueva tras «Ola 1 · cerrada», `:242-266` en `c1af7c3`; y el párrafo final `:265-266`).
- Modify: `tests/test_documentacion.py`.

- [ ] **Step 1: Test que falla.**

```python
def test_auditoria_declara_el_motor_de_la_ola_2_cerrado_y_lo_pendiente() -> None:
    auditoria = _texto("docs/auditoria/2026-09-03-auditoria-completa.md")
    _, _, ola2 = auditoria.partition("### Ola 2 · motor cerrado")
    assert ola2, "falta la subsección de la Ola 2"
    assert "pendiente: re-auditoría y corrida real (D1)" in ola2
    for hallazgo in ("C2", "C3", "A4", "A5", "A6", "A7", "A8", "A10", "A12", "A13", "A15",
                     "A16", "M3", "M14", "M15", "M16", "M17", "M18", "M19", "M20", "M21",
                     "M22", "M24"):
        assert f"**{hallazgo}**" in ola2, hallazgo
```

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py::test_auditoria_declara_el_motor_de_la_ola_2_cerrado_y_lo_pendiente -v`
Expected: FAIL.

- [ ] **Step 2: Escribir la subsección** `### Ola 2 · motor cerrado (0.9.0; PR-0, H, A–G, I)`, con el mismo formato que las de la Ola 0 y la Ola 1: enlace al spec y al CHANGELOG, la tabla `| Hallazgo | Estado | Qué se hizo |` y un cierre.
- Estados: **«Cerrado en el motor»** (la re-auditoría de §14.1 decide si lo confirma; fila I-14), «Parcial», «Fuera de alcance (§17)».
- Filas, con el «qué se hizo» en una o dos frases y la decisión que lo sostiene: C2 (D2, D15, D22, D24), C3 (Parcial: el benchmark es un comando con la unidad de análisis en código y el auditor da FAIL a la reconstrucción por ≥ 12 vías; queda la corrida real y el estudio externo, D1, D6), A4 y A5 (D19), A6, A7 y A15 (PR-A, D12, D14), A8 (`AgentReply`, `auto_approve=False`), A10 (D11; `--bare` descartado a propósito: rompe la suscripción), A12 (D5), A13 (PR-H), A16 (D3, D4), M3 (D10: delimitado y declarable, no eliminado), M13 (Parcial: trAIce declara lo aplicado, M2/M6; sigue sin el mapeo de los 17 ítems), M14 (D20, D21), M15 (fila I-7: el **bucle de rc 3** que la Ola 1 registró como M15 está cerrado por D9; los reintentos con backoff en los proveedores API que esta tabla llama M15 quedan **fuera de alcance**, §17), M16 (D27), M17 (`--max-budget-usd` en `claude_code`; presupuesto global fuera de alcance), M18–M21 (PR-H), M22 y M24 (D25; cobertura ≥ 90 %, no 80 %, §19 fila 5). Bajos cerrados por la ola: Egger desde k = 3, sin intervalo de predicción, CI sin `permissions:`, `RELEASING.md` desactualizado, conteo de tests distinto en cada documento (badge del CI).
- Cierre, con la frase literal: «**pendiente: re-auditoría y corrida real (D1)**. La Ola 2 no se declara cerrada hasta que la corrida de `prisma-ia-origen` producida por el motor liberado sea APTA, esté depositada y la re-auditoría lo confirme (§14); entonces se publica 1.0.0.»
- El párrafo final de §11 (`:265-266`, «Sigue abierta… la Ola 2…») pasa a decir que el motor de la Ola 2 está cerrado en 0.9.0 y que la ola sigue abierta hasta §14.

- [ ] **Step 3: Run, revisión y commit.**

Run: `uv run pytest -p no:cacheprovider tests/test_documentacion.py -v`
Expected: PASS. Revisión independiente: cada fila contra el CHANGELOG 0.9.0 y los planes; ningún «Cerrado» sin la PR que lo cierra.

```bash
git add docs/auditoria/2026-09-03-auditoria-completa.md tests/test_documentacion.py
git commit -m "docs(auditoría): §11 Ola 2 · motor cerrado, con la tabla hallazgo→estado y lo pendiente (D1)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 11: §19 al día, criterio de cierre del motor (§16) y PR (controlador)

**Files:**
- Modify: `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` (§19).

- [ ] **Step 1: §19 al día.** Comprobar que cada integración registró sus filas y que la numeración no salta:

```bash
SPEC=docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md
for P in PR-0 PR-H PR-A PR-B PR-C PR-D PR-E PR-F PR-G; do printf "%s " "$P"; grep -c "Plan $P" "$SPEC"; done
awk -F'|' '/^\| [0-9]+ \|/{n=$2+0; if (prev && n != prev + 1) print "salto en la fila", n; prev = n}' "$SPEC"
```

Expected: cada plan con al menos tantas filas como propuso en su tarea de integración (PR-0: 7; H: 3; A: 20; B: las de su Tarea 8; C: 21; D: 26; E: las de E₁ más 11; F: 30, de n a n+29; G: 23, de n a n+22), y el `awk` no imprime nada. Si falta alguna, se añade ahora con su origen y se anota en el cuerpo de la PR.

Después, añadir las filas de PR-I a continuación de la última (`L + 1` de la Tarea 0):

```
| I-1 | §16 cierre por CLI | Decisión del arquitecto sobre la propuesta de D (n+25) y de G (n+19): **(a)** `FakeProvider.complete` cita el primer id del bloque `estudios` del prompt de síntesis; con `grounding: judge` y verificador `fake` la cita sale marcada y se adjudica por CLI; en `existence` (el demo) la cita existe y no se marca. **(b)** se descarta / se elige: §16 reformulado (adjudicación en proceso con `corrida_ola2_completa`, `tests/test_pipeline_fake.py::test_frontera_de_la_ola_2_completa_es_apta`, G2.10) | Plan PR-I (decisión del arquitecto) |
| I-2 | §16 «por CLI» | El criterio se prueba con `revisia.cli.main([...])` en proceso (`tests/test_cierre_motor.py`), como `tests/test_cli_benchmark.py` de F: base manual con corpus congelado (sin red en la búsqueda) y `fetch_fulltext` sustituido (un registro con DOI consultaría NCBI). El humo por subproceso con red es complementario y no es un test. «Los WARN de demo» de §16 son `AVISOS_DEL_CIERRE`, con un comentario por aviso | Plan PR-I |
| I-3 | §13 badge | El badge de tests muestra el estado del workflow del CI, no un recuento fijo (la auditoría señaló recuentos distintos en cada documento) | Plan PR-I |
| I-4 | §13 versión | «Los tres sitios» son cuatro: `uv.lock` también lleva la versión del paquete; se regenera con la versión de uv del CI. Un test fija la igualdad de los cuatro, no el número. La línea de «Cómo citar» del README la fija `tests/test_documentacion.py` | Plan PR-I |
| I-5 | D27 | Quitar `InMemoryVectorStore` de `revisia.rag.__all__` es un cambio incompatible de la API pública del paquete y va en el CHANGELOG | Plan PR-I |
| I-6 | Plan PR-G, mapa del auditor | `CHECKS` tiene **26** filas tras G₂ (21 de la Ola 1 + `environment`, `deposit` + `extraction`, `rob`, `meta_analysis`; el plan de G₂ decía 25 antes de su revisión). El mapa de `docs/arquitectura.md` se contrasta con `CHECKS` en un test | Plan PR-I |
| I-7 | §1, §11 auditoría | «M15» designa dos cosas: en la tabla de la auditoría, reintentos/backoff en los proveedores API (fuera de alcance, §17); en el README y el spec de la Ola 1, el bucle de rc 3 (cerrado por D9). La §11 nombra las dos | Plan PR-I |
| I-8 | D §19 n+14, G n+19 | PR-I decide (la fila n+19 de G sustituye a la n+14 de D): el demo (`examples/demo-mini-review`) y `_TEMPLATE` siguen en `grounding: existence`. Con `judge` y juez `fake` (fail-closed) el `--auto-approve` del quickstart pausaría en el gate final (cita marcada, humano forzado). La frontera de §16 con `judge` corre sobre una copia del demo (Tarea 3); `test_pipeline_fake_con_humano_audita_sin_fail` sigue con `fallos == {"grounding"}` y `AVISOS_DE_LA_DEMO` pierde la entrada `grounding` si la conserva | Plan PR-I |
| I-9 | §13 `docs/metodologia/` | Las notas sobre GRADE, unidad de análisis y concordancia IA–IA van en una sección de `docs/metodologia/README.md`, no en un fichero nuevo | Plan PR-I |
| I-10 | §13 `docs/benchmark-cribado.md` | La tabla «Panel de referencia» con modelos concretos sale: el panel es del estudio externo (D6) y los modelos caducan; queda un `panel.yml` de ejemplo con marcadores | Plan PR-I |
| I-11 | §13 README | La sección «Auditoría abierta» se conserva y se actualiza en 0.9.0; se retira en 1.0.0 (§14.4) | Plan PR-I |
| I-12 | §19 fila 8 | `RELEASING.md` fija el comando `uvx uv@<versión del CI> lock`; un test comprueba que la versión documentada es la de `ci.yml` | Plan PR-I |
| I-13 | §13 CHANGELOG | Las subsecciones de 0.9.0 se consolidan (una de cada tipo) y «Cambios incompatibles» reúne §18.4 y lo que registró cada integración; `### Removed` nueva para D27 | Plan PR-I |
| I-14 | §13 auditoría §11 | El estado de los hallazgos de la Ola 2 es «Cerrado en el motor»: lo confirma o lo reabre la re-auditoría de §14.1 | Plan PR-I |
| I-15 | §15 dueños de ficheros | PR-I toca `revisia/llm/providers/fake.py` (dueño A; solo `complete`, con (a)) y `revisia/rag/{store,__init__,embed}.py` (dueño D; solo la clase muerta de D27, el `__init__` y docstrings). Precedente: D tocó `fake.py` (D §19 n+11). PR-I es la última de la pila: no hay rebase posterior que choque | Plan PR-I (revisión) |
| I-16 | §13 versión, RELEASING | Con cada serie cambian cuatro sitios de versión (`pyproject.toml`, `revisia/__init__.py`, `CITATION.cff`, `uv.lock`) **más** la tabla de `SECURITY.md` y la línea de «Cómo citar» del README; `RELEASING.md` los lista y un test fija `SECURITY.md` | Plan PR-I (revisión) |
| I-17 | §15, D25 · CI en PR apiladas | Decisión del orquestador: el plan de H quita el filtro de rama de `pull_request`, así que las PR apiladas corren el CI y los Expected de «CI verde» valen. Si el arquitecto la rechaza: suite local en 3.11, 3.12 y 3.13 y, al mergear, `gh pr edit <n> --base main` y cerrar y reabrir la PR | Orquestador (revisión de PR-I); **para el arquitecto** |
| I-18 | §18.4 | El CHANGELOG 0.9.0 amplía la lista de §18.4 con lo que añadieron los planes: default de `grounding` de `embedder` a `existence`, `[2019]`/`[1]` no son citas, `prisma-ia-origen` rc 2, `MIN_CLI_VERSION` con `--safe-mode`/`--tools`, entorno por allowlist, `--max-budget-usd` 1,00 con API key, 401/403 transitorios y `RecordFailedError`, `render_methods` sin `included_ids`, el demo sin `funnel.png`, `record_id` que cambian, `robvis.csv`, `InMemoryVectorStore`. `load_template` y `risk_of_bias.md` no son incompatibles | Plan PR-I (revisión) |
```

Sustituir `I-n` por los números consecutivos desde `L + 1` y completar con lo que hayan producido las revisiones de las Tareas 1–10. En I-1, dejar solo la opción elegida.

```bash
git add "$SPEC"
git commit -m "docs(spec): desviaciones (§19) de PR-I" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Verificación completa en las tres versiones.**

```bash
uv run black --check . && uv run ruff check . && uv run ruff format --check . && uvx uv@0.11.26 lock --check
for PY in 3.11 3.12 3.13; do
  uv run --python "$PY" --extra dev --extra search --extra meta \
    pytest -p no:cacheprovider -q -n auto -m "not cronometrado" -rxX || exit 1
  uv run --python "$PY" --extra dev --extra search --extra meta \
    pytest -p no:cacheprovider -q -m cronometrado || exit 1
done
# Cobertura con las dos pasadas del CI de H: la cota se juzga sobre la suma (--cov-append).
uv run --extra dev --extra search --extra meta \
  pytest -p no:cacheprovider -q -n auto -m "not cronometrado" --cov --cov-report=term --cov-fail-under=0
uv run --extra dev --extra search --extra meta \
  pytest -p no:cacheprovider -q -m cronometrado --cov --cov-append --cov-report=term --cov-fail-under=90 | tail -3
uv run revisia --version
wc -l revisia/audit/*.py | sort -n | tail -3
```

Expected: lint limpio; verde en las tres versiones, **0 XFAIL y 0 XPASS**; cobertura ≥ 90 % (D25, §19 fila 5); `revisia 0.9.0`; ningún módulo del auditor por encima de 900 líneas. Anotar el recuento `N₁` (desde `N₀`).

- [ ] **Step 3: Criterio de cierre del motor (§16), punto por punto.**

| Punto de §16 | Comando | Expected |
|---|---|---|
| `revisia run` con `grounding: judge` y verificador `fake` distinto → pausas en los cinco gates → etiquetas, una edición de campo, una de dominio, un rescate con texto y una adjudicación → `--resume` → `revisia audit` **APTA** | `uv run pytest -p no:cacheprovider tests/test_cierre_motor.py::test_cierre_judge_con_humano_por_cli_es_apto -v` | PASS. Con (b): el mismo test sin adjudicación, y además `uv run pytest -p no:cacheprovider tests/test_pipeline_fake.py::test_frontera_de_la_ola_2_completa_es_apta -v` (adjudicación en proceso, `corrida_ola2_completa`) en PASS |
| La misma corrida con `grounding: existence` → NO publicable por `grounding` | `uv run pytest -p no:cacheprovider tests/test_cierre_motor.py::test_cierre_existence_por_cli_no_es_publicable_solo_por_grounding -v && uv run pytest -p no:cacheprovider tests/test_pipeline_fake.py -k "existence" -v` | PASS (el segundo, sobre `corrida_existence` de G₂) |
| `--auto-approve` → NO publicable | `uv run pytest -p no:cacheprovider tests/test_pipeline_fake.py::test_pipeline_auto_approve_no_es_publicable -v` | PASS |
| La reconstrucción C3 → NO publicable por ≥ 12 checks | `uv run pytest -p no:cacheprovider tests/test_audit_c3.py -v` | PASS, incluido `test_audit_c3_reconstruccion_no_es_publicable_por_al_menos_doce_vias` |
| Una corrida 0.8 real (fixture) → NO publicable por `environment`, resto en diagnóstico | `uv run pytest -p no:cacheprovider tests/test_audit_entorno.py -k "08" -v` | PASS (`write_run_v08`: FAIL en `environment` con el mensaje de D12, `prompts` en FAIL por esquema v1, ninguna fila con «error interno») |
| `revisia deposit` de la corrida APTA → el depósito audita APTA | `uv run pytest -p no:cacheprovider tests/test_cierre_motor.py::test_cierre_deposito_de_la_corrida_apta_audita_apto tests/test_audit_deposito.py -v` | PASS |
| `revisia benchmark` sobre el demo importado con dos celdas fake → `benchmark.json`; `benchmark-report` → `pooled/` | `uv run pytest -p no:cacheprovider tests/test_cli_benchmark.py -v` | PASS |

Humo por subproceso, con el binario instalado (complementario; el demo usa la red de OpenAlex):

```bash
H=../i-humo; rm -rf "$H"; mkdir -p "$H"
uv run revisia run examples/demo-mini-review --auto-approve --max 8 --runs-root "$H/runs"
RUN="$(ls -d "$H"/runs/*/ | head -1)"
uv run revisia audit "$RUN" > "$H/audit.txt"; echo "rc=$?"
uv run revisia deposit "$RUN" --out "$H/dep/$(basename "$RUN")"
uv run revisia audit "$H/dep/$(basename "$RUN")" > "$H/audit-dep.txt"; echo "rc=$?"
diff <(awk 'NF>=3 && $2 ~ /^(PASS|WARN|FAIL|N\/A)$/ {print $2, $3}' "$H/audit.txt") \
     <(awk 'NF>=3 && $2 ~ /^(PASS|WARN|FAIL|N\/A)$/ {print $2, $3}' "$H/audit-dep.txt")
uv run python - "$H" <<'PY'
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "tests")
from conftest import protocolo_benchmark  # noqa: E402

destino = Path(sys.argv[1])
proto = protocolo_benchmark(destino)
panel = {"name": "panel-humo", "replicas": 2, "cells": [
    {"name": "fake-a", "provider": "fake", "model": "fake-a", "temperature": 0.0},
    {"name": "fake-b", "provider": "fake", "model": "fake-b", "temperature": 0.0}]}
(destino / "panel.yml").write_text(yaml.safe_dump(panel), encoding="utf-8")
print(proto)
PY
PROTO="$(ls -d "$H"/proto/*/ | head -1)"
uv run revisia benchmark "$PROTO" --panel "$H/panel.yml" --out "$H/bench"; echo "rc=$?"
BENCH="$(ls -d "$H"/bench/*/ | head -1)"
uv run revisia benchmark-report "$BENCH" --out "$H/pooled-out"; echo "rc=$?"
ls "$BENCH" "$H/pooled-out"
```

Expected:
- `run` termina (rc 0); las dos auditorías con `rc=1` (NO publicable: `--auto-approve` y `existence`), y el `diff` de estados por check vacío;
- `deposit` imprime los hashes retenidos;
- `benchmark` con `rc=0` y una línea por celda y réplica; `benchmark.json` y `benchmark.md` en la carpeta; `benchmark-report` con `rc=0` y `pooled/` (o la carpeta de `--out`) con `meta_analysis.json` y `report.md`.
- Si la red falla, el primer bloque se repite más tarde; no se sustituye por otra cosa.

- [ ] **Step 4: Comprobación de los textos que no pueden volver.**

```bash
grep -rn "InMemoryVectorStore\|qdrant\|QDRANT" revisia tests pyproject.toml .env.example uv.lock README.md AGENTS.md docs/*.md docs/metodologia
grep -rn "0,820\|90,7" README.md AGENTS.md docs --include=*.md | grep -v "docs/superpowers/\|docs/auditoria/\|docs/benchmark-cribado.md"
grep -rn "doble 20\|+doble\|grounding: agent" README.md AGENTS.md docs/arquitectura.md docs/benchmark-cribado.md
```

Expected: las tres órdenes no imprimen nada.

- [ ] **Step 5: Publicar la rama.**

```bash
git push -u origin feat/ola2-cierre
```

- [ ] **Step 6: Abrir la PR** (base `feat/ola2-auditor`, §15; sin merge).

```bash
gh pr create --base feat/ola2-auditor --head feat/ola2-cierre --title "Ola 2 · PR-I: cierre del motor (Qdrant fuera, 0.9.0 y documentación de la ola)" --body "$(cat <<'EOF'
## Qué cierra

M16, D7, D27 y la documentación de la Ola 2 (spec `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`, §13), y verifica el criterio de cierre del motor (§16) de punta a punta.

## Qué cambia

- **D27:** sin extra `rag`, sin `QDRANT_*` en `.env.example` y sin `InMemoryVectorStore`; `semantic_similarity` se queda (modo `embedder`).
- **§16:** <(a) el doble `fake` cita el primer estudio incluido, para que la adjudicación se vea por CLI | (b) §16 reformulado: la adjudicación se prueba en proceso>; `tests/test_cierre_motor.py` recorre el criterio por CLI.
- **0.9.0** en `pyproject.toml`, `revisia/__init__.py`, `CITATION.cff` y `uv.lock`, con un test de sincronía.
- **Documentación:** README (verificador por juez y qué significa `existence`, procedencia aplicada, RoB por herramienta sin GRADE, concordancia IA–IA, `revisia benchmark`, `revisia deposit`, CI multiplataforma, badge del CI), AGENTS, `docs/arquitectura.md` con el mapa de los 26 checks del auditor, `docs/benchmark-cribado.md` reescrito (método y comando), notas de metodología (GRADE, unidad de análisis), CHANGELOG 0.9.0 con «Cambios incompatibles», auditoría §11 «Ola 2 · motor cerrado» y `RELEASING.md` (matriz, `-m cronometrado`, `uv lock --check`, versión de uv).
- `tests/test_documentacion.py`: lo que cada documento tiene que decir y lo que ya no puede decir.

## Criterio de cierre del motor (§16)

<tabla de la Tarea 11, Step 3, con el resultado de cada fila y del humo por subproceso>

## Cambios incompatibles

Ver la sección 0.9.0 del CHANGELOG (D27 añade: extra `rag` y `InMemoryVectorStore` eliminados).

## Pendiente antes del tag `v0.9.0`

- <comprobación real de `claude -p` de PR-A: hecha el <fecha> | pendiente del arquitecto (Tarea 13, Step 6 del plan de PR-A)>.
- Después del merge de la pila: tag, release y DOI según `RELEASING.md`; luego, §14 (re-auditoría, corrida real, 1.0.0).

## Verificación

- Suite en 3.11, 3.12 y 3.13: <N₁> recogidos (base PR-G: <N₀>), en verde, 0 XFAIL; cobertura <X> %.
- `ruff`, `black`, `uv lock --check`: limpios. Ningún módulo del auditor pasa de 900 líneas.

## Pila

`main` ← PR-0 ← PR-H ← PR-A ← PR-B ← PR-C ← PR-D ← PR-E ← PR-F ← PR-G ← **PR-I** (spec §15). Al mergear, ninguna rama con `--delete-branch` mientras otra PR la use como base.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: la URL de la PR. Esperar `gh pr checks <n> --watch`: `lint`, las seis celdas de `test`, `build` y `sdk-smoke` en verde. Sustituir los marcadores `<…>` con `gh pr edit <n> --body-file …`. **El merge, el tag y el release los decide el arquitecto.**

---

## Self-review (hecha al escribir el plan)

- **Cobertura de §13:**

  | Pieza de §13 | Tarea |
  |---|---|
  | README: verificador por juez, `existence` y qué significa, procedencia aplicada, RoB por herramienta sin GRADE, concordancia IA–IA, `revisia benchmark`, `revisia deposit`, CI multiplataforma, nota M15 eliminada, badge | 5 |
  | AGENTS: `verificador` LLM con juez propio, RoB sin GRADE, extracción por campo, concordancia IA–IA | 6 |
  | `docs/arquitectura.md` (y el mapa del auditor que G₂ dejó para I) | 6 |
  | `docs/benchmark-cribado.md` reescrito, cifras solo en la nota histórica | 7 |
  | `docs/metodologia/`: GRADE y unidad de análisis | 7 |
  | `.env.example` sin `QDRANT_*`, extra `rag` eliminado, `InMemoryVectorStore` (D27) | 1 |
  | CHANGELOG con «Cambios incompatibles» (§18.4 más los planes: `prisma-ia-origen`, 401/403, `[2019]`, fail-closed, `record_id`…) | 9 |
  | Auditoría §11 con la tabla y «pendiente: re-auditoría y corrida real (D1)» | 10 |
  | `RELEASING.md`: matriz, `-m cronometrado`, `uv lock --check`, versión de uv (§19 fila 8) | 8 |
  | `CITATION.cff` 0.9.0 y bump en los tres sitios (cuatro con el lock) | 4 |
  | Decisión del cierre de §16 (D n+25, G n+19) | 2, 3, 11 |
  | §16 punto por punto, §19 al día, PR con base `feat/ola2-auditor` | 11 |

  Lo que los planes dejaron a I: A, comprobación real del arquitecto (Tarea 0, Step 4, y cuerpo de la PR); C, «doble 20 %» (ya quitado por C del README y AGENTS; I lo quita de la arquitectura y lo fija por test); D, `prisma-ia-origen` en el CHANGELOG y la propuesta del doble (Tareas 2 y 9); E, `risk_of_bias.md` conserva el nombre (Tarea 5, fila 65) y GRADE fuera (Tareas 5 y 6, fijado por test); G₂, el cierre de §16 por CLI y README/AGENTS/arquitectura con la estructura del auditor y `revisia deposit` (Tareas 2, 3, 5 y 6).
- **Líneas verificadas contra `c1af7c3` (2026-10-19):** `pyproject.toml:7,10,45`; `revisia/__init__.py:12`; `CITATION.cff:22-23,27-39`; `.env.example:57-62`; `uv.lock:2040-2054,2189-2190,2239,2273`; `revisia/rag/store.py:1-6,30-51`; `revisia/rag/__init__.py:1,6,12`; `revisia/agents/verificador.py:22` (único usuario de `semantic_similarity`); `revisia/llm/providers/fake.py:82-89`; `revisia/agents/reporte.py:20-60`; `revisia/orchestration/pipeline.py:609`; `revisia/cli.py:527-548,616-653`; `revisia/audit/__init__.py:70-102` (21 checks); `README.md:13-14,39-48,54-55,65,74-86,90-104,117-123,196-198,226-235,251-255,282-324,370-373,394-438,475-477,496-516,522,538-543`; `AGENTS.md:26-69`; `docs/arquitectura.md:15-81`; `docs/benchmark-cribado.md:1-87`; `docs/metodologia/README.md:1-32`; `docs/auditoria/2026-09-03-auditoria-completa.md:86-176,205-266`; `RELEASING.md:1-35`; `CHANGELOG.md:7-9,245,739-740`; `tests/test_entregable_honesto.py:250-255`; `tests/hitl_helpers.py:25-125`; `tests/conftest.py:75-240`; `tests/fakes.py:153-165`. Lo que las pistas cambian se toma de sus bloques Interfaces y de sus tareas de integración.
- **Consistencia de nombres:** `_texto`/`ROOT` (Tarea 5) los usan las Tareas 6–10; `AVISOS_DEL_CIERRE`, `protocolo_cierre`, `correr_por_cli` (Tarea 3) solo los usa la Tarea 3 y la 11 los ejecuta; `editar_campo`, `editar_dominio`, `rescatar_con_texto`, `EDICION_DE_CAMPO`, `EDICION_DE_DOMINIO`, `protocolo_benchmark`, `write_run_v08` son los nombres de los planes C, E, F y G.
- **Review Focus:** las cinco líneas tienen test en su tarea (4 y 9; 1 y 9; 2; 2; 6).
- **Proporción:** los bloques de código son tests, el texto de «Cambios incompatibles», las filas de §19 y comandos de verificación; ninguna función de producción tiene cuerpo (la de la Tarea 2 se describe por su contrato y su texto exacto).
- **Revisión independiente (2026-10-19) incorporada:** B1 (`protocolo_benchmark` se importa de `conftest`), B2 (CI en PR apiladas condicionado a la decisión del orquestador sobre H; fila I-17), B3 (la vía (b) usa `corrida_ola2_completa` y `test_frontera_de_la_ola_2_completa_es_apta`; fila n+19 de G). I1 (Step 0a con el inventario antes de la puerta; el `FakeProvider` real corre en muchas corridas de la suite; caso `embedder`; fila I-15), I2 (incompatibles ampliados y test con `MIN_CLI_VERSION`, `allowlist`, `funnel.png`, `embedder`; fila I-18), I3 (F 30 filas, G 23), I4 (`benchmarks/<slug>-<panel.name>/` fijado por test), I5 (`grep -rni`, `embed.py:7`), I6 (cobertura en dos pasadas con `--cov-append`), I7 (`SECURITY.md`; fila I-16), I8 (`base=aceptar_lo_obligatorio`, `flag_review`, `screening_ft/rescues/` retenido). Menores: `hitl_helpers.py` de 125 líneas, `uvx uv@0.11.26 lock --check`, `emit_attempt`, tests de documentación menos frágiles (grafía «AMSTAR 2», «Ubuntu y Windows», sin depender de saltos de línea, temas del CHANGELOG precisos), `### Removed` y `### Documentación` ubicadas, `date-released` en el checklist, ayudantes de la Tarea 3 en código, rojo por comportamiento y `AVISOS_DEL_CIERRE` aprobados aviso por aviso.
