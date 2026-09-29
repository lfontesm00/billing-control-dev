import re
import uuid


def new_int64_id() -> int:
    """Positive, non-sequential INT64 derived from UUID4 and safe in JavaScript."""
    return (uuid.uuid4().int % ((1 << 53) - 1)) + 1


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_phone(value: str | None) -> str | None:
    normalized = digits(value)
    return normalized or None


def is_valid_cpf(value: str) -> bool:
    cpf = digits(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for size in (9, 10):
        total = sum(int(cpf[index]) * (size + 1 - index) for index in range(size))
        digit = 0 if total % 11 < 2 else 11 - total % 11
        if int(cpf[size]) != digit:
            return False
    return True


def is_valid_cnpj(value: str) -> bool:
    cnpj = digits(value)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    for size, weights in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        total = sum(int(cnpj[index]) * weights[index] for index in range(size))
        digit = 0 if total % 11 < 2 else 11 - total % 11
        if int(cnpj[size]) != digit:
            return False
    return True
