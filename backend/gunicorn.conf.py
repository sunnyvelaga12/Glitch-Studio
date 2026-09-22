import multiprocessing
import os

# Render sets PORT env variable automatically
port = int(os.environ.get("PORT", 9000))

# Bind to 0.0.0.0
bind = f"0.0.0.0:{port}"

# Number of workers based on memory constraints.
# On Render free tier (512MB RAM), multiple workers easily cause OOM (SIGKILL).
# Default to 1 worker, overridable via WEB_CONCURRENCY environment variable.
workers = int(os.environ.get("WEB_CONCURRENCY", 1))

# Uvicorn worker class for ASGI apps
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts and keepalives
timeout = 120
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
