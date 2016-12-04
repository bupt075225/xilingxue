#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
一个简单、轻量级的WEB框架
"""

import sys
import os
import threading
import re
import cgi
import urllib
import logging
import time
import datetime
import mimetypes
import types
import functools
import traceback

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class Dict(dict):
    """
    字典类，用访问类成员属性的方式访问字典成员
    >>> from transwarp.web import Dict
    >>> d1 = Dict()
    >>> d1['x'] = 100
    >>> d1.x
    100
    >>> d1.y = 200
    >>> d1['y']
    200
    >>> d2 = Dict(a=1, b=2, c='3')
    >>> d2.c
    '3'
    >>> d2['empty']
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    KeyError: 'empty'
    >>> d2.empty
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "/home/lc/webService/www/transwarp/web.py", line 27, in __getattr__
         except keyError:
    NameError: global name 'keyError' is not defined
    >>> d3 = Dict(('a', 'b', 'c'), (1,2,3))
    >>> d3.a
    1
    >>> d3.b
    2
    >>> d3.c
    3
    >>>
    """

    def __init__(self, names=(), values=(), **kv):
        super(Dict, self).__init__(**kv)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except keyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

_TIMEDELTA_ZERO = datetime.timedelta(0)

# 时区样式：UTC+8:00, UTC-10:00
_RE_TZ = re.compile('^([\+\-])([0-9]{1,2})\:([0-9]{1,2})$')

class UTC(datetime.tzinfo):
    """
    UTC时区对象
    >>> from transwarp.web import UTC
    >>> tz0 = UTC('+00:00')
    >>> tz0.tzname(None)
    'UTC+00:00'
    >>> tz8 = UTC('+8:00')
    >>> tz8.tzname(None)
    'UTC+8:00'
    >>> tz7 = UTC('+7:30')
    >>> tz7.tzname(None)
    'UTC+7:30'
    >>> tz5 = UTC('-05:30')
    >>> tz5.tzname(None)
    'UTC-05:30'
    """

    def __init__(self, utc):
        utc = str(utc.strip().upper())
        mt = _RE_TZ.match(utc)
        if mt:
            minus = mt.group(1)=='-'
            h = int(mt.group(2))
            m = int(mt.group(3))
            if minus:
                h, m = (-h), (-m)
            self._utcoffset = datetime.timedelta(hours=h, minutes=m)
            self._tzname = 'UTC%s' % utc
        else:
            raise ValueError('bad utc time zone')

    def utcoffset(self, dt):
        return self._utcoffset

    def dst(self, dt):
        return _TIMEDELTA_ZERO

    def tzname(self, dt):
        return self._tzname

    def __str__(self):
        return 'UTC tzinfo object (%s)' % self._tzname

    __repr__ = __str__



_RESPONSE_STATUSES = {
    # Informational
    100: 'Continue',
    101: 'Switching Protocols',
    102: 'Processing',
    
    # Successful
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi Status',
    226: 'IM Used',
    
    # Redirection
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',

    # Client Error
    400: 'Bad Request',
    401: 'Unauthrized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    418: "I'm a teapot",
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    426: 'Upgrade Required',

    # Server Error
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    507: 'Insufficient Storage',
    510: 'Not Extended'
}

_RE_RESPONSE_STATUS = re.compile(r'^\d\d\d(\ [\w\ ]+)?$')

_RESPONSE_HEADERS = (
    'Accept-Ranges',
    'Age',
    'Allow',
    'Cache-Control',
    'Connection',
    'Content-Encoding',
    'Content-Language',
    'Content-Length',
    'Content-Location',
    'Content-MD5',
    'Content-Disposition',
    'Content-Range',
    'Content-Type',
    'Date',
    'ETag',
    'Expires',
    'Last-Modified',
    'Link',
    'Pragma',
    'Proxy-Authenticate',
    'Refresh',
    'Retry-After',
    'Server',
    'Set-Cookie',
    'Strict-Transport-Security',
    'Trailer',
    'Transfer-Encoding',
    'Vary',
    'Via',
    'Warning',
    'WWW-Authenticate',
    'X-Frame-Options',
    'X-XSS-Protection',
    'X-Content-Type-Options',
    'X-Forwarded-Proto',
    'X-Power-By',
    'X-UA-Compatible',
)

_RESPONSE_HEADER_DICT = dict(zip(map(lambda x: x.upper(), _RESPONSE_HEADERS), _RESPONSE_HEADERS))

_HEADER_X_POWERED_BY = ('X-Powered-By', 'transwarp/1.0')

# 全局ThreadLocal对象,用来保存请求和响应
ctx = threading.local()

# HTTP错误类
class HttpError(Exception):
    """
    >>> e = HttpError(200)
    >>> e.status
    '200 OK'
    """

    def __init__(self, code):
        super(HttpError, self).__init__()
        self.status = '%d %s' % (code, _RESPONSE_STATUSES[code])

    def header(self, name, value):
        if not hasattr(self, '_headers'):
            self._headers = [_HEADER_X_POWERED_BY]
        self._headers.append((name, value))

    @property
    def header(self):
        if hasattr(self, '_headers'):
            return self._headers
        return []

    def __str__(self):
        return self.status

    __repr__ = __str__

class RedirectError(HttpError):
    """
    用响应错误码初始化HttpError
    >>> e = RedirectError(301, 'http://www.apple.com')
    >>> e.status
    '301 Moved Permanently'
    >>> e.location
    'http://www.apple.com'
    """

    def __init__(self, code, location):
        super(RedirectError, self).__init__(code)
        self.location = location

    def __str__(self):
        return '%s, %s' % (self.status, self.location)

    __repr__ = __str__

def badrequest():
    """
    >>> from transwarp.web import HttpError
    >>> from transwarp.web import badrequest
    >>> raise badrequest()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    transwarp.web.HttpError: 400 Bad Request
    """
    return HttpError(400)


def unauthorized():
    """
    发送一个未授权错误的响应

    >>> from transwarp.web import HttpError
    >>> from transwarp.web import unauthorized
    >>> raise unauthorized()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      transwarp.web.HttpError: 401 Unauthrized

    """

    return HttpError(401)

def forbidden():
    """
    >>> from transwarp.web import HttpError
    >>> from transwarp.web import forbidden
    >>> raise forbidden()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    transwarp.web.HttpError: 403 Forbidden
    """

    return HttpError(403)

def notfound():
    return HttpError(404)

def conflict():
    return HttpError(409)
    
def internalerror():
    return HttpError(500)

def redirect(location):
    return RedirectError(301, location)

def found(location):
    return RedirectError(302, location)

def seeother(location):
    return RedirectError(303, location)


def _to_str(s):
    """
    >>> from transwarp.web import _to_str
    >>> _to_str('s123') == 's123'
    True
    >>> _to_str(u'\u4e2d\u6587') == '\xe4\xb8\xad\xe6'
    False
    >>> _to_str(u'\u4e2d\u6587') == '\xe4\xb8\xad\xe6\x96\x87'
    True
    >>> _to_str(-123) == '-123'
    True
    """

    if isinstance(s, str):
        return s
    if isinstance(s, unicode):
        return s.encode('utf-8')

    return str(s)

def _to_unicode(s, encoding='utf-8'):
    """
    转为utf-8编码
    >>> from transwarp.web import _to_unicode
    >>> _to_unicode('\xe4\xb8\xad\xe6\x96\x87') == u'\u4e2d\u6587'
    True
    """

    return s.decode('utf-8')

def _quote(s, encoding='utf-8'):
    """
    将utf-8编码的字符串中的特殊字符(除字母，数字和_ . -)替换成%xx
    >>> from transwarp.web import _quote
    >>> _quote('http://example/test?a=1+')
    'http%3A//example/test%3Fa%3D1%2B'
    >>> _quote(u'hello world!')
    'hello%20world%21'
    """
    if isinstance(s, unicode):
        s = s.encode(encoding)

    return urllib.quote(s)

def _unquote(s, encoding='utf-8'):
    """
    >>> from transwarp.web import _unquote
    >>> _unquote('http%3A//example/test%3Fa%3D1%2B')
    u'http://example/test?a=1+'
    """
    return urllib.unquote(s).decode(encoding)

def get(path):
    """
    @get 装饰器
    >>> from transwarp.web import get
    >>> @get('/test/:id')
    ... def test():
    ...     return 'ok'
    ... 
    >>> test.__web_method__
    'Get'
    >>> test.__web_route__
    '/test/:id'
    >>> test()
    'ok'
    """

    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'GET'
        return func

    return _decorator

def post(path):
    """
    @post 装饰器
    >>> from transwarp.web import post
    >>> @post('/post/:id')
    ... def testpost():
    ...     return '200'
    ... 
    >>> testpost.__web_route__
    '/post/:id'
    >>> testpost.__web_method__
    'POST'
    >>> testpost()
    '200'
    """

    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'POST'
        return func

    return _decorator

_re_route = re.compile(r'(\:[a-zA-Z]\w*)')

def _build_regex(path):
    """
    将路由路径转化为正则表达式
    >>> from transwarp.web import _build_regex
    >>> _build_regex('/path/to/:file')
    '^\\/\\p\\a\\t\\h\\/\\t\\o\\/(?P<file>[^\\/]+)$'
    >>> _build_regex('/:user/:comments/list')
    '^\\/(?P<user>[^\\/]+)\\/(?P<comments>[^\\/]+)\\/\\l\\i\\s\\t$'
    >>> _build_regex(':id-:pid/:w')
    '^(?P<id>[^\\/]+)\\-(?P<pid>[^\\/]+)\\/(?P<w>[^\\/]+)$'
    """

    re_list = ['^']
    var_list = []
    is_var = False

    for v in _re_route.split(path):
        if is_var:
            var_name = v[1:]
            var_list.append(var_name)
            re_list.append(r'(?P<%s>[^\/]+)' % var_name)
        else:
            s = ''
            for ch in v:
                if ch>='0' and ch<='9':
                    s = s + ch
                elif ch>='A' and ch<='Z':
                    s = s + ch
                elif ch>='a' and ch<='z':
                    s = s + ch
                else:
                    s = s + '\\' + ch
            re_list.append(s)
        is_var = not is_var

    re_list.append('$')
    return ''.join(re_list)

class Route(object):
    '''
    记录URL与后台处理函数的映射信息
    '''
    def __init__(self, func):
        self.path = func.__web_route__
        self.method = func.__web_method__
        self.is_static = _re_route.search(self.path) is None
        
        if not self.is_static:
            self.route = re.compile(_build_regex(self.path))

        self.func = func

    def match(self, url):
        m = self.route.match(url)
        if m:
            return m.groups()
        return None

    def __call__(self, *args):
        return self.func(*args)
    
    def __str__(self):
        if self.is_static:
            return 'Route(static,%s,path=%s)' % (self.method, self.path)

        return 'Route(dynamic,%s,path=%s)' % (self.method, self.path)

    __repr__ = __str__

def _static_file_generator(fpath):
    BLOCK_SIZE = 8192

    with open(fpath, 'rb') as f:
        block = f.read(BLOCK_SIZE)
        while block:
            yield block
            block = f.read(BLOCK_SIZE)

class StaticFileRoute(object):
    def __init__(self):
        self.method = 'GET'
        self.is_static = False
        self.route = re.compile('^/static/(.+)$')

    def match(self, url):
        if url.startswith('/static/'):
            return (url[1:], )
        return None

    def __call__(self, *args):
        fpath = os.path.join(ctx.application.document_root, args[0])
        if not os.path.isfile(fpath):
            raise notfound()

        fext = os.path.splitext(fpath)[1]
        ctx.response.content_type = mimetypes.types_map.get(fext.lower(), 'application/octet-stream')

        return _static_file_generator(fpath)

def favicon_handler():
    return static_file_handler('/favicon.ico')

class MultipartFile(object):
    def __init__(self, storage):
        self.filename = _to_unicode(storage.filename)
        self.file = storage.file

class Request(object):
    def __init__(self, environ):
        self._environ = environ

    def _parse_input(self):
        def _convert(item):
            if isinstance(item, list):
                return [_to_unicode(i.value) for i in item]

            if item.filename:
                return MultipartFile(item)

            return _to_unicode(item.value)

        fs = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
        inputs = dict()
        for key in fs:
            inputs[key] = _convert(fs[key])
        return inputs

    def _get_raw_input(self):
        if not hasattr(self, '_raw_input'):
            self._raw_input = self._parse_input()

        return self._raw_input

    def __getitem__(self, key):
        """
        获取属性的值
        如果有多个值，只返回第一个值
        如果属性不存在，返回KeyError
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> r['a']
        u'1'
        >>> r['c']
        u'ABC'
        >>> r['empty']
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/lc/webService/www/transwarp/web.py", line 277, in __getitem__
            r = self._get_raw_input()[key]
        KeyError: 'empty'
        """
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[0]

        return r

    def get(self, key, default=None):
        """
        与request[key]功能一样
        如果属性不存，返回给定的默认值
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M8c=ABC&c=XYZ&e=')})
        >>> r.get('a')
        u'1'
        >>> r.get('empty')
        >>> r.get('empty', 'DEFAULT')
        'DEFAULT'
        """
        r = self._get_raw_input().get(key, default)
        if isinstance(r, list):
            return r[0]

        return r

    def gets(self, key):
        """
        获取给定属性的多个值
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> r.gets('a')
        [u'1']
        >>> r.gets('c')
        [u'ABC', u'XYZ']
        >>> r.gets('empty')
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/lc/webService/www/transwarp/web.py", line 321, in gets
            r = self._get_raw_input()[key]
        KeyError: 'empty'
        """
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[:]

        return [r]

    def input(self, **kv):
        """
        从http请求中获取属性，以字典的形式返回，如果属性不存在，返回给定的默认值
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ&e=')})
        >>> i = r.input(x=2016)
        >>> i.a
        u'1'
        >>> i.b
        u'M M'
        >>> i.c
        u'ABC'
        >>> i.x
        2016
        >>> i.get('d', u'100')
        u'100'
        >>> i.x
        2016
        """

        copy = Dict(**kv)
        raw = self._get_raw_input()
        for k, v in raw.iteritems():
            copy[k] = v[0] if isinstance(v, list) else v

        return copy

    def get_body(self):
        """
        从HTTP POST请求中获取原始数据，以字符串的形式返回
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('<xml><raw/>')})
        >>> r.get_body()
        '<xml><raw/>'
        """

        fp = self._environ['wsgi.input']
        return fp.read()

    @property
    def remote_addr(self):
        """
        获取客户端IP地址
        如果获取失败，返回0.0.0.0
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'REMOTE_ADDR':'192.168.30.111'})
        >>> r.remote_addr
        '192.168.30.111'
        """

        return self._environ.get('REMOTE_ADDR', '0.0.0.0')

    @property
    def document_root(self):
        """
        如果属性不存在返回''
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'DOCUMENT_ROOT': '/srv/path/doc'})
        >>> r.document_root
        '/srv/path/doc'
        """

        return self._environ.get('DOCUMENT_ROOT', '')

    @property
    def query_string(self):
        """
        如果属性不存在返回''
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'QUERY_STRING': 'a=1&c=2'})
        >>> r.query_string
        'a=1&c=2'
        >>> r = Request({})
        >>> r.query_string
        ''
        """

        return self._environ.get('QUERY_STRING', '')

    @property
    def environ(self):
        """
        以字典形式获取environ
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD': 'GET', 'wsgi.url_scheme':'http'})
        >>> r.environ.get('REQUEST_METHOD')
        'GET'
        >>> r.environ.get('wsgi.url_scheme')
        'http'
        >>> r.environ.get('Server_name')
        >>> r.environ.get('Server_name', 'unamed')
        'unamed'
        """

        return self._environ

    @property
    def request_method(self):
        """
        获取请求方法，GET,POST,HEAD其中之一
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'REQUEST_METHOD':'GET'})
        >>> r.request_method
        'GET'
        >>> r = Request({'REQUEST_METHOD':'POST'})
        >>> r.request_method
        'POST'
        """

        return self._environ['REQUEST_METHOD']

    @property
    def path_info(self):
        """
        获取请求路径
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'PATH_INFO':'/test/a%20b.html'})
        >>> r.path_info
        '/test/a b.html'
        """

        return urllib.unquote(self._environ.get('PATH_INFO', ''))

    @property
    def host(self):
        """
        >>> from transwarp.web import Request
        >>> from StringIO import StringIO
        >>> r = Request({'HTTP_HOST':'localhost:8080'})
        >>> r.host
        'localhost:8080'
        """

        return self._environ.get('HTTP_HOST', '')

    def _get_headers(self):
        if not hasattr(self, '_headers'):
            hdrs = {}
            for k, v in self._environ.iteritems():
                if k.startswith('HTTP_'):
                    hdrs[k[5:].replace('_', '-').upper()] = v.decode('utf-8')

            self._headers = hdrs

        return self._headers

    @property
    def headers(self):
        """
        以请求头部的属性名为关键字，返回unicode编码的值
        >>> from transwarp.web import Request
        >>> r = Request({'HTTP_USER_AGENT':'Mozilla/5.0', 'HTTP_ACCEPT':'text/html'})
        >>> H = r.headers
        >>> H['ACCEPT']
        u'text/html'
        >>> H['USER-AGENT']
        u'Mozilla/5.0'
        >>> L = H.items()
        >>> L.sort()
        >>> L
        [('ACCEPT', u'text/html'), ('USER-AGENT', u'Mozilla/5.0')]
        """

        return dict(**self._get_headers())

    def header(self, header, default=None):
        """
        查询的头部字段不存在，返回None或给定的默认值
        >>> from transwarp.web import Request
        >>> r = Request({'HTTP_USER_AGENT':'Mozilla/5.0', 'HTTP_ACCEPT':'text/html'})
        >>> r.header('User-Agent')
        u'Mozilla/5.0'
        >>> r.header('USER-AGENT')
        u'Mozilla/5.0'
        >>> r.header('Accept')
        u'text/html'
        >>> r.header('Test')
        >>> r.header('Test', u'DEFAULT')
        u'DEFAULT'
        """

        return self._get_headers().get(header.upper(), default)

    def _get_cookies(self):
        if not hasattr(self, '_cookies'):
            cookies = {}
            cookie_str = self._environ.get('HTTP_COOKIE')
            if cookie_str:
                for c in cookie_str.split(';'):
                    pos = c.find('=')
                    if pos>0:
                        cookies[c[:pos].strip()] = _unquote(c[pos+1:])

            self._cookies = cookies

        return self._cookies

    @property
    def cookies(self):
        """
        以字典的形式返回所有cookies，cookies名称是字符串，值是unicode
        >>> from transwarp.web import Request
        >>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
        >>> r.cookies['A']
        u'123'
        >>> r.cookies['url']
        u'http://www.example.com/'
        """

        return Dict(**self._get_cookies())

    def cookie(self, name, default=None):
        """
        >>> from transwarp.web import Request
        >>> r = Request({'HTTP_COOKIE':'A=123; url=http%3A%2F%2Fwww.example.com%2F'})
        >>> r.cookie('A')
        u'123'
        >>> r.cookie('url')
        u'http://www.example.com/'
        >>> r.cookie('test')
        >>> r.cookie('test', u'Default')
        u'Default'
        """

        return self._get_cookies().get(name, default)

UTC_0 = UTC('+00:00')

class Response(object):
    def __init__(self):
        self._status = '200 OK'
        self._headers = {'CONTENT-TYPE':'text/html; charset=utf-8'}

    @property
    def headers(self):
        """
        返回响应消息的头部信息列表：[(key1,value1), (key2,value2)...]
        >>> from transwarp.web import Response
        >>> r = Response()
        >>> r.headers
        [('Content-Type', 'text/html; charset=utf-8'), ('X-Powered-By', 'transwarp/1.0')]
        >>> r.set_cookie('s1', 'ok', 3600)
        >>> r.headers
        [('Content-Type', 'text/html; charset=utf-8'), ('Set-Cookie', 's1=ok; Max-Age=3600; Path=/; HttpOnly'), ('X-Powered-By', 'transwarp/1.0')]
        """

        L = [(_RESPONSE_HEADER_DICT.get(k, k), v) for k, v in self._headers.iteritems()]
        if hasattr(self, '_cookies'):
            for v in self._cookies.itervalues():
                L.append(('Set-Cookie', v))

        L.append(_HEADER_X_POWERED_BY)

        return L

    def header(self, name):
        """
        获取响应消息头部字段信息,不区分大小写
        >>> from transwarp.web import Response
        >>> r = Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.header('CONTENT-type')
        'text/html; charset=utf-8'
        >>> r.header('X-Powered-By')
        """

        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name

        return self._headers.get(key)

    def unset_header(self, name):
        """
        通过头部字段名称或值来删除字段
        >>> from transwarp.web import Response
        >>> r = Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.unset_header('CONTENT-type')
        >>> r.header('content-type')
        """

        key = name.upper();
        if not key in _RESPONSE_HEADER_DICT:
            key = name
        if key in self._headers:
            del self._headers[key]

    def set_header(self, name, value):
        """
        通过头部字段名称或值来设置字段
        >>> from transwarp.web import Response
        >>> r = Response()
        >>> r.header('content-type')
        'text/html; charset=utf-8'
        >>> r.set_header('CONTENT-type', 'image/png')
        >>> r.header('content-type')
        'image/png'
        """

        key = name.upper()
        if not key in _RESPONSE_HEADER_DICT:
            key = name

        self._headers[key] = _to_str(value)

    @property
    def content_type(self):
        """
        获取HTML内容的类型，与header函数功能一样
        >>> from transwarp.web import Response
        >>> r = Response()
        >>> r.content_type
        'text/html; charset=utf-8'
        >>> r.content_type = 'application/json'
        >>> r.content_type
        'application/json'
        """

        return self.header('CONTENT-TYPE')

    @content_type.setter
    def content_type(self, value):
        if value:
            self.set_header('CONTENT-TYPE', value)
        else:
            self.unset_header('CONTENT-TYPE')

    @property
    def content_length(self):
        """
        获取HTML内容长度
        如果没设置长度，返回None
        >>> from transwarp.web import Response
        >>> r = Response()
        >>> r.content_length
        >>> r.content_length = 100
        >>> r.content_length
        '100'
        """

        return self.header('CONTENT-LENGTH')

    @content_length.setter
    def content_length(self, value):
        self.set_header('CONTENT-LENGTH', str(value))

    def delete_cookie(self, name):
        """
        删除cookie
        参数name:cookie名称
        """

        self.set_cookie(name, '__deleted__', expires=0)

    def set_cookie(self, name, value, max_age=None, expires=None, path='/', domain=None, secure=False, http_only=True):
        """
        设置cookie
        参数：
            name: cookie名称
            value: cookie值
            max_age: 可选,cookie最大有效时间，以秒为单位
            expires: 可选,cookie过期时间，expires给定后，max_age参数会被忽略
            path: cookie路径，默认为'/'
            domain: 默认是None
            http_only: 

            >>> from transwarp.web import Response,UTC
            >>> import datetime
            >>> r = Response()
            >>> r.set_cookie('company', 'Abc, Inc', max_age=3600)
            >>> r._cookies
            {'company': 'company=Abc%2C%20Inc; Max-Age=3600; Path=/; HttpOnly'}
            >>> r.set_cookie('company', r'Example="Limited"', expires=1342274794.123, path='/sub/')
            >>> r._cookies
            {'company': 'company=Example%3D%22Limited%22; Expires=Sat, 14-Jul-2012 14:06:34 GMT; Path=/sub/; HttpOnly'}
            >>> dt = datetime.datetime(2016, 3, 1, 11, 28, 34, tzinfo=UTC('+8:00'))
            >>> r.set_cookie('company', 'Expires', expires=dt)
            >>> r._cookies
            {'company': 'company=Expires; Expires=Tue, 01-Mar-2016 03:28:34 GMT; Path=/; HttpOnly'}
        """

        if not hasattr(self, '_cookies'):
            self._cookies = {}

        L = ['%s=%s' % (_quote(name), _quote(value))]
        if expires is not None:
            if isinstance(expires, (float, int, long)):
                L.append('Expires=%s' % datetime.datetime.fromtimestamp(expires, UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
            if isinstance(expires, (datetime.date, datetime.datetime)):
                L.append('Expires=%s' % expires.astimezone(UTC_0).strftime('%a, %d-%b-%Y %H:%M:%S GMT'))
        elif isinstance(max_age, (int, long)):
            L.append('Max-Age=%d' % max_age)

        L.append('Path=%s' % path)

        if domain:
            L.append('Secure')

        if http_only:
            L.append('HttpOnly')

        self._cookies[name] = '; '.join(L)

    def unset_cookie(self, name):
        """
        取消cookie设置
        >>> from transwarp.web import Response
        >>> r = Response()
        >>> r.set_cookie('company', 'Abc, Inc.', max_age=3600)
        >>> r._cookies
        {'company': 'company=Abc%2C%20Inc.; Max-Age=3600; Path=/; HttpOnly'}
        >>> r.unset_cookie('company')
        >>> r._cookies
        {}
        """

        if hasattr(self, '_cookies'):
            if name in self._cookies:
                del self._cookies[name]

    @property
    def status_code(self):
        return int(self._status[:3])

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        """
        >>> from transwarp.web import Response
        >>> r = Response()
        >>> r.status_code
        200
        >>> r.status = 404
        >>> r.status
        '404 Not Found'
        >>> r.status = u'403 Denied'
        >>> r.status
        '403 Denied'
        >>> r.status = 99
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/lc/webService/www/transwarp/web.py", line 917, in status
            raise ValueError('Bad response code: %d' % value)
        ValueError: Bad response code: 99
        >>> r.status = 'ok'
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/lc/webService/www/transwarp/web.py", line 924, in status
            raise ValueError('Bad response code: %s' % value)
        ValueError: Bad response code: ok
        >>> r.status = [1,2,3]
        Traceback (most recent call last):
          File "<stdin>", line 1, in <module>
          File "/home/lc/webService/www/transwarp/web.py", line 926, in status
            raise TypeError('Bad type of response code.')
        TypeError: Bad type of response code.
        """

        if isinstance(value, (int, long)):
            if value>=100 and value<=999:
                st = _RESPONSE_STATUSES.get(value, '')
                if st:
                    self._status = '%d %s' % (value, st)
                else:
                    self._status = str(value)
            else:
                raise ValueError('Bad response code: %d' % value)
        elif isinstance(value, basestring):
            if isinstance(value, unicode):
                value = value.encode('utf-8')
            if _RE_RESPONSE_STATUS.match(value):
                self._status = value
            else:
                raise ValueError('Bad response code: %s' % value)
        else:
            raise TypeError('Bad type of response code.')


class Template(object):
    def __init__(self, template_name, **kw):
        """
        初始化一个模板对象
        >>> from transwarp.web import Template
        >>> t = Template('hello.html', title='Hello', copyright='@2012')
        >>> t.model['title']
        'Hello'
        >>> t.model['copyright']
        '@2012'
        >>> t = Template('test.html', abc=u'ABC', xyz=u'XYZ')
        >>> t.model['abc']
        u'ABC'
        """

        self.template_name = template_name
        self.model = dict(**kw)

# 定义模板引擎
class TemplateEngine(object):
    def __call__(self, path, model):
        return '<!-- override this method to render template -->'


class Jinja2TemplateEngine(TemplateEngine):
    def __init__(self, templ_dir, **kv):
        from jinja2 import Environment,FileSystemLoader
        if not 'autoescape' in kv:
            kv['autoescape'] = True

        self._env = Environment(loader=FileSystemLoader(templ_dir), **kv)

    def add_filter(self, name, fn_filter):
        self._env.filters[name] = fn_filter

    def __call__(self, path, model):
        return self._env.get_template(path).render(**model).encode('utf-8')

def _default_error_handler(e, start_response, is_debug):
    if isinstance(e, HttpError):
        logging.info('HttpError: %s' % e.status)
        headers = e.headers[:]
        headers.append(('Content-Type', 'text/html'))
        start_response(e.status, headers)
        return ('<html><body><h1>%s</h1></body></html>' % e.status)

    logging.exception('Exception:')
    start_response('500 Internal Server Error', [('Content-Type', 'text/html'), _HEADER_X_POWERED_BY])

    if is_debug:
        return _debug()

    return ('<html><body><h1>500 Internal Server Error</h1><h3>%s</h3></body></html>' % str(e))

# 定义模板
def view(path):
    """
    view装饰器,装饰出一个模板对象,提供给模板引擎渲染出页面

    >>> from transwarp.web import view
    >>> @view('test/view.html')
    ... def hello():
    ...     return dict(name='Bob')
    ... 
    >>> t = hello()
    >>> from transwarp.web import Template
    >>> isinstance(t, Template)
    True
    >>> t.template_name
    'test/view.html'
    >>> @view('test/view.html')
    ... def hello2():
    ...     return ['a list']
    ... 
    >>> t = hello2()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "/home/lc/webService/www/transwarp/web.py", line 1180, in _wrapper
            raise ValueError('Expect return a dict when using @view() decorator.')
    ValueError: Expect return a dict when using @view() decorator.
    """

    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kv):
            r = func(*args, **kv)
            if isinstance(r, dict):
                logging.info('return Template')
                return Template(path, **r)
            raise ValueError('Expect return a dict when using @view() decorator.')
        return _wrapper
    return _decorator

_RE_INTERCEPTROR_STARTS_WITH = re.compile(r'^([^\*\?]+)\*?$')
_RE_INTERCEPTROR_ENDS_WITH = re.compile(r'^\*([^\*\?]+)$')

def _build_pattern_fn(pattern):
    m = _RE_INTERCEPTROR_STARTS_WITH.match(pattern)
    if m:
        return lambda p: p.startswith(m.group(1))

    m = _RE_INTERCEPTROR_ENDS_WITH.match(pattern)
    if m:
        return lambda p: p.endswith(m.group(1))

    raise ValueError('Invalid pattern definition in inteceptor.')

# 定义拦截器
def interceptor(pattern='/'):
    """
    @interceptor装饰器
    """
    def _decorator(func):
        func.__interceptor__ = _build_pattern_fn(pattern)
        return func

    return _decorator

def _build_interceptor_fn(func, next):
    def _wrapper():
        if func.__interceptor__(ctx.request.path_info):
            return func(next)
        else:
            return next()

    return _wrapper

def _build_interceptor_chain(last_fn, *interceptors):
    """
    构建一个拦截器链

    >>> from transwarp.web import _build_interceptor_fn
    >>> from transwarp.web import _build_interceptor_chain
    >>> def target():
    ...     print 'target'
    ...     return 123
    ... 
    >>> from transwarp.web import interceptor
    >>> @interceptor('/')
    ... def f1(next):
    ...     print 'before f1()'
    ...     return next()
    ... 
    >>> @interceptor('/test/')
    ... def f2(next):
    ...     print 'before f2()'
    ...     try:
    ...             return next()
    ...     finally:
    ...             print 'after f2()'
    ... 
    >>> @interceptor('/')
    ... def f3(next):
    ...     print 'before f3()'
    ...     try:
    ...             return next()
    ...     finally:
    ...             print 'after f3()'
    ... 
    >>> chain = _build_interceptor_chain(target, f1, f2, f3)
    >>> from transwarp.web import Dict
    >>> from transwarp.web import ctx
    >>> ctx.request = Dict(path_info='/test/abc')
    >>> chain()
    before f1()
    before f2()
    before f3()
    target
    after f3()
    after f2()
    123
    >>> ctx.request = Dict(path_info='/api/')
    >>> chain()
    before f1()
    before f3()
    target
    after f3()
    123
    """

    L = list(interceptors)
    L.reverse()
    fn = last_fn
    for f in L:
        fn = _build_interceptor_fn(f, fn)

    return fn

def _load_module(module_name):
    """
    >>> from transwarp.web import _load_module
    >>> m = _load_module('xml')
    >>> m.__name__
    'xml'
    >>> m = _load_module('xml.sax')
    >>> m.__name__
    'xml.sax'
    >>> m = _load_module('xml.sax.handler')
    >>> m.__name__
    'xml.sax.handler'
    """

    last_dot = module_name.rfind('.')
    if last_dot==(-1):
        return __import__(module_name, globals(), locals())

    from_module = module_name[:last_dot]
    import_module = module_name[last_dot+1:]
    m = __import__(from_module, globals(), locals(), [import_module])

    return getattr(m, import_module)

class WSGIApplication(object):
    def __init__(self, document_root=None, **kv):
        self._running = False
        self._document_root = document_root
        self._interceptors = []
        self._template_engine = None

        self._get_static = {}
        self._post_static = {}

        self._get_dynamic = []
        self._post_dynamic = []

    def _check_not_running(self):
        if self._running:
            raise RuntimeError('Cannot modify WSGIApplication when running.')

    @property
    def template_engine(self):
        return self._template_engine

    @template_engine.setter
    def template_engine(self, engine):
        self._check_not_running()
        self._template_engine = engine

    def add_module(self, mod):
        self._check_not_running()
        m = mod if type(mod)==types.ModuleType else _load_module(mod)
        logging.info('Add module: %s' % m.__name__)

        for name in dir(m):
            fn = getattr(m, name)
            if callable(fn) and hasattr(fn, '__web_route__') and hasattr(fn, '__web_method__'):
                self.add_url(fn)

    def add_url(self, func):
        self._check_not_running()
        route = Route(func)
        # Route类初始化对象时会根据请求的URL进行正则匹配来区分出静态或动态
        if route.is_static:
            if route.method=='GET':
                self._get_static[route.path] = route
            if route.method=='POST':
                self._post_static[route.path] = route
        else:
            if route.method=='GET':
                self._get_dynamic.append(route)
            if route.method=='POST':
                self._post_dynamic.append(route)

        logging.info('Add route: %s' % str(route))

    def add_interceptor(self, func):
        self._check_not_running()
        self._interceptors.append(func)
        logging.info('Add interceptor: %s' % str(func))

    def run(self, port=9000, host='127.0.0.1'):
        from wsgiref.simple_server import make_server
        logging.info('application(%s) will start at %s:%s...' % (self._document_root, host, port))
        server = make_server(host, port, self.get_wsgi_application(debug=True))
        server.serve_forever()

    def get_wsgi_application(self, debug=False):
        self._check_not_running()
        if debug:
            self._get_dynamic.append(StaticFileRoute())
        self._running = True

        _application = Dict(document_root=self._document_root)

        def fn_route():
            request_method = ctx.request.request_method
            path_info = ctx.request.path_info
            if request_method=='GET':
                fn = self._get_static.get(path_info, None)
                if fn:
                    return fn()
                for fn in self._get_dynamic:
                    args = fn.match(path_info)
                    if args:
                        return fn(*args)

                raise notfound()

            if request_method=='POST':
                fn = self._post_static.get(path_info, None)
                if fn:
                    return fn()
                for fn in self._post_dynamic:
                    args = fn.match(path_info)
                    if args:
                        return fn(*args)

                raise notfound()

            raise badrequest()

        fn_exec = _build_interceptor_chain(fn_route, *self._interceptors)

        def wsgi(env, start_response):
            ctx.application = _application
            ctx.request = Request(env)
            response = ctx.response = Response()

            try:
                r = fn_exec()
                if isinstance(r, Template):
                    # 模板引擎渲染出最终显示的页面
                    r = self._template_engine(r.template_name, r.model)
                if isinstance(r, unicode):
                    r = r.encode('utf-8')
                if r is None:
                    r = []

                start_response(response.status, response.headers)

                # 返回页面到浏览器
                return r

            except RedirectError, e:
                response.set_header('Location', e.location)
                start_response(e.status, response.headers)
                return []

            except HttpError, e:
                start_response(e.status, response.headers)
                return ['<html><body><h1>', e.status, '</h1></body></html>']

            except Exception, e:
                logging.exception(e)
                if not debug:
                    start_response('500 Internal Server Error', [])
                    return ['<html><body><h1>500 Internal Server Error</h1></body></html>']

                exc_type, exc_value, exc_traceback = sys.exc_info()
                fp = StringIO()
                traceback.print_exception(exc_type, exc_value, exc_traceback, file=fp)
                stacks = fp.getvalue()
                fp.close()
                start_response('500 Internal Server Error', [])
                return [
                    r'''<html><body><h1>500 Internal Server Error</h1><div style="font-family:Monaco, Menlo, Consolas, 'Courier New', monospace;"><pre>''',
                    stacks.replace('<', '&lt;').replace('>', '&gt;'),
                    '</pre></div><body></html>']

            finally:
                del ctx.application
                del ctx.request
                del ctx.response

        return wsgi

if __name__=='__main__':
    sys.path.append('.')
