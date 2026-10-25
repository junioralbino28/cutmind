-- Os modelos publicados no mural e as denúncias. Migrações daqui para frente só ACRESCENTAM.
CREATE TABLE modelos (
  id TEXT PRIMARY KEY,               -- 12 letras aleatórias (o link: /m/<id>)
  nome TEXT NOT NULL,                -- o nome que a pessoa deu ao publicar
  autor TEXT,                        -- o @ dela, sem o @ (opcional)
  post TEXT,                         -- o link do post em que ela usou o modelo (opcional)
  plataforma TEXT,                   -- instagram, tiktok ou youtube (a do post)
  modelo TEXT NOT NULL,              -- o modelo conferido (JSON), sem foto, vídeo nem música
  criado INTEGER NOT NULL,           -- segundos desde 1970
  status TEXT NOT NULL DEFAULT 'publicado',  -- publicado ou removido
  denuncias INTEGER NOT NULL DEFAULT 0,
  ip_hash TEXT NOT NULL              -- sha-256 do IP com sal: conta o limite por dia sem guardar o IP
);
CREATE INDEX modelos_mural ON modelos (status, criado DESC);
CREATE INDEX modelos_ip ON modelos (ip_hash, criado);

CREATE TABLE denuncias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  modelo_id TEXT NOT NULL REFERENCES modelos (id),
  motivo TEXT NOT NULL,
  criado INTEGER NOT NULL,
  ip_hash TEXT NOT NULL,
  UNIQUE (modelo_id, ip_hash)        -- uma denúncia por pessoa em cada modelo
);
CREATE INDEX denuncias_ip ON denuncias (ip_hash, criado);
