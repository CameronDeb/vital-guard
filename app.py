import os, json, smtplib, hmac, hashlib
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone
import pytz
import logging # Import the logging library

# ---- VITAL FIX: LOAD .env FILE ----
from dotenv import load_dotenv
load_dotenv()
# ------------------------------------

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler

# Optional libs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
USE_OPENAI = bool(OPENAI_API_KEY)
client = None
if USE_OPENAI:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        print(f"❌ CRITICAL ERROR: Failed to initialize OpenAI client: {e}")
        client = None
        USE_OPENAI = False
else:
    print("ℹ️ INFO: USE_OPENAI is False. Running in non-AI mode.")


# Optional Twilio
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")
try:
    from twilio.rest import Client as TwilioClient
    twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN) if (TWILIO_SID and TWILIO_TOKEN) else None
except Exception:
    twilio_client = None

# Optional Stripe
import stripe as _stripe
STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLIC = os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
if STRIPE_SECRET:
    _stripe.api_key = STRIPE_SECRET

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY","dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL","sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["APP_TZ"] = os.getenv("APP_TZ","UTC")

# Set up logging
logging.basicConfig(level=logging.INFO)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------------- Models ----------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_pro = db.Column(db.Boolean, default=False)

class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    name = db.Column(db.String(120), default="")
    age = db.Column(db.Integer)
    gender = db.Column(db.String(20), default="")
    weight_kg = db.Column(db.Float)
    height_cm = db.Column(db.Float)
    conditions = db.Column(db.Text, default="")
    allergies = db.Column(db.Text, default="")
    medications = db.Column(db.Text, default="")
    emergency_contact = db.Column(db.String(200), default="")
    phone = db.Column(db.String(32), default="")
    notify_email = db.Column(db.Boolean, default=True)
    notify_sms = db.Column(db.Boolean, default=False)
    tz = db.Column(db.String(64), default=os.getenv("APP_TZ","UTC"))
    # Preferences / knowledge profile for AI
    goals = db.Column(db.Text, default="")        # e.g., "lose 10 lbs safely", "walk 6k steps/day"
    diet_prefs = db.Column(db.Text, default="")   # e.g., "vegetarian", "low sodium"
    activity_limits = db.Column(db.Text, default="") # e.g., "knee pain; avoid high impact"
    notes = db.Column(db.Text, default="")        # general notes

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(50), default="general")
    due_at = db.Column(db.DateTime, nullable=False, index=True)  # stored in UTC
    pre_notify_min = db.Column(db.Integer, default=0)  # minutes before due_at to notify
    notes = db.Column(db.Text, default="")
    sent_at = db.Column(db.DateTime, nullable=True)

class CareTeam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    caregiver_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    role = db.Column(db.String(50), default="viewer")  # viewer|editor

class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    kind = db.Column(db.String(50), default="coach")  # coach|visit_prep
    content = db.Column(db.Text, default="")

# ---------------- Helpers ----------------
@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))

def bootstrap_db():
    with app.app_context(): db.create_all()

def user_tz():
    tzname = None
    if current_user.is_authenticated:
        p = Profile.query.filter_by(user_id=current_user.id).first()
        if p and p.tz: tzname = p.tz
    if not tzname: tzname = app.config["APP_TZ"]
    try:
        return pytz.timezone(tzname)
    except Exception:
        return pytz.UTC

def local_to_utc(dt_local, tz):
    return tz.localize(dt_local).astimezone(pytz.UTC).replace(tzinfo=None)

def utc_to_local(dt_utc, tz):
    return pytz.UTC.localize(dt_utc).astimezone(tz)

def parse_local_datetime(s, tz):
    try:
        # "YYYY-MM-DD HH:MM"
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        return local_to_utc(dt, tz)
    except Exception:
        return None

def build_ai_context(profile: Profile):
    if not profile:
        return "No profile on file."
    ctx = {
        "name": profile.name,
        "age": profile.age,
        "gender": profile.gender,
        "weight_kg": profile.weight_kg,
        "height_cm": profile.height_cm,
        "conditions": profile.conditions,
        "allergies": profile.allergies,
        "medications": profile.medications,
        "goals": profile.goals,
        "diet_prefs": profile.diet_prefs,
        "activity_limits": profile.activity_limits,
        "notes": profile.notes,
    }
    return json.dumps(ctx, ensure_ascii=False)

def send_email(to_email: str, subject: str, body: str):
    host=os.getenv("SMTP_HOST"); port=int(os.getenv("SMTP_PORT","587"))
    user=os.getenv("SMTP_USER"); pwd=os.getenv("SMTP_PASS")
    sender=os.getenv("SMTP_FROM", user or "no-reply@vitalguard.local")
    if not (host and user and pwd and to_email): return False
    msg=MIMEText(body,"plain","utf-8"); msg["Subject"]=subject; msg["From"]=sender; msg["To"]=to_email
    import ssl; ctx=ssl.create_default_context()
    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls(context=ctx); server.login(user, pwd); server.sendmail(sender, [to_email], msg.as_string())
        return True
    except Exception:
        return False

def send_sms(to_phone: str, body: str):
    if not (twilio_client and TWILIO_FROM and to_phone): return False
    try:
        twilio_client.messages.create(from_=TWILIO_FROM, to=to_phone, body=body)
        return True
    except Exception:
        return False

# ---------------- Scheduler ----------------
def process_due_reminders():
    with app.app_context():
        now = datetime.now(timezone.utc)
        pending = Reminder.query.filter(Reminder.sent_at.is_(None)).all()
        for r in pending:
            due = r.due_at
            notify_at = due - timedelta(minutes=r.pre_notify_min or 0)
            if now >= notify_at:
                user = User.query.get(r.user_id)
                prof = Profile.query.filter_by(user_id=r.user_id).first()
                subject = f"Vital Guard Reminder: {r.title}"
                local_due = utc_to_local(due, pytz.timezone(prof.tz or "UTC")) if prof else due
                body = f"""{r.title}
Type: {r.kind}
When: {local_due.strftime("%b %d, %Y %H:%M")}
Notes: {r.notes or '-'}
"""
                if (prof is None) or prof.notify_email: send_email(user.email, subject, body)
                if prof and prof.notify_sms and prof.phone: send_sms(prof.phone, f"{r.title} at {local_due.strftime('%b %d %H:%M')} — {r.notes or ''}")
                r.sent_at = now; db.session.add(r)
        db.session.commit()

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(process_due_reminders, "interval", seconds=60)
scheduler.start()

# ---------------- Routes ----------------
@app.route("/")
def index():
    prof = Profile.query.filter_by(user_id=current_user.id).first() if current_user.is_authenticated else None
    upcoming = []
    if current_user.is_authenticated:
        upcoming = Reminder.query.filter_by(user_id=current_user.id).order_by(Reminder.due_at.asc()).limit(8).all()
    return render_template("index.html", profile=prof, upcoming=upcoming, stripe_public=STRIPE_PUBLIC, price_id=STRIPE_PRICE_ID)

# ---- Auth ----
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        pw=request.form.get("password","")
        if not email or not pw:
            flash("Email and password required.","error"); return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Account exists.","error"); return redirect(url_for("register"))
        u=User(email=email, password_hash=generate_password_hash(pw))
        db.session.add(u); db.session.commit()
        db.session.add(Profile(user_id=u.id)); db.session.commit()
        login_user(u); flash("Welcome to Vital Guard.","success")
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower(); pw=request.form.get("password","")
        u=User.query.filter_by(email=email).first()
        if not u or not check_password_hash(u.password_hash, pw):
            flash("Invalid credentials.","error"); return redirect(url_for("login"))
        login_user(u); flash("Logged in.","success"); return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user(); flash("Logged out.","success"); return redirect(url_for("index"))

# ---- Profile ----
@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    p=Profile.query.filter_by(user_id=current_user.id).first()
    if request.method=="POST":
        fields = ["name","gender","conditions","allergies","medications","emergency_contact","phone","tz","goals","diet_prefs","activity_limits","notes"]
        for f in fields: setattr(p, f, request.form.get(f,"").strip())
        p.age=int(request.form.get("age")) if request.form.get("age") else None
        p.weight_kg=float(request.form.get("weight_kg")) if request.form.get("weight_kg") else None
        p.height_cm=float(request.form.get("height_cm")) if request.form.get("height_cm") else None
        p.notify_email=bool(request.form.get("notify_email"))
        p.notify_sms=bool(request.form.get("notify_sms"))
        db.session.add(p); db.session.commit()
        flash("Profile saved.","success"); return redirect(url_for("profile"))
    return render_template("profile.html", profile=p)

# ---- Care Team ----
@app.route("/care-team", methods=["GET","POST"])
@login_required
def care_team():
    if request.method=="POST":
        caregiver_email = request.form.get("caregiver_email","").strip().lower()
        role = request.form.get("role","viewer")
        cg_user = User.query.filter_by(email=caregiver_email).first()
        if not cg_user:
            flash("No user with that email.","error"); return redirect(url_for("care_team"))
        if cg_user.id == current_user.id:
            flash("You are already the account owner.","error"); return redirect(url_for("care_team"))
        rel = CareTeam(patient_id=current_user.id, caregiver_id=cg_user.id, role=role)
        db.session.add(rel); db.session.commit()
        flash("Caregiver added.","success"); return redirect(url_for("care_team"))
    rels = CareTeam.query.filter_by(patient_id=current_user.id).all()
    caregivers = []
    for r in rels:
        u = User.query.get(r.caregiver_id)
        caregivers.append({"email": u.email, "role": r.role})
    return render_template("care_team.html", caregivers=caregivers)

# ---- Reminders ----
@app.route("/reminders", methods=["GET","POST"])
@login_required
def reminders():
    tz = user_tz()
    if request.method=="POST":
        title=request.form.get("title","").strip()
        kind=request.form.get("kind","general")
        due_local=request.form.get("due_at","").strip()
        pre_notify=int(request.form.get("pre_notify_min") or 0)
        notes=request.form.get("notes","")
        due_utc = parse_local_datetime(due_local, tz)
        if not title or not due_utc:
            flash("Title and valid local date/time required.","error")
        else:
            r=Reminder(user_id=current_user.id, title=title, kind=kind, due_at=due_utc, pre_notify_min=pre_notify, notes=notes)
            db.session.add(r); db.session.commit(); flash("Reminder added.","success")
        return redirect(url_for("reminders"))
    items = Reminder.query.filter_by(user_id=current_user.id).order_by(Reminder.due_at.asc()).all()
    # present due times localized
    def row(r):
        return {
            "id": r.id,
            "title": r.title,
            "kind": r.kind,
            "due_local": utc_to_local(r.due_at, tz).strftime("%b %d, %Y %H:%M"),
            "pre_notify_min": r.pre_notify_min,
            "notes": r.notes,
            "sent_at": utc_to_local(r.sent_at, tz).strftime("%b %d, %Y %H:%M") if r.sent_at else None
        }
    items_view = [row(r) for r in items]
    return render_template("reminders.html", items=items_view)

@app.post("/reminders/<int:rid>/delete")
@login_required
def delete_reminder(rid):
    r = Reminder.query.filter_by(id=rid, user_id=current_user.id).first_or_404()
    db.session.delete(r); db.session.commit()
    flash("Reminder deleted.","success")
    return redirect(url_for("reminders"))

# ---- AI Health Assistant ----
@app.route("/assistant")
@login_required
def assistant():
    return render_template("assistant.html")

@app.post("/api/health-assistant")
@login_required
def api_health_assistant():
    data = request.get_json(silent=True) or {}
    symptoms = (data.get("symptoms", "")).lower()
    user_query = (data.get("query", "")).lower()
    prof = Profile.query.filter_by(user_id=current_user.id).first()

    if not prof:
        return jsonify({"error": "Please complete your profile first."}), 400

    # Use the new comprehensive AI function
    if USE_OPENAI and client:
        result = ai_health_assistant(symptoms, prof, user_query)
        # NEW: Check if the result is an error and return it to the front end
        if "error" in result:
            return jsonify(result), 500
    else:
        result = heuristic_triage(symptoms, prof)

    # If the AI returns a search query, create a Google search link.
    if result.get("doctor_search_query"):
        from urllib.parse import quote_plus
        search_query = quote_plus(result["doctor_search_query"])
        result["google_search_link"] = f"https://www.google.com/search?q={search_query}"
    
    # Save the plan if one is generated
    if result.get("plan"):
        plan = Plan(user_id=current_user.id, kind="assistant", content=json.dumps(result))
        db.session.add(plan)
        db.session.commit()

    return jsonify(result)

# ---- Data Export ----
@app.get("/export")
@login_required
def export_data():
    prof = Profile.query.filter_by(user_id=current_user.id).first()
    rems = Reminder.query.filter_by(user_id=current_user.id).order_by(Reminder.due_at.asc()).all()
    plans = Plan.query.filter_by(user_id=current_user.id).order_by(Plan.created_at.desc()).all()
    data = {
        "user": {"email": current_user.email, "is_pro": current_user.is_pro},
        "profile": {
            "name": prof.name, "age": prof.age, "gender": prof.gender, "weight_kg": prof.weight_kg,
            "height_cm": prof.height_cm, "conditions": prof.conditions, "allergies": prof.allergies,
            "medications": prof.medications, "emergency_contact": prof.emergency_contact, "phone": prof.phone,
            "notify_email": prof.notify_email, "notify_sms": prof.notify_sms, "tz": prof.tz,
            "goals": prof.goals, "diet_prefs": prof.diet_prefs, "activity_limits": prof.activity_limits, "notes": prof.notes,
        },
        "reminders": [
            {"title": r.title, "kind": r.kind, "due_at_utc": r.due_at.isoformat(), "pre_notify_min": r.pre_notify_min, "notes": r.notes}
            for r in rems
        ],
        "plans": [{"kind": p.kind, "created_at": p.created_at.isoformat(), "content": p.content} for p in plans],
    }
    js = json.dumps(data, indent=2, ensure_ascii=False)
    return Response(js, mimetype="application/json")

# ---- Billing (Stripe) ----
@app.route("/billing")
@login_required
def billing():
    return render_template("billing.html", stripe_public=STRIPE_PUBLIC, price_id=STRIPE_PRICE_ID, is_configured=bool(STRIPE_PUBLIC and STRIPE_PRICE_ID))

@app.post("/api/create-checkout-session")
@login_required
def create_checkout_session():
    if not (STRIPE_PUBLIC and STRIPE_SECRET and STRIPE_PRICE_ID):
        return jsonify({"error":"Stripe not configured"}), 400
    session = _stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=request.host_url + "billing?success=1",
        cancel_url=request.host_url + "billing?canceled=1",
        customer_email=current_user.email,
        allow_promotion_codes=True,
    )
    return jsonify({"id": session.id})

@app.post("/stripe/webhook")
def stripe_webhook():
    if not STRIPE_WEBHOOK_SECRET:
        return "", 200
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature","")
    try:
        event = _stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return "", 400
    if event["type"] in ["checkout.session.completed","customer.subscription.created","customer.subscription.updated"]:
        email = event["data"]["object"].get("customer_email") or event["data"]["object"].get("customer_details",{}).get("email")
        if email:
            user = User.query.filter_by(email=email.lower()).first()
            if user:
                user.is_pro = True
                db.session.add(user); db.session.commit()
    return "", 200

# ---------------- Triage & AI Logic ----------------
URGENT_TERMS=["chest pain","pressure in chest","shortness of breath","stroke","numbness one side","fainting","severe bleeding"]
INFECTION_TERMS=["fever","chills","sore throat","cough","congestion","flu","body aches"]
DIABETES_TERMS=["thirst","urination","blurry vision","fatigue","slow healing"]
CARDIO_TERMS=["palpitations","irregular heartbeat","swelling ankles","hypertension","bp high"]
MIGRAINE_TERMS=["migraine","headache","light sensitivity","aura","nausea"]
GI_TERMS=["abdominal pain","diarrhea","constipation","heartburn","acid reflux","nausea","vomiting"]

def heuristic_triage(text, profile):
    urgency="low"; spec="primary care"; advice=[]
    def has_any(ts): return any(t in text for t in ts)
    if has_any(URGENT_TERMS): urgency="emergency"; spec="emergency medicine"; advice.append("Call emergency services or go to the ER immediately.")
    elif has_any(CARDIO_TERMS): urgency="high"; spec="cardiology"; advice.append("Schedule an urgent appointment with a cardiologist.")
    elif has_any(DIABETES_TERMS): urgency="medium"; spec="endocrinology"; advice.append("Check blood glucose and consult an endocrinologist.")
    elif has_any(INFECTION_TERMS): urgency="medium"; spec="primary care"; advice.append("Hydrate, rest; test for COVID/flu; see primary care if persists.")
    elif has_any(MIGRAINE_TERMS): urgency="low"; spec="neurology"; advice.append("Reduce light; hydrate; consider OTC analgesics if appropriate.")
    elif has_any(GI_TERMS): urgency="low"; spec="gastroenterology"; advice.append("Track foods; hydrate; seek care if severe/persistent.")
    else: advice.append("Monitor symptoms. If they worsen or persist >48 hours, see primary care.")
    lifestyle = lifestyle_recs(profile)
    return {"urgency":urgency,"suggested_specialty":spec,"advice":advice,"lifestyle":lifestyle[:6],"disclaimer":"Educational support only. Not a medical diagnosis. Seek professional care for urgent concerns."}

def bmi_from_profile(p):
    if p and p.weight_kg and p.height_cm and p.height_cm>0:
        h = p.height_cm/100.0
        return p.weight_kg/(h*h)
    return None

def lifestyle_recs(profile):
    recs=[]
    if not profile: return recs
    conds=(profile.conditions or "").lower()
    if "diabetes" in conds: recs+=["Low-glycemic carbs, lean proteins.","Avoid sugary beverages.","150 min/wk moderate activity."]
    if "hypertension" in conds or "high blood pressure" in conds: recs+=["DASH-style diet, low sodium.","Limit alcohol; monitor BP 3–4x/wk."]
    bmi=bmi_from_profile(profile)
    if bmi is not None and bmi>=30: recs+=["Swap fried→baked; soda→water.","8–10k steps/day + 2x/wk resistance."]
    if "asthma" in conds: recs+=["Track triggers; warm up before activity; keep rescue inhaler accessible."]
    return recs

def ai_health_assistant(symptom_text, profile, user_query=""):
    ctx = build_ai_context(profile)
    prompt = f"""
You are a cautious, empathetic AI health assistant named Vital Guard. Your goal is to provide safe, helpful, and clear guidance.
Return a single, valid JSON object with the following keys:
- "urgency": (string) one of "emergency", "high", "medium", "low".
- "suggested_specialty": (string) e.g., "Cardiology", "Primary Care".
- "advice": (array of strings) Actionable next steps for the user.
- "lifestyle": (array of strings) Relevant lifestyle tips based on their profile and symptoms.
- "doctor_search_query": (string) A Google search query to find a relevant local specialist. Example: "cardiologist near me for chest pain".
- "disclaimer": (string) A standard medical disclaimer.

CRITICAL SAFETY RULES:
- If symptoms include any red flags (chest pain, difficulty breathing, severe bleeding, stroke symptoms like one-sided numbness), ALWAYS set urgency to "emergency" and the first piece of advice MUST be "Call emergency services (911) or go to the nearest emergency room immediately."
- Your responses are for informational purposes only and are not a substitute for professional medical advice, diagnosis, or treatment.
- Be conservative in your recommendations. When in doubt, advise consulting a healthcare professional.

User's Symptoms: "{symptom_text}"
User's Specific Question: "{user_query}"
User's Health Profile: {ctx}
"""
    try:
        if client and client != "legacy":
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": "You are a helpful assistant that only returns valid JSON."},
                          {"role": "user", "content": prompt}],
                temperature=0.2
            )
            content = resp.choices[0].message.content.strip()
        else:
            # This part is for the older openai library version, just in case
            import openai
            resp = openai.ChatCompletion.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": "You are a helpful assistant that only returns valid JSON."},
                          {"role": "user", "content": prompt}],
                temperature=0.2,
            )
            content = resp["choices[0]"]["message"]["content"].strip()

        data = json.loads(content)
        data.setdefault("disclaimer", "Educational support only. Not a medical diagnosis. Seek professional care for urgent concerns.")
        
        # Merge heuristic lifestyle recommendations with AI-generated ones to ensure base coverage.
        base_lifestyle = lifestyle_recs(profile)
        ai_lifestyle = data.get("lifestyle", [])
        for tip in base_lifestyle:
            if tip not in ai_lifestyle:
                ai_lifestyle.append(tip)
        data["lifestyle"] = ai_lifestyle
        return data

    except Exception as e:
        # NEW DEBUGGING STEP: Return the error message itself
        app.logger.error(f"AI call failed: {e}")
        return {"error": str(e)}


if __name__=="__main__":
    bootstrap_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",5000)), debug=True)
