# Import provenance

OpenSDL began from the user-supplied `opensdl-framework-v0.1-alpha.zip` source archive on
2026-08-02.

- Archive SHA-256: `ef828e1d04ddff429804a5038852395d97597e213df21f5e1adefd2fb49c6729`
- Archive entries: 290 files under `opensdl-framework/`
- Integrity result: every entry listed in the supplied `SHA256SUMS` passed verification
- Git metadata in the archive: none
- Preserved import commit: `c2289f2ca9f272423527eda6b182ab5b67dc7ffa`

That commit is the immutable imported snapshot, and it carries the four files that describe it —
`SHA256SUMS`, `REPO_TREE.txt`, `package-manifest.json`, and `PACKAGE_MANIFEST.md`. They are byte
identical to the archive's and were never edited afterwards, so the import evidence is complete and
permanent at that commit:

```bash
git show c2289f2:SHA256SUMS
git show c2289f2:REPO_TREE.txt
```

They no longer sit at the repository root, because they describe a snapshot from August 2026 and
looked like current ones. A root-level `SHA256SUMS` invites `sha256sum -c`, and running it against
the working tree failed on the majority of its entries — every file changed since the import.
Nothing read them, nothing regenerated them, and no check would have noticed had their contents
rotted; the disclaimer that they were historical lived only in this file, one directory away from
the artifact making the claim.

Reproducibility of the *current* repository is established by different means, each of which is
enforced rather than asserted: Git history, the committed `uv.lock` consumed with `--locked`
everywhere, a headless rebuild that compares the reference scene's exported bytes, and the checks
listed in [validation report](validation.md).
