"""Equipo de agentes mono-tarea, uno por etapa del pipeline PRISMA.

Agentes deterministas (⚙️): busqueda, dedup. Agentes de razonamiento (🤖):
screening, extraccion, sintesis/reporte, verificador. Cada agente tiene una
responsabilidad única y un contrato I/O tipado (schemas Pydantic).
"""

from __future__ import annotations
