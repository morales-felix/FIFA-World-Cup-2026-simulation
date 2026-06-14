from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.patches import FancyBboxPatch, Rectangle

try:
    from src.world_cup_simulator import (
        build_2026_playoff_matches,
        parse_annex_c_matchups,
    )
except ModuleNotFoundError:
    from world_cup_simulator import (
        build_2026_playoff_matches,
        parse_annex_c_matchups,
    )


STAGE_COLUMNS = [
    "make_round_of_32",
    "make_round_of_16",
    "make_quarterfinals",
    "make_semifinals",
    "make_final",
    "win_tournament",
]

STAGE_LABELS = {
    "make_round_of_32": "R32",
    "make_round_of_16": "R16",
    "make_quarterfinals": "QF",
    "make_semifinals": "SF",
    "make_final": "Final",
    "win_tournament": "Title",
}


def _ensure_output_path(output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _as_percent(values):
    return values * 100


def _sort_probability_columns(data, probability_columns):
    return data.sort_values(
        probability_columns + ["win_tournament", "expected_group_points", "team"],
        ascending=[False] * (len(probability_columns) + 2) + [True],
    )


def build_most_likely_group_stage_result(team_forecast):
    """
    Builds a single central group-stage outcome from the simulation forecast.

    This is not the most common full group table across all simulations. It is a
    readable central case: the most likely winner, runner-up, and third-place
    team in each group, with the eight third-place teams most likely to qualify.
    """

    rows = []
    third_place_candidates = []

    for group in sorted(team_forecast["group"].unique()):
        group_data = team_forecast[team_forecast["group"] == group].copy()

        winner = _sort_probability_columns(group_data, ["win_group"]).iloc[0]
        second = _sort_probability_columns(
            group_data[group_data["team"] != winner["team"]],
            ["finish_second"],
        ).iloc[0]
        third = _sort_probability_columns(
            group_data[~group_data["team"].isin([winner["team"], second["team"]])],
            ["finish_third"],
        ).iloc[0]

        rows.extend(
            [
                {
                    "group": group,
                    "team": winner["team"],
                    "group_rank": 1,
                    "slot_probability": winner["win_group"],
                },
                {
                    "group": group,
                    "team": second["team"],
                    "group_rank": 2,
                    "slot_probability": second["finish_second"],
                },
            ]
        )

        third_place_candidates.append(
            {
                "group": group,
                "team": third["team"],
                "group_rank": 3,
                "slot_probability": third["finish_third"],
                "qualified_as_third_probability": (
                    third["make_round_of_32"]
                    - third["win_group"]
                    - third["finish_second"]
                ),
            }
        )

    best_thirds = pd.DataFrame(third_place_candidates)
    best_thirds = best_thirds.sort_values(
        [
            "qualified_as_third_probability",
            "slot_probability",
            "team",
        ],
        ascending=[False, False, True],
    ).head(8)

    rows.extend(best_thirds.to_dict("records"))

    return pd.DataFrame(rows).sort_values(["group", "group_rank"]).reset_index(drop=True)


def _central_winner(home_team, away_team, stage, team_lookup):
    next_stage_columns = {
        "round_of_32": "make_round_of_16",
        "round_of_16": "make_quarterfinals",
        "quarterfinals": "make_semifinals",
        "semifinals": "make_final",
        "final": "win_tournament",
        "third_place": "win_tournament",
    }
    comparison_column = next_stage_columns[stage]

    home = team_lookup.loc[home_team]
    away = team_lookup.loc[away_team]
    comparison_columns = [
        comparison_column,
        "win_tournament",
        "make_final",
        "make_semifinals",
        "make_quarterfinals",
        "make_round_of_16",
        "make_round_of_32",
    ]

    for column in comparison_columns:
        if home[column] > away[column]:
            return home_team, away_team, home[column] - away[column]
        if away[column] > home[column]:
            return away_team, home_team, away[column] - home[column]

    return min(home_team, away_team), max(home_team, away_team), 0


def build_most_likely_bracket(team_forecast, third_place_matchups):
    """
    Builds a consistent central knockout bracket from team forecast probabilities.
    """

    group_stage_result = build_most_likely_group_stage_result(team_forecast)
    games = build_2026_playoff_matches(
        group_stage_result.to_dict("records"),
        third_place_matchups,
    )
    team_lookup = team_forecast.set_index("team")

    for game in games:
        if game["home_team"] == "" or game["away_team"] == "":
            continue

        winner, loser, edge = _central_winner(
            game["home_team"],
            game["away_team"],
            game["stage"],
            team_lookup,
        )
        game["advances"] = winner
        game["loses"] = loser
        game["forecast_edge"] = edge

        if game["stage"] in ["final", "third_place"]:
            continue

        next_stage = int(game["to_match"])

        if game["stage"] == "semifinals":
            next_game = games[next_stage]
            consolation_game = games[next_stage + 1]

            if next_game["home_team"] == "":
                next_game["home_team"] = winner
            else:
                next_game["away_team"] = winner

            if consolation_game["home_team"] == "":
                consolation_game["home_team"] = loser
            else:
                consolation_game["away_team"] = loser
        else:
            next_game = games[next_stage]

            if next_game["home_team"] == "":
                next_game["home_team"] = winner
            else:
                next_game["away_team"] = winner

    bracket = pd.DataFrame(games)
    bracket["match"] = bracket["match"].astype(int)
    bracket["to_match"] = bracket["to_match"].astype(int)
    return group_stage_result, bracket


def plot_champion_odds(champion_probability, output_path, top_n=10):
    data = (
        champion_probability
        .sort_values("champion_probability", ascending=False)
        .head(top_n)
        .sort_values("champion_probability")
        .copy()
    )

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(
        data["team"],
        _as_percent(data["champion_probability"]),
        color="#1f77b4",
        alpha=0.88,
    )

    if "monte_carlo_se" in data:
        ax.errorbar(
            _as_percent(data["champion_probability"]),
            data["team"],
            xerr=_as_percent(data["monte_carlo_se"]),
            fmt="none",
            ecolor="#333333",
            elinewidth=1,
            capsize=2,
        )

    for _, row in data.iterrows():
        ax.text(
            _as_percent(row["champion_probability"]) + 0.15,
            row["team"],
            f"{_as_percent(row['champion_probability']):.1f}%",
            va="center",
            fontsize=9,
        )

    ax.set_title("Most likely 2026 World Cup champions", loc="left", fontsize=15, weight="bold")
    ax.set_xlabel("Simulated title probability")
    ax.set_ylabel("")
    ax.set_xlim(0, 50)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(_ensure_output_path(output_path), dpi=1000)
    plt.close(fig)


def plot_stage_ladder(team_forecast, output_path, top_n=10):
    data = (
        team_forecast
        .sort_values("win_tournament", ascending=False)
        .head(top_n)
        .set_index("team")[STAGE_COLUMNS]
    )
    data = data.rename(columns=STAGE_LABELS)

    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(
        _as_percent(data),
        cmap="Blues",
        annot=True,
        fmt=".0f",
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Probability (%)"},
        ax=ax,
    )

    ax.set_title("How far each contender usually goes", loc="left", fontsize=15, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(_ensure_output_path(output_path), dpi=300)
    plt.close(fig)


def plot_group_expected_points(group_stage_summary, output_path):
    groups = sorted(group_stage_summary["group"].unique())
    fig, axes = plt.subplots(4, 3, figsize=(11, 12), sharex=True)
    axes = axes.flatten()

    for ax, group in zip(axes, groups):
        data = (
            group_stage_summary[group_stage_summary["group"] == group]
            .sort_values("avg_points")
            .copy()
        )
        y = range(len(data))

        ax.hlines(
            y=y,
            xmin=data["points_2nd_pct"],
            xmax=data["points_97th_pct"],
            color="#a6bddb",
            linewidth=5,
        )
        ax.scatter(data["avg_points"], y, color="#045a8d", s=45, zorder=3)
        ax.set_yticks(list(y))
        ax.set_yticklabels(data["team"])
        ax.set_title(f"Group {group}", loc="left", fontsize=11, weight="bold")
        ax.set_xlim(0, 9)
        ax.grid(axis="x", alpha=0.2)
        ax.spines[["top", "right", "left"]].set_visible(False)

    for ax in axes[len(groups):]:
        ax.axis("off")

    fig.suptitle("Expected group-stage points with 2.5%-97.5% simulation range", x=0.02, ha="left", fontsize=15, weight="bold")
    fig.supxlabel("Group-stage points")
    fig.tight_layout()
    fig.savefig(_ensure_output_path(output_path), dpi=1000)
    plt.close(fig)


def plot_group_advancement_heatmap(team_forecast, output_path):
    data = team_forecast.copy()
    data["label"] = data["group"] + " - " + data["team"]
    data = data.sort_values(["group", "make_round_of_32"], ascending=[True, False])
    heatmap_data = data.set_index("label")[
        ["win_group", "finish_second", "finish_third", "make_round_of_32"]
    ].rename(
        columns={
            "win_group": "Win group",
            "finish_second": "2nd",
            "finish_third": "3rd",
            "make_round_of_32": "Advance"
        }
    )

    fig, ax = plt.subplots(figsize=(9, 14))
    sns.heatmap(
        _as_percent(heatmap_data),
        cmap="YlGnBu",
        annot=True,
        fmt=".0f",
        linewidths=0.35,
        linecolor="white",
        cbar_kws={"label": "Probability (%)"},
        ax=ax,
    )

    ax.set_title("Group-stage path odds", loc="left", fontsize=15, weight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(_ensure_output_path(output_path), dpi=300)
    plt.close(fig)


def _stage_label(stage):
    labels = {
        "round_of_32": "Round of 32",
        "round_of_16": "Round of 16",
        "quarterfinals": "Quarterfinals",
        "semifinals": "Semifinals",
        "final": "Final",
    }
    return labels[stage]


def _compute_bracket_positions(bracket):
    main_bracket = bracket[bracket["stage"] != "third_place"].copy()
    children = {}

    for _, row in main_bracket.iterrows():
        if row["stage"] == "final":
            continue

        children.setdefault(int(row["to_match"]), []).append(int(row["match"]))

    for match in children:
        children[match] = sorted(children[match])

    def leaf_matches(match):
        if match not in children:
            return [match]

        leaves = []
        for child in children[match]:
            leaves.extend(leaf_matches(child))

        return leaves

    leaf_order = leaf_matches(30)
    y_positions = {
        match: len(leaf_order) - index - 1
        for index, match in enumerate(leaf_order)
    }

    for match in sorted(main_bracket["match"]):
        if match in y_positions:
            continue

        feeder_matches = children.get(int(match), [])
        if feeder_matches:
            y_positions[int(match)] = sum(y_positions[child] for child in feeder_matches) / len(feeder_matches)

    x_positions = {
        "round_of_32": 0,
        "round_of_16": 2.35,
        "quarterfinals": 4.7,
        "semifinals": 7.05,
        "final": 9.4,
    }

    return x_positions, y_positions


def _draw_match_box(
    ax,
    x,
    y,
    row,
    box_width=1.82,
    box_height=0.66,
    text_side="left",
    font_size=8.8,
):
    home_team = row["home_team"]
    away_team = row["away_team"]
    winner = row["advances"]
    left = x - box_width / 2
    bottom = y - box_height / 2
    line_height = box_height / 2
    longest_team_name = max(len(home_team), len(away_team))
    team_font_size = font_size - 0.9 if longest_team_name > 18 else font_size
    text_x = left + 0.07 if text_side == "left" else left + box_width - 0.07
    text_ha = "left" if text_side == "left" else "right"

    highlight_y = bottom + line_height if home_team == winner else bottom
    ax.add_patch(
        Rectangle(
            (left, highlight_y),
            box_width,
            line_height,
            facecolor="#d7ecff",
            edgecolor="none",
            zorder=1,
        )
    )
    ax.add_patch(
        FancyBboxPatch(
            (left, bottom),
            box_width,
            box_height,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            facecolor="none",
            edgecolor="#8aa0b5",
            linewidth=0.9,
            zorder=2,
        )
    )

    home_weight = "bold" if home_team == winner else "normal"
    away_weight = "bold" if away_team == winner else "normal"
    ax.text(
        text_x,
        y + box_height / 4,
        home_team,
        ha=text_ha,
        va="center",
        fontsize=team_font_size,
        weight=home_weight,
        color="#0b1f33",
        zorder=3,
    )
    ax.text(
        text_x,
        y - box_height / 4,
        away_team,
        ha=text_ha,
        va="center",
        fontsize=team_font_size,
        weight=away_weight,
        color="#0b1f33",
        zorder=3,
    )


def plot_most_likely_bracket(bracket, output_path):
    main_bracket = bracket[bracket["stage"] != "third_place"].copy()
    children = {}
    for _, row in main_bracket.iterrows():
        if row["stage"] == "final":
            continue

        children.setdefault(int(row["to_match"]), []).append(int(row["match"]))

    for match in children:
        children[match] = sorted(children[match])

    def side_matches(root_match):
        matches = [root_match]
        for child in children.get(root_match, []):
            matches.extend(side_matches(child))

        return matches

    def side_leaf_order(root_match):
        if root_match not in children:
            return [root_match]

        leaves = []
        for child in children[root_match]:
            leaves.extend(side_leaf_order(child))

        return leaves

    def side_y_positions(root_match):
        leaves = side_leaf_order(root_match)
        positions = {
            match: len(leaves) - index - 1
            for index, match in enumerate(leaves)
        }

        def assign_position(match):
            if match in positions:
                return positions[match]

            feeder_positions = [
                assign_position(child)
                for child in children.get(match, [])
            ]
            positions[match] = sum(feeder_positions) / len(feeder_positions)
            return positions[match]

        assign_position(root_match)
        return positions

    left_root = 28
    right_root = 29
    left_matches = set(side_matches(left_root))
    right_matches = set(side_matches(right_root))
    left_y_positions = side_y_positions(left_root)
    right_y_positions = side_y_positions(right_root)

    left_x_positions = {
        "round_of_32": 0,
        "round_of_16": 2.05,
        "quarterfinals": 4.1,
        "semifinals": 6.15,
    }
    right_x_positions = {
        "semifinals": 9.85,
        "quarterfinals": 11.9,
        "round_of_16": 13.95,
        "round_of_32": 16,
    }
    final_x = 8
    final_y = left_y_positions[left_root]
    box_width = 1.72
    box_height = 0.58

    fig, ax = plt.subplots(figsize=(16, 7.2))
    fig.patch.set_facecolor("#f8fafc")
    ax.set_facecolor("#f8fafc")

    def draw_side_connector(row, x_positions, y_positions, side):
        source_match = int(row["match"])
        target_match = int(row["to_match"])

        if target_match == 30:
            target_x = final_x
            target_y = final_y
            target_left = final_x - box_width / 2
            target_right = final_x + box_width / 2
        elif target_match in y_positions:
            target_row = main_bracket.loc[
                main_bracket["match"] == target_match,
            ].iloc[0]
            target_x = x_positions[target_row["stage"]]
            target_y = y_positions[target_match]
            target_left = target_x - box_width / 2
            target_right = target_x + box_width / 2
        else:
            return

        source_x = x_positions[row["stage"]]
        y1 = y_positions[source_match]

        if side == "left":
            x1 = source_x + box_width / 2
            x2 = target_left
        else:
            x1 = source_x - box_width / 2
            x2 = target_right

        midpoint = (x1 + x2) / 2

        ax.plot(
            [x1, midpoint, midpoint, x2],
            [y1, y1, target_y, target_y],
            color="#b8c4d1",
            linewidth=1.1,
            zorder=0,
        )

    for _, row in main_bracket.iterrows():
        match = int(row["match"])
        if match in left_matches and row["stage"] != "final":
            draw_side_connector(row, left_x_positions, left_y_positions, "left")
        elif match in right_matches and row["stage"] != "final":
            draw_side_connector(row, right_x_positions, right_y_positions, "right")

    for _, row in main_bracket.iterrows():
        match = int(row["match"])
        if match in left_matches:
            _draw_match_box(
                ax,
                left_x_positions[row["stage"]],
                left_y_positions[match],
                row,
                box_width=box_width,
                box_height=box_height,
                text_side="left",
                font_size=9.3,
            )
        elif match in right_matches:
            _draw_match_box(
                ax,
                right_x_positions[row["stage"]],
                right_y_positions[match],
                row,
                box_width=box_width,
                box_height=box_height,
                text_side="right",
                font_size=9.3,
            )

    final_row = main_bracket[main_bracket["stage"] == "final"].iloc[0]
    _draw_match_box(
        ax,
        final_x,
        final_y,
        final_row,
        box_width=box_width,
        box_height=box_height,
        text_side="left",
        font_size=9.3,
    )

    champion_y = final_y - 1.02
    champion_width = 1.72
    champion_height = 0.42
    ax.plot(
        [final_x, final_x],
        [
            final_y - box_height / 2,
            champion_y + champion_height / 2,
        ],
        color="#b8c4d1",
        linewidth=1.1,
        zorder=0,
    )
    ax.add_patch(
        FancyBboxPatch(
            (
                final_x - champion_width / 2,
                champion_y - champion_height / 2,
            ),
            champion_width,
            champion_height,
            boxstyle="round,pad=0.03,rounding_size=0.05",
            facecolor="#f6d36b",
            edgecolor="#a37600",
            linewidth=1,
            zorder=2,
        )
    )
    ax.text(
        final_x,
        champion_y,
        f"Champion: {final_row['advances']}",
        ha="center",
        va="center",
        fontsize=9.2,
        weight="bold",
        color="#2c2100",
        zorder=3,
    )

    y_top = max(left_y_positions.values()) + 0.72
    for stage, x in left_x_positions.items():
        ax.text(
            x,
            y_top,
            _stage_label(stage),
            ha="center",
            va="bottom",
            fontsize=9.5,
            weight="bold",
            color="#334155",
        )
    for stage, x in right_x_positions.items():
        ax.text(
            x,
            y_top,
            _stage_label(stage),
            ha="center",
            va="bottom",
            fontsize=9.5,
            weight="bold",
            color="#334155",
        )
    ax.text(
        final_x,
        y_top,
        "Final",
        ha="center",
        va="bottom",
        fontsize=9.5,
        weight="bold",
        color="#334155",
    )

    ax.text(
        -0.95,
        y_top + 0.85,
        "Most likely 2026 World Cup knockout bracket",
        ha="left",
        va="bottom",
        fontsize=18,
        weight="bold",
        color="#0f172a",
    )
    ax.text(
        -0.95,
        y_top + 0.48,
        (
            "Spain and Argentina sit on opposite sides of this central forecast path, "
            "so their first projected meeting is the final."
        ),
        ha="left",
        va="bottom",
        fontsize=10.2,
        color="#475569",
    )
    ax.text(
        -0.95,
        -1.05,
        (
            "Central forecast bracket: most likely group slots, the eight third-place teams "
            "most likely to qualify, then the higher-probability survivor at each knockout step."
        ),
        ha="left",
        va="top",
        fontsize=8.7,
        color="#475569",
    )

    ax.set_xlim(-1.0, 17.0)
    ax.set_ylim(-1.3, y_top + 1.35)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(_ensure_output_path(output_path), dpi=1000, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate 2026 World Cup forecast figures.")
    parser.add_argument("--team-forecast", default="data/full_tournament_team_forecast.csv")
    parser.add_argument("--group-summary", default="data/full_tournament_group_stage_summary.csv")
    parser.add_argument("--champion-probability", default="data/full_tournament_champion_probability.csv")
    parser.add_argument("--regulations-pdf", default="FWC26_regulations_EN.pdf")
    parser.add_argument("--output-dir", default="figures")
    parser.add_argument("--bracket-output", default="data/full_tournament_most_likely_bracket.csv")
    parser.add_argument("--group-stage-output", default="data/full_tournament_most_likely_group_stage.csv")
    args = parser.parse_args()

    team_forecast = pd.read_csv(args.team_forecast)
    group_stage_summary = pd.read_csv(args.group_summary)
    champion_probability = pd.read_csv(args.champion_probability)
    third_place_matchups = parse_annex_c_matchups(args.regulations_pdf)
    output_dir = Path(args.output_dir)

    plot_champion_odds(champion_probability, output_dir / "champion_odds.png")
    plot_stage_ladder(team_forecast, output_dir / "stage_ladder.png")
    plot_group_expected_points(group_stage_summary, output_dir / "group_expected_points.png")
    plot_group_advancement_heatmap(team_forecast, output_dir / "group_advancement_heatmap.png")
    group_stage_result, bracket = build_most_likely_bracket(
        team_forecast,
        third_place_matchups,
    )
    group_stage_result.to_csv(_ensure_output_path(args.group_stage_output), index=False)
    bracket.to_csv(_ensure_output_path(args.bracket_output), index=False)
    plot_most_likely_bracket(bracket, output_dir / "most_likely_bracket.png")


if __name__ == "__main__":
    main()
