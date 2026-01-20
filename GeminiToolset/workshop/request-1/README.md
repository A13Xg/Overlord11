# Public API Showcase

This project is a Flask-based web application designed to showcase various free, public APIs. It provides a modern, futuristic user interface for interacting with these APIs, displaying both parsed and raw responses, and generating cURL commands for each call. This serves as an example for developers to understand how to make API calls and integrate functionality.

## Features

### UI/UX
*   **Modern, Futuristic Dark Mode:** A sleek design with dark themes, neon accents, and a clear, readable layout.
*   **Dynamic API Selection:** A dropdown menu dynamically populated with available APIs.
*   **API Descriptions:** A brief summary of each API is displayed below the "Call API" button.
*   **Input Fields:** Relevant input fields appear dynamically for APIs that require parameters.
*   **Enhanced Visualizations:** Specific APIs (e.g., Pokémon, SpaceDevs) feature custom, detailed, and visually appealing displays for their data.

### API Interaction
*   **Proxy Backend:** A Flask backend acts as a proxy, handling requests to external APIs and preventing CORS issues.
*   **Robust Error Handling:** The application gracefully handles API errors and network issues, displaying informative messages.

### Output Display
*   **Parsed Response:** Key information from the API response is extracted and displayed in a user-friendly format.
*   **Raw API Call:** The exact cURL command used to make the API request is displayed in a code markdown block.
*   **Raw API Response:** The full, unformatted JSON response from the API is displayed in a code markdown block.

## Implemented APIs

The following public APIs are currently integrated into the showcase:

*   **Cat Fact API:** Get a random interesting fact about cats.
*   **Dogs API:** Get a random image of a dog.
*   **Agify API:** Predict the age of a person based on their name.
*   **Genderize API:** Predict the gender of a person based on their name.
*   **Nationalize API:** Predict the nationality of a person based on their name.
*   **PokeAPI:** Access data for various Pokémon, including their stats, types, and images.
*   **JSONPlaceholder API:** Get fake user data for testing and prototyping.
*   **NaaS (No as a Service):** Get a random reason why something cannot be done.
*   **Advice Slip API:** Get a random piece of advice.
*   **Kanye Rest API:** Receive a random quote from Kanye West.
*   **SpaceDevs API:** Get information about upcoming space launches (enhanced visualization).
*   **Cataas API:** Get a random cat image or GIF.
*   **MeowFacts API:** Get a random interesting fact about cats.
*   **Waifu.pics API:** Get a random SFW (safe for work) anime waifu image.

## How to Run the Application

1.  **Ensure Python is Installed:** Make sure you have Python 3.8+ installed on your system.
2.  **Navigate to the Project Directory:** Open your terminal or command prompt and navigate to the `workshop/request-1` directory within the project.
3.  **Install Dependencies:** Install the required Python packages using pip:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Start the Flask Server:** Run the `app.py` file to start the development server:
    ```bash
    python app.py
    ```
    The application will typically start on `http://127.0.0.1:5001`.
5.  **Access the Application:** Open your web browser and navigate to `http://127.0.0.1:5001`.

## Future Enhancements (APIs Requiring Keys)

Here is a list of recommended APIs that require a free API key for access. They are great candidates for extending the API showcase to demonstrate authenticated API calls.

**Weather & Environment**
*   **OpenWeatherMap:** One of the most popular weather APIs. Provides current weather, forecasts, and historical data. Requires an API key. (https://openweathermap.org/api)
*   **NASA Open APIs:** A collection of APIs providing access to NASA's vast collection of data and images, including the "Astronomy Picture of the Day" (APOD). (https://api.nasa.gov/)

**AI & Machine Learning**
*   **OpenAI API:** Access to powerful language models like GPT-3 for a wide range of text generation and understanding tasks. Has a free tier. (https://openai.com/api/)
*   **Hugging Face Inference API:** Provides access to thousands of pre-trained models for NLP, computer vision, and more. Offers a generous free tier. (https://huggingface.co/inference-api)

**Geocoding & Maps**
*   **Google Maps Platform:** A suite of APIs for maps, routing, places, and more. It has a free tier that is sufficient for most small projects. (https://developers.google.com/maps)

**News & Articles**
*   **NewsAPI.org:** Provides access to articles from thousands of news outlets and blogs. Great for creating news feeds. (https://newsapi.org/)

**Finance & Cryptocurrency**
*   **Alpha Vantage:** Real-time and historical data for stocks, forex, and cryptocurrencies. The free tier has some limitations on request frequency. (https://www.alphavantage.co/)

**Entertainment & Data**
*   **The Movie Database (TMDb):** A massive database of movies, TV shows, and actors. Excellent for building any kind of media-related application. (https://www.themoviedb.org/documentation/api)
*   **Giphy API:** The best way to integrate GIFs into your application. (https://developers.giphy.com/)
