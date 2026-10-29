"""Entrada Vercel: /api/perfil. Compartilha handler com a execução local."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Handler as handler
