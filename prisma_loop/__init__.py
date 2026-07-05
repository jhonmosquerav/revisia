"""prisma-loop · motor provider-agnostic para revisiones sistemáticas PRISMA.

El paquete ``prisma_loop`` es "el motor": no contiene nada de una revisión
concreta (eso vive en ``protocols/<slug>/``) ni depende de ningún proveedor
LLM ni de Claude Code. Importar este paquete no requiere ningún SDK pesado;
cada proveedor y el orquestador son extras opcionales que se cargan de forma
perezosa.
"""

from __future__ import annotations

__version__ = "0.2.0"
