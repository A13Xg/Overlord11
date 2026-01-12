"""
Document rendering utilities for PDF, HTML, and other formats.
Uses reportlab, weasyprint, and template engines.
"""

from pathlib import Path
import json
from datetime import datetime


def render_html_document(content, options):
    """
    Render content as HTML document.
    
    Args:
        content: The content to render (can be HTML or markdown)
        options: Rendering options (title, style, etc.)
    
    Returns:
        HTML string
    """
    title = options.get('title', 'Document')
    author = options.get('author', '')
    date = options.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    template = options.get('template', 'professional')
    
    # Professional template
    if template == 'professional':
        style = """
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 900px;
                margin: 40px auto;
                padding: 20px;
                line-height: 1.6;
                color: #333;
            }
            h1 {
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
            }
            h2 {
                color: #34495e;
                margin-top: 30px;
                border-bottom: 1px solid #bdc3c7;
                padding-bottom: 5px;
            }
            h3 {
                color: #7f8c8d;
            }
            .metadata {
                color: #7f8c8d;
                font-size: 0.9em;
                margin-bottom: 30px;
                padding: 10px;
                background: #ecf0f1;
                border-radius: 5px;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }
            th, td {
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #ddd;
            }
            th {
                background-color: #3498db;
                color: white;
            }
            .chart-container {
                margin: 30px 0;
                text-align: center;
            }
        </style>
        """
    else:
        # Minimal template
        style = """
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 20px auto;
                padding: 20px;
                line-height: 1.5;
            }
            h1 { margin-bottom: 10px; }
            .metadata { color: #666; font-size: 0.9em; margin-bottom: 20px; }
        </style>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        {style}
    </head>
    <body>
        <h1>{title}</h1>
        <div class="metadata">
            {f'<strong>Author:</strong> {author}<br>' if author else ''}
            <strong>Date:</strong> {date}
        </div>
        {content}
    </body>
    </html>
    """
    
    return html


def render_markdown_to_html(markdown_content, options):
    """
    Convert markdown to HTML with styling.
    
    Args:
        markdown_content: Markdown text
        options: Rendering options
    
    Returns:
        HTML string
    """
    try:
        import markdown2
        html_content = markdown2.markdown(markdown_content, extras=['tables', 'fenced-code-blocks'])
    except ImportError:
        # Fallback: simple conversion
        html_content = markdown_content.replace('\n\n', '</p><p>').replace('\n', '<br>')
        html_content = f'<p>{html_content}</p>'
    
    return render_html_document(html_content, options)


def html_to_pdf(html_content, output_path):
    """
    Convert HTML to PDF using available libraries.
    
    Args:
        html_content: HTML string
        output_path: Path to save PDF
    
    Returns:
        Path to generated PDF
    """
    try:
        # Try weasyprint first (best quality)
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(output_path)
        return str(output_path)
    except ImportError:
        pass
    
    try:
        # Try pdfkit (requires wkhtmltopdf)
        import pdfkit
        pdfkit.from_string(html_content, output_path)
        return str(output_path)
    except ImportError:
        pass
    
    # Fallback: use reportlab for basic PDF
    return render_basic_pdf(html_content, output_path)


def render_basic_pdf(content, output_path):
    """
    Render basic PDF using reportlab.
    
    Args:
        content: Text content
        output_path: Path to save PDF
    
    Returns:
        Path to generated PDF
    """
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        
        doc = SimpleDocTemplate(str(output_path), pagesize=letter)
        styles = getSampleStyleSheet()
        story = []
        
        # Simple text rendering
        paragraphs = content.split('\n\n')
        for para in paragraphs:
            if para.strip():
                story.append(Paragraph(para, styles['Normal']))
                story.append(Spacer(1, 0.2 * inch))
        
        doc.build(story)
        return str(output_path)
    except Exception as e:
        # Last resort: save as text file
        with open(output_path.replace('.pdf', '.txt'), 'w') as f:
            f.write(content)
        return str(output_path.replace('.pdf', '.txt'))


def create_csv_export(data, output_path, options=None):
    """
    Export data to CSV format.
    
    Args:
        data: List of dicts or 2D array
        output_path: Path to save CSV
        options: Export options (delimiter, header, etc.)
    
    Returns:
        Path to generated CSV file
    """
    import csv
    
    options = options or {}
    delimiter = options.get('delimiter', ',')
    include_header = options.get('include_header', True)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            # List of dictionaries
            fieldnames = data[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
            
            if include_header:
                writer.writeheader()
            writer.writerows(data)
        else:
            # 2D array
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerows(data)
    
    return str(output_path)


def create_json_export(data, output_path, options=None):
    """
    Export data to JSON format.
    
    Args:
        data: Data to export
        output_path: Path to save JSON
        options: Export options (indent, etc.)
    
    Returns:
        Path to generated JSON file
    """
    options = options or {}
    indent = options.get('indent', 2)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    
    return str(output_path)
