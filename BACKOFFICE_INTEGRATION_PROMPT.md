# Prompt: Integración del Módulo de Administración de Knowledge Base

## Contexto

Necesito implementar un módulo de administración en el backoffice existente para gestionar la base de conocimiento (knowledge base) de OrbitLLM. Este módulo permitirá a los administradores crear, editar y eliminar series (carpetas) y archivos markdown que alimentan el sistema RAG.

## API Base URL

```
Production: https://[tu-dominio]/admin
Development: http://localhost:8000/admin
```

## Autenticación

### Requisito Crítico

Todos los endpoints de admin requieren autenticación mediante API Key en el header `X-Admin-Key`. El módulo debe:

1. **Pantalla de Configuración/Login de Admin:**
   - Mostrar un input para que el usuario ingrese el API Key
   - Botón "Conectar" o "Autenticar"
   - Validar el API Key haciendo una petición de prueba a `GET /admin/series`
   - Si es válido, guardar el API Key en la sesión (sessionStorage o estado global)
   - Si es inválido, mostrar error "API Key inválida"

2. **Persistencia del API Key:**
   - Guardar en `sessionStorage` (se pierde al cerrar pestaña) - RECOMENDADO por seguridad
   - Alternativamente en estado global (Redux, Zustand, Context)
   - NUNCA guardar en `localStorage` por seguridad

3. **Uso en Peticiones:**
   - Todas las peticiones al módulo admin deben incluir:
   ```javascript
   headers: {
     'X-Admin-Key': sessionStorage.getItem('adminApiKey'),
     'Content-Type': 'application/json' // o 'multipart/form-data' para uploads
   }
   ```

4. **Manejo de Errores de Autenticación:**
   - `401 Unauthorized`: Mostrar "API Key no proporcionada"
   - `403 Forbidden`: Mostrar "API Key inválida"
   - `503 Service Unavailable`: Mostrar "Endpoints de admin deshabilitados en el servidor"
   - En cualquier caso de error auth, redirigir a pantalla de configuración

---

## Estructura del Módulo

### 1. Pantalla Principal - Dashboard

Mostrar resumen de la knowledge base:
- Total de series
- Total de archivos
- Botón "Reingestar" (para aplicar cambios)

### 2. Pantalla de Series

#### 2.1 Lista de Series
- Tabla/Grid con todas las series
- Columnas: Nombre, Cantidad de archivos, Acciones
- Acciones por fila: Ver archivos, Eliminar

**Endpoint:** `GET /admin/series`

```javascript
// Request
fetch(`${API_URL}/admin/series`, {
  method: 'GET',
  headers: {
    'X-Admin-Key': sessionStorage.getItem('adminApiKey')
  }
})

// Response
{
  "series": [
    {"name": "FLEX-C", "file_count": 14},
    {"name": "TITAN", "file_count": 23}
  ],
  "total_series": 2
}
```

#### 2.2 Crear Nueva Serie
- Modal o formulario con input para nombre
- Validar: solo letras, números, guiones y guiones bajos
- El nombre se convierte automáticamente a MAYÚSCULAS

**Endpoint:** `POST /admin/series`

```javascript
// Request
fetch(`${API_URL}/admin/series`, {
  method: 'POST',
  headers: {
    'X-Admin-Key': sessionStorage.getItem('adminApiKey'),
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ name: 'NUEVA-SERIE' })
})

// Response (201)
{
  "message": "Series 'NUEVA-SERIE' created successfully",
  "name": "NUEVA-SERIE"
}

// Error (409 - ya existe)
{
  "detail": "Series 'NUEVA-SERIE' already exists"
}
```

#### 2.3 Eliminar Serie
- Confirmación antes de eliminar: "¿Estás seguro? Se eliminarán X archivos"
- Mostrar spinner durante la operación

**Endpoint:** `DELETE /admin/series/{series_name}`

```javascript
// Request
fetch(`${API_URL}/admin/series/FLEX-C`, {
  method: 'DELETE',
  headers: {
    'X-Admin-Key': sessionStorage.getItem('adminApiKey')
  }
})

// Response
{
  "message": "Series 'FLEX-C' deleted",
  "name": "FLEX-C",
  "files_deleted": 14
}
```

---

### 3. Pantalla de Archivos de una Serie

#### 3.1 Lista de Archivos
- Breadcrumb: Series > {nombre_serie}
- Tabla con archivos de la serie seleccionada
- Columnas: Nombre, Tamaño, Última modificación, Acciones
- Acciones: Ver/Editar, Eliminar
- Botón "Subir archivo"

**Endpoint:** `GET /admin/series/{series_name}/files`

```javascript
// Request
fetch(`${API_URL}/admin/series/FLEX-C/files`, {
  method: 'GET',
  headers: {
    'X-Admin-Key': sessionStorage.getItem('adminApiKey')
  }
})

// Response
{
  "series": "FLEX-C",
  "files": [
    {
      "name": "AFLEX-C-12-ESP.md",
      "size": 8012,
      "last_modified": "2024-12-02T22:32:00"
    }
  ],
  "total_files": 1
}
```

#### 3.2 Subir Archivo (PDF)
- Drag & drop o selector de archivos
- **Solo permitir archivos `.pdf`** (se convierten automáticamente a Markdown)
- Mostrar progreso de subida y mensaje de "Procesando PDF..."
- **IMPORTANTE:** La conversión puede tomar 10-30 segundos dependiendo del tamaño del PDF

**Endpoint:** `POST /admin/series/{series_name}/files`

```javascript
// Request
const formData = new FormData();
formData.append('file', fileInput.files[0]); // Solo archivos .pdf

fetch(`${API_URL}/admin/series/FLEX-C/files`, {
  method: 'POST',
  headers: {
    'X-Admin-Key': sessionStorage.getItem('adminApiKey')
    // NO incluir Content-Type, el browser lo setea automáticamente con boundary
  },
  body: formData
})

// Response
{
  "message": "PDF 'manual-tecnico.pdf' converted and saved as 'manual-tecnico.md'",
  "series": "FLEX-C",
  "filename": "manual-tecnico.md",
  "size": 15432
}

// Error (503 - Document Intelligence no configurado)
{
  "detail": "PDF processing is not available. Azure Document Intelligence is not configured."
}
```

**Notas de UX:**
- Mostrar un spinner o barra de progreso durante la conversión
- Informar al usuario que el PDF está siendo procesado por OCR
- El nombre del archivo resultante será el mismo pero con extensión `.md`

#### 3.3 Ver/Editar Archivo
- Modal o página con editor de markdown
- Mostrar preview del markdown renderizado (opcional)
- Botón "Guardar cambios"

**Obtener contenido:** `GET /admin/series/{series_name}/files/{filename}`

```javascript
// Request
fetch(`${API_URL}/admin/series/FLEX-C/files/AFLEX-C-12-ESP.md`, {
  method: 'GET',
  headers: {
    'X-Admin-Key': sessionStorage.getItem('adminApiKey')
  }
})

// Response
{
  "series": "FLEX-C",
  "filename": "AFLEX-C-12-ESP.md",
  "content": "# AFLEX-C-12\n\nEspecificaciones técnicas..."
}
```

**Actualizar archivo:** `PUT /admin/series/{series_name}/files/{filename}`

```javascript
// Request
const blob = new Blob([editorContent], { type: 'text/markdown' });
const formData = new FormData();
formData.append('file', blob, 'AFLEX-C-12-ESP.md');

fetch(`${API_URL}/admin/series/FLEX-C/files/AFLEX-C-12-ESP.md`, {
  method: 'PUT',
  headers: {
    'X-Admin-Key': sessionStorage.getItem('adminApiKey')
  },
  body: formData
})

// Response
{
  "message": "File 'AFLEX-C-12-ESP.md' updated successfully",
  "series": "FLEX-C",
  "filename": "AFLEX-C-12-ESP.md",
  "size": 8500
}
```

#### 3.4 Eliminar Archivo
- Confirmación antes de eliminar

**Endpoint:** `DELETE /admin/series/{series_name}/files/{filename}`

```javascript
// Request
fetch(`${API_URL}/admin/series/FLEX-C/files/AFLEX-C-12-ESP.md`, {
  method: 'DELETE',
  headers: {
    'X-Admin-Key': sessionStorage.getItem('adminApiKey')
  }
})

// Response
{
  "message": "File 'AFLEX-C-12-ESP.md' deleted",
  "series": "FLEX-C",
  "filename": "AFLEX-C-12-ESP.md"
}
```

---

### 4. Reingestar Knowledge Base

**IMPORTANTE:** Después de cualquier cambio (crear/editar/eliminar archivos), el usuario debe ejecutar "Reingestar" para que los cambios se reflejen en el sistema RAG.

- Botón prominente en el dashboard o navbar
- Mostrar spinner/progreso durante la operación (puede tomar 10-30 segundos)
- Mostrar resultado: shards creados, archivos procesados, tokens totales

**Endpoint:** `POST /admin/reingest`

```javascript
// Request
fetch(`${API_URL}/admin/reingest`, {
  method: 'POST',
  headers: {
    'X-Admin-Key': sessionStorage.getItem('adminApiKey')
  }
})

// Response
{
  "message": "Knowledge base reingested successfully",
  "shards_created": 21,
  "total_files": 217,
  "total_tokens": 1075234
}
```

---

## Flujo de Usuario Típico

```
1. Usuario accede al módulo de admin
   └── Si no hay API Key en sesión → Mostrar pantalla de configuración

2. Usuario ingresa API Key
   └── Validar con GET /admin/series
       ├── Éxito → Guardar en sessionStorage, ir a Dashboard
       └── Error → Mostrar mensaje de error

3. Dashboard muestra resumen
   └── Usuario puede:
       ├── Ver lista de series
       ├── Crear nueva serie
       └── Reingestar

4. Usuario selecciona una serie
   └── Ver lista de archivos
       ├── Subir nuevo archivo
       ├── Editar archivo existente
       └── Eliminar archivo

5. Después de cambios
   └── Usuario hace clic en "Reingestar"
       └── Sistema procesa y actualiza la knowledge base
```

---

## Componentes UI Sugeridos

### Configuración/Login Admin
```
┌─────────────────────────────────────────┐
│         Configuración de Admin          │
├─────────────────────────────────────────┤
│                                         │
│  API Key de Administrador:              │
│  ┌─────────────────────────────────┐    │
│  │ ********************************│    │
│  └─────────────────────────────────┘    │
│                                         │
│  [      Conectar      ]                 │
│                                         │
│  ⚠️ Error: API Key inválida             │
│                                         │
└─────────────────────────────────────────┘
```

### Dashboard
```
┌─────────────────────────────────────────┐
│  Knowledge Base Admin    [Reingestar]   │
├─────────────────────────────────────────┤
│                                         │
│  📊 Resumen                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐│
│  │ 18       │ │ 217      │ │ 1.07M    ││
│  │ Series   │ │ Archivos │ │ Tokens   ││
│  └──────────┘ └──────────┘ └──────────┘│
│                                         │
│  [+ Nueva Serie]                        │
│                                         │
│  ┌─────────────────────────────────────┐│
│  │ Serie      │ Archivos │ Acciones   ││
│  ├─────────────────────────────────────┤│
│  │ FLEX-C     │ 14       │ 👁️ 🗑️      ││
│  │ TITAN      │ 23       │ 👁️ 🗑️      ││
│  │ GOLD       │ 25       │ 👁️ 🗑️      ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘
```

### Lista de Archivos
```
┌─────────────────────────────────────────┐
│  Series > FLEX-C           [+ Subir]    │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────────────────────────────┐│
│  │ Archivo           │ Tamaño │ Acc.  ││
│  ├─────────────────────────────────────┤│
│  │ AFLEX-C-12-ESP.md │ 7.8 KB │ ✏️ 🗑️ ││
│  │ AFLEX-C-MANUAL.md │ 48 KB  │ ✏️ 🗑️ ││
│  └─────────────────────────────────────┘│
└─────────────────────────────────────────┘
```

---

## Manejo de Errores

| Código | Significado | Acción UI |
|--------|-------------|-----------|
| 400 | Bad Request | Mostrar mensaje del campo `detail` (ej: "Only PDF files are allowed") |
| 401 | No autenticado | Redirigir a pantalla de configuración |
| 403 | API Key inválida | Limpiar sesión, redirigir a configuración |
| 404 | No encontrado | Mostrar "Serie/Archivo no encontrado" |
| 409 | Conflicto | Mostrar "Ya existe" |
| 500 | Error servidor | Mostrar "Error del servidor, intente más tarde" |
| 503 | Servicio no disponible | Mostrar "Admin deshabilitado" o "Procesamiento PDF no disponible" |

---

## Consideraciones de Seguridad

1. **Nunca exponer el API Key en logs o URLs**
2. **Usar HTTPS en producción**
3. **Limpiar sessionStorage al hacer logout**
4. **No mostrar el API Key en texto plano después de ingresarlo (usar type="password")**
5. **Implementar timeout de sesión (opcional)**

---

## Tecnologías Recomendadas

- **React/Vue/Angular** - Framework frontend
- **Axios o Fetch API** - HTTP client
- **React Query/SWR** - Cache y estado de servidor (opcional)
- **Monaco Editor o CodeMirror** - Editor de markdown (opcional)
- **react-markdown** - Preview de markdown (opcional)

---

## Ejemplo de Hook/Service (React)

```javascript
// useAdminApi.js
import { useState, useCallback } from 'react';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export function useAdminApi() {
  const getApiKey = () => sessionStorage.getItem('adminApiKey');

  const setApiKey = (key) => sessionStorage.setItem('adminApiKey', key);

  const clearApiKey = () => sessionStorage.removeItem('adminApiKey');

  const isAuthenticated = () => !!getApiKey();

  const request = useCallback(async (endpoint, options = {}) => {
    const apiKey = getApiKey();
    if (!apiKey) throw new Error('No API key configured');

    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers: {
        'X-Admin-Key': apiKey,
        ...options.headers,
      },
    });

    if (response.status === 401 || response.status === 403) {
      clearApiKey();
      throw new Error('Authentication failed');
    }

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }, []);

  const validateApiKey = async (key) => {
    const response = await fetch(`${API_URL}/admin/series`, {
      headers: { 'X-Admin-Key': key }
    });
    return response.ok;
  };

  return {
    request,
    getApiKey,
    setApiKey,
    clearApiKey,
    isAuthenticated,
    validateApiKey,
  };
}
```

---

## Checklist de Implementación

- [ ] Pantalla de configuración con input de API Key
- [ ] Validación de API Key al conectar
- [ ] Persistencia de API Key en sessionStorage
- [ ] Dashboard con resumen
- [ ] Lista de series con CRUD
- [ ] Lista de archivos por serie
- [ ] Subida de archivos PDF (drag & drop) con indicador de procesamiento
- [ ] Manejo de tiempos largos de conversión (10-30 segundos)
- [ ] Editor de archivos markdown (para archivos convertidos)
- [ ] Eliminación con confirmación
- [ ] Botón de reingestar
- [ ] Manejo de errores global (incluyendo 503 para Document Intelligence no disponible)
- [ ] Estados de carga (spinners)
- [ ] Mensajes de éxito/error (toasts)
