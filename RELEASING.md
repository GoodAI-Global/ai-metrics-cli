# Releasing Good AI Metrics

This document describes the release process for Good AI Metrics.

## Prerequisites

- Write access to the repository
- PyPI account with upload permissions (for package releases)
- All CI checks passing on `main`

## Release Checklist

### 1. Prepare the Release

1. Ensure all changes are merged to `main`
2. Verify CI is passing: `make lint test`
3. Update version in `pyproject.toml`
4. Update `CHANGELOG.md`:
   - Move items from `[Unreleased]` to new version section
   - Add release date
   - Update comparison links at bottom

### 2. Create Release Commit

```bash
# Update version in pyproject.toml
# Update CHANGELOG.md

git add pyproject.toml CHANGELOG.md
git commit -m "Release v0.x.x"
git push origin main
```

### 3. Tag the Release

```bash
git tag -a v0.x.x -m "Release v0.x.x"
git push origin v0.x.x
```

### 4. Create GitHub Release

1. Go to GitHub Releases
2. Click "Create a new release"
3. Select the tag you just created
4. Title: `v0.x.x`
5. Description: Copy relevant section from CHANGELOG.md
6. Publish release

### 5. Publish to PyPI (Optional)

```bash
# Build package
make clean build

# Upload to PyPI
pip install twine
twine upload dist/*
```

## Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0): Breaking changes to public API
- **MINOR** (0.1.0): New features, backwards compatible
- **PATCH** (0.0.1): Bug fixes, backwards compatible

## Pre-release Versions

For testing releases before stable:

- `0.1.0a1` - Alpha release
- `0.1.0b1` - Beta release
- `0.1.0rc1` - Release candidate

## Hotfix Process

For urgent fixes to released versions:

1. Create branch from the release tag: `git checkout -b hotfix/v0.1.1 v0.1.0`
2. Apply fix and test
3. Update version to patch level (e.g., `0.1.1`)
4. Update CHANGELOG.md
5. Merge to main and tag

## Rollback

If a release has critical issues:

1. Yank from PyPI: `twine yank goodai-metrics==0.x.x`
2. Delete GitHub release (mark as draft)
3. Create hotfix release

## Post-Release

- Announce in relevant channels
- Update any external documentation
- Monitor for issues
