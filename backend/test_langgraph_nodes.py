import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.agent_graph import LangGraphWorkflow, VideoGraphState

SAMPLE_LONG_TRANSCRIPT = """
[00:00] [Music] Welcome everyone to this comprehensive guide on building web applications with Python.
[00:06] Today we are going to demonstrate how to set up your project step by step.
[00:12] First, open your terminal and install the required libraries by running pip install starlette uvicorn.
[00:20] We strongly recommend creating a dedicated virtual environment so that your package dependencies remain isolated.
[00:30] [Applause] Next, make sure you configure your main entry point run.py with uvicorn.run.
[00:40] To demonstrate the workflow, let's create our routing table and start the application server on port 8000.
[00:52] Always remember to enable CORS middleware if your frontend is served from a different domain.
[01:05] [Music] Finally, verify the server response using curl or by opening http://localhost:8000 in your browser.
"""

def test_each_node():
    workflow = LangGraphWorkflow()
    
    print("=" * 60)
    print("LANGGRAPH NODE-BY-NODE VERIFICATION")
    print("=" * 60)

    # Initial shared state
    state: VideoGraphState = {
        "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "video_id": "dQw4w9WgXcQ",
        "title": "Building Web Applications in Python",
        "author": "Python Developer",
        "thumbnail_url": "https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        "transcript": SAMPLE_LONG_TRANSCRIPT,
        "errors": []
    }

    # 1. Test validate_transcript node
    t0 = time.time()
    state = workflow.validate_transcript(state)
    el = time.time() - t0
    assert len(state.get("errors", [])) == 0, f"Validation failed: {state.get('errors')}"
    print(f"1. validate_transcript node:  [PASS] ({el:.4f}s) -> Valid transcript confirmed.")

    # 2. Test clean_transcript node
    t0 = time.time()
    state = workflow.clean_transcript(state)
    el = time.time() - t0
    cleaned = state.get("cleaned_transcript", "")
    assert "[Music]" not in cleaned and "[Applause]" not in cleaned, "Noise tokens not cleaned"
    assert len(cleaned.splitlines()) >= 5, "Cleaned transcript lines count incorrect"
    print(f"2. clean_transcript node:     [PASS] ({el:.4f}s) -> Removed audio markers ([Music], [Applause]), {len(cleaned.splitlines())} lines.")

    # 3. Test chunk_transcript node
    t0 = time.time()
    state = workflow.chunk_transcript(state, max_words=50, overlap_words=10)
    el = time.time() - t0
    chunks = state.get("chunks", [])
    assert len(chunks) >= 2, f"Expected multiple chunks, got {len(chunks)}"
    print(f"3. chunk_transcript node:     [PASS] ({el:.4f}s) -> Created {len(chunks)} chunks for chunked processing.")

    # 4. Test summarize_chunks node
    t0 = time.time()
    state = workflow.summarize_chunks(state)
    el = time.time() - t0
    summaries = state.get("summaries", [])
    assert len(summaries) == len(chunks), f"Expected {len(chunks)} summaries, got {len(summaries)}"
    print(f"4. summarize_chunks node:     [PASS] ({el:.4f}s) -> Summarized {len(summaries)} chunks independently.")

    # 5. Test extract_actions node
    t0 = time.time()
    state = workflow.extract_actions(state)
    el = time.time() - t0
    actions = state.get("actions", [])
    assert len(actions) > 0, "No actions extracted"
    for a in actions:
        assert a.get("action_type") in ("demonstrated", "recommended", "instructional"), f"Invalid action_type: {a.get('action_type')}"
    print(f"5. extract_actions node:       [PASS] ({el:.4f}s) -> Extracted {len(actions)} raw actions with strict type classification.")

    # 6. Test deduplicate_actions node
    t0 = time.time()
    state = workflow.deduplicate_actions(state)
    el = time.time() - t0
    deduped = state.get("actions", [])
    assert len(deduped) > 0, "Deduplication emptied actions"
    print(f"6. deduplicate_actions node:  [PASS] ({el:.4f}s) -> Consolidated to {len(deduped)} distinct action items.")

    # 7. Test final_review node
    t0 = time.time()
    state = workflow.final_review(state)
    el = time.time() - t0
    assert state.get("overview"), "Overview is missing"
    assert state.get("final_summary"), "Final summary is missing"
    assert len(state.get("action_checklist", [])) > 0, "Checklist is empty"
    print(f"7. final_review node:         [PASS] ({el:.4f}s) -> Synthesized overview, topics, key points, and checklist ({len(state['action_checklist'])} items).")

    # 8. Test generate_pdf node
    t0 = time.time()
    state = workflow.generate_pdf(state)
    el = time.time() - t0
    pdf_path = state.get("pdf_path")
    assert pdf_path and os.path.exists(pdf_path), f"PDF file not generated at {pdf_path}"
    file_size = os.path.getsize(pdf_path)
    assert file_size > 500, f"PDF file size too small: {file_size}"
    print(f"8. generate_pdf node:         [PASS] ({el:.4f}s) -> Generated PDF report ({file_size:,} bytes at {os.path.basename(pdf_path)}).")

    # 9. Test Complete Graph Execution
    print("\n" + "=" * 60)
    print("COMPLETE LANGGRAPH WORKFLOW END-TO-END")
    print("=" * 60)
    t0 = time.time()
    fresh_state: VideoGraphState = {
        "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "video_id": "dQw4w9WgXcQ",
        "title": "Building Web Applications in Python",
        "author": "Python Developer",
        "transcript": SAMPLE_LONG_TRANSCRIPT,
        "errors": []
    }
    final_result = workflow.run(fresh_state)
    el = time.time() - t0
    assert len(final_result.get("errors", [])) == 0, f"Errors in workflow: {final_result.get('errors')}"
    assert final_result.get("pdf_path") and os.path.exists(final_result["pdf_path"])
    print(f"End-to-End Graph Execution:  [PASS] ({el:.4f}s)")
    print(f"Overview: {final_result['overview'][:80]}...")
    print(f"Actions count: {len(final_result['actions'])}")
    print(f"Checklist count: {len(final_result['action_checklist'])}")
    print(f"PDF Output: {final_result['pdf_path']}")

if __name__ == "__main__":
    test_each_node()
