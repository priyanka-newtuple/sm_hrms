FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY hrms_app hrms_app
COPY platform_tools platform_tools
COPY tests tests
RUN useradd --uid 10001 --create-home hrms
USER hrms
CMD ["uvicorn", "hrms_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
