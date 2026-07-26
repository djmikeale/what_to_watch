import json
import webbrowser
from pathlib import Path
from datetime import datetime
import polars as pl
from rich.console import Console
from rich.panel import Panel
from simplejustwatchapi import search
from rich.prompt import Confirm
import readchar

console = Console()

# File paths
MOVIES_DB = "movies.parquet"
STREAMING_DB = "streaming_cache.json"
CONFIG_FILE = "user_config.json"
WATCHED_FILE = "watched_movies.json"

def load_movies():
    """Load movies from parquet file"""
    return pl.read_parquet(MOVIES_DB)

def load_watched():
    """Load watched movies"""
    if Path(WATCHED_FILE).exists():
        with open(WATCHED_FILE) as f:
            return json.load(f)
    return []

def save_watched(watched):
    """Save watched movies"""
    with open(WATCHED_FILE, "w") as f:
        json.dump(watched, f, indent=2)

def is_movie_watched(film_id, watched_list):
    """Check if a movie is in watched list"""
    return any(w["film_id"] == film_id for w in watched_list)

def load_config():
    """Load user's streaming platform preferences"""
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"platforms": []}

def save_config(config):
    """Save user's streaming platform preferences"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def load_streaming_cache():
    """Load cached streaming info"""
    if Path(STREAMING_DB).exists():
        with open(STREAMING_DB) as f:
            return json.load(f)
    return {}

def save_streaming_cache(cache):
    """Save streaming info cache"""
    with open(STREAMING_DB, "w") as f:
        json.dump(cache, f, indent=2)

def fetch_and_cache_streaming(film_title, imdb_id):
    """Fetch streaming info and cache it"""
    cache = load_streaming_cache()

    if imdb_id in cache:
        return cache[imdb_id]

    try:
        results = search(film_title, country="DK", language="en", count=1)

        if results:
            entry = results[0]
            streaming_info = {
                "title": entry.title,
                "imdb_id": entry.imdb_id,
                "runtime": entry.runtime_minutes,
                "description": entry.short_description,
                "genres": entry.genres,
                "rating": entry.scoring.imdb_score if entry.scoring else None,
                "offers": []
            }

            for offer in entry.offers:
                streaming_info["offers"].append({
                    "service": offer.package.name,
                    "url": offer.url,
                    "type": offer.monetization_type
                })

            cache[imdb_id] = streaming_info
            save_streaming_cache(cache)
            return streaming_info
    except Exception as e:
        console.print(f"[yellow]Could not fetch streaming info for '{film_title}'[/yellow]")

    return None

def convert_genre_short_to_long(genre_short):
    """Convert short genre codes to long names"""
    genre_map = {
        "act": "Action & Adventure",
        "ani": "Animation",
        "cmy": "Comedy",
        "crm": "Crime",
        "doc": "Documentary",
        "drm": "Drama",
        "eur": "Made in Europe",
        "fml": "Kids & Family",
        "fnt": "Fantasy",
        "hrr": "Horror",
        "hst": "History",
        "msc": "Music & Musical",
        "rma": "Romance",
        "scf": "Science-Fiction",
        "spt": "Sport",
        "trl": "Mystery & Thriller",
        "war": "War & Military",
        "wsn": "Western"
    }
    return genre_map.get(genre_short, genre_short)

def setup_platforms():
    """Setup streaming platforms"""
    console.print(Panel(
        "[bold cyan]🎬 Setup Streaming Platforms[/bold cyan]\n"
        "Which streaming platforms do you have access to?",
        expand=False
    ))

    available_platforms = [
        "Netflix",
        "Netflix with Ads",
        "Apple TV Store",
        "Amazon Video",
        "Disney+",
        "Hulu",
        "HBO Max",
        "Paramount+",
        "Fandango At Home"
    ]

    selected = []
    for i, platform in enumerate(available_platforms, 1):
        if Confirm.ask(f"  {platform}?", default=False):
            selected.append(platform)

    config = load_config()
    config["platforms"] = selected
    save_config(config)

    console.print(f"\n[green]✓ Saved: {', '.join(selected)}[/green]\n")

def get_candidate_movies(movies_df, watched_list):
    """Get unwatched movies"""
    watched_ids = {w["film_id"] for w in watched_list}
    return movies_df.filter(~pl.col("film_id").is_in(watched_ids)).to_dicts()

def get_movies_with_streaming(candidates, platforms, batch_size=50):
    """
    Generator that yields movies available on user's platforms.
    Caches in batches of batch_size as needed.
    """
    cache = load_streaming_cache()
    config = load_config()
    user_platforms = config.get("platforms", [])

    cached_count = 0
    fetched_count = 0

    for i, movie in enumerate(candidates):
        imdb_id = movie["film_id"]

        # Check cache first
        if imdb_id in cache:
            streaming_info = cache[imdb_id]
            cached_count += 1
        else:
            # Fetch and cache
            streaming_info = fetch_and_cache_streaming(movie["film"], imdb_id)
            fetched_count += 1

            # Show progress every batch_size fetches
            if fetched_count % batch_size == 0:
                console.print(f"[dim]Cached {cached_count + fetched_count} films... (fetched {fetched_count})[/dim]")

        if not streaming_info:
            continue

        # Check if available on user's platforms
        matching_offers = [
            offer for offer in streaming_info.get("offers", [])
            if offer["service"] in user_platforms
        ]

        if matching_offers:
            yield {
                "movie": movie,
                "streaming": streaming_info,
                "offers": matching_offers
            }

def display_movie(movie_data):
    """Display a movie in tinder-style"""
    movie = movie_data["movie"]
    streaming = movie_data["streaming"]
    offers = movie_data["offers"]

    console.clear()

    rating_str = f"{streaming['rating']}/10" if streaming['rating'] else "N/A"

    panel_content = f"""[bold cyan]{streaming['title']}[/bold cyan]

[dim]IMDb ID: {movie['film_id']}[/dim]

[bold yellow]Rating:[/bold yellow] {rating_str}   [bold yellow]Runtime:[/bold yellow] {streaming['runtime']} minutes   [bold yellow]Genres:[/bold yellow] {', '.join(convert_genre_short_to_long(genre) for genre in streaming['genres']) if streaming['genres'] else 'N/A'}

[bold yellow]Description:[/bold yellow] {streaming['description']}
"""
    panel_content += "\n[bold yellow]Available on:[/bold yellow] "
    for offer in offers:
        panel_content += f" [link={offer['url']}]{offer['service']}[/link]"
        if offer != offers[-1]:
            panel_content += ","

    panel_content += "\n\n[dim]Y Watch  |  A Skip  |  N Skip  |  P Platforms  |  Q Quit[/dim]"
    console.print("\n")
    console.print(Panel(panel_content, border_style="cyan"))

    return offers

def get_single_keypress():
    """Read a single keypress from user without waiting for Enter"""
    try:
        key = readchar.readchar().lower()
        return key
    except (KeyboardInterrupt, EOFError):
        return "q"

def get_movie_comment():
    """Prompt user for a comment about the movie"""
    console.print("\n[dim]What did you think? (optional, press Enter to skip)[/dim]")
    comment = console.input("[cyan]Comment: [/cyan]").strip()
    return comment if comment else ""

def watch_movie(offers):
    """Open streaming link and get user comment"""
    webbrowser.open(offers[0]["url"])
    comment = get_movie_comment()
    return comment

def tinder_mode():
    """Main tinder-style movie suggestion loop"""
    config = load_config()

    # If no platforms configured, run setup first
    if not config.get("platforms"):
        setup_platforms()
        config = load_config()
        if not config.get("platforms"):
            console.print("[yellow]No platforms selected. Exiting.[/yellow]")
            return

    movies_df = load_movies()
    watched = load_watched()

    console.print("[dim]Loading movies...[/dim]")
    candidates = get_candidate_movies(movies_df, watched)

    if not candidates:
        console.print("[yellow]No unwatched movies found.[/yellow]")
        return

    console.print(f"[dim]Found {len(candidates)} unwatched movies. Starting to cache...[/dim]\n")

    movie_generator = get_movies_with_streaming(candidates, config.get("platforms"))

    for movie_data in movie_generator:
        offers = display_movie(movie_data)

        choice = get_single_keypress()

        if choice in ["a", "n"]:
            continue
        elif choice == "y":
            comment = watch_movie(offers)
            watched_entry = {
                "film_id": movie_data["movie"]["film_id"],
                "title": movie_data["streaming"]["title"],
                "comment": comment,
                "timestamp": datetime.now().isoformat()
            }
            watched.append(watched_entry)
            save_watched(watched)
            console.print("[green]✓ Marked as watched[/green]")
        elif choice == "p":
            setup_platforms()
            config = load_config()
        elif choice == "q":
            console.print("[cyan]Goodbye! 🎬[/cyan]")
            break

    if choice != "q":
        console.print("[cyan]No more movies! Add more platforms or check back later.[/cyan]")

def main():
    """Entry point - jump directly to tinder mode"""
    tinder_mode()

if __name__ == "__main__":
    main()
