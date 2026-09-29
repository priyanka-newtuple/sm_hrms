FROM python:3.12-slim
WORKDIR /app/backend
COPY hrms/requirements.txt /tmp/hrms-requirements.txt
RUN pip install --no-cache-dir -r /tmp/hrms-requirements.txt \
    pytest pytest-asyncio python-dotenv opentelemetry-sdk python-json-logger rich
COPY hrms ./hrms
COPY common ./common
COPY workflow ./workflow
COPY entities ./entities
COPY exceptions ./exceptions
RUN useradd --uid 10001 --create-home hrms && mkdir -p /app/storage /app/backend/logs && chown -R hrms:hrms /app
USER hrms
EXPOSE 8000
CMD ["uvicorn", "hrms.main:app", "--host", "0.0.0.0", "--port", "8000"]
