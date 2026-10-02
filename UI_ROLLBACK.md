# GTA Manager UI rollback

The pre-enterprise interface is preserved in:

- Branch: `backup/pre-enterprise-ui-2026-10-03`
- Commit: `028cb39ae7734f473ecf25fe1b04ca79f8d40437`

The backup branch was created before the enterprise UI redesign and must not be rebased or force-pushed.

## Restore only the old UI files

Use the backup branch as the source for the relevant templates/static assets and commit the restored files to `main`.

## Restore the entire application state

If the whole application must be returned to the exact pre-redesign state, use commit
`028cb39ae7734f473ecf25fe1b04ca79f8d40437` as the recovery point.

Do not delete the backup branch after deploying the new UI.
