# 제출본 제작·확인

제출 파일은 검토한 소스와 기획서, 실행 검증 영수증으로 만든다. 실제 제출 전 공고의 파일 형식·용량·영상 조건을 대조한다.

## 제작 전

- 제출할 커밋과 최신 기획서 PDF를 확정한다. 기획서 원고는 `docs/proposal/제주고사리_AI_Agent_개발기획서_v0.21.md`이며 `uv run --no-project --with reportlab --with pypdf python scripts/render-proposal-report.py --output <경로>`로 v0.20과 같은 보고서 서식(표지·목차·번호 체계·명조 본문)의 A4 14쪽 PDF를 만든다. 제목·표 글꼴 NanumGothic TTF는 `.local/fonts/`에 둔다.
- 최신 소스로 앱 이미지를 만들고, 기존 개인 DB와 분리한 빈 DB에서 기동·마이그레이션·화면·readiness를 확인한다.
- 이미지 ID·검증 소스 커밋·잠금 파일 해시를 실행 영수증에 남긴다. 구 이미지에 새 소스를 연결한 시험과 새 이미지 시험을 구분한다.
- Windows·센터 기동, 공개 실행 URL, 시연 영상은 실제 확보한 결과만 완료로 표시한다.
- 기획서와 영수증에서 실제 키·비밀번호·개인 기록·환경변수 원문을 제거한다. 영수증은 검토한 JSON 파일만 첨부한다.

## 입력 확인

```sh
node scripts/package-submission.mjs --dry-run
```

이 명령은 ZIP이나 실행 환경을 만들지 않는다. Git 추적 파일과 무시되지 않은 신규 파일 중 패키저의 명시 목록만 읽어 검사한다. 앱 소스·프롬프트·공개 표본·migration·실행 스크립트·설정 예제·잠금 파일·설치 문서를 포함한다.

사용 매뉴얼·AI/의존성 목록·기획서 원문·PDF 렌더러·빌드 식별 스크립트도 포함한다. 최종 실행 영수증 `docs/verification/submission-20261108.json`이 있으면 함께 검사해 포함하며, 원시 작업 로그는 묶지 않는다.

실제 `.env`, `.git`, `.agents`, `.qwen`, 설치한 의존성, 가상환경, 빌드 결과, 로그, 개인 DB와 키 파일은 포함하지 않는다. `.env.example`은 포함한다. 심볼릭 링크와 Windows에서 충돌하는 경로도 거부한다.

## 최종 ZIP

```sh
node scripts/package-submission.mjs \
  --proposal .local/submission-20261108/proposal.pdf \
  --receipt /검토한/실행-영수증.json
```

기획서 PDF가 없으면 최종 ZIP 제작은 실패한다. 영수증은 `--receipt`를 반복해 추가한다. 시연 영상을 준비했다면 `--video /검토한/demo.mp4`를 추가한다. 파일을 첨부한 사실이 그 내용의 검증 완료를 뜻하지는 않는다.

PDF는 설치된 `pdftotext`로 텍스트를 읽어 키 패턴을 검사한다. Node·Python 표준 라이브러리로 ZIP을 만들며 새 패키지나 모델을 내려받지 않는다. 자동 검사는 파일 목록·키 패턴·영수증의 개인 필드를 검사하며, 최종 기획서와 영상의 화면·내용 확인은 별도로 마친다.

출력은 Git에서 제외된 `.local/submission-20261108/` 아래에 저장한다.

- `gosari-it-<commit>.zip`: 제출 묶음
- `gosari-it-<commit>.manifest.json`: 파일별 SHA256·크기·모드·소스 커밋·tree·잠금 파일 해시
- `gosari-it-<commit>.sha256`: ZIP SHA256
- `gosari-it-<commit>.verification.json`: 실제 추출 후 파일 해시 대조 결과

ZIP 안에는 같은 `SUBMISSION_MANIFEST.json`이 들어간다. 기획서는 `submission/proposal.pdf`, 영수증은 `submission/receipts/`, 영상은 `submission/demo.<확장자>`에 둔다. 개발자 컴퓨터의 원본 절대 경로는 ZIP 매니페스트에 넣지 않는다.

경로는 NFC 상대 경로로 정규화하고 정렬한다. ZIP 시각은 커밋의 UTC 시각, 파일 모드는 고정하며 무압축 ZIP으로 압축기 버전 차이를 피한다. 같은 커밋·파일 내용·첨부파일이면 같은 ZIP SHA256이 나온다. 커밋 이후 바뀐 허용 파일은 `dirty_source_paths`로 명시하므로 커밋과 내용이 같다고 오인하지 않는다. 최종 제출은 이 목록을 확인한 뒤 확정한다.

## 추출 검증

```sh
node scripts/package-submission.mjs --verify .local/submission-20261108/gosari-it-<commit>.zip
```

중복·상대 경로 이탈·심볼릭 링크·불필요 파일을 거부하고, 임시 디렉터리에 실제로 추출한 파일의 SHA256을 매니페스트와 대조한다. 이 결과는 ZIP 무결성 확인이며, 설치·사용 시나리오 통과를 대신하지 않는다.

## 제출 직전

- [ ] ZIP 내부 소스와 매니페스트의 커밋·해시 대조
- [ ] 최신 기획서와 설치·운영 매뉴얼 포함
- [ ] 최신 이미지와 빈 DB 기동 영수증의 소스·이미지 ID 일치
- [ ] 실제 비밀·개인 데이터·로컬 환경 파일 제외
- [ ] ZIP 추출·해시 검증 통과
- [ ] 공고상 영상·실행 URL·Windows/센터 조건의 해당 여부와 실제 증거 확인
- [ ] 최종 파일명·용량·제출 경로 확인 후 제출
