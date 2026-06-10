#!/usr/bin/env python3
"""
Arada Intelligence OS — Metabase Auto-Configuration
Initializes Metabase with saved dashboards, questions, and data source connections.
Run after Metabase container is healthy: python3 infra/analytics/metabase_setup.py
"""

import os
import time
import json
import requests
import sys
from typing import Optional

METABASE_URL = os.getenv("METABASE_URL", "http://127.0.0.1:3000")
METABASE_ADMIN_EMAIL = os.getenv("METABASE_ADMIN_EMAIL", "admin@arada.fun")
METABASE_ADMIN_PASSWORD = os.getenv("METABASE_ADMIN_PASSWORD", "changeme")

# Database connection details
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "arada")
DB_USER = os.getenv("POSTGRES_USER", "arada")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme")


class MetabaseAPI:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.token: Optional[str] = None

    def health(self) -> bool:
        """Check if Metabase is healthy."""
        try:
            resp = self.session.get(f"{self.base_url}/api/health", timeout=5)
            return resp.status_code == 200
        except Exception as e:
            print(f"✗ Metabase health check failed: {e}")
            return False

    def wait_for_health(self, timeout: int = 60):
        """Wait for Metabase to become healthy."""
        start = time.time()
        while time.time() - start < timeout:
            if self.health():
                print("✓ Metabase is healthy")
                return True
            time.sleep(2)
        raise TimeoutError(f"Metabase did not become healthy within {timeout}s")

    def login(self, email: str, password: str) -> bool:
        """Authenticate with Metabase."""
        resp = self.session.post(
            f"{self.base_url}/api/session",
            json={"username": email, "password": password}
        )
        if resp.status_code != 200:
            print(f"✗ Login failed: {resp.text}")
            return False
        self.token = resp.json()["id"]
        self.session.headers.update({"X-Metabase-Session": self.token})
        print(f"✓ Logged in as {email}")
        return True

    def get_database(self, name: str) -> Optional[dict]:
        """Get database by name."""
        resp = self.session.get(f"{self.base_url}/api/database")
        if resp.status_code != 200:
            return None
        databases = resp.json()
        for db in databases.get("data", []):
            if db.get("name") == name:
                return db
        return None

    def create_database(self, name: str, details: dict) -> Optional[dict]:
        """Create a database connection."""
        payload = {
            "name": name,
            "engine": "postgres",
            "details": details,
            "is_on_demand": False
        }
        resp = self.session.post(
            f"{self.base_url}/api/database",
            json=payload
        )
        if resp.status_code not in (200, 201):
            print(f"✗ Failed to create database: {resp.text}")
            return None
        db = resp.json()
        print(f"✓ Created database: {name} (ID: {db.get('id')})")
        return db

    def sync_database(self, database_id: int) -> bool:
        """Trigger database metadata sync."""
        resp = self.session.post(
            f"{self.base_url}/api/database/{database_id}/sync_schema"
        )
        if resp.status_code != 200:
            print(f"✗ Failed to sync database: {resp.text}")
            return False
        print(f"✓ Syncing database {database_id}...")
        return True

    def create_question(self, name: str, description: str, database_id: int, query: str, collection_id: Optional[int] = None) -> Optional[dict]:
        """Create a saved question (SQL query)."""
        payload = {
            "name": name,
            "description": description,
            "database_id": database_id,
            "dataset_query": {
                "type": "native",
                "native": {
                    "query": query
                },
                "database": database_id
            },
            "collection_id": collection_id,
            "visualization_settings": {}
        }
        resp = self.session.post(
            f"{self.base_url}/api/card",
            json=payload
        )
        if resp.status_code not in (200, 201):
            print(f"✗ Failed to create question: {resp.text}")
            return None
        card = resp.json()
        print(f"✓ Created question: {name} (ID: {card.get('id')})")
        return card

    def create_collection(self, name: str, description: str = "") -> Optional[dict]:
        """Create a collection (folder)."""
        payload = {
            "name": name,
            "description": description,
            "color": "#509EE3"
        }
        resp = self.session.post(
            f"{self.base_url}/api/collection",
            json=payload
        )
        if resp.status_code not in (200, 201):
            print(f"✗ Failed to create collection: {resp.text}")
            return None
        col = resp.json()
        print(f"✓ Created collection: {name} (ID: {col.get('id')})")
        return col

    def create_dashboard(self, name: str, description: str = "", collection_id: Optional[int] = None) -> Optional[dict]:
        """Create a dashboard."""
        payload = {
            "name": name,
            "description": description,
            "collection_id": collection_id
        }
        resp = self.session.post(
            f"{self.base_url}/api/dashboard",
            json=payload
        )
        if resp.status_code not in (200, 201):
            print(f"✗ Failed to create dashboard: {resp.text}")
            return None
        dash = resp.json()
        print(f"✓ Created dashboard: {name} (ID: {dash.get('id')})")
        return dash

    def add_card_to_dashboard(self, dashboard_id: int, card_id: int, row: int = 0, col: int = 0, size_x: int = 4, size_y: int = 3) -> bool:
        """Add a card (question) to a dashboard."""
        payload = {
            "card_id": card_id,
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y
        }
        resp = self.session.post(
            f"{self.base_url}/api/dashboard/{dashboard_id}/cards",
            json=payload
        )
        if resp.status_code not in (200, 201):
            print(f"✗ Failed to add card to dashboard: {resp.text}")
            return False
        return True


def main():
    api = MetabaseAPI(METABASE_URL)

    print("=" * 70)
    print("Arada Intelligence OS — Metabase Setup")
    print("=" * 70)
    print()

    # Step 1: Wait for Metabase to be healthy
    print("Step 1: Waiting for Metabase...")
    try:
        api.wait_for_health(timeout=120)
    except TimeoutError as e:
        print(f"✗ {e}")
        sys.exit(1)
    print()

    # Step 2: Login
    print("Step 2: Authenticating...")
    if not api.login(METABASE_ADMIN_EMAIL, METABASE_ADMIN_PASSWORD):
        print("✗ Authentication failed")
        sys.exit(1)
    print()

    # Step 3: Create or find database
    print("Step 3: Setting up database connection...")
    db = api.get_database("Arada Analytics")
    if db:
        print(f"✓ Database already exists (ID: {db['id']})")
        database_id = db["id"]
    else:
        db_details = {
            "host": DB_HOST,
            "port": int(DB_PORT),
            "dbname": DB_NAME,
            "user": DB_USER,
            "password": DB_PASSWORD,
            "ssl": False
        }
        db = api.create_database("Arada Analytics", db_details)
        if not db:
            print("✗ Failed to create database")
            sys.exit(1)
        database_id = db["id"]
        time.sleep(2)
        api.sync_database(database_id)
        time.sleep(5)  # Wait for sync to complete
    print()

    # Step 4: Create collections
    print("Step 4: Creating collections...")
    content_col = api.create_collection("Content Analytics", "Content performance dashboards")
    publish_col = api.create_collection("Publishing Metrics", "Publishing & distribution analytics")
    workflow_col = api.create_collection("Workflow Performance", "Job processing metrics")
    business_col = api.create_collection("Business Metrics", "User growth, revenue, engagement")
    print()

    # Step 5: Create questions (saved queries)
    print("Step 5: Creating saved questions...")

    questions = [
        (
            content_col["id"],
            "Top Scoring Items",
            "Items ranked by final content score",
            """
            SELECT
              ni.id,
              ni.title,
              ni.url,
              cs.final_score,
              cs.relevance_score,
              cs.engagement_score,
              COUNT(DISTINCT pr.id) as publish_count,
              ni.created_at
            FROM content.normalized_items ni
            LEFT JOIN content.content_scores cs ON ni.id = cs.item_id
            LEFT JOIN analytics.publish_results pr ON ni.id = pr.video_id
            WHERE ni.deleted_at IS NULL
            GROUP BY ni.id, cs.id
            ORDER BY cs.final_score DESC
            LIMIT 100;
            """
        ),
        (
            publish_col["id"],
            "Publishing Success Rate",
            "Success rate by platform over time",
            """
            SELECT
              DATE(pj.created_at) as date,
              COALESCE(pj.platforms::text, 'unknown') as platform,
              COUNT(DISTINCT pj.id) as jobs,
              ROUND(100.0 * COUNT(DISTINCT CASE WHEN pj.status = 'completed' THEN pj.id END) / NULLIF(COUNT(DISTINCT pj.id), 0), 2) as success_rate
            FROM analytics.publish_jobs pj
            WHERE pj.deleted_at IS NULL
            GROUP BY DATE(pj.created_at), pj.platforms
            ORDER BY date DESC;
            """
        ),
        (
            workflow_col["id"],
            "Job Processing Time",
            "Average duration by job type",
            """
            SELECT
              j.job_type,
              COUNT(*) as count,
              ROUND(AVG(EXTRACT(EPOCH FROM (j.completed_at - j.created_at))), 2) as avg_duration_sec,
              ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (j.completed_at - j.created_at))), 2) as p95_duration_sec
            FROM workflow.jobs j
            WHERE j.completed_at IS NOT NULL
            GROUP BY j.job_type
            ORDER BY avg_duration_sec DESC;
            """
        ),
        (
            business_col["id"],
            "User Growth",
            "New users and active users by day",
            """
            SELECT
              DATE(created_at) as date,
              COUNT(*) as new_users,
              COUNT(DISTINCT CASE WHEN last_login_at > NOW() - INTERVAL '7 days' THEN id END) as active_7d
            FROM auth.users
            WHERE deleted_at IS NULL
            GROUP BY DATE(created_at)
            ORDER BY date DESC;
            """
        ),
        (
            business_col["id"],
            "Content Trend",
            "Items created and avg score by week",
            """
            SELECT
              DATE_TRUNC('week', ni.created_at)::DATE as week,
              COUNT(DISTINCT ni.id) as items,
              ROUND(AVG(cs.final_score), 2) as avg_score
            FROM content.normalized_items ni
            LEFT JOIN content.content_scores cs ON ni.id = cs.item_id
            WHERE ni.deleted_at IS NULL
            GROUP BY DATE_TRUNC('week', ni.created_at)
            ORDER BY week DESC;
            """
        ),
    ]

    question_ids = {}
    for col_id, q_name, q_desc, q_sql in questions:
        card = api.create_question(q_name, q_desc, database_id, q_sql, col_id)
        if card:
            question_ids[q_name] = card["id"]
    print()

    # Step 6: Create dashboards
    print("Step 6: Creating dashboards...")

    exec_dash = api.create_dashboard(
        "Executive Summary",
        "High-level KPIs and trends",
        business_col["id"]
    )

    content_dash = api.create_dashboard(
        "Content Ops",
        "Content performance and scoring",
        content_col["id"]
    )

    publish_dash = api.create_dashboard(
        "Publishing Performance",
        "Publishing success metrics",
        publish_col["id"]
    )

    workflow_dash = api.create_dashboard(
        "Workflow Performance",
        "Job processing metrics",
        workflow_col["id"]
    )
    print()

    # Step 7: Add cards to dashboards
    print("Step 7: Adding cards to dashboards...")
    if exec_dash:
        if "User Growth" in question_ids:
            api.add_card_to_dashboard(exec_dash["id"], question_ids["User Growth"], 0, 0)
        if "Content Trend" in question_ids:
            api.add_card_to_dashboard(exec_dash["id"], question_ids["Content Trend"], 0, 4)

    if content_dash:
        if "Top Scoring Items" in question_ids:
            api.add_card_to_dashboard(content_dash["id"], question_ids["Top Scoring Items"], 0, 0)

    if publish_dash:
        if "Publishing Success Rate" in question_ids:
            api.add_card_to_dashboard(publish_dash["id"], question_ids["Publishing Success Rate"], 0, 0)

    if workflow_dash:
        if "Job Processing Time" in question_ids:
            api.add_card_to_dashboard(workflow_dash["id"], question_ids["Job Processing Time"], 0, 0)
    print()

    # Step 8: Summary
    print("=" * 70)
    print("✓ Metabase setup complete!")
    print("=" * 70)
    print()
    print(f"Access Metabase: {METABASE_URL}")
    print(f"Email: {METABASE_ADMIN_EMAIL}")
    print()
    print("Next steps:")
    print("  1. Open Metabase in browser")
    print("  2. Navigate to collections (left sidebar)")
    print("  3. Explore pre-built dashboards")
    print("  4. Create additional questions as needed")
    print()


if __name__ == "__main__":
    main()
