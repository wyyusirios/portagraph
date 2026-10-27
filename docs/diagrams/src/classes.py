"""UML-диаграммы классов (доменная модель и сервисный слой) и ER-диаграмма БД PortaGraph."""
import subprocess
from html import escape

FONT = "DejaVu Sans"

def cls(name, attrs=(), ops=(), stereo=None, fill="#eef3fb", border="#2f4ac0", italic=False):
    head = ""
    if stereo:
        head += f'<FONT POINT-SIZE="9">«{stereo}»</FONT><BR/>'
    nm = f"<I>{escape(name)}</I>" if italic else escape(name)
    head += f"<B>{nm}</B>"
    rows = [f'<TR><TD BGCOLOR="{fill}" CELLPADDING="5">{head}</TD></TR>']
    if attrs is not None:
        a = "<BR ALIGN=\"LEFT\"/>".join(escape(x) for x in attrs) + ('<BR ALIGN="LEFT"/>' if attrs else "")
        rows.append(f'<TR><TD ALIGN="LEFT" BALIGN="LEFT" CELLPADDING="4">{a or " "}</TD></TR>')
    if ops is not None:
        o = "<BR ALIGN=\"LEFT\"/>".join(escape(x) for x in ops) + ('<BR ALIGN="LEFT"/>' if ops else "")
        rows.append(f'<TR><TD ALIGN="LEFT" BALIGN="LEFT" CELLPADDING="4">{o or " "}</TD></TR>')
    return (f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" COLOR="{border}">' + "".join(rows) + "</TABLE>>")


def render(name, body, extra=""):
    src = f"""digraph G {{
  graph [fontname="{FONT}", fontsize=14, pad=0.3, nodesep=0.45, ranksep=0.7, splines=true, labelloc=t {extra}];
  node [shape=plain, fontname="{FONT}", fontsize=10];
  edge [fontname="{FONT}", fontsize=9, color="#333333", arrowsize=0.9];
{body}
}}"""
    open(f"{name}.dot", "w").write(src)
    subprocess.run(["dot", "-Tpng", "-Gdpi=130", f"{name}.dot", "-o", f"../{name}.png"], check=True)


# ---------------------------------------------------------------- доменная модель
domain = {
 "User": cls("User", ["- id: Long", "- email: String", "- passwordHash: String", "- fullName: String", "- createdAt: Instant"], []),
 "Project": cls("Project", ["- id: Long", "- name: String", "- description: String", "- status: ProjectStatus", "- createdAt: Instant"],
                ["+ addRepository(r: GitRepository): void"]),
 "ProjectMember": cls("ProjectMember", ["- id: Long", "- role: ProjectRole", "- joinedAt: Instant"],
                      ["+ canApprove(): boolean", "+ canManage(): boolean"]),
 "RepoCredential": cls("RepoCredential", ["- id: Long", "- provider: GitProvider", "- encryptedToken: byte[]", "- scopes: String", "- expiresAt: Instant"],
                       ["+ isExpired(now: Instant): boolean"]),
 "GitRepository": cls("GitRepository", ["- id: Long", "- provider: GitProvider", "- url: String", "- name: String", "- defaultBranch: String",
                      "- detectedRole: RepositoryRole", "- roleConfidence: double", "- purposeSummary: String", "- status: RepositoryStatus",
                      "- lastCommitSha: String", "- lastSyncedAt: Instant", "- webhookSecret: String"],
                      ["+ markSynced(commitSha: String): void"]),
 "AnalysisRun": cls("AnalysisRun", ["- id: Long", "- trigger: RunTrigger", "- status: RunStatus", "- progress: int", "- startedAt: Instant",
                    "- finishedAt: Instant", "- errorMessage: String", "- artifactKey: String", "- stats: Map<String, Object>"],
                    ["+ moveTo(next: RunStatus): void", "+ fail(message: String): void", "+ isActive(): boolean"]),
 "SourceFile": cls("SourceFile", ["- id: Long", "- path: String", "- language: String", "- kind: FileKind", "- contentSha: String",
                   "- sizeBytes: long", "- storageKey: String"], []),
 "CodeChunk": cls("CodeChunk", ["- id: Long", "- startLine: int", "- endLine: int", "- symbol: String", "- content: String",
                  "- embedding: float[1536]"], []),
 "GraphNode": cls("GraphNode", ["- id: Long", "- type: NodeType", "- name: String", "- qualifiedName: String", "- description: String",
                  "- confidence: double", "- verified: boolean", "- metadata: Map<String, Object>"], []),
 "GraphEdge": cls("GraphEdge", ["- id: Long", "- type: EdgeType", "- confidence: double", "- verified: boolean",
                  "- evidence: List<Map<String, Object>>"], []),
 "ChatSession": cls("ChatSession", ["- id: Long", "- title: String", "- createdAt: Instant"],
                    ["+ addMessage(role: MessageRole, content: String): ChatMessage"]),
 "ChatMessage": cls("ChatMessage", ["- id: Long", "- role: MessageRole", "- content: String", "- createdAt: Instant"],
                    ["+ addCitation(file: SourceFile, start: int, end: int, node: GraphNode): void"]),
 "Citation": cls("Citation", ["- id: Long", "- startLine: int", "- endLine: int"], []),
 "ImpactReport": cls("ImpactReport", ["- id: Long", "- changeDescription: String", "- changedNodeIds: List<Long>", "- maxDepth: int",
                     "- affected: List<Map<String, Object>>", "- riskLevel: RiskLevel", "- recommendation: String", "- createdAt: Instant"], []),
 "GeneratedDocument": cls("GeneratedDocument", ["- id: Long", "- type: DocumentType", "- title: String", "- contentMd: String",
                          "- status: DocumentStatus", "- approvedAt: Instant", "- createdAt: Instant"],
                          ["+ approve(architect: User): void"]),
 "WebhookEvent": cls("WebhookEvent", ["- id: Long", "- deliveryId: String", "- eventType: String", "- branch: String",
                     "- commitSha: String", "- receivedAt: Instant", "- processed: boolean"], []),
}
EF, EB = "#f1f3f5", "#495057"
enums = {
 "RunStatus": cls("RunStatus", ["QUEUED", "FETCHING", "INDEXING", "ANALYZING", "BUILDING_GRAPH", "COMPLETED", "FAILED", "CANCELLED"], None, "enumeration", EF, EB),
 "NodeType": cls("NodeType", ["SYSTEM", "REPOSITORY", "SERVICE", "MODULE", "CLASS", "FUNCTION", "ENTITY", "API_ENDPOINT", "DATABASE", "MESSAGE_QUEUE", "EXTERNAL_SYSTEM"], None, "enumeration", EF, EB),
 "EdgeType": cls("EdgeType", ["CONTAINS", "DEPENDS_ON", "IMPORTS", "CALLS_HTTP", "PUBLISHES", "CONSUMES", "READS_WRITES", "IMPLEMENTS"], None, "enumeration", EF, EB),
 "ProjectRole": cls("ProjectRole", ["OWNER", "ARCHITECT", "DEVELOPER", "VIEWER"], None, "enumeration", EF, EB),
 "RepositoryRole": cls("RepositoryRole", ["SERVICE", "FRONTEND", "LIBRARY", "INFRASTRUCTURE", "DOCUMENTATION", "UNKNOWN"], None, "enumeration", EF, EB),
 "RiskLevel": cls("RiskLevel", ["LOW", "MEDIUM", "HIGH", "CRITICAL"], None, "enumeration", EF, EB),
 "DocumentStatus": cls("DocumentStatus", ["DRAFT", "APPROVED", "OUTDATED"], None, "enumeration", EF, EB),
}

def comp(whole, part, mw="1", mp="0..*", label=""):
    # композиция: закрашенный ромб у целого
    return f'  {whole} -> {part} [dir=back, arrowtail=diamond, taillabel="{mw}", headlabel="{mp}", label="{label}"];'

def assoc(a, b, ma, mb, label=""):
    return f'  {a} -> {b} [arrowhead=vee, taillabel="{ma}", headlabel="{mb}", label="{label}"];'

body = [f"  {k} [label={v}];" for k, v in {**domain, **enums}.items()]
body += [
 comp("Project", "ProjectMember", "1", "1..*", " members"),
 comp("Project", "GitRepository", "1", "0..*", " repositories"),
 comp("Project", "RepoCredential"),
 comp("Project", "AnalysisRun"),
 comp("Project", "ChatSession"),
 comp("Project", "ImpactReport"),
 comp("GitRepository", "SourceFile"),
 comp("GitRepository", "WebhookEvent"),
 comp("SourceFile", "CodeChunk", "1", "1..*"),
 comp("AnalysisRun", "GraphNode", "1", "0..*", " nodes"),
 comp("AnalysisRun", "GraphEdge", "1", "0..*", " edges"),
 comp("AnalysisRun", "GeneratedDocument"),
 comp("ChatSession", "ChatMessage", "1", "1..*", " messages"),
 comp("ChatMessage", "Citation"),
 assoc("ProjectMember", "User", "0..*", "1", " user"),
 assoc("Project", "User", "0..*", "1", " owner"),
 assoc("GitRepository", "RepoCredential", "0..*", "0..1", " credential"),
 assoc("GraphEdge", "GraphNode", "0..*", "1", " source"),
 assoc("GraphEdge", "GraphNode", "0..*", "1", " target"),
 '  GraphNode -> GraphNode [arrowhead=vee, taillabel="0..*", headlabel="0..1", label=" parent"];',
 assoc("GraphNode", "SourceFile", "0..*", "0..1", " sourceFile"),
 assoc("Citation", "SourceFile", "0..*", "1", " sourceFile"),
 assoc("ChatSession", "User", "0..*", "1", " user"),
 assoc("ImpactReport", "User", "0..*", "1", " author"),
 assoc("GeneratedDocument", "User", "0..*", "0..1", " approvedBy"),
 assoc("WebhookEvent", "AnalysisRun", "0..*", "0..1", " run"),
 # зависимости от перечислений
 '  edge [style=dashed, arrowhead=vee, color="#868e96"];',
 '  AnalysisRun -> RunStatus; GraphNode -> NodeType; GraphEdge -> EdgeType; ProjectMember -> ProjectRole;',
 '  GitRepository -> RepositoryRole; ImpactReport -> RiskLevel; GeneratedDocument -> DocumentStatus;',
 '  { rank=same; RunStatus; NodeType; EdgeType; ProjectRole; RepositoryRole; RiskLevel; DocumentStatus; }',
]
render("class_domain", "\n".join(body),
       ', label="Диаграмма классов: доменная модель (пакет ru.portagraph.domain)\\n\\n", ranksep=0.9')

# ---------------------------------------------------------------- сервисный слой
SF, SB = "#e7f5ff", "#1971c2"     # сервисы
IF, IB = "#fff4e6", "#d9480f"     # интерфейсы и внешние адаптеры
CF, CB = "#ebfbee", "#2b8a3e"     # ядро алгоритмов
WF, WB = "#f3f0ff", "#5f3dc4"     # контроллеры
svc = {
 "RepositoryController": cls("RepositoryController", None, ["+ list(jwt, projectId): List<RepositoryView>", "+ connect(jwt, projectId, req): List<ConnectResult>"], "RestController", WF, WB),
 "GraphController": cls("GraphController", None, ["+ graph(jwt, projectId, mode): GraphView", "+ verify(jwt, projectId, nodeId, req): void"], "RestController", WF, WB),
 "AssistantController": cls("AssistantController", None, ["+ ask(jwt, projectId, req): AnswerView"], "RestController", WF, WB),
 "ImpactController": cls("ImpactController", None, ["+ analyze(jwt, projectId, req): ImpactView"], "RestController", WF, WB),
 "WebhookController": cls("WebhookController", None, ["+ github(repoId, body, headers): ResponseEntity", "+ bitbucket(repoId, body, headers): ResponseEntity"], "RestController", WF, WB),

 "RepositoryConnectionService": cls("RepositoryConnectionService", ["- publicUrl: String"],
    ["+ connect(projectId, userId, urls, token): List<ConnectResult>", "+ list(projectId, userId): List<GitRepository>", "+ disconnect(projectId, userId, repoId): void"], "Service", SF, SB),
 "AnalysisPipeline": cls("AnalysisPipeline", None,
    ["+ enqueue(projectId, trigger): AnalysisRun", "+ enqueue(projectId, trigger, onlyPaths): AnalysisRun", "+ execute(event: RunQueued): void"], "Service", SF, SB),
 "IndexingService": cls("IndexingService", ["~ MAX_FILE_BYTES: long = 524288"],
    ["+ indexRepository(repo, commitSha, onlyPaths): IndexStats", "~ classify(path): Optional<FileKind>"], "Service", SF, SB),
 "GraphService": cls("GraphService", ["~ MIN_EDGE_CONFIDENCE: double = 0.35"],
    ["+ analyzeRepositories(run): Map<Long, GraphNode>", "+ linkRepositories(run, components): int", "+ loadGraph(projectId): ArchitectureGraph",
     "+ overview(projectId, userId): ArchitectureGraph", "+ detailed(projectId, userId): ArchitectureGraph", "+ verifyNode(projectId, userId, nodeId, text): GraphNode"], "Service", SF, SB),
 "QuestionAnsweringService": cls("QuestionAnsweringService", ["~ TOP_K: int = 12", "~ MIN_CONFIDENCE: double = 0.4"],
    ["+ ask(projectId, userId, sessionId, question): ChatMessage"], "Service", SF, SB),
 "ImpactAnalysisService": cls("ImpactAnalysisService", ["~ DEFAULT_DEPTH: int = 3", "~ MAX_DEPTH: int = 6"],
    ["+ analyze(projectId, userId, description, nodeIds, depth): ImpactReport", "+ history(projectId, userId): List<ImpactReport>"], "Service", SF, SB),
 "DocumentationService": cls("DocumentationService", None,
    ["+ generate(projectId, userId, type): GeneratedDocument", "+ approve(projectId, userId, docId): GeneratedDocument"], "Service", SF, SB),
 "WebhookService": cls("WebhookService", None,
    ["+ handlePush(repoId, body, signature, push): Outcome", "~ signatureValid(secret, body, header): boolean"], "Service", SF, SB),
 "AccessGuard": cls("AccessGuard", None, ["+ requireMember(projectId, userId): ProjectMember", "+ requireApprover(projectId, userId): ProjectMember", "+ requireOwner(projectId, userId): ProjectMember"], "Component", SF, SB),
 "CredentialCipher": cls("CredentialCipher", ["- key: SecretKeySpec"], ["+ encrypt(token: String): byte[]", "+ decrypt(data: byte[]): String"], "Component", SF, SB),

 "GitProviderClient": cls("GitProviderClient", None, ["+ provider(): GitProvider", "+ verifyAccess(url, token): RepositoryInfo", "+ latestCommit(url, branch, token): String",
    "+ listFiles(url, sha, token): List<RemoteFile>", "+ readFile(url, sha, path, token): String", "+ changedFiles(url, from, to, token): List<String>",
    "+ registerWebhook(url, callback, secret, token): void"], "interface", IF, IB, italic=True),
 "GitHubClient": cls("GitHubClient", ["- http: RestClient"], [], None, IF, IB),
 "BitbucketClient": cls("BitbucketClient", ["- http: RestClient"], [], None, IF, IB),
 "GitProviderRegistry": cls("GitProviderRegistry", ["- clients: Map<GitProvider, GitProviderClient>"], ["+ get(provider): GitProviderClient", "+ detect(url): GitProvider {static}"], None, IF, IB),
 "AgentRuntime": cls("AgentRuntime", None, ["+ describeRepository(ctx): RepositoryInsight", "+ verifyLinks(candidates, summaries): List<LinkVerdict>",
    "+ answer(question, snippets): GroundedAnswer", "+ explainImpact(change, affected): String", "+ draftDocument(type, graphSummary): String"], "interface", IF, IB, italic=True),
 "HermesAgentClient": cls("HermesAgentClient", ["- http: RestClient"], ["- run(task, input, type): T"], None, IF, IB),
 "EmbeddingClient": cls("EmbeddingClient", ["- model: String"], ["+ embed(texts: List<String>): List<float[]>", "+ toPgVector(v: float[]): String {static}"], None, IF, IB),

 "ArchitectureGraph": cls("ArchitectureGraph", ["- nodes: Map<Long, Node>", "- outgoing: Map<Long, List<Edge>>", "- incoming: Map<Long, List<Edge>>"],
    ["+ addNode(n: Node): void", "+ addEdge(e: Edge): void", "+ dependenciesOf(id): List<Edge>", "+ dependentsOf(id): List<Edge>", "+ collapseTo(types: Set<String>): ArchitectureGraph"], "core", CF, CB),
 "ImpactAnalyzer": cls("ImpactAnalyzer", ["- DECAY: double = 0.6 {readOnly}"], ["+ analyze(changed: Collection<Long>, maxDepth: int): ImpactResult", "~ assessRisk(affected): RiskLevel"], "core", CF, CB),
 "SecretScanner": cls("SecretScanner", None, ["+ scan(text: String): ScanResult", "+ isSecretFile(path: String): boolean"], "core", CF, CB),
 "CodeChunker": cls("CodeChunker", ["- windowLines: int", "- overlapLines: int"], ["+ chunk(content, symbols): List<Chunk>"], "core", CF, CB),
 "DependencyExtractor": cls("DependencyExtractor", ["- knownServices: Set<String>", "- knownArtifacts: Set<String>"], ["+ extract(path, content): List<LinkCandidate>"], "core", CF, CB),
 "RepositoryRoleClassifier": cls("RepositoryRoleClassifier", None, ["+ classify(paths): Classification"], "core", CF, CB),
 "SymbolExtractor": cls("SymbolExtractor", None, ["+ extract(language, content): List<SymbolSpan>"], "core", CF, CB),
}
use = lambda a, b: f'  {a} -> {b} [style=dashed, arrowhead=vee, label=" «use»"];'
real = lambda impl, iface: f'  {impl} -> {iface} [style=dashed, arrowhead=onormal, arrowsize=1.2];'
body = [f"  {k} [label={v}];" for k, v in svc.items()]
body += [
 '  { rank=same; RepositoryController; GraphController; AssistantController; ImpactController; WebhookController; }',
 use("RepositoryController", "RepositoryConnectionService"), use("GraphController", "GraphService"),
 use("AssistantController", "QuestionAnsweringService"), use("ImpactController", "ImpactAnalysisService"),
 use("WebhookController", "WebhookService"),
 '  edge [label=""];',
 '  RepositoryConnectionService -> AnalysisPipeline [style=dashed, arrowhead=vee];',
 '  RepositoryConnectionService -> GitProviderRegistry [style=dashed, arrowhead=vee];',
 '  RepositoryConnectionService -> CredentialCipher [style=dashed, arrowhead=vee];',
 '  RepositoryConnectionService -> AccessGuard [style=dashed, arrowhead=vee];',
 '  WebhookService -> AnalysisPipeline [style=dashed, arrowhead=vee];',
 '  AnalysisPipeline -> IndexingService [style=dashed, arrowhead=vee];',
 '  AnalysisPipeline -> GraphService [style=dashed, arrowhead=vee];',
 '  IndexingService -> GitProviderRegistry [style=dashed, arrowhead=vee];',
 '  IndexingService -> EmbeddingClient [style=dashed, arrowhead=vee];',
 '  IndexingService -> SecretScanner [style=dashed, arrowhead=vee];',
 '  IndexingService -> CodeChunker [style=dashed, arrowhead=vee];',
 '  GraphService -> AgentRuntime [style=dashed, arrowhead=vee];',
 '  GraphService -> DependencyExtractor [style=dashed, arrowhead=vee];',
 '  GraphService -> RepositoryRoleClassifier [style=dashed, arrowhead=vee];',
 '  GraphService -> SymbolExtractor [style=dashed, arrowhead=vee];',
 '  GraphService -> ArchitectureGraph [style=dashed, arrowhead=vee];',
 '  QuestionAnsweringService -> EmbeddingClient [style=dashed, arrowhead=vee];',
 '  QuestionAnsweringService -> AgentRuntime [style=dashed, arrowhead=vee];',
 '  ImpactAnalysisService -> GraphService [style=dashed, arrowhead=vee];',
 '  ImpactAnalysisService -> ImpactAnalyzer [style=dashed, arrowhead=vee];',
 '  ImpactAnalysisService -> AgentRuntime [style=dashed, arrowhead=vee];',
 '  DocumentationService -> GraphService [style=dashed, arrowhead=vee];',
 '  DocumentationService -> AgentRuntime [style=dashed, arrowhead=vee];',
 '  ImpactAnalyzer -> ArchitectureGraph [arrowhead=vee, taillabel="", headlabel="1", label=" graph"];',
 real("GitHubClient", "GitProviderClient"), real("BitbucketClient", "GitProviderClient"),
 real("HermesAgentClient", "AgentRuntime"),
 '  GitProviderRegistry -> GitProviderClient [dir=back, arrowtail=odiamond, taillabel="1", headlabel="1..*"];',
]
render("class_services", "\n".join(body),
       ', label="Диаграмма классов: сервисный слой, интеграции и ядро алгоритмов\\n\\n", ranksep=0.8, nodesep=0.3')
print("classes ok")
