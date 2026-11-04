"""One fixed signed ingress: authenticate exact bytes before JSON; no URL fetching."""

import hashlib
import hmac
import os
import re
import stat
import time
from uuid import UUID

from fastapi import Request
from pydantic import ValidationError

from api.app.wire import SignedBatchRequest
from contracts.codec import parse_object

DIRECTORY = "/etc/proofflow-batch-events"


class SignatureFailure(Exception):
    pass


def connection_key(master: bytes, connection: UUID) -> bytes:
    if type(master) is not bytes or len(master) != 32 or not isinstance(connection, UUID):
        raise SignatureFailure("BATCH_SIGNATURE_UNAVAILABLE")
    return hmac.digest(master, b"proofflow-batch-key-v1\0" + connection.bytes, "sha256")


def authenticate(headers, raw: bytes, connection: UUID, master: bytes, now: int):
    values = {}
    selected = {b"x-proofflow-event-id", b"x-proofflow-timestamp", b"x-proofflow-signature"}
    for key, value in headers:
        key = key.lower()
        if key in (b"cookie", b"origin", b"authorization", b"content-encoding"):
            raise SignatureFailure("BATCH_SIGNATURE_INVALID")
        if key in selected:
            if key in values:
                raise SignatureFailure("BATCH_SIGNATURE_INVALID")
            values[key] = value
    if set(values) != selected or not 1 <= len(raw) <= 2048:
        raise SignatureFailure("BATCH_SIGNATURE_INVALID")
    event, stamp, signature = (
        values[k]
        for k in (b"x-proofflow-event-id", b"x-proofflow-timestamp", b"x-proofflow-signature")
    )
    if (
        not re.fullmatch(rb"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", event)
        or not re.fullmatch(rb"[0-9]{10}", stamp)
        or not re.fullmatch(rb"sha256=[0-9a-f]{64}", signature)
        or abs(now - int(stamp)) > 300
    ):
        raise SignatureFailure("BATCH_SIGNATURE_INVALID")
    expected = hmac.digest(
        connection_key(master, connection), stamp + b"\n" + event + b"\n" + raw, "sha256"
    )
    if not hmac.compare_digest(expected, bytes.fromhex(signature[7:].decode("ascii"))):
        raise SignatureFailure("BATCH_SIGNATURE_INVALID")
    return UUID(event.decode("ascii")), int(stamp), hashlib.sha256(raw).hexdigest()


def load_batch_master():
    descriptors = []
    try:
        root = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(root)
        info = os.fstat(root)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise SignatureFailure("BATCH_SIGNATURE_UNAVAILABLE")
        pin = os.open("master", os.O_PATH | os.O_NOFOLLOW, dir_fd=root)
        descriptors.append(pin)
        before = os.fstat(pin)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o400
            or before.st_size != 32
        ):
            raise SignatureFailure("BATCH_SIGNATURE_UNAVAILABLE")
        reader = os.open(f"/proc/self/fd/{pin}", os.O_RDONLY | os.O_CLOEXEC)
        descriptors.append(reader)
        raw = os.read(reader, 33)
        after = os.fstat(reader)
        if len(raw) != 32 or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise SignatureFailure("BATCH_SIGNATURE_UNAVAILABLE")
        return raw
    except OSError:
        raise SignatureFailure("BATCH_SIGNATURE_UNAVAILABLE") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def install_batch_event_routes(app, store, authorize, master_loader=None):
    from api.app.product import HttpFailure, body, identifier

    if master_loader is None:
        master_loader = load_batch_master

    @app.post("/v1/connections/{connection_id}/batch-events", status_code=202)
    async def accept(connection_id: str, request: Request):
        connection = identifier(connection_id)
        raw = await body(request, 2048)
        try:
            event, stamp, digest = authenticate(
                request.scope["headers"], raw, connection, master_loader(), int(time.time())
            )
        except SignatureFailure as error:
            raise HttpFailure(
                503 if str(error) == "BATCH_SIGNATURE_UNAVAILABLE" else 403, str(error)
            ) from None
        try:
            value = SignedBatchRequest.model_validate(parse_object(raw))
        except ValidationError:
            raise HttpFailure(400, "INVALID_BATCH_EVENT") from None
        return (
            await store.call(
                "batch_event",
                connection,
                event,
                stamp,
                digest,
                identifier(value.transactions_id),
                identifier(value.customers_id),
            )
        )[0]

    @app.post("/v1/connections/{connection_id}/revoke")
    async def revoke(connection_id: str, request: Request):
        workspace, token, csrf = await authorize(request, True)
        value = parse_object(await body(request, 512))
        if value != {"confirm": True} or value["confirm"] is not True:
            raise HttpFailure(400, "EXACT_CONNECTION_REQUIRED")
        await store.call(
            "batch_connection_revoke", workspace, token, csrf, identifier(connection_id)
        )
        return {"revoked": True}
