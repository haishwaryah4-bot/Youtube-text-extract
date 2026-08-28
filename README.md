# TubeAction AI — YouTube Video Intelligence & Action Extractor

TubeAction AI transforms YouTube video content into structured intelligence, step-by-step action guides, and downloadable PDF reports, powered by a **LangGraph StateGraph workflow**.

## 🌟 Key Features

- **Grounded Intelligence:** Analyzes authentic YouTube video transcripts with zero hallucination.
- **Action Extraction:** Differentiates between *Demonstrated Actions* (performed on-screen) and *Recommended Actions* (advised by the speaker).
- **Interactive Checklist:** Live progress tracker to mark off steps as you complete them.
- **Provider-Based Transcript Layer:** Clean, fault-tolerant transcript manager with strict rate-limit protection.
- **LangGraph StateGraph Workflow:** Modular graph architecture covering validation, chunking, summarization, action extraction, deduplication, review, and PDF generation.
- **Automated PDF Reports:** Generates professional A4 intelligence summaries using `fpdf2`.
- **Grounded AI Q&A Assistant:** Chat with video content grounded directly in verified transcript data.

---

## 🏗️ Architecture

```
          FRONTEND (Vanilla JS / CSS)
                     ↓
          POST /api/youtube/analyze
                     ↓
              YouTube Service
                     ↓
         Transcript Provider Layer
                     ↓
            LangGraph Workflow
                     ↓
     ┌───────────────┼───────────────┐
     ↓               ↓               ↓
  Summary         Actions         Review
     └───────────────┼───────────────┘
                     ↓
               PDF Generator
                     ↓
               JSON Response
                     ↓
                  FRONTEND
```

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Create a `.env` file in the root directory:
```env
OPENAI_API_KEY=your_openai_api_key_here
PORT=8000
```
*(If no API key is set, the application uses deterministic grounded extraction algorithms).*

### 3. Run the Application
```bash
python run.py
```

Open your browser at [http://localhost:8000](http://localhost:8000).

---

## 📡 API Reference

### Analyze YouTube Video
- **Endpoint:** `POST /api/youtube/analyze`
- **Request Body:**
  ```json
  {
    "youtube_url": "https://www.youtube.com/watch?v=..."
  }
  ```
- **Response Format:**
  ```json
  {
    "success": true,
    "video_id": "...",
    "title": "...",
    "author": "...",
    "transcript_status": "success",
    "transcript_provider": "YouTubeTranscriptApi-Primary",
    "summary": "...",
    "key_points": ["..."],
    "demonstrated_actions": [...],
    "recommended_actions": [...],
    "tools_materials": ["..."],
    "precautions": ["..."],
    "pdf_path": "...",
    "error": null
  }
  ```

---

## 🛡️ License
MIT License.
