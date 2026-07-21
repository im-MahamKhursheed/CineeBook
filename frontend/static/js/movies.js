/**
 * movies.js — Fetches and displays movie list
 */

async function loadMovies() {
    const container = document.getElementById('movie-container');
    if (!container) return;

    try {
        // Fetch from your FastAPI endpoint defined in main.py
        const response = await apiFetch('/api/movies');
        if (!response) return;
        
        const movies = await response.json();

        container.innerHTML = ''; // Clear loading state

        movies.forEach(movie => {
            container.innerHTML += `
                <div class="col-md-4 mb-4">
                    <div class="card h-100">
                        <div class="card-body">
                            <h5 class="card-title">${movie.title}</h5>
                            <p class="card-text">${movie.description}</p>
                            <span class="badge bg-primary">${movie.genre}</span>
                            <div class="mt-3">
                                <a href="/booking?movie_id=${movie.id}" class="btn btn-accent">View Showtimes</a>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
    } catch (error) {
        console.error("Error loading movies:", error);
        showToast("Failed to load movies.", "error");
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', loadMovies);