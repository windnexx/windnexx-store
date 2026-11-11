#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Inicializar la base de datos de Flask dentro de la app
python -c "from app import app, db; app.app_context().push(); db.create_all()"