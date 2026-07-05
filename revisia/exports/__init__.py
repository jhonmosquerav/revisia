"""Exportadores reproducibles: diagrama PRISMA, checklists, bibliografía,
tablas, métodos y forest plot del meta-análisis."""

from __future__ import annotations

from revisia.exports.bibliography import render_bibtex
from revisia.exports.checklist import (
    render_prisma_2020_checklist,
    render_prisma_abstracts_checklist,
    render_prisma_s_checklist,
    render_traice_checklist,
)
from revisia.exports.extraction_table import render_extraction_table
from revisia.exports.forest import (
    render_forest_markdown,
    render_forest_png,
    render_funnel_png,
)
from revisia.exports.interop import (
    render_metafor_csv,
    render_prisma2020_flow_csv,
    render_robvis_csv,
)
from revisia.exports.methods import render_methods
from revisia.exports.prisma_flow import (
    PrismaCounts,
    render_flow_diagram,
    render_flow_markdown,
    render_flow_updated,
)

__all__ = [
    "PrismaCounts",
    "render_bibtex",
    "render_extraction_table",
    "render_flow_diagram",
    "render_flow_markdown",
    "render_flow_updated",
    "render_forest_markdown",
    "render_forest_png",
    "render_funnel_png",
    "render_metafor_csv",
    "render_methods",
    "render_prisma2020_flow_csv",
    "render_prisma_2020_checklist",
    "render_prisma_abstracts_checklist",
    "render_prisma_s_checklist",
    "render_robvis_csv",
    "render_traice_checklist",
]
