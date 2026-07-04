# User Service Release Notes

## 1.1.3 (2026-07-04)
- **Security**: Added support for `LMS_SUBSONIC_API_KEY` to handle environments where LMS and Muma use different API keys.
- **Diagnostics**: Added JSON validation and detailed error reporting for Subsonic API responses.

## 1.1.2 (2026-07-04)
- **Fix**: Added explicit `apiKey` parameter to Subsonic sync URL to satisfy LMS authentication requirements.

## 1.1.1 (2026-07-04)
- **Fix**: Corrected syntax and logic errors in `run_lms_sync` background task.
- **Feature**: Added support for multiple LMS hosts via `LMS_HOSTS`.

## 1.1.0 (2026-07-04)
- **Security**: Added `X-API-Key` validation to all endpoints.
- **Sync**: Improved synchronization logic with LMS database.

## 1.0.0 (2026-07-04)
- Initial release of the Muma User Service.
- Management of system users and their ListenBrainz accounts.
- API for user synchronization and management.
