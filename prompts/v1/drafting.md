<!-- version: 1.0.0 -->
# Drafting instructions

Produce `message_content` ONLY when `should_apply` is true. Otherwise set both `subject` and `body` to empty strings "".

## Subject

Format: "Application for {role} at {company_name}"
- Strip legal suffixes from company_name ("Inc", "LLC", "Pvt. Ltd.").
- If role is missing: use the post's primary tech stack ("Application for Go Developer").
- If company_name is missing: drop " at {company_name}" and stop after the role.

The pipeline appends a subject postfix automatically. Do NOT add suffixes like "| 3 YoE" yourself.

## Body -- strictly under 130 words, no closer

Body covers greeting through last value-prop sentence. Do NOT write "Thanks", "Regards", "Best", or any sign-off -- the pipeline appends the closer and signature.

Greeting:
- If the post names a recruiter/poster, address them by first name ("Hi Priya,").
- Otherwise "Hi Team,".

Paragraph 1 (introduction, under 40 words):
- One sentence on the candidate's current role and years of relevant experience (from <RESUME>).
- One sentence calling out the two most relevant skills the post lists that ALSO appear on the resume.

Paragraph 2 (proof, under 50 words):
- Pick ONE project from <RESUME> whose tech stack overlaps with the post.
- Lead with a quantified outcome ("Cut p95 latency by 38%", "Saved $12K/mo in infra cost").
- One short sentence linking why that work transfers to the role.

Paragraph 3 (close, under 30 words):
- A specific value proposition tied to the post (e.g., "I can take ownership of your billing migration to Postgres").
- No sign-off, no "Looking forward".

Formatting:
- Plain text. No markdown, no bullets, no asterisks in body.
- Two newlines between paragraphs.

## Role-specific tailoring

When the candidate has provided role-specific emphasis rules (in <CANDIDATE>), use them to decide which projects/skills to highlight. If no rules are provided, pick the most relevant project from <RESUME> based on tech stack overlap.

{{role_emphasis_block}}

## Hard constraints

1. Body strictly under 130 words.
2. No closer or sign-off -- the pipeline adds it.
3. Mention only skills/projects actually present in <RESUME>.
4. Quote numbers exactly as they appear in <RESUME>. No fabricated metrics.
5. No corporate boilerplate ("I'd love the opportunity to chat", "I'm a perfect fit").
