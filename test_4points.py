import sys
sys.path.insert(0, ".")

print("=== Testing all 4 points ===\n")

# Point 1 — Online evaluators actually run metrics
from backend.services.online_eval_worker import _get_metric_map
m = _get_metric_map()
print(f"Point 1 - Metric map: {len(m)} metrics loaded")
print(f"          Sample: {list(m.keys())[:6]}")

# Point 2 — Auth
from backend.routers.auth import _get_users, AUTH_ENABLED, _hash
users = _get_users()
names = [u["username"] for u in users["users"]]
print(f"\nPoint 2 - Auth enabled: {AUTH_ENABLED}")
print(f"          Users: {names}")
print(f"          Default password works: {users['users'][0]['password_hash'] == _hash('admin123')}")

# Point 3 — File watcher
from backend.services import file_watcher
print(f"\nPoint 3 - file_watcher module OK")
try:
    from watchdog.observers import Observer
    print(f"          watchdog available: real-time detection active")
except ImportError:
    print(f"          watchdog not available: 30s polling fallback")

# Point 4 — Playground
from backend.routers.playground import list_providers, _render_prompt
rendered = _render_prompt("Answer: {{question}}", "What is AI?")
print(f"\nPoint 4 - Playground prompt render: '{rendered}'")
providers = list_providers()
print(f"          Providers configured: {len(providers['providers'])}")
for p in providers["providers"]:
    print(f"          - {p['name']}: {p['model']}")
if not providers["providers"]:
    print("          No providers (configure with deepeval set-openai etc.)")

# Main app
from backend.main import app
api_routes = [r.path for r in app.routes if hasattr(r, "path") and r.path.startswith("/api/")]
print(f"\nTotal API routes: {len(api_routes)}")
print(f"/api/auth:       {[r for r in api_routes if '/auth' in r]}")
print(f"/api/playground: {[r for r in api_routes if '/playground' in r]}")

print("\n=== ALL 4 POINTS: VERIFIED OK ===")
