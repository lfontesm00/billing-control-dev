class BusinessError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, context: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.context = context or {}
