from langchain_core.tools import tool

@tool
def get_order_details(order_id: str):
    """Obtiene los detalles de un pedido de Shopify."""
    # Aquí iría la integración real con la API de Shopify
    return {"order_id": order_id, "status": "shipped", "total": 150.0}

@tool
def update_customer_info(customer_id: str, info: dict):
    """Actualiza la información de un cliente en Shopify."""
    return {"status": "success", "customer_id": customer_id}

tools = [get_order_details, update_customer_info]
