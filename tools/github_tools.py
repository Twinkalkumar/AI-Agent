"""
GitHub tools for the agent — list repos, list files, read a file, write/commit
a file. Uses a personal access token (GITHUB_TOKEN env var) via PyGithub.

Repo names can be given as "owner/repo" (e.g. "torvalds/linux"), or just
"repo" if GITHUB_DEFAULT_OWNER is set (defaults to your own username).

SAFETY NOTE: github_write_file directly commits to the repo/branch you give
it. There is no undo beyond git history. Keep the token's scope as narrow
as possible (see README) and consider testing on a throwaway repo first.
"""

import os
from github import Github, GithubException, UnknownObjectException

_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
_DEFAULT_OWNER = os.environ.get("GITHUB_DEFAULT_OWNER")

_client = None


def _get_client() -> Github:
    global _client
    if _client is None:
        if not _GITHUB_TOKEN:
            raise RuntimeError(
                "GITHUB_TOKEN is not set. Create a personal access token "
                "(repo scope) and set it as an env var — see .env.example."
            )
        _client = Github(_GITHUB_TOKEN)
    return _client


def _resolve_repo_name(repo: str) -> str:
    """Allow 'reponame' shorthand if GITHUB_DEFAULT_OWNER is set."""
    if "/" in repo:
        return repo
    if _DEFAULT_OWNER:
        return f"{_DEFAULT_OWNER}/{repo}"
    raise ValueError(
        f"'{repo}' has no owner and GITHUB_DEFAULT_OWNER is not set. "
        f"Use 'owner/{repo}' instead."
    )


def github_list_repos(visibility: str = "all") -> str:
    """List repositories the authenticated token can see.

    visibility: 'all', 'public', or 'private'
    """
    try:
        gh = _get_client()
        user = gh.get_user()
        repos = user.get_repos(visibility=visibility)
        lines = [f"- {r.full_name} ({'private' if r.private else 'public'}): {r.description or 'no description'}"
                 for r in repos]
        return "\n".join(lines) if lines else "No repositories found."
    except GithubException as e:
        return f"GitHub error: {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {e}"


def github_list_files(repo: str, path: str = "") -> str:
    """List files and folders at a path in a repo (default: repo root)."""
    try:
        gh = _get_client()
        repository = gh.get_repo(_resolve_repo_name(repo))
        contents = repository.get_contents(path)
        if not isinstance(contents, list):
            contents = [contents]
        lines = [f"- {'[dir] ' if c.type == 'dir' else ''}{c.path}" for c in contents]
        return "\n".join(lines) if lines else "Empty directory."
    except UnknownObjectException:
        return f"Path '{path}' not found in repo '{repo}'."
    except GithubException as e:
        return f"GitHub error: {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {e}"


def github_read_file(repo: str, path: str) -> str:
    """Read the text content of a single file in a repo."""
    try:
        gh = _get_client()
        repository = gh.get_repo(_resolve_repo_name(repo))
        file_content = repository.get_contents(path)
        if isinstance(file_content, list):
            return f"'{path}' is a directory, not a file."
        # Cap what we return to the model to avoid blowing the context window
        text = file_content.decoded_content.decode("utf-8", errors="replace")
        if len(text) > 8000:
            text = text[:8000] + "\n... [truncated, file is longer]"
        return text
    except UnknownObjectException:
        return f"File '{path}' not found in repo '{repo}'."
    except GithubException as e:
        return f"GitHub error: {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {e}"


def github_write_file(repo: str, path: str, content: str, commit_message: str, branch: str = None) -> str:
    """Create a new file or update an existing one, committing directly to the given branch.

    WARNING: this commits immediately — there is no confirmation step here.
    """
    try:
        gh = _get_client()
        repository = gh.get_repo(_resolve_repo_name(repo))
        branch = branch or repository.default_branch

        try:
            existing = repository.get_contents(path, ref=branch)
            result = repository.update_file(
                path, commit_message, content, existing.sha, branch=branch
            )
            action = "Updated"
        except UnknownObjectException:
            result = repository.create_file(path, commit_message, content, branch=branch)
            action = "Created"

        commit_sha = result["commit"].sha
        return f"{action} '{path}' on branch '{branch}'. Commit: {commit_sha}"
    except GithubException as e:
        return f"GitHub error: {e.data.get('message', str(e))}"
    except Exception as e:
        return f"Error: {e}"
