# READYFEED AI

READYFEED AI is an offline content curator foundation. Users can register, log in, choose topics, subscribe to content sources, edit preferences, and view placeholder download status screens.

This phase is intentionally limited to the Django + React foundation plus Redis connection checks and Django cache setup. It does not include AI, Celery, ETL jobs, WebSockets, Docker, S3, AutoGen, or deployment.

## Tech Stack

- Backend: Django, Django REST Framework, PostgreSQL with SQLite fallback
- Auth: Django session authentication with CSRF protection
- Cross-origin/local dev: django-cors-headers
- Environment variables: python-dotenv
- Cache/broker foundation: Redis with django-redis
- Frontend: React, Vite, React Router, Axios, Zustand
- Styling: Tailwind CSS

## Folder Structure

```text
.
├── core/                  # Django app: models, serializers, views, admin, tests
├── frontend/              # Vite React app
│   ├── src/api/           # Axios client and API error helpers
│   ├── src/components/    # Layout, protected route, shared UI pieces
│   ├── src/hooks/         # useAuth hook
│   ├── src/pages/         # Login, Register, Dashboard, Subscriptions, Downloads, Preferences
│   └── src/stores/        # Zustand auth store
├── readyfeed_ai/          # Django project settings and root URL config
├── manage.py
├── requirements.txt
└── README.md
```

## Backend Setup

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_defaults
python manage.py createsuperuser
python manage.py runserver
```

If you have not created the PostgreSQL database yet, comment out or remove `DATABASE_URL` in `.env` before running `migrate`. Without `DATABASE_URL`, Django uses SQLite fallback.

Backend URLs:

- Admin: `http://localhost:8000/admin/`
- Public sources API: `http://localhost:8000/api/sources/`
- API base: `http://localhost:8000/api/`

## PostgreSQL Local Setup

Django reads `DATABASE_URL` from `.env`. If `DATABASE_URL` exists, Django uses PostgreSQL. If it is missing or commented out, Django falls back to local SQLite at `db.sqlite3`.

Expected format:

```env
DATABASE_URL=postgres://DB_USER:DB_PASSWORD@localhost:5432/DB_NAME
```

Local example:

```env
DATABASE_URL=postgres://readyfeed_user:readyfeed_password@localhost:5432/readyfeed_db
```

### macOS With Homebrew

Install and start PostgreSQL:

```bash
brew install postgresql
brew services start postgresql
```

Open PostgreSQL:

```bash
psql postgres
```

Create the database user and database:

```sql
CREATE USER readyfeed_user WITH PASSWORD 'readyfeed_password';
CREATE DATABASE readyfeed_db OWNER readyfeed_user;
GRANT ALL PRIVILEGES ON DATABASE readyfeed_db TO readyfeed_user;
\q
```

Put this in `.env`:

```env
DATABASE_URL=postgres://readyfeed_user:readyfeed_password@localhost:5432/readyfeed_db
```

Then run:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_defaults
python manage.py runserver
```

### Windows

Install PostgreSQL from the official installer, then open SQL Shell (`psql`) or pgAdmin.

In `psql`:

```sql
CREATE USER readyfeed_user WITH PASSWORD 'readyfeed_password';
CREATE DATABASE readyfeed_db OWNER readyfeed_user;
GRANT ALL PRIVILEGES ON DATABASE readyfeed_db TO readyfeed_user;
```

Set this in `.env`:

```env
DATABASE_URL=postgres://readyfeed_user:readyfeed_password@localhost:5432/readyfeed_db
```

If `migrate` fails with `connection refused` or `database does not exist`, PostgreSQL is not running yet or the database/user commands have not been run.

### Linux

Ubuntu/Debian example:

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo -u postgres psql
```

In `psql`:

```sql
CREATE USER readyfeed_user WITH PASSWORD 'readyfeed_password';
CREATE DATABASE readyfeed_db OWNER readyfeed_user;
GRANT ALL PRIVILEGES ON DATABASE readyfeed_db TO readyfeed_user;
\q
```

Set this in `.env`:

```env
DATABASE_URL=postgres://readyfeed_user:readyfeed_password@localhost:5432/readyfeed_db
```

## Verify Database Connection

Check which database engine Django is using:

```bash
source .venv/bin/activate
python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE']); print(settings.DATABASES['default']['NAME'])"
```

Expected PostgreSQL engine:

```text
django.db.backends.postgresql
```

Open Django's database shell:

```bash
python manage.py dbshell
```

Or verify migrations directly in PostgreSQL:

```bash
psql postgres://readyfeed_user:readyfeed_password@localhost:5432/readyfeed_db
```

Then:

```sql
\dt
SELECT app, name FROM django_migrations ORDER BY applied DESC LIMIT 10;
```

## Redis Local Setup

Django reads `REDIS_URL` from `.env`. If `REDIS_URL` exists, Django uses Redis for the default cache through `django-redis`. If it is missing or commented out, Django falls back to local memory cache.

Expected local value:

```env
REDIS_URL=redis://localhost:6379/0
```

### macOS With Homebrew

Install and start Redis:

```bash
brew install redis
brew services start redis
```

Test Redis:

```bash
redis-cli ping
```

Expected response:

```text
PONG
```

### Windows

Use Redis through WSL, Memurai, or another Windows-compatible Redis distribution. After it is running, confirm the URL in `.env` is:

```env
REDIS_URL=redis://localhost:6379/0
```

### Linux

Ubuntu/Debian example:

```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
redis-cli ping
```

## Verify Redis From Django

Install dependencies and start Django:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver
```

The Redis endpoints require an authenticated Django session. You can log in from the React app and call these URLs in the browser, or test with curl.

Curl login example:

```bash
curl -i -c cookies.txt -b cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"username":"Sharayu","password":"your-password"}' \
  http://localhost:8000/api/auth/login/
```

Read the CSRF token from the cookie file:

```bash
CSRF=$(awk '$6 == "csrftoken" {print $7}' cookies.txt | tail -1)
```

Health check:

```bash
curl -b cookies.txt http://localhost:8000/api/system/redis-health/
```

Expected when Redis is running:

```json
{
  "redis": "connected",
  "ping": true
}
```

Expected when Redis is unavailable:

```json
{
  "redis": "unavailable",
  "error": "..."
}
```

Cache test:

```bash
curl -b cookies.txt \
  -H "X-CSRFToken: $CSRF" \
  -X POST \
  http://localhost:8000/api/system/cache-test/
```

Expected response:

```json
{
  "cache": "working",
  "value": "hello from redis"
}
```

## Frontend Setup

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

- React app: `http://localhost:5173/`

Vite proxies frontend `/api` requests to `http://localhost:8000`.

## Run Both Servers

Terminal 1:

```bash
source .venv/bin/activate
python manage.py runserver
```

Terminal 2:

```bash
cd frontend
npm run dev
```

Use `http://localhost:5173/` for the app. Use `http://localhost:8000/admin/` only for Django admin.

## API Routes

Public when logged out:

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `GET /api/sources/`

Requires login:

- `POST /api/auth/logout/`
- `GET /api/auth/me/`
- `GET /api/preferences/`
- `GET|PATCH /api/preferences/me/`
- `GET|POST /api/subscriptions/`
- `GET|POST /api/downloads/`
- `GET|POST /api/commute/`
- `GET /api/system/redis-health/`
- `POST /api/system/cache-test/`

Compatibility route:

- `GET|POST /api/commute-windows/`

## Seed Data

Run:

```bash
python manage.py seed_defaults
```

This creates starter content sources for:

- podcasts
- news
- memes

The URLs are simple sample feed URLs for local development.

## Common Errors And Fixes

`Page not found (404)` at `http://localhost:8000/`:

The Django backend root page is not the React app. Open `http://localhost:5173/` for the frontend, or `http://localhost:8000/admin/` for admin.

Admin login says the username/password is wrong:

Django admin requires a staff/superuser account. Run:

```bash
source .venv/bin/activate
python manage.py createsuperuser
```

React cannot reach the API:

Make sure Django is running on port `8000` and Vite is running on port `5173`.

CSRF or session errors:

Use the React app through `http://localhost:5173/`. The frontend Axios client sends cookies and attaches the CSRF token automatically for `POST`, `PATCH`, `PUT`, and `DELETE`.

No content sources appear:

Run:

```bash
source .venv/bin/activate
python manage.py seed_defaults
```

Port already in use:

Stop the old server process, or run Django/Vite on another port and update the Vite proxy if needed.

## Verification Commands

Backend:

```bash
source .venv/bin/activate
python manage.py test
python manage.py check
```

Frontend:

```bash
cd frontend
npm run build
```

## Manual Acceptance Checklist

1. Start Django on `http://localhost:8000`.
2. Start React on `http://localhost:5173`.
3. Open `http://localhost:5173/register`.
4. Register a new user with topics, daily item limit, storage limit, and optional source subscriptions.
5. Confirm the app redirects to the dashboard.
6. Log out from the navigation.
7. Log in again from `/login`.
8. Confirm the dashboard shows the username and selected topics.
9. Open Preferences and update topics, max daily items, and max storage.
10. Open Subscriptions and subscribe to a source.
11. Confirm the subscription button/status updates immediately.
12. Unsubscribe from the same source.
13. Open Downloads and confirm the empty/placeholder download UI loads.
14. Log out.
15. Log in again and confirm the session and saved data still work.
