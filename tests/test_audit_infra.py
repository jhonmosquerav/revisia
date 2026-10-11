"""Infraestructura del auditor: carga que nunca lanza, estado, N/A, fail-closed y render.

Spec 2026-10-04 §9.1-§9.2. Las corridas salen de las fixtures ``corrida`` y
``corrida_en_pausa_ft`` (``tests/conftest.py``).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import pytest
import yaml
from audit_fixtures import (
    auditar,
    auditar_en_subproceso,
    bomba_de_alias,
    edit_yaml,
    fila,
)
from pydantic import AfterValidator, BaseModel, TypeAdapter, ValidationError

import revisia.audit as audit_pkg
import revisia.audit.artifacts as artifacts_mod
from revisia.audit import CHECKS, AuditCheck, AuditReport, CheckSpec, render_audit_md
from revisia.audit.artifacts import (
    NA_PROTOCOLO,
    AuditContext,
    Loaded,
    format_validation,
    load_run,
    read_json,
    read_jsonl,
    read_text,
    read_yaml,
    short_repr,
    short_text,
    sufijo_mas,
    validate,
)
from revisia.audit.render import _md_cell
from revisia.audit.state import derive_state
from revisia.config import STAGES
from revisia.provenance.ledger import DecisionEntry, DecisionLedger
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


# Los loaders no lanzan ni con YAML hostil (spec §9.1; revisión de la Tarea 4).


@pytest.mark.parametrize(
    "contenido",
    ["x: !!timestamp foo\n", "x: !!bool maybe\n"],
    ids=["timestamp-AttributeError", "bool-KeyError"],
)
def test_manifiesto_con_etiqueta_yaml_hostil_es_fail_y_no_error_interno(
    corrida, contenido: str
) -> None:
    """PyYAML lanza ``AttributeError``/``KeyError`` (no ``YAMLError``) ante estas etiquetas."""
    (corrida / "manifest.yml").write_text(contenido, encoding="utf-8")
    cargado = read_yaml(corrida, "manifest.yml")
    assert cargado.present and not cargado.ok
    assert cargado.error.startswith("YAML inválido")
    report = auditar(corrida)
    manifiesto = fila(report, "manifest")
    assert manifiesto.status == "FAIL"
    assert "YAML inválido" in manifiesto.detail
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []
    assert len(report.checks) == len(CHECKS)


def test_read_text_no_lanza_si_el_sistema_de_ficheros_falla(tmp_path, monkeypatch) -> None:
    def _sin_acceso(self, *args, **kwargs):
        raise PermissionError("sin acceso")

    monkeypatch.setattr(Path, "exists", _sin_acceso)
    cargado = read_text(tmp_path, "x.json")
    assert cargado.present and not cargado.ok
    assert "PermissionError" in cargado.error


def test_read_json_y_read_jsonl_no_lanzan_ante_una_excepcion_inesperada(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "x.json").write_text("{}", encoding="utf-8")
    (tmp_path / "x.jsonl").write_text("{}\n", encoding="utf-8")

    def _roto(*args, **kwargs):
        raise TypeError("json roto")

    monkeypatch.setattr(json, "loads", _roto)
    assert "TypeError" in read_json(tmp_path, "x.json").error
    assert "línea 1" in read_jsonl(tmp_path, "x.jsonl").error


def test_validate_no_lanza_si_el_validador_revienta() -> None:
    def _revienta(_valor: int) -> int:
        raise TypeError("validador roto")

    adaptador = TypeAdapter(Annotated[int, AfterValidator(_revienta)])
    resultado = validate(Loaded("x.json", True, 1), adaptador)
    assert resultado.present and not resultado.ok
    assert "TypeError" in resultado.error


# Anidamiento profundo: `CSafeLoader` desborda la pila nativa a ~2 670 niveles (2 669-2 673
# según la sintaxis, medido con Python 3.13; ver `artifacts.py`) y mata el proceso (0xC00000FD
# en Windows) sin que ningún `except` lo atrape. Cada vector corre en un subproceso: si el
# guarda falla, se ve un código de salida distinto de 0 y no se cae la sesión de pytest.
#
# libyaml también trata U+2028, U+2029 y U+0085 como saltos de línea y salta el BOM: unas
# guardas físicas por línea (`^` + `re.MULTILINE`) no los veían y el recorrido de eventos
# nunca corría (tercera revisión de la Tarea 4). La guarda por eventos mide lo que el
# parser entiende, no lo que una regex cree ver.
_SALTOS_UNICODE = {"LS": "\u2028", "NEL": "\u0085", "PS": "\u2029"}


def _sangria_con_salto(salto: str, niveles: int = 4_000) -> str:
    """Un bloque de mapas anidados por sangría, con ``salto`` como salto de línea."""
    lineas = salto.join(" " * i + "a:" for i in range(niveles))
    return lineas + salto + " " * niveles + "z: 1"


_VECTORES_ANIDADOS = [
    pytest.param(lambda: "x: " + "[" * 10_000 + "\n", id="corchetes"),
    # Los tres siguientes esquivaban la guarda de comillas/comentarios por línea (segunda
    # revisión de la Tarea 4): una comilla suelta o un `#` dentro de una cadena multilínea
    # ocultaban los `[` que sí anidan. La guarda por eventos del parser no los puede ocultar.
    pytest.param(lambda: 'x: [a"b, ' + "[" * 10_000 + ' c"d\n', id="comilla-doble-suelta"),
    pytest.param(lambda: "x: [a'b, " + "[" * 10_000 + " c'd\n", id="comilla-simple-suelta"),
    pytest.param(
        lambda: 'x: ["a\n # b", ' + "[" * 10_000 + "\n", id="cadena-multilinea-con-almohadilla"
    ),
    pytest.param(lambda: "- " * 10_000 + "x\n", id="indicadores-de-bloque-encadenados"),
    pytest.param(
        lambda: "".join(" " * i + "a:\n" for i in range(3_000)) + " " * 3_000 + "z: 1\n",
        id="sangria",
    ),
    # Tercera revisión: saltos de línea que solo libyaml reconoce, y el BOM.
    *[
        pytest.param(lambda s=salto: _sangria_con_salto(s), id=f"sangria-con-{nombre}")
        for nombre, salto in _SALTOS_UNICODE.items()
    ],
    # Con LS y con el BOM basta la versión de 10 000 (la más fuerte); NEL y PS, la de 4 000.
    pytest.param(lambda: "x:\u2028" + "- " * 10_000, id="indicadores-con-LS"),
    pytest.param(lambda: "x:\u0085" + "- " * 4_000 + "x", id="indicadores-con-NEL"),
    pytest.param(lambda: "x:\u2029" + "- " * 4_000 + "x", id="indicadores-con-PS"),
    pytest.param(lambda: "\ufeff" + "- " * 10_000, id="bom-con-indicadores"),
]


@pytest.mark.parametrize("texto", _VECTORES_ANIDADOS)
def test_manifiesto_muy_anidado_no_tumba_el_proceso_del_auditor(corrida, texto) -> None:
    (corrida / "manifest.yml").write_text(texto(), encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=300)
    assert filas["manifest"][0] == "FAIL"
    assert "anidada" in filas["manifest"][1]
    assert [i for i, (_, detalle) in filas.items() if "error interno" in detalle] == []
    assert len(filas) == len(CHECKS)


def test_guarda_de_anidamiento_respeta_sus_limites(tmp_path) -> None:
    def cargar(texto: str, **kwargs) -> Loaded:
        (tmp_path / "x.yml").write_text(texto, encoding="utf-8")
        return read_yaml(tmp_path, "x.yml", **kwargs)

    # Un único límite, medido por eventos del parser: 500 niveles de colección (también el
    # mapa raíz), sea cual sea la sintaxis (flujo, bloque con `- `, bloque por sangría).
    def anidado(niveles: int) -> str:
        return "x: " + "[" * niveles + "]" * niveles + "\n"

    def sangrado(lineas: int) -> str:
        """`lineas` líneas `a:` más la hoja `z: 1`: lineas + 1 mapas anidados."""
        return "".join(" " * i + "a:\n" for i in range(lineas)) + " " * lineas + "z: 1\n"

    assert cargar(anidado(499)).ok  # raíz + 499 = profundidad 500: pasa
    assert "anidada" in cargar(anidado(500)).error  # profundidad 501: se rechaza sin cargar
    assert "anidada" in cargar("x: " + "{a: " * 501 + "1" + "}" * 501 + "\n").error
    # Hasta 500 indicadores `- ` encadenados en una línea pasan; 501 no.
    assert cargar("- " * 500 + "x\n", root=list).ok
    assert "anidada" in cargar("- " * 501 + "x\n", root=list).error
    assert cargar(sangrado(499)).ok
    assert "anidada" in cargar(sangrado(500)).error
    # Los corchetes entre comillas o en un comentario no cuentan (no abren colecciones).
    assert cargar('x: "' + "[" * 5_000 + '"\n').ok
    assert cargar("x: '" + "{" * 5_000 + "'\n").ok
    assert cargar("x: 1  # " + "[" * 5_000 + "\n").ok
    # Una sangría larga sin anidamiento (un bloque literal) no es un problema de pila.
    assert cargar("x: |\n" + " " * 600 + "t\n").ok
    # Un manifiesto normal (listas y mapas de profundidad < 20) no se toca.
    assert cargar("a:\n  - b: [1, 2, {c: d}]\n  - e: 'f'\n").value == {
        "a": [{"b": [1, 2, {"c": "d"}]}, {"e": "f"}]
    }
    # Los alias normales siguen permitidos: solo se rechazan las claves de fusión (`<<`).
    assert cargar("a: &x [1, 2]\nb: *x\n").value == {"a": [1, 2], "b": [1, 2]}


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("a: &a {x: 1}\nb:\n  <<: *a\n  y: 2\n", id="bloque"),
        pytest.param("a: &a {x: 1}\nb: {<<: [*a], y: 2}\n", id="flujo-con-lista"),
        pytest.param("a: &a {x: 1}\nb:\n  ? <<\n  : *a\n", id="clave-compleja"),
        # Con la etiqueta explícita `!!merge` cualquier escalar actúa como clave de fusión,
        # también uno entrecomillado o con otro valor: no basta mirar el texto `<<`.
        pytest.param('a: &a {x: 1}\nb: {!!merge "<<": *a}\n', id="etiqueta-entrecomillada"),
        pytest.param("a: &a {x: 1}\nb: {!!merge zzz: *a}\n", id="etiqueta-otro-valor"),
    ],
)
def test_clave_de_fusion_se_rechaza_sin_cargar(tmp_path, texto: str) -> None:
    (tmp_path / "x.yml").write_text(texto, encoding="utf-8")
    cargado = read_yaml(tmp_path, "x.yml")
    assert cargado.present and not cargado.ok
    assert "fusión" in cargado.error
    assert "anidada" not in cargado.error


def test_clave_entrecomillada_no_es_de_fusion(tmp_path) -> None:
    """``"<<"`` y ``'<<'`` entrecomillados son claves de texto corrientes: se cargan."""
    (tmp_path / "x.yml").write_text("a: {\"<<\": 1, '<<<': 2, x: 3}\n", encoding="utf-8")
    cargado = read_yaml(tmp_path, "x.yml")
    assert cargado.ok, cargado.error
    assert cargado.value == {"a": {"<<": 1, "<<<": 2, "x": 3}}


def test_la_guarda_no_depende_de_libyaml(tmp_path, monkeypatch) -> None:
    """Con el loader de Python puro (sin `CSafeLoader`) la guarda ve lo mismo."""
    monkeypatch.setattr(artifacts_mod, "_YAML_LOADER", yaml.SafeLoader)
    for salto in _SALTOS_UNICODE.values():
        (tmp_path / "x.yml").write_text(_sangria_con_salto(salto), encoding="utf-8")
        assert "anidada" in read_yaml(tmp_path, "x.yml").error
    (tmp_path / "x.yml").write_text("\ufeff" + "- " * 4_000 + "x\n", encoding="utf-8")
    assert "anidada" in read_yaml(tmp_path, "x.yml", root=list).error
    (tmp_path / "x.yml").write_text("a: &a {x: 1}\nb: {<<: *a}\n", encoding="utf-8")
    assert "fusión" in read_yaml(tmp_path, "x.yml").error
    # Los costes cuadráticos de carga también: el resolver del `SafeLoader` de Python puro es el
    # mismo y sus eventos traen `style=None` en los escalares planos.
    (tmp_path / "x.yml").write_text("x: " + "1:" * 600 + "1\n", encoding="utf-8")
    assert "escalar numérico" in read_yaml(tmp_path, "x.yml").error
    (tmp_path / "x.yml").write_text("".join(f"{i}: 1\n" for i in range(10_001)), encoding="utf-8")
    assert "claves enteras" in read_yaml(tmp_path, "x.yml").error
    # Un carácter de control lanza `ReaderError` al construir el loader de Python puro: no
    # es un problema de anidamiento, la carga lo informa como YAML inválido.
    (tmp_path / "x.yml").write_text("x: \x01\n", encoding="utf-8")
    assert read_yaml(tmp_path, "x.yml").error.startswith("YAML inválido")


def test_yaml_con_sintaxis_erronea_es_invalido_y_no_anidado(corrida) -> None:
    """Un error de sintaxis tras 600 `[]` es «YAML inválido», no un problema de anidamiento."""
    texto = "".join(f"k{i}: []\n" for i in range(600)) + "x: [a, b\ny: c]]\n"
    (corrida / "manifest.yml").write_text(texto, encoding="utf-8")
    manifiesto = fila(auditar(corrida), "manifest")
    assert manifiesto.status == "FAIL"
    assert "YAML inválido" in manifiesto.detail
    assert "anidada" not in manifiesto.detail


def test_manifiesto_valido_con_miles_de_corchetes_se_carga_sin_rechazo(tmp_path) -> None:
    """La guarda por eventos mide profundidad, no cantidad: 4 000 `{}`/`[]` planos no anidan."""
    llamadas = "".join(
        f"- stage: screening_ta\n  seed: {i}\n  usage: {{}}\n  tags: []\n" for i in range(2_000)
    )
    texto = f"slug: demo\nmodels_used: [m/x]\nllm_calls:\n{llamadas}"
    assert texto.count("[") + texto.count("{") > 500
    (tmp_path / "manifest.yml").write_text(texto, encoding="utf-8")
    cargado = read_yaml(tmp_path, "manifest.yml")
    assert cargado.ok, cargado.error
    assert len(cargado.value["llm_calls"]) == 2_000
    assert cargado.value["llm_calls"][1_999] == {
        "stage": "screening_ta",
        "seed": 1_999,
        "usage": {},
        "tags": [],
    }


@pytest.mark.parametrize(
    ("cola", "fila_afectada", "estado"),
    [
        pytest.param("provenance: *a9\n", "provenance", "FAIL", id="provenance"),
        pytest.param(
            "models_used: [*a9]\nllm_calls:\n- {stage: screening_ta, prompt_sha256: ab}\n",
            "manifest",
            "PASS",
            id="models_used",
        ),
        # Tercera revisión: `checks_search` interpolaba el valor crudo en dos f-strings. Con la
        # Tarea 9 una fecha tecleada nunca es PASS (C3): la fila es siempre WARN, y lo que
        # esta fila vigila es que el auditor termina, la fila existe y el detalle va acotado.
        pytest.param(
            "protocol:\n  search_window:\n    executed: *a9\n",
            "search_window",
            "WARN",
            id="search_window-executed",
        ),
        pytest.param(
            "protocol:\n  registration:\n    prospero: *a9\n",
            "registration",
            "PASS",
            id="registration-plana",
        ),
        pytest.param(
            "protocol:\n  registration: {osf: {id: *a9}}\n",
            "registration",
            "PASS",
            id="registration-anidada",
        ),
        # Tarea 5: `schemas` valida `models_used` y informa sin expandir la bomba.
        pytest.param("models_used: [*a9]\n", "schemas", "FAIL", id="models_used-schemas"),
    ],
)
def test_bomba_de_alias_no_cuelga_el_auditor_ni_llena_el_detalle(
    corrida, cola: str, fila_afectada: str, estado: str
) -> None:
    (corrida / "manifest.yml").write_text(bomba_de_alias() + cola, encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=60)
    assert filas[fila_afectada][0] == estado
    assert len(filas[fila_afectada][1]) < 500  # un `repr` acotado, no la bomba expandida
    assert [i for i, (_, detalle) in filas.items() if "error interno" in detalle] == []
    assert len(filas) == len(CHECKS)


# Una bomba de claves de fusión (`<<: [*a, … ×9]`, un nivel tras otro) cuelga la propia
# carga: `flatten_mapping` multiplica los pares ×9 por nivel (el nivel 8 ya tarda segundos
# y el 10, minutos y decenas de GB). El motor nunca escribe `<<`, así que se rechaza sin
# cargar (tercera revisión de la Tarea 4).
def _bomba_de_fusion(niveles: int) -> str:
    base = "a0: &a0 {x: 1}\n"
    return base + "".join(
        f"a{i}: &a{i} {{<<: [{', '.join([f'*a{i - 1}'] * 9)}]}}\n" for i in range(1, niveles)
    )


def test_bomba_de_claves_de_fusion_no_cuelga_la_carga(corrida) -> None:
    # Sin la guarda, la carga del nivel 8 tarda ~6 s y termina: ni el `timeout` ni una cota de
    # tiempo la distinguirían de forma fiable de una carga correcta (con 10 s pasaba igual). Lo
    # que discrimina es el veredicto de la fila `manifest` («fusión»: rechazada sin cargar); el
    # `timeout` de 60 s solo evita que una regresión con una bomba mayor cuelgue la sesión.
    (corrida / "manifest.yml").write_text(_bomba_de_fusion(8), encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=60)
    assert filas["manifest"][0] == "FAIL"
    assert "fusión" in filas["manifest"][1]
    assert [i for i, (_, detalle) in filas.items() if "error interno" in detalle] == []
    assert len(filas) == len(CHECKS)


# Dos costes cuadráticos que la guarda por eventos tampoco veía, porque no son de recursión sino
# de carga (revisión de la fase 1 de PR-E): un entero sexagesimal plano (`x: 1:1:1:…`) se
# construye con aritmética de enteros grandes, cuadrática en su longitud (400 KB ≈ 15 s), y N
# claves enteras que colisionan en el hash (`i·(2⁶¹−1)` da hash 0 para todas) llenan el
# diccionario en O(N²) (40 000 claves ≈ 16 s). El motor no escribe ninguno de los dos.
#
# Tercer vector (segunda revisión de la fase 1): las mismas claves colisionantes, pero escritas
# como ALIAS de enteros anclados en posición de valor (`- &a1 <i·(2⁶¹−1)>` … `*a1 : 1`). Un alias
# no es un escalar plano, así que el contador de claves enteras no lo veía (40 000 ≈ 15 s, 80 000
# ≈ 105 s). El motor tampoco escribe nunca claves-alias (`safe_dump` no ancla escalares).
def _claves_alias(n: int) -> str:
    """``n`` enteros colisionantes anclados en una lista y ``n`` alias suyos como claves."""
    anclas = "".join(f"  - &a{i} {i * (2**61 - 1)}\n" for i in range(n))
    return "anclas:\n" + anclas + "mapa:\n" + "".join(f"  *a{i} : 1\n" for i in range(n))


_VECTORES_CUADRATICOS = [
    pytest.param(
        lambda: "x: " + "1:" * 200_000 + "1\n", "escalar numérico", id="sexagesimal-400KB"
    ),
    pytest.param(
        lambda: "".join(f"{i * (2**61 - 1)}: 1\n" for i in range(40_000)),
        "claves enteras",
        id="40000-claves-enteras-colisionando",
    ),
    pytest.param(
        lambda: _claves_alias(40_000), "alias como clave", id="40000-claves-alias-colisionando"
    ),
]


@pytest.mark.parametrize(("texto", "motivo"), _VECTORES_CUADRATICOS)
def test_yaml_con_costes_cuadraticos_no_cuelga_la_carga(corrida, texto, motivo: str) -> None:
    (corrida / "manifest.yml").write_text(texto(), encoding="utf-8")
    filas = auditar_en_subproceso(corrida, timeout=10)  # el `timeout` es la cota de tiempo
    assert filas["manifest"][0] == "FAIL"
    assert motivo in filas["manifest"][1]
    assert len(filas["manifest"][1]) < 500  # un motivo, no el valor hostil
    assert [i for i, (_, detalle) in filas.items() if "error interno" in detalle] == []
    assert len(filas) == len(CHECKS)


def test_guarda_de_costes_cuadraticos_respeta_sus_limites(tmp_path) -> None:
    def cargar(texto: str) -> Loaded:
        (tmp_path / "x.yml").write_text(texto, encoding="utf-8")
        return read_yaml(tmp_path, "x.yml")

    def motivo(texto: str) -> str:
        return cargar(texto).error or ""

    def claves(n: int, sangria: str = "") -> str:
        return "".join(f"{sangria}{i}: 1\n" for i in range(n))

    # Escalares numéricos planos: hasta 1 000 caracteres pasan; con más se rechazan, sea cual sea
    # su forma (decimal, sexagesimal, flotante) y también con la etiqueta explícita.
    assert cargar("x: " + "9" * 1_000 + "\n").ok
    assert "escalar numérico" in motivo("x: " + "9" * 1_001 + "\n")
    assert "escalar numérico" in motivo("x: " + "1:" * 600 + "1\n")
    assert "escalar numérico" in motivo("x: " + "9" * 1_001 + ".5\n")
    assert "escalar numérico" in motivo('x: !!int "' + "9" * 1_001 + '"\n')
    assert "escalar numérico" in motivo('x: !!float "' + "9" * 1_001 + '.5"\n')
    # Lo que no se resolvería a int ni a float no se toca, por largo que sea.
    assert cargar("x: " + "9" * 1_001 + "a\n").ok  # texto plano
    assert cargar('x: "' + "9" * 5_000 + '"\n').ok  # entrecomillado: una cadena
    assert cargar("x: !!str " + "9" * 5_000 + "\n").ok
    assert cargar("x: |\n  " + "9" * 5_000 + "\n").ok  # bloque literal
    # Claves enteras planas: hasta 10 000 pasan; con una más se rechaza el documento.
    assert cargar(claves(10_000)).ok
    assert "claves enteras" in motivo(claves(10_001))
    # El límite es del documento, no de cada mapa: repartirlas en varios no lo esquiva.
    dos_mapas = "a:\n" + claves(6_000, "  ") + "b:\n" + claves(6_000, "  ")
    assert "claves enteras" in motivo(dos_mapas)
    # Solo cuentan las claves: los valores enteros, las claves de texto y las entrecomilladas no.
    assert cargar("".join(f"k{i}: {i}\n" for i in range(20_000))).ok
    assert cargar("".join(f'"{i}": 1\n' for i in range(20_000))).ok


_ALIAS_COMO_CLAVE = [
    pytest.param("x: &k 1\n*k : 2\n", id="mapa-raiz"),
    pytest.param("x: &k 1\n*k: 2\n", id="sin-espacio-antes-de-los-dos-puntos"),
    pytest.param("x: &k a\ny: {*k : 2}\n", id="mapa-de-flujo"),
    pytest.param("x: &k a\ny: [*k : 2]\n", id="par-suelto-en-secuencia-de-flujo"),
    pytest.param("x: &k a\ny:\n  - z: 1\n    *k : 2\n", id="mapa-anidado-en-secuencia"),
    pytest.param("x: &k a\nm:\n  p: {q: 1}\n  *k : 2\n", id="tras-un-valor-colección"),
]
_ALIAS_COMO_VALOR = [
    pytest.param("a: &x 1\nb: *x\n", {"a": 1, "b": 1}, id="entero"),
    pytest.param("a: &x [1, 2]\nb: [*x, *x]\nc: {k: *x}\n", None, id="en-secuencia-y-mapa"),
    pytest.param("x: &k 1\nm:\n  p: {q: 1}\n  r: *k\n", None, id="tras-un-valor-colección"),
    pytest.param("- &k 1\n- *k\n- *k\n", None, id="en-secuencia-raiz"),
]


@pytest.mark.parametrize("texto", _ALIAS_COMO_CLAVE)
def test_guarda_rechaza_un_alias_en_posicion_de_clave(tmp_path, texto: str) -> None:
    # Un alias no es un escalar plano: el contador de claves enteras no lo veía, y N alias de
    # enteros anclados que colisionan en el hash cuestan O(N²) igual que N claves planas. El
    # motor nunca escribe un alias como clave (`safe_dump` no ancla escalares): se rechaza
    # cualquiera, tenga el tamaño que tenga, con un motivo acotado.
    (tmp_path / "x.yml").write_text(texto, encoding="utf-8")
    cargado = read_yaml(tmp_path, "x.yml", root=(dict, list))
    assert not cargado.ok
    assert cargado.error == (
        "alias como clave de mapping: no admitido en artefactos del motor; no se carga porque "
        "los alias de enteros que colisionan en el hash cuestan tiempo cuadrático"
    )


@pytest.mark.parametrize(("texto", "esperado"), _ALIAS_COMO_VALOR)
def test_guarda_admite_los_alias_en_posicion_de_valor(tmp_path, texto: str, esperado) -> None:
    # Los alias normales comparten nodos y el motor puede escribirlos en valores: siguen
    # permitidos (solo el alias en posición de CLAVE se rechaza).
    (tmp_path / "x.yml").write_text(texto, encoding="utf-8")
    cargado = read_yaml(tmp_path, "x.yml", root=(dict, list))
    assert cargado.ok, cargado.error
    if esperado is not None:
        assert cargado.value == esperado


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("? [a, b]\n: 1\n", id="clave-lista"),
        pytest.param("? {a: 1}\n: 1\n", id="clave-mapa"),
    ],
)
def test_clave_compleja_es_un_yaml_invalido_limpio(tmp_path, corrida, texto: str) -> None:
    # El motor tampoco escribe claves complejas, y el `SafeLoader` ya las rechaza al construir
    # (una lista o un mapa no son hashables): el veredicto es un «YAML inválido» limpio de la
    # fila `manifest`, no un «error interno» de otro check.
    (tmp_path / "x.yml").write_text(texto, encoding="utf-8")
    assert read_yaml(tmp_path, "x.yml").error == "YAML inválido (ConstructorError)"
    (corrida / "manifest.yml").write_text(texto, encoding="utf-8")
    report = auditar(corrida)
    manifest = fila(report, "manifest")
    assert manifest.status == "FAIL"
    assert "YAML inválido" in manifest.detail
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []
    assert len(report.checks) == len(CHECKS)


def test_manifiesto_con_un_entero_de_1500_cifras_falla_sin_error_interno(corrida) -> None:
    # Un entero llano de más de 1 000 caracteres es el vector cuadrático de los sexagesimales
    # con otra forma: la guarda lo rechaza al leer el manifiesto, y el resto de los checks lo
    # ven como un manifiesto ilegible (N/A), no como un fallo propio.
    edit_yaml(corrida / "manifest.yml", lambda m: m["counts"].update(identified=10**1499))
    report = auditar(corrida)
    manifest = fila(report, "manifest")
    assert manifest.status == "FAIL"
    assert "escalar numérico" in manifest.detail
    assert len(manifest.detail) < 500  # un motivo, no el entero hostil
    assert [c.check_id for c in report.checks if "error interno" in c.detail] == []
    assert len(report.checks) == len(CHECKS)


def test_na_protocolo_no_apunta_a_una_fila_concreta() -> None:
    # La causa de un protocolo ilegible puede estar en `manifest`, en `schemas` o en cualquier
    # otra fila que lo lea: el N/A manda a mirar las filas en FAIL, no a dos filas fijas.
    assert NA_PROTOCOLO == (
        "no aplica: sin protocolo legible en el manifiesto (ver las filas en FAIL)."
    )


def test_sufijo_mas_va_en_singular_para_uno() -> None:
    assert sufijo_mas(0) == ""
    assert sufijo_mas(-3, "error") == ""
    assert sufijo_mas(1) == " (+1 más)"
    assert sufijo_mas(5) == " (+5 más)"
    assert sufijo_mas(1, "error") == " (+1 error más)"
    assert sufijo_mas(2, "error") == " (+2 errores más)"
    assert sufijo_mas(1, "artefacto") == " (+1 artefacto más)"
    assert sufijo_mas(7, "artefacto") == " (+7 artefactos más)"


def test_format_validation_dice_un_error_mas_en_singular() -> None:
    class Modelo(BaseModel):
        a: int
        b: int
        c: int
        d: int
        e: int

    def detalle(cuerpo: dict) -> str:
        with pytest.raises(ValidationError) as info:
            Modelo.model_validate(cuerpo)
        return format_validation(info.value)

    assert detalle({"a": 1}).endswith(" (+1 error más)")  # 4 errores, se listan 3
    assert detalle({}).endswith(" (+2 errores más)")  # 5 errores, se listan 3
    assert "más)" not in detalle({"a": 1, "b": 1})  # 3 errores: caben todos


def test_short_repr_acota_coste_y_longitud() -> None:
    assert short_repr("pipeline") == "'pipeline'"
    assert short_repr([1, 2]) == "[1, 2]"
    assert len(short_repr(list(range(1_000)))) <= 120
    assert len(short_repr("x" * 10_000)) <= 120
    ciclica: list = []
    ciclica.append(ciclica)  # YAML permite referencias circulares con `&a [*a]`
    assert len(short_repr(ciclica)) <= 120


def test_short_text_deja_las_cadenas_tal_cual_y_acota_el_resto() -> None:
    assert short_text("2026-10-04") == "2026-10-04"  # sin comillas: el detalle se lee como antes
    assert short_text("x" * 10_000) == "x" * 119 + "…"
    assert short_text([1, 2]) == "[1, 2]"
    assert len(short_text([[[[1] * 9] * 9] * 9] * 9)) <= 120


def test_short_text_muestra_las_fechas_en_iso() -> None:
    # PyYAML carga `executed: 2026-10-04` (sin comillas) como `datetime.date`, y su `repr`
    # (`datetime.date(2026, 10, 4)`) no es una fecha que un revisor reconozca en el informe.
    assert short_text(date(2026, 10, 4)) == "2026-10-04"
    assert short_text(datetime(2026, 10, 4, 12, 30, tzinfo=UTC)) == "2026-10-04T12:30:00+00:00"


@pytest.mark.parametrize(
    "valor",
    [
        pytest.param("\ud800", id="solo"),
        pytest.param("2026-10-04T12:00:00+00:00\ud800", id="al-final"),
        pytest.param("\ud800" * 10_000, id="enorme"),
        pytest.param(["\ud800"], id="en-lista"),
        pytest.param({"\udfff": "\ud800"}, id="en-mapa"),
    ],
)
def test_short_text_y_short_repr_siempre_son_codificables_en_utf8(valor: object) -> None:
    # Un sustituto suelto (JSON `"\ud800"`) no codifica a UTF-8: `audit.md` no se podría escribir.
    for texto in (short_text(valor), short_repr(valor), short_text(valor, limit=50)):
        texto.encode("utf-8")
    assert len(short_text(valor, limit=50)) <= 50
    assert len(short_text(valor)) <= 120


def test_short_text_escapa_el_sustituto_suelto_en_vez_de_perderlo() -> None:
    assert short_text("a\ud800b") == "a\\ud800b"


def test_ledger_con_separadores_unicode_en_el_texto_conserva_la_entrada(corrida) -> None:
    """``str.splitlines`` también corta en U+2028/U+2029/U+0085; el ledger los escribe tal cual."""
    ruta = corrida / "decisions_ledger.jsonl"
    antes = len(AuditContext(load_run(corrida)).ledger.entries)
    motivo = "uno\u2028dos\u2029tres\u0085cuatro"
    DecisionLedger(ruta).append(
        DecisionEntry(
            stage="screening_ta",
            actor="human:ana",
            autonomy="A1",
            action="label",
            target="10.1000/llm-1",
            detail={"reason": motivo},
        )
    )
    assert "\u2028" in ruta.read_text(encoding="utf-8")  # el separador va crudo en el fichero
    vista = AuditContext(load_run(corrida)).ledger
    assert vista.errors == ()
    assert len(vista.entries) == antes + 1
    assert vista.entries[-1][1].detail["reason"] == motivo


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


def test_el_mensaje_de_la_excepcion_de_un_check_va_acotado(corrida, monkeypatch) -> None:
    # El mensaje de una excepción puede traer un valor del artefacto hostil (un id de 50 000
    # caracteres en un `KeyError`): no entra entero en el detalle.
    def _roto(_ctx):
        raise ValueError("x" * 50_000)

    roto = tuple(
        CheckSpec(s.check_id, s.item_ref, s.stage, _roto) if s.check_id == "gold" else s
        for s in CHECKS
    )
    monkeypatch.setattr(audit_pkg, "CHECKS", roto)
    gold = fila(auditar(corrida), "gold")
    assert gold.status == "FAIL"
    assert "error interno del auditor (ValueError)" in gold.detail
    assert "no se considera verificada" in gold.detail
    assert len(gold.detail) < 1_000


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


def test_pausa_en_screening_ft_deja_na_las_etapas_posteriores(corrida_en_pausa_ft) -> None:
    report = auditar(corrida_en_pausa_ft)
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


def test_cli_audit_muestra_na(corrida_en_pausa_ft, capsys) -> None:
    from revisia.cli import main

    assert main(["audit", str(corrida_en_pausa_ft)]) == 1
    out = capsys.readouterr().out
    assert "➖ N/A  exclusions" in out
    assert "Traceback" not in out
