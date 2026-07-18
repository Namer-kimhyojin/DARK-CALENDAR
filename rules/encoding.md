# 인코딩 정책

> 작성하거나 수정하는 **모든 `.py` 파일**은 아래 규칙을 준수해야 합니다.
> 위반 시 pre-commit 및 CI가 차단됩니다.

## 규칙

### 1. 파일 헤더
모든 `.py` 파일 **첫 줄**에 반드시 작성:
```python
# -*- coding: utf-8 -*-
```
- BOM(UTF-8-sig) 없이 **순수 UTF-8**로 저장할 것
- BOM이 포함되면 헤더가 인식되지 않아 CI 실패 (c61b43f)

### 2. encoding= 키워드
항상 `"utf-8"` 사용 — `cp949`, `latin-1` 등 금지

**예외 화이트리스트** (테스트에서 허용됨):
- `calendar_app/preset_manager.py` — `ascii`
- `scripts/fix_encoding.py` — `cp949`, `utf-8-sig`

### 3. errors= 필수 병기
`encoding="utf-8"` 을 쓸 때는 반드시 `errors=` 를 함께 명시해야 합니다.

| errors 값 | 사용 상황 |
|---|---|
| `"strict"` | 내부 파일/데이터 — 반드시 깨끗한 UTF-8이 보장되는 경우 |
| `"replace"` | 외부 입력 — API 응답, 사용자 데이터 등 오염 가능성 있는 경우 |
| `"ignore"` | **절대 금지** — 데이터 무결성 침해 |

### 4. open() 텍스트 모드
```python
# 올바른 예
open(path, "r", encoding="utf-8", errors="strict")
open(path, "w", encoding="utf-8", errors="strict")

# 바이너리 모드는 면제
open(path, "rb")
open(path, "wb")
```

### 5. Path.read_text() / Path.write_text()
```python
Path(p).read_text(encoding="utf-8", errors="strict")
Path(p).write_text(content, encoding="utf-8", errors="strict")
```

### 6. subprocess (text=True)
```python
subprocess.run(cmd, text=True, encoding="utf-8", errors="strict")
subprocess.Popen(cmd, text=True, encoding="utf-8", errors="strict")
subprocess.check_output(cmd, text=True, encoding="utf-8", errors="strict")
```

### 7. encode() / decode()
```python
# errors= 두 번째 인자 필수
data.encode("utf-8", errors="strict")
data.decode("utf-8", errors="replace")   # 외부 데이터는 replace
```

## 빠른 참조

```python
# 내부 파일 I/O
open(path, "r", encoding="utf-8", errors="strict")
Path(p).read_text(encoding="utf-8", errors="strict")

# 외부/API 데이터
some_bytes.decode("utf-8", errors="replace")

# subprocess
subprocess.run(cmd, text=True, encoding="utf-8", errors="strict")
```

## 강제 도구

| 도구 | 명령 |
|---|---|
| pre-commit 훅 | `.pre-commit-config.yaml` → `python scripts/run_encoding_guard.py` |
| CI 게이트 | `.github/workflows/encoding-policy.yml` |
| 수동 검사 | `python scripts/run_encoding_guard.py` |
| 테스트 | `pytest tests/test_encoding_policy.py tests/test_encoding_utils.py` |
