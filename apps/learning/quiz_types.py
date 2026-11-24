"""퀴즈 문항 유형(Canvas 7가지 + 예전 단답형).

- clean_config: 강사가 만든 정답 구성을 검사해 저장 형태로 바꿉니다. 보기형(객관식·복수 응답·참/거짓)은 QuizChoice 목록을 따로 돌려줍니다.
- read_response: 학생이 보낸 양식에서 유형별 답안을 읽습니다(모르는 값은 버림).
- grade: 자동 채점. 복수 응답은 틀리게 고른 만큼 빼고, 빈칸·순서·짝·범주화는 맞은 부분의 비율만큼 점수를 줍니다.
- prepare: 학생 화면용 자료(순서는 항상 섞고, 짝 보기·범주 항목·단어 은행도 섞음).
- review / answer_text: 결과 화면의 '학생 답 · 정답' 줄과 첨삭용 한 줄 요약.
"""
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import re

from django.core.exceptions import ValidationError

CATEGORY, MCQ, MULTI, FILL, ORDER, MATCH, TF, SHORT = "CATEGORY", "MCQ", "MULTI", "FILL", "ORDER", "MATCH", "TF", "SHORT"
CHOICE_TYPES = (MCQ, MULTI, TF)
# 문항 만들기 화면의 유형 카드: (아이콘, 한 줄 설명). 아이콘은 templates/components/icon_sprite.html
TYPE_INFO = {
    CATEGORY: ("grid", "항목을 알맞은 범주로 끌어 넣기"),
    MCQ: ("radio", "보기 중 하나만 고르기"),
    MULTI: ("check-square", "정답 보기를 모두 고르기"),
    FILL: ("blank", "문장 속 빈칸 채우기"),
    ORDER: ("sort", "항목을 순서대로 놓기"),
    MATCH: ("link", "왼쪽과 오른쪽 짝 연결하기"),
    TF: ("toggle", "참인지 거짓인지 고르기"),
    SHORT: ("pen", "짧은 답 직접 쓰기"),
}
BLANK = re.compile(r"`([^`\n]+)`")
BLANK_MODES = {"text": "직접 입력", "dropdown": "드롭다운", "bank": "단어 은행"}
UNSORTED = "분류 안 함"
NO_ANSWER = "(미응답)"
PICKED = "고름"
MAX_ROWS = 40
TEXT_LIMIT = 300
_ID = re.compile(r"^[a-z]\d{1,4}$")


def _text(value):
    return str(value).strip()[:TEXT_LIMIT] if isinstance(value, (str, int, float)) else ""


def _texts(values):
    """빈 줄과 중복을 뺀 글자 목록(입력 순서 유지)."""
    seen, result = set(), []
    for value in values if isinstance(values, list) else []:
        text = _text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result[:MAX_ROWS]


def _rows(values):
    return [row for row in values if isinstance(row, dict)][:MAX_ROWS] if isinstance(values, list) else []


def _with_ids(rows, prefix):
    """편집기가 보낸 id(o1, m3 같은 꼴)는 그대로 두고, 없거나 겹치면 새 id를 붙입니다. 답안이 id로 항목을 가리킵니다."""
    used = set()
    for row in rows:
        ident = row.get("id")
        row["id"] = ident if isinstance(ident, str) and _ID.match(ident) and ident[0] == prefix and ident not in used else None
        if row["id"]:
            used.add(row["id"])
    number = 1
    for row in rows:
        while not row["id"]:
            candidate = f"{prefix}{number}"
            number += 1
            if candidate not in used:
                row["id"] = candidate
                used.add(candidate)
    return rows


def blank_answers(prompt):
    """문장의 `정답|다른 정답` 표시마다 정답 목록."""
    return [_texts(part.split("|")) for part in BLANK.findall(prompt or "")]


def display_prompt(question):
    """빈칸 채우기 문장은 정답이 보이지 않게 빈칸으로 바꿔 보여 줍니다."""
    if question.question_type == FILL:
        return BLANK.sub("[ 빈칸 ]", question.prompt)
    return question.prompt


def clean_config(question_type, data, prompt):
    """(저장할 config, 보기 목록) 을 돌려줍니다. 잘못되면 강사에게 보여 줄 문구로 ValidationError."""
    data = data if isinstance(data, dict) else {}
    if question_type in (MCQ, MULTI):
        rows = [{"text": _text(row.get("text")), "is_correct": row.get("correct") is True} for row in _rows(data.get("choices"))]
        rows = [row for row in rows if row["text"]]
        if len(rows) < 2:
            raise ValidationError("보기를 두 개 이상 입력해 주세요.")
        right = sum(row["is_correct"] for row in rows)
        if question_type == MCQ and right != 1:
            raise ValidationError("객관식은 정답 보기를 하나만 고르세요.")
        if question_type == MULTI and right < 1:
            raise ValidationError("복수 응답은 정답 보기를 하나 이상 고르세요.")
        return {}, rows
    if question_type == TF:
        answer = data.get("answer")
        if not isinstance(answer, bool):
            raise ValidationError("참/거짓 중 정답을 고르세요.")
        return {}, [{"text": "참", "is_correct": answer}, {"text": "거짓", "is_correct": not answer}]
    if question_type == FILL:
        answers = [alts for alts in blank_answers(prompt) if alts]
        if not answers:
            raise ValidationError("문장에 `정답`처럼 백틱(`)으로 빈칸을 하나 이상 표시하세요.")
        settings = _rows(data.get("blanks"))
        blanks = []
        for index, alts in enumerate(answers):
            setting = settings[index] if index < len(settings) else {}
            mode = setting.get("mode") if setting.get("mode") in BLANK_MODES else "text"
            options = [o for o in _texts(setting.get("options")) if o not in alts] if mode == "dropdown" else []
            if mode == "dropdown" and not options:
                raise ValidationError(f"{index + 1}번 빈칸: 드롭다운에 정답 말고 다른 보기를 하나 이상 넣으세요.")
            blanks.append({"mode": mode, "answers": alts, "options": options})
        bank_answers = {blank["answers"][0] for blank in blanks if blank["mode"] == "bank"}
        return {"blanks": blanks, "bank": [word for word in _texts(data.get("bank")) if word not in bank_answers]}, []
    if question_type == ORDER:
        items = [{"id": row.get("id"), "text": _text(row.get("text"))} for row in _rows(data.get("items"))]
        items = [item for item in items if item["text"]]
        if len(items) < 2:
            raise ValidationError("순서 맞추기는 항목을 두 개 이상 입력하세요.")
        return {"items": _with_ids(items, "o")}, []
    if question_type == MATCH:
        pairs = [{"id": row.get("id"), "left": _text(row.get("left")), "right": _text(row.get("right"))} for row in _rows(data.get("pairs"))]
        pairs = [pair for pair in pairs if pair["left"] and pair["right"]]
        if len(pairs) < 2:
            raise ValidationError("짝 맞추기는 짝을 두 개 이상 입력하세요.")
        rights = {pair["right"] for pair in pairs}
        return {"pairs": _with_ids(pairs, "m"), "distractors": [d for d in _texts(data.get("distractors")) if d not in rights]}, []
    if question_type == CATEGORY:
        raw = [row for row in _rows(data.get("categories")) if _text(row.get("name"))]
        if not raw:
            raise ValidationError("범주를 하나 이상 만드세요.")
        categories = _with_ids([{"id": row.get("id"), "name": _text(row.get("name"))} for row in raw], "c")
        items = []
        for category, row in zip(categories, raw):
            texts = _texts([item.get("text") if isinstance(item, dict) else item for item in row.get("items", [])])
            if not texts:
                raise ValidationError(f"'{category['name']}' 범주에 항목을 하나 이상 넣으세요.")
            items += [{"id": None, "text": text, "category": category["id"]} for text in texts]
        items += [{"id": None, "text": text, "category": ""} for text in _texts(data.get("distractors"))]
        seen = set()
        for item in items:
            if item["text"] in seen:
                raise ValidationError(f"'{item['text']}' 항목이 두 번 들어 있습니다. 한 범주에만 넣어 주세요.")
            seen.add(item["text"])
        return {"categories": categories, "items": _with_ids(items, "k")}, []
    return {}, []


def editor_data(question):
    """저장된 문항 → 편집기(quiz-editor.js)가 다루는 꼴. clean_config 에 다시 넣으면 같은 config 가 나옵니다."""
    kind, config = question.question_type, question.config or {}
    if kind in (MCQ, MULTI):
        return {"choices": [{"text": c.text, "correct": c.is_correct} for c in question.choices.all()]}
    if kind == TF:
        correct = next((c for c in question.choices.all() if c.is_correct), None)
        return {"answer": correct.text == "참"} if correct else {}
    if kind == FILL:
        return {"blanks": [{"mode": b["mode"], "options": list(b["options"])} for b in config.get("blanks", [])],
                "bank": list(config.get("bank", []))}
    if kind == ORDER:
        return {"items": [dict(item) for item in config.get("items", [])]}
    if kind == MATCH:
        return {"pairs": [dict(pair) for pair in config.get("pairs", [])], "distractors": list(config.get("distractors", []))}
    if kind == CATEGORY:
        items = config.get("items", [])
        return {"categories": [{"id": c["id"], "name": c["name"], "items": [i["text"] for i in items if i["category"] == c["id"]]}
                               for c in config.get("categories", [])],
                "distractors": [i["text"] for i in items if not i["category"]]}
    return {}


def read_response(question, data):
    """학생 양식(QueryDict) → 유형별 답안. 문항에 없는 보기·항목·범주 값은 버립니다."""
    name, kind, config = f"question_{question.pk}", question.question_type, question.config or {}
    if kind in (MCQ, TF):
        raw = data.get(name, "")
        return {"choice": int(raw)} if raw.isdigit() else {}
    if kind == MULTI:
        return {"choices": sorted({int(value) for value in data.getlist(name) if value.isdigit()})}
    if kind == FILL:
        return {"blanks": [data.get(f"{name}_blank_{i}", "").strip()[:TEXT_LIMIT] for i in range(len(config.get("blanks", [])))]}
    if kind == ORDER:
        known, order = {item["id"] for item in config.get("items", [])}, []
        for value in data.getlist(f"{name}_order"):
            if value in known and value not in order:
                order.append(value)
        return {"order": order}
    if kind == MATCH:
        options = {pair["right"] for pair in config.get("pairs", [])} | set(config.get("distractors", []))
        chosen = {pair["id"]: data.get(f"{name}_match_{pair['id']}", "") for pair in config.get("pairs", [])}
        return {"pairs": {key: value for key, value in chosen.items() if value in options}}
    if kind == CATEGORY:
        categories = {category["id"] for category in config.get("categories", [])}
        placed = {item["id"]: data.get(f"{name}_cat_{item['id']}", "") for item in config.get("items", [])}
        return {"placed": {key: value for key, value in placed.items() if value in categories}}
    return {"text": data.get(name, "").strip()[:500]}


def response_for(answer):
    """저장된 답안. 이 기능 전에 저장된 객관식·단답형 답안은 selected_choice·text_answer 로 만듭니다."""
    if answer.response:
        return answer.response
    if answer.selected_choice_id:
        return {"choice": answer.selected_choice_id}
    return {"text": answer.text_answer}


TF_ENGLISH = {"참": "True", "거짓": "False"}


def tf_label(text):
    """참/거짓 보기 옆에 영어를 붙여 보여 줍니다(저장 값은 '참'·'거짓' 그대로)."""
    english = TF_ENGLISH.get(text)
    return f"{text} ({english})" if english else text


def _same(given, answers):
    return bool(given) and given.strip().casefold() in {a.strip().casefold() for a in answers}


def _parts(question, response):
    """(라벨, 학생 답, 정답, 맞음 여부) 목록. 채점과 결과 화면이 같은 기준을 씁니다."""
    kind, config = question.question_type, question.config or {}
    if kind in CHOICE_TYPES:
        choices = list(question.choices.all())
        if kind == MULTI:
            picked = set(response.get("choices", []))
            return [(c.text, PICKED if c.pk in picked else "안 고름", "골라야 함" if c.is_correct else "고르면 안 됨", (c.pk in picked) == c.is_correct)
                    for c in choices]
        chosen = next((c for c in choices if c.pk == response.get("choice")), None)
        correct = next((c for c in choices if c.is_correct), None)
        show = tf_label if kind == TF else str
        return [("선택", show(chosen.text) if chosen else NO_ANSWER, show(correct.text) if correct else "", bool(chosen and chosen.is_correct))]
    if kind == FILL:
        given = response.get("blanks", [])
        return [(f"빈칸 {i + 1}", (given[i] if i < len(given) else "") or NO_ANSWER, " / ".join(blank["answers"]),
                 _same(given[i] if i < len(given) else "", blank["answers"]))
                for i, blank in enumerate(config.get("blanks", []))]
    if kind == ORDER:
        items = config.get("items", [])
        texts, order = {item["id"]: item["text"] for item in items}, response.get("order", [])
        return [(f"{i + 1}번째", texts.get(order[i], NO_ANSWER) if i < len(order) else NO_ANSWER, item["text"],
                 i < len(order) and order[i] == item["id"]) for i, item in enumerate(items)]
    if kind == MATCH:
        chosen = response.get("pairs", {})
        return [(pair["left"], chosen.get(pair["id"]) or NO_ANSWER, pair["right"], chosen.get(pair["id"]) == pair["right"])
                for pair in config.get("pairs", [])]
    if kind == CATEGORY:
        names = {category["id"]: category["name"] for category in config.get("categories", [])}
        placed = response.get("placed", {})
        return [(item["text"], names.get(placed.get(item["id"], ""), UNSORTED), names.get(item["category"], UNSORTED),
                 placed.get(item["id"], "") == item["category"]) for item in config.get("items", [])]
    given = response.get("text", "")
    return [("답", given or NO_ANSWER, question.correct_text, _same(given, [question.correct_text]) if question.correct_text.strip() else False)]


def grade(question, response):
    parts = _parts(question, response)
    if not parts:
        return Decimal("0.00")
    if question.question_type == MULTI:
        choices = list(question.choices.all())
        picked = set(response.get("choices", [])) & {c.pk for c in choices}
        correct = {c.pk for c in choices if c.is_correct}
        share = Fraction(max(0, len(picked & correct) - len(picked - correct)), len(correct) or 1)
    else:
        share = Fraction(sum(1 for part in parts if part[3]), len(parts))
    earned = Decimal(question.points) * Decimal(share.numerator) / Decimal(share.denominator)
    return earned.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def review(question, response):
    return [{"label": label, "given": given, "expected": expected, "ok": ok} for label, given, expected, ok in _parts(question, response)]


def answer_text(question, response):
    parts = _parts(question, response)
    if question.question_type in (MCQ, TF, SHORT):
        return parts[0][1] if parts else NO_ANSWER
    if question.question_type == MULTI:
        picked = [label for label, given, _, _ in parts if given == PICKED]
        return ", ".join(picked) or NO_ANSWER
    return " · ".join(f"{label}: {given}" for label, given, _, _ in parts)


def prepare(question, rng):
    """학생 화면용. rng 는 random.Random (테스트에서 고정)."""
    kind, config = question.question_type, question.config or {}
    if kind in CHOICE_TYPES:
        return {"choices": list(question.choices.all())}
    if kind == FILL:
        blanks = config.get("blanks", [])
        bank = [blank["answers"][0] for blank in blanks if blank["mode"] == "bank"] + list(config.get("bank", []))
        rng.shuffle(bank)
        segments, index = [], 0
        for position, part in enumerate(BLANK.split(question.prompt)):
            if position % 2 == 0:
                if part:
                    segments.append({"kind": "text", "text": part})
                continue
            if index >= len(blanks):
                segments.append({"kind": "text", "text": part})
                continue
            blank = blanks[index]
            options = [blank["answers"][0], *blank["options"]] if blank["mode"] == "dropdown" else list(bank) if blank["mode"] == "bank" else []
            if blank["mode"] == "dropdown":
                rng.shuffle(options)
            segments.append({"kind": "blank", "blank": index, "mode": blank["mode"], "options": options, "name": f"question_{question.pk}_blank_{index}"})
            index += 1
        return {"segments": segments, "bank": bank}
    if kind == ORDER:
        items = list(config.get("items", []))
        correct = [item["id"] for item in items]
        rng.shuffle(items)
        if len(items) > 1 and [item["id"] for item in items] == correct:
            items = items[1:] + items[:1]
        return {"items": items, "name": f"question_{question.pk}_order"}
    if kind == MATCH:
        options = _texts([pair["right"] for pair in config.get("pairs", [])] + list(config.get("distractors", [])))
        rng.shuffle(options)
        return {"lefts": [{**pair, "name": f"question_{question.pk}_match_{pair['id']}"} for pair in config.get("pairs", [])], "options": options}
    if kind == CATEGORY:
        items = [{**item, "name": f"question_{question.pk}_cat_{item['id']}"} for item in config.get("items", [])]
        rng.shuffle(items)
        return {"categories": config.get("categories", []), "items": items}
    return {}
