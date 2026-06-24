"""
Locust load test for ResearcherHQ backend.

Usage (via run_load_test.sh, or manually):
  locust -f load_tests/locustfile.py --headless -u 50 -r 5 -t 2m \
         --host http://localhost:8000 \
         --html load_tests/reports/report.html
"""
import random
from locust import HttpUser, task, between

TEST_PASSWORD = "LoadTest123!"
TEST_EMAILS = [f"loadtest{i}@researcherhq-test.com" for i in range(1, 11)]

SAMPLE_QUERIES = [
    "Apakah metodologi kajian yang digunakan?",
    "Ringkaskan dapatan utama kajian ini.",
    "Apakah jurang kajian yang dikenal pasti?",
    "Siapakah populasi kajian ini?",
    "Bagaimana data dikumpul dalam kajian ini?",
]


class ResearcherHQUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.token = None
        self.project_id = None
        email = random.choice(TEST_EMAILS)
        r = self.client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
        if r.status_code != 200:
            return
        self.token = r.json()["access_token"]
        projects_r = self.client.get("/projects", headers=self._h())
        if projects_r.status_code == 200:
            projects = projects_r.json()
            if projects:
                self.project_id = projects[0]["id"]

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    @task(40)
    def rag_query(self):
        if not self.project_id or not self.token:
            return
        self.client.post(
            f"/projects/{self.project_id}/query",
            json={"query": random.choice(SAMPLE_QUERIES), "output_mode": "qa"},
            headers=self._h(),
            name="/projects/{id}/query",
        )

    @task(20)
    def upload_document(self):
        if not self.project_id or not self.token:
            return
        with self.client.post(
            "/documents/upload",
            json={
                "project_id": self.project_id,
                "filename": f"doc_{random.randint(1000, 9999)}.pdf",
                "category": "artikel",
                "pages": [
                    {"page_number": i + 1, "text": " ".join(["perkataan"] * 150)}
                    for i in range(2)
                ],
            },
            headers=self._h(),
            name="/documents/upload",
            catch_response=True,
        ) as resp:
            # 403 = quota limit hit (expected business logic), not a test failure
            if resp.status_code in (200, 201, 403):
                resp.success()
            # 429 = rate limit (also expected), mark success
            elif resp.status_code == 429:
                resp.success()

    @task(20)
    def chapter_operations(self):
        if not self.project_id or not self.token:
            return
        r = self.client.get(
            f"/projects/{self.project_id}/chapters",
            headers=self._h(),
            name="/projects/{id}/chapters",
        )
        if r.status_code == 200 and r.json():
            chapter_id = r.json()[0]["id"]
            self.client.get(
                f"/projects/{self.project_id}/chapters/{chapter_id}",
                headers=self._h(),
                name="/projects/{id}/chapters/{id}",
            )

    @task(10)
    def auth_profile(self):
        if not self.token:
            return
        self.client.get("/account", headers=self._h(), name="/account")

    @task(10)
    def journal_search(self):
        if not self.token or not self.project_id:
            return
        q = random.choice(["machine learning", "qualitative", "methodology"])
        self.client.get(
            f"/search/articles?q={q}&project_id={self.project_id}",
            headers=self._h(),
            name="/search/articles",
        )
