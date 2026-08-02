"""日誌的個資與作答內容過濾（FR-079、FR-080）。

保證由兩層構成：

1. **不去記錄**——靜態檢查確認程式碼沒有把應徵者欄位傳進 logger。
   姓名無法以形態辨識，因此這一層是姓名的唯一保證。
2. **過濾**——`PiiLogFilter` 攔截 Email 與電話形態，以及被封鎖的鍵名。
   這是最後一道防線，用來擋住日後新增的、未經審查的日誌呼叫。
"""

from __future__ import annotations

import logging
import pathlib
import re

import pytest

from backend.src.audit.logger import REDACTED, sanitize_detail, scrub_text
from backend.src.main import LOGGER_NAME, PiiLogFilter, configure_logging

SRC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src"

NAME = "王小明"
EMAIL = "ming@example.com"
PHONE = "0912-345-678"
ANSWER = "def solve():\n    return secret_value"


@pytest.fixture
def captured(caplog):
    configure_logging()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    return logger


def _formatted(caplog) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


def test_email_is_scrubbed_from_messages(captured, caplog):
    captured.info("寄送通知失敗，收件者為 %s", EMAIL)
    assert EMAIL not in _formatted(caplog)
    assert REDACTED in _formatted(caplog)


def test_phone_is_scrubbed_from_messages(captured, caplog):
    captured.info(f"聯絡電話 {PHONE} 無法接通")
    assert PHONE not in _formatted(caplog)


def test_blocked_extra_keys_are_redacted(captured, caplog):
    # 刻意不使用 "name"：logging 模組保留該屬性給 logger 名稱，
    # 應徵者姓名以 "candidate_name" 傳遞。
    captured.info(
        "處理考核",
        extra={"candidate_name": NAME, "email": EMAIL, "answer": ANSWER, "phone": PHONE},
    )
    record = caplog.records[-1]
    assert record.candidate_name == REDACTED
    assert record.email == REDACTED
    assert record.answer == REDACTED
    assert record.phone == REDACTED
    assert record.name == LOGGER_NAME, "logger 自身的名稱不得被遮蔽"


def test_dict_args_are_filtered(captured, caplog):
    captured.info("%(email)s 與 %(status)s", {"email": EMAIL, "status": "SENT"})
    assert EMAIL not in _formatted(caplog)
    assert "SENT" in _formatted(caplog)


def test_scrub_text_handles_multiple_occurrences():
    text = f"{EMAIL} 與 another@example.com 都寄不出去"
    scrubbed = scrub_text(text)
    assert "@example.com" not in scrubbed


def test_sanitize_detail_blocks_answer_and_pii():
    detail = sanitize_detail(
        {
            "name": NAME,
            "email": EMAIL,
            "phone": PHONE,
            "candidate_answer": ANSWER,
            "language": "python",
            "attempt_no": 2,
        }
    )
    assert detail["name"] == REDACTED
    assert detail["email"] == REDACTED
    assert detail["phone"] == REDACTED
    assert detail["candidate_answer"] == REDACTED
    # 非個資欄位必須保留，否則稽核紀錄會失去用途
    assert detail["language"] == "python"
    assert detail["attempt_no"] == 2


def test_sanitize_detail_is_recursive():
    detail = sanitize_detail({"outer": {"email": EMAIL, "note": f"請聯絡 {EMAIL}"}})
    assert detail["outer"]["email"] == REDACTED
    assert EMAIL not in detail["outer"]["note"]


def test_filter_is_installed_by_configure_logging():
    configure_logging()
    logger = logging.getLogger(LOGGER_NAME)
    assert any(isinstance(f, PiiLogFilter) for f in logger.filters)


# ── 第一層：不去記錄 ──────────────────────────────────────────────────

# 直接把應徵者欄位交給 logger 的呼叫形式
FORBIDDEN_LOG_PATTERNS = (
    re.compile(r"log(?:ger)?\.\w+\([^)]*\b(?:candidate_answer|\.answer)\b"),
    re.compile(r"log(?:ger)?\.\w+\([^)]*\brow\[[\"'](?:name|email|phone)[\"']\]"),
    re.compile(r"log(?:ger)?\.\w+\([^)]*\bassessment\[[\"'](?:name|email|phone)[\"']\]"),
    re.compile(r"print\("),
)


@pytest.mark.parametrize("pattern", FORBIDDEN_LOG_PATTERNS, ids=lambda p: p.pattern[:40])
def test_source_never_logs_personal_data(pattern):
    offenders = []
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(SRC_ROOT)))
    assert offenders == [], (
        "應徵者姓名、Email、電話與作答內容不得寫入應用程式日誌（FR-079、FR-080）："
        + "、".join(offenders)
    )
