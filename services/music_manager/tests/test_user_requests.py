"""Covers the Google login and access-request review flow in routers/user_requests.py."""

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.music_manager.api_key import resolve_system_api_key
from services.music_manager.main import app
from services.music_manager.routers import user_requests
from services.music_manager.tests.scripted_cursor import (
    ScriptedCursor,
    assert_atomic,
    assert_rolled_back,
    transaction_log,
)

API_KEY = resolve_system_api_key()

CLAIMS = {
    'sub': 'google-sub-1',
    'email': 'user@example.com',
    'name': 'Teun',
    'picture': 'https://example.com/user.jpg',
    'iss': 'https://accounts.google.com',
    'email_verified': True,
}

PENDING_REQUEST = {
    'id': 7,
    'google_subject': 'google-sub-1',
    'email': 'user@example.com',
    'display_name': 'Teun',
    'avatar_url': 'https://example.com/user.jpg',
    'status': 'pending',
    'requested_at': '2026-01-01 01:00:00',
    'reviewed_at': None,
    'reviewed_by_user_id': None,
    'created_user_id': None,
}


class UserRequestsTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def call(self, method, path, rules=(), body=None, lastrowid=None, connection=None):
        """Drive one endpoint against a scripted cursor, as the system caller."""
        cursor = ScriptedCursor(rules, lastrowid=lastrowid)
        if connection is None:
            connection = MagicMock()
            connection.cursor.return_value = cursor
        payload = {} if body is None else {'json': body}
        with patch.object(user_requests, 'get_db_connection', return_value=connection):
            response = getattr(self.client, method)(path, headers={'x-api-key': API_KEY}, **payload)
        return response, cursor, connection


class VerifyGoogleIdTokenTest(unittest.TestCase):
    def test_an_unconfigured_server_refuses_to_validate_anything(self):
        with patch.object(user_requests, 'GOOGLE_CLIENT_ID', None), self.assertRaises(HTTPException) as raised:
            user_requests._verify_google_id_token('a-token')

        self.assertEqual(raised.exception.status_code, 500)
        self.assertIn('GOOGLE_CLIENT_ID', raised.exception.detail)

    def verify(self, claims=None, error=None):
        google_id_token = MagicMock()
        if error is not None:
            google_id_token.verify_oauth2_token.side_effect = error
        else:
            google_id_token.verify_oauth2_token.return_value = claims
        modules = {
            'google.auth.transport.requests': MagicMock(),
            'google.oauth2.id_token': google_id_token,
        }
        with (
            patch.object(user_requests, 'GOOGLE_CLIENT_ID', 'client-id'),
            patch.dict(
                'sys.modules',
                {
                    'google.auth.transport': MagicMock(requests=modules['google.auth.transport.requests']),
                    'google.auth.transport.requests': modules['google.auth.transport.requests'],
                    'google.oauth2': MagicMock(id_token=google_id_token),
                    'google.oauth2.id_token': google_id_token,
                },
            ),
        ):
            return user_requests._verify_google_id_token('a-token'), google_id_token

    def test_a_valid_token_yields_its_claims(self):
        claims, google_id_token = self.verify(CLAIMS)

        self.assertEqual(claims, CLAIMS)
        self.assertEqual(google_id_token.verify_oauth2_token.call_args.kwargs['audience'], 'client-id')

    def test_a_token_google_rejects_is_unauthorized(self):
        with self.assertRaises(HTTPException) as raised:
            self.verify(error=ValueError('token expired'))

        self.assertEqual(raised.exception.status_code, 401)

    def test_the_rejection_does_not_echo_the_library_error(self):
        # Which check failed is for the log, not for whoever is probing the verifier.
        with self.assertLogs('music-manager.user-requests', level='INFO') as logs:
            with self.assertRaises(HTTPException) as raised:
                self.verify(error=ValueError('Token used too early, 1700000000 < 1700000100'))

        self.assertEqual(raised.exception.detail, 'Invalid Google token')
        self.assertIn('Token used too early', logs.output[0])

    def test_an_unverified_email_is_unauthorized(self):
        # Google signs the address on file whether or not its owner ever proved it; an approved
        # request turns that address into a username.
        for verified in (False, 'false', None, 'yes'):
            with self.subTest(email_verified=verified):
                claims = {**CLAIMS, 'email_verified': verified}
                if verified is None:
                    del claims['email_verified']
                with self.assertRaises(HTTPException) as raised:
                    self.verify(claims)

                self.assertEqual(raised.exception.status_code, 401)
                self.assertIn('not verified', raised.exception.detail)

    def test_the_legacy_string_form_of_a_verified_email_is_accepted(self):
        claims, _google_id_token = self.verify({**CLAIMS, 'email_verified': 'true'})

        self.assertEqual(claims['email'], 'user@example.com')

    def test_a_token_from_another_issuer_is_unauthorized(self):
        with self.assertRaises(HTTPException) as raised:
            self.verify({**CLAIMS, 'iss': 'https://evil.example'})

        self.assertEqual(raised.exception.status_code, 401)
        self.assertIn('issuer', raised.exception.detail)


class GoogleLoginTest(UserRequestsTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(user_requests, '_verify_google_id_token', return_value=CLAIMS)
        self.addCleanup(patcher.stop)
        patcher.start()

    def login(self, rules=(), connection=None):
        return self.call('post', '/api/auth/google', rules, body={'id_token': 'a-token'}, connection=connection)

    def test_a_linked_account_gets_a_session(self):
        rules = [
            ('FROM user_identities WHERE provider', None, {'id': 3, 'user_id': 1}),
            (
                'SELECT * FROM users WHERE id = %s',
                None,
                {'id': 1, 'username': 'user', 'api_key': None, 'enabled': True},
            ),
        ]

        with patch('services.music_manager.routers.users.build_auth_user', return_value={'id': 1}):
            response, cursor, connection = self.login(rules)

        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['access_token'], body['api_key'])
        self.assertTrue(body['refresh_token'])
        self.assertTrue(cursor.statements_matching('INSERT INTO user_refresh_tokens'))
        connection.commit.assert_called_once()

    def test_an_existing_api_key_is_kept(self):
        rules = [
            ('FROM user_identities WHERE provider', None, {'id': 3, 'user_id': 1}),
            (
                'SELECT * FROM users WHERE id = %s',
                None,
                {'id': 1, 'username': 'user', 'api_key': 'existing-key', 'enabled': True},
            ),
        ]

        with patch('services.music_manager.routers.users.build_auth_user', return_value={'id': 1}):
            response, _cursor, _connection = self.login(rules)

        self.assertEqual(response.json()['api_key'], 'existing-key')

    def test_an_identity_whose_account_is_gone_is_a_404(self):
        rules = [('FROM user_identities WHERE provider', None, {'id': 3, 'user_id': 1})]

        response, _cursor, _connection = self.login(rules)

        self.assertEqual(response.status_code, 404)

    def test_a_disabled_account_is_refused(self):
        rules = [
            ('FROM user_identities WHERE provider', None, {'id': 3, 'user_id': 1}),
            (
                'SELECT * FROM users WHERE id = %s',
                None,
                {'id': 1, 'username': 'user', 'api_key': 'k', 'enabled': False},
            ),
        ]

        response, _cursor, _connection = self.login(rules)

        self.assertEqual(response.status_code, 403)

    def test_an_unknown_identity_reports_what_google_said_about_it(self):
        response, _cursor, _connection = self.login()

        self.assertEqual(
            response.json(),
            {
                'status': 'unknown',
                'google': {
                    'subject': 'google-sub-1',
                    'email': 'user@example.com',
                    'display_name': 'Teun',
                    'avatar_url': 'https://example.com/user.jpg',
                },
            },
        )

    def test_an_identity_with_a_pending_request_reports_its_status(self):
        rules = [
            ('FROM user_requests WHERE google_subject', None, PENDING_REQUEST),
            ('SELECT * FROM user_requests WHERE id = %s', None, PENDING_REQUEST),
        ]

        response, cursor, _connection = self.login(rules)

        self.assertEqual(response.json()['status'], 'request_pending')
        self.assertEqual(response.json()['request']['id'], 7)
        self.assertTrue(cursor.statements_matching('UPDATE user_requests SET email'))

    def test_a_database_that_is_down_is_a_500(self):
        with patch.object(user_requests, 'get_db_connection', return_value=None):
            response = self.client.post('/api/auth/google', json={'id_token': 'a-token'})

        self.assertEqual(response.status_code, 500)


class CreateAccessRequestTest(UserRequestsTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(user_requests, '_verify_google_id_token', return_value=CLAIMS)
        self.addCleanup(patcher.stop)
        patcher.start()

    def request_access(self, rules=()):
        return self.call('post', '/api/auth/access-request', rules, body={'id_token': 'a-token'})

    def test_a_new_identity_gets_a_pending_request(self):
        # The endpoint looks the request up twice: once to see whether it exists,
        # and once after the insert to read back what it just created.
        cursor = ScriptedCursor()
        lookups = iter([None, PENDING_REQUEST])
        cursor.rules = [('SELECT * FROM user_requests WHERE google_subject', None, None)]
        original_execute = cursor.execute

        def execute(sql, params=None):
            original_execute(sql, params)
            if 'SELECT * FROM user_requests WHERE google_subject' in sql:
                cursor._result = next(lookups, None)

        cursor.execute = execute
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with patch.object(user_requests, 'get_db_connection', return_value=connection):
            response = self.client.post('/api/auth/access-request', json={'id_token': 'a-token'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['request']['status'], 'pending')
        self.assertTrue(cursor.statements_matching('INSERT INTO user_requests'))
        connection.commit.assert_called_once()

    def test_an_already_linked_account_is_told_to_log_in_instead(self):
        rules = [('SELECT id FROM user_identities WHERE provider', None, {'id': 3})]

        response, _cursor, _connection = self.request_access(rules)

        self.assertEqual(response.status_code, 400)
        self.assertIn('log in instead', response.json()['detail'])

    def test_asking_twice_does_not_create_a_second_request(self):
        rules = [('SELECT * FROM user_requests WHERE google_subject', None, PENDING_REQUEST)]

        response, cursor, connection = self.request_access(rules)

        self.assertEqual(response.json()['request']['id'], 7)
        self.assertEqual(cursor.statements_matching('INSERT INTO user_requests'), [])
        connection.commit.assert_not_called()

    def test_a_database_that_is_down_is_a_500(self):
        with patch.object(user_requests, 'get_db_connection', return_value=None):
            response = self.client.post('/api/auth/access-request', json={'id_token': 'a-token'})

        self.assertEqual(response.status_code, 500)


class ListUserRequestsTest(UserRequestsTestCase):
    def test_every_request_is_listed_by_default(self):
        rules = [('SELECT * FROM user_requests ORDER BY', None, [PENDING_REQUEST])]

        response, cursor, _connection = self.call('get', '/api/user-requests', rules)

        self.assertEqual(len(response.json()), 1)
        self.assertEqual(cursor.executed[0][1], None)

    def test_the_list_can_be_narrowed_to_one_status(self):
        rules = [('WHERE status = %s ORDER BY', ('pending',), [PENDING_REQUEST])]

        response, cursor, _connection = self.call('get', '/api/user-requests?status=pending', rules)

        self.assertEqual(len(response.json()), 1)
        self.assertEqual(cursor.executed[0][1], ('pending',))

    def test_a_database_that_is_down_is_a_500(self):
        with patch.object(user_requests, 'get_db_connection', return_value=None):
            response = self.client.get('/api/user-requests', headers={'x-api-key': API_KEY})

        self.assertEqual(response.status_code, 500)


class ApproveUserRequestTest(UserRequestsTestCase):
    def approve(self, rules=(), body=None, lastrowid=99):
        return self.call('post', '/api/user-requests/7/approve', rules, body=body or {}, lastrowid=lastrowid)

    def base_rules(self, request=None):
        return [('SELECT * FROM user_requests WHERE id = %s', None, request or PENDING_REQUEST)]

    def test_approval_creates_a_new_account_with_the_default_role(self):
        with (
            patch.object(user_requests.rbac, 'get_role_by_name', return_value={'id': 2}),
            patch.object(user_requests.rbac, 'record_audit_event'),
        ):
            response, cursor, connection = self.approve(self.base_rules())

        self.assertEqual(response.status_code, 200)
        insert = cursor.statements_matching('INSERT INTO users')[0][1]
        self.assertEqual(insert[0], 'user@example.com')
        self.assertIs(insert[4], False)
        self.assertEqual(insert[5], 2)
        connection.commit.assert_called_once()

    def test_an_email_that_is_already_a_username_is_a_409_not_a_500(self):
        rules = self.base_rules() + [('SELECT id FROM users WHERE LOWER(username) = LOWER(%s)', None, {'id': 5})]

        with (
            patch.object(user_requests.rbac, 'get_role_by_name', return_value={'id': 2}),
            patch.object(user_requests.rbac, 'record_audit_event'),
        ):
            response, cursor, connection = self.approve(rules)

        self.assertEqual(response.status_code, 409)
        self.assertIn('user@example.com', response.json()['detail'])
        self.assertIn('link_user_id', response.json()['detail'])
        self.assertEqual(cursor.statements_matching('INSERT INTO users'), [])
        connection.commit.assert_not_called()

    def test_the_username_check_ignores_case(self):
        with (
            patch.object(user_requests.rbac, 'get_role_by_name', return_value={'id': 2}),
            patch.object(user_requests.rbac, 'record_audit_event'),
        ):
            _response, cursor, _connection = self.approve(self.base_rules())

        check = cursor.statements_matching('SELECT id FROM users WHERE')[0]
        self.assertIn('LOWER(username) = LOWER(%s)', check[0])
        self.assertEqual(check[1], ('user@example.com',))

    def test_losing_the_race_for_the_username_is_a_409_too(self):
        class IntegrityError(Exception):
            pass

        cursor = ScriptedCursor(self.base_rules(), lastrowid=99)
        real_execute = cursor.execute

        def execute(sql, params=None):
            real_execute(sql, params)
            if 'INSERT INTO users' in sql:
                raise IntegrityError(1062, "Duplicate entry 'user@example.com' for key 'username'")

        cursor.execute = execute
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with (
            patch.object(user_requests.rbac, 'get_role_by_name', return_value={'id': 2}),
            patch.object(user_requests, 'get_db_connection', return_value=connection),
        ):
            response = self.client.post('/api/user-requests/7/approve', json={}, headers={'x-api-key': API_KEY})

        self.assertEqual(response.status_code, 409)
        self.assertNotIn('Duplicate entry', response.json()['detail'])

    def test_a_request_without_an_email_falls_back_to_a_generated_username(self):
        request = {**PENDING_REQUEST, 'email': None}

        with (
            patch.object(user_requests.rbac, 'get_role_by_name', return_value={'id': 2}),
            patch.object(user_requests.rbac, 'record_audit_event'),
        ):
            _response, cursor, _connection = self.approve(self.base_rules(request))

        self.assertEqual(cursor.statements_matching('INSERT INTO users')[0][1][0], 'google-google-sub-1')

    def test_the_new_account_is_linked_to_the_google_identity(self):
        with (
            patch.object(user_requests.rbac, 'get_role_by_name', return_value={'id': 2}),
            patch.object(user_requests.rbac, 'record_audit_event'),
        ):
            _response, cursor, _connection = self.approve(self.base_rules())

        self.assertEqual(
            cursor.statements_matching('INSERT INTO user_identities')[0][1],
            (99, 'google', 'google-sub-1', 'user@example.com'),
        )

    def test_approval_can_link_the_identity_to_an_existing_account_instead(self):
        rules = self.base_rules() + [('SELECT * FROM users WHERE id = %s', (5,), {'id': 5, 'username': 'user'})]

        with patch.object(user_requests.rbac, 'record_audit_event') as audit:
            response, cursor, _connection = self.approve(rules, body={'link_user_id': 5, 'display_name': 'Teun S'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(cursor.statements_matching('INSERT INTO users'), [])
        self.assertEqual(cursor.statements_matching('INSERT INTO user_identities')[0][1][0], 5)
        self.assertEqual(cursor.statements_matching('UPDATE users SET display_name')[0][1], ('Teun S', 5))
        self.assertEqual(audit.call_args[0][1], 'user_request.linked')

    def test_linking_to_an_account_that_does_not_exist_is_a_404(self):
        response, _cursor, _connection = self.approve(self.base_rules(), body={'link_user_id': 5})

        self.assertEqual(response.status_code, 404)

    def test_an_unknown_request_is_a_404(self):
        response, _cursor, _connection = self.approve()

        self.assertEqual(response.status_code, 404)

    def test_a_request_that_was_already_reviewed_is_rejected(self):
        response, _cursor, _connection = self.approve(self.base_rules({**PENDING_REQUEST, 'status': 'approved'}))

        self.assertEqual(response.status_code, 400)
        self.assertIn('already approved', response.json()['detail'])

    def test_an_unexpected_failure_is_reported_and_the_connection_closed(self):
        connection = MagicMock()
        connection.cursor.side_effect = RuntimeError('connection reset')

        with patch.object(user_requests, 'get_db_connection', return_value=connection):
            response = self.client.post('/api/user-requests/7/approve', json={}, headers={'x-api-key': API_KEY})

        self.assertEqual(response.status_code, 500)
        self.assertIn('Goedkeuren mislukt', response.json()['detail'])
        connection.close.assert_called_once()

    def test_a_database_that_is_down_is_a_500(self):
        with patch.object(user_requests, 'get_db_connection', return_value=None):
            response = self.client.post('/api/user-requests/7/approve', json={}, headers={'x-api-key': API_KEY})

        self.assertEqual(response.status_code, 500)


class RejectUserRequestTest(UserRequestsTestCase):
    def reject(self, rules=(), body=None):
        return self.call('post', '/api/user-requests/7/reject', rules, body=body or {})

    def test_a_pending_request_is_marked_rejected_and_audited(self):
        rules = [('SELECT * FROM user_requests WHERE id = %s', None, PENDING_REQUEST)]

        with patch.object(user_requests.rbac, 'record_audit_event') as audit:
            response, cursor, connection = self.reject(rules, body={'reason': 'no idea who this is'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(cursor.statements_matching('UPDATE user_requests SET status')[0][1][0], 'rejected')
        self.assertIn('no idea who this is', audit.call_args.kwargs['details'])
        connection.commit.assert_called_once()

    def test_an_unknown_request_is_a_404(self):
        response, _cursor, _connection = self.reject()

        self.assertEqual(response.status_code, 404)

    def test_a_request_that_was_already_reviewed_is_rejected(self):
        rules = [('SELECT * FROM user_requests WHERE id = %s', None, {**PENDING_REQUEST, 'status': 'rejected'})]

        response, _cursor, _connection = self.reject(rules)

        self.assertEqual(response.status_code, 400)

    def test_a_database_that_is_down_is_a_500(self):
        with patch.object(user_requests, 'get_db_connection', return_value=None):
            response = self.client.post('/api/user-requests/7/reject', json={}, headers={'x-api-key': API_KEY})

        self.assertEqual(response.status_code, 500)


class UnapproveUserRequestTest(UserRequestsTestCase):
    APPROVED = {**PENDING_REQUEST, 'status': 'approved', 'created_user_id': 99, 'linked_existing': False}

    def unapprove(self, rules=(), body=None):
        return self.call('post', '/api/user-requests/7/unapprove', rules, body=body or {})

    def test_an_account_the_approval_created_is_deleted_again(self):
        rules = [('SELECT * FROM user_requests WHERE id = %s', None, self.APPROVED)]

        with (
            patch('services.music_manager.routers.users.delete_user_row') as delete_user,
            patch.object(user_requests.rbac, 'record_audit_event'),
        ):
            response, cursor, connection = self.unapprove(rules)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(delete_user.call_args[0][1], 99)
        self.assertIs(delete_user.call_args.kwargs['protect_last_admin'], False)
        self.assertEqual(cursor.statements_matching('UPDATE user_requests SET status')[0][1][0], 'pending')
        connection.commit.assert_called_once()

    def test_a_pre_existing_account_only_loses_its_identity_link(self):
        rules = [('SELECT * FROM user_requests WHERE id = %s', None, {**self.APPROVED, 'linked_existing': True})]

        with (
            patch('services.music_manager.routers.users.delete_user_row') as delete_user,
            patch.object(user_requests.rbac, 'record_audit_event'),
        ):
            _response, cursor, _connection = self.unapprove(rules)

        delete_user.assert_not_called()
        self.assertEqual(
            cursor.statements_matching('DELETE FROM user_identities')[0][1],
            (99, 'google', 'google-sub-1'),
        )

    def test_an_approval_that_created_nothing_only_reopens_the_request(self):
        rules = [('SELECT * FROM user_requests WHERE id = %s', None, {**self.APPROVED, 'created_user_id': None})]

        with (
            patch('services.music_manager.routers.users.delete_user_row') as delete_user,
            patch.object(user_requests.rbac, 'record_audit_event'),
        ):
            _response, cursor, _connection = self.unapprove(rules)

        delete_user.assert_not_called()
        self.assertEqual(cursor.statements_matching('DELETE FROM user_identities'), [])

    def test_an_unknown_request_is_a_404(self):
        response, _cursor, _connection = self.unapprove()

        self.assertEqual(response.status_code, 404)

    def test_a_request_that_was_never_approved_cannot_be_unapproved(self):
        rules = [('SELECT * FROM user_requests WHERE id = %s', None, PENDING_REQUEST)]

        response, _cursor, _connection = self.unapprove(rules)

        self.assertEqual(response.status_code, 400)
        self.assertIn('not approved', response.json()['detail'])

    def test_an_unexpected_failure_is_reported_and_the_connection_closed(self):
        connection = MagicMock()
        connection.cursor.side_effect = RuntimeError('connection reset')

        with patch.object(user_requests, 'get_db_connection', return_value=connection):
            response = self.client.post('/api/user-requests/7/unapprove', json={}, headers={'x-api-key': API_KEY})

        self.assertEqual(response.status_code, 500)
        self.assertIn('Ongedaan maken mislukt', response.json()['detail'])
        connection.close.assert_called_once()

    def test_a_database_that_is_down_is_a_500(self):
        with patch.object(user_requests, 'get_db_connection', return_value=None):
            response = self.client.post('/api/user-requests/7/unapprove', json={}, headers={'x-api-key': API_KEY})

        self.assertEqual(response.status_code, 500)


class InitDbTest(unittest.TestCase):
    def test_the_tables_are_created_by_rbac_so_this_does_nothing(self):
        cursor = ScriptedCursor()

        self.assertIsNone(user_requests.init_db(cursor))
        self.assertEqual(cursor.executed, [])


class ApprovalAtomicityTest(UserRequestsTestCase):
    """Approving creates the account, its identity and the request update together or not at all."""

    def approve(self, fail_on=None):
        cursor = ScriptedCursor([('SELECT * FROM user_requests WHERE id = %s', None, PENDING_REQUEST)], lastrowid=99)
        connection = MagicMock()
        connection.cursor.return_value = cursor
        log = transaction_log(connection, cursor, fail_on=fail_on)
        with (
            patch.object(user_requests.rbac, 'get_role_by_name', return_value={'id': 2}),
            patch.object(user_requests.rbac, 'record_audit_event'),
        ):
            response, _cursor, _connection = self.call(
                'post', '/api/user-requests/7/approve', body={}, connection=connection
            )
        return response, log

    def test_the_account_identity_and_request_are_one_transaction(self):
        response, log = self.approve()
        self.assertEqual(response.status_code, 200)
        assert_atomic(self, log, 'INSERT INTO users', 'INSERT INTO user_identities', 'UPDATE user_requests SET status')

    def test_a_failing_identity_insert_leaves_no_orphan_account(self):
        response, log = self.approve(fail_on='INSERT INTO user_identities')
        self.assertEqual(response.status_code, 500)
        assert_rolled_back(self, log)

    def test_unapproving_deletes_the_account_and_reopens_the_request_together(self):
        approved = {**PENDING_REQUEST, 'status': 'approved', 'created_user_id': 99, 'linked_existing': True}
        cursor = ScriptedCursor([('SELECT * FROM user_requests WHERE id = %s', None, approved)])
        connection = MagicMock()
        connection.cursor.return_value = cursor
        log = transaction_log(connection, cursor, fail_on='UPDATE user_requests SET status')
        with patch.object(user_requests.rbac, 'record_audit_event'):
            response, _cursor, _connection = self.call(
                'post', '/api/user-requests/7/unapprove', body={}, connection=connection
            )
        self.assertEqual(response.status_code, 500)
        assert_rolled_back(self, log)
        self.assertLess(log.index('BEGIN'), log.index(cursor.statements_matching('DELETE FROM user_identities')[0][0]))


if __name__ == '__main__':
    unittest.main()
