"""Authenticated snapshots over WebSocket, using the existing Django API."""
import asyncio
import json

from django.conf import settings
from django.http.request import split_domain_port, validate_host


PATHS = frozenset(("/dashboard/summary", "/notifications", "/fleet/live-locations", "/fleet/my-trips"))
SOCKET_PATH = "/api/v1/realtime"
INTERVAL = 15
MAX_SNAPSHOT = 2_000_000


async def _snapshot(http, scope, host, access, workspace, path):
    full_path = "/api/v1" + path
    request_scope = {
        "type": "http", "method": "GET", "http_version": "1.1",
        "scheme": "https" if scope.get("scheme") == "wss" else "http",
        "path": full_path, "query_string": b"", "root_path": "",
        "server": scope.get("server"), "client": scope.get("client"),
        "headers": [(b"host", host), (b"accept", b"application/json"),
                    (b"authorization", b"Bearer " + access), (b"x-workspace", workspace)],
    }
    status = 500
    body = bytearray()
    first = True

    async def receive():
        nonlocal first
        if first:
            first = False
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Future()

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
        elif len(body) <= MAX_SNAPSHOT:
            body.extend(message.get("body", b""))

    await http(request_scope, receive, send)
    if status != 200 or len(body) > MAX_SNAPSHOT:
        return status, None
    return status, json.loads(body)


def _authentication(message):
    raw = message.get("text")
    if not isinstance(raw, str) or len(raw) > 8192:
        raise ValueError("Invalid authentication message")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("type") != "authenticate":
        raise ValueError("Invalid authentication message")
    access, workspace, paths = value.get("access"), value.get("workspace"), value.get("paths")
    if not isinstance(access, str) or not access or not access.isascii() or not access.isprintable():
        raise ValueError("Invalid access token")
    if not isinstance(workspace, str) or not workspace or not workspace.isascii() or not workspace.isprintable() or len(workspace) > 255:
        raise ValueError("Invalid workspace")
    if not isinstance(paths, list) or not 1 <= len(paths) <= len(PATHS):
        raise ValueError("Invalid subscriptions")
    if any(not isinstance(path, str) or path not in PATHS for path in paths):
        raise ValueError("Invalid subscription")
    return access.encode("ascii"), workspace.encode("ascii"), tuple(dict.fromkeys(paths))


def with_mobile_realtime(http):
    async def application(scope, receive, send):
        if scope["type"] != "websocket":
            return await http(scope, receive, send)
        connected = await receive()
        if connected["type"] != "websocket.connect":
            return
        host = dict(scope.get("headers", ())).get(b"host", b"")
        domain, _ = split_domain_port(host.decode("ascii", errors="replace"))
        allowed_hosts = settings.ALLOWED_HOSTS
        if settings.DEBUG and not allowed_hosts:
            allowed_hosts = [".localhost", "127.0.0.1", "[::1]"]
        if scope["path"] != SOCKET_PATH or not domain or not validate_host(domain, allowed_hosts):
            await send({"type": "websocket.close", "code": 4403})
            return
        await send({"type": "websocket.accept"})
        try:
            message = await asyncio.wait_for(receive(), timeout=8)
            if message["type"] == "websocket.disconnect":
                return
            access, workspace, paths = _authentication(message)
        except (ValueError, TimeoutError):
            await send({"type": "websocket.close", "code": 4401})
            return

        try:
            while True:
                delivered = False
                for path in paths:
                    status, data = await _snapshot(http, scope, host, access, workspace, path)
                    if status == 401:
                        await send({"type": "websocket.close", "code": 4401})
                        return
                    if status != 200 or data is None:
                        continue
                    message = json.dumps({"type": "snapshot", "path": path, "data": data})
                    if len(message) <= MAX_SNAPSHOT:
                        await send({"type": "websocket.send", "text": message})
                        delivered = True
                if not delivered:
                    await send({"type": "websocket.close", "code": 4403})
                    return
                try:
                    message = await asyncio.wait_for(receive(), timeout=INTERVAL)
                    if message["type"] == "websocket.disconnect":
                        return
                    await send({"type": "websocket.close", "code": 4400})
                    return
                except TimeoutError:
                    continue
        except OSError:
            return

    return application
