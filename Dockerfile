# Dockerfile — containerises the BASIC emulator and all BASIC programs.
#
# The image is used for both the coordinator and the worker services;
# the BASIC program to run is selected at runtime via CMD or the
# BASIC_PROGRAM environment variable.
#
# Build:  docker build -t hello-bas .
# Run coordinator:
#   docker run -e OTEL_SERVICE_NAME=coordinator \
#              -e OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
#              hello-bas coordinator.bas
# Run worker:
#   docker run -e OTEL_SERVICE_NAME=worker-1 \
#              -e WORKER_ID=W1 \
#              -e COORD_URL=http://coordinator:8080 \
#              hello-bas worker.bas

FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies (OTel SDK for observability).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy BASIC programs and the emulator.
COPY basic_emulator.py .
COPY hello.bas .
COPY coordinator.bas .
COPY worker.bas .

# Thin entrypoint: run the specified BASIC program through the emulator.
# The first argument (or BASIC_PROGRAM env var) selects the program.
COPY docker-entrypoint.py .

EXPOSE 8080

CMD ["coordinator.bas"]
ENTRYPOINT ["python", "docker-entrypoint.py"]
