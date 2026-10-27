"""ER-диаграмма физической модели БД PortaGraph (PostgreSQL + pgvector), нотация «вороньи лапки»."""
import subprocess
from html import escape

T = {
 "users": [("id", "bigserial", "PK"), ("email", "varchar(254)", "UQ"), ("password_hash", "varchar(255)", ""),
           ("full_name", "varchar(150)", ""), ("created_at", "timestamptz", "")],
 "projects": [("id", "bigserial", "PK"), ("name", "varchar(120)", ""), ("description", "varchar(2000)", ""),
              ("owner_id", "bigint", "FK"), ("status", "varchar(20)", ""), ("created_at", "timestamptz", "")],
 "project_members": [("id", "bigserial", "PK"), ("project_id", "bigint", "FK"), ("user_id", "bigint", "FK"),
                     ("role", "varchar(20)", ""), ("joined_at", "timestamptz", "")],
 "repo_credentials": [("id", "bigserial", "PK"), ("project_id", "bigint", "FK"), ("provider", "varchar(20)", ""),
                      ("encrypted_token", "bytea", ""), ("scopes", "varchar(300)", ""), ("expires_at", "timestamptz", ""),
                      ("created_at", "timestamptz", "")],
 "git_repositories": [("id", "bigserial", "PK"), ("project_id", "bigint", "FK"), ("provider", "varchar(20)", ""),
                      ("url", "varchar(500)", ""), ("name", "varchar(200)", ""), ("default_branch", "varchar(100)", ""),
                      ("credential_id", "bigint", "FK"), ("detected_role", "varchar(20)", ""), ("role_confidence", "float8", ""),
                      ("purpose_summary", "varchar(2000)", ""), ("status", "varchar(20)", ""), ("last_commit_sha", "varchar(64)", ""),
                      ("last_synced_at", "timestamptz", ""), ("webhook_secret", "varchar(128)", "")],
 "analysis_runs": [("id", "bigserial", "PK"), ("project_id", "bigint", "FK"), ("trigger_type", "varchar(20)", ""),
                   ("status", "varchar(20)", ""), ("progress", "int", ""), ("started_at", "timestamptz", ""),
                   ("finished_at", "timestamptz", ""), ("error_message", "varchar(2000)", ""), ("artifact_key", "varchar(300)", ""),
                   ("stats", "jsonb", "")],
 "source_files": [("id", "bigserial", "PK"), ("repository_id", "bigint", "FK"), ("path", "varchar(1000)", ""),
                  ("language", "varchar(40)", ""), ("kind", "varchar(20)", ""), ("content_sha", "varchar(64)", ""),
                  ("size_bytes", "bigint", ""), ("storage_key", "varchar(300)", ""), ("updated_at", "timestamptz", "")],
 "code_chunks": [("id", "bigserial", "PK"), ("source_file_id", "bigint", "FK"), ("start_line", "int", ""), ("end_line", "int", ""),
                 ("symbol", "varchar(300)", ""), ("content", "text", ""), ("embedding", "vector(1536)", "IX")],
 "graph_nodes": [("id", "bigserial", "PK"), ("project_id", "bigint", "FK"), ("run_id", "bigint", "FK"), ("type", "varchar(30)", ""),
                 ("name", "varchar(300)", ""), ("qualified_name", "varchar(1000)", ""), ("repository_id", "bigint", "FK"),
                 ("source_file_id", "bigint", "FK"), ("parent_id", "bigint", "FK"), ("description", "varchar(2000)", ""),
                 ("confidence", "float8", ""), ("verified", "boolean", ""), ("metadata", "jsonb", "")],
 "graph_edges": [("id", "bigserial", "PK"), ("project_id", "bigint", "FK"), ("run_id", "bigint", "FK"),
                 ("source_node_id", "bigint", "FK"), ("target_node_id", "bigint", "FK"), ("type", "varchar(20)", ""),
                 ("confidence", "float8", ""), ("verified", "boolean", ""), ("evidence", "jsonb", "")],
 "chat_sessions": [("id", "bigserial", "PK"), ("project_id", "bigint", "FK"), ("user_id", "bigint", "FK"),
                   ("title", "varchar(200)", ""), ("created_at", "timestamptz", "")],
 "chat_messages": [("id", "bigserial", "PK"), ("session_id", "bigint", "FK"), ("role", "varchar(20)", ""),
                   ("content", "text", ""), ("created_at", "timestamptz", "")],
 "citations": [("id", "bigserial", "PK"), ("message_id", "bigint", "FK"), ("source_file_id", "bigint", "FK"),
               ("start_line", "int", ""), ("end_line", "int", ""), ("node_id", "bigint", "FK")],
 "impact_reports": [("id", "bigserial", "PK"), ("project_id", "bigint", "FK"), ("author_id", "bigint", "FK"),
                    ("change_description", "varchar(2000)", ""), ("changed_node_ids", "jsonb", ""), ("max_depth", "int", ""),
                    ("affected", "jsonb", ""), ("risk_level", "varchar(20)", ""), ("recommendation", "text", ""),
                    ("created_at", "timestamptz", "")],
 "generated_documents": [("id", "bigserial", "PK"), ("project_id", "bigint", "FK"), ("run_id", "bigint", "FK"),
                         ("type", "varchar(30)", ""), ("title", "varchar(300)", ""), ("content_md", "text", ""),
                         ("status", "varchar(20)", ""), ("approved_by", "bigint", "FK"), ("approved_at", "timestamptz", ""),
                         ("created_at", "timestamptz", "")],
 "webhook_events": [("id", "bigserial", "PK"), ("repository_id", "bigint", "FK"), ("delivery_id", "varchar(100)", ""),
                    ("event_type", "varchar(50)", ""), ("branch", "varchar(200)", ""), ("commit_sha", "varchar(64)", ""),
                    ("received_at", "timestamptz", ""), ("processed", "boolean", ""), ("run_id", "bigint", "FK")],
}
# (дочерняя.поле, родительская, обязательность связи у дочерней стороны)
REL = [
 ("projects", "owner_id", "users", True), ("project_members", "project_id", "projects", True),
 ("project_members", "user_id", "users", True), ("repo_credentials", "project_id", "projects", True),
 ("git_repositories", "project_id", "projects", True), ("git_repositories", "credential_id", "repo_credentials", False),
 ("analysis_runs", "project_id", "projects", True), ("source_files", "repository_id", "git_repositories", True),
 ("code_chunks", "source_file_id", "source_files", True), ("graph_nodes", "run_id", "analysis_runs", True),
 ("graph_nodes", "repository_id", "git_repositories", False), ("graph_nodes", "source_file_id", "source_files", False),
 ("graph_nodes", "parent_id", "graph_nodes", False), ("graph_edges", "run_id", "analysis_runs", True),
 ("graph_edges", "source_node_id", "graph_nodes", True), ("graph_edges", "target_node_id", "graph_nodes", True),
 ("chat_sessions", "project_id", "projects", True), ("chat_sessions", "user_id", "users", True),
 ("chat_messages", "session_id", "chat_sessions", True), ("citations", "message_id", "chat_messages", True),
 ("citations", "source_file_id", "source_files", True), ("citations", "node_id", "graph_nodes", False),
 ("impact_reports", "project_id", "projects", True), ("impact_reports", "author_id", "users", True),
 ("generated_documents", "run_id", "analysis_runs", True), ("generated_documents", "approved_by", "users", False),
 ("webhook_events", "repository_id", "git_repositories", True), ("webhook_events", "run_id", "analysis_runs", False),
]

def table(name, cols):
    rows = [f'<TR><TD COLSPAN="3" BGCOLOR="#2f4ac0" CELLPADDING="5"><FONT COLOR="white"><B>{name}</B></FONT></TD></TR>']
    for c, t, k in cols:
        key = {"PK": "PK", "FK": "FK", "UQ": "UQ", "IX": "HNSW"}.get(k, " ")
        bg = ' BGCOLOR="#eef3fb"' if k == "PK" else (' BGCOLOR="#fff9db"' if k == "FK" else "")
        nm = f"<B>{escape(c)}</B>" if k == "PK" else escape(c)
        rows.append(f'<TR><TD ALIGN="LEFT" PORT="{c}"{bg}>{nm}</TD><TD ALIGN="LEFT"{bg}><FONT COLOR="#555555">{t}</FONT></TD>'
                    f'<TD PORT="{c}_r"{bg}><FONT POINT-SIZE="8" COLOR="#2f4ac0">{key}</FONT></TD></TR>')
    return f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="3" COLOR="#2f4ac0">{"".join(rows)}</TABLE>>'

lines = ['digraph ER {',
 '  graph [rankdir=LR, fontname="DejaVu Sans", fontsize=14, pad=0.3, nodesep=0.35, ranksep=0.9, splines=true, labelloc=t,',
 '         label="ER-диаграмма базы данных PortaGraph (PostgreSQL 16 + pgvector)\\n\\n"];',
 '  node [shape=plain, fontname="DejaVu Sans", fontsize=10];',
 '  edge [color="#555555", dir=both, arrowsize=1.0, penwidth=1.1];']
for n, c in T.items():
    lines.append(f"  {n} [label={table(n, c)}];")
for child, fk, parent, mandatory in REL:
    tail = "crowodot"                       # «много» (0..*) со стороны дочерней таблицы
    head = "teetee" if mandatory else "teeodot"  # 1 или 0..1 со стороны родителя
    lines.append(f'  {child}:{fk}_r:e -> {parent}:id:w [arrowtail={tail}, arrowhead={head}];')
lines.append("}")
open("er.dot", "w").write("\n".join(lines))
subprocess.run(["dot", "-Tpng", "-Gdpi=120", "er.dot", "-o", "../er_database.png"], check=True)
print("er ok")
