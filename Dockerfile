FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PT_HOST=127.0.0.1 \
    PT_PORT=39000 \
    MCP_HOST=127.0.0.1 \
    MCP_PORT=8765

COPY pyproject.toml README.md LICENSE run.py pt-mcp-bridge.pta ./
COPY src ./src

# Instalamos únicamente el runtime MCP (sin descargar los binarios pesados de Qt/X11 en contenedor)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "mcp>=1.2.0,<2" && \
    pip install --no-cache-dir --no-deps .

EXPOSE 8765

ENTRYPOINT ["el-arriero-mcp", "--headless"]

