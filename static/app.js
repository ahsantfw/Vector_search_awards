// ============================================
// SBIR Vector Search - Main Application
// ============================================

const API_BASE_URL = window.location.origin; // Use same origin as the page
const API_ENDPOINT = `${API_BASE_URL}/search`; // Note: router has prefix="/search" so this is correct

// Helper function to add tunnel skip warning headers to fetch requests
function createFetchOptions(options = {}) {
    const headers = new Headers(options.headers || {});
    
    // Detect tunnel service and add appropriate header
    const hostname = window.location.hostname;
    
    // ngrok free tier
    if (hostname.includes('ngrok-free.app') || hostname.includes('ngrok.io')) {
        headers.set('ngrok-skip-browser-warning', 'true');
    }
    
    // localtunnel
    if (hostname.includes('loca.lt')) {
        headers.set('bypass-tunnel-reminder', 'true');
        // Also set a custom User-Agent as alternative method
        headers.set('User-Agent', 'SBIR-Vector-Search-Client/1.0');
    }
    
    return {
        ...options,
        headers: headers
    };
}

// State
let currentResults = {
    hybrid: [],
    lexical: [],
    semantic: [],
    metadata: {}
};

// DOM Elements - will be initialized after DOM loads
let searchInput, searchButton, topKSelect, alphaInput, betaInput;
let loadingIndicator, errorMessage, resultsSection, emptyState;
let tabButtons, hybridResultsPanel, lexicalResultsPanel, semanticResultsPanel;
let hybridResultsList, lexicalResultsList, semanticResultsList;
let hybridCount, lexicalCount, semanticCount;
let queryDisplay, searchTime, vectorStore;
let exampleTags;

// Initialize DOM elements (called after DOM is ready)
function initializeDOMElements() {
    searchInput = document.getElementById('searchInput');
    searchButton = document.getElementById('searchButton');
    topKSelect = document.getElementById('topKSelect');
    alphaInput = document.getElementById('alphaInput');
    betaInput = document.getElementById('betaInput');
    loadingIndicator = document.getElementById('loadingIndicator');
    errorMessage = document.getElementById('errorMessage');
    resultsSection = document.getElementById('resultsSection');
    emptyState = document.getElementById('emptyState');
    
    tabButtons = document.querySelectorAll('.tab-button');
    hybridResultsPanel = document.getElementById('hybridResults');
    lexicalResultsPanel = document.getElementById('lexicalResults');
    semanticResultsPanel = document.getElementById('semanticResults');
    
    hybridResultsList = document.getElementById('hybridResultsList');
    lexicalResultsList = document.getElementById('lexicalResultsList');
    semanticResultsList = document.getElementById('semanticResultsList');
    
    hybridCount = document.getElementById('hybridCount');
    lexicalCount = document.getElementById('lexicalCount');
    semanticCount = document.getElementById('semanticCount');
    
    queryDisplay = document.getElementById('queryDisplay');
    searchTime = document.getElementById('searchTime');
    vectorStore = document.getElementById('vectorStore');
    
    exampleTags = document.querySelectorAll('.example-tag');
    
    // Verify critical elements exist
    if (!searchInput || !searchButton || !topKSelect) {
        console.error('Critical DOM elements not found!', {
            searchInput: !!searchInput,
            searchButton: !!searchButton,
            topKSelect: !!topKSelect
        });
        return false;
    }
    
    // Alpha and beta are optional, but log if missing
    if (!alphaInput || !betaInput) {
        console.warn('Parameter inputs not found, using defaults');
    }
    
    return true;
}

// ============================================
// Event Listeners Setup
// ============================================

function setupEventListeners() {
    if (!searchInput || !searchButton || !topKSelect) {
        console.error('Cannot setup event listeners - elements not found', {
            searchInput: !!searchInput,
            searchButton: !!searchButton,
            topKSelect: !!topKSelect
        });
        return;
    }
    
    // Search button click
    searchButton.addEventListener('click', performSearch);

    // Enter key in search input
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    // Tab switching
    if (tabButtons && tabButtons.length > 0) {
        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                switchTab(button.dataset.tab);
            });
        });
    }

    // Example query clicks
    if (exampleTags && exampleTags.length > 0) {
        exampleTags.forEach(tag => {
            tag.addEventListener('click', () => {
                if (searchInput) {
                    searchInput.value = tag.dataset.query || '';
                    performSearch();
                }
            });
        });
    }
}

// ============================================
// Search Function
// ============================================

async function performSearch() {
    if (!searchInput) {
        showError('Search input not found. Please refresh the page.');
        return;
    }
    
    const query = searchInput.value ? searchInput.value.trim() : '';
    
    if (!query) {
        showError('Please enter a search query');
        return;
    }
    
    // Hide empty state and error
    if (errorMessage) hideError();
    if (emptyState) emptyState.classList.add('hidden');
    
    // Show loading
    if (loadingIndicator) showLoading();
    if (resultsSection) resultsSection.classList.add('hidden');
    
    // Disable search button
    if (searchButton) searchButton.disabled = true;
    
    try {
        // Get parameters with fallbacks
        let topK = 10;
        if (topKSelect && topKSelect.value) {
            topK = parseInt(topKSelect.value) || 10;
        }
        
        let alpha = 0.5;
        if (alphaInput && alphaInput.value) {
            const alphaVal = parseFloat(alphaInput.value);
            if (!isNaN(alphaVal) && alphaVal >= 0 && alphaVal <= 1) {
                alpha = alphaVal;
            }
        }
        
        let beta = 10.0;
        if (betaInput && betaInput.value) {
            const betaVal = parseFloat(betaInput.value);
            if (!isNaN(betaVal) && betaVal >= 0) {
                beta = betaVal;
            }
        }
        
        const requestBody = {
            query: query,
            top_k: topK,
            alpha: alpha,
            beta: beta
        };
        
        // Debug: Log the parameters being sent
        console.log('Search parameters:', { query, topK, alpha, beta });
        
        const response = await fetch(API_ENDPOINT, createFetchOptions({
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        }));
        
        if (!response.ok) {
            let errorMessage = `HTTP ${response.status}`;
            try {
                const errorData = await response.json();
                errorMessage = errorData.detail || errorData.message || errorMessage;
            } catch (e) {
                // If JSON parsing fails, use status text
                errorMessage = response.statusText || errorMessage;
            }
            throw new Error(errorMessage);
        }
        
        const data = await response.json();
        
        // Validate response structure
        if (!data) {
            throw new Error('Empty response from server');
        }
        
        // Store results with validation
        currentResults = {
            hybrid: Array.isArray(data.hybrid_results) ? data.hybrid_results : [],
            lexical: Array.isArray(data.lexical_results) ? data.lexical_results : [],
            semantic: Array.isArray(data.semantic_results) ? data.semantic_results : [],
            metadata: data.metadata || {}
        };
        
        // Update UI
        updateResults();
        if (data.query && data.metadata) {
            updateMetadata(data.query, data.metadata);
        }
        updateCounts();
        
        // Show results
        if (loadingIndicator) hideLoading();
        if (resultsSection) resultsSection.classList.remove('hidden');
        
        // Switch to hybrid tab (default)
        switchTab('hybrid');
        
    } catch (error) {
        console.error('Search error:', error);
        if (loadingIndicator) hideLoading();
        showError(`Search failed: ${error.message}`);
    } finally {
        if (searchButton) searchButton.disabled = false;
    }
}

// ============================================
// Tab Switching
// ============================================

function switchTab(tabName) {
    // Update tab buttons
    tabButtons.forEach(button => {
        if (button.dataset.tab === tabName) {
            button.classList.add('active');
        } else {
            button.classList.remove('active');
        }
    });
    
    // Update panels
    hybridResultsPanel.classList.remove('active');
    lexicalResultsPanel.classList.remove('active');
    semanticResultsPanel.classList.remove('active');
    
    switch(tabName) {
        case 'hybrid':
            hybridResultsPanel.classList.add('active');
            break;
        case 'lexical':
            lexicalResultsPanel.classList.add('active');
            break;
        case 'semantic':
            semanticResultsPanel.classList.add('active');
            break;
    }
}

// ============================================
// Update Results Display
// ============================================

function updateResults() {
    renderResults(currentResults.hybrid, hybridResultsList, 'hybrid');
    renderResults(currentResults.lexical, lexicalResultsList, 'lexical');
    renderResults(currentResults.semantic, semanticResultsList, 'semantic');
}

function renderResults(results, container, type) {
    container.innerHTML = '';
    
    if (results.length === 0) {
        container.innerHTML = `
            <div class="empty-results">
                <p>No results found for this search approach.</p>
            </div>
        `;
        return;
    }
    
    results.forEach((result, index) => {
        const card = createResultCard(result, index + 1, type);
        container.appendChild(card);
    });
}

function createResultCard(result, rank, type) {
    const card = document.createElement('div');
    card.className = 'result-card';
    
    // Determine which score to show based on type
    let primaryScore = null;
    let scoreLabel = '';
    
    if (type === 'hybrid') {
        primaryScore = result.final_score;
        scoreLabel = 'Final Score';
    } else if (type === 'lexical') {
        primaryScore = result.lexical_score;
        scoreLabel = 'Lexical Score';
    } else if (type === 'semantic') {
        primaryScore = result.semantic_score;
        scoreLabel = 'Semantic Score';
    }
    
    // Format scores
    const formatScore = (score) => {
        if (score === null || score === undefined) return 'N/A';
        return score.toFixed(4);
    };
    
    // Highlight query terms in snippet
    const highlightSnippet = (text, query) => {
        if (!text || !query) return text || '';
        
        // Split query into terms, filter out empty strings, spaces, and whitespace-only terms
        const terms = query.trim()
            .split(/\s+/)
            .filter(term => term && term.trim().length > 0) // Remove empty strings and whitespace
            .map(term => term.toLowerCase().trim()); // Normalize terms
        
        if (terms.length === 0) return text;
        
        let highlighted = text;
        
        // Escape special regex characters in terms
        const escapeRegex = (str) => {
            return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        };
        
        // Create a single regex pattern for all terms to avoid overlapping matches
        const escapedTerms = terms
            .filter(term => term.length > 0)
            .map(term => escapeRegex(term))
            .filter(term => term.length > 0); // Double check no empty patterns
        
        if (escapedTerms.length === 0) return text;
        
        // Match whole words only (word boundaries)
        const pattern = `\\b(${escapedTerms.join('|')})\\b`;
        const regex = new RegExp(pattern, 'gi');
        
        highlighted = highlighted.replace(regex, '<span class="highlight">$1</span>');
        
        return highlighted;
    };
    
    const queryText = searchInput ? searchInput.value : '';
    const highlightedSnippet = highlightSnippet(result.snippet || '', queryText);
    
    // Make card clickable if URL exists
    const hasUrl = result.url && result.url.trim() !== '';
    if (hasUrl) {
        card.style.cursor = 'pointer';
        card.classList.add('clickable-award');
        card.setAttribute('data-url', result.url);
        card.setAttribute('title', 'Click to view award details');
        
        // Add click handler to open URL in new window
        card.addEventListener('click', (e) => {
            // Don't open if clicking on a link or button inside
            if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON') {
                return;
            }
            window.open(result.url, '_blank', 'noopener,noreferrer');
        });
    }
    
    card.innerHTML = `
        <div class="result-header">
            <div>
                <div class="result-title">
                    ${hasUrl ? `<a href="${result.url}" target="_blank" rel="noopener noreferrer" class="award-link">${result.title || 'Untitled Award'}</a>` : (result.title || 'Untitled Award')}
                </div>
                <div class="result-id">${result.award_id}</div>
            </div>
            ${hasUrl ? `<div class="result-link-icon" title="View award details">🔗</div>` : ''}
        </div>
        
        <div class="result-scores">
            ${primaryScore !== null ? `
                <div class="score-badge final">
                    <span class="score-label">${scoreLabel}:</span>
                    <span>${formatScore(primaryScore)}</span>
                </div>
            ` : ''}
            
            ${type === 'hybrid' && result.lexical_score !== null ? `
                <div class="score-badge lexical">
                    <span class="score-label">Lexical:</span>
                    <span>${formatScore(result.lexical_score)}</span>
                </div>
            ` : ''}
            
            ${type === 'hybrid' && result.semantic_score !== null ? `
                <div class="score-badge semantic">
                    <span class="score-label">Semantic:</span>
                    <span>${formatScore(result.semantic_score)}</span>
                </div>
            ` : ''}
            
            ${type === 'lexical' && result.lexical_score !== null ? `
                <div class="score-badge lexical">
                    <span class="score-label">Score:</span>
                    <span>${formatScore(result.lexical_score)}</span>
                </div>
            ` : ''}
            
            ${type === 'semantic' && result.semantic_score !== null ? `
                <div class="score-badge semantic">
                    <span class="score-label">Score:</span>
                    <span>${formatScore(result.semantic_score)}</span>
                </div>
            ` : ''}
        </div>
        
        ${result.agency ? `
            <div class="result-agency">${result.agency}</div>
        ` : ''}
        
        ${highlightedSnippet ? `
            <div class="result-snippet">${highlightedSnippet}</div>
        ` : ''}
        
        ${result.chunks && result.chunks.length > 1 ? `
            <div class="result-chunks">
                <div class="chunks-header">
                    <strong>Matching Chunks (${result.chunks.length}):</strong>
                </div>
                <div class="chunks-list">
                    ${result.chunks.map((chunk, idx) => {
                        const chunkSnippet = chunk.chunk_text ? 
                            (chunk.chunk_text.length > 150 ? chunk.chunk_text.substring(0, 150) + '...' : chunk.chunk_text) :
                            '';
                        const chunkScore = chunk.semantic_score || chunk.lexical_score || 0;
                        return `
                            <div class="chunk-item">
                                <div class="chunk-header">
                                    <span class="chunk-index">Chunk ${chunk.chunk_index + 1}</span>
                                    ${chunkScore > 0 ? `<span class="chunk-score">Score: ${chunkScore.toFixed(4)}</span>` : ''}
                                </div>
                                <div class="chunk-text">${highlightSnippet(chunkSnippet, queryText)}</div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        ` : ''}
    `;
    
    return card;
}

// ============================================
// Update Metadata
// ============================================

function updateMetadata(query, metadata) {
    if (queryDisplay) {
        queryDisplay.textContent = query || '-';
    }
    
    if (searchTime) {
        if (metadata && metadata.search_time_ms) {
            searchTime.textContent = `${metadata.search_time_ms.toFixed(2)} ms`;
        } else {
            searchTime.textContent = '-';
        }
    }
    
    if (vectorStore) {
        if (metadata && metadata.vector_store) {
            vectorStore.textContent = metadata.vector_store.toUpperCase();
        } else {
            vectorStore.textContent = '-';
        }
    }
}

function updateCounts() {
    if (hybridCount) {
        hybridCount.textContent = currentResults.hybrid.length;
    }
    if (lexicalCount) {
        lexicalCount.textContent = currentResults.lexical.length;
    }
    if (semanticCount) {
        semanticCount.textContent = currentResults.semantic.length;
    }
}

// ============================================
// UI State Management
// ============================================

function showLoading() {
    loadingIndicator.classList.remove('hidden');
}

function hideLoading() {
    loadingIndicator.classList.add('hidden');
}

function showError(message) {
    errorMessage.textContent = message;
    errorMessage.classList.remove('hidden');
}

function hideError() {
    errorMessage.classList.add('hidden');
}

// ============================================
// Initialize
// ============================================

// Check API health on load
async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`, createFetchOptions());
        if (response.ok) {
            const data = await response.json();
            console.log('API Health:', data);
        }
    } catch (error) {
        console.warn('Health check failed:', error);
    }
}

// Initialize when DOM is ready
function initialize() {
    // Initialize DOM elements
    if (!initializeDOMElements()) {
        console.error('Failed to initialize DOM elements');
        const errorDiv = document.getElementById('errorMessage');
        if (errorDiv) {
            errorDiv.textContent = 'Page elements not loaded. Please refresh.';
            errorDiv.classList.remove('hidden');
        }
        return;
    }
    
    // Setup event listeners
    setupEventListeners();
    
    // Check API health
    checkHealth();
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
} else {
    // DOM already loaded
    initialize();
}

