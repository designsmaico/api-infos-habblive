"""API local de extração de perfis Habblive. Python 3.10+, sem dependências."""
import json
import os
import re
import hmac
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 5 * 1024 * 1024
FIELDS = {
    'ID': 'id', 'Missão': 'motto', 'Chegou em': 'created_at',
    'Último login': 'last_login', 'Placar de Conquistas': 'achievement_score',
    'Pixels': 'pixels', 'Diamantes': 'diamonds', 'Duckets': 'duckets',
    'Gemas': 'gems', 'Games': 'games', 'PromoCoins': 'promo_coins',
    'Fatias': 'slices', 'Pontos de Promoções': 'promotion_points',
    'Pontos de Eventos': 'event_points',
}
NUMERIC = set(FIELDS.values()) - {'motto', 'created_at', 'last_login'}


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    def text(self):
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = self.current = Node()
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def clean(value):
    return re.sub(r'\s+', ' ', value).strip()


def public_image(value, host, prefix):
    if value.startswith('//'):
        value = 'https:' + value
    parsed = urlsplit(value)
    if (parsed.scheme == 'https' and parsed.hostname == host
            and parsed.path.startswith(prefix) and not parsed.username
            and not parsed.password and not parsed.fragment
            and parsed.port in (None, 443)):
        return value
    return None


def parse_profile(html):
    nodes = list(Document(html).root.walk())
    avatar = next((n for n in nodes if n.tag == 'img'
                   and n.attrs.get('alt', '').startswith('Avatar de ')), None)
    if avatar is None:
        raise ValueError('PROFILE_NOT_FOUND: envie o HTML de um perfil, não a tela de login.')
    result = {'username': avatar.attrs['alt'][len('Avatar de '):].strip()}
    avatar_url = public_image(avatar.attrs.get('src', ''), 'habbo.city', '/habbo-imaging/avatarimage')
    result['avatar_url'] = avatar_url
    result['figure'] = parse_qs(urlsplit(avatar_url).query).get('figure', [None])[0] if avatar_url else None
    for node in nodes:
        if node.tag != 'b' or node.parent is None:
            continue
        field = FIELDS.get(clean(node.text()).rstrip(':').strip())
        if field is None:
            continue
        siblings = node.parent.children
        parts = []
        for sibling in siblings[siblings.index(node) + 1:]:
            if isinstance(sibling, Node) and sibling.tag in {'b', 'br'}:
                break
            parts.append(sibling.text() if isinstance(sibling, Node) else sibling)
        value = clean(''.join(parts))
        if field in NUMERIC:
            number = value.replace('.', '').replace(',', '').replace(' ', '')
            result[field] = int(number) if re.fullmatch(r'-?\d+', number) else None
        else:
            result[field] = value
    result['badges'] = []
    for node in nodes:
        if 'perfil-badge' not in node.attrs.get('class', '').split():
            continue
        match = re.search(r'''url\(\s*['"]?([^'"\s)]+)''', node.attrs.get('style', ''), re.I)
        if not match:
            continue
        image = public_image(match[1], 'images.habblive.com', '/c_imagenes/album1584/')
        if image:
            code = urlsplit(image).path.rsplit('/', 1)[-1].removesuffix('.gif')
            if code not in {b['code'] for b in result['badges']}:
                result['badges'].append({'code': code, 'image_url': image})
    result['pagination'] = {'other_pages': sorted({int(m.group(1)) for n in nodes
        if n.tag == 'a' for m in [re.search(r'[?&]badge_page=(\d+)', n.attrs.get('href', ''))] if m})}
    return result


def parse_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('O corpo deve ser um objeto JSON.')
    pages = payload.get('pages')
    if pages is None:
        pages = [payload.get('html')]
    if not isinstance(pages, list) or not 1 <= len(pages) <= 20 or any(not isinstance(p, str) or not p.strip() for p in pages):
        raise ValueError('Envie html como texto ou pages como lista de 1 a 20 HTMLs.')
    profiles = [parse_profile(page) for page in pages]
    profile = profiles[0]
    if any(p['username'].casefold() != profile['username'].casefold()
           or p.get('id') != profile.get('id') for p in profiles[1:]):
        raise ValueError('Todas as páginas devem pertencer ao mesmo usuário.')
    badges = {b['code']: b for p in profiles for b in p['badges']}
    profile['badges'] = list(badges.values())
    profile['pagination']['other_pages'] = sorted({n for p in profiles for n in p['pagination']['other_pages']})
    profile['pages_parsed'] = len(pages)
    profile['badges_scope'] = 'submitted_pages_only'
    return profile


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Não registrar HTML, cabeçalhos ou dados pessoais.

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        origin = self.headers.get('Origin')
        allowed = os.environ.get('CORS_ORIGIN', '').split(',')
        if origin and origin in allowed:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self.headers.get('Origin')
        if origin and origin in os.environ.get('CORS_ORIGIN', '').split(','):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        route = urlsplit(self.path)
        if route.path == '/api/perfil':
            secret = os.environ.get('INTEGRATION_API_KEY', '')
            if not secret:
                return self.reply(503, {'error': 'INTEGRATION_API_KEY_NOT_CONFIGURED'})
            authorization = self.headers.get('Authorization', '')
            if not hmac.compare_digest(authorization.encode(), ('Bearer ' + secret).encode()):
                return self.reply(401, {'error': 'UNAUTHORIZED'})
            from client import client, UpstreamError
            query = parse_qs(route.query)
            try:
                page = int(query.get('badge_page', ['1'])[0])
            except ValueError:
                return self.reply(400, {'error': 'INVALID_BADGE_PAGE'})
            try:
                profile = client.lookup(query.get('user', [''])[0], page)
                return self.reply(200, {'data': profile})
            except UpstreamError as error:
                return self.reply(error.status, {'error': error.code})
        if self.path == '/health':
            self.reply(200, {'status': 'ok'})
        else:
            self.reply(404, {'error': 'NOT_FOUND'})

    def do_POST(self):
        if self.path != '/v1/profile/parse':
            return self.reply(404, {'error': 'NOT_FOUND'})
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            return self.reply(415, {'error': 'USE_APPLICATION_JSON'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                return self.reply(413, {'error': 'BODY_LIMIT', 'max_bytes': MAX_BODY})
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            self.reply(200, {'data': parse_payload(payload)})
        except (ValueError, UnicodeError, RecursionError):
            self.reply(422, {'error': 'INVALID_PROFILE_HTML', 'message': 'Envie HTML válido de perfil; páginas adicionais devem ser do mesmo usuário.'})


if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8000'))
    print(f'Habblive API: http://{host}:{port}')
    ThreadingHTTPServer((host, port), Handler).serve_forever()
