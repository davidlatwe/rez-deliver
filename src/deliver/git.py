
import os
import subprocess
from datetime import datetime
from github import Github
# PyGithub, requests==2.24.0

with open(os.path.expanduser("~/github.token"), "r") as token_f:
    token = token_f.read().strip()
g = Github(token)


def clone(url, dst, branch=None, single_branch=True):
    # https://stackoverflow.com/a/4568323/14054728

    if os.path.isdir(dst + "/.git"):
        # TODO: checkout latest
        pass

    else:
        args = ["git", "clone"]

        if branch:
            args.extend(["-b", branch])

        if single_branch:
            args.append("--single-branch")

        args.extend([url, dst])

        subprocess.check_output(args)


def create_release(repo_name, branch, version, message=None):
    repo = g.get_repo(repo_name)
    release_branch = branch
    payload_version = version
    release_message = message or ""
    release_target = ""

    # check package version exists in `release_target` and `packages_path`
    # to do so, might need to generate user/dept.'s `packages_path`

    release = repo.create_git_release(payload_version, payload_version,
                                      release_message,
                                      target_commitish=release_branch)
    print(release.tag_name)

    # rez_deploy(payload_version, release_target)


def get_tags(repo_name):
    repo = g.get_repo(repo_name)
    for tag in repo.get_tags():
        print(tag.name)


def get_releases(repo_name):
    repo = g.get_repo(repo_name)
    for release in repo.get_releases():
        github_commit = repo.get_commit(release.tag_name)
        git_commit = github_commit.commit

        yield (release.tag_name,
               release.target_commitish,
               git_commit.sha[:8],
               git_commit.message)


def get_released_tags(repo_name):
    repo = g.get_repo(repo_name)
    for release in repo.get_releases():
        yield release.tag_name


def get_branches(repo_name):
    repo = g.get_repo(repo_name)
    for branch in repo.get_branches():
        github_commit = branch.commit
        git_commit = github_commit.commit
        # git_commit.committer.date
        committer_data = git_commit.committer.raw_data
        committer_name = committer_data["name"]
        commit_date = fromutcformat(committer_data["date"]).strftime("%Y-%m-%d %H:%M:%S")
        print(branch.name, committer_name, commit_date, git_commit.message)


def fromutcformat(utc_str, tz=None):
    # https://stackoverflow.com/a/63627585
    iso_str = utc_str.replace("Z", "+00:00")
    return datetime.fromisoformat(iso_str).astimezone(tz)
