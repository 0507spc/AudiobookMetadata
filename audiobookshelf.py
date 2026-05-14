import json
import os
import re
import requests
from dotenv import load_dotenv
from rich.console import Console

console = Console()

# load .env
load_dotenv()

abs_headers = {
    "Authorization": "Bearer {}",
    "Content-Type": "application/json"
}


def audiobookshelf_login():
    login_payload = {
        "username": os.getenv("AUDIOBOOKSHELF_USERNAME"),
        "password": os.getenv("AUDIOBOOKSHELF_PASSWORD"),
    }
    login_request = requests.post(url=f'{os.getenv("AUDIOBOOKSHELF_URL")}/login', data=login_payload)
    return login_request.json()['user']['token'] if login_request.ok else None


def _normalize_title(title):
    """Normalize title by removing special characters and converting to lowercase"""
    return re.sub(r'\W+', '', str(title).lower())


def _titles_are_close_match(title1, title2):
    """Check if titles are close enough (one contains most of the other)"""
    norm_title1 = _normalize_title(title1)
    norm_title2 = _normalize_title(title2)
    
    # If exact match, return True
    if norm_title1 == norm_title2:
        return True
    
    # If one is significantly longer, check if the shorter one is contained in the longer one
    # This handles cases like "Title: Subtitle" matching "Title"
    if len(norm_title1) > len(norm_title2):
        longer = norm_title1
        shorter = norm_title2
    else:
        longer = norm_title2
        shorter = norm_title1
    
    # Check if the shorter title is a substring of the longer one
    # and is at least 70% of the longer title's length
    if shorter in longer and len(shorter) >= len(longer) * 0.7:
        return True
    
    return False


def audiobookshelf_book_lookup(book_title, book_author, token, allow_partial_match=True):
    """
    Lookup a book in audiobookshelf.
    
    Args:
        book_title: The title of the book to search for
        book_author: The author of the book to search for
        token: The authentication token
        allow_partial_match: If True, will prompt user when a close match is found but not exact
    
    Returns:
        Dictionary with book data, or None if not found or user rejects partial match
    """
    library_name = os.getenv("AUDIOBOOKSHELF_LIBRARY", "main")
    lookup_url = f'{os.getenv("AUDIOBOOKSHELF_URL")}/api/libraries/{library_name}/search?q={book_title}'
    
    lookup_request = requests.get(url=lookup_url, headers={'Authorization': f'Bearer {token}'})
    
    # Debug: Print response status and content
    if not lookup_request.ok:
        console.print(f"[red]API Error: {lookup_request.status_code}[/red]")
        console.print(f"[red]Response: {lookup_request.text}[/red]")
        return None
    
    response_json = lookup_request.json()
    
    # Debug: Print response structure
    console.print(f"[yellow]Response keys: {response_json.keys()}[/yellow]")
    
    # Check if response has 'audiobooks' array (multiple results)
    if 'audiobooks' in response_json:
        if len(response_json['audiobooks']) == 0:
            return None
        
        lookup_response = response_json
        for audiobook in lookup_response['audiobooks']:
            resp_book_title = _normalize_title(audiobook['audiobook']['book']['title'])
            resp_book_author = _normalize_title(audiobook['audiobook']['book']['author'])

            if resp_book_title == _normalize_title(book_title) and resp_book_author == _normalize_title(book_author):
                return audiobook["audiobook"]
    
    # Check if response is a single book object (direct result)
    elif 'book' in response_json:
        # The API returns: { 'book': [...], 'authors': [...], ... }
        # book is a list, so get the first item
        book_list = response_json['book']
        
        if not isinstance(book_list, list) or len(book_list) == 0:
            return None
        
        # Get the first book item from the list
        book_item = book_list[0]
        
        # Check if this item has a 'libraryItem' key
        if 'libraryItem' in book_item:
            library_item = book_item['libraryItem']
        else:
            # Otherwise use the book_item directly
            library_item = book_item
        
        # Debug: Print book_data keys
        console.print(f"[yellow]LibraryItem keys: {library_item.keys()}[/yellow]")
        
        # Get metadata from the media object
        media = library_item.get('media', {})
        metadata = media.get('metadata', {})
        
        console.print(f"[yellow]Metadata keys: {metadata.keys()}[/yellow]")
        
        # Extract title and author from metadata
        resp_book_title = _normalize_title(metadata.get('title', ''))
        
        # Author is in metadata.authors as a list of objects with 'name' field
        authors = metadata.get('authors', [])
        resp_book_author = ""
        if authors and len(authors) > 0:
            resp_book_author = _normalize_title(authors[0].get('name', ''))
        
        normalized_title = _normalize_title(book_title)
        normalized_author = _normalize_title(book_author)
        
        console.print(f"[cyan]Comparing: '{resp_book_title}' vs '{normalized_title}'[/cyan]")
        console.print(f"[cyan]Comparing authors: '{resp_book_author}' vs '{normalized_author}'[/cyan]")
        
        # Check for exact match first
        if resp_book_title == normalized_title and resp_book_author == normalized_author:
            return _build_book_return(library_item, metadata, authors)
        
        # Check for close/partial match if allowed
        if allow_partial_match and resp_book_author == normalized_author and _titles_are_close_match(resp_book_title, normalized_title):
            console.print(f"\n[yellow]Found a close match:[/yellow]")
            console.print(f"  [cyan]Title in library:[/cyan] {metadata.get('title', '')}")
            console.print(f"  [cyan]Title searched:[/cyan] {book_title}")
            console.print(f"  [cyan]Author:[/cyan] {authors[0].get('name', '') if authors else 'Unknown'}")
            
            response = input("\nIs this the book you're looking for? [y/n]: ").strip().lower()
            if response == 'y':
                return _build_book_return(library_item, metadata, authors)
            else:
                return None

    return None


def _build_book_return(library_item, metadata, authors):
    """Build the standard book return object"""
    # Extract narrator names from the narrators list
    narrators = metadata.get('narrators', [])
    narrator_str = ", ".join(narrators) if narrators else ""
    
    # Extract series info if available
    series_list = metadata.get('series', [])
    series_name = series_list[0].get('name', '') if series_list else ""
    series_sequence = series_list[0].get('sequence', '') if series_list else ""
    
    # Build the expected return format
    return {
        "id": library_item.get('id'),
        "book": {
            "title": metadata.get('title', ''),
            "subtitle": metadata.get('subtitle', ''),
            "description": metadata.get('description', ''),
            "author": authors[0].get('name', '') if authors else "",
            "narrator": narrator_str,
            "series": series_name,
            "volumeNumber": series_sequence,
            "publishYear": metadata.get('publishedYear', ''),
            "publisher": metadata.get('publisher', ''),
            "isbn": metadata.get('isbn', ''),
        },
        "libraryItem": library_item
    }


# Create a new class to parse the json & update certain fields then return the json
class AudiobookshelfBook:
    def __init__(self, audiobookshelf_json, audnexus_json):
        self.book_payload = {
            "book": {
                "title": f'{audiobookshelf_json["book"]["title"]}',
                "subtitle": audiobookshelf_json['book']['subtitle'],
                "description": audiobookshelf_json['book']['description'],
                "author": audiobookshelf_json['book']['author'],
                "narrator": audiobookshelf_json['book']['narrator'],
                "series": audiobookshelf_json['book']['series'],
                "volumeNumber": audiobookshelf_json['book']['volumeNumber'],
                "publishYear": audiobookshelf_json['book']['publishYear'],
                "publisher": audiobookshelf_json['book']['publisher'],
                "isbn": audiobookshelf_json['book']['isbn'],
                "genres": []
            },
            "tags": []
        }


    def update_book_title(self, new_title):
        self.book_payload['book']['title'] = new_title
        return self.book_payload

    def update_tags(self, tags):
        self.book_payload['tags'] = tags
        return self.book_payload

    def update_genres(self, genres):
        self.book_payload['book']['genres'] = genres
        return self.book_payload



    def return_json(self):
        # Prepare the json for the POST request to audiobookshelf (dumps to string) & return
        return json.dumps(self.book_payload)




def audiobookshelf_book_update(book_id, book_payload, token):
    # I got these headers from test requests made in Postman
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/94.0',
        'Accept': 'application/json, text/plain, */*',
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json;charset=utf-8'
    }

    # Update the book details in the audiobookshelf
    update_book_request = requests.patch(url=f'{os.getenv("AUDIOBOOKSHELF_URL")}/api/books/{book_id}', headers=headers, data=book_payload)

    return bool(update_book_request.ok)
