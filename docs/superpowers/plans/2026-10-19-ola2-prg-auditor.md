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

G₁ se ejecuta en el worktree `C:\revisia-wt\g` (rama `feat/ola2-auditor`, creada desde `feat/ola2-contratos` en la Tarea 17 de PR-0), en secuencia, tarea a tarea. Al terminar G₁ la rama **no** se publica como PR: espera a PR-F, se rebasa sobre ella y continúa con G₂ (la escribe otro redactor). La PR-G se abre al final de G₂ con base en F (§15).

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
| `relations.py` (nuevo, ≈ 330) | 126-148, 155-164 (sin 151-155), 188-191, 226-385, 574-625, 657-696, 1797-1798 | rutas (`TA`…`TEXTOS`, `SCREENING_JOURNAL`, `LLM_CALLS`, `DEDUP_RECORDS`, `RETRIEVAL_JOURNAL`), `_PASAN_TA`, límites `_MAX`…`_LIMITE_ERROR`, `_SUFIJO_MAS`, `_repartir`, `_acotar_item`, `_limitar`, `_ids`, `_valor`, `_n`, `_primera_diferencia`, `_misma_secuencia`, `_ola1`, `_ids_incluidos`, `included_ids`, `_requiere_doble_extraccion`, `_recuperacion_con_diario`, `_cribado_con_trabajo`, `_Relation`, `_Relations`, `_close`, `_ratio`, `_screeners`, `_seccion`, `_artefacto`, `_normalizar` |
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
| `checks_ledger.py` (nuevo, ≈ 390) | 55-73, 88-364, 372-376, 388-412 | `_NA_LEDGER`, límites, `_ETAPAS_DE_CRIBADO`, `DECISIONES_DE_CRIBADO`, `ACTOR_POR_DEFECTO`, `CONSEJO_ACTOR`, `_BANDERA`, `indice_de_bandera`, `_ola1`, `_forzado`, `autonomia_efectiva_de_la_corrida`, `_limitar`, `_ids`, `_clave`, `_hash`, `_relacion_16`, `_autonomia_del_manifiesto`, `_NA_SIN_GATES_DECIDIDOS`, `_sin_gates_decididos`, `check_ledger`, `_detenida`, `_gates_pendientes`, `_nota_pendientes`, `_listar`, `de_la_decision_efectiva` |
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
- Modify: `revisia/audit/checks_flow.py` (entero, según el mapa), `revisia/audit/checks_hitl.py` (entero), `revisia/audit/artifacts.py:24-27,249-324,346-370`, `revisia/audit/__init__.py:21-25,35-42,82-89`, `revisia/audit/checks_quality.py:29,35-40`.
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
    largos = {p.name: len(p.read_text(encoding="utf-8").splitlines()) for p in carpeta.glob("*.py")}
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
  - sustituye `pipeline_mod.ensure_snapshot` por un envoltorio que, **solo si `run.json` no existía antes de la llamada** y el `RunInfo` devuelto tiene `environment is None`, reescribe `run.json` con `write_run_info(run_ctx.run_dir, info.model_copy(update={"environment": entorno_de_prueba()}))` y devuelve ese `info`;
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
- Modify: `revisia/audit/__init__.py` (import y `CheckSpec` justo después de `provenance`, línea 76).
- Modify: `tests/test_audit_paquete.py` (`CHECKS_ESPERADOS`: fila nueva tras `provenance`).
- Test: `tests/test_audit_entorno.py` (nuevo).

**Interfaces:**
- Consumes: `Environment` (PR-0), `LEGACY_RUN` (`checks_provenance.py:45`), `AuditContext.run_info`, `.manifest`, `.manifest_dict`, `.llm_calls`, `.llm_calls_ilegible`, `.protocol`, `.state.reached` (`artifacts.py:755-919`), `short_text`, `format_validation`, `sufijo_mas`.
- Produces (G₂ los reutiliza):
  - `PRE_OLA2_RUN: str` = el texto literal de D12 (Global Constraints), sin punto final.
  - `SEMVER: re.Pattern[str]` (la expresión oficial de semver.org 2.0.0) y `es_semver(version: str) -> bool`.
  - `entorno_de_la_corrida(ctx: AuditContext) -> Environment | None`: el de `run.json` si valida; `None` si no hay `run.json`, no valida o `environment` es `None`/falta.
  - `check_environment(ctx: AuditContext) -> Verdict`. Reglas, en este orden (un FAIL junta todos sus problemas, separados por `; `, como mucho 5 y `sufijo_mas`):
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
  - `out_dir` es la carpeta de depósito misma (no su madre). Antes de copiar nada se comprueba, y si falla se lanza sin haber creado ni copiado nada: `run_dir` existe y tiene `run.json` válido (si no, `ValueError("… sin run.json: solo se depositan corridas de la Ola 1 o posteriores")`) y `manifest.yml` (si no, `ValueError("… sin manifest.yml: solo se deposita una corrida terminada")`); `run_dir` no tiene `deposit.json` (`ValueError("… ya es una copia de depósito")`); `out_dir` no está dentro de `run_dir` (`ValueError`); `out_dir` no existe o es una carpeta vacía (si no, `FileExistsError`).
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
    corrida, corrida_en_pausa_ft, tmp_path
) -> None:
    ocupado = tmp_path / "ocupado"
    ocupado.mkdir()
    (ocupado / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        make_deposit(corrida, ocupado)
    with pytest.raises(ValueError, match="dentro"):
        make_deposit(corrida, corrida / "dep")
    with pytest.raises(ValueError, match="manifest.yml"):
        make_deposit(corrida_en_pausa_ft, tmp_path / "pausa")
    with pytest.raises(ValueError, match="run.json"):
        make_deposit(write_legacy_v07(tmp_path / "v07"), tmp_path / "legado")
    make_deposit(corrida, tmp_path / "dep")
    with pytest.raises(ValueError, match="ya es una copia de depósito"):
        make_deposit(tmp_path / "dep", tmp_path / "dep2")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dep", "ocupado", "v07"]
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
    for contenido in ("{", '["no", "es", "un", "mapa"]', '{"withheld": "' + "x" * 1_000_000 + '"}'):
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
    corrida, corrida_en_pausa_ft, tmp_path, capsys
) -> None:
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
```

### Self-review de G₁

- **Cobertura de §11 para G₁:** partición D26 con el test de 900 líneas y `CHECKS` fijado (T2); `environment` con su tabla de §11.2 (PASS, WARN y FAIL con el mensaje literal de D12) y la parte de entorno de las relaciones 19 y 20 (T4); `make_deposit` (T5); check `deposit`, relación 30 y «textos en caché frente a `retrieval.json`» por hash (T6); `revisia deposit` e impresión de hashes (T7); test de frontera «el depósito audita con el mismo veredicto» (T6, y por CLI en T7); «corrida 0.8 → FAIL `environment` y el resto diagnóstico» (T4 con `write_run_v08`, T3). Lo demás de §11.2 y §16 es de G₂ (abajo).
- **Firmas y líneas verificadas contra el árbol (`main` @ `c1af7c3`, igual en esta rama):** `checks_flow.py` (2 190; rangos del mapa por AST), `checks_hitl.py` (1 389), `artifacts.py` (919; `short_repr` 306, `short_text` 311, `sufijo_mas` 346, `format_validation` 363, `AuditContext` 755), `__init__.py` (`CHECKS` 74-96), `checks_quality.py:29,35-40`, `checks_provenance.py:45` (`LEGACY_RUN`), `cli.py` (`_cmd_audit` 527, `_cmd_export` 551, `_cmd_brain` 573, `p_export` 698-714, `main` 728, despacho de `export` 740-741), `snapshot.py` (`prompt_fingerprint` 76, `read_run_info` 84, `write_run_info` 92, `ensure_snapshot` 106), `run_context.py:190` (`write_manifest`), `pipeline.py:107,558,1278`, `audit_fixtures.py` (`edit_json` 86, `edit_yaml` 92, `editar_llamadas` 146, `write_legacy_v07` 280), `conftest.py` (`_correr` 234, fixtures de sesión 279-319). Las de PR-0 (`Environment`, `DepositInfo`, `WithheldDir`, `WithheldFile`, `DepositSource`, `DEPOSIT_FILE`, `WITHHELD_DIRS`, `tool_spec_fingerprint`) se toman de los bloques Interfaces de su plan (T5, T10).
- **Consistencia de tipos:** `entorno_de_prueba`/`editar_entorno`/`write_run_v08` (T3) los usan T4 y G₂; `PRE_OLA2_RUN`/`es_semver`/`entorno_de_la_corrida` (T4) y `leer_deposito`/`texto_retenido`/`Deposito`/`ruta_del_texto` (T6) se nombran igual en el bloque de G₂; `CHECKS_ESPERADOS` crece en T4 y T6 sin cambiar las filas de T2.
- **Review Focus:** las cinco líneas tienen test en su tarea (T4: hostil, en pausa, `null`; T5: rechazo sin copiar, `/` y subcarpetas; T6: hostil, rutas que escapan, fichero fuera de la lista).
- **Proporción:** los bloques de código son tests y un script de verificación de un solo uso; ninguna función de producción tiene cuerpo en el plan.
- **Riesgo de la frontera 0.8:** `test_corrida_08_falla_solo_en_environment…` exige que ninguna otra fila falle al quitar los campos v2; si alguna lo hace, el auditor de la Ola 1 depende de un default v2 y hay que decidirlo (T4, Step 4).

---

## Fase G₂ (sobre PR-F)

Pendiente: la escribe el redactor de G₂.

### Interfaces que G₁ deja para G₂

**Obligaciones de arranque de G₂** (tras rebasar `feat/ola2-auditor` sobre `feat/ola2-meta-benchmark`):
- Retirar la fixture `_andamio_entorno_ola2` de `tests/conftest.py` (PR-A ya escribe `environment` en `run.json` y en el manifiesto); `entorno_de_prueba` puede quedarse para tests unitarios.
- Ajustar `write_run_v08` a la forma 0.8 real con lo que A haya retirado (p. ej. volver a poner `run.json.prompt_sha256`, §5.5) y conservar `test_corrida_08_falla_solo_en_environment…`, que pasa a exigir también el FAIL de `prompts` (llamadas sin `outcome`/`attempt`).
- Volver verdes los `xfail(strict=True, reason="PR-G: …")` que PR-A deja en su Tarea 3 si algún check da FAIL por intentos fallidos (D14), y revisar la compatibilidad que PR-F declara en su Tarea 3 para `checks_meta.py` (los rangos que F cita de `checks_flow.py`, 429-491, 1843-1945 y 2161-2190, viven ahora en `checks_meta.py`).
- Mantener `test_ningun_modulo_del_auditor_supera_900_lineas`: `checks_flow.py` queda en ≈ 820 tras G₁, así que las relaciones nuevas **no** van ahí.

**Dónde va cada familia** (módulo destino; «nuevo» = módulo que crea G₂):

| Check / relación de §11.2 y §4.3 | Módulo |
|---|---|
| `prompts` (M), relación 19 completa (cada llamada `ok` con plantilla; `outcome`/`attempt`, §19 fila 1) | `checks_provenance.py` (`check_prompts`, ≈ 307 hoy) |
| `grounding` (M), relación 28 | `checks_grounding.py` (nuevo: sacar `check_grounding` y sus ayudantes de `checks_quality.py`, 492 hoy, si con lo nuevo pasara de 900) |
| `extraction` (N), relaciones 24–25 | `checks_extraction.py` (nuevo) |
| relación 26 (`agreement.json` recalculado) en `arithmetic` | `checks_journals.py` (junto a `_doble_extraccion_en_diario`), familia registrada en `checks_flow.collect_relations` |
| `rob` (N), relación 27 (dominio sin `id` = FAIL, §19 fila 2) | `checks_rob.py` (nuevo) |
| `meta_analysis` (N), relación 29; sale la familia `_meta_analisis` de `collect_relations` | `checks_meta.py` (ya tiene `_efectos_del_protocolo`, `_meta_analisis`, `_meta_entregables`, `_meta_sin_incluidos`) |
| `arithmetic` (M): relaciones 21 y 22 | `checks_journals.py` (diarios con `status: failed`, metas por intento) |
| relación 23 (rescate humano con texto) | `checks_flow.py` solo el enganche en `_recuperacion`; la lógica en un módulo nuevo o en `checks_extraction.py` |
| `timing` (M), `response_overlap` (M) | `checks_timing.py` |
| `manifest`, `provenance` (M) con `kind: benchmark`; relación 20 (`models_used`/`deterministic_token_level` sobre llamadas `ok`); relación 31 | `checks_provenance.py` |
| `derive_state` con `kind: benchmark` (`status: benchmark`, `reached` hasta `screening_ta`) | `state.py` |

**Ayudantes comunes que G₁ deja:**
- `revisia.audit.relations`: rutas de artefactos (`TA`, `FT`, `EXTRACTIONS`, `ASSESSMENTS`, `AGREEMENT`, `RETRIEVAL`, `VERIFICATION`, `DOCUMENTO`, `TEXTOS`, `LLM_CALLS`, …), `_Relations` (`eq`, `check`, `unverifiable`, `ausente`, `guard`), `_ids`, `_limitar`, `_valor`, `_n`, `_seccion`, `_artefacto`, `_ola1`, `included_ids`, `_normalizar`, `ruta_del_texto(record_id) -> str`.
- `revisia.audit.checks_ledger`: `de_la_decision_efectiva`, `indice_de_bandera`, `ACTOR_POR_DEFECTO`, `CONSEJO_ACTOR`, `autonomia_efectiva_de_la_corrida`, `_gates_pendientes`, `_detenida` (las ediciones `edit_field`/`edit_domain`/`rescue_text` de la decisión efectiva se filtran con `de_la_decision_efectiva`, como las `label`).
- `revisia.audit.checks_environment`: `PRE_OLA2_RUN`, `SEMVER`, `es_semver(version) -> bool`, `entorno_de_la_corrida(ctx) -> Environment | None`.
- `revisia.audit.checks_deposit`: `Deposito(info, retenidos)`, `leer_deposito(ctx) -> tuple[Deposito | None, str | None]`, `texto_retenido(deposito, relpath, sha256) -> bool`. **Las relaciones que leen un texto en caché o un rescate (23, 24, 28) deben, con un depósito válido, darse por verificadas por hash** (`texto_retenido`) y anotarlo, como la relación 7; si no, el test de frontera del depósito deja de dar el mismo veredicto.
- `revisia.audit.text`: `short_text`, `short_repr`, `sufijo_mas`, `format_validation` (también importables desde `revisia.audit.artifacts`).
- Tests: `tests/audit_fixtures.py` (`entorno_de_prueba`, `editar_entorno`, `write_run_v08`, `CLAVES_RUNMETA_V2`), `tests/test_audit_paquete.py::CHECKS_ESPERADOS` (cada check nuevo añade su fila en su posición), `tests/test_audit_deposito.py::test_deposito_audita_con_el_mismo_veredicto` (debe seguir verde con las corridas que amplían C, D y E).
