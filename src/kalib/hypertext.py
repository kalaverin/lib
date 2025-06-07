from collections import defaultdict
from contextlib import suppress
from enum import EnumMeta, IntEnum
from functools import wraps
from http import HTTPStatus
from http.cookies import SimpleCookie
from inspect import iscoroutine
from pathlib import Path
from re import split, sub
from typing import ClassVar

from kalib.dataclass import dataclass
from kalib.datastructures import Encoding, json, loads, pack, serializer, unpack
from kalib.descriptors import Property, cache, parent_call
from kalib.importer import optional, required, sort
from kalib.internals import Is, Who
from kalib.loggers import Logging
from kalib.misc import lazy_proxy_to
from kalib.text import Str


def build_enumerate(name, *order):
    if not isinstance(name, str):
        msg = (
            f'first arg, class name of build_enumerate() '
            f'must be string, not {Who(name)}')
        raise TypeError(msg)

    types = tuple(set(map(type, order)))

    if len(types) != 1:
        msg = f"isn't implemented mixed attributes order: {types!r}"
        raise ValueError(msg)

    if len(order) == 1 and types[0] is dict:
        order = order[0]

    elif types[0] is tuple:

        def titler(code, phrase):
            order = phrase.split(' ')
            if code // 100 >= 6:  # noqa: PLR2004
                order = [name.upper(), *order]
            return '_'.join(map(str.upper, order))

        order = {
            titler(code, phrase):
            (code, phrase, description)
            for code, phrase, description in order}

    elif issubclass(types[0], EnumMeta):
        result = {}
        for klass in order:
            for i in klass:
                value = getattr(klass, i.name)
                if i.name in order:
                    raise ValueError

                result[i.name] = value.value, value.phrase, value.description
        order = result

    else:
        msg = f"make enum from {types[0]!r} isn't implemented"
        raise ValueError(msg)

    class Special(dict):
        @Property.Cached
        def _member_names(self):
            return tuple(filter(lambda x: not x.startswith('_'), self))

    def __new__(cls, value, phrase, description=''):  # noqa: N807
        obj = int.__new__(cls, value)
        obj._value_ = value

        obj.phrase = phrase
        obj.description = description
        return obj

    order['__new__'] = __new__

    return type(name, (IntEnum,), Special(order))


HTTPStatus = build_enumerate(
    'HTTPStatus', {
        i.name: (i.value, i.phrase) + ((i.description,)
        if i.description else ()) for i in HTTPStatus})

CloudFlare = build_enumerate(
    'CloudFlare',
    (520, 'Cloudflare Unknown Error', 'Web server returns an Unknown Error'),
    (521, 'Cloudflare Server Down', 'Web server is down'),
    (522, 'Cloudflare Connection Timeout', 'Connection timed out'),
    (523, 'Cloudflare Unreachable', 'Origin is unreachable'),
    (524, 'Cloudflare Timeout', 'A timeout occurred'),
    (525, 'Cloudflare Handshake Failed', 'SSL handshake failed'),
    (526, 'Cloudflare Invalid Certificate', 'Invalid SSL certificate'),
    (527, 'Cloudflare Railgun Error', 'Railgun Listener to origin error'))

Database = build_enumerate(
    'Database',
    (600, 'General Failure', 'Common error'),
    (601, 'Bad Scheme', 'Broken or incompatible scheme'),
)

Crawling = build_enumerate(
    'Crawling',
    (700, 'General Failure', 'Common error'),
    (701, 'Mitigation Hit', 'Cloudflare challenge mitigation received'),
    (702, 'Temporary Unavailable', 'Resource temporary unavailable'),
    (703, 'Still Processing', 'Resource temporary unavailable: video compressing, etc'),
    (704, 'Need Reparse', 'Resource unavailable: need to reparse'),
    (705, 'Restricted', 'Resource unavailable: under age banner'),
    (706, 'Missing Data', 'Resource unavailable: missing fields, migration issues, etc'),
    (707, 'Need Subscription', 'Resource unavailable: paywall, need account, etc'),
    (708, 'Regional Restrictions', 'Resource unavailable for current region'),
    (709, 'No Valid Source', 'Resource unavailable: no valid video format'),
    (710, 'Broken Data', 'Resource unavailable: bad bitstream, failed transfer, etc'),
    (711, 'Missing Required Data',
          'Resource unavailable: missing required data, e.g. duration'),
)

HTTP = build_enumerate(
    'HTTP', HTTPStatus, CloudFlare, Database, Crawling)


class MimeType(dataclass):

    type : str | None
    text : str | None


class ResponseInternals(dataclass):

    url: str | \
        optional('yarl.URL', default=str) | \
        optional('httpx.URL', default=str)

    status  : int
    reason  : str | None  # can be None for disk cache
    headers : dict[str, str]
    content : bytes | Path  # can be path for disk cache


def bind_main_classes_as_property(cls):
    for code, exception in cls.exceptions.items():
        if code < 100:  # noqa: PLR2004
            setattr(cls, cls.RFC9110[code], exception)
    return cls


class HTTPResponse(Logging.Mixin):

    @classmethod
    def read(cls, response, /, **kw):

        if (
            isinstance(response, dict) and
            isinstance(response.get('headers'), Path) and
            isinstance(response.get('content'), Path)
        ):
            return FileResponse._read(response, response.get('url'), **kw)  # noqa: SLF001

        if iscoroutine(response):
            msg = f"can't process {response=}, it's coroutine, await it first"
            raise RuntimeError(msg)

        order = {
            HTTPxResponse    : 'httpx.Response',
            RequestsResponse : 'requests.models.Response',
            AioHttpResponse  : 'aiohttp.client_reqrep.ClientResponse'}

        for backend, path in order.items():
            with suppress(ImportError):
                if isinstance(response, required(path, quiet=True)):
                    return backend._read(response, **kw)  # noqa: SLF001

        raise NotImplementedError(f"{Who.Is(response)} isn't implemented")

    # common interface

    def __init__(self, response, content):
        self._raw = response
        self._content = content

    @Property.Cached
    def _headers(self):
        result = defaultdict(list)
        for key, value in self._raw.headers.items():
            result[key].append(value)
        return {
            k: tuple(v) if len(v) > 1 else v[0] for k, v in result.items()}

    @Property.Cached
    def _response_params(self):
        return {
            'url'     : self._raw.url,
            'reason'  : self._raw.reason,
            'headers' : self._headers,
            'content' : self._content}

    @Property.Cached
    def _response(self):
        return ResponseInternals.load(self._response_params)

    @Property.Cached
    def ok(self):
        return not self.exception.not_ok

    # just mapping to common internal structure

    @Property.Cached
    def url(self):
        return str(self._response.url)

    @Property.Cached
    def status(self):
        return int(self._response.status)

    @Property.Cached
    def reason(self):
        if (reason := self._response.reason):
            return reason

        reason = HTTPException.Statuses[self.status]
        return f'{reason.phrase}: {reason.description}'

    @Property.Cached
    def headers(self):
        return self._response.headers

    @Property.Cached
    def headerstring(self):
        return json.repr(self.headers)

    @Property.Cached
    def content(self):
        return self._response.content

    @Property.Cached
    def exception(self):
        return HTTPException.by_code(self.status)

    @Property.Cached
    def mime(self):
        msg = (
            f"could't detect mime-type for {self.url!r} response: "
            f'{self.headerstring}: {self.content!r}')

        if not self.content:
            self.log.verbose(msg)
            return MimeType.load({})

        try:
            if (mime := Str(self.content).mime):
                result = MimeType.load(mime)
            else:
                self.log.verbose(msg)
                return MimeType.load({})

        except Exception:
            self.log.exception(msg)
            raise

        self.log.debug(
            f"mime-type for {self.url!r} is {result.type!r}, it's {result.text!r} ")
        return result

    # content related properties

    @Property.Cached
    def bytes(self):
        return Str.to_bytes(self.content)

    @Property.Cached
    def text(self):
        return Str.to_str(self.content)

    @Property.Cached
    def feed(self):
        return required('feedparser.parse')(self.content)

    @Property.Cached
    def json(self):
        return json.loads(self.content)

    @Property.Cached
    def html(self):
        return required('lxml.html.document_fromstring')(self.content)

    @Property.Cached
    def pack(self):
        return required('msgpack.loads')(self.content, encoding='utf-8', use_list=False)

    @Property.Cached
    def xml(self):
        return required('lxml.etree').fromstring(self.content)

    # header-based mapping

    decoders = {  # noqa: RUF012

        # feedparser
        'application/atom+xml'  : 'feed',
        'application/rdf+xml'   : 'feed',
        'application/x-rss+xml' : 'feed',
        'text/x-opml'           : 'feed',
        'application/rss+xml'   : 'feed',

        # lxml html
        'application/xhtml+xml' : 'html',
        'text/html'             : 'html',

        # lxml xml
        'application/xml'       : 'xml',
        'application/rsd+xml'   : 'xml',
        'text/xml'              : 'xml',
        'xml'                   : 'xml',

        # other default types
        'application/json'      : 'json',
        'application/x-msgpack' : 'pack',
        'text/plain'            : 'text',
    }

    @Property.Cached
    def content_type(self):
        def getter(x):
            with suppress(KeyError):
                return self.headers.get(x, '').lower().split(';', 1)[0].strip()

        for header in ('Content-Type', 'content-type'):
            if (content_type := getter(header)):
                return content_type

    @Property.Cached
    def data(self):

        @cache
        def get_message(reason):
            return f'{reason} for {self.url!r} response ({self.headerstring})'

        try:
            content_type = self.content_type
            method = self.decoders[content_type]

        except KeyError:
            message = get_message("couldn't select callback")
            self.log.warning(f'try {content_type=}, {message}')

            try:
                content_type = mime_type = self.mime.type
                method = self.decoders[mime_type]
            except Exception:
                self.log.exception(f'try {mime_type=}, {message}')
                raise

        try:
            return getattr(self, method)

        except Exception:
            message = get_message(
                f'something went wrong on {method=}')
            self.log.exception(f'by {content_type=}, {message}')
            raise


class AioHttpResponse(HTTPResponse):

    @classmethod
    async def _read(cls, response, /, **kw):
        return HTTPException.catch(
            cls(response, content=await response.read()), **kw)

    @Property.Cached
    @parent_call
    def _response_params(self, parent):
        return parent | {'status': self._raw.status}


class RequestsResponse(HTTPResponse):

    @classmethod
    def _read(cls, response, /, **kw):
        return HTTPException.catch(
            cls(response, content=response.content), **kw)

    @Property.Cached
    @parent_call
    def _response_params(self, parent):
        return parent | {'status': self._raw.status_code}


class HTTPxResponse(HTTPResponse):

    @classmethod
    def _read(cls, response, /, **kw):
        return HTTPException.catch(
            cls(response, content=response.content), **kw)

    @Property.Cached
    def _response_params(self):
        return {
            'url'     : self._raw.url,
            'content' : self._content,
            'headers' : self._headers,
            'reason'  : self._raw.reason_phrase,
            'status'  : self._raw.status_code,
        }


class FileResponse(HTTPResponse):

    @classmethod
    def _read(cls, data, url=None, /, **kw):
        with data['headers'].open('rb') as fd:
            headers = json.loads(fd.read())

        self = cls(headers, content=data['content'])
        if url := (headers.get('url') or url):
            headers['url'] = url
        else:
            raise ValueError(f"can't get url from {headers=}")
        return HTTPException.catch(self, **kw)

    @Property.Cached
    def _headers(self):
        headers = dict(self._raw)
        del headers['status']
        del headers['url']
        return headers

    @Property.Cached
    def _response_params(self):
        headers = dict(self._raw)
        return {
            'url'     : headers['url'],
            'status'  : headers['status'],
            'headers' : self._headers,
            'content' : self._content,
            'reason'  : None,
        }

    @Property.Cached
    def content(self):
        with self._content.open('rb') as fd:
            return fd.read()


@lazy_proxy_to('state', 'description', 'phrase', 'value', Property.Class.Cached)
@bind_main_classes_as_property
class HTTPException(Exception, Logging.Mixin):  # noqa: N818

    RFC9110: ClassVar[dict] = {
        1: 'Information',
        2: 'Successful',
        3: 'Redirection',
        4: 'Client',
        5: 'Server',
        6: 'Database',
        7: 'Crawling',
    }
    Statuses: ClassVar[dict] = {int(x.value): x for x in HTTP}

    @staticmethod
    def scream_to_snake(text):
        return sub(
            r'((^[a-z])|(_[a-z]))',
            lambda x: x.group(1)[-1].upper(), text.lower())

    @Property.Class.Parent
    def exceptions(cls):
        @cache
        def make_parent_class(no):
            prefix = 'HTTP' if no <= 5 else ''  # noqa: PLR2004
            return type(f'{prefix}{cls.RFC9110[no]}Error', (cls,), {})

        result = {}
        classes = [[], []]

        for status in HTTP:
            offset = status.value // 100
            section = cls.RFC9110[offset]
            name = sub(r'(Error)$', '', cls.scream_to_snake(status.name))

            parent = make_parent_class(offset)
            if offset not in result:
                result[offset] = parent
                classes[offset >= 3].append(parent)  # noqa: PLR2004
                setattr(HTTP, section, parent)

            root = HTTP if offset in (2, 3) else parent
            if offset > 5:  # noqa: PLR2004
                prefix = ''
            elif offset in (2, 3):
                prefix = 'HTTP'
            else:
                prefix = f'HTTP{section}'

            postfix = 'Error' if offset >= 4 else ''  # noqa: PLR2004
            result[status.value] = type(
                f'{prefix}{name}{postfix}', (parent,), {'state': status})

            short = name.removeprefix(section)
            setattr(root, short, result[status.value])

        cls.Allright = tuple(classes[0])
        cls.Exception = tuple(classes[1])

        return result

    @Property.Class.Cached
    def not_ok(cls):
        return not issubclass(cls, cls.Allright)

    @classmethod
    def by_code(cls, *status, throw=False):
        if len(status) > 1:
            return tuple(map(cls.by_code, status))
        status = status[0]

        if not isinstance(status, HTTP | HTTPException | int):
            msg = (
                f'status code should be {Who(HTTP)} | '
                f'{Who(HTTPException)} | int, '
                f'but not {Who(status)}')
            raise TypeError(msg)

        if isinstance(status, HTTPException):
            status = status.state.value

        if isinstance(status, int):
            try:
                status = cls.Statuses[status]
            except KeyError:
                cls.log.warning(
                    f'unknown status code in response: '
                    f"couldn't get {Who(cls)}({status})")
                if not throw:
                    return HTTPUnknownStatusError
                raise

        return cls.exceptions[int(status.value)]

    def __init__(self, response):
        self.response = response

    @classmethod
    def catch(cls, response, include=None, exclude=None, handler=None):
        if iscoroutine(response):
            msg = f"can't process {response=}, it's coroutine, await it first"
            raise RuntimeError(msg)

        def to_int(x):
            if issubclass(Is.classOf(x), HTTPException):
                return int(x.value)

            elif isinstance(x, int):
                return x

            raise ValueError(
                f'include/exclude can only contains int | {Who(HTTPException)}, '
                f'not {Who.Is(x)} which passed')

        # always raise included exceptions

        if (include and (
            isinstance(include, int) or issubclass(include, HTTPException)
        )):
            include = (include,)
        include = tuple(map(to_int, include or ()))

        # do not raise excluded exceptions

        if (exclude and (
            isinstance(exclude, int) or issubclass(exclude, HTTPException)
        )):
            exclude = (exclude,)
        exclude = tuple(map(to_int, exclude or ()))

        code = int(response.status)
        if code in (exclude or ()):
            return response

        elif code // 100 >= 4 or code in (include or ()):  # noqa: PLR2004, raise all >=400
            e = cls.by_code(code)(response)
            if handler and (replace := handler(e, response)):
                raise replace
            raise e

        return response

    @Property.Cached
    def args(self):
        return (
            self.response.url,
            self.response.status,
            self.response.reason,
            self.response.headerstring,
            self.response.mime.as_dict if self.response.mime else {},
        )

    @Property.Cached
    def verbose(self):
        response = self.response

        try:
            body = f'{json.repr(response.json)=}'
        except Exception:  # noqa: BLE001
            body = response._response.content  # noqa: SLF001

        try:
            return (
                f'{response.url=}\n'
                f'{json.repr(response.headers)=}\n{body=}')

        except Exception:
            self.log.exception(f'something went wrong with {response=}')
            raise

    def __str__(self):
        return f'{self.response.status:d} {self.response.reason}'


class HTTPUnknownStatusError(HTTPException):
    ...


@lazy_proxy_to('generator', 'random')
class Agent:
    def __init__(self, **kw):
        self._kw = kw
        kw.setdefault('platforms', ('desktop'))

    @Property.Cached
    def generator(self):
        return required('fake_useragent.UserAgent')(**self._kw)

    @property
    def any(self):
        return self.generator.random

    @Property.Class
    def header(cls):
        return {'User-Agent': cls().any}


@lazy_proxy_to('cookies', 'keys', 'values', '__iter__')
class Cookies:
    skip_keys = ('domain', 'expires', 'path')

    @classmethod
    def from_dump(cls, data):
        if data is None:
            return

        elif not isinstance(data, bytes | str):
            msg = f'accept only bytes | str as data, not {Who.Is(data)}'
            cls.log.fatal(msg)
            raise TypeError(msg)

        decoded = unpack(data) or loads(data)
        if not decoded:
            msg = f"couldn't interpret received {data=}"
            cls.log.fatal(msg)
            raise ValueError(msg)

        return cls(decoded)

    @classmethod
    def from_env(cls, key):
        if key is None:
            return

        elif not isinstance(key, bytes | str):
            msg = (
                f'accept only bytes | str as environment '
                f'variable key, not {Who.Is(key)}')
            cls.log.fatal(msg)
            raise TypeError(msg)

        data = required('environment.env').str(key, None)
        if not data:
            cls.log.verbose(f"failed, {key=} isn't exists or empty", once=True)
            return

        self = cls.from_dump(data)
        self.log.verbose(f'{key=} got {self.as_json}', once=True)
        return self

    @classmethod
    def from_file(cls, path):
        if path is None:
            return

        elif not isinstance(path, bytes | str):
            msg = (
                f'accept only bytes | str as filesystem '
                f'path, not {Who.Is(path)}')
            cls.log.fatal(msg)
            raise TypeError(msg)

        path = Path(path)
        if not path.is_file():
            cls.log.verbose(f"failed, {path=} isn't exists or accessible")
            return

        with path.open('r+b') as fd:
            self = cls(fd.read())

        path = str(path)
        self.log.verbose(f'{path=} got {self.as_json}', once=True)
        return self

    def __init__(self, raw):
        self._raw = raw

    def __bool__(self):
        return bool(self.as_data)

    def __repr__(self):
        return f'<{self.selfname}: {self.as_json}>'

    @classmethod
    def iterstrings(cls, iterable):
        yield from filter(bool, map(str.strip, iterable))

    def iterraw(self):
        raw = self._raw

        if isinstance(raw, bytes | str):
            lines = Str.to_ascii(raw).split('\n')

        elif isinstance(raw, SimpleCookie):
            lines = [i.OutputString() for i in raw.values()]

        elif isinstance(raw, optional('aiohttp.CookieJar')):
            lines = [i.OutputString() for i in raw]

        else:
            lines = list(raw)
            self.log.debug(f'try to iterate over {Who.Is(lines)}')

        yield from self.iterstrings(lines)

    @Property.Cached
    def cookies(self):
        def iter_tokens():
            for line in self.iterraw():
                yield from self.iterstrings(line.split(';'))

        def iter_values():
            for line in iter_tokens():
                match = split(r'([\s=]+)', line, maxsplit=1)
                if len(match) == 3 and match[0] not in self.skip_keys:  # noqa: PLR2004
                    yield f'{match[0]}={match[2]}'

        cookie = None
        result = SimpleCookie()

        for line in sort(iter_values()):
            cookie = f'{cookie}; {line}' if cookie else line
            if len(cookie) >= 2 ** 10:
                result.load(cookie)
                cookie = None

        if cookie:
            result.load(cookie)

        return result

    @Property.Cached
    def as_data(self):
        return tuple(sort(i.OutputString() for i in self.cookies.values()))

    @Property.Cached
    def as_dict(self):
        return {i.key: i.value for i in self.values()}

    @Property.Cached
    def as_json(self):
        return json.dumps(self.as_data)

    @Property.Cached
    def as_text(self):
        return '\n'.join(self.as_data)

    @Property.Cached
    def as_base(self):
        return pack(self.as_data, codec=Encoding.Base85, encoder='json')[1:]


def proxy_to_super(func):
    @wraps(func)
    def wrapper(self, other):
        return self.load(func(self)(other).as_dict)
    return wrapper


class URL(dataclass):
    scheme   : str
    host     : str | int
    port     : str | int | None = None
    user     : str | None = None
    password : str | None = None
    path     : str | None = '/'
    query    : str = ''
    fragment : str = ''

    @Property.Class.Cached
    def subclass(cls):
        return required('yarl.URL')

    @Property.Class.Cached
    def default_ports(cls):
        return {
            'http'  : 80,
            'ftp'   : 21,
            'ssh'   : 22,
            'https' : 443,
            'amqp'  : 5672,
            'redis' : 6379,
        }

    @classmethod
    def clean_kwargs(cls, config):
        port = config.get('port')

        with suppress(KeyError):
            if config['path'] == '/':
                del config['path']

        if (
            port and
            (isinstance(port, int) or (isinstance(port, str) and port.isdigit())) and
            (port := int(port)) >= 0
        ):
            with suppress(KeyError):
                if cls.default_ports[config['scheme'].lower()] == port:
                    del config['port']

        return {k: v for k, v in config.items() if v}

    @classmethod
    def _preload(cls, config):
        if isinstance(config, str):
            config = cls.subclass(config)

        elif isinstance(config, dict | dict):
            return cls.clean_kwargs(dict(config))

        with suppress(KeyError):
            userattr = {
                'furl.furl.furl' : 'username',
                'yarl.URL'       : 'user',
            }[Who(config)]

            port = config.port or None
            config = {
                'scheme'  : str(config.scheme).lower(),
                'user'    : getattr(config, userattr),
                'password': config.password,
                'host'    : config.host,
                'port'    : port,
                'path'    : str(config.path or ''),
                'query'   : config.query_string or '',
                'fragment': config.fragment or ''}

            return cls.clean_kwargs(config)

        raise TypeError(f'{Who(cls)} unknown input: {Who.Is(config)}')

    @Property.Cached
    def as_dict(self):
        return {
            'scheme'   : self.scheme,
            'user'     : self.user,
            'password' : self.password,
            'host'     : self.host,
            'port'     : self.port,
            'path'     : self.path,
            'query'    : self.query,
            'fragment' : self.fragment}

    @Property.Cached
    def url(self):
        return self.subclass.build(**self.as_dict)

    def __str__(self):
        return str(self.url)

    @proxy_to_super
    def __and__(self):  # noqa: PLE0302
        return super().__and__

    @proxy_to_super
    def __xor__(self):  # noqa: PLE0302
        return super().__xor__

    @proxy_to_super
    def __sub__(self):  # noqa: PLE0302
        return super().__sub__

    @proxy_to_super
    def __or__(self):  # noqa: PLE0302
        return super().__or__

    @proxy_to_super
    def __add__(self):  # noqa: PLE0302
        return super().__add__

# make all exceptions for easy imports at start time


for exception in HTTPException.exceptions.values():
    locals()[exception.__name__] = exception

@serializer(HTTPException)
def from_http(something):
    return something.state.value


HTTP.URL = URL
HTTP.Agent = Agent
HTTP.Catch = HTTPResponse.read
HTTP.Exception = HTTPException
