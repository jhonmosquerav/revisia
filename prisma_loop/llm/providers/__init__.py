"""Implementaciones concretas del contrato LLMProvider.

Cada módulo importa su SDK de forma perezosa (dentro de los métodos), de modo
que el paquete ``prisma_loop`` se importe sin exigir ningún SDK. Solo el
proveedor que la config pide se importa realmente.
"""

from __future__ import annotations
