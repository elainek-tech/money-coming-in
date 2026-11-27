# Going further (talk notes, not part of the demo)

## 1. Why a Pub/Sub-driven Firestore writer is the production shape

The demo's Cloud Run service does everything inside the webhook request: extract, save to Firestore, publish to Pub/Sub. That is the simplest thing to show live. In production, make Pub/Sub the spine instead:

```
webhook -> (validate, publish "message.received") -> ack fast
Pub/Sub -> extractor worker -> publishes "lead.scored"
Pub/Sub -> Firestore writer (idempotent) -> dashboard
Pub/Sub -> CRM sync, alerts, follow-up drafts (more subscribers, no changes upstream)
```

Why it is better:

- **Fast ack.** Telegram and Meta retry slow webhooks. Publishing takes milliseconds; a model call does not.
- **Retries and dead letters.** A failed extraction or write is retried by Pub/Sub, and poison messages go to a dead-letter topic instead of vanishing.
- **Spikes.** A campaign burst queues up instead of overloading the model quota or Firestore.
- **Fan-out.** CRM, Slack alerts and analytics subscribe to the same event without touching the intake service.
- **Closes the dual-write gap.** In the demo, if the save succeeds and the publish fails, the lead is stored but the event is lost (the code logs it). With Pub/Sub first, there is one write to the source of truth.

What it costs you:

- More moving parts to deploy and monitor.
- Delivery is at-least-once, so every writer must be idempotent. The demo already keys messages by id and events by `dedupe_key` (`lead_key:version:event`).
- Ordering is not guaranteed unless you use ordering keys (use the lead key); the dashboard becomes eventually consistent.

## 2. The full scheduled sweep (sketch, untested)

The demo only recycles a lead when it **messages again**. A sweep finds leads that went quiet and may be worth a human nudge.

1. **Cloud Scheduler** calls `POST /sweep` on the service daily. Protect it with an OIDC token from a dedicated service account (or a shared token), not the public ingest token.
2. **Mark stale.** Leads still `active` and silent longer than `DORMANT_AFTER_DAYS` become `dormant`. (The demo does this lazily, only when the lead next writes.)
3. **Re-score dormant leads.** Use the stored `objection` (for example "budget too low") to decide who is worth a look: new project launch, price drop, payment plan. This is a business rule, so keep it in code, with the model only extracting facts.
4. **Draft, never send.** Produce a suggested follow-up for a human to approve. Do not auto-send.
5. **WhatsApp rules.** A business cannot message a customer first with free text after the 24-hour window; it needs an approved template, and users must have opted in. Check Meta's current rules before building this. Telegram only allows messaging users who have started your bot.
6. **Publish** `lead.recycled` through the same path as the live return, so the dashboard and subscribers need no changes.

Cost control: cap the batch size per run and log how many leads were re-scored, so a sweep cannot run up a model bill.
