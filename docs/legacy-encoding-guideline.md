# 레거시 문자열 깨짐 최소화 지침서

## 1. 목적
- 한글/이모지/특수문자 데이터가 파일, DB, 로그, API 경계를 지날 때 깨지는 현상을 예방한다.
- 깨짐이 발생하더라도 원인 추적과 복구가 가능하도록 표준 처리 절차를 통일한다.

## 2. 적용 범위
- Python 소스코드, 로케일 파일(`locales`), 설정 파일(JSON/CSV), 로그 파일
- DB 입출력 계층
- 외부 API, 서브프로세스, 콘솔/터미널 I/O

## 3. 핵심 원칙
1. 내부 표준은 `UTF-8` 하나로 통일한다.
2. 인코딩 변환은 "경계 계층"에서만 수행한다.
3. 인코딩 실패를 숨기지 않는다(`ignore` 금지).
4. 복구 가능성을 위해 원본 바이트를 우선 보존한다.

## 4. 필수 규칙

### 4.1 파일 입출력
- 텍스트 파일은 반드시 `encoding="utf-8"`을 명시한다.
- 기본 에러 정책은 `errors="strict"`로 한다.
- 예외적으로 사용자 표시용 임시 복구가 필요할 때만 `errors="replace"`를 사용한다.

```python
from pathlib import Path

def read_text_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")

def write_text_utf8(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", errors="strict", newline="\n")
```

### 4.2 JSON/CSV
- JSON 저장 시 `ensure_ascii=False`를 사용한다.
- CSV 읽기/쓰기 시 인코딩을 명시한다.

```python
import json

payload = {"title": "다크 캘린더 ✅"}
with open("data.json", "w", encoding="utf-8", errors="strict") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
```

### 4.3 로그
- 파일 로그 핸들러 생성 시 UTF-8을 강제한다.

```python
import logging

handler = logging.FileHandler("app.log", encoding="utf-8")
logging.basicConfig(level=logging.INFO, handlers=[handler])
```

### 4.4 서브프로세스
- 텍스트 모드 호출은 `encoding="utf-8"`을 명시한다.

```python
import subprocess

result = subprocess.run(
    ["python", "--version"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    check=True,
)
```

### 4.5 DB
- DB 연결 시 드라이버/클라이언트 인코딩을 UTF-8로 고정한다.
- 문자열 컬럼은 UTF-8 전제 규칙을 문서화하고, 경계 계층 외 변환을 금지한다.
- 대량 이관/복구 시 원본(raw bytes) 보관 테이블 또는 백업 파일을 먼저 만든다.

## 5. 레거시 데이터 호환 규칙

### 5.1 허용되는 fallback 순서
- 1차: `utf-8` (`strict`)
- 2차: `cp949` (`strict`)
- 3차: `euc-kr` (`strict`)
- 위 순서 외 자동 추측(chardet류)의 무분별한 상시 사용은 금지한다.

### 5.2 표준 디코더 유틸리티 예시
- fallback은 레거시 유입 지점(파일 import, 마이그레이션, 외부 연동 수집기)에서만 사용한다.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class DecodeResult:
    text: str
    encoding: str

def decode_legacy_bytes(raw: bytes) -> DecodeResult:
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return DecodeResult(text=raw.decode(enc, errors="strict"), encoding=enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", raw, 0, len(raw), "지원 인코딩으로 복구 실패")
```

### 5.3 금지 사항
- `errors="ignore"` 사용
- 이미 `str`인 데이터를 다시 임의 인코딩/디코딩
- 깨진 문자열을 원본 확인 없이 덮어쓰기

## 6. 운영 환경 표준
- Windows 실행 환경에서 `PYTHONUTF8=1`을 기본값으로 사용한다.
- 콘솔 출력 문제가 반복되면 UTF-8 코드페이지(`chcp 65001`) 및 터미널 폰트를 점검한다.
- CI에서 UTF-8 환경 변수를 명시해 로컬/배포 간 차이를 줄인다.

## 7. 테스트 지침
- 최소 테스트 샘플: `한글`, `영문`, `이모지`, `혼합문자`, `cp949 원본 바이트`.
- 파일 round-trip 테스트를 추가한다(읽기->저장->재읽기 일치성).
- 레거시 fallback 경로에 대해 "사용된 인코딩"이 로그에 남는지 검증한다.
- 깨짐 패턴(`�`) 탐지 테스트를 추가한다.

## 8. 장애 대응 절차
1. 원본 데이터 백업(raw bytes 또는 원본 파일)을 즉시 분리 보관한다.
2. 깨진 구간의 유입 경계를 확인한다(파일/DB/API/서브프로세스).
3. 동일 데이터에 대해 `utf-8 -> cp949 -> euc-kr` 순으로 오프라인 재복구를 시도한다.
4. 복구 완료 후 해당 경계에 인코딩 명시 + 테스트를 추가한다.
5. 재발 방지를 위해 PR 체크리스트를 갱신한다.

## 9. PR 체크리스트
- [ ] 모든 텍스트 I/O에 `encoding`이 명시되어 있다.
- [ ] `errors="ignore"` 사용이 없다.
- [ ] 레거시 fallback은 경계 계층에서만 동작한다.
- [ ] 신규/수정 테스트에 한글 및 특수문자 케이스가 포함되어 있다.
- [ ] 로그 또는 메트릭으로 디코딩 실패를 추적할 수 있다.
