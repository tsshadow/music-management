"""Coverage for the RBAC helpers and the schema bootstrap in services/music_manager/rbac.py."""
import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.ntfy_listener
services.music_manager.ntfy_listener.start_ntfy_listener = lambda: None
import services.music_manager.routers.users as users_router
users_router.run_lms_db_sync = lambda: None

from fastapi import HTTPException

from services.music_manager import rbac


class InitDbTest(unittest.TestCase):

    def setUp(self):
        self.cursor = MagicMock()
        # Roles resolve to ids; every SHOW COLUMNS answers "column already there".
        self.cursor.fetchone.side_effect = self.fetchone_sequence()
        self.cursor.fetchall.return_value = [{'id': 1, 'name': 'music.read'}, {'id': 2, 'name': 'users.read'}]

    def fetchone_sequence(self, columns_present=True):
        column_answer = {'Field': 'x'} if columns_present else None
        return [{'id': 1}, {'id': 2}] + [column_answer] * 20

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]

    def test_every_rbac_table_is_created(self):
        rbac.init_db(self.cursor)
        statements = ' '.join(self.statements())
        for table in ('roles', 'permissions', 'role_permissions', 'user_identities',
                      'user_requests', 'user_refresh_tokens', 'audit_events'):
            self.assertIn(f'CREATE TABLE IF NOT EXISTS {table}', statements)

    def test_both_roles_and_every_permission_are_seeded(self):
        rbac.init_db(self.cursor)
        seeded_roles = [call.args[1][0] for call in self.cursor.execute.call_args_list
                        if 'INSERT INTO roles' in call.args[0]]
        self.assertEqual(seeded_roles, ['admin', 'user'])
        seeded_permissions = [call.args[1][0] for call in self.cursor.execute.call_args_list
                              if 'INSERT INTO permissions' in call.args[0]]
        self.assertEqual(len(seeded_permissions), len(rbac.PERMISSIONS))

    def test_the_admin_role_gets_every_permission_and_the_user_role_only_its_own(self):
        rbac.init_db(self.cursor)
        grants = [call.args[1] for call in self.cursor.execute.call_args_list
                  if 'INSERT IGNORE INTO role_permissions' in call.args[0]]
        # Both permissions go to admin (role 1); only 'music.read' also goes to user (role 2).
        self.assertEqual(grants, [(1, 1), (2, 1), (1, 2)])

    def test_missing_columns_are_added(self):
        self.cursor.fetchone.side_effect = self.fetchone_sequence(columns_present=False)
        rbac.init_db(self.cursor)
        statements = ' '.join(self.statements())
        for column in ('role_id', 'enabled', 'email', 'avatar_url', 'updated_at',
                       'last_login_at', 'linked_existing'):
            self.assertIn(f'ADD COLUMN {column}', statements)

    def test_existing_columns_are_left_alone(self):
        rbac.init_db(self.cursor)
        self.assertFalse(any('ADD COLUMN' in s for s in self.statements()))

    def test_the_legacy_admin_flag_is_migrated_into_a_role(self):
        rbac.init_db(self.cursor)
        migrations = [call.args for call in self.cursor.execute.call_args_list
                      if 'UPDATE users SET role_id' in call.args[0]]
        self.assertEqual(migrations[0][1], (1,))
        self.assertIn('is_admin = TRUE', migrations[0][0])
        self.assertEqual(migrations[1][1], (2,))


class LookupTest(unittest.TestCase):

    def setUp(self):
        self.cursor = MagicMock()

    def test_a_role_is_looked_up_by_name(self):
        self.cursor.fetchone.return_value = {'id': 1, 'name': 'admin'}
        self.assertEqual(rbac.get_role_by_name(self.cursor, 'admin'), {'id': 1, 'name': 'admin'})
        self.assertEqual(self.cursor.execute.call_args.args[1], ('admin',))

    def test_the_permissions_of_a_role_are_returned_as_a_set(self):
        self.cursor.fetchall.return_value = [{'name': 'users.read'}, {'name': 'users.create'}]
        self.assertEqual(rbac.get_permissions_for_role(self.cursor, 1), {'users.read', 'users.create'})

    def test_a_user_without_a_role_has_no_permissions(self):
        self.assertEqual(rbac.get_permissions_for_role(self.cursor, None), set())
        self.cursor.execute.assert_not_called()

    def test_an_audit_event_is_recorded(self):
        rbac.record_audit_event(self.cursor, 'user.deleted', actor_user_id=1, target_user_id=2, details='x')
        self.assertEqual(self.cursor.execute.call_args.args[1], ('user.deleted', 1, 2, 'x'))


class PermissionCheckTest(unittest.TestCase):

    def test_the_system_key_always_passes(self):
        self.assertTrue(rbac.has_permission({'type': 'system'}, 'users.read'))
        self.assertTrue(rbac.is_admin_auth({'type': 'system'}))

    def test_an_absent_auth_never_passes(self):
        self.assertFalse(rbac.has_permission(None, 'users.read'))
        self.assertFalse(rbac.is_admin_auth(None))

    def test_a_user_passes_only_for_a_permission_it_holds(self):
        auth = {'type': 'user', 'user': {'permissions': ['users.read']}}
        self.assertTrue(rbac.has_permission(auth, 'users.read'))
        self.assertFalse(rbac.has_permission(auth, 'users.create'))

    def test_a_user_without_a_permission_list_passes_nothing(self):
        self.assertFalse(rbac.has_permission({'type': 'user', 'user': {}}, 'users.read'))
        self.assertFalse(rbac.has_permission({'type': 'user'}, 'users.read'))

    def test_admin_is_derived_from_the_role_name(self):
        self.assertTrue(rbac.is_admin_auth({'type': 'user', 'user': {'role_name': rbac.ADMIN_ROLE_NAME}}))
        self.assertFalse(rbac.is_admin_auth({'type': 'user', 'user': {'role_name': 'user'}}))
        self.assertFalse(rbac.is_admin_auth({'type': 'user'}))


class DependencyTest(unittest.TestCase):

    def resolve(self, dependency, auth):
        async def fake_verify(_key):
            return auth

        with patch.object(users_router, 'verify_api_key', fake_verify):
            return asyncio.run(dependency('a-key'))

    def test_a_caller_holding_the_permission_is_let_through(self):
        auth = {'type': 'user', 'user': {'permissions': ['music.play']}}
        self.assertEqual(self.resolve(rbac.require_permission('music.play'), auth), auth)

    def test_a_caller_missing_the_permission_is_forbidden(self):
        auth = {'type': 'user', 'user': {'permissions': []}}
        with self.assertRaises(HTTPException) as raised:
            self.resolve(rbac.require_permission('music.play'), auth)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn('music.play', raised.exception.detail)

    def test_an_admin_caller_is_let_through_the_admin_guard(self):
        auth = {'type': 'user', 'user': {'role_name': rbac.ADMIN_ROLE_NAME}}
        self.assertEqual(self.resolve(rbac.require_admin(), auth), auth)

    def test_a_non_admin_caller_is_refused_by_the_admin_guard(self):
        auth = {'type': 'user', 'user': {'role_name': 'user'}}
        with self.assertRaises(HTTPException) as raised:
            self.resolve(rbac.require_admin(), auth)
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == '__main__':
    unittest.main()
