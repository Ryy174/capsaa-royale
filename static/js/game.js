document.addEventListener("DOMContentLoaded", () => {
    const roundEntry = document.getElementById("roundEntry");
    const saveRoundBtn = document.getElementById("saveRoundBtn");

    if (!roundEntry) return; // game already finished, no entry form

    // Chip selection: one active symbol per player row
    roundEntry.addEventListener("click", (e) => {
        const chip = e.target.closest(".chip");
        if (!chip) return;

        const row = chip.closest(".round-player-row");
        row.querySelectorAll(".chip").forEach((c) => c.classList.remove("selected"));
        chip.classList.add("selected");
    });

    saveRoundBtn.addEventListener("click", async () => {
        const rows = roundEntry.querySelectorAll(".round-player-row");
        const entries = [];

        rows.forEach((row) => {
            const selected = row.querySelector(".chip.selected");
            if (selected) {
                entries.push({
                    player_id: parseInt(row.dataset.playerId, 10),
                    symbol: selected.dataset.symbol,
                });
            }
        });

        if (entries.length === 0) {
            alert("Pilih minimal satu hasil pemain sebelum menyimpan ronde.");
            return;
        }

        saveRoundBtn.disabled = true;
        saveRoundBtn.textContent = "Menyimpan...";

        try {
            const res = await fetch(`/game/${gameId}/save_round`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ entries }),
            });

            const data = await res.json();

            if (!res.ok) {
                alert(data.error || "Gagal menyimpan ronde.");
                saveRoundBtn.disabled = false;
                saveRoundBtn.textContent = "💾 Simpan Ronde";
                return;
            }

            if (data.winner) {
                showWinnerModal(data.winner.name, data.winner.score, data.target_score);
            } else {
                // Reload to reflect new leaderboard/history cleanly
                window.location.reload();
            }
        } catch (err) {
            alert("Terjadi kesalahan jaringan. Coba lagi.");
            saveRoundBtn.disabled = false;
            saveRoundBtn.textContent = "💾 Simpan Ronde";
        }
    });

    function showWinnerModal(name, score, target) {
        document.getElementById("winnerName").textContent = name;
        document.getElementById("winnerScore").textContent = score;
        document.getElementById("winnerOverlay").classList.add("show");
    }
});
