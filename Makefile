# Configuración de variables
PYTHON = python3
PIP = pip3
APP_MODULE = api.main:app
PORT = 8000

.PHONY: help install dev run clean

help:
	@echo "Comandos disponibles:"
	@echo "  make install  - Instalar dependencias desde requirements.txt"
	@echo "  make dev      - Ejecutar Servidor Unificado (API + UI) con auto-reload"
	@echo "  make run      - Ejecutar Servidor Unificado (Modo producción local)"
	@echo "  make clean    - Eliminar archivos temporales de Python"

install:
	$(PIP) install -r requirements.txt

dev:
	@echo "Lanzando Servidor en Modo Desarrollo: http://localhost:$(PORT)"
	@echo "La UI estará disponible en: http://localhost:$(PORT)/ui"
	$(PYTHON) -m uvicorn $(APP_MODULE) --host 0.0.0.0 --port $(PORT) --reload

run:
	@echo "Lanzando Servidor en Modo Producción Local: http://localhost:$(PORT)"
	$(PYTHON) api/main.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
