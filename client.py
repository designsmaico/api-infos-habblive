"""Cliente de login normal. Segredos e sessão permanecem somente no servidor."""
import copy
import os
import re
import threading
import time
from collections import OrderedDict
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler
from app import Document, parse_payload

BASE = 'https://habblive.in/'
LIMIT = 3 * 1024 * 1024


class UpstreamError(Exception):
    def __init__(self, code, status=502):
        self.code, self.status = code, status
        super().__init__(code)


def trusted(url):
    p = urlsplit(url)
    return p.scheme == 'https' and p.hostname == 'habblive.in' and p.port in (None, 443) and not p.username and not p.password


class SameSiteRedirect(HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not trusted(newurl):
            raise UpstreamError('UNEXPECTED_LOGIN_REDIRECT')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def login_form(html):
    nodes = list(Document(html).root.walk())
    for node in nodes:
        if node.tag == 'form' and any(n.tag == 'input' and n.attrs.get('type') == 'password' for n in node.walk()):
            return node
    return None


class HabbliveClient:
    def __init__(self):
        self.lock = threading.Lock()
        self.opener = None
        self.cache = OrderedDict()
        self.login_after = 0
        self.reset_at = 0

    def reset(self):
        self.opener = build_opener(SameSiteRedirect(), HTTPCookieProcessor(CookieJar()))
        self.reset_at = time.monotonic() + 900

    def request(self, url, fields=None):
        if not trusted(url):
            raise UpstreamError('UNEXPECTED_LOGIN_REDIRECT')
        data = urlencode(fields).encode() if fields is not None else None
        request = Request(url, data=data, headers={
            'User-Agent': 'HabbliveProfileIntegration/1.0',
            'Accept': 'text/html',
            **({'Content-Type': 'application/x-www-form-urlencoded', 'Referer': BASE} if data is not None else {}),
        })
        try:
            with self.opener.open(request, timeout=8) as response:
                raw = response.read(LIMIT + 1)
                if len(raw) > LIMIT:
                    raise UpstreamError('UPSTREAM_RESPONSE_TOO_LARGE')
                html = raw.decode('utf-8', errors='replace')
                if any(marker in html.lower() for marker in ('cf-chl-', 'challenges.cloudflare.com', 'g-recaptcha', 'h-captcha', '<title>just a moment')):
                    raise UpstreamError('INTERACTIVE_VERIFICATION_REQUIRED', 503)
                return html
        except HTTPError as error:
            # Nunca retornar corpo, cabeçalhos, cookies ou exceções do provedor.
            if error.code in (403, 429, 503):
                raise UpstreamError('UPSTREAM_BLOCKED_OR_RATE_LIMITED', 503) from None
            raise UpstreamError('UPSTREAM_HTTP_ERROR') from None
        except (URLError, TimeoutError, OSError):
            raise UpstreamError('UPSTREAM_UNAVAILABLE', 503) from None

    def login(self):
        if time.monotonic() < self.login_after:
            raise UpstreamError('LOGIN_COOLDOWN', 503)
        username = os.environ.get('HABBLIVE_USERNAME', '')
        password = os.environ.get('HABBLIVE_PASSWORD', '')
        if not username or not password:
            raise UpstreamError('HABBLIVE_CREDENTIALS_NOT_CONFIGURED', 503)
        # Limita tentativas nesta instância, inclusive quando a autenticação falha.
        self.login_after = time.monotonic() + 60
        self.reset()
        form = login_form(self.request(BASE))
        if form is None:
            raise UpstreamError('LOGIN_FORM_CHANGED')
        action = urljoin(BASE, form.attrs.get('action') or BASE)
        if not trusted(action):
            raise UpstreamError('UNEXPECTED_LOGIN_REDIRECT')
        inputs = [n for n in form.walk() if n.tag == 'input']
        names = {n.attrs.get('name') for n in inputs}
        if not {'username', 'password'} <= names:
            raise UpstreamError('LOGIN_FORM_CHANGED')
        fields = {n.attrs['name']: n.attrs.get('value', '') for n in inputs
                  if n.attrs.get('type') == 'hidden' and n.attrs.get('name')}
        fields.update(username=username, password=password)
        for n in form.walk():
            if n.tag == 'button' and n.attrs.get('name') and n.attrs.get('type', 'submit') == 'submit':
                fields[n.attrs['name']] = n.attrs.get('value', '')
                break
        response = self.request(action, fields)
        if login_form(response) is not None:
            raise UpstreamError('HABBLIVE_LOGIN_FAILED', 503)

    def lookup(self, username, page=1):
        if not isinstance(username, str) or not 1 <= len(username) <= 25 or re.search(r'[\x00-\x20\x7f/?#\\]', username):
            raise UpstreamError('INVALID_USERNAME', 400)
        if not isinstance(page, int) or not 1 <= page <= 100:
            raise UpstreamError('INVALID_BADGE_PAGE', 400)
        with self.lock:
            now = time.monotonic()
            key = (username.casefold(), page)
            cached = self.cache.get(key)
            if cached and cached[0] > now:
                return copy.deepcopy(cached[1])
            if self.opener is None or now > self.reset_at:
                self.reset()
            url = BASE + 'perfil?' + urlencode({'user': username, 'badge_page': page})
            html = self.request(url)
            if login_form(html) is not None:
                self.login()
                html = self.request(url)
                if login_form(html) is not None:
                    raise UpstreamError('HABBLIVE_SESSION_REJECTED', 503)
            try:
                profile = parse_payload({'html': html})
            except (ValueError, RecursionError):
                raise UpstreamError('PROFILE_NOT_FOUND_OR_PAGE_CHANGED', 502) from None
            if profile['username'].casefold() != username.casefold():
                raise UpstreamError('PROFILE_MISMATCH', 502)
            profile['requested_badge_page'] = page
            self.cache[key] = (time.monotonic() + 60, copy.deepcopy(profile))
            self.cache.move_to_end(key)
            while len(self.cache) > 64:
                self.cache.popitem(last=False)
            return profile


client = HabbliveClient()
