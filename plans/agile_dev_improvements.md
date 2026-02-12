# Agile Dev Workflow: 5 İyileştirme

## Context

`agile_dev.yaml` oluşturuldu (7 agent, 12 node, 21 edge). 5 iyileştirme uygulanacak:

1. **Gitignore Filtering**: Snapshot'a `.gitignore`'daki dosyalar dahil oluyor → prompt patlıyor
2. **Scope Creep**: Agent'lar kapsam dışına çıkıp başka yerleri "iyileştiriyor"
3. **Conditional Execution**: Basit bugfix için tüm pipeline gereksiz çalışıyor
4. **Generated Duplikasyon**: Tüm değişen dosyalar base64 encode + `generated/` altına kopyalanıyor → 859MB israf
5. **Plan Approval Bypass**: Her görev için insan onayı gereksiz — basit görevlerde otomatik geçilmeli

---

## Değişiklik 1: Gitignore Filtering (Engine Değişikliği)

### Problem
`_snapshot_workspace()` sadece hardcoded exclusion listesi kullanıyor. `.gitignore` dosyasını okumuyor. `node_modules/`, `.venv/`, `dist/` gibi dizinler snapshot'a dahil oluyor → diff'te görünüyor → attachment olarak sonraki agent'a iletiliyor → prompt boyutu patlıyor.

### Çözüm

**Dosya: `pyproject.toml`**
- `pathspec>=0.12.1` dependency ekle (satır 43'e)

**Dosya: `runtime/node/agent/providers/claude_code_provider.py`**

#### 1a. `_SCAN_EXCLUDE_DIRS` genişlet (satır 1096):

```python
_SCAN_EXCLUDE_DIRS = frozenset({
    # Mevcut
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", "attachments",
    # Yeni — build/dependency dizinleri
    "dist", ".build", "Build", "DerivedData",
    "Pods", ".dart_tool", ".pub-cache",
    ".gradle", ".idea", ".vs", ".vscode",
    "target", "obj",
    "coverage", ".nyc_output",
    "generated",  # recursive kopyalamayı önle
    # NOT: "bin" ve "build" kasıtlı olarak DAHİL EDİLMEDİ:
    #   Node.js: bin/www kaynak kodudur, build/ bazı projelerde script içerir
    #   Bu dizinler snapshot'ta kalır, attachment seviyesinde extension kontrolü filtreler
})
```

#### 1b. `_SNAPSHOT_HIDDEN_WHITELIST` ekle (satır ~1100, `_SCAN_EXCLUDE_FILES`'dan sonra):

```python
_SNAPSHOT_HIDDEN_WHITELIST = frozenset({'.github'})
```

#### 1c. `_load_gitignore_spec()` metodu ekle (`_SNAPSHOT_HIDDEN_WHITELIST`'ten sonra):

```python
@staticmethod
def _load_gitignore_spec(workspace_root: str):
    """Load .gitignore patterns from workspace root. Returns pathspec or None."""
    try:
        import pathspec
        gitignore_path = Path(workspace_root) / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path, "r") as f:
                return pathspec.PathSpec.from_lines("gitwildmatch", f)
    except Exception:
        pass
    return None
```

#### 1d. `_snapshot_workspace()` güncelle (satır 1114-1128):

```python
def _snapshot_workspace(self, workspace_root: str) -> Dict[str, tuple]:
    """Take a lightweight snapshot of workspace files."""
    snapshot: Dict[str, tuple] = {}
    root = Path(workspace_root)
    if not root.exists():
        return snapshot

    gitignore_spec = self._load_gitignore_spec(workspace_root)

    for item in root.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(root)
        # Skip hidden (except whitelisted) and excluded directories
        if any(
            (part.startswith(".") and part not in self._SNAPSHOT_HIDDEN_WHITELIST)
            or part in self._SCAN_EXCLUDE_DIRS
            for part in rel.parts[:-1]
        ):
            continue
        # Skip excluded files
        if rel.name in self._SCAN_EXCLUDE_FILES:
            continue
        # Skip gitignored files
        if gitignore_spec and gitignore_spec.match_file(str(rel)):
            continue
        try:
            st = item.stat()
            snapshot[str(rel)] = (st.st_size, st.st_mtime_ns)
        except OSError:
            continue
    return snapshot
```

### Neden Bu Yaklaşım?
- **Snapshot seviyesinde filtreleme**: Gitignored dosyalar snapshot'a girmez → diff'te görünmez → attachment'a eklenmez
- `pathspec` kütüphanesi Git'in `.gitignore` spec'ini tam olarak destekler (negation, nested patterns, wildcards)
- Fallback: `.gitignore` yoksa veya `pathspec` yüklenemezse mevcut hardcoded davranış devam eder
- **`.github/` korunuyor** (Fix 1): `_SNAPSHOT_HIDDEN_WHITELIST` sayesinde CI/CD dosyaları snapshot'tan düşmez

### Not: pathspec Caching

İlk implementasyonda basit versiyon yeterli. Snapshot 2 kez alınır (before + after). Gelecekte gerekirse mtime bazlı cache:

```python
_gitignore_cache: Dict[str, Tuple[float, pathspec.PathSpec]] = {}

@staticmethod
def _load_gitignore_spec(workspace_root: str):
    gitignore_path = Path(workspace_root) / ".gitignore"
    if not gitignore_path.exists():
        return None
    mtime = gitignore_path.stat().st_mtime
    cached = ClaudeCodeProvider._gitignore_cache.get(workspace_root)
    if cached and cached[0] == mtime:
        return cached[1]
    spec = pathspec.PathSpec.from_lines("gitwildmatch", gitignore_path.read_text().splitlines())
    ClaudeCodeProvider._gitignore_cache[workspace_root] = (mtime, spec)
    return spec
```

**Karar**: İlk implementasyonda basit versiyon. Cache ikinci iterasyonda.

### Not: .lock Dosyaları

`.json` extension'ı whitelist'te olduğu için `package-lock.json` extension kontrolünden geçer ama **boyut sınırı** (512KB, Değişiklik 4) tarafından yakalanır. Explicit hariç tutmak istenirse `_SCAN_EXCLUDE_FILES`'a eklenebilir:

```python
_SCAN_EXCLUDE_FILES = frozenset({
    "firebase-debug.log", ".DS_Store", "Thumbs.db", "desktop.ini",
    ".claude_sessions.json",
    # Opsiyonel: lock dosyaları
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
    'Podfile.lock', 'Gemfile.lock', 'composer.lock',
    'Cargo.lock', 'poetry.lock',
})
```

---

## Değişiklik 2: Scope Creep Prevention (Prompt Değişikliği)

### Problem
Agent'lar kendilerine verilen task kapsamı dışında "iyileştirme" yapıyor — farklı dosyaları refactor ediyor, extra feature ekliyor, alakasız kısımları düzenliyor.

### Çözüm: Her agent prompt'una SCOPE BOUNDARY bölümü ekle

**Dosya: `yaml_instance/agile_dev.yaml`**

#### Developer (`role:` başlangıcına):
```
═══ SCOPE BOUNDARY ═══

CRITICAL RULES — You MUST follow these strictly:
- ONLY create/modify files listed in your assigned task's "Files" section
- NEVER refactor, optimize, or "improve" code outside your task scope
- NEVER add features not specified in the architecture document
- NEVER modify existing tests unless your task explicitly requires it
- If you notice issues outside your scope, mention them in your summary but DO NOT fix them
- When existing code exists, follow its conventions — do not rewrite it in your preferred style
```

#### Reviewer (`role:` başlangıcına):
```
═══ SCOPE BOUNDARY ═══

- Review ONLY the code that was created/modified by the Developer
- Do NOT suggest refactoring of pre-existing code
- Do NOT flag style preferences — only flag objective quality/security issues
- Focus findings on the submitted changes, not the entire codebase
```

#### QA Engineer (`role:` başlangıcına):
```
═══ SCOPE BOUNDARY ═══

- Test ONLY the functionality described in the requirements (FR-N list)
- Fix ONLY bugs you discover in the submitted code — do NOT refactor
- Do NOT add features, improve performance, or rewrite working code
- When fixing a bug, make the MINIMAL change required
```

#### DevOps (`role:` başlangıcına):
```
═══ SCOPE BOUNDARY ═══

- Create deployment config ONLY for what the project actually needs
- Do NOT add monitoring, alerting, or observability tools unless the architecture specifies them
- Match the complexity of deployment to the project size — a simple API doesn't need Kubernetes
- If the project already has a Dockerfile or CI pipeline, build upon it rather than replacing
```

#### Technical Writer (`role:` başlangıcına):
```
═══ SCOPE BOUNDARY ═══

- Document ONLY what was actually built — do NOT describe aspirational features
- Do NOT modify any source code files
- If documentation files already exist, update them rather than replacing
```

---

## Değişiklik 3: Conditional Agent Execution (Prompt Değişikliği)

### Problem
Basit bir bugfix için tüm pipeline çalışıyor: Product Analyst gereksinim analizi yapıyor, Architect mimari tasarlıyor, DevOps Dockerfile oluşturuyor — hepsi gereksiz.

### Çözüm: Her agent prompt'una SCOPE EVALUATION adımı ekle

Engine'de "skip node" mekanizması yok. **Prompt seviyesinde** çözüm:
- Agent ilk olarak görevi değerlendirir
- Kapsam dışıysa hızlı bir "Not applicable" yanıtı verir
- Doğru keyword'ü çıktılar → downstream edge normal fire eder
- Agent hâlâ çalışır ama minimal token harcar (1-2 cümle)

**Her agent'ın prompt'unun EN BAŞINA eklenir:**

#### Product Analyst:
```
═══ SCOPE EVALUATION (do this FIRST) ═══

Before starting analysis, evaluate the request:
- If this is a BUGFIX or MINOR CHANGE to existing code (not new features), output:
  "SCOPE: Minor change — skipping full requirements analysis. Forwarding original request to Architect."
  Then forward the user's request verbatim without further analysis.
- If this is a NEW FEATURE or SIGNIFICANT CHANGE, proceed with full analysis below.
```

#### Architect:

> **NOT**: Bu bölüm Değişiklik 5 (Plan Approval Bypass) ile entegre. AUTO_APPROVE mantığı Scope Evaluation'ın içinde.

```
═══ SCOPE EVALUATION (do this FIRST) ═══

Before starting design, evaluate the request:
- If existing architecture is adequate and only minor code changes are needed:
  1. Create a single task with the specific change needed
  2. End your output with: AUTO_APPROVE
- If this requires new components, new APIs, database changes, or has
  ambiguous requirements where multiple valid approaches exist:
  Do NOT include AUTO_APPROVE — a human will review your design.
  Proceed with full design below.
```

#### DevOps:
```
═══ SCOPE EVALUATION (do this FIRST) ═══

Before creating deployment config, evaluate what was built:
- If the project already has adequate deployment config (Dockerfile, CI/CD, etc.), output:
  "SCOPE: Existing deployment config is adequate. No changes needed."
  Then provide a brief status summary only.
- If no deployment config exists or significant changes are needed, proceed with full setup below.
```

#### Technical Writer:
```
═══ SCOPE EVALUATION (do this FIRST) ═══

Before writing documentation, evaluate what was built:
- If this was a minor change (bugfix, small tweak), output:
  "SCOPE: Minor change — updating CHANGELOG only."
  Then add a brief CHANGELOG entry and skip full documentation.
- If this was a new feature or significant change, proceed with full documentation below.
```

**Reviewer ve QA Engineer'a scope evaluation EKLENMEZ** — her değişiklik review ve test edilmeli.

### Keyword Uyumu

✅ **Risk yok (doğrulandı)**: Product Analyst, Architect, DevOps ve Technical Writer'ın tüm downstream edge'leri `condition: 'true'` kullanıyor (keyword condition yok). Scope evaluation çıktısı ne olursa olsun edge her zaman fire eder.

### Token Tasarrufu Notu

Token tasarrufu gerçekçi, süre tasarrufu sınırlı. Scope evaluation "skip" dese bile Claude Code CLI başlatma overhead'i (session init, MCP server spinup) 10-20s sürüyor. Asıl tasarruf token maliyetinde — agent 1-2 cümle yazıp çıkıyor vs. 5 dk araştırma yapıp 2000 kelime çıktı üretmesi.

---

## Değişiklik 4: Generated Dosya Duplikasyonu (Engine Değişikliği)

### Problem

`_emit_claude_code_file_changes()` ([agent_executor.py:687-732](runtime/node/executor/agent_executor.py#L687)) workspace diff'teki **HER** değişen dosyayı okuyup base64 encode ediyor ve `generated/{node_id}/` altına kopyalıyor.

Agent `flutter build`, `pod install`, `npm install` çalıştırınca binlerce build artifact "değişiklik" olarak algılanıyor → hepsi base64'e çevriliyor → hepsi kopyalanıyor.

**Gerçek veri** (`generated/` toplam): 859MB gereksiz duplikasyon (98% build artifact + dependency).

### Çözüm: Akıllı Filtreleme + Boyut Sınırı

**Dosya: `runtime/node/executor/agent_executor.py`**

#### 4a. Modül seviyesinde sabitler (`_extract_tool_detail`'den önce):

```python
# --- File tracking constants for artifact generation ---

# Extensions that are likely project source code (worth tracking as artifacts)
_SOURCE_EXTENSIONS = frozenset({
    '.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.svelte',
    '.java', '.kt', '.swift', '.dart', '.go', '.rs', '.rb',
    '.c', '.cpp', '.h', '.hpp', '.cs', '.php',
    '.html', '.css', '.scss', '.less', '.sass',
    '.json', '.yaml', '.yml', '.toml', '.xml', '.env',
    '.md', '.txt', '.rst', '.sql', '.sh', '.bash',
    '.dockerfile', '.dockerignore', '.gitignore',
    '.gradle', '.cmake', '.makefile',
})

# Directories that contain build artifacts / dependencies (never track)
_ARTIFACT_DIRS = frozenset({
    'node_modules', '.venv', 'venv', '__pycache__',
    'dist', '.build', 'Build', 'DerivedData',
    'Pods', '.dart_tool', '.pub-cache',
    '.gradle', '.idea', '.vs', '.vscode',
    'target', 'obj',
    'coverage', '.nyc_output', '.pytest_cache', '.mypy_cache',
    'generated',
    # NOT: 'bin' ve 'build' kasıtlı olarak ÇIKARILDI
    #   Go/C# bin/ → binary içerir → _SOURCE_EXTENSIONS'a uymaz → otomatik filtrelenir
    #   Node.js bin/www → kaynak kodu → _SOURCE_EXTENSIONS'a uyar → doğru dahil edilir
})

# Hidden directories whitelisted for tracking (e.g. CI/CD configs)
_HIDDEN_DIR_WHITELIST = frozenset({'.github'})

# Max individual file size for artifact attachment (skip binaries > 512KB)
_MAX_ARTIFACT_FILE_SIZE = 512 * 1024
```

#### 4b. Filtreleme fonksiyonu (modül seviyesi):

```python
def _is_trackable_source_file(path: str, size: int) -> bool:
    """Return True if the file is likely source code worth tracking as artifact."""
    from pathlib import PurePosixPath
    parts = PurePosixPath(path).parts

    # Skip files inside artifact/build directories
    if any(part in _ARTIFACT_DIRS for part in parts[:-1]):
        return False

    # .github/ directory: bypass extension check, only apply size limit
    # (CI/CD dosyaları: workflow YAML, CODEOWNERS, dependabot.yml vb.)
    if any(part == '.github' for part in parts[:-1]):
        return size <= _MAX_ARTIFACT_FILE_SIZE

    # Skip other hidden directories
    if any(
        part.startswith('.') and part not in _HIDDEN_DIR_WHITELIST
        for part in parts[:-1]
    ):
        return False

    # Skip large files (binaries, APKs, etc.)
    if size > _MAX_ARTIFACT_FILE_SIZE:
        return False

    # Only track known source extensions
    ext = PurePosixPath(path).suffix.lower()
    if ext and ext not in _SOURCE_EXTENSIONS:
        return False

    # Files without extension: only allow known names
    if not ext:
        name = PurePosixPath(path).name.lower()
        return name in ('dockerfile', 'makefile', 'procfile', 'gemfile', 'rakefile', 'codeowners')

    return True
```

#### 4c. `_emit_claude_code_file_changes` filtreyi uygula (satır 688):

```python
# Mevcut:
if change_type in ("created", "modified"):

# Yeni:
if change_type in ("created", "modified") and _is_trackable_source_file(path, size):
```

### Neden Bu Yaklaşım?
- **Whitelist**: Sadece bilinen kaynak kodu uzantıları dahil edilir
- **Dizin filtreleme**: `node_modules/`, `Pods/`, `dist/` içindeki dosyalar hiç işlenmez
- **`.github/` korunuyor** (Fix 2): Extension check bypass edilir, sadece boyut sınırı uygulanır → CODEOWNERS, workflow YAML, dependabot.yml hepsi geçer
- **`_HIDDEN_DIR_WHITELIST` modül seviyesinde** (Fix 3): Fonksiyon dışında tanımlı, tekrar kullanılabilir
- **Boyut sınırı**: 512KB üzeri dosyalar (APK, SO, JAR) atlanır
- **`generated/` kendini hariç tutar**: Recursive kopyalamayı önler

### Etki Tahmini

| Agent | Önce | Sonra |
|-------|------|-------|
| Integration Engineer | 568MB | ~2MB |
| QA Bug Fixer | 53MB | ~1MB |
| QA Engineer | 108MB | ~1MB |
| Diğerleri | 130MB | ~11MB |
| **TOPLAM** | **859MB** | **~15MB** (98% azalma) |

### İki Katmanlı Savunma

| Katman | Dosya | Ne Yapar |
|--------|-------|----------|
| 1 (Snapshot) | `claude_code_provider.py` | Gitignore + `_SCAN_EXCLUDE_DIRS` + `_SNAPSHOT_HIDDEN_WHITELIST` → dosyalar diff'e girmez |
| 2 (Attachment) | `agent_executor.py` | `_SOURCE_EXTENSIONS` + `_ARTIFACT_DIRS` + `_HIDDEN_DIR_WHITELIST` + boyut sınırı → dosyalar `generated/`'a kopyalanmaz |

---

## Değişiklik 5: Plan Approval Bypass (Topoloji Değişikliği)

### Problem
Mevcut akışta **her** görev için insan onayı (Plan Approval) bekleniyor. Basit bugfix'ler ve minor değişiklikler için gereksiz. İnsan onayı sadece belirsizlik olan veya karmaşık mimari kararlar gerektiren durumlarda sorulmalı. Zaten final aşamasında (Reviewer + QA) kontrol ediliyor.

### Mevcut Akış

```
Architect → Plan Approval (HUMAN) → Developer
                 ↓ (reject)
           Revision Counter → Architect (loop, max 2)
```

SCC: `{Architect, Plan Approval, Plan Revision Counter}` — tek süper düğüm. Developer dışarıda.

### Çözüm: Architect AUTO_APPROVE Bypass

Architect `AUTO_APPROVE` keyword'ü çıktılarsa → Plan Approval atlanır → Developer doğrudan başlar.
Architect `AUTO_APPROVE` çıktılamazsa → mevcut akış devam eder (human review).

#### Neden bu yaklaşım?
1. **Human oversight korunuyor**: Karmaşık/riskli tasklarda insan hala review yapıyor
2. **Scope Evaluation ile entegre**: Değişiklik 3'teki Architect scope evaluation zaten "basit mi karmaşık mı" değerlendirmesi yapıyor — aynı noktada AUTO_APPROVE kararını da verebilir
3. **Topoloji güvenli**: SCC yapısı değişmiyor, sadece bir exit edge ekleniyor

#### Alternatifler neden değil?
- **Human'ı agent'a çevirme**: Sıfır human oversight, agent yanılabilir
- **Agent + human fallback**: Overengineering, yeni node + edge → SCC karmaşıklaşır

### YAML Değişiklikleri

**Dosya: `yaml_instance/agile_dev.yaml`**

#### 5a. Mevcut `Architect → Plan Approval` edge'ini güncelle:

```yaml
# Mevcut:
- from: Architect
  to: Plan Approval
  trigger: true
  condition: 'true'

# Yeni — sadece AUTO_APPROVE YOKSA fire et:
- from: Architect
  to: Plan Approval
  trigger: true
  condition:
    type: keyword
    config:
      any: []
      none: [AUTO_APPROVE]
      regex: []
      case_sensitive: true
```

#### 5b. Yeni `Architect → Developer` bypass edge ekle:

```yaml
- from: Architect
  to: Developer
  trigger: true
  condition:
    type: keyword
    config:
      any: [AUTO_APPROVE]
      none: []
      regex: []
      case_sensitive: true
  carry_data: true
```

#### 5c. Architect prompt (Değişiklik 3 ile entegre):

Zaten Değişiklik 3'te tanımlandı. Architect'in SCOPE EVALUATION bölümü:
```
- Basit görev → AUTO_APPROVE → Developer doğrudan başlar
- Karmaşık görev → AUTO_APPROVE yok → Plan Approval (insan) devreye girer
```

### Dynamic Map Etkileşimi

Mevcut context edge:
```yaml
- from: Architect
  to: Developer
  trigger: false
  dynamic:
    type: map
    split: { type: regex, config: { pattern: "..." } }
```

- **AUTO_APPROVE path**: Context edge task'ları split eder → trigger edge (AUTO_APPROVE) Developer'ı aktive eder
- **Non-AUTO_APPROVE path**: Context edge aynı şekilde fire eder → trigger, `Plan Approval → Developer` üzerinden gelir

Mevcut akışta da Plan Approval tek "approve" mesajı gönderirken Developer N instance'ta çalışıyor — yani mekanizma zaten çalışıyor. Bypass path için de aynı olmalı. **Runtime'da doğrulanmalı.**

### Güvenlik Ağı

Architect yanlış `AUTO_APPROVE` verse bile:
1. **Code Reviewer** kodu inceler → sorun bulursa reject
2. **QA Engineer** test yazar → hata bulursa report
3. Bu 2 katmanlı güvenlik ağı riski minimize eder

### Etki

| Senaryo | Önce | Sonra |
|---------|------|-------|
| Basit bugfix | İnsan bekle → approve → Developer | Architect AUTO_APPROVE → Developer (hemen) |
| Yeni feature | İnsan bekle → approve → Developer | İnsan bekle → approve → Developer (değişiklik yok) |
| Riskli değişiklik | İnsan bekle → approve/reject | İnsan bekle → approve/reject (değişiklik yok) |

---

## Değişiklik Özeti

| # | Dosya | Değişiklik Türü | Açıklama |
|---|-------|-----------------|----------|
| 1 | `pyproject.toml` | dependency ekleme | `pathspec>=0.12.1` |
| 1 | `claude_code_provider.py` | sabit + metod + güncelleme | `_SCAN_EXCLUDE_DIRS` genişletme, `_SNAPSHOT_HIDDEN_WHITELIST`, `_load_gitignore_spec()`, `_snapshot_workspace()` güncelleme |
| 2-3 | `agile_dev.yaml` | prompt güncellemesi | Scope boundary (5 agent) + scope evaluation (4 agent) |
| 4 | `agent_executor.py` | sabit + fonksiyon + filtre | `_SOURCE_EXTENSIONS`, `_ARTIFACT_DIRS`, `_HIDDEN_DIR_WHITELIST`, `_is_trackable_source_file()`, `_emit_claude_code_file_changes` filtre |
| 5 | `agile_dev.yaml` | edge + prompt değişikliği | Architect→PlanApproval condition, yeni Architect→Developer bypass edge, AUTO_APPROVE prompt |

---

## Uygulama Önceliği

| Sıra | Değişiklik | Neden Önce |
|------|-----------|------------|
| 1 | **Değişiklik 1** (Gitignore) | En kritik — snapshot seviyesinde filtreleme, tüm katmanları etkiler |
| 2 | **Değişiklik 4** (Generated duplikasyon) | İkinci katman savunma — Değişiklik 1'i geçen dosyalar burada yakalanır |
| 3 | **Değişiklik 2+3** (Scope Creep + Conditional) | Prompt değişikliği — engine riski yok, sadece YAML |
| 4 | **Değişiklik 5** (Plan Approval Bypass) | Topoloji değişikliği — YAML edge condition + prompt |

**Değişiklik 1+4 birlikte uygulanmalı** — iki katmanlı savunma:
- Katman 1 (snapshot): Gitignore + hardcoded exclude → diff'e girmez
- Katman 2 (attachment): Whitelist + boyut sınırı → generated'a kopyalanmaz

**Değişiklik 2+3+5 birlikte uygulanmalı** — hepsi `agile_dev.yaml` prompt/edge değişikliği.

---

## Doğrulama

### 1. Gitignore filtering:
```bash
uv pip install pathspec
uv run python -c "
from pathlib import Path
import pathspec
spec = pathspec.PathSpec.from_lines('gitwildmatch', ['node_modules/', '*.pyc', '.venv/'])
print(spec.match_file('node_modules/express/index.js'))  # True
print(spec.match_file('src/main.py'))  # False
print(spec.match_file('.venv/lib/python3.12/site.py'))  # True
"
```

### 2. YAML syntax:
```bash
uv run python -c "import yaml; yaml.safe_load(open('yaml_instance/agile_dev.yaml')); print('OK')"
```

### 3. Generated duplikasyon filtre testi:
```bash
uv run python -c "
from runtime.node.executor.agent_executor import _is_trackable_source_file

# Kaynak kodu → True
assert _is_trackable_source_file('src/main.py', 1000) == True
assert _is_trackable_source_file('lib/utils.dart', 500) == True

# Build artifact → False
assert _is_trackable_source_file('Pods/Firebase/Auth.swift', 5000) == False
assert _is_trackable_source_file('node_modules/express/index.js', 200) == False

# Binary → False (boyut sınırı)
assert _is_trackable_source_file('assets/image.png', 1_000_000) == False

# .github/ — extension check bypass, sadece boyut kontrolü
assert _is_trackable_source_file('.github/workflows/ci.yml', 500) == True
assert _is_trackable_source_file('.github/CODEOWNERS', 200) == True
assert _is_trackable_source_file('.github/dependabot.yml', 300) == True

# Diğer hidden dir'ler hala filtrelenmeli
assert _is_trackable_source_file('.hidden/secret.py', 100) == False

# bin/ ve build/ — extension'a göre filtreler, dizin bazlı değil
assert _is_trackable_source_file('bin/www', 500) == False         # Node.js entry — extensionless, 'www' not in known names → bilinen sınırlama
assert _is_trackable_source_file('build/scripts/deploy.sh', 300) == True  # build script

# Go/C# binary'leri — extension yok + known name değil → False
assert _is_trackable_source_file('bin/myapp', 5_000_000) == False   # extensionless + boyut sınırı (ikisi de yakalar)

print('All assertions passed')
"
```

### 4. Manuel test:
Basit bugfix task'ı ile workflow çalıştırarak:
- Scope evaluation'ın çalışıp çalışmadığını doğrula
- AUTO_APPROVE bypass'ın Plan Approval'ı atlayıp atlamadığını doğrula
- Dynamic map'in bypass path'te çalışıp çalışmadığını doğrula

---

## Dış Değerlendirme Bulguları

| # | Seviye | Bulgu | Durum |
|---|--------|-------|-------|
| BUG 1 | Kritik | `.github/` hidden dir kontrolü tarafından filtreleniyor → CI/CD dosyaları kaybolur | ✅ Fix 1+2: Hem snapshot (1b) hem attachment (4a-4b) seviyesinde `_HIDDEN_DIR_WHITELIST` + extension bypass |
| BUG 2 | Orta | `bin` ve `build` dizinleri false positive | ✅ Düzeltildi: Hem `_ARTIFACT_DIRS`'ten hem `_SCAN_EXCLUDE_DIRS`'ten çıkarıldı |
| Risk 3 | Düşük | `size` değerinin kaynağı doğru mu? | ✅ Risk yok: `stat.st_size` değerinden geliyor |
| D2-3 | Düşük | Scope evaluation keyword uyumu bozar mı? | ✅ Risk yok: Tüm downstream edge'ler `condition: 'true'` kullanıyor |
| D5 | Orta | Dynamic map bypass path'te çalışıyor mu? | ⏳ Runtime'da doğrulanmalı |
| Fix 1 | İyileştirme | `_SNAPSHOT_HIDDEN_WHITELIST` snapshot seviyesinde | ✅ Plana eklendi (1b) |
| Fix 2 | İyileştirme | `.github/` extension check bypass | ✅ Plana eklendi (4b) |
| Fix 3 | İyileştirme | `_HIDDEN_DIR_WHITELIST` modül seviyesinde | ✅ Plana eklendi (4a) |
