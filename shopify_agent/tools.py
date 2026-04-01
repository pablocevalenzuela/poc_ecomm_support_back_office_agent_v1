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
    Consulta la API GraphQL de Shopify para obtener el título, SKU y Vendor
    a partir de un inventory_item_id.
    """
    if not str(inventory_item_id).startswith("gid://"):
        gid = f"gid://shopify/InventoryItem/{inventory_item_id}"
    else:
        gid = inventory_item_id

    logger.info(f"Consultando detalles para GID: {gid}")

    query = """
    query($id: ID!) {
      inventoryItem(id: $id) {
        sku
        variant {
          title
          product {
            title
            vendor
          }
        }
      }
    }
    """

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={'query': query, 'variables': {'id': gid}}, headers=HEADERS)
            data = response.json()

            if "errors" in data:
                logger.error(f"Errores GraphQL: {data['errors']}")
                return f"Error en Shopify: {data['errors'][0]['message']}"

            item = data.get("data", {}).get("inventoryItem")
            if not item:
                return f"No se encontró información para el ID {inventory_item_id}"

            variant = item.get("variant", {})
            product = variant.get("product", {})
            full_title = f"{product.get('title')} ({variant.get('title')})" if variant.get(
                "title") != "Default Title" else product.get("title")

            return {
                "title": full_title,
                "sku": item.get("sku"),
                "vendor": product.get("vendor")
            }
        except Exception as e:
            return f"Error de conexión: {str(e)}"


@tool
async def get_stock_by_sku(sku: str) -> str:
    """Consulta el stock disponible de un producto en Shopify usando su SKU."""
    logger.info(f"Buscando stock para SKU: {sku}")
    query = """
    query getProductVariant($sku: String!) {
      productVariants(first: 1, query: $sku) {
        edges {
          node {
            displayName
            inventoryQuantity
          }
        }
      }
    }
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={"query": query, "variables": {"sku": sku}}, headers=HEADERS)
            data = response.json()

            edges = data.get("data", {}).get(
                "productVariants", {}).get("edges", [])
            if not edges:
                return f"No se encontró el producto con SKU: {sku}"

            variant = edges[0]["node"]
            return f"Producto: {variant['displayName']}, Stock: {variant['inventoryQuantity']}"
        except Exception as e:
            return f"Error al consultar stock: {str(e)}"


@tool
async def get_order_status(order_name: str) -> str:
    """Consulta el estado de un pedido específico en Shopify usando su nombre (ej: #1001)."""
    clean_name = order_name.replace("#", "")
    logger.info(f"Consultando pedido específico: {clean_name}")
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

            orders = data.get("data", {}).get("orders", {}).get("edges", [])
            if not orders:
                return f"No se encontró ningún pedido con el nombre {order_name}."

            order = orders[0]["node"]
            return f"Pedido {order['name']}: Pago {order['displayFinancialStatus']}, Envío {order['displayFulfillmentStatus']}."
        except Exception as e:
            return f"Error al consultar pedido: {str(e)}"


@tool
async def search_orders_by_product(sku: str) -> str:
    """
       Busca pedidos pendientes (unfulfilled) que contengan un producto específico por su SKU.

       Args:
          sku: Es el identificador de un producto o artículo en la tienda online Shopify.
    """

    logger.info(f"Buscando pedidos pendientes con SKU: {sku}")

    # Buscamos pedidos unfulfilled que coincidan con el SKU
    query = """
    query($query: String!) {
      orders(first: 10, query: $query) {
        edges {
          node {
            name
            displayFulfillmentStatus
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
    # Filtramos por pedidos NO preparados y que contengan el SKU
    search_query = f"fulfillment_status:unfulfilled sku:{sku}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={"query": query, "variables": {"query": search_query}}, headers=HEADERS)
            data = response.json()

            orders_edges = data.get("data", {}).get(
                "orders", {}).get("edges", [])
            if not orders_edges:
                return f"No hay pedidos pendientes que incluyan el producto con SKU: {sku}"

            order_names = [edge["node"]["name"] for edge in orders_edges]
            return f"Se encontraron {len(order_names)} pedidos pendientes con este producto: {', '.join(order_names)}."
        except Exception as e:
            return f"Error al buscar pedidos por producto: {str(e)}"

tools = [get_shopify_product_details, get_stock_by_sku,
         get_order_status, search_orders_by_product]
