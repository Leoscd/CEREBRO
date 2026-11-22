"""Embeddings de OpenAI y proveedor determinístico para desarrollo y pruebas."""
import hashlib
import math
import re
import unicodedata

from openai import OpenAI

from app import config


class ConfiguracionEmbeddings(RuntimeError):
    """Datos que faltan o no coinciden con el esquema de almacenamiento."""


def _vector_falso(texto: str, dimensiones: int) -> list[float]:
    normalizado = unicodedata.normalize("NFKD", texto.casefold())
    normalizado = "".join(c for c in normalizado if not unicodedata.combining(c))
    vector = [0.0] * dimensiones

    def sumar(caracteristica: str, peso: float) -> None:
        hash_entero = int.from_bytes(hashlib.blake2b(caracteristica.encode(), digest_size=8).digest())
        vector[hash_entero % dimensiones] += peso if (hash_entero // dimensiones) & 1 else -peso

    for palabra in re.findall(r"[^\W_]+", normalizado):
        sumar("palabra:" + palabra, 2.0)
        contorno = f"^{palabra}$"
        for i in range(len(contorno) - 2):
            sumar("trigrama:" + contorno[i:i + 3], 1.0)
    norma = math.hypot(*vector)
    if not norma:
        vector[0] = 1.0
        return vector
    return [valor / norma for valor in vector]


def embeber(textos: list[str]) -> list[list[float]]:
    if not textos:
        return []
    dimensiones = config.EMBEDDINGS_DIMENSIONES
    if dimensiones != 384:
        raise ConfiguracionEmbeddings("EMBEDDINGS_DIMENSIONES debe coincidir con vector(384)")
    proveedor = config.EMBEDDINGS_PROVEEDOR
    if proveedor == "falso":
        return [_vector_falso(texto, dimensiones) for texto in textos]
    if proveedor != "openai":
        raise ConfiguracionEmbeddings("EMBEDDINGS_PROVEEDOR debe ser openai o falso")
    if not config.MODELO_EMBEDDINGS:
        raise ConfiguracionEmbeddings("Configurá MODELO_EMBEDDINGS para usar embeddings de OpenAI")
    if not config.OPENAI_API_KEY:
        raise ConfiguracionEmbeddings("Configurá OPENAI_API_KEY para usar embeddings de OpenAI")

    vectores = []
    with OpenAI(api_key=config.OPENAI_API_KEY, base_url="https://api.openai.com/v1", max_retries=2, timeout=30.0) as cliente:
        for inicio in range(0, len(textos), 100):
            lote = textos[inicio:inicio + 100]
            datos = cliente.embeddings.create(model=config.MODELO_EMBEDDINGS, input=lote, dimensions=dimensiones).data
            ordenados = sorted(datos, key=lambda item: item.index)
            if [item.index for item in ordenados] != list(range(len(lote))):
                raise RuntimeError("OpenAI devolvió un lote de embeddings incompleto")
            vectores.extend(item.embedding for item in ordenados)
    return vectores


def vector_sql(vector: list[float]) -> str:
    return "[" + ",".join(str(valor) for valor in vector) + "]"
