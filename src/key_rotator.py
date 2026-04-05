"""Rotacion automatica de API keys con quota tracking y fallback."""

from src.db import get_active_keys, disable_key, track_key_usage, is_key_over_quota


class KeyRotator:
    """Rota entre multiples API keys de un servicio.

    Uso:
        rotator = KeyRotator(conn, "hunter")
        key_id, key = rotator.get()
        if not key:
            print("Sin keys disponibles")
            return
        try:
            result = call_api(key)
            rotator.on_success(key_id)
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
        """Retorna (key_id, key_value) de la proxima key disponible."""
        if not self._keys:
            return None, None

        # Try each key, skipping those over quota
        attempts = 0
        while attempts < len(self._keys):
            pair = self._keys[self._idx % len(self._keys)]
            self._idx += 1
            key_id, key_value = pair

            if is_key_over_quota(self.conn, key_id):
                disable_key(self.conn, key_id, "QUOTA_EXHAUSTED")
                self._refresh()
                if not self._keys:
                    return None, None
                attempts += 1
                continue

            return pair

        return None, None

    def get_with_secret(self) -> tuple[int, str, str] | tuple[None, None, None]:
        """Retorna (key_id, key_value, key_secret) para servicios que usan key+secret."""
        key_id, key_value = self.get()
        if key_id is None:
            return None, None, None

        row = self.conn.execute(
            "SELECT key_secret FROM api_keys WHERE id = ?", (key_id,)
        ).fetchone()
        secret = row["key_secret"] if row else ""

        # Support "client_id:client_secret" format in key_value
        if not secret and ":" in key_value:
            parts = key_value.split(":", 1)
            return key_id, parts[0], parts[1]

        return key_id, key_value, secret

    def on_success(self, key_id: int):
        """Registra uso exitoso de una key."""
        track_key_usage(self.conn, key_id)

    def on_rate_limit(self, key_id: int):
        """429 / OVER_QUERY_LIMIT -- rotar a la siguiente, no deshabilitar."""
        if len(self._keys) > 1:
            self._refresh()
        print(f"  [Keys] Rate limit en key {key_id} -- rotando")

    def on_denied(self, key_id: int, reason: str = "REQUEST_DENIED"):
        """REQUEST_DENIED / clave invalida -- deshabilitar permanentemente."""
        disable_key(self.conn, key_id, reason)
        self._refresh()
        print(f"  [Keys] Key {key_id} deshabilitada ({reason}). Quedan: {len(self._keys)}")

    def on_exhausted(self, key_id: int):
        """Quota mensual agotada."""
        disable_key(self.conn, key_id, "QUOTA_EXHAUSTED")
        self._refresh()
        print(f"  [Keys] Key {key_id} con quota agotada. Quedan: {len(self._keys)}")
