<!-- version: 1.0.0 -->
# Analysis instructions

For each posting in <JOB_POSTINGS>, produce one analysis object.

## 1. Match scoring (output: `match_percentage`, integer 0-100)

Apply this weighted rubric. Skip any criterion the posting does not mention; redistribute its weight proportionally over the remaining criteria.

- Required hard skills (40): explicit technical skills listed in the post.
- Years of experience (30): minimum required vs. relevant experience on resume.
- Education (20): degree / qualification explicitly required by the post.
- Domain keywords (10): tools, frameworks, methodologies, industry-specific terms.

Use semantic equivalence ("Node.js" ~ "JavaScript backend"; "K8s" ~ "Kubernetes"; "Postgres" ~ "RDBMS"). Do NOT count soft skills (communication, teamwork, leadership) toward the score.

If the posting specifies a range like "3-5 years", use the lower bound (3). If the resume's relevant experience meets or exceeds the requirement, set `experience_gap` to 0. If the posting does not specify experience, set both `required_experience` and `experience_gap` to 0. Round `match_percentage` to the nearest integer.

## 2. Extraction (per posting)

Pull each field directly from the post text. Use null for missing scalars and [] for missing arrays. Do not invent values.

- `contact_email`: every plausible email in the post body. Deduplicated.
- `contact_number`: every plausible phone number. Deduplicated.
- `application_link`: every URL that is plausibly an application target. Prefer external forms (Greenhouse, Lever, Workday, Typeform, Google Forms, paths containing `/apply`, `/careers`, `/jobs`). Exclude LinkedIn profile or company landing pages.
- `title`: the role's standardised title (e.g., "Senior Backend Engineer").
- `company_name`: registered name without legal suffixes ("Inc", "LLC", "Pvt. Ltd.").
- `location`: city/state/country plus mode ("Remote", "Hybrid", "On-site") if stated.
- `salary`: exact phrasing including range and benefits if mentioned.
- `missing_skills`: skills explicitly required by the post but absent from the resume.

## 3. should_apply

A boolean derived from the rubric, not a hidden judgment knob. Set true iff ALL of:
- `match_percentage` >= {{match_threshold}}
- `experience_gap` <= {{max_experience_gap}}
- `contact_email` is non-empty OR `application_link` is non-empty
- `employment_type` (if known) is not in {{rejected_employment_types}}

Otherwise false.

## 4. additional_data

Populate every supported field from the schema. Anything mentioned that does not fit the schema goes into `additional_data.other` as key-value strings.

## 5. Edge cases

- Multiple postings: emit one element per posting, in input order.
- Block is empty or non-job content: emit one element with `match_percentage: 0`, `should_apply: false`, empty `message_content`, and `additional_data.other.skip_reason` set to a short tag ("empty_post", "not_a_job_post", etc.).
- Post explicitly forbids cold applications: `should_apply: false`, set `additional_data.other.skip_reason: "cold_apply_forbidden"`.
- Post has no application mechanism (no email, no link, no phone): `should_apply: false`.
