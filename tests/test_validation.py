import pytest
import pandas as pd
import os

@pytest.fixture(scope="module")
def schedule_df():
    """
    Loads the generated schedule CSV. 
    Fails the entire test suite immediately if the file does not exist.
    """
    file_path = "outputs/schedule.csv"
    assert os.path.exists(file_path), f"Schedule file not found at {file_path}. Run the solver and extractor first."
    
    df = pd.read_csv(file_path)
    assert not df.empty, "The schedule.csv file is empty."
    return df

def test_total_fixture_count(schedule_df):
    """
    Verifies that 28 (for 8 teams) fixtures were scheduled.
    """
    valid_counts = [28]
    actual_count = len(schedule_df)
    assert actual_count in valid_counts, f"Expected 28 matches, but found {actual_count}."

def test_no_double_booking(schedule_df):
    """
    Ensures no team is scheduled to play more than one match in a single round.
    """
    for round_num, group in schedule_df.groupby('Round'):
        # Combine Home and Away teams into a single list for this round
        teams_in_round = group['Home_Team'].tolist() + group['Away_Team'].tolist()
        
        # Filter out the "Idle" or "Bye" placeholders
        teams_in_round = [t for t in teams_in_round if 'Idle' not in str(t) and 'Bye' not in str(t)]
        
        # A set automatically removes duplicates. If lengths differ, a duplicate exists.
        unique_teams = set(teams_in_round)
        assert len(teams_in_round) == len(unique_teams), (
            f"Double booking detected in Round {round_num}. "
            f"Teams scheduled: {teams_in_round}"
        )

def test_total_matches_per_team(schedule_df):
    """
    Ensures every real team plays a perfect single round-robin (7 total matches).
    """
    # Filter out bye weeks
    valid_home = schedule_df[~schedule_df['Home_Team'].str.contains('Idle|Bye', na=False)]['Home_Team']
    valid_away = schedule_df[~schedule_df['Away_Team'].str.contains('Idle|Bye', na=False)]['Away_Team']
    
    # Count total appearances across both columns
    team_match_counts = pd.concat([valid_home, valid_away]).value_counts()
    
    for team, count in team_match_counts.items():
        assert count in [7], f"Team '{team}' was scheduled for {count} matches instead of 6 or 7."

def test_home_away_sequence(schedule_df):
    """
    Ensures no team plays 3 consecutive home games or 3 consecutive away games.
    """
    # Extract a list of all unique real teams
    all_teams = set(schedule_df['Home_Team']).union(set(schedule_df['Away_Team']))
    real_teams = {t for t in all_teams if 'Idle' not in str(t) and 'Bye' not in str(t)}

    for team in real_teams:
        # Isolate matches for this specific team and sort them chronologically
        team_matches = schedule_df[
            (schedule_df['Home_Team'] == team) | (schedule_df['Away_Team'] == team)
        ].sort_values('Round')
        
        # Build a sequence string (e.g., 'HHAHAA')
        sequence = []
        for _, row in team_matches.iterrows():
            if row['Home_Team'] == team:
                sequence.append('H')
            else:
                sequence.append('A')
        
        seq_string = "".join(sequence)
        
        # Assert maximum consecutive limits
        assert "HHH" not in seq_string, f"Team '{team}' violates limit with 3 consecutive home games: {seq_string}"
        assert "AAA" not in seq_string, f"Team '{team}' violates limit with 3 consecutive away games: {seq_string}"