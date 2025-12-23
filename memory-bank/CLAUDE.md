# CLAUDE.md

This file provides guidance to developers when working with code in this repository.

## Project Overview

MediaCMN is a comprehensive media center management system with a microservice architecture:
- **Media Server**: Python/AsyncIO + FastAPI backend with PostgreSQL database
- **Media Client**: Flutter/Dart cross-platform mobile/desktop client
- **Task Queue**: Dramatiq + Redis for background job processing
- **Database**: PostgreSQL with Alembic migrations

## Development Commands

### Backend (Media Server)

**Setup and Dependencies:**
```bash
cd media-server
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

**Database Operations:**
```bash
# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Rollback migration
alembic downgrade -1
```

**Development Server:**
```bash
# Run FastAPI server with auto-reload
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Run with specific environment
PYTHONPATH=. uvicorn api.main:app --reload
```

**Background Task Workers:**
```bash
# # Start workers in development mode
# ./start_consumers.sh dev

# # Start workers in production mode
# ./start_consumers.sh prod

# Start workers manually (from media-server directory)
dramatiq services.task.consumers --processes 2 --threads 2
```

**Testing:**
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_service_name.py

# Run with coverage
pytest --cov=services tests/
```

### Frontend (Media Client)

**Setup and Dependencies:**
```bash
cd media-client
flutter pub get
```

**Development:**
```bash
# Run in development mode
flutter run

# Run on specific platform
flutter run -d web-server --web-port 5200  #目前只是用这个启动命令
flutter run -d chrome
flutter run -d windows
flutter run -d android
flutter run -d ios

# Analyze code
flutter analyze

# Run tests
flutter test
```

### Infrastructure

**Docker Services:**
```bash
# Start PostgreSQL and Redis
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f
```

## Architecture Overview

### Backend Architecture

The server follows a **layered service architecture**:

- **`api/`** - FastAPI route definitions organized by feature
- **`core/`** - Infrastructure components (database, config, auth, logging)
- **`services/`** - Business logic layer with domain-specific services
- **`models/`** - SQLModel database schemas (e.g `media_models.py`)
- **`schemas/`** - Pydantic request/response models

### Key Service Patterns

**Async/Await Throughout**: All services use async patterns for performance(include postgresql session):
```python
async def scan_media_library(user_id: str, path: str):
    async with database.transaction():
        # Process files asynchronously
        await process_batch(files)
```

**User Isolation**: All database operations are scoped by `user_id` for multi-tenancy.

**Task-Based Processing**: Heavy operations use Dramatiq workers:
- `scan` - File system scanning and discovery
- `metadata` - External metadata enrichment (TMDB, Douban)
- `persist` - Database persistence operations
- `delete` - Cleanup and orphaned file removal
- `localize` - Artwork download and localization

### Frontend Architecture

The Flutter client uses **state management with Riverpod** and **feature-based organization**:

- **`core/`** - Shared utilities, API client, routing
- **`media_library/`** - Media browsing, search, and detail views
- **`source_library/`** - Storage source management
- **`media_player/`** - Video playback using MediaKit
- **`profile/`** - User settings and authentication

**Navigation**: Uses GoRouter for declarative routing with nested routes.

### Database Design

**Unified Media Model**: Uses a flexible media entity system:
- `media_core` - Base entity for movies, series, episodes
- `media_version` - Multiple quality variants per title
- `file_assets` - Physical file mappings with storage abstraction
- `artwork` - Posters, banners, thumbnails with localization support
- `credits` - Cast and crew with role information

**Hierarchical Structure**: Series → Seasons → Episodes with proper foreign key relationships.

## Key Development Patterns

### Error Handling

Backend uses comprehensive error handling with HTTP status codes:
```python
from fastapi import HTTPException

if not media_item:
    raise HTTPException(status_code=404, detail="Media not found")
```

### Background Tasks

Use Dramatiq decorators for async task processing:
```python
import dramatiq

@dramatiq.actor(queue_name="metadata")
def enrich_metadata(media_id: str, source: str):
    # Enrich media with external metadata
    pass
```

### Database Transactions

Always use transactions for multi-table operations:
```python
async with database.transaction():
    # Multiple related operations
    await create_media_core(data)
    await create_file_assets(files)
```

### API Patterns

**Pagination**: Use `skip` and `limit` parameters for list endpoints.
**Filtering**: Support flexible filtering with query parameters.
**Validation**: Use Pydantic models for request/response validation.

### Frontend State Management

Use Riverpod providers for state management:
```dart
final mediaProvider = FutureProvider.family<Media, String>((ref, id) async {
  return await apiClient.getMedia(id);
});
```

## Testing Guidelines

### Backend Testing

- **Unit Tests**: Test individual service methods
- **Integration Tests**: Test API endpoints with database
- **Fixtures**: Use pytest fixtures for test data setup
- **Mock External Services**: Mock TMDB/Douban API calls

### Frontend Testing

- **Widget Tests**: Test individual UI components
- **Integration Tests**: Test complete user flows
- **Mock Services**: Use mock API clients for testing

## Configuration

### Environment Variables

Backend configuration uses Pydantic Settings:
- Database: `DATABASE_URL` (default: PostgreSQL localhost)
- Redis: `REDIS_URL` (default: localhost:6379)
- JWT: `SECRET_KEY` for authentication
- API Keys: TMDB, Douban API keys for scraping

### Database Configuration

Database connection configured in `alembic.ini` and environment variables. The system uses PostgreSQL with async connection pooling.

## Common Development Tasks

### Adding New API Endpoint

1. Define Pydantic schemas in `schemas/`
2. Add route in `api/` with proper HTTP methods
3. Implement business logic in `services/`
4. Add database operations in appropriate service
5. Write tests in `tests/`

### Adding New Background Task

1. Define task function in `services/task/`
2. Add Dramatiq actor decorator with appropriate queue
3. Register task in consumer if needed
4. Call task from API endpoints or other services

### Adding New Frontend Feature

1. Create model classes in appropriate feature directory
2. Add API client methods
3. Create Riverpod providers for state management
4. Build UI components following existing patterns
5. Add routes in GoRouter configuration

### Database Migration

1. Modify models in `models/media_models.py`
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Review generated migration in `alembic/versions/`
4. Apply migration: `alembic upgrade head`

## Performance Considerations

- **Async Operations**: Always use async/await for I/O operations
- **Batch Processing**: Process items in batches to reduce database calls
- **Caching**: Use Redis for frequently accessed data
- **Connection Pooling**: Database connections are pooled automatically
- **Lazy Loading**: Frontend uses lazy loading for large media lists