import os
from datetime import datetime

def make_specific_commits():
    # Dates with 5 commits each
    dates = [
        "2026-07-18",
        "2026-07-19"
    ]

    for date_str in dates:
        for i in range(5):
            # Different times for each commit
            commit_time = datetime.strptime(
                f"{date_str} {10+i}:{15+i}:00",
                "%Y-%m-%d %H:%M:%S"
            )

            formatted_date = commit_time.strftime("%Y-%m-%d %H:%M:%S")

            # Update file
            with open("activity.txt", "a") as f:
                f.write(f"Commit on {formatted_date}\n")

            # Stage changes
            os.system("git add activity.txt")

            # Create backdated commit
            os.system(
                f'git commit -m "Update activity log" --date="{formatted_date}"'
            )

    print("Success! 5 commits created for 18 July 2026 and 19 July 2026.")

if __name__ == "__main__":
    make_specific_commits()