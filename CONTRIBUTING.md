# Contributing to UniMod

Thanks for helping improve UniMod.

## Before opening an issue

Check for duplicates and include the UniMod version, Linux distribution, game, mod framework, steps to reproduce, expected behaviour and what happened instead. Remove API keys, access tokens, `nxm://` links, personal paths and private filenames from screenshots and logs.

## Development setup

1. Fork the repository and create a branch from `main`.
2. Use Python 3.10+ with Tkinter installed; optional dependencies are in `requirements-optional.txt`.
3. Run `python3 -m unittest discover -p 'test_*.py' -q` and `python3 -m compileall -q .`.
4. Add focused tests for changed behaviour, especially install/rollback and provider boundaries.
5. Open a pull request describing the change, tests, risks, and any provider-specific permissions needed.

Changes to network download hosts, authentication, archive extraction and install paths need extra review. Never add provider secrets or files you do not have the right to redistribute.

## Project standards

Use small PRs, preserve old save/config compatibility and prefer explicit user confirmation for changes to game files. Maintain code in plain Python and follow the existing project style rather than performing unrelated formatting churn.

Maintainer review is required before merging or publishing releases.
