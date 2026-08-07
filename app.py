import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, g

app = Flask(__name__)
DATABASE = "capsa_royale.db"

SCORE_OPTIONS = {
    "diamond": 4,   # 💎 kemenangan spesial
    "gold": 3,      # ⭐
    "silver": 2,    # 🥈
    "bronze": 1,    # 🥉
    "flat": 0,      # 😐
    "minus1": -1,   # ❌
    "minus2": -2,   # 💣
    "skull": -3,    # ☠️ curang
}

SYMBOL_EMOJI = {
    "diamond": "💎",
    "gold": "⭐",
    "silver": "🥈",
    "bronze": "🥉",
    "flat": "😐",
    "minus1": "❌",
    "minus2": "💣",
    "skull": "☠️",
}


# ---------- Database helpers ----------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_score INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            winner_name TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            total_score INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (game_id) REFERENCES games (id)
        );

        CREATE TABLE IF NOT EXISTS rounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games (id)
        );

        CREATE TABLE IF NOT EXISTS round_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            points INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            FOREIGN KEY (round_id) REFERENCES rounds (id),
            FOREIGN KEY (player_id) REFERENCES players (id)
        );
        """
    )
    conn.commit()
    conn.close()


# ---------- Routes: pages ----------

@app.route("/")
def home():
    db = get_db()
    active_games = db.execute(
        "SELECT * FROM games WHERE status = 'active' ORDER BY created_at DESC"
    ).fetchall()
    return render_template("home.html", active_games=active_games)


@app.route("/new_game", methods=["GET", "POST"])
def new_game():
    if request.method == "POST":
        target_score = int(request.form.get("target_score", 25))
        player_names = [
            name.strip()
            for name in request.form.getlist("player_name")
            if name.strip()
        ]

        if len(player_names) < 2:
            return render_template(
                "new_game.html",
                error="Minimal 2 pemain untuk memulai game.",
            )

        db = get_db()
        cur = db.execute(
            "INSERT INTO games (target_score, status, created_at) VALUES (?, 'active', ?)",
            (target_score, datetime.now().isoformat()),
        )
        game_id = cur.lastrowid

        for name in player_names:
            db.execute(
                "INSERT INTO players (game_id, name, total_score) VALUES (?, ?, 0)",
                (game_id, name),
            )
        db.commit()

        return redirect(url_for("game_board", game_id=game_id))

    return render_template("new_game.html")


@app.route("/game/<int:game_id>")
def game_board(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        return redirect(url_for("home"))

    players = db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC, name ASC",
        (game_id,),
    ).fetchall()

    rounds = db.execute(
        "SELECT * FROM rounds WHERE game_id = ? ORDER BY round_number DESC",
        (game_id,),
    ).fetchall()

    history = []
    for r in rounds:
        scores = db.execute(
            """
            SELECT round_scores.points, round_scores.symbol, players.name
            FROM round_scores
            JOIN players ON players.id = round_scores.player_id
            WHERE round_scores.round_id = ?
            """,
            (r["id"],),
        ).fetchall()
        history.append({"round": r, "scores": scores})

    return render_template(
        "game.html",
        game=game,
        players=players,
        history=history,
        score_options=SCORE_OPTIONS,
        symbol_emoji=SYMBOL_EMOJI,
    )


@app.route("/history")
def history_page():
    db = get_db()
    finished_games = db.execute(
        "SELECT * FROM games WHERE status = 'finished' ORDER BY created_at DESC"
    ).fetchall()

    games_with_players = []
    for game in finished_games:
        players = db.execute(
            "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC",
            (game["id"],),
        ).fetchall()
        games_with_players.append({"game": game, "players": players})

    return render_template("history.html", games=games_with_players)


# ---------- Routes: API / actions ----------

@app.route("/game/<int:game_id>/save_round", methods=["POST"])
def save_round(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None or game["status"] != "active":
        return jsonify({"error": "Game tidak ditemukan atau sudah selesai."}), 400

    data = request.get_json()
    entries = data.get("entries", [])  # [{player_id, symbol}]

    if not entries:
        return jsonify({"error": "Belum ada skor yang dipilih."}), 400

    last_round = db.execute(
        "SELECT MAX(round_number) as n FROM rounds WHERE game_id = ?", (game_id,)
    ).fetchone()
    round_number = (last_round["n"] or 0) + 1

    cur = db.execute(
        "INSERT INTO rounds (game_id, round_number, created_at) VALUES (?, ?, ?)",
        (game_id, round_number, datetime.now().isoformat()),
    )
    round_id = cur.lastrowid

    for entry in entries:
        player_id = entry["player_id"]
        symbol = entry["symbol"]
        points = SCORE_OPTIONS.get(symbol, 0)

        db.execute(
            "INSERT INTO round_scores (round_id, player_id, points, symbol) VALUES (?, ?, ?, ?)",
            (round_id, player_id, points, symbol),
        )
        db.execute(
            "UPDATE players SET total_score = total_score + ? WHERE id = ?",
            (points, player_id),
        )

    db.commit()

    # Check for winner
    players = db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC",
        (game_id,),
    ).fetchall()

    winner = None
    for p in players:
        if p["total_score"] >= game["target_score"]:
            winner = p
            break

    if winner:
        db.execute(
            "UPDATE games SET status = 'finished', winner_name = ? WHERE id = ?",
            (winner["name"], game_id),
        )
        db.commit()

    leaderboard = [
        {"id": p["id"], "name": p["name"], "total_score": p["total_score"]}
        for p in players
    ]

    return jsonify(
        {
            "success": True,
            "leaderboard": leaderboard,
            "winner": {"name": winner["name"], "score": winner["total_score"]}
            if winner
            else None,
            "target_score": game["target_score"],
        }
    )


@app.route("/game/<int:game_id>/reset", methods=["POST"])
def reset_game(game_id):
    db = get_db()
    db.execute(
        "DELETE FROM round_scores WHERE round_id IN (SELECT id FROM rounds WHERE game_id = ?)",
        (game_id,),
    )
    db.execute("DELETE FROM rounds WHERE game_id = ?", (game_id,))
    db.execute("UPDATE players SET total_score = 0 WHERE game_id = ?", (game_id,))
    db.execute(
        "UPDATE games SET status = 'active', winner_name = NULL WHERE id = ?",
        (game_id,),
    )
    db.commit()
    return redirect(url_for("game_board", game_id=game_id))


@app.route("/game/<int:game_id>/delete", methods=["POST"])
def delete_game(game_id):
    db = get_db()
    db.execute(
        "DELETE FROM round_scores WHERE round_id IN (SELECT id FROM rounds WHERE game_id = ?)",
        (game_id,),
    )
    db.execute("DELETE FROM rounds WHERE game_id = ?", (game_id,))
    db.execute("DELETE FROM players WHERE game_id = ?", (game_id,))
    db.execute("DELETE FROM games WHERE id = ?", (game_id,))
    db.commit()
    return redirect(url_for("home"))


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
        if len(player_names) < 2:
            return render_template(
                "new_game.html",
                error="Minimal 2 pemain untuk memulai game.",
            )

        db = get_db()
        cur = db.execute(
            "INSERT INTO games (target_score, status, created_at) VALUES (?, 'active', ?)",
            (target_score, datetime.now().isoformat()),
        )
        game_id = cur.lastrowid

        for name in player_names:
            db.execute(
                "INSERT INTO players (game_id, name, total_score) VALUES (?, ?, 0)",
                (game_id, name),
            )
        db.commit()

        return redirect(url_for("game_board", game_id=game_id))

    return render_template("new_game.html")


@app.route("/game/<int:game_id>")
def game_board(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        return redirect(url_for("home"))

    players = db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC, name ASC",
        (game_id,),
    ).fetchall()

    rounds = db.execute(
        "SELECT * FROM rounds WHERE game_id = ? ORDER BY round_number DESC",
        (game_id,),
    ).fetchall()

    history = []
    for r in rounds:
        scores = db.execute(
            """
            SELECT round_scores.points, round_scores.symbol, players.name
            FROM round_scores
            JOIN players ON players.id = round_scores.player_id
            WHERE round_scores.round_id = ?
            """,
            (r["id"],),
        ).fetchall()
        history.append({"round": r, "scores": scores})

    return render_template(
        "game.html",
        game=game,
        players=players,
        history=history,
        score_options=SCORE_OPTIONS,
        symbol_emoji=SYMBOL_EMOJI,
    )


@app.route("/history")
def history_page():
    db = get_db()
    finished_games = db.execute(
        "SELECT * FROM games WHERE status = 'finished' ORDER BY created_at DESC"
    ).fetchall()

    games_with_players = []
    for game in finished_games:
        players = db.execute(
            "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC",
            (game["id"],),
        ).fetchall()
        games_with_players.append({"game": game, "players": players})

    return render_template("history.html", games=games_with_players)


# ---------- Routes: API / actions ----------

@app.route("/game/<int:game_id>/save_round", methods=["POST"])
def save_round(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None or game["status"] != "active":
        return jsonify({"error": "Game tidak ditemukan atau sudah selesai."}), 400

    data = request.get_json()
    entries = data.get("entries", [])  # [{player_id, symbol}]

    if not entries:
        return jsonify({"error": "Belum ada skor yang dipilih."}), 400

    last_round = db.execute(
        "SELECT MAX(round_number) as n FROM rounds WHERE game_id = ?", (game_id,)
    ).fetchone()
    round_number = (last_round["n"] or 0) + 1

    cur = db.execute(
        "INSERT INTO rounds (game_id, round_number, created_at) VALUES (?, ?, ?)",
        (game_id, round_number, datetime.now().isoformat()),
    )
    round_id = cur.lastrowid

    for entry in entries:
        player_id = entry["player_id"]
        symbol = entry["symbol"]
        points = SCORE_OPTIONS.get(symbol, 0)

        db.execute(
            "INSERT INTO round_scores (round_id, player_id, points, symbol) VALUES (?, ?, ?, ?)",
            (round_id, player_id, points, symbol),
        )
        db.execute(
            "UPDATE players SET total_score = total_score + ? WHERE id = ?",
            (points, player_id),
        )

    db.commit()

    # Check for winner
    players = db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC",
        (game_id,),
    ).fetchall()

    winner = None
    for p in players:
        if p["total_score"] >= game["target_score"]:
            winner = p
            break

    if winner:
        db.execute(
            "UPDATE games SET status = 'finished', winner_name = ? WHERE id = ?",
            (winner["name"], game_id),
        )
        db.commit()

    leaderboard = [
        {"id": p["id"], "name": p["name"], "total_score": p["total_score"]}
        for p in players
    ]

    return jsonify(
        {
            "success": True,
            "leaderboard": leaderboard,
            "winner": {"name": winner["name"], "score": winner["total_score"]}
            if winner
            else None,
            "target_score": game["target_score"],
        }
    )


@app.route("/game/<int:game_id>/reset", methods=["POST"])
def reset_game(game_id):
    db = get_db()
    db.execute(
        "DELETE FROM round_scores WHERE round_id IN (SELECT id FROM rounds WHERE game_id = ?)",
        (game_id,),
    )
    db.execute("DELETE FROM rounds WHERE game_id = ?", (game_id,))
    db.execute("UPDATE players SET total_score = 0 WHERE game_id = ?", (game_id,))
    db.execute(
        "UPDATE games SET status = 'active', winner_name = NULL WHERE id = ?",
        (game_id,),
    )
    db.commit()
    return redirect(url_for("game_board", game_id=game_id))


@app.route("/game/<int:game_id>/delete", methods=["POST"])
def delete_game(game_id):
    db = get_db()
    db.execute(
        "DELETE FROM round_scores WHERE round_id IN (SELECT id FROM rounds WHERE game_id = ?)",
        (game_id,),
    )
    db.execute("DELETE FROM rounds WHERE game_id = ?", (game_id,))
    db.execute("DELETE FROM players WHERE game_id = ?", (game_id,))
    db.execute("DELETE FROM games WHERE id = ?", (game_id,))
    db.commit()
    return redirect(url_for("home"))


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)            )

        db = get_db()
        cur = db.execute(
            "INSERT INTO games (target_score, status, created_at) VALUES (?, 'active', ?)",
            (target_score, datetime.now().isoformat()),
        )
        game_id = cur.lastrowid

        for name in player_names:
            db.execute(
                "INSERT INTO players (game_id, name, total_score) VALUES (?, ?, 0)",
                (game_id, name),
            )
        db.commit()

        return redirect(url_for("game_board", game_id=game_id))

    return render_template("new_game.html")


@app.route("/game/<int:game_id>")
def game_board(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        return redirect(url_for("home"))

    players = db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC, name ASC",
        (game_id,),
    ).fetchall()

    rounds = db.execute(
        "SELECT * FROM rounds WHERE game_id = ? ORDER BY round_number DESC",
        (game_id,),
    ).fetchall()

    history = []
    for r in rounds:
        scores = db.execute(
            """
            SELECT round_scores.points, round_scores.symbol, players.name
            FROM round_scores
            JOIN players ON players.id = round_scores.player_id
            WHERE round_scores.round_id = ?
            """,
            (r["id"],),
        ).fetchall()
        history.append({"round": r, "scores": scores})

    return render_template(
        "game.html",
        game=game,
        players=players,
        history=history,
        score_options=SCORE_OPTIONS,
        symbol_emoji=SYMBOL_EMOJI,
    )


@app.route("/history")
def history_page():
    db = get_db()
    finished_games = db.execute(
        "SELECT * FROM games WHERE status = 'finished' ORDER BY created_at DESC"
    ).fetchall()

    games_with_players = []
    for game in finished_games:
        players = db.execute(
            "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC",
            (game["id"],),
        ).fetchall()
        games_with_players.append({"game": game, "players": players})

    return render_template("history.html", games=games_with_players)


# ---------- Routes: API / actions ----------

@app.route("/game/<int:game_id>/save_round", methods=["POST"])
def save_round(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None or game["status"] != "active":
        return jsonify({"error": "Game tidak ditemukan atau sudah selesai."}), 400

    data = request.get_json()
    entries = data.get("entries", [])  # [{player_id, symbol}]

    if not entries:
        return jsonify({"error": "Belum ada skor yang dipilih."}), 400

    last_round = db.execute(
        "SELECT MAX(round_number) as n FROM rounds WHERE game_id = ?", (game_id,)
    ).fetchone()
    round_number = (last_round["n"] or 0) + 1

    cur = db.execute(
        "INSERT INTO rounds (game_id, round_number, created_at) VALUES (?, ?, ?)",
        (game_id, round_number, datetime.now().isoformat()),
    )
    round_id = cur.lastrowid

    for entry in entries:
        player_id = entry["player_id"]
        symbol = entry["symbol"]
        points = SCORE_OPTIONS.get(symbol, 0)

        db.execute(
            "INSERT INTO round_scores (round_id, player_id, points, symbol) VALUES (?, ?, ?, ?)",
            (round_id, player_id, points, symbol),
        )
        db.execute(
            "UPDATE players SET total_score = total_score + ? WHERE id = ?",
            (points, player_id),
        )

    db.commit()

    # Check for winner
    players = db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC",
        (game_id,),
    ).fetchall()

    winner = None
    for p in players:
        if p["total_score"] >= game["target_score"]:
            winner = p
            break

    if winner:
        db.execute(
            "UPDATE games SET status = 'finished', winner_name = ? WHERE id = ?",
            (winner["name"], game_id),
        )
        db.commit()

    leaderboard = [
        {"id": p["id"], "name": p["name"], "total_score": p["total_score"]}
        for p in players
    ]

    return jsonify(
        {
            "success": True,
            "leaderboard": leaderboard,
            "winner": {"name": winner["name"], "score": winner["total_score"]}
            if winner
            else None,
            "target_score": game["target_score"],
        }
    )


@app.route("/game/<int:game_id>/reset", methods=["POST"])
def reset_game(game_id):
    db = get_db()
    db.execute(
        "DELETE FROM round_scores WHERE round_id IN (SELECT id FROM rounds WHERE game_id = ?)",
        (game_id,),
    )
    db.execute("DELETE FROM rounds WHERE game_id = ?", (game_id,))
    db.execute("UPDATE players SET total_score = 0 WHERE game_id = ?", (game_id,))
    db.execute(
        "UPDATE games SET status = 'active', winner_name = NULL WHERE id = ?",
        (game_id,),
    )
    db.commit()
    return redirect(url_for("game_board", game_id=game_id))


@app.route("/game/<int:game_id>/delete", methods=["POST"])
def delete_game(game_id):
    db = get_db()
    db.execute(
        "DELETE FROM round_scores WHERE round_id IN (SELECT id FROM rounds WHERE game_id = ?)",
        (game_id,),
    )
    db.execute("DELETE FROM rounds WHERE game_id = ?", (game_id,))
    db.execute("DELETE FROM players WHERE game_id = ?", (game_id,))
    db.execute("DELETE FROM games WHERE id = ?", (game_id,))
    db.commit()
    return redirect(url_for("home"))


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
        for name in player_names:
            db.execute(
                "INSERT INTO players (game_id, name, total_score) VALUES (?, ?, 0)",
                (game_id, name),
            )
        db.commit()

        return redirect(url_for("game_board", game_id=game_id))

    return render_template("new_game.html")


@app.route("/game/<int:game_id>")
def game_board(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None:
        return redirect(url_for("home"))

    players = db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC, name ASC",
        (game_id,),
    ).fetchall()

    rounds = db.execute(
        "SELECT * FROM rounds WHERE game_id = ? ORDER BY round_number DESC",
        (game_id,),
    ).fetchall()

    history = []
    for r in rounds:
        scores = db.execute(
            """
            SELECT round_scores.points, round_scores.symbol, players.name
            FROM round_scores
            JOIN players ON players.id = round_scores.player_id
            WHERE round_scores.round_id = ?
            """,
            (r["id"],),
        ).fetchall()
        history.append({"round": r, "scores": scores})

    return render_template(
        "game.html",
        game=game,
        players=players,
        history=history,
        score_options=SCORE_OPTIONS,
    )


@app.route("/history")
def history_page():
    db = get_db()
    finished_games = db.execute(
        "SELECT * FROM games WHERE status = 'finished' ORDER BY created_at DESC"
    ).fetchall()

    games_with_players = []
    for game in finished_games:
        players = db.execute(
            "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC",
            (game["id"],),
        ).fetchall()
        games_with_players.append({"game": game, "players": players})

    return render_template("history.html", games=games_with_players)


# ---------- Routes: API / actions ----------

@app.route("/game/<int:game_id>/save_round", methods=["POST"])
def save_round(game_id):
    db = get_db()
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game is None or game["status"] != "active":
        return jsonify({"error": "Game tidak ditemukan atau sudah selesai."}), 400

    data = request.get_json()
    entries = data.get("entries", [])  # [{player_id, symbol}]

    if not entries:
        return jsonify({"error": "Belum ada skor yang dipilih."}), 400

    last_round = db.execute(
        "SELECT MAX(round_number) as n FROM rounds WHERE game_id = ?", (game_id,)
    ).fetchone()
    round_number = (last_round["n"] or 0) + 1

    cur = db.execute(
        "INSERT INTO rounds (game_id, round_number, created_at) VALUES (?, ?, ?)",
        (game_id, round_number, datetime.now().isoformat()),
    )
    round_id = cur.lastrowid

    for entry in entries:
        player_id = entry["player_id"]
        symbol = entry["symbol"]
        points = SCORE_OPTIONS.get(symbol, 0)

        db.execute(
            "INSERT INTO round_scores (round_id, player_id, points, symbol) VALUES (?, ?, ?, ?)",
            (round_id, player_id, points, symbol),
        )
        db.execute(
            "UPDATE players SET total_score = total_score + ? WHERE id = ?",
            (points, player_id),
        )

    db.commit()

    # Check for winner
    players = db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY total_score DESC",
        (game_id,),
    ).fetchall()

    winner = None
    for p in players:
        if p["total_score"] >= game["target_score"]:
            winner = p
            break

    if winner:
        db.execute(
            "UPDATE games SET status = 'finished', winner_name = ? WHERE id = ?",
            (winner["name"], game_id),
        )
        db.commit()

    leaderboard = [
        {"id": p["id"], "name": p["name"], "total_score": p["total_score"]}
        for p in players
    ]

    return jsonify(
        {
            "success": True,
            "leaderboard": leaderboard,
            "winner": {"name": winner["name"], "score": winner["total_score"]}
            if winner
            else None,
            "target_score": game["target_score"],
        }
    )


@app.route("/game/<int:game_id>/reset", methods=["POST"])
def reset_game(game_id):
    db = get_db()
    db.execute(
        "DELETE FROM round_scores WHERE round_id IN (SELECT id FROM rounds WHERE game_id = ?)",
        (game_id,),
    )
    db.execute("DELETE FROM rounds WHERE game_id = ?", (game_id,))
    db.execute("UPDATE players SET total_score = 0 WHERE game_id = ?", (game_id,))
    db.execute(
        "UPDATE games SET status = 'active', winner_name = NULL WHERE id = ?",
        (game_id,),
    )
    db.commit()
    return redirect(url_for("game_board", game_id=game_id))


@app.route("/game/<int:game_id>/delete", methods=["POST"])
def delete_game(game_id):
    db = get_db()
    db.execute(
        "DELETE FROM round_scores WHERE round_id IN (SELECT id FROM rounds WHERE game_id = ?)",
        (game_id,),
    )
    db.execute("DELETE FROM rounds WHERE game_id = ?", (game_id,))
    db.execute("DELETE FROM players WHERE game_id = ?", (game_id,))
    db.execute("DELETE FROM games WHERE id = ?", (game_id,))
    db.commit()
    return redirect(url_for("home"))


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
