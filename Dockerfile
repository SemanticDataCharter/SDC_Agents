# --- Stage 1: Build ---
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir build \
    && python -m build --wheel \
    && pip install --no-cache-dir --prefix=/install dist/*.whl

# --- Stage 2: Runtime ---
FROM python:3.12-slim

# Create non-root user
RUN groupadd -g 1000 sdc && useradd -u 1000 -g sdc -m sdc

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy entrypoint
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create working directories
RUN mkdir -p /home/sdc/.sdc-cache /home/sdc/output \
    && chown -R sdc:sdc /home/sdc

WORKDIR /home/sdc
USER sdc

ENV SDC_AGENT=""
ENV SDC_AGENTS_CONFIG="/home/sdc/sdc-agents.yaml"

ENTRYPOINT ["docker-entrypoint.sh"]
