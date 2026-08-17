from __future__ import annotations

import re
from dataclasses import dataclass

from flask import g, request

import database as db

from .errors import (
    ForbiddenOrganizationError,
    InsufficientScopeError,
    InvalidAPIKeyError,
    MalformedAPIKeyError,
    MissingAPIKeyError,
    RevokedAPIKeyError,
)


_API_KEY_PATTERN = re.compile(r"^lii_[0-9a-f]{8}\.[A-Za-z0-9_-]{16,}$")


@dataclass(frozen=True)
class APIKeyIdentity:
    api_key_id: int
    organization_id: int
    user_id: int | None
    name: str
    scopes: tuple[str, ...]
    key_prefix: str
    raw_key: str | None = None

    def allows(self, required_scopes: tuple[str, ...] | list[str] | None = None) -> bool:
        """Chave sem escopo não autoriza nada.

        Antes, uma lista de escopos vazia liberava qualquer rota. O caminho
        provável não era ataque, era descuido: chave criada às pressas, sem
        escopo marcado, virava chave-mestra. Agora ela não abre porta nenhuma
        até alguém dizer explicitamente quais.

        O curinga `*` continua valendo — esse é um "tudo" que alguém escolheu.
        """
        required_scopes = tuple(required_scopes or ())
        if not required_scopes:
            return True
        granted = {scope for scope in self.scopes if scope}
        if "*" in granted:
            return True
        return any(scope in granted for scope in required_scopes)


def extract_raw_api_key() -> str:
    header_key = (request.headers.get("X-API-Key") or "").strip()
    if header_key:
        return header_key
    authorization = (request.headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization.split(None, 1)[1].strip()
    if authorization:
        return authorization
    raise MissingAPIKeyError()


def _parse_key_format(raw_key: str) -> str:
    if not raw_key:
        raise MissingAPIKeyError()
    if not _API_KEY_PATTERN.match(raw_key):
        raise MalformedAPIKeyError()
    return raw_key


def authenticate_api_key(*, required_scopes: tuple[str, ...] | list[str] | None = None,
                         organization_id: int | None = None,
                         request_organization_id: int | None = None) -> APIKeyIdentity:
    raw_key = _parse_key_format(extract_raw_api_key())
    row = db.load_analysis_api_key(raw_key, include_revoked=True)
    if not row:
        raise InvalidAPIKeyError()
    if row.get("revoked_at"):
        raise RevokedAPIKeyError()
    identity = APIKeyIdentity(
        api_key_id=int(row["id"]),
        organization_id=int(row["organization_id"]),
        user_id=row.get("user_id"),
        name=row.get("name") or "",
        scopes=tuple(row.get("scopes") or ()),
        key_prefix=row.get("key_prefix") or "",
        raw_key=raw_key,
    )
    expected_org = request_organization_id if request_organization_id is not None else organization_id
    if expected_org is not None and int(expected_org) != identity.organization_id:
        raise ForbiddenOrganizationError()
    if required_scopes and not identity.allows(required_scopes):
        raise InsufficientScopeError(details={
            "required_scopes": list(required_scopes),
            "granted_scopes": list(identity.scopes),
        })
    g.api_key_identity = identity
    return identity
