# Ola 2 · PR-B `feat/ola2-identidad-registros` (DOI único, dedup y corpus nativo) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el mismo artículo traído de dos fuentes tenga **un solo** `record_id` y una sola clave de dedup (A4), que los títulos de relleno nunca fusionen registros distintos y que el BibTeX con llaves anidadas conserve el título (A5), y que un corpus congelado se pueda importar en formato nativo `imported/*.records.json` con sus ids intactos (D23), cableando la `normalize_doi` que dejó PR-0.

**Architecture:** La normalización vive en un solo sitio: el validador `before` de `SearchRecord` aplica `ingest.doi.normalize_doi` a `doi` al construir **cualquier** registro (y guarda el original no normalizable en `extra["doi_raw"]`); los backends dejan sus normalizadores propios, pasan el DOI crudo del campo que la fuente etiqueta como DOI y calculan el `record_id` con la misma función. El dedup usa ese DOI, títulos NFKD sin diacríticos y `none:<record_id>` para los títulos de relleno, y lo cuenta en `DedupReport.unmerged_placeholders`. `manual_import` gana un parser BibTeX por llaves y `parse_records_json`; un único `import_format(path)` decide qué fichero de `imported/` es importable (búsqueda y preflight). **No se toca `orchestration/pipeline.py`**: `02_dedup/dedup.json` ya se escribe con `report.model_dump()`.

**Tech Stack:** Python 3.13 (3.11/3.12 tras el rebase sobre A, que ya trae PR-H), Pydantic v2, `unicodedata`, `json`, pytest, ruff + black (línea 100), uv, gh.

**Spec:** `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`, §6 (PR-B), D19 y D23 (§3), relaciones de §4.1 (`01_search/records.json`, `02_dedup/*`), §10.2 (PR-F consume `parse_records_json`), §15 (topología y solapes), §16 (método), §18 riesgo 6 y §19 filas 1–8, que vinculan. Planes hermanos: `2026-10-18-ola2-pr0-contratos.md` (Tarea 14 crea `revisia/ingest/doi.py`: **no se redefine aquí**) y `2026-10-18-ola2-prh-ci-tests.md` (Tarea 5 crea `tests/test_search_backends_parsers.py`, que esta PR adapta tras el rebase).

## Global Constraints

- Idioma: código, docstrings, comentarios, mensajes y commits **en español**, con el tono del repo; las docstrings explican el porqué y citan la auditoría («auditoría 2026-09-03, A4») o la decisión («D19», «D23»).
- Estilo: `ruff` (`E,F,I,UP,B,SIM`, línea 100) y `black` (línea 100), limpios en cada commit. `from __future__ import annotations` en todo módulo nuevo, también en `tests/`.
- **`normalize_doi` es la única normalización de DOI del paquete** (D19): al terminar, ningún módulo de `revisia/` hace `.lower().strip()`, `replace("https://doi.org/", …)` ni prefijos propios sobre un DOI. Firma (PR-0, Tarea 14): `normalize_doi(value: object) -> str | None` con `DOI_RE = ^10\.\d{4,9}/\S+$`; `doi_url(doi: str) -> str`.
- Ficheros de esta pista (§15): `agents/{busqueda,open_backends,search_backends,ncbi,dspace,dedup}.py`, `ingest/*`, `schemas/records.py`. Además, aditivo y declarado (§19): `schemas/artifacts.py` (dos campos), `orchestration/search_stage.py` y `llm/preflight.py` (solo la detección de ficheros de `imported/`). **`orchestration/pipeline.py` no se toca.**
- Tests offline y deterministas; ninguno toca la red ni necesita `httpx` instalado (los backends se prueban sustituyendo su `_client`).
- Ningún test existente se borra. Los que cambian de expectativa se listan en su tarea con fichero y línea (verificados contra `main` @ `c1af7c3` el 2026-10-19, ejecutando la suite con el cambio aplicado en una copia).
- Línea base: la suite de PR-0 en verde en el worktree (`C:\revisia-wt\b`); tras el rebase de la Tarea 8, la de A. Cada tarea termina con la suite entera en verde.
- Comandos: un test, `uv run pytest -p no:cacheprovider <ruta>::<test> -v`; la suite, `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"` y `uv run pytest -p no:cacheprovider -m cronometrado`; lint, `uv run ruff check . && uv run ruff format --check . && uv run black --check .`.
- Commits pequeños, al menos uno por tarea, prefijo convencional (`feat:`, `fix:`, `test:`, `docs:`), terminados con `-m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.
- **Los implementadores no tocan** `CHANGELOG.md`, `README.md`, `AGENTS.md`, `docs/auditoria/` ni el spec: los actualiza el controlador en la Tarea 8 (§15).
- No cambiar `revisia.__version__` ni `pyproject.toml`.
- Con PRs apiladas, **nunca** `gh pr merge --delete-branch` mientras otra PR use la rama como base (§15).

## Review Focus

Entradas que el spec implica y que ninguna tarea probaría sin estas líneas; cada una tiene su test en la tarea dueña:

1. **Importar `revisia.schemas.records` en un proceso limpio.** `records → ingest.doi` dispara `revisia/ingest/__init__.py`, que importa `manual_import`, que importa `records` a medio cargar: un `import` de módulo crea un ciclo que la suite (que importa en otro orden) no ve. → Tarea 2 (`test_importar_records_en_un_proceso_limpio`).
2. **Releer un registro ya normalizado** (`01_search/records.json` y `02_dedup/records.json` al reanudar, o un `*.records.json` importado) debe dar el mismo registro: ni un segundo `doi_raw`, ni un `doi` distinto, ni el `record_id` tocado. → Tareas 2 y 7.
3. **Un campo que la fuente no etiqueta como DOI** (`url` de ERIC que no es `doi.org`, `aid` de BVS que es un id SciELO) no debe dejar `doi_raw` ni cambiar el id de respaldo; un DOI crudo inválido de Crossref sí deja `doi_raw` y cae a `crossref:<crudo>`. → Tarea 3.
4. **Un BibTeX real de Scopus/WoS** con `@` dentro de un valor (correos, `note`), `@comment`/`@string`, mayúsculas en los nombres de campo, saltos de línea dentro de un valor o una entrada truncada: nunca un registro a medias ni un título perdido en silencio. → Tarea 5.
5. **Un `*.records.json` que es la copia de `02_dedup/records.json`** (con ids `…#2`, `extra` con `pmcid`/`doi_raw`, `source_db` de varias bases) entra tal cual; uno con ids repetidos, que no es una lista o con un registro inválido queda `failed` en `01_search/log.json` (M7), no aborta la búsqueda ni se renombra en silencio. → Tarea 7.

---

## Topología de ejecución (subagentes)

Secuencial, en el worktree `C:\revisia-wt\b` (rama `feat/ola2-identidad-registros`, creada desde `feat/ola2-contratos` en la Tarea 17 de PR-0). B se desarrolla desde PR-0, en paralelo con H, A, E₁, F₁ y G₁; ninguna de ellas toca los ficheros de esta pista (§15, tabla de solapes). Al cerrar (Tarea 8) se rebasa sobre A (`feat/ola2-procedencia`, que ya va sobre H) y la PR se abre con base A. PR-C se desarrolla después desde B rebasada.

| Tarea | Fichero(s) | Depende de |
|---|---|---|
| 1 | worktree y línea base | PR-0 cerrada |
| 2 | `revisia/schemas/records.py`; tests con DOI de una cifra (lista en la tarea) | 1 |
| 3 | `revisia/agents/{busqueda,search_backends,ncbi,open_backends,dspace}.py` | 2 |
| 4 | `revisia/ingest/manual_import.py` (`_record_id`, `parse_ris`) | 2 |
| 5 | `revisia/ingest/manual_import.py` (`parse_bibtex`) | 4 |
| 6 | `revisia/agents/dedup.py`, `revisia/schemas/artifacts.py` (`DedupReport`) | 2 |
| 7 | `revisia/ingest/{manual_import,__init__}.py`, `revisia/schemas/artifacts.py` (`SearchLogEntry`), `revisia/orchestration/search_stage.py`, `revisia/llm/preflight.py` | 5 |
| 8 | integración (controlador): rebase sobre A, test de PR-H, CHANGELOG, §19, PR | todas |

**Ciclo por tarea (§16):** implementador (subagente nuevo, TDD estricto: test rojo → código mínimo → verde → lint → commit) → revisor (subagente nuevo: primero cumplimiento del spec y de este plan, después calidad) → correcciones → siguiente tarea. Desviaciones descubiertas en revisión se corrigen y se anotan en §19 del spec (Tarea 8), no se consultan, salvo que cambien una decisión D1–D6. El controlador ejecuta de punta a punta sin pedir confirmación entre tareas. **El merge lo decide el arquitecto.**

**Los números de línea** son de `main` @ `c1af7c3`. PR-0 solo desplaza los de `revisia/schemas/artifacts.py` (localizar por nombre de clase); el resto de ficheros de esta pista no los toca PR-0.

---

## Tarea 1: Worktree y línea base (controlador)

**Files:** ninguno.

**Interfaces:** ninguna de código.

- [ ] **Step 1: Comprobar el worktree que creó PR-0** (si no existe, crearlo igual que allí).

```bash
git -C C:/revisia worktree list | grep revisia-wt/b || git -C C:/revisia worktree add C:/revisia-wt/b -b feat/ola2-identidad-registros feat/ola2-contratos
cd C:/revisia-wt/b
git log --oneline -1
```

Expected: la punta es el último commit de `feat/ola2-contratos`; existen `revisia/ingest/doi.py` y `tests/test_doi.py`.

- [ ] **Step 2: Entorno y línea base.**

```bash
uv sync --extra dev --extra search --extra meta
uv run pytest -p no:cacheprovider --collect-only -q | tail -1
uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado
```

Expected: suite en verde; anotar el recuento (es la base del cuerpo de la PR).

---

## Tarea 2: `SearchRecord.doi` normalizado al construir (D19, A4)

**Files:**
- Modify: `revisia/schemas/records.py:1-7` (docstring del módulo: el DOI se normaliza aquí, D19) y `:57-61` (el validador `before` `_sin_sustitutos`).
- Modify (cambian de expectativa; ver Step 5): `tests/test_dedup.py:77-94` y los ficheros con DOI de una cifra listados en el Step 5.
- Test: `tests/test_identidad_registros.py` (nuevo).

**Interfaces:**
- Consumes: `revisia.ingest.doi.normalize_doi(value: object) -> str | None` (PR-0, Tarea 14).
- Produces:
  - `SearchRecord.doi: str | None` **siempre** normalizado (o `None`) en todo registro construido por validación (`SearchRecord(...)`, `model_validate`, `model_validate_json`). `model_copy(update=…)` no valida: quien lo use para cambiar `doi` debe pasar un DOI ya normalizado (nadie lo hace hoy).
  - `SearchRecord.extra["doi_raw"]: str`: el valor original cuando era un `str` no vacío que `normalize_doi` no reconoce. Un `""`/espacios/`None` no deja rastro. Un valor que no es `str` no se toca (la validación de tipo lo rechaza como hoy).
  - `record_id` **no** lo toca el modelo: lo decide cada backend (Tarea 3) y `manual_import` (Tarea 4).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_identidad_registros.py`:

```python
"""Identidad de los registros: un DOI normalizado al construir (spec 2026-10-18 §6, D19;
auditoría 2026-09-03, A4)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from revisia.agents.busqueda import work_to_record
from revisia.agents.dedup import deduplicate_with_report
from revisia.ingest import parse_ris
from revisia.schemas.records import SearchRecord

RAIZ = Path(__file__).resolve().parent.parent


def test_a4_ris_con_prefijo_y_openalex_son_un_solo_registro_sin_renombrar() -> None:
    # La evidencia de A4 tal cual: RIS `https://doi.org/10.1000/ABC` + OpenAlex `10.1000/abc`.
    ris = "TY  - JOUR\nTI  - Mismo artículo\nDO  - https://doi.org/10.1000/ABC\nER  -\n"
    (importado,) = parse_ris(ris)
    openalex = work_to_record(  # el lado OpenAlex por su parser real
        {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1000/abc",
         "display_name": "Mismo artículo"}
    )
    assert openalex.doi == openalex.record_id == "10.1000/abc"
    assert importado.doi == importado.record_id == "10.1000/abc"
    unicos, informe = deduplicate_with_report([openalex, importado])
    assert [r.record_id for r in unicos] == ["10.1000/abc"]  # sin `#2`
    assert informe.renamed == [] and (informe.n_in, informe.n_out) == (2, 1)
    (duplicado,) = informe.duplicates
    assert (duplicado.record_id, duplicado.kept_record_id, duplicado.key) == (
        "10.1000/abc",
        "10.1000/abc",
        "doi:10.1000/abc",
    )


def test_search_record_normaliza_el_doi_al_construir() -> None:
    r = SearchRecord(record_id="x", title="t", doi="https://doi.org/10.1000/ABC")
    assert r.doi == "10.1000/abc" and r.extra == {}


def test_doi_no_normalizable_queda_none_y_el_original_en_extra() -> None:
    r = SearchRecord(record_id="x", title="t", doi="PMC12345", extra={"k": 1})
    assert r.doi is None and r.extra == {"k": 1, "doi_raw": "PMC12345"}


@pytest.mark.parametrize("vacio", [None, "", "   "])
def test_doi_vacio_o_ausente_no_deja_rastro(vacio: str | None) -> None:
    r = SearchRecord(record_id="x", title="t", doi=vacio)
    assert r.doi is None and r.extra == {}


def test_doi_que_no_es_texto_sigue_siendo_error_de_tipo() -> None:
    with pytest.raises(ValidationError):
        SearchRecord(record_id="x", title="t", doi=123)


def test_extra_que_no_es_dict_es_error_de_validacion() -> None:
    # Con un DOI no normalizable el validador no debe reventar con TypeError al fusionar `extra`.
    with pytest.raises(ValidationError):
        SearchRecord(record_id="x", title="t", doi="no-es-doi", extra=[1])


def test_el_modelo_no_toca_el_record_id() -> None:
    crudo = "https://doi.org/10.1000/ABC"
    assert SearchRecord(record_id=crudo, title="t", doi=crudo).record_id == crudo


def test_releer_un_registro_es_idempotente() -> None:
    for doi in ("doi:10.1000/ABC.", "no-es-doi"):
        r = SearchRecord(record_id="x", title="t", doi=doi)
        assert SearchRecord.model_validate_json(r.model_dump_json()) == r
        assert SearchRecord.model_validate(r.model_dump(mode="json")) == r


def test_importar_records_en_un_proceso_limpio() -> None:
    # records → ingest.doi → ingest/__init__ → manual_import → records: sin ciclo.
    for modulo in ("revisia.schemas.records", "revisia.ingest.doi", "revisia.agents.dedup"):
        subprocess.run([sys.executable, "-c", f"import {modulo}"], check=True, cwd=RAIZ)

```

(La colisión real de ids, `#n` con mismo id y sin DOI, la cubre `tests/test_dedup.py::test_dedup_ids_repetidos_se_desambiguan` reescrito en el Step 5; no se duplica aquí.)

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_identidad_registros.py -v`
Expected: FAIL en `test_a4_…` (hoy el RIS guarda `doi` con prefijo: dos claves, `10.1000/abc#2`), `test_search_record_normaliza…`, `test_doi_no_normalizable…`; el resto PASS.

- [ ] **Step 3: Implementar** en `revisia/schemas/records.py`: el validador `before` existente (`_sin_sustitutos`, línea 57) pasa a hacer, en este orden, (1) `replace_surrogates` como hoy y (2) si `data` es `dict` y `data.get("doi")` es `str`: `norm = normalize_doi(raw)`; copia el dict, pone `doi = norm` y, si `norm is None and raw.strip()`: con `extra = data.get("extra")`, si es `None` o un `dict`, `extra = {**(extra or {}), "doi_raw": raw}`; si es otra cosa, se deja tal cual para que la validación de tipo dé `ValidationError` (nunca un `TypeError` desde el validador). **Un solo validador** (dos `before` de modelo tendrían orden implícito). Por qué no `field_validator` (lo que dice §6): un validador de campo no puede escribir `extra`; queda en §19. El `import` de `normalize_doi` va **dentro** de la función con un comentario que explique el ciclo (`records → ingest/__init__ → manual_import → records`). Renombrar el validador a `_normaliza_entrada` y su docstring: sustitutos (A4 de la revisión final de la Ola 1) y DOI (D19, auditoría A4).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_identidad_registros.py tests/test_doi.py -v`
Expected: PASS.

- [ ] **Step 5: Tests que cambian de expectativa.** Con el validador, la suite da **20 fallos**, verificados: 19 son fixtures con DOI de registrante de una cifra (`10.1/abc`), que `DOI_RE` (`\d{4,9}`, PR-0) ya no reconoce como DOI; el 20.º es el renombrado `#2` de A4, que deja de existir. **No se relaja `DOI_RE`** (los DOI reales tienen ≥ 4 cifras): se migran las fixtures sustituyendo `10.N/` por `10.N000/` **solo** en estas líneas (entrada y su aserción):
  - `tests/test_busqueda.py:21,28,29`
  - `tests/test_coverage_gaps.py:158,164,172,176,180`
  - `tests/test_dedup.py:21,22,54,57,70,71,100,104`
  - `tests/test_errores_deterministas.py:496,515,535,564,625`
  - `tests/test_exports_biblio_extraction.py:16,32` (solo `doi`; el `record_id` `10.1/abc` y la clave `10_1_abc` de la línea 29 no cambian)
  - `tests/test_hitl_pipeline.py:488,553,1494`
  - `tests/test_pmc_ncbi.py:90,117,118,154,164,222,227,228,244,286,331,339,351,360,365`
  - `tests/test_search_multibase.py:58,80,81,234,245,254,264`
  - y, aunque hoy no fallan (pasan por la rama «DOI no normalizable» sin quererlo), `tests/test_search_stage.py:28`, `tests/test_audit_busqueda.py:1102,1110,1114` y `tests/test_fulltext.py:32`, para que sigan probando un registro **con** DOI.

  Y `tests/test_dedup.py:77-94` (`test_dedup_ids_repetidos_se_desambiguan`, que consagraba el `#2` de A4) se reescribe con el mismo nombre como colisión real: tres registros sin DOI, `record_id="hash:x"` los tres, títulos `"Uno"`, `"Dos"`, `"Uno"` → únicos `["hash:x", "hash:x#2"]`, `renamed == [("hash:x", "hash:x#2")]`, un duplicado con `key == "title:uno"` y `kept_record_id == "hash:x"`; el caso RIS + OpenAlex vive ya en `test_a4_…` de arriba. Comentario de la cabecera del test: «Ola 2 (D19): el DOI se normaliza al construir; el `#n` queda para colisiones reales».

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS (suite entera).

- [ ] **Step 6: Commit**

```bash
git add revisia/schemas/records.py tests/
git commit -m "feat(records): SearchRecord normaliza el DOI al construir y guarda el crudo en extra (D19, A4)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 3: Los backends dejan de normalizar por su cuenta (D19, A4)

**Files:**
- Modify: `revisia/agents/busqueda.py:41-44` (borrar `_normalize_doi`), `:53,64,69` (`work_to_record`), `:93-118` (`search` usa `_client`).
- Modify: `revisia/agents/search_backends.py:49,61,66` (Crossref), `:87,91,96` (S2), `:128,139,144-145` (Europe PMC).
- Modify: `revisia/agents/ncbi.py:106-126,130,135` (`_parse_pubmed_article`), `:172-175,184,189` (`esummary_pmc`), `:283-286` (`idconv`: la clave `doi` del mapa con `normalize_doi`).
- Modify: `revisia/agents/open_backends.py:44-53` (borrar `_doi`), `:89,95,100` (ERIC), `:119-122,132,137-138` (DOAJ), `:233,243,248-249` (BVS).
- Modify: `revisia/agents/dspace.py:22` (import), `:58,74,79` (`_dc_record`).
- Modify: `tests/test_open_backends.py:360-366` (ver Step 5).
- Test: `tests/test_doi_backends.py` (nuevo).

**Interfaces:**
- Consumes: `normalize_doi`, `doi_url` (PR-0); `SearchRecord` de la Tarea 2.
- Produces:
  - Patrón en cada backend: `crudo = <campo DOI nativo>`; `doi = normalize_doi(crudo)`; `SearchRecord(record_id=doi or <respaldo de hoy>, doi=crudo, url=… doi_url(doi) …)`. El modelo deja `doi` normalizado y el crudo inválido en `extra["doi_raw"]`.
  - Campos DOI nativos (pasan `doi=crudo`): OpenAlex `work["doi"]`; Crossref `it["DOI"]`; S2 `externalIds.DOI`; Europe PMC `it["doi"]`; PubMed `ArticleId[@IdType=doi]` y, si falta, `ELocationID[@EIdType=doi]` (el primero que **normalice**); PMC `articleids[idtype=doi]`; DOAJ `identifier[type=doi]`; DSpace `dc.identifier.doi`/`oapen.identifier.doi` (el primero que normalice; si ninguno, el primer crudo).
  - Campos que **no** son DOI por sí mismos (pasan `doi=doi`, ya normalizado, sin `doi_raw`): ERIC `url` (solo si contiene `doi.org/`, como hoy) y BVS `aid`.
  - `busqueda._client(timeout: float = 60.0, *, mailto: str | None = None) -> Any` → `_http.make_client(timeout, mailto=mailto)`: la indirección que ya tienen los demás backends (los tests la sustituyen; añade el User-Agent con `mailto`, mismo timeout y redirecciones). `search` deja su `import httpx` propio (`_http.HttpxMissingError` ya da el mensaje del extra).
  - `ncbi.idconv(ids, *, mailto=None) -> dict[str, str]`: misma firma; la clave que sale del campo `doi` de la respuesta es `normalize_doi(val) or str(val).lower()` (las de `pmid`/`pmcid`, `str(val).lower()` como hoy), para que case con `record.doi`, ya normalizado. `fulltext._resolve_pmcid` (`fulltext.py:118-130`) **no se toca** (es fichero de PR-C, §15): busca `str(record.doi).lower()`, que con el DOI normalizado es la misma clave.
  - Desaparecen `busqueda._normalize_doi` y `open_backends._doi`. Respaldos de `record_id` sin cambios (`crossref:<DOI crudo o índice>`, `s2:<paperId>`, `europepmc:…`, `pubmed:<pmid>`, `pmc:<uid>`, `eric:…`, `doaj:…`, `bvs:…`/`gim:…`, `<base>:<handle>`, `unesdoc:<uuid>`).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_doi_backends.py`:

```python
"""Todo backend deja el DOI normalizado al construir el registro (spec 2026-10-18 §6, D19;
auditoría 2026-09-03, A4). Sin red: se sustituye el `_client` de cada módulo."""

from __future__ import annotations

import pytest

from revisia.agents import busqueda, dspace, ncbi, open_backends, search_backends
from revisia.agents.search_backends import BACKENDS

DOI_CRUDO = "https://doi.org/10.1000/ABC"  # la evidencia de A4
DOI = "10.1000/abc"

_PUBMED_XML = (
    "<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article>"
    "<ArticleTitle>t</ArticleTitle></Article></MedlineCitation><PubmedData><ArticleIdList>"
    f'<ArticleId IdType="doi">{DOI_CRUDO}</ArticleId></ArticleIdList></PubmedData>'
    "</PubmedArticle></PubmedArticleSet>"
)
_ITEM_DSPACE = {
    "handle": "h/1",
    "uuid": "u1",
    "metadata": {"dc.title": [{"value": "t"}], "dc.identifier.doi": [{"value": DOI_CRUDO}]},
}
_HAL = {  # forma de `tests/test_dspace.py:_hal`, una página
    "_embedded": {
        "searchResult": {
            "_embedded": {"objects": [{"_embedded": {"indexableObject": _ITEM_DSPACE}}]},
            "page": {"number": 0, "size": 1, "totalPages": 1, "totalElements": 1},
        }
    }
}
_DOAJ = {"id": "a", "bibjson": {"title": "t", "identifier": [{"type": "doi", "id": DOI_CRUDO}]}}
_BVS = {"id": "b1", "ti": ["t"], "aid": DOI_CRUDO}
_DOAB = [
    {
        "uuid": "d1",
        "handle": "h/1",
        "metadata": [
            {"key": "dc.title", "value": "t"},
            {"key": "oapen.identifier.doi", "value": DOI_CRUDO},
        ],
    }
]
# Fragmento de URL → respuesta con el DOI crudo en el campo nativo de cada fuente. Un backend
# nuevo sin ruta hace fallar el test (AssertionError del router): hay que añadirle su caso.
RUTAS: list[tuple[str, object]] = [
    ("api.openalex.org", {"results": [{"id": "https://openalex.org/W1", "doi": DOI_CRUDO, "display_name": "t"}]}),
    ("api.crossref.org", {"message": {"items": [{"DOI": DOI_CRUDO, "title": ["t"]}]}}),
    ("semanticscholar.org", {"data": [{"paperId": "p1", "title": "t", "externalIds": {"DOI": DOI_CRUDO}}]}),
    ("europepmc", {"resultList": {"result": [{"id": "1", "source": "MED", "title": "t", "doi": DOI_CRUDO}]}}),
    ("esearch.fcgi", {"esearchresult": {"idlist": ["1"]}}),
    ("efetch.fcgi", _PUBMED_XML),
    ("esummary.fcgi", {"result": {"uids": ["1"], "1": {"title": "t", "articleids": [{"idtype": "doi", "value": DOI_CRUDO}]}}}),
    ("api.ies.ed.gov/eric", {"response": {"docs": [{"id": "EJ1", "title": "t", "url": DOI_CRUDO}]}}),
    ("doaj.org", {"total": 1, "results": [_DOAJ]}),
    ("data.unesco.org", {"total_count": 1, "results": [{"uuid": "u", "title": "t"}]}),
    ("search.bvsalud.org", {"diaServerResponse": [{"response": {"numFound": 1, "docs": [_BVS]}}]}),
    ("/server/api/discover/search/objects", _HAL),
    ("directory.doabooks.org", _DOAB),
]
SIN_DOI = {open_backends.unesdoc_search}  # UNESDOC no expone DOI


class _Resp:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.text = payload if isinstance(payload, str) else ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _Router:
    """Sustituto de `httpx.Client`: responde por fragmento de URL y falla ante una no prevista."""

    def __init__(self, rutas: list[tuple[str, object]]) -> None:
        self._rutas = rutas

    def __enter__(self) -> _Router:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get(self, url: str, params: dict | None = None) -> _Resp:
        for fragmento, payload in self._rutas:
            if fragmento in url:
                return _Resp(payload)
        raise AssertionError(f"URL sin respuesta en el test: {url}")


def _enruta(monkeypatch: pytest.MonkeyPatch, rutas: list[tuple[str, object]]) -> None:
    for modulo in (busqueda, search_backends, ncbi, open_backends, dspace):
        monkeypatch.setattr(modulo, "_client", lambda *a, **k: _Router(rutas))
    monkeypatch.setattr(ncbi, "_sleep", lambda _s: None)


def test_todos_los_backends_normalizan_el_doi_al_construir(monkeypatch: pytest.MonkeyPatch) -> None:
    _enruta(monkeypatch, RUTAS)
    for fn in dict.fromkeys(BACKENDS.values()):
        (record,) = fn("q", 1)
        if fn in SIN_DOI:
            assert record.doi is None, repr(fn)
            continue
        assert (record.doi, record.record_id) == (DOI, DOI), repr(fn)
        assert "doi_raw" not in record.extra, repr(fn)


def test_doi_crudo_invalido_queda_en_extra_y_el_id_cae_al_respaldo(monkeypatch: pytest.MonkeyPatch) -> None:
    _enruta(monkeypatch, [("api.crossref.org", {"message": {"items": [{"DOI": "no-es-doi", "title": ["t"]}]}})])
    (r,) = search_backends.crossref_search("q", 1)
    assert (r.doi, r.record_id, r.extra) == (None, "crossref:no-es-doi", {"doi_raw": "no-es-doi"})


def test_campos_que_no_son_doi_no_dejan_doi_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    eric = {"response": {"docs": [{"id": "EJ1", "title": "t", "url": "https://eric.ed.gov/?id=EJ1"}]}}
    bvs = {"diaServerResponse": [{"response": {"numFound": 1, "docs": [{"id": "b1", "ti": ["t"], "aid": "S0034-89102020000100001"}]}}]}
    _enruta(monkeypatch, [("api.ies.ed.gov/eric", eric), ("search.bvsalud.org", bvs)])
    (r_eric,) = open_backends.eric_search("q", 1)
    (r_bvs,) = open_backends.bvs_search("q", 1)
    assert (r_eric.doi, r_eric.record_id, "doi_raw" in r_eric.extra) == (None, "eric:EJ1", False)
    assert (r_bvs.doi, r_bvs.record_id, "doi_raw" in r_bvs.extra) == (None, "bvs:b1", False)


def test_idconv_indexa_el_doi_normalizado(monkeypatch: pytest.MonkeyPatch) -> None:
    respuesta = {"records": [{"pmid": "1", "doi": "https://doi.org/10.1000/ABC", "pmcid": "PMC9"}]}
    _enruta(monkeypatch, [("idconv", respuesta)])
    assert ncbi.idconv([DOI], mailto="x@y.z")[DOI] == "PMC9"


def test_no_queda_ningun_normalizador_propio() -> None:
    assert not hasattr(busqueda, "_normalize_doi")
    assert not hasattr(open_backends, "_doi")
```

(Las líneas largas de `RUTAS` y de los dos tests siguientes las parte `black`; el contenido es este.)

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_doi_backends.py -v`
Expected: FAIL. `test_todos_los_backends…`: `busqueda.search` sin `_client` (AttributeError al sustituirlo); tras eso, `record_id` con prefijo en Crossref/S2/Europe PMC/PubMed (`ncbi.py:112`, `val.lower()`)/PMC. `test_doi_crudo_invalido…`: hoy `record_id == "no-es-doi"` (el `.lower().strip()` de Crossref no valida nada), no `crossref:no-es-doi`. `test_idconv…`: la clave es `https://doi.org/10.1000/abc`. `test_no_queda…`: FAIL.

- [ ] **Step 3: Implementar** el patrón de Interfaces en los cinco módulos (`from revisia.ingest.doi import doi_url, normalize_doi`; `dspace` deja de importar `_doi` de `open_backends`). Docstring de `open_backends`/`busqueda` donde vivían los normalizadores: una línea que remita a `ingest.doi` (D19). En `busqueda.py`, `_client` como en `search_backends.py:28-30` y la docstring de `search` sin el `Raises: RuntimeError` propio.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_doi_backends.py tests/test_busqueda.py tests/test_search_multibase.py tests/test_open_backends.py tests/test_dspace.py tests/test_pmc_ncbi.py -v`
Expected: PASS salvo `tests/test_open_backends.py::test_helpers_year_y_doi` (Step 5).

- [ ] **Step 5: Test que cambia de expectativa.** `tests/test_open_backends.py:360-366` (`test_helpers_year_y_doi`) llama a `open_backends._doi`, que ya no existe. Se conserva el nombre y las tres aserciones de `_year`; las tres de `_doi` pasan a `normalize_doi` (`from revisia.ingest.doi import normalize_doi`) con DOI de cuatro cifras: `normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"`, `normalize_doi("doi:10.1000/x") == "10.1000/x"`, `normalize_doi("https://example.org/no-doi") is None`.

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add revisia/agents tests/test_doi_backends.py tests/test_open_backends.py
git commit -m "refactor(busqueda): los backends usan normalize_doi para el record_id y pasan el DOI crudo (D19, A4)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 4: Ids de la importación manual con `normalize_doi` (D19, A4)

**Files:**
- Modify: `revisia/ingest/manual_import.py:22-25` (`_record_id`), `:44-52` (`parse_ris`: `doi=doi`, sin `.lower().strip()`), `:90-99` (`parse_bibtex`: lo mismo; el parser se rehace en la Tarea 5).
- Test: `tests/test_manual_import.py` (nuevo).

**Interfaces:**
- Consumes: `normalize_doi` (PR-0); `SearchRecord` (Tarea 2).
- Produces:
  - `_record_id(doi: str | None, title: str) -> str`: `normalize_doi(doi)` si normaliza; si no, `f"hash:{sha256_text(title.strip().lower())[:16]}"` **como hoy** (los ids sin DOI de un RIS de la 0.8 no cambian; un DOI inválido ahora cae al hash en vez de usar la cadena en minúsculas).
  - `parse_ris(text: str, *, source_db: str = "imported-RIS") -> list[SearchRecord]`: sin cambios funcionales salvo que pasa el `DO` crudo a `doi=` (el modelo lo normaliza o lo guarda en `doi_raw`).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_manual_import.py`:

```python
"""Importación manual: ids, BibTeX por llaves y corpus nativo (spec 2026-10-18 §6, D19, D23;
auditoría 2026-09-03, A4, A5)."""

from __future__ import annotations

import pytest

from revisia.ingest import parse_ris
from revisia.provenance.runmeta import sha256_text


@pytest.mark.parametrize(
    "crudo",
    ["doi:10.1000/ABC", "http://dx.doi.org/10.1000/abc", "https://doi.org/10.1000%2Fabc", "10.1000/abc."],
)
def test_record_id_importado_usa_normalize_doi(crudo: str) -> None:
    (r,) = parse_ris(f"TY  - JOUR\nTI  - T\nDO  - {crudo}\nER  -\n")
    assert r.record_id == r.doi == "10.1000/abc"


def test_ris_con_doi_invalido_cae_al_hash_y_guarda_el_crudo() -> None:
    (r,) = parse_ris("TY  - JOUR\nTI  - T\nDO  - PMC123\nER  -\n")
    assert r.record_id.startswith("hash:") and r.doi is None
    assert r.extra == {"doi_raw": "PMC123"}


def test_ris_sin_doi_conserva_el_id_de_la_08() -> None:
    (r,) = parse_ris("TY  - JOUR\nTI  - Un título\nER  -\n")
    assert r.record_id == f"hash:{sha256_text('un título')[:16]}"  # como en la 0.8
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_manual_import.py -v`
Expected: FAIL en los casos `doi:`, `dx.doi.org` y `%2F` (hoy `_record_id` solo quita `https://doi.org/`) y en el DOI inválido (hoy `record_id == "pmc123"`); PASS el resto.

- [ ] **Step 3: Implementar** `_record_id` y los dos `doi=` según Interfaces (docstring de `_record_id`: D19, A4; el hash del título no cambia a propósito, §18 riesgo 6).

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_manual_import.py tests/test_search_multibase.py tests/test_identidad_registros.py -v`
Expected: PASS. Después, la suite entera: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/ingest/manual_import.py tests/test_manual_import.py
git commit -m "fix(ingest): el record_id importado usa normalize_doi y el doi viaja crudo al modelo (D19, A4)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 5: Parser BibTeX por llaves (A5)

**Files:**
- Modify: `revisia/ingest/manual_import.py:73-104` (`parse_bibtex` y dos funciones privadas nuevas).
- Test: `tests/test_manual_import.py` (añadir).

**Interfaces:**
- Consumes: `_record_id`, `_year` (Tarea 4).
- Produces:
  - `parse_bibtex(text: str, *, source_db: str = "imported-BibTeX") -> list[SearchRecord]` (misma firma; mismos campos usados: `title`, `doi`, `author` partido por ` and `, `abstract`, `year`, `url`).
  - `_bib_entries(text: str) -> Iterator[tuple[str, str]]`: `(tipo en minúsculas, cuerpo)` por entrada. Busca `@\s*(\w+)\s*\{`; un `@\w+\s*\(` cuyo tipo no sea `comment`, `preamble` ni `string` → `ValueError("BibTeX: @<tipo>(…) no soportado (línea <n>)")`; desde la llave cuenta llaves (sin mirar comillas) hasta la que cierra; el cuerpo es lo de dentro. Un `@` que no abre `tipo{` se salta. Llaves sin cerrar al final del texto → `ValueError("BibTeX: entrada @<tipo> sin cerrar (línea <n>)")`.
  - `_bib_fields(body: str) -> dict[str, str]`: salta la clave de cita (hasta la primera coma); después, repetidamente `nombre = valor` con `nombre` = `[^\s=,{}"#]+` (admite `Unique-ID`, `web-of-science-categories`…) en minúsculas y `valor` = una o más piezas unidas por `#`, cada pieza `{…}` (llaves anidadas, se quitan todas las llaves internas), `"…"` (se quitan las llaves internas) o un token desnudo `[\w.:-]+` (número o macro, que se conserva **literal**: las macros `@string` no se expanden); el valor final con espacios colapsados (`" ".join(v.split())`). Un texto que no casa con `nombre = valor` (tras las comas y espacios entre campos) → `ValueError("BibTeX: campo ilegible en @<tipo>{<clave>} (línea <n>)")`: el fichero queda `failed` (M7) en vez de truncar la entrada en silencio.
  - Entradas `@comment`, `@preamble` y `@string` se ignoran; una entrada sin campos se ignora (como hoy). Sin decodificación LaTeX (solo se quitan llaves).

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_manual_import.py` (imports: `parse_bibtex` de `revisia.ingest`, `deduplicate_with_report` de `revisia.agents.dedup`):

```python
def test_a5_bibtex_con_llaves_anidadas_conserva_el_titulo() -> None:
    # La evidencia de A5 tal cual: hoy el título se pierde y sale "(sin título)".
    bib = "@article{imf2020,\n  title = {The {IMF} and growth},\n  doi = {10.1000/IMF}\n}\n"
    (r,) = parse_bibtex(bib)
    assert r.title == "The IMF and growth"
    assert r.doi == r.record_id == "10.1000/imf"


def test_a5_dos_entradas_con_llaves_anidadas_siguen_siendo_dos() -> None:
    bib = (
        "@article{a,\n  title = {The {IMF} and growth}\n}\n"
        "@article{b,\n  title = {The {OECD} and growth}\n}\n"
    )
    registros = parse_bibtex(bib)
    assert [r.title for r in registros] == ["The IMF and growth", "The OECD and growth"]
    assert deduplicate_with_report(registros)[1].n_out == 2  # hoy: 1


def test_bibtex_comillas_numeros_y_concatenacion() -> None:
    (r,) = parse_bibtex('@article{k, title = "Un " # {estudio}, year = 2021, author = {Doe, J. and Roe, A.}}')
    assert (r.title, r.year, r.authors) == ("Un estudio", 2021, ["Doe, J.", "Roe, A."])


def test_bibtex_ignora_comment_string_preamble_y_arrobas_en_valores() -> None:
    bib = (
        "@comment{nada}\n@string{j = \"Journal\"}\n@preamble{\"x\"}\n"
        "@article{k, title = {Correo a x@y.org}, note = {a @ b}, journal = j}\n"
    )
    (r,) = parse_bibtex(bib)
    assert r.title == "Correo a x@y.org"


def test_bibtex_campos_en_mayusculas_y_saltos_de_linea() -> None:
    (r,) = parse_bibtex("@Article{k,\n  TITLE = {Multi\n    línea},\n  Year = {2020},\n}\n")
    assert (r.title, r.year) == ("Multi línea", 2020)


def test_bibtex_de_wos_con_nombres_de_campo_con_guion() -> None:
    # Web of Science exporta `Unique-ID` antes de `title`/`doi`: no puede cortar la entrada.
    bib = "@article{ISI:1,
  Unique-ID = {{WOS:1}},
  Title = {Un {LLM} criba},
  DOI = {10.1000/WOS1},
}
"
    (r,) = parse_bibtex(bib)
    assert (r.title, r.doi, r.record_id) == ("Un LLM criba", "10.1000/wos1", "10.1000/wos1")


def test_bibtex_campo_ilegible_es_error() -> None:
    with pytest.raises(ValueError, match="campo ilegible"):
        parse_bibtex("@article{k, title = {Bien}, = {sin nombre}}
")


def test_bibtex_con_parentesis_no_soportado_es_error() -> None:
    with pytest.raises(ValueError, match=r"no soportado \(línea 2\)"):
        parse_bibtex("@comment(nada)
@article(k, title = {T})
")


def test_bibtex_entrada_sin_cerrar_es_error_y_no_un_registro_a_medias() -> None:
    with pytest.raises(ValueError, match="sin cerrar"):
        parse_bibtex("@article{ok, title = {Bien}}\n@article{k, title = {Abierto}\n")
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_manual_import.py -v`
Expected: FAIL en los dos de A5, la concatenación, el `@` en un valor, `Unique-ID`, el campo ilegible, `@tipo(…)` y la entrada sin cerrar.

- [ ] **Step 3: Implementar** según Interfaces. Docstring de `parse_bibtex`: el porqué (A5: el regex sin anidamiento perdía el título y los títulos de relleno se fusionaban), lo que soporta y lo que no (macros, LaTeX, `@tipo(…)` con paréntesis, que es error), y que una entrada sin cerrar o un campo ilegible hacen fallar el fichero entero, que la búsqueda registra como `failed` (M7) en vez de importar medio registro.

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_manual_import.py tests/test_search_multibase.py tests/test_brain.py -v`
Expected: PASS. Después, la suite entera: PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/ingest/manual_import.py tests/test_manual_import.py
git commit -m "fix(ingest): parser BibTeX por conteo de llaves; las llaves anidadas ya no pierden el título (A5)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 6: Clave de dedup con NFKD y títulos de relleno que nunca se fusionan (D19, A5)

**Files:**
- Modify: `revisia/agents/dedup.py:1-15` (docstring: fuera el `#2` de A4 como caso típico; D19), `:24-35` (`_title_key`, `dedup_key`, constantes), `:46-105` (`deduplicate_with_report`).
- Modify: `revisia/schemas/artifacts.py` (`class DedupReport`, línea 231 en `main`): campo nuevo.
- Test: `tests/test_dedup.py` (añadir).

**Interfaces:**
- Consumes: `normalize_doi` (PR-0).
- Produces (los consume el auditor de PR-G):
  - `PLACEHOLDER_TITLES: frozenset[str] = frozenset({"", "(sin título)", "untitled", "[no title]", "sin título", "no title"})` (§6, literal).
  - `is_placeholder_title(title: str) -> bool`: `_title_key(title)` ∈ `{_title_key(t) for t in PLACEHOLDER_TITLES}` (= `{"", "sin titulo", "untitled", "no title"}`); así `"SIN TITULO"`, `"Untitled."` o `"  "` también son relleno.
  - `_title_key(title: str) -> str`: `unicodedata.normalize("NFKD", title)`, sin caracteres `unicodedata.combining`, `lower()`, `[^a-z0-9]+` → un espacio, `strip()` (las palabras siguen separadas por un espacio, como hoy).
  - `dedup_key(record: SearchRecord) -> str`: `f"doi:{d}"` con `d = normalize_doi(record.doi)` si no es `None`; si no, `f"none:{record.record_id}"` si `is_placeholder_title(record.title)`; si no, `f"title:{_title_key(record.title)}"`.
  - `deduplicate_with_report`: un registro con clave `none:` se conserva siempre (no entra en `position`, nunca es duplicado de nadie ni nadie de él) y suma 1 a `unmerged_placeholders`; el renombrado `#n` posterior no cambia (dos rellenos importados con el mismo `hash:` salen `id` e `id#2`).
  - `DedupReport.unmerged_placeholders: int = 0` (default 0: un `dedup.json` de la 0.8 sigue validando). `02_dedup/dedup.json` lo lleva sin tocar `pipeline.py` (`pipeline.py:400` escribe `report.model_dump`).

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_dedup.py` (imports: `PLACEHOLDER_TITLES`, `dedup_key`, `is_placeholder_title` de `revisia.agents.dedup`):

```python
# ── Ola 2 · D19, A5: NFKD y títulos de relleno (spec 2026-10-18 §6) ──


def test_dedup_nfkd_fusiona_titulos_con_y_sin_acentos() -> None:
    recs = [
        SearchRecord(record_id="a", title="Educación rural en Colombia"),
        SearchRecord(record_id="b", title="EDUCACION RURAL EN COLOMBIA"),
        SearchRecord(record_id="c", title="Educacio\u0301n rural en Colombia"),  # NFD
    ]
    unicos, informe = deduplicate_with_report(recs)
    assert [r.record_id for r in unicos] == ["a"]
    assert {d.key for d in informe.duplicates} == {"title:educacion rural en colombia"}


def test_a5_titulos_de_relleno_nunca_se_fusionan() -> None:
    recs = [
        SearchRecord(record_id="hash:1", title="(sin título)"),
        SearchRecord(record_id="hash:2", title="(sin título)"),
        SearchRecord(record_id="x", title="Untitled"),
        SearchRecord(record_id="y", title="[No title]"),
        SearchRecord(record_id="z", title="  "),
        SearchRecord(record_id="w", title="SIN TITULO"),
    ]
    unicos, informe = deduplicate_with_report(recs)
    assert len(unicos) == 6 and informe.duplicates == []
    assert informe.unmerged_placeholders == 6
    assert dedup_key(recs[0]) == "none:hash:1"


def test_relleno_con_el_mismo_doi_si_se_fusiona_por_doi() -> None:
    recs = [
        SearchRecord(record_id="a", title="(sin título)", doi="10.1000/x"),
        SearchRecord(record_id="b", title="Untitled", doi="10.1000/X"),
    ]
    unicos, informe = deduplicate_with_report(recs)
    assert len(unicos) == 1 and informe.unmerged_placeholders == 0


def test_a5_dos_sin_titulo_importados_siguen_siendo_dos() -> None:
    recs = parse_ris("TY  - JOUR\nER  -\nTY  - JOUR\nER  -\n")  # dos "(sin título)", mismo hash
    unicos, informe = deduplicate_with_report(recs)
    rid = recs[0].record_id
    assert [r.record_id for r in unicos] == [rid, f"{rid}#2"]
    assert informe.unmerged_placeholders == 2 and informe.duplicates == []


def test_placeholder_titles_es_el_del_spec() -> None:
    assert PLACEHOLDER_TITLES == frozenset(
        {"", "(sin título)", "untitled", "[no title]", "sin título", "no title"}
    )
    assert is_placeholder_title("Sin Titulo.") and not is_placeholder_title("Sin título previo")


def test_dedup_report_de_la_08_sigue_validando() -> None:
    assert DedupReport.model_validate({"n_in": 1, "n_out": 1}).unmerged_placeholders == 0


def test_dedup_json_registra_unmerged_placeholders(tmp_path: Path) -> None:
    def busqueda(query: str, n: int) -> list[SearchRecord]:
        return [
            SearchRecord(record_id="a", title="(sin título)", source_db="OpenAlex"),
            SearchRecord(record_id="b", title="(sin título)", source_db="PubMed"),
            SearchRecord(record_id="c", title="Un estudio", source_db="OpenAlex"),
        ]

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=busqueda)
    informe = DedupReport.model_validate_json(
        (ctx.run_dir / "02_dedup" / "dedup.json").read_text("utf-8")
    )
    assert (informe.n_in, informe.n_out, informe.unmerged_placeholders) == (3, 3, 2)
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_dedup.py -v`
Expected: FAIL (`ImportError: PLACEHOLDER_TITLES`); tras definir solo las constantes, fallan NFKD (hoy `educaci n`), los rellenos (hoy uno solo) y `unmerged_placeholders`.

- [ ] **Step 3: Implementar** según Interfaces. Docstrings: `dedup_key` explica las tres claves y por qué un relleno no forma clave (A5: dos registros distintos sin título colapsaban en uno y el revisor perdía uno sin saberlo); `unmerged_placeholders` en `DedupReport`: «registros sin DOI y con título de relleno, conservados sin deduplicar (D19); el auditor puede recalcularlo».

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_dedup.py tests/test_artifacts.py tests/test_identidad_registros.py -v`
Expected: PASS. Después, la suite entera (incluye la auditoría de corridas reales de `conftest.py`): PASS.

- [ ] **Step 5: Commit**

```bash
git add revisia/agents/dedup.py revisia/schemas/artifacts.py tests/test_dedup.py
git commit -m "fix(dedup): títulos NFKD sin diacríticos y los de relleno nunca se fusionan; unmerged_placeholders (D19, A5)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 7: Corpus nativo `imported/*.records.json` (D23)

**Files:**
- Modify: `revisia/ingest/manual_import.py:1-8` (docstring), `:18-19` (`IMPORT_SUFFIXES` → `import_format`), `:107-137` (`import_file`, `import_directory`), y `parse_records_json` nueva.
- Modify: `revisia/ingest/__init__.py` (exportar `parse_records_json`, `import_format` e `ignored_files` junto a lo que exporta PR-0; docstring «RIS, BibTeX y registros nativos»).
- Modify: `revisia/schemas/artifacts.py` (`SearchEntryKind`, línea 92 en `main`: literal nuevo al lado; `class SearchLogEntry`, línea 181: campo nuevo).
- Modify: `revisia/orchestration/search_stage.py:27` (import), `:110-131` (`_import`), `:184-189` (`multi_database_search`).
- Modify: `revisia/llm/preflight.py:51-52` (`_IMPORT_SUFFIXES` fuera), `:363-376` (`has_imports`, el mensaje y un aviso por fichero ignorado).
- Modify: `tests/test_preflight.py:358` (ver Step 5).
- Test: `tests/test_manual_import.py`, `tests/test_search_stage.py`, `tests/test_preflight.py` (añadir).

**Interfaces:**
- Consumes: `SearchRecord` (Tarea 2), `parse_ris`/`parse_bibtex` (Tareas 4–5).
- Produces (los consume PR-F para el benchmark, §10.2):
  - `ImportFormat = Literal["ris", "bibtex", "records_json"]` en `revisia/schemas/artifacts.py`.
  - `import_format(path: str | Path) -> ImportFormat | None`: `records_json` si el **nombre** es `records.json` o termina en `.records.json` (sin distinguir mayúsculas; así vale la copia tal cual de `02_dedup/records.json`); `ris` con sufijo `.ris`; `bibtex` con `.bib`/`.bibtex`; si no, `None` (un `.json` cualquiera sigue sin importarse, como hoy).
  - `parse_records_json(text: str) -> list[SearchRecord]`: `json.loads`; exige una lista; valida cada elemento con `SearchRecord.model_validate` (el DOI pasa por la Tarea 2; `record_id`, `source_db` y `extra` se conservan tal cual); `record_id` repetido → `ValueError("<id>: record_id repetido en el corpus nativo; copia 02_dedup/records.json de la corrida, que ya está desambiguado")`. Errores: `ValueError` (incluye `json.JSONDecodeError` y `pydantic.ValidationError`, que lo son).
  - `import_file(path: str | Path) -> list[SearchRecord]`: despacha por `import_format`; un `records_json` se lee con `encoding="utf-8-sig"` (un BOM de un editor de Windows no lo rompe); `ValueError` con el mensaje de hoy ampliado («usa .ris, .bib, .bibtex o .records.json») si es `None`.
  - `import_directory(directory)`: importa todo fichero con `import_format(p) is not None`, en orden de nombre.
  - `ignored_files(directory: str | Path) -> list[str]`: nombres, en orden, de los **ficheros** de la carpeta que `import_format` no reconoce (los directorios no cuentan); vacío si la carpeta no existe. El preflight emite un aviso por cada uno (`where = "imported/<nombre>"`, «no se importa: usa .ris, .bib, .bibtex o *.records.json»), para que un `corpus.json` mal nombrado no desaparezca en silencio.
  - `SearchLogEntry.format: ImportFormat | None = None`: lo pone `search_stage._import` para **toda** importación (`ris`, `bibtex`, `records_json`); `None` en bases e inyectadas, y en los logs de la 0.8.
  - `IMPORT_SUFFIXES` desaparece (su único consumidor era `search_stage.py:27`); `preflight` usa `import_format` e `ignored_files`.

- [ ] **Step 1: Tests que fallan.** Añadir a `tests/test_manual_import.py` (imports: `json`, `Path`, `get_args`, `ignored_files`, `import_directory`, `import_file`, `import_format`, `parse_records_json` de `revisia.ingest`, `ImportFormat` de `revisia.schemas.artifacts`, `SearchRecord`):

```python
def _corpus() -> list[SearchRecord]:
    # Como la copia de `02_dedup/records.json` de una exploratoria (D18, D23).
    return [
        SearchRecord(record_id="hash:abc", title="Sin DOI", source_db="OpenAlex"),
        SearchRecord(
            record_id="10.1000/x#2", title="T", doi="10.1000/x", source_db="PubMed",
            extra={"pmcid": "PMC1"},
        ),
        SearchRecord(record_id="crossref:1", title="U", doi="no-es-doi", source_db="Crossref"),
    ]


def test_parse_records_json_conserva_ids_source_db_y_extra() -> None:
    corpus = _corpus()
    texto = json.dumps([r.model_dump(mode="json") for r in corpus])
    assert parse_records_json(texto) == corpus  # ids, source_db y doi_raw intactos


@pytest.mark.parametrize(
    "malo",
    ["no json", "{}", "[1]", '[{"title": "sin id"}]', '[{"record_id": "a", "title": "x"}, {"record_id": "a", "title": "y"}]'],
)
def test_parse_records_json_rechaza_lo_que_no_es_un_corpus(malo: str) -> None:
    with pytest.raises(ValueError):
        parse_records_json(malo)


@pytest.mark.parametrize(
    ("nombre", "formato"),
    [
        ("a.ris", "ris"), ("b.BIB", "bibtex"), ("c.bibtex", "bibtex"),
        ("corpus.records.json", "records_json"), ("CORPUS.Records.JSON", "records_json"),
        ("records.json", "records_json"),
        ("otro.json", None), ("x.txt", None),
    ],
)
def test_import_format_por_nombre(nombre: str, formato: str | None) -> None:
    assert import_format(nombre) == formato


def test_import_format_cubre_el_literal() -> None:
    assert set(get_args(ImportFormat)) == {"ris", "bibtex", "records_json"}


def test_import_directory_lee_records_json_e_ignora_otros_json(tmp_path: Path) -> None:
    corpus = _corpus()
    (tmp_path / "corpus.records.json").write_text(
        json.dumps([r.model_dump(mode="json") for r in corpus]), encoding="utf-8"
    )
    (tmp_path / "otro.json").write_text("[]", encoding="utf-8")
    (tmp_path / "sub.ris").mkdir()  # un directorio no es un fichero ignorado
    assert import_directory(tmp_path) == corpus
    assert ignored_files(tmp_path) == ["otro.json"]  # de él sale el aviso del preflight
    assert import_file(tmp_path / "corpus.records.json") == corpus
    con_bom = tmp_path / "records.json"
    con_bom.write_bytes(b"ï»¿" + json.dumps([corpus[0].model_dump(mode="json")]).encode())
    assert import_file(con_bom) == corpus[:1]
    with pytest.raises(ValueError, match="records.json"):
        import_file(tmp_path / "otro.json")
```

Añadir a `tests/test_search_stage.py` (usa sus `_protocolo`, `_log`, `load_protocol`, `run_search`):

```python
def test_records_json_importado_conserva_ids_y_queda_en_el_log_con_su_formato(tmp_path: Path) -> None:
    proto = _protocolo(tmp_path, ["Scopus"])  # base manual: no se llama a ningún backend
    (proto / "imported").mkdir()
    corpus = [
        SearchRecord(record_id="hash:abc", title="Sin DOI", source_db="OpenAlex"),
        SearchRecord(record_id="10.1000/x", title="T", doi="10.1000/x", source_db="PubMed"),
    ]
    (proto / "imported" / "corpus.records.json").write_text(
        json.dumps([r.model_dump(mode="json") for r in corpus]), encoding="utf-8"
    )
    (proto / "imported" / "scopus.ris").write_text(_RIS, encoding="utf-8")
    (proto / "imported" / "notas.json").write_text("{}", encoding="utf-8")
    (proto / "imported" / "roto.records.json").write_text("{}", encoding="utf-8")
    ctx = RunContext("demo", tmp_path / "runs", "T")
    records = run_search(
        load_protocol(proto), source_dir=proto, strings_dir=proto / "search_strings",
        question="q", max_results=5, mailto=None, search_fn=None, run_ctx=ctx,
    )
    assert [r.record_id for r in records][:2] == ["hash:abc", "10.1000/x"]
    por_fichero = {e.database: e for e in _log(ctx).entries if e.kind == "manual_import"}
    assert set(por_fichero) == {
        "imported/corpus.records.json", "imported/roto.records.json", "imported/scopus.ris",
    }
    corpus_e = por_fichero["imported/corpus.records.json"]
    assert (corpus_e.format, corpus_e.status, corpus_e.n_returned) == ("records_json", "ok", 2)
    assert corpus_e.source_db == ["OpenAlex", "PubMed"]
    assert por_fichero["imported/scopus.ris"].format == "ris"
    roto = por_fichero["imported/roto.records.json"]
    assert (roto.format, roto.status, roto.n_returned) == ("records_json", "failed", 0)
```

Añadir a `tests/test_preflight.py`, **justo después de `test_preflight_imported_solo_cuenta_ficheros`** (línea 354; no al final del fichero, donde PR-A también añade tests):

```python
def test_preflight_cuenta_records_json_y_avisa_de_lo_que_ignora(proto_dir: Path) -> None:
    protocol = _proto(databases=["OpenAlex", "Scopus"])
    imported = proto_dir / "imported"
    imported.mkdir()
    (imported / "records.json").write_text("[]", "utf-8")
    assert "imported/" not in _messages(_run(protocol, proto_dir).warnings)
    (imported / "corpus.json").write_text("[]", "utf-8")  # mal nombrado: no se importa
    avisos = _messages(_run(protocol, proto_dir).warnings)
    assert "[imported/corpus.json] no se importa" in avisos
```

- [ ] **Step 2: Run para verificar que falla**

Run: `uv run pytest -p no:cacheprovider tests/test_manual_import.py tests/test_search_stage.py tests/test_preflight.py -v`
Expected: FAIL (`ImportError: parse_records_json`/`import_format`/`ImportFormat`; después, `format` ausente en el log y el aviso del preflight).

- [ ] **Step 3: Implementar** según Interfaces. Docstrings: `parse_records_json` explica D23 (el gold etiquetado sobre la exploratoria casa con el corpus del panel porque los ids no se recalculan; con RIS/BibTeX un registro sin DOI recibiría otro `hash:`), que un id repetido es un corpus dañado (renombrarlo en silencio rompería el gold) y que el DOI se renormaliza al leer (idempotente). Mensajes del preflight: «… y no hay ficheros .ris/.bib/.records.json en imported/: …» y, por fichero ignorado, «no se importa: usa .ris, .bib, .bibtex o *.records.json».

- [ ] **Step 4: Run para verificar que pasa**

Run: `uv run pytest -p no:cacheprovider tests/test_manual_import.py tests/test_search_stage.py tests/test_preflight.py tests/test_search_multibase.py tests/test_audit_busqueda.py -v`
Expected: PASS salvo `tests/test_preflight.py::test_preflight_imported_solo_cuenta_ficheros` (Step 5).

- [ ] **Step 5: Test que cambia de expectativa.** `tests/test_preflight.py:358`: `"no hay ficheros .ris/.bib en imported/"` → `"no hay ficheros .ris/.bib/.records.json en imported/"`.

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add revisia/ingest revisia/schemas/artifacts.py revisia/orchestration/search_stage.py revisia/llm/preflight.py tests/test_manual_import.py tests/test_search_stage.py tests/test_preflight.py
git commit -m "feat(ingest): corpus nativo imported/*.records.json con ids intactos y formato en el log (D23)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Tarea 8: Integración de PR-B (controlador)

**Files:**
- Modify (tras el rebase): `tests/test_search_backends_parsers.py` (de PR-H; las dos aserciones de DOI).
- Modify: `CHANGELOG.md` (bloque `## [Unreleased]`).
- Modify: `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md` (§19).

**Interfaces:** ninguna de código nueva. Deja la rama `feat/ola2-identidad-registros` rebasada sobre A, publicada, y la PR abierta (sin merge) con base `feat/ola2-procedencia` (§15).

- [ ] **Step 1: Rebase sobre A** (A ya va sobre H; §15: «base de la PR: A tras rebase»).

```bash
git fetch origin
git rebase origin/feat/ola2-procedencia
```

Expected: conflictos en tres ficheros, todos de **conservar ambas partes**: `revisia/llm/preflight.py` (A añade constantes junto a las líneas 42-52, donde B quita `_IMPORT_SUFFIXES`: quedan las de A y desaparece `_IMPORT_SUFFIXES`), `tests/test_preflight.py` (A añade tests al final; el de B va junto a `test_preflight_imported_solo_cuenta_ficheros`) y `revisia/schemas/artifacts.py` (A retira `RunInfo.prompt_sha256`; B añade `ImportFormat`, `SearchLogEntry.format` y `DedupReport.unmerged_placeholders`). Si `tests/fakes.py` o `tests/conftest.py` chocan, lo mismo. `git rebase --continue` tras cada uno y la suite en verde al final. `requires-python >= 3.11` ya viene de H.

- [ ] **Step 2: Adaptar el test de parsers de PR-H.** En `tests/test_search_backends_parsers.py` (PR-H, Tarea 5), las dos líneas que reproducen la normalización vieja (`doi = (it.get("DOI") or "").lower().strip() or None` en el test de Crossref y `doi = ((p.get("externalIds") or {}).get("DOI") or "").lower().strip() or None` en el de S2) pasan a `doi = normalize_doi(it.get("DOI"))` y `doi = normalize_doi((p.get("externalIds") or {}).get("DOI"))` (`from revisia.ingest.doi import normalize_doi`). El resto del fichero no cambia (el respaldo `crossref:` del tercer ítem sin `DOI` sigue igual).

Run: `uv run pytest -p no:cacheprovider tests/test_search_backends_parsers.py -v`
Expected: PASS.

Y comprobar que A y H no trajeron fixtures nuevas con DOI de registrante corto que lleguen a `SearchRecord.doi` o a un parser:

```bash
grep -rnE "10\.[0-9]{1,3}/" tests
```

Expected: el resultado se revisa **a mano**: quedan los usos como `record_id`, ids de diario o texto (`test_artifacts`, `test_brain`, `test_hitl`, `test_interop`, `test_fakes`, `test_run_context`…), que no pasan por `normalize_doi`; cualquier `doi=`, `"doi":`, `DO  -`, `doi = {…}` o campo DOI de una respuesta simulada se migra como en la Tarea 2, Step 5, y se anota en §19.

```bash
git add tests/test_search_backends_parsers.py
git commit -m "test: los parsers de Crossref y S2 esperan el DOI de normalize_doi (D19)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: CHANGELOG.** En `## [Unreleased]`, añadir en `### Added`:

```
- **Corpus nativo `imported/*.records.json`** (D23): una `list[SearchRecord]` (p. ej. la copia
  de `02_dedup/records.json` de una corrida exploratoria) se importa con sus `record_id`,
  `source_db` y `extra` intactos, para que un `gold.yml` etiquetado sobre ella case con el
  corpus del benchmark. `01_search/log.json` registra el `format` de cada importación
  (`ris`, `bibtex`, `records_json`).
- `02_dedup/dedup.json` gana `unmerged_placeholders`: registros sin DOI y con título de relleno,
  que ya no se deduplican (A5).
```

en `### Changed`:

```
- **Un solo normalizador de DOI** (`revisia.ingest.doi.normalize_doi`, D19): `SearchRecord`
  normaliza `doi` al construirse y guarda el original no reconocible en `extra["doi_raw"]`;
  los backends y la importación manual calculan el `record_id` con la misma función. Los ids
  de una corrida nueva pueden diferir de los de la 0.8 para el mismo artículo (riesgo 6).
- El dedup normaliza los títulos con NFKD y sin diacríticos; un título de relleno
  (`(sin título)`, `untitled`, `[no title]`…) nunca forma clave.
- El backend de OpenAlex usa el cliente HTTP compartido (User-Agent con `mailto`).
```

y en `### Fixed`:

```
- El mismo artículo importado por RIS con `https://doi.org/…` y traído de OpenAlex es **un**
  registro, sin renombrado `#2` (auditoría 2026-09-03, A4).
- BibTeX con llaves anidadas (`title = {The {IMF} and growth}`) conserva el título, y dos
  registros sin título ya no se fusionan en uno (A5).
```

- [ ] **Step 4: Desviaciones en el spec (§19).** Añadir **a continuación de la última fila existente**, con numeración consecutiva, estas filas (y las que haya producido la revisión por tarea):

```
| n | §6 `SearchRecord.doi` | La normalización va en el validador `before` del modelo (el que ya quitaba sustitutos), no en un `field_validator`: uno de campo no puede escribir `extra["doi_raw"]`. Solo actúa sobre un `str`; un `""` o espacios no deja `doi_raw`; un no-`str` lo rechaza la validación de tipo; un `extra` que no es `dict` se deja para que salga `ValidationError`. `normalize_doi` se importa dentro de la función (ciclo `records → ingest/__init__ → manual_import → records`) | Plan PR-B |
| n+1 | §6 backends | Cada backend pasa a `doi=` el valor crudo del campo que la fuente etiqueta como DOI y calcula el `record_id` con `normalize_doi`. ERIC (`url`) y BVS (`aid`) pasan solo el normalizado: no son campos DOI y un valor que no lo es no es un «DOI crudo». DSpace toma el primer valor que normaliza (si ninguno, el primer crudo). `busqueda.search` usa `_client()` → `_http.make_client`, como los demás. `ncbi.idconv` indexa el DOI de la respuesta con `normalize_doi`; `fulltext._resolve_pmcid` (fichero de PR-C) no se toca: su `str(record.doi).lower()` ya es la clave normalizada | Plan PR-B |
| n+2 | §6, PR-0 `DOI_RE` | Las fixtures con registrante de una cifra (`10.1/abc`) dejan de ser DOI con `\d{4,9}`: se migran a `10.N000/…` en `test_busqueda`, `test_coverage_gaps`, `test_dedup`, `test_fulltext`, `test_errores_deterministas`, `test_exports_biblio_extraction`, `test_hitl_pipeline`, `test_pmc_ncbi`, `test_search_multibase`, `test_search_stage` y `test_audit_busqueda`. `DOI_RE` no se relaja. Un plan posterior que construya `SearchRecord(doi="10.1/…")` obtiene `doi=None` y `doi_raw` | Plan PR-B |
| n+3 | §4.1, §4.4 | `DedupReport.unmerged_placeholders: int = 0` y `SearchLogEntry.format: ImportFormat \| None = None` (`ImportFormat = Literal["ris","bibtex","records_json"]`) los añade PR-B en `schemas/artifacts.py`: §4.1 los da como contrato, pero §4.4 y el plan de PR-0 no los incluyen. `format` se escribe en toda importación, no solo en `records_json`; default para que los artefactos v1 validen | Plan PR-B |
| n+4 | §6 dedup | La clave de título conserva un espacio entre palabras (`title:educacion rural`), como en la 0.8. Los títulos de relleno se comparan normalizados (`"SIN TITULO"`, `"Untitled."`, `"  "` lo son). Un relleno se cuenta en `unmerged_placeholders` y, si su id choca con otro, sigue pasando por el renombrado `#n` | Plan PR-B |
| n+5 | §6 BibTeX | `@comment`, `@preamble` y `@string` se ignoran; las macros no se expanden (el token desnudo se conserva literal); sin decodificación LaTeX (solo se quitan llaves); los nombres de campo son `[^\s=,{}"#]+` (admite `Unique-ID` de WoS); `@tipo(…)` con paréntesis, un campo ilegible o una entrada sin cerrar hacen fallar el fichero entero (`ValueError`, queda `failed` en el log, M7) en vez de importar medio registro | Plan PR-B |
| n+6 | D23 | `parse_records_json(text) -> list[SearchRecord]` rechaza (`ValueError`) lo que no es una lista, registros inválidos y `record_id` repetidos. Se lee con `utf-8-sig`. Un fichero se reconoce por el nombre (`records.json` o `*.records.json`, sin distinguir mayúsculas) con `import_format(path)`, que sustituye a `IMPORT_SUFFIXES` en la búsqueda y en el preflight; un `.json` cualquiera sigue sin importarse, pero el preflight avisa de cada fichero de `imported/` que ignora (`ignored_files`) | Plan PR-B |
| n+7 | D19 | En la importación manual, un registro sin DOI conserva el id de la 0.8 (`hash:` del título); uno con DOI no reconocible cae a ese hash (antes usaba la cadena en minúsculas) y guarda el crudo en `doi_raw` | Plan PR-B |
| n+8 | §15 | `schemas/records.py` y `agents/dedup.py` no figuran en la tabla de solapes de §15 pero son de esta pista (nadie más los toca). PR-B toca además `orchestration/search_stage.py` (`_import`, `multi_database_search`), `llm/preflight.py` (detección de `imported/`) y `schemas/artifacts.py` (dos campos aditivos). **No toca `orchestration/pipeline.py`** | Plan PR-B |
```

- [ ] **Step 5: Commit de documentación.**

```bash
git add CHANGELOG.md docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md
git commit -m "docs: CHANGELOG y desviaciones (§19) de PR-B" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Verificación completa.**

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" && uv run pytest -p no:cacheprovider -m cronometrado`
Expected: PASS; anotar el recuento (base: el de A).

Run: `uv run --python 3.11 pytest -p no:cacheprovider -q -n auto -m "not cronometrado"` y lo mismo con `--python 3.12`.
Expected: PASS.

Run: `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado" --cov --cov-report=term-missing:skip-covered | tail -5`
Expected: total ≥ 90 % (D25) y `revisia/ingest/manual_import.py`, `revisia/agents/dedup.py` sin líneas nuevas sin cubrir.

Run: `uv run ruff check . && uv run ruff format --check . && uv run black --check . && uv lock --check`
Expected: limpio.

Run (D19, ningún normalizador propio):

```bash
grep -rnE --include=*.py 'lower\(\)\.strip\(\)|doi = [^=]*\.lower\(\)|_normalize_doi|def _doi|import _doi|replace\("https://doi' revisia/agents revisia/ingest revisia/schemas
```

Expected: sin resultados (en `main` @ `c1af7c3` da 16 líneas; sobre el borrador de este plan, ninguna).

- [ ] **Step 7: Publicar la rama y abrir PR-B** (sin merge).

```bash
git push -u origin feat/ola2-identidad-registros
gh pr create --base feat/ola2-procedencia --head feat/ola2-identidad-registros --title "Ola 2 · PR-B: identidad de los registros (DOI único, dedup y corpus nativo)" --body "$(cat <<'EOF'
## Qué es

Cuarta PR de la Ola 2 (spec `docs/superpowers/specs/2026-10-18-ola-2-remediacion-design.md`, §6; plan `docs/superpowers/plans/2026-10-19-ola2-prb-identidad-registros.md`). Cierra A4 y A5 de la auditoría 2026-09-03 y añade la importación nativa que necesita el benchmark (D23).

## Qué cambia

- `revisia/schemas/records.py`: `SearchRecord` normaliza `doi` con `normalize_doi` al construirse; el original no reconocible queda en `extra["doi_raw"]` (D19).
- `revisia/agents/{busqueda,search_backends,ncbi,open_backends,dspace}.py`: sin normalizadores propios; `record_id` con `normalize_doi` y el DOI crudo al modelo (A4). OpenAlex usa el cliente compartido.
- `revisia/agents/dedup.py`: títulos NFKD sin diacríticos; `PLACEHOLDER_TITLES` nunca forman clave (`none:<record_id>`); `DedupReport.unmerged_placeholders` (A5).
- `revisia/ingest/manual_import.py`: ids con `normalize_doi`; parser BibTeX por conteo de llaves (A5); `parse_records_json` e `import_format` para `imported/*.records.json` (D23).
- `revisia/orchestration/search_stage.py`, `revisia/llm/preflight.py`: reconocen `*.records.json`; `01_search/log.json` registra el `format` de cada importación.

## Evidencia reproducida

- A4: RIS `https://doi.org/10.1000/ABC` + OpenAlex `10.1000/abc` → **un** registro, sin `#2` (`tests/test_identidad_registros.py`).
- A5: `title = {The {IMF} and growth}` conserva el título; dos `(sin título)` siguen siendo dos (`tests/test_manual_import.py`, `tests/test_dedup.py`).
- Todos los backends de `BACKENDS` normalizan el DOI al construir (`tests/test_doi_backends.py`).

## Cambios incompatibles

- Los `record_id` de una corrida nueva pueden diferir de los de la 0.8 para el mismo artículo (spec §18, riesgo 6; D12: las corridas 0.8 no se reanudan).

## Verificación

- `uv run pytest -p no:cacheprovider -n auto -m "not cronometrado"` + `-m cronometrado`: <N> recogidos, en verde (base: <recuento de A>); también en 3.11 y 3.12.
- Cobertura ≥ 90 %; `ruff check`, `ruff format --check`, `black --check`, `uv lock --check`: limpios.
- Ningún normalizador de DOI fuera de `revisia/ingest/doi.py` (`grep`).

## Pila

`main` ← PR-0 ← PR-H ← PR-A ← **PR-B** ← PR-C ← … (spec §15). Al mergear, no borrar la rama mientras otra PR la use como base: merge sin borrar → `gh pr edit <n> --base main` en la siguiente → borrar la rama → cerrar y reabrir la siguiente para que corra el CI.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: URL de la PR.

- [ ] **Step 8: Punto de partida de PR-C.** PR-C se desarrolla desde B rebasada (§15): `git -C C:/revisia worktree add C:/revisia-wt/c -b feat/ola2-texto-completo-extraccion feat/ola2-identidad-registros`, `uv sync --extra dev --extra search --extra meta` y la suite en verde.

---

## Self-review (hecha al escribir el plan)

- **Cobertura de §6:** `SearchRecord.doi` con normalización y `doi_raw` (T2); los cinco módulos de backends sin normalizador propio, verificados con `grep` (`busqueda.py:41-44`, `open_backends.py:44-53`, `search_backends.py:49,87,128`, `ncbi.py:112,118,175`, `dspace.py:22,58`) (T3); `manual_import._record_id` (T4); parser BibTeX por llaves (T5); `dedup_key` con NFKD, `PLACEHOLDER_TITLES`, `none:<record_id>` y `unmerged_placeholders` (T6); `parse_records_json` con `format: records_json` en el log (T7); ids estables y `#n` solo en colisiones reales (T2, `test_dedup_ids_repetidos_se_desambiguan` reescrito). Tests nombrados en §6: evidencia A4 (T2), evidencia A5 (T5 y T6), `test_normalize_doi_tabla` (ya en PR-0, `tests/test_doi.py`), `test_todos_los_backends_normalizan_el_doi_al_construir` (T3), `test_dedup_nfkd_fusiona_titulos_con_y_sin_acentos` (T6).
- **Verificación contra el código:** con una copia de `main` @ `c1af7c3` y el cambio de cada tarea aplicado en borrador, la suite dio exactamente los 20 fallos listados en la Tarea 2 (19 por DOI de una cifra + el `#2`), más `test_open_backends.py::test_helpers_year_y_doi` en la Tarea 3 y la línea 358 de `test_preflight.py` en la Tarea 7; los tests nuevos de las Tareas 2–7 pasaron sobre el borrador. Firmas leídas: `SearchRecord` y su validador (`records.py:44-61`), `dedup_key`/`deduplicate_with_report` (`dedup.py:31,46`), `DedupReport`/`SearchLogEntry`/`SearchEntryKind` (`artifacts.py:231,181,92`), `_record_id`/`parse_ris`/`parse_bibtex`/`import_file`/`import_directory`/`IMPORT_SUFFIXES` (`manual_import.py:22,35,73,107,128,19`), `_import`/`multi_database_search` (`search_stage.py:110,155`), `_IMPORT_SUFFIXES` (`preflight.py:52`), `_client` de cada backend (`search_backends.py:28`, `open_backends.py:29`, `dspace.py:35`, `ncbi.py:49`); `pipeline.py:398-400` escribe el informe del dedup sin tocarlo.
- **Consistencia de tipos:** `ImportFormat` (T7) lo usan `SearchLogEntry.format` e `import_format`; `normalize_doi` (PR-0) lo consumen T2, T3, T4, T6; `PLACEHOLDER_TITLES`/`is_placeholder_title`/`dedup_key` (T6) los consume PR-G; `parse_records_json`/`import_format` (T7), PR-F.
- **Proporción:** los bloques de código son tests con los valores del spec y la evidencia de la auditoría; las tareas de código dan firma, campos y la regla del tokenizador BibTeX, sin cuerpos.
- **Revisión independiente (2026-10-19) incorporada:** `test_coverage_gaps.py:180` y `test_fulltext.py:32` en la migración y `test_audit_busqueda.py:1110` (no 1111); conflictos del rebase sobre A (`preflight.py`, `test_preflight.py`, `artifacts.py`) y el test de preflight junto a su vecino; nombres de campo BibTeX `[^\s=,{}"#]+` con error en lo ilegible y en `@tipo(…)`; `records.json` exacto, `utf-8-sig` y aviso por fichero ignorado (`ignored_files`); Expected corregidos en T3 (Crossref y PubMed); lado OpenAlex de A4 por `work_to_record`; `extra` no-`dict` → `ValidationError`; `ncbi.idconv` con `normalize_doi`; un solo test de colisión de ids; grep manual de DOI cortos en la T8.
- **Review Focus:** las cinco entradas tienen test en su tarea (ciclo de import y releer en T2; campos no-DOI en T3; BibTeX real en T5; corpus nativo dañado o con `#2` en T7).
