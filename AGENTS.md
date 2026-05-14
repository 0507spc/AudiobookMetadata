# AudiobookMetadata Agent Guidelines

## Project Overview
This repository contains tools for automatically setting Genres & Tags on audiobookshelf servers by fetching metadata from Audible via the AudNexus API.

## Key Components

### Main Entry Point
- `main.py`: Primary script that orchestrates the workflow:
  1. Takes book title/author as input
  2. Searches Audible for matching ASINs
  3. Fetches detailed book metadata from AudNexus
  4. Optionally searches Audiobookshelf for the book
  5. Updates Audiobookshelf with fetched metadata

### Modules
- `audiobookshelf.py`: Handles Audiobookshelf API interactions
- `audnexus.py`: Handles AudNexus API interactions (Audible metadata)

## Development Guidelines

### Code Style
- Follow existing code formatting and patterns
- Use type hints where appropriate
- Keep functions focused and modular
- Add error handling for API calls
- Use the Rich library for consistent console output

### API Interactions
- All API credentials should be stored in environment variables
- Handle rate limiting and API errors gracefully
- Validate API responses before processing
- Use proper authentication flows (login tokens, etc.)

### Environment Variables
- Required variables should be documented in `.env.sample`
- Never commit actual credentials to the repository

### Testing
- Test API interactions with mock responses when possible
- Verify data mapping between AudNexus and Audiobookshelf formats
- Test edge cases (missing data, API failures, etc.)

### Common Tasks
1. Adding new metadata fields:
   - Update `_build_media_payload()` in main.py
   - Add corresponding Audiobookshelf API calls in audiobookshelf.py
   - Update field mapping logic as needed

2. Improving Audible search:
   - Modify `search_audible()` function in main.py
   - Adjust AudNexus API calls in audnexus.py

3. Enhancing Audiobookshelf integration:
   - Update functions in audiobookshelf.py
   - Ensure proper payload formatting for different endpoints

## Workflow
1. User provides book title/author (via CLI args or prompt)
2. Script searches Audible for potential matches
3. User selects or script uses first Audible result
4. Detailed metadata fetched from AudNexus
5. Optional: Search Audiobookshelf for existing book
6. If found, update book metadata with AudNexus data
7. Report success/failure to user

## Notes
- The script currently focuses on updating genres and tags primarily
- Additional metadata fields can be added via the `--update-fields` parameter
- Always verify API changes don't break existing functionality