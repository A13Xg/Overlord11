import re

def count_words(text):
    """Count words in text."""
    return len(text.split())

def count_characters(text, include_spaces=True):
    """Count characters in text."""
    if include_spaces:
        return len(text)
    return len(text.replace(" ", ""))

def count_sentences(text):
    """Count sentences in text using basic punctuation."""
    sentences = re.split(r'[.!?]+', text)
    return len([s for s in sentences if s.strip()])

def count_paragraphs(text):
    """Count paragraphs in text."""
    paragraphs = text.split('\n\n')
    return len([p for p in paragraphs if p.strip()])

def estimate_reading_time(word_count, words_per_minute=200):
    """Estimate reading time in minutes."""
    return round(word_count / words_per_minute, 1)

def calculate_avg_sentence_length(text):
    """Calculate average words per sentence."""
    words = count_words(text)
    sentences = count_sentences(text)
    if sentences == 0:
        return 0
    return round(words / sentences, 1)

def validate_length_compliance(actual_length, target_length, tolerance=0.1):
    """
    Check if actual length is within tolerance of target length.
    
    Args:
        actual_length: Actual word count
        target_length: Target word count
        tolerance: Acceptable deviation (default 10%)
    
    Returns:
        dict with compliance status and details
    """
    min_length = target_length * (1 - tolerance)
    max_length = target_length * (1 + tolerance)
    
    is_compliant = min_length <= actual_length <= max_length
    deviation = ((actual_length - target_length) / target_length) * 100
    
    return {
        "compliant": is_compliant,
        "actual": actual_length,
        "target": target_length,
        "min_acceptable": int(min_length),
        "max_acceptable": int(max_length),
        "deviation_percent": round(deviation, 1)
    }

def detect_style_markers(text):
    """
    Detect basic style markers in text.
    
    Returns:
        dict with detected style characteristics
    """
    contractions = len(re.findall(r"\b\w+'\w+\b", text))
    exclamations = text.count('!')
    questions = text.count('?')
    passive_voice = len(re.findall(r'\b(is|are|was|were|be|been|being)\s+\w+ed\b', text, re.IGNORECASE))
    
    # Simple formality check
    informal_words = ['gonna', 'wanna', 'gotta', 'kinda', 'sorta', 'yeah', 'ok', 'okay']
    informal_count = sum(text.lower().count(word) for word in informal_words)
    
    return {
        "contractions": contractions,
        "exclamation_marks": exclamations,
        "questions": questions,
        "passive_voice_instances": passive_voice,
        "informal_markers": informal_count,
        "formality_indicator": "formal" if (contractions + informal_count) < 3 else "informal"
    }
