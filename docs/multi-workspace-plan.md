# Multi-Workspace Desteği — Tasarım Planı

## Context
Şu anda tüm agent'lar tek bir `workspace_root` dizininde çalışıyor. Gerçek senaryoda birden fazla proje var: eski backend (YtkService), eski web (MigemPortal), yeni backend (mapeg), yeni frontend (mapeg-ui), mobil (Flutter). Farklı agent'lar farklı projelerde çalışmalı; Solution Architect gibi roller tüm projeleri görebilmeli.

**Hedef**: YAML seviyesinde workspace tanımı + node seviyesinde atama + frontend'ten yönetim.

---

## Faz 1: Veri Modeli (Entity/Config)

### 1a. Yeni dataclass: `WorkspaceConfig`

**Yeni dosya:** `entity/configs/workspace.py`

```python
@dataclass
class WorkspaceConfig(BaseConfig):
    name: str                              # dict key (parsing sırasında atanır)
    path: str                              # Mutlak dosya sistemi yolu
    description: str | None = None
    tech: List[str] = field(default_factory=list)
```

`FIELD_SPECS` ile UI form desteği: `path` (required str), `description` (text), `tech` (list[str]).

### 1b. `DesignConfig`'e `workspaces` alanı ekle

**Dosya:** `entity/configs/graph.py` (satır 272-313)

```python
class DesignConfig(BaseConfig):
    version: str
    vars: Dict[str, Any]
    graph: GraphDefinition
    workspaces: Dict[str, WorkspaceConfig] = field(default_factory=dict)  # YENİ
```

`from_dict()` güncelle (satır 306-313):
```python
workspaces_raw = optional_dict(mapping, "workspaces", path) or {}
workspaces = {}
for ws_name, ws_data in workspaces_raw.items():
    workspaces[ws_name] = WorkspaceConfig.from_dict(ws_data, path=..., name=ws_name)
graph = GraphDefinition.from_dict(...)
# Workspace referans validasyonu (node'lar parse edildikten sonra)
return cls(version=..., vars=..., graph=graph, workspaces=workspaces, path=path)
```

`FIELD_SPECS`'e ekle:
```python
"workspaces": ConfigFieldSpec(
    name="workspaces", display_name="Project Workspaces",
    type_hint="dict[str, WorkspaceConfig]", required=False,
    description="Named workspace definitions: agents reference these by name",
)
```

### 1c. `Node`'a `workspace` alanı ekle

**Dosya:** `entity/configs/node/node.py` (satır 37+, 168+)

Dataclass'a:
```python
workspace: str | List[str] | None = None  # "backend", ["backend","frontend"], "all", veya None
```

`from_dict()` satır ~182'ye:
```python
workspace_raw = mapping.get("workspace")
if isinstance(workspace_raw, str):
    workspace = workspace_raw.strip()
elif isinstance(workspace_raw, list):
    workspace = [str(w).strip() for w in workspace_raw]
else:
    workspace = None
```

Sonra `cls(...)` constructor'a `workspace=workspace` ekle (satır 216-228).

`FIELD_SPECS`'e ekle:
```python
"workspace": ConfigFieldSpec(
    name="workspace", display_name="Workspace",
    type_hint="str", required=False,
    description="Workspace name, list of names, or 'all'. Empty = default workspace.",
)
```

### 1d. `GraphConfig`'e `workspaces` alanı ekle

**Dosya:** `entity/graph_config.py` (satır 12-60)

```python
@dataclass
class GraphConfig:
    ...
    workspaces: Dict[str, Any] = field(default_factory=dict)  # YENİ
```

`from_definition()` ve `from_dict()`'e `workspaces` parametresi ekle. `to_dict()`'e de.

### 1e. `DesignConfig` → `GraphConfig` geçiş noktaları

`workspaces=design.workspaces` eklenmesi gereken 4 yer:
- `server/services/workflow_run_service.py:173` — `GraphConfig.from_definition(..., workspaces=design.workspaces)`
- `server/services/batch_run_service.py:209` — aynı
- `run.py:102` — aynı
- `runtime/sdk.py:101` — aynı

### 1f. Workspace referans validasyonu

**Dosya:** `entity/configs/graph.py` — `DesignConfig.from_dict()` sonuna:

```python
workspace_names = set(workspaces.keys())
for node in graph.nodes:
    if node.workspace is None:
        continue
    refs = [node.workspace] if isinstance(node.workspace, str) else node.workspace
    for ref in refs:
        if ref != "all" and ref not in workspace_names:
            raise ConfigError(f"node '{node.id}' references undefined workspace '{ref}'", ...)
```

---

## Faz 2: Runtime Çözümleme

### 2a. Yeni helper: `resolve_node_workspace()`

**Yeni dosya:** `runtime/workspace_resolver.py`

```python
def resolve_node_workspace(
    node_workspace: str | List[str] | None,
    workspaces: Dict[str, WorkspaceConfig],
    fallback: Path,
) -> tuple[Path, List[WorkspaceConfig]]:
    """(cwd_path, accessible_workspaces) döndürür."""

    if node_workspace is None:
        return fallback, []

    if node_workspace == "all":
        accessible = list(workspaces.values())
        paths = [Path(ws.path).resolve() for ws in accessible]
        return Path(os.path.commonpath(paths)), accessible

    if isinstance(node_workspace, str):
        ws = workspaces.get(node_workspace)
        return (Path(ws.path).resolve(), [ws]) if ws else (fallback, [])

    if isinstance(node_workspace, list):
        accessible = [workspaces[n] for n in node_workspace if n in workspaces]
        if len(accessible) == 1:
            return Path(accessible[0].path).resolve(), accessible
        paths = [Path(ws.path).resolve() for ws in accessible]
        return Path(os.path.commonpath(paths)), accessible

    return fallback, []
```

### 2b. `RuntimeBuilder.build()` güncelle

**Dosya:** `workflow/runtime/runtime_builder.py` (satır 31-48)

```python
workspaces = self.graph.config.workspaces or {}

# global_state'e ekle:
global_state["workspaces"] = workspaces
```

Mevcut `python_workspace_root` mantığı aynen kalır (geriye uyumluluk).

### 2c. `AgentNodeExecutor.execute()` güncelle

**Dosya:** `runtime/node/executor/agent_executor.py` (satır 70)

Eski:
```python
agent_config.workspace_root = self.context.global_state.get("python_workspace_root")
```

Yeni:
```python
from runtime.workspace_resolver import resolve_node_workspace
workspaces = self.context.global_state.get("workspaces", {})
fallback = self.context.global_state.get("python_workspace_root")
resolved_cwd, accessible = resolve_node_workspace(node.workspace, workspaces, fallback)
agent_config.workspace_root = resolved_cwd
agent_config._accessible_workspaces = accessible
```

### 2d. `AgentConfig`'e runtime field ekle

**Dosya:** `entity/configs/node/agent.py` (satır ~341)

```python
_accessible_workspaces: Any | None = field(default=None, init=False, repr=False)
```

### 2e. Subgraph workspace propagation

**Dosya:** `runtime/node/executor/subgraph_executor.py` (satır ~79 sonrası)

```python
parent_workspaces = self.context.global_state.get("workspaces", {})
if parent_workspaces and hasattr(subgraph, "config"):
    if not getattr(subgraph.config, "workspaces", None):
        subgraph.config.workspaces = dict(parent_workspaces)
```

**Dosya:** `workflow/graph_manager.py` (satır 103-109) — subgraph build sırasında da workspaces geçir:

```python
subgraph_config = GraphConfig.from_dict(
    ...,
    workspaces=self.graph.config.workspaces,  # YENİ
)
```

---

## Faz 3: Prompt Injection

### 3a. `ClaudeCodeProvider._build_prompt()` güncelle

**Dosya:** `runtime/node/agent/providers/claude_code_provider.py` (satır 543-549)

Mevcut `[Working Directory]` bloğunu değiştir:

```python
accessible = getattr(self.config, "_accessible_workspaces", None) or []
if accessible and workspace_root and not is_continuation:
    lines = [f"[Workspace Context]:",
             f"Working directory: {workspace_root}\n",
             "Accessible project workspaces:"]
    for ws in accessible:
        lines.append(f"  - {ws.name}: {ws.path}")
        if ws.description:
            lines.append(f"    {ws.description}")
        if ws.tech:
            lines.append(f"    Tech: {', '.join(ws.tech)}")
    if len(accessible) > 1:
        lines.append("\nUse absolute paths when working across workspaces.")
    parts.append("\n".join(lines))
elif workspace_root and not is_continuation:
    # Eski davranış (workspace tanımı yoksa)
    parts.append(f"[Working Directory]: {workspace_root}\n"
                 "Your current working directory is set to the project workspace above. "
                 "All files you create with your Write tool will be saved there. "
                 "Use relative paths for all file operations.")
```

---

## Faz 4: Frontend

### 4a. "Manage Workspaces" butonu

**Dosya:** `frontend/src/pages/WorkflowView.vue`

Menu dropdown'a (satır ~163-180 arası) yeni item ekle:
```html
<div @click="openManageWorkspacesModal" class="menu-item">Manage Workspaces</div>
```

Handler fonksiyon (vars modal pattern'ini takip et):
```javascript
const openManageWorkspacesModal = () => {
  // yamlContent.value?.workspaces varsa edit, yoksa create
  openDynamicFormGenerator('workspaces', { ... })
}
```

`FORM_GENERATOR_CONFIG`'e ekle:
```javascript
workspaces: [{ node: 'DesignConfig', field: 'workspaces' }]
```

### 4b. Node formunda workspace alanı

`Node` FIELD_SPECS'e eklenen `workspace` alanı, FormGenerator tarafından otomatik olarak text input olarak render edilecek. v1 için yeterli.

**Gelecek iyileştirme**: Workspace isimlerini YAML'dan okuyup dropdown olarak sunmak.

---

## YAML Örneği

```yaml
version: 0.4.0

workspaces:
  legacy-backend:
    path: /projects/YtkService
    description: "Mevcut Java/Spring backend - Oracle DB, REST API"
    tech: [java, spring-boot, oracle]
  new-backend:
    path: /projects/mapeg
    description: "Yeni Kotlin backend - PostgreSQL, GraphQL + REST"
    tech: [kotlin, spring-boot, postgresql]
  new-web:
    path: /projects/mapeg-ui
    description: "Vue.js 3 frontend"
    tech: [vue3, typescript, vite]
  mobile:
    path: /projects/mobil-uygulama
    description: "Flutter mobil uygulama"
    tech: [flutter, dart]

graph:
  nodes:
    - id: Solution Architect
      type: agent
      workspace: all
      config:
        provider: claude-code
        name: opus
        role: ...

    - id: Backend Developer
      type: agent
      workspace: new-backend
      config:
        provider: claude-code
        name: sonnet
        role: ...

    - id: Frontend Developer
      type: agent
      workspace: new-web
      config:
        provider: claude-code
        name: sonnet
        role: ...

    - id: Full Stack Dev
      type: agent
      workspace: [new-backend, new-web]
      config: ...
```

---

## Dosya Değişiklik Listesi

| # | Dosya | Değişiklik |
|---|-------|------------|
| 1 | `entity/configs/workspace.py` | **YENİ** — WorkspaceConfig dataclass |
| 2 | `entity/configs/__init__.py` | WorkspaceConfig export |
| 3 | `entity/configs/graph.py` | DesignConfig'e `workspaces` alanı + from_dict parsing + validasyon |
| 4 | `entity/configs/node/node.py` | Node'a `workspace` alanı + from_dict parsing + FIELD_SPECS |
| 5 | `entity/configs/node/agent.py` | `_accessible_workspaces` runtime field |
| 6 | `entity/graph_config.py` | GraphConfig'e `workspaces` field + from_definition/from_dict/to_dict |
| 7 | `runtime/workspace_resolver.py` | **YENİ** — `resolve_node_workspace()` helper |
| 8 | `workflow/runtime/runtime_builder.py` | global_state'e `workspaces` ekle |
| 9 | `runtime/node/executor/agent_executor.py` | Per-node workspace çözümleme (satır 70) |
| 10 | `runtime/node/executor/subgraph_executor.py` | Workspace propagation |
| 11 | `workflow/graph_manager.py` | Subgraph build'e workspaces geçir |
| 12 | `runtime/node/agent/providers/claude_code_provider.py` | Workspace context prompt injection |
| 13 | `server/services/workflow_run_service.py` | workspaces'i GraphConfig'e geçir |
| 14 | `server/services/batch_run_service.py` | workspaces'i GraphConfig'e geçir |
| 15 | `run.py` | workspaces'i GraphConfig'e geçir |
| 16 | `runtime/sdk.py` | workspaces'i GraphConfig'e geçir |
| 17 | `frontend/src/pages/WorkflowView.vue` | "Manage Workspaces" butonu + FORM_GENERATOR_CONFIG |

---

## Uygulama Sırası

1. **Faz 1** (Entity): workspace.py → graph.py → node.py → agent.py → graph_config.py → __init__.py
2. **Faz 2** (Runtime): workspace_resolver.py → runtime_builder.py → agent_executor.py → subgraph_executor.py → graph_manager.py
3. **Faz 3** (Prompt): claude_code_provider.py
4. **Faz 4** (Geçiş noktaları): workflow_run_service.py, batch_run_service.py, run.py, sdk.py
5. **Faz 5** (Frontend): WorkflowView.vue

---

## Geriye Uyumluluk

- `workspaces` tanımlanmamış YAML'lar: `DesignConfig.workspaces = {}`, `Node.workspace = None`
- `resolve_node_workspace(None, {}, fallback)` → `(fallback, [])` → mevcut davranış
- `_accessible_workspaces = None/[]` → prompt'a workspace context eklenmez
- Hiçbir mevcut YAML bozulmaz

---

## Doğrulama

1. **Syntax**: `python -c "import ast; ast.parse(open('dosya').read())"` her değiştirilen .py dosyası için
2. **Parse testi**: Workspaces'li örnek YAML'ı `load_design_from_file()` ile yükle, `DesignConfig.workspaces` dict'inin doğru parse edildiğini kontrol et
3. **Workspace çözümleme**: `resolve_node_workspace()` unit testleri — single, multi, all, None, tanımsız isim
4. **Referans validasyon**: Node'da tanımsız workspace adı → `ConfigError`
5. **Prompt injection**: Workspace'li config ile `_build_prompt()` çağrısı → çıktıda `[Workspace Context]` bloğu var mı
6. **Frontend**: YAML editöründe "Manage Workspaces" butonu → FormGenerator açılmalı
7. **Geriye uyumluluk**: Mevcut `iterative_dev_v1.yaml` (workspaces yok) → hatasız yüklenmeli

---

## Açık Sorular / Düşünülecekler

1. **Agent ekibi genişlemesi**: 20 farklı rol (PM, BA, Architect, Backend Dev, Frontend Dev, Mobile Dev, QA, DevOps, SRE, Security...) nasıl organize edilecek? Katmanlı subgraph yapısı mı?
2. **Workspace erişim kısıtlaması**: Agent'ın sadece kendi workspace'ine write access, diğerlerine read-only access vermek mümkün mü? (Claude Code'da `--allowedTools` ile kısıtlanabilir potansiyel olarak)
3. **Workspace değişkenlerinin çözümlenmesi**: `path: ${PROJECT_ROOT}/mapeg` gibi değişken kullanımı desteklenmeli mi?
4. **Frontend dropdown**: v2'de node formundaki workspace alanı için YAML'dan dinamik enum (dropdown) oluşturulabilir
