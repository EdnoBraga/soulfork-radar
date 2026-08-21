"""Fonte primária: Google Places API (New) — Text Search.

Doc: https://developers.google.com/maps/documentation/places/web-service/text-search
A API devolve no máximo 60 resultados por consulta (3 páginas de 20).
Para cobrir uma cidade inteira, o CLI faz várias consultas variando o termo
e a região (ver `montar_consultas`).
"""
from __future__ import annotations

import time
from typing import Iterator

import requests

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

# Campos pedidos. Field mask é obrigatório e cobrado por SKU:
# id/displayName/formattedAddress são "Essentials"; websiteUri/telefone/rating
# caem em "Pro"/"Enterprise". Mantido enxuto de propósito.
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.addressComponents",
    "places.location",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.primaryTypeDisplayName",
    "places.types",
    "nextPageToken",
])


class PlacesError(RuntimeError):
    pass


class PlacesClient:
    def __init__(self, api_key: str, timeout: int = 20, pausa: float = 0.6):
        if not api_key:
            raise PlacesError(
                "Falta a chave da Google Places API. "
                "Defina GOOGLE_PLACES_API_KEY no arquivo .env."
            )
        self.api_key = api_key
        self.timeout = timeout
        self.pausa = pausa
        self.sessao = requests.Session()
        self.chamadas = 0

    def _post(self, body: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }
        resp = self.sessao.post(ENDPOINT, json=body, headers=headers, timeout=self.timeout)
        self.chamadas += 1
        if resp.status_code == 403:
            raise PlacesError(
                "403 da Places API. Verifique se a Places API (New) está ativada no "
                "projeto do Google Cloud, se o faturamento está ligado e se a chave "
                "não tem restrição de referer/IP que bloqueie chamadas de servidor."
            )
        if resp.status_code == 429:
            raise PlacesError("429 — cota da Places API estourada. Tente de novo mais tarde.")
        if resp.status_code >= 400:
            raise PlacesError(f"Places API devolveu {resp.status_code}: {resp.text[:400]}")
        return resp.json()

    def buscar(
        self,
        texto: str,
        *,
        max_resultados: int = 60,
        latitude: float | None = None,
        longitude: float | None = None,
        raio_m: int = 25000,
        tipo: str | None = None,
    ) -> Iterator[dict]:
        """Roda a busca e vai devolvendo cada `place` bruto da API."""
        body: dict = {
            "textQuery": texto,
            "languageCode": "pt-BR",
            "regionCode": "BR",
            "pageSize": 20,
        }
        if tipo:
            body["includedType"] = tipo
        if latitude is not None and longitude is not None:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(min(raio_m, 50000)),
                }
            }

        entregues = 0
        token = None
        while entregues < max_resultados:
            if token:
                body["pageToken"] = token
            dados = self._post(body)
            lugares = dados.get("places") or []
            if not lugares:
                return
            for lugar in lugares:
                yield lugar
                entregues += 1
                if entregues >= max_resultados:
                    return
            token = dados.get("nextPageToken")
            if not token:
                return
            # o token leva alguns instantes para ficar válido
            time.sleep(self.pausa)


def _componente(place: dict, tipo: str) -> str | None:
    for c in place.get("addressComponents") or []:
        if tipo in (c.get("types") or []):
            return c.get("shortText") or c.get("longText")
    return None


def normalizar(place: dict) -> dict:
    """Converte o JSON da Places no dicionário achatado que o Lead consome."""
    loc = place.get("location") or {}
    return {
        "place_id": place.get("id"),
        "nome": (place.get("displayName") or {}).get("text") or "",
        "categoria": (place.get("primaryTypeDisplayName") or {}).get("text"),
        "endereco": place.get("formattedAddress"),
        "municipio": _componente(place, "administrative_area_level_2")
        or _componente(place, "locality"),
        "uf": _componente(place, "administrative_area_level_1"),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "google_maps_url": place.get("googleMapsUri"),
        "nota": place.get("rating"),
        "avaliacoes": place.get("userRatingCount"),
        "status_negocio": place.get("businessStatus"),
        "site": place.get("websiteUri"),
        "telefone": place.get("nationalPhoneNumber"),
        "telefone_intl": place.get("internationalPhoneNumber"),
    }
