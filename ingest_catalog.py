import os
import argparse
from typing import List
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
import psycopg
from shopify_agent.settings import settings


def ingest_pdf(file_path: str):
    """
    Lee un PDF, genera fragmentos y los sube a Supabase con embeddings de OpenAI.
    """
    if not os.path.exists(file_path):
        print(f"Error: No se encuentra el archivo {file_path}")
        return

    print(f"--- Iniciando Ingesta: {file_path} ---")

    # 1. Leer el PDF
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"

    print(f"Texto extraído: {len(text)} caracteres.")

    # 2. Dividir en fragmentos (Chunks)
    # 1000 caracteres con un solape de 200 para no perder contexto entre páginas
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len
    )
    chunks = text_splitter.split_text(text)
    print(f"Fragmentos generados: {len(chunks)}")

    # 3. Generar Embeddings
    # Usamos text-embedding-3-small (Anteriormente con GitHub Models)
    # from langchain_openai import OpenAIEmbeddings
    # embeddings_model = OpenAIEmbeddings(
    #     model="text-embedding-3-small",
    #     api_key=settings.ai_api_key,
    #     base_url="https://models.inference.ai.azure.com"
    # )

    # Nuevo modelo con Hugging Face (Inferencia API) - Corregido a HuggingFaceEndpointEmbeddings
    from langchain_huggingface import HuggingFaceEndpointEmbeddings
    embeddings_model = HuggingFaceEndpointEmbeddings(
        model="sentence-transformers/all-MiniLM-L6-v2",
        huggingfacehub_api_token=settings.huggingface_api_token
    )

    print("Generando vectores con Hugging Face (esto puede tardar unos segundos)...")
    embeddings = embeddings_model.embed_documents(chunks)

    # 4. Subir a Supabase (pgvector)
    db_url = settings.database_url
    if "postgresql+asyncpg://" in db_url:
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                print("Conectado a Supabase. Subiendo datos...")

                # Insertamos cada fragmento con su vector
                for content, embedding in zip(chunks, embeddings):
                    cur.execute(
                        "INSERT INTO product_catalog_embeddings (content, embedding, metadata) VALUES (%s, %s, %s)",
                        (content, embedding,
                         '{"source": "' + os.path.basename(file_path) + '"}')
                    )

                conn.commit()
                print("--- Ingesta Completada Exitosamente ---")
                print(
                    f"Se han guardado {len(chunks)} fragmentos en la tabla 'product_catalog_embeddings'.")

    except Exception as e:
        print(f"Error durante la base de datos: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingestar catálogo PDF en Supabase pgvector")
    parser.add_argument("file", help="Ruta al archivo PDF")
    args = parser.parse_args()

    ingest_pdf(args.file)
