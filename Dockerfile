# Stage 1: Runtime
FROM python:3.11-slim

# Evita que Python genere archivos .pyc y permite ver logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Añadimos la raíz del proyecto al PYTHONPATH para que los módulos se vean entre sí
ENV PYTHONPATH=/app

WORKDIR /app

# Instalamos las dependencias primero para aprovechar el cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código (excluyendo lo del .dockerignore)
COPY . .

# Exponemos el puerto (aunque Cloud Run lo ignora y usa su propia variable $PORT)
EXPOSE 8000

# Iniciamos la aplicación unificada como un módulo
CMD ["python", "-m", "api.main"]
