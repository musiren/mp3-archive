# mp3-archive

MP3 파일을 재귀적으로 스캔하여 메타데이터를 SQLite DB에 저장하고 관리하는 데스크톱 애플리케이션입니다.

## 기능

- MP3 파일 재귀 탐색 및 메타데이터(제목, 아티스트, 앨범, 길이, 크기) 저장
- ID3 태그가 없는 경우 파일명(`아티스트 - 제목.mp3`)에서 자동 파싱
- 증분 스캔: 변경된 파일만 업데이트 (빠름)
- 전체 재스캔: 모든 파일 강제 재읽기
- 파일 생성일시 / 수정일시 추적
- MP3 경로 설정 저장 (QSettings, 앱 재시작 시 복원)
- 레코드 선택 삭제

## 요구사항

```
pip install -r requirements.txt
```

- Python 3.10+
- PyQt6
- mutagen
- Pillow (UI 프리뷰 생성용)

## 실행

```bash
python main.py
```

또는 직접 실행:

```bash
python src/main_window.py
```

## 빌드

### Windows

```bash
pyinstaller build/windows.spec
# 결과물: dist/mp3-archive.exe
```

### Linux

```bash
pyinstaller build/linux.spec
# 결과물: dist/mp3-archive
```

### Android

```bash
buildozer -v android debug
# 참고: build/android.spec 설정 사용
```

## 테스트

```bash
python -m unittest discover -s test -v
```

## 디렉토리 구조

```
mp3-archive/
├── src/                        # 소스 코드
│   ├── mp3_manager.py          # MP3 스캔 및 SQLite 관리 라이브러리
│   ├── main_window.py          # PyQt6 데스크톱 UI
│   ├── main_window.ui          # Qt Designer 레이아웃
│   └── main_window_android.py  # KivyMD 안드로이드 UI
├── test/                       # 테스트 코드
├── build/                      # PyInstaller / Buildozer spec 파일
├── docs/                       # 문서 및 이미지
│   └── ui-preview.jpg
├── skills/                     # 프로젝트 가이드 문서
├── main.py                     # 진입점
└── requirements.txt
```

## UI 프리뷰

![UI Preview](docs/ui-preview.jpg)
