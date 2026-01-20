document.addEventListener('DOMContentLoaded', () => {
    // UI elements
    const UI = {
        apiSelect: document.getElementById('api-select'),
        nameInput: document.getElementById('name-input'),
        nameParam: document.getElementById('name-param'),
        pokemonInput: document.getElementById('pokemon-input'),
        pokemonParam: document.getElementById('pokemon-param'),
        callApiBtn: document.getElementById('call-api-btn'),
        parsedDisplay: document.getElementById('parsed-display'),
        rawCallDisplay: document.getElementById('raw-call-display'),
        rawResponseDisplay: document.getElementById('raw-response-display'),
        apiDescriptionDiv: document.getElementById('api-description'),
    };

    const apiData = JSON.parse(document.getElementById('api-data-json').textContent);

    const updateApiDescription = () => {
        const selectedApi = UI.apiSelect.value;
        const description = apiData.find(api => api.value === selectedApi)?.description || 'No description available.';
        UI.apiDescriptionDiv.textContent = description;
    };

    // Show the correct input field based on API selection
    const showInput = () => {
        const selectedApi = UI.apiSelect.value;
        // Hide all specific input fields first
        UI.nameInput.style.display = 'none';
        UI.pokemonInput.style.display = 'none';

        // Show relevant input field
        if (['agify', 'genderize', 'nationalize'].includes(selectedApi)) {
            UI.nameInput.style.display = 'block';
        } else if (selectedApi === 'pokeapi') {
            UI.pokemonInput.style.display = 'block';
        }
        updateApiDescription(); // Update description when input changes
    };

    // Create a user-friendly parsed response
    const createParsedResponse = (api, data) => {
        if (!data) return 'No data received.';
        let html = '';
        switch(api) {
            case 'dogs':
                return `<img src="${data.message}" alt="Random Dog">`;
            case 'catfact':
                return `<strong>Fact:</strong> ${data.fact}`;
            case 'agify':
                return `<strong>Name:</strong> ${data.name}<br><strong>Predicted Age:</strong> ${data.age}`;
            case 'genderize':
                return `<strong>Name:</strong> ${data.name}<br><strong>Predicted Gender:</strong> ${data.gender}`;
            case 'nationalize':
                const countries = data.country.map(c => `${c.country_id} (${(c.probability * 100).toFixed(1)}%)`).join(', ');
                return `<strong>Name:</strong> ${data.name}<br><strong>Predicted Nationalities:</strong> ${countries}`;
            case 'pokeapi':
                const stats = data.stats.map(s => `
                    <div class="stat-row">
                        <span class="stat-name">${s.stat.name.replace('-', ' ')}</span>
                        <div class="stat-bar-container">
                            <div class="stat-bar" style="width: ${s.base_stat / 2.55}%"></div>
                        </div>
                        <span class="stat-value">${s.base_stat}</span>
                    </div>
                `).join('');
                const abilities = data.abilities.map(a => a.ability.name).join(', ');
                const types = data.types.map(t => `<span class="type-badge type-${t.type.name}">${t.type.name}</span>`).join(' ');
                return `
                    <div class="pokemon-container">
                        <div class="pokemon-header">
                            <h3 class="pokemon-name">${data.name.toUpperCase()}</h3>
                            <span class="pokemon-id">#${data.id.toString().padStart(3, '0')}</span>
                        </div>
                        <div class="pokemon-body">
                            <div class="pokemon-image">
                                <img src="${data.sprites.other['official-artwork'].front_default}" alt="${data.name}">
                            </div>
                            <div class="pokemon-info">
                                <div class="info-row"><strong>Types:</strong> ${types}</div>
                                <div class="info-row"><strong>Abilities:</strong> ${abilities}</div>
                                <div class="info-row"><strong>Height:</strong> ${data.height / 10} m</div>
                                <div class="info-row"><strong>Weight:</strong> ${data.weight / 10} kg</div>
                            </div>
                        </div>
                        <div class="pokemon-stats">
                            <h4>Base Stats</h4>
                            ${stats}
                        </div>
                    </div>
                `;
            case 'naas':
                return `<strong>Sample Error:</strong> ${data.reason}`;
            case 'advice':
                return `<strong>Advice:</strong> ${data.slip.advice}`;
            case 'kanye':
                return `<strong>Kanye Quote:</strong> "${data.quote}"`;
            case 'spacedevs':
                if (data && data.name) {
                    return `
                        <div class="launch-card">
                            <h3>${data.name}</h3>
                            <p><strong>Mission:</strong> ${data.mission?.name || 'N/A'}</p>
                            <p><strong>Provider:</strong> ${data.launch_service_provider.name}</p>
                            <p><strong>Status:</strong> ${data.status.name}</p>
                            <p><strong>Window Start:</strong> ${new Date(data.window_start).toLocaleString()}</p>
                            <p><strong>Window End:</strong> ${new Date(data.window_end).toLocaleString()}</p>
                            ${data.image ? `<img src="${data.image}" alt="Launch Image" style="max-width: 100%;">` : ''}
                            ${data.webcast_live ? `<p><a href="${data.webcast_live}" target="_blank">Watch Live Webcast</a></p>` : ''}
                        </div>
                    `;
                }
                return `<strong>SpaceDevs API Data:</strong> <pre>${JSON.stringify(data, null, 2)}</pre>`;
            case 'cataas':
                return `<img src="${data.url}" alt="Cat Image" style="max-width: 100%;">`;
            case 'meowfacts':
                // Meowfacts returns {"data": ["fact string"]}
                return `<strong>MeowFact:</strong> ${data.data && data.data[0] ? data.data[0] : 'No fact available.'}`;
            case 'waifu':
                return `<img src="${data.url}" alt="Waifu Image" style="max-width: 100%;">`;
            default:
                return `<pre>${JSON.stringify(data, null, 2)}</pre>`;
        }
    };

    // Main function to call the API
    const callApi = async () => {
        const selectedApi = UI.apiSelect.value;
        let url = `/api/${selectedApi}`;
        const params = new URLSearchParams();

        // Clear previous results and show loading
        UI.parsedDisplay.innerHTML = 'Loading...';
        UI.rawCallDisplay.textContent = 'Loading...';
        UI.rawResponseDisplay.textContent = 'Loading...';

        // Handle parameters
        if (['agify', 'genderize', 'nationalize'].includes(selectedApi)) {
            const name = UI.nameParam.value;
            if (!name) { 
                UI.parsedDisplay.innerHTML = '<span class="error">Please enter a name.</span>';
                return;
            }
            params.append('name', name);
        } else if (selectedApi === 'pokeapi') {
            const pokemon = UI.pokemonParam.value;
            if (!pokemon) {
                UI.parsedDisplay.innerHTML = '<span class="error">Please enter a Pokémon name or ID.</span>';
                return;
            }
            params.append('pokemon', pokemon);
        }
        
        const queryString = params.toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;

        try {
            const response = await fetch(fullUrl);
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            
            // Construct cURL command
            const curlCommand = `curl -X GET "${result.request_url}"`;

            // Populate the display areas
            UI.rawCallDisplay.textContent = `\`\`\`bash\n${curlCommand}\n\`\`\``;
            UI.rawResponseDisplay.textContent = JSON.stringify(result.data, null, 2);
            UI.parsedDisplay.innerHTML = createParsedResponse(selectedApi, result.data);

        } catch (error) {
            const errorMessage = `Error: ${error.message}`;
            UI.parsedDisplay.innerHTML = `<span class="error">${errorMessage}</span>`;
            const failedUrl = queryString ? `${url}?${queryString}` : url;
            UI.rawCallDisplay.textContent = `\`\`\`bash\ncurl -X GET "${failedUrl}"\n\`\`\``; // Show the URL that failed
            UI.rawResponseDisplay.textContent = errorMessage;
        }
    };

    // Event Listeners
    UI.apiSelect.addEventListener('change', showInput);
    UI.callApiBtn.addEventListener('click', callApi);

    // Initial setup
    showInput();
    updateApiDescription(); // Call on initial load
});