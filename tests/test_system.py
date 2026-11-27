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
                     which=lambda name: "/bin/" + name, say=lambda *_: None)
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
