from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

class TranscriptResult(BaseModel):
    transcript: Optional[str] = None
    raw_segments: List[Dict[str, Any]] = Field(default_factory=list)
    word_count: int = 0
    status: Literal["success", "rate_limited", "captions_unavailable", "video_unavailable", "error", "unavailable"] = "error"
    provider: str = "none"
    error: Optional[str] = None


class VideoValidationRequest(BaseModel):
    url: str

class VideoMetadata(BaseModel):
    video_id: str
    title: str
    author: Optional[str] = "Unknown Creator"
    duration_str: Optional[str] = None
    thumbnail_url: Optional[str] = None
    url: str

class ActionItem(BaseModel):
    name: str = Field(description="Clear title of the action")
    action_type: Literal["demonstrated", "recommended", "instructional"] = Field(
        default="recommended",
        description="Whether this action was actually demonstrated in video, recommended/instructed by speaker, or general instructional"
    )
    description: str = Field(description="What needs to be done")
    steps: List[str] = Field(default_factory=list, description="Step-by-step numbered breakdown of instructions")
    why: str = Field(description="Why this action is performed (purpose / benefit)")
    tools_materials: List[str] = Field(default_factory=list, description="Required tools or materials if mentioned in transcript")
    precautions: List[str] = Field(default_factory=list, description="Important precautions or safety measures if mentioned")
    timing_frequency: Optional[str] = Field(default=None, description="Timing, schedule, or frequency if mentioned")
    timestamp_hint: Optional[str] = Field(default=None, description="Approximate timestamp if available")

class MainTopic(BaseModel):
    topic: str = Field(description="Important topic or theme discussed")
    explanation: str = Field(description="Key concepts and insights explained about this topic")

class KeyPoints(BaseModel):
    facts: List[str] = Field(default_factory=list, description="Important facts mentioned")
    explanations: List[str] = Field(default_factory=list, description="Important explanations provided")
    recommendations: List[str] = Field(default_factory=list, description="Important recommendations given")

class ProcessedVideoResponse(BaseModel):
    video_id: str
    url: str
    title: str
    author: str
    thumbnail_url: str
    overview: str
    main_topics: List[MainTopic]
    key_points: KeyPoints
    actions: List[ActionItem]
    action_checklist: List[str]
    final_summary: str
    pdf_url: str
    raw_transcript: Optional[str] = None
    total_transcript_words: Optional[int] = 0

class ChatRequest(BaseModel):
    video_id: str
    message: str
    history: Optional[List[dict]] = None

class ChatResponse(BaseModel):
    reply: str
