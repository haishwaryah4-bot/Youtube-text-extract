import os
import unicodedata
from typing import Dict, Any, List
from fpdf import FPDF

class YouTubeReportPDF(FPDF):
    def __init__(self, doc_title: str = "YouTube Video Intelligence Report"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.doc_title = doc_title
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(18, 18, 18)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(100, 116, 139) # Slate 500
            self.cell(0, 6, "YouTube Video Intelligence - Summary & Action Breakdown", border=0, align="L")
            self.ln(7)
            self.set_draw_color(226, 232, 240) # Slate 200
            self.set_line_width(0.3)
            self.line(18, 15, self.w - 18, 15)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(226, 232, 240)
        self.set_line_width(0.3)
        self.line(18, self.h - 15, self.w - 18, self.h - 15)
        
        self.set_font("Helvetica", "", 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 10, f"Grounded in Video Transcript  |  Page {self.page_no()}/{{nb}}", align="C")

    def chapter_title(self, label: str):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(30, 41, 59) # Slate 800
        self.ln(3)
        self.cell(0, 8, self.clean_text(label), border=0, align="L")
        self.ln(6)

    def clean_text(self, text: str) -> str:
        if not text:
            return ""
        # Standardize quotes, dashes, bullets, and arrows
        replacements = {
            "’": "'", "‘": "'", "“": '"', "”": '"',
            "—": "-", "–": "-", "…": "...", "•": "-",
            "→": "->", "←": "<-", "⇒": "=>", "✔": "[v]", "✓": "[v]",
            "\u200b": "", "\xa0": " "
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        # Normalize and filter out non-latin-1 characters
        normalized = unicodedata.normalize('NFKD', text)
        return normalized.encode("latin-1", "replace").decode("latin-1").replace("?", " ")


class PDFReportGenerator:
    @staticmethod
    def generate_pdf(data: Dict[str, Any], output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        pdf = YouTubeReportPDF(doc_title=data.get("title", "Video Intelligence Report"))
        pdf.alias_nb_pages()
        pdf.add_page()

        # Document Header Banner
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(37, 99, 235) # Royal Blue
        pdf.cell(0, 5, "YOUTUBE VIDEO INTELLIGENCE & ACTION PLAN", ln=True)

        # Video Title
        title_text = pdf.clean_text(data.get("title", "Video Intelligence Report"))
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(15, 23, 42) # Slate 900
        pdf.multi_cell(0, 7.5, title_text)
        pdf.ln(2)

        # Metadata Row
        author = pdf.clean_text(data.get("author", "Unknown Creator"))
        url = pdf.clean_text(data.get("url", ""))
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.write(5, f"Creator: {author}   |   URL: ")
        pdf.set_text_color(37, 99, 235)
        pdf.write(5, url, link=url)
        pdf.ln(8)

        # Divider line
        pdf.set_draw_color(37, 99, 235)
        pdf.set_line_width(0.8)
        pdf.line(18, pdf.get_y(), pdf.w - 18, pdf.get_y())
        pdf.ln(5)

        # Downstream processing warning banner if error exists
        error_msg = data.get("error")
        if error_msg:
            pdf.set_fill_color(254, 242, 242) # Red 50
            pdf.set_draw_color(252, 165, 165) # Red 300
            pdf.set_line_width(0.4)
            start_y = pdf.get_y()
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(185, 28, 28) # Red 700
            
            pdf.set_x(22)
            # We want to display label and error clearly
            clean_err = pdf.clean_text(f"Processing Warning: {error_msg}")
            pdf.multi_cell(pdf.w - 44, 5.5, clean_err, fill=True, border=1)
            
            # Left red highlight bar
            pdf.set_draw_color(220, 38, 38) # Red 600
            pdf.set_line_width(1.5)
            pdf.line(22, start_y, 22, pdf.get_y())
            pdf.ln(4)

        # Section A: Video Overview
        pdf.chapter_title("A. Video Overview")
        overview_text = pdf.clean_text(data.get("overview", "No overview provided."))
        
        # Draw Callout Box for Overview
        pdf.set_fill_color(248, 250, 252) # Slate 50
        pdf.set_draw_color(203, 213, 225) # Slate 300
        pdf.set_line_width(0.4)
        
        start_y = pdf.get_y()
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(51, 65, 85)
        
        # Calculate height needed
        pdf.set_x(22)
        pdf.multi_cell(pdf.w - 44, 5.5, overview_text, fill=True, border=1)
        # Left blue highlight bar
        pdf.set_draw_color(37, 99, 235)
        pdf.set_line_width(1.5)
        pdf.line(22, start_y, 22, pdf.get_y())
        pdf.ln(4)

        # Section B: Main Topics
        main_topics = data.get("main_topics", [])
        if main_topics:
            pdf.chapter_title("B. Main Topics & Key Concepts")
            for item in main_topics:
                t_name = pdf.clean_text(item.get("topic", ""))
                t_exp = pdf.clean_text(item.get("explanation", ""))
                
                pdf.set_font("Helvetica", "B", 9.5)
                pdf.set_text_color(37, 99, 235)
                pdf.write(5.5, f"- {t_name}: ")
                
                pdf.set_font("Helvetica", "", 9.5)
                pdf.set_text_color(51, 65, 85)
                pdf.write(5.5, f"{t_exp}\n")
            pdf.ln(4)

        # Section C: Key Points
        key_points = data.get("key_points", {})
        facts = key_points.get("facts", [])
        explanations = key_points.get("explanations", [])
        recommendations = key_points.get("recommendations", [])

        if facts or explanations or recommendations:
            pdf.chapter_title("C. Key Points & Insights")
            
            if facts:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(15, 23, 42)
                pdf.cell(0, 5, "Important Facts:", ln=True)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(51, 65, 85)
                for f in facts:
                    pdf.set_x(22)
                    pdf.multi_cell(0, 5, f"- {pdf.clean_text(f)}")
                pdf.ln(2)

            if explanations:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(15, 23, 42)
                pdf.cell(0, 5, "Important Explanations:", ln=True)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(51, 65, 85)
                for e in explanations:
                    pdf.set_x(22)
                    pdf.multi_cell(0, 5, f"- {pdf.clean_text(e)}")
                pdf.ln(2)

            if recommendations:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(15, 23, 42)
                pdf.cell(0, 5, "Important Recommendations:", ln=True)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(51, 65, 85)
                for r in recommendations:
                    pdf.set_x(22)
                    pdf.multi_cell(0, 5, f"- {pdf.clean_text(r)}")
                pdf.ln(4)

        # Section D: Actions in the Video
        actions = data.get("actions", [])
        if actions:
            pdf.chapter_title("D. Actions in the Video (Step-by-Step Breakdown)")
            
            for idx, act in enumerate(actions, 1):
                act_name = pdf.clean_text(act.get("name", f"Action {idx}"))
                act_type = act.get("action_type", "recommended").lower()
                
                is_demo = act_type == "demonstrated"
                type_tag = "[DEMONSTRATED IN VIDEO]" if is_demo else "[RECOMMENDED / INSTRUCTED]"
                
                # Check page break
                if pdf.get_y() > 230:
                    pdf.add_page()

                # Action Header Card
                pdf.set_font("Helvetica", "B", 10.5)
                pdf.set_text_color(15, 23, 42)
                pdf.cell(0, 6, f"Action {idx}: {act_name}", ln=False)
                
                # Tag color
                if is_demo:
                    pdf.set_text_color(22, 163, 74) # Green
                else:
                    pdf.set_text_color(217, 119, 6) # Amber
                
                pdf.set_font("Helvetica", "B", 8)
                pdf.cell(0, 6, f"   {type_tag}", ln=True, align="R")
                
                # Description & Purpose
                desc = pdf.clean_text(act.get("description", ""))
                why = pdf.clean_text(act.get("why", ""))
                
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(51, 65, 85)
                if desc:
                    pdf.set_x(22)
                    pdf.multi_cell(0, 4.8, f"What to do: {desc}")
                if why:
                    pdf.set_x(22)
                    pdf.multi_cell(0, 4.8, f"Why performed: {why}")

                # Steps
                steps = act.get("steps", [])
                if steps:
                    pdf.set_x(22)
                    pdf.set_font("Helvetica", "B", 9)
                    pdf.set_text_color(30, 41, 59)
                    pdf.cell(0, 5, "Step-by-Step Instructions:", ln=True)
                    for step_idx, step in enumerate(steps, 1):
                        pdf.set_x(26)
                        if isinstance(step, dict):
                            step_num = step.get("step_number", step_idx)
                            what = pdf.clean_text(step.get("what_to_do", ""))
                            why = pdf.clean_text(step.get("why_it_matters", ""))
                            stools = step.get("tools_resources", [])
                            scautions = step.get("prerequisites_cautions", [])
                            ts = pdf.clean_text(step.get("timestamp", ""))
                            ts_str = f" {ts}" if ts and ts != "unavailable" else ""
                            evidence = pdf.clean_text(step.get("evidence", ""))

                            # Draw step title and timestamp
                            pdf.set_font("Helvetica", "B", 9)
                            pdf.set_text_color(15, 23, 42)
                            pdf.cell(0, 5, f"{step_num}. {what}{ts_str}", ln=True)
                            
                            # Draw step details
                            pdf.set_font("Helvetica", "", 8.5)
                            pdf.set_text_color(71, 85, 105)
                            if why:
                                pdf.set_x(30)
                                pdf.multi_cell(0, 4.2, f"Why it matters: {why}")
                            if stools:
                                pdf.set_x(30)
                                pdf.multi_cell(0, 4.2, f"Tools/Resources: {', '.join(stools) if isinstance(stools, list) else str(stools)}")
                            if scautions:
                                pdf.set_x(30)
                                pdf.multi_cell(0, 4.2, f"Prerequisites/Cautions: {', '.join(scautions) if isinstance(scautions, list) else str(scautions)}")
                            if evidence:
                                pdf.set_x(30)
                                pdf.set_font("Helvetica", "I", 8)
                                pdf.set_text_color(100, 116, 139)
                                pdf.multi_cell(0, 4.0, f"Source excerpt: \"{evidence}\"")
                                pdf.set_font("Helvetica", "", 8.5)
                                pdf.set_text_color(71, 85, 105)
                            pdf.ln(1)
                        else:
                            pdf.set_font("Helvetica", "", 9)
                            pdf.set_text_color(51, 65, 85)
                            pdf.multi_cell(0, 4.8, f"{step_idx}. {pdf.clean_text(step)}")

                # Extra details
                tools = act.get("tools_materials", [])
                precautions = act.get("precautions", [])
                timing = act.get("timing_frequency", "")

                if tools:
                    tools_str = ", ".join(tools) if isinstance(tools, list) else str(tools)
                    pdf.set_x(22)
                    pdf.set_font("Helvetica", "I", 8.5)
                    pdf.set_text_color(13, 148, 136) # Teal
                    pdf.multi_cell(0, 4.5, f"- Tools/Materials: {pdf.clean_text(tools_str)}")

                if precautions:
                    prec_str = ", ".join(precautions) if isinstance(precautions, list) else str(precautions)
                    pdf.set_x(22)
                    pdf.set_font("Helvetica", "I", 8.5)
                    pdf.set_text_color(225, 29, 72) # Rose/Red
                    pdf.multi_cell(0, 4.5, f"- Precautions: {pdf.clean_text(prec_str)}")

                if timing:
                    pdf.set_x(22)
                    pdf.set_font("Helvetica", "I", 8.5)
                    pdf.set_text_color(100, 116, 139)
                    pdf.multi_cell(0, 4.5, f"- Timing/Frequency: {pdf.clean_text(str(timing))}")

                pdf.ln(3)
                pdf.set_draw_color(241, 245, 249)
                pdf.set_line_width(0.3)
                pdf.line(18, pdf.get_y(), pdf.w - 18, pdf.get_y())
                pdf.ln(2)

        # Section E: Action Checklist
        checklist = data.get("action_checklist", [])
        if checklist:
            if pdf.get_y() > 230:
                pdf.add_page()
            pdf.chapter_title("E. Action Checklist")
            
            for item in checklist:
                clean_item = pdf.clean_text(item)
                pdf.set_x(20)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(100, 116, 139)
                pdf.cell(8, 5, "[  ]", ln=False)
                pdf.set_font("Helvetica", "", 9.5)
                pdf.set_text_color(30, 41, 59)
                pdf.multi_cell(0, 5, clean_item)
                pdf.ln(1)
            pdf.ln(4)

        # Section F: Final Summary
        final_summary = data.get("final_summary", "")
        if final_summary:
            if pdf.get_y() > 230:
                pdf.add_page()
            pdf.chapter_title("F. Final Summary")
            
            clean_sum = pdf.clean_text(final_summary)
            pdf.set_fill_color(240, 253, 244) # Light emerald
            pdf.set_draw_color(187, 247, 208)
            pdf.set_line_width(0.4)
            start_y = pdf.get_y()
            
            pdf.set_x(22)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(20, 83, 45) # Dark emerald
            pdf.multi_cell(pdf.w - 44, 5.5, clean_sum, fill=True, border=1)
            
            pdf.set_draw_color(22, 163, 74)
            pdf.set_line_width(1.5)
            pdf.line(22, start_y, 22, pdf.get_y())

        pdf.output(output_path)
        return output_path
