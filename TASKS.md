# Tasks

## lint

Requires: venv, update

Runs all defined pre-commit hooks.

```bash
    uvx pre-commit run --config conf/pre-commit.yaml --color always --all
```

## force-update

Run: once
Requires: venv

Update all pre-commit hook versions to latest releases.

```bash
    uvx pre-commit autoupdate --config conf/pre-commit.yaml --color always

    uncommited="$(git diff --cached --name-only | sort -u | tr '\n' ' ' | xargs)"
    changes="$(git ls-files --deleted --modified --exclude-standard)"
    changes="$(printf "$changes" | sort -u | tr '\n' ' ' | xargs)"

    if [[ "$uncommited" =~ "\bconf/\pre-commit\.yaml\b" ]] || [[ "$changes" =~ "\bconf/\pre-commit\.yaml\b" ]]; then
        $XC add-precommit
    fi
```

## publish

Run: once
Requires: venv, update

Input: mode
Environment: mode=patch

Bumps project new version, build and publish the package to repository.

```bash

$XC bump "$mode"

rm -rf dist/ || true
uv build
uvx uv-publish --repo kalib
rm -rf dist/ || true
uv sync --all-extras

```

## clean

Run: once

Clean up the project working directory: remove build/, .venv/, and .ruff_cache/ directories, as well as all .pyc files and __pycache__ directories.

```bash
    rm log/*.log*          2>/dev/null || true

    rm -rf dist/           2>/dev/null || true
    rm -rf build/          2>/dev/null || true
    rm -rf src/*.egg-info/ 2>/dev/null || true

    #

    rm -rf .mypy_cache/ 2>/dev/null || true
    rm -rf .pytest_cache/ 2>/dev/null || true
    rm -rf .flakeheaven_cache/ 2>/dev/null || true

    #

    find .    -type f -delete -name "*.pyc"  || true
    find log/ -type f -delete -name "*.log*" || true

    find .    -type d -delete -name "__pycache__" || true
    find .    -type d -delete -name ".ruff_cache" || true

    $XC local-clean || true
```

## clean-all

Run: once

Clean up the project working directory: remove build/, .venv/, and .ruff_cache/ directories, as well as all .pyc files and __pycache__ directories.

```bash
    $XC stop || true
    $XC clean

    rm -rf "${UV_PROJECT_ENVIRONMENT:-.venv}/" || true
    $XC local-clean-all || true
```

## venv

Run: once

Make virtualenv for project build & test tools, install pre-push hook.

```bash
    venv=${UV_PROJECT_ENVIRONMENT:-.venv}
    if [ ! -d "$venv" ]; then
        uv venv
        uv sync --all-extras
        uvx pre-commit install \
            --config conf/pre-commit.yaml \
            --color always \
            --hook-type pre-push \
            --install-hooks \
            --overwrite
    else
        [ -f "$venv/bin/activate" ] || [ -f "$venv/Scripts/activate.bat" ]

    fi
```

## update

Run: once

Autoupdate pre-commit hooks if the last update was more than 7 days ago.

```bash

    ctime="$(date +%s)"
    mtime="$(git log -1 --format=%ct conf/pre-commit.yaml)"

    result=$(((7*86400) - (ctime - mtime)))

    if [ "$result" -le 0 ]; then
        $XC force-update
    fi
```

## bump

Run: once
Requires: venv

Inputs: mode
Environment: mode=patch

Prepare and commit a version update in a Git repository. Checks for uncommitted changes, ensures the current branch is master, verifies if there are any changes since the last tag, and bumps the version number.

After validating the readiness for an update, it prompts to proceed. Once confirmed, the script updates the pyproject.toml and .pre-commit-config.yaml files if necessary, commits the changes, tags the new version, and pushes the updates to the remote repository.

```bash
#!/bin/zsh

    uncommited="$(git diff --cached --name-only | sort -u | tr '\n' ' ' | xargs)"
    if [ -n "$uncommited" ]; then
        echo "uncommited changes found"
        exit 1
    fi

    #

    branch="$(git rev-parse --quiet --abbrev-ref HEAD 2>/dev/null)"
    if [ -z "$branch" ]; then
        exit 1
    elif [ "$branch" == "master" ]; then
        echo "using main master mode"
    else
        exit 1
    fi

    #

    changes="$(git ls-files --deleted --modified --exclude-standard)"
    changes="$(printf "$changes" | sort -u | tr '\n' ' ' | xargs)"

    if [ "$changes" == "README.md" ]; then
        echo "pipeline development mode"
    elif [ -n "$changes" ]; then
        echo "uncommited changes found"
        exit 1
    fi

    git fetch --tags --force
    current="$(git tag --list | sort -rV | head -n 1)" || retval="$?"
    if [ "$retval" -eq 128 ]; then
        current="0.0.0"
    elif [ "$retval" -gt 0 ]; then
        echo "something goes wrong on last used git tag fetch"
        exit "$retval"
    fi

    if [ -z "$current" ]; then
        echo "no current version '$current' detected, retval: '$retval'"
        exit 1
    fi

    if [ "$current" = '0.0.0' ]; then
        amount="1"
    else
        amount="$(git rev-list --count $current..HEAD)"
    fi

    uncommited="$(git diff --cached --name-only | sort -u | tr '\n' ' ' | xargs)"

    if [ "$amount" -eq 0 ] && [ -z "$uncommited" ]; then
        echo "no changes since $current"
        exit 1
    fi

    version="$(bump "$mode" "$current")"
    [ -z "$version" ] && exit 1

    revision="$(git rev-parse "$version" 2>/dev/null)" || retval="$?"

    if [ "$retval" -eq 128 ]; then
        echo "future tag $revision not found, continue"

    elif [ -z "$retval" ] && [ -n "$revision" ]; then

        echo "future tag $version already set to commit $revision, sync with remote branch!"
        exit 1

    else
        echo "something went wrong, version: '$version' revision: '$revision', retval: '$retval'"
        exit 2
    fi

    # non destructive stop here

    if [ -d "tests/" ]; then
        $XC test
    fi

    $XC lint || true
    uvx --from liontools restore-mtime || echo "datetime restoration failed, return: $?, skip"

    ls -la
    echo "we ready for bump $current -> $version, press ENTER twice to proceed or ESC+ENTER to exit"

    counter=0
    while : ; do
        read -r key

        if [[ $key == $'\e' ]]; then
            exit 1

        elif [ -z "$key" ]; then
            counter=$((counter + 1))
            if [ "$counter" -eq 2 ]; then
                break
            fi
        fi
    done

    # actions starts here

    $XC add-precommit
    $XC export-docs-requirements

    $XC update-pyproject "$current" "$version"
    $XC add-pyproject
    $XC uv-lock

    uncommited="$(git diff --cached --name-only | sort -u | tr '\n' ' ' | xargs)"
    if [ -n "$uncommited" ]; then
        git commit -m "$branch: $version"
    fi

    git tag -a "$version" -m "$version"
    git push --tags
    git push origin "$branch"

    echo "version updated to $version"
```

## add-precommit

Requires: venv

Check and format conf/pre-commit.yaml. If any changes are made, it stages the file for the next commit.

```bash

    file="conf/pre-commit.yaml"

    uvx pre-commit run check-yaml --config "$file" --color always --file "$file" || value="$?"

    while true; do
        value="0"
        uvx pre-commit run yamlfix --config "$file" --color always --file "$file" || value="$?"

        if [ "$value" -eq 0 ]; then
            break

        elif [ "$value" -eq 1 ]; then
            continue

        else
            exit "$value"

        fi
    done

    uncommited="$(git diff --cached --name-only | sort -u | tr '\n' ' ' | xargs)"
    changes="$(git ls-files --deleted --modified --exclude-standard)"
    changes="$(printf "$changes" | sort -u | tr '\n' ' ' | xargs)"

    if [[ "$uncommited" =~ "\bconf/\pre-commit\.yaml\b" ]] || [[ "$changes" =~ "\bconf/\pre-commit\.yaml\b" ]]; then
        git add "$file"
        git commit -m "(lint): autoupdate pre-commit"
    fi
```

## add-pyproject

Requires: venv

Check and format pyproject.toml. If any changes are made, it stages the file for the next commit.

```bash

    file="pyproject.toml"

    uvx pre-commit run check-toml --config conf/pre-commit.yaml --color always --file "$file" || value="$?"

    while true; do
        value="0"
        uvx pre-commit run pretty-format-toml --config conf/pre-commit.yaml --color always --file "$file" || value="$?"

        if [ "$value" -eq 0 ]; then
            break

        elif [ "$value" -eq 1 ]; then
            continue

        else
            exit "$value"

        fi
    done

    changes="$(git diff "$file")" || exit "$?"
    changes="$(printf "$changes" | wc -l)"
    if [ "$changes" -ne 0 ]; then
        git add "$file"
    fi
```

## uv-lock

Requires: venv

Check and format uv.lock. If any changes are made, it stages the file for the next commit.

```bash
    file="uv.lock"

    uv lock

    uncommited="$(git diff --cached --name-only | sort -u | tr '\n' ' ' | xargs)"
    changes="$(git ls-files --deleted --modified --exclude-standard)"
    changes="$(printf "$changes" | sort -u | tr '\n' ' ' | xargs)"

    if [[ "$uncommited" =~ "\buv.lock\b" ]] || [[ "$changes" =~ "\buv.lock\b" ]]; then
        git add "$file"
        git commit -m "(dep): lock dependencies"
    fi
```

## export-requirements

Requires: venv

```bash
    file="requirements.txt"
    if [ ! -f "$file" ]; then
        initial="1"
    fi

    uv export --color never --frozen --no-dev --format requirements-txt > "$file"

    changes="$(git diff "$file")" || exit "$?"
    changes="$(printf "$changes" | wc -l)"
    if [ "$changes" -ne 0 ] || [ "$initial" -gt 0 ]; then
        git add "$file"
    fi
```

## export-docs-requirements

Requires: venv

```bash
    file="docs/requirements.txt"
    if [ ! -f "$file" ]; then
        initial="1"
    fi

    uv export --color never --frozen --only-group docs --format requirements-txt > "$file"

    changes="$(git diff "$file")" || exit "$?"
    changes="$(printf "$changes" | wc -l)"
    if [ "$changes" -ne 0 ] || [ "$initial" -gt 0 ]; then
        git add "$file"
    fi
```

## update-pyproject

Run: once
Requires: venv

Update version in pyproject.toml file based on provided old and new version tags. It validates the version format and ensures the current tag matches the project's version before writing the new version.

```python
#!.venv/bin/python
from os import environ
from sys import argv, exit
from re import match
from pathlib import Path

import tomli_w

try:
    import tomllib as reader
except ImportError:
    import tomli as reader


ROOT = Path(environ['PWD'])

def get_version(string):
    try:
        return match(r'^(\d+\.\d+\.\d+)$', string).group(1)
    except Exception:
        print(f'could not parse version from {string}')
        exit(3)

if __name__ == '__main__':
    try:
        current_tag = get_version(argv[1])
        version_tag = get_version(argv[2])
    except IndexError:
        print('usage: xc update-pyproject <old_tag> <new_tag>')
        exit(1)

    path = ROOT / 'pyproject.toml'
    try:
        with open(path, 'rb') as fd:
            data = reader.load(fd)

    except Exception:
        print(f'could not load {path}')
        exit(2)

    try:
        current_ver = get_version(data['project']['version'])
        print(f'project version: {current_ver}')

    except KeyError:
        print(f'could not find version in {data}')
        exit(2)

    if current_tag != current_ver:
        if current_ver == version_tag:
            print(f'current version {current_ver} == {version_tag}, no update needed')
            exit(0)

        print(f'current tag {current_tag} != {current_ver} current version')
        exit(4)

    data['project']['version'] = version_tag

    try:
        with open(path, 'wb') as fd:
            tomli_w.dump(data, fd)

        print(f'project version -> {version_tag}')

    except Exception:
        print(f'could not write {path} with {data=}')
        exit(5)
```

## test

Run: once
Requires: venv

Run all tests with verbose output.

```bash
    uv run pytest -svx
```
