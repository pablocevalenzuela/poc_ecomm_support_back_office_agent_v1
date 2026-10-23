import os
import argparse
import json
from typing import List
import psycopg
from shopify_agent.settings import settings

def ingest_excel(file_path: str, sheet_name: str = None):
    """
    Lee un archivo Excel (XLSX/XLS), convierte cada fila en un fragmento de texto
    estructurado (tipo clave-valor), genera embeddings y los sube a Supabase.
    """
    if not os.path.exists(file_path):
        print(f"Error: No se encuentra el archivo {file_path}")
        return

    # 1. Validar dependencias requeridas para Excel
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        print("Error: Se requiere 'pandas' para procesar archivos Excel.")
        print("Por favor, asegúrate de tener activado el entorno virtual correcto.")
        return

    # Validar motor de lectura para archivos .xlsx
    if file_path.endswith('.xlsx'):
        try:
            import openpyxl
        except ImportError:
            print("\nError: Para leer archivos Excel modernos (.xlsx) se requiere la librería 'openpyxl'.")
            print("Por favor, instálala usando el comando:")
            print("  pip install openpyxl")
            print("Y vuelve a ejecutar el script.\n")
            return

    print(f"--- Iniciando Ingesta de Catálogo Excel: {file_path} ---")
    if sheet_name:
        print(f"Procesando hoja específica: '{sheet_name}'")

    # 2. Cargar el archivo Excel con Pandas
    try:
        # Si sheet_name es None, usamos 0 (la primera hoja) para obtener un DataFrame directo en lugar de un diccionario.
        sheet_to_read = sheet_name if sheet_name is not None else 0
        df = pd.read_excel(file_path, sheet_name=sheet_to_read)
    except Exception as e:
        print(f"Error al leer el archivo Excel: {e}")
        return

    print(f"Excel cargado con éxito. Filas detectadas: {len(df)}")
    print(f"Columnas detectadas: {list(df.columns)}")

    # 3. Convertir cada fila en un fragmento de texto estructurado clave-valor (RAG-friendly)
    chunks = []
    for idx, row in df.iterrows():
        row_parts = []
        for col in df.columns:
            val = row[col]
            # Descartar nulos, NaNs, cadenas vacías y columnas irrelevantes como 'Unnamed:'
            if pd.notna(val) and str(val).strip() != "" and not str(col).startswith("Unnamed:"):
                row_parts.append(f"{col}: {str(val).strip()}")
        
        if row_parts:
            row_text = "\n".join(row_parts)
            chunks.append(row_text)

    print(f"Se han generado {len(chunks)} fragmentos estructurados a partir del Excel.")

    if not chunks:
        print("No se encontraron datos válidos en el archivo Excel.")
        return

    # 4. Generar embeddings y subir a base de datos
    generate_and_store_embeddings(chunks, file_path)


def generate_and_store_embeddings(chunks: List[str], file_path: str):
    """
    Genera embeddings utilizando Hugging Face en lotes (batching) y los almacena en Supabase.
    """
    from langchain_huggingface import HuggingFaceEndpointEmbeddings
    
    print("Inicializando modelo de embeddings de Hugging Face...")
    embeddings_model = HuggingFaceEndpointEmbeddings(
        model="sentence-transformers/all-MiniLM-L6-v2",
        huggingfacehub_api_token=settings.huggingface_api_token
    )

    print("Estableciendo conexión con Supabase...")
    db_url = settings.database_url
    if "postgresql+asyncpg://" in db_url:
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    # Tamaño de lote optimizado para la API de inferencia y la base de datos
    batch_size = 100
    total_inserted = 0

    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                print("Conectado con éxito a Supabase.")

                for i in range(0, len(chunks), batch_size):
                    batch_chunks = chunks[i:i + batch_size]
                    print(f"Procesando lote {i // batch_size + 1} ({len(batch_chunks)} fragmentos)...")

                    # Generar embeddings para este lote
                    batch_embeddings = embeddings_model.embed_documents(batch_chunks)

                    # Insertar registros de forma masiva en este lote
                    for content, embedding in zip(batch_chunks, batch_embeddings):
                        cur.execute(
                            "INSERT INTO product_catalog_embeddings (content, embedding, metadata) VALUES (%s, %s, %s)",
                            (
                                content,
                                embedding,
                                json.dumps({"source": os.path.basename(file_path)})
                            )
                        )

                    # Confirmar los cambios por cada lote
                    conn.commit()
                    total_inserted += len(batch_chunks)
                    print(f"Progreso: {total_inserted}/{len(chunks)} fragmentos guardados.")

                print("\n--- Ingesta Completada Exitosamente ---")
                print(f"Se guardaron un total de {total_inserted} productos/filas en 'product_catalog_embeddings'.")

    except Exception as e:
        print(f"Error de base de datos o llamada a la API: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingestar catálogo desde archivo Excel en Supabase pgvector"
    )
    parser.add_argument("file", help="Ruta al archivo Excel (.xlsx, .xls)")
    parser.add_argument(
        "--sheet",
        help="Nombre de la hoja de Excel a procesar (opcional, procesa la primera por defecto)",
        default=None
    )
    args = parser.parse_args()

    ingest_excel(args.file, sheet_name=args.sheet)
