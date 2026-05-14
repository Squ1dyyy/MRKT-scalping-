class MRKTError(Exception):
    pass


class AuthError(MRKTError):
    pass


class RateLimitedError(MRKTError):
    pass


class ServerError(MRKTError):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class NetworkError(MRKTError):
    pass


class NoAccountError(MRKTError):
    pass
