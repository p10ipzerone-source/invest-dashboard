# 투자 지표 대시보드

하루 한 번 GitHub Actions가 데이터를 받아서 `docs/data.js`를 갱신하고, GitHub Pages가 `docs/index.html`을 보여줍니다.

## 처음 세팅 (약 10분)

1. **저장소 만들기**
   GitHub에서 New repository, 이름 예: `invest-dashboard`, **Public** 선택 (무료 계정은 Public이어야 Pages 사용 가능. 시세 데이터만 있으니 공개돼도 문제 없음)

2. **파일 올리기**
   저장소 화면에서 `Add file` > `Upload files`로 아래 파일을 올립니다.
   - `fetch_data.py`, `requirements.txt`, `README.md`
   - `docs` 폴더 통째로 (드래그하면 폴더 구조 유지됨)

3. **워크플로 파일 만들기** (점으로 시작하는 폴더는 업로드가 잘 안 돼서 직접 만듭니다)
   `Add file` > `Create new file`, 파일 이름 칸에 `.github/workflows/update.yml` 입력 후
   압축파일 안의 `.github/workflows/update.yml` 내용을 붙여넣고 Commit

4. **쓰기 권한 주기**
   Settings > Actions > General > 맨 아래 Workflow permissions > `Read and write permissions` 선택 후 Save

5. **KOFR용 한국은행 API 키 (선택)**
   - https://ecos.bok.or.kr/api/#/AuthKeyApply 에서 무료 인증키 신청
   - Settings > Secrets and variables > Actions > New repository secret
     Name: `ECOS_API_KEY`, Secret: 발급받은 키
   - 키가 없으면 KOFR 카드만 비어 있고 나머지는 정상 작동

6. **첫 실행**
   Actions 탭 > 왼쪽 `데이터 갱신` > `Run workflow`. 1~2분 뒤 초록 체크 확인

7. **Pages 켜기**
   Settings > Pages > Source: `Deploy from a branch`, Branch: `main`, 폴더: `/docs` > Save
   1~2분 뒤 `https://<아이디>.github.io/invest-dashboard/` 주소가 생깁니다. 즐겨찾기 해두면 끝

## 갱신 주기
- 한국시간 화~토 오전 7시 30분경 자동 실행 (미국장 마감 후). GitHub 사정으로 수십 분 늦어질 수 있음
- 바로 갱신하고 싶으면 Actions 탭에서 `Run workflow`

## 데이터 출처
| 지표 | 출처 | 비고 |
|---|---|---|
| 나스닥, S&P500, VIX, M7 | Yahoo Finance | 실패 시 FRED 백업(M7 제외) |
| 미국 3개월 국채 | Yahoo `^IRX` (13주 T-Bill) | 백업 FRED DTB3 |
| 미국 10년물 | Yahoo `^TNX` | 백업 FRED DGS10 |
| 유가 | Yahoo WTI 선물 `CL=F`, 브렌트 `BZ=F` | $80 기준은 WTI에 적용 |
| 공포탐욕지수 | CNN Fear & Greed | 비공식 경로라 막히면 직전 값 유지 |
| KOFR | 한국은행 ECOS | API 키 필요 |

어떤 소스가 실패해도 나머지는 갱신되고, 실패한 지표는 직전 데이터와 함께 "갱신 실패" 문구가 표시됩니다.

## 강조 기준 (index.html 상단 `SECTIONS`, `DD_LEVELS`에서 수정 가능)
- 나스닥, S&P500, M7: 고점 대비 -15 / -20 / -30 / -40%
  - 전고점 기준(기본): 상장 이후 최고 종가 / 기간 고점 기준: 화면에서 고른 기간 안의 최고 종가
- VIX: 30 이상, 40 이상
- 공포탐욕지수: 15 이하, 10 이하
- 미국 10년물: 5% 위/아래, 최근 1개월 변화로 상승세/하락세
- WTI: $80 위/아래, 최근 1개월 변화로 상승세/하락세

## 문제 해결
- Actions가 빨간 X: 실행 기록을 열어 `데이터 받기` 단계 로그 확인. `[fetch] ... 실패` 줄에 원인이 나옵니다
- KOFR 통계를 못 찾는다는 메시지: Secret에 `KOFR_STAT_CODE`, `KOFR_ITEM_CODE`를 ECOS에서 확인한 값으로 추가하면 됩니다 (workflow에 이미 연결돼 있음)
- GitHub는 60일 동안 저장소 활동이 없으면 예약 실행을 멈출 수 있습니다. 매일 자동 커밋이 생기므로 보통 문제 없지만, 멈추면 Actions 탭에서 다시 Enable 하면 됩니다
