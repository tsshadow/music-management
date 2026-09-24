"""Role-based access control (RBAC) for Music Manager.

Replaces the legacy hardcoded ``is_admin`` boolean with a persisted
Role -> Permission model:

    User  belongs to one Role
    Role  has many Permissions (via RolePermission)

Authorization anywhere in the API must be derived from the caller's role
and permissions (see ``require_permission``/``require_admin`` below), never
from a hardcoded username/email or an inline ``role == 'admin'`` check.
"""

from fastapi import Header, HTTPException

# name -> description
PERMISSIONS = [
    ('music.read', 'View the music library'),
    ('music.play', 'Stream/play music'),
    ('rating.write', 'Rate tracks'),
    ('scrobble.write', 'Submit scrobbles/listens'),
    ('playlist.read', 'View playlists'),
    ('playlist.write', 'Manage own playlists'),
    ('profile.manage', 'Manage own profile'),
    ('sessions.manage-own', "Manage one's own sessions"),
    ('users.read', 'View users'),
    ('users.create', 'Create users'),
    ('users.update', 'Update users'),
    ('users.disable', 'Enable/disable users'),
    ('users.assign-role', 'Assign a role to a user'),
    ('users.revoke-sessions', 'Revoke sessions of any user'),
    ('users.merge', 'Merge two user accounts into one'),
    ('user-requests.read', 'View pending/approved/rejected access requests'),
    ('user-requests.approve', 'Approve an access request'),
    ('user-requests.reject', 'Reject an access request'),
    ('user-requests.unapprove', 'Undo an approved access request (deletes/unlinks the resulting account)'),
    ('rules.manage', 'Edit artists, labels and genres, and manage tagging rules'),
    ('config.manage', 'Read and change the runtime configuration'),
    ('radio.manage', 'Create and edit radio channels'),
    ('news.manage', 'Configure news recording'),
    ('roles.read', 'View roles'),
    ('roles.manage', 'Manage roles and their permissions'),
    ('permissions.read', 'View permissions'),
]

# Permissions granted to the initial 'user' role.
USER_ROLE_PERMISSIONS = {
    'music.read',
    'music.play',
    'rating.write',
    'scrobble.write',
    'playlist.read',
    'playlist.write',
    'profile.manage',
    'sessions.manage-own',
}

ADMIN_ROLE_NAME = 'admin'
DEFAULT_ROLE_NAME = 'user'


def init_db(cursor):
    """Create RBAC tables, seed roles/permissions and migrate users.is_admin."""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            description VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            description VARCHAR(255)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_id INT NOT NULL,
            permission_id INT NOT NULL,
            PRIMARY KEY (role_id, permission_id),
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
            FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
        )
    ''')

    for name, description in (('admin', 'Full administrative access'), ('user', 'Standard application user')):
        cursor.execute(
            'INSERT INTO roles (name, description) VALUES (%s, %s) ON DUPLICATE KEY UPDATE description = VALUES(description)',
            (name, description),
        )
    for name, description in PERMISSIONS:
        cursor.execute(
            'INSERT INTO permissions (name, description) VALUES (%s, %s) ON DUPLICATE KEY UPDATE description = VALUES(description)',
            (name, description),
        )

    cursor.execute('SELECT id FROM roles WHERE name = %s', (ADMIN_ROLE_NAME,))
    admin_role_id = cursor.fetchone()['id']
    cursor.execute('SELECT id FROM roles WHERE name = %s', (DEFAULT_ROLE_NAME,))
    user_role_id = cursor.fetchone()['id']

    cursor.execute('SELECT id, name FROM permissions')
    for perm in cursor.fetchall():
        cursor.execute(
            'INSERT IGNORE INTO role_permissions (role_id, permission_id) VALUES (%s, %s)', (admin_role_id, perm['id'])
        )
        if perm['name'] in USER_ROLE_PERMISSIONS:
            cursor.execute(
                'INSERT IGNORE INTO role_permissions (role_id, permission_id) VALUES (%s, %s)',
                (user_role_id, perm['id']),
            )

    # users.role_id: the single source of truth for a user's authorization.
    cursor.execute("SHOW COLUMNS FROM users LIKE 'role_id'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE users ADD COLUMN role_id INT AFTER is_admin')
    cursor.execute("SHOW COLUMNS FROM users LIKE 'enabled'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE users ADD COLUMN enabled BOOLEAN DEFAULT TRUE AFTER role_id')
    cursor.execute("SHOW COLUMNS FROM users LIKE 'email'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE users ADD COLUMN email VARCHAR(255) AFTER username')
    cursor.execute("SHOW COLUMNS FROM users LIKE 'avatar_url'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE users ADD COLUMN avatar_url VARCHAR(1024) AFTER display_name')
    cursor.execute("SHOW COLUMNS FROM users LIKE 'updated_at'")
    if not cursor.fetchone():
        cursor.execute(
            'ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at'
        )
    cursor.execute("SHOW COLUMNS FROM users LIKE 'last_login_at'")
    if not cursor.fetchone():
        cursor.execute('ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP NULL AFTER updated_at')

    # Migrate legacy is_admin flag into role_id exactly once (only rows without a role yet).
    cursor.execute('UPDATE users SET role_id = %s WHERE role_id IS NULL AND is_admin = TRUE', (admin_role_id,))
    cursor.execute('UPDATE users SET role_id = %s WHERE role_id IS NULL', (user_role_id,))

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_identities (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            provider VARCHAR(50) NOT NULL,
            provider_subject VARCHAR(255) NOT NULL,
            email_at_provider VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_provider_subject (provider, provider_subject),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            google_subject VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255),
            display_name VARCHAR(255),
            avatar_url VARCHAR(1024),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP NULL,
            reviewed_by_user_id INT,
            created_user_id INT,
            linked_existing BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (created_user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')
    cursor.execute("SHOW COLUMNS FROM user_requests LIKE 'linked_existing'")
    if not cursor.fetchone():
        cursor.execute(
            'ALTER TABLE user_requests ADD COLUMN linked_existing BOOLEAN DEFAULT FALSE AFTER created_user_id'
        )

    # Internal refresh tokens issued alongside an access token (api_key) so
    # clients (Android, web) can obtain a fresh access token without
    # re-authenticating with Google/local credentials every time.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_refresh_tokens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            token VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            revoked_at TIMESTAMP NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            event_type VARCHAR(100) NOT NULL,
            actor_user_id INT,
            target_user_id INT,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def get_role_by_name(cursor, name):
    """The roles row called `name`, or None."""
    cursor.execute('SELECT id, name FROM roles WHERE name = %s', (name,))
    return cursor.fetchone()


def get_permissions_for_role(cursor, role_id):
    """Return the set of permission names granted to a role."""
    if not role_id:
        return set()
    cursor.execute(
        '''
        SELECT p.name FROM permissions p
        JOIN role_permissions rp ON rp.permission_id = p.id
        WHERE rp.role_id = %s
    ''',
        (role_id,),
    )
    return {row['name'] for row in cursor.fetchall()}


def record_audit_event(cursor, event_type, actor_user_id=None, target_user_id=None, details=None):
    """Append one row to audit_events."""
    cursor.execute(
        'INSERT INTO audit_events (event_type, actor_user_id, target_user_id, details) VALUES (%s, %s, %s, %s)',
        (event_type, actor_user_id, target_user_id, details),
    )


def has_permission(auth: dict, permission: str) -> bool:
    """Check a resolved `auth` dict (as returned by verify_api_key) for a permission.

    The system API key (service-to-service calls) always passes.
    """
    if not auth:
        return False
    if auth.get('type') == 'system':
        return True
    user = auth.get('user') or {}
    return permission in (user.get('permissions') or [])


def is_admin_auth(auth: dict) -> bool:
    """Convenience check resolved through the role system (not a hardcoded identity)."""
    if not auth:
        return False
    if auth.get('type') == 'system':
        return True
    user = auth.get('user') or {}
    return user.get('role_name') == ADMIN_ROLE_NAME


def require_permission(permission: str):
    """Reusable FastAPI dependency: RequirePermission("music.play")."""

    def _dependency(x_api_key: str = Header(None)):
        # Sync on purpose, like users.verify_api_key it delegates to: the key check is
        # a database round trip, and an `async def` here would run it on the event loop.
        from services.music_manager.routers.users import verify_api_key as _verify

        auth = _verify(x_api_key)
        if not has_permission(auth, permission):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return auth

    return _dependency


def require_admin():
    """Convenience guard equivalent to RequirePermission for the admin role.

    Resolves access through the role system rather than a hardcoded identity.
    """

    def _dependency(x_api_key: str = Header(None)):
        from services.music_manager.routers.users import verify_api_key as _verify

        auth = _verify(x_api_key)
        if not is_admin_auth(auth):
            raise HTTPException(status_code=403, detail='Admin role required')
        return auth

    return _dependency


#: How many refresh tokens one account keeps. Every successful login mints one -- and
#: LMS logs in on the user's behalf for every Subsonic password check it has not cached
#: -- so without a cap the table only ever grew.
REFRESH_TOKENS_PER_USER = 10

#: A revoked refresh token is refused whether its row exists or not; after this many
#: days the row only takes up space.
REVOKED_REFRESH_TOKEN_DAYS = 30

# The newest REFRESH_TOKENS_PER_USER ids of one account survive; every older one goes.
# The subquery sits inside a derived table because MariaDB refuses both a LIMIT in an
# IN-subquery and a subquery that reads the table the DELETE writes; a derived table is
# materialised first, which sidesteps both. Fewer rows than the cap leave the subquery
# empty, the comparison NULL, and nothing is deleted.
_PRUNE_ONE_ACCOUNT = (
    'DELETE FROM user_refresh_tokens WHERE user_id = %s AND id < ('
    'SELECT edge.id FROM ('
    'SELECT id FROM user_refresh_tokens WHERE user_id = %s ORDER BY id DESC LIMIT 1 OFFSET %s'
    ') AS edge)'
)

# The same cap over every account at once, for the daily housekeeping: it clears the
# backlog that built up before the per-login prune existed.
_PRUNE_ALL_ACCOUNTS = (
    'DELETE t FROM user_refresh_tokens t JOIN ('
    'SELECT id FROM ('
    'SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY id DESC) AS newest_first '
    'FROM user_refresh_tokens'
    ') AS ranked WHERE newest_first > %s'
    ') AS doomed ON doomed.id = t.id'
)

_PURGE_REVOKED = (
    'DELETE FROM user_refresh_tokens WHERE revoked_at IS NOT NULL AND revoked_at < DATE_SUB(NOW(), INTERVAL %s DAY)'
)


def issue_refresh_token(cursor, user_id: int, token: str) -> None:
    """Store a new refresh token for `user_id` and drop that account's oldest beyond the cap.

    Shared by the password login and the Google login, the two places that mint one.
    """
    cursor.execute('INSERT INTO user_refresh_tokens (user_id, token) VALUES (%s, %s)', (user_id, token))
    cursor.execute(_PRUNE_ONE_ACCOUNT, (user_id, user_id, REFRESH_TOKENS_PER_USER - 1))


def purge_refresh_tokens(conn) -> int:
    """Daily housekeeping: enforce the per-account cap everywhere and drop old revoked rows.

    Returns how many rows went. Runs from the events-retention loop.
    """
    removed = 0
    with conn.cursor() as cursor:
        cursor.execute(_PRUNE_ALL_ACCOUNTS, (REFRESH_TOKENS_PER_USER,))
        removed += int(cursor.rowcount or 0)
        cursor.execute(_PURGE_REVOKED, (REVOKED_REFRESH_TOKEN_DAYS,))
        removed += int(cursor.rowcount or 0)
    conn.commit()
    return removed
