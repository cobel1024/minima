FROM python:3.14-alpine AS base
ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PIP_NO_CACHE_DIR=off
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv export --no-hashes --no-dev --format requirements-txt > requirements-prod.txt && \
  uv export --no-hashes --only-group dev --format requirements-txt > requirements-dev-only.txt

# rust required to build ua-parser[regex]
FROM python:3.14-alpine AS build
RUN apk add --no-cache gcc musl-dev binutils git
WORKDIR /app
COPY --from=base /app/requirements-prod.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
  find /usr/local -name "*.so" -type f -exec strip --strip-all {} \; 2>/dev/null || true && \
  find /usr/local -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
  find /usr/local -type f -name "*.pyc" -delete && \
  find /usr/local -type f -name "*.pyo" -delete && \
  rm -rf /root/.cache

# runtime
FROM python:3.14-alpine AS prod
ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="/app"
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app && \
  apk add --no-cache libgcc libstdc++ font-noto-cjk fontconfig && \
  fc-cache -fv
COPY --from=build /usr/local /usr/local
COPY --chown=app:app apps/ /app/apps/
COPY --chown=app:app minima/ /app/minima/
COPY --chown=app:app locale/ /app/locale/
COPY --chown=app:app static/ /app/static/
COPY --chown=app:app manage.py /app/
USER app

# git, gettext required for development
FROM prod AS dev
USER root
RUN apk add --no-cache git gettext
COPY --from=base /app/requirements-dev-only.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
  python -m compileall -q /usr/local/lib/python3.14/site-packages || true
COPY --chown=app:app . /app/
USER app
