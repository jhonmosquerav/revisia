"""Interoperabilidad con herramientas open-source consolidadas del ecosistema.

prisma-loop no reinventa el ecosistema de síntesis de evidencia: además de sus
propios entregables, emite los resultados en formatos que consumen herramientas
probadas de la comunidad (ver ``docs/integraciones.md``):

- **robvis** (visualización de riesgo de sesgo; R/Shiny): CSV con un juicio por
  dominio y estudio, listo para las figuras semáforo/barras.
- **metafor** (meta-análisis en R): CSV con ``yi``/``vi`` por estudio, el input
  estándar de ``rma()`` — útil para replicar/extender el meta-análisis propio.
- **PRISMA2020** (paquete R + Shiny app oficial del flow diagram): CSV con los
  conteos por caja para transcribirlos a la plantilla oficial.

Todo es texto plano determinista: sin dependencias nuevas.
"""

from __future__ import annotations

import csv
import io

from prisma_loop.exports.prisma_flow import PrismaCounts
from prisma_loop.meta_analysis import MetaAnalysisResult
from prisma_loop.schemas.rob import RoBAssessment

# Vocabulario de juicios que espera robvis (tipo RoB2/ROBINS-I).
_ROBVIS_JUDGMENT = {
    "low": "Low",
    "some_concerns": "Some concerns",
    "high": "High",
    "unclear": "No information",
}


def render_robvis_csv(assessments: dict[str, RoBAssessment]) -> str:
    """CSV para robvis: ``Study, D1..Dn, Overall`` con un juicio por celda.

    Los nombres de dominio se toman de las evaluaciones (unión en orden de
    aparición), de modo que sirve para cualquier herramienta RoB configurada.
    """
    domains: list[str] = []
    for assessment in assessments.values():
        for dom in assessment.domains:
            if dom.domain not in domains:
                domains.append(dom.domain)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["Study", *domains, "Overall"])
    for study_id, assessment in assessments.items():
        by_domain = {
            d.domain: _ROBVIS_JUDGMENT.get(d.judgment, "No information") for d in assessment.domains
        }
        overall = _ROBVIS_JUDGMENT.get(assessment.overall or "unclear", "No information")
        writer.writerow([study_id, *(by_domain.get(d, "No information") for d in domains), overall])
    return buf.getvalue()


def render_metafor_csv(result: MetaAnalysisResult) -> str:
    """CSV con efectos por estudio en el formato de entrada de metafor.

    En R: ``dat <- read.csv("effects_metafor.csv"); metafor::rma(yi, vi, data=dat)``.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["study_id", "label", "measure", "yi", "vi"])
    for study in result.studies:
        writer.writerow(
            [
                study.study_id,
                study.label or "",
                result.measure,
                f"{study.yi:.6g}",
                f"{study.vi:.6g}",
            ]
        )
    return buf.getvalue()


def render_prisma2020_flow_csv(counts: PrismaCounts) -> str:
    """CSV con los conteos por caja del diagrama PRISMA 2020.

    Pensado para transcribir a la plantilla oficial (Shiny app del flow diagram
    o paquete R ``PRISMA2020``): una fila por caja, con el rótulo estándar de la
    plantilla "nuevas revisiones, solo bases de datos".
    """
    rows = [
        ("identification", "Records identified from databases", counts.identified),
        ("identification", "Duplicate records removed", counts.duplicates_removed),
        ("screening", "Records screened", counts.screened),
        ("screening", "Records excluded", counts.excluded_ta),
        ("screening", "Reports assessed for eligibility", counts.fulltext_assessed),
        ("screening", "Reports excluded", counts.excluded_ft),
        ("included", "Studies included in review", counts.included),
    ]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["phase", "box", "n"])
    writer.writerows(rows)
    return buf.getvalue()
