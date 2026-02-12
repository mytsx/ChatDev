# Agent Thought Bubbles: Gerçek Zamanlı Agent Aktivitesi Görüntüleme

## Context

Workflow çalışırken agent'ların ne yaptığı kullanıcıya görünmüyor. Şu an UI'da sadece:
- `Tool claude:Read 2.3s` gibi isim + süre gösteren loading pill'leri var
- Agent'ın çıktısı NODE_END'de TEK SEFERDE görünüyor
- Hangi dosyayı okuduğu, ne komut çalıştırdığı, ne düşündüğü GÖRÜNMÜYOR

**Hedef:** Agent'ların tool call detaylarını (dosya yolu, komut, pattern) ve reasoning metnini gerçek zamanlı göstermek.

**Mevcut Durum:** Backend zaten tool arguments'ı (`file_path`, `command`, `pattern`, `thought`) WebSocket event'inin `details.arguments` alanında gönderiyor — frontend sadece göstermiyor. Text blokları ise hiç stream edilmiyor.

---

## Değişiklik Özeti

| # | Değişiklik | Dosya | Zorluk |
|---|---|---|---|
| 1 | Loading pill'lere tool detayı ekle | `LaunchView.vue` | Kolay |
| 2 | Text blokları için `text_delta` callback ekle | `claude_code_provider.py` | Kolay |
| 3 | `AGENT_TEXT` event type + logger method | `entity/enums.py`, `utils/logger.py`, `utils/log_manager.py` | Kolay |
| 4 | `_stream_callback`'e text_delta + tool_detail desteği | `agent_executor.py` | Orta |
| 5 | Frontend: AGENT_TEXT handler + reasoning alanı | `LaunchView.vue` | Orta |

---

## Fix 1: Loading Pill'lere Tool Detayı Ekle (Frontend)

**Dosya: `frontend/src/pages/LaunchView.vue`**

### 1a. `addLoadingEntry` fonksiyonuna `detail` parametresi (satır 598)

```js
// Eski
const addLoadingEntry = (nodeId, baseKey, label) => {

// Yeni
const addLoadingEntry = (nodeId, baseKey, label, detail = '') => {
```

Entry objesine `detail` field ekle:
```js
const entry = {
  key, baseKey, label,
  detail,          // YENİ: dosya yolu, komut, pattern vb.
  status: 'running',
  startedAt: Date.now(),
  endedAt: null
}
```

### 1b. TOOL_CALL handler'da detail'ı parse et (satır 2151-2163)

```js
else if (eventType === 'TOOL_CALL') {
  if (msg.data.details.stage === "before") {
    const baseKey = `tool-${msg.data.details.tool_name || 'unknown'}`
    const detail = msg.data.details.tool_detail || ''  // YENİ
    addLoadingEntry(nodeId, baseKey, `Tool ${msg.data.details.tool_name}`, detail)
  }
  if (msg.data.details.stage === "after") {
    const baseKey = `tool-${msg.data.details.tool_name || 'unknown'}`
    finishLoadingEntry(nodeId, baseKey)
  }
}
```

### 1c. Template'de detail span'ı göster (satır 71-83)

Mevcut loading-entry div'ine ekle:
```html
<span v-if="entry.detail" class="loading-entry-detail">{{ entry.detail }}</span>
```

### 1d. CSS

```css
.loading-entry-detail {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  font-family: ui-monospace, SFMono-Regular, SF Mono, Menlo, monospace;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

**Sonuç:** `Tool claude:Read 2.3s` → `Tool claude:Read filter.py 2.3s`

---

## Fix 2: Backend — Text Delta Callback (Provider)

**Dosya: `runtime/node/agent/providers/claude_code_provider.py` satır ~378-385**

`_run_streaming()` içinde text blokları işlenirken callback ekle:

```python
elif block.get("type") == "text":
    text = block.get("text", "")
    if text:
        accumulated_text.append(text)
        # YENİ: text_delta callback
        if stream_callback:
            stream_callback("text_delta", {"text": text})
    if pending_tool and stream_callback:
        stream_callback("tool_end", pending_tool)
        pending_tool = None
```

---

## Fix 3: AGENT_TEXT Event Type + Logger Method

### 3a. EventType enum'a ekle

**Dosya: `entity/enums.py`**

```python
class EventType(str, Enum):
    # ... mevcut ...
    AGENT_TEXT = "AGENT_TEXT"  # YENİ
```

### 3b. WorkflowLogger'a method ekle

**Dosya: `utils/logger.py` (satır ~289 sonrası)**

```python
def record_agent_text(self, node_id: str, text: str) -> None:
    """Record a chunk of agent reasoning text for real-time streaming."""
    self.add_log(
        LogLevel.INFO,
        f"Agent text for node {node_id}",
        node_id=node_id,
        event_type=EventType.AGENT_TEXT,
        details={"text": text},
    )
```

### 3c. LogManager shim

**Dosya: `utils/log_manager.py` (satır ~165 sonrası)**

```python
def record_agent_text(self, node_id: str, text: str) -> None:
    """Record agent reasoning text."""
    self.logger.record_agent_text(node_id, text)
```

---

## Fix 4: Stream Callback'i Zenginleştir (Agent Executor)

**Dosya: `runtime/node/executor/agent_executor.py` satır 300-348**

### 4a. `_extract_tool_detail` helper fonksiyonu (modül seviyesi)

```python
def _extract_tool_detail(tool_name: str, tool_input: dict) -> str:
    """Tool input'tan okunabilir kısa detay çıkar."""
    file_path = tool_input.get("file_path", tool_input.get("path", ""))
    if file_path:
        return file_path.rsplit("/", 1)[-1]  # sadece dosya adı

    command = tool_input.get("command", "")
    if command:
        return command[:80] + ("..." if len(command) > 80 else "")

    pattern = tool_input.get("pattern", "")
    if pattern:
        return f'"{pattern[:60]}"'

    query = tool_input.get("query", "")
    if query:
        return query[:60] + ("..." if len(query) > 60 else "")

    url = tool_input.get("url", "")
    if url:
        return url[:80]

    thought = tool_input.get("thought", "")
    if thought:
        return thought[:80] + ("..." if len(thought) > 80 else "")

    return ""
```

### 4b. `_stream_callback` içinde tool_detail ve text_delta desteği

tool_start ve tool_end details'a `"tool_detail": detail` ekle.

text_delta için yeni branch:
```python
elif event_type == "text_delta":
    text = data.get("text", "")
    if text.strip():
        self.log_manager.record_agent_text(node.id, text)
```

---

## Fix 5: Frontend — Reasoning Alanı

**Dosya: `frontend/src/pages/LaunchView.vue`**

### 5a. AGENT_TEXT handler (processMessage içinde, TOOL_CALL'dan sonra)

```js
else if (eventType === 'AGENT_TEXT') {
  const text = msg.data.details?.text || ''
  if (text.trim() && nodeId) {
    updateAgentThought(nodeId, text)
  }
}
```

### 5b. `updateAgentThought` fonksiyonu

```js
const updateAgentThought = (nodeId, text) => {
  const nodeState = addTotalLoadingMessage(nodeId)
  if (!nodeState) return

  if (!nodeState.message.agentThought) {
    nodeState.message.agentThought = ''
  }
  nodeState.message.agentThought += text

  // Çok uzarsa son kısmı tut
  const MAX_LEN = 2000
  if (nodeState.message.agentThought.length > MAX_LEN) {
    nodeState.message.agentThought = '...' +
      nodeState.message.agentThought.slice(-MAX_LEN)
  }
}
```

### 5c. NODE_END'de temizle

Mevcut NODE_END handler'ında nodeState temizlemesine ekle:
```js
if (nodeState) {
  nodeState.message.agentThought = ''  // YENİ
  // ... mevcut finalize kodu ...
}
```

### 5d. Template — Reasoning alanı (loading entries'den sonra, ~satır 84)

```html
<!-- Agent reasoning text -->
<div v-if="message.agentThought" class="agent-reasoning">
  <CollapsibleMessage
    :html-content="renderMarkdown(message.agentThought)"
    :raw-content="message.agentThought"
    :max-height="120"
    :default-expanded="true"
  />
</div>
```

### 5e. CSS

```css
.agent-reasoning {
  margin: 8px 0 4px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.03);
  border-left: 2px solid rgba(153, 234, 249, 0.4);
  border-radius: 0 6px 6px 0;
}
```

---

## Sonuç: Kullanıcı Ne Görecek

**Önce (mevcut):**
```
[Avatar] Solution Architect                    12:34
[loading bubble]
  Tool claude:Read     2.3s
  Tool claude:Bash     1.1s
  Model claude-sonnet  45.2s
                            [120s]
```

**Sonra (yeni):**
```
[Avatar] Solution Architect                    12:34
[loading bubble]
  Tool claude:Read filter.py          2.3s
  Tool claude:Bash npm test           1.1s
  Tool claude:Grep "auth pattern"     0.8s

  Şimdi filtreleme sistemi için mimari dokümanı
  yazıyorum. Mevcut kod yapısını analiz ettim...

  Model claude-sonnet  45.2s
                            [120s]
```

---

## Kritik Dosyalar

| Dosya | Değişiklik |
|---|---|
| `entity/enums.py` | `AGENT_TEXT` enum member |
| `utils/logger.py` | `record_agent_text()` method |
| `utils/log_manager.py` | `record_agent_text()` shim |
| `runtime/node/agent/providers/claude_code_provider.py` | `text_delta` callback (1 satır) |
| `runtime/node/executor/agent_executor.py` | `_extract_tool_detail()` + text_delta handler |
| `frontend/src/pages/LaunchView.vue` | detail param, AGENT_TEXT handler, reasoning template, CSS |

---

## Doğrulama

1. **Mevcut testler**: `uv run pytest tests/ -x -q`
2. **Frontend build**: `cd frontend && npm run build`
3. **Manuel test**: Workflow başlat, loading bubble'da tool detaylarının göründüğünü doğrula
4. **Text streaming**: Agent reasoning metninin gerçek zamanlı göründüğünü, NODE_END'de temizlendiğini doğrula
5. **Paralel node'lar**: İki paralel agent'ın thought bubble'larının karışmadığını doğrula
