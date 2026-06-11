"""Integration tests for Analytics API endpoints."""
import pytest
from uuid import uuid4
from datetime import date, timedelta
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestMetricsEndpoints:
    """Test custom metrics API endpoints."""

    @pytest.mark.integration
    def test_list_metrics_endpoint(self, auth_headers):
        """Test GET /analytics/metrics endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/analytics/metrics?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "metrics" in data

    @pytest.mark.integration
    def test_create_metric_endpoint(self, auth_headers):
        """Test POST /analytics/metrics endpoint."""
        workspace_id = uuid4()

        response = client.post(
            "/analytics/metrics",
            json={
                "workspace_id": str(workspace_id),
                "name": "engagement_rate",
                "definition": "SELECT COUNT(*) FROM content.normalized_items",
                "metric_type": "count",
                "dimension": "daily",
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 400, 401, 403, 422]

    @pytest.mark.integration
    def test_get_metric_data_endpoint(self, auth_headers):
        """Test GET /analytics/metrics/{id}/data endpoint."""
        workspace_id = uuid4()
        metric_id = uuid4()
        start_date = (date.today() - timedelta(days=7)).isoformat()
        end_date = date.today().isoformat()

        response = client.get(
            f"/analytics/metrics/{metric_id}/data"
            f"?workspace_id={workspace_id}&start_date={start_date}&end_date={end_date}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 401, 403]

    @pytest.mark.integration
    def test_delete_metric_endpoint(self, auth_headers):
        """Test DELETE /analytics/metrics/{id} endpoint."""
        workspace_id = uuid4()
        metric_id = uuid4()

        response = client.delete(
            f"/analytics/metrics/{metric_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 401, 403]


class TestCohortEndpoints:
    """Test cohort analysis API endpoints."""

    @pytest.mark.integration
    def test_list_cohorts_endpoint(self, auth_headers):
        """Test GET /analytics/cohorts endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/analytics/cohorts?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "cohorts" in data

    @pytest.mark.integration
    def test_create_cohort_endpoint(self, auth_headers):
        """Test POST /analytics/cohorts endpoint."""
        workspace_id = uuid4()

        response = client.post(
            "/analytics/cohorts",
            json={
                "workspace_id": str(workspace_id),
                "name": "power_users",
                "criteria": {"engagement_rate": {">": 0.1}},
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 400, 401, 403, 422]

    @pytest.mark.integration
    def test_get_cohort_metrics_endpoint(self, auth_headers):
        """Test GET /analytics/cohorts/{id}/metrics endpoint."""
        workspace_id = uuid4()
        cohort_id = uuid4()

        response = client.get(
            f"/analytics/cohorts/{cohort_id}/metrics"
            f"?workspace_id={workspace_id}&metric_names=engagement_rate&metric_names=churn_rate",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 401, 403]

    @pytest.mark.integration
    def test_update_cohort_endpoint(self, auth_headers):
        """Test PUT /analytics/cohorts/{id} endpoint."""
        workspace_id = uuid4()
        cohort_id = uuid4()

        response = client.put(
            f"/analytics/cohorts/{cohort_id}?workspace_id={workspace_id}",
            json={
                "name": "updated_cohort",
                "criteria": {"engagement_rate": {">": 0.2}},
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 401, 403, 422]


class TestAttributionEndpoints:
    """Test attribution API endpoints."""

    @pytest.mark.integration
    def test_get_attribution_report_endpoint(self, auth_headers):
        """Test GET /analytics/attribution endpoint."""
        workspace_id = uuid4()
        conversion_id = uuid4()

        response = client.get(
            f"/analytics/attribution?workspace_id={workspace_id}&conversion_id={conversion_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 401, 403]

    @pytest.mark.integration
    def test_change_attribution_model_endpoint(self, auth_headers):
        """Test POST /analytics/attribution/model endpoint."""
        workspace_id = uuid4()
        conversion_id = uuid4()

        response = client.post(
            "/analytics/attribution/model",
            json={
                "workspace_id": str(workspace_id),
                "conversion_id": str(conversion_id),
                "model": "linear",
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 400, 401, 403, 422]


class TestPredictionEndpoints:
    """Test predictive KPI endpoints."""

    @pytest.mark.integration
    def test_list_predictions_endpoint(self, auth_headers):
        """Test GET /analytics/predictions endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/analytics/predictions?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "predictions" in data

    @pytest.mark.integration
    def test_predict_churn_endpoint(self, auth_headers):
        """Test GET /analytics/predictions/churn endpoint."""
        workspace_id = uuid4()
        user_id = uuid4()

        response = client.get(
            f"/analytics/predictions/churn"
            f"?workspace_id={workspace_id}&user_id={user_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "prediction" in data

    @pytest.mark.integration
    def test_predict_ltv_endpoint(self, auth_headers):
        """Test GET /analytics/predictions/ltv endpoint."""
        workspace_id = uuid4()
        user_id = uuid4()

        response = client.get(
            f"/analytics/predictions/ltv"
            f"?workspace_id={workspace_id}&user_id={user_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "prediction" in data


class TestDashboardEndpoints:
    """Test dashboard endpoints."""

    @pytest.mark.integration
    def test_get_dashboard_endpoint(self, auth_headers):
        """Test GET /analytics/dashboard endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/analytics/dashboard?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "metrics" in data
            assert "cohorts" in data
            assert "predictions" in data

    @pytest.mark.integration
    def test_refresh_dashboard_endpoint(self, auth_headers):
        """Test POST /analytics/dashboard/refresh endpoint."""
        workspace_id = uuid4()

        response = client.post(
            f"/analytics/dashboard/refresh?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]
