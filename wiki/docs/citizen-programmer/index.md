---
title: "I Use AI to Build Things at Work"
---

# I Use AI to Build Things at Work

If you use AI tools like ChatGPT, Claude, Copilot, or similar to build plugins, automations, scripts, dashboards, or integrations at work — this page is for you. You may be doing something risky without realising it, and it's not your fault.

## What Can Go Wrong

These are real patterns that AI tools produce. They are not obvious mistakes — the code works, the tool does what you asked, and everything looks fine. Until it doesn't.

**Stale data with no warning.** You asked an AI to build a reporting plugin. It pulls data from your database and shows a dashboard. But when the database connection drops briefly, the plugin silently shows yesterday's data with no indication anything is wrong. Your team makes decisions based on stale numbers.

**Bad data flowing straight through.** You asked an AI to connect two systems. It takes data from the external system and puts it straight into your internal database. No validation, no checking. If the external system sends bad data, your internal records are corrupted.

**Lost records of important actions.** You asked an AI to automate an approval workflow. When the approval fails to save, the AI wrote code that logs the error and moves on. The approval happened, but there's no record of it. If someone asks "who approved this and when?" — the answer is "we don't know."

**Trusting someone else's word without checking.** You asked an AI to build an integration with a partner system. The partner system says "this person is verified" and your tool grants them access — no independent check, no record of why access was given. If the partner system is wrong or compromised, everyone it vouches for gets in.

## Self-Assessment

Answer these questions about something you've built with an AI tool:

1. Does your AI-built tool connect to a database or system that other people rely on?
2. Does it run automatically (on a schedule, on a trigger) without you watching?
3. Would anyone be harmed, misinformed, or unable to do their job if it silently produced wrong results?
4. Did you test what happens when a connection fails or data is missing?
5. Does anyone in IT or security know this tool exists?
6. If you answered "yes" to two or more of these questions, talk to your IT team. You've probably built something valuable — but it may need guardrails you can't add yourself.

## What to Do Monday Morning

Talk to your IT team or your manager. Share what you've built. Ask them to review it.

This isn't about getting in trouble — it's about making sure the useful thing you built doesn't accidentally cause problems. You built something that works and that your team finds valuable. That's good. The next step is making sure it's safe, and that's a conversation, not a confession.

Your IT team can help with things like: what happens when a connection drops, whether the right checks are in place, and whether anyone else needs to know the tool exists. These are things that are hard to get right on your own, and they're not things the AI tool will warn you about.

[Read the full security analysis →](../paper.md#128-coding-is-no-longer-confined-to-developers)
