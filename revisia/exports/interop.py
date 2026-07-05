"""Interoperabilidad con herramientas open-source consolidadas del ecosistema.

revisia no reinventa el ecosistema de síntesis de evidencia: además de sus
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
from importlib import resources

from revisia.exports.prisma_flow import PrismaCounts
from revisia.meta_analysis import MetaAnalysisResult
from revisia.schemas.rob import RoBAssessment

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


def _semi_list(pairs: dict[str, int]) -> str:
    """Formato ``"Etiqueta, n; Etiqueta, n"`` que espera el paquete PRISMA2020."""
    return "; ".join(f"{label}, {n}" for label, n in sorted(pairs.items()))


def render_prisma2020_flow_csv(counts: PrismaCounts, *, meta_k: int | None = None) -> str:
    """CSV **nativo** del paquete R ``PRISMA2020`` (y su Shiny app oficial).

    Rellena la columna ``n`` de la plantilla oficial del paquete (vendorizada en
    ``exports/data/prisma2020_template.csv``, MIT, ESHackathon/Haddaway) con los
    conteos reales de la corrida. El archivo resultante se importa tal cual en
    https://estech.shinyapps.io/prisma_flowdiagram/ o con
    ``PRISMA2020::PRISMA_data(read.csv(...))`` en R.

    Args:
        counts: conteos del pipeline.
        meta_k: nº de estudios en el meta-análisis, si lo hubo (caja box17).
    """
    values: dict[str, object] = {
        "database_results": counts.identified,
        "database_specific_results": (
            _semi_list(counts.identified_by_source) if counts.identified_by_source else 0
        ),
        "register_results": 0,
        "register_specific_results": 0,
        "duplicates": counts.duplicates_removed,
        "excluded_automatic": counts.removed_automation,
        "excluded_other": counts.removed_other,
        "records_screened": counts.screened,
        "records_excluded": counts.excluded_ta,
        "dbr_sought_reports": counts.fulltext_assessed,
        "dbr_notretrieved_reports": 0,
        "dbr_assessed": counts.fulltext_assessed,
        "dbr_excluded": (
            _semi_list(counts.ft_exclusion_reasons) if counts.ft_exclusion_reasons else 0
        ),
        "new_studies": counts.included,
        "new_reports": counts.included,
        "total_studies": counts.included,
        "total_reports": counts.included,
        "previous_studies": 0,
        "previous_reports": 0,
        "website_results": 0,
        "organisation_results": 0,
        "citations_results": 0,
        "other_sought_reports": 0,
        "other_notretrieved_reports": 0,
        "other_assessed": 0,
        "other_excluded": 0,
        "total_studies_ma": meta_k if meta_k is not None else 0,
        "total_reports_ma": meta_k if meta_k is not None else 0,
    }
    template = (
        resources.files("revisia.exports")
        .joinpath("data/prisma2020_template.csv")
        .read_text(encoding="utf-8")
    )
    rows = list(csv.reader(io.StringIO(template)))
    header, body = rows[0], rows[1:]
    n_col = header.index("n")
    data_col = header.index("data")
    for row in body:
        if row[data_col] in values:
            row[n_col] = str(values[row[data_col]])
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(body)
    return buf.getvalue()
