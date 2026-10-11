"""Checks de búsqueda y registro: ``search_window``, ``registration``."""

from __future__ import annotations

from revisia.audit.artifacts import NA_PROTOCOLO, AuditContext, short_text, sufijo_mas
from revisia.audit.model import Verdict

_MAX_REGISTROS = 10  # registros que se listan; el resto se cuenta
_LIMITE_REGISTRO = 40  # caracteres de una clave o de un valor de `registration`


def _protocol_section(ctx: AuditContext, key: str) -> dict | None:
    """Sección del protocolo: de la instantánea ``00_protocol/`` si existe (D3).

    Sin instantánea (una corrida anterior a la Ola 1) sale del manifiesto. Con la
    instantánea ilegible el protocolo crudo es el del manifiesto, como en ``thresholds``.
    """
    protocol = ctx.protocol_raw
    if protocol is None:
        return None
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
        return "N/A", NA_PROTOCOLO
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
        return "N/A", NA_PROTOCOLO
    declared = [(k, v) for k, v in registration.items() if v]
    if declared:
        # Igual que arriba: la clave y el valor vienen del manifiesto, siempre acotados, y las
        # entradas también: 2 000 claves daban un detalle de ~50 KB.
        registro = ", ".join(
            f"{short_text(k, limit=_LIMITE_REGISTRO)}={short_text(v, limit=_LIMITE_REGISTRO)}"
            for k, v in declared[:_MAX_REGISTROS]
        )
        return "PASS", (
            f"Registro declarado: {registro}{sufijo_mas(len(declared) - _MAX_REGISTROS)}."
        )
    return "WARN", "Sin registro (PROSPERO/OSF): preregistra el protocolo antes de publicar."
