"""
Visualization utilities using matplotlib, seaborn, and plotly.
Internal rendering capabilities without external APIs.
"""

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import json

# Configure plotting style
sns.set_style("whitegrid")
plt.rcParams['figure.dpi'] = 300
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.size'] = 10


def create_line_chart(data, options, output_path):
    """Create a line chart from data."""
    fig, ax = plt.subplots(figsize=(options.get('width', 10), options.get('height', 6)))
    
    # Extract data
    x_data = data.get('x', [])
    y_data = data.get('y', [])
    
    ax.plot(x_data, y_data, marker='o', linewidth=2)
    ax.set_title(options.get('title', 'Line Chart'))
    ax.set_xlabel(options.get('x_label', 'X Axis'))
    ax.set_ylabel(options.get('y_label', 'Y Axis'))
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()
    
    return str(output_path)


def create_bar_chart(data, options, output_path):
    """Create a bar chart from data."""
    fig, ax = plt.subplots(figsize=(options.get('width', 10), options.get('height', 6)))
    
    categories = data.get('categories', [])
    values = data.get('values', [])
    
    ax.bar(categories, values, color=options.get('color', 'steelblue'))
    ax.set_title(options.get('title', 'Bar Chart'))
    ax.set_xlabel(options.get('x_label', 'Categories'))
    ax.set_ylabel(options.get('y_label', 'Values'))
    ax.grid(axis='y', alpha=0.3)
    
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()
    
    return str(output_path)


def create_pie_chart(data, options, output_path):
    """Create a pie chart from data."""
    fig, ax = plt.subplots(figsize=(options.get('width', 8), options.get('height', 8)))
    
    labels = data.get('labels', [])
    values = data.get('values', [])
    
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.set_title(options.get('title', 'Pie Chart'))
    ax.axis('equal')
    
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()
    
    return str(output_path)


def create_scatter_plot(data, options, output_path):
    """Create a scatter plot from data."""
    fig, ax = plt.subplots(figsize=(options.get('width', 10), options.get('height', 6)))
    
    x_data = data.get('x', [])
    y_data = data.get('y', [])
    
    ax.scatter(x_data, y_data, alpha=0.6, s=options.get('point_size', 50))
    ax.set_title(options.get('title', 'Scatter Plot'))
    ax.set_xlabel(options.get('x_label', 'X Axis'))
    ax.set_ylabel(options.get('y_label', 'Y Axis'))
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()
    
    return str(output_path)


def create_histogram(data, options, output_path):
    """Create a histogram from data."""
    fig, ax = plt.subplots(figsize=(options.get('width', 10), options.get('height', 6)))
    
    values = data.get('values', [])
    bins = options.get('bins', 20)
    
    ax.hist(values, bins=bins, color='steelblue', alpha=0.7, edgecolor='black')
    ax.set_title(options.get('title', 'Histogram'))
    ax.set_xlabel(options.get('x_label', 'Values'))
    ax.set_ylabel(options.get('y_label', 'Frequency'))
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()
    
    return str(output_path)


def create_heatmap(data, options, output_path):
    """Create a heatmap from data."""
    fig, ax = plt.subplots(figsize=(options.get('width', 10), options.get('height', 8)))
    
    matrix = data.get('matrix', [])
    x_labels = data.get('x_labels', [])
    y_labels = data.get('y_labels', [])
    
    sns.heatmap(matrix, annot=True, fmt='.2f', cmap='coolwarm', 
                xticklabels=x_labels, yticklabels=y_labels, ax=ax)
    ax.set_title(options.get('title', 'Heatmap'))
    
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()
    
    return str(output_path)


# Visualization dispatcher
VISUALIZERS = {
    'line_chart': create_line_chart,
    'bar_chart': create_bar_chart,
    'pie_chart': create_pie_chart,
    'scatter_plot': create_scatter_plot,
    'histogram': create_histogram,
    'heatmap': create_heatmap,
}


def generate_visualization(viz_type, data, options, output_path):
    """
    Generate a visualization of the specified type.
    
    Args:
        viz_type: Type of visualization
        data: Data to visualize (dict)
        options: Visualization options (dict)
        output_path: Path to save the output file
    
    Returns:
        Path to the generated visualization file
    """
    if viz_type in VISUALIZERS:
        return VISUALIZERS[viz_type](data, options, output_path)
    else:
        raise ValueError(f"Unsupported visualization type: {viz_type}")
