"""
LabAuto - MATLAB Report Generator API
Main serverless handler for Vercel Python runtime
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import io
import re
import base64
from typing import Optional

# Third-party imports
import google.generativeai as genai
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pypdf
import pdfplumber


def configure_matlab_style():
    """Configure Matplotlib to mimic MATLAB default aesthetics."""
    plt.style.use('default')
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
    plt.rcParams['font.size'] = 10
    plt.rcParams['axes.linewidth'] = 1.0
    plt.rcParams['xtick.direction'] = 'in'  # MATLAB ticks face inward
    plt.rcParams['ytick.direction'] = 'in'
    plt.rcParams['xtick.top'] = True         # Box ticks on all sides
    plt.rcParams['ytick.right'] = True
    plt.rcParams['grid.alpha'] = 0.5
    plt.rcParams['grid.linestyle'] = ':'
    plt.rcParams['figure.facecolor'] = 'white'
    plt.rcParams['axes.facecolor'] = 'white'
    # MATLAB default color cycle
    plt.rcParams['axes.prop_cycle'] = plt.cycler(
        color=['#0072BD', '#D95319', '#EDB120', '#7E2F8E', '#77AC30', '#4DBEEE', '#A2142F']
    )


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF file bytes."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return '\n'.join(text_parts)


def extract_text_from_docx(docx_bytes: bytes) -> str:
    """Extract text from DOCX file bytes."""
    doc = Document(io.BytesIO(docx_bytes))
    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)
    return '\n'.join(text_parts)


def call_gemini(question_text: str) -> dict:
    """
    Call Gemini API to generate MATLAB code, Python plotting code, and conclusion.
    Returns a dict with keys: matlab_code, python_plotting_code, conclusion
    """
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    system_prompt = """You are a MATLAB expert assistant. You will receive a lab question.
You must output a valid JSON object (no markdown code fences) containing exactly these fields:

1. "matlab_code": The complete, executable MATLAB code to solve the problem.
   - Ensure all variables are defined with example values.
   - Do NOT use input() commands; hardcode example values.
   - Include comments explaining each step.
   - The code should generate a plot/graph when applicable.

2. "python_plotting_code": Equivalent Python code using Matplotlib that generates the same graph.
   - Use numpy for numerical operations.
   - Include: import numpy as np, import matplotlib.pyplot as plt
   - End with: plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
   - Use 'buffer' as the output variable (it will be provided).
   - Add plt.grid(True) for grid lines.

3. "conclusion": A 3-4 line academic conclusion explaining:
   - What the code demonstrates
   - The behavior observed in the graph
   - Key insights from the results

Respond with ONLY the JSON object, no additional text or markdown."""

    prompt = f"""Lab Question:
{question_text}

Generate the JSON response with matlab_code, python_plotting_code, and conclusion."""

    response = model.generate_content(
        [system_prompt, prompt],
        generation_config=genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=4096,
        )
    )
    
    # Parse JSON from response
    response_text = response.text.strip()
    
    # Remove markdown code fences if present
    if response_text.startswith('```'):
        response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
        response_text = re.sub(r'\n?```$', '', response_text)
    
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        # Try to extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            result = json.loads(json_match.group())
        else:
            raise ValueError(f"Failed to parse Gemini response as JSON: {e}")
    
    return {
        'matlab_code': result.get('matlab_code', '% No code generated'),
        'python_plotting_code': result.get('python_plotting_code', ''),
        'conclusion': result.get('conclusion', 'No conclusion generated.')
    }


def generate_graph(python_code: str) -> bytes:
    """Execute Python plotting code and return PNG bytes."""
    configure_matlab_style()
    
    buffer = io.BytesIO()
    
    # Create a safe execution environment
    exec_globals = {
        'np': __import__('numpy'),
        'plt': plt,
        'buffer': buffer,
        '__builtins__': {
            'range': range,
            'len': len,
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'round': round,
            'int': int,
            'float': float,
            'str': str,
            'list': list,
            'tuple': tuple,
            'dict': dict,
            'print': print,
        }
    }
    
    try:
        # Clear any existing figures
        plt.close('all')
        
        # Execute the plotting code
        exec(python_code, exec_globals)
        
        # If buffer is empty, try saving current figure
        if buffer.tell() == 0:
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight',
                       facecolor='white', edgecolor='none')
        
        buffer.seek(0)
        return buffer.read()
    except Exception as e:
        # Generate error placeholder image
        plt.close('all')
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, f'Graph Generation Error:\n{str(e)[:100]}',
               ha='center', va='center', fontsize=12, color='red',
               transform=ax.transAxes, wrap=True)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        
        error_buffer = io.BytesIO()
        plt.savefig(error_buffer, format='png', dpi=150, bbox_inches='tight')
        error_buffer.seek(0)
        plt.close('all')
        return error_buffer.read()
    finally:
        plt.close('all')


def assemble_document(
    question: str,
    matlab_code: str,
    graph_bytes: bytes,
    conclusion: str
) -> bytes:
    """
    Load template.docx, replace placeholders, and return the assembled document.
    """
    # Get template path
    template_path = os.path.join(os.path.dirname(__file__), 'assets', 'template.docx')
    
    if not os.path.exists(template_path):
        # Create a basic document if template doesn't exist
        doc = Document()
        doc.add_heading('Lab Report', 0)
        doc.add_heading('Question', level=1)
        doc.add_paragraph(question)
        doc.add_heading('MATLAB Code', level=1)
        code_para = doc.add_paragraph()
        code_run = code_para.add_run(matlab_code)
        code_run.font.name = 'Courier New'
        code_run.font.size = Pt(9)
        doc.add_heading('Output Graph', level=1)
        doc.add_picture(io.BytesIO(graph_bytes), width=Inches(6))
        doc.add_heading('Conclusion', level=1)
        doc.add_paragraph(conclusion)
    else:
        # Load template and replace placeholders
        doc = Document(template_path)
        
        for para in doc.paragraphs:
            if '{{QUESTION}}' in para.text:
                para.text = para.text.replace('{{QUESTION}}', question)
            
            if '{{CODE}}' in para.text:
                # Clear the paragraph and add formatted code
                para.clear()
                code_run = para.add_run(matlab_code)
                code_run.font.name = 'Courier New'
                code_run.font.size = Pt(9)
            
            if '{{GRAPH}}' in para.text:
                # Clear and insert image
                para.clear()
                run = para.add_run()
                run.add_picture(io.BytesIO(graph_bytes), width=Inches(6))
            
            if '{{CONCLUSION}}' in para.text:
                para.text = para.text.replace('{{CONCLUSION}}', conclusion)
    
    # Save to buffer
    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    output_buffer.seek(0)
    return output_buffer.read()


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler."""
    
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        """Handle POST request to generate report."""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            
            question_text = data.get('question_text', '')
            file_data = data.get('file_data')  # Base64 encoded
            file_type = data.get('file_type', '')  # 'pdf' or 'docx'
            
            # Extract text from file if provided
            if file_data and not question_text:
                file_bytes = base64.b64decode(file_data)
                if file_type == 'pdf':
                    question_text = extract_text_from_pdf(file_bytes)
                elif file_type == 'docx':
                    question_text = extract_text_from_docx(file_bytes)
            
            if not question_text:
                raise ValueError("No question text provided")
            
            # Step 1: Call Gemini AI
            ai_response = call_gemini(question_text)
            
            # Step 2: Generate graph
            graph_bytes = generate_graph(ai_response['python_plotting_code'])
            
            # Step 3: Assemble document
            doc_bytes = assemble_document(
                question=question_text,
                matlab_code=ai_response['matlab_code'],
                graph_bytes=graph_bytes,
                conclusion=ai_response['conclusion']
            )
            
            # Return the document
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            self.send_header('Content-Disposition', 'attachment; filename="lab_report.docx"')
            self.send_header('Content-Length', str(len(doc_bytes)))
            self.end_headers()
            self.wfile.write(doc_bytes)
            
        except Exception as e:
            # Return error as JSON
            error_response = json.dumps({'error': str(e)})
            self.send_response(500)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(error_response.encode())
    
    def do_GET(self):
        """Health check endpoint."""
        response = json.dumps({'status': 'ok', 'service': 'LabAuto API'})
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(response.encode())
