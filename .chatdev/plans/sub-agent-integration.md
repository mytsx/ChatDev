# Sub-Agent Entegrasyonu — Her CLI Provider İçin Custom Agent Dosyaları

## Context

Hooks & Skills implementasyonu tamamlandı. Şimdi her agent'ın kendi işine yarayacak sub-agent'ları (yardımcı agent'lar) tanımlayıp workspace'e yazacağız. CLI provider'lar sub-agent dosyalarını otomatik keşfeder ve ana agent'a tool olarak sunar. Role prompt'larda sub-agent'lardan bahsedilecek ki agent bunları kullanması gerektiğinde kullansın.

**Sub-agent dosya konumları:**
- Claude Code: `.claude/agents/{name}.md` (YAML frontmatter)
- Gemini CLI: `.gemini/agents/{name}.md` (YAML frontmatter)
- Copilot CLI: `.github/agents/{name}.md` (metadata)

**Koruma kuralı:** Mevcut instruction file'lar gibi — workspace'te zaten varsa DOKUNMA, cleanup'ta sadece bizim oluşturduklarımızı sil.

---

## Sub-Agent Tasarımı (Her Role İçin)

### Developer → 2 sub-agent
1. **code-researcher**: API/framework doc araştırması. Kodlamadan ÖNCE doğru API kullanımını doğrular. Read-only tools.
2. **test-writer**: Yazılan kod için unit test üretir. Read + Write tools.

### Reviewer → 2 sub-agent
1. **security-scanner**: OWASP Top 10 odaklı güvenlik taraması. Read-only.
2. **complexity-analyzer**: Fonksiyon uzunluğu, nesting, cyclomatic complexity analizi. Read-only.

### QA Engineer → 2 sub-agent
1. **test-generator**: Requirements'tan edge case test senaryoları üretir. Read + Write.
2. **bug-analyzer**: Test failure'ların root cause analizi. Read-only.

### Architect → 1 sub-agent
1. **tech-researcher**: Framework/library karşılaştırması, versiyon uyumluluğu araştırması. Read-only.

### Technical Writer → 1 sub-agent
1. **api-documenter**: Koddan API endpoint'lerini extract edip dokümante eder. Read-only.

### Product Analyst → 0 sub-agent (zaten Exa Search MCP var)
### DevOps → 0 sub-agent (scope küçük, sub-agent gereksiz)

---

## Implementation Plan

### Step 1: SubAgentConfig Schema
**Dosya:** `entity/configs/node/hooks.py` — yeni dataclass ekle

```python
@dataclass
class SubAgentConfig(BaseConfig):
    name: str            # "code-researcher" (lowercase, hyphens)
    description: str     # "Research API docs and verify correct usage"
    prompt: str          # Sub-agent system prompt (markdown body)
    tools: List[str]     # ["Read", "Grep", "Glob"]
    model: str | None    # "haiku", "sonnet" (None = inherit)
    max_turns: int = 15  # Default turn limit
```

### Step 2: AgentConfig'e sub_agents alanı ekle
**Dosya:** `entity/configs/node/agent.py`
- `sub_agents: List[SubAgentConfig] = []` alanı ekle
- `from_dict()` parsing
- `FIELD_SPECS` entry

### Step 3: Sub-agent MD şablon dosyaları oluştur
**Dizin:** `.chatdev/workflows/agile_dev/agents/`
- `code-researcher.md`, `test-writer.md`
- `security-scanner.md`, `complexity-analyzer.md`
- `test-generator.md`, `bug-analyzer.md`
- `tech-researcher.md`
- `api-documenter.md`

Her dosya YAML frontmatter + markdown body içerir.

### Step 4: HookSkillManager'a sub-agent üretimi ekle

**Dosya:** `runtime/node/agent/providers/hook_skill_manager.py`

- `GeneratedFiles`'a `sub_agent_files: List[str]` alanı ekle
- `generate()`'a `sub_agents` parametresi ekle
- Provider-specific sub-agent dosyası üretimi:
  - Claude: `.claude/agents/{name}.md`
  - Gemini: `.gemini/agents/{name}.md`
  - Copilot: `.github/agents/{name}.md`
- `cleanup()` — oluşturulan sub-agent dosyalarını sil (mevcut olanları korur)

Format farkları:
```
# Claude Code frontmatter:
---
name: code-researcher
description: Research API docs
tools: Read, Grep, Glob
model: haiku
maxTurns: 15
---

# Gemini CLI frontmatter:
---
name: code-researcher
description: Research API docs
tools: [read_file, grep_search, list_directory]
model: gemini-2.5-flash
max_turns: 15
---

# Copilot CLI format:
---
name: code-researcher
description: Research API docs
tools: Read, Grep, Glob
model: claude-sonnet-4
---
```

### Step 5: CLI Provider Base'de sub-agent parametresini ilet
**Dosya:** `runtime/node/agent/providers/cli_provider_base.py`
- `call_model()`'da `sub_agents` config'i `hook_manager.generate()`'a geç

### Step 6: agile_dev.yaml'da sub-agent tanımları + role prompt güncellemesi
- Her agent'a `sub_agents` listesi ekle (dosya yolları ile)
- Role prompt'ların sonuna sub-agent hatırlatması ekle

### Step 7: Unit testler
**Dosya:** `tests/test_hook_skill_manager.py` — yeni test class'ları
- Sub-agent dosya üretimi (her provider)
- Mevcut dosyayı ezmeme kontrolü
- Cleanup sonrası silme
- Frontmatter format doğruluğu

---

## Dosya Değişiklikleri

### Yeni Dosyalar
| Dosya | Amaç |
|-------|------|
| `.chatdev/workflows/agile_dev/agents/*.md` | 8 sub-agent tanım dosyası |

### Değiştirilecek Dosyalar
| Dosya | Değişiklik |
|-------|-----------|
| `entity/configs/node/hooks.py` | `SubAgentConfig` dataclass |
| `entity/configs/node/agent.py` | `sub_agents` alanı |
| `entity/configs/node/__init__.py` | Export |
| `entity/configs/__init__.py` | Export |
| `runtime/node/agent/providers/hook_skill_manager.py` | Sub-agent file generation + cleanup |
| `runtime/node/agent/providers/cli_provider_base.py` | `sub_agents` parametresi iletimi |
| `yaml_instance/agile_dev.yaml` | Sub-agent config + role prompt update |
| `tests/test_hook_skill_manager.py` | Sub-agent testleri |

---

## Verification

```bash
.venv/bin/python -m pytest tests/test_hook_skill_manager.py -v
.venv/bin/python -m pytest tests/ -v  # Regression check
```

- Tüm 3 provider için sub-agent dosyası üretildiğini doğrula
- Mevcut sub-agent dosyası varsa ezilmediğini doğrula
- Cleanup sonrası dosyaların silindiğini doğrula
- agile_dev.yaml parse edilebilir olmalı
