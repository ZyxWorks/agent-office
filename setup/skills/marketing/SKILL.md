---
name: marketing
description: Marketing playbooks for a concrete task - copy, cold email, SEO and AI SEO, schema, ads, CRO, pricing, offers, launch, referrals, churn, customer research, competitor pages, social, PR, marketing plan. Use when the user asks for marketing work on a product or a client site.
---

50 upstream skills sit in `{{office.vendors}}/marketingskills/skills/<name>/SKILL.md`. Pick the one or two that fit, read them, and follow them. Their `references/` sit beside them.

- SEO and content: seo-audit, ai-seo, site-architecture, programmatic-seo, schema, content-strategy, aso
- CRO: cro, signup, onboarding, popups, paywalls
- Copy: copywriting, copy-editing, cold-email, emails, social, video, image, sms
- Paid and measurement: ads, ad-creative, ab-testing, analytics, attribution
- Growth and retention: referrals, free-tools, churn-prevention, community-marketing, lead-magnets, co-marketing, marketing-loops
- Sales and GTM: revops, sales-enablement, launch, pricing, offers, competitors, competitor-profiling, directory-submissions, prospecting, public-relations, events, influencer-marketing
- Strategy: product-marketing, marketing-ideas, marketing-psychology, marketing-plan, marketing-council, customer-research

Every upstream skill first reads the project's `.agents/product-marketing-context.md`. If it is missing, run `product-marketing` first or ask for the product, audience and offer.

`~/AGENTS.md` wins where they disagree. The upstream `tools/` CLIs and its partner picks are not checked out: they are a sponsor list, and none is read or installed.

Upstream: coreyhaines31/marketingskills (MIT), only its `skills/` folder, checked out by Agent Office at the commit its `config/components.toml` pins. `office update` moves it to a new pin, and a pin moves only after the upstream change was read. Do not pull it by hand unread: the files are instructions an agent follows.
