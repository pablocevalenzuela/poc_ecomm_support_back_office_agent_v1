import gradio as gr

def predict(message, history):
    return f"Respuesta simulada para: {message}"

demo = gr.ChatInterface(fn=predict, title="Shopify Agent Admin UI")

if __name__ == "__main__":
    demo.launch()
