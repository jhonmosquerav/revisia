"""Las razones de exclusión no rompen el diagrama, la tabla ni el CSV PRISMA2020.

Revisión final de la Ola 1, grupo C. Las razones de exclusión a texto completo son texto
humano libre (la ``reason`` de ``decision.yml``) o el primer criterio que cita la IA, y los
nombres de base llegan de las APIs: un ``|`` partía la fila de la tabla (también en el HTML
exportado), unas comillas cerraban la etiqueta Mermaid e inyectaban nodos (``no cumple
"población adulta"`` es español normal), un salto de línea partía la fila y el nodo, y un ``;``
o una ``,`` rompían el formato ``Reason, n; Reason, n`` del paquete PRISMA2020. Un test por
carácter.
"""

from __future__ import annotations

import csv
import io
import re

import pytest

from revisia.exports import (
    PrismaCounts,
    render_flow_diagram,
    render_flow_markdown,
    render_prisma2020_flow_csv,
)

# Un `|` sin escapar (el separador de columnas de una tabla Markdown).
_SEPARADOR = re.compile(r"(?<!\\)\|")


def _counts(reason: str, *, fuente: str = "OpenAlex") -> PrismaCounts:
    return PrismaCounts(
        identified=3,
        identified_by_source={fuente: 2, "Crossref": 1},
        screened=3,
        fulltext_sought=3,
        fulltext_assessed=3,
        excluded_ft=2,
        excluded_ft_ai=2,
        ft_exclusion_reasons={reason: 1, "otra razón": 1},
        included=1,
    )


def _filas_de_tabla(markdown: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.strip()]


def _nodo(diagrama: str, nodo: str) -> str:
    (linea,) = [line for line in diagrama.splitlines() if line.strip().startswith(f'{nodo}["')]
    return linea


def test_un_pipe_en_la_razon_no_parte_la_fila_de_la_tabla() -> None:
    tabla = render_flow_markdown(_counts("criterio A | criterio B"))

    for fila in _filas_de_tabla(tabla):
        assert len(_SEPARADOR.findall(fila)) == 3, fila  # | etapa | n |
    assert "criterio A \\| criterio B" in tabla


def test_unas_comillas_en_la_razon_no_cierran_la_etiqueta_mermaid() -> None:
    diagrama = render_flow_diagram(_counts('no cumple "población adulta"'))

    nodo = _nodo(diagrama, "F")
    assert nodo.count('"') == 2  # solo las que abren y cierran la etiqueta
    assert "no cumple #quot;población adulta#quot;" in nodo


def test_unas_comillas_en_el_nombre_de_la_base_no_cierran_la_etiqueta_mermaid() -> None:
    diagrama = render_flow_diagram(_counts("x", fuente='Base "rara"'))

    assert _nodo(diagrama, "A").count('"') == 2


@pytest.mark.parametrize("salto", ["\n", "\r\n", chr(0x2028), chr(0x85)])
def test_un_salto_de_linea_en_la_razon_no_parte_ni_la_tabla_ni_el_nodo(salto: str) -> None:
    counts = _counts(f"primera parte{salto}| segunda: inyectada |")

    tabla = render_flow_markdown(counts)
    diagrama = render_flow_diagram(counts)

    for fila in _filas_de_tabla(tabla):
        assert fila.startswith("|") and len(_SEPARADOR.findall(fila)) == 3, fila
    assert "primera parte \\| segunda: inyectada \\|" in tabla
    assert "primera parte" in _nodo(diagrama, "F")
    assert not any(line.startswith("| segunda") for line in diagrama.splitlines())


def _celda_csv(texto_csv: str, data: str) -> str:
    filas = list(csv.DictReader(io.StringIO(texto_csv)))
    (fila,) = [f for f in filas if f["data"] == data]
    return fila["n"]


@pytest.mark.parametrize("separador", [";", ","])
def test_un_separador_en_la_razon_no_rompe_el_formato_prisma2020(separador: str) -> None:
    counts = _counts(f"no cumple población{separador} edad fuera de rango")

    celda = _celda_csv(render_prisma2020_flow_csv(counts), "dbr_excluded")

    pares = celda.split("; ")
    assert len(pares) == 2, celda  # una razón por par
    for par in pares:
        etiqueta, n = par.rsplit(", ", 1)
        assert n.isdigit()
        assert ";" not in etiqueta and "," not in etiqueta
    assert "no cumple población - edad fuera de rango, 1" in pares


@pytest.mark.parametrize("separador", [";", ",", "\n"])
def test_un_separador_en_el_nombre_de_la_base_no_rompe_el_formato_prisma2020(
    separador: str,
) -> None:
    counts = _counts("x", fuente=f"Base{separador}rara")

    celda = _celda_csv(render_prisma2020_flow_csv(counts), "database_specific_results")

    pares = celda.split("; ")
    assert len(pares) == 2, celda
    for par in pares:
        etiqueta, n = par.rsplit(", ", 1)
        assert n.isdigit()
        assert not set(";,\n") & set(etiqueta), etiqueta
