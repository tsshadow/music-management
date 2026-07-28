# Artist Image Fetch Progress 400 Bad Request

# status: fixed

# reported problem
`https://music.example.com/muma/api/artists/fetch-progress` returns `400 bad request : Request with the provided ID has already finished loading`.

# Possible reason
Polling `/api/artists/fetch-progress` or background task state tracking raises a bad request or errors out when requested after a background task/request ID has already finished loading or completed.

# solution
Ensure `/api/artists/fetch-progress` and related background fetch state endpoints handle completed/idle status robustly without returning 400 errors, and establish the 2-step bug-reporting workflow (`docs/bug-reports/00#-<title>.md`).
