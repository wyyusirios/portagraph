-- PortaGraph: схема базы данных (PostgreSQL 14+)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE users (
    id            bigserial PRIMARY KEY,
    email         varchar(254) NOT NULL UNIQUE,
    password_hash varchar(255) NOT NULL,
    full_name     varchar(150) NOT NULL,
    created_at    timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id          bigserial PRIMARY KEY,
    name        varchar(120)  NOT NULL,
    description varchar(2000),
    owner_id    bigint        NOT NULL REFERENCES users (id),
    status      varchar(20)   NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    created_at  timestamptz   NOT NULL DEFAULT now()
);

CREATE TABLE project_members (
    id         bigserial PRIMARY KEY,
    project_id bigint      NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    user_id    bigint      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role       varchar(20) NOT NULL CHECK (role IN ('OWNER', 'ARCHITECT', 'DEVELOPER', 'VIEWER')),
    joined_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, user_id)
);

CREATE TABLE repo_credentials (
    id              bigserial PRIMARY KEY,
    project_id      bigint      NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    provider        varchar(20) NOT NULL,
    encrypted_token bytea       NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE repositories (
    id              bigserial PRIMARY KEY,
    project_id      bigint        NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    source_kind     varchar(10)   NOT NULL CHECK (source_kind IN ('git', 'zip', 'demo', 'local')),
    provider        varchar(20)   NOT NULL DEFAULT 'OTHER',
    url             varchar(500)  NOT NULL,
    name            varchar(200)  NOT NULL,
    default_branch  varchar(100),
    credential_id   bigint        REFERENCES repo_credentials (id) ON DELETE SET NULL,
    local_path      varchar(1000),
    detected_role   varchar(20)   NOT NULL DEFAULT 'UNKNOWN',
    role_confidence double precision NOT NULL DEFAULT 0,
    purpose_summary varchar(2000),
    status          varchar(20)   NOT NULL DEFAULT 'CONNECTED',
    status_message  varchar(500),
    last_commit_sha varchar(64),
    last_synced_at  timestamptz,
    webhook_secret  varchar(128),
    created_at      timestamptz   NOT NULL DEFAULT now(),
    UNIQUE (project_id, url),
    UNIQUE (project_id, name)
);

CREATE TABLE analysis_runs (
    id            bigserial PRIMARY KEY,
    project_id    bigint      NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    trigger_type  varchar(20) NOT NULL CHECK (trigger_type IN ('MANUAL', 'WEBHOOK', 'SCHEDULE', 'SYNC')),
    status        varchar(20) NOT NULL DEFAULT 'QUEUED',
    progress      int         NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    stage_message varchar(500),
    started_at    timestamptz,
    finished_at   timestamptz,
    error_message varchar(2000),
    stats         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    log           jsonb       NOT NULL DEFAULT '[]'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_runs_project_status ON analysis_runs (project_id, status);

CREATE TABLE source_files (
    id            bigserial PRIMARY KEY,
    repository_id bigint        NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    path          varchar(1000) NOT NULL,
    language      varchar(40),
    kind          varchar(20)   NOT NULL,
    content_sha   varchar(64)   NOT NULL,
    size_bytes    bigint        NOT NULL,
    line_count    int           NOT NULL DEFAULT 0,
    content       text          NOT NULL,
    secrets_found int           NOT NULL DEFAULT 0,
    updated_at    timestamptz   NOT NULL DEFAULT now(),
    UNIQUE (repository_id, path)
);

CREATE TABLE code_chunks (
    id             bigserial PRIMARY KEY,
    source_file_id bigint NOT NULL REFERENCES source_files (id) ON DELETE CASCADE,
    project_id     bigint NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    start_line     int    NOT NULL,
    end_line       int    NOT NULL,
    symbol         varchar(300),
    search_text    text   NOT NULL,
    content        text   NOT NULL,
    tsv            tsvector GENERATED ALWAYS AS (to_tsvector('simple', search_text)) STORED,
    CHECK (end_line >= start_line)
);
CREATE INDEX ix_chunks_file ON code_chunks (source_file_id);
CREATE INDEX ix_chunks_project ON code_chunks (project_id);
CREATE INDEX ix_chunks_tsv ON code_chunks USING gin (tsv);

CREATE TABLE graph_nodes (
    id             bigserial PRIMARY KEY,
    project_id     bigint        NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    run_id         bigint        NOT NULL REFERENCES analysis_runs (id) ON DELETE CASCADE,
    type           varchar(30)   NOT NULL,
    name           varchar(300)  NOT NULL,
    qualified_name varchar(1000) NOT NULL,
    repository_id  bigint        REFERENCES repositories (id) ON DELETE CASCADE,
    source_file_id bigint        REFERENCES source_files (id) ON DELETE SET NULL,
    start_line     int,
    end_line       int,
    parent_id      bigint        REFERENCES graph_nodes (id) ON DELETE CASCADE,
    description    varchar(2000),
    confidence     double precision NOT NULL DEFAULT 1 CHECK (confidence BETWEEN 0 AND 1),
    verified       boolean       NOT NULL DEFAULT false,
    metadata       jsonb         NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ix_nodes_run_type ON graph_nodes (run_id, type);
CREATE INDEX ix_nodes_name_trgm ON graph_nodes USING gin (name gin_trgm_ops);

CREATE TABLE graph_edges (
    id             bigserial PRIMARY KEY,
    project_id     bigint      NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    run_id         bigint      NOT NULL REFERENCES analysis_runs (id) ON DELETE CASCADE,
    source_node_id bigint      NOT NULL REFERENCES graph_nodes (id) ON DELETE CASCADE,
    target_node_id bigint      NOT NULL REFERENCES graph_nodes (id) ON DELETE CASCADE,
    type           varchar(20) NOT NULL,
    confidence     double precision NOT NULL DEFAULT 1 CHECK (confidence BETWEEN 0 AND 1),
    verified       boolean     NOT NULL DEFAULT false,
    rejected       boolean     NOT NULL DEFAULT false,
    evidence       jsonb       NOT NULL DEFAULT '[]'::jsonb,
    CHECK (source_node_id <> target_node_id)
);
CREATE INDEX ix_edges_run ON graph_edges (run_id);
CREATE INDEX ix_edges_target ON graph_edges (target_node_id);

-- Решения архитектора переживают повторный анализ: ключ – полное имя узла
CREATE TABLE verifications (
    id             bigserial PRIMARY KEY,
    project_id     bigint        NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    subject        varchar(10)   NOT NULL CHECK (subject IN ('NODE', 'EDGE')),
    key            varchar(2100) NOT NULL,
    decision       varchar(10)   NOT NULL CHECK (decision IN ('CONFIRM', 'REJECT')),
    description    varchar(2000),
    user_id        bigint        NOT NULL REFERENCES users (id),
    created_at     timestamptz   NOT NULL DEFAULT now(),
    UNIQUE (project_id, subject, key)
);

CREATE TABLE chat_sessions (
    id         bigserial PRIMARY KEY,
    project_id bigint       NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    user_id    bigint       NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title      varchar(200) NOT NULL,
    created_at timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
    id         bigserial PRIMARY KEY,
    session_id bigint      NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    role       varchar(20) NOT NULL CHECK (role IN ('USER', 'ASSISTANT')),
    content    text        NOT NULL,
    citations  jsonb       NOT NULL DEFAULT '[]'::jsonb,
    confidence double precision,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE impact_reports (
    id                 bigserial PRIMARY KEY,
    project_id         bigint        NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    run_id             bigint        REFERENCES analysis_runs (id) ON DELETE SET NULL,
    author_id          bigint        NOT NULL REFERENCES users (id),
    change_description varchar(2000) NOT NULL,
    changed_nodes      jsonb         NOT NULL,
    max_depth          int           NOT NULL CHECK (max_depth BETWEEN 1 AND 6),
    affected           jsonb         NOT NULL,
    risk_level         varchar(20)   NOT NULL CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    total_weight       double precision NOT NULL DEFAULT 0,
    recommendation     text,
    created_at         timestamptz   NOT NULL DEFAULT now()
);

CREATE TABLE generated_documents (
    id          bigserial PRIMARY KEY,
    project_id  bigint       NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    run_id      bigint       REFERENCES analysis_runs (id) ON DELETE SET NULL,
    type        varchar(30)  NOT NULL CHECK (type IN ('ARCHITECTURE_OVERVIEW', 'ONBOARDING_GUIDE', 'SERVICE_CARD')),
    title       varchar(300) NOT NULL,
    content_md  text         NOT NULL,
    status      varchar(20)  NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'APPROVED', 'OUTDATED')),
    created_by  bigint       REFERENCES users (id),
    approved_by bigint       REFERENCES users (id),
    approved_at timestamptz,
    created_at  timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE webhook_events (
    id            bigserial PRIMARY KEY,
    repository_id bigint       NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    delivery_id   varchar(100) NOT NULL,
    event_type    varchar(50)  NOT NULL,
    branch        varchar(200),
    commit_sha    varchar(64),
    received_at   timestamptz  NOT NULL DEFAULT now(),
    processed     boolean      NOT NULL DEFAULT false,
    run_id        bigint       REFERENCES analysis_runs (id) ON DELETE SET NULL,
    UNIQUE (repository_id, delivery_id)
);
