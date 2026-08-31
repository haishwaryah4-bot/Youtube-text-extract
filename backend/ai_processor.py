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
                if response.status_code in (401, 403, 429, 500, 502, 503, 504):
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
            "final_summary": final_summary
        }

    def _fallback_grounded_extractor(self, title: str, author: str, transcript_text: str, video_desc: str = "") -> Dict[str, Any]:
        """
        Deterministic fallback extractor if no OpenAI key is set.
        Extracts key sentences and grounded action points directly from transcript sentences.
        """
        # Sanitize video_desc: strip all bare URLs so they can never contaminate summary fields
        _url_re = re.compile(r'https?://\S+', re.IGNORECASE)
        video_desc_clean = _url_re.sub('', video_desc).strip()
        video_desc_clean = re.sub(r'\n{3,}', '\n\n', video_desc_clean).strip()

        # Sanitize transcript_text: prevent users from pasting a raw URL and having it parsed as content
        transcript_clean = _url_re.sub('', transcript_text).strip()
        lines = [line.strip() for line in transcript_clean.split('\n') if line.strip()]
        
        parsed_lines = []
        for line in lines:
            match = re.search(r'\[(\d{1,2}:\d{2}(?::\d{2})?)\]', line)
            if match:
                clean_text = line.replace(match.group(0), "").strip()
                # Clean up leading hyphens or colons
                clean_text = re.sub(r'^[:\s\-\u2013\u2014]+', '', clean_text)
                parsed_lines.append({"time": f"[{match.group(1)}]", "text": clean_text})
            else:
                parsed_lines.append({"time": "unavailable", "text": line})

        # Build structured overview with bold headings
        total = len(parsed_lines)

        def pick_lines(start_frac, end_frac, n):
            """Pick up to n lines from a fraction of the transcript."""
            s = int(total * start_frac)
            e = int(total * end_frac)
            return [p for p in parsed_lines[s:e] if p["text"]] [:n]

        def ts_range(group):
            """Return '[start - end]' or '[start]' or '' from a group of parsed lines."""
            times = [p["time"] for p in group if p["time"] != "unavailable"]
            if len(times) >= 2:
                return f"[{times[0].strip('[]')} - {times[-1].strip('[]')}]"
            elif len(times) == 1:
                return f"{times[0]}"
            return ""

        context_lines  = pick_lines(0.0, 0.15, 3)
        content_lines  = pick_lines(0.1,  0.8,  6)
        moment_lines   = pick_lines(0.0,  1.0,  6)  # spread across whole video
        action_lines   = [p for p in parsed_lines if any(
            kw in p["text"].lower() for kw in ["first","next","then","step","install","run","click","apply","make sure","prepare","open","go to"]
        )][:6]

        context_text = " ".join(p["text"] for p in context_lines)
        context_ts   = ts_range(context_lines)

        content_text = " ".join(p["text"] for p in content_lines)
        content_ts   = ts_range(content_lines)

        moment_bullets = ""
        step_interval = max(1, total // 6)
        for i, p in enumerate(parsed_lines[::step_interval][:6]):
            ts = f" {p['time']}" if p["time"] != "unavailable" else ""
            moment_bullets += f"\n- {p['text']}{ts}"

        action_numbered = ""
        for i, p in enumerate(action_lines, 1):
            ts = f" {p['time']}" if p["time"] != "unavailable" else ""
            action_numbered += f"\n{i}. {p['text']}{ts}"

        sections = []
        if context_text:
            sections.append(f"**Context:** {context_text}" + (f" {context_ts}" if context_ts else ""))
        if content_text:
            sections.append(f"**Content Summary:** {content_text}" + (f" {content_ts}" if content_ts else ""))
        if moment_bullets:
            sections.append(f"**Key Moments:**{moment_bullets}")
        if action_numbered:
            sections.append(f"**Actions / Steps:**{action_numbered}")

        overview = "\n\n".join(sections)
        if not overview or not sections:
            # No transcript sections could be built — use sanitised description or generic placeholder
            if video_desc_clean:
                overview = f"**Video Description:**\n{video_desc_clean}"
            else:
                overview = f"**Content Summary:** Video overview for '{title}' by {author}."

        # Build final_summary from the last 20 % of the transcript (wrap-up / conclusions)
        conclusion_lines = pick_lines(0.75, 1.0, 4)
        conclusion_text = " ".join(p["text"] for p in conclusion_lines)
        conclusion_ts = ts_range(conclusion_lines)
        if conclusion_text:
            final_summary = f"**Conclusions:** {conclusion_text}" + (f" {conclusion_ts}" if conclusion_ts else "")
        else:
            final_summary = overview

        # Extract potential action verbs & sentences chronologically
        action_keywords = ["how to", "make sure", "first", "next", "then", "step", "you need to", "recommend", "apply", "install", "configure", "click", "run", "prepare"]
        actions_list = []
        idx = 1
        for pline in parsed_lines:
            lower = pline["text"].lower()
            if any(kw in lower for kw in action_keywords) and len(pline["text"]) > 20:
                actions_list.append({
                    "name": f"Action {idx}: {pline['text'][:45]}...",
                    "action_type": "recommended",
                    "description": pline["text"],
                    "why": "To implement the guidelines demonstrated at this point in the video.",
                    "tools_materials": [],
                    "precautions": ["Follow standard precautions as described in the video."],
                    "timing_frequency": None,
                    "steps": [
                        {
                            "step_number": 1,
                            "what_to_do": pline["text"],
                            "why_it_matters": "To execute the step described in the video tutorial.",
                            "tools_resources": [],
                            "prerequisites_cautions": ["Observe standard caution during execution."],
                            "timestamp": pline["time"],
                            "evidence": pline["text"]
                        }
                    ]
                })
                idx += 1
                if len(actions_list) >= 8:
                    break

        if not actions_list:
            for idx, pline in enumerate(parsed_lines[:5], 1):
                actions_list.append({
                    "name": f"Instruction {idx}: {pline['text'][:45]}...",
                    "action_type": "recommended",
                    "description": pline["text"],
                    "why": f"Actionable step discussed in the tutorial at {pline['time']}.",
                    "tools_materials": [],
                    "precautions": [],
                    "timing_frequency": None,
                    "steps": [
                        {
                            "step_number": idx,
                            "what_to_do": pline["text"],
                            "why_it_matters": "Demonstrated instruction from transcript.",
                            "tools_resources": [],
                            "prerequisites_cautions": [],
                            "timestamp": pline["time"],
                            "evidence": pline["text"]
                        }
                    ]
                })

        checklist = [act["name"] for act in actions_list]

        # Key points facts / explanations / recommendations
        facts = []
        explanations = []
        recommendations = []
        for pline in parsed_lines:
            txt = pline["text"]
            t_str = f" {pline['time']}" if pline['time'] != 'unavailable' else ""
            if "warning" in txt.lower() or "caution" in txt.lower() or "prevent" in txt.lower():
                if len(explanations) < 3:
                    explanations.append(f"{txt}{t_str} (Source excerpt: '{txt[:60]}...')")
            elif "recommend" in txt.lower() or "should" in txt.lower() or "advice" in txt.lower():
                if len(recommendations) < 3:
                    recommendations.append(f"{txt}{t_str} (Source excerpt: '{txt[:60]}...')")
            else:
                if len(facts) < 3 and len(txt) > 30:
                    facts.append(f"{txt}{t_str} (Source excerpt: '{txt[:60]}...')")

        if not facts:
            facts = [f"Video titled '{title}' presented by {author}."]
        if not explanations:
            explanations = ["Detailed transcript provided covering instructional workflows."]
        if not recommendations:
            recommendations = ["Follow step-by-step instructions detailed in the transcript."]

        return {
            "overview": overview,
            "main_topics": [
                {"topic": "Core Subject", "explanation": f"The primary subject matter covered in '{title}' by {author}."},
                {"topic": "Transcript Highlights", "explanation": "Direct walkthrough and key concepts covered in the video recording."}
            ],
            "key_points": {
                "facts": facts,
                "explanations": explanations,
                "recommendations": recommendations
            },
            "actions": actions_list,
            "action_checklist": [act["name"] for act in actions_list],
            "final_summary": final_summary
        }
