"""Memoria persistente de investigador (cerebro de archivos · markdown + JSONL).

Sin vectores ni servidores: cada revisión se sedimenta en archivos markdown y un
log JSONL append-only, de modo que el conocimiento se acumula entre corridas y
cualquier agente lo recupera leyendo archivos. Inspirado en el patrón `cerebro`.
"""

from revisia.memory.brain import ResearchBrain

__all__ = ["ResearchBrain"]
