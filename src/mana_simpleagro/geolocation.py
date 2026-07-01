"""Coordenadas (geolocalização) dos pedidos — extraídas dos docs de pedido.

Não é endpoint próprio — reutiliza OrdersAPI.list e extrai/normaliza lat/lng.
Muito usado pra detectar pedidos sem coordenada (cadastro incompleto do vendedor).
"""

from __future__ import annotations

import logging
from typing import Any

from .client import SimpleAgroClient
from .helpers import extract_name, parse_coord, so_digitos
from .orders import OrdersAPI

log = logging.getLogger("mana-simpleagro.geolocation")


class GeolocationAPI:
    """API de geolocalização (derivada dos pedidos).

    Args:
        client: SimpleAgroClient.
        orders: OrdersAPI (opcional).
    """

    def __init__(
        self,
        client: SimpleAgroClient,
        orders: OrdersAPI | None = None,
    ) -> None:
        self.client = client
        self.orders = orders or OrdersAPI(client)

    def listar_coordenadas_pedidos(
        self,
        safra_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista pedidos com geoloc normalizada por pedido.

        Returns:
            [{numero, cnpj, cliente, vendedor, cidade, status, tipo_frete,
              lat, lng, lat_raw, lng_raw}, ...]

            lat/lng são None se ausentes, inválidas ou zeradas (cobre '0000').
        """
        docs = self.orders.list(safra_id=safra_id)
        out = []
        for o in docs:
            geo = o.get("geolocalizacao_entrega") or {}
            lat_raw = geo.get("latitude")
            lng_raw = geo.get("longitude")
            # Só considera válida se AMBOS os campos estão ok
            lat_ok = parse_coord(lat_raw)
            lng_ok = parse_coord(lng_raw)
            lat = lat_ok if lng_ok is not None else None
            lng = lng_ok if lat_ok is not None else None

            cliente = o.get("cliente") or {}
            cnpj = so_digitos(cliente.get("cpf_cnpj") or cliente.get("cnpj") or "")

            out.append({
                "numero": str(o.get("numero") or ""),
                "cnpj": cnpj,
                "cliente": extract_name(cliente),
                "vendedor": extract_name(o.get("vendedor")),
                "cidade": (
                    str(o.get("cidade") or "")
                    + (" / " + str(o.get("estado") or "") if o.get("estado") else "")
                ),
                "status": str(o.get("status") or "").strip().lower(),
                "tipo_frete": str(o.get("tipo_frete") or ""),
                "lat": lat,
                "lng": lng,
                "lat_raw": str(lat_raw) if lat_raw is not None else "",
                "lng_raw": str(lng_raw) if lng_raw is not None else "",
            })
        return out

    def pedidos_sem_coordenadas(
        self, safra_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Atalho: só os pedidos com lat/lng ausente ou zerada."""
        return [
            p for p in self.listar_coordenadas_pedidos(safra_id)
            if p["lat"] is None or p["lng"] is None
        ]
