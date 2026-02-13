# Inter-Agent Real-Time Communication (Agent Comm)

## Context

ChatDev workflow engine'de agent'lar şu an sadece **edge'ler aracılığıyla**, **sıralı olarak** (bir node bitince diğerine) haberleşiyor. Paralel çalışan agent'lar birbirlerinden tamamen izole — çalışma sırasında soru soramıyor, bilgi paylaşamıyor. Kullanıcı, [mytsx/agent-chat](https://github.com/mytsx/agent-chat) projesinden ilham alarak:

1. Agent'ların **çalışırken** birbirine soru sorabilmesini
2. **Team Lead** tarafından yönetilen akıllı mesaj routing'i
3. **"Always alive"** takım konseptini (biten agent'lar da sorulara cevap verebilmeli)

istiyor. Bu plan, mevcut MCP forwarding altyapısı üzerine in-process message bus + MCP server mimarisi ile bunu gerçekleştiriyor.

---

## Mimari Özet

```
Agent (CLI subprocess)
  │  ask_team("API formatı ne?", "Backend Dev")
  ▼
MCP Tool Call → agent_comm.py (stdio MCP server)
  │  HTTP POST /api/internal/agent-comm
  ▼
FastAPI Endpoint → server/routes/internal.py
  │  bus.ask_and_wait(from, to, question, timeout=120)
  ▼
AgentMessageBus (thread-safe, in global_state)
  │  _route_message() → Team Lead filter? → deliver to inbox
  ▼
Target Agent → check_messages() → reply_to_message()
  │  bus.send_response(correlation_id, answer)
  ▼
Asking Agent ← Event.set() ← response returned
```

**Neden bu mimari?**
- Tüm 3 CLI provider (Claude, Gemini, Copilot) MCP tool'larını doğal kullanıyor
- Mevcut `chatdev_reporter.py` paterni birebir takip ediliyor
- Harici servis yok (Redis, dosya kuyruğu vs.) — tamamen in-process
- Thread-safe: paralel node'lar `ThreadPoolExecutor`'da çalışıyor

---

## Faz 1: Core Message Bus + MCP Server

### 1.1 — AgentMessageBus (yeni)
**Dosya:** `runtime/comm/agent_message_bus.py`

Thread-safe in-process message broker. `global_state["_agent_message_bus"]` içinde yaşar.

**Veri yapıları** (`runtime/comm/models.py`):
```python
class AgentStatus(Enum):
    RUNNING, IDLE, FINISHED, WARM  # WARM = bitti ama session canlı

class MessageType(Enum):
    QUESTION, RESPONSE, INFO, BROADCAST, STATUS_UPDATE

class DeliveryStatus(Enum):
    PENDING, ROUTED, DELIVERED, ANSWERED, EXPIRED, REJECTED

@dataclass
class AgentRegistration:
    node_id: str
    agent_role: str       # "Backend Developer"
    provider: str         # "claude-code"
    status: AgentStatus
    current_task: str
    session_id: str | None
    scc_id: str | None    # Cycle group membership
    layer: int            # Topological layer
    registered_at: float
    last_activity: float

@dataclass
class InterAgentMessage:
    id: str               # UUID
    type: MessageType
    from_agent: str
    to_agent: str | None  # None = team lead karar verir
    content: str
    correlation_id: str | None  # request/response eşleştirme
    created_at: float
    expires_at: float | None
    priority: int         # 0=normal, 1=urgent (team lead bypass)
    status: DeliveryStatus
    response: str | None
    metadata: dict        # chain_depth, etc.
```

**AgentMessageBus core API:**
```python
class AgentMessageBus:
    def __init__(self, config: InterAgentCommConfig)
    # Registration
    def register_agent(node_id, role, provider, scc_id, layer)
    def unregister_agent(node_id)
    def update_status(node_id, status, task="")
    def get_all_agents() -> Dict[str, AgentRegistration]
    # Messaging
    def send_message(msg: InterAgentMessage) -> str
    def check_inbox(node_id, limit=10) -> List[InterAgentMessage]
    def send_response(correlation_id, from_agent, content)
    # Blocking ask
    def ask_and_wait(from_agent, to_agent, question, timeout=120) -> str | None
    # Shutdown
    def shutdown()
```

**Threading modeli:**
- Tek `threading.RLock` tüm mutasyonlar için (operasyonlar hızlı: dict lookup, deque append)
- `ask_and_wait`: per-correlation `threading.Event` kullanır → bekleme sırasında ana lock tutulmaz
- Her agent'ın kendi `deque[InterAgentMessage]` inbox'ı var

**Loop prevention:**
- Rate limit: max 10 mesaj/dakika/agent
- Chain depth: `metadata["chain_depth"]` max 3 (A→B→A→B... engeller)
- TTL: Mesajlar default 120s sonra expire olur
- Duplicate detection: `(from, to, content_hash)` sliding window

### 1.2 — Inter-Agent MCP Server (yeni)
**Dosya:** `mcp_servers/agent_comm.py`

`chatdev_reporter.py` ile birebir aynı pattern: FastMCP + HTTP POST.

**Env vars** (cli_provider_base `_create_mcp_config`'den gelir):
- `CHATDEV_SERVER_URL`, `CHATDEV_SESSION_ID`, `CHATDEV_NODE_ID`, `CHATDEV_AGENT_ROLE`

**5 MCP tool:**

| Tool | Açıklama | Blocking? |
|------|----------|-----------|
| `ask_team(question, target_agent?)` | Soru sor, cevap bekle | Evet (max 120s) |
| `tell_team(message, target_agent?)` | Bilgi paylaş, cevap bekleme | Hayır |
| `check_messages()` | Gelen mesajları oku | Hayır |
| `reply_to_message(reply_id, response)` | Soruya cevap ver | Hayır |
| `get_team_status()` | Takım durumunu gör | Hayır |

### 1.3 — HTTP Bridge Endpoint
**Dosya:** `server/routes/internal.py` (mevcut, ekleme)

Yeni endpoint: `POST /api/internal/agent-comm`

```python
class AgentCommPayload(BaseModel):
    session_id: str
    node_id: str
    action: str  # "ask", "tell", "check", "reply", "team_status"
    question: str | None = None
    message: str | None = None
    target_agent: str | None = None
    correlation_id: str | None = None
    response: str | None = None
```

`ask` action → `asyncio.run_in_executor(None, bus.ask_and_wait, ...)` → blocking thread, async event loop bloke olmaz.

### 1.4 — MCP Config Injection
**Dosya:** `runtime/node/agent/providers/cli_provider_base.py` (değişiklik)

`_create_mcp_config()` (satır ~748): `chatdev-reporter` bloğunun hemen altına `chatdev-agent-comm` ekle:

```python
# Inter-agent communication MCP server (conditional)
agent_comm_path = str(
    Path(__file__).resolve().parents[4] / "mcp_servers" / "agent_comm.py"
)
if session_id and Path(agent_comm_path).exists():
    # Only add if inter-agent comm is enabled in global_state
    # (checked via a class-level flag set during executor init)
    if getattr(self, '_inter_agent_comm_enabled', False):
        servers["chatdev-agent-comm"] = {
            "command": "python",
            "args": [agent_comm_path],
            "env": {
                "CHATDEV_SERVER_URL": f"http://127.0.0.1:{server_port}",
                "CHATDEV_SESSION_ID": session_id,
                "CHATDEV_NODE_ID": node_id,
                "CHATDEV_AGENT_ROLE": getattr(self, '_agent_role', ''),
            },
        }
```

### 1.5 — GraphExecutor Entegrasyonu
**Dosya:** `workflow/graph.py` (değişiklik)

`run()` metodu (satır ~280, `_build_memories_and_thinking()` sonrası):

```python
self._init_inter_agent_comm()
```

```python
def _init_inter_agent_comm(self) -> None:
    comm_config = self.graph.config.metadata.get("inter_agent_comm")
    if not comm_config or not comm_config.get("enabled"):
        return
    from runtime.comm.agent_message_bus import AgentMessageBus
    from runtime.comm.models import InterAgentCommConfig
    config = InterAgentCommConfig.from_dict(comm_config)
    bus = AgentMessageBus(config)
    # SCC membership bilgisini doldur (bypass kuralları için)
    if self.cycle_manager:
        for cycle_id, info in self.cycle_manager.cycles.items():
            for nid in info.nodes:
                bus.set_scc_membership(nid, cycle_id)
    # Layer bilgisi
    for idx, layer in enumerate(self.graph.layers):
        for nid in layer:
            bus.set_layer(nid, idx)
    ctx = self._get_execution_context()
    ctx.global_state["_agent_message_bus"] = bus
```

`run()` finally bloğunda: `bus.shutdown()` çağır.

### 1.6 — Agent Executor Entegrasyonu
**Dosya:** `runtime/node/executor/agent_executor.py` (değişiklik)

`execute()` başında (satır ~190 civarı):
```python
bus = self.context.global_state.get("_agent_message_bus")
if bus:
    bus.register_agent(node.id, node.role or node.id, agent_config.provider)
    bus.update_status(node.id, AgentStatus.RUNNING, "Starting execution")
```

`execute()` sonunda (finally):
```python
if bus:
    bus.update_status(node.id, AgentStatus.WARM, "Finished, available for Q&A")
```

### 1.7 — Prompt Injection
**Dosya:** `runtime/node/agent/providers/cli_provider_base.py` (değişiklik)

`_build_prompt()` (satır ~613): `inter_agent_comm_enabled` ise prompt'a ek bölüm:

```
[Team Communication]:
You have tools to communicate with teammates:
- ask_team(question, target_agent?): Ask and wait for answer (use sparingly)
- tell_team(message, target_agent?): Share info without waiting
- check_messages(): Check incoming messages periodically
- reply_to_message(reply_id, response): Reply to a question
- get_team_status(): See who's online
GUIDELINES: Don't ask what you can answer yourself. Keep messages concise.
Check messages every few tool calls during long tasks.
```

---

## Faz 2: Team Lead Routing

### 2.1 — Team Lead MCP Tools (ek)
**Dosya:** `mcp_servers/agent_comm.py` (ekleme)

Team Lead node_id `CHATDEV_TEAM_LEAD=true` env var ile tanınır. Ek tool'lar:

```python
@mcp.tool  # Sadece team lead'de aktif
def review_pending_messages() -> str
def approve_message(message_id, modified_content="") -> str
def reject_message(message_id, reason="") -> str
def route_message(message_id, target_agent) -> str
```

### 2.2 — Routing Mantığı
**Dosya:** `runtime/comm/agent_message_bus.py` (ekleme)

`_route_message()` kararları:
1. **Bypass team lead** (direkt ilet):
   - `priority == 1` (urgent)
   - `type == RESPONSE` veya `STATUS_UPDATE`
   - Sender ve receiver aynı SCC'de (cycle group)
   - Sender ve receiver aynı layer'da (paralel)
   - Team lead FINISHED durumda ve resume callback yok
2. **Team lead'e yönlendir**: Diğer tüm mesajlar team lead'in review inbox'ına gider
3. **Auto-approve**: Team lead 30s içinde karar vermezse otomatik onay

### 2.3 — Smart Auto-Routing
`target_agent` boş olduğunda bus, agent_role ve current_task'tan keyword eşleştirme yaparak en uygun agent'ı seçer. Belirsizse team lead'e yönlendirir.

---

## Faz 3: Always-Alive Pattern

### 3.1 — Resume Callback
**Dosya:** `runtime/node/executor/agent_executor.py` (ekleme)

Agent bitince resume callback register eder:

```python
def _create_resume_callback(self, node, provider, agent_config, workspace_root):
    def resume_for_question(question: str) -> str:
        session_id = provider.get_session(node.id)
        if not session_id:
            return "(Agent session expired)"
        client = provider.create_client()
        prompt = f"A teammate asks: {question}\nAnswer concisely."
        cmd = provider._build_resume_command(client, session_id, prompt, None, 5)
        raw, _ = provider._run_streaming(cmd, workspace_root, 60, None, idle_timeout=30)
        return raw.get("result", "(no answer)")
    return resume_for_question
```

`AgentMessageBus._deliver_to_inbox()`: Eğer target WARM ise ve mesaj QUESTION ise, resume callback çalıştırılır (ayrı thread'de).

### 3.2 — Warm Agent TTL
- Default 300s inaktivite sonrası WARM → FINISHED geçişi
- FINISHED agent'lara soru sorulursa: "(Agent no longer available)"
- Workflow bittiğinde `bus.shutdown()` tüm callback'leri temizler

---

## YAML Konfigürasyon

```yaml
graph:
  id: fullstack_dev
  inter_agent_comm:
    enabled: true
    team_lead: "Architect"           # routing coordinator
    max_messages_per_minute: 10
    ask_timeout: 120                 # seconds
    warm_agent_ttl: 300              # seconds
    bypass_same_scc: true            # aynı cycle'da direkt iletişim
    bypass_same_layer: true          # paralel node'lar arası direkt
```

---

## Dosya Listesi

| Faz | Dosya | İşlem |
|-----|-------|-------|
| 1 | `runtime/comm/__init__.py` | Yeni |
| 1 | `runtime/comm/models.py` | Yeni (~80 satır) |
| 1 | `runtime/comm/agent_message_bus.py` | Yeni (~350 satır) |
| 1 | `mcp_servers/agent_comm.py` | Yeni (~120 satır) |
| 1 | `server/routes/internal.py` | Değişiklik (+80 satır) |
| 1 | `runtime/node/agent/providers/cli_provider_base.py` | Değişiklik (+25 satır) |
| 1 | `workflow/graph.py` | Değişiklik (+30 satır) |
| 1 | `runtime/node/executor/agent_executor.py` | Değişiklik (+15 satır) |
| 2 | `mcp_servers/agent_comm.py` | Ekleme (+60 satır, team lead tools) |
| 2 | `runtime/comm/agent_message_bus.py` | Ekleme (+100 satır, routing) |
| 3 | `runtime/node/executor/agent_executor.py` | Ekleme (+30 satır, resume callback) |
| 3 | `runtime/comm/agent_message_bus.py` | Ekleme (+50 satır, warm delivery) |

---

## Doğrulama

### Birim Testler
1. `AgentMessageBus`: register/unregister, send/check, ask_and_wait timeout, rate limiting, loop prevention
2. `InterAgentMessage` serialization/deserialization
3. Routing: bypass rules (same SCC, same layer, urgent)
4. Team lead: approve/reject/route flow

### Entegrasyon Testleri
1. MCP server `agent_comm.py` → HTTP bridge → bus → response cycle (mock bus)
2. Paralel 2 agent: Agent A `ask_team` → Agent B `check_messages` + `reply_to_message` → Agent A response alır
3. WARM agent resume: Agent biter → `ask_team` → resume callback → cevap döner
4. Team lead routing: Agent A mesaj → team lead review → approve → Agent B teslim

### Manuel Test
1. `fullstack_dev.yaml`'a `inter_agent_comm: { enabled: true, team_lead: "Architect" }` ekle
2. Backend Developer + Frontend Developer paralel çalışırken `ask_team` ile birbirine soru sorsun
3. UI'da (WebSocket) mesaj akışını gözlemle
