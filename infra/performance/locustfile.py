"""
Arada Intelligence OS — Load Testing with Locust

Usage:
  # GUI (http://localhost:8089)
  locust -f infra/performance/locustfile.py --host=https://arada.fun

  # Headless (automated)
  locust -f locustfile.py --host=https://arada.fun \
    --users 100 --spawn-rate 10 --run-time 300 --headless
"""

from locust import HttpUser, task, between, events
import logging
import time

logger = logging.getLogger(__name__)

# Global test state
auth_token = None


class AradaUser(HttpUser):
    """Simulates a real user interacting with Arada API."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    def on_start(self):
        """Register and login user at start of session."""
        global auth_token

        # Register user (unique per worker)
        register_data = {
            "email": f"user-{self.client.env.target}-{time.time()}@test.arada.fun",
            "password": "TestPassword123!",
            "workspace_name": f"workspace-{int(time.time() * 1000)}",
        }

        response = self.client.post("/auth/register", json=register_data)
        if response.status_code == 201:
            auth_token = response.json()["access_token"]
            logger.info(f"User registered and logged in: {register_data['email']}")
        else:
            logger.error(f"Registration failed: {response.text}")

    # ========================================================================
    # LIGHTWEIGHT TASKS (high weight = more frequent)
    # ========================================================================

    @task(5)  # Health check (fast, no auth needed)
    def health_check(self):
        """Check API health (no auth)."""
        self.client.get("/system/health", name="/system/health")

    @task(4)  # List content (paginated)
    def list_items(self):
        """List content items with pagination."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        self.client.get(
            "/content/items?limit=20&offset=0",
            headers=headers,
            name="/content/items",
        )

    @task(3)  # Get workflow jobs
    def list_jobs(self):
        """List workflow jobs."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        self.client.get(
            "/workflow/jobs?limit=20&status=completed",
            headers=headers,
            name="/workflow/jobs",
        )

    # ========================================================================
    # MEDIUM-WEIGHT TASKS
    # ========================================================================

    @task(2)  # Get user profile
    def get_profile(self):
        """Fetch current user profile."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        self.client.get("/auth/me", headers=headers, name="/auth/me")

    @task(2)  # Get workspace
    def get_workspace(self):
        """Fetch current workspace."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        self.client.get("/auth/workspace", headers=headers, name="/auth/workspace")

    @task(1)  # Create content source
    def create_source(self):
        """Create a new content source."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        data = {
            "name": f"source-{int(time.time() * 1000)}",
            "source_type": "rss",
            "url": "https://news.ycombinator.com/rss",
        }
        self.client.post(
            "/content/sources", json=data, headers=headers, name="/content/sources"
        )

    @task(1)  # Get metrics (internal endpoint)
    def metrics(self):
        """Fetch Prometheus metrics (simulating monitoring scrape)."""
        self.client.get("/metrics", name="/metrics")

    # ========================================================================
    # HEAVY-WEIGHT TASKS (less frequent, slower)
    # ========================================================================

    @task(1)  # Create workflow job (complex operation)
    def create_job(self):
        """Create a workflow job (brief generation)."""
        headers = {"Authorization": f"Bearer {auth_token}"}
        data = {
            "job_type": "brief",
            "input_data": {"item_ids": ["uuid-1", "uuid-2"], "brief_type": "daily"},
            "priority": 5,
        }
        self.client.post(
            "/workflow/jobs", json=data, headers=headers, name="/workflow/jobs"
        )


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    logger.info("=" * 60)
    logger.info("LOAD TEST STARTED")
    logger.info(f"Target: {environment.host}")
    logger.info(f"Users: {environment.shape_class}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    logger.info("=" * 60)
    logger.info("LOAD TEST STOPPED")
    logger.info(f"Total requests: {environment.stats.total.num_requests}")
    logger.info(f"Total failures: {environment.stats.total.num_failures}")
    logger.info(f"Mean response time: {environment.stats.total.avg_response_time:.0f}ms")
    logger.info("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, exception, **kwargs):
    """Called after each request (for custom metrics)."""
    if exception:
        logger.error(f"Request failed: {name} - {exception}")


# ============================================================================
# LOAD PROFILE (optional)
# ============================================================================

from locust import LoadTestShape


class StepLoadShape(LoadTestShape):
    """
    Gradually increase load over time.
    Useful for testing how system handles ramping up.
    """

    stages = [
        {"duration": 60, "users": 10, "spawn_rate": 1},  # 0-60s: 10 users
        {"duration": 120, "users": 50, "spawn_rate": 5},  # 60-180s: 50 users
        {"duration": 180, "users": 100, "spawn_rate": 10},  # 180-360s: 100 users
        {"duration": 120, "users": 200, "spawn_rate": 20},  # 360-480s: 200 users
        {"duration": 60, "users": 0, "spawn_rate": 10},  # 480-540s: ramp down
    ]

    def tick(self):
        run_time = self.get_run_time()

        for stage in self.stages:
            if run_time < sum(s["duration"] for s in self.stages[: self.stages.index(stage) + 1]):
                tick_data = (stage["users"], stage["spawn_rate"])
                return tick_data

        return None
