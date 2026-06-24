import math
import random


def read_games(file):
    """
    Initializes game objects from csv
    """
    
    import csv

    games = [item for item in csv.DictReader(open(file, encoding="latin-1"))]

    return games


def read_teams(file):
    """
    Initializes team objects from csv
    """

    import csv

    teams = {}

    for row in csv.DictReader(open(file, encoding="latin-1")):
        rating = float(row["rating"])
        points = int(float(row.get("points", 0) or 0))
        teams[row["team"]] = {
            "name": row["team"],
            "group": row.get("group", ""),
            "rating": rating,
            "start_rating": rating,
            "points": points,
        }

    return teams


def simulate_group_stage_game(game, ternary=True):
    """
    Simulates a single game in the group stage
    """

    home = game["elo_prob_home"]
    away = 1 - game["elo_prob_home"]
    tie = 0

    # Simulating game proper
    wildcard = random.uniform(0, 1)

    # Concoction to go from binary probabilities to ternary
    if ternary:
        if home > 0 and home < 1:
            home_odds = home / away
            tie_odds = 1
            away_odds = 1 - abs(home - 0.5) * 2

            home_odds1 = (home / away) / min(away_odds, tie_odds, home_odds)
            tie_odds1 = 1 / min(away_odds, tie_odds, home_odds)
            away_odds1 = (1 - abs(home - 0.5) * 2) / min(away_odds, tie_odds, home_odds)

            home = home_odds1 / (home_odds1 + tie_odds1 + away_odds1)
            tie = tie_odds1 / (home_odds1 + tie_odds1 + away_odds1)
            away = away_odds1 / (home_odds1 + tie_odds1 + away_odds1)

        elif home == 0:
            tie = 0
            away = 1

        elif home == 1:
            tie = 0
            away = 0

        else:
            raise ValueError("Probabilities must be floats between 0 and 1, inclusive")
    else:
        pass

    if wildcard >= 0 and wildcard < away:
        return 0

    if wildcard >= away and wildcard < away + tie and ternary:
        return 0.5

    if wildcard >= away + tie and wildcard <= 1:
        return 1


def simulate_playoff_game(game, ternary=True):
    """
    Simulates a single game in the knockout stage
    """

    home = game["elo_prob_home"]
    away = 1 - game["elo_prob_home"]
    tie = 0

    # Simulating game proper
    wildcard = random.uniform(0, 1)

    # Concoction to go from binary probabilities to ternary
    # 50-50% should translate into 1/3, 1/3, 1/3 (even split of probability space)
    # With increasing lopsidedness (e.g. 75-25%), the stronger team should see increased win probability,
    # and the weaker team should see decreased win probability. And in terms of ties, that also should decrease
    # as lopsidedness increases, but I assume that at a lower rate than weaker team win probability.
    if ternary:
        if home > 0 and home < 1:
            home_odds = home / away
            tie_odds = 1
            away_odds = 1 - abs(home - 0.5) * 2

            home_odds1 = (home / away) / min(away_odds, tie_odds, home_odds)
            tie_odds1 = 1 / min(away_odds, tie_odds, home_odds)
            away_odds1 = (1 - abs(home - 0.5) * 2) / min(away_odds, tie_odds, home_odds)

            home = home_odds1 / (home_odds1 + tie_odds1 + away_odds1)
            tie = tie_odds1 / (home_odds1 + tie_odds1 + away_odds1)
            away = away_odds1 / (home_odds1 + tie_odds1 + away_odds1)

        elif home == 0:
            tie = 0
            away = 1

        elif home == 1:
            tie = 0
            away = 0

        else:
            raise ValueError("Probabilities must be floats between 0 and 1, inclusive")
    else:
        pass

    if wildcard >= 0 and wildcard < away:
        return game["away_team"], game["home_team"], 0, False

    if wildcard >= away and wildcard < away + tie and ternary:
        # Simulating outcome of a penalty shootout. I assume it is a coin-toss. An advancing team is needed.
        teams = [game["away_team"], game["home_team"]]
        advances = random.choice(teams)
        teams.remove(advances)
        return advances, teams[0], 0.5, True

    if wildcard >= away + tie and wildcard <= 1:
        return game["home_team"], game["away_team"], 1, False


def simulate_group_stage(games, teams, ternary=True):
    """
    Simulates the entire group stage
    """

    for game in games:
        team1, team2 = teams[game["home_team"]], teams[game["away_team"]]

        # Home field advantage is BS
        elo_diff = team1["rating"] - team2["rating"]

        # This is the most important piece, where we set my_prob1 to our forecasted probability
        game["elo_prob_home"] = 1.0 / (math.pow(10.0, (-elo_diff / 400.0)) + 1.0)

        # If game was played, maintain team Elo ratings
        if game["result_home"] == "":

            game["result_home"] = simulate_group_stage_game(game, ternary)

            # Elo shift based on K
            shift = 60.0 * (game["result_home"] - game["elo_prob_home"])

            # Apply shift
            team1["rating"] += shift
            team2["rating"] -= shift

            # Apply points
            if game["result_home"] == 0:
                team1["points"] += 0
                team2["points"] += 3
            elif game["result_home"] == 0.5:
                team1["points"] += 1
                team2["points"] += 1
            else:
                team1["points"] += 3
                team2["points"] += 0


def simulate_playoffs(games, teams, ternary=True):
    """
    Simulates the entire knockout stage
    """

    for game in games:
        team1, team2 = teams[game["home_team"]], teams[game["away_team"]]

        # Home field advantage is B.S. in modern soccer
        elo_diff = team1["rating"] - team2["rating"]

        # This is the most important piece
        game["elo_prob_home"] = 1.0 / (math.pow(10.0, (-elo_diff / 400.0)) + 1.0)

        # If game was played, maintain team Elo ratings
        if game["advances"] == "" or game["loses"] == "":

            game["advances"], game["loses"], game["result_home"], game["penalties"] = (
                simulate_playoff_game(game, ternary)
            )

            # Elo shift based on K
            shift = 60.0 * (game["result_home"] - game["elo_prob_home"])

            # Apply shift
            team1["rating"] += shift
            team2["rating"] -= shift

        # This is to populate the next knockout round based on previous results.
        next_stage = int(game["to_match"])

        if game["stage"] in ["final", "third_place"]:
            pass
        elif game["stage"] == "semifinals":
            if games[next_stage]["home_team"] == "":
                games[next_stage]["home_team"] = game["advances"]
            else:
                games[next_stage]["away_team"] = game["advances"]

            if games[next_stage + 1]["home_team"] == "":
                games[next_stage + 1]["home_team"] = game["loses"]
            else:
                games[next_stage + 1]["away_team"] = game["loses"]
        else:
            if games[next_stage]["home_team"] == "":
                games[next_stage]["home_team"] = game["advances"]
            else:
                games[next_stage]["away_team"] = game["advances"]


def collect_playoff_results(team, dataframe):
    """
    Collects the results of a team in the knockout stage
    """
    
    f = dataframe["home_team"] == team
    g = dataframe["away_team"] == team

    team_pd = dataframe.loc[f | g]
    max_match_number = team_pd["match"].astype(int).max()

    if max_match_number < 16:
        result = "Round_of_32"
    elif max_match_number >= 16 and max_match_number < 24:
        result = "Round_of_16"
    elif max_match_number >= 24 and max_match_number < 28:
        result = "Quarterfinals"
    elif max_match_number >= 28 and max_match_number < 30:
        result = "Semifinals"
    elif max_match_number == 30:
        if team_pd.loc[max_match_number, "advances"] == team:
            result = "Champion"
        else:
            result = "Second_place"
    elif max_match_number == 31:
        if team_pd.loc[max_match_number, "advances"] == team:
            result = "Third_place"
        else:
            result = "Fourth_place"

    return result


def collect_playoff_results_from_games(team, games):
    """
    Collects the knockout-stage result of a team from game dictionaries.
    """

    team_games = [
        game for game in games
        if game["home_team"] == team or game["away_team"] == team
    ]

    if not team_games:
        return "Group_stage"

    max_match_number = max(int(game["match"]) for game in team_games)
    final_game = [
        game for game in team_games
        if int(game["match"]) == max_match_number
    ][0]

    if max_match_number < 16:
        result = "Round_of_32"
    elif max_match_number >= 16 and max_match_number < 24:
        result = "Round_of_16"
    elif max_match_number >= 24 and max_match_number < 28:
        result = "Quarterfinals"
    elif max_match_number >= 28 and max_match_number < 30:
        result = "Semifinals"
    elif max_match_number == 30:
        if final_game["advances"] == team:
            result = "Champion"
        else:
            result = "Second_place"
    elif max_match_number == 31:
        if final_game["advances"] == team:
            result = "Third_place"
        else:
            result = "Fourth_place"

    return result


def parse_annex_c_matchups(pdf_path="FWC26_regulations_EN.pdf"):
    """
    Parses Annex C of the 2026 World Cup regulations PDF.
    """

    import re
    import subprocess
    from pathlib import Path

    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(Path(pdf_path)), "-"],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pdftotext is required to parse Annex C from FWC26_regulations_EN.pdf."
        ) from exc

    text = completed.stdout.decode("utf-8", errors="replace")
    row_pattern = re.compile(
        r"^\s*(\d{1,3})\s+" + r"\s+".join([r"(3[A-L])"] * 8) + r"\s*$"
    )
    assignment_targets = ["1A", "1B", "1D", "1E", "1G", "1I", "1K", "1L"]
    matchups = {}

    for line in text.splitlines():
        match = row_pattern.match(line)
        if not match:
            continue

        option = int(match.group(1))
        assignments = match.groups()[1:]
        third_groups_key = "".join(sorted(slot[1] for slot in assignments))
        matchups[third_groups_key] = {
            "option": option,
            "matchups": dict(zip(assignment_targets, assignments)),
        }

    if len(matchups) != 495:
        raise ValueError(
            f"Expected 495 Annex C matchup combinations, found {len(matchups)}"
        )

    return matchups


def rank_2026_group_stage(teams, games):
    """
    Ranks all 2026 group-stage teams after one simulated group stage.
    """

    groups = {}
    group_games = {}

    for game in games:
        group_games.setdefault(game["group"], []).append(game)

    for team in teams.values():
        groups.setdefault(team["group"], []).append(
            {
                "group": team["group"],
                "team": team["name"],
                "points": team["points"],
                "start_rating": team["start_rating"],
                "rating_after_group": team["rating"],
                "tie_breaker": random.random(),
            }
        )

    ranked = []

    for group in sorted(groups):
        group_ranked = []

        point_totals = sorted(
            {row["points"] for row in groups[group]},
            reverse=True,
        )

        for points in point_totals:
            tied_rows = [
                row for row in groups[group]
                if row["points"] == points
            ]
            tied_teams = {row["team"] for row in tied_rows}
            head_to_head_points = {
                team: 0 for team in tied_teams
            }

            for game in group_games[group]:
                home_team = game["home_team"]
                away_team = game["away_team"]

                if home_team not in tied_teams or away_team not in tied_teams:
                    continue

                result_home = float(game["result_home"])

                if result_home == 1:
                    head_to_head_points[home_team] += 3
                elif result_home == 0.5:
                    head_to_head_points[home_team] += 1
                    head_to_head_points[away_team] += 1
                elif result_home == 0:
                    head_to_head_points[away_team] += 3

            group_ranked.extend(
                sorted(
                    tied_rows,
                    key=lambda row: (
                        head_to_head_points[row["team"]],
                        row["start_rating"],
                        row["tie_breaker"],
                    ),
                    reverse=True,
                )
            )

        for rank, row in enumerate(group_ranked, start=1):
            ranked_row = {
                "group": row["group"],
                "team": row["team"],
                "points": row["points"],
                "start_rating": row["start_rating"],
                "rating_after_group": row["rating_after_group"],
                "group_rank": rank,
                "_tie_breaker": row["tie_breaker"],
            }
            ranked.append(ranked_row)

    return ranked


def select_2026_knockout_teams(group_stage_rankings):
    """
    Selects the 24 top-two teams and eight best third-place teams.
    """

    automatic_qualifiers = [
        row for row in group_stage_rankings
        if row["group_rank"] <= 2
    ]
    third_place_teams = [
        row for row in group_stage_rankings
        if row["group_rank"] == 3
    ]
    best_third_place_teams = sorted(
        third_place_teams,
        key=lambda row: (
            row["points"],
            row["start_rating"],
            row.get("_tie_breaker", 0),
        ),
        reverse=True,
    )[:8]

    return sorted(
        automatic_qualifiers + best_third_place_teams,
        key=lambda row: (row["group"], row["group_rank"]),
    )


def build_2026_playoff_matches(group_stage_result, third_place_matchups):
    """
    Builds the 2026 32-team knockout bracket from group-stage results.
    """

    third_place_groups = [
        row["group"] for row in group_stage_result
        if row["group_rank"] == 3
    ]
    selection_key = "".join(sorted(third_place_groups))
    selected_assignment = third_place_matchups.get(selection_key)

    if selected_assignment is None:
        raise ValueError(
            f"No third-place assignment found for groups: {selection_key}"
        )

    third_place_opponents = selected_assignment["matchups"]
    group_stage_lookup = {
        (row["group"], row["group_rank"]): row["team"]
        for row in group_stage_result
    }
    match_rows = []

    def slot_to_team(slot):
        return group_stage_lookup[(slot[1], int(slot[0]))]

    def add_match(match, home_slot, away_slot, to_match, stage):
        match_rows.append(
            {
                "match": match,
                "home_team": "" if home_slot == "" else slot_to_team(home_slot),
                "away_team": "" if away_slot == "" else slot_to_team(away_slot),
                "elo_prob_home": "",
                "result_home": "",
                "advances": "",
                "to_match": to_match,
                "loses": "",
                "penalties": "",
                "stage": stage,
            }
        )

    round_of_32 = [
        ("2A", "2B", 16),
        ("1E", third_place_opponents["1E"], 17),
        ("1F", "2C", 16),
        ("1C", "2F", 18),
        ("1I", third_place_opponents["1I"], 17),
        ("2E", "2I", 18),
        ("1A", third_place_opponents["1A"], 19),
        ("1L", third_place_opponents["1L"], 19),
        ("1D", third_place_opponents["1D"], 21),
        ("1G", third_place_opponents["1G"], 21),
        ("2K", "2L", 20),
        ("1H", "2J", 20),
        ("1B", third_place_opponents["1B"], 23),
        ("1J", "2H", 22),
        ("1K", third_place_opponents["1K"], 23),
        ("2D", "2G", 22),
    ]

    for match, (home_slot, away_slot, to_match) in enumerate(round_of_32):
        add_match(match, home_slot, away_slot, to_match, "round_of_32")

    future_matches = [
        (16, 24, "round_of_16"),
        (17, 24, "round_of_16"),
        (18, 26, "round_of_16"),
        (19, 26, "round_of_16"),
        (20, 25, "round_of_16"),
        (21, 25, "round_of_16"),
        (22, 27, "round_of_16"),
        (23, 27, "round_of_16"),
        (24, 28, "quarterfinals"),
        (25, 28, "quarterfinals"),
        (26, 29, "quarterfinals"),
        (27, 29, "quarterfinals"),
        (28, 30, "semifinals"),
        (29, 30, "semifinals"),
        (30, 31, "final"),
        (31, 31, "third_place"),
    ]

    for match, to_match, stage in future_matches:
        add_match(match, "", "", to_match, stage)

    return match_rows


def collect_2026_playoff_stage_results(games):
    """
    Collects bracket-level results from one simulated 2026 knockout stage.
    """

    def stage_advances(stage):
        return [
            game["advances"] for game in games
            if game["stage"] == stage
        ]

    def stage_loses(stage):
        return [
            game["loses"] for game in games
            if game["stage"] == stage
        ]

    stage_results = {
        "Round_of_16": stage_advances("round_of_32"),
        "Quarterfinals": stage_advances("round_of_16"),
        "Semifinals": stage_advances("quarterfinals"),
        "Final": stage_advances("semifinals"),
        "third_place_match": stage_loses("semifinals"),
    }

    final_game = [
        game for game in games
        if game["stage"] == "final"
    ][0]
    third_place_game = [
        game for game in games
        if game["stage"] == "third_place"
    ][0]

    stage_results["Champion"] = final_game["advances"]
    stage_results["second_place"] = final_game["loses"]
    stage_results["third_place"] = third_place_game["advances"]
    stage_results["fourth_place"] = third_place_game["loses"]

    for match_number in range(16, 32):
        game = games[match_number]
        stage_results[f"match{match_number}"] = [
            game["home_team"],
            game["away_team"],
        ]

    return stage_results


def simulate_2026_tournament(
    matches_file,
    roster_file,
    third_place_matchups,
    ternary=True,
):
    """
    Simulates one full 2026 World Cup from group stage through the final.
    """

    group_games = read_games(matches_file)
    teams = read_teams(roster_file)

    simulate_group_stage(group_games, teams, ternary=ternary)

    group_stage_rankings = rank_2026_group_stage(teams, group_games)
    group_stage_result = select_2026_knockout_teams(group_stage_rankings)
    playoff_games = build_2026_playoff_matches(
        group_stage_result,
        third_place_matchups,
    )

    simulate_playoffs(playoff_games, teams, ternary=ternary)

    qualified_teams = {
        row["team"] for row in group_stage_result
    }
    team_results = []

    for row in group_stage_rankings:
        result = "Group_stage"

        if row["team"] in qualified_teams:
            result = collect_playoff_results_from_games(
                row["team"],
                playoff_games,
            )

        team_results.append(
            {
                "group": row["group"],
                "team": row["team"],
                "points": row["points"],
                "group_rank": row["group_rank"],
                "start_rating": row["start_rating"],
                "rating_after_group": row["rating_after_group"],
                "result": result,
            }
        )

    return {
        "group_games": group_games,
        "group_stage_rankings": group_stage_rankings,
        "group_stage_result": group_stage_result,
        "playoff_games": playoff_games,
        "team_results": team_results,
        "stage_results": collect_2026_playoff_stage_results(playoff_games),
    }
