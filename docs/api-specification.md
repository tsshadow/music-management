## 🔌 API Specification

The `music-manager` service provides a REST API (FastAPI) for managing the music library, users, and notifications.

### 🔐 Authentication
- **POST `/users/auth/login`**: Authenticate with username/password and receive an API key.
- **GET `/users/auth/verify`**: Verify the validity of an `X-API-Key`.

### 👤 User & Settings Management
- **GET `/users/`**: List all registered users (Admin only).
- **GET `/users/{user_id}/settings/{app_id}`**: Retrieve application-specific settings (e.g., for Ultrasonic).
- **POST `/users/{user_id}/settings/{app_id}`**: Backup application-specific settings.
- **GET `/users/{user_id}/lb-account`**: Get ListenBrainz integration details.

### 🔔 Notifications
- **GET `/api/notifications/`**: Retrieve recent notifications sent via `ntfy.sh`.
- **DELETE `/api/notifications/{id}`**: Remove a specific notification.
- **DELETE `/api/notifications/`**: Clear all notifications.

### 📈 Scrobbling & Ratings
- **POST `/api/event`**: General scrobble/playback event endpoint.
- **POST `/api/lms-event`**: Specific endpoint for Logitech Media Server webhooks (syncs ratings).

### 🛠 Management & Rules
- **GET `/api/rules`**: List all active tagging and genre rules.
- **POST `/api/users/sync/lms-db`**: Manually trigger a synchronization with `lms.db`.
- **GET `/api/system/containers`**: Monitor the status of system Docker containers.
