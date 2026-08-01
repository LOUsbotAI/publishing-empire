# LOUSTA Mainframe — Project Status

Canonical reference for the project's current state and standing rules. Update this
file, not a chat transcript, when architectural decisions are made.

## Current Focus

- Stabilise the Termux-based mainframe environment.
- Repair only broken components while preserving live systems.
- Verify production services before making changes.
- Maintain the Android + PM2 + Cloudflare architecture.

## Core Configuration

- Termux is the primary command environment.
- PM2 manages long-running services.
- Cloudflare Tunnel provides external connectivity.
- Stripe and Gumroad integrations are retained and inspected without altering credentials.
- Website: lousta.com remains part of the production environment.

## Project Progress

- Book generation pipeline established.
- Publishing pipeline defined (Book → PDF → Audiobook → Video → Distribution).
- Revenue monitoring infrastructure present.
- Multiple autonomous agents identified and organised.

## Agent & Service Audit

- Controller/orchestrator architecture reviewed.
- Publishing, telemetry, watchdog, dashboard, webhook and rendering services identified.
- Live services should be verified before any repair.

## Standing Project Rules

1. Do not disconnect or rotate live credentials unless explicitly requested.
2. Mask secrets in all logs and reports.
3. No fake or simulated revenue or payment events.
4. Avoid moving or renaming production folders.
5. Apply minimal, targeted fixes only.

## Outstanding Work

- Verify PM2 process health.
- Confirm Cloudflare tunnel.
- Resolve remaining Gumroad authentication issues.
- Continue debugging any failing services.
- Increase publishing automation and revenue generation.

## Resume Point

Continue from the latest Termux audit. Keep the mainframe stable while reconnecting
any non-working components. Record all future architectural decisions in this
document so it remains the project's canonical reference.
