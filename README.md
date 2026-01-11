# Minima LMS

[![English](https://img.shields.io/badge/Language-English-blue)](README.md)
[![한국어](https://img.shields.io/badge/Language-한국어-red)](README-ko.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Modern, self-hosted LMS built with Django and Solidjs TypeScript.
A lightweight alternative to Moodle, Canvas, and Open edX.

> **🚧 Pre-Release**: Approaching v1.0 release (~80% complete).
Core features are functional and being polished for production use.
Early adopters and contributors welcome!


## Screenshots

![API Documentation](screenshot/screenshot-api.png)
*Interactive API documentation powered by Django Ninja*

![Admin Panel](screenshot/screenshot-admin-en.png)
*Modern admin interface with django-unfold*

![Multilingual Support](screenshot/screenshot-admin-ko.png)
*Built-in i18n support (English, Korean)*

## Features

- 🚀 **Modern Stack**: Django 6.x + Solidjs TypeScript
- 🐳 **Easy Setup**: Docker-based, 5-minute installation
- 🔍 **Powerful Search**: OpenSearch integration
- 🤖 **AI Assistant**: Integrated teaching assistant
- 🌍 **Multilingual**: i18n support
- 🔐 **Secure**: JWT + 2FA authentication

## Related Projects

- [Minima Student](https://github.com/cobel1024/minima-student)
- Minima Website _(coming soon)_

## Quick Start

### Prerequisites

- Docker
- Python 3.14
- uv (Fast Python Package Manager)

### Clone repo

```bash
git clone https://github.com/cobel1024/minima && cd minima
```

### Configure environment

```bash
cp env.example .env
# Edit .env file with your settings
```

### Install uv and sync requirements

[https://docs.astral.sh/uv/](https://docs.astral.sh/uv/)

```bash
uv sync
```

### Setup Docker environment and bootstrap Django

```bash
uv run dev.py up && uv run dev.py bootstrap
# you can also load dummy test data
# docker compose exec minima pytest -v -s --cov -m load_data
```

Access the admin panel: [http://localhost:8000/admin/](http://localhost:8000/admin/)

- account: `admin@example.com`
- password: `1111`

API docs: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

### Additional Services

- **Mailpit** (Email testing): [http://localhost:8025](http://localhost:8025)
- **MinIO Console** (Object storage): [http://localhost:9001](http://localhost:9001)
  - User: `minima`
  - Password: `minima.dev`
- **OpenSearch**: [http://localhost:9200](http://localhost:9200)

## Testing

### Run all tests

```bash
docker compose exec minima pytest -v -s --cov
```

### Load persistent test data

```bash
docker compose exec minima pytest -v -s --cov -m load_data
```

### Run e2e API tests

```bash
docker compose exec minima pytest -v -s --cov -m e2e
```

### Parallel test execution

```bash
docker compose exec minima pytest -v -s --cov -n auto
```

## Development

### Docker Environment Includes

See [docker-compose.yml](docker-compose.yml) for full configuration.

- **Minima** - Minima LMS
- **Celery worker** - Background task processing
- **PostgreSQL** - Primary database
- **OpenSearch** - Search engine
- **Redis** - Cache and message broker
- **Mailpit** - Email testing
- **MinIO** - Object storage
- **Apache Tika** - Document processing

### Helper Commands

```bash
uv run dev.py up        # Build images, create network, start services
uv run dev.py bootstrap # Initialize database and setup environment
uv run dev.py lint      # Run type checking and linting
```

### Development Tools

```bash
# Install development tools
uv tool install ty      # Type checker
uv tool install ruff    # Linter and formatter

# Update tools
uv tool upgrade ty ruff
```

### Code Quality

```bash
# Run all checks
uv run dev.py lint

# Or run individually
uv run ty check                    # Type checking
uv run ruff check .                # Linting
uv run ruff check --select I .     # Import sorting
uv run ruff format .               # Code formatting
```

### Translation

```bash
docker compose exec minima python manage.py makemessages -a --extension html,txt,py,mjml
# edit your {language}.po file in locale/
docker compose exec minima python manage.py compilemessages --ignore=.venv
```

### Database Migrations

```bash
# Create migrations
docker compose exec minima python manage.py makemigrations

# Apply migrations
docker compose exec minima python manage.py migrate

# Show migration status
docker compose exec minima python manage.py showmigrations
```

## Troubleshooting

### Reset environment

```bash
docker compose down -v
docker network rm minima
uv run dev.py up && uv run dev.py bootstrap
```

### Network already exists error

```bash
# This is normal if you've run dev.py up before
# The command will continue anyway
```

### Clean build

```bash
docker compose down -v
uv run dev.py up
```

## Tech Stack

### Backend

- **Framework**: Django 6.x with Django Ninja (Fast API-like REST framework)
- **Database**: PostgreSQL with advanced features (triggers, history tracking)
- **Search**: OpenSearch with django-opensearch-dsl
- **Cache**: Redis
- **Task Queue**: Celery with Redis broker
- **Storage**: MinIO (S3-compatible object storage)
- **Authentication**: JWT + OTP (2FA)

### Key Libraries

- **API**: django-ninja, msgspec, pydantic
- **Admin**: django-unfold (Modern admin interface)
- **Database**: django-pgtrigger, django-pghistory, django-treebeard
- **Content Processing**: tika, yt-dlp, beautifulsoup4
- **AI Integration**: google-genai
- **PDF**: fpdf2, pypdfium2
- **Email**: mjml-python (Responsive email templates)

### Development

- **Package Manager**: uv
- **Type Checking**: ty (pyright wrapper)
- **Linting/Formatting**: ruff
- **Testing**: pytest with pytest-django, factory-boy, mimesis
- **Coverage**: pytest-cov

## License

MIT License

Copyright (c) 2025 Minima

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
