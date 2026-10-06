# AI Expense Tracker — Deployment Notes

## Required environment variables
- `MONGO_URI`
- `JWT_SECRET_KEY`
- `JWT_ACCESS_TOKEN_EXPIRES` (optional; defaults to 86400 seconds)

## Start command
`gunicorn app:app`

## Health check
`/health`

## Important
- Do not commit `.env`.
- Do not commit `.git/`, `__pycache__/`, or virtual environments.
- Frontend API calls use same-origin relative URLs, so the app works locally and after deployment.
