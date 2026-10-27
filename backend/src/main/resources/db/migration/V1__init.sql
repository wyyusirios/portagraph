-- PortaGraph: начальная схема БД (PostgreSQL 16 + pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(150) NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(120)  NOT NULL,
    description VARCHAR(2000),
    owner_id    BIGINT        NOT NULL REFERENCES users (id),
    status      VARCHAR(20)   NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE project_members (
    id         BIGSERIAL PRIMARY KEY,
    project_id BIGINT      NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    user_id    BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role       VARCHAR(20) NOT NULL CHECK (role IN ('OWNER', 'ARCHITECT', 'DEVELOPER', 'VIEWER')),
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, user_id)
);

CREATE TABLE repo_credentials (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT      NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    provider        VARCHAR(20) NOT NULL,
    encrypted_token BYTEA       NOT NULL,
    scopes          VARCHAR(300),
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE git_repositories (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT        NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    provider        VARCHAR(20)   NOT NULL CHECK (provider IN ('GITHUB', 'BITBUCKET', 'GITLAB', 'GITVERSE')),
    url             VARCHAR(500)  NOT NULL,
    name            VARCHAR(200)  NOT NULL,
    default_branch  VARCHAR(100)  NOT NULL DEFAULT 'main',
    credential_id   BIGINT        REFERENCES repo_credentials (id) ON DELETE SET NULL,
    detected_role   VARCHAR(20)   NOT NULL DEFAULT 'UNKNOWN',
    role_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    purpose_summary VARCHAR(2000),
    status          VARCHAR(20)   NOT NULL DEFAULT 'CONNECTED',
    last_commit_sha VARCHAR(64),
    last_synced_at  TIMESTAMPTZ,
    webhook_secret  VARCHAR(128),
    UNIQUE (project_id, url)
);

CREATE TABLE analysis_runs (
    id            BIGSERIAL PRIMARY KEY,
    project_id    BIGINT      NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    trigger_type  VARCHAR(20) NOT NULL CHECK (trigger_type IN ('MANUAL', 'WEBHOOK', 'SCHEDULE')),
    status        VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
    progress      INT         NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    error_message VARCHAR(2000),
    artifact_key  VARCHAR(300),
    stats         JSONB
);
CREATE INDEX ix_runs_project_status ON analysis_runs (project_id, status);

CREATE TABLE source_files (
    id            BIGSERIAL PRIMARY KEY,
    repository_id BIGINT        NOT NULL REFERENCES git_repositories (id) ON DELETE CASCADE,
    path          VARCHAR(1000) NOT NULL,
    language      VARCHAR(40),
    kind          VARCHAR(20)   NOT NULL,
    content_sha   VARCHAR(64)   NOT NULL,
    size_bytes    BIGINT        NOT NULL,
    storage_key   VARCHAR(300),
    updated_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    UNIQUE (repository_id, path)
);

CREATE TABLE code_chunks (
    id             BIGSERIAL PRIMARY KEY,
    source_file_id BIGINT NOT NULL REFERENCES source_files (id) ON DELETE CASCADE,
    start_line     INT    NOT NULL,
    end_line       INT    NOT NULL,
    symbol         VARCHAR(300),
    content        TEXT   NOT NULL,
    embedding      vector(1536),
    CHECK (end_line >= start_line)
);
CREATE INDEX ix_chunks_file ON code_chunks (source_file_id);
-- приближённый поиск ближайших соседей по косинусному расстоянию
CREATE INDEX ix_chunks_embedding ON code_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE graph_nodes (
    id             BIGSERIAL PRIMARY KEY,
    project_id     BIGINT        NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    run_id         BIGINT        NOT NULL REFERENCES analysis_runs (id) ON DELETE CASCADE,
    type           VARCHAR(30)   NOT NULL,
    name           VARCHAR(300)  NOT NULL,
    qualified_name VARCHAR(1000),
    repository_id  BIGINT        REFERENCES git_repositories (id) ON DELETE CASCADE,
    source_file_id BIGINT        REFERENCES source_files (id) ON DELETE SET NULL,
    parent_id      BIGINT        REFERENCES graph_nodes (id) ON DELETE CASCADE,
    description    VARCHAR(2000),
    confidence     DOUBLE PRECISION NOT NULL DEFAULT 1 CHECK (confidence BETWEEN 0 AND 1),
    verified       BOOLEAN       NOT NULL DEFAULT FALSE,
    metadata       JSONB
);
CREATE INDEX ix_nodes_run_type ON graph_nodes (run_id, type);

CREATE TABLE graph_edges (
    id             BIGSERIAL PRIMARY KEY,
    project_id     BIGINT      NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    run_id         BIGINT      NOT NULL REFERENCES analysis_runs (id) ON DELETE CASCADE,
    source_node_id BIGINT      NOT NULL REFERENCES graph_nodes (id) ON DELETE CASCADE,
    target_node_id BIGINT      NOT NULL REFERENCES graph_nodes (id) ON DELETE CASCADE,
    type           VARCHAR(20) NOT NULL,
    confidence     DOUBLE PRECISION NOT NULL DEFAULT 1 CHECK (confidence BETWEEN 0 AND 1),
    verified       BOOLEAN     NOT NULL DEFAULT FALSE,
    evidence       JSONB,
    CHECK (source_node_id <> target_node_id)
);
CREATE INDEX ix_edges_run ON graph_edges (run_id);
CREATE INDEX ix_edges_target ON graph_edges (target_node_id);

CREATE TABLE chat_sessions (
    id         BIGSERIAL PRIMARY KEY,
    project_id BIGINT       NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    user_id    BIGINT       NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title      VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
    id         BIGSERIAL PRIMARY KEY,
    session_id BIGINT      NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    role       VARCHAR(20) NOT NULL CHECK (role IN ('USER', 'ASSISTANT')),
    content    TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE citations (
    id             BIGSERIAL PRIMARY KEY,
    message_id     BIGINT NOT NULL REFERENCES chat_messages (id) ON DELETE CASCADE,
    source_file_id BIGINT NOT NULL REFERENCES source_files (id) ON DELETE CASCADE,
    start_line     INT    NOT NULL,
    end_line       INT    NOT NULL,
    node_id        BIGINT REFERENCES graph_nodes (id) ON DELETE SET NULL
);

CREATE TABLE impact_reports (
    id                 BIGSERIAL PRIMARY KEY,
    project_id         BIGINT        NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    author_id          BIGINT        NOT NULL REFERENCES users (id),
    change_description VARCHAR(2000) NOT NULL,
    changed_node_ids   JSONB         NOT NULL,
    max_depth          INT           NOT NULL CHECK (max_depth BETWEEN 1 AND 6),
    affected           JSONB         NOT NULL,
    risk_level         VARCHAR(20)   NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    recommendation     TEXT,
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE generated_documents (
    id          BIGSERIAL PRIMARY KEY,
    project_id  BIGINT       NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    run_id      BIGINT       NOT NULL REFERENCES analysis_runs (id) ON DELETE CASCADE,
    type        VARCHAR(30)  NOT NULL,
    title       VARCHAR(300) NOT NULL,
    content_md  TEXT         NOT NULL,
    status      VARCHAR(20)  NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'APPROVED', 'OUTDATED')),
    approved_by BIGINT       REFERENCES users (id),
    approved_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE webhook_events (
    id            BIGSERIAL PRIMARY KEY,
    repository_id BIGINT       NOT NULL REFERENCES git_repositories (id) ON DELETE CASCADE,
    delivery_id   VARCHAR(100) NOT NULL,
    event_type    VARCHAR(50)  NOT NULL,
    branch        VARCHAR(200),
    commit_sha    VARCHAR(64),
    received_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    processed     BOOLEAN      NOT NULL DEFAULT FALSE,
    run_id        BIGINT       REFERENCES analysis_runs (id) ON DELETE SET NULL,
    UNIQUE (repository_id, delivery_id)
);
