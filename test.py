#!/usr/bin/env python3
import os

import google.generativeai as genai
from rich.console import Console
from rich.table import Table


# Load environment variables from .env file if it exists
def load_env_file():
    if os.path.exists('.env'):
        with open('.env', 'r') as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value

# Load API key from environment variables
load_env_file()
api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    print("Error: GEMINI_API_KEY not found in environment variables or .env file")
    exit(1)

# Configure the Gemini API
genai.configure(api_key=api_key)

# Create a rich console for pretty output
console = Console()

console.print("\n[bold cyan]Available Gemini Models (v1beta)[/bold cyan]")

# Create a table
table = Table(show_header=True, header_style="bold magenta")
table.add_column("Model Name", style="dim")
table.add_column("Display Name", style="cyan")
table.add_column("Description", style="green", no_wrap=False)
table.add_column("Input Token Limit", style="yellow")
table.add_column("Output Token Limit", style="yellow")
table.add_column("Temperature Range", style="yellow")

try:
    # List all available models
    models = genai.list_models()
    
    # Filter for Gemini models
    gemini_models = [model for model in models if "gemini" in model.name.lower()]
    
    # Sort models by name
    gemini_models.sort(key=lambda x: x.name)
    
    # Add each model to the table
    for model in gemini_models:
        # Extract token limits
        input_token_limit = "N/A"
        output_token_limit = "N/A"
        temp_min = "N/A"
        temp_max = "N/A"
        
        # Try to get token limits if available
        if hasattr(model, 'input_token_limit'):
            input_token_limit = str(model.input_token_limit)
        
        if hasattr(model, 'output_token_limit'):
            output_token_limit = str(model.output_token_limit)
        
        # Try to get temperature range if available
        if hasattr(model, 'temperature'):
            if hasattr(model.temperature, 'minimum'):
                temp_min = str(model.temperature.minimum)
            if hasattr(model.temperature, 'maximum'):
                temp_max = str(model.temperature.maximum)
        
        # Add row to table
        table.add_row(
            model.name,
            getattr(model, 'display_name', 'N/A'),
            getattr(model, 'description', 'No description available').replace('\n', ' '),
            input_token_limit,
            output_token_limit,
            f"{temp_min} - {temp_max}"
        )
    
    # Print the table
    console.print(table)
    
    # Print the total count
    console.print(f"\n[bold green]Found {len(gemini_models)} Gemini models[/bold green]")

except Exception as e:
    console.print(f"[bold red]Error listing models: {e}[/bold red]")

# Print raw model details for debugging
console.print("\n[bold cyan]Raw Model Details (first model only):[/bold cyan]")
if gemini_models:
    console.print(f"Model attributes for {gemini_models[0].name}:")
    for attr in dir(gemini_models[0]):
        if not attr.startswith('_'):  # Skip private attributes
            try:
                value = getattr(gemini_models[0], attr)
                if not callable(value):  # Skip methods
                    console.print(f"  {attr}: {value}")
            except Exception as e:
                console.print(f"  {attr}: [red]Error: {e}[/red]")
