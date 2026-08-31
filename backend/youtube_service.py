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
    """Primary provider using youtube-transcript-api.
    
    Uses api.list() to discover ALL available transcripts (manual + auto-generated,
    any language), then tries them in priority order:
    1. Manual English
    2. Auto-generated English
    3. Any manual transcript
    4. Any auto-generated transcript
    """
    @property
    def name(self) -> str:
        return "YouTubeTranscriptApi-Primary"

    def _fetch_all_transcripts(self, video_id: str, socket_timeout: float = 10.0) -> TranscriptResult:
        """Try to fetch transcript using list() to discover all available tracks."""
        import logging
        logger = logging.getLogger("youtube_service.primary")
        session = _get_configured_session(timeout=socket_timeout)
        api = YouTubeTranscriptApi(http_client=session)

        # List all available transcripts for this video
        transcript_list = api.list(video_id)

        # Build priority order: manual EN > auto EN > any manual > any auto
        candidates = list(transcript_list)
        priority = []

        # 1. Manual English
        for t in candidates:
            if t.language_code.startswith("en") and not t.is_generated:
                priority.append(t)
        # 2. Auto-generated English
        for t in candidates:
            if t.language_code.startswith("en") and t.is_generated:
                priority.append(t)
        # 3. Any other manual
        for t in candidates:
            if not t.language_code.startswith("en") and not t.is_generated:
                priority.append(t)
        # 4. Any other auto-generated
        for t in candidates:
            if not t.language_code.startswith("en") and t.is_generated:
                priority.append(t)

        if not priority:
            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="captions_unavailable", provider=self.name,
                error="No transcript tracks are available for this video."
            )

        last_error = "No transcript tracks could be fetched."
        for transcript_obj in priority:
            try:
                logger.info(f"Trying transcript: lang={transcript_obj.language_code}, generated={transcript_obj.is_generated}")
                fetched = transcript_obj.fetch()
                snippets = getattr(fetched, "snippets", fetched)

                raw_segments = []
                for s in snippets:
                    if hasattr(s, "text"):
                        raw_segments.append({
                            "text": getattr(s, "text", ""),
                            "start": getattr(s, "start", 0),
                            "duration": getattr(s, "duration", 0)
                        })
                    elif isinstance(s, dict):
                        raw_segments.append(s)

                if not raw_segments:
                    continue

                # Build formatted transcript
                formatted_lines = []
                plain_parts = []
                for seg in raw_segments:
                    text = seg.get("text", "").strip()
                    if not text:
                        continue
                    plain_parts.append(text)
                    start_sec = int(seg.get("start", 0))
                    mins, secs = divmod(start_sec, 60)
                    formatted_lines.append(f"[{mins:02d}:{secs:02d}] {text}")

                full_text = "\n".join(formatted_lines)
                word_count = len(" ".join(plain_parts).split())

                if word_count < 10:
                    last_error = f"Transcript too short ({word_count} words)."
                    continue

                logger.info(f"Successfully fetched transcript ({word_count} words, lang={transcript_obj.language_code})")
                return TranscriptResult(
                    transcript=full_text,
                    raw_segments=raw_segments,
                    word_count=word_count,
                    status="success",
                    provider=self.name,
                    error=None
                )
            except Exception as fetch_err:
                last_error = str(fetch_err)
                logger.warning(f"Failed to fetch transcript (lang={transcript_obj.language_code}): {fetch_err}")
                continue

        return TranscriptResult(
            transcript=None, raw_segments=[], word_count=0,
            status="captions_unavailable", provider=self.name,
            error=f"All available transcript tracks failed: {last_error}"
        )

    def get_transcript(self, video_id: str, timeout: float = 15.0) -> TranscriptResult:
        import logging
        logger = logging.getLogger("youtube_service.primary")
        socket_timeout = min(10.0, timeout)

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._fetch_all_transcripts, video_id, socket_timeout)
                return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="error", provider=self.name,
                error=f"Primary transcript request timed out after {int(timeout)} seconds."
            )
        except Exception as e:
            error_name = type(e).__name__
            error_str = str(e)

            if any(k in error_name or k in error_str for k in ("IpBlocked", "RequestBlocked", "BOT_DETECTED", "TooManyRequests", "429")):
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="rate_limited", provider=self.name,
                    error="YouTube is temporarily rate-limiting or blocking automated requests from this IP."
                )
            elif any(k in error_name or k in error_str for k in ("VideoUnavailable", "AgeRestricted", "PrivateVideo")):
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="video_unavailable", provider=self.name,
                    error="Video is private, age-restricted, removed, or unavailable."
                )
            else:
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="error", provider=self.name,
                    error=f"Transcript retrieval error: {error_str}"
                )


class FallbackTranscriptProvider(TranscriptProvider):
    """
    Fallback provider using YouTube's InnerTube API to get session-signed caption URLs.
    
    YouTube's caption URLs require a session 'ei' token to return content.
    This provider replicates what youtube-transcript-api does internally:
    1. GET /watch?v=... to establish a session
    2. POST /youtubei/v1/player with session context to get signed caption URLs
    3. Fetch the actual transcript from the signed URL
    
    This works even from cloud IPs where the transcript XML endpoint alone fails.
    """
    INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
    INNERTUBE_URL = f"https://www.youtube.com/youtubei/v1/player?key={INNERTUBE_KEY}"

    @property
    def name(self) -> str:
        return "YouTubeInnerTube-Fallback"

    def get_transcript(self, video_id: str, timeout: float = 20.0) -> TranscriptResult:
        import logging
        logger = logging.getLogger("youtube_service.fallback")

        session = _get_configured_session(timeout=timeout)

        try:
            # Step 1: GET /watch page to establish session state (required for ei token)
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"[TRANSCRIPT] GET {watch_url}")
            watch_resp = session.get(watch_url, timeout=timeout)

            if watch_resp.status_code == 429:
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="rate_limited", provider=self.name,
                    error="YouTube returned 429 (rate-limited) on watch page request."
                )
            if watch_resp.status_code != 200:
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="error", provider=self.name,
                    error=f"YouTube watch page returned HTTP {watch_resp.status_code}"
                )

            # Check if YouTube returned a bot/consent page instead of the real page
            html = watch_resp.text
            if "ytInitialPlayerResponse" not in html:
                logger.warning("[TRANSCRIPT] Watch page missing ytInitialPlayerResponse — possible bot detection")
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="rate_limited", provider=self.name,
                    error="YouTube returned a consent/bot-detection page instead of the watch page."
                )

            # Step 2: POST to InnerTube player API using ANDROID client context.
            # IMPORTANT: The WEB client context often returns 0 caption tracks for videos
            # with only auto-generated captions. The ANDROID context reliably returns all
            # caption tracks — this is exactly what youtube-transcript-api uses internally.
            innertube_payload = {
                "context": {
                    "client": {
                        "clientName": "ANDROID",
                        "clientVersion": "20.10.38",
                    }
                },
                "videoId": video_id
            }
            logger.info(f"[TRANSCRIPT] POST InnerTube player API for {video_id}")
            player_resp = session.post(
                self.INNERTUBE_URL,
                json=innertube_payload,
                timeout=timeout
            )

            if player_resp.status_code != 200:
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="error", provider=self.name,
                    error=f"InnerTube player API returned HTTP {player_resp.status_code}"
                )

            player_data = player_resp.json()

            # Check for video unavailability
            playability = player_data.get("playabilityStatus", {})
            if playability.get("status") in ("LOGIN_REQUIRED", "AGE_CHECK_REQUIRED", "ERROR"):
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="video_unavailable", provider=self.name,
                    error=f"Video unavailable: {playability.get('reason', 'Unknown reason')}"
                )

            # Extract caption tracks from the InnerTube response
            caption_tracks = (
                player_data
                .get("captions", {})
                .get("playerCaptionsTracklistRenderer", {})
                .get("captionTracks", [])
            )

            if not caption_tracks:
                logger.info(f"[TRANSCRIPT] InnerTube: No caption tracks for {video_id}")
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="captions_unavailable", provider=self.name,
                    error="This video has no captions (confirmed via InnerTube API)."
                )

            logger.info(f"[TRANSCRIPT] InnerTube: Found {len(caption_tracks)} caption tracks")

            # Priority: manual EN > auto EN > any manual > any auto
            priority = []
            for t in caption_tracks:
                lc = t.get("languageCode", "")
                kind = t.get("kind", "")
                if lc.startswith("en") and kind != "asr":
                    priority.insert(0, t)
                elif lc.startswith("en"):
                    priority.insert(1, t)
                else:
                    priority.append(t)

            # Step 3: Fetch the transcript from the first working signed URL
            for track in priority:
                base_url = track.get("baseUrl", "")
                lang = track.get("languageCode", "?")
                kind = track.get("kind", "manual")
                if not base_url:
                    continue

                # Try JSON3 first, then XML fallback
                for fmt, parser in [("json3", self._parse_json3), ("srv1", self._parse_xml)]:
                    try:
                        fetch_url = base_url + f"&fmt={fmt}"
                        logger.info(f"[TRANSCRIPT] Fetching {lang}/{kind} caption in {fmt}: {fetch_url[:80]}")
                        cap_resp = session.get(fetch_url, timeout=timeout)

                        if cap_resp.status_code != 200 or not cap_resp.text.strip():
                            logger.warning(f"[TRANSCRIPT] Caption {fmt} fetch empty for {lang} (status={cap_resp.status_code})")
                            continue

                        result = parser(cap_resp.text if fmt == "srv1" else cap_resp.json())
                        if result and result.status == "success":
                            logger.info(f"[TRANSCRIPT] InnerTube success: {result.word_count} words lang={lang}")
                            return result

                    except Exception as fetch_err:
                        logger.warning(f"[TRANSCRIPT] Caption fetch failed for {lang}/{fmt}: {fetch_err}")
                        continue

            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="captions_unavailable", provider=self.name,
                error="Caption tracks found but all returned empty content."
            )

        except Exception as e:
            error_name = type(e).__name__
            error_str = str(e)
            logger.error(f"[TRANSCRIPT] FallbackTranscriptProvider error: {error_name}: {error_str}")

            if any(k in error_str for k in ("429", "TooManyRequests", "IpBlocked")):
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="rate_limited", provider=self.name,
                    error="YouTube rate-limited this server."
                )
            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="error", provider=self.name,
                error=f"FallbackTranscriptProvider error: {error_str}"
            )

    def _parse_json3(self, data: dict) -> Optional["TranscriptResult"]:
        """Parse YouTube's JSON3 caption format."""
        events = data.get("events", [])
        raw_segments = []
        for event in events:
            if "segs" in event:
                text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
                if text:
                    raw_segments.append({
                        "text": text.replace("\n", " ").strip(),
                        "start": event.get("tStartMs", 0) / 1000.0,
                        "duration": event.get("dDurationMs", 0) / 1000.0
                    })
        return self._build_result(raw_segments)

    def _parse_xml(self, xml_text: str) -> Optional["TranscriptResult"]:
        """Parse YouTube's SRV1/XML caption format."""
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None
        raw_segments = []
        for text_el in root.iter("text"):
            text = (text_el.text or "").strip()
            if text:
                start = float(text_el.get("start", 0))
                dur = float(text_el.get("dur", 0))
                raw_segments.append({"text": text, "start": start, "duration": dur})
        return self._build_result(raw_segments)

    def _build_result(self, raw_segments: list) -> Optional["TranscriptResult"]:
        """Build a TranscriptResult from raw segments."""
        if not raw_segments:
            return None
        formatted_lines = []
        plain_parts = []
        for seg in raw_segments:
            text = seg.get("text", "").strip()
            if not text:
                continue
            plain_parts.append(text)
            start_sec = int(seg.get("start", 0))
            mins, secs = divmod(start_sec, 60)
            formatted_lines.append(f"[{mins:02d}:{secs:02d}] {text}")

        full_text = "\n".join(formatted_lines)
        word_count = len(" ".join(plain_parts).split())
        if word_count < 10:
            return TranscriptResult(
                transcript=None, raw_segments=raw_segments, word_count=word_count,
                status="captions_unavailable", provider=self.name,
                error=f"Transcript too short ({word_count} words)."
            )
        return TranscriptResult(
            transcript=full_text, raw_segments=raw_segments,
            word_count=word_count, status="success",
            provider=self.name, error=None
        )



class WhisperAudioTranscriptProvider(TranscriptProvider):
    """Fallback provider using yt-dlp to download audio and OpenAI Whisper to transcribe."""
    @property
    def name(self) -> str:
        return "OpenAI-Whisper-Audio-Fallback"

    def get_transcript(self, video_id: str, timeout: float = 300.0) -> TranscriptResult:
        import os
        import io
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
            
        import tempfile
        if os.environ.get("VERCEL") == "1" or os.environ.get("AWS_EXECUTION_ENV"):
            temp_dir = Path(tempfile.gettempdir()) / "yt_audio"
        else:
            temp_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent / "temp"
            
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create temp directory: {e}")
            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="error", provider=self.name,
                error=f"Could not create temporary directory for audio extraction: {e}"
            )
        
        out_tmpl = str(temp_dir / f"{video_id}.%(ext)s")
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # yt-dlp options: use a realistic user-agent + request headers
        # to reduce bot-detection risk on cloud server IPs.
        ydl_opts = {
            'format': 'worstaudio[ext=m4a]/worstaudio/bestaudio',
            'outtmpl': out_tmpl,
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/127.0.0.0 Safari/537.36'
                ),
                'Accept-Language': 'en-US,en;q=0.9',
            },
            'socket_timeout': 30,
            'retries': 1,          # Do NOT hammer YouTube if blocked
            'fragment_retries': 1,
        }
        
        # Capture yt-dlp stderr/stdout to detect bot-check errors
        import io as _io
        error_buffer = _io.StringIO()
        
        class _LogCapture:
            """Capture yt-dlp log messages into a buffer."""
            def debug(self, msg):
                pass
            def info(self, msg):
                pass
            def warning(self, msg):
                error_buffer.write(msg + "\n")
            def error(self, msg):
                error_buffer.write(msg + "\n")
        
        ydl_opts['logger'] = _LogCapture()
        
        try:
            print(f"[5] Fallback transcription started (Whisper) for {video_id}...")
            logger.info(f"Downloading audio for {video_id} using yt-dlp...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([youtube_url])
                
        except Exception as e:
            captured = error_buffer.getvalue()
            raw_err = str(e) + "\n" + captured
            
            # ---- Detect YouTube bot-check / sign-in required ----
            bot_check_signals = (
                "Sign in to confirm",
                "confirm you're not a bot",
                "sign in",
                "bot",
                "cookies",
                "Use --cookies",
                "429",
                "Too Many Requests",
            )
            if any(s.lower() in raw_err.lower() for s in bot_check_signals):
                logger.warning(f"yt-dlp bot-check detected for {video_id}. Cannot download audio from this server.")
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="bot_check",
                    provider=self.name,
                    error=(
                        "YouTube is requiring sign-in to access this video from our servers. "
                        "Audio transcription is unavailable for this video in the cloud environment. "
                        "Please paste the video transcript manually."
                    )
                )
            
            # Other download error
            logger.error(f"yt-dlp download failed: {e}")
            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="error", provider=self.name,
                error=f"Audio download failed: {e}"
            )
        
        # ---- Audio downloaded, now transcribe ----
        try:
            possible_files = list(temp_dir.glob(f"{video_id}.*"))
            if not possible_files:
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="error", provider=self.name,
                    error="Audio file was not created after yt-dlp download."
                )
            audio_path = str(possible_files[0])
            
            # Reject files > 25 MB (Whisper API limit)
            file_size = os.path.getsize(audio_path)
            if file_size > 25 * 1024 * 1024:
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="error", provider=self.name,
                    error="Audio file exceeds the 25MB limit for the transcription API."
                )
                
            logger.info(f"Sending audio {os.path.basename(audio_path)} ({file_size // 1024}KB) to Whisper API...")
            
            api_url = "https://api.openai.com/v1/audio/transcriptions"
            model_name = "whisper-1"
            if api_key.startswith("gsk_"):
                api_url = "https://api.groq.com/openai/v1/audio/transcriptions"
                model_name = "whisper-large-v3"
            
            with open(audio_path, "rb") as f:
                resp = requests.post(
                    api_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (os.path.basename(audio_path), f)},
                    data={"model": model_name, "response_format": "verbose_json"},
                    timeout=timeout
                )
                
            if resp.status_code != 200:
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("error", {}).get("message", resp.text[:300])
                except Exception:
                    err_msg = resp.text[:300]
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="error", provider=self.name,
                    error=f"Transcription API error ({resp.status_code}): {err_msg}"
                )
                
            data = resp.json()
            raw_segments = []
            if "segments" in data:
                for seg in data["segments"]:
                    raw_segments.append({
                        "text": seg.get("text", "").strip(),
                        "start": seg.get("start", 0),
                        "duration": seg.get("end", 0) - seg.get("start", 0)
                    })
            elif "text" in data:
                # Flat response fallback
                raw_segments = [{"text": data["text"].strip(), "start": 0, "duration": 0}]
                
            if not raw_segments:
                return TranscriptResult(
                    transcript=None, raw_segments=[], word_count=0,
                    status="error", provider=self.name,
                    error="Whisper returned an empty transcript."
                )
                
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
            logger.error(f"Whisper transcription failed: {e}")
            return TranscriptResult(
                transcript=None, raw_segments=[], word_count=0,
                status="error", provider=self.name,
                error=f"Transcription failed: {e}"
            )
        finally:
            # Always clean up temp files
            try:
                for f in temp_dir.glob(f"{video_id}.*"):
                    f.unlink(missing_ok=True)
            except Exception as cleanup_err:
                logger.warning(f"Could not clean up temp file: {cleanup_err}")


class TranscriptManager:
    """Coordinates transcript providers with strict rate-limit protection and fallback.
    
    Provider chain (no yt-dlp):
      1. PrimaryTranscriptProvider  — youtube-transcript-api (all languages, auto-generated)
      2. FallbackTranscriptProvider — YouTube timedtext API / watch page scraping
    """
    def __init__(self, providers: Optional[List[TranscriptProvider]] = None):
        self.providers: List[TranscriptProvider] = providers or [
            PrimaryTranscriptProvider(),
            FallbackTranscriptProvider(),
            # WhisperAudioTranscriptProvider is intentionally excluded.
            # yt-dlp cannot be used on Vercel serverless (YouTube bot-check blocks cloud IPs).
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
            # Whisper needs much more time than the default 15s for downloading and API calls
            provider_timeout = 300.0 if "Whisper" in provider.name else timeout
            result = provider.get_transcript(video_id, timeout=provider_timeout)
            
            if result.status == "success":
                logger.info(f"Success with transcript provider: {provider.name}")
                return result

            logger.warning(f"Provider {provider.name} failed. Status: {result.status}. Error: {result.error}")
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
