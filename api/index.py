from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import json
import os
import io
import re
import base64

# Third-party imports
import google.generativeai as genai
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pypdf
import pdfplumber

app = Flask(__name__)
CORS(app)


def configure_matlab_style():
    """Configure Matplotlib to mimic MATLAB default aesthetics."""
    plt.style.use('default')
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Helvetica', 'Arial', 'DejaVu Sans']
    plt.rcParams['font.size'] = 10
    plt.rcParams['axes.linewidth'] = 1.0
    plt.rcParams['xtick.direction'] = 'in'
    plt.rcParams['ytick.direction'] = 'in'
    plt.rcParams['xtick.top'] = True
    plt.rcParams['ytick.right'] = True
    plt.rcParams['grid.alpha'] = 0.5
    plt.rcParams['grid.linestyle'] = ':'
    plt.rcParams['figure.facecolor'] = 'white'
    plt.rcParams['axes.facecolor'] = 'white'
    plt.rcParams['axes.prop_cycle'] = plt.cycler(
        color=['#0072BD', '#D95319', '#EDB120', '#7E2F8E', '#77AC30', '#4DBEEE', '#A2142F']
    )


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return '\n'.join(text_parts)


def extract_text_from_docx(docx_bytes: bytes) -> str:
    doc = Document(io.BytesIO(docx_bytes))
    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)
    return '\n'.join(text_parts)


def split_questions(text: str) -> list:
    """Split input text into individual questions based on numbering patterns."""
    # Try to split by common patterns: 1), 1., Q1, Question 1, etc.
    patterns = [
        r'(?=\n\s*\d+\s*[\.\)]\s)',  # 1. or 1)
        r'(?=\n\s*Q\d+[\.\:\)]?\s)',  # Q1, Q1., Q1:
        r'(?=\n\s*Question\s*\d+)',   # Question 1
    ]
    
    questions = []
    for pattern in patterns:
        parts = re.split(pattern, text, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 20]
        if len(parts) > 1:
            questions = parts
            break
    
    # If no pattern matched, return the whole text as one question
    if not questions:
        questions = [text.strip()]
    
    return questions


def call_gemini_single(question_text: str, question_num: int) -> dict:
    """Call Gemini for a single question."""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    system_prompt = """You are a MATLAB expert assistant. Solve the given lab question.

Output a valid JSON object (no markdown code fences) with these fields:

1. "matlab_code": Complete executable MATLAB code with comments. Hardcode all values, no input().

2. "python_plotting_code": Equivalent Python/Matplotlib code to generate the graph.
   - Use numpy as np, matplotlib.pyplot as plt
   - End with: plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
   - Variable 'buffer' will be provided.

3. "conclusion": 2-3 line academic conclusion about the results.

Output ONLY the JSON object. Keep code concise."""

    prompt = f"""Question {question_num}:
{question_text}

Generate the JSON response."""

    try:
        response = model.generate_content(
            [system_prompt, prompt],
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=4096,
            )
        )
        
        response_text = response.text.strip()
        
        # Remove markdown code fences if present
        if response_text.startswith('```'):
            response_text = re.sub(r'^```(?:json)?\n?', '', response_text)
            response_text = re.sub(r'\n?```$', '', response_text)
        
        # Try to parse JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise ValueError("Could not parse response")
        
        return {
            'matlab_code': result.get('matlab_code', '% Code generation failed'),
            'python_plotting_code': result.get('python_plotting_code', ''),
            'conclusion': result.get('conclusion', 'No conclusion generated.')
        }
    except Exception as e:
        return {
            'matlab_code': f'% Error generating code for this question: {str(e)[:50]}',
            'python_plotting_code': '',
            'conclusion': f'Error processing this question: {str(e)[:50]}'
        }


def generate_graph(python_code: str) -> bytes:
    """Execute Python plotting code and return PNG bytes."""
    configure_matlab_style()
    buffer = io.BytesIO()
    
    if not python_code or len(python_code.strip()) < 10:
        # Return a placeholder if no code
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, 'No graph generated', ha='center', va='center', fontsize=14)
        ax.axis('off')
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
        buffer.seek(0)
        plt.close('all')
        return buffer.read()
    
    exec_globals = {
        'np': __import__('numpy'),
        'plt': plt,
        'buffer': buffer,
        '__builtins__': {
            'range': range, 'len': len, 'abs': abs, 'min': min, 'max': max,
            'sum': sum, 'round': round, 'int': int, 'float': float,
            'str': str, 'list': list, 'tuple': tuple, 'dict': dict, 'print': print,
        }
    }
    
    try:
        plt.close('all')
        exec(python_code, exec_globals)
        
        if buffer.tell() == 0:
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight',
                       facecolor='white', edgecolor='none')
        
        buffer.seek(0)
        return buffer.read()
    except Exception as e:
        plt.close('all')
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, f'Graph Error:\n{str(e)[:80]}',
               ha='center', va='center', fontsize=10, color='red',
               transform=ax.transAxes, wrap=True)
        ax.axis('off')
        
        error_buffer = io.BytesIO()
        plt.savefig(error_buffer, format='png', dpi=150, bbox_inches='tight')
        error_buffer.seek(0)
        plt.close('all')
        return error_buffer.read()
    finally:
        plt.close('all')


def assemble_multi_question_document(questions_data: list) -> bytes:
    """
    Assemble a document with multiple questions, each with code, graph, and conclusion.
    questions_data: list of dicts with keys: question, matlab_code, graph_bytes, conclusion, question_num
    """
    doc = Document()
    
    # Add title
    title = doc.add_heading('Lab Report', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    for item in questions_data:
        # Question heading
        q_heading = doc.add_heading(f"Question {item['question_num']}", level=1)
        
        # Question text
        doc.add_paragraph(item['question'][:500] + ('...' if len(item['question']) > 500 else ''))
        
        # MATLAB Code section
        doc.add_heading('MATLAB Code', level=2)
        code_para = doc.add_paragraph()
        code_run = code_para.add_run(item['matlab_code'])
        code_run.font.name = 'Courier New'
        code_run.font.size = Pt(9)
        
        # Graph section
        doc.add_heading('Output Graph', level=2)
        if item['graph_bytes']:
            doc.add_picture(io.BytesIO(item['graph_bytes']), width=Inches(5.5))
        
        # Conclusion section
        doc.add_heading('Conclusion', level=2)
        doc.add_paragraph(item['conclusion'])
        
        # Add page break between questions (except for last)
        if item != questions_data[-1]:
            doc.add_page_break()
    
    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    output_buffer.seek(0)
    return output_buffer.read()


@app.route('/', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'LabAuto API', 'version': '2.0', 'multi_question': True})


@app.route('/generate', methods=['POST', 'OPTIONS'])
def generate():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        
        question_text = data.get('question_text', '')
        file_data = data.get('file_data')
        file_type = data.get('file_type', '')
        
        # Extract text from file if provided
        if file_data and not question_text:
            file_bytes = base64.b64decode(file_data)
            if file_type == 'pdf':
                question_text = extract_text_from_pdf(file_bytes)
            elif file_type == 'docx':
                question_text = extract_text_from_docx(file_bytes)
        
        if not question_text:
            return jsonify({'error': 'No question text provided'}), 400
        
        # Split into individual questions
        questions = split_questions(question_text)
        
        # Process each question
        questions_data = []
        for i, q in enumerate(questions, 1):
            # Call Gemini for this question
            ai_response = call_gemini_single(q, i)
            
            # Generate graph
            graph_bytes = generate_graph(ai_response['python_plotting_code'])
            
            questions_data.append({
                'question_num': i,
                'question': q,
                'matlab_code': ai_response['matlab_code'],
                'graph_bytes': graph_bytes,
                'conclusion': ai_response['conclusion']
            })
        
        # Assemble the document with all questions
        doc_bytes = assemble_multi_question_document(questions_data)
        
        return send_file(
            io.BytesIO(doc_bytes),
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name='lab_report.docx'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
