import argparse
import requests
from rich import box, print_json
from rich.prompt import Prompt, Confirm
from rich.console import Console
from audiobookshelf import AudiobookshelfBook, audiobookshelf_login, audiobookshelf_book_lookup, audiobookshelf_book_update
from audnexus import audnexus_asin_lookup

console = Console()

def _build_media_payload(aud_book_details, fields):
    """
    Build a media payload dictionary for the Audiobookshelf /items/<ID>/media endpoint.
    'fields' is a list of canonical names (see supported list below).
    """
    payload = {}

    # helpers
    def first_author(authors):
        if not authors:
            return None
        a0 = authors[0]
        return a0.get("name") if isinstance(a0, dict) else str(a0)

    # genres & tags lists from audnexus style
    genres = [g["name"] for g in aud_book_details.get("genres", []) if g.get("type") == "genre"]
    tags = [g["name"] for g in aud_book_details.get("genres", []) if g.get("type") == "tag"]

    # narrators
    narrators = aud_book_details.get("narrators") or []
    if isinstance(narrators, list):
        narrators_list = [n if isinstance(n, str) else n.get("name", "") for n in narrators]
    elif isinstance(narrators, str):
        narrators_list = [narrators]
    else:
        narrators_list = []

    # series handling
    series_name = ""
    series_sequence = ""
    series = aud_book_details.get("series") or []
    if isinstance(series, list) and len(series) > 0:
        entry = series[0]
        if isinstance(entry, dict):
            series_name = entry.get("name", "")
            series_sequence = entry.get("sequence", "")
        else:
            series_name = str(entry)
    elif isinstance(series, dict):
        series_name = series.get("name", "")
        series_sequence = series.get("sequence", "")

    # published year fallback
    published_year = aud_book_details.get("publishedYear") or ""
    if not published_year:
        pd = aud_book_details.get("publishedDate") or aud_book_details.get("published_date")
        if pd:
            published_year = str(pd)[:4]

    # Map fields -> payload keys (use the API's expected key names)
    for f in fields:
        k = f.strip()
        if k == "title":
            payload["title"] = aud_book_details.get("title", "")
        elif k == "subtitle":
            payload["subtitle"] = aud_book_details.get("subtitle", "")
        elif k in ("authors", "author"):
            # Audiobookshelf sometimes expects authors array; adapt as needed.
            # Use authors array if available, otherwise use a single author string.
            authors = aud_book_details.get("authors", [])
            if authors:
                # convert to array of objects if possible
                if isinstance(authors, list) and isinstance(authors[0], dict):
                    payload["authors"] = authors
                else:
                    payload["authors"] = [{"name": first_author(authors)}]
            else:
                # fallback to single author string field if API expects 'author'
                payload["author"] = first_author(authors) or aud_book_details.get("author", "")
        elif k in ("narrators", "narrator"):
            # Many ABS APIs accept narrators as array or string — send array
            payload["narrators"] = narrators_list
        elif k == "series":
            if series_name:
                # ABS may expect series array/structure; use simple fields if your API expects that
                payload["series"] = [{"name": series_name, "sequence": series_sequence}] if series_name else []
        elif k == "genres":
            payload["genres"] = genres
        elif k in ("publishedYear", "publish_year"):
            payload["publishedYear"] = published_year
        elif k == "publishedDate":
            payload["publishedDate"] = aud_book_details.get("publishedDate") or aud_book_details.get("published_date", "")
        elif k == "publisher":
            payload["publisher"] = aud_book_details.get("publisher", "")
        elif k == "description":
            payload["description"] = aud_book_details.get("description", "") or aud_book_details.get("descriptionPlain", "")
        elif k == "isbn":
            payload["isbn"] = aud_book_details.get("isbn", "") or aud_book_details.get("tagIsbn", "")
        elif k == "asin":
            payload["asin"] = aud_book_details.get("asin", "") or aud_book_details.get("tagASIN", "")
        elif k == "language":
            payload["language"] = aud_book_details.get("language", "")
        elif k == "explicit":
            payload["explicit"] = bool(aud_book_details.get("explicit", False))
        elif k == "tags":
            payload["tags"] = tags
        # ignore unknown keys silently

    return payload

def search_audible(book_title, book_author):
    with console.status("Searching for possible matches on Audible...") as _:
        query = requests.get(
            url="https://api.audible.com/1.0/catalog/products",
            params={
                "title": book_title,
                "author": book_author,
                "category_id": "18685580011"  # Only show English results
            }
        )

        if not query.ok:  # If the request failed then we can't continue so just exit
            console.print("\nError: Unable to query audible API. Quitting...", style="red")
            quit()

        possible_asin = []
        # If any results are found we loop through them all & append each to a list
        if query.json()["total_results"] != 0:
            for result in query.json()["products"]:
                # noinspection PyTypeChecker
                possible_asin.append(result["asin"])

        # Return list of audible asin IDs for the book title & author we searched for
        return possible_asin


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Search for audiobook metadata and update audiobookshelf"
    )
    parser.add_argument(
        "--update-fields",
        help="Book update fields REQUIRED to update.",
        default=None
    )
    parser.add_argument(
        "-t", "--title",
        help="Book title (if not provided, will prompt)",
        default=None
    )
    parser.add_argument(
        "-a", "--author",
        help="Book author (if not provided, will prompt)",
        default=None
    )
    parser.add_argument(
        "--skip-show-search-json",
        action="store_true",
        help="Skip prompting to show Audible search JSON (automatically set to False)"
    )
    parser.add_argument(
        "--skip-show-abs-json",
        action="store_true",
        help="Skip prompting to show Audiobookshelf JSON (automatically set to False)"
    )
    parser.add_argument(
        "--search-abs",
        action="store_true",
        help="Automatically search audiobookshelf without prompting"
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    
    # Get book title from args or prompt
    if args.title:
        book_title_prompt = args.title
    else:
        book_title_prompt = Prompt.ask("Book Title")
        while not bool(book_title_prompt):  # Verify user input is not empty
            book_title_prompt = Prompt.ask("Book Title (Can't be blank)")
    
    # Get book author from args or prompt
    if args.author:
        book_author_prompt = args.author
    else:
        book_author_prompt = Prompt.ask("Author")

    query_aud = search_audible(book_title=book_title_prompt, book_author=book_author_prompt)

    if bool(query_aud):  # If the function returned at-least 1 asin we can call new function to gt book details
        aud_book_details = audnexus_asin_lookup(query_aud)
        console.line(count=2)  # Print 2 blank lines
        console.print(f'OK, We got the audiobook metadata for "[chartreuse2]{aud_book_details["title"]}[/chartreuse2]" by "[chartreuse2]{aud_book_details["authors"][0]["name"]}[/chartreuse2]"')

        # Ask if the user wants to see json output (skip if flag is set)
        if not args.skip_show_search_json:
            if Confirm.ask(prompt="Show JSON output?", default=False):
                print_json(data=aud_book_details)
                console.line(count=1)

        # Determine if we should search audiobookshelf
        should_search_abs = args.search_abs or Confirm.ask(prompt="\nSearch audiobookshelf for the book?", default=True)
        
        # Prompt user if they want to search audiobookshelf for the book & update the books details if found
        if should_search_abs:
            bearer_token = audiobookshelf_login()  # Get the bearer token
            if bearer_token:
                # Now try & find the book on audiobookshelf
                audiobookshelf_lookup = audiobookshelf_book_lookup(book_title=aud_book_details["title"], book_author=aud_book_details["authors"][0]["name"], token=bearer_token)
                if audiobookshelf_lookup:
                    console.print(f'Yay we found: "[dodger_blue1]{audiobookshelf_lookup["book"]["title"]}[/dodger_blue1]" by "[dodger_blue1]{audiobookshelf_lookup["book"]["author"]}[/dodger_blue1]"')
                    console.line(count=1)

                    if not args.skip_show_abs_json:
                        if Confirm.ask(prompt="Show audiobookshelf json response?", default=False):
                            print_json(data=audiobookshelf_lookup)
                            console.line(count=1)
                            
                    if args.update_fields:
                        if args.update_fields.strip().lower() == "all":
                            fields = ["title","subtitle","authors","narrators","series","genres","publishedYear","publishedDate","publisher","description","isbn","asin","language","explicit","tags"]
                        else:
                            fields = [f.strip() for f in args.update_fields.split(",") if f.strip()]
                    
                        media_payload = _build_media_payload(aud_book_details, fields)
                        # If Audiobookshelf expects the payload nested under "metadata" or "media", adjust accordingly.
                        # Example (if required): media_payload = {"metadata": media_payload}
                        success = audiobookshelf_media_update(item_id=audiobookshelf_lookup["libraryItem"]["id"] if "libraryItem" in audiobookshelf_lookup else audiobookshelf_lookup["id"], media_payload=media_payload, token=bearer_token)
                        if success:
                            console.print("\nSelected fields updated on audiobookshelf.\n", style="green")
                        else:
                            console.print("\nFailed to update selected fields on audiobookshelf.\n", style="red")



        
                    # Use the AudiobookshelfBook class to create a default book object
                    p1 = AudiobookshelfBook(audiobookshelf_json=audiobookshelf_lookup, audnexus_json=aud_book_details)
                    # Update the book genres & tags which we get back from the audnexus api (AKA audible)
                    p1.update_genres(genres=[g['name'] for g in aud_book_details["genres"] if g["type"] == "genre"])
                    p1.update_tags(tags=[t['name'] for t in aud_book_details["genres"] if t["type"] == "tag"])

                    # Update the book on audiobookshelf
                    f = audiobookshelf_book_update(book_id=audiobookshelf_lookup["id"], book_payload=p1.return_json(), token=bearer_token)
                    if f:
                        console.print("\nBook updated on audiobookshelf.\n", style="green")

                else:
                    console.print("\nBook not found on audiobookshelf.\n", style="red")
            else:
                console.print("\nError: Unable to get bearer token. Quitting...", style="red")
