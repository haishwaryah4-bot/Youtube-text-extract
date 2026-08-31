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

import os
from http.cookiejar import MozillaCookieJar

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
    
    # Load cookies from cookies.txt in project root if available to bypass rate-limiting
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cookies_path = os.path.join(base_dir, "cookies.txt")
    if os.path.exists(cookies_path):
        try:
            cj = MozillaCookieJar(cookies_path)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies.update(cj)
        except Exception:
            pass
            
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
    """Fallback legitimate transcript provider using YouTube timedtext API or watch page scraping."""
    @property
    def name(self) -> str:
        return "YouTubeTimedText-Fallback"

    def get_transcript(self, video_id: str, timeout: float = 15.0) -> TranscriptResult:
        import logging
        logger = logging.getLogger("youtube_service.fallback")
        logger.info(f"Attempting fallback transcript retrieval for video ID: {video_id}")
        
        session = _get_configured_session(timeout=timeout)
        try:
            # Step 1: Try direct timedtext request first (English manually created or automated)
            direct_urls = [
                f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en&fmt=json3",
                f"https://www.youtube.com/api/timedtext?v={video_id}&lang=en&kind=asr&fmt=json3"
            ]
            
            for url in direct_urls:
                try:
                    logger.info(f"Querying timedtext URL directly: {url}")
                    response = session.get(url, timeout=timeout)
                    if response.status_code == 200 and response.text.strip():
                        data = response.json()
                        result = self._parse_json3(data)
                        if result:
                            return result
                    elif response.status_code == 429:
                        logger.warning("YouTube timedtext endpoint returned HTTP 429 Rate Limited.")
                        return TranscriptResult(
                            transcript=None,
                            raw_segments=[],
                            word_count=0,
                            status="rate_limited",
                            provider=self.name,
                            error="YouTube is temporarily rate-limiting or blocking automated requests from this IP."
                        )
                except Exception as ex:
                    logger.debug(f"Direct timedtext query to {url} failed: {ex}")

            # Step 2: Fetch watch page to extract captions tracklist from player response
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"Fetching watch page to extract caption tracks: {watch_url}")
            response = session.get(watch_url, timeout=timeout)
            
            if response.status_code == 429:
                logger.warning("YouTube watch page request returned HTTP 429 Rate Limited.")
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="rate_limited",
                    provider=self.name,
                    error="YouTube is temporarily rate-limiting or blocking automated requests from this IP."
                )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch YouTube watch page (Status code: {response.status_code})")
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="error",
                    provider=self.name,
                    error=f"Failed to fetch YouTube watch page (Status code: {response.status_code})"
                )

            html = response.text
            
            # Find captionTracks from player response
            caption_tracks = []
            match = re.search(r'ytInitialPlayerResponse\s*=\s*({.*?});', html)
            if match:
                try:
                    player_data = json.loads(match.group(1))
                    caption_tracks = player_data.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
                    logger.info(f"Extracted {len(caption_tracks)} caption tracks from player response.")
                except Exception as ex:
                    logger.debug(f"Parsing ytInitialPlayerResponse failed: {ex}")

            # Fallback regex search for captionTracks directly in html
            if not caption_tracks:
                match_tracks = re.search(r'"captionTracks":\s*(\[.*?\])', html)
                if match_tracks:
                    try:
                        caption_tracks = json.loads(match_tracks.group(1))
                        logger.info(f"Extracted {len(caption_tracks)} caption tracks via direct regex.")
                    except Exception as ex:
                        logger.debug(f"Parsing captionTracks regex match failed: {ex}")

            if not caption_tracks:
                logger.info("No caption tracks found for this video in page HTML.")
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="captions_unavailable",
                    provider=self.name,
                    error="Captions/Subtitles are disabled or unavailable for this video (no caption tracks found)."
                )

            # Prioritize manual English, then auto-generated English, then any track
            selected_track_url = None
            for track in caption_tracks:
                lang = track.get("languageCode", "")
                kind = track.get("kind", "")
                if lang.startswith("en") and kind != "asr":
                    selected_track_url = track.get("baseUrl")
                    logger.info(f"Selected manual English track: {selected_track_url}")
                    break
            
            if not selected_track_url:
                for track in caption_tracks:
                    lang = track.get("languageCode", "")
                    if lang.startswith("en"):
                        selected_track_url = track.get("baseUrl")
                        logger.info(f"Selected auto-generated English track: {selected_track_url}")
                        break

            if not selected_track_url and caption_tracks:
                selected_track_url = caption_tracks[0].get("baseUrl")
                logger.info(f"Selected fallback first available track: {selected_track_url}")

            if not selected_track_url:
                logger.warning("No suitable caption track URL found.")
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="captions_unavailable",
                    provider=self.name,
                    error="No suitable English caption track found."
                )

            # Ensure JSON3 format is requested for parsing ease
            if "fmt=json3" not in selected_track_url:
                selected_track_url += "&fmt=json3"

            logger.info(f"Fetching selected track URL: {selected_track_url}")
            track_response = session.get(selected_track_url, timeout=timeout)
            
            if track_response.status_code == 429:
                logger.warning("YouTube timedtext baseUrl query returned HTTP 429 Rate Limited.")
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="rate_limited",
                    provider=self.name,
                    error="YouTube is temporarily rate-limiting or blocking automated requests from this IP."
                )

            if track_response.status_code == 200 and track_response.text.strip():
                data = track_response.json()
                result = self._parse_json3(data)
                if result:
                    return result

            return TranscriptResult(
                transcript=None,
                raw_segments=[],
                word_count=0,
                status="captions_unavailable",
                provider=self.name,
                error="Could not parse or fetch any valid subtitle track content."
            )

        except Exception as e:
            error_name = type(e).__name__
            error_str = str(e)
            logger.error(f"Error during fallback retrieval: {error_name}: {error_str}")
            
            if any(k in error_name or k in error_str for k in ("IpBlocked", "RequestBlocked", "BOT_DETECTED", "TooManyRequests", "429")):
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="rate_limited",
                    provider=self.name,
                    error="YouTube is temporarily rate-limiting or blocking automated requests from this IP."
                )
            
            if any(k in error_name or k in error_str for k in ("Timeout", "time out", "timed out", "TimeoutError")):
                return TranscriptResult(
                    transcript=None,
                    raw_segments=[],
                    word_count=0,
                    status="error",
                    provider=self.name,
                    error=f"Fallback transcript request timed out: {error_str}"
                )
            
            return TranscriptResult(
                transcript=None,
                raw_segments=[],
                word_count=0,
                status="captions_unavailable",
                provider=self.name,
                error=f"Fallback transcript provider error: {error_str}"
            )

    def _parse_json3(self, data: Dict[str, Any]) -> Optional[TranscriptResult]:
        events = data.get("events", [])
        raw_segments = []
        for event in events:
            if "segs" in event:
                text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
                if text:
                    text = text.replace('\n', ' ').strip()
                    start_ms = event.get("tStartMs", 0)
                    duration_ms = event.get("dDurationMs", 0)
                    raw_segments.append({
                        "text": text,
                        "start": start_ms / 1000.0,
                        "duration": duration_ms / 1000.0
                    })
        
        if not raw_segments:
            return None

        # Format transcript with timestamps
        formatted_lines = []
        total_text_parts = []
        for seg in raw_segments:
            start_sec = int(seg.get('start', 0))
            mins = start_sec // 60
            secs = start_sec % 60
            time_str = f"[{mins:02d}:{secs:02d}]"
            text = seg.get('text', '')
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


class WhisperAudioTranscriptProvider(TranscriptProvider):
    """Fallback provider using yt-dlp to download audio and OpenAI Whisper to transcribe."""
    @property
    def name(self) -> str:
        return "OpenAI-Whisper-Audio-Fallback"

    def get_transcript(self, video_id: str, timeout: float = 300.0) -> TranscriptResult:
        import os
        import logging
        import requests
        from pathlib import Path
        try:
            import yt_dlp
        except ImportError:
            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="error", provider=self.name,
                error="yt-dlp is not installed. Cannot use audio transcription fallback."
            )
            
        logger = logging.getLogger("youtube_service.whisper")
        
        # Check API key
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key or api_key == "sk-placeholder" or len(api_key) < 20:
            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="error", provider=self.name,
                error="OpenAI API key is missing or invalid. Cannot use audio transcription fallback."
            )
            
        temp_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent / "temp"
        temp_dir.mkdir(exist_ok=True)
        
        out_tmpl = str(temp_dir / f"{video_id}.%(ext)s")
        
        # 1. Download lowest bitrate audio
        ydl_opts = {
            'format': 'worstaudio[ext=m4a]/worstaudio/bestaudio',
            'outtmpl': out_tmpl,
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            print(f"[5] Fallback transcription started (Whisper) for {video_id}...")
            logger.info(f"Downloading audio for {video_id} using yt-dlp...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
                
            possible_files = list(temp_dir.glob(f"{video_id}.*"))
            if not possible_files:
                raise Exception("Audio file was not created.")
            audio_path = str(possible_files[0])
            
            # Check file size < 25MB
            if os.path.getsize(audio_path) > 25 * 1024 * 1024:
                raise Exception("Audio file exceeds the 25MB limit for transcription API.")
                
            logger.info(f"Sending audio {os.path.basename(audio_path)} to Audio Transcription API...")
            
            api_url = "https://api.openai.com/v1/audio/transcriptions"
            model_name = "whisper-1"
            if api_key.startswith("gsk_"):
                api_url = "https://api.groq.com/openai/v1/audio/transcriptions"
                model_name = "whisper-large-v3"
            
            with open(audio_path, "rb") as f:
                response = requests.post(
                    api_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (os.path.basename(audio_path), f)},
                    data={"model": model_name, "response_format": "verbose_json"},
                    timeout=timeout
                )
                
            if response.status_code != 200:
                try:
                    err_json = response.json()
                    err_msg = err_json.get("error", {}).get("message", response.text)
                except Exception:
                    err_msg = response.text
                raise Exception(f"Transcription API Error ({response.status_code}): {err_msg}")
                
            data = response.json()
            raw_segments = []
            if "segments" in data:
                for seg in data["segments"]:
                    raw_segments.append({
                        "text": seg.get("text", "").strip(),
                        "start": seg.get("start", 0),
                        "duration": seg.get("end", 0) - seg.get("start", 0)
                    })
                    
            if not raw_segments:
                raise Exception("Whisper returned empty transcript.")
                
            full_text = " ".join([s["text"] for s in raw_segments])
            
            print("[6] Speech-to-text succeeded")
            return TranscriptResult(
                transcript=full_text,
                raw_segments=raw_segments,
                word_count=len(full_text.split()),
                status="success",
                provider=self.name,
                error=None
            )
            
        except Exception as e:
            print(f"[6] Speech-to-text failed: {e}")
            logger.error(f"Whisper fallback failed: {e}")
            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="error", provider=self.name,
                error=str(e)
            )
        finally:
            # Clean up all temp files matching video_id
            try:
                for f in temp_dir.glob(f"{video_id}.*"):
                    f.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Failed to clean up temp file: {e}")


class TranscriptManager:
    """Coordinates transcript providers with strict rate-limit protection and fallback."""
    def __init__(self, providers: Optional[List[TranscriptProvider]] = None):
        self.providers: List[TranscriptProvider] = providers or [
            PrimaryTranscriptProvider(),
            FallbackTranscriptProvider(),
            WhisperAudioTranscriptProvider()
        ]

    def fetch_transcript(self, video_id: str, timeout: float = 15.0) -> TranscriptResult:
        import logging
        logger = logging.getLogger("youtube_service.manager")
        
        last_result = TranscriptResult(
            transcript=None,
            raw_segments=[],
            word_count=0,
            status="error",
            provider="None",
            error="No transcript providers configured."
        )

        for provider in self.providers:
            logger.info(f"Attempting transcript retrieval with provider: {provider.name}")
            result = provider.get_transcript(video_id, timeout=timeout)
            
            if result.status == "success":
                logger.info(f"Success with transcript provider: {provider.name}")
                return result

            logger.warning(f"Provider {provider.name} failed. Status: {result.status}. Error: {result.error}")

            # If video is private/unavailable, do not try other providers
            if result.status == "video_unavailable":
                logger.warning(f"Video {video_id} is unavailable. Stopping fallback sequence.")
                return result

            last_result = result

        logger.error(f"All transcript providers failed for video {video_id}.")
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
        import urllib.parse
        
        if not url_or_id or not url_or_id.strip():
            raise YouTubeServiceError("Please provide a YouTube video URL.", "EMPTY_URL")
        
        trimmed = url_or_id.strip()
        
        # Strip ?si= and other tracking queries via urllib if it's a URL
        if "http" in trimmed:
            try:
                parsed = urllib.parse.urlparse(trimmed)
                # If watch?v= format, keep the query to extract 'v'
                if "watch" not in parsed.path:
                    # e.g., youtu.be/ID?si=... -> youtu.be/ID
                    trimmed = urllib.parse.urlunparse(parsed._replace(query=""))
            except Exception:
                pass
                
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
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "description": ""
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

        # Deep-scrape the watch page to get title, author and description
        # (handles music videos and oEmbed-blocked videos)
        try:
            session = _get_configured_session(timeout=timeout)
            resp = session.get(standard_url, timeout=timeout)
            if resp.status_code == 200:
                html = resp.text
                import html as html_lib

                # --- Title from og:title or <title> tag ---
                og_title = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', html)
                if og_title:
                    candidate = html_lib.unescape(og_title.group(1)).strip()
                    # Only override if oEmbed gave us nothing useful
                    if candidate and (metadata["title"].startswith("YouTube Video (") or not metadata["title"]):
                        metadata["title"] = candidate

                # --- Author from ytInitialPlayerResponse.videoDetails ---
                player_match = re.search(r'ytInitialPlayerResponse\s*=\s*({.+?})\s*;\s*(?:var |const |let |\n)', html)
                player_data = {}
                if player_match:
                    try:
                        player_data = json.loads(player_match.group(1))
                    except Exception:
                        pass

                vd = player_data.get("videoDetails", {})
                if vd.get("title") and (metadata["title"].startswith("YouTube Video (") or not metadata["title"]):
                    metadata["title"] = html_lib.unescape(vd["title"]).strip()
                if vd.get("author") and (metadata["author"] == "YouTube Creator" or not metadata["author"]):
                    metadata["author"] = html_lib.unescape(vd["author"]).strip()

                # --- Description ---
                description = vd.get("shortDescription", "").strip()
                if not description:
                    desc_match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
                    if not desc_match:
                        desc_match = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', html)
                    if desc_match:
                        description = html_lib.unescape(desc_match.group(1)).strip()

                metadata["description"] = description
        except Exception:
            pass
            
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
            "error": "TRANSCRIPT_FETCH_ERROR",
            "unavailable": "TRANSCRIPT_FETCH_ERROR"
        }
        err_code = status_to_code.get(res.status, "TRANSCRIPT_FETCH_ERROR")
        if res.status == "error" and res.error and "timed out" in res.error.lower():
            err_code = "TRANSCRIPT_TIMEOUT"
        raise YouTubeServiceError(res.error or "Failed to retrieve transcript.", err_code)
