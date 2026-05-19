# STAGE 1: The Builder Environment
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies into a localized deployment layer folder
RUN pip install --no-cache-dir --user -r requirements.txt

# STAGE 2: The Hardened Production Runner
FROM python:3.11-slim AS runner

WORKDIR /app

# Create an unprivileged system user to prevent container escaping vulnerabilities
RUN groupadd -g 10001 operator_group && \
    useradd -u 10001 -g operator_group -m -s /bin/bash operator

# Copy only the compiled binaries and application space from builder stage
COPY --from=builder /root/.local /home/operator/.local
COPY ./apps/api/app ./app

# Re-align strict directory ownership maps to the unprivileged worker
RUN chown -R operator:operator_group /app

# Append Python user binary configurations to environment path maps
ENV PATH=/home/operator/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

USER operator

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]