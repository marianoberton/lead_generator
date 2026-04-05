"""Rotación automática de API keys con blacklist y fallback."""

from src.db import get_active_keys, disable_key


class KeyRotator:
    """Rota entre múltiples API keys de un servicio.

    Uso:
        rotator = KeyRotator(conn, "google_places")
        key_id, key = rotator.get()
        try:
            result = call_api(key)
            rotator.success(key_id)
        except RateLimitError:
            rotator.on_rate_limit(key_id)
        except DeniedError:
            rotator.on_denied(key_id, "REQUEST_DENIED")
    """

    def __init__(self, conn, service: str):
        self.conn = conn
        self.service = service
        self._idx = 0
        self._refresh()

    def _refresh(self):
        self._keys = get_active_keys(self.conn, self.service)

    @property
    def available(self) -> int:
        return len(self._keys)

    def get(self) -> tuple[int, str] | tuple[None, None]:
        """Retorna (key_id, key_value) de la próxima key disponible."""
        if not self._keys:
            return None, None
        pair = self._keys[self._idx % len(self._keys)]
        self._idx += 1
        return pair

    def on_rate_limit(self, key_id: int):
        """429 / OVER_QUERY_LIMIT — rotar a la siguiente, no deshabilitar."""
        if len(self._keys) > 1:
            # Mover esta key al final para intentarla después
            self._refresh()
        print(f"  [Keys] Rate limit en key {key_id} — rotando")

    def on_denied(self, key_id: int, reason: str = "REQUEST_DENIED"):
        """REQUEST_DENIED / clave inválida — deshabilitar permanentemente."""
        disable_key(self.conn, key_id, reason)
        self._refresh()
        print(f"  [Keys] Key {key_id} deshabilitada ({reason}). Quedan: {len(self._keys)}")

    def on_exhausted(self, key_id: int):
        """Quota diaria agotada — deshabilitar hasta mañana."""
        disable_key(self.conn, key_id, "QUOTA_EXHAUSTED")
        self._refresh()
        print(f"  [Keys] Key {key_id} con quota agotada. Quedan: {len(self._keys)}")
