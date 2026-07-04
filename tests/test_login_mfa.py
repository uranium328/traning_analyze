"""
tests/test_login_mfa.py — login_setup._resolve_mfa_code 行為驗證

重點：密碼錯誤時 garminconnect 的 widget 登入會誤觸 MFA 提示；本函式讓使用者
留空 Enter 即乾淨中止（raise MfaAborted），而非送出假驗證碼。input 以假函式注入，
不需真登入或網路。
"""

import pytest

from login_setup import _resolve_mfa_code, MfaAborted


def test_empty_input_aborts_widget_flow():
    with pytest.raises(MfaAborted):
        _resolve_mfa_code("widget", input_fn=lambda _p: "")


def test_whitespace_only_aborts():
    with pytest.raises(MfaAborted):
        _resolve_mfa_code("ios", input_fn=lambda _p: "   ")


def test_returns_code_when_provided():
    assert _resolve_mfa_code("ios", input_fn=lambda _p: "123456") == "123456"


def test_strips_surrounding_whitespace():
    assert _resolve_mfa_code("widget", input_fn=lambda _p: " 654321 ") == "654321"


def test_none_flow_still_supports_abort_and_code():
    # 未知/None 流程也適用留空中止與正常回碼
    with pytest.raises(MfaAborted):
        _resolve_mfa_code(None, input_fn=lambda _p: "")
    assert _resolve_mfa_code(None, input_fn=lambda _p: "000000") == "000000"
