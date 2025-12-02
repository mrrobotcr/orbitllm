# API Documentation - Azure Endpoints

Esta documentación describe los endpoints de Azure OpenAI disponibles en el sistema de RAG con Semantic Sharding y Agentic Routing.

## Arquitectura

El sistema utiliza:
- **Semantic Sharding**: Los documentos se agrupan por Serie (AFLEX, VIRTUS, GOLD, etc.) antes de crear shards de ~100k tokens.
- **Agentic Routing**: Un LLM analiza la pregunta del usuario y selecciona solo los shards relevantes.
- **Conversational Memory**: El sistema mantiene historial de sesión para preguntas contextuales.
- **Source Citation**: Cada respuesta incluye las fuentes (documentos y páginas) consultadas.

---

## Endpoints

### 1. POST `/ingest/azure`

Ingesta la base de conocimientos desde el directorio `./knowledge_base` y crea shards en memoria.

#### Request

**URL**: `http://localhost:8000/ingest/azure`  
**Method**: `POST`  
**Headers**: Ninguno requerido  
**Body**: Ninguno

#### Response

```json
{
  "message": "Knowledge base ingested for Azure successfully.",
  "cache_names": ["azure_shard_0", "azure_shard_1", "..."],
  "document_count": 216,
  "total_chars": 15234567,
  "total_tokens": 3500000,
  "shards_created": 22
}
```

#### Campos de Respuesta

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `message` | `string` | Mensaje de confirmación |
| `cache_names` | `string[]` | Nombres virtuales de los shards creados |
| `document_count` | `int` | Total de archivos `.md` procesados |
| `total_chars` | `int` | Total de caracteres procesados |
| `total_tokens` | `int` | Total de tokens procesados |
| `shards_created` | `int` | Número de shards creados (uno o más por serie) |

#### Ejemplo de Uso

```bash
curl -X POST http://localhost:8000/ingest/azure
```

#### Notas Importantes

- Los archivos deben estar en formato Markdown (`.md`) en el directorio `./knowledge_base/`.
- Los archivos se agrupan automáticamente por Serie usando prefijos en sus nombres (ej. `AFLEX-`, `VIRTUS-`, `AGO-T-`).
- Archivos que no coinciden con ninguna serie conocida se clasifican como `OTHER`.
- Cada shard respeta el límite de ~100k tokens para optimizar el uso del TPM quota (2M tokens/min).

#### Logs Generados

Durante la ingesta, el sistema genera logs como:

```
INFO - Processing Series: FLEX (36 files)
INFO - Processing Series: VIRTUS (11 files)
WARNING - File 'MANUAL-GENERICO.md' categorized as OTHER
INFO - Azure ingestion complete. 22 shards created.
```

---

### 2. POST `/ask/azure`

Responde preguntas del usuario utilizando el conocimiento ingestado.

#### Request

**URL**: `http://localhost:8000/ask/azure`  
**Method**: `POST`  
**Headers**: `Content-Type: application/json`  
**Body**:

```json
{
  "question": "¿Qué refrigerante usa la serie AFLEX-C?",
  "session_id": "user123"
}
```

#### Campos de Request

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `question` | `string` | ✅ Sí | Pregunta del usuario |
| `session_id` | `string` | ❌ No | ID de sesión para conversaciones multi-turno (default: `"default"`) |

#### Response

```json
{
  "answer": "Los modelos de la serie AFLEX-C utilizan refrigerante R-410A...",
  "sources": [
    {
      "file": "AFLEX-C-18-ESP.pdf",
      "detail": [
        "AFLEX-C-18-ESP. - Página 1",
        "AFLEX-C-18-ESP. - Página 3"
      ]
    },
    {
      "file": "AFLEX-C-36-RTCA-A.pdf",
      "detail": [
        "AFLEX-C-36-RTCA-A - Página 1"
      ]
    }
  ]
}
```

#### Campos de Response

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `answer` | `string` | Respuesta sintetizada del sistema |
| `sources` | `SourceItem[]` | Lista de fuentes consultadas |
| `sources[].file` | `string` | Nombre del documento con extensión `.pdf` |
| `sources[].detail` | `string[]` | Lista de referencias específicas (ej. "Documento - Página X") |

#### Ejemplo de Uso

**Pregunta Simple**:
```bash
curl -X POST http://localhost:8000/ask/azure \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Cuál es la capacidad de enfriamiento del AFLEX-C-24?"}'
```

**Conversación Multi-Turno**:
```bash
# Turno 1: Pregunta ambigua
curl -X POST http://localhost:8000/ask/azure \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test1", "question": "¿Qué significa el error E9?"}'

# Respuesta: "Para poder ayudarte mejor, ¿podrías especificar la Serie o el Modelo de tu equipo?"

# Turno 2: Usuario proporciona contexto
curl -X POST http://localhost:8000/ask/azure \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test1", "question": "Serie AFLEX-C"}'

# Respuesta: "El error E9 en la serie AFLEX-C indica..."
```


## Ejemplo Completo de Flujo

```bash
# 1. Ingestar la base de conocimientos
curl -X POST http://localhost:8000/ingest/azure

# Respuesta:
# {
#   "message": "Knowledge base ingested for Azure successfully.",
#   "shards_created": 22,
#   ...
# }

# 2. Hacer una pregunta
curl -X POST http://localhost:8000/ask/azure \
  -H "Content-Type: application/json" \
  -d '{
    "question": "¿Qué tipo de compresor usa la serie AFLEX-C?",
    "session_id": "user456"
  }'

# Respuesta:
# {
#   "answer": "La serie AFLEX-C utiliza compresores rotativos tipo scroll...",
#   "sources": [
#     {
#       "file": "AFLEX-C-18-ESP.pdf",
#       "detail": ["AFLEX-C-18-ESP. - Página 2"]
#     }
#   ]
# }
```

---

## Soporte

Para reportar problemas o solicitar mejoras, contactar al equipo de desarrollo.
