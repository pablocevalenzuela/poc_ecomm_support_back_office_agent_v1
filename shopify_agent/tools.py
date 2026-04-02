import os
import httpx
import logging
import json
from langchain_core.tools import tool
from .settings import settings

# Configuración de Logger para las Tools
logger = logging.getLogger("SHOPIFY-TOOLS")

HEADERS = {
    "X-Shopify-Access-Token": settings.shopify_admin_access_token,
    "Content-Type": "application/json",
}

@tool
async def get_shopify_product_details(inventory_item_id: str):
    """
    Obtiene detalles técnicos (SKU, Título, Vendor) de un ítem de inventario.
    """
    gid = f"gid://shopify/InventoryItem/{inventory_item_id}" if not str(inventory_item_id).startswith("gid://") else inventory_item_id
    query = """
    query($id: ID!) {
      inventoryItem(id: $id) {
        sku
        variant {
          title
          product { title vendor }
        }
      }
    }
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={'query': query, 'variables': {'id': gid}}, headers=HEADERS)
            data = response.json()
            if not data or not data.get("data"): return f"No se encontró información para el ID {inventory_item_id}"
            item = data["data"].get("inventoryItem")
            if not item: return f"No se encontró el ítem {inventory_item_id}"
            variant = item.get("variant", {})
            product = variant.get("product", {})
            title = f"{product.get('title')} ({variant.get('title')})" if variant.get("title") != "Default Title" else product.get("title")
            return {"title": title, "sku": item.get("sku"), "vendor": product.get("vendor")}
        except Exception as e:
            return f"Error: {str(e)}"

@tool
async def get_stock_by_sku(product_name_or_sku: str) -> str:
    """
    Consulta el stock disponible de un producto. 
    Acepta tanto el SKU exacto como el nombre del producto (ej: 'nimbus' o 'queso nimbus').
    """
    logger.info(f"Buscando stock para: {product_name_or_sku}")
    query = """
    query getProductVariant($query: String!) {
      productVariants(first: 5, query: $query) {
        edges {
          node {
            displayName
            inventoryQuantity
            sku
          }
        }
      }
    }
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={"query": query, "variables": {"query": product_name_or_sku}}, headers=HEADERS)
            data = response.json()
            edges = data.get("data", {}).get("productVariants", {}).get("edges", []) if data and data.get("data") else []
            
            if not edges and " " in product_name_or_sku:
                last_word = product_name_or_sku.split()[-1]
                logger.info(f"Reintentando stock con: '{last_word}'")
                response = await client.post(settings.shopify_url, json={"query": query, "variables": {"query": last_word}}, headers=HEADERS)
                data = response.json()
                edges = data.get("data", {}).get("productVariants", {}).get("edges", []) if data and data.get("data") else []

            if not edges: return f"No encontré stock para '{product_name_or_sku}'."
            res = [f"- {e['node']['displayName']} (SKU: {e['node']['sku']}): {e['node']['inventoryQuantity']} uds" for e in edges]
            return "Resultados de stock:\n" + "\n".join(res)
        except Exception as e:
            return f"Error al consultar stock: {str(e)}"

@tool
async def get_order_status(order_name: str) -> str:
    """Obtiene el estado de un pedido específico por su nombre (ej: '#1001')."""
    clean_name = order_name.replace("#", "")
    query = """
    query getOrder($query: String!) {
      orders(first: 1, query: $query) {
        edges {
          node {
            name
            displayFinancialStatus
            displayFulfillmentStatus
          }
        }
      }
    }
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={"query": query, "variables": {"query": f"name:{clean_name}"}}, headers=HEADERS)
            data = response.json()
            orders = data.get("data", {}).get("orders", {}).get("edges", []) if data and data.get("data") else []
            if not orders: return f"No encontré el pedido {order_name}."
            order = orders[0]["node"]
            return f"Pedido {order['name']}: Pago {order['displayFinancialStatus']}, Envío {order['displayFulfillmentStatus']}."
        except Exception as e:
            return f"Error: {str(e)}"

@tool
async def search_orders_by_product(product_term: str) -> str:
    """
    Busca pedidos pendientes (no preparados) que contengan un producto específico.
    Acepta SKU o parte del nombre del producto.
    """
    logger.info(f"Iniciando búsqueda profunda de pedidos para: {product_term}")
    
    # Obtenemos los últimos 50 pedidos pendientes (unfulfilled)
    query = """
    {
      orders(first: 50, query: "fulfillment_status:unfulfilled") {
        edges {
          node {
            name
            lineItems(first: 20) {
              edges {
                node {
                  sku
                  title
                }
              }
            }
          }
        }
      }
    }
    """
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={"query": query}, headers=HEADERS)
            data = response.json()
            
            if not data or not data.get("data"):
                return "Error al obtener pedidos de Shopify."

            orders = data["data"].get("orders", {}).get("edges", [])
            if not orders:
                return "No hay pedidos pendientes (unfulfilled) en la tienda actualmente."

            term_lower = product_term.lower()
            matching_orders = []

            # Filtrado manual infalible en Python
            for edge in orders:
                order = edge["node"]
                found_in_order = False
                items_matched = []
                
                for item_edge in order["lineItems"]["edges"]:
                    item = item_edge["node"]
                    sku = (item.get("sku") or "").lower()
                    title = (item.get("title") or "").lower()
                    
                    if term_lower in sku or term_lower in title:
                        found_in_order = True
                        items_matched.append(f"{item['title']} (SKU: {item['sku']})")
                
                if found_in_order:
                    matching_orders.append(f"- Pedido {order['name']}: incluye {', '.join(items_matched)}")

            if not matching_orders:
                # Si no hubo match exacto y hay espacios, intentamos con la última palabra
                if " " in product_term:
                    last_word = product_term.split()[-1]
                    logger.info(f"Reintentando filtrado con palabra clave: '{last_word}'")
                    return await search_orders_by_product(last_word)
                return f"No encontré ningún pedido pendiente que contenga '{product_term}' en sus ítems."

            return f"He encontrado {len(matching_orders)} pedido(s) pendiente(s) con '{product_term}':\n" + "\n".join(matching_orders)

        except Exception as e:
            logger.error(f"Error en search_orders_by_product: {str(e)}")
            return f"Error técnico al buscar pedidos: {str(e)}"

tools = [get_shopify_product_details, get_stock_by_sku, get_order_status, search_orders_by_product]
