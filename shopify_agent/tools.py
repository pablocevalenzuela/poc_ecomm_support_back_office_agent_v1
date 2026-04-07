import os
import httpx
import logging
import json
import psycopg
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from .settings import settings

# Configuración de Logger para las Tools
logger = logging.getLogger("SHOPIFY-TOOLS")

HEADERS = {
    "X-Shopify-Access-Token": settings.shopify_admin_access_token,
    "Content-Type": "application/json",
}

def translate_shopify_status(status_type: str, value: str) -> str:
    """Traduce los estados técnicos de Shopify a español humano."""
    translations = {
        "payment": {
            "PAID": "Pagado ✅",
            "PENDING": "Pendiente de pago ⏳",
            "AUTHORIZED": "Autorizado 💳",
            "PARTIALLY_REFUNDED": "Reembolsado parcialmente ⚠️",
            "REFUNDED": "Reembolsado 🔙",
            "VOIDED": "Anulado ❌",
            "PARTIALLY_PAID": "Pagado parcialmente 💸"
        },
        "fulfillment": {
            "UNFULFILLED": "Pendiente de envío 📦",
            "FULFILLED": "Enviado 🚚",
            "PARTIALLY_FULFILLED": "Enviado parcialmente 🚛",
            "RESTOCKED": "Devuelto al inventario 🔄",
            "PENDING_FULFILLMENT": "Preparación pendiente ⏳"
        }
    }
    return translations.get(status_type, {}).get(value, value)

@tool
async def search_product_catalog(query: str) -> str:
    """
    Busca información técnica detallada sobre productos en el catálogo PDF.
    """
    logger.info(f"--- RAG: Iniciando búsqueda para: '{query}' ---")
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small", api_key=settings.ai_api_key, base_url="https://models.inference.ai.azure.com")
    
    try:
        query_embedding = await embeddings_model.aembed_query(query)
        db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://") if "postgresql+asyncpg://" in settings.database_url else settings.database_url
            
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT content FROM product_catalog_embeddings ORDER BY embedding <=> %s::vector LIMIT 5;", (query_embedding,))
                rows = await cur.fetchall()
                if not rows: return "No se encontró información en el catálogo."
                return "Información técnica:\n\n" + "\n---\n".join([row[0] for row in rows])
    except Exception as e:
        return f"Error en catálogo: {str(e)}"

@tool
async def get_shopify_product_details(inventory_item_id: str):
    """Obtiene detalles técnicos de un ítem de inventario."""
    gid = f"gid://shopify/InventoryItem/{inventory_item_id}" if not str(inventory_item_id).startswith("gid://") else inventory_item_id
    query = "query($id: ID!) { inventoryItem(id: $id) { sku variant { title product { title vendor } } } }"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={'query': query, 'variables': {'id': gid}}, headers=HEADERS)
            data = response.json()
            item = data["data"].get("inventoryItem")
            if not item: return "No encontrado."
            return {"title": item["variant"]["product"]["title"], "sku": item["sku"]}
        except Exception as e: return str(e)

@tool
async def get_stock_by_sku(product_name_or_sku: str) -> str:
    """Consulta el stock disponible de un producto."""
    query = "query($query: String!) { productVariants(first: 5, query: $query) { edges { node { displayName inventoryQuantity sku } } } }"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={"query": query, "variables": {"query": product_name_or_sku}}, headers=HEADERS)
            data = response.json()
            edges = data.get("data", {}).get("productVariants", {}).get("edges", [])
            if not edges: return "Sin stock."
            return "\n".join([f"- {e['node']['displayName']}: {e['node']['inventoryQuantity']} uds" for e in edges])
        except Exception as e: return str(e)

@tool
async def get_order_status(order_name: str) -> str:
    """
    Obtiene el estado de un pedido incluyendo cliente y fecha.
    """
    logger.info(f"Buscando pedido: {order_name}")
    clean_name = str(order_name).replace("#", "").strip()
    search_queries = [f"name:#{clean_name}", f"name:{clean_name}", clean_name]
    
    query = """
    query getOrder($query: String!) {
      orders(first: 1, query: $query) {
        edges {
          node {
            name
            createdAt
            displayFinancialStatus
            displayFulfillmentStatus
            customer {
              firstName
              lastName
            }
          }
        }
      }
    }
    """
    
    async with httpx.AsyncClient() as client:
        try:
            for s_query in search_queries:
                response = await client.post(settings.shopify_url, json={"query": query, "variables": {"query": s_query}}, headers=HEADERS)
                data = response.json()
                edges = data.get("data", {}).get("orders", {}).get("edges", [])
                
                if edges:
                    order = edges[0]["node"]
                    customer = order.get("customer")
                    cliente_nombre = f"{customer['firstName']} {customer['lastName']}" if customer else "Cliente no registrado"
                    fecha = order["createdAt"][:10]
                    p_status = translate_shopify_status("payment", order["displayFinancialStatus"])
                    s_status = translate_shopify_status("fulfillment", order["displayFulfillmentStatus"])
                    
                    return (f"DATOS CONFIRMADOS DEL PEDIDO {order['name']}:\n"
                            f"👤 Cliente: {cliente_nombre}\n"
                            f"📅 Fecha: {fecha}\n"
                            f"💰 Pago: {p_status}\n"
                            f"📦 Envío: {s_status}")

            return f"No encontré el pedido '{order_name}'."
        except Exception as e:
            return f"Error: {str(e)}"

@tool
async def search_orders_by_product(product_term: str) -> str:
    """Busca pedidos pendientes por producto."""
    query = "{ orders(first: 50, query: \"fulfillment_status:unfulfilled\") { edges { node { name displayFinancialStatus displayFulfillmentStatus lineItems(first: 20) { edges { node { sku title } } } } } } }"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={"query": query}, headers=HEADERS)
            data = response.json()
            orders = data.get("data", {}).get("orders", {}).get("edges", [])
            matching = []
            for edge in orders:
                order = edge["node"]
                for item_edge in order["lineItems"]["edges"]:
                    if product_term.lower() in item_edge["node"]["title"].lower():
                        matching.append(f"- Pedido {order['name']}")
                        break
            return "\n".join(matching) if matching else "No hay pedidos."
        except Exception as e: return str(e)

tools = [get_shopify_product_details, get_stock_by_sku, get_order_status, search_orders_by_product, search_product_catalog]
