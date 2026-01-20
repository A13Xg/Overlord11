from flask import Flask, jsonify, request, render_template
import requests
import random # Added for random ID generation
import string # Added for random string generation

# Initialize the Flask application
app = Flask(__name__, template_folder='templates')

# A dictionary to store the URLs for the external APIs
API_URLS = {
    'catfact': 'https://catfact.ninja/fact',
    'dogs': 'https://dog.ceo/api/breeds/image/random',
    'agify': 'https://api.agify.io',
    'genderize': 'https://api.genderize.io',
    'nationalize': 'https://api.nationalize.io',
    'pokeapi': 'https://pokeapi.co/api/v2/pokemon/',
    'jsonplaceholder': 'https://jsonplaceholder.typicode.com/users',
    'naas': 'https://naas.isalman.dev/no',
    'advice': 'https://api.adviceslip.com/advice', # Get a random advice slip
    'kanye': 'https://api.kanye.rest/', # Get a random Kanye West quote
    'spacedevs': 'https://lldev.thespacedevs.com/2.2.0/launch/upcoming/?limit=1', # Upcoming space launches
    'cataas': 'https://cataas.com/cat?json=true', # Cat as a service - cat images/GIFs
    'meowfacts': 'https://meowfacts.herokuapp.com/', # Random cat facts
    'waifu': 'https://api.waifu.pics/sfw/waifu' # Anime images
}

# A dictionary to store descriptions for each API
API_DESCRIPTIONS = {
    'catfact': 'Get a random interesting fact about cats.',
    'dogs': 'Get a random image of a dog.',
    'agify': 'Predict the age of a person based on their name.',
    'genderize': 'Predict the gender of a person based on their name.',
    'nationalize': 'Predict the nationality of a person based on their name.',
    'pokeapi': 'Access data for various Pokémon, including their stats, types, and images.',
    'jsonplaceholder': 'Get fake user data for testing and prototyping.',
    'naas': 'Get a random reason why something cannot be done (No as a Service).',
    'advice': 'Get a random piece of advice.',
    'kanye': 'Receive a random quote from Kanye West.',
    'spacedevs': 'Get information about upcoming space launches.',
    'cataas': 'Get a random cat image or GIF.',
    'meowfacts': 'Get a random interesting fact about cats (another source).',
    'waifu': 'Get a random SFW (safe for work) anime waifu image.'
}

def call_external_api(api_name):
    """
    Calls the specified external API and returns the JSON response.
    Handles API-specific parameters.
    """
    url = API_URLS[api_name]
    params = {}
    
    # Handle API-specific parameters
    if api_name in ['agify', 'genderize', 'nationalize']:
        name = request.args.get('name')
        if not name:
            return {"error": "A 'name' parameter is required for this API"}, 400
        params['name'] = name
    elif api_name == 'pokeapi':
        pokemon = request.args.get('pokemon', 'ditto').lower()
        url += pokemon
    elif api_name == 'advice':
        pass # No specific params needed
    elif api_name == 'kanye':
        pass # No specific params needed
    elif api_name == 'spacedevs':
        pass # No specific params needed
    elif api_name == 'cataas':
        pass # No specific params needed (json=true is in URL already)
    elif api_name == 'meowfacts':
        pass # No specific params needed
    elif api_name == 'waifu':
        pass # No specific params needed

    try:
        print(f"DEBUG: Making request to URL: {url} with params: {params}") # DEBUG PRINT
        request_kwargs = {}
        if params:
            request_kwargs['params'] = params
        
        # Meowfacts returns [{ "data": ["fact string"] }]
        if api_name == 'meowfacts':
            response = requests.get(url, **request_kwargs)
            response.raise_for_status()
            return response.json(), 200, response.url
        
        response = requests.get(url, **request_kwargs) # Pass params only if present
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        return response.json(), 200, response.url
    except requests.exceptions.RequestException as e:
        # Handle network-related errors
        return {"error": str(e)}, 500, url

@app.route('/')
def index():
    """
    Serves the main HTML page of the application.
    """
    api_list = []
    for key in API_URLS.keys():
        api_list.append({
            "value": key,
            "name": key.replace('_', ' ').title(),
            "description": API_DESCRIPTIONS.get(key, 'No description available.')
        })
    return render_template('index.html', api_list=api_list)

@app.route('/api/<api_name>')
def api_proxy(api_name):
    """
    A proxy endpoint that routes requests to the appropriate external API.
    """
    if api_name not in API_URLS:
        return jsonify({"error": "Invalid API name"}), 404

    data, status_code, request_url = call_external_api(api_name)
    
    response_data = {
        "data": data,
        "request_url": request_url
    }
    
    return jsonify(response_data), status_code

if __name__ == '__main__':
    # Runs the Flask application
    app.run(debug=True, port=5001)
