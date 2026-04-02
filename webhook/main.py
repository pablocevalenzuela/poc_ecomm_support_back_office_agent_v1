from fastapi import FastAPI, Request, Header, HTTPException

app = FastAPI(title="Shopify Webhook Handler")

@app.post("/webhooks/orders/create")
async def order_created(request: Request, x_shopify_topic: str = Header(None)):
    payload = await request.json()
    # Lógica para procesar el webhook
    return {"status": "received"}
