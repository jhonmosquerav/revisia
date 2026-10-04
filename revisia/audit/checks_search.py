"""Checks de búsqueda y registro: ``search_window``, ``registration``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext, short_text
from revisia.audit.model import Verdict

_NA_PROTOCOLO = "no aplica: sin protocolo legible en el manifiesto (ver `manifest`)."


def _protocol_section(ctx: AuditContext, key: str) -> dict | None:
    if ctx.manifest_dict is None:
        return None
    protocol = ctx.manifest_dict.get("protocol")
    if not isinstance(protocol, dict):
        return {}
    section = protocol.get(key)
    return section if isinstance(section, dict) else {}


def check_search_window(ctx: AuditContext) -> Verdict:
    """PRISMA-S: ventana temporal de la búsqueda."""
    window = _protocol_section(ctx, "search_window")
    if window is None:
        return "N/A", _NA_PROTOCOLO
    if window.get("executed"):
        # Valor no confiable del manifiesto: acotado, no interpolado crudo (una bomba de alias,
        # `*a` ×9 por nivel, cuelga el `str` del f-string; tercera revisión de la Tarea 4).
        return "PASS", f"Búsqueda ejecutada declarada: {short_text(window.get('executed'))}."
    return "WARN", "search_window.executed vacío: declara cuándo se ejecutó la búsqueda."


def check_registration(ctx: AuditContext) -> Verdict:
    """PRISMA 24a: registro del protocolo."""
    registration = _protocol_section(ctx, "registration")
    if registration is None:
        return "N/A", _NA_PROTOCOLO
    declared = {k: v for k, v in registration.items() if v}
    if declared:
        # Igual que arriba: la clave y el valor vienen del manifiesto, siempre acotados.
        registro = ", ".join(f"{short_text(k)}={short_text(v)}" for k, v in declared.items())
        return "PASS", f"Registro declarado: {registro}."
    return "WARN", "Sin registro (PROSPERO/OSF): preregistra el protocolo antes de publicar."
