import pytest
from unittest.mock import patch, AsyncMock
from shopify_agent.tools import get_order_status, translate_shopify_status

def test_translate_shopify_status():
    """Prueba que la traducción de estados sea correcta."""
    assert translate_shopify_status("payment", "PAID") == "Pagado ✅"
    assert translate_shopify_status("fulfillment", "FULFILLED") == "Enviado 🚚"
    assert translate_shopify_status("payment", "UNKNOWN") == "UNKNOWN"

@pytest.mark.asyncio
async def test_get_order_status_success():
    """Prueba la obtención exitosa de un pedido mockeando httpx."""
    mock_data = {
        "data": {
            "orders": {
                "edges": [{
                    "node": {
                        "name": "#1001",
                        "displayFinancialStatus": "PAID",
                        "displayFulfillmentStatus": "FULFILLED",
                        "customer": {"firstName": "Juan", "lastName": "Perez"}
                    }
                }]
            }
        }
    }
    
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_data
        )
        
        # Las herramientas de LangChain se llaman con .ainvoke() y un diccionario
        result = await get_order_status.ainvoke({"order_name": "1001"})
        assert "Pedido #1001" in result
        assert "Juan Perez" in result
        assert "Pagado ✅" in result

@pytest.mark.asyncio
async def test_get_order_status_not_found():
    """Prueba el comportamiento cuando un pedido no existe."""
    mock_data = {"data": {"orders": {"edges": []}}}
    
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_data
        )
        
        result = await get_order_status.ainvoke({"order_name": "9999"})
        assert "No encontré el pedido" in result
