import os
from datetime import datetime

def make_specific_commits():
    # Specific dates with 4 commits each
    dates = [
<<<<<<< HEAD
        "2026-11-09",
        "2026-11-10"
=======
        "2026-10-12",
        "2026-10-13"
>>>>>>> 81be2d63a53bdd4458087d413ff8e6981320ab94
    ]

    for date_str in dates:
        for i in range(4):
            # Different times for each commit
            commit_time = datetime.strptime(
                f"{date_str} {10+i}:{15+i}:00",
                "%Y-%m-%d %H:%M:%S"
            )

            formatted_date = commit_time.strftime('%Y-%m-%d %H:%M:%S')

            # Update file
            with open("activity.txt", "a") as f:
                f.write(f"Commit on {formatted_date}\n")

            # Git add
            os.system("git add activity.txt")

            # Backdated commit
            os.system(
                f'git commit -m "Update activity log" --date="{formatted_date}"'
            )

    print("Success! 4 commits created for 12 July 2026 and 13 July 2026.")


if __name__ == "__main__":
    make_specific_commits()