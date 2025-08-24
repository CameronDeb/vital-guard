Vital Guard Pro (Revenue-Ready Scaffold)
=======================================
Run locally:
1) python -m venv .venv && source .venv/bin/activate  (Windows: .venv\Scripts\activate)
2) pip install -r requirements.txt
3) cp .env.example .env  (fill optional keys for OpenAI/SMTP/Twilio/Stripe)
4) python app.py
5) http://localhost:5000

Key Features
- Auth + per-user Profiles
- Care Team (caregivers can manage someone else with permission)
- Symptom Checker (OpenAI optional; heuristic fallback)
- Health Coach Plan (AI-generated plan using your full context)
- Reminders with timezone + pre-notify offset; email/SMS notifications
- Billing scaffold (Stripe Checkout) — set STRIPE_* to enable
- Data export (JSON) for user-owned portability
- White/red medical UI with underglow and animations
