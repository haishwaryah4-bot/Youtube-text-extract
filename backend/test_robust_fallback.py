import sys
import os
import time
from unittest.mock import MagicMock, patch
from pathlib import Path

# Project-relative import
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.youtube_service import YouTubeService, YouTubeServiceError, TranscriptManager, PrimaryTranscriptProvider, FallbackTranscriptProvider
from backend.models import TranscriptResult
from backend.agent_graph import run_youtube_analysis, compiled_graph

def test_1_import():
    print("\n" + "=" * 50)
    print("TEST 1: Import Verification")
    print("=" * 50)
    try:
        import backend.youtube_service
        import backend.agent_graph
        import backend.models
        import backend.main
        print("Status: PASS")
        return True
    except Exception as e:
        print(f"Status: FAIL. Exception: {e}")
        return False

def test_2_service_unit_rate_limit():
    print("\n" + "=" * 50)
    print("TEST 2: Mocked Rate-Limit Failure & Fallback Trigger")
    print("=" * 50)
    
    # Mock Primary provider to fail with rate_limited
    mock_primary = MagicMock()
    mock_primary.name = "MockPrimary"
    mock_primary.get_transcript.return_value = TranscriptResult(
        transcript=None,
        raw_segments=[],
        word_count=0,
        status="rate_limited",
        provider="MockPrimary",
        error="YouTube is rate-limiting."
    )
    
    # Mock Fallback provider to also fail
    mock_fallback = MagicMock()
    mock_fallback.name = "MockFallback"
    mock_fallback.get_transcript.return_value = TranscriptResult(
        transcript=None,
        raw_segments=[],
        word_count=0,
        status="captions_unavailable",
        provider="MockFallback",
        error="Captions unavailable."
    )
    
    manager = TranscriptManager(providers=[mock_primary, mock_fallback])
    res = manager.fetch_transcript("dQw4w9WgXcQ")
    
    # Ensure both were called because rate_limited in primary triggers fallback now
    primary_called = mock_primary.get_transcript.called
    fallback_called = mock_fallback.get_transcript.called
    
    print(f"Primary called: {primary_called}")
    print(f"Fallback called: {fallback_called}")
    print(f"Result Status: {res.status}")
    print(f"Result Error: {res.error}")
    
    if primary_called and fallback_called and res.status == "captions_unavailable":
        print("Status: PASS")
        return True
    else:
        print("Status: FAIL")
        return False

def test_3_fallback_success():
    print("\n" + "=" * 50)
    print("TEST 3: Fallback Success with Mocked Primary Failure")
    print("=" * 50)
    
    mock_primary = MagicMock()
    mock_primary.name = "MockPrimary"
    mock_primary.get_transcript.return_value = TranscriptResult(
        transcript=None,
        raw_segments=[],
        word_count=0,
        status="rate_limited",
        provider="MockPrimary",
        error="YouTube is rate-limiting."
    )
    
    mock_fallback = MagicMock()
    mock_fallback.name = "MockFallback"
    mock_fallback.get_transcript.return_value = TranscriptResult(
        transcript="[00:00] Actual transcript contents here.",
        raw_segments=[{"text": "Actual transcript contents here.", "start": 0.0, "duration": 2.0}],
        word_count=4,
        status="success",
        provider="MockFallback",
        error=None
    )
    
    manager = TranscriptManager(providers=[mock_primary, mock_fallback])
    res = manager.fetch_transcript("dQw4w9WgXcQ")
    
    print(f"Result Status: {res.status}")
    print(f"Result Provider: {res.provider}")
    print(f"Result Transcript: {res.transcript}")
    
    if res.status == "success" and res.provider == "MockFallback" and res.transcript is not None:
        print("Status: PASS")
        return True
    else:
        print("Status: FAIL")
        return False

def test_4_unavailable_transcript():
    print("\n" + "=" * 50)
    print("TEST 4: Unavailable Transcript handling")
    print("=" * 50)
    
    mock_primary = MagicMock()
    mock_primary.name = "MockPrimary"
    mock_primary.get_transcript.return_value = TranscriptResult(
        transcript=None,
        raw_segments=[],
        word_count=0,
        status="rate_limited",
        provider="MockPrimary",
        error="YouTube is rate-limiting."
    )
    
    mock_fallback = MagicMock()
    mock_fallback.name = "MockFallback"
    mock_fallback.get_transcript.return_value = TranscriptResult(
        transcript=None,
        raw_segments=[],
        word_count=0,
        status="rate_limited",
        provider="MockFallback",
        error="YouTube is rate-limiting fallback too."
    )
    
    manager = TranscriptManager(providers=[mock_primary, mock_fallback])
    
    # Temporarily patch the singleton _transcript_manager in youtube_service
    with patch("backend.youtube_service._transcript_manager", manager):
        # We also mock video metadata to prevent external network calls during this unit test
        with patch("backend.youtube_service.YouTubeService.fetch_video_metadata") as mock_meta:
            mock_meta.return_value = {
                "video_id": "dQw4w9WgXcQ",
                "title": "Mock Video Title",
                "author": "Mock Video Author",
                "thumbnail_url": "http://example.com/thumb.jpg"
            }
            
            res = run_youtube_analysis(youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            
            print(f"Workflow Success field: {res.get('success')}")
            print(f"Workflow Transcript Status: {res.get('transcript_status')}")
            print(f"Workflow Error: {res.get('error')}")
            
            expected_err = "YouTube is currently rate-limiting automated transcript requests. Transcript-based analysis is unavailable for this video at the moment."
            if res.get("transcript_status") == "unavailable" and res.get("error") == expected_err:
                print("Status: PASS")
                return True
            else:
                print("Status: FAIL")
                return False

def test_5_langgraph_routing():
    print("\n" + "=" * 50)
    print("TEST 5: LangGraph routing test (Halts at END when unavailable)")
    print("=" * 50)
    
    mock_primary = MagicMock()
    mock_primary.name = "MockPrimary"
    mock_primary.get_transcript.return_value = TranscriptResult(
        transcript=None,
        raw_segments=[],
        word_count=0,
        status="rate_limited",
        provider="MockPrimary",
        error="Rate limited"
    )
    
    mock_fallback = MagicMock()
    mock_fallback.name = "MockFallback"
    mock_fallback.get_transcript.return_value = TranscriptResult(
        transcript=None,
        raw_segments=[],
        word_count=0,
        status="rate_limited",
        provider="MockFallback",
        error="Rate limited"
    )
    
    manager = TranscriptManager(providers=[mock_primary, mock_fallback])
    
    with patch("backend.youtube_service._transcript_manager", manager):
        with patch("backend.youtube_service.YouTubeService.fetch_video_metadata") as mock_meta:
            mock_meta.return_value = {
                "video_id": "dQw4w9WgXcQ",
                "title": "Mock Video Title",
                "author": "Mock Video Author",
                "thumbnail_url": "http://example.com/thumb.jpg"
            }
            
            # Spy on downstream nodes to verify they are NOT executed
            # Nodes: summarize_content, extract_actions, generate_pdf
            with patch("backend.agent_graph.summarize_content", side_effect=AssertionError("summarize_content node should not be called!")) as mock_sum, \
                 patch("backend.agent_graph.extract_actions", side_effect=AssertionError("extract_actions node should not be called!")) as mock_act, \
                 patch("backend.agent_graph.generate_pdf", side_effect=AssertionError("generate_pdf node should not be called!")) as mock_pdf:
                
                try:
                    res = run_youtube_analysis(youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
                    print(f"Workflow completed successfully without calling downstream nodes.")
                    print(f"State keys populated: {list(res.keys())}")
                    
                    # Verify no fake data generated in summaries, actions, overview
                    assert not res.get("summary")
                    assert not res.get("overview")
                    assert not res.get("final_summary")
                    assert not res.get("actions")
                    assert not res.get("action_checklist")
                    assert res.get("transcript_status") == "unavailable"
                    
                    print("No fake data protection verified.")
                    print("Status: PASS")
                    return True
                except Exception as e:
                    print(f"Status: FAIL. Exception: {e}")
                    return False

if __name__ == "__main__":
    t1 = test_1_import()
    t2 = test_2_service_unit_rate_limit()
    t3 = test_3_fallback_success()
    t4 = test_4_unavailable_transcript()
    t5 = test_5_langgraph_routing()
    
    print("\n" + "=" * 50)
    print(f"ROBUST FALLBACK SUMMARY: {'ALL 5 TESTS PASSED' if all([t1, t2, t3, t4, t5]) else 'SOME TESTS FAILED'}")
    print("=" * 50)
    
    if all([t1, t2, t3, t4, t5]):
        sys.exit(0)
    else:
        sys.exit(1)
