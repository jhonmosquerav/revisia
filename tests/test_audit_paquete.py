"""El auditor es un paquete y conserva su API pública (spec 2026-10-04 §9.1)."""

from __future__ import annotations

from pathlib import Path

import revisia.audit as audit
from revisia.audit import AuditCheck, AuditReport, render_audit_md, run_audit
from revisia.audit.model import AuditCheck as AuditCheckModelo
from revisia.audit.model import AuditReport as AuditReportModelo
from revisia.audit.render import render_audit_md as render_modulo


def test_audit_es_un_paquete_con_la_api_de_siempre() -> None:
    assert Path(audit.__file__).name == "__init__.py"
    assert AuditCheck is AuditCheckModelo
    assert AuditReport is AuditReportModelo
    assert render_audit_md is render_modulo
    assert callable(run_audit)
    assert set(audit.__all__) >= {"AuditCheck", "AuditReport", "render_audit_md", "run_audit"}


def test_render_del_paquete_igual_que_antes(tmp_path) -> None:
    report = AuditReport(
        run_dir=tmp_path,
        checks=[AuditCheck("manifest", "PRISMA 27 / trAIce M2", "PASS", "ok")],
    )
    markdown = render_audit_md(report)
    assert "| manifest | PRISMA 27 / trAIce M2 | ✅ PASS | ok |" in markdown
    assert "APTA para preparar publicación" in markdown
