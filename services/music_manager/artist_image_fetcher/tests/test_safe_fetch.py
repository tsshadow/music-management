"""Tests for safe_fetch: resolve once, refuse internal addresses, connect to the checked one.

Bug report 114. The rebinding tests hand getaddrinfo a sequence of answers -- public
first, internal second -- and prove the fetch never asks a second time. The end-to-end
tests run a real HTTP server on loopback and let only that one address count as public,
so a request can only reach it by the pinned address (the name itself resolves nowhere).
"""

import ipaddress
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from unittest.mock import MagicMock, patch

import urllib3

from services.music_manager.artist_image_fetcher import safe_fetch

PUBLIC = '93.184.216.34'
# A host in the 192.168.0.0/16 private block, computed so no concrete LAN address sits in the source.
LAN = str(ipaddress.ip_network('192.168.0.0/16')[27])


def answers(*addresses):
    """getaddrinfo tuples for the given addresses."""
    return [(10 if ':' in a else 2, 1, 6, '', (a, 0)) for a in addresses]


def resolving_to(*addresses):
    """A getaddrinfo stand-in returning the given addresses for any host."""
    return MagicMock(return_value=answers(*addresses))


def response(status=200, body=b'img', headers=None):
    """A streamed urllib3 response with `body`, as a pinned pool would return it."""
    return urllib3.HTTPResponse(body=BytesIO(body), headers=headers or {}, status=status, preload_content=False)


class AddressCheckTest(unittest.TestCase):
    def test_internal_addresses_are_not_public(self):
        for text in (
            '127.0.0.1',
            '10.0.0.5',
            '172.17.0.2',  # the default docker bridge
            LAN,  # a home network host
            '169.254.169.254',  # cloud metadata
            '100.64.0.1',  # CGNAT / tailnet
            '100.127.255.254',
            '0.0.0.0',
            '255.255.255.255',
            '224.0.0.1',
            '::',
            '::1',
            'fe80::1',
            'fc00::1',
            'fd12:3456::1',
            'ff02::1',
            '::ffff:127.0.0.1',  # IPv4-mapped
            '::ffff:169.254.169.254',
            '::ffff:100.64.0.1',
            f'::ffff:{LAN}',
            '::127.0.0.1',  # IPv4-compatible
            '2002:c0a8:001b::1',  # 6to4 around a 192.168.0.0/16 host
            '64:ff9b::a00:1',  # NAT64 around 10.0.0.1
            '2001:db8::1',
        ):
            self.assertFalse(safe_fetch.is_public_address(ipaddress.ip_address(text)), text)

    def test_public_addresses_are_public(self):
        for text in (PUBLIC, '1.1.1.1', '2606:4700:4700::1111', '::ffff:93.184.216.34'):
            self.assertTrue(safe_fetch.is_public_address(ipaddress.ip_address(text)), text)

    def test_one_internal_answer_among_public_ones_refuses_the_host(self):
        with (
            patch.object(safe_fetch.socket, 'getaddrinfo', resolving_to(PUBLIC, '10.0.0.1')),
            self.assertRaises(safe_fetch.UnsafeUrl),
        ):
            safe_fetch.resolve_public('images.example', 443)

    def test_an_internal_ipv6_answer_refuses_the_host(self):
        with (
            patch.object(safe_fetch.socket, 'getaddrinfo', resolving_to(PUBLIC, '::ffff:10.0.0.1')),
            self.assertRaises(safe_fetch.UnsafeUrl),
        ):
            safe_fetch.resolve_public('images.example', 443)

    def test_an_unresolvable_host_is_refused(self):
        with (
            patch.object(safe_fetch.socket, 'getaddrinfo', side_effect=OSError('no such host')),
            self.assertRaises(safe_fetch.UnsafeUrl),
        ):
            safe_fetch.resolve_public('nowhere.example', 443)

    def test_a_scoped_ipv6_answer_is_checked_without_its_zone(self):
        with (
            patch.object(safe_fetch.socket, 'getaddrinfo', resolving_to('fe80::1%eth0')),
            self.assertRaises(safe_fetch.UnsafeUrl),
        ):
            safe_fetch.resolve_public('images.example', 443)

    def test_non_http_and_credentialed_urls_are_refused(self):
        for url in (
            'file:///etc/passwd',
            'ftp://example.com/a.jpg',
            'gopher://x',
            'http://',
            'http://u:p@example.com/',
        ):
            with self.assertRaises(safe_fetch.UnsafeUrl, msg=url):
                safe_fetch.split_url(url)


class PinnedFetchTest(unittest.TestCase):
    """The connection goes to the address that was checked, never to a fresh lookup."""

    def setUp(self):
        self.pools = []
        self.replies = []
        patcher = patch.object(safe_fetch, '_pool', side_effect=self.make_pool)
        patcher.start()
        self.addCleanup(patcher.stop)
        resolver = patch.object(safe_fetch.socket, 'getaddrinfo', resolving_to(PUBLIC))
        self.getaddrinfo = resolver.start()
        self.addCleanup(resolver.stop)

    def make_pool(self, scheme, host, address, port, timeout):
        pool = MagicMock()
        pool.args = (scheme, host, address, port, timeout)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            pool.urlopen.side_effect = reply
        else:
            pool.urlopen.return_value = reply
        self.pools.append(pool)
        return pool

    def test_a_public_url_is_fetched_through_the_checked_address_with_its_own_host_header(self):
        self.replies.append(response(body=b'binary'))
        self.assertEqual(safe_fetch.fetch('https://images.example/a.jpg?size=640'), b'binary')
        self.assertEqual(len(self.pools), 1)
        pool = self.pools[0]
        scheme, host, address, port, _timeout = pool.args
        self.assertEqual((scheme, host, address, port), ('https', 'images.example', PUBLIC, 443))
        method, target = pool.urlopen.call_args.args
        kwargs = pool.urlopen.call_args.kwargs
        self.assertEqual((method, target), ('GET', '/a.jpg?size=640'))
        self.assertEqual(kwargs['headers']['Host'], 'images.example')
        self.assertFalse(kwargs['redirect'])
        self.assertFalse(kwargs['retries'])

    def test_a_non_default_port_is_part_of_the_host_header(self):
        self.replies.append(response())
        safe_fetch.fetch('http://images.example:8080/a.jpg')
        self.assertEqual(self.pools[0].urlopen.call_args.kwargs['headers']['Host'], 'images.example:8080')

    def test_a_rebinding_resolver_is_asked_only_once(self):
        # A rebinding DNS server: public for the check, internal for anyone asking again.
        self.getaddrinfo.side_effect = [answers(PUBLIC), answers('127.0.0.1')]
        self.replies.append(response(body=b'binary'))
        self.assertEqual(safe_fetch.fetch('https://rebind.example/a.jpg'), b'binary')
        self.assertEqual(self.getaddrinfo.call_count, 1)
        self.assertEqual(self.pools[0].args[2], PUBLIC)

    def test_a_rebinding_resolver_that_turns_internal_on_the_redirect_is_refused(self):
        self.getaddrinfo.side_effect = [answers(PUBLIC), answers('169.254.169.254')]
        self.replies.append(response(status=302, headers={'Location': '/second'}))
        with self.assertRaises(safe_fetch.UnsafeUrl):
            safe_fetch.fetch('https://rebind.example/a.jpg')
        self.assertEqual(len(self.pools), 1)

    def test_a_redirect_to_a_private_address_is_refused_before_connecting(self):
        def resolve(host, *_args, **_kwargs):
            return answers(LAN if host == 'internal.example' else PUBLIC)

        self.getaddrinfo.side_effect = resolve
        self.replies.append(response(status=301, headers={'Location': 'http://internal.example/api/users'}))
        with self.assertRaises(safe_fetch.UnsafeUrl):
            safe_fetch.fetch('https://images.example/a.jpg')
        self.assertEqual(len(self.pools), 1)

    def test_a_redirect_to_an_ip_literal_is_checked_too(self):
        self.getaddrinfo.side_effect = lambda host, *a, **k: answers(host if host[0].isdigit() else PUBLIC)
        self.replies.append(response(status=307, headers={'Location': 'http://169.254.169.254/latest/meta-data/'}))
        with self.assertRaises(safe_fetch.UnsafeUrl):
            safe_fetch.fetch('https://images.example/a.jpg')

    def test_a_redirect_to_another_scheme_is_refused(self):
        self.replies.append(response(status=302, headers={'Location': 'file:///etc/passwd'}))
        with self.assertRaises(safe_fetch.UnsafeUrl):
            safe_fetch.fetch('https://images.example/a.jpg')

    def test_a_public_redirect_is_followed_with_the_new_host_header(self):
        self.replies.extend([response(status=302, headers={'Location': 'https://cdn.example/b.jpg'}), response()])
        self.assertEqual(safe_fetch.fetch('https://images.example/a.jpg'), b'img')
        self.assertEqual(self.pools[1].args[1], 'cdn.example')
        self.assertEqual(self.pools[1].urlopen.call_args.kwargs['headers']['Host'], 'cdn.example')

    def test_the_redirect_hop_limit_holds(self):
        self.replies.extend(response(status=302, headers={'Location': '/again'}) for _ in range(3))
        with self.assertRaises(safe_fetch.UnsafeUrl):
            safe_fetch.fetch('https://images.example/a.jpg', max_redirects=2)
        self.assertEqual(len(self.pools), 3)

    def test_a_declared_oversized_body_is_refused(self):
        self.replies.append(response(headers={'Content-Length': str(101)}))
        with self.assertRaises(safe_fetch.ResponseTooLarge):
            safe_fetch.fetch('https://images.example/a.jpg', max_bytes=100)

    def test_an_undeclared_oversized_body_is_cut_off(self):
        self.replies.append(response(body=b'x' * (safe_fetch.CHUNK_BYTES * 3)))
        with self.assertRaises(safe_fetch.ResponseTooLarge):
            safe_fetch.fetch('https://images.example/a.jpg', max_bytes=safe_fetch.CHUNK_BYTES)

    def test_an_error_status_is_a_failure(self):
        self.replies.append(response(status=404))
        with self.assertRaises(safe_fetch.FetchFailed):
            safe_fetch.fetch('https://images.example/a.jpg')

    def test_the_next_checked_address_is_tried_when_one_does_not_answer(self):
        self.getaddrinfo.return_value = answers(PUBLIC, '1.1.1.1')
        self.replies.extend([urllib3.exceptions.NewConnectionError(None, 'refused'), response()])
        self.assertEqual(safe_fetch.fetch('https://images.example/a.jpg'), b'img')
        self.assertEqual([p.args[2] for p in self.pools], [PUBLIC, '1.1.1.1'])


class PoolTest(unittest.TestCase):
    """The pinned pool keeps the name for TLS: SNI and certificate check, not the IP."""

    def test_https_sends_the_name_as_sni_and_checks_the_certificate_against_it(self):
        pool = safe_fetch._pool('https', 'images.example', PUBLIC, 443, 5)
        self.assertIsInstance(pool, urllib3.HTTPSConnectionPool)
        self.assertEqual(pool.host, PUBLIC)
        self.assertEqual(pool.conn_kw['server_hostname'], 'images.example')
        self.assertEqual(pool.assert_hostname, 'images.example')
        self.assertEqual(pool.cert_reqs, 'CERT_REQUIRED')

    def test_http_connects_to_the_address(self):
        pool = safe_fetch._pool('http', 'images.example', '2606:4700:4700::1111', 80, 5)
        self.assertEqual(pool.host, '2606:4700:4700::1111')
        self.assertNotIsInstance(pool, urllib3.HTTPSConnectionPool)


class _Handler(BaseHTTPRequestHandler):
    """Serves the few behaviours the end-to-end tests need, recording the Host header."""

    seen_hosts: list = []

    def do_GET(self):  # noqa: N802 - the http.server API
        """Answer by path: an image, a slow drip, or a stall."""
        _Handler.seen_hosts.append(self.headers.get('Host'))
        if self.path == '/drip':
            self.send_response(200)
            self.end_headers()
            try:
                for _ in range(100):
                    self.wfile.write(b'x' * 16)
                    self.wfile.flush()
                    time.sleep(0.05)
            except OSError:
                pass
            return
        if self.path == '/stall':
            time.sleep(2)
            return
        body = b'\x89PNG pinned'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        """Keep the test output quiet."""


class EndToEndTest(unittest.TestCase):
    """A real socket: the request can only arrive through the pinned loopback address."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        cls.server.daemon_threads = True
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.seen_hosts = []
        real = safe_fetch.is_public_address
        # Only this test's loopback server counts as public; everything else keeps the real rule.
        allow = patch.object(safe_fetch, 'is_public_address', side_effect=lambda a: str(a) == '127.0.0.1' or real(a))
        allow.start()
        self.addCleanup(allow.stop)
        # The name's first answer is the server; any second lookup of the name gets an
        # address nothing listens on. urllib3 still passes the pinned IP literal through
        # getaddrinfo, which only ever returns the literal itself -- so do the same here.
        self.name_answers = [answers('127.0.0.1'), answers('10.255.255.1')]
        self.name_lookups = 0
        real_getaddrinfo = safe_fetch.socket.getaddrinfo

        def resolve(host, *args, **kwargs):
            if host == 'images.example':
                self.name_lookups += 1
                return self.name_answers.pop(0)
            return real_getaddrinfo(host, *args, **kwargs)

        resolver = patch.object(safe_fetch.socket, 'getaddrinfo', side_effect=resolve)
        resolver.start()
        self.addCleanup(resolver.stop)

    def test_the_body_arrives_through_the_pinned_address_with_the_original_host(self):
        body = safe_fetch.fetch(f'http://images.example:{self.port}/a.png', timeout=5)
        self.assertEqual(body, b'\x89PNG pinned')
        self.assertEqual(_Handler.seen_hosts, [f'images.example:{self.port}'])
        self.assertEqual(self.name_lookups, 1)

    def test_the_overall_deadline_cuts_off_a_slow_drip(self):
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            safe_fetch.fetch(f'http://images.example:{self.port}/drip', timeout=0.5)
        self.assertLess(time.monotonic() - started, 2)

    def test_a_server_that_never_answers_times_out(self):
        started = time.monotonic()
        with self.assertRaises(urllib3.exceptions.ReadTimeoutError):
            safe_fetch.fetch(f'http://images.example:{self.port}/stall', timeout=0.3)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_the_size_cap_holds_on_a_real_stream(self):
        with self.assertRaises(safe_fetch.ResponseTooLarge):
            safe_fetch.fetch(f'http://images.example:{self.port}/drip', timeout=5, max_bytes=40)


if __name__ == '__main__':
    unittest.main()
