FROM python:3.13-slim

WORKDIR /app/backend

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "alembic -c ${ALEMBIC_CONFIG_PATH:-/app/backend/alembic.ini} upgrade head && python main.py"]
