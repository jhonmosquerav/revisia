# Ola 2 · PR-G `feat/ola2-auditor` (el auditor verifica lo que la Ola 2 afirma) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `revisia audit` compruebe, con evidencia en disco, cada afirmación nueva de la Ola 2 (relaciones 19–31 de §4.3: procedencia aplicada, diarios con fallo, texto completo y extracción, RoB por herramienta, verificación por juez, meta-análisis ligado a los incluidos, depósito y benchmark), que declare no publicable una corrida 0.8 (D12), una `existence`/`embedder` (D2) o una de benchmark (D23), que una copia de depósito sin textos completos audite con el mismo veredicto que su corrida (D17), y que ningún módulo del auditor supere 900 líneas (D26).

**Architecture:** Dos fases sobre la misma rama. **G₁** arranca desde PR-0 en paralelo con A, B, C, D, E₁ y F₁: primero parte `checks_flow.py`, `checks_hitl.py` y `artifacts.py` sin tocar una línea de lógica (los cuerpos se mueven tal cual; un script compara el AST), después añade el check `environment` (D12, relaciones 19-parcial y 20-parcial) y `revisia deposit` con su check `deposit` (D17, relación 30). Como el pipeline no escribe `environment` hasta PR-A, G₁ instala en los tests un andamio que lo inyecta en las corridas reales de la suite; G₂ lo retira. **G₂** rebasa sobre PR-F (con A–F ya en la pila) y añade o cambia los checks de §11.2 que necesitan los artefactos v2 reales, `derive_state` con `kind: benchmark` y los tests de frontera de §16.

**Tech Stack:** Python 3.13 (la suite también en 3.11/3.12 desde PR-H), Pydantic v2, PyYAML, pytest + pytest-xdist, ruff + black (línea 100), uv, `argparse` (CLI), `shutil`/`hashlib` (depósito).

**Spec:** `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`: §11 (esta PR), D12, D17, D23, D26, §4.1, §4.2 (`DepositInfo`, `Environment`, `RunInfo` v2), §4.3 relaciones 19, 20 y 30, §15 (topología), §16 (método) y **§19 filas 1–8** (vinculantes; la 1 dice que el auditor reconoce una corrida 0.8 por la ausencia de `environment` y de `outcome`/`attempt`, no por `schema_version`). Plan del que se importan las firmas: `docs/superpowers/plans/2026-10-18-ola2-pr0-contratos.md` (Tarea 5: `Environment`, `RunInfo.kind/environment`, `DepositInfo`, `DepositSource`, `WithheldDir`, `WithheldFile`, `DEPOSIT_FILE`, `WITHHELD_DIRS`, `RunKind`; Tarea 10: `tool_spec_fingerprint`). Referencia del auditor anterior: `docs/superpowers/plans/2026-10-04-ola-1-c-auditor.md`.

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes, detalles del informe y commits **en español**, con el tono del repo; las docstrings explican el porqué y citan la decisión («D12», «D17», «D26») o la relación («relación 30»).
- Estilo: `ruff` (`E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100), limpios en cada commit. `from __future__ import annotations` en todo módulo nuevo, también en `tests/`.
- **El auditor es fail-closed** (spec 2026-10-04 §9.2): ningún check lanza; todo valor leído de un artefacto entra en un detalle acotado con `short_text`/`short_repr`; las listas se acotan (`_limitar`, `_ids`, `sufijo_mas`); un N/A solo con algún FAIL. Un artefacto hostil (raíz de lista, cadena de 1 MB, tipos cambiados) da FAIL con detalle acotado, nunca «error interno».
- **D26:** el primer commit de la PR es la partición, sin cambio de lógica y con la suite en verde; `CHECKS` no cambia en ese commit; ningún módulo de `revisia/audit/` supera **900** líneas (`len(text.splitlines())`), y un test lo fija para G₂.
- **D12, texto literal** del FAIL de `environment` para una corrida sin `environment`: `anterior a la Ola 2 (motor < 0.9): sin procedencia aplicada ni verificación por juez; regenera la corrida con el motor actual` (seguido de `.` en el detalle, como `LEGACY_RUN`).
- **§19 fila 1:** una corrida 0.8 se reconoce por la ausencia de `environment` en `run.json` (y, en G₂, de `outcome`/`attempt` en las llamadas crudas), nunca comparando `schema_version`.
- Tests offline y deterministas; ninguno invoca `claude`, APIs ni WeasyPrint.
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"` y después `uv run pytest -p no:cacheprovider -m cronometrado`; lint, `uv run ruff check . && uv run ruff format --check . && uv run black --check .`.
- Commits pequeños, al menos uno por tarea, con prefijo convencional y terminados con `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- **Los implementadores no tocan** `CHANGELOG.md`, `README.md`, `AGENTS.md`, `docs/auditoria/`, `docs/arquitectura.md` ni el spec (§15): el integrador los actualiza al cerrar la PR (después de G₂).
- `cli.py` lo tocan también F (`benchmark`, `benchmark-report`) y A (§15): G solo añade `_cmd_deposit` (función nueva, justo antes de `_cmd_brain`), un bloque de subparser justo después del de `export` en `build_parser` y una línea de despacho justo después de la de `export` en `main`. F₁ ancla lo suyo tras `_cmd_audit` (plan PR-F, Tarea 9), así que G ancla en `export` para no dar trozos contiguos. Nada más de `cli.py`.
- No tocar `revisia/orchestration/` ni `revisia/schemas/` (son de A, C, D, E, F y PR-0); G₁ solo consume sus modelos.
- Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base.

## Review Focus

Entradas que el spec implica y que ninguna tarea probaría sin estas líneas; cada una tiene su test en la tarea dueña:

1. **Un `deposit.json` o un `environment` hostil** (raíz de lista, `packages` de 1 MB, `withheld` con `..` o rutas absolutas, `files` que no es lista) debe dar FAIL con detalle acotado, no «error interno» ni un detalle de megabytes. → Tareas 4 (`test_environment_hostil_falla_acotado`) y 6 (`test_deposit_json_hostil_falla_acotado`).
2. **Un destino de depósito dentro de la propia corrida, ya ocupado o una corrida sin manifiesto** debe fallar **antes** de copiar nada (sin copia a medias que alguien deposite por error). → Tarea 5 (`test_make_deposit_rechaza_sin_copiar_nada`).
3. **Rutas de Windows:** los `relpath` de `deposit.json` van siempre con `/` y relativos a la corrida, aunque el depósito se haga en Windows; el auditor no acepta `\`. → Tarea 5 (`test_make_deposit_lista_los_retenidos_con_sus_hashes`) y Tarea 6 (`..`/absolutas).
4. **Un rescate humano en subcarpeta** (`screening_ft/rescues/sub/a.pdf`) también se retiene y se lista; un fichero que reaparece en cualquier nivel de una carpeta retenida es FAIL. → Tareas 5 y 6.
5. **Una corrida en pausa** (sin `manifest.yml` todavía) no puede dar FAIL en `environment` por no tener con qué comparar, y `"environment": null` explícito cuenta como ausente. → Tarea 4 (`test_environment_en_pausa_no_exige_el_manifiesto`, `test_environment_null_es_ausente`).

---

## Topología de ejecución (subagentes)

G₁ se ejecuta en el worktree `C:\revisia-wt\g` (rama `feat/ola2-auditor`, creada desde `feat/ola2-contratos` en la Tarea 17 de PR-0), en secuencia, tarea a tarea. Al terminar G₁ la rama **no** se publica como PR: espera a PR-F, se rebasa sobre ella (Tarea G2.0) y continúa con G₂ (su tabla de topología va al principio de la fase). La PR-G se abre al final de G₂ (Tarea G2.11) con base `feat/ola2-meta-benchmark` (§15).

| Tarea | Fichero(s) | Depende de |
|---|---|---|
| 1 | worktree y línea base | PR-0 cerrada |
| 2 | partición D26: `revisia/audit/*` (8 módulos nuevos), 5 tests con imports redirigidos, `tests/test_audit_paquete.py` | 1 |
| 3 | andamio de `environment` y corrida 0.8: `tests/conftest.py`, `tests/audit_fixtures.py`, `tests/test_audit_fixtures.py` | 2 |
| 4 | check `environment`: `revisia/audit/checks_environment.py`, `revisia/audit/__init__.py`, `tests/test_audit_entorno.py` | 3 |
| 5 | `make_deposit`: `revisia/exports/deposit.py`, `tests/test_deposito.py` | 1 |
| 6 | check `deposit` y relación 7 por hash: `revisia/audit/checks_deposit.py`, `checks_flow.py`, `relations.py`, `__init__.py`, `tests/test_audit_deposito.py` | 4, 5 |
| 7 | `revisia deposit`: `revisia/cli.py`, `tests/test_cli_deposit.py` | 5, 6 |

**Ciclo por tarea (§16):** implementador (subagente nuevo, TDD estricto) → revisor (subagente nuevo: primero cumplimiento del spec y de este plan, después calidad) → correcciones. Las desviaciones descubiertas en revisión se corrigen y se anotan para §19 (las añade el integrador al cerrar la PR), no se consultan, salvo que cambien una decisión D1–D6. **El merge lo decide el arquitecto.**

---

## Fase G₁ (desde PR-0)

### Mapa de la partición (D26)

Números de línea de `main` @ `c1af7c3` (idénticos en PR-0, que no toca `revisia/audit/`). Cada rango se mueve **tal cual**, con sus comentarios previos; solo cambian los `import` de cabecera y las docstrings de módulo (se reparten los párrafos de la original). Las cuentas son estimaciones del cuerpo movido + cabecera.

**Por qué hay módulos fuera de la lista de D26.** Los ayudantes compartidos (`_Relations`, `_ids`, `_limitar`, `_seccion`, `_artefacto`, `_ola1`, `included_ids`, las rutas) no pueden quedarse en `checks_flow.py`: `collect_relations` (allí) llama a `_diarios`, `_consolidados`, `_meta_analisis`, `_metrics` y `_copies`, y esos módulos necesitan los ayudantes, así que habría un import circular. Van a `relations.py`. En la familia HITL los ayudantes compartidos (`de_la_decision_efectiva`, `indice_de_bandera`, `_gates_pendientes`…) se quedan en `checks_ledger.py`, que es la raíz de la familia y no importa de las otras tres. Y `artifacts.py` (919 líneas, que §2 no menciona) también pasa el límite: sus ayudantes de texto acotado van a `text.py`.

`revisia/audit/checks_flow.py` (2 190 → ≈ 810 líneas) se reparte así:

| Destino | Rangos de `checks_flow.py` | Contenido |
|---|---|---|
| `relations.py` (nuevo, ≈ 330) | 126-138, 140-148, 156-164, 188-191, 226-385, 574-625, 657-696, 1797-1798 | rutas (`TA`…`TEXTOS`, `SCREENING_JOURNAL`, `LLM_CALLS`, `DEDUP_RECORDS`, `RETRIEVAL_JOURNAL`), `_PASAN_TA`, límites `_MAX`…`_LIMITE_ERROR`, `_SUFIJO_MAS`, `_repartir`, `_acotar_item`, `_limitar`, `_ids`, `_valor`, `_n`, `_primera_diferencia`, `_misma_secuencia`, `_ola1`, `_ids_incluidos`, `included_ids`, `_requiere_doble_extraccion`, `_recuperacion_con_diario`, `_cribado_con_trabajo`, `_Relation`, `_Relations`, `_close`, `_ratio`, `_screeners`, `_seccion`, `_artefacto`, `_normalizar` |
| `checks_flow.py` (≈ 810) | 628-654, 699-1246, 1949-1966, 2004-2113 | `_Csv`, `_read_csv`, embudo (`_funnel`, `_conteos_ola1`, `_cribado_ta`, `_cribado_ta_ola1`, `_busqueda_y_dedup`, `_diario_dentro_del_dedup`, `_texto_completo_ola1`, `_recuperacion`, `_textos_en_cache`, `_propuestas_ft`, `_lista_16b`, `_texto_completo`), incluidos (`_included_artifacts`, `_herramienta_rob`, `_doble_extraccion`, `_total_excluidos`), `_csv`, `_diagrama_prisma`, `collect_relations`, `check_arithmetic`, `check_exclusions` |
| `checks_journals.py` (nuevo, ≈ 560) | 153-155, 1249-1342, 1494-1503, 1506-1794, 1801-1840, 1969-2001 | `_CAMPOS_HUMANOS`, `_calls` (llamadas), `_clave`, `_sin_humanos`, `_Llamadas`, `_llamadas`, `_llamadas_esperadas`, `_diarios`, `_RevisionDiario`, `_revisar_diario`, `_Diario`, `_diario`, `_contra_diario` (relación 12), `_consolidado`, `_consolidados` (13), `_documento`, `_doble_extraccion_en_diario` |
| `checks_meta.py` (nuevo, ≈ 260) | 149-151, 429-491, 1843-1946, 2161-2190 | `_META_SEGUN_ENTORNO`, `_EfectosProtocolo`, `_EFECTOS_LEIDOS`, `_efectos_del_protocolo`, `_leer_efectos_del_protocolo`, `_meta_distinto`, `_meta_analisis`, `_P_SEGUN_ENTORNO`, `_meta_entregables`, `_meta_sin_incluidos` |
| `checks_artifacts.py` (nuevo, ≈ 445) | 139, 166-187, 192-223, 388-426, 494-571, 1345-1491, 2116-2158 | `GOLD_Y_METRICAS`, `STAGE_ARTIFACTS`, `STAGE_ARTIFACTS_OLA1`, `CONDITIONAL_ARTIFACTS`, `MANIFEST_COPIES`, `COPIAS_SIEMPRE_ESCRITAS`, `DELIVERABLE_FILES`, `_GoldProtocolo`, `_gold_del_protocolo`, `_journals_ola1`, `check_stage_artifacts`, `_gold_anclado`, `_metrics`, `_matriz_desde_gold`, `_copies`, `check_deliverable`, `_revision_vacia` |

`_metrics`/`_gold_anclado`/`_matriz_desde_gold` y `_copies` van a `checks_artifacts.py` y no a `checks_flow.py` por tamaño: con ellos `checks_flow.py` quedaría en ≈ 930. Comparten con `check_stage_artifacts` el ancla del gold (`_gold_del_protocolo`) y la lista de copias del manifiesto, así que es su sitio natural fuera del embudo.

Imports cruzados resultantes (sin ciclos: `relations` ← todos; `checks_meta` ← `checks_artifacts`, `checks_flow`; `checks_journals` ← `checks_flow`; `checks_artifacts` ← `checks_flow`):

| Módulo | Importa de módulos nuevos |
|---|---|
| `checks_flow` | `relations`: `AGREEMENT, ASSESSMENTS, CSV, DEDUP_RECORDS, DEDUP_REPORT, EFECTOS_PROTOCOLO, EXCLUDED, EXCLUSIONS, EXTRACTIONS, FT, PRISMA_FLOW, RETRIEVAL, SCREENING_JOURNAL, SEARCH_RECORDS, TA, TEXTOS, _LIMITE_ERROR, _PASAN_TA, _Relation, _Relations, _artefacto, _ids, _ids_incluidos, _limitar, _misma_secuencia, _n, _normalizar, _ola1, _requiere_doble_extraccion, _screeners, _seccion, _valor, included_ids`; `checks_journals`: `_calls, _consolidados, _diarios`; `checks_meta`: `_efectos_del_protocolo, _meta_analisis`; `checks_artifacts`: `_copies, _metrics` |
| `checks_journals` | `relations`: `AGREEMENT, ASSESSMENTS, DOCUMENTO, EXTRACTIONS, FT, LLM_CALLS, RETRIEVAL, TA, VERIFICATION, _LIMITE_ID, _Relations, _artefacto, _ids, _n, _normalizar, _ola1, _screeners, _seccion, included_ids` |
| `checks_meta` | `relations`: `EFECTOS_PROTOCOLO, META, METAFOR_CSV, META_MD, _LIMITE_ERROR, _Relations, _ids, _normalizar, _ola1, included_ids` |
| `checks_artifacts` | `relations`: `AGREEMENT, ASSESSMENTS, EFECTOS_PROTOCOLO, EXCLUSIONS, EXTRACTIONS, FT, GOLD, GOLD_PROTOCOLO, LLM_CALLS, META, METAFOR_CSV, META_MD, METRICS, RETRIEVAL, RETRIEVAL_JOURNAL, SCREENING_JOURNAL, TA, _LIMITE_ERROR, _Relations, _close, _cribado_con_trabajo, _ids, _limitar, _ola1, _ratio, _recuperacion_con_diario, _requiere_doble_extraccion, _seccion, _valor, included_ids`; `checks_meta`: `_efectos_del_protocolo, _meta_sin_incluidos` |

La docstring de 81 líneas de `checks_flow.py` se reparte por párrafos: 3-9, 31-35 y 41-51 se quedan en `checks_flow.py`; 11-19 y 21-29 van a `relations.py`; 37-39 y 53-65 a `checks_journals.py`; 67-70 a `checks_artifacts.py`; 72-81 a `checks_meta.py`. La primera línea de cada módulo dice qué familia contiene y cita D26.

`revisia/audit/checks_hitl.py` (1 389 → ≈ 330 líneas):

| Destino | Rangos de `checks_hitl.py` | Contenido |
|---|---|---|
| `checks_ledger.py` (nuevo, ≈ 390) | 55-64, 67-73, 88-364, 372-376, 388-412 | `_NA_LEDGER`, límites, `_ETAPAS_DE_CRIBADO`, `DECISIONES_DE_CRIBADO`, `ACTOR_POR_DEFECTO`, `CONSEJO_ACTOR`, `_BANDERA`, `indice_de_bandera`, `_ola1`, `_forzado`, `autonomia_efectiva_de_la_corrida`, `_limitar`, `_ids`, `_clave`, `_hash`, `_relacion_16`, `_autonomia_del_manifiesto`, `_NA_SIN_GATES_DECIDIDOS`, `_sin_gates_decididos`, `check_ledger`, `_detenida`, `_gates_pendientes`, `_nota_pendientes`, `_listar`, `de_la_decision_efectiva` |
| `checks_hitl.py` (≈ 330) | 367-369, 379-385, 415-678 | `_orden_etapa`, `_excluded_human`, `_etiquetas_de_cribado`, `_es_exclusion_humana`, `_etiquetas_por_registro`, `_reglas_ft`, `check_hitl` |
| `checks_request_hash.py` (nuevo, ≈ 620) | 65-66, 74-85, 684-1223 | `ARTEFACTOS_APROBADOS`, `_BYTES_POR_CARACTER`, `_BYTES_MINIMOS`, `_ALIAS_DESMESURADOS`, `_NO_ES_JSON`, `_CLAVES_DEL_MOTOR`, `_SinEtiquetar`, `_caracteres_json` … `_atada`, `check_request_hash` |
| `checks_final_gate.py` (nuevo, ≈ 200) | 1229-1389 | `_relacion_17`, `_ids_numericos`, `_sin_terminar`, `_solicitud_vigente`, `check_final_gate` |

Imports cruzados: `checks_hitl`, `checks_request_hash` y `checks_final_gate` importan de `checks_ledger` exactamente los nombres que usan (`checks_hitl`: `ACTOR_POR_DEFECTO, CONSEJO_ACTOR, DECISIONES_DE_CRIBADO, _ETAPAS_DE_CRIBADO, _NA_LEDGER, _gates_pendientes, _ids, _limitar, _listar, _nota_pendientes, _ola1, autonomia_efectiva_de_la_corrida, de_la_decision_efectiva`; `checks_request_hash`: `DECISIONES_DE_CRIBADO, _NA_LEDGER, _gates_pendientes, _ids, _limitar, _nota_pendientes, _ola1, de_la_decision_efectiva, indice_de_bandera`; `checks_final_gate`: `ACTOR_POR_DEFECTO, CONSEJO_ACTOR, _MAX_LISTADOS, _NA_LEDGER, _detenida, _limitar, _ola1, de_la_decision_efectiva, indice_de_bandera`). Las rutas `AGREEMENT, ASSESSMENTS, DOCUMENTO, EXTRACTIONS, FT, TA, VERIFICATION` que hoy vienen de `checks_flow` (`checks_hitl.py:32-40`) pasan a venir de `relations`. La docstring (líneas 1-21) se reparte: el párrafo del ledger no confiable a `checks_ledger.py`; el de la Ola 1 y `hitl` a `checks_hitl.py`; el de `request_hash` (relación 15) a `checks_request_hash.py`; `checks_final_gate.py` lleva una propia de dos líneas (gate final y relación 17).

`revisia/audit/artifacts.py` (919 → ≈ 820 líneas): las líneas 249-324 (`_SHORT_REPR`, `_NO_VISIBLES`, `_visible`, `_acotar`, `short_repr`, `short_text`) y 346-370 (`sufijo_mas`, `format_validation`) van a `revisia/audit/text.py` (nuevo, ≈ 120). `artifacts.py` las **reexporta** (`from revisia.audit.text import format_validation, short_repr as short_repr, short_text, sufijo_mas`; el alias redundante marca la reexportación de `short_repr`, que `artifacts.py` ya no usa) y pierde los imports `reprlib`, `unicodedata` y `date` (líneas 24, 25, 27).

**Imports de otros módulos y de los tests: se redirigen, no se reexportan** (salvo `artifacts.py`). Razón: reexportar desde `checks_flow`/`checks_hitl` exigiría imports sin uso con `noqa` y dejaría dos sitios para el mismo nombre; los usos son pocos y cambiar la línea de import no cambia lógica. En `artifacts.py` se reexporta porque `short_text` y compañía se importan desde `artifacts` en todos los `checks_*` y en `tests/test_audit_infra.py:30-44`. Lista completa:

| Fichero | Hoy | Pasa a |
|---|---|---|
| `revisia/audit/__init__.py:35-42` | `checks_flow, checks_hitl, …` | + `checks_artifacts, checks_final_gate, checks_ledger, checks_request_hash` |
| `revisia/audit/__init__.py:82-89` | `checks_hitl.check_ledger/…`, `checks_flow.check_stage_artifacts`, `check_deliverable` | `checks_ledger.check_ledger`, `checks_hitl.check_hitl`, `checks_request_hash.check_request_hash`, `checks_final_gate.check_final_gate`, `checks_artifacts.check_stage_artifacts`, `checks_flow.check_arithmetic`, `checks_flow.check_exclusions`, `checks_artifacts.check_deliverable` |
| `revisia/audit/checks_quality.py:29` | `from revisia.audit.checks_flow import TA, included_ids` | `from revisia.audit.relations import TA, included_ids` |
| `revisia/audit/checks_quality.py:35-40` | `from revisia.audit.checks_hitl import (ACTOR_POR_DEFECTO, CONSEJO_ACTOR, de_la_decision_efectiva, indice_de_bandera)` | `from revisia.audit.checks_ledger import (…)` |
| `tests/test_audit_flujo.py:33` | `from revisia.audit.checks_flow import _limitar, collect_relations` | `… checks_flow import collect_relations` + `from revisia.audit.relations import _limitar` |
| `tests/test_auditor_meta_y_estados.py:39` | `… checks_flow import collect_relations, included_ids` | `… checks_flow import collect_relations` + `… relations import included_ids` |
| `tests/test_audit_hitl.py:17` | `… checks_hitl import check_final_gate, de_la_decision_efectiva` | `… checks_final_gate import check_final_gate` + `… checks_ledger import de_la_decision_efectiva` |
| `tests/test_audit_hitl_registro.py:55` | `… checks_hitl import _hash_acotado, autonomia_efectiva_de_la_corrida` | `… checks_ledger import autonomia_efectiva_de_la_corrida` + `… checks_request_hash import _hash_acotado` |

`tests/test_audit_aritmetica_ola1.py:38` (`collect_relations`) no cambia. Ningún test hace `monkeypatch` sobre `checks_flow` ni `checks_hitl` (verificado con `grep`); `tests/test_audit_infra.py:295` parchea `artifacts_mod._YAML_LOADER`, que se queda en `artifacts.py`.

Los nombres con `_` se importan entre módulos del paquete tal cual (ruff no tiene activa ninguna regla contra importar privados); renombrarlos sería cambiar líneas de lógica.

---

### Tarea 1: Worktree y línea base (controlador)

**Files:** ninguno.

- [ ] **Step 1: Comprobar el worktree** que creó PR-0 (Tarea 17, Step 6).

```bash
cd C:/revisia-wt/g && git status && git log --oneline -1
```

Expected: rama `feat/ola2-auditor`, limpia, en la punta de `feat/ola2-contratos`. Si no existe: `git -C C:/revisia worktree add C:/revisia-wt/g -b feat/ola2-auditor feat/ola2-contratos`.

- [ ] **Step 2: Entorno y línea base.**

```bash
uv sync --extra dev --extra search --extra meta
uv run pytest -p no:cacheprovider --collect-only -q | tail -1
uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado
wc -l revisia/audit/*.py
```

Expected: la suite de PR-0 en verde (anotar el recuento); `checks_flow.py 2190`, `checks_hitl.py 1389`, `artifacts.py 919` y el resto ≤ 492.

---

### Tarea 2: Partición del auditor sin cambio de lógica (D26)

**Files:**
- Create: `revisia/audit/relations.py`, `checks_journals.py`, `checks_meta.py`, `checks_artifacts.py`, `checks_ledger.py`, `checks_request_hash.py`, `checks_final_gate.py`, `text.py`.
- Modify: `revisia/audit/checks_flow.py` (entero, según el mapa), `revisia/audit/checks_hitl.py` (entero), `revisia/audit/artifacts.py:24-27,249-324,346-370`, `revisia/audit/__init__.py:21-25,35-42,82-89` (dentro de `CHECKS`, 70-102), `revisia/audit/checks_quality.py:29,35-40`.
- Modify (solo imports): `tests/test_audit_flujo.py:33`, `tests/test_auditor_meta_y_estados.py:39`, `tests/test_audit_hitl.py:17`, `tests/test_audit_hitl_registro.py:55`.
- Test: `tests/test_audit_paquete.py` (añadir).

**Interfaces:**
- Consumes: nada nuevo.
- Produces: los módulos del mapa, con los nombres de hoy. Para las tareas siguientes y para G₂: `revisia.audit.relations` (rutas, `_Relations`, `_ids`, `_limitar`, `_seccion`, `_artefacto`, `_ola1`, `included_ids`, `TEXTOS`, `RETRIEVAL`), `revisia.audit.checks_ledger` (`de_la_decision_efectiva`, `indice_de_bandera`, `ACTOR_POR_DEFECTO`, `CONSEJO_ACTOR`, `autonomia_efectiva_de_la_corrida`), `revisia.audit.text` (`short_text`, `short_repr`, `sufijo_mas`, `format_validation`; también accesibles desde `artifacts`). Constante de test `CHECKS_ESPERADOS` en `tests/test_audit_paquete.py`, que las Tareas 4 y 6 amplían.

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_audit_paquete.py` (imports: `from revisia.audit import CHECKS`):

```python
# ── D26: el auditor partido en módulos revisables (spec 2026-10-18 §11.1) ──

LIMITE_LINEAS = 900

# (id, ítem, etapa, módulo, función): el orden y los valores de `CHECKS` no cambian con la
# partición; solo el módulo donde vive cada función. Las Tareas 4 y 6 de PR-G añaden filas.
CHECKS_ESPERADOS = [
    ("manifest", "PRISMA 27 / trAIce M2", "reporte", "checks_provenance", "check_manifest"),
    ("provenance", "PRISMA 27 / trAIce M2", "reporte", "checks_provenance", "check_provenance"),
    ("schemas", "PRISMA 27 / trAIce M5", None, "checks_provenance", "check_schemas"),
    (
        "protocol_snapshot",
        "PRISMA 24b / trAIce M1",
        "protocolo",
        "checks_provenance",
        "check_protocol_snapshot",
    ),
    ("prompts", "trAIce M6", "reporte", "checks_provenance", "check_prompts"),
    ("timing", "PRISMA 27 / trAIce M2", None, "checks_timing", "check_timing"),
    ("ledger", "trAIce M8 / PRISMA 8", None, "checks_ledger", "check_ledger"),
    ("hitl", "trAIce M8/R1 / PRISMA 8", None, "checks_hitl", "check_hitl"),
    ("request_hash", "trAIce M8", None, "checks_request_hash", "check_request_hash"),
    ("final_gate", "trAIce M8", None, "checks_final_gate", "check_final_gate"),
    ("stage_artifacts", "PRISMA 16/27", None, "checks_artifacts", "check_stage_artifacts"),
    ("arithmetic", "PRISMA 16 / trAIce R1", "reporte", "checks_flow", "check_arithmetic"),
    ("exclusions", "trAIce R1", "screening_ft", "checks_flow", "check_exclusions"),
    ("deliverable", "PRISMA 16/16b/17/18/27", "reporte", "checks_artifacts", "check_deliverable"),
    ("gold", "trAIce M9/R2", "screening_ta", "checks_quality", "check_gold"),
    (
        "thresholds",
        "trAIce M9/R2 / PRISMA 8, 24c",
        "screening_ta",
        "checks_quality",
        "check_thresholds",
    ),
    ("grounding", "trAIce M8/M9", "sintesis", "checks_quality", "check_grounding"),
    ("search_log", "PRISMA-S 1/8/13/15", "busqueda", "checks_search", "check_search_log"),
    ("search_window", "PRISMA-S 9/13", "busqueda", "checks_search", "check_search_window"),
    ("registration", "PRISMA 24a", None, "checks_search", "check_registration"),
    ("response_overlap", "trAIce M2", "reporte", "checks_timing", "check_response_overlap"),
]


def test_ningun_modulo_del_auditor_supera_900_lineas() -> None:
    carpeta = Path(audit.__file__).parent
    largos = {
        p.name: len(p.read_text(encoding="utf-8").splitlines()) for p in carpeta.glob("*.py")
    }
    assert {nombre: n for nombre, n in largos.items() if n > LIMITE_LINEAS} == {}


def test_checks_no_cambian_y_cada_uno_vive_en_su_modulo_d26() -> None:
    actual = [
        (s.check_id, s.item_ref, s.stage, s.fn.__module__.rsplit(".", 1)[-1], s.fn.__name__)
        for s in CHECKS
    ]
    assert actual == CHECKS_ESPERADOS
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_paquete.py -v`
Expected: FAIL; el primero lista `{'artifacts.py': 919, 'checks_flow.py': 2190, 'checks_hitl.py': 1389}`, el segundo da `checks_hitl`/`checks_flow` donde se espera `checks_ledger`/`checks_artifacts`…

- [ ] **Step 3: Partir `checks_flow.py`** según el mapa: crear `relations.py`, `checks_journals.py`, `checks_meta.py` y `checks_artifacts.py` con los rangos indicados (cortar y pegar, cabecera de imports nueva, docstring repartida), dejar en `checks_flow.py` solo lo suyo, redirigir `checks_quality.py:29`, `checks_hitl.py:32-40` y los dos tests de flujo. `ruff check --fix` ordena los imports; ningún cuerpo se toca.

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" tests/test_audit_*.py tests/test_auditor_meta_y_estados.py tests/test_pipeline_fake.py`
Expected: PASS (los dos tests nuevos siguen en rojo por `checks_hitl.py` y `artifacts.py`).

- [ ] **Step 4: Partir `checks_hitl.py`** según el mapa: crear `checks_ledger.py`, `checks_request_hash.py`, `checks_final_gate.py`; redirigir `checks_quality.py:35-40`, `__init__.py` y los dos tests HITL.

- [ ] **Step 5: Partir `artifacts.py`**: crear `text.py` con las líneas 249-324 y 346-370 (más sus imports `reprlib`, `unicodedata`, `date`, `ValidationError`) y reexportar desde `artifacts.py`. Actualizar la docstring de `__init__.py:21-25` («Estructura»: los módulos de D26, `relations` y `text`).

- [ ] **Step 6: Verificar que ningún cuerpo cambió** (script de un solo uso, no se commitea): compara el AST de cada definición de nivel de módulo de los tres ficheros originales con alguna definición homónima de los módulos nuevos.

```bash
uv run python - <<'EOF'
import ast, pathlib, subprocess

def defs(src):
    out = {}
    for n in ast.parse(src).body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out[n.name] = ast.dump(n)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            t = n.targets[0] if isinstance(n, ast.Assign) else n.target
            out[ast.unparse(t)] = ast.dump(n)
    return out

despues = {}
for p in pathlib.Path("revisia/audit").glob("*.py"):
    for k, v in defs(p.read_text(encoding="utf-8")).items():
        despues.setdefault(k, []).append(v)
distintos = []
for f in ("checks_flow.py", "checks_hitl.py", "artifacts.py"):
    viejo = subprocess.check_output(["git", "show", f"HEAD:revisia/audit/{f}"], encoding="utf-8")
    distintos += [(f, k) for k, v in defs(viejo).items() if v not in despues.get(k, [])]
print("cuerpos distintos:", distintos)
EOF
```

Expected: `cuerpos distintos: []`.

- [ ] **Step 7: Run de todo**

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado && uv run ruff check . && uv run ruff format --check . && uv run black --check . && wc -l revisia/audit/*.py`
Expected: PASS con el mismo recuento que la línea base más 2; lint limpio; ningún módulo > 900 (`checks_flow.py` ≈ 810).

- [ ] **Step 8: Commit** (un solo commit: es «el primer commit de PR-G», D26)

```bash
git add revisia/audit tests/test_audit_paquete.py tests/test_audit_flujo.py tests/test_auditor_meta_y_estados.py tests/test_audit_hitl.py tests/test_audit_hitl_registro.py
git commit -m "refactor(audit): partición D26 sin cambio de lógica (flujo, diarios, meta, artefactos; ledger, hitl, request_hash, final_gate; text)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 3: Andamio de `environment` en las corridas de la suite y corrida 0.8

PR-A es quien escribe `run.json.environment` y su copia en el manifiesto (§5.5), y se desarrolla en paralelo. Sin andamio, el check de la Tarea 4 daría FAIL en **todas** las corridas reales de la suite (las de `tests/conftest.py`, `test_pipeline_fake_con_humano_audita_sin_fail`, los escenarios de `test_audit_hitl_registro.py`…) y rompería cientos de aserciones de `publishable`. El andamio emula lo que PR-A hará, solo en los tests y solo en corridas nuevas; G₂ lo retira al rebasar sobre F.

**Files:**
- Modify: `tests/audit_fixtures.py` (añadir al final, sección «Ola 2»; imports de cabecera `importlib.metadata`, `platform`, `revisia.__version__`, `Environment`, `prompt_fingerprint`, `tool_spec_fingerprint`, `utc_now_iso`).
- Modify: `tests/conftest.py` (fixture nueva al final; imports `read_run_info`, `write_run_info`, `entorno_de_prueba`).
- Test: `tests/test_audit_fixtures.py` (añadir).

**Interfaces:**
- Consumes: `Environment` (`revisia.schemas.artifacts`, PR-0 T5), `tool_spec_fingerprint` (`revisia.schemas.rob_tools`, PR-0 T10), `prompt_fingerprint`, `read_run_info`, `write_run_info` (`revisia.orchestration.snapshot:76,84,92`), `RunContext.write_manifest` (`run_context.py:190`), `pipeline_mod.ensure_snapshot` (`pipeline.py:107`, llamada en `:1278`), `editar_llamadas`, `edit_json`, `edit_yaml` (`audit_fixtures.py:86,92,146`).
- Produces (en `tests/audit_fixtures.py`):
  - `CLAVES_RUNMETA_V2: tuple[str, ...] = ("schema_version", "seed_applied", "temperature_applied", "top_p_applied", "schema_sha256", "prompt_template", "prompt_template_sha256", "attempt", "outcome", "effort", "backend_version", "latency_ms", "cost_usd", "model_source")` (los campos que PR-0 T3 añade a `RunMeta`).
  - `entorno_de_prueba() -> Environment`: `engine_version=revisia.__version__`, `python_version=platform.python_version()`, `python_implementation=platform.python_implementation()`, `platform=platform.platform()`, `git_commit="0" * 40`, `git_dirty=False` (así `environment` da PASS y no WARN en `AVISOS_DE_LA_DEMO`), `packages={"pydantic": importlib.metadata.version("pydantic")}`, `prompt_templates={**prompt_fingerprint(), **tool_spec_fingerprint()}`, `created_utc=utc_now_iso()`.
  - `editar_entorno(run_dir: Path, fn: Callable[[dict], Any]) -> None`: aplica `fn` (semántica de `_apply`) al `environment` de `run.json` y al del `manifest.yml` si existe, la misma edición en las dos copias.
  - `write_run_v08(run_dir: Path) -> Path`: convierte **en el sitio** una copia de una corrida real en la forma de una corrida 0.8: quita `environment` y `kind` de `run.json`, `environment` del manifiesto, y las `CLAVES_RUNMETA_V2` de cada llamada en `llm_calls.jsonl`, en las `metas` de los diarios y en `manifest.llm_calls` (con `editar_llamadas`). Devuelve `run_dir`. Las claves se quitan con `del` dentro de una función, nunca con `lambda d: d.pop(...)`: `_apply` (`audit_fixtures.py:74`) sustituiría el documento entero por el mapa que devuelve `pop`.
- Produces (en `tests/conftest.py`): fixture `_andamio_entorno_ola2` (`scope="session"`, `autouse=True`), con `pytest.MonkeyPatch.context()` durante toda la sesión:
  - sustituye `pipeline_mod.ensure_snapshot` por un envoltorio que, **solo si `run.json` no existía antes de la llamada** y el `RunInfo` devuelto tiene `environment is None`, reescribe `run.json` con `write_run_info(run_ctx.run_dir, info.model_copy(update={"environment": entorno_de_prueba()}))` y devuelve la tupla `(snapshot, info)` con ese `info` (la firma de `ensure_snapshot` devuelve `tuple[Path, RunInfo]`, `snapshot.py:106-112`);
  - sustituye `RunContext.write_manifest` por un envoltorio que, si `read_run_info(self.run_dir)` tiene `environment`, pasa `extra={**(extra or {}), "environment": info.environment.model_dump(mode="json")}` con `setdefault` (no pisa un `environment` que el motor ya escriba).
  - Docstring: «ANDAMIO TEMPORAL de PR-G (plan 2026-10-19, Tarea 3): emula PR-A §5.5 en las corridas de la suite para que el check `environment` (D12) no dé FAIL en todas mientras G₁ se desarrolla desde PR-0. Con PR-A en la pila el motor ya escribe `environment` y los envoltorios no hacen nada; G₂ lo retira.» Es de sesión y no de función porque las corridas cacheadas (`_corrida_auditoria`…) se crean en fixtures de sesión, antes de cualquier fixture de función.

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_audit_fixtures.py` (imports de `audit_fixtures`: `CLAVES_RUNMETA_V2, editar_entorno, write_run_v08`; `from revisia.schemas.artifacts import JOURNAL_PATHS, Environment`):

```python
# ── Ola 2: andamio de `environment` (plan PR-G, Tarea 3) y corrida 0.8 ──


def _manifiesto(run: Path) -> dict:
    return yaml.safe_load((run / "manifest.yml").read_text(encoding="utf-8"))


def _run_json(run: Path) -> dict:
    return json.loads((run / "run.json").read_text(encoding="utf-8"))


def test_andamio_escribe_el_mismo_entorno_en_run_json_y_en_el_manifiesto(corrida) -> None:
    entorno = Environment.model_validate(_run_json(corrida)["environment"])
    assert entorno.engine_version == _run_json(corrida)["engine_version"]
    assert (entorno.git_commit, entorno.git_dirty) == ("0" * 40, False)
    assert "rob/RoB2.yml" in entorno.prompt_templates
    assert _manifiesto(corrida)["environment"] == entorno.model_dump(mode="json")


def test_andamio_tambien_en_la_corrida_en_pausa_sin_manifiesto(corrida_en_pausa_ft) -> None:
    assert _run_json(corrida_en_pausa_ft)["environment"] is not None
    assert not (corrida_en_pausa_ft / "manifest.yml").exists()


def test_editar_entorno_edita_las_dos_copias(corrida) -> None:
    editar_entorno(corrida, lambda e: e.update(platform="otra"))
    assert _run_json(corrida)["environment"]["platform"] == "otra"
    assert _manifiesto(corrida)["environment"]["platform"] == "otra"


def test_write_run_v08_quita_entorno_y_campos_v2_de_todas_las_copias(corrida) -> None:
    write_run_v08(corrida)
    assert "environment" not in _run_json(corrida) and "kind" not in _run_json(corrida)
    assert "environment" not in _manifiesto(corrida)
    lineas = [json.loads(x) for x in (corrida / "llm_calls.jsonl").read_text("utf-8").splitlines()]
    metas_diarios = [
        m
        for rel in JOURNAL_PATHS.values()
        if (corrida / rel).exists()
        for x in (corrida / rel).read_text("utf-8").splitlines()
        for m in json.loads(x)["metas"]
    ]
    for llamada in [*lineas, *_manifiesto(corrida)["llm_calls"], *metas_diarios]:
        assert not set(CLAVES_RUNMETA_V2) & set(llamada), llamada
    assert lineas  # la corrida real hizo llamadas
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_fixtures.py -v -k "andamio or entorno or v08"`
Expected: FAIL con `ImportError: cannot import name 'CLAVES_RUNMETA_V2'`.

- [ ] **Step 3: Implementar** `CLAVES_RUNMETA_V2`, `entorno_de_prueba`, `editar_entorno` y `write_run_v08` en `tests/audit_fixtures.py` (y añadir los cuatro a la lista de la docstring del módulo), y la fixture `_andamio_entorno_ola2` al final de `tests/conftest.py` (un párrafo nuevo en la docstring del módulo que la explica y dice que es temporal).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS (el auditor todavía no lee `environment`: nada más cambia).

- [ ] **Step 5: Commit**

```bash
git add tests/audit_fixtures.py tests/conftest.py tests/test_audit_fixtures.py
git commit -m "test(audit): andamio temporal de environment en las corridas de la suite y corrida 0.8 (D12, hasta PR-A)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 4: Check `environment` (D12; relaciones 19 y 20, parte de entorno)

**Files:**
- Create: `revisia/audit/checks_environment.py`.
- Modify: `revisia/audit/__init__.py` (import y `CheckSpec` justo después de `provenance`, línea 72; `CHECKS` ocupa 70-102).
- Modify: `tests/test_audit_paquete.py` (`CHECKS_ESPERADOS`: fila nueva tras `provenance`).
- Test: `tests/test_audit_entorno.py` (nuevo).

**Interfaces:**
- Consumes: `Environment` (PR-0), `LEGACY_RUN` (`checks_provenance.py:45`), `AuditContext.run_info`, `.manifest`, `.manifest_dict`, `.llm_calls`, `.llm_calls_ilegible`, `.protocol`, `.state.reached` (`artifacts.py:755-919`), `short_text`, `format_validation`, `sufijo_mas`.
- Produces (G₂ los reutiliza):
  - `PRE_OLA2_RUN: str` = el texto literal de D12 (Global Constraints), sin punto final.
  - `SEMVER: re.Pattern[str]` (la expresión oficial de semver.org 2.0.0) y `es_semver(version: str) -> bool`.
  - `entorno_de_la_corrida(ctx: AuditContext) -> Environment | None`: el de `run.json` si valida; `None` si no hay `run.json`, no valida o `environment` es `None`/falta.
  - `check_environment(ctx: AuditContext) -> Verdict`. Reglas, en este orden (un FAIL junta todos sus problemas, separados por `; `, como mucho 5 y `sufijo_mas`):
    Las reglas 1–3 **cortan la evaluación**: devuelven su FAIL con ese detalle exacto y nada más (los tests comparan el detalle por igualdad); las reglas 4–8 acumulan.
    1. Sin `run.json`: FAIL `f"{LEGACY_RUN}."`.
    2. `run.json` que no valida: FAIL `"run.json no valida (ver `schemas`): sin `environment` verificable."`.
    3. `environment` ausente o `null`: FAIL `f"{PRE_OLA2_RUN}."`.
    4. FAIL si `engine_version` no es SemVer (`"… no es SemVer"`), si difiere de `run.json.engine_version` (`"≠ run.json.engine_version"`), si `prompt_templates` está vacío (`"sin plantillas hasheadas"`), si algún valor no es un sha256 hexadecimal de 64 (`"hash no es sha256: <clave>"`), o si el protocolo se lee y falta `rob/<protocol.rob_tool>.yml` (`"falta la especificación `rob/RoB2.yml`"`).
    5. Relación 19 (parte de plantillas): para cada llamada de `ctx.llm_calls` con `prompt_template` de tipo `str`: FAIL `"19 · plantilla fuera de environment.prompt_templates: <p>"` si no es clave; `"19 · hash de plantilla distinto: <p>"` si `prompt_template_sha256` ≠ el valor. Con `llm_calls_ilegible`, la relación queda no verificable: WARN con `LLM_CALLS_ILEGIBLE` (el FAIL lo da `schemas`). Las llamadas sin plantilla no se juzgan aquí (eso es `prompts`, G₂).
    6. Relación 20 (parte de entorno): si `manifest.yml` existe o `"reporte"` está en `ctx.state.reached`: FAIL `"manifest.yml ilegible: `environment` no se puede comparar"`, `"manifest.yml sin `environment`"`, `"manifest.environment no valida: …"` o `"manifest.environment ≠ run.json.environment (<campos distintos>)"`. Si no, no se compara y el PASS lo dice (`"manifiesto aún no escrito"`).
    7. Sin FAIL: WARN si `git_commit is None` (`"sin commit de git (motor instalado desde un paquete)"`) o `git_dirty is True` (`"árbol de git con cambios sin commitear (git_dirty)"`).
    8. PASS: `f"motor {v} · Python {py} ({impl}) · {platform} · commit {commit[:12]} · {n} plantillas y especificaciones hasheadas · == manifest.environment."` (o `· manifiesto aún no escrito.`), todos los valores con `short_text`.
- Registro: `CheckSpec("environment", "PRISMA 27 / trAIce M2", None, checks_environment.check_environment)`. `stage=None`: corre siempre, también en pausa.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_audit_entorno.py`:

```python
"""Check `environment` (spec 2026-10-18 §11.2, D12; relaciones 19 y 20 en su parte de entorno)."""

from __future__ import annotations

import json
from pathlib import Path

from audit_fixtures import (
    auditar,
    edit_json,
    edit_yaml,
    editar_entorno,
    editar_llamadas,
    fila,
    write_legacy_v07,
    write_run_v08,
)

from revisia.audit.checks_environment import PRE_OLA2_RUN, es_semver
from revisia.audit.checks_provenance import LEGACY_RUN


def _sin(clave: str):
    # `del` y no `pop`: `_apply` sustituiría el documento entero por el mapa devuelto.
    def _quitar(data: dict) -> None:
        del data[clave]

    return _quitar


def _sin_entorno(run: Path) -> None:
    edit_json(run / "run.json", _sin("environment"))
    edit_yaml(run / "manifest.yml", _sin("environment"))


def test_environment_corrida_real_pasa(corrida) -> None:
    entorno = fila(auditar(corrida), "environment")
    assert entorno.status == "PASS", entorno.detail
    assert "== manifest.environment" in entorno.detail


def test_environment_ausente_es_fail_con_el_mensaje_de_d12(corrida) -> None:
    _sin_entorno(corrida)
    report = auditar(corrida)
    assert fila(report, "environment").status == "FAIL"
    assert fila(report, "environment").detail == f"{PRE_OLA2_RUN}."
    assert PRE_OLA2_RUN == (
        "anterior a la Ola 2 (motor < 0.9): sin procedencia aplicada ni verificación por juez; "
        "regenera la corrida con el motor actual"
    )
    assert not report.publishable


def test_environment_null_es_ausente(corrida) -> None:
    edit_json(corrida / "run.json", lambda r: r.update(environment=None))
    assert fila(auditar(corrida), "environment").detail == f"{PRE_OLA2_RUN}."


def test_corrida_08_falla_solo_en_environment_y_el_resto_es_diagnostico(corrida) -> None:
    report = auditar(write_run_v08(corrida))
    assert {c.check_id for c in report.checks if c.status == "FAIL"} == {"environment"}
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []


def test_environment_sin_run_json_es_la_corrida_anterior_a_la_ola_1(tmp_path) -> None:
    entorno = fila(auditar(write_legacy_v07(tmp_path)), "environment")
    assert (entorno.status, entorno.detail) == ("FAIL", f"{LEGACY_RUN}.")


def test_environment_distinto_del_manifiesto_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", lambda m: m["environment"].update(platform="otra"))
    entorno = fila(auditar(corrida), "environment")
    assert entorno.status == "FAIL"
    assert "manifest.environment ≠ run.json.environment" in entorno.detail
    assert "platform" in entorno.detail


def test_environment_ausente_solo_en_el_manifiesto_falla(corrida) -> None:
    edit_yaml(corrida / "manifest.yml", _sin("environment"))
    assert "manifest.yml sin `environment`" in fila(auditar(corrida), "environment").detail


def test_environment_manifiesto_ilegible_falla(corrida) -> None:
    (corrida / "manifest.yml").write_text("[: no es yaml", encoding="utf-8")
    entorno = fila(auditar(corrida), "environment")
    assert entorno.status == "FAIL" and "manifest.yml ilegible" in entorno.detail


def test_environment_en_pausa_no_exige_el_manifiesto(corrida_en_pausa_ft) -> None:
    entorno = fila(auditar(corrida_en_pausa_ft), "environment")
    assert entorno.status == "PASS", entorno.detail
    assert "manifiesto aún no escrito" in entorno.detail


def test_es_semver() -> None:
    assert es_semver("0.9.0") and es_semver("1.0.0-rc.1+build.5")
    assert not es_semver("0.9") and not es_semver("0.9.0.dev1") and not es_semver("v1.0.0")


def test_environment_version_no_semver_o_distinta_de_run_json_falla(corrida) -> None:
    editar_entorno(corrida, lambda e: e.update(engine_version="0.9"))
    detalle = fila(auditar(corrida), "environment").detail
    assert "no es SemVer" in detalle and "≠ run.json.engine_version" in detalle


def test_environment_plantillas_vacias_mal_hasheadas_o_sin_especificacion_falla(corrida) -> None:
    editar_entorno(corrida, lambda e: e.update(prompt_templates={}))
    assert "sin plantillas hasheadas" in fila(auditar(corrida), "environment").detail
    editar_entorno(corrida, lambda e: e.update(prompt_templates={"x/v1.md": "zz"}))
    detalle = fila(auditar(corrida), "environment").detail
    assert "hash no es sha256: x/v1.md" in detalle
    assert "falta la especificación `rob/RoB2.yml`" in detalle


def test_relacion_19_plantilla_desconocida_o_con_otro_hash_falla(corrida) -> None:
    plantillas = json.loads((corrida / "run.json").read_text("utf-8"))["environment"][
        "prompt_templates"
    ]
    conocida = next(k for k in plantillas if k.endswith(".md"))

    def _editar(llamadas: list[dict]) -> None:
        llamadas[0].update(prompt_template="extraccion/v9.md", prompt_template_sha256="a" * 64)
        llamadas[1].update(prompt_template=conocida, prompt_template_sha256="b" * 64)

    editar_llamadas(corrida, _editar)
    detalle = fila(auditar(corrida), "environment").detail
    assert "19 · plantilla fuera de environment.prompt_templates: extraccion/v9.md" in detalle
    assert f"19 · hash de plantilla distinto: {conocida}" in detalle


def test_environment_sin_commit_o_sucio_solo_advierte(corrida) -> None:
    editar_entorno(corrida, lambda e: e.update(git_commit=None))
    report = auditar(corrida)
    assert fila(report, "environment").status == "WARN" and report.publishable
    editar_entorno(corrida, lambda e: e.update(git_commit="0" * 40, git_dirty=True))
    assert "git_dirty" in fila(auditar(corrida), "environment").detail


def test_environment_hostil_falla_acotado(corrida) -> None:
    editar_entorno(corrida, lambda e: e.update(packages="x" * 1_000_000))
    edit_json(corrida / "run.json", lambda r: r.update(environment=["no", "es", "un", "mapa"]))
    entorno = fila(auditar(corrida), "environment")
    assert entorno.status == "FAIL" and "error interno" not in entorno.detail
    assert len(entorno.detail) < 2_000
```

Y en `tests/test_audit_paquete.py`, en `CHECKS_ESPERADOS`, tras la fila de `provenance`: `("environment", "PRISMA 27 / trAIce M2", None, "checks_environment", "check_environment"),`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_entorno.py tests/test_audit_paquete.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'revisia.audit.checks_environment'`.

- [ ] **Step 3: Implementar** `revisia/audit/checks_environment.py` según Interfaces (docstring: D12, §19 fila 1, relaciones 19 y 20 en su parte de entorno; lo que queda para G₂: cada llamada con plantilla y `outcome`/`attempt` en `prompts`) y registrarlo en `__init__.py`. La comparación con el manifiesto valida su `environment` con `TypeAdapter(Environment)` y compara los modelos; los campos distintos se listan por nombre, nunca por valor.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_entorno.py tests/test_audit_paquete.py -v && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS. Si `test_corrida_08_falla_solo_en_environment…` muestra otra fila en FAIL, es un hallazgo (el auditor de hoy depende de un campo v2): se diagnostica y se anota para §19; no se relaja el test sin registrarlo.

- [ ] **Step 5: Commit**

```bash
git add revisia/audit/checks_environment.py revisia/audit/__init__.py tests/test_audit_entorno.py tests/test_audit_paquete.py
git commit -m "feat(audit): check environment: corrida 0.8 no publicable, entorno igual al manifiesto y plantillas de las llamadas (D12, relaciones 19-20)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 5: `make_deposit` (D17)

**Files:**
- Create: `revisia/exports/deposit.py` (no se exporta desde `revisia/exports/__init__.py`: la CLI lo importa perezosamente).
- Test: `tests/test_deposito.py` (nuevo).

**Interfaces:**
- Consumes: `DepositInfo`, `DepositSource`, `WithheldDir`, `WithheldFile`, `DEPOSIT_FILE`, `WITHHELD_DIRS` (`revisia.schemas.artifacts`, PR-0 T5), `read_run_info` (`snapshot.py:84`), `revisia.__version__`.
- Produces: `make_deposit(run_dir: str | Path, out_dir: str | Path) -> DepositInfo`.
  - `out_dir` es la carpeta de depósito misma (no su madre). Antes de copiar nada se comprueba, y si falla se lanza sin haber creado ni copiado nada: `run_dir` existe y tiene `run.json` válido (si no, `ValueError("… sin run.json: solo se depositan corridas de la Ola 1 o posteriores")`) y `manifest.yml` (si no, `ValueError("… sin manifest.yml: solo se deposita una corrida terminada")`); `run_dir` no tiene `deposit.json` (`ValueError("… ya es una copia de depósito")`); `out_dir` no está dentro de `run_dir` (`ValueError(f"el destino {out_dir} está dentro de la corrida {run_dir}: elige una carpeta fuera de ella")`); `out_dir` no existe o es una carpeta vacía (si no, `FileExistsError`).
  - Copia `run_dir` → `out_dir` con `shutil.copytree(..., dirs_exist_ok=True, ignore=…)` omitiendo exactamente las carpetas de `WITHHELD_DIRS` (comparando la ruta relativa POSIX + `/`).
  - `withheld`: siempre las dos entradas de `WITHHELD_DIRS`, en ese orden, `reason="copyright"` las dos; `files` = todos los ficheros de esa carpeta a cualquier profundidad, ordenados por `relpath`, con `relpath` relativo a `run_dir` y con `/`, `sha256` = `hashlib.sha256(bytes).hexdigest()` (para un texto en caché es igual a su `text_sha256`, porque el motor lo escribe en bytes UTF-8) y `n_bytes`. Una carpeta que no existe da `files=[]`.
  - `source_run` = `slug` y `timestamp` de `run.json`, `manifest_sha256` = sha256 de los bytes de `manifest.yml`; `engine_version=__version__`.
  - Escribe `out_dir/deposit.json` (último paso) con `json.dumps(info.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"` y devuelve `info`. La corrida original no se toca.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_deposito.py`:

```python
"""`make_deposit`: copia de depósito sin textos completos (spec 2026-10-18 D17, §11.3)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from audit_fixtures import write_legacy_v07

from revisia import __version__
from revisia.exports.deposit import make_deposit
from revisia.schemas.artifacts import DEPOSIT_FILE, WITHHELD_DIRS, DepositInfo


def _arbol(raiz: Path) -> dict[str, str]:
    return {
        p.relative_to(raiz).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(raiz.rglob("*"))
        if p.is_file()
    }


def _con_rescate(corrida: Path) -> Path:
    rescate = corrida / "screening_ft" / "rescues" / "sub" / "a.pdf"
    rescate.parent.mkdir(parents=True)
    rescate.write_bytes(b"%PDF-1.4 rescate")
    return rescate


def test_make_deposit_copia_todo_salvo_lo_retenido(corrida, tmp_path) -> None:
    _con_rescate(corrida)
    origen = _arbol(corrida)
    destino = tmp_path / "deposito" / corrida.name
    info = make_deposit(corrida, destino)
    copiado = _arbol(destino)
    retenidos = {k for k in origen if any(k.startswith(d) for d in WITHHELD_DIRS)}
    assert retenidos and any(k.startswith("04_fulltext/texts/") for k in retenidos)
    assert {k: v for k, v in copiado.items() if k != DEPOSIT_FILE} == {
        k: v for k, v in origen.items() if k not in retenidos
    }
    assert DepositInfo.model_validate_json((destino / DEPOSIT_FILE).read_text("utf-8")) == info
    assert _arbol(corrida) == origen  # la corrida original no se toca


def test_make_deposit_lista_los_retenidos_con_sus_hashes(corrida, tmp_path) -> None:
    rescate = _con_rescate(corrida)
    info = make_deposit(corrida, tmp_path / "dep")
    assert [(w.path, w.reason) for w in info.withheld] == [(d, "copyright") for d in WITHHELD_DIRS]
    textos, rescates = info.withheld
    assert textos.files == sorted(textos.files, key=lambda f: f.relpath)
    for f in [*textos.files, *rescates.files]:
        datos = (corrida / f.relpath).read_bytes()
        assert (f.sha256, f.n_bytes) == (hashlib.sha256(datos).hexdigest(), len(datos))
        assert "\\" not in f.relpath and not f.relpath.startswith("/")
    assert [f.relpath for f in rescates.files] == [rescate.relative_to(corrida).as_posix()]


def test_make_deposit_identifica_la_corrida_de_origen(corrida, tmp_path) -> None:
    info = make_deposit(corrida, tmp_path / "dep")
    run = json.loads((corrida / "run.json").read_text("utf-8"))
    assert (info.source_run.slug, info.source_run.timestamp) == (run["slug"], run["timestamp"])
    manifiesto = hashlib.sha256((corrida / "manifest.yml").read_bytes()).hexdigest()
    assert info.source_run.manifest_sha256 == manifiesto
    assert info.engine_version == __version__


def test_make_deposit_sin_carpetas_retenidas_las_declara_vacias(corrida_sin_registros, tmp_path):
    info = make_deposit(corrida_sin_registros, tmp_path / "dep")
    assert [w.files for w in info.withheld] == [[], []]


def test_make_deposit_rechaza_sin_copiar_nada(
    corrida, _corrida_en_pausa_ft, tmp_path_factory, tmp_path
) -> None:
    # La corrida en pausa se copia bajo OTRA raíz: `corrida` y `corrida_en_pausa_ft` se llaman
    # `<slug>-<YYYYmmdd-HHMMSS>` y, copiadas las dos en `tmp_path/runs/`, colisionarían si se
    # generaron en el mismo segundo.
    corrida_en_pausa_ft = tmp_path_factory.mktemp("pausa") / _corrida_en_pausa_ft.name
    shutil.copytree(_corrida_en_pausa_ft, corrida_en_pausa_ft)
    ocupado = tmp_path / "ocupado"
    ocupado.mkdir()
    (ocupado / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        make_deposit(corrida, ocupado)
    with pytest.raises(ValueError, match="dentro"):
        make_deposit(corrida, corrida / "dep")
    with pytest.raises(ValueError, match="manifest.yml"):
        make_deposit(corrida_en_pausa_ft, tmp_path / "pausa")  # su copia vive en otra raíz
    with pytest.raises(ValueError, match="run.json"):
        make_deposit(write_legacy_v07(tmp_path / "v07"), tmp_path / "legado")
    make_deposit(corrida, tmp_path / "dep")
    with pytest.raises(ValueError, match="ya es una copia de depósito"):
        make_deposit(tmp_path / "dep", tmp_path / "dep2")
    # `corrida` se copia en `tmp_path/runs/` (conftest.py:323-332); nada más se creó.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dep", "ocupado", "runs", "v07"]
    assert not (corrida / "dep").exists()


def test_make_deposit_acepta_un_destino_vacio(corrida, tmp_path) -> None:
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    make_deposit(corrida, vacio)
    assert (vacio / DEPOSIT_FILE).is_file()
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_deposito.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'revisia.exports.deposit'`.

- [ ] **Step 3: Implementar** `revisia/exports/deposit.py` según Interfaces (docstring: D17, por qué los textos no son depositables, que `deposit.json` no es una firma — riesgo 10 del spec).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_deposito.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/exports/deposit.py tests/test_deposito.py
git commit -m "feat(exports): make_deposit copia la corrida sin textos completos y lista lo retenido con sus hashes (D17)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 6: Check `deposit` y textos en caché verificados por hash (D17, relación 30)

**Files:**
- Create: `revisia/audit/checks_deposit.py`.
- Modify: `revisia/audit/relations.py` (añadir `ruta_del_texto`), `revisia/audit/checks_flow.py` (`_textos_en_cache`, hoy `checks_flow.py:1008-1033` del original), `revisia/audit/__init__.py` (import y `CheckSpec` tras `stage_artifacts`).
- Modify: `tests/test_audit_paquete.py` (`CHECKS_ESPERADOS`: fila tras `stage_artifacts`).
- Test: `tests/test_audit_deposito.py` (nuevo).

**Interfaces:**
- Consumes: `make_deposit` (Tarea 5), `DepositInfo`, `DEPOSIT_FILE`, `WITHHELD_DIRS` (PR-0), `RETRIEVAL`, `TEXTOS`, `_ids`, `_Relations` (`relations`), `AuditContext.art.json`, `.art.artifact(RETRIEVAL)`, `.run_info`, `sha256_text`.
- Produces (G₂ los reutiliza para las relaciones 23, 24 y 28, que leen textos y rescates retenidos):
  - En `relations.py`: `ruta_del_texto(record_id: str) -> str` = `f"{TEXTOS}/{sha256_text(record_id)[:16]}.txt"` (la regla del motor, `pipeline.py:558`); `_textos_en_cache` pasa a usarla.
  - En `checks_deposit.py`:
    - `@dataclass(frozen=True) class Deposito`: `info: DepositInfo`, `retenidos: dict[str, str]` (`relpath → sha256` de todos los ficheros de `withheld`).
    - `leer_deposito(ctx: AuditContext) -> tuple[Deposito | None, str | None]`: `(None, None)` sin `deposit.json`; `(None, motivo)` si existe y no se lee o no valida (motivo acotado, con `format_validation`); `(Deposito, None)` si valida.
    - `texto_retenido(deposito: Deposito, relpath: str, sha256: str) -> bool`.
    - `check_deposit(ctx: AuditContext) -> Verdict`:
      - sin `deposit.json`: PASS `"no es copia de depósito (sin deposit.json)."`;
      - ilegible o inválido: FAIL `"deposit.json ilegible o inválido: <motivo>."`;
      - FAIL (todos los problemas, acotados) si: una entrada de `withheld` con `path` fuera de `WITHHELD_DIRS` o repetida; un `relpath` que no empieza por su `path`, absoluto, con `\` o con un segmento `..`, o repetido; un fichero retenido presente en la copia (`"fichero retenido presente: <relpath>"`); cualquier fichero bajo una carpeta de `WITHHELD_DIRS` que no esté en la lista (`"fichero fuera de la lista en <dir>: <relpath>"`); una fila `available` de `retrieval.json` cuya `ruta_del_texto(id)` no esté retenida con `sha256 == text_sha256` (`"texto de <id> sin hash retenido o distinto"`); `retrieval.json` presente e inválido; `manifest.yml` ausente o con sha256 ≠ `source_run.manifest_sha256` (`"manifest_sha256 no coincide"`); `slug`/`timestamp` ≠ `run.json` o sin `run.json`;
      - PASS: `f"copia de depósito ({created_utc}): {n} ficheros retenidos con su sha256 ({por carpeta}); {k} textos de retrieval.json verificados por hash; manifest.yml igual al de la corrida de origen."`.
  - `_textos_en_cache` (relación 7 de `arithmetic`): si `leer_deposito(ctx)` devuelve un `Deposito`, la relación se llama `f"7 · textos de {TEXTOS} == text_sha256 de {RETRIEVAL} (copia de depósito: verificados por hash en {DEPOSIT_FILE})"` y para cada fila `available` exige `row.text_file == ruta_del_texto(id)` y `texto_retenido(dep, esa ruta, row.text_sha256)`; `n_chars` no se puede verificar sin el texto y la docstring lo declara. Sin depósito válido, la relación es la de siempre.
- Registro: `CheckSpec("deposit", "PRISMA 27", None, checks_deposit.check_deposit)`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_audit_deposito.py`:

```python
"""Check `deposit` y la relación 7 por hash en una copia de depósito (D17, relación 30)."""

from __future__ import annotations

import shutil
from pathlib import Path

from audit_fixtures import auditar, edit_json, fila

from revisia.exports.deposit import make_deposit
from revisia.schemas.artifacts import DEPOSIT_FILE


def _deposito(corrida: Path, tmp_path: Path) -> Path:
    destino = tmp_path / "deposito" / corrida.name
    make_deposit(corrida, destino)
    return destino


def _primer_retenido(deposito: dict) -> dict:
    return deposito["withheld"][0]["files"][0]


def test_deposito_audita_con_el_mismo_veredicto(corrida, tmp_path) -> None:
    original = auditar(corrida)
    deposito = auditar(_deposito(corrida, tmp_path))
    assert {c.check_id: c.status for c in deposito.checks} == {
        c.check_id: c.status for c in original.checks
    }
    assert original.publishable and deposito.publishable
    assert "copia de depósito" in fila(deposito, "deposit").detail
    assert "verificados por hash" in fila(deposito, "deposit").detail


def test_corrida_sin_deposit_json_no_es_copia_de_deposito(corrida) -> None:
    fila_deposito = fila(auditar(corrida), "deposit")
    assert fila_deposito.status == "PASS" and "no es copia de depósito" in fila_deposito.detail


def test_deposito_con_un_texto_retenido_dentro_falla(corrida, tmp_path) -> None:
    destino = _deposito(corrida, tmp_path)
    texto = next((corrida / "04_fulltext" / "texts").iterdir())
    (destino / "04_fulltext" / "texts").mkdir(parents=True)
    shutil.copyfile(texto, destino / "04_fulltext" / "texts" / texto.name)
    report = auditar(destino)
    assert "fichero retenido presente" in fila(report, "deposit").detail
    assert not report.publishable


def test_deposito_con_un_fichero_fuera_de_la_lista_falla(corrida, tmp_path) -> None:
    destino = _deposito(corrida, tmp_path)
    otro = destino / "screening_ft" / "rescues" / "sub" / "b.pdf"
    otro.parent.mkdir(parents=True)
    otro.write_bytes(b"%PDF")
    assert "fuera de la lista" in fila(auditar(destino), "deposit").detail


def test_deposito_con_un_hash_retenido_cambiado_falla_tambien_en_arithmetic(
    corrida, tmp_path
) -> None:
    destino = _deposito(corrida, tmp_path)
    edit_json(destino / DEPOSIT_FILE, lambda d: _primer_retenido(d).update(sha256="0" * 64))
    report = auditar(destino)
    assert "sin hash retenido o distinto" in fila(report, "deposit").detail
    assert fila(report, "arithmetic").status == "FAIL"
    assert "verificados por hash" in fila(report, "arithmetic").detail


def test_deposito_con_otro_manifiesto_falla(corrida, tmp_path) -> None:
    destino = _deposito(corrida, tmp_path)
    edit_json(destino / DEPOSIT_FILE, lambda d: d["source_run"].update(manifest_sha256="0" * 64))
    assert "manifest_sha256 no coincide" in fila(auditar(destino), "deposit").detail


def test_deposit_json_hostil_falla_acotado(corrida, tmp_path) -> None:
    destino = _deposito(corrida, tmp_path)
    enorme = '{"withheld": "' + "x" * 1_000_000 + '"}'
    for contenido in ("{", '["no", "es", "un", "mapa"]', enorme):
        (destino / DEPOSIT_FILE).write_text(contenido, encoding="utf-8")
        fila_deposito = fila(auditar(destino), "deposit")
        assert fila_deposito.status == "FAIL" and "deposit.json" in fila_deposito.detail
        assert "error interno" not in fila_deposito.detail and len(fila_deposito.detail) < 2_000


def test_deposit_json_con_rutas_que_escapan_falla(corrida, tmp_path) -> None:
    destino = _deposito(corrida, tmp_path)
    for mala in ("04_fulltext/texts/../../run.json", "/etc/passwd", "04_fulltext\\texts\\a.txt"):
        edit_json(destino / DEPOSIT_FILE, lambda d, m=mala: _primer_retenido(d).update(relpath=m))
        assert fila(auditar(destino), "deposit").status == "FAIL", mala
```

Y en `tests/test_audit_paquete.py`, en `CHECKS_ESPERADOS`, tras `stage_artifacts`: `("deposit", "PRISMA 27", None, "checks_deposit", "check_deposit"),`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_deposito.py tests/test_audit_paquete.py -v`
Expected: FAIL con `sin fila 'deposit'` (y `ModuleNotFoundError` en `test_audit_paquete`).

- [ ] **Step 3: Implementar** `ruta_del_texto` en `relations.py`, `checks_deposit.py` según Interfaces (docstring: D17, relación 30, por qué la relación 7 pasa a hash y qué no se puede verificar sin los textos; que G₂ debe tratar igual las relaciones 23, 24 y 28), la rama de depósito de `_textos_en_cache` y el registro en `__init__.py`. Las rutas de `deposit.json` son entrada no confiable: se validan como texto antes de construir ninguna ruta, y nunca se abre un fichero a partir de ellas (solo se comprueba existencia con la ruta ya validada bajo `run_dir`).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_deposito.py tests/test_audit_paquete.py -v && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado && wc -l revisia/audit/*.py`
Expected: PASS; ningún módulo > 900.

- [ ] **Step 5: Commit**

```bash
git add revisia/audit/checks_deposit.py revisia/audit/relations.py revisia/audit/checks_flow.py revisia/audit/__init__.py tests/test_audit_deposito.py tests/test_audit_paquete.py
git commit -m "feat(audit): check deposit y textos en caché verificados por hash en una copia de depósito (D17, relación 30)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea 7: `revisia deposit` (D17, §11.3)

**Files:**
- Modify: `revisia/cli.py`: función nueva `_cmd_deposit` justo antes de `_cmd_brain` (`cli.py:573`, tras `_cmd_export`, `:551-570`); bloque de subparser justo después del de `export` (`cli.py:698-714`); despacho justo después de `cli.py:740-741` (`export`). Nada más. F₁ ancla `benchmark-report` tras `_cmd_audit`/`audit` (plan PR-F, Tarea 9): anclar en `export` deja los trozos separados.
- Test: `tests/test_cli_deposit.py` (nuevo).

**Interfaces:**
- Consumes: `make_deposit` (Tarea 5), `main` (`cli.py:728`).
- Produces: `revisia deposit <run_dir> --out <dir>` (`--out` obligatorio). `_cmd_deposit(args: argparse.Namespace) -> int`, con import perezoso de `revisia.exports.deposit`:
  - `run_dir` inexistente → `error: la carpeta '<run_dir>' no existe.` a stderr, rc 2;
  - `ValueError`, `FileExistsError` u `OSError` de `make_deposit` → `error: <mensaje>` a stderr, rc 2;
  - éxito → stdout `✓ Copia de depósito: <out>`, después por cada `WithheldDir` `  Retenido (<reason>): <path> · <n> fichero(s)` y por cada fichero `    - <relpath> sha256=<sha256> (<n_bytes> bytes)`, y al final `  Audítala con: revisia audit <out>`; rc 0.
  - Ayuda del subparser: `"Copia de depósito de una corrida terminada, sin textos completos (D17): lista lo retenido con su sha256."`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_cli_deposit.py`:

```python
"""`revisia deposit` (spec 2026-10-18 §11.3, D17)."""

from __future__ import annotations

import json
import shutil

import pytest

from revisia.cli import main
from revisia.schemas.artifacts import DEPOSIT_FILE


def test_cli_deposit_crea_la_copia_imprime_los_hashes_y_audita_apta(corrida, tmp_path, capsys):
    destino = tmp_path / "deposito" / corrida.name
    assert main(["deposit", str(corrida), "--out", str(destino)]) == 0
    salida = capsys.readouterr().out
    info = json.loads((destino / DEPOSIT_FILE).read_text("utf-8"))
    hashes = [f["sha256"] for w in info["withheld"] for f in w["files"]]
    assert hashes and all(h in salida for h in hashes)
    assert f"revisia audit {destino}" in salida
    assert main(["audit", str(destino)]) == 0


def test_cli_deposit_sin_out_es_error_de_uso(corrida) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["deposit", str(corrida)])
    assert exc.value.code == 2


def test_cli_deposit_carpeta_inexistente_rc_2(tmp_path, capsys) -> None:
    assert main(["deposit", str(tmp_path / "nada"), "--out", str(tmp_path / "d")]) == 2
    assert "no existe" in capsys.readouterr().err


def test_cli_deposit_destino_ocupado_o_corrida_sin_manifiesto_rc_2(
    corrida, _corrida_en_pausa_ft, tmp_path_factory, tmp_path, capsys
) -> None:
    # Copia de la corrida en pausa bajo otra raíz (colisión de nombre con `corrida`, ver T5).
    corrida_en_pausa_ft = tmp_path_factory.mktemp("pausa") / _corrida_en_pausa_ft.name
    shutil.copytree(_corrida_en_pausa_ft, corrida_en_pausa_ft)
    ocupado = tmp_path / "ocupado"
    ocupado.mkdir()
    (ocupado / "x").write_text("x", encoding="utf-8")
    assert main(["deposit", str(corrida), "--out", str(ocupado)]) == 2
    assert main(["deposit", str(corrida_en_pausa_ft), "--out", str(tmp_path / "p")]) == 2
    assert "manifest.yml" in capsys.readouterr().err
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_cli_deposit.py -v`
Expected: FAIL (`argparse`: `invalid choice: 'deposit'`, `SystemExit 2` en el primer test).

- [ ] **Step 3: Implementar** `_cmd_deposit`, el subparser y el despacho en `revisia/cli.py` según Interfaces.

- [ ] **Step 4: Run para verificar que pasa, y la suite entera**

Run: `uv run pytest -p no:cacheprovider tests/test_cli_deposit.py -v && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado && uv run ruff check . && uv run ruff format --check . && uv run black --check .`
Expected: PASS y lint limpio. Anotar el recuento final de G₁ para el cuerpo de la PR.

- [ ] **Step 5: Commit**

```bash
git add revisia/cli.py tests/test_cli_deposit.py
git commit -m "feat(cli): revisia deposit <run_dir> --out <dir> con los hashes retenidos (D17)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Supuestos revocables de G₁ (filas propuestas para §19)

El spec no fija estos puntos; el plan decide y el integrador los añade a §19 **a continuación de la última fila existente**, con numeración consecutiva:

```
| n | D26, §11.1 | Además de los ocho módulos de D26 hay tres auxiliares: `relations.py` (rutas, `_Relations` y ayudantes de la familia del flujo; en `checks_flow.py` habrían creado un import circular con `collect_relations`), `text.py` (sale de `artifacts.py`, que tenía 919 líneas y §2 no mencionaba) y `checks_ledger.py` como raíz de los ayudantes HITL compartidos | Plan PR-G |
| n+1 | D26 | `_metrics`/`_gold_anclado`/`_matriz_desde_gold` y `_copies` van a `checks_artifacts.py`, no a `checks_flow.py`, para dejar este en ≈ 810 líneas (con ellos, ≈ 930) | Plan PR-G |
| n+2 | D26 | Los imports de `checks_flow`/`checks_hitl` desde otros módulos y desde los tests se redirigen (cinco ficheros), sin reexportar; `artifacts.py` sí reexporta `short_text`, `short_repr`, `sufijo_mas` y `format_validation` (decenas de usos). Los nombres privados conservan su `_` | Plan PR-G |
| n+3 | §11.2 `environment`, D12 | Sin `run.json`: FAIL con `LEGACY_RUN` (corrida anterior a la Ola 1). `"environment": null` cuenta como ausente. «Válido» incluye `engine_version == run.json.engine_version`; «plantillas y especificaciones hasheadas» = `prompt_templates` no vacío, valores sha256 de 64 hex y la clave `rob/<rob_tool>.yml` del protocolo. La comparación con el manifiesto solo se exige si `manifest.yml` existe o la corrida alcanzó `reporte`; un manifiesto ilegible es FAIL | Plan PR-G |
| n+4 | §11.2 `environment`, relación 19 | G₁ comprueba la parte de plantillas de la relación 19 solo en las llamadas que traen `prompt_template`; que **toda** llamada `ok` la traiga, y `outcome`/`attempt` (§19 fila 1), los comprueba `prompts` en G₂ | Plan PR-G |
| n+5 | §15, D12 | Andamio temporal en `tests/conftest.py` (`_andamio_entorno_ola2`, de sesión): mientras G₁ se desarrolla desde PR-0, los tests inyectan `environment` en `run.json` y en el manifiesto de las corridas nuevas; G₂ lo retira al rebasar sobre F (PR-A ya lo escribe). La «corrida 0.8» de los tests (`write_run_v08`) es una corrida real sin `environment`, sin `kind` y sin los campos v2 de `RunMeta`, no una producida por el motor 0.8 | Plan PR-G |
| n+6 | D17, §11.3 | `make_deposit(run_dir, out_dir)`: `out_dir` es la carpeta de depósito misma, vacía o inexistente y fuera de la corrida; exige `run.json` y `manifest.yml` y rechaza depositar un depósito, todo antes de copiar. Las dos carpetas de `WITHHELD_DIRS` se declaran siempre (con `files: []` si no existen), ambas con `reason: copyright`; `sha256` es el de los bytes del fichero; `--out` es obligatorio en la CLI | Plan PR-G |
| n+7 | D17, relación 30 | Con `deposit.json` válido, la relación 7 de `arithmetic` comprueba ruta y hash de cada texto contra lo retenido; `n_chars` deja de verificarse (bytes ≠ caracteres) y se declara. El check `deposit` va tras `stage_artifacts` con ítem «PRISMA 27»; `environment`, tras `provenance` con «PRISMA 27 / trAIce M2» | Plan PR-G |
| n+8 | §15 `cli.py` | G toca `build_parser` y `main`, las mismas funciones que F (`benchmark`, `benchmark-report`): G ancla sus tres trozos en `export` (función antes de `_cmd_brain`, subparser y despacho tras los de `export`) y F₁ en `audit`, para que el rebase de G sobre F no tenga trozos contiguos | Plan PR-G |
| n+9 | D17, relaciones 23, 24 y 28 | Con `deposit.json` válido, las relaciones que recalculan desde textos en caché o rescates retenidos (23 rescate, 24 `quote_status`, 28 ventana y `numbers_missing`) se dan por verificadas por hash contra lo retenido y se anota; G₂ lo implementa con `leer_deposito`/`texto_retenido` | Mismo veredicto que la corrida original (D17, §11.3) |
```

### Self-review de G₁

- **Cobertura de §11 para G₁:** partición D26 con el test de 900 líneas y `CHECKS` fijado (T2); `environment` con su tabla de §11.2 (PASS, WARN y FAIL con el mensaje literal de D12) y la parte de entorno de las relaciones 19 y 20 (T4); `make_deposit` (T5); check `deposit`, relación 30 y «textos en caché frente a `retrieval.json`» por hash (T6); `revisia deposit` e impresión de hashes (T7); test de frontera «el depósito audita con el mismo veredicto» (T6, y por CLI en T7); «corrida 0.8 → FAIL `environment` y el resto diagnóstico» (T4 con `write_run_v08`, T3). Lo demás de §11.2 y §16 es de G₂ (abajo).
- **Firmas y líneas verificadas contra el árbol (`main` @ `c1af7c3`, igual en esta rama):** `checks_flow.py` (2 190; rangos del mapa por AST), `checks_hitl.py` (1 389), `artifacts.py` (919; `short_repr` 306, `short_text` 311, `sufijo_mas` 346, `format_validation` 363, `AuditContext` 755), `__init__.py` (`CHECKS` 70-102, `provenance` 72), `checks_quality.py:29,35-40`, `checks_provenance.py:45` (`LEGACY_RUN`), `cli.py` (`_cmd_audit` 527, `_cmd_export` 551, `_cmd_brain` 573, `p_export` 698-714, `main` 728, despacho de `export` 740-741), `snapshot.py` (`prompt_fingerprint` 76, `read_run_info` 84, `write_run_info` 92, `ensure_snapshot` 106), `run_context.py:190` (`write_manifest`), `pipeline.py:107,558,1278`, `audit_fixtures.py` (`edit_json` 86, `edit_yaml` 92, `editar_llamadas` 146, `write_legacy_v07` 280), `conftest.py` (`_correr` 234, fixtures de sesión 279-319). Las de PR-0 (`Environment`, `DepositInfo`, `WithheldDir`, `WithheldFile`, `DepositSource`, `DEPOSIT_FILE`, `WITHHELD_DIRS`, `tool_spec_fingerprint`) se toman de los bloques Interfaces de su plan (T5, T10).
- **Consistencia de tipos:** `entorno_de_prueba`/`editar_entorno`/`write_run_v08` (T3) los usan T4 y G₂; `PRE_OLA2_RUN`/`es_semver`/`entorno_de_la_corrida` (T4) y `leer_deposito`/`texto_retenido`/`Deposito`/`ruta_del_texto` (T6) se nombran igual en el bloque de G₂; `CHECKS_ESPERADOS` crece en T4 y T6 sin cambiar las filas de T2.
- **Review Focus:** las cinco líneas tienen test en su tarea (T4: hostil, en pausa, `null`; T5: rechazo sin copiar, `/` y subcarpetas; T6: hostil, rutas que escapan, fichero fuera de la lista).
- **Proporción:** los bloques de código son tests y un script de verificación de un solo uso; ninguna función de producción tiene cuerpo en el plan.
- **Riesgo de la frontera 0.8:** `test_corrida_08_falla_solo_en_environment…` exige que ninguna otra fila falle al quitar los campos v2; si alguna lo hace, el auditor de la Ola 1 depende de un default v2 y hay que decidirlo (T4, Step 4).

---

## Fase G₂ (sobre PR-F)

**Estado de partida:** PR-0 + H + A + B + C + D + E + F, con G₁ rebasada encima. Los nombres que G₂ consume salen de los bloques «Para PR-G₂», «Contratos/Interfaces para G₂» y «Estado en que X deja el pipeline» de cada plan:
- `2026-10-19-ola2-pra-procedencia.md` (A): Tarea 2 (`APPLIED_PARAMS`, `emit_attempt`), Tarea 3 (sink, `RecordFailedError`) y Tarea 6 (`environment`, `collect_environment`, `git_state`, `_git_state_fijo`, relación 20).
- `-prb-identidad-registros.md` (B): Tarea 6 (`DedupReport.unmerged_placeholders`, `PLACEHOLDER_TITLES`, `dedup_key`) y Tarea 7 (`SearchLogEntry.format`, `ignored_files`).
- `-prc-texto-completo-extraccion.md` (C): «Contratos para G₂ (relaciones 22–26)», `failed_extraction` (T5) y `failed_ids` (T11).
- `-prd-verificador.md` (D): «Interfaces para G₂ (relación 28)», con `claim_numbers_missing`.
- `-pre-rob-por-herramienta.md` (E): «Interfaces para G₂ (relación 27)», con `failed_assessment`.
- `-prf-meta-benchmark.md` (F): «Interfaces para G₂ (relaciones 29 y 31)», **incluido su «CAMBIO tras revisión»**.

Si un nombre de aquí no coincide con el del plan dueño, **manda el bloque Interfaces del plan dueño**; la discrepancia se anota para §19.

**Reglas adicionales de G₂** (además de Global Constraints):
- El código de test no pasa de 99 columnas. Los bloques de test de este plan llevan sus imports completos y `-> None`.
- Los imports de `fakes`, `hitl_helpers`, `audit_fixtures` y `conftest` van en el bloque de terceros, tras `import pytest`.
- Antes de cada comprobación: `uv run black . && uv run ruff check --fix .`.
- Para borrar claves en las ediciones de test, `del` dentro de una función, nunca `pop` en una `lambda`: `_apply` sustituiría el documento por lo que devuelve.
- Cada check nuevo o cambiado se prueba con **un síntoma por test**: una corrida real y coherente, una sola edición y la fila esperada. La corrida de partida audita sin FAIL.
- **Fail-closed por subcomprobación:** `extraction`, `rob`, `meta_analysis` y `grounding` corren cada subcomprobación dentro de su propio `guard`, con el mismo patrón que `_Relations.guard`. Una excepción es un problema con su tipo, nunca «error interno». Cada tarea añade su `test_<check>_hostil_falla_acotado`.
- `test_ningun_modulo_del_auditor_supera_900_lineas` se ejecuta en cada tarea.

### Interfaces que G₁ deja para G₂

**Obligaciones de arranque de G₂** (las cumplen las Tareas G2.0, G2.1 y G2.5):
- Retirar la fixture `_andamio_entorno_ola2` de `tests/conftest.py` (PR-A ya escribe `environment` en `run.json` y en el manifiesto). G₂ se apoya en la fixture autouse `_git_state_fijo` de PR-A (Tarea 6), que fija `snapshot.git_state` a `("0" * 40, False)`. Sin ella, el `git_dirty` real daría WARN en `environment`, que no está en `AVISOS_DE_LA_DEMO`.
- `write_run_v08` se acerca a la forma 0.8 real (G2.1). Por eso `test_corrida_08_falla_solo_en_environment…` pasa a exigir:
  - `environment` en FAIL con el mensaje de D12;
  - `prompts` en FAIL por esquema v1;
  - ninguna fila con «error interno».
- Volver verdes los `xfail(strict=True)` de A, C, D, E y F (lista en G2.0) y borrar los tres tests gemelos «…_solo_falla_lo_que_adapta_g2» de C, D y E.
- **Hueco de D17:** con `deposit.json` válido, las relaciones 23, 24 y 28 se dan por verificadas por hash (`texto_retenido` contra `text_sha256`/`rescue_file_sha256`) y el detalle lo anota (fila n+9).
- `checks_flow.py` queda en ≈ 820 líneas tras G₁. Las relaciones nuevas **no** van ahí: solo se registran en `collect_relations`.

**Dónde va cada familia** (decisión de G₂; «nuevo» = módulo que crea G₂):

| Check / relación (§11.2, §4.3) | Módulo | Tarea |
|---|---|---|
| `prompts` (M): esquema v1, plantilla en cada llamada `ok`, intentos fallidos > 20 % | `checks_provenance.py` (`check_prompts`) | G2.2 |
| relación 19: cada llamada `ok` en su línea de diario | `checks_journals.py` (`_diarios`, relación 12 ampliada) | G2.2 |
| relación 20: `models_used`/`deterministic_token_level` sobre llamadas `ok` | `checks_journals.py` (`_calls`) | G2.2 |
| relación 21: parámetros aplicados (`arithmetic`) | `checks_calls.py` (nuevo) | G2.2 |
| `timing` (M), `response_overlap` (M) | `checks_timing.py` | G2.3 |
| relación 22: línea `failed` ⇒ consolidado fallido; T/A y FT; exenciones de fallidos (gold, relación 13, `_llamadas_esperadas`, cota de llamadas) | `checks_failed.py` (nuevo); enganches en `checks_journals.py` y `checks_artifacts.py` | G2.4 (y G2.6, G2.7 para extracción y RoB) |
| ediciones de la decisión efectiva por etapa (`edit_field`, `edit_domain`, `rescue_text`) | `checks_ledger.py` (`ediciones_efectivas`, nuevo ayudante único) | G2.4 |
| `grounding` (M), relación 28 | `checks_grounding.py` (nuevo; sale de `checks_quality.py`) | G2.5 |
| relaciones 23 y 7 con `human_rescue` (`arithmetic`); `extraction` (N): relaciones 22 (extracción), 24 y 25; relación 26 (`arithmetic`) | `checks_extraction.py` (nuevo); enganche en `checks_flow._recuperacion` | G2.6 |
| `concordance`, `FieldEdits`/`DomainEdits` sin `decision.yml`, `artifact_sha256` de `extraccion`/`rob` | `checks_request_hash.py` | G2.6, G2.7 |
| `rob` (N): relaciones 22 (RoB) y 27 | `checks_rob.py` (nuevo) | G2.7 |
| `meta_analysis` (N): relación 29; la familia `_meta_analisis` sale de `arithmetic` | `checks_meta.py` | G2.8 |
| `derive_state` con `kind: benchmark`; `provenance` con D23; relación 31; `publishable` | `state.py`, `checks_provenance.py`, `__init__.py`, `model.py` | G2.9 |

**Ayudantes comunes que G₁ deja:**
- `revisia.audit.relations`:
  - rutas (`TA`, `FT`, `EXTRACTIONS`, `ASSESSMENTS`, `AGREEMENT`, `RETRIEVAL`, `VERIFICATION`, `DOCUMENTO`, `TEXTOS`, `LLM_CALLS`, …);
  - `_Relations` (`eq`, `check`, `unverifiable`, `ausente`, `guard`);
  - `_ids`, `_limitar`, `_valor`, `_n`, `_seccion`, `_artefacto`, `_ola1`, `included_ids`, `_normalizar` y `ruta_del_texto(record_id) -> str`.
- `revisia.audit.checks_ledger`: `de_la_decision_efectiva`, `indice_de_bandera`, `ACTOR_POR_DEFECTO`, `CONSEJO_ACTOR`, `autonomia_efectiva_de_la_corrida`, `_gates_pendientes` y `_detenida`.
- `revisia.audit.checks_environment`: `PRE_OLA2_RUN`, `SEMVER`, `es_semver` y `entorno_de_la_corrida`.
- `revisia.audit.checks_deposit`: `Deposito`, `leer_deposito` y `texto_retenido`.
- `revisia.audit.text`: `short_text`, `short_repr`, `sufijo_mas` y `format_validation`.
- Tests:
  - `tests/audit_fixtures.py`: `entorno_de_prueba`, `editar_entorno`, `write_run_v08` y `CLAVES_RUNMETA_V2`;
  - `tests/test_audit_paquete.py::CHECKS_ESPERADOS`;
  - `tests/test_audit_deposito.py::test_deposito_audita_con_el_mismo_veredicto`.

### Topología de G₂

En el mismo worktree `C:\revisia-wt\g`, secuencial. G2.0 y G2.11 son del controlador; el resto, implementador y revisor por tarea (§16).

| Tarea | Fichero(s) principales | Depende de |
|---|---|---|
| G2.0 | rebase sobre F, conflictos, lista de `xfail` | PR-F cerrada |
| G2.1 | `tests/conftest.py` (sin andamio), `tests/audit_fixtures.py` (`write_run_v08`, ayudantes de edición), `tests/test_audit_entorno.py` | G2.0 |
| G2.2 | `checks_provenance.py` (`prompts`), `checks_journals.py` (19, 20, 12), `checks_calls.py` (21) | G2.1 |
| G2.3 | `checks_timing.py` | G2.2 |
| G2.4 | `checks_failed.py` (22), `checks_ledger.py` (`ediciones_efectivas`), `checks_journals.py`, `checks_artifacts.py`, `checks_flow.py` | G2.2 |
| G2.5 | `checks_grounding.py` (nuevo), `checks_quality.py`, `checks_journals.py`; `tests/conftest.py` (`protocolo_auditoria` en `judge`, `corrida_existence`) | G2.4 |
| G2.6 | `checks_extraction.py` (nuevo), `checks_request_hash.py`, `checks_journals.py`, `checks_flow.py` | G2.5 |
| G2.7 | `checks_rob.py` (nuevo), `checks_journals.py`, `checks_request_hash.py` | G2.6 |
| G2.8 | `checks_meta.py`, `checks_flow.py`, `checks_artifacts.py` | G2.5 |
| G2.9 | `state.py`, `model.py`, `__init__.py`, `checks_provenance.py`, `checks_environment.py` | G2.8 |
| G2.10 | fronteras de §11 y §16; fixture combinada `corrida_ola2_completa` | G2.1–G2.9 |
| G2.11 | integración (controlador) | todas |

`CHECKS` al final de G₂ (**26 filas**): las 23 de G₁, más `extraction` y `rob` tras `exclusions` y `meta_analysis` tras `arithmetic`. `grounding` cambia de módulo a `checks_grounding`. Cada tarea que añade o mueve una fila actualiza `CHECKS_ESPERADOS`.

**Estimación de tamaños tras G₂** (≤ 900; el test lo comprueba en cada tarea):

| Módulo | Líneas |
|---|---|
| `checks_flow` | ≈ 830 |
| `checks_request_hash` | ≈ 760 (`concordance`, `FieldEdits`/`DomainEdits` sin `decision.yml`, hash de las salidas del diario) |
| `checks_journals` | ≈ 680 |
| `checks_artifacts` | ≈ 470 |
| `checks_grounding` | ≈ 480 |
| `checks_extraction` | ≈ 480 |
| `checks_meta` | ≈ 430 |
| `checks_ledger` | ≈ 430 |
| `checks_provenance` | ≈ 430 |
| `checks_timing` | ≈ 420 |
| `checks_quality` | ≈ 380 (sin `grounding`) |
| `checks_rob` | ≈ 340 |
| `checks_environment` | ≈ 240 |
| `checks_deposit` | ≈ 220 |
| `checks_failed` | ≈ 160 |
| `checks_calls` | ≈ 120 |

Si uno se acerca a 900, la familia que crece sale a su propio módulo; no se compacta código.

---

### Tarea G2.0: Rebase sobre PR-F, conflictos y lista de `xfail` (controlador)

**Files:** los conflictos del rebase; ninguno nuevo.

- [ ] **Step 1: Rebase.**

```bash
cd C:/revisia-wt/g
git fetch origin && git rebase origin/feat/ola2-meta-benchmark
```

Conflictos previstos y su resolución (en los demás ficheros manda F):
- `tests/test_auditor_meta_y_estados.py`: unión de los imports de G₁ (`relations.included_ids`) y de las ediciones de F₁ (plan F, tabla de solapes).
- `tests/conftest.py`: se conservan las fixtures de A (`_git_state_fijo`, `_cli_claude_simulado`), C, D, E y F (`protocolo_benchmark`, F2.4), y el andamio de G₁ (lo retira G2.1).
- `revisia/cli.py`: `deposit` (anclado en `export`) y `benchmark`/`benchmark-report` (anclados en `audit`) conviven.
- `tests/audit_fixtures.py`: el precalentamiento de PR-H y los ayudantes de G₁ conviven.
- `revisia/audit/*`: F no lo toca. Si aparece un conflicto ahí, hay un error de pista y se para.

- [ ] **Step 2: Línea base y lista de `xfail`.**

```bash
uv sync --extra dev --extra search --extra meta
uv run black . && uv run ruff check --fix .
uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX | tee ../g2-base.txt
uv run pytest -p no:cacheprovider -m cronometrado
```

Expected: PASS con exactamente estos XFAIL estrictos. Son los que G₂ pone en verde, con su plan de origen y la tarea que lo hace:

| Test | Plan | Pone en verde |
|---|---|---|
| `tests/test_snapshot.py::test_modelo_con_solo_intentos_fallidos_audita_sin_fail` | A (Tarea 6) | G2.2 |
| los que A marque en su Tarea 3 con `reason="PR-G: <check> no conoce los intentos fallidos (D14)"` (condicionales: copiarlos del cuerpo de la PR-A) | A (Tarea 3) | G2.2 |
| `tests/test_auditor_meta_y_estados.py::test_agreement_editado_con_su_copia_no_es_el_acuerdo_aprobado` | C (Tarea 7) | G2.6 |
| `tests/test_pipeline_fake.py::test_pipeline_fake_con_edicion_de_campo_audita_sin_fail` | C (Tarea 12) | G2.6 |
| `tests/test_audit_aritmetica_ola1.py::test_arithmetic_pasa_en_las_corridas_reales_de_la_ola_1[juez-de-grounding]` | D | G2.5 |
| `tests/test_audit_aritmetica_ola1.py::test_arithmetic_pasa_en_las_corridas_reales_de_la_ola_1[juez-interrumpido-y-reanudado]` | D | G2.5 |
| `tests/test_audit_aritmetica_ola1.py::test_arithmetic_corrida_real_rota_falla_nombrando_la_relacion[juez-sin-su-llamada]` | D | G2.5 |
| `tests/test_pipeline_fake.py::test_pipeline_existence_no_es_publicable` | D (Tarea 7) | G2.5 (sobre `corrida_existence`) |
| `tests/test_pipeline_fake.py::test_pipeline_fake_con_humano_judge_audita_sin_fail` | D (Tarea 7) | G2.10 |
| `tests/test_pipeline_fake.py::test_pipeline_fake_con_edicion_de_dominio_audita_sin_fail` | E (E2.5) | G2.7 |
| `tests/test_pipeline_fake.py::test_pipeline_fake_con_humano_audita_sin_fail` | F (único XFAIL de F tras su revisión, relación 29) | G2.8 (la aserción cambia en G2.5, ver B4) |

Gemelos sin marcador que G₂ **borra**:
- `test_pipeline_fake_con_edicion_de_campo_solo_falla_lo_que_adapta_g2` (C) → G2.6;
- `test_pipeline_fake_con_edicion_de_dominio_solo_falla_lo_que_adapta_g2` (E) → G2.7;
- `test_pipeline_fake_con_juez_solo_falla_lo_que_adapta_g2` (D) → G2.10.

Si la lista real (`-rxX`) difiere, se completa la tabla en el informe y en el cuerpo de la PR. Ningún `xfail` sale de G₂ sin pasar.

---

### Tarea G2.1: Retirar el andamio, corrida 0.8 al día y ayudantes de edición

**Files:**
- Modify: `tests/conftest.py`: quitar `_andamio_entorno_ola2` y su párrafo de la docstring.
- Modify: `tests/audit_fixtures.py`:
  - `write_run_v08`;
  - ayudantes nuevos: `editar_extracciones`, `editar_evaluaciones`, `editar_verificacion`, `editar_meta` y `intento_fallido`.
- Modify: `tests/test_audit_entorno.py`, `tests/test_audit_fixtures.py`.

**Interfaces:**
- Consumes: `_git_state_fijo` (A, Tarea 6); `primera_llamada`, `editar_llamadas` (`audit_fixtures.py`).
- Produces:
  - `write_run_v08(run_dir) -> Path`, además de lo de G₁:
    - pone `run.json.prompt_sha256 = {k: v for k, v in environment.prompt_templates.items() if k.endswith(".md")}`, leído antes de quitar `environment`. Antes de implementarlo, comprobar que `RunInfo` sigue sin `model_config` con `extra="forbid"` (`grep -n "model_config\|ConfigDict" revisia/schemas/artifacts.py`). Hoy no lo tiene, así que la clave sobrante se ignora al validar; si A lo añadiera, `prompt_sha256` no se repone y se anota (M7);
    - quita `status` y `error` de cada línea de diario, `outcome` de cada efecto de `00_protocol/effects.yml` y el `id` de cada dominio de `07_rob/assessments.json` (y de su copia `manifest.risk_of_bias`). Todo con `del` dentro de funciones.
  - `editar_extracciones(run, fn)` / `editar_evaluaciones(run, fn)`: editan `05_extraction/extractions.json` / `07_rob/assessments.json` (mapas `study_id → registro`, `artifacts.py:578`) y su copia en el manifiesto si la hay (`risk_of_bias`).
  - `editar_verificacion(run, fn)`: `06_synthesis/verification.json` y `manifest.verification`.
  - `editar_meta(run, fn)`: `08_meta/meta_analysis.json` y `manifest.meta_analysis`, las dos copias (M4).
  - `intento_fallido(run, **cambios) -> dict`: una línea de `llm_calls.jsonl` con `outcome: "transient_error"`, `attempt: 1`, proveedor `fake`, `stage: "screening_ta"`, `record_id: "x"` y `timestamp_utc = primera_llamada(run).isoformat()` (I11: la fecha cae dentro de la corrida). Los `cambios` la ajustan.

- [ ] **Step 1: Tests que fallan.** En `tests/test_audit_entorno.py`, el test de la corrida 0.8 se renombra y cambia:

```python
def test_corrida_08_falla_en_environment_y_prompts_y_el_resto_es_diagnostico(corrida) -> None:
    report = auditar(write_run_v08(corrida))
    fallos = {c.check_id for c in report.checks if c.status == "FAIL"}
    assert {"environment", "prompts"} <= fallos
    assert fila(report, "environment").detail == f"{PRE_OLA2_RUN}."
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []
```

En `tests/test_audit_fixtures.py` (imports: `json`, `JOURNAL_PATHS`, `write_run_v08`, `intento_fallido`, `primera_llamada`):

```python
def test_write_run_v08_vuelve_a_la_forma_08(corrida) -> None:
    write_run_v08(corrida)
    run = json.loads((corrida / "run.json").read_text("utf-8"))
    assert "environment" not in run and run["prompt_sha256"]
    for rel in JOURNAL_PATHS.values():
        if (corrida / rel).exists():
            for linea in (corrida / rel).read_text("utf-8").splitlines():
                assert not {"status", "error"} & set(json.loads(linea)), rel
    rob = json.loads((corrida / "07_rob" / "assessments.json").read_text("utf-8"))
    assert all("id" not in d for a in rob.values() for d in a["domains"])


def test_sin_andamio_el_entorno_lo_escribe_el_motor(corrida) -> None:
    import conftest

    assert not hasattr(conftest, "_andamio_entorno_ola2")
    run = json.loads((corrida / "run.json").read_text("utf-8"))
    assert run["environment"]["git_commit"] == "0" * 40  # _git_state_fijo (A)


def test_intento_fallido_cae_dentro_de_la_corrida(corrida) -> None:
    linea = intento_fallido(corrida)
    assert linea["timestamp_utc"] == primera_llamada(corrida).isoformat()
    assert (linea["outcome"], linea["attempt"]) == ("transient_error", 1)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_entorno.py tests/test_audit_fixtures.py -v -k "08 or andamio or intento"`
Expected: FAIL (`ImportError: intento_fallido`; el andamio sigue ahí).

- [ ] **Step 3: Implementar** según Interfaces. `prompts` todavía no conoce el esquema v1, así que `test_corrida_08_falla_en_environment_y_prompts…` lleva `xfail(strict=True, reason="G2.2: prompts esquema v1")` hasta G2.2.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX`
Expected: PASS; XFAIL = los de G2.0 más el de G2.2.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/audit_fixtures.py tests/test_audit_entorno.py tests/test_audit_fixtures.py
git commit -m "test(audit): sin andamio de environment (PR-A lo escribe), corrida 0.8 al día y ayudantes de edición" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.2: Procedencia por intento: `prompts` y relaciones 19, 20 y 21

**Files:**
- Modify: `revisia/audit/checks_provenance.py` (`check_prompts`, hoy `:289-307`).
- Modify: `revisia/audit/checks_journals.py`: `_calls` (relación 20); `_diarios`/`_revisar_diario`/`_llamadas_esperadas` (relaciones 12 y 19).
- Create: `revisia/audit/checks_calls.py` (relación 21).
- Modify: `revisia/audit/checks_flow.py` (`collect_relations`: una línea por familia nueva).
- Test: `tests/test_audit_intentos.py` (nuevo).

**Interfaces:**
- Consumes:
  - `APPLIED_PARAMS: dict[str, frozenset[AppliedParam]]` (A, Tarea 2, `revisia/llm/meta.py`);
  - líneas no-`ok` en `llm_calls.jsonl` (A, Tarea 3): los intentos fallidos no necesitan diario, y la última meta de una línea `failed` **no** tiene por qué ser `deterministic_error`.
- Produces:
  - `check_prompts` (§11.2, §19 fila 1), sobre las llamadas **crudas** (`ctx.llm_calls`), sin depender del manifiesto (en benchmark no lo hay, G2.9):
    - FAIL `f"esquema v1: {n} llamada(s) sin outcome/attempt (anterior a la Ola 2)"` si alguna llamada no trae la clave `outcome` o `attempt`.
    - FAIL `f"{n} llamada(s) ok sin prompt_template (relación 19)"` si alguna con `outcome == "ok"` no la trae. **Esta regla vive solo aquí** (I7): `environment` sigue comprobando únicamente la pertenencia y el hash de las plantillas que sí vienen.
    - WARN `"llamadas ok sin hash de prompt o de respuesta (ver `schemas`)"`, como hoy.
    - WARN `f"intentos fallidos: {f}/{n} llamadas ({p:.0%}) > 20 %"`.
    - PASS `f"{ok}/{n} llamadas ok con prompt_sha256, response_sha256, prompt_template y outcome; {n - ok} intento(s) fallido(s)."`.
  - `_calls` (relación 20): `models_used` y `deterministic_token_level` se recalculan sobre las llamadas con `outcome == "ok"`. Una llamada sin `outcome` cuenta como `ok`, para diagnosticar una 0.8. La relación se llama `"20 · models_used == modelos de las llamadas ok"`.
  - Relación 12 adaptada a intentos:
    - `_llamadas_esperadas` cuenta solo metas `ok` por rol;
    - una línea `failed` puede tener menos metas `ok` que las esperadas, incluso ninguna;
    - las metas no-`ok` de una línea también deben estar en `llm_calls.jsonl`.
  - Relación 19 (completa): cada llamada `ok` de `llm_calls.jsonl` está, idéntica, en las `metas` de alguna línea de diario de su `stage` y `record_id`.
    - Las huérfanas `ok` solo se admiten si `run.json.resumes` no está vacío (una caída a mitad de registro; A, Tarea 3). Con `resumes` son no verificables (WARN de `arithmetic`, con el número); sin `resumes`, la relación se rompe: `"19 · llamada ok sin su línea de diario: <stage>/<record_id>"`.
    - Las no-`ok` no necesitan diario.
  - `checks_calls.py`: `parametros_aplicados(ctx, rel)`, familia `"relaciones de la procedencia aplicada (21)"`. Para cada llamada con `provider` en `APPLIED_PARAMS` y cada `p ∈ {"seed", "temperature", "top_p"}`:
    - si `p ∉ APPLIED_PARAMS[provider]`, `f"{p}_applied"` debe ser `None` (`"21 · <p>_applied no nulo en <provider>"`);
    - `deterministic is True` solo con `provider == "fake"` (`"21 · deterministic fuera de fake"`);
    - un `provider` desconocido rompe la relación (`"21 · proveedor desconocido"`).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_audit_intentos.py`:

```python
"""Procedencia por intento: `prompts` y relaciones 19, 20 y 21 (spec 2026-10-18 §4.3, §11.2)."""

from __future__ import annotations

import pytest
from audit_fixtures import _llamadas, auditar, edit_json, editar_llamadas, fila, intento_fallido


def _quitar_outcome(llamadas: list[dict]) -> None:
    del llamadas[0]["outcome"]


def test_prompts_corrida_real_pasa(corrida) -> None:
    assert fila(auditar(corrida), "prompts").status == "PASS"


def test_prompts_llamada_sin_outcome_es_esquema_v1(corrida) -> None:
    editar_llamadas(corrida, _quitar_outcome)
    detalle = fila(auditar(corrida), "prompts").detail
    assert "esquema v1: 1 llamada(s) sin outcome/attempt" in detalle


def test_prompts_llamada_ok_sin_plantilla_falla(corrida) -> None:
    editar_llamadas(corrida, lambda ll: ll[0].update(prompt_template=None))
    assert "sin prompt_template (relación 19)" in fila(auditar(corrida), "prompts").detail


def test_prompts_muchos_intentos_fallidos_solo_advierten(corrida) -> None:
    n = len(_llamadas(corrida))
    editar_llamadas(corrida, lambda ll: ll + [intento_fallido(corrida)] * n)
    report = auditar(corrida)
    assert fila(report, "prompts").status == "WARN" and report.publishable


def test_relacion_20_modelo_con_solo_intentos_fallidos_no_va_en_models_used(corrida) -> None:
    editar_llamadas(corrida, lambda ll: ll + [intento_fallido(corrida, model="otro")])
    assert fila(auditar(corrida), "arithmetic").status == "PASS"


def test_relacion_19_llamada_ok_huerfana_sin_reanudar_falla(corrida) -> None:
    editar_llamadas(corrida, lambda ll: ll + [intento_fallido(corrida, outcome="ok")])
    detalle = fila(auditar(corrida), "arithmetic").detail
    assert "19 · llamada ok sin su línea de diario" in detalle


def test_relacion_19_huerfana_en_corrida_reanudada_solo_advierte(corrida) -> None:
    editar_llamadas(corrida, lambda ll: ll + [intento_fallido(corrida, outcome="ok")])
    marca = intento_fallido(corrida)["timestamp_utc"]
    edit_json(corrida / "run.json", lambda r: r.update(resumes=[marca]))
    assert fila(auditar(corrida), "arithmetic").status == "WARN"


@pytest.mark.parametrize(
    ("proveedor", "campo"),
    [
        ("claude_code", "seed_applied"),
        ("claude_code", "temperature_applied"),
        ("anthropic", "seed_applied"),
    ],
)
def test_relacion_21_parametro_aplicado_que_el_backend_no_admite_falla(
    corrida, proveedor: str, campo: str
) -> None:
    editar_llamadas(corrida, lambda ll: ll[0].update(provider=proveedor, **{campo: 0}))
    detalle = fila(auditar(corrida), "arithmetic").detail
    assert f"21 · {campo} no nulo en {proveedor}" in detalle


def test_relacion_21_deterministic_solo_en_fake(corrida) -> None:
    editar_llamadas(corrida, lambda ll: ll[0].update(provider="gemini", deterministic=True))
    assert "21 · deterministic fuera de fake" in fila(auditar(corrida), "arithmetic").detail


def test_prompts_hostil_falla_acotado(corrida) -> None:
    editar_llamadas(corrida, lambda ll: ll[0].update(outcome=["x"] * 100_000, attempt="y"))
    prompts = fila(auditar(corrida), "prompts")
    assert prompts.status == "FAIL" and "error interno" not in prompts.detail
    assert len(prompts.detail) < 2_000
```

Además se retiran:
- el `xfail` de `test_modelo_con_solo_intentos_fallidos_audita_sin_fail` (A);
- los condicionales de la Tarea 3 de A;
- el de `test_corrida_08_falla_en_environment_y_prompts…` (G2.1).

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_intentos.py -v`
Expected: FAIL (`prompts` en PASS con una llamada v1; `models_used` cuenta el intento fallido).

- [ ] **Step 3: Implementar** según Interfaces (docstrings: D14, §19 fila 1, por qué las huérfanas `ok` solo valen en una corrida reanudada).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX`
Expected: PASS; XFAIL = lista de G2.0 menos los de A.

- [ ] **Step 5: Commit**

```bash
git add revisia/audit tests/test_audit_intentos.py tests/test_audit_entorno.py tests/test_snapshot.py
git commit -m "feat(audit): procedencia por intento: prompts (esquema v1), relaciones 19, 20 y 21 (D14, A6)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.3: `timing` y `response_overlap` con intentos

**Files:**
- Modify: `revisia/audit/checks_timing.py` (`check_timing` `:209`, `check_response_overlap` `:319`).
- Test: `tests/test_audit_timing.py` (añadir).

**Interfaces:**
- `check_timing`:
  - las heurísticas (mediana, ráfagas, solapes) usan solo las llamadas `outcome == "ok"` (o sin `outcome`), y los límites temporales se aplican a **todas**;
  - FAIL nuevo: dentro de cada `(stage, record_id, role)`, en el orden de `llm_calls.jsonl`, cada `attempt` es `1` o el anterior + 1. Si no: `"attempt fuera de orden: <stage>/<record_id> (<a> tras <b>)"`.
  - Opcional (M6): un reinicio a 1 sin intento `ok` previo de esa clave exige que `run.json.resumes` no esté vacío. Si se implementa, va con su test; si no, queda anotado.
- `check_response_overlap`: WARN nuevo si dos llamadas `agent` del mismo `(stage, record_id)` con roles distintos tienen `model_source == "config"` y el mismo `model`. Detalle: `"dos miembros agent con el modelo de la configuración (model_source: config): pueden ser el mismo modelo (A8)"`.

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_audit_timing.py` (imports de `audit_fixtures`: `auditar`, `editar_llamadas`, `fila`, `reetiquetar_llamadas`):

```python
def _salto(llamadas: list[dict]) -> None:
    llamadas[0]["attempt"] = 3


def test_timing_attempt_fuera_de_orden_falla(corrida) -> None:
    editar_llamadas(corrida, _salto)
    assert "attempt fuera de orden" in fila(auditar(corrida), "timing").detail


def test_timing_reintentos_al_final_en_orden_pasan(corrida) -> None:
    def _reintentos(llamadas: list[dict]) -> list[dict]:
        # Se AÑADEN al final (I10): un intento nuevo del primer registro, 1 y 2, tras su ok.
        base = {**llamadas[-1], "record_id": llamadas[0]["record_id"],
                "stage": llamadas[0]["stage"], "role": llamadas[0].get("role"),
                "outcome": "invalid_output"}
        return [*llamadas, {**base, "attempt": 1}, {**base, "attempt": 2}]

    editar_llamadas(corrida, _reintentos)
    timing = fila(auditar(corrida), "timing")
    assert timing.status in {"PASS", "WARN"} and "attempt" not in timing.detail


def _config(llamadas: list[dict]) -> None:
    for llamada in llamadas:
        llamada["model_source"] = "config"


def test_response_overlap_dos_agent_con_modelo_de_config_avisa(corrida) -> None:
    reetiquetar_llamadas(corrida, provider="agent")
    editar_llamadas(corrida, _config)
    overlap = fila(auditar(corrida), "response_overlap")
    assert overlap.status == "WARN" and "model_source: config" in overlap.detail
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_timing.py -v -k "attempt or reintentos or config"`
Expected: FAIL.

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX`
Expected: PASS; sin XFAIL nuevos.

- [ ] **Step 5: Commit**

```bash
git add revisia/audit/checks_timing.py tests/test_audit_timing.py
git commit -m "feat(audit): timing con intentos ordenados y response_overlap con model_source (D14, A8)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.4: Relación 22 en el cribado, exenciones de los fallidos y ediciones efectivas

**Files:**
- Create: `revisia/audit/checks_failed.py`.
- Modify: `revisia/audit/checks_ledger.py`: ayudante nuevo `ediciones_efectivas`.
- Modify: `revisia/audit/checks_journals.py` (`_contra_diario`/`_consolidados`: la salida de una línea `failed` es la del registro fallido), `revisia/audit/checks_artifacts.py` (`_matriz_desde_gold`: exime los fallidos, como `compute_screening_metrics`), `revisia/audit/checks_flow.py` (`_recuperacion`: un FT fallido está recuperado sin voto; `collect_relations`: familia nueva), `revisia/audit/checks_request_hash.py` (`_decision_del_ledger`: un fallido sin etiqueta no está «sin etiquetar» si llega en `failed`).
- Modify: `tests/conftest.py`: `_corrida_con_fallo_ta`/`corrida_con_fallo_ta`.
- Test: `tests/test_audit_fallos.py` (nuevo).

**Interfaces:**
- Consumes:
  - `gates.failed_ids(decisions)` (C, T11), `failed_extraction(study_id, form_fields, *, source_text, text_sha256, truncated)` (C, T5) y `failed_assessment(spec, study_id, *, source_text)` (E);
  - `JournalEntry` v2 (`status`, `error`), `ScriptedProvider(fail_deterministic_at=…)` (PR-0).
- Produces:
  - `checks_ledger.ediciones_efectivas(ctx, stage: str) -> list[DecisionEntry]` (I9): las `edit_field`/`edit_domain`/`rescue_text` de la decisión efectiva de `stage` (mismo `decision_sha256` que su `approve`), en el orden del ledger. Es el ayudante **único** que usan G2.6 y G2.7.
  - `checks_failed.py`:
    - `lineas_fallidas(ctx, stage) -> dict[str, JournalEntry]`: las líneas `status == "failed"` del diario de `stage`, por `record_id`; si un registro tiene varias, vale la última.
    - `salida_de_linea_fallida(ctx, stage, entry) -> dict` (I3): la «salida del diario» de una línea fallida, para comparar el consolidado y para `apply_*_edits`. En T/A y FT es el `ScreeningDecision` sin votos de C (T11); en `extraccion`, `failed_extraction(id, form_fields, source_text=…, text_sha256=…, truncated=…)`, con los datos de `retrieval.json`; en `rob`, `failed_assessment(spec, id, source_text=…)`.
    - `fallidos_del_cribado(ctx, rel)`, familia `"relaciones de los diarios con fallo (22)"`. Relación 22 completa (I3):
      - una línea `failed` implica que el consolidado de ese registro es el fallido (T/A y FT: `ensemble_label is None`, `votes == []`; extracción y RoB: `status == "failed"`);
      - con el gate aprobado, `human_label is not None` (cribado).
      - Mensajes: `"22 · registro fallido sin decisión humana: <ids>"`, `"22 · registro fallido con propuesta de la IA: <ids>"`, `"22 · línea failed sin consolidado fallido: <stage>/<id>"`.
      - Las ediciones obligatorias de extracción y RoB las comprueban `extraction` y `rob` (G2.6, G2.7) con `ediciones_efectivas`.
  - Exenciones, todas con `failed_ids`/`lineas_fallidas`:
    - relación 13: se compara el consolidado con `salida_de_linea_fallida`;
    - matriz desde el gold: los fallidos fuera, con nota;
    - cota inferior de llamadas: se descuentan los fallidos.
  - `tests/conftest.py`: `_corrida_con_fallo_ta` (sesión) y `corrida_con_fallo_ta` (copia por test). Se construye con `_correr(..., proveedor=lambda cfg: ScriptedProvider(model=cfg.model, palabras=PALABRAS_FT, fail_deterministic_at=1))`, la misma configuración que la Tarea 11 de C (M8), y la revisora `etiquetar_auditoria`, que etiqueta lo que `must_label` pide.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_audit_fallos.py`:

```python
"""Relación 22 (spec 2026-10-18 §4.3, D9): diarios con fallo determinista."""

from __future__ import annotations

import json
from pathlib import Path

from audit_fixtures import auditar, edit_json, fila


def _primer_fallido(run: Path) -> str:
    diario = run / "03_screening" / "journal.jsonl"
    lineas = [json.loads(x) for x in diario.read_text("utf-8").splitlines()]
    return next(x["record_id"] for x in lineas if x.get("status") == "failed")


def _editar_decision(run: Path, record_id: str, **cambios: object) -> None:
    def _editar(decisiones: list[dict]) -> None:
        for decision in decisiones:
            if decision["record_id"] == record_id:
                decision.update(cambios)

    edit_json(run / "03_screening" / "decisions.json", _editar)


def test_corrida_con_fallo_determinista_en_ta_audita_sin_fail(corrida_con_fallo_ta) -> None:
    report = auditar(corrida_con_fallo_ta)
    assert {c.check_id for c in report.checks if c.status == "FAIL"} == set()


def test_relacion_22_fallido_sin_decision_humana_falla(corrida_con_fallo_ta) -> None:
    fallido = _primer_fallido(corrida_con_fallo_ta)
    _editar_decision(corrida_con_fallo_ta, fallido, human_label=None, final_label=None)
    detalle = fila(auditar(corrida_con_fallo_ta), "arithmetic").detail
    assert "22 · registro fallido sin decisión humana" in detalle


def test_relacion_22_fallido_con_propuesta_de_la_ia_falla(corrida_con_fallo_ta) -> None:
    fallido = _primer_fallido(corrida_con_fallo_ta)
    _editar_decision(corrida_con_fallo_ta, fallido, ensemble_label="include")
    detalle = fila(auditar(corrida_con_fallo_ta), "arithmetic").detail
    assert "22 · registro fallido con propuesta de la IA" in detalle
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_fallos.py -v`
Expected: FAIL (`test_corrida_con_fallo…` con FAIL en `arithmetic`/`thresholds`: el auditor de la Ola 1 no conoce las líneas `failed`; los otros, sin la relación 22).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && wc -l revisia/audit/*.py`
Expected: PASS; sin XFAIL nuevos; ningún módulo > 900.

- [ ] **Step 5: Commit**

```bash
git add revisia/audit tests/conftest.py tests/test_audit_fallos.py
git commit -m "feat(audit): relación 22 (diarios con fallo, D9), exenciones de los fallidos y ediciones efectivas por etapa" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.5: `grounding` por juez (D2, D15, D24; relación 28)

**Files:**
- Create: `revisia/audit/checks_grounding.py`: `check_grounding`, `_adjudications` e `_indices` **salen** de `checks_quality.py:377-492`, más lo nuevo.
- Modify: `revisia/audit/checks_quality.py` (sin `check_grounding`), `revisia/audit/__init__.py`, `tests/test_audit_paquete.py` (`grounding` → `checks_grounding`).
- Modify: `revisia/audit/checks_journals.py`: `_llamadas_esperadas` (`checks_flow.py:1550-1559` del original) y `_consolidados`. En `judge` no se exige la línea `verificacion`; cada `check:<i>:<id>` lleva exactamente una llamada `ok` o es `failed`.
- Modify: `revisia/audit/checks_artifacts.py`: `STAGE_ARTIFACTS_OLA1["sintesis"]` exige `06_synthesis/verification.jsonl` solo si el modo lo produce.
- Modify: `tests/conftest.py` (B2):
  - `protocolo_auditoria` pasa a `grounding: judge` con `llm.verificador: {provider: fake, model: fake-juez, temperature: 0.0}`;
  - `proveedor_auditoria` responde a `fake-juez` con `ScriptedProvider(model=cfg.model, judge=GUION_JUEZ)` (D);
  - fixtures nuevas `protocolo_existence` (el de antes: `existence`), `_corrida_existence` y `corrida_existence`;
  - `protocolo_con_cita_marcada` deriva del nuevo `protocolo_auditoria` **conservando `judge`**: el juez fail-closed marca `[10.1000/llm-1]` y la revisora lo adjudica, así que `corrida_con_cita_marcada` sigue siendo «una cita marcada y adjudicada». Si algún índice o texto de sus tests cambia, se lista en el commit.
- Modify: `tests/test_pipeline_fake.py` (B4):
  - `test_pipeline_existence_no_es_publicable` pasa a `corrida_existence` y pierde el `xfail`;
  - `test_pipeline_fake_con_humano_audita_sin_fail` (el demo, que sigue en `existence` hasta PR-I) cambia su aserción a `fallos == {"grounding"}` (con `report.publishable is False`) y conserva el `xfail` de F con la razón `"G2.8: relación 29"`, que G2.8 solo retira;
  - `AVISOS_DE_LA_DEMO` pierde `grounding`.
- Test: `tests/test_audit_grounding.py` (nuevo).

**Interfaces:**
- Consumes (D, «Interfaces para G₂ (relación 28)»):
  - `split_claims(text, corpus_ids)`, `uncited_quantitative(text, corpus_ids)` e `is_grounded(mode, *, exists, source_available, numbers_missing, verdict_grounded, quote_status)` (`revisia/agents/verificador.py`);
  - `claim_numbers_missing(claim, sources, abstracts)` (I1: la unión de fuente y resumen de las citas del corpus; **no** `missing_numbers` directo);
  - `source_window(sentence, fuente, *, abstract, max_chars).sha256` y `support_quote_status(quote, fuente, *, abstract)` (`revisia/rag/grounding.py`);
  - `JUDGE_FAILED_NOTE`, `VerificationReport.n_judge_failed`, `vendor_of` (`revisia/llm/vendors.py`; `vendor_of("fake") is None`), `protocol.grounding`, `grounding_alias`, `protocol.llm.verificador`, `protocol.verificador.max_source_chars`, `provider_for("sintesis")`;
  - `manifest.verification.{mode, judge}` y `leer_deposito`/`texto_retenido` (G₁).
- Produces: `check_grounding(ctx) -> Verdict`, en este orden:
  - **Corrida 0.8, que corta la evaluación (B1).** Se reconoce si se cumple cualquiera de estas condiciones:
    - `mode` ausente en el JSON **crudo** de `verification.json`;
    - `grounding_alias == "agent"` en el protocolo de la instantánea;
    - `mode == "judge"` y `verification.jsonl` tiene una sola línea `verificacion` con metas.

    Detalle: `"verificación anterior a la Ola 2 (modo agent, línea única `verificacion`): sin juez distinto del redactor (D2)"`. No se mira `llm.verificador`: las corridas `existence`/`embedder` también tienen una sola línea y no son 0.8.
  - **FAIL que cortan la evaluación:**
    - `mode == "existence"`: `"modo `existence` (D2): las citas solo se comprobaron por existencia; una corrida publicable exige `grounding: judge`"`;
    - `mode == "embedder"`: `"modo `embedder` (D2, experimental): no sirve para una corrida publicable; usa `grounding: judge`"`.
  - **FAIL que se acumulan**, cada subcomprobación en su `guard` (I8):
    - `mode ≠ protocol.grounding`, o `manifest.verification` ≠ `{mode, judge}`;
    - `judge` == `provider_for("sintesis")` (`"juez == redactor (`<p>:<m>`)"`), o `judge` ≠ `llm.verificador`;
    - afirmaciones recalculadas desde la narrativa de `documento.md` con `split_claims(…, incluidos)`, cuyo número o pares `(claim_index, cited_id)` ≠ `checks`: `"afirmaciones recalculadas ≠ checks"`;
    - `n_uncited_quantitative ≠ len(uncited_quantitative(…))`;
    - por comprobación: `numbers_missing` ≠ `claim_numbers_missing(claim, sources, abstracts)`, `quote_status` ≠ `support_quote_status(…)` o `grounded` ≠ `is_grounded(…)`, con `verdict_grounded` de la salida de su línea o `None` si es `failed`: `"grounded recalculado ≠ en <índices>"`;
    - en `judge`, cada comprobación con `exists_in_corpus and source_available and not numbers_missing` tiene su línea `check:<i>:<id>` (con una cifra ausente D no llama al juez y no escribe línea, D §19 n+4; si ninguna comprobación se juzga, no hay `verification.jsonl`):
      - con exactamente una llamada `ok`, o `status: failed` con la nota `JUDGE_FAILED_NOTE`;
      - `inputs.ventana_sha256 == source_window(…).sha256`;
      - `input_sha256 == canonical_sha256({claim, cited_id, fuente_sha256, ventana_sha256, modo: "judge", juez: [f"{p}:{m}", temperature, seed]})`, el contrato de D (M5).
      - Mensajes: `"comprobación sin su línea check:<i>:<id>"`, `"ventana_sha256 recalculada ≠ en <índices>"`, `"input_sha256 de check:<i> ≠ recalculado"`;
    - lo de hoy: marcas sin adjudicar, bandera incoherente, `exists_in_corpus` falso.
  - **Depósito (n+9):** con `deposit.json` válido, `numbers_missing`, `quote_status` y `ventana_sha256` de las comprobaciones cuya fuente es un texto retenido se dan por verificados con `texto_retenido` y el detalle anota `"<n> comprobaciones verificadas por hash (copia de depósito)"`.
  - **WARN:**
    - mismo fabricante (`vendor_of(juez) == vendor_of(redactor) is not None`): `"juez de la misma familia que el redactor (D24)"`;
    - `n_uncited_quantitative > 0`;
    - `n_judge_failed > 0`: `"<n> comprobaciones con el juez fallido (D9): adjudicadas por el humano"`;
    - marcadas, todas adjudicadas;
    - `window_truncated` en alguna comprobación;
    - la síntesis no cita ningún estudio teniendo incluidos (el WARN de D, `test_c2_…`).
  - **PASS:** `f"modo judge · juez {p}:{m} ≠ redactor · {n_claims} afirmaciones recalculadas iguales · {n} comprobaciones ({k} con su línea check:<i>:<id>) · ninguna marcada."`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_audit_grounding.py`:

```python
"""`grounding` por juez (spec 2026-10-18 §11.2, D2, D15, D24; relación 28)."""

from __future__ import annotations

import json
from pathlib import Path

from audit_fixtures import auditar, edit_json, editar_protocolo, editar_verificacion, fila
from conftest import PALABRAS_FT, _correr, adjudicar_auditoria, proveedor_con_juez
from fakes import ScriptedProvider


def _lineas(run: Path) -> list[dict]:
    diario = run / "06_synthesis" / "verification.jsonl"
    return [json.loads(x) for x in diario.read_text(encoding="utf-8").splitlines()]


def _escribir(run: Path, lineas: list[dict]) -> None:
    texto = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lineas)
    (run / "06_synthesis" / "verification.jsonl").write_text(texto, encoding="utf-8")


def test_grounding_judge_coherente_avisa_solo_por_la_adjudicada(corrida_con_juez) -> None:
    report = auditar(corrida_con_juez)
    assert fila(report, "grounding").status == "WARN" and report.publishable


def test_corrida_de_auditoria_en_judge_sigue_apta(corrida) -> None:
    report = auditar(corrida)
    assert report.publishable and fila(report, "grounding").status in {"PASS", "WARN"}


def test_grounding_existence_es_fail_d2(corrida_existence) -> None:
    grounding = fila(auditar(corrida_existence), "grounding")
    assert grounding.status == "FAIL" and "modo `existence` (D2)" in grounding.detail


def _sin_mode(verificacion: dict) -> None:
    del verificacion["mode"]


def test_grounding_08_sin_mode_es_anterior_a_la_ola_2(corrida_con_juez) -> None:
    edit_json(corrida_con_juez / "06_synthesis" / "verification.json", _sin_mode)
    detalle = fila(auditar(corrida_con_juez), "grounding").detail
    assert "anterior a la Ola 2" in detalle


def test_grounding_existence_no_se_confunde_con_una_08(corrida_existence) -> None:
    assert "anterior a la Ola 2" not in fila(auditar(corrida_existence), "grounding").detail


def test_grounding_juez_igual_al_redactor_falla(corrida_con_juez) -> None:
    editar_verificacion(
        corrida_con_juez, lambda v: v.update(judge={"provider": "fake", "model": "fake-1"})
    )
    assert "juez == redactor" in fila(auditar(corrida_con_juez), "grounding").detail


def test_grounding_afirmacion_anadida_al_documento_sin_check_falla(corrida_con_juez) -> None:
    doc = corrida_con_juez / "deliverable" / "documento.md"
    texto = doc.read_text(encoding="utf-8")
    doc.write_text(texto + "\nEl cribado ahorra 99% [10.1000/asreview].\n", encoding="utf-8")
    detalle = fila(auditar(corrida_con_juez), "grounding").detail
    assert "afirmaciones recalculadas ≠ checks" in detalle


def test_grounding_grounded_manipulado_falla(corrida_con_juez) -> None:
    editar_verificacion(corrida_con_juez, lambda v: v["checks"][-1].update(grounded=True))
    assert "grounded recalculado ≠" in fila(auditar(corrida_con_juez), "grounding").detail


def test_grounding_comprobacion_sin_su_linea_falla(corrida_con_juez) -> None:
    _escribir(corrida_con_juez, _lineas(corrida_con_juez)[1:])
    assert "sin su línea check:" in fila(auditar(corrida_con_juez), "grounding").detail


def test_grounding_cifra_ausente_no_exige_linea_ni_da_fail(tmp_path, protocolo_con_juez) -> None:
    # D §19 n+4: con una cifra ausente el juez no se llama y no hay línea check:<i>:<id>.
    def _proveedor(cfg):
        if cfg.model == "fake-1":
            sintesis = "LLM screening reached a recall of 0.55 [10.1000/llm-1]."
            return ScriptedProvider(model=cfg.model, palabras=PALABRAS_FT, sintesis=sintesis)
        return proveedor_con_juez(cfg)

    run = _correr(
        tmp_path,
        protocolo_con_juez,
        parar_en=None,
        proveedor=_proveedor,
        etiquetar=adjudicar_auditoria,
    )
    verificacion = json.loads(
        (run / "06_synthesis" / "verification.json").read_text(encoding="utf-8")
    )
    assert verificacion["checks"][0]["numbers_missing"] == ["0.55"]
    assert not (run / "06_synthesis" / "verification.jsonl").exists()
    grounding = fila(auditar(run), "grounding")
    assert grounding.status != "FAIL" and "sin su línea check:" not in grounding.detail


def test_grounding_ventana_manipulada_falla(corrida_con_juez) -> None:
    lineas = _lineas(corrida_con_juez)
    lineas[0]["inputs"]["ventana_sha256"] = "0" * 64
    _escribir(corrida_con_juez, lineas)
    detalle = fila(auditar(corrida_con_juez), "grounding").detail
    assert "ventana_sha256 recalculada ≠" in detalle


def test_grounding_mismo_fabricante_avisa(corrida_con_juez) -> None:
    # vendor_of("fake") is None (I2): se usa anthropic frente a claude_code, mismo fabricante.
    def _protocolo(p: dict) -> None:
        p["llm"]["sintesis"] = {"provider": "claude_code", "model": "opus"}
        p["llm"]["verificador"] = {"provider": "anthropic", "model": "claude-sonnet"}

    editar_protocolo(corrida_con_juez, _protocolo)
    editar_verificacion(
        corrida_con_juez,
        lambda v: v.update(judge={"provider": "anthropic", "model": "claude-sonnet"}),
    )
    assert "misma familia" in fila(auditar(corrida_con_juez), "grounding").detail


def test_grounding_hostil_falla_acotado(corrida_con_juez) -> None:
    editar_verificacion(corrida_con_juez, lambda v: v.update(checks="x" * 1_000_000))
    grounding = fila(auditar(corrida_con_juez), "grounding")
    assert grounding.status == "FAIL" and "error interno" not in grounding.detail
    assert len(grounding.detail) < 2_000
```

Para que `test_grounding_mismo_fabricante_avisa` aísle el aviso de D24, el `editar_protocolo` también renombra el proveedor en las llamadas (`reetiquetar_llamadas`); el resto de filas puede cambiar, pero el test solo mira el aviso.

Además se retiran los `xfail` de D: `[juez-de-grounding]`, `[juez-interrumpido-y-reanudado]`, `[juez-sin-su-llamada]` y `test_pipeline_existence_no_es_publicable` (ahora sobre `corrida_existence`).

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_grounding.py -v`
Expected: FAIL (`existence` sin FAIL; sin recálculo de afirmaciones; `corrida_existence` no existe).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && wc -l revisia/audit/*.py`
Expected: PASS. `corrida` sigue APTA (B2): ninguna de sus aserciones cambia. XFAIL restantes: los de C, E, F y `test_pipeline_fake_con_humano_judge_audita_sin_fail`. `checks_grounding.py` ≤ 900.

- [ ] **Step 5: Commit**

```bash
git add revisia/audit tests
git commit -m "feat(audit): grounding exige juez distinto del redactor y recalcula las afirmaciones (D2, D15, D24; relación 28)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.6: `extraction`, rescate con texto y concordancia (relaciones 22–26)

**Files:**
- Create: `revisia/audit/checks_extraction.py`.
- Modify: `revisia/audit/__init__.py` (fila `extraction` tras `exclusions`), `tests/test_audit_paquete.py`.
- Modify: `revisia/audit/checks_flow.py`: `_recuperacion` (relación 7: un `human_rescue` está disponible con la decisión `not_retrieved`) y `collect_relations` (familias 23 y 26).
- Modify: `revisia/audit/checks_journals.py` (`_consolidados`: relación 13 de `extractions.json` comparada con `apply_field_edits(salidas del diario, …)`; filas `human_rescue` de `retrieval.json` exentas del diario de recuperación).
- Modify: `revisia/audit/checks_request_hash.py`:
  - `_acuerdo_de_la_solicitud`: de `second_extraction` a `concordance` (`CONCORDANCE_FIELDS` + `n_disagreements`);
  - `_contenido`: `artifact_sha256` de `extraccion` = hash de las **salidas del diario**, con `salida_de_linea_fallida` para las fallidas;
  - `_decision_del_ledger`: rehace `records.<id>.fields` (`FieldEdits`) desde `ediciones_efectivas(ctx, "extraccion")` y `text_file` desde `rescue_text` cuando falta `decision.yml` (I4).
- Modify: `tests/test_pipeline_fake.py`: retirar el `xfail` de `test_pipeline_fake_con_edicion_de_campo_audita_sin_fail`, que queda APTA de verdad con `corrida` en `judge` (B2), y borrar `…_solo_falla_lo_que_adapta_g2`.
- Test: `tests/test_audit_extraccion.py` (nuevo).

**Interfaces:**
- Consumes (C, «Contratos para G₂»):
  - `find_quote` (`revisia/text/quotes.py`), `extraccion.quote_source(record, texto_o_None)`, `fulltext.ingest_rescue(ruta, max_chars=…)`;
  - `gates.apply_field_edits(extractions, edits, actor)`, `compute_extraction_agreement(diario, diario_2, expected=[…])`, `CONCORDANCE_FIELDS`, `select_double_extraction_subset`, `canonical_sha256`, `dump_artifact`;
  - las fixtures `corrida_con_edicion_de_campo` (`EDICION_DE_CAMPO`) y `corrida_con_rescate_con_texto` (`RESCATE_CON_TEXTO`);
  - de G2.4: `ediciones_efectivas`, `salida_de_linea_fallida`.
- Produces:
  - `check_extraction(ctx) -> Verdict`, etapa `extraccion`, ítem `"PRISMA 9/10 / trAIce M8"`; cada subcomprobación en su `guard`.
    - Relación 24: `source_text` ⇔ `retrieval.available`; `text_sha256` = el de `retrieval.json`; `quote_status`/`quote_offset` recalculados con `find_quote(quote, quote_source(record, texto))`.
    - Relación 25:
      - `human_edited` ⇔ `edit_field` de `ediciones_efectivas` con ese `target`, `to == human_value`, `reason == human_reason` y `human_actor ==` el actor del `approve`;
      - `final_value == (human_value if human_edited else value)` (M5);
      - `extractions.json == apply_field_edits(salidas del diario, ediciones, actor)`;
      - la clave `extracciones_sha256` del diario `sintesis` == `canonical_sha256(dump_artifact(extractions.json))`.
    - Relación 22 (extracción): `status == "failed"` implica, con el gate aprobado, una `edit_field` por cada clave de `fields`.
    - FAIL: `"human_value sin edit_field: <study>#<key>"`, `"edit_field sin human_value: …"`, `"final_value incoherente: …"`, `"quote_status recalculado ≠: …"`, `"source_text ≠ retrieval: …"`, `"status failed sin editar todas sus claves: <id>"`, `"extractions.json ≠ salidas del diario + ediciones"`.
    - WARN: `"cita de origen no encontrada en campos aprobados sin edición humana: <study>#<key>…"`.
    - PASS: `f"{n} estudios · {e} ediciones humanas con su edit_field · citas recalculadas iguales ({f} sobre texto completo, {a} sobre resumen)."`.
  - Relación 23 (`arithmetic`): `rescates_con_texto(ctx, rel)`, familia `"relaciones del rescate con texto (23)"`.
    - Fila `human_rescue` ⇔ `rescue_text` de `ediciones_efectivas(ctx, "screening_ft")` con ese `target`.
    - `rescue_file == detail.text_file`, `rescue_file_sha256 == sha256(bytes de rescues/<nombre>) == detail.file_sha256`, y el texto en caché (`ruta_del_texto`) == `ingest_rescue(ruta, max_chars=protocol.fulltext.max_chars).text`.
  - Relación 26 (`arithmetic`, solo aquí): `concordancia(ctx, rel)`, familia `"relaciones de la concordancia IA–IA (26)"`. `agreement.json == compute_extraction_agreement(diario, diario_2, expected=subconjunto)` y `n_studies + len(failed_studies) == len(select_double_extraction_subset(incluidos))`.
  - Depósito: las relaciones 23 y 24 sobre ficheros retenidos se dan por verificadas por hash y se anota.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_audit_extraccion.py`:

```python
"""`extraction` y relaciones 22–26 (spec 2026-10-18 §11.2, D3, D4, D21, D22)."""

from __future__ import annotations

import pytest
from audit_fixtures import (
    auditar,
    edit_json,
    edit_ledger,
    edit_yaml,
    editar_extracciones,
    fila,
)
from conftest import EDICION_DE_CAMPO, RESCATE_CON_TEXTO

ESTUDIO, CLAVE = EDICION_DE_CAMPO[0], EDICION_DE_CAMPO[1]


def _sin_ediciones(entradas: list[dict]) -> list[dict]:
    return [e for e in entradas if e["action"] != "edit_field"]


def test_extraction_con_edicion_de_campo_pasa_y_la_corrida_es_apta(
    corrida_con_edicion_de_campo,
) -> None:
    report = auditar(corrida_con_edicion_de_campo)
    assert fila(report, "extraction").status in {"PASS", "WARN"} and report.publishable


def test_human_value_sin_edit_field_falla(corrida_con_edicion_de_campo) -> None:
    edit_ledger(corrida_con_edicion_de_campo, _sin_ediciones)
    detalle = fila(auditar(corrida_con_edicion_de_campo), "extraction").detail
    assert "human_value sin edit_field" in detalle


def test_quote_status_manipulado_falla(corrida_con_edicion_de_campo) -> None:
    editar_extracciones(
        corrida_con_edicion_de_campo,
        lambda ex: ex[ESTUDIO]["fields"][CLAVE].update(quote_status="exact"),
    )
    detalle = fila(auditar(corrida_con_edicion_de_campo), "extraction").detail
    assert "quote_status recalculado ≠" in detalle


def test_final_value_incoherente_falla(corrida_con_edicion_de_campo) -> None:
    editar_extracciones(
        corrida_con_edicion_de_campo,
        lambda ex: ex[ESTUDIO]["fields"][CLAVE].update(human_edited=False),
    )
    detalle = fila(auditar(corrida_con_edicion_de_campo), "extraction").detail
    assert "final_value incoherente" in detalle or "edit_field sin human_value" in detalle


def test_rescate_con_texto_audita_sin_fail(corrida_con_rescate_con_texto) -> None:
    report = auditar(corrida_con_rescate_con_texto)
    assert {c.check_id for c in report.checks if c.status == "FAIL"} == set()


def test_rescate_con_fichero_cambiado_rompe_la_relacion_23(
    corrida_con_rescate_con_texto,
) -> None:
    rescates = corrida_con_rescate_con_texto / "screening_ft" / "rescues"
    fichero = rescates / RESCATE_CON_TEXTO[1]
    fichero.write_bytes(fichero.read_bytes() + b" editado")
    assert "23 · " in fila(auditar(corrida_con_rescate_con_texto), "arithmetic").detail


def test_agreement_manipulado_rompe_la_relacion_26(corrida) -> None:
    # Las dos copias a la vez (fichero y manifiesto): solo se rompe el recálculo (26).
    edit_json(corrida / "05_extraction" / "agreement.json", lambda a: a.update(n_studies=99))
    edit_yaml(
        corrida / "manifest.yml", lambda m: m["extraction_agreement"].update(n_studies=99)
    )
    assert "26 · agreement.json" in fila(auditar(corrida), "arithmetic").detail


@pytest.mark.parametrize("valor", ["x" * 1_000_000, ["no", "es", "un", "mapa"]])
def test_extraction_hostil_falla_acotado(corrida_con_edicion_de_campo, valor: object) -> None:
    editar_extracciones(corrida_con_edicion_de_campo, lambda ex: ex[ESTUDIO].update(fields=valor))
    extraccion = fila(auditar(corrida_con_edicion_de_campo), "extraction")
    assert extraccion.status == "FAIL" and "error interno" not in extraccion.detail
    assert len(extraccion.detail) < 2_000
```

Además se retiran los `xfail` de C: `test_pipeline_fake_con_edicion_de_campo_audita_sin_fail` (APTA de verdad, B2) y `test_agreement_editado_con_su_copia_no_es_el_acuerdo_aprobado`.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_extraccion.py -v`
Expected: FAIL (`sin fila 'extraction'`; relación 13 de `extractions.json` rota con la edición).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && wc -l revisia/audit/*.py`
Expected: PASS; XFAIL restantes: E, F y `test_pipeline_fake_con_humano_judge_audita_sin_fail`; `checks_request_hash.py` ≤ 900.

- [ ] **Step 5: Commit**

```bash
git add revisia/audit tests
git commit -m "feat(audit): check extraction, rescate con texto y concordancia recalculada (relaciones 22-26)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.7: `rob` por herramienta (relaciones 22 y 27)

**Files:**
- Create: `revisia/audit/checks_rob.py`.
- Modify: `revisia/audit/__init__.py` (fila `rob` tras `extraction`), `tests/test_audit_paquete.py`.
- Modify: `revisia/audit/checks_journals.py` (relación 13 de `07_rob/assessments.json` comparada con `apply_domain_edits(salidas del diario, ediciones, actor, spec=spec)`, con `salida_de_linea_fallida` para las fallidas), `revisia/audit/checks_request_hash.py` (`artifact_sha256` de `rob` = hash de las salidas del diario; `_decision_del_ledger` rehace `DomainEdits` desde `ediciones_efectivas(ctx, "rob")` sin `decision.yml`, I4), `revisia/audit/checks_flow.py` (`_herramienta_rob`: GRADE ya no es herramienta).
- Modify: `tests/test_pipeline_fake.py`: retirar el `xfail` de `test_pipeline_fake_con_edicion_de_dominio_audita_sin_fail` (APTA de verdad, B2) y borrar `…_solo_falla_lo_que_adapta_g2`.
- Test: `tests/test_audit_rob.py` (nuevo).

**Interfaces:**
- Consumes (E, «Interfaces para G₂ (relación 27)»):
  - `load_tool_spec(tool)`, `RoBToolSpec.domain_ids`/`domains[i].name`/`scale_for`/`overall_scale`, `revisia.rob.aggregate.aggregate(spec, final_judgments(a))`, `find_quote`;
  - `gates.apply_domain_edits(assessments, edits, actor, *, spec)`, `failed_assessment(spec, rid, source_text=…)`;
  - `edit_domain` en el orden de la especificación con `#overall` al final, y `tool_version` en las `inputs`;
  - `corrida_con_edicion_de_dominio` (`EDICION_DE_DOMINIO`);
  - de G2.4: `ediciones_efectivas`.
- Produces: `check_rob(ctx) -> Verdict`, etapa `rob`, ítem `"PRISMA 11/18 / trAIce M8"`, cada subcomprobación en su `guard`. FAIL acumulados:
  - GRADE (I5): si `rob_tool == "GRADE"` en el protocolo **crudo** de la instantánea (`ctx.protocol_raw`, porque `ctx.protocol` es `None`: `RoBTool` ya no admite GRADE y el protocolo no valida) o en algún `assessment.tool`, FAIL `"GRADE no es una herramienta de riesgo de sesgo por estudio (D5)"`, que corta la evaluación.
  - Identidad:
    - `"tool ≠ protocolo"`, `"tool_version ≠ especificación"`;
    - `"dominio sin id: <study>"` (el check lo exige aunque el esquema lo deje opcional, §19 fila 2);
    - `"dominios ≠ especificación: <study>"` (ids y orden, con `status == "ok"` o `failed` con el gate aprobado);
    - `"nombre de dominio ≠ especificación: <study>#<id>"` (`domain == spec.domains[i].name`, I4).
  - Escalas (I4):
    - `"juicio fuera de escala: <study>#<dominio>"` (`judgment` y `human_judgment ∈ scale_for(id)`);
    - `"overall_human fuera de escala: <study>"` (`∈ overall_scale`);
    - `applicability` según la especificación (QUADAS-2: ids y escala).
  - Agregación:
    - `"overall_algorithm ≠ regla: <study>"`;
    - `"overall ≠ overall_human or overall_algorithm: <study>"`.
    - NOS: el global es un recuento en texto y no se compara con una escala; QUADAS-2: `None`.
  - Ediciones (I4):
    - `human_judgment` ⇔ `edit_domain` de `ediciones_efectivas` con `target == f"{id}#{dominio}"`, `to == human_judgment`, `reason == human_reason`;
    - `overall_human` ⇔ `#overall`;
    - `human_actor ==` el actor del `approve`.
    - Mensajes: `"edición sin edit_domain"`, `"edit_domain sin edición"`, `"human_actor ≠ actor del approve"`.
  - Artefacto: `"assessments.json ≠ salidas del diario + ediciones"`.
  - Relación 22 (RoB): `"status failed sin editar todos sus dominios: <id>"`.
  - Cita: `quote_status` ≠ `find_quote(support_quote, texto crudo)[0]`.

  Lo demás:
  - WARN: `"juicios sin support_quote: <study>#<dominio>…"`.
  - PASS: `f"{tool} ({tool_version}) · {n} estudios · dominios y escalas de la especificación · overall por la regla · {e} ediciones con su edit_domain."`.
  - Depósito: `quote_status` sobre texto retenido, verificado por hash.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_audit_rob.py`:

```python
"""`rob` por herramienta (spec 2026-10-18 §11.2, D5; relaciones 22 y 27)."""

from __future__ import annotations

import pytest
from audit_fixtures import auditar, edit_ledger, editar_evaluaciones, editar_protocolo, fila


def _primer_dominio(evaluaciones: dict) -> dict:
    return next(iter(evaluaciones.values()))["domains"][0]


def _sin_ids(evaluaciones: dict) -> None:
    for evaluacion in evaluaciones.values():
        for dominio in evaluacion["domains"]:
            del dominio["id"]


def _overall_low(evaluaciones: dict) -> None:
    for evaluacion in evaluaciones.values():
        evaluacion["overall_algorithm"] = "low"


def _sin_edit_domain(entradas: list[dict]) -> list[dict]:
    return [e for e in entradas if e["action"] != "edit_domain"]


def test_rob_con_edicion_de_dominio_pasa_y_es_apta(corrida_con_edicion_de_dominio) -> None:
    report = auditar(corrida_con_edicion_de_dominio)
    assert fila(report, "rob").status in {"PASS", "WARN"} and report.publishable


def test_rob_dominio_renombrado_falla(corrida_con_edicion_de_dominio) -> None:
    editar_evaluaciones(
        corrida_con_edicion_de_dominio, lambda ev: _primer_dominio(ev).update(id="D9")
    )
    detalle = fila(auditar(corrida_con_edicion_de_dominio), "rob").detail
    assert "dominios ≠ especificación" in detalle


def test_rob_overall_manipulado_falla(corrida_con_edicion_de_dominio) -> None:
    editar_evaluaciones(corrida_con_edicion_de_dominio, _overall_low)
    detalle = fila(auditar(corrida_con_edicion_de_dominio), "rob").detail
    assert "overall_algorithm ≠ regla" in detalle


def test_rob_dominio_sin_id_falla(corrida) -> None:
    editar_evaluaciones(corrida, _sin_ids)
    assert "dominio sin id" in fila(auditar(corrida), "rob").detail


def test_rob_juicio_humano_fuera_de_escala_falla(corrida_con_edicion_de_dominio) -> None:
    editar_evaluaciones(
        corrida_con_edicion_de_dominio,
        lambda ev: _primer_dominio(ev).update(human_judgment="pésimo"),
    )
    detalle = fila(auditar(corrida_con_edicion_de_dominio), "rob").detail
    assert "fuera de escala" in detalle


def test_rob_edicion_sin_ledger_falla(corrida_con_edicion_de_dominio) -> None:
    edit_ledger(corrida_con_edicion_de_dominio, _sin_edit_domain)
    detalle = fila(auditar(corrida_con_edicion_de_dominio), "rob").detail
    assert "edición sin edit_domain" in detalle


def test_rob_grade_falla_leyendo_el_protocolo_crudo(corrida) -> None:
    editar_protocolo(corrida, lambda p: p.update(rob_tool="GRADE"))
    assert "GRADE" in fila(auditar(corrida), "rob").detail


@pytest.mark.parametrize("valor", ["x" * 1_000_000, {"no": "es una lista"}])
def test_rob_hostil_falla_acotado(corrida, valor: object) -> None:
    editar_evaluaciones(corrida, lambda ev: next(iter(ev.values())).update(domains=valor))
    rob = fila(auditar(corrida), "rob")
    assert rob.status == "FAIL" and "error interno" not in rob.detail
    assert len(rob.detail) < 2_000
```

Se retira el `xfail` de E (`test_pipeline_fake_con_edicion_de_dominio_audita_sin_fail`) y se borra su gemelo.

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_rob.py -v`
Expected: FAIL (`sin fila 'rob'`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && wc -l revisia/audit/*.py`
Expected: PASS; XFAIL restantes: F y `test_pipeline_fake_con_humano_judge_audita_sin_fail`.

- [ ] **Step 5: Commit**

```bash
git add revisia/audit tests
git commit -m "feat(audit): check rob por herramienta: dominios, escalas, agregación y ediciones (relaciones 22 y 27, D5)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.8: `meta_analysis` ligado a los incluidos (relación 29)

**Files:**
- Modify: `revisia/audit/checks_meta.py`:
  - `check_meta_analysis` (nuevo) absorbe `_meta_analisis` y `_meta_entregables`;
  - `_leer_efectos_del_protocolo` recalcula con los incluidos y `random_method`;
  - `_meta_sin_incluidos` se retira.
- Modify: `revisia/audit/checks_flow.py`:
  - `collect_relations` pierde la familia `"relaciones del meta-análisis (§8.1)"`;
  - `_csv`: `total_studies_ma`/`total_reports_ma == n_studies` del recálculo (hoy `len(effects)`, `:1244`).
- Modify: `revisia/audit/checks_artifacts.py` (`check_deliverable` sin el WARN de `_meta_sin_incluidos`), `revisia/audit/__init__.py` (fila `meta_analysis` tras `arithmetic`), `tests/test_audit_paquete.py`.
- Modify: `tests/test_pipeline_fake.py`: **solo** se retira el `xfail` de `test_pipeline_fake_con_humano_audita_sin_fail` (su aserción la cambió G2.5); `tests/test_auditor_meta_y_estados.py`: los tests de §8.1 pasan a leer la fila `meta_analysis` (cada cambio, listado en el commit).
- Test: `tests/test_audit_meta_v2.py` (nuevo).

**Interfaces:**
- Consumes (F, «Interfaces para G₂» y su «CAMBIO tras revisión»):
  - `meta_analyze(effects, measure, *, random_method)`, `MetaAnalysisResult.n_studies`, `outcomes[].studies`, `not_pooled[].study_ids`, `excluded` (sin `k`/`studies`, retirados en F2.2);
  - `ExcludedEffectsFile` (`excluded`, `included_without_effect` **ordenado**), `unit_of_analysis_violations(effects)`;
  - `EffectsFile.multiple_per_study`/`random_method`, `render_forest_markdown(result, display=…, exclusions=…)`, `PI_MIN_K`, `EGGER_MIN_K`;
  - `editar_meta` (G2.1).
- Produces: `check_meta_analysis(ctx) -> Verdict`, etapa `sintesis`, ítem `"PRISMA 13d/20b/20c"`, cada subcomprobación en su `guard`.
  - Sin `effects.yml` en la instantánea: PASS `"sin effects.yml: no hay meta-análisis que comprobar"`. Un `meta_analysis.json` o `excluded_effects.json` presente sin él es FAIL (inventado, como hoy).
  - Relación 29, sobre el **multiconjunto** `(study_id, outcome)` (F, cambio 1):
    - agregados (`outcomes[].studies` y `not_pooled[].study_ids`) + `excluded_effects.excluded` == efectos de la instantánea, contando repeticiones;
    - `kept = efectos ∩ incluidos efectivos` (`04_fulltext/decisions.json`, `final_label == "include"`);
    - `included_without_effect == sorted(incluidos − con efecto)`;
    - `meta_analysis.json` == recálculo campo a campo con `_meta_distinto` (que ignora `p_value`/`p_method`);
    - `excluded == len(excluded_effects.excluded)`;
    - `prediction_interval is None ⇔ k < PI_MIN_K`, y `egger is None ⇔ k < EGGER_MIN_K` o `egger_note` de precisión constante;
    - `meta_analisis.md` y `effects_metafor.csv` == su render.
  - FAIL:
    - `"efecto de un no incluido agregado: <id>"`;
    - `"egger con k < 10: <desenlace>"`;
    - `"unit_of_analysis en excluded_effects (no lo produce el motor)"`;
    - `"study_id repetido en <desenlace> sin multiple_per_study"`;
    - `"meta_analysis.json ≠ recálculo (<campo>)"`;
    - `"multiconjunto (study_id, outcome) ≠ efectos de la instantánea"`.
  - WARN: `"multiple_per_study.allowed: <justificación acotada>"`, `"duplicados detectados: <pares>"`.
  - PASS: `f"{n_outcomes} desenlace(s) · {n_studies} estudios incluidos con efecto · {excluded} efecto(s) excluido(s) · recálculo igual ({random_method})."`.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_audit_meta_v2.py`:

```python
"""`meta_analysis` ligado a los incluidos (spec 2026-10-18 §11.2, D16; relación 29)."""

from __future__ import annotations

import pytest
from audit_fixtures import auditar, edit_json, editar_meta, fila


def _colar_no_incluido(meta: dict) -> None:
    estudio = meta["outcomes"][0]["studies"][0]
    meta["outcomes"][0]["studies"].append({**estudio, "study_id": "10.9999/no-incluido"})


def _egger(meta: dict) -> None:
    meta["outcomes"][0]["egger"] = {"intercept": 0.1, "p_value": 0.5}


def _unit_of_analysis(excluidos: dict) -> None:
    excluidos["excluded"].append({"study_id": "x", "outcome": "o", "reason": "unit_of_analysis"})


def test_meta_analysis_corrida_real_pasa(corrida) -> None:
    assert fila(auditar(corrida), "meta_analysis").status == "PASS"


def test_meta_analysis_efecto_de_no_incluido_agregado_falla(corrida) -> None:
    editar_meta(corrida, _colar_no_incluido)
    detalle = fila(auditar(corrida), "meta_analysis").detail
    assert "efecto de un no incluido agregado" in detalle


def test_meta_analysis_egger_con_k_menor_que_10_falla(corrida) -> None:
    editar_meta(corrida, _egger)
    assert "egger con k < 10" in fila(auditar(corrida), "meta_analysis").detail


def test_meta_analysis_unit_of_analysis_en_excluidos_falla(corrida) -> None:
    edit_json(corrida / "08_meta" / "excluded_effects.json", _unit_of_analysis)
    assert "unit_of_analysis" in fila(auditar(corrida), "meta_analysis").detail


def test_meta_analysis_ya_no_es_relacion_de_arithmetic(corrida) -> None:
    editar_meta(corrida, lambda m: m.update(excluded=7))
    report = auditar(corrida)
    assert fila(report, "meta_analysis").status == "FAIL"
    assert "§8.1" not in fila(report, "arithmetic").detail


@pytest.mark.parametrize("valor", ["x" * 1_000_000, [1, 2, 3]])
def test_meta_analysis_hostil_falla_acotado(corrida, valor: object) -> None:
    editar_meta(corrida, lambda m: m.update(outcomes=valor))
    meta = fila(auditar(corrida), "meta_analysis")
    assert meta.status == "FAIL" and "error interno" not in meta.detail
    assert len(meta.detail) < 2_000
```

Se retira el único XFAIL de F, `test_pipeline_fake_con_humano_audita_sin_fail` (solo el marcador).

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_meta_v2.py -v`
Expected: FAIL (`sin fila 'meta_analysis'`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && wc -l revisia/audit/*.py`
Expected: PASS; XFAIL restante: `test_pipeline_fake_con_humano_judge_audita_sin_fail` (D, G2.10).

- [ ] **Step 5: Commit**

```bash
git add revisia/audit tests
git commit -m "feat(audit): check meta_analysis ligado a los incluidos y a su unidad de análisis (relación 29, D16)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.9: Corridas de benchmark (D23; relación 31; `derive_state`, `publishable`)

**Files:**
- Modify: `revisia/audit/state.py`:
  - `RunStateStatus` gana `"benchmark"`; `_DESCRIPCION`; `describe` → `"de benchmark (D23): no es una revisión"`;
  - `derive_state`: con `run_info.kind == "benchmark"`, `RunState("benchmark", frozenset(STAGES[: STAGES.index("screening_ta") + 1]), None)`, antes de cualquier otra regla.
- Modify: `revisia/audit/model.py` (`AuditReport.publishable`: `False` si `state is not None and state.status == "benchmark"`).
- Modify: `revisia/audit/__init__.py`:
  - `BENCHMARK_CHECKS = frozenset({"provenance", "schemas", "protocol_snapshot", "environment", "prompts", "timing", "gold", "search_log", "search_window", "deposit"})` (F, cambio 5: `environment`, `prompts` y `timing` se aplican; I6: `thresholds` no);
  - en `_run_one` con `ctx.state.status == "benchmark"`: los de `BENCHMARK_CHECKS` corren **sin** filtro de etapa, y el resto (`manifest`, `thresholds` incluidos) es N/A con `"no aplica: corrida de benchmark (D23)."`.
- Modify: `revisia/audit/checks_provenance.py` (`check_provenance` en benchmark: FAIL `"corrida de benchmark: no es una revisión (D23)"`, más la relación 31).
- Modify: `revisia/audit/checks_environment.py` (I6): en benchmark no se compara con el manifiesto y el PASS dice `"· corrida de benchmark: sin manifiesto (D23)."` en lugar de «manifiesto aún no escrito».
- Test: `tests/test_audit_benchmark.py` (nuevo).

**Interfaces:**
- Consumes (F):
  - `run_benchmark`, `protocolo_benchmark(tmp_path)` (**`tests/conftest.py`**, F2.4), `BenchmarkPanel`;
  - `benchmark.json` en `../../benchmark.json` de cada corrida, con `cells[].run_dir == f"runs/{celda}-r{k}"` y `metrics` tal cual;
  - sin `manifest.yml` en una corrida de benchmark (F n+16).
- Produces:
  - Relación 31, en `provenance` (cada rotura se añade al detalle):
    - sin `decisions_ledger.jsonl`, `*/review_request.yml`, `deliverable/` ni `manifest.yml`;
    - con `03_screening/metrics.json`;
    - `../../benchmark.json` con su celda y las `metrics` iguales. Si no existe, el detalle lo anota como «benchmark.json no encontrado junto a la corrida: relación 31 no verificable». F proponía WARN, pero la fila ya es FAIL por D23.
  - El estado de la fila es FAIL, no el PASS que sugiere la tabla de §11.2: un benchmark deja casi todas las filas en N/A, y el invariante «N/A ⇒ algún FAIL» exige que una lo sea. `provenance` es ese FAIL y dice por qué (fila n+15).
  - `AuditReport.publishable` es `False` en benchmark, también como regla explícita.

- [ ] **Step 1: Tests que fallan** — crear `tests/test_audit_benchmark.py`:

```python
"""Corridas `kind: benchmark` (spec 2026-10-18 D23, §11.2; relación 31)."""

from __future__ import annotations

from pathlib import Path

import pytest
from audit_fixtures import auditar, fila
from conftest import protocolo_benchmark, proveedor_auditoria

from revisia.benchmark.run import run_benchmark
from revisia.config import load_protocol
from revisia.orchestration import pipeline as pipeline_mod
from revisia.schemas.benchmark import BenchmarkPanel

PANEL = BenchmarkPanel.model_validate(
    {
        "name": "p",
        "replicas": 1,
        "cells": [{"name": "fake-a", "provider": "fake", "model": "a", "temperature": 0.0}],
    }
)


@pytest.fixture
def corrida_benchmark(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(pipeline_mod, "build_provider", proveedor_auditoria)
    proto = protocolo_benchmark(tmp_path)
    carpeta, _ = run_benchmark(load_protocol(proto), proto, PANEL, out_root=tmp_path / "b")
    return carpeta / "runs" / "fake-a-r1"


def test_benchmark_no_es_publicable_y_no_cascada(corrida_benchmark: Path) -> None:
    report = auditar(corrida_benchmark)
    assert not report.publishable and report.state.status == "benchmark"
    assert {c.check_id for c in report.checks if c.status == "FAIL"} == {"provenance"}
    detalle = fila(report, "provenance").detail
    assert "corrida de benchmark: no es una revisión (D23)" in detalle
    for check_id in ("ledger", "manifest", "thresholds"):
        assert fila(report, check_id).detail == "no aplica: corrida de benchmark (D23)."
    assert "sin manifiesto (D23)" in fila(report, "environment").detail
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []


def test_benchmark_con_ledger_rompe_la_relacion_31(corrida_benchmark: Path) -> None:
    (corrida_benchmark / "decisions_ledger.jsonl").write_text("", encoding="utf-8")
    assert "decisions_ledger.jsonl" in fila(auditar(corrida_benchmark), "provenance").detail


def test_benchmark_con_metricas_distintas_de_benchmark_json(corrida_benchmark: Path) -> None:
    metricas = corrida_benchmark / "03_screening" / "metrics.json"
    metricas.write_text(metricas.read_text("utf-8").replace('"n": ', '"n": 1'), "utf-8")
    assert "benchmark.json" in fila(auditar(corrida_benchmark), "provenance").detail


def test_benchmark_sin_benchmark_json_lo_anota(corrida_benchmark: Path) -> None:
    (corrida_benchmark.parent.parent / "benchmark.json").unlink()
    detalle = fila(auditar(corrida_benchmark), "provenance").detail
    assert "relación 31 no verificable" in detalle
```

(Si los campos de `BenchmarkPanel` de PR-0 (Tarea 13) difieren, se ajusta `PANEL` a ellos.)

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_audit_benchmark.py -v`
Expected: FAIL (estado `completed` o `unknown`; cascada de FAIL de `ledger`, `hitl` y `final_gate`).

- [ ] **Step 3: Implementar** según Interfaces.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX`
Expected: PASS; sin XFAIL nuevos.

- [ ] **Step 5: Commit**

```bash
git add revisia/audit tests/test_audit_benchmark.py
git commit -m "feat(audit): corridas de benchmark no publicables y sin cascada (D23, relación 31)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.10: Fronteras de §11 y §16

**Files:**
- Modify: `tests/conftest.py`: fixture combinada `_corrida_ola2_completa`/`corrida_ola2_completa` (I12).
- Modify: `tests/test_pipeline_fake.py`: retirar el `xfail` de `test_pipeline_fake_con_humano_judge_audita_sin_fail` (D) y borrar `test_pipeline_fake_con_juez_solo_falla_lo_que_adapta_g2` (D).
- Modify: `tests/test_audit_c3.py`: `VIAS_C3 |= {"environment", "prompts"}` **sin** `grounding` (B3: en C3 sale N/A) y `len(fails) >= 12`.
- Modify: `tests/test_audit_deposito.py`: el mismo veredicto con cada corrida de la Ola 2.
- Test: los de esos ficheros.

**Interfaces:**
- `corrida_ola2_completa` (I12): `_correr` sobre `protocolo_auditoria` (`judge`), con:
  - `proveedor=proveedor_con_juez` (D);
  - `fetch_fn=fetch_no_disponible(["10.1000/ensemble"])`;
  - `etiquetar_con_carpeta=lambda d: rescatar_con_texto(d, *RESCATE_CON_TEXTO[:3], reason=RESCATE_CON_TEXTO[3], base=editar_dominio(*EDICION_DE_DOMINIO, base=editar_campo(*EDICION_DE_CAMPO, base=adjudicar_auditoria)))` (`hitl_helpers`, de C y E).

  Es una corrida con juez, una edición de campo, una de dominio, un rescate con texto y una adjudicación: el cierre de §16, en proceso.
- **Decisión sobre la propuesta de D (§16 «con una adjudicación» por CLI):** G₂ no toca `FakeProvider` (`revisia/llm/providers/*` es de A, §15). El cierre se prueba en proceso con `corrida_ola2_completa`, y la variante por CLI queda para PR-I (fila n+19).

- [ ] **Step 1: Tests que fallan / cambian**

En `tests/test_pipeline_fake.py` (imports: `make_deposit`, `auditar`, `fila`, `run_audit`):

```python
def test_frontera_de_la_ola_2_completa_es_apta(corrida_ola2_completa) -> None:
    report = run_audit(corrida_ola2_completa)
    assert {c.check_id: c.detail for c in report.checks if c.status == "FAIL"} == {}
    assert report.publishable
    assert fila(report, "grounding").status == "WARN"  # la cita marcada, adjudicada
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []
```

En `tests/test_audit_deposito.py` (imports: `pytest`, `make_deposit`, `auditar`):

```python
@pytest.mark.parametrize(
    "nombre",
    [
        "corrida_ola2_completa",
        "corrida_con_juez",
        "corrida_con_rescate_con_texto",
        "corrida_con_edicion_de_campo",
        "corrida_con_edicion_de_dominio",
    ],
)
def test_deposito_de_cada_corrida_de_la_ola_2_audita_con_el_mismo_veredicto(
    request: pytest.FixtureRequest, tmp_path, nombre: str
) -> None:
    corrida = request.getfixturevalue(nombre)
    original = auditar(corrida)
    destino = tmp_path / "dep" / corrida.name
    make_deposit(corrida, destino)
    deposito = auditar(destino)
    assert {c.check_id: c.status for c in deposito.checks} == {
        c.check_id: c.status for c in original.checks
    }
    assert original.publishable and deposito.publishable
```

En `tests/test_audit_c3.py`:

```python
VIAS_C3 = {
    "schemas", "ledger", "timing", "hitl", "stage_artifacts", "arithmetic", "final_gate",
    "environment", "prompts",
}


def test_audit_c3_reconstruccion_no_es_publicable_por_al_menos_doce_vias(tmp_path) -> None:
    report = auditar(write_c3_reconstruction(tmp_path, provenance="pipeline"))
    fails = {c.check_id for c in report.checks if c.status == "FAIL"}
    assert len(fails) >= 12 and fails >= VIAS_C3
    assert fila(report, "grounding").status == "N/A"
```

(`len(fails) >= 7` del test original pasa a `>= 12`; el revisor contó 11 hoy y 13 tras G₂.) `test_pipeline_auto_approve_no_es_publicable` y `test_audit_c3_cada_sintoma_basta_solo` siguen sobre `corrida`, que es APTA (B2).

- [ ] **Step 2: Run de la suite entera**

Run: `uv run black . && uv run ruff check --fix . && uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX && uv run pytest -p no:cacheprovider -m cronometrado && wc -l revisia/audit/*.py`
Expected: PASS, **0 XFAIL** y 0 XPASS; ningún módulo > 900.

- [ ] **Step 3: Commit**

```bash
git add tests
git commit -m "test(audit): fronteras de la Ola 2: corrida completa APTA, existence y auto-approve no publicables, C3 por 12 vías, depósito igual" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Tarea G2.11: Integración de PR-G (controlador)

**Files:**
- Modify: `CHANGELOG.md` (`## [Unreleased]`).
- Modify: `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` (§19, filas a continuación de la última).

- [ ] **Step 1: CHANGELOG.** En `### Added`:

```
- **Auditor de la Ola 2** (spec §11): checks `environment` (D12: una corrida 0.8 no es publicable),
  `deposit` (D17), `extraction`, `rob` y `meta_analysis` (relaciones 22–29); `prompts`, `grounding`,
  `arithmetic`, `timing` y `response_overlap` por intento (relaciones 19–23, 26); corridas de
  benchmark no publicables y sin cascada (D23, relación 31). `revisia deposit <run_dir> --out <dir>`:
  copia de depósito sin textos completos, auditable con el mismo veredicto (D17). El auditor queda
  partido en módulos de ≤ 900 líneas (D26).
```

En `### Changed`: ``- `grounding: existence`/`embedder` da FAIL en el auditor: una corrida publicable exige `grounding: judge` con un juez distinto del redactor (D2). El demo sigue en `existence` hasta PR-I.``

- [ ] **Step 2: §19.** Copiar tal cual las filas n…n+9 de «Supuestos revocables de G₁» y las n+10…n+22 de «Supuestos revocables de G₂», numeradas a continuación de la última fila existente. La n+18 se escribe como sustituta de la fila n+14 de PR-D, citándola. **Filas sustituidas:** al registrar, marcar como «sustituida por la fila X» (X, el número real que reciba aquí la fila de G):
  - la fila de D n+14 → por la n+18 de G;
  - las filas de F n+26 y n+27 (propuestas de la revisión de F₂) → por la n+15 de G.

- [ ] **Step 3: Commit de documentación.**

```bash
git add CHANGELOG.md docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md
git commit -m "docs: CHANGELOG y desviaciones (§19) de PR-G" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: Verificación completa.**

```bash
uv run black --check . && uv run ruff check . && uv run ruff format --check . && uv lock --check
uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" -rxX
uv run pytest -p no:cacheprovider -m cronometrado
uv run --python 3.11 pytest -p no:cacheprovider -n auto -m "not cronometrado"
uv run --python 3.12 pytest -p no:cacheprovider -n auto -m "not cronometrado"
uv run pytest -p no:cacheprovider --cov --cov-report=term -n auto -m "not cronometrado" | tail -3
wc -l revisia/audit/*.py
```

Expected: todo en verde; 0 XFAIL; cobertura ≥ 90 % (D25); ningún módulo > 900.

Humo por CLI con el demo (`existence`) y `fake`:

```bash
uv run revisia run examples/demo-mini-review --auto-approve --runs-root ../g-humo
uv run revisia audit ../g-humo/<carpeta>
uv run revisia deposit ../g-humo/<carpeta> --out ../g-humo/dep
uv run revisia audit ../g-humo/dep
```

Expected:
- en las dos auditorías, rc 1 (NO publicable: `--auto-approve` y `existence`), con las mismas filas;
- `deposit` imprime los hashes retenidos.

- [ ] **Step 5: Publicar y abrir la PR** (sin merge).

```bash
git push -u origin feat/ola2-auditor
gh pr create --base feat/ola2-meta-benchmark --head feat/ola2-auditor --title "Ola 2 · PR-G: el auditor verifica lo que la Ola 2 afirma (relaciones 19–31, D2, D12, D17, D23, D26)" --body "$(cat <<'EOF'
## Qué cierra

Spec `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` §11: relaciones 19–31, D2 en el auditor, D12, D17, D23, D26.

## Qué cambia

- **Partición D26** (primer commit, sin lógica). Ningún módulo de `revisia/audit/` pasa de 900 líneas (test).
- **Checks nuevos** (26 filas en total): `environment`, `deposit`, `extraction`, `rob`, `meta_analysis`.
- **Checks cambiados:** `prompts`, `grounding` (FAIL en `existence`/`embedder`, juez ≠ redactor, afirmaciones recalculadas), `arithmetic` (19–23, 26), `timing`, `response_overlap`, `provenance` (benchmark, 31).
- `derive_state` con `kind: benchmark`; `publishable` es `False` en benchmark.
- `revisia deposit <run_dir> --out <dir>`.

## Cambios incompatibles

- Una corrida `grounding: existence`/`embedder` ya no es publicable (D2); el demo sigue en `existence` hasta PR-I.
- Una corrida 0.8 tampoco (D12).

## `xfail` estrictos de A, C, D, E y F puestos en verde

<tabla de la Tarea G2.0, con la tarea de G₂ que pone en verde cada uno>

## Verificación

- Suite en 3.11, 3.12 y 3.13: <N> recogidos, en verde, 0 XFAIL; cobertura <X> %.
- `ruff`, `black`, `uv lock --check`: limpios. Humo por CLI: auditoría y depósito con el mismo veredicto.

## Pila

`main` ← PR-0 ← PR-H ← PR-A ← PR-B ← PR-C ← PR-D ← PR-E ← PR-F ← **PR-G** ← PR-I (spec §15). No borrar la rama al mergear mientras PR-I la use como base.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: la URL de la PR y `gh pr checks <n> --watch` en verde. Sustituir `<N>`, `<X>` y la tabla con `gh pr edit <n> --body-file …`. **El merge lo decide el arquitecto.**

---

### Supuestos revocables de G₂ (filas propuestas para §19)

A continuación de las de G₁:

```
| n+10 | §11.2 `prompts`, relación 19 | Una llamada `ok` sin `prompt_template` es FAIL, y solo en `prompts` (`environment` comprueba la pertenencia y el hash de las plantillas que sí vienen) | Plan PR-G (G₂), revisión I7 |
| n+11 | relación 19 | Una llamada `ok` sin línea de diario solo es válida si la corrida se reanudó (`run.json.resumes` no vacío): la huérfana de una caída a mitad de registro (A, Tarea 3). Entonces es no verificable (WARN de `arithmetic`); sin reanudación, FAIL | Plan PR-G (G₂) |
| n+12 | relaciones 21–23, 26; D26 | Las relaciones nuevas de `arithmetic` viven fuera de `checks_flow.py`: 21 en `checks_calls.py`, 22 en `checks_failed.py`, 23 y 26 en `checks_extraction.py` (la 26 solo en `arithmetic`); `checks_ledger.ediciones_efectivas` es el único lector de `edit_field`/`edit_domain`/`rescue_text` de la decisión efectiva | Plan PR-G (G₂), revisión I9 |
| n+13 | §11.2 `timing` | «`attempt` creciente» = dentro de `(stage, record_id, role)`, en el orden del fichero, cada `attempt` es 1 o el anterior + 1 (un registro reanudado vuelve a 1); atar los reinicios a `run.json.resumes` es opcional | Plan PR-G (G₂), revisión M6 |
| n+14 | §11.2 `grounding`, D2 | Una corrida 0.8 se reconoce por `mode` ausente en el JSON crudo, o `grounding_alias == "agent"`, o (`mode == "judge"` y una sola línea `verificacion` con metas); `existence`/`embedder` cortan con un FAIL propio. `grounding` vive en `checks_grounding.py` | Plan PR-G (G₂), revisión B1 |
| n+15 | §11.2, D23, relación 31 | Benchmark: corren `provenance`, `schemas`, `protocol_snapshot`, `environment`, `prompts`, `timing`, `gold`, `search_log`, `search_window` y `deposit`, sin filtro de etapa; `manifest`, `thresholds` y el resto, N/A «corrida de benchmark (D23)». `provenance` da **FAIL** (la tabla de §11.2 lo ponía en la columna PASS) porque el invariante N/A ⇒ algún FAIL lo exige; la relación 31 busca `../../benchmark.json` y, sin él, lo anota como no verificable dentro de ese FAIL (F proponía WARN, n+26 de F). `environment` dice «sin manifiesto (D23)» | Plan PR-G (G₂), revisión I6; propuestas n+26 y n+27 de F |
| n+16 | §11.2 orden de `CHECKS` | 26 filas: `meta_analysis` tras `arithmetic`; `extraction` y `rob` tras `exclusions`; ítems «PRISMA 13d/20b/20c», «PRISMA 9/10 / trAIce M8», «PRISMA 11/18 / trAIce M8» | Plan PR-G (G₂) |
| n+17 | §16, tests | `protocolo_auditoria` pasa a `grounding: judge` con `llm.verificador: fake-juez` (y `protocolo_con_cita_marcada` lo conserva): `corrida` sigue APTA y sus ~80 aserciones no cambian; la frontera D2 usa `corrida_existence`; los xfail «…audita_sin_fail» de C y E quedan APTA de verdad | Decisión del orquestador (revisión B2/P3) |
| n+18 | §16, §14.2 (sustituye a la fila n+14 de PR-D) | El demo sigue en `grounding: existence` hasta PR-I: `test_pipeline_fake_con_humano_audita_sin_fail` pasa a exigir `fallos == {"grounding"}` y `AVISOS_DE_LA_DEMO` pierde `grounding` | Plan PR-G (G₂), revisión B4 |
| n+19 | §16 cierre por CLI | El demo por CLI con `FakeProvider` no cita, así que «con una adjudicación» no es alcanzable por CLI. G₂ no toca `llm/providers/*` (§15): el cierre se prueba en proceso con `corrida_ola2_completa` (juez, edición de campo y de dominio, rescate con texto, adjudicación); PR-I decide si `FakeProvider.complete` cita un id incluido o se reformula el criterio | Plan PR-G (G₂), propuesta de D |
| n+20 | relación 22 | Una línea `failed` implica consolidado fallido en las cuatro etapas, y su «salida del diario» para la relación 13 y para `apply_*_edits` es `failed_extraction(...)` (C) o `failed_assessment(spec, rid, source_text=…)` (E) | Plan PR-G (G₂), revisión I3 |
| n+21 | relación 27 | Además de §4.3: `domain == spec.domains[i].name`, `human_judgment ∈ scale_for`, `overall_human ∈ overall_scale`, `#overall` ⇔ `overall_human`, `applicability` según la especificación y `human_actor ==` actor del `approve`; GRADE se detecta en el protocolo crudo (no valida) | Plan PR-G (G₂), revisión I4/I5 |
| n+22 | §11.2 checks nuevos | Cada subcomprobación de `extraction`, `rob`, `meta_analysis` y `grounding` corre en su propio `guard` (una excepción es un problema con su tipo, no «error interno»), con un test hostil por check | Plan PR-G (G₂), revisión I8 |
```

---

## Self-review del plan entero (G₁ + G₂)

- **Cobertura de §11:**
  - 11.1 partición: T2.
  - 11.2, check por check:

    | Check | Tareas |
    |---|---|
    | `environment` | T4, G2.9 |
    | `prompts` | G2.2 |
    | `grounding` | G2.5 |
    | `extraction` | G2.6 |
    | `rob` | G2.7 |
    | `meta_analysis` | G2.8 |
    | `deposit` | T6 |
    | `arithmetic` 21 | G2.2 |
    | `arithmetic` 22 | G2.4 |
    | `arithmetic` 23, 26 | G2.6 |
    | `timing`, `response_overlap` | G2.3 |
    | `manifest`/`provenance`, `derive_state`, `publishable` | G2.9 |

  - 11.3 `revisia deposit`: T5–T7.
- **Relaciones 19–31:**

  | Relación | Tareas |
  |---|---|
  | 19 | T4, G2.2 |
  | 20 | T4, G2.2 |
  | 21 | G2.2 |
  | 22 | G2.4, G2.6, G2.7 |
  | 23–26 | G2.6 |
  | 27 | G2.7 |
  | 28 | G2.5 |
  | 29 | G2.8 |
  | 30 | T6 |
  | 31 | G2.9 |
- **Tests «un síntoma a la vez» de §11:**

  | Síntoma | Test (tarea) |
  |---|---|
  | `existence` → FAIL | G2.5 (`corrida_existence`) |
  | juez igual al redactor | G2.5 |
  | afirmación añadida | G2.5 |
  | `human_value` sin `edit_field` | G2.6 |
  | dominio renombrado y `overall` manipulado | G2.7 |
  | efecto de no incluido | G2.8 |
  | `environment` ausente | T4 |
  | corrida 0.8 | T4, G2.1 |
  | depósito con el mismo veredicto, y con un texto dentro | T6, G2.10 |
  | benchmark | G2.9 |
  | `agreement.json` manipulado | G2.6 |

  Fronteras: G2.10 (`corrida_ola2_completa` APTA, `existence` y `auto-approve` no publicables, C3 por ≥ 12 vías sin `grounding`).
- **`xfail` de otras pistas:** los diez de la tabla de G2.0 más los condicionales de A (Tarea 3). Cada uno tiene tarea dueña, G2.10 exige 0 XFAIL y los tres gemelos se borran (G2.6, G2.7, G2.10).
- **Revisión de G₂ incorporada:**

  | Hallazgo | Dónde |
  |---|---|
  | B1 | G2.5 |
  | B2/P3 | G2.5 y n+17 |
  | B3 | G2.10 |
  | B4 | G2.5, G2.8 y n+18 |
  | I1, I2 | G2.5 |
  | I3 | G2.4 y n+20 |
  | I4, I5 | G2.6, G2.7 y n+21 |
  | I6 | G2.9 y n+15 |
  | I7 | G2.2 y n+10 |
  | I8 | todas, n+22 |
  | I9 | estimaciones, `checks_failed`, `ediciones_efectivas` |
  | I10, I11 | G2.3, G2.1 |
  | I12 | G2.10 |
  | M1–M8 | imports y `-> None`, Run/Expected, `del`, `editar_meta`, `input_sha256`/`final_value`, M6 opcional, comprobación de `extra`, configuración de C T11 |
  | Recuento de `CHECKS` | 26 |

  Cambios de F tras su revisión: multiconjunto y orden (G2.8), sin `k`/`studies` (G2.8), `protocolo_benchmark` en `conftest.py` y `../../benchmark.json` (G2.9), `environment`/`prompts`/`timing` en benchmark (G2.9), único XFAIL de F (G2.0).
- **Consistencia de nombres:** los consumidos de A–F son los de sus bloques Interfaces (verificados el 2026-10-19):
  - A: `APPLIED_PARAMS`, `_git_state_fijo`;
  - C: `failed_ids`, `failed_extraction`, `apply_field_edits`, `compute_extraction_agreement(..., expected=)`, `CONCORDANCE_FIELDS`, `ingest_rescue`, `quote_source`;
  - D: `split_claims`, `uncited_quantitative`, `claim_numbers_missing`, `source_window`, `support_quote_status`, `is_grounded`, `JUDGE_FAILED_NOTE`, `vendor_of`, `n_judge_failed`;
  - E: `aggregate`, `final_judgments`, `apply_domain_edits(..., spec=)`, `failed_assessment`;
  - F: `n_studies`, `unit_of_analysis_violations`, `run_benchmark`, `protocolo_benchmark`.

  Los de G₁ (`leer_deposito`, `texto_retenido`, `ruta_del_texto`, `PRE_OLA2_RUN`, `write_run_v08`) y G2.4 (`ediciones_efectivas`, `salida_de_linea_fallida`) se usan con el mismo nombre en las tareas posteriores.
- **900 líneas:** estimaciones en «Topología de G₂»; el mayor, `checks_flow` (≈ 830), solo registra familias.
- **Proporción:** los bloques de código son tests y scripts de verificación; ninguna función de producción tiene cuerpo en el plan.
