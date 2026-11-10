"""Модульные тесты ядра: граф, impact analysis, секреты, разбор кода, связи, роли."""
import unittest

from portagraph.core import deps, impact, roles, secrets, symbols
from portagraph.core.chunker import CodeChunker
from portagraph.core.graph import ArchitectureGraph, Edge, Node


def chain_graph():
    g = ArchitectureGraph()
    for i, (t, name) in enumerate([("SERVICE", "auth"), ("SERVICE", "orders"), ("SERVICE", "gateway"), ("SERVICE", "web"),
                                   ("MESSAGE_QUEUE", "orders.created"), ("SERVICE", "billing")], start=1):
        g.add_node(Node(i, t, name))
    g.add_edge(Edge(2, 1, "CALLS_HTTP", 1.0))   # orders → auth
    g.add_edge(Edge(3, 1, "CALLS_HTTP", 1.0))   # gateway → auth
    g.add_edge(Edge(4, 3, "CALLS_HTTP", 0.5))   # web → gateway (неуверенная)
    g.add_edge(Edge(2, 4 + 1, "PUBLISHES", 1.0))  # orders публикует в топик
    g.add_edge(Edge(6, 5, "CONSUMES", 1.0))     # billing читает топик
    return g


class GraphTests(unittest.TestCase):
    def test_self_loop_ignored(self):
        g = ArchitectureGraph()
        g.add_node(Node(1, "SERVICE", "a"))
        g.add_edge(Edge(1, 1, "CALLS_HTTP", 1))
        self.assertEqual(list(g.edges()), [])

    def test_publishes_is_reversed_for_impact(self):
        g = chain_graph()
        affected = {n for n, _ in g.affected_by(2)}
        self.assertIn(5, affected)  # изменение издателя затрагивает топик

    def test_collapse_keeps_max_confidence(self):
        g = ArchitectureGraph()
        g.add_node(Node(1, "SERVICE", "a"))
        g.add_node(Node(2, "SERVICE", "b"))
        g.add_node(Node(3, "CLASS", "A1", parent_id=1))
        g.add_node(Node(4, "CLASS", "B1", parent_id=2))
        g.add_edge(Edge(3, 4, "IMPORTS", 0.6))
        g.add_edge(Edge(1, 2, "IMPORTS", 0.9))
        c = g.collapse_to({"SERVICE"})
        es = list(c.edges())
        self.assertEqual(len(es), 1)
        self.assertAlmostEqual(es[0].confidence, 0.9)


class ImpactTests(unittest.TestCase):
    def test_decay_and_distance(self):
        res = impact.analyze(chain_graph(), [1], 3)
        by = {a.node.name: a for a in res.affected}
        self.assertAlmostEqual(by["orders"].score, 0.6)
        self.assertAlmostEqual(by["gateway"].score, 0.6)
        self.assertAlmostEqual(by["web"].score, 0.6 * 0.6 * 0.5)
        self.assertEqual(by["billing"].distance, 3)
        self.assertEqual(res.direct_services, 2)
        self.assertEqual(res.risk, "HIGH")

    def test_depth_limits(self):
        res = impact.analyze(chain_graph(), [1], 1)
        self.assertEqual({a.node.name for a in res.affected}, {"orders", "gateway"})
        with self.assertRaises(ValueError):
            impact.analyze(chain_graph(), [1], 7)
        with self.assertRaises(ValueError):
            impact.analyze(chain_graph(), [], 3)

    def test_risk_levels(self):
        self.assertEqual(impact.assess_risk(4, 1, 4), "CRITICAL")
        self.assertEqual(impact.assess_risk(0, 4.2, 9), "CRITICAL")
        self.assertEqual(impact.assess_risk(2, 1, 2), "HIGH")
        self.assertEqual(impact.assess_risk(0, 0.3, 1), "MEDIUM")
        self.assertEqual(impact.assess_risk(0, 0, 0), "LOW")


class SecretsTests(unittest.TestCase):
    def test_masks_values(self):
        text = 'password: S3cr3tPassw0rd!\napi_key = "abcdef123456"\nurl: postgres://app:hunter22@db:5432/x\ntoken ghp_' + "a" * 36
        r = secrets.scan(text)
        self.assertNotIn("S3cr3tPassw0rd", r.sanitized)
        self.assertNotIn("abcdef123456", r.sanitized)
        self.assertNotIn("hunter22", r.sanitized)
        self.assertIn("postgres://app:[REDACTED", r.sanitized)
        self.assertNotIn("ghp_aaaa", r.sanitized)
        self.assertGreaterEqual(len(r.findings), 4)

    def test_keeps_lookups(self):
        for s in ['API_KEY = os.getenv("API_KEY")', "token: process.env.TOKEN", "secret = settings.SECRET_KEY", "password: ${DB_PASSWORD}"]:
            self.assertFalse(secrets.scan(s).has_secrets, s)

    def test_secret_files(self):
        self.assertTrue(secrets.is_secret_file("config/.env"))
        self.assertTrue(secrets.is_secret_file("keys/server.pem"))
        self.assertFalse(secrets.is_secret_file(".env.example"))


class SymbolsTests(unittest.TestCase):
    def test_spring_controller(self):
        src = '''package ru.x.web;
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    @PostMapping
    public Order create() { return null; }
    @GetMapping("/{id}")
    public Order get(@PathVariable long id) { return null; }
}'''
        st = symbols.analyze_file("OrderController.java", src, "java")
        self.assertEqual(st.package, "ru.x.web")
        self.assertIn("OrderController", [s.name for s in st.symbols])
        paths = {(e["method"], e["path"]) for e in st.endpoints}
        self.assertIn(("POST", "/api/v1/orders"), paths)
        self.assertIn(("GET", "/api/v1/orders/{id}"), paths)

    def test_python_fastapi(self):
        src = "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/products')\ndef products():\n    return []\n\nclass Product:\n    __tablename__ = 'products'\n"
        st = symbols.analyze_file("app/main.py", src, "python")
        self.assertIn(("GET", "/products"), {(e["method"], e["path"]) for e in st.endpoints})
        self.assertIn("Product", st.entities)

    def test_chunker_by_symbols(self):
        text = "\n".join(f"line {i}" for i in range(1, 121))
        chunks = CodeChunker(window=60, overlap=10).chunk(text, [symbols.SymbolSpan("A", "class", 5, 50)] if hasattr(symbols, "SymbolSpan") else [])
        self.assertTrue(chunks)


class DepsTests(unittest.TestCase):
    def test_http_kafka_and_artifact(self):
        repos = [
            deps.RepoInput("auth-service", [("src/App.java", "CODE", "java", "class App {}"),
                                            ("pom.xml", "BUILD_SCRIPT", None, "<artifactId>auth-service</artifactId>")]),
            deps.RepoInput("common-dto", [("pom.xml", "BUILD_SCRIPT", None, "<groupId>ru.x</groupId><artifactId>common-dto</artifactId>")]),
            deps.RepoInput("order-service", [
                ("src/AuthClient.java", "CODE", "java", 'RestClient http = RestClient.create("http://auth-service:8080/api");'),
                ("src/Pub.java", "CODE", "java", 'kafka.send("orders.created", event);'),
                ("pom.xml", "BUILD_SCRIPT", None, "<artifactId>order-service</artifactId><dependencies><dependency><groupId>ru.x</groupId><artifactId>common-dto</artifactId></dependency></dependencies>"),
            ]),
        ]
        links = deps.LinkExtractor(repos).extract()
        kinds = {(l.source, l.edge_type, l.target) for l in links}
        self.assertIn(("order-service", "CALLS_HTTP", "auth-service"), kinds)
        self.assertIn(("order-service", "PUBLISHES", "orders.created"), kinds)
        self.assertIn(("order-service", "DEPENDS_ON", "common-dto"), kinds)

    def test_combine(self):
        self.assertAlmostEqual(deps.combine([0.5, 0.5]), 0.75)
        self.assertLessEqual(deps.combine([0.95, 0.95, 0.95]), 0.98)


class RolesTests(unittest.TestCase):
    def test_service_and_library(self):
        svc = roles.classify(["Dockerfile", "src/main/java/App.java", "pom.xml"],
                             {"src/main/java/App.java": "@SpringBootApplication public class App { public static void main(String[] a){} }", "pom.xml": "spring-boot-starter-web"})
        self.assertEqual(svc.role, "SERVICE")
        infra = roles.classify(["docker-compose.yml", "terraform/main.tf", "helm/values.yaml"], {})
        self.assertEqual(infra.role, "INFRASTRUCTURE")


if __name__ == "__main__":
    unittest.main()
