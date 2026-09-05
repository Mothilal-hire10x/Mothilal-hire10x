#!/usr/bin/env python3
"""Community chess on the GitHub profile of @Mothilal-M.

Visitors open pre-filled issues titled ``chess|move|e2e4``; a GitHub Action
runs this script, which validates the move with python-chess, updates
``chess/state.json``, re-renders ``chess/board.svg``, regenerates the chess
section of ``README.md``, and writes ``chess/comment.md`` for the bot reply.

Usage:
    python chess/play.py bootstrap      # reset to a fresh game #1
    ISSUE_TITLE=... ISSUE_USER=... ISSUE_NUMBER=... python chess/play.py
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

import chess
import chess.svg

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OWNER = "Mothilal-M"
REPO = "Mothilal-M"
PROFILE_URL = f"https://github.com/{OWNER}"
REPO_URL = f"https://github.com/{OWNER}/{REPO}"
NEW_ISSUE_URL = f"{REPO_URL}/issues/new"
RAW_BOARD_URL = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/chess/board.svg"
KNIGHT_URL = "./assets/knight.svg"  # spinning 3D ASCII knight, sits beside the board

CHESS_DIR = Path(__file__).resolve().parent
STATE_FILE = CHESS_DIR / "state.json"
BOARD_FILE = CHESS_DIR / "board.svg"
GAMES_FILE = CHESS_DIR / "games.md"
COMMENT_FILE = CHESS_DIR / "comment.md"
README_FILE = CHESS_DIR.parent / "README.md"

MARKER_START = "<!--CHESS:START-->"
MARKER_END = "<!--CHESS:END-->"

BOARD_SIZE = 420

# Brand palette (mirrors the rest of the profile).
BOARD_COLORS = {
    "square light": "#EDE9DE",
    "square dark": "#6E685E",
    "square light lastmove": "#D6FF3FBB",
    "square dark lastmove": "#B8D935BB",
    "margin": "#0F0E0C",
    "coord": "#A39D92",
    "inner border": "#2B2722",
    "outer border": "#2B2722",
}

PIECE_GLYPHS = {
    (chess.PAWN, chess.WHITE): "♙", (chess.PAWN, chess.BLACK): "♟",
    (chess.KNIGHT, chess.WHITE): "♘", (chess.KNIGHT, chess.BLACK): "♞",
    (chess.BISHOP, chess.WHITE): "♗", (chess.BISHOP, chess.BLACK): "♝",
    (chess.ROOK, chess.WHITE): "♖", (chess.ROOK, chess.BLACK): "♜",
    (chess.QUEEN, chess.WHITE): "♕", (chess.QUEEN, chess.BLACK): "♛",
    (chess.KING, chess.WHITE): "♔", (chess.KING, chess.BLACK): "♚",
}
PIECE_ORDER = [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]

TITLE_RE = re.compile(r"^chess\|(new|move\|[a-h][1-8][a-h][1-8][qrbn]?)$")
SUMMARY_SAFE_RE = re.compile(r"[^A-Za-z0-9 :#@.+=-]")

TERMINATION_LABELS = {
    chess.Termination.CHECKMATE: "checkmate",
    chess.Termination.STALEMATE: "stalemate",
    chess.Termination.INSUFFICIENT_MATERIAL: "draw — insufficient material",
    chess.Termination.SEVENTYFIVE_MOVES: "draw — 75-move rule",
    chess.Termination.FIVEFOLD_REPETITION: "draw — fivefold repetition",
}


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def fresh_state(game_number: int) -> dict:
    return {
        "game_number": game_number,
        "fen": chess.STARTING_FEN,
        "moves": [],
        "created": datetime.date.today().isoformat(),
    }


def load_state() -> dict:
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def board_from_state(state: dict) -> chess.Board:
    """Replay all moves so repetition / move-count rules are detectable."""
    board = chess.Board()
    for record in state["moves"]:
        board.push_uci(record["uci"])
    return board


# ---------------------------------------------------------------------------
# GitHub Action outputs
# ---------------------------------------------------------------------------

def set_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return  # local run — nothing to do
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{key}={value}\n")


def sanitize_summary(text: str) -> str:
    return SUMMARY_SAFE_RE.sub("", text)


# ---------------------------------------------------------------------------
# Rendering — board SVG
# ---------------------------------------------------------------------------

def render_board(board: chess.Board) -> None:
    lastmove = board.peek() if board.move_stack else None
    svg = chess.svg.board(
        board,
        lastmove=lastmove,
        size=BOARD_SIZE,
        coordinates=True,
        borders=True,
        colors=BOARD_COLORS,
    )
    BOARD_FILE.write_text(svg, encoding="utf-8")


# ---------------------------------------------------------------------------
# Rendering — README section
# ---------------------------------------------------------------------------

def move_issue_url(uci: str, san: str) -> str:
    title = urllib.parse.quote(f"chess|move|{uci}", safe="")
    body = urllib.parse.quote(
        "Just press 'Submit new issue' — you don't need to write anything. "
        f"The bot will play **{san}**, update the board on my profile, and "
        "credit you. (Please don't edit the title.)",
        safe="",
    )
    return f"{NEW_ISSUE_URL}?title={title}&body={body}"


def legal_move_lines(board: chess.Board) -> str:
    """All legal moves as issue links, grouped by piece type."""
    groups: dict[int, list[str]] = {pt: [] for pt in PIECE_ORDER}
    for move in board.legal_moves:
        if move.promotion not in (None, chess.QUEEN):
            continue  # only offer queen promotions to keep the list compact
        piece = board.piece_at(move.from_square)
        san = board.san(move)
        groups[piece.piece_type].append((san, move.uci()))

    parts = []
    for piece_type in PIECE_ORDER:
        moves = sorted(groups[piece_type])
        if not moves:
            continue
        glyph = PIECE_GLYPHS[(piece_type, board.turn)]
        links = " ".join(f"[{san}]({move_issue_url(uci, san)})" for san, uci in moves)
        parts.append(f"**{glyph}** {links}")
    return " · ".join(parts)


def recent_moves_table(state: dict) -> str:
    moves = state["moves"]
    if not moves:
        return f"No moves yet — make the first move in game #{state['game_number']}!"
    rows = ["| # | move | played by |", "|---|------|-----------|"]
    for record in moves[-5:][::-1]:
        user = record["player"]
        rows.append(f"| {record['n']} | {record['san']} | [@{user}](https://github.com/{user}) |")
    return "\n".join(rows)


def status_line(state: dict, board: chess.Board) -> str:
    game_no = state["game_number"]
    move_no = board.fullmove_number
    if board.is_game_over():
        outcome = board.outcome()
        label = TERMINATION_LABELS.get(outcome.termination, "game over")
        return f"game #{game_no} · finished · {outcome.result()} ({label})"
    turn = "♙ white" if board.turn == chess.WHITE else "♟ black"
    return f"game #{game_no} · move {move_no} · {turn} to play"


def render_readme(state: dict, board: chess.Board, note: str | None = None) -> None:
    cache_bust = f"{state['game_number']}-{len(state['moves'])}"
    note_html = f"\n<sub>{note}</sub>\n<br>" if note else ""
    section = f"""{MARKER_START}
<div align="center">

<table>
<tr>
<td valign="middle"><img src="{KNIGHT_URL}" width="300" alt="spinning 3D ASCII chess knight"></td>
<td valign="middle"><img src="{RAW_BOARD_URL}?m={cache_bust}" width="{BOARD_SIZE}" alt="current board"></td>
</tr>
</table>

<sub>{status_line(state, board)}</sub>
{note_html}
</div>

**play a move** — click one, then just press <em>Submit new issue</em>; the bot does the rest:

{legal_move_lines(board) or '_The game is over — open an issue titled `chess|new` to start the next one._'}

**recent moves**

{recent_moves_table(state)}

<div align="center">
<sub><a href="chess/games.md">hall of fame</a> · powered by a GitHub Action + python-chess — moves are real issues from real people</sub>
</div>
{MARKER_END}"""

    readme = README_FILE.read_text(encoding="utf-8")
    start = readme.index(MARKER_START)
    end = readme.index(MARKER_END) + len(MARKER_END)
    README_FILE.write_text(readme[:start] + section + readme[end:], encoding="utf-8")


# ---------------------------------------------------------------------------
# Rendering — comments & hall of fame
# ---------------------------------------------------------------------------

def write_comment(text: str) -> None:
    COMMENT_FILE.write_text(text.rstrip() + "\n", encoding="utf-8")


def how_to_play() -> str:
    return (
        f"**How to play:** head to [my profile]({PROFILE_URL}) and click any move "
        "link under the board — it opens a pre-filled issue, and all you have to do "
        "is press *Submit new issue*. The bot plays your move and credits you."
    )


def append_hall_of_fame(state: dict, board: chess.Board) -> None:
    outcome = board.outcome()
    label = TERMINATION_LABELS.get(outcome.termination, "game over")
    last_player = state["moves"][-1]["player"] if state["moves"] else "—"
    row = (
        f"| #{state['game_number']} | {outcome.result()} ({label}) | "
        f"{len(state['moves'])} | {datetime.date.today().isoformat()} | "
        f"[@{last_player}](https://github.com/{last_player}) |\n"
    )
    if not GAMES_FILE.exists():
        GAMES_FILE.write_text(
            "# 🏆 Hall of Fame\n\n"
            f"Every finished game from the community chess board on [my profile]({PROFILE_URL}).\n\n"
            "| game | result | moves | date | last player |\n"
            "|------|--------|-------|------|-------------|\n",
            encoding="utf-8",
        )
    with open(GAMES_FILE, "a", encoding="utf-8") as fh:
        fh.write(row)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def bootstrap() -> None:
    state = fresh_state(1)
    save_state(state)
    board = board_from_state(state)
    render_board(board)
    render_readme(state, board)
    COMMENT_FILE.unlink(missing_ok=True)
    print(f"Bootstrapped game #{state['game_number']} at the starting position.")


def reject(user: str, reason: str) -> None:
    write_comment(
        f"Hi @{user}, thanks for stopping by! Unfortunately I couldn't play that one:\n\n"
        f"> {reason}\n\n"
        f"{how_to_play()}\n\n"
        "Hope to see your move on the board soon! ♟️"
    )
    set_output("valid", "false")
    print(f"Rejected: {reason}")


def handle_new(state: dict, user: str) -> None:
    board = board_from_state(state)
    if not board.is_game_over():
        reject(
            user,
            f"`chess|new` only works once a game has finished, and the current game "
            f"(game #{state['game_number']}) is still in progress.",
        )
        return

    # A finished game is normally archived automatically, but archive it here
    # too in case state was left finished for any reason.
    append_hall_of_fame(state, board)
    new_state = fresh_state(state["game_number"] + 1)
    save_state(new_state)
    new_board = board_from_state(new_state)
    render_board(new_board)
    render_readme(new_state, new_board)
    write_comment(
        f"Thanks @{user}! 🎉 Game #{new_state['game_number']} has begun — the board on "
        f"[my profile]({PROFILE_URL}) is reset and **white** is to play.\n\n{how_to_play()}"
    )
    set_output("valid", "true")
    set_output("summary", sanitize_summary(f"new game #{new_state['game_number']} by {user}"))
    print(f"Started game #{new_state['game_number']}.")


def handle_move(state: dict, uci: str, user: str) -> None:
    board = board_from_state(state)

    if board.is_game_over():
        reject(
            user,
            "The current game has already finished — open an issue titled "
            "`chess|new` to start the next one.",
        )
        return

    try:
        move = chess.Move.from_uci(uci)
        legal = move in board.legal_moves
    except ValueError:
        legal = False
    if not legal:
        side = "white" if board.turn == chess.WHITE else "black"
        reject(
            user,
            f"`{uci}` isn't a legal move in the current position (it's **{side}**'s turn).",
        )
        return

    san = board.san(move)
    board.push(move)
    halfmove = len(state["moves"]) + 1
    state["moves"].append({"n": halfmove, "san": san, "uci": uci, "player": user})
    state["fen"] = board.fen()
    save_state(state)
    render_board(board)

    set_output("valid", "true")
    set_output("summary", sanitize_summary(f"move {halfmove}: {san} by {user}"))

    if board.is_game_over():
        outcome = board.outcome()
        label = TERMINATION_LABELS.get(outcome.termination, "game over")
        game_no = state["game_number"]
        append_hall_of_fame(state, board)

        # Reset so the board on the profile is always playable.
        next_state = fresh_state(game_no + 1)
        save_state(next_state)
        next_board = board_from_state(next_state)
        render_board(next_board)
        render_readme(
            next_state,
            next_board,
            note=f"game #{game_no} just ended: {outcome.result()} ({label}) — "
            f'see the <a href="{REPO_URL}/blob/main/chess/games.md">hall of fame</a>',
        )
        write_comment(
            f"🏁 What a finish! @{user} played **{san}** and game #{game_no} is over: "
            f"**{outcome.result()}** ({label}).\n\n"
            f"Your move is forever enshrined in the "
            f"[hall of fame]({REPO_URL}/blob/main/chess/games.md). 🏆\n\n"
            f"A fresh game #{next_state['game_number']} has already started on "
            f"[my profile]({PROFILE_URL}) — come claim the first move!"
        )
        print(f"Game #{game_no} finished: {outcome.result()} ({label}). Started game #{next_state['game_number']}.")
        return

    render_readme(state, board)
    next_side = "white" if board.turn == chess.WHITE else "black"
    write_comment(
        f"Thanks @{user}! 🎉\n\n"
        f"You played **{san}** (half-move {halfmove} of game #{state['game_number']}) — "
        f"the board on [my profile]({PROFILE_URL}) has been updated and you're credited "
        f"in the recent moves table.\n\n"
        f"It's **{next_side}**'s turn now. Anyone can play it — even you. "
        f"See you on the board! ♟️"
    )
    print(f"Played {san} (half-move {halfmove}) for @{user}.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "bootstrap":
        bootstrap()
        return

    title = os.environ.get("ISSUE_TITLE", "")
    user = os.environ.get("ISSUE_USER", "someone")
    normalized = re.sub(r"\s+", "", title.lower())

    match = TITLE_RE.match(normalized)
    if not match:
        reject(
            user,
            f"I couldn't understand the issue title `{title.strip() or '(empty)'}`. "
            "Titles must look exactly like `chess|move|e2e4` (or `chess|new` once a "
            "game has finished).",
        )
        return

    state = load_state()
    command = match.group(1)
    if command == "new":
        handle_new(state, user)
    else:
        handle_move(state, command.split("|", 1)[1], user)


if __name__ == "__main__":
    main()
