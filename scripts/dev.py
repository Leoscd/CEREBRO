"""Levanta el gestor en local SIN Docker: Postgres embebido (pgserver, con pgvector),
migraciones, datos demo y uvicorn con recarga.

Uso: .venv\\Scripts\\python -m scripts.dev  [--puerto 8000]
La base de desarrollo vive en data/pgdev (ignorada por git).
"""
import argparse
import os

from app import config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=int(os.getenv("PORT", "8000")))
    args = ap.parse_args()

    import pgserver

    carpeta = config.DATA_DIR / "pgdev"
    carpeta.mkdir(parents=True, exist_ok=True)
    servidor = pgserver.get_server(str(carpeta), cleanup_mode=None)  # queda corriendo entre sesiones
    url = servidor.get_uri()
    os.environ["DATABASE_URL"] = url
    config.DATABASE_URL = url

    from scripts import seed_demo

    seed_demo.main()

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.puerto, reload=False)


if __name__ == "__main__":
    main()
