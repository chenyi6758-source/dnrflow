"""CLI: exit codes and output."""

from dnrflow.cli import main


def test_cli_case33(capsys):
    assert main(["case33"]) == 0
    out = capsys.readouterr().out
    assert "139.55" in out
    assert "202.68" in out


def test_cli_unknown_case(capsys):
    assert main(["case999"]) == 2
    assert "unknown case" in capsys.readouterr().err


def test_cli_levels(capsys):
    assert main(["case33", "--levels"]) == 0
    out = capsys.readouterr().out
    assert "peak" in out and "mid" in out and "valley" in out


def test_cli_milp_case16(capsys):
    assert main(["case16", "--solver", "milp"]) == 0
    assert "468.33" in capsys.readouterr().out


def test_cli_json(tmp_path, capsys):
    target = tmp_path / "res.json"
    assert main(["case33", "--json", str(target)]) == 0
    assert target.exists()
    assert '"final_loss_kw": 139.5' in target.read_text()
