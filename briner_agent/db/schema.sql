-- db/schema.sql
-- Tabla principal para registrar el estado y metadatos de los archivos del workspace
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL UNIQUE,
    extension TEXT,
    size_bytes INTEGER,
    status TEXT DEFAULT 'pending', -- Estados: pending, processed, error
    last_modified TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla para mantener un registro de auditoría/logs de las acciones tomadas por la IA
CREATE TABLE IF NOT EXISTS actions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    action_type TEXT NOT NULL, -- Ejemplos: 'categorize', 'move', 'extract_data'
    description TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);
