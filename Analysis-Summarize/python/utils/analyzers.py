"""
Data analysis utilities for text and numerical analysis.
"""

import re
from collections import Counter
from datetime import datetime
import statistics


def extract_keywords(text, top_n=10):
    """
    Extract top keywords from text.
    
    Args:
        text: Input text
        top_n: Number of top keywords to return
    
    Returns:
        List of (word, count) tuples
    """
    # Simple keyword extraction
    words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
    
    # Common stop words to exclude
    stop_words = {
        'this', 'that', 'with', 'from', 'have', 'been', 'were', 'their',
        'there', 'would', 'could', 'should', 'about', 'which', 'these',
        'those', 'will', 'when', 'where', 'what', 'who', 'how'
    }
    
    filtered_words = [w for w in words if w not in stop_words]
    word_counts = Counter(filtered_words)
    
    return word_counts.most_common(top_n)


def extract_entities(text):
    """
    Extract basic entities from text (dates, numbers, emails, URLs).
    
    Args:
        text: Input text
    
    Returns:
        Dict of entity types and their values
    """
    entities = {
        'dates': [],
        'numbers': [],
        'emails': [],
        'urls': [],
        'percentages': []
    }
    
    # Date patterns (simple)
    date_patterns = [
        r'\d{4}-\d{2}-\d{2}',
        r'\d{1,2}/\d{1,2}/\d{4}',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b'
    ]
    for pattern in date_patterns:
        entities['dates'].extend(re.findall(pattern, text, re.IGNORECASE))
    
    # Numbers with context
    entities['numbers'] = re.findall(r'\$?\d+(?:,\d{3})*(?:\.\d+)?[KMB]?', text)
    
    # Percentages
    entities['percentages'] = re.findall(r'\d+(?:\.\d+)?%', text)
    
    # Emails
    entities['emails'] = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    
    # URLs
    entities['urls'] = re.findall(r'https?://[^\s]+', text)
    
    return entities


def calculate_statistics(numbers):
    """
    Calculate basic statistics for a list of numbers.
    
    Args:
        numbers: List of numerical values
    
    Returns:
        Dict of statistical measures
    """
    if not numbers:
        return None
    
    stats = {
        'count': len(numbers),
        'sum': sum(numbers),
        'mean': statistics.mean(numbers),
        'median': statistics.median(numbers),
        'min': min(numbers),
        'max': max(numbers),
    }
    
    if len(numbers) > 1:
        stats['stdev'] = statistics.stdev(numbers)
        stats['variance'] = statistics.variance(numbers)
    
    return stats


def detect_sentiment(text):
    """
    Basic sentiment analysis.
    
    Args:
        text: Input text
    
    Returns:
        Dict with sentiment score and label
    """
    # Simple word-based sentiment (expand with actual sentiment library)
    positive_words = {
        'good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic',
        'positive', 'success', 'successful', 'happy', 'pleased', 'improved',
        'growth', 'increase', 'gain', 'profit', 'benefit', 'advantage'
    }
    
    negative_words = {
        'bad', 'poor', 'terrible', 'awful', 'horrible', 'negative',
        'failure', 'failed', 'problem', 'issue', 'decline', 'decrease',
        'loss', 'concern', 'risk', 'challenge', 'difficulty'
    }
    
    words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
    
    positive_count = sum(1 for w in words if w in positive_words)
    negative_count = sum(1 for w in words if w in negative_words)
    
    total = positive_count + negative_count
    if total == 0:
        sentiment_score = 0
        sentiment_label = 'neutral'
    else:
        sentiment_score = (positive_count - negative_count) / total
        if sentiment_score > 0.2:
            sentiment_label = 'positive'
        elif sentiment_score < -0.2:
            sentiment_label = 'negative'
        else:
            sentiment_label = 'neutral'
    
    return {
        'score': round(sentiment_score, 2),
        'label': sentiment_label,
        'positive_words': positive_count,
        'negative_words': negative_count
    }


def summarize_text(text, num_sentences=3):
    """
    Create a simple extractive summary.
    
    Args:
        text: Input text
        num_sentences: Number of sentences to include
    
    Returns:
        Summary string
    """
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) <= num_sentences:
        return text
    
    # Simple scoring: prefer sentences with more keywords
    keywords = set([w for w, _ in extract_keywords(text, top_n=20)])
    
    scored_sentences = []
    for sent in sentences:
        words = set(re.findall(r'\b[a-zA-Z]{4,}\b', sent.lower()))
        score = len(words & keywords)
        scored_sentences.append((score, sent))
    
    # Sort by score and take top sentences
    scored_sentences.sort(reverse=True)
    top_sentences = [sent for _, sent in scored_sentences[:num_sentences]]
    
    # Return in original order
    summary_sentences = []
    for sent in sentences:
        if sent in top_sentences:
            summary_sentences.append(sent)
    
    return '. '.join(summary_sentences) + '.'


def compare_datasets(data1, data2, labels=None):
    """
    Compare two numerical datasets.
    
    Args:
        data1: First dataset (list of numbers)
        data2: Second dataset (list of numbers)
        labels: Optional labels for the datasets
    
    Returns:
        Dict with comparison results
    """
    if not labels:
        labels = ['Dataset 1', 'Dataset 2']
    
    stats1 = calculate_statistics(data1)
    stats2 = calculate_statistics(data2)
    
    comparison = {
        labels[0]: stats1,
        labels[1]: stats2,
        'differences': {
            'mean_diff': stats2['mean'] - stats1['mean'],
            'median_diff': stats2['median'] - stats1['median'],
            'mean_percent_change': ((stats2['mean'] - stats1['mean']) / stats1['mean'] * 100) if stats1['mean'] != 0 else None
        }
    }
    
    return comparison
