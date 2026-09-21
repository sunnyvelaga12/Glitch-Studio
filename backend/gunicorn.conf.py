import multiprocessing
import os

# Render sets PORT env variable automatically
port = int(os.environ.get("PORT", 9000))

# Bind to 0.0.0.0
bind = f"0.0.0.0:{port}"

# Number of workers based on CPU cores (Render instances)
# A good rule of thumb is (2 * CPU_CORES) + 1, but we limit to 4 for standard deployments
# to avoid OOM errors on smaller instances.
workers = int(os.environ.get("WEB_CONCURRENCY", min(multiprocessing.cpu_count() * 2 + 1, 4)))

# Uvicorn worker class for ASGI apps
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts and keepalives
timeout = 120
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
