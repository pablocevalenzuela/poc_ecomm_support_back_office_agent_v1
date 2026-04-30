import os
import httpx
import logging
import json
import psycopg
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from .settings import settings

# Configuración de Logger
logger = logging.getLogger("SHOPIFY-TOOLS")

HEADERS = {
    "X-Shopify-Access-Token": settings.shopify_admin_access_token,
    "Content-Type": "application/json",
}


def translate_shopify_status(status_type: str, value: str) -> str:
    """Traduce los estados técnicos de Shopify a español humano con iconos."""
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
            "PENDING_FULFILLMENT": "Preparación pendiente ⏳",
            "FULFILLED_AND_CANCELLED": "Anulado ❌"
        }
    }
    if value == "null" or value is None:
        return "Pendiente de envío 📦"
    return translations.get(status_type, {}).get(value, value)


@tool
async def get_order_status(order_name: str) -> str:
    """
    Consulta el estado REAL y sincronizado de un pedido en Shopify. 
    Es OBLIGATORIO usar esta herramienta antes de informar sobre cualquier pedido. 
    Al responder, confirma al usuario que has 'verificado en Shopify'.
    """
    clean_name = str(order_name).replace("#", "").strip()
    logger.info(f"--- CONSULTA REAL SHOPIFY: Pedido {clean_name} ---")

    query = """
    query($query: String!) {
      orders(first: 1, query: $query) {
        edges {
          node {
            name
            displayFinancialStatus
            displayFulfillmentStatus
            customer { firstName lastName }
          }
        }
      }
    }
    """

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={"query": query, "variables": {"query": f"name:#{clean_name}"}}, headers=HEADERS)
            data = response.json()
            edges = data.get("data", {}).get("orders", {}).get("edges", [])

            if not edges:
                return f"No encontré el pedido {order_name} en Shopify."

            order = edges[0]["node"]
            p_status = translate_shopify_status(
                "payment", order["displayFinancialStatus"])
            f_status = translate_shopify_status(
                "fulfillment", order["displayFulfillmentStatus"])
            cust = order.get("customer")
            nombre = f"{cust['firstName']} {cust['lastName']}" if cust else "Cliente"

            return f"ESTADO ACTUAL (Sincronizado): Pedido {order['name']} de {nombre}. Pago: {p_status}. Envío: {f_status}."
        except Exception as e:
            return f"Error al consultar Shopify: {str(e)}"


@tool
async def cancel_shopify_order(order_id: str, reason: str = "CUSTOMER") -> str:
    """
    Ejecuta la cancelación de un pedido en Shopify realmente vía GraphQL.
    Esta es una acción crítica que requiere confirmación previa.
    """
    clean_name = str(order_id).replace("#", "").strip()
    logger.info(
        f"--- ACCIÓN REAL: Iniciando cancelación para Pedido {clean_name} ---")

    # 1. Buscar GID y Email del cliente
    search_query = """
    query($query: String!) { 
        orders(first: 1, query: $query) { 
            edges { node { id name email } } 
        } 
    }
    """
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(settings.shopify_url, json={"query": search_query, "variables": {"query": f"name:#{clean_name}"}}, headers=HEADERS)
            data = resp.json()
            edges = data.get("data", {}).get("orders", {}).get("edges", [])

            if not edges:
                return f"Error: No encontré el pedido {order_id} para cancelar."

            gid = edges[0]["node"]["id"]
            order_name = edges[0]["node"]["name"]
            customer_email = edges[0]["node"].get(
                "email", settings.admin_email)

            logger.info(f"ID encontrado: {gid} para el pedido {order_name}")

        except Exception as e:
            return f"Error técnico al buscar pedido: {str(e)}"

    # 2. Mutación de cancelación
    mutation = """
    mutation orderCancel($orderId: ID!, $reason: OrderCancelReason!, $refund: Boolean!, $restock: Boolean!) {
      orderCancel(orderId: $orderId, reason: $reason, refund: $refund, restock: $restock) {
        job { id }
        userErrors { field message }
      }
    }
    """

    variables = {
        "orderId": gid,
        "reason": "CUSTOMER",
        "refund": False,
        "restock": True
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={"query": mutation, "variables": variables}, headers=HEADERS)
            res_data = response.json()
            logger.info(f"RESPUESTA DE SHOPIFY: {json.dumps(res_data)}")

            cancel_result = res_data.get("data", {}).get("orderCancel", {})
            user_errors = cancel_result.get("userErrors", [])

            if user_errors:
                return f"Shopify rechazó la cancelación: {user_errors[0]['message']}"

            return f"EXITO: Pedido {order_name} cancelado. Email cliente: {customer_email}."
        except Exception as e:
            return f"Error técnico al ejecutar cancelación: {str(e)}"


@tool
async def send_approval_email(order_name: str, reason: str) -> str:
    """
    Envía correo al administrador para aprobación de cancelación. 
    Informa al usuario que has enviado la solicitud vía email al administrador.
    """
    if not settings.smtp_user or not settings.admin_email:
        return "Error: Configuración de email incompleta en .env."

    subject = f"APROBACIÓN REQUERIDA: Cancelar {order_name}"
    body = f"El asistente de IA solicita cancelar el pedido {order_name}.\nMotivo: {reason}\n\nPor favor, responde 'apruebo' o 'no apruebo' en el chat para proceder."

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = settings.admin_email
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return f"Email de solicitud enviado al administrador ({settings.admin_email})."
    except Exception as e:
        return f"Error al enviar email: {str(e)}"


@tool
async def send_email_to_supplier(cant: int, sku: str) -> str:
    """
    Envía un correo electrónico formal al proveedor solicitando nuevo stock de un producto y además una copia del mismo correo electrónico al administrador del negocio. 
    Al usar esta herramienta, informa al usuario que la solicitud se ha procesado 
    'a través del sistema de correos' para asegurar transparencia total.
    """
    if not settings.smtp_user or not settings.admin_email:
        return "Error: Configuración de email incompleta en .env."

    subject = f"NUEVA SOLICITUD DE STOCK"
    body = f"Estimado Juan Pérez de Lechería Río Claro, desde La Tablita,\n\nsolicitamos reservar nuevo stock de {cant}, para el SKU: {sku}\n\nPor favor, espere nuestra OC que será enviada en un plazo de 24 hrs.\n\nGracias, Joaquín Urra, La Tablita"

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = settings.email_to_supplier
        msg["Cc"] = settings.admin_email
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return f"Email de solicitud enviado al proveedor y al administrador ({settings.admin_email})."
    except Exception as e:
        return f"Error al enviar email: {str(e)}"


@tool
async def send_customer_cancellation_email(order_name: str, customer_email: str) -> str:
    """Envía notificación formal de cancelación al cliente."""
    subject = f"Actualización de tu pedido {order_name} - Cancelado"
    body = f"Hola,\n\nTe informamos que tu pedido {order_name} ha sido cancelado exitosamente.\n\nSaludos,\nEquipo de La Tablita."

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_user
        msg["To"] = customer_email
        msg["Cc"] = settings.admin_email
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return f"Notificación enviada al cliente ({customer_email}) y administrador."
    except Exception as e:
        return f"Error al notificar al cliente: {str(e)}"


@tool
async def search_product_catalog(query: str) -> str:
    """
    Busca información técnica sobre un proveedor, un producto(ingredientes, información de contacto del proveedor y datos técnicos de los productos del catálogo de un proveedor) en el catálogo PDF mediante RAG. 
    Al responder, menciona explícitamente que la información proviene de la 'Documentación oficial y técnica del proveedor y su catálogo de productos'.
    """
    logger.info(f"--- RAG: Iniciando búsqueda en catálogo para: '{query}' ---")
    embeddings_model = HuggingFaceEndpointEmbeddings(
        model="sentence-transformers/all-MiniLM-L6-v2", huggingfacehub_api_token=settings.huggingface_api_token)
    try:
        # Generar vector
        query_embedding = await embeddings_model.aembed_query(query)

        db_url = settings.database_url.replace(
            "postgresql+asyncpg://", "postgresql://")
        async with await psycopg.AsyncConnection.connect(db_url) as conn:
            async with conn.cursor() as cur:
                # DEPURACIÓN: ¿Hay algo en la base de datos?
                await cur.execute("SELECT count(*) FROM product_catalog_embeddings;")
                count = await cur.fetchone()
                logger.info(
                    f"RAG DIAGNÓSTICO: La base de datos tiene {count[0]} filas.")

                # Búsqueda real
                # IMPORTANTE: Convertimos el vector a lista de strings para asegurar el casting correcto en PostgreSQL
                embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

                await cur.execute(
                    "SELECT content FROM product_catalog_embeddings ORDER BY embedding <=> %s LIMIT 10;",
                    (embedding_str,)
                )
                rows = await cur.fetchall()

                if not rows:
                    # SI NO HAY RESULTADOS CON VECTOR, DEVOLVEMOS LO QUE HAYA (Fallback para catálogo pequeño)
                    await cur.execute("SELECT content FROM product_catalog_embeddings LIMIT 2;")
                    fallback_rows = await cur.fetchall()
                    if fallback_rows:
                        logger.info("RAG: Usando fallback de contenido total.")
                        return "INFORMACIÓN GENERAL DEL CATÁLOGO:\n\n" + "\n---\n".join([r[0] for r in fallback_rows])

                    return "No encontré información técnica en el catálogo."

                logger.info(f"RAG: Éxito. {len(rows)} fragmentos recuperados.")
                return "INFORMACIÓN DEL CATÁLOGO PDF:\n\n" + "\n---\n".join([row[0] for row in rows])
    except Exception as e:
        logger.error(f"RAG Error: {str(e)}")
        return f"Error técnico al acceder al catálogo: {str(e)}"


@tool
async def get_stock_by_sku(product_name_or_sku: str) -> str:
    """
    Consulta el stock disponible en Shopify. 
    Confirma al usuario que has 'consultado el inventario de Shopify' al dar la respuesta.
    """
    query = "query($q: String!) { productVariants(first: 5, query: $q) { edges { node { displayName inventoryQuantity sku } } } }"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(settings.shopify_url, json={"query": query, "variables": {"q": product_name_or_sku}}, headers=HEADERS)
            edges = r.json().get("data", {}).get("productVariants", {}).get("edges", [])
            return "\n".join([f"- {e['node']['displayName']}: {e['node']['inventoryQuantity']} uds" for e in edges]) if edges else "Sin stock."
        except Exception as e:
            return str(e)


@tool
async def get_shopify_product_details(inventory_item_id: str):
    """Obtiene detalles técnicos de un ítem de inventario en Shopify."""
    gid = f"gid://shopify/InventoryItem/{inventory_item_id}" if not str(
        inventory_item_id).startswith("gid://") else inventory_item_id
    query = "query($id: ID!) { inventoryItem(id: $id) { sku variant { title product { title vendor } } } }"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(settings.shopify_url, json={'query': query, 'variables': {'id': gid}}, headers=HEADERS)
            data = response.json()
            item = data["data"].get("inventoryItem")
            if not item:
                return "Producto no encontrado."
            return {"title": item["variant"]["product"]["title"], "sku": item["sku"]}
        except Exception as e:
            return str(e)

tools = [get_order_status, cancel_shopify_order, send_approval_email, send_customer_cancellation_email,
         search_product_catalog, get_stock_by_sku, get_shopify_product_details, send_email_to_supplier]
