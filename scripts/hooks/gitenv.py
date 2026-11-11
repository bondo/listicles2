"""Import for its side effect in every hook test module: drop the git variables that name the repository.
Git exports GIT_DIR (and friends) to hooks when pushing from a linked worktree; tests that run `git init`/`git commit` in
temp dirs would otherwise write into the real repository (R11-51). Same list as `git rev-parse --local-env-vars`."""

import os

LOCAL_ENV_VARS = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_OBJECT_DIRECTORY", "GIT_DIR",
    "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE", "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX", "GIT_SHALLOW_FILE", "GIT_COMMON_DIR",
)


def scrub():
    for name in LOCAL_ENV_VARS:
        os.environ.pop(name, None)


scrub()
