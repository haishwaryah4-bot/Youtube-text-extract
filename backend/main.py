import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, List
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# Load environment variables
from dotenv import load_dotenv
load_dotenv(override=True)

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.youtube_service import YouTubeService, YouTubeServiceError
from backend.ai_processor import AIProcessor
from backend.agent_graph import LangGraphAgent, run_youtube_analysis
from backend.pdf_generator import PDFReportGenerator

import tempfile
if os.environ.get("VERCEL") == "1" or os.environ.get("AWS_EXECUTION_ENV"):
    PDF_OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "generated_pdfs")
else:
    PDF_OUTPUT_DIR = str(BASE_DIR / "generated_pdfs")
os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)

# In-memory store for fast retrieval & chat grounding
processed_store: Dict[str, Dict[str, Any]] = {}
ai_processor = AIProcessor()

async def health_check(request):
    return JSONResponse({"status": "ok", "service": "YouTube Video Intelligence & Action Extractor"})

async def config_check(request):
    """
    GET /api/config/check
    Safely return whether OpenAI API Key is configured without exposing it.
    """
    key = os.getenv("OPENAI_API_KEY", "").strip()
    is_configured = bool(key and key != "sk-placeholder" and len(key) > 20)
    return JSONResponse({"OpenAI configured": is_configured})

async def get_samples(request):
    """Return pre-tested YouTube sample URLs for instant 1-click testing."""
    samples = [
        {
            "title": "Applying Fertilizer & Plant Nutrition Guide",
            "url": "https://www.youtube.com/watch?v=0e3GPea1Tyg",
            "category": "Agriculture & Practical"
        },
        {
            "title": "Python in 100 Seconds (Fireship)",
            "url": "https://www.youtube.com/watch?v=x7X9w_GIm1s",
            "category": "Coding & Tech"
        },
        {
            "title": "How to Brew Pour Over Coffee (James Hoffmann)",
            "url": "https://www.youtube.com/watch?v=1oB1oDrDkHM",
            "category": "How-To Guide"
        }
    ]
    return JSONResponse(samples)

async def validate_url(request):
    """Validate YouTube URL and return metadata."""
    try:
        body = await request.json()
        url = (body.get("youtube_url") or body.get("url", "")).strip()
        video_id = YouTubeService.extract_video_id(url)
        metadata = YouTubeService.fetch_video_metadata(video_id)
        return JSONResponse({"valid": True, "metadata": metadata})
    except YouTubeServiceError as e:
        return JSONResponse({"valid": False, "error": e.message, "code": e.error_code}, status_code=400)
    except Exception as e:
        return JSONResponse({"valid": False, "error": str(e), "code": "VALIDATION_FAILED"}, status_code=400)

async def analyze_youtube(request):
    """
    POST /api/youtube/analyze
    Full End-to-End Pipeline powered by LangGraph:
    YouTube URL → validate URL → extract ID → metadata → transcript provider → LangGraph analysis → summary → actions → review → PDF
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({
            "success": False,
            "video_id": "",
            "title": "",
            "author": "",
            "transcript_status": "error",
            "transcript_provider": "none",
            "summary": "",
            "key_points": [],
            "demonstrated_actions": [],
            "recommended_actions": [],
            "tools_materials": [],
            "precautions": [],
            "pdf_path": None,
            "error": "Invalid JSON body"
        }, status_code=400)

    youtube_url = (body.get("youtube_url") or body.get("url", "")).strip()
    custom_api_key = (body.get("api_key") or "").strip()
    custom_transcript = body.get("transcript")

    print(f"\n[1] YouTube URL received: {youtube_url}")

    if not youtube_url:
        return JSONResponse({
            "success": False,
            "video_id": "",
            "title": "",
            "author": "",
            "transcript_status": "error",
            "transcript_provider": "none",
            "summary": "",
            "key_points": [],
            "demonstrated_actions": [],
            "recommended_actions": [],
            "tools_materials": [],
            "precautions": [],
            "pdf_path": None,
            "error": "youtube_url is required."
        }, status_code=400)

    # Execute LangGraph Workflow
    try:
        res = run_youtube_analysis(
            youtube_url=youtube_url,
            api_key=custom_api_key if custom_api_key else None,
            transcript=custom_transcript
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": f"An unexpected backend error occurred: {str(e)}",
            "error_type": "INTERNAL_SERVER_ERROR"
        }, status_code=200) # Must be 200 so frontend parses it cleanly, or handled in frontend

    print(f"[9] Response returned to frontend. Status: {res.get('transcript_status', 'error')}, Error: {res.get('error', 'None')}")

    video_id = res.get("video_id", "")
    title = res.get("title", "")
    author = res.get("author", "")
    transcript_status = res.get("transcript_status", "error")
    transcript_provider = res.get("provider", "none")
    transcript_text = res.get("transcript")
    error = res.get("error")

    is_success = (transcript_status == "success" and bool(transcript_text))

    if is_success:
        actions = res.get("actions", [])
        demonstrated_actions = [act for act in actions if act.get("action_type") == "demonstrated"]
        recommended_actions = [act for act in actions if act.get("action_type") != "demonstrated"]

        # Aggregate key points
        kp_dict = res.get("key_points", {})
        key_points: List[str] = []
        for category in ("facts", "explanations", "recommendations"):
            for item in kp_dict.get(category, []):
                if item and item not in key_points:
                    key_points.append(item)

        # Aggregate tools/materials and precautions
        tools_materials: List[str] = []
        precautions: List[str] = []
        for act in actions:
            for t in act.get("tools_materials", []):
                if t and t not in tools_materials:
                    tools_materials.append(t)
            for p in act.get("precautions", []):
                if p and p not in precautions:
                    precautions.append(p)

        pdf_path = res.get("pdf_path") or os.path.join(PDF_OUTPUT_DIR, f"report_{video_id}.pdf")
        summary = res.get("final_summary") or res.get("overview", "")

        processed_store[video_id] = {
            "metadata": {
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": title,
                "author": author,
                "thumbnail_url": res.get("thumbnail_url", ""),
                "overview": res.get("overview", ""),
                "main_topics": res.get("main_topics", []),
                "key_points": kp_dict,
                "actions": actions,
                "action_checklist": res.get("action_checklist", []),
                "final_summary": summary
            },
            "transcript": transcript_text,
            "pdf_path": pdf_path
        }

        response_payload = {
            "success": True,
            "video_id": video_id,
            "title": title,
            "author": author,
            "transcript_status": transcript_status,
            "transcript_provider": transcript_provider,
            "raw_transcript": transcript_text,
            "summary": summary,
            "overview": res.get("overview", summary),
            "main_topics": res.get("main_topics", []),
            "key_points": kp_dict,
            "final_summary": res.get("final_summary", ""),
            "action_checklist": res.get("action_checklist", []),
            "demonstrated_actions": demonstrated_actions,
            "recommended_actions": recommended_actions,
            "tools_materials": tools_materials,
            "precautions": precautions,
            "pdf_path": pdf_path,
            "error": error
        }
        return JSONResponse(response_payload)

    else:
        # Failure / Rate limited / Unavailable branch
        response_payload = {
            "success": False,
            "video_id": video_id,
            "title": title,
            "author": author,
            "transcript_status": transcript_status,
            "transcript_provider": transcript_provider,
            "summary": "",
            "key_points": [],
            "demonstrated_actions": [],
            "recommended_actions": [],
            "tools_materials": [],
            "precautions": [],
            "pdf_path": None,
            "error_type": res.get("error_type", "TRANSCRIPTION_ERROR"),
            "error": error or f"Transcript retrieval failed ({transcript_status})."
        }
        return JSONResponse(response_payload, status_code=200)

async def get_pdf(request):
    """Serve or download the generated PDF report."""
    video_id = request.path_params.get("video_id", "")
    download = request.query_params.get("download", "false").lower() == "true"

    pdf_filename = f"report_{video_id}.pdf"
    pdf_filepath = os.path.join(PDF_OUTPUT_DIR, pdf_filename)

    if not os.path.exists(pdf_filepath):
        if video_id in processed_store:
            PDFReportGenerator.generate_pdf(processed_store[video_id]["metadata"], pdf_filepath)
        else:
            return JSONResponse({"error": "PDF not found for this video ID."}, status_code=404)

    disposition = "attachment" if download else "inline"
    return FileResponse(
        pdf_filepath,
        media_type="application/pdf",
        headers={"Content-Disposition": f"{disposition}; filename=\"{pdf_filename}\""}
    )

async def chat_with_video(request):
    """Interactive AI chat grounded in the processed video transcript."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    video_id = body.get("video_id", "")
    question = body.get("message", "")
    history = body.get("history", [])
    custom_api_key = body.get("api_key", "").strip()

    if video_id not in processed_store:
        return JSONResponse({"error": "Video context not found. Please process the video first."}, status_code=400)

    stored = processed_store[video_id]
    processor = AIProcessor(api_key=custom_api_key) if custom_api_key else ai_processor
    
    reply = processor.chat_with_video(
        transcript=stored["transcript"],
        summary_data=stored["metadata"],
        question=question,
        history=history
    )
    return JSONResponse({"reply": reply})

# Route Definitions
async def debug_transcript(request):
    """
    GET /api/debug/transcript?v=VIDEO_ID
    Safely test each transcript provider and return diagnostic info.
    Shows which providers succeeded/failed without exposing credentials.
    """
    video_id = request.query_params.get("v", "").strip()
    if not video_id:
        return JSONResponse({"error": "Missing ?v=VIDEO_ID parameter"}, status_code=400)

    from backend.youtube_service import (
        PrimaryTranscriptProvider, FallbackTranscriptProvider
    )
    import os

    results = []
    providers = [PrimaryTranscriptProvider(), FallbackTranscriptProvider()]
    for provider in providers:
        try:
            r = provider.get_transcript(video_id, timeout=15.0)
            results.append({
                "provider": provider.name,
                "status": r.status,
                "word_count": r.word_count,
                "error": r.error,
                "success": r.status == "success"
            })
        except Exception as e:
            results.append({
                "provider": provider.name,
                "status": "exception",
                "error": str(e),
                "success": False
            })

    api_key = os.getenv("OPENAI_API_KEY", "")
    openai_configured = bool(api_key and len(api_key) > 20 and api_key != "sk-placeholder")

    return JSONResponse({
        "video_id": video_id,
        "openai_configured": openai_configured,
        "openai_key_prefix": api_key[:6] + "..." if openai_configured else "NOT_SET",
        "providers": results
    })

routes = [
    Route("/api/health", health_check, methods=["GET"]),
    Route("/api/config/check", config_check, methods=["GET"]),
    Route("/api/samples", get_samples, methods=["GET"]),
    Route("/api/validate-url", validate_url, methods=["POST"]),
    Route("/api/youtube/analyze", analyze_youtube, methods=["POST"]),
    Route("/api/process-video", analyze_youtube, methods=["POST"]),  # Legacy alias
    Route("/api/pdf/{video_id}", get_pdf, methods=["GET"]),
    Route("/api/chat", chat_with_video, methods=["POST"]),
    Route("/api/debug/transcript", debug_transcript, methods=["GET"]),
]

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

static_dir = str(BASE_DIR / "static")
os.makedirs(static_dir, exist_ok=True)

app = Starlette(debug=True, routes=routes, middleware=middleware)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
