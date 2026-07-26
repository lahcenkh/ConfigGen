from pathlib import Path

from configgen.core.preflight import (
    BUILTIN_CHECKS,
    check_generic,
    check_ios,
    check_junos,
    check_sros,
    check_vrp,
    get_check,
    load_custom_check,
    run_preflight,
)

# -- check_ios ---------------------------------------------------------


def test_check_ios_clean_config_has_no_warnings():
    text = "interface GigabitEthernet0/0\n no shutdown\nvlan 10\nend\n"
    assert check_ios(text) == []


def test_check_ios_missing_end_warns():
    text = "interface GigabitEthernet0/0\n no shutdown\n"
    warnings = check_ios(text)
    assert any("no closing 'end'" in w for w in warnings)


def test_check_ios_no_interface_no_end_required():
    text = "hostname foo\nntp server 1.2.3.4\n"
    assert check_ios(text) == []


def test_check_ios_invalid_interface_name_warns():
    text = "interface bad!name\n no shutdown\nend\n"
    warnings = check_ios(text)
    assert any("bad!name" in w for w in warnings)


def test_check_ios_valid_interface_names_pass():
    for name in ("GigabitEthernet0/0", "Vlan10", "Loopback0", "TenGigE0/1/2"):
        text = f"interface {name}\n no shutdown\nend\n"
        assert check_ios(text) == [], f"{name} should be valid"


def test_check_ios_vlan_in_range_ok():
    text = "vlan 1\nvlan 4094\n"
    assert check_ios(text) == []


def test_check_ios_vlan_out_of_range_warns():
    text = "vlan 0\nvlan 4095\n"
    warnings = check_ios(text)
    assert any("VLAN 0" in w for w in warnings)
    assert any("VLAN 4095" in w for w in warnings)


# -- check_junos ---------------------------------------------------------


def test_check_junos_balanced_braces_ok():
    text = "system {\n  host-name foo;\n}\n"
    assert check_junos(text) == []


def test_check_junos_unbalanced_braces_warns():
    text = "system {\n  host-name foo;\n"
    warnings = check_junos(text)
    assert any("unbalanced braces" in w for w in warnings)


def test_check_junos_stray_closing_brace_warns():
    text = "system {\n}\n}\n"
    warnings = check_junos(text)
    assert any("no matching open brace" in w for w in warnings)


# -- check_generic ---------------------------------------------------------


def test_check_generic_clean_text_has_no_warnings():
    assert check_generic("hostname foo\nntp server 1.2.3.4\n") == []


def test_check_generic_unresolved_marker_warns():
    warnings = check_generic("hostname {{ hostname }}\n")
    assert any("unresolved template marker" in w for w in warnings)


def test_check_generic_consecutive_blank_lines_warn():
    text = "hostname foo\n\n\nntp server 1.2.3.4\n"
    warnings = check_generic(text)
    assert any("consecutive blank lines" in w for w in warnings)


def test_check_generic_single_blank_line_is_fine():
    text = "hostname foo\n\nntp server 1.2.3.4\n"
    assert check_generic(text) == []


# -- check_sros (Nokia SR OS) -----------------------------------------------


def test_check_sros_balanced_blocks_ok():
    text = 'router "Base"\n    interface "system"\n        address 10.0.0.1/32\n    exit\nexit\n'
    assert check_sros(text) == []


def test_check_sros_missing_exit_warns():
    text = 'router "Base"\n    interface "system"\n        address 10.0.0.1/32\n    exit\n'
    warnings = check_sros(text)
    assert any("but only 1 'exit'" in w for w in warnings)


def test_check_sros_exit_all_counts_too():
    text = "port 1/1/1\nexit all\n"
    assert check_sros(text) == []


def test_check_sros_no_blocks_no_exit_required():
    text = "# just a comment\n"
    assert check_sros(text) == []


# -- check_vrp (Huawei VRP8) -------------------------------------------------


def test_check_vrp_clean_config_has_no_warnings():
    text = "interface GigabitEthernet0/0/1\n undo shutdown\nquit\n"
    assert check_vrp(text) == []


def test_check_vrp_missing_quit_warns():
    text = "interface GigabitEthernet0/0/1\n undo shutdown\n"
    warnings = check_vrp(text)
    assert any("no closing 'quit'" in w for w in warnings)


def test_check_vrp_invalid_interface_name_warns():
    text = "interface bad!name\nquit\n"
    warnings = check_vrp(text)
    assert any("bad!name" in w for w in warnings)


def test_check_vrp_valid_interface_names_pass():
    for name in ("GigabitEthernet0/0/1", "Vlanif10", "Eth-Trunk1", "LoopBack0"):
        text = f"interface {name}\nquit\n"
        assert check_vrp(text) == [], f"{name} should be valid"


def test_check_vrp_vlan_out_of_range_warns():
    text = "vlan 4095\n"
    warnings = check_vrp(text)
    assert any("VLAN 4095" in w for w in warnings)


# -- registry / custom checks -----------------------------------------------


def test_builtin_checks_registered():
    assert set(BUILTIN_CHECKS) == {"ios", "junos", "sros", "vrp", "generic"}


def test_load_custom_check_missing_file_returns_none(tmp_path: Path):
    assert load_custom_check(tmp_path, "ios") is None


def test_load_custom_check_without_check_function_returns_none(tmp_path: Path):
    (tmp_path / "ios.py").write_text("x = 1\n", encoding="utf-8")
    assert load_custom_check(tmp_path, "ios") is None


def test_load_custom_check_returns_callable(tmp_path: Path):
    (tmp_path / "ios.py").write_text(
        "def check(text):\n    return ['custom warning'] if 'bad' in text else []\n",
        encoding="utf-8",
    )
    check_fn = load_custom_check(tmp_path, "ios")
    assert check_fn("this is bad") == ["custom warning"]
    assert check_fn("this is fine") == []


def test_get_check_falls_back_to_builtin_when_no_custom(tmp_path: Path):
    assert get_check("ios", tmp_path) is check_ios


def test_get_check_custom_overrides_builtin(tmp_path: Path):
    (tmp_path / "ios.py").write_text(
        "def check(text):\n    return ['always warns']\n", encoding="utf-8"
    )
    check_fn = get_check("ios", tmp_path)
    assert check_fn("anything") == ["always warns"]


def test_get_check_custom_can_add_a_new_platform(tmp_path: Path):
    (tmp_path / "eos.py").write_text("def check(text):\n    return []\n", encoding="utf-8")
    assert get_check("eos", tmp_path) is not None
    assert get_check("eos", None) is None  # not a builtin


def test_get_check_unknown_platform_without_custom_dir_returns_none():
    assert get_check("does-not-exist") is None


# -- run_preflight ---------------------------------------------------------


def test_run_preflight_dispatches_to_builtin():
    warnings = run_preflight("ios", "interface Gi0/0\nend\n")
    assert warnings == []


def test_run_preflight_unknown_platform_returns_explanatory_warning():
    warnings = run_preflight("does-not-exist", "anything")
    assert len(warnings) == 1
    assert "unknown preflight platform" in warnings[0]


def test_run_preflight_uses_custom_check_dir(tmp_path: Path):
    (tmp_path / "generic.py").write_text(
        "def check(text):\n    return ['from custom checker']\n", encoding="utf-8"
    )
    warnings = run_preflight("generic", "anything", tmp_path)
    assert warnings == ["from custom checker"]
