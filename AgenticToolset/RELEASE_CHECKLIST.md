# Release / Publication Checklist

Fill and verify each item before publishing a public release.

- [ ] Confirm `.gitignore` contains AI, model, and secret patterns
- [ ] Remove or rotate any plaintext secrets from the repository
- [ ] Ensure `PROJECT_BRIEF.md` and `ONBOARDING.md` do not contain sensitive info
- [ ] Run full test suite: `pytest` (or project-specific test command)
- [ ] Update `CHANGELOG.md` with release notes
- [ ] Ensure `LICENSE` is present and correct
- [ ] Bump version (if applicable) and tag the release
- [ ] Build release artifacts and smoke-test them
- [ ] Create release PR and ensure CI passes
- [ ] Create archival backup if required

Notes:
- This checklist is a starting point — adapt to your project's requirements.
