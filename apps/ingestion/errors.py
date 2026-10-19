class TemporaryIngestError(Exception):
    """Временный сбой источника. Для него разрешён повтор с нарастающей паузой."""
