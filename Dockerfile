FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml ./
COPY bill_reader ./bill_reader
RUN pip install --no-cache-dir .
COPY config ./config
COPY samples ./samples
EXPOSE 8000
CMD ["bill-reader", "serve", "--host", "0.0.0.0", "--port", "8000"]
