from typing import Any

def human_approval_required(state: Any) -> bool:
    """Determina si una acción requiere aprobación humana (HITL)."""
    # Lógica para detectar acciones sensibles (ej: reembolsos grandes)
    return False
