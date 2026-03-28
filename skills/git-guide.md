# Git 가이드

## 규칙

- **푸시 전 확인**: 푸시하기 전에 항상 사용자에게 푸시할지 여부를 물어본다.
- **커밋 메시지 형식**: 리눅스 커널 스타일을 따른다.
  - 제목은 50자 이내, 명령형으로 작성 (e.g. `Fix bug`, `Add feature`)
  - 제목과 본문 사이 빈 줄 삽입
  - 본문은 72자 줄바꿈, "무엇을"보다 "왜"를 설명
  - 예시:
    ```
    subsystem: short summary of the change

    More detailed explanation of why this change is needed,
    what problem it solves, and any side effects.

    Signed-off-by: Name <email>
    ```
- **언어**: 모든 커밋 메시지 및 문서는 영어로 작성한다.

## 기본 설정

```bash
git config --global user.name "이름"
git config --global user.email "이메일"
```

## 저장소 초기화 및 클론

```bash
git init                        # 새 저장소 초기화
git clone <url>                 # 원격 저장소 클론
git clone <url> <디렉토리명>    # 특정 디렉토리에 클론
```

## 브랜치

```bash
git branch                      # 로컬 브랜치 목록
git branch -a                   # 원격 포함 전체 브랜치 목록
git branch <브랜치명>           # 브랜치 생성
git checkout <브랜치명>         # 브랜치 전환
git checkout -b <브랜치명>      # 브랜치 생성 후 전환
git branch -d <브랜치명>        # 브랜치 삭제
```

## 스테이징 및 커밋

```bash
git status                      # 작업 상태 확인
git add <파일>                  # 특정 파일 스테이징
git add .                       # 전체 변경사항 스테이징
git commit -m "메시지"          # 커밋
git commit --amend              # 마지막 커밋 수정
```

## 원격 저장소

```bash
git remote -v                           # 원격 저장소 목록
git remote add origin <url>             # 원격 저장소 추가
git push -u origin <브랜치명>           # 최초 푸시 (upstream 설정)
git push                                # 푸시
git pull origin <브랜치명>              # 풀
git fetch origin <브랜치명>             # 패치 (병합 없이 가져오기)
```

## 병합 및 리베이스

```bash
git merge <브랜치명>            # 브랜치 병합
git rebase <브랜치명>           # 리베이스
git rebase --abort              # 리베이스 중단
git rebase --continue           # 리베이스 계속
```

## 로그 및 차이 확인

```bash
git log                         # 커밋 히스토리
git log --oneline --graph       # 그래프 형태로 간략히 보기
git diff                        # 변경사항 확인
git diff <브랜치1>..<브랜치2>   # 브랜치 간 차이 확인
git show <커밋해시>             # 특정 커밋 내용 확인
```

## 되돌리기

```bash
git restore <파일>              # 작업 디렉토리 변경사항 취소
git restore --staged <파일>     # 스테이징 취소
git revert <커밋해시>           # 커밋 되돌리기 (새 커밋 생성)
git reset --hard <커밋해시>     # 특정 커밋으로 강제 초기화 (주의)
```

## 스태시

```bash
git stash                       # 작업 내용 임시 저장
git stash list                  # 스태시 목록
git stash pop                   # 최근 스태시 적용 후 삭제
git stash apply stash@{0}       # 특정 스태시 적용
git stash drop stash@{0}        # 특정 스태시 삭제
```

## 태그

```bash
git tag                         # 태그 목록
git tag <태그명>                # 태그 생성
git tag -a <태그명> -m "메시지" # 주석 태그 생성
git push origin <태그명>        # 태그 푸시
git push origin --tags          # 전체 태그 푸시
```
