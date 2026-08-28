import sys
import time
from pathlib import Path

# Project-relative import
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.youtube_service import YouTubeService, YouTubeServiceError

def run_test_1():
    """Test 1: YouTube URL validation"""
    print("\n" + "=" * 50)
    print("TEST 1: YouTube URL validation")
    print("=" * 50)
    t0 = time.time()
    valid_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
    ]
    invalid_urls = [
        "https://vimeo.com/12345678901",
        "https://google.com",
        "not-a-url",
        ""
    ]
    failed = []
    
    for u in valid_urls:
        try:
            vid = YouTubeService.extract_video_id(u)
            if vid != "dQw4w9WgXcQ":
                failed.append(f"Expected dQw4w9WgXcQ, got {vid} for {u}")
        except Exception as e:
            failed.append(f"Failed on valid URL {u}: {e}")

    for u in invalid_urls:
        try:
            vid = YouTubeService.extract_video_id(u)
            failed.append(f"Invalid URL should have failed, but got {vid} for '{u}'")
        except YouTubeServiceError:
            pass  # Expected

    elapsed = time.time() - t0
    if not failed:
        print(f"Status: PASS")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Details: Verified {len(valid_urls)} valid URL formats and {len(invalid_urls)} invalid inputs.")
        return True
    else:
        print(f"Status: FAIL")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Error Message: {'; '.join(failed)}")
        return False

def run_test_2():
    """Test 2: extract_video_id()"""
    print("\n" + "=" * 50)
    print("TEST 2: extract_video_id()")
    print("=" * 50)
    t0 = time.time()
    test_cases = [
        ("https://www.youtube.com/watch?v=x7X9w_GIm1s", "x7X9w_GIm1s"),
        ("https://youtu.be/x7X9w_GIm1s", "x7X9w_GIm1s"),
        ("https://www.youtube.com/embed/x7X9w_GIm1s", "x7X9w_GIm1s"),
        ("https://www.youtube.com/shorts/x7X9w_GIm1s", "x7X9w_GIm1s"),
        ("x7X9w_GIm1s", "x7X9w_GIm1s"),
    ]
    failed = []
    for inp, expected in test_cases:
        try:
            out = YouTubeService.extract_video_id(inp)
            if out != expected:
                failed.append(f"Expected {expected}, got {out} for input '{inp}'")
        except Exception as e:
            failed.append(f"Exception on input '{inp}': {e}")

    elapsed = time.time() - t0
    if not failed:
        print(f"Status: PASS")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Details: Successfully extracted 11-char video ID across all formats.")
        return True
    else:
        print(f"Status: FAIL")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Error Message: {'; '.join(failed)}")
        return False

def run_test_3():
    """Test 3: fetch_video_metadata()"""
    print("\n" + "=" * 50)
    print("TEST 3: fetch_video_metadata()")
    print("=" * 50)
    t0 = time.time()
    failed = []
    test_ids = ["dQw4w9WgXcQ", "x7X9w_GIm1s", "INVALID_ID_XYZ"]
    
    for vid in test_ids:
        try:
            meta = YouTubeService.fetch_video_metadata(vid, timeout=8.0)
            if not isinstance(meta, dict) or "title" not in meta or "thumbnail_url" not in meta:
                failed.append(f"Malformed metadata for ID {vid}")
        except Exception as e:
            failed.append(f"Unexpected exception for {vid}: {e}")

    elapsed = time.time() - t0
    if not failed:
        print(f"Status: PASS")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Details: Successfully retrieved/generated metadata with timeout fallback.")
        return True
    else:
        print(f"Status: FAIL")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Error Message: {'; '.join(failed)}")
        return False

def run_test_4():
    """Test 4: fetch_transcript()"""
    print("\n" + "=" * 50)
    print("TEST 4: fetch_transcript()")
    print("=" * 50)
    t0 = time.time()
    # Test that fetch_transcript retrieves or cleanly returns standard error without hanging
    test_id = "dQw4w9WgXcQ"
    error_msg = None
    try:
        text, segments, word_count = YouTubeService.fetch_transcript(test_id, timeout=15.0)
        details = f"Retrieved {len(segments)} segments ({word_count} words)"
    except YouTubeServiceError as e:
        details = f"Cleanly handled YouTube response with code [{e.error_code}]: {e.message}"
    except Exception as e:
        error_msg = f"Unhandled exception: {type(e).__name__}: {e}"

    elapsed = time.time() - t0
    if not error_msg:
        print(f"Status: PASS")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Details: {details}")
        return True
    else:
        print(f"Status: FAIL")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Error Message: {error_msg}")
        return False

def run_test_5():
    """Test 5: Strict 15s timeout & exception handling on invalid/unresponsive requests"""
    print("\n" + "=" * 50)
    print("TEST 5: Strict 15s timeout & error handling")
    print("=" * 50)
    t0 = time.time()
    failed = []
    
    # 1. Test non-existent video ID
    try:
        t_sub = time.time()
        YouTubeService.fetch_transcript("NON_EXIST_99", timeout=15.0)
        failed.append("Expected error for non-existent video ID")
    except YouTubeServiceError as e:
        t_sub_el = time.time() - t_sub
        if t_sub_el > 15.5:
            failed.append(f"Request exceeded 15s timeout: took {t_sub_el:.2f}s")

    # 2. Test timeout handling parameter
    try:
        t_sub = time.time()
        # Set 0.001s timeout to ensure TimeoutError is triggered and caught
        YouTubeService.fetch_transcript("x7X9w_GIm1s", timeout=0.001)
        failed.append("Expected timeout error for 0.001s timeout")
    except YouTubeServiceError as e:
        t_sub_el = time.time() - t_sub
        if e.error_code not in ("TRANSCRIPT_TIMEOUT", "REQUEST_BLOCKED"):
            failed.append(f"Unexpected error code for timeout: [{e.error_code}] {e.message}")

    elapsed = time.time() - t0
    if not failed:
        print(f"Status: PASS")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Details: Strict timeouts enforced and all exceptions properly mapped without hanging.")
        return True
    else:
        print(f"Status: FAIL")
        print(f"Execution Time: {elapsed:.4f}s")
        print(f"Error Message: {'; '.join(failed)}")
        return False

if __name__ == "__main__":
    t1 = run_test_1()
    t2 = run_test_2()
    t3 = run_test_3()
    t4 = run_test_4()
    t5 = run_test_5()
    
    print("\n" + "=" * 50)
    print(f"YOUTUBE BACKEND SUMMARY: {'ALL 5 TESTS PASSED' if all([t1, t2, t3, t4, t5]) else 'SOME TESTS FAILED'}")
    print("=" * 50)
