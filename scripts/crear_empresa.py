"""Crea la empresa con sus áreas, tipos de proyecto base y el primer administrador.

Uso: python -m scripts.crear_empresa "Estudio Díaz" estudio-diaz admin@ejemplo.com "Leo Díaz"
La contraseña se pide por consola (no queda en el historial).
"""
import getpass
import sys

import psycopg
from psycopg.rows import dict_row

from app import config
from app.db.migrar import migrar
from app.services.empresa import crear_empresa


def main() -> None:
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)
    nombre, slug, email, admin_nombre = sys.argv[1:]
    password = getpass.getpass("Contraseña del admin (mínimo 10 caracteres): ")
    if len(password) < 10 or password != getpass.getpass("Repetila: "):
        print("La contraseña es muy corta o no coincide.")
        sys.exit(1)
    migrar(verbose=True)
    with psycopg.connect(config.DATABASE_URL, row_factory=dict_row) as conn:
        empresa, admin = crear_empresa(conn, nombre=nombre, slug=slug, admin_email=email,
                                       admin_nombre=admin_nombre, admin_password=password)
        conn.commit()
    print(f"Empresa '{empresa['nombre']}' creada (id {empresa['id']}). Admin: {admin['email']}")


if __name__ == "__main__":
    main()
