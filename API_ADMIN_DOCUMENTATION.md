# OrbitLLM Admin API Documentation

API endpoints for managing the knowledge base content. All endpoints require authentication via API key.

## Authentication

All admin endpoints require the `X-Admin-Key` header with a valid API key.

```bash
curl -H "X-Admin-Key: your-api-key" https://your-api.com/admin/series
```

### Error Responses

| Status Code | Description |
|-------------|-------------|
| `401 Unauthorized` | Missing `X-Admin-Key` header |
| `403 Forbidden` | Invalid API key |
| `503 Service Unavailable` | Admin endpoints disabled (ADMIN_API_KEY not configured) |

---

## Series Management

### List All Series

Returns a list of all series (folders) in the knowledge base.

**Endpoint:** `GET /admin/series`

**Response:**
```json
{
  "series": [
    {"name": "FLEX-C", "file_count": 14},
    {"name": "TITAN", "file_count": 23},
    {"name": "GOLD", "file_count": 25}
  ],
  "total_series": 3
}
```

**Example:**
```bash
curl -X GET \
  -H "X-Admin-Key: your-api-key" \
  https://your-api.com/admin/series
```

---

### Create Series

Creates a new series (folder) in the knowledge base.

**Endpoint:** `POST /admin/series`

**Request Body:**
```json
{
  "name": "NEW-SERIES"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Series name (alphanumeric, hyphens, underscores only) |

**Response:**
```json
{
  "message": "Series 'NEW-SERIES' created successfully",
  "name": "NEW-SERIES"
}
```

**Error Responses:**
| Status | Description |
|--------|-------------|
| `400 Bad Request` | Invalid series name |
| `409 Conflict` | Series already exists |

**Example:**
```bash
curl -X POST \
  -H "X-Admin-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "NUEVA-SERIE"}' \
  https://your-api.com/admin/series
```

---

### Delete Series

Deletes a series and all its files from the knowledge base.

**Endpoint:** `DELETE /admin/series/{series_name}`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `series_name` | string | Name of the series to delete |

**Response:**
```json
{
  "message": "Series 'FLEX-C' deleted",
  "name": "FLEX-C",
  "files_deleted": 14
}
```

**Error Responses:**
| Status | Description |
|--------|-------------|
| `404 Not Found` | Series does not exist |

**Example:**
```bash
curl -X DELETE \
  -H "X-Admin-Key: your-api-key" \
  https://your-api.com/admin/series/FLEX-C
```

---

## File Management

### List Files in Series

Returns all markdown files in a specific series.

**Endpoint:** `GET /admin/series/{series_name}/files`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `series_name` | string | Name of the series |

**Response:**
```json
{
  "series": "FLEX-C",
  "files": [
    {
      "name": "AFLEX-C-12-ESP.md",
      "size": 8012,
      "last_modified": "2024-12-02T22:32:00"
    },
    {
      "name": "AFLEX-C-MANUAL-USUARIO-ES.md",
      "size": 49463,
      "last_modified": "2024-12-02T22:35:00"
    }
  ],
  "total_files": 2
}
```

**Error Responses:**
| Status | Description |
|--------|-------------|
| `404 Not Found` | Series does not exist |

**Example:**
```bash
curl -X GET \
  -H "X-Admin-Key: your-api-key" \
  https://your-api.com/admin/series/FLEX-C/files
```

---

### Upload File (PDF)

Uploads a PDF file to a series. The PDF is automatically converted to Markdown using Azure Document Intelligence (OCR) before being stored.

**Endpoint:** `POST /admin/series/{series_name}/files`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `series_name` | string | Name of the series |

**Request:** `multipart/form-data`
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | PDF file (.pdf) to upload. Will be converted to Markdown automatically. |

**Response:**
```json
{
  "message": "PDF 'manual.pdf' converted and saved as 'manual.md'",
  "series": "FLEX-C",
  "filename": "manual.md",
  "size": 5432
}
```

**Error Responses:**
| Status | Description |
|--------|-------------|
| `400 Bad Request` | Invalid file (not .pdf or invalid PDF format) |
| `404 Not Found` | Series does not exist |
| `503 Service Unavailable` | Azure Document Intelligence not configured |

**Example:**
```bash
curl -X POST \
  -H "X-Admin-Key: your-api-key" \
  -F "file=@/path/to/document.pdf" \
  https://your-api.com/admin/series/FLEX-C/files
```

**Note:** The PDF conversion may take 10-30 seconds depending on the document size and complexity.

---

### Get File Content

Retrieves the content of a specific file.

**Endpoint:** `GET /admin/series/{series_name}/files/{filename}`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `series_name` | string | Name of the series |
| `filename` | string | Name of the file |

**Response:**
```json
{
  "series": "FLEX-C",
  "filename": "AFLEX-C-12-ESP.md",
  "content": "# AFLEX-C-12\n\nEspecificaciones técnicas..."
}
```

**Error Responses:**
| Status | Description |
|--------|-------------|
| `400 Bad Request` | File is not a .md file |
| `404 Not Found` | File or series does not exist |

**Example:**
```bash
curl -X GET \
  -H "X-Admin-Key: your-api-key" \
  https://your-api.com/admin/series/FLEX-C/files/AFLEX-C-12-ESP.md
```

---

### Update File

Updates an existing file in a series.

**Endpoint:** `PUT /admin/series/{series_name}/files/{filename}`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `series_name` | string | Name of the series |
| `filename` | string | Name of the file to update |

**Request:** `multipart/form-data`
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | New content for the file (.md) |

**Response:**
```json
{
  "message": "File 'AFLEX-C-12-ESP.md' updated successfully",
  "series": "FLEX-C",
  "filename": "AFLEX-C-12-ESP.md",
  "size": 8500
}
```

**Error Responses:**
| Status | Description |
|--------|-------------|
| `400 Bad Request` | Invalid file (not .md or invalid UTF-8) |
| `404 Not Found` | File or series does not exist |

**Example:**
```bash
curl -X PUT \
  -H "X-Admin-Key: your-api-key" \
  -F "file=@/path/to/updated-document.md" \
  https://your-api.com/admin/series/FLEX-C/files/AFLEX-C-12-ESP.md
```

---

### Delete File

Deletes a file from a series.

**Endpoint:** `DELETE /admin/series/{series_name}/files/{filename}`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `series_name` | string | Name of the series |
| `filename` | string | Name of the file to delete |

**Response:**
```json
{
  "message": "File 'old-document.md' deleted",
  "series": "FLEX-C",
  "filename": "old-document.md"
}
```

**Error Responses:**
| Status | Description |
|--------|-------------|
| `400 Bad Request` | File is not a .md file |
| `404 Not Found` | File or series does not exist |

**Example:**
```bash
curl -X DELETE \
  -H "X-Admin-Key: your-api-key" \
  https://your-api.com/admin/series/FLEX-C/files/old-document.md
```

---

### Move File

Moves a file from one series to another. Useful when a file was uploaded to the wrong series.

**Endpoint:** `PATCH /admin/series/{series_name}/files/{filename}/move`

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `series_name` | string | Name of the source series |
| `filename` | string | Name of the file to move |

**Request Body:**
```json
{
  "target_series": "TITAN"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `target_series` | string | Yes | Name of the destination series |

**Response:**
```json
{
  "message": "File 'manual.md' moved from 'FLEX-C' to 'TITAN'",
  "filename": "manual.md",
  "source_series": "FLEX-C",
  "target_series": "TITAN"
}
```

**Error Responses:**
| Status | Description |
|--------|-------------|
| `400 Bad Request` | Invalid filename, target series name, or same source/target |
| `404 Not Found` | Source file or target series does not exist |
| `409 Conflict` | File already exists in target series |

**Example:**
```bash
curl -X PATCH \
  -H "X-Admin-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"target_series": "TITAN"}' \
  https://your-api.com/admin/series/FLEX-C/files/manual.md/move
```

---

## Knowledge Base Operations

### Reingest Knowledge Base

Re-ingests all content from the knowledge base after making changes. This rebuilds all shards and updates the cache.

**Important:** Call this endpoint after uploading, updating, or deleting files to make changes effective in the RAG system.

**Endpoint:** `POST /admin/reingest`

**Response:**
```json
{
  "message": "Knowledge base reingested successfully",
  "shards_created": 21,
  "total_files": 217,
  "total_tokens": 1075234
}
```

**Error Responses:**
| Status | Description |
|--------|-------------|
| `500 Internal Server Error` | Ingestion failed |

**Example:**
```bash
curl -X POST \
  -H "X-Admin-Key: your-api-key" \
  https://your-api.com/admin/reingest
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ADMIN_API_KEY` | Yes | - | API key for admin authentication |
| `AZURE_STORAGE_CONNECTION_STRING` | No | - | Azure Blob Storage connection string |
| `AZURE_STORAGE_CONTAINER_NAME` | No | `knowledge-base` | Azure Blob container name |
| `AZURE_DOCINTEL_ENDPOINT` | Yes* | - | Azure Document Intelligence endpoint URL |
| `AZURE_DOCINTEL_API_KEY` | Yes* | - | Azure Document Intelligence API key |

*Required for PDF upload functionality. Without these, file uploads will be disabled.

### Storage Modes

The API supports two storage modes:

1. **Azure Blob Storage** (recommended for production)
   - Set `AZURE_STORAGE_CONNECTION_STRING`
   - Files stored in Azure Blob container
   - Survives container restarts/redeployments

2. **Local Filesystem** (fallback)
   - Used when Azure Blob is not configured
   - Files stored in `./knowledge_base/` directory
   - Suitable for development/testing

---

## Typical Workflow

1. **Create a new series:**
   ```bash
   POST /admin/series
   {"name": "NEW-PRODUCT"}
   ```

2. **Upload documentation files:**
   ```bash
   POST /admin/series/NEW-PRODUCT/files
   # Upload each .md file
   ```

3. **Reingest to apply changes:**
   ```bash
   POST /admin/reingest
   ```

4. **Verify the series is available:**
   ```bash
   GET /admin/series
   ```

---

## OpenAPI Documentation

Interactive API documentation is available at:
- Swagger UI: `https://your-api.com/docs`
- ReDoc: `https://your-api.com/redoc`
