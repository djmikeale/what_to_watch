import json
import webbrowser
from pathlib import Path
import polars as pl
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from simplejustwatchapi import search
from pynput import keyboard
import threading

console = Console()

# File paths
MOVIES_DB = "movies.parquet"
STREAMING_DB = "streaming_cache.json"
CONFIG_FILE = "user_config.json"
WATCHED_FILE = "watched_movies.json"

# Global for keyboard input
key_pressed = None

def on_press(key):
    """Capture key presses"""
    global key_pressed
    try:
        if key == keyboard.Key.left:
            key_pressed = "left"
        elif key == keyboard.Key.right:
            key_pressed = "right"
        elif key.char in ['q', 'Q']:
            key_pressed = "quit"
    except AttributeError:
        pass

def load_movies():
    """Load movies from parquet file"""
    return pl.read_parquet(MOVIES_DB)

def load_watched():
    """Load watched movies"""
    if Path(WATCHED_FILE).exists():
        with open(WATCHED_FILE) as f:
            return set(json.load(f))
    return set()

def save_watched(watched):
    """Save watched movies"""
    with open(WATCHED_FILE, "w") as f:
        json.dump(list(watched), f)

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

    console.print(f"\n[green]✓ Saved: {', '.join(selected)}[/green]")

def get_candidate_movies(movies_df, watched):
    """Get unwatched movies (all of them, no filtering yet)"""
    return movies_df.filter(~pl.col("film_id").is_in(watched)).to_dicts()

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

    panel_content += "\n\n[dim] Select: ← Maybe Later  |  → Watch  |  Q Quit[/dim]"
    console.print("\n")
    console.print(Panel(panel_content, border_style="cyan"))

    return offers

def watch_movie(offers):
    """Open streaming link"""
    webbrowser.open(offers[0]["url"])
    return True

def wait_for_key():
    """Wait for arrow key or q press"""
    global key_pressed
    key_pressed = None

    with keyboard.Listener(on_press=on_press) as listener:
        while key_pressed is None:
            pass

    return key_pressed

def tinder_mode():
    """Main tinder-style movie suggestion loop"""
    config = load_config()
    if not config.get("platforms"):
        console.print("[yellow]No streaming platforms configured. Run setup first.[/yellow]")
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

        choice = wait_for_key()

        if choice == "left":
            continue
        elif choice == "right":
            if watch_movie(offers):
                watched.add(movie_data["movie"]["film_id"])
                save_watched(watched)
                console.print("[green]✓ Marked as watched[/green]")
        elif choice == "quit":
            break

    console.print("[cyan]No more movies! Add more platforms or check back later.[/cyan]")

def main():
    """Main menu"""
    while True:
        console.print(Panel(
            "[bold cyan]🎬 What to Watch[/bold cyan]",
            expand=False
        ))

        console.print("\n1. Setup streaming platforms")
        console.print("2. Get movie suggestion")
        console.print("3. Exit")

        choice = Prompt.ask("Select", choices=["1", "2", "3"])

        if choice == "1":
            setup_platforms()
        elif choice == "2":
            tinder_mode()
        else:
            console.print("[cyan]Goodbye! 🎬[/cyan]")
            break

if __name__ == "__main__":
    main()
