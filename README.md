# NeuroChess

NeuroChess is a local desktop chess project for exploring how search and a
learned position evaluation work together. The interface is in German.
python-chess handles legal moves and board rules. The opponent search and
adaptive evaluation are implemented in this project.

## Features

| Opponent | Board | Behavior |
| --- | --- | --- |
| Amateur | Classic Green | Bounded one- and two-ply search with controlled variation. |
| Großmeister | Premium Wood | Iterative deepening, alpha–beta search, a fixed evaluation, and bounded quiescence. The mode name carries no verified Elo rating. |
| Adaptive Grandmaster AI | Cyber Blue | The same search framework with five weights that TD(0) can update. |

Play with either color, or use the separate two-player rules test. Rapid 15+10,
SAN move history, captured pieces, save and resume, player statistics, and
adaptive learning reports are available locally. Board previews are visual demos.

## Install and run

Validated with Python 3.11.0 on macOS 15.7.3 (Apple Silicon). The stack includes
PySide6 6.10.2, python-chess 1.999 (chess 1.11.2), the standard-library SQLite
binding, and pytest 9.2.0. Run these commands from the project directory.

```bash
# Create the virtual environment only on a fresh checkout.
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python main.py
```

In PyCharm, select the existing project folder and `.venv/bin/python`.
Run `main.py` with the project folder as the working directory. The verified
lock file targets the tested macOS setup. SQLite requires no extra package.

## Play and save

Choose **Neues Spiel**, an opponent, and a color. Click a piece and its target,
or drag it. Touch-move applies in real games. Select the promotion piece when
prompted. Each side starts with 15 minutes and receives ten seconds per
completed move. A claimable draw can be requested with **Remis beantragen**.
Use **Speichern & verlassen** and **Spiel fortsetzen**. One unfinished game is
resumable at a time. **Statistiken** separates human results from automated
tests. On macOS, use the window's full-screen control or Control–Command–F.

## Learning, training and evaluation

The adaptive evaluator learns five weights for piece activity, center control,
king safety, pawn structure, and endgame strategy. Training can start manually
in **KI-Testzentrum → KI-Training · 600 Partien**. One worker runs 200 games
against each opponent, equally split by color. The Adaptive training opponent
is a frozen snapshot. The trainee's weights and completed games are
checkpointed. A complete training run creates a candidate.

Evaluation is a separate, manually started **400-game** process with 200 games
per model, paired conditions, and frozen weights. Technical endings are reported
separately and excluded from normal score rates. The paired report shows
uncertainty and bounds for unresolved outcomes. Select a completed run and
**Auswahl erneut testen** to repeat it under the current method. A qualifying
candidate still requires manual confirmation before it can become the reference.

A higher short-test score or a changed weight is insufficient evidence of
stronger play. The bounded protocol emphasizes endgames and does not measure
Rapid playing strength. General dead-position recognition is limited to the
available material checks. The app is designed and tested for local macOS use.

## Storage and layout

The app creates `database/neurochess.sqlite3` locally as needed. Game records and
clocks, immutable model revisions and learning events, training checkpoints,
and review results occupy separate tables. Save transactions keep move and
learning updates consistent. Keep local databases and exported games private.

| Path | Responsibility |
| --- | --- |
| `main.py`, `ui/` | Entry point, PySide6 pages, worker lifecycle |
| `game/` | Rules, clocks, checkpoints |
| `ai/`, `learning/` | Search, evaluation, TD(0) and model revisions |
| `database/`, `evaluation/` | SQLite persistence, training, paired review and statistics |
| `assets/`, `tests/`, `docs/` | Vector resources, tests and documentation |

## Test and reproduce

```bash
mkdir -p .venv/.tmp
.venv/bin/python -B -m pytest -q
.venv/bin/python -B tests/gui_smoke_phase10.py
.venv/bin/python -B tests/training_full_probe.py
.venv/bin/python -B tests/review_quality_probe.py
```

pytest uses offscreen Qt. The native smoke test needs a macOS desktop. The
full probes use isolated SQLite files and synthetic starting weights by default.
They print the measured results. The native smoke test uses the actual entry
point with an isolated database.

[CRISP-DM documentation (German)](docs/CRISP_DM_DE.md) ·
[User guide (German)](docs/BEDIENUNGSANLEITUNG_DE.md) ·
[Publication preparation (German)](docs/VEROEFFENTLICHUNG_DE.md)
