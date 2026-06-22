# READYFEED AI

READYFEED AI is an offline content curator foundation. Users can register, log in, choose topics, subscribe to content sources, edit preferences, and view placeholder download status screens.

This phase is intentionally limited to the Django + React foundation. It does not include AI, Celery, Redis, ETL jobs, WebSockets, Docker, or deployment.

## Tech Stack

- Backend: Django, Django REST Framework, SQLite
- Auth: Django session authentication with CSRF protection
- Cross-origin/local dev: django-cors-headers
- Environment variables: python-dotenv
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

Backend URLs:

- Admin: `http://localhost:8000/admin/`
- Public sources API: `http://localhost:8000/api/sources/`
- API base: `http://localhost:8000/api/`

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
