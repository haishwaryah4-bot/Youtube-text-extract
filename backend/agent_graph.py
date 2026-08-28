import os
import re
import sys
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, TypedDict

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.youtube_service import YouTubeService, YouTubeServiceError
from backend.ai_processor import AIProcessor, AIProcessorError
from backend.pdf_generator import PDFReportGenerator
from backend.models import TranscriptResult

# ---------------------------------------------------------
# State Definition
# ---------------------------------------------------------
class VideoGraphState(TypedDict, total=False):
    youtube_url: str
    video_id: str
    title: str
    author: str
    thumbnail_url: str
    transcript: Optional[str]
    transcript_status: str  # "success" | "rate_limited" | "captions_unavailable" | "video_unavailable" | "error"
    provider: str
    chunks: List[Dict[str, Any]]
    summaries: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    action_checklist: List[str]
    overview: str
    main_topics: List[Dict[str, str]]
    key_points: Dict[str, List[str]]
    final_summary: str
    pdf_path: str
    error: Optional[str]
    api_key: Optional[str]


# ---------------------------------------------------------
# Node Implementations
# ---------------------------------------------------------

def validate_input(state: VideoGraphState) -> VideoGraphState:
    """Node 1: Validate YouTube URL and fetch video metadata."""
    if state.get("error"):
        return state

    url = state.get("youtube_url", "").strip()
    video_id = state.get("video_id", "").strip()

    try:
        if not video_id:
            if not url:
                state["error"] = "YouTube URL is required."
                state["transcript_status"] = "error"
                state["provider"] = "none"
                return state
            video_id = YouTubeService.extract_video_id(url)
            state["video_id"] = video_id

        # Fetch metadata if title or author is missing
        if not state.get("title") or not state.get("author"):
            meta = YouTubeService.fetch_video_metadata(video_id)
            state["title"] = meta.get("title", f"YouTube Video ({video_id})")
            state["author"] = meta.get("author", "YouTube Creator")
            state["thumbnail_url"] = meta.get("thumbnail_url", f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg")

    except YouTubeServiceError as e:
        state["error"] = f"URL Validation Error: {e.message}"
        state["transcript_status"] = "error"
        state["provider"] = "none"
    except Exception as e:
        state["error"] = f"Input validation failed: {str(e)}"
        state["transcript_status"] = "error"
        state["provider"] = "none"

    return state


def prepare_transcript(state: VideoGraphState) -> VideoGraphState:
    """Node 2: Retrieve, classify, clean, and chunk transcript via Provider layer."""
    if state.get("error") and not state.get("video_id"):
        return state

    video_id = state.get("video_id", "")
    existing_transcript = state.get("transcript")

    if existing_transcript and existing_transcript.strip():
        # Pre-supplied transcript from client or verified test source
        transcript_text = existing_transcript.strip()
        transcript_status = "success"
        provider_name = "client_supplied"
        err_msg = None
    else:
        # Fetch from YouTube service provider architecture
        t_res: TranscriptResult = YouTubeService.fetch_transcript_result(video_id)
        transcript_status = t_res.status
        transcript_text = t_res.transcript
        provider_name = t_res.provider
        err_msg = t_res.error

    state["transcript_status"] = transcript_status
    state["provider"] = provider_name

    # If no legitimate transcript is available, strictly set transcript to None
    if transcript_status != "success" or not transcript_text:
        state["transcript"] = None
        state["chunks"] = []
        state["error"] = err_msg or f"Transcript unavailable ({transcript_status})."
        return state

    # Legitimate transcript successfully retrieved
    state["transcript"] = transcript_text
    state["error"] = None

    # Clean noise/audio markers
    lines = transcript_text.splitlines()
    cleaned_lines = []
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        trimmed = re.sub(r'\[(?:Music|Applause|Laughter|Cheering|Audio|Silence)\]', '', trimmed, flags=re.IGNORECASE)
        trimmed = re.sub(r'\((?:Music|Applause|Laughter|Cheering|Audio|Silence)\)', '', trimmed, flags=re.IGNORECASE)
        trimmed = re.sub(r'\s+', ' ', trimmed).strip()
        if trimmed and not re.match(r'^\[\d+:\d+\]$', trimmed):
            cleaned_lines.append(trimmed)

    # Chunk transcript for LLM
    max_words = 350
    overlap_words = 40
    chunks: List[Dict[str, Any]] = []
    current_chunk_lines: List[str] = []
    current_word_count = 0
    chunk_idx = 1

    for line in cleaned_lines:
        line_words = len(line.split())
        current_chunk_lines.append(line)
        current_word_count += line_words

        if current_word_count >= max_words:
            chunks.append({
                "chunk_id": chunk_idx,
                "text": "\n".join(current_chunk_lines),
                "word_count": current_word_count
            })
            chunk_idx += 1
            if overlap_words > 0 and len(current_chunk_lines) > 2:
                current_chunk_lines = current_chunk_lines[-2:]
                current_word_count = sum(len(l.split()) for l in current_chunk_lines)
            else:
                current_chunk_lines = []
                current_word_count = 0

    if current_chunk_lines:
        chunks.append({
            "chunk_id": chunk_idx,
            "text": "\n".join(current_chunk_lines),
            "word_count": sum(len(l.split()) for l in current_chunk_lines)
        })

    state["chunks"] = chunks
    return state


def summarize_content(state: VideoGraphState) -> VideoGraphState:
    """Node 3: Summarize transcript chunks using AIProcessor."""
    chunks = state.get("chunks", [])
    title = state.get("title", "YouTube Video")
    author = state.get("author", "YouTube Creator")
    api_key = state.get("api_key")

    try:
        processor = AIProcessor(api_key=api_key)
        summaries: List[Dict[str, Any]] = []

        for chunk in chunks:
            c_text = chunk.get("text", "")
            c_id = chunk.get("chunk_id", 1)
            
            res = processor.process_transcript(
                title=f"{title} (Part {c_id})" if len(chunks) > 1 else title,
                author=author,
                transcript_text=c_text
            )

            summaries.append({
                "chunk_id": c_id,
                "overview": res.get("overview", ""),
                "main_topics": res.get("main_topics", []),
                "key_points": res.get("key_points", {"facts": [], "explanations": [], "recommendations": []}),
                "raw_actions": res.get("actions", []),
                "final_summary": res.get("final_summary", "")
            })

        state["summaries"] = summaries

    except Exception as e:
        state["error"] = f"Content summarization error: {str(e)}"

    return state


def extract_actions(state: VideoGraphState) -> VideoGraphState:
    """Node 4: Grounded action extraction with demonstrated vs recommended categorization."""
    summaries = state.get("summaries", [])
    all_actions: List[Dict[str, Any]] = []

    try:
        for s in summaries:
            raw_acts = s.get("raw_actions", [])
            for act in raw_acts:
                act_name = act.get("name", "Action Item")
                act_type = str(act.get("action_type", "recommended")).lower()
                if act_type not in ["demonstrated", "recommended", "instructional"]:
                    act_type = "recommended"

                steps = act.get("steps", [])
                if isinstance(steps, str):
                    steps = [steps]
                elif not isinstance(steps, list):
                    steps = []

                all_actions.append({
                    "name": act_name,
                    "action_type": act_type,
                    "description": act.get("description", ""),
                    "steps": steps,
                    "why": act.get("why", "To execute the demonstrated or recommended procedure."),
                    "tools_materials": act.get("tools_materials", []) if isinstance(act.get("tools_materials"), list) else [],
                    "precautions": act.get("precautions", []) if isinstance(act.get("precautions"), list) else [],
                    "timing_frequency": act.get("timing_frequency")
                })

        state["actions"] = all_actions

    except Exception as e:
        state["error"] = f"Action extraction failed: {str(e)}"

    return state


def deduplicate_actions(state: VideoGraphState) -> VideoGraphState:
    """Node 5: Deduplicate actions across chunks and merge steps."""
    actions = state.get("actions", [])
    if not actions:
        state["actions"] = []
        return state

    try:
        seen_names = set()
        deduped: List[Dict[str, Any]] = []

        for act in actions:
            norm_name = re.sub(r'[^a-zA-Z0-9]', '', act.get("name", "").lower())[:30]
            if not norm_name:
                continue

            if norm_name not in seen_names:
                seen_names.add(norm_name)
                deduped.append(act)
            else:
                for existing in deduped:
                    ex_norm = re.sub(r'[^a-zA-Z0-9]', '', existing.get("name", "").lower())[:30]
                    if ex_norm == norm_name:
                        for s in act.get("steps", []):
                            if s not in existing.get("steps", []):
                                existing.setdefault("steps", []).append(s)
                        break

        state["actions"] = deduped[:8]

    except Exception as e:
        state["error"] = f"Action deduplication failed: {str(e)}"

    return state


def final_review(state: VideoGraphState) -> VideoGraphState:
    """Node 6: Synthesize overview, main topics, key points, checklist, and final summary."""
    summaries = state.get("summaries", [])
    title = state.get("title", "YouTube Video")
    author = state.get("author", "YouTube Creator")
    actions = state.get("actions", [])

    try:
        all_topics: List[Dict[str, str]] = []
        seen_topics = set()
        for s in summaries:
            for top in s.get("main_topics", []):
                t_name = top.get("topic", "").strip()
                if t_name and t_name.lower() not in seen_topics:
                    seen_topics.add(t_name.lower())
                    all_topics.append(top)

        all_facts, all_explanations, all_recommendations = [], [], []
        for s in summaries:
            kp = s.get("key_points", {})
            for f in kp.get("facts", []):
                if f not in all_facts:
                    all_facts.append(f)
            for e in kp.get("explanations", []):
                if e not in all_explanations:
                    all_explanations.append(e)
            for r in kp.get("recommendations", []):
                if r not in all_recommendations:
                    all_recommendations.append(r)

        first_overview = summaries[0].get("overview", "") if summaries else f"Video analysis for '{title}' by {author}."
        final_sum = summaries[-1].get("final_summary", "") if summaries else first_overview
        checklist = [act.get("name", "Action item") for act in actions]

        state["overview"] = first_overview
        state["main_topics"] = all_topics[:6]
        state["key_points"] = {
            "facts": all_facts[:6],
            "explanations": all_explanations[:6],
            "recommendations": all_recommendations[:6]
        }
        state["action_checklist"] = checklist
        state["final_summary"] = final_sum

    except Exception as e:
        state["error"] = f"Final review synthesis failed: {str(e)}"

    return state


def generate_pdf(state: VideoGraphState) -> VideoGraphState:
    """Node 7: Generate PDF report."""
    video_id = state.get("video_id", "unknown_video")
    pdf_out_dir = str(BASE_DIR / "generated_pdfs")
    os.makedirs(pdf_out_dir, exist_ok=True)
    pdf_filepath = state.get("pdf_path") or os.path.join(pdf_out_dir, f"report_{video_id}.pdf")

    pdf_data = {
        "video_id": video_id,
        "url": state.get("youtube_url", f"https://www.youtube.com/watch?v={video_id}"),
        "title": state.get("title", f"Video ({video_id})"),
        "author": state.get("author", "YouTube Creator"),
        "thumbnail_url": state.get("thumbnail_url", f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"),
        "overview": state.get("overview", ""),
        "main_topics": state.get("main_topics", []),
        "key_points": state.get("key_points", {}),
        "actions": state.get("actions", []),
        "action_checklist": state.get("action_checklist", []),
        "final_summary": state.get("final_summary", "")
    }

    try:
        PDFReportGenerator.generate_pdf(pdf_data, pdf_filepath)
        state["pdf_path"] = pdf_filepath
    except Exception as e:
        state["pdf_path"] = ""

    return state


# ---------------------------------------------------------
# LangGraph StateGraph Construction & Conditional Routing
# ---------------------------------------------------------
from langgraph.graph import StateGraph, START, END

def check_transcript_success(state: VideoGraphState) -> str:
    """Conditional router: continue only if legitimate transcript was retrieved."""
    if state.get("transcript_status") == "success" and state.get("transcript"):
        return "continue"
    return "stop"


def build_youtube_graph():
    graph_builder = StateGraph(VideoGraphState)

    graph_builder.add_node("validate_input", validate_input)
    graph_builder.add_node("prepare_transcript", prepare_transcript)
    graph_builder.add_node("summarize_content", summarize_content)
    graph_builder.add_node("extract_actions", extract_actions)
    graph_builder.add_node("deduplicate_actions", deduplicate_actions)
    graph_builder.add_node("final_review", final_review)
    graph_builder.add_node("generate_pdf", generate_pdf)

    # Workflow Connections
    graph_builder.add_edge(START, "validate_input")
    graph_builder.add_edge("validate_input", "prepare_transcript")

    # Conditional Branch: Success -> continue, No -> Stop with clear error/status
    graph_builder.add_conditional_edges(
        "prepare_transcript",
        check_transcript_success,
        {
            "continue": "summarize_content",
            "stop": END
        }
    )

    graph_builder.add_edge("summarize_content", "extract_actions")
    graph_builder.add_edge("extract_actions", "deduplicate_actions")
    graph_builder.add_edge("deduplicate_actions", "final_review")
    graph_builder.add_edge("final_review", "generate_pdf")
    graph_builder.add_edge("generate_pdf", END)

    return graph_builder.compile()

compiled_graph = build_youtube_graph()


# ---------------------------------------------------------
# Public Execution Function & Compatibility Wrapper
# ---------------------------------------------------------

def run_youtube_analysis(
    youtube_url: str,
    api_key: Optional[str] = None,
    transcript: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute the compiled LangGraph workflow and return structured result.
    """
    initial_state: VideoGraphState = {
        "youtube_url": youtube_url,
        "video_id": "",
        "title": title or "",
        "author": author or "",
        "thumbnail_url": "",
        "transcript": transcript,
        "transcript_status": "success" if transcript else "captions_unavailable",
        "provider": "client_supplied" if transcript else "none",
        "chunks": [],
        "summaries": [],
        "actions": [],
        "action_checklist": [],
        "overview": "",
        "main_topics": [],
        "key_points": {"facts": [], "explanations": [], "recommendations": []},
        "final_summary": "",
        "pdf_path": "",
        "error": None,
        "api_key": api_key
    }
    return compiled_graph.invoke(initial_state)


class LangGraphAgent:
    """Wrapper maintaining interface compatibility for server routes."""
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def run(self, video_id: str, title: str, author: str, transcript_text: str) -> Dict[str, Any]:
        res = run_youtube_analysis(
            youtube_url=f"https://www.youtube.com/watch?v={video_id}",
            api_key=self.api_key,
            transcript=transcript_text,
            title=title,
            author=author
        )
        return res
