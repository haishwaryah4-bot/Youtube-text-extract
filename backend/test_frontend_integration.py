import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from starlette.testclient import TestClient
from backend.main import app

def test_frontend_integration():
    client = TestClient(app)

    print("=== 1. VERIFY FRONTEND STATIC ASSETS SERVING ===")
    r_index = client.get("/")
    assert r_index.status_code == 200, f"Expected 200, got {r_index.status_code}"
    assert "TubeAction" in r_index.text
    assert 'id="youtubeUrl"' in r_index.text
    assert 'id="btnProcess"' in r_index.text
    assert 'id="progressSection"' in r_index.text
    assert 'id="errorSection"' in r_index.text
    assert 'id="resultsSection"' in r_index.text
    assert 'id="btnDownloadPdf"' in r_index.text
    print("Index HTML asset verification: PASS")

    r_js = client.get("/app.js")
    assert r_js.status_code == 200
    assert "/api/youtube/analyze" in r_js.text
    print("App.js asset & endpoint connection verification: PASS")

    print("\n=== 2. VERIFY MOCKED SUCCESS FLOW & SCHEMA (All 14 UI Points) ===")
    sample_t = """
    [00:00] First prepare the beans and hot water.
    [00:15] Grind 15 grams to medium consistency.
    [00:30] Make sure not to spill boiling water on your skin.
    [00:45] Pour 50g water in circular motions.
    """

    resp_succ = client.post("/api/youtube/analyze", json={
        "youtube_url": "https://www.youtube.com/watch?v=1oB1oDrDkHM",
        "transcript": sample_t
    })

    assert resp_succ.status_code == 200
    data_succ = resp_succ.json()

    assert data_succ["success"] is True
    assert data_succ["video_id"] == "1oB1oDrDkHM"
    assert data_succ["transcript_status"] == "success"
    assert data_succ["summary"] is not None
    assert isinstance(data_succ["key_points"], list)
    assert isinstance(data_succ["demonstrated_actions"], list)
    assert isinstance(data_succ["recommended_actions"], list)
    assert isinstance(data_succ["tools_materials"], list)
    assert isinstance(data_succ["precautions"], list)
    assert data_succ["pdf_path"] is not None
    assert data_succ["error"] is None

    print("Success Response Verification: PASS")
    print("Video Title:", data_succ["title"])
    print("Author:", data_succ["author"])
    print("Transcript Status:", data_succ["transcript_status"])
    print("Summary:", data_succ["summary"][:60] + "...")
    print("PDF Path:", data_succ["pdf_path"])

    print("\n=== 3. VERIFY PDF SERVING & DOWNLOAD ENDPOINT ===")
    vid = data_succ["video_id"]
    pdf_url = f"/api/pdf/{vid}"
    r_pdf = client.get(pdf_url)
    assert r_pdf.status_code == 200
    assert r_pdf.headers.get("content-type") == "application/pdf"
    print(f"PDF endpoint ({pdf_url}) verification: PASS (Content-Type: application/pdf)")

    print("\n=== 4. VERIFY TRANSCRIPT-UNAVAILABLE & RATE-LIMITED FLOW ===")
    resp_fail = client.post("/api/youtube/analyze", json={
        "youtube_url": "https://www.youtube.com/watch?v=00000000000"
    })
    data_fail = resp_fail.json()
    assert data_fail["success"] is False
    assert data_fail["transcript_status"] != "success"
    assert data_fail["error"] is not None
    assert data_fail["pdf_path"] is None
    print("Unavailable / Error Flow verification: PASS")
    print("Error reported:", data_fail["error"])

    print("\nALL FRONTEND INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_frontend_integration()
