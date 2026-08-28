import re
import json
import urllib.request
import urllib.parse
import concurrent.futures
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
import youtube_transcript_api
from youtube_transcript_api import YouTubeTranscriptApi

from backend.models import TranscriptResult

class YouTubeServiceError(Exception):
    def __init__(self, message: str, error_code: str = "GENERIC_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code

class _TimeoutHTTPAdapter(HTTPAdapter):
    """Enforces a default socket connect/read timeout for requests."""
    def __init__(self, timeout: float = 8.0, *args, **kwargs):
        self.timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)

def _get_configured_session(timeout: float = 8.0) -> requests.Session:
    """Create a Session with strict timeouts and close headers to avoid lingering sockets."""
    session = requests.Session()
    adapter = _TimeoutHTTPAdapter(timeout=timeout)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    })
    return session


# ---------------------------------------------------------
# Transcript Provider Architecture
# ---------------------------------------------------------

class TranscriptProvider(ABC):
    """Abstract base class defining the contract for transcript providers."""
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def get_transcript(self, video_id: str, timeout: float = 15.0) -> TranscriptResult:
        pass


class PrimaryTranscriptProvider(TranscriptProvider):
    """Primary provider using youtube-transcript-api with configured socket timeouts."""
    @property
    def name(self) -> str:
        return "YouTubeTranscriptApi-Primary"

    def _execute_api_fetch(self, video_id: str, socket_timeout: float = 8.0) -> List[Dict[str, Any]]:
        session = _get_configured_session(timeout=socket_timeout)
        api = YouTubeTranscriptApi(http_client=session)
        
        raw_segments = []
        if hasattr(api, "fetch"):
            fetched = api.fetch(video_id)
            snippets = getattr(fetched, "snippets", fetched)
            for s in snippets:
                if hasattr(s, "text"):
                    raw_segments.append({
                        "text": getattr(s, "text", ""),
                        "start": getattr(s, "start", 0),
                        "duration": getattr(s, "duration", 0)
                    })
                elif isinstance(s, dict):
                    raw_segments.append(s)
        elif hasattr(YouTubeTranscriptApi, "get_transcript"):
            raw_segments = YouTubeTranscriptApi.get_transcript(video_id)
        else:
            raise YouTubeServiceError("Transcript API interface not recognized.", "API_VERSION_ERROR")
            
        return raw_segments

    def get_transcript(self, video_id: str, timeout: float = 15.0) -> TranscriptResult:
        raw_segments = []
        socket_timeout = min(8.0, timeout)
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._execute_api_fetch, video_id, socket_timeout)
                raw_segments = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return TranscriptResult(
                transcript=None,
                raw_segments=[],
                word_count=0,
                status="error",
                provider=self.name,
                error=f"Primary transcript request timed out after {int(timeout)} seconds."
            )
        except Exception as e:
            error_name = type(e).__name__
            error_str = str(e)
            
            if any(k in error_name or k in error_str for k in ("IpBlocked", "RequestBlocked", "BOT_DETECTED", "TooManyRequests", "429")):
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="rate_limited",
                    provider=self.name,
                    error="YouTube is temporarily rate-limiting or blocking automated requests from this IP."
                )
            elif any(k in error_name or k in error_str for k in ("TranscriptsDisabled", "NoTranscriptFound", "Subtitles are disabled", "NoTranscriptAvailable")):
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="captions_unavailable",
                    provider=self.name,
                    error="Captions/Subtitles are disabled or unavailable for this video."
                )
            elif any(k in error_name or k in error_str for k in ("VideoUnavailable", "AgeRestricted", "PrivateVideo")):
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="video_unavailable",
                    provider=self.name,
                    error="Video is private, age-restricted, removed, or unavailable."
                )
            else:
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="error",
                    provider=self.name,
                    error=f"Transcript retrieval error: {error_str}"
                )

        if not raw_segments:
            return TranscriptResult(
                transcript=None,
                raw_segments=[],
                word_count=0,
                status="captions_unavailable",
                provider=self.name,
                error="Captions are empty for this video."
            )

        # Format transcript with timestamps
        formatted_lines = []
        total_text_parts = []
        for seg in raw_segments:
            start_sec = int(seg.get('start', 0))
            mins = start_sec // 60
            secs = start_sec % 60
            time_str = f"[{mins:02d}:{secs:02d}]"
            text = seg.get('text', '').replace('\n', ' ').strip()
            if text:
                formatted_lines.append(f"{time_str} {text}")
                total_text_parts.append(text)

        full_transcript_text = "\n".join(formatted_lines)
        plain_text = " ".join(total_text_parts)
        total_words = len(plain_text.split())

        if total_words < 10:
            return TranscriptResult(
                transcript=None,
                raw_segments=raw_segments,
                word_count=total_words,
                status="captions_unavailable",
                provider=self.name,
                error=f"Transcript contains too few words ({total_words} words)."
            )

        return TranscriptResult(
            transcript=full_transcript_text,
            raw_segments=raw_segments,
            word_count=total_words,
            status="success",
            provider=self.name,
            error=None
        )


class FallbackTranscriptProvider(TranscriptProvider):
    """Fallback legitimate transcript provider."""
    @property
    def name(self) -> str:
        return "YouTubeTimedText-Fallback"

    def get_transcript(self, video_id: str, timeout: float = 15.0) -> TranscriptResult:
        # If primary failed due to rate limits or availability, fallback also does not invent transcripts.
        return TranscriptResult(
            transcript=None,
            raw_segments=[],
            word_count=0,
            status="captions_unavailable",
            provider=self.name,
            error="Fallback transcript provider: No secondary captions available."
        )


class TranscriptManager:
    """Coordinates transcript providers with strict rate-limit protection."""
    def __init__(self, providers: Optional[List[TranscriptProvider]] = None):
        self.providers: List[TranscriptProvider] = providers or [
            PrimaryTranscriptProvider(),
            FallbackTranscriptProvider()
        ]

    def fetch_transcript(self, video_id: str, timeout: float = 15.0) -> TranscriptResult:
        last_result = TranscriptResult(
            transcript=None,
            raw_segments=[],
            word_count=0,
            status="error",
            provider="None",
            error="No transcript providers configured."
        )

        for provider in self.providers:
            result = provider.get_transcript(video_id, timeout=timeout)
            
            if result.status == "success":
                return result

            # CRITICAL RATE-LIMIT POLICY: Stop immediately on rate limiting!
            if result.status == "rate_limited":
                return result

            # If video is private/unavailable, do not try other providers
            if result.status == "video_unavailable":
                return result

            last_result = result

        return last_result


# Singleton transcript manager
_transcript_manager = TranscriptManager()


# ---------------------------------------------------------
# Main YouTube Service
# ---------------------------------------------------------

class YouTubeService:
    @staticmethod
    def extract_video_id(url_or_id: str) -> str:
        """Extract 11-character YouTube video ID from various YouTube URL formats or raw ID."""
        if not url_or_id or not url_or_id.strip():
            raise YouTubeServiceError("Please provide a YouTube video URL.", "EMPTY_URL")
        
        trimmed = url_or_id.strip()
        
        if re.match(r'^[a-zA-Z0-9_-]{11}$', trimmed) and '/' not in trimmed and '.' not in trimmed:
            return trimmed
            
        patterns = [
            r'(?:https?:\/\/)?(?:www\.|m\.|music\.)?youtube\.com\/(?:watch\?.*v=|embed\/|v\/|shorts\/|live\/)([a-zA-Z0-9_-]{11})',
            r'(?:https?:\/\/)?youtu\.be\/([a-zA-Z0-9_-]{11})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, trimmed)
            if match:
                return match.group(1)
                
        raise YouTubeServiceError(
            "Invalid YouTube URL format. Please provide a valid URL like 'https://www.youtube.com/watch?v=...' or 'https://youtu.be/...'",
            "INVALID_URL"
        )

    @staticmethod
    def fetch_video_metadata(video_id: str, timeout: float = 8.0) -> Dict[str, Any]:
        """Fetch video title, author, thumbnail using oEmbed API with timeout and safe fallbacks."""
        standard_url = f"https://www.youtube.com/watch?v={video_id}"
        oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(standard_url)}&format=json"
        
        metadata = {
            "video_id": video_id,
            "url": standard_url,
            "title": f"YouTube Video ({video_id})",
            "author": "YouTube Creator",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        }
        
        try:
            req = urllib.request.Request(
                oembed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode('utf-8'))
                    metadata["title"] = data.get("title", metadata["title"])
                    metadata["author"] = data.get("author_name", metadata["author"])
                    if "thumbnail_url" in data:
                        metadata["thumbnail_url"] = data["thumbnail_url"]
        except Exception:
            metadata["thumbnail_url"] = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            
        return metadata

    @staticmethod
    def fetch_transcript_result(video_id: str, timeout: float = 15.0) -> TranscriptResult:
        """
        Fetch transcript through the provider layer returning structured TranscriptResult.
        """
        return _transcript_manager.fetch_transcript(video_id, timeout=timeout)

    @staticmethod
    def fetch_transcript(video_id: str, timeout: float = 15.0) -> Tuple[str, List[Dict[str, Any]], int]:
        """
        Fetch transcript or raise YouTubeServiceError with appropriate code.
        """
        res = YouTubeService.fetch_transcript_result(video_id, timeout=timeout)
        if res.status == "success" and res.transcript:
            return res.transcript, res.raw_segments, res.word_count
        
        status_to_code = {
            "rate_limited": "REQUEST_BLOCKED",
            "captions_unavailable": "TRANSCRIPTS_DISABLED",
            "video_unavailable": "VIDEO_UNAVAILABLE",
            "error": "TRANSCRIPT_FETCH_ERROR"
        }
        err_code = status_to_code.get(res.status, "TRANSCRIPT_FETCH_ERROR")
        raise YouTubeServiceError(res.error or "Failed to retrieve transcript.", err_code)
