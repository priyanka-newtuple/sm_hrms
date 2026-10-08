# Product-owned packaging of the unchanged platform source.
FROM python:3.13-slim
WORKDIR /app/backend
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
# HRMS one-off maintenance tools, run with `docker exec`; the platform source above stays unchanged.
COPY applications/hrms_api/platform_tools/ /app/hrms_platform_tools/
CMD ["sh", "-c", "alembic -c ${ALEMBIC_CONFIG_PATH:-/app/backend/alembic.ini} upgrade head && python main.py"]
