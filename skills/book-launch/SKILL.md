---
name: book-launch
description: This skill should be used when an author wants a marketing plan for their own book launch, e.g. "책 마케팅 계획 세워줘", "출간 마케팅 전략", "내 책 홍보 어떻게 해", "출간 준비 할 일 정리", "book launch plan". Also use it when the author reports numbers for that book (weekly sales after launch, launch-alert sign-ups, pre-order copies), asks whether a piece of content is worth making for the book, or asks what to do first this week. Not for writing the manuscript, finding a publisher, or marketing things that are not books.
version: 0.1.0
---

# 책 출간 마케팅 계획

책과 저자의 상황을 받아, 출간 8주 전부터 출간 후 12주까지의 할 일을 문서로 만든다. 여러 에이전트를 동시에 돌려 진단하고, 할 일을 짜고, 검토한다.

## 세 가지 원칙

1. **에이전트는 숫자를 만들지 않는다.** 숫자는 사용자가 준 값이나 웹에서 확인한 값에서 오고, 계산은 `scripts/calc.py`가 한다. 에이전트는 예/아니오로 분류하고 글을 쓴다. 메인도 더하거나 나누지 않고 계산 결과를 옮겨 적기만 한다.
2. **사용자에게는 쉬운 말만 쓴다.** 사용자에게 보이는 모든 글(질문, 진행 안내, 결과)에 `references/glossary.md`의 표시 문구만 쓴다. 에이전트 이름, 파일 형식, 내부 용어를 말하지 않는다. 진행 안내는 "책 정보를 정리하고 있어요", "할 일을 짜고 있어요"처럼 한다.
3. **갈래에 맞춘다.** 첫 책인 사람과 판매 기록이 있는 사람은 질문, 목표, 분량, 말투가 다르다.

## 경로와 명령

- **스킬 폴더**: `${CLAUDE_PLUGIN_ROOT}/skills/book-launch`. 이 값이 비어 있거나 글자 그대로 보이면 이 파일이 있는 폴더.
- **작업 폴더**: 사용자의 현재 폴더 아래 `book-launch/`. 없으면 만든다. 중간 파일은 `book-launch/work/`에 둔다.
- **계산**: `python "<스킬 폴더>/scripts/calc.py" <명령> ...` (`python`이 없으면 `python3`). 경로는 항상 큰따옴표로 감싼다. 아래 명령은 모두 **작업 폴더에서** 실행한다. 결과를 파일로 받을 때는 셸의 `>` 대신 `--out <파일>`을 쓴다.

에이전트에게 주는 지시문에는 작업 폴더와 스킬 폴더의 절대 경로, 갈래, 말투 수준(`term_level`)을 항상 적는다.

## 갈래

| | 첫 책 (`first_book`) | 실적 있음 (`has_record`) |
|---|---|---|
| 질문 | 공통 8개 | 공통 8개 + 실적 5개 |
| 기본 목표 | 1쇄 부수를 12주 안에 다 팔기 | 전작 첫 주 판매 넘기 |
| 첫 주 예상 판매 | 채널 계산이 기준. 비슷한 책 조사는 대조에만 씀 | 전작 기록으로 계산 |
| 할 일 분량 | 꼭 할 일 30개 이내, 나머지는 "여유 있으면". 줄기마다 16개까지 | 줄기마다 24개까지 |
| 목표가 어려울 때 | 내 채널 몫과 계산이 모르는 부분을 나눠 말함 | 출간일을 바꿀 수 있으면 미뤘을 때 더 준비할 수 있는 것을 말함 |
| 말투 (`term_level`) | 쉬운 말만 (`plain`) | 쉬운 말 + 원래 용어를 괄호로 한 번 (`with_original`) |

원래 용어는 스크립트가 문서로 바꿀 때 붙인다. 에이전트와 메인이 쓰는 글에는 붙이지 않는다.

## 깊이

사용자가 따로 말하지 않으면 **기본**으로 한다. "빨리", "간단히"라고 하면 빠르게, "자세히", "꼼꼼히"라고 하면 꼼꼼히.

| 깊이 | 분석 (동시에) | 할 일 작성 (동시에) | 검토 |
|---|---|---|---|
| 빠르게 | `evidence-auditor`, `criticism-checker`, `angle-designer` | 메인이 `work/items-all.json` 하나로 직접 작성 | `strategy-verifier` |
| 기본 | 위 셋 + `reference-forecaster` (첫 책 갈래만) | `phase-planner` 3개 (줄기 `evidence`, `readers`, `reach`) | `strategy-verifier` |
| 꼼꼼히 | 위 셋 + `reference-forecaster` (두 갈래 모두, "경쟁 신간도 조사") | `phase-planner` 3개 | `strategy-verifier` + 독자 역할 검토 |

- 에이전트 유형 이름은 `book-launch:<이름>`이다. 그 유형이 없으면 일반 에이전트에게 "`${CLAUDE_PLUGIN_ROOT}/agents/<이름>.md`를 먼저 읽고 그 본문을 지시로 따르라"고 시킨다.
- 같은 단계의 에이전트는 한 메시지에서 한꺼번에 실행한다.
- 빠르게 깊이에서 메인이 직접 할 일을 쓸 때는 `references/phases.md`와 `agents/phase-planner.md`의 규칙을 모두 따른다.
- 에이전트가 파일을 만들지 못했으면 한 번 다시 시킨다. 웹 검색을 쓸 수 없으면 비슷한 책 조사는 건너뛰고 "찾지 못함"으로 적는다.

## 진행 순서

### 0. 시작

1. **요청을 가른다.**
   - 새 계획을 원함 → 1단계부터.
   - 가벼운 질문("책 홍보 어떻게 해요?")만 함 → 짧게 답하고, 전체 계획을 만들지 묻는다.
   - 이미 계획이 있고 숫자(주간 판매, 출간 알림 신청 수, 예약 판매 부수)를 알려 줌 → "숫자가 들어왔을 때" 절.
   - 콘텐츠 하나를 만들지, 지금 뭐부터 할지 물음 → "낱개 질문" 절.
2. `references/glossary.md`를 읽는다.
3. `python --version`으로 Python이 있는지 본다. 없으면 "계산에 필요한 프로그램(Python)이 없어요. 설치를 도와드릴까요?"처럼 쉬운 말로 알린다. 계산 중 PyYAML이 없다고 나오면 같은 식으로 알리고 `pip install pyyaml` 실행을 제안한다.
4. 깊이를 정한다. 기본 이상이면 "여러 작업을 동시에 돌려서 몇 분 걸리고 사용량이 꽤 듭니다"를 한 줄로 알린다.
5. 작업 폴더의 `work/`에 이전 결과가 있으면 지운다(`profile.yaml`과 계획 문서는 남긴다). 남아 있으면 할 일이 두 배로 읽힌다.

### 1. 정보 받기

`references/intake.md`를 따른다. 작업 폴더에 `profile.yaml`이 이미 있으면 요약해 보여 주고 바뀐 것만 묻는다. 없으면 갈래 질문부터 대화로 받아 `templates/profile.example.yaml` 양식으로 `profile.yaml`을 쓴다. 사용자에게 파일을 직접 채우라고 하지 않는다.

### 2. 첫 계산

```
calc.py estimate profile.yaml --out work/estimate.json
```

결과에 따라 갈린다.

- `weeks_to_launch`가 음수(이미 출간)면 새 계획 대신 "숫자가 들어왔을 때" 절로 간다.
- `weeks_to_launch`가 8보다 작으면 계획은 지금부터 시작한다. 4단계의 요약에 남은 주 수를 적는다.
- `no_channel`이 참이면 "글을 올릴 곳 하나 정하기"를 넣어야 할 일의 맨 위에 둔다.
- `time_budget`이 비어 있으면(하루 가능 시간을 모름) 하루 1시간으로 가정해 `profile.yaml`에 적고 다시 계산한다. 사용자에게는 추측이라고 알린다.

### 3. 분석 (동시에)

깊이 표의 분석 에이전트를 한꺼번에 실행한다. 끝나면 `work/`에 `audit.json`, `criticism.md`, `angles.md`, (있으면) `reference.json`이 생긴다. `criticism-checker`가 답으로 준 질문 5개의 예/아니오는 4단계에서 `work/checks.md`에 옮겨 적는다.

### 4. 판정

1. `calc.py forces work/audit.json --out work/forces.json`으로 가장 약한 힘과, 출간 후 여섯 주의 큰 일을 어느 줄기가 맡는지(`big_weeks`)를 얻는다.
2. `reference.json`의 `comparables` 가운데 `copies`와 `weeks`가 숫자인 것을 `profile.yaml`의 `reference.comparables`에 옮겨 적고 2단계 계산을 다시 한다. 3권이 안 되면 스크립트가 쓰지 않는다. `note`와 `competing`은 요약에 옮긴다.
3. **목표를 확인한다.** 아래 경우에는 할 일을 짜기 전에 사용자에게 숫자를 보여 주고 목표를 어떻게 할지 묻는다. 목표가 바뀌면 `targets.goal_copies`와 `goal_weeks`를 고치고 2단계 계산을 다시 한다.
   - 판정이 "어려움"일 때: 내 채널 몫(`feasible_goal_copies`)과 목표를 나란히 보여 준다.
   - 목표가 없을 때(`verdict`가 비어 있음): 예상 판매만 보여 주고, 목표를 지금 정할지 나중에 정할지 묻는다. 나중에 정하면 판정 줄에는 예상만 적는다.
4. `references/framework.md` 3절의 출간 전 점검 10가지를 판정해 `work/checks.md`에 적는다(번호, 예/아니오, 근거, 아니오일 때 넣을 일). 6·7·9번은 할 일을 짠 뒤에 확정되므로 여기서는 "할 일에서 채움"으로 둔다.
5. `work/brief.md`를 쓴다. 양식은 `references/formats.md`의 "요약". 할 일을 짜는 에이전트는 이 요약을 기준으로 삼는다. 주차별 날짜, 줄기별 저자 시간, 큰 일을 맡는 주는 계산 결과를 그대로 옮긴다. "넣어야 할 일"은 그 일이 키우는 힘에 따라 줄기 하나에 배정한다. 줄기를 넘나드는 것(고친 한 문장 소개, 독자를 부르는 이름, 예약 판매가 열리는 날 등)은 "줄기 사이 약속"에 누가 정하는지 적는다. 채널은 세 줄기가 함께 쓰므로 "알리는 자리 달력"에 주마다 모든 채널에 내는 부탁 하나와 고정 자리에 걸 것을 정해 준다. 프로필에 있는 채널 이름만 쓴다.

### 5. 할 일 작성 (동시에)

할 일은 시기가 아니라 힘으로 나눠 쓴다. `phase-planner`를 줄기 `evidence`(증거와 검색), `readers`(답하기와 팬 모임), `reach`(퍼뜨리기와 연결)로 세 번 실행한다. 지시문에 줄기를 적는다. 결과는 `work/items-evidence.json`, `items-readers.json`, `items-reach.json`이다. 줄기 하나가 출간 8주 전부터 끝까지를 맡기 때문에, 모으는 일과 쓰는 일이 한 작성자 안에서 이어진다.

### 6. 검사와 조립

1. `calc.py check profile.yaml "work/items-*.json"`. 문제가 나오면 고친다. 한두 건은 해당 JSON을 직접 고치고, 줄기 전체의 문제면 그 줄기 에이전트에게 문제 목록을 주고 다시 쓰게 한다. 스크립트는 빈 주, 한 주에 큰 일이 둘인 경우, 저자 시간 초과, 줄기 파일에 다른 줄기의 힘이 들어간 경우를 잡는다. **세 번 고쳐도 통과하지 못하면 멈추고 7단계에서 사용자에게 알린다.**
   - 첫 책 갈래에서는 "여유 있으면"으로 내려간 일 가운데 꼭 할 일이 기대는 준비 일이 있는지 보고, 합계 30개 안에서 `must: true`로 올린다. 30개를 넘으면 `phases.md`의 순서로 내린다.
   - 결과의 `notes`에 꼭 할 일인데 후순위라는 알림이 있으면 그 일을 바꾸거나, 그래도 필요한 이유를 설명에 적게 한다.
   - 큰 일 여섯 개의 제목을 나란히 놓고 본다. 두 줄기가 같은 소재를 큰 일로 잡았으면 한쪽 줄기에 바꾸게 한다. 세 줄기는 서로의 큰 일을 모른다.
   - 세 줄기가 답에 적은 "다른 줄기가 해 둔다고 가정한 것"을 모아, 실제로 그 일이 다른 줄기 파일에 있는지 확인한다. 없으면 맡을 줄기에 넣게 한다.
2. `work/head.md`와 `work/tail.md`를 쓴다. 양식은 `references/formats.md`의 "첫 장"과 "끝 장". 4단계에서 "할 일에서 채움"으로 둔 점검을 여기서 확정한다.
3. 문서로 만든다.

```
calc.py render profile.yaml "work/items-*.json" --head work/head.md --tail work/criticism.md --tail work/angles.md --tail work/tail.md --out 출간-마케팅-계획.md
```

4. `calc.py words 출간-마케팅-계획.md`로 금지어를 찾는다. 말투가 `with_original`이면 `--parens-ok`를 붙인다. 걸린 낱말은 원본 파일에서 표시 문구로 바꾸고 3번부터 다시 한다.
5. `strategy-verifier`를 실행한다. 지시문에 할 일 파일 이름을 적는다. 심각도 높음과 보통인 문제를 고치고 1번부터 다시 한 뒤 한 번 더 검토받는다. **검토는 모두 합쳐 두 번까지다.** 그래도 남은 문제는 7단계에서 알린다.
   - 꼼꼼히 깊이에서는 첫 검토 때 일반 에이전트 하나에게 "이 책의 대상 독자 입장에서 `angles.md`와 한 장 요약을 읽고, 살 마음이 드는지와 걸리는 점 3가지를 말해 달라"고 함께 맡긴다. 그 의견은 `angles.md`를 고치는 데 쓴다.

### 7. 전달

- 채팅에는 한 장 요약만 보여 주고 문서 위치(`book-launch/출간-마케팅-계획.md`)를 알린다. 전체 할 일 목록을 채팅에 다시 쓰지 않는다.
- "알려주면 더 정확해지는 것"이 있으면 그중 하나를 질문으로 건넨다.
- 검사나 검토에서 끝내 못 고친 문제가 있으면 숨기지 않고 말한다.

## 정보가 바뀌었을 때

| 바뀐 것 | 다시 하는 곳 |
|---|---|
| 채널 숫자, 목표, 하루 가능 시간 | 2단계 계산, 그리고 4단계의 요약부터 |
| 한 문장 소개, 목차 | 3단계부터 전부 |
| 출간일 | 2단계 계산. 남은 주가 달라지면 5단계부터 |
| 출간 알림 신청 수, 예약 판매 부수, 주간 판매 | 아래 "숫자가 들어왔을 때" |

## 숫자가 들어왔을 때

**출간 전**: 출간 알림 신청 수는 `experiment.signup_count`에, 예약 판매 부수는 `experiment.preorder_copies`에 넣고 2단계 계산을 다시 한다. 달라진 예상과 판정을 알려 주고, 문서의 첫 장과 끝 장을 고쳐 6단계 3번부터 다시 조립한다.

**출간 후**: 주간 판매량을 받으면

1. `profile.yaml`의 `actuals.weekly_sales`에 주마다 이어 적는다.
2. `calc.py flow <1주차> <2주차> ...`로 주간 판매 흐름을 보여 준다. 1 미만이면 줄고 있다는 뜻이다.
3. `framework.md` 4절의 출간 후 순서로 이번 주에 먼저 할 일을 고른다.
4. 두 주 이상 쌓였으면 사용자에게 묻고 `targets.weekly_flow`를 실제 값으로 바꿔 2단계 계산을 다시 한다.

이 책의 실적을 이 책 프로필의 `record`에 넣지 않는다. 자기 첫 주를 전작 기록으로 쓰게 된다. 다음 책을 시작할 때 `actuals`의 첫 주 판매와 누적 판매, 당시 팔로워 합계를 새 프로필의 `record`로 옮긴다.

## 낱개 질문

- **"이 글(영상) 만들까요?"**: `framework.md` 6절 구간으로 8개 항목을 사용자와 함께 매기고 `calc.py cscore <8개>`를 돌린다. 책 다음에 권할 상품이 있는 저자에게는 절대 기준을 쓴다(3점 미만은 권하지 않음, 4점 이상은 집중). 책만 파는 저자는 점수가 전반적으로 낮게 나오므로, 다른 후보 한두 개를 같이 매겨 어느 쪽이 나은지 순위로 답한다.
- **"지금 뭐부터 해요?"**: `framework.md` 4절 순서를 따른다. 문서가 있으면 그 안의 할 일에서 고른다.
- **"○○ 초안 써 주세요"**: 문서의 그 할 일과 내 책 정보를 읽고, 그대로 보낼 수 있는 글(편집자 메일, 모집 글, 추천 부탁)을 쓴다. 프로필에 없는 사실은 빈칸으로 두고 무엇을 채워야 하는지 적는다.

## 참고 파일

| 파일 | 언제 읽는가 |
|---|---|
| `references/glossary.md` | 0단계에서 항상. 말투, 판정 문구, 금지어 |
| `references/intake.md` | 1단계. 질문 문구와 저장 위치 |
| `references/framework.md` | 4단계 판정, 낱개 질문 |
| `references/formats.md` | 4단계 요약, 6단계 첫 장과 끝 장 양식 |
| `references/rubric.md` | 에이전트가 읽음. 메인은 판정 근거를 확인할 때만 |
| `references/phases.md` | 할 일 양식과 규칙. 빠르게 깊이에서 직접 쓸 때 |
| `templates/profile.example.yaml` | 프로필 양식 |
