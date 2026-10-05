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
    """PRISMA-S 9/13: ventana de la búsqueda declarada y fecha de ejecución registrada.

    Sin ``01_search/log.json`` la fecha la tecleó un humano en el protocolo y nadie más la
    registró: el auditor anterior daba PASS por eso (auditoría 2026-09-03, C3/M12), así que
    ahora es siempre WARN. Desde la Ola 1 la registra el motor.
    """
    window = _protocol_section(ctx, "search_window")
    if window is None:
        return "N/A", _NA_PROTOCOLO
    warns: list[str] = []
    missing = [k for k in ("from", "to") if not window.get(k)]
    if missing:
        warns.append(f"ventana sin `{'` ni `'.join(missing)}` (PRISMA-S 9)")
    executed = window.get("executed")
    if executed:
        # Valor no confiable del manifiesto: acotado, no interpolado crudo (una bomba de alias,
        # `*a` ×9 por nivel, cuelga el `str` del f-string; tercera revisión de la Tarea 4).
        warns.append(
            f"fecha tecleada (`executed: {short_text(executed)}`), no registrada por el motor "
            "(sin 01_search/log.json)"
        )
    else:
        warns.append("sin fecha de ejecución: ni `executed` ni 01_search/log.json")
    return "WARN", "; ".join(warns) + "."


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
