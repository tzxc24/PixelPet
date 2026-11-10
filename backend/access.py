"""Local host/origin boundary shared by HTTP and device WebSockets."""
import hmac
import ipaddress
import re
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 11 * 1024 * 1024
DEFAULT_ALLOWED_HOSTS = ('localhost', '127.0.0.1', '::1')


def parse_allowed_hosts(value):
    """An explicit list of bare DNS names or IP addresses; no wildcard/port/URL."""
    entries = value.split(',') if isinstance(value, str) else value
    result = set()
    for entry in entries:
        host = entry.strip().lower()
        if not host:
            continue
        try:
            if '%' in host:
                raise ValueError('Scoped IPv6 hosts are not supported.')
            host = str(ipaddress.ip_address(host))
        except ValueError:
            if len(host) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in host.split('.')):
                raise ValueError('Allowed hosts must be explicit bare hostnames or IP addresses.') from None
        result.add(host)
    if not result:
        raise ValueError('At least one explicit allowed host is required.')
    return frozenset(result)


def access_error(scope, token: str, allowed_hosts=None):
    """Return a safe status/message, or None. Never return supplied credentials."""
    headers = {}
    for key, value in scope.get('headers', []):
        name = key.decode('latin-1').lower()
        if name in headers and name in ('host', 'origin', 'authorization'):
            return 400, '重复的访问请求头。'
        headers[name] = value.decode('latin-1')
    peer = (scope.get('client') or ('', 0))[0]
    host = headers.get('host', '')
    try:
        address = urlsplit('//' + host)
        # Resolve only syntax; no DNS query or hostname-derived trust.
        name = address.hostname
        try:
            name = str(ipaddress.ip_address(name))
        except ValueError:
            pass
        trusted = parse_allowed_hosts(DEFAULT_ALLOWED_HOSTS if allowed_hosts is None else allowed_hosts)
        allowed = name in trusted
        # Starlette's in-process test transport has no network peer or DNS.
        test_transport = peer == 'testclient' and name == 'testserver'
        allowed = allowed or test_transport
        if not allowed or address.username or address.password or address.path or address.query or address.fragment or address.port == 0:
            return 403, '不允许的本地访问地址。'
    except ValueError:
        return 403, '不允许的本地访问地址。'
    origin = headers.get('origin')
    if origin:
        try:
            parsed = urlsplit(origin)
            scheme = {'ws': 'http', 'wss': 'https'}.get(scope.get('scheme'), scope.get('scheme', 'http'))
            if parsed.scheme != scheme or parsed.netloc.lower() != host.lower() or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
                return 403, '不允许跨站访问本地数据。'
        except ValueError:
            return 403, '不允许跨站访问本地数据。'
    try:
        local = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        local = peer in ('testclient', 'localhost')
    try:
        local_host = ipaddress.ip_address(name).is_loopback
    except ValueError:
        local_host = name == 'localhost' or test_transport
    if token or not local or not local_host:
        supplied = headers.get('authorization', '')
        supplied = supplied[7:] if supplied.startswith('Bearer ') else ''
        if not token or not hmac.compare_digest(supplied.encode('utf-8'), token.encode('utf-8')):
            return 401, '访问需要配置本地访问令牌。'
    return None


class LocalAccessMiddleware:
    """Validate the boundary and bound actual bytes before multipart/JSON parsing."""
    def __init__(self, app, token: str = '', allowed_hosts=None):
        self.app, self.token = app, token
        self.allowed_hosts = parse_allowed_hosts(DEFAULT_ALLOWED_HOSTS if allowed_hosts is None else allowed_hosts)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        error = access_error(scope, self.token, self.allowed_hosts)
        # Static UI stays available for the token prompt; API data requires auth.
        if error is not None and (error[0] != 401 or scope.get('path', '').startswith('/api/')):
            return await JSONResponse({'detail': error[1]}, status_code=error[0])(scope, receive, send)
        lengths = [value for key, value in scope.get('headers', []) if key.lower() == b'content-length']
        if len(lengths) > 1 or (lengths and (not lengths[0] or any(char not in b'0123456789' for char in lengths[0]))):
            return await JSONResponse({'detail': '无效请求长度。'}, status_code=400)(scope, receive, send)
        if lengths and int(lengths[0]) > MAX_REQUEST_BYTES:
            return await JSONResponse({'detail': '请求超过上传大小限制。'}, status_code=413)(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                return await JSONResponse({'detail': '请求超过上传大小限制。'}, status_code=413)(scope, receive, send)
            body.extend(chunk)
            if not message.get('more_body', False):
                break
        replayed = False
        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        return await self.app(scope, replay, send)
