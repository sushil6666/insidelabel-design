<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->
- Claim rules live in the `claim_rules` table (approved rows used at scan time, bundled claim_rules.json as fallback); unknown claims queue in `unmatched_claims`. Why: the checker grows without code changes while staying deterministic.
- AI only drafts rules into status 'draft' using a fixed set of check types; only the admin (first account, via user_roles) approves. Why: no unreviewed rule can flag a product.
- Scan responses include their extracted label text and reading status; the result screen uses those as evidence rather than inferring source text from verdicts. Why: people must be able to check a finding against what the reader actually saw.
