import os
import json
import re
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
            
        if self.api_key.startswith("gsk_"):
            self.api_url = "https://api.groq.com/openai/v1/chat/completions"
            self.model = "openai/gpt-oss-120b"
        else:
            self.api_url = "https://api.openai.com/v1/chat/completions"
            self.model = "gpt-4o-mini"

    def process_transcript(self, title: str, author: str, transcript_text: str, video_desc: str = "") -> Dict[str, Any]:
        """
        Process the complete video transcript with strict grounding and extract all required sections.
        """
        if not self.api_key:
            return self._fallback_grounded_extractor(title, author, transcript_text, video_desc)

        system_prompt = (
            "You are an expert video content analyst. Analyze the following transcript of a YouTube video "
            "and produce a comprehensive, strictly grounded, high-fidelity JSON analysis.\n\n"
            "CRITICAL GROUNDING RULES:\n"
            "1. NEVER hallucinate, extrapolate, or assume missing video content.\n"
            "2. Ground every single point, step, and recommendation strictly in what is stated in the transcript.\n"
            "3. Provide timestamp citations (e.g. [02:14]) for every major summary point and action step. "
            "If the transcript lacks timestamps, label them as 'unavailable'.\n"
            "4. For every action, extract detailed step-by-step instructions. For each step, include:\n"
            "   - step_number: order index starting from 1\n"
            "   - what_to_do: clear instruction of what to do\n"
            "   - why_it_matters: why this step matters / purpose / benefit\n"
            "   - tools_resources: list of tools, resources, or links mentioned for this step (empty list if none)\n"
            "   - prerequisites_cautions: prerequisites or cautions/warnings for this step (empty list if none)\n"
            "   - timestamp: the timestamp citation where this step begins (e.g. '[03:45]') or 'unavailable'\n"
            "   - evidence: exact supporting transcript excerpt/evidence for this step\n"
            "5. The 'overview' summary MUST be formatted with bold headings exactly like this:\n"
            "   **Context:** one or two sentences giving background. [timestamp]\n"
            "   **Content Summary:** multi-sentence coverage of the main subject, key ideas, and notable details. [timestamp - timestamp]\n"
            "   **Key Moments:** bullet list of the most important or interesting moments, each with a timestamp.\n"
            "   **Actions / Steps:** numbered instructions extracted from the video, each with a timestamp.\n"
            "   Use this exact section order. Include real timestamps from the transcript. Do NOT collapse everything into one paragraph.\n"
            "6. Output must be strictly valid JSON without markdown wrapping or backticks."
        )

        user_prompt = f"""
        VIDEO TITLE: {title}
        CREATOR: {author}

        TRANSCRIPT CONTENT:
        {transcript_text[:18000]}

        OUTPUT JSON FORMAT:
        {{
          "overview": "Detailed, chronological summary covering the entire video section-by-section, citing timestamps (e.g. [01:23]) for major points. Thorough explanation of explanations, warnings, and conclusions.",
          "main_topics": [
            {{"topic": "Important topic discussed", "explanation": "Detailed explanation with timestamp citations (e.g. [04:30]) and supporting transcript excerpt."}}
          ],
          "key_points": {{
            "facts": ["Important fact 1 [01:10] (supporting excerpt)", "Important fact 2 [02:15] (supporting excerpt)"],
            "explanations": ["Important explanation 1 [03:05] (supporting excerpt)"],
            "recommendations": ["Important recommendation 1 [04:20] (supporting excerpt)"]
          }},
          "actions": [
            {{
              "name": "Action Name",
              "action_type": "demonstrated",
              "description": "What needs to be done",
              "why": "Why this action is performed",
              "tools_materials": ["Tool/material 1"],
              "precautions": ["Precaution/warning 1"],
              "timing_frequency": "Timing or frequency if mentioned",
              "steps": [
                {{
                  "step_number": 1,
                  "what_to_do": "Step 1 description",
                  "why_it_matters": "Why this step matters",
                  "tools_resources": ["Tool A"],
                  "prerequisites_cautions": ["Caution B"],
                  "timestamp": "[03:45]",
                  "evidence": "supporting transcript excerpt"
                }}
              ]
            }}
          ],
          "action_checklist": [
            "Action 1 short task description",
            "Action 2 short task description"
          ],
          "final_summary": "Thorough chronological summary of key takeaways and actionable conclusions with timestamp citations."
        }}
        """

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
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
                
                print(f"[AIProcessor] OpenAI/Groq API Error ({response.status_code}): {error_detail}. Falling back to Free Local Summary Mode.")
                return self._fallback_grounded_extractor(title, author, transcript_text, video_desc)

            data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            result = json.loads(raw_content)
            return self._validate_and_sanitize_result(result, title)
        except Exception as e:
            print(f"[AIProcessor] Error: {e}. Using Free Local Summary Mode.")
            return self._fallback_grounded_extractor(title, author, transcript_text, video_desc)

    def chat_with_video(self, transcript: str, summary_data: Dict[str, Any], question: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """Answer user questions grounded strictly in the transcript and extracted summary."""
        if not self.api_key:
            return self._fallback_grounded_chat(transcript, summary_data, question)

        system_prompt = (
            "You are an AI assistant answering questions about a specific YouTube video.\n"
            "Answer the user's question accurately and concisely, strictly grounded in the provided transcript and summary.\n"
            "You MUST cite specific timestamps (e.g. [02:14]) from the transcript when discussing details. "
            "If the transcript has no timestamps, label citations as 'unavailable'.\n"
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
            elif response.status_code in (401, 403, 429, 500, 502, 503, 504):
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
            steps_texts = []
            for s in act.get('steps', []):
                if isinstance(s, dict):
                    steps_texts.append(s.get('what_to_do', ''))
                else:
                    steps_texts.append(str(s))
            act_text = f"{act.get('name', '')} {act.get('description', '')} {' '.join(steps_texts)}".lower()
            if any(qw in act_text for qw in q_words):
                matching_actions.append(act)
        
        if matching_actions:
            res_parts = [f"Based on the video content for '{summary_data.get('title', 'this video')}':"]
            for act in matching_actions[:2]:
                res_parts.append(f"\n• **{act.get('name')}** ({act.get('action_type', 'action').title()}): {act.get('description')}")
                if act.get('steps'):
                    step_strings = []
                    for s in act.get('steps')[:3]:
                        if isinstance(s, dict):
                            ts_str = f" {s.get('timestamp')}" if s.get('timestamp') and s.get('timestamp') != 'unavailable' else ""
                            step_strings.append(f"{s.get('what_to_do')}{ts_str}")
                        else:
                            step_strings.append(str(s))
                    res_parts.append("  Steps: " + " → ".join(step_strings))
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
            "final_summary": final_summary,
            "is_local_fallback": result.get("is_local_fallback", False)
        }

    def _fallback_grounded_extractor(self, title: str, author: str, transcript_text: str, video_desc: str = "") -> Dict[str, Any]:
        """
        Local fallback extractor if no OpenAI key is set or API fails.
        Performs local extractive summarization using basic frequency scoring.
        """
        # Sanitize text
        _url_re = re.compile(r'https?://\S+', re.IGNORECASE)
        transcript_clean = _url_re.sub('', transcript_text).strip()
        lines = [line.strip() for line in transcript_clean.split('\n') if line.strip()]
        
        parsed_lines = []
        for line in lines:
            match = re.search(r'\[(\d{1,2}:\d{2}(?::\d{2})?)\]', line)
            if match:
                clean_text = line.replace(match.group(0), "").strip()
                clean_text = re.sub(r'^[:\s\-\u2013\u2014]+', '', clean_text)
                parsed_lines.append({"time": f"[{match.group(1)}]", "text": clean_text})
            else:
                parsed_lines.append({"time": "unavailable", "text": line})

        # Calculate word frequency
        stop_words = set(["the", "and", "is", "in", "to", "of", "a", "it", "that", "this", "you", "for", "on", "are", "with", "as", "i", "we", "they", "so", "be", "but", "not", "have", "from", "or", "what", "how", "can", "your", "all", "about"])
        word_freq = {}
        for p in parsed_lines:
            words = re.findall(r'\b\w+\b', p["text"].lower())
            for w in words:
                if w not in stop_words and len(w) > 3:
                    word_freq[w] = word_freq.get(w, 0) + 1

        # Score sentences
        for p in parsed_lines:
            score = 0
            words = re.findall(r'\b\w+\b', p["text"].lower())
            unique_words = set(words)
            for w in unique_words:
                if w in word_freq:
                    score += word_freq[w]
            p["score"] = score / (len(words) + 1) # Normalize by length

        # Sort by score for extraction, but keep original order for summary
        sorted_lines = sorted(parsed_lines, key=lambda x: x["score"], reverse=True)
        
        # Get top sentences for overview
        top_sentences = sorted_lines[:15]
        
        # Create summary from chronologically ordered top sentences
        top_indices = {parsed_lines.index(p) for p in top_sentences}
        summary_lines = [p for i, p in enumerate(parsed_lines) if i in top_indices]
        
        # Format the output
        overview_parts = []
        for p in summary_lines:
            ts = p["time"] if p["time"] != "unavailable" else ""
            overview_parts.append(f"{ts} {p['text']}".strip())
            
        overview_text = "\n\n".join([" ".join(overview_parts[i:i+3]) for i in range(0, len(overview_parts), 3)])
        if not overview_text:
            overview_text = "No transcript content available to summarize."
            
        overview = f"**Context:** {title}\n**Content Summary:**\n{overview_text}"

        # Extract Key Points (top 6 sentences)
        key_points_facts = []
        for p in sorted_lines[:6]:
            ts = f" {p['time']}" if p['time'] != "unavailable" else ""
            key_points_facts.append(f"{p['text']}{ts}")

        # Extract Topics (top frequency words)
        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:6]
        main_topics = []
        for w, freq in top_words:
            for p in sorted_lines:
                if w in p["text"].lower():
                    ts = f" {p['time']}" if p['time'] != "unavailable" else ""
                    main_topics.append({"topic": w.title(), "explanation": f"{p['text']}{ts}"})
                    break

        return self._validate_and_sanitize_result({
            "overview": overview,
            "main_topics": main_topics,
            "key_points": {
                "facts": key_points_facts,
                "explanations": [],
                "recommendations": []
            },
            "actions": [],
            "action_checklist": [],
            "final_summary": overview_text,
            "is_local_fallback": True
        }, title)
