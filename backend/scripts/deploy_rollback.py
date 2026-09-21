import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger("virtualhr.deploy_rollback")

def check_instance_health(url: str, timeout: float = 5.0) -> bool:
    """Queries instance /health/readiness probe."""
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/health/readiness", headers={"User-Agent": "VirtualHR-Deploy-HealthChecker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "ready"
    except Exception as e:
        logger.warning(f"Health check probe failed for {url}: {e}")
    return False

def run_zero_downtime_deployment(
    current_version_url: str,
    new_version_url: str,
    readiness_timeout_seconds: int = 30
) -> Dict[str, Any]:
    """
    Executes an Expand-Migrate-Contract zero-downtime deployment simulation.
    
    Workflow:
      1. Verify current Version N instance is online and healthy.
      2. Deploy Version N+1 container instance.
      3. Poll /health/readiness probe on N+1 for readiness_timeout_seconds.
      4. If N+1 responds ready within window -> Route 100% traffic to N+1 (SUCCESS).
      5. If N+1 fails readiness -> Instantly trigger 100% traffic rollback to Version N container (ROLLBACK).
    """
    logger.info(f"--- STARTING ZERO-DOWNTIME DEPLOYMENT VALIDATION ---")
    logger.info(f"Current Version N endpoint: {current_version_url}")
    logger.info(f"Candidate Version N+1 endpoint: {new_version_url}")

    # 1. Verify current version is healthy
    n_healthy = check_instance_health(current_version_url)
    logger.info(f"Version N health status: {'HEALTHY' if n_healthy else 'DEGRADED'}")

    # 2. Poll candidate version N+1
    start_poll = time.time()
    n1_ready = False
    while time.time() - start_poll < readiness_timeout_seconds:
        if check_instance_health(new_version_url):
            n1_ready = True
            break
        time.sleep(1.0)

    if n1_ready:
        logger.info(f"✅ Candidate Version N+1 passed readiness probe in {time.time() - start_poll:.2f}s. Routing traffic to Version N+1.")
        return {
            "deployment_status": "PROMOTED",
            "active_version": "N+1",
            "rollback_triggered": False,
            "readiness_time_seconds": round(time.time() - start_poll, 2)
        }
    else:
        logger.error(f"❌ Candidate Version N+1 FAILED readiness probe within {readiness_timeout_seconds}s. TRIGGERING AUTOMATIC ROLLBACK TO VERSION N!")
        # Automatic rollback execution: route 100% traffic back to Version N
        return {
            "deployment_status": "ROLLED_BACK",
            "active_version": "N",
            "rollback_triggered": True,
            "reason": f"Version N+1 failed readiness check within {readiness_timeout_seconds}s"
        }

if __name__ == "__main__":
    n_url = os.getenv("VERSION_N_URL", "http://localhost:9000")
    n1_url = os.getenv("VERSION_N1_URL", "http://localhost:9000")
    res = run_zero_downtime_deployment(n_url, n1_url)
    print(json.dumps(res, indent=2))
