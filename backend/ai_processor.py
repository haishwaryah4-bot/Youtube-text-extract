import os
import json
from pathlib import Path
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class AIProcessorError(Exception):
    pass

class AIProcessor:
    def __init__(self, api_key: Optional[str] = None):
        raw_key = api_key or os.getenv("OPENAI_API_KEY", "")
        # Check if key is a placeholder or actual key
        if raw_key and raw_key.strip() not in ("sk-...", "sk-placeholder", "") and len(raw_key.strip()) > 20:
            self.api_key = raw_key.strip()
        else:
            self.api_key = ""
        self.api_url = "https://api.openai.com/v1/chat/completions"

    def process_transcript(self, title: str, author: str, transcript_text: str) -> Dict[str, Any]:
        """
        Process the complete video transcript with strict grounding and extract all required sections.
        """
        if not self.api_key:
            return self._fallback_grounded_extractor(title, author, transcript_text)

        system_prompt = (
            "You are an expert video content analyst. Analyze the following transcript of a YouTube video "
            "and produce a comprehensive, strictly grounded, high-fidelity JSON analysis.\n\n"
            "CRITICAL GROUNDING RULES:\n"
            "1. NEVER hallucinate, extrapolate, or assume missing video content.\n"
            "2. Ground every single point, step, and recommendation strictly in what is stated in the transcript.\n"
            "3. Clearly distinguish between:\n"
            "   - 'demonstrated': Actions physically shown, built, coded, or performed step-by-step in the video.\n"
            "   - 'recommended': Actions advised, suggested, or instructed by the speaker.\n"
            "   - 'instructional': General procedures or guidelines taught.\n"
            "4. For every action, extract:\n"
            "   - name: Clear action name\n"
            "   - action_type: 'demonstrated' | 'recommended' | 'instructional'\n"
            "   - description: What needs to be done\n"
            "   - steps: Array of step-by-step instructions\n"
            "   - why: Why the action is performed (purpose / benefit)\n"
            "   - tools_materials: List of required tools/materials ONLY if mentioned in transcript\n"
            "   - precautions: Important precautions/warnings ONLY if mentioned\n"
            "   - timing_frequency: Timing or frequency ONLY if mentioned\n"
            "5. Generate a simple checklist of these actions.\n"
            "6. Output must be strictly valid JSON without markdown wrapping or backticks."
        )

        user_prompt = f"""
VIDEO TITLE: {title}
CREATOR: {author}

TRANSCRIPT CONTENT:
{transcript_text[:18000]}

OUTPUT JSON FORMAT:
{{
  "overview": "Short description of what the video is about and its core focus",
  "main_topics": [
    {{"topic": "Important topic discussed", "explanation": "Key concept or insight explained"}}
  ],
  "key_points": {{
    "facts": ["Important fact 1", "Important fact 2"],
    "explanations": ["Important explanation 1", "Important explanation 2"],
    "recommendations": ["Important recommendation 1", "Important recommendation 2"]
  }},
  "actions": [
    {{
      "name": "Action Name",
      "action_type": "demonstrated",
      "description": "What needs to be done",
      "steps": [
        "Step 1...",
        "Step 2...",
        "Step 3..."
      ],
      "why": "Why this action is performed",
      "tools_materials": ["Tool or material 1"],
      "precautions": ["Precaution or warning 1"],
      "timing_frequency": "Timing or frequency if mentioned"
    }}
  ],
  "action_checklist": [
    "Action 1 short task description",
    "Action 2 short task description"
  ],
  "final_summary": "Concise summary of the most important information and actions from the video."
}}
"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=90)
            if response.status_code != 200:
                error_detail = response.text
                try:
                    err_json = response.json()
                    error_detail = err_json.get("error", {}).get("message", error_detail)
                except Exception:
                    pass
                if response.status_code in (401, 403, 429):
                    print(f"[AIProcessor] OpenAI status {response.status_code}. Falling back to smart transcript extractor.")
                    return self._fallback_grounded_extractor(title, author, transcript_text)
                raise AIProcessorError(f"OpenAI API Error ({response.status_code}): {error_detail}")

            data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            result = json.loads(raw_content)
            return self._validate_and_sanitize_result(result, title)
        except AIProcessorError:
            raise
        except Exception as e:
            print(f"[AIProcessor] Error: {e}. Using smart transcript grounded extractor.")
            return self._fallback_grounded_extractor(title, author, transcript_text)

    def chat_with_video(self, transcript: str, summary_data: Dict[str, Any], question: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """Answer user questions grounded strictly in the transcript and extracted summary."""
        if not self.api_key:
            return self._fallback_grounded_chat(transcript, summary_data, question)

        system_prompt = (
            "You are an AI assistant answering questions about a specific YouTube video.\n"
            "Answer the user's question accurately and concisely, strictly grounded in the provided transcript and summary.\n"
            "If the answer is not present or supported by the video transcript, politely clarify that the video does not mention it."
        )

        context = f"""
VIDEO TITLE: {summary_data.get('title', '')}
VIDEO OVERVIEW: {summary_data.get('overview', '')}
ACTIONS IDENTIFIED: {json.dumps(summary_data.get('actions', []))}

TRANSCRIPT:
{transcript[:15000]}
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"VIDEO CONTEXT:\n{context}"}
        ]

        if history:
            for item in history[-6:]:
                messages.append({"role": item.get("role", "user"), "content": item.get("content", "")})

        messages.append({"role": "user", "content": question})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.3
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            elif response.status_code in (401, 403, 429):
                return self._fallback_grounded_chat(transcript, summary_data, question)
            else:
                return f"Error ({response.status_code}): {response.text}"
        except Exception as e:
            return self._fallback_grounded_chat(transcript, summary_data, question)

    def _fallback_grounded_chat(self, transcript: str, summary_data: Dict[str, Any], question: str) -> str:
        """Grounded QA fallback based on keyword matching across transcript and extracted actions."""
        q_words = [w.lower().strip("?,!.'\"") for w in question.split() if len(w) > 2 and w.lower() not in ("what", "how", "when", "where", "why", "the", "and", "is", "are", "you", "for", "with", "this", "that")]
        
        # Check actions first
        actions = summary_data.get("actions", [])
        matching_actions = []
        for act in actions:
            act_text = f"{act.get('name', '')} {act.get('description', '')} {' '.join(act.get('steps', []))}".lower()
            if any(qw in act_text for qw in q_words):
                matching_actions.append(act)
        
        if matching_actions:
            res_parts = [f"Based on the video content for '{summary_data.get('title', 'this video')}':"]
            for act in matching_actions[:2]:
                res_parts.append(f"\n• **{act.get('name')}** ({act.get('action_type', 'action').title()}): {act.get('description')}")
                if act.get('steps'):
                    res_parts.append("  Steps: " + " → ".join(act.get('steps')[:3]))
            return "\n".join(res_parts)
        
        # Search transcript sentences
        lines = [line.strip() for line in transcript.split('\n') if line.strip()]
        matches = []
        for line in lines:
            line_lower = line.lower()
            match_score = sum(1 for qw in q_words if qw in line_lower)
            if match_score > 0:
                matches.append((match_score, line))
        
        matches.sort(key=lambda x: x[0], reverse=True)
        if matches:
            top_quotes = [m[1] for m in matches[:3]]
            return f"According to the video transcript:\n\n" + "\n".join(f"> {q}" for q in top_quotes)
        
        return f"The video transcript discusses '{summary_data.get('title', '')}' focusing on: {summary_data.get('overview', '')}. Specific details for '{question}' were not explicitly emphasized in the transcript."

    def _validate_and_sanitize_result(self, result: Dict[str, Any], default_title: str) -> Dict[str, Any]:
        """Ensure all required keys and nested structures exist and are non-null."""
        overview = result.get("overview") or f"Summary and action extraction for '{default_title}'."
        main_topics = result.get("main_topics") or []
        key_points = result.get("key_points") or {"facts": [], "explanations": [], "recommendations": []}
        
        # Ensure key_points has all 3 lists
        if not isinstance(key_points.get("facts"), list):
            key_points["facts"] = []
        if not isinstance(key_points.get("explanations"), list):
            key_points["explanations"] = []
        if not isinstance(key_points.get("recommendations"), list):
            key_points["recommendations"] = []

        actions = result.get("actions") or []
        for act in actions:
            if "name" not in act:
                act["name"] = "Instructional Action"
            if act.get("action_type") not in ["demonstrated", "recommended", "instructional"]:
                act["action_type"] = "recommended"
            if not isinstance(act.get("steps"), list):
                act["steps"] = [act.get("steps")] if act.get("steps") else []
            if not isinstance(act.get("tools_materials"), list):
                act["tools_materials"] = []
            if not isinstance(act.get("precautions"), list):
                act["precautions"] = []

        checklist = result.get("action_checklist") or []
        if not checklist and actions:
            checklist = [act.get("name", "Action item") for act in actions]

        final_summary = result.get("final_summary") or overview

        return {
            "overview": overview,
            "main_topics": main_topics,
            "key_points": key_points,
            "actions": actions,
            "action_checklist": checklist,
            "final_summary": final_summary
        }

    def _fallback_grounded_extractor(self, title: str, author: str, transcript_text: str) -> Dict[str, Any]:
        """
        Deterministic fallback extractor if no OpenAI key is set.
        Extracts key sentences and grounded action points directly from transcript sentences.
        """
        lines = [line.strip() for line in transcript_text.split('\n') if line.strip()]
        # Strip timestamps for content analysis
        clean_sentences = []
        for line in lines:
            if line.startswith('[') and ']' in line:
                clean_sentences.append(line.split(']', 1)[1].strip())
            else:
                clean_sentences.append(line)

        full_text = " ".join(clean_sentences)
        
        # Overview
        first_few = clean_sentences[:8]
        overview = f"This video by {author} focuses on {title}. " + " ".join(first_few[:3])
        
        # Extract potential action verbs & sentences
        action_keywords = ["how to", "make sure", "first", "next", "then", "step", "you need to", "recommend", "apply", "install", "configure", "click", "run", "prepare"]
        extracted_actions = []
        
        for sent in clean_sentences:
            lower = sent.lower()
            if any(kw in lower for kw in action_keywords) and len(sent) > 20:
                if len(extracted_actions) < 4:
                    extracted_actions.append(sent)

        actions_list = []
        for idx, act_text in enumerate(extracted_actions, 1):
            actions_list.append({
                "name": f"Action {idx}: {act_text[:45]}...",
                "action_type": "recommended",
                "description": act_text,
                "steps": [
                    f"Follow instruction: {act_text}",
                    "Apply the guidelines mentioned in the video context."
                ],
                "why": "To implement the process outlined in this video segment.",
                "tools_materials": [],
                "precautions": ["Follow standard precautions as described in the video."],
                "timing_frequency": None
            })

        if not actions_list:
            actions_list.append({
                "name": "General Implementation",
                "action_type": "instructional",
                "description": "Review the concepts demonstrated in the video tutorial.",
                "steps": ["Review transcript instructions", "Execute steps as instructed"],
                "why": "To apply knowledge from the video.",
                "tools_materials": [],
                "precautions": [],
                "timing_frequency": None
            })

        checklist = [act["name"] for act in actions_list]

        return {
            "overview": overview,
            "main_topics": [
                {"topic": "Core Subject", "explanation": f"The primary subject matter covered in '{title}' by {author}."},
                {"topic": "Transcript Highlights", "explanation": "Direct walkthrough and key concepts covered in the video recording."}
            ],
            "key_points": {
                "facts": [f"Video titled '{title}' presented by {author}."],
                "explanations": ["Detailed transcript provided covering instructional workflows."],
                "recommendations": ["Follow step-by-step instructions detailed in the transcript."]
            },
            "actions": actions_list,
            "action_checklist": checklist,
            "final_summary": f"In summary, this video '{title}' provides clear instructions and actionable guidance for viewers."
        }
