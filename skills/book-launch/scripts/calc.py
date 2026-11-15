#!/usr/bin/env python3
"""책 출간 마케팅 계산기.

원칙: 에이전트는 숫자를 만들지 않는다. 숫자는 여기서만 계산한다.
변수 이름에 단위(_people 명, _copies 권)를 붙여 서로 다른 단위를 비교하지 않는다.

명령:
  estimate <profile.yaml>                첫 주 예상 판매, 목표 대비 판정, 더 알려주면 좋은 값
  forces   <audit.json>                  판매를 이어가는 힘 6가지 점수와 가장 약한 힘
  cscore   <점수 8개>                     콘텐츠 가성비 점수
  check    <profile.yaml> <items.json..>  할 일 목록 기계 검사
  render   <profile.yaml> <items.json..> [--head f].. [--tail f]..  할 일 목록을 문서로
  flow     <주간 판매량 ..>               출간 후 실제 주간 판매 흐름
  words    <문서.md> [--parens-ok]        금지어 검사
  --selftest                             자체 점검

모든 명령에 --out <파일>을 붙이면 결과를 그 파일에 UTF-8로 저장한다.
--head, --tail은 여러 번 쓸 수 있고 적은 순서대로 이어 붙인다.
"""
import glob
import json
import os
import re
import sys
from datetime import date, timedelta

# 내부 키: (표시 문구, 원래 용어). 표시 문구를 바꾸면 references/glossary.md도 같이 바꾼다.
FORCES = {
    "proof": ("남들도 샀다는 증거", "사회적 증거"),
    "reply": ("저자가 독자에게 답하기", "보상 루프"),
    "spread": ("독자가 대신 퍼뜨리기", "콘텐츠 재생산"),
    "link": ("채널끼리 연결", "채널 시너지"),
    "fans": ("팬 모임", "부족 형성"),
    "search": ("검색하면 나오는 글", "검색 자산"),
}
# 결과 문서에 싣는 한 줄 설명
FORCE_NOTES = {
    "proof": "후기, 순위, 추천이 쌓여 다음 사람이 덜 망설이게 되는 것",
    "reply": "독자의 글과 인증에 저자가 직접 반응해 독자가 더 움직이는 것",
    "spread": "독자가 책 내용을 자기 말로 올려 저자 대신 알리는 것",
    "link": "한 채널에서 본 사람이 다른 채널과 구매 링크로 넘어오는 것",
    "fans": "독자들이 한데 모여 서로 권하고 함께 하는 것",
    "search": "글과 영상이 쌓여 검색으로 사람들이 찾아오는 것",
}
# 할 일을 나눠 쓰는 세 줄기. 줄기마다 힘 두 가지를 출간 전부터 끝까지 맡는다.
# 시기로 나누면 같은 줄기의 일이 여러 작성자에게 흩어져 겹치거나 서로 미루게 된다.
THREADS = {
    "evidence": ("proof", "search"),
    "readers": ("reply", "fans"),
    "reach": ("spread", "link"),
}
THREAD_NAMES = {"evidence": "증거와 검색", "readers": "답하기와 팬 모임", "reach": "퍼뜨리기와 연결"}
REPEAT = ("daily", "weekly")  # 반복하는 일. author_minutes 는 daily 가 하루 분, weekly 가 한 주 분
# 점수가 같을 때 먼저 손볼 순서. 팬 모임은 앞의 힘들이 쌓인 결과라 맨 뒤.
TIE_ORDER = ["reply", "proof", "spread", "link", "search", "fans"]

# 프로필의 targets 로 덮어쓸 수 있는 기본값. 전부 "추측" 등급이다.
DEFAULTS = {
    "activation_rate": 0.15,                # 팔로워 중 실제로 보는 비율
    "conversion_rate": [0.01, 0.02, 0.03],  # 본 사람 중 사는 비율 [낮음, 기준, 높음]
    "weekly_flow": [0.7, 0.85, 1.0],        # 다음 주 판매 ÷ 이번 주 판매 [낮음, 기준, 높음]
    "signup_conversion": [0.1, 0.2, 0.4],   # 출간 알림 신청자 중 사는 비율
    "warning_ratio": 0.6,                   # 목표의 이 비율 미만이면 "어려움"
    "overlap_discount": 0.0,                # 여러 채널을 같이 보는 사람 할인 (0 = 할인 없음)
    "time_use_ratio": 0.85,                 # 말한 하루 가능 시간 중 계획에 쓰는 비율. 남는 15%는 여유
    "ad_cost_per_sale": None,               # 광고로 1권 파는 데 드는 돈(원). 모르면 광고 효과는 0으로 둔다
}


def triple(v):
    """숫자 하나 또는 [낮음, 기준, 높음]을 길이 3 목록으로."""
    return [float(v)] * 3 if isinstance(v, (int, float)) else [float(x) for x in v]


def round2(x):
    """유효숫자 2자리로 반올림 (1620 -> 1600)."""
    if x < 100:
        return int(round(x))
    m = 10 ** (len(str(int(x))) - 2)
    return int(round(x / m) * m)


def week_label(w):
    return f"출간 {-w}주 전" if w < 0 else "출간 주" if w == 0 else f"출간 후 {w}주차"


def weeks_to(publish_date, today=None):
    try:
        d = date.fromisoformat(str(publish_date))
    except ValueError:
        return None
    return (d - (today or date.today())).days // 7


def load_profile(path):
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML이 필요합니다. 설치: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_items(patterns):
    items = []
    for pat in patterns:
        for path in sorted(glob.glob(pat)) or [pat]:
            m = re.search(r"items-(\w+)\.json$", os.path.basename(path))
            with open(path, encoding="utf-8") as f:
                for it in json.load(f):
                    if m and m.group(1) in THREADS:
                        it["_thread"] = m.group(1)
                    items.append(it)
    return items


def week_dates(publish_date, first=-8, last=12):
    """주차별 월요일 날짜. 0은 출간일이 든 주. 에이전트가 날짜를 직접 세지 않게 미리 준다."""
    try:
        d = date.fromisoformat(str(publish_date))
    except ValueError:
        return None
    monday = d - timedelta(days=d.weekday())
    return {str(w): (monday + timedelta(weeks=w)).isoformat() for w in range(first, last + 1)}


def time_budget(hours, ratio=1.0):
    """줄기별 저자 시간 몫 (분). 세 줄기를 동시에 짜도 합계가 한 주 한도를 넘지 않게 미리 나눈다.

    한 주 한도 = 하루 가능 시간 × 7일 × ratio. 사람은 쓸 수 있는 시간을 넉넉히 말하므로 ratio 로 여유를 둔다.
    한도의 2/3는 매일·매주 하는 일, 1/3은 한 번 하는 일과 큰 일. 5분 단위로 내림한다.
    """
    if not hours:
        return None
    cap = hours * 60 * 7 * ratio

    def floor5(x):
        return int(x // 5 * 5)

    repeat = floor5(cap * 2 / 3)
    # 답하기는 하루 30분이 기준이지만, 하루에 쓸 수 있는 시간의 절반을 넘지 않게 한다
    reply_min = min(30, floor5(cap / 7 / 2))
    # 답하기는 저자만 할 수 있어 먼저 떼어 둔다. 남는 것을 나머지 두 줄기가 나눈다.
    readers = max(reply_min * 7, floor5(repeat * 0.5))
    rest = repeat - readers
    return {
        "weekly_cap": round(cap),
        "reply_min_per_day": reply_min,          # 저자가 독자에게 답하는 최소 시간
        "repeat_per_week": {                     # 매일·매주 하는 일의 한 주 합계 (매일 하는 일은 7을 곱해 센다)
            "evidence": floor5(rest * 0.4), "readers": readers, "reach": floor5(rest * 0.6)},
        "once_per_week": {                       # 한 번 하는 일과 큰 일의 한 주 합계. 줄기마다 같은 몫
            "before_repeat": floor5(cap * 0.31),   # 출간 4주 전까지 (반복 일이 시작되기 전)
            "pre_launch": floor5(cap * 0.107),     # 출간 3주 전부터 출간 주까지
            "big_week": floor5(cap * 0.2),         # 출간 후, 내가 큰 일을 맡은 주
            "other_week": floor5(cap * 0.065),     # 출간 후, 큰 일을 맡지 않은 주
        },
    }


# ---------------------------------------------------------------- estimate

def estimate(p, today=None):
    t = {**DEFAULTS, **{k: v for k, v in (p.get("targets") or {}).items() if v is not None}}
    track = p.get("track") or "first_book"
    book, res, rec, exp = (p.get(k) or {} for k in ("book_info", "resources", "record", "experiment"))
    conv, flow_rates = triple(t["conversion_rate"]), triple(t["weekly_flow"])

    # 1) 채널별 "실제로 보는 사람" (명)
    channels = []
    for c in p.get("channels") or []:
        followers = c.get("followers") or 0
        if c.get("avg_views") is not None:
            people, grade = float(c["avg_views"]), "확실"
        else:
            people, grade = followers * t["activation_rate"], "추측"
        channels.append({"name": c.get("name"), "followers": followers,
                         "viewers_people": round(people), "grade": grade})
    keep = 1 - t["overlap_discount"]
    viewers_people = sum(c["viewers_people"] for c in channels) * keep
    followers_total = sum(c["followers"] for c in channels)

    # 2) 광고로 팔리는 권수 (권). 과거 광고 성과가 있을 때만 계산한다.
    budget = res.get("ad_budget") or 0
    past = rec.get("past_ad") or {}
    cost_per_sale, ad_grade = t["ad_cost_per_sale"], "추측"
    if past.get("spend") and past.get("sales"):
        # 과거 기록은 확실하지만, 같은 효율이 새 예산에서도 이어진다는 것은 가정이다
        cost_per_sale, ad_grade = past["spend"] / past["sales"], "비슷한 사례"
    paid_copies = budget / cost_per_sale if budget and cost_per_sale else 0
    preorder_copies = exp.get("preorder_copies") or 0

    # 3) 첫 주 예상 판매 (권)를 여러 방법으로 계산
    def channel_copies(rate):  # 명 × 비율 = 권. 예약 판매분은 출간 주에 합쳐 세므로 더한다
        return viewers_people * rate + paid_copies + preorder_copies

    routes = {"channel": {"copies": [channel_copies(r) for r in conv],
                          "basis": "채널 계산: 실제로 보는 사람 × 사는 비율(추측)"}}
    if rec.get("prev_first_week_sales"):
        prev = float(rec["prev_first_week_sales"])
        scaled = prev * followers_total / rec["prev_followers_total"] if rec.get("prev_followers_total") else prev
        # 기준은 팔로워 규모에 맞춰 환산한 값. 환산은 가정이므로 범위의 한쪽 끝은 환산하지 않은 기록으로 둔다.
        routes["record"] = {"copies": [min(prev, scaled), scaled, max(prev, scaled)],
                            "basis": "전작 첫 주 판매 기록(확실)을 지금 팔로워 규모에 맞춰 환산. "
                                     "팔로워가 늘어난 만큼 판매도 는다고 가정한 값이라 실제는 다를 수 있음"}
    if exp.get("signup_count"):
        routes["signup"] = {"copies": [exp["signup_count"] * r for r in triple(t["signup_conversion"])],
                            "basis": "출간 알림 신청 수(확실) × 신청자 중 사는 비율(추측)"}
    # 비슷한 책 조사: 책마다 (부수, 주 수)를 받아 주당 판매를 여기서 계산한다. 3권 이상일 때만 쓴다.
    ref = p.get("reference") or {}
    per_week = sorted(c["copies"] / c["weeks"] for c in ref.get("comparables") or []
                      if c.get("copies") and c.get("weeks"))
    if len(per_week) >= 3:
        ref_copies = [per_week[0], per_week[len(per_week) // 2], per_week[-1]]
    elif ref.get("base"):
        ref_copies = [float(ref.get("low", ref["base"])), float(ref["base"]), float(ref.get("high", ref["base"]))]
    else:
        ref_copies = None
    if ref_copies:
        routes["reference"] = {"copies": ref_copies,
                               "basis": "비슷한 책의 공개된 판매 부수를 주당으로 나눈 값(비슷한 사례). "
                                        "부수가 공개되는 책은 잘 팔린 책이라 높게 치우쳤을 수 있고, "
                                        "첫 주가 아니라 여러 주의 평균임"}
    # 이미 팔린 예약 판매분보다 예상이 낮을 수는 없다
    for k in ("record", "signup"):
        if k in routes:
            routes[k]["copies"] = [max(x, preorder_copies) for x in routes[k]["copies"]]
    # 비슷한 책 조사는 대조에만 쓴다. 높게 치우친 값이라 기준으로 삼지 않는다.
    main = next(k for k in ("record", "signup", "channel") if k in routes)

    # 4) 두 방법이 2배 넘게 다르면 범위를 넓히고 알린다
    base_main = routes[main]["copies"][1]
    disagree = [k for k, r in routes.items() if k != main and base_main > 0 and r["copies"][1] > 0
                and max(r["copies"][1], base_main) / min(r["copies"][1], base_main) >= 2]
    first_week = list(routes[main]["copies"])
    if disagree and main != "record":  # 전작 기록은 실제 값이라 추측 때문에 넓히지 않는다
        first_week[0] = min(routes[k]["copies"][0] for k in [main, *disagree])
        first_week[2] = max(routes[k]["copies"][2] for k in [main, *disagree])

    # 5) 목표와 비교. 목표가 여러 주짜리면 누적 판매로 비교한다.
    goal = t.get("goal_copies") or (book.get("first_print_run") if track == "first_book"
                                    else rec.get("prev_first_week_sales") or 3500)
    weeks = int(t.get("goal_weeks") or (12 if track == "first_book" else 1))

    def cumulative(first, rate):
        return first * sum(rate ** k for k in range(weeks))

    cum = [cumulative(first_week[i], flow_rates[i]) for i in range(3)]

    def level(copies):
        r = copies / goal
        return "가능" if r >= 1 else "보강하면 가능" if r >= t["warning_ratio"] else "어려움"

    # 6) 판단을 뒤집는 값만 골라 되묻는다
    asks, verdict, stable, feasible = [], None, None, None
    if not goal:
        asks.append("목표 판매량이 없습니다. 1쇄 부수나 목표 권수를 알려주세요.")
    else:
        verdict = level(cum[1])
        stable = level(cum[0]) == level(cum[2])
        if main == "channel" and len({level(cumulative(channel_copies(r), flow_rates[1])) for r in conv}) > 1:
            asks.append("본 사람 중 몇 명이 사는지 모릅니다. 출간 알림 신청을 받아 신청 수를 알려주세요."
                        if track == "first_book" else
                        "본 사람 중 몇 명이 사는지 모릅니다. 전작 첫 주 판매량과 당시 팔로워 수를 알려주세요.")
        if weeks > 1 and len({level(cumulative(first_week[1], f)) for f in flow_rates}) > 1:
            asks.append("출간 후 매주 판매가 얼마나 이어질지 모릅니다. 출간 뒤 주간 판매량을 넣으면 실제 값으로 다시 계산합니다.")
        if main == "channel" and not stable:
            total = sum(c["viewers_people"] for c in channels) or 1
            asks += [f"{c['name']}의 최근 게시물 10개 평균 조회수를 알려주세요."
                     for c in channels if c["grade"] == "추측" and c["viewers_people"] / total >= 0.2]
        if verdict == "어려움" and cum[1] > 0:
            feasible = round2(cum[1])
    no_channel = main == "channel" and viewers_people == 0
    if no_channel:
        asks.insert(0, "운영하는 채널이 없어 내 채널로 팔 수 있는 양을 계산하지 못했습니다. "
                       "글을 올릴 곳 하나를 먼저 정하는 것이 첫 할 일입니다.")
    if budget and not cost_per_sale:
        asks.append("광고비는 있지만 효과를 계산하지 못했습니다. 과거 광고에 쓴 돈과 그때 팔린 권수를 알려주세요.")

    # 7) 어디서 팔리는지 (기준값 기준)
    # 광고 몫은 채널 계산에서만 따로 본다. 전작 기록에는 그때의 광고 효과가 섞여 있어 나눌 수 없으므로,
    # 전작 기준 예상에는 광고분을 더하지 않고 광고 없이 팔리는 몫도 계산하지 않는다.
    paid_in_estimate = main == "channel" and paid_copies > 0
    organic = viewers_people * conv[1]
    sold = organic + (paid_copies if paid_in_estimate else 0)
    total_viewers = sum(c["viewers_people"] for c in channels) or 1
    contribution = [{"name": c["name"], "share": round(organic * c["viewers_people"] / total_viewers / sold, 2),
                     "cost": "없음"} for c in channels] if sold else []
    if paid_in_estimate:
        contribution.append({"name": "광고", "share": round(paid_copies / sold, 2), "cost": f"{budget:,}원"})
    contribution.sort(key=lambda r: -r["share"])
    free_share = round(organic / sold, 2) if sold and main == "channel" else None
    warnings = []
    if free_share is not None and free_share < 0.5:
        warnings.append("판매의 절반 이상을 광고에 기대고 있습니다. 광고를 끄면 판매가 멈출 수 있어 자체 채널을 먼저 키워야 합니다.")
    if disagree:
        warnings.append("전작 기록으로 계산한 값이 기본 비율로 계산한 값과 2배 넘게 다릅니다. 실제 기록인 전작 기준을 따랐습니다."
                        if main == "record" else
                        "계산 방법에 따라 결과가 2배 넘게 다릅니다. 범위를 넓게 잡았습니다.")

    # 채널 계산은 내 채널을 거쳐 팔리는 양만 본다. 이 한계를 결과에 같이 싣는다.
    scope = ("이 숫자는 내 채널을 통해 팔리는 양만 계산한 것입니다. "
             "서점 진열, 출판사 홍보, 입소문으로 팔리는 양은 들어 있지 않습니다.") if main == "channel" else None

    return {
        "track": track,
        "scope": scope,
        "weeks_to_launch": weeks_to(book.get("publish_date"), today),
        "week_dates": week_dates(book.get("publish_date")),
        "date_flexible": book.get("date_flexible"),
        "time_budget": time_budget(res.get("daily_hours"), t["time_use_ratio"]),
        "channels": channels,
        "viewers_people": round(viewers_people), "followers_total": followers_total, "no_channel": no_channel,
        "paid_copies": round(paid_copies), "paid_grade": ad_grade if paid_copies else None,
        "paid_in_estimate": paid_in_estimate,  # 거짓이면 광고분은 첫 주 예상에 들어 있지 않다
        "preorder_copies": preorder_copies,
        "routes": {k: {"copies": [round(x) for x in r["copies"]], "basis": r["basis"]} for k, r in routes.items()},
        "main_route": main, "disagree_with": disagree,
        "first_week_copies": [round(x) for x in first_week],
        "goal_copies": goal, "goal_weeks": weeks,
        "cumulative_copies": [round(x) for x in cum],
        "ratio_to_goal": [round(x / goal, 2) for x in cum] if goal else None,
        "verdict": verdict, "verdict_stable": stable, "feasible_goal_copies": feasible,
        "asks": asks, "contribution": contribution, "free_share": free_share, "warnings": warnings,
        "assumptions": {k: t[k] for k in ("activation_rate", "conversion_rate", "weekly_flow",
                                          "signup_conversion", "warning_ratio", "overlap_discount")},
    }


# ---------------------------------------------------------------- forces

def forces(audit):
    """힘마다 예/아니오 지표 5개. 근거를 못 댄 '예'는 '아니오'로 센다."""
    def counted(i):
        return bool(i.get("yes")) and bool(str(i.get("evidence") or "").strip())

    scores = {k: sum(counted(i) for i in audit.get(k) or []) for k in FORCES}
    weakest, note = min(TIE_ORDER, key=lambda k: scores[k]), None
    if weakest == "fans" and min(scores["proof"], scores["reply"]) < 3:
        # 팬 모임은 증거와 답하기가 쌓인 결과다. 둘 중 하나라도 절반(3점)을 못 넘으면 그쪽이 먼저다.
        weakest = min(("reply", "proof"), key=lambda k: scores[k])
        note = ("팬 모임 점수가 가장 낮지만, 팬 모임은 '남들도 샀다는 증거'와 '저자가 독자에게 답하기'가 "
                "쌓여야 생깁니다. 그래서 그 둘 중 약한 쪽을 먼저 봅니다.")
    weak_thread = next(t for t, fs in THREADS.items() if weakest in fs)
    order = [weak_thread] + [t for t in THREADS if t != weak_thread]
    return {
        "scores": {FORCES[k][0]: s for k, s in scores.items()},
        "weakest": weakest, "weakest_name": FORCES[weakest][0], "note": note,
        "weak_thread": weak_thread,
        # 출간 후 여섯 주의 큰 일을 누가 맡는지. 가장 약한 힘의 줄기가 1주차와 4주차
        "big_weeks": {t: [i + 1, i + 4] for i, t in enumerate(order)},
        "missing": [i.get("q") for i in audit.get(weakest) or [] if not counted(i)],
    }


# ---------------------------------------------------------------- cscore

def cscore(v, low=3.0, high=4.0):
    """콘텐츠 가성비 점수. 입력 8개는 각각 1~10점.

    순서: 조회, 구매로 이어짐, 건당 수익, 다시 쓸 수 있음 / 제작비, 제작 시간, 경쟁, 금방 낡을 위험
    """
    if len(v) != 8 or not all(1 <= x <= 10 for x in v):
        raise ValueError("1~10점 8개가 필요합니다")
    views, buys, price, reuse, cost, hours, rivals, expiry = v
    score = (views * 3 + buys * 4 + price * 3 + reuse * 2.5) / (cost * 2 + hours * 2 + rivals * 3 + expiry * 2)
    return score, "빼는 것을 권함" if score < low else "집중 권함" if score >= high else "보통"


def cscore_marks(items):
    """후보끼리 순위를 매겨 위 1/4과 아래 1/4에 표시. 후보가 4개 미만이면 표시하지 않는다."""
    scored = sorted((it for it in items if it.get("cscore")), key=lambda it: cscore(it["cscore"])[0])
    if len(scored) < 4:
        return {}
    q = len(scored) // 4
    return {**{id(it): " △후순위" for it in scored[:q]}, **{id(it): " ★집중" for it in scored[-q:]}}


# ---------------------------------------------------------------- check / render

def check(items, p, today=None):
    problems = []
    track = p.get("track") or "first_book"
    hours = (p.get("resources") or {}).get("daily_hours")
    weeks_left = weeks_to((p.get("book_info") or {}).get("publish_date"), today)
    ratio = (p.get("targets") or {}).get("time_use_ratio") or DEFAULTS["time_use_ratio"]
    budget = time_budget(hours, ratio) or {}
    for n, it in enumerate(items, 1):
        if it.get("force") not in FORCES:
            problems.append(f"{n}번 '{it.get('title')}': force 값이 {list(FORCES)} 중 하나가 아님")
        elif it.get("_thread") and it["force"] not in THREADS[it["_thread"]]:
            problems.append(f"{n}번 '{it.get('title')}': '{THREAD_NAMES[it['_thread']]}' 줄기 파일인데 "
                            f"다른 줄기의 힘({it['force']})을 키우는 일임")
        if it.get("kind") not in ("once", "big", *REPEAT):
            problems.append(f"{n}번 '{it.get('title')}': kind 값이 once/big/daily/weekly 중 하나가 아님")
        elif it["kind"] not in REPEAT and not isinstance(it.get("when"), int):
            problems.append(f"{n}번 '{it.get('title')}': when(주차)이 정수가 아님")
        elif (it["kind"] not in REPEAT and weeks_left is not None and weeks_left >= 0
              and it["when"] < -weeks_left):
            problems.append(f"{n}번 '{it.get('title')}': {week_label(it['when'])}는 이미 지났음 "
                            f"(출간까지 {weeks_left}주 남음)")
    daily = [it for it in items if it.get("kind") == "daily"]
    repeating = [it for it in items if it.get("kind") in REPEAT]
    for w in range(1, 7):
        bigs = sum(1 for it in items if it.get("kind") == "big" and it.get("when") == w)
        if bigs == 0:
            problems.append(f"출간 후 {w}주차에 '이번 주 큰 일'이 없음")
        elif bigs > 1:
            problems.append(f"출간 후 {w}주차에 '이번 주 큰 일'이 {bigs}개 (한 주에 하나여야 시간 몫이 맞음)")
    # 하루 1시간이 안 되는 저자는 답하기 하나만으로 시간이 찬다. 그때는 하나만 요구한다.
    min_repeat = 3 if not hours or hours >= 1 else 1
    if len(repeating) < min_repeat:
        problems.append(f"매일·매주 하는 일이 {min_repeat}개 미만")
    for key, (name, _) in FORCES.items():
        if not any(it.get("force") == key for it in items):
            problems.append(f"'{name}'을 키우는 일이 없음")
    need = budget.get("reply_min_per_day", 30)
    if not any(it.get("force") == "reply" and (it.get("author_minutes") or 0) >= need for it in daily):
        problems.append(f"저자가 매일 {need}분 이상 독자에게 직접 답하는 일이 없음")
    once_by_week = {}
    for it in items:
        if it.get("kind") not in REPEAT and isinstance(it.get("when"), int):
            once_by_week[it["when"]] = once_by_week.get(it["when"], 0) + (it.get("author_minutes") or 0)
    if hours:
        cap = budget["weekly_cap"]
        for w in sorted(once_by_week):
            # 그 주에 이미 시작한 반복 일: 매일 하는 일은 7번, 매주 하는 일은 1번
            load = once_by_week[w] + sum((7 if it["kind"] == "daily" else 1) * (it.get("author_minutes") or 0)
                                         for it in repeating
                                         if not isinstance(it.get("when"), int) or it["when"] <= w)
            if load > cap:
                problems.append(f"{week_label(w)}: 저자 시간 {load}분이 주간 한도 {cap}분을 넘음")
    # 줄기마다 할 일 개수 상한. 줄기 하나가 전 기간을 맡으면 시간 몫을 다 채우려 드는데,
    # 시간에 들어간다고 사람이 따라갈 수 있는 것은 아니다.
    limit = 16 if track == "first_book" else 24
    per_thread = {}
    for it in items:
        if it.get("_thread"):
            per_thread[it["_thread"]] = per_thread.get(it["_thread"], 0) + 1
    for thread, count in per_thread.items():
        if count > limit:
            problems.append(f"'{THREAD_NAMES[thread]}' 줄기의 할 일이 {count}개 ({limit}개 이내여야 함. "
                            f"시간 몫은 상한이지 채워야 할 양이 아님)")
    # 가장 바쁜 주. 사람은 주 합계보다 하루 몇 분인지로 읽으므로 하루 평균(5분 단위 올림)도 준다.
    busiest = None
    if once_by_week:
        def week_total(w):
            return once_by_week.get(w, 0) + sum(
                (7 if it["kind"] == "daily" else 1) * (it.get("author_minutes") or 0) for it in repeating
                if not isinstance(it.get("when"), int) or it["when"] <= w)
        span = range(min(once_by_week), max(once_by_week) + 1)
        top = max(span, key=week_total)
        total = week_total(top)
        busiest = {"week": week_label(top), "total_minutes": total,
                   "per_day_minutes": -(-total // 7 // 5) * 5 if total else 0}
    must = sum(1 for it in items if it.get("must"))
    if track == "first_book" and must > 30:
        problems.append(f"꼭 할 일이 {must}개 (30개 이내여야 함)")
    marks = cscore_marks(items)
    notes = [f"'{it['title']}': 가성비 순위가 낮은데 꼭 할 일로 표시됨"
             for it in items if marks.get(id(it)) == " △후순위" and it.get("must")]
    # 도와줄 사람이 주마다 맡는 일의 수. 그 사람의 시간은 알 수 없어 개수만 알려 준다.
    # 세 구간이 따로 쓴 일을 합쳐야 보이는 값이라, 양을 확인하는 일은 이 숫자로 쓴다.
    helper_load = {}
    for it in items:
        if it.get("kind") in REPEAT or not isinstance(it.get("when"), int):
            continue
        for name in (n.strip() for n in str(it.get("who") or "저자").split(",")):
            if name and name != "저자":
                weeks_of = helper_load.setdefault(name, {})
                weeks_of[week_label(it["when"])] = weeks_of.get(week_label(it["when"]), 0) + 1
    return {"ok": not problems, "problems": problems, "notes": notes, "count": len(items), "must": must,
            "helper_load": helper_load, "busiest_week": busiest,
            # 첫 장에 옮겨 적을 값 (저자 시간, 분): 매일 하는 일의 하루 합계, 매주 하는 일의 한 주 합계,
            # 한 번 하는 일이 가장 많은 주의 합계
            "author_daily_minutes": sum(it.get("author_minutes") or 0 for it in daily),
            "author_weekly_repeat_minutes": sum(it.get("author_minutes") or 0 for it in repeating
                                                if it["kind"] == "weekly"),
            "author_weekly_once_max": max(once_by_week.values(), default=0)}


def render(items, p, head="", tail=""):
    first = (p.get("track") or "first_book") == "first_book"
    with_orig = p.get("term_level") == "with_original"
    marks, seen = cscore_marks(items), set()

    def force_name(key):
        name, orig = FORCES[key]
        if with_orig and key not in seen:  # 원래 용어는 처음 한 번만 괄호로
            seen.add(key)
            return f"{name}({orig})"
        return name

    solo = len({it.get("who", "저자") for it in items}) <= 1  # 담당이 한 명뿐이면 줄마다 적지 않는다
    dates = week_dates((p.get("book_info") or {}).get("publish_date")) or {}

    def dated(w):  # "출간 8주 전 (11월 23일 주)". 사용자가 날짜를 직접 세지 않게 한다
        label = week_label(w)
        if str(w) in dates:
            d = date.fromisoformat(dates[str(w)])
            label += f" ({d.month}월 {d.day}일 주)"
        return label

    def line(it, prefix=""):
        mark = marks.get(id(it), "")
        if not it.get("cscore"):
            score = ""
        elif with_orig:  # 원래 용어를 아는 사람에게는 점수와 순위 표시를 보여 준다
            score = f". 가성비 {cscore(it['cscore'])[0]:.1f}{mark}"
        else:            # 쉬운 말 문서에는 싣지 않는다. 중요도 하나만 보게 한다
            score = ""
        who = "" if solo else f"담당: {it.get('who', '저자')}. "
        return (f"- [ ] {prefix}**{it['title']}** — {it.get('detail', '')} "
                f"(키우는 힘: {force_name(it['force'])}. {who}중요도: {it.get('priority', '중')}{score})")

    def since(it):  # 반복하는 일 앞에 붙는 말
        weekly = it.get("kind") == "weekly"
        if isinstance(it.get("when"), int):
            return f"({'매주, ' if weekly else ''}{dated(it['when'])}부터) "
        return "(매주) " if weekly else ""

    def start(it):  # 정렬용. 시작 주가 없는 반복 일은 맨 앞
        return it["when"] if isinstance(it.get("when"), int) else -99

    shown = [it for it in items if it.get("must") or not first]
    extra = sorted((it for it in items if first and not it.get("must")), key=start)
    once = sorted((it for it in shown if it.get("kind") not in REPEAT), key=lambda it: it["when"])
    out = ["## 판매를 이어가는 힘 6가지\n",
           "책이 계속 팔리려면 아래 여섯 가지가 함께 돌아야 합니다. 할 일마다 어느 힘을 키우는지 적었습니다.\n",
           *[f"- **{force_name(k)}**: {FORCE_NOTES[k]}" for k in FORCES], ""]
    if with_orig and any(it.get("cscore") for it in items):
        out += ["글이나 영상을 만드는 일에는 가성비 점수가 붙어 있습니다. 들이는 시간과 돈에 비해 얻는 것이 "
                "얼마나 큰지를 계산한 숫자이고, 이 목록 안에서 서로 비교하는 용도입니다. "
                "★집중은 먼저 할 것, △후순위는 미뤄도 되는 것입니다.", ""]
    for title, group in (("출간 전에 할 일", [it for it in once if it["when"] < 0]),
                         ("출간 주에 할 일", [it for it in once if it["when"] == 0]),
                         ("출간 후에 할 일", [it for it in once if it["when"] > 0])):
        if not group:
            continue
        out.append(f"## {title}\n" if title != "출간 주에 할 일" else f"## {dated(0)}에 할 일\n")
        for w in sorted({it["when"] for it in group}):
            if w != 0:
                out.append(f"### {dated(w)}\n")
            out += [line(it) for it in group if it["when"] == w] + [""]
    repeating = [it for it in shown if it.get("kind") in REPEAT]
    label = "매일·매주 하는 일" if any(it["kind"] == "weekly" for it in repeating) else "매일 하는 일"
    if repeating:
        out += [f"## {label}\n",
                "하루 빠졌다면 다음 날 이어서 하면 됩니다. 며칠씩 끊기지 않게 하는 것이 중요합니다.\n",
                *[line(it, since(it)) for it in repeating], ""]
    if extra:
        out += ["## 여유 있으면\n",
                *[line(it, since(it) if it.get("kind") in REPEAT else f"({dated(it['when'])}) ") for it in extra], ""]
    out += ["## 출간 후 6주 달력\n", f"| 주 | 이번 주 큰 일 | {label} |", "|---|---|---|"]
    repeat_titles = ", ".join(it["title"] for it in repeating) or "(없음)"
    for w in range(1, 7):
        big = ", ".join(it["title"] for it in items if it.get("kind") == "big" and it.get("when") == w) or "(없음)"
        out.append(f"| {dated(w).replace('출간 후 ', '')} | {big} | {repeat_titles} |")
    return "\n\n".join(s for s in (head.strip(), "\n".join(out).strip(), tail.strip()) if s) + "\n"


# ---------------------------------------------------------------- flow / words

def flow(sales):
    """출간 후 실제 값. 다음 주 판매 ÷ 이번 주 판매."""
    ratios = [round(b / a, 2) for a, b in zip(sales, sales[1:]) if a]
    latest = ratios[-1] if ratios else None
    reading = None if latest is None else ("판매가 늘고 있음" if latest > 1 else
                                           "판매가 유지되고 있음" if latest == 1 else "판매가 줄고 있음")
    return {"weekly_ratio": ratios, "latest": latest, "reading": reading}


def load_banned():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "glossary.md")
    terms, on = [], False
    with open(path, encoding="utf-8") as f:
        for raw in f:
            if raw.startswith("## "):
                on = raw.strip() == "## 금지어"
            elif on and raw.startswith("- "):
                terms.append(raw[2:].strip().strip("`"))
    return terms


def find_banned(text, banned, parens_ok=False):
    hits = []
    for n, raw in enumerate(text.splitlines(), 1):
        s = re.sub(r"\([^)]*\)", "", raw) if parens_ok else raw
        for term in banned:
            if term.startswith("re:"):
                pat = term[3:]
            elif term.isascii():  # 영문 용어는 낱말 단위로만 (PR 안의 R은 잡지 않는다)
                pat = rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])"
            else:
                pat = re.escape(term)
            if re.search(pat, s):
                hits.append({"term": term, "line": n, "text": raw.strip()})
    return hits


# ---------------------------------------------------------------- selftest

def selftest():
    big_author = {"track": "has_record", "channels": [
        {"name": "유튜브", "followers": 430000}, {"name": "인스타그램", "followers": 50000},
        {"name": "스레드", "followers": 12000}, {"name": "블로그", "followers": 3000},
        {"name": "단톡방", "followers": 10000}, {"name": "뉴스레터", "followers": 5000},
        {"name": "틱톡", "followers": 20000}, {"name": "페이스북", "followers": 10000}]}
    e = estimate(big_author)
    assert e["viewers_people"] == 81000, e["viewers_people"]
    assert e["first_week_copies"][1] == 1620, e["first_week_copies"]
    assert e["ratio_to_goal"][1] == 0.46 and e["verdict"] == "어려움", e
    assert e["feasible_goal_copies"] == 1600

    # 과거 구현의 오류 재현 방지: 팔로워 1.4만이 3,500권 목표를 통과하면 안 된다 (명과 권은 다른 단위)
    small = estimate({"track": "has_record", "channels": [{"name": "스레드", "followers": 14000}]})
    assert small["first_week_copies"][1] == 42 and small["verdict"] == "어려움", small

    # 첫 책: 1쇄 부수가 목표, 12주 누적으로 비교
    first = estimate({"track": "first_book", "book_info": {"first_print_run": 1200},
                      "channels": [{"name": "스레드", "followers": 0, "avg_views": 5000}],
                      "targets": {"weekly_flow": 1.0}})
    assert first["channels"][0]["grade"] == "확실"
    assert first["first_week_copies"][1] == 100 and first["cumulative_copies"][1] == 1200
    assert first["verdict"] == "가능" and first["goal_weeks"] == 12

    # 전작 기록이 있으면 그 방법을 쓴다. 채널 계산과 2배 넘게 다르면 알린다.
    rec = estimate({"track": "has_record", "channels": [{"name": "유튜브", "followers": 100000}],
                    "record": {"prev_first_week_sales": 2000, "prev_followers_total": 50000}})
    assert rec["main_route"] == "record" and rec["first_week_copies"][1] == 4000
    assert rec["disagree_with"] == ["channel"] and rec["first_week_copies"] == [2000, 4000, 4000]
    assert rec["goal_copies"] == 2000  # 실적 있음의 기본 목표는 전작 첫 주 판매
    assert rec["free_share"] is None and rec["scope"] is None and not rec["paid_in_estimate"]

    # 비슷한 책 조사와 채널 계산이 크게 다르면 범위를 넓힌다
    wide = estimate({"track": "first_book", "book_info": {"first_print_run": 2000},
                     "channels": [{"name": "스레드", "followers": 2000}],
                     "reference": {"low": 50, "base": 100, "high": 300}})
    assert wide["main_route"] == "channel" and wide["first_week_copies"] == [3, 6, 300], wide
    assert wide["scope"] and wide["disagree_with"] == ["reference"]
    # 비슷한 책은 (부수, 주 수)로 받아 주당 판매를 여기서 계산한다
    comp = estimate({"track": "first_book", "channels": [{"name": "스레드", "followers": 2000}],
                     "reference": {"comparables": [{"copies": 1000, "weeks": 4}, {"copies": 3000, "weeks": 6},
                                                   {"copies": 900, "weeks": 9}]}})
    assert comp["routes"]["reference"]["copies"] == [100, 250, 500] and comp["verdict"] is None
    none = estimate({"track": "first_book", "book_info": {"first_print_run": 1000}, "channels": []})
    assert none["no_channel"] and none["feasible_goal_copies"] is None
    assert none["asks"][0].startswith("운영하는 채널이 없어")

    # 줄기별 시간 몫을 다 써도 어느 주든 한 주 한도를 넘지 않는다
    for h in (0.5, 1, 2):
        b = time_budget(h)
        rp, on = sum(b["repeat_per_week"].values()), b["once_per_week"]
        assert on["before_repeat"] * 3 <= b["weekly_cap"], b
        assert rp + on["pre_launch"] * 3 <= b["weekly_cap"], b
        assert rp + on["big_week"] + on["other_week"] * 2 <= b["weekly_cap"], b
        assert b["repeat_per_week"]["readers"] >= b["reply_min_per_day"] * 7, b
    assert time_budget(1) == {
        "weekly_cap": 420, "reply_min_per_day": 30,
        "repeat_per_week": {"evidence": 25, "readers": 210, "reach": 40},
        "once_per_week": {"before_repeat": 130, "pre_launch": 40, "big_week": 80, "other_week": 25}}
    assert time_budget(0.5)["reply_min_per_day"] == 15
    # 여유 15%를 두면 하루 1시간인 사람의 한 주 한도는 357분이고 답하기 최소는 25분
    slack = time_budget(1, 0.85)
    assert slack["weekly_cap"] == 357 and slack["reply_min_per_day"] == 25, slack
    assert (sum(slack["repeat_per_week"].values()) + slack["once_per_week"]["big_week"]
            + slack["once_per_week"]["other_week"] * 2) <= slack["weekly_cap"], slack
    assert week_dates("2027-03-10")["0"] == "2027-03-08" and week_dates("2027-03-10")["-3"] == "2027-02-15"

    assert round(cscore([5] * 8)[0], 2) == 1.39 and cscore([5] * 8)[1] == "빼는 것을 권함"
    assert cscore([9, 9, 9, 9, 3, 3, 3, 3])[1] == "집중 권함"

    audit = {k: [{"q": "q", "yes": True, "evidence": "근거"}] * 3 for k in FORCES}
    audit["search"] = [{"q": "근거 없는 예", "yes": True, "evidence": ""}]
    f = forces(audit)
    assert f["weakest"] == "search" and f["missing"] == ["근거 없는 예"], f
    # 팬 모임이 가장 낮아도 증거·답하기가 3점 미만이면 그쪽이 먼저
    audit = {k: [{"q": "q", "yes": True, "evidence": "근거"}] * 4 for k in FORCES}
    audit["fans"], audit["proof"] = [], audit["proof"][:2]
    f = forces(audit)
    assert f["weakest"] == "proof" and f["note"], f
    assert f["weak_thread"] == "evidence" and f["big_weeks"] == {
        "evidence": [1, 4], "readers": [2, 5], "reach": [3, 6]}, f
    # 줄기 파일에 다른 줄기의 힘이 들어 있으면 잡는다. 한 주에 큰 일이 둘이어도 잡는다.
    mixed = check([{"title": "글", "kind": "once", "when": 1, "force": "spread", "_thread": "readers"},
                   {"title": "큰 일 가", "kind": "big", "when": 1, "force": "fans", "_thread": "readers"},
                   {"title": "큰 일 나", "kind": "big", "when": 1, "force": "proof", "_thread": "evidence"}], {})
    assert any("다른 줄기의 힘" in x for x in mixed["problems"]), mixed["problems"]
    assert any("1주차에 '이번 주 큰 일'이 2개" in x for x in mixed["problems"]), mixed["problems"]
    many = check([{"title": f"일 {n}", "kind": "once", "when": 1, "force": "proof", "_thread": "evidence"}
                  for n in range(17)], {"track": "first_book"})
    assert any("할 일이 17개 (16개 이내" in x for x in many["problems"]), many["problems"]

    banned = ["전환율", "R", r"re:D[-+]\d+"]
    assert not find_banned("본 사람 중 사는 비율과 PR 기사", banned)
    assert [h["term"] for h in find_banned("전환율과 R 값, D-8주", banned)] == ["전환율", "R", r"re:D[-+]\d+"]
    assert not find_banned("사는 비율(전환율)", banned, parens_ok=True)
    assert "전환율" in load_banned()

    items = [{"title": f"큰 일 {w}", "kind": "big", "when": w, "force": "proof", "must": True} for w in (1, 2, 4, 5, 6)]
    items += [{"title": "답글", "kind": "daily", "force": "reply", "author_minutes": 30, "must": True}]
    c = check(items, {"track": "first_book", "resources": {"daily_hours": 0.25}})
    assert "출간 후 3주차에 '이번 주 큰 일'이 없음" in c["problems"]
    assert not any("하는 일이" in x and "미만" in x for x in c["problems"])  # 하루 1시간 미만이면 하나로 충분
    assert "매일·매주 하는 일이 3개 미만" in check(items, {"resources": {"daily_hours": 1}})["problems"]
    # 매주 하는 일은 한 주에 한 번만 센다
    wk = check(items + [{"title": "모아 소개", "kind": "weekly", "force": "fans", "author_minutes": 40},
                        {"title": "글", "kind": "daily", "force": "spread", "author_minutes": 0}],
               {"resources": {"daily_hours": 1}})
    assert wk["author_weekly_repeat_minutes"] == 40 and not any("미만" in x for x in wk["problems"])
    # 출간까지 3주 남았는데 8주 전 할 일이 있으면 잡는다
    late = check([{"title": "옛 일", "kind": "once", "when": -8, "force": "proof"}],
                 {"book_info": {"publish_date": "2027-01-22"}}, today=date(2027, 1, 1))
    assert any("이미 지났음" in x for x in late["problems"]), late["problems"]
    assert any("저자 시간 210분" in s for s in c["problems"]), c["problems"]
    doc = render(items, {"track": "first_book"})
    assert "| 3주차 | (없음) | 답글 |" in doc and "키우는 힘: 저자가 독자에게 답하기" in doc
    assert "담당:" not in doc and "## 판매를 이어가는 힘 6가지" in doc
    team = render(items + [{"title": "편집", "kind": "once", "when": 1, "force": "spread", "who": "편집자"}],
                  {"track": "has_record", "term_level": "with_original"})
    assert "담당: 편집자" in team and team.count("(보상 루프)") == 1, team
    # 출간일이 있으면 주차 옆에 날짜가 붙는다
    with_date = render(items, {"track": "first_book", "book_info": {"publish_date": "2027-01-18"}})
    assert "| 3주차 (2월 8일 주) | (없음) |" in with_date, with_date[-400:]
    # 가장 바쁜 주: 큰 일 0분 + 매일 30분 × 7일 = 210분, 하루 평균 30분
    assert c["busiest_week"]["total_minutes"] == 210 and c["busiest_week"]["per_day_minutes"] == 30, c["busiest_week"]
    # 쉬운 말 문서에는 가성비 숫자를 싣지 않고 표시만 싣는다
    scored = [{"title": f"글 {n}", "kind": "once", "when": 1, "force": "spread", "must": True,
               "cscore": [n, n, 3, 3, 3, 3, 3, 3]} for n in (2, 4, 6, 8)]
    assert "가성비" not in render(scored, {"track": "first_book"}) and "★" not in render(scored, {"track": "first_book"})
    assert "가성비 2.7 ★집중" in render(scored, {"track": "has_record", "term_level": "with_original"})
    assert not find_banned(doc, load_banned()), find_banned(doc, load_banned())

    assert flow([1000, 800, 880]) == {"weekly_ratio": [0.8, 1.1], "latest": 1.1, "reading": "판매가 늘고 있음"}
    print("자체 점검 통과")


# ---------------------------------------------------------------- main

def pop_opts(args, flag):
    """args에서 `flag 값` 쌍을 모두 꺼내 값 목록으로 돌려준다."""
    values = []
    while flag in args:
        i = args.index(flag)
        values.append(args[i + 1])
        del args[i:i + 2]
    return values


def read_all(paths):
    texts = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            texts.append(f.read().strip())
    return "\n\n".join(texts)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], list(argv[1:])
    out = (pop_opts(args, "--out") or [None])[-1]

    def emit(text):  # 셸의 > 는 윈도우에서 글자가 깨질 수 있어 파일 저장을 직접 한다
        if out:
            with open(out, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"저장: {out}")
        else:
            print(text, end="")

    def dump(obj):
        emit(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")

    if cmd == "--selftest":
        selftest()
    elif cmd == "estimate":
        dump(estimate(load_profile(args[0])))
    elif cmd == "forces":
        with open(args[0], encoding="utf-8") as f:
            dump(forces(json.load(f)))
    elif cmd == "cscore":
        score, label = cscore([float(x) for x in args])
        dump({"score": round(score, 2), "label": label})
    elif cmd == "check":
        result = check(load_items(args[1:]), load_profile(args[0]))
        dump(result)
        return 0 if result["ok"] else 1
    elif cmd == "render":
        head, tail = read_all(pop_opts(args, "--head")), read_all(pop_opts(args, "--tail"))
        emit(render(load_items(args[1:]), load_profile(args[0]), head, tail))
    elif cmd == "flow":
        dump(flow([float(x) for x in args]))
    elif cmd == "words":
        parens_ok = "--parens-ok" in args
        path = next(a for a in args if not a.startswith("--"))
        with open(path, encoding="utf-8") as f:
            hits = find_banned(f.read(), load_banned(), parens_ok)
        dump({"ok": not hits, "hits": hits})
        return 0 if not hits else 1
    else:
        print(f"모르는 명령: {cmd}\n{__doc__}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
