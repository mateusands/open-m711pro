"""System integration tests — udev rule and menu entry, never the mouse.

`open-m711pro setup` exists for the people who install from a release or with
pip: neither the wheel nor the sdist carried `packaging/`, so the release notes
told them to run a script they did not have, and without the udev rule the
mouse is unreachable. The files now ship inside the package and these tests
prove they are there and that setup puts them in the right places.

Nothing here runs sudo or writes outside a temporary directory: the command
runner is injected and the target paths are parameters.
"""
import os
import shlex
import tempfile

from m711pro import system


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- The files ship inside the package --------------------------------------
def test_the_udev_rule_ships_inside_the_package():
    rule = system.udev_rule()
    assert 'ATTRS{idProduct}=="fa07"' in rule
    assert 'ATTRS{idProduct}=="fa08"' in rule
    assert 'TAG+="uaccess"' in rule


def test_pyproject_declares_the_data_files():
    # without this the wheel silently drops them, which is the original bug
    with open(os.path.join(REPO, "pyproject.toml")) as handle:
        pyproject = handle.read()
    assert "*.rules" in pyproject and "*.desktop" in pyproject


def test_install_sh_reads_the_same_files():
    # one source of truth: the checkout installer must not carry its own copy
    with open(os.path.join(REPO, "packaging", "install.sh")) as handle:
        script = handle.read()
    assert "m711pro/data" in script
    assert not os.path.exists(os.path.join(REPO, "packaging", "99-m711pro.rules"))


# --- The menu entry runs something that exists ------------------------------
def test_the_launcher_prefers_the_installed_gui_command():
    found = system.launcher(which=lambda name: "/home/u/.local/bin/" + name)
    assert found == ["/home/u/.local/bin/open-m711pro-gui"]


def test_the_launcher_falls_back_to_the_checkout():
    # the README's per-distribution steps clone and never run pip, so the
    # installed command does not exist; the entry must run main.py instead
    found = system.launcher(which=lambda name: None)
    assert found[-1] == os.path.join(REPO, "main.py")
    assert os.path.isabs(found[0])                # the interpreter, absolute


def test_the_desktop_entry_quotes_a_path_with_spaces():
    entry = system.desktop_entry(["/usr/bin/python3", "/home/u/my repos/main.py"])
    exec_line = [l for l in entry.splitlines() if l.startswith("Exec=")]
    assert exec_line == ['Exec=/usr/bin/python3 "/home/u/my repos/main.py"']
    assert "TryExec" not in entry


def test_install_desktop_entry_writes_to_the_user_data_dir():
    with tempfile.TemporaryDirectory() as tmp:
        path = system.install_desktop_entry(["/bin/gui"], data_home=tmp)
        assert path == os.path.join(tmp, "applications", "open-m711pro.desktop")
        with open(path) as handle:
            assert "Exec=/bin/gui" in handle.read()


# --- The udev rule: the only step that needs root ---------------------------
def test_udev_commands_use_sudo_when_not_root():
    commands = system.udev_install_commands("/tmp/rule", is_root=False)
    assert all(cmd[0] == "sudo" for cmd in commands)
    install = commands[0]
    assert install[-2:] == ["/tmp/rule", "/etc/udev/rules.d/99-m711pro.rules"]


def test_udev_commands_skip_sudo_as_root():
    commands = system.udev_install_commands("/tmp/rule", is_root=True)
    assert all(cmd[0] != "sudo" for cmd in commands)


def test_udev_commands_reload_and_trigger_only_hidraw():
    flat = [shlex.join(cmd) for cmd in
            system.udev_install_commands("/tmp/rule", is_root=True)]
    assert any("udevadm control --reload-rules" in c for c in flat)
    assert any("udevadm trigger --subsystem-match=hidraw" in c for c in flat)


def test_setup_runs_the_udev_steps_and_writes_the_entry():
    ran = []
    with tempfile.TemporaryDirectory() as tmp:
        system.setup(run=ran.append, data_home=tmp, is_root=False,
                     which=lambda name: "/bin/" + name, say=lambda *_: None,
                     legacy_path=os.path.join(tmp, "none.rules"))
        assert os.path.exists(os.path.join(tmp, "applications",
                                           "open-m711pro.desktop"))
    assert len(ran) == 3 and ran[0][0] == "sudo"


def test_uninstall_removes_both():
    ran = []
    with tempfile.TemporaryDirectory() as tmp:
        system.install_desktop_entry(["/bin/gui"], data_home=tmp)
        system.uninstall(run=ran.append, data_home=tmp, is_root=False,
                         say=lambda *_: None)
        assert not os.path.exists(os.path.join(tmp, "applications",
                                               "open-m711pro.desktop"))
    assert ran[0] == ["sudo", "rm", "-f", "/etc/udev/rules.d/99-m711pro.rules"]


def test_setup_refuses_to_run_under_sudo():
    # `sudo open-m711pro setup` would write the menu entry into root's home
    os.environ["SUDO_USER"] = "someone"
    try:
        try:
            system.setup(run=lambda cmd: None, is_root=True,
                         which=lambda name: None, say=lambda *_: None)
        except system.RunAsUser:
            pass
        else:
            raise AssertionError("setup under sudo must refuse")
    finally:
        del os.environ["SUDO_USER"]


def test_the_launcher_finds_the_gui_command_next_to_the_interpreter():
    # pipx/venv installs put it beside sys.executable, often off the PATH
    import sys
    beside = os.path.join(os.path.dirname(sys.executable), "open-m711pro-gui")
    found = system.launcher(which=lambda name: None,
                            exists=lambda path: path == beside)
    assert found == [beside]


# --- The legacy rule from the first README -----------------------------------
# v0 of the README told people to create 99-redragon-m711.rules with MODE 0666.
# Its file name differs from ours, so installing the new uaccess rule alone
# leaves the world-writable one active. Setup removes it — but only when it is
# byte-for-byte the line we told people to write.
def _legacy(tmp, content):
    path = os.path.join(tmp, "99-redragon-m711.rules")
    with open(path, "w") as handle:
        handle.write(content)
    return path


def test_the_legacy_rule_we_wrote_is_recognised():
    with tempfile.TemporaryDirectory() as tmp:
        assert system.legacy_rule(_legacy(tmp, system.LEGACY_LINE + "\n")) == "ours"
        assert system.legacy_rule(_legacy(tmp, "# edited\n" + system.LEGACY_LINE)) \
            == "modified"
        assert system.legacy_rule(os.path.join(tmp, "absent.rules")) is None


def test_setup_removes_our_legacy_rule_before_reloading():
    ran = []
    with tempfile.TemporaryDirectory() as tmp:
        legacy = _legacy(tmp, system.LEGACY_LINE + "\n")
        system.setup(run=ran.append, data_home=tmp, is_root=False,
                     which=lambda name: "/bin/" + name, say=lambda *_: None,
                     legacy_path=legacy)
    assert ["sudo", "rm", "-f", legacy] in ran
    assert ran.index(["sudo", "rm", "-f", legacy]) < \
        ran.index(["sudo", "udevadm", "control", "--reload-rules"])


def test_setup_leaves_an_edited_legacy_rule_alone_and_says_so():
    ran, said = [], []
    with tempfile.TemporaryDirectory() as tmp:
        legacy = _legacy(tmp, "# my own tweaks\n" + system.LEGACY_LINE + "\n")
        system.setup(run=ran.append, data_home=tmp, is_root=False,
                     which=lambda name: "/bin/" + name, say=said.append,
                     legacy_path=legacy)
    assert not any(cmd[-1] == legacy for cmd in ran)
    assert any(legacy in line and "0666" in line for line in said)


def test_install_sh_handles_the_legacy_rule_too():
    with open(os.path.join(REPO, "packaging", "install.sh")) as handle:
        script = handle.read()
    assert "99-redragon-m711.rules" in script
    assert system.LEGACY_LINE in script
